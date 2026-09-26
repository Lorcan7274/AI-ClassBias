import json

from conftest import CALLS_PER_SESSION

from pipeline.client import DryRunClient
from pipeline.cvs import load_pairs
from pipeline.runner import (build_jobs, compute_prompt_hash, prompt_record, results_file,
                             run_session, shuffle_jobs)


class PicksCandidate1:
    """Fake client: always prefers Candidate 1, and remembers every request it was sent."""

    def __init__(self):
        self.bodies = []

    def send(self, body):
        self.bodies.append(body)
        answer = {
            "candidate_1": {"shortlist": True, "rating": 8, "reason": "first"},
            "candidate_2": {"shortlist": False, "rating": 3, "reason": "second"},
            "preferred": "1",
        }
        return json.dumps(answer), {"model": body["model"], "usage": {"total_tokens": 10}}


class BrokenClient:
    """Fake client whose model replies with something that isn't JSON."""

    def send(self, body):
        return "Sorry, I can't help with that.", {}


def read_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def key(row):
    return (row["session"], row["model"], row["pair_id"], row["order"], row["rep"])


def test_every_pair_is_planned_in_both_orders_for_every_rep(project):
    pairs, _ = load_pairs(project.cv_dir, project.arms)
    jobs = build_jobs(project.models, pairs, project.reps)
    assert len(jobs) == CALLS_PER_SESSION  # 2 models x 9 pairs x 2 orders x 2 reps
    assert len({j.key("day1") for j in jobs}) == len(jobs)


def test_call_order_is_repeatable_but_differs_between_sessions(project):
    pairs, _ = load_pairs(project.cv_dir, project.arms)
    jobs = build_jobs(project.models, pairs, project.reps)
    day1 = [j.key("") for j in shuffle_jobs(jobs, 1, "day1")]
    assert day1 == [j.key("") for j in shuffle_jobs(jobs, 1, "day1")]
    assert day1 != [j.key("") for j in shuffle_jobs(jobs, 1, "day2")]
    assert sorted(day1) == sorted(j.key("") for j in jobs)  # same calls, new order


def test_answers_are_mapped_back_to_the_right_variant(project):
    run_session(project, "day1", PicksCandidate1(), dry_run=True)
    rows = read_rows(results_file(project.output_dir(True)))
    assert len(rows) == CALLS_PER_SESSION and all(r["ok"] for r in rows)
    for r in rows:
        x, y = project.arms[r["arm"]]
        expected_order = (x, y) if r["order"] == "xy" else (y, x)
        assert (r["pos1_variant"], r["pos2_variant"]) == expected_order
        assert r["preferred_position"] == 1
        assert r["preferred_variant"] == r["pos1_variant"]
        assert (r["pos1_rating"], r["pos2_rating"]) == (8, 3)
    # Always picking Candidate 1 means picking x exactly half the time, thanks to the order swap.
    assert sum(r["preferred_variant"] == project.arms[r["arm"]][0] for r in rows) == CALLS_PER_SESSION / 2


def test_candidate_1_in_the_prompt_is_the_variant_recorded_as_pos1(project):
    client = PicksCandidate1()
    run_session(project, "day1", client, dry_run=True)
    rows = read_rows(results_file(project.output_dir(True)))
    pairs = {p.pair_id: p for p in load_pairs(project.cv_dir, project.arms)[0]}
    for body, row in zip(client.bodies, rows):
        prompt = body["messages"][1]["content"]
        pair = pairs[row["pair_id"]]
        text = {pair.x_variant: pair.x_text, pair.y_variant: pair.y_text}
        assert prompt.index(text[row["pos1_variant"]]) < prompt.index(text[row["pos2_variant"]])
        assert ".txt" not in prompt  # no file names reach the model


def test_every_row_carries_the_prompt_hash_and_the_prompt_is_saved(project):
    run_session(project, "day1", DryRunClient(), dry_run=True, limit=3)
    expected = compute_prompt_hash(prompt_record(project))
    rows = read_rows(results_file(project.output_dir(True)))
    assert [r["prompt_hash"] for r in rows] == [expected] * 3
    saved = project.output_dir(True) / "prompts" / f"{expected}.json"
    assert json.loads(saved.read_text(encoding="utf-8")) == prompt_record(project)


def test_prompt_hash_changes_when_any_part_of_the_prompt_changes(project):
    record = prompt_record(project)
    original = compute_prompt_hash(record)
    assert compute_prompt_hash(dict(record)) == original
    for part in ("system_prompt", "user_prompt_template", "job_description"):
        assert compute_prompt_hash(dict(record, **{part: record[part] + " "})) != original, part
    schema = json.loads(json.dumps(record["response_format"]))
    schema["json_schema"]["name"] = "renamed"
    assert compute_prompt_hash(dict(record, response_format=schema)) != original


def test_moving_text_between_prompt_parts_changes_the_hash(project):
    record = prompt_record(project)
    a = dict(record, system_prompt="AB", job_description="C")
    b = dict(record, system_prompt="A", job_description="BC")
    assert compute_prompt_hash(a) != compute_prompt_hash(b)


def test_resume_skips_calls_that_already_succeeded(project):
    path = results_file(project.output_dir(True))
    assert run_session(project, "day1", DryRunClient(), dry_run=True, limit=5) == 5
    assert run_session(project, "day1", DryRunClient(), dry_run=True) == CALLS_PER_SESSION - 5
    rows = read_rows(path)
    assert len(rows) == CALLS_PER_SESSION
    assert len({key(r) for r in rows}) == CALLS_PER_SESSION  # no call made twice
    assert run_session(project, "day1", DryRunClient(), dry_run=True) == 0  # nothing left to do


def test_failed_calls_are_kept_and_tried_again_on_the_next_run(project):
    path = results_file(project.output_dir(True))
    run_session(project, "day1", BrokenClient(), dry_run=True, limit=4)
    failed = read_rows(path)
    assert [r["ok"] for r in failed] == [False] * 4
    assert all(r["error"].startswith("JSONDecodeError") for r in failed)

    assert run_session(project, "day1", DryRunClient(), dry_run=True, limit=4) == 4
    rows = read_rows(path)
    assert rows[:4] == failed  # the failed rows stay in the file (append-only)
    assert [key(r) for r in rows[4:]] == [key(r) for r in failed]
    assert all(r["ok"] for r in rows[4:])


def test_dry_runs_never_write_to_the_real_results_file(project):
    run_session(project, "day1", DryRunClient(), dry_run=True, limit=3)
    assert not results_file(project.output_dir(False)).exists()
    assert all(r["dry_run"] for r in read_rows(results_file(project.output_dir(True))))


def test_a_dry_run_does_not_make_the_real_run_skip_calls(project):
    """A finished dry run with the same session label must not count as done for the real run."""
    run_session(project, "day1", DryRunClient(), dry_run=True)
    # A fake client stands in for OpenRouter, so this "real" run costs nothing.
    assert run_session(project, "day1", PicksCandidate1(), dry_run=False, limit=3) == 3
    rows = read_rows(results_file(project.output_dir(False)))
    assert len(rows) == 3 and not any(r["dry_run"] for r in rows)

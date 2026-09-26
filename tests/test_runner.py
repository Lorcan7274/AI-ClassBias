import json

import pytest
from conftest import CALLS_PER_SESSION

from pipeline.client import CallResult, DryRunClient
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
        content = json.dumps(answer)
        response = {"id": "gen-fake", "model": body["model"], "usage": {"total_tokens": 10},
                    "choices": [{"finish_reason": "stop", "message": {"content": content}}]}
        return CallResult(content=content, response=response, attempts=1, elapsed=0.1)


class BrokenClient:
    """Fake client whose model replies with something that isn't JSON."""

    def send(self, body):
        content = "Sorry, I can't help with that."
        return CallResult(content=content, response={"choices": [{"message": {"content": content}}]}, attempts=1, elapsed=0.1)


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
    run_session(project, "day1", PicksCandidate1(), dry_run=True, quiet=True)
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
    run_session(project, "day1", client, dry_run=True, workers=1, quiet=True)
    rows = read_rows(results_file(project.output_dir(True)))
    pairs = {p.pair_id: p for p in load_pairs(project.cv_dir, project.arms)[0]}
    assert len(client.bodies) == len(rows)
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
    assert run_session(project, "day1", DryRunClient(), dry_run=True, limit=5, quiet=True).attempted == 5
    assert run_session(project, "day1", DryRunClient(), dry_run=True, quiet=True).attempted == CALLS_PER_SESSION - 5
    rows = read_rows(path)
    assert len(rows) == CALLS_PER_SESSION
    assert len({key(r) for r in rows}) == CALLS_PER_SESSION  # no call made twice
    assert run_session(project, "day1", DryRunClient(), dry_run=True, quiet=True).attempted == 0  # nothing left


def test_failed_calls_are_kept_and_tried_again_on_the_next_run(project):
    path = results_file(project.output_dir(True))
    run_session(project, "day1", BrokenClient(), dry_run=True, limit=4, workers=1, quiet=True)
    failed = read_rows(path)
    assert [r["ok"] for r in failed] == [False] * 4
    assert all(r["error"].startswith("JSONDecodeError") and r["error_type"] == "bad_json" for r in failed)

    assert run_session(project, "day1", DryRunClient(), dry_run=True, limit=4, workers=1, quiet=True).attempted == 4
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
    run_session(project, "day1", DryRunClient(), dry_run=True, quiet=True)
    # A fake client stands in for OpenRouter, so this "real" run costs nothing.
    assert run_session(project, "day1", PicksCandidate1(), dry_run=False, limit=3, quiet=True).attempted == 3
    rows = read_rows(results_file(project.output_dir(False)))
    assert len(rows) == 3 and not any(r["dry_run"] for r in rows)


# ----------------------------- Phase 3: workers, raw files, budget, retries -----------------------------

from pipeline import client as api  # noqa: E402
from pipeline.runner import ResultsWriter, raw_dir, read_results  # noqa: E402


class FlakyClient:
    """Fake client: the given call numbers fail with the given error types."""

    def __init__(self, failures):
        self.failures = dict(failures)  # call number (1-based) -> error_type
        self.calls = 0
        self.lock = __import__("threading").Lock()
        self.inner = DryRunClient()

    def send(self, body):
        with self.lock:
            self.calls += 1
            n = self.calls
        if n in self.failures:
            error_type = self.failures[n]
            raise api.CallError(error_type, f"simulated {error_type}", status=500, fatal=error_type in ("auth", "payment"))
        return self.inner.send(body)


def test_workers_write_every_row_and_raw_file_intact(project):
    stats = run_session(project, "day1", DryRunClient(), dry_run=True, workers=8, quiet=True)
    assert (stats.planned, stats.attempted, stats.ok) == (CALLS_PER_SESSION,) * 3
    rows, bad = read_results(results_file(project.output_dir(True)))
    assert bad == 0 and len(rows) == CALLS_PER_SESSION
    assert len({r["call_id"] for r in rows}) == CALLS_PER_SESSION
    raw_files = sorted(p.name for p in raw_dir(project.output_dir(True)).glob("*.json"))
    assert raw_files == sorted(f"{r['call_id']}.json" for r in rows)
    raw = json.loads((raw_dir(project.output_dir(True)) / raw_files[0]).read_text(encoding="utf-8"))
    assert raw["request"]["response_format"]["type"] == "json_schema"
    assert raw["response"]["choices"][0]["message"]["content"]
    assert set(rows[0]) >= {"call_id", "generation_id", "served_model", "provider", "prompt_tokens",
                            "completion_tokens", "total_tokens", "cost_usd", "attempts", "latency_s"}
    assert abs(stats.cost_usd - CALLS_PER_SESSION * DryRunClient.FAKE_COST_USD) < 1e-9


def test_budget_stops_the_run_early(project):
    stats = run_session(project, "day1", DryRunClient(), dry_run=True, workers=1,
                        budget=10 * DryRunClient.FAKE_COST_USD, quiet=True)
    assert stats.attempted == 11  # the call that passed the budget is the last one
    assert stats.stopped.startswith("stopped: the cost of this run")
    rows, _ = read_results(results_file(project.output_dir(True)))
    assert len(rows) == 11
    # The next run carries on where the budget stop left off.
    assert run_session(project, "day1", DryRunClient(), dry_run=True, quiet=True).attempted == CALLS_PER_SESSION - 11


def test_failed_rows_are_recorded_with_their_error_type_and_raw_file(project):
    client = FlakyClient({2: "rate_limit", 3: "bad_request"})
    stats = run_session(project, "day1", client, dry_run=True, limit=4, workers=1, quiet=True)
    assert stats.failures == {"rate_limit": 1, "bad_request": 1} and stats.ok == 2
    rows, _ = read_results(results_file(project.output_dir(True)))
    failed = [r for r in rows if not r["ok"]]
    assert sorted(r["error_type"] for r in failed) == ["bad_request", "rate_limit"]
    raw = json.loads((raw_dir(project.output_dir(True)) / f"{failed[0]['call_id']}.json").read_text(encoding="utf-8"))
    assert raw["ok"] is False and raw["error_type"] == failed[0]["error_type"]


def test_retry_failed_only_reruns_the_failed_calls(project):
    run_session(project, "day1", FlakyClient({1: "server_error", 4: "timeout"}), dry_run=True, limit=6, workers=1, quiet=True)
    stats = run_session(project, "day1", DryRunClient(), dry_run=True, retry_failed=True, quiet=True)
    assert stats.planned == 2 and stats.ok == 2
    rows, _ = read_results(results_file(project.output_dir(True)))
    assert len(rows) == 8
    retried = [key(r) for r in rows[6:]]
    assert sorted(retried) == sorted(key(r) for r in rows[:6] if not r["ok"])
    # Nothing failed any more, so retry-failed has nothing to do; a normal run does the rest.
    assert run_session(project, "day1", DryRunClient(), dry_run=True, retry_failed=True, quiet=True).planned == 0
    assert run_session(project, "day1", DryRunClient(), dry_run=True, quiet=True).planned == CALLS_PER_SESSION - 6


def test_a_fatal_error_stops_the_run(project):
    stats = run_session(project, "day1", FlakyClient({3: "payment"}), dry_run=True, workers=1, quiet=True)
    assert stats.stopped == "stopped: payment error, every further call would fail too"
    assert stats.attempted == 3


def test_a_session_refuses_a_changed_prompt(project, make_config):
    from pipeline.config import load_config
    run_session(project, "day1", DryRunClient(), dry_run=True, limit=2, quiet=True)
    changed = load_config(make_config({"You are a recruiter.": "You are a strict recruiter."}))
    with pytest.raises(RuntimeError, match="session 'day1' already holds rows made with a different prompt"):
        run_session(changed, "day1", DryRunClient(), dry_run=True, limit=2, quiet=True)
    # A new session label is fine.
    assert run_session(changed, "day2", DryRunClient(), dry_run=True, limit=2, quiet=True).ok == 2


def test_a_half_written_last_line_is_skipped_and_repaired(project, capsys):
    path = results_file(project.output_dir(True))
    run_session(project, "day1", DryRunClient(), dry_run=True, limit=3, quiet=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"session": "day1", "model": "test/open-model", "pair_id": "cv0')  # crash mid-write
    stats = run_session(project, "day1", DryRunClient(), dry_run=True, limit=2, quiet=True)
    assert stats.planned == 2
    assert "1 unreadable line(s)" in capsys.readouterr().out
    rows, bad = read_results(path)
    assert bad == 1 and len(rows) == 5  # the new rows were not glued on to the broken line


def test_results_writer_is_safe_with_many_threads(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    writer = ResultsWriter(tmp_path / "results.jsonl")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda i: writer.write({"i": i, "text": "x" * 500}), range(400)))
    writer.close()
    rows, bad = read_results(tmp_path / "results.jsonl")
    assert bad == 0 and sorted(r["i"] for r in rows) == list(range(400))

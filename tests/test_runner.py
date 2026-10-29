import json

import pytest
from conftest import CALLS_PER_SESSION

from pipeline.client import CallResult, DryRunClient
from pipeline.cvs import load_fillers, load_stimuli
from pipeline.runner import (build_jobs, compute_prompt_hash, prompt_record, results_file,
                             run_session, shuffle_jobs)


class SaysYes:
    """Fake client: shortlists everyone at 80, and remembers every request it was sent."""

    def __init__(self):
        self.bodies = []

    def send(self, body):
        self.bodies.append(body)
        answer = {"shortlist": True, "rank_in_round": 2, "likelihood": 80, "reason": "fine"}
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
    return (row["session"], row["model"], row["cv_id"], row["arm"], row["variant"], row["sample"])


def test_every_cv_is_planned_once_per_sample(project):
    stimuli, _ = load_stimuli(project.cv_dir, project.arms)
    assert len(stimuli) == 18  # 3 base CVs x 3 arms x 2 variants
    jobs = build_jobs(project.models, stimuli, project.samples)
    assert len(jobs) == CALLS_PER_SESSION  # 2 models x 18 CVs x 2 samples
    assert len({j.key("day1") for j in jobs}) == len(jobs)


def test_a_lone_variant_is_not_loaded(project):
    (project.cv_dir / "cv02_explicit_low.txt").unlink()
    stimuli, missing = load_stimuli(project.cv_dir, project.arms)
    assert missing == ["cv02_explicit"]
    assert len(stimuli) == 16 and "cv02_explicit_high" not in {s.stimulus_id for s in stimuli}


def test_call_order_is_repeatable_but_differs_between_sessions(project):
    stimuli, _ = load_stimuli(project.cv_dir, project.arms)
    jobs = build_jobs(project.models, stimuli, project.samples)
    day1 = [j.key("") for j in shuffle_jobs(jobs, 1, "day1")]
    assert day1 == [j.key("") for j in shuffle_jobs(jobs, 1, "day1")]
    assert day1 != [j.key("") for j in shuffle_jobs(jobs, 1, "day2")]
    assert sorted(day1) == sorted(j.key("") for j in jobs)  # same calls, new order


def test_each_row_records_its_cv_and_the_answer(project):
    run_session(project, "day1", SaysYes(), dry_run=True, quiet=True)
    rows = read_rows(results_file(project.output_dir(True)))
    assert len(rows) == CALLS_PER_SESSION and all(r["ok"] for r in rows)
    for r in rows:
        assert r["variant"] in project.arms[r["arm"]]
        assert r["stimulus_id"] == f"{r['cv_id']}_{r['arm']}_{r['variant']}"
        assert (r["shortlist"], r["rank_in_round"], r["likelihood"], r["reason"]) == (True, 2, 80, "fine")
        assert "pair_id" not in r and "order" not in r  # nothing pairwise is left in a row
    # The prefix is byte-identical across calls: that is what the providers cache.
    # (checked in the prompt-structure test through the content parts)
    # Every CV was sent exactly `samples` times to each model.
    from collections import Counter
    counts = Counter((r["model"], r["stimulus_id"]) for r in rows)
    assert set(counts.values()) == {project.samples}


def test_the_prompt_is_the_fixed_fillers_then_the_one_target_cv(project):
    client = SaysYes()
    run_session(project, "day1", client, dry_run=True, workers=1, quiet=True)
    rows = read_rows(results_file(project.output_dir(True)))
    texts = {s.stimulus_id: s.text for s in load_stimuli(project.cv_dir, project.arms)[0]}
    fillers = load_fillers(project.filler_dir)
    assert [name for name, _ in fillers] == ["F1.txt", "F2.txt"]
    assert len(client.bodies) == len(rows)
    for body, row in zip(client.bodies, rows):
        parts = body["messages"][1]["content"]
        # Two content parts: the prefix that never changes, marked for caching, then the CV.
        assert [p["type"] for p in parts] == ["text", "text"]
        assert parts[0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in parts[1]
        prefix, suffix = parts[0]["text"], parts[1]["text"]
        prompt = prefix + suffix
        target = texts[row["stimulus_id"]].rstrip()
        # The same fillers in the same order in the prefix, then the target as the last applicant in the suffix.
        positions = [prefix.index(text.rstrip()) for _, text in fillers]
        assert positions == sorted(positions) and target not in prefix
        assert suffix.startswith("=== APPLICANT 3 ===") and target in suffix
        assert prompt.count("=== APPLICANT") == 3 and "Assess Applicant 3 only." in suffix
        assert (row["n_fillers"], row["target_position"]) == (2, 3)
        assert 1 <= row["rank_in_round"] <= 3 if "rank_in_round" in row else True
        # The schema sent limits the rank to the round.
        assert body["response_format"]["json_schema"]["schema"]["properties"]["rank_in_round"]["maximum"] == 3
        others = [t for sid, t in texts.items() if sid != row["stimulus_id"] and t not in texts[row["stimulus_id"]]]
        assert not any(t in prompt for t in others)  # never a second stimulus CV, never the twin
        assert ".txt" not in prompt  # no file name reaches the model


def test_temperature_is_sent_only_to_models_that_take_it(make_config):
    from pipeline.config import load_config
    from pipeline.cvs import make_dummy_cvs
    cfg = load_config(make_config({"temperature: null": "temperature: 1.0",
                                   "type: frontier": "type: frontier\n    send_temperature: false"}))
    make_dummy_cvs(cfg.cv_dir, cfg.arms, n_cvs=1)
    client = SaysYes()
    run_session(cfg, "day1", client, dry_run=True, workers=1, quiet=True)
    rows = read_rows(results_file(cfg.output_dir(True)))
    by_model = {}
    for body, row in zip(client.bodies, rows):
        by_model.setdefault(row["model"], set()).add((body.get("temperature"), row["temperature"]))
    assert by_model["test/frontier-model"] == {(None, None)}
    assert by_model["test/open-model"] == {(1.0, 1.0)}


def test_every_row_carries_the_prompt_hash_and_the_prompt_is_saved(project):
    run_session(project, "day1", DryRunClient(), dry_run=True, limit=3)
    fillers = load_fillers(project.filler_dir)
    expected = compute_prompt_hash(prompt_record(project, fillers))
    rows = read_rows(results_file(project.output_dir(True)))
    assert [r["prompt_hash"] for r in rows] == [expected] * 3
    saved = project.output_dir(True) / "prompts" / f"{expected}.json"
    assert json.loads(saved.read_text(encoding="utf-8")) == prompt_record(project, fillers)
    assert [f["name"] for f in prompt_record(project, fillers)["fillers"]] == ["F1.txt", "F2.txt"]
    # The schema in the record is the one for this round size.
    assert prompt_record(project, fillers)["response_format"]["json_schema"]["schema"]["properties"]["rank_in_round"]["maximum"] == 3


def test_prompt_hash_changes_when_any_part_of_the_prompt_changes(project):
    fillers = load_fillers(project.filler_dir)
    record = prompt_record(project, fillers)
    original = compute_prompt_hash(record)
    assert compute_prompt_hash(dict(record)) == original
    for part in ("system_prompt", "user_prompt_template", "job_description"):
        assert compute_prompt_hash(dict(record, **{part: record[part] + " "})) != original, part
    schema = json.loads(json.dumps(record["response_format"]))
    schema["json_schema"]["name"] = "renamed"
    assert compute_prompt_hash(dict(record, response_format=schema)) != original
    # A changed filler is a changed prompt: it is in every call.
    changed = [(fillers[0][0], fillers[0][1] + " "), *fillers[1:]]
    assert compute_prompt_hash(prompt_record(project, changed)) != original
    # So is the same text under a different file name, or a different order.
    assert compute_prompt_hash(prompt_record(project, list(reversed(fillers)))) != original


def test_a_run_refuses_to_start_without_fillers(project):
    for path in project.filler_dir.glob("*.txt"):
        path.unlink()
    with pytest.raises(RuntimeError, match="No filler CVs found"):
        run_session(project, "day1", DryRunClient(), dry_run=True, quiet=True)


def test_moving_text_between_prompt_parts_changes_the_hash(project):
    fillers = load_fillers(project.filler_dir)
    record = prompt_record(project, fillers)
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
    assert run_session(project, "day1", SaysYes(), dry_run=False, limit=3, quiet=True).attempted == 3
    rows = read_rows(results_file(project.output_dir(False)))
    assert len(rows) == 3 and not any(r["dry_run"] for r in rows)


# ----------------------------- workers, raw files, budget, retries -----------------------------

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
    assert raw["stimulus_id"] and raw["sample"] >= 1
    assert set(rows[0]) >= {"call_id", "generation_id", "served_model", "provider", "prompt_tokens",
                            "completion_tokens", "total_tokens", "cost_usd", "attempts", "latency_s",
                            "shortlist", "likelihood", "reason"}
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
        f.write('{"session": "day1", "model": "test/open-model", "stimulus_id": "cv0')  # crash mid-write
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

"""Running one session: build the list of calls, skip the ones already done, make the
rest with several workers at once, and append one row per call to the results file."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
import random
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from pipeline import client as api
from pipeline.config import ModelSpec
from pipeline.cvs import Pair, load_pairs

# "xy" shows the x variant as Candidate 1, "yx" shows the y variant first.
# Every pair is sent in both orders so a preference for one position is balanced
# across the two variants.
ORDERS = ("xy", "yx")

# After one of these, every further call would fail the same way, so the run stops.
FATAL_ERROR_TYPES = {"auth", "payment"}


@dataclass
class Job:
    """One planned call: a model, a pair, an order and a repetition number."""
    model: ModelSpec
    pair: Pair
    order: str  # "xy" or "yx"
    rep: int    # 1 .. reps

    def key(self, session):
        """Identifies the call within the results file. Used to skip calls that already succeeded."""
        return (session, self.model.id, self.pair.pair_id, self.order, self.rep)


@dataclass
class RunStats:
    """What happened in one run, for the summary at the end."""
    planned: int = 0
    attempted: int = 0
    ok: int = 0
    failures: Counter = field(default_factory=Counter)  # error_type -> count
    cost_usd: float = 0.0
    total_tokens: int = 0
    stopped: str | None = None  # why the run stopped early, if it did

    def add(self, row):
        self.attempted += 1
        if row["ok"]:
            self.ok += 1
        else:
            self.failures[row["error_type"]] += 1
        self.cost_usd += row.get("cost_usd") or 0.0
        self.total_tokens += row.get("total_tokens") or 0


def results_file(output_dir) -> Path:
    return Path(output_dir) / "results.jsonl"


def raw_dir(output_dir) -> Path:
    return Path(output_dir) / "raw"


# ----------------------------- the prompt hash -----------------------------

def prompt_record(cfg) -> dict:
    """Everything sent with each call apart from the two CVs."""
    return {
        "system_prompt": cfg.system_prompt,
        "user_prompt_template": cfg.user_prompt_template,
        "job_description": cfg.job_description,
        "response_format": api.RESPONSE_FORMAT,
    }


def compute_prompt_hash(record) -> str:
    """SHA-256 of the prompt record. It is saved in every result row, so if the
    prompt changes between sessions it shows up in the data."""
    # Hashing one JSON text keeps the boundaries between the parts clear: moving a
    # sentence from the system prompt into the template still changes the hash.
    # sort_keys gives the same text, and so the same hash, every time.
    text = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_prompt_record(output_dir, record, prompt_hash) -> Path:
    """Keep a copy of the prompt texts under their hash, so any hash in the results
    can be traced back to the exact wording that was sent."""
    path = Path(output_dir) / "prompts" / f"{prompt_hash}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ----------------------------- reading the results file -----------------------------

def read_results(path):
    """All rows in a results file. Returns (rows, number of unreadable lines).

    A crash in the middle of a write can leave a half-written last line; such lines
    are skipped rather than stopping the whole run.
    """
    rows, bad = [], 0
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    bad += 1
    return rows, bad


def row_key(row):
    return (row["session"], row["model"], row["pair_id"], row["order"], row["rep"])


def completed_and_failed_keys(rows):
    """Keys of calls that have succeeded, and keys whose every attempt so far failed."""
    done = {row_key(r) for r in rows if r.get("ok")}
    failed = {row_key(r) for r in rows if not r.get("ok")} - done
    return done, failed


def check_session(rows, session, prompt_hash):
    """Refuse to add rows to a session that was run with a different prompt.

    Two prompts in one session would make its rows impossible to compare, so a
    changed prompt must go under a new session label.
    """
    hashes = {r.get("prompt_hash") for r in rows if r.get("session") == session}
    others = sorted(str(h) for h in hashes if h != prompt_hash)
    if others:
        raise RuntimeError(
            f"session '{session}' already holds rows made with a different prompt "
            f"(prompt_hash {', '.join(h[:12] + '...' for h in others)}; now {prompt_hash[:12]}...). "
            "Use a new session label for the changed prompt, or restore the old prompt.")


# ----------------------------- planning the calls -----------------------------

def build_jobs(models, pairs, reps) -> list[Job]:
    """Every call for one session: each model x pair x order x rep."""
    return [Job(m, p, order, rep)
            for m in models for p in pairs for order in ORDERS for rep in range(1, reps + 1)]


def shuffle_jobs(jobs, seed, session) -> list[Job]:
    """Shuffle the calls so drift during a run can't line up with one model or condition.

    Seeding with seed + session gives the same order every time a session is
    (re)started, and a different order in each session. seed=None gives a new
    random order every time.
    """
    rng = random.Random(f"{seed}:{session}") if seed is not None else random.Random()
    shuffled = list(jobs)
    rng.shuffle(shuffled)
    return shuffled


# ----------------------------- making the calls -----------------------------

def fill_prompt(cfg, first_text, second_text) -> str:
    """The user prompt for one call. The model only ever sees "Candidate 1" and
    "Candidate 2": no file names or variant labels."""
    return cfg.user_prompt_template.format(job=cfg.job_description, cv1=first_text, cv2=second_text)


class ResultsWriter:
    """Appends rows to results.jsonl. One lock makes it safe with several workers."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Append only: rows already in the file are never changed or removed. If a
        # crash left a half-written last line without a newline, finish that line
        # first so the next row can't be glued on to it.
        self.file = self.path.open("a+", encoding="utf-8")
        self.file.seek(0, 2)
        if self.file.tell() > 0:
            self.file.seek(self.file.tell() - 1)
            if self.file.read(1) != "\n":
                self.file.write("\n")

    def write(self, row):
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with self.lock:
            self.file.write(line)
            self.file.flush()

    def close(self):
        self.file.close()


def run_one(cfg, session, job, client, prompt_hash, dry_run, out_dir) -> dict:
    """Make one call, save the full response under results/raw/, and return the row.
    A failed call gives ok=False plus error_type and error."""
    if job.order == "xy":
        first_variant, first_text = job.pair.x_variant, job.pair.x_text
        second_variant, second_text = job.pair.y_variant, job.pair.y_text
    else:
        first_variant, first_text = job.pair.y_variant, job.pair.y_text
        second_variant, second_text = job.pair.x_variant, job.pair.x_text

    call_id = uuid.uuid4().hex
    row = {
        "call_id": call_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session": session,
        "model": job.model.id,
        "model_type": job.model.type,
        "pair_id": job.pair.pair_id,
        "cv_id": job.pair.cv_id,
        "arm": job.pair.arm,
        "order": job.order,
        "rep": job.rep,
        "pos1_variant": first_variant,
        "pos2_variant": second_variant,
        "temperature": cfg.temperature,
        "prompt_hash": prompt_hash,
        "dry_run": dry_run,
    }
    body = api.build_request_body(job.model.id, cfg.system_prompt,
                                  fill_prompt(cfg, first_text, second_text), cfg.temperature)
    raw = {"call_id": call_id, "session": session, "pair_id": job.pair.pair_id, "order": job.order,
           "rep": job.rep, "prompt_hash": prompt_hash, "dry_run": dry_run, "request": body}
    try:
        result = client.send(body)
    except api.CallError as e:
        row.update({"ok": False, "error_type": e.error_type, "error": e.message,
                    "http_status": e.status, "attempts": e.attempts})
        raw.update({"ok": False, "error_type": e.error_type, "error": e.message, "http_status": e.status,
                    "attempts": e.attempts, "retries": e.notes, "response": e.response})
        save_raw(out_dir, call_id, raw)
        return row

    row.update(api.extract_details(result.response))
    row.update({"attempts": result.attempts, "latency_s": round(result.elapsed, 3)})
    raw.update({"attempts": result.attempts, "retries": result.notes, "latency_s": round(result.elapsed, 3),
                "response": result.response})
    try:
        answer = api.parse_answer(result.content)
        api.check_answer(answer)
    except (ValueError, TypeError) as e:  # json.JSONDecodeError is a ValueError
        error_type = "bad_json" if isinstance(e, json.JSONDecodeError) else "bad_answer"
        row.update({"ok": False, "error_type": error_type, "error": f"{type(e).__name__}: {e}"[:300]})
        raw.update({"ok": False, "error_type": error_type, "error": row["error"]})
        save_raw(out_dir, call_id, raw)
        return row

    row.update({
        "ok": True,
        "preferred_position": int(answer["preferred"]),
        # Map "Candidate 1/2" back to the variant that was shown in that position.
        "preferred_variant": first_variant if answer["preferred"] == "1" else second_variant,
        "pos1_shortlist": answer["candidate_1"]["shortlist"],
        "pos1_rating": answer["candidate_1"]["rating"],
        "pos1_reason": answer["candidate_1"]["reason"],
        "pos2_shortlist": answer["candidate_2"]["shortlist"],
        "pos2_rating": answer["candidate_2"]["rating"],
        "pos2_reason": answer["candidate_2"]["reason"],
    })
    raw["ok"] = True
    save_raw(out_dir, call_id, raw)
    return row


def save_raw(out_dir, call_id, raw):
    """The full request and response of one call, in its own file."""
    path = raw_dir(out_dir) / f"{call_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def run_session(cfg, session, client, dry_run=False, limit=None, workers=None, budget=None,
                retry_failed=False, quiet=False) -> RunStats:
    """Make every call for this session that hasn't succeeded yet.

    `client` is an OpenRouterClient for real runs or a DryRunClient for dry runs.
    Real rows go to results/results.jsonl, dry-run rows to results/dry_run/results.jsonl.
    With retry_failed=True only calls whose attempts so far all failed are made.
    The run stops early when the cost of this run passes `budget` (USD), after a
    fatal error (bad key, no credits), or on Ctrl-C; in-flight calls still finish
    and their rows are saved.
    """
    pairs, missing = load_pairs(cfg.cv_dir, cfg.arms)
    if missing:
        print(f"WARNING: incomplete pairs skipped: {missing}")
    if not pairs:
        raise RuntimeError(f"No complete CV pairs found in {cfg.cv_dir}")

    out_dir = cfg.output_dir(dry_run)
    out_file = results_file(out_dir)
    record = prompt_record(cfg)
    prompt_hash = compute_prompt_hash(record)

    rows, bad_lines = read_results(out_file)
    if bad_lines:
        print(f"WARNING: {bad_lines} unreadable line(s) in {out_file} were skipped "
              "(probably a call interrupted while it was being written).")
    check_session(rows, session, prompt_hash)
    done, failed = completed_and_failed_keys(rows)

    jobs = shuffle_jobs(build_jobs(cfg.models, pairs, cfg.reps), cfg.shuffle_seed, session)
    if retry_failed:
        todo = [j for j in jobs if j.key(session) in failed]
        note = f"{len(todo)} failed calls to retry"
    else:
        todo = [j for j in jobs if j.key(session) not in done]
        note = f"{len(jobs) - len(todo)} already done, {len(todo)} to do now"
    if limit is not None:
        todo = todo[:limit]
        note += f", limited to {len(todo)}"
    workers = workers or cfg.workers
    print(f"{len(pairs)} pairs, {len(jobs)} calls in session '{session}': {note}.")
    print(f"Writing to {out_file} (prompt_hash {prompt_hash[:12]}..., {workers} worker(s)"
          f"{'' if budget is None else f', budget ${budget:g}'})")

    stats = RunStats(planned=len(todo))
    out_dir.mkdir(parents=True, exist_ok=True)
    save_prompt_record(out_dir, record, prompt_hash)
    writer = ResultsWriter(out_file)

    def work(job):
        row = run_one(cfg, session, job, client, prompt_hash, dry_run, out_dir)
        writer.write(row)  # written by the worker, so an interrupted run keeps finished calls
        return row

    remaining = iter(todo)
    pending = set()
    pool = ThreadPoolExecutor(max_workers=workers)
    bar = tqdm(total=len(todo), unit="call", disable=quiet, dynamic_ncols=True)

    def submit_more():
        while len(pending) < workers and stats.stopped is None:
            job = next(remaining, None)
            if job is None:
                return
            pending.add(pool.submit(work, job))

    try:
        submit_more()
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                pending.discard(future)
                row = future.result()
                stats.add(row)
                bar.update(1)
                bar.set_postfix_str(f"ok {stats.ok}, failed {sum(stats.failures.values())}, "
                                    f"${stats.cost_usd:.4f}")
                if not row["ok"]:
                    tqdm.write(f"  FAILED {row['model']} {row['pair_id']} {row['order']} r{row['rep']}: "
                               f"{row['error_type']}: {row['error'][:120]}")
                    if row["error_type"] in FATAL_ERROR_TYPES and stats.stopped is None:
                        stats.stopped = f"stopped: {row['error_type']} error, every further call would fail too"
                # The tiny allowance stops floating-point rounding (e.g. 20 x 0.0005 = 0.010000000000000002)
                # from tripping the budget on the exact amount.
                if budget is not None and stats.cost_usd > budget + 1e-9 and stats.stopped is None:
                    stats.stopped = f"stopped: the cost of this run (${stats.cost_usd:.4f}) passed the budget of ${budget:g}"
            submit_more()
    except KeyboardInterrupt:
        stats.stopped = "stopped by Ctrl-C; calls already in flight were allowed to finish"
        for future in pending:
            future.cancel()
        pool.shutdown(wait=True)
        for future in pending:
            if future.done() and not future.cancelled():
                stats.add(future.result())
    finally:
        pool.shutdown(wait=True)
        bar.close()
        writer.close()

    print_summary(stats, dry_run)
    return stats


def print_summary(stats, dry_run):
    lines = [f"Calls made: {stats.attempted} of {stats.planned} planned; {stats.ok} ok, "
             f"{sum(stats.failures.values())} failed."]
    for error_type, n in stats.failures.most_common():
        lines.append(f"  {n} x {error_type}")
    lines.append(f"Tokens: {stats.total_tokens}. Cost of this run: ${stats.cost_usd:.4f}"
                 + (" (fake numbers: dry run)" if dry_run else ""))
    if stats.stopped:
        lines.append(stats.stopped[0].upper() + stats.stopped[1:])
    print("\n".join(lines))

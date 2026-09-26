"""Running one session: build the list of calls, skip the ones already done,
call the model for the rest, and append one row per call to the results file."""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pipeline import client as api
from pipeline.config import ModelSpec
from pipeline.cvs import Pair, load_pairs

# "xy" shows the x variant as Candidate 1, "yx" shows the y variant first.
# Every pair is sent in both orders so a preference for one position is balanced
# across the two variants.
ORDERS = ("xy", "yx")


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


def results_file(output_dir) -> Path:
    return Path(output_dir) / "results.jsonl"


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


def completed_keys(path) -> set:
    """Keys of calls that already succeeded, so an interrupted session can be resumed.
    Failed calls are not included, so they are tried again on the next run."""
    keys = set()
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("ok"):
                    keys.add((row["session"], row["model"], row["pair_id"], row["order"], row["rep"]))
    return keys


# ----------------------------- making the calls -----------------------------

def fill_prompt(cfg, first_text, second_text) -> str:
    """The user prompt for one call. The model only ever sees "Candidate 1" and
    "Candidate 2": no file names or variant labels."""
    return cfg.user_prompt_template.format(job=cfg.job_description, cv1=first_text, cv2=second_text)


def run_one(cfg, session, job, client, prompt_hash, dry_run) -> dict:
    """Make one call and return the row to save. A failed call gives ok=False plus the error."""
    if job.order == "xy":
        first_variant, first_text = job.pair.x_variant, job.pair.x_text
        second_variant, second_text = job.pair.y_variant, job.pair.y_text
    else:
        first_variant, first_text = job.pair.y_variant, job.pair.y_text
        second_variant, second_text = job.pair.x_variant, job.pair.x_text

    row = {
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
    try:
        content, raw = client.send(body)
        answer = api.parse_answer(content)
        api.check_answer(answer)
    except Exception as e:  # any failure is saved in the row, and the call is retried next run
        row.update({"ok": False, "error": f"{type(e).__name__}: {e}"})
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
        "served_model": raw.get("model"),
        "usage": raw.get("usage"),
    })
    return row


def run_session(cfg, session, client, dry_run=False, limit=None) -> int:
    """Make every call for this session that hasn't succeeded yet. Returns the number of calls made.

    `client` is an OpenRouterClient for real runs or a DryRunClient for dry runs.
    Real rows go to results/results.jsonl, dry-run rows to results/dry_run/results.jsonl.
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

    jobs = shuffle_jobs(build_jobs(cfg.models, pairs, cfg.reps), cfg.shuffle_seed, session)
    done = completed_keys(out_file)
    todo = [j for j in jobs if j.key(session) not in done]
    n_done = len(jobs) - len(todo)
    if limit is not None:
        todo = todo[:limit]
    print(f"{len(pairs)} pairs, {len(jobs)} calls in session '{session}': "
          f"{n_done} already done, {len(todo)} to do now.")
    print(f"Writing to {out_file} (prompt_hash {prompt_hash[:12]}...)")

    out_dir.mkdir(parents=True, exist_ok=True)
    save_prompt_record(out_dir, record, prompt_hash)
    # Append only: rows already in the file are never changed or removed.
    with out_file.open("a", encoding="utf-8") as f:
        for i, job in enumerate(todo, 1):
            row = run_one(cfg, session, job, client, prompt_hash, dry_run)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            status = row["preferred_variant"] if row["ok"] else "ERROR " + row["error"][:80]
            print(f"[{i}/{len(todo)}] {job.model.id} {job.pair.pair_id} {job.order} r{job.rep} -> {status}")
            if not dry_run and cfg.sleep_between_calls:
                time.sleep(cfg.sleep_between_calls)
    return len(todo)

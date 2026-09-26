"""Checks to run before a real (paid) session. Nothing here calls the API."""

from __future__ import annotations

from pipeline.cvs import load_pairs, placeholder_pairs
from pipeline.runner import ORDERS, compute_prompt_hash, prompt_record
from pipeline.validation import validate_cvs


def run_preflight(cfg, api_key) -> bool:
    """Print what a real run would do and anything that would stop it. Returns True if all is well."""
    problems = list(cfg.placeholder_problems())

    print(f"Config: {cfg.path}")
    print("Models:")
    for m in cfg.models:
        print(f"  {m.id}  ({m.type})")

    # Only say whether the key exists: never print it.
    print(f"OPENROUTER_API_KEY: {'found' if api_key else 'NOT FOUND'}")
    if not api_key:
        problems.append("OPENROUTER_API_KEY is not set (copy .env.example to .env and add your key)")

    pairs, missing = load_pairs(cfg.cv_dir, cfg.arms)
    print(f"CV pairs in {cfg.cv_dir}: {len(pairs)} complete, {len(missing)} incomplete")
    if not pairs:
        problems.append(f"no complete CV pairs in {cfg.cv_dir}")
    if missing:
        problems.append(f"incomplete pairs: {', '.join(missing)} (run validate-cvs)")
    dummies = placeholder_pairs(pairs)
    if dummies:
        problems.append(f"{len(dummies)} CV pair(s) contain the word PLACEHOLDER, e.g. {dummies[0]}: "
                        "these look like dummy CVs")

    check = validate_cvs(cfg)
    print(f"CV check: {len(check.errors)} error(s), {len(check.warnings)} warning(s) (details: validate-cvs)")
    if check.errors:
        problems.append(f"the CV check found {len(check.errors)} error(s): run validate-cvs")

    n_calls = len(cfg.models) * len(pairs) * len(ORDERS) * cfg.reps
    print(f"Calls per session: {n_calls} = {len(cfg.models)} models x {len(pairs)} pairs "
          f"x {len(ORDERS)} orders x {cfg.reps} reps")
    print(f"Temperature: {'model default (not sent)' if cfg.temperature is None else cfg.temperature}")
    print(f"prompt_hash: {compute_prompt_hash(prompt_record(cfg))}")
    print("Note: the models are not yet checked against the OpenRouter models API.")

    if problems:
        print("\nA real run would not start yet:")
        for p in problems:
            print(f"  - {p}")
        return False
    print("\nAll local checks passed.")
    return True

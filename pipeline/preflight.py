"""Checks to run before a real (paid) session:  python -m pipeline preflight

Local checks (config, key, CVs) come first. Then, with a key, three free OpenRouter
endpoints: the key's credit limit, the models list (does each model exist and
support structured outputs?) and each model's providers. Only with --allow-paid is
one small test call made per model.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import client as api
from pipeline.cvs import load_pairs, placeholder_pairs
from pipeline.runner import ORDERS, compute_prompt_hash, fill_prompt, prompt_record
from pipeline.validation import validate_cvs

# Structured outputs guide: support "is determined per endpoint, not just per model",
# and the models list marks it with "structured_outputs" in supported_parameters.
STRUCTURED = "structured_outputs"

# A very rough token estimate for the cost preview: about 4 characters per token.
CHARS_PER_TOKEN = 4
ESTIMATED_ANSWER_TOKENS = 150

# Two tiny CVs for the --allow-paid test call, to keep it as cheap as possible.
TEST_CV_1 = "A. Smith\nEducation: BSc Economics, 2:1\nExperience: finance internship, 2024\n"
TEST_CV_2 = "B. Jones\nEducation: BSc Economics, 2:1\nExperience: audit internship, 2024\n"


def run_preflight(cfg, api_key, allow_paid=False) -> bool:
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
    print(f"Workers: {cfg.workers}, rate limit: {cfg.calls_per_minute:g} calls/minute, "
          f"retries: {cfg.max_retries}, timeout: {cfg.request_timeout:g}s")
    print(f"prompt_hash: {compute_prompt_hash(prompt_record(cfg))}")

    if api_key:
        problems += check_key(api_key)
        problems += check_models(cfg, api_key, pairs, n_calls // max(len(cfg.models), 1))
        if allow_paid:
            if problems:
                print("\nSkipping the paid test calls because of the problems below.")
            else:
                problems += test_calls(cfg, api_key)
        else:
            print("\nNo paid test call was made (add --allow-paid to make one tiny call per model).")

    if problems:
        print("\nA real run would not start yet:")
        for p in problems:
            print(f"  - {p}")
        return False
    print("\nAll checks passed.")
    return True


def check_key(api_key) -> list[str]:
    """Credit limit and usage of the key, from GET /api/v1/key (all amounts in USD)."""
    print("\nAPI key (GET /api/v1/key):")
    try:
        info = api.key_info(api_key)
    except api.CallError as e:
        print(f"  could not read the key: {e.message}")
        return [f"the API key was not accepted: {e.message}"]
    limit, remaining = info.get("limit"), info.get("limit_remaining")
    # The key's label is not printed: OpenRouter labels keys with a masked copy of the key.
    print(f"  spending limit: {'none' if limit is None else f'${limit:g}'}; "
          f"remaining: {'unlimited' if remaining is None else f'${remaining:g}'}")
    print(f"  used so far: ${info.get('usage', 0):g} in total, ${info.get('usage_daily', 0):g} today")
    if remaining is not None and remaining <= 0:
        return ["the key's spending limit is used up"]
    return []


def check_models(cfg, api_key, pairs, calls_per_model) -> list[str]:
    """Does each configured model exist and support structured outputs, and what would it cost?"""
    print("\nModels (GET /api/v1/models):")
    try:
        by_id = {m["id"]: m for m in api.list_models(api_key)}
    except api.CallError as e:
        print(f"  could not read the models list: {e.message}")
        return [f"could not read the models list: {e.message}"]
    problems = []
    longest = max((len(fill_prompt(cfg, p.x_text, p.y_text)) + len(cfg.system_prompt) for p in pairs), default=0)
    prompt_tokens = longest // CHARS_PER_TOKEN
    estimate_total = 0.0
    for spec in cfg.models:
        model = by_id.get(spec.id)
        print(f"  {spec.id}:")
        if model is None:
            print("    NOT FOUND in the models list")
            problems.append(f"model '{spec.id}' is not in the OpenRouter models list (check the slug)")
            continue
        params = model.get("supported_parameters") or []
        print(f"    name: {model.get('name')}; context length: {model.get('context_length')}")
        print(f"    structured_outputs: {'yes' if STRUCTURED in params else 'NO'}; "
              f"response_format: {'yes' if 'response_format' in params else 'no'}; "
              f"temperature: {'yes' if 'temperature' in params else 'no'}")
        if STRUCTURED not in params:
            problems.append(f"model '{spec.id}' does not list structured_outputs in supported_parameters")
        if cfg.temperature is not None and "temperature" not in params:
            problems.append(f"model '{spec.id}' does not list temperature in supported_parameters, "
                            "but config.yaml sets one (require_parameters would leave it no provider)")
        pricing = model.get("pricing") or {}
        try:  # prices are strings in USD per token (models list docs)
            prompt_price, completion_price = float(pricing.get("prompt", 0)), float(pricing.get("completion", 0))
        except (TypeError, ValueError):
            prompt_price = completion_price = 0.0
        per_call = prompt_tokens * prompt_price + ESTIMATED_ANSWER_TOKENS * completion_price
        estimate_total += per_call * calls_per_model
        print(f"    price: ${prompt_price * 1e6:.3f} per M prompt tokens, ${completion_price * 1e6:.3f} per M "
              f"completion tokens; rough cost per session: ${per_call * calls_per_model:.2f} "
              f"({calls_per_model} calls x ~{prompt_tokens} prompt + {ESTIMATED_ANSWER_TOKENS} answer tokens)")
        print_endpoints(model, api_key)
    print(f"  Rough cost for one whole session: ${estimate_total:.2f} (a guess from character counts; "
          "the real cost is recorded per call)")
    return problems


def print_endpoints(model, api_key):
    """Which providers serve the model, and which of them support structured outputs."""
    details = (model.get("links") or {}).get("details")
    if not details:
        print("    providers: no endpoints link in the models list")
        return
    try:
        endpoints = api.model_endpoints(details, api_key).get("endpoints") or []
    except api.CallError as e:
        print(f"    providers: could not be read ({e.message})")
        return
    if not endpoints:
        print("    providers: none listed")
    for ep in endpoints:
        params = ep.get("supported_parameters") or []
        print(f"    provider {ep.get('provider_name')}: structured_outputs "
              f"{'yes' if STRUCTURED in params else 'NO'}; status {ep.get('status')}; "
              f"uptime last day {ep.get('uptime_last_1d')}")


def test_calls(cfg, api_key) -> list[str]:
    """One tiny paid call per model, with the real system prompt, template and answer
    schema. Checks the answer parses and shows the cost and provider recorded."""
    print("\nTest calls (--allow-paid: one small call per model):")
    client = api.OpenRouterClient(api_key, timeout=cfg.request_timeout, max_retries=cfg.max_retries,
                                  calls_per_minute=cfg.calls_per_minute)
    out_dir = Path(cfg.results_dir) / "preflight"
    out_dir.mkdir(parents=True, exist_ok=True)
    problems = []
    for spec in cfg.models:
        body = api.build_request_body(spec.id, cfg.system_prompt, fill_prompt(cfg, TEST_CV_1, TEST_CV_2),
                                      cfg.temperature)
        raw_path = out_dir / (spec.id.replace("/", "__") + ".json")
        try:
            result = client.send(body)
        except api.CallError as e:
            print(f"  {spec.id}: FAILED ({e.error_type}: {e.message})")
            raw_path.write_text(json.dumps({"request": body, "error": e.message, "response": e.response},
                                           indent=1) + "\n", encoding="utf-8")
            problems.append(f"the test call to '{spec.id}' failed: {e.error_type}: {e.message[:120]}")
            continue
        raw_path.write_text(json.dumps({"request": body, "response": result.response}, indent=1,
                                       ensure_ascii=False) + "\n", encoding="utf-8")
        details = api.extract_details(result.response)
        try:
            api.check_answer(api.parse_answer(result.content))
            answer_note = "answer parsed and valid"
        except (ValueError, TypeError) as e:
            answer_note = f"ANSWER INVALID: {e}"
            problems.append(f"the test call to '{spec.id}' returned an unusable answer: {e}")
        print(f"  {spec.id}: {answer_note}; served by {details['provider']} as {details['served_model']}; "
              f"{details['prompt_tokens']} + {details['completion_tokens']} tokens; "
              f"cost ${details['cost_usd']}; finish_reason {details['finish_reason']}")
        cross_check_cost(api_key, details)
    return problems


def cross_check_cost(api_key, details):
    """Compare the cost in the response with GET /api/v1/generation, which reports
    total_cost and provider_name for the same call."""
    try:
        stats = api.generation_stats(api_key, details["generation_id"])
    except api.CallError as e:
        print(f"    generation stats: not available ({e.message[:100]})")
        return
    print(f"    generation stats: total_cost ${stats.get('total_cost')}, provider {stats.get('provider_name')}, "
          f"tokens {stats.get('tokens_prompt')} + {stats.get('tokens_completion')}")

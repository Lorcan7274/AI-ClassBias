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
from pipeline.cvs import load_fillers, load_stimuli, placeholder_stimuli
from pipeline.runner import compute_prompt_hash, fill_prompt, prompt_record, split_prompt, target_label
from pipeline.validation import validate_cvs

# Structured outputs guide: support "is determined per endpoint, not just per model",
# and the models list marks it with "structured_outputs" in supported_parameters.
STRUCTURED = "structured_outputs"

# A rough token estimate for the cost preview. Measured on a real call: an Anthropic
# model tokenised the round-of-ten prompt at about 2.6 characters per token (4,863
# tokens for ~12,500 characters); Gemini and Llama tokenisers are sparser (3.9 and
# 4.3), so for them this errs on the high side, which is the right side for a cost
# preview and for the Anthropic cache-minimum check.
CHARS_PER_TOKEN = 2.6
ESTIMATED_ANSWER_TOKENS = 200

# Anthropic will not cache a prefix shorter than this on its larger models (prompt
# caching guide: 512 to 4,096 tokens depending on the model). The round has to clear it.
ANTHROPIC_CACHE_MINIMUM = 4096

# A tiny CV for the --allow-paid test call, to keep it as cheap as possible.
TEST_CV = "A. Smith\nEducation: BSc Economics, 2:1\nExperience: finance internship, 2024\n"


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

    stimuli, missing = load_stimuli(cfg.cv_dir, cfg.arms)
    n_cvs = len({s.cv_id for s in stimuli})
    print(f"CVs in {cfg.cv_dir}: {len(stimuli)} files from {n_cvs} base CVs; {len(missing)} incomplete pair(s)")
    if not stimuli:
        problems.append(f"no complete CV pairs in {cfg.cv_dir}")
    if missing:
        problems.append(f"incomplete pairs: {', '.join(missing)} (run validate-cvs)")
    dummies = placeholder_stimuli(stimuli)
    if dummies:
        problems.append(f"{len(dummies)} CV(s) contain the word PLACEHOLDER, e.g. {dummies[0]}: "
                        "these look like dummy CVs")
    fillers = load_fillers(cfg.filler_dir)
    print(f"Fillers in {cfg.filler_dir}: {len(fillers)}"
          + (f" ({', '.join(name for name, _ in fillers)}); the target is always {target_label(fillers)}"
             if fillers else ""))
    if not fillers:
        problems.append(f"no filler CVs in {cfg.filler_dir} (paths.filler_dir)")
    check = validate_cvs(cfg)
    print(f"CV check: {len(check.errors)} error(s), {len(check.warnings)} warning(s) (details: validate-cvs)")
    if check.errors:
        problems.append(f"the CV check found {len(check.errors)} error(s): run validate-cvs")

    n_calls = len(cfg.models) * len(stimuli) * cfg.samples
    print(f"Calls per session: {n_calls} = {len(cfg.models)} models x {len(stimuli)} CVs x {cfg.samples} samples")
    not_sent = [m.id for m in cfg.models if not m.send_temperature]
    if cfg.temperature is None:
        print("Temperature: model default (not sent)")
    else:
        print(f"Temperature: {cfg.temperature:g}"
              + (f"; not sent to {', '.join(not_sent)} (send_temperature: false)" if not_sent else ""))
    print(f"Workers: {cfg.workers}, rate limit: {cfg.calls_per_minute:g} calls/minute, "
          f"retries: {cfg.max_retries}, timeout: {cfg.request_timeout:g}s")
    print(f"prompt_hash: {compute_prompt_hash(prompt_record(cfg, fillers))}")

    if api_key:
        problems += check_key(api_key)
        problems += check_models(cfg, api_key, stimuli, fillers, n_calls // max(len(cfg.models), 1))
        if allow_paid:
            if problems:
                print("\nSkipping the paid test calls because of the problems below.")
            else:
                problems += test_calls(cfg, api_key, fillers)
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


def check_models(cfg, api_key, stimuli, fillers, calls_per_model) -> list[str]:
    """Does each configured model exist and support structured outputs, and what would it cost?"""
    print("\nModels (GET /api/v1/models):")
    try:
        by_id = {m["id"]: m for m in api.list_models(api_key)}
    except api.CallError as e:
        print(f"  could not read the models list: {e.message}")
        return [f"could not read the models list: {e.message}"]
    problems = []
    # The prefix (system prompt, job description, fillers) is identical in every call,
    # the suffix (the CV) is not; the cost preview is given with and without caching.
    prefix_chars = len(cfg.system_prompt) + (len(split_prompt(cfg, stimuli[0].text, fillers)[0]) if stimuli else 0)
    suffix_chars = max((len(split_prompt(cfg, s.text, fillers)[1]) for s in stimuli), default=0)
    prefix_tokens, suffix_tokens = int(prefix_chars / CHARS_PER_TOKEN), int(suffix_chars / CHARS_PER_TOKEN)
    prompt_tokens = prefix_tokens + suffix_tokens
    print(f"  Prompt: ~{prefix_tokens} tokens of cacheable prefix + ~{suffix_tokens} for the CV"
          + (f" (below Anthropic's {ANTHROPIC_CACHE_MINIMUM}-token minimum: Anthropic models would not cache)"
             if prefix_tokens < ANTHROPIC_CACHE_MINIMUM else ""))
    estimate_total = 0.0
    estimate_cached = 0.0
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
              f"temperature: {'yes' if 'temperature' in params else 'no'}"
              + ("" if spec.send_temperature else " (not sent to this model: send_temperature is false)"))
        if STRUCTURED not in params:
            problems.append(f"model '{spec.id}' does not list structured_outputs in supported_parameters")
        if cfg.temperature is not None and spec.send_temperature and "temperature" not in params:
            problems.append(f"model '{spec.id}' does not list temperature in supported_parameters, "
                            "but config.yaml sets one (require_parameters would leave it no provider); "
                            "give the model send_temperature: false")
        pricing = model.get("pricing") or {}
        prompt_price, completion_price = _price(pricing, "prompt"), _price(pricing, "completion")
        read_price, write_price = _price(pricing, "input_cache_read"), _price(pricing, "input_cache_write")
        per_call = prompt_tokens * prompt_price + ESTIMATED_ANSWER_TOKENS * completion_price
        estimate_total += per_call * calls_per_model
        if read_price is None:
            per_session_cached = per_call * calls_per_model
            cache_note = "no cache price listed, so no saving assumed"
        else:
            # First call writes the prefix (at the write price, or the input price where
            # none is listed); every later call reads it.
            first = prefix_tokens * (write_price if write_price is not None else prompt_price) \
                + suffix_tokens * prompt_price + ESTIMATED_ANSWER_TOKENS * completion_price
            later = prefix_tokens * read_price + suffix_tokens * prompt_price + ESTIMATED_ANSWER_TOKENS * completion_price
            per_session_cached = first + later * max(calls_per_model - 1, 0)
            cache_note = (f"cache read ${read_price * 1e6:.3f} per M"
                          + (f", write ${write_price * 1e6:.3f} per M" if write_price is not None else ""))
        estimate_cached += per_session_cached
        print(f"    price: ${prompt_price * 1e6:.3f} per M prompt tokens, ${completion_price * 1e6:.3f} per M "
              f"completion tokens; {cache_note}")
        print(f"    rough cost per session: ${per_call * calls_per_model:.2f} without caching, "
              f"${per_session_cached:.2f} with ({calls_per_model} calls x ~{prompt_tokens} prompt + "
              f"{ESTIMATED_ANSWER_TOKENS} answer tokens)")
        print_endpoints(model, api_key)
    print(f"  Rough cost for one whole session: ${estimate_total:.2f} without caching, ${estimate_cached:.2f} with "
          "(a guess from character counts; the real cost is recorded per call)")
    return problems


def _price(pricing, key):
    """A price from the models list, USD per token, or None if not listed."""
    value = pricing.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def test_calls(cfg, api_key, fillers) -> list[str]:
    """Two small paid calls per model, with the real system prompt, template, fillers
    and answer schema. The first writes the prefix to the provider's cache; the second
    should read it, which the cached_tokens figure shows. Checks the answer parses."""
    print("\nTest calls (--allow-paid: two small calls per model, so the second can hit the cache):")
    client = api.OpenRouterClient(api_key, timeout=cfg.request_timeout, max_retries=cfg.max_retries,
                                  calls_per_minute=cfg.calls_per_minute)
    out_dir = Path(cfg.results_dir) / "preflight"
    out_dir.mkdir(parents=True, exist_ok=True)
    problems = []
    n_applicants = len(fillers) + 1
    for spec in cfg.models:
        temperature = cfg.temperature if spec.send_temperature else None
        body = api.build_request_body(spec.id, cfg.system_prompt, split_prompt(cfg, TEST_CV, fillers), temperature,
                                      response_format=api.response_format(n_applicants))
        for attempt in (1, 2):
            raw_path = out_dir / (spec.id.replace("/", "__") + f".{attempt}.json")
            try:
                result = client.send(body)
            except api.CallError as e:
                print(f"  {spec.id} call {attempt}: FAILED ({e.error_type}: {e.message})")
                raw_path.write_text(json.dumps({"request": body, "error": e.message, "response": e.response},
                                               indent=1) + "\n", encoding="utf-8")
                problems.append(f"the test call to '{spec.id}' failed: {e.error_type}: {e.message[:120]}")
                break
            raw_path.write_text(json.dumps({"request": body, "response": result.response}, indent=1,
                                           ensure_ascii=False) + "\n", encoding="utf-8")
            details = api.extract_details(result.response)
            try:
                api.check_answer(api.parse_answer(result.content), n_applicants)
            except (ValueError, TypeError) as e:
                print(f"  {spec.id} call {attempt}: answered, but the answer is unusable ({e})")
                problems.append(f"'{spec.id}' gave an unusable answer in the test call: {e}")
                break
            print(f"  {spec.id} call {attempt}: ok; provider {details['provider']}; "
                  f"{details['prompt_tokens']} prompt tokens, cached {details['cached_tokens']}, "
                  f"cache write {details['cache_write_tokens']}; cost ${details['cost_usd']}")
            if attempt == 2 and not details["cached_tokens"]:
                print(f"    note: the second call read nothing from the cache on this route")
    return problems

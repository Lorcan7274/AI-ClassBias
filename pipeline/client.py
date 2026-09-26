"""Talking to OpenRouter: one chat completion per CV pair, plus the free
information endpoints that preflight uses.

OpenRouter docs this code relies on (checked 2026-09-26):
- Chat completions request and response fields:
  https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion
- Structured outputs (response_format with a JSON schema):
  https://openrouter.ai/docs/guides/features/structured-outputs
- Provider routing (provider.require_parameters):
  https://openrouter.ai/docs/guides/routing/provider-selection
- Router metadata (the X-OpenRouter-Metadata header, which provider served the call):
  https://openrouter.ai/docs/guides/features/router-metadata
- Usage accounting (usage.cost and the token counts):
  https://openrouter.ai/docs/cookbook/administration/usage-accounting
- Errors, error bodies inside a 200, and the Retry-After header:
  https://openrouter.ai/docs/api_reference/errors-and-debugging
- Credit and rate limits (402 and 429):
  https://openrouter.ai/docs/api_reference/limits
- Models list:  https://openrouter.ai/docs/api/api-reference/models/get-models
- Endpoints for one model:
  https://openrouter.ai/docs/api/api-reference/endpoints/list-all-endpoints-for-a-model
- Current API key (credit limit and usage, in USD):
  https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key
- Generation stats (cost and provider of one call, after the fact):
  https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field

import requests

BASE_URL = "https://openrouter.ai/api/v1"
CHAT_URL = f"{BASE_URL}/chat/completions"
MODELS_URL = f"{BASE_URL}/models"
KEY_URL = f"{BASE_URL}/key"
GENERATION_URL = f"{BASE_URL}/generation"

# Never wait longer than this for one retry, whatever Retry-After says.
MAX_WAIT_SECONDS = 300

# The answer we ask every model for: a rating, shortlist decision and reason for each
# candidate, plus a forced choice. Structured outputs take the form
# {"type": "json_schema", "json_schema": {"name", "strict", "schema"}} (structured outputs guide).
CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "shortlist": {"type": "boolean", "description": "Should this candidate be shortlisted?"},
        "rating": {"type": "integer", "description": "Rating from 1 to 10"},
        "reason": {"type": "string", "description": "One-sentence reason"},
    },
    "required": ["shortlist", "rating", "reason"],
    "additionalProperties": False,
}

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "cv_screening",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "candidate_1": CANDIDATE_SCHEMA,
                "candidate_2": CANDIDATE_SCHEMA,
                "preferred": {
                    "type": "string",
                    "enum": ["1", "2"],
                    "description": "Which candidate you would pick if only one",
                },
            },
            "required": ["candidate_1", "candidate_2", "preferred"],
            "additionalProperties": False,
        },
    },
}


def build_request_body(model, system_prompt, user_prompt, temperature):
    """The JSON body for one chat completion request."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": RESPONSE_FORMAT,
        # By default a provider that doesn't support a parameter "will ignore unknown
        # parameters"; with require_parameters "the request won't even be routed to that
        # provider" (provider routing docs). So no provider can silently drop the JSON
        # schema or the temperature.
        "provider": {"require_parameters": True},
    }
    if temperature is not None:
        body["temperature"] = temperature
    return body


# ----------------------------- results and errors -----------------------------

@dataclass
class CallResult:
    content: str        # the model's answer text (JSON)
    response: dict      # the full response body
    attempts: int
    elapsed: float      # seconds for the successful attempt
    notes: list = field(default_factory=list)  # one line per retry


class CallError(Exception):
    """A call that failed. `error_type` is a short label used to count failures by kind."""

    def __init__(self, error_type, message, status=None, retryable=False, retry_after=None, fatal=False, response=None):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status = status          # HTTP status, if there was a response
        self.retryable = retryable    # worth trying again after a wait?
        self.retry_after = retry_after  # seconds the server asked us to wait, if any
        self.fatal = fatal            # will every further call fail too (bad key, no credits)?
        self.response = response      # the error body, if any
        self.attempts = 1
        self.notes = []


# Status codes worth retrying, from the errors and limits pages: 408 timeout, 429 rate
# limit, 502 model down, 503 no provider available, and other server errors.
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504, 524}

STATUS_LABELS = {
    400: "bad_request", 401: "auth", 402: "payment", 403: "forbidden", 404: "not_found",
    408: "timeout", 429: "rate_limit",
}


def classify_status(status, body, retry_after=None):
    """A CallError for an HTTP error status, with the retry rules from the docs."""
    error = (body or {}).get("error") if isinstance(body, dict) else None
    error = error if isinstance(error, dict) else {}
    metadata = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
    message = error.get("message") or json.dumps(body)[:300] if body is not None else ""
    message = f"HTTP {status}: {message}"[:400]
    label = STATUS_LABELS.get(status, "server_error" if status >= 500 else "http_error")
    if status == 402:
        # Limits page: a 402 whose limit_source is openrouter_in_flight_budget "is
        # transient ... wait for the Retry-After header and retry". Any other 402 means
        # the credits are gone, so every further call would fail too.
        transient = metadata.get("limit_source") == "openrouter_in_flight_budget"
        return CallError("in_flight_budget" if transient else "payment", message, status,
                         retryable=transient, retry_after=retry_after, fatal=not transient, response=body)
    if status == 401:
        return CallError(label, message, status, fatal=True, response=body)
    return CallError(label, message, status, retryable=status in RETRYABLE_STATUSES,
                     retry_after=retry_after, response=body)


def parse_retry_after(value):
    """Seconds from a Retry-After header, or None. Only the plain number form is handled."""
    if value is None:
        return None
    value = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return min(float(value), MAX_WAIT_SECONDS)
    return None


def backoff_seconds(attempt, retry_after=None):
    """How long to wait before retrying: the server's Retry-After if given, otherwise
    exponential backoff (1, 2, 4, ... seconds) plus a little randomness so that
    several workers don't all retry at the same moment."""
    if retry_after:
        return min(max(retry_after, 1.0), MAX_WAIT_SECONDS)
    return min(2 ** (attempt - 1) + random.random(), 60)


# ----------------------------- rate limiting -----------------------------

class RateLimiter:
    """Spaces out call starts so that all workers together stay under calls_per_minute."""

    def __init__(self, calls_per_minute):
        self.interval = 60.0 / calls_per_minute if calls_per_minute else 0.0
        self.lock = threading.Lock()
        self.next_start = 0.0

    def wait(self):
        if not self.interval:
            return
        with self.lock:  # take the next free slot; the sleep itself happens outside the lock
            now = time.monotonic()
            start = max(now, self.next_start)
            self.next_start = start + self.interval
        if start > now:
            time.sleep(start - now)


# ----------------------------- the real client -----------------------------

class OpenRouterClient:
    """Sends requests to OpenRouter. Only used for real (paid) runs."""

    def __init__(self, api_key, timeout, max_retries, calls_per_minute=0):
        self.api_key = api_key  # never print or save this
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = RateLimiter(calls_per_minute)

    def headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Adds openrouter_metadata to the response, which names the provider that
            # served the call (router metadata guide).
            "X-OpenRouter-Metadata": "enabled",
        }

    def send(self, body) -> CallResult:
        """POST one request, retrying on transient errors. Raises CallError when it gives up."""
        notes = []
        for attempt in range(1, self.max_retries + 1):
            self.limiter.wait()
            started = time.monotonic()
            try:
                resp = requests.post(CHAT_URL, headers=self.headers(), json=body, timeout=self.timeout)
            except requests.Timeout:
                error = CallError("timeout", f"no response within {self.timeout:g}s", retryable=True)
            except requests.RequestException as e:
                error = CallError("network", f"{type(e).__name__}: {e}"[:300], retryable=True)
            else:
                result_or_error = check_response(resp)
                if isinstance(result_or_error, CallError):
                    error = result_or_error
                else:
                    return CallResult(content=result_or_error[0], response=result_or_error[1],
                                      attempts=attempt, elapsed=time.monotonic() - started, notes=notes)
            error.attempts = attempt
            error.notes = notes
            if not error.retryable or attempt == self.max_retries:
                raise error
            wait = backoff_seconds(attempt, error.retry_after)
            notes.append(f"attempt {attempt}: {error.error_type}: {error.message[:160]}; waiting {wait:.1f}s")
            time.sleep(wait)
        raise AssertionError("unreachable")  # the loop always returns or raises


def check_response(resp):
    """Turn an HTTP response into (content, body) or a CallError."""
    retry_after = parse_retry_after(resp.headers.get("Retry-After"))
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code != 200:
        if body is None:
            body = {"error": {"message": resp.text[:300]}}
        return classify_status(resp.status_code, body, retry_after)
    if not isinstance(body, dict):
        return CallError("bad_response", "the response was not a JSON object", 200, retryable=True)
    choices = body.get("choices") or []
    if "error" in body and not choices:
        # Errors page: after the provider accepted the request, a failure arrives as
        # "a 200 OK whose JSON body holds only an error object and no choices".
        code = (body["error"] or {}).get("code") if isinstance(body["error"], dict) else None
        error = classify_status(code if isinstance(code, int) else 502, body, retry_after)
        error.error_type = "provider_error"
        error.status = 200
        return error
    if not choices:
        return CallError("bad_response", "no choices in the response", 200, retryable=True, response=body)
    choice = choices[0]
    if choice.get("finish_reason") == "error":
        return CallError("provider_error", "the provider reported an error during generation", 200,
                         retryable=True, response=body)
    message = choice.get("message") or {}
    content = message.get("content")
    if not content:
        refusal = message.get("refusal")
        return CallError("empty_answer", f"the model returned no answer{': ' + str(refusal)[:200] if refusal else ''}",
                         200, response=body)
    return content, body


def extract_details(response) -> dict:
    """The fields worth keeping from one successful response body. Each field name is
    from the chat completion reference; cost and token details from usage accounting."""
    usage = response.get("usage") or {}
    metadata = response.get("openrouter_metadata") or {}
    provider = None
    for endpoint in (metadata.get("endpoints") or {}).get("available") or []:
        if endpoint.get("selected"):
            provider = endpoint.get("provider")
    choice = (response.get("choices") or [{}])[0]
    return {
        "generation_id": response.get("id"),
        "served_model": response.get("model"),
        "provider": provider,
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        # "Cost of the completion" in USD (the key endpoint describes credits as USD).
        "cost_usd": usage.get("cost"),
    }


# ----------------------------- the dry-run client -----------------------------

class DryRunClient:
    """Stand-in for OpenRouterClient used by --dry-run. It never touches the network and
    returns random but valid answers, in the same shape as a real response, so the rest
    of the pipeline (including the budget stop) can be tested for free."""

    FAKE_COST_USD = 0.0005  # per call, so --budget can be tried in a dry run

    def send(self, body) -> CallResult:
        answer = {
            "candidate_1": {"shortlist": random.random() > 0.4, "rating": random.randint(4, 9), "reason": "dry run"},
            "candidate_2": {"shortlist": random.random() > 0.4, "rating": random.randint(4, 9), "reason": "dry run"},
            "preferred": random.choice(["1", "2"]),
        }
        content = json.dumps(answer)
        prompt_tokens = sum(len(m["content"]) for m in body["messages"]) // 4
        response = {
            "id": "dry-" + uuid.uuid4().hex[:12],
            "model": body["model"],
            "object": "chat.completion",
            "dry_run": True,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": len(content) // 4,
                      "total_tokens": prompt_tokens + len(content) // 4, "cost": self.FAKE_COST_USD},
            "openrouter_metadata": {"endpoints": {"available": [{"provider": "dry-run", "model": body["model"],
                                                                 "selected": True}], "total": 1}},
        }
        return CallResult(content=content, response=response, attempts=1, elapsed=0.0)


# ----------------------------- reading the answer -----------------------------

def parse_answer(content):
    """Turn the model's reply into a dict. Tolerates a ```json fence around the JSON."""
    if isinstance(content, dict):
        return content
    content = content.strip()
    content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
    return json.loads(content)


def check_answer(parsed):
    """Raise ValueError if the answer is missing something or has an impossible value."""
    if not isinstance(parsed, dict):
        raise ValueError("the answer is not a JSON object")
    for c in ("candidate_1", "candidate_2"):
        candidate = parsed.get(c)
        if not isinstance(candidate, dict):
            raise ValueError(f"{c} is missing")
        for key in ("shortlist", "rating", "reason"):
            if key not in candidate:
                raise ValueError(f"{c}.{key} is missing")
        r = candidate["rating"]
        # bool is excluded on purpose: Python counts True as the number 1.
        if isinstance(r, bool) or not isinstance(r, int) or not 1 <= r <= 10:
            raise ValueError(f"{c}.rating out of range: {r!r}")
        if not isinstance(candidate["shortlist"], bool):
            raise ValueError(f"{c}.shortlist is not true/false: {candidate['shortlist']!r}")
        if not isinstance(candidate["reason"], str):
            raise ValueError(f"{c}.reason is not text")
    if parsed.get("preferred") not in ("1", "2"):
        raise ValueError(f"preferred must be \"1\" or \"2\", got {parsed.get('preferred')!r}")


# ----------------------------- free information endpoints -----------------------------

def get_json(url, api_key=None, params=None, timeout=60):
    """GET a JSON document. The key is sent when given; the public models list works without it."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise CallError("network", f"{type(e).__name__}: {e}"[:300]) from None
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code != 200:
        raise classify_status(resp.status_code, body if body is not None else {"error": {"message": resp.text[:300]}})
    return body


def list_models(api_key=None) -> list:
    """Every model OpenRouter offers, with supported_parameters and pricing (models list docs)."""
    return get_json(MODELS_URL, api_key)["data"]


def model_endpoints(details_path, api_key=None) -> dict:
    """The providers ("endpoints") serving one model. `details_path` is the model's
    links.details value, e.g. /api/v1/models/openai/gpt-4o/endpoints."""
    url = details_path if details_path.startswith("http") else "https://openrouter.ai" + details_path
    return get_json(url, api_key)["data"]


def key_info(api_key) -> dict:
    """Credit limit and usage (in USD) for the key, from GET /api/v1/key."""
    return get_json(KEY_URL, api_key)["data"]


def generation_stats(api_key, generation_id) -> dict:
    """Cost, provider and token counts of one call, from GET /api/v1/generation?id=..."""
    return get_json(GENERATION_URL, api_key, params={"id": generation_id})["data"]

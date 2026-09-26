"""Sending one CV pair to a model through OpenRouter, and reading its answer.

OpenRouter docs this code relies on (checked 2026-09-26):
- Chat completions request and response:
  https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion
- Structured outputs (response_format with a JSON schema):
  https://openrouter.ai/docs/guides/features/structured-outputs
- Provider routing (provider.require_parameters):
  https://openrouter.ai/docs/guides/routing/provider-selection
"""

from __future__ import annotations

import json
import random
import re
import time

import requests

# Chat completions endpoint. The key goes in the Authorization header as a bearer
# token (chat completion reference above).
API_URL = "https://openrouter.ai/api/v1/chat/completions"

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


class OpenRouterClient:
    """Sends requests to OpenRouter. Only used for real (paid) runs."""

    def __init__(self, api_key, timeout, max_retries):
        self.api_key = api_key  # never print or save this
        self.timeout = timeout
        self.max_retries = max_retries

    def send(self, body):
        """POST one request. Returns (answer_text, full_response_json)."""
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        error = ""
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(API_URL, headers=headers, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                error = f"{type(e).__name__}: {e}"
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    # The answer text is in choices[0].message.content (response example
                    # in the chat completion reference).
                    return data["choices"][0]["message"]["content"], data
                error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                if resp.status_code in (400, 401, 402, 404):
                    raise RuntimeError(error)  # retrying won't fix these
            wait = 2 ** attempt + random.random()
            print(f"  retry {attempt + 1}/{self.max_retries} in {wait:.1f}s ({error[:120]})")
            time.sleep(wait)
        raise RuntimeError(f"gave up after {self.max_retries} attempts: {error}")


class DryRunClient:
    """Stand-in for OpenRouterClient used by --dry-run. It never touches the network and
    returns random but valid answers, so the rest of the pipeline can be tested for free."""

    def send(self, body):
        answer = {
            "candidate_1": {"shortlist": random.random() > 0.4, "rating": random.randint(4, 9), "reason": "dry run"},
            "candidate_2": {"shortlist": random.random() > 0.4, "rating": random.randint(4, 9), "reason": "dry run"},
            "preferred": random.choice(["1", "2"]),
        }
        return json.dumps(answer), {"model": body["model"], "dry_run": True}


def parse_answer(content):
    """Turn the model's reply into a dict. Tolerates a ```json fence around the JSON."""
    if isinstance(content, dict):
        return content
    content = content.strip()
    content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
    return json.loads(content)


def check_answer(parsed):
    """Raise ValueError if the answer has an impossible rating or choice."""
    for c in ("candidate_1", "candidate_2"):
        r = parsed[c]["rating"]
        if not (isinstance(r, int) and 1 <= r <= 10):
            raise ValueError(f"rating out of range: {r}")
    if parsed["preferred"] not in ("1", "2"):
        raise ValueError("bad preferred value")

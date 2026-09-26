"""The OpenRouter client, tested against a fake requests.post: retry rules, the
Retry-After header, error bodies inside a 200, and reading the response fields."""

import json

import pytest

from pipeline import client as api


class FakeResponse:
    def __init__(self, status, body=None, headers=None, text=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("not JSON")
        return self._body


def good_body(answer=None, **extra):
    content = json.dumps(answer or {
        "candidate_1": {"shortlist": True, "rating": 7, "reason": "solid"},
        "candidate_2": {"shortlist": False, "rating": 4, "reason": "weak"},
        "preferred": "1"})
    body = {"id": "gen-123", "model": "test/model-v1", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 60, "total_tokens": 960, "cost": 0.0012,
                      "prompt_tokens_details": {"cached_tokens": 100},
                      "completion_tokens_details": {"reasoning_tokens": 5}},
            "openrouter_metadata": {"endpoints": {"total": 2, "available": [
                {"provider": "Alpha", "model": "test/model-v1", "selected": False},
                {"provider": "Beta", "model": "test/model-v1", "selected": True}]}}}
    body.update(extra)
    return body


@pytest.fixture
def fake_http(monkeypatch):
    """Scripted responses for requests.post, and a record of every call and every sleep."""
    state = {"responses": [], "posts": [], "sleeps": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        state["posts"].append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        item = state["responses"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(api.requests, "post", fake_post)
    monkeypatch.setattr(api.time, "sleep", lambda s: state["sleeps"].append(s))
    return state


def make_client(max_retries=3):
    return api.OpenRouterClient("sk-test", timeout=30, max_retries=max_retries)


def test_a_good_response_is_returned_with_its_details(fake_http):
    fake_http["responses"] = [FakeResponse(200, good_body())]
    result = make_client().send({"model": "test/model-v1", "messages": []})
    assert result.attempts == 1
    post = fake_http["posts"][0]
    assert post["url"] == api.CHAT_URL
    assert post["headers"]["Authorization"] == "Bearer sk-test"
    assert post["headers"]["X-OpenRouter-Metadata"] == "enabled"
    details = api.extract_details(result.response)
    assert details == {"generation_id": "gen-123", "served_model": "test/model-v1", "provider": "Beta",
                       "finish_reason": "stop", "prompt_tokens": 900, "completion_tokens": 60,
                       "total_tokens": 960, "reasoning_tokens": 5, "cached_tokens": 100, "cost_usd": 0.0012}


def test_429_is_retried_after_the_retry_after_header(fake_http):
    fake_http["responses"] = [
        FakeResponse(429, {"error": {"code": 429, "message": "Rate limit exceeded"}}, headers={"Retry-After": "7"}),
        FakeResponse(200, good_body()),
    ]
    result = make_client().send({})
    assert result.attempts == 2
    assert fake_http["sleeps"] == [7.0]
    assert result.notes == ["attempt 1: rate_limit: HTTP 429: Rate limit exceeded; waiting 7.0s"]


def test_server_errors_and_network_problems_are_retried_with_backoff(fake_http):
    fake_http["responses"] = [
        FakeResponse(502, {"error": {"code": 502, "message": "model down"}}),
        api.requests.ConnectionError("connection reset"),
        FakeResponse(200, good_body()),
    ]
    result = make_client().send({})
    assert result.attempts == 3
    assert len(fake_http["sleeps"]) == 2
    assert 1 <= fake_http["sleeps"][0] < 2 and 2 <= fake_http["sleeps"][1] < 3


def test_gives_up_after_max_retries(fake_http):
    fake_http["responses"] = [FakeResponse(503, {"error": {"code": 503, "message": "no provider"}})] * 3
    with pytest.raises(api.CallError) as err:
        make_client(max_retries=3).send({})
    assert err.value.error_type == "server_error"
    assert err.value.attempts == 3
    assert len(fake_http["posts"]) == 3


@pytest.mark.parametrize("status, error_type, fatal", [
    (400, "bad_request", False), (401, "auth", True), (403, "forbidden", False), (404, "not_found", False),
])
def test_client_errors_are_not_retried(fake_http, status, error_type, fatal):
    fake_http["responses"] = [FakeResponse(status, {"error": {"code": status, "message": "nope"}})]
    with pytest.raises(api.CallError) as err:
        make_client().send({})
    assert (err.value.error_type, err.value.fatal, err.value.status) == (error_type, fatal, status)
    assert len(fake_http["posts"]) == 1 and fake_http["sleeps"] == []


def test_402_out_of_credits_is_fatal_but_the_in_flight_budget_case_is_retried(fake_http):
    fake_http["responses"] = [FakeResponse(402, {"error": {"code": 402, "message": "Insufficient credits",
                                                          "metadata": {"limit_source": "openrouter_credits"}}})]
    with pytest.raises(api.CallError) as err:
        make_client().send({})
    assert (err.value.error_type, err.value.fatal, err.value.retryable) == ("payment", True, False)

    fake_http["responses"] = [
        FakeResponse(402, {"error": {"code": 402, "message": "in flight", "metadata":
                           {"limit_source": "openrouter_in_flight_budget"}}}, headers={"Retry-After": "3"}),
        FakeResponse(200, good_body()),
    ]
    assert make_client().send({}).attempts == 2
    assert fake_http["sleeps"] == [3.0]


def test_an_error_body_inside_a_200_is_a_provider_error(fake_http):
    fake_http["responses"] = [
        FakeResponse(200, {"id": "gen-1", "error": {"code": 502, "message": "upstream failed"}}),
        FakeResponse(200, good_body()),
    ]
    assert make_client().send({}).attempts == 2
    fake_http["responses"] = [FakeResponse(200, {"error": {"code": 400, "message": "bad prompt"}})]
    with pytest.raises(api.CallError) as err:
        make_client().send({})
    assert err.value.error_type == "provider_error" and err.value.status == 200 and not err.value.retryable


def test_finish_reason_error_and_empty_answers(fake_http):
    body = good_body()
    body["choices"][0]["finish_reason"] = "error"
    fake_http["responses"] = [FakeResponse(200, body), FakeResponse(200, good_body())]
    assert make_client().send({}).attempts == 2

    body = good_body()
    body["choices"][0]["message"] = {"role": "assistant", "content": None, "refusal": "I can't rank people"}
    fake_http["responses"] = [FakeResponse(200, body)]
    with pytest.raises(api.CallError) as err:
        make_client().send({})
    assert err.value.error_type == "empty_answer" and "I can't rank people" in err.value.message


def test_timeouts_are_retried_and_a_non_json_error_page_is_reported(fake_http):
    fake_http["responses"] = [api.requests.Timeout(), FakeResponse(200, good_body())]
    assert make_client().send({}).attempts == 2
    fake_http["responses"] = [FakeResponse(524, None, text="<html>timeout</html>")] * 3
    with pytest.raises(api.CallError) as err:
        make_client().send({})
    assert err.value.error_type == "server_error" and "<html>timeout</html>" in err.value.message


def test_retry_after_is_only_read_as_plain_seconds_and_capped():
    assert api.parse_retry_after("12") == 12.0
    assert api.parse_retry_after("2.5") == 2.5
    assert api.parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert api.parse_retry_after(None) is None
    assert api.parse_retry_after("100000") == api.MAX_WAIT_SECONDS
    assert api.backoff_seconds(1, retry_after=0.2) == 1.0


def test_rate_limiter_spaces_out_calls(monkeypatch):
    clock = {"now": 100.0}
    sleeps = []
    monkeypatch.setattr(api.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(api.time, "sleep", lambda s: sleeps.append(s))
    limiter = api.RateLimiter(calls_per_minute=120)  # one call every 0.5 s
    limiter.wait()
    limiter.wait()
    limiter.wait()
    assert sleeps == [0.5, 1.0]
    assert api.RateLimiter(0).interval == 0


def test_dry_run_client_looks_like_a_real_response():
    result = api.DryRunClient().send({"model": "m", "messages": [{"content": "x" * 400}]})
    answer = api.parse_answer(result.content)
    api.check_answer(answer)
    details = api.extract_details(result.response)
    assert details["provider"] == "dry-run" and details["cost_usd"] == api.DryRunClient.FAKE_COST_USD
    assert details["prompt_tokens"] == 100 and details["finish_reason"] == "stop"


@pytest.mark.parametrize("content", [
    '{"candidate_1": {"shortlist": true, "rating": 7, "reason": "ok"}, "candidate_2": {"shortlist": false, "rating": 3, "reason": "no"}, "preferred": "2"}',
    '```json\n{"candidate_1": {"shortlist": true, "rating": 7, "reason": "ok"}, "candidate_2": {"shortlist": false, "rating": 3, "reason": "no"}, "preferred": "2"}\n```',
])
def test_answers_are_parsed_with_or_without_a_code_fence(content):
    answer = api.parse_answer(content)
    api.check_answer(answer)
    assert answer["preferred"] == "2"


@pytest.mark.parametrize("bad, message", [
    ("not json at all", None),
    ('{"candidate_1": {"shortlist": true, "rating": 11, "reason": "x"}, "candidate_2": {"shortlist": true, "rating": 5, "reason": "x"}, "preferred": "1"}', "rating out of range"),
    ('{"candidate_1": {"shortlist": true, "rating": true, "reason": "x"}, "candidate_2": {"shortlist": true, "rating": 5, "reason": "x"}, "preferred": "1"}', "rating out of range"),
    ('{"candidate_1": {"shortlist": true, "rating": 7.5, "reason": "x"}, "candidate_2": {"shortlist": true, "rating": 5, "reason": "x"}, "preferred": "1"}', "rating out of range"),
    ('{"candidate_1": {"shortlist": "yes", "rating": 7, "reason": "x"}, "candidate_2": {"shortlist": true, "rating": 5, "reason": "x"}, "preferred": "1"}', "shortlist"),
    ('{"candidate_1": {"shortlist": true, "rating": 7, "reason": "x"}, "preferred": "1"}', "candidate_2 is missing"),
    ('{"candidate_1": {"shortlist": true, "rating": 7}, "candidate_2": {"shortlist": true, "rating": 5, "reason": "x"}, "preferred": "1"}', "reason is missing"),
    ('{"candidate_1": {"shortlist": true, "rating": 7, "reason": "x"}, "candidate_2": {"shortlist": true, "rating": 5, "reason": "x"}, "preferred": "3"}', "preferred"),
    ('{"candidate_1": {"shortlist": true, "rating": 7, "reason": "x"}, "candidate_2": {"shortlist": true, "rating": 5, "reason": "x"}, "preferred": 1}', "preferred"),
    ('[1, 2, 3]', "not a JSON object"),
])
def test_bad_model_output_is_rejected(bad, message):
    if message is None:
        with pytest.raises(ValueError):
            api.parse_answer(bad)
    else:
        with pytest.raises(ValueError, match=message):
            api.check_answer(api.parse_answer(bad))


def test_info_endpoints_send_the_key_and_report_errors(monkeypatch):
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, headers, params))
        if url == api.KEY_URL:
            return FakeResponse(200, {"data": {"label": "k", "limit": 10, "limit_remaining": 4.5, "usage": 5.5}})
        if url == api.MODELS_URL:
            return FakeResponse(200, {"data": [{"id": "a/b"}]})
        if url.endswith("/endpoints"):
            return FakeResponse(200, {"data": {"endpoints": [{"provider_name": "P"}]}})
        return FakeResponse(401, {"error": {"code": 401, "message": "bad key"}})

    monkeypatch.setattr(api.requests, "get", fake_get)
    assert api.key_info("sk-x")["limit_remaining"] == 4.5
    assert api.list_models("sk-x") == [{"id": "a/b"}]
    assert api.model_endpoints("/api/v1/models/a/b/endpoints", "sk-x")["endpoints"][0]["provider_name"] == "P"
    assert calls[2][0] == "https://openrouter.ai/api/v1/models/a/b/endpoints"
    assert all(h["Authorization"] == "Bearer sk-x" for _, h, _ in calls)
    with pytest.raises(api.CallError) as err:
        api.generation_stats("sk-x", "gen-1")
    assert err.value.error_type == "auth" and calls[-1][2] == {"id": "gen-1"}

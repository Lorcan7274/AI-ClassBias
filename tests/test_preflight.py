"""preflight, with the OpenRouter information endpoints faked."""

import pytest

from pipeline import client as api
from pipeline import preflight


MODELS = [
    {"id": "test/frontier-model", "name": "Frontier", "context_length": 128000,
     "supported_parameters": ["temperature", "structured_outputs", "response_format"],
     "pricing": {"prompt": "0.000002", "completion": "0.000008"},
     "links": {"details": "/api/v1/models/test/frontier-model/endpoints"}},
    {"id": "test/open-model", "name": "Open", "context_length": 32000,
     "supported_parameters": ["temperature", "max_tokens"],  # no structured outputs
     "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
     "links": {"details": "/api/v1/models/test/open-model/endpoints"}},
]


@pytest.fixture
def fake_api(monkeypatch):
    state = {"key": {"label": "study key", "limit": 50, "limit_remaining": 20, "usage": 30, "usage_daily": 1},
             "models": MODELS, "paid_calls": 0}
    monkeypatch.setattr(api, "key_info", lambda key: dict(state["key"]))
    monkeypatch.setattr(api, "list_models", lambda key=None: list(state["models"]))
    monkeypatch.setattr(api, "model_endpoints", lambda path, key=None: {"endpoints": [
        {"provider_name": "Alpha", "status": 0, "uptime_last_1d": 99.5,
         "supported_parameters": ["structured_outputs"] if "frontier" in path else []}]})

    def no_paid_call(self, body):
        state["paid_calls"] += 1
        raise AssertionError("a paid call was attempted")
    monkeypatch.setattr(api.OpenRouterClient, "send", no_paid_call)
    return state


def test_preflight_reports_models_without_structured_outputs(project, fake_api, capsys):
    ok = preflight.run_preflight(project, "sk-test")
    out = capsys.readouterr().out
    assert not ok
    assert "spending limit: $50; remaining: $20" in out
    assert "test/frontier-model:\n    name: Frontier" in out
    assert "structured_outputs: yes; response_format: yes; temperature: yes" in out
    assert "structured_outputs: NO" in out
    assert "provider Alpha: structured_outputs yes" in out
    assert "$2.000 per M prompt tokens, $8.000 per M completion tokens" in out
    assert "model 'test/open-model' does not list structured_outputs" in out
    assert "CV pair(s) contain the word PLACEHOLDER" in out  # the test project uses dummy CVs
    assert "No paid test call was made" in out
    assert fake_api["paid_calls"] == 0
    assert "sk-test" not in out


def test_preflight_flags_unknown_models_and_a_used_up_key(project, fake_api, capsys):
    fake_api["models"] = [dict(MODELS[0], id="test/other")]
    fake_api["key"]["limit_remaining"] = 0
    assert not preflight.run_preflight(project, "sk-test")
    out = capsys.readouterr().out
    assert "model 'test/frontier-model' is not in the OpenRouter models list" in out
    assert "the key's spending limit is used up" in out


def test_preflight_skips_paid_calls_while_there_are_problems(project, fake_api, capsys):
    assert not preflight.run_preflight(project, "sk-test", allow_paid=True)
    assert "Skipping the paid test calls" in capsys.readouterr().out
    assert fake_api["paid_calls"] == 0


def test_preflight_without_a_key_makes_no_api_calls(project, fake_api, monkeypatch, capsys):
    monkeypatch.setattr(api, "key_info", lambda key: (_ for _ in ()).throw(AssertionError("called")))
    assert not preflight.run_preflight(project, "")
    assert "OPENROUTER_API_KEY is not set" in capsys.readouterr().out

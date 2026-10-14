"""preflight, with the OpenRouter information endpoints faked."""

import pytest

from pipeline import client as api
from pipeline import preflight


MODELS = [
    {"id": "test/frontier-model", "name": "Frontier", "context_length": 128000,
     "supported_parameters": ["temperature", "structured_outputs", "response_format"],
     "pricing": {"prompt": "0.000002", "completion": "0.000008",
                 "input_cache_read": "0.0000002", "input_cache_write": "0.0000025"},
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
    assert "$2.000 per M prompt tokens, $8.000 per M completion tokens; cache read $0.200 per M, write $2.500 per M" in out
    assert "no cache price listed" in out  # the open model lists none
    assert "without caching" in out and "with (" in out
    assert "Prompt: ~" in out and "cacheable prefix" in out
    assert "model 'test/open-model' does not list structured_outputs" in out
    assert "CV(s) contain the word PLACEHOLDER" in out  # the test project uses dummy CVs
    assert "Calls per session: 72 = 2 models x 18 CVs x 2 samples" in out
    assert "Fillers in" in out and "F1.txt, F2.txt); the target is always Applicant 3" in out
    assert "No paid test call was made" in out
    assert fake_api["paid_calls"] == 0
    assert "sk-test" not in out


def test_preflight_rejects_a_temperature_a_model_cannot_take_unless_opted_out(make_config, fake_api, capsys):
    from pipeline.config import load_config
    from pipeline.cvs import make_dummy_cvs
    fake_api["models"] = [dict(MODELS[0], supported_parameters=["structured_outputs", "response_format"]),
                          dict(MODELS[1], supported_parameters=["structured_outputs", "temperature"])]
    cfg = load_config(make_config({"temperature: null": "temperature: 1.0"}))
    make_dummy_cvs(cfg.cv_dir, cfg.arms, n_cvs=3)
    preflight.run_preflight(cfg, "sk-test")
    out = capsys.readouterr().out
    assert "model 'test/frontier-model' does not list temperature" in out
    assert "Temperature: 1" in out

    cfg = load_config(make_config({"temperature: null": "temperature: 1.0",
                                   "type: frontier": "type: frontier\n    send_temperature: false"}))
    preflight.run_preflight(cfg, "sk-test")
    out = capsys.readouterr().out
    assert "does not list temperature" not in out
    assert "not sent to test/frontier-model (send_temperature: false)" in out
    assert "(not sent to this model: send_temperature is false)" in out


def test_preflight_refuses_a_run_with_no_fillers(project, fake_api, capsys):
    for path in project.filler_dir.glob("*.txt"):
        path.unlink()
    assert not preflight.run_preflight(project, "sk-test")
    assert "no filler CVs in" in capsys.readouterr().out


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

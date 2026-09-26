"""Shared test set-up.

Every test works in its own temporary folder, so the real cvs/ and results/ folders
(results/results.jsonl above all) are never touched. No test may use the network.
"""

import pytest
import requests

from pipeline.config import load_config
from pipeline.cvs import make_dummy_cvs

# A small study: 2 models, 3 arms, 2 reps. With 3 base CVs that gives
# 9 pairs and 2 x 9 x 2 x 2 = 72 calls per session.
CONFIG_TEXT = """
models:
  - id: test/frontier-model
    type: frontier
  - id: test/open-model
    type: open_source
arms:
  implicit: [high, low]
  explicit: [high, low]
  demographic: [a, b]
reps: 2
temperature: null
shuffle_seed: 1
prompts:
  job_description: Graduate Analyst.
  system_prompt: You are a recruiter.
  user_prompt_template: |-
    Job: {job}
    === CANDIDATE 1 ===
    {cv1}
    === CANDIDATE 2 ===
    {cv2}
paths:
  cv_dir: cvs
  results_dir: results
runner:
  sleep_between_calls: 0
  max_retries: 1
  request_timeout: 5
"""
CALLS_PER_SESSION = 72


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if any test tries a real HTTP request (which could cost money)."""
    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not make network calls")
    monkeypatch.setattr(requests.sessions.Session, "request", refuse)


@pytest.fixture
def make_config(tmp_path):
    """Returns a function that writes config.yaml into the test's temporary folder.
    Pass {old_text: new_text} to change settings, e.g. make_config({"reps: 2": "reps: 0"})."""
    def _make(replacements=None):
        text = CONFIG_TEXT
        for old, new in (replacements or {}).items():
            assert old in text, f"{old!r} is not in the test config"
            text = text.replace(old, new)
        path = tmp_path / "config.yaml"
        path.write_text(text, encoding="utf-8")
        return path
    return _make


@pytest.fixture
def project(make_config):
    """The test config plus placeholder CVs for 3 base CVs. Returns the loaded Config."""
    cfg = load_config(make_config())
    make_dummy_cvs(cfg.cv_dir, cfg.arms, n_cvs=3)
    return cfg

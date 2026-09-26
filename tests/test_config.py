import pytest

from pipeline.config import DEFAULT_CONFIG_PATH, ConfigError, load_config, read_api_key


def test_shipped_config_matches_the_study_design():
    """config.yaml in the repo loads, with 3 arms, 5 reps, 2 frontier and 2 open-source models."""
    cfg = load_config(DEFAULT_CONFIG_PATH)
    assert cfg.arms == {"implicit": ("high", "low"), "explicit": ("high", "low"), "demographic": ("a", "b")}
    assert cfg.reps == 5
    assert sorted(m.type for m in cfg.models) == ["frontier", "frontier", "open_source", "open_source"]


def test_folders_are_relative_to_the_config_file(make_config, tmp_path):
    cfg = load_config(make_config())
    assert cfg.cv_dir == tmp_path.resolve() / "cvs"
    assert cfg.output_dir(dry_run=False) == tmp_path.resolve() / "results"
    assert cfg.output_dir(dry_run=True) == tmp_path.resolve() / "results" / "dry_run"


@pytest.mark.parametrize("old, new, message", [
    ("temperature: null", "temprature: null", "temprature"),       # typo in a setting name
    ("max_retries: 1", "max_retry: 1", "max_retry"),               # typo inside a section
    ("reps: 2", "reps: 0", "reps"),
    ("reps: 2", "reps: 2.5", "reps"),
    ("temperature: null", "temperature: 2.5", "temperature"),      # OpenRouter allows 0-2
    ("temperature: null", "temperature: yes", "temperature"),      # YAML reads yes as true
    ("implicit: [high, low]", "implicit: [high, high]", "implicit"),
    ("implicit: [high, low]", "implicit: [high]", "implicit"),
    ("implicit: [high, low]", "implicit: [high_class, low]", "implicit"),  # "_" would break file names
    ("type: frontier", "type: closed", "type"),
    ("id: test/open-model", "id: test/frontier-model", "more than once"),
    ("{cv2}", "{cv3}", r"missing \{cv2\}; unknown \{cv3\}"),
    ("Job: {job}", "Job: {job} {", "unmatched curly brace"),
    ("job_description: Graduate Analyst.", "job_description: ''", "job_description"),
])
def test_bad_settings_are_rejected_with_a_clear_message(make_config, old, new, message):
    with pytest.raises(ConfigError, match=message):
        load_config(make_config({old: new}))


def test_literal_braces_in_the_template_are_allowed(make_config):
    cfg = load_config(make_config({"Job: {job}": "Job: {job} {{not a placeholder}}"}))
    assert "{{not a placeholder}}" in cfg.user_prompt_template


def test_placeholders_are_reported(make_config):
    cfg = load_config(make_config({
        "id: test/open-model": "id: PUT_OPEN_SOURCE_MODEL_HERE",
        "job_description: Graduate Analyst.": "job_description: PLACEHOLDER job advert",
    }))
    problems = " ".join(cfg.placeholder_problems())
    assert "PUT_OPEN_SOURCE_MODEL_HERE" in problems
    assert "job_description" in problems


def test_api_key_comes_from_env_file_or_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert read_api_key(tmp_path) == ""                     # no .env and nothing in the environment
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-from-file\n", encoding="utf-8")
    assert read_api_key(tmp_path) == "sk-from-file"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-environment")
    assert read_api_key(tmp_path) == "sk-from-environment"  # the environment wins

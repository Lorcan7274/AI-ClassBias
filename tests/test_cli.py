import json

import pytest

from conftest import CALLS_PER_SESSION

from pipeline.cli import main


def run_cli(config_path, *args):
    main(["--config", str(config_path), *args])


def test_full_dry_run_from_the_command_line(make_config, tmp_path, capsys):
    config = make_config()
    run_cli(config, "make-dummy-cvs", "--n-cvs", "3")
    run_cli(config, "validate-cvs")
    run_cli(config, "run", "--session", "day1", "--dry-run")
    run_cli(config, "run", "--session", "day2", "--dry-run")
    run_cli(config, "analyze", "--dry-run")

    dry = tmp_path / "results" / "dry_run"
    rows = [json.loads(line) for line in (dry / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 * CALLS_PER_SESSION
    assert {r["session"] for r in rows} == {"day1", "day2"}
    assert (dry / "summary.csv").exists() and (dry / "all_calls_flat.csv").exists()
    assert not (tmp_path / "results" / "results.jsonl").exists()
    assert "pct_pick_x" in capsys.readouterr().out


def test_make_dummy_cvs_refuses_to_run_twice(make_config):
    config = make_config()
    run_cli(config, "make-dummy-cvs", "--n-cvs", "1")
    with pytest.raises(SystemExit, match="already holds"):
        run_cli(config, "make-dummy-cvs", "--n-cvs", "1")


def test_validate_cvs_fails_when_a_variant_file_is_missing(make_config, tmp_path, capsys):
    config = make_config()
    run_cli(config, "make-dummy-cvs", "--n-cvs", "2")
    (tmp_path / "cvs" / "cv02_explicit_low.txt").unlink()
    with pytest.raises(SystemExit) as stop:
        run_cli(config, "validate-cvs")
    assert stop.value.code == 1
    assert "cv02_explicit" in capsys.readouterr().out


def test_real_run_refuses_without_an_api_key(make_config, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = make_config()
    (tmp_path / "cvs").mkdir()
    for arm_variant in ("implicit_high", "implicit_low"):
        (tmp_path / "cvs" / f"cv01_{arm_variant}.txt").write_text(f"real CV {arm_variant}", encoding="utf-8")
    with pytest.raises(SystemExit, match="OPENROUTER_API_KEY"):
        run_cli(config, "run", "--session", "day1")
    assert not (tmp_path / "results").exists()


def test_real_run_refuses_placeholders_and_never_prints_the_key(make_config, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-real-key")
    config = make_config({"id: test/open-model": "id: PUT_OPEN_SOURCE_MODEL_HERE"})
    run_cli(config, "make-dummy-cvs", "--n-cvs", "1")
    with pytest.raises(SystemExit) as stop:
        run_cli(config, "run", "--session", "day1")
    message = str(stop.value.code)
    assert "PUT_OPEN_SOURCE_MODEL_HERE" in message
    assert "PLACEHOLDER" in message
    assert not (tmp_path / "results").exists()

    with pytest.raises(SystemExit):
        run_cli(config, "preflight")
    output = capsys.readouterr().out
    assert "OPENROUTER_API_KEY: found" in output
    assert "sk-test-not-a-real-key" not in output + message


def test_bad_config_gives_a_clear_error(make_config):
    config = make_config({"reps: 2": "reps: none"})
    with pytest.raises(SystemExit, match="reps must be a whole number"):
        run_cli(config, "validate-cvs")


def test_analyze_without_results_says_so(make_config, capsys):
    run_cli(make_config(), "analyze")
    assert "No results yet" in capsys.readouterr().out

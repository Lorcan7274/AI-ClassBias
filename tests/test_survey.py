"""The human survey comparison."""

import pandas as pd
import pytest

from pipeline import survey
from test_analysis import make_rows, write_rows


@pytest.fixture
def sample(project, tmp_path):
    return survey.write_sample_survey(tmp_path / "survey.csv", project.arms, n_participants=12,
                                      pairs_per_participant=3, n_cvs=3, seed=1)


def test_sample_survey_has_the_documented_columns(sample):
    df = pd.read_csv(sample)
    assert list(df.columns) == ["participant_id", "pair_id", "first_variant", "chosen_position", "guess_job_1",
                                "guess_school_1", "rating_1", "guess_job_2", "guess_school_2", "rating_2"]
    assert len(df) == 36 and df["participant_id"].nunique() == 12
    assert set(df["first_variant"]) == {"high", "low"} and set(df["chosen_position"]) == {1, 2}


def test_picked_high_is_worked_out_from_position_and_first_variant(project, tmp_path):
    path = tmp_path / "s.csv"
    pd.DataFrame([
        {"participant_id": "a", "pair_id": "cv01_implicit", "first_variant": "high", "chosen_position": 1,
         "guess_job_1": "professional", "guess_job_2": "manual", "guess_school_1": "private", "guess_school_2": "state"},
        {"participant_id": "a", "pair_id": "cv02_implicit", "first_variant": "low", "chosen_position": 1,
         "guess_job_1": "manual", "guess_job_2": "professional", "guess_school_1": "state", "guess_school_2": "private"},
        {"participant_id": "b", "pair_id": "cv02_implicit", "first_variant": "low", "chosen_position": 2,
         "guess_job_1": "unsure", "guess_job_2": "Professional", "guess_school_1": "state", "guess_school_2": "unsure"},
    ]).to_csv(path, index=False)
    df = survey.load_survey(path, project.arms)
    assert df["picked_high"].tolist() == [1, 0, 1]
    assert df["chosen_variant"].tolist() == ["high", "low", "high"]
    check = survey.manipulation_check(df, project.arms)
    high_job = check[(check["variant_shown"] == "high") & (check["guess"] == "parental job")].iloc[0]
    assert high_job["n_shown"] == 3 and high_job["pct_intended_of_decided"] == 100.0
    low_school = check[(check["variant_shown"] == "low") & (check["guess"] == "school type")].iloc[0]
    assert low_school["n_decided"] == 3 and low_school["pct_intended_of_decided"] == 100.0


@pytest.mark.parametrize("column, value, message", [
    ("first_variant", "medium", "first_variant must be high or low"),
    ("chosen_position", "3", "chosen_position must be 1 or 2"),
    ("guess_job_1", "rich", "guess_job_1 must be professional, manual or unsure"),
    ("guess_school_2", "grammar", "guess_school_2 must be private, state or unsure"),
    ("pair_id", "cv01_gender", "pair_id must end in an arm name"),
])
def test_bad_survey_values_are_reported_with_the_line_number(project, sample, column, value, message):
    df = pd.read_csv(sample, dtype=str)
    df.loc[4, column] = value
    df.to_csv(sample, index=False)
    with pytest.raises(survey.SurveyError, match=message):
        survey.load_survey(sample, project.arms)


def test_missing_columns_are_reported(project, sample):
    df = pd.read_csv(sample).drop(columns=["guess_school_2"])
    df.to_csv(sample, index=False)
    with pytest.raises(survey.SurveyError, match="missing the column"):
        survey.load_survey(sample, project.arms)


def test_analyze_survey_compares_with_the_models_on_the_same_pairs(project, sample, capsys):
    write_rows(project, make_rows(project, {"implicit": 0.9, "explicit": 0.5, "demographic": 0.5}, reps=2))
    summary = survey.analyze_survey(project, sample, dry_run=False)
    assert 0 < summary.iloc[0]["human_pick_high_rate"] < 1
    out_dir = project.output_dir(False) / "survey"
    by_pair = pd.read_csv(out_dir / "survey_by_pair.csv")
    assert set(by_pair["pair_id"]) <= {"cv01_implicit", "cv02_implicit", "cv03_implicit"}
    assert {"model_frontier-model", "model_open-model"} <= set(by_pair.columns)
    assert (by_pair["model_frontier-model"] > 0.6).all()
    for name in ["survey_summary.csv", "survey_manipulation_check.csv", "survey_report.md", "figures/survey_vs_models.png"]:
        assert (out_dir / name).exists(), name
    report = (out_dir / "survey_report.md").read_text(encoding="utf-8")
    assert "## Manipulation check" in report and "Spearman" in report


def test_analyze_survey_without_model_results(project, sample):
    survey.analyze_survey(project, sample, dry_run=False)
    report = (project.output_dir(False) / "survey" / "survey_report.md").read_text(encoding="utf-8")
    assert "No model results were found" in report

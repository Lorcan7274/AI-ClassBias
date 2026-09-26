"""CV checks (validate-cvs). The study depends on each pair being identical except
for its arm's marker, so these tests make sure every kind of problem is caught."""

import pytest

from pipeline.cvs import cv_path, dummy_cv_text, read_cv
from pipeline.validation import ERROR, WARNING, find_leak_words, format_report, save_report, validate_cvs


def messages(result, level):
    return [f"{f.where}: {f.message}" for f in result.findings if f.level == level]


def rewrite(cfg, name, old, new):
    """Replace text in one CV file of the test project."""
    path = cfg.cv_dir / name
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_placeholder_cvs_pass_every_check(project):
    result = validate_cvs(project)
    assert result.findings == []
    assert (len(result.base_cv_ids), result.n_pairs) == (3, 9)


def test_the_report_shows_exactly_which_lines_differ(project):
    report = format_report(project, validate_cvs(project))
    assert "cv01_implicit (high vs low): OK" in report
    assert "high: Secondary school: St Aldhelm's College, an independent boarding school" in report
    assert "low: Secondary school: Northfield Academy, a state comprehensive school" in report
    assert "[education]" in report and "[interests]" in report
    assert "SUMMARY: 3 base CVs, 9 complete pairs, 0 error(s), 0 warning(s)." in report
    path = save_report(project, report)
    assert path == project.results_dir / "cv_validation.txt"
    assert path.read_text(encoding="utf-8") == report


def test_a_difference_outside_the_allowed_sections_is_an_error(project):
    # A stray edit in the work-experience section of the low variant only.
    rewrite(project, "cv02_implicit_low.txt", "cash-flow forecast", "cash flow forecast")
    errors = messages(validate_cvs(project), ERROR)
    assert len(errors) == 1
    assert errors[0].startswith("cv02_implicit: differs outside the allowed sections [education, interests]")
    assert "work experience" in errors[0]


def test_a_marker_in_the_wrong_arm_is_an_error(project):
    # The explicit arm may only differ in the monitoring box, not in the school line.
    rewrite(project, "cv01_explicit_low.txt", "Riverside Sixth Form College", "Northfield Academy")
    assert any(m.startswith("cv01_explicit: differs outside") for m in messages(validate_cvs(project), ERROR))


def test_identical_variants_are_an_error(project):
    (project.cv_dir / "cv03_demographic_b.txt").write_text(
        (project.cv_dir / "cv03_demographic_a.txt").read_text(encoding="utf-8"), encoding="utf-8")
    assert "cv03_demographic: the two variants are identical, so the marker is missing" in messages(
        validate_cvs(project), ERROR)


def test_different_section_headings_are_an_error(project):
    rewrite(project, "cv01_implicit_low.txt", "\nInterests\n", "\nHobbies\n")
    errors = messages(validate_cvs(project), ERROR)
    assert any("different section headings" in m for m in errors)


def test_an_invisible_difference_in_the_final_line_break_is_an_error(project):
    path = project.cv_dir / "cv02_demographic_b.txt"
    path.write_text(dummy_cv_text(2, "demographic", 0).rstrip("\n"), encoding="utf-8")
    errors = messages(validate_cvs(project), ERROR)
    assert "cv02_demographic: the variants differ only in invisible line endings or the final line break" in errors


def test_whitespace_differences_are_shown_with_repr(project):
    rewrite(project, "cv01_implicit_low.txt", "basic Python", "basic Python")  # non-breaking space
    result = validate_cvs(project)
    assert any(m.startswith("cv01_implicit: differs outside") for m in messages(result, ERROR))
    assert "changed: ' ' -> '\\xa0'" in format_report(project, result)


def test_a_byte_order_mark_does_not_count_as_a_difference(project):
    path = project.cv_dir / "cv01_implicit_high.txt"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())  # as saved by some Windows editors
    assert read_cv(path) == dummy_cv_text(1, "implicit", 0)
    assert messages(validate_cvs(project), ERROR) == []


def test_missing_and_misnamed_files_are_reported(project):
    (project.cv_dir / "cv02_explicit_low.txt").rename(project.cv_dir / "cv02_explict_low.txt")
    (project.cv_dir / "cv03_implicit_high.txt").rename(project.cv_dir / "cv03_implicit_High.txt")
    (project.cv_dir / "notes.docx").write_text("not a CV", encoding="utf-8")
    result = validate_cvs(project)
    errors = messages(result, ERROR)
    assert "cv02_explict_low.txt: misnamed: unknown arm 'explict' (did you mean 'explicit'?)" in errors
    assert "cv03_implicit_High.txt: misnamed: unknown variant 'High' for arm 'implicit' (did you mean 'high'?)" in errors
    assert "cv02: missing cv02_explicit_low.txt" in errors
    assert "cv03: missing cv03_implicit_high.txt" in errors
    assert "notes.docx: ignored: CV files must end in .txt" in messages(result, WARNING)


def test_the_number_of_base_cvs_is_checked(project):
    for path in project.cv_dir.glob("cv03_*.txt"):
        path.unlink()
    assert any("found 2 base CVs, but the study design has 3" in m for m in messages(validate_cvs(project), ERROR))


def test_empty_and_non_utf8_files_are_errors(project):
    (project.cv_dir / "cv01_implicit_low.txt").write_text("  \n", encoding="utf-8")
    (project.cv_dir / "cv01_explicit_low.txt").write_bytes("Café".encode("latin-1"))
    errors = messages(validate_cvs(project), ERROR)
    assert "cv01_implicit_low.txt: the file is empty" in errors
    assert any(m.startswith("cv01_explicit_low.txt: cv01_explicit_low.txt is not saved as UTF-8") for m in errors)


def test_a_big_length_difference_is_a_warning(project):
    rewrite(project, "cv01_implicit_low.txt", "Five-a-side football, gaming and volunteering at a food bank",
            "Five-a-side football, gaming, volunteering at a food bank, coaching an under-12s team on "
            "Saturday mornings and organising charity quiz nights at the local community centre")
    warnings = messages(validate_cvs(project), WARNING)
    assert len(warnings) == 1 and warnings[0].startswith("cv01_implicit: the variants differ in length by")


def test_words_that_could_leak_the_condition_are_warnings(project):
    rewrite(project, "cv01_implicit_high.txt", "Organised, numerate", "Organised, highly numerate, high achiever")
    rewrite(project, "cv02_explicit_low.txt", "Available on request.", "Available on request (explicit consent given).")
    warnings = messages(validate_cvs(project), WARNING)
    assert "cv01_implicit_high.txt: contains 'high' (line 6), which could give the condition away" in warnings
    assert any(w.startswith("cv02_explicit_low.txt: contains 'explicit'") for w in warnings)
    assert not any("highly" in w for w in warnings)  # whole words only


def test_leak_words_are_matched_as_whole_words_ignoring_capitals():
    text = "High standards\nlowest cost\nfollow-up\nLOW risk, low cost"
    assert find_leak_words(text, ["high", "low"]) == {"high": [1], "low": [4]}


@pytest.mark.parametrize("old, new, message", [
    ("demographic: [header]", "demographic: [Hobbies]", "not one of cv_checks.section_headings"),
    ("    demographic: [header]\n", "", "missing demographic"),
    ("expected_base_cvs: 3", "expected_base_cvs: 0", "expected_base_cvs"),
    ("max_length_difference_pct: 3", "max_length_difference_pct: -1", "max_length_difference_pct"),
    ("leak_words: [high, low, variant]", "leak_words: high", "leak_words"),
    ("section_headings: [Personal Profile,", "section_headings: [Header, Personal Profile,", "reserved|can't be a heading"),
])
def test_bad_cv_check_settings_are_rejected(make_config, old, new, message):
    from pipeline.config import ConfigError, load_config
    with pytest.raises(ConfigError, match=message):
        load_config(make_config({old: new}))


def test_dummy_cvs_only_support_the_three_study_arms(tmp_path):
    from pipeline.cvs import make_dummy_cvs
    with pytest.raises(ValueError, match="only knows the arms"):
        make_dummy_cvs(tmp_path, {"implicit": ("high", "low"), "extra": ("a", "b")}, n_cvs=1)
    assert cv_path(tmp_path, "cv01", "implicit", "high").exists() is False

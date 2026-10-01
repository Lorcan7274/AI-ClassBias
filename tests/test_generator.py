"""The CV generator in generator/: the real sheets must render, and every pair must
differ only where it is meant to. Runs in a temporary folder, so generator/out/ and
cvs/ are never touched."""

import shutil
import sys
from pathlib import Path

import pytest

GENERATOR_DIR = Path(__file__).resolve().parent.parent / "generator"
sys.path.insert(0, str(GENERATOR_DIR))

render = pytest.importorskip("render")  # needs jinja2


@pytest.fixture
def generator_copy(tmp_path):
    for name in ("base_cvs.csv", "markers.csv", "cv_template.txt", "form_template.txt"):
        shutil.copy(GENERATOR_DIR / name, tmp_path / name)
    return tmp_path


def test_real_sheets_render_and_pass_the_diff_check(generator_copy):
    out_dir, cv_dir = generator_copy / "out", generator_copy / "cvs"
    rendered, problems = render.build(generator_copy, out_dir, cv_dir, quiet=True)
    assert problems == []
    assert len(rendered) == 15
    assert len(list(out_dir.glob("B??_v?.txt"))) == 90
    assert len(list(out_dir.glob("B??_v?_form.txt"))) == 30
    assert len(list(cv_dir.glob("*.txt"))) == 90
    assert not any("[" in p.read_text(encoding="utf-8") for p in out_dir.glob("*.txt"))


def test_explicit_versions_share_one_cv_and_differ_only_on_the_form(generator_copy):
    rendered, _ = render.build(generator_copy, generator_copy / "out", None, quiet=True)
    for versions in rendered.values():
        assert versions["v3"]["cv"] == versions["v4"]["cv"]
        form_diff = [(a, b) for a, b in zip(versions["v3"]["form"].splitlines(),
                                            versions["v4"]["form"].splitlines()) if a != b]
        assert len(form_diff) == 3  # occupation, school type and free school meals


def test_pipeline_copy_of_the_explicit_arm_carries_the_form_as_its_own_section(generator_copy):
    cv_dir = generator_copy / "cvs"
    render.build(generator_copy, generator_copy / "out", cv_dir, quiet=True)
    high = (cv_dir / "B01_explicit_high.txt").read_text(encoding="utf-8")
    low = (cv_dir / "B01_explicit_low.txt").read_text(encoding="utf-8")
    assert "\nEqual Opportunities Monitoring\n" in high
    assert high.split("Equal Opportunities Monitoring")[0] == low.split("Equal Opportunities Monitoring")[0]


def test_a_placeholder_left_in_a_sheet_fails_the_diff_check(generator_copy):
    markers = generator_copy / "markers.csv"
    markers.write_text(markers.read_text(encoding="utf-8").replace("Hugo Pemberton", "[name]"), encoding="utf-8")
    _, problems = render.build(generator_copy, generator_copy / "out", None, quiet=True)
    assert any("square bracket" in p for p in problems)


def test_a_marker_that_does_not_differ_is_reported(generator_copy):
    markers = generator_copy / "markers.csv"
    text = markers.read_text(encoding="utf-8")
    # Give B01 the same interests in both implicit versions.
    text = text.replace("Five-a-side football, guitar (self-taught), gaming",
                        "Rowing (school first VIII), violin (Grade 8), skiing", 1)
    markers.write_text(text, encoding="utf-8")
    _, problems = render.build(generator_copy, generator_copy / "out", None, quiet=True)
    assert any("interests line is the same" in p for p in problems)

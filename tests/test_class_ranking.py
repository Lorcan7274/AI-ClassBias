"""class_ranking.csv must describe every marker value in the stimulus set, once each.

The sheet is what a reader consults to see which class level each descriptor was
assigned. A value missing from it is a coding decision nobody recorded; a value
listed twice is two decisions that may disagree. Both are caught here.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

STIMULUS = Path(__file__).resolve().parent.parent / "stimulus"
SCRIPT = STIMULUS / "make_class_ranking.py"
MARKERS = STIMULUS / "markers.csv"
RANKING = STIMULUS / "class_ranking.csv"

pytestmark = pytest.mark.skipif(not MARKERS.exists(),
                                reason="the stimulus set is not present")

MARKER_TYPES = {"school", "first_name", "surname", "interests", "award", "parent_job"}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def expected_pairs():
    """Every (marker_type, value) the stimulus set actually uses."""
    pairs = set()
    for row in read(MARKERS):
        first, *rest = row["name"].split()
        pairs.add(("first_name", first))
        pairs.add(("surname", " ".join(rest)))
        pairs.add(("school", row["school"]))
        pairs.add(("award", row["award"]))
        pairs.add(("interests", row["interests"]))
        if row["parent_job"]:
            pairs.add(("parent_job", row["parent_job"]))
    return pairs


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Run the generator into a temporary file, so the test covers the script."""
    out = tmp_path_factory.mktemp("ranking") / "class_ranking.csv"
    result = subprocess.run([sys.executable, str(SCRIPT), "--out", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"generator failed:\n{result.stderr}"
    return read(out)


def test_every_marker_value_appears_exactly_once(generated):
    produced = [(r["marker_type"], r["value"]) for r in generated]
    counts = {}
    for pair in produced:
        counts[pair] = counts.get(pair, 0) + 1

    duplicated = sorted(pair for pair, n in counts.items() if n > 1)
    assert not duplicated, f"listed more than once: {duplicated}"

    expected = expected_pairs()
    missing = sorted(expected - set(produced))
    assert not missing, f"used in markers.csv but not described: {missing}"

    extra = sorted(set(produced) - expected)
    assert not extra, f"described but not used in markers.csv: {extra}"


def test_columns_and_vocabularies(generated):
    assert list(generated[0]) == ["marker_type", "value", "class_level",
                                 "nssec_class", "justification"]
    for row in generated:
        assert row["marker_type"] in MARKER_TYPES, row
        assert row["class_level"] in {"high", "low", "neutral"}, row
        assert row["justification"].strip(), f"no justification: {row}"


def test_nssec_is_set_for_parent_jobs_only(generated):
    for row in generated:
        if row["marker_type"] == "parent_job":
            assert row["nssec_class"], f"parent_job without an NS-SEC class: {row}"
            assert row["nssec_class"] in {"1", "2", "3", "4", "5", "6", "7"}, row
        else:
            assert row["nssec_class"] == "", f"NS-SEC class set on a non-job row: {row}"


def test_low_parent_jobs_are_not_all_the_same_class(generated):
    """The brief drew the low jobs from NS-SEC 6 and 7, so flattening them all to
    one class would misstate the design."""
    classes = {r["nssec_class"] for r in generated
               if r["marker_type"] == "parent_job" and r["class_level"] == "low"}
    assert classes == {"6", "7"}, f"expected both 6 and 7 among the low jobs, got {classes}"


def test_high_parent_jobs_are_class_one(generated):
    classes = {r["nssec_class"] for r in generated
               if r["marker_type"] == "parent_job" and r["class_level"] == "high"}
    assert classes == {"1"}, f"expected every high job at NS-SEC 1, got {classes}"


def test_committed_file_is_up_to_date():
    """Guards against the sheet drifting from markers.csv after an edit."""
    result = subprocess.run([sys.executable, str(SCRIPT), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{RANKING.name} is stale; run `python make_class_ranking.py`\n{result.stderr}")

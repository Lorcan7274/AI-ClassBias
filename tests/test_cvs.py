import pytest

from pipeline.cvs import cv_path, load_pairs, make_dummy_cvs, placeholder_pairs

ARMS = {"implicit": ("high", "low"), "explicit": ("high", "low"), "demographic": ("a", "b")}


def write_cv(folder, cv_id, arm, variant, text=None):
    path = cv_path(folder, cv_id, arm, variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or f"CV text for {cv_id} {arm} {variant}", encoding="utf-8")


def test_only_complete_pairs_are_used(tmp_path):
    for arm, variants in ARMS.items():
        for v in variants:
            write_cv(tmp_path, "cv01", arm, v)
            if (arm, v) != ("explicit", "low"):
                write_cv(tmp_path, "cv02", arm, v)
    pairs, missing = load_pairs(tmp_path, ARMS)
    assert sorted(p.pair_id for p in pairs) == [
        "cv01_demographic", "cv01_explicit", "cv01_implicit", "cv02_demographic", "cv02_implicit"]
    assert missing == ["cv02_explicit"]


def test_x_is_the_first_variant_listed_in_the_config(tmp_path):
    write_cv(tmp_path, "cv01", "implicit", "high", "HIGH-CLASS CV")
    write_cv(tmp_path, "cv01", "implicit", "low", "LOW-CLASS CV")
    pairs, _ = load_pairs(tmp_path, {"implicit": ("high", "low")})
    assert len(pairs) == 1
    p = pairs[0]
    assert (p.x_variant, p.x_text, p.y_variant, p.y_text) == ("high", "HIGH-CLASS CV", "low", "LOW-CLASS CV")


def test_dummy_cvs_never_overwrite_existing_files_by_accident(tmp_path):
    folder = tmp_path / "cvs"
    assert len(make_dummy_cvs(folder, ARMS, n_cvs=2)) == 12
    real_cv = folder / "cv01_implicit_high.txt"
    real_cv.write_text("a real CV", encoding="utf-8")
    with pytest.raises(FileExistsError):
        make_dummy_cvs(folder, ARMS, n_cvs=2)
    assert real_cv.read_text(encoding="utf-8") == "a real CV"
    make_dummy_cvs(folder, ARMS, n_cvs=2, overwrite=True)
    assert "PLACEHOLDER" in real_cv.read_text(encoding="utf-8")


def test_dummy_cvs_are_not_mixed_into_a_folder_of_other_cvs(tmp_path):
    folder = tmp_path / "cvs"
    write_cv(folder, "alice", "implicit", "high")
    with pytest.raises(FileExistsError):
        make_dummy_cvs(folder, ARMS, n_cvs=2)
    assert [p.name for p in folder.iterdir()] == ["alice_implicit_high.txt"]


def test_dummy_cvs_are_recognised_as_placeholders(tmp_path):
    make_dummy_cvs(tmp_path, ARMS, n_cvs=1)
    write_cv(tmp_path, "cv02", "implicit", "high", "real text")
    write_cv(tmp_path, "cv02", "implicit", "low", "real text too")
    pairs, _ = load_pairs(tmp_path, ARMS)
    assert placeholder_pairs(pairs) == ["cv01_implicit", "cv01_explicit", "cv01_demographic"]

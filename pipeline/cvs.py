"""CV files: finding them, pairing them up, and writing placeholder CVs for testing.

CV files live in cvs/ and are named <cv_id>_<arm>_<variant>.txt, for example
cv01_implicit_high.txt. Each base CV gives one pair per arm, so 15 base CVs and
3 arms give 45 pairs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Pair:
    pair_id: str     # e.g. "cv01_implicit"
    cv_id: str       # e.g. "cv01"
    arm: str         # e.g. "implicit"
    x_variant: str   # first variant listed for this arm in config.yaml (class arms: high)
    x_text: str
    y_variant: str   # second variant (class arms: low)
    y_text: str


def cv_path(cv_dir, cv_id, arm, variant) -> Path:
    return Path(cv_dir) / f"{cv_id}_{arm}_{variant}.txt"


def find_cv_ids(cv_dir, arms) -> list[str]:
    """Base CV ids (the part before _<arm>_) of every .txt file named after a known arm."""
    pattern = re.compile(r"^(.+?)_(" + "|".join(re.escape(a) for a in arms) + r")_")
    ids = set()
    for path in Path(cv_dir).glob("*.txt"):
        match = pattern.match(path.stem)
        if match:
            ids.add(match.group(1))
    return sorted(ids)


def load_pairs(cv_dir, arms):
    """Build every (base CV, arm) pair whose two variant files both exist.

    Returns (pairs, missing): `missing` lists the pair ids with a file missing.
    """
    pairs, missing = [], []
    for cv_id in find_cv_ids(cv_dir, arms):
        for arm, (vx, vy) in arms.items():
            x_file, y_file = cv_path(cv_dir, cv_id, arm, vx), cv_path(cv_dir, cv_id, arm, vy)
            if x_file.exists() and y_file.exists():
                pairs.append(Pair(
                    pair_id=f"{cv_id}_{arm}", cv_id=cv_id, arm=arm,
                    x_variant=vx, x_text=x_file.read_text(encoding="utf-8"),
                    y_variant=vy, y_text=y_file.read_text(encoding="utf-8"),
                ))
            else:
                missing.append(f"{cv_id}_{arm}")
    return pairs, missing


def placeholder_pairs(pairs) -> list[str]:
    """Pair ids whose CV text still contains the word PLACEHOLDER (i.e. dummy CVs)."""
    return [p.pair_id for p in pairs if "PLACEHOLDER" in p.x_text or "PLACEHOLDER" in p.y_text]


def make_dummy_cvs(cv_dir, arms, n_cvs=15, overwrite=False) -> list[Path]:
    """Write placeholder CVs so the pipeline can be tested before the real CVs exist.

    Refuses to write into a folder that already holds .txt files unless
    overwrite=True, so placeholders can never replace or mix with real CVs by
    accident. Returns the paths written.
    """
    cv_dir = Path(cv_dir)
    existing = sorted(cv_dir.glob("*.txt")) if cv_dir.exists() else []
    if existing and not overwrite:
        raise FileExistsError(
            f"{cv_dir} already holds {len(existing)} .txt file(s), e.g. {existing[0].name}. "
            "Nothing was written. Use --overwrite only if those are placeholders you want to replace.")
    cv_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i in range(1, n_cvs + 1):
        cv_id = f"cv{i:02d}"
        for arm, variants in arms.items():
            for v in variants:
                path = cv_path(cv_dir, cv_id, arm, v)
                path.write_text(
                    f"PLACEHOLDER CV {i:02d}\nPersonal profile: ...\nEducation: ...\n"
                    f"Experience: ...\nSkills and interests: ...\n[{arm}/{v} marker goes here]\n",
                    encoding="utf-8",
                )
                written.append(path)
    return written

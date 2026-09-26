"""CV files: reading them, pairing them up, and writing placeholder CVs for testing.

CV files live in cvs/ and are named <cv_id>_<arm>_<variant>.txt, for example
cv01_implicit_high.txt. Each base CV gives one pair per arm, so 15 base CVs and
3 arms give 45 pairs.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path


class CVFileError(Exception):
    """A CV file that can't be read as text."""


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


def read_cv(path) -> str:
    """The text of one CV file, exactly as it will be shown to the model.

    "utf-8-sig" skips the invisible byte-order mark that some Windows editors put at
    the start of a file, so that mark can't make two variants differ.
    """
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise CVFileError(f"{Path(path).name} is not saved as UTF-8 text; re-save it as plain UTF-8 text") from None


def parse_cv_name(stem, arms):
    """Split a file name (without .txt) into (cv_id, arm, variant).

    Raises ValueError with a helpful message if the name doesn't fit the pattern.
    Arm and variant names can't contain "_" (config.yaml checks that), so the name is
    split at its last two underscores and the cv_id may itself contain underscores.
    """
    parts = stem.rsplit("_", 2)
    if len(parts) != 3 or not all(parts):
        raise ValueError("the name should look like <cv_id>_<arm>_<variant>.txt, e.g. cv01_implicit_high.txt")
    cv_id, arm, variant = parts
    if arm not in arms:
        raise ValueError(f"unknown arm '{arm}'{_did_you_mean(arm, arms)}")
    if variant not in arms[arm]:
        raise ValueError(f"unknown variant '{variant}' for arm '{arm}'{_did_you_mean(variant, arms[arm])}")
    return cv_id, arm, variant


def _did_you_mean(word, options):
    close = difflib.get_close_matches(word, list(options), n=1)
    return f" (did you mean '{close[0]}'?)" if close else ""


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
                    x_variant=vx, x_text=read_cv(x_file),
                    y_variant=vy, y_text=read_cv(y_file),
                ))
            else:
                missing.append(f"{cv_id}_{arm}")
    return pairs, missing


def placeholder_pairs(pairs) -> list[str]:
    """Pair ids whose CV text still contains the word PLACEHOLDER (i.e. dummy CVs)."""
    return [p.pair_id for p in pairs if "PLACEHOLDER" in p.x_text or "PLACEHOLDER" in p.y_text]


# ----------------------------- placeholder CVs -----------------------------

# Each dummy base CV takes its surname, degree, university and job from these lists,
# so the 15 dummies are not all the same.
SURNAMES = ["Morgan", "Hughes", "Reid", "Clarke", "Walsh", "Price", "Doyle", "Shaw",
            "Evans", "Hart", "Lloyd", "Mills", "Wood", "Hall", "Ward"]
DEGREES = ["BSc Economics", "BSc Accounting and Finance", "BA Economics and Politics",
           "BSc Mathematics with Economics", "BSc Business Management"]
UNIVERSITIES = ["University of Leeds", "University of Bristol", "University of Nottingham",
                "University of Glasgow", "University of Exeter"]
JOBS = ["Summer intern, regional accountancy practice", "Finance assistant (part-time), housing association",
        "Spring week, commercial bank", "Audit intern, mid-size accountancy firm", "Treasury intern, logistics company"]

# The markers that make the two variants of a pair different. Index 0 is used for the
# first variant of an arm in config.yaml (high, a) and index 1 for the second (low, b).
# Every other line is the same in both variants, so the dummies pass validate-cvs.
FIRST_NAMES = ["Alex", "Sam"]  # demographic arm: only the name (and email) changes
SCHOOLS = ["Secondary school: St Aldhelm's College, an independent boarding school",
           "Secondary school: Northfield Academy, a state comprehensive school"]
INTERESTS = ["Sailing, skiing and playing the cello in a chamber orchestra",
             "Five-a-side football, gaming and volunteering at a food bank"]
MONITORING = [
    ["Main household earner's job when you were 14: Senior manager or professional",
     "Type of school attended at 11 to 16: Independent or fee-paying",
     "Eligible for free school meals: No"],
    ["Main household earner's job when you were 14: Routine manual work, such as a cleaner",
     "Type of school attended at 11 to 16: State-funded, non-selective",
     "Eligible for free school meals: Yes"],
]
# Used where an arm doesn't vary a field, so those lines carry no class signal.
NEUTRAL_SCHOOL = "Secondary school: Riverside Sixth Form College"
NEUTRAL_INTERESTS = "Running, reading and cooking"
DUMMY_ARMS = ("implicit", "explicit", "demographic")


def dummy_cv_text(i, arm, variant_index) -> str:
    """Placeholder CV number i for one arm and variant (0 = first, 1 = second)."""
    first_name = FIRST_NAMES[variant_index] if arm == "demographic" else FIRST_NAMES[0]
    school = SCHOOLS[variant_index] if arm == "implicit" else NEUTRAL_SCHOOL
    interests = INTERESTS[variant_index] if arm == "implicit" else NEUTRAL_INTERESTS
    surname = SURNAMES[(i - 1) % len(SURNAMES)]
    lines = [
        f"PLACEHOLDER CV {i:02d}: replace with a real CV before a real run",
        f"{first_name} {surname}",
        f"{first_name.lower()}.{surname.lower()}@example.com | London",
        "",
        "Personal Profile",
        "Recent graduate looking to start a career in finance. Organised, numerate and",
        "comfortable working to deadlines, with experience of month-end reporting.",
        "",
        "Education",
        f"{DEGREES[(i - 1) % len(DEGREES)]}, {UNIVERSITIES[(i - 1) % len(UNIVERSITIES)]} (2022 to 2025), grade 2:1",
        school,
        "A-levels: Mathematics (A), Economics (A), History (B)",
        "",
        "Work Experience",
        f"{JOBS[(i - 1) % len(JOBS)]} (June to August 2024)",
        "Prepared monthly reconciliations and helped build a cash-flow forecast in Excel.",
        "",
        "Skills",
        "Excel (pivot tables, lookups), basic Python, financial modelling",
        "",
        "Interests",
        interests,
        "",
    ]
    if arm == "explicit":
        lines += ["Equal Opportunities Monitoring"] + MONITORING[variant_index] + [""]
    lines += ["References", "Available on request."]
    return "\n".join(lines) + "\n"


def make_dummy_cvs(cv_dir, arms, n_cvs=15, overwrite=False) -> list[Path]:
    """Write placeholder CVs so the pipeline can be tested before the real CVs exist.

    Each pair differs only in its arm's marker, in the section config.yaml allows for
    that arm. Refuses to write into a folder that already holds .txt files unless
    overwrite=True, so placeholders can never replace or mix with real CVs by
    accident. Returns the paths written.
    """
    if sorted(arms) != sorted(DUMMY_ARMS):
        raise ValueError(f"make-dummy-cvs only knows the arms {', '.join(DUMMY_ARMS)}")
    cv_dir = Path(cv_dir)
    existing = sorted(cv_dir.glob("*.txt")) if cv_dir.exists() else []
    if existing and not overwrite:
        raise FileExistsError(
            f"{cv_dir} already holds {len(existing)} .txt file(s), e.g. {existing[0].name}. "
            "Nothing was written. Use --overwrite only if those are placeholders you want to replace.")
    cv_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i in range(1, n_cvs + 1):
        for arm, variants in arms.items():
            for index, variant in enumerate(variants):
                path = cv_path(cv_dir, f"cv{i:02d}", arm, variant)
                path.write_text(dummy_cv_text(i, arm, index), encoding="utf-8")
                written.append(path)
    return written

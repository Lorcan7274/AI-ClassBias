"""Copy the rendered stimulus set into the pipeline's cvs/ folder.

    python install_to_pipeline.py [--cv-dir ../cvs]

The pipeline sends one block of text per candidate, named
<cv_id>_<arm>_<variant>.txt, so this step renames the versions and, for the
explicit arm, appends the monitoring form to the CV.

That append is the point of the script. The explicit arm's two CVs are
deliberately identical -- the class signal is in the form alone -- so without the
form the pipeline would show the model two identical candidates, and validate-cvs
would (correctly) report the marker as missing.

The form arrives as its own section, "Equal Opportunities Monitoring", which is
the only section config.yaml lets the explicit arm differ in.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"


def install(cv_dir: Path) -> dict:
    with (OUT / "manifest.csv").open(encoding="utf-8-sig", newline="") as fh:
        manifest = list(csv.DictReader(fh))
    if not manifest:
        raise SystemExit("out/manifest.csv is empty -- run render.py first")

    cv_dir.mkdir(parents=True, exist_ok=True)
    for stale in cv_dir.glob("*.txt"):
        stale.unlink()

    counts = {}
    for row in manifest:
        text = (OUT / row["cv_file"]).read_text(encoding="utf-8")
        if row["form_file"]:
            form = (OUT / row["form_file"]).read_text(encoding="utf-8")
            # One blank line between the CV and the form, and no trailing blank run.
            text = text.rstrip("\n") + "\n\n" + form.rstrip("\n") + "\n"
        (cv_dir / row["pipeline_file"]).write_text(text, encoding="utf-8")
        counts[row["arm"]] = counts.get(row["arm"], 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cv-dir", default=str(ROOT.parent / "cvs"),
                        help="where the pipeline reads CVs from (default: ../cvs)")
    args = parser.parse_args()

    cv_dir = Path(args.cv_dir).resolve()
    counts = install(cv_dir)
    total = sum(counts.values())
    detail = ", ".join(f"{n} {arm}" for arm, n in sorted(counts.items()))
    print(f"Installed {total} CVs into {cv_dir} ({detail})")
    print("Next: python -m pipeline validate-cvs")


if __name__ == "__main__":
    main()

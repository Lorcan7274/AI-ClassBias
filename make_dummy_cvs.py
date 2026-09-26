"""Creates placeholder CVs in cvs/ so you can test the pipeline before the real ones exist.
Delete cvs/ (or overwrite the files) once your real CVs are ready."""

from pathlib import Path
from run_pipeline import ARMS

N_CVS = 15
out = Path(__file__).parent / "cvs"
out.mkdir(exist_ok=True)

for i in range(1, N_CVS + 1):
    for arm, variants in ARMS.items():
        for v in variants:
            (out / f"cv{i:02d}_{arm}_{v}.txt").write_text(
                f"PLACEHOLDER CV {i:02d}\nPersonal profile: ...\nEducation: ...\n"
                f"Experience: ...\nSkills and interests: ...\n[{arm}/{v} marker goes here]\n",
                encoding="utf-8",
            )
print(f"Wrote {N_CVS * sum(len(v) for v in ARMS.values())} placeholder CVs to {out}")

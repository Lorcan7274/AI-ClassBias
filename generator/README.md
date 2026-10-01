# CV generator

Two spreadsheets in, six CVs per base out. Teammates only ever touch the spreadsheets.

This folder was built in October 2026 to the brief in `CLAUDE_CODE_PROMPT.md`. The scoring
pipeline in the parent folder (`python -m pipeline`) reads the CVs this folder writes.

## Files
- `base_cvs.csv` — one row per base CV. The content that is held constant across all six versions.
- `markers.csv` — one row per base CV. The values that get swapped in: schools, names, interests, awards, parents' jobs.
- `cv_template.txt` — the fixed CV layout (Jinja2). Edit only to change the CV structure.
- `form_template.txt` — the separate equal-opportunities monitoring form used by the explicit arm.
- `render.py` — reads the two sheets, writes `out/` and `../cvs/`, then checks every pair differs only in its intended fields.
- `make_pdf.py` — turns rendered CV text files into A4 PDFs, one page per CV.
- `class_ranking.csv` — the class level assigned to every marker value, with a one-line justification.
- `schools_verification.csv` — every school in `markers.csv` with its type, region and the source it was checked against.
- `REVIEW.md` — what the human team should check before scoring.
- `out/` — the rendered files (see below). `implicit_arm.pdf` and `neutral_cvs.pdf` are the PDF versions.

## Run
    pip install jinja2 reportlab
    python render.py
    python make_pdf.py out/*v1*.txt out/*v2*.txt -o implicit_arm.pdf
    python make_pdf.py out/*v3*.txt out/*v5*.txt out/*v6*.txt -o neutral_cvs.pdf

`render.py` must end with `Diff check: OK`. Anything else is printed and must be fixed before scoring.

## Sheet rules
- `base_id` must match between the two sheets (B01, B02, ...).
- Bullets in `job1_bullets` / `job2_bullets` are separated with `|`.
- Nothing in `base_cvs.csv` may carry a class signal: no school name, no hobbies, no awards, no postcode, no family. Those live in `markers.csv`.
- Both rows of each real school pair must be in the same town or county; neither nationally famous.
- `name_high` and `name_low` are both White British and the same gender. `name_neutral` and `name_bench_a` are White British and class-neutral; `name_bench_b` differs from `name_bench_a` only in ethnicity.
- Every cell must be filled. A `[placeholder]` left in a sheet shows up as a square bracket in the output and fails the diff check.

## What each version contains
| Version | School line | Name | Interests | Award | Monitoring form |
|---|---|---|---|---|---|
| v1 implicit high | school_high | name_high | interests_high | award_high | none |
| v2 implicit low | school_low | name_low | interests_low | award_low | none |
| v3 explicit high | not named | name_neutral | interests_neutral | award_neutral | separate form: parent_job_high, independent school |
| v4 explicit low | not named | name_neutral | interests_neutral | award_neutral | separate form: parent_job_low, state school |
| v5 benchmark a | not named | name_bench_a | interests_neutral | award_neutral | none |
| v6 benchmark b | not named | name_bench_b | interests_neutral | award_neutral | none |

Versions 3–6 don't name the school ("Secondary school, 2016–2023"), so the form's school type can
never contradict a real school the model recognises. All four omit it equally, so it is held constant.

For the explicit arm the monitoring section is a **separate file** (`..._form.txt`), mirroring a real
application form. Versions 3 and 4 share a byte-identical CV; only their form files differ, in the
parent's occupation and the school type. The two questions use the Social Mobility Commission's
recommended wording for employers.

The e-mail address is `first.surname@example.com` (a domain reserved for examples) and the phone
number is in Ofcom's drama range, so no version can point at a real person. Both are derived the
same way for every version, so only the name itself differs between them.

## Outputs of `render.py`
- `out/<base_id>_v1.txt` … `_v6.txt` — the 6 CV versions (90 files for 15 bases).
- `out/<base_id>_v3_form.txt`, `_v4_form.txt` — the monitoring forms (30 files).
- `out/manifest.csv` — one row per version: files, name, school, award, interests, form answers.
- `out/canva_bulk.csv` — one row per version, one column per Canva text box (see below).
- `../cvs/<base_id>_<arm>_<variant>.txt` — the same CVs named the way the scoring pipeline expects
  (`B01_implicit_high.txt`, `B01_explicit_low.txt`, `B01_demographic_a.txt`, ...). For the explicit arm the
  form is appended to the CV as an `Equal Opportunities Monitoring` section, which is the one section
  `config.yaml` lets that arm differ in. `../cvs/` is ignored by git; run `render.py` to recreate it.
  `--no-pipeline` skips these copies; `--pipeline-dir` changes where they go.

## Diff check
`render.py` ends with a line-by-line comparison of each pair:
- v1 vs v2 may differ only in the name line, the e-mail line, the school line, the awards line and the interests line, and must differ in all five;
- v3 and v4 must be byte-identical, and their forms may differ only in the two answers;
- v5 vs v6, and v3 vs v5, may differ only in the name and e-mail lines.
It also fails if any output still contains a square bracket (a `[placeholder]` left in a sheet), and
prints the length difference of each v1/v2 pair (the scoring pipeline warns above 3%).

After rendering, the scoring pipeline's own check runs the same kind of comparison on `../cvs/`:

    cd .. && python -m pipeline validate-cvs

## Canva (for the human survey)
`out/canva_bulk.csv` has one row per CV version and one column per text box
(Name, Contact, Profile, University, Modules, School, A-levels, GCSEs, Job1 heading, Job1 bullets,
Job2 heading, Job2 bullets, Skills, Award, Interests, Monitoring).

1. In Canva (Pro / Teams / Education, desktop), design one A4 CV with a text box for each column above.
2. Apps → Bulk Create → Upload data → `canva_bulk.csv`.
3. Right-click each text box → Connect data → pick the matching column.
4. Generate designs → "Individual designs" → export as PDF.
The Monitoring column is blank for versions without the form, so that text box just renders empty.
Filter the CSV to v1/v2 rows first if the survey only uses the implicit arm.

## Filling the sheets
`CLAUDE_CODE_PROMPT.md` is the task brief the sheets were filled to. Review the school pairs and
names (`REVIEW.md`, `schools_verification.csv`) before scoring — they are the manipulation.

# CV stimulus set — review record

Decisions, applied fixes and verification for the 15-base CV stimulus set.
Companion to `REVIEW_FEEDBACK.md`, the reviewer's note this round answers.

## How this folder works

Everything in `out/` and both PDFs are **generated**. The sources are:

| File | What it holds |
|---|---|
| `base_cvs.csv` | one 33-line body per base CV, with `{{name}}`, `{{email}}`, `{{phone}}`, `{{school_line}}`, `{{award}}` and `{{interests}}` where the versions differ |
| `markers.csv` | the values that vary, one row per (base, version) — 90 rows |
| `form_template.txt` | the equal-opportunities monitoring form |

`class_ranking.csv` and `schools_verification.csv` are generated from the above
by `make_class_ranking.py` and `verify_schools.py`.

```
python render.py              # rebuild out/ + both PDFs, then run the diff check
python install_to_pipeline.py # copy into ../cvs/ under the pipeline's naming
python -m pipeline validate-cvs
python verify_schools.py      # re-check all 30 schools against the DfE register
python make_class_ranking.py  # rebuild class_ranking.csv from markers.csv
```

Edit the sheets, never `out/`. `render.py` ends with `Diff check: OK` only when
every pair differs in exactly the lines its arm permits. **`render.py` alone does
not update `cvs/`** — run `install_to_pipeline.py` after it, or `validate-cvs`
will read the previous build.

### Provenance of these sheets

The previous delivery contained only `out/`; the sheets and `render.py` were
missing (reviewer's section 4). They were reconstructed from the delivered files,
gated on exact reproduction: before any fix was applied, `render.py` regenerated
all 120 text files **and** `manifest.csv` byte-for-byte identical to the
delivery. The sheets therefore carry no new content of their own.

## Fixes applied

| # | Fix | Where |
|---|---|---|
| 2.1 | Free-school-meals question added as the third question (v3 `No`, v4 `Yes`) | `form_template.txt`, new `free_school_meals` column |
| 2.2 | Monitoring disclaimer added, directly under the heading | `form_template.txt` |
| 2.3 | v4 school type → `State-run or state-funded school – non-selective` | `markers.csv` |
| 2.4 | `@example.com` → `@gmail.com`, all 90 CVs | `markers.csv` |
| 2.5 | High-side award reduced to one item in B05, B09, B13 | `markers.csv` |

**2.2 placement.** The instruction read "directly under the form heading, before
the questions". The disclaimer went immediately after the heading, satisfying
both halves; the "Section 6 …" scaffolding line now sits third.

**2.5 B13 — changed from the prescribed value, deliberately.** The review
prescribed `Head of House`, which is neither item of B13's old line
(`School Prize for Mathematics and Senior Prefect`) — it is the second item of
**B09's** old line, so the two look transposed. B13 now reads **`Senior Prefect`**,
for a reason better than the transposition: the high-side award should be
*status*-coded, not *ability*-coded. `School Prize for Mathematics` reads as
attainment beyond the identical A-levels, which is a productivity confound;
`Senior Prefect` is class-coded through the institution and says nothing about
ability. It is also B13's own item, and it clears the length warning the
prescribed value introduced (3.0% against a 3% limit; now 2.9%).

## School verification — all 30, against the DfE register

Source: **Get Information about Schools**, the statutory register
(`get-information-schools.service.gov.uk`). `verify_schools.py` downloads the
daily extract and matches every school, so `schools_verification.csv` carries a
URN and a `source_url` per row rather than an assertion. Columns include `urn`,
`establishment_type`, `gias_status`, `single_sex`, `local_authority`,
`la_selective`, `la_selective_share_pct` and `admissions_policy`.

**Result: 28 of 30 clean, 2 flagged, both benign.** All 30 exist, all are Open,
and every establishment type matches the role its CV plays — 15 independent
schools on the high side, 15 non-selective state schools on the low side.

The two flags are colloquial-name mismatches, not errors:

- **B09 high** — the CV writes `Bolton School`; GIAS registers two establishments,
  `Bolton School Boys' Division` (URN 105271) and the Girls' Division. Pinned to
  the Boys' Division, which matches the pair's male candidate. `Bolton School` is
  what a candidate would actually write.
- **B14 low** — the CV writes `City of Norwich School`; GIAS names the open record
  `City of Norwich School, An Ormiston Academy` (URN 141269). **The name alone
  matched a Closed record** (URN 121172, the pre-academy community school), so
  this is pinned to the open one. Worth noting: a bare name search would have
  verified a school that no longer exists.

### How "selective area" was decided

Not from a remembered list of grammar-school counties. The register gives each
state secondary's admissions policy, so the selective share of each authority is
counted directly: 35 of 152 authorities contain at least one selective state
secondary, which matches the known figure for England. Grammar schools in the
pair's own *town* are reported separately, since those are the ones that actually
cream off the local intake.

Three pairs sit in authorities with some selection, but **none has a grammar
school in its own town**, so their state schools are not secondary moderns:

| Pair | Authority | Selective share | Nearest grammars |
|---|---|---|---|
| B05 Warwick | Warwickshire | 12.8% (5/39) | Rugby, Alcester, Stratford — none in Warwick |
| B06 Harrogate | North Yorkshire | 7.3% (3/41) | Ripon, Skipton — none in Harrogate |
| B08 Ivybridge | Devon | 2.4% (1/41) | Colyton — ~40 miles |

## B03 replaced (optional item 3.1, now resolved)

Kent is confirmed from the register at **31.1% selective (32 of 103 state
secondaries), with 4 grammar schools in Maidstone itself**. The Maplesden Noakes
School therefore functioned as a secondary modern, a stronger class signal than
the other fourteen pairs — an asymmetry that would need defending in every
write-up. The pair was swapped:

| | Was | Now |
|---|---|---|
| high | Sutton Valence School, Sutton Valence, Kent | **Bloxham School, Banbury, Oxfordshire** (URN 123275) |
| low | The Maplesden Noakes School, Maidstone, Kent | **The Warriner School, Banbury, Oxfordshire** (URN 142218) |

**Oxfordshire has zero selective state secondaries** (0 of 41), so there is no
11-plus effect to correct for. The replacement is a closer match than the
original on every other axis: both schools are in the *same* town (the old pair
was two different Kent towns), both Mixed, neither nationally prominent, and the
type and scale line up — Bloxham is an 11–19 boarding independent of 583 pupils
against Sutton Valence's 826, and Warriner a non-selective 11–18 academy of 1,553
against Maplesden Noakes's 1,418.

## What rests on inference rather than the register

Everything above is read from GIAS except one thing: **candidate gender**, which
is inferred from first names and recorded in its own column
(`candidate_gender_inferred`). It is used only to check single-sex schools.
The set contains exactly three, and all three match:

| Pair | School | GIAS | Candidate |
|---|---|---|---|
| B02 high | Tormead School | Girls | Imogen Beaumont |
| B05 high | Warwick School | Boys | Henry Fairfax |
| B09 high | Bolton School Boys' Division | Boys | Oliver Montague |

The other 27 schools are Mixed, so no gender inference bears on them.

**One discrepancy with the review:** its section 1 reports the 15 pairs as
"8 male, 7 female". Counting the names gives **7 male, 8 female** (female pairs:
B02, B04, B06, B08, B10, B12, B14, B15). Nothing depends on the split, but the
review's figure appears to be off by one.

## `class_ranking.csv` — now generated, and one correction

Previously hand-written by an earlier session against Part 3 of the stimulus
brief, which is why nothing in the delivery recorded how it was made. It is now
produced by `make_class_ranking.py` from `markers.csv`: 267 rows, one per
distinct marker value, with the justifications held in dicts in the script so
the reasoning sits beside the coding.

| marker_type | rows |
|---|---|
| school | 31 |
| first_name | 75 |
| surname | 75 |
| interests | 45 |
| award | 20 |
| parent_job | 21 |

**NS-SEC correction applied.** The low parent jobs are classified individually
rather than all set to 7, which the brief's own sourcing requires: it drew them
from classes 6 and 7. Five are semi-routine (class 6: care assistant,
supermarket cashier, security guard, kitchen assistant, catering assistant) and
seven are routine (class 7: warehouse operative, packer, labourer, cleaner,
hospital porter, bus driver, delivery driver). A test asserts both classes are
present, so a future edit cannot quietly flatten them again.

School rows take their justification from `schools_verification.csv`, so each
cites the establishment type the DfE register records plus the URN, rather than
an assertion. Interests rows are composed from the individually coded activities
actually present in the value.

**Scope.** The six marker types the brief defines. `school_type` and
`free_school_meals` are the explicit arm's instrument rather than descriptors in
this taxonomy — their class level is carried by `parent_job` — and `email` and
`phone` are derived from the name or constant, so none appear.

**Two of the 267 justifications are weaker than the rest and say so in the sheet
itself:** `first_name` and `surname` rows (150 of the 267) are coded on British
class connotation and are not validated against a name-SES dataset. Every one of
those rows carries that caveat in its `justification`, so a reader cannot mistake
them for the sourced school and NS-SEC rows.

## The rule for award coding

> **High-side awards are merit-based (scholarships, school offices); subject-specific
> prizes are excluded because they signal a competence beyond the identical
> qualifications. Low-side awards are need-based or widening-participation.**

The principle is deliberately narrower than "no ability signal on the high side",
which would be the wrong rule: the academic scholarships on B01, B02, B06, B08,
B11 and B12 are ability-coded, and so are the Sutton Trust and Social Mobility
Foundation programmes on the low side, which also select on attainment. The
scholarship-versus-bursary contrast is the canonical one — Rivera and Tilcsik's
award versus award-for-financial-aid — so it stays.

What the rule excludes is only the subject-specific prize: "School Prize for
Mathematics" claims a particular competence beyond the A-levels that are
identical across the pair, which is a productivity confound rather than a class
signal. Two awards were changed under it:

| | Was | Now |
|---|---|---|
| B09 high | School Prize for Mathematics | **Head of House** |
| B13 high | School Prize for Mathematics and Senior Prefect | **Senior Prefect** |

No base now carries a subject-specific prize on the high side. The high-side set
is three academic scholarships and two school offices; the low-side set is two
need-based bursaries and three widening-participation programmes.
`make_class_ranking.py` keeps the excluded value in its `AWARDS` dict, marked
`EXCLUDED`, so the rule stays legible to the next reader.

### One consequence, not yet resolved

B09's low-side award is the longest in the set (`Social Mobility Foundation
Aspiring Professionals Programme`, 59 characters) and `Head of House` is the
shortest high-side one (13), so the pair now differs in length by **3.3%
(1318 vs 1363 characters) against the 3% limit** — `validate-cvs` warns, which
does not block a run. The same thing happened to B13 and was resolved there by a
longer award. Three ways out, none chosen:

- accept 3.3%, on the grounds that the coding rule matters more than the margin;
- give B09 a longer status-coded award — `Sixth Form Academic Scholarship`
  (31 characters) brings the pair to 2.0% and stays inside the rule, since
  scholarships are permitted;
- shorten B09's low-side award, which would break the five-programme cycle used
  across the other bases.

## Change outside this folder

`config.yaml` → `cv_checks.allowed_sections.implicit` gained `header`.

The implicit arm varies the candidate's name, and the email derived from it, as a
class signal in its own right (`Hugo Pemberton` / `Connor Smith`). The name sits
above the first heading, so it falls in the `header` section, which the arm
previously did not permit — `validate-cvs` reported all 15 implicit pairs as
errors on that ground alone. The reviewer's section 1 confirms the per-pair names
as intended design, so the setting was widened rather than the names removed.

## Verification, this round

`render.py` → `Diff check: OK`. All seven of the reviewer's section-5 checks pass:
30 forms carry both new lines exactly once, no `example.com` remains, v3/v4 are
identical in all 15 bases, B05/B09/B13 high awards are single-item, and the PDFs
are 30 and 45 pages. `verify_schools.py` → 30 schools, 28 clean, 2 naming notes.
`python -m pipeline validate-cvs` → 15 base CVs, 45 complete pairs,
**0 errors, 0 warnings**. Full dry run completes; `python -m pytest` → 124 passed.

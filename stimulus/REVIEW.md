# CV stimulus set — review record

Decisions, applied fixes and open questions for the 15-base CV stimulus set.
Companion to `REVIEW_FEEDBACK.md` (the reviewer's note this round answers).

## How this folder works

Everything in `out/` and both PDFs are **generated**. The sources are:

| File | What it holds |
|---|---|
| `base_cvs.csv` | one 33-line body per base CV, with `{{name}}`, `{{email}}`, `{{phone}}`, `{{school_line}}`, `{{award}}`, `{{interests}}` where the versions differ |
| `markers.csv` | the values that vary, one row per (base, version) — 90 rows |
| `form_template.txt` | the equal-opportunities monitoring form |

```
python render.py              # rebuild out/ + both PDFs, then run the diff check
python install_to_pipeline.py # copy into ../cvs/ under the pipeline's naming
python -m pipeline validate-cvs
```

Edit the sheets, never `out/`. `render.py` ends with `Diff check: OK` only when every
pair differs in exactly the lines its arm permits.

### Provenance of these sheets

The previous delivery contained only `out/`; the sheets and `render.py` were missing
(reviewer's section 4). They were reconstructed from the delivered files, and the
reconstruction was gated on exact reproduction: before any fix was applied, `render.py`
regenerated all 120 text files **and** `manifest.csv` byte-for-byte identical to the
delivery. The sheets therefore carry no new content of their own.

## Fixes applied this round

| # | Fix | Where |
|---|---|---|
| 2.1 | Free-school-meals question added as the third question (v3 `No`, v4 `Yes`) | `form_template.txt`, new `free_school_meals` column in `markers.csv` |
| 2.2 | Monitoring disclaimer added | `form_template.txt` |
| 2.3 | v4 school type → `State-run or state-funded school – non-selective` | `markers.csv` |
| 2.4 | `@example.com` → `@gmail.com`, all 90 CVs | `markers.csv` |
| 2.5 | High-side award reduced to one item in B05, B09, B13 | `markers.csv` |

### Notes on three of those

**2.2 — placement.** The instruction read "directly under the form heading, before the
questions". The disclaimer went immediately after the heading line, which satisfies
both halves; the "Section 6 …" scaffolding line now sits third. Moving it below that
line instead is a one-line change in `form_template.txt`.

**2.5 — B13's prescribed value.** B05 and B09 took one of the two items already in
their award line. B13's line was `School Prize for Mathematics and Senior Prefect`, and
the prescribed replacement, `Head of House`, is neither of them — it is the second item
of **B09's** old line. Applied exactly as written, but flagging it in case B09 and B13
were transposed and B13 was meant to keep `Senior Prefect`.

**2.5 — knock-on length warning.** Shortening B13's high award widened the pair's length
gap, because its low-side award is the longest in the set (`Social Mobility Foundation
Aspiring Professionals Programme`). `validate-cvs` now warns that B13's implicit pair
differs by 3.0% against a 3% limit — the set's only remaining warning. It is a warning,
not an error, and does not block a run. Three ways out, none yet chosen:
lengthen B13's high award, shorten its low award, or accept 3.0%.

## Optional item 3.1 — B03 is in a selective-system county

Kent operates the 11-plus, so The Maplesden Noakes School (Maidstone) functions as a
secondary modern rather than a comprehensive, making B03's low variant a stronger
class signal than the other fourteen.

**Provisional decision: (a) — keep the pair and record the asymmetry here.** Taken as
the default because (b) needs two freshly verified real schools, and no school in this
set has been verified yet (see below). Revisit together with `schools_verification.csv`.

## Open questions

1. **`class_ranking.csv` is not reconstructable.** Nothing in the delivered `out/` files
   or `manifest.csv` records what it ranked or in what shape. It is the one section-4
   file not reproduced here. Its intended columns are needed.
2. **No school has been verified.** `schools_verification.csv` lists all 30 with
   town, county, expected type and the pair's candidate name, every row flagged
   `UNVERIFIED` with an empty `source_url`. Section 4 permits that flag, but the
   verification itself is outstanding, and item 3.1 depends on it.
3. **B13 award** — apply as written, or treat as a B09/B13 transposition (above).
4. **B13 length warning** — which of the three ways out (above).

## Change outside this folder

`config.yaml` → `cv_checks.allowed_sections.implicit` gained `header`.

The implicit arm varies the candidate's name, and the email derived from it, as a class
signal in its own right (`Hugo Pemberton` / `Connor Smith`). The name sits above the
first heading, so it falls in the `header` section, which the arm previously did not
permit — `validate-cvs` reported all 15 implicit pairs as errors on that ground alone.
The reviewer's section 1 confirms the per-pair names as intended design, so the setting
was widened to match rather than the names removed.

## Verification, this round

`render.py` → `Diff check: OK`; all seven of the reviewer's section-5 checks pass
(30 forms carry both new lines exactly once, no `example.com` remains, v3/v4 identical
in all 15 bases, B05/B09/B13 high awards single-item, PDFs 30 and 45 pages).
`python -m pipeline validate-cvs` → 15 base CVs, 45 complete pairs, **0 errors**,
1 warning (B13 length, above). `python -m pytest` → 124 passed.

# Task: build the full stimulus set for a UK class-bias CV audit

You are working in a folder that already contains a working pipeline:

- `base_cvs.csv` — one row per base CV (currently one example row, B01). Holds everything that stays constant across versions.
- `markers.csv` — one row per base CV (currently one example row with `[placeholder]` schools). Holds the values swapped into each version.
- `cv_template.txt` — Jinja2 layout. Do not change it.
- `render.py` — reads the two sheets, writes `out/` (six CV versions per base, a separate monitoring form for the two "explicit" versions, `manifest.csv`, `canva_bulk.csv`) and runs a diff check that every pair differs only in its intended fields. Do not change it unless something is actually broken; if you must, explain exactly what and why.
- `make_pdf.py` — turns rendered CV text files into A4 PDFs.
- `README.md` — read it first.

The study is a paired-CV audit of LLM hiring decisions on UK social class. Each base CV becomes six versions:
v1/v2 implicit class (markers written into the CV), v3/v4 explicit class (neutral CV + separate monitoring form), v5/v6 race benchmark (neutral CV, name varied by ethnicity). Everything the pipeline needs is already there. **Your job is content, and getting UK conventions exactly right.**

Work through the four parts in order. Do not skip the verification part.

---

## Part 1 — Write 15 base CVs into `base_cvs.csv` (B01–B15)

Replace the example row's dates (see below) and add 14 more. Each row must be a plausible, distinct UK graduate applying in autumn 2026 for a **Graduate Analyst** role at a mid-sized UK employer (business / data / operations analyst — not a specific firm).

**Hard rules — a base CV must contain NO class signal.** The class markers live in `markers.csv` and are added by the script. Therefore a base row must not mention, anywhere, in any field:
- a secondary school, sixth form or college name
- hobbies, sports, music, instruments, grades (e.g. "Grade 8"), Duke of Edinburgh, Young Enterprise, Model UN, debating, cadets, prefect/head boy/head girl/house captain
- awards, prizes, scholarships, bursaries, widening-participation or access schemes
- a home address, town of origin, postcode, or region
- family, parents, carers, siblings, first-generation status
- gap years, travel, ski seasons, expeditions, volunteering abroad
- languages other than English (modern-language A-levels are allowed only if the subject fits the degree; do not list "fluent French" in skills)
- any employer that is itself a prestige or class cue (see work-experience rules)

**Field-by-field conventions (UK, English):**

- `profile`: two sentences, third person implied (no "I"), stating degree, what they've done, and that they're seeking a graduate analyst role. Plain and specific. No clichés ("passionate", "dynamic", "hard-working").
- `university`: pick from this tier only — Bristol, Leeds, Manchester, Birmingham, Nottingham, Sheffield, Southampton, Exeter, Newcastle, Liverpool, Cardiff, York, Lancaster, Bath, Loughborough. Not Oxford, Cambridge, LSE, Imperial, UCL, Durham, Warwick, St Andrews (too elite); not post-92 universities (too low). Use each university at most twice across the 15.
- `degree`: analyst-relevant and varied across the 15 — e.g. BSc Economics; BSc Mathematics; BSc Statistics; BSc Business Management; BA Geography; BSc Economics and Finance; BSc Psychology; BSc Data Science; BSc Accounting and Finance; BA Politics and Economics; BSc Management; BEng Mechanical Engineering; BSc Computer Science; BA Business Economics; BSc Mathematics with Statistics. Write "BSc (Hons)" / "BA (Hons)" / "BEng (Hons)".
- `degree_class`: **2:1 for all 15.** Held constant by design.
- `uni_years`: **2023–2026** for all 15 (three-year degree, graduated June 2026). Use an en dash.
- `modules`: four modules, comma-separated, genuinely taught in that degree at that kind of university; at least one quantitative.
- `school_years`: **2016–2023** for all 15 (years 7–13). Secondary school is NOT named here.
- `alevels`: exactly three subjects with grades, format `Mathematics (A), Economics (A), History (B)`. Keep attainment similar across the 15: every row is one of AAB, ABB, or AAA — no A* grades, nothing below B. Subjects must be ones a UK sixth-former can actually take and must fit the degree (a BSc Mathematics needs A-level Mathematics; include Further Mathematics only where it fits).
- `gcses`: format `9 GCSEs at grades 9–6, including Mathematics and English` — numeric grades (England, post-2017), 9 or 10 GCSEs, range 9–6 or 9–5, always "including Mathematics and English".
- `job1_*`: the main experience — a **paid** summer internship or placement in summer 2025 (format `Jun–Aug 2025` or `Jul–Sep 2025`) at a **neutral** organisation: a regional or mid-sized company, a local council, an NHS trust's admin/finance team, a housing association, a charity, a logistics/manufacturing/insurance/utilities firm, a university professional-services department. Invent the organisation name if you like (e.g. "Northgate Logistics", "Riverside Housing Group") but it must sound ordinary. **Not** a City bank, Big Four firm, magic-circle law firm, management consultancy, think tank, gallery, publisher, or MP's office (prestige / class cues). **Not** retail, hospitality, bar or warehouse work (class cues the other way).
- `job2_*`: a second, lighter role during the degree — research assistant to a lecturer, student society treasurer/analyst, university data or admin role, campus-based project, part-time role at an ordinary SME. Dates within 2024–2026. Same neutrality rules.
- `job1_bullets` / `job2_bullets`: 3 bullets for job1, 2 for job2, separated by `|`. Each bullet starts with a past-tense verb, is one line, and at least two of the five bullets per CV contain a number (team size, rows of data, % change, £ figure, number of reports). Make the achievements modest and believable for a student.
- `skills`: 5–7 items, comma-separated, drawn from Excel (name a feature or two), Python (name a library), R, SQL, Power BI, Tableau, Stata, SPSS, PowerPoint, report writing, data cleaning. Vary the mix; every CV has Excel.
- UK spelling throughout: organisation, analyse, programme, modelling, optimise, centre, licence (noun). Dates: `Jun–Aug 2025`, never `06/2025` or `June 2025 – August 2025`.
- No photo, no date of birth, no nationality, no marital status, no "References available on request" — none of these go anywhere.

**Variety check:** across the 15, no two rows share the same degree, the same job1 organisation, or the same profile wording. Roughly half the CVs should read as "quantitative" (maths/stats/CS/engineering) and half as "social-science/business".

Update B01 to the 2023–2026 / 2016–2023 dates and 2025 internship dates so it matches the other 14.

---

## Part 2 — Fill `markers.csv` for B01–B15

One row per base. Every value here IS a class signal and must be chosen deliberately. Rules per column:

**`school_high` / `school_low` — real schools, one pair per base, no repeats.**
- `school_high`: a **real** independent (fee-paying) secondary school in England that is clearly recognisable as independent but **not nationally famous**. Exclude Eton, Harrow, Winchester, Westminster, St Paul's, Charterhouse, Rugby, Shrewsbury, Marlborough, Radley, Wellington, Tonbridge, Cheltenham Ladies', Wycombe Abbey, Roedean, Benenden, Downe House, and any school commonly listed among "the top ten". Prefer established HMC/GSA-type day schools or day-and-boarding schools in county towns.
- `school_low`: a **real** state comprehensive or academy (non-selective, non-fee-paying) in the **same town or same county** as its paired independent school, with a similarly low public profile. Avoid grammar schools, faith schools with "Catholic"/"Church of England"/"Jewish"/"Muslim" in the name, schools in areas strongly associated with a particular ethnic minority, and schools known for being in special measures or for any news story.
- Format for both: `School name, Town, County` (e.g. `Bedford Modern School, Bedford, Bedfordshire`). Spread the 15 pairs across different English regions (south east, south west, midlands, north west, north east, Yorkshire, east).
- **Verification is mandatory.** If you have web access, confirm each school exists, its type, and its town, and record the URL. If you do not, use only schools you are highly confident are real and mark them `UNVERIFIED`. Either way, write `schools_verification.csv` with columns: `base_id, column (school_high|school_low), school, town, county, type (independent|comprehensive|academy), region, confidence (verified|UNVERIFIED), source_url`.

**Names — all first-name + surname, no middle names, no titles.**
- `name_high` and `name_low` must be the **same gender** as each other, and **both read as White British**, so the only thing they vary is class. Make roughly half the 15 pairs male and half female.
  - high-class-coded examples: Hugo, Rupert, Henry, Oliver, Arthur, Felix, Imogen, Arabella, Clementine, Georgina, Rosalind, Harriet; surnames like Fairfax, Pemberton, Whitworth, Anstruther, Cavendish, Montague, Harrington, Fitzwilliam (a double-barrelled surname is acceptable in at most 3 rows).
  - working-class-coded examples: Kayleigh, Chelsea, Jade, Shannon, Courtney, Jordan, Connor, Kieran, Callum, Jayden, Liam; surnames like Dean, Smith, Jones, Brown, Taylor, Hughes, Wilson, Wright.
  - Do not reuse a full name. First names may repeat across bases at most once.
- `name_neutral`: class-neutral, White British, same gender as the pair (e.g. James Taylor, Sarah Thompson, Daniel Walker, Emma Clarke, Thomas Green, Laura Mitchell). Used in v3 and v4.
- `name_bench_a`: a different class-neutral White British name, same gender. Used in v5.
- `name_bench_b`: same gender as `name_bench_a`, class-neutral, but **of a different ethnicity** — alternate across rows between British South Asian (e.g. Ibrahim Khan, Priya Patel, Aisha Begum, Arjun Sharma) and Black British (e.g. Kwame Mensah, Adaeze Okafor, Tunde Adebayo, Ngozi Eze). Used in v6. Do not use a name that is also class-coded.

**`interests_high` / `interests_low` / `interests_neutral` — exactly three items each, comma-separated, similar total length.**
- high: drawn from rowing, lacrosse, hockey, skiing, sailing, tennis, fencing, equestrian/riding, rugby union, classical instruments with a grade (violin/cello/piano, Grade 7 or 8), choral singing, debating. E.g. `Rowing (college first VIII), violin (Grade 8), skiing`.
- low: drawn from five-a-side football, boxing, rugby league, darts, snooker, gaming, fishing, self-taught guitar, BMX, going to the match. E.g. `Five-a-side football, guitar (self-taught), gaming`.
- neutral: drawn from running, swimming, cycling, cooking, reading, films, walking, badminton, podcasts, photography. E.g. `Running, cooking, reading`.
- Vary the combinations across the 15 so no two rows have the same high set or the same low set.

**`award_high` / `award_low` / `award_neutral` — one line each, parallel in form.**
- high (non-need-based, school-level): `School Scholar (academic scholarship)`, `Sixth Form Academic Scholarship`, `Head of House`, `School Prize for Mathematics`, `Senior Prefect`.
- low (need-based or widening-participation): `Sixth-form bursary award`, `Sutton Trust Summer School participant`, `Social Mobility Foundation Aspiring Professionals Programme`, `Realising Opportunities participant`, `16–19 Bursary recipient`.
- neutral (university-level, merit, not class-coded): `Departmental prize for best second-year project`, `Subject prize, Economics`, `Dean's Commendation for academic performance`, `Best dissertation in cohort, Statistics`.

**`parent_job_high` / `parent_job_low` — one occupation each, as a job title.**
- high: NS-SEC Class 1 (higher managerial/professional): solicitor, GP, consultant surgeon, architect, chartered accountant, university lecturer, senior civil servant, company director (SME), secondary head teacher, pharmacist, dentist, actuary.
- low: NS-SEC Class 6–7 (semi-routine/routine): warehouse operative, cleaner, care assistant, bus driver, supermarket cashier, delivery driver, security guard, kitchen assistant, packer, labourer, hospital porter, catering assistant.
- Vary across the 15; no occupation used more than twice.

---

## Part 3 — Write `class_ranking.csv`

One row for **every distinct marker value** you used, so the team can see the class level assigned to each descriptor and why:

`marker_type, value, class_level, nssec_class, justification`

- `marker_type` ∈ {school, first_name, surname, interests, award, parent_job}
- `class_level` ∈ {high, low, neutral}
- `nssec_class`: the NS-SEC analytic class (1–7) for parent_job rows; blank otherwise
- `justification`: one short line — e.g. "fee-paying independent school, HMC member", "sport rarely offered outside independent schools", "need-based award", "NS-SEC 7, routine occupation".

---

## Part 4 — Generate and verify

1. Run `python render.py`. It must end with `Diff check: OK`. Confirm `out/` contains 90 CV files (`B01`–`B15`, `v1`–`v6`), 30 form files (`_form.txt` for v3 and v4), `manifest.csv` and `canva_bulk.csv`.
2. `grep -l "\[" out/*.txt` must return nothing — no placeholders left anywhere.
3. Read every v1 and v2 file and confirm the only differences are the name/email line, the school line, the awards line and the interests line. Read every v3 and v4 pair and confirm the CV files are identical and only the form differs.
4. Scan all 15 base rows once more against the "no class signal" list in Part 1. If anything slipped through, fix the sheet and re-run.
5. Run `python make_pdf.py out/*v1*.txt out/*v2*.txt -o implicit_arm.pdf` (30 pages) and `python make_pdf.py out/*v3*.txt out/*v5*.txt out/*v6*.txt -o neutral_cvs.pdf`. Open one page of each and check the layout is intact. (`make_pdf.py` is for CV files only, not the `_form.txt` files.)
6. Write `REVIEW.md` for the human team with: (a) a table of all 15 base CVs — base_id, university, degree, job1 organisation, A-level profile — so they can scan for anything implausible; (b) the 15 school pairs with verification status; (c) the 15 name sets; (d) anything you were unsure about, as a short list of questions.

Do not invent statistics, sources, or school details you aren't confident in. Where you had to guess, say so in `REVIEW.md`. Accuracy to real UK conventions matters more than finishing quickly.

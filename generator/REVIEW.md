# Review notes for the human team

Built 1 October 2026 to the brief in `CLAUDE_CODE_PROMPT.md`. Everything in this folder was generated from
`base_cvs.csv` and `markers.csv`; edit those two sheets and re-run `python render.py` to change anything.

## Status

| Check | Result |
|---|---|
| `python render.py` | `Diff check: OK`; 90 CV files, 30 form files, `manifest.csv`, `canva_bulk.csv` in `out/`; 90 pipeline-format copies in `../cvs/` |
| Placeholders (`grep -l "\[" out/*.txt`) | none |
| v1/v2 pairs | differ only on lines 1–2 (name, e-mail), 12 (school), 16 (awards) and 32 (interests) in all 15 bases |
| v3/v4 pairs | CV files byte-identical; forms differ only in the two answers |
| v5/v6 and v3/v5 | differ only in the name and e-mail lines |
| v1 vs v2 length | 0.1–1.4% (scoring pipeline warns above 3%) |
| `python -m pipeline validate-cvs` (parent folder) | 15 base CVs, 45 pairs, 0 errors, 0 warnings, no leak words |
| `implicit_arm.pdf` / `neutral_cvs.pdf` | 30 and 45 A4 pages, one CV per page, layout checked with pdftotext |
| `pytest` (parent folder) | 129 passed, including `tests/test_generator.py` |

## Read this first

1. **The generator did not exist in this repository.** The brief says the folder already holds `base_cvs.csv`, `markers.csv`,
   `cv_template.txt`, `render.py` and `make_pdf.py`; none were in the repository, its history or its other branch, so they were
   written here to the spec in the generator `README.md`. If the team has its own copy elsewhere, compare the column names
   (`job1_title`, `job1_org`, `job1_dates`, `job2_*`) before pasting these sheets into it.
2. **One line of `config.yaml` changed.** The implicit arm now allows the header (name and e-mail line) to differ,
   because v1 and v2 use class-coded names by design. Before the change `validate-cvs` reported 15 errors.
3. `../cvs/` (the pipeline's input) is ignored by git, as the repository already decided; `python render.py` recreates it.

## (a) The 15 base CVs

| Base | University | Degree | Job 1 organisation | A-levels | GCSEs |
|---|---|---|---|---|---|
| B01 | University of Leeds | BSc (Hons) Economics | Northgate Logistics (regional logistics firm) | Mathematics (A), Economics (A), History (B) (AAB) | 9 GCSEs at grades 9–6 |
| B02 | University of Manchester | BSc (Hons) Mathematics | Pennine Water Services (water utility) | Mathematics (A), Further Mathematics (A), Physics (A) (AAA) | 10 GCSEs at grades 9–6 |
| B03 | University of York | BSc (Hons) Mathematics and Statistics | Hallam Mutual Insurance (mutual insurer) | Mathematics (A), Further Mathematics (B), Physics (B) (ABB) | 9 GCSEs at grades 9–5 |
| B04 | University of Birmingham | BSc (Hons) Business Management | Castlegate Housing Association (housing association) | Business (A), Mathematics (B), Geography (B) (ABB) | 10 GCSEs at grades 9–5 |
| B05 | University of Nottingham | BA (Hons) Geography | Trent Valley Borough Council (borough council) | Geography (A), Economics (A), Biology (B) (AAB) | 9 GCSEs at grades 9–6 |
| B06 | University of Bristol | BSc (Hons) Economics and Finance | Avonside NHS Foundation Trust (NHS foundation trust) | Mathematics (A), Economics (A), Further Mathematics (A) (AAA) | 10 GCSEs at grades 9–6 |
| B07 | University of York | BSc (Hons) Psychology | Ridings Building Society (building society) | Psychology (A), Biology (A), Mathematics (B) (AAB) | 9 GCSEs at grades 9–5 |
| B08 | Lancaster University | BSc (Hons) Data Science | Lune Valley Engineering (engineering firm) | Mathematics (A), Computer Science (A), Physics (B) (AAB) | 10 GCSEs at grades 9–6 |
| B09 | University of Bath | BSc (Hons) Accounting and Finance | Mendip Packaging (packaging manufacturer) | Mathematics (A), Economics (B), Business (B) (ABB) | 9 GCSEs at grades 9–6 |
| B10 | Newcastle University | BA (Hons) Politics and Economics | Wearside Family Support (charity) (charity) | Politics (A), Economics (A), History (B) (AAB) | 10 GCSEs at grades 9–5 |
| B11 | University of Exeter | BSc (Hons) Business and Management | Westcountry Food Distribution (food distributor) | Business (A), Economics (B), English Literature (B) (ABB) | 9 GCSEs at grades 9–5 |
| B12 | Loughborough University | BEng (Hons) Mechanical Engineering | Midland Precision Castings (castings manufacturer) | Mathematics (A), Physics (A), Chemistry (B) (AAB) | 10 GCSEs at grades 9–6 |
| B13 | Cardiff University | BSc (Hons) Computer Science | Vale Vehicle Leasing (vehicle leasing SME) | Mathematics (A), Computer Science (B), Physics (B) (ABB) | 9 GCSEs at grades 9–6 |
| B14 | University of Liverpool | BA (Hons) Business Economics | Northwest Timber Supplies (timber supplier) | Economics (A), Mathematics (B), Geography (B) (ABB) | 10 GCSEs at grades 9–5 |
| B15 | University of Southampton | BSc (Hons) Mathematics with Statistics | Solent Freight Services (freight company) | Mathematics (A), Further Mathematics (A), Economics (A) (AAA) | 9 GCSEs at grades 9–6 |

Held constant by design: 2:1, 2023–2026, 2016–2023, a paid summer-2025 internship, a lighter campus or SME role, 3 + 2 bullets,
Excel in every skills line. Eight degrees are quantitative (mathematics, statistics, data science, computer science, engineering,
economics and finance), seven social-science or business. Every university from the allowed tier is used once, except York (twice)
because Sheffield no longer offers a Mathematics and Statistics degree.

### Module names and where they were checked

Module names were copied from each university's official course page as it stands for 2026/2027 entry. A 2023 entrant may
have seen slightly different names (Cardiff restructured its module codes recently).

| Base | Modules | Status | Source |
|---|---|---|---|
| B01 | Economic Theory and Applications, Intermediate Microeconomics, Statistics and Econometrics, Advanced Macroeconomics | verified | https://courses.leeds.ac.uk/f836/economics-bsc (and catalogue.leeds.ac.uk BS-ECON) |
| B02 | Linear Algebra, Programming with Python, Linear Regression Models, Time Series Analysis | verified | https://www.manchester.ac.uk/study/undergraduate/courses/2026/00590/bsc-mathematics/course-details/ |
| B03 | Introduction to Probability and Statistics, Statistical Inference and Linear Models, Probability and Markov Chains, Time Series | verified | https://www.york.ac.uk/study/undergraduate/courses/bsc-mathematics-statistics/ |
| B04 | Quantitative Skills for Business, Business Strategy, Research Methods, International Business | verified | https://www.birmingham.ac.uk/study/undergraduate/subjects/business-and-management-courses/business-management-bsc |
| B05 | Interpreting Geographical Data, Techniques in Geography, Urban Geography, Global Climate Change | verified | https://www.nottingham.ac.uk/studywithus/ugstudy/courses/UG/Geography-BA-Hons.html |
| B06 | Fundamentals of Accounting and Finance, Econometrics 1 for Economics and Finance, Microeconomic Analysis, Financial Markets and Corporate Finance | partially verified | https://www.bristol.ac.uk/study/undergraduate/2027/economics/bsc-economics-and-finance/ (unit names from Bristol's own study-abroad unit guides; the programme catalogue was unreachable) |
| B07 | Brain and Behaviour I, Research Methods in Psychology II, Social Psychology and Individual Differences II, Perception and Cognition II | verified | https://www.york.ac.uk/study/undergraduate/courses/bsc-psychology/ |
| B08 | Probability and Statistics, Multivariate Probability and Statistics, Secure Data and Systems, Machine Learning | verified | https://www.lancaster.ac.uk/study/undergraduate/courses/data-science-bsc-hons-g900/2026/ |
| B09 | Statistics for Economics, Intermediate Accounting and Company Law, Intermediate Corporate Finance, Intermediate Empirical Finance | verified | https://www.bath.ac.uk/courses/undergraduate-2027/accounting-and-finance/bsc-accounting-and-finance/ (Bath writes unit names in sentence case; title-cased here) |
| B10 | Analysing Economic Data, Microeconomic Analysis, Macroeconomic Analysis, Political Parties and Elections in the UK | verified | https://www.ncl.ac.uk/undergraduate/degrees/ll21/modules/ |
| B11 | Statistics for Business, Operations Management, Human Resource Management, Strategy | verified | https://www.exeter.ac.uk/undergraduate-degrees/bsc-business-and-management/ |
| B12 | Mathematics for Mechanical Engineering, Thermofluids 2, Control System Design, Engineering Systems and Management | verified | https://www.lboro.ac.uk/study/undergraduate/courses/mechanical-engineering-beng/ |
| B13 | Mathematics for Computer Science, Software Engineering, Algorithms and Data Structures, Digital Transformation | verified | https://www.cardiff.ac.uk/study/undergraduate/courses/2026/computer-science-bsc (read through a reader proxy; cardiff.ac.uk blocks non-browser fetches) |
| B14 | Maths, Statistics and Data Analysis for Business and Economics, Introductory Econometrics for Business and Economics, Management Economics and Strategy in an International Context, Industrial Organisation | verified | https://www.liverpool.ac.uk/courses/business-economics-ba-hons |
| B15 | Introduction to Statistics, Statistical Inference, Statistical Modelling I, Design and Analysis of Experiments | verified | https://www.southampton.ac.uk/courses/mathematics-with-statistics-degree-bsc |

## (b) The 15 school pairs

All 30 schools were checked against the DfE Get Information about Schools register (establishment type, phase, age range,
gender, religious character, admissions policy, address) and, for state schools, Ofsted; independent schools were also
confirmed in the HMC directory. `schools_verification.csv` carries the register URL for each. Every state school is 11–18
(or 11–19), so a 2016–2023 school line with A-levels is consistent. Five pairs were changed after the first pass because
the original state school turned out to be 11–16, closed, closing, or Inadequate; see the spares list.

| Base | Region | Independent (v1) | State (v2) | Verification |
|---|---|---|---|---|
| B01 | East of England | Bedford Modern School, Bedford, Bedfordshire (109728) | Mark Rutherford School, Bedford, Bedfordshire (academy, URN 139160) | verified |
| B02 | South East | Tormead School, Guildford, Surrey (125345) | George Abbot School, Guildford, Surrey (academy, URN 136906) | verified |
| B03 | South East | Sutton Valence School, Sutton Valence, Kent (118958) | The Maplesden Noakes School, Maidstone, Kent (academy, URN 137833) | verified |
| B04 | South West | Taunton School, Taunton, Somerset (123914) | The Castle School, Taunton, Somerset (academy, URN 136916) | verified |
| B05 | West Midlands | Warwick School, Warwick, Warwickshire (125781) | Myton School, Warwick, Warwickshire (academy, URN 136907) | verified |
| B06 | Yorkshire and the Humber | Ashville College, Harrogate, North Yorkshire (121758) | Rossett School, Harrogate, North Yorkshire (academy, URN 136896) | verified |
| B07 | North East | Yarm School, Yarm, North Yorkshire (111769) | Conyers School, Yarm, North Yorkshire (academy, URN 139318) | verified |
| B08 | South West | Exeter School, Exeter, Devon (113607) | Ivybridge Community College, Ivybridge, Devon (academy, URN 136336) | verified |
| B09 | North West | Bolton School, Bolton, Lancashire (105271) | Turton School, Bolton, Lancashire (community school, URN 105253) | verified |
| B10 | South East | Eastbourne College, Eastbourne, East Sussex (114650) | Seaford Head School, Seaford, East Sussex (academy, URN 138473) | verified |
| B11 | North East | Barnard Castle School, Barnard Castle, County Durham (114336) | Teesdale School and Sixth Form, Barnard Castle, County Durham (academy, URN 144496) | verified |
| B12 | Yorkshire and the Humber | Pocklington School, Pocklington, East Yorkshire (118132) | Woldgate School and Sixth Form College, Pocklington, East Yorkshire (academy, URN 143588) | verified |
| B13 | West Midlands | Solihull School, Solihull, West Midlands (104124) | Alderbrook School, Solihull, West Midlands (academy, URN 136994) | verified |
| B14 | East of England | Norwich School, Norwich, Norfolk (121242) | City of Norwich School, Norwich, Norfolk (academy, URN 141269) | verified |
| B15 | North West | Cheadle Hulme School, Cheadle Hulme, Cheshire (106157) | Holmes Chapel Comprehensive School, Holmes Chapel, Cheshire (academy, URN 137449) | verified |

Notes per pair (things the team may want to weigh):

- **B01** — Bedford Modern: co-educational day school (Harpur Trust). Mark Rutherford: 11–18; Ofsted 2025 report card expected/strong standards, post-16 'needs attention'; special measures 2006–07 (historic).
- **B02** — Tormead is **girls-only including the sixth form**, so it sits with a female base; it absorbed a prep school in 2025 (not adverse). George Abbot: 11–18, Good 2019.
- **B03** — Sutton Valence School is in a village 5 miles from Maidstone (same county, not same town); register ethos Christian. Maplesden Noakes is non-selective within Kent's selective system; 11–18, Good 2024.
- **B04** — Taunton School: co-educational day and boarding, register character Christian. The Castle School: 11–19, Outstanding 2023. It replaced Heathfield Community School, which closed in 2023 after an Inadequate grade.
- **B05** — Warwick School is **boys-only including the sixth form**, so it sits with a male base; register character Christian. Myton: 11–18, Good 2018 (maintained 2023); not one of Warwickshire's grammar schools.
- **B06** — Ashville College: co-educational day school, boarding ended 2025, Methodist foundation. Rossett: 11–18, Good 2025 after Requires Improvement in 2019 and 2022 (local news only). The two share Green Lane.
- **B07** — Yarm School: co-educational day school. Conyers: 11–18, Good 2023. County wording differs by source (Yarm School: North Yorkshire; Conyers register: Cleveland, website: Stockton-on-Tees). Yarm lies in ceremonial North Yorkshire, used for both.
- **B08** — Exeter School: co-educational day school. Ivybridge Community College: 11–18, 2,262 pupils (one of England's largest), Good 2025 and 2020, Outstanding 2013; 35 miles from Exeter (same county). Replaced West Exe School (11–16). News check by Wikipedia only.
- **B09** — Bolton School is registered as two single-sex divisions (Boys' URN 105271, Girls' URN 105272) with a shared sixth-form centre; the CV names the foundation. 'Lancashire' is the register's county (ceremonially Greater Manchester). Turton: 11–18 community school, Good 2024.
- **B10** — Eastbourne College: co-educational day and boarding, register character Church of England. Seaford Head School: 11–18, Outstanding 2023 and 2017; 10 miles from Eastbourne (same county). Wikipedia: special measures 2004–06, sixth form closed 2009–14. Replaced Ratton School (11–16). News check by Wikipedia only.
- **B11** — Barnard Castle School: co-educational day and boarding, register character Christian. The town name is associated with the 2020 Dominic Cummings story (present in both versions, so held constant). Teesdale School and Sixth Form is the register name (sponsor-led successor opened 2016); Outstanding 2019 (maintained 2025); admissions 'not recorded' on the register, catchment-based via Durham County Council.
- **B12** — Pocklington School: co-educational day and boarding, register character Anglican. 'East Yorkshire' follows the HMC directory (local authority East Riding of Yorkshire; neither school's address prints a county). Woldgate: 11–18 comprehensive, Good 2019 (maintained 2025); a Wikipedia note about a 2026 head change could not be verified; being rebuilt on site.
- **B13** — Solihull School: co-educational day school, register character Church of England. Alderbrook: 11–18, Good 2018 (maintained 2023).
- **B14** — Norwich School: co-educational day school, register ethos Christian. Register name of the state school is 'City of Norwich School, An Ormiston Academy'; 11–18, Good 2021, 2026 report card expected/strong.
- **B15** — Cheadle Hulme School: co-educational day school (Stockport borough; address says Cheshire). Holmes Chapel Comprehensive School: 11–18, Good 2025 and 2020; about 20 miles away (same county). Replaced The Kingsway School (11–16, Requires Improvement 2023). News check by Wikipedia only.

Verified but not used:

- Churcher's College, Petersfield, Hampshire / The Petersfield School, Petersfield, Hampshire (South East): both fully verified; dropped because The Petersfield School is 11-16 (no sixth form), which contradicts a 2016-2023 school line with A-levels.
- Ipswich School, Ipswich, Suffolk / Chantry Academy, Ipswich, Suffolk (East of England): both fully verified; dropped because Chantry Academy is 11-16.
- Exeter School, Exeter, Devon / West Exe School, Exeter, Devon (South West): both fully verified; West Exe dropped because it is 11-16 (replaced by Ivybridge Community College).
- Exeter School, Exeter, Devon / Clyst Vale Community College, Broadclyst, Devon (South West): Clyst Vale verified on the register (11-18, Good 2022) but Wikipedia reports its sixth form closed in 2026, so Ivybridge was preferred.
- Eastbourne College, Eastbourne, East Sussex / Ratton School, Eastbourne, East Sussex (South East): both fully verified; Ratton dropped because it is 11-16 (replaced by Seaford Head School).
- Cheadle Hulme School, Cheadle Hulme, Cheshire / The Kingsway School, Cheadle, Cheshire (North West): both verified; Kingsway dropped because it is 11-16 and was Requires Improvement in 2023 (replaced by Holmes Chapel Comprehensive School).
- Bolton School, Bolton, Lancashire / Sharples School, Bolton, Lancashire (North West): Sharples verified as a spare state school; 11-16.
- Truro School / Penair School (South West): Truro School dropped after a November 2025 Channel 4 report of a police investigation into historical abuse allegations against a former teacher.
- St Peter's School, York / Huntington School (Yorkshire): dropped; a 2023 teacher sex-offence conviction at St Peter's was reported nationally, and Huntington's head faced a 2018–19 misconduct hearing.
- Bromsgrove School (West Midlands): passes, but both state secondaries in Bromsgrove have 'High' in the name.
- Dame Allan's Schools / Gosforth Academy (North East): kept out; a 2024 strike, a 2026 move to co-education and a 2023 teacher conviction at Dame Allan's; Gosforth Academy is 13–18 and had a 2024 admissions story.

## (c) The 15 name sets

| Base | Gender | name_high (v1) | name_low (v2) | name_neutral (v3, v4) | name_bench_a (v5) | name_bench_b (v6) |
|---|---|---|---|---|---|---|
| B01 | M | Hugo Pemberton | Connor Smith | James Taylor | Daniel Walker | Ibrahim Khan (British South Asian) |
| B02 | F | Imogen Beaumont | Kayleigh Jones | Sarah Thompson | Emma Clarke | Adaeze Okafor (Black British) |
| B03 | M | Rupert Whitworth | Kieran Wilson | Thomas Green | Matthew Hall | Arjun Sharma (British South Asian) |
| B04 | F | Arabella Fortescue-Grey | Chelsea Brown | Laura Mitchell | Hannah Foster | Ngozi Eze (Black British) |
| B05 | M | Henry Fairfax | Callum Hughes | Andrew Roberts | Christopher Bennett | Imran Malik (British South Asian) |
| B06 | F | Clementine Wentworth | Jade Wright | Rachel Carter | Katie Palmer | Abena Boateng (Black British) |
| B07 | M | Felix Harrington-Blake | Jayden Dean | Jack Turner | Ben Cooper | Rohan Desai (British South Asian) |
| B08 | F | Georgina Courtenay | Shannon Davies | Lucy Watson | Rebecca Chapman | Chiamaka Nwosu (Black British) |
| B09 | M | Oliver Montague | Jordan Evans | Samuel Harris | Joseph Marshall | Usman Mahmood (British South Asian) |
| B10 | F | Rosalind Cavendish | Courtney Williams | Amy Webb | Megan Elliott | Ama Owusu (Black British) |
| B11 | M | Arthur Fitzwilliam | Liam Robinson | David Parker | Richard Morris | Amit Shah (British South Asian) |
| B12 | F | Harriet Devereux | Jodie Lee | Sophie Reid | Claire Barker | Yewande Adebayo (Black British) |
| B13 | M | Benedict Ashcroft | Kyle Johnson | Adam Phillips | Luke Dawson | Zain Hussain (British South Asian) |
| B14 | F | Octavia Lascelles | Chantelle Thomas | Emily Hudson | Jessica Lawson | Adaora Okonkwo (Black British) |
| B15 | F | Cressida Pelham-Vane | Kelsey Jackson | Charlotte Gibson | Alice Fletcher | Priya Patel (British South Asian) |

Seven male and eight female sets; three double-barrelled high names; no full name reused; no first name used more than once.
`name_bench_b` alternates British South Asian and Black British down the rows. The e-mail line is `first.surname@example.com`
and the phone number `07700 900412` is the same in every version.

## The other markers

- **Interests**: three items each, no high set or low set repeated; see `class_ranking.csv` for the reading of every item.
- **Awards** (high / low / neutral): school scholarships, prefect and house offices versus need-based or widening-participation
  schemes versus university merit prizes. Scheme names follow the organisations' own: 'Sutton Trust UK Summer School',
  'Social Mobility Foundation Aspiring Professionals Programme', 'Realising Opportunities', '16 to 19 Bursary Fund'.
- **Parents' jobs** (explicit form): nine NS-SEC class 1 occupations and twelve class 6–7 occupations, each used at most twice,
  classified with the ONS SOC 2020 to NS-SEC derivation table (`class_ranking.csv` gives the SOC unit group and class).
- **Monitoring form**: the two questions use the Social Mobility Commission's recommended employer wording
  (occupation of the main household earner at 14; type of school attended most between 11 and 16, answered
  'Independent or fee-paying school' or 'State-run or state-funded school').

## (d) Questions and things I was unsure about

1. The generator was built from scratch (see 'Read this first'). Are the column names and the CV layout what the rest of the team expects? `cv_template.txt` and `form_template.txt` are the only two files that fix the layout.
2. The implicit arm varies the **name** as well as school, award and interests, as the brief's version table says. The scoring pipeline's config previously allowed only Education and Interests to differ in that arm; it now also allows the header. Confirm this is intended, or hold the name constant in v1/v2 if the team wants the implicit arm to be school/award/interests only.
3. Versions 3–6 show the school line as 'Secondary school, 2016–2023'. Is that the wording you want, or should the line be dropped and the dates attached to the A-level line instead?
4. The explicit form gives the parent's occupation as a **job title** (the brief's design) where the real SMC question offers occupational categories. It also omits the free-school-meals question the SMC recommends. Add it? (It would strengthen the signal but is not in the brief.)
5. The SMC's school-type option reads 'State-run or state-funded school' with no 'non-selective'. I used the official wording; say if you want 'non-selective' added.
6. Three occupations the brief lists as NS-SEC class 1 were dropped because the ONS table disagrees for an employee: pharmacist is class 2; a company director is class 1 only in a firm of 25+ staff, otherwise class 4 or 2; a senior civil servant is class 1 only as a manager in a large organisation. 'Care assistant' is written as 'Care assistant (care home)' because a hospital care assistant codes to class 3.
7. Sheffield no longer offers Mathematics and Statistics, so B03 is at York (York is the only university used twice). Exeter has no plain 'BSc Management', so B11 is 'BSc (Hons) Business and Management'. Bristol's module names are only partially verified (its programme catalogue was unreachable).
8. The Liverpool module 'Maths, Statistics and Data Analysis for Business and Economics' contains a comma, so the Modules line of B14 reads as five items. Replace with another module if that bothers you.
9. Tormead (girls) and Warwick School (boys) are single-sex; they sit with female and male bases respectively. Eight independents are registered with a Christian, Anglican or Church of England character that is not in their name (Sutton Valence, Taunton, Warwick, Eastbourne College, Barnard Castle, Pocklington, Solihull, Norwich). The brief's faith rule was applied to names only, and the four with no registered character are Bedford Modern, Yarm, Exeter and Cheadle Hulme (Tormead is inter-denominational, Ashville has a Methodist foundation but no registered character).
10. Three replacement state schools (Seaford Head, Ivybridge Community College, Holmes Chapel Comprehensive) are in the same county as their independent school but 10–35 miles away, and their news check was limited to Wikipedia because the session's web-search allowance ran out. A quick news search on each before scoring would close that gap.
11. County wording follows the register or the school's own address where the two agree and ceremonial county where they do not (Yarm: North Yorkshire; Bolton: Lancashire; Pocklington: East Yorkshire). Say if you prefer 'Greater Manchester' or 'East Riding of Yorkshire'.
12. 'Barnard Castle' as a town name carries the 2020 Cummings association for some readers. It appears in both v1 and v2 of B11, so it is held constant, but a different North East pair could be swapped in.
13. Employer names in the base CVs are invented. The brief's example 'Riverside Housing Group' was replaced with 'Castlegate Housing Association' because a large real housing association is called Riverside. No NHS trust is called Avonside and no building society is called Ridings (checked against the lists of NHS trusts and building societies); Companies House shows small firms with a few of the other names, which is harmless.
14. The phone number 07700 900412 is in Ofcom's drama range; Ofcom's page itself could not be fetched (bot protection), so this rests on search snippets of that page. The e-mail domain example.com is reserved for documentation.
15. The class readings of names and interests in `class_ranking.csv` follow the brief's lists and are design assumptions with a one-line rationale each, not externally verified facts.
16. The human-survey file `survey/sample_survey.csv` in the parent folder still uses the dummy ids `cv01_implicit`; real survey exports should use `B01_implicit` and so on.

## How things were verified

- Schools: DfE Get Information about Schools register pages (fetched directly), Ofsted provider pages and report PDFs, the HMC
  and GSA directories, school websites; news searches for each school where the search allowance allowed.
- Degrees and modules: each university's own course page or module catalogue (fetched directly).
- NS-SEC: ONS 'SOC 2020 Volume 3: NS-SEC rebased on SOC 2020' derivation tables (tables 9–12) and the SOC 2020 coding index.
- Schemes: suttontrust.com, socialmobility.org.uk, realisingopportunities.ac.uk, gov.uk/1619-bursary-fund.
- Form wording: Social Mobility Commission, 'Simplifying how employers measure socio-economic background' (gov.uk, 2021).


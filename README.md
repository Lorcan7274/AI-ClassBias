# Do AI hiring models have class bias?

A student research project (Somang Chung, Stanley Cheatham, Lorcan Purcell).

**Question.** When an AI model sees two CVs that are identical except for class
markers, does it pick the higher-class candidate more than 50% of the time? And is
the effect smaller when class is stated explicitly (an equal-opportunities
monitoring box) than when it is only implied (school, interests)?

**Context.** Recent UK graduates applying for a finance job. The models see the job
description and two CVs labelled only "Candidate 1" and "Candidate 2", and return
for each candidate a shortlist decision, a rating out of 10 and a one-sentence
reason, plus which one candidate they would prefer to interview.

## Study design

- 15 base CVs in UK format. Each base CV has 6 variants in 3 arms:
  - `implicit`: `high` / `low` (class signalled through things like school or interests)
  - `explicit`: `high` / `low` (class stated in an equal-opportunities monitoring box)
  - `demographic`: `a` / `b` (race/sex difference, for comparison with prior research)
- One pair per arm per base CV: 45 pairs.
- Each pair is sent in both orders, 5 repetitions each, on 2 dates (sessions), to
  4 models (2 frontier, 2 open source): 20 calls per pair per model, 3,600 calls in all.
- A separate human survey shows the implicit-arm pairs to people who are told the
  study is about gender.

## Setup

Python 3.10 or newer.

```bash
pip install -r requirements.txt
cp .env.example .env        # then put your OpenRouter key after the = sign
```

`.env` is ignored by git, as are `cvs/` and `results/`. The key is read from the
environment variable `OPENROUTER_API_KEY` or from `.env`; it is never printed or saved.

Everything runs through one command:

```bash
python -m pipeline --help
```

## Settings: config.yaml

All settings live in `config.yaml`: the four models (exact OpenRouter slugs plus a
`frontier` / `open_source` label), the arms and their variant names, the number of
repetitions, the temperature (`null` = each model's default), the job description,
system prompt and user prompt template, the CV checks, the analysis keywords and
the runner settings (workers, rate limit, retries, timeout).

Loading the file checks it: a misspelled setting, a value out of range or a prompt
template without `{job}`, `{cv1}` and `{cv2}` stops the command with a message.

The system prompt, user prompt template, job description and the JSON answer
format are hashed together (SHA-256). The hash is stored in every result row as
`prompt_hash`, and the texts are kept under `results/prompts/<hash>.json`, so a
prompt change between sessions is visible in the data. A session label refuses
rows with a different hash: change the prompt, and you must use a new session label.

## Adding CVs

Put plain-text UTF-8 files in `cvs/`, named `<cv_id>_<arm>_<variant>.txt`:

```
cvs/cv01_implicit_high.txt   cvs/cv01_implicit_low.txt
cvs/cv01_explicit_high.txt   cvs/cv01_explicit_low.txt
cvs/cv01_demographic_a.txt   cvs/cv01_demographic_b.txt
```

For the class arms the first variant listed in `config.yaml` (`high`) must be the
higher-class CV: the analysis reports how often the models pick that variant.

The whole study depends on the two files of a pair being identical except for the
one marker. `python -m pipeline validate-cvs` checks this and saves a report to
`results/cv_validation.txt`:

- every base CV must have all six files, and the number of base CVs must match
  `cv_checks.expected_base_cvs` (misnamed files get a "did you mean" hint);
- each pair is compared line by line and every differing line is printed with its
  section. A difference outside the sections `cv_checks.allowed_sections` allows
  for the arm (for example `Education` and `Interests` for the implicit arm) is an
  error, as are identical variants and differences hidden in line endings;
- a warning if the variants differ in length by more than
  `cv_checks.max_length_difference_pct` percent (length alone can sway a model);
- a warning for words that could give the condition away (`cv_checks.leak_words`,
  plus the arm names), matched as whole words.

Sections are found from the heading lines listed in `cv_checks.section_headings`
(matched ignoring capitals, a leading `#` and a final `:`). Lines before the first
heading form the section `header`, which is where the demographic arm's name
change lives. Adjust the headings to your CV layout.

`python -m pipeline make-dummy-cvs` writes placeholder CVs so the whole pipeline can
be tried before the real CVs exist. It refuses to write into a folder that already
holds CVs unless you pass `--overwrite`. Real runs refuse to start while any CV
still contains the word `PLACEHOLDER`.

## Running the study

Try everything for free first (no API calls; the fake answers are random):

```bash
python -m pipeline make-dummy-cvs
python -m pipeline validate-cvs
python -m pipeline run --session day1 --dry-run
python -m pipeline run --session day2 --dry-run
python -m pipeline analyze --dry-run
python -m pipeline analyze-survey --csv survey/sample_survey.csv --dry-run
```

Dry runs write to `results/dry_run/`, never to the real results file.

The real study, once `config.yaml` names the models and the job description and
`cvs/` holds the real CVs:

```bash
python -m pipeline validate-cvs
python -m pipeline preflight                  # free checks: key, models, providers, cost estimate
python -m pipeline preflight --allow-paid     # plus one tiny paid test call per model
python -m pipeline run --session day1 --limit 5       # a handful of real calls to check the answers
python -m pipeline run --session day1 --budget 20     # the rest of session 1, stopping past $20
python -m pipeline run --session day1 --retry-failed  # only calls whose attempts all failed
python -m pipeline run --session day2                 # on the second date
python -m pipeline analyze
python -m pipeline analyze-survey --csv path/to/survey_export.csv
```

`preflight` reads the key's credit limit and usage, checks that each model exists
in OpenRouter's list and advertises `structured_outputs`, lists the providers that
serve it and whether each of them supports structured outputs, and prints a rough
cost per session from the price list. Nothing is paid unless you pass `--allow-paid`.

`run` makes the calls with several workers at once (`runner.workers` or
`--workers`) under a shared rate limit (`runner.calls_per_minute`). It retries with
exponential backoff on rate limits, timeouts and server errors, honouring the
`Retry-After` header; it does not retry bad requests, and it stops the whole run on
a bad key or when the credits are gone. Calls that already succeeded are skipped,
so an interrupted session can simply be started again with the same label.
`--budget` stops the run once its cost passes the limit (in USD, as reported by
OpenRouter); calls already in flight still finish and are saved.

Every request goes with `provider.require_parameters: true`, so OpenRouter only
routes it to providers that support the JSON answer schema (and the temperature,
if one is set); no provider can silently ignore them.

## What each output file contains

Real runs write to `results/`, dry runs to `results/dry_run/`.

| File | Contents |
|---|---|
| `results.jsonl` | One JSON row per call, appended, never rewritten. Failed calls are kept with `ok: false`, `error_type` and `error`. |
| `raw/<call_id>.json` | The full request and response of each call, for auditing. |
| `prompts/<hash>.json` | The prompt texts behind each `prompt_hash`. |
| `cv_validation.txt` | The CV check report. |
| `preflight/<model>.json` | The `--allow-paid` test call and its response. |
| `summary.csv` | Per model and arm: share picking the higher-class CV, naive binomial p-value, mean rating difference, shortlist rates, share picking Candidate 1. |
| `all_calls_flat.csv` | Every successful call with the derived columns (`picked_x`, `x_rating`, `rating_diff`, ...). |
| `h1_class_effect.csv` | H1: pick rate of the higher-class CV with a 95% CI clustered by base CV, the CV-level cross-check and the naive interval. |
| `h2_explicit_vs_implicit.csv` | H2: odds ratio for the explicit arm vs the implicit arm, and the paired CV-level difference. |
| `position_bias.csv` | Share picking Candidate 1; pick rate of the higher-class CV when first vs second; the class effect adjusted for position. |
| `consistency.csv` | Per model and pair: agreement with the majority answer across the repeated calls, and the change when the order swapped. |
| `sessions.csv` | Session 1 vs session 2 pick rates, odds ratio and mean change per pair. |
| `ratings_shortlist.csv` | Paired rating and shortlist differences with clustered CIs. |
| `reasons.csv` | How often the one-sentence reasons mention each keyword in `analysis.reason_keywords`. |
| `figures/*.png` | Pick rates with CIs, rating-difference distributions, position bias. |
| `report.md` | All of the above in plain English with tables. |
| `survey/` | The survey outputs (see below). |

Columns of a result row: `call_id`, `timestamp`, `session`, `model`, `model_type`,
`pair_id`, `cv_id`, `arm`, `order` (`xy` = the first variant of the arm was
Candidate 1), `rep`, `pos1_variant`, `pos2_variant`, `temperature`, `prompt_hash`,
`dry_run`, `ok`; on success `preferred_position`, `preferred_variant`,
`pos1_shortlist`, `pos1_rating`, `pos1_reason`, `pos2_*`, `generation_id`,
`served_model` (the model OpenRouter reports having used), `provider`, `finish_reason`,
`prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens`,
`cached_tokens`, `cost_usd`, `attempts`, `latency_s`; on failure `error_type`,
`error`, `http_status`, `attempts`.

## The statistics

The 20 calls on one pair, and the 60 on one base CV, are not independent: they
share the CV's wording. Treating them as independent would make confidence
intervals too narrow. So:

- **H1** (class effect above 50%): per model and arm, an intercept-only logistic
  regression of "picked the higher-class CV" with standard errors clustered by
  base CV gives the pick rate, its 95% CI and a p-value against 50%. As a
  cross-check, each base CV is reduced to one pick rate and a t-interval and a
  Wilcoxon test are run across the 15 CVs. The naive Wilson interval is shown for
  comparison only.
- **H2** (explicit effect smaller than implicit): a logistic regression on both
  class arms with an explicit-arm term, clustered by base CV; the odds ratio below
  1 means a smaller effect in the explicit arm. Cross-check: each base CV's
  implicit rate minus its explicit rate, paired t-test and Wilcoxon test.
- **Position bias**: the share of calls picking Candidate 1, and the class effect
  re-estimated with a (centred) term for whether the higher-class CV came first.
- **Consistency**: per pair, the share of its calls that agree with the majority
  answer, and the session-1 vs session-2 comparison.
- **Ratings and shortlisting**: within-call differences (higher-class minus other)
  with clustered CIs.

statsmodels has no frequentist mixed-effects logistic model, which is why the
clustered regressions plus CV-level aggregation are used instead.

## Human survey

`python -m pipeline analyze-survey --csv FILE` reads one row per participant and
pair. Required columns:

| Column | Values |
|---|---|
| `participant_id` | any id |
| `pair_id` | the pair shown, e.g. `cv01_implicit` |
| `first_variant` | the variant shown as Candidate 1: `high` or `low` |
| `chosen_position` | the candidate the participant preferred: `1` or `2` |
| `guess_job_1`, `guess_job_2` | guessed parental job of candidate 1 / 2: `professional`, `manual` or `unsure` |
| `guess_school_1`, `guess_school_2` | guessed school type: `private`, `state` or `unsure` |
| `rating_1`, `rating_2` (optional) | rating out of 10 |

`survey/sample_survey.csv` is a fake export in this format. The command reports the
human pick rate for the higher-class CV (CI clustered by participant), the
manipulation check (did people read the markers in the intended direction?), and a
per-pair comparison with each model's pick rate on the same pairs, with a Spearman
correlation across pairs. Outputs go to `results/survey/`.

## Tests

```bash
pytest
```

The tests use fake HTTP responses and a temporary folder; any attempt to reach the
network fails the test. They cover config loading, CV validation, pair building,
order swapping and mapping answers back to variants, JSON parsing and bad model
output, retries and the Retry-After rules, resume and `--retry-failed`, the budget
stop, session hash enforcement, the analysis on synthetic data and the survey.

## Caveats on interpreting the results

- Position bias can be large. The design sends each pair in both orders so it
  cancels in the pick rates, but check `position_bias.csv` before trusting a small
  class effect.
- With 15 base CVs the clustered intervals are wide, and one unusual CV can move
  a result; look at the per-CV table printed by `analyze`.
- Twelve model-by-arm comparisons are tested for H1; expect about one false
  positive at the 5% level by chance.
- The models behind a slug can change between sessions and providers; compare
  `served_model` and `provider` across sessions.
- Answers depend on the exact prompt; `prompt_hash` tells you which prompt each
  row was made with.
- Ratings are on a scale the models use freely; treat differences as ordinal.
- A dry run's numbers are random and mean nothing.

## OpenRouter documentation used

The API details the code relies on were checked against these pages:
[chat completions](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion),
[structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs),
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[router metadata](https://openrouter.ai/docs/guides/features/router-metadata),
[usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting),
[errors](https://openrouter.ai/docs/api_reference/errors-and-debugging),
[limits](https://openrouter.ai/docs/api_reference/limits),
[models list](https://openrouter.ai/docs/api/api-reference/models/get-models),
[endpoints for a model](https://openrouter.ai/docs/api/api-reference/endpoints/list-all-endpoints-for-a-model),
[current key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key) and
[generation stats](https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation).

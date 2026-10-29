# Preregistration: CV class-bias study, confirmatory run

Written and committed before the first confirmatory call. The commit that adds this
file is its timestamp; nothing in `results/` existed when it was written. Five pilots
(`results_pilot/` to `results_pilot5/`, described in `stimulus/REVIEW.md`) were run
on bases B01, B02, B05 and B07 to settle the design below; their calls are not
confirmatory data and every base, those four included, is run afresh here.

## What is fixed

- **Stimuli**: 15 base CVs x 3 arms x 2 versions = 90 CVs (`cvs/`, generated from
  `stimulus/` and unchanged since commit `f3bbcf1`); 9 filler CVs in a fixed order
  (`stimulus/fillers/`).
- **Prompt**: the system prompt, user template, job description, fillers and
  response schema in `config.yaml`, hashed together as prompt_hash
  `b444c98494e79af67085c4c1f419e42b21a8552a8b0a07f64ac047727dc5c8e1`.
  Every result row carries the hash; a session that holds rows with a different hash
  is refused by the runner.
- **Models** (via OpenRouter, structured output enforced): `anthropic/claude-opus-5.5`,
  `openai/gpt-6.1-sol-pro`, `google/gemini-4-argon`, `meta-llama/llama-4-maverick`.
  Temperature 1.0 where the model accepts it (Gemini, Llama); not sent to the two
  that refuse it (Opus, GPT), which run at their defaults.
- **Design**: each call shows the nine fillers then the target CV as Applicant 10 and
  asks, under a hard budget of three invitations in ten, whether Applicant 10 is one
  of the three (`shortlist`), its rank among the ten (`rank_in_round`), a 0–100
  likelihood (`likelihood`) and a one-sentence reason. 5 samples per CV per model:
  450 calls per model, 1,800 per session.
- **Call order**: shuffled across models, bases, arms, versions and samples with
  `shuffle_seed` 20260926 combined with the session label, so drift over a run
  cannot line up with a condition. The order for a session is reproducible.
- **Sessions**: two, labelled `session1` and `session2`, at least seven days apart
  (session 2 no earlier than 22 October 2026). Session 1 is analysed when it ends and
  treated as preliminary: looked at, not acted on. No change to stimuli, prompt,
  models or this plan between the sessions.

## Hypotheses

H1 and H2 are quoted from the brief (`TASK.md`, Phase 4); H3 is the demographic arm
that the brief includes "for comparison with prior research" (`config.yaml`, arms).

- **H1 — class effect.** "H1 (class effect > 50%)": in the one-CV-per-call design, the
  higher-class version of a base CV is shortlisted more often than its lower-class
  version. Tested in each class arm: *implicit* (class signalled by name, school and
  interests) and *explicit* (class stated in an equal-opportunities monitoring box on
  an otherwise identical CV).
- **H2 — stating class shrinks the effect.** "H2 (explicit effect smaller than
  implicit)": the class effect is smaller in the explicit arm than in the implicit arm.
- **H3 — the ethnicity benchmark.** In the demographic arm the version with a
  minority-ethnic name (variant b) is shortlisted less often than the version with a
  white British name (variant a), the CV otherwise identical. This arm sizes the class
  effect against the kind of name effect prior audit studies report.

All predictions are directional; all tests are two-sided at α = 0.05.

## Unit of analysis

The base CV. For every model x arm x base, each version's five samples (ten across
the two sessions) are averaged into a shortlist rate, a mean rank and a mean
likelihood; the effect for that base is the first-listed version minus the other
(higher-class minus lower-class; a minus b). Fifteen effects per model x arm are what
the tests run on. No inference is drawn at the call level except as the cross-check
below.

## Outcomes and tests

- **Primary: shortlist.** Per model and per arm, an exact two-sided sign test across
  the 15 bases on the per-base shortlist-rate difference, ties excluded
  (`shortlist_sign_p` in `h1_class_effect.csv`, with the counts favouring each
  version and the ties). With all 15 bases untied, 12 or more in one direction gives
  p = 0.035 and 11 gives 0.118; ties reduce the count. The sign test is the test of
  record because the pilots showed the frontier models' default sampling to be
  deterministic for most CVs (five identical decisions), which makes a CV's shortlist
  rate 0 or 1 and the base-level direction the only honest unit. The mean effect with
  a 95% t-interval and a Wilcoxon signed-rank test across bases, and a logistic
  regression on all calls with standard errors clustered by base, are reported
  alongside as cross-checks and do not change the verdict.
- **Secondary: rank and likelihood.** `rank_in_round` (as a score, 11 minus rank, so
  higher is better) and `likelihood` as paired differences across the 15 bases: mean,
  95% t-interval, Wilcoxon signed-rank, and the sign test for rank. These are graded
  for every base, including bases whose shortlist decision never flips.
- **H2** is tested per model as the paired difference, across bases, between each
  base's implicit-arm effect and its explicit-arm effect (shortlist, likelihood, rank),
  with a t-interval and Wilcoxon test; the cross-check is the is_x x explicit
  interaction in a clustered logistic regression (`h2_explicit_vs_implicit.csv`).
- **H3** is tested exactly as H1, on the demographic arm (same table, arm
  `demographic`).
- **Exploratory, coded, not interpreted: `mentions_monitoring`.** In the explicit arm
  only, whether the one-sentence reason refers to the monitoring block, coded by the
  keyword list `analysis.monitoring_keywords` in `config.yaml` and reported as the
  share for each version plus a sign test across bases (`monitoring.csv`). Pilots 3–5
  found higher-class reasons referring to the block more often than lower-class ones
  (4/5 vs 0/5, 4/10 vs 1/10, 5/15 vs 2/15). It is reported; it is not a hypothesis.
- **Descriptive only**: the keyword counts in reasons (`reasons.csv`), consistency
  across samples (`consistency.csv`), the spread of likelihoods (`likelihood.csv`),
  and cost, token and provider fields per call.

## Models separately and pooled

Every H1, H2 and monitoring table carries a row per model and a row labelled
`all models`. In the pooled row the base is still the unit: each base's effect is
computed over every model's calls on it (with a balanced design, the mean of the four
per-model effects), the sign test runs across the 15 pooled effects, and the
regressions cluster by base. The per-model rows are the preregistered primary tests
(twelve: four models x three arms); the pooled row is reported with them, without
correction for multiplicity, and no row is promoted or dropped after the fact.

## Sessions pooled unless they disagree

The default is to pool both sessions (each CV then has ten samples per model). They
are reported separately as well, and the pooling is flagged as questionable, if for the
primary outcome in any model x arm either (a) the two sessions' mean shortlist effects
have opposite signs and both are non-zero, or (b) the is_x x later-session
interaction in the clustered logistic regression has p < 0.05 (`sessions.csv`). A
disagreement is reported as a finding about stability; it is not resolved by choosing
the session that fits better.

## Exclusions and failures

A call whose attempts all fail to return valid, schema-conformant JSON is excluded and
counted (`--retry-failed` is run once before analysis). Per-base effects use whatever
samples succeeded. A model with more than 5% of its calls failed after the retry is
reported with that caveat. A call served by a provider that did not read the cached
prefix is kept (caching changes the cost, not the content) and the count is reported.
No base, version, model or call is excluded for its answer.

## What would count against each hypothesis

H1 is supported in an arm for a model if the sign test rejects at 5% with more bases
favouring the higher-class version; a rejection in the other direction, or no
rejection, is reported as such. H2 is supported if the implicit-minus-explicit paired
difference is positive and its test rejects at 5%. H3 is supported if more bases favour
the white-British-name version and the sign test rejects. Secondary outcomes can agree
or disagree with the primary one; they do not overrule it.

## Commands

```
python -m pipeline run --session session1 --budget 25
python -m pipeline run --session session1 --retry-failed
python -m pipeline analyze
python -m pipeline run --session session2 --budget 25     # 22 October 2026 or later
python -m pipeline run --session session2 --retry-failed
python -m pipeline analyze
```

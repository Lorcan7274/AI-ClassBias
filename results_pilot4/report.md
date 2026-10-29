# CV class-bias study: results

Generated 2026-10-14 20:31 UTC from `/home/user/AI-ClassBias/results_pilot4/results.jsonl`.

## Data

- 60 successful calls (0 failed calls excluded), 12 CVs from 2 base CVs, 1 models, sessions: pilot4.
- Each call shows the model the same fixed fillers and then one CV, and asks about that CV only: is it one of the three in ten invited to interview, where does it rank in the round, and how likely is it to be invited (0-100). Each CV is sampled several times per session.
- Arms and their variants: implicit = high vs low; explicit = high vs low; demographic = a vs b. In the tables, x is the first variant of each arm (for the class arms, the higher-class CV).
- Prompt hashes in the data: 0837f8d25d25.

How the tests deal with repeated calls: the calls on one base CV share its wording and are not independent, so the headline estimates use one number per base CV (its effect), and the cross-checks are regressions on all calls with standard errors clustered by base CV.

## Summary

Plain averages over all calls. `shortlist_diff` is the shortlist rate of the higher-class CV minus the other; `likelihood_diff` the same for the mean 0-100 likelihood.

| model                     | arm         | n_calls | shortlist_rate_x | shortlist_rate_y | shortlist_diff | mean_rank_x | mean_rank_y | mean_likelihood_x | mean_likelihood_y | likelihood_diff |
| ------------------------- | ----------- | ------- | ---------------- | ---------------- | -------------- | ----------- | ----------- | ----------------- | ----------------- | --------------- |
| anthropic/claude-opus-5.5 | demographic | 20      | 0.2              | 0                | 0.2            | 3.8         | 4           | 39                | 35.7              | 3.3             |
| anthropic/claude-opus-5.5 | explicit    | 20      | 0.2              | 0.5              | -0.3           | 3.8         | 3.5         | 39.5              | 44.5              | -5              |
| anthropic/claude-opus-5.5 | implicit    | 20      | 0                | 0                | 0              | 4           | 4           | 33.5              | 37                | -3.5            |

## H1: is the higher-class CV shortlisted more than the other?

`shortlist_effect` is the mean, across base CVs, of (higher-class CV's shortlist rate minus the other's), with a 95% t-interval and a Wilcoxon test against 0. `shortlist_cvs_favouring_x` counts the base CVs where the higher-class version was shortlisted more often, `..._y` the reverse, and `shortlist_sign_p` is the exact sign test on them: for a model whose decision never varies across samples (`deterministic_share` near 1) the share of yes answers is 0 or 1 per CV and this sign test, one decision per CV, is the test of record. `rank_effect` is the same on the rank in the round, turned so that positive favours the higher-class CV (places), and `likelihood_effect` on the 0-100 scale. The pooled columns are the clustered-regression cross-checks.

| model                     | arm         | n_cvs | deterministic_share | shortlist_effect | shortlist_ci_low | shortlist_ci_high | shortlist_t_p | shortlist_cvs_favouring_x | shortlist_cvs_favouring_y | shortlist_cvs_tied | shortlist_sign_p | rank_effect | rank_ci_low | rank_ci_high | rank_sign_p | likelihood_effect | likelihood_ci_low | likelihood_ci_high | pooled_odds_ratio | pooled_or_p |
| ------------------------- | ----------- | ----- | ------------------- | ---------------- | ---------------- | ----------------- | ------------- | ------------------------- | ------------------------- | ------------------ | ---------------- | ----------- | ----------- | ------------ | ----------- | ----------------- | ----------------- | ------------------ | ----------------- | ----------- |
| anthropic/claude-opus-5.5 | demographic | 2     | 0.75                | 0.2              | -2.341           | 2.741             | 0.5           | 1                         | 0                         | 1                  | 1                | 0.2         | -2.341      | 2.741        | 1           | 3.3               | -25.924           | 32.524             | 110639303204.101  | 0.972       |
| anthropic/claude-opus-5.5 | explicit    | 2     | 0.75                | -0.3             | -4.112           | 3.512             | 0.5           | 0                         | 1                         | 1                  | 1                | -0.3        | -4.112      | 3.512        | 1           | -5                | -55.825           | 45.825             | 0.25              | 0.072       |
| anthropic/claude-opus-5.5 | implicit    | 2     | 1                   | 0                |                  |                   |               | 0                         | 0                         | 2                  |                  | 0           |             |              |             | -3.5              | -47.972           | 40.972             |                   |             |

- anthropic/claude-opus-5.5, demographic: shortlist effect 20.0% (95% CI -234.1% to 274.1%, includes 0; t-test not significant at 5%). Sign test: 1 CVs favour the higher-class version, 0 the other, 1 tied, p = 1. Rank effect 0.2 places (sign test p = 1); likelihood effect 3.3 points (95% CI -25.9 to 32.5). Pooled odds ratio 110639303204.101, p = 0.972.
- anthropic/claude-opus-5.5, explicit: shortlist effect -30.0% (95% CI -411.2% to 351.2%, includes 0; t-test not significant at 5%). Sign test: 0 CVs favour the higher-class version, 1 the other, 1 tied, p = 1. Rank effect -0.3 places (sign test p = 1); likelihood effect -5 points (95% CI -55.8 to 45.8). Pooled odds ratio 0.25, p = 0.072.
- anthropic/claude-opus-5.5, implicit: shortlist effect 0.0% (95% CI  to , no interval; t-test no test possible). Sign test: 0 CVs favour the higher-class version, 0 the other, 2 tied, p =  (deterministic model: this is the test of record). Rank effect 0 places (sign test p = ); likelihood effect -3.5 points (95% CI -48 to 41). Pooled odds ratio , p = . Note: not enough variation to estimate the effect.

![class effects](figures/effects.png)

## H2: is the effect smaller when class is stated explicitly (explicit vs implicit)?

For each base CV, its implicit-arm effect minus its explicit-arm effect; the mean across CVs with a paired t-test and a Wilcoxon test. Above 0 means the explicit arm's effect is the smaller. `interaction_odds_ratio` is the clustered-regression cross-check (below 1 means the same thing).

| model                     | implicit_shortlist_effect | explicit_shortlist_effect | cv_level_mean_diff_implicit_minus_explicit | cv_level_ci_low | cv_level_ci_high | cv_level_t_p | cv_level_wilcoxon_p | implicit_likelihood_effect | explicit_likelihood_effect | likelihood_cv_level_mean_diff | likelihood_cv_level_t_p | interaction_odds_ratio | interaction_p | n_cvs_paired |
| ------------------------- | ------------------------- | ------------------------- | ------------------------------------------ | --------------- | ---------------- | ------------ | ------------------- | -------------------------- | -------------------------- | ----------------------------- | ----------------------- | ---------------------- | ------------- | ------------ |
| anthropic/claude-opus-5.5 | 0                         | -0.3                      | 0.3                                        | -3.512          | 4.112            | 0.5          | 1                   | -3.5                       | -5                         | 1.5                           | 0.874                   | 1.333                  | 1             | 2            |

- anthropic/claude-opus-5.5: implicit effect 0.0% vs explicit -30.0%; CV-level difference 30.0% (paired t-test p = 0.5, Wilcoxon p = 1). Interaction odds ratio 1.333 (95% CI 0 to inf), not significant at 5%.

## Consistency across the samples of each CV

`agreement_with_majority` is the share of a CV's samples that gave its most common answer (1 = always the same, 0.5 = a coin flip); `likelihood_sd` is the spread of its likelihoods. A model whose samples never disagree gives no information about its shortlist probability beyond yes or no.

| model                     | arm         | n_cvs | mean_agreement | cvs_fully_consistent | mean_likelihood_sd |
| ------------------------- | ----------- | ----- | -------------- | -------------------- | ------------------ |
| anthropic/claude-opus-5.5 | demographic | 4     | 0.9            | 3                    | 3.149              |
| anthropic/claude-opus-5.5 | explicit    | 4     | 0.9            | 3                    | 3.337              |
| anthropic/claude-opus-5.5 | implicit    | 4     | 1              | 4                    | 1.112              |

The full per-CV table is in `consistency.csv`.

## Session 1 vs session 2

Only one session so far, so there is nothing to compare yet.

## How the likelihoods are spread

If every CV gets a likelihood near the same value, the 0-100 scale is not discriminating and only the yes/no decision carries information.

| model                     | arm         | variant          | n_calls | mean | sd   | min | p10  | median | p90  | max | n_distinct_values | shortlist_rate |
| ------------------------- | ----------- | ---------------- | ------- | ---- | ---- | --- | ---- | ------ | ---- | --- | ----------------- | -------------- |
| anthropic/claude-opus-5.5 | demographic | y                | 10      | 35.7 | 4.9  | 30  | 30   | 37.5   | 40.2 | 42  | 4                 | 0              |
| anthropic/claude-opus-5.5 | demographic | x (higher-class) | 10      | 39   | 8.9  | 30  | 30   | 37.5   | 55   | 55  | 4                 | 0.2            |
| anthropic/claude-opus-5.5 | explicit    | y                | 10      | 44.5 | 10.6 | 30  | 34.5 | 45     | 55   | 55  | 3                 | 0.5            |
| anthropic/claude-opus-5.5 | explicit    | x (higher-class) | 10      | 39.5 | 8.8  | 25  | 34   | 37.5   | 55   | 55  | 4                 | 0.2            |
| anthropic/claude-opus-5.5 | implicit    | y                | 10      | 37   | 3.3  | 30  | 34.5 | 37.5   | 40   | 40  | 3                 | 0              |
| anthropic/claude-opus-5.5 | implicit    | x (higher-class) | 10      | 33.5 | 6.7  | 25  | 25   | 35     | 40   | 40  | 3                 | 0              |

![likelihoods](figures/likelihoods.png)

## What the reasons mention

Share of one-sentence reasons mentioning each keyword (analysis.reason_keywords in config.yaml), for the higher-class CVs (x) and the other CVs (y).

| model                     | arm         | n_reasons_x | x_pct | n_reasons_y | y_pct |
| ------------------------- | ----------- | ----------- | ----- | ----------- | ----- |
| anthropic/claude-opus-5.5 | demographic | 10          | 100   | 10          | 100   |
| anthropic/claude-opus-5.5 | explicit    | 10          | 100   | 10          | 100   |
| anthropic/claude-opus-5.5 | implicit    | 10          | 100   | 10          | 100   |

Per keyword (only keywords mentioned at least once):

| model                     | arm         | keyword       | x_mentions | x_pct | y_mentions | y_pct |
| ------------------------- | ----------- | ------------- | ---------- | ----- | ---------- | ----- |
| anthropic/claude-opus-5.5 | demographic | grade*        | 0          | 0     | 1          | 10    |
| anthropic/claude-opus-5.5 | demographic | a-level*      | 3          | 30    | 0          | 0     |
| anthropic/claude-opus-5.5 | demographic | interest*     | 4          | 40    | 6          | 60    |
| anthropic/claude-opus-5.5 | demographic | experience    | 5          | 50    | 7          | 70    |
| anthropic/claude-opus-5.5 | demographic | internship*   | 10         | 100   | 10         | 100   |
| anthropic/claude-opus-5.5 | demographic | professional* | 0          | 0     | 1          | 10    |
| anthropic/claude-opus-5.5 | explicit    | a-level*      | 3          | 30    | 3          | 30    |
| anthropic/claude-opus-5.5 | explicit    | interest*     | 7          | 70    | 5          | 50    |
| anthropic/claude-opus-5.5 | explicit    | experience    | 5          | 50    | 8          | 80    |
| anthropic/claude-opus-5.5 | explicit    | internship*   | 8          | 80    | 7          | 70    |
| anthropic/claude-opus-5.5 | explicit    | background    | 1          | 10    | 0          | 0     |
| anthropic/claude-opus-5.5 | explicit    | professional* | 2          | 20    | 2          | 20    |
| anthropic/claude-opus-5.5 | implicit    | school*       | 1          | 10    | 0          | 0     |
| anthropic/claude-opus-5.5 | implicit    | grade*        | 0          | 0     | 1          | 10    |
| anthropic/claude-opus-5.5 | implicit    | a-level*      | 0          | 0     | 4          | 40    |
| anthropic/claude-opus-5.5 | implicit    | interest*     | 4          | 40    | 5          | 50    |
| anthropic/claude-opus-5.5 | implicit    | experience    | 5          | 50    | 8          | 80    |
| anthropic/claude-opus-5.5 | implicit    | internship*   | 8          | 80    | 10         | 100   |
| anthropic/claude-opus-5.5 | implicit    | background    | 1          | 10    | 0          | 0     |
| anthropic/claude-opus-5.5 | implicit    | professional* | 2          | 20    | 3          | 30    |

## Explicit arm: does the reason refer to the monitoring block?

Coded from the one-sentence reasons with analysis.monitoring_keywords (words from the block itself: monitoring, free school meals, household earner, disregarded, and so on). `mentions_x_pct` is the share of reasons for the higher-class CVs that refer to it, `mentions_y_pct` for the other CVs; the difference is tested across base CVs. A model that announces it has set the block aside for one class of applicant and not the other is a finding in its own right. Recorded, not interpreted.

| model                     | n_calls_x | n_calls_y | mentions_x_pct | mentions_y_pct | cv_level_mean_diff | ci_low | ci_high | t_p   | wilcoxon_p | cvs_more_for_x | cvs_more_for_y | cvs_tied | sign_p | n_cvs |
| ------------------------- | --------- | --------- | -------------- | -------------- | ------------------ | ------ | ------- | ----- | ---------- | -------------- | -------------- | -------- | ------ | ----- |
| anthropic/claude-opus-5.5 | 10        | 10        | 40             | 10             | 0.3                | -0.971 | 1.571   | 0.205 | 0.5        | 2              | 0              | 0        | 0.5    | 2     |

## Caveats

- Calls on the same base CV are not independent; the headline estimates use one effect per base CV, but with 15 base CVs the intervals are wide and a single unusual CV can move a result.
- Twelve model-by-arm comparisons are tested; expect about one false positive at the 5% level by chance alone.
- The models may have changed between sessions (see `served_model` and `provider` in the results), and the answers depend on the exact prompt (`prompt_hash`).
- Models that were not sent a temperature (see `temperature` in the rows) sampled at their own default; where `deterministic_share` is near 1 their shortlist rate per CV is 0 or 1, read the sign test rather than the t-interval, and treat the five samples as evidence that the determinism is real rather than as five observations.
- The 0-100 likelihoods are numbers the models chose freely; treat them as ordinal.

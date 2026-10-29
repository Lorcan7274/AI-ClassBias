# Statistical analysis of record: sessions 1 and 2 pooled

Data: `results/results.jsonl`, 3,600 successful calls (prompt hash `b444c984…`):
session 1 on 14 October 2026, session 2 on 29 October 2026, fifteen days apart.
90 CVs = 15 bases × 3 arms × 2 versions, 4 models, 5 samples per CV per model per
session, so ten samples per CV per model pooled. The tests are those fixed in
`PREREGISTRATION.md` (commit `bcaf7c1`) before session 1; `results/analysis_session1.md`
is the single-session analysis that preceded this one. Additions beyond the
preregistration are labelled: the Holm correction (§3) and the sensitivity bounds (§7).

Unit: the base CV. For each model × arm × base, the first-listed version's shortlist
rate, mean rank and mean likelihood over its ten samples minus the other version's
(higher-class minus lower-class; white-British name minus minority-ethnic name).
Primary test: exact two-sided sign test across the 15 per-base shortlist differences,
ties excluded. Secondary: paired differences in rank (as a score, 11 − rank) and 0–100
likelihood, with 95% t-intervals and Wilcoxon signed-rank tests. Cross-checks:
logistic and linear regressions on all calls, standard errors clustered by base.
α = 0.05, two-sided throughout.

## 1. The two sessions, and the pooling rule

Session 2 ran on the same configuration and prompt hash. Three of the four models
were served by different hosts for part of it (GPT: Azure for 54 calls; Gemini:
Google AI Studio for 139; Llama: DigitalOcean and Parasail for all 450 instead of
Novita). Eleven Llama calls returned a JSON object missing the shortlist field and
failed validation; two of them failed again on the resume and succeeded on the
preregistered retry, so two calls were made three times, one more than the plan's
single retry. No call is excluded.

| model | shortlist rate s1 / s2 | mean rank s1 / s2 | mean likelihood s1 / s2 | CVs with 10 identical decisions |
|---|---|---|---|---|
| Claude Opus 5.5 | 0.45 / 0.44 | 3.75 / 3.75 | 41.9 / 42.4 | 84% |
| GPT 6.1 Sol Pro | 0.41 / 0.41 | 3.95 / 3.98 | 46.1 / 46.1 | 93% |
| Gemini 4 Argon | 0.33 / 0.34 | 4.16 / 4.17 | 42.2 / 42.3 | 97% |
| Llama 4 Maverick | 0.83 / **1.00** | 3.17 / **2.66** | 88.1 / 86.8 | 71% |

The three frontier models reproduced their session-1 behaviour to within 1.5
points. Llama did not: on its new hosts it shortlisted 99.6% of targets and placed
the target first of ten, above the two first-class fillers, in 83 of 450 calls. It
had used ranks 2–5 in session 1 and ranks 1–6 in session 2.

The preregistered disagreement rule (opposite signs in the two sessions, both
non-zero, or a session × version interaction at p < 0.05 on the primary outcome) is
triggered in four of the twelve model × arm cells: Claude's demographic arm, where
the effect is −2.7 points in session 1 and +1.3 in session 2 (interaction p = 0.38,
a sign flip around zero), and all three of Llama's arms (interaction p < 10⁻⁶ in
each, from the ceiling shift above). As the rule requires, those cells are reported
per session as well as pooled, and their pooled estimates are flagged. The
disagreement is itself a finding: the frontier models are stable instruments over a
fortnight; Llama, as served through OpenRouter, is not.

## 2. H1: is the higher-class version shortlisted more often? (implicit and explicit arms)

Primary test, per model and arm; "for high / for low / tied" counts the 15 bases.

| model | arm | for high / for low / tied | sign p | mean diff, pp (95% CI) |
|---|---|---|---|---|
| Claude | implicit | 0 / 3 / 12 | 0.25 | −4.0 (−9.8, +1.8) |
| Claude | explicit | 0 / 3 / 12 | 0.25 | −6.7 (−15.5, +2.1) |
| GPT | implicit | 0 / 1 / 14 | 1.00 | −0.7 (−2.1, +0.8) |
| GPT | explicit | 0 / 2 / 13 | 0.50 | −2.0 (−5.1, +1.1) |
| Gemini | implicit | 1 / 0 / 14 | 1.00 | +0.7 (−0.8, +2.1) |
| Gemini | explicit | 0 / 1 / 14 | 1.00 | −1.3 (−4.2, +1.5) |
| Llama (flagged) | implicit | 4 / 1 / 10 | 0.38 | +4.7 (−1.2, +10.5) |
| Llama (flagged) | explicit | 0 / 4 / 11 | 0.13 | −2.7 (−5.2, −0.1) |
| pooled | implicit | 5 / 3 / 7 | 0.73 | +0.2 (−2.0, +2.4) |
| pooled | explicit | 0 / 7 / 8 | **0.016** | −3.2 (−5.9, −0.5) |

**No preregistered per-model test rejects, in either session or pooled.** H1 is not
supported for any model. In the implicit arm the pooled estimate is zero to within
two points.

The pooled explicit arm rejects, against the direction of H1, as it did in session 1
with one more base: seven bases shortlisted the lower-class version more often and
none the reverse. The clustered odds ratio is 0.88 (0.80, 0.97), p = 0.010. The
graded measures agree, and with ten samples per CV each frontier model now shows it
on its own:

| explicit arm, likelihood (0–100) | effect (95% CI) | t p | Wilcoxon p |
|---|---|---|---|
| Claude | −2.2 (−3.6, −0.8) | 0.005 | 0.004 |
| GPT | −1.3 (−2.5, −0.1) | 0.041 | 0.046 |
| Gemini | −2.5 (−4.1, −0.8) | 0.006 | 0.008 |
| Llama (flagged) | −0.7 (−2.9, +1.4) | 0.48 | 0.51 |
| pooled | −1.7 (−2.3, −1.0) | <0.001 | 0.001 |

Pooled rank: −0.06 places (−0.11, −0.01), p = 0.022. The shortlist shifts sit in a
few bases (Claude: B07, B11, B12; GPT: B11, B12; Gemini: B01; Llama: B04, B06, B07,
B10); the likelihood effect is spread across most bases. In every frontier model ×
class-arm cell the likelihood effect has the same sign in both sessions.

The implicit arm, which stated nothing and only varied name, school and hobbies,
now also shows a small negative likelihood effect in two frontier models: Claude
−2.3 (−3.8, −0.7), p = 0.008; GPT −1.4 (−2.4, −0.3), p = 0.015; Gemini −0.9 (−2.5,
+0.6), n.s. Rank and shortlist do not move. Llama, flagged, is the one model with a
positive implicit-arm signal: rank +0.21 places (+0.08, +0.33), p = 0.003, sign test
10 bases to 2, p = 0.039; likelihood +3.5 (+0.4, +6.6), p = 0.030; shortlist n.s.
Session 1 alone gave Llama +0.12 places (p = 0.07) and +4.3 points (n.s.), session 2
+0.29 places; the pooled signal is real within Llama's data but comes from a model
that shortlisted everyone in session 2 and whose ranks moved with its host.

Reading: the frontier models do not prefer the higher-class candidate. On the
graded likelihood they score the higher-class version one to two and a half points
lower in both arms, and that tilt replicates across sessions; on the decision that
matters, the shortlist, only the explicit arm moves, by three points pooled, and only
when the models are pooled. Llama leans the other way on rank and likelihood in the
implicit arm, under the stability flag.

## 3. Multiplicity

Holm-adjusting the twelve preregistered sign tests leaves every adjusted p at 1.0.
The pooled explicit tests (sign p = 0.016, likelihood p < 0.001) are not among the
twelve; the likelihood result survives any correction, the sign test would not
survive a Bonferroni over the three pooled arms (0.016 × 3 = 0.048 does, just).

## 4. H2: is the class effect smaller when class is stated explicitly?

Per base, implicit-arm effect minus explicit-arm effect; positive means the explicit
effect is the smaller (more negative).

| model | shortlist diff (95% CI) | t p | likelihood diff (95% CI) | t p | interaction OR (95% CI) | p |
|---|---|---|---|---|---|---|
| Claude | +0.03 (−0.02, +0.08) | 0.26 | −0.0 (−1.4, +1.3) | 0.94 | 0.90 (0.75, 1.08) | 0.25 |
| GPT | +0.01 (−0.02, +0.05) | 0.43 | −0.1 (−0.9, +0.8) | 0.82 | 0.95 (0.83, 1.09) | 0.43 |
| Gemini | +0.02 (−0.01, +0.05) | 0.19 | +1.5 (−0.7, +3.8) | 0.16 | 0.91 (0.80, 1.04) | 0.18 |
| Llama (flagged) | +0.07 (+0.00, +0.14) | 0.044 | +4.2 (+0.4, +8.1) | 0.033 | 0.44 (0.24, 0.79) | 0.006 |
| pooled | +0.03 (+0.01, +0.06) | **0.025** | +1.4 (+0.3, +2.5) | **0.014** | 0.88 (0.79, 0.97) | **0.010** |

The pooled difference is positive on all three measures, so H2 as stated is met in
the pooled analysis. It is carried by Llama. For Claude and GPT the implicit and
explicit effects are the same size and sign (Claude: −2.3 and −2.2 likelihood
points), so there is no preference for the explicit statement to shrink. H2
presupposed a positive implicit effect; none exists, and the hypothesis is met only
in the arithmetic.

## 5. H3: the ethnicity benchmark (demographic arm)

| model | for white-British / for minority / tied | sign p | shortlist diff, pp (95% CI) | likelihood diff (95% CI) | rank diff (95% CI) |
|---|---|---|---|---|---|
| Claude (flagged) | 1 / 2 / 12 | 1.00 | −0.7 (−3.2, +1.9) | +0.0 (−0.6, +0.7) | −0.03 (−0.07, +0.00) |
| GPT | 0 / 2 / 13 | 0.50 | −3.3 (−9.1, +2.5) | −1.2 (−3.6, +1.2) | −0.02 (−0.11, +0.07) |
| Gemini | 0 / 1 / 14 | 1.00 | −0.7 (−2.1, +0.8) | −1.8 (−3.7, +0.1) | +0.01 (−0.05, +0.08) |
| Llama (flagged) | 2 / 2 / 11 | 1.00 | +0.7 (−3.2, +4.6) | +1.1 (−1.1, +3.4) | +0.02 (−0.07, +0.11) |
| pooled | 1 / 6 / 8 | 0.125 | −1.0 (−2.5, +0.5) | −0.5 (−1.5, +0.6) | −0.01 (−0.05, +0.04) |

No test rejects. The lean, such as it is, runs against the white-British name
(six bases to one pooled; Gemini's likelihood −1.8, p = 0.061; Claude's rank
−0.03 places, p = 0.055). H3 is not supported: at this precision no model treats the
two names differently, and an advantage for the white-British name of more than one
shortlist point pooled is excluded.

## 6. Exploratory: does the reason refer to the monitoring box?

Explicit arm only, `mentions_monitoring` coded by the preregistered keyword list.

| model | higher-class reasons | lower-class reasons | bases more / less / tied | sign p | Fisher p (calls) |
|---|---|---|---|---|---|
| Claude | 72 / 150 (48.0%) | 19 / 150 (12.7%) | 14 / 0 / 1 | <0.001 | 2 × 10⁻¹¹ |
| GPT | 0 / 150 | 0 / 150 | 0 / 0 / 15 | | |
| Gemini | 0 / 150 | 0 / 150 | 0 / 0 / 15 | | |
| Llama | 4 / 150 | 4 / 150 | 0 / 0 / 15 | | 1.0 |
| pooled | 76 / 600 (12.7%) | 23 / 600 (3.8%) | 14 / 0 / 1 | <0.001 | |

This replicated exactly: 36 of 75 against 9 of 75 in session 1, 36 of 75 against
10 of 75 in session 2. Claude says it set the monitoring answers aside ("the equal
opportunities monitoring answers played no part in this assessment") four times as
often when the box says professional parent and fee-paying school as when it says
manual-job parent, state school and free school meals, on fourteen of the fifteen
bases and never the reverse. Mentioning the box is not what lowers the score: within
Claude's higher-class answers, those that mention it are shortlisted at least as
often as those that do not. GPT and Gemini never refer to the box; Llama does so
rarely and symmetrically. Across the 3,600 reasons the word "school" appears three
times and "background" 208 times, at the same rate for both versions.

## 7. What the data rule out

Upper 95% limits on a higher-class advantage, from the preregistered intervals,
pooled over sessions:

| | shortlist (pp) | likelihood (points) | rank (places) |
|---|---|---|---|
| pooled, implicit | +2.4 | +0.8 | +0.06 |
| pooled, explicit | −0.5 | −1.0 | −0.01 |
| pooled, demographic | +0.5 | +0.6 | +0.04 |
| Claude, implicit | +1.8 | −0.7 | +0.01 |
| GPT, implicit | +0.8 | −0.3 | +0.00 |
| Gemini, implicit | +2.1 | +0.6 | +0.04 |
| Llama, implicit (flagged) | +10.5 | +6.6 | +0.33 |

A higher-class advantage of more than about two shortlist points pooled, or one to
two points in any frontier model, is incompatible with the data; in the explicit arm,
and on likelihood for Claude and GPT in the implicit arm, an advantage of any size is.

## 8. The human survey

Twelve responses had been received when the form was last exported (15 October):
ten would interview, two would not; mean likelihood 7.0 of 10; school guesses 6
private, 3 state, 3 "no idea"; nine respondents saw a higher-class version and
three a lower-class one. The manipulation check (private-school guesses, 5 of 7
against 1 of 2, Fisher p = 1.0) cannot be read at this size. The form remains open;
its export is analysed with `survey/form_responses.py`.

## 9. Conclusions

1. **H1 not supported.** No model shortlists the higher-class version of a CV more
   often than the lower-class version, in either arm, in either session or pooled.
   The pooled implicit estimate is +0.2 points with an interval of −2.0 to +2.4.
2. **A small, replicated tilt the other way when class is stated.** With the
   monitoring box filled in, the higher-class version is shortlisted 3.2 points less
   often pooled (seven bases to none), scored 1.7 points lower, and ranked a
   sixteenth of a place lower; each frontier model shows the likelihood effect on its
   own, and the sign held in both sessions in every frontier cell.
3. **On the graded score the frontier models tilt against the higher-class version
   even in the implicit arm** (Claude −2.3, GPT −1.4 points), without any movement on
   the shortlist decision.
4. **H2 is met in arithmetic and empty in substance**: the explicit effect is
   "smaller" because it is negative, and the difference is carried by Llama.
5. **H3 not supported.** No name effect; the lean is against the white-British name.
6. **Claude announces that it ignored the stated class information four times as
   often for the privileged version** (48% vs 13%, fourteen bases to none, replicated
   to the call in session 2). No other model does.
7. **Stability.** Claude, GPT and Gemini are stable instruments over fifteen days.
   Llama is not: its host changed and it moved to the ceiling, and under the
   preregistered rule its pooled rows are flagged. Its positive implicit-arm rank
   and likelihood effects are reported with that flag and should not be weighed
   against the frontier models' null.

Cost of the two sessions: $29.50.

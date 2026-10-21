# Statistical analysis: session 1 (preliminary under the preregistration)

Data: `results/results.jsonl`, 1,800 successful calls on 14 October 2026 (prompt hash
`b444c984…`), 90 CVs = 15 bases × 3 arms × 2 versions, 4 models, 5 samples per CV
per model. Three calls failed on a credits error and were re-made; no call failed to
parse. The tests are those fixed in `PREREGISTRATION.md` (commit `bcaf7c1`) before the
run. The preregistration pools two sessions; session 2 has not run, so this is the
single-session analysis it describes as preliminary. Nothing below was chosen after
seeing the data except the Holm correction in §3, added as a robustness check, and
the sensitivity bounds in §7, which are read off the preregistered intervals.

Unit: the base CV. For each model × arm × base, the first-listed version's shortlist
rate, mean rank and mean likelihood over its five samples minus the other version's
(higher-class minus lower-class; white-British name minus minority-ethnic name).
Primary test: exact two-sided sign test across the 15 per-base shortlist differences,
ties excluded. Secondary: paired differences in rank (as a score, 11 − rank) and 0–100
likelihood, with 95% t-intervals and Wilcoxon signed-rank tests. Cross-checks:
logistic and linear regressions on all calls, standard errors clustered by base.
α = 0.05, two-sided throughout.

## 1. How the instrument behaved

| model | shortlist rate | mean rank | mean likelihood | CVs with 5 identical decisions |
|---|---|---|---|---|
| Claude Opus 5.5 | 0.45 | 3.75 | 41.9 | 89% |
| GPT 6.1 Sol Pro | 0.41 | 3.95 | 46.1 | 94% |
| Gemini 4 Argon | 0.33 | 4.16 | 42.2 | 99% |
| Llama 4 Maverick | 0.83 | 3.17 | 88.1 | 74% |

Targets were placed at ranks 2–5 only; the two strongest fillers always took the
first two places. The three frontier models shortlisted close to the stated three in
ten and gave the same decision on nearly every repeat, so each base contributes a
0 or a 1 per version and most bases tie: this is why the preregistration made the
sign test the test of record. Llama shortlisted 83% of targets with a median
likelihood of 100, i.e. it sits at the ceiling; its tests are reported but carry
little information. The models' one-sentence reasons almost never cite the planted
markers: across 1,800 reasons the word "school" appears once and "background" 40
times, at the same rate for both versions (reasons.csv).

## 2. H1: is the higher-class version shortlisted more often? (implicit and explicit arms)

Primary test, per model and arm. "for high / for low / tied" counts bases.

| model | arm | high rate | low rate | for high / for low / tied | sign p | mean diff (95% CI) |
|---|---|---|---|---|---|---|
| Claude | implicit | 0.44 | 0.45 | 0 / 1 / 14 | 1.00 | −1.3 pp (−4.2, +1.5) |
| Claude | explicit | 0.43 | 0.52 | 0 / 3 / 12 | 0.25 | −9.3 pp (−21.1, +2.4) |
| GPT | implicit | 0.39 | 0.40 | 0 / 1 / 14 | 1.00 | −1.3 pp (−4.2, +1.5) |
| GPT | explicit | 0.41 | 0.44 | 0 / 1 / 14 | 1.00 | −2.7 pp (−8.4, +3.1) |
| Gemini | implicit | 0.33 | 0.32 | 1 / 0 / 14 | 1.00 | +1.3 pp (−1.5, +4.2) |
| Gemini | explicit | 0.33 | 0.33 | 0 / 0 / 15 | no test | 0.0 pp |
| Llama | implicit | 0.84 | 0.77 | 3 / 1 / 11 | 0.63 | +6.7 pp (−4.1, +17.5) |
| Llama | explicit | 0.79 | 0.84 | 0 / 4 / 11 | 0.13 | −5.3 pp (−10.4, −0.3) |
| pooled | implicit | 0.50 | 0.49 | 4 / 3 / 8 | 1.00 | +1.3 pp (−1.7, +4.4) |
| pooled | explicit | 0.49 | 0.53 | 0 / 6 / 9 | **0.031** | −4.3 pp (−8.1, −0.6) |

**No preregistered per-model test rejects.** H1 is not supported in either arm for
any model. In the implicit arm the estimates are within ±1.5 points for the three
frontier models, with 14 of 15 bases tied in each.

The pooled explicit arm rejects, in the direction opposite to H1: six bases
shortlisted the lower-class version more often and none the reverse. The
graded measures agree and are more precise:

| pooled, explicit arm | effect (95% CI) | t p | Wilcoxon p |
|---|---|---|---|
| likelihood (0–100) | −2.4 (−3.5, −1.3) | <0.001 | 0.003 |
| rank score (places) | −0.08 (−0.15, −0.02) | 0.018 | 0.016 |
| clustered logistic OR, shortlist | 0.84 (0.73, 0.96) | 0.013 | |

Per model, the likelihood difference in the explicit arm is negative in all four
(Claude −3.3, CI −5.0 to −1.5; GPT −1.4; Gemini −1.6; Llama −3.2), and is the only
per-model secondary result that rejects (Claude explicit, t p = 0.001; Claude
implicit −1.7, CI −3.1 to −0.2, p = 0.028). The explicit-arm shortlist shifts come
from three bases in Claude (B07, B11, B12), one in GPT (B11) and four in Llama
(B04, B06, B07, B10); Gemini never moved.

Reading: when parents' occupation and school type are stated in a monitoring box,
the models score the applicant with the professional parent and the fee-paying
school slightly lower than the same CV with the manual-job parent and the state
school. The size is two to three points on a 100-point scale and about a twelfth of
a rank place. It is consistent across models in sign and across the three measures,
but it clears the 5% threshold only when the models are pooled.

## 3. Multiplicity

The preregistration names twelve primary tests (4 models × 3 arms) without
correction and the pooled row as reported alongside. Holm-adjusting the twelve
sign tests leaves every adjusted p at 1.0 (two are untestable: Gemini's explicit and
demographic arms, all ties). The pooled explicit sign test (p = 0.031) and the pooled
explicit likelihood test (p < 0.001) are not among the twelve; the likelihood result
would survive any reasonable correction, the sign test would not.

## 4. H2: is the class effect smaller when class is stated explicitly?

Per base, implicit-arm effect minus explicit-arm effect; positive means the explicit
effect is the smaller (more negative).

| model | shortlist diff (95% CI) | t p | likelihood diff (95% CI) | t p | interaction OR (95% CI) | p |
|---|---|---|---|---|---|---|
| Claude | +0.08 (−0.02, +0.18) | 0.11 | +1.6 (−0.0, +3.3) | 0.053 | 0.73 (0.50, 1.06) | 0.09 |
| GPT | +0.01 (−0.05, +0.08) | 0.67 | −0.0 (−1.7, +1.7) | 0.97 | 0.95 (0.74, 1.21) | 0.67 |
| Gemini | +0.01 (−0.02, +0.04) | 0.33 | +1.2 (−1.9, +4.4) | 0.42 | 0.94 (0.84, 1.06) | 0.30 |
| Llama | +0.12 (−0.02, +0.26) | 0.08 | +7.5 (−2.0, +17.0) | 0.11 | 0.46 (0.21, 0.97) | 0.04 |
| pooled | +0.06 (+0.00, +0.11) | **0.045** | +2.6 (+0.2, +5.0) | **0.037** | 0.80 (0.65, 0.98) | **0.027** |

The pooled difference is positive and significant on all three measures, so the
preregistered statement of H2 ("explicit effect smaller than implicit") is met in
the pooled analysis. But H2 presupposed a positive class effect that stating class
would shrink. What the data show is an implicit effect of zero and an explicit effect
below zero. H2 is therefore technically supported and substantively empty: stating
class did not reduce a preference for the higher-class candidate, it introduced a
small penalty against them. Per model, only Llama's interaction reaches 5%.

## 5. H3: the ethnicity benchmark (demographic arm)

| model | white-British rate | minority-ethnic rate | for a / for b / tied | sign p | likelihood diff (95% CI) | rank diff (95% CI) |
|---|---|---|---|---|---|---|
| Claude | 0.43 | 0.45 | 0 / 1 / 14 | 1.00 | +0.2 (−1.1, +1.5) | −0.08 (−0.15, −0.01) |
| GPT | 0.40 | 0.43 | 0 / 2 / 13 | 0.50 | −1.1 (−3.2, +1.1) | −0.01 (−0.11, +0.09) |
| Gemini | 0.33 | 0.33 | 0 / 0 / 15 | no test | −0.7 (−2.2, +0.7) | +0.07 (−0.08, +0.22) |
| Llama | 0.87 | 0.85 | 2 / 2 / 11 | 1.00 | −0.2 (−4.1, +3.8) | 0.00 (−0.13, +0.13) |
| pooled | 0.51 | 0.52 | 1 / 5 / 9 | 0.22 | −0.5 (−1.5, +0.6) | −0.01 (−0.08, +0.06) |

No model favours the white-British name on any measure. The one interval that
excludes zero is Claude's rank difference, a twelfth of a place against the
white-British name, with the sign test at p = 0.062. H3 is not supported; the
benchmark effect that audit studies report for human recruiters does not appear
here at the precision available.

## 6. Exploratory: does the reason refer to the monitoring box?

Explicit arm only, `mentions_monitoring` coded by the preregistered keyword list.

| model | higher-class reasons | lower-class reasons | bases more / less / tied | sign p | Fisher p (calls) |
|---|---|---|---|---|---|
| Claude | 36 / 75 (48%) | 9 / 75 (12%) | 12 / 0 / 3 | <0.001 | 2 × 10⁻⁶ |
| GPT | 0 / 75 | 0 / 75 | 0 / 0 / 15 | | |
| Gemini | 0 / 75 | 0 / 75 | 0 / 0 / 15 | | |
| Llama | 3 / 75 | 3 / 75 | 0 / 0 / 15 | | 1.0 |
| pooled | 39 / 300 (13%) | 12 / 300 (4%) | 12 / 0 / 3 | <0.001 | 1 × 10⁻⁴ |

This is the clearest result in the data and it belongs to one model. Claude states
that it set the monitoring information aside ("the equal opportunities monitoring
answers played no part in this assessment") four times as often when the box says
professional parent and fee-paying school as when it says manual-job parent and
state school, and does so for twelve of the fifteen bases with no base the other
way. Mentioning the box is not what lowers the score: within Claude's higher-class
answers, those that mention it were shortlisted slightly more often (50%) than those
that do not (36%). GPT and Gemini never refer to the box; Llama does so rarely and
symmetrically. The pattern held in the three pilots that preceded the run (4/5 vs
0/5, 4/10 vs 1/10, 5/15 vs 2/15) and is now established at n = 150. It was
preregistered as coded and uninterpreted; the interpretation is for the write-up.

## 7. What the data rule out

The upper 95% limits on a higher-class advantage, from the preregistered intervals:

| | shortlist (pp) | likelihood (points) | rank (places) |
|---|---|---|---|
| pooled, implicit | +4.4 | +2.1 | +0.05 |
| pooled, explicit | −0.6 | −1.3 | −0.02 |
| pooled, demographic | +1.1 | +0.6 | +0.06 |
| Claude, implicit | +1.5 | −0.2 | +0.02 |
| GPT, implicit | +1.5 | +0.6 | +0.01 |
| Gemini, implicit | +4.2 | +1.5 | +0.04 |
| Llama, implicit | +17.5 | +10.2 | +0.25 |

So a higher-class advantage of more than about four shortlist points pooled, or
one and a half points in Claude or GPT, is incompatible with the data; in the
explicit arm an advantage of any size is. Llama's interval is uninformative. For
the sign test, with fifteen bases untied, twelve in one direction is the smallest
count that rejects at 5%; with nine to fourteen ties, as here, no count can.

## 8. The human survey

Twelve responses to the online form as of 15 October: ten would interview the
candidate, two would not; mean likelihood 7.0 of 10; school guesses 6 private, 3
state, 3 "no idea". Nine respondents saw a higher-class version, three a lower-class
one; nine of the thirty CVs have been seen. Among those who guessed a school, 5 of 7
shown the higher-class version said private against 1 of 2 shown the lower-class
version (Fisher p = 1.0). Nothing can be concluded at this size; the manipulation
check needs roughly a hundred responses before the private/state split per version
is informative.

## 9. Conclusions, session 1

1. H1 not supported. No model shortlists, ranks or scores the higher-class version
   of a CV above the lower-class version in the implicit arm; intervals exclude an
   advantage above 1.5 points for Claude and GPT.
2. In the explicit arm the direction is reversed and small: pooled across models the
   higher-class version is shortlisted 4 points less often, scored 2.4 points lower
   and ranked a twelfth of a place lower; consistent in sign across all four models,
   significant only pooled.
3. H2 is met as stated and empty in substance: the explicit effect is "smaller" only
   because it is negative.
4. H3 not supported: no name effect on any measure.
5. Claude announces that it ignored the stated class information four times as often
   for the privileged version (48% vs 12%, p < 0.001), an asymmetry no other model
   shows.
6. Llama is at the ceiling and contributes little; the frontier models are near-
   deterministic, which makes ties the norm and the sign test the right test.

Session 2, when run, will double the samples per CV and test stability; the
preregistration's pooling rule applies then.

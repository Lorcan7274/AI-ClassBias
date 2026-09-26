# Task: make the pipeline research-grade

The current code works end to end in dry-run mode: `run_pipeline.py`, `analyze.py`, `make_dummy_cvs.py`.
Upgrade it in the phases below. Work one phase at a time. After each phase, run the tests and a dry run,
then summarise what changed before moving on. Read CLAUDE.md first. Its rules apply throughout.

Start by reading all the existing code and telling me your plan for each phase. Wait for my OK before coding.

---

## Phase 1: Project structure and config
- Move all settings (models, reps, temperature, job description, system prompt, user prompt template,
  arms) out of the Python file into `config.yaml`.
- Save a SHA-256 hash of the prompt template and job description with every result row. That way, if
  the prompt changes between sessions, it shows up in the data.
- Add `.env` support for `OPENROUTER_API_KEY` (python-dotenv) and a `.gitignore`.
- Organise the code as a small package (for example `pipeline/` with `config.py`, `cvs.py`, `client.py`,
  `runner.py`, `analysis.py`) and a single CLI entry point with subcommands:
  `validate-cvs`, `preflight`, `run`, `analyze`, `make-dummy-cvs`.

## Phase 2: CV validation (important for the study's validity)
`validate-cvs` should:
- Check that every base CV has all 6 variant files, and report anything missing or misnamed.
- Diff each pair (using difflib) and print exactly which lines differ. **Flag any pair where the
  difference goes beyond the intended field.** The whole study depends on pairs being identical
  except for the one marker.
- Warn if the variants in a pair differ in length by more than a few percent. Length alone can
  influence models.
- Warn if a CV file contains words like "high", "low", "variant", or the arm name, which could
  leak the condition to the model.
- Save a validation report to `results/cv_validation.txt`.

## Phase 3: A more robust runner
- `preflight`: for each configured model, check with the OpenRouter models API that the model exists and
  supports structured outputs. Verify the right endpoint and fields in the docs first. Then make ONE tiny test
  call per model, only when I pass `--allow-paid`.
- Run calls concurrently, with a configurable number of workers and a rate limit, and retry with backoff
  on 429 and 5xx errors. Writes to the results file must stay safe with multiple threads.
- Keep the resume behaviour (skip calls that already succeeded). Add `--retry-failed` to re-run only failed rows.
- Save the full raw API response for each call in a separate file (`results/raw/<call_id>.json`), and put a
  unique `call_id` in the main results row.
- Record the served model, provider, token usage, and cost. Check the OpenRouter docs for which response
  fields actually hold these. Add a `--budget` flag that stops the run once the running total passes a limit.
- Show a progress bar (tqdm) and print a summary at the end: calls done, failures by error type, total cost.
- Enforce `session` labels. Refuse to run if the same session label already holds rows with a
  different prompt hash.

## Phase 4: Analysis that actually tests the hypotheses
Keep the current descriptive tables, and add:
- **H1 (class effect > 50%):** for each model, a test that respects the fact that repeated calls on the
  same base CV are not independent. For example, aggregate to base-CV level, or use logistic regression
  with standard errors clustered by `cv_id`, or a mixed-effects model with a random effect for `cv_id`.
  Explain the choice in a comment and report 95% confidence intervals.
- **H2 (explicit effect smaller than implicit):** a direct test comparing the implicit and explicit arms
  for each model (for example an interaction term, or a paired comparison at CV level).
- **Position bias:** pick rate for position 1 vs position 2, for each model, plus a check of whether the
  class effect still holds after controlling for position.
- **Consistency:** for each pair, how often the model gave the same answer across its 20 calls; also whether
  results differ between session 1 and session 2.
- **Ratings and shortlisting:** paired comparison of high vs low ratings, and shortlist rates.
- **Reasons text:** count how often the 1-sentence reasons mention class-related terms (school, university,
  interests, experience, etc.). Keep the keyword list in config so we can edit it.
- **Plots** (matplotlib) saved to `results/figures/`: pick rate with CIs per model per arm, rating difference
  distributions, and position bias.
- Write a `results/report.md` summarising all of the above in plain English, with tables.

## Phase 5: Human survey comparison
- Add an `analyze-survey` command that reads a CSV exported from our survey tool. Define and document the
  expected columns in the README, and include a sample CSV with fake data.
- Report: the human pick rate for high vs low, the manipulation check (did people guess parental job and school
  type in the intended direction?), and a side-by-side comparison of human and model pick rates on the same pairs.

## Phase 6: Tests and docs
- pytest tests with the API mocked. Cover: pair building, order swapping and mapping the answer back to the
  right variant, JSON parsing and validation (including bad model output), resume logic, and the budget stop.
- A README covering: setup, how to add CVs, the full command sequence for running the study, what each
  output file contains, and the caveats on interpreting the results.

## Definition of done
- `pytest` passes.
- A full dry run on the dummy CVs works from start to finish (validate, run on both sessions, analyze, report).
- No real API calls were made unless I explicitly approved them.

# CV bias pipeline

Sends pairs of CVs to models via OpenRouter and analyses which one they prefer.

## Parts

- `config.yaml` – all settings: models, arms, reps, prompts, CV checks, analysis keywords, runner limits
- `pipeline/` – the code
  - `config.py` – loads and checks `config.yaml`, reads the API key from `.env`
  - `cvs.py` – reads `cvs/`, builds pairs, writes dummy CVs
  - `validation.py` – checks the CV files (names, pair diffs, length, leak words)
  - `client.py` – OpenRouter calls, retries, rate limit
  - `runner.py` – runs a session with workers, resume, budget, raw response files
  - `preflight.py` – checks key, models and providers before a real run
  - `analysis.py`, `stats.py` – tables, tests, figures, `report.md`
  - `survey.py` – human survey CSV vs the models
  - `cli.py` – the commands
- `cvs/` – CV files, `<cv_id>_<arm>_<variant>.txt`
- `results/` – outputs (`results.jsonl` is append-only; dry runs go to `results/dry_run/`)
- `survey/sample_survey.csv` – survey format example
- `tests/` – `pytest`

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENROUTER_API_KEY
```

## Run

Dry run (no API calls):

```bash
python -m pipeline make-dummy-cvs
python -m pipeline validate-cvs
python -m pipeline run --session day1 --dry-run
python -m pipeline run --session day2 --dry-run
python -m pipeline analyze --dry-run
python -m pipeline analyze-survey --csv survey/sample_survey.csv --dry-run
```

Real run:

```bash
python -m pipeline validate-cvs
python -m pipeline preflight               # free checks
python -m pipeline preflight --allow-paid  # one tiny paid call per model
python -m pipeline run --session day1 --limit 5
python -m pipeline run --session day1 --budget 20
python -m pipeline run --session day2
python -m pipeline analyze
python -m pipeline analyze-survey --csv <export.csv>
```

Other flags: `run --workers N`, `run --retry-failed`. `python -m pipeline --help` lists everything.

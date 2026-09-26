"""The single entry point:  python -m pipeline [--config FILE] <command> [options]

Commands:
  make-dummy-cvs   write placeholder CVs into cvs/ for testing
  validate-cvs     check the CV files: names, pair differences, lengths, leak words
  preflight        check config, key, CVs and the models before a real run
  run              send CV pairs to the models and save one row per call
  analyze          summarise the results

Trying the whole pipeline for free on placeholder CVs:
  python -m pipeline make-dummy-cvs
  python -m pipeline validate-cvs
  python -m pipeline run --session day1 --dry-run
  python -m pipeline run --session day2 --dry-run
  python -m pipeline analyze --dry-run

A real session (paid API calls; the key is read from .env):
  python -m pipeline validate-cvs
  python -m pipeline preflight                 # free checks only
  python -m pipeline preflight --allow-paid    # plus one tiny test call per model
  python -m pipeline run --session day1 --limit 5      # a few real calls first
  python -m pipeline run --session day1 --budget 20    # the rest, stopping at $20
  python -m pipeline run --session day1 --retry-failed
  python -m pipeline analyze
"""

from __future__ import annotations

import argparse
import sys

from pipeline import analysis, cvs, preflight, runner, validation
from pipeline.client import DryRunClient, OpenRouterClient
from pipeline.config import DEFAULT_CONFIG_PATH, ConfigError, load_config, read_api_key


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m pipeline", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH),
                        help="settings file (default: config.yaml in the project folder)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("make-dummy-cvs", help="write placeholder CVs for testing")
    p.add_argument("--n-cvs", type=int, default=15, help="number of base CVs (default 15)")
    p.add_argument("--overwrite", action="store_true",
                   help="write even though the CV folder already holds .txt files")

    sub.add_parser("validate-cvs", help="check the CV files: names, pair differences, lengths, leak words")
    p = sub.add_parser("preflight", help="check config, key, CVs and the models before a real run")
    p.add_argument("--allow-paid", action="store_true", help="also make one tiny paid test call per model")

    p = sub.add_parser("run", help="send CV pairs to the models and save one row per call")
    p.add_argument("--session", required=True, help="label for this run date, e.g. day1")
    p.add_argument("--dry-run", action="store_true",
                   help="no API calls: fake answers, saved under results/dry_run/")
    p.add_argument("--limit", type=int, help="only make this many calls (for testing)")
    p.add_argument("--workers", type=int, help="calls in flight at once (default: runner.workers in config.yaml)")
    p.add_argument("--budget", type=float, help="stop once this run has cost more than this many USD")
    p.add_argument("--retry-failed", action="store_true", help="only re-run calls whose attempts all failed")

    p = sub.add_parser("analyze", help="summarise the results")
    p.add_argument("--dry-run", action="store_true", help="analyse the dry-run results instead of the real ones")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        sys.exit(f"Problem in {args.config}: {e}")

    if args.command == "make-dummy-cvs":
        make_dummy_cvs(cfg, args)
    elif args.command == "validate-cvs":
        validate_cvs(cfg)
    elif args.command == "preflight":
        # The .env file is looked for next to the config file.
        if not preflight.run_preflight(cfg, read_api_key(cfg.path.parent), allow_paid=args.allow_paid):
            sys.exit(1)
    elif args.command == "run":
        run(cfg, args)
    elif args.command == "analyze":
        analysis.analyze(cfg, dry_run=args.dry_run)


def make_dummy_cvs(cfg, args):
    if args.n_cvs < 1:
        sys.exit("--n-cvs must be at least 1")
    try:
        written = cvs.make_dummy_cvs(cfg.cv_dir, cfg.arms, n_cvs=args.n_cvs, overwrite=args.overwrite)
    except (FileExistsError, ValueError) as e:
        sys.exit(str(e))
    print(f"Wrote {len(written)} placeholder CVs to {cfg.cv_dir}")


def validate_cvs(cfg):
    result = validation.validate_cvs(cfg)
    report = validation.format_report(cfg, result)
    print(report)
    print(f"Report saved to {validation.save_report(cfg, report)}")
    if result.errors:
        sys.exit(1)


def check_cvs_before_run(cfg, dry_run):
    """Run the CV checks and save the report. Returns a problem for a real run, or None."""
    result = validation.validate_cvs(cfg)
    path = validation.save_report(cfg, validation.format_report(cfg, result))
    if not result.errors:
        return None
    message = f"the CV check found {len(result.errors)} error(s): run validate-cvs, or see {path}"
    if dry_run:
        print(f"WARNING: {message}. Continuing because this is a dry run.")
        return None
    return message


def run(cfg, args):
    if not args.session.strip():
        sys.exit("--session needs a label, e.g. day1")
    if args.limit is not None and args.limit < 1:
        sys.exit("--limit must be at least 1")
    if args.workers is not None and args.workers < 1:
        sys.exit("--workers must be at least 1")
    if args.budget is not None and args.budget <= 0:
        sys.exit("--budget must be more than 0")

    cv_problem = check_cvs_before_run(cfg, args.dry_run)
    if args.dry_run:
        client = DryRunClient()
    else:
        # Refuse to spend money on a set-up that still has placeholders or CV errors in it.
        problems = cfg.placeholder_problems() + ([cv_problem] if cv_problem else [])
        pairs, _ = cvs.load_pairs(cfg.cv_dir, cfg.arms)
        dummies = cvs.placeholder_pairs(pairs)
        if dummies:
            problems.append(f"{len(dummies)} CV pair(s) contain the word PLACEHOLDER, e.g. {dummies[0]}")
        api_key = read_api_key(cfg.path.parent)
        if not api_key:
            problems.append("OPENROUTER_API_KEY is not set (copy .env.example to .env and add your key)")
        if problems:
            sys.exit("Not starting a real run:\n  - " + "\n  - ".join(problems)
                     + "\nUse --dry-run to test without API calls.")
        client = OpenRouterClient(api_key, timeout=cfg.request_timeout, max_retries=cfg.max_retries,
                                  calls_per_minute=cfg.calls_per_minute)

    try:
        stats = runner.run_session(cfg, args.session.strip(), client, dry_run=args.dry_run, limit=args.limit,
                                   workers=args.workers, budget=args.budget, retry_failed=args.retry_failed)
    except (RuntimeError, cvs.CVFileError) as e:
        sys.exit(str(e))
    if stats.stopped:
        sys.exit(2)

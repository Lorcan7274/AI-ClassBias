"""Load and check config.yaml, and read the API key.

All study settings live in config.yaml so they sit in one place instead of being
buried in Python code. This module reads that file, checks it for mistakes that
would otherwise only show up halfway through a paid run, and returns a Config.
"""

from __future__ import annotations

import os
import re
import string
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import dotenv_values

# config.yaml sits in the project folder, one level above this package.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.yaml"

MODEL_TYPES = ("frontier", "open_source")

# The user prompt template must use exactly these {placeholders}.
TEMPLATE_FIELDS = {"job", "cv1", "cv2"}

# Arm and variant names become part of CV file names (cv01_implicit_high.txt),
# which are split on "_", so the names themselves must not contain "_".
NAME_PATTERN = re.compile(r"[A-Za-z0-9-]+")

# Every setting config.yaml may contain. Anything else is almost certainly a typo
# (e.g. "temprature"). Silently ignoring a typo could run a whole session with the
# wrong settings, so we stop with an error instead.
TOP_LEVEL_KEYS = {"models", "arms", "reps", "temperature", "shuffle_seed", "prompts", "paths", "runner", "cv_checks"}
PROMPT_KEYS = {"job_description", "system_prompt", "user_prompt_template"}
PATH_KEYS = {"cv_dir", "results_dir"}
RUNNER_KEYS = {"workers", "calls_per_minute", "max_retries", "request_timeout"}
CV_CHECK_KEYS = {"expected_base_cvs", "section_headings", "allowed_sections", "max_length_difference_pct", "leak_words"}

# The lines of a CV before its first section heading (name and contact details).
HEADER_SECTION = "header"


def heading_key(text) -> str:
    """How section headings are compared: ignoring capital letters, surrounding spaces,
    a leading "#" and a final ":". So "EDUCATION", "Education:" and "## Education" all match."""
    return text.strip().lstrip("#").strip().rstrip(":").strip().casefold()


class ConfigError(Exception):
    """config.yaml is missing something, or has a value the pipeline can't use."""


@dataclass
class ModelSpec:
    id: str    # exact OpenRouter model slug
    type: str  # "frontier" or "open_source"

    def is_placeholder(self) -> bool:
        return self.id.startswith("PUT_")


@dataclass
class Config:
    path: Path                         # the config file these settings came from
    models: list[ModelSpec]
    arms: dict[str, tuple[str, str]]   # arm -> (variant_x, variant_y)
    reps: int
    temperature: float | None          # None = not sent, model default
    shuffle_seed: int | None           # None = a new random call order every run
    job_description: str
    system_prompt: str
    user_prompt_template: str
    cv_dir: Path
    results_dir: Path
    workers: int                       # calls made at the same time
    calls_per_minute: float            # rate limit shared by all workers; 0 = no limit
    max_retries: int
    request_timeout: float
    # CV checks (validate-cvs)
    expected_base_cvs: int | None      # None = don't check the number of base CVs
    section_headings: list[str]
    allowed_sections: dict[str, set]   # arm -> heading keys where its two variants may differ
    max_length_difference_pct: float
    leak_words: list[str]

    def output_dir(self, dry_run: bool) -> Path:
        """Folder a run writes to. Dry runs get their own folder, so fake answers can
        never end up in the real, append-only results/results.jsonl."""
        return self.results_dir / "dry_run" if dry_run else self.results_dir

    def placeholder_problems(self) -> list[str]:
        """Settings still at their placeholder values. Real runs refuse to start while any remain."""
        problems = [f"model '{m.id}' is still a placeholder" for m in self.models if m.is_placeholder()]
        for name in sorted(PROMPT_KEYS):
            if "PLACEHOLDER" in getattr(self, name):
                problems.append(f"prompts.{name} still contains the word PLACEHOLDER")
        return problems


def load_config(path=DEFAULT_CONFIG_PATH) -> Config:
    """Read config.yaml, check every setting, and return a Config."""
    path = Path(path).resolve()
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"{path.name} is not valid YAML:\n{e}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{path.name} should contain settings such as 'models:' and 'arms:'")
    _check_keys(raw, TOP_LEVEL_KEYS, path.name)

    prompts = _section(raw, "prompts", PROMPT_KEYS, required=True)
    paths = _section(raw, "paths", PATH_KEYS)
    runner = _section(raw, "runner", RUNNER_KEYS)
    checks = _section(raw, "cv_checks", CV_CHECK_KEYS, required=True)
    arms = _read_arms(raw.get("arms"))
    headings = _read_headings(checks.get("section_headings"))

    for key in sorted(PROMPT_KEYS):
        if not isinstance(prompts.get(key), str) or not prompts[key].strip():
            raise ConfigError(f"prompts.{key} must be some text")
    _check_template(prompts["user_prompt_template"])

    return Config(
        path=path,
        models=_read_models(raw.get("models")),
        arms=arms,
        reps=_whole_number(raw.get("reps"), "reps", minimum=1),
        temperature=_read_temperature(raw.get("temperature")),
        shuffle_seed=_optional_whole_number(raw.get("shuffle_seed"), "shuffle_seed"),
        job_description=prompts["job_description"],
        system_prompt=prompts["system_prompt"],
        user_prompt_template=prompts["user_prompt_template"],
        # Relative folders are read from the config file's folder, not from wherever
        # the command happens to be run.
        cv_dir=path.parent / _folder(paths.get("cv_dir", "cvs"), "paths.cv_dir"),
        results_dir=path.parent / _folder(paths.get("results_dir", "results"), "paths.results_dir"),
        workers=_whole_number(runner.get("workers", 4), "runner.workers", minimum=1),
        calls_per_minute=_number(runner.get("calls_per_minute", 60), "runner.calls_per_minute", minimum=0),
        max_retries=_whole_number(runner.get("max_retries", 5), "runner.max_retries", minimum=1),
        request_timeout=_number(runner.get("request_timeout", 120), "runner.request_timeout", minimum=1),
        expected_base_cvs=_optional_whole_number(checks.get("expected_base_cvs"), "cv_checks.expected_base_cvs", minimum=1),
        section_headings=headings,
        allowed_sections=_read_allowed_sections(checks.get("allowed_sections"), arms, headings),
        max_length_difference_pct=_number(checks.get("max_length_difference_pct"),
                                          "cv_checks.max_length_difference_pct", minimum=0),
        leak_words=_read_leak_words(checks.get("leak_words")),
    )


def read_api_key(folder) -> str:
    """OPENROUTER_API_KEY from the environment, or else from a .env file in `folder`.

    A key already set in the environment wins over the .env file. The .env file is
    read without changing the environment. The key must only ever be passed to the
    API client: never print it or save it.
    """
    key = os.environ.get("OPENROUTER_API_KEY") or dotenv_values(Path(folder) / ".env").get("OPENROUTER_API_KEY")
    return (key or "").strip()


# ----------------------------- checks for each setting -----------------------------

def _check_keys(section, allowed, where):
    unknown = sorted(str(k) for k in section if k not in allowed)
    if unknown:
        raise ConfigError(
            f"unknown setting(s) in {where}: {', '.join(unknown)}. "
            f"Allowed here: {', '.join(sorted(allowed))}. Check the spelling.")


def _section(raw, name, allowed, required=False):
    section = raw.get(name)
    if section is None:
        if required:
            raise ConfigError(f"the '{name}:' section is missing")
        return {}
    if not isinstance(section, dict):
        raise ConfigError(f"'{name}:' should be a group of settings")
    _check_keys(section, allowed, f"'{name}:'")
    return section


def _read_models(models):
    if not isinstance(models, list) or not models:
        raise ConfigError("'models:' must be a list with at least one model")
    specs = []
    for i, m in enumerate(models, 1):
        if not isinstance(m, dict) or set(m) != {"id", "type"}:
            raise ConfigError(f"models entry {i} must have exactly two settings: id and type")
        if not isinstance(m["id"], str) or not m["id"].strip():
            raise ConfigError(f"models entry {i}: id must be the model's OpenRouter slug")
        if m["type"] not in MODEL_TYPES:
            raise ConfigError(f"models entry {i}: type must be one of: {', '.join(MODEL_TYPES)}")
        specs.append(ModelSpec(id=m["id"].strip(), type=m["type"]))
    ids = [s.id for s in specs]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise ConfigError(f"model listed more than once: {', '.join(repeated)}")
    return specs


def _read_arms(arms):
    if not isinstance(arms, dict) or not arms:
        raise ConfigError("'arms:' must list each arm with its two variants, e.g.  implicit: [high, low]")
    result = {}
    for arm, variants in arms.items():
        if not isinstance(arm, str) or not NAME_PATTERN.fullmatch(arm):
            raise ConfigError(f"arm name {arm!r} may only use letters, digits and '-'")
        if not isinstance(variants, list) or len(variants) != 2:
            raise ConfigError(f"arm '{arm}' must have exactly two variants, e.g. [high, low]")
        for v in variants:
            if not isinstance(v, str) or not NAME_PATTERN.fullmatch(v):
                raise ConfigError(
                    f"arm '{arm}': variant {v!r} may only use letters, digits and '-' "
                    "(put it in quotes if YAML read it as true/false or a number)")
        if variants[0] == variants[1]:
            raise ConfigError(f"arm '{arm}': the two variants must be different")
        result[arm] = (variants[0], variants[1])
    return result


def _read_temperature(value):
    if value is None:
        return None
    # OpenRouter's chat completion reference gives the range as "Sampling temperature (0-2)":
    # https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 2:
        raise ConfigError("temperature must be null or a number from 0 to 2")
    return float(value)


def _check_template(template):
    """The template is filled in with str.format, so check its {placeholders} now
    rather than letting the first call of a run crash."""
    try:
        fields = {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
    except ValueError as e:
        raise ConfigError(
            f"prompts.user_prompt_template has an unmatched curly brace ({e}). "
            "Write {{ or }} for a literal brace.") from None
    missing = sorted(TEMPLATE_FIELDS - fields)
    unknown = sorted(fields - TEMPLATE_FIELDS)
    if missing or unknown:
        problems = []
        if missing:
            problems.append("missing " + ", ".join("{" + f + "}" for f in missing))
        if unknown:
            problems.append("unknown " + ", ".join("{" + f + "}" for f in unknown))
        raise ConfigError(
            "prompts.user_prompt_template must use {job}, {cv1} and {cv2} and nothing else: "
            + "; ".join(problems) + ". Write {{ or }} for a literal brace.")


def _whole_number(value, name, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"{name} must be a whole number of at least {minimum}")
    return value


def _optional_whole_number(value, name, minimum=None):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or (minimum is not None and value < minimum):
        at_least = f" of at least {minimum}" if minimum is not None else ""
        raise ConfigError(f"{name} must be a whole number{at_least}, or null")
    return value


def _number(value, name, minimum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(f"{name} must be a number of at least {minimum}")
    return float(value)


def _folder(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a folder name")
    return value


def _read_headings(headings):
    if not isinstance(headings, list) or not headings or not all(isinstance(h, str) and h.strip() for h in headings):
        raise ConfigError("cv_checks.section_headings must be a list of heading texts, e.g. [Education, Interests]")
    keys = [heading_key(h) for h in headings]
    if HEADER_SECTION in keys:
        raise ConfigError(f"cv_checks.section_headings: '{HEADER_SECTION}' is the name for the lines before "
                          "the first heading, so it can't be a heading itself")
    repeated = sorted({k for k in keys if keys.count(k) > 1})
    if repeated:
        raise ConfigError(f"cv_checks.section_headings lists the same heading twice: {', '.join(repeated)}")
    return [h.strip() for h in headings]


def _read_allowed_sections(allowed, arms, headings):
    if not isinstance(allowed, dict):
        raise ConfigError("cv_checks.allowed_sections must give, for each arm, the sections where its variants may differ")
    missing = [a for a in arms if a not in allowed]
    unknown = [str(a) for a in allowed if a not in arms]
    if missing or unknown:
        raise ConfigError(f"cv_checks.allowed_sections must list exactly the arms ({', '.join(arms)}): "
                          + "; ".join(filter(None, [missing and f"missing {', '.join(missing)}",
                                                    unknown and f"unknown {', '.join(unknown)}"])))
    known = {heading_key(h) for h in headings} | {HEADER_SECTION}
    result = {}
    for arm in arms:
        names = allowed[arm]
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
            raise ConfigError(f"cv_checks.allowed_sections.{arm} must be a list of section names, e.g. [Education]")
        for name in names:
            if heading_key(name) not in known:
                raise ConfigError(f"cv_checks.allowed_sections.{arm}: '{name}' is not one of "
                                  f"cv_checks.section_headings (or '{HEADER_SECTION}')")
        result[arm] = {heading_key(n) for n in names}
    return result


def _read_leak_words(words):
    if words is None:
        return []
    if not isinstance(words, list) or not all(isinstance(w, str) and w.strip() for w in words):
        raise ConfigError("cv_checks.leak_words must be a list of words, e.g. [high, low, variant]")
    return [w.strip() for w in words]

"""Checking the CV files before any money is spent:  python -m pipeline validate-cvs

The whole study depends on each pair being identical except for the one marker its
arm is about. These checks look for anything that would break that:
  - missing or misnamed files
  - pairs that differ outside the sections config.yaml allows for their arm
  - pairs whose two variants differ noticeably in length
  - words that could give the condition away (e.g. "high", "low", an arm name)
The full report, with every line that differs in every pair, is saved to
results/cv_validation.txt.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import heading_key
from pipeline.cvs import CVFileError, Pair, cv_path, parse_cv_name, read_cv

ERROR = "ERROR"      # must be fixed before a real run
WARNING = "WARNING"  # worth a look, but doesn't block a run


@dataclass
class Finding:
    level: str    # ERROR or WARNING
    where: str    # the file, pair or folder it is about
    message: str


@dataclass
class ValidationResult:
    findings: list = field(default_factory=list)
    pair_reports: list = field(default_factory=list)  # one block of text per pair
    base_cv_ids: list = field(default_factory=list)
    n_pairs: int = 0

    @property
    def errors(self):
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == WARNING]

    def add(self, level, where, message):
        self.findings.append(Finding(level, where, message))


def validate_cvs(cfg) -> ValidationResult:
    """Run every check on the CV folder named in config.yaml."""
    result = ValidationResult()
    cv_dir = Path(cfg.cv_dir)
    if not cv_dir.is_dir():
        result.add(ERROR, str(cv_dir), "CV folder not found")
        return result
    headings = {heading_key(h) for h in cfg.section_headings}
    words = leak_words(cfg)

    # 1. Each file on its own: name, readable text, leak words, headings.
    texts = {}  # (cv_id, arm, variant) -> text
    for path in sorted(cv_dir.iterdir()):
        if path.is_dir() or path.name.startswith("."):  # skip folders and hidden files like .DS_Store
            continue
        if path.suffix != ".txt":
            result.add(WARNING, path.name, "ignored: CV files must end in .txt")
            continue
        try:
            cv_id, arm, variant = parse_cv_name(path.stem, cfg.arms)
        except ValueError as e:
            result.add(ERROR, path.name, f"misnamed: {e}")
            continue
        try:
            text = read_cv(path)
        except CVFileError as e:
            result.add(ERROR, path.name, str(e))
            continue
        if not text.strip():
            result.add(ERROR, path.name, "the file is empty")
            continue
        texts[(cv_id, arm, variant)] = text
        for word, line_numbers in find_leak_words(text, words).items():
            result.add(WARNING, path.name, f"contains '{word}' (line {', '.join(map(str, line_numbers))}), "
                                           "which could give the condition away")
        if not any(heading_key(line) in headings for line in text.splitlines()):
            result.add(WARNING, path.name, "none of cv_checks.section_headings appear in this CV, "
                                           "so every line counts as 'header'")

    # 2. Every base CV needs every variant of every arm.
    result.base_cv_ids = sorted({cv_id for cv_id, _, _ in texts})
    for cv_id in result.base_cv_ids:
        for arm, variants in cfg.arms.items():
            for variant in variants:
                if (cv_id, arm, variant) not in texts:
                    result.add(ERROR, cv_id, f"missing {cv_path('.', cv_id, arm, variant).name}")
    if not result.base_cv_ids:
        result.add(ERROR, cv_dir.name, "no correctly named CV files found")
    elif cfg.expected_base_cvs is not None and len(result.base_cv_ids) != cfg.expected_base_cvs:
        result.add(ERROR, cv_dir.name, f"found {len(result.base_cv_ids)} base CVs, but the study design has "
                                       f"{cfg.expected_base_cvs} (cv_checks.expected_base_cvs)")

    # 3. Compare the two variants of every complete pair.
    for cv_id in result.base_cv_ids:
        for arm, (vx, vy) in cfg.arms.items():
            if (cv_id, arm, vx) in texts and (cv_id, arm, vy) in texts:
                pair = Pair(f"{cv_id}_{arm}", cv_id, arm, vx, texts[(cv_id, arm, vx)], vy, texts[(cv_id, arm, vy)])
                result.n_pairs += 1
                compare_pair(pair, cfg, headings, result)
    return result


def compare_pair(pair, cfg, headings, result):
    """Diff the two variants line by line (difflib) and check every difference lies in
    a section config.yaml allows for this arm. Adds findings and a report block."""
    allowed = cfg.allowed_sections[pair.arm]
    x_lines, y_lines = pair.x_text.splitlines(), pair.y_text.splitlines()
    x_sections = section_of_each_line(x_lines, headings)
    y_sections = section_of_each_line(y_lines, headings)
    errors, warnings, details = [], [], []

    if pair.x_text == pair.y_text:
        errors.append("the two variants are identical, so the marker is missing")

    x_headings = [heading_key(line) for line in x_lines if heading_key(line) in headings]
    y_headings = [heading_key(line) for line in y_lines if heading_key(line) in headings]
    if x_headings != y_headings:
        errors.append(f"the variants have different section headings: {x_headings} vs {y_headings}")

    # autojunk=False: never treat common lines (like blank ones) as "junk" to be skipped.
    matcher = difflib.SequenceMatcher(None, x_lines, y_lines, autojunk=False)
    changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    outside = []
    for _, i1, i2, j1, j2 in changes:
        sections = {x_sections[i] for i in range(i1, i2)} | {y_sections[j] for j in range(j1, j2)}
        not_allowed = sorted(sections - allowed)
        where = line_numbers_text(i1, i2, j1, j2, pair)
        flag = "   <-- outside the allowed sections" if not_allowed else ""
        details.append(f"    {where} [{', '.join(sorted(sections))}]{flag}")
        details += [f"      {pair.x_variant}: {line}" for line in x_lines[i1:i2]]
        details += [f"      {pair.y_variant}: {line}" for line in y_lines[j1:j2]]
        if i2 - i1 == 1 and j2 - j1 == 1:
            old, new = changed_part(x_lines[i1], y_lines[j1])
            details.append(f"      changed: {old!r} -> {new!r}")
        if not_allowed:
            outside.append(f"{where} ({', '.join(not_allowed)})")
    if outside:
        errors.append(f"differs outside the allowed sections [{', '.join(sorted(allowed))}]: {'; '.join(outside)}")
    if not changes and pair.x_text != pair.y_text:
        # Splitting into lines hides a difference in line endings or in the final line break.
        errors.append("the variants differ only in invisible line endings or the final line break")

    length_pct = 100 * abs(len(pair.x_text) - len(pair.y_text)) / max(len(pair.x_text), len(pair.y_text))
    if length_pct > cfg.max_length_difference_pct:
        warnings.append(f"the variants differ in length by {length_pct:.1f}% ({len(pair.x_text)} vs "
                        f"{len(pair.y_text)} characters); the limit is {cfg.max_length_difference_pct:g}%")

    for message in errors:
        result.add(ERROR, pair.pair_id, message)
    for message in warnings:
        result.add(WARNING, pair.pair_id, message)
    status = "ERROR" if errors else ("WARNING" if warnings else "OK")
    n_lines = sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in changes)
    result.pair_reports.append("\n".join(
        [f"{pair.pair_id} ({pair.x_variant} vs {pair.y_variant}): {status}",
         f"    {n_lines} line(s) differ; length difference {length_pct:.1f}%"] + details))


def section_of_each_line(lines, headings) -> list[str]:
    """The section each line belongs to. A heading line starts its own section;
    lines before the first heading belong to the "header" section."""
    current = "header"
    sections = []
    for line in lines:
        if heading_key(line) in headings:
            current = heading_key(line)
        sections.append(current)
    return sections


def line_numbers_text(i1, i2, j1, j2, pair) -> str:
    """Human-readable line numbers (counting from 1) for one changed block."""
    def numbers(start, end):
        if end - start == 0:
            return "none"
        return str(start + 1) if end - start == 1 else f"{start + 1}-{end}"
    x_part, y_part = numbers(i1, i2), numbers(j1, j2)
    word = "lines" if "-" in x_part + y_part else "line"
    if x_part == y_part:
        return f"{word} {x_part}"
    return f"{word} {x_part} ({pair.x_variant}) / {y_part} ({pair.y_variant})"


def changed_part(a, b):
    """The part of two similar lines that differs, found by trimming what they share
    at the start and at the end. Shown with repr() so invisible characters stand out."""
    start = 0
    while start < min(len(a), len(b)) and a[start] == b[start]:
        start += 1
    end = 0
    while end < min(len(a), len(b)) - start and a[len(a) - 1 - end] == b[len(b) - 1 - end]:
        end += 1
    return a[start:len(a) - end], b[start:len(b) - end]


def leak_words(cfg) -> list[str]:
    """Words to look for: the configured list plus every arm name."""
    words = []
    for word in list(cfg.leak_words) + list(cfg.arms):
        if word.lower() not in words:
            words.append(word.lower())
    return words


def find_leak_words(text, words) -> dict:
    """Which of `words` appear in `text` as whole words, ignoring capitals: {word: [line numbers]}."""
    if not words:
        return {}
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)
    found = {}
    for number, line in enumerate(text.splitlines(), 1):
        for match in pattern.finditer(line):
            lines = found.setdefault(match.group(1).lower(), [])
            if number not in lines:
                lines.append(number)
    return found


def format_report(cfg, result) -> str:
    """The full report: every pair's differences, then the errors, warnings and a summary."""
    lines = [
        "CV validation report",
        f"Created: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        f"CV folder: {cfg.cv_dir}",
        f"Settings: cv_checks in {cfg.path}",
        "",
        "PAIR BY PAIR: every line that differs between the two variants",
        "",
    ]
    lines += result.pair_reports or ["  (no complete pairs)"]
    lines += ["", f"ERRORS ({len(result.errors)})"]
    lines += [f"  - {f.where}: {f.message}" for f in result.errors] or ["  none"]
    lines += ["", f"WARNINGS ({len(result.warnings)})"]
    lines += [f"  - {f.where}: {f.message}" for f in result.warnings] or ["  none"]
    lines += ["", f"SUMMARY: {len(result.base_cv_ids)} base CVs, {result.n_pairs} complete pairs, "
                  f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)."]
    return "\n".join(lines) + "\n"


def save_report(cfg, text) -> Path:
    path = Path(cfg.results_dir) / "cv_validation.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

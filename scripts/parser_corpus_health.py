#!/usr/bin/env python3
"""Parse every debate file in a corpus and report, in aggregate, how the parser coped.

The labeled evaluation (`tests/evals/parser/`) measures *accuracy* on thirty files. This measures
*health* on all of them — the ~2,400 `.docx` files across the hsld26 caselist snapshots and the camp
files: does every file parse, why do the ones that fail fail, and does the output look like debate
files (cards found, completeness, template family). It is unlabeled, so it says nothing about
whether a card is right, only whether the parser produced one.

**Operator-run only.** It reads the real corpus, which never reaches CI or a session, and it is
well over the two-minute hand-off threshold (working agreements §2). It writes **counts only**:
no file name, path, school, team code, document text or exception message appears in the
report — an exception is counted by its type name, a refusal by its `ParseFailureReason`.

Snapshots are cumulative, so the same bytes appear in several of them. A file is parsed once per
SHA-256 and the report gives both the number of files seen and the number of distinct files.

    uv run python scripts/parser_corpus_health.py \\
      --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0901" \\
      --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0908" \\
      --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0915" \\
      --input "camp=$HOME/Documents/debate/2026-2027/Policy Debate/Camp Files" \\
      --output docs/data/parser-corpus-health.md

It exits non-zero when the parse success rate is below 0.98 (Goal criterion ac5), after writing
the report either way.
"""

from __future__ import annotations

import argparse
import hashlib
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from survey_docx_styles import read_file_usage  # noqa: E402

from debate_core.domain.caselist.entities import SourceDocument  # noqa: E402
from debate_core.domain.caselist.values import SourceFormat, SourceOrigin  # noqa: E402
from debate_core.domain.debate_files import CardCompleteness, ParsedDocument  # noqa: E402
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser  # noqa: E402

__all__ = ["CorpusHealth", "SUCCESS_RATE_TARGET", "main", "measure", "render_report"]

#: Goal criterion ac5.
SUCCESS_RATE_TARGET = 0.98

_SNAPSHOT = date(2026, 9, 15)
_EXTENSIONS = {".docx": "docx", ".doc": "doc", ".docm": "docm", ".pdf": "pdf"}


@dataclass
class CategoryHealth:
    files_seen: int = 0
    formats: Counter[str] = field(default_factory=Counter)
    """Distinct files by extension."""
    docx: int = 0
    parsed: int = 0
    failures: Counter[str] = field(default_factory=Counter)
    families: Counter[str] = field(default_factory=Counter)
    parsed_by_family: Counter[str] = field(default_factory=Counter)
    completeness: Counter[str] = field(default_factory=Counter)
    cards_per_file: list[int] = field(default_factory=list)
    files_without_cards: int = 0
    parse_seconds: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float | None:
        return self.parsed / self.docx if self.docx else None


@dataclass
class CorpusHealth:
    categories: dict[str, CategoryHealth] = field(default_factory=dict)
    total: CategoryHealth = field(default_factory=CategoryHealth)

    def category(self, name: str) -> CategoryHealth:
        return self.categories.setdefault(name, CategoryHealth())


def _iter_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith(("~$", ".")):
            yield path


def _source(category: str, sha256: str, size: int) -> tuple[SourceDocument, str | None]:
    caselist = category == "caselist"
    return (
        SourceDocument(
            sha256=sha256,
            byte_size=size,
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.CASELIST_ARCHIVE if caselist else SourceOrigin.OPENEV,
            caselist="hsld26" if caselist else None,
            first_seen_snapshot=_SNAPSHOT,
            last_seen_snapshot=_SNAPSHOT,
        ),
        None if caselist else category,
    )


def measure(inputs: Sequence[tuple[str, Path]], parser: DebateDocxParser | None = None) -> CorpusHealth:
    """Parse every distinct `.docx` under the inputs and count what happened. Never raises per file."""
    parser = parser if parser is not None else DebateDocxParser()
    health = CorpusHealth()
    seen: set[str] = set()
    for category, root in inputs:
        if not root.is_dir():
            raise SystemExit(f"input folder not found for category {category}")
        for path in _iter_files(root):
            kind = _EXTENSIONS.get(path.suffix.lower(), "other")
            content = path.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            groups = (health.category(category), health.total)
            for group in groups:
                group.files_seen += 1
            if sha256 in seen:
                continue
            seen.add(sha256)
            for group in groups:
                group.formats[kind] += 1
            if kind != "docx":
                continue

            family = read_file_usage(path, category).template_family
            source, camp = _source(category, sha256, len(content))
            started = time.perf_counter()
            try:
                result = parser.parse(content, source, source_path=f"health/{sha256}.docx", camp=camp)
                outcome = result if isinstance(result, ParsedDocument) else f"refused: {result.reason.value}"
            except Exception as error:  # noqa: BLE001 - a crash is a count, never a stopped run
                outcome = f"parser exception: {type(error).__name__}"
            elapsed = time.perf_counter() - started

            for group in groups:
                group.docx += 1
                group.families[family] += 1
                group.parse_seconds.append(elapsed)
                if isinstance(outcome, str):
                    group.failures[outcome] += 1
                    continue
                group.parsed += 1
                group.parsed_by_family[family] += 1
                group.cards_per_file.append(outcome.card_count)
                if outcome.card_count == 0:
                    group.files_without_cards += 1
                group.completeness.update(card.completeness.value for card in outcome.cards)
    return health


def _share(count: int, total: int) -> str:
    return f"{count} ({count / total:.1%})" if total else "0"


def _rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))] if ordered else 0.0


def render_report(health: CorpusHealth, *, run_on: date, corpus_description: str) -> str:
    total = health.total
    names = sorted(health.categories)
    groups = [(name, health.categories[name]) for name in names] + [("**all**", total)]
    verdict = (
        "MET" if total.success_rate is not None and total.success_rate >= SUCCESS_RATE_TARGET else "NOT MET"
    )
    lines = [
        "# Parser corpus health",
        "",
        "Whether the `v1-e31-t03` parser reads every debate file the platform will import, measured over",
        "the real corpus in place by `scripts/parser_corpus_health.py`. Unlabeled: this says whether a",
        "file parsed and what came out, not whether the cards are right. Accuracy is the labeled",
        "evaluation's job (`tests/evals/parser/`).",
        "",
        "Counts only. No file name, path, school, team code, document text or exception message is",
        "collected into this report; a crash is counted by its exception type, a refusal by its reason.",
        "",
        "| | |",
        "|---|---|",
        f"| Run on | {run_on.isoformat()} |",
        f"| Parser version | `{DOCX_PARSER_VERSION}` |",
        f"| Corpus | {corpus_description} |",
        f"| Files seen | {total.files_seen} ({sum(total.formats.values())} distinct by SHA-256) |",
        f"| Distinct `.docx` files | {total.docx} |",
        f"| **Parse success rate** | **{_rate(total.success_rate)}** of distinct `.docx` files "
        f"(target {SUCCESS_RATE_TARGET}: {verdict}) |",
        "",
        "## Parse success rate by category",
        "",
        "| Category | Files seen | Distinct | `.docx` | Parsed | Parse success rate |",
        "|---|---|---|---|---|---|",
    ]
    for name, group in groups:
        lines.append(
            f"| {name} | {group.files_seen} | {sum(group.formats.values())} | {group.docx} | "
            f"{group.parsed} | {_rate(group.success_rate)} |"
        )

    lines += ["", "## Failure reasons", "", "Every `.docx` that did not parse, counted by reason.", ""]
    reasons = sorted(total.failures)
    if not reasons:
        lines.append("None: every distinct `.docx` parsed.")
    else:
        lines += ["| Reason | " + " | ".join(names) + " | all |", "|---|" + "---|" * (len(names) + 1)]
        for reason in reasons:
            cells = [str(health.categories[name].failures[reason]) for name in names]
            lines.append(f"| {reason} | " + " | ".join(cells) + f" | {total.failures[reason]} |")

    other_formats = sorted(kind for kind in total.formats if kind != "docx")
    if other_formats:
        lines += ["", "Files not parsed because V1 reads `.docx` only (distinct files):", ""]
        lines += [f"- `{kind}`: {total.formats[kind]}" for kind in other_formats]

    families = sorted(total.families)
    lines += [
        "",
        "## Template families",
        "",
        "From `scripts/survey_docx_styles.py`'s classifier. Parsed / distinct `.docx` per family.",
        "",
        "| Family | " + " | ".join(names) + " | all | parse success rate |",
        "|---|" + "---|" * (len(names) + 2),
    ]
    for family in families:
        cells = [str(health.categories[name].families[family]) for name in names]
        rate = total.parsed_by_family[family] / total.families[family]
        lines.append(f"| {family} | " + " | ".join(cells) + f" | {total.families[family]} | {rate:.4f} |")

    lines += [
        "",
        "## What came out",
        "",
        "| Category | Cards | FULL | ABBREVIATED | CITE_ONLY | Median cards per file | 90th percentile "
        "| Parsed files with no cards |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, group in groups:
        cards = sum(group.completeness.values())
        median = statistics.median(group.cards_per_file) if group.cards_per_file else 0
        lines.append(
            f"| {name} | {cards} | "
            + " | ".join(_share(group.completeness[c.value], cards) for c in CardCompleteness)
            + f" | {median:g} | {_quantile(group.cards_per_file, 0.9):g} | "
            f"{_share(group.files_without_cards, group.parsed)} |"
        )

    lines += [
        "",
        "## Parse time per file",
        "",
        "| Category | Median | 95th percentile | Slowest | Total |",
        "|---|---|---|---|---|",
    ]
    for name, group in groups:
        times = group.parse_seconds
        lines.append(
            f"| {name} | {_quantile(times, 0.5):.3f} s | {_quantile(times, 0.95):.3f} s | "
            f"{max(times, default=0.0):.3f} s | {sum(times):.1f} s |"
        )
    lines += [
        "",
        "Every failure reason above is filed against `v1-e31-t03`'s parser, not fixed inside the",
        "evaluation.",
    ]
    return "\n".join(lines) + "\n"


def _parse_input(value: str) -> tuple[str, Path]:
    category, separator, path = value.partition("=")
    if not separator or category not in {"caselist", "camp", "team"}:
        raise argparse.ArgumentTypeError("--input takes CATEGORY=PATH, CATEGORY one of caselist, camp, team")
    return category, Path(path).expanduser()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", action="append", type=_parse_input, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--corpus-description",
        default="the hsld26 weekly caselist snapshots and the 2026-27 Policy camp files",
    )
    args = parser.parse_args(argv)

    started = time.monotonic()
    health = measure(args.input)
    report = render_report(health, run_on=date.today(), corpus_description=args.corpus_description)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    rate = health.total.success_rate
    print(
        f"parsed {health.total.parsed} of {health.total.docx} distinct .docx files "
        f"(parse success rate {_rate(rate)}) in {time.monotonic() - started:.0f} s -> {args.output}"
    )
    for reason, count in sorted(health.total.failures.items()):
        print(f"  {reason}: {count}")
    return 0 if rate is not None and rate >= SUCCESS_RATE_TARGET else 1


if __name__ == "__main__":
    sys.exit(main())

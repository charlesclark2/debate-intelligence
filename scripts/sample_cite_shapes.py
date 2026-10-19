#!/usr/bin/env python3
"""Ask a person about a sample of what `v1-e31-t19`'s cite rules take and leave. Counts only.

The rules were proposed from counts over the corpus, and counts say how many paragraphs a rule
takes, not how many it takes wrongly. This draws, for each rule, paragraphs it takes and
paragraphs of the same population it leaves, shows each one in place, and asks one question with
one key. The PM approved the plan on 2026-10-18, 70 items:

* a cite behind a first name or a title: 10 taken (8 read as nothing before, 2 read as body), 10
  left (7 read as nothing, 3 as body);
* a paragraph style that maps to no unit: 6 taken as cites, 8 taken as body, 6 left as nothing;
* a highlighted cite: 10 taken, 10 left;
* the cite-style hold: 7 re-read as body, 3 still held as cites.

It parses every source in the store with the parser this branch carries. The sample was taken on
2026-10-18 with the three rules behind a flag that only this script switched on, so it judged the
code that would ship; the rules were switched on for good once the tallies supported them, and the
flag removed. That takes a few minutes before the first question; then the items come in an
order that does not say which rule or which side each is from.

**Read-only, and nothing but tallies leaves it.** It reads the data directory's parsed store
index and blobs in place and writes nothing there. Every text it shows stays in memory. The one
file it writes is the tallies file, which must be outside the repository: the seed, the counts
drawn and asked, the seconds spent answering, and the answers counted by rule and side. No
paragraph, tag, cite, file name, path or digest.

    uv run python scripts/sample_cite_shapes.py --seed 20261018 \\
      --save-tallies ~/cite-shape-sample-tallies.txt

Keys: `y` yes, `n` no, `u` unsure, with no Enter; `q` stops and keeps the tallies so far.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from compare_card_clusters import CLEAR_TERMINAL, read_key  # noqa: E402

from debate_core.application.ports.parsed_store import parse_version_directory  # noqa: E402
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin  # noqa: E402
from debate_core.domain.debate_files import FileSection, ParsedDocument  # noqa: E402
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleProfile  # noqa: E402
from debate_core.evidence.style_classifier import (  # noqa: E402
    first_name_and_year,
    is_a_highlighted_cite,
    the_cite_style_marks_a_name_and_year_at_the_head,
)
from debate_core.integrations.docx_parser import DebateDocxParser  # noqa: E402
from debate_core.integrations.docx_parser.runs import ReadParagraph  # noqa: E402
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY  # noqa: E402

__all__ = ["STRATA", "Stratum", "main", "strata_of"]

CITE_QUESTION = "Is the marked paragraph this card's cite, or a line of it?"
TEXT_QUESTION = "Is the marked paragraph part of the card's text, the evidence?"
EITHER_QUESTION = "Is the marked paragraph a cite, or part of a card's text?"

ANSWERS = {"y": "yes", "n": "no", "u": "unsure"}
STOP_KEY = "q"
PROMPT = "  y yes   n no   u unsure   q stop and keep the tallies > "

BEHIND_A_NAME = "assembly-cite-behind-a-name-before-the-body"
HIGHLIGHTED_CITE = "assembly-highlighted-cite-before-the-body"
GUESS_REREAD = "assembly-cite-guess-"

#: How far a long paragraph is shown: its opening and its end, with the middle counted.
SHOWN_OPENING, SHOWN_END, SHOWN_CONTEXT = 900, 400, 240

_HEADINGS = (StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK, StructuralUnit.TAG)


@dataclass(frozen=True, slots=True)
class Stratum:
    """One cell of the plan: a rule, which side of it, and how many to draw."""

    rule: str
    side: str
    question: str
    planned: int

    @property
    def label(self) -> str:
        return f"{self.rule} | {self.side}"


STRATA: tuple[Stratum, ...] = (
    Stratum("a cite behind a first name or a title", "taken, read as nothing before", CITE_QUESTION, 8),
    Stratum("a cite behind a first name or a title", "taken, read as body before", CITE_QUESTION, 2),
    Stratum("a cite behind a first name or a title", "left, read as nothing", CITE_QUESTION, 7),
    Stratum("a cite behind a first name or a title", "left, read as body", CITE_QUESTION, 3),
    Stratum("a paragraph style that maps to no unit", "taken as a cite", CITE_QUESTION, 6),
    Stratum("a paragraph style that maps to no unit", "taken as body", TEXT_QUESTION, 8),
    Stratum("a paragraph style that maps to no unit", "left as nothing", EITHER_QUESTION, 6),
    Stratum("a highlighted cite", "taken", CITE_QUESTION, 10),
    Stratum("a highlighted cite", "left", CITE_QUESTION, 10),
    Stratum("the cite-style hold", "re-read as body", CITE_QUESTION, 7),
    Stratum("the cite-style hold", "still held as a cite", CITE_QUESTION, 3),
)


# ------------------------------------------------------------------------------------------------
# Which paragraphs belong to which stratum
# ------------------------------------------------------------------------------------------------


def _says_nothing(section: FileSection) -> bool:
    """A blank line, a table cell or a text box: stepped over, as the assembly steps over them."""
    return (
        not section.text.strip()
        or section.in_table
        or section.match.rule_id.startswith(("assembly-text-box", "assembly-table-cell"))
    )


def _in_an_unmapped_style(read: ReadParagraph, profile: StyleProfile) -> bool:
    description = read.description
    style = profile.resolve_paragraph_style(
        description.style_id, description.style_name, description.style_based_on
    )
    return style is not None and style.unit is StructuralUnit.OTHER


def _carries_a_cite_style(read: ReadParagraph, profile: StyleProfile) -> bool:
    for run in read.description.visible_runs:
        style = profile.resolve_character_style(
            run.character_style_id, run.character_style_name, run.character_style_based_on
        )
        if style is not None and style.emphasis is RunEmphasis.CITE:
            return True
    return False


def _card_has_no_cite(sections: Sequence[FileSection], tag_at: int) -> bool:
    """Whether nothing between the tag at `tag_at` and the next heading or analytic is a cite."""
    for section in sections[tag_at + 1 :]:
        if section.unit in _HEADINGS or section.unit is StructuralUnit.ANALYTIC:
            return True
        if section.unit is StructuralUnit.CITE:
            return False
    return True


def strata_of(
    reads: Sequence[ReadParagraph], sections: Sequence[FileSection], profile: StyleProfile
) -> list[tuple[int, int]]:
    """Each paragraph of one parsed file that belongs to a stratum, as (stratum, position).

    `reads` and `sections` are the file's paragraphs as read and as the parser decided them,
    aligned. A paragraph is in one stratum at most: what a
    rule took is looked for before what it left.
    """
    found: list[tuple[int, int]] = []
    previous: int | None = None
    for position, (read, section) in enumerate(zip(reads, sections, strict=True)):
        if _says_nothing(section):
            continue
        stratum = _stratum_of(read, section, sections, previous, profile)
        if stratum is not None:
            found.append((stratum, position))
        previous = position
    return found


def _stratum_of(
    read: ReadParagraph,
    section: FileSection,
    sections: Sequence[FileSection],
    previous: int | None,
    profile: StyleProfile,
) -> int | None:
    rule, unit = section.match.rule_id, section.unit
    text = read.text.strip()
    if rule.startswith(BEHIND_A_NAME):
        overruled = rule.split(":", 1)[1]
        return 0 if overruled.startswith("heuristic-unclassified-paragraph") else 1
    if rule.startswith(HIGHLIGHTED_CITE):
        return 7
    if _in_an_unmapped_style(read, profile):
        if unit is StructuralUnit.CITE:
            return 4
        if unit is StructuralUnit.EVIDENCE:
            return 5
        return 6 if unit is StructuralUnit.OTHER else None
    if (
        unit is StructuralUnit.EVIDENCE
        and rule.startswith(GUESS_REREAD)
        and _carries_a_cite_style(read, profile)
        and not the_cite_style_marks_a_name_and_year_at_the_head(read.description, profile)
    ):
        return 9
    if (
        unit is StructuralUnit.CITE
        and rule.startswith("heuristic-")
        and len(text) > 2_000
        and the_cite_style_marks_a_name_and_year_at_the_head(read.description, profile)
    ):
        return 10
    if (
        unit in (StructuralUnit.OTHER, StructuralUnit.EVIDENCE)
        and previous is not None
        and sections[previous].unit is StructuralUnit.TAG
        and _card_has_no_cite(sections, previous)
    ):
        name = first_name_and_year(text, profile)
        if name is not None and 0 < name.start() <= 40:
            return 2 if unit is StructuralUnit.OTHER else 3
    if unit is not StructuralUnit.CITE and is_a_highlighted_cite(read.description, profile):
        return 8
    return None


# ------------------------------------------------------------------------------------------------
# Reading the store
# ------------------------------------------------------------------------------------------------


class _ReadingParser(DebateDocxParser):
    """The parser, keeping each file's paragraphs as it read them."""

    def __init__(self) -> None:
        super().__init__()
        self.reads: list[ReadParagraph] = []

    def _read_sections(self, package: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        sections = super()._read_sections(package)  # pyright: ignore[reportPrivateUsage]
        self.reads = [section.read for section in sections]
        return sections


@dataclass(frozen=True, slots=True)
class _Source:
    caselist: str
    sha256: str
    blob: Path


def _version_directory(parsed: Path, caselist: str) -> Path:
    """The newest version directory of `caselist` that holds an index."""
    directory = parsed / caselist
    versions = (
        [path for path in directory.iterdir() if (path / "index.jsonl").is_file()]
        if directory.is_dir()
        else []
    )
    if not versions:
        raise SystemExit(f"{caselist}: no version directory with an index under the parsed store")
    return max(versions, key=lambda path: parse_version_directory(path.name))


def sources_in(data_dir: Path, caselists: Iterable[str]) -> list[_Source]:
    """Every source the store recorded as parsed, in a fixed order."""
    sources: list[_Source] = []
    for caselist in caselists:
        index = _version_directory(data_dir / "parsed", caselist) / "index.jsonl"
        for line in index.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("outcome") == "PARSED":
                digest = record["source_sha256"]
                blob = data_dir / BLOB_DIRECTORY / digest[:2] / digest[2:4] / digest
                sources.append(_Source(caselist, digest, blob))
    return sorted(sources, key=lambda source: (source.caselist, source.sha256))


_PARSER: _ReadingParser | None = None


def _parse(source: _Source) -> tuple[list[ReadParagraph], ParsedDocument] | None:
    global _PARSER  # noqa: PLW0603 - one parser per worker process
    if _PARSER is None:
        _PARSER = _ReadingParser()
    content = source.blob.read_bytes()
    snapshot = date(2026, 10, 18)
    record = SourceDocument(
        sha256=source.sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV if source.caselist == "openev" else SourceOrigin.CASELIST_ARCHIVE,
        caselist=None if source.caselist == "openev" else source.caselist,
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    document = _PARSER.parse(content, record, source_path="sample.docx")
    if not isinstance(document, ParsedDocument):
        return None
    return _PARSER.reads, document


def _strata_in(source: _Source) -> list[tuple[int, int]]:
    parsed = _parse(source)
    if parsed is None:
        return []
    reads, document = parsed
    return strata_of(reads, document.sections, _PARSER.profile)  # type: ignore[union-attr]


def scan(sources: Sequence[_Source], workers: int) -> dict[int, list[tuple[_Source, int]]]:
    """Every paragraph in every stratum, as (source, position), in a fixed order."""
    found: dict[int, list[tuple[_Source, int]]] = {number: [] for number in range(len(STRATA))}
    if workers <= 1:
        results = [_strata_in(source) for source in sources]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_strata_in, sources, chunksize=8))
    for source, in_file in zip(sources, results, strict=True):
        for stratum, position in in_file:
            found[stratum].append((source, position))
    return found


# ------------------------------------------------------------------------------------------------
# Showing an item
# ------------------------------------------------------------------------------------------------

_BOLD, _UNDERLINE, _REVERSE, _RESET = "\x1b[1m", "\x1b[4m", "\x1b[7m", "\x1b[0m"


def _shortened(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + " …"


def _marked(read: ReadParagraph) -> str:
    """The paragraph with its bold, underline and highlighting, a long one cut in the middle."""
    description = read.description
    segments: list[tuple[int, int, str]] = []
    for run, (starts, ends) in zip(description.runs, read.run_offsets, strict=True):
        if ends <= starts:
            continue
        bold = run.bold if run.bold is not None else bool(description.paragraph_bold)
        codes = (_BOLD if bold else "") + (_UNDERLINE if run.is_directly_underlined else "")
        segments.append((starts, ends, codes + (_REVERSE if run.highlight else "")))
    length = len(read.text)
    if length <= SHOWN_OPENING + SHOWN_END + 100:
        return _shown(read.text, segments, 0, length)
    return (
        _shown(read.text, segments, 0, SHOWN_OPENING)
        + f"\n   [… {length - SHOWN_OPENING - SHOWN_END:,} characters not shown …]\n"
        + _shown(read.text, segments, length - SHOWN_END, length)
    )


def _shown(text: str, segments: Sequence[tuple[int, int, str]], starts: int, ends: int) -> str:
    """Characters `starts` to `ends` of `text`, each run's stretch in its formatting codes."""
    shown: list[str] = []
    for segment_starts, segment_ends, codes in segments:
        part = text[max(segment_starts, starts) : min(segment_ends, ends)]
        if part:
            shown.append(codes + part + _RESET if codes else part)
    return "".join(shown)


def render_item(reads: Sequence[ReadParagraph], sections: Sequence[FileSection], position: int) -> str:
    """The marked paragraph between the tag over it and the paragraphs either side."""
    lines: list[str] = []
    for earlier in range(position - 1, -1, -1):
        unit = sections[earlier].unit
        if unit is StructuralUnit.TAG:
            lines.append(f"Tag above:  {_shortened(sections[earlier].text, SHOWN_CONTEXT)}")
            break
        if unit in _HEADINGS:
            lines.append("Tag above:  none")
            break
    above = next((k for k in range(position - 1, -1, -1) if not _says_nothing(sections[k])), None)
    if above is not None and sections[above].unit is not StructuralUnit.TAG:
        lines.append(f"Paragraph above:  {_shortened(sections[above].text, SHOWN_CONTEXT)}")
    lines.append("")
    lines.append(">>> " + _marked(reads[position]).replace("\n", "\n    "))
    lines.append("")
    below = next((k for k in range(position + 1, len(sections)) if not _says_nothing(sections[k])), None)
    if below is not None:
        lines.append(f"Paragraph below:  {_shortened(sections[below].text, SHOWN_CONTEXT)}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------
# The sample
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Item:
    stratum: int
    shown: str


@dataclass(frozen=True, slots=True)
class Tallies:
    """What was drawn, asked and answered, by stratum. Counts only."""

    seed: int
    sources: int
    population: dict[int, int]
    drawn: Counter[int]
    answered: Counter[tuple[int, str]]
    asked: int
    stopped: bool
    seconds_answering: float

    def lines(self) -> list[str]:
        answered = sum(self.answered.values())
        summary = f"  Asked {self.asked}; answered {answered} in {round(self.seconds_answering)} seconds"
        summary += f", stopped with {self.asked - answered} not answered." if self.stopped else "."
        lines = [
            f"Cite-shape sample (v1-e31-t19), seed {self.seed}: drew {sum(self.drawn.values())} items "
            f"from {self.sources:,} parsed sources.",
            summary,
        ]
        for number, stratum in enumerate(STRATA):
            answers = ", ".join(f"{word} {self.answered[(number, word)]}" for word in ANSWERS.values())
            lines.append(
                f"  {stratum.label}: in the corpus {self.population[number]:,}; drew {self.drawn[number]} "
                f"of {stratum.planned}; {answers}"
            )
        return lines


def draw(found: dict[int, list[tuple[_Source, int]]], seed: int) -> list[tuple[int, _Source, int]]:
    """Each stratum's planned number, at random by `seed`, then all of them in one shuffled order."""
    chooser = random.Random(seed)
    drawn: list[tuple[int, _Source, int]] = []
    for number, stratum in enumerate(STRATA):
        candidates = found[number]
        for source, position in chooser.sample(candidates, min(stratum.planned, len(candidates))):
            drawn.append((number, source, position))
    chooser.shuffle(drawn)
    return drawn


def prepare(drawn: Sequence[tuple[int, _Source, int]]) -> list[_Item]:
    """Each drawn item rendered, before the first question, so the clock times answering alone."""
    items: list[_Item] = []
    for stratum, source, position in drawn:
        parsed = _parse(source)
        if parsed is None:
            continue
        reads, document = parsed
        items.append(_Item(stratum, render_item(reads, document.sections, position)))
    return items


def ask_about(
    items: Sequence[_Item],
    *,
    ask: Callable[[str], str],
    show: Callable[[str], None],
    clock: Callable[[], float] = time.monotonic,
) -> tuple[Counter[tuple[int, str]], bool, float]:
    """Show each item and read one key for it. The answers by stratum, whether stopped, seconds."""
    answered: Counter[tuple[int, str]] = Counter()
    stopped = False
    started = clock()
    for number, item in enumerate(items, start=1):
        show(CLEAR_TERMINAL)
        show(f"Item {number} of {len(items)}.\n")
        show(item.shown + "\n")
        show(STRATA[item.stratum].question + "\n")
        key = ""
        while key not in ANSWERS and key != STOP_KEY:
            key = ask(PROMPT).strip().lower()[:1]
        if key == STOP_KEY:
            stopped = True
            break
        answered[(item.stratum, ANSWERS[key])] += 1
    seconds = clock() - started if items else 0.0
    show(CLEAR_TERMINAL)
    return answered, stopped, seconds


def _refuse_inside_the_repository(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(REPO_ROOT):
        raise SystemExit("--save-tallies must be outside the repository: the tallies are the operator's")
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".debate-research" / "dev",
        help="The data directory whose parsed store and blobs are read. Default: the dev data directory.",
    )
    parser.add_argument(
        "--caselist",
        action="append",
        help="Repeat for several. Default: hsld26, hspf26, hspolicy26 and openev.",
    )
    parser.add_argument("--seed", type=int, help="Draws the same items again. Default: a new one, recorded.")
    parser.add_argument("--save-tallies", type=Path, required=True, help="A file outside the repository.")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 2),
        help="Processes for the parse before the first question. Default: all processors but two.",
    )
    arguments = parser.parse_args(argv)
    saved = _refuse_inside_the_repository(arguments.save_tallies)
    seed = arguments.seed if arguments.seed is not None else random.SystemRandom().randrange(10**9)
    caselists = arguments.caselist or ["hsld26", "hspf26", "hspolicy26", "openev"]

    sources = sources_in(arguments.data_dir, caselists)
    print(f"Reading {len(sources):,} parsed sources; a few minutes …", flush=True)
    found = scan(sources, arguments.workers)
    items = prepare(draw(found, seed))
    answered, stopped, seconds = ask_about(
        items, ask=read_key, show=lambda text: print(text, end="", flush=True)
    )

    tallies = Tallies(
        seed=seed,
        sources=len(sources),
        population={number: len(found[number]) for number in range(len(STRATA))},
        drawn=Counter(item.stratum for item in items),
        answered=answered,
        asked=len(items),
        stopped=stopped,
        seconds_answering=seconds,
    )
    lines = tallies.lines()
    print("\n".join(lines))
    saved.parent.mkdir(parents=True, exist_ok=True)
    with saved.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    print(f"Tallies appended to {saved.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

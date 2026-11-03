#!/usr/bin/env python3
"""What `v1-e31-t23`'s ruling N1 changes in a parsed store, card by card. Counts only.

The PM's ruling of 2026-11-03: a line read as nothing between two body paragraphs of one card is body
when it is over 200 characters, or 41 to 200 and ends a sentence, unless a cite guard holds it. Every
source the store recorded as parsed is read twice from its blob by the parser this checkout carries,
once with N1 switched off and once with it on, and the two readings are compared:

* **the lines N1 makes body**, by its two strata (`assembly-sentence-between-body-paragraphs` and
  `assembly-long-line-between-body-paragraphs`);
* **the lines the cite guard holds back**, by stratum and by guard: a link, a web address, a DOI or
  "accessed", as ruled; and a line naming its source at its head, the session's addition, counted
  apart so the PM can weigh it;
* **the cards whose evidence text changed**, the count only. Matched by their range of paragraphs,
  which N1 never moves; any other difference between the two readings' cards is counted as **another
  card that changed**, and the bar for it is 0.

**Read-only, and nothing but counts leaves it.** It reads the parsed store's index and the blobs in
place and writes nothing. Its output on stdout is counts and rule names: no card text, tag, cite,
file name, path or digest. Progress goes to stderr.

    uv run python scripts/diff_lines_between_body_paragraphs.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.evidence.in_round_markers import lines_read_as_nothing
from debate_core.evidence.line_above_a_cite import rule_family
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.docx_parser.parser import (
    DOCX_PARSER_VERSION,
    LONG_LINE_BETWEEN_BODY_PARAGRAPHS,
    SENTENCE_BETWEEN_BODY_PARAGRAPHS,
    read_between_body_paragraphs,
)
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY

__all__ = ["CASELISTS", "compare", "diff_caselist", "main"]

CASELISTS = ("hsld26", "hspf26", "hspolicy26", "openev")

_N1_RULES = (SENTENCE_BETWEEN_BODY_PARAGRAPHS, LONG_LINE_BETWEEN_BODY_PARAGRAPHS)

#: What N1 may change in a card: the body it adds a line to, its spans, and the rules and confidence
#: the card records. Any other field that differs is another card that changed.
_WHAT_N1_CHANGES = frozenset(
    {"evidence_text", "formatting_spans", "font_size_spans", "rule_ids", "confidence", "match_source"}
)


class _Reading(DebateDocxParser):
    """The parser with N1 on or off."""

    def __init__(self, *, with_n1: bool) -> None:
        super().__init__()
        self.with_n1 = with_n1

    def _lines_between_body_paragraphs(self, assembled: Any) -> dict[int, str]:  # pyright: ignore[reportIncompatibleMethodOverride]
        if not self.with_n1:
            return {}
        return super()._lines_between_body_paragraphs(assembled)  # pyright: ignore[reportPrivateUsage]


@dataclass(slots=True)
class Compared:
    """One file's two readings, in counts."""

    cards: int = 0
    lines_made_body: Counter[str] = field(default_factory=Counter[str])
    held_back: Counter[tuple[str, str]] = field(default_factory=Counter[tuple[str, str]])
    cards_whose_evidence_text_changed: int = 0
    other_cards_changed: int = 0


def _by_range(cards: Sequence[ParsedCard]) -> dict[tuple[int, int], ParsedCard]:
    return {(card.provenance.first_element_index, card.provenance.last_element_index): card for card in cards}


def compare(before: ParsedDocument, after: ParsedDocument, parser: DebateDocxParser) -> Compared:
    """N1 switched off (`before`) and on (`after`), for one file."""
    compared = Compared(cards=len(after.cards))
    for section in after.sections:
        family = rule_family(section.match.rule_id)
        if family in _N1_RULES:
            compared.lines_made_body[family] += 1
    for position, line in lines_read_as_nothing(before.sections, before.cards):
        reading = read_between_body_paragraphs(before.sections[position].text, line, parser.profile)
        if reading.stratum is not None and reading.held_by is not None:
            compared.held_back[reading.stratum, reading.held_by] += 1
    earlier, later = _by_range(before.cards), _by_range(after.cards)
    compared.other_cards_changed += len(earlier.keys() ^ later.keys())
    for card_range in earlier.keys() & later.keys():
        was, now = earlier[card_range].model_dump(), later[card_range].model_dump()
        if was["evidence_text"] != now["evidence_text"]:
            compared.cards_whose_evidence_text_changed += 1
        if any(was[name] != now[name] for name in was if name not in _WHAT_N1_CHANGES):
            compared.other_cards_changed += 1
    return compared


@dataclass(frozen=True, slots=True)
class _Source:
    caselist: str
    sha256: str
    blob: Path


@dataclass(frozen=True, slots=True)
class _Result:
    without_a_blob: bool = False
    not_parsed: bool = False
    compared: Compared | None = None


_READINGS: tuple[_Reading, _Reading] | None = None


def _diff(source: _Source) -> _Result:
    global _READINGS  # noqa: PLW0603 - one pair of parsers per worker process
    if not source.blob.is_file():
        return _Result(without_a_blob=True)
    if _READINGS is None:
        _READINGS = (_Reading(with_n1=False), _Reading(with_n1=True))
    content = source.blob.read_bytes()
    snapshot = date(2026, 11, 3)
    record = SourceDocument(
        sha256=source.sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV if source.caselist == "openev" else SourceOrigin.CASELIST_ARCHIVE,
        caselist=None if source.caselist == "openev" else source.caselist,
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    before, after = (reading.parse(content, record, source_path="diffed.docx") for reading in _READINGS)
    if not isinstance(before, ParsedDocument) or not isinstance(after, ParsedDocument):
        return _Result(not_parsed=True)
    return _Result(compared=compare(before, after, _READINGS[1]))


def _newest_version(parsed: Path, caselist: str) -> Path:
    directory = parsed / caselist
    versions = (
        [path for path in directory.iterdir() if (path / "index.jsonl").is_file()]
        if directory.is_dir()
        else []
    )
    if not versions:
        raise SystemExit(f"{caselist}: no version directory with an index under {parsed}")
    return max(versions, key=lambda path: parse_version_directory(path.name))


def _sources(data_dir: Path, caselist: str, version: Path) -> list[_Source]:
    sources: list[_Source] = []
    for line in (version / "index.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("outcome") == "PARSED":
            digest = record["source_sha256"]
            blob = data_dir / BLOB_DIRECTORY / digest[:2] / digest[2:4] / digest
            sources.append(_Source(caselist, digest, blob))
    return sorted(sources, key=lambda source: source.sha256)


def diff_caselist(data_dir: Path, caselist: str, *, workers: int) -> dict[str, Any]:
    """The counts for one caselist."""
    started = time.monotonic()
    version = _newest_version(data_dir / "parsed", caselist)
    sources = _sources(data_dir, caselist, version)
    _progress(f"{caselist}: reading {len(sources):,} sources of {version.name} twice")
    if workers <= 1:
        results = [_diff(source) for source in sources]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_diff, sources, chunksize=8))
    compared = [result.compared for result in results if result.compared is not None]
    made: Counter[str] = Counter()
    held: Counter[tuple[str, str]] = Counter()
    for one in compared:
        made.update(one.lines_made_body)
        held.update(one.held_back)
    held_by_stratum: dict[str, dict[str, int]] = {}
    for (stratum, guard), count in sorted(held.items()):
        held_by_stratum.setdefault(stratum, {})[guard] = count
    return {
        "store_version": version.name,
        "parser_version": DOCX_PARSER_VERSION,
        "sources": len(sources),
        "sources_read": len(compared),
        "without_a_blob": sum(result.without_a_blob for result in results),
        "not_parsed": sum(result.not_parsed for result in results),
        "cards": sum(one.cards for one in compared),
        "lines_made_body": {rule: made[rule] for rule in _N1_RULES},
        "lines_held_back_by_the_cite_guard": held_by_stratum,
        "cards_whose_evidence_text_changed": sum(one.cards_whose_evidence_text_changed for one in compared),
        "files_with_a_card_whose_evidence_text_changed": sum(
            one.cards_whose_evidence_text_changed > 0 for one in compared
        ),
        "other_cards_changed": sum(one.other_cards_changed for one in compared),
        "seconds": round(time.monotonic() - started),
    }


def _summed(values: Sequence[Any]) -> Any:
    """Counts added up across caselists, key by key; anything that is not a count is left out."""
    if all(isinstance(value, Mapping) for value in values):
        keys = sorted({key for value in values for key in value})
        summed = {key: _summed([value[key] for value in values if key in value]) for key in keys}
        return {key: value for key, value in summed.items() if value is not None}
    if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return sum(values)
    return None


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".debate-research" / "dev",
        help="The data directory whose parsed store and blobs are read. Default: the dev data directory.",
    )
    parser.add_argument(
        "--caselist", action="append", help=f"Repeat for several. Default: {', '.join(CASELISTS)}."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 2),
        help="Processes for reading and parsing. Default: all processors but two.",
    )
    arguments = parser.parse_args(argv)
    started = time.monotonic()
    results = {
        caselist: diff_caselist(arguments.data_dir, caselist, workers=arguments.workers)
        for caselist in arguments.caselist or CASELISTS
    }
    output = {
        "caselists": results,
        "total": _summed(
            [{k: v for k, v in counts.items() if k != "seconds"} for counts in results.values()]
        ),
        "seconds": round(time.monotonic() - started),
    }
    print(json.dumps(output, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

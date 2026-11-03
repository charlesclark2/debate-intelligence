#!/usr/bin/env python3
"""Count the lines t24's rule leaves above a cite, bold in part, by shape. Counts only (`v1-e31-t32`).

`v1-e31-t24`'s rule reads a line directly above a cite that opens a card with no tag as the card's
tag only when Word shows it bold throughout. `v1-e31-t32`'s sample (seed 20261103) drew 24 of the lines
it leaves that fail it only by being bold in part, and the operator answered 19 tags. Split by where
the unbolded part sits (:class:`~debate_core.evidence.line_above_a_cite.BoldInPartShape`), every line
unbolded only at the tail with no digit in that tail was a tag, 17 of 17; a tail holding digits was a
tag 1 time in 4. This counts each shape in every caselist, so the PM can rule on a narrower rule
from the counts.

Per caselist, over every line directly above a cite that opens a card with no tag, read as body or
as nothing:

* the lines by the first condition of t24's rule each fails, as the sample's tally sheet gave them;
* the lines that fail only by being bold in part, by shape: lines, distinct lines and files;
* the lines bold in part that fail something else too, by shape and by each other condition.

"Distinct lines" counts a line's text once however many files hold it. The texts are compared in
memory only, by digest, and never written. Every source the store's newest version directory
recorded as parsed is parsed again from its blob by the parser this checkout carries, whatever
version wrote the directory: the counts are what that parser leaves.

**Read-only, and nothing but counts leaves it.** It reads the parsed store's index and the blobs
in place and writes nothing. Its output on stdout is counts, condition names and shape names: no
card text, tag, cite, heading, file name, path or digest. Progress goes to stderr.

    uv run python scripts/count_bold_in_part_tags.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.line_above_a_cite import (
    BoldInPartShape,
    FailingCondition,
    line_above,
    lines_above_cites,
    unbolded_part,
)
from debate_core.evidence.style_classifier import ParagraphDescription
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.docx_parser.runs import as_word_shows_it
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY

__all__ = ["count", "main"]

FAILS_NOTHING = "fails nothing: the cite is a guess a body may yet take"


@dataclass(frozen=True, slots=True)
class _Line:
    """One line left above a cite: what it fails, its shape when bold in part, its text's digest."""

    failing: tuple[FailingCondition, ...]
    shape: BoldInPartShape | None
    digest: str


@dataclass(frozen=True, slots=True)
class _Source:
    caselist: str
    sha256: str
    blob: Path


@dataclass(frozen=True, slots=True)
class _Counted:
    parsed: bool = False
    without_a_blob: bool = False
    lines: tuple[_Line, ...] = ()


class _ReadingParser(DebateDocxParser):
    """The parser, keeping each file's paragraphs as it read them and as Word shows them."""

    def __init__(self) -> None:
        super().__init__()
        self.descriptions: list[ParagraphDescription] = []
        self.shown: list[ParagraphDescription] = []

    def _read_sections(self, package: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        sections = super()._read_sections(package)  # pyright: ignore[reportPrivateUsage]
        self.descriptions = [section.read.description for section in sections]
        self.shown = [as_word_shows_it(description, package) for description in self.descriptions]
        return sections


_PARSER: _ReadingParser | None = None


def _count(source: _Source) -> _Counted:
    global _PARSER  # noqa: PLW0603 - one parser per worker process
    if not source.blob.is_file():
        return _Counted(without_a_blob=True)
    if _PARSER is None:
        _PARSER = _ReadingParser()
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
    document = _PARSER.parse(content, record, source_path="counted.docx")
    if not isinstance(document, ParsedDocument):
        return _Counted()
    found: list[_Line] = []
    for cite, line in lines_above_cites(
        _PARSER.descriptions,
        document.sections,
        document.cards,
        _PARSER.profile,
        shown=_PARSER.shown,
        cite_rules=None,
    ):
        position = line_above(document.sections, cite)
        if position is None or not (line.cite_opens_a_card_with_no_tag and line.read_as_body_or_nothing):
            continue
        failing = line.failing_conditions
        shape = None
        if FailingCondition.BOLD_IN_PART in failing:
            part = unbolded_part(_PARSER.shown[position])
            shape = None if part is None else part.shape
        text = " ".join(document.sections[position].text.split())
        found.append(_Line(failing, shape, hashlib.sha256(text.encode()).hexdigest()))
    return _Counted(parsed=True, lines=tuple(found))


def _by_shape(lines: Sequence[tuple[int, _Line]]) -> dict[str, dict[str, int]]:
    """Lines, distinct lines and files for each shape, every shape named."""
    return {
        shape.value: {
            "lines": sum(line.shape is shape for _, line in lines),
            "distinct_lines": len({line.digest for _, line in lines if line.shape is shape}),
            "files": len({source for source, line in lines if line.shape is shape}),
        }
        for shape in BoldInPartShape
    }


def _tally(lines: Sequence[tuple[int, _Line]]) -> dict[str, Any]:
    """The counts over some lines, each with the number of the source that holds it."""
    first = Counter(line.failing[0].value if line.failing else FAILS_NOTHING for _, line in lines)
    alone = [(source, line) for source, line in lines if line.failing == (FailingCondition.BOLD_IN_PART,)]
    more = [
        (source, line)
        for source, line in lines
        if line.failing[:1] == (FailingCondition.BOLD_IN_PART,) and len(line.failing) > 1
    ]
    return {
        "lines_left": len(lines),
        "by_first_failing_condition": {
            **{condition.value: first[condition.value] for condition in FailingCondition},
            FAILS_NOTHING: first[FAILS_NOTHING],
        },
        "bold_in_part_and_nothing_else": {
            "lines": len(alone),
            "distinct_lines": len({line.digest for _, line in alone}),
            "files": len({source for source, _ in alone}),
            "by_shape": _by_shape(alone),
        },
        "bold_in_part_and_something_else": {
            "lines": len(more),
            "by_shape": _by_shape(more),
            "by_other_condition": {
                condition.value: sum(condition in line.failing for _, line in more)
                for condition in FailingCondition
                if condition is not FailingCondition.BOLD_IN_PART
            },
        },
    }


def _caselists(parsed: Path) -> list[str]:
    """Every caselist the parsed store holds a version directory with an index for."""
    if not parsed.is_dir():
        raise SystemExit(f"no parsed store under {parsed.parent}")
    return sorted(
        directory.name
        for directory in parsed.iterdir()
        if directory.is_dir() and any((version / "index.jsonl").is_file() for version in directory.iterdir())
    )


def _newest_version(parsed: Path, caselist: str) -> Path:
    directory = parsed / caselist
    versions = (
        [path for path in directory.iterdir() if (path / "index.jsonl").is_file()]
        if directory.is_dir()
        else []
    )
    if not versions:
        raise SystemExit(f"{caselist}: no version directory with an index under the parsed store")
    return max(versions, key=lambda path: parse_version_directory(path.name))


def count(data_dir: Path, caselists: Sequence[str] | None, workers: int) -> dict[str, Any]:
    """The counts for each caselist and over all of them."""
    started = time.monotonic()
    parsed = data_dir / "parsed"
    names = list(caselists) if caselists else _caselists(parsed)
    results: dict[str, Any] = {}
    everywhere: list[tuple[int, _Line]] = []
    numbered = 0
    for caselist in names:
        caselist_started = time.monotonic()
        version = _newest_version(parsed, caselist)
        digests = sorted(
            record["source_sha256"]
            for record in map(json.loads, (version / "index.jsonl").read_text(encoding="utf-8").splitlines())
            if record.get("outcome") == "PARSED"
        )
        _progress(f"{caselist}: reading {len(digests):,} sources of {version.name}")
        sources = [
            _Source(caselist, digest, data_dir / BLOB_DIRECTORY / digest[:2] / digest[2:4] / digest)
            for digest in digests
        ]
        if workers <= 1:
            counted = [_count(source) for source in sources]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                counted = list(pool.map(_count, sources, chunksize=16))
        lines = [(numbered + k, line) for k, result in enumerate(counted) for line in result.lines]
        numbered += len(counted)
        everywhere += lines
        results[caselist] = {
            "store_version": version.name,
            "sources": len(digests),
            "parsed": sum(result.parsed for result in counted),
            "without_a_blob": sum(result.without_a_blob for result in counted),
            **_tally(lines),
            "seconds": round(time.monotonic() - caselist_started),
        }
    return {
        "parser_version": DOCX_PARSER_VERSION,
        "caselists": results,
        "every_caselist": {
            "sources": sum(result["sources"] for result in results.values()),
            "parsed": sum(result["parsed"] for result in results.values()),
            **_tally(everywhere),
        },
        "seconds": round(time.monotonic() - started),
    }


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
        "--caselist",
        action="append",
        help="Repeat for several. Default: every caselist the parsed store holds.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 2),
        help="Processes for reading and parsing. Default: all processors but two.",
    )
    arguments = parser.parse_args(argv)
    print(json.dumps(count(arguments.data_dir, arguments.caselist, arguments.workers), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Count the line above a cite the bracketed rule reads, over a parsed store. Counts only (`v1-e31-t24`).

`v1-e31-t19`'s item (7): a card read by the bracketed cite-line rule with no tag, and the line above
its cite, the card's tag in bold, read as body. Two counts per caselist, from the store's newest
version directory:

* **Above a bracketed cite.** Every cite read by a bracketed rule
  (`debate_core.evidence.line_above_a_cite.BRACKETED_CITE_RULES`) and what the paragraph directly
  above it was read as. The shape is a line read as body or as nothing, bold throughout as Word
  shows it or in a tag style. It is split by how the line is formatted, bold and size both as the
  reader gives them and as Word shows them, and by the files holding it.
* **In files whose defaults make text bold.** (7)'s lines say nothing of bold or size, and their
  file's document defaults make every such run bold at 13 pt, so Word shows a tag and the reader an
  unbolded line of no size. In every file whose document defaults, or default paragraph style,
  make text bold: the line above every cite, whatever read it, and every line read as body or as
  nothing that Word shows as the classifier's bold-heading rule would take it.

With `--every-source`, a third: **in every file**, the line above every cite, and how many lines the
rule proposed to the PM would take (`LineAboveACite.the_proposed_rule_takes`). That parses every
source and takes minutes; the two counts above parse only the sources they need and take seconds.

The store keeps no paragraphs, so each source counted is parsed again from its blob by the parser
this checkout carries, which must be the store's. A source whose parse does not give back the
stored cards' ranges is counted as such and not described.

**Read-only, and nothing but counts leaves it.** It reads the parsed store and the blobs in place
and writes nothing. Its output on stdout is counts and the names of rules: no card text, tag,
cite, heading, file name, path or digest. Progress goes to stderr.

    uv run python scripts/count_tag_above_bracketed_cite.py --expect-version 2026.10.20-docx-6
    uv run python scripts/count_tag_above_bracketed_cite.py --expect-version 2026.10.20-docx-6 --every-source
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import zipfile
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from debate_core.application.ports.parsed_store import parse_version_directory, source_object_key
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.line_above_a_cite import (
    BRACKETED_CITE_RULES,
    BoldLine,
    LineAboveACite,
    bold_lines_read_as_body_or_nothing,
    lines_above_cites,
    tally_bold_lines,
    tally_lines_above_cites,
)
from debate_core.evidence.style_classifier import ParagraphDescription
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION
from debate_core.integrations.docx_parser.runs import as_word_shows_it, defaults_make_text_bold
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY

__all__ = ["CASELISTS", "count_caselist", "main", "version_directory"]

CASELISTS = ("hsld26", "hspf26", "hspolicy26", "openev")

#: The most of a styles part read to look for bold defaults; past it the source is parsed anyway.
_STYLES_PART_BYTES = 8 * 1024 * 1024

#: A bold element in a document's run defaults or in a default style, on or off: a candidate only.
#: Whether the defaults make text bold is read from the parsed package.
_DEFAULTS_BLOCK = re.compile(
    rb"<w:docDefaults\b.*?</w:docDefaults>|<w:style\b[^>]*w:default=\"(?:1|true|on)\"[^>]*>.*?</w:style>",
    re.DOTALL,
)
_BOLD_ELEMENT = re.compile(rb"<w:b[\s/>]")


def version_directory(parsed: Path, caselist: str, expected: str | None) -> Path:
    """The newest version directory of `caselist` that holds an index, refused unless it is the
    parser version expected and the version this checkout's parser writes."""
    directory = parsed / caselist
    versions = (
        [path for path in directory.iterdir() if (path / "index.jsonl").is_file()]
        if directory.is_dir()
        else []
    )
    if not versions:
        raise SystemExit(f"{caselist}: no version directory with an index under {parsed}")
    newest = max(versions, key=lambda path: parse_version_directory(path.name))
    version = parse_version_directory(newest.name)[0]
    if expected is not None and version != expected:
        raise SystemExit(
            f"{caselist}: the newest version directory is {newest.name}, not {expected}: stopping"
        )
    if version != DOCX_PARSER_VERSION:
        raise SystemExit(
            f"{caselist}: the store is {version} and this checkout's parser is {DOCX_PARSER_VERSION}: "
            "the line above a cite is counted as the store's parser reads it"
        )
    return newest


def _parsed_sources(version: Path) -> list[str]:
    digests: list[str] = []
    for line in (version / "index.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("outcome") == "PARSED":
            digests.append(record["source_sha256"])
    return sorted(digests)


def _may_have_bold_defaults(blob: Path) -> bool:
    """A cheap look at the styles part: True for any file whose defaults hold a bold element."""
    try:
        with zipfile.ZipFile(blob) as archive:
            names = [name for name in archive.namelist() if name.endswith("styles.xml")]
            for name in names:
                with archive.open(name) as part:
                    styles = part.read(_STYLES_PART_BYTES)
                if any(_BOLD_ELEMENT.search(block.group(0)) for block in _DEFAULTS_BLOCK.finditer(styles)):
                    return True
    except (OSError, zipfile.BadZipFile):
        return True
    return False


@dataclass(frozen=True, slots=True)
class _Source:
    caselist: str
    sha256: str
    stored: Path
    blob: Path
    every_source: bool = False


@dataclass(frozen=True, slots=True)
class _Counted:
    parsed_again: bool = False
    not_reproduced: bool = False
    without_a_blob: bool = False
    defaults_bold: bool = False
    above_bracketed_cites: tuple[LineAboveACite, ...] = ()
    above_every_cite: tuple[LineAboveACite, ...] = ()
    bold_lines: tuple[BoldLine, ...] = ()
    """Filled in a file whose defaults make text bold only."""


class _ReadingParser(DebateDocxParser):
    """The parser, keeping each file's paragraphs as it read them and as Word shows them."""

    def __init__(self) -> None:
        super().__init__()
        self.descriptions: list[ParagraphDescription] = []
        self.shown: list[ParagraphDescription] = []
        self.defaults_bold = False

    def _read_sections(self, package: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        sections = super()._read_sections(package)  # pyright: ignore[reportPrivateUsage]
        self.descriptions = [section.read.description for section in sections]
        self.shown = [as_word_shows_it(description, package) for description in self.descriptions]
        self.defaults_bold = defaults_make_text_bold(package)
        return sections


_PARSER: _ReadingParser | None = None


def _parse(source: _Source, content: bytes) -> tuple[_ReadingParser, ParsedDocument | None]:
    global _PARSER  # noqa: PLW0603 - one parser per worker process
    if _PARSER is None:
        _PARSER = _ReadingParser()
    snapshot = date(2026, 10, 20)
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
    return _PARSER, document if isinstance(document, ParsedDocument) else None


def _count(source: _Source) -> _Counted:
    stored_text = source.stored.read_text(encoding="utf-8")
    bracketed = any(rule in stored_text for rule in BRACKETED_CITE_RULES)
    if not source.blob.is_file():
        return _Counted(without_a_blob=bracketed or source.every_source)
    if not source.every_source and not bracketed and not _may_have_bold_defaults(source.blob):
        return _Counted()
    parser, document = _parse(source, source.blob.read_bytes())
    # Split on newlines only: a card's text may hold U+2028, which `splitlines` also splits on.
    stored = json.loads(stored_text.split("\n")[1])["document"]["cards"]
    ranges = [
        (card["provenance"]["first_element_index"], card["provenance"]["last_element_index"])
        for card in stored
    ]
    if document is None or ranges != [
        (card.provenance.first_element_index, card.provenance.last_element_index) for card in document.cards
    ]:
        return _Counted(parsed_again=True, not_reproduced=True)
    every = lines_above_cites(
        parser.descriptions,
        document.sections,
        document.cards,
        parser.profile,
        shown=parser.shown,
        cite_rules=None,
    )
    above_bracketed = tuple(line for _, line in every if line.cite_rule in BRACKETED_CITE_RULES)
    if not parser.defaults_bold:
        return _Counted(
            parsed_again=True,
            above_bracketed_cites=above_bracketed,
            above_every_cite=tuple(line for _, line in every),
        )
    bold_lines = bold_lines_read_as_body_or_nothing(
        parser.descriptions, parser.shown, document.sections, document.cards, parser.profile
    )
    return _Counted(
        parsed_again=True,
        defaults_bold=True,
        above_bracketed_cites=above_bracketed,
        above_every_cite=tuple(line for _, line in every),
        bold_lines=tuple(bold_lines),
    )


def _files_holding_the_shape(counted: Sequence[_Counted], *, opening_a_card_with_no_tag: bool) -> int:
    return sum(
        any(
            line.is_the_shape and (line.cite_opens_a_card_with_no_tag or not opening_a_card_with_no_tag)
            for line in result.above_bracketed_cites
        )
        for result in counted
    )


def count_caselist(
    data_dir: Path, caselist: str, *, expected: str | None, workers: int, every_source: bool = False
) -> dict[str, Any]:
    """The counts for one caselist."""
    started = time.monotonic()
    store_root = data_dir / "parsed"
    version = version_directory(store_root, caselist, expected)
    digests = _parsed_sources(version)
    _progress(f"{caselist}: reading {len(digests):,} sources of {version.name}")
    sources = [
        _Source(
            caselist,
            digest,
            store_root / source_object_key(caselist, version.name, digest),
            data_dir / BLOB_DIRECTORY / digest[:2] / digest[2:4] / digest,
            every_source,
        )
        for digest in digests
    ]
    if workers <= 1:
        counted = [_count(source) for source in sources]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            counted = list(pool.map(_count, sources, chunksize=16))

    described = [result for result in counted if result.parsed_again and not result.not_reproduced]
    bracketed = [line for result in described for line in result.above_bracketed_cites]
    by_rule: dict[str, list[LineAboveACite]] = {}
    for line in bracketed:
        by_rule.setdefault(line.cite_rule, []).append(line)
    bold_files = [result for result in described if result.defaults_bold]
    every_cite = [line for result in bold_files for line in result.above_every_cite]
    counts: dict[str, Any] = {
        "version": version.name,
        "sources": len(digests),
        "sources_parsed_again": sum(result.parsed_again for result in counted),
        "not_reproduced": sum(result.not_reproduced for result in counted),
        "without_a_blob": sum(result.without_a_blob for result in counted),
        "above_a_bracketed_cite": {
            "files_holding_the_shape": _files_holding_the_shape(described, opening_a_card_with_no_tag=False),
            "files_holding_the_shape_above_a_cite_opening_a_card_with_no_tag": _files_holding_the_shape(
                described, opening_a_card_with_no_tag=True
            ),
            "every_bracketed_rule": tally_lines_above_cites(bracketed),
            "by_cite_rule": {rule: tally_lines_above_cites(found) for rule, found in sorted(by_rule.items())},
        },
        "in_files_whose_defaults_make_text_bold": {
            "files": len(bold_files),
            "above_every_cite": tally_lines_above_cites(every_cite),
            "above_every_cite_by_cite_rule": {
                rule: tally_lines_above_cites(line for line in every_cite if line.cite_rule == rule)
                for rule in sorted({line.cite_rule for line in every_cite})
            },
            "bold_lines_read_as_body_or_nothing": tally_bold_lines(
                line for result in bold_files for line in result.bold_lines
            ),
            "files_with_a_bold_line_read_as_body_or_nothing": sum(
                bool(result.bold_lines) for result in bold_files
            ),
        },
    }
    if every_source:
        everywhere = [line for result in described for line in result.above_every_cite]
        counts["in_every_file"] = {
            "above_every_cite": tally_lines_above_cites(everywhere),
            "above_every_cite_by_cite_rule": {
                rule: tally_lines_above_cites(line for line in everywhere if line.cite_rule == rule)
                for rule in sorted({line.cite_rule for line in everywhere})
            },
            "files_the_proposed_rule_reaches": sum(
                any(line.the_proposed_rule_takes for line in result.above_every_cite) for result in described
            ),
        }
    counts["seconds"] = round(time.monotonic() - started)
    return counts


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
        "--expect-version",
        help="Stop unless each caselist's newest version directory is of this parser version.",
    )
    parser.add_argument(
        "--every-source",
        action="store_true",
        help="Also parse every source and count the line above every cite in every file. Minutes.",
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
        caselist: count_caselist(
            arguments.data_dir,
            caselist,
            expected=arguments.expect_version,
            workers=arguments.workers,
            every_source=arguments.every_source,
        )
        for caselist in arguments.caselist or CASELISTS
    }
    output = {
        "bracketed_cite_rules": sorted(BRACKETED_CITE_RULES),
        "caselists": results,
        "seconds": round(time.monotonic() - started),
    }
    print(json.dumps(output, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

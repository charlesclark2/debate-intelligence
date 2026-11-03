#!/usr/bin/env python3
"""What `v1-e31-t24`'s bold-tag rule changes in a parsed store, card by card. Counts only.

The PM's check of 2026-10-20: re-parse, read-only, every file the rule can reach, once with the rule
switched off and once with it on, and show that the only cards that differ stand next to a line the
rule took. A file can be reached only if it holds a card with no tag and a cite, so those are the
sources read: every one whose stored cards hold such a card. Each is parsed twice from its blob by the
parser this checkout carries. Every card of the second reading is then one of:

* **a card that gains a tag**: it begins at a line the rule took, and is otherwise the card that began
  at the cite below that line: the same cite, body, formatting and last paragraph;
* **the card above, losing its last body paragraph**: it held the taken line as its last paragraph
  and now ends before it, with the same body less that paragraph;
* **unchanged**: the same card as the first reading gave.

Anything else is counted as **another card that changed**, and the PM's bar for it is 0. A card of the
first reading the second does not give back is counted too: a card above whose tag had nothing left
under it once the line was taken, and so became an analytic.

It also measures the guards the PM added to the sampled rule. The lines the sampled rule takes
(`LineAboveACite.the_proposed_rule_takes`, read on the first reading as Word shows it) and the lines
the parser took are compared, and each line the parser left is put down to its guard: a highlighted
run, the underline or emphasis character style, or another reason (a cite a body may yet take).

The first reading is also compared with the cards the store holds, by range: a difference there is a
change made since the store was written that is not this rule (`v1-e31-t24`'s ac4, the Undertag
step-over).

**Read-only, and nothing but counts leaves it.** No card text, tag, cite, file name, path or digest.

    uv run python scripts/diff_tag_above_a_cite.py --caselist hspf26
"""

from __future__ import annotations

import argparse
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

from debate_core.application.ports.parsed_store import parse_version_directory, source_object_key
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.domain.style_profile import RunEmphasis
from debate_core.evidence.line_above_a_cite import line_above, lines_above_cites
from debate_core.evidence.style_classifier import ParagraphDescription
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.docx_parser.runs import as_word_shows_it
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY

__all__ = ["CASELISTS", "TAKEN", "compare", "diff_caselist", "main"]

CASELISTS = ("hsld26", "hspf26", "hspolicy26", "openev")

#: The rule id the parser gives a line it took.
TAKEN = "assembly-bold-tag-above-a-cite"


class _Reading(DebateDocxParser):
    """The parser with the bold-tag rule on or off, keeping each paragraph as read and as Word shows it."""

    def __init__(self, *, with_the_rule: bool) -> None:
        super().__init__()
        self.with_the_rule = with_the_rule
        self.descriptions: list[ParagraphDescription] = []
        self.shown: list[ParagraphDescription] = []

    def _read_sections(self, package: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        sections = super()._read_sections(package)  # pyright: ignore[reportPrivateUsage]
        self.descriptions = [section.read.description for section in sections]
        self.shown = [as_word_shows_it(description, package) for description in self.descriptions]
        return sections

    def _bold_tags_above_cites(self, assembled: Any, package: Any) -> frozenset[int]:  # pyright: ignore[reportIncompatibleMethodOverride]
        if not self.with_the_rule:
            return frozenset()
        return super()._bold_tags_above_cites(assembled, package)  # pyright: ignore[reportPrivateUsage]


@dataclass(frozen=True, slots=True)
class Compared:
    """One file's two readings, in counts."""

    sampled_rule_takes: int = 0
    taken: int = 0
    left_highlighted: int = 0
    left_underline_or_emphasis_style: int = 0
    left_otherwise: int = 0
    taken_beyond_the_sampled_rule: int = 0
    cards_gaining_a_tag: int = 0
    cards_above_losing_their_last_body_paragraph: int = 0
    cards_above_that_vanish: int = 0
    cards_whose_heading_path_now_names_a_taken_line: int = 0
    cards_changed_only_in_their_heading_path: int = 0
    other_cards_changed: int = 0
    cards_unchanged: int = 0


def _says_nothing(section: Any) -> bool:
    """A blank line, a table cell or a text box, stepped over as the parser steps over them."""
    return (
        not section.text.strip()
        or section.in_table
        or section.match.rule_id.startswith(("assembly-text-box", "assembly-table-cell"))
    )


#: What a card that gains a tag may change besides its tag: where it begins, the headings above it,
#: and the rules it was built by (the tag's rule is one more, and the weakest source may be it).
_A_TAG_CHANGES = ("tag", "first_element_index", "section_path", "rule_ids", "confidence", "match_source")

#: What the card above may change when it loses its last paragraph.
_LOSING_THE_LINE_CHANGES = (
    "evidence_text",
    "formatting_spans",
    "font_size_spans",
    "last_element_index",
    "completeness",
    "rule_ids",
    "confidence",
    "match_source",
)


def _without(card: ParsedCard, *names: str) -> dict[str, Any]:
    dumped = card.model_dump(mode="json")
    provenance = dict(dumped.pop("provenance"))
    for name in names:
        dumped.pop(name, None)
        provenance.pop(name, None)
    return {**dumped, "provenance": provenance}


def _marks_read_evidence(description: ParagraphDescription, parser: DebateDocxParser) -> bool:
    for run in description.visible_runs:
        match = parser.profile.resolve_character_style(
            run.character_style_id, run.character_style_name, run.character_style_based_on
        )
        if match is not None and match.emphasis in (RunEmphasis.UNDERLINE, RunEmphasis.EMPHASIS):
            return True
    return False


def compare(before: ParsedDocument, after: ParsedDocument, reading: _Reading) -> Compared:
    """The counts for one file, read with the rule off (`before`, as `reading` read it) and on."""
    sections = after.sections
    taken = {section.element_index for section in sections if section.match.rule_id.startswith(TAKEN)}
    sampled = {
        before.sections[above].element_index
        for cite, line in lines_above_cites(
            reading.descriptions,
            before.sections,
            before.cards,
            reading.profile,
            shown=reading.shown,
            cite_rules=None,
        )
        if line.the_proposed_rule_takes and (above := line_above(before.sections, cite)) is not None
    }
    left = sampled - taken
    highlighted = {index for index in left if reading.descriptions[index].has_highlighted_run}
    styled = {
        index for index in left - highlighted if _marks_read_evidence(reading.descriptions[index], reading)
    }

    # The cite below each taken line: the first paragraph after it that says something.
    cite_of = {}
    for index in taken:
        below = index + 1
        while below < len(sections) and _says_nothing(sections[below]):
            below += 1
        cite_of[index] = below

    old = {card.provenance.first_element_index: card for card in before.cards}
    taken_texts = {sections[index].text for index in taken}
    counts: Counter[str] = Counter()
    matched_old: set[int] = set()
    for card in after.cards:
        first = card.provenance.first_element_index
        start = cite_of[first] if first in taken else first
        earlier = old.get(start)
        matched_old.add(start)
        if earlier is None:
            counts["other_cards_changed"] += 1
            continue
        if card == earlier:
            counts["cards_unchanged"] += 1
            continue
        effects = _effects(earlier, card, after, taken=taken, taken_texts=taken_texts, gains=first in taken)
        if effects is None:
            counts["other_cards_changed"] += 1
            continue
        for effect in effects:
            counts[effect] += 1
        if effects == {"cards_whose_heading_path_now_names_a_taken_line"}:
            counts["cards_changed_only_in_their_heading_path"] += 1
    for first, earlier in old.items():
        if first in matched_old:
            continue
        if earlier.provenance.last_element_index in taken:
            counts["cards_above_that_vanish"] += 1
        else:
            counts["other_cards_changed"] += 1
    return Compared(
        sampled_rule_takes=len(sampled),
        taken=len(taken),
        left_highlighted=len(highlighted),
        left_underline_or_emphasis_style=len(styled),
        left_otherwise=len(left - highlighted - styled),
        taken_beyond_the_sampled_rule=len(taken - sampled),
        **counts,
    )


def _effects(
    earlier: ParsedCard,
    card: ParsedCard,
    after: ParsedDocument,
    *,
    taken: set[int],
    taken_texts: set[str],
    gains: bool,
) -> set[str] | None:
    """Which of the rule's three effects turn `earlier` into `card`; None when they do not explain it.

    * it gains a tag: it now begins at a line the rule took, with that line as its tag;
    * it loses its last body paragraph: that paragraph was a line the rule took for the card below;
    * its heading path now names a taken line: a card with no tag further down, under the same
      block, whose path named the tag above it and now names the line the rule took after that tag.
    """
    effects: set[str] = set()
    expected = earlier.model_dump(mode="json")
    if gains:
        if (earlier.tag or "").strip():
            return None
        effects.add("cards_gaining_a_tag")
    last = earlier.provenance.last_element_index
    if last in taken and card.provenance.last_element_index < last:
        line = next(section for section in after.sections if section.element_index == last)
        kept = earlier.evidence_text.removesuffix(line.text).removesuffix("\n")
        if (
            kept == earlier.evidence_text
            or card.evidence_text != kept
            or card.provenance.last_element_index >= last
        ):
            return None
        effects.add("cards_above_losing_their_last_body_paragraph")
        expected["evidence_text"] = card.evidence_text
    if not gains and card.section_path != earlier.section_path:
        # The taken line is now the open tag: it takes the place of the tag above, or is added
        # where no tag was open.
        new, old = card.section_path, earlier.section_path
        if not new or new[-1] not in taken_texts or new[:-1] not in (old, old[:-1]):
            return None
        effects.add("cards_whose_heading_path_now_names_a_taken_line")
    changes = set(_A_TAG_CHANGES) if gains else {"section_path"}
    if "cards_above_losing_their_last_body_paragraph" in effects:
        changes |= set(_LOSING_THE_LINE_CHANGES)
    if _without(card, *changes) != _without(earlier, *changes):
        return None
    return effects


@dataclass(frozen=True, slots=True)
class _Source:
    caselist: str
    sha256: str
    stored: Path
    blob: Path


@dataclass(frozen=True, slots=True)
class _Result:
    read: bool = False
    without_a_blob: bool = False
    not_parsed: bool = False
    first_reading_differs_from_the_store: bool = False
    compared: Compared | None = None


_READINGS: tuple[_Reading, _Reading] | None = None


def _diff(source: _Source) -> _Result:
    global _READINGS  # noqa: PLW0603 - one pair of parsers per worker process
    lines = source.stored.read_text(encoding="utf-8").split("\n")
    if len(lines) < 2 or not lines[1].strip():
        return _Result()
    stored = json.loads(lines[1])["document"]["cards"]
    if not any(
        not (card.get("tag") or "").strip() and (card.get("full_cite") or "").strip() for card in stored
    ):
        return _Result()
    if not source.blob.is_file():
        return _Result(without_a_blob=True)
    if _READINGS is None:
        _READINGS = (_Reading(with_the_rule=False), _Reading(with_the_rule=True))
    content = source.blob.read_bytes()
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
    without, with_ = _READINGS
    after = with_.parse(content, record, source_path="compared.docx")
    before = without.parse(content, record, source_path="compared.docx")
    if not isinstance(before, ParsedDocument) or not isinstance(after, ParsedDocument):
        return _Result(read=True, not_parsed=True)
    ranges = [
        (card["provenance"]["first_element_index"], card["provenance"]["last_element_index"])
        for card in stored
    ]
    differs = ranges != [
        (c.provenance.first_element_index, c.provenance.last_element_index) for c in before.cards
    ]
    return _Result(
        read=True, first_reading_differs_from_the_store=differs, compared=compare(before, after, without)
    )


def _newest_version(parsed: Path, caselist: str) -> Path:
    versions = [path for path in (parsed / caselist).iterdir() if (path / "index.jsonl").is_file()]
    return max(versions, key=lambda path: parse_version_directory(path.name))


def diff_caselist(data_dir: Path, caselist: str, *, workers: int) -> dict[str, Any]:
    """The counts for one caselist, summed over its files."""
    started = time.monotonic()
    version = _newest_version(data_dir / "parsed", caselist)
    digests = sorted(
        record["source_sha256"]
        for line in (version / "index.jsonl").read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line)).get("outcome") == "PARSED"
    )
    print(f"{caselist}: {len(digests):,} sources of {version.name}", file=sys.stderr, flush=True)
    sources = [
        _Source(
            caselist,
            digest,
            data_dir / "parsed" / source_object_key(caselist, version.name, digest),
            data_dir / BLOB_DIRECTORY / digest[:2] / digest[2:4] / digest,
        )
        for digest in digests
    ]
    if workers <= 1:
        results = [_diff(source) for source in sources]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_diff, sources, chunksize=8))
    compared = [result.compared for result in results if result.compared is not None]
    totals: Counter[str] = Counter()
    for one in compared:
        for name in Compared.__dataclass_fields__:
            totals[name] += getattr(one, name)
    return {
        "version": version.name,
        "sources": len(digests),
        "sources_read": sum(result.read for result in results),
        "without_a_blob": sum(result.without_a_blob for result in results),
        "not_parsed": sum(result.not_parsed for result in results),
        "first_reading_differs_from_the_store": sum(r.first_reading_differs_from_the_store for r in results),
        "files_with_a_line_taken": sum(one.taken > 0 for one in compared),
        "files_the_sampled_rule_reaches": sum(one.sampled_rule_takes > 0 for one in compared),
        **dict(sorted(totals.items())),
        "seconds": round(time.monotonic() - started),
    }


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
        help="Processes for parsing. Default: all processors but two.",
    )
    arguments = parser.parse_args(argv)
    output = {
        caselist: diff_caselist(arguments.data_dir, caselist, workers=arguments.workers)
        for caselist in arguments.caselist or CASELISTS
    }
    print(json.dumps(output, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

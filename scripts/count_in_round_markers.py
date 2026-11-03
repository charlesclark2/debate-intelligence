#!/usr/bin/env python3
"""Count in-round markers and the lines read as nothing between body paragraphs. Counts only (`v1-e31-t23`).

Two populations, ruled on one table, per caselist, from the store's newest version directory:

* **Marker-shaped lines**, by form (a pattern id from
  :class:`debate_core.evidence.in_round_markers.LineForm`, never the line's text), by how the parser
  reads them (body, nothing, a cite) and by where they stand (the end of a body, inside it).
* **The lines read as nothing between two body paragraphs of one card**, `v1-e31-t19`'s 43,488, by
  the same form ids, and by `v1-e31-t19`'s length bands, sentence end and capitals.

And **how many clusters the markers split today**: for each set of marker forms, every body those
lines change, as it would be matched without them (the lines left out, and the halves a marker read
as a cite divides joined again), set against the store's occurrence table: the marker-free
fingerprints another card already has, and how many of today's clusters each such body spans. That
is the exact-fingerprint view: two copies that differ only by a marker and that the near-duplicate
rules already joined span one cluster and are not counted as split.

The store keeps no paragraphs, so every source is parsed again from its blob by the parser this
checkout carries. The lines are counted on that parse, which is what a ruling would change. Where
the store was written by another parser version, some sources' cards differ from the stored ones;
they are counted (`sources_whose_cards_differ_from_the_store`), and a fingerprint the occurrence
table does not hold is counted and joins no cluster.

**Read-only, and nothing but counts leaves it.** It reads the parsed store and the blobs in place
and writes nothing. Its output on stdout is counts, form ids and the names of rules: no card text,
tag, cite, heading, file name, path or digest. Progress goes to stderr.

    uv run python scripts/count_in_round_markers.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from debate_core.application.ports.parsed_store import parse_version_directory, source_object_key
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.in_round_markers import (
    MARKER_FORMS,
    LineForm,
    LinePlace,
    MarkerFreeBody,
    Reading,
    describe_lines,
    marker_free_bodies,
)
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY

__all__ = ["CASELISTS", "FORM_SETS", "count_caselist", "main", "version_directory"]

CASELISTS = ("hsld26", "hspf26", "hspolicy26", "openev")

#: The sets of marker forms a ruling could leave out of matching, each counted for the clusters it
#: splits: each form alone, the three that say nothing but the mark, and all four.
FORM_SETS: Mapping[str, tuple[LineForm, ...]] = {
    **{form.value: (form,) for form in MARKER_FORMS},
    "+".join(form.value for form in MARKER_FORMS[:3]): MARKER_FORMS[:3],
    "every-marker-form": MARKER_FORMS,
}

#: The forms whose rules and files are counted: the marker forms and a marker inside a line.
_MARKER_SHAPED = (*MARKER_FORMS, LineForm.MARKER_INSIDE_A_LINE)
_MARKER_SHAPED_IDS = frozenset(form.value for form in _MARKER_SHAPED)


def version_directory(parsed: Path, caselist: str, expected: str | None) -> Path:
    """The newest version directory of `caselist` that holds an index, refused unless it is the
    parser version expected, when one is."""
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
    return newest


def _parsed_sources(version: Path) -> list[str]:
    digests: list[str] = []
    for line in (version / "index.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("outcome") == "PARSED":
            digests.append(record["source_sha256"])
    return sorted(digests)


@dataclass(frozen=True, slots=True)
class _Source:
    caselist: str
    sha256: str
    stored: Path
    blob: Path


@dataclass(slots=True)
class _Counted:
    without_a_blob: bool = False
    not_parsed: bool = False
    differs_from_the_store: bool = False
    cards: int = 0
    lines: Counter[tuple[str, str, str]] = field(default_factory=Counter[tuple[str, str, str]])
    """(reading, form, place) for every line."""
    rules: Counter[tuple[str, str, str]] = field(default_factory=Counter[tuple[str, str, str]])
    """(reading, form, rule family) for every marker-shaped line."""
    read_as_nothing: Counter[tuple[str, str, bool, bool]] = field(
        default_factory=Counter[tuple[str, str, bool, bool]]
    )
    """(place, length band, ends a sentence, in capitals) for every line read as nothing."""
    cards_holding: Counter[tuple[str, str, str]] = field(default_factory=Counter[tuple[str, str, str]])
    """(reading, form, place) once per card that holds such a line."""
    cards_with_a_line_between_body_paragraphs: int = 0
    forms_held: frozenset[tuple[str, str]] = frozenset()
    """(reading, form) of the marker-shaped lines the file holds."""
    bodies: dict[str, list[MarkerFreeBody]] = field(default_factory=dict[str, list[MarkerFreeBody]])


_PARSER: DebateDocxParser | None = None


def _parse(source: _Source, content: bytes) -> ParsedDocument | None:
    global _PARSER  # noqa: PLW0603 - one parser per worker process
    if _PARSER is None:
        _PARSER = DebateDocxParser()
    snapshot = date(2026, 11, 2)
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
    return document if isinstance(document, ParsedDocument) else None


def _count(source: _Source) -> _Counted:
    if not source.blob.is_file():
        return _Counted(without_a_blob=True)
    document = _parse(source, source.blob.read_bytes())
    if document is None:
        return _Counted(not_parsed=True)
    # Split on newlines only: a card's text may hold U+2028, which `splitlines` also splits on.
    stored = json.loads(source.stored.read_text(encoding="utf-8").split("\n")[1])["document"]["cards"]
    counted = _Counted(
        cards=len(document.cards),
        differs_from_the_store=[
            (card["provenance"]["first_element_index"], card["provenance"]["last_element_index"])
            for card in stored
        ]
        != [
            (card.provenance.first_element_index, card.provenance.last_element_index)
            for card in document.cards
        ],
    )
    held: set[tuple[str, str, str, int]] = set()
    between: set[int] = set()
    for line in describe_lines(document.sections, document.cards):
        counted.lines[line.reading.value, line.form.value, line.place.value] += 1
        if line.form in _MARKER_SHAPED:
            counted.rules[line.reading.value, line.form.value, line.rule] += 1
        if line.reading is Reading.NOTHING:
            counted.read_as_nothing[
                line.place.value, line.length_band, line.ends_a_sentence, line.in_capitals
            ] += 1
            if line.place is LinePlace.BETWEEN_BODY_PARAGRAPHS and line.card is not None:
                between.add(line.card)
        if line.card is not None:
            held.add((line.reading.value, line.form.value, line.place.value, line.card))
    for reading, form, place, _card in held:
        counted.cards_holding[reading, form, place] += 1
    counted.cards_with_a_line_between_body_paragraphs = len(between)
    counted.forms_held = frozenset(
        (reading, form) for (reading, form, _place) in counted.lines if form in _MARKER_SHAPED_IDS
    )
    counted.bodies = {
        name: marker_free_bodies(document.sections, document.cards, forms)
        for name, forms in FORM_SETS.items()
    }
    return counted


def _nested(counter: Mapping[tuple[str, ...], int]) -> dict[str, Any]:
    """`{("a", "b", "c"): 1}` as `{"a": {"b": {"c": 1}}}`, keys sorted."""
    tree: dict[str, Any] = {}
    for key, count in sorted(counter.items()):
        node = tree
        for part in key[:-1]:
            node = node.setdefault(part, {})
        node[key[-1]] = node.get(key[-1], 0) + count
    return tree


def _read_as_nothing_by_place(counter: Mapping[tuple[str, str, bool, bool], int]) -> dict[str, Any]:
    by_place: dict[str, Any] = {}
    for (place, band, ends, capitals), count in sorted(counter.items()):
        bands = by_place.setdefault(place, {}).setdefault(
            band, {"lines": 0, "no_sentence_end": 0, "ends_a_sentence": 0, "in_capitals": 0}
        )
        bands["lines"] += count
        bands["ends_a_sentence" if ends else "no_sentence_end"] += count
        bands["in_capitals"] += count if capitals else 0
    return by_place


def _occurrence_clusters(version: Path) -> tuple[dict[str, set[str]], int, list[str]]:
    """Each exact fingerprint's clusters, the rows read, and the fingerprint versions they carry."""
    clusters: dict[str, set[str]] = {}
    rows = 0
    versions: set[str] = set()
    table = version / "occurrences.jsonl"
    if not table.is_file():
        return clusters, rows, []
    with table.open(encoding="utf-8") as lines:
        for line in lines:
            if not line.strip():
                continue
            row = json.loads(line)
            clusters.setdefault(row["exact_fingerprint"], set()).add(row["cluster_id"])
            versions.add(row["fingerprint_version"])
            rows += 1
    return clusters, rows, sorted(versions)


def _clusters_split(bodies: Iterable[MarkerFreeBody], clusters_of: Mapping[str, set[str]]) -> dict[str, int]:
    """What leaving one set of forms out of matching would do, against today's clusters."""
    groups: dict[str, set[tuple[str, ...]]] = {}
    changed = joined = 0
    for body in bodies:
        changed += 1
        joined += len(body.exact_fingerprints) > 1
        groups.setdefault(body.fingerprint, set()).add(body.exact_fingerprints)
    held_today = with_a_copy = split = would_join = not_in_the_table = 0
    for fingerprint, parts in groups.items():
        exact = {digest for part in parts for digest in part}
        not_in_the_table += sum(digest not in clusters_of for digest in exact)
        another_card_has_it = fingerprint in clusters_of and fingerprint not in exact
        held_today += another_card_has_it
        with_a_copy += len(parts) + another_card_has_it >= 2
        spanned = set[str]().union(*(clusters_of.get(digest, set()) for digest in (exact | {fingerprint})))
        if len(spanned) >= 2:
            split += 1
            would_join += len(spanned) - 1
    return {
        "bodies_changed": changed,
        "bodies_joined_across_a_marker_read_as_a_cite": joined,
        "marker_free_fingerprints": len(groups),
        "marker_free_fingerprints_another_card_has_today": held_today,
        "marker_free_fingerprints_held_by_two_copies_or_more": with_a_copy,
        "marker_free_fingerprints_spanning_two_clusters_or_more": split,
        "clusters_that_would_join_one_another": would_join,
        "exact_fingerprints_the_occurrence_table_does_not_hold": not_in_the_table,
    }


def count_caselist(data_dir: Path, caselist: str, *, expected: str | None, workers: int) -> dict[str, Any]:
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
        )
        for digest in digests
    ]
    if workers <= 1:
        counted = [_count(source) for source in sources]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            counted = list(pool.map(_count, sources, chunksize=16))
    clusters_of, rows, fingerprint_versions = _occurrence_clusters(version)

    lines: Counter[tuple[str, str, str]] = Counter()
    rules: Counter[tuple[str, str, str]] = Counter()
    nothing: Counter[tuple[str, str, bool, bool]] = Counter()
    cards_holding: Counter[tuple[str, str, str]] = Counter()
    files_holding: Counter[tuple[str, str]] = Counter()
    for result in counted:
        lines.update(result.lines)
        rules.update(result.rules)
        nothing.update(result.read_as_nothing)
        cards_holding.update(result.cards_holding)
        files_holding.update(result.forms_held)
    return {
        "store_version": version.name,
        "parser_version": DOCX_PARSER_VERSION,
        "sources": len(digests),
        "sources_parsed_again": sum(not (r.without_a_blob or r.not_parsed) for r in counted),
        "without_a_blob": sum(r.without_a_blob for r in counted),
        "not_parsed": sum(r.not_parsed for r in counted),
        "sources_whose_cards_differ_from_the_store": sum(r.differs_from_the_store for r in counted),
        "cards": sum(r.cards for r in counted),
        "lines": _nested(lines),
        "marker_shaped_lines_by_rule": _nested(rules),
        "cards_holding": _nested(cards_holding),
        "cards_with_a_line_read_as_nothing_between_body_paragraphs": sum(
            r.cards_with_a_line_between_body_paragraphs for r in counted
        ),
        "files_holding_a_marker_shaped_line": _nested(files_holding),
        "read_as_nothing_by_length": _read_as_nothing_by_place(nothing),
        "occurrence_rows": rows,
        "occurrence_fingerprint_versions": fingerprint_versions,
        "clusters": {
            name: _clusters_split((body for r in counted for body in r.bodies.get(name, ())), clusters_of)
            for name in FORM_SETS
        },
        "seconds": round(time.monotonic() - started),
    }


def _summed(values: Sequence[Any]) -> Any:
    """Counts added up across caselists, key by key; anything that is not a count is left out."""
    if all(isinstance(value, dict) for value in values):
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
        "--expect-version",
        help="Stop unless each caselist's newest version directory is of this parser version.",
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
            arguments.data_dir, caselist, expected=arguments.expect_version, workers=arguments.workers
        )
        for caselist in arguments.caselist or CASELISTS
    }
    output = {
        "form_sets": {name: [form.value for form in forms] for name, forms in FORM_SETS.items()},
        "caselists": results,
        "total": _summed(
            [
                {key: value for key, value in counts.items() if key not in ("seconds", "occurrence_rows")}
                for counts in results.values()
            ]
        ),
        "seconds": round(time.monotonic() - started),
    }
    print(json.dumps(output, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

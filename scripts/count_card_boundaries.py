#!/usr/bin/env python3
"""Count the card boundaries the parser misses, over a parsed store. Counts only (`v1-e31-t22`).

Two counts per caselist, read from the store's newest version directory:

* **Bodies too long to be one card**: every stored card whose body is over 3,000 words
  (`debate_core.evidence.card_boundaries.LONG_BODY_WORDS`). The store keeps no paragraphs, so each
  source holding one is parsed again from its blob, by the parser this checkout carries, and the
  card is described by its file's paragraphs: what ended it, whether the file writes tags at all or
  uses any debate style, and what is inside the body. A card the parse does not reproduce exactly
  (another range or another body) is counted as such and not described: it means the checkout's
  parser is not the one that wrote the store.
* **Two cards stored as one**: every distinct full body that holds two or more shorter bodies whole
  that share no five-word run with each other, by the clusterer's own reading of "holds"
  (`debate_core.evidence.near_duplicates.CutIndex`); and, more loosely, two that do not overlap.

**Read-only, and nothing but counts leaves it.** It reads the parsed store and the blobs in place
and writes nothing to the data directory. Its output on stdout is counts and the names of rules:
no card text, tag, cite, heading, file name, path or digest. `--save-candidates FILE` also writes,
outside the repository, the store positions of what was counted (source digests and paragraph
indices, no text), so that a sample can draw from them without counting again. Progress goes to
stderr.

    uv run python scripts/count_card_boundaries.py --expect-version 2026.10.18-docx-5 \\
        --save-candidates ~/.debate-research/dev/card-boundaries-t22.jsonl > ~/t22-card-boundary-counts.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from debate_core.application.ports.parsed_store import parse_version_directory, source_object_key
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.card_boundaries import (
    LONG_BODY_WORDS,
    Holding,
    LongBody,
    bodies_holding_two_cards,
    is_too_long_to_be_one_card,
    read_long_body,
    tally_holdings,
    tally_long_bodies,
    word_count,
)
from debate_core.evidence.fingerprints import fingerprint_text
from debate_core.evidence.near_duplicates import CutIndex
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY

__all__ = ["CASELISTS", "StoredCard", "count_caselist", "main", "stored_cards", "version_directory"]

REPO_ROOT = Path(__file__).resolve().parent.parent

CASELISTS = ("hsld26", "hspf26", "hspolicy26", "openev")

type CardKey = tuple[str, int]
"""A card position: its source's SHA-256 and its first element index."""


@dataclass(frozen=True, slots=True)
class StoredCard:
    """What the counts need of one stored card. `body` is kept for a full card only."""

    sha256: str
    first: int
    last: int
    completeness: str
    words: int
    fingerprint: str
    body: str

    @property
    def key(self) -> CardKey:
        return (self.sha256, self.first)


def version_directory(parsed: Path, caselist: str, expected: str | None) -> Path:
    """The newest version directory of `caselist` that holds an index, refused unless it is the
    parser version expected."""
    directory = parsed / caselist
    versions = (
        [path for path in directory.iterdir() if (path / "index.jsonl").is_file()]
        if directory.is_dir()
        else []
    )
    if not versions:
        raise SystemExit(f"{caselist}: no version directory with an index under {parsed}")
    newest = max(versions, key=lambda path: parse_version_directory(path.name))
    if expected is not None and parse_version_directory(newest.name)[0] != expected:
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


def _read_source(path: Path) -> list[StoredCard]:
    """The cards of one per-source file, read as JSON."""
    with path.open(encoding="utf-8") as stream:
        stream.readline()
        document = json.loads(stream.readline())["document"]
    sha256 = document["source_sha256"]
    cards: list[StoredCard] = []
    for card in document["cards"]:
        body = card["evidence_text"]
        full = card["completeness"] == "FULL"
        cards.append(
            StoredCard(
                sha256=sha256,
                first=card["provenance"]["first_element_index"],
                last=card["provenance"]["last_element_index"],
                completeness=card["completeness"],
                words=word_count(body),
                fingerprint=fingerprint_text(body) if body else "",
                body=body if full else "",
            )
        )
    return cards


def stored_cards(
    store_root: Path, caselist: str, version: str, digests: Sequence[str], workers: int
) -> list[StoredCard]:
    """Every card the store holds for `digests`, in source order."""
    paths = [store_root / source_object_key(caselist, version, digest) for digest in digests]
    if workers <= 1:
        per_source = [_read_source(path) for path in paths]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_source = list(pool.map(_read_source, paths, chunksize=32))
    return [card for cards in per_source for card in cards]


# ------------------------------------------------------------------------------------------------
# Long bodies, read again from their sources
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _LongBodySource:
    caselist: str
    sha256: str
    blob: Path
    ranges: tuple[tuple[int, int, int], ...]
    """(first index, last index, words) of each long card the store holds for the source."""


@dataclass(frozen=True, slots=True)
class _LongBodiesRead:
    described: tuple[tuple[int, LongBody], ...]
    not_reproduced: int
    without_a_blob: int


_PARSER: DebateDocxParser | None = None


def _parse(source: _LongBodySource) -> ParsedDocument | None:
    global _PARSER  # noqa: PLW0603 - one parser per worker process
    if _PARSER is None:
        _PARSER = DebateDocxParser()
    content = source.blob.read_bytes()
    snapshot = date(2026, 10, 19)
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


def _describe(source: _LongBodySource) -> _LongBodiesRead:
    if not source.blob.is_file():
        return _LongBodiesRead((), 0, without_a_blob=len(source.ranges))
    document = _parse(source)
    cards = {} if document is None else {card.provenance.first_element_index: card for card in document.cards}
    described: list[tuple[int, LongBody]] = []
    not_reproduced = 0
    for first, last, words in source.ranges:
        card = cards.get(first)
        if (
            document is None
            or card is None
            or card.provenance.last_element_index != last
            or word_count(card.evidence_text) != words
        ):
            not_reproduced += 1
            continue
        described.append((first, read_long_body(document, card, _PARSER.profile)))  # type: ignore[union-attr]
    return _LongBodiesRead(tuple(described), not_reproduced, without_a_blob=0)


def describe_long_bodies(
    caselist: str, long_cards: Sequence[StoredCard], blobs: Path, workers: int
) -> tuple[dict[CardKey, LongBody], int, int]:
    """Each long card described by its file's paragraphs; how many the parse did not reproduce; and
    how many are in a source with no blob on this machine."""
    ranges: defaultdict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for card in long_cards:
        ranges[card.sha256].append((card.first, card.last, card.words))
    sources = [
        _LongBodySource(caselist, digest, blobs / digest[:2] / digest[2:4] / digest, tuple(sorted(found)))
        for digest, found in sorted(ranges.items())
    ]
    if workers <= 1:
        results = [_describe(source) for source in sources]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_describe, sources, chunksize=4))
    described: dict[CardKey, LongBody] = {}
    not_reproduced = without_a_blob = 0
    for source, result in zip(sources, results, strict=True):
        not_reproduced += result.not_reproduced
        without_a_blob += result.without_a_blob
        for first, body in result.described:
            described[(source.sha256, first)] = body
    return described, not_reproduced, without_a_blob


# ------------------------------------------------------------------------------------------------
# One caselist
# ------------------------------------------------------------------------------------------------


def _first_card_of(cards: Iterable[StoredCard]) -> dict[str, CardKey]:
    """For each full body, the first store position that carries it."""
    first: dict[str, CardKey] = {}
    for card in sorted(cards, key=lambda card: card.key):
        if card.completeness == "FULL":
            first.setdefault(card.fingerprint, card.key)
    return first


def _candidates(
    caselist: str,
    described: Mapping[CardKey, LongBody],
    holdings: Sequence[Holding],
    position_of: Mapping[str, CardKey],
) -> list[dict[str, Any]]:
    """What was counted, by store position: digests and indices, no text."""
    rows: list[dict[str, Any]] = [
        {"caselist": caselist, "count": "long-body", "group": body.kind.value, "card": list(key)}
        for key, body in sorted(described.items())
    ]
    for holding in holdings:
        pair = holding.pair_sharing_nothing or holding.pair_not_overlapping
        assert pair is not None  # noqa: S101 - every holding has a pair that does not overlap
        rows.append(
            {
                "caselist": caselist,
                "count": "two-cards-in-one",
                "group": "sharing nothing" if holding.pair_sharing_nothing else "not overlapping",
                "card": list(position_of[holding.holder]),
                "pieces": [list(position_of[piece]) for piece in pair],
            }
        )
    return rows


def count_caselist(
    data_dir: Path, caselist: str, *, expected: str | None, workers: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The counts for one caselist, and the candidates they were counted from."""
    started = time.monotonic()
    store_root = data_dir / "parsed"
    version = version_directory(store_root, caselist, expected)
    digests = _parsed_sources(version)
    _progress(f"{caselist}: reading {len(digests):,} sources of {version.name}")
    cards = stored_cards(store_root, caselist, version.name, digests, workers)
    read_at = time.monotonic()

    long_cards = [
        card for card in cards if card.completeness != "CITE_ONLY" and is_too_long_to_be_one_card(card.words)
    ]
    _progress(f"{caselist}: parsing again the sources of {len(long_cards):,} long bodies")
    described, not_reproduced, without_a_blob = describe_long_bodies(
        caselist, long_cards, data_dir / BLOB_DIRECTORY, workers
    )
    described_at = time.monotonic()

    full = [card for card in cards if card.completeness == "FULL"]
    bodies: dict[str, str] = {}
    for card in full:
        bodies.setdefault(card.fingerprint, card.body)
    _progress(f"{caselist}: finding which of {len(bodies):,} full texts hold which")
    index = CutIndex(bodies)
    holdings = bodies_holding_two_cards(index)
    long_texts = frozenset(card.fingerprint for card in long_cards if card.completeness == "FULL")
    two_cards = tally_holdings(
        holdings,
        index,
        cards_by_fingerprint=Counter(card.fingerprint for card in full),
        long_bodies=long_texts,
    )
    finished = time.monotonic()

    counts: dict[str, Any] = {
        "version": version.name,
        "sources": len(digests),
        "cards": len(cards),
        "full_cards": len(full),
        "long_bodies": {
            "texts": len({card.fingerprint for card in long_cards}),
            "not_reproduced": not_reproduced,
            "in_a_source_with_no_blob": without_a_blob,
            **tally_long_bodies(described[key] for key in sorted(described)),
        },
        "two_cards_in_one": two_cards,
        "seconds": {
            "reading": round(read_at - started),
            "long_bodies": round(described_at - read_at),
            "two_cards_in_one": round(finished - described_at),
        },
    }
    return counts, _candidates(caselist, described, holdings, _first_card_of(cards))


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _outside_the_repository(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(REPO_ROOT):
        raise SystemExit("--save-candidates must be outside the repository: what it names is the operator's")
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
        "--caselist", action="append", help=f"Repeat for several. Default: {', '.join(CASELISTS)}."
    )
    parser.add_argument(
        "--expect-version",
        help="Stop unless each caselist's newest version directory is of this parser version.",
    )
    parser.add_argument(
        "--save-candidates",
        type=Path,
        help="Also write the positions counted (digests, indices) to this file, outside the repository.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 2),
        help="Processes for reading and parsing. Default: all processors but two.",
    )
    arguments = parser.parse_args(argv)
    saved = _outside_the_repository(arguments.save_candidates) if arguments.save_candidates else None

    started = time.monotonic()
    results: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    for caselist in arguments.caselist or CASELISTS:
        counts, found = count_caselist(
            arguments.data_dir, caselist, expected=arguments.expect_version, workers=arguments.workers
        )
        results[caselist] = counts
        candidates.extend(found)
    output = {
        "long_body_words": LONG_BODY_WORDS,
        "caselists": results,
        "seconds": round(time.monotonic() - started),
    }
    print(json.dumps(output, indent=1, sort_keys=True))
    if saved is not None:
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in candidates), encoding="utf-8"
        )
        _progress(f"{len(candidates):,} candidates written to {saved.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

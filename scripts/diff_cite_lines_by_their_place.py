#!/usr/bin/env python3
"""What `v1-e31-t31`'s rules change in a parsed store, card by card. Counts only, unless sampling.

The PM's ruling of 2026-10-27, Q2 (b): after the rules are built, re-parse the store read-only, one
caselist at a time, and count the cards that gain a cite, by shape, caselist and template family, and
how many of the dev index's 6,214 documents with no cite gain one.

Every source the store holds under its newest version directory (`2026.10.20-docx-6`) is parsed again
from its blob by the parser this checkout carries (`2026.10.27-docx-7`). Its cards are compared with
the cards the store holds, matched by their last paragraph, which no rule of this task moves. Every
card of the new reading is one of:

* **a card that gains a cite**: its cite was empty and is not, by the rule whose id its cite carries:
  a line under a tag, or a cite in the tag style, which also gives the card the tag above it back and
  begins it there;
* **a card whose cite gains a line**: a later line of a cite;
* **a card that loses only white highlight**, the PM's ruling Q3. Formatting is compared as the
  characters each emphasis covers, so spans on either side of a white one that now join are no change;
* **a card whose heading path alone changed**, a card further down under a tag given back;
* **unchanged**.

Anything else is **another card that changed**, counted by the fields that changed. A card the store
holds that the new reading does not give back, and a new card the store does not hold, are counted.

The template family of each source is `scripts/survey_docx_styles.py`'s, read from its blob.

**Read-only, and nothing but counts leaves it** unless `--sample-out` is given. That writes the coach
sample of Q2 (c) under the data directory, never inside the repository: up to `--sample-size` lines
that a line-under-a-tag rule made a cite, at most one per file, drawn with `--seed`; each with the line,
the tag above it and the first 200 characters of the body below it, and a blank verdict column.

    uv run python scripts/diff_cite_lines_by_their_place.py --caselist hspf26
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sqlite3
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from survey_docx_styles import read_file_usage  # noqa: E402

from debate_core.application.ports.parsed_store import (  # noqa: E402
    DocumentRecord,
    parse_version_directory,
    source_object_key,
)
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin  # noqa: E402
from debate_core.domain.debate_files import ParsedCard, ParsedDocument  # noqa: E402
from debate_core.domain.file_provenance import formatting_sha256  # noqa: E402
from debate_core.domain.style_profile import RunEmphasis  # noqa: E402
from debate_core.integrations.docx_parser import DebateDocxParser  # noqa: E402
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY  # noqa: E402

__all__ = ["CASELISTS", "SHAPES", "Compared", "compare", "draw_sample", "main"]

CASELISTS = ("hsld26", "hspf26", "hspolicy26", "openev")

#: Each rule's id, by the shape the PM ruled it for.
SHAPES = {
    "assembly-cite-line-below-a-cite": "later line of a cite",
    "assembly-cite-line-below-a-tag": "line under a tag",
    "assembly-cite-in-the-tag-style-below-a-tag": "cite in the tag style",
}
LINE_UNDER_A_TAG = "assembly-cite-line-below-a-tag"

#: What a card that gains a cite, or a line of it, may change besides its cite.
_A_CITE_CHANGES = ("full_cite", "short_cite", "rule_ids", "confidence", "match_source")
#: And a card whose cite was in the tag style: it begins at the tag above it, which it takes back.
_A_TAG_STYLE_CITE_CHANGES = (*_A_CITE_CHANGES, "tag", "first_element_index", "section_path")

BODY_CHARACTERS = 200


@dataclass
class Compared:
    """One file's two readings, in counts, and the shape each changed card was changed by."""

    cards_gaining_a_cite: Counter[str] = field(default_factory=Counter[str])
    cards_whose_cite_gains_a_line: Counter[str] = field(default_factory=Counter[str])
    cards_losing_only_white_highlight: int = 0
    white_highlight_spans_removed: int = 0
    cards_changed_only_in_their_heading_path: int = 0
    other_cards_changed: Counter[str] = field(default_factory=Counter[str])
    """By the fields that changed, joined with `+`."""
    cards_the_store_holds_that_vanish: int = 0
    new_cards: int = 0
    cards_unchanged: int = 0
    gained_by_last_paragraph: dict[int, str] = field(default_factory=dict[int, str])
    """Each card that gained a cite, by its last paragraph, with its shape: for the index's documents."""


def _shape(card: ParsedCard) -> str | None:
    for rule_id in card.rule_ids:
        for prefix, shape in SHAPES.items():
            if rule_id.startswith(prefix + ":"):
                return shape
    return None


def _without_white(card: ParsedCard) -> tuple[ParsedCard, int]:
    spans = tuple(
        span
        for span in card.formatting_spans
        if not (span.emphasis is RunEmphasis.HIGHLIGHT and span.highlight_color == "white")
    )
    return card.model_copy(update={"formatting_spans": spans}), len(card.formatting_spans) - len(spans)


def _dumped(card: ParsedCard, *names: str) -> dict[str, Any]:
    """The card as JSON, its formatting as the characters each emphasis covers.

    Spans are compared as the writer's fidelity check compares them (`formatting_sha256`): when a
    white span between two underlines goes, the two join into one span over the same characters.
    """
    dumped = card.model_dump(mode="json")
    dumped["formatting"] = formatting_sha256(card.formatting_spans, card.font_size_spans)
    dumped.pop("formatting_spans")
    dumped.pop("font_size_spans")
    provenance = dict(dumped.pop("provenance"))
    # Where the file came from is the re-parse's record, not the parser's reading.
    for name in ("parser_version", "source_path", "camp", "snapshot"):
        provenance.pop(name, None)
    for name in names:
        dumped.pop(name, None)
        provenance.pop(name, None)
    return {**dumped, "provenance": provenance}


def _changed(before: ParsedCard, after: ParsedCard) -> list[str]:
    old, new = _dumped(before), _dumped(after)
    names = [name for name in old if name != "provenance" and old[name] != new[name]]
    names += [name for name in old["provenance"] if old["provenance"][name] != new["provenance"].get(name)]
    return sorted(names)


def compare(before: Sequence[ParsedCard], after: ParsedDocument) -> Compared:
    """The store's cards of one file against its new reading."""
    compared = Compared()
    stored = {card.provenance.last_element_index: card for card in before}
    seen: set[int] = set()
    for card in after.cards:
        last = card.provenance.last_element_index
        old = stored.get(last)
        if old is None:
            compared.new_cards += 1
            continue
        seen.add(last)
        old_without_white, removed = _without_white(old)
        compared.white_highlight_spans_removed += removed
        shape = _shape(card)
        gains = not old.full_cite.strip() and bool(card.full_cite.strip())
        grows = bool(old.full_cite.strip()) and len(card.full_cite) > len(old.full_cite)
        allowed = _A_TAG_STYLE_CITE_CHANGES if shape == "cite in the tag style" else _A_CITE_CHANGES
        if (
            shape is not None
            and (gains or grows)
            and _dumped(old_without_white, *allowed) == _dumped(card, *allowed)
        ):
            target = compared.cards_gaining_a_cite if gains else compared.cards_whose_cite_gains_a_line
            target[shape] += 1
            compared.gained_by_last_paragraph[last] = shape
            continue
        changed = _changed(old_without_white, card)
        if not changed:
            if removed:
                compared.cards_losing_only_white_highlight += 1
            else:
                compared.cards_unchanged += 1
        elif changed == ["section_path"]:
            compared.cards_changed_only_in_their_heading_path += 1
        else:
            compared.other_cards_changed["+".join(changed)] += 1
    compared.cards_the_store_holds_that_vanish = len(set(stored) - seen)
    return compared


# --------------------------------------------------------------------------------------------
# One source, in a worker
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Source:
    caselist: str
    sha256: str
    stored: Path
    blob: Path
    no_cite_documents: tuple[int, ...] = ()
    """The last paragraphs of the index's no-cite documents whose representative card is this file's."""
    sampling: bool = False


@dataclass(frozen=True, slots=True)
class _Result:
    family: str = ""
    read: bool = False
    without_a_blob: bool = False
    not_parsed: bool = False
    failed: bool = False
    """The comparison raised. Nothing of the error is kept: it could quote a stored field."""
    compared: Compared | None = None
    no_cite_documents_gaining_a_cite: tuple[str, ...] = ()
    """The shape each of the index's no-cite documents of this file gained its cite by."""
    sample_candidates: tuple[dict[str, str], ...] = ()


_PARSER: DebateDocxParser | None = None


def _candidates(document: ParsedDocument) -> tuple[dict[str, str], ...]:
    """The lines a line-under-a-tag rule made a cite: the line, its card's tag, and the body's opening."""
    found: list[dict[str, str]] = []
    for section in document.sections:
        if not section.match.rule_id.startswith(LINE_UNDER_A_TAG + ":"):
            continue
        index = section.element_index
        card = next(
            (
                c
                for c in document.cards
                if c.provenance.first_element_index <= index <= c.provenance.last_element_index
            ),
            None,
        )
        if card is None:
            continue
        found.append(
            {
                "line": section.text.strip(),
                "tag_above": (card.tag or "").strip(),
                "body_below": card.evidence_text[:BODY_CHARACTERS],
                "element_index": str(index),
            }
        )
    return tuple(found)


def _diff(source: _Source) -> _Result:
    try:
        return _diff_or_raise(source)
    except Exception:  # noqa: BLE001 - counted, never printed: a message could quote a stored field
        return _Result(read=True, failed=True)


def _diff_or_raise(source: _Source) -> _Result:
    global _PARSER  # noqa: PLW0603 - one parser per worker process
    lines = source.stored.read_text(encoding="utf-8").split("\n")
    if len(lines) < 2 or not lines[1].strip():
        return _Result()
    if not source.blob.is_file():
        return _Result(without_a_blob=True)
    family = read_file_usage(source.blob, source.caselist).template_family
    stored = DocumentRecord.model_validate_json(lines[1]).to_parsed_document("compared.docx").cards
    if _PARSER is None:
        _PARSER = DebateDocxParser()
    content = source.blob.read_bytes()
    snapshot = date(2026, 10, 27)
    record = SourceDocument(
        sha256=source.sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV if source.caselist == "openev" else SourceOrigin.CASELIST_ARCHIVE,
        caselist=None if source.caselist == "openev" else source.caselist,
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    after = _PARSER.parse(content, record, source_path="compared.docx")
    if not isinstance(after, ParsedDocument):
        return _Result(family=family, read=True, not_parsed=True)
    compared = compare(stored, after)
    return _Result(
        family=family,
        read=True,
        compared=compared,
        no_cite_documents_gaining_a_cite=tuple(
            compared.gained_by_last_paragraph[last]
            for last in source.no_cite_documents
            if last in compared.gained_by_last_paragraph
        ),
        sample_candidates=_candidates(after) if source.sampling else (),
    )


# --------------------------------------------------------------------------------------------
# A caselist
# --------------------------------------------------------------------------------------------


def _newest_version(parsed: Path, caselist: str) -> Path:
    versions = [path for path in (parsed / caselist).iterdir() if (path / "index.jsonl").is_file()]
    return max(versions, key=lambda path: parse_version_directory(path.name))


def no_cite_documents(index: Path) -> dict[tuple[str, str], tuple[int, ...]]:
    """The index's documents with no cite, as (caselist, source digest) → their cards' last paragraphs.

    Each document is its representative's card, the occurrence of ordinal 0. Read-only.
    """
    connection = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT d.caselist, o.source_sha256, o.last_element_index FROM documents d "
            "JOIN occurrences o ON o.doc_id = d.doc_id AND o.ordinal = 0 WHERE trim(d.cite) = ''"
        ).fetchall()
    finally:
        connection.close()
    found: dict[tuple[str, str], list[int]] = {}
    for caselist, digest, last in rows:
        found.setdefault((caselist, digest), []).append(last)
    return {key: tuple(lasts) for key, lasts in found.items()}


def _keyed(counter: Counter[str], families: Iterable[tuple[str, Counter[str]]]) -> dict[str, Any]:
    return {
        "all": dict(sorted(counter.items())),
        "by_family": {family: dict(sorted(one.items())) for family, one in sorted(families) if one},
    }


def diff_caselist(
    data_dir: Path,
    caselist: str,
    *,
    workers: int,
    index_documents: Mapping[tuple[str, str], tuple[int, ...]],
    sampling: bool,
    limit: int | None = None,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, str]]]]:
    """The counts for one caselist, and the sample's candidates by source digest."""
    started = time.monotonic()
    version = _newest_version(data_dir / "parsed", caselist)
    digests = sorted(
        record["source_sha256"]
        for line in (version / "index.jsonl").read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line)).get("outcome") == "PARSED"
    )[:limit]
    print(f"{caselist}: {len(digests):,} sources of {version.name}", file=sys.stderr, flush=True)
    sources = [
        _Source(
            caselist,
            digest,
            data_dir / "parsed" / source_object_key(caselist, version.name, digest),
            data_dir / BLOB_DIRECTORY / digest[:2] / digest[2:4] / digest,
            index_documents.get((caselist, digest), ()),
            sampling,
        )
        for digest in digests
    ]
    if workers <= 1:
        results = [_diff(source) for source in sources]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_diff, sources, chunksize=8))

    gaining: Counter[str] = Counter()
    growing: Counter[str] = Counter()
    gaining_by_family: dict[str, Counter[str]] = {}
    growing_by_family: dict[str, Counter[str]] = {}
    index_gaining: Counter[str] = Counter()
    index_gaining_by_family: dict[str, Counter[str]] = {}
    index_documents_by_family: Counter[str] = Counter()
    other: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    for source, result in zip(sources, results, strict=True):
        index_documents_by_family[result.family or "not read"] += len(source.no_cite_documents)
        one = result.compared
        if one is None:
            continue
        gaining += one.cards_gaining_a_cite
        growing += one.cards_whose_cite_gains_a_line
        gaining_by_family.setdefault(result.family, Counter())
        gaining_by_family[result.family] += one.cards_gaining_a_cite
        growing_by_family.setdefault(result.family, Counter())
        growing_by_family[result.family] += one.cards_whose_cite_gains_a_line
        index_gaining.update(result.no_cite_documents_gaining_a_cite)
        index_gaining_by_family.setdefault(result.family, Counter()).update(
            result.no_cite_documents_gaining_a_cite
        )
        other += one.other_cards_changed
        for name in (
            "cards_losing_only_white_highlight",
            "white_highlight_spans_removed",
            "cards_changed_only_in_their_heading_path",
            "cards_the_store_holds_that_vanish",
            "new_cards",
            "cards_unchanged",
        ):
            totals[name] += getattr(one, name)
    counts = {
        "version": version.name,
        "sources": len(digests),
        "sources_read": sum(result.read for result in results),
        "without_a_blob": sum(result.without_a_blob for result in results),
        "not_parsed": sum(result.not_parsed for result in results),
        "failed": sum(result.failed for result in results),
        "sources_by_family": dict(sorted(Counter(r.family for r in results if r.read).items())),
        "cards_gaining_a_cite": _keyed(gaining, gaining_by_family.items()),
        "cards_whose_cite_gains_a_line": _keyed(growing, growing_by_family.items()),
        **dict(sorted(totals.items())),
        "other_cards_changed": dict(sorted(other.items())),
        "index_no_cite_documents": sum(index_documents_by_family.values()),
        "index_no_cite_documents_by_family": dict(sorted(index_documents_by_family.items())),
        "index_no_cite_documents_gaining_a_cite": _keyed(index_gaining, index_gaining_by_family.items()),
        "seconds": round(time.monotonic() - started),
    }
    candidates = [
        (f"{caselist}/{source.sha256}", candidate)
        for source, result in zip(sources, results, strict=True)
        for candidate in result.sample_candidates
    ]
    return counts, candidates


# --------------------------------------------------------------------------------------------
# The coach sample
# --------------------------------------------------------------------------------------------


def draw_sample(
    candidates: Sequence[tuple[str, dict[str, str]]], *, seed: int, size: int
) -> list[tuple[str, dict[str, str]]]:
    """Up to `size` candidates, at most one per file, the same for the same seed and candidates."""
    by_file: dict[str, list[dict[str, str]]] = {}
    for file, candidate in candidates:
        by_file.setdefault(file, []).append(candidate)
    rng = random.Random(seed)
    files = sorted(by_file)
    rng.shuffle(files)
    drawn: list[tuple[str, dict[str, str]]] = []
    for file in files[:size]:
        options = sorted(by_file[file], key=lambda candidate: int(candidate["element_index"]))
        drawn.append((file, rng.choice(options)))
    return drawn


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def write_sample(drawn: Sequence[tuple[str, dict[str, str]]], out: Path) -> None:
    """The coach's CSV, and beside it the key that says where each row came from."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_row", "line", "tag_above", "body_below_first_200", "verdict"])
        for row, (_, candidate) in enumerate(drawn, start=1):
            writer.writerow([row, candidate["line"], candidate["tag_above"], candidate["body_below"], ""])
    key = out.with_suffix(".key.jsonl")
    key.write_text(
        "".join(
            json.dumps({"sample_row": row, "source": file, "element_index": int(candidate["element_index"])})
            + "\n"
            for row, (file, candidate) in enumerate(drawn, start=1)
        ),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".debate-research" / "dev")
    parser.add_argument(
        "--caselist", action="append", help=f"Repeat for several. Default: {', '.join(CASELISTS)}."
    )
    parser.add_argument(
        "--index",
        type=Path,
        help="The search-index.sqlite whose no-cite documents are followed, opened read-only.",
    )
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--limit", type=int, help="Only the first N sources of each caselist, to time a run.")
    parser.add_argument(
        "--sample-out", type=Path, help="Write the coach sample here: under the data directory."
    )
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument("--sample-size", type=int, default=20)
    arguments = parser.parse_args(argv)
    if arguments.sample_out is not None and (
        _inside(arguments.sample_out, REPO_ROOT) or not _inside(arguments.sample_out, arguments.data_dir)
    ):
        print(
            "--sample-out must be under the data directory, and never inside the repository", file=sys.stderr
        )
        return 2
    started = time.monotonic()
    index_documents = no_cite_documents(arguments.index) if arguments.index is not None else {}
    results: dict[str, Any] = {}
    candidates: list[tuple[str, dict[str, str]]] = []
    for caselist in arguments.caselist or CASELISTS:
        results[caselist], found = diff_caselist(
            arguments.data_dir,
            caselist,
            workers=arguments.workers,
            index_documents=index_documents,
            sampling=arguments.sample_out is not None,
            limit=arguments.limit,
        )
        candidates += found
    output: dict[str, Any] = {"caselists": results, "seconds": round(time.monotonic() - started)}
    if arguments.sample_out is not None:
        drawn = draw_sample(candidates, seed=arguments.seed, size=arguments.sample_size)
        write_sample(drawn, arguments.sample_out)
        output["sample"] = {
            "candidates": len(candidates),
            "files_with_a_candidate": len({file for file, _ in candidates}),
            "rows_written": len(drawn),
            "seed": arguments.seed,
        }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

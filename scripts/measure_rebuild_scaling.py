#!/usr/bin/env python3
"""How the aggregate rebuild scales, and where its time goes (`v1-e31-t10`, Goal criterion ac1).

Two modes, both printing one JSON line of counts, seconds and shares, and nothing else: never a word
of a card, a tag, a cite, a path, a school or a team.

* **`synthetic --sources N [N ...]`** builds a synthetic store of invented words for each size in a
  temporary directory and times its rebuild. Cards are passages of invented articles, drawn by
  preferential attachment so that popular cards recur and distinct bodies grow more slowly than
  sources; a drawn card is an exact copy, a copy with a word changed, a cut, a longer extent of the
  article, an abbreviated disclosure or a cite-only entry.
* **`real --data-dir DIR --caselist SLUG`** times the rebuild of a caselist's current version
  directory in an existing store, **read-only**: the aggregates it makes are rendered to a SHA-256 in
  memory and never written, and nothing else is written either. The JSON says whether that digest is
  the store's own `occurrences.jsonl`'s, which is a check that the measured rebuild is the one the
  store was built by.

Both time the rebuild by phase, by wrapping each step of the placer and the clusterer: reading the
documents, fingerprints, body words, `CutIndex`, MinHash, band pairs and Jaccard, the joins of copies,
the cut step, linking, and writing. With `--components` (always on in `real`) they also count the
dependency components of the clusterer: the bodies a week of new sources reaches through a band pair
with Jaccard at the threshold, a confirmed containment, or (for a short body) a body holding both its
ends, which is what an incremental placement would have to re-cluster. The week is the sources first
disclosed in the newest snapshot, and separately the last `--new-share` of sources by first snapshot.
Each is counted with every too-common edge kept, and with the edges of a short body whose both-end
holders span ten or more components dropped.
"""

from __future__ import annotations

import argparse
import asyncio
import bisect
import contextlib
import functools
import hashlib
import itertools
import json
import random
import resource
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import debate_core.application.caselist_card_stats as card_stats
import debate_core.evidence.near_duplicates as near
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources, live_disclosures
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList, load_suppression_state
from debate_core.application.caselist_card_stats import CardPlacer
from debate_core.application.caselist_parse import CaselistParseService, ParsePlan
from debate_core.application.ports.parsed_store import (
    OCCURRENCES_NAME,
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    parse_version_directory,
)
from debate_core.domain.caselist import SnapshotDate, SourceDocument, SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FormattingSpan,
    ParsedCard,
    ParsedDocument,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.evidence.abbreviated_links import default_ellipsis_markers
from debate_core.evidence.near_duplicates import NearDuplicateThresholds
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

#: A short body whose both-end holders span at least this many components is too common whatever
#: happens inside them: clusters never cross components, and `too_common` needs more than eight.
SATURATED_COMPONENTS = near.MAX_CONTAINER_CLUSTERS + 2

SYNTHETIC_CASELIST = "synthcl26"
SYNTHETIC_PARSER_VERSION = "2031.01.01-synthetic-1"
SYNTHETIC_PROFILE_VERSION = "synthetic-profile-1"
SYNTHETIC_WEEKS = 12
SYNTHETIC_SEED = 20261106


# ------------------------------------------------------------------------------------------------
# Timing the phases
# ------------------------------------------------------------------------------------------------


class PhaseClock:
    """Wraps the rebuild's steps while it is entered, and adds up each one's seconds and calls."""

    def __init__(self) -> None:
        self.seconds: Counter[str] = Counter()
        self.calls: Counter[str] = Counter()
        self._restore: list[tuple[object, str, object]] = []

    def _wrap(self, owner: object, name: str, phase: str) -> None:
        original = getattr(owner, name)
        clock = self

        if asyncio.iscoroutinefunction(original):

            @functools.wraps(original)
            async def timed_async(*args: Any, **kwargs: Any) -> Any:
                started = time.perf_counter()
                try:
                    return await original(*args, **kwargs)
                finally:
                    clock.seconds[phase] += time.perf_counter() - started
                    clock.calls[phase] += 1

            setattr(owner, name, timed_async)
        else:

            @functools.wraps(original)
            def timed(*args: Any, **kwargs: Any) -> Any:
                started = time.perf_counter()
                try:
                    return original(*args, **kwargs)
                finally:
                    clock.seconds[phase] += time.perf_counter() - started
                    clock.calls[phase] += 1

            setattr(owner, name, timed)
        self._restore.append((owner, name, original))

    def __enter__(self) -> PhaseClock:
        self._wrap(LocalParsedStore, "read_document", "read_document")
        self._wrap(DocumentRecord, "to_parsed_document", "to_parsed")
        self._wrap(CardPlacer, "add", "placer_add")
        self._wrap(CardPlacer, "placements", "placements")
        self._wrap(near.BodyWords, "__init__", "body_words")
        self._wrap(near.CutIndex, "__init__", "cut_index")
        self._wrap(near.CutIndex, "shingle_texts", "shingle_texts")
        self._wrap(near.CutIndex, "copies", "copies_pairs")
        self._wrap(near, "minhash_signature", "minhash")
        self._wrap(near, "_join_copies", "join_copies")
        self._wrap(near, "_join_cuts_to_their_one_container", "cut_step")
        self._wrap(card_stats, "cluster_near_duplicates", "cluster_total")
        return self

    def __exit__(self, *_: object) -> None:
        for owner, name, original in reversed(self._restore):
            setattr(owner, name, original)
        self._restore.clear()

    def phases(self, total: float, write: float) -> dict[str, float]:
        """The rebuild's seconds by phase; `order_and_rest` is what no wrapped step accounts for."""
        s = self.seconds
        clustered = sum(
            s[name]
            for name in ("cut_index", "minhash", "shingle_texts", "join_copies", "copies_pairs", "cut_step")
        )
        phases = {
            "read_documents": s["read_document"] + s["to_parsed"],
            "fingerprints": s["placer_add"],
            "body_words": s["body_words"],
            "cut_index": s["cut_index"],
            "minhash": s["minhash"] + s["shingle_texts"],
            "band_pairs_and_jaccard": s["cluster_total"] - clustered,
            "joins_of_copies": s["join_copies"] + s["copies_pairs"],
            "cut_step": s["cut_step"],
            "linking": s["placements"] - s["body_words"] - s["cluster_total"],
            "writing": write,
        }
        phases["plan_ordering_and_rest"] = total - sum(phases.values())
        return {name: round(seconds, 2) for name, seconds in phases.items()}


@dataclass
class Captured:
    """What the components count needs from one rebuild, kept from it rather than computed again."""

    index: near.CutIndex | None = None
    signatures: list[tuple[int, ...]] = field(default_factory=list[tuple[int, ...]])
    holders: defaultdict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    """Each distinct full body's fingerprint, to the sources holding it."""


class RecordingPlacer(CardPlacer):
    """The rebuild's own placer, noting which sources hold each full body."""

    def __init__(
        self, captured: Captured, thresholds: NearDuplicateThresholds, markers: tuple[str, ...]
    ) -> None:
        super().__init__(thresholds, markers)
        self._captured = captured

    def add(self, card: ParsedCard) -> None:
        super().add(card)
        if card.completeness is CardCompleteness.FULL:
            self._captured.holders[self._fingerprints[-1]].add(card.provenance.source_sha256)


@contextlib.contextmanager
def capturing(captured: Captured) -> Iterator[None]:
    """Keep the rebuild's `CutIndex` and its MinHash signatures, in the order they were made."""
    original_init = near.CutIndex.__init__
    original_minhash = near.minhash_signature

    def init(self: near.CutIndex, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        captured.index = self

    def minhash(*args: Any, **kwargs: Any) -> tuple[int, ...]:
        signature = original_minhash(*args, **kwargs)
        captured.signatures.append(signature)
        return signature

    near.CutIndex.__init__ = init  # type: ignore[method-assign]
    near.minhash_signature = minhash
    try:
        yield
    finally:
        near.CutIndex.__init__ = original_init  # type: ignore[method-assign]
        near.minhash_signature = original_minhash


# ------------------------------------------------------------------------------------------------
# A store the rebuild reads and never writes
# ------------------------------------------------------------------------------------------------


class ReadOnlyParsedStore(LocalParsedStore):
    """Reads as the local store does. The aggregates are rendered to a digest and dropped."""

    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir)
        self.occurrences_sha256: str | None = None
        self.rows = 0
        self.writing_seconds = 0.0

    async def write_source(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("the measurement writes no per-source file")

    async def write_aggregates(
        self,
        caselist: str,
        version: str,
        *,
        index: Sequence[SourceEntry],
        failures: Sequence[SourceEntry],
        occurrences: Iterable[OccurrenceRecord],
    ) -> None:
        started = time.perf_counter()
        digest = hashlib.sha256()
        for row in occurrences:
            digest.update(f"{_render(row)}\n".encode())
            self.rows += 1
        for record in (*index, *failures):
            _render(record)
        self.occurrences_sha256 = digest.hexdigest()
        self.writing_seconds += time.perf_counter() - started


def _render(record: OccurrenceRecord | SourceEntry) -> str:
    """A line as the local store writes it."""
    return json.dumps(
        record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


@dataclass(frozen=True)
class _Versions:
    """The parser the service is built with: its versions alone. Nothing is parsed."""

    parser_version: str
    profile_version: str

    def parse(self, *args: object, **kwargs: object) -> ParsedDocument:
        raise RuntimeError("the measurement parses nothing")


# ------------------------------------------------------------------------------------------------
# The rebuild, timed
# ------------------------------------------------------------------------------------------------


async def timed_rebuild(
    data_dir: Path,
    caselist: str,
    version: str | None,
    *,
    markers: tuple[str, ...],
    captured: Captured | None,
) -> dict[str, Any]:
    """Rebuild `caselist`'s version directory read-only, by phase. `captured`, if given, is filled."""
    store = ReadOnlyParsedStore(data_dir)
    names = await store.version_directories(caselist)
    if not names:
        raise SystemExit(f"no parsed version directory for {caselist}")
    chosen = version or max(names, key=parse_version_directory)
    entries = await store.read_entries(caselist, chosen)
    if not entries:
        raise SystemExit(f"{caselist}/{chosen} holds no source")
    parser_version, profile_version = Counter(
        (entry.parser_version, entry.profile_version) for entry in entries
    ).most_common(1)[0][0]
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )
    suppression = RecordedSuppressionList(local_suppression_list_file(data_dir))
    sources = await enumerate_sources(local, caselist)
    state = await load_suppression_state(suppression)
    plan = ParsePlan(
        caselist=caselist,
        version=chosen,
        new_version=False,
        superseded=None,
        parser_version=parser_version,
        profile_version=profile_version,
        snapshot=None,
        reparse=False,
        sources=sources,
        in_scope=len(sources),
        suppressed=0,
        to_parse=(),
        suppression=state,
    )
    thresholds = NearDuplicateThresholds()
    holding = captured or Captured()
    service = CaselistParseService(
        local=local,
        store=store,
        parser=_Versions(parser_version, profile_version),
        runner=InProcessParseRunner(),
        suppression=suppression,
        card_placer=lambda: RecordingPlacer(holding, thresholds, markers),
        failure_rate_threshold=1.0,
        failure_rate_minimum_sources=1,
    )
    clock = PhaseClock()
    with capturing(holding) if captured is not None else contextlib.nullcontext(), clock:
        started = time.perf_counter()
        totals = await service._rebuild(plan)  # noqa: SLF001 - the rebuild alone, as a second run times it
        total = time.perf_counter() - started
    table = data_dir / "parsed" / caselist / chosen / OCCURRENCES_NAME
    stored = hashlib.sha256(table.read_bytes()).hexdigest() if table.is_file() else None
    words = 0
    if holding.index is not None:
        words = sum(len(holding.index.words[fingerprint]) for fingerprint in holding.index.fingerprints)
    return {
        "caselist": caselist,
        "version": chosen,
        "sources": totals.sources,
        "parsed": totals.parsed,
        "cards": totals.cards,
        "occurrences": totals.occurrences,
        "clusters": totals.clusters,
        "distinct_full_bodies": len(holding.holders),
        "distinct_full_body_words": words,
        "rebuild_seconds": round(total, 2),
        "phases_seconds": clock.phases(total, store.writing_seconds),
        "table_equals_the_stores": stored == store.occurrences_sha256 if stored is not None else None,
        "_plan": plan,
    }


# ------------------------------------------------------------------------------------------------
# The dependency components
# ------------------------------------------------------------------------------------------------


class _Union:
    def __init__(self, members: Iterable[str]) -> None:
        self.parent = {member: member for member in members}

    def find(self, member: str) -> str:
        root = member
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[member] != root:
            self.parent[member], member = root, self.parent[member]
        return root

    def join(self, left: str, right: str) -> None:
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


@dataclass(frozen=True)
class DependencyEdges:
    """The clusterer's dependencies between distinct full bodies, from one rebuild's index."""

    joining: frozenset[tuple[str, str]]
    """Band pairs with Jaccard at the threshold, and confirmed containments: what clusters form along."""
    both_ends: dict[str, tuple[str, ...]]
    """For each short body, the bodies holding both its ends: what its too-common count reads."""


def dependency_edges(captured: Captured) -> DependencyEdges:
    index = captured.index
    if index is None:
        raise SystemExit("the rebuild clustered no body")
    signed = [fingerprint for fingerprint in index.fingerprints if index.size(fingerprint)]
    if len(signed) != len(captured.signatures):
        raise SystemExit("the signatures kept do not match the bodies signed")
    buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)
    for fingerprint, signature in zip(signed, captured.signatures, strict=True):
        for band in range(near.LSH_BANDS):
            rows = signature[band * near.LSH_ROWS_PER_BAND : (band + 1) * near.LSH_ROWS_PER_BAND]
            buckets[(band, rows)].append(fingerprint)
    pairs = {
        (min(left, right), max(left, right))
        for members in buckets.values()
        for position, left in enumerate(members)
        for right in members[position + 1 :]
    }
    joining = {
        pair
        for pair in pairs
        if near.jaccard(index.sets[pair[0]], index.sets[pair[1]]) >= index.limits.jaccard
    }
    both_ends: dict[str, tuple[str, ...]] = {}
    for cut in index.fingerprints:
        for holder in index.candidates(cut):
            if index.holds(holder, cut):
                joining.add((min(cut, holder), max(cut, holder)))
        if index.size(cut) < near.SHORT_BODY_SHINGLES and index.holding_both_ends(cut):
            both_ends[cut] = tuple(index.holding_both_ends(cut))
    return DependencyEdges(frozenset(joining), both_ends)


def components(edges: DependencyEdges, members: set[str], *, bound_stock_phrases: bool) -> _Union:
    """The components of `members`; with `bound_stock_phrases`, a saturated short body's too-common
    edges dropped."""
    joined = _Union(members)
    for left, right in edges.joining:
        if left in members and right in members:
            joined.join(left, right)
    found = _Union(members)
    found.parent = dict(joined.parent)
    for cut, holders in edges.both_ends.items():
        if cut not in members:
            continue
        present = [holder for holder in holders if holder in members]
        if bound_stock_phrases and len({joined.find(holder) for holder in present}) >= SATURATED_COMPONENTS:
            continue
        for holder in present:
            found.join(cut, holder)
    return found


def reached(
    edges: DependencyEdges, bodies: set[str], new: set[str], *, bound_stock_phrases: bool
) -> dict[str, Any]:
    """What an incremental placement would re-cluster for a week whose new bodies are `new`."""
    old = bodies - new
    before = components(edges, old, bound_stock_phrases=bound_stock_phrases)
    after = components(edges, bodies, bound_stock_phrases=bound_stock_phrases)
    sizes = Counter(before.find(body) for body in old)
    with_new = {after.find(body) for body in new}
    touched = {before.find(body) for body in old if after.find(body) in with_new}
    for cut, holders in edges.both_ends.items():
        if cut in old and any(holder in new for holder in holders):
            touched.add(before.find(cut))
    count = len(new) + sum(sizes[root] for root in touched)
    return {
        "stored_components": len(sizes),
        "largest_stored_components": [size for _, size in sizes.most_common(3)],
        "components_reached": len(touched),
        "bodies_to_recluster": count,
        "share_of_bodies_to_recluster": round(count / len(bodies), 4) if bodies else 0.0,
    }


def first_disclosed(plan: ParsePlan) -> dict[str, str]:
    """Each live source's first snapshot."""
    firsts: dict[str, str] = {}
    for source in plan.sources:
        live = live_disclosures(source, plan.suppression)
        if live:
            firsts[source.sha256] = min(disclosed.snapshot for disclosed in live)
    return firsts


def component_counts(captured: Captured, plan: ParsePlan, new_share: float) -> dict[str, Any]:
    started = time.perf_counter()
    edges = dependency_edges(captured)
    bodies = set(captured.holders)
    firsts = first_disclosed(plan)
    ordered = sorted(firsts, key=lambda sha: (firsts[sha], sha))
    newest = max(firsts.values()) if firsts else None
    weeks = {
        "newest_snapshot": {sha for sha, snapshot in firsts.items() if snapshot == newest},
        "last_share": set(ordered[int(len(ordered) * (1 - new_share)) :]),
    }
    result: dict[str, Any] = {
        "joining_edges": len(edges.joining),
        "short_bodies_with_both_end_holders": len(edges.both_ends),
    }
    for name, new_sources in weeks.items():
        new = {body for body, holders in captured.holders.items() if holders <= new_sources}
        result[name] = {
            "new_sources": len(new_sources),
            "new_bodies": len(new),
            "every_too_common_edge": reached(edges, bodies, new, bound_stock_phrases=False),
            "stock_phrases_bounded": reached(edges, bodies, new, bound_stock_phrases=True),
        }
    result["last_share"]["share"] = new_share
    result["seconds"] = round(time.perf_counter() - started, 2)
    return result


# ------------------------------------------------------------------------------------------------
# Synthetic stores
# ------------------------------------------------------------------------------------------------

_SYLLABLES = [
    onset + rest for onset in "bdfgklmnprstvz" for rest in ("a", "e", "i", "o", "u", "ar", "en", "ol")
]


@dataclass
class _Card:
    element: int
    text: str
    completeness: CardCompleteness
    short_cite: str


class SyntheticCorpus:
    """Invented articles; cards are passages of them, drawn by preferential attachment."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        words: set[str] = set()
        while len(words) < 6000:
            words.add("".join(self.rng.choice(_SYLLABLES) for _ in range(self.rng.choice((2, 2, 3, 3, 4)))))
        self.words = sorted(words)
        self.cumulative = list(
            itertools.accumulate(1.0 / (rank + 1) ** 1.05 for rank in range(len(self.words)))
        )
        self.articles: list[tuple[list[str], str]] = []
        self.passages: list[tuple[int, int, int]] = []
        self.draws: list[int] = []

    def _text(self, length: int) -> list[str]:
        total = self.cumulative[-1]
        return [
            self.words[bisect.bisect_left(self.cumulative, self.rng.random() * total)] for _ in range(length)
        ]

    def _new_passage(self) -> int:
        if self.articles and self.rng.random() < 0.4:
            article = self.rng.randrange(len(self.articles))
        else:
            author = self._text(1)[0].capitalize()
            year = self.rng.choice((24, 25, 26))
            self.articles.append((self._text(self.rng.randint(400, 1600)), f"{author} {year}"))
            article = len(self.articles) - 1
        words, _ = self.articles[article]
        length = self.rng.randint(25, 60) if self.rng.random() < 0.15 else self.rng.randint(80, 700)
        length = min(length, len(words))
        start = self.rng.randint(0, len(words) - length)
        self.passages.append((article, start, length))
        return len(self.passages) - 1

    def draw(self) -> int:
        new_rate = min(0.7, 0.7 * (max(len(self.draws), 1) / 2000) ** -0.37)
        passage = (
            self.rng.choice(self.draws)
            if self.draws and self.rng.random() >= new_rate
            else self._new_passage()
        )
        self.draws.append(passage)
        return passage

    def card(self, passage: int, element: int) -> _Card:
        article, start, length = self.passages[passage]
        words, short_cite = self.articles[article]
        kept = words[start : start + length]
        roll = self.rng.random()
        if roll < 0.72:
            return _Card(element, " ".join(kept) + ".", CardCompleteness.FULL, short_cite)
        if roll < 0.80 and length > 12:
            changed = list(kept)
            changed[self.rng.randrange(6, length - 6)] = self.rng.choice(self.words)
            return _Card(element, " ".join(changed) + ".", CardCompleteness.FULL, short_cite)
        if roll < 0.88 and length > 30:
            keep = self.rng.randint(max(20, length // 5), length - 5)
            offset = self.rng.randint(0, length - keep)
            return _Card(
                element, " ".join(kept[offset : offset + keep]) + ".", CardCompleteness.FULL, short_cite
            )
        if roll < 0.92:
            first = max(0, start - self.rng.randint(0, 60))
            last = min(len(words), start + length + self.rng.randint(0, 60))
            return _Card(element, " ".join(words[first:last]) + ".", CardCompleteness.FULL, short_cite)
        if roll < 0.97:
            opening, closing = self.rng.randint(3, 8), self.rng.randint(3, 8)
            text = f"{' '.join(kept[:opening])} … {' '.join(kept[-closing:])}"
            return _Card(element, text, CardCompleteness.ABBREVIATED, short_cite)
        return _Card(element, "", CardCompleteness.CITE_ONLY, short_cite)


def _spans(text: str) -> tuple[FormattingSpan, ...]:
    """Underline and highlight stretches, about one every twelve words, as real cards carry."""
    spans: list[FormattingSpan] = []
    for number, start in enumerate(range(0, max(len(text) - 30, 0), 70)):
        spans.append(
            FormattingSpan(
                emphasis=RunEmphasis.UNDERLINE,
                start_offset=start,
                end_offset=start + 30,
                rule_id="synthetic-underline",
                match_source=StyleMatchSource.VERBATIM,
            )
        )
        if number % 2 == 0:
            spans.append(
                FormattingSpan(
                    emphasis=RunEmphasis.HIGHLIGHT,
                    highlight_color="cyan",
                    start_offset=start + 5,
                    end_offset=start + 25,
                    rule_id="synthetic-highlight",
                    match_source=StyleMatchSource.VERBATIM,
                )
            )
    return tuple(spans)


class _SyntheticParser:
    parser_version = SYNTHETIC_PARSER_VERSION
    profile_version = SYNTHETIC_PROFILE_VERSION

    def __init__(self, documents: dict[str, list[_Card]]) -> None:
        self.documents = documents

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument:
        assert snapshot is not None
        return ParsedDocument(
            source_sha256=source.sha256,
            source_path=source_path,
            parser_version=SYNTHETIC_PARSER_VERSION,
            profile_version=SYNTHETIC_PROFILE_VERSION,
            cards=tuple(
                ParsedCard(
                    tag="An invented claim",
                    short_cite=card.short_cite,
                    full_cite=f"{card.short_cite} (Invented Author, Fictional Quarterly)",
                    evidence_text=card.text,
                    completeness=card.completeness,
                    formatting_spans=_spans(card.text),
                    match_source=StyleMatchSource.VERBATIM,
                    confidence=1.0,
                    provenance=FileImportProvenance(
                        source_sha256=source.sha256,
                        source_path=source_path,
                        origin=SourceOrigin.CASELIST_ARCHIVE,
                        caselist=SYNTHETIC_CASELIST,
                        snapshot=snapshot,
                        first_element_index=card.element,
                        last_element_index=card.element + 2,
                        parser_version=SYNTHETIC_PARSER_VERSION,
                        profile_version=SYNTHETIC_PROFILE_VERSION,
                    ),
                )
                for card in self.documents[source.sha256]
            ),
        )


async def build_synthetic_store(data_dir: Path, sources: int, seed: int, *, aggregates: bool = False) -> None:
    """A parsed synthetic store of `sources` sources over twelve weeks; with `aggregates`, rebuilt."""
    corpus = SyntheticCorpus(seed)
    documents: dict[str, list[_Card]] = {}
    manifests: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    first = date(2026, 8, 4)
    weeks = [(first + timedelta(days=7 * week)).isoformat() for week in range(SYNTHETIC_WEEKS)]
    per_week = -(-sources // SYNTHETIC_WEEKS)
    for number in range(sources):
        week = number // per_week
        content = f"synthetic source {seed}-{number}".encode()
        sha = hashlib.sha256(content).hexdigest()
        blob = data_dir / "blobs" / "sha256" / sha[0:2] / sha[2:4] / sha
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(content)
        documents[sha] = [corpus.card(corpus.draw(), 3 * k) for k in range(corpus.rng.randint(12, 32))]
        path = f"Invented School/Team {number}/round-{number}.docx"
        listed = [(weeks[week], path)]
        if week + 1 < SYNTHETIC_WEEKS and corpus.rng.random() < 0.10:
            listed.append((weeks[week + 1], path))
        if corpus.rng.random() < 0.03:
            listed.append((weeks[week], f"Invented School/Team {number}b/copy-{number}.docx"))
        for snapshot, at in listed:
            manifests[snapshot].append(
                {
                    "kind": "member",
                    "classification": "NEW",
                    "path": at,
                    "sha256": sha,
                    "byte_size": len(content),
                    "format": "DOCX",
                }
            )
    for snapshot, rows in manifests.items():
        manifest = data_dir / "objects" / "manifests" / SYNTHETIC_CASELIST / f"{snapshot}.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    service = CaselistParseService(
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        store=LocalParsedStore(data_dir),
        parser=_SyntheticParser(documents),
        runner=InProcessParseRunner(),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        card_placer=lambda: CardPlacer(NearDuplicateThresholds(), SYNTHETIC_MARKERS),
        failure_rate_threshold=1.0,
        failure_rate_minimum_sources=1,
    )

    if not aggregates:

        async def parse_only(plan: ParsePlan) -> None:
            return None

        service._rebuild = parse_only  # type: ignore[method-assign]  # noqa: SLF001 - the rebuild is what is timed after

    await service.run(await service.plan(SYNTHETIC_CASELIST))


SYNTHETIC_MARKERS = ("…",)


# ------------------------------------------------------------------------------------------------
# The command
# ------------------------------------------------------------------------------------------------


async def measure(
    data_dir: Path,
    caselist: str,
    version: str | None,
    *,
    markers: tuple[str, ...],
    with_components: bool,
    new_share: float,
) -> dict[str, Any]:
    captured = Captured() if with_components else None
    result = await timed_rebuild(data_dir, caselist, version, markers=markers, captured=captured)
    plan: ParsePlan = result.pop("_plan")
    if captured is not None:
        print(json.dumps({"rebuild_seconds": result["rebuild_seconds"]}), file=sys.stderr, flush=True)
        result["components"] = component_counts(captured, plan, new_share)
    result["peak_resident_bytes"] = _peak_resident_bytes()
    return result


def _peak_resident_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    modes = parser.add_subparsers(dest="mode", required=True)
    synthetic = modes.add_parser("synthetic", help="Time the rebuild of synthetic stores of the given sizes.")
    synthetic.add_argument("--sources", type=int, nargs="+", required=True)
    synthetic.add_argument("--seed", type=int, default=SYNTHETIC_SEED)
    synthetic.add_argument("--components", action="store_true", help="Count the dependency components too.")
    synthetic.add_argument("--new-share", type=float, default=0.05)
    real = modes.add_parser("real", help="Time a store's rebuild read-only, and count its components.")
    real.add_argument("--data-dir", type=Path, required=True)
    real.add_argument("--caselist", required=True)
    real.add_argument("--version", default=None, help="Default: the newest version directory.")
    real.add_argument("--new-share", type=float, default=0.05)
    arguments = parser.parse_args(argv)

    if arguments.mode == "real":
        data_dir = arguments.data_dir.expanduser()
        result = asyncio.run(
            measure(
                data_dir,
                arguments.caselist,
                arguments.version,
                markers=default_ellipsis_markers(),
                with_components=True,
                new_share=arguments.new_share,
            )
        )
        print(json.dumps(result))
        return 0
    for size in arguments.sources:
        with tempfile.TemporaryDirectory(prefix="rebuild-scaling-") as scratch:
            data_dir = Path(scratch)
            asyncio.run(build_synthetic_store(data_dir, size, arguments.seed))
            result = asyncio.run(
                measure(
                    data_dir,
                    SYNTHETIC_CASELIST,
                    None,
                    markers=SYNTHETIC_MARKERS,
                    with_components=arguments.components,
                    new_share=arguments.new_share,
                )
            )
        print(json.dumps({"seed": arguments.seed, **result}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The aggregate rebuild reads cards source by source (`v1-e40-t36`).

Until this task the rebuild read every parsed card of a caselist into one list before placing any,
about 1.3 GB of the main process for 250 `hspolicy26` sources (`docs/data/caselist-parse-memory.md`).
What each test below holds the rebuild to:

* **It keeps no source's cards once it has read the next.** When the placer is asked to place, none
  of the store's cards is alive but the one last read (a counting stand-in over the garbage
  collector's objects), and the rebuild's traced peak, for four times the sources, grows by less
  than a quarter of the extra sources' card bodies (`tracemalloc`). The rebuild before this task
  held every card at that moment and fails both.
* **It writes the same bytes.** `index.jsonl`, `failures.jsonl`, `occurrences.jsonl` and
  `camp_paths.jsonl` are byte for byte what the rebuild before this task wrote over the same store:
  sources that share cards and clusters, a disclosure in three snapshots, cards out of paragraph order
  in their document, a failed and an unsupported source, a stopped disclosure and a stopped source,
  camp files at two paths of one release, a withdrawn camp path, and generated stores. That rebuild
  is kept below as the oracle, copied from `caselist_parse.py` and `caselist_card_stats.py` at the
  commit this task started from (`61d3191`), with only its names changed. It is the old code, not
  the code under test, so it can disagree with it (working agreement 6).
* **The placer places as the one list did**, on generated lists of cards (Hypothesis).

Every source here is synthetic: invented words, invented paths, no real file's text or name.
"""

from __future__ import annotations

import gc
import hashlib
import json
import random
import tracemalloc
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import (
    DisclosureKey,
    EnumeratedSource,
    camp_path_digests,
    disclosure_key,
    is_aggregated,
    live_disclosures,
)
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService, ClusterPlacement
from debate_core.application.caselist_parse import CaselistParseService, ParsePlan, PlacesCards
from debate_core.application.ports.parsed_store import (
    CAMP_PATHS_NAME,
    FAILURES_NAME,
    INDEX_NAME,
    OCCURRENCES_NAME,
    CampPathRecord,
    OccurrenceRecord,
    SourceOutcome,
    StoreRecord,
)
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionState,
    camp_path_disclosure,
    disclosure_digest,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import SnapshotDate, SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FormattingSpan,
    ParsedCard,
    ParsedDocument,
    ParseFailure,
    ParseFailureReason,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.evidence.abbreviated_links import (
    AbbreviationAnchor,
    FullCardWords,
    abbreviation_anchor,
    group_unmatched_abbreviations,
    link_abbreviated,
    matching_full_cards,
    short_cite_key,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.evidence.near_duplicates import (
    NearDuplicateThresholds,
    cluster_near_duplicates,
    matching_words,
)
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.caselist import build_fake_caselist_repository

pytestmark = pytest.mark.anyio

CASELIST: Final = "synthcl26"
OPENEV: Final = "openev"
PARSER_VERSION: Final = "2031.01.01-synthetic-1"
PROFILE_VERSION: Final = "synthetic-profile-1"
MARKERS: Final = ("…",)
WEEKS: Final = ("2026-09-01", "2026-09-08", "2026-09-15", "2026-09-22")
AGGREGATES: Final = (INDEX_NAME, FAILURES_NAME, OCCURRENCES_NAME, CAMP_PATHS_NAME)

#: Invented words, so no body here is anyone's evidence.
VOCABULARY: Final = [
    "lantern",
    "quiver",
    "marrow",
    "tessel",
    "orvane",
    "plinth",
    "caddow",
    "ferrule",
    "wimble",
    "sorrel",
    "brindle",
    "quorl",
    "hessian",
    "tamber",
    "vellum",
    "ostrich",
    "pellow",
    "carrack",
    "drumlin",
    "fescue",
    "gannet",
    "harl",
    "isthmus",
    "jorum",
    "kestrel",
    "lodestar",
    "mizzen",
    "nacre",
    "oriel",
    "parapet",
    "quillon",
    "rasp",
    "scutter",
    "tallow",
    "umber",
    "vane",
    "wether",
    "yarrow",
    "zephyr",
    "argent",
    "bastion",
    "corbel",
    "dirk",
    "eyot",
    "fathom",
    "gimbal",
    "halyard",
    "ingle",
    "jib",
    "keel",
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def body(seed: int, words: int = 60) -> str:
    """A synthetic card body: `words` invented words, the same for the same seed."""
    chosen = random.Random(seed)
    return " ".join(chosen.choice(VOCABULARY) for _ in range(words)) + "."


def near_copy(text: str) -> str:
    """`text` with its middle word changed: the near duplicate a copy with a typo is."""
    words = text.split(" ")
    middle = len(words) // 2
    words[middle] = "gallimaufry" if words[middle] != "gallimaufry" else "hobbledehoy"
    return " ".join(words)


def cut(text: str, opening: int = 6, closing: int = 6) -> str:
    """An abbreviated card of `text`: its first and last words around an ellipsis marker."""
    words = text.split(" ")
    return f"{' '.join(words[:opening])} … {' '.join(words[-closing:])}"


@dataclass(frozen=True, slots=True)
class Card:
    """What a synthetic document holds at one paragraph."""

    element: int
    text: str
    completeness: CardCompleteness = CardCompleteness.FULL
    short_cite: str | None = "Quillon 26"


def cite_only(element: int, short_cite: str = "Marrow 25") -> Card:
    return Card(element, "", CardCompleteness.CITE_ONLY, short_cite)


def abbreviated(element: int, text: str, short_cite: str | None = "Quillon 26") -> Card:
    return Card(element, text, CardCompleteness.ABBREVIATED, short_cite)


class SyntheticParser:
    """Answers for each registered source with the cards it was given, as the parser would build them:
    provenance from the job, a formatting span on each body, and a refusal for what it was told to
    refuse or cannot read."""

    parser_version = PARSER_VERSION
    profile_version = PROFILE_VERSION

    def __init__(self, documents: dict[str, tuple[Card, ...] | ParseFailureReason]) -> None:
        self._documents = documents

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        spec = self._documents[source.sha256]
        if source.source_format is not SourceFormat.DOCX or isinstance(spec, ParseFailureReason):
            return ParseFailure(
                source_sha256=source.sha256,
                source_path=source_path,
                reason=spec
                if isinstance(spec, ParseFailureReason)
                else ParseFailureReason.UNSUPPORTED_FORMAT,
                detail="synthetic",
                parser_version=PARSER_VERSION,
            )
        assert snapshot is not None
        return ParsedDocument(
            source_sha256=source.sha256,
            source_path=source_path,
            parser_version=PARSER_VERSION,
            profile_version=PROFILE_VERSION,
            cards=tuple(self._card(card, source, source_path, snapshot, camp) for card in spec),
        )

    def _card(
        self, card: Card, source: SourceDocument, path: str, snapshot: SnapshotDate, camp: str | None
    ) -> ParsedCard:
        spans = (
            (
                FormattingSpan(
                    emphasis=RunEmphasis.UNDERLINE,
                    start_offset=0,
                    end_offset=len(card.text),
                    rule_id="synthetic-underline",
                    match_source=StyleMatchSource.VERBATIM,
                ),
            )
            if card.text
            else ()
        )
        return ParsedCard(
            tag="An invented claim",
            short_cite=card.short_cite,
            full_cite=f"{card.short_cite or 'Unnamed'} (Invented Author, Fictional Quarterly, 2026)",
            evidence_text=card.text,
            completeness=card.completeness,
            formatting_spans=spans,
            match_source=StyleMatchSource.VERBATIM,
            confidence=1.0,
            provenance=FileImportProvenance(
                source_sha256=source.sha256,
                source_path=path,
                origin=SourceOrigin.OPENEV if camp is not None else SourceOrigin.CASELIST_ARCHIVE,
                caselist=None if camp is not None else CASELIST,
                camp=camp,
                snapshot=snapshot,
                first_element_index=card.element,
                last_element_index=card.element + 2,
                parser_version=PARSER_VERSION,
                profile_version=PROFILE_VERSION,
            ),
        )


@dataclass
class SyntheticStore:
    """A data directory whose manifests name synthetic sources, and a parse service over it."""

    data_dir: Path
    caselist: str = CASELIST
    documents: dict[str, tuple[Card, ...] | ParseFailureReason] = field(default_factory=dict)
    manifests: defaultdict[str, list[dict[str, object]]] = field(default_factory=lambda: defaultdict(list))

    def source(
        self,
        name: str,
        cards: tuple[Card, ...] | ParseFailureReason,
        *,
        at: Sequence[tuple[str, str]],
        source_format: str = "DOCX",
    ) -> str:
        """Store one source's bytes and list it at each `(snapshot, path)`; its SHA-256."""
        content = f"synthetic source {name}".encode()
        sha = hashlib.sha256(content).hexdigest()
        blob = self.data_dir / "blobs" / "sha256" / sha[0:2] / sha[2:4] / sha
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(content)
        self.documents[sha] = cards
        for snapshot, path in at:
            row: dict[str, object] = {
                "kind": "member",
                "classification": "NEW",
                "path": path,
                "sha256": sha,
                "byte_size": len(content),
                "format": source_format,
            }
            if self.caselist == OPENEV:
                row |= {"camp": "Invented Camp", "imported_on": "2026-07-30"}
            self.manifests[snapshot].append(row)
        self._write_manifests()
        return sha

    def _write_manifests(self) -> None:
        for snapshot, rows in self.manifests.items():
            manifest = self.data_dir / "objects" / "manifests" / self.caselist / f"{snapshot}.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    @property
    def store(self) -> LocalParsedStore:
        return LocalParsedStore(self.data_dir)

    @property
    def suppression(self) -> RecordedSuppressionList:
        return RecordedSuppressionList(local_suppression_list_file(self.data_dir))

    def service(self, card_placer: Callable[[], PlacesCards] | None = None) -> CaselistParseService:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        stats = CaselistCardStatsService(build_fake_caselist_repository(), ellipsis_markers=MARKERS)
        return CaselistParseService(
            local=LocalEvidence(
                objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
            ),
            store=self.store,
            parser=SyntheticParser(self.documents),
            runner=InProcessParseRunner(),
            suppression=self.suppression,
            card_placer=card_placer or stats.placer,
            failure_rate_threshold=1.0,
            failure_rate_minimum_sources=1,
        )

    async def parse(self, service: CaselistParseService | None = None) -> ParsePlan:
        """Plan and run once; the plan the run was made from."""
        service = service or self.service()
        plan = await service.plan(self.caselist)
        await service.run(plan)
        return plan

    def written(self, version: str = PARSER_VERSION) -> dict[str, bytes]:
        directory = self.data_dir / "parsed" / self.caselist / version
        return {name: (directory / name).read_bytes() for name in AGGREGATES if (directory / name).is_file()}

    async def stop(self, sha: str, *, disclosure: str | None = None) -> None:
        """What a removal made on another machine leaves on this one's list."""
        await self.suppression.append(
            [
                SuppressionEntry(
                    action=SuppressionAction.SUPPRESS,
                    sha256=sha,
                    disclosure=disclosure,
                    recorded_at=datetime(2026, 10, 30, 18, 0, tzinfo=UTC),
                    reason=ReasonCode.POLICY,
                    request_id="RM-2026-36",
                )
            ]
        )


# ------------------------------------------------------------------------------------------------
# The rebuild before v1-e40-t36, kept as the oracle
# ------------------------------------------------------------------------------------------------


def place_as_before(
    cards: Sequence[ParsedCard], thresholds: NearDuplicateThresholds, markers: tuple[str, ...]
) -> list[tuple[str, str, ClusterMembership]]:
    """`CaselistCardStatsService.place` at `61d3191`: `(fingerprint, cluster, membership)` per card."""
    fingerprints = [card_fingerprint(card).exact_fingerprint for card in cards]
    bodies: dict[str, str] = {}
    for card, fingerprint in zip(cards, fingerprints, strict=True):
        if card.completeness is CardCompleteness.FULL:
            bodies.setdefault(fingerprint, card.evidence_text)
    clusters = cluster_near_duplicates(bodies, thresholds)

    copies: Counter[tuple[str, str | None]] = Counter()
    full_by_cite: defaultdict[str | None, dict[str, FullCardWords]] = defaultdict(dict)
    for card, fingerprint in zip(cards, fingerprints, strict=True):
        if card.completeness is CardCompleteness.FULL:
            copies[(fingerprint, short_cite_key(card.short_cite))] += 1
    for card, fingerprint in zip(cards, fingerprints, strict=True):
        if card.completeness is CardCompleteness.FULL:
            key = short_cite_key(card.short_cite)
            if fingerprint not in full_by_cite[key]:
                full_by_cite[key][fingerprint] = FullCardWords(
                    clusters[fingerprint],
                    key,
                    tuple(matching_words(card.evidence_text)),
                    copies[(fingerprint, key)],
                )

    linked: dict[int, str] = {}
    keys: defaultdict[str, set[AbbreviationAnchor]] = defaultdict(set)
    not_grouped: set[str] = set()
    for position, (card, fingerprint) in enumerate(zip(cards, fingerprints, strict=True)):
        if card.completeness is CardCompleteness.FULL:
            continue
        anchor = abbreviation_anchor(card, markers)
        if anchor is None:
            continue
        matches = matching_full_cards(anchor, full_by_cite[anchor.short_cite_key].values())
        cluster = link_abbreviated(anchor, matches)
        if cluster is not None:
            linked[position] = cluster
            continue
        keys[fingerprint].add(anchor)
        if matches:
            not_grouped.add(fingerprint)
    groups = group_unmatched_abbreviations(
        {
            fingerprint: next(iter(anchors))
            for fingerprint, anchors in keys.items()
            if len(anchors) == 1 and fingerprint not in not_grouped
        }
    )

    placed: list[tuple[str, str, ClusterMembership]] = []
    for position, (card, fingerprint) in enumerate(zip(cards, fingerprints, strict=True)):
        if card.completeness is CardCompleteness.FULL:
            placed.append((fingerprint, clusters[fingerprint], ClusterMembership.NEAR_DUPLICATE))
        elif position in linked:
            placed.append((fingerprint, linked[position], ClusterMembership.ABBREVIATED_LINK))
        elif fingerprint in groups:
            placed.append((fingerprint, groups[fingerprint], ClusterMembership.ABBREVIATED_LINK))
        else:
            placed.append((fingerprint, fingerprint, ClusterMembership.UNLINKED))
    return placed


def disclosure_spans_as_before(
    source: EnumeratedSource, state: SuppressionState
) -> list[tuple[str | None, str, str, tuple[str, ...]]]:
    """`caselist_parse._disclosure_spans` at `61d3191`."""
    spans: dict[DisclosureKey, tuple[str, str]] = {}
    for disclosed in live_disclosures(source, state):
        key = disclosure_key(source, disclosed)
        first, last = spans.get(key, (disclosed.snapshot, disclosed.snapshot))
        spans[key] = (min(first, disclosed.snapshot), max(last, disclosed.snapshot))
    return [
        (disclosure, first, last, camp_path_digests(source, state, first))
        for (disclosure, _), (first, last) in spans.items()
    ]


def rendered_as_before(records: Sequence[StoreRecord]) -> bytes:
    """`LocalParsedStore._write_lines`'s content at `61d3191`: the whole file, rendered at once."""
    return "".join(
        json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
        for record in records
    ).encode("utf-8")


def camp_path_records_as_before(
    occurrences: Sequence[OccurrenceRecord], table_sha256: str
) -> list[CampPathRecord]:
    """`local.parsed_store._camp_path_records` at `61d3191`."""
    records: dict[tuple[str, str, str], CampPathRecord] = {}
    for row in occurrences:
        for path in row.camp_path_disclosures:
            key = (row.snapshot, row.source_sha256, path)
            if key not in records:
                records[key] = CampPathRecord(
                    caselist=row.caselist,
                    snapshot=row.snapshot,
                    source_sha256=row.source_sha256,
                    parser_version=row.parser_version,
                    profile_version=row.profile_version,
                    fingerprint_version=row.fingerprint_version,
                    camp_path_disclosure=path,
                    occurrence_table_sha256=table_sha256,
                )
    return [records[key] for key in sorted(records)]


async def aggregates_as_before(world: SyntheticStore, plan: ParsePlan) -> dict[str, bytes]:
    """The four files `CaselistParseService._rebuild` wrote at `61d3191` for this store and plan."""
    store, state = world.store, plan.suppression
    held = {source.sha256: source for source in plan.sources}
    entries = await store.read_entries(plan.caselist, plan.version)
    index = [entry for entry in entries if is_aggregated(held.get(entry.source_sha256), state)]
    failures = [
        entry
        for entry in entries
        if entry.outcome is not SourceOutcome.PARSED and is_aggregated(held.get(entry.source_sha256), state)
    ]
    cards: list[ParsedCard] = []
    for entry in entries:
        source = held.get(entry.source_sha256)
        if entry.outcome is not SourceOutcome.PARSED or source is None:
            continue
        live = live_disclosures(source, state)
        if not live:
            continue
        record = await store.read_document(plan.caselist, plan.version, entry.source_sha256)
        assert record is not None
        document = record.to_parsed_document(live[0].path)
        cards.extend(
            card.model_copy(update={"formatting_spans": (), "font_size_spans": ()}) for card in document.cards
        )
    cards.sort(key=lambda card: (card.provenance.source_sha256, card.provenance.first_element_index))
    placements = place_as_before(cards, NearDuplicateThresholds(), MARKERS)
    spans = {sha256: disclosure_spans_as_before(source, state) for sha256, source in held.items()}
    rows: list[OccurrenceRecord] = []
    for card, (fingerprint, cluster_id, membership) in zip(cards, placements, strict=True):
        provenance = card.provenance
        source = held[provenance.source_sha256]
        for disclosure, first, last, camp_paths in spans[provenance.source_sha256]:
            rows.append(
                OccurrenceRecord(
                    caselist=plan.caselist,
                    snapshot=first,
                    last_snapshot=last,
                    source_sha256=provenance.source_sha256,
                    parser_version=plan.parser_version,
                    profile_version=plan.profile_version,
                    fingerprint_version=FINGERPRINT_VERSION,
                    disclosure=disclosure,
                    camp=source.camp,
                    first_element_index=provenance.first_element_index,
                    last_element_index=provenance.last_element_index,
                    exact_fingerprint=fingerprint,
                    cluster_id=cluster_id,
                    membership=membership,
                    completeness=card.completeness,
                    camp_path_disclosures=camp_paths,
                ),
            )
    ordered = sorted(
        rows,
        key=lambda row: (
            row.cluster_id,
            row.source_sha256,
            row.first_element_index,
            row.snapshot,
            row.disclosure or "",
        ),
    )
    table = rendered_as_before(ordered)
    files = {
        INDEX_NAME: rendered_as_before(index),
        FAILURES_NAME: rendered_as_before(failures),
        OCCURRENCES_NAME: table,
    }
    camp_paths = camp_path_records_as_before(ordered, hashlib.sha256(table).hexdigest())
    if camp_paths:
        files[CAMP_PATHS_NAME] = rendered_as_before(camp_paths)
    return files


async def assert_written_as_before(world: SyntheticStore, plan: ParsePlan) -> dict[str, bytes]:
    written = world.written(plan.version)
    expected = await aggregates_as_before(world, plan)
    assert sorted(written) == sorted(expected)
    for name in expected:
        assert hashlib.sha256(written[name]).hexdigest() == hashlib.sha256(expected[name]).hexdigest(), name
    return written


def lines(content: bytes) -> list[dict[str, object]]:
    return [json.loads(line) for line in content.decode("utf-8").splitlines()]


# ------------------------------------------------------------------------------------------------
# The stores
# ------------------------------------------------------------------------------------------------

SHARED: Final = body(1)
"""A full card three sources read: one copy exact, one with a word changed, one cut."""
SECOND: Final = body(2)
THIRD: Final = body(3, words=40)
UNMATCHED: Final = body(4)
"""The card two abbreviated cards were cut from, which nobody disclosed in full."""


def caselist_sources(world: SyntheticStore) -> dict[str, str]:
    """Sources that share cards and clusters across one another, and the refusals beside them."""
    return {
        # Out of paragraph order in its document, and in three weeks at one path and at a second path.
        "alpha": world.source(
            "alpha",
            (Card(10, SHARED), Card(2, SECOND), abbreviated(30, cut(SHARED))),
            at=[
                (WEEKS[0], "Lanternfield/Aff-Round1.docx"),
                (WEEKS[1], "Lanternfield/Aff-Round1.docx"),
                (WEEKS[2], "Lanternfield/Aff-Round1.docx"),
                (WEEKS[1], "Orvane/Neg-Round2.docx"),
            ],
        ),
        "beta": world.source(
            "beta", (Card(4, near_copy(SHARED)), Card(8, THIRD)), at=[(WEEKS[1], "Plinth/Aff-Round3.docx")]
        ),
        "gamma": world.source(
            "gamma",
            (Card(1, SECOND), cite_only(3), abbreviated(5, cut(UNMATCHED, 5, 7), "Tessel 24")),
            at=[(WEEKS[2], "Caddow/Neg-Round1.docx")],
        ),
        "delta": world.source(
            "delta",
            (
                abbreviated(2, cut(UNMATCHED, 6, 6), "Tessel 24"),
                cite_only(6),
                abbreviated(9, cut(SHARED, 8, 4)),
            ),
            at=[(WEEKS[2], "Ferrule/Aff-Round4.docx"), (WEEKS[3], "Ferrule/Aff-Round4.docx")],
        ),
        "two_paths": world.source(
            "two_paths",
            (Card(3, SHARED), Card(7, body(5))),
            at=[(WEEKS[1], "Wimble/Neg-Round5.docx"), (WEEKS[1], "Sorrel/Neg-Round6.docx")],
        ),
        "stopped_later": world.source(
            "stopped_later", (Card(1, SECOND), Card(2, body(6))), at=[(WEEKS[3], "Brindle/Aff-Round2.docx")]
        ),
        "failed": world.source(
            "failed", ParseFailureReason.MALFORMED_PACKAGE, at=[(WEEKS[0], "Quorl/Neg-Round3.docx")]
        ),
        "pdf": world.source("pdf", (), at=[(WEEKS[0], "Hessian/Aff-Round5.pdf")], source_format="PDF"),
    }


async def test_a_caselist_whose_sources_share_clusters_is_written_as_before(tmp_path: Path) -> None:
    world = SyntheticStore(tmp_path / "evidence")
    sources = caselist_sources(world)
    plan = await world.parse()

    written = await assert_written_as_before(world, plan)

    rows = lines(written[OCCURRENCES_NAME])
    # The preconditions, from the table above: a cluster spans three sources, an abbreviated card in
    # one source joins a full card's cluster in another, and the disclosure in three weeks is one row.
    by_source = defaultdict(set)
    for row in rows:
        by_source[row["cluster_id"]].add(row["source_sha256"])
    assert max(len(members) for members in by_source.values()) >= 3
    assert any(
        row["membership"] == "ABBREVIATED_LINK" and row["source_sha256"] == sources["delta"] for row in rows
    )
    assert {
        (row["snapshot"], row["last_snapshot"]) for row in rows if row["source_sha256"] == sources["alpha"]
    } == {
        (WEEKS[0], WEEKS[2]),
        (WEEKS[1], WEEKS[1]),
    }
    assert {row["reason"] for row in lines(written[FAILURES_NAME])} == {
        "MALFORMED_PACKAGE",
        "UNSUPPORTED_FORMAT",
    }


async def test_a_stopped_disclosure_and_a_stopped_source_are_written_as_before(tmp_path: Path) -> None:
    """Stopped after the first parse, so their documents are still in the directory and only the
    rebuild's own reading of the list keeps their rows out."""
    world = SyntheticStore(tmp_path / "evidence")
    sources = caselist_sources(world)
    await world.parse()
    await world.stop(sources["two_paths"], disclosure=disclosure_digest(CASELIST, "Wimble/Neg-Round5.docx"))
    await world.stop(sources["stopped_later"])
    plan = await world.parse()

    written = await assert_written_as_before(world, plan)

    rows = lines(written[OCCURRENCES_NAME])
    assert {row["disclosure"] for row in rows if row["source_sha256"] == sources["two_paths"]} == {
        disclosure_digest(CASELIST, "Sorrel/Neg-Round6.docx")
    }
    assert sources["stopped_later"] not in {row["source_sha256"] for row in rows}
    assert sources["stopped_later"] not in {row["source_sha256"] for row in lines(written[INDEX_NAME])}


async def test_camp_files_at_two_paths_of_a_release_are_written_as_before(tmp_path: Path) -> None:
    world = SyntheticStore(tmp_path / "evidence", caselist=OPENEV)
    two_paths = world.source(
        "camp-grid",
        (Card(4, SHARED), Card(1, SECOND), abbreviated(9, cut(SHARED))),
        at=[
            ("2031-policy", "openev-512-Synthetic_Grid_CP.docx"),
            ("2031-policy", "openev-513-Synthetic_Grid_CP.docx"),
            ("2032-policy", "openev-640-Synthetic_Grid_CP.docx"),
        ],
    )
    world.source(
        "camp-other",
        (Card(2, near_copy(SHARED)), Card(6, THIRD)),
        at=[("2031-policy", "openev-77-Other.docx")],
    )
    plan = await world.parse()

    written = await assert_written_as_before(world, plan)
    assert len(lines(written[CAMP_PATHS_NAME])) == 3 + 1

    await world.stop(
        two_paths, disclosure=camp_path_disclosure("2031-policy", "openev-512-Synthetic_Grid_CP.docx")
    )
    plan = await world.parse()

    written = await assert_written_as_before(world, plan)
    assert {row["camp_path_disclosure"] for row in lines(written[CAMP_PATHS_NAME])} == {
        camp_path_disclosure("2031-policy", "openev-513-Synthetic_Grid_CP.docx"),
        camp_path_disclosure("2032-policy", "openev-640-Synthetic_Grid_CP.docx"),
        camp_path_disclosure("2031-policy", "openev-77-Other.docx"),
    }


def generated_store(world: SyntheticStore, seed: int) -> list[str]:
    """Thirty sources drawn from a few bodies, their copies, near copies and cuts, at one to three
    paths in up to four weeks; the digests, in the order they were made."""
    chosen = random.Random(seed)
    bodies = [body(seed * 100 + number, words=chosen.randint(12, 80)) for number in range(8)]
    cites = ["Quillon 26", "Tessel 24", "Marrow 25"]
    digests: list[str] = []
    for number in range(30):
        cards: list[Card] = []
        for element in chosen.sample(range(40), chosen.randint(1, 8)):
            text, kind = chosen.choice(bodies), chosen.random()
            cite = chosen.choice(cites)
            if kind < 0.5:
                cards.append(Card(element, text, short_cite=cite))
            elif kind < 0.7:
                cards.append(Card(element, near_copy(text), short_cite=cite))
            elif kind < 0.9:
                cards.append(
                    abbreviated(element, cut(text, chosen.randint(3, 8), chosen.randint(3, 8)), cite)
                )
            else:
                cards.append(cite_only(element, cite))
        paths = [f"School{chosen.randint(1, 9)}/Round{number}-{side}.docx" for side in ("Aff", "Neg")]
        at = sorted({(chosen.choice(WEEKS), chosen.choice(paths)) for _ in range(chosen.randint(1, 3))})
        digests.append(world.source(f"generated-{seed}-{number}", tuple(cards), at=at))
    return digests


@pytest.mark.parametrize("seed", [3, 17, 41])
async def test_a_generated_store_is_written_as_before_and_after_a_removal(tmp_path: Path, seed: int) -> None:
    world = SyntheticStore(tmp_path / "evidence")
    digests = generated_store(world, seed)
    plan = await world.parse()
    await assert_written_as_before(world, plan)

    await world.stop(digests[seed % 30])
    plan = await world.parse()
    await assert_written_as_before(world, plan)


# ------------------------------------------------------------------------------------------------
# Memory
# ------------------------------------------------------------------------------------------------

POOL: Final = tuple(body(1000 + number, words=3000) for number in range(12))
"""Twelve long bodies every source of the memory stores reads: about 20 KB each, so that a card's
body is most of what holding it costs, and the distinct bodies do not grow with the sources."""


def memory_store(world: SyntheticStore, sources: int) -> set[str]:
    """`sources` sources of the twelve pool cards each, in their own week and path; their digests."""
    return {
        world.source(
            f"memory-{number}",
            tuple(Card(element * 3, text) for element, text in enumerate(POOL)),
            at=[(WEEKS[number % 4], f"School{number}/Aff-Round{number}.docx")],
        )
        for number in range(sources)
    }


class CountingPlacer:
    """The real placer, counting the store's cards still alive when it is asked to place them."""

    store: frozenset[str] = frozenset()
    alive_at_placing: list[int] = []

    def __init__(self) -> None:
        self._inner = CaselistCardStatsService(
            build_fake_caselist_repository(), ellipsis_markers=MARKERS
        ).placer()

    def add(self, card: ParsedCard) -> None:
        self._inner.add(card)

    def placements(self) -> Sequence[ClusterPlacement]:
        gc.collect()
        CountingPlacer.alive_at_placing.append(
            sum(
                1
                for held in gc.get_objects()
                if isinstance(held, ParsedCard) and held.provenance.source_sha256 in CountingPlacer.store
            )
        )
        return self._inner.placements()


async def test_no_card_but_the_last_read_is_alive_when_the_rebuild_places_them(tmp_path: Path) -> None:
    """The rebuild before this task held every card here: 24 sources of 12, 288."""
    world = SyntheticStore(tmp_path / "evidence")
    CountingPlacer.store = frozenset(memory_store(world, 24))
    CountingPlacer.alive_at_placing = []
    await world.parse()
    gc.collect()

    await world.parse(world.service(card_placer=CountingPlacer))

    (alive,) = CountingPlacer.alive_at_placing
    assert alive <= 1, alive


async def rebuild_peak(tmp_path: Path, sources: int) -> int:
    """The traced peak, in bytes, of a run with nothing to parse over `sources` memory sources."""
    world = SyntheticStore(tmp_path / f"evidence-{sources}")
    memory_store(world, sources)
    await world.parse()
    service = world.service()
    plan = await service.plan(CASELIST)
    assert not plan.to_parse
    gc.collect()
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        await service.run(plan)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


async def test_the_rebuilds_peak_grows_by_far_less_than_the_cards_of_the_sources_added(
    tmp_path: Path,
) -> None:
    """Six sources, then twenty-four: 216 cards more, of about 20 KB of body each. Holding them would
    add their bodies to the peak and more; reading them in turn adds a fingerprint and a row's place
    each, well under a quarter of their bodies."""
    fewer, more = 6, 24
    added_bodies = (more - fewer) * sum(len(text) for text in POOL)

    growth = await rebuild_peak(tmp_path, more) - await rebuild_peak(tmp_path, fewer)

    assert growth < added_bodies / 4, (growth, added_bodies)


# ------------------------------------------------------------------------------------------------
# Placement
# ------------------------------------------------------------------------------------------------

PLACEMENT_BODIES: Final = tuple(body(500 + number, words=24) for number in range(4))


def placement_card(kind: int, which: int, opening: int, element: int) -> ParsedCard:
    text = PLACEMENT_BODIES[which]
    shapes = (
        Card(element, text),
        Card(element, near_copy(text)),
        Card(element, text, short_cite="Tessel 24"),
        abbreviated(element, cut(text, opening, 9 - opening)),
        abbreviated(element, cut(text, opening, 3), "Tessel 24"),
        cite_only(element),
    )
    sha = hashlib.sha256(f"placement source {element % 5}".encode()).hexdigest()
    document = SourceDocument(
        sha256=sha,
        byte_size=1,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=date(2026, 9, 1),
        last_seen_snapshot=date(2026, 9, 1),
    )
    return SyntheticParser({})._card(shapes[kind], document, "Synthetic/Path.docx", date(2026, 9, 1), None)  # pyright: ignore[reportPrivateUsage]


@settings(max_examples=150, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 5), st.integers(0, 3), st.integers(3, 6), st.integers(0, 60)),
        min_size=1,
        max_size=24,
    )
)
def test_the_placer_places_cards_given_one_at_a_time_as_the_one_list_did(
    shapes: list[tuple[int, int, int, int]],
) -> None:
    cards = [placement_card(*shape) for shape in shapes]
    placer = CaselistCardStatsService(build_fake_caselist_repository(), ellipsis_markers=MARKERS).placer()
    for card in cards:
        placer.add(card)

    placed = [(item.fingerprint, item.cluster_id, item.membership) for item in placer.placements()]

    assert placed == place_as_before(cards, NearDuplicateThresholds(), MARKERS)

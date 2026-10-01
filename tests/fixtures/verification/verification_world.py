"""An evidence verifier wired to in-memory stores, and cards cut from real snapshots for it to check.

Shared by the verifier's tests (`packages/debate_core/tests/evidence/test_verifier*.py`) and meant
for any exporter's tests that need a card that verifies and one that does not, to show the exporter
calls `EvidenceVerifier.ensure_finished` (the hard-failure rule).

Snapshots go the way production's do: `SnapshotService.create` stores them, the record is saved to
the article repository, and `SnapshotService.load` reads them back with every integrity check.
Cards are cut by `EvidenceExtractor`, marked up with t03's `CardMarkup`, and put on a card by
`place_evidence_on_card`, the production mapping from a selection to a card (ADR-0018,
`v1-e03-t07`). This module does no offset arithmetic of its own, so a card here is made exactly as
production makes one, omissions included.

Every source text is invented.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any, cast

from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import AccessStatus, Card, Citation, ProvenanceMode, SpanPurpose
from debate_core.evidence.card_mapping import place_evidence_on_card
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan
from debate_core.evidence.selection import EvidenceSelection
from debate_core.evidence.verification_types import VerificationResult
from debate_core.testing import (
    FixedClock,
    InMemoryArticleRepository,
    InMemorySnapshotStore,
    SequentialIdGenerator,
)
from debate_core.testing.builders import DEFAULT_OWNER_ID, build_citation

ARTICLE_ID = "0ART0000000000000000000001"
CANONICAL_URL = "https://example.org/water/invented-basin"
EXTRACTOR_VERSION = "fake-extractor/1.0"
RETRIEVED_AT = datetime(2026, 9, 30, 12, 5, tzinfo=UTC)
VERIFIED_CITATION = build_citation()


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion; the in-memory stores never suspend."""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("an in-memory store suspended; fakes must not perform real I/O")


class VerificationWorld:
    """In-memory stores, a snapshot service and the verifier, wired the way a composition root does."""

    def __init__(self) -> None:
        self.blobs = InMemorySnapshotStore()
        self.articles = InMemoryArticleRepository()
        self.clock = FixedClock()
        self.snapshots = SnapshotService(
            blobs=self.blobs, clock=self.clock, id_generator=SequentialIdGenerator("SNAP")
        )
        self.verifier = EvidenceVerifier(articles=self.articles, snapshots=self.snapshots, clock=self.clock)
        self._card_ids = SequentialIdGenerator("CARD")

    def add_source(self, extracted_text: str, *, raw_bytes: bytes | None = None) -> LoadedSnapshot:
        """Create, save and load a snapshot of ``extracted_text``, as an article service would."""
        snapshot = run(
            self.snapshots.create(
                article_id=ARTICLE_ID,
                raw_bytes=extracted_text.encode("utf-8") if raw_bytes is None else raw_bytes,
                extracted_text=extracted_text,
                canonical_url=CANONICAL_URL,
                retrieved_at=RETRIEVED_AT,
                extractor_version=EXTRACTOR_VERSION,
                provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
                access_status=AccessStatus.ACCESSIBLE,
            )
        )
        run(self.articles.save_snapshot(snapshot))
        return run(self.snapshots.load(snapshot))

    def cut_card(
        self,
        source: LoadedSnapshot,
        start: int,
        end: int,
        markup: tuple[EvidenceMarkupSpan, ...] | None = None,
        *,
        citation: Citation = VERIFIED_CITATION,
    ) -> Card:
        """A card for ``[start, end)`` of ``source``, cut by the extractor, underlined end to end
        unless ``markup`` (snapshot offsets) says otherwise."""
        return self.cut_card_from_ranges(source, ((start, end),), markup, citation=citation)

    def cut_card_from_ranges(
        self,
        source: LoadedSnapshot,
        ranges: tuple[tuple[int, int], ...],
        markup: tuple[EvidenceMarkupSpan, ...] | None = None,
        *,
        citation: Citation = VERIFIED_CITATION,
    ) -> Card:
        """A card quoting the snapshot ``ranges`` of ``source`` and omitting what lies between them.

        Each kept segment is underlined end to end unless ``markup`` (snapshot offsets) says otherwise.
        """
        evidence = EvidenceExtractor().extract(
            source.snapshot, source.normalized, EvidenceSelection.of_offsets(*ranges)
        )
        spans = (
            tuple(
                EvidenceMarkupSpan.underline(segment.start, segment.end, SpanPurpose.CLAIM)
                for segment in evidence.segments
            )
            if markup is None
            else markup
        )
        return card_from_markup(
            CardMarkup(evidence, spans), card_id=self._card_ids.new_id(), citation=citation
        )

    def verify(self, card: Card) -> VerificationResult:
        return run(self.verifier.verify(card))

    def ensure_finished(self, card: Card) -> VerificationResult:
        return run(self.verifier.ensure_finished(card))


def card_from_markup(markup: CardMarkup, *, card_id: str, citation: Citation) -> Card:
    """The card ``markup`` makes: a fresh card for the snapshot's article, given to
    ``place_evidence_on_card``, which sets everything about the evidence."""
    snapshot = markup.evidence.snapshot
    blank = Card(
        card_id=card_id,
        owner_id=DEFAULT_OWNER_ID,
        article_id=snapshot.article_id,
        tag="Invented basin evidence for the verifier's tests",
        citation=citation,
        provenance_mode=snapshot.provenance_mode,
    )
    return place_evidence_on_card(blank, markup)

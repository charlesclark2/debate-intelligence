"""An evidence verifier wired to in-memory stores, and cards cut from real snapshots for it to check.

Shared by the verifier's tests (`packages/debate_core/tests/evidence/test_verifier*.py`) and meant
for any exporter's tests that need a card that verifies and one that does not, to show the exporter
calls `EvidenceVerifier.ensure_finished` (the hard-failure rule).

Snapshots go the way production's do: `SnapshotService.create` stores them, the record is saved to
the article repository, and `SnapshotService.load` reads them back with every integrity check.
Cards are built by `card_from_extraction` from `EvidenceExtractor` output. That mapping is test-only
on purpose: `v1-e03-t07` owns the production function that turns a selection into a card (ADR-0018)
and will switch these fixtures to it. Until then a card quotes one contiguous range.

Every source text is invented.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any, cast

from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import AccessStatus, Card, CardSpan, Citation, ProvenanceMode, SpanPurpose
from debate_core.evidence.extractor import EvidenceExtractor, ExtractedEvidence
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
        evidence = EvidenceExtractor().extract(
            source.snapshot, source.normalized, EvidenceSelection.of_offsets((start, end))
        )
        spans = (EvidenceMarkupSpan.underline(start, end, SpanPurpose.CLAIM),) if markup is None else markup
        return card_from_extraction(
            CardMarkup(evidence, spans), card_id=self._card_ids.new_id(), citation=citation
        )

    def verify(self, card: Card) -> VerificationResult:
        return run(self.verifier.verify(card))

    def ensure_finished(self, card: Card) -> VerificationResult:
        return run(self.verifier.ensure_finished(card))


def card_from_extraction(markup: CardMarkup, *, card_id: str, citation: Citation) -> Card:
    """The card a selection and its markup make, for single-segment evidence. Test-only (see above).

    The text, offsets, hash and version all come from the extractor's output; the spans are moved
    from snapshot offsets to evidence-text offsets by subtracting where the evidence starts.
    """
    evidence: ExtractedEvidence = markup.evidence
    if len(evidence.segments) != 1:
        raise ValueError("cards quote one contiguous range until v1-e03-t07 adds omitted ranges")
    return Card(
        card_id=card_id,
        owner_id=DEFAULT_OWNER_ID,
        article_id=evidence.snapshot.article_id,
        snapshot_id=evidence.snapshot_id,
        tag="Invented basin evidence for the verifier's tests",
        citation=citation,
        evidence_text=evidence.segments[0].text,
        evidence_start_offset=evidence.start,
        evidence_end_offset=evidence.end,
        normalized_text_hash=evidence.normalized_text_hash,
        normalizer_version=evidence.normalizer_version,
        spans=tuple(
            CardSpan(
                start_offset=span.start - evidence.start,
                end_offset=span.end - evidence.start,
                style=span.style,
                purpose=span.purpose,
            )
            for span in markup.spans
        ),
        provenance_mode=evidence.snapshot.provenance_mode,
    )

"""Skeleton for the red run of v1-e06-t02's happy-path node: it cuts nothing and saves a blank card."""

from __future__ import annotations

from debate_core.application.card_types import (
    CardFailure,
    CardFailureReason,
    CardSelecting,
    CutRequest,
    CutResult,
)
from debate_core.application.citation_service import CitationService
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports.persistence import ArticleRepository, CardRepository
from debate_core.application.ports.providers import Clock, IdGenerator
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import Card
from debate_core.evidence.verification_types import ReasonCode

__all__ = ["CardService"]


class CardService:
    def __init__(
        self,
        *,
        articles: ArticleRepository,
        snapshots: SnapshotService,
        selector: CardSelecting,
        citations: CitationService,
        verifier: EvidenceVerifier,
        cards: CardRepository,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._articles = articles
        self._snapshots = snapshots
        self._selector = selector
        self._citations = citations
        self._verifier = verifier
        self._cards = cards
        self._clock = clock
        self._ids = id_generator

    async def cut_card(self, request: CutRequest) -> CutResult:
        record = await self._articles.get_snapshot(request.snapshot_id)
        card = Card(
            card_id=self._ids.new_id(),
            owner_id=request.owner_id,
            article_id=record.article_id,
            tag=request.need,
            provenance_mode=record.provenance_mode,
        )
        recorded, verification = await self._verifier.verify_and_record(card)
        saved = await self._cards.create(recorded)
        failure = CardFailure(
            CardFailureReason.EVIDENCE_UNVERIFIED, "skeleton", verifier_code=ReasonCode.CARD_INCOMPLETE
        )
        return CutResult(card=saved, verification=verification, metadata=(), reasons=(failure,))

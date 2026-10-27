"""CardService: a stored snapshot and a research need in, a persisted card and its verdict out (v1-e06-t02).

:meth:`CardService.cut_card` is the use case behind `debate-research cut` (`v1-e06-t06`). Fetching is
ArticleService's (E04) and rendering and export are `v1-e06-t04` and `t05`'s; this module composes
what lies between, through the ports and services it is given (architecture proposal §6, §8):

1. **Read the snapshot record**, and refuse one whose access status is not ACCESSIBLE with
   :class:`~debate_core.application.card_types.SourceNotAccessibleError`, before any model call and
   without making a card.
2. **Load it** with every integrity check (:meth:`SnapshotService.load
   <debate_core.application.snapshot_service.SnapshotService.load>`). The model is shown that text,
   numbered by paragraph, and nothing else.
3. **Select** (`card.select`), fail-closed, through the injected
   :class:`~debate_core.application.card_types.CardSelecting`; the tag is the selection's.
4. **Extract** the selected passages from the snapshot's normalized text
   (:class:`~debate_core.evidence.extractor.EvidenceExtractor`). The evidence text is always that
   slice: no model output ever becomes card text (ADR-0006).
5. **Mark up** (`card.markup`) and map the spans onto the card
   (:func:`~debate_core.evidence.card_mapping.place_evidence_on_card`).
6. **Cite** the source (:class:`~debate_core.application.citation_service.CitationService`).
7. **Verify** (:class:`~debate_core.application.evidence_verifier.EvidenceVerifier`, the only code
   that sets VERIFIED) and **save** the card once, new, at revision 1
   (:meth:`CardRepository.create <debate_core.application.ports.persistence.CardRepository.create>`:
   the port's ``save`` updates a stored card and refuses a new one).

## Failures after the snapshot exists are reasons, not exceptions

From step 3 on, nothing that goes wrong with the card stops it being saved: a refused model answer
(``MODEL_OUTPUT_INVALID``), places that do not fit the snapshot (``SPAN_MISMATCH``) and a cite field
that is missing or unverified (``CITATION_UNVERIFIED``) each become a
:class:`~debate_core.application.card_types.CardFailure`, the pipeline goes on as far as it can, and
the card is saved UNVERIFIED with every reason the verifier found beside them (the §8 hard failure
rule). A selection that was refused leaves no evidence and keeps the student's need as the tag; a
markup that was refused leaves the evidence without marks, which the verifier refuses
(``CARD_INCOMPLETE``). The card is never saved looking finished.

What is not a verdict about the card propagates, and nothing is saved: a missing snapshot
(``NotFound``), a damaged one (``SnapshotIntegrityError``), a model provider that could not answer
(``ProviderError``), a prompt that is not registered, and a store that cannot be reached. The caller
reports that the cut could not run, rather than a card that failed.

## Model provenance

Each model call's :class:`~debate_core.domain.provenance.SourcedArtifactMetadata`, the route's model,
prompt id and version, parameters sent (temperature included) and the snapshot it was shown, is kept
on the card as ``generated_by`` and returned as :attr:`CutResult.metadata
<debate_core.application.card_types.CutResult.metadata>`. A refused call has no response, so it
leaves none; its failure names the prompt and version.
"""

from __future__ import annotations

from collections.abc import Awaitable

from debate_core.application.card_types import (
    CardFailure,
    CardFailureReason,
    CardSelecting,
    CutRequest,
    CutResult,
    SourceNotAccessibleError,
)
from debate_core.application.citation_service import CitationService
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.model_errors import ModelOutputError
from debate_core.application.ports.persistence import ArticleRepository, CardRepository
from debate_core.application.ports.providers import Clock, IdGenerator
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import AccessStatus, Card
from debate_core.domain.provenance import SourcedArtifactMetadata
from debate_core.evidence.card_mapping import place_evidence_on_card
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.markup import CardMarkup, InvalidMarkup
from debate_core.evidence.numbered_snapshot import NumberedOffsetError, NumberedSnapshot
from debate_core.evidence.selection import InvalidSelection
from debate_core.evidence.selection_contract import GeneratedCardSelection
from debate_core.evidence.verification_types import ReasonCode, VerificationResult

__all__ = ["CardService", "failures_of"]

_SPAN_CODES = frozenset({ReasonCode.TEXT_MISMATCH, ReasonCode.SPAN_OUT_OF_RANGE})
"""The verifier's codes for evidence it could not reproduce at the card's offsets."""


class CardService:
    """Cuts cards from stored snapshots. Holds no state between calls."""

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
        self._extractor = EvidenceExtractor()

    async def cut_card(self, request: CutRequest) -> CutResult:
        """Cut, cite, verify and save one card for `request`; see the module docstring.

        Raises :class:`~debate_core.application.card_types.SourceNotAccessibleError` for a snapshot that
        is not ACCESSIBLE, before any model call. Every failure after that which is about the card is a
        reason on the saved UNVERIFIED card; the rest propagate with nothing saved.
        """
        record = await self._articles.get_snapshot(request.snapshot_id)
        if record.access_status is not AccessStatus.ACCESSIBLE:
            raise SourceNotAccessibleError(record.snapshot_id, record.access_status)
        loaded = await self._snapshots.load(record)
        article = await self._articles.get(record.article_id)
        now = self._clock.now()
        card = Card(
            card_id=self._ids.new_id(),
            owner_id=request.owner_id,
            organization_id=request.organization_id,
            article_id=article.article_id,
            snapshot_id=record.snapshot_id,
            tag=request.need,
            provenance_mode=record.provenance_mode,
            format_profile=request.format_profile,
            created_at=now,
            updated_at=now,
        )
        cut = _Cut(card)
        selected = await cut.answer(self._selector.select(loaded, request.research_need))
        if selected is not None:
            cut.generated.append(selected.metadata)
            cut.card = cut.card.evolve(tag=selected.selection.tag.text)
            await self._extract_and_mark(cut, loaded, selected, request.research_need)
        resolution = await self._citations.resolve(article, loaded)
        card = cut.card.evolve(citation=resolution.citation, generated_by=tuple(cut.generated))
        recorded, verification = await self._verifier.verify_and_record(card)
        saved = await self._cards.create(recorded)
        return CutResult(
            card=saved,
            verification=verification,
            metadata=saved.generated_by,
            reasons=tuple(dict.fromkeys((*cut.failures, *failures_of(verification, saved)))),
        )

    async def _extract_and_mark(
        self, cut: _Cut, loaded: LoadedSnapshot, selected: GeneratedCardSelection, research_need: str
    ) -> None:
        """Put the selected evidence, and the marks the model names in it, on `cut`'s card."""
        numbered = NumberedSnapshot(loaded.normalized)
        try:
            evidence = self._extractor.extract(
                loaded.snapshot, loaded.normalized, numbered.evidence_selection(selected.selection)
            )
        except (NumberedOffsetError, InvalidSelection) as unfit:
            cut.fail(CardFailureReason.SPAN_MISMATCH, f"the selection does not fit the snapshot: {unfit}")
            return
        markup = CardMarkup(evidence, ())
        marked = await cut.answer(self._selector.mark_up(loaded, selected, research_need))
        if marked is not None:
            cut.generated.append(marked.metadata)
            try:
                markup = CardMarkup(evidence, numbered.markup_spans(marked.markup))
            except (NumberedOffsetError, InvalidMarkup) as unfit:
                cut.fail(CardFailureReason.SPAN_MISMATCH, f"the markup does not fit the evidence: {unfit}")
        cut.card = place_evidence_on_card(cut.card, markup)


class _Cut:
    """One card being cut: the card so far, the model calls made for it, and what went wrong."""

    def __init__(self, card: Card) -> None:
        self.card = card
        self.generated: list[SourcedArtifactMetadata] = []
        self.failures: list[CardFailure] = []

    def fail(self, reason: CardFailureReason, detail: str) -> None:
        self.failures.append(CardFailure(reason, detail))

    async def answer[AnswerT](self, call: Awaitable[AnswerT]) -> AnswerT | None:
        """The model's answer, or `None` with ``MODEL_OUTPUT_INVALID`` recorded when it was refused."""
        try:
            return await call
        except ModelOutputError as refused:
            kinds = (
                ", ".join(dict.fromkeys(problem.type for problem in refused.problems)) or "no problems listed"
            )
            self.fail(
                CardFailureReason.MODEL_OUTPUT_INVALID,
                f"{refused.prompt_id}@{refused.prompt_version} was refused after {refused.attempts} "
                f"attempt(s): {kinds}",
            )
            return None


def failures_of(verification: VerificationResult, card: Card) -> tuple[CardFailure, ...]:
    """The verifier's reasons as card failures: cite fields, spans, and anything else by its code."""
    found: list[CardFailure] = []
    for reason in verification.reasons:
        if reason.code is ReasonCode.CITATION_UNVERIFIED:
            failure = CardFailure(
                CardFailureReason.CITATION_UNVERIFIED,
                reason.detail,
                fields=card.citation.unverified_fields,
                verifier_code=reason.code,
            )
        elif reason.code in _SPAN_CODES:
            failure = CardFailure(CardFailureReason.SPAN_MISMATCH, reason.detail, verifier_code=reason.code)
        else:
            failure = CardFailure(
                CardFailureReason.EVIDENCE_UNVERIFIED, reason.detail, verifier_code=reason.code
            )
        found.append(failure)
    return tuple(found)

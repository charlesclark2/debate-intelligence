"""Applies a student's edit to a stored card, re-verifies it, and saves it with the verdict (§8 step 7).

:meth:`CardEditService.edit` is the one way an edit reaches a stored card. The V2 rich-text editor
calls this same service; nothing about its UI belongs here. For one edit it:

1. refuses an insertion, substitution or move by kind
   (:func:`~debate_core.evidence.edit_policy.allowed_edit`), without reading its payload;
2. reads the card, and refuses with :class:`~debate_core.application.errors.RevisionMismatch` at once
   if its revision is not ``expected_revision``. The edit's offsets index the ``evidence_text`` the
   student was shown, which is the text at that revision, so they mean nothing against any other;
3. applies the edit:

   * a **quotation edit** (a deletion, a markup change, an interpolation added or removed) needs the
     card's snapshot, loaded with every integrity check
     (:meth:`~debate_core.application.snapshot_service.SnapshotService.load`), and cuts the card again
     from it (:func:`~debate_core.evidence.edit_policy.apply_quotation_edit`). On a card with no
     evidence yet it is refused (``CARD_HAS_NO_EVIDENCE``);
   * a **tag or cite edit** needs no snapshot and never re-cuts
     (:func:`~debate_core.evidence.edit_policy.apply_tag_or_cite_edit`), so it applies to any card,
     one with no evidence included;

   or refuses it with a typed :class:`~debate_core.evidence.edits.EvidenceEditRefused`;
4. re-verifies the result with
   :meth:`~debate_core.application.evidence_verifier.EvidenceVerifier.verify_and_record`, the only code
   that sets a card's status;
5. **saves it with that verdict, VERIFIED or not**, once, through :meth:`CardRepository.save` with
   ``expected_revision``, which refuses a write that raced another and increments the revision by one;
6. appends one :class:`~debate_core.application.ports.CardEditEntry` to the
   :class:`~debate_core.application.ports.CardEditLog`, with the status before and after.

A refused edit and an edit that loses a race leave the stored card unchanged and the log untouched.

## Save with the verdict

Integrity comes from the policy, not from refusing to save. Every quotation edit is cut again from the
snapshot and must leave exactly the text the student saw, less what they deleted; insertions,
substitutions and moves are refused; and only the verifier sets a status, so whatever is saved says
truthfully whether it verifies. A VERIFIED card whose markup is all removed is saved UNVERIFIED with the
verifier's reason (``CARD_INCOMPLETE``), and adding markup back returns it to VERIFIED. A student's
changed cite field is unverified until the citation service re-resolves it (`v1-e06-t01` ac5), so the
card is saved UNVERIFIED (``CITATION_UNVERIFIED``) meanwhile. A tag edit on a card whose stored
quotation no longer matches its snapshot leaves the quotation as it was, and is saved UNVERIFIED
(``TEXT_MISMATCH``): neither repaired nor refused. :class:`CardEditResult` carries the statuses and the
verifier's reasons so the caller can say so.

## The card and the log entry are two writes

The card is saved first and the entry appended after, so a failure between them leaves an edit with no
entry rather than an entry for an edit that never happened. The in-memory fakes cannot fail between
the two. A production adapter (the V2 editor's, `v2-e12-t05` ac6) writes both in one transaction.
"""

from __future__ import annotations

from dataclasses import dataclass

from debate_core.application.errors import RevisionMismatch
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports import ArticleRepository, CardEditEntry, CardEditLog, CardRepository, Clock
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import Card, Ulid, VerificationStatus
from debate_core.evidence.edit_policy import (
    EditedCard,
    NegationFlag,
    allowed_edit,
    apply_quotation_edit,
    apply_tag_or_cite_edit,
)
from debate_core.evidence.edits import (
    EditCite,
    EditProblem,
    EditTag,
    EvidenceEdit,
    InvalidEvidenceEdit,
    QuotationEdit,
)
from debate_core.evidence.verification_types import VerificationReason, VerificationResult

__all__ = ["CardEditResult", "CardEditService"]


@dataclass(frozen=True, slots=True)
class CardEditResult:
    """An accepted edit: the card as saved, the verifier's verdict on it, and the entry logged for it."""

    card: Card
    """The card as stored, at ``entry.revision_after``, with the verifier's status."""

    verification: VerificationResult
    """The verifier's verdict on ``card``, VERIFIED or not."""

    entry: CardEditEntry
    """The audit entry appended for this edit."""

    @property
    def status_before(self) -> VerificationStatus:
        """The card's stored status when the edit was made against it."""
        return self.entry.status_before

    @property
    def status_after(self) -> VerificationStatus:
        """The status the edited card was saved with."""
        return self.entry.status_after

    @property
    def reasons(self) -> tuple[VerificationReason, ...]:
        """Why the edited card does not verify; empty when it does."""
        return self.verification.reasons

    @property
    def negation_flag(self) -> NegationFlag | None:
        """Set when the edit was a deletion that removed a word that negates (``v1-e03-t05`` ac6)."""
        return self.entry.negation_flag


class CardEditService:
    """Edits stored cards under the evidence edit policy. Holds no state between calls."""

    def __init__(
        self,
        *,
        cards: CardRepository,
        articles: ArticleRepository,
        snapshots: SnapshotService,
        verifier: EvidenceVerifier,
        edit_log: CardEditLog,
        clock: Clock,
    ) -> None:
        self._cards = cards
        self._articles = articles
        self._snapshots = snapshots
        self._verifier = verifier
        self._edit_log = edit_log
        self._clock = clock

    async def edit(
        self, card_id: Ulid, edit: EvidenceEdit, *, expected_revision: int, actor_id: Ulid
    ) -> CardEditResult:
        """Apply ``edit`` to the card ``card_id`` at ``expected_revision``, on behalf of ``actor_id``.

        The edited card is saved with the verifier's verdict, whatever it is. Raises
        :class:`~debate_core.evidence.edits.EvidenceEditRefused` when the policy refuses the edit and
        :class:`~debate_core.application.errors.RevisionMismatch` when the card is not at
        ``expected_revision`` (before anything else is read, or at the save if another write raced it).
        ``NotFound`` and ``SnapshotIntegrityError`` from reading the card, or the snapshot a quotation
        edit needs, propagate: an edit cannot be applied to evidence that cannot be read. In every one of
        those cases nothing is saved or logged.
        """
        allowed = allowed_edit(edit)
        card = await self._cards.get(card_id)
        if card.revision != expected_revision:
            raise RevisionMismatch("Card", card_id, expected_revision, card.revision)
        if isinstance(allowed, EditTag | EditCite):
            edited = apply_tag_or_cite_edit(card, allowed)
        else:
            edited = await self._apply_to_quotation(card, allowed)
        recorded, result = await self._verifier.verify_and_record(edited.card)
        saved = await self._cards.save(recorded, expected_revision=expected_revision)
        entry = CardEditEntry(
            card_id=saved.card_id,
            actor_id=actor_id,
            edit_kind=edited.kind,
            revision_before=expected_revision,
            revision_after=saved.revision,
            status_before=card.verification_status,
            status_after=saved.verification_status,
            recorded_at=self._clock.now(),
            negation_flag=edited.negation_flag,
        )
        await self._edit_log.append(entry)
        return CardEditResult(card=saved, verification=result, entry=entry)

    async def _apply_to_quotation(self, card: Card, edit: QuotationEdit) -> EditedCard:
        """Cut ``card`` again from its snapshot with ``edit`` applied, or refuse."""
        if card.snapshot_id is None:
            raise InvalidEvidenceEdit(
                edit.kind, EditProblem.CARD_HAS_NO_EVIDENCE, f"card {card.card_id} quotes nothing yet"
            )
        record = await self._articles.get_snapshot(card.snapshot_id)
        loaded = await self._snapshots.load(record)
        return apply_quotation_edit(card, edit, loaded.snapshot, loaded.normalized)

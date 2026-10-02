"""Applies a student's edit to a stored card, re-verifies it, and saves it (§8 step 7).

:meth:`CardEditService.edit` is the one way an edit reaches a stored card. The V2 rich-text editor
calls this same service; nothing about its UI belongs here. For one edit it:

1. reads the card, and refuses with :class:`~debate_core.application.errors.RevisionMismatch` at once
   if its revision is not ``expected_revision``. The edit's offsets index the ``evidence_text`` the
   student was shown, which is the text at that revision, so they mean nothing against any other;
2. loads the card's snapshot with every integrity check
   (:meth:`~debate_core.application.snapshot_service.SnapshotService.load`);
3. applies the edit with :func:`~debate_core.evidence.edit_policy.apply_edit`, which cuts the card again
   from the snapshot, or refuses it with a typed
   :class:`~debate_core.evidence.edits.EvidenceEditRefused`;
4. re-verifies the result with
   :meth:`~debate_core.application.evidence_verifier.EvidenceVerifier.verify_and_record`, the only code
   that changes a card's status. **Unless it comes back VERIFIED, nothing is saved**, and
   :class:`EditNotVerified` carries the verifier's reasons;
5. saves the card once, through :meth:`CardRepository.save` with ``expected_revision``, which refuses
   a write that raced another and increments the revision by one;
6. appends one :class:`~debate_core.application.ports.CardEditEntry` to the
   :class:`~debate_core.application.ports.CardEditLog`.

A refused edit, an edit that does not re-verify, and an edit that loses a race all leave the stored
card unchanged and the log untouched.

## Every kind of edit re-verifies, including a tag or a cite

The rule is the PM's: every accepted edit is re-verified and saved only if VERIFIED. A tag cannot
change what a card quotes, but re-verifying it costs one snapshot load and keeps a single path. It has
one consequence a caller should know: a card that does not verify today, for any reason, cannot be
edited through this service at all, not even its tag, until whatever stops it verifying is fixed.

## The card and the log entry are two writes

The card is saved first and the entry appended after, so a failure between them leaves an edit with no
entry rather than an entry for an edit that never happened. The in-memory fakes cannot fail between
the two. A production adapter (the V2 editor's) should write both in one transaction.
"""

from __future__ import annotations

from dataclasses import dataclass

from debate_core.application.errors import RevisionMismatch
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports import ArticleRepository, CardEditEntry, CardEditLog, CardRepository, Clock
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import Card, Ulid
from debate_core.evidence.edit_policy import NegationFlag, apply_edit
from debate_core.evidence.edits import (
    EditKind,
    EditProblem,
    EvidenceEdit,
    EvidenceEditRefused,
    InvalidEvidenceEdit,
    kind_of,
)
from debate_core.evidence.verification_types import VerificationResult

__all__ = ["CardEditResult", "CardEditService", "EditNotVerified"]


class EditNotVerified(EvidenceEditRefused):
    """The edited card did not re-verify, so nothing was saved. ``result`` says why."""

    def __init__(self, kind: EditKind, result: VerificationResult) -> None:
        self.result = result
        """The verifier's verdict on the edited card, with every reason it failed."""
        codes = ", ".join(code.value for code in result.reason_codes)
        super().__init__(kind, f"the edited card does not verify ({codes}); nothing was saved")


@dataclass(frozen=True, slots=True)
class CardEditResult:
    """An accepted edit: the card as saved, its verification, and the entry logged for it."""

    card: Card
    """The card as stored, VERIFIED, at ``entry.revision_after``."""

    verification: VerificationResult
    """The verifier's VERIFIED result for ``card``."""

    entry: CardEditEntry
    """The audit entry appended for this edit."""

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

        Raises :class:`~debate_core.application.errors.RevisionMismatch` when the card is not at
        ``expected_revision`` (before anything else, or at the save if another write raced it),
        :class:`~debate_core.evidence.edits.EvidenceEditRefused` when the policy refuses the edit, and
        :class:`EditNotVerified` when the edited card does not verify. ``NotFound`` and
        ``SnapshotIntegrityError`` from reading the card or its snapshot propagate: an edit cannot be
        applied to evidence that cannot be read. In every one of those cases nothing is saved or logged.
        """
        kind = kind_of(edit)
        card = await self._cards.get(card_id)
        if card.revision != expected_revision:
            raise RevisionMismatch("Card", card_id, expected_revision, card.revision)
        if card.snapshot_id is None:
            raise InvalidEvidenceEdit(
                kind, EditProblem.CARD_HAS_NO_EVIDENCE, f"card {card_id} quotes nothing yet"
            )
        record = await self._articles.get_snapshot(card.snapshot_id)
        loaded = await self._snapshots.load(record)
        edited = apply_edit(card, edit, loaded.snapshot, loaded.normalized)
        recorded, result = await self._verifier.verify_and_record(edited.card)
        if not result.is_verified:
            raise EditNotVerified(kind, result)
        saved = await self._cards.save(recorded, expected_revision=expected_revision)
        entry = CardEditEntry(
            card_id=saved.card_id,
            actor_id=actor_id,
            edit_kind=kind,
            revision_before=expected_revision,
            revision_after=saved.revision,
            recorded_at=self._clock.now(),
            negation_flag=edited.negation_flag,
        )
        await self._edit_log.append(entry)
        return CardEditResult(card=saved, verification=result, entry=entry)

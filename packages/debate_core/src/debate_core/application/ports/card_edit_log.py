"""The audit trail of student edits to cards (`v1-e03-t05-edit-constraints`).

Every edit :class:`~debate_core.application.card_edit_service.CardEditService` accepts appends one
:class:`CardEditEntry`. A refused edit appends nothing, because nothing happened to the card.

## What an entry holds, and what it never holds

Who made the edit (an opaque actor id), which card, what kind of edit, the card's revision and
verification status before and after, when, and whether the edit removed a negation (and which
omission now holds it, as snapshot offsets). That is all. A status is not student data.

It never holds evidence text, the text that was deleted, an interpolation's words, a tag, a cite, or
any payload an editor sent. It holds no student data beyond the actor id: no name, no email, no
school (architecture proposal §14, data minimization). The edited card is in the card repository,
and the snapshot holds the quoted and deleted text; an auditor reads them there, under their own
access rules.

## Adapters

| Adapter | Where |
|---|---|
| :class:`~debate_core.testing.fakes.InMemoryCardEditLog` | tests |

None yet in production. No V1 command edits a card; the V2 editor brings the first real one, and
with it the need to write the entry in the same transaction as the card (see the service's module
docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from debate_core.domain import Ulid, VerificationStatus
from debate_core.evidence.edit_policy import NegationFlag
from debate_core.evidence.edits import EditKind

__all__ = ["CardEditEntry", "CardEditLog"]


@dataclass(frozen=True, slots=True)
class CardEditEntry:
    """One accepted edit to one card."""

    card_id: Ulid
    """The card edited."""

    actor_id: Ulid
    """Who edited it: an opaque user id, the only student data an entry holds."""

    edit_kind: EditKind
    """What kind of edit it was. Only allowed kinds appear, since refused edits are not logged."""

    revision_before: int
    """The card's revision the edit was made against."""

    revision_after: int
    """The card's revision once the edit was saved: one more than ``revision_before``."""

    status_before: VerificationStatus
    """The card's stored verification status when the edit was made against it."""

    status_after: VerificationStatus
    """The status the edited card was saved with: the verifier's verdict on it."""

    recorded_at: datetime
    """When the edit was saved, in UTC."""

    negation_flag: NegationFlag | None
    """Set when a deletion removed a word that negates, naming the omission that holds it."""


class CardEditLog(Protocol):
    """Appends and reads the edit history of cards. Entries are never changed or removed."""

    async def append(self, entry: CardEditEntry) -> None:
        """Record ``entry`` after every entry already recorded for its card."""
        ...

    async def entries_for(self, card_id: Ulid) -> tuple[CardEditEntry, ...]:
        """Every entry recorded for ``card_id``, oldest first; empty when there are none."""
        ...

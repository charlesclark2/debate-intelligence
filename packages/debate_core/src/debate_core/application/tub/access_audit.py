"""The access records: a card page view, a copy, a download and a search (`v1-e39-t07`).

The data-use policy's E39 gate item 4: every access is audited, with the time, the account's
subject, its role, the action and the card cluster ids, and nothing else. The records are
:class:`~debate_core.application.tub.audit.AuditRecord`, in the shape the coach's account changes
already use, written to the same append-only log.

## Written before the card goes out (the PM's rulings of 2026-10-22)

A card page, a copy and a download are each recorded **before** the card leaves the function. A
record that cannot be written raises :class:`AccessNotRecorded`, and the route answers without the
card: an access the log cannot hold does not happen.

A search is counted, not recorded as an access to any card. Its record is written after the page is
found, and a failed write logs one warning naming the action and lets the search answer.

## What a search record is

One per search, for its first page only: a next page is the same search. Nothing is written for a
search that was refused, that had no search terms, or that the index could not answer. The record
holds the number of results on the page, and nothing about the query: :meth:`AccessAuditService.
searched` takes a session and a number, so a query, a filter or a cursor has no way in.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from debate_core.application.errors import DomainError, StoreError
from debate_core.application.ports.tub import AuditSink
from debate_core.application.tub.audit import AuditAction, AuditRecord, card_reference
from debate_core.application.tub.sessions import Session

__all__ = ["AccessAuditService", "AccessNotRecorded"]

logger = logging.getLogger(__name__)


class AccessNotRecorded(DomainError):
    """The record of a card access could not be written, so the card was not sent."""

    def __init__(self, action: AuditAction) -> None:
        self.action = action
        super().__init__(f"a {action.value} record could not be written, so the card was not sent")


class AccessAuditService:
    """Writes the access records for one function, through its audit sink."""

    def __init__(self, *, audit: AuditSink, clock: Callable[[], datetime]) -> None:
        self._audit = audit
        self._clock = clock

    def card_viewed(self, session: Session, caselist: str, cluster_id: str) -> None:
        """Record a card page before it is sent. :class:`AccessNotRecorded` if the record is not written."""
        self._card_access(AuditAction.CARD_VIEWED, session, [(caselist, cluster_id)])

    def card_copied(self, session: Session, caselist: str, cluster_id: str) -> None:
        """Record a copy before the card is sent. :class:`AccessNotRecorded` if the record is not written."""
        self._card_access(AuditAction.CARD_COPIED, session, [(caselist, cluster_id)])

    def cards_downloaded(self, session: Session, cards: Sequence[tuple[str, str]]) -> None:
        """Record a download of `(caselist, cluster id)` cards before the file is sent (`v1-e39-t08`)."""
        self._card_access(AuditAction.CARDS_DOWNLOADED, session, cards)

    def searched(self, session: Session, results: int) -> None:
        """Count a search's first page. Never raises: a failed write is one warning naming the action."""
        record = AuditRecord(
            time=self._clock(),
            action=AuditAction.SEARCHED,
            actor_role=session.role,
            actor_subject=session.subject,
            count=results,
        )
        try:
            self._audit.record(record)
        except StoreError:
            logger.warning("tub audit: a %s record was not written", AuditAction.SEARCHED.value)

    def _card_access(self, action: AuditAction, session: Session, cards: Sequence[tuple[str, str]]) -> None:
        record = AuditRecord(
            time=self._clock(),
            action=action,
            actor_role=session.role,
            actor_subject=session.subject,
            cards=tuple(card_reference(caselist, cluster_id) for caselist, cluster_id in cards),
        )
        try:
            self._audit.record(record)
        except StoreError as problem:
            logger.warning("tub audit: a %s record was not written, so the card was not sent", action.value)
            raise AccessNotRecorded(action) from problem

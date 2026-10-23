"""The audit record every account change and every access is written as (ADR-0019 (e) 3).

One JSON object per event, holding the format version, the time, the action, the actor's pool
subject and role, and the subject of the account it changed, the cards it reached, or a count.
Nothing else: never a username, an email address, a password, a code, a token, a query, a URL, an
IP address, a school, a team code or a word of evidence (gate item 4). Every field is an
identifier, a role, a time or a number, and a card is named only as `<caselist>/<cluster id>`,
which :class:`AuditRecord` checks, so no field can carry text. A pool subject is an
opaque identifier Cognito assigns; it says which account without naming anyone, and it stops
meaning anything once the account is removed.

The coach's `tub users` commands run on the coach's Mac under the `TubAccounts` permission set, not
as a pool user, so their records carry the role `coach` and no actor subject. The pilot's own
records, of a change on the account page and of a session it ended, carry the student's subject as
the actor.

`session-ended-no-second-factor` is the pilot's own: revalidation ended a session because its
account no longer had a second factor it may sign in with (PM ruling, 2026-10-20).

## Access records (`v1-e39-t07`, the PM's rulings of 2026-10-22)

* `card-viewed` and `card-copied`: one card each, written by the card page and Copy card before the
  card goes out. A record that cannot be written stops the card (:mod:`debate_core.application.tub.
  access_audit`).
* `cards-downloaded`: up to :data:`MAX_DOWNLOAD_CARDS` cards, defined here for `v1-e39-t08`'s
  download, under the same rule.
* `searched`: one per search, its first page only, with `count` the number of results on that
  page and no card. Searches are counted, never recorded with their words (ADR-0019 (e) 3): there
  is no field a query, a filter or a cursor could go into, and the cards a search found are not
  named, since they would say what it was about.

`docs/data/tub-audit-record.schema.json` is this shape as a JSON Schema; a test holds the two
together.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from debate_core.application.tub.identity import Role
from debate_core.domain.file_recipe import RECIPE_STORE_PATTERN

__all__ = [
    "AUDIT_FORMAT_VERSION",
    "CARD_REFERENCE_PATTERN",
    "MAX_DOWNLOAD_CARDS",
    "AuditAction",
    "AuditRecord",
    "card_reference",
]

AUDIT_FORMAT_VERSION: Final = 1
"""Raised when a field's meaning changes, so a reader of a 400-day-old record knows which it is.

Still 1 after `v1-e39-t07`: it adds actions and the `cards` field, and changes no field's meaning."""

CARD_REFERENCE_PATTERN: Final = "^" + RECIPE_STORE_PATTERN.strip("^$") + "/[0-9a-f]{64}$"
"""`hsld26/<64 hex>`: a card as the pilot addresses it, the store and the cluster id in it."""

MAX_DOWNLOAD_CARDS: Final = 30
"""The most cards one download holds (ADR-0019 (d), the download cart)."""

_CARD_REFERENCE: Final = re.compile(CARD_REFERENCE_PATTERN)


def card_reference(caselist: str, cluster_id: str) -> str:
    """A card as a record names it, `<caselist>/<cluster id>`, or :class:`ValueError`."""
    reference = f"{caselist}/{cluster_id}"
    if _CARD_REFERENCE.match(reference) is None:
        raise ValueError("a card is named by its store and its 64-character cluster id")
    return reference


class AuditAction(StrEnum):
    """What happened. The coach's commands, the student's own changes, then the pilot's own."""

    ACCOUNT_ADDED = "account-added"
    ACCOUNTS_LISTED = "accounts-listed"
    ACCOUNT_RESET = "account-reset"
    ACCOUNT_DISABLED = "account-disabled"
    ACCOUNT_ENABLED = "account-enabled"
    ACCOUNT_REMOVED = "account-removed"
    EMAIL_SECOND_FACTOR_ALLOWED = "email-second-factor-allowed"
    EMAIL_SECOND_FACTOR_WITHDRAWN = "email-second-factor-withdrawn"
    BACKUP_EMAIL_ADDED = "backup-email-added"
    BACKUP_EMAIL_REMOVED = "backup-email-removed"
    AUTHENTICATOR_REGISTERED = "authenticator-registered"
    SESSION_ENDED_NO_SECOND_FACTOR = "session-ended-no-second-factor"
    SEARCHED = "searched"
    CARD_VIEWED = "card-viewed"
    CARD_COPIED = "card-copied"
    CARDS_DOWNLOADED = "cards-downloaded"


_ONE_CARD: Final = frozenset({AuditAction.CARD_VIEWED, AuditAction.CARD_COPIED})


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One audit event. Every field is an identifier, a role, a time or a number."""

    time: datetime
    action: AuditAction
    actor_role: Role
    actor_subject: str | None = None
    """The pool subject of whoever acted, or `None` for the coach's command line."""
    account_subject: str | None = None
    """The pool subject of the account the action changed, when it changed one."""
    count: int | None = None
    """How many: accounts in a listing, or results on a search's first page."""
    cards: tuple[str, ...] = ()
    """The cards an access reached, each as :func:`card_reference` names it."""

    def __post_init__(self) -> None:
        if self.count is not None and self.count < 0:
            raise ValueError("a count is never negative")
        for reference in self.cards:
            if _CARD_REFERENCE.match(reference) is None:
                raise ValueError("a card is named by its store and its 64-character cluster id")
        if self.action in _ONE_CARD and len(self.cards) != 1:
            raise ValueError(f"a {self.action.value} record names exactly one card")
        if self.action is AuditAction.CARDS_DOWNLOADED and not 1 <= len(self.cards) <= MAX_DOWNLOAD_CARDS:
            raise ValueError(f"a download holds 1 to {MAX_DOWNLOAD_CARDS} cards")
        if self.cards and self.action not in _ONE_CARD | {AuditAction.CARDS_DOWNLOADED}:
            raise ValueError(f"a {self.action.value} record names no card")
        if self.action is AuditAction.SEARCHED and (self.count is None or self.account_subject is not None):
            raise ValueError("a searched record carries its result count, and no account")

    def to_json(self) -> str:
        """The record as one line of JSON, keys sorted, with absent fields left out."""
        fields: dict[str, object] = {
            "format_version": AUDIT_FORMAT_VERSION,
            "time": self.time.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "action": self.action.value,
            "actor_role": self.actor_role.value,
        }
        if self.actor_subject is not None:
            fields["actor_subject"] = self.actor_subject
        if self.account_subject is not None:
            fields["account_subject"] = self.account_subject
        if self.count is not None:
            fields["count"] = self.count
        if self.cards:
            fields["cards"] = list(self.cards)
        return json.dumps(fields, sort_keys=True, separators=(",", ":"))

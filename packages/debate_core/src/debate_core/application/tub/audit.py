"""The audit record every account change is written as (ADR-0019 (e) 3).

One JSON object per event, holding the format version, the time, the action, the actor's pool
subject and role, and the subject of the account it changed or a count. Nothing else: never a
username, an email address, a password, a code or a token (gate item 4). A pool subject is an
opaque identifier Cognito assigns; it says which account without naming anyone, and it stops
meaning anything once the account is removed.

The coach's `tub users` commands run on the coach's Mac under the `TubAccounts` permission set, not
as a pool user, so their records carry the role `coach` and no actor subject. The pilot's own
records, of a change on the account page and of a session it ended, carry the student's subject as
the actor.

A replacement authenticator is recorded twice: `authenticator-replacement-started` when the student
chooses *Start*, which drops the old one, and `authenticator-registered` when the new one is
confirmed. A start with no registration after it is an abandoned replacement; if the session then
ended for want of a second factor, `session-ended-no-second-factor` says so (PM ruling,
2026-10-20).

`v1-e39-t07` adds the access records (searches counted, cards by cluster id) to the same shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from debate_core.application.tub.identity import Role

__all__ = ["AUDIT_FORMAT_VERSION", "AuditAction", "AuditRecord"]

AUDIT_FORMAT_VERSION: Final = 1
"""Raised when a field's meaning changes, so a reader of a 400-day-old record knows which it is."""


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
    AUTHENTICATOR_REPLACEMENT_STARTED = "authenticator-replacement-started"
    AUTHENTICATOR_REGISTERED = "authenticator-registered"
    SESSION_ENDED_NO_SECOND_FACTOR = "session-ended-no-second-factor"


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
    """How many, for an action over many accounts (a listing)."""

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
        return json.dumps(fields, sort_keys=True, separators=(",", ":"))

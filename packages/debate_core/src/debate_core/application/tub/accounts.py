"""The coach's `tub users` commands, as use cases (ADR-0019 (d), The account lifecycle).

* `add`: create (invitation suppressed), add to the role's group, and to `email-second-factor` if
  asked. Audit action `account-added`.
* `list`: list every account with its groups. `accounts-listed`, with the count.
* `reset`: a new temporary password, remove the authenticator, sign out everywhere.
  `account-reset`.
* `disable`: sign out everywhere, then disable. `account-disabled`.
* `enable`: enable. `account-enabled`.
* `remove`: sign out everywhere, then delete. `account-removed`.
* `email-second-factor`: add to or remove from that group. `email-second-factor-allowed` or
  `email-second-factor-withdrawn`.

Every command checks the username first, so an email-shaped name is refused before the pool is
asked anything. Each writes exactly one audit record, after the change it records, holding the
account's subject and no name. A temporary password is generated here, handed to the directory and
returned once in an :class:`IssuedPassword` for the command to print; it is in no record and no
error.

`disable` and `remove` sign the account out before they change it, so that every open session
fails its next revalidation and ends within five minutes (ADR-0019 (d), Revalidation).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from debate_core.application.ports.tub import AccountDirectory, AuditSink, DirectoryAccount
from debate_core.application.tub.audit import AuditAction, AuditRecord
from debate_core.application.tub.identity import (
    EMAIL_SECOND_FACTOR_GROUP,
    Role,
    TemporaryPassword,
    generate_temporary_password,
    parse_username,
    role_from_groups,
)

__all__ = ["AccountAdministration", "AccountSummary", "IssuedPassword"]


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """One line of `tub users list`: the username and the role, and nothing else."""

    username: str
    role: Role | None


@dataclass(frozen=True, slots=True)
class IssuedPassword:
    """What `add` and `reset` return: the one place a temporary password leaves this module."""

    username: str
    role: Role | None
    temporary_password: TemporaryPassword


class AccountAdministration:
    """The coach's account commands over one pool, each written to the audit log."""

    def __init__(
        self,
        *,
        directory: AccountDirectory,
        audit: AuditSink,
        clock: Callable[[], datetime],
        new_password: Callable[[], TemporaryPassword] = generate_temporary_password,
    ) -> None:
        self._directory = directory
        self._audit = audit
        self._clock = clock
        self._new_password = new_password

    def add(self, username: str, role: Role, *, email_second_factor: bool = False) -> IssuedPassword:
        """Create the account in `role`'s group and return its temporary password, shown once."""
        name = parse_username(username)
        password = self._new_password()
        subject = self._directory.create(name, password)
        self._directory.add_to_group(name, role.value)
        if email_second_factor:
            self._directory.add_to_group(name, EMAIL_SECOND_FACTOR_GROUP)
        self._record(AuditAction.ACCOUNT_ADDED, account_subject=subject)
        return IssuedPassword(username=name, role=role, temporary_password=password)

    def list(self) -> list[AccountSummary]:
        """Every account's username and role, by username."""
        accounts = self._directory.list_accounts()
        self._record(AuditAction.ACCOUNTS_LISTED, count=len(accounts))
        return sorted(
            (AccountSummary(account.username, role_from_groups(account.groups)) for account in accounts),
            key=lambda summary: summary.username,
        )

    def reset(self, username: str) -> IssuedPassword:
        """A new temporary password, the authenticator removed and every session ended."""
        account = self._account(username)
        password = self._new_password()
        self._directory.set_temporary_password(account.username, password)
        self._directory.remove_authenticator(account.username)
        self._directory.sign_out_everywhere(account.username)
        self._record(AuditAction.ACCOUNT_RESET, account_subject=account.subject)
        return IssuedPassword(
            username=account.username, role=role_from_groups(account.groups), temporary_password=password
        )

    def disable(self, username: str) -> AccountSummary:
        """Sign the account out everywhere, then disable it. Reversible with :meth:`enable`."""
        account = self._account(username)
        self._directory.sign_out_everywhere(account.username)
        self._directory.disable(account.username)
        self._record(AuditAction.ACCOUNT_DISABLED, account_subject=account.subject)
        return _summary(account)

    def enable(self, username: str) -> AccountSummary:
        """Let a disabled account sign in again."""
        account = self._account(username)
        self._directory.enable(account.username)
        self._record(AuditAction.ACCOUNT_ENABLED, account_subject=account.subject)
        return _summary(account)

    def remove(self, username: str) -> AccountSummary:
        """Sign the account out everywhere, then delete it with every attribute on it."""
        account = self._account(username)
        self._directory.sign_out_everywhere(account.username)
        self._directory.delete(account.username)
        self._record(AuditAction.ACCOUNT_REMOVED, account_subject=account.subject)
        return _summary(account)

    def set_email_second_factor(self, username: str, *, allowed: bool) -> AccountSummary:
        """Allow or withdraw a verified email as this account's only second factor."""
        account = self._account(username)
        if allowed:
            self._directory.add_to_group(account.username, EMAIL_SECOND_FACTOR_GROUP)
            action = AuditAction.EMAIL_SECOND_FACTOR_ALLOWED
        else:
            self._directory.remove_from_group(account.username, EMAIL_SECOND_FACTOR_GROUP)
            action = AuditAction.EMAIL_SECOND_FACTOR_WITHDRAWN
        self._record(action, account_subject=account.subject)
        return _summary(account)

    def _account(self, username: str) -> DirectoryAccount:
        return self._directory.get(parse_username(username))

    def _record(
        self, action: AuditAction, *, account_subject: str | None = None, count: int | None = None
    ) -> None:
        self._audit.record(
            AuditRecord(
                time=self._clock(),
                action=action,
                actor_role=Role.COACH,
                account_subject=account_subject,
                count=count,
            )
        )


def _summary(account: DirectoryAccount) -> AccountSummary:
    return AccountSummary(account.username, role_from_groups(account.groups))

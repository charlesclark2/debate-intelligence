"""The pilot's account and session rules, one at a time (debate_core.application.tub, v1-e39-t05)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest

from debate_core.application.errors import NotFound
from debate_core.application.ports.tub import AccountStanding, DirectoryAccount
from debate_core.application.tub.account_page import InvalidEmail, authenticator_uri, parse_email
from debate_core.application.tub.accounts import AccountAdministration
from debate_core.application.tub.audit import AuditAction, AuditRecord
from debate_core.application.tub.identity import (
    TEMPORARY_PASSWORD_ALPHABET,
    AuthenticatorSecret,
    InvalidUsername,
    Role,
    TemporaryPassword,
    generate_temporary_password,
    parse_username,
    role_from_groups,
)
from debate_core.application.tub.sessions import (
    PendingEnrolment,
    Session,
    SessionStanding,
    enrolment_is_current,
    new_sign_in_transaction,
    safe_return_path,
    session_standing,
    transaction_is_current,
)
from debate_core.application.tub.sign_in import SignInDecision, sign_in_decision

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)

# --------------------------------------------------------------------------------------------
# Usernames, roles and secrets
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["abc", "debater.one", "2027.class", "a" * 32, "..."])
def test_lowercase_letters_digits_and_dots_from_3_to_32_are_usernames(name: str) -> None:
    assert parse_username(name) == name


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("debater@example.test", "a username is never an email address"),
        ("@", "a username is never an email address"),
        ("debater.one@", "a username is never an email address"),
        ("ab", "use 3 to 32 lowercase letters, digits and dots"),
        ("a" * 33, "use 3 to 32 lowercase letters, digits and dots"),
        ("Debater", "use 3 to 32 lowercase letters, digits and dots"),
        ("debater_one", "use 3 to 32 lowercase letters, digits and dots"),
        ("debater one", "use 3 to 32 lowercase letters, digits and dots"),
        ("debater.one\n", "use 3 to 32 lowercase letters, digits and dots"),
        ("débater", "use 3 to 32 lowercase letters, digits and dots"),
        ("", "use 3 to 32 lowercase letters, digits and dots"),
    ],
)
def test_anything_else_is_refused_without_repeating_the_name(name: str, reason: str) -> None:
    with pytest.raises(InvalidUsername) as refused:
        parse_username(name)

    assert refused.value.reason == reason
    assert str(refused.value) == f"not a username: {reason}"


@pytest.mark.parametrize(
    ("groups", "role"),
    [
        ({"coach"}, Role.COACH),
        ({"coach", "student"}, Role.COACH),
        ({"student", "email-second-factor"}, Role.STUDENT),
        ({"email-second-factor"}, None),
        (set[str](), None),
        ({"administrator"}, None),
    ],
)
def test_the_role_comes_from_the_groups_coach_first(groups: set[str], role: Role | None) -> None:
    assert role_from_groups(groups) is role


def test_temporary_passwords_are_four_groups_of_four_unambiguous_characters() -> None:
    passwords = {generate_temporary_password().reveal() for _ in range(500)}

    assert len(passwords) == 500
    for password in passwords:
        groups = password.split("-")
        assert len(password) == 19 and len(groups) == 4
        assert all(len(group) == 4 and set(group) <= set(TEMPORARY_PASSWORD_ALPHABET) for group in groups)
    assert not set("01ilo") & set(TEMPORARY_PASSWORD_ALPHABET)


@pytest.mark.parametrize(
    "secret", [TemporaryPassword("abcd-efgh-jkmn-pqrs"), AuthenticatorSecret("JBSWY3DPEHPK3PXP")]
)
def test_a_secret_prints_as_a_placeholder(secret: TemporaryPassword | AuthenticatorSecret) -> None:
    value = secret.reveal()

    assert value not in repr(secret)
    assert value not in str(secret)
    assert value not in f"{secret}"


# --------------------------------------------------------------------------------------------
# Lifetimes
# --------------------------------------------------------------------------------------------


def session(**changes: object) -> Session:
    base = Session(
        subject="sub-1",
        username="debater.one",
        role=Role.STUDENT,
        email_second_factor=False,
        started_at=NOW,
        last_seen_at=NOW,
        revalidated_at=NOW,
        csrf_token="csrf",
        refresh_token="refresh",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("after", "standing"),
    [
        (timedelta(0), SessionStanding.CURRENT),
        (timedelta(minutes=4, seconds=59), SessionStanding.CURRENT),
        (timedelta(minutes=5), SessionStanding.DUE_FOR_REVALIDATION),
        (timedelta(minutes=59, seconds=59), SessionStanding.DUE_FOR_REVALIDATION),
        (timedelta(minutes=60), SessionStanding.IDLE),
        (timedelta(hours=12), SessionStanding.EXPIRED),
    ],
)
def test_a_session_left_alone(after: timedelta, standing: SessionStanding) -> None:
    assert session_standing(session(), NOW + after) is standing


def test_twelve_hours_from_sign_in_ends_a_session_seen_a_moment_ago() -> None:
    end = NOW + timedelta(hours=12)
    active = session(last_seen_at=end - timedelta(minutes=1), revalidated_at=end - timedelta(minutes=1))

    assert session_standing(active, end - timedelta(seconds=1)) is SessionStanding.CURRENT
    assert session_standing(active, end) is SessionStanding.EXPIRED


@pytest.mark.parametrize("moved", ["started_at", "last_seen_at", "revalidated_at"])
def test_a_time_in_the_future_is_not_trusted(moved: str) -> None:
    assert (
        session_standing(session(**{moved: NOW + timedelta(minutes=1)}), NOW) is not SessionStanding.CURRENT
    )


def test_a_sign_in_transaction_lasts_five_minutes_and_a_pending_enrolment_fifteen() -> None:
    transaction = new_sign_in_transaction("/", NOW)
    enrolment = PendingEnrolment(
        subject="sub-1",
        username="debater.one",
        role=Role.STUDENT,
        email_second_factor=False,
        started_at=NOW,
        return_to="/",
        csrf_token="csrf",
        refresh_token="refresh",
    )

    assert transaction_is_current(transaction, NOW + timedelta(minutes=4, seconds=59))
    assert not transaction_is_current(transaction, NOW + timedelta(minutes=5))
    assert enrolment_is_current(enrolment, NOW + timedelta(minutes=14, seconds=59))
    assert not enrolment_is_current(enrolment, NOW + timedelta(minutes=15))


def test_a_transactions_challenge_is_the_s256_of_its_verifier() -> None:
    import base64
    import hashlib

    transaction = new_sign_in_transaction("/", NOW)

    expected = base64.urlsafe_b64encode(hashlib.sha256(transaction.code_verifier.encode()).digest()).rstrip(
        b"="
    )
    assert transaction.code_challenge == expected.decode()
    assert 43 <= len(transaction.code_verifier) <= 128
    assert transaction.code_verifier not in repr(transaction)


@pytest.mark.parametrize(
    ("raw", "path"),
    [
        ("/account?done=email-sent", "/account?done=email-sent"),
        ("/", "/"),
        ("", "/"),
        (None, "/"),
        ("//evil.example/", "/"),
        ("/\\evil.example", "/"),
        ("https://evil.example/", "/"),
        ("account", "/"),
        ("/a\\b", "/"),
        ("/a\r\nSet-Cookie: x", "/"),
        ("/a\x7f", "/"),
    ],
)
def test_a_return_path_stays_on_the_site(raw: str | None, path: str) -> None:
    assert safe_return_path(raw) == path


# --------------------------------------------------------------------------------------------
# Who may have a session
# --------------------------------------------------------------------------------------------


def standing(authenticator: bool, email: str | None = None, verified: bool = False) -> AccountStanding:
    return AccountStanding(
        has_authenticator=authenticator, email=email, email_verified=verified, email_factor_enabled=verified
    )


@pytest.mark.parametrize(
    ("email_second_factor", "account", "decision"),
    [
        (False, standing(True), SignInDecision.START_SESSION),
        (True, standing(True), SignInDecision.START_SESSION),
        (False, standing(False), SignInDecision.ENROL_AUTHENTICATOR),
        (False, standing(False, "debater@example.test", True), SignInDecision.ENROL_AUTHENTICATOR),
        (True, standing(False, "debater@example.test", True), SignInDecision.START_SESSION),
        (True, standing(False, "debater@example.test", False), SignInDecision.ENROL_AUTHENTICATOR),
        (True, standing(False), SignInDecision.ENROL_AUTHENTICATOR),
    ],
)
def test_no_session_without_an_authenticator_unless_email_second_factor_with_a_verified_email(
    email_second_factor: bool, account: AccountStanding, decision: SignInDecision
) -> None:
    assert sign_in_decision(email_second_factor=email_second_factor, standing=account) is decision


# --------------------------------------------------------------------------------------------
# The audit record, emails and the authenticator URI
# --------------------------------------------------------------------------------------------


def test_an_audit_record_is_one_line_of_identifiers_and_nothing_else() -> None:
    record = AuditRecord(
        time=NOW, action=AuditAction.ACCOUNT_RESET, actor_role=Role.COACH, account_subject="sub-1"
    )

    line = record.to_json()

    assert "\n" not in line
    assert json.loads(line) == {
        "format_version": 1,
        "time": "2026-11-02T15:00:00Z",
        "action": "account-reset",
        "actor_role": "coach",
        "account_subject": "sub-1",
    }


@pytest.mark.parametrize(
    "raw", ["debater.one@example.test", "  debater.one@example.test  ", "a+b@sub.example.test"]
)
def test_an_email_is_trimmed_and_kept(raw: str) -> None:
    assert parse_email(raw) == raw.strip()


@pytest.mark.parametrize(
    "raw", ["", "debater", "debater@", "@example.test", "a@b", "a@b.", "a b@example.test", "a@@b.test"]
)
def test_something_else_is_not_an_email(raw: str) -> None:
    with pytest.raises(InvalidEmail):
        parse_email(raw)


def test_the_authenticator_uri_is_totp_sha1_six_digits_thirty_seconds() -> None:
    uri = authenticator_uri(
        AuthenticatorSecret("JBSWY3DPEHPK3PXP"), issuer="Team evidence search (dev)", username="debater.one"
    )

    assert uri == (
        "otpauth://totp/Team%20evidence%20search%20%28dev%29%3Adebater.one"
        "?secret=JBSWY3DPEHPK3PXP&issuer=Team%20evidence%20search%20%28dev%29&algorithm=SHA1&digits=6&period=30"
    )


# --------------------------------------------------------------------------------------------
# The coach's commands, over a directory that records what it was asked
# --------------------------------------------------------------------------------------------


@dataclass
class RecordingDirectory:
    accounts: dict[str, DirectoryAccount] = field(default_factory=lambda: {})
    calls: list[tuple[str, str]] = field(default_factory=lambda: [])

    def create(self, username: str, temporary_password: TemporaryPassword) -> str:
        self.calls.append(("create", username))
        self.accounts[username] = DirectoryAccount(username, f"sub-{username}", frozenset(), True)
        return f"sub-{username}"

    def add_to_group(self, username: str, group: str) -> None:
        self.calls.append((f"add-to-{group}", username))

    def remove_from_group(self, username: str, group: str) -> None:
        self.calls.append((f"remove-from-{group}", username))

    def get(self, username: str) -> DirectoryAccount:
        self.calls.append(("get", username))
        if username not in self.accounts:
            raise NotFound("account", username)
        return self.accounts[username]

    def list_accounts(self) -> Sequence[DirectoryAccount]:
        self.calls.append(("list", ""))
        return list(self.accounts.values())

    def set_temporary_password(self, username: str, temporary_password: TemporaryPassword) -> None:
        self.calls.append(("set-temporary-password", username))

    def remove_authenticator(self, username: str) -> None:
        self.calls.append(("remove-authenticator", username))

    def sign_out_everywhere(self, username: str) -> None:
        self.calls.append(("sign-out-everywhere", username))

    def disable(self, username: str) -> None:
        self.calls.append(("disable", username))

    def enable(self, username: str) -> None:
        self.calls.append(("enable", username))

    def delete(self, username: str) -> None:
        self.calls.append(("delete", username))


@dataclass
class RecordingAudit:
    records: list[AuditRecord] = field(default_factory=lambda: [])

    def record(self, record: AuditRecord) -> None:
        self.records.append(record)


def administration() -> tuple[AccountAdministration, RecordingDirectory, RecordingAudit]:
    directory, audit = RecordingDirectory(), RecordingAudit()
    directory.accounts["debater.one"] = DirectoryAccount("debater.one", "sub-1", frozenset({"student"}), True)
    return AccountAdministration(directory=directory, audit=audit, clock=lambda: NOW), directory, audit


@pytest.mark.parametrize(
    ("command", "calls", "action"),
    [
        (
            "reset",
            ["get", "set-temporary-password", "remove-authenticator", "sign-out-everywhere"],
            "account-reset",
        ),
        ("disable", ["get", "sign-out-everywhere", "disable"], "account-disabled"),
        ("enable", ["get", "enable"], "account-enabled"),
        ("remove", ["get", "sign-out-everywhere", "delete"], "account-removed"),
    ],
)
def test_each_command_makes_its_calls_in_order_and_writes_one_record(
    command: str, calls: list[str], action: str
) -> None:
    accounts, directory, audit = administration()

    getattr(accounts, command)("debater.one")

    assert [call for call, _ in directory.calls] == calls
    assert [(record.action.value, record.account_subject, record.actor_role) for record in audit.records] == [
        (action, "sub-1", Role.COACH)
    ]


def test_add_puts_the_account_in_its_role_and_the_fallback_group_when_asked() -> None:
    accounts, directory, audit = administration()

    issued = accounts.add("debater.two", Role.STUDENT, email_second_factor=True)

    assert directory.calls == [
        ("create", "debater.two"),
        ("add-to-student", "debater.two"),
        ("add-to-email-second-factor", "debater.two"),
    ]
    assert issued.temporary_password.reveal()
    assert [record.action for record in audit.records] == [AuditAction.ACCOUNT_ADDED]


def test_a_command_on_an_account_that_does_not_exist_changes_and_records_nothing() -> None:
    accounts, directory, audit = administration()

    with pytest.raises(NotFound):
        accounts.disable("nobody.here")

    assert directory.calls == [("get", "nobody.here")]
    assert audit.records == []


def test_list_gives_usernames_and_roles_by_username_and_records_the_count() -> None:
    accounts, directory, audit = administration()
    directory.accounts["coach.one"] = DirectoryAccount("coach.one", "sub-2", frozenset({"coach"}), True)
    directory.accounts["left.over"] = DirectoryAccount("left.over", "sub-3", frozenset(), True)

    summaries = accounts.list()

    assert [(s.username, s.role) for s in summaries] == [
        ("coach.one", Role.COACH),
        ("debater.one", Role.STUDENT),
        ("left.over", None),
    ]
    assert [(r.action, r.count, r.account_subject) for r in audit.records] == [
        (AuditAction.ACCOUNTS_LISTED, 3, None)
    ]

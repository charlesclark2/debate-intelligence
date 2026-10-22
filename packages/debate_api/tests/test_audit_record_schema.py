"""The committed audit-record schema and the code that writes records, held together (`v1-e39-t07`, ac2).

`docs/data/tub-audit-record.schema.json` is what a reader of the 400-day audit log is promised. The
drift half checks it against :mod:`debate_core.application.tub.audit` from both sides, from
hand-written expectations: the actions, the fields, the card pattern. The forbidden half builds a
record for every action, the way the code that writes it does, after an event full of things a
record must never hold (a fixture school, team code, query, URL, token, username, email address
and card text), and shows none of them in it. The schema refuses each forbidden field by name.

`conftest.FakeAuditSink` also validates every record the app writes in any test of this package.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Final

import pytest
from jsonschema import Draft202012Validator, ValidationError

from debate_core.application.ports.tub import DirectoryAccount
from debate_core.application.tub.access_audit import AccessAuditService
from debate_core.application.tub.accounts import AccountAdministration
from debate_core.application.tub.audit import (
    CARD_REFERENCE_PATTERN,
    MAX_DOWNLOAD_CARDS,
    AuditAction,
    AuditRecord,
)
from debate_core.application.tub.identity import Role, TemporaryPassword
from debate_core.application.tub.sessions import Session

AUDIT_RECORD_SCHEMA: Final = (
    Path(__file__).resolve().parents[3] / "docs" / "data" / "tub-audit-record.schema.json"
)
NOW: Final = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
SUBJECT: Final = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
"""A synthetic pool subject, in the UUID shape Cognito gives one."""

ACTIONS: Final = (
    "account-added",
    "accounts-listed",
    "account-reset",
    "account-disabled",
    "account-enabled",
    "account-removed",
    "email-second-factor-allowed",
    "email-second-factor-withdrawn",
    "backup-email-added",
    "backup-email-removed",
    "authenticator-registered",
    "session-ended-no-second-factor",
    "searched",
    "card-viewed",
    "card-copied",
    "cards-downloaded",
)
FIELDS: Final = {
    "format_version",
    "time",
    "action",
    "actor_role",
    "actor_subject",
    "account_subject",
    "count",
    "cards",
}

# What the event around a record held, every one of which a record must never hold.
SCHOOL, TEAM, QUERY = "Maple Grove", "QX", "zephyr Maple Grove QX"
URL: Final = "https://tub.example.test/search?q=zephyr+Maple+Grove+QX"
TOKEN: Final = "refresh-synthetic-0123456789"
USERNAME, EMAIL = "debater.audited", "debater.audited@example.test"
CARD_TEXT: Final = "Zephyr winds raise granite costs."
IP_ADDRESS: Final = "203.0.113.7"
FORBIDDEN_VALUES: Final = (SCHOOL, TEAM, QUERY, URL, TOKEN, USERNAME, EMAIL, CARD_TEXT, IP_ADDRESS, "zephyr")
FORBIDDEN_FIELDS: Final = (
    "query",
    "q",
    "url",
    "path",
    "token",
    "refresh_token",
    "name",
    "username",
    "email",
    "school",
    "team_code",
    "text",
    "card_text",
    "ip",
    "ip_address",
    "filters",
    "cursor",
)
CARDS: Final = (f"hsld26/{1:064x}", f"openev/{3:064x}")


def schema() -> dict[str, Any]:
    return json.loads(AUDIT_RECORD_SCHEMA.read_text(encoding="utf-8"))


@cache
def audit_record_validator() -> Draft202012Validator:
    Draft202012Validator.check_schema(schema())
    return Draft202012Validator(schema())


# ------------------------------------------------------------------------------------------------
# Drift: the schema and the code say the same thing
# ------------------------------------------------------------------------------------------------


def test_audit_schema_is_a_valid_draft_2020_12_schema_that_allows_no_other_field() -> None:
    audit_record_validator()
    committed = schema()
    assert committed["additionalProperties"] is False
    assert set(committed["properties"]) == FIELDS
    assert committed["required"] == ["format_version", "time", "action", "actor_role"]


def test_audit_schema_names_every_action_the_code_has_and_no_other() -> None:
    assert tuple(schema()["properties"]["action"]["enum"]) == ACTIONS
    assert tuple(action.value for action in AuditAction) == ACTIONS


def test_audit_record_has_exactly_the_schemas_fields() -> None:
    assert {"format_version"} | {field.name for field in dataclasses.fields(AuditRecord)} == FIELDS


def test_audit_schema_names_a_card_as_the_code_does() -> None:
    cards = schema()["properties"]["cards"]
    assert cards["items"]["pattern"] == CARD_REFERENCE_PATTERN == "^(?:[a-z]+[0-9]{2}|openev)/[0-9a-f]{64}$"
    assert cards["maxItems"] == MAX_DOWNLOAD_CARDS == 30
    assert schema()["properties"]["format_version"] == {"const": 1}
    assert schema()["properties"]["actor_role"]["enum"] == [role.value for role in Role]


# ------------------------------------------------------------------------------------------------
# Every action, as the code that writes it builds it
# ------------------------------------------------------------------------------------------------


class Directory:
    """One synthetic account, for the coach's commands."""

    def __init__(self) -> None:
        self.account = DirectoryAccount(
            username=USERNAME, subject=SUBJECT, groups=frozenset({"student"}), enabled=True
        )

    def create(self, username: str, temporary_password: TemporaryPassword) -> str:
        return SUBJECT

    def add_to_group(self, username: str, group: str) -> None: ...

    def remove_from_group(self, username: str, group: str) -> None: ...

    def get(self, username: str) -> DirectoryAccount:
        return self.account

    def list_accounts(self) -> Sequence[DirectoryAccount]:
        return [self.account]

    def set_temporary_password(self, username: str, temporary_password: TemporaryPassword) -> None: ...

    def remove_authenticator(self, username: str) -> None: ...

    def sign_out_everywhere(self, username: str) -> None: ...

    def disable(self, username: str) -> None: ...

    def enable(self, username: str) -> None: ...

    def delete(self, username: str) -> None: ...


class Sink:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, record: AuditRecord) -> None:
        self.records.append(record)


def session() -> Session:
    return Session(
        subject=SUBJECT,
        username=USERNAME,
        role=Role.STUDENT,
        email_second_factor=False,
        started_at=NOW,
        last_seen_at=NOW,
        revalidated_at=NOW,
        csrf_token="csrf-synthetic",
        refresh_token=TOKEN,
    )


def every_action() -> dict[str, AuditRecord]:
    """One record per action. The coach's eight and the four access records come from the code that
    writes them; the student's four account records are built as `account_page.py` and `sign_in.py`
    build theirs (the actor's own subject, as actor and account), since driving those flows here
    would only repeat `v1-e39-t05`'s tests, whose records `FakeAuditSink` already validates."""
    sink = Sink()
    accounts = AccountAdministration(
        directory=Directory(),
        audit=sink,
        clock=lambda: NOW,
        new_password=lambda: TemporaryPassword("Synthetic-pass-1"),
    )
    accounts.add(USERNAME, Role.STUDENT)
    accounts.list()
    accounts.reset(USERNAME)
    accounts.disable(USERNAME)
    accounts.enable(USERNAME)
    accounts.remove(USERNAME)
    accounts.set_email_second_factor(USERNAME, allowed=True)
    accounts.set_email_second_factor(USERNAME, allowed=False)
    access = AccessAuditService(audit=sink, clock=lambda: NOW)
    access.searched(session(), 7)
    access.card_viewed(session(), "hsld26", f"{1:064x}")
    access.card_copied(session(), "hsld26", f"{1:064x}")
    access.cards_downloaded(session(), [("hsld26", f"{1:064x}"), ("openev", f"{3:064x}")])
    for action in (
        AuditAction.BACKUP_EMAIL_ADDED,
        AuditAction.BACKUP_EMAIL_REMOVED,
        AuditAction.AUTHENTICATOR_REGISTERED,
        AuditAction.SESSION_ENDED_NO_SECOND_FACTOR,
    ):
        sink.record(
            AuditRecord(
                time=NOW,
                action=action,
                actor_role=Role.STUDENT,
                actor_subject=SUBJECT,
                account_subject=SUBJECT,
            )
        )
    return {record.action.value: record for record in sink.records}


EVERY_ACTION: Final = every_action()


def test_audit_every_action_has_a_record() -> None:
    assert sorted(EVERY_ACTION) == sorted(ACTIONS)


@pytest.mark.parametrize("action", ACTIONS)
def test_audit_every_actions_record_meets_the_schema_and_holds_no_forbidden_value(action: str) -> None:
    line = EVERY_ACTION[action].to_json()
    record = json.loads(line)

    audit_record_validator().validate(record)
    assert set(record) <= FIELDS
    assert not set(record) & set(FORBIDDEN_FIELDS)
    for value in FORBIDDEN_VALUES:
        assert value.lower() not in line.lower(), value


def test_audit_the_access_records_carry_exactly_their_fields() -> None:
    shapes = {action: set(json.loads(EVERY_ACTION[action].to_json())) for action in ACTIONS[-4:]}

    common = {"format_version", "time", "action", "actor_role", "actor_subject"}
    assert shapes == {
        "searched": common | {"count"},
        "card-viewed": common | {"cards"},
        "card-copied": common | {"cards"},
        "cards-downloaded": common | {"cards"},
    }
    assert json.loads(EVERY_ACTION["cards-downloaded"].to_json())["cards"] == list(CARDS)


# ------------------------------------------------------------------------------------------------
# What the schema refuses
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("field", FORBIDDEN_FIELDS)
def test_audit_schema_refuses_a_record_with_a_forbidden_field(field: str) -> None:
    record = json.loads(EVERY_ACTION["searched"].to_json())
    record[field] = QUERY

    with pytest.raises(ValidationError):
        audit_record_validator().validate(record)


@pytest.mark.parametrize(
    ("action", "change"),
    [
        pytest.param("card-viewed", {"cards": list(CARDS)}, id="a view of two cards"),
        pytest.param(
            "card-copied", {"cards": [f"hsld26/{1:064x} {SCHOOL}"]}, id="a card reference with words"
        ),
        pytest.param("card-viewed", {"count": 1}, id="a view with a count"),
        pytest.param("searched", {"cards": [CARDS[0]]}, id="a search naming a card"),
        pytest.param("searched", {"count": -1}, id="a negative count"),
        pytest.param("cards-downloaded", {"cards": [CARDS[0]] * 31}, id="a download of 31 cards"),
        pytest.param("account-added", {"cards": [CARDS[0]]}, id="an account change naming a card"),
        pytest.param("searched", {"actor_subject": f"{USERNAME} {EMAIL}"}, id="a subject with words"),
        pytest.param("searched", {"time": "2026-11-02 15:00"}, id="a time not in UTC seconds"),
    ],
)
def test_audit_schema_refuses_a_record_out_of_shape(action: str, change: dict[str, Any]) -> None:
    record = {**json.loads(EVERY_ACTION[action].to_json()), **change}

    with pytest.raises(ValidationError):
        audit_record_validator().validate(record)


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"action": AuditAction.CARD_VIEWED, "cards": CARDS}, id="a view of two cards"),
        pytest.param(
            {"action": AuditAction.CARD_COPIED, "cards": ("hsld26/Maple Grove",)}, id="a card with words"
        ),
        pytest.param({"action": AuditAction.SEARCHED}, id="a search with no count"),
        pytest.param(
            {"action": AuditAction.SEARCHED, "count": 3, "cards": CARDS[:1]}, id="a search naming a card"
        ),
        pytest.param(
            {"action": AuditAction.CARDS_DOWNLOADED, "cards": CARDS * 16}, id="a download of 32 cards"
        ),
        pytest.param(
            {"action": AuditAction.ACCOUNT_ADDED, "cards": CARDS[:1]}, id="an account change naming a card"
        ),
    ],
)
def test_audit_record_refuses_to_be_built_out_of_shape(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        AuditRecord(time=NOW, actor_role=Role.STUDENT, actor_subject=SUBJECT, **fields)

"""`debate-research tub users` (v1-e39-t05 ac3): the pool's administrative API, called as expected.

The real command, the real composition root and the real Cognito and CloudWatch adapters run here.
Only the two boto3 clients are replaced, by real clients under botocore's `Stubber`, which fails a
test on any call that was not queued or whose parameters differ from the ones written here. No
request leaves the process.

Every username, subject and address is synthetic.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import boto3
import pytest
from botocore.stub import ANY, Stubber
from typer.testing import CliRunner, Result

import debate_core.integrations.cloudwatch_audit as cloudwatch_audit
import debate_core.integrations.cognito as cognito
from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.tub.identity import TEMPORARY_PASSWORD_ALPHABET

POOL = "us-east-1_SyntheticPool"
SUBJECT = "0b8f2c3e-0000-4000-8000-000000000001"
PASSWORD_SHAPE = re.compile(
    rf"[{TEMPORARY_PASSWORD_ALPHABET}]{{4}}(?:-[{TEMPORARY_PASSWORD_ALPHABET}]{{4}}){{3}}"
)

runner = CliRunner()


def _client(service: str) -> Any:
    session = boto3.session.Session(
        aws_access_key_id="synthetic", aws_secret_access_key="synthetic", region_name="us-east-1"
    )
    return session.client(service)  # pyright: ignore[reportUnknownMemberType]


@dataclass(repr=False)
class StubbedPilot:
    """The two stubbed clients, what the commands sent through them, and the profiles they used.

    `repr=False`: botocore's hook logger prints a handler's repr at DEBUG, and this one holds the
    temporary password the command sent.
    """

    cognito: Any
    logs: Any
    profiles: list[str | None] = field(default_factory=lambda: [])
    sent: list[tuple[str, dict[str, Any]]] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        self.users = Stubber(self.cognito)
        self.audit_log = Stubber(self.logs)

    def capture(self, params: dict[str, Any], model: Any, **_: Any) -> None:
        self.sent.append((model.name, dict(params)))

    def expect(self, operation: str, params: dict[str, Any], response: dict[str, Any] | None = None) -> None:
        self.users.add_response(operation, response or {}, {"UserPoolId": POOL, **params})

    def expect_audit(self, *, group: str = "debate-dev-tub-audit") -> None:
        self.audit_log.add_response(
            "put_log_events", {}, {"logGroupName": group, "logStreamName": "tub-users", "logEvents": ANY}
        )

    def expect_account(self, username: str, groups: tuple[str, ...] = ("student",), **extra: Any) -> None:
        self.expect(
            "admin_get_user",
            {"Username": username},
            {
                "Username": username,
                "UserAttributes": [{"Name": "sub", "Value": SUBJECT}],
                "Enabled": True,
                **extra,
            },
        )
        self.expect(
            "admin_list_groups_for_user",
            {"Username": username},
            {"Groups": [{"GroupName": group} for group in groups]},
        )

    def sent_value(self, operation: str, name: str) -> Any:
        return next(params[name] for op, params in self.sent if op == operation)

    def audit_records(self) -> list[dict[str, Any]]:
        return [
            json.loads(event["message"])
            for op, params in self.sent
            if op == "PutLogEvents"
            for event in params["logEvents"]
        ]

    def assert_done(self) -> None:
        self.users.assert_no_pending_responses()
        self.audit_log.assert_no_pending_responses()


@pytest.fixture(scope="module")
def clients() -> tuple[Any, Any]:
    """Building a boto3 client takes longer than a test; each test gets its own Stubber on these."""
    return _client("cognito-idp"), _client("logs")


@pytest.fixture
def pilot(monkeypatch: pytest.MonkeyPatch, clients: tuple[Any, Any]) -> Iterator[StubbedPilot]:
    stubbed = StubbedPilot(*clients)
    for client in clients:
        client.meta.events.register(
            "provide-client-params.*.*", stubbed.capture, unique_id="tub-users-capture"
        )

    def admin_client(*, profile: str | None, region: str = "us-east-1") -> Any:
        stubbed.profiles.append(profile)
        return stubbed.cognito

    def logs_client(*, profile: str | None, region: str) -> Any:
        stubbed.profiles.append(profile)
        return stubbed.logs

    monkeypatch.setattr(cognito, "build_cognito_admin_client", admin_client)
    monkeypatch.setattr(cloudwatch_audit, "build_logs_client", logs_client)
    monkeypatch.setenv("TUB_USER_POOL_ID", POOL)
    try:
        with stubbed.users, stubbed.audit_log:
            yield stubbed
    finally:
        for client in clients:
            client.meta.events.unregister("provide-client-params.*.*", unique_id="tub-users-capture")


def tub_users(*args: str, json_output: bool = False, verbose: bool = False) -> Result:
    root = [*(["--json"] if json_output else []), *(["--verbose"] if verbose else [])]
    return runner.invoke(create_app(), [*root, "tub", "users", *args])


def passwords_in(text: str) -> list[str]:
    return PASSWORD_SHAPE.findall(text)


# --------------------------------------------------------------------------------------------
# add
# --------------------------------------------------------------------------------------------


def test_add_creates_the_account_with_no_invitation_and_shows_its_password_once(pilot: StubbedPilot) -> None:
    pilot.expect(
        "admin_create_user",
        {"Username": "debater.one", "TemporaryPassword": ANY, "MessageAction": "SUPPRESS"},
        {"User": {"Username": "debater.one", "Attributes": [{"Name": "sub", "Value": SUBJECT}]}},
    )
    pilot.expect("admin_add_user_to_group", {"Username": "debater.one", "GroupName": "student"})
    pilot.expect_audit()

    result = tub_users("add", "debater.one", "--role", "student", "--env", "dev")

    assert result.exit_code == ExitCode.OK, result.output
    sent_password = pilot.sent_value("AdminCreateUser", "TemporaryPassword")
    assert PASSWORD_SHAPE.fullmatch(sent_password)
    assert result.stdout.count(sent_password) == 1
    assert passwords_in(result.stderr) == []
    assert "Created debater.one (student)" in result.stdout
    pilot.assert_done()


def test_add_writes_one_audit_record_with_the_subject_and_no_name(pilot: StubbedPilot) -> None:
    pilot.expect(
        "admin_create_user",
        {"Username": "debater.one", "TemporaryPassword": ANY, "MessageAction": "SUPPRESS"},
        {"User": {"Username": "debater.one", "Attributes": [{"Name": "sub", "Value": SUBJECT}]}},
    )
    pilot.expect("admin_add_user_to_group", {"Username": "debater.one", "GroupName": "student"})
    pilot.expect_audit()

    tub_users("add", "debater.one", "--env", "dev")

    [record] = pilot.audit_records()
    assert record == {
        "format_version": 1,
        "time": record["time"],
        "action": "account-added",
        "actor_role": "coach",
        "account_subject": SUBJECT,
    }
    message = pilot.sent[-1][1]["logEvents"][0]["message"]
    assert "debater.one" not in message
    assert pilot.sent_value("AdminCreateUser", "TemporaryPassword") not in message


def test_add_with_the_email_second_factor_puts_the_account_in_that_group_too(pilot: StubbedPilot) -> None:
    pilot.expect(
        "admin_create_user",
        {"Username": "debater.two", "TemporaryPassword": ANY, "MessageAction": "SUPPRESS"},
        {"User": {"Username": "debater.two", "Attributes": [{"Name": "sub", "Value": SUBJECT}]}},
    )
    pilot.expect("admin_add_user_to_group", {"Username": "debater.two", "GroupName": "student"})
    pilot.expect("admin_add_user_to_group", {"Username": "debater.two", "GroupName": "email-second-factor"})
    pilot.expect_audit()

    result = tub_users("add", "debater.two", "--email-second-factor", "--env", "dev")

    assert result.exit_code == ExitCode.OK, result.output
    pilot.assert_done()


def test_add_as_a_coach_and_in_json_shows_the_password_only_in_the_result(pilot: StubbedPilot) -> None:
    pilot.expect(
        "admin_create_user",
        {"Username": "coach.two", "TemporaryPassword": ANY, "MessageAction": "SUPPRESS"},
        {"User": {"Username": "coach.two", "Attributes": [{"Name": "sub", "Value": SUBJECT}]}},
    )
    pilot.expect("admin_add_user_to_group", {"Username": "coach.two", "GroupName": "coach"})
    pilot.expect_audit()

    result = tub_users("add", "coach.two", "--role", "coach", "--env", "dev", json_output=True, verbose=True)

    envelope = json.loads(result.stdout)
    sent_password = pilot.sent_value("AdminCreateUser", "TemporaryPassword")
    assert envelope["data"] == {"username": "coach.two", "role": "coach", "temporary_password": sent_password}
    assert result.stdout.count(sent_password) == 1
    assert sent_password not in result.stderr


def test_add_uses_the_environments_accounts_profile_and_audit_group(pilot: StubbedPilot) -> None:
    pilot.expect(
        "admin_create_user",
        {"Username": "debater.one", "TemporaryPassword": ANY, "MessageAction": "SUPPRESS"},
        {"User": {"Username": "debater.one", "Attributes": [{"Name": "sub", "Value": SUBJECT}]}},
    )
    pilot.expect("admin_add_user_to_group", {"Username": "debater.one", "GroupName": "student"})
    pilot.expect_audit(group="debate-prod-tub-audit")

    result = tub_users("add", "debater.one", "--env", "prod")

    assert result.exit_code == ExitCode.OK, result.output
    assert pilot.profiles == ["debate-prod-tub-accounts", "debate-prod-tub-accounts"]


def test_an_account_that_exists_already_is_refused_with_no_password_shown(pilot: StubbedPilot) -> None:
    pilot.users.add_client_error(
        "admin_create_user",
        "UsernameExistsException",
        expected_params={
            "UserPoolId": POOL,
            "Username": "debater.one",
            "TemporaryPassword": ANY,
            "MessageAction": "SUPPRESS",
        },
    )

    result = tub_users("add", "debater.one", "--env", "dev", verbose=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "already exists" in result.output
    assert passwords_in(result.output) == []
    assert pilot.audit_records() == []


def test_a_failed_audit_write_reports_the_failure_and_shows_no_password(pilot: StubbedPilot) -> None:
    pilot.expect(
        "admin_create_user",
        {"Username": "debater.one", "TemporaryPassword": ANY, "MessageAction": "SUPPRESS"},
        {"User": {"Username": "debater.one", "Attributes": [{"Name": "sub", "Value": SUBJECT}]}},
    )
    pilot.expect("admin_add_user_to_group", {"Username": "debater.one", "GroupName": "student"})
    pilot.audit_log.add_client_error("put_log_events", "AccessDeniedException")

    result = tub_users("add", "debater.one", "--env", "dev", json_output=True, verbose=True)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    assert json.loads(result.stdout)["error"]["code"] == "STORE_ACCESS_DENIED"
    assert passwords_in(result.output) == []


# --------------------------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------------------------


def test_list_shows_usernames_and_roles_only(pilot: StubbedPilot) -> None:
    for group, members in [
        ("coach", ["coach.one"]),
        ("student", ["debater.one", "debater.two"]),
        ("email-second-factor", ["debater.two"]),
    ]:
        pilot.expect(
            "list_users_in_group",
            {"GroupName": group},
            {
                "Users": [
                    {"Username": name, "Attributes": [{"Name": "email", "Value": f"{name}@example.test"}]}
                    for name in members
                ]
            },
        )
    pilot.expect(
        "list_users",
        {"AttributesToGet": ["sub"]},
        {"Users": [{"Username": "debater.two"}, {"Username": "coach.one"}], "PaginationToken": "page-2"},
    )
    pilot.expect(
        "list_users",
        {"AttributesToGet": ["sub"], "PaginationToken": "page-2"},
        {"Users": [{"Username": "debater.one"}, {"Username": "left.over"}]},
    )
    pilot.expect_audit()

    result = tub_users("list", "--env", "dev", json_output=True)

    assert result.exit_code == ExitCode.OK, result.output
    assert json.loads(result.stdout)["data"] == {
        "accounts": [
            {"username": "coach.one", "role": "coach"},
            {"username": "debater.one", "role": "student"},
            {"username": "debater.two", "role": "student"},
            {"username": "left.over", "role": "none"},
        ]
    }
    assert "@example.test" not in result.output
    [record] = pilot.audit_records()
    assert record["action"] == "accounts-listed" and record["count"] == 4
    pilot.assert_done()


# --------------------------------------------------------------------------------------------
# reset, disable, enable, remove, email-second-factor
# --------------------------------------------------------------------------------------------


def test_reset_sets_a_temporary_password_removes_the_authenticator_and_signs_out(pilot: StubbedPilot) -> None:
    pilot.expect_account("debater.one")
    pilot.expect("admin_set_user_password", {"Username": "debater.one", "Password": ANY, "Permanent": False})
    pilot.expect(
        "admin_get_user",
        {"Username": "debater.one"},
        {"Username": "debater.one", "UserMFASettingList": ["SOFTWARE_TOKEN_MFA"]},
    )
    pilot.expect("admin_delete_software_token", {"Username": "debater.one"})
    pilot.expect("admin_user_global_sign_out", {"Username": "debater.one"})
    pilot.expect_audit()

    result = tub_users("reset", "debater.one", "--env", "dev")

    assert result.exit_code == ExitCode.OK, result.output
    sent_password = pilot.sent_value("AdminSetUserPassword", "Password")
    assert result.stdout.count(sent_password) == 1
    assert pilot.audit_records()[0]["action"] == "account-reset"
    pilot.assert_done()


def test_reset_of_an_account_that_never_enrolled_skips_the_authenticator(pilot: StubbedPilot) -> None:
    pilot.expect_account("debater.one")
    pilot.expect("admin_set_user_password", {"Username": "debater.one", "Password": ANY, "Permanent": False})
    pilot.expect(
        "admin_get_user", {"Username": "debater.one"}, {"Username": "debater.one", "UserMFASettingList": []}
    )
    pilot.expect("admin_user_global_sign_out", {"Username": "debater.one"})
    pilot.expect_audit()

    result = tub_users("reset", "debater.one", "--env", "dev")

    assert result.exit_code == ExitCode.OK, result.output
    pilot.assert_done()


def test_disable_signs_out_everywhere_then_disables(pilot: StubbedPilot) -> None:
    pilot.expect_account("debater.one")
    pilot.expect("admin_user_global_sign_out", {"Username": "debater.one"})
    pilot.expect("admin_disable_user", {"Username": "debater.one"})
    pilot.expect_audit()

    result = tub_users("disable", "debater.one", "--env", "dev")

    assert result.exit_code == ExitCode.OK, result.output
    assert "within five minutes" in result.stdout
    assert pilot.audit_records()[0] == {
        **pilot.audit_records()[0],
        "action": "account-disabled",
        "account_subject": SUBJECT,
    }
    pilot.assert_done()


def test_enable_enables(pilot: StubbedPilot) -> None:
    pilot.expect_account("debater.one")
    pilot.expect("admin_enable_user", {"Username": "debater.one"})
    pilot.expect_audit()

    assert tub_users("enable", "debater.one", "--env", "dev").exit_code == ExitCode.OK
    pilot.assert_done()


def test_remove_signs_out_everywhere_then_deletes(pilot: StubbedPilot) -> None:
    pilot.expect_account("debater.one")
    pilot.expect("admin_user_global_sign_out", {"Username": "debater.one"})
    pilot.expect("admin_delete_user", {"Username": "debater.one"})
    pilot.expect_audit()

    result = tub_users("remove", "debater.one", "--env", "dev")

    assert result.exit_code == ExitCode.OK, result.output
    assert pilot.audit_records()[0]["action"] == "account-removed"
    pilot.assert_done()


@pytest.mark.parametrize(
    ("flag", "operation", "action"),
    [
        ("--allow", "admin_add_user_to_group", "email-second-factor-allowed"),
        ("--withdraw", "admin_remove_user_from_group", "email-second-factor-withdrawn"),
    ],
)
def test_email_second_factor_puts_the_account_in_or_out_of_the_group(
    pilot: StubbedPilot, flag: str, operation: str, action: str
) -> None:
    pilot.expect_account("debater.two")
    pilot.expect(operation, {"Username": "debater.two", "GroupName": "email-second-factor"})
    pilot.expect_audit()

    result = tub_users("email-second-factor", "debater.two", flag, "--env", "dev")

    assert result.exit_code == ExitCode.OK, result.output
    assert pilot.audit_records()[0]["action"] == action
    pilot.assert_done()


@pytest.mark.parametrize(
    "command",
    [["disable"], ["enable"], ["remove"], ["email-second-factor", "--allow"], ["list"]],
)
def test_no_other_command_shows_a_password(pilot: StubbedPilot, command: list[str]) -> None:
    if command == ["list"]:
        for group in ("coach", "student", "email-second-factor"):
            pilot.expect("list_users_in_group", {"GroupName": group}, {"Users": []})
        pilot.expect("list_users", {"AttributesToGet": ["sub"]}, {"Users": []})
        pilot.expect_audit()
        result = tub_users("list", "--env", "dev", verbose=True)
    else:
        pilot.expect_account("debater.one")
        follow_on = {
            "disable": [("admin_user_global_sign_out", {}), ("admin_disable_user", {})],
            "enable": [("admin_enable_user", {})],
            "remove": [("admin_user_global_sign_out", {}), ("admin_delete_user", {})],
            "email-second-factor": [("admin_add_user_to_group", {"GroupName": "email-second-factor"})],
        }[command[0]]
        for operation, extra in follow_on:
            pilot.expect(operation, {"Username": "debater.one", **extra})
        pilot.expect_audit()
        result = tub_users(command[0], "debater.one", *command[1:], "--env", "dev", verbose=True)

    assert result.exit_code == ExitCode.OK, result.output
    assert passwords_in(result.output) == []
    pilot.assert_done()


def test_an_account_that_does_not_exist_is_reported(pilot: StubbedPilot) -> None:
    pilot.users.add_client_error(
        "admin_get_user",
        "UserNotFoundException",
        expected_params={"UserPoolId": POOL, "Username": "nobody.here"},
    )

    result = tub_users("reset", "nobody.here", "--env", "dev", json_output=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert json.loads(result.stdout)["error"]["code"] == "NOT_FOUND"
    assert passwords_in(result.output) == []


def test_an_expired_sso_session_says_how_to_sign_in(pilot: StubbedPilot) -> None:
    pilot.users.add_client_error("admin_get_user", "ExpiredTokenException")

    result = tub_users("disable", "debater.one", "--env", "dev", json_output=True)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    assert json.loads(result.stdout)["error"]["hint"] == "aws sso login --profile debate-dev-tub-accounts"


# --------------------------------------------------------------------------------------------
# Usernames
# --------------------------------------------------------------------------------------------

NOT_USERNAMES = [
    "debater.one@example.test",
    "debater@school",
    "Debater.One",
    "ab",
    "a" * 33,
    "debater_one",
    "debater-one",
    "debater one",
    "",
]


@pytest.mark.parametrize("username", NOT_USERNAMES)
@pytest.mark.parametrize(
    "command", [["add"], ["reset"], ["disable"], ["enable"], ["remove"], ["email-second-factor", "--allow"]]
)
def test_a_name_that_is_not_a_username_is_refused_before_the_pool_is_asked(
    pilot: StubbedPilot, username: str, command: list[str]
) -> None:
    result = tub_users(command[0], username, *command[1:], "--env", "dev", json_output=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "INVALID_USERNAME"
    assert pilot.sent == []
    if "@" in username:
        assert error["message"] == "not a username: a username is never an email address"


@pytest.mark.parametrize("username", ["abc", "debater.one", "a" * 32, "2027.class.debater"])
def test_lowercase_letters_digits_and_dots_are_usernames(pilot: StubbedPilot, username: str) -> None:
    pilot.expect_account(username)
    pilot.expect("admin_enable_user", {"Username": username})
    pilot.expect_audit()

    assert tub_users("enable", username, "--env", "dev").exit_code == ExitCode.OK


def test_nothing_the_commands_do_is_logged(pilot: StubbedPilot, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    pilot.expect(
        "admin_create_user",
        {"Username": "debater.one", "TemporaryPassword": ANY, "MessageAction": "SUPPRESS"},
        {"User": {"Username": "debater.one", "Attributes": [{"Name": "sub", "Value": SUBJECT}]}},
    )
    pilot.expect("admin_add_user_to_group", {"Username": "debater.one", "GroupName": "student"})
    pilot.expect_audit()

    tub_users("add", "debater.one", "--env", "dev", verbose=True)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert pilot.sent_value("AdminCreateUser", "TemporaryPassword") not in logged

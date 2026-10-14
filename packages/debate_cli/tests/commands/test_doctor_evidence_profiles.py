"""`debate-research doctor --evidence-profiles`: each evidence profile, checked before a run meets it.

`v1-e34-t22`. A profile setting that names a profile this machine's AWS config does not define
stops every command that reaches the bucket before it starts, the weekly pull among them
(`v1-e29-t07`). With `--evidence-profiles`, `doctor` reports for each configured evidence profile,
the environment's everyday one and `DEBATE_REMOVAL_PROFILE` when it is set, whether it is defined
and which permission set it is signed in as, and fails on one that is not defined. An expired
session is reported as expired and does not fail it.

Plain `doctor` does none of this, and that is deliberate: `scripts/install_channel.sh` runs plain
`doctor` on every install and so does `validate-dev`, on machines with no AWS config at all, and a
`doctor` that failed there for want of an operator's profile would refuse every build.

Three kinds of test, and none reads a real AWS config or reaches a network:

* **The identity stubbed at the port** (`CallerIdentity`, `v1-e29-t08`): what `doctor` does with
  each answer about who a profile is.
* **boto3 refusing a real session**, against an AWS config written for the test: how a profile that
  is not defined is met, through the real composition root and the real adapter.
* **The real STS adapter on moto**, with each profile signed in as a role named the way the
  account names a permission set's: what leaves the adapter, and that none of it is an account id
  or a role's full identifier.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from botocore.client import BaseClient
from botocore.exceptions import UnauthorizedSSOTokenError
from moto import mock_aws
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import StoreCredentialsExpired, StoreUnavailable

runner = CliRunner()

BUCKET = "debate-dev-evidence-doctor-moto"
EVERYDAY_PROFILE = "debate-dev-evidence"
TAKEDOWN_PROFILE = "debate-dev-evidence-removal"
MISSPELT_PROFILE = "debate-dev-evidence-typo"
EVERYDAY_SETTING = "storage.s3.aws_profile"
TAKEDOWN_SETTING = "DEBATE_REMOVAL_PROFILE"
AWS_CONFIG_NAME = "an-aws-config-written-for-this-test"

THE_ADAPTERS_FIX = (
    "set {setting} to a profile this machine's AWS config defines, or add the profile to it: "
    "docs/runbooks/evidence-store.md lists the evidence profiles and how they are added. It is not an "
    "expired session, and logging in changes nothing"
)
"""The hint the S3 adapter writes for a profile the AWS config lacks (`v1-e29-t07`), by hand."""

AN_ACCOUNT_OR_AN_ADDRESS = re.compile(r"\b\d{12}\b|arn:|https?://|awsapps\.com|AWSReservedSSO")
"""An account id, a role's full identifier or its own name, or an address a session starts at."""


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming a bucket and the everyday profile, and an AWS config defining both
    evidence profiles. `DEBATE_REMOVAL_PROFILE` is unset, as it is in every profile."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / AWS_CONFIG_NAME
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (EVERYDAY_PROFILE, TAKEDOWN_PROFILE)),
        encoding="utf-8",
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for name in (EVERYDAY_PROFILE, TAKEDOWN_PROFILE)
        ),
        encoding="utf-8",
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{EVERYDAY_PROFILE}"\n'
        f'[caselist]\nnotifier = "none"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield tmp_path


class SignedInAs:
    """The caller-identity port answering with a role's name, or `None` for no role."""

    def __init__(self, role_name: str | None) -> None:
        self.role_name = role_name

    async def assumed_role_name(self) -> str | None:
        return self.role_name


class CannotBeAsked:
    """The port raising what its adapter raises for a credential that cannot be asked."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def assumed_role_name(self) -> str | None:
        raise self.error


def who_each_profile_is(monkeypatch: pytest.MonkeyPatch, callers: dict[str, Any]) -> list[str]:
    """Stub the identity at the port, by profile name. A profile with no stub is asked for real,
    which is how a test meets one the AWS config lacks. Returns the names asked for, as they are."""
    real = getattr(ServiceContainer, "caller_identity_for", None)
    asked: list[str] = []

    def caller_identity_for(self: ServiceContainer, profile: Any) -> Any:
        asked.append(profile.name)
        if profile.name in callers:
            return callers[profile.name]
        assert real is not None
        return real(self, profile)

    monkeypatch.setattr(ServiceContainer, "caller_identity_for", caller_identity_for, raising=False)
    return asked


def doctor(*arguments: str) -> tuple[int, dict[str, Any]]:
    result: Result = runner.invoke(create_app(), ["--json", "doctor", *arguments])
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}\n{result.stderr}"
    envelope: dict[str, Any] = json.loads(lines[0])
    return result.exit_code, envelope


def profiles_in(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    report = envelope["data"] if envelope["data"] is not None else envelope["error"]["details"]
    found: list[dict[str, Any]] = report["evidence_profiles"]
    return found


def as_a_person_sees_it(*arguments: str) -> tuple[int, str]:
    """The table and any panel, on one line with the box drawn around them taken off."""
    result = runner.invoke(create_app(), ["doctor", *arguments])
    text = re.sub(r"[│┃┏┓┗┛━─┡┩╇╭╮╰╯┼┬┴├┤┌┐└┘╰╯]", " ", result.stdout + result.stderr)
    return result.exit_code, " ".join(text.split())


# ------------------------------------------------------------------------------------------------
# Plain doctor is as it was
# ------------------------------------------------------------------------------------------------


def test_plain_doctor_asks_about_no_profile_and_passes_where_the_profile_is_not_defined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What `install_channel.sh` and `validate-dev` run, on machines with no AWS config. The
    profile setting here names a profile the AWS config lacks, and plain `doctor` neither looks
    nor fails."""
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)
    asked = who_each_profile_is(monkeypatch, {})

    exit_code, envelope = doctor()

    assert exit_code == ExitCode.OK, envelope
    assert "evidence_profiles" not in envelope["data"]
    assert asked == []


# ------------------------------------------------------------------------------------------------
# ac3, with the identity stubbed at the port
# ------------------------------------------------------------------------------------------------


def test_the_everyday_profile_is_reported_as_defined_with_the_permission_set_it_is_signed_in_as(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = who_each_profile_is(monkeypatch, {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE)})

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.OK, envelope
    assert profiles_in(envelope) == [
        {
            "setting": "storage.s3.aws_profile",
            "profile": "debate-dev-evidence",
            "defined": True,
            "session": "signed_in",
            "permission_set": "DebateDevEvidenceOperator",
            "summary": "defined, and signed in as DebateDevEvidenceOperator",
            "hint": None,
        }
    ]
    assert asked == [EVERYDAY_PROFILE], "DEBATE_REMOVAL_PROFILE is unset, so no second profile is asked"


def test_the_removal_profile_is_reported_too_when_it_is_set_each_under_its_own_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", TAKEDOWN_PROFILE)
    who_each_profile_is(
        monkeypatch,
        {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE), TAKEDOWN_PROFILE: SignedInAs(TAKEDOWN_ROLE)},
    )

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.OK, envelope
    assert [
        (one["setting"], one["profile"], one["defined"], one["permission_set"])
        for one in profiles_in(envelope)
    ] == [
        ("storage.s3.aws_profile", "debate-dev-evidence", True, "DebateDevEvidenceOperator"),
        ("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal", True, "DebateDevEvidenceRemoval"),
    ]


def test_an_expired_session_is_reported_as_expired_and_does_not_fail_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expired = StoreCredentialsExpired("not usable", hint="aws sso login --profile debate-dev-evidence")
    who_each_profile_is(monkeypatch, {EVERYDAY_PROFILE: CannotBeAsked(expired)})

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.OK, envelope
    [found] = profiles_in(envelope)
    assert (found["defined"], found["session"], found["permission_set"]) == (True, "expired", None)
    assert found["hint"] == "aws sso login --profile debate-dev-evidence"


def test_an_account_that_does_not_answer_does_not_fail_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    unanswered = StoreUnavailable("GetCallerIdentity", f"s3://{BUCKET}", "timed out")
    who_each_profile_is(monkeypatch, {EVERYDAY_PROFILE: CannotBeAsked(unanswered)})

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.OK, envelope
    [found] = profiles_in(envelope)
    assert (found["defined"], found["session"]) == (True, "no_answer")


def test_a_removal_profile_signed_in_as_the_everyday_set_is_reported_and_does_not_fail_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`DEBATE_REMOVAL_PROFILE` naming the everyday profile. The takedown's preflight refuses it
    when a removal is run (`v1-e29-t08`); here it is said early, and it is not this check's failure."""
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", EVERYDAY_PROFILE)
    who_each_profile_is(monkeypatch, {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE)})

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.OK, envelope
    assert [one["summary"] for one in profiles_in(envelope)] == [
        "defined, and signed in as DebateDevEvidenceOperator",
        "defined, and signed in as DebateDevEvidenceOperator; a takedown runs only as "
        "DebateDevEvidenceRemoval, so `caselist remove --execute` will refuse this profile",
    ]


def test_an_environment_with_no_bucket_has_no_everyday_profile_to_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`test` names no bucket and no profile: nothing is configured, nothing is asked, and it passes."""
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.delenv("DEBATE_PROFILE_DIR")
    asked = who_each_profile_is(monkeypatch, {})

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.OK, envelope
    assert profiles_in(envelope) == []
    assert asked == []


# ------------------------------------------------------------------------------------------------
# ac3: a profile that is not defined, met for real
# ------------------------------------------------------------------------------------------------


def test_an_everyday_profile_the_aws_config_lacks_fails_doctor_naming_the_profile_and_its_setting(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """boto3 raises `ProfileNotFound` when the adapter builds a session for it. No stub."""
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope["error"]
    assert error["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert error["message"] == (
        "AWS profile 'debate-dev-evidence-typo', named by storage.s3.aws_profile, is not defined in "
        "this machine's AWS config, so every command that uses it will refuse to start."
    )
    assert error["hint"] == THE_ADAPTERS_FIX.format(setting=EVERYDAY_SETTING)
    assert profiles_in(envelope) == [
        {
            "setting": "storage.s3.aws_profile",
            "profile": "debate-dev-evidence-typo",
            "defined": False,
            "session": "not_defined",
            "permission_set": None,
            "summary": "not defined in this machine's AWS config",
            "hint": THE_ADAPTERS_FIX.format(setting=EVERYDAY_SETTING),
        }
    ]
    # What the profile check adds to the report. `doctor` has always reported where its interpreter
    # is, which is a path; nothing it says about a profile is one.
    about_the_profiles = json.dumps([error["message"], error["hint"], profiles_in(envelope)])
    for forbidden in (str(installation), str(Path.home()), AWS_CONFIG_NAME, "/.aws", "aws sso login"):
        assert forbidden not in about_the_profiles
    assert AWS_CONFIG_NAME not in json.dumps(envelope), "nowhere in the envelope either"


def test_a_removal_profile_the_aws_config_lacks_fails_doctor_naming_its_own_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The everyday profile is fine and is still reported; the failure names the variable."""
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", MISSPELT_PROFILE)
    who_each_profile_is(monkeypatch, {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE)})

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert envelope["error"]["message"] == (
        "AWS profile 'debate-dev-evidence-typo', named by DEBATE_REMOVAL_PROFILE, is not defined in "
        "this machine's AWS config, so every command that uses it will refuse to start."
    )
    assert envelope["error"]["hint"] == THE_ADAPTERS_FIX.format(setting=TAKEDOWN_SETTING)
    assert [(one["profile"], one["defined"], one["permission_set"]) for one in profiles_in(envelope)] == [
        ("debate-dev-evidence", True, "DebateDevEvidenceOperator"),
        ("debate-dev-evidence-typo", False, None),
    ]


def test_two_profiles_that_are_not_defined_are_both_named_with_each_ones_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal-typo")

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["message"] == (
        "AWS profile 'debate-dev-evidence-typo', named by storage.s3.aws_profile, and AWS profile "
        "'debate-dev-evidence-removal-typo', named by DEBATE_REMOVAL_PROFILE, are not defined in "
        "this machine's AWS config, so every command that uses them will refuse to start."
    )
    assert envelope["error"]["hint"] == (
        THE_ADAPTERS_FIX.format(setting=EVERYDAY_SETTING)
        + ". "
        + THE_ADAPTERS_FIX.format(setting=TAKEDOWN_SETTING)
    )


def test_a_profile_that_is_not_defined_and_another_failed_check_are_reported_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`doctor` reports every check it fails on, as it does for its other two."""
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)
    monkeypatch.setattr(unicodedata, "unidata_version", "1.0.0")

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "INSTALLATION_CHECKS_FAILED"
    assert "Unicode database is 1.0.0" in envelope["error"]["message"]
    assert "named by storage.s3.aws_profile, is not defined" in envelope["error"]["message"]


# ------------------------------------------------------------------------------------------------
# The real adapter: what botocore and STS answer
# ------------------------------------------------------------------------------------------------


def test_an_expired_sso_session_met_by_the_real_adapter_is_reported_with_the_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """botocore raises the SSO token error before any request is signed; the adapter translates it."""

    def expired(self: BaseClient, operation_name: str, api_params: dict[str, Any]) -> Any:
        raise UnauthorizedSSOTokenError()

    monkeypatch.setattr(BaseClient, "_make_api_call", expired)

    exit_code, envelope = doctor("--evidence-profiles")

    assert exit_code == ExitCode.OK, envelope
    [found] = profiles_in(envelope)
    assert (found["defined"], found["session"]) == (True, "expired")
    assert found["hint"] == "aws sso login --profile debate-dev-evidence"


def test_through_the_real_sts_adapter_each_profile_is_named_by_its_permission_set_and_nothing_else(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """moto answers `GetCallerIdentity` in the shape AWS does, account and full identifier
    included. What `doctor` shows of that answer is the permission set's name."""
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", TAKEDOWN_PROFILE)
    with mock_aws():
        sign_in(
            installation / "aws-credentials",
            {EVERYDAY_PROFILE: EVERYDAY_ROLE, TAKEDOWN_PROFILE: TAKEDOWN_ROLE},
        )

        exit_code, envelope = doctor("--evidence-profiles")
        shown_exit, shown = as_a_person_sees_it("--evidence-profiles")

    assert exit_code == shown_exit == ExitCode.OK, envelope
    assert [(one["profile"], one["permission_set"]) for one in profiles_in(envelope)] == [
        ("debate-dev-evidence", "DebateDevEvidenceOperator"),
        ("debate-dev-evidence-removal", "DebateDevEvidenceRemoval"),
    ]
    for said in (json.dumps(profiles_in(envelope)), shown):
        assert AN_ACCOUNT_OR_AN_ADDRESS.search(said) is None, said
        assert AWS_CONFIG_NAME not in said and "/.aws" not in said


# ------------------------------------------------------------------------------------------------
# For a person
# ------------------------------------------------------------------------------------------------


def test_a_person_sees_one_row_for_each_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", TAKEDOWN_PROFILE)
    expired = StoreCredentialsExpired(
        "not usable", hint="aws sso login --profile debate-dev-evidence-removal"
    )
    who_each_profile_is(
        monkeypatch,
        {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE), TAKEDOWN_PROFILE: CannotBeAsked(expired)},
    )

    exit_code, shown = as_a_person_sees_it("--evidence-profiles")

    assert exit_code == ExitCode.OK, shown
    assert (
        "Evidence profile debate-dev-evidence (storage.s3.aws_profile): defined, and signed in as "
        "DebateDevEvidenceOperator"
    ) in shown
    assert (
        "Evidence profile debate-dev-evidence-removal (DEBATE_REMOVAL_PROFILE): defined; its session "
        "has expired or was never started, so AWS cannot be asked which permission set it is (aws sso "
        "login --profile debate-dev-evidence-removal)"
    ) in shown


def test_a_person_sees_the_report_and_then_the_profile_that_is_not_defined(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)

    exit_code, shown = as_a_person_sees_it("--evidence-profiles")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert (
        "Evidence profile debate-dev-evidence-typo (storage.s3.aws_profile): not defined in this "
        "machine's AWS config"
    ) in shown
    assert "(set storage.s3.aws_profile" not in shown, "the fix is the panel's, not the row's"
    assert "STORE_PROFILE_NOT_CONFIGURED" in shown
    assert "named by storage.s3.aws_profile, is not defined" in shown
    for forbidden in (str(installation), AWS_CONFIG_NAME, "/.aws"):
        assert forbidden not in shown


def test_with_nothing_configured_a_person_is_told_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.delenv("DEBATE_PROFILE_DIR")

    exit_code, shown = as_a_person_sees_it("--evidence-profiles")

    assert exit_code == ExitCode.OK, shown
    assert "Evidence profiles none configured for this environment" in shown

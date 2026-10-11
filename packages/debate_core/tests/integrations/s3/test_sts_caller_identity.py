"""Who a credential is signed in as, asked of moto's STS through the real adapter (`v1-e29-t08`).

The takedown preflight compares a role's name with the role a takedown runs as, so what this
adapter has to get right is small and exact: the name of the assumed role, taken out of what STS
answers, and nothing else of that answer. moto answers `GetCallerIdentity` in the shape AWS does, so
the identifiers here are the ones moto made up, read back from its own responses; this file writes
down no account and no role's full identifier, real or invented.

What moto cannot show is that AWS names an Identity Center role the way these tests name theirs.
That is read from the runbook's own check (`docs/runbooks/evidence-store.md`, step 4), not proven
here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.exceptions import UnauthorizedSSOTokenError
from moto import mock_aws

from debate_core.application.errors import StoreCredentialsExpired, StoreProfileNotConfigured
from debate_core.application.ports.caller_identity import CallerIdentity
from debate_core.integrations.s3 import StsCallerIdentity, build_sts_client

pytestmark = pytest.mark.anyio

TAKEDOWN_ROLE = "AWSReservedSSO_DebateDevEvidenceRemoval_0123456789abcdef"
TAKEDOWN_PROFILE = "debate-dev-evidence-removal"
TAKEDOWN_SETTING = "DEBATE_REMOVAL_PROFILE"
BUCKET = "debate-test-evidence-moto"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def moto_account(fake_aws_credentials: None) -> Iterator[None]:
    with mock_aws():
        yield


def moto_client(service: str, **credentials: str) -> Any:
    """A client onto moto's `service`. boto3's types cover `s3` alone here, so this one is `Any`."""
    untyped: Any = boto3
    return untyped.client(service, region_name="us-east-1", **credentials)


def assume(role_name: str, *, path: str = "/") -> dict[str, str]:
    """Create `role_name` in moto and assume it; the temporary credentials, as boto3 names them."""
    role = moto_client("iam").create_role(
        RoleName=role_name,
        Path=path,
        AssumeRolePolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": []}),
    )["Role"]
    issued = moto_client("sts").assume_role(RoleArn=role["Arn"], RoleSessionName="an-operator")["Credentials"]
    return {
        "aws_access_key_id": issued["AccessKeyId"],
        "aws_secret_access_key": issued["SecretAccessKey"],
        "aws_session_token": issued["SessionToken"],
    }


class TestTheRoleACredentialIsSignedInAs:
    async def test_an_assumed_role_is_named_by_its_role_name_alone(self, moto_account: None) -> None:
        caller = StsCallerIdentity(bucket=BUCKET, client=moto_client("sts", **assume(TAKEDOWN_ROLE)))

        assert isinstance(caller, CallerIdentity)
        assert await caller.assumed_role_name() == TAKEDOWN_ROLE

    async def test_a_role_under_a_path_is_named_without_the_path(self, moto_account: None) -> None:
        """Identity Center keeps its roles under a path; the name a session carries has none."""
        credentials = assume(TAKEDOWN_ROLE, path="/aws-reserved/sso.amazonaws.com/")

        caller = StsCallerIdentity(bucket=BUCKET, client=moto_client("sts", **credentials))

        assert await caller.assumed_role_name() == TAKEDOWN_ROLE

    async def test_a_credential_that_is_not_a_role_has_no_role_name(self, moto_account: None) -> None:
        """What moto answers a key it did not issue: a user. An answer, not an error."""
        caller = StsCallerIdentity(bucket=BUCKET, client=moto_client("sts"))

        assert await caller.assumed_role_name() is None

    async def test_a_user_with_its_own_key_has_no_role_name(self, moto_account: None) -> None:
        iam = moto_client("iam")
        iam.create_user(UserName="assumed-role")
        key = iam.create_access_key(UserName="assumed-role")["AccessKey"]
        client = moto_client(
            "sts", aws_access_key_id=key["AccessKeyId"], aws_secret_access_key=key["SecretAccessKey"]
        )

        assert await StsCallerIdentity(bucket=BUCKET, client=client).assumed_role_name() is None


class _Answers:
    """A client that answers `GetCallerIdentity` with one fixed identifier, or raises."""

    def __init__(self, answer: object) -> None:
        self._answer = answer

    def get_caller_identity(self) -> dict[str, Any]:
        if isinstance(self._answer, BaseException):
            raise self._answer
        return {"Arn": self._answer} if self._answer is not None else {}


class TestWhatIsReadOutOfTheAnswer:
    """Identifiers written with a word where the account goes: the adapter must not care what is there."""

    @pytest.mark.parametrize(
        ("identifier", "role_name"),
        [
            (f"arn:aws:sts::ACCOUNT:assumed-role/{TAKEDOWN_ROLE}/an-operator", TAKEDOWN_ROLE),
            (f"arn:aws-us-gov:sts::ACCOUNT:assumed-role/{TAKEDOWN_ROLE}/an-operator", TAKEDOWN_ROLE),
            # A session name may hold a slash-free address; whatever it is, it is not the role.
            (f"arn:aws:sts::ACCOUNT:assumed-role/{TAKEDOWN_ROLE}/someone@example.org", TAKEDOWN_ROLE),
            ("arn:aws:iam::ACCOUNT:user/assumed-role", None),
            (f"arn:aws:iam::ACCOUNT:user/assumed-role/{TAKEDOWN_ROLE}/x", None),
            ("arn:aws:iam::ACCOUNT:root", None),
            (f"arn:aws:sts::ACCOUNT:federated-user/{TAKEDOWN_ROLE}", None),
            (f"arn:aws:iam::ACCOUNT:role/{TAKEDOWN_ROLE}", None),
            (f"arn:aws:sts::ACCOUNT:assumed-role/{TAKEDOWN_ROLE}", None),
            ("", None),
            (None, None),
        ],
    )
    async def test_only_an_assumed_role_yields_a_name(
        self, identifier: str | None, role_name: str | None
    ) -> None:
        caller = StsCallerIdentity(bucket=BUCKET, client=_Answers(identifier))

        assert await caller.assumed_role_name() == role_name


class TestACredentialThatCannotBeAsked:
    async def test_an_expired_session_is_reported_with_the_login_for_its_profile(self) -> None:
        caller = StsCallerIdentity(
            bucket=BUCKET,
            profile=TAKEDOWN_PROFILE,
            profile_setting=TAKEDOWN_SETTING,
            client=_Answers(UnauthorizedSSOTokenError()),
        )

        with pytest.raises(StoreCredentialsExpired) as expired:
            await caller.assumed_role_name()

        assert expired.value.hint == f"aws sso login --profile {TAKEDOWN_PROFILE}"
        assert f"s3://{BUCKET}" in str(expired.value)

    def test_a_profile_the_config_lacks_is_a_configuration_error_naming_its_setting(
        self, fake_aws_credentials: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config = tmp_path / "an-aws-config-written-for-this-test"
        config.write_text("[profile debate-dev-evidence]\nregion = us-east-1\n", encoding="utf-8")
        monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials-file"))

        with pytest.raises(StoreProfileNotConfigured) as refused:
            build_sts_client(region="us-east-1", profile=TAKEDOWN_PROFILE, profile_setting=TAKEDOWN_SETTING)

        assert refused.value.setting == TAKEDOWN_SETTING
        assert str(tmp_path) not in str(refused.value)

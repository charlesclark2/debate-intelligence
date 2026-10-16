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
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.exceptions import UnauthorizedSSOTokenError
from moto import mock_aws

from debate_core.application.errors import (
    StoreCredentialsExpired,
    StoreProfileNotConfigured,
    StoreUnavailable,
)
from debate_core.application.evidence_profiles import ConfiguredProfile, EvidenceProfileCheck
from debate_core.application.ports.caller_identity import CallerIdentity
from debate_core.integrations.s3 import StsCallerIdentity, build_sts_client
from debate_core.integrations.s3.caller_identity import IDENTITY_TIME_LIMIT_SECONDS

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


class TestAnAdapterBuiltFromAProfile:
    async def test_it_answers_for_the_role_that_profile_is_signed_in_as(
        self, moto_account: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """As the composition root builds it: a profile's name and no client. Two profiles in one
        AWS config, signed in as two roles, and each adapter answers for its own."""
        everyday_role = "AWSReservedSSO_DebateDevEvidenceOperator_fedcba9876543210"
        profiles = {"debate-dev-evidence": everyday_role, TAKEDOWN_PROFILE: TAKEDOWN_ROLE}
        config = tmp_path / "an-aws-config-written-for-this-test"
        config.write_text("".join(f"[profile {name}]\nregion = us-east-1\n" for name in profiles))
        credentials = tmp_path / "credentials-written-for-this-test"
        credentials.write_text(
            "".join(
                f"[{name}]\n" + "".join(f"{key} = {value}\n" for key, value in assume(role).items())
                for name, role in profiles.items()
            )
        )
        monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials))

        answered = {
            name: await StsCallerIdentity(
                bucket=BUCKET, profile=name, profile_setting=TAKEDOWN_SETTING, region="us-east-1"
            ).assumed_role_name()
            for name in profiles
        }

        assert answered == profiles


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


# ------------------------------------------------------------------------------------------------
# An account that does not answer (`v1-e29-t09` ac6)
# ------------------------------------------------------------------------------------------------

CHECK_LAUNCHD_GIVES_UP_AFTER_SECONDS = 60
"""How long `ops/launchd/install.sh --check-launchd` waits for the agent's check, which runs
`doctor --evidence-profiles`, before it reports that the check never finished."""

PROFILES_DOCTOR_ASKS_ABOUT = 2
"""The everyday profile, and the takedown profile when `DEBATE_REMOVAL_PROFILE` is set: asked one
after the other."""


class _NeverAnswers:
    """A client whose `GetCallerIdentity` hangs, as one does when packets to AWS are dropped."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.asked = 0

    def get_caller_identity(self) -> dict[str, Any]:
        self.asked += 1
        self.release.wait(timeout=30)
        return {}


@pytest.fixture
def never_answers() -> Iterator[_NeverAnswers]:
    client = _NeverAnswers()
    yield client
    client.release.set()


class TestAnAccountThatDoesNotAnswer:
    async def test_the_question_gives_up_after_its_own_time_limit_and_says_aws_did_not_answer(
        self, never_answers: _NeverAnswers
    ) -> None:
        caller = StsCallerIdentity(
            bucket=BUCKET, profile=TAKEDOWN_PROFILE, client=never_answers, time_limit_seconds=0.2
        )
        started = time.monotonic()

        with pytest.raises(StoreUnavailable) as unanswered:
            await caller.assumed_role_name()

        assert time.monotonic() - started < 2, "gave up at its own limit, not when the client did"
        assert never_answers.asked == 1
        assert unanswered.value.operation == "GetCallerIdentity"
        assert str(unanswered.value) == (
            f"GetCallerIdentity on s3://{BUCKET} failed: AWS did not answer within 0.2 seconds"
        )

    async def test_the_profile_check_reports_no_answer_for_it_and_asks_the_next_profile(
        self, never_answers: _NeverAnswers
    ) -> None:
        """What `doctor --evidence-profiles` prints for each profile, through the real adapter."""
        profiles = [
            ConfiguredProfile(setting="storage.s3.aws_profile", name="debate-dev-evidence"),
            ConfiguredProfile(setting=TAKEDOWN_SETTING, name=TAKEDOWN_PROFILE, for_takedowns=True),
        ]

        def caller_for(profile: ConfiguredProfile) -> CallerIdentity:
            return StsCallerIdentity(
                bucket=BUCKET, profile=profile.name, client=never_answers, time_limit_seconds=0.2
            )

        started = time.monotonic()
        found = await EvidenceProfileCheck(profiles=profiles, caller_for=caller_for, environment="dev").run()

        assert time.monotonic() - started < 3
        assert never_answers.asked == 2
        assert [(one.session.value, one.defined) for one in found] == [
            ("no_answer", True),
            ("no_answer", True),
        ]
        assert {one.summary for one in found} == {
            "defined; AWS did not answer when asked which permission set it is signed in as"
        }

    def test_the_default_limit_for_every_profile_asked_is_well_inside_check_launchds_wait(self) -> None:
        """Both profiles unanswered take at most a third of the 60 seconds, leaving the rest for
        the build's other checks and for starting the command under launchd."""
        assert (
            IDENTITY_TIME_LIMIT_SECONDS * PROFILES_DOCTOR_ASKS_ABOUT
            <= CHECK_LAUNCHD_GIVES_UP_AFTER_SECONDS / 3
        )

    def test_the_limit_is_what_check_launchd_waits_for_against_install_sh(self) -> None:
        """If `install.sh` shortens its wait, this fails and the limit is looked at again."""
        install = Path(__file__).parents[5] / "ops" / "launchd" / "install.sh"
        assert f'if [ "${{waited}}" -gt {CHECK_LAUNCHD_GIVES_UP_AFTER_SECONDS} ]; then' in install.read_text(
            encoding="utf-8"
        )

    async def test_an_answer_inside_the_limit_is_the_answer(self) -> None:
        arn = f"arn:aws:sts::ACCOUNT:assumed-role/{TAKEDOWN_ROLE}/an-operator"
        caller = StsCallerIdentity(bucket=BUCKET, client=_Answers(arn), time_limit_seconds=5)

        assert await caller.assumed_role_name() == TAKEDOWN_ROLE

    async def test_a_failure_inside_the_limit_is_translated_as_before(self) -> None:
        caller = StsCallerIdentity(
            bucket=BUCKET,
            profile=TAKEDOWN_PROFILE,
            client=_Answers(UnauthorizedSSOTokenError()),
            time_limit_seconds=5,
        )

        with pytest.raises(StoreCredentialsExpired):
            await caller.assumed_role_name()

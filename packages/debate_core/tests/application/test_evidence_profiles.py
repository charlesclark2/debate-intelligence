"""Each configured evidence profile: is it defined, and which permission set is it signed in as?

`v1-e34-t22`. A profile setting that names a profile this machine's AWS config does not define
stops every command that reaches the bucket, the weekly pull among them, and it is found here
before a scheduled run meets it: `debate-research doctor --evidence-profiles` and
`ops/launchd/install.sh --check-launchd` both run this check.

The check asks through the caller-identity port `v1-e29-t08` added, and every answer in these
tests is stubbed at that port: a role's name, or the error the port raises when a credential
cannot be asked. The AWS adapter behind the port, on moto, is the CLI's test. Each expected
sentence is written out by hand.

The module under test is new, so it is looked up when a test runs: against a source without it
every test here fails by itself.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from debate_core.application import errors
from debate_core.application.caselist.removal_service import takedown_permission_set

pytestmark = pytest.mark.anyio

EVERYDAY_SETTING = "storage.s3.aws_profile"
TAKEDOWN_SETTING = "DEBATE_REMOVAL_PROFILE"
EVERYDAY_PROFILE = "debate-dev-evidence"
TAKEDOWN_PROFILE = "debate-dev-evidence-removal"

EVERYDAY_ROLE = "AWSReservedSSO_DebateDevEvidenceOperator_fedcba9876543210"
TAKEDOWN_ROLE = "AWSReservedSSO_DebateDevEvidenceRemoval_0123456789abcdef"
"""Two roles named the way the account names a permission set's, with made-up suffixes."""

LOGIN = "aws sso login --profile debate-dev-evidence"
THE_ADAPTERS_FIX = (
    "set storage.s3.aws_profile to a profile this machine's AWS config defines, or add the profile to "
    "it: docs/runbooks/evidence-store.md lists the evidence profiles and how they are added. It is "
    "not an expired session, and logging in changes nothing"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def module() -> Any:
    return importlib.import_module("debate_core.application.evidence_profiles")


def everyday(name: str = EVERYDAY_PROFILE) -> Any:
    return module().ConfiguredProfile(setting=EVERYDAY_SETTING, name=name)


def takedown(name: str = TAKEDOWN_PROFILE) -> Any:
    return module().ConfiguredProfile(setting=TAKEDOWN_SETTING, name=name, for_takedowns=True)


class SignedInAs:
    """The port answering with a role's name, or `None` for a credential that is no role."""

    def __init__(self, role_name: str | None) -> None:
        self.role_name = role_name
        self.asked = 0

    async def assumed_role_name(self) -> str | None:
        self.asked += 1
        return self.role_name


class CannotBeAsked:
    """The port raising what its adapter raises for a credential that cannot be asked."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def assumed_role_name(self) -> str | None:
        raise self.error


def not_defined(profile: str, setting: str) -> errors.StoreProfileNotConfigured:
    return errors.StoreProfileNotConfigured(profile, setting=setting, hint=THE_ADAPTERS_FIX)


async def check(
    profiles: list[Any], callers: dict[str, Any], *, environment: str = "dev"
) -> list[dict[str, Any]]:
    """Run the check with each profile's caller looked up by its name; a caller that is an
    exception is raised when the caller is built, as a profile the AWS config lacks is."""

    def caller_for(profile: Any) -> Any:
        caller = callers[profile.name]
        if isinstance(caller, Exception):
            raise caller
        return caller

    found = (
        await module()
        .EvidenceProfileCheck(profiles=profiles, caller_for=caller_for, environment=environment)
        .run()
    )
    return [one.as_json() for one in found]


# ------------------------------------------------------------------------------------------------
# Defined, and signed in
# ------------------------------------------------------------------------------------------------


async def test_a_profile_signed_in_as_a_permission_sets_role_is_named_by_the_permission_set() -> None:
    [found] = await check([everyday()], {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE)})

    assert found == {
        "setting": "storage.s3.aws_profile",
        "profile": "debate-dev-evidence",
        "defined": True,
        "session": "signed_in",
        "permission_set": "DebateDevEvidenceOperator",
        "summary": "defined, and signed in as DebateDevEvidenceOperator",
        "hint": None,
    }
    assert EVERYDAY_ROLE not in str(found), "the permission set's name and never the role's own"


async def test_each_profile_is_asked_once_and_reported_under_its_own_setting_in_the_order_given() -> None:
    """Two profiles, two answers: neither is reported under the other's setting or name."""
    callers = {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE), TAKEDOWN_PROFILE: SignedInAs(TAKEDOWN_ROLE)}

    found = await check([everyday(), takedown()], callers)

    assert [(one["setting"], one["profile"], one["permission_set"]) for one in found] == [
        ("storage.s3.aws_profile", "debate-dev-evidence", "DebateDevEvidenceOperator"),
        ("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal", "DebateDevEvidenceRemoval"),
    ]
    assert [one["summary"] for one in found] == [
        "defined, and signed in as DebateDevEvidenceOperator",
        "defined, and signed in as DebateDevEvidenceRemoval",
    ]
    assert [caller.asked for caller in callers.values()] == [1, 1]


async def test_no_configured_profile_is_nothing_to_report() -> None:
    assert await check([], {}) == []


# ------------------------------------------------------------------------------------------------
# Not defined, expired, unanswered
# ------------------------------------------------------------------------------------------------


async def test_a_profile_the_aws_config_lacks_is_not_defined_and_carries_the_adapters_fix() -> None:
    """Raised when the caller is built, which is where boto3 refuses a session for it."""
    missing = not_defined("debate-dev-evidence-typo", EVERYDAY_SETTING)

    [found] = await check([everyday("debate-dev-evidence-typo")], {"debate-dev-evidence-typo": missing})

    assert found == {
        "setting": "storage.s3.aws_profile",
        "profile": "debate-dev-evidence-typo",
        "defined": False,
        "session": "not_defined",
        "permission_set": None,
        "summary": "not defined in this machine's AWS config",
        "hint": THE_ADAPTERS_FIX,
    }


async def test_a_profile_found_missing_only_when_it_is_asked_is_not_defined_too() -> None:
    """botocore's own chain can name a profile late; the answer is the same."""
    missing = CannotBeAsked(not_defined(EVERYDAY_PROFILE, EVERYDAY_SETTING))

    [found] = await check([everyday()], {EVERYDAY_PROFILE: missing})

    assert (found["defined"], found["session"]) == (False, "not_defined")


async def test_an_expired_session_is_reported_as_expired_with_the_login_and_the_profile_is_defined() -> None:
    expired = CannotBeAsked(errors.StoreCredentialsExpired("the AWS session is not usable", hint=LOGIN))

    [found] = await check([everyday()], {EVERYDAY_PROFILE: expired})

    assert found == {
        "setting": "storage.s3.aws_profile",
        "profile": "debate-dev-evidence",
        "defined": True,
        "session": "expired",
        "permission_set": None,
        "summary": (
            "defined; its session has expired or was never started, so AWS cannot be asked which "
            "permission set it is"
        ),
        "hint": "aws sso login --profile debate-dev-evidence",
    }


async def test_an_account_that_does_not_answer_is_no_verdict_on_the_profile() -> None:
    unanswered = CannotBeAsked(errors.StoreUnavailable("GetCallerIdentity", "s3://a-bucket", "timed out"))

    [found] = await check([everyday()], {EVERYDAY_PROFILE: unanswered})

    assert found == {
        "setting": "storage.s3.aws_profile",
        "profile": "debate-dev-evidence",
        "defined": True,
        "session": "no_answer",
        "permission_set": None,
        "summary": "defined; AWS did not answer when asked which permission set it is signed in as",
        "hint": "Run the check again when this machine can reach AWS.",
    }
    assert "a-bucket" not in str(found) and "timed out" not in str(found)


async def test_an_account_that_refuses_the_question_is_no_verdict_on_the_profile_either() -> None:
    """AWS does not refuse `GetCallerIdentity`. If something in front of it ever does, the profile
    is still one the AWS config defines, and the check says only that it got no answer."""
    refused = CannotBeAsked(errors.StoreAccessDenied("GetCallerIdentity", "s3://a-bucket"))

    [found] = await check([everyday()], {EVERYDAY_PROFILE: refused})

    assert (found["defined"], found["session"], found["permission_set"]) == (True, "no_answer", None)
    assert "a-bucket" not in str(found)


async def test_one_profile_that_is_not_defined_does_not_stop_the_other_being_asked() -> None:
    callers = {
        "debate-dev-evidence-typo": not_defined("debate-dev-evidence-typo", EVERYDAY_SETTING),
        TAKEDOWN_PROFILE: SignedInAs(TAKEDOWN_ROLE),
    }

    found = await check([everyday("debate-dev-evidence-typo"), takedown()], callers)

    assert [(one["profile"], one["session"], one["permission_set"]) for one in found] == [
        ("debate-dev-evidence-typo", "not_defined", None),
        ("debate-dev-evidence-removal", "signed_in", "DebateDevEvidenceRemoval"),
    ]


async def test_an_error_the_port_does_not_promise_is_not_swallowed() -> None:
    """A bug in an adapter is a bug: the check reports what the port says, and nothing else."""
    with pytest.raises(RuntimeError, match="a bug"):
        await check([everyday()], {EVERYDAY_PROFILE: CannotBeAsked(RuntimeError("a bug"))})


# ------------------------------------------------------------------------------------------------
# Signed in as something else
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role_name", "summary"),
    [
        pytest.param(
            "a-role-someone-made-by-hand",
            "defined, and signed in as a role that is no permission set's",
            id="a hand-made role",
        ),
        pytest.param(None, "defined, and signed in, but not as a role", id="not a role"),
    ],
)
async def test_a_credential_that_is_no_permission_sets_role_is_said_so_and_never_named(
    role_name: str | None, summary: str
) -> None:
    [found] = await check([everyday()], {EVERYDAY_PROFILE: SignedInAs(role_name)})

    assert (found["defined"], found["session"], found["permission_set"]) == (True, "signed_in", None)
    assert found["summary"] == summary
    assert "a-role-someone-made-by-hand" not in str(found), "permission-set names only"


async def test_a_takedown_profile_signed_in_as_another_permission_set_is_told_what_a_takedown_runs_as() -> (
    None
):
    """`DEBATE_REMOVAL_PROFILE` naming the everyday profile: `v1-e29-t08`'s mistake, seen early.
    The required set is the one the takedown preflight itself requires."""
    [found] = await check([takedown(EVERYDAY_PROFILE)], {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE)})

    assert found["permission_set"] == "DebateDevEvidenceOperator"
    assert found["summary"] == (
        "defined, and signed in as DebateDevEvidenceOperator; a takedown runs only as "
        "DebateDevEvidenceRemoval, so `caselist remove --execute` will refuse this profile"
    )
    assert takedown_permission_set("dev") == "DebateDevEvidenceRemoval"


async def test_the_takedown_permission_set_is_the_environments() -> None:
    """In prod the dev takedown role is the wrong one, and the prod one the right one."""
    prod_role = "AWSReservedSSO_DebateProdEvidenceRemoval_00000000000000aa"

    [wrong] = await check([takedown()], {TAKEDOWN_PROFILE: SignedInAs(TAKEDOWN_ROLE)}, environment="prod")
    [right] = await check([takedown()], {TAKEDOWN_PROFILE: SignedInAs(prod_role)}, environment="prod")

    assert wrong["summary"] == (
        "defined, and signed in as DebateDevEvidenceRemoval; a takedown runs only as "
        "DebateProdEvidenceRemoval, so `caselist remove --execute` will refuse this profile"
    )
    assert right["summary"] == "defined, and signed in as DebateProdEvidenceRemoval"


async def test_a_takedown_profile_that_is_no_permission_sets_role_is_told_the_same() -> None:
    [found] = await check([takedown()], {TAKEDOWN_PROFILE: SignedInAs(None)})

    assert found["summary"] == (
        "defined, and signed in, but not as a role; a takedown runs only as "
        "DebateDevEvidenceRemoval, so `caselist remove --execute` will refuse this profile"
    )


async def test_the_everyday_profile_signed_in_as_the_takedown_permission_set_is_said_so() -> None:
    """The other way round: the profile every run uses is the one that may delete."""
    [found] = await check([everyday(TAKEDOWN_PROFILE)], {TAKEDOWN_PROFILE: SignedInAs(TAKEDOWN_ROLE)})

    assert found["summary"] == (
        "defined, and signed in as DebateDevEvidenceRemoval, which is the takedown's permission set; "
        "the everyday profile is not meant to hold it"
    )


@pytest.mark.parametrize(
    ("environment", "role_name", "summary"),
    [
        pytest.param(
            "dev",
            "AWSReservedSSO_DebateProdEvidenceOperator_00000000000000aa",
            "defined, and signed in as DebateProdEvidenceOperator, which is prod's permission set and not "
            "dev's: dev's bucket grants it nothing, so every command that reaches the bucket will be refused",
            id="prod's everyday set, in dev",
        ),
        pytest.param(
            "prod",
            EVERYDAY_ROLE,
            "defined, and signed in as DebateDevEvidenceOperator, which is dev's permission set and not "
            "prod's: prod's bucket grants it nothing, so every command that reaches the bucket will be "
            "refused",
            id="dev's everyday set, in prod",
        ),
        pytest.param(
            "dev",
            "AWSReservedSSO_DebateProdEvidenceRemoval_00000000000000bb",
            "defined, and signed in as DebateProdEvidenceRemoval, which is prod's permission set and not "
            "dev's: dev's bucket grants it nothing, so every command that reaches the bucket will be refused",
            id="prod's takedown set, in dev",
        ),
    ],
)
async def test_an_everyday_profile_signed_in_as_the_other_environments_permission_set_is_said_so(
    environment: str, role_name: str, summary: str
) -> None:
    """`v1-e29-t09` ac5: a profile copied from the other environment's block, seen before a run
    meets every refusal. Said, and not a failure: only a profile that is not defined fails."""
    [found] = await check([everyday()], {EVERYDAY_PROFILE: SignedInAs(role_name)}, environment=environment)

    assert found["summary"] == summary
    assert (found["defined"], found["session"]) == (True, "signed_in")
    assert role_name not in str(found), "the permission set's name and never the role's own"


async def test_an_everyday_profile_signed_in_as_this_environments_set_is_not_said_to_be_the_others() -> None:
    [dev] = await check([everyday()], {EVERYDAY_PROFILE: SignedInAs(EVERYDAY_ROLE)}, environment="dev")
    prod_role = "AWSReservedSSO_DebateProdEvidenceOperator_00000000000000aa"
    [prod] = await check([everyday()], {EVERYDAY_PROFILE: SignedInAs(prod_role)}, environment="prod")

    assert dev["summary"] == "defined, and signed in as DebateDevEvidenceOperator"
    assert prod["summary"] == "defined, and signed in as DebateProdEvidenceOperator"


# ------------------------------------------------------------------------------------------------
# Which findings fail a check
# ------------------------------------------------------------------------------------------------


async def test_only_a_profile_that_is_not_defined_is_a_failure() -> None:
    """Expired, unanswered and signed in as something unexpected are all reported and none fails:
    the spec's rule, and the one `doctor` and the launchd check exit by."""
    check_module = module()
    callers: dict[str, Any] = {
        "missing": not_defined("missing", EVERYDAY_SETTING),
        "expired": CannotBeAsked(errors.StoreCredentialsExpired("not usable", hint=LOGIN)),
        "unanswered": CannotBeAsked(errors.StoreUnavailable("GetCallerIdentity", "s3://b", "503")),
        "wrong": SignedInAs(EVERYDAY_ROLE),
        "right": SignedInAs(TAKEDOWN_ROLE),
    }
    profiles = [
        everyday("missing"),
        everyday("expired"),
        everyday("unanswered"),
        takedown("wrong"),
        takedown("right"),
    ]

    def caller_for(profile: Any) -> Any:
        caller = callers[profile.name]
        if isinstance(caller, Exception):
            raise caller
        return caller

    found = await check_module.EvidenceProfileCheck(
        profiles=profiles, caller_for=caller_for, environment="dev"
    ).run()

    assert [(one.profile, one.defined) for one in found] == [
        ("missing", False),
        ("expired", True),
        ("unanswered", True),
        ("wrong", True),
        ("right", True),
    ]

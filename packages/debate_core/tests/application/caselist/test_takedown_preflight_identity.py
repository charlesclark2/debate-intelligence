"""The takedown preflight asks who the credential is before it lists or writes (`v1-e29-t08`).

Until `v1-e29-t06` the preflight began by listing object versions, which the everyday profile could
not do, so naming that profile for a takedown failed with nothing written. That grant made the
listing something both profiles may do. By the policy's text the everyday profile then lists,
writes the preflight's probe, and is refused only at the delete, leaving the probe behind. The
preflight's first step is now a question only the takedown role answers correctly: which role is
this credential signed in as?

## What these tests prove, and what they do not

Moto does not enforce IAM, so every store here would let any caller do anything. That is the
point of the refusals below: the stores are fully able, and the run still stops, with not one call
having reached them. Who the caller is is stubbed at the port
(:class:`~.conftest.SignedInAs`), so these tests prove what the application does with an answer.
That AWS gives the everyday profile the answer stubbed here is not proven by them: it rests on how
the account names an Identity Center role, which `docs/runbooks/evidence-store.md` step 4 has the
operator read back.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES

from debate_core.application.caselist.removal_plan import RemovalPlan, SourceSelector
from debate_core.application.caselist.removal_service import (
    CaselistRemovalService,
    TakedownAccess,
    TakedownPreflightFailed,
)
from debate_core.application.errors import (
    StoreCredentialsExpired,
    StoreProfileNotConfigured,
    StoreUnavailable,
)
from debate_core.application.ports.suppression import ReasonCode

from .conftest import EVERYDAY_ROLE, TAKEDOWN_ROLE, RemovalWorld, SignedInAs

pytestmark = pytest.mark.anyio

BAYVIEW = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()
EVERYDAY_PROFILE = "debate-dev-evidence"
TAKEDOWN_PROFILE = "debate-dev-evidence-removal"

ASKED = "caller.assumed_role_name"
THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE = [
    ASKED,
    "versions.list_versions",
    "objects.put_file",
    "versions.list_versions",
    "versions.delete_versions",
    "versions.list_versions",
]
"""Who is asking, first and once; then the probe as it has always gone: list, write, list, delete, list."""


class Journalled:
    """Passes every call through to `inner`, writing its name in `journal` first."""

    def __init__(self, inner: object, journal: list[str], label: str) -> None:
        self._inner = inner
        self._journal = journal
        self._label = label

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def call(*arguments: Any, **named: Any) -> Any:
            self._journal.append(f"{self._label}.{name}")
            return attribute(*arguments, **named)

        return call


def a_credential(
    world: RemovalWorld, signed_in_as: SignedInAs, *, profile: str
) -> tuple[Callable[[], TakedownAccess], list[str]]:
    """A takedown credential whose stores can do everything, and the journal of what is asked of it."""
    journal: list[str] = []
    real = world.takedown()

    def takedown() -> TakedownAccess:
        versions: Any = Journalled(real.versions, journal, "versions")
        objects: Any = Journalled(real.objects, journal, "objects")
        caller: Any = Journalled(signed_in_as, journal, "caller")
        return TakedownAccess(
            versions=versions, objects=objects, caller=caller, profile=profile, bucket=real.bucket
        )

    return takedown, journal


async def a_plan(service: CaselistRemovalService) -> RemovalPlan:
    return await service.plan(SourceSelector(BAYVIEW), request_id="RM-2026-03", reason=ReasonCode.POLICY)


def everything(world: RemovalWorld) -> tuple[Any, ...]:
    """This machine's files and records, and every object version in the bucket, probes included."""
    return world.tree(), world.versions(), world.records()


# ------------------------------------------------------------------------------------------------
# A caller that is not the takedown role
# ------------------------------------------------------------------------------------------------

NOT_THE_TAKEDOWN_ROLE = {
    "the everyday role": EVERYDAY_ROLE,
    "prod's takedown role, in dev": "AWSReservedSSO_DebateProdEvidenceRemoval_0123456789abcdef",
    "an administrator's role": "AWSReservedSSO_DebateBreakGlassAdmin_0123456789abcdef",
    "a set whose name begins with the takedown's": (
        "AWSReservedSSO_DebateDevEvidenceRemovalReaders_0123456789abcdef"
    ),
    "a set whose name is the takedown's and more": (
        "AWSReservedSSO_DebateDevEvidenceRemoval_Readers_0123456789abcdef"
    ),
    "the takedown set's name with no suffix": "AWSReservedSSO_DebateDevEvidenceRemoval_",
    "the takedown set's name and nothing after": "AWSReservedSSO_DebateDevEvidenceRemoval",
    "a role someone made by hand with the set's name": "DebateDevEvidenceRemoval",
    "a hand-made role that ends like the takedown's": "XAWSReservedSSO_DebateDevEvidenceRemoval_0123",
    "the set's name in another case": "AWSReservedSSO_debatedevevidenceremoval_0123456789abcdef",
    "not a role at all": None,
}


class TestACallerThatIsNotTheTakedownRole:
    @pytest.mark.parametrize("role_name", NOT_THE_TAKEDOWN_ROLE.values(), ids=NOT_THE_TAKEDOWN_ROLE.keys())
    async def test_it_is_refused_before_anything_is_listed_or_written(
        self, removal_world: RemovalWorld, role_name: str | None
    ) -> None:
        """The stores would let it run the whole removal. Not one call reaches them."""
        before = everything(removal_world)
        takedown, journal = a_credential(removal_world, SignedInAs(role_name), profile=EVERYDAY_PROFILE)
        service = removal_world.service(takedown=takedown)

        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(await a_plan(service))

        assert journal == [ASKED], "asked who it is, and then nothing: no listing, no probe"
        assert everything(removal_world) == before
        assert not (removal_world.data_dir / "suppression").exists(), "nothing appended either"
        message = str(refused.value)
        assert EVERYDAY_PROFILE in message and "nothing was deleted" in message
        assert "probe" not in message, "there is no probe to name: none was written"

    async def test_the_everyday_role_is_told_what_it_is_and_what_a_takedown_needs(
        self, removal_world: RemovalWorld
    ) -> None:
        takedown, _ = a_credential(removal_world, SignedInAs(EVERYDAY_ROLE), profile=EVERYDAY_PROFILE)
        service = removal_world.service(takedown=takedown)

        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(await a_plan(service))

        said = f"{refused.value} {refused.value.hint}"
        assert "NOT_THE_TAKEDOWN_ROLE" in said
        assert "DebateDevEvidenceOperator" in said, "the role it is signed in as, by its set's name"
        assert "DebateDevEvidenceRemoval" in said, "the role a takedown runs as"
        assert "DEBATE_REMOVAL_PROFILE" in said and TAKEDOWN_PROFILE in said
        assert "aws sso login" not in said, "it is signed in; logging in again changes nothing"
        assert EVERYDAY_ROLE not in said, "the set's name says it; the account's suffix is not needed"

    async def test_a_refusal_is_an_answer_and_is_not_asked_again_as_the_same_service_retries(
        self, removal_world: RemovalWorld
    ) -> None:
        """A second attempt with the same service asks again and is refused again: no cached pass."""
        takedown, journal = a_credential(removal_world, SignedInAs(EVERYDAY_ROLE), profile=EVERYDAY_PROFILE)
        service = removal_world.service(takedown=takedown)
        plan = await a_plan(service)

        for _ in range(2):
            with pytest.raises(TakedownPreflightFailed):
                await service.execute(plan)

        assert journal == [ASKED, ASKED]

    async def test_the_takedown_role_of_another_environment_is_refused_in_this_one(
        self, removal_world: RemovalWorld
    ) -> None:
        """Dev's takedown role, with the service built for prod."""
        before = everything(removal_world)
        takedown, journal = a_credential(removal_world, SignedInAs(TAKEDOWN_ROLE), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)
        plan = await a_plan(service)
        service.environment = "prod"

        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(plan)

        assert journal == [ASKED]
        assert everything(removal_world) == before
        assert "DebateProdEvidenceRemoval" in f"{refused.value} {refused.value.hint}"

    async def test_unsuppress_is_refused_the_same_way(self, removal_world: RemovalWorld) -> None:
        proper = removal_world.service()
        await proper.execute(await a_plan(proper))
        before = everything(removal_world)
        takedown, journal = a_credential(removal_world, SignedInAs(EVERYDAY_ROLE), profile=EVERYDAY_PROFILE)
        service = removal_world.service(takedown=takedown)
        plan = await service.plan_unsuppress(BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR)

        with pytest.raises(TakedownPreflightFailed):
            await service.unsuppress(plan)

        assert journal == [ASKED]
        assert everything(removal_world) == before


# ------------------------------------------------------------------------------------------------
# A credential that cannot be asked
# ------------------------------------------------------------------------------------------------


class TestACredentialThatCannotBeAsked:
    async def test_an_expired_session_stops_at_the_question_with_the_login_for_the_profile(
        self, removal_world: RemovalWorld
    ) -> None:
        before = everything(removal_world)
        expired = StoreCredentialsExpired(
            "the AWS session is not usable", hint=f"aws sso login --profile {TAKEDOWN_PROFILE}"
        )
        takedown, journal = a_credential(removal_world, SignedInAs(expired), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)

        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(await a_plan(service))

        assert journal == [ASKED]
        assert everything(removal_world) == before
        assert refused.value.__cause__ is expired, "what the command's exit status is read from"
        assert refused.value.hint == f"aws sso login --profile {TAKEDOWN_PROFILE}"
        assert "STORE_CREDENTIALS_EXPIRED" in str(refused.value)
        assert "nothing was deleted" in str(refused.value)

    async def test_an_account_that_does_not_answer_is_not_taken_for_the_takedown_role(
        self, removal_world: RemovalWorld
    ) -> None:
        unavailable = StoreUnavailable("GetCallerIdentity", "s3://a-bucket", "the connection timed out")
        takedown, journal = a_credential(removal_world, SignedInAs(unavailable), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)

        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(await a_plan(service))

        assert journal == [ASKED]
        assert refused.value.__cause__ is unavailable
        assert "STORE_UNAVAILABLE" in str(refused.value)


# ------------------------------------------------------------------------------------------------
# A profile the AWS config does not define (the PM's ac5)
# ------------------------------------------------------------------------------------------------


class TestATakedownProfileTheAwsConfigLacks:
    async def test_it_is_a_preflight_failure_that_says_nothing_was_deleted(
        self, removal_world: RemovalWorld
    ) -> None:
        """What `v1-e29-t07` left bare: the adapter's own error, which says nothing of the removal."""
        before = everything(removal_world)
        missing = StoreProfileNotConfigured(
            "debate-dev-evidence-removal-typo",
            setting="DEBATE_REMOVAL_PROFILE",
            hint="set DEBATE_REMOVAL_PROFILE to a profile this machine's AWS config defines",
        )

        def takedown() -> TakedownAccess:
            raise missing

        service = removal_world.service(takedown=takedown)

        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(await a_plan(service))

        message = str(refused.value)
        assert "nothing was deleted" in message
        assert "debate-dev-evidence-removal-typo" in message and "DEBATE_REMOVAL_PROFILE" in message
        assert "STORE_PROFILE_NOT_CONFIGURED" in message
        assert refused.value.__cause__ is missing, "a configuration error, so the command still exits 1"
        assert refused.value.hint == missing.hint, "the setting to correct, and never a login"
        assert "signed in" not in message and "aws sso login" not in message
        assert everything(removal_world) == before
        assert not (removal_world.data_dir / "suppression").exists()

    async def test_unsuppress_reports_it_the_same_way(self, removal_world: RemovalWorld) -> None:
        proper = removal_world.service()
        await proper.execute(await a_plan(proper))

        def takedown() -> TakedownAccess:
            raise StoreProfileNotConfigured("a-typo", setting="DEBATE_REMOVAL_PROFILE")

        service = removal_world.service(takedown=takedown)
        plan = await service.plan_unsuppress(BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR)

        with pytest.raises(TakedownPreflightFailed, match="nothing was deleted"):
            await service.unsuppress(plan)


# ------------------------------------------------------------------------------------------------
# The takedown role
# ------------------------------------------------------------------------------------------------


class TestTheTakedownRole:
    async def test_it_is_asked_who_it_is_first_and_once_and_then_the_probe_goes_as_before(
        self, removal_world: RemovalWorld
    ) -> None:
        takedown, journal = a_credential(removal_world, SignedInAs(TAKEDOWN_ROLE), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)

        report = await service.execute(await a_plan(service))

        assert report.completed
        assert journal[: len(THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE)] == THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE
        assert journal.count(ASKED) == 1
        probes = [key for key, _ in removal_world.versions() if "/preflight/" in key]
        assert probes == [], "the probe it wrote is gone, every version of it"

    async def test_a_service_that_has_passed_does_not_ask_again(self, removal_world: RemovalWorld) -> None:
        """Checked once per service, as the probe is: a second request in one run is not a second login."""
        takedown, journal = a_credential(removal_world, SignedInAs(TAKEDOWN_ROLE), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)
        await service.execute(await a_plan(service))

        await service.unsuppress(await service.plan_unsuppress(BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR))

        assert journal.count(ASKED) == 1
        assert journal.count("objects.put_file") > 1, "it went on to write, without a second preflight"

    @pytest.mark.parametrize(
        "suffix", ["0123456789abcdef", "fedcba9876543210", "a1b2c3", "0A1B2C3D4E5F6071"], ids=str
    )
    async def test_it_is_the_takedown_role_whatever_suffix_the_account_gave_it(
        self, removal_world: RemovalWorld, suffix: str
    ) -> None:
        """The suffix is the account's and is not ours to predict. The set's name is ours."""
        role = f"AWSReservedSSO_DebateDevEvidenceRemoval_{suffix}"
        takedown, _ = a_credential(removal_world, SignedInAs(role), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)

        report = await service.execute(await a_plan(service))

        assert report.completed

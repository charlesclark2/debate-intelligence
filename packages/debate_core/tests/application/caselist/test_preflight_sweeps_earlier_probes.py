"""A preflight that passes deletes the probes an earlier preflight left (`v1-e29-t09` ac4).

A probe is left when a preflight writes it and is refused the delete: from `v1-e29-t06` until
`v1-e29-t08`, the everyday profile named for a takedown; at any time, a takedown role whose delete
grant is broken. Until this task nothing removed one but the runbook's AWS CLI loop. Now the next
preflight that passes removes every version it found under `manifests/_suppression/preflight/`
before it wrote its own probe, with the credential it has just proven may delete there: the
takedown's.

"Older than its own probe" is read from the order of the calls, not from a clock: the preflight
lists the prefix before it writes, so whatever that listing found was there first. A probe that
arrives after the listing is not touched.

The sweep is housekeeping, and never holds a takedown back (the PM's review of `v1-e29-t09`). An
earlier probe whose delete is refused is left, counted on the run's report, and removed by hand as
`docs/runbooks/caselist-removal.md` describes; the takedown goes ahead. Only the preflight's own
probe is its proof, and a refused delete of that one still fails it.

Against moto, through the real S3 adapters; who the caller is is stubbed at the port, as in
`test_takedown_preflight_identity.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest

from debate_core.application.caselist.removal_service import (
    PREFLIGHT_PREFIX,
    TakedownAccess,
    TakedownPreflightFailed,
)
from debate_core.application.caselist.suppression import REMOVAL_LOG_KEY, SUPPRESSION_LIST_KEY
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import ReasonCode

from .conftest import EVERYDAY_ROLE, TAKEDOWN_ROLE, RemovalWorld, SignedInAs
from .test_takedown_preflight_identity import (
    BAYVIEW,
    EVERYDAY_PROFILE,
    TAKEDOWN_PROFILE,
    THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE,
    a_credential,
    a_plan,
)

pytestmark = pytest.mark.anyio

LEFT_ONCE = f"{PREFLIGHT_PREFIX}{'0' * 32}.txt"
"""A probe left with one version, as a refused delete leaves it."""

LEFT_AND_HIDDEN = f"{PREFLIGHT_PREFIX}{'1' * 32}.txt"
"""A probe with two versions and a delete marker: someone deleted it by key, without a version id."""

ARRIVED_LATER = f"{PREFLIGHT_PREFIX}{'2' * 32}.txt"
"""A probe written after the preflight listed the prefix: not older than its own, so not touched."""

PROBE_BODY = b"caselist remove preflight\n"


def leave_probes(world: RemovalWorld) -> None:
    """What earlier preflights left: four versions over two keys, one of them a delete marker."""
    world.client.put_object(Bucket=world.bucket_name, Key=LEFT_ONCE, Body=PROBE_BODY)
    world.client.put_object(Bucket=world.bucket_name, Key=LEFT_AND_HIDDEN, Body=PROBE_BODY)
    world.client.put_object(Bucket=world.bucket_name, Key=LEFT_AND_HIDDEN, Body=PROBE_BODY)
    world.client.delete_object(Bucket=world.bucket_name, Key=LEFT_AND_HIDDEN)


def probes(world: RemovalWorld) -> list[str]:
    """Every version under the preflight's prefix, delete markers included, by key."""
    return [key for key, _ in world.versions() if key.startswith(PREFLIGHT_PREFIX)]


class VersionsWithAHook:
    """The takedown's version store, with a hook after each listing and a delete that may refuse."""

    def __init__(
        self,
        inner: Any,
        *,
        after_listing: Callable[[int], None] | None = None,
        refuse_delete: Callable[[int, Sequence[ObjectVersion]], bool] | None = None,
    ) -> None:
        self._inner = inner
        self._after_listing = after_listing
        self._refuse_delete = refuse_delete
        self.listings = 0
        self.deletes = 0

    @property
    def location(self) -> str:
        return str(self._inner.location)

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        listed: tuple[ObjectVersion, ...] = await self._inner.list_versions(prefix)
        self.listings += 1
        if self._after_listing is not None:
            self._after_listing(self.listings)
        return listed

    async def get_version_file(self, version: ObjectVersion, destination: Any) -> None:
        await self._inner.get_version_file(version, destination)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        self.deletes += 1
        if self._refuse_delete is not None and self._refuse_delete(self.deletes, versions):
            raise StoreAccessDenied("DeleteObject", f"s3://bucket/{versions[0].key}")
        return int(await self._inner.delete_versions(versions))


def with_versions(world: RemovalWorld, versions: VersionsWithAHook) -> Callable[[], TakedownAccess]:
    real = world.takedown()

    def takedown() -> TakedownAccess:
        return TakedownAccess(
            versions=versions,
            objects=real.objects,
            caller=real.caller,
            profile=real.profile,
            bucket=real.bucket,
        )

    return takedown


class TestAPreflightThatPasses:
    async def test_it_deletes_every_version_an_earlier_preflight_left_with_the_takedown_profile(
        self, removal_world: RemovalWorld
    ) -> None:
        leave_probes(removal_world)
        assert len(probes(removal_world)) == 4, "two versions of one, and one of the other, and a marker"
        takedown, journal = a_credential(removal_world, SignedInAs(TAKEDOWN_ROLE), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)

        report = await service.execute(await a_plan(service))

        assert report.completed
        assert report.preflight_probes_left == ()
        assert probes(removal_world) == [], "every version and the marker, and its own probe"
        # Its own probe as it has always gone, then one delete of what the first listing found,
        # through the takedown credential's version store: the only one that may delete.
        sweep = len(THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE)
        assert journal[: sweep + 1] == [*THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE, "versions.delete_versions"]
        kept = {key for key, _ in removal_world.versions()}
        assert {SUPPRESSION_LIST_KEY, REMOVAL_LOG_KEY} <= kept, "one level up, and never deleted"

    async def test_with_nothing_left_it_deletes_nothing_more_than_its_own_probe(
        self, removal_world: RemovalWorld
    ) -> None:
        takedown, journal = a_credential(removal_world, SignedInAs(TAKEDOWN_ROLE), profile=TAKEDOWN_PROFILE)
        service = removal_world.service(takedown=takedown)

        await service.execute(await a_plan(service))

        sweep = len(THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE)
        assert journal[:sweep] == THE_PREFLIGHT_WITH_THE_TAKEDOWN_ROLE
        assert journal[sweep : sweep + 1] != ["versions.delete_versions"]

    async def test_a_probe_written_after_its_listing_is_not_older_than_its_own_and_is_kept(
        self, removal_world: RemovalWorld
    ) -> None:
        """Another preflight's probe, written between this one's listing and its write."""
        leave_probes(removal_world)

        def another_preflight_writes(listing: int) -> None:
            if listing == 1:
                removal_world.client.put_object(
                    Bucket=removal_world.bucket_name, Key=ARRIVED_LATER, Body=PROBE_BODY
                )

        versions = VersionsWithAHook(
            removal_world.takedown().versions, after_listing=another_preflight_writes
        )
        service = removal_world.service(takedown=with_versions(removal_world, versions))

        assert (await service.execute(await a_plan(service))).completed

        assert probes(removal_world) == [ARRIVED_LATER]

    async def test_unsuppress_sweeps_the_same_way(self, removal_world: RemovalWorld) -> None:
        proper = removal_world.service()
        await proper.execute(await a_plan(proper))
        leave_probes(removal_world)
        service = removal_world.service()

        report = await service.unsuppress(
            await service.plan_unsuppress(BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR)
        )

        assert probes(removal_world) == []
        assert report.preflight_probes_left == ()

    async def test_an_earlier_probe_whose_delete_is_refused_is_left_and_counted_and_the_takedown_completes(
        self, removal_world: RemovalWorld
    ) -> None:
        """The PM's review: housekeeping never holds a takedown back. One earlier probe refused,
        the other deleted with its marker; the removal is carried out and the one left is counted."""
        leave_probes(removal_world)
        versions = VersionsWithAHook(
            removal_world.takedown().versions,
            refuse_delete=lambda _, asked: any(version.key == LEFT_ONCE for version in asked),
        )
        service = removal_world.service(takedown=with_versions(removal_world, versions))

        report = await service.execute(await a_plan(service))

        assert report.completed
        assert report.log_entry.s3_versions_deleted > 0, "the takedown itself went ahead"
        assert len(report.preflight_probes_left) == 1
        assert [version.key for version in report.preflight_probes_left] == [LEFT_ONCE]
        assert probes(removal_world) == [LEFT_ONCE], "the other probe, its versions and its marker went"

    async def test_unsuppress_counts_an_earlier_probe_it_could_not_delete_and_appends_its_entry(
        self, removal_world: RemovalWorld
    ) -> None:
        proper = removal_world.service()
        await proper.execute(await a_plan(proper))
        leave_probes(removal_world)
        versions = VersionsWithAHook(
            removal_world.takedown().versions,
            refuse_delete=lambda _, asked: any(version.key == LEFT_ONCE for version in asked),
        )
        service = removal_world.service(takedown=with_versions(removal_world, versions))

        report = await service.unsuppress(
            await service.plan_unsuppress(BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR)
        )

        assert [version.key for version in report.preflight_probes_left] == [LEFT_ONCE]
        assert probes(removal_world) == [LEFT_ONCE]


class TestAPreflightThatDoesNotPass:
    async def test_the_everyday_profile_deletes_no_earlier_probe(self, removal_world: RemovalWorld) -> None:
        leave_probes(removal_world)
        before = probes(removal_world)
        takedown, _ = a_credential(removal_world, SignedInAs(EVERYDAY_ROLE), profile=EVERYDAY_PROFILE)
        service = removal_world.service(takedown=takedown)

        with pytest.raises(TakedownPreflightFailed):
            await service.execute(await a_plan(service))

        assert probes(removal_world) == before

    async def test_a_refused_delete_of_its_own_probe_still_fails_it_and_sweeps_nothing(
        self, removal_world: RemovalWorld
    ) -> None:
        """Its own probe is the proof, so this is unchanged: refused, the takedown does not begin,
        the error names the probe left, and no earlier probe is touched."""
        leave_probes(removal_world)
        before = probes(removal_world)
        versions = VersionsWithAHook(
            removal_world.takedown().versions, refuse_delete=lambda call, _: call == 1
        )
        service = removal_world.service(takedown=with_versions(removal_world, versions))

        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(await a_plan(service))

        assert refused.value.step == "delete an object version"
        assert "its probe object was left at manifests/_suppression/preflight/" in str(refused.value)
        assert versions.deletes == 1, "no sweep after a preflight that did not pass"
        left = probes(removal_world)
        assert [key for key in left if key in before] == before
        assert len(left) == len(before) + 1, "its own probe, left, and named in the error"
        assert not (removal_world.data_dir / "suppression").exists(), "nothing appended"

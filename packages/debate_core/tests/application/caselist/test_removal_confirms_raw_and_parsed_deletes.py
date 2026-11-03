"""After deleting `raw/` and `parsed/`, a removal lists them again and stops if one survived (`v1-e30-t29`).

`v1-e32-t13` gave the landscape school views a listing after the delete; this gives the same to every
`raw/` and `parsed/` key the plan reaches. A version or delete marker of one of those keys that the
takedown credential still lists after deleting it stops the run `INCOMPLETE`, with counts and no key,
and running the same removal again finishes it (ac1).

Every bucket is moto's, versioned, and every removal is the real one. A delete the store answers and
does not carry out is the double :class:`AnswersWithoutDeleting`, copied from `v1-e32-t13`'s
`KeepsOneKey` and widened to a rule, because the preflight's probe goes through the same credential
and must still be deleted.

The file removed is the Seaside Cup round 5 affirmative: in the `testcl26` week of 2026-09-15 only,
no camp file, no other holder, so its bucket copy is one `raw/` key with one version. Its parsed
cards are written here by hand, under one `parsed/` key with two versions, because the synthetic
store is imported and published but never parsed. Everything below is counted from those two keys.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from tests.fixtures.caselist.publish_expectations import digest_of_body

from debate_core.application.caselist.removal_plan import RemovalPlan, Side, SourceSelector
from debate_core.application.caselist.removal_service import (
    BucketObjectsLeft,
    RemovalIncomplete,
    TakedownAccess,
)
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import ReasonCode, RemovalOutcome

from .conftest import REQUEST, RemovalWorld

pytestmark = pytest.mark.anyio

REMOVED = digest_of_body("seaside-round-5-aff")
RAW_KEY = f"raw/caselist/testcl26/sha256/{REMOVED[:2]}/{REMOVED[2:4]}/{REMOVED}"
PARSED_KEY = f"parsed/testcl26/2026.09.20-docx-1/sha256/{REMOVED[:2]}/{REMOVED[2:4]}/{REMOVED}.jsonl"
SIBLING_KEY = f"{RAW_KEY}.extra"
"""A key the raw key is a prefix of, and that no plan names: what a listing by the key also returns."""

UNSAID = (REMOVED, "raw/", "parsed/", "testcl26", "Seaside", "Maple Grove", "QX")
"""What the error, its facts and the removal log never hold: a key, a path, a caselist, a school or a
team code. The removal log names the removed digest by design (`removed_sha256`), so it is checked
for the rest."""


class AnswersWithoutDeleting:
    """The removal credential's versions, except that deleting what `keeps` picks is answered and not done."""

    def __init__(self, access: TakedownAccess, keeps: Callable[[ObjectVersion], bool]) -> None:
        self._inner = access.versions
        self._keeps = keeps
        self.access = TakedownAccess(
            versions=self,  # pyright: ignore[reportArgumentType]
            objects=access.objects,
            caller=access.caller,
            profile=access.profile,
            bucket=access.bucket,
        )

    @property
    def location(self) -> str:
        return self._inner.location

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        return await self._inner.list_versions(prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        await self._inner.get_version_file(version, destination)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        await self._inner.delete_versions([one for one in versions if not self._keeps(one)])
        return len(versions)


def under(*keys: str) -> Callable[[ObjectVersion], bool]:
    return lambda version: version.key in keys


@pytest.fixture
async def world(removal_world: RemovalWorld) -> RemovalWorld:
    """The removal world, with the removed file's parsed cards in the bucket in two versions."""
    for version in (1, 2):
        removal_world.client.put_object(
            Bucket=removal_world.bucket_name, Key=PARSED_KEY, Body=f"synthetic cards {version}\n".encode()
        )
    return removal_world


async def plan_of(world: RemovalWorld) -> RemovalPlan:
    return await world.service().plan(
        SourceSelector(REMOVED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )


def bucket_versions(world: RemovalWorld, key: str) -> list[str]:
    """Every version id and delete marker id of exactly `key`."""
    return [version_id for listed, version_id in world.versions() if listed == key]


async def stopped(world: RemovalWorld, keeps: Callable[[ObjectVersion], bool]) -> RemovalIncomplete:
    service = world.service(takedown=lambda: AnswersWithoutDeleting(world.takedown(), keeps).access)
    with pytest.raises(RemovalIncomplete) as raised:
        await service.execute(await plan_of(world))
    return raised.value


async def log_lines(world: RemovalWorld) -> list[str]:
    return [line for record in world.removal_log().records for line in await record.read_lines()]


async def test_the_plan_reaches_exactly_the_raw_and_the_parsed_key(world: RemovalWorld) -> None:
    """The ground every count below stands on, from the fixture's facts."""
    plan = await plan_of(world)

    assert sorted(planned.key for planned in plan.objects_on(Side.BUCKET)) == [PARSED_KEY, RAW_KEY]
    assert len(bucket_versions(world, RAW_KEY)) == 1
    assert len(bucket_versions(world, PARSED_KEY)) == 2


class TestADeleteThatDeletesNothing:
    """ac1: the credential answers every delete of the removed file's keys and carries out none."""

    async def test_it_stops_the_removal_incomplete_counting_the_versions_and_files_left(
        self, world: RemovalWorld
    ) -> None:
        incomplete = await stopped(world, under(RAW_KEY, PARSED_KEY))

        assert incomplete.error_code == "BUCKET_OBJECTS_LEFT"
        assert incomplete.report.log_entry.outcome is RemovalOutcome.INCOMPLETE
        assert incomplete.report.log_entry.error_code == "BUCKET_OBJECTS_LEFT"
        left = incomplete.__cause__
        assert isinstance(left, BucketObjectsLeft)
        assert (left.versions, left.files) == (3, 2)
        assert str(left) == (
            "3 version(s) or delete marker(s) of 2 source or parsed file(s) this removal reached are "
            "still in the bucket after it deleted them; run the same removal again"
        )
        assert len(bucket_versions(world, RAW_KEY)) == 1
        assert len(bucket_versions(world, PARSED_KEY)) == 2

    async def test_the_error_its_facts_and_the_log_entry_hold_counts_and_no_key(
        self, world: RemovalWorld
    ) -> None:
        incomplete = await stopped(world, under(RAW_KEY, PARSED_KEY))

        left = incomplete.__cause__
        assert isinstance(left, BucketObjectsLeft)
        said = [str(incomplete), str(left), *(str(value) for value in vars(left).values())]
        for text in said:
            for word in UNSAID:
                assert word not in text, f"{word!r} in {text!r}"
        lines = await log_lines(world)
        assert len(lines) == 2, "one entry, in this machine's copy and the bucket's"
        for line in lines:
            for word in UNSAID[1:]:
                assert word not in line, f"{word!r} in the removal log"

    async def test_the_same_removal_run_again_with_a_delete_that_works_finishes_it(
        self, world: RemovalWorld
    ) -> None:
        await stopped(world, under(RAW_KEY, PARSED_KEY))

        service = world.service()
        report = await service.execute(await plan_of(world))

        assert report.completed
        assert bucket_versions(world, RAW_KEY) == []
        assert bucket_versions(world, PARSED_KEY) == []
        entries = await world.removal_log().entries()
        assert [(entry.outcome, entry.error_code) for entry in entries] == [
            (RemovalOutcome.INCOMPLETE, "BUCKET_OBJECTS_LEFT"),
            (RemovalOutcome.COMPLETED, None),
        ]


class TestEachSideAlone:
    async def test_a_version_left_under_raw_alone_stops_the_removal(self, world: RemovalWorld) -> None:
        incomplete = await stopped(world, under(RAW_KEY))

        left = incomplete.__cause__
        assert isinstance(left, BucketObjectsLeft)
        assert (left.versions, left.files) == (1, 1)
        assert bucket_versions(world, PARSED_KEY) == []

    async def test_a_version_left_under_parsed_alone_stops_the_removal(self, world: RemovalWorld) -> None:
        incomplete = await stopped(world, under(PARSED_KEY))

        left = incomplete.__cause__
        assert isinstance(left, BucketObjectsLeft)
        assert (left.versions, left.files) == (2, 1)
        assert bucket_versions(world, RAW_KEY) == []

    async def test_a_delete_marker_left_behind_is_a_survivor(self, world: RemovalWorld) -> None:
        """A plain delete of the raw key before the removal leaves its version noncurrent behind a marker;
        the credential here deletes the version and answers for the marker without deleting it."""
        world.client.delete_object(Bucket=world.bucket_name, Key=RAW_KEY)
        assert len(bucket_versions(world, RAW_KEY)) == 2

        incomplete = await stopped(world, lambda version: version.is_delete_marker)

        left = incomplete.__cause__
        assert isinstance(left, BucketObjectsLeft)
        assert (left.versions, left.files) == (1, 1)
        assert len(bucket_versions(world, RAW_KEY)) == 1


class TestWhatTheCheckLeavesAlone:
    async def test_a_sibling_key_the_raw_key_is_a_prefix_of_does_not_stop_it(
        self, world: RemovalWorld
    ) -> None:
        world.client.put_object(Bucket=world.bucket_name, Key=SIBLING_KEY, Body=b"synthetic sibling\n")
        plan = await plan_of(world)
        assert SIBLING_KEY not in {planned.key for planned in plan.objects_on(Side.BUCKET)}

        report = await world.service().execute(plan)

        assert report.completed
        assert bucket_versions(world, RAW_KEY) == []
        assert len(bucket_versions(world, SIBLING_KEY)) == 1

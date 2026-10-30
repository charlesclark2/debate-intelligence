"""`tub index prune`'s rules, against moto through the real S3 adapters (`v1-e39-t15`).

The bucket is the versioned moto bucket of `tests/fixtures/moto_evidence_bucket.py`. Each test writes
its search indexes the way `tub index publish` does, the two files and then `current.json`, and keeps
the version id S3 gave every write; what the prune must delete and keep is written down from those
writes, never read back from the prune. Which role the takedown credential holds is stubbed at the
port, as the removal tests do: moto does not enforce IAM.
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import pytest
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE

from debate_core.application.caselist.removal_service import NotTheTakedownRole, TakedownAccess
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.search_index_prune import (
    PruneGroup,
    PruneOnCloudRunDay,
    SearchIndexPointerMoved,
    SearchIndexPrune,
    SearchIndexPruneRefused,
    WouldDeleteTheCurrentSearchIndex,
    is_cloud_run_day,
)
from debate_core.domain.search_index import (
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SEARCH_INDEX_PREFIX,
    SearchIndexPointer,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore, S3EvidenceVersionStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

FIRST: Final = "aaaaaaaaaaaaaaaa"
SECOND: Final = "bbbbbbbbbbbbbbbb"
CURRENT: Final = "cccccccccccccccc"
NEVER_UPLOADED: Final = "dddddddddddddddd"
LATER: Final = "eeeeeeeeeeeeeeee"

THURSDAY: Final = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
WEDNESDAY_NOON_IN_CHICAGO: Final = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)

Written = tuple[str, str]
"""One write: its key and the version id S3 gave it."""


def written(versions: tuple[ObjectVersion, ...]) -> set[Written]:
    return {(one.key, str(one.version_id)) for one in versions}


@dataclass
class Bucket:
    """The moto bucket, written to as `tub index publish` writes, every version id kept."""

    client: S3Client
    name: str
    files: dict[str, set[Written]] = field(default_factory=dict)
    """Every version of each index's two files, by index id, delete markers included."""
    pointers: dict[str, Written] = field(default_factory=dict)
    """The `current.json` version that named each index."""

    def put(self, key: str, body: bytes = b"index bytes") -> Written:
        return key, self.client.put_object(Bucket=self.name, Key=key, Body=body)["VersionId"]

    def upload(self, index_id: str) -> None:
        """An index's manifest and gzip object, with no pointer: the first two steps of a publish."""
        for name in (SEARCH_INDEX_MANIFEST_NAME, SEARCH_INDEX_GZIP_NAME):
            self.files.setdefault(index_id, set()).add(self.put(f"{SEARCH_INDEX_PREFIX}{index_id}/{name}"))

    def point_at(self, index_id: str) -> None:
        """The last step of a publish: `current.json` naming `index_id`."""
        self.pointers[index_id] = self.put(SEARCH_INDEX_POINTER_KEY, pointer(index_id).to_json_bytes())

    def publish(self, index_id: str) -> None:
        self.upload(index_id)
        self.point_at(index_id)

    def delete(self, key: str) -> Written:
        """A plain delete: S3 writes a delete marker, and every version stays."""
        return key, self.client.delete_object(Bucket=self.name, Key=key)["VersionId"]

    def listing(self) -> set[Written]:
        listed = self.client.list_object_versions(Bucket=self.name, Prefix=SEARCH_INDEX_PREFIX)
        return {
            (str(one.get("Key")), str(one.get("VersionId")))
            for one in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]
        }


def pointer(index_id: str) -> SearchIndexPointer:
    return SearchIndexPointer(
        format_version=1,
        index_id=index_id,
        manifest_key=f"{SEARCH_INDEX_PREFIX}{index_id}/{SEARCH_INDEX_MANIFEST_NAME}",
        manifest_sha256="1" * 64,
        object_key=f"{SEARCH_INDEX_PREFIX}{index_id}/{SEARCH_INDEX_GZIP_NAME}",
        object_sha256="2" * 64,
        sqlite_sha256="3" * 64,
    )


class SignedInAs:
    """The takedown credential's identity, stubbed at the port."""

    def __init__(self, role_name: str | None) -> None:
        self.role_name = role_name

    async def assumed_role_name(self) -> str | None:
        return self.role_name


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> Bucket:
    return Bucket(client=s3_client, name=evidence_bucket)


@pytest.fixture
def three_published(bucket: Bucket) -> Bucket:
    """Three indexes published in turn, the first's gzip object deleted by hand (a delete marker), and
    the current index's manifest uploaded twice (a noncurrent version inside the current directory)."""
    bucket.publish(FIRST)
    bucket.publish(SECOND)
    bucket.files[FIRST].add(bucket.delete(f"{SEARCH_INDEX_PREFIX}{FIRST}/{SEARCH_INDEX_GZIP_NAME}"))
    bucket.publish(CURRENT)
    bucket.files[CURRENT].add(bucket.put(f"{SEARCH_INDEX_PREFIX}{CURRENT}/{SEARCH_INDEX_MANIFEST_NAME}"))
    return bucket


def superseded(world: Bucket) -> set[Written]:
    """What the prune of `three_published` deletes, from the writes: the two earlier directories, the
    delete marker among them, and the two `current.json` versions that named them."""
    return world.files[FIRST] | world.files[SECOND] | {world.pointers[FIRST], world.pointers[SECOND]}


def current(world: Bucket) -> set[Written]:
    """What it keeps: every version in the current directory, and the `current.json` naming it."""
    return world.files[CURRENT] | {world.pointers[CURRENT]}


def prune_service(
    world: Bucket, *, role: str | None = TAKEDOWN_ROLE, now: datetime = THURSDAY
) -> SearchIndexPrune:
    objects = S3EvidenceObjectStore(bucket=world.name, client=world.client)
    access = TakedownAccess(
        versions=S3EvidenceVersionStore(bucket=world.name, client=world.client),
        objects=objects,
        caller=SignedInAs(role),
        profile="debate-dev-evidence-removal",
        bucket=world.name,
    )
    return SearchIndexPrune(pointer=objects, takedown=lambda: access, environment="dev", clock=lambda: now)


# ------------------------------------------------------------------------------------------------
# The dry run
# ------------------------------------------------------------------------------------------------


def test_the_dry_run_lists_every_superseded_version_and_delete_marker(three_published: Bucket) -> None:
    plan = asyncio.run(prune_service(three_published).plan())

    assert plan.refusals == ()
    assert written(plan.doomed) == superseded(three_published)
    assert len(plan.doomed) == 7
    assert sum(one.is_delete_marker for one in plan.doomed) == 1


def test_the_dry_run_keeps_the_current_index_directory_and_the_current_pointer(
    three_published: Bucket,
) -> None:
    plan = asyncio.run(prune_service(three_published).plan())

    assert written(plan.kept) == current(three_published)
    assert plan.index_id == CURRENT
    assert not written(plan.doomed) & current(three_published)
    assert written(plan.doomed) | written(plan.kept) == three_published.listing()


def test_the_dry_run_counts_by_directory_and_deletes_nothing(three_published: Bucket) -> None:
    before = three_published.listing()

    plan = asyncio.run(prune_service(three_published).plan())

    assert plan.groups == (
        PruneGroup(name=f"{FIRST}/", delete=2, delete_markers=1, keep=0),
        PruneGroup(name=f"{SECOND}/", delete=2, delete_markers=0, keep=0),
        PruneGroup(name=f"{CURRENT}/", delete=0, delete_markers=0, keep=3),
        PruneGroup(name="current.json", delete=2, delete_markers=0, keep=1),
    )
    assert three_published.listing() == before


def test_the_confirmation_code_is_twelve_hex_characters_and_follows_what_was_listed(
    three_published: Bucket,
) -> None:
    service = prune_service(three_published)
    first = asyncio.run(service.plan()).confirmation
    three_published.put(f"{SEARCH_INDEX_PREFIX}{SECOND}/{SEARCH_INDEX_MANIFEST_NAME}")

    second = asyncio.run(service.plan()).confirmation

    assert len(first) == 12 and int(first, 16) >= 0
    assert second != first


def test_a_bucket_with_only_the_current_index_has_nothing_to_delete(bucket: Bucket) -> None:
    bucket.publish(CURRENT)

    plan = asyncio.run(prune_service(bucket).plan())

    assert plan.refusals == ()
    assert plan.doomed == ()
    assert written(plan.kept) == current(bucket)


# ------------------------------------------------------------------------------------------------
# The pointer must name an index the listing holds
# ------------------------------------------------------------------------------------------------


def test_a_pointer_naming_an_index_the_listing_does_not_hold_is_refused(three_published: Bucket) -> None:
    three_published.point_at(NEVER_UPLOADED)
    before = three_published.listing()
    service = prune_service(three_published)

    plan = asyncio.run(service.plan())

    assert [one.code for one in plan.refusals] == ["POINTER_NOT_IN_LISTING"]
    with pytest.raises(SearchIndexPruneRefused):
        asyncio.run(service.execute(plan, confirmation=plan.confirmation))
    assert three_published.listing() == before


def test_a_pointer_whose_gzip_object_is_deleted_is_refused(three_published: Bucket) -> None:
    three_published.delete(f"{SEARCH_INDEX_PREFIX}{CURRENT}/{SEARCH_INDEX_GZIP_NAME}")

    plan = asyncio.run(prune_service(three_published).plan())

    assert [one.code for one in plan.refusals] == ["POINTER_NOT_IN_LISTING"]


def test_a_pointer_whose_manifest_is_missing_is_refused(bucket: Bucket) -> None:
    bucket.put(f"{SEARCH_INDEX_PREFIX}{CURRENT}/{SEARCH_INDEX_GZIP_NAME}")
    bucket.point_at(CURRENT)

    plan = asyncio.run(prune_service(bucket).plan())

    assert [one.code for one in plan.refusals] == ["POINTER_NOT_IN_LISTING"]


def test_a_bucket_with_no_pointer_is_refused(bucket: Bucket) -> None:
    bucket.publish(FIRST)
    bucket.delete(SEARCH_INDEX_POINTER_KEY)

    plan = asyncio.run(prune_service(bucket).plan())

    assert [one.code for one in plan.refusals] == ["NO_CURRENT_SEARCH_INDEX"]
    assert plan.doomed == ()


def test_a_pointer_this_build_cannot_read_is_refused(bucket: Bucket) -> None:
    bucket.upload(FIRST)
    bucket.put(SEARCH_INDEX_POINTER_KEY, b'{"index_id": "aaaaaaaaaaaaaaaa"}')

    plan = asyncio.run(prune_service(bucket).plan())

    assert [one.code for one in plan.refusals] == ["SEARCH_INDEX_POINTER_UNREADABLE"]
    assert plan.doomed == ()


def test_the_everyday_role_is_refused_before_anything_is_listed(three_published: Bucket) -> None:
    with pytest.raises(NotTheTakedownRole):
        asyncio.run(prune_service(three_published, role=EVERYDAY_ROLE).plan())


# ------------------------------------------------------------------------------------------------
# --execute
# ------------------------------------------------------------------------------------------------


def test_execute_with_the_dry_runs_code_deletes_exactly_what_it_listed(three_published: Bucket) -> None:
    service = prune_service(three_published)
    plan = asyncio.run(service.plan())

    result = asyncio.run(service.execute(plan, confirmation=plan.confirmation))

    assert result.deleted == 7
    assert three_published.listing() == current(three_published)
    again = asyncio.run(service.plan())
    assert again.doomed == ()
    assert again.index_id == CURRENT


@pytest.mark.parametrize("confirmation", [None, "", "000000000000"])
def test_execute_without_the_dry_runs_code_refuses_and_deletes_nothing(
    three_published: Bucket, confirmation: str | None
) -> None:
    service = prune_service(three_published)
    plan = asyncio.run(service.plan())
    before = three_published.listing()

    with pytest.raises(SearchIndexPruneRefused) as refused:
        asyncio.run(service.execute(plan, confirmation=confirmation))

    assert refused.value.refusal.code == "CONFIRMATION_MISMATCH"
    assert three_published.listing() == before


def test_a_code_from_an_earlier_listing_is_refused(three_published: Bucket) -> None:
    service = prune_service(three_published)
    earlier = asyncio.run(service.plan()).confirmation
    three_published.put(f"{SEARCH_INDEX_PREFIX}{SECOND}/{SEARCH_INDEX_MANIFEST_NAME}")
    plan = asyncio.run(service.plan())
    before = three_published.listing()

    with pytest.raises(SearchIndexPruneRefused):
        asyncio.run(service.execute(plan, confirmation=earlier))

    assert three_published.listing() == before


def test_a_pointer_that_moved_after_the_dry_run_refuses_and_deletes_nothing(three_published: Bucket) -> None:
    service = prune_service(three_published)
    plan = asyncio.run(service.plan())
    three_published.publish(LATER)
    before = three_published.listing()

    with pytest.raises(SearchIndexPointerMoved):
        asyncio.run(service.execute(plan, confirmation=plan.confirmation))

    assert three_published.listing() == before


def test_execute_refuses_a_plan_that_would_delete_the_current_index(three_published: Bucket) -> None:
    """The last check before the delete, whatever the plan says: the current directory's versions and
    the current `current.json` are never sent to the store."""
    service = prune_service(three_published)
    plan = asyncio.run(service.plan())
    before = three_published.listing()

    for kept in plan.kept:
        tampered = dataclasses.replace(plan, doomed=(*plan.doomed, kept))
        with pytest.raises(WouldDeleteTheCurrentSearchIndex):
            asyncio.run(service.execute(tampered, confirmation=tampered.confirmation))

    assert three_published.listing() == before


def test_execute_refuses_on_the_cloud_runs_day_and_deletes_nothing(three_published: Bucket) -> None:
    service = prune_service(three_published, now=WEDNESDAY_NOON_IN_CHICAGO)
    plan = asyncio.run(service.plan())
    before = three_published.listing()

    with pytest.raises(PruneOnCloudRunDay):
        asyncio.run(service.execute(plan, confirmation=plan.confirmation))

    assert three_published.listing() == before


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 4, 6, 0, tzinfo=UTC), True),
        (datetime(2026, 11, 4, 18, 0, tzinfo=UTC), True),
        (datetime(2026, 11, 5, 5, 30, tzinfo=UTC), True),
        (datetime(2026, 11, 4, 5, 30, tzinfo=UTC), False),
        (datetime(2026, 11, 5, 6, 30, tzinfo=UTC), False),
        (datetime(2026, 10, 28, 4, 59, tzinfo=UTC), False),
        (datetime(2026, 10, 28, 5, 0, tzinfo=UTC), True),
    ],
)
def test_the_cloud_runs_day_is_wednesday_in_chicago(now: datetime, expected: bool) -> None:
    """Chicago is UTC-5 until 1 November 2026 and UTC-6 after: Wednesday there starts at 05:00 UTC on
    28 October and at 06:00 UTC on 4 November."""
    assert is_cloud_run_day(now) is expected

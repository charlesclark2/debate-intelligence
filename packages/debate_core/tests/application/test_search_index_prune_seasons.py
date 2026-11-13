"""`tub index prune` with backfile seasons' pointers beside `current.json` (`v1-e39-t18`).

The PM's shape 4 puts each season's index under `reports/tub/search/<index id>/`, as every index
is, and its pointer at `reports/tub/search/seasons/<season>.json`. The prune lists that prefix whole,
so it must keep what each season pointer names, as it keeps what `current.json` names, and still
delete every superseded season version: a removal has to reach a backfile card's old copies too (E39
gate items 1 and 5).

Against the versioned moto bucket of `tests/fixtures/moto_evidence_bucket.py`, written as `tub index
publish --season` writes; what is kept and deleted is written down from the writes, never read back
from the prune. Every id and slug is invented.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import pytest
from tests.fixtures.identity_center_roles import TAKEDOWN_ROLE

from debate_core.application.caselist.removal_service import TakedownAccess
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.search_index_prune import (
    SearchIndexPointerMoved,
    SearchIndexPrune,
    WouldDeleteTheCurrentSearchIndex,
)
from debate_core.application.season_indexes import season_pointer_key
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

OLD_CURRENT: Final = "aaaaaaaaaaaaaaaa"
CURRENT: Final = "cccccccccccccccc"
OLD_SEASON: Final = "1111111111111111"
SEASON_INDEX: Final = "2222222222222222"
OTHER_SEASON_INDEX: Final = "3333333333333333"
SEASON: Final = "hsxx25"
OTHER_SEASON: Final = "hsyy24"
THURSDAY: Final = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)

Written = tuple[str, str]


def written(versions: tuple[ObjectVersion, ...]) -> set[Written]:
    return {(one.key, str(one.version_id)) for one in versions}


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


@dataclass
class Bucket:
    client: S3Client
    name: str
    files: dict[str, set[Written]] = field(default_factory=dict[str, set[Written]])
    pointers: dict[tuple[str, str], Written] = field(default_factory=dict[tuple[str, str], Written])
    """The pointer version that named each index, by (pointer key, index id)."""

    def put(self, key: str, body: bytes = b"index bytes") -> Written:
        return key, self.client.put_object(Bucket=self.name, Key=key, Body=body)["VersionId"]

    def publish(self, index_id: str, *, pointer_key: str = SEARCH_INDEX_POINTER_KEY) -> None:
        for name in (SEARCH_INDEX_MANIFEST_NAME, SEARCH_INDEX_GZIP_NAME):
            self.files.setdefault(index_id, set()).add(self.put(f"{SEARCH_INDEX_PREFIX}{index_id}/{name}"))
        self.pointers[(pointer_key, index_id)] = self.put(pointer_key, pointer(index_id).to_json_bytes())

    def listing(self) -> set[Written]:
        listed = self.client.list_object_versions(Bucket=self.name, Prefix=SEARCH_INDEX_PREFIX)
        return {
            (str(one.get("Key")), str(one.get("VersionId")))
            for one in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]
        }


class SignedInAs:
    def __init__(self, role_name: str | None) -> None:
        self.role_name = role_name

    async def assumed_role_name(self) -> str | None:
        return self.role_name


def prune_service(world: Bucket) -> SearchIndexPrune:
    objects = S3EvidenceObjectStore(bucket=world.name, client=world.client)
    access = TakedownAccess(
        versions=S3EvidenceVersionStore(bucket=world.name, client=world.client),
        objects=objects,
        caller=SignedInAs(TAKEDOWN_ROLE),
        profile="debate-dev-evidence-removal",
        bucket=world.name,
    )
    return SearchIndexPrune(
        pointer=objects, takedown=lambda: access, environment="dev", clock=lambda: THURSDAY
    )


@pytest.fixture
def seasons_published(evidence_bucket: str, s3_client: S3Client) -> Bucket:
    """Two current indexes in turn, and one season's two indexes in turn, and a second season's one."""
    world = Bucket(client=s3_client, name=evidence_bucket)
    world.publish(OLD_CURRENT)
    world.publish(CURRENT)
    world.publish(OLD_SEASON, pointer_key=season_pointer_key(SEASON))
    world.publish(SEASON_INDEX, pointer_key=season_pointer_key(SEASON))
    world.publish(OTHER_SEASON_INDEX, pointer_key=season_pointer_key(OTHER_SEASON))
    return world


def kept_by_every_pointer(world: Bucket) -> set[Written]:
    """The current index and each season's current index, with the pointer version naming each."""
    return (
        world.files[CURRENT]
        | world.files[SEASON_INDEX]
        | world.files[OTHER_SEASON_INDEX]
        | {
            world.pointers[(SEARCH_INDEX_POINTER_KEY, CURRENT)],
            world.pointers[(season_pointer_key(SEASON), SEASON_INDEX)],
            world.pointers[(season_pointer_key(OTHER_SEASON), OTHER_SEASON_INDEX)],
        }
    )


def superseded_everywhere(world: Bucket) -> set[Written]:
    """The superseded current index and the superseded season index, and the pointer versions naming them."""
    return (
        world.files[OLD_CURRENT]
        | world.files[OLD_SEASON]
        | {
            world.pointers[(SEARCH_INDEX_POINTER_KEY, OLD_CURRENT)],
            world.pointers[(season_pointer_key(SEASON), OLD_SEASON)],
        }
    )


def test_the_prune_keeps_every_season_pointers_current_index(seasons_published: Bucket) -> None:
    plan = asyncio.run(prune_service(seasons_published).plan())

    assert plan.refusals == ()
    assert written(plan.kept) == kept_by_every_pointer(seasons_published)
    assert not written(plan.doomed) & kept_by_every_pointer(seasons_published)


def test_the_prune_still_deletes_a_seasons_superseded_index_and_pointer_versions(
    seasons_published: Bucket,
) -> None:
    plan = asyncio.run(prune_service(seasons_published).plan())

    assert written(plan.doomed) == superseded_everywhere(seasons_published)
    assert written(plan.doomed) | written(plan.kept) == seasons_published.listing()


def test_executing_the_plan_leaves_every_current_index_and_pointer(seasons_published: Bucket) -> None:
    service = prune_service(seasons_published)
    plan = asyncio.run(service.plan())

    result = asyncio.run(service.execute(plan, confirmation=plan.confirmation))

    assert result.deleted == len(superseded_everywhere(seasons_published))
    assert seasons_published.listing() == kept_by_every_pointer(seasons_published)


def test_a_season_pointer_that_cannot_be_read_refuses_the_plan(seasons_published: Bucket) -> None:
    seasons_published.put(season_pointer_key(OTHER_SEASON), b"not a pointer")

    plan = asyncio.run(prune_service(seasons_published).plan())

    assert [one.code for one in plan.refusals] == ["SEASON_POINTER_UNREADABLE"]
    assert plan.doomed == ()


def test_a_season_pointer_naming_an_index_the_listing_lacks_refuses_the_plan(
    seasons_published: Bucket,
) -> None:
    seasons_published.put(season_pointer_key(OTHER_SEASON), pointer("4444444444444444").to_json_bytes())

    plan = asyncio.run(prune_service(seasons_published).plan())

    assert [one.code for one in plan.refusals] == ["POINTER_NOT_IN_LISTING"]
    assert plan.doomed == ()


def test_a_season_pointer_moved_after_the_plan_stops_the_delete(seasons_published: Bucket) -> None:
    service = prune_service(seasons_published)
    plan = asyncio.run(service.plan())
    seasons_published.publish("5555555555555555", pointer_key=season_pointer_key(SEASON))
    before = seasons_published.listing()

    with pytest.raises(SearchIndexPointerMoved):
        asyncio.run(service.execute(plan, confirmation=plan.confirmation))

    assert seasons_published.listing() == before


def test_the_last_check_refuses_a_plan_naming_a_seasons_current_index(seasons_published: Bucket) -> None:
    service = prune_service(seasons_published)
    plan = asyncio.run(service.plan())
    season_files = tuple(
        one for one in plan.kept if one.key.startswith(f"{SEARCH_INDEX_PREFIX}{SEASON_INDEX}/")
    )
    tampered = type(plan)(
        location=plan.location,
        pointer=plan.pointer,
        kept=tuple(one for one in plan.kept if one not in season_files),
        doomed=(*plan.doomed, *season_files),
        refusals=(),
        season_pointers=plan.season_pointers,
    )
    before = seasons_published.listing()

    with pytest.raises(WouldDeleteTheCurrentSearchIndex):
        asyncio.run(service.execute(tampered, confirmation=tampered.confirmation))

    assert seasons_published.listing() == before

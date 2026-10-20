"""`store sync` pushes no manifest `caselist publish` withholds (`v1-e30-t25`, item 1).

Until this task a push sent every local manifest. Only `manifests/_suppression/` and the blobs the
list or a hold stops were skipped, so a manifest the publisher withholds, because a row of it names a
removed file or a held path, went to the bucket under another command. A push now asks the
publisher's own plan of that one snapshot
(:attr:`~debate_core.application.caselist.publish_plan.SnapshotPlan.withholding_rows`), as `caselist
status` does for its hint (`v1-e30-t19`), and skips the manifest with the publisher's own message.

The row kinds are those `withholding_rows` is made of, counted from the code:

* `suppressed_rows`, a stored row the list stops: the whole file, one caselist disclosure of it, or
  one camp path of it (`v1-e30-t07`, `v1-e30-t14`);
* `held_rows`, a stored row at a path a removal holds (`v1-e30-t21`), in a weekly or in a complete
  archive, whose manifest is a level further down;
* `held_skipped_rows`, a skipped member's row at a held path (`v1-e30-t23`): a symbolic link, or
  the AppleDouble junk that shadows one (`v1-e30-t25`, item 2).

Each case puts one manifest of that kind on this machine and not in the bucket, beside one that
withholds nothing, and pushes both. The store and the removal are `v1-e30-t21`'s and `v1-e30-t22`'s.
Every test runs offline: moto for the bucket, a temporary data directory, and a temporary `HOME`.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_revised_path_archives import (
    CASELIST,
    ONE_WEEK_PATH,
    REVISED_PATH,
    digest_of,
)

from debate_core.application.caselist import publish_service
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import CaselistPublishService, ManifestOutcome
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    ManifestWithholding,
    PlannedObject,
    SyncAction,
    SyncDirection,
    SyncKeyspace,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    camp_path_scope,
    disclosure_digest,
)
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.testing.fakes import InMemoryAppendOnlyRecord

from .conftest import REQUEST, RemovalWorld
from .test_held_path_loose_ends import (
    HELD_WEEK_MANIFEST,
    an_older_build_imports_next_week,
    an_older_build_imports_the_next_complete_archive,
)
from .test_held_rows_publish_nothing import (
    LINK_WEEK_MANIFEST,
    WEEK_OF_THE_LINK,
    an_older_builds_importer,
    import_archive,
)
from .test_junk_beside_a_held_link import JUNK_OF_THE_HELD_PATH, write_archive
from .test_removal_covers_later_uploads import (
    NAMES,
    a_camp_releases_the_later_revision,
    remove_the_named_file,
    revised_path_world,
)
from .test_removed_path_holds_later_imports import manifest_rows

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

#: Holds only `kept`, which no case stops or holds: the manifest pushed beside the withheld one.
PUSHED_BESIDE = f"manifests/{CASELIST}/2026-09-22.jsonl"
#: The only manifest naming `one-week-only`, at `ONE_WEEK_PATH`.
ONE_WEEK_MANIFEST = f"manifests/{CASELIST}/2026-09-08.jsonl"

type AskWithheld = Callable[[ObjectInfo, SuppressionState], Awaitable[ManifestWithholding | None]]
type AskTheStore = Callable[
    [LocalEvidence, ObjectInfo, SuppressionState], Awaitable[ManifestWithholding | None]
]


@pytest.fixture(autouse=True)
def temporary_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `HOME` of this test's own, so nothing here can read or write the operator's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


class CountingStore:
    """The bucket, counting the listings and heads asked of it: what planning a sync costs."""

    def __init__(self, inner: EvidenceObjectStore) -> None:
        self._inner = inner
        self.listings: list[str] = []
        self.heads: list[ObjectKey] = []

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        self.listings.append(prefix)
        return await self._inner.list_objects(prefix)

    async def head(self, key: ObjectKey) -> ObjectInfo:
        self.heads.append(key)
        return await self._inner.head(key)

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        return await self._inner.put_file(key, source)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        return await self._inner.get_file(key, destination)


def store_sync(
    world: RemovalWorld,
    suppression: SuppressionList,
    *,
    remote: EvidenceObjectStore | None = None,
    asked: list[ObjectKey] | None = None,
    withholding: bool = True,
) -> EvidenceSyncService:
    """`store sync --blob-prefix raw/caselist/testcl26`, built as the composition root builds it.

    `asked` collects every manifest key the push asks the publisher about. On a build without the
    question (the red run), the service is built as that build's composition root builds it.
    """
    ask: AskTheStore | None = getattr(publish_service, "withheld_manifest_reason", None)
    extra: dict[str, AskWithheld] = {}
    if withholding and ask is not None and "withheld_manifests" in signature(EvidenceSyncService).parameters:
        asking = functools.partial(ask, world.local)

        async def recorded(manifest: ObjectInfo, state: SuppressionState) -> ManifestWithholding | None:
            if asked is not None:
                asked.append(manifest.key)
            return await asking(manifest, state)

        extra["withheld_manifests"] = recorded
    bucket = remote if remote is not None else world.bucket
    return EvidenceSyncService(
        suppression=suppression,
        keyspaces=(
            SyncKeyspace(name="objects", local=world.local.objects, remote=bucket),
            SyncKeyspace(
                name="blobs",
                local=world.local.blobs,
                remote=bucket,
                remote_prefix=f"raw/caselist/{CASELIST}",
                content_addressed=True,
            ),
        ),
        **extra,  # pyright: ignore[reportArgumentType]
    )


def with_entry(
    world_entries: tuple[SuppressionEntry, ...], entry: SuppressionEntry
) -> RecordedSuppressionList:
    """The world's list with one more entry, as a removal made on another machine leaves it: on the
    list, and the manifest on this machine not rewritten."""
    lines = [one.to_line() for one in (*world_entries, entry)]
    return RecordedSuppressionList(InMemoryAppendOnlyRecord("the list, one entry more", lines))


def stops(digest: str, disclosure: str | None = None) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=digest,
        disclosure=disclosure,
        recorded_at=datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id=REQUEST,
    )


def in_the_bucket(world: RemovalWorld, key: str) -> bool:
    return world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=key).get("KeyCount", 0) == 1


def off_the_bucket(world: RemovalWorld, *keys: str) -> None:
    """Delete the bucket's copy of each key, so a push would send this machine's."""
    for key in keys:
        world.client.delete_object(Bucket=world.bucket_name, Key=key)


def planned(objects: tuple[PlannedObject, ...], key: str) -> PlannedObject:
    (found,) = [one for one in objects if one.keyspace == "objects" and one.remote_key == key]
    return found


def caselist_and_snapshot(key: str) -> tuple[str, str]:
    caselist, _, snapshot = key.removeprefix("manifests/").removesuffix(".jsonl").partition("/")
    return caselist, snapshot


# ------------------------------------------------------------------------------------------------
# One manifest of each row kind, on this machine and not in the bucket
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Withheld:
    """A manifest the publisher withholds, the list it is withheld by, and what it names."""

    key: str
    suppression: SuppressionList
    names: tuple[str, ...]
    """The paths the manifest's withholding rows are at: none may appear in the sync's reason."""


async def a_suppressed_file(world: RemovalWorld, tmp_path: Path) -> Withheld:
    """`one-week-only` on the list as a whole file, and `2026-09-08` not rewritten."""
    listed = with_entry(await world.suppression().entries(), stops(digest_of("one-week-only")))
    return Withheld(ONE_WEEK_MANIFEST, listed, (ONE_WEEK_PATH,))


async def a_withdrawn_disclosure(world: RemovalWorld, tmp_path: Path) -> Withheld:
    """`one-week-only` withdrawn from `ONE_WEEK_PATH` alone."""
    withdrawn = stops(digest_of("one-week-only"), disclosure_digest(CASELIST, ONE_WEEK_PATH))
    return Withheld(
        ONE_WEEK_MANIFEST, with_entry(await world.suppression().entries(), withdrawn), (ONE_WEEK_PATH,)
    )


async def a_withdrawn_camp_path(world: RemovalWorld, tmp_path: Path) -> Withheld:
    """A camp release of `later-revision`, published, then withdrawn from its camp path alone."""
    key = await a_camp_releases_the_later_revision(world, tmp_path / "camp")
    (path,) = [
        str(row["path"])
        for row in manifest_rows(world, key)
        if row.get("sha256") == digest_of("later-revision")
    ]
    _, release = caselist_and_snapshot(key)
    withdrawn = stops(digest_of("later-revision"), disclosure_digest(camp_path_scope(release), path))
    return Withheld(key, with_entry(await world.suppression().entries(), withdrawn), (path,))


async def a_held_row(world: RemovalWorld, tmp_path: Path) -> Withheld:
    """After the removal, an older build imports `2026-10-08` with an upload at the held path."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    return Withheld(HELD_WEEK_MANIFEST, world.suppression(), (REVISED_PATH,))


async def a_held_row_in_a_complete_archive(world: RemovalWorld, tmp_path: Path) -> Withheld:
    """After the removal, an older build imports the complete archive of `2026-10-09`, whose manifest
    is a level further down: `manifests/testcl26/full/2026-10-09.jsonl`."""
    await remove_the_named_file(world)
    await an_older_build_imports_the_next_complete_archive(world, tmp_path)
    return Withheld(f"manifests/{CASELIST}/full/2026-10-09.jsonl", world.suppression(), (REVISED_PATH,))


async def a_held_link(world: RemovalWorld, tmp_path: Path) -> Withheld:
    """After the removal, an older build imports `2026-10-11` with a symbolic link at the held path."""
    await remove_the_named_file(world)
    archive = write_archive(
        tmp_path / "arriving" / f"{CASELIST}-weekly-2026-10-11.zip", links=(REVISED_PATH,)
    )
    await import_archive(world, archive, WEEK_OF_THE_LINK, importer=an_older_builds_importer(world))
    return Withheld(LINK_WEEK_MANIFEST, world.suppression(), (REVISED_PATH,))


async def junk_at_the_held_path(world: RemovalWorld, tmp_path: Path) -> Withheld:
    """After the removal, an older build imports `2026-10-11` with AppleDouble junk naming the held path."""
    await remove_the_named_file(world)
    archive = write_archive(
        tmp_path / "arriving" / f"{CASELIST}-weekly-2026-10-11.zip", junk=(JUNK_OF_THE_HELD_PATH,)
    )
    await import_archive(world, archive, WEEK_OF_THE_LINK, importer=an_older_builds_importer(world))
    return Withheld(LINK_WEEK_MANIFEST, world.suppression(), (REVISED_PATH, JUNK_OF_THE_HELD_PATH))


ROW_KINDS: dict[str, Callable[[RemovalWorld, Path], Awaitable[Withheld]]] = {
    "a suppressed file": a_suppressed_file,
    "a withdrawn disclosure": a_withdrawn_disclosure,
    "a withdrawn camp path": a_withdrawn_camp_path,
    "a held row": a_held_row,
    "a held row in a complete archive": a_held_row_in_a_complete_archive,
    "a held link": a_held_link,
    "junk at the held path": junk_at_the_held_path,
}


@pytest.fixture(params=list(ROW_KINDS))
async def withheld(request: pytest.FixtureRequest, world: RemovalWorld, tmp_path: Path) -> Withheld:
    """One manifest of the kind, and `PUSHED_BESIDE`, on this machine and not in the bucket."""
    made = await ROW_KINDS[request.param](world, tmp_path)
    off_the_bucket(world, made.key, PUSHED_BESIDE)
    return made


async def the_publishers_message(world: RemovalWorld, withheld: Withheld) -> str | None:
    """What `caselist publish` says when it withholds the manifest, from its own run."""
    caselist, snapshot = caselist_and_snapshot(withheld.key)
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=withheld.suppression
    )
    (outcome,) = (await publisher.execute(await publisher.plan(caselist, snapshot))).snapshots
    assert outcome.manifest is ManifestOutcome.WITHHELD, "the precondition: the publisher withholds it"
    return outcome.manifest_error


# ------------------------------------------------------------------------------------------------
# The push
# ------------------------------------------------------------------------------------------------


async def test_a_push_skips_the_manifest_the_publisher_withholds_with_its_reason_and_pushes_the_rest(
    world: RemovalWorld, withheld: Withheld
) -> None:
    service = store_sync(world, withheld.suppression)

    plan = await service.plan(prefix="manifests/", direction=SyncDirection.PUSH)
    report = await service.execute(plan)

    skipped = planned(plan.objects, withheld.key)
    assert skipped.action is SyncAction.SKIPPED, f"{withheld.key} was planned {skipped.action}"
    assert planned(plan.objects, PUSHED_BESIDE).action is SyncAction.NEW
    assert report.succeeded
    assert not in_the_bucket(world, withheld.key), "the withheld manifest went up"
    assert in_the_bucket(world, PUSHED_BESIDE)
    assert skipped.reason == await the_publishers_message(world, withheld)
    assert not [word for word in (*NAMES, *withheld.names, ".docx", "__MACOSX") if word in skipped.reason]


async def test_a_push_of_a_rewritten_manifest_that_withholds_nothing_still_sends_it(
    world: RemovalWorld,
) -> None:
    """The removal rewrote `2026-09-15` here; the bucket's copy is the one from before. Nothing in the
    rewrite withholds it, so the push sends it over the bucket's, as before this task."""
    await remove_the_named_file(world)
    key = f"manifests/{CASELIST}/2026-09-15.jsonl"
    world.client.put_object(Bucket=world.bucket_name, Key=key, Body=b"an older copy\n")

    plan = await store_sync(world, world.suppression()).plan(prefix=key, direction=SyncDirection.PUSH)

    assert planned(plan.objects, key).action is SyncAction.CHANGED


async def test_a_push_asks_only_about_manifests_it_would_send_and_makes_no_extra_request(
    world: RemovalWorld, withheld: Withheld
) -> None:
    """What the question costs: no listing or head the push did not already make, and one read of each
    local manifest the push would otherwise send. A manifest already in the bucket is not asked about."""
    asked: list[ObjectKey] = []
    with_question, without = CountingStore(world.bucket), CountingStore(world.bucket)

    await store_sync(world, withheld.suppression, remote=with_question, asked=asked).plan(
        prefix="manifests/", direction=SyncDirection.PUSH
    )
    await store_sync(world, withheld.suppression, remote=without, withholding=False).plan(
        prefix="manifests/", direction=SyncDirection.PUSH
    )

    assert sorted(asked) == sorted((withheld.key, PUSHED_BESIDE))
    assert (with_question.listings, sorted(with_question.heads)) == (without.listings, sorted(without.heads))


async def test_a_pull_is_not_asked_about_withholding(world: RemovalWorld) -> None:
    """Only a push sends a manifest. The bucket's `2026-09-08`, published before the list stopped a
    row of it, is pulled to a machine that lacks it, as before this task."""
    listed = await a_suppressed_file(world, Path())
    FsEvidenceObjectStore(world.data_dir).path_for(ONE_WEEK_MANIFEST).unlink()
    asked: list[ObjectKey] = []

    plan = await store_sync(world, listed.suppression, asked=asked).plan(
        prefix="manifests/", direction=SyncDirection.PULL
    )

    assert planned(plan.objects, ONE_WEEK_MANIFEST).action is SyncAction.NEW
    assert asked == []


async def test_a_push_skips_a_manifest_the_publisher_cannot_read_and_carries_on(world: RemovalWorld) -> None:
    """A publish refuses a manifest it cannot read and publishes nothing of it; a push cannot tell
    whether it withholds it, so does not send it either. Skipped with the publisher's refusal, which
    names the key and the line and never the line itself, and the rest of the push goes ahead."""
    unreadable = f"manifests/{CASELIST}/2026-10-13.jsonl"
    FsEvidenceObjectStore(world.data_dir).path_for(unreadable).write_bytes(b"not a manifest row\n")
    off_the_bucket(world, PUSHED_BESIDE)
    service = store_sync(world, world.suppression())

    plan = await service.plan(prefix="manifests/", direction=SyncDirection.PUSH)
    report = await service.execute(plan)

    skipped = planned(plan.objects, unreadable)
    assert (skipped.action, skipped.reason) == (
        SyncAction.SKIPPED,
        f"{unreadable} line 1 is not a usable manifest row: not JSON",
    )
    assert report.succeeded
    assert in_the_bucket(world, PUSHED_BESIDE)
    assert not in_the_bucket(world, unreadable)

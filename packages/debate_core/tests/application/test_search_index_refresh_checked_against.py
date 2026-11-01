"""A rebuild identical to the published index records what it was checked against (`v1-e39-t19`, ac1).

An index id is the start of its SQLite file's digest, so a suppression entry that stops nothing in
the corpus rebuilds the same index, and the weekly stage does not publish it again. Before this task
the published manifest then went on naming the shorter list, and the cutover's comparison read that
as a difference (`v1-e40-t06`). Now the stage writes `checked-against.json` beside the manifest.

Against moto's versioned S3, through the real S3 adapter, so that every PUT a test counts is a
version of its key: the bucket says what was uploaded, not a wrapper around the adapter. The run's
lock is the real :class:`~debate_core.application.caselist.run_lock.BucketRunLock` over the same
bucket, fencing the client the index is published through as the composition root fences it, while
the stage reads `current.json` through an unfenced one: a read needs no lease.

Every store is synthetic, as `test_search_index_stage.py`'s are; its store writer is reused. Every
expected value is written by hand from the store a test builds.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest

from debate_core.application.caselist.run_lock import (
    CLOCK_SKEW_MARGIN,
    LEASE,
    RUN_LOCK_KEY,
    BucketRunLock,
    HolderKind,
    RunLockLost,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_sync import SearchIndexStageReport, StageOutcome
from debate_core.application.errors import StoreCredentialsExpired
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.application.ports.parsed_store import OPENEV_STORE
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.application.search_index_publish import (
    CHECKED_AGAINST_NAME,
    CheckedAgainstRecord,
    SearchIndexPublishService,
)
from debate_core.application.search_index_refresh import (
    RESTORED_INDEX_MARKER,
    SEARCH_INDEX_DIRECTORY,
    SearchIndexRefresh,
)
from debate_core.domain.caselist import Event
from debate_core.domain.search_index import (
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SEARCH_INDEX_PREFIX,
    SearchIndexManifest,
    SearchIndexPointer,
)
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.integrations.s3.fencing import fence_client
from debate_core.integrations.s3.run_lock_object import S3LockObject
from debate_core.integrations.s3.search_index_source import S3SearchIndexSource
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

from .test_caselist_sync_run_state import run_state
from .test_search_index_stage import CASELIST, PARSER, STORES, CountingBuilder, suppression_of, write_store

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

START: Final = datetime(2026, 11, 4, 11, 0, 5, tzinfo=UTC)

CASELIST_TEXTS: Final = ["Invented growth evidence", "Invented trade evidence"]
CAMP_TEXTS: Final = ["Invented camp evidence"]

STOPS_A_CARD: Final = suppression_of("Invented trade evidence")
"""An entry that stops one of the caselist's two cards: the first index is built under it."""

STOPS_NOTHING: Final = suppression_of("Invented evidence no store holds")
"""An entry for a source no store holds, as `RM-2026-90`'s was: the list grows, the index does not."""


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class ExpiringUploads:
    """The S3 adapter, except that uploading one key finds the session expired."""

    def __init__(self, inner: S3EvidenceObjectStore, expires_at: str | None) -> None:
        self.inner = inner
        self.expires_at = expires_at

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self.inner.list_objects(prefix)

    async def head(self, key: str) -> ObjectInfo:
        return await self.inner.head(key)

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        if key == self.expires_at:
            raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")
        return await self.inner.put_file(key, source)

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        return await self.inner.get_file(key, destination)


@dataclass
class BucketWorld:
    """One machine's data directory and the stage, over one versioned moto bucket.

    `writes` is the client the index and the record are published through; `reads` the one the stage
    reads `current.json` with. Without a lock they are the same client.
    """

    root: Path
    reads: S3Client
    bucket: str
    writes: S3Client
    session_expires_at: str | None = None
    """A key whose upload finds the AWS session expired, as an SSO login that ran out mid-run does."""

    def __post_init__(self) -> None:
        self.data_dir = self.root / "data"
        self.out = self.data_dir / SEARCH_INDEX_DIRECTORY
        self.parsed = InMemoryParsedStore()
        self.local = RecordedSuppressionList(local_suppression_list_file(self.data_dir))
        self.builder = CountingBuilder(
            parsed_store=self.parsed,
            caselists=InMemoryCaselistRepository(),
            suppression=self.local,
            writer=SqliteSearchIndexWriter(),
            parser_version=PARSER,
            event_for_caselist={CASELIST: Event.LD}.get,
            release_manifest_lines=lambda _key: (),
        )
        write_store(self.parsed, CASELIST, CASELIST_TEXTS)
        write_store(self.parsed, OPENEV_STORE, CAMP_TEXTS)
        self.suppress(STOPS_A_CARD)

    def suppress(self, *entries: Any) -> None:
        asyncio.run(self.local.append(list(entries)))

    def stage(self) -> SearchIndexRefresh:
        async def reconciled() -> None:
            """This machine's copy is the whole list here; the bucket's copy is another suite's."""

        return SearchIndexRefresh(
            builder=self.builder,
            out=self.out,
            parser_version=PARSER,
            publisher=SearchIndexPublishService(
                bucket=ExpiringUploads(
                    S3EvidenceObjectStore(bucket=self.bucket, client=self.writes), self.session_expires_at
                ),
                parser_version=PARSER,
            ),
            bucket=S3EvidenceObjectStore(bucket=self.bucket, client=self.reads),
            reconcile=reconciled,
            environment="dev",
        )

    def refresh(self) -> SearchIndexStageReport:
        return asyncio.run(self.stage().refresh(STORES, no_session=None))

    def forget_local_indexes(self) -> None:
        """The cloud's working copy, or a damaged one: the next run rebuilds whatever the digests say."""
        shutil.rmtree(self.out)

    # -- what the bucket holds ----------------------------------------------------------------------

    def versions(self) -> dict[str, int]:
        """How many times each key under `reports/tub/search/` was put: its versions in the bucket."""
        listed = self.reads.list_object_versions(Bucket=self.bucket, Prefix=SEARCH_INDEX_PREFIX)
        counted: dict[str, int] = {}
        for version in listed.get("Versions", []):
            counted[version["Key"]] = counted.get(version["Key"], 0) + 1  # pyright: ignore[reportTypedDictNotRequiredAccess]
        return counted

    def body(self, key: str) -> bytes:
        return self.reads.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def pointer(self) -> SearchIndexPointer:
        return SearchIndexPointer.model_validate_json(self.body(SEARCH_INDEX_POINTER_KEY))

    def record(self, index_id: str) -> CheckedAgainstRecord:
        return CheckedAgainstRecord.model_validate_json(self.body(record_key(index_id)))

    def suppression_digest(self) -> str:
        return asyncio.run(self.builder.sources(STORES)).suppression_list.sha256


def key(index_id: str, name: str) -> str:
    return f"{SEARCH_INDEX_PREFIX}{index_id}/{name}"


def record_key(index_id: str) -> str:
    return key(index_id, CHECKED_AGAINST_NAME)


def published_once(index_id: str) -> dict[str, int]:
    """A first publish: the gzip object, the manifest and the pointer, each put once."""
    return {
        key(index_id, SEARCH_INDEX_GZIP_NAME): 1,
        key(index_id, SEARCH_INDEX_MANIFEST_NAME): 1,
        SEARCH_INDEX_POINTER_KEY: 1,
    }


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> BucketWorld:
    return BucketWorld(tmp_path, reads=s3_client, bucket=evidence_bucket, writes=s3_client)


def first_publish(world: BucketWorld) -> str:
    """The first index, under one entry, published: its id."""
    report = world.refresh()
    assert report.outcome is StageOutcome.COMPLETED and report.counts is not None
    assert report.counts.published and report.counts.documents == 2
    assert world.versions() == published_once(report.counts.index_id)
    return report.counts.index_id


# ------------------------------------------------------------------------------------------------
# An identical rebuild under a longer list
# ------------------------------------------------------------------------------------------------


def test_index_refresh_records_a_longer_list_beside_the_manifest_without_uploading_the_index(
    world: BucketWorld,
) -> None:
    index_id = first_publish(world)
    manifest_before = world.body(key(index_id, SEARCH_INDEX_MANIFEST_NAME))
    pointer_before = world.pointer()
    world.suppress(STOPS_NOTHING)

    report = world.refresh()

    assert report.counts is not None
    assert world.builder.builds == 2, "the suppression digest changed, so the stage rebuilt"
    assert report.counts.index_id == index_id, "the entry stops nothing: the same bytes, the same id"
    assert report.outcome is StageOutcome.COMPLETED
    assert (report.counts.built, report.counts.published) == (True, False)
    assert world.versions() == {**published_once(index_id), record_key(index_id): 1}, (
        "the record is put once, and no object of the index, nor the pointer, again"
    )
    assert world.body(key(index_id, SEARCH_INDEX_MANIFEST_NAME)) == manifest_before
    assert world.pointer() == pointer_before

    record = world.record(index_id)
    published = SearchIndexManifest.model_validate_json(manifest_before)
    assert record.index_id == index_id
    assert record.manifest_sha256 == pointer_before.manifest_sha256
    assert (published.suppression.entries, record.suppression.entries) == (1, 2)
    assert record.suppression.sha256 == world.suppression_digest()
    assert record.stores == published.stores
    assert record.counts == published.counts, "an entry that stops nothing changes no count"
    assert "which current.json names" in report.reason
    assert (
        "recorded what it was checked against beside its manifest, checked-against.json: the suppression "
        "list at 2 entries and 0 path holds, where it said 1 and 0"
    ) in report.reason


def test_index_refresh_records_a_longer_list_after_a_rebuild_from_nothing_as_the_cloud_rebuilds(
    world: BucketWorld,
) -> None:
    """The cloud's working copy holds no index of its own: a changed digest rebuilds from the store."""
    index_id = first_publish(world)
    world.forget_local_indexes()
    world.suppress(STOPS_NOTHING)

    report = world.refresh()

    assert report.counts is not None and report.counts.index_id == index_id
    assert world.versions() == {**published_once(index_id), record_key(index_id): 1}
    assert world.record(index_id).suppression.entries == 2


def test_index_refresh_writes_the_record_again_for_a_list_longer_still_and_nothing_else(
    world: BucketWorld,
) -> None:
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.refresh()
    world.suppress(suppression_of("Invented evidence nobody disclosed either"))

    report = world.refresh()

    assert report.counts is not None and report.counts.index_id == index_id
    assert world.versions() == {**published_once(index_id), record_key(index_id): 2}
    assert world.record(index_id).suppression.entries == 3
    assert "the suppression list at 3 entries and 0 path holds, where it said 2 and 0" in report.reason


# ------------------------------------------------------------------------------------------------
# The same list writes nothing
# ------------------------------------------------------------------------------------------------


def test_index_refresh_rebuilding_under_the_list_the_manifest_names_writes_nothing(
    world: BucketWorld,
) -> None:
    index_id = first_publish(world)
    world.forget_local_indexes()

    report = world.refresh()

    assert world.builder.builds == 2, "nothing on this machine to keep: the stage rebuilt"
    assert report.counts is not None and report.counts.index_id == index_id
    assert report.outcome is StageOutcome.COMPLETED
    assert "current.json already names it" in report.reason
    assert "recorded" not in report.reason
    assert world.versions() == published_once(index_id), "nothing was put"


def test_index_refresh_rebuilding_under_the_list_the_record_names_writes_nothing(world: BucketWorld) -> None:
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.refresh()
    recorded = world.versions()
    world.forget_local_indexes()

    rebuilt = world.refresh()
    kept = world.refresh()

    assert world.builder.builds == 3
    assert rebuilt.counts is not None and rebuilt.counts.index_id == index_id
    assert "recorded" not in rebuilt.reason
    assert kept.outcome is StageOutcome.SKIPPED
    assert "which current.json names: nothing to build or publish" in kept.reason
    assert world.versions() == recorded == {**published_once(index_id), record_key(index_id): 1}


def test_index_refresh_a_record_beside_another_manifest_is_not_read(world: BucketWorld) -> None:
    """A record names the manifest it stands beside by digest: one naming another is not this one's."""
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.refresh()
    stale = json.loads(world.body(record_key(index_id)))
    stale["manifest_sha256"] = "0" * 64
    world.reads.put_object(Bucket=world.bucket, Key=record_key(index_id), Body=json.dumps(stale).encode())
    world.forget_local_indexes()

    report = world.refresh()

    assert "where it said 1 and 0" in report.reason, "what the manifest says, not the stale record"
    assert world.record(index_id).manifest_sha256 == world.pointer().manifest_sha256


# ------------------------------------------------------------------------------------------------
# A different index publishes as before
# ------------------------------------------------------------------------------------------------


def test_index_refresh_a_different_index_is_published_as_before_and_records_nothing(
    world: BucketWorld,
) -> None:
    first = first_publish(world)
    write_store(world.parsed, OPENEV_STORE, [*CAMP_TEXTS, "Invented later camp evidence"])
    world.suppress(STOPS_NOTHING)

    report = world.refresh()

    assert report.counts is not None and report.counts.published
    second = report.counts.index_id
    assert second != first
    assert world.pointer().index_id == second
    assert world.versions() == {
        **published_once(first),
        key(second, SEARCH_INDEX_GZIP_NAME): 1,
        key(second, SEARCH_INDEX_MANIFEST_NAME): 1,
        SEARCH_INDEX_POINTER_KEY: 2,
    }
    published = SearchIndexManifest.model_validate_json(world.body(key(second, SEARCH_INDEX_MANIFEST_NAME)))
    assert published.suppression.entries == 2, "a new index's manifest names the list it was built from"


# ------------------------------------------------------------------------------------------------
# Under the run's lock
# ------------------------------------------------------------------------------------------------


@dataclass
class Locked:
    world: BucketWorld
    lock: BucketRunLock
    clock: Clock

    def lock_versions(self) -> int:
        listed = self.world.reads.list_object_versions(Bucket=self.world.bucket, Prefix=RUN_LOCK_KEY)
        return len(listed.get("Versions", []))


@pytest.fixture
def locked(tmp_path: Path, s3_client: S3Client, evidence_bucket: str, aws_region: str) -> Locked:
    """The run holds the bucket's lock, and the client the index is published through asks it first."""
    clock = Clock()
    seed = BucketRunLock(
        store=S3LockObject(bucket=evidence_bucket, key=RUN_LOCK_KEY, client=s3_client),
        environment="dev",
        clock=clock,
        kind=HolderKind.MAC,
    )
    seed.create(command="caselist seed-run-state")
    seed.release()
    lock = BucketRunLock(
        store=S3LockObject(bucket=evidence_bucket, key=RUN_LOCK_KEY, client=s3_client),
        environment="dev",
        clock=clock,
        kind=HolderKind.CLOUD,
    )
    lock.take(command="caselist pull")
    fenced: S3Client = boto3.client("s3", region_name=aws_region)  # pyright: ignore[reportUnknownMemberType]
    fence_client(fenced, lock)
    return Locked(BucketWorld(tmp_path, reads=s3_client, bucket=evidence_bucket, writes=fenced), lock, clock)


def test_index_refresh_writes_the_record_under_the_runs_lock(locked: Locked) -> None:
    """A named object's write renews the lease first: the record's write is one renewal of the lock."""
    world = locked.world
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    before = locked.lock_versions()

    report = world.refresh()

    assert report.outcome is StageOutcome.COMPLETED
    assert world.record(index_id).suppression.entries == 2
    assert locked.lock_versions() == before + 1, (
        "the record's write renewed the lease, and nothing else wrote"
    )


def test_index_refresh_writes_no_record_once_the_runs_lease_was_taken(
    locked: Locked, s3_client: S3Client, evidence_bucket: str
) -> None:
    world = locked.world
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    locked.clock.now += LEASE + CLOCK_SKEW_MARGIN + timedelta(seconds=1)
    BucketRunLock(
        store=S3LockObject(bucket=evidence_bucket, key=RUN_LOCK_KEY, client=s3_client),
        environment="dev",
        clock=locked.clock,
        kind=HolderKind.MAC,
    ).take(command="caselist backfile-import")

    report = world.refresh()

    assert report.outcome is StageOutcome.FAILED
    assert isinstance(report.failure, RunLockLost)
    assert "the record of what it was checked against was not written" in report.reason
    assert world.versions() == published_once(index_id), "no record, and nothing else, was written"
    assert report.hint is not None and "tub index publish" not in report.hint


def test_index_refresh_record_pends_when_the_session_expires_before_it_is_written(world: BucketWorld) -> None:
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.session_expires_at = record_key(index_id)

    pended = world.refresh()
    world.session_expires_at = None
    caught_up = world.refresh()

    assert pended.outcome is StageOutcome.PENDING
    assert (
        "the record of what it was checked against is not written, for want of an AWS login" in pended.reason
    )
    assert "the next run with a session writes it" in pended.reason
    assert caught_up.outcome is StageOutcome.COMPLETED
    assert world.builder.builds == 2, "the index built while the session lasted is kept, not rebuilt"
    assert world.versions() == {**published_once(index_id), record_key(index_id): 1}


# ------------------------------------------------------------------------------------------------
# An older reader does not read it
# ------------------------------------------------------------------------------------------------


def test_index_refresh_record_is_never_read_by_the_function_which_loads_the_index_as_before(
    world: BucketWorld, tmp_path: Path
) -> None:
    """The function's holder reads the three keys the pointer names and nothing else.

    Its read path is the one the deployed function runs: `search_index_holder.py` and its S3 source
    are unchanged since `v1.1.0-dev.200`, the installed build.
    """
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.refresh()
    assert record_key(index_id) in world.versions()
    read: list[str] = []

    def reading(params: dict[str, Any], **_: object) -> None:
        read.append(str(params.get("Key")))

    world.reads.meta.events.register("before-parameter-build.s3.GetObject", reading)
    holder = SearchIndexHolder(
        S3SearchIndexSource(bucket=world.bucket, client=world.reads),
        directory=tmp_path / "function-tmp",
        open_reader=lambda path, index_id: SqliteSearchIndexReader(path, index_id=index_id),
        clock=Clock(),
    )
    try:
        with holder.lease() as search:
            assert search.search("growth").hits
        assert holder.loaded_index_id == index_id
    finally:
        holder.close()
    assert read == [
        SEARCH_INDEX_POINTER_KEY,
        key(index_id, SEARCH_INDEX_MANIFEST_NAME),
        key(index_id, SEARCH_INDEX_GZIP_NAME),
    ]


def test_index_refresh_record_bytes_name_no_path_and_are_written_like_the_manifest(
    world: BucketWorld,
) -> None:
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.refresh()

    raw = world.body(record_key(index_id))

    assert raw == world.record(index_id).to_json_bytes()
    assert raw.endswith(b"\n") and raw.startswith(b'{\n  "record_version": 1,')
    assert str(world.root).encode() not in raw
    assert hashlib.sha256(world.body(key(index_id, SEARCH_INDEX_MANIFEST_NAME))).hexdigest() == (
        world.record(index_id).manifest_sha256
    )


# ------------------------------------------------------------------------------------------------
# A run's restore brings it back with the manifest, for the stage and the comparison
# ------------------------------------------------------------------------------------------------


def restored_index(world: BucketWorld, copy: Path) -> Path:
    """What `caselist restore-run-state` restores of the published index into a new working copy."""
    copy.mkdir()
    state = run_state(copy, world.reads, world.bucket)
    index_id = asyncio.run(state._restore_index_manifest())  # pyright: ignore[reportPrivateUsage]
    assert index_id is not None
    return copy / SEARCH_INDEX_DIRECTORY / index_id


def test_index_refresh_record_comes_back_beside_the_manifest_a_run_restores(
    world: BucketWorld, tmp_path: Path
) -> None:
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.refresh()

    directory = restored_index(world, tmp_path / "working-copy")

    assert directory.name == index_id
    assert sorted(one.name for one in directory.iterdir()) == [
        CHECKED_AGAINST_NAME,
        SEARCH_INDEX_MANIFEST_NAME,
        RESTORED_INDEX_MARKER,
    ]
    assert (directory / CHECKED_AGAINST_NAME).read_bytes() == world.body(record_key(index_id))
    assert (directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes() == world.body(
        key(index_id, SEARCH_INDEX_MANIFEST_NAME)
    )


def test_index_refresh_restore_without_a_record_restores_the_manifest_alone(
    world: BucketWorld, tmp_path: Path
) -> None:
    first_publish(world)

    directory = restored_index(world, tmp_path / "working-copy")

    assert sorted(one.name for one in directory.iterdir()) == [
        SEARCH_INDEX_MANIFEST_NAME,
        RESTORED_INDEX_MARKER,
    ]


def test_index_refresh_restore_leaves_out_a_record_beside_another_manifest(
    world: BucketWorld, tmp_path: Path
) -> None:
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    world.refresh()
    stale = json.loads(world.body(record_key(index_id)))
    stale["manifest_sha256"] = "0" * 64
    world.reads.put_object(Bucket=world.bucket, Key=record_key(index_id), Body=json.dumps(stale).encode())

    directory = restored_index(world, tmp_path / "working-copy")

    assert sorted(one.name for one in directory.iterdir()) == [
        SEARCH_INDEX_MANIFEST_NAME,
        RESTORED_INDEX_MARKER,
    ]

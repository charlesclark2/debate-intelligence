"""An identical index is neither rebuilt nor republished once its record says so (`v1-e39-t25`, ac1).

`v1-e39-t19` made an identical rebuild under a longer suppression list write `checked-against.json`
beside the manifest instead of republishing. Two things went on doing the work again:

* **The weekly stage on the cloud.** Each run restores the published manifest, and the record
  beside it, into an empty working copy. The manifest names the list the index was first built
  from, so its digest differs from the bucket's list and the stage rebuilt the same index every
  week, minutes of the run for an index it then did not publish. Now a restored manifest whose
  record matches the sources is the index kept current, and the stage skips the rebuild.
* **`tub index publish --newest`** on the index `current.json` already names uploaded it whole again,
  the gzip object, the manifest and the pointer, and every environment's function downloaded it
  again. Now it records, as the stage does, or is refused when there is nothing to record.

Against moto's versioned S3 through the real adapter, as t19's suite is, whose world and fixtures
this reuses: every PUT is a version of its key, so "nothing uploaded" is the bucket's count, not a
wrapper's. Every expected value is written by hand from the stores a test builds.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.run_lock import (
    CLOCK_SKEW_MARGIN,
    LEASE,
    RUN_LOCK_KEY,
    BucketRunLock,
    HolderKind,
    RunLockLost,
)
from debate_core.application.caselist_sync import StageOutcome
from debate_core.application.ports.parsed_store import OPENEV_STORE
from debate_core.application.search_index_publish import (
    CHECKED_AGAINST_NAME,
    CheckedAgainstRecord,
    PublishedSearchIndex,
    RecordedCheck,
    SearchIndexAlreadyCurrent,
    SearchIndexFilesDamaged,
    SearchIndexPublishService,
)
from debate_core.application.search_index_refresh import RESTORED_INDEX_MARKER
from debate_core.domain.search_index import (
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SearchIndexManifest,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.integrations.s3.run_lock_object import S3LockObject

from .test_caselist_sync_run_state import run_state
from .test_search_index_refresh_checked_against import (
    CAMP_TEXTS,
    STOPS_NOTHING,
    BucketWorld,
    Locked,
    first_publish,
    key,
    published_once,
    record_key,
)
from .test_search_index_refresh_checked_against import locked as locked  # noqa: F401 - a fixture
from .test_search_index_refresh_checked_against import world as world  # noqa: F401 - a fixture
from .test_search_index_stage import PARSER, STORES, suppression_of, write_store

STOPS_NOTHING_EITHER: Final = suppression_of("Invented evidence nobody disclosed either")
"""A third entry for a source no store holds: the list grows again, the index does not."""


def recorded_once(world: BucketWorld) -> tuple[str, dict[str, int]]:
    """The first index published, then rebuilt under a list one entry longer, which t19 records.

    The record's one version, and the index's objects and pointer at one each, are what every test
    here counts against.
    """
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    report = world.refresh()
    assert report.counts is not None and report.counts.index_id == index_id
    assert world.builder.builds == 2
    versions = world.versions()
    assert versions == {**published_once(index_id), record_key(index_id): 1}
    return index_id, versions


def restore(world: BucketWorld) -> Path:
    """The cloud's start: an empty working copy, into which the run restores the published manifest."""
    world.forget_local_indexes()
    index_id = asyncio.run(
        run_state(world.data_dir, world.reads, world.bucket)._restore_index_manifest()  # pyright: ignore[reportPrivateUsage]
    )
    assert index_id is not None
    return world.out / index_id


# ------------------------------------------------------------------------------------------------
# The weekly stage skips the rebuild its restored record matches
# ------------------------------------------------------------------------------------------------


def test_search_index_stage_skips_the_rebuild_a_restored_record_matches_and_writes_nothing(
    world: BucketWorld,
) -> None:
    index_id, recorded = recorded_once(world)
    directory = restore(world)
    assert sorted(one.name for one in directory.iterdir()) == [
        CHECKED_AGAINST_NAME,
        SEARCH_INDEX_MANIFEST_NAME,
        RESTORED_INDEX_MARKER,
    ], "the premise: the restore brought the record back beside the manifest"
    manifest = SearchIndexManifest.model_validate_json((directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes())
    assert manifest.suppression.entries == 1 and manifest.suppression.sha256 != world.suppression_digest(), (
        "the premise: the restored manifest alone would rebuild"
    )

    report = world.refresh()

    assert world.builder.builds == 2, "not rebuilt"
    assert report.outcome is StageOutcome.SKIPPED
    assert report.counts is not None
    assert (report.counts.index_id, report.counts.built, report.counts.published) == (index_id, False, False)
    assert report.counts.documents == 2, (
        "the record's count: one caselist card stopped, one kept, one camp card"
    )
    assert (
        f"unchanged since {index_id}, which {CHECKED_AGAINST_NAME} beside its restored manifest says was "
        "checked against these sources, so it is not rebuilt"
    ) in report.reason
    assert "which current.json names: nothing to build or publish" in report.reason
    assert world.versions() == recorded, "no version of the object, the manifest, the pointer or the record"


def test_search_index_stage_skipping_the_rebuild_writes_not_even_the_runs_lock(locked: Locked) -> None:
    """The skip only reads: the lease is not renewed, since nothing is written that it fences."""
    world = locked.world
    _, recorded = recorded_once(world)
    restore(world)
    before = locked.lock_versions()

    report = world.refresh()

    assert report.outcome is StageOutcome.SKIPPED
    assert world.builder.builds == 2
    assert locked.lock_versions() == before
    assert world.versions() == recorded


def test_search_index_stage_rebuilds_when_the_list_grew_past_what_the_restored_record_names(
    world: BucketWorld,
) -> None:
    index_id, _ = recorded_once(world)
    restore(world)
    world.suppress(STOPS_NOTHING_EITHER)

    report = world.refresh()

    assert world.builder.builds == 3, "the suppression digest differs from the record's: rebuilt"
    assert report.counts is not None and report.counts.index_id == index_id
    assert report.outcome is StageOutcome.COMPLETED
    assert "not rebuilt" not in report.reason
    assert "the suppression list at 3 entries and 0 path holds, where it said 2 and 0" in report.reason
    assert world.versions() == {**published_once(index_id), record_key(index_id): 2}, (
        "one more version of the record, and none of the index or the pointer"
    )


def test_search_index_stage_rebuilds_and_publishes_when_a_store_changed_past_the_restored_record(
    world: BucketWorld,
) -> None:
    first, _ = recorded_once(world)
    restore(world)
    write_store(world.parsed, OPENEV_STORE, [*CAMP_TEXTS, "Invented later camp evidence"])

    report = world.refresh()

    assert world.builder.builds == 3
    assert report.counts is not None and report.counts.published
    second = report.counts.index_id
    assert second != first
    assert world.pointer().index_id == second
    assert world.versions() == {
        **published_once(first),
        record_key(first): 1,
        key(second, SEARCH_INDEX_GZIP_NAME): 1,
        key(second, SEARCH_INDEX_MANIFEST_NAME): 1,
        SEARCH_INDEX_POINTER_KEY: 2,
    }


def test_search_index_stage_rebuilds_when_the_restored_record_names_another_parser_version(
    world: BucketWorld,
) -> None:
    index_id, recorded = recorded_once(world)
    directory = restore(world)
    record = json.loads((directory / CHECKED_AGAINST_NAME).read_bytes())
    record["parser_version"] = "2025.12.01-synthetic-0"
    (directory / CHECKED_AGAINST_NAME).write_text(json.dumps(record), encoding="utf-8")

    report = world.refresh()

    assert world.builder.builds == 3, "an index of another parser's rows is not this build's: rebuilt"
    assert report.counts is not None and report.counts.index_id == index_id
    assert "not rebuilt" not in report.reason
    assert world.versions() == recorded, "the bucket's record already says what the rebuild read"


def test_search_index_stage_a_restored_record_naming_another_manifest_is_not_trusted(
    world: BucketWorld,
) -> None:
    """A record names the manifest it stands beside by digest; one naming another says nothing of this one.

    The bucket holds no record here, so the restored manifest alone would rebuild. A record planted
    beside it matches the sources in every field but `manifest_sha256`: trusting it would skip.
    """
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    directory = restore(world)
    assert not (directory / CHECKED_AGAINST_NAME).exists()
    restored = SearchIndexManifest.model_validate_json((directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes())
    sources = asyncio.run(world.builder.sources(STORES))
    planted = CheckedAgainstRecord(
        index_id=index_id,
        manifest_sha256="0" * 64,
        parser_version=PARSER,
        stores=sources.stores,
        snapshot=restored.snapshot,
        suppression=sources.suppression_list,
        counts=restored.counts,
    )
    assert (
        planted.manifest_sha256
        != hashlib.sha256((directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes()).hexdigest()
    )
    (directory / CHECKED_AGAINST_NAME).write_bytes(planted.to_json_bytes())

    report = world.refresh()

    assert world.builder.builds == 2, "the planted record is not read: rebuilt"
    assert "not rebuilt" not in report.reason
    assert world.versions() == {**published_once(index_id), record_key(index_id): 1}
    assert world.record(index_id).manifest_sha256 == world.pointer().manifest_sha256


# ------------------------------------------------------------------------------------------------
# `tub index publish --newest` on the index current.json names records instead of republishing
# ------------------------------------------------------------------------------------------------


def publisher(world: BucketWorld) -> SearchIndexPublishService:
    """`tub index publish`'s service over the bucket the index is published through."""
    return SearchIndexPublishService(
        bucket=S3EvidenceObjectStore(bucket=world.bucket, client=world.writes), parser_version=PARSER
    )


def built_by_hand(world: BucketWorld) -> Path:
    """`tub index build` on this machine: the newest index's directory, its manifest naming today's list."""
    built = asyncio.run(world.builder.build(STORES, world.out))
    return built.directory


def test_publish_newest_on_the_current_index_records_a_longer_list_and_uploads_nothing_of_it(
    world: BucketWorld,
) -> None:
    index_id = first_publish(world)
    pointer_before = world.body(SEARCH_INDEX_POINTER_KEY)
    world.suppress(STOPS_NOTHING)
    directory = built_by_hand(world)
    assert directory.name == index_id, "the entry stops nothing: the same index"

    result = asyncio.run(publisher(world).publish_newest(directory))

    assert isinstance(result, RecordedCheck)
    assert result.key == record_key(index_id)
    assert world.versions() == {**published_once(index_id), record_key(index_id): 1}, (
        "the record once, and no version of the gzip object, the manifest or current.json"
    )
    assert world.body(SEARCH_INDEX_POINTER_KEY) == pointer_before
    assert result.pointer == world.pointer()
    assert world.record(index_id).suppression.entries == 2
    assert world.record(index_id).suppression.sha256 == world.suppression_digest()
    assert (result.replaced.suppression.entries, result.record.suppression.entries) == (1, 2)


def test_publish_newest_on_the_current_index_is_refused_when_it_is_already_recorded_so(
    world: BucketWorld,
) -> None:
    index_id = first_publish(world)
    directory = world.out / index_id
    refused_by_the_manifest = world.versions()

    with pytest.raises(SearchIndexAlreadyCurrent) as first:
        asyncio.run(publisher(world).publish_newest(directory))

    assert world.versions() == refused_by_the_manifest == published_once(index_id)
    assert first.value.index_id == index_id
    assert "already current" in str(first.value) and "Nothing was written" in str(first.value)
    assert first.value.hint is not None and "--index" in first.value.hint

    world.suppress(STOPS_NOTHING)
    asyncio.run(publisher(world).publish_newest(built_by_hand(world)))
    recorded = world.versions()

    with pytest.raises(SearchIndexAlreadyCurrent):
        asyncio.run(publisher(world).publish_newest(world.out / index_id))
    assert world.versions() == recorded == {**published_once(index_id), record_key(index_id): 1}


def test_publish_newest_on_another_index_publishes_it_as_before(world: BucketWorld) -> None:
    first = first_publish(world)
    write_store(world.parsed, OPENEV_STORE, [*CAMP_TEXTS, "Invented later camp evidence"])
    directory = built_by_hand(world)

    result = asyncio.run(publisher(world).publish_newest(directory))

    assert isinstance(result, PublishedSearchIndex)
    assert (result.index_id, result.replaced) == (directory.name, first)
    assert world.pointer().index_id == directory.name
    assert world.versions() == {
        **published_once(first),
        key(directory.name, SEARCH_INDEX_GZIP_NAME): 1,
        key(directory.name, SEARCH_INDEX_MANIFEST_NAME): 1,
        SEARCH_INDEX_POINTER_KEY: 2,
    }


def test_publish_newest_never_records_from_a_restored_directory(world: BucketWorld) -> None:
    """A restored manifest holds no index files: refused as before, and nothing is written."""
    index_id, recorded = recorded_once(world)
    directory = restore(world)
    world.suppress(STOPS_NOTHING_EITHER)

    with pytest.raises(SearchIndexFilesDamaged):
        asyncio.run(publisher(world).publish_newest(directory))

    assert world.versions() == recorded
    assert world.record(index_id).suppression.entries == 2


def test_publish_newest_writes_the_record_under_the_runs_lock(locked: Locked) -> None:
    world = locked.world
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    directory = built_by_hand(world)
    before = locked.lock_versions()

    result = asyncio.run(publisher(world).publish_newest(directory))

    assert isinstance(result, RecordedCheck)
    assert locked.lock_versions() == before + 1, (
        "the record's write renewed the lease, and nothing else wrote"
    )
    assert world.versions() == {**published_once(index_id), record_key(index_id): 1}


def test_publish_newest_writes_no_record_once_the_runs_lease_was_taken(locked: Locked) -> None:
    world = locked.world
    index_id = first_publish(world)
    world.suppress(STOPS_NOTHING)
    directory = built_by_hand(world)
    locked.clock.now += LEASE + CLOCK_SKEW_MARGIN + timedelta(seconds=1)
    BucketRunLock(
        store=S3LockObject(bucket=world.bucket, key=RUN_LOCK_KEY, client=world.reads),
        environment="dev",
        clock=locked.clock,
        kind=HolderKind.MAC,
    ).take(command="caselist backfile-import")

    with pytest.raises(RunLockLost):
        asyncio.run(publisher(world).publish_newest(directory))

    assert world.versions() == published_once(index_id), "no record, and nothing else, was written"

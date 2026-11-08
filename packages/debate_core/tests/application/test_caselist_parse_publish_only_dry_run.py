"""The plan `caselist parse --publish-only --dry-run` prints, and what it leaves alone (`v1-e31-t40`).

:meth:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher.plan` is the publish
with every write taken out: the same suppression list and held uploads, the same occurrence table
guard, the same digest comparison, the aggregates after the per-source files. These tests hold it,
over the fictional caselist of `test_caselist_parse.py`, to:

* the counts of each kind, written here by hand from the fixture's table: the six sources of
  09-01 and 09-08 (`verbatim`, `wiki`, `pdf`, `cardmirror`, `doc`, `broken`) each have a
  per-source file, the directory has three aggregates (no camp paths outside `openev`) and one
  placement state;
* the bytes of each object, measured on disk here, not by the code under test;
* the publish that follows doing exactly what the plan said, object by object;
* the occurrence table guard refusing the plan as it refuses the publish;
* nothing written, to the bucket or to the parsed store.

The "bucket" is an object store on disk that computes digests as S3 records them.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, digest_of, import_weeks

from debate_core.application import caselist_parse as caselist_parse_module
from debate_core.application.caselist import occurrence_table_guard, parsed_publish_only
from debate_core.application.caselist.occurrence_table_guard import NewerFingerprintTable
from debate_core.application.caselist.parsed_publish import (
    ParsedObjectKind,
    ParsedPublishPlan,
    PlannedAction,
)
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.errors import error_code_of
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.local import FsEvidenceObjectStore

from .test_caselist_parse import THROUGH_0908, World
from .test_caselist_parse_publish_only import a_bucket, publisher_to, restamp

pytestmark = pytest.mark.anyio

PER_SOURCE, AGGREGATES, PLACEMENT = (
    ParsedObjectKind.PER_SOURCE_FILES,
    ParsedObjectKind.AGGREGATES,
    ParsedObjectKind.PLACEMENT_STATE,
)
UPLOAD, PRESENT, SUPPRESSED, BLOCKED = (
    PlannedAction.UPLOAD,
    PlannedAction.PRESENT,
    PlannedAction.SUPPRESSED,
    PlannedAction.BLOCKED,
)
#: Written by hand from the fixture's table (module docstring).
SOURCES_THROUGH_0908: Final = 6
AGGREGATES_OF_A_WEEKLY_STORE: Final = 3
BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
PREFIX: Final = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def world(tmp_path: Path) -> World:
    """09-01 and 09-08 imported and parsed, nothing published."""
    built = World(data_dir=tmp_path / "evidence", zips_dir=tmp_path / "zips")
    await import_weeks(built.data_dir, built.zips_dir, through=THROUGH_0908)
    await built.run()
    return built


@pytest.fixture
def as_build(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    def at(version: str) -> None:
        monkeypatch.setattr(caselist_parse_module, "FINGERPRINT_VERSION", version)
        monkeypatch.setattr(occurrence_table_guard, "FINGERPRINT_VERSION", version)
        monkeypatch.setattr(parsed_publish_only, "FINGERPRINT_VERSION", version)

    return at


def on_disk(world: World) -> dict[str, int]:
    """Every file of the version directory by its bucket key, with its size as the filesystem gives it."""
    root = world.store.root / CASELIST / DOCX_PARSER_VERSION
    return {
        PREFIX + path.relative_to(root).as_posix(): path.stat().st_size
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def kind_by_hand(key: str) -> ParsedObjectKind:
    """The kind of a key, by the layout in `docs/data/parsed-card-store.md`."""
    if key.removeprefix(PREFIX).startswith("sha256/"):
        return PER_SOURCE
    return PLACEMENT if key.endswith("/placement-state.sqlite") else AGGREGATES


def keys(plan: ParsedPublishPlan, action: PlannedAction) -> list[str]:
    return sorted(one.key for one in plan.objects if one.action is action)


def counts(plan: ParsedPublishPlan, action: PlannedAction) -> tuple[int, int, int]:
    return (plan.count(action, PER_SOURCE), plan.count(action, AGGREGATES), plan.count(action, PLACEMENT))


def state_of(*roots: Path) -> dict[str, tuple[bytes, int]]:
    """Every file and directory under `roots`, with bytes and when each was last written."""
    found: dict[str, tuple[bytes, int]] = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            found[str(path)] = (path.read_bytes() if path.is_file() else b"<dir>", path.stat().st_mtime_ns)
    return found


async def plan_to(world: World, remote: FsEvidenceObjectStore) -> ParsedPublishPlan:
    return await publisher_to(world, remote).plan(CASELIST, DOCX_PARSER_VERSION)


# ------------------------------------------------------------------------------------------------
# What the plan lists, and the publish that follows
# ------------------------------------------------------------------------------------------------


async def test_a_plan_over_an_empty_bucket_uploads_the_whole_directory_and_the_publish_then_uploads_those(
    world: World, tmp_path: Path
) -> None:
    bucket = a_bucket(tmp_path, "prod-bucket")
    sizes = on_disk(world)

    plan = await plan_to(world, bucket)

    assert counts(plan, UPLOAD) == (SOURCES_THROUGH_0908, AGGREGATES_OF_A_WEEKLY_STORE, 1)
    assert counts(plan, PRESENT) == counts(plan, SUPPRESSED) == counts(plan, BLOCKED) == (0, 0, 0)
    assert {one.key: (one.kind, one.size) for one in plan.objects} == {
        key: (kind_by_hand(key), size) for key, size in sizes.items()
    }
    for kind in (PER_SOURCE, AGGREGATES, PLACEMENT):
        assert plan.size(UPLOAD, kind) == sum(
            size for key, size in sizes.items() if kind_by_hand(key) is kind
        )
    assert plan.count(UPLOAD) == len(sizes)
    assert plan.size(UPLOAD) == sum(sizes.values())
    assert (plan.caselist, plan.version, plan.prefix) == (CASELIST, DOCX_PARSER_VERSION, PREFIX)
    assert not plan.aggregates_withheld
    assert await bucket.list_objects("") == ()

    published = await publisher_to(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    uploaded = sorted(one.key for one in published.objects if one.result is SourceResult.UPLOADED)
    assert uploaded == keys(plan, UPLOAD)
    assert published.count(SourceResult.UPLOADED) == plan.count(UPLOAD)


async def test_after_a_partial_publish_the_plan_lists_what_the_bucket_holds_as_present_and_writes_nothing(
    world: World, tmp_path: Path
) -> None:
    """Two per-source files and the index never reached the bucket: those are the plan's uploads,
    everything else is present with the bytes it has on disk, and the publish skips exactly that."""
    bucket = a_bucket(tmp_path, "dev-bucket")
    await publisher_to(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)
    lost = [f"{PREFIX}index.jsonl", *(key for key in on_disk(world) if digest_of("wiki") in key)]
    lost.append(next(key for key in on_disk(world) if digest_of("pdf") in key))
    for key in lost:
        bucket.path_for(key).unlink()
    sizes = on_disk(world)
    before = state_of(tmp_path / "dev-bucket", world.data_dir)

    plan = await plan_to(world, bucket)

    assert state_of(tmp_path / "dev-bucket", world.data_dir) == before
    assert keys(plan, UPLOAD) == sorted(lost)
    assert counts(plan, UPLOAD) == (2, 1, 0)
    assert counts(plan, PRESENT) == (SOURCES_THROUGH_0908 - 2, AGGREGATES_OF_A_WEEKLY_STORE - 1, 1)
    assert plan.size(UPLOAD) == sum(sizes[key] for key in lost)
    assert plan.size(PRESENT) == sum(size for key, size in sizes.items() if key not in lost)

    published = await publisher_to(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    skipped = sorted(one.key for one in published.objects if one.result is SourceResult.SKIPPED)
    assert skipped == keys(plan, PRESENT)
    assert published.count(SourceResult.UPLOADED) == len(lost)


async def test_a_source_the_list_stops_is_planned_suppressed_with_its_bytes_as_the_publish_withholds_it(
    world: World, tmp_path: Path
) -> None:
    await world.suppress(digest_of("wiki"))
    await world.run()
    bucket = a_bucket(tmp_path, "prod-bucket")
    [wiki] = [key for key in on_disk(world) if digest_of("wiki") in key]

    plan = await plan_to(world, bucket)

    assert keys(plan, SUPPRESSED) == [wiki]
    assert counts(plan, SUPPRESSED) == (1, 0, 0)
    assert plan.size(SUPPRESSED) == on_disk(world)[wiki]
    assert counts(plan, UPLOAD) == (SOURCES_THROUGH_0908 - 1, AGGREGATES_OF_A_WEEKLY_STORE, 1)
    published = await publisher_to(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)
    assert [one.key for one in published.objects if one.result is SourceResult.SUPPRESSED] == [wiki]


async def test_a_per_source_file_the_bucket_holds_with_other_bytes_is_blocked_and_no_aggregate_is_planned(
    world: World, tmp_path: Path
) -> None:
    """The publish would fail that file and withhold the aggregates, so the plan lists none of them."""
    bucket = a_bucket(tmp_path, "dev-bucket")
    [cardmirror] = [key for key in on_disk(world) if digest_of("cardmirror") in key]
    bucket.path_for(cardmirror).parent.mkdir(parents=True)
    bucket.path_for(cardmirror).write_bytes(b"other bytes under the same key\n")

    plan = await plan_to(world, bucket)

    assert keys(plan, BLOCKED) == [cardmirror]
    assert plan.blocked_codes == ("CHECKSUM_MISMATCH",)
    assert plan.blocked_keys == (cardmirror,)
    assert plan.aggregates_withheld
    assert counts(plan, UPLOAD) == (SOURCES_THROUGH_0908 - 1, 0, 0)
    assert [one.kind for one in plan.objects if one.kind is not PER_SOURCE] == []
    published = await publisher_to(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)
    assert published.failed_keys == (cardmirror,)
    assert published.aggregates_withheld


async def test_an_aggregate_the_bucket_holds_with_other_bytes_is_an_upload_that_replaces_it(
    world: World, tmp_path: Path
) -> None:
    bucket = a_bucket(tmp_path, "dev-bucket")
    await publisher_to(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)
    bucket.path_for(f"{PREFIX}failures.jsonl").write_bytes(b"an older rebuild's failures\n")

    plan = await plan_to(world, bucket)

    assert keys(plan, UPLOAD) == [f"{PREFIX}failures.jsonl"]
    assert counts(plan, PRESENT) == (SOURCES_THROUGH_0908, AGGREGATES_OF_A_WEEKLY_STORE - 1, 1)
    assert not plan.blocked_keys
    published = await publisher_to(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)
    assert [one.key for one in published.objects if one.result is SourceResult.UPLOADED] == [
        f"{PREFIX}failures.jsonl"
    ]


# ------------------------------------------------------------------------------------------------
# The publisher's own refusal, asked alike
# ------------------------------------------------------------------------------------------------


async def test_a_newer_occurrence_table_in_the_bucket_refuses_the_plan_as_it_refuses_the_publish(
    tmp_path: Path, as_build: Callable[[str], None]
) -> None:
    """A world of its own, parsed by a build at a synthetic fingerprint version from the start."""
    as_build(BUILD)
    world = World(data_dir=tmp_path / "evidence-at-v7", zips_dir=tmp_path / "zips-at-v7")
    await import_weeks(world.data_dir, world.zips_dir, through=THROUGH_0908)
    await world.run()
    version = DOCX_PARSER_VERSION
    assert {row["fingerprint_version"] for row in world.lines("occurrences.jsonl")} == {BUILD}
    bucket = a_bucket(tmp_path, "prod-bucket")
    table = world.store.root / CASELIST / version / "occurrences.jsonl"
    newer = tmp_path / "newer-occurrences.jsonl"
    newer.write_bytes(table.read_bytes())
    restamp(newer, NEWER)
    await bucket.put_file(f"parsed/{CASELIST}/{version}/occurrences.jsonl", newer)
    before = state_of(tmp_path / "prod-bucket", world.data_dir)
    publisher = publisher_to(world, bucket)

    with pytest.raises(NewerFingerprintTable) as planned:
        await publisher.plan(CASELIST, version)
    assert state_of(tmp_path / "prod-bucket", world.data_dir) == before
    with pytest.raises(NewerFingerprintTable) as published:
        await publisher.publish(CASELIST, version)

    assert (error_code_of(planned.value), str(planned.value)) == (
        error_code_of(published.value),
        str(published.value),
    )
    assert NEWER in str(planned.value)

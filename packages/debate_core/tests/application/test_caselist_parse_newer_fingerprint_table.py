"""The parse pipeline and the parsed store's publish refuse a table a newer build stamped (`v1-e34-t29`).

`caselist parse`, with or without `--publish`, and the weekly run's parse stage all run
:meth:`~debate_core.application.caselist_parse.CaselistParseService.run` and
:class:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher`. Each asks
:func:`~debate_core.application.caselist.occurrence_table_guard.refuse_newer_table` before it writes
anything, and these tests hold both to it over the fictional caselist of `test_caselist_parse.py`:

* ac1: a rebuild, a re-parse that would supersede, and a publish over a table stamped newer than the
  build are refused with both versions named, and nothing is written, here or in the bucket.
* ac2: an equal or older stamp is rebuilt, and published, exactly as a build with no guard does.
* A path that took its answer from anywhere but the rule fails `..._takes_the_rules_answer`.

Every version is synthetic (PM notes, 2026-10-20): the build is :data:`BUILD`, and a store is
stamped by running the pipeline as a build at another version first.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, digest_of, import_weeks

from debate_core.application import caselist_parse as caselist_parse_module
from debate_core.application.caselist import occurrence_table_guard
from debate_core.application.caselist.occurrence_table_guard import NewerFingerprintTable
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_caselist_parse import THROUGH_0908, THROUGH_0915, CountingParser, World, publisher, put_requests

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
OLDER: Final = "synthetic-fingerprint-v6"
TABLE: Final = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/occurrences.jsonl"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def always(newer: bool) -> Callable[[str, str], bool]:
    """A comparison that answers `newer` for every pair of versions."""

    def answer(stamped: str, build: str) -> bool:
        return newer

    return answer


@pytest.fixture
async def world(tmp_path: Path) -> World:
    """09-01 and 09-08 imported; nothing parsed yet."""
    built = World(data_dir=tmp_path / "evidence", zips_dir=tmp_path / "zips")
    await import_weeks(built.data_dir, built.zips_dir, through=THROUGH_0908)
    return built


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


@pytest.fixture
def as_build(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Run as a build at a fingerprint version: what the pipeline stamps, and what the rule compares."""

    def at(version: str) -> None:
        monkeypatch.setattr(caselist_parse_module, "FINGERPRINT_VERSION", version)
        monkeypatch.setattr(occurrence_table_guard, "FINGERPRINT_VERSION", version)

    return at


def stamps(world: World, version: str = DOCX_PARSER_VERSION) -> set[str]:
    return {row["fingerprint_version"] for row in world.lines("occurrences.jsonl", version)}


def bucket_objects(s3_client: S3Client, name: str) -> dict[str, bytes]:
    listed = s3_client.list_objects_v2(Bucket=name).get("Contents", [])
    return {
        str(item.get("Key")): s3_client.get_object(Bucket=name, Key=str(item.get("Key")))["Body"].read()
        for item in listed
    }


def refusal(store: str, stamped: str = NEWER, version: str = DOCX_PARSER_VERSION) -> str:
    return (
        f"the occurrence table of {CASELIST} {version} in {store} is stamped {stamped}, newer than this "
        f"build's {BUILD}; it was left as it was"
    )


async def a_world(tmp_path: Path, name: str, *, through: Any = THROUGH_0908) -> World:
    """Another machine's data directory, holding the same caselist."""
    other = World(data_dir=tmp_path / name, zips_dir=tmp_path / f"{name}-zips")
    await import_weeks(other.data_dir, other.zips_dir, through=through)
    return other


# ------------------------------------------------------------------------------------------------
# ac1: the parse stage
# ------------------------------------------------------------------------------------------------


async def test_a_rebuild_over_a_table_a_newer_build_stamped_is_refused_and_writes_nothing(
    world: World, as_build: Callable[[str], None]
) -> None:
    """09-15 brings a new source, so the refused run had something to parse, and parsed none of it."""
    as_build(NEWER)
    await world.run()
    await import_weeks(world.data_dir, world.zips_dir, through=THROUGH_0915, after=THROUGH_0908)
    before = world.tree()
    as_build(BUILD)
    parser = CountingParser()

    with pytest.raises(NewerFingerprintTable) as refused:
        await world.run(parser)

    assert str(refused.value) == refusal("this machine's parsed store")
    assert parser.parsed == []
    assert world.tree() == before
    assert stamps(world) == {NEWER}


async def test_a_reparse_never_supersedes_a_table_a_newer_build_stamped(
    world: World, as_build: Callable[[str], None]
) -> None:
    """A new generation would become the caselist's current table: the same as a rewrite."""
    as_build(NEWER)
    await world.run()
    as_build(BUILD)

    with pytest.raises(NewerFingerprintTable) as refused:
        await world.run(reparse=True)

    assert str(refused.value) == refusal("this machine's parsed store")
    assert await world.store.version_directories(CASELIST) == (DOCX_PARSER_VERSION,)


# ------------------------------------------------------------------------------------------------
# ac2: an equal or older stamp is rebuilt as before
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("stamped", [BUILD, OLDER])
async def test_an_equal_or_older_table_is_rebuilt_exactly_as_a_build_with_no_table_builds_it(
    world: World, as_build: Callable[[str], None], tmp_path: Path, stamped: str
) -> None:
    """09-15's new source is parsed, and the table is byte for byte the one a fresh store gets."""
    as_build(stamped)
    await world.run()
    await import_weeks(world.data_dir, world.zips_dir, through=THROUGH_0915, after=THROUGH_0908)
    as_build(BUILD)
    parser = CountingParser()

    report = await world.run(parser)

    assert parser.parsed == [digest_of("direct")]
    assert stamps(world) == {BUILD}
    fresh = await a_world(tmp_path, "fresh", through=THROUGH_0915)
    await fresh.run()
    assert world.tree()["occurrences.jsonl"] == fresh.tree()["occurrences.jsonl"]
    assert report.store is not None and report.store.occurrences == len(world.lines("occurrences.jsonl"))


@pytest.mark.parametrize("stamped", [BUILD, OLDER])
async def test_a_reparse_over_an_equal_or_older_table_starts_its_new_generation(
    world: World, as_build: Callable[[str], None], stamped: str
) -> None:
    as_build(stamped)
    await world.run()
    as_build(BUILD)

    report = await world.run(reparse=True)

    assert report.plan.superseded == DOCX_PARSER_VERSION
    assert stamps(world, report.plan.version) == {BUILD}
    assert stamps(world) == {stamped}, "the superseded directory is left as it was"


# ------------------------------------------------------------------------------------------------
# ac1: the publish stage
# ------------------------------------------------------------------------------------------------


async def test_a_publish_of_a_table_a_newer_build_stamped_is_refused_and_sends_nothing(
    world: World, as_build: Callable[[str], None], bucket: S3EvidenceObjectStore, s3_client: S3Client
) -> None:
    as_build(NEWER)
    await world.run()
    as_build(BUILD)
    puts = put_requests(s3_client)

    with pytest.raises(NewerFingerprintTable) as refused:
        await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    assert str(refused.value) == refusal("this machine's parsed store")
    assert puts == []


async def test_a_publish_over_the_buckets_table_a_newer_build_stamped_is_refused_and_sends_nothing(
    world: World,
    as_build: Callable[[str], None],
    bucket: S3EvidenceObjectStore,
    s3_client: S3Client,
    evidence_bucket: str,
    tmp_path: Path,
) -> None:
    """Another machine at the newer version published; this one, parsed here at its own, would not."""
    as_build(NEWER)
    newer_machine = await a_world(tmp_path, "newer-machine")
    await newer_machine.run()
    assert (await publisher(newer_machine, bucket).publish(CASELIST, DOCX_PARSER_VERSION)).succeeded
    held = bucket_objects(s3_client, evidence_bucket)
    as_build(BUILD)
    await world.run()
    puts = put_requests(s3_client)

    with pytest.raises(NewerFingerprintTable) as refused:
        await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    assert str(refused.value) == refusal("the bucket")
    assert puts == []
    assert bucket_objects(s3_client, evidence_bucket) == held


@pytest.mark.parametrize("stamped", [BUILD, OLDER])
async def test_a_publish_over_the_buckets_equal_or_older_table_replaces_it_as_before(
    world: World,
    as_build: Callable[[str], None],
    bucket: S3EvidenceObjectStore,
    s3_client: S3Client,
    evidence_bucket: str,
    stamped: str,
) -> None:
    """Published at `stamped`, then 09-15 parsed and published by this build: its source and the
    two aggregates it changes go up, and the bucket's table is this machine's."""
    as_build(stamped)
    await world.run()
    assert (await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)).succeeded
    as_build(BUILD)
    await import_weeks(world.data_dir, world.zips_dir, through=THROUGH_0915, after=THROUGH_0908)
    await world.run()

    report = await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    assert report.succeeded
    uploaded = {outcome.key for outcome in report.objects if outcome.result is SourceResult.UPLOADED}
    assert TABLE in uploaded and len(uploaded) == 3
    assert bucket_objects(s3_client, evidence_bucket)[TABLE] == world.tree()["occurrences.jsonl"]


# ------------------------------------------------------------------------------------------------
# Neither path decides for itself
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def the_rule_says(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Make the rule's comparison answer `newer` for every pair of versions."""

    def answer(newer: bool) -> None:
        monkeypatch.setattr(occurrence_table_guard, "is_newer_fingerprint_version", always(newer))

    return answer


async def test_the_rebuild_takes_the_rules_answer_and_has_none_of_its_own(
    world: World, as_build: Callable[[str], None], the_rule_says: Callable[[bool], None]
) -> None:
    """Refused over its own stamp when the rule says newer; rebuilt over a newer one when it says not."""
    as_build(BUILD)
    await world.run()
    the_rule_says(True)
    with pytest.raises(NewerFingerprintTable):
        await world.run()

    the_rule_says(False)
    as_build(NEWER)
    await world.run()
    as_build(BUILD)
    await world.run()
    assert stamps(world) == {BUILD}


async def test_the_publish_takes_the_rules_answer_and_has_none_of_its_own(
    world: World,
    as_build: Callable[[str], None],
    the_rule_says: Callable[[bool], None],
    bucket: S3EvidenceObjectStore,
    s3_client: S3Client,
    evidence_bucket: str,
) -> None:
    """Refused over its own stamp when the rule says newer; sent over the bucket's newer table, and
    a newer one of its own, when it says not."""
    as_build(BUILD)
    await world.run()
    the_rule_says(True)
    with pytest.raises(NewerFingerprintTable):
        await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    the_rule_says(False)
    as_build(NEWER)
    await world.run()
    as_build(BUILD)
    assert (await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)).succeeded
    as_build(OLDER)
    await world.run()
    assert (await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)).succeeded
    assert bucket_objects(s3_client, evidence_bucket)[TABLE] == world.tree()["occurrences.jsonl"]

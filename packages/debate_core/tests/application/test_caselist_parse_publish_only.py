"""Publishing the parsed store's current version directory without rebuilding it (`v1-e31-t30`).

`caselist parse --publish-only` is
:meth:`~debate_core.application.caselist_parse.CaselistParseService.publishable_version` and then
the one publisher, :meth:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher.
publish`, called as the rebuild's publish calls it. These tests hold it, over the fictional caselist
of `test_caselist_parse.py`, to:

* ac1: over a directory a rebuild just wrote, it sends exactly the objects the rebuild's publish
  sends, byte for byte, reports each as that publish does, and parses and rewrites nothing.
* ac2: a missing directory, a missing aggregate, an index naming a source with no file, a source
  parsed under another profile, and a fingerprint stamp that is not this build's are each refused
  with their own code and reason before anything is uploaded.
* A per-source record stamped with an older fingerprint version, which is what a rebuild after a
  fingerprint bump leaves, is published as the rebuild's publish publishes it.
* ac4: aggregates naming a source or a disclosure the target environment's suppression list now
  stops or holds, because they were rebuilt before it did, are refused before any upload. Over a
  list the rebuild read, it publishes as the rebuild's publish does.

The two "buckets" are object stores on disk: a refusal is checked by the second being empty.
Fingerprint versions are synthetic, as in `test_caselist_parse_newer_fingerprint_table.py`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import pytest
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import (
    CASELIST,
    R1_COPY_PATH,
    WEEKS,
    digest_of,
    import_weeks,
)

from debate_core.application import caselist_parse as caselist_parse_module
from debate_core.application.caselist import occurrence_table_guard, parsed_publish_only
from debate_core.application.caselist.parsed_publish import ParsedPublishReport, ParsedStorePublisher
from debate_core.application.caselist.parsed_publish_only import (
    ParsedAggregatesMissing,
    ParsedByAnotherParserVersion,
    ParsedFingerprintVersionMismatch,
    ParsedSourceFilesMissing,
    ParsedVersionDirectoryMissing,
    PublishOnlyRefused,
)
from debate_core.application.caselist.publish_plan import InvalidPublishTarget
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.errors import error_code_of
from debate_core.application.ports.parsed_store import AGGREGATE_NAMES, source_object_key
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.local import FsEvidenceObjectStore

from .test_caselist_parse import THROUGH_0908, THROUGH_0915, CountingParser, World

pytestmark = pytest.mark.anyio

BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
OLDER: Final = "synthetic-fingerprint-v6"
OTHER_PROFILE: Final = "2026.10.01-verbatim-2"
STOPPED_BY_THE_LIST: Final = "PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS"
#: A `--source` removal's file, taken from :data:`HELD_ONLY_PATH`; no week holds it any more.
REMOVED: Final = hashlib.sha256(b"a removed file no snapshot of this store holds").hexdigest()
#: `cardmirror`'s only path, first listed in `2026-09-08`: a hold there leaves its bytes held only.
HELD_ONLY_PATH: Final = next(path for path, body in WEEKS[1].members if body == "cardmirror")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def world(tmp_path: Path) -> World:
    """09-01 and 09-08 imported; nothing parsed yet."""
    built = World(data_dir=tmp_path / "evidence", zips_dir=tmp_path / "zips")
    await import_weeks(built.data_dir, built.zips_dir, through=THROUGH_0908)
    return built


@pytest.fixture
def as_build(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Run as a build at a fingerprint version: what the pipeline stamps, and what every rule compares."""

    def at(version: str) -> None:
        monkeypatch.setattr(caselist_parse_module, "FINGERPRINT_VERSION", version)
        monkeypatch.setattr(occurrence_table_guard, "FINGERPRINT_VERSION", version)
        monkeypatch.setattr(parsed_publish_only, "FINGERPRINT_VERSION", version)

    return at


def a_bucket(tmp_path: Path, name: str) -> FsEvidenceObjectStore:
    """An environment's evidence bucket, as a store on disk that records digests as S3 does."""
    return FsEvidenceObjectStore(tmp_path / name)


def publisher_to(world: World, remote: FsEvidenceObjectStore) -> ParsedStorePublisher:
    """The publisher as the composition root builds it, over the world's parsed store."""
    local = FsEvidenceObjectStore(world.data_dir, subdirectory=Path("parsed"))
    return ParsedStorePublisher(
        local=local,
        local_path_for=local.path_for,
        remote=remote,
        suppression=world.suppression,
        evidence=world.local,
    )


async def rebuild_and_publish(world: World, remote: FsEvidenceObjectStore) -> ParsedPublishReport:
    """`caselist parse --publish`: the rebuild, then the publish of the directory it wrote."""
    service = world.service()
    plan = await service.plan(CASELIST)
    await service.run(plan)
    return await publisher_to(world, remote).publish(CASELIST, plan.version)


async def publish_only(
    world: World, remote: FsEvidenceObjectStore, parser: CountingParser | None = None
) -> ParsedPublishReport:
    """`caselist parse --publish-only`: the check, then the same publish of the directory it names."""
    version = await world.service(parser).publishable_version(CASELIST)
    return await publisher_to(world, remote).publish(CASELIST, version)


async def contents(remote: FsEvidenceObjectStore) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for info in await remote.list_objects(""):
        found[info.key] = remote.path_for(info.key).read_bytes()
    return found


def outcomes(report: ParsedPublishReport) -> list[tuple[str, SourceResult, bool, str | None]]:
    return [(one.key, one.result, one.aggregate, one.error_code) for one in report.objects]


def written(world: World) -> dict[str, tuple[bytes, int]]:
    """Every file of the parsed store, with when it was last written: a rebuild rewrites the aggregates."""
    root = world.store.root
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def directory(world: World, version: str = DOCX_PARSER_VERSION) -> Path:
    return world.store.root / CASELIST / version


def restamp(path: Path, stamp: str) -> None:
    """Rewrite every line's `fingerprint_version`, as a build at `stamp` would have written it."""
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    path.write_text(
        "".join(json.dumps({**line, "fingerprint_version": stamp}, sort_keys=True) + "\n" for line in lines),
        encoding="utf-8",
    )


# ------------------------------------------------------------------------------------------------
# ac1: the same objects as the rebuild's publish, without a rebuild
# ------------------------------------------------------------------------------------------------


async def test_publish_only_sends_exactly_what_the_rebuilds_publish_sends_and_reports_it_alike(
    world: World, tmp_path: Path
) -> None:
    """A second environment: the rebuild published to one bucket, publish-only sends to another."""
    first, second = a_bucket(tmp_path, "dev-bucket"), a_bucket(tmp_path, "prod-bucket")
    rebuilt = await rebuild_and_publish(world, first)
    before = written(world)
    parser = CountingParser()

    published = await publish_only(world, second, parser)

    assert await contents(second) == await contents(first)
    assert outcomes(published) == outcomes(rebuilt)
    assert (published.caselist, published.version, published.prefix) == (
        rebuilt.caselist,
        rebuilt.version,
        rebuilt.prefix,
    )
    assert published.succeeded and rebuilt.succeeded
    assert published.count(SourceResult.UPLOADED) == len(before)
    assert parser.parsed == []
    assert written(world) == before


async def test_publish_only_after_a_partial_publish_sends_what_the_rebuilds_publish_would_have(
    world: World, tmp_path: Path
) -> None:
    """A publish that failed after its rebuild: both buckets hold the 09-08 store, 09-15 is rebuilt,
    and publish-only uploads the new source and the aggregates and skips the rest, as a rerun of the
    rebuild's publish does."""
    first, second = a_bucket(tmp_path, "dev-bucket"), a_bucket(tmp_path, "prod-bucket")
    await rebuild_and_publish(world, first)
    await publish_only(world, second)
    await import_weeks(world.data_dir, world.zips_dir, through=THROUGH_0915, after=THROUGH_0908)
    rebuilt = await rebuild_and_publish(world, first)

    published = await publish_only(world, second)

    assert await contents(second) == await contents(first)
    assert outcomes(published) == outcomes(rebuilt)
    # The new source's file, and the two aggregates it changes: the failures file is unchanged, as
    # `test_publish_after_a_new_snapshot_uploads_only_the_new_source_and_the_aggregates` says.
    assert published.count(SourceResult.SKIPPED) == rebuilt.count(SourceResult.SKIPPED) > 0
    assert published.count(SourceResult.UPLOADED) == rebuilt.count(SourceResult.UPLOADED) == 3


async def test_publish_only_over_an_unchanged_bucket_uploads_nothing(world: World, tmp_path: Path) -> None:
    first = a_bucket(tmp_path, "dev-bucket")
    rebuilt = await rebuild_and_publish(world, first)

    again = await publish_only(world, first)

    assert again.count(SourceResult.UPLOADED) == 0
    assert again.count(SourceResult.SKIPPED) == rebuilt.count(SourceResult.UPLOADED)


async def test_a_suppressed_source_is_withheld_by_publish_only_as_by_the_rebuilds_publish(
    world: World, tmp_path: Path
) -> None:
    """Over the list the rebuild read, the publisher withholds the source's file for both paths,
    from the same code, and the aggregates, rebuilt without it, are published."""
    first, second = a_bucket(tmp_path, "dev-bucket"), a_bucket(tmp_path, "prod-bucket")
    await world.run()
    await world.suppress(digest_of("wiki"))
    rebuilt = await rebuild_and_publish(world, first)

    published = await publish_only(world, second)

    assert outcomes(published) == outcomes(rebuilt)
    assert published.count(SourceResult.SUPPRESSED) == 1
    assert not any(digest_of("wiki") in key for key in await contents(second))


async def test_records_stamped_before_a_fingerprint_bump_are_published_as_the_rebuild_publishes_them(
    world: World, tmp_path: Path, as_build: Callable[[str], None]
) -> None:
    """After a fingerprint bump the rebuild re-parses nothing and restamps only the occurrence table,
    so the per-source records keep the older stamp, and the rebuild's publish sends them."""
    as_build(OLDER)
    await world.run()
    as_build(BUILD)
    first, second = a_bucket(tmp_path, "dev-bucket"), a_bucket(tmp_path, "prod-bucket")
    rebuilt = await rebuild_and_publish(world, first)
    assert {row["fingerprint_version"] for row in world.lines("index.jsonl")} == {OLDER}
    assert {row["fingerprint_version"] for row in world.lines("occurrences.jsonl")} == {BUILD}

    published = await publish_only(world, second)

    assert await contents(second) == await contents(first)
    assert outcomes(published) == outcomes(rebuilt)


async def test_publish_only_names_the_running_parsers_newest_generation_and_never_an_older_one(
    world: World,
) -> None:
    await world.run()
    report = await world.run(reparse=True)

    assert await world.service().publishable_version(CASELIST) == report.plan.version != DOCX_PARSER_VERSION


# ------------------------------------------------------------------------------------------------
# ac2: refused, with its reason, before any upload
# ------------------------------------------------------------------------------------------------


async def refused(world: World, tmp_path: Path, parser: CountingParser | None = None) -> PublishOnlyRefused:
    """Run publish-only expecting a refusal; check it uploaded nothing and parsed nothing."""
    remote = a_bucket(tmp_path, "refused-bucket")
    counting = parser or CountingParser()
    with pytest.raises(PublishOnlyRefused) as caught:
        await publish_only(world, remote, counting)
    assert await contents(remote) == {}
    assert counting.parsed == []
    for identifier in FICTIONAL_IDENTIFIERS:
        assert identifier not in str(caught.value) and identifier not in caught.value.hint
    return caught.value


async def test_a_caselist_never_parsed_is_refused_as_having_no_directory(
    world: World, tmp_path: Path
) -> None:
    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedVersionDirectoryMissing)
    assert error_code_of(refusal) == "PARSED_VERSION_DIRECTORY_MISSING"
    assert str(refusal) == (
        f"{CASELIST} has no version directory of parser version {DOCX_PARSER_VERSION} on this machine"
    )
    assert f"caselist parse --caselist {CASELIST} --publish`" in refusal.hint


async def test_a_directory_of_another_parser_version_is_never_published(world: World, tmp_path: Path) -> None:
    """Only the running parser's directory is named; an older parser's is not a fallback."""
    await world.run(CountingParser(parser_version="2026.01.01-docx-1"))

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedVersionDirectoryMissing)


@pytest.mark.parametrize(
    ("deleted", "named"),
    [
        (("index.jsonl",), "index"),
        (("failures.jsonl",), "failures file"),
        (("occurrences.jsonl",), "occurrence table"),
        (AGGREGATE_NAMES, "index, failures file, occurrence table"),
    ],
)
async def test_a_directory_missing_an_aggregate_is_refused_naming_it(
    world: World, tmp_path: Path, deleted: tuple[str, ...], named: str
) -> None:
    """All three is what a removal leaves until the next rebuild."""
    await world.run()
    for name in deleted:
        (directory(world) / name).unlink()

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedAggregatesMissing)
    assert error_code_of(refusal) == "PARSED_AGGREGATES_MISSING"
    assert str(refusal) == (
        f"{CASELIST} {DOCX_PARSER_VERSION} has no {named}: a removal deleted it, or no rebuild has "
        "finished since"
    )


async def test_an_index_naming_a_source_with_no_file_is_refused_naming_its_digest(
    world: World, tmp_path: Path
) -> None:
    await world.run()
    sha256 = digest_of("wiki")
    (world.store.root / source_object_key(CASELIST, DOCX_PARSER_VERSION, sha256)).unlink()

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedSourceFilesMissing)
    assert error_code_of(refusal) == "PARSED_SOURCE_FILES_MISSING"
    assert str(refusal) == (
        f"the index of {CASELIST} {DOCX_PARSER_VERSION} names 1 source(s) with no per-source file on "
        f"this machine (sha256 {sha256[:12]})"
    )


async def test_a_directory_parsed_under_another_profile_is_refused(world: World, tmp_path: Path) -> None:
    """A rebuild would start a new generation and publish that, not this directory."""
    await world.run(CountingParser(profile_version=OTHER_PROFILE))

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedByAnotherParserVersion)
    assert error_code_of(refusal) == "PARSED_BY_ANOTHER_PARSER_VERSION"
    profile = CountingParser().profile_version
    assert str(refusal) == (
        f"{CASELIST} {DOCX_PARSER_VERSION} holds sources parsed under parser {DOCX_PARSER_VERSION} "
        f"with profile {OTHER_PROFILE}, not this build's parser {DOCX_PARSER_VERSION} with profile "
        f"{profile}; a rebuild would start a new generation and publish that"
    )


async def test_an_occurrence_table_of_an_older_fingerprint_version_is_refused(
    world: World, tmp_path: Path, as_build: Callable[[str], None]
) -> None:
    """Published as it is, it would send the older build's clusters; the rebuild would restamp it."""
    as_build(OLDER)
    await world.run()
    as_build(BUILD)

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedFingerprintVersionMismatch)
    assert error_code_of(refusal) == "PARSED_FINGERPRINT_VERSION_MISMATCH"
    assert str(refusal) == (
        f"the occurrence table of {CASELIST} {DOCX_PARSER_VERSION} holds rows stamped {OLDER}, not "
        f"this build's {BUILD}"
    )
    assert f"caselist parse --caselist {CASELIST} --publish`" in refusal.hint


async def test_an_occurrence_table_of_a_newer_fingerprint_version_is_refused_naming_the_build_it_needs(
    world: World, tmp_path: Path, as_build: Callable[[str], None]
) -> None:
    as_build(NEWER)
    await world.run()
    as_build(BUILD)

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedFingerprintVersionMismatch)
    assert str(refusal) == (
        f"the occurrence table of {CASELIST} {DOCX_PARSER_VERSION} holds rows stamped {NEWER}, not "
        f"this build's {BUILD}"
    )
    assert refusal.hint == f"Publish it with a build at {NEWER} or later."


async def test_a_table_mixing_this_builds_rows_with_another_versions_is_refused(
    world: World, tmp_path: Path, as_build: Callable[[str], None]
) -> None:
    as_build(BUILD)
    await world.run()
    table = directory(world) / "occurrences.jsonl"
    lines = table.read_text(encoding="utf-8").splitlines(keepends=True)
    older = json.dumps({**json.loads(lines[0]), "fingerprint_version": OLDER}, sort_keys=True) + "\n"
    table.write_text(older + "".join(lines[1:]), encoding="utf-8")

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedFingerprintVersionMismatch)
    assert f"stamped {OLDER}, not" in str(refusal)


async def test_a_per_source_record_a_newer_build_stamped_is_refused(
    world: World, tmp_path: Path, as_build: Callable[[str], None]
) -> None:
    """The table is this build's; one source's file says a newer build parsed it."""
    as_build(BUILD)
    await world.run()
    restamp(world.store.root / source_object_key(CASELIST, DOCX_PARSER_VERSION, digest_of("wiki")), NEWER)

    refusal = await refused(world, tmp_path)

    assert isinstance(refusal, ParsedFingerprintVersionMismatch)
    assert str(refusal) == (
        f"per-source records of {CASELIST} {DOCX_PARSER_VERSION} are stamped {NEWER}, newer than this "
        f"build's {BUILD}"
    )
    assert refusal.hint == f"Publish it with a build at {NEWER} or later."


async def test_a_caselist_that_is_not_a_slug_is_refused_before_anything_is_read(world: World) -> None:
    with pytest.raises(InvalidPublishTarget, match="slug"):
        await world.service().publishable_version("Maple Grove")


# ------------------------------------------------------------------------------------------------
# ac4: aggregates the target environment's list has since stopped something in
# ------------------------------------------------------------------------------------------------


async def hold(world: World, path: str) -> None:
    """A `--source` removal of :data:`REMOVED` from `path`, as another environment records one."""
    recorded = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
    await world.suppression.append(
        [
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=REMOVED,
                recorded_at=recorded,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-72",
            )
        ]
    )
    await world.suppression.append_path_holds(
        [
            PathHoldEntry(
                caselist=CASELIST,
                disclosure=disclosure_digest(CASELIST, path),
                sha256=REMOVED,
                after_snapshot=date(2026, 9, 1),
                recorded_at=recorded,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-72",
            )
        ]
    )


async def test_a_removal_the_rebuild_never_read_is_refused_and_nothing_is_uploaded(
    world: World, tmp_path: Path
) -> None:
    """Dev's aggregates, and a prod list holding one removal dev's lacks: the index still names
    the source, and its occurrence rows its disclosures."""
    await world.run()
    await world.suppress(digest_of("wiki"))

    refusal = await refused(world, tmp_path)

    assert error_code_of(refusal) == STOPPED_BY_THE_LIST
    message = str(refusal)
    assert message.startswith(f"the aggregates of {CASELIST} {DOCX_PARSER_VERSION} name 1 source(s) and ")
    assert "disclosure(s) this environment's suppression list now stops or holds (0 of the sources" in message
    assert f"(sha256 {digest_of('wiki')[:12]})" in message
    assert refusal.hint == (
        f"`debate-research caselist parse --caselist {CASELIST} --publish` rebuilds the aggregates "
        "from this environment's suppression list, then publishes them."
    )


async def test_a_withdrawn_disclosure_of_a_source_another_path_still_discloses_is_refused(
    world: World, tmp_path: Path
) -> None:
    """The index may still name the source; one of its occurrence rows names what is withdrawn."""
    await world.run()
    await world.suppress(digest_of("verbatim"), path=R1_COPY_PATH)

    refusal = await refused(world, tmp_path)

    assert error_code_of(refusal) == STOPPED_BY_THE_LIST
    assert str(refusal).startswith(
        f"the aggregates of {CASELIST} {DOCX_PARSER_VERSION} name 0 source(s) and 1 disclosure(s) "
    )
    assert f"(sha256 {digest_of('verbatim')[:12]})" in str(refusal)


async def test_a_path_hold_the_rebuild_never_read_is_refused(world: World, tmp_path: Path) -> None:
    await world.run()
    await hold(world, HELD_ONLY_PATH)

    refusal = await refused(world, tmp_path)

    assert error_code_of(refusal) == STOPPED_BY_THE_LIST
    assert "name 1 source(s) and " in str(refusal)
    assert "(1 of the sources only at a path a removal holds)" in str(refusal)
    assert f"(sha256 {digest_of('cardmirror')[:12]})" in str(refusal)


async def test_a_path_hold_the_rebuild_read_is_published_as_the_rebuilds_publish_does(
    world: World, tmp_path: Path
) -> None:
    first, second = a_bucket(tmp_path, "dev-bucket"), a_bucket(tmp_path, "prod-bucket")
    await hold(world, HELD_ONLY_PATH)
    rebuilt = await rebuild_and_publish(world, first)

    published = await publish_only(world, second)

    assert await contents(second) == await contents(first)
    assert outcomes(published) == outcomes(rebuilt)

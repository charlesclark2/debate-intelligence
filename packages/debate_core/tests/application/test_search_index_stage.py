"""The weekly run's search index stage: build when the store changed, publish when behind (`v1-e39-t09`).

The stage under test is :class:`~debate_core.application.search_index_refresh.SearchIndexRefresh`,
over the real `tub index build` and `tub index publish` services (`v1-e39-t02`) and the real
suppression list over two local files, one standing for this machine's copy and one for the
bucket's. The bucket is a directory on disk (`FsEvidenceObjectStore`) behind a switch that makes it
answer as a bucket with no session, or one that will not take a key: no network, no AWS.

Every store is synthetic: invented sentences, invented sources (`"1" * 64`), and parser versions
that are no release's (`2026.01.05-synthetic-a`; the PM's note of 2026-10-20 asks for synthetic
versions, because the real store moves to a new one on the day after this merges). Every expected
value is written by hand from the store a test builds.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_sync import SearchIndexStageReport, StageOutcome
from debate_core.application.errors import StoreCredentialsExpired, StoreUnavailable
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.application.ports.parsed_store import (
    OPENEV_STORE,
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.search_index_build import (
    BuiltSearchIndex,
    SearchIndexBuildService,
    SearchIndexSources,
)
from debate_core.application.search_index_publish import SearchIndexPublishService
from debate_core.application.search_index_refresh import (
    GZIP_BYTES_WARNING,
    SEARCH_INDEX_DIRECTORY,
    SQLITE_BYTES_WARNING,
    SearchIndexRefresh,
    newest_local_index,
    size_warnings,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Event, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard, ParsedDocument
from debate_core.domain.search_index import (
    DEFAULT_PROVENANCE_LIMIT,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    IndexFile,
    SearchIndexPointer,
)
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes import InMemoryCaselistRepository, InMemoryParsedStore

CASELIST: Final = "hsld26"
STORES: Final = (CASELIST, OPENEV_STORE)
"""What the run hands the stage: its configured caselists, and `openev` (PM ruling, question 3)."""

PARSER: Final = "2026.01.05-synthetic-a"
NEWER_PARSER: Final = "2026.02.05-synthetic-b"
OLDER_PARSER: Final = "2025.12.01-synthetic-0"
OTHER_FINGERPRINT: Final = "card-fingerprint-synthetic-z"
PROFILE: Final = "2026.01.01-synthetic-profile"
RELEASE: Final = "2026-ld"
NO_SESSION: Final = "the publish stage found no AWS session"


def sha(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


# ------------------------------------------------------------------------------------------------
# The store
# ------------------------------------------------------------------------------------------------


def _card(source: str, text: str, store: str) -> ParsedCard:
    camp = store == OPENEV_STORE
    return ParsedCard(
        tag="Invented growth claim",
        full_cite="Okonkwo 26, Invented Journal of Growth",
        evidence_text=text,
        completeness=CardCompleteness.FULL,
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.9,
        provenance=FileImportProvenance(
            source_sha256=source,
            source_path="placeholder.docx",
            origin=SourceOrigin.OPENEV if camp else SourceOrigin.CASELIST_ARCHIVE,
            caselist=None if camp else CASELIST,
            camp="Cascade Institute" if camp else None,
            snapshot=date(2026, 9, 1),
            first_element_index=0,
            last_element_index=2,
            parser_version=PARSER,
            profile_version=PROFILE,
        ),
    )


def write_store(
    parsed: InMemoryParsedStore,
    store: str,
    texts: Sequence[str],
    *,
    version: str = PARSER,
    fingerprint: str = FINGERPRINT_VERSION,
) -> None:
    """A source of one card for each of `texts` in `store`'s directory `version`, and one occurrence row each.

    Called again with other texts, it writes the sources it has not written and replaces the rows:
    a store's table changes, its recorded sources do not.
    """
    camp = store == OPENEV_STORE
    snapshot = RELEASE if camp else "2026-09-01"
    rows: list[OccurrenceRecord] = []
    for text in texts:
        source = sha(f"{store} {text}")
        card = _card(source, text, store)
        entry = SourceEntry(
            caselist=store,
            snapshot=snapshot,
            source_sha256=source,
            parser_version=version,
            profile_version=PROFILE,
            fingerprint_version=FINGERPRINT_VERSION,
            source_format=SourceFormat.DOCX,
            byte_size=100,
            outcome=SourceOutcome.PARSED,
            cards=1,
        )
        document = ParsedDocument(
            source_sha256=source,
            source_path="placeholder.docx",
            parser_version=version,
            profile_version=PROFILE,
            cards=(card,),
        )
        record = DocumentRecord.from_parsed_document(
            document,
            caselist=store,
            snapshot=snapshot,
            fingerprint_version=FINGERPRINT_VERSION,
            camp="Cascade Institute" if camp else None,
        )
        if asyncio.run(parsed.read_document(store, version, source)) is None:
            asyncio.run(parsed.write_source(store, version, entry, record))
        rows.append(
            OccurrenceRecord(
                caselist=store,
                snapshot=snapshot,
                last_snapshot=snapshot,
                source_sha256=source,
                parser_version=version,
                profile_version=PROFILE,
                fingerprint_version=fingerprint,
                disclosure=None if camp else sha(f"disclosure {text}"),
                camp="Cascade Institute" if camp else None,
                first_element_index=0,
                last_element_index=2,
                exact_fingerprint=card_fingerprint(card).exact_fingerprint,
                cluster_id=sha(f"cluster {text}"),
                membership=ClusterMembership.NEAR_DUPLICATE,
                completeness=CardCompleteness.FULL,
            )
        )
    asyncio.run(parsed.write_aggregates(store, version, index=(), failures=(), occurrences=rows))


def suppression_of(source_text: str, *, store: str = CASELIST) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha(f"{store} {source_text}"),
        recorded_at=datetime(2026, 10, 1, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-09",
    )


# ------------------------------------------------------------------------------------------------
# The bucket, and the services over it
# ------------------------------------------------------------------------------------------------


class SwitchableBucket:
    """A directory standing for the bucket, which can lose its session or refuse one key's upload."""

    def __init__(self, root: Path) -> None:
        self.inner = FsEvidenceObjectStore(root)
        self.session = True
        self.refuse: str | None = None
        self.expire_on_upload: str | None = None
        self.puts: list[str] = []

    def _check(self, key: str) -> None:
        if not self.session:
            raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")
        if self.refuse is not None and key.endswith(self.refuse):
            raise StoreUnavailable("PutObject", key, "connection reset")

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        self._check(prefix)
        return await self.inner.list_objects(prefix)

    async def head(self, key: str) -> ObjectInfo:
        self._check(key)
        return await self.inner.head(key)

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        self._check(key)
        if self.expire_on_upload is not None and key.endswith(self.expire_on_upload):
            raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")
        self.puts.append(key)
        return await self.inner.put_file(key, source)

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        self._check(key)
        return await self.inner.get_file(key, destination)


class CountingBuilder(SearchIndexBuildService):
    """The real build service, counting the builds it is asked for."""

    builds: int = 0

    async def build(
        self,
        stores: Sequence[str],
        out: Path,
        *,
        provenance_limit: int = DEFAULT_PROVENANCE_LIMIT,
        sources: SearchIndexSources | None = None,
    ) -> BuiltSearchIndex:
        self.builds += 1
        return await super().build(stores, out, provenance_limit=provenance_limit, sources=sources)


@dataclass
class World:
    """One machine's data directory, the bucket and the stage, with every copy a test can reach."""

    root: Path
    openev_version: str = PARSER
    """The parser version whose directory the camp store is written in."""

    parsed: InMemoryParsedStore = field(default_factory=InMemoryParsedStore)
    reconciles: int = 0

    def __post_init__(self) -> None:
        self.data_dir = self.root / "data"
        self.out = self.data_dir / SEARCH_INDEX_DIRECTORY
        self.bucket = SwitchableBucket(self.root / "bucket")
        self.local = RecordedSuppressionList(local_suppression_list_file(self.data_dir))
        self.bucket_copy = RecordedSuppressionList(local_suppression_list_file(self.root / "bucket-copy"))
        self.union = RecordedSuppressionList(
            local_suppression_list_file(self.data_dir), local_suppression_list_file(self.root / "bucket-copy")
        )
        self.builder = CountingBuilder(
            parsed_store=self.parsed,
            caselists=InMemoryCaselistRepository(),
            suppression=self.local,
            writer=SqliteSearchIndexWriter(),
            parser_version=PARSER,
            event_for_caselist={CASELIST: Event.LD}.get,
        )
        write_store(self.parsed, CASELIST, ["Invented growth evidence", "Invented trade evidence"])
        write_store(self.parsed, OPENEV_STORE, ["Invented camp evidence"], version=self.openev_version)

    async def _reconcile(self) -> None:
        self.reconciles += 1
        self.bucket._check("manifests/_suppression/suppression-list.jsonl")  # pyright: ignore[reportPrivateUsage]
        await self.union.reconcile()

    def stage(self, *, publishing: bool = True) -> SearchIndexRefresh:
        return SearchIndexRefresh(
            builder=self.builder,
            out=self.out,
            parser_version=PARSER,
            publisher=SearchIndexPublishService(bucket=self.bucket, parser_version=PARSER)
            if publishing
            else None,
            bucket=self.bucket if publishing else None,
            reconcile=self._reconcile if publishing else None,
            environment="dev",
        )

    def refresh(self, *, no_session: str | None = None, publishing: bool = True) -> SearchIndexStageReport:
        return asyncio.run(self.stage(publishing=publishing).refresh(STORES, no_session=no_session))

    def pointer(self) -> SearchIndexPointer | None:
        landed = self.root / "fetched-current.json"
        try:
            asyncio.run(self.bucket.inner.get_file(SEARCH_INDEX_POINTER_KEY, landed))
        except Exception:
            return None
        return SearchIndexPointer.model_validate_json(landed.read_bytes())

    def local_ids(self) -> list[str]:
        return sorted(one.name for one in self.out.iterdir()) if self.out.is_dir() else []

    def newest_id(self) -> str | None:
        newest = newest_local_index(self.out)
        return newest.index_id if newest is not None else None

    def sources(self) -> SearchIndexSources:
        return asyncio.run(self.builder.sources(STORES))


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def published_with(world: World, report: SearchIndexStageReport) -> str:
    """The index the report says is current and published, checked against the bucket's pointer."""
    assert report.counts is not None
    pointer = world.pointer()
    assert pointer is not None
    assert pointer.index_id == report.counts.index_id
    return pointer.index_id


# ------------------------------------------------------------------------------------------------
# ac1: build and publish only when the store changed
# ------------------------------------------------------------------------------------------------


def test_index_stage_builds_and_publishes_a_first_index(world: World) -> None:
    report = world.refresh()

    assert report.outcome is StageOutcome.COMPLETED
    assert report.counts is not None
    assert (report.counts.built, report.counts.published, report.counts.documents) == (True, True, 3)
    index_id = published_with(world, report)
    assert world.local_ids() == [index_id]
    assert world.bucket.puts[-1] == SEARCH_INDEX_POINTER_KEY, "the pointer is written last"
    assert f"built {index_id}" in report.reason and "published, and current.json names it" in report.reason


def test_index_stage_builds_and_publishes_nothing_when_the_store_has_not_changed(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    puts = list(world.bucket.puts)

    again = world.refresh()

    assert again.outcome is StageOutcome.SKIPPED
    assert again.counts is not None
    assert (again.counts.built, again.counts.published) == (False, False)
    assert again.counts.index_id == first.counts.index_id
    assert f"unchanged since {first.counts.index_id}" in again.reason
    assert "which current.json names: nothing to build or publish" in again.reason
    assert world.builder.builds == 1
    assert world.bucket.puts == puts, "nothing was uploaded"


def test_index_stage_rebuilds_and_publishes_when_a_stores_rows_changed(world: World) -> None:
    first = world.refresh()
    write_store(world.parsed, OPENEV_STORE, ["Invented camp evidence", "Invented later camp evidence"])

    second = world.refresh()

    assert second.outcome is StageOutcome.COMPLETED
    assert first.counts is not None and second.counts is not None
    assert second.counts.index_id != first.counts.index_id
    assert (second.counts.built, second.counts.published, second.counts.documents) == (True, True, 4)
    assert published_with(world, second) == second.counts.index_id
    assert world.builder.builds == 2


def test_index_stage_rebuilds_when_only_the_suppression_list_changed(world: World) -> None:
    first = world.refresh()
    asyncio.run(world.local.append([suppression_of("Invented trade evidence")]))

    second = world.refresh()

    assert first.counts is not None and second.counts is not None
    assert second.counts.built and second.counts.documents == 2
    assert published_with(world, second) != first.counts.index_id


def test_index_stage_rebuilds_an_index_whose_files_are_damaged_rather_than_failing_every_week(
    world: World,
) -> None:
    first = world.refresh()
    assert first.counts is not None
    world.bucket.inner = FsEvidenceObjectStore(world.root / "emptied-bucket")
    (world.out / first.counts.index_id / SEARCH_INDEX_GZIP_NAME).write_bytes(b"not the gzip object")

    second = world.refresh()

    assert second.outcome is StageOutcome.COMPLETED
    assert second.counts is not None and second.counts.built
    assert second.counts.index_id == first.counts.index_id, "the same store gives the same bytes"
    assert published_with(world, second) == first.counts.index_id


def test_index_stage_without_a_bucket_builds_and_says_nothing_is_published(world: World) -> None:
    first = world.refresh(publishing=False)
    second = world.refresh(publishing=False)

    assert first.outcome is StageOutcome.COMPLETED
    assert "names no evidence bucket, so it is not published" in first.reason
    assert second.outcome is StageOutcome.SKIPPED
    assert world.builder.builds == 1
    assert world.bucket.puts == []
    assert world.reconciles == 0


# ------------------------------------------------------------------------------------------------
# ac5: the suppression copies, and an index built with no session
# ------------------------------------------------------------------------------------------------


def test_index_stage_reconciles_the_suppression_copies_before_it_builds(world: World) -> None:
    """A removal made on another machine is in the bucket's copy alone: the first index leaves it out."""
    asyncio.run(world.bucket_copy.append([suppression_of("Invented growth evidence")]))

    report = world.refresh()

    assert world.reconciles == 1
    assert [one.request_id for one in asyncio.run(world.local.entries())] == ["RM-2026-09"]
    assert report.counts is not None and report.counts.documents == 2
    assert report.local_copy_only is None


def test_index_stage_without_a_session_builds_from_the_local_copy_and_the_publish_pends(world: World) -> None:
    world.bucket.session = False

    report = world.refresh()

    assert report.outcome is StageOutcome.PENDING
    assert report.counts is not None and report.counts.built and not report.counts.published
    assert world.pointer() is None
    assert world.local_ids() == [report.counts.index_id]
    assert "built, publish pending, for want of an AWS login" in report.reason
    assert "`debate-research tub index publish`" in report.reason
    assert report.local_copy_only is not None
    assert "built from this machine's copy of the suppression list alone" in report.reason


def test_index_stage_told_there_is_no_session_does_not_try_the_bucket(world: World) -> None:
    report = world.refresh(no_session=NO_SESSION)

    assert report.outcome is StageOutcome.PENDING
    assert world.reconciles == 0
    assert world.bucket.puts == []
    assert report.local_copy_only == NO_SESSION
    assert NO_SESSION in report.reason


def test_index_stage_publishes_an_index_built_without_a_session_at_the_next_run_without_a_rebuild(
    world: World,
) -> None:
    world.bucket.session = False
    pended = world.refresh()
    world.bucket.session = True

    caught_up = world.refresh()

    assert pended.counts is not None and caught_up.counts is not None
    assert caught_up.outcome is StageOutcome.COMPLETED
    assert (caught_up.counts.built, caught_up.counts.published) == (False, True)
    assert published_with(world, caught_up) == pended.counts.index_id
    assert world.builder.builds == 1
    assert f"unchanged since {pended.counts.index_id}" in caught_up.reason


def test_index_stage_rebuilds_at_the_next_run_when_reconciling_changed_the_suppression_digest(
    world: World,
) -> None:
    world.bucket.session = False
    pended = world.refresh()
    asyncio.run(world.bucket_copy.append([suppression_of("Invented camp evidence", store=OPENEV_STORE)]))
    world.bucket.session = True

    caught_up = world.refresh()

    assert pended.counts is not None and caught_up.counts is not None
    assert (caught_up.counts.built, caught_up.counts.published, caught_up.counts.documents) == (True, True, 2)
    assert caught_up.counts.index_id != pended.counts.index_id
    assert published_with(world, caught_up) == caught_up.counts.index_id
    assert world.builder.builds == 2


def test_index_stage_with_an_unreachable_bucket_builds_from_the_local_copy_and_fails_its_publish(
    world: World,
) -> None:
    first = world.refresh()
    write_store(world.parsed, CASELIST, ["Invented growth evidence"])
    world.bucket.refuse = "suppression-list.jsonl"

    report = world.refresh()

    assert first.counts is not None and report.counts is not None
    assert report.outcome is StageOutcome.FAILED
    assert isinstance(report.failure, StoreUnavailable)
    assert report.counts.built and not report.counts.published
    assert report.local_copy_only is None, "the summary's field is a login the run did not have"
    assert "alone: the bucket's copy could not be reached (StoreUnavailable)" in report.reason
    assert "not published, and current.json is as it was" in report.reason
    assert published_with(world, first) == first.counts.index_id


# ------------------------------------------------------------------------------------------------
# ac2: a failure leaves the previous pointer and the previous local index, and names it
# ------------------------------------------------------------------------------------------------


def test_index_stage_a_failed_build_leaves_the_previous_index_and_pointer_and_names_them(
    world: World,
) -> None:
    first = world.refresh()
    assert first.counts is not None
    asyncio.run(world.parsed.write_aggregates(OPENEV_STORE, PARSER, index=(), failures=(), occurrences=()))

    report = world.refresh()

    assert report.outcome is StageOutcome.FAILED
    assert type(report.failure).__name__ == "SearchIndexStoreNotReady"
    assert (
        f"the index was not built; the newest index on this machine stays {first.counts.index_id}"
        in report.reason
    )
    assert world.local_ids() == [first.counts.index_id]
    assert world.newest_id() == first.counts.index_id
    assert published_with(world, first) == first.counts.index_id


def test_index_stage_a_failed_upload_leaves_the_previous_pointer_and_names_it(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    write_store(world.parsed, CASELIST, ["Invented growth evidence"])
    world.bucket.refuse = SEARCH_INDEX_MANIFEST_NAME

    report = world.refresh()

    assert report.outcome is StageOutcome.FAILED
    assert isinstance(report.failure, StoreUnavailable)
    assert report.counts is not None and report.counts.built and not report.counts.published
    assert f"current.json still names {first.counts.index_id}" in report.reason
    assert published_with(world, first) == first.counts.index_id
    assert report.hint is not None
    assert f"--index <data_dir>/tub-index/{report.counts.index_id}" in report.hint
    assert "DEBATE_ENV=dev debate-research tub index publish --env dev" in report.hint


def test_index_stage_a_session_that_expires_mid_publish_pends_and_leaves_the_pointer(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    write_store(world.parsed, CASELIST, ["Invented growth evidence"])
    world.bucket.expire_on_upload = SEARCH_INDEX_POINTER_KEY

    report = world.refresh()

    assert report.outcome is StageOutcome.PENDING
    assert f"current.json still names {first.counts.index_id}" in report.reason
    assert published_with(world, first) == first.counts.index_id


# ------------------------------------------------------------------------------------------------
# ac3: a version mismatch skips the stage with its reason
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "named"),
    [
        (NEWER_PARSER, f"it was parsed by {NEWER_PARSER}, a newer parser than this build's {PARSER}"),
        (OLDER_PARSER, f"no version directory of parser {PARSER} (it was parsed by {OLDER_PARSER})"),
    ],
)
def test_index_stage_skips_a_store_parsed_by_another_parser(tmp_path: Path, written: str, named: str) -> None:
    """The camp store holds only `written`'s directory, or a newer parser's beside this build's."""
    world = World(tmp_path, openev_version=written)
    if written == NEWER_PARSER:
        write_store(world.parsed, OPENEV_STORE, ["Invented camp evidence"])

    report = world.refresh()

    assert report.outcome is StageOutcome.SKIPPED
    assert report.reason.startswith("skipped, the parsed store is not this build's version")
    assert named in report.reason
    assert world.builder.builds == 0
    assert world.bucket.puts == []
    assert world.pointer() is None


def test_index_stage_skips_a_store_whose_rows_carry_another_fingerprint_version(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    write_store(world.parsed, CASELIST, ["Invented growth evidence"], fingerprint=OTHER_FINGERPRINT)

    report = world.refresh()

    assert report.outcome is StageOutcome.SKIPPED
    assert OTHER_FINGERPRINT in report.reason and FINGERPRINT_VERSION in report.reason
    assert f"the newest index on this machine stays {first.counts.index_id}" in report.reason
    assert world.builder.builds == 1
    assert published_with(world, first) == first.counts.index_id


# ------------------------------------------------------------------------------------------------
# ac6: size
# ------------------------------------------------------------------------------------------------


def test_index_stage_reports_the_sqlite_bytes_and_bytes_per_document_of_every_build(world: World) -> None:
    report = world.refresh()

    assert report.counts is not None
    newest = newest_local_index(world.out)
    assert newest is not None
    sqlite_bytes = newest.manifest.sqlite_file.bytes
    assert report.counts.sqlite_bytes == sqlite_bytes
    assert report.counts.gzip_bytes == newest.manifest.gzip_object.bytes
    assert report.counts.bytes_per_document == sqlite_bytes // 3
    assert f"SQLite file {sqlite_bytes:,} bytes, {sqlite_bytes // 3:,} bytes a document" in report.reason
    assert report.counts.warnings == ()


@pytest.mark.parametrize(
    ("sqlite_bytes", "gzip_bytes", "lines"),
    [
        (SQLITE_BYTES_WARNING, GZIP_BYTES_WARNING, ()),
        (SQLITE_BYTES_WARNING + 1, GZIP_BYTES_WARNING, ("1 GB uncompressed",)),
        (SQLITE_BYTES_WARNING, GZIP_BYTES_WARNING + 1, ("revisit trigger",)),
        (SQLITE_BYTES_WARNING + 1, GZIP_BYTES_WARNING + 1, ("1 GB uncompressed", "revisit trigger")),
    ],
)
def test_index_stage_warns_past_each_of_adr_0019s_lines(
    world: World, sqlite_bytes: int, gzip_bytes: int, lines: tuple[str, ...]
) -> None:
    assert (SQLITE_BYTES_WARNING, GZIP_BYTES_WARNING) == (900_000_000, 400_000_000)
    world.refresh()
    newest = newest_local_index(world.out)
    assert newest is not None
    manifest = newest.manifest.model_copy(
        update={
            "sqlite_file": IndexFile(name="search-index.sqlite", bytes=sqlite_bytes, sha256="a" * 64),
            "gzip_object": IndexFile(name="search-index.sqlite.gz", bytes=gzip_bytes, sha256="b" * 64),
        }
    )

    warnings = size_warnings(manifest)

    assert len(warnings) == len(lines)
    for warning, line in zip(warnings, lines, strict=True):
        assert "ADR-0019" in warning and line in warning


# ------------------------------------------------------------------------------------------------
# The newest local index
# ------------------------------------------------------------------------------------------------


def test_index_stage_the_newest_local_index_is_the_last_manifest_written_and_never_a_scratch_directory(
    world: World,
) -> None:
    first = world.refresh()
    write_store(world.parsed, OPENEV_STORE, ["Invented camp evidence", "Invented later camp evidence"])
    second = world.refresh()
    assert first.counts is not None and second.counts is not None
    earlier = world.out / first.counts.index_id / SEARCH_INDEX_MANIFEST_NAME
    later = world.out / second.counts.index_id / SEARCH_INDEX_MANIFEST_NAME
    os.utime(earlier, ns=(1_000_000_000, 1_000_000_000))
    os.utime(later, ns=(2_000_000_000, 2_000_000_000))
    (world.out / ".building-abandoned").mkdir()
    (world.out / "not-an-index").mkdir()

    assert world.newest_id() == second.counts.index_id
    os.utime(earlier, ns=(3_000_000_000, 3_000_000_000))
    assert world.newest_id() == first.counts.index_id


def test_index_stage_compares_with_the_digests_the_build_service_computes(world: World) -> None:
    report = world.refresh()
    newest = newest_local_index(world.out)
    assert report.counts is not None and newest is not None

    sources = world.sources()

    assert newest.manifest.stores == sources.stores
    assert newest.manifest.suppression == sources.suppression_list

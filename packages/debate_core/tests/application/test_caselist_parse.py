"""`CaselistParseService`: the incremental parse pipeline (`v1-e31-t06-parse-pipeline`).

Run over a fictional caselist imported by the real importer
(`tests/fixtures/parse_pipeline/build_parse_world.py`), whose documents are the `v1-e31-t03`
structural fixtures. Every count asserted here is the hand-written :data:`EXPECTED` of that
fixture, derived from its table without running the parser (working agreement 6).

What each test holds the service to:

* ac1: a second run parses nothing and reports every source skipped; a new snapshot parses only its
  new sources; `--reparse`, a parser bump and a profile bump each write a new version directory and
  leave the old one byte for byte.
* ac2: every record the run writes carries the six fields.
* ac3: one failing source never stops the run; it is recorded with its typed reason; the failure
  rate counts PDFs and `.doc` files on neither side; the pool survives a parse past its time limit
  and a worker that dies.
* The full-archive namespace is never enumerated, and never reaches the occurrence table.
* Nothing the run logs names a school, a team, a path or a word of a card.

Publishing (`-k publish`) and the removal criterion (ac6) have their own tests: the publish tests
below, and `caselist/test_parsed_store_removal.py`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import (
    BODIES,
    CASELIST,
    EXPECTED,
    WEEKS,
    digest_of,
    import_weeks,
)

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import (
    InProcessParseRunner,
    LoadableJob,
    ParseJob,
    ParseResult,
    ProcessPoolParseRunner,
)
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService, ParseRunReport
from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.parsed_store import (
    AGGREGATE_NAMES,
    SourceOutcome,
    version_directory_name,
)
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.domain.caselist import SnapshotDate, SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import MisbehavingDebateFileParser, build_fake_caselist_repository

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

THROUGH_0908: Final = date(2026, 9, 8)
THROUGH_0915: Final = date(2026, 9, 15)
SIX_FIELDS: Final = (
    "caselist",
    "snapshot",
    "source_sha256",
    "parser_version",
    "profile_version",
    "fingerprint_version",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class CountingParser:
    """The real parser, counting the sources it is asked to read."""

    def __init__(
        self,
        inner: DebateFileParser | None = None,
        *,
        parser_version: str | None = None,
        profile_version: str | None = None,
    ) -> None:
        self._inner = inner or DebateDocxParser()
        self._parser_version = parser_version
        self._profile_version = profile_version
        self.parsed: list[str] = []

    @property
    def parser_version(self) -> str:
        return self._parser_version or self._inner.parser_version

    @property
    def profile_version(self) -> str:
        return self._profile_version or self._inner.profile_version

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        self.parsed.append(source.sha256)
        result = self._inner.parse(content, source, source_path=source_path, snapshot=snapshot, camp=camp)
        if isinstance(result, ParsedDocument) and (self._parser_version or self._profile_version):
            return result.model_copy(
                update={
                    "parser_version": self.parser_version,
                    "profile_version": self.profile_version,
                    "cards": tuple(
                        card.model_copy(
                            update={
                                "provenance": card.provenance.model_copy(
                                    update={
                                        "parser_version": self.parser_version,
                                        "profile_version": self.profile_version,
                                    }
                                )
                            }
                        )
                        for card in result.cards
                    ),
                }
            )
        return result


@dataclass
class World:
    """A data directory holding the fictional caselist, and a service over it."""

    data_dir: Path
    zips_dir: Path

    @property
    def local(self) -> LocalEvidence:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        )

    @property
    def store(self) -> LocalParsedStore:
        return LocalParsedStore(self.data_dir)

    @property
    def suppression(self) -> RecordedSuppressionList:
        return RecordedSuppressionList(local_suppression_list_file(self.data_dir))

    def service(
        self,
        parser: DebateFileParser | None = None,
        *,
        runner: Any = None,
        threshold: float = 0.5,
    ) -> CaselistParseService:
        return CaselistParseService(
            local=self.local,
            store=self.store,
            parser=parser or DebateDocxParser(),
            runner=runner or InProcessParseRunner(),
            suppression=self.suppression,
            place_cards=CaselistCardStatsService(build_fake_caselist_repository()).place,
            failure_rate_threshold=threshold,
        )

    async def run(self, parser: DebateFileParser | None = None, **plan: Any) -> ParseRunReport:
        service = self.service(parser)
        return await service.run(await service.plan(CASELIST, **plan))

    def tree(self, version: str = DOCX_PARSER_VERSION) -> dict[str, bytes]:
        root = self.store.root / CASELIST / version
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def lines(self, name: str, version: str = DOCX_PARSER_VERSION) -> list[dict[str, Any]]:
        path = self.store.root / CASELIST / version / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    async def suppress(self, sha256: str, *, path: str | None = None) -> None:
        """Append a suppression entry the way a removal on another machine leaves one here."""
        await self.suppression.append(
            [
                SuppressionEntry(
                    action=SuppressionAction.SUPPRESS,
                    sha256=sha256,
                    disclosure=disclosure_digest(CASELIST, path) if path is not None else None,
                    recorded_at=datetime(2026, 9, 30, 18, 0, tzinfo=UTC),
                    reason=ReasonCode.POLICY,
                    request_id="RM-2026-91",
                )
            ]
        )


@pytest.fixture
async def world(tmp_path: Path) -> World:
    """09-01 and 09-08 imported; nothing parsed yet."""
    built = World(data_dir=tmp_path / "evidence", zips_dir=tmp_path / "zips")
    await import_weeks(built.data_dir, built.zips_dir, through=THROUGH_0908)
    return built


# ------------------------------------------------------------------------------------------------
# A first run
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_first_run_parses_every_source_and_reports_the_hand_derived_counts(world: World) -> None:
    expected = EXPECTED["after_0908"]
    report = await world.run()

    assert report.plan.in_scope == expected["sources"]
    assert report.attempted == expected["sources"]
    assert report.parsed == expected["parsed"]
    assert report.cards == expected["cards"]
    assert report.unsupported == expected["unsupported"]
    assert report.failed == expected["failed"]
    assert report.failure_rate == expected["failure_rate"]
    assert report.store is not None
    assert (report.store.sources, report.store.cards, report.store.occurrences) == (
        expected["sources"],
        expected["cards"],
        expected["occurrences"],
    )
    assert report.plan.version == DOCX_PARSER_VERSION
    assert not report.plan.new_version


@pytest.mark.anyio
async def test_the_occurrence_table_has_a_row_per_card_per_disclosure_named_by_its_digest(
    world: World,
) -> None:
    """A file disclosed in two weeks and under two paths is one parse and one row per disclosure."""
    await world.run()
    rows = world.lines("occurrences.jsonl")
    verbatim = [row for row in rows if row["source_sha256"] == digest_of("verbatim")]
    paths = {path for week in WEEKS[:2] for path, body in week.members if body == "verbatim"}
    disclosures = {
        (week.snapshot.isoformat(), disclosure_digest(CASELIST, path))
        for week in WEEKS[:2]
        for path, body in week.members
        if body == "verbatim"
    }
    assert {(row["snapshot"], row["disclosure"]) for row in verbatim} == disclosures
    assert len(verbatim) == 4 == len(disclosures)
    assert len(paths) == 3
    assert {row["completeness"] for row in rows if row["source_sha256"] == digest_of("wiki")} == {
        "ABBREVIATED",
        "CITE_ONLY",
    }


# ------------------------------------------------------------------------------------------------
# ac1: incremental
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_second_run_over_an_unchanged_store_parses_nothing_and_skips_every_source(
    world: World,
) -> None:
    await world.run()
    before = world.tree()
    parser = CountingParser()

    report = await world.run(parser)

    assert parser.parsed == []
    assert report.attempted == 0
    assert report.plan.skipped == EXPECTED["after_0908"]["sources"]
    assert report.parsed == 0
    assert world.tree() == before


@pytest.mark.anyio
async def test_importing_a_new_snapshot_parses_only_its_new_sources(world: World) -> None:
    await world.run()
    await import_weeks(world.data_dir, world.zips_dir, through=THROUGH_0915, after=THROUGH_0908)
    parser = CountingParser()

    report = await world.run(parser)

    expected = EXPECTED["after_0915"]
    assert parser.parsed == [digest_of("direct")]
    assert report.parsed == expected["parsed_this_run"]
    assert report.plan.skipped == expected["skipped_this_run"]
    assert report.store is not None
    assert (report.store.sources, report.store.cards, report.store.occurrences) == (
        expected["sources"],
        expected["cards"],
        expected["occurrences"],
    )


@pytest.mark.anyio
async def test_a_snapshot_run_parses_only_that_snapshots_unparsed_sources(world: World) -> None:
    service = world.service()
    await service.run(await service.plan(CASELIST, snapshot="2026-09-01"))
    parser = CountingParser()

    report = await world.run(parser, snapshot="2026-09-08")

    assert sorted(parser.parsed) == sorted(digest_of(body) for body in ("cardmirror", "doc", "broken"))
    assert report.plan.skipped == 3


@pytest.mark.anyio
async def test_reparse_writes_a_new_version_directory_and_leaves_the_old_one_byte_for_byte(
    world: World,
) -> None:
    await world.run()
    before = world.tree()
    parser = CountingParser()

    report = await world.run(parser, reparse=True)

    newer = version_directory_name(DOCX_PARSER_VERSION, 2)
    assert report.plan.version == newer
    assert report.plan.superseded == DOCX_PARSER_VERSION
    assert len(parser.parsed) == EXPECTED["after_0908"]["sources"]
    assert world.tree() == before
    assert set(world.tree(newer)) == set(before)
    again = CountingParser()
    assert (await world.run(again)).plan.version == newer
    assert again.parsed == []


@pytest.mark.anyio
async def test_a_parser_version_bump_parses_everything_into_its_own_directory(world: World) -> None:
    await world.run()
    before = world.tree()
    bumped = CountingParser(parser_version="2026.10.01-docx-2")

    report = await world.run(bumped)

    assert report.plan.version == "2026.10.01-docx-2"
    assert len(bumped.parsed) == EXPECTED["after_0908"]["sources"]
    assert world.tree() == before
    assert {row["parser_version"] for row in world.lines("index.jsonl", "2026.10.01-docx-2")} == {
        "2026.10.01-docx-2"
    }


@pytest.mark.anyio
async def test_a_profile_bump_under_the_same_parser_reparses_into_a_new_generation(world: World) -> None:
    """The skip key includes the profile version: a new profile is a re-parse, never a skip."""
    await world.run()
    before = world.tree()
    bumped = CountingParser(profile_version="2026.10.01-verbatim-2")

    report = await world.run(bumped)

    assert report.plan.version == version_directory_name(DOCX_PARSER_VERSION, 2)
    assert len(bumped.parsed) == EXPECTED["after_0908"]["sources"]
    assert world.tree() == before
    assert {row["profile_version"] for row in world.lines("index.jsonl", report.plan.version)} == {
        "2026.10.01-verbatim-2"
    }


@pytest.mark.anyio
async def test_a_dry_run_plans_and_writes_nothing(world: World) -> None:
    service = world.service()
    plan = await service.plan(CASELIST)
    report = service.dry_run(plan)

    assert len(plan.to_parse) == EXPECTED["after_0908"]["sources"]
    assert report.attempted == 0
    assert not (world.data_dir / "parsed").exists()


@pytest.mark.anyio
async def test_a_source_missing_from_this_machine_is_recorded_and_tried_again(world: World) -> None:
    blob = world.local.blob_path_for
    assert blob is not None
    sha = digest_of("cardmirror")
    path = blob(f"sha256/{sha[0:2]}/{sha[2:4]}/{sha}")
    held = path.read_bytes()
    path.unlink()

    first = await world.run()
    assert first.failed == {"NOT_A_ZIP": 1, "SOURCE_MISSING": 1}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(held)
    parser = CountingParser()
    second = await world.run(parser)
    assert parser.parsed == [sha]
    assert second.parsed == 1


@pytest.mark.anyio
async def test_a_blob_that_no_longer_matches_its_name_is_never_parsed(world: World) -> None:
    blob = world.local.blob_path_for
    assert blob is not None
    sha = digest_of("verbatim")
    path = blob(f"sha256/{sha[0:2]}/{sha[2:4]}/{sha}")
    path.chmod(0o644)
    path.write_bytes(b"changed on disk")

    report = await world.run()

    assert report.failed == {"NOT_A_ZIP": 1, "SOURCE_INTEGRITY": 1}


# ------------------------------------------------------------------------------------------------
# ac2: every record
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_every_record_the_run_writes_carries_the_six_fields(world: World) -> None:
    await world.run()
    files = sorted((world.store.root / CASELIST).rglob("*.jsonl"))
    assert {path.name for path in files} >= set(AGGREGATE_NAMES)
    kinds: set[str] = set()
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            kinds.add(record["record"])
            assert all(record[name] for name in SIX_FIELDS), path.name
            assert record["caselist"] == CASELIST
            assert record["parser_version"] == DOCX_PARSER_VERSION
    assert kinds == {"source", "document", "occurrence"}


# ------------------------------------------------------------------------------------------------
# ac3: failures
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_one_failing_source_is_recorded_with_its_reason_and_the_run_carries_on(world: World) -> None:
    report = await world.run()

    failures = world.lines("failures.jsonl")
    assert {(row["source_sha256"], row["outcome"], row["reason"]) for row in failures} == {
        (digest_of("broken"), "FAILED", "NOT_A_ZIP"),
        (digest_of("pdf"), "UNSUPPORTED", "UNSUPPORTED_FORMAT"),
        (digest_of("doc"), "UNSUPPORTED", "UNSUPPORTED_FORMAT"),
    }
    assert {row["source_format"] for row in failures if row["outcome"] == "UNSUPPORTED"} == {"PDF", "DOC"}
    assert report.parsed == EXPECTED["after_0908"]["parsed"]


@pytest.mark.anyio
async def test_unsupported_formats_count_on_neither_side_of_the_failure_rate(world: World) -> None:
    """One failure over the four sources tried that are not a PDF or a `.doc`, not three over six."""
    service = world.service(threshold=0.2)
    report = await service.run(await service.plan(CASELIST))

    assert report.failure_rate == 0.25
    assert report.exceeds_threshold

    above = world.service(threshold=0.25)
    rerun = await above.run(await above.plan(CASELIST, reparse=True))
    assert rerun.failure_rate == 0.25
    assert not rerun.exceeds_threshold


@pytest.mark.anyio
async def test_a_parser_that_raises_on_one_source_fails_that_source_only(world: World) -> None:
    parser = MisbehavingDebateFileParser(DebateDocxParser(), raise_on={digest_of("wiki")})

    report = await world.run(parser)

    assert report.failed == {"NOT_A_ZIP": 1, "PARSER_ERROR": 1}
    assert report.parsed == 2
    rows = {row["source_sha256"]: row for row in world.lines("failures.jsonl")}
    assert rows[digest_of("wiki")]["detail"] == "RuntimeError"


@pytest.mark.anyio
async def test_the_failure_rate_is_zero_when_nothing_was_tried(world: World) -> None:
    await world.run()
    report = await world.run()
    assert report.failure_rate == 0.0
    assert not report.exceeds_threshold


def test_the_suppression_list_is_a_required_argument_with_no_default() -> None:
    parameter = inspect.signature(CaselistParseService).parameters["suppression"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


# ------------------------------------------------------------------------------------------------
# The pool
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_pool_writes_exactly_what_parsing_in_process_writes(world: World, tmp_path: Path) -> None:
    await world.run()
    pooled = World(data_dir=tmp_path / "pooled", zips_dir=tmp_path / "pooled-zips")
    await import_weeks(pooled.data_dir, pooled.zips_dir, through=THROUGH_0908)
    service = pooled.service(runner=ProcessPoolParseRunner(workers=2, timeout_seconds=60))

    report = await service.run(await service.plan(CASELIST))

    assert report.workers == 2
    assert pooled.tree() == world.tree()


@pytest.mark.anyio
async def test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on(world: World) -> None:
    parser = MisbehavingDebateFileParser(DebateDocxParser(), stall={digest_of("verbatim")}, stall_seconds=60)
    service = world.service(parser, runner=ProcessPoolParseRunner(workers=2, timeout_seconds=1.5))

    report = await service.run(await service.plan(CASELIST))

    assert report.failed == {"NOT_A_ZIP": 1, "TIMEOUT": 1}
    assert report.parsed == 2
    assert report.failure_rate == 0.5


@pytest.mark.anyio
async def test_a_worker_that_dies_fails_its_source_and_is_replaced(world: World) -> None:
    parser = MisbehavingDebateFileParser(DebateDocxParser(), crash={digest_of("wiki")})
    service = world.service(parser, runner=ProcessPoolParseRunner(workers=1, timeout_seconds=60))

    report = await service.run(await service.plan(CASELIST))

    assert report.failed == {"NOT_A_ZIP": 1, "WORKER_CRASHED": 1}
    assert report.parsed == 2


def test_a_pool_with_nothing_to_do_starts_no_worker() -> None:
    class Unpicklable:
        """A parser no worker could be started with; the pool never tries."""

        parser_version = "x"
        profile_version = "y"

        def __reduce__(self) -> Any:
            raise AssertionError("a worker was started")

        def parse(self, *args: object, **kwargs: object) -> ParseResult:  # pragma: no cover
            raise AssertionError

    jobs: Sequence[LoadableJob] = ()
    runner = ProcessPoolParseRunner(workers=4, timeout_seconds=1)
    results: Iterator[tuple[ParseJob, ParseResult]] = runner.run(Unpicklable(), jobs)  # pyright: ignore[reportArgumentType]
    assert list(results) == []


# ------------------------------------------------------------------------------------------------
# What is enumerated
# ------------------------------------------------------------------------------------------------

FULL_ARCHIVE_KEYS: Final = (
    "manifests/testcl26/full/2026-09-15.jsonl",
    "manifests/testcl26/all/2026-09-15.jsonl",
    "manifests/testcl26/archive/2026-09-15.jsonl",
    "manifests/testcl26/2026-09-15-all.jsonl",
    "manifests/testcl26/2026-09-15.full.jsonl",
)


@pytest.mark.anyio
@pytest.mark.parametrize("key", FULL_ARCHIVE_KEYS)
async def test_the_full_archive_namespace_is_neither_parsed_nor_in_the_occurrence_table(
    world: World, key: str
) -> None:
    """`v1-e34-t04` files a complete archive beside the weekly series. Its copies are not disclosures.

    The planted manifest names a file the weeklies hold (verbatim) and one they do not (direct),
    whose blob is on this machine, as it would be after a full-archive import.
    """
    blob = world.local.blob_path_for
    assert blob is not None
    sha = digest_of("direct")
    target = blob(f"sha256/{sha[0:2]}/{sha[2:4]}/{sha}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(BODIES["direct"])
    rows = [
        {
            "kind": "member",
            "classification": "NEW",
            "path": f"Westfield/XY/full-{body}.docx",
            "sha256": digest_of(body),
            "byte_size": len(BODIES[body]),
            "format": "DOCX",
        }
        for body in ("verbatim", "direct")
    ]
    manifest = world.data_dir / "objects" / key
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    parser = CountingParser()

    report = await world.run(parser)

    assert digest_of("direct") not in parser.parsed
    assert report.plan.in_scope == EXPECTED["after_0908"]["sources"]
    assert report.store is not None
    assert report.store.occurrences == EXPECTED["after_0908"]["occurrences"]
    assert {row["snapshot"] for row in world.lines("occurrences.jsonl")} == {"2026-09-01", "2026-09-08"}


@pytest.mark.anyio
async def test_a_camp_release_is_parsed_with_its_camp_and_no_disclosure(tmp_path: Path) -> None:
    """An OpenEv release manifest, in the shape the OpenEv importer writes, read the same way."""
    world = World(data_dir=tmp_path / "evidence", zips_dir=tmp_path / "zips")
    body = (
        Path(__file__).resolve().parents[4]
        / "tests/fixtures/debate_files/structural/cardmirror-camp-file.docx"
    ).read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    blob = world.data_dir / "blobs" / "sha256" / sha[0:2] / sha[2:4] / sha
    blob.parent.mkdir(parents=True)
    blob.write_bytes(body)
    row = {
        "kind": "member",
        "classification": "NEW",
        "path": "Cascade Institute/Climate Adv CP - Cascade 2026.docx",
        "sha256": sha,
        "byte_size": len(body),
        "format": "DOCX",
        "camp": "Cascade Institute",
        "imported_on": "2026-09-14",
    }
    manifest = world.data_dir / "objects" / "manifests" / "openev" / "2026-policy.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
    service = world.service()

    report = await service.run(await service.plan("openev"))

    assert report.parsed == 1
    assert report.cards == 2
    occurrences = [
        json.loads(line)
        for line in (world.store.root / "openev" / DOCX_PARSER_VERSION / "occurrences.jsonl")
        .read_text()
        .splitlines()
    ]
    assert [(row["snapshot"], row["disclosure"], row["camp"]) for row in occurrences] == [
        ("2026-policy", None, "Cascade Institute")
    ] * 2
    record = await world.store.read_document("openev", DOCX_PARSER_VERSION, sha)
    assert record is not None
    document = record.to_parsed_document("camp path")
    assert {
        (card.provenance.origin, card.provenance.camp, card.provenance.caselist) for card in document.cards
    } == {("OPENEV", "Cascade Institute", None)}


# ------------------------------------------------------------------------------------------------
# Failures listing
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_failure_listing_names_each_source_by_digest_and_its_manifest_path(world: World) -> None:
    service = world.service()
    assert not (await service.failures(CASELIST)).present
    await service.run(await service.plan(CASELIST))

    listing = await service.failures(CASELIST)

    assert listing.present
    paths = {body: path for week in WEEKS[:2] for path, body in week.members}
    assert {
        (row.sha256_prefix, row.path, row.reason, row.counts_toward_failure_rate) for row in listing.rows
    } == {
        (digest_of("broken")[:12], paths["broken"], "NOT_A_ZIP", True),
        (digest_of("pdf")[:12], paths["pdf"], "UNSUPPORTED_FORMAT", False),
        (digest_of("doc")[:12], paths["doc"], "UNSUPPORTED_FORMAT", False),
    }


# ------------------------------------------------------------------------------------------------
# Logs
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_nothing_the_run_logs_names_a_school_a_team_a_path_or_a_card(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="debate_core")
    report = await world.run()
    await world.service().failures(CASELIST)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "caselist parse testcl26" in logged
    for identifier in FICTIONAL_IDENTIFIERS:
        assert identifier not in logged
    record = await world.store.read_document(CASELIST, DOCX_PARSER_VERSION, digest_of("verbatim"))
    assert record is not None
    for card in record.to_parsed_document("x").cards:
        assert card.evidence_text[:40] not in logged
        assert card.tag not in logged
    assert repr(report.plan).count("Maple") == 0


# ------------------------------------------------------------------------------------------------
# ac4: publishing (`-k publish`)
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


def publisher(world: World, bucket: S3EvidenceObjectStore) -> ParsedStorePublisher:
    local = FsEvidenceObjectStore(world.data_dir, subdirectory=Path("parsed"))
    return ParsedStorePublisher(
        local=local, local_path_for=local.path_for, remote=bucket, suppression=world.suppression
    )


def put_requests(s3_client: S3Client) -> list[str]:
    """Every PutObject the client makes from here on, by key, counted at botocore's event hook."""
    made: list[str] = []

    def count(params: dict[str, Any], **_: object) -> None:
        made.append(str(params["Key"]))

    s3_client.meta.events.register("before-parameter-build.s3.PutObject", count)
    return made


@pytest.mark.anyio
async def test_publish_uploads_every_object_of_the_current_version_under_its_prefix(
    world: World, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
) -> None:
    await world.run()
    puts = put_requests(s3_client)

    report = await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    local = {f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/{name}" for name in world.tree()}
    listed = {
        str(item.get("Key")) for item in s3_client.list_objects_v2(Bucket=evidence_bucket).get("Contents", [])
    }
    assert listed == local
    assert sorted(puts) == sorted(local)
    assert report.succeeded
    assert report.count(SourceResult.UPLOADED) == len(local)
    assert puts[-3:] == sorted(puts[-3:]) and {key.rsplit("/", 1)[1] for key in puts[-3:]} == set(
        AGGREGATE_NAMES
    )
    for key in local:
        head = s3_client.head_object(Bucket=evidence_bucket, Key=key, ChecksumMode="ENABLED")
        assert head["Metadata"]["sha256"] == hashlib.sha256(world.tree()[key.split("/", 3)[3]]).hexdigest()


@pytest.mark.anyio
async def test_a_publish_rerun_uploads_nothing(
    world: World, bucket: S3EvidenceObjectStore, s3_client: S3Client
) -> None:
    await world.run()
    await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)
    await world.run()
    puts = put_requests(s3_client)

    report = await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    assert puts == []
    assert report.count(SourceResult.UPLOADED) == 0
    assert report.count(SourceResult.SKIPPED) == len(world.tree())


@pytest.mark.anyio
async def test_publish_after_a_new_snapshot_uploads_only_the_new_source_and_the_aggregates(
    world: World, bucket: S3EvidenceObjectStore, s3_client: S3Client
) -> None:
    await world.run()
    await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)
    await import_weeks(world.data_dir, world.zips_dir, through=THROUGH_0915, after=THROUGH_0908)
    await world.run()
    puts = put_requests(s3_client)

    await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    # The new source's file, and the two aggregates it changes. The failures file is unchanged,
    # because the new source parsed, so its bytes match the bucket's and it is skipped.
    sha = digest_of("direct")
    prefix = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}"
    assert sorted(puts) == sorted(
        [
            f"{prefix}/sha256/{sha[0:2]}/{sha[2:4]}/{sha}.jsonl",
            f"{prefix}/index.jsonl",
            f"{prefix}/occurrences.jsonl",
        ]
    )


@pytest.mark.anyio
async def test_publish_withholds_the_aggregates_when_a_source_file_disagrees_with_the_bucket(
    world: World, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
) -> None:
    await world.run()
    sha = digest_of("verbatim")
    key = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/sha256/{sha[0:2]}/{sha[2:4]}/{sha}.jsonl"
    staged = world.data_dir / "elsewhere.jsonl"
    staged.write_text("{}\n", encoding="utf-8")
    await bucket.put_file(key, staged)
    puts = put_requests(s3_client)

    report = await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    assert not report.succeeded
    assert report.failed_keys == (key,)
    assert not any(put.rsplit("/", 1)[1] in AGGREGATE_NAMES for put in puts)
    assert key not in puts


@pytest.mark.anyio
async def test_publish_never_uploads_a_suppressed_sources_file(
    world: World, bucket: S3EvidenceObjectStore, s3_client: S3Client
) -> None:
    await world.run()
    await world.suppress(digest_of("pdf"))
    await world.run()
    puts = put_requests(s3_client)

    report = await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    sha = digest_of("pdf")
    assert not any(sha in put for put in puts)
    assert report.count(SourceResult.SUPPRESSED) == 1


@pytest.mark.anyio
async def test_publish_names_nothing_but_digests_and_versions(
    world: World,
    bucket: S3EvidenceObjectStore,
    s3_client: S3Client,
    evidence_bucket: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="debate_core")
    await world.run()
    await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    listed = [
        str(item.get("Key")) for item in s3_client.list_objects_v2(Bucket=evidence_bucket).get("Contents", [])
    ]
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for identifier in FICTIONAL_IDENTIFIERS:
        assert all(identifier not in key for key in listed)
        assert identifier not in logged
    for key in listed:
        metadata = s3_client.head_object(Bucket=evidence_bucket, Key=key)["Metadata"]
        assert set(metadata) == {"sha256"}
    assert all(SourceOutcome.PARSED.value not in key for key in listed)

"""An older build's own code, reading the parsed card store as this build writes it (`v1-e31-t26`).

Not collected: its name is not a test module's, and it is only ever run by its path, in two steps.
It writes nothing outside the directory named by `CHECK_PARSED_STORE_DIR` and pytest's temporary
directory, and the bucket is moto's.

1. **This build writes** (`CHECK_PARSED_STORE=write`, run with this build's source): the parse world
   of `tests/fixtures/parse_pipeline/build_parse_world.py`, all three weeks, parsed once; then a
   removal made elsewhere holds two paths, `cardmirror`'s only path and one of `verbatim`'s three,
   and this build parses again. The directory then holds every shape this task writes: aggregates
   without a held-only source or a held disclosure, and that source's per-source file beside them,
   out of every aggregate. The data directory is copied to `CHECK_PARSED_STORE_DIR`.
2. **An older build reads** (`CHECK_PARSED_STORE=read`, with the older build's source first on
   `PYTHONPATH`): its parsed store reads every file of the copy, record by record; its publisher
   publishes the directory to moto; and its parse pipeline runs over the copy as the weekly agent's
   pull does. A build with this parser version rebuilds this build's directory; one with an older
   parser version starts its own, beside it.

The commands and what they printed are in `docs/session-reports/v1-e31-t26-held-upload-parsed-publish.md`.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, R5_PATH, WEEKS, import_weeks

import debate_core
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.ports.parsed_store import SourceOutcome
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.caselist import build_fake_caselist_repository

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STEP = os.environ.get("CHECK_PARSED_STORE", "")
COPY = Path(os.environ.get("CHECK_PARSED_STORE_DIR", "/nonexistent"))
HELD_ONLY_PATH = next(path for path, body in WEEKS[1].members if body == "cardmirror")
REMOVED = hashlib.sha256(b"a removed file no snapshot of this store holds").hexdigest()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def local_evidence(data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def suppression(data_dir: Path) -> RecordedSuppressionList:
    return RecordedSuppressionList(local_suppression_list_file(data_dir))


def accepted(factory: Any, **arguments: Any) -> dict[str, Any]:
    """The arguments `factory`'s signature takes: an older build's has fewer."""
    named = inspect.signature(factory).parameters
    return {name: value for name, value in arguments.items() if name in named}


def parse_service(data_dir: Path) -> CaselistParseService:
    return CaselistParseService(
        **accepted(
            CaselistParseService,
            local=local_evidence(data_dir),
            store=LocalParsedStore(data_dir),
            parser=DebateDocxParser(),
            runner=InProcessParseRunner(),
            suppression=suppression(data_dir),
            # This build places cards given one at a time (`v1-e40-t36`); an earlier build takes them all.
            card_placer=getattr(CaselistCardStatsService(build_fake_caselist_repository()), "placer", None),
            place_cards=CaselistCardStatsService(build_fake_caselist_repository()).place,
            failure_rate_threshold=1.0,
            failure_rate_minimum_sources=1,
        )
    )


@pytest.mark.skipif(STEP != "write", reason="run with CHECK_PARSED_STORE=write")
async def test_this_build_writes_a_parsed_store_holding_held_uploads(tmp_path: Path) -> None:
    from debate_core.application.ports.suppression import (
        PathHoldEntry,
        ReasonCode,
        SuppressionAction,
        SuppressionEntry,
        disclosure_digest,
    )

    data_dir = tmp_path / "evidence"
    await import_weeks(data_dir, tmp_path / "zips", through=date(2026, 9, 15))
    service = parse_service(data_dir)
    await service.run(await service.plan(CASELIST))
    recorded = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
    await suppression(data_dir).append(
        [
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=REMOVED,
                recorded_at=recorded,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-71",
            )
        ]
    )
    await suppression(data_dir).append_path_holds(
        [
            PathHoldEntry(
                caselist=CASELIST,
                disclosure=disclosure_digest(CASELIST, path),
                sha256=REMOVED,
                after_snapshot=date(2026, 9, 1),
                recorded_at=recorded,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-71",
            )
            for path in (HELD_ONLY_PATH, R5_PATH)
        ]
    )
    service = parse_service(data_dir)
    report = await service.run(await service.plan(CASELIST))
    assert report.store is not None
    print(
        f"\nwriter: {Path(debate_core.__file__).parent}\n"
        f"this build wrote {report.plan.version}: {report.store.sources} sources, {report.store.cards} "
        f"cards, {report.store.occurrences} occurrences; {report.plan.suppressed} held or suppressed"
    )
    if COPY.exists():
        shutil.rmtree(COPY)
    shutil.copytree(data_dir, COPY)


@pytest.mark.skipif(STEP != "read", reason="run with CHECK_PARSED_STORE=read and an older build first")
async def test_the_source_on_the_path_reads_publishes_and_parses_this_builds_store(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = tmp_path / "evidence"
    shutil.copytree(COPY, data_dir)
    written = sorted(path.name for path in (data_dir / "parsed" / CASELIST).iterdir())
    print(f"\nreader: {Path(debate_core.__file__).parent}, parser {DOCX_PARSER_VERSION}")

    store = LocalParsedStore(data_dir)
    for version in await store.version_directories(CASELIST):
        entries = await store.read_entries(CASELIST, version)
        documents = [
            await store.read_document(CASELIST, version, entry.source_sha256)
            for entry in entries
            if entry.outcome is SourceOutcome.PARSED
        ]
        index = await store.read_index(CASELIST, version)
        failures = await store.read_failures(CASELIST, version)
        occurrences = await store.read_occurrences(CASELIST, version)
        assert None not in documents and None not in (index, failures, occurrences)
        assert index is not None and failures is not None and occurrences is not None
        print(
            f"read {version}: {len(entries)} per-source files, {len(documents)} documents, "
            f"{len(index)} index rows, {len(failures)} failure rows, {len(occurrences)} occurrence rows"
        )

    bucket = S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)
    parsed = FsEvidenceObjectStore(data_dir, subdirectory=Path("parsed"))
    publisher = ParsedStorePublisher(
        **accepted(
            ParsedStorePublisher,
            local=parsed,
            local_path_for=parsed.path_for,
            remote=bucket,
            suppression=suppression(data_dir),
            evidence=local_evidence(data_dir),
        )
    )
    for version in written:
        published = await publisher.publish(CASELIST, version)
        assert published.succeeded
        print(
            f"publish {version}: succeeded {published.succeeded}, "
            + ", ".join(f"{result.value} {published.count(result)}" for result in SourceResult)
        )

    service = parse_service(data_dir)
    plan = await service.plan(CASELIST)
    report = await service.run(plan)
    assert report.store is not None
    print(
        f"parse: wrote {plan.version} ({'new' if plan.new_version else 'this build’s, again'}), "
        f"{report.attempted} parsed, store {report.store.sources} sources, {report.store.occurrences} "
        "occurrences"
    )

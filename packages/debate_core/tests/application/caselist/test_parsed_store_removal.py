"""After a removal, no part of the parsed card store holds the removed source (`v1-e31-t06` ac6).

The removed team is Riverbend Academy MnPr of the parse-pipeline fixture
(`tests/fixtures/parse_pipeline/build_parse_world.py`). Its removal reaches all three aggregates:

* its PDF and its `.doc` are removed outright, and each is a row of `index.jsonl` and
  `failures.jsonl`;
* its copy of the shared `verbatim` file is withdrawn, not deleted, because Maple Grove QX holds the
  same bytes, and that copy's two disclosures are rows of `occurrences.jsonl`.

Two ways a removal reaches this machine, both checked:

* **Made here**, with `caselist remove --execute` against moto: it deletes the per-source files by
  digest and every aggregate of the caselist, in every version directory, here and in the bucket
  with every version; the next `caselist parse` rebuilds the aggregates without them.
* **Made on another machine**: only the suppression list says so. The next run's rebuild consults
  the list for each aggregate.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import (
    CASELIST,
    EXPECTED,
    SHARED_TEAM,
    WEEKS,
    digest_of,
    import_weeks,
)

from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import parse_team_selector
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService, ParseRunReport
from debate_core.application.ports.parsed_store import AGGREGATE_NAMES, version_directory_name
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.fakes import build_fake_caselist_repository, empty_suppression_list

from .conftest import REMOVAL_TIME, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REQUEST: Final = "RM-2026-02"
OLDER: Final = DOCX_PARSER_VERSION
CURRENT: Final = version_directory_name(DOCX_PARSER_VERSION, 2)
#: What the removal must leave no trace of, in any aggregate: the two files removed outright, and
#: the two disclosures of the shared file the team withdrew (its Round 5 path in 09-08 and 09-15).
REMOVED: Final = (digest_of("pdf"), digest_of("doc"))
WITHDRAWN_PATH: Final = next(
    path for path, body in WEEKS[-1].members if body == "verbatim" and "Riverbend" in path
)
WITHDRAWN: Final = disclosure_digest(CASELIST, WITHDRAWN_PATH)


def parse_service(world: RemovalWorld) -> CaselistParseService:
    return CaselistParseService(
        local=world.local,
        store=LocalParsedStore(world.data_dir),
        parser=DebateDocxParser(),
        runner=InProcessParseRunner(),
        suppression=world.suppression(),
        place_cards=CaselistCardStatsService(build_fake_caselist_repository()).place,
        failure_rate_threshold=1.0,
    )


async def parse(world: RemovalWorld, *, reparse: bool = False) -> ParseRunReport:
    service = parse_service(world)
    report = await service.run(await service.plan(CASELIST, reparse=reparse))
    local = FsEvidenceObjectStore(world.data_dir, subdirectory=Path("parsed"))
    publisher = ParsedStorePublisher(
        local=local, local_path_for=local.path_for, remote=world.bucket, suppression=world.suppression()
    )
    assert (await publisher.publish(CASELIST, report.plan.version)).succeeded
    return report


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """All three weeks imported and published; parsed twice (a re-parse makes a second directory)
    and both directories published: the state an operator is in when a request arrives."""
    data_dir = tmp_path / "evidence"
    await import_weeks(data_dir, tmp_path / "zips", through=date(2026, 9, 15))
    built = RemovalWorld(data_dir=data_dir, bucket_name=evidence_bucket, client=s3_client)
    publisher = CaselistPublishService(
        local=built.local, remote=built.bucket, suppression=empty_suppression_list()
    )
    assert (await publisher.execute(await publisher.plan(CASELIST))).succeeded
    await parse(built)
    assert (await parse(built, reparse=True)).plan.version == CURRENT
    return built


def local_aggregates(world: RemovalWorld) -> dict[str, list[dict[str, object]]]:
    root = world.data_dir / "parsed" / CASELIST
    return {
        path.relative_to(root).as_posix(): [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        for path in sorted(root.glob("*/*.jsonl"))
        if path.name in AGGREGATE_NAMES
    }


def bucket_versions(world: RemovalWorld, prefix: str) -> list[tuple[str, str]]:
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix=prefix)
    return [(str(v.get("Key")), str(v.get("VersionId"))) for v in listed.get("Versions", [])]


def bucket_aggregate_rows(world: RemovalWorld) -> list[dict[str, object]]:
    """Every row of every version of every aggregate in the bucket, current and noncurrent."""
    rows: list[dict[str, object]] = []
    for key, version_id in bucket_versions(world, f"parsed/{CASELIST}/"):
        if key.rsplit("/", 1)[-1] in AGGREGATE_NAMES:
            body = world.client.get_object(Bucket=world.bucket_name, Key=key, VersionId=version_id)[
                "Body"
            ].read()
            rows += [json.loads(line) for line in body.decode().splitlines()]
    return rows


def traces(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """The rows derived from what the removal took out."""
    return [row for row in rows if row["source_sha256"] in REMOVED or row.get("disclosure") == WITHDRAWN]


async def remove_shared_team(world: RemovalWorld) -> None:
    remover = world.service()
    plan = await remover.plan(
        parse_team_selector(SHARED_TEAM), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    await remover.execute(plan)


async def test_before_the_removal_the_team_is_in_every_aggregate(world: RemovalWorld) -> None:
    """The precondition the other tests rely on: each aggregate starts with a row to remove."""
    current = local_aggregates(world)
    for name in AGGREGATE_NAMES:
        assert traces(current[f"{CURRENT}/{name}"]), name
    assert traces(bucket_aggregate_rows(world))


async def test_caselist_remove_leaves_no_aggregate_holding_the_team_here_or_in_the_bucket(
    world: RemovalWorld,
) -> None:
    """Between the removal and the next run: nothing derived from the team, in any version directory."""
    await remove_shared_team(world)

    for name, rows in local_aggregates(world).items():
        assert traces(rows) == [], name
    assert traces(bucket_aggregate_rows(world)) == []


async def test_caselist_remove_deletes_the_removed_sources_files_in_every_version_directory(
    world: RemovalWorld,
) -> None:
    """The per-source files are deleted by digest, in the older generation too, here and in the bucket."""
    await remove_shared_team(world)

    for digest in REMOVED:
        assert not list((world.data_dir / "parsed").rglob(f"{digest}*"))
        assert [key for key, _ in bucket_versions(world, f"parsed/{CASELIST}/") if digest in key] == []
    shared = digest_of("verbatim")
    for version in (OLDER, CURRENT):
        assert list((world.data_dir / "parsed" / CASELIST / version).rglob(f"{shared}.jsonl")), version


async def test_the_next_run_rebuilds_each_aggregate_without_the_team(world: RemovalWorld) -> None:
    await remove_shared_team(world)

    report = await parse(world)

    expected = EXPECTED["after_shared_team_removed"]
    assert report.plan.version == CURRENT
    assert report.attempted == 0
    assert report.store is not None
    assert (report.store.sources, report.store.unsupported, report.store.occurrences) == (
        expected["sources"],
        expected["unsupported"],
        expected["occurrences"],
    )
    current = local_aggregates(world)
    for name in AGGREGATE_NAMES:
        assert traces(current[f"{CURRENT}/{name}"]) == [], name
    assert {row["source_sha256"] for row in current[f"{CURRENT}/failures.jsonl"]} == {digest_of("broken")}
    assert f"{OLDER}/index.jsonl" not in current
    assert traces(bucket_aggregate_rows(world)) == []


async def test_a_removal_made_elsewhere_is_honoured_by_each_aggregate_of_the_next_run(
    world: RemovalWorld,
) -> None:
    """Only the suppression list knows: the files and manifest rows are all still on this machine."""
    entries = [
        SuppressionEntry(
            action=SuppressionAction.SUPPRESS,
            sha256=digest,
            recorded_at=REMOVAL_TIME,
            reason=ReasonCode.REQUESTED_BY_TEAM,
            request_id=REQUEST,
        )
        for digest in REMOVED
    ] + [
        SuppressionEntry(
            action=SuppressionAction.SUPPRESS,
            sha256=digest_of("verbatim"),
            disclosure=WITHDRAWN,
            recorded_at=REMOVAL_TIME,
            reason=ReasonCode.REQUESTED_BY_TEAM,
            request_id=REQUEST,
        )
    ]
    await world.suppression().append(entries)

    report = await parse(world)

    expected = EXPECTED["after_shared_team_removed"]
    assert report.store is not None
    assert (report.store.sources, report.store.occurrences) == (expected["sources"], expected["occurrences"])
    current = local_aggregates(world)
    for name in AGGREGATE_NAMES:
        assert traces(current[f"{CURRENT}/{name}"]) == [], name

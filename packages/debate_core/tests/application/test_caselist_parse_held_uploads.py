"""`caselist parse` and `--publish` send nothing of a held upload (`v1-e31-t26`).

A removal by `--source` holds the removed file's path (`v1-e30-t13`): an upload there in a later
snapshot is the requester's, and this build's importer refuses it. A build from before that task
imported one, and `caselist parse` parsed it, because the parse skipped only what the suppression
list stops. Its parsed file then went to the bucket with `--publish`, and its rows to the caselist's
index, failures file and occurrence table, which the student search pilot's index is built from
(E39).

The parse asks the publisher's own rule for a held row
(:func:`~debate_core.application.caselist.publish_plan.stored_row_hold`) of every disclosure, before
it parses a source, before it writes the source's rows to the aggregates, and before it publishes the
source's parsed file. Bytes another live path discloses are parsed and published as before; only the
held disclosure's occurrence rows go.

The world is `test_caselist_parse.py`'s: the fictional caselist of
`tests/fixtures/parse_pipeline/build_parse_world.py`, whose documents hold cards. A hold is appended
as a removal made on another machine leaves it here: the removed file's suppression entry and the
hold on the path it was taken from. The removed file itself is an invented digest no week holds,
because it has already gone; what the hold covers is the upload at its path afterwards.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import (
    CASELIST,
    R1_COPY_PATH,
    R1_PATH,
    R5_PATH,
    WEEKS,
    digest_of,
    import_weeks,
)

from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.ports.parsed_store import AGGREGATE_NAMES
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_caselist_parse import THROUGH_0908, CountingParser, World, publisher, put_requests

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REQUEST: Final = "RM-2026-71"
#: The file the removal took, from each path below in `2026-09-01`. No week holds it any more.
REMOVED: Final = hashlib.sha256(b"a removed file no snapshot of this store holds").hexdigest()
HOLD_DATE: Final = date(2026, 9, 1)

#: `cardmirror`'s only path, first listed in `2026-09-08`: held there, its bytes are held only.
HELD_ONLY_PATH: Final = next(path for path, body in WEEKS[1].members if body == "cardmirror")
#: `broken`'s only path, first listed in `2026-09-08`: a held upload that fails to parse.
HELD_FAILURE_PATH: Final = next(path for path, body in WEEKS[1].members if body == "broken")
PREFIX: Final = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def world(tmp_path: Path) -> World:
    """09-01 and 09-08 imported, as a build that reads no hold imports them; nothing parsed yet."""
    built = World(data_dir=tmp_path / "evidence", zips_dir=tmp_path / "zips")
    await import_weeks(built.data_dir, built.zips_dir, through=THROUGH_0908)
    return built


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


async def hold(world: World, *paths: str) -> None:
    """A `--source` removal of :data:`REMOVED` from each of `paths`, made on another machine."""
    recorded = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
    await world.suppression.append(
        [
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=REMOVED,
                recorded_at=recorded,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id=REQUEST,
            )
        ]
    )
    await world.suppression.append_path_holds(
        [
            PathHoldEntry(
                caselist=CASELIST,
                disclosure=disclosure_digest(CASELIST, path),
                sha256=REMOVED,
                after_snapshot=HOLD_DATE,
                recorded_at=recorded,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id=REQUEST,
            )
            for path in paths
        ]
    )


def digests_in(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["source_sha256"]) for row in rows}


def aggregates(world: World) -> dict[str, list[dict[str, Any]]]:
    return {name: world.lines(name) for name in AGGREGATE_NAMES}


def bucket_rows(s3_client: S3Client, bucket_name: str, name: str) -> list[dict[str, Any]]:
    body = s3_client.get_object(Bucket=bucket_name, Key=f"{PREFIX}/{name}")["Body"].read()
    return [json.loads(line) for line in body.decode("utf-8").splitlines()]


# ------------------------------------------------------------------------------------------------
# Held only: neither parsed, nor in an aggregate, nor published
# ------------------------------------------------------------------------------------------------


async def test_a_held_uploads_source_is_not_parsed_and_is_in_no_aggregate(world: World) -> None:
    held = digest_of("cardmirror")
    await hold(world, HELD_ONLY_PATH)
    parser = CountingParser()

    report = await world.run(parser)

    assert held not in parser.parsed
    assert report.plan.suppressed == 1
    for name, rows in aggregates(world).items():
        assert held not in digests_in(rows), name
    assert not list((world.store.root / CASELIST).rglob(f"{held}*"))


async def test_an_earlier_builds_parse_of_a_held_upload_leaves_every_aggregate(world: World) -> None:
    """The earlier build parsed it, so its file is in the version directory, which this build's run
    writes into again: the rebuild leaves its rows out of each aggregate."""
    held = digest_of("cardmirror")
    await world.run()
    assert held in digests_in(world.lines("index.jsonl")), "the precondition: the earlier build's rows"
    await hold(world, HELD_ONLY_PATH)

    report = await world.run()

    assert report.store is not None
    assert report.attempted == 0
    for name, rows in aggregates(world).items():
        assert held not in digests_in(rows), name
    assert report.store.cards == sum(int(row["cards"]) for row in world.lines("index.jsonl"))


async def test_publish_sends_nothing_of_an_earlier_builds_parse_of_a_held_upload(
    world: World, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
) -> None:
    held = digest_of("cardmirror")
    await world.run()
    await hold(world, HELD_ONLY_PATH)
    await world.run()
    held_file = f"{PREFIX}/sha256/{held[0:2]}/{held[2:4]}/{held}.jsonl"
    assert held_file.split("/", 3)[3] in world.tree(), "the precondition: the earlier build's parsed file"
    puts = put_requests(s3_client)

    report = await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    assert report.succeeded
    assert held_file not in puts
    assert not any(held in put for put in puts)
    assert {outcome.key for outcome in report.objects if outcome.result is SourceResult.SUPPRESSED} == {
        held_file
    }
    for name in AGGREGATE_NAMES:
        assert f"{PREFIX}/{name}" in puts, name
        assert held not in digests_in(bucket_rows(s3_client, evidence_bucket, name)), name


async def test_a_held_upload_that_failed_is_in_no_failure_listing(world: World) -> None:
    """The listing names each failure by its manifest path, which here is the held path."""
    await world.run()
    await hold(world, HELD_FAILURE_PATH)
    await world.run()

    listing = await world.service().failures(CASELIST)

    assert digest_of("broken") not in {row.sha256 for row in listing.rows}
    assert digest_of("broken") not in digests_in(world.lines("failures.jsonl"))


# ------------------------------------------------------------------------------------------------
# Bytes another live path discloses: parsed and published, without the held disclosure
# ------------------------------------------------------------------------------------------------


async def test_bytes_another_live_path_discloses_are_parsed_and_published(
    world: World, bucket: S3EvidenceObjectStore, s3_client: S3Client
) -> None:
    """`verbatim` is held at R5, from `2026-09-08`, and live at R1 and its `(1)` copy."""
    shared = digest_of("verbatim")
    await hold(world, R5_PATH)
    parser = CountingParser()

    await world.run(parser)
    puts = put_requests(s3_client)
    report = await publisher(world, bucket).publish(CASELIST, DOCX_PARSER_VERSION)

    assert shared in parser.parsed
    assert shared in digests_in(world.lines("index.jsonl"))
    assert f"{PREFIX}/sha256/{shared[0:2]}/{shared[2:4]}/{shared}.jsonl" in puts
    assert report.succeeded and report.count(SourceResult.SUPPRESSED) == 0


async def test_only_the_held_disclosures_occurrence_rows_go(world: World) -> None:
    shared = digest_of("verbatim")
    await hold(world, R5_PATH)

    await world.run()

    rows = [row for row in world.lines("occurrences.jsonl") if row["source_sha256"] == shared]
    assert sorted((row["disclosure"], row["snapshot"], row["last_snapshot"]) for row in rows) == sorted(
        [
            (disclosure_digest(CASELIST, R1_PATH), "2026-09-01", "2026-09-08"),
            (disclosure_digest(CASELIST, R1_COPY_PATH), "2026-09-08", "2026-09-08"),
        ]
    )


async def test_a_path_live_before_the_hold_dates_from_keeps_only_its_earlier_rows(world: World) -> None:
    """R1 held from `2026-09-01`: its `2026-09-01` row is the earlier version, which the removal does
    not cover, and its `2026-09-08` row is held. The disclosure's span ends where the hold begins."""
    shared = digest_of("verbatim")
    await hold(world, R1_PATH)

    await world.run()

    rows = [
        row
        for row in world.lines("occurrences.jsonl")
        if row["source_sha256"] == shared and row["disclosure"] == disclosure_digest(CASELIST, R1_PATH)
    ]
    assert [(row["snapshot"], row["last_snapshot"]) for row in rows] == [("2026-09-01", "2026-09-01")]

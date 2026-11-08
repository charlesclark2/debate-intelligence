"""A removal keeps the parse a snapshot is owed: nothing is rebuilt after it (`v1-e30-t34`).

Until this task a removal cleared the parse owed of each snapshot whose manifest it rewrote
(`v1-e40-t08`), because the rebuild `caselist-removal.md` then asked for parsed whatever was unparsed.
Since `v1-e30-t33` nothing follows a removal, and the parse stage chooses a caselist to parse only when
the parse-owed file names it, its store has no directory of the running parser version, or the run
imported into it. A caselist parsed before always has such a directory, so a snapshot whose entry a
removal cleared waited for its caselist's next import. The PM's ruling of 2026-11-08: stop clearing.

So the removal leaves the parse-owed file as it found it, every entry and every byte, the snapshot it
reached included. Keeping the entry cannot bring the removed file back: an entry names a caselist to
parse, never a source, and the parse plans from the manifests the removal rewrote, which no longer
name it. The command-level proof, the next run parsing the owed caselist without the removed file in
local and bucket mode, is `packages/debate_cli/tests/bucket_mode/test_parse_owed.py`.

The file removed is the Seaside Cup round 5 affirmative: in the `testcl26` week of 2026-09-15 only,
beside the Bayview semifinal negative, which the same week added and which stays.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest
from tests.fixtures.caselist.publish_expectations import digest_of_body

from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.removal_service import CaselistRemovalService
from debate_core.application.caselist_sync import (
    PARSE_OWED_FILENAME,
    FullParseOwed,
    ParseOwed,
    PendingSnapshot,
)
from debate_core.application.ports.suppression import ReasonCode, RemovalOutcome
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION

from .conftest import REQUEST, RemovalWorld

pytestmark = pytest.mark.anyio

CASELIST = "testcl26"
REMOVED = digest_of_body("seaside-round-5-aff")
KEPT = digest_of_body("bayview-semis-neg")
"""Added in the same week as the removed file, and not removed."""

REACHED = PendingSnapshot(caselist=CASELIST, snapshot="2026-09-15")
"""The snapshot whose manifest the removal rewrites: the one an entry was cleared for until this task."""


def service_of(world: RemovalWorld) -> CaselistRemovalService:
    """The removal service as the composition root builds it.

    A build before `v1-e30-t34` took the parse-owed file in the data directory, which it cleared from,
    and is given it here; this build takes none. A build that takes one again is given it too, so that
    these tests hold whatever it does with it.
    """
    service = world.service()
    if any(one.name == "parse_owed" for one in fields(service)):
        given = {"parse_owed": ParseOwed(world.data_dir / PARSE_OWED_FILENAME)}
        service = replace(service, **given)  # pyright: ignore[reportArgumentType]
    return service


async def test_a_removal_that_reaches_an_owed_snapshot_keeps_every_parse_owed_byte_for_byte(
    removal_world: RemovalWorld,
) -> None:
    owed = ParseOwed(removal_world.data_dir / PARSE_OWED_FILENAME)
    owed.owe(
        snapshots=[
            PendingSnapshot(caselist=CASELIST, snapshot="2026-09-08"),
            REACHED,
            PendingSnapshot(caselist="openev", snapshot="2026-policy"),
        ],
        full_parses=[FullParseOwed(caselist=CASELIST, parser_version=DOCX_PARSER_VERSION)],
    )
    before = owed.path.read_bytes()
    service = service_of(removal_world)
    plan = await service.plan(
        SourceSelector(REMOVED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    assert f"manifests/{CASELIST}/2026-09-15.jsonl" in {rewrite.key for rewrite in plan.manifests}, (
        "the premise: the removal rewrites the owed snapshot's manifest"
    )

    report = await service.execute(plan)

    assert report.log_entry.outcome is RemovalOutcome.COMPLETED
    assert owed.path.is_file(), "the file is kept"
    assert owed.path.read_bytes() == before, "every entry kept, the reached snapshot's included"
    assert REACHED in owed.read().snapshots


async def test_after_a_removal_the_owed_caselists_sources_leave_out_the_removed_file(
    removal_world: RemovalWorld,
) -> None:
    """What the next parse stage plans from (:func:`enumerate_sources`): the manifests as the removal
    rewrote them. The removed file is not among them; the file added beside it still is."""
    ParseOwed(removal_world.data_dir / PARSE_OWED_FILENAME).owe(snapshots=[REACHED])
    service = service_of(removal_world)
    before = {source.sha256 for source in await enumerate_sources(removal_world.local, CASELIST)}
    assert {REMOVED, KEPT} <= before, "the premise: both are sources of the caselist before"

    await service.execute(
        await service.plan(SourceSelector(REMOVED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)
    )

    after = {source.sha256 for source in await enumerate_sources(removal_world.local, CASELIST)}
    assert after == before - {REMOVED}
    assert ParseOwed(removal_world.data_dir / PARSE_OWED_FILENAME).read().snapshots == (REACHED,)

"""Manifest and aggregate versions older than a removal, as `caselist status` reports them (`v1-e30-t15`).

A removal rewrites each manifest that held the file and purges every other version of it, and it
deletes every version of the parsed store's aggregates. So a version of one of those, older than the
removal, is something the removal should have taken. `caselist status` finds them by comparing the
listing's `LastModified` with the removal log's completion time, and downloads nothing.

Every bucket here is moto's, versioned, and every removal is the real one. The removal's clock is
fixed at :data:`COMPLETED`, and moto stamps what it writes with the time the test runs, which is
later. A version the test needs older is put and then **backdated** in moto's own record of it
(:func:`backdate`): moto keeps a version's `last_modified` as a plain attribute and computes
`IsLatest` from it, so a backdated version is listed exactly as an old one would be, and the tests
keep each key's versions in the order they were written. Every count asserted is worked out by hand
beside the edit that causes it (working agreements §6).

Fixture facts the expectations rest on, read from `tests/fixtures/caselist/build_synthetic_archives.py`:
the Seaside Cup round 5 affirmative is in the week of 2026-09-15 only, it is no camp file, and no
other team holds it. (The Harbor Classic octafinals negative, which `v1-e30-t10`'s tests remove, is
no use here: the week it disappeared from records a `REMOVED` row at its path, so a removal of it
rewrites every manifest of the caselist.)
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.s3.models import FakeKey, s3_backends
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.caselist.publish_expectations import digest_of_body
from tests.fixtures.openev.build_synthetic_openev import SYNTHETIC_EVENT as OPENEV_EVENT
from tests.fixtures.openev.build_synthetic_openev import SYNTHETIC_YEAR as OPENEV_YEAR

from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.removal_residue import (
    CaselistResidue,
    OlderVersions,
    RemovalCompletion,
)
from debate_core.application.caselist.removal_service import RemovalReport
from debate_core.application.caselist.status_service import CaselistStatusReport, CaselistStatusService
from debate_core.application.caselist.suppression import (
    REMOVAL_LOG_KEY,
    SUPPRESSION_LIST_KEY,
    RecordedRemovalLog,
)
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.suppression import (
    REMOVAL_SCOPES_FILENAME,
    ManifestRewriteRecord,
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    RemovalSelectorKind,
)
from debate_core.integrations.local.suppression_list import local_removal_log_file
from debate_core.integrations.s3 import S3EvidenceVersionStore

from .conftest import REMOVAL_TIME, REQUEST, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    pass

pytestmark = pytest.mark.anyio

REMOVED = digest_of_body("seaside-round-5-aff")
REWRITTEN = (f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl",)
"""The one manifest that holds the removed file: what the removal rewrites."""
NOT_REWRITTEN = f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl"
"""A manifest of the same caselist that never held it."""
OPENEV_MANIFEST = f"manifests/openev/{OPENEV_YEAR}-{OPENEV_EVENT.lower()}.jsonl"
PARSER_VERSIONS = ("2026.10.10-docx-2", "2026.10.12-docx-3")
"""The parsed store's version directory now, and the one the coming re-parse writes."""
AGGREGATES = ("index.jsonl", "failures.jsonl", "occurrences.jsonl")
COMPLETED = REMOVAL_TIME
"""What the removal log records as the removal's completion: its clock is fixed there."""
MARGIN = timedelta(minutes=15)
LONG_BEFORE = COMPLETED - timedelta(days=1)
SCOPES_KEY = f"manifests/_suppression/{REMOVAL_SCOPES_FILENAME}"


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------


def backdate(world: RemovalWorld, key: str, version_id: str, when: datetime) -> None:
    """Set the `LastModified` moto lists for one version, as if it had been written at `when`.

    moto lists a key's versions newest first by this time, but serves the last one it stored as the
    current one, so the stored list is put back in the order of the times as well: a version
    backdated beneath the current one stays beneath it for a `GetObject` too.
    """
    stored: list[FakeKey] = (
        s3_backends[DEFAULT_ACCOUNT_ID]["aws"].get_bucket(world.bucket_name).keys.getlist(key)
    )
    matching = [one for one in stored if one.version_id == version_id]
    assert len(matching) == 1, f"no single version {version_id} of {key}"
    matching[0].last_modified = when.astimezone(UTC).replace(tzinfo=None)
    stored.sort(key=lambda one: one.last_modified)


def put(world: RemovalWorld, key: str, body: bytes, *, written: datetime | None = None) -> str:
    """Put one version and return its id; with `written`, backdated to then."""
    version_id = str(world.client.put_object(Bucket=world.bucket_name, Key=key, Body=body)["VersionId"])
    if written is not None:
        backdate(world, key, version_id, written)
    return version_id


def aggregate_key(caselist: str, version: str, name: str) -> str:
    return f"parsed/{caselist}/{version}/{name}"


def current_bytes(world: RemovalWorld, key: str) -> bytes:
    return world.client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read()


def versions_of(world: RemovalWorld, key: str) -> list[str]:
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix=key)
    return [str(one.get("VersionId")) for one in listed.get("Versions", []) if one.get("Key") == key]


async def remove(world: RemovalWorld) -> RemovalReport:
    """`caselist remove --source <the round 5 affirmative> --request RM-2026-01 --execute`."""
    service = world.service()
    plan = await service.plan(
        SourceSelector(REMOVED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    report = await service.execute(plan)
    assert report.completed
    return report


async def status(
    world: RemovalWorld,
    *,
    versions: EvidenceVersionStore | None = None,
    removal_log: RecordedRemovalLog | None = None,
    environment: str = "dev",
) -> CaselistStatusReport:
    """`caselist status`, every caselist, with the residue check, as the command builds it."""
    service = CaselistStatusService(
        local=world.local,
        remote=world.bucket,
        suppression=world.suppression(),
        versions=versions or S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client),
        removal_log=removal_log or world.removal_log(),
        environment=environment,
    )
    return await service.status(residue=True)


def of(report: CaselistStatusReport, caselist: str) -> CaselistResidue:
    (found,) = [one for one in report.residue if one.caselist == caselist]
    return found


@pytest.fixture
async def removed(removal_world: RemovalWorld) -> RemovalWorld:
    """The removal completed, and its rewrites put back at a plausible time inside the run.

    moto stamps each rewrite with the time the test runs, which is after the fixed completion
    time. A real rewrite is written during the run, before its completion is logged: two minutes
    before, here.
    """
    await remove(removal_world)
    for key in REWRITTEN:
        (only,) = versions_of(removal_world, key)
        backdate(removal_world, key, only, COMPLETED - timedelta(minutes=2))
    return removal_world


# ------------------------------------------------------------------------------------------------
# ac1: the takedown's behaviour that makes the model true, and where it does not
# ------------------------------------------------------------------------------------------------


class TestWhatTheTakedownLeaves:
    async def test_a_manifest_it_rewrites_keeps_no_version_but_the_rewrite(
        self, removal_world: RemovalWorld
    ) -> None:
        """The manifest that held the file had three versions: the publish's and two more."""
        world = removal_world
        for key in REWRITTEN:
            body = current_bytes(world, key)
            put(world, key, body)
            put(world, key, body)
            assert len(versions_of(world, key)) == 3

        await remove(world)

        for key in REWRITTEN:
            assert len(versions_of(world, key)) == 1, key
            assert REMOVED.encode() not in current_bytes(world, key)

    async def test_it_deletes_every_version_of_every_aggregate_in_every_version_directory(
        self, removal_world: RemovalWorld
    ) -> None:
        """Two versions of each aggregate, in both version directories, of both caselists."""
        world = removal_world
        for caselist in (SYNTHETIC_CASELIST, "openev"):
            for version in PARSER_VERSIONS:
                for name in AGGREGATES:
                    put(world, aggregate_key(caselist, version, name), b"first build\n")
                    put(world, aggregate_key(caselist, version, name), b"second build\n")

        await remove(world)

        left = world.client.list_object_versions(Bucket=world.bucket_name, Prefix="parsed/")
        assert [one.get("Key") for one in left.get("Versions", [])] == []
        assert [one.get("Key") for one in left.get("DeleteMarkers", [])] == []

    async def test_a_manifest_it_did_not_rewrite_keeps_a_version_that_never_named_the_file(
        self, removal_world: RemovalWorld
    ) -> None:
        """Where the model is wrong. The sweep downloads each noncurrent manifest version of the
        caselist and deletes those that name what was removed; this one does not, so it stays,
        older than the removal. The same happens to a camp release's manifest re-published by
        `caselist reimport-openev-metadata`."""
        world = removal_world
        put(world, NOT_REWRITTEN, current_bytes(world, NOT_REWRITTEN))
        assert len(versions_of(world, NOT_REWRITTEN)) == 2

        await remove(world)

        assert len(versions_of(world, NOT_REWRITTEN)) == 2

    async def test_beside_its_log_entry_it_records_the_caselists_it_touched_and_the_manifests_it_rewrote(
        self, removal_world: RemovalWorld
    ) -> None:
        """What `caselist status` needs and the removal log does not hold, written by the removal.

        In both places, beside the log, and joined to its entry. The log line itself keeps the keys
        every installed build writes.
        """
        world = removal_world

        report = await remove(world)

        expected = RemovalScopeEntry(
            recorded_at=COMPLETED,
            request_id=REQUEST,
            environment="dev",
            caselists=(SYNTHETIC_CASELIST,),
            manifest_rewrites=tuple(
                ManifestRewriteRecord(key=key, version_id=versions_of(world, key)[0]) for key in REWRITTEN
            ),
        )
        assert await world.removal_log().scopes() == (expected,)
        assert expected.joins(report.log_entry)
        for copy in (
            current_bytes(world, SCOPES_KEY).decode(),
            (world.data_dir / "suppression" / REMOVAL_SCOPES_FILENAME).read_text(encoding="utf-8"),
        ):
            assert copy == expected.to_line() + "\n"
        (log_line,) = current_bytes(world, REMOVAL_LOG_KEY).decode().splitlines()
        assert set(json.loads(log_line)) == set(RemovalLogEntry.model_fields)


# ------------------------------------------------------------------------------------------------
# ac2: what is reported
# ------------------------------------------------------------------------------------------------


class TestOlderVersionsAreReported:
    async def test_a_manifest_and_an_aggregate_version_older_than_the_removal_are_reported_by_role(
        self, removed: RemovalWorld
    ) -> None:
        """One manifest version the purge missed, and two aggregate versions, a day before it."""
        world = removed
        put(world, REWRITTEN[0], b"the manifest as it was\n", written=LONG_BEFORE)
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[1], "occurrences.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )

        report = await status(world)

        residue = of(report, SYNTHETIC_CASELIST)
        assert residue.checked
        assert residue.files == ()
        assert residue.older_versions == (
            OlderVersions(role="manifest", versions=1),
            OlderVersions(role="index.jsonl", versions=1),
            OlderVersions(role="occurrences.jsonl", versions=1),
        )
        assert residue.older_than == RemovalCompletion(request_id=REQUEST, completed_at=COMPLETED)
        assert report.residue_found
        assert not report.in_sync
        assert of(report, "openev").older_versions == ()

    async def test_versions_written_after_the_removal_are_not_reported(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """The aggregates rebuilt afterwards, as step 5 of the runbook does, and a manifest re-published.

        moto stamps them with the time the test runs, after the removal. The rewrite becomes
        noncurrent and is still not reported: it is the removal's own.
        """
        world = removed
        for version in PARSER_VERSIONS:
            for name in AGGREGATES:
                put(world, aggregate_key(SYNTHETIC_CASELIST, version, name), b"rebuilt\n")
        republished = tmp_path / "manifest.jsonl"
        republished.write_bytes(current_bytes(world, REWRITTEN[0]))
        await world.bucket.put_file(REWRITTEN[0], republished)
        assert len(versions_of(world, REWRITTEN[0])) == 2

        report = await status(world)

        residue = of(report, SYNTHETIC_CASELIST)
        assert residue.checked
        assert residue.older_versions == ()
        assert residue.older_than == RemovalCompletion(request_id=REQUEST, completed_at=COMPLETED)
        assert not report.residue_found
        assert report.in_sync

    async def test_the_margin_reports_a_version_before_it_and_nothing_at_or_inside_it(
        self, removed: RemovalWorld
    ) -> None:
        """Fifteen minutes, S3's own bound on how far this machine's clock can be from its own.

        One second outside the margin is residue; the boundary itself and one second inside are
        given to a later write.
        """
        world = removed
        version = PARSER_VERSIONS[0]
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, version, "index.jsonl"),
            b"x\n",
            written=COMPLETED - MARGIN - timedelta(seconds=1),
        )
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, version, "failures.jsonl"),
            b"x\n",
            written=COMPLETED - MARGIN,
        )
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, version, "occurrences.jsonl"),
            b"x\n",
            written=COMPLETED - MARGIN + timedelta(seconds=1),
        )

        residue = of(await status(world), SYNTHETIC_CASELIST)

        assert residue.older_versions == (OlderVersions(role="index.jsonl", versions=1),)

    async def test_the_removals_own_rewrite_is_never_residue_however_long_the_run_took(
        self, removed: RemovalWorld
    ) -> None:
        """A run that rewrote the manifest twenty minutes before it finished: the inbox's zips are slow."""
        world = removed
        (rewrite,) = versions_of(world, REWRITTEN[0])
        backdate(world, REWRITTEN[0], rewrite, COMPLETED - timedelta(minutes=20))

        residue = of(await status(world), SYNTHETIC_CASELIST)

        assert residue.checked
        assert residue.older_versions == ()

    async def test_a_current_aggregate_the_removal_did_not_delete_is_counted(
        self, removed: RemovalWorld
    ) -> None:
        """What a takedown that stopped short, or a build from before it deleted them, leaves: the
        aggregate is still the current one, from before the removal."""
        world = removed
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "failures.jsonl"),
            b"a\n",
            written=LONG_BEFORE - timedelta(hours=1),
        )
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "failures.jsonl"),
            b"b\n",
            written=LONG_BEFORE,
        )

        residue = of(await status(world), SYNTHETIC_CASELIST)

        assert residue.older_versions == (OlderVersions(role="failures.jsonl", versions=2),)


# ------------------------------------------------------------------------------------------------
# ac3: what is not, and what cannot be checked
# ------------------------------------------------------------------------------------------------


class RefusesUnder:
    """The everyday profile, refused the version listing under one prefix only."""

    def __init__(self, inner: EvidenceVersionStore, prefix: str) -> None:
        self._inner = inner
        self._prefix = prefix
        self.location = inner.location

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        if prefix.startswith(self._prefix):
            raise StoreAccessDenied("ListObjectVersions", f"{self.location}/{prefix}")
        return await self._inner.list_versions(prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        raise AssertionError("caselist status downloaded an object version")

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        raise AssertionError("caselist status deleted something")


class TestWhatIsNotReported:
    async def test_a_caselist_no_removal_touched_reports_nothing_whatever_versions_it_has(
        self, removed: RemovalWorld
    ) -> None:
        """OpenEv held nothing removed. Its release manifest has an old noncurrent version, as a
        metadata re-import leaves one, and its aggregates are a day older than the removal."""
        world = removed
        put(world, OPENEV_MANIFEST, b"the release as first imported\n", written=LONG_BEFORE)
        for name in AGGREGATES:
            put(world, aggregate_key("openev", PARSER_VERSIONS[0], name), b"old\n", written=LONG_BEFORE)

        report = await status(world)

        openev = of(report, "openev")
        assert openev == CaselistResidue(caselist="openev", checked=True)
        assert report.in_sync

    async def test_a_manifest_the_removal_did_not_rewrite_is_not_reported_for_versions_it_kept(
        self, removed: RemovalWorld
    ) -> None:
        """The week the file was never in. Its version from before the removal is one the sweep
        read and kept, because it names nothing removed (the ac1 test above)."""
        world = removed
        put(world, NOT_REWRITTEN, current_bytes(world, NOT_REWRITTEN), written=LONG_BEFORE)

        residue = of(await status(world), SYNTHETIC_CASELIST)

        assert residue.checked
        assert residue.older_versions == ()

    async def test_the_suppression_records_old_versions_are_never_residue(
        self, removed: RemovalWorld
    ) -> None:
        """`manifests/_suppression/` is appended to, and its versions are the record of what was asked."""
        world = removed
        put(world, SUPPRESSION_LIST_KEY, b"", written=LONG_BEFORE)

        report = await status(world)

        assert not report.residue_found

    @pytest.mark.parametrize("refused", ["raw/", "parsed/", "manifests/"])
    async def test_a_refused_listing_is_not_checked_and_never_none(
        self, removed: RemovalWorld, refused: str
    ) -> None:
        """An old aggregate and an old manifest version are there; a profile refused any one of the
        three listings sees neither, and says so."""
        world = removed
        put(world, REWRITTEN[0], b"the manifest as it was\n", written=LONG_BEFORE)
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )
        everyday = S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client)

        report = await status(world, versions=RefusesUnder(everyday, refused))

        residue = of(report, SYNTHETIC_CASELIST)
        assert residue == CaselistResidue(
            caselist=SYNTHETIC_CASELIST, checked=False, not_checked_reason="STORE_ACCESS_DENIED"
        )
        assert residue.current_objects is None
        assert not report.residue_found
        assert SYNTHETIC_CASELIST in report.residue_not_checked


# ------------------------------------------------------------------------------------------------
# Which removal log decides
# ------------------------------------------------------------------------------------------------


def log_entry(
    *,
    request_id: str,
    recorded_at: datetime,
    environment: str = "dev",
    outcome: RemovalOutcome = RemovalOutcome.COMPLETED,
) -> RemovalLogEntry:
    return RemovalLogEntry(
        kind=RemovalLogKind.REMOVAL,
        recorded_at=recorded_at,
        request_id=request_id,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        environment=environment,
        outcome=outcome,
        selector=RemovalSelectorKind.SOURCE,
        removed_sha256=(REMOVED,),
        error_code=None if outcome is RemovalOutcome.COMPLETED else "STORE_UNAVAILABLE",
    )


def scope_of(entry: RemovalLogEntry, *caselists: str) -> RemovalScopeEntry:
    return RemovalScopeEntry(
        recorded_at=entry.recorded_at,
        request_id=entry.request_id,
        environment=entry.environment,
        caselists=caselists,
        manifest_rewrites=(),
    )


async def log_in(
    directory: Path, entries: Sequence[RemovalLogEntry], scopes: Sequence[RemovalScopeEntry] = ()
) -> RecordedRemovalLog:
    """A removal log of its own, on this machine only, holding `entries` and, beside them, `scopes`."""
    log = RecordedRemovalLog(local_removal_log_file(directory))
    await log.append(entries, scopes=scopes)
    return log


class TestTheRemovalLog:
    async def test_a_removal_an_old_build_made_has_no_scope_and_is_named_as_not_checked(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """A completed removal with no scope beside its log entry: made by a build from before this
        one, which recorded neither. It cannot say which caselists it touched, so nothing is
        compared with it, and the report says so rather than reading it as none."""
        world = removed
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE - timedelta(days=1),
        )
        old = log_entry(request_id="RM-2026-90", recorded_at=COMPLETED - timedelta(hours=12))

        report = await status(world, removal_log=await log_in(tmp_path, [old]))

        assert report.removals_not_checked == ("RM-2026-90",)
        assert of(report, SYNTHETIC_CASELIST).older_than is None
        assert of(report, SYNTHETIC_CASELIST).older_versions == ()

    async def test_a_removal_recorded_only_in_the_buckets_copy_is_compared(
        self, removed: RemovalWorld
    ) -> None:
        """The environment's own record is the bucket's: a removal run from another data directory."""
        world = removed
        local_removal_log_file(world.data_dir).path.unlink()
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )

        residue = of(await status(world), SYNTHETIC_CASELIST)

        assert residue.older_than == RemovalCompletion(request_id=REQUEST, completed_at=COMPLETED)
        assert residue.older_versions == (OlderVersions(role="index.jsonl", versions=1),)

    async def test_only_this_environments_removals_are_compared(self, removed: RemovalWorld) -> None:
        """Prod's status runs against the dev data directory, whose local copy holds dev's removals.

        Dev's removal is no completion in prod: prod may not have run it yet.
        """
        world = removed
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )

        report = await status(world, environment="prod")

        assert of(report, SYNTHETIC_CASELIST).older_than is None
        assert of(report, SYNTHETIC_CASELIST).older_versions == ()

    async def test_an_incomplete_run_is_no_completion_and_a_later_completed_one_of_the_request_is(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """A request's stopped run touched the caselist; its re-run, which found nothing left to name
        it by, completed. The caselists are the request's, the time its completion."""
        world = removed
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )
        stopped = log_entry(
            request_id="RM-2026-02",
            recorded_at=COMPLETED - timedelta(days=3),
            outcome=RemovalOutcome.INCOMPLETE,
        )
        finished = log_entry(request_id="RM-2026-02", recorded_at=COMPLETED - timedelta(days=2))
        stopped_scope = scope_of(stopped, SYNTHETIC_CASELIST)

        alone = of(
            await status(world, removal_log=await log_in(tmp_path / "alone", [stopped], [stopped_scope])),
            SYNTHETIC_CASELIST,
        )
        both = of(
            await status(
                world,
                removal_log=await log_in(
                    tmp_path / "both", [stopped, finished], [stopped_scope, scope_of(finished)]
                ),
            ),
            SYNTHETIC_CASELIST,
        )

        assert alone.older_than is None
        assert both.older_than == RemovalCompletion(
            request_id="RM-2026-02", completed_at=COMPLETED - timedelta(days=2)
        )
        assert both.older_versions == ()  # the old index is from a day after that removal

    async def test_another_requests_scope_is_not_this_ones(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """A scope is joined to its own log entry: the same environment, request and moment."""
        world = removed
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )
        completed = log_entry(request_id="RM-2026-03", recorded_at=COMPLETED)
        elsewhere = RemovalScopeEntry(
            recorded_at=COMPLETED,
            request_id="RM-2026-04",
            environment="dev",
            caselists=(SYNTHETIC_CASELIST,),
            manifest_rewrites=(),
        )

        report = await status(world, removal_log=await log_in(tmp_path, [completed], [elsewhere]))

        assert report.removals_not_checked == ("RM-2026-03",)
        assert of(report, SYNTHETIC_CASELIST).older_versions == ()


# ------------------------------------------------------------------------------------------------
# The runbook's instruction: run the removal again, under the same request
# ------------------------------------------------------------------------------------------------


class TestClearingIt:
    async def test_the_same_request_run_again_clears_both_and_status_says_so(
        self, removed: RemovalWorld
    ) -> None:
        """A manifest version as it was before the removal, naming the file, and an old index.

        `caselist remove --source <a removed sha256>` under the same request, executed: the sweep
        downloads the manifest version and finds the row, and the plan deletes every aggregate.
        """
        world = removed
        old_rows = "".join(
            line + "\n" for line in [json.dumps({"kind": "member", "path": "x.docx", "sha256": REMOVED})]
        ).encode()
        put(world, REWRITTEN[0], old_rows, written=LONG_BEFORE)
        put(
            world,
            aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl"),
            b"old\n",
            written=LONG_BEFORE,
        )
        assert of(await status(world), SYNTHETIC_CASELIST).found

        await remove(world)

        cleared = await status(world)
        assert of(cleared, SYNTHETIC_CASELIST) == CaselistResidue(
            caselist=SYNTHETIC_CASELIST,
            checked=True,
            older_than=RemovalCompletion(request_id=REQUEST, completed_at=COMPLETED),
        )
        assert cleared.in_sync

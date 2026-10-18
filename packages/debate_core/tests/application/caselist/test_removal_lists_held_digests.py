"""Running a removal again lists an upload the import held, once its archive has left the inbox.

`v1-e30-t13` holds a path a whole-file removal takes a file from: the importer refuses a new upload
there, stores nothing of it, and counts it under the request. Running the same removal again put its
sha256 on the list only while the archive that brought it was still in the download inbox, where the
plan could read it. Once retention or the take-out removed the archive, nothing named the bytes, and
the same bytes arriving at another path were imported (`v1-e30-t13`'s Deviation 2).

The PM's ruling of 2026-10-16 reverses that deviation. The import writes each upload it holds to a
record beside the path holds, `held-digests.jsonl`: its sha256, the digest of the held path, and the
request holding the path. Digests and a request id, never a path or a name. Running the removal
again reads it, and lists each digest under its request by the rule a later upload has followed
since `v1-e30-t16`: held at no other path, the bytes are suppressed whole; held at another live path
too, they are withdrawn from the held path only.

The store and the removal are `v1-e30-t13`'s: `caselist remove --source <named-version>` holds
`(testcl26, REVISED_PATH)` for snapshots dated after `2026-09-08`, and the archives that arrive are
`tests/fixtures/caselist/build_held_path_archives.py`'s. Every archive here is imported from a
scratch directory and never put in the inbox, which is the state "it has left the inbox" leaves.

No test imports a name this task adds, so each runs against the start commit's source too, where
the ones about the record and the re-run fail on what that source does.

Every test runs offline: moto for the bucket, a temporary data directory, and a temporary `HOME`.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_held_path_archives import ARRIVING_BODIES, arriving_digest_of
from tests.fixtures.caselist.build_revised_path_archives import (
    CASELIST,
    ONE_WEEK_PATH,
    OTHER_TEAM_PATH,
    REVISED_PATH,
    digest_of,
)

from debate_core.application.caselist.import_service import CaselistImportService, Classification
from debate_core.application.caselist.removal_plan import RemovalPlan, SourceSelector
from debate_core.application.caselist.suppression import LocalFallbackSuppressionList, RecordedSuppressionList
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

from .conftest import REQUEST, RemovalWorld
from .test_held_rows_publish_nothing import import_archive, write_weekly
from .test_removal_covers_later_uploads import (
    NAMED,
    NAMES,
    held_at,
    local_blob,
    remove_the_named_file,
    revised_path_world,
)
from .test_removed_path_holds_later_imports import import_weekly, manifest_rows

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

UPLOADED_AFTER = arriving_digest_of("uploaded-after-the-removal")
UPLOADED_AFTER_AT_TWO_PATHS = arriving_digest_of("uploaded-after-at-two-paths")
HELD_PATH = disclosure_digest(CASELIST, REVISED_PATH)
WEEK_OF_THE_HELD_UPLOAD = date(2026, 10, 8)
WEEK_OF_THE_SHARED_UPLOAD = date(2026, 10, 10)
#: A week after the re-run, in which the held bytes arrive again at a path no removal holds.
WEEK_THEY_ARRIVE_AGAIN = date(2026, 10, 13)
TWO_PATHS_MANIFEST = f"manifests/{CASELIST}/2026-10-10.jsonl"

#: Where this task's record is kept, beside the path holds in each place (`v1-e30-t23`).
LOCAL_RECORD = Path("suppression") / "held-digests.jsonl"
BUCKET_RECORD = "manifests/_suppression/held-digests.jsonl"


@pytest.fixture(autouse=True)
def temporary_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `HOME` of this test's own, so nothing here can read or write the operator's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    built = await revised_path_world(tmp_path, s3_client, evidence_bucket)
    await remove_the_named_file(built)
    return built


def local_record(world: RemovalWorld) -> list[dict[str, object]]:
    """This machine's held-digest record, line by line; none where there is no file."""
    path = world.data_dir / LOCAL_RECORD
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def bucket_record(world: RemovalWorld) -> list[dict[str, object]]:
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=BUCKET_RECORD)
    if listed.get("KeyCount", 0) == 0:
        return []
    body = world.client.get_object(Bucket=world.bucket_name, Key=BUCKET_RECORD)["Body"].read()
    return [json.loads(line) for line in body.decode("utf-8").splitlines()]


def line_for(digest: str) -> dict[str, object]:
    """What the record holds for an upload refused at the held path, written out by hand."""
    return {"schema_version": 1, "sha256": digest, "disclosure": HELD_PATH, "request_id": REQUEST}


async def plan_again(world: RemovalWorld, request_id: str = REQUEST) -> RemovalPlan:
    """The dry run of the same removal: `caselist remove --source <named-version>`."""
    return await world.service().plan(
        SourceSelector(NAMED), request_id=request_id, reason=ReasonCode.REQUESTED_BY_TEAM
    )


async def run_again(world: RemovalWorld) -> RemovalPlan:
    """`caselist remove --source <named-version> --execute`, the same request, run again."""
    service = world.service()
    plan = await plan_again(world)
    assert (await service.execute(plan)).completed
    return plan


def entries_for(plan: RemovalPlan, digest: str) -> list[SuppressionEntry]:
    return [entry for entry in plan.suppression_entries if entry.sha256 == digest]


def held_bytes_at(path: str, digest: str, tmp_path: Path, week: date) -> Path:
    """A weekly archive holding the bytes of `digest` at `path`, and nothing else."""
    body = next(body for name, body in ARRIVING_BODIES.items() if arriving_digest_of(name) == digest)
    return write_weekly(tmp_path / "again" / f"{CASELIST}-weekly-{week.isoformat()}.zip", {path: body})


def classification_at(rows: Sequence[dict[str, object]], path: str) -> list[object]:
    return [row["classification"] for row in rows if row["path"] == path]


# ------------------------------------------------------------------------------------------------
# The import writes what it held
# ------------------------------------------------------------------------------------------------


async def test_the_import_records_the_upload_it_holds_by_digest_and_request(
    world: RemovalWorld, tmp_path: Path
) -> None:
    report = await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

    assert report.count(Classification.SUPPRESSED) == 1, "the precondition: the upload was held"
    assert local_record(world) == [line_for(UPLOADED_AFTER)]
    assert bucket_record(world) == [], "the import runs offline: the bucket's copy is the removal's"


async def test_the_record_names_no_path_school_team_or_file(world: RemovalWorld, tmp_path: Path) -> None:
    """Personal-data rule 6: digests and a request id only."""
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

    assert [sorted(line) for line in local_record(world)] == [
        ["disclosure", "request_id", "schema_version", "sha256"]
    ]
    text = (world.data_dir / LOCAL_RECORD).read_text(encoding="utf-8")
    for name in (*NAMES, *REVISED_PATH.split("/"), ".docx", ".zip"):
        assert name not in text


async def test_a_dry_run_import_records_nothing(world: RemovalWorld, tmp_path: Path) -> None:
    report = await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD, dry_run=True)

    assert report.count(Classification.SUPPRESSED) == 1
    assert local_record(world) == []


async def test_importing_the_same_archive_again_records_the_upload_once(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The record is idempotent: the same upload held again is the same line, appended once."""
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

    assert local_record(world) == [line_for(UPLOADED_AFTER)]


async def test_an_upload_at_a_path_no_removal_holds_is_not_recorded(
    world: RemovalWorld, tmp_path: Path
) -> None:
    archive = held_bytes_at(ONE_WEEK_PATH, UPLOADED_AFTER, tmp_path, WEEK_OF_THE_HELD_UPLOAD)

    report = await import_archive(world, archive, WEEK_OF_THE_HELD_UPLOAD)

    assert report.count(Classification.SUPPRESSED) == 0
    assert local_record(world) == []


class RefusesToRecordHeldDigests(RecordedSuppressionList):
    """This machine's list, but the held-digest record beside it cannot be written: a full disk."""

    async def append_held_digests(self, entries: object) -> None:
        raise OSError(28, "No space left on device")


async def test_an_import_whose_held_upload_cannot_be_recorded_fails(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Fail closed: an import that lost the only record of the bytes would let them back in later."""
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=RefusesToRecordHeldDigests(local_suppression_list_file(world.data_dir)),
    )

    with pytest.raises(OSError, match="No space left"):
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD, importer=importer)


# ------------------------------------------------------------------------------------------------
# Running the removal again lists it, after the archive has gone
# ------------------------------------------------------------------------------------------------


async def test_running_the_removal_again_lists_a_held_upload_whose_archive_has_left_the_inbox(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The point of the item: the archive is not in the inbox, and the store holds nothing of it."""
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
    assert not list((world.data_dir / "inbox").glob(f"{CASELIST}-weekly-2026-10-08*")), "not in the inbox"

    plan = await plan_again(world)

    planned = plan.source(UPLOADED_AFTER)
    assert planned is not None, "the re-run does not list the held upload"
    assert (planned.inclusion.value, planned.disposition.value) == ("held_at_import", "remove")
    (entry,) = entries_for(plan, UPLOADED_AFTER)
    assert (entry.disclosure, entry.request_id) == (None, REQUEST), "whole, under its request"


async def test_executing_it_puts_the_digest_on_the_list_in_both_copies_and_the_record_in_the_bucket(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

    await run_again(world)

    state = await world.suppression().entries()
    assert any(
        entry.sha256 == UPLOADED_AFTER and entry.disclosure is None and entry.request_id == REQUEST
        for entry in state
    )
    local = local_suppression_list_file(world.data_dir).path.read_text(encoding="utf-8")
    bucket = world.client.get_object(
        Bucket=world.bucket_name, Key="manifests/_suppression/suppression-list.jsonl"
    )["Body"].read()
    assert UPLOADED_AFTER in local and UPLOADED_AFTER.encode() in bucket
    assert bucket_record(world) == local_record(world) == [line_for(UPLOADED_AFTER)], "mirrored"


async def test_after_the_re_run_the_same_bytes_at_another_path_are_stopped_at_import(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
    await run_again(world)
    archive = held_bytes_at(ONE_WEEK_PATH, UPLOADED_AFTER, tmp_path, WEEK_THEY_ARRIVE_AGAIN)

    report = await import_archive(world, archive, WEEK_THEY_ARRIVE_AGAIN)

    assert report.count(Classification.SUPPRESSED) == 1, "the bytes came back in at another path"
    assert not local_blob(world, UPLOADED_AFTER).exists()


async def test_running_it_a_third_time_has_nothing_left_to_do_for_it(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
    await run_again(world)

    plan = await plan_again(world)

    assert plan.source(UPLOADED_AFTER) is None
    assert plan.nothing_to_do


async def test_a_removal_of_another_file_under_the_same_request_does_not_list_it(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The hold that refused it is on the named version: a `--source` of any other file holds nothing
    there, though one request may name several files."""
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

    plan = await world.service().plan(
        SourceSelector(digest_of("kept")), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )

    assert plan.source(UPLOADED_AFTER) is None


async def test_another_requests_removal_does_not_list_it(world: RemovalWorld, tmp_path: Path) -> None:
    """The digest is listed under the request holding the path, by that request's run alone."""
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

    plan = await plan_again(world, request_id="RM-2026-77")

    assert plan.source(UPLOADED_AFTER) is None


# ------------------------------------------------------------------------------------------------
# The holder rule: bytes another live path holds are withdrawn from the held path only
# ------------------------------------------------------------------------------------------------


async def shared_upload_imported(world: RemovalWorld, tmp_path: Path) -> None:
    """`2026-10-10` holds `uploaded-after-at-two-paths` at the held path and at another team's."""
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
    report = await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_SHARED_UPLOAD)
    rows = manifest_rows(world, TWO_PATHS_MANIFEST)
    assert held_at(rows, OTHER_TEAM_PATH) == {UPLOADED_AFTER_AT_TWO_PATHS}, "the precondition"
    assert held_at(rows, REVISED_PATH) == set(), "the precondition: the held path's copy was refused"
    assert report.count(Classification.SUPPRESSED) == 1


async def test_bytes_another_path_holds_are_withdrawn_from_the_held_path_only(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await shared_upload_imported(world, tmp_path)
    assert line_for(UPLOADED_AFTER_AT_TWO_PATHS) in local_record(world)

    plan = await plan_again(world)

    planned = plan.source(UPLOADED_AFTER_AT_TWO_PATHS)
    assert planned is not None, "the re-run does not list the held copy"
    assert (planned.inclusion.value, planned.disposition.value) == ("held_at_import", "withdraw")
    (entry,) = entries_for(plan, UPLOADED_AFTER_AT_TWO_PATHS)
    assert (entry.disclosure, entry.request_id) == (HELD_PATH, REQUEST), "the held path only"
    assert not planned.local_blob
    assert planned.kept_in == (CASELIST,)


async def test_bytes_another_path_holds_are_never_put_on_the_list_whole(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await shared_upload_imported(world, tmp_path)

    await run_again(world)

    whole = [
        entry
        for entry in await world.suppression().entries()
        if entry.sha256 == UPLOADED_AFTER_AT_TWO_PATHS and entry.disclosure is None
    ]
    assert whole == []
    assert held_at(manifest_rows(world, TWO_PATHS_MANIFEST), OTHER_TEAM_PATH) == {UPLOADED_AFTER_AT_TWO_PATHS}
    assert local_blob(world, UPLOADED_AFTER_AT_TWO_PATHS).exists(), "the other team's copy stays"
    withdrawals = (world.data_dir / "suppression" / "withdrawals.jsonl").read_text(encoding="utf-8")
    assert [
        (line["sha256"], line["disclosure"], line["caselist"])
        for line in map(json.loads, withdrawals.splitlines())
        if line["sha256"] == UPLOADED_AFTER_AT_TWO_PATHS
    ] == [(UPLOADED_AFTER_AT_TWO_PATHS, HELD_PATH, CASELIST)]


async def test_after_the_re_run_bytes_another_path_holds_still_import_at_a_path_nothing_holds(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await shared_upload_imported(world, tmp_path)
    await run_again(world)
    archive = held_bytes_at(ONE_WEEK_PATH, UPLOADED_AFTER_AT_TWO_PATHS, tmp_path, WEEK_THEY_ARRIVE_AGAIN)

    report = await import_archive(world, archive, WEEK_THEY_ARRIVE_AGAIN)

    assert report.count(Classification.SUPPRESSED) == 0
    rows = manifest_rows(world, f"manifests/{CASELIST}/2026-10-13.jsonl")
    assert classification_at(rows, ONE_WEEK_PATH) != [str(Classification.SUPPRESSED)]
    assert held_at(rows, ONE_WEEK_PATH) == {UPLOADED_AFTER_AT_TWO_PATHS}


# ------------------------------------------------------------------------------------------------
# The weekly pull records it too, on this machine alone
# ------------------------------------------------------------------------------------------------


async def test_a_pull_records_the_upload_it_held_on_this_machine_and_not_in_the_bucket(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """`test_held_path_inbox_copies.py`'s world: week four re-uploads the removed file at its path.

    The pull holds the everyday credential, which may not write under `manifests/_suppression/`. Its
    list is built as the composition root builds it (`ServiceContainer.caselist_sync`): every copy,
    falling back to this machine's without a login.
    """
    from .test_held_path_inbox_copies import (
        BAYVIEW_PATH,
        REUPLOADED_SHA256,
        WEEK_4,
        installation_of,
        remove_bayview,
        week_four,
    )
    from .test_inbox_retention import FakeSource
    from .test_pull_stage_failure_codes import pull

    await remove_bayview(removal_world)
    installation = dataclasses.replace(
        installation_of(removal_world, week_four(tmp_path / "published", another_teams_file=True)),
        suppression=LocalFallbackSuppressionList(
            removal_world.suppression(),
            local=RecordedSuppressionList(local_suppression_list_file(removal_world.data_dir)),
        ),
    )

    watched = await pull(installation, installation.sync(FakeSource(installation.archives, weeks=[WEEK_4])))

    assert watched.summary.succeeded
    assert local_record(removal_world) == [
        {
            "schema_version": 1,
            "sha256": REUPLOADED_SHA256,
            "disclosure": disclosure_digest("testcl26", BAYVIEW_PATH),
            "request_id": REQUEST,
        }
    ]
    assert bucket_record(removal_world) == []

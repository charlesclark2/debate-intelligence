"""`caselist status` reports an upload an import refused at a held path, until the re-run lists it.

`v1-e30-t23` records each upload the import refuses at a path a removal holds, in
`held-digests.jsonl` beside the path holds: the upload's sha256, the held path's digest and the
request holding the path. Running the same removal again reads it and lists the digest, whole or
withdrawn from the held path, whether or not the archive is still in the download inbox. Status read
only the inbox (`v1-e30-t21`): once the archive had gone, it said nothing, though the record held a
digest the re-run had not listed (t23's Follow-up 2).

Now status reads the record too, from both copies as the removal reads it (t23 Decision 3: the
import writes this machine's copy alone, and the removal the bucket's), and names each such digest's
request under `removals_owed` (`v1-e30-t24`, item 3). One the list already stops is not owed: the
re-run puts it there whole, or as the held path's disclosure. Nor is one whose hold an un-suppress
lifted, which the re-run does not list either. It is read when the inbox is, so `caselist pull`,
which asks for neither, reads nothing more.

The world is t23's: `RM-2026-01` removed the named version by `--source`, holding
`(testcl26, REVISED_PATH)` for snapshots after 2026-09-08, and the weekly of 2026-10-08 holds a new
upload at that path. It is imported from a scratch directory, the state "it has left the inbox"
leaves, unless a test puts it in the inbox.

The tests that say what `removals_owed` holds import no name this task adds, so they run against the
start commit's source too.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_held_path_archives import build_arriving_weekly_zips
from tests.fixtures.caselist.build_revised_path_archives import CASELIST, OTHER_CASELIST, REVISED_PATH

from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusReport, CaselistStatusService
from debate_core.application.ports.suppression import (
    HeldDigestEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
)

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_uploads import NAMED, NAMES, remove_the_named_file, revised_path_world
from .test_removal_lists_held_digests import (
    BUCKET_RECORD,
    HELD_PATH,
    LOCAL_RECORD,
    UPLOADED_AFTER,
    UPLOADED_AFTER_AT_TWO_PATHS,
    WEEK_OF_THE_HELD_UPLOAD,
    line_for,
    run_again,
    shared_upload_imported,
)
from .test_removed_path_holds_later_imports import import_weekly

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def temporary_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `HOME` of this test's own, so nothing here can read or write the operator's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """`RM-2026-01` has held the path; nothing has been imported there since."""
    built = await revised_path_world(tmp_path, s3_client, evidence_bucket)
    await remove_the_named_file(built)
    return built


def status_service(world: RemovalWorld) -> CaselistStatusService:
    """The comparison as `caselist status` builds it: both copies of the list, and the inbox."""
    return CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression(), inbox=world.inbox
    )


async def owed(world: RemovalWorld, caselist: str | None = None) -> CaselistStatusReport:
    """`caselist status`, asking what a removal's hold says is owed, as the command asks."""
    return await status_service(world).status(caselist, held_in_inbox=True)


def put_the_held_week_in_the_inbox(world: RemovalWorld, scratch: Path) -> Path:
    built = build_arriving_weekly_zips(scratch / "arriving")[(CASELIST, WEEK_OF_THE_HELD_UPLOAD)]
    waiting = world.data_dir / "inbox" / built.name
    shutil.copyfile(built, waiting)
    return waiting


class TestAHeldUploadTheReRunHasNotListed:
    async def test_once_its_archive_has_left_the_inbox_it_is_a_removal_owed(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        """The point of the item. The import refused the upload and recorded it; the archive is
        nowhere this machine looks, and the store holds nothing of it."""
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
        assert json.loads((world.data_dir / LOCAL_RECORD).read_text(encoding="utf-8")) == line_for(
            UPLOADED_AFTER
        ), "the precondition: the import recorded it"

        publisher = CaselistPublishService(
            local=world.local, remote=world.bucket, suppression=world.suppression()
        )
        assert (await publisher.execute(await publisher.plan(CASELIST))).succeeded

        report = await owed(world)

        assert report.held_in_inbox == (), "the precondition: nothing waits in the inbox"
        assert report.removals_owed == (REQUEST,)
        assert report.in_sync, "owed is said beside the verdict, as since v1-e30-t21"

    async def test_while_its_archive_waits_in_the_inbox_it_is_owed_as_well(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        archive = put_the_held_week_in_the_inbox(world, tmp_path)
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
        assert archive.exists()

        report = await owed(world)

        assert report.removals_owed == (REQUEST,)

    async def test_it_is_named_by_its_holds_caselist_its_digest_and_the_request(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        """With the archive in the inbox, the inbox names it as well: each says what it holds."""
        put_the_held_week_in_the_inbox(world, tmp_path)
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

        report = await owed(world)

        assert [(one.caselist, one.sha256, one.request_id) for one in report.refused_at_import] == [
            (CASELIST, UPLOADED_AFTER, REQUEST)
        ]
        assert [(one.caselist, one.sha256) for one in report.held_in_inbox] == [(CASELIST, UPLOADED_AFTER)]
        said = json.dumps([[one.caselist, one.sha256, one.request_id] for one in report.refused_at_import])
        assert not [word for word in (*NAMES, REVISED_PATH, ".zip", ".docx") if word in said], said

    async def test_a_line_only_the_buckets_copy_holds_is_read_too(self, world: RemovalWorld) -> None:
        """Status reads both copies as one, as the removal does: a removal from another machine gave
        the bucket's copy a line this machine's lacks."""
        line = HeldDigestEntry(sha256=UPLOADED_AFTER, disclosure=HELD_PATH, request_id=REQUEST)
        world.client.put_object(
            Bucket=world.bucket_name, Key=BUCKET_RECORD, Body=(line.to_line() + "\n").encode()
        )
        assert not (world.data_dir / LOCAL_RECORD).exists()

        report = await owed(world)

        assert report.removals_owed == (REQUEST,)


class TestWhatIsNotOwed:
    async def test_once_the_same_removal_run_again_lists_it_nothing_is_owed(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
        assert (await owed(world)).removals_owed == (REQUEST,)

        await run_again(world)

        report = await owed(world)
        assert report.removals_owed == ()
        assert report.refused_at_import == ()

    async def test_bytes_withdrawn_from_the_held_path_alone_are_not_owed_once_withdrawn(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        """`uploaded-after-at-two-paths` is also at another team's path, so the re-run withdraws it
        from the held path and puts it on the list as that path's disclosure, not whole."""
        await shared_upload_imported(world, tmp_path)
        before = await owed(world)
        assert UPLOADED_AFTER_AT_TWO_PATHS in [one.sha256 for one in before.refused_at_import]

        await run_again(world)

        assert (await owed(world)).removals_owed == ()

    async def test_one_whose_hold_an_unsuppress_lifted_is_not_owed(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        """`caselist unsuppress` of the named version lifts its hold, so an upload at the path is let in
        again, and the re-run lists nothing for it."""
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)
        await world.suppression().append(
            [
                SuppressionEntry(
                    action=SuppressionAction.UNSUPPRESS,
                    sha256=NAMED,
                    recorded_at=datetime(2026, 10, 12, 9, 0, tzinfo=UTC),
                    reason=ReasonCode.REMOVED_IN_ERROR,
                    request_id=REQUEST,
                )
            ]
        )

        assert (await owed(world)).removals_owed == ()

    async def test_a_comparison_of_another_caselist_does_not_report_it(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        """The hold, and so the upload, is `testcl26`'s."""
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

        assert (await owed(world, OTHER_CASELIST)).removals_owed == ()
        assert (await owed(world, CASELIST)).removals_owed == (REQUEST,)

    async def test_a_comparison_that_does_not_ask_reads_no_record(
        self, world: RemovalWorld, tmp_path: Path
    ) -> None:
        """`caselist pull` asks for the comparison alone, and its report stage reads no more than it
        did."""
        await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_UPLOAD)

        report = await status_service(world).status()

        assert report.removals_owed == ()

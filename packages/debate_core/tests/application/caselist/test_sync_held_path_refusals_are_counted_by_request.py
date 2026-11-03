"""A pull that met a removal's hold says how many uploads it refused, by request (`v1-e34-t23`, item 10).

`v1-e30-t13`'s importer refuses an upload at a path a removal holds, and its report counts the
refusals by the removal's request id (`ImportReport.held_by_request`), which `caselist import`
prints. A pull said nothing of them: the operator learned of a held upload only by running the
removal's dry run after a pull (`v1-e30-t13`'s Follow-up 2). Now the run's details carry the count
by request, and a notification says it, with the command that says whether the removal is owed
again. By request id and count only: never the path, which names a school and a team, and never
a new field on the run record, which every installed build would refuse.

The world is `test_held_path_inbox_copies.py`'s: the three synthetic weeks imported and published,
the Bayview semifinal negative removed with `caselist remove --source` (request `RM-2026-01`), and
week four arriving with the same file uploaded again at the held path and another team's new file.
Its import refuses exactly one upload, the re-upload, under `RM-2026-01`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.caselist_sync import SyncStage
from debate_core.application.sync_runs import SyncRunRecord
from debate_core.integrations.local.macos_notifier import MacOsNotifier

from .conftest import REQUEST, RemovalWorld
from .test_held_path_inbox_copies import (
    BAYVIEW_PATH,
    REUPLOADED_SHA256,
    WEEK_4,
    installation_of,
    remove_bayview,
    week_four,
)
from .test_inbox_retention import FakeSource
from .test_pull_stage_failure_codes import pull, stage

pytestmark = pytest.mark.anyio

WHERE = "Run 20260916T060000Z (dev)"
HELD_TITLE = "caselist pull: uploads held by a removal"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_the_details_and_the_notification_count_the_refused_upload_by_request(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_bayview(removal_world)
    archive = week_four(tmp_path / "published", another_teams_file=True)
    installation = installation_of(removal_world, archive)

    watched = await pull(installation, installation.sync(FakeSource(installation.archives, weeks=[WEEK_4])))

    summary = watched.summary
    assert summary.succeeded
    assert summary.as_json()["held_by_request"] == {REQUEST: 1}
    assert "; 1 upload(s) refused at a path a removal holds (RM-2026-01: 1)" in str(
        stage(summary, SyncStage.IMPORT)["reason"]
    )
    details = watched.pulled.details
    assert details is not None
    assert details.model_dump(mode="json")["held_by_request"] == {REQUEST: 1}
    [notification] = watched.notifier.sent
    assert notification.title == HELD_TITLE
    assert notification.message == (
        f"{WHERE}: the import refused 1 upload(s) at a path a removal holds, by request: RM-2026-01 1. "
        "Nothing of them was stored."
    )
    assert notification.fix_command == "debate-research caselist status"
    shown = " ".join(MacOsNotifier(executable="osascript").command_for(notification))
    for forbidden in (BAYVIEW_PATH, "Maple Grove", "Bayview", REUPLOADED_SHA256, str(tmp_path)):
        assert forbidden not in shown and forbidden not in notification.text


async def test_the_record_gains_no_field_for_it(removal_world: RemovalWorld, tmp_path: Path) -> None:
    """The count is in the details and the import stage's reason, which every build already reads."""
    await remove_bayview(removal_world)
    archive = week_four(tmp_path / "published", another_teams_file=True)
    installation = installation_of(removal_world, archive)

    watched = await pull(installation, installation.sync(FakeSource(installation.archives, weeks=[WEEK_4])))

    record = watched.pulled.record
    assert record is not None
    assert set(record.model_dump()) == set(SyncRunRecord.model_fields)
    assert "held_by_request" not in record.model_dump_json()


async def test_a_pull_that_met_no_hold_says_nothing_of_one(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    archive = week_four(tmp_path / "published", another_teams_file=True)
    installation = installation_of(removal_world, archive)

    watched = await pull(installation, installation.sync(FakeSource(installation.archives, weeks=[WEEK_4])))

    assert watched.summary.as_json()["held_by_request"] == {}
    assert watched.pulled.details is not None
    assert watched.pulled.details.model_dump(mode="json")["held_by_request"] == {}
    assert [one.title for one in watched.notifier.sent] == []

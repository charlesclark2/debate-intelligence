"""The run record's redaction keeps a snapshot name and a runbook, and still takes a path (`v1-e34-t23`).

`sync_runs.redact` removes anything path-shaped from every reason a record keeps, because a
disclosure's path is `School/TeamCode/School-TeamCode-Side-Tournament-Round.docx` and an `OSError`
quotes the file it failed on. It took two things that are neither with them:

* **A complete archive's snapshot name**, `full/<date>` (`v1-e30-t18`'s Follow-up 4, item 14). Every
  import stage's reason that counted a complete archive's withdrawals read `complete archive
  testcl26 [redacted] 0 withdrawn`, the colon taken too.
* **The runbook a refusal points at** (`v1-e34-t19`'s Follow-up 9, item 7). A refused publish's
  reason read "[redacted] lists what each profile is granted": the sentence `v1-e29-t07` put into
  the refusal names `docs/runbooks/evidence-store.md`.

Both are kept now, whole, and nothing else that has a `/` in it is: a path on the operator's
machine, absolute or under the home directory, quoted or not, and a disclosure's path, which is
relative and is not a runbook. Every expected string is written out by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist_sync import RunSummary, StageOutcome, StageRecord, SyncStage
from debate_core.application.sync_runs import REDACTED, record_for_summary, redact
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .run_record_scenarios import World, a_publish_the_bucket_refused_with_the_adapters_fix
from .test_inbox_retention import Installation

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STARTED = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)

THE_HOME_DIRECTORY_PATH = "/Users/someone/.debate-research/dev/inbox/testcl26-weekly-2026-09-01.zip"
UNDER_HOME = "~/.debate-research/dev/caselist-sync-pending.json"
A_DISCLOSURE_PATH = "Maple Grove/QX/MapleGrove-QX-Aff-Harbor-Round1.docx"
A_DISCLOSURE_PATH_WITHOUT_SPACES = "MapleGrove/QX/MapleGrove-QX-Aff-Harbor-Round1.docx"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        pytest.param(
            "complete archive testcl26 full/2026-09-15: 2 withdrawn, 0 superseded against 3 earlier",
            "complete archive testcl26 full/2026-09-15: 2 withdrawn, 0 superseded against 3 earlier",
            id="a complete archive's snapshot name, colon and all",
        ),
        pytest.param(
            "1 snapshot(s) left for a later run: testcl26 full/2026-09-15, testcl26 2026-09-08",
            "1 snapshot(s) left for a later run: testcl26 full/2026-09-15, testcl26 2026-09-08",
            id="a snapshot name followed by a comma",
        ),
        pytest.param(
            "the AWS profile lacks a grant for this. docs/runbooks/evidence-store.md lists what each "
            "profile is granted.",
            "the AWS profile lacks a grant for this. docs/runbooks/evidence-store.md lists what each "
            "profile is granted.",
            id="the runbook a refusal points at",
        ),
        pytest.param(
            "see (docs/runbooks/caselist-scheduled-sync.md).",
            "see (docs/runbooks/caselist-scheduled-sync.md).",
            id="a runbook in brackets",
        ),
    ],
)
def test_a_snapshot_name_and_a_runbook_survive_the_redaction(message: str, expected: str) -> None:
    assert redact(message) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        pytest.param(
            f"could not open {THE_HOME_DIRECTORY_PATH}: no such file",
            f"could not open {REDACTED} no such file",
            id="an absolute path on this machine",
        ),
        pytest.param(
            f"the pending-work file {UNDER_HOME} could not be read",
            f"the pending-work file {REDACTED} could not be read",
            id="a path under the home directory",
        ),
        pytest.param(
            f"refused '{A_DISCLOSURE_PATH}' as an upload",
            f"refused {REDACTED} as an upload",
            id="a quoted disclosure path with spaces",
        ),
        pytest.param(
            f"refused {A_DISCLOSURE_PATH_WITHOUT_SPACES} as an upload",
            f"refused {REDACTED} as an upload",
            id="a disclosure path",
        ),
        pytest.param(
            "could not open /Users/someone/docs/runbooks/evidence-store.md",
            f"could not open {REDACTED}",
            id="a runbook's name inside a path on this machine",
        ),
        pytest.param(
            "could not open /Users/someone/archives/full/2026-09-15",
            f"could not open {REDACTED}",
            id="a snapshot's name inside a path on this machine",
        ),
        pytest.param(
            "refused docs/../../Users/someone/notes.md",
            f"refused {REDACTED}",
            id="a path that only starts like the runbooks",
        ),
        pytest.param(
            "refused full/2026-09-15/School/Team-Aff.docx",
            f"refused {REDACTED}",
            id="a path that only starts like a snapshot",
        ),
        pytest.param(
            "refused docs/runbooks/evidence-store.md.docx",
            f"refused {REDACTED}",
            id="a file named like a runbook",
        ),
    ],
)
def test_a_path_on_the_operators_machine_or_a_disclosure_is_still_redacted(
    message: str, expected: str
) -> None:
    assert redact(message) == expected


def test_the_record_keeps_a_complete_archives_name_in_the_import_stage_and_takes_the_path_beside_it() -> None:
    """Through the record itself: the import stage's reason as a pull writes it, with a path
    an error might have quoted in the same sentence."""
    summary = RunSummary(
        run_id="20260916T060000Z",
        started_at=STARTED,
        finished_at=STARTED,
        dry_run=False,
        caselists=("testcl26",),
        stages=(
            StageRecord(
                stage=SyncStage.IMPORT,
                outcome=StageOutcome.FAILED,
                reason=(
                    "1 imported; complete archive testcl26 full/2026-09-15: 2 withdrawn, 0 superseded "
                    f"against 3 earlier snapshot(s); 1 refused: {THE_HOME_DIRECTORY_PATH} is not a zip"
                ),
            ),
        ),
    )

    record = record_for_summary(summary, environment="dev", mode="run")

    [entry] = record.stages
    assert entry.reason == (
        "1 imported; complete archive testcl26 full/2026-09-15: 2 withdrawn, 0 superseded against 3 "
        f"earlier snapshot(s); 1 refused: {REDACTED} is not a zip"
    )


async def test_a_refused_publish_keeps_the_runbook_its_reason_points_at(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 7 as the operator met it: the bucket refuses a profile that lacks a grant, the adapter's
    refusal says which runbook lists the grants, and the record now says so too."""

    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    world = World(
        installation=Installation(
            data_dir=tmp_path / "evidence",
            bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            archives=build_snapshot_zips(tmp_path / "published"),
        ),
        s3_client=s3_client,
        bucket_name=evidence_bucket,
        scratch=tmp_path,
        set_clock=set_clock,
    )

    await a_publish_the_bucket_refused_with_the_adapters_fix(world)

    [pulled] = world.pulled
    assert pulled.record is not None
    [publish] = [one for one in pulled.record.stages if one.stage == "publish"]
    assert publish.reason is not None
    assert "docs/runbooks/evidence-store.md lists what each profile is granted" in publish.reason
    assert f"{REDACTED} lists what each profile is granted" not in publish.reason
    assert str(tmp_path) not in pulled.record.model_dump_json()

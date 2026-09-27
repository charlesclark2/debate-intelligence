"""`debate-research caselist runs`, and the run log `caselist pull` leaves behind (ac4, ac5, ac6).

Through Typer's `CliRunner` against the real application and composition root, in a `test`
environment of each test's own: no bucket, the null notifier (the `test` profile says `none`), and
OpenCaselist answered by respx. Nothing reaches the network or the notification centre.

The archives are the invented ones from `tests/fixtures/caselist/`. The fixture has three weeklies,
so a fresh installation wants three; every count below is that, split by hand.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import respx
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist_sync import DOWNLOAD_LEDGER_FILENAME, DownloadLedger
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    SyncRunLog,
    SyncRunOutcome,
    SyncRunRecord,
)

API = "https://api.opencaselist.example.invalid/v1"
FILE_HOST = "https://files.opencaselist.example.invalid"

runner = CliRunner()


def weekly_name(day: date) -> str:
    return f"{SYNTHETIC_CASELIST}-weekly-{day.isoformat()}.zip"


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A `test` environment: the API on, a fixture token in the environment, no bucket."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    data = tmp_path / "data"
    for name, value in {
        "DEBATE_ENV": "test",
        "DEBATE_STORAGE__DATA_DIR": str(data),
        "DEBATE_ALLOW_NETWORK": "true",
        "DEBATE_CASELIST__API_ENABLED": "true",
        "DEBATE_CASELIST__API_BASE_URL": API,
        "DEBATE_CASELIST__MIN_REQUEST_INTERVAL_SECONDS": "0.5",
        "DEBATE_PROVIDERS__CASELIST_TOKEN": f"fixture-token-{secrets.token_hex(8)}",
    }.items():
        monkeypatch.setenv(name, value)
    yield data


@pytest.fixture
def site(tmp_path: Path) -> Iterator[respx.MockRouter]:
    """OpenCaselist: the fixture's three weekly archives and no OpenEv files."""
    archives = build_snapshot_zips(tmp_path / "published")
    listing = [
        {"name": weekly_name(snapshot.snapshot), "url": f"{FILE_HOST}/{weekly_name(snapshot.snapshot)}"}
        for snapshot in SNAPSHOTS
    ]
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/caselists/{SYNTHETIC_CASELIST}/downloads").respond(200, json=listing)
        router.get(f"{API}/openev").respond(200, json=[])
        for snapshot in SNAPSHOTS:
            router.get(f"{FILE_HOST}/{weekly_name(snapshot.snapshot)}").respond(
                200, content=archives[snapshot.snapshot].read_bytes()
            )
        yield router


def invoke(*arguments: str) -> Result:
    # Wide enough that Rich does not wrap a column heading across two lines.
    return runner.invoke(create_app(), list(arguments), env={"COLUMNS": "200"})


def as_json(*arguments: str) -> dict[str, Any]:
    result = invoke("--json", *arguments)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}"
    envelope: dict[str, Any] = json.loads(lines[0])
    envelope["exit_code"] = result.exit_code
    return envelope


def spend_todays_allowance(data_dir: Path, downloads: int) -> None:
    DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME).record(
        datetime.now(UTC).astimezone().date(), downloads
    )


def a_record(started: datetime, *, downloaded: int = 2, deferred: int = 0) -> SyncRunRecord:
    return SyncRunRecord(
        run_id=started.strftime("%Y%m%dT%H%M%SZ"),
        environment="test",
        mode="run",
        started_at=started,
        finished_at=started + timedelta(seconds=30),
        outcome=SyncRunOutcome.CAP_DEFERRED if deferred else SyncRunOutcome.COMPLETED,
        caselists=(SYNTHETIC_CASELIST,),
        archives_wanted=downloaded + deferred,
        archives_downloaded=downloaded,
        archives_deferred=deferred,
        deferred_by_caselist={SYNTHETIC_CASELIST: deferred},
        pending_publish=(),
    )


# ------------------------------------------------------------------------------------------------
# `caselist runs --last 5` (ac4)
# ------------------------------------------------------------------------------------------------


def test_runs_last_5_shows_the_five_newest_with_every_column(installation: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    log = SyncRunLog(installation / SYNC_RUN_LOG_FILENAME)
    for days_ago in range(7, 0, -1):
        log.append(a_record(now - timedelta(days=days_ago), downloaded=1, deferred=days_ago % 2))

    envelope = as_json("caselist", "runs", "--last", "5")

    assert envelope["exit_code"] == ExitCode.OK
    runs = envelope["data"]["runs"]
    assert len(runs) == 5
    assert runs[0]["run_id"] == (now - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ"), "newest first"
    assert [one["archives_deferred"] for one in runs] == [1, 0, 1, 0, 1]
    assert envelope["data"]["days_since_last_run"] == 1
    assert envelope["data"]["overdue"] is False

    table = " ".join(invoke("caselist", "runs", "--last", "5").stdout.split())
    for heading in ("Run id", "Started (UTC)", "Outcome", "Downloaded", "Deferred by cap", "Pending publish"):
        assert heading in table
    assert "cap_deferred" in table
    assert "1 of 2" in table, "a deferred run shows downloaded against wanted"


def test_runs_with_nothing_recorded_says_so_and_is_overdue(installation: Path) -> None:
    envelope = as_json("caselist", "runs")

    assert envelope["data"]["runs"] == []
    assert envelope["data"]["overdue"] is True
    assert "No caselist pull has been recorded" in invoke("caselist", "runs").stdout


def test_runs_calls_out_a_schedule_that_has_stopped(installation: Path) -> None:
    """The run that did not happen: no failure, no record — only a newest record that is old."""
    SyncRunLog(installation / SYNC_RUN_LOG_FILENAME).append(a_record(datetime.now(UTC) - timedelta(days=12)))

    envelope = as_json("caselist", "runs")

    assert envelope["data"]["overdue"] is True
    assert "the schedule may have stopped" in " ".join(invoke("caselist", "runs").stdout.split())


def test_runs_remote_without_a_bucket_is_a_clear_refusal(installation: Path) -> None:
    envelope = as_json("caselist", "runs", "--remote")

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert "no evidence bucket" in envelope["error"]["message"]


# ------------------------------------------------------------------------------------------------
# What `caselist pull` leaves in the log (ac1, ac5, ac6)
# ------------------------------------------------------------------------------------------------


def test_a_pull_leaves_one_record_that_runs_then_shows(installation: Path, site: respx.MockRouter) -> None:
    pulled = as_json("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)

    assert pulled["data"]["run_record"]["outcome"] == "completed"
    [record] = SyncRunLog(installation / SYNC_RUN_LOG_FILENAME).read()
    assert record.run_id == pulled["data"]["run_id"]
    assert [one["run_id"] for one in as_json("caselist", "runs")["data"]["runs"]] == [record.run_id]


def test_a_dry_run_leaves_no_record(installation: Path, site: respx.MockRouter) -> None:
    as_json("caselist", "pull", "--caselist", SYNTHETIC_CASELIST, "--dry-run")

    assert not (installation / SYNC_RUN_LOG_FILENAME).exists()


def test_a_cap_blocked_pull_is_not_captioned_nothing_new(installation: Path, site: respx.MockRouter) -> None:
    """The second dev run of 2026-09-24, through the command: 3 wanted, 0 allowed, 3 deferred."""
    spend_todays_allowance(installation, 5)

    result = invoke("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)

    assert result.exit_code == ExitCode.OK, "the cap is a delay, not a failure"
    rendered = " ".join(result.stdout.split())
    assert "Nothing new" not in rendered
    assert "Nothing fetched: 3 archive(s) wanted and all 3 deferred by the daily download cap" in rendered
    [record] = SyncRunLog(installation / SYNC_RUN_LOG_FILENAME).read()
    assert (record.outcome, record.archives_wanted, record.archives_deferred) == (
        SyncRunOutcome.CAP_DEFERRED,
        3,
        3,
    )


def test_a_truncated_pull_states_wanted_and_deferred_and_the_next_run_carries_the_backlog(
    installation: Path, site: respx.MockRouter
) -> None:
    """The first dev run in miniature: 2 of 3 fetched and 1 deferred; the next run carries the 1."""
    spend_todays_allowance(installation, 3)

    first = " ".join(invoke("caselist", "pull", "--caselist", SYNTHETIC_CASELIST).stdout.split())

    assert "2 of 3 wanted archive(s)" in first
    assert "1 archive(s) deferred by the daily download cap wait for a later run" in first
    assert "1 to fetch" not in first

    second = as_json("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)

    assert second["data"]["run_record"]["backlog_carried"] == 1
    assert second["data"]["run_record"]["archives_deferred"] == 1, "today's allowance is still spent"


def test_redact_an_expired_token_run_record_carries_neither_the_token_nor_a_path(
    installation: Path, site: respx.MockRouter
) -> None:
    """ac2 and ac4 through the command: a 401 is recorded as CaselistAuthExpired, token-free."""
    site.get(f"{API}/caselists/{SYNTHETIC_CASELIST}/downloads").respond(401)
    token = os.environ["DEBATE_PROVIDERS__CASELIST_TOKEN"]

    envelope = as_json("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    [record] = SyncRunLog(installation / SYNC_RUN_LOG_FILENAME).read()
    assert record.error_class == "CaselistAuthExpired"
    assert "caselist auth login" in (record.error_message or "")
    log_text = (installation / SYNC_RUN_LOG_FILENAME).read_text(encoding="utf-8")
    assert token not in log_text
    assert token not in json.dumps(as_json("caselist", "runs"))

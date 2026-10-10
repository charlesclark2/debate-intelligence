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
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist_sync import DOWNLOAD_LEDGER_FILENAME, DownloadLedger
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    SyncRunLog,
    SyncRunOutcome,
    SyncRunRecord,
)
from debate_core.testing.fakes import FixedClock

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


OPERATOR_EVENING = datetime(2026, 9, 29, 4, 45, 11, tzinfo=UTC)
"""23:45:11 CDT on 2026-09-28, when the operator's evening runs spent their five."""


@pytest.fixture
def forty_minutes_later(monkeypatch: pytest.MonkeyPatch) -> FixedClock:
    """The command's clock, pinned forty minutes after `OPERATOR_EVENING`: past local midnight.

    Pinned through the container's one clock, so the run and the window it counts against are
    read from the same place, and nothing depends on when or where the suite runs (v1-e34-t06
    ac2b). Each read advances a second, so two runs get two run ids.
    """
    clock = FixedClock(OPERATOR_EVENING + timedelta(minutes=40), step=timedelta(seconds=1))
    monkeypatch.setattr(ServiceContainer, "clock", lambda self: clock.now)
    return clock


def spend_allowance(data_dir: Path, downloads: int, *, at: datetime) -> None:
    """Record `downloads` bulk downloads started at `at`, as an earlier run would have."""
    ledger = DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME)
    for _ in range(downloads):
        ledger.record(at)


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


STORED_RUN_LOG = (
    Path(__file__).resolve().parents[3]
    / "debate_core/tests/application/caselist/stored_run_records/run_log_written_by_a_schema_3_build.jsonl"
)
"""One run-log line as a build before `v1-e34-t13` wrote it, kept as written: a pull against the
synthetic caselist whose download of week three failed on a burst rate limit. The installed weekly
agent runs such a build, in the data directory a newer build reads, until it is reinstalled."""


def test_runs_still_reads_the_run_log_a_schema_3_build_wrote(installation: Path) -> None:
    """`v1-e34-t13` moved the run *summary* to schema 4 and left the run log's record alone, so the
    log the installed agent writes reads as it did. Every expected value is read off the stored
    line by hand: 2 of 3 wanted weeks downloaded, none deferred, the download stage failed."""
    installation.mkdir(parents=True)
    (installation / SYNC_RUN_LOG_FILENAME).write_bytes(STORED_RUN_LOG.read_bytes())

    envelope = as_json("caselist", "runs", "--last", "5")

    assert envelope["exit_code"] == ExitCode.OK, envelope
    [run] = envelope["data"]["runs"]
    assert (run["run_id"], run["outcome"], run["environment"]) == ("20260916T060000Z", "failed", "dev")
    assert (run["archives_wanted"], run["archives_downloaded"], run["archives_deferred"]) == (3, 2, 0)
    assert [(one["stage"], one["outcome"]) for one in run["stages"]][:3] == [
        ("select", "completed"),
        ("download", "failed"),
        ("import", "completed"),
    ]
    assert all(sorted(one) == ["outcome", "reason", "stage"] for one in run["stages"])

    table = " ".join(invoke("caselist", "runs", "--last", "5").stdout.split())
    # Nothing was deferred by the cap, so the table shows the downloads as a plain count.
    assert "20260916T060000Z │ 2026-09-16 06:00 │ failed │ 2 │ 0 │ 0" in table


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


def test_a_cap_blocked_pull_is_not_captioned_nothing_new(
    installation: Path, site: respx.MockRouter, forty_minutes_later: FixedClock
) -> None:
    """The second dev run of 2026-09-24, through the command: 3 wanted, 0 allowed, 3 deferred.

    The five were spent forty minutes earlier, on the other side of midnight: a new date, and the
    same 24 hours.
    """
    spend_allowance(installation, 5, at=OPERATOR_EVENING)

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
    installation: Path, site: respx.MockRouter, forty_minutes_later: FixedClock
) -> None:
    """The first dev run in miniature: 2 of 3 fetched and 1 deferred; the next run carries the 1."""
    spend_allowance(installation, 3, at=OPERATOR_EVENING)

    first = " ".join(invoke("caselist", "pull", "--caselist", SYNTHETIC_CASELIST).stdout.split())

    assert "2 of 3 wanted archive(s)" in first
    assert "1 archive(s) deferred by the daily download cap wait for a later run" in first
    assert "1 to fetch" not in first

    second = as_json("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)

    assert second["data"]["run_record"]["backlog_carried"] == 1
    assert second["data"]["run_record"]["archives_deferred"] == 1, "the 24 hours' allowance is still spent"
    assert second["data"]["bulk_downloads_spent_in_window"] == 5
    window_start = datetime.fromisoformat(second["data"]["bulk_download_window_start"])
    pinned = OPERATOR_EVENING + timedelta(minutes=40) - timedelta(hours=24)
    assert pinned <= window_start < pinned + timedelta(minutes=1), "counted on the pinned clock"


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

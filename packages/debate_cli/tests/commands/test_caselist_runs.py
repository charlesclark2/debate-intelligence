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
    StageEntry,
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
        # The parse stage is on, as it is for the agent (`v1-e34-t17`). One worker, so that a pull
        # here starts one process and not the machine's cores less one.
        "DEBATE_PARSE__WORKERS": "1",
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
    assert run["details"] is None, "a build before v1-e34-t19 wrote nothing beside its record"

    table = " ".join(invoke("caselist", "runs", "--last", "5").stdout.split())
    # Nothing was deferred by the cap, so the table shows the downloads as a plain count. The parse
    # stage's column says the run has no counts on record, which is not the same as none parsed.
    # Since `v1-e34-t23` the codes and the verdict follow the outcome; an older build kept neither.
    assert (
        "20260916T060000Z │ 2026-09-16 06:00 │ failed │ not recorded │ not recorded │ 2 │ 0 │ 0 │ "
        "not recorded" in table
    )


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


def test_runs_shows_what_the_newest_runs_parse_stage_did(installation: Path, site: respx.MockRouter) -> None:
    """`v1-e34-t17` ac5's reading: the stage's counts, in `caselist runs --last 1`.

    By hand from the fixture: one caselist, whose three weeklies hold fourteen distinct bodies, of
    which one is a PDF and one a legacy `.doc`; plain paragraphs, so no cards; nothing parsed
    before, so a full parse; and no bucket in `test`, so the sentence says nothing of one.
    """
    assert invoke("--json", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST).exit_code == ExitCode.OK

    shown = " ".join(invoke("caselist", "runs", "--last", "1").stdout.split())

    assert (
        "Parse stage of the newest run" in shown
        and "completed. 1 caselist(s) parsed: 14 source(s) attempted, 0 skipped as parsed already, "
        "2 unsupported, 0 failed, 0 card(s); 1 of them parsed in full, into a version directory that "
        "held nothing."
        in shown
    ), shown
    [record] = as_json("caselist", "runs", "--last", "1")["data"]["runs"]
    assert {one["stage"]: one["outcome"] for one in record["stages"]}["parse"] == "completed"

    # The next run imports nothing, so its parse stage is skipped and the caption is silent on it.
    # (The table has a "Parse stage" column since `v1-e34-t19`; it is the caption's sentence that
    # is absent.)
    assert invoke("--json", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST).exit_code == ExitCode.OK
    assert "Parse stage of the newest run" not in " ".join(
        invoke("caselist", "runs", "--last", "1").stdout.split()
    )


# ------------------------------------------------------------------------------------------------
# The parse stage's counts, in the table (`v1-e34-t19` ac9)
# ------------------------------------------------------------------------------------------------

DETAILS_FILE = "caselist-sync-run-details.jsonl"
"""The file beside the run log that holds what the record cannot, by its name in the runbook."""


def test_runs_shows_the_nine_parse_counts_kept_beside_a_record_each_under_its_own_name(
    installation: Path,
) -> None:
    """A record, and beside it details written here by hand, with nine different numbers so that no
    two counts can change places unnoticed. All nine are in the run's row, each named."""
    started = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    record = a_record(started)
    SyncRunLog(installation / SYNC_RUN_LOG_FILENAME).append(record)
    (installation / DETAILS_FILE).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": record.run_id,
                "stages": [],
                "failure_codes": [],
                "hint": None,
                "parse": {
                    "caselists": 3,
                    "full_parses": 1,
                    "attempted": 120,
                    "skipped": 45,
                    "unsupported": 7,
                    "failed": 2,
                    "cards": 310,
                    "uploaded": 58,
                    "not_published": 4,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    table = " ".join(invoke("caselist", "runs").stdout.split())

    assert "Parse stage" in table
    assert f"{record.run_id} │" in table
    for counts in (
        "3 caselist(s), 1 in full",
        "120 attempted, 45 skipped, 7 unsupported, 2 failed",
        "310 card(s)",
        "58 uploaded, 4 caselist(s) not published",
    ):
        assert counts in table, table
    [run] = as_json("caselist", "runs")["data"]["runs"]
    assert run["run_id"] == record.run_id, "the record's own fields are where they always were"
    assert run["details"]["parse"]["cards"] == 310


def test_runs_shows_what_a_real_pulls_parse_stage_counted_and_that_the_next_one_did_not_run(
    installation: Path, site: respx.MockRouter
) -> None:
    """Through the command, both ways. The counts are the ones the caption test above derives by
    hand from the fixture: one caselist parsed in full, fourteen bodies of which a PDF and a legacy
    `.doc` are unsupported, no cards, and no bucket in `test` so nothing uploaded. The second pull
    imports nothing, so its parse stage did not run, and its row says that and not a row of zeros."""
    first = as_json("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)
    assert first["exit_code"] == ExitCode.OK, first
    by_hand = {
        "caselists": 1,
        "full_parses": 1,
        "attempted": 14,
        "skipped": 0,
        "unsupported": 2,
        "failed": 0,
        "cards": 0,
        "uploaded": 0,
        "not_published": 0,
    }
    assert first["data"]["run_details"]["parse"] == by_hand

    [run] = as_json("caselist", "runs", "--last", "1")["data"]["runs"]
    assert run["details"]["parse"] == by_hand
    table = " ".join(invoke("caselist", "runs", "--last", "1").stdout.split())
    for counts in (
        "1 caselist(s), 1 in full",
        "14 attempted, 0 skipped, 2 unsupported, 0 failed",
        "0 card(s)",
        "0 uploaded, 0 caselist(s) not published",
    ):
        assert counts in table, table

    assert as_json("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)["exit_code"] == ExitCode.OK
    newest, older = as_json("caselist", "runs")["data"]["runs"]
    assert newest["details"]["parse"] is None
    assert older["details"]["parse"] == by_hand
    rows = " ".join(invoke("caselist", "runs").stdout.split())
    assert f"{newest['run_id']} │" in rows and "│ did not run" in rows


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


# ------------------------------------------------------------------------------------------------
# `v1-e34-t23`, item 3: each run's codes and verdict, from its details
# ------------------------------------------------------------------------------------------------


def a_failed_record(started: datetime) -> SyncRunRecord:
    return a_record(started).model_copy(update={"outcome": SyncRunOutcome.FAILED})


def details_line(run_id: str, *failure_codes: str) -> str:
    """A run's details as this build writes them, by hand: the codes its exit was decided from."""
    return json.dumps(
        {
            "schema_version": 1,
            "run_id": run_id,
            "stages": [],
            "failure_codes": list(failure_codes),
            "hint": None,
            "parse": None,
        }
    )


def test_runs_shows_each_runs_codes_and_verdict_from_its_details(installation: Path) -> None:
    """Four runs, newest first: one that failed only on what a retry may cure, one that met a verdict
    among such failures, one that did not fail, and one an older build recorded with no details.
    The verdict is the command's own rule for exit `3` (retry) against every other failure (person),
    the rule the notification asks too."""
    day = datetime.now(UTC).replace(microsecond=0) - timedelta(days=4)
    retried, looked_at, fine, older = (
        a_failed_record(day + timedelta(days=3)),
        a_failed_record(day + timedelta(days=2)),
        a_record(day + timedelta(days=1)),
        a_failed_record(day),
    )
    log = SyncRunLog(installation / SYNC_RUN_LOG_FILENAME)
    for record in (older, fine, looked_at, retried):
        log.append(record)
    (installation / DETAILS_FILE).write_text(
        "\n".join(
            (
                details_line(fine.run_id),
                details_line(looked_at.run_id, "UNREADABLE_ARCHIVE", "STORE_UNAVAILABLE"),
                details_line(retried.run_id, "STORE_UNAVAILABLE"),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    table = " ".join(invoke("caselist", "runs").stdout.split())

    for heading in ("Failed on", "Verdict"):
        assert heading in table
    assert (
        f"{retried.run_id} │ {retried.started_at:%Y-%m-%d %H:%M} │ failed │ STORE_UNAVAILABLE │ retry │"
        in table
    )
    assert (
        f"{looked_at.run_id} │ {looked_at.started_at:%Y-%m-%d %H:%M} │ failed │ UNREADABLE_ARCHIVE, "
        "STORE_UNAVAILABLE │ person │"
    ) in table
    assert f"{fine.run_id} │ {fine.started_at:%Y-%m-%d %H:%M} │ completed │ none │ none │" in table
    assert (
        f"{older.run_id} │ {older.started_at:%Y-%m-%d %H:%M} │ failed │ not recorded │ not recorded │"
        in table
    )

    runs = as_json("caselist", "runs")["data"]["runs"]
    assert [(one["run_id"], one["verdict"]) for one in runs] == [
        (retried.run_id, "retry"),
        (looked_at.run_id, "person"),
        (fine.run_id, None),
        (older.run_id, None),
    ]
    assert [one["details"]["failure_codes"] if one["details"] else None for one in runs] == [
        ["STORE_UNAVAILABLE"],
        ["UNREADABLE_ARCHIVE", "STORE_UNAVAILABLE"],
        [],
        None,
    ]


def test_runs_shows_the_banners_own_words_beside_the_verdict(installation: Path) -> None:
    """`v1-e34-t26`, item 3. Five runs, newest first: one the lock refused, a publish refused with a
    fix, a run stopped by a refusal with a fix, a retry with no fix, and an older build's lock refusal
    with no details. The first three banners had words of their own beside the verdict, and the table
    and `--json` now say them: `skipped` and `retry once fixed`. A retry with no fix has none, and a
    run with no details has none known."""
    day = datetime.now(UTC).replace(microsecond=0) - timedelta(days=5)
    locked = a_failed_record(day + timedelta(days=4)).model_copy(update={"error_class": "SyncRunInProgress"})
    refused = a_failed_record(day + timedelta(days=3)).model_copy(
        update={"stages": (StageEntry(stage="publish", outcome="failed"),)}
    )
    stopped = a_failed_record(day + timedelta(days=2)).model_copy(update={"error_class": "StoreAccessDenied"})
    retried = a_failed_record(day + timedelta(days=1)).model_copy(
        update={"stages": (StageEntry(stage="publish", outcome="failed"),)}
    )
    older = a_failed_record(day).model_copy(update={"error_class": "SyncRunInProgress"})
    log = SyncRunLog(installation / SYNC_RUN_LOG_FILENAME)
    for record in (older, retried, stopped, refused, locked):
        log.append(record)
    grant = "the AWS profile lacks a grant for this; docs/runbooks/evidence-store.md lists what each has"
    (installation / DETAILS_FILE).write_text(
        "\n".join(
            (
                details_line(locked.run_id, "SYNC_RUN_IN_PROGRESS"),
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": refused.run_id,
                        "stages": [{"stage": "publish", "error_codes": ["STORE_ACCESS_DENIED"], "hint": grant}],
                        "failure_codes": ["STORE_ACCESS_DENIED"],
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": stopped.run_id,
                        "failure_codes": ["STORE_ACCESS_DENIED"],
                        "hint": grant,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": retried.run_id,
                        "stages": [{"stage": "publish", "error_codes": ["STORE_UNAVAILABLE"]}],
                        "failure_codes": ["STORE_UNAVAILABLE"],
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    table = " ".join(invoke("caselist", "runs").stdout.split())

    assert (
        f"{locked.run_id} │ {locked.started_at:%Y-%m-%d %H:%M} │ failed (SyncRunInProgress) │ "
        "SYNC_RUN_IN_PROGRESS │ person (skipped) │"
    ) in table
    assert (
        f"{refused.run_id} │ {refused.started_at:%Y-%m-%d %H:%M} │ failed │ STORE_ACCESS_DENIED │ "
        "retry (retry once fixed) │"
    ) in table
    assert (
        f"{stopped.run_id} │ {stopped.started_at:%Y-%m-%d %H:%M} │ failed (StoreAccessDenied) │ "
        "STORE_ACCESS_DENIED │ retry (retry once fixed) │"
    ) in table
    assert f"{retried.run_id} │ {retried.started_at:%Y-%m-%d %H:%M} │ failed │ STORE_UNAVAILABLE │ retry │" in table
    assert (
        f"{older.run_id} │ {older.started_at:%Y-%m-%d %H:%M} │ failed (SyncRunInProgress) │ not recorded │ "
        "not recorded │"
    ) in table

    runs = as_json("caselist", "runs")["data"]["runs"]
    assert [(one["run_id"], one["verdict"], one["banner"]) for one in runs] == [
        (locked.run_id, "person", "skipped"),
        (refused.run_id, "retry", "retry once fixed"),
        (stopped.run_id, "retry", "retry once fixed"),
        (retried.run_id, "retry", None),
        (older.run_id, None, None),
    ]

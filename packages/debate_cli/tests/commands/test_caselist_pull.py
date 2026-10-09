"""`debate-research caselist pull`, run the way the launchd agent runs it.

Through Typer's `CliRunner` against the real application and the real composition root — the real
OpenCaselist client, the real transport, the real importers, the real manifests — with the site
answered by respx. Nothing here reaches the network (respx, and `--disable-socket`), and the
`test` environment names no bucket, so the publish and report stages are skipped with their reason
and the run still succeeds. Publishing is covered end to end by
`tests/smoke/test_caselist_pull.py`, against moto.

The archives served are the invented ones from `tests/fixtures/caselist/`; nothing here is real
caselist content (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES as CAMP_BODIES
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands.caselist_pull import _caption  # pyright: ignore[reportPrivateUsage]
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist_sync import (
    InboxFileKind,
    InboxFileVerdict,
    InboxRetention,
    RetentionDecision,
    RunSummary,
    StageOutcome,
    StageRecord,
    SyncStage,
)
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.integrations.local.macos_notifier import MacOsNotifier

API = "https://api.opencaselist.example.invalid/v1"
FILE_HOST = "https://files.opencaselist.example.invalid"

runner = CliRunner()


def weekly_name(day: date) -> str:
    return f"{SYNTHETIC_CASELIST}-weekly-{day.isoformat()}.zip"


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A `test` environment of this test's own: the API on, a token in the environment, no bucket."""
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
        # The floor the settings allow. Five paced requests at the 1s default would put a unit
        # test over four seconds for nothing: what is under test is the command, not the pacing.
        "DEBATE_CASELIST__MIN_REQUEST_INTERVAL_SECONDS": "0.5",
        "DEBATE_PROVIDERS__CASELIST_TOKEN": f"fixture-token-{secrets.token_hex(8)}",
        # The counts in this module were written by hand for the weeklies alone. The complete-archive
        # rotation, on by default (`v1-e34-t04`), is turned back on by the tests at the end of it.
        "DEBATE_CASELIST__FULL_ARCHIVE_ROTATION": "false",
    }.items():
        monkeypatch.setenv(name, value)
    yield data


@pytest.fixture
def archives(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_zips(tmp_path / "published")


@pytest.fixture
def site(archives: dict[date, Path]) -> Iterator[respx.MockRouter]:
    """OpenCaselist: three weekly archives, one full archive, and no OpenEv files.

    The complete archive is served as the 09-15 weekly's bytes: the synthetic weeklies are
    cumulative, so the newest one holds what a complete archive of that date would.
    """
    listing = [
        {"name": weekly_name(snapshot.snapshot), "url": f"{FILE_HOST}/{weekly_name(snapshot.snapshot)}"}
        for snapshot in SNAPSHOTS
    ]
    newest = SNAPSHOTS[-1].snapshot
    full = f"{SYNTHETIC_CASELIST}-all-{newest.isoformat()}.zip"
    listing.append({"name": full, "url": f"{FILE_HOST}/{full}"})
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/caselists/{SYNTHETIC_CASELIST}/downloads").respond(200, json=listing)
        router.get(f"{API}/openev").respond(200, json=[])
        for snapshot in SNAPSHOTS:
            router.get(f"{FILE_HOST}/{weekly_name(snapshot.snapshot)}").respond(
                200, content=archives[snapshot.snapshot].read_bytes()
            )
        router.get(f"{FILE_HOST}/{full}").respond(200, content=archives[newest].read_bytes())
        yield router


def pull(*arguments: str) -> dict[str, Any]:
    """Run `caselist pull` asking for JSON, and return its envelope with the exit code on it."""
    result: Result = runner.invoke(create_app(), ["--json", "caselist", "pull", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}"
    envelope = json.loads(lines[0])
    assert isinstance(envelope, dict)
    envelope["exit_code"] = result.exit_code
    return envelope  # pyright: ignore[reportUnknownVariableType]


# ------------------------------------------------------------------------------------------------
# What a run does
# ------------------------------------------------------------------------------------------------


def test_a_dry_run_lists_what_it_would_download_and_writes_nothing(
    installation: Path, site: respx.MockRouter
) -> None:
    """ac2 through the command: listing calls only, and no data directory left behind."""
    envelope = pull("--caselist", SYNTHETIC_CASELIST, "--dry-run")

    assert envelope["exit_code"] == ExitCode.OK
    data = envelope["data"]
    assert data["dry_run"] is True
    assert [one["archive"] for one in data["selections"] if one["decision"] == "download"] == [
        weekly_name(SNAPSHOTS[0].snapshot),
        weekly_name(SNAPSHOTS[1].snapshot),
        weekly_name(SNAPSHOTS[2].snapshot),
    ]
    assert data["archives_downloaded"] == 0
    assert data["summary_written_to"] is None
    assert not any(call.request.url.host == "files.opencaselist.example.invalid" for call in site.calls)
    assert not (installation / "inbox").exists()
    assert not (installation / "objects").exists()


def test_a_run_downloads_imports_and_reports_this_weeks_archives(
    installation: Path, site: respx.MockRouter
) -> None:
    """The whole local half of ac1, oldest first, with the counts the fixture states by hand.

    Three archives here rather than two, because this installation starts empty: the totals are
    `expected_summary.json`'s three weeks added up. Stored members — NEW + UNCHANGED + CHANGED +
    DUPLICATE — are 4, then 7 + 3 + 1 + 2 = 13, then 2 + 12 = 14: **31**. Distinct digests the
    store did not have grow 0 → 4 → 12 → 14: **14**. Skips, the `zip` row, are 3 + 3 + 5: **11**.
    """
    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.OK
    data = envelope["data"]
    assert data["archives_downloaded"] == 3
    assert data["files_imported"] == 31
    assert data["blobs_stored"] == 14
    assert data["files_skipped"] == 11
    assert data["snapshots_imported"] == [
        f"{SYNTHETIC_CASELIST} {snapshot.snapshot.isoformat()}" for snapshot in SNAPSHOTS
    ]
    fetched = [
        call.request.url.path.rsplit("/", 1)[-1]
        for call in site.calls
        if call.request.url.host == "files.opencaselist.example.invalid"
    ]
    assert fetched == [weekly_name(snapshot.snapshot) for snapshot in SNAPSHOTS]
    assert Path(data["summary_written_to"]).is_file()


def test_a_second_run_downloads_nothing_and_says_nothing_is_new(
    installation: Path, site: respx.MockRouter
) -> None:
    """ac1's second half through the command: exit 0, and not one byte fetched again."""
    pull("--caselist", SYNTHETIC_CASELIST)
    fetched_first_time = len(site.calls)

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.OK
    assert envelope["data"]["nothing_new"] is True
    assert envelope["data"]["archives_downloaded"] == 0
    downloads_after = [
        call
        for call in site.calls[fetched_first_time:]
        if call.request.url.host == "files.opencaselist.example.invalid"
    ]
    assert downloads_after == []


def test_the_publish_and_report_stages_say_why_they_were_skipped(
    installation: Path, site: respx.MockRouter
) -> None:
    """A run on an environment with no bucket is a success that says so, not a silent no-op."""
    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    stages = {one["stage"]: one for one in envelope["data"]["stages"]}
    assert stages["publish"]["outcome"] == "skipped"
    assert "no evidence bucket" in stages["publish"]["reason"]
    assert stages["parse"]["outcome"] == "skipped"
    assert "v1-e31-t06" in stages["parse"]["reason"]
    assert stages["landscape"]["outcome"] == "skipped"
    assert envelope["exit_code"] == ExitCode.OK


def test_a_download_the_site_will_not_serve_is_a_failure_with_a_usable_hint(
    installation: Path, site: respx.MockRouter, archives: dict[date, Path]
) -> None:
    """The first archive lands, the second is gone: exit 1, and what landed is still imported."""
    site.get(f"{FILE_HOST}/{weekly_name(SNAPSHOTS[1].snapshot)}").respond(404)

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    assert "download" in envelope["error"]["message"]
    assert envelope["error"]["details"]["snapshots_imported"] == [
        f"{SYNTHETIC_CASELIST} {SNAPSHOTS[0].snapshot.isoformat()}"
    ]


# ------------------------------------------------------------------------------------------------
# Which caselists, and the refusals
# ------------------------------------------------------------------------------------------------


def test_the_profiles_caselists_are_pulled_when_the_flag_is_not_given(
    installation: Path, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # JSON, because pydantic-settings decodes a list-valued variable itself. A profile file
    # writes it as a TOML list; `ops/launchd/` passes --caselist flags instead.
    monkeypatch.setenv("DEBATE_CASELIST__SYNC_CASELISTS", json.dumps([SYNTHETIC_CASELIST]))

    envelope = pull("--dry-run")

    assert envelope["exit_code"] == ExitCode.OK
    assert envelope["data"]["caselists"] == [SYNTHETIC_CASELIST]


def test_a_run_with_no_caselist_anywhere_refuses_and_names_both_ways_to_set_one(
    installation: Path, site: respx.MockRouter
) -> None:
    envelope = pull("--dry-run")

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "NO_CASELISTS_CONFIGURED"
    assert "--caselist" in envelope["error"]["message"]
    assert "sync_caselists" in envelope["error"]["message"]


def test_an_installation_that_has_not_turned_the_api_on_refuses_before_any_request(
    installation: Path, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The data-use policy's E34 gate is the operator's decision, and this is where it is felt."""
    monkeypatch.setenv("DEBATE_CASELIST__API_ENABLED", "false")

    envelope = pull("--caselist", SYNTHETIC_CASELIST, "--dry-run")

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "CASELIST_API_DISABLED"
    assert site.calls.call_count == 0


def test_dry_run_and_publish_pending_together_are_a_usage_error(
    installation: Path, site: respx.MockRouter
) -> None:
    result = runner.invoke(
        create_app(), ["caselist", "pull", "--caselist", SYNTHETIC_CASELIST, "--dry-run", "--publish-pending"]
    )

    assert result.exit_code == ExitCode.USAGE_ERROR


def test_publish_pending_with_nothing_owed_exits_zero_without_fetching(
    installation: Path, site: respx.MockRouter
) -> None:
    envelope = pull("--publish-pending")

    assert envelope["exit_code"] == ExitCode.OK
    stages = {one["stage"]: one for one in envelope["data"]["stages"]}
    assert stages["download"]["outcome"] == "skipped"
    assert stages["publish"]["outcome"] == "skipped"
    assert not any(call.request.url.host == "files.opencaselist.example.invalid" for call in site.calls)


def test_a_second_run_while_one_holds_the_lock_exits_at_once(
    installation: Path, site: respx.MockRouter
) -> None:
    """ac4's first half, through the command: the lock message, and nothing done."""
    from debate_core.application.caselist_sync import LOCK_FILENAME, RunLock

    installation.mkdir(parents=True, exist_ok=True)
    with RunLock(installation / LOCK_FILENAME):
        envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "SYNC_RUN_IN_PROGRESS"
    assert "already running" in envelope["error"]["message"]
    assert not any(call.request.url.host == "files.opencaselist.example.invalid" for call in site.calls)


def test_the_help_names_the_three_things_a_run_can_be_asked_to_do() -> None:
    result = runner.invoke(create_app(), ["caselist", "pull", "--help"])

    assert result.exit_code == ExitCode.OK
    rendered = " ".join(result.stdout.split())
    for flag in ("--caselist", "--dry-run", "--publish-pending"):
        assert flag in rendered


def test_nothing_the_command_prints_carries_the_token(installation: Path, site: respx.MockRouter) -> None:
    token = os.environ["DEBATE_PROVIDERS__CASELIST_TOKEN"]

    result: Result = runner.invoke(
        create_app(), ["--json", "--verbose", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST]
    )

    assert token not in result.stdout
    assert token not in (result.stderr or "")


def test_a_run_summary_reaches_the_data_directory_where_the_run_log_will_read_it(
    installation: Path, site: respx.MockRouter
) -> None:
    """ac4's second half: one JSON file per run, with counts and no school or team code."""
    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    written = Path(envelope["data"]["summary_written_to"])
    assert written.parent == installation / "caselist-sync-runs"
    body = json.loads(written.read_text(encoding="utf-8"))
    assert body["archives_downloaded"] == 3
    assert body["files_imported"] == 31
    text = written.read_text(encoding="utf-8")
    for forbidden in ("Maple Grove", "Cedar Hollow", "Riverbend Academy", "ZaLu", "MnPr"):
        assert forbidden not in text


# ------------------------------------------------------------------------------------------------
# A camp file is named by id, never by title (v1-e34-t12)
# ------------------------------------------------------------------------------------------------

PROBE = "Zqxprobe"
"""In each camp file's folder and title, and so in its inbox name. Searched for case-insensitively."""

#: A camp document the run imports, and a camp release the archive reader refuses, naming the file.
PROBE_CAMP_FILES = {
    f"/openev/2026/{PROBE} Institute/{PROBE} Estuary Solvency Advocate.docx": (
        512,
        CAMP_BODIES["estuary-solvency"],
    ),
    f"/openev/2026/{PROBE} Institute/{PROBE} Camp Release.zip": (
        777,
        b"PK\x03\x04 an invented camp release, cut short: not a zip any reader can open",
    ),
}


@pytest.fixture
def probe_site() -> Iterator[respx.MockRouter]:
    """OpenCaselist listing no archives and the two camp files in :data:`PROBE_CAMP_FILES`."""
    listing = [
        {
            "openev_id": openev_id,
            "path": path,
            "filename": path.rsplit("/", 1)[-1],
            "year": 2026,
            "camp": f"{PROBE} Institute",
            "tags": {"policy": True},
        }
        for path, (openev_id, _) in PROBE_CAMP_FILES.items()
    ]

    def download(request: httpx.Request) -> httpx.Response:
        # The client takes the leading `/` off a listed path before asking for it.
        return httpx.Response(200, content=PROBE_CAMP_FILES["/" + request.url.params["path"]][1])

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/caselists/{SYNTHETIC_CASELIST}/downloads").respond(200, json=[])
        router.get(f"{API}/openev").respond(200, json=listing)
        router.get(f"{API}/download").mock(side_effect=download)
        yield router


@pytest.fixture
def notified(monkeypatch: pytest.MonkeyPatch) -> RecordingNotifier:
    """What the run monitor would have shown: the `test` environment's notifier shows nothing."""
    notifier = RecordingNotifier()
    monkeypatch.setattr(ServiceContainer, "sync_notifier", lambda _: notifier)
    return notifier


def printed(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def assert_no_probe(where: str, text: str) -> None:
    assert PROBE.casefold() not in text.casefold(), f"a camp file's title reached {where}: {text!r}"


def test_no_output_of_a_pull_names_a_camp_file_by_its_title(
    installation: Path, probe_site: respx.MockRouter, notified: RecordingNotifier
) -> None:
    """ac1 through the command: the line the launchd agent writes to stdout, the table a person reads,
    the summary file, `caselist runs` both ways and the notifications. 512 is imported and 777 is
    refused, so the run exits 1 and the failure's own message and details are printed too."""
    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert_no_probe("the stdout line of `caselist pull --json`", json.dumps(envelope))
    selections = envelope["error"]["details"]["openev_selections"]
    assert [(one["openev_id"], one["decision"]) for one in selections] == [
        (512, "download"),
        (777, "download"),
    ]
    assert all(one["inbox_file"].startswith("sha256 ") for one in selections)
    assert all("inbox_name" not in one for one in selections)
    summary_file = Path(envelope["error"]["details"]["summary_written_to"])
    assert_no_probe("the run-summary file", summary_file.read_text(encoding="utf-8"))

    rendered = printed("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)

    assert rendered.exit_code == ExitCode.DOMAIN_FAILURE
    assert "openev-777 (sha256 " in rendered.output, "the table no longer names the refused download"
    assert_no_probe("the rendered `caselist pull`", rendered.output + (rendered.stderr or ""))
    for arguments in (("--json", "caselist", "runs"), ("caselist", "runs")):
        runs = printed(*arguments)
        assert runs.exit_code == ExitCode.OK, runs.output
        assert_no_probe(f"`{' '.join(arguments)}`", runs.output + (runs.stderr or ""))
    assert [one.title for one in notified.sent] == ["caselist pull failed", "caselist pull failed"]
    shown = MacOsNotifier(executable="osascript")
    assert_no_probe("the notifications", " ".join(" ".join(shown.command_for(one)) for one in notified.sent))


# ------------------------------------------------------------------------------------------------
# The inbox's retention stage (v1-e34-t11)
# ------------------------------------------------------------------------------------------------


def test_retention_without_a_bucket_removes_nothing_and_says_why(
    installation: Path, site: respx.MockRouter
) -> None:
    """`test` names no bucket, so no publish can be confirmed: the three weeks stay in the inbox."""
    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    stages = {one["stage"]: one for one in envelope["data"]["stages"]}
    assert stages["retention"]["outcome"] == "skipped"
    assert "nothing leaves the inbox" in stages["retention"]["reason"]
    assert envelope["data"]["inbox_retention"] is None
    assert sorted(path.name for path in (installation / "inbox").iterdir() if path.is_file()) == [
        weekly_name(snapshot.snapshot) for snapshot in SNAPSHOTS
    ]


def _week(day: str, decision: RetentionDecision, size: int) -> InboxFileVerdict:
    return InboxFileVerdict(
        name=f"{SYNTHETIC_CASELIST} {day}",
        kind=InboxFileKind.WEEKLY_ARCHIVE,
        decision=decision,
        byte_size=size,
        path=Path("/nowhere") / weekly_name(date.fromisoformat(day)),
    )


def _retention_summary(*, dry_run: bool) -> RunSummary:
    """A run whose retention stage judged three files: two weeks removable, one week not imported."""
    retention = InboxRetention(
        dry_run=dry_run,
        removed=(
            _week("2026-09-01", RetentionDecision.REMOVE, 1000),
            _week("2026-09-08", RetentionDecision.REMOVE, 234),
        ),
        kept=(_week("2026-09-15", RetentionDecision.NOT_IMPORTED, 99),),
        once_imported=(f"{SYNTHETIC_CASELIST} 2026-09-22",) if dry_run else (),
    )
    started = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
    return RunSummary(
        run_id="20260916T060000Z",
        started_at=started,
        finished_at=started,
        dry_run=dry_run,
        caselists=(SYNTHETIC_CASELIST,),
        stages=(
            StageRecord(SyncStage.RETENTION, StageOutcome.PLANNED if dry_run else StageOutcome.COMPLETED),
        ),
        inbox_retention=retention,
    )


def test_retention_the_caption_counts_what_left_the_inbox_and_what_stayed() -> None:
    caption = _caption(_retention_summary(dry_run=False))  # pyright: ignore[reportPrivateUsage]

    assert "Inbox: 2 file(s) removed (1234 bytes freed), 1 kept." in caption


def test_retention_a_dry_runs_caption_says_what_would_leave_and_removes_nothing() -> None:
    caption = _caption(_retention_summary(dry_run=True))  # pyright: ignore[reportPrivateUsage]

    assert (
        "Inbox: would remove 2 file(s) (1234 bytes), 1 kept, and 1 more once this run has imported them "
        "and the bucket confirms them."
    ) in caption
    assert "Nothing was written." in caption


# ------------------------------------------------------------------------------------------------
# The complete archive (v1-e34-t04)
# ------------------------------------------------------------------------------------------------

FULL_NAME = f"{SYNTHETIC_CASELIST}-all-{SNAPSHOTS[-1].snapshot.isoformat()}.zip"


def fetched_files(site: respx.MockRouter) -> list[str]:
    return [
        call.request.url.path.rsplit("/", 1)[-1]
        for call in site.calls
        if call.request.url.host == "files.opencaselist.example.invalid"
    ]


def test_full_archive_rotation_fetches_one_after_the_weeklies_by_default(
    installation: Path, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The profile's default: three weeklies, then the complete archive, from the five a day."""
    monkeypatch.delenv("DEBATE_CASELIST__FULL_ARCHIVE_ROTATION")

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.OK
    assert fetched_files(site) == [*(weekly_name(one.snapshot) for one in SNAPSHOTS), FULL_NAME]
    full = envelope["data"]["full_archive"]
    assert full["fetch"] == SYNTHETIC_CASELIST
    assert full["allowance_after_weeklies"] == 2
    assert [one["snapshot"] for one in full["imported"]] == ["full/2026-09-15"]
    assert (
        installation / "objects" / "manifests" / SYNTHETIC_CASELIST / "full" / "2026-09-15.jsonl"
    ).is_file()


def test_full_archive_flag_dry_run_shows_the_decision_and_the_allowance_left(
    installation: Path, site: respx.MockRouter
) -> None:
    """What the operator reads before the first real fetch: nothing fetched, the decision said."""
    result = runner.invoke(
        create_app(),
        [
            "caselist",
            "pull",
            "--caselist",
            SYNTHETIC_CASELIST,
            "--full-archive",
            SYNTHETIC_CASELIST,
            "--dry-run",
        ],
    )

    assert result.exit_code == ExitCode.OK, result.output
    assert fetched_files(site) == []
    flat = " ".join(result.output.split())
    assert (
        "Complete archive: testcl26's would be fetched; 2 bulk download(s) left after the weeklies." in flat
    )


def test_full_archive_flag_is_refused_when_the_weeklies_leave_no_allowance(
    installation: Path, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three a day, three weeklies new: the complete archive is refused, and nothing is fetched."""
    monkeypatch.setenv("DEBATE_CASELIST__BULK_DOWNLOADS_PER_DAY", "3")

    envelope = pull("--caselist", SYNTHETIC_CASELIST, "--full-archive", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert "no complete archive of testcl26 is fetched this run" in envelope["error"]["message"]
    assert fetched_files(site) == []


def test_full_archive_flag_and_publish_pending_are_refused_together(installation: Path) -> None:
    result = runner.invoke(
        create_app(), ["caselist", "pull", "--publish-pending", "--full-archive", SYNTHETIC_CASELIST]
    )

    assert result.exit_code == ExitCode.USAGE_ERROR

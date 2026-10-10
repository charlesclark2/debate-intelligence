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
from debate_cli.commands.caselist_pull import (
    _caption,  # pyright: ignore[reportPrivateUsage]
    _pull_failure,  # pyright: ignore[reportPrivateUsage]
)
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
# The exit code comes from what the failed stages failed on (v1-e34-t13)
# ------------------------------------------------------------------------------------------------
#
# Through the real OpenCaselist client, so the status a server answers with is turned into an error
# by the transport, recorded by the download stage under that error's code, and into an exit code by
# the command. Week three is the one that fails: weeks one and two arrive and are imported, 2 of 3.

WEEK_ONE, WEEK_TWO, WEEK_THREE = (snapshot.snapshot for snapshot in SNAPSHOTS)

A_CAMP_FILE = {
    "openev_id": 512,
    "path": "/openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx",
    "filename": "TSF-Estuary Solvency Advocate.docx",
    "year": 2026,
    "camp": "Tamarack",
    "tags": {"policy": True},
}
"""One OpenEv file as `GET /openev` lists it, tagged with its event so the run selects it."""


@pytest.fixture
def quick_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two attempts and a short wait, so a test of the retries does not sit through the defaults."""
    monkeypatch.setenv("DEBATE_CASELIST__MAX_ATTEMPTS", "2")
    monkeypatch.setenv("DEBATE_CASELIST__BACKOFF_BASE_SECONDS", "0.01")


def stages_of(envelope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The run's stages by name, from `data` on success or the failure's `details`."""
    summary = envelope["data"] if envelope["data"] is not None else envelope["error"]["details"]
    return {one["stage"]: one for one in summary["stages"]}


def requests_for(site: respx.MockRouter, archive: str) -> int:
    return sum(1 for call in site.calls if call.request.url.path.endswith(f"/{archive}"))


def test_a_download_answered_503_past_the_retries_exits_three_and_the_next_run_fetches_it(
    installation: Path, site: respx.MockRouter, archives: dict[date, Path], quick_retries: None
) -> None:
    """The file host answers 503 to both attempts. That is a provider that did not answer, so the
    run is a `3`; the next run fetches the one week still missing and nothing else."""
    week_three = site.get(f"{FILE_HOST}/{weekly_name(WEEK_THREE)}")
    week_three.respond(503)

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.RETRIEVAL_FAILURE, envelope
    assert envelope["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    assert envelope["error"]["exit_code"] == 3
    assert requests_for(site, weekly_name(WEEK_THREE)) == 2, "bounded: two attempts, as configured"
    download = stages_of(envelope)["download"]
    assert (download["outcome"], download["error_codes"]) == ("failed", ["PROVIDER_UNAVAILABLE"])
    assert envelope["error"]["details"]["snapshots_imported"] == [
        f"{SYNTHETIC_CASELIST} {WEEK_ONE.isoformat()}",
        f"{SYNTHETIC_CASELIST} {WEEK_TWO.isoformat()}",
    ]

    week_three.respond(200, content=archives[WEEK_THREE].read_bytes())
    again = pull("--caselist", SYNTHETIC_CASELIST)

    assert again["exit_code"] == ExitCode.OK, again
    assert again["data"]["snapshots_imported"] == [f"{SYNTHETIC_CASELIST} {WEEK_THREE.isoformat()}"]
    assert requests_for(site, weekly_name(WEEK_ONE)) == 1
    assert requests_for(site, weekly_name(WEEK_TWO)) == 1


def test_a_download_that_times_out_exits_three(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    site.get(f"{FILE_HOST}/{weekly_name(WEEK_THREE)}").mock(side_effect=httpx.ReadTimeout("timed out"))

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.RETRIEVAL_FAILURE, envelope
    assert stages_of(envelope)["download"]["error_codes"] == ["PROVIDER_UNAVAILABLE"]


def test_a_connection_that_never_opens_exits_three(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    site.get(f"{FILE_HOST}/{weekly_name(WEEK_THREE)}").mock(side_effect=httpx.ConnectError("refused"))

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.RETRIEVAL_FAILURE, envelope
    assert stages_of(envelope)["download"]["error_codes"] == ["PROVIDER_UNAVAILABLE"]


def test_a_rate_limit_that_is_not_the_daily_cap_exits_three(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    """A `Retry-After` of ten minutes is longer than the client will sit through and far short of a
    day: a burst limit that outlasted the retries, which a later run does not meet."""
    site.get(f"{FILE_HOST}/{weekly_name(WEEK_THREE)}").respond(429, headers={"Retry-After": "600"})

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.RETRIEVAL_FAILURE, envelope
    assert stages_of(envelope)["download"]["error_codes"] == ["PROVIDER_RATE_LIMITED"]


def test_the_daily_cap_defers_the_week_and_the_run_still_exits_zero(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    """Unchanged: a `Retry-After` of a day is the site's verdict for today, the week is deferred,
    and a run that captured the rest is a success. It is never a `3`."""
    site.get(f"{FILE_HOST}/{weekly_name(WEEK_THREE)}").respond(429, headers={"Retry-After": "86400"})

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.OK, envelope
    download = stages_of(envelope)["download"]
    assert (download["outcome"], download["error_codes"]) == ("completed", [])
    assert envelope["data"]["archives_deferred"] == 1


def test_the_daily_cap_on_a_camp_download_exits_one(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    """A camp download has nothing to be deferred to, so the day's verdict fails the stage, and a
    verdict is a `1`: running the command again today gets the same answer."""
    site.get(f"{API}/openev").respond(200, json=[A_CAMP_FILE])
    site.get(f"{API}/download").respond(429, headers={"Retry-After": "86400"})

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert stages_of(envelope)["download"]["error_codes"] == ["DAILY_DOWNLOAD_LIMIT_REACHED"]


def test_a_camp_download_the_api_answers_401_to_exits_one_and_is_asked_for_once(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    """Policy E34 gate 5: a 401 is never retried, and no later run can cure it without a login."""
    site.get(f"{API}/openev").respond(200, json=[A_CAMP_FILE])
    refused = site.get(f"{API}/download")
    refused.respond(401)

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert stages_of(envelope)["download"]["error_codes"] == ["CASELIST_AUTH_EXPIRED"]
    assert refused.call_count == 1


def test_an_archive_the_file_host_no_longer_serves_exits_one(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    site.get(f"{FILE_HOST}/{weekly_name(WEEK_THREE)}").respond(404)

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert stages_of(envelope)["download"]["error_codes"] == ["ARCHIVE_UNAVAILABLE"]


def test_an_archive_over_the_size_ceiling_exits_one(
    installation: Path,
    site: respx.MockRouter,
    archives: dict[date, Path],
    quick_retries: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ceiling is set between the fixture's two smaller weeks and its largest, week three."""
    sizes = {day: path.stat().st_size for day, path in archives.items()}
    assert max(sizes[WEEK_ONE], sizes[WEEK_TWO]) < sizes[WEEK_THREE]
    monkeypatch.setenv("DEBATE_CASELIST__MAX_ARCHIVE_BYTES", str(sizes[WEEK_THREE] - 1))

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert stages_of(envelope)["download"]["error_codes"] == ["ARCHIVE_TOO_LARGE"]


def test_one_retryable_and_one_deterministic_failure_exit_one(
    installation: Path, site: respx.MockRouter, quick_retries: None
) -> None:
    """Week three's download answers 503, which a retry may cure. Week two arrives as bytes no
    reader can open, which it cannot. One verdict among the failures makes the run a `1`."""
    site.get(f"{FILE_HOST}/{weekly_name(WEEK_TWO)}").respond(
        200, content=b"PK\x03\x04 an invented archive, cut short: not a zip any reader can open"
    )
    site.get(f"{FILE_HOST}/{weekly_name(WEEK_THREE)}").respond(503)

    envelope = pull("--caselist", SYNTHETIC_CASELIST)

    stages = stages_of(envelope)
    assert stages["download"]["error_codes"] == ["PROVIDER_UNAVAILABLE"]
    assert stages["import"]["error_codes"] == ["UNREADABLE_ARCHIVE"]
    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert envelope["error"]["exit_code"] == 1


def failed_run(*stages: StageRecord) -> RunSummary:
    """A run summary holding these stage records and nothing else: what the exit rule reads."""
    started = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
    return RunSummary(
        run_id="20260916T060000Z",
        started_at=started,
        finished_at=started,
        dry_run=False,
        caselists=(SYNTHETIC_CASELIST,),
        stages=stages,
    )


def failed(stage: SyncStage, *codes: str, hint: str | None = None) -> StageRecord:
    return StageRecord(stage, StageOutcome.FAILED, "a sentence", error_codes=codes, hint=hint)


@pytest.mark.parametrize(
    ("failures", "expected"),
    [
        pytest.param(
            [(SyncStage.IMPORT, ("STORE_UNAVAILABLE",))],
            ExitCode.RETRIEVAL_FAILURE,
            id="the store did not answer the import",
        ),
        pytest.param(
            [(SyncStage.DOWNLOAD, ("PROVIDER_UNAVAILABLE",)), (SyncStage.PUBLISH, ("STORE_ACCESS_DENIED",))],
            ExitCode.RETRIEVAL_FAILURE,
            id="two stages, both retryable",
        ),
        pytest.param(
            [(SyncStage.DOWNLOAD, ("PROVIDER_UNAVAILABLE",)), (SyncStage.IMPORT, ("UNREADABLE_ARCHIVE",))],
            ExitCode.DOMAIN_FAILURE,
            id="one retryable stage and one deterministic",
        ),
        pytest.param(
            [(SyncStage.IMPORT, ("STORE_UNAVAILABLE", "UNREADABLE_ARCHIVE"))],
            ExitCode.DOMAIN_FAILURE,
            id="one stage, a retryable failure and a deterministic one",
        ),
        pytest.param(
            [(SyncStage.DOWNLOAD, ("ARCHIVE_UNAVAILABLE",))],
            ExitCode.DOMAIN_FAILURE,
            id="a refused archive",
        ),
        pytest.param(
            [(SyncStage.DOWNLOAD, ("DAILY_DOWNLOAD_LIMIT_REACHED",))],
            ExitCode.DOMAIN_FAILURE,
            id="the daily cap",
        ),
        pytest.param(
            [(SyncStage.IMPORT, ("A_CODE_NOBODY_MAPPED",))],
            ExitCode.DOMAIN_FAILURE,
            id="a code on no list",
        ),
        pytest.param(
            [(SyncStage.IMPORT, ("INTERNAL_ERROR",))],
            ExitCode.DOMAIN_FAILURE,
            id="an error nobody modelled",
        ),
        pytest.param(
            [(SyncStage.IMPORT, ())],
            ExitCode.DOMAIN_FAILURE,
            id="a failed stage that recorded no code",
        ),
        pytest.param(
            [(SyncStage.IMPORT, ("STORE_UNAVAILABLE",)), (SyncStage.REPORT, ("CASELIST_DRIFT",))],
            ExitCode.RETRIEVAL_FAILURE,
            id="a stage that need not finish decides nothing",
        ),
    ],
)
def test_the_exit_code_is_three_only_when_every_required_failure_is_retryable(
    failures: list[tuple[SyncStage, tuple[str, ...]]], expected: ExitCode
) -> None:
    """The rule by itself, on hand-written stage records: 3 only when every failure behind a stage
    that had to finish is one a retry may cure; 1 as soon as one is not, or has no code."""
    failure = _pull_failure(failed_run(*(failed(stage, *codes) for stage, codes in failures)), {})

    assert failure.exit_code is expected
    assert failure.code == "CASELIST_PULL_INCOMPLETE"


def test_a_stage_that_names_its_own_fix_supplies_the_commands_hint() -> None:
    """A refused store's fix comes before "run it again": running it again changes nothing."""
    fix = "This machine refused the blob directory: check storage.data_dir."
    failure = _pull_failure(failed_run(failed(SyncStage.PUBLISH, "STORE_ACCESS_DENIED", hint=fix)), {})

    assert failure.hint is not None
    assert failure.hint.startswith(fix)
    assert "--publish-pending" not in failure.hint


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


def test_a_pending_work_file_that_cannot_be_read_exits_one_names_it_by_role_and_is_left_alone(
    installation: Path, site: respx.MockRouter
) -> None:
    """`--publish-pending` reads the pending-work file before anything else. One that was cut short
    is not "nothing owed" (`v1-e34-t18`): the command exits `1`, its hint names the file by what it
    is for and never by where it is, and the file is byte for byte what it was."""
    cut_short = b'{"publish": [{"caselist": "testcl26", "snap'
    installation.mkdir(parents=True)
    (installation / "caselist-sync-pending.json").write_bytes(cut_short)

    envelope = pull("--publish-pending")

    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert envelope["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    stages = {one["stage"]: one for one in envelope["error"]["details"]["stages"]}
    assert stages["publish"]["outcome"] == "failed"
    assert stages["publish"]["error_codes"] == ["PENDING_WORK_UNREADABLE"]
    assert "the pending-work file under storage.data_dir" in envelope["error"]["hint"]
    said = json.dumps([envelope["error"]["message"], envelope["error"]["hint"], stages["publish"]])
    assert str(installation) not in said
    assert "aws sso login" not in said
    assert (installation / "caselist-sync-pending.json").read_bytes() == cut_short
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

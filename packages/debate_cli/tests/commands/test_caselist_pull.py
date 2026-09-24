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
from datetime import date
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
    }.items():
        monkeypatch.setenv(name, value)
    yield data


@pytest.fixture
def archives(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_zips(tmp_path / "published")


@pytest.fixture
def site(archives: dict[date, Path]) -> Iterator[respx.MockRouter]:
    """OpenCaselist: three weekly archives, one full archive, and no OpenEv files."""
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
        router.get(f"{FILE_HOST}/{full}").respond(200, content=b"the full archive is not pulled weekly")
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

"""What `caselist pull` and `caselist runs` print names no path on this machine (`v1-e34-t16`).

The scheduled-sync runbook says the run's output can be pasted into an issue as it is. The launchd
agent runs `debate-research --json caselist pull`, so its stdout log holds this command's envelope,
and a person reads the rendered table and `caselist runs` the same way.

Each test runs the real application and composition root, with OpenCaselist answered by respx, in a
data directory under :data:`DATA_PROBE` and with `HOME` set to a directory under :data:`HOME_PROBE`.
It then looks for either probe, for the test's temporary directory, for the user's name and for
any absolute path in stdout and stderr, both as JSON and rendered, and in the files the run left in
the data directory. `debate_core`'s `test_pull_names_no_path_on_this_machine.py` runs the same probe
over every kind of run a record describes, its notifications and the bucket's copies.

The archives served are the invented ones from `tests/fixtures/caselist/`; nothing here is real
caselist content (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

import getpass
import json
import os
import re
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
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
from debate_core.application.caselist_sync import LOCK_FILENAME, RUN_SUMMARY_DIRECTORY, RunLock

API = "https://api.opencaselist.example.invalid/v1"
FILE_HOST = "https://files.opencaselist.example.invalid"

DATA_PROBE = "Zqxdataprobe"
"""In the path of the data directory, and so of the inbox inside it. Searched for case-insensitively."""

HOME_PROBE = "Zqxhomeprobe"
"""In the path `HOME` is set to, apart from the data directory. Searched for case-insensitively."""

ABSOLUTE_PATH = re.compile(r"(?<![\w.:/~-])(?:~/|/(?:Users|home|private|var|tmp|Volumes|opt|etc)/)")
"""The start of a path on a machine. Not after a word, a dot, a colon or a slash, so that a URL's
path and the `docs/runbooks/…` a hint cites are not taken for one."""

WIDE = {"COLUMNS": "1000"}
"""Wide enough that Rich wraps no reason, so that a path is never split across two lines."""

runner = CliRunner()


def weekly_name(snapshot: object) -> str:
    return f"{SYNTHETIC_CASELIST}-weekly-{snapshot}.zip"


@dataclass(frozen=True)
class Probe:
    root: Path
    data_dir: Path
    home: Path

    def found_in(self, text: str) -> list[str]:
        """What of this machine `text` names, by what it is; empty when it names nothing."""
        found = [
            what
            for what, needle in (
                ("the data directory's probe", DATA_PROBE),
                ("the home directory's probe", HOME_PROBE),
                ("the temporary directory", str(self.root)),
                ("the temporary directory, resolved", str(self.root.resolve())),
            )
            if needle.casefold() in text.casefold()
        ]
        user = getpass.getuser()
        if len(user) >= 3 and re.search(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", text, re.I):
            found.append("the user's name")
        if match := ABSOLUTE_PATH.search(text):
            around = text[max(match.start() - 60, 0) : match.end() + 60]
            found.append(f"an absolute path at {match.start()}: {around!r}")
        return found


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Probe]:
    """A `test` environment of this test's own, as `test_caselist_pull.py` builds it, in the probe's
    data directory and with `HOME` under the other probe. No bucket, so the publish stage is skipped."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    home = tmp_path / HOME_PROBE / "operator"
    home.mkdir(parents=True)
    data = tmp_path / DATA_PROBE / ".debate-research" / "test"
    for name, value in {
        "HOME": str(home),
        "DEBATE_ENV": "test",
        "DEBATE_STORAGE__DATA_DIR": str(data),
        "DEBATE_ALLOW_NETWORK": "true",
        "DEBATE_CASELIST__API_ENABLED": "true",
        "DEBATE_CASELIST__API_BASE_URL": API,
        "DEBATE_CASELIST__MIN_REQUEST_INTERVAL_SECONDS": "0.5",
        "DEBATE_PROVIDERS__CASELIST_TOKEN": f"fixture-token-{secrets.token_hex(8)}",
        "DEBATE_CASELIST__FULL_ARCHIVE_ROTATION": "false",
        "DEBATE_CASELIST__PARSE_IMPORTED_SOURCES": "false",
    }.items():
        monkeypatch.setenv(name, value)
    assert Path.home() == home
    yield Probe(root=tmp_path, data_dir=data, home=home)


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
    return runner.invoke(create_app(), list(arguments), env=WIDE)


def printed(result: Result) -> str:
    """Everything the command wrote, stdout and stderr."""
    return f"{result.stdout}\n{result.stderr}"


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}"
    envelope: dict[str, Any] = json.loads(lines[0])
    return envelope


def files_left(data_dir: Path) -> dict[str, str]:
    """The run summaries, the run log and the run details a run left in the data directory."""
    return {
        f"the data directory's {path.relative_to(data_dir)}": path.read_text(encoding="utf-8")
        for path in sorted(data_dir.rglob("*"))
        if path.is_file()
        and (path.name.startswith("caselist-sync-run") or path.parent.name == RUN_SUMMARY_DIRECTORY)
    }


def assert_names_nothing_of_this_machine(texts: dict[str, str], probe: Probe) -> None:
    named = {where: found for where, text in texts.items() if (found := probe.found_in(text))}
    assert not named, f"a path on this machine reached {json.dumps(named, indent=2)}"


def test_the_probe_finds_a_path_into_the_data_directory_or_the_home_directory(tmp_path: Path) -> None:
    """Without this a probe could pass by looking for a string that was never there."""
    probe = Probe(root=tmp_path, data_dir=tmp_path / DATA_PROBE / "dev", home=tmp_path / HOME_PROBE)
    assert probe.found_in(f"would download 3 file(s) into {probe.data_dir / 'inbox'}")
    assert probe.found_in(f"{probe.home}/Library/Logs/debate-research/caselist-sync.jsonl")
    assert probe.found_in("lock held at ~/.debate-research/dev/caselist-sync.lock")
    assert not probe.found_in(
        "would download 3 file(s) into the inbox; see docs/runbooks/caselist-scheduled-sync.md"
    )


# ------------------------------------------------------------------------------------------------
# ac1: the dry run, as JSON and rendered
# ------------------------------------------------------------------------------------------------


def test_a_dry_run_prints_the_inbox_by_its_role_and_no_path_on_this_machine(
    probe: Probe, site: respx.MockRouter
) -> None:
    """`--json` and the table, with `--verbose` for the progress lines. A dry run writes no file."""
    as_json = invoke("--json", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST, "--dry-run")
    rendered = invoke("--verbose", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST, "--dry-run")

    assert as_json.exit_code == ExitCode.OK, printed(as_json)
    assert rendered.exit_code == ExitCode.OK, printed(rendered)
    assert_names_nothing_of_this_machine(
        {"caselist pull --json --dry-run": printed(as_json), "caselist pull --dry-run": printed(rendered)},
        probe,
    )
    data = envelope_of(as_json)["data"]
    (download,) = [stage for stage in data["stages"] if stage["stage"] == "download"]
    assert download["reason"] == "would download 3 file(s) into the inbox"
    assert data["summary_written_to"] is None
    assert "would download 3 file(s) into the inbox" in rendered.stdout
    assert not probe.data_dir.exists() or files_left(probe.data_dir) == {}


# ------------------------------------------------------------------------------------------------
# ac2: a run, the run list, and a run another run's lock refused
# ------------------------------------------------------------------------------------------------


def test_a_run_and_the_run_list_print_no_path_on_this_machine(probe: Probe, site: respx.MockRouter) -> None:
    """A run that imports three weeks, then one that finds nothing new; then `caselist runs`.

    The envelope says where the summary was written, as a path inside the data directory.
    """
    first = invoke("--json", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST)
    second = invoke("--verbose", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST)
    listed = invoke("caselist", "runs")
    listed_as_json = invoke("--json", "caselist", "runs")

    for result in (first, second, listed, listed_as_json):
        assert result.exit_code == ExitCode.OK, printed(result)
    assert_names_nothing_of_this_machine(
        {
            "caselist pull --json": printed(first),
            "caselist pull": printed(second),
            "caselist runs": printed(listed),
            "caselist runs --json": printed(listed_as_json),
            **files_left(probe.data_dir),
        },
        probe,
    )
    written_to = envelope_of(first)["data"]["summary_written_to"]
    run_id = envelope_of(first)["data"]["run_id"]
    assert written_to == f"caselist-sync-runs/{run_id}.json"
    assert json.loads((probe.data_dir / written_to).read_text(encoding="utf-8"))["run_id"] == run_id


def test_a_run_another_runs_lock_refused_prints_no_path_on_this_machine(
    probe: Probe, site: respx.MockRouter
) -> None:
    """The refusal names the lock by its file name in the data directory, as the runbook does."""
    probe.data_dir.mkdir(parents=True)
    with RunLock(probe.data_dir / LOCK_FILENAME):
        as_json = invoke("--json", "caselist", "pull", "--caselist", SYNTHETIC_CASELIST)
        rendered = invoke("caselist", "pull", "--caselist", SYNTHETIC_CASELIST)
    listed = invoke("--json", "caselist", "runs")

    assert as_json.exit_code == ExitCode.DOMAIN_FAILURE, printed(as_json)
    assert rendered.exit_code == ExitCode.DOMAIN_FAILURE, printed(rendered)
    assert_names_nothing_of_this_machine(
        {
            "caselist pull --json": printed(as_json),
            "caselist pull": printed(rendered),
            "caselist runs --json": printed(listed),
            **files_left(probe.data_dir),
        },
        probe,
    )
    assert envelope_of(as_json)["error"]["message"] == (
        "another caselist sync is already running (it holds the run lock, caselist-sync.lock in the data "
        "directory); this run did nothing. Wait for it to finish, or remove the lock file if no process "
        "holds it."
    )

"""`debate-research caselist import` end to end, as `validate-dev` runs it before a promotion.

The whole user-facing surface in one check: an operator's three weekly archives, imported in
order through the installed command, into a data directory that did not exist a moment ago —
and the counts they produce compared against `tests/fixtures/caselist/expected_summary.json`.

**This one is offline, unlike the rest of `tests/smoke/`.** The other checks here need a deployed
environment because what they verify is that a bucket exists and a session can reach it. What
this verifies is that the import path works at all when it is wired up the way an installation
wires it — the console script, the composition root, the settings profile, the real SQLite file,
the real blob store, the real manifest — and none of that needs a network or an account. Marking
it `live` would mean the one check that covers the command an operator runs every Monday was
skipped in CI and skipped before every promotion.

Running the *real* corpus through this is a separate, operator-run job (v1-e30-t06), reported as
counts only; 2,342 files will not finish inside a CI budget, and no real caselist file may reach
this repository in any case (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
    written_expected_summary,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A data directory and a dev profile of this check's own, and no inherited DEBATE_* vars.

    A profile file rather than environment overrides for the data directory, because that is how
    a real installation is configured: the command has to resolve where to write from
    `config/profiles/<env>.toml`, and a check that bypassed that would not be checking the path
    an operator uses.
    """
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield tmp_path / "data"


@pytest.fixture
def archives(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_zips(tmp_path / "downloads")


def import_week(archive: Path, snapshot: date) -> Result:
    """Run the command exactly as an operator types it, asking for the machine-readable answer."""
    return runner.invoke(
        create_app(),
        [
            "--json",
            "caselist",
            "import",
            str(archive),
            "--caselist",
            SYNTHETIC_CASELIST,
            "--snapshot",
            snapshot.isoformat(),
        ],
    )


def reported(result: Result) -> dict[str, Any]:
    """The `data` object of the one JSON envelope the run printed, or a failure saying why not."""
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    envelope = json.loads(lines[0])
    if result.exit_code != ExitCode.OK:
        error = envelope.get("error") or {}
        pytest.fail(f"import failed: {error.get('code')}: {error.get('message')}")
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


def test_three_weekly_archives_import_into_a_new_data_directory(
    installation: Path, archives: dict[date, Path]
) -> None:
    """The check itself: import all three weeks and hold every count to the expected summary."""
    expected_weeks = {week["snapshot"]: week for week in written_expected_summary()["snapshots"]}  # pyright: ignore[reportIndexIssue, reportGeneralTypeIssues]

    for snapshot in SNAPSHOTS:
        data = reported(import_week(archives[snapshot.snapshot], snapshot.snapshot))
        expected = expected_weeks[snapshot.snapshot.isoformat()]

        assert data["counts"] == expected["classifications"], snapshot.archive_name
        assert data["skipped_total"] == expected["skipped"]["zip"], snapshot.archive_name
        assert data["warnings"] == expected["warnings"], snapshot.archive_name
        assert data["applied"] is True

    assert _blob_count(installation) == len(DOCUMENT_BODIES)


def test_every_week_leaves_a_manifest_where_the_publisher_will_find_it(
    installation: Path, archives: dict[date, Path]
) -> None:
    """`manifests/<caselist>/<snapshot>.jsonl` in the evidence object store, ready for t05."""
    for snapshot in SNAPSHOTS:
        import_week(archives[snapshot.snapshot], snapshot.snapshot)

    for snapshot in SNAPSHOTS:
        manifest = (
            installation
            / "objects"
            / "manifests"
            / SYNTHETIC_CASELIST
            / f"{snapshot.snapshot.isoformat()}.jsonl"
        )

        assert manifest.is_file(), manifest
        rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
        assert rows[-1]["kind"] == "summary"
        assert rows[-1]["snapshot"] == snapshot.snapshot.isoformat()


def test_running_the_last_week_again_changes_nothing_on_disk(
    installation: Path, archives: dict[date, Path]
) -> None:
    """The property an operator relies on when they cannot remember whether a run finished."""
    for snapshot in SNAPSHOTS:
        import_week(archives[snapshot.snapshot], snapshot.snapshot)
    before = _tree_of(installation)

    data = reported(import_week(archives[SNAPSHOTS[-1].snapshot], SNAPSHOTS[-1].snapshot))

    assert data["newly_stored_blobs"] == 0
    assert _tree_of(installation) == before


def test_an_import_writes_only_inside_the_data_directory(
    installation: Path, archives: dict[date, Path], tmp_path: Path
) -> None:
    """The zip carries a `../escaped.docx` member; nothing may land beside the data directory."""
    import_week(archives[SNAPSHOTS[-1].snapshot], SNAPSHOTS[-1].snapshot)

    assert not (tmp_path / "escaped.docx").exists()
    assert not (installation.parent / "escaped.docx").exists()
    # `debate.sqlite3-wal` and `-shm` are SQLite's own sidecars: the database is opened in WAL
    # mode so a reader never blocks the writer (`debate_core.integrations.local.sqlite_db`).
    written = {entry.name.removesuffix("-wal").removesuffix("-shm") for entry in installation.iterdir()}
    assert written == {"blobs", "debate.sqlite3", "objects"}


def _blob_count(data_dir: Path) -> int:
    blobs = data_dir / "blobs"
    return sum(1 for path in blobs.rglob("*") if path.is_file()) if blobs.exists() else 0


def _tree_of(data_dir: Path) -> dict[str, int]:
    """Every file under the data directory and its size, for comparing before with after.

    The SQLite file is left out: WAL checkpointing changes its size without anything having been
    written, which would make this assert on the wrong thing.
    """
    return {
        str(path.relative_to(data_dir)): path.stat().st_size
        for path in sorted(data_dir.rglob("*"))
        if path.is_file() and not path.name.startswith("debate.sqlite3")
    }

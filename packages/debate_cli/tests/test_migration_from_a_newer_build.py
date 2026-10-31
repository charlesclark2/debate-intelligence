"""A data directory whose database a newer build migrated ends a command with its own code (`v1-e41-t01`).

Every checkout and installed build on the operator's Mac shares `~/.debate-research/<env>`. A command
run from a newer one migrates the database there, and every older build then refuses it. Before this
task the refusal was an unmodelled `MigrationError`: exit `70`, "This is a bug", and its own sentence
withheld. Now it is `DATABASE_FROM_NEWER_BUILD`, exit `1`, with a hint naming both schema versions and
the fix. Exit `1` and not `3`: running the same command again meets the same database, so no retry
fixes it; syncing the checkout or installing the newer build does.

Run through `CliRunner` against the real application and composition root, with `caselist cards` as
the command: building its service opens the installation's database. The message and hint are written
out whole, by hand.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.integrations.local.sqlite_db import SCHEMA_VERSION_TABLE, SqliteDatabase, load_migrations

runner = CliRunner()

NEWER_SCHEMA = 9999


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev installation whose data directory holds a database a newer build migrated."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    with SqliteDatabase.open(tmp_path / "data") as database:
        database.connection.execute(
            f"INSERT INTO {SCHEMA_VERSION_TABLE} (version, name, applied_at) "
            f"VALUES ({NEWER_SCHEMA}, 'a migration from a newer build', '2030-01-01T00:00:00+00:00')"
        )
    (tmp_path / "parsed").mkdir()
    yield tmp_path


def run(tmp_path: Path, *global_options: str) -> Result:
    arguments = [
        *global_options,
        "caselist",
        "cards",
        "--caselist",
        "testcl26",
        "--parsed",
        str(tmp_path / "parsed"),
    ]
    return runner.invoke(create_app(), arguments)


def envelope_of(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def test_a_database_a_newer_build_migrated_has_its_own_code_both_versions_and_the_fix(tmp_path: Path) -> None:
    newest = load_migrations()[-1].version

    result = run(tmp_path, "--json")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert error == {
        "code": "DATABASE_FROM_NEWER_BUILD",
        "message": (
            f"this data directory's database is at schema version {NEWER_SCHEMA}, and this build reads "
            f"schema versions up to {newest}: a newer build migrated it"
        ),
        "exit_code": 1,
        "details": {"database_version": NEWER_SCHEMA, "build_version": newest},
        "hint": (
            f"Schema version {NEWER_SCHEMA} is newer than this build's {newest}, and an older schema "
            "cannot read a newer database safely. Sync this checkout (`scripts/task sync <task>`, or "
            "`git pull` and `uv sync --all-packages`), or install the newer build, then run the command "
            "again."
        ),
    }


def test_the_refusal_is_not_called_a_bug_and_names_no_path(tmp_path: Path) -> None:
    """The rendered panel is the same failure, and `--verbose` prints no traceback for it."""
    result = run(tmp_path, "--verbose")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    written = " ".join((result.stdout + result.stderr).split())
    assert "DATABASE_FROM_NEWER_BUILD" in written
    assert "`scripts/task sync <task>`" in written
    assert "bug" not in written and "Traceback" not in written
    assert str(tmp_path) not in written

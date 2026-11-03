"""`caselist import` of a weekly that arrives late, and of a week imported again (`v1-e30-t18`).

Through Typer's `CliRunner` against the real composition root, over `v1-e30-t17`'s window-order
archives (`tests/fixtures/caselist/build_window_order_archives.py`), whose answers are worked out by
hand there. Each store is its own data directory, so a late import can be compared, byte for byte,
with the date-order run of the same weeks.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.caselist.build_window_order_archives import (
    CASELIST,
    FIRST_WEEK,
    SECOND_WEEK,
    THIRD_WEEK,
    build_weekly_zips,
)
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.manifest import manifest_key

runner = CliRunner()

WEEKS = (FIRST_WEEK, SECOND_WEEK, THIRD_WEEK)


@pytest.fixture(autouse=True)
def no_inherited_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield


class Store:
    """One data directory and a profile naming it, which every command of this store runs with."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.data_dir = root / "data"
        self.profiles = root / "profiles"
        self.profiles.mkdir(parents=True)
        (self.profiles / "dev.toml").write_text(
            f'[storage]\ndata_dir = "{self.data_dir}"\n'
            f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
        self._monkeypatch = monkeypatch

    def import_week(self, archive: Path, week: date, *arguments: str) -> Result:
        self._monkeypatch.setenv("DEBATE_PROFILE_DIR", str(self.profiles))
        return runner.invoke(
            create_app(),
            [
                "--json",
                "caselist",
                "import",
                str(archive),
                "--caselist",
                CASELIST,
                "--snapshot",
                week.isoformat(),
                *arguments,
            ],
        )

    def manifest(self, week: date) -> bytes:
        return (self.data_dir / "objects" / manifest_key(CASELIST, week)).read_bytes()


def data_of(result: Result) -> dict[str, Any]:
    assert result.exit_code == ExitCode.OK, result.stdout + result.stderr
    (line,) = [line for line in result.stdout.splitlines() if line.strip()]
    envelope = json.loads(line)
    assert envelope["status"] == "ok"
    return envelope["data"]


@pytest.fixture
def archives(tmp_path: Path) -> dict[date, Path]:
    return build_weekly_zips(tmp_path / "downloads")


@pytest.fixture
def in_date_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archives: dict[date, Path]) -> Store:
    store = Store(tmp_path / "in-date-order", monkeypatch)
    for week in WEEKS:
        data_of(store.import_week(archives[week], week))
    return store


def test_a_weekly_imported_late_rewrites_the_week_after_it_to_the_date_order_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archives: dict[date, Path], in_date_order: Store
) -> None:
    """ac1. The archives of the weeks already imported are gone, as retention leaves them."""
    late = Store(tmp_path / "late", monkeypatch)
    for week in (FIRST_WEEK, THIRD_WEEK):
        data_of(late.import_week(archives[week], week))
    second = archives[SECOND_WEEK].read_bytes()
    for archive in archives.values():
        archive.unlink()
    (tmp_path / "late-second-week.zip").write_bytes(second)

    data = data_of(late.import_week(tmp_path / "late-second-week.zip", SECOND_WEEK, "--allow-out-of-order"))

    for week in WEEKS:
        assert late.manifest(week) == in_date_order.manifest(week), week
    assert data["rewritten_manifests"] == ["2026-09-15"]
    assert data["complete_archive_recounted"] is None


def test_a_week_already_imported_is_imported_again_without_the_flag(
    archives: dict[date, Path], in_date_order: Store
) -> None:
    """ac2. It needs no flag, writes its own manifest again, and changes no other week's."""
    before = {week: in_date_order.manifest(week) for week in WEEKS}

    data = data_of(in_date_order.import_week(archives[SECOND_WEEK], SECOND_WEEK))

    assert (data["snapshot"], data["previous_snapshot"]) == ("2026-09-08", "2026-09-01")
    assert data["rewritten_manifests"] == []
    assert {week: in_date_order.manifest(week) for week in WEEKS} == before


def test_a_weekly_never_imported_and_older_than_the_newest_still_needs_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archives: dict[date, Path]
) -> None:
    """Importing it rewrites other weeks' manifests, so it is still a deliberate act (Decision 1)."""
    store = Store(tmp_path / "store", monkeypatch)
    for week in (FIRST_WEEK, THIRD_WEEK):
        data_of(store.import_week(archives[week], week))

    refused = store.import_week(archives[SECOND_WEEK], SECOND_WEEK)

    assert refused.exit_code == ExitCode.DOMAIN_FAILURE
    (line,) = [line for line in refused.stdout.splitlines() if line.strip()]
    assert json.loads(line)["error"]["code"] == "SNAPSHOT_OUT_OF_ORDER"

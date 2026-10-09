"""`debate-research caselist reimport-openev-metadata`, through the real composition root (`v1-e30-t08`).

A synthetic camp release is imported with `caselist import-openev` under a table that knows one of
its camps, then re-derived with a table that knows all of them. What is checked is what an operator
relies on: the manifest is rewritten at the key it was read from and nowhere else, no blob on disk
changes, a dry run writes nothing, and a second run writes nothing either.

Invented camps and titles only (the OpenEv fixture's `QDI`/`TSF`/`BWW`, and an unlisted `Zephyr`).
Expected counts are written by hand from the files below.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

FILES = {
    "Disadvantages/Lantern Shipping DA - TSF 2026 MNOP.docx": b"lantern shipping filler",
    "Counterplans/NEG Orchard Grants CP - QDI 2026 JKT.docx": b"orchard grants filler",
    "Kritiks/Tidewater Kritik - Brightwater Workshop 2026.docx": b"tidewater kritik filler",
    "Topicality/Saltmarsh T - Zephyr 2026.docx": b"saltmarsh topicality filler",
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
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
    yield profiles


@pytest.fixture
def imported(tmp_path: Path) -> Path:
    """The data directory, after the release went in with only QDI readable."""
    release = tmp_path / "camp-files"
    for path, body in FILES.items():
        (release / path).parent.mkdir(parents=True, exist_ok=True)
        (release / path).write_bytes(body)
    one_camp = tmp_path / "one_camp.yaml"
    one_camp.write_text("camps:\n  QDI:\n    - Quillfeather\n", encoding="utf-8")
    result = invoke(
        "caselist", "import-openev", str(release), "--year", "2026", "--event", "policy",
        "--snapshot", "2026-09-26", "--camp-aliases", str(one_camp),
    )  # fmt: skip
    assert result.exit_code == ExitCode.OK, result.stdout
    return tmp_path / "data"


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def reimport(*arguments: str) -> dict[str, Any]:
    result = invoke(
        "--json", "caselist", "reimport-openev-metadata", "--year", "2026", "--event", "policy",
        "--camp-aliases", str(CAMP_ALIASES_PATH), *arguments,
    )  # fmt: skip
    assert result.exit_code == ExitCode.OK, result.stdout
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, lines
    return json.loads(lines[0])["data"]


def tree(root: Path) -> dict[str, str]:
    """Every file under `root`, by relative path, to the digest of its bytes."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_reimport_command_rewrites_only_the_release_manifest_at_its_own_key(imported: Path) -> None:
    blobs, objects = tree(imported / "blobs"), tree(imported / "objects")

    data = reimport()

    assert data["manifest_key"] == "manifests/openev/2026-policy.jsonl"
    assert data["manifest"] == str(imported / "objects" / "manifests" / "openev" / "2026-policy.jsonl")
    assert tree(imported / "blobs") == blobs
    after = tree(imported / "objects")
    assert sorted(after) == sorted(objects) == ["manifests/openev/2026-policy.jsonl"]
    assert after != objects


def test_reimport_command_reports_the_counts(imported: Path) -> None:
    data = reimport()

    assert data["camps_before"] == {"QDI": 1, "UNKNOWN": 3}
    assert data["camps_after"] == {"BWW": 1, "QDI": 1, "TSF": 1, "UNKNOWN": 1}
    assert (data["rows"], data["rows_changed"], data["titles_changed"]) == (4, 2, 2)
    assert (data["camp_files_updated"], data["camp_files_missing"], data["blobs_missing"]) == (2, 0, 0)
    assert data["applied"] is True
    assert data["manifest_changed"] is True


def camp_file_rows(data_dir: Path) -> list[tuple[Any, ...]]:
    """The camp-file table's rows. The database file's bytes are no test: closing a connection
    checkpoints the write-ahead log into it."""
    with sqlite3.connect(f"file:{data_dir / 'debate.sqlite3'}?mode=ro", uri=True) as connection:
        return connection.execute("SELECT * FROM caselist_camp_files ORDER BY source_sha256").fetchall()


def test_reimport_command_dry_run_writes_nothing(imported: Path) -> None:
    files, records = tree(imported / "blobs") | tree(imported / "objects"), camp_file_rows(imported)

    data = reimport("--dry-run")

    assert data["applied"] is False
    assert data["manifest"] is None
    assert data["titles_changed"] == 2
    assert tree(imported / "blobs") | tree(imported / "objects") == files
    assert camp_file_rows(imported) == records


def test_reimport_command_a_second_time_writes_nothing(imported: Path) -> None:
    reimport()
    objects = tree(imported / "objects")

    data = reimport()

    assert (data["manifest_changed"], data["manifest"], data["rows_changed"]) == (False, None, 0)
    assert tree(imported / "objects") == objects


def test_reimport_command_without_an_imported_release_is_refused() -> None:
    result = invoke("--json", "caselist", "reimport-openev-metadata", "--year", "2026", "--event", "ld")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "manifests/openev/2026-ld.jsonl" in result.stdout


def test_reimport_command_table_names_camps_and_no_title(imported: Path) -> None:
    result = invoke(
        "caselist", "reimport-openev-metadata", "--year", "2026", "--event", "policy",
        "--camp-aliases", str(CAMP_ALIASES_PATH),
    )  # fmt: skip

    assert result.exit_code == ExitCode.OK
    assert "TSF" in result.stdout
    assert "2 title(s) changed" in result.stdout
    assert all(word not in result.stdout for word in ("Lantern", "Orchard", "Tidewater", "Saltmarsh"))

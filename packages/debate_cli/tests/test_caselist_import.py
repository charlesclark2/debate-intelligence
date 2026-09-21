"""`debate-research caselist import`, run the way an operator runs it, and the manifest it writes.

Through Typer's `CliRunner` against the real application and the real composition root: the real
SQLite database, the real blob store, the real archive reader over the real synthetic archives.
Nothing is faked, because most of what is worth checking here — that a re-import writes the same
manifest bytes, that a dry run leaves the data directory empty, that the summary a program reads
and the table a person reads agree — is only true if the whole path is wired up.

Nothing reaches the network: an import writes to the machine it runs on, and publishing what it
wrote is a separate `debate-research store sync` (v1-e30-t05).
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
    EXPECTED_SNAPSHOTS,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_directories,
    build_snapshot_zips,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands.caselist import EVENTS_BY_SLUG_PREFIX, event_for_caselist
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.manifest import MANIFEST_SCHEMA_VERSION, manifest_key
from debate_core.domain.caselist import Event

runner = CliRunner()

FIRST_WEEK = SNAPSHOTS[0].snapshot
LAST_WEEK = SNAPSHOTS[-1].snapshot


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A profile directory and a data directory this test owns, and no inherited DEBATE_* vars."""
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
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def zips(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_zips(tmp_path / "archives")


@pytest.fixture
def directories(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_directories(tmp_path / "unpacked")


def invoke(*arguments: str) -> Result:
    """Run `debate-research` with these arguments against a freshly built application."""
    return runner.invoke(create_app(), list(arguments))


def import_week(source: Path, snapshot: date, *arguments: str, json_output: bool = False) -> Result:
    prefix = ["--json"] if json_output else []
    return invoke(
        *prefix,
        "caselist",
        "import",
        str(source),
        "--caselist",
        SYNTHETIC_CASELIST,
        "--snapshot",
        snapshot.isoformat(),
        *arguments,
    )


def envelope(result: Result) -> dict[str, Any]:
    """The one JSON object the run put on stdout."""
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON; got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def manifest_path(data_dir: Path, snapshot: date) -> Path:
    return data_dir / "objects" / manifest_key(SYNTHETIC_CASELIST, snapshot)


def manifest_rows(data_dir: Path, snapshot: date) -> list[dict[str, Any]]:
    text = manifest_path(data_dir, snapshot).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


# ------------------------------------------------------------------------------------------------
# It runs, and it reports what it did
# ------------------------------------------------------------------------------------------------


def test_the_command_is_registered() -> None:
    result = invoke("caselist", "import", "--help")

    assert result.exit_code == ExitCode.OK
    assert "--caselist" in result.stdout
    assert "--snapshot" in result.stdout


def test_importing_one_week_succeeds_and_prints_a_summary_table(
    zips: dict[date, Path], data_dir: Path
) -> None:
    result = import_week(zips[FIRST_WEEK], FIRST_WEEK)

    assert result.exit_code == ExitCode.OK
    assert "NEW" in result.stdout
    assert "Classification" in result.stdout
    assert manifest_path(data_dir, FIRST_WEEK).is_file()


def test_the_json_envelope_reports_every_classification(zips: dict[date, Path]) -> None:
    """ac6. A scheduled consumer reads counts, not a table."""
    result = import_week(zips[FIRST_WEEK], FIRST_WEEK, json_output=True)

    data = envelope(result)["data"]
    expected = EXPECTED_SNAPSHOTS[0]
    assert data["counts"] == {
        "NEW": expected.new,
        "UNCHANGED": expected.unchanged,
        "CHANGED": expected.changed,
        "DUPLICATE": expected.duplicate,
        "REMOVED": expected.removed,
        "SUPPRESSED": expected.suppressed,
    }
    assert data["skipped_total"] == expected.skipped_zip
    assert data["applied"] is True
    assert data["caselist"] == SYNTHETIC_CASELIST


def test_importing_the_three_weeks_in_order_matches_the_expected_summary(
    zips: dict[date, Path],
) -> None:
    """ac2, end to end through the command an operator actually types."""
    for expected in EXPECTED_SNAPSHOTS:
        result = import_week(zips[expected.snapshot], expected.snapshot, json_output=True)

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope(result)["data"]
        assert data["counts"]["NEW"] == expected.new, expected.snapshot
        assert data["counts"]["UNCHANGED"] == expected.unchanged, expected.snapshot
        assert data["counts"]["CHANGED"] == expected.changed, expected.snapshot
        assert data["counts"]["DUPLICATE"] == expected.duplicate, expected.snapshot
        assert data["counts"]["REMOVED"] == expected.removed, expected.snapshot


def test_a_directory_imports_exactly_as_the_zip_does(
    zips: dict[date, Path], directories: dict[date, Path], tmp_path: Path
) -> None:
    from_zip = envelope(import_week(zips[FIRST_WEEK], FIRST_WEEK, json_output=True))["data"]

    # A second data directory, so the two runs do not see each other.
    (tmp_path / "profiles" / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "second"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    from_directory = envelope(import_week(directories[FIRST_WEEK], FIRST_WEEK, json_output=True))["data"]

    assert from_zip["counts"] == from_directory["counts"]


# ------------------------------------------------------------------------------------------------
# ac4: the manifest
# ------------------------------------------------------------------------------------------------


def test_the_manifest_is_filed_under_the_key_the_bucket_uses(zips: dict[date, Path], data_dir: Path) -> None:
    """`manifests/<caselist>/<snapshot>.jsonl`, inside the local evidence object store.

    Under `objects/` because that is where
    `debate_core.integrations.local.FsEvidenceObjectStore` roots named objects, which is what
    makes `debate-research store sync` publish it without further arrangement (v1-e30-t05). See
    the Deviations note in the session report for the difference from ac4's literal path.
    """
    import_week(zips[FIRST_WEEK], FIRST_WEEK)

    assert manifest_key(SYNTHETIC_CASELIST, FIRST_WEEK) == "manifests/testcl26/2026-09-01.jsonl"
    assert manifest_path(data_dir, FIRST_WEEK).is_file()


def test_every_row_is_schema_versioned(zips: dict[date, Path], data_dir: Path) -> None:
    import_week(zips[FIRST_WEEK], FIRST_WEEK)

    rows = manifest_rows(data_dir, FIRST_WEEK)

    assert rows
    assert all(row["schema_version"] == MANIFEST_SCHEMA_VERSION for row in rows)


def test_there_is_one_member_row_per_archive_member_sorted_by_path(
    zips: dict[date, Path], data_dir: Path
) -> None:
    """All three weeks, so the last one has a previous archive to have lost a file from."""
    for snapshot in SNAPSHOTS:
        import_week(zips[snapshot.snapshot], snapshot.snapshot)

    rows = manifest_rows(data_dir, LAST_WEEK)
    members = [row for row in rows if row["kind"] == "member"]
    paths = [row["path"] for row in members]
    expected = EXPECTED_SNAPSHOTS[-1]

    assert paths == sorted(paths)
    # Every member the archive held, plus the one path last week had and this one does not.
    assert len(members) == expected.disclosures + expected.skipped_zip + expected.removed
    assert any(row["classification"] == "REMOVED" for row in members)


def test_a_member_row_carries_everything_ac4_names(zips: dict[date, Path], data_dir: Path) -> None:
    import_week(zips[FIRST_WEEK], FIRST_WEEK)

    row = next(
        row
        for row in manifest_rows(data_dir, FIRST_WEEK)
        if row["path"].endswith("Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx")
    )

    assert row["sha256"]
    assert row["byte_size"] > 0
    assert row["format"] == "DOCX"
    assert row["classification"] == "NEW"
    assert row["school"] == "Maple Grove"
    assert row["team_code"] == "QX"
    assert row["side"] == "AFF"
    assert row["tournament"] == "Grove City Invitational"
    assert row["round"] == "Round 1"
    assert row["round_normalized"] == "R1"
    assert row["warnings"] == []


def test_a_row_for_an_unreadable_filename_carries_its_warnings(
    zips: dict[date, Path], data_dir: Path
) -> None:
    import_week(zips[SNAPSHOTS[1].snapshot], SNAPSHOTS[1].snapshot)

    row = next(
        row
        for row in manifest_rows(data_dir, SNAPSHOTS[1].snapshot)
        if row["path"].endswith("notes about the harbor round.docx")
    )

    assert row["side"] == "UNKNOWN"
    assert row["tournament"] is None
    assert row["round"] is None
    assert row["warnings"]


def test_a_skipped_member_has_a_row_with_its_reason_and_no_digest(
    zips: dict[date, Path], data_dir: Path
) -> None:
    import_week(zips[LAST_WEEK], LAST_WEEK)

    skipped = [row for row in manifest_rows(data_dir, LAST_WEEK) if row.get("skip_reason")]

    assert len(skipped) == EXPECTED_SNAPSHOTS[-1].skipped_zip
    assert all(row["sha256"] is None and row["classification"] is None for row in skipped)
    assert {row["skip_reason"] for row in skipped} >= {"SYMLINK", "PATH_OUTSIDE_ARCHIVE"}


def test_the_last_row_is_the_summary(zips: dict[date, Path], data_dir: Path) -> None:
    import_week(zips[FIRST_WEEK], FIRST_WEEK)

    rows = manifest_rows(data_dir, FIRST_WEEK)

    assert rows[-1]["kind"] == "summary"
    assert all(row["kind"] == "member" for row in rows[:-1])
    assert rows[-1]["caselist"] == SYNTHETIC_CASELIST
    assert rows[-1]["snapshot"] == FIRST_WEEK.isoformat()
    assert rows[-1]["classifications"] == {"NEW": EXPECTED_SNAPSHOTS[0].new}


def test_every_member_row_has_the_same_keys(zips: dict[date, Path], data_dir: Path) -> None:
    """Fields that do not apply are null, not absent, so a table built from the file is not ragged."""
    import_week(zips[LAST_WEEK], LAST_WEEK)

    members = [row for row in manifest_rows(data_dir, LAST_WEEK) if row["kind"] == "member"]

    assert len({tuple(sorted(row)) for row in members}) == 1


def test_the_manifest_records_which_archive_the_week_was_compared_against(
    zips: dict[date, Path], data_dir: Path
) -> None:
    import_week(zips[FIRST_WEEK], FIRST_WEEK)
    import_week(zips[SNAPSHOTS[1].snapshot], SNAPSHOTS[1].snapshot)

    first = manifest_rows(data_dir, FIRST_WEEK)[-1]
    second = manifest_rows(data_dir, SNAPSHOTS[1].snapshot)[-1]

    assert first["previous_snapshot"] is None
    assert second["previous_snapshot"] == FIRST_WEEK.isoformat()


# ------------------------------------------------------------------------------------------------
# ac3: re-import is a no-op
# ------------------------------------------------------------------------------------------------


def test_re_importing_a_week_writes_byte_identical_manifest_bytes(
    zips: dict[date, Path], data_dir: Path
) -> None:
    """ac3. Nothing about *the run* is in the manifest, so two runs produce the same file."""
    for snapshot in SNAPSHOTS:
        import_week(zips[snapshot.snapshot], snapshot.snapshot)
    first = manifest_path(data_dir, LAST_WEEK).read_bytes()

    import_week(zips[LAST_WEEK], LAST_WEEK)

    assert manifest_path(data_dir, LAST_WEEK).read_bytes() == first


def test_re_importing_a_week_stores_no_further_files(zips: dict[date, Path], data_dir: Path) -> None:
    for snapshot in SNAPSHOTS:
        import_week(zips[snapshot.snapshot], snapshot.snapshot)
    before = sorted(path.name for path in (data_dir / "blobs").rglob("*") if path.is_file())

    result = import_week(zips[LAST_WEEK], LAST_WEEK, json_output=True)

    assert envelope(result)["data"]["newly_stored_blobs"] == 0
    assert sorted(path.name for path in (data_dir / "blobs").rglob("*") if path.is_file()) == before


def test_an_older_archive_is_refused_with_a_domain_failure(zips: dict[date, Path]) -> None:
    import_week(zips[LAST_WEEK], LAST_WEEK)

    result = import_week(zips[FIRST_WEEK], FIRST_WEEK)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "--allow-out-of-order" in result.stdout + result.stderr


def test_the_refusal_is_reported_in_the_json_envelope_too(zips: dict[date, Path]) -> None:
    import_week(zips[LAST_WEEK], LAST_WEEK)

    result = import_week(zips[FIRST_WEEK], FIRST_WEEK, json_output=True)

    reported = envelope(result)
    assert reported["status"] == "error"
    assert reported["error"]["code"] == "SNAPSHOT_OUT_OF_ORDER"


def test_an_older_archive_is_imported_when_the_flag_is_given(zips: dict[date, Path]) -> None:
    import_week(zips[LAST_WEEK], LAST_WEEK)

    result = import_week(zips[FIRST_WEEK], FIRST_WEEK, "--allow-out-of-order")

    assert result.exit_code == ExitCode.OK


# ------------------------------------------------------------------------------------------------
# ac6: --dry-run writes nothing
# ------------------------------------------------------------------------------------------------


def test_a_dry_run_writes_no_blob_and_no_manifest(zips: dict[date, Path], data_dir: Path) -> None:
    result = import_week(zips[FIRST_WEEK], FIRST_WEEK, "--dry-run", json_output=True)

    assert result.exit_code == ExitCode.OK
    assert envelope(result)["data"]["applied"] is False
    assert envelope(result)["data"]["manifest"] is None
    assert not manifest_path(data_dir, FIRST_WEEK).exists()
    assert not (data_dir / "blobs").exists()


def test_a_dry_run_reports_the_counts_a_real_run_would(zips: dict[date, Path]) -> None:
    planned = envelope(import_week(zips[FIRST_WEEK], FIRST_WEEK, "--dry-run", json_output=True))
    applied = envelope(import_week(zips[FIRST_WEEK], FIRST_WEEK, json_output=True))

    assert planned["data"]["counts"] == applied["data"]["counts"]


def test_a_dry_run_says_so_in_the_table(zips: dict[date, Path]) -> None:
    result = import_week(zips[FIRST_WEEK], FIRST_WEEK, "--dry-run")

    # Rich wraps the caption to the terminal width, so the text is compared without its spacing.
    unwrapped = "".join(result.stdout.split())
    assert "dryrun" in unwrapped
    assert "nothingwaswritten" in unwrapped


# ------------------------------------------------------------------------------------------------
# Which event
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("hsld26", Event.LD),
        ("hspolicy26", Event.POLICY),
        ("hspf26", Event.PF),
        ("ndtceda26", Event.POLICY),
        ("testcl26", Event.LD),
        ("mysterycl26", None),
    ],
)
def test_the_event_is_inferred_from_the_caselist_slug(slug: str, expected: Event | None) -> None:
    assert event_for_caselist(slug) == expected


def test_a_slug_this_build_does_not_know_is_refused_rather_than_guessed(
    zips: dict[date, Path],
) -> None:
    """Guessing would file every disclosure under a side the event does not debate."""
    result = invoke(
        "caselist",
        "import",
        str(zips[FIRST_WEEK]),
        "--caselist",
        "mysterycl26",
        "--snapshot",
        FIRST_WEEK.isoformat(),
    )

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "--event" in result.stdout + result.stderr


def test_an_explicit_event_overrides_the_inference(zips: dict[date, Path]) -> None:
    result = invoke(
        "caselist",
        "import",
        str(zips[FIRST_WEEK]),
        "--caselist",
        "mysterycl26",
        "--snapshot",
        FIRST_WEEK.isoformat(),
        "--event",
        "LD",
    )

    assert result.exit_code == ExitCode.OK


def test_every_known_prefix_maps_to_a_real_event() -> None:
    assert all(isinstance(event, Event) for event in EVENTS_BY_SLUG_PREFIX.values())


# ------------------------------------------------------------------------------------------------
# Bad input
# ------------------------------------------------------------------------------------------------


def test_a_snapshot_that_is_not_a_date_is_refused(zips: dict[date, Path]) -> None:
    result = invoke(
        "caselist",
        "import",
        str(zips[FIRST_WEEK]),
        "--caselist",
        SYNTHETIC_CASELIST,
        "--snapshot",
        "week three",
    )

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "--snapshot" in result.stdout + result.stderr


def test_a_source_that_does_not_exist_is_a_usage_error(tmp_path: Path) -> None:
    result = import_week(tmp_path / "no-such-archive.zip", FIRST_WEEK)

    assert result.exit_code == ExitCode.USAGE_ERROR


def test_a_file_that_is_not_an_archive_is_refused(tmp_path: Path) -> None:
    not_an_archive = tmp_path / "hsld26-0915.zip"
    not_an_archive.write_bytes(b"this is not a zip file")

    result = import_week(not_an_archive, FIRST_WEEK)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE


def test_an_archive_over_the_configured_ceiling_is_refused(
    zips: dict[date, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ac5, through the setting an operator would actually change."""
    monkeypatch.setenv("DEBATE_CASELIST__MAX_ARCHIVE_BYTES", "16")

    result = import_week(zips[FIRST_WEEK], FIRST_WEEK)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "ceiling" in (result.stdout + result.stderr)


def test_the_refusal_names_the_archive_and_no_member_of_it(
    zips: dict[date, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docs/policies/caselist-data-use.md`: no school or team code in an error message."""
    monkeypatch.setenv("DEBATE_CASELIST__MAX_ARCHIVE_BYTES", "16")

    result = import_week(zips[FIRST_WEEK], FIRST_WEEK)

    assert "Maple Grove" not in result.stdout + result.stderr
    assert "ZaLu" not in result.stdout + result.stderr

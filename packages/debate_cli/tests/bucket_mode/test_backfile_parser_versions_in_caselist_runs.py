"""`caselist runs --remote` names each backfile behind the running parser version (`v1-e40-t46`).

Through the real application and composition root, over the moto bucket of `conftest.py`'s world,
in local mode as the operator's Mac reads it. Nothing is pulled: each test writes the parsed store's
version directories straight into the bucket, one small object each, and, where it needs one, a run
record with its details. The backfiles are `caselist.backfile_caselists`, set as the environment
sets any list setting. No test here opens a socket.

Every expected line and object is written by hand from the PM's rulings of 2026-11-12: a backfile
at the reference version is not named whatever else it holds; one without is named with each
parser version it holds, newest first, or as not imported; none named is one line; and none of it
changes the exit status, the verdicts or the overdue warning.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.sync_runs import (
    BucketRunDetails,
    RestoreDetails,
    SyncRunDetails,
    SyncRunOutcome,
    SyncRunRecord,
    sync_run_details_key,
)
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.s3.version_directories import S3VersionDirectories

BUILD: Final = DOCX_PARSER_VERSION
"""This build's parser version, whatever it is: the versions below are all older than it."""
DOCX_8: Final = "2026.10.30-docx-8"
DOCX_7: Final = "2026.10.27-docx-7"
DOCX_6: Final = "2026.10.20-docx-6"
FOUR: Final = ["hspolicy25", "hsld25", "hspolicy24", "hsld24"]
RUN_STARTED: Final = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)

World = Any
"""`conftest.py`'s world: its bucket, its client and its environment."""


def backfiles(world: World, slugs: list[str]) -> None:
    world.monkeypatch.setenv("DEBATE_CASELIST__BACKFILE_CASELISTS", json.dumps(slugs))


def directory(world: World, caselist: str, version: str) -> None:
    """One version directory of `caselist`'s parsed store in the bucket: one invented object."""
    world.client.put_object(Bucket=world.bucket, Key=f"parsed/{caselist}/{version}/index.jsonl", Body=b"{}\n")


def flat(text: str) -> str:
    return " ".join(text.split())


def runs(world: World) -> tuple[dict[str, Any], str]:
    """`caselist runs --remote`'s envelope and its table's words."""
    envelope = world.run("caselist", "runs", "--remote")
    shown = world.invoke("caselist", "runs", "--remote")
    assert shown.exit_code == envelope["exit_code"], shown.output
    return envelope, flat(shown.output)


def the_state_of_2026_11_12(world: World) -> None:
    """hspolicy25 at docx-7 only; hsld25 at this build; hspolicy24 at both; hsld24 never imported."""
    backfiles(world, FOUR)
    directory(world, "hspolicy25", DOCX_7)
    directory(world, "hsld25", BUILD)
    directory(world, "hspolicy24", DOCX_7)
    directory(world, "hspolicy24", BUILD)


def test_a_backfile_without_this_builds_directory_is_named_with_what_it_holds(world: World) -> None:
    the_state_of_2026_11_12(world)

    envelope, shown = runs(world)

    assert envelope["exit_code"] == ExitCode.OK, envelope
    assert envelope["data"]["backfile_parser_versions"] == {
        "reference": {"parser_version": BUILD, "source": "this_build", "run_id": None},
        "backfiles_checked": 4,
        "named": [
            {"caselist": "hspolicy25", "imported": True, "parser_versions": [DOCX_7]},
            {"caselist": "hsld24", "imported": False, "parser_versions": []},
        ],
    }
    assert (
        f"2 of 4 backfile(s) have no parsed-store directory at parser {BUILD} (this build): "
        f"hspolicy25: holds {DOCX_7} hsld24: not imported (no parsed store)"
    ) in shown


def test_several_older_versions_are_named_newest_first(world: World) -> None:
    backfiles(world, ["hspolicy24"])
    for version in (DOCX_6, DOCX_8, DOCX_7):
        directory(world, "hspolicy24", version)

    envelope, shown = runs(world)

    [named] = envelope["data"]["backfile_parser_versions"]["named"]
    assert named["parser_versions"] == [DOCX_8, DOCX_7, DOCX_6]
    assert f"hspolicy24: holds {DOCX_8}, {DOCX_7}, {DOCX_6}" in shown


def test_one_line_says_every_backfile_is_at_the_version(world: World) -> None:
    backfiles(world, FOUR)
    directory(world, "hspolicy25", DOCX_7)
    for caselist in FOUR:
        directory(world, caselist, BUILD)

    envelope, shown = runs(world)

    assert envelope["data"]["backfile_parser_versions"]["named"] == []
    assert f"All 4 backfile(s) are at parser {BUILD} (this build)." in shown
    assert "have no parsed-store directory" not in shown


def test_the_newest_run_that_recorded_its_parser_version_is_the_reference_and_is_said(world: World) -> None:
    """The cloud run restored at docx-8: judged against that, and the line says whose it was."""
    backfiles(world, ["hspolicy25", "hsld25"])
    directory(world, "hspolicy25", DOCX_8)
    directory(world, "hsld25", BUILD)
    run_id = record_a_bucket_run(world, restored_at=DOCX_8)

    envelope, shown = runs(world)

    found = envelope["data"]["backfile_parser_versions"]
    assert found["reference"] == {"parser_version": DOCX_8, "source": "newest_run", "run_id": run_id}
    assert found["named"] == [{"caselist": "hsld25", "imported": True, "parser_versions": [BUILD]}]
    assert f"at parser {DOCX_8} (recorded by run {run_id}):" in shown


def test_the_exit_status_verdicts_and_overdue_warning_are_unchanged_by_a_backfile_named(world: World) -> None:
    """The same bucket read with no backfile configured, then with three named."""
    record_a_bucket_run(world, restored_at=BUILD)
    before, _ = runs(world)
    the_state_of_2026_11_12(world)

    after, _ = runs(world)

    assert after["data"]["backfile_parser_versions"]["named"] != []
    assert after["exit_code"] == before["exit_code"] == ExitCode.OK
    assert {key: value for key, value in after["data"].items() if key != "backfile_parser_versions"} == {
        key: value for key, value in before["data"].items() if key != "backfile_parser_versions"
    }
    assert before["data"]["backfile_parser_versions"] == {
        "reference": {"parser_version": BUILD, "source": "newest_run", "run_id": "20261111T060000Z"},
        "backfiles_checked": 0,
        "named": [],
    }


def test_without_remote_nothing_is_listed_and_the_key_is_null(world: World) -> None:
    the_state_of_2026_11_12(world)

    envelope = world.run("caselist", "runs")

    assert envelope["exit_code"] == ExitCode.OK, envelope
    assert envelope["data"]["backfile_parser_versions"] is None
    assert "backfile" not in flat(world.invoke("caselist", "runs").output)


def test_a_listing_the_bucket_refuses_is_said_and_changes_no_exit_status(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    the_state_of_2026_11_12(world)

    async def refused(self: S3VersionDirectories, caselist: str) -> tuple[str, ...]:
        raise StoreAccessDenied("ListObjectsV2", f"s3://{world.bucket}/parsed/{caselist}/")

    monkeypatch.setattr(S3VersionDirectories, "version_directories", refused)

    envelope, shown = runs(world)

    assert envelope["exit_code"] == ExitCode.OK, envelope
    assert envelope["data"]["backfile_parser_versions"] is None
    assert (
        "The backfiles' parser versions were not checked: not allowed to ListObjectsV2 "
        f"s3://{world.bucket}/parsed/hspolicy25/."
    ) in shown


def record_a_bucket_run(world: World, *, restored_at: str) -> str:
    """A completed bucket-mode run's record and details in the bucket, as the cloud run leaves them."""
    started = RUN_STARTED
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    record = SyncRunRecord(
        run_id=run_id,
        environment="dev",
        mode="run",
        started_at=started,
        finished_at=started + timedelta(minutes=20),
        outcome=SyncRunOutcome.NOTHING_NEW,
    )
    restore = RestoreDetails(started_at=started, finished_at=started, parsed_version=restored_at)
    details = SyncRunDetails(run_id=run_id, bucket_run=BucketRunDetails(restore=restore))
    world.client.put_object(
        Bucket=world.bucket, Key=record.object_key, Body=record.model_dump_json().encode()
    )
    world.client.put_object(
        Bucket=world.bucket,
        Key=sync_run_details_key(record.object_key),
        Body=details.model_dump_json().encode(),
    )
    return run_id

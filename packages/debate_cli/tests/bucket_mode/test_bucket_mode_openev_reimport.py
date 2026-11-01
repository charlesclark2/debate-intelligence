"""`caselist reimport-openev-metadata` in bucket mode, over moto and a bundle the seed wrote (`v1-e40-t34`).

Since the cutover, dev's records are the cloud run's run-state bundle, so a re-import of a release's
camp metadata has to reach it, as `caselist remove` does: take the run lock, restore, re-derive,
publish the release manifest, save the bundle, release the lock. Each test starts from the same
world: two weeks pulled on the Mac, with the invented camp file (`conftest.CAMP_FILE`), seeded into
the bucket by `caselist seed-run-state`, then the re-import run from a data directory of its own, as a
cloud task or the operator's Mac would.

The camp file went in as `openev-512-TSF-Estuary_Solvency_Advocate.docx`, camp `UNKNOWN` (the
packaged table names no `TSF`), with OpenEv's own camp word `Tamarack` on its row (`v1-e30-t31`).
The table the tests re-derive with names `TSF`, so, written by hand from that row:

| | Before | After |
|---|---|---|
| camp | `UNKNOWN` | `TSF` |
| title | the whole name, `TSF` and all | the name without the camp |
| warnings | the `UNKNOWN` warning | none |
| `openev_camp_word` | `Tamarack` | `Tamarack`, kept as written |

1 row, 1 changed, 1 title and 1 warning changed, 1 camp-file record corrected, and 1 file not held,
because a restored working copy fetches no source. Everything here is invented; no test opens a socket.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import WEEKS

import debate_core.integrations.s3 as s3_package
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist import openev_import_service
from debate_core.application.caselist.run_lock import RUN_LOCK_KEY
from debate_core.application.caselist.run_state import RUN_STATE_BUNDLE_KEY
from debate_core.integrations.local.fs_blob_store import FsSnapshotStore

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, _ = (week.snapshot for week in WEEKS)
COMMAND: Final = "caselist reimport-openev-metadata"
MANIFEST_KEY: Final = "manifests/openev/2026-policy.jsonl"
CAMP_FILE_NAME: Final = "openev-512-TSF-Estuary_Solvency_Advocate.docx"
TITLE_WORDS: Final = ("Estuary", "Solvency", "Advocate", "openev-512")

ON_A_THURSDAY: Final = datetime(2026, 10, 22, 14, 0, tzinfo=UTC)
"""09:00 in Chicago, the morning after a weekly run: outside the no-import window."""

INSIDE_THE_WINDOW: Final = {
    "Tuesday 06:00 Chicago, as it opens": datetime(2026, 10, 20, 11, 0, tzinfo=UTC),
    "Wednesday 00:30 Chicago": datetime(2026, 10, 21, 5, 30, tzinfo=UTC),
    "Wednesday 23:30 Chicago": datetime(2026, 10, 22, 4, 30, tzinfo=UTC),
}
"""Chicago is five hours behind UTC until 2026-11-01."""

OUTSIDE_THE_WINDOW: Final = {
    "Tuesday 05:59 Chicago": datetime(2026, 10, 20, 10, 59, tzinfo=UTC),
    "Thursday 00:00 Chicago, as it closes": datetime(2026, 10, 22, 5, 0, tzinfo=UTC),
}


@pytest.fixture
def seeded(world: World, tmp_path: Path) -> World:
    """The release pulled and seeded into the bucket; then a fresh data directory, on a Thursday."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    assert member_row(world)["camp"] == "UNKNOWN", "the premise: the release went in unfiled"
    table = tmp_path / "camp-aliases.yaml"
    table.write_text("camps:\n  TSF:\n    - Tamarack Summer Forum\n", encoding="utf-8")
    world.table = table
    world.clock.now = ON_A_THURSDAY
    world.use(tmp_path / "working-copy")
    return world


def reimport(world: World, *flags: str) -> dict[str, Any]:
    return world.run(
        "caselist", "reimport-openev-metadata", "--year", "2026", "--event", "policy",
        "--camp-aliases", str(world.table), *flags,
    )  # fmt: skip


def member_row(world: World) -> dict[str, Any]:
    """The release's one member row, as the bucket holds it."""
    rows = [json.loads(line) for line in world.body(MANIFEST_KEY).decode("utf-8").splitlines()]
    (row,) = [row for row in rows if row.get("kind") == "member"]
    return row


def bundle_version(world: World) -> str:
    return str(world.client.head_object(Bucket=world.bucket, Key=RUN_STATE_BUNDLE_KEY)["VersionId"])


def lock_holders(world: World) -> list[str]:
    """The command of every version of the lock object a holder wrote."""
    found: list[str] = []
    for version in world.versions(RUN_LOCK_KEY):
        body = world.client.get_object(Bucket=world.bucket, Key=RUN_LOCK_KEY, VersionId=version["VersionId"])
        holder = json.loads(body["Body"].read()).get("holder")
        if holder:
            found.append(holder["command"])
    return found


def every_version(world: World) -> list[tuple[str, str]]:
    """Every version of every key in the bucket: what a command that wrote nothing leaves as it was."""
    return sorted((str(one["Key"]), str(one["VersionId"])) for one in world.versions(""))


def refused(envelope: dict[str, Any], code: str) -> dict[str, Any]:
    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert envelope["error"]["code"] == code, envelope["error"]
    return envelope["error"]


EXPECTED_COUNTS: Final = {
    "camps_before": {"UNKNOWN": 1},
    "camps_after": {"TSF": 1},
    "rows": 1,
    "rows_changed": 1,
    "titles_changed": 1,
    "warnings_changed": 1,
    "camp_files_updated": 1,
    "camp_files_missing": 0,
    "blobs_missing": 1,
}


def counts_of(data: dict[str, Any]) -> dict[str, Any]:
    return {name: data[name] for name in EXPECTED_COUNTS}


# ------------------------------------------------------------------------------------------------
# The dry run, by default
# ------------------------------------------------------------------------------------------------


def test_reimport_dry_run_restores_the_buckets_copy_prints_the_counts_and_writes_nothing_to_the_bucket(
    seeded: World,
) -> None:
    before = every_version(seeded)

    planned = reimport(seeded)

    assert planned["exit_code"] == ExitCode.OK, planned
    data = planned["data"]
    assert counts_of(data) == EXPECTED_COUNTS
    assert (data["applied"], data["bucket_mode"], data["manifest_published"], data["bundle_saved"]) == (
        False,
        True,
        None,
        False,
    )
    assert data["execute_command"] == (
        "DEBATE_ENV=dev debate-research caselist reimport-openev-metadata --year 2026 --event policy "
        "--execute"
    )
    assert every_version(seeded) == before, "not one object or version written, the lock's included"
    assert COMMAND not in lock_holders(seeded)
    assert (seeded.data_dir / "debate.sqlite3").is_file(), "the working copy was restored from the bundle"


def test_reimport_dry_run_names_camps_and_counts_and_no_title_lab_or_path(seeded: World) -> None:
    result = seeded.invoke(
        "caselist", "reimport-openev-metadata", "--year", "2026", "--event", "policy",
        "--camp-aliases", str(seeded.table),
    )  # fmt: skip

    assert result.exit_code == ExitCode.OK, result.output
    text = " ".join(result.output.replace("│", " ").split())
    assert "TSF" in text and "UNKNOWN" in text
    assert "1 title(s) and 1 warning(s) changed" in text
    assert "DRY RUN" in text and "the run lock was not taken" in text
    assert "--execute" in text
    assert all(word not in text for word in TITLE_WORDS), text
    assert str(seeded.root) not in text


# ------------------------------------------------------------------------------------------------
# The run
# ------------------------------------------------------------------------------------------------


def test_reimport_execute_takes_the_lock_publishes_the_manifest_and_saves_the_bundle(seeded: World) -> None:
    bundle_before = bundle_version(seeded)
    row_before = member_row(seeded)

    done = reimport(seeded, "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    data = done["data"]
    assert counts_of(data) == EXPECTED_COUNTS
    assert (data["applied"], data["manifest_published"], data["bundle_saved"]) == (True, "uploaded", True)
    assert data["next_step"].startswith("The next cloud run's parse stage carries the camps")
    row = member_row(seeded)
    assert (row["camp"], row["warnings"]) == ("TSF", [])
    assert row["openev_camp_word"] == "Tamarack", "OpenEv's own word is kept as written (v1-e30-t31)"
    unchanged = ("sha256", "path", "byte_size", "classification", "openev_id", "upstream_path_sha256")
    assert {name: row[name] for name in unchanged} == {name: row_before[name] for name in unchanged}
    assert bundle_version(seeded) != bundle_before, "the bundle was saved again"
    assert COMMAND in lock_holders(seeded)
    assert seeded.lock()["state"] == "free"


def test_reimport_execute_leaves_the_bundle_holding_the_refiled_manifest_and_records(
    seeded: World, tmp_path: Path
) -> None:
    """Read back from another working copy: its restore is of the bundle the run saved."""
    assert reimport(seeded, "--execute")["exit_code"] == ExitCode.OK
    seeded.use(tmp_path / "another-copy")

    again = reimport(seeded)

    assert again["exit_code"] == ExitCode.OK, again
    data = again["data"]
    assert (data["camps_before"], data["camps_after"]) == ({"TSF": 1}, {"TSF": 1})
    assert (data["rows_changed"], data["camp_files_updated"], data["manifest_changed"]) == (0, 0, False)
    assert data["execute_command"] is None


def test_reimport_execute_a_second_time_publishes_and_saves_nothing(seeded: World) -> None:
    assert reimport(seeded, "--execute")["exit_code"] == ExitCode.OK
    before = bundle_version(seeded)

    again = reimport(seeded, "--execute")

    assert again["exit_code"] == ExitCode.OK, again
    data = again["data"]
    assert (data["rows_changed"], data["manifest_published"], data["bundle_saved"]) == (0, None, False)
    assert data["next_step"] is None
    assert bundle_version(seeded) == before
    assert seeded.lock()["state"] == "free"


class RawReads:
    """Every object any client of the command reads under `raw/`: a source file's bytes."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        build = s3_package.build_s3_client

        def built(**arguments: Any) -> Any:
            client = build(**arguments)

            def record(params: dict[str, Any], model: Any, **_: object) -> None:
                key = str(params.get("Key", ""))
                if model.name == "GetObject" and key.startswith("raw/"):
                    self.keys.append(key)

            client.meta.events.register("before-parameter-build.s3", record)
            return client

        monkeypatch.setattr(s3_package, "build_s3_client", built)


def test_reimport_reads_no_files_bytes_here_or_in_the_bucket(
    seeded: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It asks only whether each digest is held, as `v1-e30-t32`'s refile test asks of a local copy."""
    reads = RawReads()
    reads.install(monkeypatch)

    async def refused_read(self: FsSnapshotStore, key: str) -> bytes:
        raise AssertionError("the re-import read a file's bytes")

    monkeypatch.setattr(FsSnapshotStore, "get", refused_read)

    done = reimport(seeded, "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    assert reads.keys == [], "no source fetched from the bucket"
    assert done["data"]["blobs_missing"] == 1, "counted as not held, never fetched"
    held = seeded.data_dir / "blobs"
    assert not held.exists() or not any(path.is_file() for path in held.rglob("*"))


# ------------------------------------------------------------------------------------------------
# Refusals
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("moment", sorted(INSIDE_THE_WINDOW), ids=str)
def test_reimport_inside_the_no_import_window_is_refused_dry_or_not_before_anything_is_restored(
    seeded: World, moment: str
) -> None:
    seeded.clock.now = INSIDE_THE_WINDOW[moment]
    before = every_version(seeded)

    for flags in ((), ("--execute",)):
        error = refused(reimport(seeded, *flags), "INSIDE_NO_IMPORT_WINDOW")
        assert "it closes at 2026-10-22T05:00:00+00:00" in error["message"]

    assert every_version(seeded) == before
    assert not (seeded.data_dir / "debate.sqlite3").exists(), "nothing was restored"


@pytest.mark.parametrize("moment", sorted(OUTSIDE_THE_WINDOW), ids=str)
def test_reimport_just_outside_the_window_runs(seeded: World, moment: str) -> None:
    seeded.clock.now = OUTSIDE_THE_WINDOW[moment]

    assert reimport(seeded, "--execute")["exit_code"] == ExitCode.OK


def a_prod_profile(world: World) -> None:
    """Prod, in bucket mode, over the same moto bucket: the lock's home is still dev's."""
    profiles = Path(world.root / "profiles")
    (profiles / "prod.toml").write_text(
        f'[storage]\ndata_dir = "{world.root / "prod-data"}"\n'
        f'[storage.s3]\nbucket = "{world.bucket}"\nregion = "us-east-1"\n'
        'aws_profile = "debate-dev-evidence"\n',
        encoding="utf-8",
    )
    world.monkeypatch.setenv("DEBATE_ENV", "prod")
    world.monkeypatch.delenv("DEBATE_STORAGE__DATA_DIR")
    world.monkeypatch.delenv("DEBATE_CASELIST__API_BASE_URL")  # prod refuses an override of the site
    world.data_dir = world.root / "prod-data"


def test_reimport_execute_in_prod_without_confirm_prod_is_refused_before_anything(seeded: World) -> None:
    a_prod_profile(seeded)
    before = every_version(seeded)

    error = refused(reimport(seeded, "--execute"), "CONFIRMATION_REQUIRED")

    assert "--confirm-prod" in error["message"]
    assert every_version(seeded) == before
    assert not (seeded.data_dir / "debate.sqlite3").exists(), "nothing was restored"
    # With the flag it goes on, to the lock, whose home is dev's: the flag was what stopped it.
    refused(reimport(seeded, "--execute", "--confirm-prod"), "RUN_LOCK_WRONG_HOME")


def test_reimport_is_refused_while_another_runner_holds_the_lock(seeded: World) -> None:
    now = seeded.clock.now
    seeded.client.put_object(
        Bucket=seeded.bucket,
        Key=RUN_LOCK_KEY,
        Body=json.dumps(
            {
                "format_version": 1,
                "home_environment": "dev",
                "state": "held",
                "holder": {
                    "kind": "cloud",
                    "run_id": "20261022T135500Z",
                    "task": None,
                    "command": "caselist pull",
                },
                "acquired_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "renewed_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lease_expires_at": (now + timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "took_over_from": None,
            }
        ).encode(),
    )
    before = every_version(seeded)

    refused(reimport(seeded, "--execute"), "RUN_LOCK_HELD")

    assert every_version(seeded) == before
    assert not (seeded.data_dir / "debate.sqlite3").exists(), "nothing was restored"


def test_reimport_after_the_run_home_moved_is_refused_dry_or_not_naming_the_move(seeded: World) -> None:
    assert seeded.run("caselist", "move-run-home", "--execute")["exit_code"] == ExitCode.OK
    before = every_version(seeded)

    for flags in ((), ("--execute",)):
        error = refused(reimport(seeded, *flags), "RUN_HOME_MOVED")
        assert error["message"].startswith("the weekly run now runs from prod: ")

    assert every_version(seeded) == before


def test_reimport_in_a_bucket_never_seeded_is_refused_dry_or_not(world: World) -> None:
    world.mode("bucket")
    world.clock.now = ON_A_THURSDAY

    for flags in ((), ("--execute",)):
        envelope = world.run(
            "caselist", "reimport-openev-metadata", "--year", "2026", "--event", "policy", *flags
        )
        refused(envelope, "RUN_STATE_NOT_SEEDED")

    assert world.object_keys() == set()


def test_reimport_refuses_a_bundle_rewritten_since_its_restore_and_publishes_nothing(
    seeded: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between the restore and the publish, as a removal would rewrite it: the removal's bundle stays."""
    rederive = openev_import_service.OpenEvImportService.reimport_metadata

    async def then_rewritten(self: Any, **arguments: Any) -> Any:
        report = await rederive(self, **arguments)
        seeded.client.copy_object(
            Bucket=seeded.bucket,
            Key=RUN_STATE_BUNDLE_KEY,
            CopySource={"Bucket": seeded.bucket, "Key": RUN_STATE_BUNDLE_KEY},
            Metadata={"rewritten": "by a removal"},
            MetadataDirective="REPLACE",
        )
        return report

    monkeypatch.setattr(openev_import_service.OpenEvImportService, "reimport_metadata", then_rewritten)

    refused(reimport(seeded, "--execute"), "BUNDLE_CHANGED_SINCE_RESTORE")

    assert member_row(seeded)["camp"] == "UNKNOWN", "nothing published"
    head = seeded.client.head_object(Bucket=seeded.bucket, Key=RUN_STATE_BUNDLE_KEY)
    assert head["Metadata"] == {"rewritten": "by a removal"}
    assert seeded.lock()["state"] == "free"


def test_reimport_dry_run_and_execute_together_is_a_usage_error(seeded: World) -> None:
    result = seeded.invoke(
        "caselist",
        "reimport-openev-metadata",
        "--year",
        "2026",
        "--event",
        "policy",
        "--dry-run",
        "--execute",
    )

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output

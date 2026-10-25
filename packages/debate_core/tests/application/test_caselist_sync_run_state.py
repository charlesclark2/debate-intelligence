"""The pieces of a bucket-mode run's state, one at a time (`v1-e40-t04`, ADR-0020 (3)).

The whole run is tested through the command, in `debate_cli/tests/bucket_mode/`. What is here is
each rule on its own, against moto's S3 and a temporary data directory:

* the run-state bundle holds the manifests and a compacted database, and nothing else unpacks;
* a state file this machine no longer holds is saved as an empty object, and restored as absent;
* the bundle is saved only when every local manifest is confirmed in the bucket, and never while
  one is a manifest the publisher withholds, in the publisher's words;
* `store sync` skips `manifests/_run-state/` either way, on either side;
* the run monitor's notifications for a lock another runner held, a lease lost and one taken over.
"""

from __future__ import annotations

import asyncio
import functools
import io
import sqlite3
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from debate_core.application.caselist.bucket_run import BucketRun
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import withheld_manifest_reason
from debate_core.application.caselist.run_lock import RunLockHeld, RunLockLost
from debate_core.application.caselist.run_state import RunState, RunStateWithheld, state_key
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    SyncDirection,
    SyncJournal,
    SyncKeyspace,
)
from debate_core.application.ports.run_state import RUN_STATE_BUNDLE_KEY, RunStateBundleUnreadable
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.sync_runs import (
    ANOTHER_RUN_HELD_THE_LOCK_TITLE,
    LOCK_BANNER_WORDS,
    RUN_LOCK_LOST_TITLE,
    TOOK_OVER_THE_LOCK_TITLE,
    BucketRunDetails,
    SyncRunDetails,
    banner_words,
    notifications_for,
    record_for_failure,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.run_state_files import LocalRunStateFiles
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.clock_and_ids import FixedClock
from debate_core.testing.fakes.suppression import empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

MANIFEST: Final = "manifests/testcl26/2026-09-15.jsonl"
SOURCE: Final = "ab" * 32
ROW: Final = (
    '{"kind": "member", "path": "Fictional School/AB/round-1.docx", "sha256": "' + SOURCE + '", '
    '"byte_size": 3, "classification": "NEW", "source_format": "docx"}\n'
)
NOW: Final = datetime(2026, 10, 21, 11, 0, 5, tzinfo=UTC)


def evidence_at(directory: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(directory)
    blobs = FsEvidenceObjectStore(directory, subdirectory=BLOB_DIRECTORY.parent)
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def a_data_directory(root: Path, *, rows: str = ROW) -> Path:
    data_dir = root / "data"
    manifest = data_dir / "objects" / MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(rows, encoding="utf-8")
    database = sqlite3.connect(data_dir / "debate.sqlite3")
    database.execute("create table kept (value text)")
    database.executemany("insert into kept values (?)", [(f"{SOURCE}-{i}" * 20,) for i in range(400)])
    database.commit()
    database.execute("delete from kept where rowid > 1")
    database.commit()
    database.close()
    return data_dir


def run_state(data_dir: Path, client: S3Client, bucket: str, *, suppression: object = None) -> RunState:
    return RunState(
        bucket=S3EvidenceObjectStore(bucket=bucket, client=client),
        files=LocalRunStateFiles(data_dir),
        local=evidence_at(data_dir),
        staged=evidence_at,
        withheld=lambda evidence: functools.partial(withheld_manifest_reason, evidence),
        suppression=suppression or empty_suppression_list(),  # pyright: ignore[reportArgumentType]
        data_dir=data_dir,
        clock=lambda: NOW,
    )


# ------------------------------------------------------------------------------------------------
# The bundle's files
# ------------------------------------------------------------------------------------------------


def test_a_bundle_holds_the_manifests_and_a_compacted_database_and_nothing_else(tmp_path: Path) -> None:
    data_dir = a_data_directory(tmp_path)
    assert f"{SOURCE}-399".encode() in (data_dir / "debate.sqlite3").read_bytes(), "the premise: a free page"
    bundle = tmp_path / "bundle.tar.gz"

    LocalRunStateFiles(data_dir).pack(bundle)

    with tarfile.open(bundle, "r:gz") as archive:
        assert sorted(archive.getnames()) == ["debate.sqlite3", f"objects/{MANIFEST}"]
        database = archive.extractfile("debate.sqlite3")
        assert database is not None
        assert f"{SOURCE}-399".encode() not in database.read(), "a deleted row is not in the bundle"


def test_installing_a_bundle_replaces_the_manifests_and_database_whole_and_drops_an_old_wal(
    tmp_path: Path,
) -> None:
    source = a_data_directory(tmp_path / "from")
    bundle = tmp_path / "bundle.tar.gz"
    LocalRunStateFiles(source).pack(bundle)
    target = tmp_path / "to"
    stale = target / "objects" / "manifests" / "testcl26" / "2026-01-01.jsonl"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")
    (target / "debate.sqlite3-wal").write_bytes(b"an old log")
    staging = tmp_path / "staging"
    staging.mkdir()
    files = LocalRunStateFiles(target)

    files.unpack(bundle, staging)
    files.install(staging)

    assert not stale.exists()
    assert (target / "objects" / MANIFEST).read_text(encoding="utf-8") == ROW
    assert not (target / "debate.sqlite3-wal").exists()
    assert sqlite3.connect(target / "debate.sqlite3").execute("select count(*) from kept").fetchone() == (1,)


def a_tar(tmp_path: Path, name: str, *, link: bool = False) -> Path:
    bundle = tmp_path / f"{len(list(tmp_path.iterdir()))}.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        member = tarfile.TarInfo(name)
        if link:
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            archive.addfile(member)
        else:
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        database = tarfile.TarInfo("debate.sqlite3")
        database.size = 1
        archive.addfile(database, io.BytesIO(b"x"))
    return bundle


@pytest.mark.parametrize(
    ("name", "link"),
    [
        ("../outside.jsonl", False),
        ("/etc/cron.d/x", False),
        ("objects/other/thing.json", False),
        ("caselist-sync-runs.jsonl", False),
        (f"objects/{MANIFEST}", True),
    ],
)
def test_a_bundle_holding_anything_but_manifests_and_the_database_unpacks_nothing(
    tmp_path: Path, name: str, link: bool
) -> None:
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    bundle = a_tar(bundles, name, link=link)
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(RunStateBundleUnreadable):
        LocalRunStateFiles(tmp_path / "data").unpack(bundle, staging)

    assert list(staging.iterdir()) == []


def test_bytes_that_are_not_a_bundle_are_refused(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    bundle.write_bytes(b"not a gzip")
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(RunStateBundleUnreadable):
        LocalRunStateFiles(tmp_path).unpack(bundle, staging)


# ------------------------------------------------------------------------------------------------
# State files and the bundle's save
# ------------------------------------------------------------------------------------------------


def test_a_state_file_this_machine_removed_is_saved_empty_and_restored_absent(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Nothing here may delete, so the pending-work file's removal is recorded as an empty object."""
    data_dir = a_data_directory(tmp_path)
    state = run_state(data_dir, s3_client, evidence_bucket)
    pending = data_dir / "caselist-sync-pending.json"
    pending.write_text('{"publish": [{"caselist": "testcl26", "snapshot": "2026-09-15"}]}', encoding="utf-8")
    asyncio.run(state.save_state_file(pending.name))
    pending.unlink()

    asyncio.run(state.save_state_file(pending.name))

    stored = s3_client.get_object(Bucket=evidence_bucket, Key=state_key(pending.name))["Body"].read()
    assert stored == b""
    pending.write_text("left from an older copy", encoding="utf-8")
    asyncio.run(state._restore_state_files())  # pyright: ignore[reportPrivateUsage]
    assert not pending.exists()


def test_the_bundle_is_not_saved_while_a_manifest_is_unconfirmed_in_the_bucket(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = a_data_directory(tmp_path)
    state = run_state(data_dir, s3_client, evidence_bucket)

    unsaved = asyncio.run(state.save_bundle())

    assert not unsaved.saved
    assert "1 manifest(s) on this machine are not yet confirmed" in unsaved.reason
    assert "Contents" not in s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix=RUN_STATE_BUNDLE_KEY)

    s3_client.put_object(
        Bucket=evidence_bucket, Key=MANIFEST, Body=b"other bytes\n", Metadata={"sha256": "0" * 64}
    )
    assert not asyncio.run(state.save_bundle()).saved, "the bucket holds other bytes under the key"

    asyncio.run(
        S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client).put_file(
            MANIFEST, data_dir / "objects" / MANIFEST
        )
    )
    saved = asyncio.run(state.save_bundle())
    assert saved.saved, saved.reason


def test_a_bundle_holding_a_manifest_the_publisher_withholds_is_not_saved_in_the_publishers_words(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = a_data_directory(tmp_path)
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=SOURCE,
        recorded_at=datetime(2026, 10, 20, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )
    suppression = empty_suppression_list()
    asyncio.run(suppression.append([entry]))
    state = run_state(data_dir, s3_client, evidence_bucket, suppression=suppression)

    with pytest.raises(RunStateWithheld) as withheld:
        asyncio.run(state.save_bundle())

    assert SOURCE in str(withheld.value)
    assert "re-run `caselist remove`" in str(withheld.value)
    assert "Contents" not in s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix=RUN_STATE_BUNDLE_KEY)


# ------------------------------------------------------------------------------------------------
# store sync
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("direction", list(SyncDirection))
def test_store_sync_skips_the_run_state_bundle_either_way_on_either_side(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, direction: SyncDirection
) -> None:
    data_dir = tmp_path / "evidence"
    local_only = data_dir / "objects" / "manifests" / "_run-state" / "run-state.tar.gz"
    local_only.parent.mkdir(parents=True)
    local_only.write_bytes(b"this machine's")
    s3_client.put_object(
        Bucket=evidence_bucket, Key="manifests/_run-state/older.tar.gz", Body=b"the bucket's"
    )
    objects = FsEvidenceObjectStore(data_dir)
    service = EvidenceSyncService(
        suppression=empty_suppression_list(),
        keyspaces=(
            SyncKeyspace(
                name="objects",
                local=objects,
                remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
                local_path_for=objects.path_for,
            ),
        ),
        journal=SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket),
        remote_name=evidence_bucket,
        clock=FixedClock(),
    )

    plan = asyncio.run(service.plan(direction=direction))

    decided = {planned.remote_key: (str(planned.action), planned.skip_kind) for planned in plan.objects}
    assert decided == {
        "manifests/_run-state/run-state.tar.gz": ("skipped", "run_state"),
        "manifests/_run-state/older.tar.gz": ("skipped", "run_state"),
    }


# ------------------------------------------------------------------------------------------------
# What the coach is told
# ------------------------------------------------------------------------------------------------


def a_refusal(error: BaseException, bucket: BucketRunDetails) -> list[object]:
    record = record_for_failure(
        error, run_id="20261021T110005Z", started_at=NOW, finished_at=NOW, environment="dev", mode="run"
    )
    details = SyncRunDetails(run_id="20261021T110005Z", failure_codes=("X",), bucket_run=bucket)
    return [record, details]


def test_a_run_another_held_the_lock_against_is_announced_as_skipped_naming_that_runner_and_its_lease() -> (
    None
):
    record, details = a_refusal(
        RunLockHeld(holder=None, lease_expires_at=None),
        BucketRunDetails(held_by="cloud run 20261021T104500Z (`caselist pull`)", held_until=NOW),
    )

    [sent] = notifications_for(record, details, aws_login_command="aws sso login", credentials_expired=False)  # pyright: ignore[reportArgumentType]

    assert sent.title == ANOTHER_RUN_HELD_THE_LOCK_TITLE
    assert (
        "cloud run 20261021T104500Z (`caselist pull`), its lease until 2026-10-21T11:00:05Z" in sent.message
    )
    assert banner_words(record, details) == LOCK_BANNER_WORDS  # pyright: ignore[reportArgumentType]


def test_a_run_whose_lease_was_taken_is_announced_as_lock_lost() -> None:
    record, details = a_refusal(RunLockLost(), BucketRunDetails(lock_lost=True))

    [sent] = notifications_for(record, details, aws_login_command="aws sso login", credentials_expired=False)  # pyright: ignore[reportArgumentType]

    assert sent.title == RUN_LOCK_LOST_TITLE
    assert "RUN_LOCK_LOST" in sent.message


def test_a_run_that_took_over_an_expired_lease_says_so() -> None:
    from debate_core.application.sync_runs import SyncRunOutcome, SyncRunRecord

    record = SyncRunRecord(
        run_id="20261021T110005Z",
        environment="dev",
        mode="run",
        started_at=NOW,
        finished_at=NOW,
        outcome=SyncRunOutcome.COMPLETED,
    )
    taken = "took over the bucket's run lock from mac run 20261021T104500Z (`caselist pull`)"
    details = SyncRunDetails(run_id="20261021T110005Z", bucket_run=BucketRunDetails(took_over=taken))

    sent = notifications_for(record, details, aws_login_command="aws sso login", credentials_expired=False)

    assert [one.title for one in sent] == [TOOK_OVER_THE_LOCK_TITLE]
    assert taken in sent[0].message


def test_a_stop_cancels_the_run_once_and_a_cancellation_nobody_asked_for_stays_one() -> None:
    from debate_core.application.caselist.run_lock import BucketWriteGuard, RunTerminated
    from debate_core.application.settings import RunStateMode

    run = BucketRun(
        guard=BucketWriteGuard(mode=RunStateMode.BUCKET, lock=None), lock=None, state=None, parsed_version="v"
    )
    cancelled = asyncio.CancelledError()
    assert run.as_terminated(cancelled) is cancelled

    async def stopped() -> BaseException:
        task = asyncio.current_task()
        assert task is not None
        run.watching(task)  # pyright: ignore[reportArgumentType]
        run.terminate()
        run.terminate()
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError as stop:
            return run.as_terminated(stop)
        raise AssertionError("not cancelled")

    assert isinstance(asyncio.run(stopped()), RunTerminated)

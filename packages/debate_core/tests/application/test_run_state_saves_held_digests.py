"""A save of the run-state bundle first gives the bucket the held uploads the working copy recorded (`v1-e40-t12`).

An import that refuses an upload at a path a removal holds records it in the working copy's
`held-digests.jsonl` (`v1-e30-t23`). A cloud task's working copy vanishes when the task stops, so in
bucket mode :meth:`RunState.save_bundle` first appends to `manifests/_suppression/held-digests.jsonl`
the lines the bucket lacks, under the lease every save site holds (the PM's rulings of 2026-10-27):

* before the bundle, so no bundle that records a snapshot is in the bucket without the held uploads
  its import refused;
* whether or not the bundle is then saved: an unconfirmed manifest or a withheld one stops the
  bundle, never the record;
* only what the bucket lacks, appended: a line already there, a removal's own among them, stays
  byte for byte, and no line is written twice.

Against moto's S3 and a temporary data directory, as `test_caselist_sync_run_state.py` tests the
bundle's other rules.
"""

from __future__ import annotations

import asyncio
import functools
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import withheld_manifest_reason
from debate_core.application.caselist.run_state import RunState, RunStateWithheld
from debate_core.application.caselist.suppression import (
    HELD_DIGESTS_KEY,
    SUPPRESSION_LIST_KEY,
    ObjectStoreAppendOnlyRecord,
    RecordedSuppressionList,
    record_held_digests,
)
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.application.ports.run_state import RUN_STATE_BUNDLE_KEY
from debate_core.application.ports.suppression import (
    HeldDigestEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.run_state_files import LocalRunStateFiles
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

MANIFEST: Final = "manifests/testcl26/2026-09-22.jsonl"
SOURCE: Final = "ab" * 32
ROW: Final = (
    '{"kind": "member", "path": "Fictional School/AB/round-1.docx", "sha256": "' + SOURCE + '", '
    '"byte_size": 3, "classification": "NEW", "source_format": "docx"}\n'
)
NOW: Final = datetime(2026, 10, 28, 11, 0, 5, tzinfo=UTC)

HELD_IN_THE_TASK: Final = HeldDigestEntry(sha256="cd" * 32, disclosure="ef" * 32, request_id="RM-2026-07")
"""What the cloud task's import refused at a held path, recorded in its working copy alone."""
A_REMOVALS_LINE: Final = HeldDigestEntry(sha256="12" * 32, disclosure="34" * 32, request_id="RM-2026-05")
"""A line a removal already gave the bucket, from the Mac's own import, which this copy never saw."""


class RecordingStore(S3EvidenceObjectStore):
    """The bucket's everyday adapter, noting the key of every upload in order."""

    def __init__(self, *, bucket: str, client: S3Client) -> None:
        super().__init__(bucket=bucket, client=client)
        self.puts: list[ObjectKey] = []

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        self.puts.append(key)
        return await super().put_file(key, source)


def evidence_at(directory: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(directory)
    blobs = FsEvidenceObjectStore(directory, subdirectory=BLOB_DIRECTORY.parent)
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def a_working_copy(root: Path) -> Path:
    """A data directory with one manifest and the held upload its import recorded locally."""
    data_dir = root / "cloud-task"
    manifest = data_dir / "objects" / MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(ROW, encoding="utf-8")
    asyncio.run(record_held_digests(RecordedSuppressionList(local_suppression_list_file(data_dir)), [HELD_IN_THE_TASK]))
    return data_dir


def run_state(data_dir: Path, store: S3EvidenceObjectStore) -> RunState:
    """A run's state over `data_dir`, with the suppression list over its copy and the bucket's, as the container builds it."""
    return RunState(
        bucket=store,
        files=LocalRunStateFiles(data_dir),
        local=evidence_at(data_dir),
        staged=evidence_at,
        withheld=lambda evidence: functools.partial(withheld_manifest_reason, evidence),
        suppression=RecordedSuppressionList(
            local_suppression_list_file(data_dir), ObjectStoreAppendOnlyRecord(store, SUPPRESSION_LIST_KEY)
        ),
        data_dir=data_dir,
        clock=lambda: NOW,
    )


def confirm_the_manifest(data_dir: Path, store: S3EvidenceObjectStore) -> None:
    asyncio.run(store.put_file(MANIFEST, data_dir / "objects" / MANIFEST))


def held_in_the_bucket(client: S3Client, bucket: str) -> bytes | None:
    listed = client.list_objects_v2(Bucket=bucket, Prefix=HELD_DIGESTS_KEY)
    if "Contents" not in listed:
        return None
    return client.get_object(Bucket=bucket, Key=HELD_DIGESTS_KEY)["Body"].read()


def line(entry: HeldDigestEntry) -> bytes:
    return f"{entry.to_line()}\n".encode()


def test_a_saved_bundle_gives_the_bucket_the_held_uploads_the_working_copy_recorded_before_the_bundle(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = a_working_copy(tmp_path)
    store = RecordingStore(bucket=evidence_bucket, client=s3_client)
    confirm_the_manifest(data_dir, store)
    store.puts.clear()

    saved = asyncio.run(run_state(data_dir, store).save_bundle())

    assert saved.saved, saved.reason
    assert held_in_the_bucket(s3_client, evidence_bucket) == line(HELD_IN_THE_TASK)
    assert store.puts == [HELD_DIGESTS_KEY, RUN_STATE_BUNDLE_KEY], "the held uploads first, then the bundle"


def test_the_held_upload_is_appended_and_a_removals_line_already_in_the_bucket_stays_byte_for_byte(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = a_working_copy(tmp_path)
    store = RecordingStore(bucket=evidence_bucket, client=s3_client)
    confirm_the_manifest(data_dir, store)
    before = line(A_REMOVALS_LINE)
    s3_client.put_object(Bucket=evidence_bucket, Key=HELD_DIGESTS_KEY, Body=before)

    asyncio.run(run_state(data_dir, store).save_bundle())

    after = held_in_the_bucket(s3_client, evidence_bucket)
    assert after == before + line(HELD_IN_THE_TASK), "appended after the removal's line, which is untouched"
    versions = s3_client.list_object_versions(Bucket=evidence_bucket, Prefix=HELD_DIGESTS_KEY)["Versions"]
    assert len(versions) == 2, "one append: the removal's version is kept beneath it"


def test_a_line_the_bucket_already_holds_is_not_written_again(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = a_working_copy(tmp_path)
    store = RecordingStore(bucket=evidence_bucket, client=s3_client)
    confirm_the_manifest(data_dir, store)
    held = line(A_REMOVALS_LINE) + line(HELD_IN_THE_TASK)
    s3_client.put_object(Bucket=evidence_bucket, Key=HELD_DIGESTS_KEY, Body=held)
    store.puts.clear()

    asyncio.run(run_state(data_dir, store).save_bundle())

    assert held_in_the_bucket(s3_client, evidence_bucket) == held
    assert HELD_DIGESTS_KEY not in store.puts, "nothing the bucket lacks, so nothing written"


def test_a_bundle_left_unsaved_for_an_unconfirmed_manifest_still_leaves_the_held_upload_in_the_bucket(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = a_working_copy(tmp_path)
    store = RecordingStore(bucket=evidence_bucket, client=s3_client)

    unsaved = asyncio.run(run_state(data_dir, store).save_bundle())

    assert not unsaved.saved
    assert "not yet confirmed" in unsaved.reason
    assert held_in_the_bucket(s3_client, evidence_bucket) == line(HELD_IN_THE_TASK)
    assert RUN_STATE_BUNDLE_KEY not in store.puts


def test_a_bundle_the_publisher_withholds_still_leaves_the_held_upload_in_the_bucket(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = a_working_copy(tmp_path)
    store = RecordingStore(bucket=evidence_bucket, client=s3_client)
    confirm_the_manifest(data_dir, store)
    state = run_state(data_dir, store)
    suppressed = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=SOURCE,
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-07",
    )
    asyncio.run(RecordedSuppressionList(local_suppression_list_file(data_dir)).append([suppressed]))

    with pytest.raises(RunStateWithheld):
        asyncio.run(state.save_bundle())

    assert held_in_the_bucket(s3_client, evidence_bucket) == line(HELD_IN_THE_TASK)
    assert RUN_STATE_BUNDLE_KEY not in store.puts


def test_a_working_copy_that_held_nothing_creates_no_held_digest_record_in_the_bucket(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = tmp_path / "cloud-task"
    manifest = data_dir / "objects" / MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(ROW, encoding="utf-8")
    store = RecordingStore(bucket=evidence_bucket, client=s3_client)
    confirm_the_manifest(data_dir, store)

    assert asyncio.run(run_state(data_dir, store).save_bundle()).saved

    assert held_in_the_bucket(s3_client, evidence_bucket) is None

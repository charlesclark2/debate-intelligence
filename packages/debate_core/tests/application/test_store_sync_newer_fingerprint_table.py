"""`store sync` never moves an occurrence table over one a newer build stamped (`v1-e34-t29`).

`parsed/` is one of the bucket's named-object prefixes, so `store sync --pull` copies the parsed
store into `<data_dir>/objects/parsed/` and `--push` sends that copy back, overwriting what differs.
A machine that pulled before a newer build published would put the older clusters back. Before an
`occurrences.jsonl` under `parsed/` moves, the sync asks
:func:`~debate_core.application.caselist.occurrence_table_guard.refuse_newer_table` of the copy a
push sends and of the copy either way overwrites:

* a push of a table stamped newer than the build, or over the bucket's newer table, fails that
  object with both versions named, and the bucket keeps its bytes;
* a pull over this machine's newer copy fails that object, and the copy keeps its bytes;
* an equal or older stamp moves as before, and so does any other object under `parsed/`;
* the sync takes its answer from the one rule.

The tables are synthetic lines with synthetic versions: a sync reads only their stamps.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from debate_core.application.caselist import occurrence_table_guard
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    SyncAction,
    SyncDirection,
    SyncJournal,
    SyncKeyspace,
    SyncReport,
)
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore
from debate_core.testing.fakes import FixedClock, empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
OLDER: Final = "synthetic-fingerprint-v6"
TABLE: Final = "parsed/testcl26/2099.01.01-docx-9/occurrences.jsonl"
INDEX: Final = "parsed/testcl26/2099.01.01-docx-9/index.jsonl"
MANIFEST: Final = "manifests/testcl26/2026-09-15.jsonl"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def always(newer: bool) -> Callable[[str, str], bool]:
    """A comparison that answers `newer` for every pair of versions."""

    def answer(stamped: str, build: str) -> bool:
        return newer

    return answer


@pytest.fixture(autouse=True)
def synthetic_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(occurrence_table_guard, "FINGERPRINT_VERSION", BUILD)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "evidence"


@pytest.fixture
def service(data_dir: Path, evidence_bucket: str, s3_client: S3Client) -> EvidenceSyncService:
    """The named-object keyspace as the composition root builds it: `<data_dir>/objects/<key>`."""
    local = FsEvidenceObjectStore(data_dir)
    return EvidenceSyncService(
        suppression=empty_suppression_list(),
        keyspaces=(
            SyncKeyspace(
                name="objects",
                local=local,
                remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
                local_path_for=local.path_for,
            ),
        ),
        journal=SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket),
        remote_name=evidence_bucket,
        clock=FixedClock(),
    )


def table(stamp: str, rows: int = 2) -> bytes:
    """An occurrence table's lines, as far as a sync reads them."""
    return b"".join(
        json.dumps({"record": "occurrence", "fingerprint_version": stamp, "row": row}).encode() + b"\n"
        for row in range(rows)
    )


def write_local(data_dir: Path, key: str, body: bytes) -> None:
    path = data_dir / "objects" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def read_local(data_dir: Path, key: str) -> bytes:
    return (data_dir / "objects" / key).read_bytes()


def put_remote(client: S3Client, bucket: str, key: str, body: bytes) -> None:
    client.put_object(
        Bucket=bucket, Key=key, Body=body, Metadata={SHA256_METADATA_NAME: hashlib.sha256(body).hexdigest()}
    )


def read_remote(client: S3Client, bucket: str, key: str) -> bytes:
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


async def sync(service: EvidenceSyncService, direction: SyncDirection) -> SyncReport:
    return await service.execute(await service.plan(direction=direction))


def outcomes(report: SyncReport) -> dict[str, tuple[bool, str | None]]:
    return {one.key: (one.transferred, one.error_code) for one in report.outcomes}


def refusal(report: SyncReport, store: str, stamped: str = NEWER) -> None:
    [failed] = report.failed
    assert (failed.key, failed.error_code) == (TABLE, "NEWER_FINGERPRINT_TABLE")
    assert failed.error_message == (
        f"the occurrence table of testcl26 2099.01.01-docx-9 in {store} is stamped {stamped}, newer "
        f"than this build's {BUILD}; it was left as it was"
    )


# ------------------------------------------------------------------------------------------------
# A push
# ------------------------------------------------------------------------------------------------


async def test_a_push_of_a_table_a_newer_build_stamped_is_refused_and_the_rest_goes_up(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    write_local(data_dir, TABLE, table(NEWER))
    write_local(data_dir, MANIFEST, b'{"week": 1}\n')

    report = await sync(service, SyncDirection.PUSH)

    refusal(report, "this machine's store sync copy")
    assert outcomes(report)[MANIFEST] == (True, None)
    assert "Contents" not in s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="parsed/")


async def test_a_push_over_the_buckets_table_a_newer_build_stamped_is_refused_and_leaves_it(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The copy this machine pulled before the newer build published is older than the bucket's."""
    put_remote(s3_client, evidence_bucket, TABLE, table(NEWER, rows=3))
    write_local(data_dir, TABLE, table(BUILD))

    report = await sync(service, SyncDirection.PUSH)

    assert report.plan.of(SyncAction.CHANGED)[0].remote_key == TABLE
    refusal(report, "the bucket")
    assert read_remote(s3_client, evidence_bucket, TABLE) == table(NEWER, rows=3)


@pytest.mark.parametrize(("ours", "theirs"), [(BUILD, BUILD), (BUILD, OLDER), (OLDER, OLDER), (OLDER, BUILD)])
async def test_a_push_of_an_equal_or_older_table_over_an_equal_or_older_one_goes_up_as_before(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    ours: str,
    theirs: str,
) -> None:
    put_remote(s3_client, evidence_bucket, TABLE, table(theirs, rows=3))
    write_local(data_dir, TABLE, table(ours))

    report = await sync(service, SyncDirection.PUSH)

    assert outcomes(report) == {TABLE: (True, None)}
    assert read_remote(s3_client, evidence_bucket, TABLE) == table(ours)


async def test_a_push_reads_no_stamp_of_an_object_that_is_not_an_occurrence_table(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The index's rows carry the version their source was parsed under, which decides nothing."""
    put_remote(s3_client, evidence_bucket, INDEX, table(NEWER, rows=3))
    write_local(data_dir, INDEX, table(BUILD))

    report = await sync(service, SyncDirection.PUSH)

    assert outcomes(report) == {INDEX: (True, None)}


# ------------------------------------------------------------------------------------------------
# A pull
# ------------------------------------------------------------------------------------------------


async def test_a_pull_over_this_machines_copy_a_newer_build_stamped_is_refused_and_leaves_it(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    put_remote(s3_client, evidence_bucket, TABLE, table(BUILD, rows=3))
    put_remote(s3_client, evidence_bucket, MANIFEST, b'{"week": 1}\n')
    write_local(data_dir, TABLE, table(NEWER))

    report = await sync(service, SyncDirection.PULL)

    refusal(report, "this machine's store sync copy")
    assert outcomes(report)[MANIFEST] == (True, None)
    assert read_local(data_dir, TABLE) == table(NEWER)


@pytest.mark.parametrize(("ours", "theirs"), [(BUILD, BUILD), (OLDER, BUILD), (None, NEWER), (OLDER, NEWER)])
async def test_a_pull_over_an_equal_or_older_copy_or_none_comes_down_as_before(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    ours: str | None,
    theirs: str,
) -> None:
    """A pull publishes nothing, so a newer table in the bucket comes down: only what it would
    overwrite is asked about."""
    put_remote(s3_client, evidence_bucket, TABLE, table(theirs, rows=3))
    if ours is not None:
        write_local(data_dir, TABLE, table(ours))

    report = await sync(service, SyncDirection.PULL)

    assert outcomes(report) == {TABLE: (True, None)}
    assert read_local(data_dir, TABLE) == table(theirs, rows=3)


# ------------------------------------------------------------------------------------------------
# The sync decides nothing for itself
# ------------------------------------------------------------------------------------------------


async def test_the_sync_takes_the_rules_answer_and_has_none_of_its_own(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_local(data_dir, TABLE, table(BUILD))
    monkeypatch.setattr(occurrence_table_guard, "is_newer_fingerprint_version", always(True))
    assert outcomes(await sync(service, SyncDirection.PUSH)) == {TABLE: (False, "NEWER_FINGERPRINT_TABLE")}

    put_remote(s3_client, evidence_bucket, TABLE, table(NEWER, rows=3))
    write_local(data_dir, TABLE, table(NEWER))
    monkeypatch.setattr(occurrence_table_guard, "is_newer_fingerprint_version", always(False))
    assert outcomes(await sync(service, SyncDirection.PUSH)) == {TABLE: (True, None)}

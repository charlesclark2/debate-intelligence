"""`store sync` never moves `parsed/`, either way (`v1-e29-t12`).

`caselist parse --publish` is the parsed store's only publisher. Before this task `store sync` treated
`parsed/` as named objects, so a pull copied the bucket's parsed store into `<data_dir>/objects/parsed/`,
which no reader opens, and a push from a machine that pulled earlier could overwrite a per-source file,
the index or the failures file that had changed since. `v1-e34-t29` guarded the occurrence table alone.
Now every key under `parsed/` is planned `skipped`, of kind `parsed_store`, whatever is on either side:

* a push sends nothing under `parsed/` and a pull brings nothing down, whatever the stamps say;
* a key under `parsed/` at the destination only is skipped too, not `would_delete`;
* `manifests/`, `reports/`, `files/` and the blobs are planned and moved exactly as before;
* the occurrence-table rule is never asked: there is nothing for it to refuse;
* a stale `objects/parsed/` copy is counted for `--dry-run`, and never deleted.

The first seven tests are `v1-e34-t29`'s, from `test_store_sync_newer_fingerprint_table.py`, turned
from "refused" into "skipped": the same scenes, now with nothing moved and nothing failed. The tables
are synthetic lines with synthetic versions, and the bucket is moto's: nothing reaches AWS.
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
    PlannedObject,
    SyncAction,
    SyncDirection,
    SyncJournal,
    SyncKeyspace,
    SyncPlan,
    SyncReport,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore
from debate_core.testing.fakes import FixedClock, empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
OLDER: Final = "synthetic-fingerprint-v6"
VERSION_DIRECTORY: Final = "parsed/testcl26/2099.01.01-docx-9"
TABLE: Final = f"{VERSION_DIRECTORY}/occurrences.jsonl"
INDEX: Final = f"{VERSION_DIRECTORY}/index.jsonl"
FAILURES: Final = f"{VERSION_DIRECTORY}/failures.jsonl"
PER_SOURCE: Final = f"{VERSION_DIRECTORY}/sha256/ab/cd/{'abcd' * 16}.jsonl"
MANIFEST: Final = "manifests/testcl26/2026-09-15.jsonl"
REPORT: Final = "reports/testcl26/2026-09-15/landscape.json"
BUILT_FILE: Final = "files/testcl26/2026-09-15/synthetic.docx"
BLOB_PREFIX: Final = "raw/caselist/testcl26"
PARSED_STORE: Final = "parsed_store"
"""`SkipKind.PARSED_STORE`'s value, compared as a string so this module collects before it exists."""


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
    """Both keyspaces as the composition root builds them: `<data_dir>/objects/` and `<data_dir>/blobs/`."""
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    remote = S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)
    return EvidenceSyncService(
        suppression=empty_suppression_list(),
        keyspaces=(
            SyncKeyspace(name="objects", local=objects, remote=remote, local_path_for=objects.path_for),
            SyncKeyspace(
                name="blobs",
                local=blobs,
                remote=remote,
                remote_prefix=BLOB_PREFIX,
                content_addressed=True,
                local_path_for=blobs.path_for,
            ),
        ),
        journal=SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket),
        remote_name=evidence_bucket,
        clock=FixedClock(),
    )


def table(stamp: str, rows: int = 2) -> bytes:
    """An occurrence table's lines, as far as the guard would read them."""
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


def write_local_blob(data_dir: Path, body: bytes) -> str:
    """A blob in `<data_dir>/blobs/`; returns its bucket key under :data:`BLOB_PREFIX`."""
    digest = hashlib.sha256(body).hexdigest()
    path = data_dir / "blobs" / "sha256" / digest[:2] / digest[2:4] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return f"{BLOB_PREFIX}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def put_remote(client: S3Client, bucket: str, key: str, body: bytes) -> None:
    client.put_object(
        Bucket=bucket, Key=key, Body=body, Metadata={SHA256_METADATA_NAME: hashlib.sha256(body).hexdigest()}
    )


def read_remote(client: S3Client, bucket: str, key: str) -> bytes:
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def remote_keys(client: S3Client, bucket: str, prefix: str = "") -> list[str]:
    listing = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return sorted(str(stored.get("Key", "")) for stored in listing.get("Contents", []))


async def sync(service: EvidenceSyncService, direction: SyncDirection, prefix: str = "") -> SyncReport:
    return await service.execute(await service.plan(prefix=prefix, direction=direction))


def outcomes(report: SyncReport) -> dict[str, tuple[bool, str | None]]:
    return {one.key: (one.transferred, one.error_code) for one in report.outcomes}


def decisions(plan: SyncPlan) -> dict[str, tuple[str, str | None]]:
    """Each planned key's action and kind of skip, by bucket key."""
    return {planned.remote_key: (planned.action.value, planned.skip_kind) for planned in plan.objects}


def parsed_store_skips(plan: SyncPlan) -> list[str]:
    return [planned.remote_key for planned in plan.objects if planned.skip_kind == PARSED_STORE]


SKIPPED_AS_PARSED: Final = ("skipped", PARSED_STORE)


# ------------------------------------------------------------------------------------------------
# A push (v1-e34-t29's push tests, turned from "refused" into "skipped")
# ------------------------------------------------------------------------------------------------


async def test_a_push_skips_a_table_a_newer_build_stamped_and_the_rest_goes_up(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Was `test_a_push_of_a_table_a_newer_build_stamped_is_refused_and_the_rest_goes_up`."""
    write_local(data_dir, TABLE, table(NEWER))
    write_local(data_dir, MANIFEST, b'{"week": 1}\n')

    report = await sync(service, SyncDirection.PUSH)

    assert decisions(report.plan)[TABLE] == SKIPPED_AS_PARSED
    assert outcomes(report) == {MANIFEST: (True, None)}
    assert remote_keys(s3_client, evidence_bucket, "parsed/") == []


async def test_a_push_skips_a_table_over_the_buckets_newer_one_and_leaves_it(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Was `test_a_push_over_the_buckets_table_a_newer_build_stamped_is_refused_and_leaves_it`: the
    copy this machine pulled before the newer build published is no longer `changed`, and fails nothing."""
    put_remote(s3_client, evidence_bucket, TABLE, table(NEWER, rows=3))
    write_local(data_dir, TABLE, table(BUILD))

    report = await sync(service, SyncDirection.PUSH)

    assert decisions(report.plan) == {TABLE: SKIPPED_AS_PARSED}
    assert (report.outcomes, report.succeeded) == ((), True)
    assert read_remote(s3_client, evidence_bucket, TABLE) == table(NEWER, rows=3)


@pytest.mark.parametrize(("ours", "theirs"), [(BUILD, BUILD), (BUILD, OLDER), (OLDER, OLDER), (OLDER, BUILD)])
async def test_a_push_of_an_equal_or_older_table_over_an_equal_or_older_one_moves_nothing(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    ours: str,
    theirs: str,
) -> None:
    """Was `test_a_push_of_an_equal_or_older_table_over_an_equal_or_older_one_goes_up_as_before`:
    what the guard let through, the sync now leaves for `caselist parse --publish`."""
    put_remote(s3_client, evidence_bucket, TABLE, table(theirs, rows=3))
    write_local(data_dir, TABLE, table(ours))

    report = await sync(service, SyncDirection.PUSH)

    assert (decisions(report.plan), report.outcomes) == ({TABLE: SKIPPED_AS_PARSED}, ())
    assert read_remote(s3_client, evidence_bucket, TABLE) == table(theirs, rows=3)


async def test_a_push_skips_every_other_object_under_parsed_too(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Was `test_a_push_reads_no_stamp_of_an_object_that_is_not_an_occurrence_table`, where the index
    went up over the bucket's. The per-source files, the index and the failures file are what the
    guard never covered, and what a push from an earlier pull overwrote."""
    for key in (INDEX, FAILURES, PER_SOURCE):
        put_remote(s3_client, evidence_bucket, key, table(NEWER, rows=3))
        write_local(data_dir, key, table(BUILD))

    report = await sync(service, SyncDirection.PUSH)

    assert (decisions(report.plan), report.outcomes) == (
        {INDEX: SKIPPED_AS_PARSED, FAILURES: SKIPPED_AS_PARSED, PER_SOURCE: SKIPPED_AS_PARSED},
        (),
    )
    for key in (INDEX, FAILURES, PER_SOURCE):
        assert read_remote(s3_client, evidence_bucket, key) == table(NEWER, rows=3)


# ------------------------------------------------------------------------------------------------
# A pull (v1-e34-t29's pull tests, turned the same way)
# ------------------------------------------------------------------------------------------------


async def test_a_pull_skips_the_table_over_this_machines_newer_copy_and_the_rest_comes_down(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Was `test_a_pull_over_this_machines_copy_a_newer_build_stamped_is_refused_and_leaves_it`."""
    put_remote(s3_client, evidence_bucket, TABLE, table(BUILD, rows=3))
    put_remote(s3_client, evidence_bucket, MANIFEST, b'{"week": 1}\n')
    write_local(data_dir, TABLE, table(NEWER))

    report = await sync(service, SyncDirection.PULL)

    assert decisions(report.plan)[TABLE] == SKIPPED_AS_PARSED
    assert outcomes(report) == {MANIFEST: (True, None)}
    assert read_local(data_dir, TABLE) == table(NEWER)


@pytest.mark.parametrize(("ours", "theirs"), [(BUILD, BUILD), (OLDER, BUILD), (None, NEWER), (OLDER, NEWER)])
async def test_a_pull_of_any_table_over_any_copy_or_none_brings_nothing_down(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    ours: str | None,
    theirs: str,
) -> None:
    """Was `test_a_pull_over_an_equal_or_older_copy_or_none_comes_down_as_before`. A copy under
    `objects/parsed/` is read by nothing, so a pull no longer makes one, or refreshes one."""
    put_remote(s3_client, evidence_bucket, TABLE, table(theirs, rows=3))
    if ours is not None:
        write_local(data_dir, TABLE, table(ours))

    report = await sync(service, SyncDirection.PULL)

    assert (decisions(report.plan), report.outcomes) == ({TABLE: SKIPPED_AS_PARSED}, ())
    if ours is None:
        assert not (data_dir / "objects" / "parsed").exists()
    else:
        assert read_local(data_dir, TABLE) == table(ours)


# ------------------------------------------------------------------------------------------------
# The occurrence-table rule is not asked
# ------------------------------------------------------------------------------------------------


async def test_the_sync_asks_the_occurrence_table_rule_nothing(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Was `test_the_sync_takes_the_rules_answer_and_has_none_of_its_own`. The rule stays for
    `caselist parse` and its publisher; a sync that moves no table has nothing to ask it, so a rule
    that refuses everything changes nothing either way."""
    write_local(data_dir, TABLE, table(BUILD))
    put_remote(s3_client, evidence_bucket, TABLE, table(NEWER, rows=3))
    monkeypatch.setattr(occurrence_table_guard, "is_newer_fingerprint_version", always(True))

    for direction in SyncDirection:
        report = await sync(service, direction)
        assert (decisions(report.plan), report.outcomes, report.succeeded) == (
            {TABLE: SKIPPED_AS_PARSED},
            (),
            True,
        )


# ------------------------------------------------------------------------------------------------
# Whatever is on either side, either way (acceptance criterion 1)
# ------------------------------------------------------------------------------------------------


def a_store_with_every_keyspace(data_dir: Path, client: S3Client, bucket: str, *, with_parsed: bool) -> str:
    """Each keyspace in each state, on both sides; with `parsed/` in every state too when asked.

    Returns the bucket key of the blob this machine holds and the bucket does not.
    """
    write_local(data_dir, MANIFEST, b'{"week": 1}\n')
    write_local(data_dir, REPORT, b'{"landscape": 2}')
    put_remote(client, bucket, REPORT, b'{"landscape": 1, "an earlier build": true}')
    write_local(data_dir, BUILT_FILE, b"a synthetic built file")
    put_remote(client, bucket, "manifests/testcl26/2026-09-08.jsonl", b'{"week": 0}\n')
    blob = write_local_blob(data_dir, b"a synthetic disclosure")
    if with_parsed:
        write_local(data_dir, TABLE, table(BUILD))
        put_remote(client, bucket, TABLE, table(OLDER, rows=3))
        write_local(data_dir, INDEX, b'{"record": "source"}\n')
        put_remote(client, bucket, FAILURES, b'{"record": "failure"}\n')
    return blob


async def test_a_push_plans_parsed_skipped_on_either_side_and_every_other_keyspace_as_written(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Written by hand from the scene: a `parsed/` key on this machine only, in the bucket only and on
    both is `skipped`; the bucket-only one is not `would_delete`, as a bucket-only manifest still is."""
    blob = a_store_with_every_keyspace(data_dir, s3_client, evidence_bucket, with_parsed=True)

    plan = await service.plan(direction=SyncDirection.PUSH)

    assert decisions(plan) == {
        MANIFEST: ("new", None),
        "manifests/testcl26/2026-09-08.jsonl": ("would_delete", None),
        REPORT: ("changed", None),
        BUILT_FILE: ("new", None),
        blob: ("new", None),
        TABLE: SKIPPED_AS_PARSED,
        INDEX: SKIPPED_AS_PARSED,
        FAILURES: SKIPPED_AS_PARSED,
    }


async def test_a_pull_plans_parsed_skipped_on_either_side_and_every_other_keyspace_as_written(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    blob = a_store_with_every_keyspace(data_dir, s3_client, evidence_bucket, with_parsed=True)

    plan = await service.plan(direction=SyncDirection.PULL)

    assert decisions(plan) == {
        MANIFEST: ("would_delete", None),
        "manifests/testcl26/2026-09-08.jsonl": ("new", None),
        REPORT: ("changed", None),
        BUILT_FILE: ("would_delete", None),
        blob: ("would_delete", None),
        TABLE: SKIPPED_AS_PARSED,
        INDEX: SKIPPED_AS_PARSED,
        FAILURES: SKIPPED_AS_PARSED,
    }


@pytest.mark.parametrize("direction", list(SyncDirection))
async def test_every_other_keyspace_is_planned_and_moved_as_it_is_without_parsed(
    service: EvidenceSyncService,
    tmp_path: Path,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    direction: SyncDirection,
) -> None:
    """The same store with and without `parsed/` objects: the plan for everything else is the same
    object for object, and so is what each run moves. The bucket is emptied between the two."""

    def without_parsed(plan: SyncPlan) -> tuple[PlannedObject, ...]:
        return tuple(planned for planned in plan.objects if not planned.remote_key.startswith("parsed/"))

    a_store_with_every_keyspace(data_dir, s3_client, evidence_bucket, with_parsed=False)
    before = await sync(service, direction)
    for key in remote_keys(s3_client, evidence_bucket):
        s3_client.delete_object(Bucket=evidence_bucket, Key=key)
    for path in sorted(data_dir.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()

    a_store_with_every_keyspace(data_dir, s3_client, evidence_bucket, with_parsed=True)
    after = await sync(service, direction)

    assert without_parsed(after.plan) == without_parsed(before.plan)
    assert outcomes(after) == outcomes(before)
    assert outcomes(after) and all(transferred for transferred, _ in outcomes(after).values())
    assert len(parsed_store_skips(after.plan)) == 3


async def test_a_push_and_a_pull_leave_both_sides_of_parsed_as_they_were(
    service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    a_store_with_every_keyspace(data_dir, s3_client, evidence_bucket, with_parsed=True)
    local_before = sorted(path.relative_to(data_dir).as_posix() for path in (data_dir / "objects/parsed").rglob("*"))

    await sync(service, SyncDirection.PUSH)
    await sync(service, SyncDirection.PULL)

    assert remote_keys(s3_client, evidence_bucket, "parsed/") == [FAILURES, TABLE]
    assert read_remote(s3_client, evidence_bucket, TABLE) == table(OLDER, rows=3)
    assert sorted(
        path.relative_to(data_dir).as_posix() for path in (data_dir / "objects/parsed").rglob("*")
    ) == local_before
    assert read_local(data_dir, TABLE) == table(BUILD)


@pytest.mark.parametrize("direction", list(SyncDirection))
async def test_a_run_filtered_to_parsed_moves_nothing(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    direction: SyncDirection,
) -> None:
    a_store_with_every_keyspace(data_dir, s3_client, evidence_bucket, with_parsed=True)

    report = await sync(service, direction, prefix="parsed/")

    assert (parsed_store_skips(report.plan), report.outcomes) == ([FAILURES, INDEX, TABLE], ())


@pytest.mark.parametrize("direction", list(SyncDirection))
async def test_the_skipped_breakdown_counts_parsed_as_its_own_kind(
    service: EvidenceSyncService,
    data_dir: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    direction: SyncDirection,
) -> None:
    a_store_with_every_keyspace(data_dir, s3_client, evidence_bucket, with_parsed=True)

    plan = await service.plan(direction=direction)

    assert [(reason.kind, reason.count, reason.key_prefixes) for reason in plan.skipped_reasons] == [
        (PARSED_STORE, 3, ("parsed/testc",))
    ]
    assert plan.counts["skipped"] == 3


# ------------------------------------------------------------------------------------------------
# The stale copy an earlier pull left (acceptance criterion 2)
# ------------------------------------------------------------------------------------------------


async def test_a_stale_copy_is_its_directory_and_its_file_count_and_is_left_where_it_is(
    service: EvidenceSyncService, data_dir: Path
) -> None:
    for key in (TABLE, INDEX, PER_SOURCE):
        write_local(data_dir, key, b"what an earlier pull copied\n")
    write_local(data_dir, MANIFEST, b'{"week": 1}\n')

    stale = await service.stale_parsed_copy()

    assert stale is not None
    assert (stale.directory, stale.files) == (data_dir / "objects" / "parsed", 3)
    assert read_local(data_dir, PER_SOURCE) == b"what an earlier pull copied\n"


async def test_no_stale_copy_is_none(service: EvidenceSyncService, data_dir: Path) -> None:
    write_local(data_dir, MANIFEST, b'{"week": 1}\n')
    (data_dir / "parsed" / "testcl26").mkdir(parents=True)

    assert await service.stale_parsed_copy() is None

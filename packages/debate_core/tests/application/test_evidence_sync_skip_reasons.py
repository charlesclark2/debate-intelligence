"""Why a sync skipped what it skipped, grouped by kind (`v1-e29-t11-store-sync-skip-reasons`).

`store sync --json` reported only a `skipped` count, so an operator whose push left a manifest the
publisher withholds behind could not see the reason, which is what tells them to run the removal
again. Every `skipped` object now carries a :class:`SkipKind`, and :attr:`SyncPlan.skipped_reasons`
groups the plan's skips by it: a count, up to three 12-character key prefixes, and, for the two
publisher kinds, the publisher's message for each object, word for word.

The kinds are the planner's skip branches, counted from `EvidenceSyncService._classify` and
`_unless_withheld`: the suppression record, a suppressed blob, a held-only blob, a key another
keyspace owns, a key under no documented prefix, a blob the bucket already holds, a journaled
object, an identical object, and a manifest the publisher withholds or cannot read. A blob already
stored under its digest and a named object of the same digest are both *identical at the
destination*, so they are one kind.

The publisher is stood in for by a callable answering as `withheld_manifest_reason` does; the real
one is `caselist/test_store_sync_skip_reasons.py`'s. Every store is real: the filesystem store on
`tmp_path` and the S3 store on a moto bucket. Every value is synthetic.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    HeldBackDigests,
    JournalEntry,
    ManifestWithholding,
    PlannedObject,
    SkipKind,
    SkippedReason,
    SyncAction,
    SyncDirection,
    SyncJournal,
    SyncKeyspace,
    SyncPlan,
    WithheldManifests,
)
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionState,
)
from debate_core.domain import Sha256Hex
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore
from debate_core.testing.fakes import InMemoryAppendOnlyRecord, empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

BLOB_PREFIX = "raw/caselist/synth26"
IDENTICAL_MANIFEST = "manifests/synth26/2026-09-01.jsonl"
JOURNALED_REPORT = "reports/synth26/2026-09-01/landscape.json"
WITHHELD_MANIFEST = "manifests/synth26/2026-09-08.jsonl"
UNREADABLE_MANIFEST = "manifests/synth26/2026-09-15.jsonl"
SENT_MANIFEST = "manifests/synth26/2026-09-22.jsonl"
SUPPRESSION_RECORD = "manifests/_suppression/suppression-list.jsonl"
IN_THE_BLOB_KEYSPACE = f"{BLOB_PREFIX}/notes.txt"
#: A key under no documented prefix, whose first characters are a school's name.
UNDOCUMENTED = "Synthetic Ridge School/SR/round-1.docx"

WITHHELD_MESSAGE = (
    "the local manifest still has 1 row(s) at a path a removal holds: "
    f"{'ab' * 32} (RM-2026-71); re-run `caselist remove` for them on this machine to rewrite it"
)
UNREADABLE_MESSAGE = f"{UNREADABLE_MANIFEST} line 1 is not a usable manifest row: not JSON"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "evidence"


def write_local_object(data_dir: Path, key: str, body: bytes) -> str:
    path = data_dir / "objects" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def write_local_blob(data_dir: Path, body: bytes) -> str:
    """Store `body` in the local blob tree and return its digest."""
    digest = hashlib.sha256(body).hexdigest()
    path = data_dir / "blobs" / "sha256" / digest[:2] / digest[2:4] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return digest


def blob_key(digest: str) -> str:
    return f"{BLOB_PREFIX}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def put_remote_object(client: S3Client, bucket: str, key: str, body: bytes) -> None:
    client.put_object(
        Bucket=bucket, Key=key, Body=body, Metadata={SHA256_METADATA_NAME: hashlib.sha256(body).hexdigest()}
    )


def stops(digest: str) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=digest,
        recorded_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-72",
    )


def held(*digests: str) -> HeldBackDigests:
    async def held_back(_: SuppressionState) -> frozenset[Sha256Hex]:
        return frozenset(digests)

    return held_back


def publisher_answering(answers: dict[str, ManifestWithholding]) -> WithheldManifests:
    """A stand-in for `withheld_manifest_reason`: the answer for each manifest key, `None` for the rest."""

    async def withheld(manifest: ObjectInfo, _: SuppressionState) -> ManifestWithholding | None:
        return answers.get(manifest.key)

    return withheld


def sync_service(
    data_dir: Path,
    s3_client: S3Client,
    bucket: str,
    *,
    suppression: RecordedSuppressionList | None = None,
    journal: SyncJournal | None = None,
    held_back: tuple[str, ...] = (),
    answers: dict[str, ManifestWithholding] | None = None,
) -> EvidenceSyncService:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    remote = S3EvidenceObjectStore(bucket=bucket, client=s3_client)
    return EvidenceSyncService(
        suppression=suppression or empty_suppression_list(),
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
        journal=journal,
        remote_name=bucket,
        held_back=held(*held_back),
        withheld_manifests=publisher_answering(answers or {}),
    )


def kinds_of(plan: SyncPlan) -> dict[str, SkipKind | None]:
    return {planned.remote_key: planned.skip_kind for planned in plan.of(SyncAction.SKIPPED)}


def by_kind(plan: SyncPlan) -> dict[SkipKind, SkippedReason]:
    return {reason.kind: reason for reason in plan.skipped_reasons}


# ------------------------------------------------------------------------------------------------
# A push that skips one object of every kind
# ------------------------------------------------------------------------------------------------


@pytest.fixture
async def every_kind(data_dir: Path, s3_client: S3Client, evidence_bucket: str) -> SyncPlan:
    """One push planning a skip of every kind, beside one manifest it sends."""
    body = b'{"kind":"member"}\n'
    write_local_object(data_dir, IDENTICAL_MANIFEST, body)
    put_remote_object(s3_client, evidence_bucket, IDENTICAL_MANIFEST, body)

    report = b'{"claims":[]}'
    report_digest = write_local_object(data_dir, JOURNALED_REPORT, report)
    put_remote_object(s3_client, evidence_bucket, JOURNALED_REPORT, report)
    journal = SyncJournal.unwritten(remote=evidence_bucket)
    journal.record(
        JournalEntry(
            finished_at="2026-10-01T12:00:00+00:00",
            direction=SyncDirection.PUSH,
            keyspace="objects",
            key=JOURNALED_REPORT,
            sha256=report_digest,
            size=len(report),
            remote=evidence_bucket,
        )
    )

    stored = write_local_blob(data_dir, b"a synthetic disclosed file the bucket holds")
    put_remote_object(
        s3_client, evidence_bucket, blob_key(stored), b"a synthetic disclosed file the bucket holds"
    )
    held_only = write_local_blob(data_dir, b"a synthetic upload at a held path")
    suppressed = write_local_blob(data_dir, b"a synthetic file a removal took down")

    for key in (WITHHELD_MANIFEST, UNREADABLE_MANIFEST, SENT_MANIFEST, SUPPRESSION_RECORD):
        write_local_object(data_dir, key, b"synthetic\n")
    write_local_object(data_dir, IN_THE_BLOB_KEYSPACE, b"filed under the wrong tree")
    write_local_object(data_dir, UNDOCUMENTED, b"not evidence")

    service = sync_service(
        data_dir,
        s3_client,
        evidence_bucket,
        suppression=RecordedSuppressionList(
            InMemoryAppendOnlyRecord("the list", [stops(suppressed).to_line()])
        ),
        journal=journal,
        held_back=(held_only,),
        answers={
            WITHHELD_MANIFEST: ManifestWithholding(WITHHELD_MESSAGE, request_ids=("RM-2026-71",)),
            UNREADABLE_MANIFEST: ManifestWithholding(UNREADABLE_MESSAGE, unreadable=True),
        },
    )
    return await service.plan(direction=SyncDirection.PUSH)


async def test_every_skip_carries_the_kind_of_branch_that_skipped_it(every_kind: SyncPlan) -> None:
    digests = {
        planned.remote_key: planned.sha256 for planned in every_kind.objects if planned.keyspace == "blobs"
    }
    stored, held_only, suppressed = (
        blob_key(hashlib.sha256(body).hexdigest())
        for body in (
            b"a synthetic disclosed file the bucket holds",
            b"a synthetic upload at a held path",
            b"a synthetic file a removal took down",
        )
    )

    assert set(digests) == {stored, held_only, suppressed}
    assert kinds_of(every_kind) == {
        IDENTICAL_MANIFEST: SkipKind.IDENTICAL,
        stored: SkipKind.IDENTICAL,
        JOURNALED_REPORT: SkipKind.JOURNALED,
        held_only: SkipKind.HELD_ONLY_BLOB,
        WITHHELD_MANIFEST: SkipKind.WITHHELD_MANIFEST,
        UNREADABLE_MANIFEST: SkipKind.UNREADABLE_MANIFEST,
        suppressed: SkipKind.SUPPRESSED_SOURCE,
        SUPPRESSION_RECORD: SkipKind.SUPPRESSION_RECORD,
        IN_THE_BLOB_KEYSPACE: SkipKind.ANOTHER_KEYSPACE,
        UNDOCUMENTED: SkipKind.UNDOCUMENTED_PREFIX,
    }
    assert [planned.remote_key for planned in every_kind.of(SyncAction.NEW)] == [SENT_MANIFEST]


async def test_the_breakdown_groups_every_skip_by_kind_with_its_count_and_key_prefixes(
    every_kind: SyncPlan,
) -> None:
    """In :class:`SkipKind`'s order, only the kinds the plan has. The blob keyspace sorts first."""
    assert every_kind.skipped_reasons == (
        SkippedReason(SkipKind.IDENTICAL, 2, ("raw/caselist", "manifests/sy")),
        SkippedReason(SkipKind.JOURNALED, 1, ("reports/synt",)),
        SkippedReason(SkipKind.HELD_ONLY_BLOB, 1, ("raw/caselist",)),
        SkippedReason(
            SkipKind.WITHHELD_MANIFEST,
            1,
            ("manifests/sy",),
            messages=(WITHHELD_MESSAGE,),
            request_ids=("RM-2026-71",),
        ),
        SkippedReason(SkipKind.UNREADABLE_MANIFEST, 1, ("manifests/sy",), messages=(UNREADABLE_MESSAGE,)),
        SkippedReason(SkipKind.SUPPRESSED_SOURCE, 1, ("raw/caselist",)),
        SkippedReason(SkipKind.SUPPRESSION_RECORD, 1, ("manifests/_s",)),
        SkippedReason(SkipKind.ANOTHER_KEYSPACE, 1, ("raw/caselist",)),
        SkippedReason(SkipKind.UNDOCUMENTED_PREFIX, 1, ()),
    )
    assert sum(reason.count for reason in every_kind.skipped_reasons) == every_kind.counts["skipped"] == 10


async def test_the_publishers_message_is_the_plans_reason_word_for_word(every_kind: SyncPlan) -> None:
    reasons = {planned.remote_key: planned.reason for planned in every_kind.objects}
    breakdown = by_kind(every_kind)

    assert breakdown[SkipKind.WITHHELD_MANIFEST].messages == (reasons[WITHHELD_MANIFEST],)
    assert breakdown[SkipKind.UNREADABLE_MANIFEST].messages == (reasons[UNREADABLE_MANIFEST],)


async def test_a_key_under_no_documented_prefix_is_counted_and_never_named(every_kind: SyncPlan) -> None:
    """Such a key is whatever someone put in the local tree, so even 12 characters of it can be a
    school's name. It is counted, with no prefix."""
    assert by_kind(every_kind)[SkipKind.UNDOCUMENTED_PREFIX].key_prefixes == ()
    assert "Synthetic" not in repr([reason.as_json() for reason in every_kind.skipped_reasons])


async def test_each_kind_reports_as_json_with_messages_only_for_the_publisher_kinds(
    every_kind: SyncPlan,
) -> None:
    breakdown = by_kind(every_kind)

    assert breakdown[SkipKind.IDENTICAL].as_json() == {
        "count": 2,
        "key_prefixes": ["raw/caselist", "manifests/sy"],
    }
    assert breakdown[SkipKind.WITHHELD_MANIFEST].as_json() == {
        "count": 1,
        "key_prefixes": ["manifests/sy"],
        "messages": [WITHHELD_MESSAGE],
        "request_ids": ["RM-2026-71"],
    }
    assert breakdown[SkipKind.UNREADABLE_MANIFEST].as_json() == {
        "count": 1,
        "key_prefixes": ["manifests/sy"],
        "messages": [UNREADABLE_MESSAGE],
        "request_ids": [],
    }


# ------------------------------------------------------------------------------------------------
# Grouping by kind, not by text
# ------------------------------------------------------------------------------------------------


async def test_manifests_withheld_for_different_rows_are_one_kind_with_each_message(
    data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The publisher's messages differ per manifest: grouped by the text, three manifests would be
    three reasons. They are one, with each message in key order and each request once."""
    keys = [f"manifests/synth26/2026-10-{day:02d}.jsonl" for day in (1, 8, 15)]
    for key in keys:
        write_local_object(data_dir, key, b"synthetic\n")
    messages = [f"the local manifest still has row {number}" for number in (1, 2, 3)]
    answers = {
        keys[0]: ManifestWithholding(messages[0], request_ids=("RM-2026-79",)),
        keys[1]: ManifestWithholding(messages[1], request_ids=("RM-2026-73", "RM-2026-79")),
        keys[2]: ManifestWithholding(messages[2]),
    }

    plan = await sync_service(data_dir, s3_client, evidence_bucket, answers=answers).plan(
        direction=SyncDirection.PUSH
    )

    assert plan.skipped_reasons == (
        SkippedReason(
            SkipKind.WITHHELD_MANIFEST,
            3,
            ("manifests/sy",),
            messages=tuple(messages),
            request_ids=("RM-2026-73", "RM-2026-79"),
        ),
    )


async def test_at_most_three_distinct_key_prefixes_in_key_order(
    data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    for key in (
        "files/synth26/2026-09-01/aff.docx",
        "manifests/synth26/2026-09-01.jsonl",
        "manifests/synth26/2026-09-08.jsonl",
        "reports/synth26/2026-09-01/landscape.json",
        "uploads/synth26/2026-09-01/upload.json",
    ):
        body = key.encode()
        write_local_object(data_dir, key, body)
        put_remote_object(s3_client, evidence_bucket, key, body)

    plan = await sync_service(data_dir, s3_client, evidence_bucket).plan(direction=SyncDirection.PUSH)

    assert plan.skipped_reasons == (
        SkippedReason(SkipKind.IDENTICAL, 5, ("files/synth2", "manifests/sy", "reports/synt")),
    )


async def test_nothing_skipped_is_an_empty_breakdown(
    data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    write_local_object(data_dir, SENT_MANIFEST, b"synthetic\n")

    plan = await sync_service(data_dir, s3_client, evidence_bucket).plan(direction=SyncDirection.PUSH)

    assert (plan.counts["skipped"], plan.skipped_reasons) == (0, ())


# ------------------------------------------------------------------------------------------------
# A pull
# ------------------------------------------------------------------------------------------------


async def test_a_pull_reports_the_same_way_and_has_no_push_only_kind(
    data_dir: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The bucket holds a manifest the publisher would withhold and a blob only a held row names. A
    pull, which writes to this machine, sends neither anywhere: both are `new`, and the identical
    manifest is the one skip."""
    body = b'{"kind":"member"}\n'
    write_local_object(data_dir, IDENTICAL_MANIFEST, body)
    put_remote_object(s3_client, evidence_bucket, IDENTICAL_MANIFEST, body)
    put_remote_object(s3_client, evidence_bucket, WITHHELD_MANIFEST, b"synthetic\n")
    held_only = hashlib.sha256(b"a synthetic upload at a held path").hexdigest()
    put_remote_object(s3_client, evidence_bucket, blob_key(held_only), b"a synthetic upload at a held path")

    plan = await sync_service(
        data_dir,
        s3_client,
        evidence_bucket,
        held_back=(held_only,),
        answers={WITHHELD_MANIFEST: ManifestWithholding(WITHHELD_MESSAGE, request_ids=("RM-2026-71",))},
    ).plan(direction=SyncDirection.PULL)

    assert sorted(planned.remote_key for planned in plan.of(SyncAction.NEW)) == [
        WITHHELD_MANIFEST,
        blob_key(held_only),
    ]
    assert plan.skipped_reasons == (SkippedReason(SkipKind.IDENTICAL, 1, ("manifests/sy",)),)


# ------------------------------------------------------------------------------------------------
# A skip always has a kind, and nothing else has one
# ------------------------------------------------------------------------------------------------


def planned_object(action: SyncAction, skip_kind: SkipKind | None) -> PlannedObject:
    return PlannedObject(
        keyspace="objects",
        local_key=SENT_MANIFEST,
        remote_key=SENT_MANIFEST,
        action=action,
        size=1,
        reason="synthetic",
        skip_kind=skip_kind,
    )


def test_a_skip_without_a_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="skip_kind"):
        planned_object(SyncAction.SKIPPED, None)


@pytest.mark.parametrize("action", [action for action in SyncAction if action is not SyncAction.SKIPPED])
def test_a_kind_on_anything_but_a_skip_is_refused(action: SyncAction) -> None:
    with pytest.raises(ValueError, match="skip_kind"):
        planned_object(action, SkipKind.IDENTICAL)

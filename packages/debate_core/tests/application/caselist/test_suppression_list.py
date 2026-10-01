"""The suppression list: append-only, merged across copies, latest entry wins, and no names.

Each guarantee is tested by trying to break it rather than by exercising it: a line that would
name a team, an append that would rewrite, two copies that disagree, an unfinished last line, an
un-suppress written before the suppression it would lift.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from debate_core.application.caselist.suppression import (
    SUPPRESSION_LIST_KEY,
    ObjectStoreAppendOnlyRecord,
    RecordedRemovalLog,
    RecordedSuppressionList,
    load_suppression_state,
)
from debate_core.application.ports.suppression import (
    AppendOnlyRecord,
    ReasonCode,
    RemovalLog,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    UnreadableAppendOnlyRecord,
    disclosure_digest,
)
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.suppression_list import (
    SUPPRESSION_FILE_MODE,
    LocalAppendOnlyFile,
    local_suppression_list_file,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import InMemoryAppendOnlyRecord

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

FILE_A = "a" * 64
FILE_B = "b" * 64
NOON = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def suppress(sha256: str, *, at: datetime = NOON, disclosure: str | None = None) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha256,
        disclosure=disclosure,
        recorded_at=at,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )


def unsuppress(sha256: str, *, at: datetime) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.UNSUPPRESS, sha256=sha256, recorded_at=at, reason=ReasonCode.REMOVED_IN_ERROR
    )


# ------------------------------------------------------------------------------------------------
# What an entry may say
# ------------------------------------------------------------------------------------------------


class TestAnEntryCannotCarryAName:
    def test_a_line_holds_exactly_the_documented_fields(self) -> None:
        line = json.loads(suppress(FILE_A).to_line())
        assert set(line) == {
            "schema_version",
            "action",
            "sha256",
            "disclosure",
            "recorded_at",
            "reason",
            "request_id",
        }

    def test_an_extra_field_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            SuppressionEntry.model_validate({**suppress(FILE_A).model_dump(), "school": "Maple Grove"})

    @pytest.mark.parametrize("request_id", ["RM-2026-01 Maple Grove QX", "Maple Grove", "RM-26-1", ""])
    def test_a_request_id_is_a_register_id_and_nothing_else(self, request_id: str) -> None:
        with pytest.raises(ValidationError):
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=FILE_A,
                recorded_at=NOON,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id=request_id,
            )

    def test_the_removal_log_has_no_free_text_field_either(self) -> None:
        entry = RemovalLogEntry(
            kind=RemovalLogKind.REMOVAL,
            recorded_at=NOON,
            request_id="RM-2026-01",
            reason=ReasonCode.REQUESTED_BY_TEAM,
            environment="dev",
            outcome=RemovalOutcome.INCOMPLETE,
            error_code="STORE_ACCESS_DENIED",
        )
        assert RemovalLogEntry.from_line(entry.to_line()) == entry
        with pytest.raises(ValidationError):
            entry.evolve(error_code="denied while deleting Maple Grove QX")
        with pytest.raises(ValidationError):
            RemovalLogEntry.model_validate({**entry.model_dump(), "team_code": "QX"})

    def test_a_suppression_needs_a_request_and_a_removal_reason(self) -> None:
        with pytest.raises(ValidationError, match="request id"):
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS, sha256=FILE_A, recorded_at=NOON, reason=ReasonCode.POLICY
            )
        with pytest.raises(ValidationError, match="not a reason to suppress"):
            suppress(FILE_A).evolve(reason=ReasonCode.REMOVED_IN_ERROR)

    def test_an_unsuppress_lifts_a_sha256_and_names_no_disclosure(self) -> None:
        with pytest.raises(ValidationError, match="names no disclosure"):
            unsuppress(FILE_A, at=NOON).evolve(disclosure=FILE_B)
        with pytest.raises(ValidationError, match="not a reason to un-suppress"):
            unsuppress(FILE_A, at=NOON).evolve(reason=ReasonCode.REQUESTED_BY_TEAM)

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            suppress(FILE_A, at=datetime(2026, 9, 30, 12, 0))  # noqa: DTZ001 - the point of the test


# ------------------------------------------------------------------------------------------------
# What the list suppresses
# ------------------------------------------------------------------------------------------------


class TestTheLatestEntryWins:
    def test_a_suppressed_source_is_suppressed_at_every_path(self) -> None:
        state = SuppressionState.from_entries([suppress(FILE_A)])
        assert state.suppresses_source(FILE_A)
        assert state.suppresses(FILE_A, disclosure=None)
        assert state.suppresses(FILE_A, disclosure=disclosure_digest("testcl26", "any/path.docx"))
        assert not state.suppresses(FILE_B, disclosure=None)

    def test_a_disclosure_scoped_entry_stops_that_disclosure_only(self) -> None:
        mine = disclosure_digest(
            "testcl26", "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
        )
        theirs = disclosure_digest(
            "testcl26", "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx"
        )
        state = SuppressionState.from_entries([suppress(FILE_A, disclosure=mine)])

        assert state.suppresses(FILE_A, disclosure=mine)
        assert not state.suppresses(FILE_A, disclosure=theirs)
        assert not state.suppresses(FILE_A, disclosure=None), (
            "an OpenEv copy of shared bytes is not withdrawn"
        )
        assert not state.suppresses_source(FILE_A)
        assert state.is_suppressed(FILE_A)

    def test_an_unsuppress_lifts_both_scopes(self) -> None:
        mine = disclosure_digest("testcl26", "Maple Grove/QX/a.docx")
        state = SuppressionState.from_entries(
            [
                suppress(FILE_A),
                suppress(FILE_A, disclosure=mine),
                unsuppress(FILE_A, at=NOON + timedelta(days=1)),
            ]
        )
        assert not state.is_suppressed(FILE_A)

    def test_order_is_time_not_position_in_the_file(self) -> None:
        """Two copies can hold the same entries in different orders; both must mean the same thing."""
        later_unsuppress = [suppress(FILE_A), unsuppress(FILE_A, at=NOON + timedelta(hours=1))]
        assert not SuppressionState.from_entries(later_unsuppress).is_suppressed(FILE_A)
        assert not SuppressionState.from_entries(reversed(later_unsuppress)).is_suppressed(FILE_A)

        earlier_unsuppress = [unsuppress(FILE_A, at=NOON - timedelta(hours=1)), suppress(FILE_A)]
        assert SuppressionState.from_entries(earlier_unsuppress).is_suppressed(FILE_A)
        assert SuppressionState.from_entries(reversed(earlier_unsuppress)).is_suppressed(FILE_A)

    def test_a_file_can_be_suppressed_again_after_it_was_reinstated(self) -> None:
        state = SuppressionState.from_entries(
            [
                suppress(FILE_A),
                unsuppress(FILE_A, at=NOON + timedelta(days=1)),
                suppress(FILE_A, at=NOON + timedelta(days=2)),
            ]
        )
        assert state.suppresses_source(FILE_A)
        assert state.latest[FILE_A].action is SuppressionAction.SUPPRESS


# ------------------------------------------------------------------------------------------------
# The local copy
# ------------------------------------------------------------------------------------------------


class TestTheLocalCopyIsOnlyEverAppendedTo:
    async def test_reading_a_list_that_does_not_exist_creates_nothing(self, tmp_path: Path) -> None:
        record = local_suppression_list_file(tmp_path / "data")
        assert await record.read_lines() == ()
        assert not (tmp_path / "data").exists()

    async def test_every_append_keeps_every_earlier_byte_and_the_same_file(self, tmp_path: Path) -> None:
        record = local_suppression_list_file(tmp_path)
        await record.append_lines([suppress(FILE_A).to_line()])
        first_bytes = record.path.read_bytes()
        first_inode = record.path.stat().st_ino

        await record.append_lines([suppress(FILE_B).to_line()])

        assert record.path.read_bytes().startswith(first_bytes)
        assert record.path.stat().st_ino == first_inode, "the file was replaced, not appended to"
        assert await record.read_lines() == (suppress(FILE_A).to_line(), suppress(FILE_B).to_line())

    async def test_the_file_is_the_operators_alone(self, tmp_path: Path) -> None:
        record = local_suppression_list_file(tmp_path)
        await record.append_lines([suppress(FILE_A).to_line()])
        assert stat.S_IMODE(record.path.stat().st_mode) == SUPPRESSION_FILE_MODE

    async def test_an_append_lands_after_bytes_another_writer_added(self, tmp_path: Path) -> None:
        """`O_APPEND`: the write goes after whatever is in the file now, not where this process thought."""
        record = LocalAppendOnlyFile(tmp_path / "list.jsonl")
        await record.append_lines([suppress(FILE_A).to_line()])
        with record.path.open("a", encoding="utf-8") as other:
            other.write(suppress(FILE_B).to_line() + "\n")
        await record.append_lines([unsuppress(FILE_A, at=NOON + timedelta(days=1)).to_line()])
        assert await record.read_lines() == (
            suppress(FILE_A).to_line(),
            suppress(FILE_B).to_line(),
            unsuppress(FILE_A, at=NOON + timedelta(days=1)).to_line(),
        )

    async def test_an_unfinished_last_line_is_refused_and_nothing_is_written_after_it(
        self, tmp_path: Path
    ) -> None:
        record = LocalAppendOnlyFile(tmp_path / "list.jsonl")
        record.path.write_text(suppress(FILE_A).to_line() + "\n" + '{"action":"SUPP', encoding="utf-8")
        torn = record.path.read_bytes()

        with pytest.raises(UnreadableAppendOnlyRecord, match="line 2"):
            await record.read_lines()
        with pytest.raises(UnreadableAppendOnlyRecord):
            await record.append_lines([suppress(FILE_B).to_line()])
        assert record.path.read_bytes() == torn

    async def test_a_line_that_is_not_an_entry_is_named_by_number_and_not_quoted(
        self, tmp_path: Path
    ) -> None:
        record = LocalAppendOnlyFile(tmp_path / "list.jsonl")
        record.path.write_text(suppress(FILE_A).to_line() + '\n{"school":"Maple Grove"}\n', encoding="utf-8")
        with pytest.raises(UnreadableAppendOnlyRecord, match="line 2") as refused:
            await RecordedSuppressionList(record).entries()
        assert "Maple Grove" not in str(refused.value)


# ------------------------------------------------------------------------------------------------
# The bucket's copy
# ------------------------------------------------------------------------------------------------


class TestTheBucketCopyIsOnlyEverAppendedTo:
    async def test_an_append_keeps_every_earlier_byte_and_the_bucket_keeps_each_version(
        self, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        record = ObjectStoreAppendOnlyRecord(
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client), SUPPRESSION_LIST_KEY
        )
        assert await record.read_lines() == ()

        await record.append_lines([suppress(FILE_A).to_line()])
        first = s3_client.get_object(Bucket=evidence_bucket, Key=SUPPRESSION_LIST_KEY)["Body"].read()
        await record.append_lines([suppress(FILE_B).to_line()])
        second = s3_client.get_object(Bucket=evidence_bucket, Key=SUPPRESSION_LIST_KEY)["Body"].read()

        assert second.startswith(first)
        assert await record.read_lines() == (suppress(FILE_A).to_line(), suppress(FILE_B).to_line())
        versions = s3_client.list_object_versions(Bucket=evidence_bucket, Prefix=SUPPRESSION_LIST_KEY)
        assert len(versions.get("Versions", [])) == 2

    async def test_a_torn_object_is_refused_before_anything_is_written(self, tmp_path: Path) -> None:
        store = FsEvidenceObjectStore(tmp_path)
        torn = store.path_for(SUPPRESSION_LIST_KEY)
        torn.parent.mkdir(parents=True)
        torn.write_text('{"action":"SUPP', encoding="utf-8")
        record = ObjectStoreAppendOnlyRecord(store, SUPPRESSION_LIST_KEY)

        with pytest.raises(UnreadableAppendOnlyRecord):
            await record.append_lines([suppress(FILE_A).to_line()])
        assert torn.read_text(encoding="utf-8") == '{"action":"SUPP'


# ------------------------------------------------------------------------------------------------
# The merge
# ------------------------------------------------------------------------------------------------


class TestCopiesAreMergedAsASetUnion:
    async def test_each_copy_contributes_and_each_receives_what_it_lacks(self) -> None:
        local = InMemoryAppendOnlyRecord("local", [suppress(FILE_A).to_line()])
        bucket = InMemoryAppendOnlyRecord("bucket", [suppress(FILE_B).to_line()])
        suppression = RecordedSuppressionList(local, bucket)

        assert {entry.sha256 for entry in await suppression.entries()} == {FILE_A, FILE_B}

        reinstated = unsuppress(FILE_A, at=NOON + timedelta(days=1))
        await suppression.append([reinstated])

        assert (
            set(local.lines)
            == set(bucket.lines)
            == {
                suppress(FILE_A).to_line(),
                suppress(FILE_B).to_line(),
                reinstated.to_line(),
            }
        )
        # Every copy only grew: its earlier lines are still its first lines, in their order.
        assert local.lines[0] == suppress(FILE_A).to_line()
        assert bucket.lines[0] == suppress(FILE_B).to_line()
        assert not (await load_suppression_state(suppression)).is_suppressed(FILE_A)

    async def test_reconcile_copies_lines_across_and_appends_nothing_new(self) -> None:
        local = InMemoryAppendOnlyRecord("local", [suppress(FILE_A).to_line()])
        bucket = InMemoryAppendOnlyRecord("bucket")
        await RecordedSuppressionList(local, bucket).reconcile()
        assert bucket.lines == local.lines
        assert local.appends == []

    async def test_an_entry_already_present_is_not_appended_twice(self) -> None:
        local = InMemoryAppendOnlyRecord("local")
        suppression = RecordedSuppressionList(local)
        await suppression.append([suppress(FILE_A)])
        await suppression.append([suppress(FILE_A)])
        assert local.lines == [suppress(FILE_A).to_line()]

    async def test_a_failed_append_to_one_copy_leaves_the_other_appended_and_a_rerun_finishes(self) -> None:
        local = InMemoryAppendOnlyRecord("local")
        bucket = InMemoryAppendOnlyRecord("bucket")
        bucket.fail_next_append = RuntimeError("the bucket refused the write")
        suppression = RecordedSuppressionList(local, bucket)

        with pytest.raises(RuntimeError):
            await suppression.append([suppress(FILE_A)])
        assert local.lines == [suppress(FILE_A).to_line()] and bucket.lines == []

        await suppression.reconcile()
        assert bucket.lines == local.lines

    async def test_the_local_file_and_the_bucket_merge_without_either_being_rewritten(
        self, tmp_path: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        local = local_suppression_list_file(tmp_path)
        bucket = ObjectStoreAppendOnlyRecord(
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client), SUPPRESSION_LIST_KEY
        )
        await local.append_lines([suppress(FILE_A).to_line()])
        await bucket.append_lines([suppress(FILE_B).to_line()])
        local_before = local.path.read_bytes()
        bucket_before = s3_client.get_object(Bucket=evidence_bucket, Key=SUPPRESSION_LIST_KEY)["Body"].read()

        await RecordedSuppressionList(local, bucket).reconcile()

        bucket_after = s3_client.get_object(Bucket=evidence_bucket, Key=SUPPRESSION_LIST_KEY)["Body"].read()
        assert local.path.read_bytes().startswith(local_before)
        assert bucket_after.startswith(bucket_before)
        assert set(local.path.read_bytes().splitlines()) == set(bucket_after.splitlines())


# ------------------------------------------------------------------------------------------------
# The port, as v2-e35-t05 will read it
# ------------------------------------------------------------------------------------------------


class TestReadableThroughThePort:
    async def test_every_implementation_is_the_port(self, tmp_path: Path) -> None:
        records: list[AppendOnlyRecord] = [
            InMemoryAppendOnlyRecord(),
            local_suppression_list_file(tmp_path),
            ObjectStoreAppendOnlyRecord(FsEvidenceObjectStore(tmp_path), SUPPRESSION_LIST_KEY),
        ]
        for record in records:
            assert isinstance(record, AppendOnlyRecord)
            suppression: SuppressionList = RecordedSuppressionList(record)
            log: RemovalLog = RecordedRemovalLog(record)
            assert isinstance(suppression, SuppressionList)
            assert isinstance(log, RemovalLog)

    async def test_a_reader_with_only_the_port_sees_the_current_state(self) -> None:
        async def tub_should_hide(suppression: SuppressionList, sha256: str) -> bool:
            return (await load_suppression_state(suppression)).suppresses_source(sha256)

        record = InMemoryAppendOnlyRecord()
        suppression = RecordedSuppressionList(record)
        await suppression.append([suppress(FILE_A)])
        assert await tub_should_hide(suppression, FILE_A)
        assert not await tub_should_hide(suppression, FILE_B)


def test_the_local_append_never_opens_the_file_for_writing_from_the_start() -> None:
    """The only flags the local adapter opens its file with include `O_APPEND` and never `O_TRUNC`."""
    from debate_core.integrations.local import suppression_list

    flags = suppression_list._APPEND_FLAGS  # pyright: ignore[reportPrivateUsage]
    assert flags & os.O_APPEND
    assert not flags & os.O_TRUNC

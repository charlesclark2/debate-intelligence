"""The path-hold record: what a line is, when a hold is in force, and where its copies are kept.

The record is `path-holds.jsonl`, beside the suppression list on this machine and in the bucket
(`v1-e30-t13`). These tests are about the record alone: the model, the state it becomes, and the
list that finds it beside its own copies. What a removal writes to it and what an import does with
it are `test_removal_path_hold_plan.py` and `test_removed_path_holds_later_imports.py`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from debate_core.application.caselist import suppression as suppression_module
from debate_core.application.caselist.suppression import (
    PATH_HOLDS_KEY,
    SUPPRESSION_LIST_KEY,
    LocalFallbackSuppressionList,
    ObjectStoreAppendOnlyRecord,
    RecordedSuppressionList,
    load_suppression_state,
)
from debate_core.application.errors import StoreAccessDenied, StoreCredentialsExpired
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.application.ports.suppression import (
    AppendOnlyViolation,
    PathHoldEntry,
    PathHoldList,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    UnreadableAppendOnlyRecord,
)
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.suppression_list import (
    local_path_holds_file,
    local_suppression_list_file,
)
from debate_core.testing.fakes import InMemoryAppendOnlyRecord

pytestmark = pytest.mark.anyio

REMOVED = "a" * 64
ANOTHER_REMOVED = "c" * 64
CASELIST = "testcl26"
PATH = "Alder Point/KR/Alder Point-KR-Aff-Lakeshore Open-Round 2.docx"
OTHER_PATH = "Birch Hill/MT/Birch Hill-MT-Neg-Lakeshore Open-Round 4.docx"
REMOVED_AT = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
FIRST_HELD = date(2026, 9, 8)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def path_digest(caselist: str, path: str) -> str:
    """The digest a path entry stores in place of the path, worked out here and not by the code."""
    return hashlib.sha256(f"{caselist}/{path}".encode()).hexdigest()


def hold(
    *,
    sha256: str = REMOVED,
    caselist: str = CASELIST,
    path: str = PATH,
    after: date = FIRST_HELD,
    recorded_at: datetime = REMOVED_AT,
    request_id: str = "RM-2026-01",
) -> PathHoldEntry:
    return PathHoldEntry(
        caselist=caselist,
        disclosure=path_digest(caselist, path),
        sha256=sha256,
        after_snapshot=after,
        recorded_at=recorded_at,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id=request_id,
    )


def suppressed(sha256: str = REMOVED, recorded_at: datetime = REMOVED_AT) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha256,
        recorded_at=recorded_at,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )


def unsuppressed(sha256: str = REMOVED, *, recorded_at: datetime) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.UNSUPPRESS,
        sha256=sha256,
        recorded_at=recorded_at,
        reason=ReasonCode.REMOVED_IN_ERROR,
    )


# ------------------------------------------------------------------------------------------------
# One line
# ------------------------------------------------------------------------------------------------


def test_a_path_entry_is_one_canonical_line_of_digests_dates_and_codes() -> None:
    assert json.loads(hold().to_line()) == {
        "schema_version": 1,
        "caselist": "testcl26",
        "disclosure": path_digest("testcl26", PATH),
        "sha256": REMOVED,
        "after_snapshot": "2026-09-08",
        "recorded_at": "2026-09-30T18:00:00Z",
        "reason": "REQUESTED_BY_TEAM",
        "request_id": "RM-2026-01",
    }
    assert PathHoldEntry.from_line(hold().to_line()) == hold()
    for name in ("Alder Point", "KR", "Lakeshore", "Round 2", ".docx"):
        assert name not in hold().to_line()


def test_a_path_entry_has_no_field_a_name_or_a_path_could_be_written_into() -> None:
    assert set(PathHoldEntry.model_fields) == {
        "schema_version",
        "caselist",
        "disclosure",
        "sha256",
        "after_snapshot",
        "recorded_at",
        "reason",
        "request_id",
    }
    line = json.loads(hold().to_line())
    with pytest.raises(ValidationError):
        PathHoldEntry.model_validate({**line, "path": PATH})
    with pytest.raises(ValidationError):
        PathHoldEntry.model_validate({**line, "disclosure": PATH})
    with pytest.raises(ValidationError):
        PathHoldEntry.model_validate({**line, "caselist": "Alder Point"})
    with pytest.raises(ValidationError):
        PathHoldEntry.model_validate({**line, "request_id": "the KR request"})


def test_a_path_entry_carries_a_removals_reason_and_never_a_reinstatements() -> None:
    with pytest.raises(ValidationError):
        PathHoldEntry.model_validate({**json.loads(hold().to_line()), "reason": "REMOVED_IN_ERROR"})


# ------------------------------------------------------------------------------------------------
# When a hold is in force
# ------------------------------------------------------------------------------------------------


def test_a_hold_stops_an_upload_at_its_path_in_a_snapshot_dated_after_it() -> None:
    state = SuppressionState.from_entries([suppressed()], [hold()])

    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 9, 9)) == hold()
    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 10, 8)) == hold()
    assert state.path_holds == (hold(),)


def test_a_snapshot_of_the_same_date_or_earlier_is_not_held() -> None:
    """An earlier snapshot holds an earlier version, and the dates cannot order one of the same day."""
    state = SuppressionState.from_entries([suppressed()], [hold()])

    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=FIRST_HELD) is None
    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 9, 1)) is None


def test_another_path_and_the_same_spelling_in_another_caselist_are_not_held() -> None:
    state = SuppressionState.from_entries([suppressed()], [hold()])

    assert state.path_hold(caselist=CASELIST, path=OTHER_PATH, snapshot=date(2026, 10, 8)) is None
    assert state.path_hold(caselist="testclb26", path=PATH, snapshot=date(2026, 10, 8)) is None


def test_an_unsuppress_of_the_removed_file_lifts_its_holds_and_no_others() -> None:
    later = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    other = hold(sha256=ANOTHER_REMOVED, path=OTHER_PATH)
    state = SuppressionState.from_entries(
        [suppressed(), suppressed(ANOTHER_REMOVED), unsuppressed(recorded_at=later)], [hold(), other]
    )

    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 10, 8)) is None
    assert state.path_hold(caselist=CASELIST, path=OTHER_PATH, snapshot=date(2026, 10, 8)) == other
    assert state.path_holds == (other,)


def test_an_unsuppress_at_the_same_instant_lifts_the_hold_as_it_lifts_the_suppression() -> None:
    state = SuppressionState.from_entries([suppressed(), unsuppressed(recorded_at=REMOVED_AT)], [hold()])

    assert not state.suppresses_source(REMOVED)
    assert state.path_holds == ()


def test_a_hold_recorded_after_an_unsuppress_is_in_force_because_the_file_was_removed_again() -> None:
    lifted = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    again = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
    second = hold(recorded_at=again, request_id="RM-2026-02")
    state = SuppressionState.from_entries(
        [suppressed(), unsuppressed(recorded_at=lifted), suppressed(recorded_at=again)], [hold(), second]
    )

    assert state.path_holds == (second,), "the first removal's hold stays lifted"
    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 10, 8)) == second


def test_two_removals_holding_one_path_count_an_upload_under_the_earlier_request() -> None:
    later = hold(
        sha256=ANOTHER_REMOVED,
        after=date(2026, 9, 15),
        recorded_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
        request_id="RM-2026-02",
    )
    state = SuppressionState.from_entries([suppressed(), suppressed(ANOTHER_REMOVED)], [later, hold()])

    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 10, 8)) == hold()
    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 9, 15)) == hold()


def test_holds_add_nothing_to_what_the_list_itself_suppresses() -> None:
    """A hold is asked with a path and a date. The checks older code makes by digest do not see it."""
    state = SuppressionState.from_entries([], [hold()])

    assert len(state) == 0
    assert not state.suppresses(REMOVED, disclosure=path_digest(CASELIST, PATH))
    assert not state.is_suppressed(REMOVED)
    assert state.latest == {}


# ------------------------------------------------------------------------------------------------
# Where the record is kept: beside every copy of the list
# ------------------------------------------------------------------------------------------------


def both_copies(tmp_path: Path) -> tuple[RecordedSuppressionList, Path, Path]:
    """The list over a local copy and a bucket's copy, the bucket being a directory here."""
    data_dir, bucket = tmp_path / "evidence", tmp_path / "bucket"
    listed = RecordedSuppressionList(
        local_suppression_list_file(data_dir),
        ObjectStoreAppendOnlyRecord(
            FsEvidenceObjectStore(bucket),
            SUPPRESSION_LIST_KEY,
            location=f"s3://bucket/{SUPPRESSION_LIST_KEY}",
        ),
    )
    return listed, data_dir, bucket


async def test_a_path_entry_is_appended_beside_the_list_in_both_places_and_nowhere_in_the_list(
    tmp_path: Path,
) -> None:
    listed, data_dir, bucket = both_copies(tmp_path)

    await listed.append([suppressed()])
    await listed.append_path_holds([hold()])

    local = data_dir / "suppression" / "path-holds.jsonl"
    remote = bucket / "objects" / "manifests" / "_suppression" / "path-holds.jsonl"
    assert local.read_text(encoding="utf-8") == hold().to_line() + "\n"
    assert remote.read_text(encoding="utf-8") == hold().to_line() + "\n"
    assert (data_dir / "suppression" / "suppression-list.jsonl").read_text(encoding="utf-8") == (
        suppressed().to_line() + "\n"
    )
    assert await listed.path_holds() == (hold(),)
    assert PATH_HOLDS_KEY == "manifests/_suppression/path-holds.jsonl"
    assert local_path_holds_file(data_dir).path == local


async def test_reading_a_list_that_holds_no_path_creates_nothing(tmp_path: Path) -> None:
    listed, data_dir, bucket = both_copies(tmp_path)

    assert await listed.path_holds() == ()
    await listed.append_path_holds([])
    assert (await load_suppression_state(listed)).path_holds == ()

    assert not data_dir.exists() and not bucket.exists()


async def test_each_copy_is_given_the_entries_the_other_holds(tmp_path: Path) -> None:
    listed, data_dir, _ = both_copies(tmp_path)
    earlier = hold(sha256=ANOTHER_REMOVED, path=OTHER_PATH)
    await local_path_holds_file(data_dir).append_lines([earlier.to_line()])

    await listed.append_path_holds([hold()])

    for record in listed.path_hold_records:
        assert set(await record.read_lines()) == {earlier.to_line(), hold().to_line()}, record.location
    assert [record.location for record in listed.path_hold_records] == [
        "the local path-hold list under storage.data_dir",
        "s3://bucket/manifests/_suppression/path-holds.jsonl",
    ]


async def test_a_line_that_cannot_be_read_refuses_the_record_by_its_role_and_never_its_path(
    tmp_path: Path,
) -> None:
    listed, data_dir, _ = both_copies(tmp_path)
    await local_path_holds_file(data_dir).append_lines(['{"schema_version":1,"path":"a name"}'])

    with pytest.raises(UnreadableAppendOnlyRecord) as refused:
        await load_suppression_state(listed)

    assert "the local path-hold list under storage.data_dir line 1 is not readable" in str(refused.value)
    assert str(tmp_path) not in str(refused.value) and "a name" not in str(refused.value)


class _Counting:
    """One credential's reach into a bucket, counting what it was asked to read and to write."""

    def __init__(self, bucket: FsEvidenceObjectStore) -> None:
        self._bucket = bucket
        self.reads = 0
        self.writes = 0

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        self.reads += 1
        return await self._bucket.get_file(key, destination)

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        self.writes += 1
        return await self._bucket.put_file(key, source)


async def test_the_bucket_copy_is_read_and_written_with_the_credentials_the_list_is(tmp_path: Path) -> None:
    """A removal appends with the takedown credential and reads with the everyday one."""
    bucket = FsEvidenceObjectStore(tmp_path / "bucket")
    takedown, everyday = _Counting(bucket), _Counting(bucket)
    the_list = ObjectStoreAppendOnlyRecord(takedown, SUPPRESSION_LIST_KEY, reader=everyday)  # pyright: ignore[reportArgumentType]

    beside = the_list.beside("path-holds.jsonl", called="path-hold list")
    await beside.append_lines([hold().to_line()])

    assert beside.key == PATH_HOLDS_KEY
    assert await beside.read_lines() == (hold().to_line(),)
    assert (takedown.writes, takedown.reads) == (1, 0)
    assert everyday.writes == 0 and everyday.reads >= 2


class _ListWithNoHolds:
    """A suppression list as the port alone describes one: entries, and nothing beside them."""

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        return ()

    async def append(self, entries: object) -> None:
        raise AssertionError("nothing here appends to the list")


async def test_a_list_whose_copies_keep_no_record_beside_them_holds_no_path() -> None:
    """A test's in-memory list, and what a build from before this task reads: the list alone."""
    listed = RecordedSuppressionList(InMemoryAppendOnlyRecord("an in-memory list"))

    assert await listed.path_holds() == ()
    assert (await load_suppression_state(listed)).path_holds == ()
    await listed.append_path_holds([])
    with pytest.raises(AppendOnlyViolation):
        await listed.append_path_holds([hold()])
    with pytest.raises(AppendOnlyViolation):
        await LocalFallbackSuppressionList(_ListWithNoHolds(), local=listed).append_path_holds([hold()])


def test_every_suppression_list_the_platform_builds_keeps_the_path_holds() -> None:
    """A list class that forgot them would import a held upload without a word."""
    lists = [
        one
        for _, one in inspect.getmembers(suppression_module, inspect.isclass)
        if one.__module__ == suppression_module.__name__ and one.__name__.endswith("SuppressionList")
    ]
    assert all(issubclass(one, SuppressionList) for one in lists)

    assert {one.__name__ for one in lists} == {"RecordedSuppressionList", "LocalFallbackSuppressionList"}
    assert all(issubclass(one, PathHoldList) for one in lists)


# ------------------------------------------------------------------------------------------------
# The weekly pull without a login
# ------------------------------------------------------------------------------------------------


class _BucketNeedingALogin:
    """An evidence bucket whose session has run out: every read refuses the same way."""

    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        raise self.failure

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        raise self.failure

    async def head(self, key: ObjectKey) -> ObjectInfo:
        raise self.failure

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        raise self.failure


def the_pulls_list(tmp_path: Path, failure: Exception) -> LocalFallbackSuppressionList:
    data_dir = tmp_path / "evidence"
    local = RecordedSuppressionList(local_suppression_list_file(data_dir))
    union = RecordedSuppressionList(
        local_suppression_list_file(data_dir),
        ObjectStoreAppendOnlyRecord(_BucketNeedingALogin(failure), SUPPRESSION_LIST_KEY),  # pyright: ignore[reportArgumentType]
    )
    return LocalFallbackSuppressionList(union, local=local)


async def test_without_a_login_the_pull_reads_the_holds_from_this_machine_and_says_so(tmp_path: Path) -> None:
    expired = StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")
    listed = the_pulls_list(tmp_path, expired)
    await local_suppression_list_file(tmp_path / "evidence").append_lines([suppressed().to_line()])
    await local_path_holds_file(tmp_path / "evidence").append_lines([hold().to_line()])

    state = await load_suppression_state(listed)

    assert state.suppresses_source(REMOVED)
    assert state.path_hold(caselist=CASELIST, path=PATH, snapshot=date(2026, 10, 8)) == hold()
    assert listed.fallbacks >= 1
    assert listed.local_only_reason is not None and "without a login" in listed.local_only_reason


async def test_a_bucket_that_refuses_for_any_other_reason_still_fails_the_read(tmp_path: Path) -> None:
    """A missing grant is not a login that timed out: a list nobody can read cannot be honoured."""
    denied = StoreAccessDenied("GetObject", f"s3://bucket/{PATH_HOLDS_KEY}")
    listed = the_pulls_list(tmp_path, denied)

    with pytest.raises(StoreAccessDenied):
        await listed.path_holds()
    assert listed.fallbacks == 0


async def test_the_pulls_list_never_appends_a_hold_to_this_machines_copy_alone(tmp_path: Path) -> None:
    expired = StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")
    listed = the_pulls_list(tmp_path, expired)

    with pytest.raises(StoreCredentialsExpired):
        await listed.append_path_holds([hold()])

    assert not local_path_holds_file(tmp_path / "evidence").path.exists()

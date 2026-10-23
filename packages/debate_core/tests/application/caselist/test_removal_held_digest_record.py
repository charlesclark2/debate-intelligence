"""The held-digest record: what a line is, and which copies an import and a removal write (`v1-e30-t23`).

The record is `held-digests.jsonl`, beside the path holds on this machine and in the bucket. An
import appends the uploads it refused at a held path to this machine's copy alone; a removal, which
holds every copy, gives each the lines it lacks. What an import writes to it and what a removal does
with it are `test_removal_lists_held_digests.py`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from debate_core.application.caselist import suppression as suppression_module
from debate_core.application.caselist.suppression import (
    HELD_DIGESTS_KEY,
    SUPPRESSION_LIST_KEY,
    LocalFallbackSuppressionList,
    ObjectStoreAppendOnlyRecord,
    RecordedSuppressionList,
    read_held_digests,
    record_held_digests,
)
from debate_core.application.errors import StoreAccessDenied, StoreCredentialsExpired
from debate_core.application.ports.suppression import (
    AppendOnlyViolation,
    HeldDigestEntry,
    HeldDigestList,
    SuppressionEntry,
)
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord

from .test_suppression_path_holds import _BucketNeedingALogin  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.anyio

HELD_UPLOAD = "b" * 64
PATH = "Alder Point/KR/Alder Point-KR-Aff-Lakeshore Open-Round 2.docx"
HELD_PATH = hashlib.sha256(f"testcl26/{PATH}".encode()).hexdigest()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def held(sha256: str = HELD_UPLOAD, request_id: str = "RM-2026-01") -> HeldDigestEntry:
    return HeldDigestEntry(sha256=sha256, disclosure=HELD_PATH, request_id=request_id)


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
    return listed, data_dir / "suppression" / "held-digests.jsonl", bucket / "objects" / HELD_DIGESTS_KEY


# ------------------------------------------------------------------------------------------------
# A line
# ------------------------------------------------------------------------------------------------


def test_a_line_is_two_digests_and_a_request_id_and_nothing_else() -> None:
    assert json.loads(held().to_line()) == {
        "schema_version": 1,
        "sha256": HELD_UPLOAD,
        "disclosure": HELD_PATH,
        "request_id": "RM-2026-01",
    }
    assert held().to_line() == (
        f'{{"disclosure":"{HELD_PATH}","request_id":"RM-2026-01","schema_version":1,"sha256":"{HELD_UPLOAD}"}}'
    )


@pytest.mark.parametrize(
    "extra",
    [{"path": PATH}, {"school": "Alder Point"}, {"team_code": "KR"}, {"file_name": "Round 2.docx"}],
)
def test_a_line_has_no_field_a_name_or_a_path_could_be_written_into(extra: dict[str, str]) -> None:
    line = json.loads(held().to_line()) | extra
    with pytest.raises(ValidationError):
        HeldDigestEntry.from_line(json.dumps(line))


@pytest.mark.parametrize("request_id", ["Maple Grove QX", "RM-2026-01 Alder Point", ""])
def test_the_request_id_is_the_registers_and_cannot_carry_a_name(request_id: str) -> None:
    with pytest.raises(ValidationError):
        held(request_id=request_id)


# ------------------------------------------------------------------------------------------------
# Where it is kept, and who writes which copy
# ------------------------------------------------------------------------------------------------


async def test_the_union_appends_beside_the_path_holds_in_both_places(tmp_path: Path) -> None:
    """What a removal's list does: every copy, by the set-union rule the other records follow."""
    listed, local, remote = both_copies(tmp_path)

    await listed.append_held_digests([held()])
    await listed.append_held_digests([held()])

    assert local.read_text(encoding="utf-8") == remote.read_text(encoding="utf-8") == held().to_line() + "\n"
    assert await read_held_digests(listed) == (held(),)
    assert HELD_DIGESTS_KEY == "manifests/_suppression/held-digests.jsonl"


async def test_a_removal_gives_the_bucket_what_this_machines_imports_recorded(tmp_path: Path) -> None:
    listed, local, remote = both_copies(tmp_path)
    await RecordedSuppressionList(local_suppression_list_file(tmp_path / "evidence")).append_held_digests(
        [held()]
    )
    assert not remote.exists()

    await listed.append_held_digests(())

    assert remote.read_text(encoding="utf-8") == local.read_text(encoding="utf-8")


async def test_the_pulls_list_appends_to_this_machines_copy_alone_with_a_login(tmp_path: Path) -> None:
    """The everyday credential may not write under the bucket's `manifests/_suppression/`."""
    union, local, remote = both_copies(tmp_path)
    listed = LocalFallbackSuppressionList(
        union, local=RecordedSuppressionList(local_suppression_list_file(tmp_path / "evidence"))
    )

    await record_held_digests(listed, [held()])

    assert local.read_text(encoding="utf-8") == held().to_line() + "\n"
    assert not remote.exists()


async def test_the_pulls_list_appends_without_a_login_and_reads_this_machines_copy(tmp_path: Path) -> None:
    expired = StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")
    data_dir = tmp_path / "evidence"
    union = RecordedSuppressionList(
        local_suppression_list_file(data_dir),
        ObjectStoreAppendOnlyRecord(_BucketNeedingALogin(expired), SUPPRESSION_LIST_KEY),  # pyright: ignore[reportArgumentType]
    )
    listed = LocalFallbackSuppressionList(
        union, local=RecordedSuppressionList(local_suppression_list_file(data_dir))
    )

    await listed.append_held_digests([held()])

    assert await listed.held_digests() == (held(),)
    assert listed.fallbacks == 1


async def test_a_bucket_that_refuses_for_any_other_reason_still_fails_the_read(tmp_path: Path) -> None:
    denied = StoreAccessDenied("GetObject", f"s3://bucket/{HELD_DIGESTS_KEY}")
    union = RecordedSuppressionList(
        local_suppression_list_file(tmp_path / "evidence"),
        ObjectStoreAppendOnlyRecord(_BucketNeedingALogin(denied), SUPPRESSION_LIST_KEY),  # pyright: ignore[reportArgumentType]
    )
    listed = LocalFallbackSuppressionList(
        union, local=RecordedSuppressionList(local_suppression_list_file(tmp_path / "evidence"))
    )

    with pytest.raises(StoreAccessDenied):
        await listed.held_digests()


async def test_reading_or_appending_nothing_creates_nothing(tmp_path: Path) -> None:
    listed, local, remote = both_copies(tmp_path)

    assert await listed.held_digests() == ()
    await record_held_digests(listed, [])
    await listed.append_held_digests(())

    assert not local.exists() and not remote.exists()


async def test_a_list_that_keeps_no_record_beside_it_refuses_an_entry_rather_than_dropping_it() -> None:
    """An import that lost the only record of the bytes would let them back in at another path."""
    listed = RecordedSuppressionList(InMemoryAppendOnlyRecord("an in-memory list"))

    assert await listed.held_digests() == ()
    with pytest.raises(AppendOnlyViolation):
        await record_held_digests(listed, [held()])


class _AListOfLinesAlone:
    """A suppression list that is not a held-digest list at all, as a build's own fake might be."""

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        return ()

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:
        raise AssertionError("nothing here appends to the list")


async def test_a_list_of_another_kind_refuses_an_entry_too() -> None:
    with pytest.raises(AppendOnlyViolation):
        await record_held_digests(_AListOfLinesAlone(), [held()])
    await record_held_digests(_AListOfLinesAlone(), [])


def test_every_suppression_list_the_platform_builds_keeps_the_held_digests() -> None:
    lists = [
        one
        for _, one in inspect.getmembers(suppression_module, inspect.isclass)
        if one.__module__ == suppression_module.__name__ and one.__name__.endswith("SuppressionList")
    ]

    assert {one.__name__ for one in lists} == {"RecordedSuppressionList", "LocalFallbackSuppressionList"}
    assert all(issubclass(one, HeldDigestList) for one in lists)

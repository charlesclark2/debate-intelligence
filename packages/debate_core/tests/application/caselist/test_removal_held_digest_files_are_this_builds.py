"""The stored held-digest record is what this build writes, and names no one (`v1-e30-t23`).

`stored_suppression_lists/held_digests_written_by_this_build/` is what `held_digest_scenario.py`
leaves on this machine and in the bucket, written by `write_held_digest_files.py`.
`check_an_older_build_reads_this_builds_files.py` puts these files where an older build keeps its
records, and runs that build over them. This test holds the stored files to what this build writes,
so that check is always run over the record as it really is.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST

from .conftest import RemovalWorld
from .held_digest_scenario import (
    HELD_UPLOAD_BODY,
    an_upload_held_and_the_removal_run_again,
    held_digest_records,
)
from .suppression_list_scenario import REMOVED_BY_SOURCE_PATH, SECOND_REQUEST

pytestmark = pytest.mark.anyio

STORED = Path(__file__).parent / "stored_suppression_lists" / "held_digests_written_by_this_build"

#: The one line, worked out here from the fixture: the upload's bytes, the removed path, the request.
THE_LINE = {
    "schema_version": 1,
    "sha256": hashlib.sha256(HELD_UPLOAD_BODY).hexdigest(),
    "disclosure": hashlib.sha256(f"{SYNTHETIC_CASELIST}/{REMOVED_BY_SOURCE_PATH}".encode()).hexdigest(),
    "request_id": SECOND_REQUEST,
}


def stored() -> dict[str, bytes]:
    return {
        path.relative_to(STORED).as_posix(): path.read_bytes() for path in sorted(STORED.rglob("*.jsonl"))
    }


async def test_this_build_still_writes_the_stored_files_byte_for_byte(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    await an_upload_held_and_the_removal_run_again(removal_world, tmp_path / "arriving")

    assert held_digest_records(removal_world) == stored()


def test_each_copy_is_the_one_line_for_the_upload_held_at_the_removed_path() -> None:
    assert sorted(stored()) == ["bucket/held-digests.jsonl", "local/held-digests.jsonl"]
    for name, body in stored().items():
        assert [json.loads(line) for line in body.decode("utf-8").splitlines()] == [THE_LINE], name


def test_the_stored_files_name_no_school_team_path_or_file() -> None:
    for body in stored().values():
        for name in (*REMOVED_BY_SOURCE_PATH.split("/"), ".docx", ".zip"):
            assert name.encode() not in body

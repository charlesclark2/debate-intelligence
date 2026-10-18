"""Writes `stored_suppression_lists/held_digests_written_by_this_build/`: this build's held-digest record.

Not collected: its name is not a test module's, and it is only ever run by its path, with this
build's source. `stored_suppression_lists/README.md` gives the command. It refuses to run without
the variable, because it overwrites the stored files.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from .conftest import RemovalWorld
from .held_digest_scenario import an_upload_held_and_the_removal_run_again, held_digest_records

pytestmark = pytest.mark.anyio

STORED = Path(__file__).parent / "stored_suppression_lists" / "held_digests_written_by_this_build"


async def test_write_what_this_build_leaves_in_the_held_digest_record(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    assert os.environ.get("WRITE_HELD_DIGEST_FILES") == "this-build", (
        "this rewrites the stored files; see stored_suppression_lists/README.md"
    )

    await an_upload_held_and_the_removal_run_again(removal_world, tmp_path / "arriving")

    for name, body in held_digest_records(removal_world).items():
        target = STORED / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

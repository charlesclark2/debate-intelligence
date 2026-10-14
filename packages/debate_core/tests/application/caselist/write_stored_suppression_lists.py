"""Writes one directory of `stored_suppression_lists/`: what one build left in the takedown's records.

Not collected: its name is not a test module's, and it is only ever run by its path, with the source
of the build whose files it is to store first on `PYTHONPATH`. `stored_suppression_lists/README.md`
gives the three commands. It refuses to run without saying which build that is, because it
overwrites the stored files.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from .conftest import RemovalWorld
from .suppression_list_scenario import a_team_removal_a_source_removal_and_an_unsuppress, takedown_records

pytestmark = pytest.mark.anyio

STORED = Path(__file__).parent / "stored_suppression_lists"
WRITTEN_BY = {
    "the-installed-build": "written_by_the_installed_build",
    "the-start-commit": "written_by_the_start_commit",
    "this-build": "written_by_this_build",
}


async def test_write_what_this_source_leaves_in_the_takedowns_records(removal_world: RemovalWorld) -> None:
    build = os.environ.get("WRITE_STORED_SUPPRESSION_LISTS", "")
    assert build in WRITTEN_BY, "this rewrites the stored files; see stored_suppression_lists/README.md"

    await a_team_removal_a_source_removal_and_an_unsuppress(removal_world)

    directory = STORED / WRITTEN_BY[build]
    for stale in directory.rglob("*.jsonl") if directory.exists() else ():
        stale.unlink()
    for name, body in takedown_records(removal_world).items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

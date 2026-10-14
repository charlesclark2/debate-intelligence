"""Writes one file of `stored_camp_manifests/`: the camp release manifest one build's pull writes.

Not collected: its name is not a test module's, and it is only ever run by its path, with the source
of the build whose manifest it is to store first on `PYTHONPATH`. `stored_camp_manifests/README.md`
gives the three commands. It refuses to run without saying which build that is, because it
overwrites the stored file.
"""

from __future__ import annotations

import os

import pytest

from .camp_manifest_scenario import MANIFEST_NAME, STORED, release_manifest, two_pulls
from .conftest import RemovalWorld

pytestmark = pytest.mark.anyio

WRITTEN_BY = {
    "the-installed-build": "written_by_the_installed_build",
    "the-start-commit": "written_by_the_start_commit",
    "this-build": "written_by_this_build",
}


async def test_write_the_release_manifest_this_sources_pull_writes(removal_world: RemovalWorld) -> None:
    build = os.environ.get("WRITE_STORED_CAMP_MANIFESTS", "")
    assert build in WRITTEN_BY, "this rewrites the stored files; see stored_camp_manifests/README.md"

    await two_pulls(removal_world)

    target = STORED / WRITTEN_BY[build] / MANIFEST_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(release_manifest(removal_world).read_bytes())

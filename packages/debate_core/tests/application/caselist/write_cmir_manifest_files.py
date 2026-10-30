"""The `.cmir` week as this build imports it (`v1-e30-t26`), for earlier builds to read.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_CMIR_MANIFEST_FILES` set to the directory to write into. It imports the week of
`test_a_cmir_file_is_imported_as_cmir.py` into `<directory>/evidence` with this build's importer
and writes its manifest, whose `.cmir` row carries `"format": "CMIR"`. Then
`check_an_older_build_reads_a_cmir_manifest.py` reads that data directory with each build. The
commands and what they printed are in the session report of `v1-e30-t26`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from .test_a_cmir_file_is_imported_as_cmir import CMIR_PATH, import_cmir_week, member_rows

pytestmark = pytest.mark.anyio


async def test_write_the_cmir_week(tmp_path: Path) -> None:
    where = os.environ.get("WRITE_CMIR_MANIFEST_FILES")
    if not where:
        pytest.fail("set WRITE_CMIR_MANIFEST_FILES to the directory to write into")
    data_dir = Path(where) / "evidence"
    assert not data_dir.exists(), f"{data_dir} is already there; give a new directory"

    manifest = await import_cmir_week(data_dir, tmp_path / "zips")

    assert member_rows(manifest)[CMIR_PATH]["format"] == "CMIR"
    print(json.dumps({"manifest": str(manifest.relative_to(data_dir)), "cmir_format": "CMIR"}))

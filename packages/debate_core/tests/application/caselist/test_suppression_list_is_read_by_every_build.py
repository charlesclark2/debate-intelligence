"""The suppression list this build writes is one every installed build reads, and the reverse.

A line of the list forbids unknown keys and pins `schema_version` to `1`, and a reader refuses the
whole list at the first line it cannot validate. So does every build already installed: the weekly
agent's (`0.1.0.dev60`) and the one at the commit this task started from (`v0.1.0-dev.119`). An
import against a list it cannot read fails closed, which for the agent is a weekly run that stops.
No line of another shape may ever be written to the list, and none is: the paths a removal holds
(`v1-e30-t13`) are in `path-holds.jsonl`, beside the list, which no older build opens.

## What is compared with what

`stored_suppression_lists/` holds what each build says and wrote, none of it written by hand
(its `README.md` says how each file was made):

* `line_schemas_of_the_installed_build.json`, `line_schemas_of_the_start_commit.json`: the JSON
  Schema of a suppression-list line and of a removal-log line, printed by each build's own code.
* `written_by_the_installed_build/`, `written_by_the_start_commit/`, `written_by_this_build/`: the
  takedown's records as each build left them after the same history
  (`suppression_list_scenario.py`), on this machine and in the bucket.

**An older build reads what this build writes.** The list and the removal log this build writes
are byte for byte the ones each older build wrote for the same history, in both places; every line
validates against each older build's own schema; and what this build adds is one more file beside
them. `check_an_older_build_reads_this_builds_files.py` runs an older build's own importer,
publisher and status over these files, and the README records what it printed.

**This build reads what an older build wrote.** Each stored list reads back to the state written
out below by hand, with no path held, and serialises again to the bytes it was read from.

The scenario and the records it leaves are the invented archives of `tests/fixtures/`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest

from debate_core.application.caselist.suppression import (
    SUPPRESSION_LIST_KEY,
    ObjectStoreAppendOnlyRecord,
    RecordedRemovalLog,
    RecordedSuppressionList,
    load_suppression_state,
)
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    RemovalLogEntry,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)

from .conftest import RemovalWorld
from .suppression_list_scenario import (
    REMOVED_BY_SOURCE,
    REMOVED_BY_SOURCE_PATH,
    REMOVED_WITH_THE_TEAM,
    UNSUPPRESSED,
    WITHDRAWN_FROM_THE_TEAM,
    a_team_removal_a_source_removal_and_an_unsuppress,
    takedown_records,
)

pytestmark = pytest.mark.anyio

STORED = Path(__file__).parent / "stored_suppression_lists"
THIS_BUILD = STORED / "written_by_this_build"
OLDER_BUILDS = {
    "the installed build": STORED / "written_by_the_installed_build",
    "the start commit": STORED / "written_by_the_start_commit",
}
SCHEMAS = {
    "the installed build": STORED / "line_schemas_of_the_installed_build.json",
    "the start commit": STORED / "line_schemas_of_the_start_commit.json",
}

THE_LIST = "suppression-list.jsonl"
THE_LOG = "removal-log.jsonl"
THE_PATH_HOLDS = "path-holds.jsonl"
PLACES = ("local", "bucket")

#: What the stored history leaves suppressed, written from `suppression_list_scenario.py`'s
#: docstring: the team's three files less the one let back in, and the one removed by `--source`.
SUPPRESSED_WHOLE = {*REMOVED_WITH_THE_TEAM, REMOVED_BY_SOURCE} - {UNSUPPRESSED}
THE_TEAMS_PATHS_OF_THE_SHARED_FILE = (
    "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
    "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx",
)


def schemas_of(build: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(SCHEMAS[build].read_text(encoding="utf-8")))


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# ------------------------------------------------------------------------------------------------
# The stored files are what this build writes
# ------------------------------------------------------------------------------------------------


async def test_this_build_still_writes_the_stored_files_byte_for_byte(removal_world: RemovalWorld) -> None:
    await a_team_removal_a_source_removal_and_an_unsuppress(removal_world)

    written = takedown_records(removal_world)

    stored = {
        f"{place}/{path.name}": path.read_bytes()
        for place in PLACES
        for path in sorted((THIS_BUILD / place).iterdir())
    }
    assert sorted(written) == sorted(stored)
    assert written == stored


# ------------------------------------------------------------------------------------------------
# An older build reads what this build writes
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("build", sorted(OLDER_BUILDS))
@pytest.mark.parametrize("record", [THE_LIST, THE_LOG])
@pytest.mark.parametrize("place", PLACES)
def test_the_list_and_the_log_this_build_writes_are_the_ones_an_older_build_wrote(
    build: str, record: str, place: str
) -> None:
    """Byte for byte, on this machine and in the bucket: an older build is reading its own file."""
    assert (THIS_BUILD / place / record).read_bytes() == (OLDER_BUILDS[build] / place / record).read_bytes()


@pytest.mark.parametrize("build", sorted(SCHEMAS))
def test_every_line_this_build_writes_to_the_list_is_one_an_older_builds_schema_accepts(build: str) -> None:
    schemas = schemas_of(build)

    for place in PLACES:
        listed = lines_of(THIS_BUILD / place / THE_LIST)
        assert len(listed) == 7
        for line in listed:
            jsonschema.validate(json.loads(line), schemas["suppression_list_line"])
        for line in lines_of(THIS_BUILD / place / THE_LOG):
            jsonschema.validate(json.loads(line), schemas["removal_log_line"])


def test_an_older_build_validates_a_line_with_the_model_this_build_validates_it_with() -> None:
    """Schema for schema, so what one accepts the other accepts, and what one refuses the other refuses."""
    ours = {
        "suppression_list_line": SuppressionEntry.model_json_schema(),
        "removal_log_line": RemovalLogEntry.model_json_schema(),
    }

    for build in SCHEMAS:
        assert schemas_of(build) == json.loads(json.dumps(ours)), build
    assert SCHEMAS["the installed build"].read_bytes() == SCHEMAS["the start commit"].read_bytes()


@pytest.mark.parametrize("build", sorted(SCHEMAS))
def test_a_path_entry_is_a_line_an_older_build_would_refuse_which_is_why_it_is_not_in_the_list(
    build: str,
) -> None:
    """Had it been written to the list, the older build's reader would have refused the whole list."""
    (entry,) = lines_of(THIS_BUILD / "local" / THE_PATH_HOLDS)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(json.loads(entry), schemas_of(build)["suppression_list_line"])


def test_what_this_build_adds_is_one_file_beside_the_list_in_each_place() -> None:
    for place in PLACES:
        ours = {path.name for path in (THIS_BUILD / place).iterdir()}
        for build, directory in OLDER_BUILDS.items():
            theirs = {path.name for path in (directory / place).iterdir()}
            assert theirs == {THE_LIST, THE_LOG}, build
            assert ours - theirs == {THE_PATH_HOLDS}, build
    assert (THIS_BUILD / "local" / THE_PATH_HOLDS).read_bytes() == (
        THIS_BUILD / "bucket" / THE_PATH_HOLDS
    ).read_bytes()


def test_the_one_path_entry_is_for_the_file_removed_by_source_and_names_no_one() -> None:
    (line,) = lines_of(THIS_BUILD / "local" / THE_PATH_HOLDS)

    assert json.loads(line) == {
        "schema_version": 1,
        "caselist": "testcl26",
        "disclosure": disclosure_digest("testcl26", REMOVED_BY_SOURCE_PATH),
        "sha256": REMOVED_BY_SOURCE,
        "after_snapshot": "2026-09-08",
        "recorded_at": "2026-09-30T18:00:00Z",
        "reason": "REQUESTED_BY_SCHOOL",
        "request_id": "RM-2026-02",
    }
    for name in ("Riverbend", "MnPr", "Seaside", "Finals", ".docx", "Maple Grove", "QX"):
        assert name not in line


# ------------------------------------------------------------------------------------------------
# This build reads what an older build wrote
# ------------------------------------------------------------------------------------------------


def copies_of(directory: Path, scratch: Path) -> tuple[Path, FsEvidenceObjectStore]:
    """An older build's stored files, put where this build keeps the takedown's records."""
    data_dir = scratch / "evidence"
    (data_dir / "suppression").mkdir(parents=True)
    for stored in (directory / "local").iterdir():
        (data_dir / "suppression" / stored.name).write_bytes(stored.read_bytes())
    bucket = FsEvidenceObjectStore(scratch / "bucket")
    for stored in (directory / "bucket").iterdir():
        target = bucket.path_for(f"manifests/_suppression/{stored.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stored.read_bytes())
    return data_dir, bucket


@pytest.mark.parametrize("build", sorted(OLDER_BUILDS))
async def test_this_build_reads_the_list_an_older_build_wrote(build: str, tmp_path: Path) -> None:
    data_dir, bucket = copies_of(OLDER_BUILDS[build], tmp_path)
    listed = RecordedSuppressionList(
        local_suppression_list_file(data_dir), ObjectStoreAppendOnlyRecord(bucket, SUPPRESSION_LIST_KEY)
    )

    state = await load_suppression_state(listed)

    assert state.sources == SUPPRESSED_WHOLE
    assert state.disclosures == {
        (WITHDRAWN_FROM_THE_TEAM, disclosure_digest("testcl26", path))
        for path in THE_TEAMS_PATHS_OF_THE_SHARED_FILE
    }
    assert not state.is_suppressed(UNSUPPRESSED)
    assert state.path_holds == (), "an older build wrote no path entry, and none is invented for it"
    assert (
        state.path_hold(caselist="testcl26", path=REMOVED_BY_SOURCE_PATH, snapshot=date(2026, 10, 8)) is None
    )
    assert [entry.to_line() for entry in await listed.entries()] == lines_of(
        OLDER_BUILDS[build] / "local" / THE_LIST
    )
    before = {path.name: path.read_bytes() for path in (data_dir / "suppression").iterdir()}
    await listed.reconcile()
    assert {path.name: path.read_bytes() for path in (data_dir / "suppression").iterdir()} == before


@pytest.mark.parametrize("build", sorted(OLDER_BUILDS))
async def test_this_build_reads_the_removal_log_an_older_build_wrote(build: str, tmp_path: Path) -> None:
    data_dir, _ = copies_of(OLDER_BUILDS[build], tmp_path)

    entries = await RecordedRemovalLog(local_removal_log_file(data_dir)).entries()

    assert [(str(entry.kind), entry.request_id) for entry in entries] == [
        ("REMOVAL", "RM-2026-01"),
        ("REMOVAL", "RM-2026-02"),
        ("UNSUPPRESS", "RM-2026-01"),
    ]
    assert [entry.to_line() for entry in entries] == lines_of(OLDER_BUILDS[build] / "local" / THE_LOG)


async def test_this_build_reads_its_own_files_back_with_the_one_path_held(tmp_path: Path) -> None:
    data_dir, bucket = copies_of(THIS_BUILD, tmp_path)
    listed = RecordedSuppressionList(
        local_suppression_list_file(data_dir), ObjectStoreAppendOnlyRecord(bucket, SUPPRESSION_LIST_KEY)
    )

    state = await load_suppression_state(listed)

    assert state.sources == SUPPRESSED_WHOLE
    (held,) = state.path_holds
    assert held == PathHoldEntry.from_line(lines_of(THIS_BUILD / "local" / THE_PATH_HOLDS)[0])
    assert (
        state.path_hold(caselist="testcl26", path=REMOVED_BY_SOURCE_PATH, snapshot=date(2026, 10, 8)) == held
    )

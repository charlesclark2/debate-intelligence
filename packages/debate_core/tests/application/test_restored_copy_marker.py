"""The marker a restored copy carries at its root (`v1-e40-t21`).

:class:`~debate_core.application.caselist.run_state_restore.RunStateRestore` alone, with stand-ins for
the run state, the suppression list and the raw sources, so that each rule is tested on its own. The
whole command, against moto, is `debate_cli/tests/bucket_mode/test_restore_run_state.py`; the
runbooks' search for the marker is `tests/docs/test_restored_copy_search.py`. What is here:

* a restored copy holds the marker, and the marker holds the environment, the bucket, the time of the
  restore and the build's tag, and nothing else: no caselist, no path;
* the marker is in place before the first thing restored, so a restore that stops part-way leaves a
  whole marker beside what it restored, and a stop while the marker itself is written leaves none;
* a refused directory, the data directory among them, is never given one.

Every slug, bucket and tag here is invented.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pytest

from debate_core.application.caselist import run_state_restore
from debate_core.application.caselist.run_state import RestoreReport, RunState
from debate_core.application.caselist.run_state_restore import (
    RESTORED_COPY_MARKER,
    RestoredCopyMarker,
    RestoreTargetRefused,
    RunStateRestore,
)
from debate_core.application.caselist.run_state_sources import RestoredSources
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import BlobIntegrityError

CASELIST: Final = "samplecl26"
BUCKET: Final = "debate-dev-evidence-sample"
TAG: Final = "v1.8.0-dev.201"
RESTORED_AT: Final = datetime(2026, 11, 6, 14, 3, 9, tzinfo=UTC)
ALLOWED_FIELDS: Final = {"environment", "bucket", "restored_at", "build_tag"}


class StateStandIn:
    """The run state over the copy: writes one file, then stops when told to."""

    def __init__(self, directory: Path, *, stop: bool) -> None:
        self.directory = directory
        self.stop = stop
        self.marker_when_restore_began: bool | None = None

    async def restore(self, caselists: Sequence[str], *, parsed_version: str | None) -> RestoreReport:
        self.marker_when_restore_began = (self.directory / RESTORED_COPY_MARKER).is_file()
        (self.directory / "debate.sqlite3").write_bytes(b"a restored database\n")
        if self.stop:
            raise BlobIntegrityError("parsed/samplecl26/v1/part.jsonl", "0" * 64)
        return RestoreReport(started_at=RESTORED_AT, finished_at=RESTORED_AT, state_files=())

    async def local_manifests(self) -> list[object]:
        return []


class SuppressionStandIn:
    async def reconcile(self) -> None:
        return None

    async def entries(self) -> list[object]:
        return []


class World:
    def __init__(self, tmp_path: Path, *, stop: bool = False) -> None:
        self.live = tmp_path / "home" / ".debate-research" / "dev"
        self.live.mkdir(parents=True)
        self.states: list[StateStandIn] = []
        self.stop = stop

    def state_in(self, directory: Path) -> RunState:
        state = StateStandIn(directory, stop=self.stop)
        self.states.append(state)
        return cast("RunState", state)

    def restore(self, *, build_tag: str | None = TAG) -> RunStateRestore:
        def suppression_in(directory: Path) -> RecordedSuppressionList:
            return cast("RecordedSuppressionList", SuppressionStandIn())

        def sources_in(directory: Path) -> RestoredSources:  # pragma: no cover - no test asks for sources
            raise AssertionError("sources were not asked for")

        return RunStateRestore(
            state_in=self.state_in,
            suppression_in=suppression_in,
            sources_in=sources_in,
            live_data_dir=self.live,
            parsed_version="v1",
            environment="dev",
            bucket=BUCKET,
            build_tag=build_tag,
            clock=lambda: RESTORED_AT,
        )


def marker_in(directory: Path) -> dict[str, Any]:
    return json.loads((directory / RESTORED_COPY_MARKER).read_text(encoding="utf-8"))


def test_a_restored_copy_holds_the_marker_with_the_environment_bucket_time_and_tag_only(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    copy = tmp_path / "home" / "a" / "b" / "c" / "d" / "copy-samplecl26"

    asyncio.run(world.restore().restore(copy, [CASELIST]))

    assert marker_in(copy) == {
        "environment": "dev",
        "bucket": BUCKET,
        "restored_at": "2026-11-06T14:03:09Z",
        "build_tag": TAG,
    }
    text = (copy / RESTORED_COPY_MARKER).read_text(encoding="utf-8")
    assert CASELIST not in text, "no caselist slug, though the copy's own name holds one"
    assert str(tmp_path) not in text and "copy-" not in text, "no path"


def test_a_source_checkouts_marker_has_no_tag_and_still_only_the_allowed_fields(tmp_path: Path) -> None:
    world = World(tmp_path)
    copy = tmp_path / "copy"

    asyncio.run(world.restore(build_tag=None).restore(copy, [CASELIST]))

    assert set(marker_in(copy)) == ALLOWED_FIELDS
    assert marker_in(copy)["build_tag"] is None


def test_the_marker_is_in_place_before_anything_is_restored(tmp_path: Path) -> None:
    world = World(tmp_path)

    asyncio.run(world.restore().restore(tmp_path / "copy", [CASELIST]))

    assert [state.marker_when_restore_began for state in world.states] == [True]


def test_a_restore_that_stops_part_way_leaves_a_whole_marker_beside_what_it_restored(tmp_path: Path) -> None:
    world = World(tmp_path, stop=True)
    copy = tmp_path / "copy"

    with pytest.raises(BlobIntegrityError):
        asyncio.run(world.restore().restore(copy, [CASELIST]))

    assert (copy / "debate.sqlite3").is_file(), "the premise: the stop left a restored file"
    assert set(marker_in(copy)) == ALLOWED_FIELDS
    assert sorted(path.name for path in copy.iterdir()) == sorted(["debate.sqlite3", RESTORED_COPY_MARKER]), (
        "no temporary file is left beside them"
    )


def test_a_stop_while_the_marker_is_written_leaves_no_marker_and_nothing_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of "a whole marker or none": the marker lands by a rename, or not at all."""
    world = World(tmp_path)
    copy = tmp_path / "copy"

    def interrupted(self: RestoredCopyMarker) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(run_state_restore.RestoredCopyMarker, "as_json", interrupted)
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(world.restore().restore(copy, [CASELIST]))

    assert world.states == [], "nothing was restored"
    assert list(copy.iterdir()) == [], "no marker, and no temporary file"


@pytest.mark.parametrize("where", ["the data directory", "inside it", "a directory that is not empty"])
def test_a_refused_directory_is_never_given_a_marker(tmp_path: Path, where: str) -> None:
    world = World(tmp_path)
    (world.live / "debate.sqlite3").write_bytes(b"the live database\n")
    full = tmp_path / "full"
    full.mkdir()
    (full / "notes.txt").write_text("someone's notes\n", encoding="utf-8")
    target = {
        "the data directory": world.live,
        "inside it": world.live / "copy",
        "a directory that is not empty": full,
    }[where]

    with pytest.raises(RestoreTargetRefused):
        asyncio.run(world.restore().restore(target, [CASELIST]))

    assert list((tmp_path / "home").rglob(RESTORED_COPY_MARKER)) == []
    assert list(full.rglob(RESTORED_COPY_MARKER)) == []
    assert world.states == []

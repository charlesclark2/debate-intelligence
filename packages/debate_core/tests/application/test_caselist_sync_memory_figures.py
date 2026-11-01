"""The weekly run's memory high-water marks as each stage ends, in its summary and details (`v1-e40-t31`).

The measurement in `docs/data/caselist-parse-memory.md` found that the run's main process is what
grows, in the parse's aggregate rebuild, so the cloud task's size has to come from what a real run
used. Each stage the run times now carries, read as it ended, the container's memory high-water mark
(its cgroup's peak) and the main process's own, by `v1-e40-t32`'s reader. A figure that cannot be
read, as the container's on the Mac, is left out, never zero. The run's record gains nothing, and
the details gain no key of their own: the figures are inside each stage's entry, which the details
schema of `v1.1.0-dev.251` (the cloud image) and of `v1.1.0-dev.200` (the Mac's installed build)
both leave open (`stored_run_records/`). `check_an_older_build_reads_the_run_memory_figures.py`
reads the same details with those builds' own code.

The run is the one `test_caselist_sync_stage_times_and_volume.py` drives, with the memory reader a
stub whose numbers every expected value below is written from by hand.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import jsonschema
import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST

from debate_core.application.caselist import memory_high_water
from debate_core.application.caselist.memory_high_water import MemoryHighWater, read_memory_high_water
from debate_core.application.caselist_sync import RunSummary, SearchIndexStageReport, StageOutcome
from debate_core.application.sync_runs import SyncRunDetails, details_for_summary, record_for_summary

from .test_caselist_sync_stage_times_and_volume import EVERY_STAGE, Clock, service

GIB: Final = 1024**3
MIB: Final = 1024**2

BEFORE_THE_INDEX: Final = MemoryHighWater(
    container_peak_bytes=1 * GIB, cgroup="v2", main_process_peak_bytes=200 * MIB
)
AFTER_THE_INDEX: Final = MemoryHighWater(
    container_peak_bytes=3 * GIB, cgroup="v2", main_process_peak_bytes=900 * MIB
)

STORED: Final = Path(__file__).parent / "caselist" / "stored_run_records"
FIGURES: Final = Path(__file__).parent / "caselist" / "run_memory_figures"
DETAILS_THIS_BUILD_WRITES: Final = FIGURES / "details_this_build_writes.json"
"""The details of :func:`a_run_whose_index_stage_grows`, written out by hand."""


class Memory:
    """The memory reader: `reading` until a stage changes it, and how many times it was read."""

    def __init__(self, reading: MemoryHighWater) -> None:
        self.reading = reading
        self.reads = 0

    def __call__(self) -> MemoryHighWater:
        self.reads += 1
        return self.reading


class GrowingIndexStage:
    """The search index stage: seven minutes by the run's clock, after which the marks are higher."""

    def __init__(self, clock: Clock, memory: Memory) -> None:
        self.clock = clock
        self.memory = memory

    async def refresh(self, stores: Sequence[str], *, no_session: str | None) -> SearchIndexStageReport:
        self.clock.now += timedelta(minutes=7)
        self.memory.reading = AFTER_THE_INDEX
        return SearchIndexStageReport(outcome=StageOutcome.SKIPPED, reason="the parsed store has not changed")


def a_run_whose_index_stage_grows(tmp_path: Path) -> tuple[RunSummary, Memory]:
    clock = Clock()
    memory = Memory(BEFORE_THE_INDEX)
    summary = asyncio.run(
        service(tmp_path, clock, search_index=GrowingIndexStage(clock, memory), memory=memory).run(
            [SYNTHETIC_CASELIST]
        )
    )
    return summary, memory


def a_run_reading(tmp_path: Path, reading: MemoryHighWater) -> RunSummary:
    return asyncio.run(service(tmp_path, Clock(), memory=Memory(reading)).run([SYNTHETIC_CASELIST]))


def stage_json(summary: RunSummary) -> list[dict[str, Any]]:
    """Each stage's entry in the summary, as `caselist pull --json` prints it."""
    return [one.as_json() for one in summary.stage_times]


def details_json(summary: RunSummary) -> dict[str, Any]:
    """The run's details, as the details file and the bucket hold them."""
    return json.loads(details_for_summary(summary).model_dump_json())


# ------------------------------------------------------------------------------------------------
# Each stage's figures
# ------------------------------------------------------------------------------------------------


def test_memory_figures_each_stage_carries_the_marks_read_as_it_ended(tmp_path: Path) -> None:
    summary, memory = a_run_whose_index_stage_grows(tmp_path)

    assert [str(one.stage) for one in summary.stage_times] == EVERY_STAGE
    assert [one.memory for one in summary.stage_times] == [BEFORE_THE_INDEX] * 5 + [AFTER_THE_INDEX] * 4, (
        "the index stage's figures are read after it ran, not before"
    )
    assert memory.reads == len(EVERY_STAGE), "read once, as each stage ended"
    assert stage_json(summary)[5] == {
        "stage": "search_index",
        "started_at": "2026-11-04T12:00:00+00:00",
        "finished_at": "2026-11-04T12:07:00+00:00",
        "duration_seconds": 420.0,
        "memory": {"container_peak_bytes": 3221225472, "cgroup": "v2", "main_process_peak_bytes": 943718400},
    }
    assert all("memory" in one for one in stage_json(summary)), "no stage is without its figures"


def test_memory_figures_the_details_hold_each_stages_figures_as_the_hand_written_file(tmp_path: Path) -> None:
    summary, _ = a_run_whose_index_stage_grows(tmp_path)

    assert details_json(summary) == json.loads(DETAILS_THIS_BUILD_WRITES.read_text(encoding="utf-8"))


def test_memory_figures_read_back_from_the_details_and_are_none_in_older_details(tmp_path: Path) -> None:
    summary, _ = a_run_whose_index_stage_grows(tmp_path)

    again = SyncRunDetails.model_validate_json(details_for_summary(summary).model_dump_json())
    assert [one.memory.container_peak_bytes if one.memory else None for one in again.stage_times] == (
        [1 * GIB] * 5 + [3 * GIB] * 4
    )
    older = SyncRunDetails.model_validate_json(
        '{"schema_version": 1, "run_id": "20261028T110000Z", "stage_times": [{"stage": "parse", '
        '"started_at": "2026-10-28T11:00:00Z", "finished_at": "2026-10-28T11:40:00Z"}]}'
    )
    assert [one.memory for one in older.stage_times] == [None], "details before v1-e40-t31 recorded none"


# ------------------------------------------------------------------------------------------------
# What cannot be read is left out
# ------------------------------------------------------------------------------------------------


def test_memory_figures_with_no_cgroup_keep_the_main_process_and_leave_the_container_out(
    tmp_path: Path,
) -> None:
    """The Mac's case: no cgroup to read, and the main process's own peak from `getrusage`."""
    summary = a_run_reading(tmp_path, MemoryHighWater(main_process_peak_bytes=500 * MIB))

    assert {json.dumps(one.get("memory")) for one in stage_json(summary)} == {
        '{"main_process_peak_bytes": 524288000}'
    }
    assert {json.dumps(one.get("memory")) for one in details_json(summary)["stage_times"]} == {
        '{"main_process_peak_bytes": 524288000}'
    }


def test_memory_figures_none_readable_are_no_figures_never_zero(tmp_path: Path) -> None:
    summary = a_run_reading(tmp_path, MemoryHighWater())

    assert [set(one) for one in stage_json(summary)] == [
        {"stage", "started_at", "finished_at", "duration_seconds"}
    ] * len(EVERY_STAGE)
    assert [set(one) for one in details_json(summary)["stage_times"]] == [
        {"stage", "started_at", "finished_at"}
    ] * len(EVERY_STAGE)


# ------------------------------------------------------------------------------------------------
# Read with v1-e40-t32's reader
# ------------------------------------------------------------------------------------------------


def test_memory_figures_from_t32s_reader_are_the_containers_cgroup_and_this_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`v1-e40-t32`'s reader over a stand-in cgroup. That the service reads with it when none is given
    is the CLI's test of the same figures, through the container's wiring."""
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "memory.peak").write_text("7516192768\n", encoding="ascii")
    monkeypatch.setattr(memory_high_water, "CGROUP_ROOT", cgroup)

    summary = asyncio.run(service(tmp_path, Clock(), memory=read_memory_high_water).run([SYNTHETIC_CASELIST]))

    figures = [one.memory for one in summary.stage_times]
    assert [(one.container_peak_bytes, one.cgroup) if one else None for one in figures] == [
        (7516192768, "v2")
    ] * len(EVERY_STAGE)
    assert all(one and one.main_process_peak_bytes and one.main_process_peak_bytes > 0 for one in figures)


# ------------------------------------------------------------------------------------------------
# What the earlier builds read
# ------------------------------------------------------------------------------------------------


def stored_schema(name: str) -> dict[str, Any]:
    return json.loads((STORED / name).read_text(encoding="utf-8"))


def test_memory_figures_details_are_ones_the_cloud_image_and_the_macs_build_read(tmp_path: Path) -> None:
    """Against what `v1.1.0-dev.251` and `v1.1.0-dev.200` validate details with: one schema, which both
    print byte for byte (`details_schema_of_the_macs_installed_build.json`). The record is unchanged,
    against the record schema both print (`record_schema_of_the_cloud_image.json`), which forbids a key
    it does not define in a record and in a stage."""
    summary, _ = a_run_whose_index_stage_grows(tmp_path)
    schema = stored_schema("details_schema_of_the_macs_installed_build.json")

    for details in (details_json(summary), json.loads(DETAILS_THIS_BUILD_WRITES.read_text(encoding="utf-8"))):
        jsonschema.validate(details, schema)
        assert set(details) <= set(schema["properties"]), "no details key the earlier builds do not define"
    assert schema["$defs"]["StageTiming"].get("additionalProperties", True) is not False
    record = json.loads(record_for_summary(summary, environment="dev", mode="run").model_dump_json())
    jsonschema.validate(record, stored_schema("record_schema_of_the_cloud_image.json"))

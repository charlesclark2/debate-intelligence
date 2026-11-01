"""What a backfile import's log lines carry as it goes (`v1-e40-t32`): parse progress and memory.

The first cloud import was killed for memory at 71 minutes and left an empty log. Each step's start
and end, in order, through the real command, is
`packages/debate_cli/tests/bucket_mode/test_backfile_import.py`'s; here are the two parts with rules
of their own:

* the parse's progress lines, at the interval, on a clock the test moves. Every expected line is
  worked out by hand: ten sources of 100 seconds each against a 300-second interval give a line at
  the start, after the third, sixth and ninth, and after the tenth, the last;
* the memory high-water marks (the PM's amendment of 2026-10-31): the container's from a stand-in
  cgroup directory, v2's `memory.peak` before v1's `memory.max_usage_in_bytes`, and the main
  process's from `getrusage`, each left out, never zero, where it cannot be read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from debate_core.application.caselist.backfile_import import (
    PARSE_PROGRESS_INTERVAL_SECONDS,
    ParseProgress,
    StepEvent,
    StepLine,
)
from debate_core.application.caselist.memory_high_water import MemoryHighWater, read_memory_high_water

STAND_IN_MEMORY = MemoryHighWater(container_peak_bytes=20_000_000_000, cgroup="v2", main_process_peak_bytes=3)


@dataclass
class Clock:
    now: float = 1_000.0

    def __call__(self) -> float:
        return self.now


def progress_over(clock: Clock, lines: list[StepLine]) -> ParseProgress:
    return ParseProgress(lines.append, monotonic=clock, memory=lambda: STAND_IN_MEMORY, interval=300.0)


def said(lines: list[StepLine]) -> list[tuple[str, str, float | None, dict[str, int]]]:
    return [(str(line.event), line.step, line.seconds, dict(line.counts)) for line in lines]


# ------------------------------------------------------------------------------------------------
# The parse's progress
# ------------------------------------------------------------------------------------------------


def test_the_backfile_parse_says_how_far_it_got_at_the_start_every_interval_and_at_the_last_source() -> None:
    clock, lines = Clock(), []
    progress = progress_over(clock, lines)

    progress.start(10)
    for done in range(1, 11):
        clock.now += 100.0
        progress(done)

    assert said(lines) == [
        ("parse_progress", "parse", 0.0, {"sources_done": 0, "sources_left": 10}),
        ("parse_progress", "parse", 300.0, {"sources_done": 3, "sources_left": 7}),
        ("parse_progress", "parse", 600.0, {"sources_done": 6, "sources_left": 4}),
        ("parse_progress", "parse", 900.0, {"sources_done": 9, "sources_left": 1}),
        ("parse_progress", "parse", 1_000.0, {"sources_done": 10, "sources_left": 0}),
    ]
    assert all(line.memory == STAND_IN_MEMORY for line in lines)


def test_the_backfile_parse_interval_counts_from_its_last_line_not_from_the_start() -> None:
    """A slow source, then quick ones: the next line is 300 seconds after the one before it."""
    clock, lines = Clock(), []
    progress = progress_over(clock, lines)
    progress.start(5)

    for done, took in enumerate((350.0, 100.0, 100.0, 100.0), start=1):
        clock.now += took
        progress(done)

    assert [(line.seconds, dict(line.counts)["sources_done"]) for line in lines] == [
        (0.0, 0),
        (350.0, 1),
        (650.0, 4),
    ]


def test_a_backfile_parse_with_nothing_to_parse_says_so_once() -> None:
    clock, lines = Clock(), []

    progress_over(clock, lines).start(0)

    assert said(lines) == [("parse_progress", "parse", 0.0, {"sources_done": 0, "sources_left": 0})]


def test_the_backfile_parse_progress_interval_is_five_minutes() -> None:
    assert PARSE_PROGRESS_INTERVAL_SECONDS == 300.0
    assert StepEvent.PARSE_PROGRESS == "parse_progress"


# ------------------------------------------------------------------------------------------------
# The memory high-water marks
# ------------------------------------------------------------------------------------------------


def stand_in_cgroup(root: Path, *, v2: str | None = None, v1: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if v2 is not None:
        (root / "memory.peak").write_text(v2, encoding="ascii")
    if v1 is not None:
        (root / "memory").mkdir()
        (root / "memory" / "memory.max_usage_in_bytes").write_text(v1, encoding="ascii")
    return root


def test_a_backfile_import_reads_cgroup_v2s_peak(tmp_path: Path) -> None:
    memory = read_memory_high_water(stand_in_cgroup(tmp_path / "cgroup", v2="17179869184\n"))

    assert (memory.container_peak_bytes, memory.cgroup) == (17_179_869_184, "v2")


def test_a_backfile_import_reads_cgroup_v1s_peak_where_there_is_no_v2(tmp_path: Path) -> None:
    memory = read_memory_high_water(stand_in_cgroup(tmp_path / "cgroup", v1="8589934592\n"))

    assert (memory.container_peak_bytes, memory.cgroup) == (8_589_934_592, "v1")


def test_a_backfile_import_prefers_v2_when_both_are_there(tmp_path: Path) -> None:
    memory = read_memory_high_water(stand_in_cgroup(tmp_path / "cgroup", v2="200\n", v1="100\n"))

    assert (memory.container_peak_bytes, memory.cgroup) == (200, "v2")


@pytest.mark.parametrize("unreadable", ["", "max\n", "-1\n", "12 MB\n"])
def test_a_backfile_import_leaves_out_a_peak_it_cannot_read_and_never_says_zero(
    tmp_path: Path, unreadable: str
) -> None:
    memory = read_memory_high_water(stand_in_cgroup(tmp_path / "cgroup", v2=unreadable))

    assert (memory.container_peak_bytes, memory.cgroup) == (None, None)


def test_a_backfile_import_on_a_machine_with_no_cgroup_leaves_the_container_out(tmp_path: Path) -> None:
    """The Mac: no cgroup, so no container figure, and the main process's still."""
    memory = read_memory_high_water(tmp_path / "no-cgroup-here")

    assert (memory.container_peak_bytes, memory.cgroup) == (None, None)
    assert memory.main_process_peak_bytes is not None


def test_a_backfile_imports_main_process_peak_is_in_bytes(tmp_path: Path) -> None:
    """A Python process running pytest peaks well over 10 MiB. Linux's `ru_maxrss` counts kibibytes,
    so a figure read as bytes there would be about a thousandth of the truth, and under it."""
    memory = read_memory_high_water(tmp_path / "no-cgroup-here")

    assert memory.main_process_peak_bytes is not None
    assert memory.main_process_peak_bytes > 10 * 1024 * 1024

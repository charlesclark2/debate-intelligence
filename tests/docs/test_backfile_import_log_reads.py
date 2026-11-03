"""The runbook's reads of a backfile import's log, run over a synthetic log (`v1-e40-t32`).

`docs/runbooks/caselist-cloud-run.md`, "Backfile imports", reads a task's log twice: "How far it got"
reads the last step line, and "Its counts" reads the result. Since `v1-e40-t32` both kinds of line
carry `"command": "caselist backfile-import"`, so each read is held here to its own lines. The
filters are read out of the runbook, everything after its `aws logs tail ...`, and run by `sh` over a
log in `aws logs tail`'s shape, so a change to the runbook is what is tested.

The step lines are written by the CLI's own renderer from step lines built by hand; the result line,
the expected output and every number are written by hand. No AWS call, no network.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
from pathlib import Path
from typing import Final

from debate_cli.commands.caselist_backfile import step_line_as_json
from debate_cli.output import CliOutput, OutputMode
from debate_core.application.caselist.backfile_import import IMPORT_COMMAND, StepEvent, StepLine
from debate_core.application.caselist.memory_high_water import MemoryHighWater

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"
PREFIX: Final = "2026-11-02T16:10:00.000000+00:00 run/run/0123456789abcdef0123456789abcdef "
MEMORY: Final = MemoryHighWater(
    container_peak_bytes=30_064_771_072, cgroup="v1", main_process_peak_bytes=2_147_483_648
)


def log_line(line: StepLine) -> str:
    stderr = io.StringIO()
    CliOutput(OutputMode.JSON, stderr=stderr).event_line(
        IMPORT_COMMAND, str(line.event), step_line_as_json(line), text=""
    )
    return PREFIX + stderr.getvalue()


def killed_in_the_parse() -> str:
    """A task stopped an hour into the parse: no result line, and a line the container wrote itself."""
    return "".join(
        [
            PREFIX + "Starting the caselist run container\n",
            log_line(StepLine(StepEvent.STARTED, "restore")),
            log_line(StepLine(StepEvent.ENDED, "restore", 41.27, {"state_files": 6}, MEMORY)),
            log_line(StepLine(StepEvent.STARTED, "parse")),
            log_line(
                StepLine(
                    StepEvent.PARSE_PROGRESS,
                    "parse",
                    3300.0,
                    {"sources_done": 11000, "sources_left": 9000},
                    MEMORY,
                )
            ),
            log_line(
                StepLine(
                    StepEvent.PARSE_PROGRESS,
                    "parse",
                    3600.04,
                    {"sources_done": 12000, "sources_left": 8000},
                    MEMORY,
                )
            ),
        ]
    )


RESULT: Final = PREFIX + json.dumps(
    {
        "schema_version": 1,
        "status": "ok",
        "command": "caselist backfile-import",
        "data": {
            "applied": True,
            "import": {"parsed": 20000, "cards": 400000, "step_seconds": {"parse": 5400.0}},
        },
        "error": None,
    }
)


def filter_after_the_tail(marker: str) -> str:
    """The pipeline after `aws logs tail ...` in the one runbook command that contains `marker`."""
    commands = [
        line
        for line in RUNBOOK.read_text(encoding="utf-8").splitlines()
        if line.startswith("aws logs tail ") and marker in line
    ]
    assert len(commands) == 1, commands
    return commands[0].split(" | ", 1)[1]


def run_filter(pipeline: str, log: str) -> list[str]:
    ran = subprocess.run(["sh", "-c", pipeline], input=log, capture_output=True, text=True, check=False)
    return ran.stdout.splitlines()


HOW_FAR: Final = "| tail -1 |"
COUNTS: Final = '"parsed_uploaded": [0-9]+'


def test_how_far_it_got_prints_the_last_step_lines_step_seconds_counts_and_memory() -> None:
    assert run_filter(filter_after_the_tail(HOW_FAR), killed_in_the_parse()) == [
        '"event": "parse_progress"',
        '"step": "parse"',
        '"seconds": 3600.0',
        '"counts": {"sources_done": 12000, "sources_left": 8000}',
        '"memory": {"container_peak_bytes": 30064771072, "cgroup": "v1", '
        '"main_process_peak_bytes": 2147483648}',
    ]


def test_how_far_it_got_passes_over_the_result_line_that_follows_the_steps() -> None:
    log = (
        killed_in_the_parse()
        + log_line(StepLine(StepEvent.ENDED, "parse", 5400.0, {"parsed": 19998}))
        + RESULT
    )

    assert run_filter(filter_after_the_tail(HOW_FAR), log)[:2] == ['"event": "step_ended"', '"step": "parse"']


def test_the_counts_block_reads_the_result_and_never_a_step_line() -> None:
    log = (
        killed_in_the_parse()
        + log_line(StepLine(StepEvent.ENDED, "parse", 5400.0, {"parsed": 19998}))
        + RESULT
    )

    assert run_filter(filter_after_the_tail(COUNTS), log) == [
        '"status": "ok"',
        '"applied": true',
        '"parsed": 20000',
        '"cards": 400000',
        '"parse": 5400.0',
    ]


def test_how_far_it_got_comes_after_the_imports_watch_and_before_its_counts() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    imports = text.index("### The four imports")
    watch = text.index("**Watch it** every half hour", imports)
    how_far = text.index("**How far it got**", imports)
    counts = text.index("**Its counts.**", imports)
    assert watch < how_far < counts
    assert re.search(r"after a `STOPPED` that is not exit `0`", text[how_far:counts])

"""The runbooks' reads of the weekly run's log, run over a synthetic log (`v1-e40-t43`).

Since `v1-e40-t43` the weekly run (`caselist pull`) writes a step line as each step starts and ends,
beside its result, and every line carries `"command": "caselist pull"`. So each read of the run's log
is held here to its own lines:

* `caselist-cloud-run.md`, Step 8's "How far it has got", prints the last step line, filtered the way
  the backfile import's is, and passes over the result. It refuses a shell with a `DEBATE_` variable
  set, before it calls `aws`.
* The cloud rehearsal's counts block (Step 7) reads the result's counts and none of a step line's.
* `caselist-cutover.md`'s check of the summary line counts the result alone, not the step lines.

Each command is read out of its runbook and run by `sh` (or Python, for the cutover's script) over a
log in `aws logs tail`'s or `filter-log-events`' shape, so a change to the runbook is what is tested.
The step lines are written by the CLI's own renderer from step lines built by hand; the result lines,
the expected output and every number are written by hand. `aws` is a stand-in on `PATH` that prints
the log: no AWS call, no network.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

from debate_cli.output import CliOutput, OutputMode
from debate_cli.step_lines import write_step_line
from debate_core.application.caselist.memory_high_water import MemoryHighWater
from debate_core.application.caselist.step_lines import StepEvent, StepLine

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOUD_RUN = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"
CUTOVER = REPO_ROOT / "docs" / "runbooks" / "caselist-cutover.md"
TASK_ID: Final = "0123456789abcdef0123456789abcdef"
PREFIX: Final = f"2026-11-11T10:40:00.000000+00:00 run/run/{TASK_ID} "
MEMORY: Final = MemoryHighWater(
    container_peak_bytes=17_179_869_184, cgroup="v1", main_process_peak_bytes=4_294_967_296
)


def step_line(line: StepLine) -> str:
    """One step line exactly as `debate-research --json caselist pull` writes it on stderr."""
    stderr = io.StringIO()
    write_step_line(CliOutput(OutputMode.JSON, stderr=stderr), "caselist pull", line)
    return stderr.getvalue().rstrip("\n")


IN_THE_PARSE: Final = [
    "Starting the caselist run container",
    step_line(StepLine(StepEvent.STARTED, "restore")),
    step_line(
        StepLine(StepEvent.ENDED, "restore", 48.31, {"state_files": 6, "parsed_objects": 15210}, MEMORY)
    ),
    step_line(StepLine(StepEvent.STARTED, "select")),
    step_line(
        StepLine(
            StepEvent.ENDED,
            "select",
            12.0,
            {"archives_seen": 40, "archives_wanted": 2, "archives_deferred": 0, "openev_seen": 3},
            MEMORY,
            "completed",
        )
    ),
    step_line(StepLine(StepEvent.STARTED, "parse")),
    step_line(
        StepLine(
            StepEvent.PARSE_PROGRESS,
            "parse",
            600.04,
            {"sources_done": 410, "sources_left": 890, "caselists_done": 1, "caselists_left": 2},
            MEMORY,
        )
    ),
]
"""A run twenty minutes in, ten minutes into its parse of the second of three caselists."""

PARSE_ENDED: Final = step_line(
    StepLine(
        StepEvent.ENDED,
        "parse",
        2400.0,
        {"caselists": 3, "attempted": 1300, "failed": 2, "cards": 9000},
        MEMORY,
        "completed",
    )
)

RESULT: Final = json.dumps(
    {
        "schema_version": 1,
        "status": "ok",
        "command": "caselist pull",
        "data": {
            "dry_run": True,
            "archives_wanted": 3,
            "archives_downloaded": 0,
            "objects_published": 0,
            "run_record": None,
        },
        "error": None,
    }
)
"""A dry run's result, the last line of its log."""


def tailed(lines: list[str]) -> str:
    """The lines as `aws logs tail` prints them: each after its time and stream."""
    return "".join(PREFIX + line + "\n" for line in lines)


def command_containing(runbook: Path, marker: str) -> str:
    """The one line of a shell block in `runbook` that contains `marker`."""
    found = [line for line in runbook.read_text(encoding="utf-8").splitlines() if marker in line]
    assert len(found) == 1, found
    return found[0]


MEMORY_SAID: Final = (
    '"memory": {"container_peak_bytes": 17179869184, "cgroup": "v1", "main_process_peak_bytes": 4294967296}'
)
HOW_FAR: Final = """grep '"command": "caselist pull"' | grep '"event": ' | tail -1"""
DRY_RUN_COUNTS: Final = '"dry_run": true|"archives_wanted"'


def run_with_a_stand_in_aws(
    command: str, log: str, tmp_path: Path, **environment: str
) -> tuple[list[str], bool]:
    """Run `command` with `sh`, its `aws` a script that prints `log`; its output and whether `aws` ran."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_file = tmp_path / "log.txt"
    log_file.write_text(log, encoding="utf-8")
    called = tmp_path / "aws-was-called"
    stand_in = bin_dir / "aws"
    stand_in.write_text(f'#!/bin/sh\ntouch "{called}"\ncat "{log_file}"\n', encoding="utf-8")
    stand_in.chmod(0o755)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", **environment}
    ran = subprocess.run(["sh", "-c", command], capture_output=True, text=True, check=False, env=env)
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.splitlines(), called.exists()


def test_how_far_it_has_got_prints_the_last_step_lines_event_step_seconds_counts_and_memory(
    tmp_path: Path,
) -> None:
    said, called = run_with_a_stand_in_aws(
        command_containing(CLOUD_RUN, HOW_FAR), tailed(IN_THE_PARSE), tmp_path
    )

    assert called
    assert said == [
        '"event": "parse_progress"',
        '"step": "parse"',
        '"seconds": 600.0',
        '"counts": {"sources_done": 410, "sources_left": 890, "caselists_done": 1, "caselists_left": 2}',
        MEMORY_SAID,
    ]


def test_how_far_it_has_got_prints_an_ended_stages_outcome_and_passes_over_the_result(tmp_path: Path) -> None:
    log = tailed([*IN_THE_PARSE, PARSE_ENDED, RESULT])

    said, _ = run_with_a_stand_in_aws(command_containing(CLOUD_RUN, HOW_FAR), log, tmp_path)

    assert said == [
        '"event": "step_ended"',
        '"step": "parse"',
        '"seconds": 2400.0',
        '"outcome": "completed"',
        '"counts": {"caselists": 3, "attempted": 1300, "failed": 2, "cards": 9000}',
        MEMORY_SAID,
    ]


def test_how_far_it_has_got_refuses_a_shell_with_a_debate_variable_set_before_it_reads_anything(
    tmp_path: Path,
) -> None:
    said, called = run_with_a_stand_in_aws(
        command_containing(CLOUD_RUN, HOW_FAR),
        tailed(IN_THE_PARSE),
        tmp_path,
        DEBATE_STORAGE__DATA_DIR="/scratch",
    )

    assert said == ["STOP: a DEBATE_ variable is set in this shell; unset it and paste again"]
    assert not called


def test_the_rehearsals_counts_block_reads_the_result_and_never_a_step_line(tmp_path: Path) -> None:
    """The select stage's end line carries `"archives_wanted"` too: only the result's is printed."""
    log = tailed([*IN_THE_PARSE, RESULT])

    said, _ = run_with_a_stand_in_aws(command_containing(CLOUD_RUN, DRY_RUN_COUNTS), log, tmp_path)

    assert said == [
        '"status": "ok"',
        '"dry_run": true',
        '"archives_wanted": 3',
        '"archives_downloaded": 0',
        '"objects_published": 0',
    ]


def test_how_far_it_has_got_comes_after_step_8s_watch_and_before_its_record() -> None:
    text = CLOUD_RUN.read_text(encoding="utf-8")
    step_8 = text.index("## Step 8")
    watch = text.index("**Watch it**, every half hour", step_8)
    how_far = text.index("**How far it has got**", step_8)
    record = text.index("**Its record reads as a Mac run's does**", step_8)
    assert watch < how_far < record
    assert text.index(command_containing(CLOUD_RUN, HOW_FAR), step_8) < record


def cutover_script() -> str:
    """The Python the cutover's "Its log" block runs, between its `<<'RUNLOG'` and `RUNLOG` lines."""
    text = CUTOVER.read_text(encoding="utf-8")
    found = re.search(r"<<'RUNLOG'\n(.*?)\nRUNLOG\n", text, re.DOTALL)
    assert found is not None
    return found.group(1)


def test_the_cutovers_summary_check_counts_the_result_and_no_step_line(tmp_path: Path) -> None:
    lines = [*IN_THE_PARSE[1:], PARSE_ENDED, RESULT]
    events = tmp_path / "events.json"
    events.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "logStreamName": f"run/run/{TASK_ID}",
                        "timestamp": 1_762_857_600_000 + n,
                        "message": line,
                    }
                    for n, line in enumerate(lines)
                ]
            }
        ),
        encoding="utf-8",
    )
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"tasks": [{"stoppedAt": "2026-11-11T12:00:00Z"}]}), encoding="utf-8")

    ran = subprocess.run(
        [sys.executable, "-I", "-", str(events), str(task), TASK_ID],
        input=cutover_script(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    said = ran.stdout.splitlines()
    assert said[-2] == "summary lines found: 1"
    assert said[0].endswith("of the 262144-byte event limit, one whole JSON object")
    assert said[0].startswith(f"summary line: {len(RESULT.encode())} bytes, ")

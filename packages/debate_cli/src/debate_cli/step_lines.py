"""How a long command's step lines are written: one JSON line on stderr, or a sentence (`v1-e40-t32`).

`caselist backfile-import` (`v1-e40-t32`) and the weekly run, `caselist pull` (`v1-e40-t43`), write
:class:`~debate_core.application.caselist.step_lines.StepLine`\\ s as they go. In JSON mode, the cloud
task's, each is an object of the result's envelope shape with an `"event"` where a result has its
`"status"` (:meth:`~debate_cli.output.CliOutput.event_line`), so a log read by its `"command"` finds
it and a reader of results passes over it. In Rich mode it is a sentence. Stdout keeps the command's
one result either way.
"""

from __future__ import annotations

from debate_cli.output import CliOutput, JsonValue
from debate_core.application.caselist.memory_high_water import MemoryHighWater
from debate_core.application.caselist.step_lines import StepLine

__all__ = ["step_line_as_json", "step_sentence", "write_step_line"]


def write_step_line(output: CliOutput, command: str, line: StepLine) -> None:
    """A step's line on stderr as it starts, ends or goes; stdout keeps the result."""
    output.event_line(command, str(line.event), step_line_as_json(line), text=step_sentence(command, line))


def step_line_as_json(line: StepLine) -> dict[str, JsonValue]:
    """A step line's `data`: the step, its seconds, its counts, and the memory figures that could be read.

    A figure that could not be read is left out, never zero (the PM's amendment of 2026-10-31). A
    step's `"outcome"` is written only where the command records one (`v1-e40-t43`).
    """
    data: dict[str, JsonValue] = {"step": line.step}
    if line.seconds is not None:
        data["seconds"] = round(line.seconds, 1)
    if line.outcome is not None:
        data["outcome"] = line.outcome
    data["counts"] = {name: count for name, count in line.counts.items()}
    memory = _memory_as_json(line.memory)
    if memory:
        data["memory"] = memory
    return data


def _memory_as_json(memory: MemoryHighWater | None) -> dict[str, JsonValue]:
    if memory is None:
        return {}
    data: dict[str, JsonValue] = {}
    if memory.container_peak_bytes is not None:
        data["container_peak_bytes"] = memory.container_peak_bytes
        data["cgroup"] = memory.cgroup
    if memory.main_process_peak_bytes is not None:
        data["main_process_peak_bytes"] = memory.main_process_peak_bytes
    return data


def step_sentence(command: str, line: StepLine) -> str:
    """The line for a person: `caselist pull: parse step ended at 12.3 s (completed); parsed 3, …`."""
    said = f"{command}: {line.step} {str(line.event).replace('_', ' ')}"
    if line.seconds is not None:
        said += f" at {line.seconds:.1f} s"
    if line.outcome is not None:
        said += f" ({line.outcome})"
    if line.counts:
        said += "; " + ", ".join(f"{name} {count:,}" for name, count in line.counts.items())
    memory = line.memory
    if memory is not None and memory.container_peak_bytes is not None:
        said += f"; container peak {memory.container_peak_bytes:,} bytes (cgroup {memory.cgroup})"
    if memory is not None and memory.main_process_peak_bytes is not None:
        said += f"; main process peak {memory.main_process_peak_bytes:,} bytes"
    return said

"""Everything `debate-research` writes, and the two shapes it writes in.

A command never calls `print`, never builds a Rich renderable and never serialises JSON itself. It
hands this module a result — a mapping for machines and, optionally, a table or a line for people
— and this module decides where it goes:

|                          | default (Rich)                  | `--json`                          |
|--------------------------|----------------------------------|-----------------------------------|
| `success(...)`           | `display` on **stdout**          | the envelope on **stdout**, once  |
| `failure(...)`           | an error panel on **stderr**     | the envelope on **stdout**, once  |
| `detail(...)` (verbose)  | **stderr**                       | **stderr**                        |
| `note(...)`              | **stderr**                       | **stderr**                        |

That split is the reason the module exists. In `--json` mode stdout carries exactly one JSON
object and nothing else, so `debate-research --json caselist sync | jq` keeps working when a
command later grows a progress line, a warning or a deprecation notice: those are diagnostics and
diagnostics go to stderr.

## The envelope

Every `--json` run prints one object with the same five keys, whether it succeeded or failed::

    {"schema_version": 1, "status": "ok",    "command": "doctor", "data": {...}, "error": null}
    {"schema_version": 1, "status": "error", "command": "doctor", "data": null,
     "error": {"code": "PROVIDER_UNAVAILABLE", "message": "...", "exit_code": 3,
               "details": {"provider": "openalex"}, "hint": null}}

The promise to a scheduled consumer (v1-e34-t02's caselist sync is the first one) is:

* the five envelope keys and the five `error` keys are always present, `null` rather than absent
  when they do not apply;
* a command's own payload lives under `data` and nowhere else, so a command may add fields to
  `data` at any time and a consumer that reads two of them keeps working;
* `status`, `error.code` and `error.exit_code` are the fields to branch on, and `error.code` comes
  from :func:`~debate_cli.exit_codes.error_code_for`;
* anything that would break those rules bumps `schema_version`.

`data` values must be JSON-serialisable. Evidence text is never one of them: model and card
payloads carry offsets, paragraph ids and metadata, not quoted source text (architecture proposal
§8), and that rule is not relaxed because the output is machine-readable.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TextIO

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from debate_cli.exit_codes import ExitCode, error_code_for, exit_code_for
from debate_core.application.errors import DomainError

__all__ = [
    "SCHEMA_VERSION",
    "CliOutput",
    "CommandFailure",
    "JsonValue",
    "OutputMode",
    "TableSpec",
]

SCHEMA_VERSION = 1
"""Version of the `--json` envelope. Bumped only by a change that breaks existing consumers."""

type JsonValue = str | int | float | bool | None | Sequence[JsonValue] | Mapping[str, JsonValue]


class OutputMode(StrEnum):
    """Whether this run is being read by a person (`RICH`) or by a program (`JSON`)."""

    RICH = "rich"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class TableSpec:
    """A table described in plain data, so commands stay free of Rich imports.

    `rows` holds already-formatted strings: how a value is rendered is the command's decision,
    how the table is drawn is this module's.
    """

    columns: Sequence[str]
    rows: Sequence[Sequence[str]]
    title: str | None = None
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class CommandFailure:
    """A failure as both surfaces need it: a panel for a person, an `error` object for a program.

    Commands build one directly when the failure is an outcome rather than an exception::

        CommandFailure(
            code="UNVERIFIED",
            message="3 of 12 cards could not be reproduced from their snapshot",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"unverified": 3, "total": 12},
        )
    """

    code: str
    message: str
    exit_code: ExitCode
    details: Mapping[str, JsonValue] = field(default_factory=dict)
    hint: str | None = None

    @classmethod
    def from_exception(cls, exception: BaseException, *, hint: str | None = None) -> CommandFailure:
        """Describe `exception` the way the CLI reports it.

        `details` carries the facts the exception kept as attributes — `entity` and `key` on a
        `NotFound`, `provider` and `retry_after_seconds` on a `ProviderRateLimited` — which is why
        :mod:`debate_core.application.errors` stores them as attributes rather than only in the
        message. A consumer reads `details["key"]` instead of parsing English.
        """
        return cls(
            code=error_code_for(exception),
            message=str(exception) or type(exception).__name__,
            exit_code=exit_code_for(exception),
            details=_details_of(exception),
            hint=hint,
        )


class CliOutput:
    """The console the CLI writes through, in one of the two :class:`OutputMode` shapes.

    One instance is built per run by the root callback and reaches commands on the
    :class:`~debate_cli.context.CliContext`. Tests construct one directly with `stdout`/`stderr`
    set to `io.StringIO`.
    """

    def __init__(
        self,
        mode: OutputMode = OutputMode.RICH,
        *,
        verbose: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        width: int | None = None,
    ) -> None:
        self._mode = mode
        self._verbose = verbose
        self._stdout = stdout
        self._reported = False
        # Results are for whoever consumes the command; diagnostics are for whoever is watching.
        # highlight=False keeps Rich from colouring numbers and paths inside our own strings.
        self._results = Console(file=stdout, width=width, highlight=False)
        self._diagnostics = Console(file=stderr, stderr=True, width=width, highlight=False)

    @property
    def mode(self) -> OutputMode:
        return self._mode

    @property
    def verbose(self) -> bool:
        return self._verbose

    @property
    def is_json(self) -> bool:
        """True when stdout is reserved for the machine-readable envelope."""
        return self._mode is OutputMode.JSON

    def success(
        self,
        command: str,
        data: Mapping[str, JsonValue],
        *,
        display: TableSpec | str | None = None,
    ) -> None:
        """Report that `command` succeeded.

        `data` is the machine-readable payload (the envelope's `data`); `display` is what a person
        sees instead — a :class:`TableSpec`, a line of text, or nothing when the command's result
        is that it said nothing.
        """
        self._start_report(command)
        if self.is_json:
            self._write_envelope(status="ok", command=command, data=dict(data), error=None)
            return
        if isinstance(display, TableSpec):
            self._results.print(_render_table(display))
        elif display is not None:
            self._results.print(display, markup=False, soft_wrap=True)

    def failure(self, failure: CommandFailure, *, command: str | None = None) -> None:
        """Report that the run failed.

        This only *reports*; ending the process with `failure.exit_code` is the caller's job —
        :class:`~debate_cli.app.DebateResearchGroup` for an exception, the command itself for an
        outcome such as `UNVERIFIED`.

        If a result was already reported (a command that emitted its result and then failed
        while finishing up), the failure goes to stderr as a diagnostic instead: one run still
        puts exactly one JSON object on stdout.
        """
        if self._reported and self.is_json:
            self._diagnostics.print(
                f"{failure.code}: {failure.message} (after the result was already emitted)",
                markup=False,
                soft_wrap=True,
                style="red",
            )
            return
        if self.is_json:
            self._reported = True
            self._write_envelope(
                status="error",
                command=command,
                data=None,
                error={
                    "code": failure.code,
                    "message": failure.message,
                    "exit_code": int(failure.exit_code),
                    "details": dict(failure.details),
                    "hint": failure.hint,
                },
            )
            return
        self._reported = True
        self._diagnostics.print(_render_failure(failure))

    def detail(self, message: str) -> None:
        """Write a diagnostic that is only interesting with `--verbose` (stderr, both modes)."""
        if not self._verbose:
            return
        self._diagnostics.print(message, markup=False, soft_wrap=True, style="dim")

    def note(self, message: str) -> None:
        """Write a diagnostic a person should always see: a warning, help text (stderr)."""
        self._diagnostics.print(message, markup=False, soft_wrap=True)

    def _start_report(self, command: str) -> None:
        if self._reported:
            raise RuntimeError(
                f"{command!r} reported a second result; a run reports exactly one result or failure"
            )
        self._reported = True

    def _write_envelope(
        self,
        *,
        status: str,
        command: str | None,
        data: Mapping[str, JsonValue] | None,
        error: Mapping[str, JsonValue] | None,
    ) -> None:
        envelope: dict[str, JsonValue] = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "command": command,
            "data": data,
            "error": error,
        }
        # Written straight to the stream rather than through Rich: the envelope must be one line
        # of exactly the bytes json.dumps produced, with no wrapping, styling or highlighting.
        stream = self._stdout if self._stdout is not None else sys.stdout
        stream.write(json.dumps(envelope, ensure_ascii=False, default=str) + "\n")
        stream.flush()


def _render_table(spec: TableSpec) -> Table:
    table = Table(title=spec.title, caption=spec.caption, title_justify="left", header_style="bold")
    for column in spec.columns:
        table.add_column(column, overflow="fold")
    for row in spec.rows:
        table.add_row(*row)
    return table


def _render_failure(failure: CommandFailure) -> Panel:
    body = Text(failure.message)
    for key, value in failure.details.items():
        body.append(f"\n{key}: {value}", style="dim")
    if failure.hint is not None:
        body.append(f"\n\n{failure.hint}", style="italic")
    return Panel(
        body,
        title=failure.code,
        title_align="left",
        subtitle=f"exit {int(failure.exit_code)}",
        subtitle_align="right",
        border_style="red",
    )


def _details_of(exception: BaseException) -> dict[str, JsonValue]:
    """The facts worth reporting about `exception`, as JSON scalars."""
    if isinstance(exception, DomainError):
        return {
            name: value
            for name, value in vars(exception).items()
            if not name.startswith("_") and isinstance(value, str | int | float | bool | None)
        }
    if isinstance(exception, typer.TyperException):
        # A usage error's message is the whole story; its attributes are parser internals.
        return {}
    return {"exception_type": type(exception).__name__}

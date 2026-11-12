"""`debate-research search ... --auto-cut N --output bundle.docx`: then cut the results (`v1-e08-t06`).

The deciding is `debate_core`'s:
:class:`~debate_core.application.batch_cut_service.BatchCutService` walks the ranked results, skips
the inaccessible ones, cuts at most `--concurrency` at a time through `fetch`'s and `cut`'s services,
and stops at N VERIFIED cards, when the results run out, or when the budget guard refuses a call;
:class:`~debate_core.application.export_service.ExportService` writes the bundle. What is here is the
command-line surface: which options go together, the files, and the exit code.

## Options

`--auto-cut N` needs `--argument` and `--need`, which say what every card is cut for, and `--output`,
the .docx bundle. `--card-format PROFILE` is the team format profile of the bundle (`search`'s own
`--format` is its output's, a table or JSON). `--concurrency` is how many cuts run at once, 1 to 8,
2 unless given. `--max-cost USD` is the most the whole command may spend on model calls: with
`--expand-llm`, the expansion's call and the cuts' calls are held to that one limit. Each of them
without `--auto-cut` is a usage error, as is an unknown profile; nothing is searched.

## Files

Beside `--output`: `<name>.manifest.json`, the same cards' manifest, and `report.json`, one entry per
result tried. The bundle and the manifest are written only when a card was cut, VERIFIED or not;
report.json always. Each is written in one step, a file beside it renamed into place.

## Exit codes

0 when N cards are VERIFIED, whatever the search's own status (a partial search's providers are named
in the footer and in report.json's `partial_providers`; one the search left out of its status, missing
only configuration, is in the footer but not in `partial_providers`, `v1-e07-t23`). 8
(`AUTO_CUT_SHORT`) when every result was tried and fewer were VERIFIED, 9 (`BUDGET_EXCEEDED`) when the
budget stopped it short. A search that could not give results ends as `search` does, with nothing cut:
1, 3 or 7.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NoReturn

import typer

from debate_cli.container import LOCAL_OWNER_ID, BatchCutting
from debate_cli.context import CliContext, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.budget import MAX_COST_OPTION, with_max_cost
from debate_cli.output import CommandFailure, JsonValue
from debate_cli.presenters.batch_report_presenter import (
    AutoCutFiles,
    AutoCutSettings,
    exit_code_for_batch,
    report_failure,
    report_payload,
    report_table,
)
from debate_core.application.batch_cut_service import (
    BatchCandidate,
    BatchCutRequest,
    BatchNeed,
    BatchReport,
    batch_candidates,
    batch_need,
)
from debate_core.application.federated_search_types import SearchOutcome
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE

__all__ = [
    "DEFAULT_CONCURRENCY",
    "MAX_CONCURRENCY",
    "REPORT_FILE_NAME",
    "AutoCutOptions",
    "auto_cut",
    "auto_cut_options",
    "cut_and_write",
    "write_atomically",
]

DEFAULT_CONCURRENCY: Final = 2
MAX_CONCURRENCY: Final = 8
"""The most cuts `--concurrency` lets run at once: never unbounded, and each host is paced by the fetcher."""
REPORT_FILE_NAME: Final = "report.json"


@dataclass(frozen=True, slots=True)
class AutoCutOptions:
    """`--auto-cut` and the options that go with it, checked."""

    wanted: int
    output: Path
    card_format: str
    concurrency: int
    max_cost: float | None

    @property
    def manifest(self) -> Path:
        return self.output.with_name(f"{self.output.stem}.manifest.json")

    @property
    def report(self) -> Path:
        return self.output.parent / REPORT_FILE_NAME


def auto_cut_options(
    cli: CliContext,
    *,
    wanted: int | None,
    output: Path | None,
    card_format: str | None,
    concurrency: int | None,
    max_cost: float | None,
    expanded: bool,
) -> AutoCutOptions | None:
    """The checked options, or None without `--auto-cut`; a usage error for any that do not go together.

    With `--max-cost`, the command's settings take it as their per-run limit from here on, so every
    model router the command builds is guarded by it, and all of them count against it together: the
    container gives them the command's one budget run (v1-e08-t17).
    """
    given = [
        flag
        for flag, value in (
            ("--output", output),
            ("--card-format", card_format),
            ("--concurrency", concurrency),
            (MAX_COST_OPTION, max_cost),
        )
        if value is not None
    ]
    if wanted is None:
        if given:
            raise typer.BadParameter(f"{' and '.join(given)} go with --auto-cut", param_hint="--auto-cut")
        return None
    if not expanded:
        raise typer.BadParameter(
            "--auto-cut needs --argument and --need: they say what every card is cut for",
            param_hint="--auto-cut",
        )
    if output is None:
        raise typer.BadParameter(
            "--auto-cut needs --output, the .docx bundle to write", param_hint="--output"
        )
    if not output.parent.is_dir():
        raise typer.BadParameter(f"{output.parent} is not a directory", param_hint="--output")
    profile = card_format or DEFAULT_FORMAT_PROFILE
    profiles = cli.services.format_profiles()
    if profile not in profiles:
        raise typer.BadParameter(
            f"no format profile named {profile!r}; the profiles are {', '.join(sorted(profiles))}",
            param_hint="--card-format",
        )
    if max_cost is not None:
        cli.services.override("settings", with_max_cost(cli.services.settings, max_cost))
    return AutoCutOptions(wanted, output, profile, concurrency or DEFAULT_CONCURRENCY, max_cost)


def auto_cut(
    cli: CliContext,
    ctx: typer.Context,
    outcome: SearchOutcome,
    search: dict[str, JsonValue],
    options: AutoCutOptions,
) -> None:
    """Cut the search's results into the bundle, write report.json, print the table, end with the code."""
    expansion = outcome.search.expansion
    assert expansion is not None, "--auto-cut is refused without --argument and --need"
    need = batch_need(cli.services.argument_taxonomy(), expansion, outcome.search.query)
    report, files = _run(
        cut_and_write(cli.services.batch_cutting(), batch_candidates(outcome), need, options)
    )
    payload = report_payload(
        report,
        outcome,
        need,
        AutoCutSettings(options.wanted, options.concurrency, options.card_format, options.max_cost),
        files,
    )
    write_atomically(files.report, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    data: dict[str, JsonValue] = {"search": search, "auto_cut": payload}
    exit_code = exit_code_for_batch(report)
    if exit_code is ExitCode.OK or not cli.output.is_json:
        cli.output.success(command_name(ctx), data, display=report_table(report, outcome, need, files))
    if exit_code is not ExitCode.OK:
        _end(cli, ctx, report_failure(report, data, exit_code))


async def cut_and_write(
    batch: BatchCutting, candidates: Sequence[BatchCandidate], need: BatchNeed, options: AutoCutOptions
) -> tuple[BatchReport, AutoCutFiles]:
    """Run the batch over `candidates`, then write the bundle and its manifest when a card was cut.

    The bundle's block heading is `need`'s. `search --auto-cut` gives its ranked results; `daily
    --auto-cut` its digest's new results, each with its own need (v1-e08-t07).
    """
    async with batch:
        report = await batch.service.cut(
            BatchCutRequest(
                candidates=candidates,
                wanted=options.wanted,
                need=need,
                owner_id=LOCAL_OWNER_ID,
                concurrency=options.concurrency,
                format_profile=options.card_format,
            )
        )
        if not (report.verified or report.unverified):
            return report, AutoCutFiles(report=options.report)
        document = await batch.export.export_docx_bundle(
            report.verified,
            report.unverified,
            profile=batch.profiles[options.card_format],
            block=need.heading,
        )
        manifest = await batch.export.export_json_bundle(report.verified, report.unverified)
    write_atomically(options.output, document)
    write_atomically(options.manifest, manifest)
    return report, AutoCutFiles(report=options.report, bundle=options.output, manifest=options.manifest)


def write_atomically(path: Path, content: bytes) -> None:
    """Write `content` in one step: a file beside it, renamed into place, so no half-written file is left."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)

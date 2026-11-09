"""`debate-research daily <preset> --date YYYY-MM-DD`: one day's new research as a digest (`v1-e08-t07`).

The deciding is `debate_core`'s: :class:`~debate_core.application.digest_service.DigestService` runs
the preset's searches (`config/daily_presets.yaml`) through `search`'s federated search for the
window, leaves out what an earlier digest of the preset listed, groups the rest by argument and need,
and records them as listed only once the file is written. What is here is the command-line surface:
the options, writing the file, and the exit code. The Markdown, the JSON and the summary are
:mod:`debate_cli.presenters.daily_presenter`'s.

## Files

`<digest dir>/<preset>-<date>.md`, or `.json` with `--format json`; the directory is `digests` in the
working directory unless `--digest-dir` names another, and is made if missing. Each is written in one
step. Running a date again writes its digest again. What each preset has listed is kept in the data
directory, `<data dir>/daily/seen/<preset>.json`, never beside the digests.

## `--auto-cut N`

Hands the digest's new results to `search --auto-cut`'s batch, which cuts them until N cards are
VERIFIED: each group's top result first, each cut for its own argument and need. The bundle is
`<preset>-<date>.docx` beside the digest, with its manifest and `report.json`, named as `search
--auto-cut` names them.

## Exit codes

0 complete (with new results or none), 6 partial (the digest is written, and the footer names each
provider that did not answer), 3 when no provider answered and 1 when none of the preset's providers
is enabled (no digest is written, and nothing is marked listed), 2 for a usage error such as an
unknown preset (the message lists the presets). With `--auto-cut`, 8 or 9 when fewer than N cards
are VERIFIED, as for `search`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from debate_cli.container import DailyDigesting
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode
from debate_cli.presenters.batch_report_presenter import (
    AutoCutSettings,
    batch_report_table,
    exit_code_for_batch,
    report_failure,
)
from debate_cli.presenters.daily_presenter import (
    DigestFormat,
    auto_cut_footer,
    auto_cut_payload,
    digest_failure,
    digest_file_name,
    digest_footer,
    digest_markdown,
    digest_payload,
    digest_table,
    exit_code_for_digest,
)
from debate_cli.search_auto_cut import DEFAULT_CONCURRENCY, AutoCutOptions, cut_and_write, write_atomically
from debate_core.application.digest_service import (
    Digest,
    DigestRequest,
    DigestWindow,
    DigestWriter,
    digest_batch_candidates,
    digest_bundle_need,
)
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.domain.daily_preset import DailyPreset

__all__ = ["daily"]

DATE_FORMAT = "%Y-%m-%d"
DEFAULT_DIGEST_DIRECTORY = Path("digests")


def daily(
    ctx: typer.Context,
    preset: Annotated[
        str, typer.Argument(help="The preset in config/daily_presets.yaml, e.g. politics or nhi.")
    ],
    day: Annotated[
        datetime | None,
        typer.Option(
            "--date", formats=[DATE_FORMAT], help="The date the digest is for. Default: today, UTC."
        ),
    ] = None,
    window: Annotated[
        str, typer.Option("--window", help="How many days, ending with --date, to search: 1d to 31d.")
    ] = "1d",
    file_format: Annotated[
        DigestFormat,
        typer.Option("--format", case_sensitive=False, help="md for the coach, json for programs."),
    ] = DigestFormat.MD,
    auto_cut_count: Annotated[
        int | None,
        typer.Option(
            "--auto-cut",
            metavar="N",
            min=1,
            max=50,
            help="Then cut the new results until N cards are VERIFIED, into <preset>-<date>.docx beside "
            "the digest, as search --auto-cut does.",
        ),
    ] = None,
    digest_dir: Annotated[
        Path,
        typer.Option("--digest-dir", file_okay=False, help="Where the digest is written, made if missing."),
    ] = DEFAULT_DIGEST_DIRECTORY,
) -> None:
    """Write one day's digest of new research for a preset, grouped by argument and need.

    Runs the preset's queries, each expanded for each of its argument/need pairs, through search's
    providers for the window, and writes digests/<preset>-<date>.md: each new result's title,
    publisher, date, why it ranked, and its URL. Results an earlier digest of the same preset listed
    are left out; a run of the same date again lists its own again. Results count as listed only once
    the digest file is written.

    Exit codes:
    0  complete: every provider answered; the digest is written, with new results or none
    1  no provider was asked: none of the preset's providers is enabled; nothing is written
    2  usage error, for example an unknown preset (the presets are listed) or a --window that is not 1d to 31d
    3  no provider answered; nothing is written and nothing is marked listed
    6  partial: the digest is written; the footer names each provider that did not answer
    8  auto-cut short: every new result was tried, and fewer than N cards are VERIFIED
    9  budget exceeded: the budget guard stopped --auto-cut short of N cards
    """
    cli = cli_context(ctx)
    if file_format is DigestFormat.JSON and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    chosen = _preset(cli, preset)
    request = DigestRequest(chosen, _day(cli, day), _window(window))
    digesting = cli.services.daily_digesting(feed_topics=chosen.feed_topics)
    _progress(cli, ctx, request)
    digest = _run(_digest(digesting, request, partial(_write, digest_dir, file_format)))
    payload = {**digest_payload(digest), "file": str(digest.file) if digest.file is not None else None}
    exit_code = exit_code_for_digest(digest)
    if auto_cut_count is not None and digest.file is not None:
        return _auto_cut(cli, ctx, digest, payload, _cut_options(digest, auto_cut_count))
    if exit_code is ExitCode.OK:
        cli.output.success(command_name(ctx), payload, display=digest_table(digest))
        return
    if exit_code is ExitCode.SEARCH_PARTIAL and not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=digest_table(digest))
    elif not cli.output.is_json:
        cli.output.note("\n".join(digest_footer(digest)))
    _end(cli, ctx, digest_failure(digest, payload, exit_code))


# ------------------------------------------------------------------------------------------------
# The request
# ------------------------------------------------------------------------------------------------


def _preset(cli: CliContext, name: str) -> DailyPreset:
    """The preset named `name`, or a usage error listing the presets there are."""
    presets = cli.services.daily_presets()
    found = presets.find(name)
    if found is None:
        raise typer.BadParameter(
            f"no daily preset named {name!r}; the presets are {', '.join(presets.names)}", param_hint="PRESET"
        )
    return found


def _day(cli: CliContext, given: datetime | None) -> date:
    """`--date`, or today in UTC by the container's clock."""
    if given is not None:
        return given.date()
    return cli.services.clock()().astimezone(UTC).date()


def _window(text: str) -> DigestWindow:
    try:
        return DigestWindow.parse(text)
    except ValueError as invalid:
        raise typer.BadParameter(str(invalid), param_hint="--window") from None


def _progress(cli: CliContext, ctx: typer.Context, request: DigestRequest) -> None:
    preset = request.preset
    searches = len(preset.pairs) * len(preset.queries)
    cli.output.event_line(
        command_name(ctx),
        "digesting",
        {"preset": preset.name, "date": request.day.isoformat(), "window": str(request.window)},
        text=f"Building the {preset.name} digest for {request.day.isoformat()} ({request.window}): "
        f"{searches} {'search' if searches == 1 else 'searches'} of {', '.join(preset.providers)}",
    )


# ------------------------------------------------------------------------------------------------
# The digest and its file
# ------------------------------------------------------------------------------------------------


async def _digest(digesting: DailyDigesting, request: DigestRequest, write: DigestWriter) -> Digest:
    """Build and write the digest, closing every provider when it ends, however it ends."""
    async with digesting:
        return await digesting.service.run(request, write)


def _write(directory: Path, file_format: DigestFormat, digest: Digest) -> Path:
    """Render the digest and write it in one step; called by the service before anything is marked listed."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / digest_file_name(digest, file_format)
    if file_format is DigestFormat.MD:
        text = digest_markdown(digest)
    else:
        text = json.dumps(digest_payload(digest), ensure_ascii=False, indent=2) + "\n"
    write_atomically(path, text.encode("utf-8"))
    return path


# ------------------------------------------------------------------------------------------------
# --auto-cut
# ------------------------------------------------------------------------------------------------


def _cut_options(digest: Digest, wanted: int) -> AutoCutOptions:
    """`search --auto-cut`'s options with its defaults, and the bundle named after the digest."""
    assert digest.file is not None, "the bundle goes beside a written digest"
    bundle = digest.file.with_name(f"{digest.preset.name}-{digest.day.isoformat()}.docx")
    return AutoCutOptions(wanted, bundle, DEFAULT_FORMAT_PROFILE, DEFAULT_CONCURRENCY, None)


def _auto_cut(
    cli: CliContext,
    ctx: typer.Context,
    digest: Digest,
    digest_data: dict[str, JsonValue],
    options: AutoCutOptions,
) -> None:
    """Cut the digest's new results into the bundle, write report.json, print the table, end with the code."""
    need = digest_bundle_need(digest)
    candidates = digest_batch_candidates(digest)
    report, files = _run(cut_and_write(cli.services.batch_cutting(), candidates, need, options))
    settings = AutoCutSettings(options.wanted, options.concurrency, options.card_format, options.max_cost)
    payload = auto_cut_payload(report, digest, settings, files)
    write_atomically(files.report, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    data: dict[str, JsonValue] = {"digest": digest_data, "auto_cut": payload}
    exit_code = exit_code_for_batch(report)
    if exit_code is ExitCode.OK or not cli.output.is_json:
        display = batch_report_table(report, auto_cut_footer(digest), need.heading, files)
        cli.output.success(command_name(ctx), data, display=display)
    if exit_code is not ExitCode.OK:
        _end(cli, ctx, report_failure(report, data, exit_code))


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion: a CLI command is the one caller with no event loop of its own."""
    return asyncio.run(awaitable)

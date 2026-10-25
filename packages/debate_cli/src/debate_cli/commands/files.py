"""`debate-research files`: build an evidence file from a recipe, check a built file, suggest a draft.

::

    debate-research files build ~/.debate-research/dev/files/recipes/nhi/politics-da-answers.yaml
    debate-research files build <recipe> --out ~/e33-files --allow-draft
    debate-research files check ~/.debate-research/dev/files/built/nhi/politics-da-answers.docx
    debate-research files suggest --caselist hspolicy26 --position politics-da --top 10

Every decision is the services' (`v1-e33-t03`): :class:`~debate_core.application.file_build_service.
FileBuildService` for `build` and `check`, which runs the
:class:`~debate_core.application.file_quality_service.FileQualityService` the container wires
(`v1-e33-t04`), and :class:`~debate_core.application.file_suggest_service.FileSuggestService` for
`suggest`. This module parses the options and :mod:`debate_cli.presenters.files_presenter` renders;
the exit codes are documented there and in each command's `--help`.

Nothing reaches a bucket, a model or the network. Built files and their sidecars hold card text and
who disclosed each card, so neither a built file nor a draft is ever written inside a git working tree.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from debate_cli.commands.caselist import _snapshot_date  # pyright: ignore[reportPrivateUsage]
from debate_cli.commands.landscape import _config_dir  # pyright: ignore[reportPrivateUsage]
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.output import CliOutput, CommandFailure, OutputMode
from debate_cli.presenters.files_presenter import (
    Rendered,
    build_rendered,
    check_rendered,
    refused_request,
    suggest_rendered,
    unattributed_lines,
)
from debate_core.application.file_build_service import BuildFileRequest, UnattributedCard
from debate_core.application.file_suggest_service import SuggestRefused, SuggestRequest
from debate_core.application.landscape_run import LandscapeRequestRefused
from debate_core.domain.caselist import Side

__all__ = ["BUILD_HELP", "CHECK_HELP", "SUGGEST_HELP", "build", "check", "suggest"]

_JSON_HELP = "Write one machine-readable JSON object to stdout."

BUILD_HELP = (
    "Build an evidence file from a recipe: <name>.docx, its .provenance.json, and its quality report.\n\n"
    "Exit 0: built, and every quality check passed or only warned.\n\n"
    "Exit 1: the recipe does not load or resolve (every error listed), the parsed store was made by "
    "another parser or fingerprint version, a source is missing (with the `store get` that fetches it), "
    "the writer refuses a card, or a quality check FAILs (the files are kept).\n\n"
    "Exit 2: a draft without --allow-draft, or an --out inside a git working tree."
)
"""`files build --help`; its docstring is set to it, so Rich wraps each paragraph whole."""

CHECK_HELP = (
    "Check a built evidence file and write its .quality.json and .quality.md beside it, building "
    "nothing.\n\n"
    "Exit 0: every check passed or only warned. Exit 1: a check FAILs, named, with what explains it "
    "when that is known."
)

SUGGEST_HELP = (
    "Write a draft recipe from the landscape's most-read cards for a position: status draft, no tags, "
    "and no model called.\n\n"
    "Exit 0: the draft is written. Exit 1: the landscape report cannot be built.\n\n"
    "Exit 2: a caselist, snapshot, position or side the landscape does not have, or a draft path "
    "that is taken or inside a git working tree."
)


def build(
    ctx: typer.Context,
    recipe: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="The recipe's YAML file (v1-e33-t01).")
    ],
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            file_okay=False,
            help="Write here. Default: <data dir>/files/built/<topic>/. Never inside a git working tree.",
        ),
    ] = None,
    allow_draft: Annotated[
        bool, typer.Option("--allow-draft", help="Build a status: draft recipe; its header will say DRAFT.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    cli = _context(ctx, json_output)
    service = cli.services.file_build()
    result = asyncio.run(
        service.build(
            BuildFileRequest(recipe, out_dir=out, allow_draft=allow_draft),
            on_unattributed=lambda cards: _note_unattributed(cli, cards),
        )
    )
    _report(cli, ctx, build_rendered(result))


def check(
    ctx: typer.Context,
    file: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, help="A built .docx, with its .provenance.json beside it."
        ),
    ],
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    cli = _context(ctx, json_output)
    result = asyncio.run(cli.services.file_build().check(file))
    _report(cli, ctx, check_rendered(result))


def suggest(
    ctx: typer.Context,
    caselist: Annotated[str, typer.Option("--caselist", help="Caselist slug, e.g. hspolicy26.")],
    position: Annotated[str, typer.Option("--position", help="Position id, as the landscape names it.")],
    side: Annotated[
        Side | None,
        typer.Option("--side", case_sensitive=False, help="The file's side. Default: the position's."),
    ] = None,
    snapshot: Annotated[
        str | None, typer.Option("--snapshot", help="The weekly snapshot, YYYY-MM-DD. Default: the newest.")
    ] = None,
    top: Annotated[int, typer.Option("--top", min=1, help="How many of the most-read cards to draft.")] = 10,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            dir_okay=False,
            help=(
                "Where to write the draft. "
                "Default: <data dir>/files/recipes/<topic>/<position>-<side>-draft.yaml."
            ),
        ),
    ] = None,
    config_dir: Annotated[
        Path | None,
        typer.Option(
            "--config-dir",
            file_okay=False,
            help="The directory holding topics.yaml. Default: config/landscape in this checkout.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    cli = _context(ctx, json_output)
    request = SuggestRequest(
        caselist=caselist, position=position, side=side, snapshot=_day(snapshot), top=top, out=out
    )
    service = cli.services.file_suggest(config_dir=_config_dir(config_dir))
    try:
        result = asyncio.run(service.suggest(request))
    except (SuggestRefused, LandscapeRequestRefused) as refused:
        _end(cli, ctx, refused_request(refused, known=refused.known, hint=_hint_of(refused)))
    _report(cli, ctx, suggest_rendered(result))


build.__doc__ = BUILD_HELP
check.__doc__ = CHECK_HELP
suggest.__doc__ = SUGGEST_HELP


def _context(ctx: typer.Context, json_output: bool) -> CliContext:
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    return cli


def _day(snapshot: str | None) -> date | None:
    return _snapshot_date(snapshot) if snapshot is not None else None


def _hint_of(refused: Exception) -> str | None:
    hint = getattr(refused, "hint", None)
    if isinstance(hint, str):
        return hint
    edit = getattr(refused, "file_to_edit", None)
    return f"Edit {edit}." if isinstance(edit, str) else None


def _note_unattributed(cli: CliContext, cards: Sequence[UnattributedCard]) -> None:
    for line in unattributed_lines(cards):
        cli.output.note(line)


def _report(cli: CliContext, ctx: typer.Context, rendered: Rendered) -> None:
    """The result, then, for an outcome that failed, its failure and its exit code."""
    if rendered.failure is None or not cli.output.is_json:
        cli.output.success(command_name(ctx), rendered.payload, display=rendered.display)
    if rendered.failure is not None:
        _end(cli, ctx, rendered.failure)


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)

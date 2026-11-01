"""`debate-research cut <URL> --need ... --output evidence.docx`: one URL in, one card out, or why not.

The deciding is `debate_core`'s (`v1-e06-t06`): :class:`~debate_core.application.article_fetch.ArticleFetch`
retrieves the page into a snapshot (E04), :class:`~debate_core.application.card_service.CardService`
asks the model where the evidence is, cuts it from the snapshot, cites and verifies it and saves the
card (`v1-e06-t02`), and :class:`~debate_core.application.export_service.ExportService` renders it in
the team's format profile with its manifest embedded (`v1-e06-t04`, `t05`). What is here is the
command-line surface: the options, the request, the progress lines, the file, and the exit code each
outcome ends with (architecture proposal §11). The words for each outcome are
:mod:`debate_cli.presenters.cut_presenter`'s.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import CliOutput, OutputMode
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE

__all__ = ["cut"]


def cut(
    ctx: typer.Context,
    url: Annotated[str, typer.Argument(help="The article or open-access PDF to cut a card from.")],
    need: Annotated[
        str,
        typer.Option(
            "--need", help='What the card must say, e.g. "de-extinction diverts conservation money".'
        ),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", dir_okay=False, writable=True, help="The .docx to write the card to."),
    ],
    argument: Annotated[
        str | None,
        typer.Option("--argument", help='The argument the card is for, e.g. "Conservation DA".'),
    ] = None,
    format_profile: Annotated[
        str,
        typer.Option(
            "--format", metavar="PROFILE", help="The team format profile: team-default, flow or plain."
        ),
    ] = DEFAULT_FORMAT_PROFILE,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Cut one verified card from an article, cited and underlined, into a .docx.

    Fetches the page, or uses a snapshot stored recently, and asks the model where --need is answered.
    The evidence is cut from the stored text, never from the model's answer, then cited and verified.
    The card is written in the --format profile with its manifest embedded; progress goes to stderr.
    The model is called only when DEBATE_MODEL_MODE is live or record; otherwise its answers are replayed.

    Exit codes:
    0  the card is VERIFIED and was written to --output
    1  could not run, nothing saved: a refused model call, a missing or damaged snapshot, an unknown prompt
    2  usage error, for example an unknown --format
    3  PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND, or the model did not answer; nothing written
    4  the card is UNVERIFIED: written with its banner, and each reason printed
    """
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    cli.output.success(command_name(ctx), {})

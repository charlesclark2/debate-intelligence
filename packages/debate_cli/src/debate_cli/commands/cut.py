"""`debate-research cut <URL> --need ... --output evidence.docx`: one URL in, one card out, or why not.

The deciding is `debate_core`'s (`v1-e06-t06`): :class:`~debate_core.application.article_fetch.ArticleFetch`
retrieves the page into a snapshot (E04), :class:`~debate_core.application.card_service.CardService`
asks the model where the evidence is, cuts it from the snapshot, cites and verifies it and saves the
card (`v1-e06-t02`), and :class:`~debate_core.application.export_service.ExportService` renders it in
the team's format profile with its manifest embedded (`v1-e06-t04`, `t05`). What is here is the
command-line surface: the options, the request, the file, and the exit code each outcome ends with
(architecture proposal §11). The words for each stage and outcome are
:mod:`debate_cli.presenters.cut_presenter`'s.

## Exit codes

From :mod:`debate_cli.exit_codes`:

* `0`: the card is VERIFIED and was written to `--output`.
* `1`: the cut could not run and nothing was saved, nor any card id printed: the model provider
  refused the call (`MODEL_ACCESS_DENIED`, `MODEL_REQUEST_REJECTED`), the snapshot is missing or
  damaged, a prompt is not registered, no answer was recorded for a replayed call, or the URL names
  no source. These are exceptions; the root group maps them. With `--from-paste`, also no copy stored
  for the URL (`NO_USER_SUPPLIED_COPY`), with a hint naming `fetch --paste`.
* `2`: the command line was wrong: no `--need`, a `--format` no profile has, an `--output` in a
  directory that does not exist. Nothing is fetched.
* `3`: the source is PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND, UNSUPPORTED_TYPE or ERROR
  (`SOURCE_NOT_ACCESSIBLE`, with the status and the canonical URL), or the model provider did not
  answer or throttled the call. No card is saved and nothing is written.
* `4`: the card is UNVERIFIED (`CARD_UNVERIFIED`): saved, written to `--output` with its banner, and
  each reason printed. A card cut `--from-paste` always is, for its cite (see below).

## `--from-paste`

The way to cut an article the coach can read and the platform cannot, such as one behind a library
subscription (`v1-e06-t08`). `fetch --paste FILE --source-url URL` stores the coach's copy as
USER_SUPPLIED, after they attest lawful access; `cut URL --from-paste` cuts from the newest copy stored
for that URL's canonical form, through
:meth:`~debate_core.application.article_fetch.ArticleFetch.user_supplied_copy`. Nothing is fetched,
and the publisher's snapshot never stands in for the copy. The card carries USER_SUPPLIED provenance
(the manifest's card says so, and its snapshot reference names that copy), its cite ends "user-supplied
text", and its evidence is verified against the copy exactly as against a retrieved page. Its cite is
not: the citation rules verify no cite field of text a user supplied (`v1-e06-t01`), so the card is
UNVERIFIED for its cite alone (`CITATION_UNVERIFIED`, exit 4), and `verify` says the same.

## `--json`

Accepted after the command as well as before it. One object on stdout: the cut under `data` on exit
0, the same under `error.details` on exit 4 (:func:`~debate_cli.presenters.cut_presenter.cut_payload`),
and the failure otherwise. Progress is on stderr, one event object per stage. Neither holds evidence
text: the manifest, evidence included, is the one embedded in the .docx.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from typing import Annotated, Any, NoReturn

import typer

from debate_cli.commands.fetch import ATTESTATION_FLAG
from debate_cli.container import LOCAL_OWNER_ID, CardCutting
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.output import CliOutput, CommandFailure, OutputMode
from debate_cli.presenters.cut_presenter import (
    CutProgress,
    cut_payload,
    not_accessible,
    unverified,
    verdict_table,
)
from debate_core.application.article_fetch import ArticleFetch, FetchReport
from debate_core.application.article_service import NoUserSuppliedCopy
from debate_core.application.card_types import CutRequest, CutResult
from debate_core.domain import AccessStatus
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.evidence.docx_manifest_part import read_embedded_manifest_bytes
from debate_core.evidence.format_profile import ResolvedFormatProfile
from debate_core.evidence.selection_contract import CARD_MARKUP_PROMPT_ID, CARD_SELECT_PROMPT_ID

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
    from_paste: Annotated[
        bool,
        typer.Option(
            "--from-paste",
            help="Cut from your copy of this URL stored with fetch --paste, as USER_SUPPLIED. No fetch.",
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Cut one verified card from an article, cited and underlined, into a .docx.

    Fetches the page, or uses a snapshot stored recently, and asks the model where --need is answered.
    The evidence is cut from the stored text, never from the model's answer, then cited and verified.
    The card is written in the --format profile with its manifest embedded; progress goes to stderr.
    The model is called only when DEBATE_MODEL_MODE is live or record; otherwise its answers are replayed.

    With --from-paste, cuts from the copy you stored with fetch --paste instead, and fetches nothing.
    The card says it is USER_SUPPLIED; its cite is never verified, so it is UNVERIFIED (exit 4).

    Exit codes:
    0  the card is VERIFIED and was written to --output
    1  could not run, nothing saved: a refused model call, a missing or damaged snapshot, an unknown
       prompt, or for --from-paste no copy stored with fetch --paste
    2  usage error, for example an unknown --format
    3  PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND, or the model did not answer; nothing written
    4  the card is UNVERIFIED: written with its banner, and each reason printed
    """
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    profile = _profile(cli, format_profile)
    _check_output(output)
    cutting = cli.services.card_cutting()

    def request_for(snapshot_id: str) -> CutRequest:
        return CutRequest(
            snapshot_id=snapshot_id,
            need=need,
            owner_id=LOCAL_OWNER_ID,
            argument=argument,
            format_profile=format_profile,
        )

    progress = CutProgress(cli.output, command_name(ctx))
    try:
        done = _run(
            _cut(
                cli.services.article_fetch(),
                cutting,
                url,
                request_for,
                profile,
                progress,
                from_paste=from_paste,
            )
        )
    except NoUserSuppliedCopy as missing:
        _end(cli, ctx, CommandFailure.from_exception(missing, hint=_paste_hint(url, output)))
    if done.result is None or done.document is None:
        _end(cli, ctx, not_accessible(done.report, output))
    _write(output, done.document)
    progress.exported(output, format_profile)
    payload = cut_payload(
        done.report,
        done.result,
        output=output,
        profile=format_profile,
        manifest_bytes=read_embedded_manifest_bytes(output),
    )
    if not cli.output.is_json or done.result.is_verified:
        cli.output.success(
            command_name(ctx), payload, display=verdict_table(done.result, payload, done.report)
        )
    if not done.result.is_verified:
        _end(cli, ctx, unverified(done.result, payload))


@dataclass(frozen=True)
class _Done:
    """What a run came to: the retrieval, and for an ACCESSIBLE source the card and its document."""

    report: FetchReport
    result: CutResult | None = None
    document: bytes | None = None


def _profile(cli: CliContext, name: str) -> ResolvedFormatProfile:
    """The format profile `--format` names, or a usage error listing the ones there are."""
    profiles = cli.services.format_profiles()
    if name not in profiles:
        raise typer.BadParameter(
            f"no format profile named {name!r}; the profiles are {', '.join(sorted(profiles))}",
            param_hint="--format",
        )
    return profiles[name]


def _check_output(output: Path) -> None:
    """Refuse, before anything is fetched, an `--output` whose directory does not exist."""
    if not output.parent.is_dir():
        raise typer.BadParameter(f"{output.parent} is not a directory", param_hint="--output")


async def _cut(
    fetching: ArticleFetch,
    cutting: CardCutting,
    url: str,
    request_for: Callable[[str], CutRequest],
    profile: ResolvedFormatProfile,
    progress: CutProgress,
    *,
    from_paste: bool,
) -> _Done:
    """Fetch, or read the stored pasted copy, then cut and export the card: the three services, in order.

    A retrieval is cut only when the source is ACCESSIBLE; a pasted copy whatever status its user
    reported, as CardService decides.
    """
    async with fetching, cutting:
        report = await (fetching.user_supplied_copy(url) if from_paste else fetching.retrieve(url))
        progress.fetched(report)
        if report.snapshot is None or (
            not from_paste and report.access_status is not AccessStatus.ACCESSIBLE
        ):
            return _Done(report)
        progress.extracted(report.snapshot)
        progress.selecting((CARD_SELECT_PROMPT_ID, CARD_MARKUP_PROMPT_ID))
        result = await cutting.cards.cut_card(request_for(report.snapshot.snapshot_id))
        progress.verified(result)
        document = await cutting.export.export_docx(
            [result.card], profile=profile, failures={result.card.card_id: result.reasons}
        )
        return _Done(report, result, document)


def _paste_hint(url: str, output: Path) -> str:
    return (
        f"No card was cut and nothing was written to {output}. Store your copy first, if you can read it "
        f"lawfully: debate-research fetch --paste FILE --source-url {quote(url)} {ATTESTATION_FLAG}"
    )


def _write(output: Path, document: bytes) -> None:
    """Write the .docx in one step: a file beside it, renamed into place, so no half-written card is left."""
    handle, temporary = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(document)
        Path(temporary).replace(output)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    """Report ``failure`` and end the run with its exit code."""
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion: a CLI command is the one caller with no event loop of its own."""
    return asyncio.run(awaitable)

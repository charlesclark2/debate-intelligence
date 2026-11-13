"""`debate-research fetch <URL>`: retrieve a source into a hashed snapshot, or say exactly why not.

The deciding is :class:`~debate_core.application.article_service.ArticleService`'s, in `debate_core`,
reached through :class:`~debate_core.application.article_fetch.ArticleFetch`: fetching politely,
classifying the access status, extracting the text and storing the snapshot (v1-e04-t02 to t05). What
is here is the command-line surface: the arguments, the attestation for pasted text, a table or a
failure panel for a person, one JSON object for a program, and which exit code each outcome ends with
(architecture proposal §11).

Articles and snapshots are stored in this environment's data directory (`storage.data_dir`), where
`verify` reads them. A page that is not ACCESSIBLE stores no snapshot.

## Exit codes

From :mod:`debate_cli.exit_codes`:

* `0`: the page is ACCESSIBLE and its snapshot is stored (or a fresh stored one answered), or pasted
  text was stored as USER_SUPPLIED.
* `1`: refused before anything was stored: the URL names no source (`INVALID_SOURCE_URL`), pasted text
  was not attested (`USER_TEXT_NOT_ATTESTED`), or it failed a quality gate (`USER_TEXT_REJECTED`).
* `2`: the command line was wrong, for example `--paste` without `--source-url`.
* `3`: the page is PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND, UNSUPPORTED_TYPE or ERROR
  (`SOURCE_NOT_ACCESSIBLE`, with the status, the reason and the rules version), or the fetcher could
  not run at all. No snapshot is stored.

## `--paste`

The lawful path for an article the coach can read and the platform cannot, such as one behind a
subscription (§19). The text comes from a file, or `-` for stdin, and is stored under the article for
`--source-url` with `provenance_mode` USER_SUPPLIED, which every card cut from it carries. Nothing is
fetched. `cut URL --from-paste` cuts from it (`v1-e06-t08`), and a page that is not ACCESSIBLE says so
in its hint. It is stored only after the user attests lawful access: by answering the prompt in a terminal,
or with `--i-have-lawful-access` anywhere else (with `--json`, when the text comes from stdin, or when
stdin is not a terminal). A run that can neither prompt nor was given the flag stores nothing and
exits 1.

With `--paste`, `--title`, `--author` (once per author, in order), `--date` (`YYYY`, `YYYY-MM` or
`YYYY-MM-DD`, kept at that precision and never completed to a day, `v1-e06-t13`) and
`--publication` state the copy's cite fields (`v1-e06-t12`). They are stored with the copy,
unverified, and a card cut from it is cited with them; it stays UNVERIFIED for its cite, as text a
user supplied always is. Any of them without `--paste`, an empty value, or a date in another form is
a usage error. The table prints the fields stored with the copy. Stored again, identical text with
none of these options, or with the newest copy's own, reuses that copy and its fields; with others
it is a new copy holding exactly those, so a field must be stated again to be kept.

## `--json`

Accepted after the command (`fetch <URL> --json`, as the spec writes it) as well as before it
(`debate-research --json fetch <URL>`). One object on stdout, described by
`packages/debate_core/schemas/fetch_result.v1.json`: the report under `data` on exit 0, the same
report under `error.details` for a status that is not ACCESSIBLE. Neither ever contains page text or
pasted text.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from shlex import quote
from typing import Annotated, Any, NoReturn

import typer

from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.lawful_access import ATTESTATION_FLAG
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode, TableSpec
from debate_core.application.article_fetch import (
    SOURCE_NOT_ACCESSIBLE_CODE,
    ArticleFetch,
    FetchReport,
    StatedCite,
)
from debate_core.application.article_service import UserTextNotAttested
from debate_core.application.citation_service import InvalidStatedCite, stated_citation
from debate_core.domain import AccessStatus, Citation, ProvenanceMode

__all__ = ["ATTESTATION_FLAG", "CITE_OPTIONS", "fetch", "stdin_is_a_terminal"]

CITE_OPTIONS = {
    "title": "--title",
    "authors": "--author",
    "published_at": "--date",
    "publication": "--publication",
}
"""The option that states each cite field with --paste (`v1-e06-t12`)."""

NOT_STATED = "not stated"

ATTESTATION_PROMPT = (
    "Store this text as USER_SUPPLIED for {url}? Answer yes only if you have lawful access to it "
    "(a subscription, a library copy) and it is that article's text"
)


def fetch(
    ctx: typer.Context,
    url: Annotated[
        str | None,
        typer.Argument(help="The article or open-access PDF to retrieve. Not with --paste."),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Ask the publisher again even when a stored snapshot is recent."),
    ] = False,
    paste: Annotated[
        typer.FileText | None,
        typer.Option(
            "--paste",
            help="Store text you lawfully have, from a file or - (stdin), as USER_SUPPLIED. Fetches nothing.",
        ),
    ] = None,
    source_url: Annotated[
        str | None,
        typer.Option("--source-url", help="With --paste: the URL of the article the text is from."),
    ] = None,
    lawful_access: Annotated[
        bool,
        typer.Option(
            ATTESTATION_FLAG,
            help="With --paste: attest lawful access without a prompt. Required where none can be shown.",
        ),
    ] = False,
    title: Annotated[
        str | None, typer.Option("--title", help="With --paste: the article's title, as you state it.")
    ] = None,
    authors: Annotated[
        list[str] | None,
        typer.Option("--author", help="With --paste: an author's name; repeat it for each, in order."),
    ] = None,
    published_on: Annotated[
        str | None,
        typer.Option(
            "--date",
            help="With --paste: the date the article was published, YYYY, YYYY-MM or YYYY-MM-DD.",
        ),
    ] = None,
    publication: Annotated[
        str | None,
        typer.Option("--publication", help="With --paste: the publication, journal or outlet."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Retrieve an article or open-access PDF into a hashed snapshot, or report why it cannot be used.

    Prints the canonical URL, title, identifiers, access status with its reason, and the snapshot's
    id, hashes, paragraph count and extractor version. With --paste, stores text you lawfully have
    as USER_SUPPLIED after you attest lawful access; nothing is fetched. --title, --author, --date and
    --publication state the copy's cite, stored unverified; a new copy holds only the fields stated.

    Exit codes:
    0  ACCESSIBLE and stored, or pasted text stored as USER_SUPPLIED
    1  refused, nothing stored: not a source URL, or pasted text not attested or rejected
    2  usage error, for example --paste without --source-url, or a --date not YYYY, YYYY-MM or YYYY-MM-DD
    3  PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND, UNSUPPORTED_TYPE or ERROR; no snapshot stored
    """
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    _check_arguments(url, refresh=refresh, paste=paste, source_url=source_url, lawful_access=lawful_access)
    stated = _stated_cite(
        paste, title=title, authors=authors, published_on=published_on, publication=publication
    )
    if paste is None or source_url is None:
        report = _run(_retrieve(cli.services.article_fetch(), str(url), refresh=refresh))
    else:
        attested = lawful_access or _attest_by_prompt(cli, paste, source_url)
        try:
            report = _run(
                _ingest(
                    cli.services.article_fetch(), source_url, paste.read(), attested=attested, stated=stated
                )
            )
        except UserTextNotAttested as refused:
            _end(cli, ctx, CommandFailure.from_exception(refused, hint=_attestation_hint(cli, paste)))

    payload: dict[str, JsonValue] = report.model_dump(mode="json")
    # Pasted text is stored whatever status its user reports; a retrieval stores only an ACCESSIBLE page.
    if paste is None and report.access_status is not AccessStatus.ACCESSIBLE:
        _end(cli, ctx, _not_accessible(report, payload))
    cli.output.success(command_name(ctx), payload, display=_table(report))


def stdin_is_a_terminal() -> bool:
    """Whether the attestation can be asked for: a terminal on standard input. Tests replace this."""
    return sys.stdin.isatty()


# ------------------------------------------------------------------------------------------------
# Arguments and the attestation
# ------------------------------------------------------------------------------------------------


def _check_arguments(
    url: str | None,
    *,
    refresh: bool,
    paste: typer.FileText | None,
    source_url: str | None,
    lawful_access: bool,
) -> None:
    """Refuse, as a usage error, a command line that asks for a fetch and a paste at once, or neither."""
    if paste is None:
        if url is None:
            raise typer.BadParameter(
                "give the URL to retrieve, or --paste with --source-url", param_hint="URL"
            )
        if source_url is not None or lawful_access:
            raise typer.BadParameter(
                f"--source-url and {ATTESTATION_FLAG} go with --paste", param_hint="--source-url"
            )
        return
    if url is not None:
        raise typer.BadParameter(
            "--paste stores text for --source-url and fetches nothing; give the URL as --source-url",
            param_hint="URL",
        )
    if source_url is None:
        raise typer.BadParameter(
            "--paste needs --source-url, the article the text is from", param_hint="--source-url"
        )
    if refresh:
        raise typer.BadParameter(
            "--paste fetches nothing, so there is nothing to refresh", param_hint="--refresh"
        )


def _stated_cite(
    paste: typer.FileText | None,
    *,
    title: str | None,
    authors: list[str] | None,
    published_on: str | None,
    publication: str | None,
) -> Citation | None:
    """The cite fields stated with --paste, unverified; a usage error without --paste or for a bad value."""
    if paste is None:
        stated = (
            ("--title", title),
            ("--author", authors),
            ("--date", published_on),
            ("--publication", publication),
        )
        given = [option for option, value in stated if value is not None and value != []]
        if given:
            raise typer.BadParameter(f"{', '.join(given)} go with --paste", param_hint=given[0])
        return None
    try:
        return stated_citation(
            title=title, authors=authors or (), publication=publication, published_on=published_on
        )
    except InvalidStatedCite as refused:
        raise typer.BadParameter(refused.detail, param_hint=CITE_OPTIONS[refused.field]) from refused


def _can_prompt(cli: CliContext, paste: typer.FileText) -> bool:
    """A person can answer: not `--json`, a terminal on stdin, and the text not read from stdin."""
    return not cli.output.is_json and paste.name != "<stdin>" and stdin_is_a_terminal()


def _attest_by_prompt(cli: CliContext, paste: typer.FileText, source_url: str) -> bool:
    """The answer to the attestation prompt; False, without asking, when no one can answer it."""
    if not _can_prompt(cli, paste):
        return False
    return typer.confirm(ATTESTATION_PROMPT.format(url=source_url), default=False, err=True)


def _attestation_hint(cli: CliContext, paste: typer.FileText) -> str:
    if _can_prompt(cli, paste):
        return "Nothing was stored. Answer yes at the prompt only if you have lawful access to the text."
    return (
        f"Nothing was stored. No prompt can be shown here; pass {ATTESTATION_FLAG} if you have lawful access."
    )


async def _retrieve(fetcher: ArticleFetch, url: str, *, refresh: bool) -> FetchReport:
    async with fetcher:
        return await fetcher.retrieve(url, refresh=refresh)


async def _ingest(
    fetcher: ArticleFetch, source_url: str, text: str, *, attested: bool, stated: Citation | None
) -> FetchReport:
    async with fetcher:
        return await fetcher.ingest_pasted(
            source_url=source_url, text=text, attested=attested, stated_citation=stated
        )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    """Report ``failure`` and end the run with its exit code."""
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _not_accessible(report: FetchReport, payload: dict[str, JsonValue]) -> CommandFailure:
    evidence = report.evidence
    marker = evidence.marker.marker_id if evidence is not None and evidence.marker is not None else None
    return CommandFailure(
        code=SOURCE_NOT_ACCESSIBLE_CODE,
        message=f"{report.access_status.value}: {report.reason}",
        exit_code=ExitCode.RETRIEVAL_FAILURE,
        details=payload,
        hint="No snapshot was stored, so nothing can be cut from this source. Paywalls are never bypassed; "
        "if you can read it lawfully, store your copy with "
        f"--paste FILE --source-url {quote(report.requested_url)} "
        f"and cut it with: debate-research cut {quote(report.requested_url)} --from-paste",
        panel_details={
            "access_status": report.access_status.value,
            "canonical_url": report.canonical_url,
            "status_code": evidence.status_code if evidence is not None else None,
            "marker": marker,
            "rules_version": report.rules_version,
        },
    )


def _table(report: FetchReport) -> TableSpec:
    identifiers = ", ".join(f"{name}: {value}" for name, value in report.identifiers if value is not None)
    rows = [
        ("Canonical URL", report.canonical_url),
        ("Title", report.title),
        ("Identifiers", identifiers or "none"),
        ("Access status", report.access_status.value),
        ("Reason", report.reason),
        ("Provenance", report.provenance_mode.value if report.provenance_mode is not None else "none"),
    ]
    snapshot = report.snapshot
    if snapshot is not None:
        rows += [
            ("Snapshot", snapshot.snapshot_id + (" (already stored)" if snapshot.reused else "")),
            ("SHA-256 (raw bytes)", snapshot.sha256),
            ("SHA-256 (normalized text)", snapshot.normalized_text_hash),
            ("Paragraphs", str(snapshot.paragraph_count)),
            ("Extractor", snapshot.extractor_version),
            ("Normalizer", snapshot.normalizer_version),
        ]
    if snapshot is not None and snapshot.provenance_mode is ProvenanceMode.USER_SUPPLIED:
        rows += _stated_rows(snapshot.stated_cite)
    shown = (
        report.provenance_mode
        if report.provenance_mode is ProvenanceMode.USER_SUPPLIED
        else report.access_status
    )
    return TableSpec(title=f"{shown.value} {report.canonical_url}", columns=("Field", "Value"), rows=rows)


def _stated_rows(stated: StatedCite | None) -> list[tuple[str, str]]:
    """The cite fields stored with a pasted copy, each one, so a field not stated shows as such."""
    if stated is None:
        return [("Stated cite", "none")]
    return [
        ("Stated authors", "; ".join(stated.authors) or NOT_STATED),
        ("Stated title", stated.title or NOT_STATED),
        ("Stated date", stated.published_at or NOT_STATED),
        ("Stated publication", stated.publication or NOT_STATED),
    ]


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion: a CLI command is the one caller with no event loop of its own."""
    return asyncio.run(awaitable)

"""`debate-research search "<query>"`: ask every discovery provider at once, and say which ones answered.

The deciding is `debate_core`'s (`v1-e08-t05`):
:class:`~debate_core.application.federated_search.FederatedSearchService` expands the query by argument
and need (v1-e08-t04), asks every enabled provider every query under one deadline (t01), merges what
they return into distinct sources (t02), ranks them by explainable features (t03), matches each to an
Article without fetching it, and stores the search. What is here is the command-line surface: the
options, the request, and the exit code each outcome ends with (architecture proposal §11). The table,
the JSON and the provider status footer are :mod:`debate_cli.presenters.search_presenter`'s.

Search returns sources, not cards: nothing it prints or stores is evidence text, and no snippet or
abstract is printed. A result's access is `UNKNOWN` until `fetch` or `cut` reads it.

## Exit codes

From :mod:`debate_cli.exit_codes` (:func:`~debate_cli.exit_codes.exit_code_for_search`):

* `0`: every provider answered in full, and there are results.
* `1`: no provider was asked, because none of those selected is enabled in `providers.enabled`.
* `2`: the command line was wrong: an unknown `--argument`, `--need`, `--topic` or `--var` (the
  message lists the valid ones), `--since` after `--until`, a provider this build does not have,
  or `--need` without `--argument`. Nothing is searched.
* `3`: no provider answered: each failed, timed out, was rate-limited or had its breaker open.
* `6`: partial: results from the providers that answered, and the footer names each one that did
  not, with its reason.
* `7`: every provider answered, and nothing matched.

## `--format json`

The same as `--json`, after the command or before it. One object on stdout: the search under `data` on
exit 0, and under `error.details` on 6, 7 and 3, as `cut` carries its card on exit 4
(:func:`~debate_cli.presenters.search_presenter.search_payload`). Progress and the expansion's warning
are on stderr.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Coroutine
from datetime import UTC, datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError

from debate_cli.container import FederatedSearching
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode, exit_code_for_search
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode
from debate_cli.presenters.search_presenter import (
    SearchProgress,
    footer_lines,
    outcome_failure,
    results_table,
    search_payload,
)
from debate_core.application.federated_search_types import ExpansionRequest, SearchOutcome, SearchRequest
from debate_core.application.settings import SearchProviderName
from debate_core.domain import SearchFilters

__all__ = ["OutputFormat", "search"]

DATE_FORMAT = "%Y-%m-%d"


class OutputFormat(StrEnum):
    """What `--format` chooses between: a table for a person, or one JSON object for a program."""

    TABLE = "table"
    JSON = "json"


def search(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help='What to search for, e.g. "health insurance".')],
    since: Annotated[
        datetime | None,
        typer.Option("--since", formats=[DATE_FORMAT], help="Only sources published on or after this date."),
    ] = None,
    until: Annotated[
        datetime | None,
        typer.Option("--until", formats=[DATE_FORMAT], help="Only sources published on or before this date."),
    ] = None,
    max_results: Annotated[
        int, typer.Option("--max-results", min=1, max=200, help="The most results to show, 1 to 200.")
    ] = 20,
    argument: Annotated[
        str | None,
        typer.Option(
            "--argument", help="Expand the query for a debate argument, e.g. politics-da (needs --need)."
        ),
    ] = None,
    need: Annotated[
        str | None,
        typer.Option(
            "--need",
            help="The part of the argument to find, from its family's needs: e.g. link for a DA, "
            "framework-good for a framework, solvency for a counterplan, alternative for a kritik.",
        ),
    ] = None,
    topic: Annotated[
        str | None,
        typer.Option(
            "--topic", help="A topic preset whose values fill the expansion, e.g. policy-2026-27-nhi."
        ),
    ] = None,
    variables: Annotated[
        list[str] | None,
        typer.Option(
            "--var",
            metavar="NAME=VALUE",
            help="A value for the expansion's templates, e.g. bill=... or impact=war. Repeatable.",
        ),
    ] = None,
    providers: Annotated[
        str | None,
        typer.Option(
            "--providers",
            help="Ask only these providers, comma-separated, e.g. openalex,rss. Default: every enabled one.",
        ),
    ] = None,
    expand_llm: Annotated[
        bool,
        typer.Option(
            "--expand-llm",
            help="Also ask a model for a few extra queries. Off unless given; replayed unless "
            "DEBATE_MODEL_MODE is live or record.",
        ),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", case_sensitive=False, help="table for people, json for programs."),
    ] = OutputFormat.TABLE,
    save: Annotated[
        Path | None,
        typer.Option(
            "--save",
            dir_okay=False,
            writable=True,
            help="Also write the results, as the JSON output's search object, to this file.",
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="The same as --format json: one JSON object on stdout.")
    ] = False,
) -> None:
    """Search every enabled discovery provider at once, and rank what they find with the reasons why.

    Prints each source's rank, title, publisher or venue, date, source type, access and a short
    explanation, then one line per provider saying whether it answered. Nothing is fetched and no card
    is cut: use fetch or cut on a result's URL. With --argument and --need the query is expanded into
    the taxonomy's queries for that argument and need. Every search is stored with its results.

    Exit codes:
    0  complete: every provider answered, with results
    1  no provider was asked: none of those selected is enabled
    2  usage error, for example an unknown --argument (the valid ones are listed) or --since after --until
    3  no provider answered: each failed, timed out or was skipped
    6  partial: results from the providers that answered; the footer names each one that did not
    7  every provider answered, and nothing matched
    """
    cli = cli_context(ctx)
    if (json_output or output_format is OutputFormat.JSON) and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    request = SearchRequest(
        query=query,
        filters=_filters(since, until, max_results),
        providers=_providers(providers),
        expansion=_expansion(argument, need, topic, variables or [], expand_llm),
    )
    if save is not None and not save.parent.is_dir():
        raise typer.BadParameter(f"{save.parent} is not a directory", param_hint="--save")
    progress = SearchProgress(cli.output, command_name(ctx))
    progress.searching(query, request.providers)
    outcome = _run(_search(cli.services.federated_search(model_expansion=expand_llm), request))
    progress.searched(outcome)
    expansion = outcome.search.expansion
    if expansion is not None and expansion.warning is not None:
        cli.output.note(f"Warning: {expansion.warning}")
    payload = search_payload(outcome)
    exit_code = exit_code_for_search(outcome)
    if save is not None and exit_code in (ExitCode.OK, ExitCode.SEARCH_PARTIAL):
        _write_json(save, payload)
    if exit_code is ExitCode.OK:
        cli.output.success(command_name(ctx), payload, display=results_table(outcome))
        return
    if exit_code is ExitCode.SEARCH_PARTIAL and not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=results_table(outcome))
    elif not cli.output.is_json:
        # No rows to show, but the footer still says what each provider did.
        cli.output.note("\n".join(footer_lines(outcome)))
    _end(cli, ctx, outcome_failure(outcome, payload, exit_code))


# ------------------------------------------------------------------------------------------------
# The request
# ------------------------------------------------------------------------------------------------


def _filters(since: datetime | None, until: datetime | None, max_results: int) -> SearchFilters:
    """The date window, from the start of `--since`'s day to the end of `--until`'s, in UTC."""
    start = datetime.combine(since.date(), time.min, tzinfo=UTC) if since is not None else None
    end = datetime.combine(until.date(), time.max, tzinfo=UTC) if until is not None else None
    if start is not None and end is not None and start > end:
        raise typer.BadParameter(
            f"--since {start.date().isoformat()} is after --until {end.date().isoformat()}",
            param_hint="--since",
        )
    return SearchFilters(since=start, until=end, max_results=max_results)


def _providers(value: str | None) -> tuple[str, ...] | None:
    """The providers `--providers` names, each one this build knows, or a usage error listing them."""
    if value is None:
        return None
    names = tuple(name.strip() for name in value.split(",") if name.strip())
    known = [provider.value for provider in SearchProviderName]
    unknown = [name for name in names if name not in known]
    if not names or unknown:
        raise typer.BadParameter(
            f"no provider named {', '.join(map(repr, unknown)) or 'there'}; "
            f"the providers are {', '.join(known)}",
            param_hint="--providers",
        )
    return names


def _expansion(
    argument: str | None, need: str | None, topic: str | None, variables: list[str], use_model: bool
) -> ExpansionRequest | None:
    """`--argument` and `--need` with what goes with them, or None; a usage error for half of a pair.

    Whether the taxonomy has the argument, need, topic and variables is the expansion stage's to say,
    before any provider is asked: it raises the `UnknownExpansionChoice` that exits 2 with the choices.
    """
    if argument is None or need is None:
        given = [flag for flag, value in (("--topic", topic), ("--var", variables or None)) if value]
        if use_model:
            given.append("--expand-llm")
        if argument is not None:
            raise typer.BadParameter(
                "--argument needs --need, the part of the argument to find", param_hint="--need"
            )
        if need is not None:
            raise typer.BadParameter(
                "--need needs --argument, the argument it is part of", param_hint="--argument"
            )
        if given:
            raise typer.BadParameter(
                f"{' and '.join(given)} expand a query for --argument and --need; give both",
                param_hint="--argument",
            )
        return None
    values: dict[str, str] = {}
    for item in variables:
        name, separator, value = item.partition("=")
        if not separator or not name.strip() or not value.strip():
            raise typer.BadParameter(f"{item!r} is not NAME=VALUE, e.g. bill=...", param_hint="--var")
        values[name.strip()] = value.strip()
    try:
        return ExpansionRequest(
            argument=argument, need=need, topic_id=topic, variables=values, use_model=use_model
        )
    except ValidationError as invalid:
        raise typer.BadParameter(
            invalid.errors()[0]["msg"].removeprefix("Value error, "), param_hint="--var"
        ) from None


async def _search(searching: FederatedSearching, request: SearchRequest) -> SearchOutcome:
    """Run the search, closing every provider when it ends, however it ends."""
    async with searching:
        return await searching.service.search(request)


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    """Write `payload` in one step: a file beside it, renamed into place, so no half-written file is left."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)
            stream.write("\n")
        Path(temporary).replace(path)
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

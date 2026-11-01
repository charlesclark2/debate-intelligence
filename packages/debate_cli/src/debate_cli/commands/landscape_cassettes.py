"""`debate-research landscape cassettes`: one caselist's model cassettes on this machine, counted and deleted.

::

    debate-research landscape cassettes --caselist hsld26
    debate-research landscape cassettes --caselist hsld26 --json
    debate-research landscape cassettes --caselist hsld26 --delete --confirm <code>

Every decision is :mod:`~debate_core.application.cassette_filing`'s (`v1-e32-t31`): which caselists a
cassette names, and what deleting one caselist's cassettes does to each. This is the guards and the
rendering (`v1-e32-t34`).

## Which directory

The landscape model stage's: `<data dir>/landscape/model-cassettes/`, where `<data dir>` is
`DEBATE_ENV`'s `storage.data_dir`. The container hands this command and the model stage the same
directory (:meth:`~debate_cli.container.ServiceContainer.landscape_cassettes`). The stage runs only from
a checkout, since it reads `prompts/`; this command needs no prompt, and run from that checkout (as the
annual purge runs it) or from an installed build it reads the same directory for the same environment.
Until the stage has recorded something there is no directory: the command says so, counts zero, and
creates nothing.

## A dry run, then a confirmation

Without `--delete` nothing changes. The command counts the caselist's cassettes by what a delete would
do to each, and prints a confirmation code:

* **sole**: only this caselist names it. A delete removes it.
* **shared**: another caselist names it too. A delete keeps it, taking only this caselist's name off,
  since the other caselist still replays it.
* **unattributed**: it names no caselist, because it was recorded before `v1-e32-t31`. No caselist's
  delete removes it; the count goes to the PM.
* **other caselists only**: untouched.

`--delete --confirm <code>` lists again and acts only if that listing's code is the one given: the code
is a digest of every cassette the delete would change, so a cassette recorded since the dry run, or a
code another caselist's dry run printed, is refused, exit `1`, `CONFIRMATION_MISMATCH`. In
prod, `--delete` also needs `--confirm-prod`. This is `caselist retire`'s pattern (and `tub index
prune`'s), with `--delete` for its `--execute`.

## What it prints

Counts, the caselist's slug, the environment, the directory as `<data dir>/landscape/model-cassettes/`
and the code. Never a cassette's content: a cassette holds the model's inputs, which may quote a card.
Never a cassette's name, a path, a school or a team code. A file in the directory that does not read as
a cassette stops the command before anything changes, exit `1`, `CASSETTE_UNREADABLE`, without naming
it: a misfiled file's name could be anything. A `--caselist` that is not a slug is refused, exit `2`,
without being repeated.
"""

from __future__ import annotations

from typing import Annotated, Final, NoReturn

import typer

from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode
from debate_core.application.cassette_filing import (
    CaselistCassettes,
    CassetteDeleteRefused,
    caselist_cassettes,
    delete_caselist_cassettes,
    is_caselist_slug,
)
from debate_core.application.errors import DomainError, error_code_of
from debate_core.application.settings import Environment

__all__ = ["DIRECTORY_SHOWN", "cassettes", "cassettes_summary"]

DIRECTORY_SHOWN: Final = "<data dir>/landscape/model-cassettes/"
"""The directory as the output names it: where it is in every data directory, never this machine's path."""


def cassettes(
    ctx: typer.Context,
    caselist: Annotated[str, typer.Option("--caselist", help="Caselist slug, e.g. hsld26.")],
    delete: Annotated[
        bool,
        typer.Option(
            "--delete",
            help="Delete the cassettes this caselist alone names, given the dry run's code with --confirm. "
            "Shared and unattributed cassettes are kept.",
        ),
    ] = False,
    confirmation: Annotated[
        str | None, typer.Option("--confirm", help="The confirmation code the dry run printed.")
    ] = None,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required to delete with DEBATE_ENV=prod.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Count a caselist's landscape model cassettes on this machine and, with confirmation, delete its own."""
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    environment = cli.services.settings.environment
    if not is_caselist_slug(caselist):
        _end(cli, ctx, _not_a_slug())
    if delete and environment is Environment.PROD and not confirm_prod:
        _end(cli, ctx, _prod_unconfirmed())
    files = cli.services.landscape_cassettes()
    found = files.root.is_dir()
    try:
        listed = (
            delete_caselist_cassettes(files, caselist, confirmation=confirmation)
            if delete
            else caselist_cassettes(files, caselist)
        )
    except CassetteDeleteRefused as refused:
        _end(cli, ctx, _mismatch(refused, environment))
    except DomainError as error:
        _end(cli, ctx, _unreadable(caselist, error))
    cli.output.success(
        command_name(ctx),
        cassettes_summary(listed, environment, found=found, deleted=delete),
        display=_display(listed, environment, found=found, deleted=delete),
    )


def cassettes_summary(
    listed: CaselistCassettes, environment: Environment, *, found: bool, deleted: bool
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`: counts, never a cassette's name."""
    return {
        "caselist": listed.caselist,
        "environment": environment.value,
        "directory": DIRECTORY_SHOWN,
        "directory_found": found,
        "deleted": deleted,
        "cassettes": _counts(listed),
        "confirmation": None if deleted else listed.confirmation,
    }


def _counts(listed: CaselistCassettes) -> dict[str, JsonValue]:
    return {
        "sole": len(listed.sole),
        "shared": len(listed.shared),
        "unattributed": len(listed.unattributed),
        "other_caselists": listed.others,
    }


# ------------------------------------------------------------------------------------------------
# Refusals: nothing was changed
# ------------------------------------------------------------------------------------------------


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _not_a_slug() -> CommandFailure:
    return CommandFailure(
        code="NOT_A_CASELIST_SLUG",
        message="--caselist takes a caselist's slug, such as hsld26: lower-case letters, then two digits",
        exit_code=ExitCode.USAGE_ERROR,
        hint="Nothing was read or changed.",
    )


def _prod_unconfirmed() -> CommandFailure:
    return CommandFailure(
        code="CONFIRMATION_REQUIRED",
        message=f"refusing to delete production's model cassettes without {CONFIRM_PROD_FLAG}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"environment": Environment.PROD.value},
        hint=f"Run it without --delete first and read the counts, then add {CONFIRM_PROD_FLAG}.",
    )


def _mismatch(refused: CassetteDeleteRefused, environment: Environment) -> CommandFailure:
    return CommandFailure(
        code="CONFIRMATION_MISMATCH",
        message=str(refused),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={
            "caselist": refused.listed.caselist,
            "environment": environment.value,
            "cassettes": _counts(refused.listed),
        },
        hint="Run it without --delete, read the counts, and pass the code it prints with --confirm.",
    )


def _unreadable(caselist: str, error: DomainError) -> CommandFailure:
    """A cassette file that does not read, told by its error's code: the error's text names the file."""
    return CommandFailure(
        code="CASSETTE_UNREADABLE",
        message=(
            f"a file in {DIRECTORY_SHOWN} does not read as a model cassette, so the cassettes of {caselist} "
            "cannot be counted; nothing was changed"
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"caselist": caselist, "cause_code": error_code_of(error)},
        hint="Tell the PM. The file is not named here, since a misfiled file's name could be anything.",
    )


# ------------------------------------------------------------------------------------------------
# Rendering: counts only
# ------------------------------------------------------------------------------------------------


def _display(listed: CaselistCassettes, environment: Environment, *, found: bool, deleted: bool) -> str:
    env = environment.value
    if not found:
        return (
            f"No model cassettes in {env}: the landscape model stage has recorded none on this machine "
            f"(no {DIRECTORY_SHOWN} directory).\n" + ("Deleted nothing." if deleted else "Nothing to delete.")
        )
    lines = [
        f"Model cassettes of {listed.caselist} in {env}, in the landscape model stage's directory, "
        f"{DIRECTORY_SHOWN}:"
    ]
    if deleted:
        lines += [
            f"  Deleted {len(listed.sole)} cassette(s) only this caselist named.",
            f"  Kept {len(listed.shared)} shared cassette(s), taking only this caselist's name off: another "
            "caselist still replays them.",
            f"  Kept {len(listed.unattributed)} unattributed cassette(s): it names no caselist, so no "
            "caselist's delete removes it. Send the PM the count.",
        ]
    else:
        lines += [
            f"  {len(listed.sole)} this caselist's alone: a delete removes them.",
            f"  {len(listed.shared)} shared with another caselist: kept, losing only this caselist's name, "
            "since another caselist still replays them.",
            f"  {len(listed.unattributed)} unattributed, naming no caselist (recorded before v1-e32-t31): "
            "kept, since no caselist's delete removes one. Send the PM the count.",
        ]
    lines.append(f"  {listed.others} of other caselists only: untouched.")
    if not deleted:
        lines.append(
            f"Dry run: nothing was changed. To carry it out, add: --delete --confirm {listed.confirmation}"
            if listed.sole or listed.shared
            else "Dry run: nothing was changed, and a delete would change nothing."
        )
    return "\n".join(lines)

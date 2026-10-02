"""`debate-research verify <manifest.json>`: is every card in a manifest reproducible from its snapshot?

The deciding is :class:`~debate_core.application.verify_manifest.VerifyManifest`'s, in `debate_core`:
reading the manifest, checking it against its published schema, and handing each card to the
evidence verifier, which cuts the evidence again from the stored snapshot and compares it exactly.
What is here is the command-line surface: one argument, a table for a person or one JSON object for
a program, and which exit code each outcome ends with (architecture proposal §11, `v1-e03-t06`).

Snapshots are read from this environment's data directory (`storage.data_dir`, chosen by
`DEBATE_ENV` or `DEBATE_STORAGE__DATA_DIR`). Nothing is fetched: a card whose snapshot is not on this
machine is UNVERIFIED with `SNAPSHOT_MISSING`, never skipped and never assumed.

## Exit codes

From :mod:`debate_cli.exit_codes`, and each one means exactly one thing here:

* `0`: every card is VERIFIED.
* `1`: the manifest was read and at least one card is UNVERIFIED. Every card is still reported.
* `2`: the command line was wrong, or the file is not a card manifest: not JSON, or not valid
  against `card_manifest.v1.json`. The failing JSON path is reported and nothing is verified.
* `3`: verification could not run, for example because a store could not be read. No card has a
  verdict, so this is never reported as `0` or `1`.

A card that passes the manifest schema but is not a valid card (ADR-0018's length invariant is the
example a schema cannot express) is one UNVERIFIED row with `CARD_INVALID`; it does not turn the
whole run into a `2`, because one tampered card must not hide the verdict on the others.

## `--json`

One object on stdout, described by `packages/debate_core/schemas/verify_result.v1.json`: the report
under `data` on exit 0, the same report under `error.details` on exit 1, and the failure with its
details otherwise. Like every reason detail it is built from, it never contains evidence text.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Annotated, Any, NoReturn

import typer

from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, TableSpec
from debate_core.application.verify_manifest import (
    INVALID_MANIFEST_CODE,
    UNVERIFIED_CODE,
    VERIFICATION_COULD_NOT_RUN_CODE,
    InvalidManifest,
    ManifestVerificationReport,
    VerificationCouldNotRun,
)

__all__ = ["verify"]


def verify(
    ctx: typer.Context,
    manifest: Annotated[
        typer.FileBinaryRead,
        typer.Argument(help="The JSON card manifest to verify; - reads it from stdin."),
    ],
) -> None:
    """Verify every card in a JSON card manifest against the snapshots on this machine.

    Each card's evidence is cut again from its stored snapshot and compared exactly.
    Snapshots are read from this environment's data directory and never fetched.

    Exit codes:
    0  every card is VERIFIED
    1  at least one card is UNVERIFIED (every card is still listed)
    2  usage error, or a manifest that fails its JSON Schema (the failing JSON path is reported)
    3  verification could not run, for example a store could not be read
    """
    cli = cli_context(ctx)
    try:
        report = _run(cli.services.verify_manifest().verify(manifest.read()))
    except InvalidManifest as invalid:
        _end(cli, ctx, _invalid_manifest(invalid, manifest.name))
    except VerificationCouldNotRun as stopped:
        _end(cli, ctx, _could_not_run(stopped))

    payload = report.model_dump(mode="json")
    for verdict in report.cards:
        for reason in verdict.reasons:
            cli.output.detail(f"{verdict.card_id} {reason.code.value}: {reason.detail}")
    if report.all_verified:
        cli.output.success(command_name(ctx), payload, display=_table(report))
        return
    # The failure envelope, so that `status`, `error.code` and the exit code agree for a program;
    # the whole report rides in `error.details`. A person gets the table, then a panel with the
    # counts: the report is already on the screen.
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_table(report))
        payload = {"total": report.total, "verified": report.verified, "unverified": report.unverified}
    _end(cli, ctx, _unverified(report, payload))


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    """Report ``failure`` and end the run with its exit code."""
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _unverified(report: ManifestVerificationReport, payload: dict[str, Any]) -> CommandFailure:
    return CommandFailure(
        code=UNVERIFIED_CODE,
        message=f"{report.unverified} of {report.total} card(s) could not be verified against their snapshot",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint="Re-run with --verbose for each reason's detail. An UNVERIFIED card is never finished evidence.",
    )


def _invalid_manifest(invalid: InvalidManifest, source: str) -> CommandFailure:
    return CommandFailure(
        code=INVALID_MANIFEST_CODE,
        message=str(invalid),
        exit_code=ExitCode.USAGE_ERROR,
        details={
            "json_path": invalid.json_path,
            "problem": invalid.problem,
            "violations": invalid.violations,
            "manifest": source,
        },
        hint="Nothing was verified. The schema is packages/debate_core/schemas/card_manifest.v1.json.",
    )


def _could_not_run(stopped: VerificationCouldNotRun) -> CommandFailure:
    return CommandFailure(
        code=VERIFICATION_COULD_NOT_RUN_CODE,
        message=str(stopped),
        exit_code=ExitCode.RETRIEVAL_FAILURE,
        details={
            "card_id": stopped.card_id,
            "position": stopped.position,
            "cause": type(stopped.cause).__name__,
        },
        hint=stopped.hint or "No card has a verdict. Run the command again once the store can be read.",
    )


def _table(report: ManifestVerificationReport) -> TableSpec:
    return TableSpec(
        title=f"{report.verified} of {report.total} card(s) verified",
        columns=("Card", "Tag", "Status", "Reasons"),
        rows=[
            (
                verdict.card_id,
                verdict.tag,
                verdict.status.value,
                "\n".join(
                    reason.code.value
                    if reason.first_differing_offset is None
                    else f"{reason.code.value} at offset {reason.first_differing_offset}"
                    for reason in verdict.reasons
                ),
            )
            for verdict in report.cards
        ],
    )


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion: a CLI command is the one caller with no event loop of its own."""
    return asyncio.run(awaitable)

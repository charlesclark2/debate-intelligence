"""`debate-research verify <manifest.json | evidence.docx>`: is every card reproducible from its snapshot?

The deciding is :class:`~debate_core.application.verify_manifest.VerifyManifest`'s, in `debate_core`:
reading the manifest, checking it against its published schema, and handing each card to the
evidence verifier, which cuts the evidence again from the stored snapshot and compares it exactly.
What is here is the command-line surface: one argument, a table for a person or one JSON object for
a program, and which exit code each outcome ends with (architecture proposal §11, `v1-e03-t06`).

A .docx the platform exported is read too (`v1-e06-t07`): the use case finds the manifest embedded in
it, verifies its cards the same way, and then checks that the document body still shows each card's
evidence, allowing only the edits the edit policy allows. A card whose quoted words were changed is
UNVERIFIED with `MANUAL_EDIT` and the character range; a bracketed interpolation is a warning
(`INTERPOLATION_PRESENT`) on a card that stays VERIFIED. A card in the body that the manifest does
not list, such as one pasted in by hand, is a row of its own, UNVERIFIED with
`BODY_CARD_NOT_IN_MANIFEST`. The file is only ever read.

Snapshots are read from this environment's data directory (`storage.data_dir`, chosen by
`DEBATE_ENV` or `DEBATE_STORAGE__DATA_DIR`). Nothing is fetched: a card whose snapshot is not on this
machine is UNVERIFIED with `SNAPSHOT_MISSING`, never skipped and never assumed.

## Exit codes

From :mod:`debate_cli.exit_codes`, and each one means exactly one thing here:

* `0`: every card is VERIFIED.
* `1`: the manifest was read and at least one card is UNVERIFIED, a .docx's `MANUAL_EDIT` among
  them, or a .docx's body holds a card its manifest does not list (`BODY_CARD_NOT_IN_MANIFEST`).
  Every card is still reported.
* `2`: the command line was wrong, or the file is not a card manifest this build reads: not JSON,
  not valid against `card_manifest.v1.json`, or written by a newer build (`NewerManifestVersion`,
  whose hint says to install a newer build). The failing JSON path is reported and nothing is
  verified. A .docx with no embedded manifest is a `2` under its own code, `NO_MANIFEST`: verify
  reads only files debate-research exported, and hand-cut team files are not checked.
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
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_cli.panel_summaries import by_count, every_value_in_full
from debate_core.application.verify_manifest import (
    INVALID_MANIFEST_CODE,
    NO_MANIFEST_CODE,
    UNVERIFIED_CODE,
    VERIFICATION_COULD_NOT_RUN_CODE,
    CardVerdict,
    InvalidManifest,
    ManifestVerificationReport,
    NewerManifestVersion,
    NoManifest,
    ReportedReason,
    UnclaimedBodyCardVerdict,
    VerificationCouldNotRun,
)
from debate_core.domain import VerificationStatus

__all__ = ["verify"]


def verify(
    ctx: typer.Context,
    manifest: Annotated[
        typer.FileBinaryRead,
        typer.Argument(
            help="The JSON card manifest, or a .docx debate-research exported, to verify; - reads stdin."
        ),
    ],
) -> None:
    """Verify every card in a JSON card manifest, or an exported .docx, against the snapshots on this machine.

    Each card's evidence is cut again from its stored snapshot and compared exactly.
    In a .docx, the body must still show each card's evidence: deleting whole words and
    changing markup are allowed, a bracketed interpolation is a warning, and any other
    change is MANUAL_EDIT. A card in the body that the manifest does not list is
    UNVERIFIED with BODY_CARD_NOT_IN_MANIFEST. Snapshots are read from this environment's
    data directory and never fetched, and the file is never written.

    Exit codes:
    0  every card is VERIFIED
    1  at least one card is UNVERIFIED (every card is still listed);
       BODY_CARD_NOT_IN_MANIFEST for a card in a .docx body that its manifest does not list
    2  usage error, a manifest that fails its JSON Schema, or one from a newer build (its JSON path is shown);
       NO_MANIFEST for a .docx with no embedded manifest
    3  verification could not run, for example a store could not be read
    """
    cli = cli_context(ctx)
    try:
        report = _run(cli.services.verify_manifest().verify(manifest.read()))
    except InvalidManifest as invalid:
        _end(cli, ctx, _invalid_manifest(invalid, manifest.name))
    except NoManifest as missing:
        _end(cli, ctx, _no_manifest(missing, manifest.name))
    except VerificationCouldNotRun as stopped:
        _end(cli, ctx, _could_not_run(stopped))

    payload = report.model_dump(mode="json")
    for verdict in report.cards:
        for reason in verdict.reasons:
            cli.output.detail(f"{verdict.card_id} {reason.code.value}: {reason.detail}")
        for warning in verdict.warnings:
            cli.output.detail(f"{verdict.card_id} {warning.code.value} (warning): {warning.detail}")
    for unclaimed in report.unclaimed_body_card_verdicts:
        for reason in unclaimed.reasons:
            cli.output.detail(f"{_body_card(unclaimed)} {reason.code.value}: {reason.detail}")
    if report.all_verified:
        cli.output.success(command_name(ctx), payload, display=_table(report))
        return
    # The failure envelope, so that `status`, `error.code` and the exit code agree for a program;
    # the whole report rides in `error.details`. A person gets the table, then a panel with the
    # counts: the report is already on the screen.
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_table(report))
    _end(cli, ctx, _unverified(report, payload))


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    """Report ``failure`` and end the run with its exit code."""
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _unverified(report: ManifestVerificationReport, payload: dict[str, Any]) -> CommandFailure:
    """`UNVERIFIED`, with the whole report in the details and its counts in the panel (`v1-e30-t27`)."""
    return CommandFailure(
        code=UNVERIFIED_CODE,
        message=f"{report.unverified} of {report.total} card(s) could not be verified against their snapshot",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint="Re-run with --verbose for each reason's detail. An UNVERIFIED card is never finished evidence.",
        panel_details=_unverified_panel(report),
    )


def _unverified_panel(report: ManifestVerificationReport) -> dict[str, JsonValue]:
    """The cards by count, the reasons by code, and one line per snapshot an unverified card names."""
    unverified = [verdict for verdict in report.cards if verdict.status is not VerificationStatus.VERIFIED]
    unclaimed = report.unclaimed_body_card_verdicts
    in_the_body_only = f", {len(unclaimed)} in the body only" if unclaimed else ""
    panel: dict[str, JsonValue] = {
        "cards": (
            f"{len(report.cards)} in the manifest{in_the_body_only}, {report.verified} verified, "
            f"{report.unverified} unverified"
        ),
        "reasons": by_count(
            code.value for verdict in (*unverified, *unclaimed) for code in verdict.reason_codes
        ),
    }
    by_snapshot: dict[str | None, list[CardVerdict]] = {}
    for verdict in unverified:
        by_snapshot.setdefault(verdict.snapshot_id, []).append(verdict)
    for snapshot, cards in by_snapshot.items():
        codes = ", ".join(dict.fromkeys(code.value for verdict in cards for code in verdict.reason_codes))
        named = "no snapshot named" if snapshot is None else f"snapshot {snapshot}"
        panel[named] = f"{len(cards)} card(s) unverified ({codes})"
    if unclaimed:
        panel["not in the manifest"] = ", ".join(_body_card(verdict) for verdict in unclaimed)
    return every_value_in_full(panel)


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
        hint=_invalid_manifest_hint(invalid),
        # The file's path is the one the command was given, which can be under a home directory: the
        # envelope keeps it, the panel does not (`v1-e30-t27`).
        panel_details=every_value_in_full(
            {"json_path": invalid.json_path, "problem": invalid.problem, "violations": invalid.violations}
        ),
    )


def _invalid_manifest_hint(invalid: InvalidManifest) -> str:
    """Where to look next: a newer build for a manifest one wrote, the schema for any other refusal."""
    if isinstance(invalid, NewerManifestVersion):
        return (
            "Nothing was verified. A newer build of debate-research wrote this manifest; install a newer "
            "build to verify it."
        )
    return "Nothing was verified. The schema is packages/debate_core/schemas/card_manifest.v1.json."


def _no_manifest(missing: NoManifest, source: str) -> CommandFailure:
    return CommandFailure(
        code=NO_MANIFEST_CODE,
        message=str(missing),
        exit_code=ExitCode.USAGE_ERROR,
        details={"document": source},
        hint=(
            "Nothing was verified. verify reads only .docx files debate-research exported, which carry "
            "their manifest; checking hand-cut team files is not supported yet."
        ),
        panel_details={},
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
    """A row per card: its id with its snapshot's beneath, its tag, its status, its reasons and warnings.

    A snapshot id is as wide as a card id, so the second line costs the table no width. A body card the
    manifest does not list follows the manifest's cards, named by its place in the body.
    """
    return TableSpec(
        title=f"{report.verified} of {report.total} card(s) verified",
        columns=("Card / snapshot", "Tag", "Status", "Reasons"),
        rows=[
            (
                verdict.card_id
                if verdict.snapshot_id is None
                else f"{verdict.card_id}\n{verdict.snapshot_id}",
                verdict.tag,
                verdict.status.value,
                "\n".join(
                    [_reason_cell(reason) for reason in verdict.reasons]
                    + [
                        f"{warning.code.value} (warning) at offset {warning.evidence_offset}"
                        if warning.evidence_offset is not None
                        else f"{warning.code.value} (warning)"
                        for warning in verdict.warnings
                    ]
                ),
            )
            for verdict in report.cards
        ]
        + [
            (_body_card(unclaimed), unclaimed.tag, unclaimed.status.value, "\n".join(unclaimed.reason_codes))
            for unclaimed in report.unclaimed_body_card_verdicts
        ],
        lines_below=_document_lines(report),
    )


def _body_card(unclaimed: UnclaimedBodyCardVerdict) -> str:
    """How a person names a body card: counted from 1, as Word's reader would count them."""
    return f"body card {unclaimed.body_position + 1}"


def _reason_cell(reason: ReportedReason) -> str:
    if reason.first_differing_offset is not None:
        return f"{reason.code.value} at offset {reason.first_differing_offset}"
    if reason.evidence_range is not None:
        return f"{reason.code.value} at {reason.evidence_range.start}-{reason.evidence_range.end}"
    return reason.code.value


def _document_lines(report: ManifestVerificationReport) -> list[str]:
    """For a .docx: which profile its body was read in, and how many body cards the manifest does not list."""
    document = report.document
    if document is None:
        return []
    lines = [f"Document body read in the {document.format_profile} format profile."]
    unclaimed = document.unclaimed_body_cards
    if unclaimed:
        positions = ", ".join(str(position + 1) for position in unclaimed)
        lines.append(
            f"{len(unclaimed)} card(s) in the body are not in its manifest (body card {positions}); "
            "they are UNVERIFIED."
        )
    return lines


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion: a CLI command is the one caller with no event loop of its own."""
    return asyncio.run(awaitable)

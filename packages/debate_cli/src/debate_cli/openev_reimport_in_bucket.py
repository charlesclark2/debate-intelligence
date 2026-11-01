"""`caselist reimport-openev-metadata` in bucket mode: on the bucket's copy of the run's state (`v1-e40-t34`).

::

    DEBATE_ENV=dev debate-research caselist reimport-openev-metadata --year 2026 --event policy
    DEBATE_ENV=dev debate-research caselist reimport-openev-metadata --year 2026 --event policy --execute

In bucket mode (`caselist.run_state = "bucket"`, dev since the cutover) the command is a dry run unless
`--execute` is given: it restores the bucket's run state into this machine's working copy, as
`caselist remove`'s dry run does, re-derives the release with nothing written, and prints what would
change. It takes no lock and writes nothing to the bucket. `--execute` holds the bucket's run lock from
the restore to the save of the run-state bundle, publishes the release manifest, and in prod needs
`--confirm-prod` as well. Both refuse inside the no-import window, Tuesday 06:00 to Thursday 00:00
America/Chicago, which holds every Wednesday. The rules are
:mod:`debate_core.application.caselist.openev_metadata_reimport_in_bucket`'s.

In local mode the command is as `v1-e30-t08` made it: it applies unless `--dry-run`, over this
machine's data directory, and `--execute` changes nothing.

## What is printed

Camps by name, with their counts before and after, and counts: titles, warnings, records. A camp is an
institution's public name. Never a title, a lab, a file's name or a path on this machine, in the text
or the JSON.
"""

from __future__ import annotations

import asyncio
from typing import NoReturn

import typer

from debate_cli.bucket_lock import terminated_on_sigterm
from debate_cli.context import CliContext, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist.camp_metadata import CampAliases
from debate_core.application.caselist.openev_metadata_reimport import OpenEvMetadataReimport
from debate_core.application.caselist.openev_metadata_reimport_in_bucket import BucketReimport
from debate_core.application.settings import Environment
from debate_core.domain.caselist import Event

__all__ = ["NEXT_STEP", "bucket_reimport_summary", "reimport_counts", "reimport_in_bucket"]

NEXT_STEP = (
    "The next cloud run's parse stage carries the camps to the occurrence rows, and its search index "
    "stage carries them to the cards; nothing more is run by hand."
)


def reimport_in_bucket(
    cli: CliContext,
    ctx: typer.Context,
    *,
    year: int,
    event: Event,
    aliases: CampAliases,
    execute: bool,
    confirm_prod: bool,
) -> None:
    """The command's bucket-mode form: refuse prod without the flag, then the dry run or the run."""
    settings = cli.services.settings
    if execute and settings.environment is Environment.PROD and not confirm_prod:
        _fail(
            cli,
            ctx,
            CommandFailure(
                code="CONFIRMATION_REQUIRED",
                message=(
                    f"refusing to change production's run state without {CONFIRM_PROD_FLAG}: "
                    f"{settings.storage.s3.bucket}"
                ),
                exit_code=ExitCode.DOMAIN_FAILURE,
                details={"environment": settings.environment.value},
                hint=(
                    f"Run it without --execute first and read the counts, then add --execute "
                    f"{CONFIRM_PROD_FLAG}."
                ),
            ),
        )
    service = cli.services.openev_metadata_reimport_in_bucket()
    cli.output.detail(f"restoring the run state from {settings.storage.s3.bucket} first")
    if execute:
        with terminated_on_sigterm():
            outcome = asyncio.run(service.execute(year=year, event=event, aliases=aliases))
    else:
        outcome = asyncio.run(service.dry_run(year=year, event=event, aliases=aliases))
    cli.output.detail(outcome.restored.sentence)
    data = bucket_reimport_summary(outcome, environment=settings.environment.value, confirm_prod=confirm_prod)
    if not outcome.succeeded:
        _fail(
            cli,
            ctx,
            CommandFailure(
                code="OPENEV_REIMPORT_INCOMPLETE",
                message=(
                    f"the re-import of openev {outcome.reimport.release} did not finish: "
                    f"{_incomplete(outcome)}"
                ),
                exit_code=ExitCode.DOMAIN_FAILURE,
                details=data,
                hint="Run the same command again: it restores the bucket's run state and re-derives again.",
            ),
        )
    cli.output.success(command_name(ctx), data, display=_table(outcome, data))


def reimport_counts(report: OpenEvMetadataReimport) -> dict[str, JsonValue]:
    """The counts and camps of a re-import, either form's. No path, title or lab."""
    return {
        "release": report.release,
        "year": report.year,
        "event": str(report.event),
        "applied": report.applied,
        "manifest_key": report.manifest_key,
        "rows": report.rows,
        "rows_changed": report.rows_changed,
        "titles_changed": report.titles_changed,
        "warnings_changed": report.warnings_changed,
        "camps_before": dict(report.camps_before),
        "camps_after": dict(report.camps_after),
        "unknown_before": report.unknown_before,
        "unknown_after": report.unknown_after,
        "camp_files_updated": report.camp_files_updated,
        "camp_files_missing": report.camp_files_missing,
        "blobs_missing": report.blobs_missing,
        "identities_added": report.identities_added,
        "manifest_changed": report.manifest_changed,
    }


def bucket_reimport_summary(
    outcome: BucketReimport, *, environment: str, confirm_prod: bool = False
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` in bucket mode: the counts, then what reached the bucket."""
    published = outcome.published
    return {
        **reimport_counts(outcome.reimport),
        "bucket_mode": True,
        "environment": environment,
        "restored_state_files": len(outcome.restored.state_files),
        "manifest_published": (
            str(published.snapshots[0].manifest) if published is not None and published.snapshots else None
        ),
        "bundle_saved": outcome.bundle is not None and outcome.bundle.saved,
        "bundle": outcome.bundle.reason if outcome.bundle is not None else None,
        "execute_command": None if outcome.executed else _execute_command(outcome, environment, confirm_prod),
        "next_step": NEXT_STEP if outcome.executed and outcome.changes_anything else None,
    }


def _execute_command(outcome: BucketReimport, environment: str, confirm_prod: bool) -> str | None:
    if not outcome.changes_anything:
        return None
    report = outcome.reimport
    prod = f" {CONFIRM_PROD_FLAG}" if environment == Environment.PROD.value or confirm_prod else ""
    return (
        f"DEBATE_ENV={environment} debate-research caselist reimport-openev-metadata --year {report.year} "
        f"--event {str(report.event).lower()} --execute{prod}"
    )


def _incomplete(outcome: BucketReimport) -> str:
    published = outcome.published
    if published is not None and not published.succeeded:
        codes = ", ".join(published.failure_codes) or "the manifest was withheld"
        return f"the release's publish did not complete ({codes}), so the run-state bundle was not saved"
    if outcome.bundle is not None:
        return f"the manifest was published and the run-state bundle was {outcome.bundle.reason}"
    return "the run-state bundle was not saved"  # pragma: no cover - a failed outcome has one of the above


def _table(outcome: BucketReimport, data: dict[str, JsonValue]) -> TableSpec:
    """One row per camp, before and after, then what was done or would be."""
    report = outcome.reimport
    camps = sorted(set(report.camps_before) | set(report.camps_after))
    rows = [
        [camp, str(report.camps_before.get(camp, 0)), str(report.camps_after.get(camp, 0))] for camp in camps
    ]
    record_verb = "corrected" if outcome.executed else "to correct"
    counts = (
        f"{report.rows} file(s), {report.rows_changed} changed: {report.titles_changed} title(s) and "
        f"{report.warnings_changed} warning(s) changed, {report.camp_files_updated} camp-file record(s) "
        f"{record_verb}, {report.identities_added} row(s) given their upstream identity. "
        f"{report.blobs_missing} not held in this working copy, which fetches no file."
    )
    return TableSpec(
        columns=("Camp", "Files before", "Files after"),
        rows=rows,
        title=(
            f"openev {report.release} metadata, {data['environment']}'s run state "
            f"({'re-derived' if outcome.executed else 'dry run'})"
        ),
        caption=f"{counts} {_outcome_sentence(outcome, data)}",
    )


def _outcome_sentence(outcome: BucketReimport, data: dict[str, JsonValue]) -> str:
    if not outcome.executed:
        said = (
            "DRY RUN: the bucket's run state was restored into this machine's working copy; nothing was "
            "written to the bucket and the run lock was not taken."
        )
        command = data["execute_command"]
        return f"{said} To carry it out: {command}" if command else f"{said} Nothing would change."
    if not outcome.changes_anything:
        return "The release's metadata was already right: nothing was published or saved."
    return (
        f"Published the release's manifest ({data['manifest_published']}) and saved the run-state "
        f"bundle. {NEXT_STEP}"
    )


def _fail(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)

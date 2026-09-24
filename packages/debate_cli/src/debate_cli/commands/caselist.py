"""`debate-research caselist import | import-openev | publish | status`: archives in, the bucket out.

`import` turns one downloaded archive into the local evidence store (`v1-e30-t03`), and
`import-openev` does the same for OpenEv camp files (`v1-e30-t04`). `publish` puts what was
imported into the environment's evidence bucket and `status` says whether the two agree
(`v1-e30-t05`); each is described under its own heading below, after `import`.

Every decision about what an archive member *is* — new, carried forward, revised, a duplicate,
taken down, suppressed — belongs to
:class:`~debate_core.application.caselist.import_service.CaselistImportService` in `debate_core`.
What is here is the part that is genuinely a command-line surface: which flags mean what, which
event a caselist slug implies, where the manifest lands, and how a summary is rendered for a
person and for a program.

::

    debate-research caselist import ~/Downloads/hsld26-0915.zip \\
        --caselist hsld26 --snapshot 2026-09-15

    debate-research caselist import ~/Downloads/hsld26-0915 --caselist hsld26 \\
        --snapshot 2026-09-15 --dry-run          # classify everything, write nothing
    debate-research --json caselist import ...   # one JSON object for a scheduled consumer

## The archive is a zip or a directory

Both are read the same way and both produce the same relative paths, so it makes no difference to
what gets stored which one the operator happens to have
(:func:`debate_core.integrations.local.archive_reader.read_archive`).

## Which event

`--event` says which sides the caselist debates, and it decides whether `Aff` or `Pro` is a legal
side on a disclosure. It is inferred from the slug for the caselists that exist
(:data:`EVENTS_BY_SLUG_PREFIX`), because typing `--event LD` after `--caselist hsld26` every week
is a way to eventually type the wrong one. A slug this build does not recognise is a refusal that
names the flag, not a guess.

## Nothing is written under `--dry-run`

No blob, no record, no snapshot row and no manifest. It is the rehearsal an operator does first
on a week that looks odd, and the counts it prints are the counts a real run would produce.

## Exit codes

From :mod:`debate_cli.exit_codes`, and no new numbers. `0` when the import ran. `1` for the
deterministic refusals an operator has to act on: an archive over the size ceiling, an unreadable
path, a slug whose event cannot be inferred, or an archive older than one already imported
without `--allow-out-of-order`. All four arrive as
:class:`~debate_core.application.errors.DomainError`s and are rendered by the root group.

## `caselist import-openev`

::

    debate-research caselist import-openev ~/Downloads/openev-policy-2026.zip \\
        --year 2026 --event policy
    debate-research caselist import-openev ~/Downloads/camp-files --year 2026 --event policy \\
        --dry-run --camp-aliases ~/camp_aliases.yaml

Every decision — which camp, which title, new or duplicate, what the release manifest becomes —
is :class:`~debate_core.application.caselist.openev_import_service.OpenEvImportService`'s. This
command reads the release's existing manifest (`manifests/openev/<year>-<event>.jsonl`) so the
import merges into it, and writes the merged one back unless `--dry-run`. `--snapshot` is the date
the import is recorded under, today by default; `--camp-aliases` replaces the packaged alias
table. A camp nobody listed is not a failure: the file is imported with camp `UNKNOWN` and the
count is in the summary. Exit codes are `import`'s.

## `caselist publish`

::

    debate-research caselist publish --caselist hsld26                  # every local snapshot, dev
    debate-research caselist publish --caselist hsld26 --snapshot 2026-09-15 --dry-run
    DEBATE_ENV=prod debate-research caselist publish --caselist hsld26 --confirm-prod

Every decision — what to upload, what to skip, when a manifest may be written — is
:class:`~debate_core.application.caselist.publish_service.CaselistPublishService`'s. Unlike
`store sync`, this command **applies by default**: it moves exactly the sources a manifest names,
never overwrites a content-addressed key, and writes each manifest only once all of its sources are
confirmed, so there is nothing destructive for a plan-first default to protect against. `--dry-run`
plans and uploads nothing. Writing to prod still needs `--confirm-prod`.

`DEBATE_ENV` chooses the bucket and nothing else does, exactly as for `store`; `test` names no
bucket and is refused.

Exit codes: `0` when every requested snapshot is complete in the bucket; `1` when any is not —
with the failed sha256 values in the message and every count in `error.details` — or when a guard
refused to start. An expired SSO session ends the run at once, before any further manifest, and is
reported with the `aws sso login --profile …` line the adapter built.

## `caselist status`

Compares this machine's snapshots with the bucket's
(:class:`~debate_core.application.caselist.status_service.CaselistStatusService`) and writes
nothing. `0` only when every snapshot agrees; `1` on any drift, with the per-snapshot report in
`error.details`. With no `--caselist` it compares every caselist either side holds a manifest for.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Final

import typer

from debate_cli.commands.store import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist.camp_metadata import load_camp_aliases
from debate_core.application.caselist.import_service import Classification, ImportReport
from debate_core.application.caselist.manifest import (
    manifest_key,
    read_manifest_lines,
    write_manifest,
    write_manifest_lines,
)
from debate_core.application.caselist.openev_import_service import OpenEvImportReport
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.publish_plan import SourceAction, validate_publish_target
from debate_core.application.caselist.publish_service import PublishReport, SourceResult
from debate_core.application.caselist.status_service import CaselistStatusReport, SnapshotStatus
from debate_core.application.settings import ConfigurationError, Environment, Settings
from debate_core.domain.caselist import Event
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.fs_object_store import FsEvidenceObjectStore

__all__ = [
    "EVENTS_BY_SLUG_PREFIX",
    "InvalidSnapshotDate",
    "UnknownCaselistEvent",
    "event_for_caselist",
    "import_archive",
    "import_openev",
    "import_summary",
    "openev_import_summary",
    "publish",
    "publish_summary",
    "status",
    "status_summary",
]

EVENTS_BY_SLUG_PREFIX: Final[dict[str, Event]] = {
    "hsld": Event.LD,
    "hspolicy": Event.POLICY,
    "hspf": Event.PF,
    "ndtceda": Event.POLICY,
    "nfald": Event.LD,
    # The synthetic caselist the test archives are built under (`tests/fixtures/caselist/`).
    # Named here rather than special-cased in a test so that the smoke check runs the same code
    # path an operator runs.
    "testcl": Event.LD,
}
"""Which event each published caselist slug debates, by the letters before its season year.

A table rather than a rule, because a slug is data (`CaselistSlug` is a validated string, not an
enum) and next season's slugs are rows somebody adds here. A slug that is not in it is a refusal
naming `--event`, never a guess: guessing wrong would file every disclosure in the archive under
a side the event does not debate.
"""


def event_for_caselist(caselist: str) -> Event | None:
    """The event a caselist slug implies, or `None` when this build does not know the slug."""
    prefix = caselist.rstrip("0123456789")
    return EVENTS_BY_SLUG_PREFIX.get(prefix)


def import_archive(
    ctx: typer.Context,
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            help="The weekly archive: a .zip straight from OpenCaselist, or a directory.",
        ),
    ],
    caselist: Annotated[
        str,
        typer.Option("--caselist", help="Caselist slug the archive was published for, e.g. hsld26."),
    ],
    snapshot: Annotated[
        str,
        typer.Option("--snapshot", help="The date the archive was published, as YYYY-MM-DD."),
    ],
    event: Annotated[
        Event | None,
        typer.Option("--event", help="Which event the caselist debates. Inferred from the slug."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Classify everything and write nothing at all."),
    ] = False,
    allow_out_of_order: Annotated[
        bool,
        typer.Option(
            "--allow-out-of-order",
            help="Import an archive older than one already imported for this caselist.",
        ),
    ] = False,
) -> None:
    """Import one weekly caselist archive, deduplicated against the ones already imported."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    published = _snapshot_date(snapshot)
    resolved_event = event or event_for_caselist(caselist)
    if resolved_event is None:
        raise UnknownCaselistEvent(caselist)

    service = cli.services.caselist_import()
    cli.output.detail(f"reading {source.name}")
    report = _run(
        service.import_archive(
            read_archive(
                source,
                max_archive_bytes=settings.caselist.max_archive_bytes,
                max_unpacked_bytes=settings.caselist.max_unpacked_bytes,
            ),
            caselist=caselist,
            snapshot=published,
            event=resolved_event,
            archive_sha256=archive_digest(source),
            allow_out_of_order=allow_out_of_order,
            dry_run=dry_run,
        )
    )

    manifest = None
    if not dry_run:
        objects = FsEvidenceObjectStore(settings.storage.data_dir)
        manifest = write_manifest(report, objects.path_for(manifest_key(caselist, published)))
        cli.output.detail(f"wrote {manifest.name}")

    cli.output.success(
        command_name(ctx),
        import_summary(report, manifest),
        display=_summary_table(report, manifest),
    )


def import_openev(
    ctx: typer.Context,
    source: Annotated[
        Path,
        typer.Argument(exists=True, help="The OpenEv camp files: a .zip, or a directory of them."),
    ],
    year: Annotated[
        int,
        typer.Option("--year", min=2000, max=9999, help="Topic year of the camp release, e.g. 2026."),
    ],
    event: Annotated[
        Event,
        typer.Option("--event", case_sensitive=False, help="Event the files were cut for: ld, policy or pf."),
    ],
    snapshot: Annotated[
        str | None,
        typer.Option("--snapshot", help="Date to record the import under, as YYYY-MM-DD. Default: today."),
    ] = None,
    camp_aliases: Annotated[
        Path | None,
        typer.Option(
            "--camp-aliases",
            exists=True,
            dir_okay=False,
            help="An alias table to use instead of the packaged camp_aliases.yaml.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Classify everything and write nothing at all."),
    ] = False,
) -> None:
    """Import OpenEv camp files, deduplicated against everything already imported."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    # UTC, because that is the calendar the domain's no-future-dates rule reads.
    imported_on = _snapshot_date(snapshot) if snapshot is not None else datetime.now(UTC).date()
    aliases = load_camp_aliases(camp_aliases)
    manifest_path = FsEvidenceObjectStore(settings.storage.data_dir).path_for(
        openev_manifest_key(year, event)
    )

    service = cli.services.openev_import()
    cli.output.detail(f"reading {source.name}")
    report = _run(
        service.import_release(
            read_archive(
                source,
                max_archive_bytes=settings.caselist.max_archive_bytes,
                max_unpacked_bytes=settings.caselist.max_unpacked_bytes,
            ),
            year=year,
            event=event,
            imported_on=imported_on,
            archive_sha256=archive_digest(source),
            recorded_manifest=read_manifest_lines(manifest_path),
            aliases=aliases,
            dry_run=dry_run,
        )
    )

    manifest = None
    if not dry_run:
        manifest = write_manifest_lines(report.manifest_lines, manifest_path)
        cli.output.detail(f"wrote {manifest.name}")

    cli.output.success(
        command_name(ctx),
        openev_import_summary(report, manifest),
        display=_openev_summary_table(report, manifest),
    )


def publish(
    ctx: typer.Context,
    caselist: Annotated[
        str,
        typer.Option("--caselist", help="Caselist slug to publish, e.g. hsld26, or openev for camp files."),
    ],
    snapshot: Annotated[
        str | None,
        typer.Option(
            "--snapshot",
            help="Publish only this snapshot: YYYY-MM-DD, or <year>-<event> for openev. Default: all.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List the planned uploads and upload nothing."),
    ] = False,
    confirm_prod: Annotated[
        bool,
        typer.Option(CONFIRM_PROD_FLAG, help="Required to write to the production evidence bucket."),
    ] = False,
) -> None:
    """Publish imported snapshots and their sources to this environment's evidence bucket."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    validate_publish_target(caselist, snapshot)
    _refuse(
        cli,
        ctx,
        _no_bucket(settings, writing=not dry_run)
        or _unconfirmed_production_write(settings, writing=not dry_run, confirmed=confirm_prod),
    )

    service = cli.services.caselist_publish()
    cli.output.detail(f"planning {caselist} against {settings.storage.s3.bucket}")
    plan = _run(service.plan(caselist, snapshot))
    if dry_run:
        report = PublishReport(plan=plan, applied=False)
    else:
        cli.output.detail(f"uploading {len(plan.uploads)} source(s)")
        report = _run(service.execute(plan))

    payload = publish_summary(report, settings)
    display = _publish_table(report, settings)
    if report.succeeded:
        cli.output.success(command_name(ctx), payload, display=display)
        return
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=display)
    cli.output.failure(_publish_failure(report, payload), command=command_name(ctx))
    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)


def status(
    ctx: typer.Context,
    caselist: Annotated[
        str | None,
        typer.Option("--caselist", help="Only this caselist. Default: every caselist either side holds."),
    ] = None,
    snapshot: Annotated[
        str | None,
        typer.Option("--snapshot", help="Only this snapshot of --caselist."),
    ] = None,
) -> None:
    """Compare local caselist snapshots with this environment's bucket; exit 0 only if they agree."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    if snapshot is not None and caselist is None:
        raise InvalidStatusRequest
    if caselist is not None:
        validate_publish_target(caselist, snapshot)
    _refuse(cli, ctx, _no_bucket(settings, writing=False))

    report = _run(cli.services.caselist_status().status(caselist, snapshot))
    payload = status_summary(report, settings)
    display = _status_table(report, settings)
    if report.in_sync:
        cli.output.success(command_name(ctx), payload, display=display)
        return
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=display)
    drifted = report.drifted
    cli.output.failure(
        CommandFailure(
            code="CASELIST_DRIFT",
            message=(
                f"{len(drifted)} snapshot(s) differ between this machine and the bucket: "
                + ", ".join(f"{entry.caselist} {entry.snapshot}" for entry in drifted)
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint="`caselist publish` completes what is missing here; a checksum mismatch needs a person.",
        ),
        command=command_name(ctx),
    )
    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)


class InvalidStatusRequest(ConfigurationError):
    """`--snapshot` was given without `--caselist`, which it is a snapshot of."""

    def __init__(self) -> None:
        super().__init__("--snapshot needs --caselist", field="--snapshot", source="cli")


# ------------------------------------------------------------------------------------------------
# Publish and status guards
# ------------------------------------------------------------------------------------------------


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    """Report `refusal` and end the run, or return so the command can continue.

    The same outcome-not-exception pattern as `store` (see :mod:`debate_cli.commands.store`).
    """
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


def _no_bucket(settings: Settings, *, writing: bool) -> CommandFailure | None:
    """A publish needs dev or prod; even a dry run or a status needs a bucket to read."""
    if writing and settings.environment not in SYNCABLE_ENVIRONMENTS:
        return CommandFailure(
            code="ENVIRONMENT_NOT_SYNCABLE",
            message=f"`caselist publish` writes to dev or prod, not {settings.environment.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev (or prod) and try again.",
        )
    if not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"the {settings.environment.value} environment names no evidence bucket",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV to dev or prod, or set storage.s3.bucket for this environment.",
        )
    return None


def _unconfirmed_production_write(
    settings: Settings, *, writing: bool, confirmed: bool
) -> CommandFailure | None:
    """Publishing to the production bucket needs `--confirm-prod`; a dry run writes nothing."""
    if not writing or settings.environment is not Environment.PROD or confirmed:
        return None
    return CommandFailure(
        code="CONFIRMATION_REQUIRED",
        message=(
            "refusing to publish to the production evidence bucket without "
            f"{CONFIRM_PROD_FLAG}: {settings.storage.s3.bucket}"
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"environment": settings.environment.value, "bucket": settings.storage.s3.bucket},
        hint=f"Run it with --dry-run first, then again with {CONFIRM_PROD_FLAG}.",
    )


# ------------------------------------------------------------------------------------------------
# Publish and status rendering
# ------------------------------------------------------------------------------------------------


def publish_summary(report: PublishReport, settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist publish`.

    For a program first — the scheduled sync (`v1-e34-t02`) reads it. `applied` says whether
    anything was uploaded; per snapshot, a dry run carries its `planned` action counts and an
    applied run its `results`; `failed_sha256` is the list a retry would be about. Digests and keys
    only: nothing from inside a manifest.
    """
    outcomes = report.snapshots if report.applied else (None,) * len(report.plan.snapshots)
    snapshots: list[JsonValue] = []
    for plan, outcome in zip(report.plan.snapshots, outcomes, strict=True):
        entry: dict[str, JsonValue] = {
            "snapshot": plan.snapshot,
            "manifest_key": plan.manifest_key,
            "planned": dict(plan.counts),
        }
        if outcome is None:
            entry["manifest"] = "blocked" if plan.blocked else plan.manifest_action.value
        else:
            entry["results"] = {result.value: len(outcome.of(result)) for result in SourceResult}
            entry["manifest"] = outcome.manifest.value
            entry["failed"] = [
                {"sha256": failure.sha256, "code": failure.error_code, "message": failure.error_message}
                for failure in outcome.failed
            ]
            entry["manifest_error"] = outcome.manifest_error
        snapshots.append(entry)
    return {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "caselist": report.plan.caselist,
        "applied": report.applied,
        "planned_uploads": len(report.plan.uploads),
        "bytes_to_upload": report.plan.bytes_to_upload,
        "counts": ({result.value: report.count(result) for result in SourceResult} if report.applied else {}),
        "snapshots": snapshots,
        "failed_sha256": list(report.failed_sha256),
    }


def status_summary(report: CaselistStatusReport, settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist status`: one object per snapshot."""
    return {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "in_sync": report.in_sync,
        "snapshots": [_status_entry(entry) for entry in report.snapshots],
    }


def _status_entry(entry: SnapshotStatus) -> dict[str, JsonValue]:
    return {
        "caselist": entry.caselist,
        "snapshot": entry.snapshot,
        "manifest_key": entry.manifest_key,
        "in_sync": entry.in_sync,
        "local_manifest": entry.local_manifest,
        "manifest_present": entry.manifest_present,
        "sources": entry.sources,
        "local_files": entry.local_files,
        "published_sources": entry.published_sources,
        "missing_sources": list(entry.missing_sources),
        "missing_local": list(entry.missing_local),
        "checksum_mismatches": list(entry.checksum_mismatches),
        "suppressed": entry.suppressed,
    }


def _publish_table(report: PublishReport, settings: Settings) -> TableSpec:
    title = f"{report.plan.caselist} -> {settings.storage.s3.bucket} ({settings.environment.value})"
    if not report.applied:
        rows = [
            [
                plan.snapshot,
                str(len(plan.of(SourceAction.UPLOAD))),
                str(len(plan.of(SourceAction.VERIFY, SourceAction.UPLOADED_EARLIER))),
                str(len(plan.blocked)),
                "blocked" if plan.blocked else plan.manifest_action.value,
            ]
            for plan in report.plan.snapshots
        ]
        return TableSpec(
            columns=("Snapshot", "Upload", "Present or earlier", "Blocked", "Manifest"),
            rows=rows,
            title=f"{title}, dry run",
            caption=(
                f"{len(report.plan.uploads)} upload(s) planned; nothing was uploaded. "
                "Re-run without --dry-run to publish."
            ),
        )
    rows = [
        [
            outcome.snapshot,
            str(len(outcome.of(SourceResult.UPLOADED))),
            str(len(outcome.of(SourceResult.SKIPPED))),
            str(len(outcome.failed)),
            outcome.manifest.value,
        ]
        for outcome in report.snapshots
    ]
    complete = sum(1 for outcome in report.snapshots if outcome.complete)
    return TableSpec(
        columns=("Snapshot", "Uploaded", "Skipped", "Failed", "Manifest"),
        rows=rows,
        title=title,
        caption=(
            f"{complete} of {len(report.snapshots)} snapshot(s) complete in the bucket; "
            f"{report.count(SourceResult.UPLOADED)} source(s) uploaded and verified."
        ),
    )


def _status_table(report: CaselistStatusReport, settings: Settings) -> TableSpec:
    rows = [
        [
            entry.caselist,
            entry.snapshot,
            f"{entry.local_files}/{entry.sources}" if entry.local_manifest else "no manifest",
            str(entry.published_sources),
            str(len(entry.missing_sources)),
            "yes" if entry.manifest_present else "no",
            str(len(entry.checksum_mismatches)),
            "yes" if entry.in_sync else "NO",
        ]
        for entry in report.snapshots
    ]
    drifted = len(report.drifted)
    return TableSpec(
        columns=(
            "Caselist",
            "Snapshot",
            "Local files",
            "Published",
            "Missing",
            "Manifest",
            "Mismatches",
            "In sync",
        ),
        rows=rows,
        title=f"{settings.storage.s3.bucket} ({settings.environment.value}) against this machine",
        caption=(
            "Every snapshot agrees."
            if not drifted
            else f"{drifted} snapshot(s) differ; see --json for digests."
        ),
    )


def _publish_failure(report: PublishReport, payload: dict[str, JsonValue]) -> CommandFailure:
    """What an incomplete publish exits `1` with: the failed digests, and every count in details."""
    failed = report.failed_sha256
    if not report.applied:
        return CommandFailure(
            code="PUBLISH_BLOCKED",
            message=(
                f"{len(failed)} source(s) cannot be published as planned (a checksum mismatch in the "
                f"bucket, or missing from this machine): {', '.join(failed)}"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint=(
                "Nothing was uploaded. A mismatch in the bucket needs a person; a missing file needs "
                "a re-import."
            ),
        )
    incomplete = [outcome for outcome in report.snapshots if not outcome.complete]
    withheld = ", ".join(f"{outcome.snapshot} ({outcome.manifest.value})" for outcome in incomplete)
    named = f"; failed sha256: {', '.join(failed)}" if failed else ""
    return CommandFailure(
        code="PUBLISH_INCOMPLETE",
        message=f"{len(incomplete)} snapshot(s) not complete in the bucket, manifest {withheld}{named}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint="Re-run the same command: every confirmed source is skipped and the manifests follow.",
    )


def _snapshot_date(value: str) -> date:
    """Parse `--snapshot` as a plain calendar date.

    Taken as a string and parsed here rather than declared as a `datetime` option, because a
    snapshot is the day an archive was published and an option typed as a datetime would accept
    `2026-09-15T06:00` and silently carry a time of day the source does not have.
    """
    try:
        return date.fromisoformat(value.strip())
    except ValueError as malformed:
        raise InvalidSnapshotDate(value) from malformed


class InvalidSnapshotDate(ConfigurationError):
    """`--snapshot` was not a calendar date. It names the archive's publication day."""

    def __init__(self, value: str) -> None:
        super().__init__(
            f"--snapshot must be a date as YYYY-MM-DD (the day the archive was published), not {value!r}",
            field="--snapshot",
            source="cli",
        )


class UnknownCaselistEvent(ConfigurationError):
    """The caselist slug is not one this build knows the event for, and `--event` was not given.

    A :class:`~debate_core.application.settings.ConfigurationError`, so the root group reports it
    as the deterministic failure it is: the operator supplies the flag and the same command works.
    """

    def __init__(self, caselist: str) -> None:
        known = ", ".join(sorted(EVENTS_BY_SLUG_PREFIX))
        super().__init__(
            f"this build does not know which event {caselist!r} debates, so it cannot tell a legal "
            f"side from an illegal one; pass --event, or add the slug prefix to the table in "
            f"debate_cli.commands.caselist (known prefixes: {known})",
            field="--event",
            source="cli",
        )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------


def import_summary(report: ImportReport, manifest: Path | None) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist import`.

    Written for a program first, because the scheduled weekly import (`v1-e34-t02`) reads it:
    every classification has a count whether or not it occurred, `applied` says whether anything
    was written, and `manifest` is the path or `null` rather than a sentence to parse.
    """
    return {
        "caselist": report.caselist,
        "snapshot": report.snapshot.isoformat(),
        "event": str(report.event),
        "previous_snapshot": (
            report.previous_snapshot.isoformat() if report.previous_snapshot is not None else None
        ),
        "applied": report.applied,
        "archive_sha256": report.archive_sha256,
        "members": report.member_count,
        "counts": {str(name): report.count(name) for name in Classification},
        "skipped": {str(reason): count for reason, count in sorted(report.skipped.items(), key=str)},
        "skipped_total": sum(report.skipped.values()),
        "distinct_sha256": report.distinct_digests,
        "newly_stored_blobs": report.newly_stored_blobs,
        "warnings": report.warning_count,
        "manifest": str(manifest) if manifest is not None else None,
    }


def openev_import_summary(report: OpenEvImportReport, manifest: Path | None) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist import-openev`.

    Shaped like `import`'s, for the same reader (`v1-e34-t02`): every classification counted
    whether or not it occurred, `applied`, and `manifest` as a path or `null`. `release` is what
    `caselist publish --caselist openev --snapshot` takes. `unknown_camps` is how many files need a
    line in the alias table; `caselist_duplicates` how many a team had already disclosed.
    """
    return {
        "release": report.release,
        "year": report.year,
        "event": str(report.event),
        "imported_on": report.imported_on.isoformat(),
        "applied": report.applied,
        "archive_sha256": report.archive_sha256,
        "members": report.member_count,
        "counts": {str(name): report.count(name) for name in Classification},
        "skipped": {str(reason): count for reason, count in sorted(report.skipped.items(), key=str)},
        "skipped_total": sum(report.skipped.values()),
        "distinct_sha256": report.distinct_digests,
        "newly_stored_blobs": report.newly_stored_blobs,
        "warnings": report.warning_count,
        "unknown_camps": report.unknown_camp_count,
        "caselist_duplicates": report.caselist_duplicate_count,
        "manifest_key": report.manifest_key,
        "manifest": str(manifest) if manifest is not None else None,
    }


def _openev_summary_table(report: OpenEvImportReport, manifest: Path | None) -> TableSpec:
    """One row per classification an OpenEv import can produce, then the skips."""
    rows = [
        [str(name), str(report.count(name))] for name in Classification if name is not Classification.REMOVED
    ]
    rows.append(["SKIPPED", str(sum(report.skipped.values()))])
    unknown = (
        f", {report.unknown_camp_count} with no camp in the alias table" if report.unknown_camp_count else ""
    )
    disclosed = (
        f", {report.caselist_duplicate_count} already disclosed on a caselist"
        if report.caselist_duplicate_count
        else ""
    )
    if not report.applied:
        outcome = "Planned only; nothing was written. Re-run without --dry-run to import it."
    else:
        written = manifest.name if manifest else "none"
        outcome = f"{report.newly_stored_blobs} new file(s) stored; manifest at {written}."
    return TableSpec(
        columns=("Classification", "Files"),
        rows=rows,
        title=f"openev {report.release} ({'dry run' if not report.applied else 'imported'})",
        caption=f"{report.member_count} member(s){unknown}{disclosed}. {outcome}",
    )


def _summary_table(report: ImportReport, manifest: Path | None) -> TableSpec:
    """One row per classification, then the skips: what an operator checks the week against."""
    rows = [[str(name), str(report.count(name))] for name in Classification]
    rows.append(["SKIPPED", str(sum(report.skipped.values()))])
    return TableSpec(
        columns=("Classification", "Files"),
        rows=rows,
        title=(
            f"{report.caselist} {report.snapshot.isoformat()} "
            f"({'dry run' if not report.applied else 'imported'})"
        ),
        caption=_caption(report, manifest),
    )


def _caption(report: ImportReport, manifest: Path | None) -> str:
    """What the numbers mean, in the one line under the table."""
    against = (
        f"against {report.previous_snapshot.isoformat()}"
        if report.previous_snapshot is not None
        else "the first archive for this caselist"
    )
    warned = f", {report.warning_count} filename(s) not fully read" if report.warning_count else ""
    if not report.applied:
        return (
            f"{report.member_count} member(s), {against}{warned}. Planned only; nothing was "
            "written. Re-run without --dry-run to import it."
        )
    return (
        f"{report.member_count} member(s), {against}{warned}. "
        f"{report.newly_stored_blobs} new file(s) stored; manifest at "
        f"{manifest.name if manifest else 'none'}."
    )


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion.

    The services are `async` because the API and the workers will await them; a CLI command is the
    one caller with no event loop of its own, so it starts one for the duration of the command.
    """
    return asyncio.run(awaitable)

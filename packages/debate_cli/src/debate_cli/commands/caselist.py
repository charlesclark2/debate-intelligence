"""`debate-research caselist import | import-openev | reimport-openev-metadata | publish | status`.

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
(:func:`debate_core.integrations.local.archive_reader.read_archive`, which the composition root
binds to this installation's size ceilings as :meth:`debate_cli.container.ServiceContainer.read_archive`).

## Which event

`--event` says which sides the caselist debates, and it decides whether `Aff` or `Pro` is a legal
side on a disclosure. It is inferred from the slug for the caselists that exist
(:data:`~debate_cli.caselist_events.EVENTS_BY_SLUG_PREFIX`), because typing `--event LD` after
`--caselist hsld26` every week is a way to eventually type the wrong one. A slug this build does
not recognise is a refusal that names the flag, not a guess.

## Nothing is written under `--dry-run`

No blob, no record, no snapshot row and no manifest. It is the rehearsal an operator does first
on a week that looks odd, and the counts it prints are the counts a real run would produce.

## A weekly imported late measures the later manifests again

After the manifest is written, every weekly manifest dated after it is measured again from the
store, and the newest complete archive dated after it has its withdrawals counted again
(:class:`~debate_core.application.caselist.later_manifests.LaterManifests`, `v1-e30-t18`). A week
imported in date order, or imported again, rewrites none. The summary lists what was rewritten
(`rewritten_manifests`, `complete_archive_recounted`), and `caselist publish` uploads each as a
changed manifest. `--allow-out-of-order` is needed only for a weekly older than one already imported
that has never been imported itself; a week already imported is imported again without it.

## Exit codes

From :mod:`debate_cli.exit_codes`, and no new numbers. `0` when the import ran. `1` for the
deterministic refusals an operator has to act on: an archive over the size ceiling, an unreadable
path, a slug whose event cannot be inferred, or a weekly older than one already imported and never
imported itself, without `--allow-out-of-order`. All four arrive as
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

## `caselist reimport-openev-metadata`

::

    debate-research caselist reimport-openev-metadata --year 2026 --event policy --dry-run
    debate-research caselist reimport-openev-metadata --year 2026 --event policy

Re-derives camp, lab, title and warnings for a release already imported, from the paths its
manifest recorded, with the current alias table, and gives each row its upstream identity
(`openev_id`, `upstream_path_sha256`) from this machine's OpenEv delivery record (`v1-e30-t14`)
(:meth:`~debate_core.application.caselist.openev_import_service.OpenEvImportService.reimport_metadata`,
`v1-e30-t08`). It reads the local manifest, corrects the camp-file records, and writes the manifest
back to the same key — only when it changed, and never under `--dry-run`. It downloads nothing and
never writes a blob, a digest or a key. The manifest's bytes change, so `caselist status` reports
the release as drifted until `caselist publish --caselist openev --snapshot <year>-<event>`
re-uploads it. Exit codes are `import`'s.

That is local mode. In bucket mode (dev since the cutover), the records are the cloud run's run-state
bundle, and the command works on the bucket's copy instead (`v1-e40-t34`,
:mod:`debate_cli.commands.caselist_reimport_in_bucket`): a dry run unless `--execute`, which holds the
bucket's run lock while it restores, re-derives, publishes the release manifest and saves the bundle.

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
refused to start; `3` when the store did not answer: an expired SSO session or a refused request,
which end the run at once, before any further manifest, or an applied run whose every failure was
the store being unavailable (`v1-e01-t20`). An expired session is reported with the
`aws sso login --profile …` line the adapter built, and a refused request with the adapter's hint
that the profile lacks a grant. A profile the AWS config does not define is neither: it exits `1`
as `STORE_PROFILE_NOT_CONFIGURED`, naming the setting to correct (`v1-e29-t07`).

## `caselist status`

Compares this machine's snapshots with the bucket's
(:class:`~debate_core.application.caselist.status_service.CaselistStatusService`) and writes
nothing. `0` only when every snapshot agrees; `1` on any drift, with the per-snapshot report in
`error.details`; `3` when the bucket could not be read. With no `--caselist` it compares every
caselist either side holds a manifest for.

A checksum mismatch is named by its kind (`v1-e30-t12`), in the message, the table and each
snapshot's `mismatches` in the JSON. A **manifest** mismatch is this machine's copy rewritten since
its last publish, by a camp metadata re-import or a removal, and the hint names
`caselist publish --caselist <slug>` for each caselist affected, complete archives included. A
**source** mismatch is other bytes under a digest's key, and the hint says it needs a person. A run
with both prints both. Each snapshot also shows its suppressed rows, and each caselist the current
objects of suppressed sources still in the bucket, which a removal should have taken: a run whose
only difference is such an object says that every snapshot agrees and what is left. The exit codes
are as above.

It also reports what a removal left in the bucket (`v1-e30-t10`): per caselist, the current objects,
noncurrent versions and delete markers still held under `raw/` and `parsed/` of files the
suppression list says were removed, later uploads taken down with them included. It lists object
versions with the everyday profile and nothing else: no delete, no download, and never the takedown
profile. Anything found is `1`, as `REMOVAL_RESIDUE` when every snapshot agrees, and the runbook says
what to run (`docs/runbooks/caselist-removal.md`). A file is named by the first twelve characters of
its sha256 and by counts, in the text and in `removal_residue` of the JSON alike. Where the profile
may not list versions the caselist is reported as *not checked*, with `null` counts: that is not a
finding of none, and it does not change the exit code.

It says when a removal is owed again (`v1-e30-t21`): a stored row at a path a removal holds, which a
build from before `v1-e30-t13` imported, and an upload at a held path in an archive in the download
inbox. Each is named by the first twelve characters of its sha256 and the request id of the removal
holding its path, with the hint to run that removal again; never by its path or the archive's name.
Neither is a difference from the bucket, so neither changes the exit code.

And, per caselist a completed removal touched, the manifest and aggregate versions older than it, by
key role and count (`v1-e30-t15`): versions of the parsed store's `index.jsonl`, `failures.jsonl` and
`occurrences.jsonl` in every version directory, and of each manifest the removal rewrote other than
its own rewrite. Found by comparing the listing's times with the removal log's, with the scope each
removal records beside its log entry; nothing is downloaded. A completed removal whose build recorded
no scope is named as not checked.

Three more things since `v1-e30-t19`. A manifest mismatch whose manifest the publisher withholds,
for a row a removal stops or holds, gets the hint to finish the removal first and not the publish
hint: status asks the publisher's own rule. A copy withdrawn from a caselist that keeps no holder of
it is named, if anything is left of it, by that caselist and the request the withdrawal record
gives, by digest prefix and count; and a withdrawal no record attributes, which an earlier build
made, by its request as not attributed. Neither of those two changed the exit code then.

Three since `v1-e30-t24`. The withdrawn copy left is residue, as a removed file's is: `1`, as
`REMOVAL_RESIDUE` when every snapshot agrees (the PM's ruling on t19's question 1). A withdrawal not
attributed still changes nothing: it says what was not looked at. An upload an import refused at a
held path, which the same removal run again has not yet listed, is named by caselist, digest prefix
and request, from the held-digest record, and its request is owed, whether or not the archive is
still in the inbox; that changes no exit code either. And the error panel no longer prints the whole
report it carries in `error.details`, which in prod on 2026-10-18 was about 1,000 lines of sha256:
it prints the counts, one line per snapshot that differs, with digests by prefix. `--json` keeps
every field.

One since `v1-e32-t13`. Per caselist a completed removal run's own scope names, the landscape
school-view files (`schools.csv`, `schools.md`) written before that run completed: in the bucket by a
plain listing of `reports/landscape/`, which the everyday profile may make (it lists no versions
there), and on this machine under `<data dir>/reports/landscape/`. They are residue, `1`, and the same
removal run again deletes them. A view written after the run, such as the newest bundle republished
without the removed rounds, is not counted. JSON gives them as `school_views` and
`school_views_older_than` beside `older_versions`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from debate_cli.bucket_lock import run_holding_the_bucket_lock
from debate_cli.caselist_events import EVENTS_BY_SLUG_PREFIX, event_for_caselist
from debate_cli.caselist_publish_refusals import no_bucket, refuse, unconfirmed_production_write
from debate_cli.commands.caselist_reimport_in_bucket import reimport_counts, reimport_in_bucket
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode, exit_code_for_failure_codes
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG
from debate_cli.options.snapshot_date import parse_snapshot_date
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_cli.panel_summaries import (
    by_count,
    digest_of_key,
    digest_prefix,
    every_value_in_full,
    some_prefixes,
)
from debate_cli.parses_owed import parses_owed
from debate_core.application.caselist.camp_metadata import load_camp_aliases
from debate_core.application.caselist.import_service import Classification, ImportReport
from debate_core.application.caselist.later_manifests import LaterManifestsRemeasured
from debate_core.application.caselist.manifest import (
    manifest_key,
    read_manifest_lines,
    write_manifest,
    write_manifest_lines,
)
from debate_core.application.caselist.openev_import_service import OpenEvImportReport
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.openev_metadata_reimport import OpenEvMetadataReimport
from debate_core.application.caselist.publish_plan import SnapshotPlan, SourceAction, validate_publish_target
from debate_core.application.caselist.publish_service import PublishReport, SnapshotOutcome, SourceResult
from debate_core.application.caselist.removal_residue import CaselistResidue
from debate_core.application.caselist.status_service import (
    CASELIST_DRIFT,
    REMOVAL_RESIDUE,
    CaselistStatusReport,
    SnapshotStatus,
)
from debate_core.application.caselist_sync import full_archive_of_inbox_name
from debate_core.application.errors import UNMODELLED_ERROR_CODE
from debate_core.application.settings import ConfigurationError, Settings
from debate_core.domain.caselist import Event

__all__ = [
    "UnknownCaselistEvent",
    "import_archive",
    "import_openev",
    "import_summary",
    "openev_import_summary",
    "openev_metadata_reimport_summary",
    "publish",
    "reimport_openev_metadata",
    "publish_summary",
    "status",
    "status_summary",
]


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
            help=(
                "Import a weekly older than one already imported for this caselist, and never imported "
                "itself. The later manifests are measured again with it."
            ),
        ),
    ] = False,
) -> None:
    """Import one weekly caselist archive, deduplicated against the ones already imported."""
    cli = cli_context(ctx)
    cli.services.settings  # noqa: B018 - loaded first, so a broken profile is reported before a bad flag
    if full_archive_of_inbox_name(source.name) is not None:
        raise CompleteArchiveNotImportedByHand(source.name)
    published = parse_snapshot_date(snapshot)
    resolved_event = event or event_for_caselist(caselist)
    if resolved_event is None:
        raise UnknownCaselistEvent(caselist)

    service = cli.services.caselist_import()
    cli.output.detail(f"reading {source.name}")
    report = _run(
        service.import_archive(
            cli.services.read_archive(source),
            caselist=caselist,
            snapshot=published,
            event=resolved_event,
            archive_sha256=cli.services.archive_digest(source),
            allow_out_of_order=allow_out_of_order,
            dry_run=dry_run,
        )
    )

    manifest = None
    remeasured = None
    if not dry_run:
        manifest = write_manifest(
            report, cli.services.evidence_object_path(manifest_key(caselist, published))
        )
        cli.output.detail(f"wrote {manifest.name}")
        remeasured = _run(cli.services.caselist_later_manifests().after_weekly_import(report))
        for snapshot in remeasured.rewritten:
            cli.output.detail(f"measured {caselist} {snapshot} again and rewrote its manifest")

    cli.output.success(
        command_name(ctx),
        import_summary(report, manifest, remeasured),
        display=_summary_table(report, manifest, remeasured),
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
    cli.services.settings  # noqa: B018 - loaded first, so a broken profile is reported before a bad flag
    # UTC, because that is the calendar the domain's no-future-dates rule reads.
    imported_on = parse_snapshot_date(snapshot) if snapshot is not None else datetime.now(UTC).date()
    aliases = load_camp_aliases(camp_aliases)
    manifest_path = cli.services.evidence_object_path(openev_manifest_key(year, event))

    service = cli.services.openev_import()
    cli.output.detail(f"reading {source.name}")
    report = _run(
        service.import_release(
            cli.services.read_archive(source),
            year=year,
            event=event,
            imported_on=imported_on,
            archive_sha256=cli.services.archive_digest(source),
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


def reimport_openev_metadata(
    ctx: typer.Context,
    year: Annotated[
        int,
        typer.Option("--year", min=2000, max=9999, help="Topic year of the camp release, e.g. 2026."),
    ],
    event: Annotated[
        Event,
        typer.Option("--event", case_sensitive=False, help="Event the files were cut for: ld, policy or pf."),
    ],
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
        typer.Option("--dry-run", help="Report what would change and write nothing at all."),
    ] = False,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="In bucket mode, carry it out. Without it, bucket mode is a dry run."),
    ] = False,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required with --execute in the production environment.")
    ] = False,
) -> None:
    """Re-derive camp and title for camp files already imported. Downloads nothing."""
    cli = cli_context(ctx)
    cli.services.settings  # noqa: B018 - loaded first, so a broken profile is reported before a bad flag
    if dry_run and execute:
        raise typer.BadParameter(
            "--dry-run and --execute ask for opposite things; pass one", param_hint="--execute"
        )
    aliases = load_camp_aliases(camp_aliases)
    if cli.services.bucket_write_guard().bucket_mode:
        reimport_in_bucket(
            cli, ctx, year=year, event=event, aliases=aliases, execute=execute, confirm_prod=confirm_prod
        )
        return
    manifest_path = cli.services.evidence_object_path(openev_manifest_key(year, event))

    report = _run(
        cli.services.openev_import().reimport_metadata(
            year=year,
            event=event,
            recorded_manifest=read_manifest_lines(manifest_path),
            aliases=aliases,
            dry_run=dry_run,
            upstream_paths=cli.services.openev_upstream_paths(),
        )
    )

    manifest = None
    if not dry_run and report.manifest_changed:
        manifest = write_manifest_lines(report.manifest_lines, manifest_path)
        cli.output.detail(f"wrote {manifest.name}")

    cli.output.success(
        command_name(ctx),
        openev_metadata_reimport_summary(report, manifest),
        display=_reimport_table(report, manifest),
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
    refuse(
        cli,
        ctx,
        no_bucket(settings, writing=not dry_run)
        or unconfirmed_production_write(settings, writing=not dry_run, confirmed=confirm_prod),
    )

    service = cli.services.caselist_publish()
    cli.output.detail(f"planning {caselist} against {settings.storage.s3.bucket}")
    plan = _run(service.plan(caselist, snapshot))
    if dry_run:
        report = PublishReport(plan=plan, applied=False)
    else:
        cli.output.detail(f"uploading {len(plan.uploads)} source(s)")
        report = run_holding_the_bucket_lock(cli, "caselist publish", lambda: service.execute(plan))

    payload = publish_summary(report, settings)
    display = _publish_table(report, settings)
    if report.succeeded:
        cli.output.success(command_name(ctx), payload, display=display)
        return
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=display)
    failure = _publish_failure(report, payload)
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


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
    refuse(cli, ctx, no_bucket(settings, writing=False))

    report = _run(cli.services.caselist_status().status(caselist, snapshot, residue=True, held_in_inbox=True))
    owed, owed_sentence = parses_owed(cli.services, remote=False)
    payload = {**status_summary(report, settings), "parses_owed": owed}
    display = _status_table(report, settings, owed_sentence=owed_sentence)
    if report.in_sync:
        cli.output.success(command_name(ctx), payload, display=display)
        return
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=display)
    cli.output.failure(_status_failure(report, payload), command=command_name(ctx))
    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)


def _status_failure(report: CaselistStatusReport, payload: dict[str, JsonValue]) -> CommandFailure:
    """What a status that is not clean reports: the snapshots that differ, or what a removal left.

    Snapshots that differ are `CASELIST_DRIFT`, with any residue in the details beside them. When
    every snapshot agrees and a version listing still shows a removed file, or a copy withdrawn
    from a caselist that keeps no holder of it (`v1-e30-t24`), the code is `REMOVAL_RESIDUE` and the
    message says what is left, by digest prefix and count.

    The details are the whole report, for `--json`; the panel prints :func:`_status_panel` in their
    place (`v1-e30-t24`).
    """
    drifted = report.drifted
    panel = _status_panel(report, payload)
    if report.residue_found and not drifted:
        return CommandFailure(
            code=REMOVAL_RESIDUE,
            message=f"{_residue_held(report)}: "
            + "; ".join(_residue_found(one, withdrawn=True) for one in report.residue if one.found),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint=(
                "A removal left them. Run that removal again, dry run first, then --execute: "
                'docs/runbooks/caselist-removal.md, "When caselist status reports removal residue".'
            ),
            panel_details=panel,
        )
    differ = (
        f"{len(drifted)} snapshot(s) differ between this machine and the bucket: "
        + ", ".join(_drifted_snapshot(entry) for entry in drifted)
        if drifted
        else "every snapshot agrees"
    )
    leftover = _suppressed_objects_found(report)
    return CommandFailure(
        code=CASELIST_DRIFT,
        message=differ if leftover is None else f"{differ}{'; and' if drifted else ', and'} {leftover}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint=" ".join(_drift_hints(report)),
        panel_details=panel,
    )


def _status_panel(report: CaselistStatusReport, payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """What a failing status's panel prints in place of its details, the whole report (`v1-e30-t24`).

    The environment and the bucket, how many snapshots were compared and differ, and one line per
    snapshot that differs, saying what differs by count with up to three digests by prefix. The
    table above it has already counted every snapshot, and `--json` holds every digest in full.
    """
    panel: dict[str, JsonValue] = {
        "environment": payload["environment"],
        "bucket": payload["bucket"],
        "snapshots": f"{len(report.snapshots)} compared, {len(report.drifted)} differ",
    }
    for entry in report.drifted:
        panel[f"{entry.caselist} {entry.snapshot}"] = _what_differs(entry)
    return every_value_in_full(panel, every="every digest")


def _what_differs(entry: SnapshotStatus) -> str:
    """One snapshot's differences, by count, each list of digests named by its first prefixes."""
    what: list[str] = []
    if not entry.local_manifest:
        what.append("no manifest on this machine")
    if not entry.manifest_present:
        what.append("no manifest in the bucket")
    if entry.manifest_mismatched:
        what.append("manifest mismatch")
    for counted, digests in (
        ("source(s) not in the bucket", entry.missing_sources),
        ("source(s) not on this machine", entry.missing_local),
        ("source mismatch(es)", tuple(digest_of_key(key) for key in entry.source_mismatches)),
        ("suppressed row(s)", entry.suppressed_rows),
    ):
        if digests:
            what.append(f"{len(digests)} {counted} {some_prefixes(digests)}")
    return ", ".join(what)


def _residue_held(report: CaselistStatusReport) -> str:
    """What a `REMOVAL_RESIDUE` message begins with: what kind of thing the bucket still holds."""
    files = sum(len(one.files) for one in report.residue)
    if files:
        return f"the bucket still holds versions of {files} removed file(s)"
    if any(one.older_versions for one in report.residue):
        return "the bucket still holds versions older than a removal"
    if any(one.school_views for one in report.residue):
        return "landscape school views older than a removal are still held"
    copies = sum(len(one.withdrawn_copies) for one in report.residue)
    return (
        f"the bucket still holds copies of {copies} file(s) withdrawn from a caselist that keeps no "
        "holder of them"
    )


def _drifted_snapshot(entry: SnapshotStatus) -> str:
    """`<caselist> <snapshot>`, and in brackets the mismatches and suppressed rows that differ."""
    what: list[str] = []
    if entry.manifest_mismatched:
        what.append("manifest mismatch")
    if entry.source_mismatches:
        what.append(f"{len(entry.source_mismatches)} source mismatch(es)")
    if entry.suppressed_rows:
        what.append(f"{len(entry.suppressed_rows)} suppressed row(s)")
    named = f"{entry.caselist} {entry.snapshot}"
    return f"{named} ({', '.join(what)})" if what else named


def _suppressed_objects_found(report: CaselistStatusReport) -> str | None:
    """`the bucket still holds N current object(s) of suppressed sources: <caselist> N, …`, or None."""
    if not report.suppressed_objects:
        return None
    counts = [
        f"{caselist} {len(found)}"
        for caselist in report.caselists
        if (found := report.suppressed_objects_of(caselist))
    ]
    return (
        f"the bucket still holds {len(report.suppressed_objects)} current object(s) of suppressed "
        f"sources: {', '.join(counts)}"
    )


def _drift_hints(report: CaselistStatusReport) -> list[str]:
    """One sentence per kind of difference found, each naming what clears it (`v1-e30-t12`).

    A manifest mismatch is this machine's rewrite not yet published, and the publish of each
    caselist affected uploads it, unless the publisher withholds that manifest for a row a removal
    stops or holds (`v1-e30-t19`): then the removal is finished first. Whether it does is the
    publisher's own rule, which status asked (:attr:`SnapshotStatus.manifest_withheld`). A source
    mismatch needs a person. What a removal left needs the removal finished. Anything missing is
    what a publish completes, as before.
    """
    drifted = report.drifted
    hints: list[str] = []
    if any(entry.incomplete for entry in drifted):
        hints.append("`caselist publish` completes what is missing here.")
    manifests = tuple(
        dict.fromkeys(entry.caselist for entry in report.manifest_mismatched if not entry.manifest_withheld)
    )
    if manifests:
        commands = " and ".join(f"`caselist publish --caselist {caselist}`" for caselist in manifests)
        hints.append(
            "A manifest mismatch is this machine's copy rewritten since its last publish, by a camp "
            f"metadata re-import or a removal. Run {commands} to upload it."
        )
    withheld = [entry for entry in report.manifest_mismatched if entry.manifest_withheld]
    if withheld:
        named = ", ".join(f"{entry.caselist} {entry.snapshot}" for entry in withheld)
        hints.append(
            f"A manifest mismatch in {named} is not cleared by a publish: the publisher withholds that "
            "manifest while it has a row a removal stops or holds. Finish the removal first: run it "
            "again, dry run first, then --execute, and publish after it "
            '(docs/runbooks/caselist-removal.md, "When caselist status reports removal residue").'
        )
    if report.source_mismatched:
        hints.append("A source mismatch needs a person: the bucket holds other bytes under a digest's key.")
    if report.suppressed_objects or any(entry.suppressed_rows for entry in drifted):
        hints.append(
            "A suppressed row or object is what a removal did not finish: "
            'docs/runbooks/caselist-removal.md, "When caselist status reports removal residue".'
        )
    if report.removals_owed:
        hints.append(_removals_owed(report))
    return hints


def _removals_owed(report: CaselistStatusReport) -> str:
    """The hint for a held row, a held upload in the inbox, one refused at import or a held upload's
    parsed file in the bucket (`v1-e31-t26`): which removals to run again, and how."""
    kinds = ["A held row", "a held upload in the inbox"]
    if report.refused_at_import:
        kinds.append("an upload an import refused at a held path")
    if report.held_parsed_objects:
        kinds.append("a held upload's parsed file in the bucket")
    held = f"{', '.join(kinds[:-1])} or {kinds[-1]}"
    return (
        f"{held} means {', '.join(report.removals_owed)} is owed again: "
        "run the same removal again, dry run first, then --execute "
        "(docs/runbooks/caselist-removal.md, step 9)."
    )


class InvalidStatusRequest(ConfigurationError):
    """`--snapshot` was given without `--caselist`, which it is a snapshot of."""

    def __init__(self) -> None:
        super().__init__("--snapshot needs --caselist", field="--snapshot", source="cli")


# ------------------------------------------------------------------------------------------------
# Publish and status guards
# ------------------------------------------------------------------------------------------------


# ------------------------------------------------------------------------------------------------
# Publish and status rendering
# ------------------------------------------------------------------------------------------------


def publish_summary(report: PublishReport, settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist publish`.

    For a program first — the scheduled sync (`v1-e34-t02`) reads it. `applied` says whether
    anything was uploaded; per snapshot, a dry run carries its `planned` action counts and an
    applied run its `results`; `failed_sha256` is the list a retry would be about. Digests and keys
    only: nothing from inside a manifest.

    `manifest_error` is the sentence for a person; `manifest_error_code` is the code of a manifest
    that failed on its own (`v1-e34-t13`). Until then the code was written at the front of the
    sentence, `"STORE_UNAVAILABLE: …"`, and read back out of it.
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
            entry["manifest_error_code"] = outcome.manifest_error_code
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
    """The `--json` envelope's `data` for `caselist status`: one object per snapshot.

    `removal_residue` is one object per caselist compared (`v1-e30-t10`): what a version listing
    shows of its removed files, by digest prefix and count, or `checked: false` with `null` counts
    where the listing was refused. No whole digest and nothing from a manifest row. Each also gives
    `older_versions`, by key role and count, and `older_than`, the latest completed removal that
    touched the caselist (`v1-e30-t15`). `removals_not_checked` names the completed removals no
    version was compared with, because the build that made them did not record their reach.

    Per snapshot, `mismatches` gives each of `checksum_mismatches` with its kind, `manifest` or
    `source`, in the same order; `checksum_mismatches` is unchanged (`v1-e30-t12`). Beside them,
    `suppressed_rows` counts the local manifest's rows the suppression list stops, and
    `suppressed_row_prefixes` names their files; `held_rows`, `held_row_prefixes` and
    `held_row_requests` do the same for its rows at a path a removal holds (`v1-e30-t21`), which an
    older build imported. `held_skipped_rows` and `held_skipped_row_requests` count the skipped
    members' rows at such a path, a symbolic link named as the removed file, which have no digest to
    name and which every build before `v1-e30-t22` wrote. `held_only_in_bucket`, in bucket mode and
    only when above zero, counts the raw sources this machine lacks that the bucket holds at the
    manifest's digest, which count as present (`v1-e40-t13`). `held_in_inbox` is one object per caselist
    compared: the uploads at a held path in the download inbox's archives, by count,
    `sha256_prefixes` and `requests`. `refused_at_import` is the same, for the uploads an import
    refused at a held path that the same removal run again has not yet listed, from the held-digest
    record (`v1-e30-t24`). `held_parsed_objects` is the same again, for the parsed files in the
    bucket of bytes only a held path discloses, which an earlier build's `caselist parse --publish`
    sent (`v1-e31-t26`): `objects` counts the sources, not their version directories. `removals_owed`
    is every request any of these names, whose removal is
    owed again. None of these is part of `in_sync`. `withdrawn_copies_left` is one object per file
    withdrawn from a caselist that keeps no holder of it, of whose copy there something is left, by
    caselist, digest prefix, the request the withdrawal record gives and counts (`v1-e30-t19`); since
    `v1-e30-t24` it is part of `in_sync`, as `removal_residue` is. `withdrawals_not_attributed` is
    the requests of withdrawals no record attributes, which an earlier build made, and is not part
    of `in_sync`. `suppressed_objects` is one object per caselist
    compared, because one listing of a caselist's source prefix finds them for all its snapshots:
    the count of current source objects whose digest is suppressed, and their `sha256_prefixes`.
    A removed file is named by the first twelve characters of its digest, as in `removal_residue`.
    """
    return {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "in_sync": report.in_sync,
        "snapshots": [_status_entry(entry) for entry in report.snapshots],
        "suppressed_objects": [
            {
                "caselist": caselist,
                "objects": len(found := report.suppressed_objects_of(caselist)),
                "sha256_prefixes": [digest_prefix(digest_of_key(key)) for key in found],
            }
            for caselist in report.caselists
        ],
        "removal_residue": [_residue_entry(one) for one in report.residue],
        "removals_not_checked": list(report.removals_not_checked),
        "held_in_inbox": [
            {
                "caselist": caselist,
                "uploads": len(found := report.held_in_inbox_of(caselist)),
                "sha256_prefixes": [digest_prefix(upload.sha256) for upload in found],
                "requests": sorted({upload.request_id for upload in found}),
            }
            for caselist in report.caselists
        ],
        "refused_at_import": [
            {
                "caselist": caselist,
                "uploads": len(found := report.refused_at_import_of(caselist)),
                "sha256_prefixes": [digest_prefix(upload.sha256) for upload in found],
                "requests": sorted({upload.request_id for upload in found}),
            }
            for caselist in report.caselists
        ],
        "held_parsed_objects": [
            {
                "caselist": caselist,
                "objects": len(found := report.held_parsed_objects_of(caselist)),
                "sha256_prefixes": [digest_prefix(one.sha256) for one in found],
                "requests": sorted({one.request_id for one in found}),
            }
            for caselist in report.caselists
        ],
        "removals_owed": list(report.removals_owed),
        "withdrawn_copies_left": [
            {
                "caselist": residue.caselist,
                "sha256_prefix": copy.sha256_prefix,
                "request_id": copy.request_id,
                "current_objects": copy.current_objects,
                "noncurrent_versions": copy.noncurrent_versions,
                "delete_markers": copy.delete_markers,
            }
            for residue in report.residue
            for copy in residue.withdrawn_copies
        ],
        "withdrawals_not_attributed": list(report.withdrawals_not_attributed),
    }


def _residue_entry(residue: CaselistResidue) -> dict[str, JsonValue]:
    """One caselist's residue. Unchecked, every count is `null`: a zero would say nothing is left."""
    files: list[JsonValue] = [
        {
            "sha256_prefix": one.sha256_prefix,
            "current_objects": one.current_objects,
            "noncurrent_versions": one.noncurrent_versions,
            "delete_markers": one.delete_markers,
        }
        for one in residue.files
    ]
    return {
        "caselist": residue.caselist,
        "checked": residue.checked,
        "not_checked_reason": residue.not_checked_reason,
        "current_objects": residue.current_objects,
        "noncurrent_versions": residue.noncurrent_versions,
        "delete_markers": residue.delete_markers,
        "files": files if residue.checked else None,
        "older_versions": [{"role": one.role, "versions": one.versions} for one in residue.older_versions]
        if residue.checked
        else None,
        "older_than": None
        if residue.older_than is None
        else {
            "request_id": residue.older_than.request_id,
            "completed_at": _utc_stamp(residue.older_than.completed_at),
        },
        "school_views": [{"role": one.role, "files": one.versions} for one in residue.school_views]
        if residue.checked
        else None,
        "school_views_older_than": None
        if residue.school_views_older_than is None
        else {
            "request_id": residue.school_views_older_than.request_id,
            "completed_at": _utc_stamp(residue.school_views_older_than.completed_at),
        },
    }


def _utc_stamp(when: datetime) -> str:
    """A moment as the removal log writes one: UTC, `Z`."""
    return when.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _residue_found(residue: CaselistResidue, *, withdrawn: bool = False) -> str:
    """`<caselist>: counts of N file(s) (sha256 <prefix>, …)`, and the versions older than a removal
    by role and count, for a caselist with something left; with `withdrawn`, its withdrawn copies'
    counts too (`v1-e30-t24`), which the table gives a line of their own."""
    found: list[str] = []
    if residue.files:
        named = ", ".join(f"sha256 {one.sha256_prefix}" for one in residue.files)
        found.append(
            f"{residue.current_objects} current object(s), {residue.noncurrent_versions} noncurrent "
            f"version(s) and {residue.delete_markers} delete marker(s) "
            f"of {len(residue.files)} file(s) ({named})"
        )
    if residue.older_versions and residue.older_than is not None:
        counts = [f"{one.versions} {one.role} version(s)" for one in residue.older_versions]
        listed = counts[0] if len(counts) == 1 else f"{', '.join(counts[:-1])} and {counts[-1]}"
        found.append(
            f"{listed} older than {residue.older_than.request_id}, completed "
            f"{residue.older_than.completed_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC"
        )
    if residue.school_views and residue.school_views_older_than is not None:
        counts = [f"{one.versions} {one.role} file(s)" for one in residue.school_views]
        found.append(
            f"{' and '.join(counts)} older than {residue.school_views_older_than.request_id}, completed "
            f"{residue.school_views_older_than.completed_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC"
        )
    if withdrawn and residue.withdrawn_copies:
        found.append(_withdrawn_counts(residue))
    return f"{residue.caselist}: " + "; ".join(found)


def _residue_lines(report: CaselistStatusReport) -> list[str]:
    """What the status table says under it about removal residue: found, not checked, or none."""
    lines = [
        f"REMOVAL RESIDUE in {_residue_found(one)}."
        for one in report.residue
        if one.files or one.older_versions or one.school_views
    ]
    if lines:
        lines.append("A removal left them; docs/runbooks/caselist-removal.md says what to run.")
    unchecked = report.residue_not_checked
    if unchecked:
        lines.append(
            f"Removal residue NOT CHECKED for {', '.join(unchecked)}: this profile may not list object "
            "versions there. That is not a finding of none."
        )
    if report.removals_not_checked:
        lines.append(
            f"Manifest and aggregate versions NOT CHECKED against {', '.join(report.removals_not_checked)}: "
            "the build that made that removal did not record which caselists it touched. That is not a "
            "finding of none."
        )
    lines += _withdrawn_copy_lines(report)
    checked = [one for one in report.residue if one.checked]
    if checked and not report.residue_found:
        lines.append(
            "No version of a removed file is left under raw/ or parsed/, and no manifest or aggregate "
            f"version is older than a removal that touched its caselist ({len(checked)} caselist(s) checked)."
        )
    return lines


def _withdrawn_copy_lines(report: CaselistStatusReport) -> list[str]:
    """What is left of copies withdrawn from a caselist, by caselist and request, and the withdrawals
    no record attributes (`v1-e30-t19`). The first fails the command as residue (`v1-e30-t24`); the
    second does not."""
    lines = [
        f"WITHDRAWN COPIES LEFT in {residue.caselist}: {_withdrawn_counts(residue)}."
        for residue in report.residue
        if residue.withdrawn_copies
    ]
    if lines:
        lines.append(
            "Run that removal again, dry run first, then --execute: docs/runbooks/caselist-removal.md, "
            '"When caselist status reports removal residue".'
        )
    if report.withdrawals_not_attributed:
        lines.append(
            f"Withdrawals NOT ATTRIBUTED to a caselist: {', '.join(report.withdrawals_not_attributed)}. The "
            "build that made that removal recorded no caselist for the copies it withdrew, so what is "
            "left of them is not checked. That is not a finding of none."
        )
    return lines


def _withdrawn_counts(residue: CaselistResidue) -> str:
    """`N current object(s), … of M file(s) withdrawn from <caselist> (sha256 <prefix>, <request>, …)`."""
    copies = residue.withdrawn_copies
    named = ", ".join(f"sha256 {copy.sha256_prefix}, {copy.request_id}" for copy in copies)
    return (
        f"{sum(copy.current_objects for copy in copies)} current object(s), "
        f"{sum(copy.noncurrent_versions for copy in copies)} noncurrent version(s) and "
        f"{sum(copy.delete_markers for copy in copies)} delete marker(s) of {len(copies)} file(s) "
        f"withdrawn from {residue.caselist} ({named})"
    )


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
        "mismatches": [
            {"key": key, "kind": entry.mismatch_kind(key).value} for key in entry.checksum_mismatches
        ],
        "suppressed_rows": len(entry.suppressed_rows),
        "suppressed_row_prefixes": [digest_prefix(digest) for digest in entry.suppressed_rows],
        "held_rows": len(entry.held_rows),
        "held_row_prefixes": [digest_prefix(row.sha256) for row in entry.held_rows],
        "held_row_requests": sorted({row.request_id for row in entry.held_rows}),
        "held_skipped_rows": len(entry.held_skipped_rows),
        "held_skipped_row_requests": sorted(set(entry.held_skipped_rows)),
        # Only in bucket mode, and only when there are some, so local mode's output is unchanged (v1-e40-t13).
        **({"held_only_in_bucket": len(entry.held_only_in_bucket)} if entry.held_only_in_bucket else {}),
    }


def _suppressed_object_lines(report: CaselistStatusReport) -> list[str]:
    """Under the status table, per caselist: the current objects of suppressed sources, by count."""
    lines: list[str] = []
    for caselist in report.caselists:
        found = report.suppressed_objects_of(caselist)
        if found:
            named = ", ".join(f"sha256 {digest_prefix(digest_of_key(key))}" for key in found)
            lines.append(
                f"SUPPRESSED SOURCE OBJECTS in {caselist}: {len(found)} current object(s) ({named})."
            )
    return lines


def _held_lines(report: CaselistStatusReport) -> list[str]:
    """Under the status table: rows and uploads at a held path, in the inbox or refused at import
    (`v1-e30-t24`), and a held upload's parsed file in the bucket (`v1-e31-t26`), by digest prefix
    and request.

    A skipped member's row has no digest, so it is named by the request holding its path alone.
    """
    lines: list[str] = []
    for entry in report.held_snapshots:
        named = f"HELD PATH ROWS in {entry.caselist} {entry.snapshot}"
        if entry.held_rows:
            held = _held_named((row.sha256, row.request_id) for row in entry.held_rows)
            lines.append(f"{named}: {len(entry.held_rows)} row(s) at a path a removal holds ({held}).")
        if entry.held_skipped_rows:
            requests = ", ".join(sorted(set(entry.held_skipped_rows)))
            lines.append(
                f"{named}: {len(entry.held_skipped_rows)} skipped member row(s) at a path a removal "
                f"holds ({requests})."
            )
    for caselist in report.caselists:
        found = report.held_in_inbox_of(caselist)
        if found:
            lines.append(
                f"HELD UPLOADS IN THE DOWNLOAD INBOX for {caselist}: {len(found)} upload(s) at a path a "
                f"removal holds ({_held_named((one.sha256, one.request_id) for one in found)})."
            )
    for caselist in report.caselists:
        refused = report.refused_at_import_of(caselist)
        if refused:
            named = _held_named((one.sha256, one.request_id) for one in refused)
            lines.append(
                f"REFUSED AT IMPORT AT A HELD PATH in {caselist}: {len(refused)} upload(s) the same "
                f"removal has not yet listed ({named})."
            )
    for caselist in report.caselists:
        parsed = report.held_parsed_objects_of(caselist)
        if parsed:
            named = _held_named((one.sha256, one.request_id) for one in parsed)
            lines.append(
                f"HELD UPLOADS PARSED IN THE BUCKET in {caselist}: {len(parsed)} source(s) only a held "
                f"path discloses, whose parsed file an earlier build published ({named})."
            )
    if report.removals_owed:
        lines.append(_removals_owed(report))
    return lines


def _held_named(held: Iterable[tuple[str, str]]) -> str:
    """`sha256 <prefix>, <request id>` for each held file, comma-separated."""
    return ", ".join(f"sha256 {digest_prefix(digest)}, {request_id}" for digest, request_id in held)


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


def _status_table(
    report: CaselistStatusReport, settings: Settings, *, owed_sentence: str | None = None
) -> TableSpec:
    rows = [
        [
            entry.caselist,
            entry.snapshot,
            f"{entry.local_files}/{entry.sources}" if entry.local_manifest else "no manifest",
            str(entry.published_sources),
            str(len(entry.missing_sources)),
            ("differs" if entry.manifest_mismatched else "yes") if entry.manifest_present else "no",
            str(len(entry.source_mismatches)),
            str(len(entry.suppressed_rows)),
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
            "Source mismatches",
            "Suppressed rows",
            "In sync",
        ),
        rows=rows,
        title=f"{settings.storage.s3.bucket} ({settings.environment.value}) against this machine",
        caption="\n".join(
            [
                "Every snapshot agrees."
                if not drifted
                else f"{drifted} snapshot(s) differ; see --json for digests.",
                *_suppressed_object_lines(report),
                *_held_lines(report),
                *_residue_lines(report),
                *_held_only_in_bucket_lines(report),
                # What the runs owe the parsed store (`v1-e40-t08`): not drift, and not part of in sync.
                *([owed_sentence] if owed_sentence else []),
            ]
        ),
    )


def _held_only_in_bucket_lines(report: CaselistStatusReport) -> list[str]:
    """Under the status table, in bucket mode: the raw sources only the bucket holds, by count and
    snapshot (`v1-e40-t13`). Counted present, so not drift, and not among the local files either."""
    held = [entry for entry in report.snapshots if entry.held_only_in_bucket]
    if not held:
        return []
    named = ", ".join(
        f"{len(entry.held_only_in_bucket)} in {entry.caselist} {entry.snapshot}" for entry in held
    )
    return [
        f"Raw sources held only in the bucket: {named}. Bucket mode counts each as present, at the "
        "manifest's digest."
    ]


def _publish_failure(report: PublishReport, payload: dict[str, JsonValue]) -> CommandFailure:
    """What an incomplete publish reports: the failed digests, and every count in details.

    A plan that cannot be carried out (`PUBLISH_BLOCKED`) is `1`. An applied run that left a
    snapshot incomplete is `3` when every failure behind it is the store not answering, and `1` as
    soon as one is not (`v1-e01-t20`). The codes are the publish result's own
    (:attr:`~debate_core.application.caselist.publish_service.PublishReport.failure_codes`): each
    failed source's, and a failed manifest's from its structured `manifest_error_code`, never from
    the text of its message (`v1-e34-t13`).

    The details are the whole report and the message names every failed digest, for `--json`; the
    panel prints a message that counts them and :func:`_publish_panel` in their place (`v1-e30-t27`).
    """
    failed = report.failed_sha256
    if not report.applied:
        cannot = (
            f"{len(failed)} source(s) cannot be published as planned (a checksum mismatch in the "
            "bucket, or missing from this machine)"
        )
        return CommandFailure(
            code="PUBLISH_BLOCKED",
            message=f"{cannot}: {', '.join(failed)}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint=(
                "Nothing was uploaded. A mismatch in the bucket needs a person; a missing file needs "
                "a re-import."
            ),
            panel_message=cannot,
            panel_details=_publish_panel(report, payload),
        )
    incomplete = [outcome for outcome in report.snapshots if not outcome.complete]
    withheld = ", ".join(f"{outcome.snapshot} ({outcome.manifest.value})" for outcome in incomplete)
    named = f"; failed sha256: {', '.join(failed)}" if failed else ""
    not_complete = f"{len(incomplete)} snapshot(s) not complete in the bucket"
    return CommandFailure(
        code="PUBLISH_INCOMPLETE",
        message=f"{not_complete}, manifest {withheld}{named}",
        exit_code=exit_code_for_failure_codes(report.failure_codes),
        details=payload,
        hint="Re-run the same command: every confirmed source is skipped and the manifests follow.",
        panel_message=f"{not_complete}; {len(failed)} source(s) failed" if failed else not_complete,
        panel_details=_publish_panel(report, payload),
    )


def _publish_panel(report: PublishReport, payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """What a failed publish's panel prints in place of its details, the whole report (`v1-e30-t27`).

    The environment and the bucket, how many snapshots there were and how many did not go, and one
    line per snapshot that did not, as `caselist status`'s panel has one per snapshot that differs.
    """
    panel: dict[str, JsonValue] = {"environment": payload["environment"], "bucket": payload["bucket"]}
    if not report.applied:
        stopped = [plan for plan in report.plan.snapshots if plan.blocked or plan.withholding_rows]
        panel["snapshots"] = f"{len(report.plan.snapshots)} planned, {len(stopped)} blocked"
        for plan in stopped:
            panel[f"{plan.caselist} {plan.snapshot}"] = _what_blocks(plan)
        return every_value_in_full(panel)
    incomplete = [outcome for outcome in report.snapshots if not outcome.complete]
    panel["snapshots"] = f"{len(report.snapshots)} published, {len(incomplete)} not complete"
    panel["sources"] = ", ".join(f"{report.count(result)} {result.value}" for result in SourceResult)
    for outcome in incomplete:
        panel[f"{outcome.caselist} {outcome.snapshot}"] = _what_did_not_complete(outcome)
    return every_value_in_full(panel)


def _what_blocks(plan: SnapshotPlan) -> str:
    """What stops one planned snapshot: its blocking sources, then the rows that withhold its manifest."""
    what = [
        f"{len(sources)} {counted} {some_prefixes(sorted(source.sha256 for source in sources))}"
        for counted, sources in (
            ("source(s) missing from this machine", plan.of(SourceAction.MISSING_LOCALLY)),
            ("source(s) mismatched in the bucket", plan.of(SourceAction.MISMATCHED)),
        )
        if sources
    ]
    rows: list[str] = []
    if plan.suppressed_rows:
        rows.append(f"{len(plan.suppressed_rows)} suppressed row(s) {some_prefixes(plan.suppressed_rows)}")
    if plan.held_rows:
        held = tuple(row.sha256 for row in plan.held_rows)
        rows.append(f"{len(held)} row(s) at a held path {some_prefixes(held)}")
    if plan.held_skipped_rows:
        requests = ", ".join(sorted(set(plan.held_skipped_rows)))
        rows.append(f"{len(plan.held_skipped_rows)} skipped member row(s) at a held path ({requests})")
    if rows:
        what.append(f"manifest withheld for {', '.join(rows)}")
    return ", ".join(what)


def _what_did_not_complete(outcome: SnapshotOutcome) -> str:
    """One incomplete snapshot: its manifest, and its failed sources by count, prefix and code."""
    what = f"manifest {outcome.manifest.value}"
    if outcome.manifest_error_code is not None:
        what += f" ({outcome.manifest_error_code})"
    if outcome.failed:
        failed = sorted(source.sha256 for source in outcome.failed)
        codes = by_count(source.error_code or UNMODELLED_ERROR_CODE for source in outcome.failed)
        what += f", {len(failed)} source(s) failed {some_prefixes(failed)}: {codes}"
    return what


class CompleteArchiveNotImportedByHand(ConfigurationError):
    """`caselist import` was given a complete archive (`<slug>-all-<date>.zip`, `v1-e34-t04`).

    This command files into the weekly series, where a complete archive collides with the weekly of
    its date and strands every older one (ADR-0017, revision of 2026-09-26). It is imported as its
    own snapshot by `caselist pull --full-archive <slug>` instead. Recognised by its name, as the
    site and the pull name it; a renamed copy is not recognised.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"{name} is a complete archive, which `caselist import` would file into the weekly series; "
            "import it with `caselist pull --full-archive <slug>`, which files it as its own snapshot",
            field="source",
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
            f"debate_cli.caselist_events (known prefixes: {known})",
            field="--event",
            source="cli",
        )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------


def import_summary(
    report: ImportReport, manifest: Path | None, remeasured: LaterManifestsRemeasured | None = None
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist import`.

    Written for a program first, because the scheduled weekly import (`v1-e34-t02`) reads it:
    every classification has a count whether or not it occurred, `applied` says whether anything
    was written, and `manifest` is the path or `null` rather than a sentence to parse.

    `counts["NEW"]` is week-over-week: not present in `previous_snapshot`. `first_seen` is what is
    new to the caselist — distinct stored digests no earlier snapshot of it held — and is the
    number to sum across weeks (`v1-e30-t08`).

    `held_at_removed_paths` is `{request id: count}` for the uploads refused because a removal
    holds their path (`v1-e30-t13`): each is one of `counts["SUPPRESSED"]`, and empty when none was.

    `rewritten_manifests` names the later snapshots whose manifests were measured again and
    rewritten, weeklies in date order and then the newest complete archive, and
    `complete_archive_recounted` is that complete archive's new withdrawal counts, or `null`
    (`v1-e30-t18`). Both are empty under `--dry-run`, which measures nothing again. Additive keys.
    """
    recount = remeasured.complete_archive if remeasured is not None else None
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
        "held_at_removed_paths": dict(sorted(report.held_by_request.items())),
        "skipped": {str(reason): count for reason, count in sorted(report.skipped.items(), key=str)},
        "skipped_total": sum(report.skipped.values()),
        "distinct_sha256": report.distinct_digests,
        "newly_stored_blobs": report.newly_stored_blobs,
        "first_seen": report.first_seen,
        "warnings": report.warning_count,
        "manifest": str(manifest) if manifest is not None else None,
        "rewritten_manifests": list(remeasured.rewritten) if remeasured is not None else [],
        "complete_archive_recounted": (
            {
                "snapshot": recount.snapshot,
                "withdrawn": recount.after.withdrawn,
                "superseded": recount.after.superseded,
                "earlier_snapshots": recount.after.earlier_snapshots,
            }
            if recount is not None
            else None
        ),
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


def openev_metadata_reimport_summary(
    report: OpenEvMetadataReimport, manifest: Path | None
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist reimport-openev-metadata`.

    Counts and camps only. `camps_before` and `camps_after` count member rows per camp; a camp is an
    institution, and no path, title or file name appears here. `manifest` is the path written, or
    `null` when nothing was (a dry run, or a manifest already right).
    """
    return {**reimport_counts(report), "manifest": str(manifest) if manifest is not None else None}


def _reimport_table(report: OpenEvMetadataReimport, manifest: Path | None) -> TableSpec:
    """One row per camp, before and after, then what was written."""
    camps = sorted(set(report.camps_before) | set(report.camps_after))
    rows = [
        [camp, str(report.camps_before.get(camp, 0)), str(report.camps_after.get(camp, 0))] for camp in camps
    ]
    if not report.applied:
        outcome = "Planned only; nothing was written. Re-run without --dry-run to apply it."
    elif manifest is None:
        outcome = "The manifest was already right; nothing was written."
    else:
        outcome = (
            f"{report.camp_files_updated} camp-file record(s) corrected; manifest at {manifest.name}. "
            "Publish the release to bring the bucket's manifest in line."
        )
    return TableSpec(
        columns=("Camp", "Files before", "Files after"),
        rows=rows,
        title=f"openev {report.release} metadata ({'dry run' if not report.applied else 're-derived'})",
        caption=(
            f"{report.rows} file(s), {report.titles_changed} title(s) changed, "
            f"{report.identities_added} row(s) given their upstream identity, "
            f"{report.blobs_missing} not held locally. {outcome}"
        ),
    )


def _summary_table(
    report: ImportReport, manifest: Path | None, remeasured: LaterManifestsRemeasured | None = None
) -> TableSpec:
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
        caption=_caption(report, manifest) + _remeasured_note(remeasured),
    )


def _remeasured_note(remeasured: LaterManifestsRemeasured | None) -> str:
    """One sentence when the later manifests were rewritten: which, and that a publish uploads them."""
    if remeasured is None or not remeasured.rewritten:
        return ""
    weeklies = (
        f" Measured again with this week and rewritten: {', '.join(remeasured.weeklies)}."
        if remeasured.weeklies
        else ""
    )
    recount = remeasured.complete_archive
    recounted = (
        f" The complete archive {recount.snapshot} recounted: {recount.after.withdrawn} withdrawn, "
        f"{recount.after.superseded} superseded against {recount.after.earlier_snapshots} earlier "
        "snapshot(s)."
        if recount is not None
        else ""
    )
    return f"{weeklies}{recounted} `caselist publish --caselist {remeasured.caselist}` uploads them."


def _held_note(report: ImportReport) -> str:
    """One sentence when a removal's hold refused an upload: how many, under which request, and what next."""
    if not report.held_by_request:
        return ""
    requests = ", ".join(
        f"{count} under {request}" for request, count in sorted(report.held_by_request.items())
    )
    return (
        f" SUPPRESSED includes {report.held_at_removed_paths} new upload(s) at a removed path ({requests}), "
        "refused because that removal holds the path: run the same `caselist remove` again to finish."
    )


def _caption(report: ImportReport, manifest: Path | None) -> str:
    """What the numbers mean, in the lines under the table: NEW's baseline, and first-seen beside it."""
    against = (
        f"against {report.previous_snapshot.isoformat()}"
        if report.previous_snapshot is not None
        else "the first archive for this caselist"
    )
    warned = f", {report.warning_count} filename(s) not fully read" if report.warning_count else ""
    new_means = (
        f"NEW: not present in the {report.previous_snapshot.isoformat()} snapshot"
        if report.previous_snapshot is not None
        else "NEW: no earlier snapshot to compare with"
    )
    first_seen = (
        f"; {report.first_seen} first seen in {report.caselist}" if report.first_seen is not None else ""
    )
    meaning = f"{new_means}{first_seen}.{_held_note(report)}"
    if not report.applied:
        return (
            f"{report.member_count} member(s), {against}{warned}. {meaning} Planned only; nothing was "
            "written. Re-run without --dry-run to import it."
        )
    return (
        f"{report.member_count} member(s), {against}{warned}. {meaning} "
        f"{report.newly_stored_blobs} new file(s) stored; manifest at "
        f"{manifest.name if manifest else 'none'}."
    )


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion.

    The services are `async` because the API and the workers will await them; a CLI command is the
    one caller with no event loop of its own, so it starts one for the duration of the command.
    """
    return asyncio.run(awaitable)

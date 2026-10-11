"""`debate-research caselist remove | unsuppress`: honouring a takedown request, and reversing a mistake.

::

    # The dry run: what would go, what is shared and kept, what the list will say. Changes nothing.
    DEBATE_ENV=dev debate-research caselist remove --team 'hsld26/Maple Grove/QX' \\
        --request RM-2026-01 --reason REQUESTED_BY_TEAM

    # Then the same command with --execute, under the takedown profile.
    DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal debate-research caselist remove \\
        --team 'hsld26/Maple Grove/QX' --request RM-2026-01 --reason REQUESTED_BY_TEAM --execute

    # Prod: dry run first, every time, and --confirm-prod on top of --execute.
    DEBATE_ENV=prod DEBATE_REMOVAL_PROFILE=debate-prod-evidence-removal debate-research caselist remove \\
        --team 'hsld26/Maple Grove/QX' --request RM-2026-01 --reason REQUESTED_BY_TEAM \\
        --execute --confirm-prod

    # A file removed in error: append an un-suppress entry (the list is never edited).
    DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal debate-research caselist unsuppress \\
        --sha256 <sha256> --reason REMOVED_IN_ERROR --request RM-2026-01 --execute

Every decision is :class:`~debate_core.application.caselist.removal_service.CaselistRemovalService`'s
and :class:`~debate_core.application.caselist.removal_plan.RemovalPlanner`'s. This module decides
which flags mean what, refuses what the policy refuses, and renders the plan for a person deciding
under a 7-day clock (`docs/policies/caselist-data-use.md`, "Removal").

## Dry run by default

Without `--execute` nothing is written anywhere — no record, file, object, list line or log line —
and only the everyday evidence profile is used. The plan is printed in the order an operator needs
it: what will be removed, what is shared and therefore kept, the later uploads at each removed path
that the plan adds and the earlier versions it leaves (`v1-e30-t11`), the manifests that will be
rewritten, the files in the download inbox that hold removed files and what happens to each
(`v1-e30-t09`), the suppression entries exactly as they will be appended, and a paragraph of facts
for the confirmation to the requester, then the exact command that executes it.

`--execute` needs the takedown profile (`DEBATE_REMOVAL_PROFILE`) and, in prod, `--confirm-prod`.

## Later uploads, and `--only-named`

A removal request covers later uploads at the same path, so the plan includes every later upload
the store holds at a path it takes a named file from, and says how many it adds where the operator
confirms it: above the command under *TO CARRY IT OUT*, and again when `--execute` starts.
`--only-named` plans the named files alone, for a request that is explicitly about one version; the
later uploads are still listed, as left in place. The command printed under *TO CARRY IT OUT*
carries the flag, so the plan that is executed is the plan that was read.

## What is printed and what is not

The plan's text names the team's paths, school and team code: this is the operator's own terminal,
and checking the plan against the request is the point of the dry run. Nothing here *logs* them, and
the removal log and the suppression list cannot hold them (`debate_core.application.ports.
suppression`).

`--json` carries none of them (`v1-e30-t11`): no school, team code, path, camp, title or file
name. A file is its sha256, a disclosure is the digest the suppression list uses for one
(:func:`~debate_core.application.ports.suppression.disclosure_digest`), a team selector is its
caselist, and an inbox file is the label an error would give it. JSON is what gets piped, saved and
pasted, and the policy keeps those names out of everything that is.

## Exit codes

`0` for a dry run and for a completed execution. `1` for a refusal (a malformed selector, a missing
`--execute` guard, `DEBATE_REMOVAL_PROFILE` unset — all before anything changes) and for a run that
stopped part-way for a reason re-running cannot cure. `3` when the bucket did not answer —
unavailable, an expired takedown session (the S3 adapter reports a profile missing from the AWS
config that way too), or a refused request — whether that stopped the preflight or a run part-way,
whose message says to re-run the same command (`v1-e01-t20`). A removal that completed and could not
be logged stays `1`: running it again would log zero counts.
"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Coroutine
from typing import Annotated, Any

import typer

from debate_cli.commands.store import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode
from debate_core.application.caselist.inbox_purge import InboxAction, InboxFilePlan
from debate_core.application.caselist.removal_path_versions import (
    PathVersion,
    SamePathEvidence,
    VersionRelation,
)
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    InvalidRemovalRequest,
    LaterUploadOutcome,
    PlannedSource,
    RemovalPlan,
    RemovalSelector,
    Side,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.caselist.removal_service import RemovalReport, UnsuppressPlan, UnsuppressReport
from debate_core.application.ports.suppression import (
    REINSTATEMENT_REASONS,
    REMOVAL_REASONS,
    ReasonCode,
    disclosure_digest,
)
from debate_core.application.settings import Environment, Settings

__all__ = ["ONLY_NAMED_FLAG", "plan_summary", "remove", "render_plan", "unsuppress"]

ONLY_NAMED_FLAG = "--only-named"
_REMOVAL_REASONS = ", ".join(sorted(REMOVAL_REASONS))
_REINSTATEMENT_REASONS = ", ".join(sorted(REINSTATEMENT_REASONS))


def remove(
    ctx: typer.Context,
    source: Annotated[
        str | None, typer.Option("--source", help="Remove one file, by its sha256.", show_default=False)
    ] = None,
    team: Annotated[
        str | None,
        typer.Option("--team", help="Remove everything one team disclosed: <caselist>/<school>/<team code>."),
    ] = None,
    request: Annotated[
        str, typer.Option("--request", help="The register id of the request, e.g. RM-2026-01.")
    ] = "",
    reason: Annotated[str, typer.Option("--reason", help=f"Why: one of {_REMOVAL_REASONS}.")] = "",
    execute: Annotated[
        bool, typer.Option("--execute", help="Carry out the removal. Without it, a dry run.")
    ] = False,
    include_shared: Annotated[
        bool,
        typer.Option("--include-shared", help="Also remove files another team or a camp file holds too."),
    ] = False,
    only_named: Annotated[
        bool,
        typer.Option(
            ONLY_NAMED_FLAG,
            help="Leave later uploads at the removed path in place: for a request about one version.",
        ),
    ] = False,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required with --execute in the production environment.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Remove a source or a team's disclosures from this machine and the bucket, and suppress them."""
    cli = _with_json(cli_context(ctx), json_output)
    settings = cli.services.settings
    selector = _selector(source, team)
    code = _reason(reason, REMOVAL_REASONS, _REMOVAL_REASONS)
    if not request:
        raise InvalidRemovalRequest("--request is required: the register id, e.g. RM-2026-01")
    _refuse(cli, ctx, _guard(settings, execute=execute, confirmed=confirm_prod, command="caselist remove"))

    service = cli.services.caselist_removal()
    cli.output.detail(f"planning against {settings.storage.s3.bucket}")
    plan = _run(
        service.plan(
            selector, request_id=request, reason=code, include_shared=include_shared, only_named=only_named
        )
    )
    if not execute:
        cli.output.success(
            command_name(ctx), plan_summary(plan, settings, None), display=render_plan(plan, None)
        )
        return
    cli.output.detail(
        f"executing under the takedown profile: {_what_the_plan_covers(plan, carried_out=True)}"
    )
    report = _run(service.execute(plan))
    cli.output.success(
        command_name(ctx), plan_summary(plan, settings, report), display=render_plan(plan, report)
    )


def unsuppress(
    ctx: typer.Context,
    sha256: Annotated[str, typer.Option("--sha256", help="The file to let back in.")],
    reason: Annotated[str, typer.Option("--reason", help=f"Why: one of {_REINSTATEMENT_REASONS}.")],
    request: Annotated[
        str | None,
        typer.Option("--request", help="The register id of the original request, if there is one."),
    ] = None,
    execute: Annotated[
        bool, typer.Option("--execute", help="Append the entry. Without it, a dry run.")
    ] = False,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required with --execute in the production environment.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Lift a suppression by appending an un-suppress entry. Purged data is not restored."""
    cli = _with_json(cli_context(ctx), json_output)
    settings = cli.services.settings
    _refuse(
        cli, ctx, _guard(settings, execute=execute, confirmed=confirm_prod, command="caselist unsuppress")
    )
    service = cli.services.caselist_removal()
    code = _reason(reason, REINSTATEMENT_REASONS, _REINSTATEMENT_REASONS)
    plan = _run(service.plan_unsuppress(sha256.strip().lower(), reason=code, request_id=request))
    report = _run(service.unsuppress(plan)) if execute else None
    cli.output.success(
        command_name(ctx), unsuppress_summary(plan, settings, report), display=render_unsuppress(plan, report)
    )


# ------------------------------------------------------------------------------------------------
# Guards
# ------------------------------------------------------------------------------------------------


def _selector(source: str | None, team: str | None) -> RemovalSelector:
    if (source is None) == (team is None):
        raise InvalidRemovalRequest(
            "give exactly one of --source <sha256> or --team <caselist>/<school>/<team code>"
        )
    if source is not None:
        return SourceSelector(source.strip().lower())
    assert team is not None
    return parse_team_selector(team)


def _reason(text: str, allowed: frozenset[ReasonCode], listed: str) -> ReasonCode:
    try:
        code = ReasonCode(text.strip().upper())
    except ValueError:
        code = None
    if code is None or code not in allowed:
        raise InvalidRemovalRequest(f"--reason must be one of {listed}")
    return code


def _guard(settings: Settings, *, execute: bool, confirmed: bool, command: str) -> CommandFailure | None:
    """A removal works on dev or prod, needs a bucket even to plan, and in prod needs --confirm-prod."""
    if settings.environment not in SYNCABLE_ENVIRONMENTS or not settings.storage.s3.bucket:
        return CommandFailure(
            code="ENVIRONMENT_NOT_REMOVABLE",
            message=(
                f"`{command}` works on dev or prod, whose buckets hold the evidence; "
                f"not {settings.environment.value}"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev (then prod) and try again.",
        )
    if execute and settings.environment is Environment.PROD and not confirmed:
        return CommandFailure(
            code="CONFIRMATION_REQUIRED",
            message=(
                f"refusing to change production evidence without {CONFIRM_PROD_FLAG}: "
                f"{settings.storage.s3.bucket}"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value, "bucket": settings.storage.s3.bucket},
            hint=f"Run it without --execute first and read the plan, then add --execute {CONFIRM_PROD_FLAG}.",
        )
    return None


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


def _with_json(cli: CliContext, json_output: bool) -> CliContext:
    """`--json` after the command, as well as before the group, as `caselist cards` takes it."""
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    return cli


# ------------------------------------------------------------------------------------------------
# The plan, for a person
# ------------------------------------------------------------------------------------------------


def render_plan(plan: RemovalPlan, report: RemovalReport | None) -> str:
    """The plan as an operator reads it before deciding, or the outcome after `--execute`."""
    lines: list[str] = []
    # Later uploads have their own section; these three are the files the request names.
    removed, withdrawn, skipped = (
        _not_later_uploads(plan, Disposition.REMOVE),
        _not_later_uploads(plan, Disposition.WITHDRAW),
        _not_later_uploads(plan, Disposition.SKIP_SHARED),
    )
    if report is None:
        lines.append(f"DRY RUN: nothing was changed. {plan.environment}, bucket {plan.bucket}.")
    else:
        lines.append(
            f"DONE in {plan.environment} ({plan.bucket}): {report.local_records_deleted} record(s), "
            f"{report.local_files_deleted} local file(s), {report.s3_versions_deleted} bucket object "
            f"version(s) deleted; {report.manifests_rewritten} manifest(s) rewritten without "
            f"{report.manifest_rows_dropped} row(s); {report.inbox_files_deleted} inbox file(s) deleted and "
            f"{report.inbox_files_rewritten} rewritten."
        )
        lines.append(f"It covered {_what_the_plan_covers(plan, carried_out=True)}.")
    lines.append(f"Request {plan.request_id}, reason {plan.reason}, selector {_describe(plan.selector)}.")
    if plan.nothing_to_do and not skipped:
        lines += ["", "Nothing is left to remove: everything this selects is already gone and suppressed."]

    if removed:
        lines += ["", f"WILL BE REMOVED, everywhere, and suppressed: {len(removed)} file(s)"]
        for number, source in enumerate(removed, start=1):
            lines += _source_lines(number, source, plan)
    if withdrawn:
        lines += [
            "",
            f"SHARED, KEPT: {len(withdrawn)} file(s) another team or a camp file also holds. Only this",
            "team's copies are withdrawn and suppressed; the file stays for the others.",
            "--include-shared would remove it for everyone.",
        ]
        for number, source in enumerate(withdrawn, start=1):
            lines += _source_lines(number, source, plan)
    if skipped:
        lines += [
            "",
            f"SHARED, SKIPPED: {len(skipped)} file(s) more than one holder has. Nothing is done to them",
            "without --include-shared, which removes them for every holder; --team withdraws one team's",
            "copies.",
        ]
        for number, source in enumerate(skipped, start=1):
            lines += _source_lines(number, source, plan)

    lines += _later_upload_lines(plan)
    lines += _earlier_version_lines(plan)

    if plan.manifests:
        lines += ["", f"MANIFESTS REWRITTEN without the rows that name it: {len(plan.manifests)}"]
        for rewrite in plan.manifests:
            versions = "" if rewrite.versions is None else f", {rewrite.versions} version(s) replaced by one"
            lines.append(f"  {rewrite.side.value:6} {rewrite.key}  -{rewrite.rows_dropped} row(s){versions}")

    lines += ["", *_inbox_lines(plan)]

    entries = plan.suppression_entries
    whole = sum(1 for entry in entries if entry.disclosure is None)
    lines += [
        "",
        f"SUPPRESSION ENTRIES appended to the list, here and in the bucket: {len(entries)}",
        f"  {whole} whole file(s), and {len(entries) - whole} of this team's path(s) to a shared file. Each",
        "  line below is exactly what is written, with recorded_at set when it runs; no school, team",
        "  code or name appears in any of them.",
    ]
    lines += [f"  {entry.to_line()}" for entry in entries] or [
        "  (none: everything selected is already on the list)"
    ]

    if not plan.versions_counted and report is None:
        lines += [
            "",
            "Versions not counted: the everyday profile may not list object versions. --execute lists and",
            "deletes every version with the takedown profile, and reports how many.",
        ]
    lines += ["", "FOR THE CONFIRMATION TO THE REQUESTER", *_confirmation(plan)]
    if report is None and not plan.nothing_to_do:
        lines += [
            "",
            "TO CARRY IT OUT",
            f"  This plan covers {_what_the_plan_covers(plan)}.",
            *_what_the_flag_would_change(plan),
            f"  {_execute_command(plan)}",
        ]
    return "\n".join(lines)


def _not_later_uploads(plan: RemovalPlan, disposition: Disposition) -> tuple[PlannedSource, ...]:
    return tuple(source for source in plan.of(disposition) if source.inclusion is not Inclusion.LATER_UPLOAD)


def _what_the_plan_covers(plan: RemovalPlan, *, carried_out: bool = False) -> str:
    """One clause: how many files the request names and how many later uploads the plan adds.

    Said where the operator confirms the plan, above the `--execute` command, and, as what was
    `carried_out`, when the execution starts and on the `DONE` line.
    """
    named = len(plan.included_as(Inclusion.NAMED))
    found = plan.later_uploads_found
    if plan.only_named:
        return (
            f"the {named} file(s) named only; {found} later upload(s) at the removed path(s) are left in "
            f"place ({ONLY_NAMED_FLAG})"
        )
    kept = found - plan.later_uploads_added
    also = f" ({kept} more is shared and kept)" if kept else ""
    later = f"{plan.later_uploads_added} later upload(s) at the removed path(s){also}"
    if carried_out:
        return f"the {named} file(s) named and {later}"
    return f"the {named} file(s) named, and adds {later}"


def _what_the_flag_would_change(plan: RemovalPlan) -> list[str]:
    if not plan.later_uploads:
        return []
    if plan.only_named:
        return [f"  Without {ONLY_NAMED_FLAG} it would include them: a removal request covers later uploads."]
    return [
        f"  For a request that is explicitly about one version, plan again with {ONLY_NAMED_FLAG}, which "
        "leaves the later uploads in place."
    ]


_LATER_UPLOAD_OUTCOMES = {
    LaterUploadOutcome.REMOVED: "removed everywhere",
    LaterUploadOutcome.WITHDRAWN_FROM_THE_PATH: (
        "withdrawn from this path only: another path still holds it, so its bytes stay"
    ),
    LaterUploadOutcome.KEPT_SHARED: (
        "KEPT: another holder has it too, and one camp path of a file cannot be withdrawn. To remove it for "
        "everyone, name it with --source and --include-shared"
    ),
    LaterUploadOutcome.LEFT_IN_PLACE: f"left in place ({ONLY_NAMED_FLAG})",
}


def _later_upload_lines(plan: RemovalPlan) -> list[str]:
    """The later uploads at the removed paths: by digest, caselist and snapshot, and what happens to each."""
    if not plan.later_uploads:
        return []
    digests = sorted({version.sha256 for version in plan.later_uploads})
    if plan.only_named:
        lines = [
            "",
            f"LATER UPLOADS AT A REMOVED PATH, LEFT IN PLACE ({ONLY_NAMED_FLAG}): {len(digests)} file(s)",
            "  The store holds each at a path this removal takes a named file from, in a later snapshot.",
            "  A removal request covers them unless it is explicitly about one version; without",
            f"  {ONLY_NAMED_FLAG} this plan would include them.",
        ]
    else:
        lines = [
            "",
            f"LATER UPLOADS AT A REMOVED PATH, ADDED TO THIS PLAN: {len(digests)} file(s)",
            "  The store holds each at a path this removal takes a named file from, in a snapshot dated",
            "  after the named file first appeared there (for a camp file: a higher OpenEv id at the same",
            "  camp path). The request covers them, so each goes through what a named file goes through.",
            f"  {ONLY_NAMED_FLAG} leaves them in place.",
        ]
    for number, digest in enumerate(digests, start=1):
        source = plan.source(digest)
        detail = _source_lines(number, source, plan) if source is not None else [f"  {number}. {digest}"]
        lines.append(detail[0])
        lines += [
            f"     later upload of {_sha256_label(version.of_sha256)} in {_where_held(version)}: "
            f"{_LATER_UPLOAD_OUTCOMES[plan.later_upload_outcome(version)]}"
            for version in plan.later_uploads
            if version.sha256 == digest
        ]
        lines += detail[1:]
    return lines


def _earlier_version_lines(plan: RemovalPlan) -> list[str]:
    """Earlier versions at the removed paths: listed for the operator, and nothing is done to them."""
    if not plan.earlier_versions:
        return []
    digests = sorted({version.sha256 for version in plan.earlier_versions})
    lines = [
        "",
        f"EARLIER VERSIONS AT A REMOVED PATH, NOT REMOVED: {len(digests)} file(s)",
        "  The store holds each at a path this removal takes a named file from, from before the named file",
        "  first appeared there. The request does not cover them and nothing is done to them. To remove",
        "  one, name it: --source <its sha256>.",
    ]
    for number, digest in enumerate(digests, start=1):
        lines.append(f"  {number}. {digest}")
        for version in plan.earlier_versions:
            if version.sha256 != digest:
                continue
            when = (
                "the same date as the named file's first snapshot, so which came first is not known"
                if version.relation is VersionRelation.SAME_DATE
                else "earlier"
            )
            lines.append(
                f"     at the path of {_sha256_label(version.of_sha256)} in {_where_held(version)}: {when}"
            )
    return lines


def _sha256_label(digest: str) -> str:
    """`sha256 <first 12 hex>`: how a file is named where its full digest is not needed."""
    return f"sha256 {digest[:12]}"


def _where_held(version: PathVersion) -> str:
    """The caselist and snapshots a version is held in. Never its path."""
    snapshots = ", ".join(version.snapshots)
    if not version.openev_ids:
        return f"{version.caselist}, held in {snapshots}"
    ids = ", ".join(f"openev-{one}" for one in version.openev_ids)
    matched = (
        "the delivery record puts both ids at one upstream path"
        if version.evidence is SamePathEvidence.UPSTREAM_PATH_DIGEST
        else "matched by file name alone: no delivery record here knows both ids, so check it"
    )
    return f"openev {snapshots} as {ids} ({matched})"


def _inbox_lines(plan: RemovalPlan) -> list[str]:
    """The download inbox: each file holding a removed file, and whether it is deleted or rewritten."""
    if not plan.inbox_exists:
        lines = [
            f"DOWNLOAD INBOX ({plan.inbox_directory}): does not exist, so there is nothing to check or "
            "change (an environment that has never pulled has none)."
        ]
    elif not plan.inbox:
        lines = [f"DOWNLOAD INBOX ({plan.inbox_directory}): nothing in it holds a removed file."]
    else:
        lines = [
            f"DOWNLOAD INBOX ({plan.inbox_directory}): {len(plan.inbox)} file(s) hold removed files. An",
            "archive still waiting to be imported is rewritten without them, never deleted.",
        ]
        lines += [_inbox_file_line(one) for one in plan.inbox]
    for left in plan.inbox_team_files_left:
        lines += [
            f"  NOTE {left.name}, waiting to be imported, holds {left.files} file(s) under this team's",
            "       directory that the store has never seen, so this removal cannot resolve them. Run",
            "       `caselist pull` to import it, then this same command again.",
        ]
    return lines


def _inbox_file_line(one: InboxFilePlan) -> str:
    noun = "entry" if one.entries_dropped == 1 else "entries"
    entries = f" ({one.entries_dropped} {noun} out, {one.entries_kept} kept)" if one.dropped else ""
    if one.action is InboxAction.UNREADABLE:
        return (
            f"  UNREADABLE {one.name}: {one.reason} ({one.detail}). Move it out of the inbox: the removal "
            "stops INCOMPLETE while it is there."
        )
    return f"  {one.action.value:8} {one.name}: {one.reason}{entries}"


def _source_lines(number: int, source: PlannedSource, plan: RemovalPlan) -> list[str]:
    size = (
        f"{source.source_format or 'unknown format'}, {source.byte_size} bytes"
        if source.byte_size
        else "not on this machine"
    )
    held = []
    if source.other_teams:
        held.append(f"{source.other_teams} other team(s)")
    if source.camp_file_holders:
        held.append(f"{source.camp_file_holders} camp file(s)")
    also = f"; also held by {' and '.join(held)}" if held else ""
    lines = [f"  {number}. {source.sha256}  ({size}{also})"]
    held_here = (
        source.disclosures
        or source.camp_files
        or source.local_blob
        or any(planned.sha256 == source.sha256 for planned in plan.objects)
    )
    if source.disposition is Disposition.REMOVE and not held_here:
        lines.append(
            "     held nowhere in this environment: it is only suppressed, so no import can bring it in"
        )
    if source.already_suppressed:
        lines.append("     already suppressed by this request: finishing what a previous run left")
    for ref in source.disclosures:
        lines.append(f"     record   {ref.caselist} {ref.snapshot.isoformat()}  {ref.source_path}")
    for camp_file in source.camp_files:
        lines.append(
            f"     record   openev {camp_file.year}-{camp_file.event.lower()}  "
            f"{camp_file.camp}: {camp_file.file_title}"
        )
    if source.disposition is Disposition.WITHDRAW:
        for caselist, path in source.requester_paths:
            lines.append(f"     withdraw {caselist}  {path}")
        if source.kept_in:
            lines.append(f"     kept in  {', '.join(source.kept_in)} (another team there still holds it)")
    for planned in plan.objects:
        if planned.sha256 != source.sha256:
            continue
        versions = (
            "versions not counted" if planned.versions is None else f"{len(planned.versions)} version(s)"
        )
        where = "this machine" if planned.side is Side.LOCAL else "bucket"
        lines.append(f"     {where:12} {planned.key}  ({versions})")
    return lines


def _confirmation(plan: RemovalPlan) -> list[str]:
    """Facts for the written confirmation: what went, in the requester's terms, and what did not."""
    removed = [*plan.of(Disposition.REMOVE), *plan.of(Disposition.WITHDRAW)]
    refs = [ref for source in removed for ref in source.disclosures]
    rounds = sorted(
        {f"{ref.tournament or 'no tournament named'}, {ref.round_label or 'no round named'}" for ref in refs}
    )
    snapshots = sorted({ref.snapshot for ref in refs})
    lines = [
        f"  - Removed from this environment: {len(_not_later_uploads(plan, Disposition.REMOVE))} file(s), "
        "and this team's copies of "
        f"{len(_not_later_uploads(plan, Disposition.WITHDRAW))} shared file(s)."
    ]
    if plan.later_uploads_added:
        lines.append(
            f"  - Also removed, as later uploads at the same path(s): {plan.later_uploads_added} file(s)."
        )
    elif plan.later_uploads and plan.only_named:
        lines.append(
            f"  - Not removed: {plan.later_uploads_found} later upload(s) at the same path(s), because the "
            "request was about one version."
        )
    if snapshots:
        lines.append(
            f"  - Disclosed in the {snapshots[0].isoformat()} to {snapshots[-1].isoformat()} weekly "
            "archives; "
            f"{len(rounds)} tournament round(s):"
        )
        lines += [f"      {item}" for item in rounds]
    shared = _not_later_uploads(plan, Disposition.WITHDRAW) + plan.of(Disposition.SKIP_SHARED)
    if shared:
        lines.append(
            f"  - Kept: {len(shared)} file(s) another team disclosed too or a camp released; say so, and why."
        )
    if plan.inbox:
        lines.append(
            f"  - Taken out of the download inbox on this machine: {len(plan.inbox)} downloaded file(s) "
            "held it."
        )
    lines += [
        "  - Suppressed, so next week's cumulative archive cannot bring any of it back.",
        f"  - Run in {plan.environment} only; the policy needs dev and prod both, dev first.",
        "  - Not done: the disclosure on OpenCaselist itself, which is the site's to remove.",
    ]
    return lines


def _describe(selector: RemovalSelector) -> str:
    return f"--source {selector.sha256}" if isinstance(selector, SourceSelector) else f"--team {selector}"


def _execute_command(plan: RemovalPlan) -> str:
    environment = plan.environment
    selector = (
        f"--source {plan.selector.sha256}"
        if isinstance(plan.selector, SourceSelector)
        else f"--team {shlex.quote(str(plan.selector))}"
    )
    flags = ["--execute"]
    if plan.only_named:
        flags.insert(0, ONLY_NAMED_FLAG)
    if plan.include_shared:
        flags.insert(0, "--include-shared")
    if environment == Environment.PROD.value:
        flags.append(CONFIRM_PROD_FLAG)
    return (
        f"DEBATE_ENV={environment} DEBATE_REMOVAL_PROFILE=debate-{environment}-evidence-removal "
        f"debate-research caselist remove {selector} --request {plan.request_id} --reason {plan.reason} "
        f"{' '.join(flags)}"
    )


# ------------------------------------------------------------------------------------------------
# The plan, for a program
# ------------------------------------------------------------------------------------------------


def plan_summary(plan: RemovalPlan, settings: Settings, report: RemovalReport | None) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`: the whole plan, and the outcome when it was executed.

    No school, team code, path, camp, title or file name: see "What is printed and what is not" in
    the module docstring. The text of the plan is where the operator reads those.
    """
    data: dict[str, JsonValue] = {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "applied": report is not None,
        "request_id": plan.request_id,
        "reason": str(plan.reason),
        "selector": _selector_json(plan.selector),
        "include_shared": plan.include_shared,
        "only_named": plan.only_named,
        "versions_counted": plan.versions_counted,
        "sources": [_source_json(source) for source in plan.sources],
        "later_uploads": [
            {**_version_json(version), "outcome": plan.later_upload_outcome(version).value}
            for version in plan.later_uploads
        ],
        "later_uploads_added": plan.later_uploads_added,
        "earlier_versions": [_version_json(version) for version in plan.earlier_versions],
        "manifests": [
            {
                "key": rewrite.key,
                "side": rewrite.side.value,
                "rows_dropped": rewrite.rows_dropped,
                "versions": rewrite.versions,
            }
            for rewrite in plan.manifests
        ],
        "objects": [
            {
                "key": planned.key,
                "side": planned.side.value,
                "kind": planned.kind.value,
                "sha256": planned.sha256,
                "versions": None if planned.versions is None else len(planned.versions),
            }
            for planned in plan.objects
        ],
        "suppression_entries": [entry.to_line() for entry in plan.suppression_entries],
        "inbox_directory": plan.inbox_directory,
        "inbox_exists": plan.inbox_exists,
        "inbox": [
            {
                "name": one.label,
                "kind": one.kind.value,
                "sha256": one.sha256,
                "action": one.action.value,
                "reason": str(one.reason),
                "removed_sha256": list(one.removed_sha256),
                "entries_dropped": one.entries_dropped,
                "entries_kept": one.entries_kept,
            }
            for one in plan.inbox
        ],
        "inbox_team_files_left": [
            {"name": left.name, "files": left.files} for left in plan.inbox_team_files_left
        ],
        "counts": {
            "remove": len(plan.of(Disposition.REMOVE)),
            "withdraw": len(plan.of(Disposition.WITHDRAW)),
            "skip_shared": len(plan.of(Disposition.SKIP_SHARED)),
            "local_records": plan.local_records,
        },
    }
    if report is not None:
        data["outcome"] = str(report.log_entry.outcome)
        data["log_entry"] = report.log_entry.to_line()
    return data


def _selector_json(selector: RemovalSelector) -> dict[str, JsonValue]:
    """A file by its digest; a team by its caselist alone, since the rest of it is a school and a code."""
    if isinstance(selector, SourceSelector):
        return {"kind": str(selector.kind), "sha256": selector.sha256}
    return {"kind": str(selector.kind), "caselist": selector.caselist}


def _version_json(version: PathVersion) -> dict[str, JsonValue]:
    """One later upload or earlier version: its digest, its caselist and its snapshots. Never its path."""
    return {
        "sha256": version.sha256,
        "sha256_prefix": version.sha256[:12],
        "relation": version.relation.value,
        "of_sha256": version.of_sha256,
        "caselist": version.caselist,
        "snapshots": list(version.snapshots),
        "openev_ids": list(version.openev_ids),
        "same_path_by": version.evidence.value,
    }


def _source_json(source: PlannedSource) -> dict[str, JsonValue]:
    return {
        "sha256": source.sha256,
        "inclusion": source.inclusion.value,
        "disposition": source.disposition.value,
        "byte_size": source.byte_size,
        "format": source.source_format,
        "other_teams": source.other_teams,
        "camp_file_holders": source.camp_file_holders,
        "kept_in": list(source.kept_in),
        "already_suppressed": source.already_suppressed,
        "disclosures": [
            {
                "caselist": ref.caselist,
                "snapshot": ref.snapshot.isoformat(),
                "disclosure": disclosure_digest(ref.caselist, ref.source_path),
            }
            for ref in source.disclosures
        ],
        "camp_files": [{"year": camp.year, "event": str(camp.event)} for camp in source.camp_files],
        "withdrawn_disclosures": [
            {"caselist": caselist, "disclosure": disclosure_digest(caselist, path)}
            for caselist, path in source.requester_paths
        ],
        "local_blob": source.local_blob,
        "deletes_source_record": source.delete_source_record,
    }


# ------------------------------------------------------------------------------------------------
# unsuppress
# ------------------------------------------------------------------------------------------------


def render_unsuppress(plan: UnsuppressPlan, report: UnsuppressReport | None) -> str:
    scopes = []
    if plan.whole_source:
        scopes.append("the whole file")
    if plan.disclosures:
        scopes.append(f"{plan.disclosures} withdrawn disclosure(s)")
    head = (
        f"DRY RUN: nothing was changed. {plan.environment}."
        if report is None
        else f"DONE in {plan.environment}: the un-suppress entry and a removal-log entry were appended."
    )
    lines = [
        head,
        f"{plan.sha256} is suppressed now ({', '.join(scopes)}), "
        f"by {plan.previous.request_id or 'no request id'}"
        f" ({plan.previous.reason}).",
        "",
        "UN-SUPPRESS ENTRY appended to the list, here and in the bucket:",
        f"  {plan.entry.to_line()}",
        "",
        "The next import of an archive that holds the file stores it again. Nothing purged is restored.",
    ]
    if report is None:
        request = f" --request {plan.request_id}" if plan.request_id else ""
        confirm = f" {CONFIRM_PROD_FLAG}" if plan.environment == Environment.PROD.value else ""
        lines += [
            "",
            "TO CARRY IT OUT",
            f"  DEBATE_ENV={plan.environment} "
            f"DEBATE_REMOVAL_PROFILE=debate-{plan.environment}-evidence-removal "
            f"debate-research caselist unsuppress --sha256 {plan.sha256} --reason {plan.reason}{request} "
            f"--execute{confirm}",
        ]
    return "\n".join(lines)


def unsuppress_summary(
    plan: UnsuppressPlan, settings: Settings, report: UnsuppressReport | None
) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = {
        "environment": settings.environment.value,
        "applied": report is not None,
        "sha256": plan.sha256,
        "reason": str(plan.reason),
        "request_id": plan.request_id,
        "whole_source": plan.whole_source,
        "disclosures": plan.disclosures,
        "entry": plan.entry.to_line(),
    }
    if report is not None:
        data["log_entry"] = report.log_entry.to_line()
    return data


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)

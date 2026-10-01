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
it: what will be removed, what is shared and therefore kept, the manifests that will be rewritten,
the suppression entries exactly as they will be appended, and a paragraph of facts for the
confirmation to the requester, then the exact command that executes it.

`--execute` needs the takedown profile (`DEBATE_REMOVAL_PROFILE`) and, in prod, `--confirm-prod`.

## What is printed and what is not

The plan names the team's paths, school and team code: this is the operator's own terminal, and
checking the plan against the request is the point of the dry run. Nothing here *logs* them, and
the removal log and the suppression list cannot hold them (`debate_core.application.ports.
suppression`).

## Exit codes

`0` for a dry run and for a completed execution. `1` for a refusal (a malformed selector, a missing
`--execute` guard, an unset or refused takedown profile — all before anything changes) and for a run
that stopped part-way, whose message says to re-run the same command.
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
from debate_core.application.caselist.removal_plan import (
    Disposition,
    InvalidRemovalRequest,
    PlannedSource,
    RemovalPlan,
    RemovalSelector,
    Side,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.caselist.removal_service import RemovalReport, UnsuppressPlan, UnsuppressReport
from debate_core.application.ports.suppression import REINSTATEMENT_REASONS, REMOVAL_REASONS, ReasonCode
from debate_core.application.settings import Environment, Settings

__all__ = ["plan_summary", "remove", "unsuppress"]

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
    plan = _run(service.plan(selector, request_id=request, reason=code, include_shared=include_shared))
    if not execute:
        cli.output.success(
            command_name(ctx), plan_summary(plan, settings, None), display=render_plan(plan, None)
        )
        return
    cli.output.detail("executing under the takedown profile")
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
    removed, withdrawn, skipped = (
        plan.of(Disposition.REMOVE),
        plan.of(Disposition.WITHDRAW),
        plan.of(Disposition.SKIP_SHARED),
    )
    if report is None:
        lines.append(f"DRY RUN: nothing was changed. {plan.environment}, bucket {plan.bucket}.")
    else:
        lines.append(
            f"DONE in {plan.environment} ({plan.bucket}): {report.local_records_deleted} record(s), "
            f"{report.local_files_deleted} local file(s), {report.s3_versions_deleted} bucket object "
            f"version(s) deleted; {report.manifests_rewritten} manifest(s) rewritten without "
            f"{report.manifest_rows_dropped} row(s)."
        )
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

    if plan.manifests:
        lines += ["", f"MANIFESTS REWRITTEN without the rows that name it: {len(plan.manifests)}"]
        for rewrite in plan.manifests:
            versions = "" if rewrite.versions is None else f", {rewrite.versions} version(s) replaced by one"
            lines.append(f"  {rewrite.side.value:6} {rewrite.key}  -{rewrite.rows_dropped} row(s){versions}")

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
        lines += ["", "TO CARRY IT OUT", f"  {_execute_command(plan)}"]
    return "\n".join(lines)


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
        f"  - Removed from this environment: {len(plan.of(Disposition.REMOVE))} file(s), and this team's "
        "copies of "
        f"{len(plan.of(Disposition.WITHDRAW))} shared file(s)."
    ]
    if snapshots:
        lines.append(
            f"  - Disclosed in the {snapshots[0].isoformat()} to {snapshots[-1].isoformat()} weekly "
            "archives; "
            f"{len(rounds)} tournament round(s):"
        )
        lines += [f"      {item}" for item in rounds]
    shared = plan.of(Disposition.WITHDRAW) + plan.of(Disposition.SKIP_SHARED)
    if shared:
        lines.append(
            f"  - Kept: {len(shared)} file(s) another team disclosed too or a camp released; say so, and why."
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
    """The `--json` envelope's `data`: the whole plan, and the outcome when it was executed."""
    data: dict[str, JsonValue] = {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "applied": report is not None,
        "request_id": plan.request_id,
        "reason": str(plan.reason),
        "selector": {"kind": str(plan.selector.kind), "value": _selector_value(plan.selector)},
        "include_shared": plan.include_shared,
        "versions_counted": plan.versions_counted,
        "sources": [_source_json(source) for source in plan.sources],
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


def _selector_value(selector: RemovalSelector) -> str:
    return selector.sha256 if isinstance(selector, SourceSelector) else str(selector)


def _source_json(source: PlannedSource) -> dict[str, JsonValue]:
    return {
        "sha256": source.sha256,
        "disposition": source.disposition.value,
        "byte_size": source.byte_size,
        "format": source.source_format,
        "other_teams": source.other_teams,
        "camp_file_holders": source.camp_file_holders,
        "kept_in": list(source.kept_in),
        "already_suppressed": source.already_suppressed,
        "disclosures": [
            {"caselist": ref.caselist, "snapshot": ref.snapshot.isoformat(), "path": ref.source_path}
            for ref in source.disclosures
        ],
        "camp_files": [
            {"year": camp.year, "event": str(camp.event), "camp": camp.camp, "title": camp.file_title}
            for camp in source.camp_files
        ],
        "withdrawn_paths": [path for _, path in source.requester_paths],
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

"""`debate-research store sync | ls | get`: moving evidence between this machine and the bucket.

Three commands over one service. Every decision — what differs, what may be written, what is
verified, what a resumed run may skip — is
:class:`~debate_core.application.evidence_sync.EvidenceSyncService`'s, in `debate_core`. What is
here is the part that is genuinely a command-line surface: which flags mean what, which run needs
a second pair of eyes before it happens, how a plan is rendered, and which exit code a failure
ends with (architecture proposal §6, §11).

## Nothing is written unless you ask

`store sync` **plans by default**. It lists both sides, prints what it would do, and stops. Adding
`--apply` is what makes it transfer anything, and pushing to prod needs `--confirm-prod` on top of
that. That is the opposite of the usual default and it is deliberate: this command's whole job is
to write to the team's system of record, the local store is whatever happens to be on one
person's laptop, and the cheapest moment to notice that it is not what you thought is before the
upload rather than after it.

::

    debate-research store sync                                  # what would change, in dev
    debate-research store sync --apply                          # do it
    DEBATE_ENV=prod debate-research store sync --apply --confirm-prod
    debate-research store sync --prefix manifests/hsld26/       # one part of the store
    debate-research store sync --blob-prefix raw/caselist/hsld26 --apply   # the corpus itself
    debate-research store sync --pull --apply                   # bucket to laptop

## Which bucket

`DEBATE_ENV` and nothing else. `dev` and `prod` name different buckets and different SSO profiles
in their profile files (`config/profiles/<env>.toml`, from the environment root's Terraform
outputs), and `test` names no bucket at all, so a test environment cannot reach a real store —
it is refused rather than defaulted. No flag overrides the bucket: a command that could be
pointed at prod by a typo in an argument would be a command that eventually is.

## Exit codes

From :mod:`debate_cli.exit_codes`, and no new numbers. `0` when the run did what it was asked;
`1` when the answer is a failure the operator has to deal with — an object that would not verify,
a content-addressed key whose two sides disagree, an environment with no bucket, a prod push with
no `--confirm-prod`; `3` when a provider failed. An expired SSO session arrives as
:class:`~debate_core.application.errors.StoreCredentialsExpired`, which carries the `aws sso
login --profile …` line the adapter built, and the root group renders that as the hint on a
one-line failure rather than a traceback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Annotated, Any

import typer

from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.evidence_sync import (
    SyncAction,
    SyncDirection,
    SyncPlan,
    SyncReport,
)
from debate_core.application.settings import Environment, Settings

__all__ = ["get", "ls", "sync"]

#: The environments that name a real bucket. `test` is deliberately not one of them.
SYNCABLE_ENVIRONMENTS = (Environment.DEV, Environment.PROD)

#: Confirmation a push to production needs, spelled the way the rest of the CLI spells one.
CONFIRM_PROD_FLAG = "--confirm-prod"


def sync(
    ctx: typer.Context,
    prefix: Annotated[
        str,
        typer.Option(
            "--prefix",
            help="Only objects whose bucket key starts with this, e.g. manifests/hsld26/.",
        ),
    ] = "",
    blob_prefix: Annotated[
        str,
        typer.Option(
            "--blob-prefix",
            help=(
                "Where the local content-addressed store belongs in the bucket, "
                "e.g. raw/caselist/hsld26. Required when there are blobs to move."
            ),
        ),
    ] = "",
    pull: Annotated[
        bool,
        typer.Option("--pull", help="Bring the bucket down to this machine instead of publishing."),
    ] = False,
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Actually transfer. The default plans and changes nothing.",
        ),
    ] = False,
    confirm_prod: Annotated[
        bool,
        typer.Option(CONFIRM_PROD_FLAG, help="Required to write to the production evidence bucket."),
    ] = False,
) -> None:
    """Compare the local evidence store with this environment's bucket, and optionally transfer."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    direction = SyncDirection.PULL if pull else SyncDirection.PUSH
    _refuse(
        cli,
        ctx,
        _no_bucket_to_sync_with(settings, applying=apply_changes)
        or _unconfirmed_production_write(settings, direction, applying=apply_changes, confirmed=confirm_prod),
    )

    service = cli.services.evidence_sync(blob_prefix=blob_prefix or None)
    cli.output.detail(f"listing {settings.storage.s3.bucket} and {settings.storage.data_dir}")
    plan = _run(service.plan(prefix=prefix, direction=direction))

    if not apply_changes:
        report = SyncReport(plan=plan, applied=False)
    else:
        cli.output.detail(f"transferring {len(plan.transfers)} object(s)")
        report = _run(service.execute(plan))

    payload = sync_report(report, settings)
    if report.succeeded:
        cli.output.success(command_name(ctx), payload, display=_sync_table(report, settings))
        return

    # A failed run reports the *failure* envelope, so that `status`, `error.code` and the exit
    # code agree with each other for the scheduled consumer; the whole payload rides along in
    # `error.details` so that nothing a successful run would have told it is lost. A person still
    # gets the table, because the counts are most of what they came for.
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_sync_table(report, settings))
    cli.output.failure(_sync_failure(report, payload), command=command_name(ctx))
    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)


def ls(
    ctx: typer.Context,
    prefix: Annotated[
        str,
        typer.Argument(help="Bucket key prefix to list. Omit for every documented prefix."),
    ] = "",
) -> None:
    """List what this environment's evidence bucket holds under a prefix."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    _refuse(cli, ctx, _no_bucket_to_sync_with(settings, applying=False))

    service = cli.services.evidence_sync()
    objects = _run(service.list_remote(prefix))
    rows = [[info.key, _bytes(info.size)] for info in objects]
    cli.output.success(
        command_name(ctx),
        {
            "environment": settings.environment.value,
            "bucket": settings.storage.s3.bucket,
            "prefix": prefix,
            "count": len(objects),
            "bytes": sum(info.size for info in objects),
            "objects": [{"key": info.key, "size": info.size} for info in objects],
        },
        display=TableSpec(
            columns=("Key", "Size"),
            rows=rows,
            title=f"{settings.storage.s3.bucket} {prefix or '(every documented prefix)'}",
            caption=f"{len(objects)} object(s), {_bytes(sum(info.size for info in objects))}",
        ),
    )


def get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The object's key in the bucket.")],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Where to write it. The default is its place in the local evidence store.",
        ),
    ] = None,
) -> None:
    """Download one object from this environment's evidence bucket, verifying it on the way in."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    _refuse(cli, ctx, _no_bucket_to_sync_with(settings, applying=False))

    service = cli.services.evidence_sync(blob_prefix=_corpus_prefix_of(key))
    landed = _run(service.fetch(key, output))
    destination = output if output is not None else settings.storage.data_dir
    cli.output.success(
        command_name(ctx),
        {
            "environment": settings.environment.value,
            "bucket": settings.storage.s3.bucket,
            "key": key,
            "sha256": landed.sha256,
            "destination": str(destination),
        },
        display=f"{key} -> {destination}",
    )


# ------------------------------------------------------------------------------------------------
# The guards
# ------------------------------------------------------------------------------------------------


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    """Report `refusal` and end the run, or return so the command can get on with it.

    A guard declining to run is an *outcome*, not an exception: nothing in `debate_core` failed,
    the command-line surface decided not to start. So it is reported through
    :meth:`~debate_cli.output.CliOutput.failure` and exited with a code from
    :mod:`debate_cli.exit_codes`, which is the pattern :mod:`debate_cli.app` documents for
    exactly this case.
    """
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


def _no_bucket_to_sync_with(settings: Settings, *, applying: bool) -> CommandFailure | None:
    """A write needs a real environment; even a read needs a bucket to read from.

    Reading under `test` is refused for the same reason writing is: the test environment names no
    bucket, so there is nothing to read, and reporting "0 objects" would be a lie that looks like
    a clean run.
    """
    if applying and settings.environment not in SYNCABLE_ENVIRONMENTS:
        return CommandFailure(
            code="ENVIRONMENT_NOT_SYNCABLE",
            message=f"`store sync --apply` runs against dev or prod, not {settings.environment.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev (or prod) and try again.",
        )
    if not settings.storage.s3.bucket:
        # The container refuses the same thing when it builds the service; this one is here so
        # that the message names the command rather than the wiring.
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"the {settings.environment.value} environment names no evidence bucket",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV to dev or prod, or set storage.s3.bucket for this environment.",
        )
    return None


def _unconfirmed_production_write(
    settings: Settings, direction: SyncDirection, *, applying: bool, confirmed: bool
) -> CommandFailure | None:
    """Writing to the production bucket is the one thing this CLI asks twice about.

    Only a push: pulling prod down to a laptop writes nothing to the team's evidence, and a dry
    run writes nothing anywhere, so neither has anything to confirm.
    """
    if not applying or direction is not SyncDirection.PUSH:
        return None
    if settings.environment is not Environment.PROD or confirmed:
        return None
    return CommandFailure(
        code="CONFIRMATION_REQUIRED",
        message=(
            "refusing to write to the production evidence bucket without "
            f"{CONFIRM_PROD_FLAG}: {settings.storage.s3.bucket}"
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"environment": settings.environment.value, "bucket": settings.storage.s3.bucket},
        hint=f"Re-run with {CONFIRM_PROD_FLAG} once you have read the plan.",
    )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------


def sync_report(report: SyncReport, settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `store sync`.

    The shape the scheduled caselist sync (`v1-e34-t02`) reads, so it is written for a program
    first: every action has a count and a byte total whether or not it happened, `applied` says
    whether anything moved, and `failed` is a list of objects rather than a sentence to parse.
    """
    plan = report.plan
    return {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "direction": plan.direction.value,
        "prefix": plan.prefix,
        "applied": report.applied,
        "counts": dict(plan.counts),
        "bytes": dict(plan.byte_counts),
        "remote_head_requests": plan.remote_head_requests,
        "transferred": len(report.transferred),
        "bytes_transferred": report.bytes_transferred,
        "failed": [
            {
                "key": outcome.key,
                "code": outcome.error_code,
                "message": outcome.error_message,
            }
            for outcome in report.failed
        ],
        "mismatched": [planned.remote_key for planned in plan.of(SyncAction.MISMATCHED)],
        "journal": str(report.journal_path) if report.journal_path is not None else None,
    }


def _sync_table(report: SyncReport, settings: Settings) -> TableSpec:
    """One row per action, with what it would move and what it did."""
    plan = report.plan
    rows = [
        [action.value, str(plan.count(action)), _bytes(plan.bytes_for(action))]
        for action in SyncAction
        if plan.count(action) or action in (SyncAction.NEW, SyncAction.CHANGED, SyncAction.SKIPPED)
    ]
    return TableSpec(
        columns=("Action", "Objects", "Bytes"),
        rows=rows,
        title=(
            f"{plan.direction.value} {settings.environment.value} "
            f"{'->' if plan.direction is SyncDirection.PUSH else '<-'} "
            f"{settings.storage.s3.bucket}{_filtered(plan)}"
        ),
        caption=_caption(report),
    )


def _caption(report: SyncReport) -> str:
    if not report.applied:
        return (
            f"Planned only; nothing was transferred. {report.plan.remote_head_requests} head "
            "request(s). Re-run with --apply to move it."
        )
    moved = f"{len(report.transferred)} object(s) transferred, {_bytes(report.bytes_transferred)}"
    if report.failed:
        return f"{moved}; {len(report.failed)} failed."
    return f"{moved}, each verified at the destination."


def _filtered(plan: SyncPlan) -> str:
    return f" under {plan.prefix}" if plan.prefix else ""


def _sync_failure(report: SyncReport, payload: dict[str, JsonValue]) -> CommandFailure:
    """What a run that could not verify everything reports, and exits `1` with.

    `payload` is the same object a successful run puts under `data`, carried in `details` so that
    a consumer reading a failed run still gets every count, the journal path and the list of what
    failed — the things it needs in order to decide whether to re-run.
    """
    mismatched = report.plan.of(SyncAction.MISMATCHED)
    if report.failed:
        first = report.failed[0]
        return CommandFailure(
            code=first.error_code or "SYNC_FAILED",
            message=(
                f"{len(report.failed)} object(s) could not be transferred and verified; "
                f"the first was {first.key}"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={**payload, "first_key": first.key},
            hint="Re-run the same command: everything that did verify is journaled and is skipped.",
        )
    return CommandFailure(
        code="BLOB_INTEGRITY_ERROR",
        message=(
            f"{len(mismatched)} content-addressed object(s) differ between the two stores and "
            "were left untouched; the first was " + mismatched[0].remote_key
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={**payload, "first_key": mismatched[0].remote_key},
        hint=(
            "A key that is the digest of its own bytes cannot hold two things. Nothing was "
            "overwritten; this needs a person (docs/guides/evidence-store-cli.md)."
        ),
    )


def _corpus_prefix_of(key: str) -> str | None:
    """The corpus prefix a content-addressed key sits under, so `get` can place it locally.

    `raw/caselist/hsld26/sha256/ab/cd/abcd…` is under `raw/caselist/hsld26`. A key with no
    `sha256/` segment is a named object and needs no prefix.
    """
    head, segment, _ = key.partition("sha256/")
    return head.rstrip("/") if segment else None


def _bytes(count: int) -> str:
    """A byte count as an operator reads it in a summary: `18.4 MB`, `912 B`."""
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")  # pragma: no cover


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion.

    The services are `async` because their adapters are I/O-bound and the API and the workers will
    await them; a CLI command is the one caller with no event loop of its own, so it starts one for
    the duration of the command. `asyncio.run` rather than a loop kept between commands: a
    `debate-research` process runs one command and exits.
    """
    return asyncio.run(awaitable)

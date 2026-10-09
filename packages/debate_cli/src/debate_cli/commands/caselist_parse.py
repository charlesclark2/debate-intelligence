"""`debate-research caselist parse`: imported sources into the parsed card store.

::

    debate-research caselist parse --caselist hsld26
    debate-research caselist parse --caselist hsld26 --snapshot 2026-09-15
    debate-research caselist parse --caselist hsld26 --dry-run
    debate-research caselist parse --caselist hsld26 --publish
    debate-research caselist parse --caselist openev --reparse
    debate-research caselist parse --caselist hsld26 --failures

Every decision is :class:`~debate_core.application.caselist_parse.CaselistParseService`'s and
:class:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher`'s
(`v1-e31-t06-parse-pipeline`); this is the guards and the rendering. The store's layout is
`docs/data/parsed-card-store.md`.

## Exit code

0 unless the share of the sources this run tried to read that failed is above
`parse.failure_rate_threshold` (`PARSE_FAILURE_RATE_EXCEEDED`), or a `--publish` left something
unconfirmed in the bucket (`PARSED_PUBLISH_INCOMPLETE`). A PDF or a legacy `.doc` is an outcome,
not a failure, and counts on neither side of the rate.

## `--publish`

The same guards as `caselist publish`: dev or prod only, and prod only with `--confirm-prod`. The
store is parsed first, here, then the current version directory is copied to the bucket.

## `--failures`

Lists the sources of the current version directory that did not parse, by SHA-256 prefix and the
path the manifests disclose them at. Those paths name schools and team codes: the listing is for the
operator's terminal, and its `--json` says so in a `notice`. Nothing else this command prints names
a path, a school, a team code or a word of a card.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Final

import typer

from debate_cli.commands.caselist import (
    _no_bucket,  # pyright: ignore[reportPrivateUsage]
    _refuse,  # pyright: ignore[reportPrivateUsage]
    _unconfirmed_production_write,  # pyright: ignore[reportPrivateUsage]
)
from debate_cli.commands.store import CONFIRM_PROD_FLAG
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode, TableSpec
from debate_core.application.caselist.parsed_publish import ParsedPublishReport
from debate_core.application.caselist.publish_plan import validate_publish_target
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist_parse import FailureListing, ParseRunReport
from debate_core.application.settings import Settings
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = ["failures_summary", "parse", "parse_summary"]

FAILURES_NOTICE: Final = (
    "Contains disclosure paths, which name schools and team codes. For this terminal only: never "
    "paste it into a report, a document, an issue or a commit (docs/policies/caselist-data-use.md)."
)


def parse(
    ctx: typer.Context,
    caselist: Annotated[
        str, typer.Option("--caselist", help="Caselist slug to parse, e.g. hsld26, or openev for camp files.")
    ],
    snapshot: Annotated[
        str | None,
        typer.Option("--snapshot", help="Parse only this snapshot's sources: YYYY-MM-DD, or <year>-<event>."),
    ] = None,
    publish: Annotated[
        bool, typer.Option("--publish", help="Then copy the store to this environment's evidence bucket.")
    ] = False,
    reparse: Annotated[
        bool, typer.Option("--reparse", help="Parse everything again, into a new version directory.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Count what would be parsed and write nothing.")
    ] = False,
    failures: Annotated[
        bool, typer.Option("--failures", help="List the sources that did not parse, with their paths.")
    ] = False,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required to publish to the production evidence bucket.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Parse imported caselist or camp sources into the parsed card store, skipping what is parsed."""
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    validate_publish_target(caselist, snapshot)
    if failures:
        listing = asyncio.run(cli.services.caselist_parse(with_bucket=False).failures(caselist))
        cli.output.success(command_name(ctx), failures_summary(listing), display=_failures_table(listing))
        return
    settings = cli.services.settings
    writing = publish and not dry_run
    _refuse(
        cli,
        ctx,
        (_no_bucket(settings, writing=True) if writing else None)
        or _unconfirmed_production_write(settings, writing=writing, confirmed=confirm_prod),
    )
    service = cli.services.caselist_parse(with_bucket=writing)
    plan = asyncio.run(service.plan(caselist, snapshot=snapshot, reparse=reparse))
    report = service.dry_run(plan) if dry_run else asyncio.run(service.run(plan))
    published = (
        asyncio.run(cli.services.parsed_publisher().publish(caselist, plan.version)) if writing else None
    )
    payload = parse_summary(report, published, settings)
    failure = _failure(report, published, payload)
    if failure is None or not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_parse_table(report, published, settings))
    if failure is not None:
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code)


# ------------------------------------------------------------------------------------------------
# Rendering: counts, versions and digests only
# ------------------------------------------------------------------------------------------------


def parse_summary(
    report: ParseRunReport, published: ParsedPublishReport | None, settings: Settings
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`. Counts, versions, digests and keys: never a path or a name."""
    plan = report.plan
    store = report.store
    return {
        "environment": settings.environment.value,
        "caselist": plan.caselist,
        "snapshot": plan.snapshot,
        "applied": report.applied,
        "version": plan.version,
        "new_version": plan.new_version,
        "superseded": plan.superseded,
        "parser_version": plan.parser_version,
        "profile_version": plan.profile_version,
        "fingerprint_version": FINGERPRINT_VERSION,
        "workers": report.workers,
        "sources": plan.in_scope,
        "skipped": plan.skipped,
        "suppressed": plan.suppressed,
        "to_parse": len(plan.to_parse),
        "attempted": report.attempted,
        "parsed": report.parsed,
        "cards": report.cards,
        "unsupported": dict(report.unsupported),
        "failed": dict(report.failed),
        "failure_rate": round(report.failure_rate, 4),
        "failure_rate_threshold": report.threshold,
        "threshold_exceeded": report.exceeds_threshold,
        "store": None
        if store is None
        else {
            "sources": store.sources,
            "parsed": store.parsed,
            "unsupported": store.unsupported,
            "failed": store.failed,
            "cards": store.cards,
            "occurrences": store.occurrences,
            "clusters": store.clusters,
        },
        "elapsed_seconds": round(report.elapsed_seconds, 1),
        "publish": None if published is None else _publish_summary(published, settings),
    }


def _publish_summary(published: ParsedPublishReport, settings: Settings) -> dict[str, JsonValue]:
    return {
        "bucket": settings.storage.s3.bucket,
        "prefix": published.prefix,
        "counts": {result.value: published.count(result) for result in SourceResult},
        "aggregates": "withheld" if published.aggregates_withheld else "published",
        "failed_keys": list(published.failed_keys),
    }


def failures_summary(listing: FailureListing) -> dict[str, JsonValue]:
    """`--failures --json`: every failing source with its path, and a notice saying it has paths."""
    return {
        "caselist": listing.caselist,
        "version": listing.version,
        "present": listing.present,
        "contains_disclosure_paths": True,
        "notice": FAILURES_NOTICE,
        "failures": [
            {
                "sha256": row.sha256,
                "path": row.path,
                "snapshot": row.snapshot,
                "format": row.source_format,
                "reason": row.reason,
                "detail": row.detail,
                "counts_toward_failure_rate": row.counts_toward_failure_rate,
            }
            for row in listing.rows
        ],
    }


def _failure(
    report: ParseRunReport, published: ParsedPublishReport | None, payload: dict[str, JsonValue]
) -> CommandFailure | None:
    if report.exceeds_threshold:
        return CommandFailure(
            code="PARSE_FAILURE_RATE_EXCEEDED",
            message=(
                f"{sum(report.failed.values())} of the {report.attempted - sum(report.unsupported.values())} "
                f"source(s) this run tried to read failed ({report.failure_rate:.1%}), above the "
                f"{report.threshold:.1%} threshold"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint="`caselist parse --failures` lists them; parse.failure_rate_threshold sets the threshold.",
        )
    if published is not None and not published.succeeded:
        return CommandFailure(
            code="PARSED_PUBLISH_INCOMPLETE",
            message=(
                f"{len(published.failed_keys)} object(s) not confirmed in the bucket"
                + ("; the aggregates were withheld" if published.aggregates_withheld else "")
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint="Run it again to retry; a checksum mismatch needs a person.",
        )
    return None


def _parse_table(
    report: ParseRunReport, published: ParsedPublishReport | None, settings: Settings
) -> TableSpec:
    plan = report.plan
    store = report.store
    rows = [
        ["Version", plan.version + (f" (new; {plan.superseded} left as it was)" if plan.new_version else "")],
        ["Sources", str(plan.in_scope)],
        ["Skipped (already parsed)", str(plan.skipped)],
        ["Suppressed", str(plan.suppressed)],
        [
            "Parsed" if report.applied else "To parse",
            str(report.parsed if report.applied else len(plan.to_parse)),
        ],
    ]
    if report.applied:
        rows += [
            ["Cards parsed", str(report.cards)],
            ["Unsupported", _counts(report.unsupported)],
            ["Failed", _counts(report.failed)],
            ["Failure rate", f"{report.failure_rate:.1%} (threshold {report.threshold:.1%})"],
        ]
    if store is not None:
        rows += [
            ["Store", f"{store.sources} sources, {store.cards} cards, {store.clusters} clusters"],
            ["Occurrences", str(store.occurrences)],
        ]
    if published is not None:
        rows.append(["Published", _published(published, settings)])
    caption = (
        "Dry run: nothing was parsed or written."
        if not report.applied
        else f"{report.elapsed_seconds:.1f} s with {report.workers} worker(s)."
    )
    return TableSpec(
        columns=("", plan.caselist), rows=rows, title=f"caselist parse {plan.caselist}", caption=caption
    )


def _failures_table(listing: FailureListing) -> TableSpec:
    if not listing.present:
        return TableSpec(
            columns=("sha256", "Path", "Reason"),
            rows=[],
            title=f"{listing.caselist}: no failures file",
            caption="Not parsed yet, or a removal deleted it: run `caselist parse` to rebuild it.",
        )
    rows = [
        [
            row.sha256_prefix,
            row.path or "-",
            row.snapshot,
            row.source_format,
            row.reason,
            "yes" if row.counts_toward_failure_rate else "no",
        ]
        for row in listing.rows
    ]
    return TableSpec(
        columns=("sha256", "Path", "Parsed under", "Format", "Reason", "Counts"),
        rows=rows,
        title=f"{listing.caselist} {listing.version}: {len(rows)} source(s) with no document",
        caption=FAILURES_NOTICE,
    )


def _counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {count}" for name, count in counts.items()) or "0"


def _published(published: ParsedPublishReport, settings: Settings) -> str:
    return (
        f"{published.count(SourceResult.UPLOADED)} uploaded, "
        f"{published.count(SourceResult.SKIPPED)} skipped, "
        f"{len(published.failed_keys)} failed to {settings.storage.s3.bucket}/{published.prefix}"
    )

"""`debate-research caselist parse`: imported sources into the parsed card store.

::

    debate-research caselist parse --caselist hsld26
    debate-research caselist parse --caselist hsld26 --snapshot 2026-09-15
    debate-research caselist parse --caselist hsld26 --dry-run
    debate-research caselist parse --caselist hsld26 --publish
    debate-research caselist parse --caselist hsld26 --publish-only --dry-run
    debate-research caselist parse --caselist hsld26 --publish-only
    debate-research caselist parse --caselist openev --reparse
    debate-research caselist parse --caselist hsld26 --failures

Every decision is :class:`~debate_core.application.caselist_parse.CaselistParseService`'s and
:class:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher`'s
(`v1-e31-t06-parse-pipeline`); this is the guards and the rendering. The store's layout is
`docs/data/parsed-card-store.md`.

## Exit code

0 unless the share of the sources this run tried to read that failed is above
`parse.failure_rate_threshold` (`PARSE_FAILURE_RATE_EXCEEDED`, exit `1`), or a `--publish` or
`--publish-only` left something unconfirmed in the bucket (`PARSED_PUBLISH_INCOMPLETE`). A PDF or a
legacy `.doc` is an outcome, not a failure, and counts on neither side of the rate.

The rate is judged only in a run that tried at least `parse.failure_rate_minimum_sources` sources
(`v1-e34-t17`). A smaller run reports its failures, says `failure_rate_judged: false`, and exits 0
however many of its few sources failed.

An incomplete publish exits by what it failed on, as `caselist publish` does
(:func:`~debate_cli.exit_codes.exit_code_for_failure_codes`, `v1-e34-t17`): `3` when every object
the bucket did not confirm failed on something a retry may cure, such as a bucket that did not
answer, and `1` as soon as one is a verdict, such as a checksum mismatch. The envelope's `publish`
carries the codes.

## `--publish`

The same guards as `caselist publish`: dev or prod only, and prod only with `--confirm-prod`. The
store is parsed first, here, then the current version directory is copied to the bucket.

## `--publish-only`

Publishes the current version directory as the last rebuild left it, parsing and rebuilding
nothing (`v1-e31-t30`): for a publish that failed after its rebuild had finished, and for the same
store sent to a second environment's bucket. The directory is the one `--publish` would publish,
the newest generation of the running parser version, and the publisher is the same one, so what is
withheld, what goes last and what is skipped are the same too
(:mod:`debate_core.application.caselist.parsed_publish_only`). Before anything is uploaded the
directory is checked whole and written by this build's parser and fingerprint versions, and its
aggregates are checked to name nothing this environment's suppression list now stops or holds,
asked of the list the publisher is given; when it fails a check, the command is refused with the
reason's code, exit `1`, and a hint naming `--publish`.

It is refused, exit `2`, beside `--publish` or any option that only shapes a rebuild (`--reparse`,
`--snapshot`), and beside `--failures`, which publishes nothing. The guards are `--publish`'s.

## `--publish-only --dry-run`

Lists what `--publish-only` would upload and what the bucket already holds with the same digest,
with counts and bytes for each kind (per-source files, aggregates, the placement state), and
uploads and writes nothing (`v1-e31-t40`). It makes every check `--publish-only` makes, in the same
order, and is refused by each with the same code, message, hint and exit code: the environment
guard, the directory's checks, the run lock (read, never taken:
:meth:`~debate_core.application.caselist.run_lock.BucketWriteGuard.refuse_what_holding_would_refuse`)
and the occurrence table guard. Only `--confirm-prod` is the real publish's. The plan is
:meth:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher.plan`, which decides
each object by the publish's own code. A per-source file the bucket holds with other bytes, which
the publish would fail and withhold the aggregates for, fails the dry run as
`PARSED_PUBLISH_BLOCKED`, exit `1`, after the plan is printed.

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

from debate_cli.bucket_lock import run_holding_the_bucket_lock
from debate_cli.caselist_publish_refusals import no_bucket, refuse, unconfirmed_production_write
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode, exit_code_for_failure_codes
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode, TableSpec
from debate_cli.panel_summaries import by_count, digest_of_key, every_value_in_full, some_prefixes
from debate_core.application.caselist.parsed_publish import (
    ParsedObjectKind,
    ParsedObjectOutcome,
    ParsedPublishPlan,
    ParsedPublishReport,
    PlannedAction,
)
from debate_core.application.caselist.publish_plan import validate_publish_target
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist_parse import (
    PARSE_FAILURE_RATE_EXCEEDED,
    FailureListing,
    ParseRunReport,
)
from debate_core.application.errors import UNMODELLED_ERROR_CODE
from debate_core.application.settings import Settings
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "ConflictingPublishOnly",
    "failures_summary",
    "parse",
    "parse_summary",
    "publish_only_plan_summary",
    "publish_only_summary",
]

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
    publish_only: Annotated[
        bool,
        typer.Option(
            "--publish-only",
            help=(
                "Copy the current version directory to this environment's evidence bucket as the "
                "last rebuild left it, parsing and rebuilding nothing."
            ),
        ),
    ] = False,
    reparse: Annotated[
        bool, typer.Option("--reparse", help="Parse everything again, into a new version directory.")
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Count what would be parsed and write nothing; with --publish-only, list what it "
                "would upload and refuse what it would refuse."
            ),
        ),
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
    if publish_only:
        _publish_only(
            cli,
            ctx,
            caselist,
            confirmed=confirm_prod,
            beside={"publish": publish, "reparse": reparse, "failures": failures},
            snapshot=snapshot,
            dry_run=dry_run,
        )
        return
    validate_publish_target(caselist, snapshot)
    if failures:
        listing = asyncio.run(cli.services.caselist_parse(with_bucket=False).failures(caselist))
        cli.output.success(command_name(ctx), failures_summary(listing), display=_failures_table(listing))
        return
    settings = cli.services.settings
    writing = publish and not dry_run
    refuse(
        cli,
        ctx,
        (no_bucket(settings, writing=True) if writing else None)
        or unconfirmed_production_write(settings, writing=writing, confirmed=confirm_prod),
    )
    service = cli.services.caselist_parse(with_bucket=writing)
    plan = asyncio.run(service.plan(caselist, snapshot=snapshot, reparse=reparse))
    report = service.dry_run(plan) if dry_run else asyncio.run(service.run(plan))
    published = (
        run_holding_the_bucket_lock(
            cli,
            "caselist parse --publish",
            lambda: cli.services.parsed_publisher().publish(caselist, plan.version),
        )
        if writing
        else None
    )
    payload = parse_summary(report, published, settings)
    failure = _failure(report, published, payload)
    if failure is None or not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_parse_table(report, published, settings))
    if failure is not None:
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code)


class ConflictingPublishOnly(typer.BadParameter):
    """`--publish-only` beside an option it has no use for: one that rebuilds, or that publishes nothing."""

    def __init__(self, option: str, why: str) -> None:
        super().__init__(
            f"--publish-only publishes the directory the last rebuild left, so it cannot be combined "
            f"with {option}: {why}; pass one or the other",
            param_hint=option,
        )


def _refuse_beside_publish_only(
    *, publish: bool, reparse: bool, snapshot: str | None, failures: bool
) -> None:
    """Raise :class:`ConflictingPublishOnly` for the first option given that `--publish-only` refuses."""
    for given, option, why in (
        (publish, "--publish", "--publish rebuilds the directory first"),
        (reparse, "--reparse", "--reparse rebuilds into a new directory"),
        (snapshot is not None, "--snapshot", "--snapshot chooses what a rebuild parses"),
        (failures, "--failures", "--failures lists the directory's failures and publishes nothing"),
    ):
        if given:
            raise ConflictingPublishOnly(option, why)


def _publish_only(
    cli: CliContext,
    ctx: typer.Context,
    caselist: str,
    *,
    confirmed: bool,
    beside: dict[str, bool],
    snapshot: str | None,
    dry_run: bool,
) -> None:
    """`--publish-only`: the options it refuses beside it, `--publish`'s guards, the directory's
    check, then `--publish`'s publisher, or its plan with `--dry-run`. `beside` is each flag of the
    command by its parameter.

    The dry run is the same path with the writes taken out: the environment guard as a publish's
    (`writing=True`), `--confirm-prod` alone left to the real run.
    """
    _refuse_beside_publish_only(snapshot=snapshot, **beside)
    validate_publish_target(caselist)
    settings = cli.services.settings
    refuse(
        cli,
        ctx,
        no_bucket(settings, writing=True)
        or unconfirmed_production_write(settings, writing=not dry_run, confirmed=confirmed),
    )
    # With the bucket: the check asks the list the publisher is given, this environment's.
    version = asyncio.run(cli.services.caselist_parse(with_bucket=True).publishable_version(caselist))
    if dry_run:
        _publish_only_dry_run(cli, ctx, caselist, version)
        return
    published = run_holding_the_bucket_lock(
        cli,
        "caselist parse --publish-only",
        lambda: cli.services.parsed_publisher().publish(caselist, version),
    )
    payload = publish_only_summary(published, settings)
    failure = _publish_failure(published, payload)
    if failure is None or not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_publish_only_table(published, settings))
    if failure is not None:
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code)


def _publish_only_dry_run(cli: CliContext, ctx: typer.Context, caselist: str, version: str) -> None:
    """`--publish-only --dry-run`, after the directory's checks: the lock read and never taken, then
    the publisher's plan, uploading and writing nothing."""
    cli.services.bucket_write_guard().refuse_what_holding_would_refuse()
    planned = asyncio.run(cli.services.parsed_publisher().plan(caselist, version))
    settings = cli.services.settings
    payload = publish_only_plan_summary(planned, settings)
    failure = _plan_failure(planned, payload)
    if failure is None or not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_publish_only_plan_table(planned, settings))
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
        "failure_rate_minimum_sources": report.minimum_sources,
        "failure_rate_judged": report.rate_is_judged,
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


def publish_only_summary(published: ParsedPublishReport, settings: Settings) -> dict[str, JsonValue]:
    """`--publish-only --json`'s `data`: `publish` is the object `--publish` reports, key for key."""
    return {
        "environment": settings.environment.value,
        "caselist": published.caselist,
        "version": published.version,
        "publish_only": True,
        "fingerprint_version": FINGERPRINT_VERSION,
        "publish": _publish_summary(published, settings),
    }


def publish_only_plan_summary(planned: ParsedPublishPlan, settings: Settings) -> dict[str, JsonValue]:
    """`--publish-only --dry-run --json`'s `data`: the plan's counts and bytes, in total and by kind.

    `plan`'s `objects` and `bytes` are the totals, each by what the publish would do with an object
    (`upload`, `present`, `suppressed`, `blocked`); `by_kind` gives the same for each kind.
    """
    return {
        "environment": settings.environment.value,
        "caselist": planned.caselist,
        "version": planned.version,
        "publish_only": True,
        "dry_run": True,
        "fingerprint_version": FINGERPRINT_VERSION,
        "plan": {
            "bucket": settings.storage.s3.bucket,
            "prefix": planned.prefix,
            **_planned_figures(planned, None),
            "by_kind": {kind.value: _planned_figures(planned, kind) for kind in ParsedObjectKind},
            "aggregates": "withheld" if planned.aggregates_withheld else "planned",
            "blocked_keys": list(planned.blocked_keys),
            "blocked_codes": list(dict.fromkeys(planned.blocked_codes)),
        },
    }


def _planned_figures(planned: ParsedPublishPlan, kind: ParsedObjectKind | None) -> dict[str, JsonValue]:
    return {
        "objects": {action.value: planned.count(action, kind) for action in PlannedAction},
        "bytes": {action.value: planned.size(action, kind) for action in PlannedAction},
    }


def _publish_summary(published: ParsedPublishReport, settings: Settings) -> dict[str, JsonValue]:
    return {
        "bucket": settings.storage.s3.bucket,
        "prefix": published.prefix,
        "counts": {result.value: published.count(result) for result in SourceResult},
        "aggregates": "withheld" if published.aggregates_withheld else "published",
        "failed_keys": list(published.failed_keys),
        "failure_codes": list(dict.fromkeys(published.failure_codes)),
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
    """`PARSE_FAILURE_RATE_EXCEEDED`, or else the publish's failure, if it had one.

    The details are the whole `--json` record; the panel prints counts in their place (`v1-e30-t27`).
    """
    if report.exceeds_threshold:
        panel: dict[str, JsonValue] = {
            "environment": payload["environment"],
            "caselist": f"{report.plan.caselist}, version {report.plan.version}",
            "sources": (
                f"{report.attempted} attempted, {report.parsed} parsed, "
                f"{sum(report.unsupported.values())} unsupported, {sum(report.failed.values())} failed"
            ),
            "failed": ", ".join(f"{reason} {count}" for reason, count in sorted(report.failed.items())),
        }
        if published is not None:
            panel["publish"] = _published_counts(published)
        return CommandFailure(
            code=PARSE_FAILURE_RATE_EXCEEDED,
            message=(
                f"{sum(report.failed.values())} of the {report.attempted - sum(report.unsupported.values())} "
                f"source(s) this run tried to read failed ({report.failure_rate:.1%}), above the "
                f"{report.threshold:.1%} threshold"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint="`caselist parse --failures` lists them; parse.failure_rate_threshold sets the threshold.",
            panel_details=every_value_in_full(panel),
        )
    return None if published is None else _publish_failure(published, payload)


def _publish_failure(published: ParsedPublishReport, payload: dict[str, JsonValue]) -> CommandFailure | None:
    """`PARSED_PUBLISH_INCOMPLETE`, whichever of `--publish` and `--publish-only` published.

    Either way the directory is whole by now, so the hint is the publish alone: `--publish` again
    would rebuild it for nothing. The panel names the objects not confirmed by count, digest prefix
    and code, and `--json`'s details every key (`v1-e30-t27`).
    """
    if published.succeeded:
        return None
    panel: dict[str, JsonValue] = {
        "environment": payload["environment"],
        "caselist": f"{published.caselist}, version {published.version}",
        "objects": _published_counts(published),
        "aggregates": "withheld" if published.aggregates_withheld else "published",
    }
    failed = [outcome for outcome in published.objects if outcome.result is SourceResult.FAILED]
    if failed:
        panel["not confirmed"] = _not_confirmed(failed)
    return CommandFailure(
        code="PARSED_PUBLISH_INCOMPLETE",
        message=(
            f"{len(published.failed_keys)} object(s) not confirmed in the bucket"
            + ("; the aggregates were withheld" if published.aggregates_withheld else "")
        ),
        exit_code=exit_code_for_failure_codes(published.failure_codes),
        details=payload,
        hint=(
            f"`debate-research caselist parse --caselist {published.caselist} --publish-only` retries "
            "the publish without rebuilding; a checksum mismatch needs a person."
        ),
        panel_details=every_value_in_full(panel),
    )


def _plan_failure(planned: ParsedPublishPlan, payload: dict[str, JsonValue]) -> CommandFailure | None:
    """`PARSED_PUBLISH_BLOCKED`: the plan holds an object the publish would fail, so it would end
    `PARSED_PUBLISH_INCOMPLETE`. Exit `1` on a checksum mismatch, `3` when every blocked object is
    one a store did not answer for, as the publish's own exit would be."""
    blocked = [one for one in planned.objects if one.action is PlannedAction.BLOCKED]
    if not blocked:
        return None
    panel: dict[str, JsonValue] = {
        "environment": payload["environment"],
        "caselist": f"{planned.caselist}, version {planned.version}",
        "objects": _planned_counts(planned),
        "aggregates": "withheld" if planned.aggregates_withheld else "planned",
        "blocked": _named_objects(
            [(one.key, one.kind is ParsedObjectKind.PER_SOURCE_FILES, one.error_code) for one in blocked]
        ),
    }
    return CommandFailure(
        code="PARSED_PUBLISH_BLOCKED",
        message=(
            f"{len(blocked)} object(s) cannot be published as planned (a per-source file the bucket "
            "holds with other bytes, or an object that could not be read)"
            + ("; the aggregates would be withheld" if planned.aggregates_withheld else "")
        ),
        exit_code=exit_code_for_failure_codes(planned.blocked_codes),
        details=payload,
        hint=(
            "Nothing was uploaded. A checksum mismatch in the bucket needs a person; an object that "
            "could not be read, run the dry run again."
        ),
        panel_details=every_value_in_full(panel),
    )


def _published_counts(published: ParsedPublishReport) -> str:
    """`6 uploaded, 0 skipped, 0 suppressed, 31 failed`: every object of the version directory."""
    return ", ".join(f"{published.count(result)} {result.value}" for result in SourceResult)


def _planned_counts(planned: ParsedPublishPlan, kind: ParsedObjectKind | None = None) -> str:
    """`upload 6 (1234 bytes); present 0 (0 bytes); suppressed 0 (0 bytes); blocked 0 (0 bytes)`:
    the `--json` plan's figures for `kind`, or for every kind, in the same order."""
    return "; ".join(
        f"{action.value} {planned.count(action, kind)} ({planned.size(action, kind)} bytes)"
        for action in PlannedAction
    )


def _not_confirmed(failed: list[ParsedObjectOutcome]) -> str:
    """The objects not confirmed: source files by digest prefix, aggregates by name, then their codes."""
    return _named_objects([(outcome.key, not outcome.aggregate, outcome.error_code) for outcome in failed])


def _named_objects(objects: list[tuple[str, bool, str | None]]) -> str:
    """Objects as `(key, a per-source file, error code)`: source files by digest prefix, the others
    by name, then their codes."""
    sources = sorted(digest_of_key(key).removesuffix(".jsonl") for key, source, _ in objects if source)
    others = [key.rsplit("/", 1)[-1] for key, source, _ in objects if not source]
    what = [f"{len(sources)} source file(s) {some_prefixes(sources)}"] if sources else []
    if others:
        what.append(f"{len(others)} aggregate(s) ({', '.join(sorted(others))})")
    codes = by_count(code or UNMODELLED_ERROR_CODE for _, _, code in objects)
    return f"{', '.join(what)}: {codes}"


def _parse_table(
    report: ParseRunReport, published: ParsedPublishReport | None, settings: Settings
) -> TableSpec:
    plan = report.plan
    store = report.store
    rows = [
        ["Version", plan.version + _new_version_note(report)],
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
            ["Failure rate", _failure_rate(report)],
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


def _publish_only_table(published: ParsedPublishReport, settings: Settings) -> TableSpec:
    return TableSpec(
        columns=("", published.caselist),
        rows=[["Version", published.version], ["Published", _published(published, settings)]],
        title=f"caselist parse {published.caselist} --publish-only",
        caption="Nothing was parsed or rebuilt: the directory was published as the last rebuild left it.",
    )


def _publish_only_plan_table(planned: ParsedPublishPlan, settings: Settings) -> TableSpec:
    """The `--json` plan's figures, row by row: each kind, then the total."""
    last = (
        "A per-source file is blocked, so the aggregates and the placement state would be withheld."
        if planned.aggregates_withheld
        else "The aggregates and the placement state go last, once every per-source file is confirmed."
    )
    return TableSpec(
        columns=("", planned.caselist),
        rows=[
            ["Version", planned.version],
            ["Per-source files", _planned_counts(planned, ParsedObjectKind.PER_SOURCE_FILES)],
            ["Aggregates", _planned_counts(planned, ParsedObjectKind.AGGREGATES)],
            ["Placement state", _planned_counts(planned, ParsedObjectKind.PLACEMENT_STATE)],
            ["Total", _planned_counts(planned)],
            ["Bucket", f"{settings.storage.s3.bucket}/{planned.prefix}"],
        ],
        title=f"caselist parse {planned.caselist} --publish-only --dry-run",
        caption=f"Dry run: nothing was uploaded or written. {last}",
    )


def _new_version_note(report: ParseRunReport) -> str:
    """What the version row adds when this run starts the directory (`v1-e31-t16`)."""
    plan = report.plan
    if not plan.new_version:
        return ""
    started = "new" if report.applied else "new: a run would start it"
    if plan.superseded is None:
        return f" ({started})"
    return f" ({started}; it supersedes {plan.superseded}, which is left as it was)"


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


def _failure_rate(report: ParseRunReport) -> str:
    """The rate beside its threshold, and whether this run was large enough for it to be judged."""
    rate = f"{report.failure_rate:.1%} (threshold {report.threshold:.1%})"
    if report.rate_is_judged:
        return rate
    return f"{rate}; not judged: {report.tried} source(s) tried, under the {report.minimum_sources} it takes"


def _counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {count}" for name, count in counts.items()) or "0"


def _published(published: ParsedPublishReport, settings: Settings) -> str:
    return (
        f"{published.count(SourceResult.UPLOADED)} uploaded, "
        f"{published.count(SourceResult.SKIPPED)} skipped, "
        f"{len(published.failed_keys)} failed to {settings.storage.s3.bucket}/{published.prefix}"
    )

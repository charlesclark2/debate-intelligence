"""`debate-research landscape report` and `landscape evaluate`: the landscape, and its model stage measured.

::

    debate-research landscape report --caselist hspolicy26
    debate-research landscape report --caselist hspolicy26 --snapshot 2026-10-20 --json
    debate-research landscape report --caselist hspolicy26 --publish --dry-run
    debate-research landscape report --caselist hspolicy26 --publish --accept-scan-hits 3f9a0c1d2e4b
    debate-research landscape report --caselist hspolicy26 --restored-copy <copy> --publish

Every decision is :class:`~debate_core.application.landscape_run.LandscapeRunService`'s
(`v1-e32-t05-landscape-cli`); this is the guards and the rendering.

## The bundle

The run writes seven files, under `<data dir>/reports/landscape/<caselist>/<snapshot>/` unless
`--out` names a directory (`v1-e32-t12-landscape-cli-seven-files`):

* **circuit-wide**, naming no school, team or debater: `v1-e32-t03`'s `report.md`, `positions.csv`
  and `top_cards.csv`, `v1-e32-t10`'s `impact_cards.csv`, and `v1-e32-t04`'s `trends.csv`;
* **school view**, naming each disclosing school and team code as disclosed: `v1-e32-t04`'s
  `schools.csv` and `schools.md`.

`--help`, the human output and `--json`'s `bundle` mark each file one or the other, read from
:data:`~debate_core.application.landscape_report.CIRCUIT_WIDE_FILES` and
:data:`~debate_core.application.landscape_report.SCHOOL_VIEW_FILES`, so an operator sees which files
name schools before publishing. `--json` also counts the trends (`trends.rows_by_label`, NEW, RISING,
FALLING and STEADY, and `trends.held_back_by_team_floor`) and the school view (`school_view.schools`,
`team_codes` and `rows`), all from the run's result and as numbers only.

## A stale report

The status line starts `STALE:` when `v1-e34-t03`'s hook says the report is. When the latest sync run
of the caselist failed or stopped on an error (`v1-e34-t32`), the line ends with the hook's own
sentence, :meth:`~debate_core.application.landscape_staleness.FailedSyncRun.sentence`, and `--json`'s
`staleness.failed_run` holds the run id and the failed stages' names or the error's class, as the hook
holds them: never a stage's reason or the error's message, which can name a school or a path.

## `--publish`

Uploads the bundle to `reports/landscape/<caselist>/<snapshot>/` in this environment's evidence
bucket, which is private, skipping a file the bucket holds with the same SHA-256. Dev or prod only,
and prod only with `--confirm-prod`; `DEBATE_ENV` never defaults to prod. Never a presigned URL.

## The scan before sharing

Every run scans the bundle for the schools, team codes, tournaments and paths its disclosures name,
and prints each hit with its line. Those lines can name a school or a team: they are for the
operator's terminal, and `--json` says so in a `notice`. `--publish` is refused, exit `1`, while a
hit no earlier run accepted remains, naming the digest of those hits. Read them; when none names a
team, run again with `--accept-scan-hits <digest>`, which is accepted only while it is the digest of
the hits the run finds. Accepted hits are remembered on this machine, so next week stops only on new
ones.

## `--dry-run`

Writes nothing but the plan-text and analytic-text caches: not the classification cache, the review
queue, the bundle, the acceptance log, the model cassettes or usage log, or the bucket. The two text
caches are keyed on the parser version, so the first report after a parser bump reads every on-topic
source again; a dry run keeps those readings, derived fields and never evidence text, in the data
directory (never in a `--restored-copy`), and the publish after it parses none of those sources to
fill them (`v1-e32-t30`, the PM's ruling of 2026-10-31). Like every run, it still reads again, in
memory, the few sources holding a CP text, alternative or role of the ballot the report quotes.
`--json`'s `text_caches` says, for each cache, how many sources the run asked for, found cached,
read and could not read, and how many entries it wrote, in every run. With `--publish` it asks the
bucket which files would go up. In every model mode it says how many cards it would ask the model
about (`--json`: `classification.model.would_ask`, `null` in a run that is no dry run), and asks
none: under `none` that is 0, and under `replay` or `live` it is what a run would send, with what it
would hold back over `--max-model-items` (`v1-e40-t17`).

## `--restored-copy`

Since the cutover the weekly run is the cloud task, and the weeks it pulls are in the dev bucket, not in
this machine's data directory. `--restored-copy <copy>` (`v1-e40-t17`) reads the caselist's cards from a
copy `caselist restore-run-state --with-sources` made and `caselist parse` parsed with this build: its
manifests, parsed store, suppression list, run log and raw sources. Every piece of the landscape's own
state stays in the data directory, where a deleted copy cannot take it: the classification cache, the
review queue, the plan-text and analytic-text caches, the scan acceptances, the model cassettes and
usage log, and the bundle. `--json`'s `restored_copy` names the copy, `null` without one. Refused, exit
`2`, for the data directory, a directory inside it or holding it, one inside a checkout, one that is no
directory, a copy holding no weekly manifest of the caselist, and a copy whose newest parsed directory of
it is not this build's parser version. In bucket mode `--publish` without it is refused, exit `1`, with
the runbook in the hint (`docs/runbooks/landscape-report-from-the-cloud-run.md`): the data directory's
newest snapshot is not the newest week. A dry run, and a report kept on this machine, need no copy.

## Exit codes

`0` when the report was written (and published, when asked). `2` for an unknown caselist or snapshot,
with the known ones, or a caselist and date `topics.yaml` maps to no topic with a taxonomy, naming
the file to edit, or a `--restored-copy` refused. `3` for a classification stage whose model was
throttled or stopped answering partway (`v1-e32-t32`): the cache and the review queue keep what was
answered, nothing is published, and the next run asks only about the cards not yet cached. `--json`'s
`error.code` is `MODEL_STAGE_INTERRUPTED`, and `error.details.cause_code` the code of what stopped it
(`PROVIDER_RATE_LIMITED`, `PROVIDER_UNAVAILABLE`). `1` for a publish the scan holds back, a
classification stage over its model budget or whose model call was refused (`MODEL_ACCESS_DENIED`,
`MODEL_REQUEST_REJECTED`; also after writing the cache and the review queue, publishing nothing), a live
run the data-use policy does not yet allow, a publish in bucket mode without `--restored-copy`, or a
report that cannot be built.

## `--model-mode`

* `none` (the default): classification is deterministic, and no model is called.
* `replay` and `live` (`v1-e32-t07`): the cards headings cannot place, or place below the review
  threshold, go to `landscape.classify_position`, at most `--max-model-items` of them a run (one per
  card fingerprint, the most shared first). `replay` answers from the cassettes this machine recorded
  under `<data dir>/landscape/model-cassettes/`; `live` calls the routed model, and is refused until
  the data-use policy records its open question 4 as answered (the E32 gate). A run that holds cards
  back over the limit exits `1` after caching what it asked, so the next run asks about the rest.
  `--json`'s `classification.model` counts what was asked, held back, refused and spent in tokens.

## `landscape evaluate`

::

    debate-research landscape evaluate --caselist hspolicy26 --sample <coach CSV> --sample-rows <rows file>

Measures the model stage against cards a coach labelled (`v1-e32-t07` ac4): `v1-e32-t21`'s coach
sample, the filled CSV and the rows file written beside it. Every labelled card the store holds is asked
about, and the command prints, for the caselist's format, how many of the cards a report would count
name the coach's position (the bar is 85%), and what the scan of the prompt inputs and of the prompt's
cassettes on this machine found: counts, never a name. `--model-mode replay` (the default) answers from
those cassettes; `record`, once, after the data-use policy records its open question 4 as answered,
makes the calls and writes them. It caches, writes and publishes no report. Exit `0` when the format
meets the bar and both scans are clean, `1` otherwise.
"""

from __future__ import annotations

import asyncio
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, NoReturn

import typer

from debate_cli.bucket_lock import run_holding_the_bucket_lock
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.options.landscape_config import landscape_config_dir
from debate_cli.options.snapshot_date import parse_snapshot_date
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode
from debate_core.application.analytic_texts import AnalyticTextCounts
from debate_core.application.errors import error_code_of
from debate_core.application.landscape_model_evaluation import TARGET_ACCURACY, FormatEvaluation
from debate_core.application.landscape_model_stage import (
    DEFAULT_MAX_MODEL_ITEMS,
    POLICY_QUESTION,
    model_use_gate,
)
from debate_core.application.landscape_report import CIRCUIT_WIDE_FILES, SCHOOL_VIEW_FILES
from debate_core.application.landscape_restored_copy import (
    LANDSCAPE_RUNBOOK,
    RESTORED_COPY_FLAG,
    publish_refusal,
    restored_copy_refusal,
)
from debate_core.application.landscape_run import (
    LandscapeModelMode,
    LandscapeRequestRefused,
    LandscapeRunRequest,
    LandscapeRunResult,
    PublishRefusal,
)
from debate_core.application.landscape_staleness import FailedSyncRun
from debate_core.application.plan_texts import PlanTextCounts
from debate_core.application.settings import Environment, Settings, find_repository_root
from debate_core.arguments.landscape.model_stage import NameScan
from debate_core.domain.landscape_trends import LandscapeTrends, TrendLabel

__all__ = [
    "CIRCUIT_WIDE",
    "REPORT_HELP",
    "SCAN_NOTICE",
    "SCHOOL_VIEW",
    "EvaluationMode",
    "evaluate",
    "evaluation_summary",
    "report",
    "run_summary",
]

POLICY_FILE: Final = Path("docs") / "policies" / "caselist-data-use.md"

SCAN_NOTICE: Final = (
    "scan.hits quote report lines that may name a school or a team code. For this terminal only: "
    "never paste them into a report, a document, an issue or a commit (docs/policies/caselist-data-use.md)."
)

CIRCUIT_WIDE: Final = "circuit_wide"
SCHOOL_VIEW: Final = "school_view"
_VIEWS: Final = {
    **dict.fromkeys(CIRCUIT_WIDE_FILES, CIRCUIT_WIDE),
    **dict.fromkeys(SCHOOL_VIEW_FILES, SCHOOL_VIEW),
}
"""Each bundle file's view, by name. A file in neither of t04's lists is a KeyError, not a guess."""

REPORT_HELP: Final = (
    "Build a caselist's argument landscape report, write it here and, with --publish, to the bucket.\n\n"
    f"Circuit-wide: {', '.join(CIRCUIT_WIDE_FILES)}. "
    f"School view, naming schools and team codes: {', '.join(SCHOOL_VIEW_FILES)}."
)
"""`--help`'s text, from t04's lists; :func:`report`'s docstring is set to it."""


def report(
    ctx: typer.Context,
    caselist: Annotated[str, typer.Option("--caselist", help="Caselist slug, e.g. hspolicy26.")],
    snapshot: Annotated[
        str | None,
        typer.Option("--snapshot", help="The weekly snapshot, YYYY-MM-DD. Default: the newest."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            file_okay=False,
            help="Write the bundle here. Default: <data dir>/reports/landscape/<caselist>/<snapshot>/.",
        ),
    ] = None,
    publish: Annotated[
        bool,
        typer.Option("--publish/--no-publish", help="Also upload it to this environment's evidence bucket."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Say what a run would write and upload, and write nothing but the plan-text and "
                "analytic-text caches, which the publish after it reads instead of the sources."
            ),
        ),
    ] = False,
    accept_scan_hits: Annotated[
        str | None,
        typer.Option(
            "--accept-scan-hits",
            metavar="DIGEST",
            help="Publish although the scan found these hits: the digest a refused publish printed.",
        ),
    ] = None,
    model_mode: Annotated[
        LandscapeModelMode,
        typer.Option(
            "--model-mode",
            help="none: deterministic only, no model call. replay: the model stage from recorded cassettes. "
            "live: the model stage, calling the routed model (behind the data-use policy's gate).",
        ),
    ] = LandscapeModelMode.NONE,
    max_model_items: Annotated[
        int | None,
        typer.Option(
            "--max-model-items",
            min=0,
            help=f"Cards the model stage may ask about in this run. Default: {DEFAULT_MAX_MODEL_ITEMS}.",
        ),
    ] = None,
    config_dir: Annotated[
        Path | None,
        typer.Option(
            "--config-dir",
            file_okay=False,
            help="The directory holding topics.yaml. Default: config/landscape in this checkout.",
        ),
    ] = None,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required to publish to the production evidence bucket.")
    ] = False,
    restored_copy: Annotated[
        Path | None,
        typer.Option(
            RESTORED_COPY_FLAG,
            file_okay=False,
            help="Read the caselist's cards from this copy restored from the bucket "
            "(`caselist restore-run-state --with-sources`); the landscape's own state stays in the data "
            "directory. Required to publish in bucket mode.",
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    settings = cli.services.settings
    copy = restored_copy.expanduser().resolve() if restored_copy is not None else None
    refusal = _environment_refusal(
        settings, publish=publish, writing=publish and not dry_run, confirmed=confirm_prod
    ) or _copy_refusal(settings, copy, publish=publish, dry_run=dry_run)
    if refusal is None and model_mode is LandscapeModelMode.LIVE and not dry_run:
        refusal = _policy_refusal()
    if refusal is not None:
        _end(cli, ctx, refusal)
    request = LandscapeRunRequest(
        caselist=caselist,
        snapshot=parse_snapshot_date(snapshot) if snapshot is not None else None,
        out=_outside_a_checkout(out),
        publish=publish,
        dry_run=dry_run,
        accept_scan_hits=accept_scan_hits,
        model_mode=model_mode,
        max_model_items=max_model_items,
    )
    service = cli.services.landscape_run(
        config_dir=landscape_config_dir(config_dir), with_bucket=publish, restored_copy=copy
    )
    try:
        result = (
            run_holding_the_bucket_lock(cli, "landscape report --publish", lambda: service.run(request))
            if publish and not dry_run
            else asyncio.run(service.run(request))
        )
    except LandscapeRequestRefused as refused:
        _end(cli, ctx, _usage_failure(refused))
    payload = run_summary(result, settings, restored_copy=copy)
    failure = _publish_failure(result, payload)
    if failure is None or not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_display(result, settings))
    if failure is not None:
        _end(cli, ctx, failure)


report.__doc__ = REPORT_HELP


class EvaluationMode(StrEnum):
    """`--model-mode` for an evaluation: replay the cassettes, or record them once."""

    REPLAY = "replay"
    RECORD = "record"


def evaluate(
    ctx: typer.Context,
    caselist: Annotated[str, typer.Option("--caselist", help="Caselist slug, e.g. hspolicy26.")],
    sample: Annotated[
        Path, typer.Option("--sample", exists=True, dir_okay=False, help="The coach's filled sample CSV.")
    ],
    sample_rows: Annotated[
        Path,
        typer.Option("--sample-rows", exists=True, dir_okay=False, help="The rows file written beside it."),
    ],
    model_mode: Annotated[
        EvaluationMode,
        typer.Option("--model-mode", help="replay: from this machine's cassettes. record: call and record."),
    ] = EvaluationMode.REPLAY,
    snapshot: Annotated[
        str | None, typer.Option("--snapshot", help="The weekly snapshot, YYYY-MM-DD. Default: the newest.")
    ] = None,
    config_dir: Annotated[
        Path | None,
        typer.Option("--config-dir", file_okay=False, help="The directory holding topics.yaml."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Measure the landscape's model stage against cards a coach labelled."""
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    refusal = _policy_refusal() if model_mode is EvaluationMode.RECORD else None
    if refusal is not None:
        _end(cli, ctx, refusal)
    service = cli.services.landscape_evaluation(
        config_dir=landscape_config_dir(config_dir), record=model_mode is EvaluationMode.RECORD
    )
    with sample.open(encoding="utf-8", newline="") as labels, sample_rows.open(encoding="utf-8") as rows:
        result = asyncio.run(
            service.evaluate(
                caselist, labels, rows, snapshot=parse_snapshot_date(snapshot) if snapshot else None
            )
        )
    payload = evaluation_summary(result)
    passed = result.meets_target and result.sent.clean and result.cassettes.clean
    if passed or not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=_evaluation_display(result))
    if not passed:
        _end(cli, ctx, _evaluation_failure(result, payload))


def evaluation_summary(result: FormatEvaluation) -> dict[str, JsonValue]:
    """`landscape evaluate`'s `data`: counts, the accuracy against the bar, and the two scans' counts."""
    return {
        "caselist": result.caselist,
        "event": result.event,
        "topic_id": result.topic_id,
        "taxonomy_version": result.taxonomy_version,
        "prompt_version": result.prompt_version,
        "snapshot": _iso(result.snapshot),
        "labelled": result.labelled,
        "found": result.found,
        "asked": result.asked,
        "calls": result.calls,
        "counted": result.counted,
        "correct": result.correct,
        "accuracy": result.accuracy,
        "target": TARGET_ACCURACY,
        "meets_target": result.meets_target,
        "placed_below_threshold": result.placed_below_threshold,
        "placed_labelled_none": result.placed_labelled_none,
        "refused": dict(result.refused),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "interrupted": result.interrupted,
        "scan": {
            name: {
                "texts": scan.texts,
                "schools": scan.schools,
                "team_codes": scan.team_codes,
                "other_names": scan.other_names,
                "clean": scan.clean,
            }
            for name, scan in (("prompt_inputs", result.sent), ("cassettes", result.cassettes))
        },
    }


def _evaluation_display(result: FormatEvaluation) -> str:
    accuracy = "n/a" if result.accuracy is None else f"{result.accuracy:.1%}"
    return "\n".join(
        [
            f"{result.caselist} ({result.event}) on {result.topic_id} {result.taxonomy_version}, "
            f"landscape.classify_position {result.prompt_version}.",
            f"Labelled {result.labelled}, found {result.found}; asked about {result.asked} in "
            f"{result.calls} call(s).",
            f"Counted {result.counted}, correct {result.correct}: {accuracy} (bar {TARGET_ACCURACY:.0%}); "
            f"{result.placed_below_threshold} placed below the threshold, {result.placed_labelled_none} "
            "labelled none.",
            f"Scan of the prompt inputs: {_scan_line(result.sent)}. Of the cassettes: "
            f"{_scan_line(result.cassettes)}.",
        ]
    )


def _scan_line(scan: NameScan) -> str:
    return (
        f"{scan.texts} text(s), {scan.schools} naming a school, {scan.team_codes} a team code, "
        f"{scan.other_names} a tournament"
    )


def _evaluation_failure(result: FormatEvaluation, payload: dict[str, JsonValue]) -> CommandFailure:
    if not (result.sent.clean and result.cassettes.clean):
        message = "the scan found a school, team code or tournament in the prompt inputs or the cassettes"
    else:
        message = (
            f"the model stage's accuracy is under the bar of {TARGET_ACCURACY:.0%}, or nothing was counted"
        )
    return CommandFailure(
        code="EVALUATION_BELOW_BAR", message=message, exit_code=ExitCode.DOMAIN_FAILURE, details=payload
    )


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _policy_refusal() -> CommandFailure | None:
    """A live model run waits on the data-use policy's open question 4: refused while it is open."""
    root = find_repository_root()
    policy = root / POLICY_FILE if root is not None else None
    reason = model_use_gate(
        policy.read_text(encoding="utf-8") if policy is not None and policy.is_file() else None
    )
    if reason is None:
        return None
    return CommandFailure(
        code="MODEL_USE_NOT_YET_ALLOWED",
        message=reason,
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"policy": str(POLICY_FILE), "open_question": POLICY_QUESTION},
        hint="Use --model-mode replay or none until the policy records the answer.",
    )


def _outside_a_checkout(out: Path | None) -> Path | None:
    """`--out`, refused inside a checkout: a report holds real tags and cites, never committed."""
    if out is None:
        return None
    resolved = out.expanduser().resolve()
    if find_repository_root(resolved) is not None:
        raise typer.BadParameter(
            f"{resolved} is inside a checkout of this repository, and a report holds real tags and cites; "
            "write it outside, or leave --out out for the data directory",
            param_hint="--out",
        )
    return resolved


def _environment_refusal(
    settings: Settings, *, publish: bool, writing: bool, confirmed: bool
) -> CommandFailure | None:
    """A publish needs dev or prod and a bucket; prod needs --confirm-prod. A dry run only reads."""
    environment = settings.environment
    if publish and environment not in SYNCABLE_ENVIRONMENTS:
        return CommandFailure(
            code="ENVIRONMENT_NOT_SYNCABLE",
            message=f"`landscape report --publish` writes to dev or prod, not {environment.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": environment.value},
            hint="Set DEBATE_ENV=dev and try again.",
        )
    if publish and not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"the {environment.value} environment names no evidence bucket",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": environment.value},
            hint="Set storage.s3.bucket for this environment, or run without --publish.",
        )
    if writing and environment is Environment.PROD and not confirmed:
        return CommandFailure(
            code="CONFIRMATION_REQUIRED",
            message=f"refusing to publish to the production evidence bucket without {CONFIRM_PROD_FLAG}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": environment.value},
            hint=f"Publish to dev first. Then run with --dry-run, and again with {CONFIRM_PROD_FLAG}.",
        )
    return None


def _copy_refusal(
    settings: Settings, copy: Path | None, *, publish: bool, dry_run: bool
) -> CommandFailure | None:
    """A `--restored-copy` that is no copy; in bucket mode, a publish without one (`v1-e40-t17`)."""
    environment = settings.environment.value
    if copy is not None and (reason := restored_copy_refusal(copy, data_dir=settings.storage.data_dir)):
        return CommandFailure(
            code="RESTORED_COPY_REFUSED",
            message=f"{RESTORED_COPY_FLAG} names no copy to read: {reason}",
            exit_code=ExitCode.USAGE_ERROR,
            details={"environment": environment},
            hint="Name the directory `caselist restore-run-state --into` restored, beside the data dir.",
        )
    reason = publish_refusal(
        run_state=settings.caselist.run_state,
        publish=publish,
        dry_run=dry_run,
        restored_copy=copy is not None,
    )
    if reason is None:
        return None
    return CommandFailure(
        code="PUBLISH_NEEDS_A_RESTORED_COPY",
        message=f"nothing was published: {reason}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"environment": environment},
        hint=f"Restore a copy, parse it, and publish from it: {LANDSCAPE_RUNBOOK}.",
    )


def _usage_failure(refused: LandscapeRequestRefused) -> CommandFailure:
    details: dict[str, JsonValue] = {"known": list(refused.known)}
    if refused.file_to_edit is not None:
        details["file_to_edit"] = refused.file_to_edit
    return CommandFailure(
        code=error_code_of(refused),
        message=str(refused),
        exit_code=ExitCode.USAGE_ERROR,
        details=details,
        hint=f"Edit {refused.file_to_edit}." if refused.file_to_edit else None,
    )


def _publish_failure(result: LandscapeRunResult, payload: dict[str, JsonValue]) -> CommandFailure | None:
    """A publish the scan held back: exit 1, after the result and its hits are printed."""
    refused = result.publish.refused if result.publish is not None else None
    if refused is None:
        return None
    scan = result.scan
    if refused is PublishRefusal.SCAN_DIGEST_STALE:
        message = (
            f"--accept-scan-hits names other hits than the {len(scan.pending)} this run found not yet "
            f"accepted (digest {scan.digest}); nothing was published"
        )
    else:
        message = (
            f"the scan found {len(scan.pending)} hit(s) not yet accepted (digest {scan.digest}); "
            "nothing was published"
        )
    return CommandFailure(
        code=refused.value,
        message=message,
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint=(
            f"Read each hit's line above. If none names a team, run again with --accept-scan-hits "
            f"{scan.digest}; the report is written locally at {result.directory}."
        ),
        panel_details={"digest": scan.digest, "hits_not_yet_accepted": len(scan.pending)},
    )


def run_summary(
    result: LandscapeRunResult, settings: Settings, *, restored_copy: Path | None = None
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`: paths, counts, method totals, model calls, scan and publish."""
    counts = result.classification.counts
    header = result.report.header
    unclassified = result.report.unclassified
    queue = result.classification.review_queue.counts
    publish = result.publish
    return {
        "caselist": result.caselist,
        "snapshot": result.snapshot.isoformat(),
        "report_date": result.report_date.isoformat(),
        "environment": settings.environment.value,
        "topic_id": result.topic_id,
        "taxonomy_version": result.taxonomy_version,
        "overrides_digest": result.overrides_digest,
        "parsed_version": result.parsed_version,
        "model_mode": result.model_mode.value,
        "model_calls": result.model_calls,
        "dry_run": result.dry_run,
        "restored_copy": str(restored_copy) if restored_copy is not None else None,
        "written": result.written,
        "paths": {"directory": str(result.directory), "files": [str(path) for path in result.files]},
        "bundle": [
            {"name": path.name, "path": str(path), "view": _VIEWS[path.name]} for path in result.files
        ],
        "counts": {
            "sources": counts.sources,
            "sections": counts.sections,
            "cards": counts.cards,
            "cards_counted": counts.cards_counted,
            "cards_below_threshold": counts.cards_below_threshold,
            "positions": len(result.report.positions),
            "top_card_rows": len(result.report.top_cards),
            "rounds": header.rounds,
            "rounds_with_a_read": header.rounds_with_a_read,
            "teams": header.teams,
            "aff_rounds": unclassified.aff_rounds,
            "aff_rounds_unidentified": unclassified.aff_rounds_unidentified,
            "neg_rounds": unclassified.neg_rounds,
            "neg_rounds_unplaced": unclassified.neg_rounds_unplaced,
            "other_side_position_rounds": unclassified.other_side_position_rounds,
        },
        "trends": {
            "rows_by_label": dict(_trend_counts(result.trends)),
            "held_back_by_team_floor": result.trends.held_back,
        },
        "school_view": {
            "schools": result.schools.schools,
            "team_codes": result.schools.teams,
            "rows": len(result.schools.rows),
        },
        "classification": {
            "cards_by_method": dict(counts.cards_by_method),
            "sections_by_method": dict(counts.sections_by_method),
            "cache": {
                "lookups": counts.lookups,
                "hits": counts.hits,
                "misses": counts.misses,
                "written": counts.cache_written,
            },
            "model": {
                "prompt_version": result.classification.prompt_version,
                "would_ask": counts.model_items if result.dry_run else None,
                "asked": counts.model_items,
                "calls": counts.model_calls,
                "cached": counts.model_hits,
                "held_back": counts.model_held_back,
                "refused": dict(counts.model_refused),
                "input_tokens": counts.model_input_tokens,
                "output_tokens": counts.model_output_tokens,
            },
        },
        "review_queue": {
            "rows": queue.rows,
            "items": queue.queued_items,
            "location": result.classification.review_queue_location,
        },
        "text_caches": {
            "plan_texts": _text_cache(result.plan_texts),
            "analytic_texts": _text_cache(result.analytic_texts.read if result.analytic_texts else None),
        },
        "aff_assignments": result.aff_assignments,
        "aff_identification": {one.method: one.rounds for one in result.report.aff_identification},
        "staleness": {
            "stale": result.staleness.stale,
            "newest_snapshot": _iso(result.staleness.newest_snapshot),
            "age_days": result.staleness.age_days,
            "archives_awaiting_download": result.staleness.archives_awaiting_download,
            "failed_run": _failed_run(result.staleness.failed_run),
        },
        "scan": {
            "hits": [
                {
                    "file": hit.file,
                    "line": hit.line_number,
                    "kind": hit.kind.value,
                    "term": hit.term,
                    "text": hit.line,
                }
                for hit in result.scan.hits
            ],
            "not_yet_accepted": len(result.scan.pending),
            "digest": result.scan.digest,
            "accepted_now": result.scan.accepted_now,
            "acceptance_log": result.scan.acceptance_log,
        },
        "publish": None
        if publish is None
        else {
            "bucket": str(settings.storage.s3.bucket) if settings.storage.s3.bucket else None,
            "planned": [
                {
                    "name": one.name,
                    "key": one.key,
                    "sha256": one.sha256,
                    "action": one.action.value if one.action is not None else None,
                }
                for one in publish.planned
            ],
            "uploaded": list(publish.uploaded),
            "unchanged": list(publish.unchanged),
            "refused": publish.refused.value if publish.refused is not None else None,
        },
        "notice": SCAN_NOTICE if result.scan.hits else None,
    }


def _text_cache(counts: PlanTextCounts | AnalyticTextCounts | None) -> dict[str, JsonValue] | None:
    """How a text cache was read and written (`v1-e32-t30`); None when the run read none of it."""
    if counts is None:
        return None
    return {
        "sources": counts.sources,
        "cached": counts.hits,
        "read": counts.parsed,
        "unread": counts.unread,
        "entries_written": counts.parsed if counts.cache_written else 0,
        "written": counts.cache_written,
    }


def _text_cache_lines(result: LandscapeRunResult) -> list[str]:
    """Each text cache's line: sources read and already cached, and the entries written, a dry run too."""
    lines: list[str] = []
    for label, counts in (
        ("Plan-text cache", result.plan_texts),
        ("Analytic-text cache", result.analytic_texts.read if result.analytic_texts else None),
    ):
        if counts is None:
            continue
        entries = counts.parsed if counts.cache_written else 0
        written = (
            f"{entries} {'entry' if entries == 1 else 'entries'} written"
            if entries
            else ("older entries dropped" if counts.cache_written else "nothing written")
        )
        lines.append(
            f"{label}: {counts.parsed} of {counts.sources} source(s) read, {counts.hits} already cached, "
            f"{written}."
        )
    return lines


def _model_lines(result: LandscapeRunResult) -> list[str]:
    """The model stage's line, when the run had one: asked, cached, held back, refused, tokens."""
    if result.model_mode is LandscapeModelMode.NONE:
        return []
    counts = result.classification.counts
    refused = ", ".join(f"{reason} {count}" for reason, count in counts.model_refused.items()) or "none"
    return [
        f"Model stage ({result.classification.prompt_version}): asked about {counts.model_items} card(s) in "
        f"{counts.model_calls} call(s), {counts.model_hits} cached, {counts.model_held_back} held back; "
        f"refused: {refused}; tokens {counts.model_input_tokens} in, {counts.model_output_tokens} out."
    ]


def _would_ask_lines(result: LandscapeRunResult) -> list[str]:
    """A dry run's count of the cards it would ask the model about, in every mode; it asked none."""
    if not result.dry_run:
        return []
    counts = result.classification.counts
    line = f"Dry run: would ask the model about {counts.model_items} card(s)"
    if result.model_mode is LandscapeModelMode.NONE:
        return [f"{line}; --model-mode none asks it nothing."]
    if counts.model_held_back:
        return [f"{line}, and hold {counts.model_held_back} more back for a later run."]
    return [f"{line}."]


def _display(result: LandscapeRunResult, settings: Settings) -> str:
    counts = result.classification.counts
    header = result.report.header
    unclassified = result.report.unclassified
    methods = ", ".join(f"{method} {count}" for method, count in counts.cards_by_method.items())
    lines = [
        f"{result.caselist} through {result.snapshot.isoformat()} on {result.topic_id} "
        f"{result.taxonomy_version} "
        f"(overrides {result.overrides_digest}, model mode {result.model_mode.value}, "
        f"{result.model_calls} model calls).",
        f"Sources {counts.sources}; cards {counts.cards}, {counts.cards_counted} counted "
        f"({_share(counts.cards_counted, counts.cards)}); by method: {methods}.",
        f"Positions {len(result.report.positions)}; rounds {header.rounds}, "
        f"{header.rounds_with_a_read} with a read "
        f"({_share(header.rounds_with_a_read, header.rounds)}); teams {header.teams}.",
        f"Affirmative rounds with no identified aff: {unclassified.aff_rounds_unidentified} of "
        f"{unclassified.aff_rounds}; aff assignments {result.aff_assignments}.",
        *_text_cache_lines(result),
        *_model_lines(result),
        *_would_ask_lines(result),
        f"Review queue: {result.classification.review_queue.counts.rows} rows "
        f"({result.classification.review_queue_location}).",
        _trends_line(result.trends),
        f"School view: {result.schools.schools} school(s), {result.schools.teams} team code(s), "
        f"{len(result.schools.rows)} row(s).",
        _staleness_line(result),
        *_bundle_lines(result),
    ]
    scan = result.scan
    lines.append(
        f"Scan: {len(scan.hits)} hit(s), {len(scan.pending)} not yet accepted"
        + (f" (digest {scan.digest})." if scan.pending else ".")
    )
    lines += [
        f"  {hit.file}:{hit.line_number} {hit.kind.value} {hit.term!r}"
        + (" (accepted)" if hit not in scan.pending else "")
        + f": {hit.line}"
        for hit in scan.hits
    ]
    if scan.accepted_now:
        lines.append(
            f"Accepted {len(scan.pending)} hit(s) under digest {scan.digest}; "
            f"recorded in {scan.acceptance_log}."
        )
    if result.publish is not None:
        target = (
            f"{settings.environment.value} bucket {settings.storage.s3.bucket}"
            if settings.storage.s3.bucket
            else "no bucket"
        )
        lines.append(f"Publish to {target}:")
        lines += [
            f"  {one.action.value if one.action is not None else 'PLANNED'} {one.key} ({one.sha256[:12]})"
            for one in result.publish.planned
        ]
        lines.append(
            f"Uploaded {len(result.publish.uploaded)}, unchanged {len(result.publish.unchanged)}."
            if result.publish.refused is None and not result.dry_run
            else "Nothing uploaded."
        )
    return "\n".join(lines)


def _staleness_line(result: LandscapeRunResult) -> str:
    staleness = result.staleness
    said = (
        f"newest snapshot {_iso(staleness.newest_snapshot)}, {staleness.age_days} day(s) old, "
        f"{staleness.archives_awaiting_download} archive(s) awaiting download"
    )
    line = f"STALE: {said}." if staleness.stale else f"Current: {said}."
    return line if staleness.failed_run is None else f"{line} {staleness.failed_run.sentence()}"


def _failed_run(failed: FailedSyncRun | None) -> dict[str, JsonValue] | None:
    """The hook's failed run as it holds it: the run id, and the stage names or the error's class."""
    if failed is None:
        return None
    return {
        "run_id": failed.run_id,
        "stages": list(failed.stages),
        "stopped_before_stages": failed.stopped_before_stages,
        "error_class": failed.error_class,
    }


def _trend_counts(trends: LandscapeTrends) -> dict[str, int]:
    """The trend rows under each label, in report order."""
    return {label.value: len(trends.labelled(label)) for label in TrendLabel}


def _trends_line(trends: LandscapeTrends) -> str:
    labels = ", ".join(f"{label} {count}" for label, count in _trend_counts(trends).items())
    return f"Trends: {labels}; {trends.held_back} held back by the team floor."


def _bundle_lines(result: LandscapeRunResult) -> list[str]:
    """Where the bundle went, or would go, and which of its files are circuit-wide or name schools."""
    files = len(result.files)
    head = (
        f"Wrote {files} files to {result.directory}:"
        if result.written
        else f"Dry run: the bundle is not written; its {files} files would go to {result.directory}:"
    )
    return [
        head,
        f"  circuit-wide: {_names_in(result, CIRCUIT_WIDE)}",
        f"  school view, naming schools and team codes: {_names_in(result, SCHOOL_VIEW)}",
    ]


def _names_in(result: LandscapeRunResult, view: str) -> str:
    return ", ".join(path.name for path in result.files if _VIEWS[path.name] == view)


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day is not None else None


def _share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"

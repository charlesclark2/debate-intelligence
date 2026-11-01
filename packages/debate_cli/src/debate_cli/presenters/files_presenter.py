"""How `debate-research files build`, `check`, `suggest` and `publish` show results (`v1-e33-t03`, `t05`).

Each function takes a service's result and returns a :class:`Rendered`: the `--json` payload, the table
a person reads, and the :class:`~debate_cli.output.CommandFailure` the outcome is reported as when it
failed. Nothing here decides an outcome: the build service decided it.

## What is shown

Counts, digests, paths of the files written, the place in the recipe of each card a problem is about,
and each check's PASS, WARN or FAIL. Never card text, a school or a team code: no result holds one.

`files check` and `files build` follow the checks table with one line per WARN or FAIL result, in the
`.quality.md`'s words and order (:func:`~debate_core.evidence.file_checks.report.finding_line`), and
`--json` carries the same results under `quality.findings`, each shaped as the `.quality.json`'s
`results` entries are (`v1-e33-t12`). A file with no WARN or FAIL prints the table alone.

`files publish` names the warned checks of each file it lets through in the table's caption, and below
the table prints each of their warnings in the same line `files check` does, under the file's slug,
and `--json` carries them as the file's `warnings` (PM amendment 2026-10-31, `v1-e33-t16`). A refused
file prints none of these: a `QUALITY_FAILED` refusal carries its sidecar check's warnings in its own
message (`v1-e33-t10`).

## Exit codes

* `0`: built (or checked) and every check passed or only warned; a draft was written; every file was
  published, already published (`SKIPPED`), or, in a dry run, would be.
* `1`: the build was refused after reading the recipe and the store (an invalid or unresolved recipe,
  a store another build parsed, a missing source, a card the writer could not copy), or a check
  FAILed. A FAIL keeps the files, which the payload names. For `files publish`, a file was refused,
  each named with its reason and the checks that failed.
* `2`: the command line asked for what is refused before anything is read: a draft without
  `--allow-draft`, an output directory inside a git working tree; for `files suggest`, a caselist,
  snapshot, position or side the landscape does not have, or a draft path that is taken or inside a
  git working tree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.errors import error_code_of
from debate_core.application.file_build_service import (
    BuildRefusalCode,
    BuildStatus,
    FileBuildResult,
    FileCheckResult,
    UnattributedCard,
)
from debate_core.application.file_publish_service import PublishOutcome, PublishResult, PublishStatus
from debate_core.application.file_suggest_service import SuggestResult
from debate_core.evidence.file_checks.report import CheckStatus, FileQualityReport, finding_line

__all__ = [
    "Rendered",
    "build_rendered",
    "check_rendered",
    "publish_rendered",
    "refused_request",
    "suggest_rendered",
    "unattributed_lines",
]

#: Refusals that are about the command line, raised before the store is read: exit 2.
_USAGE_REFUSALS = frozenset(
    {BuildRefusalCode.DRAFT_NOT_ALLOWED, BuildRefusalCode.OUTPUT_IN_A_GIT_WORKING_TREE}
)


@dataclass(frozen=True, slots=True)
class Rendered:
    payload: dict[str, JsonValue]
    display: TableSpec | str | None
    """None when the failure panel says it all."""
    failure: CommandFailure | None = None


def unattributed_lines(cards: Sequence[UnattributedCard]) -> list[str]:
    """What `files build` says before it builds, for each card resolved to an unattributed occurrence."""
    lines = [
        f"{len(cards)} card(s) resolved to an occurrence with nothing on record about who disclosed it; "
        "the built file's sidecar will name no team for them:"
    ]
    lines += [f"  {card.path}: {card.fingerprint[:12]} ({card.caselist})" for card in cards]
    return lines


def build_rendered(result: FileBuildResult) -> Rendered:
    """`files build`: the summary and the check table, or the refusal with every error it listed."""
    payload = _build_payload(result)
    if result.status is BuildStatus.REFUSED:
        assert result.refusal is not None
        refusal = result.refusal
        listed = [str(error) for error in result.recipe_errors] + [
            f"{one.path}: {one.code}: {one.detail}" + (f"; run `{one.hint}`" if one.hint else "")
            for one in result.card_problems
        ]
        failure = CommandFailure(
            code=str(refusal.code),
            message="\n".join([refusal.message, *listed]),
            exit_code=ExitCode.USAGE_ERROR if refusal.code in _USAGE_REFUSALS else ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint=refusal.hint,
            panel_details={"recipe": str(result.recipe_path)},
        )
        return Rendered(payload, None, failure)
    assert result.files is not None and result.counts is not None and result.quality is not None
    counts = result.counts
    title = (
        f"Built {result.files.docx}: {counts.cards_placed} card(s) placed from {counts.sources_used} "
        f"source(s), {counts.tag_overrides} tag override(s), {len(result.warnings)} warning(s)"
    )
    display = _checks_table(result.quality, title=title, caption=_warnings_caption(result.warnings))
    failure = None
    if result.status is BuildStatus.QUALITY_FAILED:
        failure = _quality_failure(result.quality, payload, kept=str(result.files.docx))
    return Rendered(payload, display, failure)


def check_rendered(result: FileCheckResult) -> Rendered:
    """`files check`: the check table, and a FAIL with whatever explains it as the hint."""
    report = result.checked.report
    payload: dict[str, JsonValue] = {
        "file": str(result.checked.json_path.with_name(_built_name(result.checked.json_path.name))),
        "quality": _quality_payload(report),
        "reports": {
            "quality_json": str(result.checked.json_path),
            "quality_markdown": str(result.checked.markdown_path),
        },
        "notes": list(result.notes),
    }
    writer = report.builder_version or "-"
    display = _checks_table(
        report,
        title=f"Checked: {report.status}, {report.card_count} card(s), writer {writer}",
        caption=" ".join(result.notes) or None,
    )
    failure = None
    if report.status is CheckStatus.FAIL:
        failure = _quality_failure(report, payload, kept=None, hint=" ".join(result.notes) or None)
    return Rendered(payload, display, failure)


def suggest_rendered(result: SuggestResult) -> Rendered:
    """`files suggest`: where the draft went, and its cards by rank with what each pin names.

    A counterplan's draft also says how many blocks and cards it left out as another position's
    (`v1-e33-t11`): `other_positions_left_out`, null for any other position's draft. And how many it
    kept, marked, under a heading an aff or an advantage places (`v1-e33-t13`): `affirmative_side_kept`,
    null for any other position's draft too.
    """
    payload: dict[str, JsonValue] = {
        "path": str(result.path),
        "caselist": result.caselist,
        "snapshot": result.snapshot.isoformat(),
        "topic": result.topic,
        "position": result.position,
        "side": str(result.side),
        "status": "draft",
        "recipe_hash": result.recipe_hash,
        "cards": [
            {
                "rank": one.rank,
                "teams_reading": one.teams_reading,
                "fingerprint": one.fingerprint,
                "block": one.block,
                "pin_names": list(one.pin_fields),
            }
            for one in result.cards
        ],
        "left_out": [
            {"rank": one.rank, "fingerprint": one.fingerprint, "reason": one.reason}
            for one in result.left_out
        ],
        "other_positions_left_out": (
            None
            if result.other_positions is None
            else {"blocks": result.other_positions.blocks, "cards": result.other_positions.cards}
        ),
        "affirmative_side_kept": (
            None
            if result.affirmative_side_kept is None
            else {"blocks": result.affirmative_side_kept.blocks, "cards": result.affirmative_side_kept.cards}
        ),
    }
    rows = [
        [
            str(one.rank),
            str(one.teams_reading),
            one.fingerprint[:12],
            one.block,
            ", ".join(one.pin_fields) or "-",
        ]
        for one in result.cards
    ]
    left = f" {len(result.left_out)} most-read card(s) left out, see --json." if result.left_out else ""
    other = result.other_positions
    if other is not None:
        left += (
            f" A counterplan's draft: {other.blocks} block(s) holding {other.cards} card(s) left out, "
            "their heading another position's."
        )
    kept = result.affirmative_side_kept
    if kept is not None:
        left += (
            f" {kept.blocks} block(s) holding {kept.cards} card(s) kept under an aff's or advantage's "
            "heading, marked to check against the plan."
        )
    display = TableSpec(
        columns=["Rank", "Teams", "Fingerprint", "Block", "Pin also names"],
        rows=rows,
        title=(
            f"Draft written to {result.path}: {len(result.cards)} card(s) of {result.position} "
            f"({result.side}) from {result.caselist} through {result.snapshot.isoformat()}"
        ),
        caption=(
            "status: draft. Edit it, add your own cards and tags, then set status: ready, or build it as "
            f"it is with `files build --allow-draft`.{left}"
        ),
    )
    return Rendered(payload, display)


def publish_rendered(result: PublishResult, *, environment: str, bucket: str) -> Rendered:
    """`files publish`: each file's status and prefix, and, when any was refused, every refusal."""
    counts = {str(status): 0 for status in PublishStatus}
    for one in result.outcomes:
        counts[str(one.status)] += 1
    payload: dict[str, JsonValue] = {
        "environment": environment,
        "bucket": bucket,
        "dry_run": result.dry_run,
        "counts": dict(counts),
        "files": [_outcome_payload(one) for one in result.outcomes],
    }
    verb = "Dry run: would publish to" if result.dry_run else "Published to"
    warned = [
        f"{one.slug}: {', '.join(str(check) for check in one.warned_checks)}"
        for one in result.outcomes
        if one.warned_checks
    ]
    display = TableSpec(
        columns=["File", "Status", "Prefix, or why refused"],
        rows=[[one.docx.name, str(one.status), _where(one)] for one in result.outcomes],
        title=f"{verb} the {environment} evidence bucket {bucket}",
        caption=", ".join(f"{count} {status}" for status, count in counts.items() if count)
        + (f". Warned, not blocked: {'; '.join(warned)}" if warned else ""),
        lines_below=_warning_lines(result.outcomes),
    )
    refused = result.refused
    if not refused:
        return Rendered(payload, display)
    codes = {str(one.refusal.code) for one in refused if one.refusal is not None}
    failure = CommandFailure(
        code=codes.pop() if len(codes) == 1 else "FILES_REFUSED",
        message="\n".join(
            [f"{len(refused)} of {len(result.outcomes)} built file(s) refused; nothing of them was uploaded:"]
            + [f"  {one.docx.name}: {_why(one)}" for one in refused]
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint=refused[0].refusal.hint if len(refused) == 1 and refused[0].refusal is not None else None,
        panel_details={"refused": len(refused), **{key: value for key, value in counts.items() if value}},
    )
    return Rendered(payload, display, failure)


def _outcome_payload(outcome: PublishOutcome) -> dict[str, JsonValue]:
    refusal = outcome.refusal
    return {
        "file": str(outcome.docx),
        "slug": outcome.slug,
        "status": str(outcome.status),
        "keys": list(outcome.keys),
        "written": list(outcome.written),
        "skipped": list(outcome.skipped),
        "warned_checks": [str(one) for one in outcome.warned_checks],
        "warnings": [one.model_dump(mode="json") for one in outcome.warnings],
        "refusal": None
        if refusal is None
        else {
            "code": str(refusal.code),
            "message": refusal.message,
            "hint": refusal.hint,
            "failing_checks": [str(one) for one in refusal.failing_checks],
        },
    }


def _warning_lines(outcomes: Sequence[PublishOutcome]) -> list[str]:
    """Each warning of each file let through, as `files check` prints it, under the file's slug."""
    lines: list[str] = []
    for one in outcomes:
        if one.warnings:
            lines += [
                f"Warned, not blocked in {one.slug}:",
                *(f"  {finding_line(found)}" for found in one.warnings),
            ]
    return lines


def _where(outcome: PublishOutcome) -> str:
    if outcome.refusal is not None:
        return str(outcome.refusal.code)
    return outcome.keys[0].rsplit("/", 1)[0] + "/" if outcome.keys else ""


def _why(outcome: PublishOutcome) -> str:
    refusal = outcome.refusal
    assert refusal is not None
    checks = (
        f" (failing: {', '.join(str(one) for one in refusal.failing_checks)})"
        if refusal.failing_checks
        else ""
    )
    return f"[{refusal.code}] {refusal.message}{checks}"


def refused_request(refused: Exception, *, known: Sequence[str], hint: str | None) -> CommandFailure:
    """A request `files suggest` refuses before writing: a name the landscape or the taxonomy lacks."""
    details: dict[str, JsonValue] = {"known": list(known)}
    return CommandFailure(
        code=error_code_of(refused),
        message=str(refused),
        exit_code=ExitCode.USAGE_ERROR,
        details=details,
        hint=hint,
    )


def _build_payload(result: FileBuildResult) -> dict[str, JsonValue]:
    files = result.files
    counts = result.counts
    refusal = result.refusal
    return {
        "recipe": str(result.recipe_path),
        "recipe_hash": result.recipe_hash,
        "status": str(result.status),
        "refusal": None
        if refusal is None
        else {"code": str(refusal.code), "message": refusal.message, "hint": refusal.hint},
        "recipe_errors": [
            {"code": str(error.code), "path": error.path, "line": error.line, "message": error.message}
            for error in result.recipe_errors
        ],
        "card_problems": [
            {
                "path": one.path,
                "fingerprint": one.fingerprint,
                "code": one.code,
                "detail": one.detail,
                "hint": one.hint,
            }
            for one in result.card_problems
        ],
        "unattributed": [
            {"path": one.path, "fingerprint": one.fingerprint, "caselist": one.caselist}
            for one in result.unattributed
        ],
        "files": None
        if files is None
        else {
            "docx": str(files.docx),
            "provenance": str(files.provenance),
            "quality_json": str(files.quality_json),
            "quality_markdown": str(files.quality_markdown),
        },
        "counts": None
        if counts is None
        else {
            "cards_placed": counts.cards_placed,
            "sources_used": counts.sources_used,
            "tag_overrides": counts.tag_overrides,
            "analytics": counts.analytics,
            "warnings": len(result.warnings),
        },
        "warnings": list(result.warnings),
        "quality": None if result.quality is None else _quality_payload(result.quality),
    }


def _quality_payload(report: FileQualityReport) -> dict[str, JsonValue]:
    return {
        "status": str(report.status),
        "checks": [
            {
                "check": str(one.check),
                "status": str(one.status),
                "failures": one.failures,
                "warnings": one.warnings,
            }
            for one in report.checks
        ],
        "failing_checks": [str(one.check) for one in report.checks if one.status is CheckStatus.FAIL],
        "findings": [one.model_dump(mode="json") for one in report.findings],
    }


def _checks_table(report: FileQualityReport, *, title: str, caption: str | None) -> TableSpec:
    return TableSpec(
        columns=["Check", "Status", "Failures", "Warnings"],
        rows=[
            [str(one.check), str(one.status), str(one.failures), str(one.warnings)] for one in report.checks
        ],
        title=title,
        caption=caption,
        lines_below=_findings_lines(report),
    )


def _findings_lines(report: FileQualityReport) -> list[str]:
    """Each WARN and FAIL under a heading, as `.quality.md` words them; nothing for a clean file."""
    if not report.findings:
        return []
    return ["Failures and warnings:", *(f"  {finding_line(one)}" for one in report.findings)]


def _quality_failure(
    report: FileQualityReport, payload: dict[str, JsonValue], *, kept: str | None, hint: str | None = None
) -> CommandFailure:
    failing = [str(one.check) for one in report.checks if one.status is CheckStatus.FAIL]
    where = f"; the files are kept for inspection beside {kept}" if kept else ""
    return CommandFailure(
        code="QUALITY_FAILED",
        message=f"the quality check FAILed: {', '.join(failing)}{where}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint=hint
        if hint is not None
        else "Each finding is listed above; the .quality.md beside the file has the full report.",
        panel_details={"failing_checks": ", ".join(failing)},
    )


def _warnings_caption(warnings: Sequence[str]) -> str | None:
    return "Warnings: " + "; ".join(warnings) if warnings else None


def _built_name(quality_json_name: str) -> str:
    """`synthetic.docx` for `synthetic.docx.quality.json`."""
    return quality_json_name.removesuffix(".quality.json")

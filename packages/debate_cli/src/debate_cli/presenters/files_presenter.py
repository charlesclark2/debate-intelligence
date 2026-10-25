"""How `debate-research files build`, `files check` and `files suggest` show their results (`v1-e33-t03`).

Each function takes a service's result and returns a :class:`Rendered`: the `--json` payload, the table
a person reads, and the :class:`~debate_cli.output.CommandFailure` the outcome is reported as when it
failed. Nothing here decides an outcome: the build service decided it.

## What is shown

Counts, digests, paths of the files written, the place in the recipe of each card a problem is about,
and each check's PASS, WARN or FAIL. Never card text, a school or a team code: no result holds one.

## Exit codes

* `0`: built (or checked) and every check passed or only warned; a draft was written.
* `1`: the build was refused after reading the recipe and the store (an invalid or unresolved recipe,
  a store another build parsed, a missing source, a card the writer could not copy), or a check
  FAILed. A FAIL keeps the files, which the payload names.
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
from debate_core.application.file_suggest_service import SuggestResult
from debate_core.evidence.file_checks.report import CheckStatus, FileQualityReport

__all__ = [
    "Rendered",
    "build_rendered",
    "check_rendered",
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
    """`files suggest`: where the draft went, and its cards by rank with what each pin names."""
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
    }


def _checks_table(report: FileQualityReport, *, title: str, caption: str | None) -> TableSpec:
    return TableSpec(
        columns=["Check", "Status", "Failures", "Warnings"],
        rows=[
            [str(one.check), str(one.status), str(one.failures), str(one.warnings)] for one in report.checks
        ],
        title=title,
        caption=caption,
    )


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
        hint=hint if hint is not None else "Read the .quality.md beside the file for each card's finding.",
        panel_details={"failing_checks": ", ".join(failing)},
    )


def _warnings_caption(warnings: Sequence[str]) -> str | None:
    return "Warnings: " + "; ".join(warnings) if warnings else None


def _built_name(quality_json_name: str) -> str:
    """`synthetic.docx` for `synthetic.docx.quality.json`."""
    return quality_json_name.removesuffix(".quality.json")

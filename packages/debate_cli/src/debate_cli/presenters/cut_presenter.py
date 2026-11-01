"""What `debate-research cut` says at each stage and about each outcome (`v1-e06-t06`).

Every decision was made in `debate_core` before anything here runs: whether the page could be read
(the access classifier), what the card is and whether it verifies (CardService), and what the
document holds (ExportService). This module only puts those answers into words and shapes:

* **Progress**, one line per stage on stderr, in order: `fetch`, `extract`, `select`, `verify`,
  `export`. Under `--json` each is an event object (:meth:`~debate_cli.output.CliOutput.event_line`),
  so stdout still carries one object. `select` is announced before the model is asked, because that
  is the stage a person waits on.
* **The payload**: the card's id and status (`status`, as `verify` names a card's), the file, the
  source and snapshot, each failure reason, each model call's provenance, and the manifest's
  identity: its version, time, cards, snapshot references and the SHA-256 of the manifest bytes
  embedded in the document. Never evidence text or
  a model's words, as no `--json` payload carries them (:mod:`debate_cli.output`). The manifest itself,
  evidence included, is the one in the .docx.
* **The failures**: a source that is not ACCESSIBLE (exit 3, the status with the canonical URL) and a
  card that is not VERIFIED (exit 4, each reason). Exit codes are :class:`~debate_cli.exit_codes.ExitCode`'s;
  a cut that could not run at all is an exception, which the root group maps (exit 1 or 3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, JsonValue, TableSpec
from debate_core.application.article_fetch import SOURCE_NOT_ACCESSIBLE_CODE, FetchReport, SnapshotSummary
from debate_core.application.card_types import CardFailure, CardFailureReason, CutResult
from debate_core.domain import AccessStatus

__all__ = [
    "ACCESS_STATUS_WORDS",
    "CARD_UNVERIFIED_CODE",
    "FAILURE_REASON_WORDS",
    "STAGES",
    "CutProgress",
    "cut_payload",
    "not_accessible",
    "unverified",
    "verdict_table",
]

STAGES: Final = ("fetch", "extract", "select", "verify", "export")
"""The stages progress names, in the order they run."""

CARD_UNVERIFIED_CODE: Final = ExitCode.CARD_UNVERIFIED.name
"""The `error.code` of a card exported UNVERIFIED: the exit code's own name, as for every outcome code."""

ACCESS_STATUS_WORDS: Final[dict[AccessStatus, str]] = {
    AccessStatus.PAYWALLED: "a subscription, metering or registration wall stands in front of the text",
    AccessStatus.BLOCKED: "the site served a bot challenge or block page instead of the article",
    AccessStatus.ROBOTS_DISALLOWED: "the site's robots rules do not allow this URL to be fetched",
    AccessStatus.NOT_FOUND: "the URL does not resolve to a document",
    AccessStatus.UNSUPPORTED_TYPE: "the document is of a kind the extractor cannot read",
    AccessStatus.ERROR: "the retrieval failed for a transport or server reason",
    AccessStatus.UNKNOWN: "the source was never classified",
}
"""What each status that is not ACCESSIBLE means, for the person reading the panel."""

FAILURE_REASON_WORDS: Final[dict[CardFailureReason, str]] = {
    CardFailureReason.MODEL_OUTPUT_INVALID: "the model's answer was refused, after its one repair",
    CardFailureReason.SPAN_MISMATCH: "the passage the model named could not be cut from the stored text",
    CardFailureReason.CITATION_UNVERIFIED: "a required cite field is missing or unverified",
    CardFailureReason.EVIDENCE_UNVERIFIED: "the verifier did not pass the evidence against its snapshot",
}
"""What each reason a card is UNVERIFIED means, before its own detail."""

_LABEL_WIDTH: Final = 8
"""Each progress line starts with its stage padded to this width, so the lines align."""


class CutProgress:
    """Writes one line per stage to stderr, as text for a person or as an event object under `--json`."""

    def __init__(self, output: CliOutput, command: str) -> None:
        self._output = output
        self._command = command

    def fetched(self, report: FetchReport) -> None:
        how = "fetched from the publisher" if report.fetched else "a recent stored snapshot answered"
        self._line(
            "fetch",
            f"{report.access_status.value} {report.canonical_url} ({how})",
            canonical_url=report.canonical_url,
            access_status=report.access_status.value,
            fetched=report.fetched,
        )

    def extracted(self, snapshot: SnapshotSummary) -> None:
        self._line(
            "extract",
            f"{snapshot.paragraph_count} paragraphs, snapshot {snapshot.snapshot_id} "
            f"({snapshot.extractor_version})",
            snapshot_id=snapshot.snapshot_id,
            paragraph_count=snapshot.paragraph_count,
            extractor_version=snapshot.extractor_version,
            reused=snapshot.reused,
        )

    def selecting(self, prompts: Sequence[str]) -> None:
        self._line(
            "select",
            f"asking the model where the evidence is and what to underline ({', '.join(prompts)})",
            prompts=list(prompts),
        )

    def verified(self, result: CutResult) -> None:
        status = result.verification.status.value
        codes = [reason.value for reason in result.reason_codes]
        self._line(
            "verify",
            f"{status} card {result.card.card_id}" + (f": {', '.join(codes)}" if codes else ""),
            card_id=result.card.card_id,
            status=status,
            reasons=codes,
        )

    def exported(self, output: Path, profile: str) -> None:
        self._line("export", f"{output} ({profile})", output=str(output), format_profile=profile)

    def _line(self, stage: str, text: str, **data: JsonValue) -> None:
        self._output.event_line(self._command, stage, data, text=f"{stage:<{_LABEL_WIDTH}} {text}")


def cut_payload(
    report: FetchReport, result: CutResult, *, output: Path, profile: str, manifest_bytes: bytes
) -> dict[str, JsonValue]:
    """The cut as one JSON object: `data` on exit 0, `error.details` on exit 4. No evidence text."""
    manifest: dict[str, Any] = json.loads(manifest_bytes)
    snapshot = report.snapshot
    return {
        "card_id": result.card.card_id,
        "status": result.verification.status.value,
        "output": str(output),
        "format_profile": profile,
        "source": {
            "requested_url": report.requested_url,
            "canonical_url": report.canonical_url,
            "access_status": report.access_status.value,
            "fetched": report.fetched,
            "snapshot_id": snapshot.snapshot_id if snapshot is not None else None,
            "snapshot_reused": snapshot.reused if snapshot is not None else None,
        },
        "reasons": [_reason(failure) for failure in result.reasons],
        "model_calls": [call.model_dump(mode="json") for call in result.metadata],
        "manifest": {
            "manifest_version": manifest["manifest_version"],
            "generated_at": manifest["generated_at"],
            "card_ids": [card["card_id"] for card in manifest["cards"]],
            "snapshots": manifest["snapshots"],
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        },
    }


def verdict_table(result: CutResult, payload: dict[str, JsonValue], report: FetchReport) -> TableSpec:
    """The card as a person reads it: where it went, what it was cut from, and how it was made."""
    manifest: Any = payload["manifest"]
    calls = ", ".join(
        f"{call.prompt_id}@{call.prompt_version} ({call.route.model_id})" for call in result.metadata
    )
    snapshot = report.snapshot
    rows = [
        ("Card", result.card.card_id),
        ("Status", result.verification.status.value),
        ("Written to", str(payload["output"])),
        ("Format profile", str(payload["format_profile"])),
        ("Source", report.canonical_url),
        ("Snapshot", snapshot.snapshot_id if snapshot is not None else "none"),
        ("Model calls", calls or "none"),
        ("Manifest", f"version {manifest['manifest_version']}, SHA-256 {manifest['sha256']}"),
    ]
    return TableSpec(
        title=f"{result.verification.status.value} card {result.card.card_id}",
        columns=("Field", "Value"),
        rows=rows,
    )


def not_accessible(report: FetchReport, output: Path) -> CommandFailure:
    """Exit 3: the source is not ACCESSIBLE, so no card was cut and nothing was written."""
    evidence = report.evidence
    marker = evidence.marker.marker_id if evidence is not None and evidence.marker is not None else None
    details: dict[str, JsonValue] = {
        "access_status": report.access_status.value,
        "canonical_url": report.canonical_url,
        "requested_url": report.requested_url,
        "reason": report.reason,
        "status_code": evidence.status_code if evidence is not None else None,
        "marker": marker,
        "rules_version": report.rules_version,
    }
    return CommandFailure(
        code=SOURCE_NOT_ACCESSIBLE_CODE,
        message=f"{report.access_status.value}: {ACCESS_STATUS_WORDS[report.access_status]}. {report.reason}",
        exit_code=ExitCode.RETRIEVAL_FAILURE,
        details=details,
        hint=f"No card was cut and nothing was written to {output}. Paywalls and robots rules are never "
        "worked around; cut from a source the platform may read.",
        panel_details={
            "access_status": report.access_status.value,
            "canonical_url": report.canonical_url,
            "status_code": details["status_code"],
            "marker": marker,
        },
    )


def unverified(result: CutResult, payload: dict[str, JsonValue]) -> CommandFailure:
    """Exit 4: the card was saved and written UNVERIFIED, with its banner; each reason is printed."""
    return CommandFailure(
        code=CARD_UNVERIFIED_CODE,
        message=f"card {result.card.card_id} is UNVERIFIED: written to {payload['output']} with its banner, "
        "and not finished evidence",
        exit_code=ExitCode.CARD_UNVERIFIED,
        details=payload,
        hint="An UNVERIFIED card must not be read as evidence. Each reason above says what failed.",
        panel_details=_reasons_panel(result.reasons),
    )


def _reasons_panel(reasons: Sequence[CardFailure]) -> dict[str, JsonValue]:
    """One line per reason, under its code and the verifier's; a code that repeats is numbered."""
    panel: dict[str, JsonValue] = {}
    for failure in reasons:
        label = _reason_label(failure)
        repeated = sum(1 for key in panel if key == label or key.startswith(f"{label} #"))
        panel[f"{label} #{repeated + 1}" if repeated else label] = _reason_sentence(failure)
    return panel


def _reason(failure: CardFailure) -> dict[str, JsonValue]:
    return {
        "reason": failure.reason.value,
        "detail": failure.detail,
        "fields": list(failure.fields),
        "verifier_code": failure.verifier_code.value if failure.verifier_code is not None else None,
    }


def _reason_label(failure: CardFailure) -> str:
    code = failure.reason.value
    return f"{code} ({failure.verifier_code.value})" if failure.verifier_code is not None else code


def _reason_sentence(failure: CardFailure) -> str:
    fields = f" [{', '.join(failure.fields)}]" if failure.fields else ""
    return f"{FAILURE_REASON_WORDS[failure.reason]}{fields}: {failure.detail}"

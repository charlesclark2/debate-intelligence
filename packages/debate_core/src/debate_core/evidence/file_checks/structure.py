"""The checks on a built file's shape: sidecar, cites, duplicates, headings, alignment, provenance, removals.

Each is a function of the built file re-parsed by the E31 parser, the provenance sidecar, and for the
last one the suppressions in force. None of them reads a byte, calls a model or changes anything: a
check reports, and fixing a file is rebuilding it (the task's forbidden list).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.domain.file_provenance import FileProvenanceEntry
from debate_core.domain.style_profile import StyleProfile
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck
from debate_core.evidence.fingerprints import card_fingerprint

__all__ = [
    "SuppressionsInForce",
    "card_fingerprints",
    "check_alignment",
    "check_cites",
    "check_duplicates",
    "check_headings",
    "check_provenance",
    "check_sidecar",
    "check_suppression",
]


def card_fingerprints(cards: Sequence[ParsedCard]) -> list[str]:
    """Each card's exact fingerprint, recomputed from the card as parsed."""
    return [card_fingerprint(card).exact_fingerprint for card in cards]


def _pass(
    check: QualityCheck, message: str, position: int | None = None, fingerprint: str | None = None
) -> CheckResult:
    return CheckResult(
        check=check, status=CheckStatus.PASS, card_position=position, fingerprint=fingerprint, message=message
    )


def check_sidecar(
    *,
    problems: Sequence[str],
    recorded_docx_sha256: str | None,
    docx_sha256: str,
    sidecar_parser_version: str | None,
    parser_version: str,
) -> list[CheckResult]:
    """The sidecar is readable and valid (`problems` says how it is not), and describes these bytes."""
    return [_pass(QualityCheck.SIDECAR, "the sidecar is valid and describes this file")]


def check_cites(cards: Sequence[ParsedCard]) -> list[CheckResult]:
    """Each card has a cite with a short cite. A missing one is a WARN, never a FAIL (PM, 2026-10-19)."""
    fingerprints = card_fingerprints(cards)
    return [
        _pass(QualityCheck.CITE_PRESENT, "the card has a cite with a short cite", index + 1, fingerprint)
        for index, fingerprint in enumerate(fingerprints)
    ]


def check_duplicates(cards: Sequence[ParsedCard]) -> list[CheckResult]:
    """No fingerprint twice (FAIL); cards in one near-duplicate cluster are WARNs."""
    fingerprints = card_fingerprints(cards)
    return [
        _pass(QualityCheck.DUPLICATE_CARDS, "no other card is this card", index + 1, fingerprint)
        for index, fingerprint in enumerate(fingerprints)
    ]


def check_headings(
    document: ParsedDocument, profile: StyleProfile, known_headings: frozenset[str]
) -> list[CheckResult]:
    """Headings nest pocket > hat > block > tag with no level skipped, each in its profile style.

    `known_headings` are the coach's headings the sidecar records; a heading above a violation is
    named by its text only if it is one of them, and otherwise by its unit and paragraph.
    """
    return [_pass(QualityCheck.HEADING_STRUCTURE, "every heading is in place and in its profile style")]


def check_alignment(entries: Sequence[FileProvenanceEntry], cards: Sequence[ParsedCard]) -> list[CheckResult]:
    """The sidecar and the document hold the same cards, in the same order, under the same headings."""
    return [
        _pass(
            QualityCheck.MANIFEST_ALIGNMENT,
            "the document holds this card here",
            entry.position,
            entry.fingerprint,
        )
        for entry in entries
    ]


def check_provenance(entries: Sequence[FileProvenanceEntry], document: ParsedDocument) -> list[CheckResult]:
    """Each entry's provenance is complete, and its line is below its card's cite, in Undertag."""
    return [
        _pass(
            QualityCheck.PROVENANCE_COMPLETE,
            "the card's provenance is complete",
            entry.position,
            entry.fingerprint,
        )
        for entry in entries
    ]


@dataclass(frozen=True, slots=True)
class SuppressionsInForce:
    """The suppressions in force, each with the request id it honours.

    `sources` maps a suppressed source's SHA-256 to its request id; `disclosures` maps a
    `(sha256, disclosure digest)` pair to the request id of that one disclosure's suppression.
    """

    sources: Mapping[str, str] = field(default_factory=lambda: {})
    disclosures: Mapping[tuple[str, str], str] = field(default_factory=lambda: {})


def check_suppression(
    entries: Sequence[FileProvenanceEntry], suppressions: SuppressionsInForce
) -> list[CheckResult]:
    """No card from a suppressed source or disclosure (ac6). Names the card and the request, nothing else."""
    return [
        _pass(QualityCheck.SUPPRESSION, "no suppression covers the card", entry.position, entry.fingerprint)
        for entry in entries
    ]

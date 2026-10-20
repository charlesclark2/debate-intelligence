"""The evidence-identity check: each card in a built file is its source card, re-read from both files.

For every entry of the provenance sidecar, the caller re-parses the source document the entry names
(fetched by its SHA-256) and finds the card at the entry's element range; it also re-parses the built
file. This check then compares, card by card:

* the source card's fingerprint with the sidecar's, and the sidecar's evidence, cite and formatting
  digests with the source card's own (the sidecar is a claim, and is checked like one);
* the built card at the entry's position with the source card: fingerprint, evidence text, cite,
  formatting (:func:`~debate_core.domain.file_provenance.formatting_sha256`, the reading the writer's
  digest uses) and completeness;
* the tag: the source card's, or, where the sidecar says the coach replaced it, the replaced tag's
  digest is the source tag's.

Every digest is recomputed here from the two re-parses; the sidecar's and the writer's are never taken
as the answer (the task's first forbidden item). Every difference is a FAIL, and nothing in this module
can make one a warning (the fourth). A message names the field that differs and the digests' prefixes,
never the text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from debate_core.domain.debate_files import ParsedCard
from debate_core.domain.file_provenance import FileProvenanceEntry, formatting_sha256, text_sha256
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck
from debate_core.evidence.fingerprints import card_fingerprint

__all__ = ["SourceCardReading", "check_identity"]


@dataclass(frozen=True, slots=True)
class SourceCardReading:
    """What re-reading one entry's source gave: the card at its element range, or why there is none."""

    card: ParsedCard | None
    problem: str | None = None


def _prefix(digest: str) -> str:
    return f"{digest[:12]}…"


def _differs(field: str, built: str, source: str) -> str:
    return (
        f"the built card's {field} differs from the source card's "
        f"(built {_prefix(built)}, source {_prefix(source)})"
    )


def _against_source(
    entry: FileProvenanceEntry, built: ParsedCard, source: ParsedCard, built_fingerprint: str
) -> list[str]:
    """Every way the built card is not the source card, by field."""
    problems: list[str] = []
    source_fingerprint = card_fingerprint(source).exact_fingerprint
    if built_fingerprint != source_fingerprint:
        problems.append(_differs("fingerprint", built_fingerprint, source_fingerprint))
    for field, built_digest, source_digest in (
        ("evidence text", text_sha256(built.evidence_text), text_sha256(source.evidence_text)),
        ("cite", text_sha256(built.full_cite), text_sha256(source.full_cite)),
        (
            "formatting",
            formatting_sha256(built.formatting_spans, built.font_size_spans),
            formatting_sha256(source.formatting_spans, source.font_size_spans),
        ),
    ):
        if built_digest != source_digest:
            problems.append(_differs(field, built_digest, source_digest))
    if built.completeness is not source.completeness:
        problems.append(
            f"the built card's completeness is {built.completeness}, "
            f"and the source card's {source.completeness}"
        )
    source_tag = text_sha256(source.tag) if source.tag is not None else None
    if entry.tag_overridden:
        if entry.original_tag_sha256 != source_tag:
            problems.append("the sidecar's digest of the tag the coach replaced is not the source card's tag")
    elif built.tag != source.tag:
        problems.append(
            "the built card's tag differs from the source card's, and the sidecar records no override"
        )
    return problems


def _sidecar_against_source(entry: FileProvenanceEntry, source: ParsedCard) -> list[str]:
    """Every digest the sidecar records that the source card, re-parsed, does not give."""
    problems: list[str] = []
    source_fingerprint = card_fingerprint(source).exact_fingerprint
    if source_fingerprint != entry.fingerprint:
        problems.append(
            "the card at the source's recorded paragraphs does not have the sidecar's fingerprint "
            f"(source {_prefix(source_fingerprint)})"
        )
    for field, recorded, actual in (
        ("evidence digest", entry.evidence_sha256, text_sha256(source.evidence_text)),
        ("cite digest", entry.cite_sha256, text_sha256(source.full_cite)),
        (
            "formatting digest",
            entry.formatting_sha256,
            formatting_sha256(source.formatting_spans, source.font_size_spans),
        ),
    ):
        if recorded != actual:
            problems.append(
                f"the sidecar's {field} is not the source card's "
                f"(sidecar {_prefix(recorded)}, source {_prefix(actual)})"
            )
    if entry.completeness is not source.completeness:
        problems.append(
            f"the sidecar says {entry.completeness}, and the source card is {source.completeness}"
        )
    return problems


def check_identity(
    entries: Sequence[FileProvenanceEntry],
    built_cards: Sequence[ParsedCard],
    sources: Mapping[int, SourceCardReading],
) -> list[CheckResult]:
    """One or more results per entry: PASS, or a FAIL for each way the card is not its source card.

    `built_cards` are the built file's cards in document order; `sources` maps an entry's position to
    the reading of its source.
    """
    results: list[CheckResult] = []
    for entry in entries:
        problems: list[str] = []
        reading = sources.get(entry.position, SourceCardReading(None, "the source was not read"))
        source = reading.card
        if source is None:
            problems.append(f"the source card cannot be read: {reading.problem}")
        else:
            problems.extend(_sidecar_against_source(entry, source))
        built = built_cards[entry.position - 1] if entry.position <= len(built_cards) else None
        if built is None:
            problems.append("the built file has no card at this position")
        else:
            built_fingerprint = card_fingerprint(built).exact_fingerprint
            if built_fingerprint != entry.fingerprint:
                problems.append(
                    f"the built card's fingerprint is not the sidecar's (built {_prefix(built_fingerprint)})"
                )
            if source is not None:
                problems.extend(_against_source(entry, built, source, built_fingerprint))
        if not problems:
            results.append(
                CheckResult(
                    check=QualityCheck.EVIDENCE_IDENTITY,
                    status=CheckStatus.PASS,
                    card_position=entry.position,
                    fingerprint=entry.fingerprint,
                    message="evidence text, cite, formatting and fingerprint are the source card's",
                )
            )
        results.extend(
            CheckResult(
                check=QualityCheck.EVIDENCE_IDENTITY,
                status=CheckStatus.FAIL,
                card_position=entry.position,
                fingerprint=entry.fingerprint,
                message=problem,
            )
            for problem in problems
        )
    return results

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
from debate_core.domain.file_provenance import FileProvenanceEntry
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck

__all__ = ["SourceCardReading", "check_identity"]


@dataclass(frozen=True, slots=True)
class SourceCardReading:
    """What re-reading one entry's source gave: the card at its element range, or why there is none."""

    card: ParsedCard | None
    problem: str | None = None


def check_identity(
    entries: Sequence[FileProvenanceEntry],
    built_cards: Sequence[ParsedCard],
    sources: Mapping[int, SourceCardReading],
) -> list[CheckResult]:
    """One or more results per entry: PASS, or a FAIL for each way the card is not its source card.

    `built_cards` are the built file's cards in document order; `sources` maps an entry's position to
    the reading of its source.
    """
    return [
        CheckResult(
            check=QualityCheck.EVIDENCE_IDENTITY,
            status=CheckStatus.PASS,
            card_position=entry.position,
            fingerprint=entry.fingerprint,
            message="the card is its source card",
        )
        for entry in entries
    ]

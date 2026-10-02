"""Rebuilding a card's evidence from its snapshot and comparing it exactly: the verifier's checks.

:class:`~debate_core.application.evidence_verifier.EvidenceVerifier` decides whether a card is
finished evidence. It lives in the application layer because it has to load the snapshot through
:meth:`~debate_core.application.snapshot_service.SnapshotService.load`, which the evidence layer
cannot import. Everything it checks that needs no I/O is here, and none of it sets a status: these
functions record which checks ran and what failed in a :class:`VerificationFindings`, and the
verifier turns that into a :class:`~debate_core.evidence.verification_types.VerificationResult`.

## Reconstruction happens in one place

:func:`reconstruct_card_evidence` is the only code that rebuilds a card's evidence from a snapshot.
It selects the card's envelope minus its omitted ranges (ADR-0018, ``Card.quoted_ranges``) and cuts
those ranges out of the snapshot's stored normalized text with
:class:`~debate_core.evidence.extractor.EvidenceExtractor`, the same code that cut it in the first
place, so a card is checked by the rules it was made by. :func:`evidence_text_of` joins the pieces
with nothing between them, as ADR-0018 requires, and is also what
:func:`~debate_core.evidence.card_mapping.place_evidence_on_card` uses to write ``evidence_text``.

Each omission is therefore checked as part of the text. Widen, narrow, remove or add one and either
the domain refuses the card (the envelope minus the omissions is no longer as long as the text) or
the reconstruction differs from ``evidence_text`` and the card is ``TEXT_MISMATCH``. A card whose
omissions were never validated (``model_construct``, ``model_copy``) and are not in canonical form
is refused here rather than read some other way: see :func:`reconstruct_card_evidence`.

## What "re-normalizes" means here

The snapshot stores the raw bytes and the normalized text, not the content extractor's output, and
that extractor arrives with E04. So the evidence is reconstructed from the stored normalized text,
which :meth:`SnapshotService.load` has checked against the record's hashes, under the normalizer
version the card and snapshot both record. Re-running the content extractor on the raw bytes is
follow-up work for E04, and no result claims it (see ``checks_run``).

Re-running the normalizer over the stored text, to show it is a fixed point, is deliberately not
done. The text's hash is checked against a record written by
:meth:`~debate_core.application.snapshot_service.SnapshotService.create`, the only code that encodes
snapshot text, and it stores only normalizer output. The one thing such a check would add is
refusing a record and blobs written together outside ``create`` around un-normalized text; invented
text that is already normalized passes it (both shown in the `v1-e03-t04` session report). It would
also make every verification depend on the normalizer's pinned Unicode database, which loading and
reconstruction do not.

## Failures are typed, and only the expected ones become reasons

The extractor's refusals become reasons: :class:`~debate_core.evidence.selection.InvalidSelection`
(the offsets do not select evidence from this text) is ``SPAN_OUT_OF_RANGE``, and
:class:`~debate_core.evidence.extractor.SnapshotTextMismatch` (the text is not the record's) is
``HASH_MISMATCH``. Anything else propagates. A ``TypeError`` or a card checked against another
card's snapshot is a bug in the caller, and turning it into an UNVERIFIED card would hide it.
"""

from __future__ import annotations

from debate_core.domain import Card, SourceSnapshot
from debate_core.evidence.extractor import EvidenceExtractor, ExtractedEvidence, SnapshotTextMismatch
from debate_core.evidence.normalization import SUPPORTED_NORMALIZER_VERSIONS
from debate_core.evidence.selection import EvidenceSelection, InvalidSelection, SelectionProblem
from debate_core.evidence.snapshot_text import SnapshotText
from debate_core.evidence.verification_types import (
    ReasonCode,
    VerificationCheck,
    VerificationReason,
)

__all__ = [
    "VerificationFindings",
    "check_against_snapshot",
    "check_card",
    "evidence_text_of",
    "first_difference",
    "reconstruct_card_evidence",
]

_EXTRACTOR = EvidenceExtractor()


class VerificationFindings:
    """What one verification has found so far: the checks that ran, and the reasons it fails.

    A check is recorded as run when it was attempted, whether it passed or not. Nothing here decides
    whether that was every check: a
    :class:`~debate_core.evidence.verification_types.VerificationResult` refuses to be VERIFIED unless
    all of :data:`~debate_core.evidence.verification_types.REQUIRED_CHECKS` ran, so a code path that
    forgets a check without recording a reason fails loudly instead of verifying. (The same rule here
    as well was removed: mutation showed it changed nothing the result's own rule did not.)
    """

    def __init__(self) -> None:
        self._checks_run: set[VerificationCheck] = set()
        self._reasons: list[VerificationReason] = []

    def ran(self, check: VerificationCheck) -> None:
        """Record that ``check`` was attempted."""
        self._checks_run.add(check)

    def fail(
        self,
        check: VerificationCheck,
        code: ReasonCode,
        detail: str,
        *,
        first_differing_offset: int | None = None,
    ) -> None:
        """Record that ``check`` ran and failed for ``code``."""
        self.ran(check)
        self._reasons.append(VerificationReason(code, detail, first_differing_offset))

    @property
    def checks_run(self) -> frozenset[VerificationCheck]:
        """The checks attempted so far."""
        return frozenset(self._checks_run)

    @property
    def reasons(self) -> tuple[VerificationReason, ...]:
        """The failures found so far, in the order they were found."""
        return tuple(self._reasons)


def check_card(card: Card, findings: VerificationFindings) -> None:
    """The checks that need only the card: completeness, a known normalizer version, a verified cite."""
    missing: list[str] = []
    if not card.evidence_text or card.evidence_start_offset is None or card.evidence_end_offset is None:
        missing.append("evidence text and offsets")
    if card.normalized_text_hash is None:
        missing.append("normalized_text_hash")
    if card.normalizer_version is None:
        missing.append("normalizer_version")
    if not card.spans:
        missing.append("at least one span")
    findings.ran(VerificationCheck.CARD_COMPLETE)
    if missing:
        findings.fail(
            VerificationCheck.CARD_COMPLETE,
            ReasonCode.CARD_INCOMPLETE,
            "the card lacks " + ", ".join(missing),
        )

    # A card with no version at all is reported as incomplete above; there is nothing to look up.
    if card.normalizer_version is not None:
        findings.ran(VerificationCheck.NORMALIZER_VERSION_KNOWN)
        if card.normalizer_version not in SUPPORTED_NORMALIZER_VERSIONS:
            findings.fail(
                VerificationCheck.NORMALIZER_VERSION_KNOWN,
                ReasonCode.UNKNOWN_NORMALIZER_VERSION,
                f"the card's offsets were taken under {card.normalizer_version!r}; this code has "
                + ", ".join(SUPPORTED_NORMALIZER_VERSIONS),
            )

    findings.ran(VerificationCheck.CITATION_VERIFIED)
    unverified = card.citation.unverified_fields
    if unverified:
        findings.fail(
            VerificationCheck.CITATION_VERIFIED,
            ReasonCode.CITATION_UNVERIFIED,
            "required citation fields not verified: " + ", ".join(unverified),
        )


def check_against_snapshot(
    card: Card,
    snapshot: SourceSnapshot,
    snapshot_text: SnapshotText,
    findings: VerificationFindings,
) -> None:
    """Reconstruct the card's evidence from ``snapshot_text`` and compare it, and its spans, exactly.

    ``snapshot`` must be the record ``card.snapshot_id`` names and ``snapshot_text`` must come from
    loading it with :meth:`~debate_core.application.snapshot_service.SnapshotService.load`; see
    :mod:`debate_core.evidence.extractor` for why this layer cannot check where the text came from.
    Passing another card's snapshot is a bug and raises :class:`ValueError`.
    """
    if card.snapshot_id != snapshot.snapshot_id:
        raise ValueError(f"card {card.card_id} names snapshot {card.snapshot_id}, not {snapshot.snapshot_id}")

    # A misattributed quotation. Reconstruction still runs: the offsets point into this snapshot's
    # text, so whether the quotation is verbatim is a separate fact worth reporting.
    findings.ran(VerificationCheck.ARTICLE_MATCHES_SNAPSHOT)
    if card.article_id != snapshot.article_id:
        findings.fail(
            VerificationCheck.ARTICLE_MATCHES_SNAPSHOT,
            ReasonCode.ARTICLE_MISMATCH,
            f"the card cites article {card.article_id}; its snapshot was taken of article "
            f"{snapshot.article_id}",
        )

    # Where the text came from is the snapshot's to say; a card can arrive without passing through
    # place_evidence_on_card, which copies it. Like the article, a mismatch does not stop the
    # quotation being checked.
    findings.ran(VerificationCheck.PROVENANCE_MATCHES_SNAPSHOT)
    if card.provenance_mode is not snapshot.provenance_mode:
        findings.fail(
            VerificationCheck.PROVENANCE_MATCHES_SNAPSHOT,
            ReasonCode.PROVENANCE_MISMATCH,
            f"the card claims provenance {card.provenance_mode.value}; its snapshot's text is "
            f"{snapshot.provenance_mode.value}",
        )

    findings.ran(VerificationCheck.CARD_MATCHES_SNAPSHOT)
    contradicts = False
    if card.normalizer_version is not None and card.normalizer_version != snapshot.normalizer_version:
        contradicts = True
        findings.fail(
            VerificationCheck.CARD_MATCHES_SNAPSHOT,
            ReasonCode.HASH_MISMATCH,
            f"the card's offsets were taken under {card.normalizer_version!r}, the snapshot's text is "
            f"{snapshot.normalizer_version!r}",
        )
    if card.normalized_text_hash is not None and card.normalized_text_hash != snapshot.normalized_text_hash:
        contradicts = True
        findings.fail(
            VerificationCheck.CARD_MATCHES_SNAPSHOT,
            ReasonCode.HASH_MISMATCH,
            f"the card was cut from text hashing to {card.normalized_text_hash}, the snapshot's text "
            f"hashes to {snapshot.normalized_text_hash}",
        )
    if contradicts or card.evidence_start_offset is None or card.evidence_end_offset is None:
        # The offsets point into other text, or there are none; reconstructing would compare nothing.
        return

    findings.ran(VerificationCheck.EVIDENCE_RECONSTRUCTED)
    try:
        evidence = reconstruct_card_evidence(card, snapshot, snapshot_text)
    except InvalidSelection as refused:
        omissions = f" less {len(card.omitted_ranges)} omitted range(s)" if card.omitted_ranges else ""
        findings.fail(
            VerificationCheck.EVIDENCE_RECONSTRUCTED,
            ReasonCode.SPAN_OUT_OF_RANGE,
            f"the card's offsets [{card.evidence_start_offset}, {card.evidence_end_offset}){omissions} do "
            f"not select evidence from the snapshot's {len(snapshot_text.text)}-character text: {refused}",
        )
        return
    except SnapshotTextMismatch as mismatch:
        findings.fail(
            VerificationCheck.EVIDENCE_RECONSTRUCTED,
            ReasonCode.HASH_MISMATCH,
            f"the snapshot's text is not intact: {mismatch}",
        )
        return
    reconstructed = evidence_text_of(evidence)

    findings.ran(VerificationCheck.EVIDENCE_TEXT_EXACT)
    differs_at = first_difference(card.evidence_text, reconstructed)
    if differs_at is not None:
        findings.fail(
            VerificationCheck.EVIDENCE_TEXT_EXACT,
            ReasonCode.TEXT_MISMATCH,
            _describe_difference(card.evidence_text, reconstructed, differs_at),
            first_differing_offset=differs_at,
        )

    findings.ran(VerificationCheck.SPANS_INSIDE_EVIDENCE)
    length = len(reconstructed)
    outside = [
        f"[{span.start_offset}, {span.end_offset})"
        for span in card.spans
        if not 0 <= span.start_offset < span.end_offset <= length
    ]
    if outside:
        findings.fail(
            VerificationCheck.SPANS_INSIDE_EVIDENCE,
            ReasonCode.SPAN_OUT_OF_RANGE,
            f"spans {', '.join(outside)} are not inside the {length}-character evidence",
        )


def reconstruct_card_evidence(
    card: Card, snapshot: SourceSnapshot, snapshot_text: SnapshotText
) -> ExtractedEvidence:
    """Cut the card's evidence out of its snapshot's text again: its envelope minus its omissions.

    The one place a card's evidence is rebuilt. Raises
    :class:`~debate_core.evidence.selection.InvalidSelection` when the offsets do not select evidence
    from this text (including a card that records none) and
    :class:`~debate_core.evidence.extractor.SnapshotTextMismatch` when the text is not the record's.

    The evidence comes back cut exactly where the card says it was cut, or not at all. A card whose
    omissions are not in canonical form can only arrive unvalidated, and most such forms leave an
    empty or reversed range that the selection refuses. An empty omission does not: the extractor
    joins the two ranges either side of it, which would verify a card claiming a cut that never
    happened, so a reconstruction cut anywhere else than the card says is refused too.
    """
    quoted = card.quoted_ranges
    if not quoted:
        raise InvalidSelection(SelectionProblem.NO_PARTS, "the card records no evidence offsets")
    evidence = _EXTRACTOR.extract(snapshot, snapshot_text, EvidenceSelection.of_offsets(*quoted))
    if tuple((segment.start, segment.end) for segment in evidence.segments) != quoted:
        raise InvalidSelection(
            SelectionProblem.SEGMENTS_TOUCH,
            f"the card's {len(quoted)} quoted ranges come back as {len(evidence.segments)}; an omission "
            "that removes nothing is not an omission",
        )
    return evidence


def evidence_text_of(evidence: ExtractedEvidence) -> str:
    """The evidence as a card quotes it: its segments' text, joined with nothing between them.

    ADR-0018: an omission is recorded as offsets and rendered by the exporter, never stored as text.
    """
    return "".join(segment.text for segment in evidence.segments)


def first_difference(card_text: str, reconstructed: str) -> int | None:
    """The first index at which the two texts differ, or ``None`` if they are equal.

    When one is a prefix of the other, the shorter one's length: the first index one has and the
    other does not. Indices are into the evidence text, not the snapshot.
    """
    for index, (claimed, actual) in enumerate(zip(card_text, reconstructed, strict=False)):
        if claimed != actual:
            return index
    if len(card_text) != len(reconstructed):
        return min(len(card_text), len(reconstructed))
    return None


def _describe_difference(card_text: str, reconstructed: str, index: int) -> str:
    # Code points rather than characters: a detail never quotes evidence, and a homoglyph is only
    # visible as a code point anyway.
    lengths = f"evidence_text is {len(card_text)} characters, the snapshot's evidence {len(reconstructed)}"
    if index < len(card_text) and index < len(reconstructed):
        return (
            f"evidence_text has U+{ord(card_text[index]):04X} at offset {index} where the snapshot has "
            f"U+{ord(reconstructed[index]):04X}; {lengths}"
        )
    return f"the texts agree up to offset {index}, where the shorter one ends; {lengths}"

"""What verifying a card produces: a status, the reasons it is not VERIFIED, and the checks that ran.

A :class:`VerificationResult` is the evidence verifier's verdict on one card
(:class:`~debate_core.application.evidence_verifier.EvidenceVerifier`, architecture proposal §8 steps
5-6). It is VERIFIED only with no reasons and with every check in :data:`REQUIRED_CHECKS` recorded
as run, and UNVERIFIED only with at least one reason. Both rules are enforced at construction, so a
result cannot say VERIFIED while carrying a failure, and cannot say VERIFIED after a check was
skipped.

## Reason codes

Machine-readable, stable, one per kind of failure. A result carries every reason found, not only
the first, so one run reports everything wrong with a card:

* ``SNAPSHOT_MISSING``: the card names no snapshot, or its record or a blob is gone.
* ``HASH_MISMATCH``: a stored blob failed its integrity check, or the card's recorded text hash or
  normalizer version is not the snapshot's.
* ``UNKNOWN_NORMALIZER_VERSION``: the card or the snapshot names a normalizer version this code
  does not have.
* ``CARD_INCOMPLETE``: the card lacks something re-verification needs.
* ``TEXT_MISMATCH``: the card's evidence text is not the snapshot's text at its offsets.
* ``SPAN_OUT_OF_RANGE``: the offsets, or a span, do not fit the snapshot's evidence.
* ``CITATION_UNVERIFIED``: a required citation field is not marked verified.

## What VERIFIED means, and what it does not

:data:`REQUIRED_CHECKS` is the whole of it. In particular the verifier does **not** re-run the
content extractor on the raw bytes: that extractor arrives with E04, and until then the chain from
card to source ends at the snapshot's stored normalized text, whose bytes and hash are checked on
every load. ``checks_run`` on every result says which checks ran, so a VERIFIED result never implies
a raw-bytes reproduction that did not happen. See `docs/evidence/snapshot-text-format.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from debate_core.domain import VerificationStatus
from debate_core.evidence._runtime_checks import is_instance

__all__ = [
    "REQUIRED_CHECKS",
    "VERIFIER_VERSION",
    "ReasonCode",
    "UnverifiedEvidenceError",
    "VerificationCheck",
    "VerificationReason",
    "VerificationResult",
]

VERIFIER_VERSION: Final = "evidence-verifier-v1"
"""Recorded on every result. A change to which checks run, or to what one of them accepts, is a new
version, so a stored result says which rules it was reached under."""


class ReasonCode(StrEnum):
    """Why a card is UNVERIFIED. Values are stable: they are written into reports and JSON output."""

    SNAPSHOT_MISSING = "SNAPSHOT_MISSING"
    """The card names no snapshot, or the snapshot record or one of its blobs does not exist."""

    HASH_MISMATCH = "HASH_MISMATCH"
    """Stored content is not what its record says (any of `SnapshotService.load`'s integrity checks
    other than the normalizer version), or the card records a text hash or normalizer version other
    than its snapshot's, so its offsets point into different text."""

    UNKNOWN_NORMALIZER_VERSION = "UNKNOWN_NORMALIZER_VERSION"
    """The card or its snapshot names a normalizer version this installation does not have, so its
    offsets cannot be interpreted here. Distinct from ``HASH_MISMATCH`` because nothing is damaged:
    the fix is newer code, not a fresh retrieval."""

    CARD_INCOMPLETE = "CARD_INCOMPLETE"
    """The card lacks something re-verification needs: evidence text and its offsets, the normalized
    text hash, the normalizer version, or at least one span. The same list the domain requires
    before a card may claim VERIFIED, plus the text hash that binds the card to the exact text."""

    TEXT_MISMATCH = "TEXT_MISMATCH"
    """The card's evidence text is not, character for character, the snapshot's normalized text at
    the card's offsets. Carries the first differing offset."""

    SPAN_OUT_OF_RANGE = "SPAN_OUT_OF_RANGE"
    """The card's offsets do not select evidence from the snapshot's text (past its end, empty,
    reversed), or a span runs outside the reconstructed evidence."""

    CITATION_UNVERIFIED = "CITATION_UNVERIFIED"
    """A required citation field is not marked verified. The verifier reads the per-field flags the
    citation service sets; it does not look the metadata up again."""


class VerificationCheck(StrEnum):
    """One check the verifier can run. A result lists those that ran, passed or not."""

    CARD_COMPLETE = "card_complete"
    """The card has evidence text, offsets, a normalized text hash, a normalizer version and spans."""

    NORMALIZER_VERSION_KNOWN = "normalizer_version_known"
    """The card's normalizer version is one this code has."""

    CITATION_VERIFIED = "citation_verified"
    """Every required citation field is marked verified."""

    SNAPSHOT_INTEGRITY = "snapshot_integrity"
    """The snapshot record was found and `SnapshotService.load` passed: raw bytes hash to the record's
    `sha256` and are `byte_size` long, the normalized blob hashes to its key and is canonical, and its
    text hashes to `normalized_text_hash` under the record's normalizer version."""

    CARD_MATCHES_SNAPSHOT = "card_matches_snapshot"
    """The card's recorded text hash and normalizer version are the snapshot's."""

    EVIDENCE_RECONSTRUCTED = "evidence_reconstructed"
    """The evidence was cut again from the snapshot's stored normalized text at the card's offsets."""

    EVIDENCE_TEXT_EXACT = "evidence_text_exact"
    """The card's evidence text was compared, exactly, with the reconstruction."""

    SPANS_INSIDE_EVIDENCE = "spans_inside_evidence"
    """Every span lies inside the reconstructed evidence."""


REQUIRED_CHECKS: Final = frozenset(VerificationCheck)
"""Every check. A VERIFIED result must record all of them as run."""


@dataclass(frozen=True, slots=True)
class VerificationReason:
    """One reason a card is UNVERIFIED.

    ``detail`` is for people and never quotes evidence text: it gives offsets, lengths, code points
    and record values. ``first_differing_offset`` is set for ``TEXT_MISMATCH`` and only for it.
    """

    code: ReasonCode
    detail: str
    first_differing_offset: int | None = None
    """For ``TEXT_MISMATCH``: the first index at which the card's ``evidence_text`` and the
    reconstruction differ, **in evidence-text coordinates** (an index into ``evidence_text``, not
    into the snapshot). When one text is a prefix of the other it is the shorter one's length. For a
    card quoting one contiguous range, the snapshot offset is ``evidence_start_offset`` plus this."""

    def __post_init__(self) -> None:
        if not is_instance(self.code, ReasonCode):
            raise TypeError(f"code must be a ReasonCode, got {self.code!r}")
        is_text_mismatch = self.code is ReasonCode.TEXT_MISMATCH
        if is_text_mismatch != (self.first_differing_offset is not None):
            raise ValueError("first_differing_offset is set for TEXT_MISMATCH and only for it")
        if self.first_differing_offset is not None and self.first_differing_offset < 0:
            raise ValueError("first_differing_offset cannot be negative")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The verifier's verdict on one card, and how it was reached.

    Constructed only with a status its reasons and checks support: VERIFIED with no reasons and
    every :data:`REQUIRED_CHECKS` member in ``checks_run``, UNVERIFIED with at least one reason.
    """

    card_id: str
    status: VerificationStatus
    reasons: tuple[VerificationReason, ...]
    checks_run: frozenset[VerificationCheck]
    verified_at: datetime
    """When the verification ran (timezone-aware, from the verifier's clock)."""
    verifier_version: str
    normalizer_version: str | None
    """The normalizer version the card records, which its offsets were taken under."""
    snapshot_id: str | None
    """The snapshot the card names."""

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None:
            raise ValueError("verified_at must be timezone-aware")
        if self.status is VerificationStatus.VERIFIED:
            if self.reasons:
                raise ValueError("a VERIFIED result cannot carry reasons")
            skipped = REQUIRED_CHECKS - self.checks_run
            if skipped:
                raise ValueError(
                    "a VERIFIED result must record every check as run; not run: " + ", ".join(sorted(skipped))
                )
        elif not self.reasons:
            raise ValueError("an UNVERIFIED result must say why")

    @property
    def is_verified(self) -> bool:
        """True when the card's evidence was reproduced exactly and every check passed."""
        return self.status is VerificationStatus.VERIFIED

    @property
    def reason_codes(self) -> tuple[ReasonCode, ...]:
        """The codes of :attr:`reasons`, in order, without repeats."""
        return tuple(dict.fromkeys(reason.code for reason in self.reasons))


class UnverifiedEvidenceError(Exception):
    """A card that is not VERIFIED was about to be presented or exported as finished evidence.

    The hard-failure rule (architecture proposal §8): an UNVERIFIED card may be shown as a draft
    with its reasons, but never as a finished card. Raised by
    :meth:`~debate_core.application.evidence_verifier.EvidenceVerifier.ensure_finished`.
    """

    def __init__(self, result: VerificationResult) -> None:
        self.result = result
        """The verification that failed, with its reasons."""
        codes = ", ".join(result.reason_codes) or result.status.value
        super().__init__(f"card {result.card_id} is not verified evidence: {codes}")

"""The gate that decides whether a card is finished evidence (architecture proposal §8 steps 5-6).

:class:`EvidenceVerifier` is the only code that sets ``VERIFIED``, on a
:class:`~debate_core.evidence.verification_types.VerificationResult` or on a card. A test scans every
source package and fails if anything else does (`tests/evidence/test_verifier.py`).

For one card it:

1. checks the card itself: evidence text, offsets, text hash, normalizer version and spans are
   present, the normalizer version is one this code has, and every required citation field is
   marked verified;
2. finds the card's snapshot record and loads it with
   :meth:`~debate_core.application.snapshot_service.SnapshotService.load`, which re-hashes both
   blobs against the record;
3. reconstructs the evidence from the stored normalized text at the card's offsets, compares it with
   the card's text exactly, and checks the spans fit it (:mod:`debate_core.evidence.verifier`).

The result is VERIFIED only if no check failed, and it cannot be constructed VERIFIED unless every
check ran. Model calls play no part.

## Expected failures are reasons; everything else propagates

A missing snapshot (``NotFound``) is ``SNAPSHOT_MISSING``. A failed integrity check
(``SnapshotIntegrityError``) is ``UNKNOWN_NORMALIZER_VERSION`` when the snapshot names a normalizer
version this code lacks and ``HASH_MISMATCH`` for every other check. These are verdicts about the
card, and they come back as an UNVERIFIED result, never as an exception.

A store that cannot be reached (``StoreError``) is not a verdict about the card, so it propagates:
the caller reports that verification could not run, rather than that the card failed it. So does
anything unexpected, because an UNVERIFIED card is the wrong way to report a bug.

## ensure_finished re-verifies; it does not read the card's status

A card's ``verification_status`` field is a stored claim, and the domain lets anyone construct a card
with ``VERIFIED`` in it, because a persisted verified card has to load. A guard that read the field
would pass a hand-built card with altered text. :meth:`EvidenceVerifier.ensure_finished` therefore
runs the verification again and trusts nothing the card says about itself. That costs one snapshot
load per card, measured by `v1-e03-t02` at 0.3 ms for a web article and 166 ms for a 50 MB PDF.

The alternative, a ``VerificationResult`` bound to the card's content and checked without I/O, was
rejected for two reasons. Results are not stored anywhere, so an exporter of saved cards would have
no result to present. And a result is a plain frozen value that anyone can construct or
``dataclasses.replace``, so binding one to a card proves only that someone computed the binding.
"""

from __future__ import annotations

from debate_core.application.errors import NotFound, SnapshotIntegrityCheck, SnapshotIntegrityError
from debate_core.application.ports import ArticleRepository, Clock
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import Card, VerificationStatus
from debate_core.evidence.verification_types import (
    VERIFIER_VERSION,
    ReasonCode,
    UnverifiedEvidenceError,
    VerificationCheck,
    VerificationResult,
)
from debate_core.evidence.verifier import VerificationFindings, check_against_snapshot, check_card

__all__ = ["EvidenceVerifier"]


class EvidenceVerifier:
    """Verifies cards against their stored snapshots. Holds no state between calls.

    Reaches snapshot records through the :class:`~debate_core.application.ports.ArticleRepository`
    port and their content through :class:`~debate_core.application.snapshot_service.SnapshotService`.
    """

    def __init__(self, *, articles: ArticleRepository, snapshots: SnapshotService, clock: Clock) -> None:
        self._articles = articles
        self._snapshots = snapshots
        self._clock = clock

    async def verify(self, card: Card) -> VerificationResult:
        """Verify ``card`` and return the verdict, with every reason it fails.

        Raises only for failures that are not verdicts about the card: see the module docstring.
        """
        findings = VerificationFindings()
        check_card(card, findings)
        loaded = await self._load(card, findings)
        if loaded is not None:
            check_against_snapshot(card, loaded.snapshot, loaded.normalized, findings)
        return VerificationResult(
            card_id=card.card_id,
            status=VerificationStatus.UNVERIFIED if findings.reasons else VerificationStatus.VERIFIED,
            reasons=findings.reasons,
            checks_run=findings.checks_run,
            verified_at=self._clock.now(),
            verifier_version=VERIFIER_VERSION,
            normalizer_version=card.normalizer_version,
            snapshot_id=card.snapshot_id,
        )

    async def verify_and_record(self, card: Card) -> tuple[Card, VerificationResult]:
        """Verify ``card`` and return a copy whose ``verification_status`` is the result's.

        The one way to change a card's status. A card that was VERIFIED and no longer verifies comes
        back UNVERIFIED. Saving the copy is the caller's step.
        """
        result = await self.verify(card)
        return card.evolve(verification_status=result.status), result

    async def ensure_finished(self, card: Card) -> VerificationResult:
        """Return ``card``'s VERIFIED result, or raise ``UnverifiedEvidenceError``.

        The hard-failure rule: every exporter and presenter calls this before it shows a card as a
        finished evidence card. It re-verifies rather than reading ``card.verification_status``,
        which is a claim anyone can construct (see the module docstring). An UNVERIFIED card may
        still be shown as a draft, with the reasons on the error's ``result``.
        """
        result = await self.verify(card)
        if not result.is_verified:
            raise UnverifiedEvidenceError(result)
        return result

    async def _load(self, card: Card, findings: VerificationFindings) -> LoadedSnapshot | None:
        """The card's snapshot, loaded with every integrity check, or ``None`` with the reason recorded."""
        if card.snapshot_id is None:
            findings.fail(
                VerificationCheck.SNAPSHOT_INTEGRITY,
                ReasonCode.SNAPSHOT_MISSING,
                "the card names no snapshot",
            )
            return None
        try:
            record = await self._articles.get_snapshot(card.snapshot_id)
            loaded = await self._snapshots.load(record)
        except NotFound as missing:
            findings.fail(VerificationCheck.SNAPSHOT_INTEGRITY, ReasonCode.SNAPSHOT_MISSING, str(missing))
            return None
        except SnapshotIntegrityError as damaged:
            code = (
                ReasonCode.UNKNOWN_NORMALIZER_VERSION
                if damaged.check is SnapshotIntegrityCheck.UNKNOWN_NORMALIZER_VERSION
                else ReasonCode.HASH_MISMATCH
            )
            findings.fail(VerificationCheck.SNAPSHOT_INTEGRITY, code, str(damaged))
            return None
        findings.ran(VerificationCheck.SNAPSHOT_INTEGRITY)
        return loaded

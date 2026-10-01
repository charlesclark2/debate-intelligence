"""EvidenceVerifier: a card is VERIFIED only when its evidence comes back out of its snapshot exactly.

Tests are named so the plan's criteria can select them: ``-k finished`` runs the finished-evidence
guard (ac4). Every expected string, offset and reason below is worked out by hand from ``EXTRACTED``
and written down, never captured from the verifier (`docs/process/working-agreements.md` §6).
Snapshots are made and loaded through ``SnapshotService``; cards are cut by the extractor and mapped
by hand (``tests/fixtures/verification/verification_world.py``). The source is invented.

No test here uses Hypothesis. The single-character edits of ac2 are enumerated exhaustively instead,
with each expected offset taken from the edit's own position.
"""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import TypeGuard

import pytest
from tests.fixtures.verification.verification_world import VerificationWorld, run

from debate_core.application.errors import StoreUnavailable
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports import BlobKey
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import Card, CardSpan, SourceSnapshot, SpanPurpose, SpanStyle, VerificationStatus
from debate_core.evidence.markup import EvidenceMarkupSpan
from debate_core.evidence.normalization import NORMALIZER_VERSION, Paragraph, normalize
from debate_core.evidence.snapshot_text import SnapshotText, encode_snapshot_text
from debate_core.evidence.verification_types import (
    REQUIRED_CHECKS,
    VERIFIER_VERSION,
    ReasonCode,
    UnverifiedEvidenceError,
    VerificationCheck,
    VerificationReason,
    VerificationResult,
)
from debate_core.evidence.verifier import VerificationFindings, first_difference
from debate_core.testing import FAKE_EPOCH, InMemorySnapshotStore, SequentialIdGenerator
from debate_core.testing.builders import build_citation

#: Raw extracted text: CRLF breaks and a trailing newline, which normalization tidies.
EXTRACTED = (
    "Groundwater in the Tessaly basin fell 4 metres in a decade.\r\n\r\n"
    "Farmers there now pump twice what the aquifer recharges.\n\n"
    "Without new limits, the wells will run dry by 2040.\n"
)

#: What EXTRACTED normalizes to, by hand. "Groundwater in the Tessaly basin fell 4 metres in a
#: decade." is 59 characters (0-59), a break takes 59-61, "Farmers there now pump twice what the
#: aquifer recharges." is 56 (61-117), a break takes 117-119, and "Without new limits, the wells will
#: run dry by 2040." is 51 (119-170).
NORMALIZED = (
    "Groundwater in the Tessaly basin fell 4 metres in a decade.\n\n"
    "Farmers there now pump twice what the aquifer recharges.\n\n"
    "Without new limits, the wells will run dry by 2040."
)
PARAGRAPHS = (Paragraph("p0001", 0, 59), Paragraph("p0002", 61, 117), Paragraph("p0003", 119, 170))

#: Paragraph two, the evidence most tests cut: snapshot offsets 61-117.
FARMERS = "Farmers there now pump twice what the aquifer recharges."
#: Paragraph one, which has the only doubled letter in the text: the "ss" of "Tessaly" at 21-23.
GROUNDWATER = "Groundwater in the Tessaly basin fell 4 metres in a decade."

ALL_CHECKS = frozenset(VerificationCheck)
UNKNOWN_VERSION = "evidence-normalizer-v9"


@pytest.fixture
def world() -> VerificationWorld:
    return VerificationWorld()


@pytest.fixture
def source(world: VerificationWorld) -> LoadedSnapshot:
    return world.add_source(EXTRACTED)


@pytest.fixture
def card(world: VerificationWorld, source: LoadedSnapshot) -> Card:
    """Paragraph two, underlined throughout, with "pump twice" (snapshot 79-89) highlighted."""
    return world.cut_card(
        source,
        61,
        117,
        (
            EvidenceMarkupSpan.underline(61, 117, SpanPurpose.CLAIM),
            EvidenceMarkupSpan.highlight(79, 89, SpanPurpose.IMPACT),
        ),
    )


@pytest.fixture
def lightly_marked_card(world: VerificationWorld, source: LoadedSnapshot) -> Card:
    """Paragraph two with only "Farmers" (snapshot 61-68) underlined, so its span fits any edit of it."""
    return world.cut_card(source, 61, 117, (EvidenceMarkupSpan.underline(61, 68),))


def test_the_fixture_normalizes_to_the_hand_written_text_and_paragraphs(source: LoadedSnapshot) -> None:
    assert source.normalized.text == NORMALIZED
    assert source.normalized.paragraphs == PARAGRAPHS


def test_the_card_fixture_is_the_hand_written_evidence_and_spans(card: Card) -> None:
    assert card.evidence_text == FARMERS
    assert (card.evidence_start_offset, card.evidence_end_offset) == (61, 117)
    assert [(span.start_offset, span.end_offset, span.style) for span in card.spans] == [
        (0, 56, SpanStyle.UNDERLINE),
        (18, 28, SpanStyle.HIGHLIGHT),
    ]


# =============================================================================================
# A card cut by the extractor from an intact snapshot is VERIFIED (ac1)
# =============================================================================================


def test_a_card_cut_from_an_intact_snapshot_is_verified_with_no_reasons(
    world: VerificationWorld, card: Card, source: LoadedSnapshot
) -> None:
    result = world.verify(card)

    assert result.status is VerificationStatus.VERIFIED
    assert result.reasons == ()
    assert result.checks_run == ALL_CHECKS
    assert result.card_id == card.card_id
    assert result.snapshot_id == source.snapshot.snapshot_id
    assert result.normalizer_version == NORMALIZER_VERSION
    assert result.verifier_version == VERIFIER_VERSION == "evidence-verifier-v1"
    assert result.verified_at == FAKE_EPOCH


def test_a_card_crossing_a_paragraph_break_is_verified(
    world: VerificationWorld, source: LoadedSnapshot
) -> None:
    card = world.cut_card(source, 40, 89)

    assert card.evidence_text == "metres in a decade.\n\nFarmers there now pump twice"
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_card_quoting_the_whole_snapshot_is_verified(
    world: VerificationWorld, source: LoadedSnapshot
) -> None:
    card = world.cut_card(source, 0, 170)

    assert card.evidence_text == NORMALIZED
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_card_cut_from_raw_bytes_that_differ_from_the_extracted_text_is_verified(
    world: VerificationWorld,
) -> None:
    """The raw bytes are checked against their hash, not re-extracted (that is E04's), so a card's text
    only has to match the stored normalized text."""
    source = world.add_source(EXTRACTED, raw_bytes=b"<html><p>Groundwater in the Tessaly basin</p></html>")
    card = world.cut_card(source, 61, 117)

    result = world.verify(card)

    assert result.status is VerificationStatus.VERIFIED
    assert result.checks_run == ALL_CHECKS


def test_verify_and_record_sets_the_cards_status_from_the_result(
    world: VerificationWorld, card: Card
) -> None:
    recorded, result = run(world.verifier.verify_and_record(card))

    assert result.is_verified
    assert recorded.verification_status is VerificationStatus.VERIFIED
    assert recorded.evolve(verification_status=VerificationStatus.UNVERIFIED) == card


def test_verify_and_record_demotes_a_card_that_no_longer_verifies(
    world: VerificationWorld, card: Card
) -> None:
    claimed = card.evolve(verification_status=VerificationStatus.VERIFIED, evidence_text=FARMERS.upper())

    recorded, result = run(world.verifier.verify_and_record(claimed))

    assert result.reason_codes == (ReasonCode.TEXT_MISMATCH,)
    assert recorded.verification_status is VerificationStatus.UNVERIFIED


# =============================================================================================
# One changed, inserted or deleted character is TEXT_MISMATCH at the first differing offset (ac2)
# =============================================================================================
# Offsets are evidence-text coordinates: an index into the card's evidence_text. For these
# single-range cards the snapshot offset is evidence_start_offset (61) plus the index.


@pytest.mark.parametrize(
    ("edited", "first_differing_offset"),
    [
        pytest.param("Farmers there now pamp twice what the aquifer recharges.", 19, id="changed-u-of-pump"),
        pytest.param(
            "Farmerss there now pump twice what the aquifer recharges.", 7, id="inserted-after-farmers"
        ),
        pytest.param("Farmers there no pump twice what the aquifer recharges.", 16, id="deleted-w-of-now"),
        pytest.param("XFarmers there now pump twice what the aquifer recharges.", 0, id="inserted-at-start"),
        pytest.param("armers there now pump twice what the aquifer recharges.", 0, id="deleted-at-start"),
        pytest.param(
            "Farmers there now pump twice what the aquifer recharges", 55, id="deleted-final-period"
        ),
        pytest.param("Farmers there now pump twice what the aquifer recharges..", 56, id="appended-period"),
        pytest.param(
            "Farmers there now pump twice what the aquifer recharges!", 55, id="changed-final-period"
        ),
    ],
)
def test_one_edited_character_is_a_text_mismatch_at_the_first_differing_offset(
    world: VerificationWorld, lightly_marked_card: Card, edited: str, first_differing_offset: int
) -> None:
    result = world.verify(lightly_marked_card.evolve(evidence_text=edited))

    assert result.status is VerificationStatus.UNVERIFIED
    assert result.reasons == (
        VerificationReason(ReasonCode.TEXT_MISMATCH, result.reasons[0].detail, first_differing_offset),
    )


def test_a_deletion_inside_a_run_of_equal_characters_is_reported_where_the_run_ends(
    world: VerificationWorld, source: LoadedSnapshot
) -> None:
    """Deleting either "s" of "Tessaly" (19-26) gives "Tesaly". The texts agree through index 21 and first
    differ at 22, whichever "s" was removed: the offset is where the texts diverge, not which character
    was edited, because the two edits produce the same text."""
    card = world.cut_card(source, 0, 59, (EvidenceMarkupSpan.underline(0, 11),))
    assert card.evidence_text == GROUNDWATER

    result = world.verify(card.evolve(evidence_text=GROUNDWATER.replace("Tessaly", "Tesaly")))

    assert [(reason.code, reason.first_differing_offset) for reason in result.reasons] == [
        (ReasonCode.TEXT_MISMATCH, 22)
    ]


def test_the_mismatch_detail_names_code_points_and_never_quotes_the_text(
    world: VerificationWorld, lightly_marked_card: Card
) -> None:
    result = world.verify(lightly_marked_card.evolve(evidence_text=FARMERS.replace("pump", "pamp")))

    assert result.reasons[0].detail == (
        "evidence_text has U+0061 at offset 19 where the snapshot has U+0075; "
        "evidence_text is 56 characters, the snapshot's evidence 56"
    )


def _single_character_edits(text: str) -> Iterator[tuple[str, str, int]]:
    """Every single-character substitution, insertion and deletion of ``text`` whose first differing
    offset is the edit's own position, with that position.

    A substitution by "X" (absent from the text) differs where it is made. An insertion of "X" at i
    differs at i. A deletion at i differs at i unless the next character equals the deleted one; those
    are the runs covered by the hand-written test above, and are skipped here.
    """
    assert "X" not in text
    for index in range(len(text)):
        yield f"substitute {index}", text[:index] + "X" + text[index + 1 :], index
        if index == len(text) - 1 or text[index] != text[index + 1]:
            yield f"delete {index}", text[:index] + text[index + 1 :], index
    for index in range(len(text) + 1):
        yield f"insert {index}", text[:index] + "X" + text[index:], index


def test_every_single_character_edit_is_a_text_mismatch_at_its_own_offset(
    world: VerificationWorld, lightly_marked_card: Card
) -> None:
    edits = list(_single_character_edits(FARMERS))
    # 56 substitutions, 56 deletions (FARMERS has no doubled letter) and 57 insertions.
    assert len(edits) == 169

    wrong: list[str] = []
    for name, edited, offset in edits:
        result = world.verify(lightly_marked_card.evolve(evidence_text=edited))
        got = [(reason.code, reason.first_differing_offset) for reason in result.reasons]
        if result.status is not VerificationStatus.UNVERIFIED or got != [(ReasonCode.TEXT_MISMATCH, offset)]:
            wrong.append(f"{name}: {result.status} {got}")

    assert wrong == []


@pytest.mark.parametrize(
    ("card_text", "reconstructed", "expected"),
    [
        ("abc", "abc", None),
        ("abd", "abc", 2),
        ("ab", "abc", 2),
        ("abc", "ab", 2),
        ("", "a", 0),
        ("xbc", "abc", 0),
    ],
)
def test_first_difference(card_text: str, reconstructed: str, expected: int | None) -> None:
    assert first_difference(card_text, reconstructed) == expected


# =============================================================================================
# A missing snapshot, a tampered blob or an unknown normalizer version is a reason, not an
# exception (ac3)
# =============================================================================================

ABSENT_SNAPSHOT_ID = "0SNAP000000000000000000099"


def test_a_card_whose_snapshot_record_does_not_exist_is_snapshot_missing(
    world: VerificationWorld, card: Card
) -> None:
    result = world.verify(card.evolve(snapshot_id=ABSENT_SNAPSHOT_ID))

    assert result.status is VerificationStatus.UNVERIFIED
    assert result.reason_codes == (ReasonCode.SNAPSHOT_MISSING,)
    assert result.reasons[0].detail == f"SourceSnapshot not found: {ABSENT_SNAPSHOT_ID}"


def test_a_card_whose_snapshot_blobs_are_gone_is_snapshot_missing(source: LoadedSnapshot, card: Card) -> None:
    """The record is there; the store it points into is empty."""
    elsewhere = VerificationWorld()
    run(elsewhere.articles.save_snapshot(source.snapshot))

    result = elsewhere.verify(card)

    assert result.reason_codes == (ReasonCode.SNAPSHOT_MISSING,)
    assert result.reasons[0].detail.startswith("snapshot blob not found: ")


def test_a_tampered_raw_blob_is_a_hash_mismatch(
    world: VerificationWorld, source: LoadedSnapshot, card: Card
) -> None:
    world.blobs.corrupt(source.snapshot.raw_blob_key, b"Groundwater in the Tessaly basin rose.")

    result = world.verify(card)

    assert result.reason_codes == (ReasonCode.HASH_MISMATCH,)
    assert "raw_bytes_hash" in result.reasons[0].detail


def test_a_tampered_normalized_blob_is_a_hash_mismatch(
    world: VerificationWorld, source: LoadedSnapshot, card: Card
) -> None:
    """The replacement is a valid, canonical document whose text says something else."""
    forged = SnapshotText.from_normalized(
        normalize(EXTRACTED.replace("pump twice", "pump half"), NORMALIZER_VERSION)
    )
    world.blobs.corrupt(source.snapshot.normalized_blob_key, encode_snapshot_text(forged))

    result = world.verify(card)

    assert result.reason_codes == (ReasonCode.HASH_MISMATCH,)
    assert "normalized_blob_hash" in result.reasons[0].detail


class _StoreThatServesWhatItHolds(InMemorySnapshotStore):
    """A store whose own read check is missing, so only the snapshot service's re-hash stands."""

    def __init__(self, inner: InMemorySnapshotStore, replacements: dict[BlobKey, bytes]) -> None:
        super().__init__()
        self._inner = inner
        self._replacements = replacements

    async def get(self, key: BlobKey) -> bytes:
        if key in self._replacements:
            return self._replacements[key]
        return await self._inner.get(key)


def test_a_tampered_blob_served_by_a_store_that_does_not_check_is_still_a_hash_mismatch(
    world: VerificationWorld, source: LoadedSnapshot, card: Card
) -> None:
    lax = _StoreThatServesWhatItHolds(world.blobs, {source.snapshot.raw_blob_key: b"altered raw bytes"})
    verifier = EvidenceVerifier(
        articles=world.articles,
        snapshots=SnapshotService(blobs=lax, clock=world.clock, id_generator=SequentialIdGenerator()),
        clock=world.clock,
    )

    result = run(verifier.verify(card))

    assert result.reason_codes == (ReasonCode.HASH_MISMATCH,)
    assert "raw_bytes_hash" in result.reasons[0].detail


def test_a_card_under_an_unknown_normalizer_version_is_unverified_with_that_code(
    world: VerificationWorld, card: Card
) -> None:
    """The card's offsets were taken under a version this code lacks, and that is not the snapshot's."""
    result = world.verify(card.evolve(normalizer_version=UNKNOWN_VERSION))

    assert result.reason_codes == (ReasonCode.UNKNOWN_NORMALIZER_VERSION, ReasonCode.HASH_MISMATCH)
    assert VerificationCheck.EVIDENCE_RECONSTRUCTED not in result.checks_run


def test_a_snapshot_under_an_unknown_normalizer_version_is_unverified_with_that_code(
    world: VerificationWorld, source: LoadedSnapshot, card: Card
) -> None:
    future = source.snapshot.evolve(
        snapshot_id="0SNAP000000000000000000042", normalizer_version=UNKNOWN_VERSION
    )
    run(world.articles.save_snapshot(future))

    result = world.verify(card.evolve(snapshot_id=future.snapshot_id))

    assert result.reason_codes == (ReasonCode.UNKNOWN_NORMALIZER_VERSION,)
    assert "unknown_normalizer_version" in result.reasons[0].detail


class _UnreachableStore(InMemorySnapshotStore):
    async def get(self, key: BlobKey) -> bytes:
        raise StoreUnavailable("GetObject", key, "connection reset")


def test_a_store_that_cannot_be_reached_is_not_a_verdict_and_propagates(
    world: VerificationWorld, card: Card
) -> None:
    """Reporting UNVERIFIED would say the card failed a check that never ran."""
    verifier = EvidenceVerifier(
        articles=world.articles,
        snapshots=SnapshotService(
            blobs=_UnreachableStore(), clock=world.clock, id_generator=SequentialIdGenerator()
        ),
        clock=world.clock,
    )

    with pytest.raises(StoreUnavailable):
        run(verifier.verify(card))


class _SnapshotServiceWithABug(SnapshotService):
    async def load(self, snapshot: SourceSnapshot) -> LoadedSnapshot:
        raise RuntimeError("a bug, not a verdict")


def test_a_bug_while_loading_propagates_rather_than_becoming_an_unverified_card(
    world: VerificationWorld, card: Card
) -> None:
    verifier = EvidenceVerifier(
        articles=world.articles,
        snapshots=_SnapshotServiceWithABug(
            blobs=world.blobs, clock=world.clock, id_generator=SequentialIdGenerator()
        ),
        clock=world.clock,
    )

    with pytest.raises(RuntimeError, match="a bug, not a verdict"):
        run(verifier.verify(card))


class _RepositoryReturningTheWrongRecord:
    def __init__(self, record: SourceSnapshot) -> None:
        self._record = record

    async def get_snapshot(self, snapshot_id: str) -> SourceSnapshot:
        return self._record


def test_a_record_for_another_snapshot_is_a_bug_and_propagates(
    world: VerificationWorld, source: LoadedSnapshot, card: Card
) -> None:
    other = world.add_source("A different invented source entirely.")
    verifier = EvidenceVerifier(
        articles=_RepositoryReturningTheWrongRecord(other.snapshot),  # pyright: ignore[reportArgumentType]
        snapshots=world.snapshots,
        clock=world.clock,
    )

    with pytest.raises(ValueError, match="names snapshot"):
        run(verifier.verify(card))


class _SnapshotServiceServingOtherText(SnapshotService):
    """Returns the record with text that is not its own, as a broken load would."""

    async def load(self, snapshot: SourceSnapshot) -> LoadedSnapshot:
        loaded = await super().load(snapshot)
        other = SnapshotText.from_normalized(normalize(EXTRACTED.replace("2040", "2050"), NORMALIZER_VERSION))
        return dataclasses.replace(loaded, normalized=other)


def test_text_that_is_not_the_records_is_a_hash_mismatch_even_past_a_broken_load(
    world: VerificationWorld, card: Card
) -> None:
    """The extractor's own check (SnapshotTextMismatch) catches it; the verifier reports HASH_MISMATCH."""
    verifier = EvidenceVerifier(
        articles=world.articles,
        snapshots=_SnapshotServiceServingOtherText(
            blobs=world.blobs,
            clock=world.clock,
            id_generator=SequentialIdGenerator(),
        ),
        clock=world.clock,
    )

    result = run(verifier.verify(card))

    assert result.reason_codes == (ReasonCode.HASH_MISMATCH,)
    assert "text_hash" in result.reasons[0].detail
    assert VerificationCheck.EVIDENCE_TEXT_EXACT not in result.checks_run


# =============================================================================================
# The other reasons
# =============================================================================================


def test_a_card_with_no_spans_is_incomplete(world: VerificationWorld, card: Card) -> None:
    result = world.verify(card.evolve(spans=()))

    assert result.reason_codes == (ReasonCode.CARD_INCOMPLETE,)
    assert result.reasons[0].detail == "the card lacks at least one span"


def test_a_card_with_no_text_hash_is_incomplete(world: VerificationWorld, card: Card) -> None:
    result = world.verify(card.evolve(normalized_text_hash=None))

    assert result.reason_codes == (ReasonCode.CARD_INCOMPLETE,)


def test_a_card_with_no_normalizer_version_is_incomplete(world: VerificationWorld, card: Card) -> None:
    result = world.verify(card.evolve(normalizer_version=None))

    assert result.reason_codes == (ReasonCode.CARD_INCOMPLETE,)
    assert VerificationCheck.NORMALIZER_VERSION_KNOWN not in result.checks_run


def test_a_card_with_nothing_cut_is_incomplete_and_nothing_is_reconstructed(
    world: VerificationWorld, card: Card
) -> None:
    bare = card.evolve(evidence_text="", evidence_start_offset=None, evidence_end_offset=None, spans=())

    result = world.verify(bare)

    assert result.reason_codes == (ReasonCode.CARD_INCOMPLETE,)
    assert result.reasons[0].detail == "the card lacks evidence text and offsets, at least one span"
    assert VerificationCheck.EVIDENCE_RECONSTRUCTED not in result.checks_run


def test_a_card_with_nothing_cut_and_no_snapshot_is_incomplete_and_snapshot_missing(
    world: VerificationWorld, card: Card
) -> None:
    bare = card.evolve(
        snapshot_id=None, evidence_text="", evidence_start_offset=None, evidence_end_offset=None, spans=()
    )

    assert world.verify(bare).reason_codes == (ReasonCode.CARD_INCOMPLETE, ReasonCode.SNAPSHOT_MISSING)


def test_an_unverified_citation_is_citation_unverified(world: VerificationWorld, card: Card) -> None:
    result = world.verify(card.evolve(citation=build_citation(verified=False)))

    assert result.reason_codes == (ReasonCode.CITATION_UNVERIFIED,)
    assert result.reasons[0].detail == (
        "required citation fields not verified: authors, title, publication, published_at, canonical_url"
    )


def test_a_card_cut_from_other_text_is_a_hash_mismatch_and_is_not_compared(
    world: VerificationWorld, card: Card
) -> None:
    """The card's recorded text hash binds it to the exact text, even if its snapshot record were replaced."""
    other_hash = "0" * 64

    result = world.verify(card.evolve(normalized_text_hash=other_hash))

    assert result.reason_codes == (ReasonCode.HASH_MISMATCH,)
    assert VerificationCheck.EVIDENCE_RECONSTRUCTED not in result.checks_run


def test_offsets_past_the_end_of_the_text_are_span_out_of_range(world: VerificationWorld, card: Card) -> None:
    """The same 56 characters claimed at 150-206 of a 170-character text."""
    result = world.verify(card.evolve(evidence_start_offset=150, evidence_end_offset=206))

    assert result.reason_codes == (ReasonCode.SPAN_OUT_OF_RANGE,)
    assert result.reasons[0].detail.startswith(
        "the card's offsets [150, 206) do not select evidence from the snapshot's 170-character text: "
        "out_of_bounds"
    )


def test_a_span_past_the_end_of_the_evidence_is_span_out_of_range(
    world: VerificationWorld, card: Card
) -> None:
    """``model_copy`` skips the domain's own span check, as any unvalidated construction does."""
    overrun = card.model_copy(
        update={"spans": (CardSpan(start_offset=50, end_offset=60, style=SpanStyle.UNDERLINE),)}
    )

    result = world.verify(overrun)

    assert result.reason_codes == (ReasonCode.SPAN_OUT_OF_RANGE,)
    assert result.reasons[0].detail == "spans [50, 60) are not inside the 56-character evidence"


def test_text_appended_and_marked_is_a_text_mismatch_and_a_span_out_of_range(
    world: VerificationWorld, card: Card
) -> None:
    claimed = FARMERS + " It is already too late."
    highlight = CardSpan(start_offset=57, end_offset=80, style=SpanStyle.HIGHLIGHT)

    result = world.verify(card.evolve(evidence_text=claimed, spans=(*card.spans, highlight)))

    assert [(reason.code, reason.first_differing_offset) for reason in result.reasons] == [
        (ReasonCode.TEXT_MISMATCH, 56),
        (ReasonCode.SPAN_OUT_OF_RANGE, None),
    ]


def test_every_reason_is_reported_not_only_the_first(world: VerificationWorld, card: Card) -> None:
    result = world.verify(card.evolve(citation=build_citation(verified=False), evidence_text=FARMERS.lower()))

    assert result.reason_codes == (ReasonCode.CITATION_UNVERIFIED, ReasonCode.TEXT_MISMATCH)


# =============================================================================================
# A result's status is what its reasons and checks support
# =============================================================================================


def _result(
    status: VerificationStatus,
    reasons: tuple[VerificationReason, ...] = (),
    checks: frozenset[VerificationCheck] = ALL_CHECKS,
) -> VerificationResult:
    return VerificationResult(
        card_id="0CARD000000000000000000001",
        status=status,
        reasons=reasons,
        checks_run=checks,
        verified_at=FAKE_EPOCH,
        verifier_version=VERIFIER_VERSION,
        normalizer_version=NORMALIZER_VERSION,
        snapshot_id="0SNAP000000000000000000001",
    )


def test_a_verified_result_with_a_reason_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="cannot carry reasons"):
        _result(VerificationStatus.VERIFIED, (VerificationReason(ReasonCode.CARD_INCOMPLETE, "no spans"),))


def test_a_verified_result_that_skipped_a_check_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="not run: spans_inside_evidence"):
        _result(VerificationStatus.VERIFIED, checks=ALL_CHECKS - {VerificationCheck.SPANS_INSIDE_EVIDENCE})


def test_an_unverified_result_without_a_reason_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="must say why"):
        _result(VerificationStatus.UNVERIFIED)


def test_a_result_needs_an_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        dataclasses.replace(_result(VerificationStatus.VERIFIED), verified_at=datetime(2026, 1, 1))  # noqa: DTZ001


def test_a_first_differing_offset_belongs_to_a_text_mismatch_only() -> None:
    with pytest.raises(ValueError, match="TEXT_MISMATCH and only for it"):
        VerificationReason(ReasonCode.HASH_MISMATCH, "detail", 3)
    with pytest.raises(ValueError, match="TEXT_MISMATCH and only for it"):
        VerificationReason(ReasonCode.TEXT_MISMATCH, "detail")


def test_findings_that_skipped_a_check_have_not_passed_even_with_no_reasons() -> None:
    """The verifier's last line of defence against a code path that forgets to run a check."""
    findings = VerificationFindings()
    for check in REQUIRED_CHECKS - {VerificationCheck.EVIDENCE_TEXT_EXACT}:
        findings.ran(check)

    assert findings.reasons == ()
    assert not findings.passed
    findings.ran(VerificationCheck.EVIDENCE_TEXT_EXACT)
    assert findings.passed


# =============================================================================================
# ensure_finished: UNVERIFIED cards are never presented as finished (ac4)
# =============================================================================================


def test_ensure_finished_returns_the_verified_result_for_a_verified_card(
    world: VerificationWorld, card: Card
) -> None:
    result = world.ensure_finished(card)

    assert result.is_verified
    assert result.card_id == card.card_id


@pytest.mark.parametrize(
    ("change", "code"),
    [
        pytest.param(
            {"evidence_text": FARMERS.replace("twice", "thrice")}, ReasonCode.TEXT_MISMATCH, id="text"
        ),
        pytest.param({"snapshot_id": ABSENT_SNAPSHOT_ID}, ReasonCode.SNAPSHOT_MISSING, id="snapshot"),
        pytest.param({"spans": ()}, ReasonCode.CARD_INCOMPLETE, id="spans"),
        pytest.param({"citation": build_citation(verified=False)}, ReasonCode.CITATION_UNVERIFIED, id="cite"),
        pytest.param(
            {"evidence_start_offset": 150, "evidence_end_offset": 206},
            ReasonCode.SPAN_OUT_OF_RANGE,
            id="offsets",
        ),
    ],
)
def test_ensure_finished_raises_for_every_unverified_card(
    world: VerificationWorld, card: Card, change: dict[str, object], code: ReasonCode
) -> None:
    with pytest.raises(UnverifiedEvidenceError) as raised:
        world.ensure_finished(card.evolve(**change))

    assert raised.value.result.status is VerificationStatus.UNVERIFIED
    assert raised.value.result.reason_codes == (code,)
    assert str(raised.value) == f"card {card.card_id} is not verified evidence: {code.value}"


def test_ensure_finished_rejects_a_hand_built_card_claiming_verified_with_altered_text(
    world: VerificationWorld, card: Card
) -> None:
    """The domain lets anyone construct a card that says VERIFIED. The guard does not read the claim."""
    forged = Card(
        card_id=card.card_id,
        owner_id=card.owner_id,
        article_id=card.article_id,
        snapshot_id=card.snapshot_id,
        tag=card.tag,
        citation=card.citation,
        evidence_text="Farmers there now pump half what the aquifer recharges.",
        evidence_start_offset=card.evidence_start_offset,
        evidence_end_offset=card.evidence_end_offset,
        normalized_text_hash=card.normalized_text_hash,
        normalizer_version=card.normalizer_version,
        spans=(CardSpan(start_offset=0, end_offset=7, style=SpanStyle.UNDERLINE),),
        verification_status=VerificationStatus.VERIFIED,
        provenance_mode=card.provenance_mode,
    )
    assert forged.verification_status is VerificationStatus.VERIFIED
    assert forged.is_finished_evidence  # the field-reading property is fooled; the guard must not be

    with pytest.raises(UnverifiedEvidenceError) as raised:
        world.ensure_finished(forged)

    assert [(reason.code, reason.first_differing_offset) for reason in raised.value.result.reasons] == [
        (ReasonCode.TEXT_MISMATCH, 23)
    ]


def test_ensure_finished_rejects_a_card_claiming_verified_whose_snapshot_has_since_been_tampered_with(
    world: VerificationWorld, source: LoadedSnapshot, card: Card
) -> None:
    recorded, _ = run(world.verifier.verify_and_record(card))
    assert recorded.verification_status is VerificationStatus.VERIFIED
    world.blobs.corrupt(source.snapshot.raw_blob_key, b"replaced")

    with pytest.raises(UnverifiedEvidenceError) as raised:
        world.ensure_finished(recorded)

    assert raised.value.result.reason_codes == (ReasonCode.HASH_MISMATCH,)


def test_ensure_finished_judges_the_evidence_not_the_stored_status(
    world: VerificationWorld, card: Card
) -> None:
    """A card whose status field was never updated is still finished if its evidence verifies now."""
    assert card.verification_status is VerificationStatus.UNVERIFIED

    assert world.ensure_finished(card).is_verified


# =============================================================================================
# VERIFIED is set only by EvidenceVerifier (spec forbidden list)
# =============================================================================================

REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOTS = sorted((REPO_ROOT / "packages").glob("*/src"))
VERIFIER_MODULE = "debate_core/application/evidence_verifier.py"

#: Modules allowed to write a verification status, and why. An entry that matches nothing fails the
#: scan, so the list cannot go stale.
ALLOWED_WRITERS = {
    VERIFIER_MODULE: "the evidence verifier",
    "debate_core/testing/builders.py": (
        "build_card passes its caller's verification_status through for tests about verified cards; it "
        "defaults to UNVERIFIED and is test support that the application layer cannot import"
    ),
}

VALUE_USE = "VerificationStatus.VERIFIED used as a value"
STATUS_KEYWORD = "verification_status= keyword"
STATUS_ATTRIBUTE = "assignment to .verification_status"
STATUS_STRING = "string naming the status or its field"
RESULT_CONSTRUCTED = "VerificationResult constructed"


def status_writes(source: str) -> list[tuple[int, str]]:
    """Every place in ``source`` that could set a verification status, as ``(line, kind)``.

    Reading the status is fine: ``VerificationStatus.VERIFIED`` as an operand of a comparison is not
    reported, and neither is a keyword passing ``VerificationStatus.UNVERIFIED``. Everything else that
    touches the value, the field or the result type is.
    """
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if _is_status_member(node, "VERIFIED") and not isinstance(parents.get(node), ast.Compare):
            found.append((node.lineno, VALUE_USE))
        elif isinstance(node, ast.keyword) and node.arg == "verification_status":
            if not _is_status_member(node.value, "UNVERIFIED"):
                found.append((node.value.lineno, STATUS_KEYWORD))
        elif isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Attribute) and t.attr == "verification_status" for t in targets):
                found.append((node.lineno, STATUS_ATTRIBUTE))
        elif (
            isinstance(node, ast.Constant)
            and node.value in {"VERIFIED", "verification_status"}
            and not _is_docstring(node, parents)
            and not _is_enum_member_definition(node, parents)
        ):
            found.append((node.lineno, STATUS_STRING))
        elif isinstance(node, ast.Call) and _called_name(node.func) == "VerificationResult":
            found.append((node.lineno, RESULT_CONSTRUCTED))
    return sorted(found)


def _is_status_member(node: ast.AST, member: str) -> TypeGuard[ast.Attribute]:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == member
        and isinstance(node.value, ast.Name)
        and node.value.id == "VerificationStatus"
    )


def _is_docstring(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> bool:
    return isinstance(parents.get(node), ast.Expr)


def _is_enum_member_definition(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> bool:
    """``VERIFIED = "VERIFIED"`` inside ``class VerificationStatus``: the enum's own definition."""
    assign = parents.get(node)
    owner = parents.get(assign) if assign is not None else None
    return (
        isinstance(assign, ast.Assign)
        and isinstance(owner, ast.ClassDef)
        and owner.name == "VerificationStatus"
    )


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _scan_sources() -> dict[str, list[tuple[int, str]]]:
    writes: dict[str, list[tuple[int, str]]] = {}
    for root in SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            found = status_writes(path.read_text(encoding="utf-8"))
            if found:
                writes[path.relative_to(root).as_posix()] = found
    return writes


def test_verified_is_set_only_by_the_evidence_verifier() -> None:
    writes = _scan_sources()

    assert len(SOURCE_ROOTS) >= 4, "the scan did not find the source packages"
    verifier_kinds = {kind for _, kind in writes.get(VERIFIER_MODULE, [])}
    assert {VALUE_USE, STATUS_KEYWORD, RESULT_CONSTRUCTED} <= verifier_kinds, (
        "the scan did not see the verifier's own assignments, so it cannot be trusted to see others"
    )
    stale = sorted(set(ALLOWED_WRITERS) - set(writes))
    assert stale == [], f"allowed writers that no longer write a status: {stale}"
    offending = {module: found for module, found in writes.items() if module not in ALLOWED_WRITERS}
    assert offending == {}


@pytest.mark.parametrize(
    ("snippet", "kinds"),
    [
        ("card.evolve(verification_status=VerificationStatus.VERIFIED)", [VALUE_USE, STATUS_KEYWORD]),
        ("card.evolve(verification_status=status)", [STATUS_KEYWORD]),
        ("card.evolve(verification_status=VerificationStatus.UNVERIFIED)", []),
        ("card.model_copy(update={'verification_status': s})", [STATUS_STRING]),
        ("object.__setattr__(card, 'verification_status', s)", [STATUS_STRING]),
        ("card.verification_status = s", [STATUS_ATTRIBUTE]),
        ("status = VerificationStatus('VERIFIED')", [STATUS_STRING]),
        ("statuses = [VerificationStatus.VERIFIED]", [VALUE_USE]),
        ("VerificationResult(card_id=c, status=s)", [RESULT_CONSTRUCTED]),
        ("types.VerificationResult(card_id=c, status=s)", [RESULT_CONSTRUCTED]),
        ("ok = card.verification_status is VerificationStatus.VERIFIED", []),
        ("ok = card.verification_status == VerificationStatus.VERIFIED", []),
        ('"""A docstring that says VERIFIED."""', []),
        ('class VerificationStatus:\n    VERIFIED = "VERIFIED"', []),
        ('class SomethingElse:\n    VERIFIED = "VERIFIED"', [STATUS_STRING]),
    ],
)
def test_the_status_scan_recognises_writes_and_only_writes(snippet: str, kinds: list[str]) -> None:
    assert [kind for _, kind in status_writes(snippet)] == kinds


def test_the_status_scan_reads_real_source_files() -> None:
    """The verifier module parses and yields its writes, so a scan that read nothing would fail above."""
    path = next(root / VERIFIER_MODULE for root in SOURCE_ROOTS if (root / VERIFIER_MODULE).exists())
    assert status_writes(path.read_text(encoding="utf-8")) != []

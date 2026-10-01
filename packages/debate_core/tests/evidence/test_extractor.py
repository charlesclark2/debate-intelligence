"""Span-addressed evidence extraction: evidence comes out of the snapshot by offsets, or not at all.

Every expected string and offset below is worked out by hand from ``EXTRACTED`` and written down,
never captured from the extractor (`docs/process/working-agreements.md` §6). The source text is
invented. ``SnapshotText`` values are built from a normalizer result or through
``SnapshotService.load``, never by decoding hand-written bytes.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil
import re
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, NewType, TypeVar, cast, get_args, get_origin, get_type_hints

import pytest

import debate_core
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode, SourceSnapshot
from debate_core.evidence.extractor import (
    EvidenceExtractor,
    ExtractedEvidence,
    SnapshotTextCheck,
    SnapshotTextMismatch,
)
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan
from debate_core.evidence.normalization import (
    NORMALIZER_VERSION,
    Paragraph,
    UnknownNormalizerVersionError,
    normalize,
)
from debate_core.evidence.selection import (
    EvidenceSegment,
    EvidenceSelection,
    InvalidSelection,
    OffsetRange,
    OmittedRange,
    ParagraphId,
    ParagraphRun,
    SelectionProblem,
)
from debate_core.evidence.snapshot_text import SnapshotText
from debate_core.testing import FixedClock, InMemorySnapshotStore, SequentialIdGenerator
from debate_core.testing.builders import build_source_snapshot

#: Raw extracted text: CRLF breaks, a doubled space, a trailing newline.
EXTRACTED = (
    "Arctic methane is accelerating.\r\n\r\n"
    "Ocean heat  reached a new high.\n\n"
    "Permafrost holds twice the carbon of the atmosphere.\n"
)

#: What EXTRACTED normalizes to, by hand. Paragraph one is "Arctic methane is accelerating."
#: (31 characters, 0-31), a break at 31-33, "Ocean heat reached a new high." (30 characters, 33-63), a
#: break at 63-65, and "Permafrost holds twice the carbon of the atmosphere." (52 characters, 65-117).
NORMALIZED = (
    "Arctic methane is accelerating.\n\n"
    "Ocean heat reached a new high.\n\n"
    "Permafrost holds twice the carbon of the atmosphere."
)
PARAGRAPHS = (Paragraph("p0001", 0, 31), Paragraph("p0002", 33, 63), Paragraph("p0003", 65, 117))

P1, P2, P3 = ParagraphId("p0001"), ParagraphId("p0002"), ParagraphId("p0003")

extractor = EvidenceExtractor()


@pytest.fixture
def text() -> SnapshotText:
    return SnapshotText.from_normalized(normalize(EXTRACTED, NORMALIZER_VERSION))


@pytest.fixture
def snapshot(text: SnapshotText) -> SourceSnapshot:
    return snapshot_of(text.text)


def snapshot_of(normalized_text: str, normalizer_version: str = NORMALIZER_VERSION) -> SourceSnapshot:
    """A record whose ``normalized_text_hash`` really is the SHA-256 of ``normalized_text``."""
    return build_source_snapshot(normalized_text=normalized_text, normalizer_version=normalizer_version)


def test_the_fixture_normalizes_to_the_hand_written_text_and_paragraphs(text: SnapshotText) -> None:
    assert text.text == NORMALIZED
    assert text.paragraphs == PARAGRAPHS


def segments_of(evidence: ExtractedEvidence) -> list[tuple[int, int, str]]:
    return [(segment.start, segment.end, segment.text) for segment in evidence.segments]


def omissions_of(evidence: ExtractedEvidence) -> list[tuple[int, int]]:
    return [(omitted.start, omitted.end) for omitted in evidence.omitted_ranges]


# =============================================================================================
# Extraction by paragraph and by offset (ac1)
# =============================================================================================


def test_extract_one_paragraph_by_id(snapshot: SourceSnapshot, text: SnapshotText) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_paragraphs(P2))

    assert segments_of(evidence) == [(33, 63, "Ocean heat reached a new high.")]
    assert evidence.omitted_ranges == ()
    assert (evidence.start, evidence.end) == (33, 63)


def test_extract_by_offsets(snapshot: SourceSnapshot, text: SnapshotText) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_offsets((7, 14)))

    assert segments_of(evidence) == [(7, 14, "methane")]


def test_extract_a_range_ending_exactly_at_the_end_of_the_text(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_offsets((106, 117)))

    assert segments_of(evidence) == [(106, 117, "atmosphere.")]


def test_extract_a_paragraph_run_includes_the_breaks_between_its_paragraphs(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection((ParagraphRun(P1, P2),)))

    assert segments_of(evidence) == [
        (0, 63, "Arctic methane is accelerating.\n\nOcean heat reached a new high.")
    ]
    assert evidence.omitted_ranges == ()


def test_extract_an_offset_range_may_cross_a_paragraph_break(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_offsets((18, 43)))

    assert segments_of(evidence) == [(18, 43, "accelerating.\n\nOcean heat")]


def test_extract_records_the_snapshot_it_was_cut_from(snapshot: SourceSnapshot, text: SnapshotText) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_paragraphs(P1))

    assert evidence.snapshot_id == snapshot.snapshot_id
    assert evidence.normalized_text_hash == snapshot.normalized_text_hash
    assert evidence.normalizer_version == NORMALIZER_VERSION


def test_extract_through_a_verified_load(text: SnapshotText) -> None:
    """The route production takes: create, load (which re-hashes both blobs), then extract."""
    service = SnapshotService(
        blobs=InMemorySnapshotStore(), clock=FixedClock(), id_generator=SequentialIdGenerator("SNAP")
    )
    snapshot = run(
        service.create(
            article_id="0ART0000000000000000000001",
            raw_bytes=EXTRACTED.encode("utf-8"),
            extracted_text=EXTRACTED,
            canonical_url="https://example.org/climate/arctic-methane",
            retrieved_at=datetime(2026, 9, 30, 12, 5, tzinfo=UTC),
            extractor_version="fake-extractor/1.0",
            provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
            access_status=AccessStatus.ACCESSIBLE,
        )
    )
    loaded = run(service.load(snapshot))

    evidence = extractor.extract(
        loaded.snapshot,
        loaded.normalized,
        EvidenceSelection((OffsetRange(0, 6), ParagraphRun(P3, P3))),
    )

    assert segments_of(evidence) == [
        (0, 6, "Arctic"),
        (65, 117, "Permafrost holds twice the carbon of the atmosphere."),
    ]


# =============================================================================================
# Non-contiguous selections and omitted ranges (ac2)
# =============================================================================================


def test_extract_non_contiguous_paragraphs_records_the_cut_between_them(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_paragraphs(P1, P3))

    assert segments_of(evidence) == [
        (0, 31, "Arctic methane is accelerating."),
        (65, 117, "Permafrost holds twice the carbon of the atmosphere."),
    ]
    assert omissions_of(evidence) == [(31, 65)]


def test_extract_consecutive_paragraphs_listed_separately_omit_the_break_between_them(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    """Separate parts are separate selections: the break was not selected, so it is a cut."""
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_paragraphs(P1, P2))

    assert segments_of(evidence) == [
        (0, 31, "Arctic methane is accelerating."),
        (33, 63, "Ocean heat reached a new high."),
    ]
    assert omissions_of(evidence) == [(31, 33)]


def test_extract_mixed_paragraph_and_offset_parts(snapshot: SourceSnapshot, text: SnapshotText) -> None:
    evidence = extractor.extract(
        snapshot, text, EvidenceSelection((ParagraphRun(P3, P3), OffsetRange(0, 6), OffsetRange(44, 51)))
    )

    assert segments_of(evidence) == [
        (0, 6, "Arctic"),
        (44, 51, "reached"),
        (65, 117, "Permafrost holds twice the carbon of the atmosphere."),
    ]
    assert omissions_of(evidence) == [(6, 44), (51, 65)]


def test_extract_puts_parts_in_source_order_whatever_order_they_were_given_in(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    given_backwards = extractor.extract(snapshot, text, EvidenceSelection.of_offsets((65, 75), (0, 6)))
    given_forwards = extractor.extract(snapshot, text, EvidenceSelection.of_offsets((0, 6), (65, 75)))

    assert segments_of(given_backwards) == [(0, 6, "Arctic"), (65, 75, "Permafrost")]
    assert given_backwards == given_forwards


def test_extract_touching_ranges_are_one_segment_with_no_cut(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    """Nothing lies between them, so an ellipsis there would announce a cut that never happened."""
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_offsets((0, 6), (6, 14)))

    assert segments_of(evidence) == [(0, 14, "Arctic methane")]
    assert evidence.omitted_ranges == ()


def test_extract_pieces_alternate_segments_and_cuts_and_cuts_carry_no_text(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    evidence = extractor.extract(snapshot, text, EvidenceSelection.of_offsets((0, 6), (44, 51), (65, 75)))

    pieces = evidence.pieces()

    assert [type(piece) for piece in pieces] == [
        EvidenceSegment,
        OmittedRange,
        EvidenceSegment,
        OmittedRange,
        EvidenceSegment,
    ]
    assert [field.name for field in dataclasses.fields(OmittedRange)] == ["start", "end"]
    assert not hasattr(pieces[1], "text")


@pytest.mark.parametrize(
    ("parts", "problem"),
    [
        pytest.param(((0, 10), (5, 20)), SelectionProblem.OVERLAPPING, id="partial-overlap"),
        pytest.param(((0, 31), (5, 10)), SelectionProblem.OVERLAPPING, id="one-inside-another"),
        pytest.param(((5, 10), (5, 10)), SelectionProblem.OVERLAPPING, id="the-same-range-twice"),
        pytest.param(((5, 20), (0, 10)), SelectionProblem.OVERLAPPING, id="overlap-given-backwards"),
    ],
)
def test_extract_refuses_overlapping_offset_ranges(
    snapshot: SourceSnapshot,
    text: SnapshotText,
    parts: tuple[tuple[int, int], ...],
    problem: SelectionProblem,
) -> None:
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection.of_offsets(*parts))

    assert refused.value.problem is problem


@pytest.mark.parametrize(
    "parts",
    [
        pytest.param((ParagraphRun(P1, P1), ParagraphRun(P1, P1)), id="a-paragraph-twice"),
        pytest.param((ParagraphRun(P1, P1), OffsetRange(5, 10)), id="offsets-inside-a-selected-paragraph"),
        pytest.param((ParagraphRun(P1, P3), ParagraphRun(P2, P2)), id="a-paragraph-inside-a-run"),
        pytest.param((OffsetRange(25, 40), ParagraphRun(P2, P2)), id="offsets-into-the-next-paragraph"),
    ],
)
def test_extract_refuses_parts_that_overlap_once_paragraphs_are_resolved(
    snapshot: SourceSnapshot, text: SnapshotText, parts: tuple[OffsetRange | ParagraphRun, ...]
) -> None:
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection(parts))

    assert refused.value.problem is SelectionProblem.OVERLAPPING


def test_a_reversed_offset_range_is_refused() -> None:
    with pytest.raises(InvalidSelection) as refused:
        OffsetRange(10, 5)

    assert refused.value.problem is SelectionProblem.REVERSED_RANGE


def test_extract_refuses_a_reversed_paragraph_run(snapshot: SourceSnapshot, text: SnapshotText) -> None:
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection((ParagraphRun(P3, P1),)))

    assert refused.value.problem is SelectionProblem.REVERSED_RANGE


def test_extract_refuses_a_reversed_run_that_touches_another_part_instead_of_shortening_it(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    """p0002..p0001 would resolve to (33, 31). Joined to [20, 33), which ends where it starts, it
    would quietly turn the selection into [20, 31). Found by the arbitrary-selection property with
    the reversed-run check removed; every example test above still passed."""
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection((OffsetRange(20, 33), ParagraphRun(P2, P1))))

    assert refused.value.problem is SelectionProblem.REVERSED_RANGE


# =============================================================================================
# Refusals: nothing is clamped, nothing is guessed
# =============================================================================================


@pytest.mark.parametrize(
    "offsets",
    [
        pytest.param((110, 118), id="one-past-the-end"),
        pytest.param((117, 118), id="starting-at-the-end"),
        pytest.param((0, 118), id="the-whole-text-and-one-more"),
        pytest.param((200, 300), id="wholly-past-the-end"),
    ],
)
def test_extract_refuses_offsets_past_the_end_instead_of_clamping(
    snapshot: SourceSnapshot, text: SnapshotText, offsets: tuple[int, int]
) -> None:
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection.of_offsets(offsets))

    assert refused.value.problem is SelectionProblem.OUT_OF_BOUNDS


def test_extract_refuses_an_out_of_range_part_even_when_it_touches_a_valid_one(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    """Merging touching ranges must not carry an out-of-range end past the bounds check."""
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection.of_offsets((100, 117), (117, 120)))

    assert refused.value.problem is SelectionProblem.OUT_OF_BOUNDS


@pytest.mark.parametrize(
    ("start", "end", "problem"),
    [
        pytest.param(5, 5, SelectionProblem.EMPTY_RANGE, id="empty"),
        pytest.param(-1, 5, SelectionProblem.NOT_AN_OFFSET, id="negative-start"),
        pytest.param(True, 5, SelectionProblem.NOT_AN_OFFSET, id="bool-start"),
        pytest.param(0, 5.0, SelectionProblem.NOT_AN_OFFSET, id="float-end"),
        pytest.param("0", 5, SelectionProblem.NOT_AN_OFFSET, id="string-start"),
    ],
)
def test_an_offset_range_that_is_not_a_range_of_characters_is_refused(
    start: object, end: object, problem: SelectionProblem
) -> None:
    with pytest.raises(InvalidSelection) as refused:
        OffsetRange(cast("int", start), cast("int", end))

    assert refused.value.problem is problem


@pytest.mark.parametrize("paragraph_id", ["p0004", "p0000", "P1", "1", "p1"])
def test_extract_refuses_a_paragraph_id_not_in_the_map(
    snapshot: SourceSnapshot, text: SnapshotText, paragraph_id: str
) -> None:
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection.of_paragraphs(ParagraphId(paragraph_id)))

    assert refused.value.problem is SelectionProblem.UNKNOWN_PARAGRAPH


def test_extract_refuses_a_run_whose_last_paragraph_is_unknown(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(snapshot, text, EvidenceSelection((ParagraphRun(P1, ParagraphId("p0009")),)))

    assert refused.value.problem is SelectionProblem.UNKNOWN_PARAGRAPH


@pytest.mark.parametrize("paragraph_id", ["", 3, None])
def test_a_paragraph_id_that_is_not_a_non_empty_string_is_refused(paragraph_id: object) -> None:
    with pytest.raises(InvalidSelection) as refused:
        ParagraphRun(cast("ParagraphId", paragraph_id), P1)

    assert refused.value.problem is SelectionProblem.NOT_A_PARAGRAPH_ID


def test_an_empty_selection_is_refused() -> None:
    with pytest.raises(InvalidSelection) as refused:
        EvidenceSelection(())

    assert refused.value.problem is SelectionProblem.NO_PARTS


@pytest.mark.parametrize(
    "parts",
    [
        pytest.param(((0, 5),), id="a-bare-tuple"),
        pytest.param(("Arctic methane",), id="a-string"),
        pytest.param([OffsetRange(0, 5)], id="a-list-not-a-tuple"),
    ],
)
def test_a_selection_part_that_is_not_a_range_or_run_is_refused(parts: object) -> None:
    with pytest.raises(InvalidSelection) as refused:
        EvidenceSelection(cast("tuple[OffsetRange, ...]", parts))

    assert refused.value.problem is SelectionProblem.NOT_A_PART


def test_extract_refuses_text_in_place_of_a_snapshot_text(snapshot: SourceSnapshot) -> None:
    with pytest.raises(TypeError):
        extractor.extract(snapshot, cast("SnapshotText", NORMALIZED), EvidenceSelection.of_offsets((0, 6)))


# =============================================================================================
# The text must belong to the record, and the paragraph map to the text
# =============================================================================================


def test_extract_refuses_text_that_is_not_the_records(text: SnapshotText) -> None:
    other_snapshot = snapshot_of(NORMALIZED.replace("twice", "three times"))

    with pytest.raises(SnapshotTextMismatch) as refused:
        extractor.extract(other_snapshot, text, EvidenceSelection.of_offsets((0, 6)))

    assert refused.value.check is SnapshotTextCheck.TEXT_HASH
    assert refused.value.snapshot_id == other_snapshot.snapshot_id


def test_extract_refuses_text_under_another_normalizer_version_than_the_records(text: SnapshotText) -> None:
    snapshot = snapshot_of(text.text, "evidence-normalizer-v2")

    with pytest.raises(SnapshotTextMismatch) as refused:
        extractor.extract(snapshot, text, EvidenceSelection.of_offsets((0, 6)))

    assert refused.value.check is SnapshotTextCheck.NORMALIZER_VERSION


def test_extract_refuses_one_changed_character_in_the_text(text: SnapshotText) -> None:
    snapshot = snapshot_of(text.text)
    altered = dataclasses.replace(text, text=text.text.replace("twice", "twico"))

    with pytest.raises(SnapshotTextMismatch) as refused:
        extractor.extract(snapshot, altered, EvidenceSelection.of_offsets((0, 6)))

    assert refused.value.check is SnapshotTextCheck.TEXT_HASH


def test_extract_refuses_a_paragraph_boundary_moved_to_another_valid_offset(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    """The edit `v1-e03-t02` found only the blob hash notices: same text, same version, one boundary
    moved. Selecting p0002 would otherwise quote "cean heat reached a new high." from the source."""
    moved = dataclasses.replace(
        text, paragraphs=(Paragraph("p0001", 0, 31), Paragraph("p0002", 34, 63), Paragraph("p0003", 65, 117))
    )

    with pytest.raises(SnapshotTextMismatch) as refused:
        extractor.extract(snapshot, moved, EvidenceSelection.of_paragraphs(P2))

    assert refused.value.check is SnapshotTextCheck.PARAGRAPH_MAP


@pytest.mark.parametrize(
    "paragraphs",
    [
        pytest.param((Paragraph("p0001", 0, 31), Paragraph("p0002", 33, 63)), id="a-paragraph-dropped"),
        pytest.param(
            (Paragraph("p0001", 0, 31), Paragraph("p0003", 33, 63), Paragraph("p0002", 65, 117)),
            id="two-ids-swapped",
        ),
        pytest.param((Paragraph("p0001", 0, 117),), id="one-paragraph-for-the-whole-text"),
    ],
)
def test_extract_refuses_any_paragraph_map_the_text_does_not_have(
    snapshot: SourceSnapshot, text: SnapshotText, paragraphs: tuple[Paragraph, ...]
) -> None:
    altered = dataclasses.replace(text, paragraphs=paragraphs)

    with pytest.raises(SnapshotTextMismatch) as refused:
        extractor.extract(snapshot, altered, EvidenceSelection.of_paragraphs(P1))

    assert refused.value.check is SnapshotTextCheck.PARAGRAPH_MAP


def test_extract_by_offsets_does_not_depend_on_the_paragraph_map(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    """Offsets address the text directly, so a damaged map does not stop an offset selection."""
    moved = dataclasses.replace(text, paragraphs=(Paragraph("p0001", 0, 117),))

    evidence = extractor.extract(snapshot, moved, EvidenceSelection.of_offsets((7, 14)))

    assert segments_of(evidence) == [(7, 14, "methane")]


def test_extract_refuses_a_paragraph_from_text_under_an_unknown_normalizer_version() -> None:
    text = SnapshotText(text=NORMALIZED, normalizer_version="evidence-normalizer-v9", paragraphs=PARAGRAPHS)
    snapshot = snapshot_of(NORMALIZED, "evidence-normalizer-v9")

    with pytest.raises(UnknownNormalizerVersionError):
        extractor.extract(snapshot, text, EvidenceSelection.of_paragraphs(P1))


def test_extract_refuses_an_empty_paragraph_rather_than_letting_it_vanish_into_a_neighbour() -> None:
    """v1 never makes an empty paragraph, but its segmentation gives one to text holding two breaks in
    a row, so a map can pass the map check and still have one. Selected beside a range that ends where
    it starts, an empty part would merge away unnoticed; it is refused instead."""
    two_breaks = "A\n\n\n\nB"  # p0001 = [0, 1), p0002 = [3, 3), p0003 = [5, 6)
    text = SnapshotText(
        text=two_breaks,
        normalizer_version=NORMALIZER_VERSION,
        paragraphs=(Paragraph("p0001", 0, 1), Paragraph("p0002", 3, 3), Paragraph("p0003", 5, 6)),
    )
    snapshot = snapshot_of(two_breaks)

    with pytest.raises(InvalidSelection) as refused:
        extractor.extract(
            snapshot,
            text,
            EvidenceSelection((OffsetRange(0, 3), ParagraphRun(ParagraphId("p0002"), ParagraphId("p0002")))),
        )

    assert refused.value.problem is SelectionProblem.EMPTY_RANGE


# =============================================================================================
# ExtractedEvidence and EvidenceSegment hold their invariants however they are built
# =============================================================================================


def test_a_segment_reads_its_text_from_the_snapshot_text_at_its_offsets(text: SnapshotText) -> None:
    assert EvidenceSegment(text, 7, 14).text == "methane"


def test_a_segment_past_the_end_of_the_text_is_refused(text: SnapshotText) -> None:
    with pytest.raises(InvalidSelection) as refused:
        EvidenceSegment(text, 110, 118)

    assert refused.value.problem is SelectionProblem.OUT_OF_BOUNDS


def test_a_segment_needs_a_snapshot_text_not_a_string() -> None:
    with pytest.raises(TypeError):
        EvidenceSegment(cast("SnapshotText", NORMALIZED), 0, 6)


@pytest.mark.parametrize(
    ("ranges", "problem"),
    [
        pytest.param([(0, 10), (5, 20)], SelectionProblem.OVERLAPPING, id="overlapping"),
        pytest.param([(10, 20), (0, 5)], SelectionProblem.OVERLAPPING, id="out-of-order"),
        pytest.param([(0, 6), (6, 14)], SelectionProblem.SEGMENTS_TOUCH, id="touching"),
        pytest.param([], SelectionProblem.NO_PARTS, id="none"),
    ],
)
def test_evidence_built_directly_must_be_ordered_and_separated(
    snapshot: SourceSnapshot, text: SnapshotText, ranges: list[tuple[int, int]], problem: SelectionProblem
) -> None:
    with pytest.raises(InvalidSelection) as refused:
        ExtractedEvidence(snapshot, tuple(EvidenceSegment(text, start, end) for start, end in ranges))

    assert refused.value.problem is problem


def test_evidence_built_directly_must_come_from_one_text(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    twin = dataclasses.replace(text)

    with pytest.raises(ValueError, match="same SnapshotText"):
        ExtractedEvidence(snapshot, (EvidenceSegment(text, 0, 6), EvidenceSegment(twin, 7, 14)))


def test_evidence_built_directly_must_belong_to_its_record(text: SnapshotText) -> None:
    other_snapshot = snapshot_of("Something else entirely.")

    with pytest.raises(SnapshotTextMismatch):
        ExtractedEvidence(other_snapshot, (EvidenceSegment(text, 0, 6),))


# =============================================================================================
# No extractor entry point accepts evidence text (ac4)
# =============================================================================================

#: The modules whose whole public API is in scope: selection types, extraction, markup.
EXTRACTION_MODULES = (
    "debate_core.evidence.selection",
    "debate_core.evidence.extractor",
    "debate_core.evidence.markup",
)

#: The types extraction produces. Anything anywhere in debate_core that returns one is in scope too.
_PRODUCES_EVIDENCE = re.compile(
    r"\b(ExtractedEvidence|EvidenceSegment|EvidenceSelection|OffsetRange|ParagraphRun|OmittedRange"
    r"|CardMarkup|EvidenceMarkupSpan)\b"
)

#: String-typed parameters that are allowed because they are identifiers, not text.
_IDENTIFIER_TYPES: frozenset[object] = frozenset({ParagraphId})


#: Annotations that admit arbitrary text outright.
_TEXT_TYPES: tuple[object, ...] = (str, bytes, bytearray, memoryview, object, Any)


def admits_free_text(annotation: object) -> bool:
    """True if a value of this annotation could carry arbitrary text into the extractor.

    Fails closed: anything it does not recognise as safe counts as text.
    """
    if annotation in _IDENTIFIER_TYPES:
        return False
    if isinstance(annotation, NewType):
        return True  # a new string alias would otherwise slip past as "not str"
    if any(annotation is text_type for text_type in _TEXT_TYPES) or isinstance(annotation, TypeVar):
        return True
    origin = get_origin(annotation)
    if origin is Literal:
        return any(isinstance(argument, str | bytes) for argument in get_args(annotation))
    if origin is not None:
        return any(
            admits_free_text(argument) for argument in get_args(annotation) if argument is not Ellipsis
        )
    if annotation is type(None):
        return False
    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            return False
        return issubclass(annotation, str | bytes)
    return True


def _parameters(function: Callable[..., object]) -> Iterator[tuple[str, object]]:
    hints = get_type_hints(function)
    for name, parameter in inspect.signature(function).parameters.items():
        if name in {"self", "cls"}:
            continue
        if parameter.annotation is inspect.Parameter.empty:
            yield name, Any
        else:
            yield name, hints[name]


def _methods(cls: type, qualified: str) -> Iterator[tuple[str, Callable[..., object]]]:
    """A class's constructor, if it defines one, and its public methods, classmethods and staticmethods."""
    for member_name, member in vars(cls).items():
        function = getattr(member, "__func__", member)  # unwrap classmethod/staticmethod
        if not inspect.isfunction(function):
            continue
        # A class without its own __init__ has object's, which takes nothing.
        if member_name == "__init__" or not member_name.startswith("_"):
            yield f"{qualified}.{member_name}", function


def _module_entry_points(module_name: str) -> Iterator[tuple[str, Callable[..., object]]]:
    module = importlib.import_module(module_name)
    for name in module.__all__:
        value: object = getattr(module, name)
        qualified = f"{module_name}.{name}"
        if inspect.isclass(value):
            if issubclass(value, BaseException | Enum):
                continue  # messages are not cards; enums take no text
            yield from _methods(value, qualified)
        elif inspect.isfunction(value):
            yield qualified, value


#: The extraction result types. A subclass of one anywhere in debate_core is in scope.
_EXTRACTION_TYPES = (
    ExtractedEvidence,
    EvidenceSegment,
    EvidenceSelection,
    OffsetRange,
    ParagraphRun,
    CardMarkup,
    EvidenceMarkupSpan,
)


def _debate_core_producers() -> Iterator[tuple[str, Callable[..., object]]]:
    """Every callable in debate_core that returns an extraction type, or constructs a subclass of one."""
    for module_info in pkgutil.walk_packages(debate_core.__path__, prefix="debate_core."):
        module = importlib.import_module(module_info.name)
        for name, value in vars(module).items():
            if getattr(value, "__module__", None) != module.__name__:
                continue
            qualified = f"{module.__name__}.{name}"
            if inspect.isclass(value):
                for member_name, function in _methods(value, qualified):
                    constructs = member_name.endswith(".__init__") and issubclass(value, _EXTRACTION_TYPES)
                    if constructs or _returns_extraction_type(function):
                        yield member_name, function
            elif inspect.isfunction(value) and _returns_extraction_type(value):
                yield qualified, value


def _returns_extraction_type(function: Callable[..., object]) -> bool:
    return bool(_PRODUCES_EVIDENCE.search(str(inspect.signature(function, eval_str=False).return_annotation)))


def free_text_parameters(
    entry_points: Iterator[tuple[str, Callable[..., object]]],
) -> tuple[set[str], list[str]]:
    seen: set[str] = set()
    offending: list[str] = []
    for qualified, function in entry_points:
        seen.add(qualified)
        for name, annotation in _parameters(function):
            if admits_free_text(annotation):
                offending.append(f"{qualified}({name}: {annotation!r})")
    return seen, offending


def test_no_public_extraction_api_has_a_parameter_that_accepts_free_text() -> None:
    """Every public callable in selection, extraction and markup takes ids, offsets, enums and typed values.

    Exceptions are skipped: an error message never reaches a card. ``SnapshotText`` and
    ``SourceSnapshot`` are structured inputs whose own constructors take text; their provenance is
    the caller's to guarantee (see the extractor's module docstring), not something a signature can.
    """
    seen: set[str] = set()
    offending: list[str] = []
    for module_name in EXTRACTION_MODULES:
        module_seen, module_offending = free_text_parameters(_module_entry_points(module_name))
        seen |= module_seen
        offending += module_offending

    assert {
        "debate_core.evidence.extractor.EvidenceExtractor.extract",
        "debate_core.evidence.extractor.ExtractedEvidence.__init__",
        "debate_core.evidence.selection.EvidenceSegment.__init__",
        "debate_core.evidence.selection.EvidenceSelection.__init__",
        "debate_core.evidence.selection.ParagraphRun.__init__",
        "debate_core.evidence.markup.CardMarkup.__init__",
        "debate_core.evidence.markup.EvidenceMarkupSpan.__init__",
        "debate_core.evidence.markup.EvidenceMarkupSpan.underline",
    } <= seen, "the scan did not see the entry points it exists to check"
    assert offending == []


def test_nothing_in_debate_core_produces_extracted_evidence_from_free_text() -> None:
    """A convenience constructor added anywhere else, such as an ``ExtractedEvidence.from_text`` in the
    application layer, fails here even though it is outside the extraction modules."""
    seen, offending = free_text_parameters(_debate_core_producers())

    assert "debate_core.evidence.extractor.EvidenceExtractor.extract" in seen, "the scan saw nothing"
    assert offending == []


@pytest.mark.parametrize(
    ("annotation", "admits"),
    [
        (str, True),
        (str | None, True),
        (tuple[str, ...], True),
        (bytes, True),
        (object, True),
        (Any, True),
        (Literal["quote"], True),
        (NewType("Quote", str), True),
        (ParagraphId, False),
        (int, False),
        (tuple[int, int], False),
        (int | None, False),
        (SelectionProblem, False),
        (SnapshotText, False),
        (tuple[OffsetRange | ParagraphRun, ...], False),
    ],
)
def test_the_free_text_check_recognises_text_and_only_text(annotation: object, admits: bool) -> None:
    assert admits_free_text(annotation) is admits


# =============================================================================================
# Helpers
# =============================================================================================


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion; the in-memory stores never suspend."""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("an in-memory store suspended; fakes must not perform real I/O")

"""Markup over extracted evidence: inside the evidence, never across a cut, never doubled up.

The source is the invented three-paragraph text of ``test_extractor.py``, normalized. Word offsets,
worked out by hand (`docs/process/working-agreements.md` §6):

* p0001 ``[0, 31)``: "Arctic" 0-6, "methane" 7-14, "is" 15-17, "accelerating." 18-31;
* p0003 ``[65, 117)``: "Permafrost" 65-75, "holds" 76-81, "twice" 82-87, "the" 88-91,
  "carbon" 92-98, "of" 99-101, "the" 102-105, "atmosphere." 106-117.

Most tests mark up the evidence cut from p0001 and p0003, with the cut at ``[31, 65)``.
"""

from __future__ import annotations

from typing import cast

import pytest

from debate_core.domain import SourceSnapshot, SpanPurpose, SpanStyle
from debate_core.evidence.extractor import EvidenceExtractor, ExtractedEvidence
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan, InvalidMarkup, MarkupProblem
from debate_core.evidence.normalization import NORMALIZER_VERSION, normalize
from debate_core.evidence.selection import EvidenceSelection, ParagraphId
from debate_core.evidence.snapshot_text import SnapshotText
from debate_core.testing.builders import build_source_snapshot

EXTRACTED = (
    "Arctic methane is accelerating.\r\n\r\n"
    "Ocean heat  reached a new high.\n\n"
    "Permafrost holds twice the carbon of the atmosphere.\n"
)
NORMALIZED = (
    "Arctic methane is accelerating.\n\n"
    "Ocean heat reached a new high.\n\n"
    "Permafrost holds twice the carbon of the atmosphere."
)

underline = EvidenceMarkupSpan.underline
highlight = EvidenceMarkupSpan.highlight


@pytest.fixture
def text() -> SnapshotText:
    stored = SnapshotText.from_normalized(normalize(EXTRACTED, NORMALIZER_VERSION))
    assert stored.text == NORMALIZED
    return stored


@pytest.fixture
def snapshot(text: SnapshotText) -> SourceSnapshot:
    return build_source_snapshot(normalized_text=text.text, normalizer_version=NORMALIZER_VERSION)


@pytest.fixture
def evidence(snapshot: SourceSnapshot, text: SnapshotText) -> ExtractedEvidence:
    """p0001 and p0003, with the cut between them at [31, 65)."""
    return EvidenceExtractor().extract(
        snapshot, text, EvidenceSelection.of_paragraphs(ParagraphId("p0001"), ParagraphId("p0003"))
    )


def marked(markup: CardMarkup, style: SpanStyle) -> list[str]:
    return [NORMALIZED[span.start : span.end] for span in markup.of_style(style)]


# =============================================================================================
# Markup that fits
# =============================================================================================


def test_markup_inside_both_segments_is_accepted_with_its_purposes(evidence: ExtractedEvidence) -> None:
    markup = CardMarkup(
        evidence,
        (
            underline(82, 117, SpanPurpose.IMPACT),
            underline(7, 31, SpanPurpose.WARRANT),
            highlight(82, 98, SpanPurpose.IMPACT),
            highlight(7, 14),
        ),
    )

    assert marked(markup, SpanStyle.UNDERLINE) == [
        "methane is accelerating.",
        "twice the carbon of the atmosphere.",
    ]
    assert marked(markup, SpanStyle.HIGHLIGHT) == ["methane", "twice the carbon"]
    assert [span.purpose for span in markup.of_style(SpanStyle.UNDERLINE)] == [
        SpanPurpose.WARRANT,
        SpanPurpose.IMPACT,
    ]


def test_markup_records_snapshot_offsets_not_offsets_into_the_evidence(evidence: ExtractedEvidence) -> None:
    """ "twice" is character 17 of the second segment and 48 of the joined evidence; it is recorded at
    82, where it is in the snapshot."""
    markup = CardMarkup(evidence, (underline(82, 87),))

    (span,) = markup.spans
    assert (span.start, span.end) == (82, 87)
    assert NORMALIZED[span.start : span.end] == "twice"


def test_markup_may_cover_a_whole_segment_exactly(evidence: ExtractedEvidence) -> None:
    CardMarkup(evidence, (underline(0, 31), underline(65, 117), highlight(65, 117)))


def test_markup_may_be_empty(evidence: ExtractedEvidence) -> None:
    assert CardMarkup(evidence, ()).spans == ()


def test_markup_spans_of_one_style_may_touch(evidence: ExtractedEvidence) -> None:
    markup = CardMarkup(evidence, (underline(0, 6), underline(6, 14)))

    assert marked(markup, SpanStyle.UNDERLINE) == ["Arctic", " methane"]


def test_a_highlight_may_run_across_touching_underlines(evidence: ExtractedEvidence) -> None:
    CardMarkup(evidence, (underline(0, 6), underline(6, 14), highlight(3, 10)))


# =============================================================================================
# Spans that are not spans
# =============================================================================================


@pytest.mark.parametrize(
    ("start", "end", "problem"),
    [
        pytest.param(5, 5, MarkupProblem.EMPTY_SPAN, id="empty"),
        pytest.param(10, 5, MarkupProblem.REVERSED_SPAN, id="reversed"),
        pytest.param(-1, 5, MarkupProblem.NOT_AN_OFFSET, id="negative"),
        pytest.param(False, 5, MarkupProblem.NOT_AN_OFFSET, id="bool"),
        pytest.param(0, 5.0, MarkupProblem.NOT_AN_OFFSET, id="float"),
    ],
)
def test_a_span_that_marks_no_characters_is_refused(
    start: object, end: object, problem: MarkupProblem
) -> None:
    with pytest.raises(InvalidMarkup) as refused:
        underline(cast("int", start), cast("int", end))

    assert refused.value.problem is problem


def test_a_style_given_as_a_string_is_refused() -> None:
    with pytest.raises(InvalidMarkup) as refused:
        EvidenceMarkupSpan(0, 6, cast("SpanStyle", "underline"))

    assert refused.value.problem is MarkupProblem.NOT_A_STYLE


def test_a_purpose_given_as_a_string_is_refused() -> None:
    with pytest.raises(InvalidMarkup) as refused:
        underline(0, 6, cast("SpanPurpose", "claim"))

    assert refused.value.problem is MarkupProblem.NOT_A_PURPOSE


def test_markup_spans_must_be_a_tuple_of_spans(evidence: ExtractedEvidence) -> None:
    with pytest.raises(InvalidMarkup) as refused:
        CardMarkup(evidence, cast("tuple[EvidenceMarkupSpan, ...]", [underline(0, 6)]))

    assert refused.value.problem is MarkupProblem.NOT_A_SPAN


# =============================================================================================
# Out of the evidence's bounds (ac3)
# =============================================================================================


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(106, 118, id="one-past-the-end"),
        pytest.param(117, 120, id="wholly-past-the-end"),
    ],
)
def test_markup_past_the_end_of_the_evidence_is_refused_not_trimmed(
    evidence: ExtractedEvidence, start: int, end: int
) -> None:
    with pytest.raises(InvalidMarkup) as refused:
        CardMarkup(evidence, (underline(start, end),))

    assert refused.value.problem is MarkupProblem.OUTSIDE_EVIDENCE


def test_markup_before_the_start_of_the_evidence_is_refused(
    snapshot: SourceSnapshot, text: SnapshotText
) -> None:
    only_p3 = EvidenceExtractor().extract(
        snapshot, text, EvidenceSelection.of_paragraphs(ParagraphId("p0003"))
    )

    with pytest.raises(InvalidMarkup) as refused:
        CardMarkup(only_p3, (underline(0, 6),))

    assert refused.value.problem is MarkupProblem.OUTSIDE_EVIDENCE


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(18, 70, id="across-the-cut"),
        pytest.param(40, 50, id="wholly-inside-the-cut"),
        pytest.param(31, 65, id="exactly-the-cut"),
        pytest.param(30, 32, id="one-character-into-the-cut"),
        pytest.param(64, 70, id="one-character-before-the-second-segment"),
    ],
)
def test_markup_over_omitted_text_is_refused(evidence: ExtractedEvidence, start: int, end: int) -> None:
    """Underlining across a cut would mark words the card does not contain."""
    with pytest.raises(InvalidMarkup) as refused:
        CardMarkup(evidence, (underline(start, end),))

    assert refused.value.problem is MarkupProblem.CROSSES_OMITTED_TEXT


def test_a_highlight_over_omitted_text_is_refused_for_that_and_not_for_lacking_an_underline(
    evidence: ExtractedEvidence,
) -> None:
    with pytest.raises(InvalidMarkup) as refused:
        CardMarkup(evidence, (underline(0, 31), highlight(20, 40)))

    assert refused.value.problem is MarkupProblem.CROSSES_OMITTED_TEXT


# =============================================================================================
# Overlap within a style (ac3)
# =============================================================================================


@pytest.mark.parametrize(
    "spans",
    [
        pytest.param((underline(0, 10), underline(5, 20)), id="underlines-partly"),
        pytest.param((underline(0, 31), underline(7, 14)), id="an-underline-inside-another"),
        pytest.param((underline(7, 14), underline(7, 14)), id="the-same-underline-twice"),
        pytest.param((underline(65, 117), underline(0, 31), underline(70, 80)), id="underlines-out-of-order"),
        pytest.param(
            (underline(0, 31), highlight(0, 10), highlight(5, 14)),
            id="highlights-partly",
        ),
        pytest.param(
            (underline(0, 31), highlight(7, 14), highlight(7, 14, SpanPurpose.CLAIM)),
            id="the-same-highlight-twice-with-different-purposes",
        ),
    ],
)
def test_spans_of_one_style_that_share_a_character_are_refused(
    evidence: ExtractedEvidence, spans: tuple[EvidenceMarkupSpan, ...]
) -> None:
    with pytest.raises(InvalidMarkup) as refused:
        CardMarkup(evidence, spans)

    assert refused.value.problem is MarkupProblem.OVERLAPS_SAME_STYLE


# =============================================================================================
# Highlighting lies within underlining
# =============================================================================================


@pytest.mark.parametrize(
    "spans",
    [
        pytest.param((highlight(7, 14),), id="no-underline-at-all"),
        pytest.param((underline(7, 14), highlight(7, 20)), id="running-past-the-underline"),
        pytest.param((underline(7, 14), highlight(0, 10)), id="starting-before-the-underline"),
        pytest.param(
            (underline(0, 6), underline(7, 14), highlight(3, 10)), id="across-a-gap-between-underlines"
        ),
        pytest.param((underline(0, 31), highlight(82, 87)), id="under-another-segments-underline"),
    ],
)
def test_a_highlight_that_is_not_wholly_underlined_is_refused(
    evidence: ExtractedEvidence, spans: tuple[EvidenceMarkupSpan, ...]
) -> None:
    with pytest.raises(InvalidMarkup) as refused:
        CardMarkup(evidence, spans)

    assert refused.value.problem is MarkupProblem.HIGHLIGHT_NOT_UNDERLINED

"""Tests for `debate_core.evidence.run_segmentation`: CardSpans to runs, and where the cuts go (`v1-e06-t04`).

The renderer formats a card's evidence run by run, and every run boundary comes from here: a span's
edge, an omitted range's place in `evidence_text`, or an interpolation's anchor. The expected runs in
the examples are written by hand from the spans; the properties compare against an oracle written
from the rules (a character's styles are the styles of the spans covering it), not from the code.

Example count comes from ``RUN_SEGMENTATION_PROPERTY_EXAMPLES`` (default 300). The generators record
``event``s, so ``--hypothesis-show-statistics`` shows how often overlapping spans, breaks inside a
run, and cards with both an omission and an interpolation at one place are produced.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from debate_core.domain import Card, CardOmission, CardSpan, Interpolation, SpanStyle
from debate_core.evidence.run_segmentation import (
    EvidencePiece,
    EvidenceRun,
    InterpolationMark,
    OmissionMark,
    lay_out_evidence,
    omission_offsets,
    segment_runs,
)
from debate_core.testing.builders import build_card

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("RUN_SEGMENTATION_PROPERTY_EXAMPLES", "300")), deadline=None
)

U = SpanStyle.UNDERLINE
H = SpanStyle.HIGHLIGHT


def span(start: int, end: int, style: SpanStyle) -> CardSpan:
    return CardSpan(start_offset=start, end_offset=end, style=style)


def run(start: int, end: int, *styles: SpanStyle) -> EvidenceRun:
    return EvidenceRun(start, end, frozenset(styles))


# --------------------------------------------------------------------------------------------
# segment_runs: examples written by hand
# --------------------------------------------------------------------------------------------


def test_evidence_with_no_spans_is_one_condensed_run() -> None:
    assert segment_runs(12, ()) == (run(0, 12),)
    assert segment_runs(12, ())[0].condensed


def test_no_evidence_is_no_runs() -> None:
    assert segment_runs(0, ()) == ()


def test_overlapping_underline_and_highlight_split_where_either_starts_or_ends() -> None:
    spans = (span(2, 10, U), span(5, 8, H))

    assert segment_runs(20, spans) == (
        run(0, 2),
        run(2, 5, U),
        run(5, 8, U, H),
        run(8, 10, U),
        run(10, 20),
    )


def test_a_highlight_that_runs_past_the_underline_keeps_only_the_highlight_there() -> None:
    assert segment_runs(10, (span(0, 4, U), span(2, 7, H))) == (
        run(0, 2, U),
        run(2, 4, U, H),
        run(4, 7, H),
        run(7, 10),
    )


def test_two_touching_spans_of_one_style_are_one_run() -> None:
    assert segment_runs(10, (span(0, 5, U), span(5, 10, U))) == (run(0, 10, U),)


def test_a_break_splits_a_run_with_the_same_styles_either_side() -> None:
    assert segment_runs(20, (span(2, 10, U),), breaks=(6, 12)) == (
        run(0, 2),
        run(2, 6, U),
        run(6, 10, U),
        run(10, 12),
        run(12, 20),
    )


def test_a_break_at_an_edge_or_on_a_span_edge_adds_no_empty_run() -> None:
    assert segment_runs(10, (span(2, 5, U),), breaks=(0, 2, 5, 10, 5)) == (
        run(0, 2),
        run(2, 5, U),
        run(5, 10),
    )


def test_unread_text_is_condensed_and_read_text_is_not() -> None:
    runs = segment_runs(10, (span(0, 3, U), span(6, 8, H)))

    assert [r.condensed for r in runs] == [False, True, False, True]


@pytest.mark.parametrize(
    ("spans", "breaks", "problem"),
    [
        ((span(5, 11, U),), (), "runs past the end of the evidence"),
        ((), (11,), "outside the evidence"),
        ((), (-1,), "outside the evidence"),
    ],
)
def test_a_span_or_break_outside_the_evidence_is_refused(
    spans: tuple[CardSpan, ...], breaks: tuple[int, ...], problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        segment_runs(10, spans, breaks=breaks)


# --------------------------------------------------------------------------------------------
# segment_runs: properties
# --------------------------------------------------------------------------------------------


@st.composite
def spans_and_breaks(draw: st.DrawFn) -> tuple[int, list[CardSpan], list[int]]:
    length = draw(st.integers(min_value=0, max_value=60))
    spans: list[CardSpan] = []
    if length:
        for _ in range(draw(st.integers(min_value=0, max_value=6))):
            start = draw(st.integers(min_value=0, max_value=length - 1))
            end = draw(st.integers(min_value=start + 1, max_value=length))
            spans.append(span(start, end, draw(st.sampled_from([U, H]))))
    breaks = draw(st.lists(st.integers(min_value=0, max_value=length), max_size=5))
    if any(a.overlaps(b) for i, a in enumerate(spans) for b in spans[i + 1 :] if a.style is not b.style):
        event("an underline and a highlight overlap")
    if any(0 < b < length and not any(b in (s.start_offset, s.end_offset) for s in spans) for b in breaks):
        event("a break falls where no span starts or ends")
    return length, spans, breaks


def styles_at(offset: int, spans: list[CardSpan]) -> frozenset[SpanStyle]:
    """The oracle: a character carries the style of every span that covers it."""
    return frozenset(s.style for s in spans if s.start_offset <= offset < s.end_offset)


@PROPERTY_SETTINGS
@given(spans_and_breaks())
def test_runs_tile_the_evidence_and_carry_exactly_the_styles_of_the_spans_over_them(
    case: tuple[int, list[CardSpan], list[int]],
) -> None:
    length, spans, breaks = case
    runs = segment_runs(length, spans, breaks=breaks)

    position = 0
    for evidence_run in runs:
        assert evidence_run.start == position
        assert evidence_run.end > evidence_run.start
        for offset in range(evidence_run.start, evidence_run.end):
            assert evidence_run.styles == styles_at(offset, spans)
        position = evidence_run.end
    assert position == length


@PROPERTY_SETTINGS
@given(spans_and_breaks())
def test_every_run_boundary_is_a_change_of_style_or_a_break_and_every_break_is_a_boundary(
    case: tuple[int, list[CardSpan], list[int]],
) -> None:
    length, spans, breaks = case
    runs = segment_runs(length, spans, breaks=breaks)
    boundaries = {evidence_run.start for evidence_run in runs[1:]}

    assert {b for b in breaks if 0 < b < length} <= boundaries
    for previous, following in zip(runs, runs[1:], strict=False):
        assert previous.styles != following.styles or following.start in breaks


# --------------------------------------------------------------------------------------------
# Where the cuts and interpolations sit
# --------------------------------------------------------------------------------------------

#: "Revival is " is 11 characters, "years away." 11 more; the second piece starts at 22 and is 28
#: characters, "Every delay costs elephants." The snapshot's [122, 142) was cut out between them.
CUT_EVIDENCE = "Revival is years away.Every delay costs elephants."


def cut_card(*, interpolations: tuple[Interpolation, ...] = (), spans: tuple[CardSpan, ...] = ()) -> Card:
    return build_card(
        evidence_text=CUT_EVIDENCE,
        evidence_start_offset=100,
        evidence_end_offset=170,
        omitted_ranges=(CardOmission(start_offset=122, end_offset=142),),
        spans=spans,
    ).evolve(interpolations=interpolations)


def test_an_omission_sits_where_its_kept_text_before_it_ends() -> None:
    assert len(CUT_EVIDENCE) == 50
    assert omission_offsets(cut_card()) == (22,)


def test_each_of_several_omissions_sits_after_all_the_kept_text_before_it() -> None:
    card = build_card(
        evidence_text="x" * 40,
        evidence_start_offset=10,
        evidence_end_offset=60,
        omitted_ranges=(
            CardOmission(start_offset=20, end_offset=25),
            CardOmission(start_offset=40, end_offset=45),
        ),
        spans=(),
    )

    # Kept: [10, 20) is 10 characters, [25, 40) 15 more, then [45, 60).
    assert omission_offsets(card) == (10, 25)


def test_a_card_with_no_omissions_has_no_cuts() -> None:
    assert omission_offsets(build_card()) == ()


def test_the_layout_interleaves_runs_the_cut_and_interpolations_in_reading_order() -> None:
    at_the_cut = Interpolation(anchor=22, text="the company says")
    at_the_end = Interpolation(anchor=50, text="emphasis added")
    card = cut_card(
        interpolations=(at_the_cut, at_the_end),
        spans=(span(11, 21, U), span(11, 16, H), span(22, 49, U), span(28, 33, H)),
    )

    assert lay_out_evidence(card) == (
        run(0, 11),
        run(11, 16, U, H),
        run(16, 21, U),
        run(21, 22),
        OmissionMark(22),
        InterpolationMark(22, at_the_cut),
        run(22, 28, U),
        run(28, 33, U, H),
        run(33, 49, U),
        run(49, 50),
        InterpolationMark(50, at_the_end),
    )


def test_a_cut_splits_an_underline_that_runs_across_it() -> None:
    card = cut_card(spans=(span(16, 28, U),))

    assert lay_out_evidence(card) == (
        run(0, 16),
        run(16, 22, U),
        OmissionMark(22),
        run(22, 28, U),
        run(28, 50),
    )


def test_an_interpolation_before_the_first_character_comes_first() -> None:
    first = Interpolation(anchor=0, text="Colossal's")
    card = cut_card(interpolations=(first,))

    assert lay_out_evidence(card)[:2] == (InterpolationMark(0, first), run(0, 22))


def test_a_card_with_no_evidence_lays_out_nothing() -> None:
    card = build_card(evidence_text="", evidence_start_offset=None, evidence_end_offset=None, spans=())

    assert lay_out_evidence(card) == ()


@st.composite
def cut_cards(draw: st.DrawFn) -> Card:
    """A card whose evidence has random cuts, interpolations and spans; its text is letters only."""
    length = draw(st.integers(min_value=1, max_value=40))
    cuts = (
        sorted(draw(st.sets(st.integers(min_value=1, max_value=length - 1), max_size=3)))
        if length > 1
        else []
    )
    anchors = sorted(draw(st.sets(st.integers(min_value=0, max_value=length), max_size=3)))
    spans: list[CardSpan] = []
    for style in (U, H):
        edges = sorted(draw(st.sets(st.integers(min_value=0, max_value=length), max_size=6)))
        spans.extend(span(a, b, style) for a, b in zip(edges[::2], edges[1::2], strict=False))
    omitted: list[CardOmission] = []
    snapshot_position, kept = 1000, 0
    for cut in cuts:
        snapshot_position += cut - kept
        width = draw(st.integers(min_value=1, max_value=4))
        omitted.append(CardOmission(start_offset=snapshot_position, end_offset=snapshot_position + width))
        snapshot_position += width
        kept = cut
    end = snapshot_position + (length - kept)
    if set(cuts) & set(anchors):
        event("an omission and an interpolation share a place")
    if omitted and spans:
        event("a card with cuts and spans")
    return build_card(
        evidence_text="".join(chr(ord("a") + i % 26) for i in range(length)),
        evidence_start_offset=1000,
        evidence_end_offset=end,
        omitted_ranges=tuple(omitted),
        spans=tuple(spans),
    ).evolve(interpolations=tuple(Interpolation(anchor=a, text=f"word {a}") for a in anchors))


def cut_places(card: Card) -> list[int]:
    """The oracle for where a cut sits: the length of the snapshot text kept before it."""
    places: list[int] = []
    kept = 0
    previous_end = card.evidence_start_offset
    assert previous_end is not None
    for omission in card.omitted_ranges:
        kept += omission.start_offset - previous_end
        places.append(kept)
        previous_end = omission.end_offset
    return places


@PROPERTY_SETTINGS
@given(cut_cards())
def test_the_layout_reads_the_evidence_in_order_with_every_cut_and_interpolation_in_its_place(
    card: Card,
) -> None:
    pieces: tuple[EvidencePiece, ...] = lay_out_evidence(card)
    position = 0
    cuts: list[int] = []
    interpolations: list[Interpolation] = []
    text = ""
    for piece in pieces:
        match piece:
            case EvidenceRun():
                assert piece.start == position
                text += card.evidence_text[piece.start : piece.end]
                position = piece.end
            case OmissionMark():
                assert piece.offset == position
                assert not interpolations or interpolations[-1].anchor < position, "a cut comes before"
                cuts.append(piece.offset)
            case InterpolationMark():
                assert piece.offset == position == piece.interpolation.anchor
                interpolations.append(piece.interpolation)

    assert text == card.evidence_text
    assert cuts == cut_places(card)
    assert tuple(interpolations) == card.interpolations


@PROPERTY_SETTINGS
@given(cut_cards())
def test_the_layouts_runs_are_the_spans_runs_split_at_each_cut_and_interpolation(card: Card) -> None:
    runs = tuple(piece for piece in lay_out_evidence(card) if isinstance(piece, EvidenceRun))
    breaks = [*cut_places(card), *(i.anchor for i in card.interpolations)]

    assert runs == segment_runs(len(card.evidence_text), card.spans, breaks=breaks)

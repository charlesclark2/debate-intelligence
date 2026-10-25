"""The paragraph-numbered rendering a model reads, and its offset map, both ways (v1-e05-t06).

Every expected rendering and offset below is worked out by hand from ``SOURCE`` and written down,
never captured from the renderer (`docs/process/working-agreements.md` §6). The text is invented
and deliberately not ASCII: a curly quote, an em dash, accented capitals and an emoji (one code
point, four UTF-8 bytes, two UTF-16 units), so an offset counted in any unit but code points lands
on the wrong character.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from debate_core.domain import SpanPurpose, SpanStyle
from debate_core.evidence.markup import EvidenceMarkupSpan
from debate_core.evidence.normalization import NORMALIZER_VERSION, Paragraph, normalize
from debate_core.evidence.numbered_snapshot import NumberedOffsetError, NumberedSnapshot, OffsetProblem
from debate_core.evidence.selection import EvidenceSelection, OffsetRange
from debate_core.evidence.selection_contract import (
    CardSelection,
    MarkupSpan,
    MarkupSuggestion,
    SelectedPassage,
)
from debate_core.evidence.snapshot_text import SnapshotText

#: Paragraph one is "Café “one”—two 🌍." (17 characters, 0-17), a break at 17-19, "Étude three."
#: (12 characters, 19-31), a break at 31-33, and "Four" (4 characters, 33-37). Counted by hand:
#: C a f é = 4, space 5, “ 6, o n e 9, ” 10, — 11, t w o 14, space 15, 🌍 16, . 17.
SOURCE = "Café “one”—two 🌍.\n\nÉtude three.\n\nFour"
PARAGRAPHS = (Paragraph("p0001", 0, 17), Paragraph("p0002", 19, 31), Paragraph("p0003", 33, 37))

RENDERED = "[P1] Café “one”—two 🌍.\n\n[P2] Étude three.\n\n[P3] Four"

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("NUMBERED_SNAPSHOT_PROPERTY_EXAMPLES", "200")),
    deadline=None,  # the first normalize() call builds cached Unicode tables
    suppress_health_check=[HealthCheck.too_slow],
)


@pytest.fixture
def numbered() -> NumberedSnapshot:
    source = SnapshotText.from_normalized(normalize(SOURCE, NORMALIZER_VERSION))
    assert source.paragraphs == PARAGRAPHS  # the hand count above, checked once
    return NumberedSnapshot(source)


# =============================================================================================
# Rendering
# =============================================================================================


def test_render_labels_every_paragraph_with_its_number(numbered: NumberedSnapshot) -> None:
    assert numbered.render() == RENDERED
    assert numbered.paragraph_count == 3


def test_render_of_some_paragraphs_keeps_their_numbers_and_snapshot_order(numbered: NumberedSnapshot) -> None:
    assert numbered.render([3, 1, 3]) == "[P1] Café “one”—two 🌍.\n\n[P3] Four"


def test_render_refuses_a_paragraph_the_snapshot_does_not_have(numbered: NumberedSnapshot) -> None:
    with pytest.raises(NumberedOffsetError) as raised:
        numbered.render([2, 4])

    assert raised.value.problem is OffsetProblem.PARAGRAPH_OUT_OF_BOUNDS


def test_render_of_an_empty_snapshot_is_empty() -> None:
    assert NumberedSnapshot(SnapshotText.from_normalized(normalize("", NORMALIZER_VERSION))).render() == ""


def test_what_follows_a_label_is_the_paragraph_text_character_for_character(
    numbered: NumberedSnapshot,
) -> None:
    blocks = numbered.render().split("\n\n")

    assert blocks == ["[P1] Café “one”—two 🌍.", "[P2] Étude three.", "[P3] Four"]
    assert [block.removeprefix(f"[P{number}] ") for number, block in enumerate(blocks, start=1)] == [
        "Café “one”—two 🌍.",
        "Étude three.",
        "Four",
    ]


# =============================================================================================
# The offset map: paragraph offsets to snapshot offsets and back
# =============================================================================================


@pytest.mark.parametrize(
    ("number", "offset", "snapshot_offset"),
    [
        (1, 0, 0),
        (1, 15, 15),  # the emoji
        (1, 16, 16),  # the full stop after it: one code point on, not two or four
        (1, 17, 17),  # the end of paragraph one, where an exclusive end points
        (2, 0, 19),
        (2, 12, 31),
        (3, 0, 33),
        (3, 4, 37),
    ],
)
def test_paragraph_offset_to_snapshot_offset_and_back(
    numbered: NumberedSnapshot, number: int, offset: int, snapshot_offset: int
) -> None:
    assert numbered.to_snapshot_offset(number, offset) == snapshot_offset
    assert numbered.to_paragraph_offset(snapshot_offset) == (number, offset)


def test_offsets_count_code_points_not_bytes(numbered: NumberedSnapshot) -> None:
    text = numbered.source.text

    assert text[numbered.to_snapshot_offset(1, 15) : numbered.to_snapshot_offset(1, 16)] == "🌍"
    assert text[numbered.to_snapshot_offset(2, 0) : numbered.to_snapshot_offset(2, 5)] == "Étude"
    assert len(text[:17].encode("utf-8")) == 27  # é, “, ”, — and 🌍 are 2, 3, 3, 3 and 4 bytes


@pytest.mark.parametrize(
    ("number", "offset", "problem"),
    [
        (1, 18, OffsetProblem.OFFSET_OUT_OF_BOUNDS),  # one past the end of paragraph one
        (2, 13, OffsetProblem.OFFSET_OUT_OF_BOUNDS),
        (1, -1, OffsetProblem.OFFSET_OUT_OF_BOUNDS),
        (0, 0, OffsetProblem.PARAGRAPH_OUT_OF_BOUNDS),
        (4, 0, OffsetProblem.PARAGRAPH_OUT_OF_BOUNDS),
        (True, 0, OffsetProblem.PARAGRAPH_OUT_OF_BOUNDS),
    ],
    ids=["one-past-the-end", "past-paragraph-two", "negative", "paragraph-zero", "paragraph-four", "bool"],
)
def test_an_offset_outside_its_paragraph_is_refused_never_carried_into_the_next(
    numbered: NumberedSnapshot, number: int, offset: int, problem: OffsetProblem
) -> None:
    with pytest.raises(NumberedOffsetError) as raised:
        numbered.to_snapshot_offset(number, offset)

    assert raised.value.problem is problem


@pytest.mark.parametrize(
    "snapshot_offset", [18, 32, 38, -1], ids=["break-1", "break-2", "past-end", "negative"]
)
def test_a_snapshot_offset_in_no_paragraph_is_refused(
    numbered: NumberedSnapshot, snapshot_offset: int
) -> None:
    with pytest.raises(NumberedOffsetError) as raised:
        numbered.to_paragraph_offset(snapshot_offset)

    assert raised.value.problem is OffsetProblem.OFFSET_OUT_OF_BOUNDS


def test_paragraph_numbers_name_the_paragraph_map_ids(numbered: NumberedSnapshot) -> None:
    assert [numbered.paragraph_id(number) for number in (1, 2, 3)] == ["p0001", "p0002", "p0003"]
    assert [numbered.paragraph_length(number) for number in (1, 2, 3)] == [17, 12, 4]


# =============================================================================================
# Passages and spans
# =============================================================================================


def passage(first: int, last: int, start: int = 0, end: int | None = None) -> SelectedPassage:
    return SelectedPassage(first_paragraph=first, last_paragraph=last, start_offset=start, end_offset=end)


@pytest.mark.parametrize(
    ("selected", "expected"),
    [
        (passage(1, 1), (0, 17)),
        (passage(1, 3), (0, 37)),
        (passage(1, 2, start=15, end=5), (15, 24)),  # "🌍.\n\nÉtude"
        (passage(2, 2, start=6, end=11), (25, 30)),  # "three"
    ],
    ids=["whole-paragraph", "whole-snapshot", "across-a-break", "inside-one"],
)
def test_passage_range_resolves_to_snapshot_offsets(
    numbered: NumberedSnapshot, selected: SelectedPassage, expected: tuple[int, int]
) -> None:
    assert numbered.passage_range(selected) == expected


def test_passage_range_of_a_cross_paragraph_passage_slices_the_text_it_names(
    numbered: NumberedSnapshot,
) -> None:
    start, end = numbered.passage_range(passage(1, 2, start=15, end=5))

    assert numbered.source.text[start:end] == "🌍.\n\nÉtude"


@pytest.mark.parametrize(
    ("selected", "problem"),
    [
        (passage(2, 1), OffsetProblem.REVERSED_RANGE),
        (passage(1, 1, start=17), OffsetProblem.OFFSET_OUT_OF_BOUNDS),  # starts at the end: a break follows
        (passage(1, 1, end=18), OffsetProblem.OFFSET_OUT_OF_BOUNDS),  # one past the end
        (passage(2, 2, start=4, end=4), OffsetProblem.EMPTY_RANGE),
        (passage(2, 2, start=6, end=5), OffsetProblem.REVERSED_RANGE),
        (passage(4, 4), OffsetProblem.PARAGRAPH_OUT_OF_BOUNDS),
        (passage(1, 4), OffsetProblem.PARAGRAPH_OUT_OF_BOUNDS),
    ],
    ids=[
        "reversed-paragraphs",
        "start-at-end",
        "end-one-past",
        "empty",
        "reversed-offsets",
        "no-paragraph",
        "no-last",
    ],
)
def test_passage_range_refuses_what_names_no_characters(
    numbered: NumberedSnapshot, selected: SelectedPassage, problem: OffsetProblem
) -> None:
    with pytest.raises(NumberedOffsetError) as raised:
        numbered.passage_range(selected)

    assert raised.value.problem is problem


def test_passage_range_accepts_an_end_exactly_at_the_paragraph_end(numbered: NumberedSnapshot) -> None:
    assert numbered.passage_range(passage(1, 1, end=17)) == (0, 17)


def test_selection_and_markup_convert_to_the_types_span_extraction_takes(numbered: NumberedSnapshot) -> None:
    selection = CardSelection.model_validate(
        {
            "passages": [
                {"first_paragraph": 1, "last_paragraph": 1, "start_offset": 5},
                {"first_paragraph": 3, "last_paragraph": 3},
            ],
            "tag": {
                "text": "A tag",
                "argument_role": "impact",
                "need_alignment": "partial",
                "confidence": 0.5,
            },
            "rationale": "A rationale",
            "confidence": 0.5,
        }
    )
    markup = MarkupSuggestion(
        spans=(
            MarkupSpan(paragraph=1, start_offset=15, end_offset=16, style=SpanStyle.UNDERLINE),
            MarkupSpan(
                paragraph=3,
                start_offset=0,
                end_offset=4,
                style=SpanStyle.HIGHLIGHT,
                purpose=SpanPurpose.CLAIM,
            ),
        ),
        rationale="A rationale",
    )

    assert numbered.evidence_selection(selection) == EvidenceSelection(
        (OffsetRange(5, 17), OffsetRange(33, 37))
    )
    assert numbered.markup_spans(markup) == (
        EvidenceMarkupSpan(15, 16, SpanStyle.UNDERLINE),
        EvidenceMarkupSpan(33, 37, SpanStyle.HIGHLIGHT, SpanPurpose.CLAIM),
    )


def test_span_range_refuses_an_end_one_past_its_paragraph(numbered: NumberedSnapshot) -> None:
    with pytest.raises(NumberedOffsetError) as raised:
        numbered.span_range(MarkupSpan(paragraph=3, start_offset=0, end_offset=5, style=SpanStyle.UNDERLINE))

    assert raised.value.problem is OffsetProblem.OFFSET_OUT_OF_BOUNDS


# =============================================================================================
# The offset map on generated text, both ways
# =============================================================================================

_CHARACTERS = st.sampled_from(["a", "Z", "é", "É", "ß", "“", "”", "’", "—", "–", "🌍", "😬", "9", "."])
_WORDS = st.text(_CHARACTERS, min_size=1, max_size=6)
_PARAGRAPHS = st.lists(_WORDS, min_size=1, max_size=5).map(" ".join)


@st.composite
def numbered_snapshots(draw: st.DrawFn) -> NumberedSnapshot:
    paragraphs = draw(st.lists(_PARAGRAPHS, min_size=1, max_size=5))
    text = "\n\n".join(paragraphs)
    event(f"paragraphs: {len(paragraphs)}")
    event(
        "has an astral character"
        if any(ord(character) > 0xFFFF for character in text)
        else "no astral character"
    )
    return NumberedSnapshot(SnapshotText.from_normalized(normalize(text, NORMALIZER_VERSION)))


@PROPERTY_SETTINGS
@given(numbered_snapshots())
def test_every_paragraph_offset_maps_to_the_snapshot_and_back(numbered: NumberedSnapshot) -> None:
    text = numbered.source.text
    for number in range(1, numbered.paragraph_count + 1):
        paragraph_text = numbered.source.paragraph_text(numbered.paragraph_id(number))
        assert f"[P{number}] {paragraph_text}" in numbered.render().split("\n\n")
        for offset in range(len(paragraph_text) + 1):
            snapshot_offset = numbered.to_snapshot_offset(number, offset)
            assert numbered.to_paragraph_offset(snapshot_offset) == (number, offset)
            assert text[snapshot_offset:].startswith(paragraph_text[offset:])
        with pytest.raises(NumberedOffsetError):
            numbered.to_snapshot_offset(number, len(paragraph_text) + 1)


@PROPERTY_SETTINGS
@given(numbered_snapshots())
def test_every_snapshot_offset_maps_to_its_paragraph_and_back_or_is_in_a_break(
    numbered: NumberedSnapshot,
) -> None:
    text = numbered.source.text
    for snapshot_offset in range(len(text) + 1):
        in_a_break = (
            text[snapshot_offset - 1 : snapshot_offset + 1] == "\n\n" if snapshot_offset > 0 else False
        )
        if in_a_break:
            with pytest.raises(NumberedOffsetError):
                numbered.to_paragraph_offset(snapshot_offset)
        else:
            number, offset = numbered.to_paragraph_offset(snapshot_offset)
            assert numbered.to_snapshot_offset(number, offset) == snapshot_offset

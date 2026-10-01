"""Properties of extraction and markup over random snapshots and random selections.

Each property compares the code with an oracle written here from the rules, not from the code: the
set of characters a selection names, and whether a selection or a set of spans is valid at all. Each
docstring names the check the property guards; the session report records whether removing that
check makes the property fail.

Example count comes from `EXTRACTION_PROPERTY_EXAMPLES` (default 200), so a deep run is
`EXTRACTION_PROPERTY_EXAMPLES=50000 uv run pytest <this file>`.
``SnapshotText`` values come from a normalizer result, never from hand-decoded bytes.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterable

import pytest
from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from debate_core.domain import SourceSnapshot, SpanStyle
from debate_core.evidence.extractor import (
    EvidenceExtractor,
    ExtractedEvidence,
    SnapshotTextCheck,
    SnapshotTextMismatch,
)
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan, InvalidMarkup
from debate_core.evidence.normalization import NORMALIZER_VERSION, Paragraph, normalize
from debate_core.evidence.selection import (
    EvidenceSelection,
    InvalidSelection,
    OffsetRange,
    ParagraphId,
    ParagraphRun,
    SelectionPart,
)
from debate_core.evidence.snapshot_text import SnapshotText
from debate_core.testing.builders import build_source_snapshot

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("EXTRACTION_PROPERTY_EXAMPLES", "200")),
    deadline=None,  # the first normalize() call builds cached Unicode tables
    suppress_health_check=[HealthCheck.too_slow],
)

extractor = EvidenceExtractor()

# ---------------------------------------------------------------------------------------------
# Random snapshots
# ---------------------------------------------------------------------------------------------

_WORD = st.text(
    alphabet=st.one_of(
        st.characters(categories=("L", "N", "P", "S")),
        st.sampled_from(list("aééßﬁ—\"'")),
    ),
    min_size=1,
    max_size=8,
)
_WORD_GAP = st.sampled_from([" ", "  ", "\t", " ", "­ "])
_PARAGRAPH_GAP = st.sampled_from(["\n\n", "\r\n\r\n", "\n \n", " "])


@st.composite
def snapshots(draw: st.DrawFn) -> tuple[SourceSnapshot, SnapshotText]:
    """A record and its normalized text, from raw text of one to six paragraphs of one to eight words."""
    paragraphs = draw(st.lists(st.lists(_WORD, min_size=1, max_size=8), min_size=1, max_size=6))
    raw = ""
    for index, words in enumerate(paragraphs):
        if index:
            raw += draw(_PARAGRAPH_GAP)
        for position, word in enumerate(words):
            raw += (draw(_WORD_GAP) if position else "") + word
    text = SnapshotText.from_normalized(normalize(raw, NORMALIZER_VERSION))
    assume(text.text)  # a word can be all removed characters; there must be something to select
    return build_source_snapshot(normalized_text=text.text, normalizer_version=NORMALIZER_VERSION), text


def _distinct_points(draw: st.DrawFn, low: int, high: int, max_pairs: int) -> list[int]:
    available_pairs = (high - low + 1) // 2
    count = draw(st.integers(min_value=1, max_value=min(max_pairs, available_pairs))) * 2
    points = draw(st.lists(st.integers(low, high), min_size=count, max_size=count, unique=True))
    return sorted(points)


@st.composite
def valid_selections(draw: st.DrawFn, text: SnapshotText) -> list[SelectionPart]:
    """Parts that select disjoint characters: paragraph runs and offset ranges inside paragraphs, or
    free offset ranges anywhere. Some ranges are split into two parts that touch."""
    parts: list[SelectionPart] = []
    if draw(st.booleans(), label="by-paragraph-plan"):
        index = 0
        while index < len(text.paragraphs):
            paragraph = text.paragraphs[index]
            choice = draw(st.sampled_from(["skip", "run", "offsets"]))
            if choice == "run":
                last = draw(st.integers(index, len(text.paragraphs) - 1))
                first_id = ParagraphId(paragraph.paragraph_id)
                parts.append(ParagraphRun(first_id, ParagraphId(text.paragraphs[last].paragraph_id)))
                index = last + 1
                continue
            if choice == "offsets" and paragraph.end - paragraph.start >= 1:
                points = _distinct_points(draw, paragraph.start, paragraph.end, 3)
                parts.extend(OffsetRange(points[i], points[i + 1]) for i in range(0, len(points), 2))
            index += 1
    else:
        points = _distinct_points(draw, 0, len(text.text), 4)
        parts.extend(OffsetRange(points[i], points[i + 1]) for i in range(0, len(points), 2))
    split: list[SelectionPart] = []
    for part in parts:
        if isinstance(part, OffsetRange) and part.end - part.start >= 2 and draw(st.booleans()):
            middle = draw(st.integers(part.start + 1, part.end - 1))
            split.extend((OffsetRange(part.start, middle), OffsetRange(middle, part.end)))
        else:
            split.append(part)
    assume(split)
    return draw(st.permutations(split))


@st.composite
def arbitrary_parts(draw: st.DrawFn, text: SnapshotText) -> list[SelectionPart]:
    """Parts that may overlap, run off the end, name unknown paragraphs or run backwards."""
    length = len(text.text)
    ids = [paragraph.paragraph_id for paragraph in text.paragraphs] + ["p0000", "p9999"]
    # Paragraph edges, where a part can touch a paragraph run exactly.
    edges = sorted({edge for paragraph in text.paragraphs for edge in (paragraph.start, paragraph.end)})

    def offsets() -> OffsetRange:
        start = draw(st.integers(0, length + 3) | st.sampled_from(edges[:-1] or [0]))
        later_edges = [edge for edge in edges if edge > start]
        end_strategy = st.integers(start + 1, length + 6)
        return OffsetRange(
            start, draw(end_strategy | st.sampled_from(later_edges) if later_edges else end_strategy)
        )

    def run() -> ParagraphRun:
        return ParagraphRun(ParagraphId(draw(st.sampled_from(ids))), ParagraphId(draw(st.sampled_from(ids))))

    count = draw(st.integers(1, 4))
    return [offsets() if draw(st.booleans()) else run() for _ in range(count)]


@st.composite
def markup_for(draw: st.DrawFn, evidence: ExtractedEvidence, length: int) -> list[EvidenceMarkupSpan]:
    """Well-formed markup for ``evidence`` (disjoint underlines in segments, highlights inside them),
    then up to two perturbations: a span stretched or shifted, or an arbitrary span added. The
    oracle, not the generator, decides whether the result is valid."""
    spans: list[EvidenceMarkupSpan] = []
    for segment in evidence.segments:
        if draw(st.integers(0, 3)) == 0:  # leave a quarter of the segments unmarked
            continue
        points = _distinct_points(draw, segment.start, segment.end, 2)
        for i in range(0, len(points), 2):
            if points[i + 1] - points[i] >= 2 and draw(st.booleans()):
                # Two underlines that touch, which a highlight may run across.
                middle = draw(st.integers(points[i] + 1, points[i + 1] - 1))
                spans.append(EvidenceMarkupSpan.underline(points[i], middle))
                spans.append(EvidenceMarkupSpan.underline(middle, points[i + 1]))
            else:
                spans.append(EvidenceMarkupSpan.underline(points[i], points[i + 1]))
            if points[i + 1] - points[i] >= 1 and draw(st.booleans()):
                inner = sorted(
                    draw(st.lists(st.integers(points[i], points[i + 1]), min_size=2, max_size=2, unique=True))
                )
                spans.append(EvidenceMarkupSpan.highlight(inner[0], inner[1]))
    for _ in range(draw(st.integers(0, 2), label="perturbations")):
        kind = draw(st.sampled_from(["stretch", "shift", "add"]))
        if kind == "add" or not spans:
            start = draw(st.integers(0, length))
            spans.append(
                EvidenceMarkupSpan(
                    start, draw(st.integers(start + 1, length + 2)), draw(st.sampled_from(list(SpanStyle)))
                )
            )
        else:
            index = draw(st.integers(0, len(spans) - 1))
            span = spans[index]
            delta = draw(st.integers(1, 3))
            start, end = (
                (span.start, span.end + delta)
                if kind == "stretch"
                else (span.start + delta, span.end + delta)
            )
            spans[index] = EvidenceMarkupSpan(start, end, span.style)
    return draw(st.permutations(spans))


# ---------------------------------------------------------------------------------------------
# Oracles, written from the rules
# ---------------------------------------------------------------------------------------------


def oracle_ranges(text: SnapshotText, parts: Iterable[SelectionPart]) -> list[tuple[int, int]] | None:
    """Each part as a character range, or ``None`` if any part does not name characters of the text."""
    position = {paragraph.paragraph_id: index for index, paragraph in enumerate(text.paragraphs)}
    ranges: list[tuple[int, int]] = []
    for part in parts:
        if isinstance(part, OffsetRange):
            start, end = part.start, part.end
        else:
            if part.first not in position or part.last not in position:
                return None
            first, last = position[part.first], position[part.last]
            if last < first:
                return None
            start, end = text.paragraphs[first].start, text.paragraphs[last].end
        if end > len(text.text) or start >= end:
            return None
        ranges.append((start, end))
    return ranges


def oracle_selected(text: SnapshotText, parts: Iterable[SelectionPart]) -> set[int] | None:
    """The characters a selection names, or ``None`` if it is invalid (bad part, or two parts share one)."""
    ranges = oracle_ranges(text, parts)
    if ranges is None:
        return None
    selected: set[int] = set()
    for start, end in ranges:
        characters = set(range(start, end))
        if characters & selected:
            return None
        selected |= characters
    return selected


def covered(evidence: ExtractedEvidence) -> set[int]:
    return {index for segment in evidence.segments for index in range(segment.start, segment.end)}


def oracle_markup_is_valid(evidence: ExtractedEvidence, spans: list[EvidenceMarkupSpan]) -> bool:
    in_evidence = covered(evidence)
    segment_of = {
        index: number
        for number, segment in enumerate(evidence.segments)
        for index in range(segment.start, segment.end)
    }
    for span in spans:
        characters = range(span.start, span.end)
        if not all(index in in_evidence for index in characters):
            return False
        if len({segment_of[index] for index in characters}) != 1:
            return False  # pragma: no cover - a gap between segments is never in the evidence
    for style in SpanStyle:
        marked: set[int] = set()
        for span in spans:
            if span.style is style:
                characters = set(range(span.start, span.end))
                if characters & marked:
                    return False
                marked |= characters
    underlined = {
        index for span in spans if span.style is SpanStyle.UNDERLINE for index in range(span.start, span.end)
    }
    highlighted = {
        index for span in spans if span.style is SpanStyle.HIGHLIGHT for index in range(span.start, span.end)
    }
    return highlighted <= underlined


# ---------------------------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(snapshots(), st.data())
def test_extract_a_valid_selection_yields_exactly_the_selected_characters_in_source_order(
    snapshot_and_text: tuple[SourceSnapshot, SnapshotText], data: st.DataObject
) -> None:
    """ac1 and ac2 on random snapshots: every segment is the snapshot text at its offsets, the
    segments hold exactly the selected characters (nothing widened, nothing dropped), in source
    order, separated by non-empty cuts that are exactly the unselected text between them, and the
    order the parts were given in makes no difference.

    Guards the merge of touching ranges and the source ordering of parts."""
    snapshot, text = snapshot_and_text
    parts = data.draw(valid_selections(text), label="parts")
    expected = oracle_selected(text, parts)
    assert expected is not None, "the generator made an invalid selection"

    evidence = extractor.extract(snapshot, text, EvidenceSelection(tuple(parts)))
    event(f"segments: {min(len(evidence.segments), 3)}{'+' if len(evidence.segments) > 3 else ''}")
    event(f"paragraph runs: {any(isinstance(part, ParagraphRun) for part in parts)}")
    event(f"touching parts merged: {len(evidence.segments) < len(parts)}")

    assert covered(evidence) == expected
    assert "".join(segment.text for segment in evidence.segments) == "".join(
        text.text[index] for index in sorted(expected)
    )
    for segment in evidence.segments:
        assert segment.text == text.text[segment.start : segment.end]
    for previous, omitted, following in zip(
        evidence.segments[:-1], evidence.omitted_ranges, evidence.segments[1:], strict=True
    ):
        assert previous.end == omitted.start < omitted.end == following.start
    assert evidence == extractor.extract(snapshot, text, EvidenceSelection(tuple(reversed(parts))))


@PROPERTY_SETTINGS
@given(snapshots(), st.data())
def test_extract_an_arbitrary_selection_is_either_exact_or_refused_never_repaired(
    snapshot_and_text: tuple[SourceSnapshot, SnapshotText], data: st.DataObject
) -> None:
    """Overlapping, out-of-range, reversed or unknown parts raise InvalidSelection; a selection the
    oracle accepts yields exactly its characters. Nothing is clamped, trimmed or dropped.

    Guards the overlap refusal, the bounds check, the reversed-run check and paragraph lookup."""
    snapshot, text = snapshot_and_text
    parts = data.draw(arbitrary_parts(text), label="parts")
    expected = oracle_selected(text, parts)

    event(f"oracle says: {'valid' if expected is not None else 'invalid'}")
    if expected is None:
        with pytest.raises(InvalidSelection):
            extractor.extract(snapshot, text, EvidenceSelection(tuple(parts)))
    else:
        assert covered(extractor.extract(snapshot, text, EvidenceSelection(tuple(parts)))) == expected


@PROPERTY_SETTINGS
@given(snapshots(), st.data())
def test_markup_is_accepted_exactly_when_it_lies_in_one_segment_without_same_style_overlap_and_underlined(
    snapshot_and_text: tuple[SourceSnapshot, SnapshotText], data: st.DataObject
) -> None:
    """ac3 on random evidence and random spans, checked against the oracle in both directions.

    Guards containment, the cut check, same-style overlap and highlight-within-underline."""
    snapshot, text = snapshot_and_text
    evidence = extractor.extract(
        snapshot, text, EvidenceSelection(tuple(data.draw(valid_selections(text), label="parts")))
    )
    spans = data.draw(markup_for(evidence, len(text.text)), label="spans")

    valid = oracle_markup_is_valid(evidence, spans)
    event(f"oracle says: {'valid' if valid else 'invalid'}, {'no spans' if not spans else 'with spans'}")
    if valid:
        assert CardMarkup(evidence, tuple(spans)).spans == tuple(spans)
    else:
        with pytest.raises(InvalidMarkup):
            CardMarkup(evidence, tuple(spans))


@PROPERTY_SETTINGS
@given(snapshots(), st.data())
def test_extract_refuses_any_moved_paragraph_boundary_before_resolving_a_paragraph(
    snapshot_and_text: tuple[SourceSnapshot, SnapshotText], data: st.DataObject
) -> None:
    """The `v1-e03-t02` finding, at the point of use: one boundary moved to another offset that keeps
    the map in order and inside the text, the text and its hash untouched. Selecting any paragraph
    is refused.

    Guards the paragraph-map check."""
    snapshot, text = snapshot_and_text
    paragraphs = list(text.paragraphs)
    index = data.draw(st.integers(0, len(paragraphs) - 1), label="paragraph")
    paragraph = paragraphs[index]
    low = paragraphs[index - 1].end if index else 0
    high = paragraphs[index + 1].start if index + 1 < len(paragraphs) else len(text.text)
    if data.draw(st.booleans(), label="move-start"):
        moved = data.draw(st.integers(low, paragraph.end).filter(lambda value: value != paragraph.start))
        paragraphs[index] = Paragraph(paragraph.paragraph_id, moved, paragraph.end)
    else:
        moved = data.draw(st.integers(paragraph.start, high).filter(lambda value: value != paragraph.end))
        paragraphs[index] = Paragraph(paragraph.paragraph_id, paragraph.start, moved)
    tampered = dataclasses.replace(text, paragraphs=tuple(paragraphs))
    selected = ParagraphId(data.draw(st.sampled_from(paragraphs)).paragraph_id)

    with pytest.raises(SnapshotTextMismatch) as refused:
        extractor.extract(snapshot, tampered, EvidenceSelection.of_paragraphs(selected))

    assert refused.value.check is SnapshotTextCheck.PARAGRAPH_MAP


@PROPERTY_SETTINGS
@given(snapshots(), st.data())
def test_extract_refuses_any_single_character_change_to_the_text(
    snapshot_and_text: tuple[SourceSnapshot, SnapshotText], data: st.DataObject
) -> None:
    """Text that differs from the record's in one character is refused, whatever is selected and
    wherever the change is, even outside the selection.

    Guards the text-hash check."""
    snapshot, text = snapshot_and_text
    position = data.draw(st.integers(0, len(text.text) - 1), label="position")
    replacement = data.draw(
        st.characters(exclude_categories=("Cs",)).filter(lambda character: character != text.text[position])
    )
    altered = dataclasses.replace(text, text=text.text[:position] + replacement + text.text[position + 1 :])

    with pytest.raises(SnapshotTextMismatch) as refused:
        extractor.extract(snapshot, altered, EvidenceSelection.of_offsets((0, 1)))

    assert refused.value.check is SnapshotTextCheck.TEXT_HASH

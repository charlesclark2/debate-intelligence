"""The labelled cite shapes, scored the way the evaluation scores a real file (`v1-e31-t12`).

`cite_shapes.py` holds the examples and says how each was read before the task. Here the harness's
own `score_file` measures the parser on them, one invented file a shape, so the figures in the
session report are the ones this file holds the parser to: tag and cite precision of 1.000 on
every shape, and a cite recall that falls short only by the one example left misread on purpose.

Every PR runs these. The files are built in memory from invented text.
"""

from __future__ import annotations

from datetime import date

import pytest
from tests.evals.parser.cite_shapes import (
    EXAMPLES,
    CiteShape,
    ReadingBefore,
    build_example_file,
    build_shape_file,
    examples_of,
)
from tests.evals.parser.metrics import FileScore, prediction_from_document, score_file

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.docx_parser import DebateDocxParser

SNAPSHOT = date(2026, 10, 12)

#: The spec asks for at least ten labelled examples of each shape (Goal criterion ac1).
MINIMUM_EXAMPLES_OF_A_SHAPE = 10

#: Cite lines the parser is known to miss, by shape: a second line of a cite set in small print
#: with no bold opening, which only its words tell from the body's first line.
CITE_LINES_LEFT_MISREAD = {CiteShape.A_SMALL_PRINT_LINE_UNDER_A_CITE: 1}


def parse(content: bytes) -> ParsedDocument:
    source = SourceDocument(
        sha256="0" * 64,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hsld26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    document = DebateDocxParser().parse(content, source, source_path="cite-shapes/invented.docx")
    assert isinstance(document, ParsedDocument), document
    return document


def score(shape: CiteShape) -> FileScore:
    built = build_shape_file(shape)
    return score_file(built.labels, prediction_from_document(parse(built.content)))


@pytest.mark.parametrize("shape", list(CiteShape), ids=lambda shape: shape.value)
def test_each_shape_has_at_least_ten_labelled_examples(shape: CiteShape) -> None:
    assert len(examples_of(shape)) >= MINIMUM_EXAMPLES_OF_A_SHAPE


def test_no_two_examples_share_a_name() -> None:
    names = [example.name for example in EXAMPLES]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.name)
def test_an_examples_labels_describe_whole_cards(example) -> None:  # type: ignore[no-untyped-def]
    """Each labelled card is one run of paragraphs and holds a cite or a tag: a card, not a stray body."""
    built = build_example_file(example)
    for first, last, _ in built.cards:
        inside = built.lines[first : last + 1]
        assert all(line.card is not None or line.unit is StructuralUnit.OTHER for line in inside)
        assert inside[0].unit in (StructuralUnit.TAG, StructuralUnit.CITE)
        assert inside[-1].unit in (StructuralUnit.EVIDENCE, StructuralUnit.CITE)


@pytest.mark.parametrize("shape", list(CiteShape), ids=lambda shape: shape.value)
def test_tag_and_cite_precision_are_whole_on_every_shape(shape: CiteShape) -> None:
    """Nothing the parser calls a tag or a cite on these files is anything else."""
    units = score(shape).units
    assert units[StructuralUnit.TAG].false_positive == 0
    assert units[StructuralUnit.CITE].false_positive == 0
    assert units[StructuralUnit.TAG].precision == 1.0
    assert units[StructuralUnit.CITE].precision == 1.0


@pytest.mark.parametrize("shape", list(CiteShape), ids=lambda shape: shape.value)
def test_every_tag_is_found_and_every_cite_but_the_one_left_on_purpose(shape: CiteShape) -> None:
    units = score(shape).units
    assert units[StructuralUnit.TAG].false_negative == 0
    assert units[StructuralUnit.CITE].false_negative == CITE_LINES_LEFT_MISREAD.get(shape, 0)


@pytest.mark.parametrize("shape", list(CiteShape), ids=lambda shape: shape.value)
def test_every_card_has_its_boundaries_and_its_completeness(shape: CiteShape) -> None:
    result = score(shape)
    labelled = sum(len(example.completeness) for example in examples_of(shape))
    assert result.labeled_cards == labelled
    assert result.predicted_cards == labelled
    assert result.boundary_matches == labelled
    assert result.completeness_correct == labelled


def test_only_the_small_print_shape_has_an_example_left_misread() -> None:
    """What is left is named, with its reason, and is one line of one shape."""
    left = [example for example in EXAMPLES if example.before is ReadingBefore.STILL_MISREAD]
    assert [example.shape for example in left] == [CiteShape.A_SMALL_PRINT_LINE_UNDER_A_CITE]
    assert all(example.why for example in left)

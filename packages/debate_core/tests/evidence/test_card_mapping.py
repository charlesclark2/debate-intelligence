"""place_evidence_on_card: a selection and its markup become a card's envelope, omissions, text and spans.

Every expected offset, string and span below is worked out by hand from ``NORMALIZED`` and written
down, never captured from the code (`docs/process/working-agreements.md` §6). The source is invented.
The last section is `v1-e03-t07` ac3's scan: no other code in the tree does this offset arithmetic.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.verification.verification_world import VerificationWorld

from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.domain import (
    Card,
    CardOmission,
    Interpolation,
    ProvenanceMode,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
)
from debate_core.evidence.card_mapping import place_evidence_on_card
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan
from debate_core.evidence.selection import EvidenceSelection
from debate_core.testing.builders import DEFAULT_OWNER_ID, build_citation

EXTRACTED = (
    "Groundwater in the Tessaly basin fell 4 metres in a decade.\n\n"
    "Farmers there now pump twice what the aquifer recharges.\n\n"
    "Without new limits, the wells will run dry by 2040.\n"
)

#: What EXTRACTED normalizes to. Paragraphs at 0-59, 61-117 and 119-170, by hand.
NORMALIZED = (
    "Groundwater in the Tessaly basin fell 4 metres in a decade.\n\n"
    "Farmers there now pump twice what the aquifer recharges.\n\n"
    "Without new limits, the wells will run dry by 2040."
)

# The card most tests cut, in snapshot offsets:
#   kept     61-68   "Farmers"
#   omitted  68-78   " there now"                                (10 characters)
#   kept     78-89   " pump twice"
#   omitted  89-119  " what the aquifer recharges.\n\n"           (30 characters)
#   kept    119-138  "Without new limits,"
# Envelope 61-138 is 77 characters; less 40 omitted leaves 37, the length of CUT_TEXT. In CUT_TEXT,
# "Farmers" is 0-7, " pump twice" 7-18 and "Without new limits," 18-37.
KEPT = ((61, 68), (78, 89), (119, 138))
CUT_TEXT = "Farmers pump twiceWithout new limits,"


@pytest.fixture
def world() -> VerificationWorld:
    return VerificationWorld()


@pytest.fixture
def source(world: VerificationWorld) -> LoadedSnapshot:
    return world.add_source(EXTRACTED)


def blank_card(source: LoadedSnapshot) -> Card:
    """A tag-only card for the source's article: what exists before anything is cut."""
    return Card(
        owner_id=DEFAULT_OWNER_ID,
        article_id=source.snapshot.article_id,
        tag="Aquifer depletion is on a fixed clock",
        citation=build_citation(),
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
    )


def markup_for(
    source: LoadedSnapshot, ranges: tuple[tuple[int, int], ...], *spans: EvidenceMarkupSpan
) -> CardMarkup:
    evidence = EvidenceExtractor().extract(
        source.snapshot, source.normalized, EvidenceSelection.of_offsets(*ranges)
    )
    return CardMarkup(evidence, spans)


#: Snapshot markup on the cut: each kept piece underlined to its edges, so underlines touch across
#: both cuts, with "twice" (84-89) and "limits" (131-137) highlighted.
MARKUP = (
    EvidenceMarkupSpan.underline(61, 68, SpanPurpose.CLAIM),
    EvidenceMarkupSpan.underline(78, 89, SpanPurpose.WARRANT),
    EvidenceMarkupSpan.highlight(84, 89, SpanPurpose.IMPACT),
    EvidenceMarkupSpan.underline(119, 138, SpanPurpose.CLAIM),
    EvidenceMarkupSpan.highlight(131, 137),
)


def test_the_fixture_normalizes_to_the_hand_written_text(source: LoadedSnapshot) -> None:
    assert source.normalized.text == NORMALIZED


# =============================================================================================
# The mapping, on hand-worked examples
# =============================================================================================


def test_card_mapping_puts_the_envelope_omissions_text_and_spans_on_the_card(source: LoadedSnapshot) -> None:
    card = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))

    assert (card.evidence_start_offset, card.evidence_end_offset) == (61, 138)
    assert card.omitted_ranges == (
        CardOmission(start_offset=68, end_offset=78),
        CardOmission(start_offset=89, end_offset=119),
    )
    assert card.evidence_text == CUT_TEXT
    assert card.quoted_ranges == KEPT
    assert [(span.start_offset, span.end_offset, span.style, span.purpose) for span in card.spans] == [
        (0, 7, SpanStyle.UNDERLINE, SpanPurpose.CLAIM),
        (7, 18, SpanStyle.UNDERLINE, SpanPurpose.WARRANT),
        (13, 18, SpanStyle.HIGHLIGHT, SpanPurpose.IMPACT),
        (18, 37, SpanStyle.UNDERLINE, SpanPurpose.CLAIM),
        (30, 36, SpanStyle.HIGHLIGHT, None),
    ]


def test_card_mapping_spans_mark_the_same_words_in_the_text_as_in_the_snapshot(
    source: LoadedSnapshot,
) -> None:
    card = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))

    marked = [card.evidence_text[span.start_offset : span.end_offset] for span in card.spans]
    assert marked == ["Farmers", " pump twice", "twice", "Without new limits,", "limits"]


def test_card_mapping_keeps_touching_spans_either_side_of_a_cut_as_separate_spans(
    source: LoadedSnapshot,
) -> None:
    """ "Farmers" ends at the first cut and " pump twice" starts after it: in the text they touch at 7,
    and they stay two underlines, each with its own purpose (see the card_mapping module docstring)."""
    card = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))

    underlines = card.spans_of_style(SpanStyle.UNDERLINE)
    assert [(span.start_offset, span.end_offset) for span in underlines] == [(0, 7), (7, 18), (18, 37)]


def test_card_mapping_stores_no_joiner_where_text_was_omitted(source: LoadedSnapshot) -> None:
    """The cuts leave "Farmers" against " pump" and "twice" against "Without": no ellipsis, bracket or
    space is added, because none is in the snapshot."""
    card = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))

    assert "twiceWithout" in card.evidence_text
    assert "..." not in card.evidence_text and "…" not in card.evidence_text
    assert len(card.evidence_text) == (138 - 61) - (10 + 30)


def test_card_mapping_of_one_contiguous_range_has_no_omissions(source: LoadedSnapshot) -> None:
    """Paragraph two, "pump twice" (79-89) underlined: in the text it is 79 - 61 = 18 to 28."""
    card = place_evidence_on_card(
        blank_card(source), markup_for(source, ((61, 117),), EvidenceMarkupSpan.underline(79, 89))
    )

    assert (card.evidence_start_offset, card.evidence_end_offset) == (61, 117)
    assert card.omitted_ranges == ()
    assert card.evidence_text == "Farmers there now pump twice what the aquifer recharges."
    assert [(span.start_offset, span.end_offset) for span in card.spans] == [(18, 28)]


def test_card_mapping_counts_an_omission_only_once_a_span_is_past_it(source: LoadedSnapshot) -> None:
    """A span starting where a cut ends (119) is past that cut; one ending where a cut starts (89) is
    not. Both edges, by hand: 119 - 61 - 40 = 18, and 89 - 61 - 10 = 18."""
    card = place_evidence_on_card(
        blank_card(source),
        markup_for(
            source, KEPT, EvidenceMarkupSpan.underline(85, 89), EvidenceMarkupSpan.underline(119, 126)
        ),
    )

    assert [(span.start_offset, span.end_offset) for span in card.spans] == [(14, 18), (18, 25)]
    assert [card.evidence_text[span.start_offset : span.end_offset] for span in card.spans] == [
        "wice",
        "Without",
    ]


def test_card_mapping_records_where_the_offsets_point(source: LoadedSnapshot) -> None:
    card = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))

    assert card.snapshot_id == source.snapshot.snapshot_id
    assert card.normalized_text_hash == source.snapshot.normalized_text_hash
    assert card.normalizer_version == source.snapshot.normalizer_version


def test_card_mapping_keeps_the_card_and_replaces_its_evidence(source: LoadedSnapshot) -> None:
    """Cutting again replaces the previous evidence entirely, and new evidence is never VERIFIED."""
    first = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))
    claimed = first.model_copy(update={"verification_status": VerificationStatus.VERIFIED})

    recut = place_evidence_on_card(
        claimed, markup_for(source, ((0, 11),), EvidenceMarkupSpan.underline(0, 11, SpanPurpose.CLAIM))
    )

    assert recut.card_id == first.card_id
    assert (recut.tag, recut.citation, recut.owner_id) == (first.tag, first.citation, first.owner_id)
    assert recut.verification_status is VerificationStatus.UNVERIFIED
    assert recut.evidence_text == "Groundwater"
    assert recut.omitted_ranges == ()
    assert [(span.start_offset, span.end_offset) for span in recut.spans] == [(0, 11)]


def test_card_mapping_drops_interpolations_whose_anchors_index_the_evidence_it_replaces(
    source: LoadedSnapshot,
) -> None:
    """Anchor 7 is still inside the new 11-character text, so only the mapping dropping it removes it."""
    first = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))
    annotated = first.evolve(interpolations=(Interpolation(anchor=7, text="in the basin"),))

    recut = place_evidence_on_card(
        annotated, markup_for(source, ((0, 11),), EvidenceMarkupSpan.underline(0, 11, SpanPurpose.CLAIM))
    )

    assert recut.interpolations == ()


def test_card_mapping_takes_provenance_from_the_snapshot_not_the_card(world: VerificationWorld) -> None:
    """ProvenanceMode "travels from the snapshot onto every card cut from it". A tag-only card made
    with the strongest claim, PUBLISHER_RETRIEVED, given text a user supplied, must say USER_SUPPLIED."""
    supplied = world.add_source(EXTRACTED, provenance_mode=ProvenanceMode.USER_SUPPLIED)
    claiming = blank_card(supplied)
    assert claiming.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED

    card = place_evidence_on_card(claiming, markup_for(supplied, KEPT, *MARKUP))

    assert card.provenance_mode is ProvenanceMode.USER_SUPPLIED


def test_card_mapping_refuses_a_card_for_another_article(source: LoadedSnapshot) -> None:
    other = blank_card(source).evolve(article_id="0ART0000000000000000000002")

    with pytest.raises(ValueError, match="cites article 0ART0000000000000000000002"):
        place_evidence_on_card(other, markup_for(source, KEPT, *MARKUP))


def test_card_mapping_output_verifies(world: VerificationWorld, source: LoadedSnapshot) -> None:
    card = place_evidence_on_card(blank_card(source), markup_for(source, KEPT, *MARKUP))

    assert world.verify(card).status is VerificationStatus.VERIFIED


# =============================================================================================
# ac3: the arithmetic exists once
# =============================================================================================
# The calculation that turns a snapshot offset into an evidence_text offset subtracts where the
# evidence starts: `s - evidence.start - ...`, or `span.start - evidence.start` in the single-range
# mapping t04's fixture used to carry. Its inverse adds where the card starts to a span offset. The
# scan flags both shapes everywhere Python lives in the tree: production code, tests, test fixtures
# and scripts. Subtracting an object's own start from its own end is a length and is left alone.

REPOSITORY = Path(__file__).resolve().parents[4]
SCANNED = ("packages/*/src/**/*.py", "packages/*/tests/**/*.py", "tests/**/*.py", "scripts/**/*.py")
MAPPING_MODULE = "packages/debate_core/src/debate_core/evidence/card_mapping.py"
FIXTURE_MODULE = "tests/fixtures/verification/verification_world.py"

_START = frozenset({"start", "start_offset", "evidence_start_offset"})
_END = frozenset({"end", "end_offset", "evidence_end_offset"})
_SPAN_OFFSETS = frozenset({"start_offset", "end_offset"})
_ENVELOPE_START = frozenset({"start", "evidence_start_offset"})


def _is_length(end: ast.expr, start: ast.Attribute) -> bool:
    return (
        isinstance(end, ast.Attribute) and end.attr in _END and ast.dump(end.value) == ast.dump(start.value)
    )


def offset_shifts(tree: ast.AST) -> Iterator[ast.BinOp | ast.AugAssign]:
    """Every expression in ``tree`` shaped like moving an offset between snapshot and evidence_text."""
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp | ast.AugAssign) and isinstance(node.op, ast.Sub):
            subtracted = node.right if isinstance(node, ast.BinOp) else node.value
            minuend = node.left if isinstance(node, ast.BinOp) else node.target
            if (
                isinstance(subtracted, ast.Attribute)
                and subtracted.attr in _START
                and not _is_length(minuend, subtracted)
            ):
                yield node
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            pair = (node.left, node.right)
            attributes = [operand.attr for operand in pair if isinstance(operand, ast.Attribute)]
            if len(attributes) == 2 and {*attributes} & _ENVELOPE_START and {*attributes} & _SPAN_OFFSETS:
                yield node


def _scanned_files() -> Iterator[Path]:
    for pattern in SCANNED:
        yield from REPOSITORY.glob(pattern)


def _calls_the_mapping(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name | ast.Attribute)
        and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr) == "place_evidence_on_card"
        for node in ast.walk(tree)
    )


def test_card_mapping_arithmetic_exists_once_in_the_whole_tree() -> None:
    shifts: dict[str, list[str]] = {}
    callers: set[str] = set()
    for path in _scanned_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(REPOSITORY).as_posix()
        found = [f"{relative}:{node.lineno}: {ast.unparse(node)}" for node in offset_shifts(tree)]
        if found:
            shifts[relative] = found
        if _calls_the_mapping(tree):
            callers.add(relative)

    # The scan reached the mapping's own arithmetic and the code that exists to use it, so it cannot
    # pass by reading nothing, or by reading production code only.
    assert MAPPING_MODULE in shifts, "the scan did not see the mapping's own arithmetic"
    assert {FIXTURE_MODULE, "packages/debate_core/tests/evidence/test_card_mapping.py"} <= callers, (
        f"the scan did not see the mapping's call sites; it saw {sorted(callers)}"
    )
    assert [line for module, lines in shifts.items() if module != MAPPING_MODULE for line in lines] == []


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("span.start - evidence.start", True),
        ("span.end - evidence.start - omitted", True),
        ("s - card.evidence_start_offset", True),
        ("offset -= evidence.start", True),
        ("card.evidence_start_offset + span.start_offset", True),
        ("span.end_offset + evidence.start", True),
        ("segment.end - segment.start", False),
        ("card.evidence_end_offset - card.evidence_start_offset", False),
        ("omitted.end - omitted.start", False),
        ("len(text) - 1", False),
        ("part.start + 1", False),
        ("card.evidence_start_offset + len(text)", False),
    ],
)
def test_the_offset_shift_scan_flags_the_arithmetic_and_only_it(source: str, flagged: bool) -> None:
    assert bool(list(offset_shifts(ast.parse(source)))) is flagged

"""apply_edit: what each kind of edit does to a card, cut again from its snapshot.

Every expected text, offset and span below is worked out by hand from ``SOURCE`` and written down,
never captured from the code (`docs/process/working-agreements.md` §6). The source is invented.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.fixtures.verification.verification_world import VerificationWorld

from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.domain import (
    Card,
    CardOmission,
    CitationField,
    CitationFieldSource,
    Interpolation,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
)
from debate_core.evidence.card_mapping import snapshot_ranges_of
from debate_core.evidence.edit_policy import EditedCard, NegationFlag, apply_edit
from debate_core.evidence.edits import (
    AddInterpolation,
    DeleteRange,
    EditCite,
    EditKind,
    EditProblem,
    EditTag,
    EvidenceEdit,
    ForbiddenEvidenceEdit,
    InsertText,
    InterpolationBlocksDeletion,
    InvalidEvidenceEdit,
    MoveText,
    RemoveInterpolation,
    ReplaceText,
    SetMarkup,
    kind_of,
)
from debate_core.evidence.markup import EvidenceMarkupSpan
from debate_core.evidence.negation import removes_negation
from debate_core.testing.builders import build_card_span

#: Normalizes to itself: no doubled spaces, no trailing newline. Paragraphs by hand:
#:   0-59    "The council will not approve the new reservoir before 2030."
#:   61-117  "Engineers say the old dam can hold for a decade at most."
#:   119-164 "Residents don't expect rationing this summer."
SOURCE = (
    "The council will not approve the new reservoir before 2030.\n\n"
    "Engineers say the old dam can hold for a decade at most.\n\n"
    "Residents don't expect rationing this summer."
)

# The plain card quotes 0-59 with no omissions, so its evidence-text offsets are snapshot offsets.
#   underline 4-28  "council will not approve"   claim
#   highlight 17-20 "not"                         claim
#   underline 37-58 "reservoir before 2030"      impact
PLAIN_TEXT = "The council will not approve the new reservoir before 2030."

# The cut card, in snapshot offsets:
#   kept     4-28    "council will not approve"                         -> evidence 0-24
#   omitted  28-75   " the new reservoir before 2030.\n\nEngineers say " (47 characters)
#   kept     75-117  "the old dam can hold for a decade at most."      -> evidence 24-66
#   omitted  117-129 "\n\nResidents "                                    (12 characters)
#   kept     129-164 "don't expect rationing this summer."              -> evidence 66-101
# Envelope 4-164 is 160 characters; less 59 omitted leaves 101.
# Markup, snapshot offsets -> evidence offsets:
#   underline 4-28 claim -> 0-24, highlight 17-20 "not" claim -> 13-16,
#   underline 75-117 warrant -> 24-66, highlight 83-95 "dam can hold" warrant -> 32-44,
#   underline 129-164 impact -> 66-101.
CUT_RANGES = ((4, 28), (75, 117), (129, 164))
CUT_TEXT = (
    "council will not approvethe old dam can hold for a decade at most.don't expect rationing this summer."
)

U, H = SpanStyle.UNDERLINE, SpanStyle.HIGHLIGHT
CLAIM, WARRANT, IMPACT = SpanPurpose.CLAIM, SpanPurpose.WARRANT, SpanPurpose.IMPACT

type Marked = list[tuple[SpanStyle, int, int, SpanPurpose | None]]


@pytest.fixture
def world() -> VerificationWorld:
    return VerificationWorld()


@pytest.fixture
def source(world: VerificationWorld) -> LoadedSnapshot:
    return world.add_source(SOURCE)


@pytest.fixture
def plain(world: VerificationWorld, source: LoadedSnapshot) -> Card:
    return world.cut_card(
        source,
        0,
        59,
        (
            EvidenceMarkupSpan.underline(4, 28, CLAIM),
            EvidenceMarkupSpan.highlight(17, 20, CLAIM),
            EvidenceMarkupSpan.underline(37, 58, IMPACT),
        ),
    )


@pytest.fixture
def cut(world: VerificationWorld, source: LoadedSnapshot) -> Card:
    return world.cut_card_from_ranges(
        source,
        CUT_RANGES,
        (
            EvidenceMarkupSpan.underline(4, 28, CLAIM),
            EvidenceMarkupSpan.highlight(17, 20, CLAIM),
            EvidenceMarkupSpan.underline(75, 117, WARRANT),
            EvidenceMarkupSpan.highlight(83, 95, WARRANT),
            EvidenceMarkupSpan.underline(129, 164, IMPACT),
        ),
    )


def edit(card: Card, operation: EvidenceEdit, source: LoadedSnapshot) -> EditedCard:
    return apply_edit(card, operation, source.snapshot, source.normalized)


def marked(card: Card) -> Marked:
    """The card's spans as (style, start, end, purpose), in reading order, underlines first at a tie."""
    return sorted(
        ((span.style, span.start_offset, span.end_offset, span.purpose) for span in card.spans),
        key=lambda item: (item[1], item[0] is H, item[2]),
    )


def omissions(card: Card) -> list[tuple[int, int]]:
    return [(omission.start_offset, omission.end_offset) for omission in card.omitted_ranges]


def test_the_fixture_cards_are_what_the_comments_say(
    world: VerificationWorld, plain: Card, cut: Card
) -> None:
    assert plain.evidence_text == PLAIN_TEXT
    assert marked(plain) == [(U, 4, 28, CLAIM), (H, 17, 20, CLAIM), (U, 37, 58, IMPACT)]
    assert cut.evidence_text == CUT_TEXT
    assert (cut.evidence_start_offset, cut.evidence_end_offset) == (4, 164)
    assert omissions(cut) == [(28, 75), (117, 129)]
    assert marked(cut) == [
        (U, 0, 24, CLAIM),
        (H, 13, 16, CLAIM),
        (U, 24, 66, WARRANT),
        (H, 32, 44, WARRANT),
        (U, 66, 101, IMPACT),
    ]
    assert world.verify(plain).status is VerificationStatus.VERIFIED
    assert world.verify(cut).status is VerificationStatus.VERIFIED


# =============================================================================================
# Deletions: the envelope, the omissions, the text and the markup
# =============================================================================================


def test_a_deletion_inside_a_plain_card_becomes_an_omission_and_splits_the_span_it_cuts(
    world: VerificationWorld, source: LoadedSnapshot, plain: Card
) -> None:
    """Delete "will " (12-17). The claim underline 4-28 loses its middle: two underlines, both claims."""
    edited = edit(plain, DeleteRange(12, 17), source)

    card = edited.card
    assert card.evidence_text == "The council not approve the new reservoir before 2030."
    assert (card.evidence_start_offset, card.evidence_end_offset) == (0, 59)
    assert omissions(card) == [(12, 17)]
    assert marked(card) == [(U, 4, 12, CLAIM), (U, 12, 23, CLAIM), (H, 12, 15, CLAIM), (U, 32, 53, IMPACT)]
    assert card.verification_status is VerificationStatus.UNVERIFIED
    assert edited.kind is EditKind.DELETE_RANGE
    assert edited.negation_flag is None
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_deletion_at_the_start_of_a_plain_card_shrinks_its_envelope_and_adds_no_omission(
    world: VerificationWorld, source: LoadedSnapshot, plain: Card
) -> None:
    card = edit(plain, DeleteRange(0, 4), source).card

    assert card.evidence_text == "council will not approve the new reservoir before 2030."
    assert (card.evidence_start_offset, card.evidence_end_offset) == (4, 59)
    assert card.omitted_ranges == ()
    assert marked(card) == [(U, 0, 24, CLAIM), (H, 13, 16, CLAIM), (U, 33, 54, IMPACT)]
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_deletion_near_an_omission_adds_a_separate_one_and_the_set_stays_canonical(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 8-13, "will " (snapshot 12-17). "not approve" (17-28) is still kept between it
    and the omission at 28, so it is an omission of its own, not part of that one."""
    card = edit(cut, DeleteRange(8, 13), source).card

    assert card.evidence_text == (
        "council not approvethe old dam can hold for a decade at most.don't expect rationing this summer."
    )
    assert (card.evidence_start_offset, card.evidence_end_offset) == (4, 164)
    assert omissions(card) == [(12, 17), (28, 75), (117, 129)]
    assert marked(card) == [
        (U, 0, 8, CLAIM),
        (U, 8, 19, CLAIM),
        (H, 8, 11, CLAIM),
        (U, 19, 61, WARRANT),
        (H, 27, 39, WARRANT),
        (U, 61, 96, IMPACT),
    ]
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_deleting_the_kept_piece_between_two_omissions_merges_them_into_one(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 24-66, the whole middle piece (snapshot 75-117). 28-75, 75-117 and 117-129
    touch, so they are one omission, 28-129. The warrant underline and highlight lose all their text
    and are dropped, their purpose with them."""
    card = edit(cut, DeleteRange(24, 66), source).card

    assert card.evidence_text == "council will not approvedon't expect rationing this summer."
    assert omissions(card) == [(28, 129)]
    assert marked(card) == [(U, 0, 24, CLAIM), (H, 13, 16, CLAIM), (U, 24, 59, IMPACT)]
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_deletion_that_touches_an_omission_widens_it(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 16-24, " approve" (snapshot 20-28), which ends where the omission 28-75 starts."""
    card = edit(cut, DeleteRange(16, 24), source).card

    assert omissions(card) == [(20, 75), (117, 129)]
    assert card.evidence_text.startswith("council will notthe old dam")
    assert marked(card)[:2] == [(U, 0, 16, CLAIM), (H, 13, 16, CLAIM)]
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_deletion_across_a_cut_takes_from_both_kept_pieces_and_never_from_the_omission(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 20-30, "rove" + "the ol": snapshot 24-28 and 75-81, either side of 28-75."""
    card = edit(cut, DeleteRange(20, 30), source).card

    assert card.evidence_text == (
        "council will not appd dam can hold for a decade at most.don't expect rationing this summer."
    )
    assert omissions(card) == [(24, 81), (117, 129)]
    assert marked(card) == [
        (U, 0, 20, CLAIM),
        (H, 13, 16, CLAIM),
        (U, 20, 56, WARRANT),
        (H, 22, 34, WARRANT),
        (U, 56, 91, IMPACT),
    ]
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_deletion_at_the_end_of_a_cut_card_shrinks_its_envelope(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 88-101, " this summer." (snapshot 151-164)."""
    card = edit(cut, DeleteRange(88, 101), source).card

    assert (card.evidence_start_offset, card.evidence_end_offset) == (4, 151)
    assert omissions(card) == [(28, 75), (117, 129)]
    assert card.evidence_text.endswith("most.don't expect rationing")
    assert marked(card)[-1] == (U, 66, 88, IMPACT)
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_a_deletion_is_refused_when_it_runs_past_the_text_or_would_leave_nothing(
    source: LoadedSnapshot, cut: Card
) -> None:
    with pytest.raises(InvalidEvidenceEdit) as past:
        edit(cut, DeleteRange(90, 102), source)
    assert past.value.problem is EditProblem.OUTSIDE_EVIDENCE

    with pytest.raises(InvalidEvidenceEdit) as everything:
        edit(cut, DeleteRange(0, 101), source)
    assert everything.value.problem is EditProblem.DELETES_ALL_EVIDENCE


@pytest.mark.parametrize(
    ("start", "end", "problem"),
    [
        (5, 5, EditProblem.EMPTY_DELETION),
        (6, 5, EditProblem.EMPTY_DELETION),
        (-1, 3, EditProblem.NOT_AN_OFFSET),
        (True, 3, EditProblem.NOT_AN_OFFSET),
        (0, 2.0, EditProblem.NOT_AN_OFFSET),
    ],
)
def test_a_deletion_that_is_not_a_range_is_refused_when_it_is_built(
    start: object, end: object, problem: EditProblem
) -> None:
    with pytest.raises(InvalidEvidenceEdit) as refused:
        DeleteRange(start, end)  # type: ignore[arg-type]
    assert refused.value.problem is problem
    assert refused.value.kind is EditKind.DELETE_RANGE


# =============================================================================================
# The negation flag (ac6)
# =============================================================================================


def test_a_dropped_not_is_flagged_with_the_omission_that_holds_it(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 13-17, "not " (snapshot 17-21). Accepted, flagged, and the highlight that marked
    only "not" is dropped."""
    edited = edit(cut, DeleteRange(13, 17), source)

    assert edited.negation_flag == NegationFlag(CardOmission(start_offset=17, end_offset=21))
    assert edited.card.evidence_text.startswith("council will approvethe old dam")
    assert (H, 13, 16, CLAIM) not in marked(edited.card)
    assert world.verify(edited.card).status is VerificationStatus.VERIFIED


def test_an_ordinary_deletion_is_not_flagged(source: LoadedSnapshot, cut: Card) -> None:
    assert edit(cut, DeleteRange(8, 13), source).negation_flag is None


def test_cutting_the_contraction_out_of_a_word_is_flagged(source: LoadedSnapshot, cut: Card) -> None:
    """Delete evidence 68-71, "n't" of "don't" (snapshot 131-134): the cut is inside a word, so the
    whole word, "don't", is what it touched."""
    edited = edit(cut, DeleteRange(68, 71), source)

    assert edited.negation_flag == NegationFlag(CardOmission(start_offset=131, end_offset=134))
    assert edited.card.evidence_text.endswith("at most.do expect rationing this summer.")


def test_a_negation_cut_from_the_edge_is_flagged_with_no_omission_to_point_at(
    source: LoadedSnapshot, plain: Card
) -> None:
    """Delete 0-21, "The council will not ". The envelope shrinks to 21-59; nothing records the cut."""
    edited = edit(plain, DeleteRange(0, 21), source)

    assert edited.negation_flag == NegationFlag(None)
    assert edited.card.omitted_ranges == ()


def test_a_negation_cut_into_an_existing_omission_names_the_widened_omission(
    source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 12-24, " not approve" (snapshot 16-28), which joins the omission 28-75."""
    edited = edit(cut, DeleteRange(12, 24), source)

    assert edited.negation_flag == NegationFlag(CardOmission(start_offset=16, end_offset=75))


def test_a_cut_beside_a_kept_negation_is_not_flagged_for_it(source: LoadedSnapshot, plain: Card) -> None:
    """Delete 20-28, " approve": it starts at a word's edge, so the "not" it leaves is not touched."""
    assert edit(plain, DeleteRange(20, 28), source).negation_flag is None


@pytest.mark.parametrize(
    ("start", "end", "negates"),
    [
        (17, 20, True),  # "not"
        (16, 20, True),  # " not"
        (12, 16, False),  # "will"
        (20, 28, False),  # " approve"
        (4, 11, False),  # "council"
        (131, 134, True),  # "n't", inside "don't"
        (130, 131, True),  # "o", inside "don't"
        (128, 129, False),  # the space before "don't"
        (119, 128, False),  # "Residents"
        (164, 164, False),  # nothing, at the very end of the text
    ],
)
def test_removes_negation_reads_the_words_a_cut_touches(
    source: LoadedSnapshot, start: int, end: int, negates: bool
) -> None:
    assert removes_negation(source.normalized, ((start, end),)) is negates


@pytest.mark.parametrize(
    ("start", "end", "negates"),
    [
        (5, 10, True),  # "won’t", curly apostrophe
        (17, 19, True),  # "No", capitalised
        (21, 28, False),  # "nothing" is not on the list
        (32, 37, False),  # "knots", which contains "not"
        (42, 48, True),  # "cannot"
        (50, 57, True),  # "neither"
        (59, 66, True),  # "without"
    ],
)
def test_removes_negation_folds_case_and_curly_apostrophes_and_matches_whole_words(
    world: VerificationWorld, start: int, end: int, negates: bool
) -> None:
    # By hand: "won’t" 5-10, "No" 17-19, "nothing" 21-28, "knots" 32-37, "cannot" 42-48,
    # "neither" 50-57, "without" 59-66.
    words = "They won’t sign. No, nothing in knots; we cannot, neither, without."
    other = world.add_source(words)
    assert other.normalized.text == words
    assert removes_negation(other.normalized, ((start, end),)) is negates


# =============================================================================================
# Interpolations (ac3): beside the quotation, moving with it
# =============================================================================================


def with_interpolations(card: Card, *anchors: int) -> Card:
    return card.evolve(interpolations=tuple(Interpolation(anchor=a, text=f"note {a}") for a in anchors))


def test_an_interpolation_is_stored_beside_the_quotation_and_rendered_in_brackets(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    card = edit(cut, AddInterpolation(24, "  the council says "), source).card

    assert card.evidence_text == CUT_TEXT
    assert card.interpolations == (Interpolation(anchor=24, text="the council says"),)
    assert card.interpolations[0].rendered == "[the council says]"
    assert marked(card) == marked(cut)
    assert world.verify(card).status is VerificationStatus.VERIFIED


@pytest.mark.parametrize("text", ["x] will [y", "[the U.S.]", "", "   "])
def test_an_interpolation_holding_a_bracket_or_nothing_is_refused_without_quoting_it(
    source: LoadedSnapshot, cut: Card, text: str
) -> None:
    with pytest.raises(InvalidEvidenceEdit) as refused:
        edit(cut, AddInterpolation(24, text), source)
    assert refused.value.problem is EditProblem.INVALID_INTERPOLATION
    if text.strip():
        assert text not in str(refused.value)


def test_an_interpolation_goes_inside_the_text_or_at_its_end_one_to_a_place(
    source: LoadedSnapshot, cut: Card
) -> None:
    at_end = edit(cut, AddInterpolation(101, "in 2031"), source).card
    assert at_end.interpolations == (Interpolation(anchor=101, text="in 2031"),)

    with pytest.raises(InvalidEvidenceEdit) as past:
        edit(cut, AddInterpolation(102, "in 2031"), source)
    assert past.value.problem is EditProblem.OUTSIDE_EVIDENCE

    with pytest.raises(InvalidEvidenceEdit) as taken:
        edit(at_end, AddInterpolation(101, "again"), source)
    assert taken.value.problem is EditProblem.INTERPOLATION_ALREADY_THERE


def test_interpolations_are_kept_in_anchor_order(source: LoadedSnapshot, cut: Card) -> None:
    card = edit(with_interpolations(cut, 0, 66), AddInterpolation(24, "middle"), source).card

    assert [item.anchor for item in card.interpolations] == [0, 24, 66]


def test_an_interpolation_is_removed_by_its_anchor(source: LoadedSnapshot, cut: Card) -> None:
    card = edit(with_interpolations(cut, 0, 24), RemoveInterpolation(24), source).card
    assert card.interpolations == (Interpolation(anchor=0, text="note 0"),)

    with pytest.raises(InvalidEvidenceEdit) as missing:
        edit(card, RemoveInterpolation(24), source)
    assert missing.value.problem is EditProblem.NO_INTERPOLATION_THERE


def test_a_deletion_moves_the_interpolations_after_it_back_and_those_before_it_not_at_all(
    source: LoadedSnapshot, cut: Card
) -> None:
    """Delete evidence 8-13 ("will "): 5 characters. 0 and 8 stay; 24 and 101 move to 19 and 96."""
    card = edit(with_interpolations(cut, 0, 8, 24, 101), DeleteRange(8, 13), source).card

    assert [item.anchor for item in card.interpolations] == [0, 8, 19, 96]
    assert [item.text for item in card.interpolations] == ["note 0", "note 8", "note 24", "note 101"]


def test_an_interpolation_at_the_far_edge_of_a_deletion_moves_with_the_seam(
    source: LoadedSnapshot, cut: Card
) -> None:
    """Anchored before "not" (13); delete "will " (8-13): it is now before "not" at 8."""
    card = edit(with_interpolations(cut, 13), DeleteRange(8, 13), source).card

    assert card.interpolations == (Interpolation(anchor=8, text="note 13"),)
    assert card.evidence_text[8:11] == "not"


def test_a_deletion_with_an_interpolation_strictly_inside_it_is_refused(
    source: LoadedSnapshot, cut: Card
) -> None:
    with pytest.raises(InterpolationBlocksDeletion) as refused:
        edit(with_interpolations(cut, 10), DeleteRange(8, 13), source)

    assert refused.value.anchors == (10,)
    assert refused.value.kind is EditKind.DELETE_RANGE
    assert "remove the interpolation first" in str(refused.value)


def test_a_deletion_that_would_bring_two_interpolations_to_one_place_is_refused(
    source: LoadedSnapshot, cut: Card
) -> None:
    with pytest.raises(InterpolationBlocksDeletion) as refused:
        edit(with_interpolations(cut, 8, 13), DeleteRange(8, 13), source)

    assert refused.value.anchors == (8, 13)


def test_the_card_refuses_interpolations_out_of_order_past_the_text_or_without_evidence(cut: Card) -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        with_interpolations(cut, 24, 0)
    with pytest.raises(ValueError, match="strictly increasing"):
        with_interpolations(cut, 24, 24)
    with pytest.raises(ValueError, match="past the end"):
        with_interpolations(cut, 102)
    with pytest.raises(ValueError, match="nowhere to put"):
        Card(
            owner_id=cut.owner_id,
            article_id=cut.article_id,
            tag="t",
            provenance_mode=cut.provenance_mode,
            interpolations=(Interpolation(anchor=0, text="x"),),
        )


# =============================================================================================
# Markup
# =============================================================================================


def test_set_markup_replaces_every_span_and_leaves_the_text(
    world: VerificationWorld, source: LoadedSnapshot, plain: Card
) -> None:
    spans = (
        build_card_span(span_id="0SPN0000000000000000000001", start_offset=0, end_offset=11, purpose=WARRANT),
        build_card_span(
            span_id="0SPN0000000000000000000002", start_offset=4, end_offset=11, style=H, purpose=None
        ),
    )
    card = edit(plain, SetMarkup(spans), source).card

    assert card.evidence_text == PLAIN_TEXT
    assert marked(card) == [(U, 0, 11, WARRANT), (H, 4, 11, None)]
    assert world.verify(card).status is VerificationStatus.VERIFIED


def test_set_markup_across_a_cut_marks_each_side_separately(source: LoadedSnapshot, cut: Card) -> None:
    span = build_card_span(start_offset=20, end_offset=30, purpose=CLAIM)
    card = edit(cut, SetMarkup((span,)), source).card

    assert marked(card) == [(U, 20, 24, CLAIM), (U, 24, 30, CLAIM)]


@pytest.mark.parametrize(
    ("spans", "problem"),
    [
        (((0, 10, U), (5, 15, U)), EditProblem.INVALID_MARKUP),
        (((0, 10, U), (8, 12, H)), EditProblem.INVALID_MARKUP),
        (((0, 102, U),), EditProblem.OUTSIDE_EVIDENCE),
    ],
    ids=["underlines-overlap", "highlight-not-underlined", "past-the-text"],
)
def test_set_markup_that_does_not_fit_is_refused(
    source: LoadedSnapshot, cut: Card, spans: tuple[tuple[int, int, SpanStyle], ...], problem: EditProblem
) -> None:
    card_spans = tuple(build_card_span(start_offset=s, end_offset=e, style=style) for s, e, style in spans)
    with pytest.raises(InvalidEvidenceEdit) as refused:
        edit(cut, SetMarkup(card_spans), source)
    assert refused.value.problem is problem


# =============================================================================================
# Tag and cite
# =============================================================================================


def test_the_tag_is_freely_editable_and_the_evidence_is_untouched(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    card = edit(cut, EditTag("Rationing is years away"), source).card

    assert card.tag == "Rationing is years away"
    assert (card.evidence_text, card.omitted_ranges, marked(card)) == (
        CUT_TEXT,
        cut.omitted_ranges,
        marked(cut),
    )
    assert world.verify(card).status is VerificationStatus.VERIFIED

    with pytest.raises(InvalidEvidenceEdit) as empty:
        edit(cut, EditTag("   "), source)
    assert empty.value.problem is EditProblem.INVALID_TAG


def test_a_cite_edit_may_change_a_field_but_not_claim_it_is_verified(
    world: VerificationWorld, source: LoadedSnapshot, cut: Card
) -> None:
    credentials = CitationField[str](
        value="Professor of hydrology", source=CitationFieldSource.BYLINE, verified=False
    )
    card = edit(cut, EditCite(cut.citation.evolve(author_credentials=credentials)), source).card
    assert card.citation.author_credentials == credentials
    assert world.verify(card).status is VerificationStatus.VERIFIED

    forged = CitationField[str](value="An invented title", source=CitationFieldSource.CROSSREF, verified=True)
    with pytest.raises(InvalidEvidenceEdit) as refused:
        edit(cut, EditCite(cut.citation.evolve(title=forged)), source)
    assert refused.value.problem is EditProblem.CITATION_CLAIMS_VERIFICATION
    assert "An invented title" not in str(refused.value)


# =============================================================================================
# Insertions, substitutions and moves (ac2)
# =============================================================================================

FORBIDDEN: list[tuple[EvidenceEdit, EditKind]] = [
    (InsertText(13, "certainly "), EditKind.INSERT_TEXT),
    (InsertText(0, ""), EditKind.INSERT_TEXT),
    (ReplaceText(13, 16, "now"), EditKind.REPLACE_TEXT),
    (ReplaceText(13, 16, "not"), EditKind.REPLACE_TEXT),
    (ReplaceText(13, 16, ""), EditKind.REPLACE_TEXT),
    (MoveText(0, 8, 24), EditKind.MOVE_TEXT),
]


@pytest.mark.parametrize(("operation", "kind"), FORBIDDEN, ids=repr)
def test_an_insertion_substitution_or_move_is_refused_by_kind_whatever_its_payload(
    source: LoadedSnapshot, cut: Card, operation: EvidenceEdit, kind: EditKind
) -> None:
    with pytest.raises(ForbiddenEvidenceEdit) as refused:
        edit(cut, operation, source)

    assert refused.value.kind is kind
    payload = getattr(operation, "text", "")
    if payload:
        assert payload not in str(refused.value)
        assert payload not in repr(operation)


def test_a_forbidden_edit_is_refused_before_the_snapshot_is_looked_at(
    world: VerificationWorld, cut: Card
) -> None:
    """The kind alone decides: even a snapshot that is not the card's is never consulted."""
    other = world.add_source("An unrelated passage.")
    with pytest.raises(ForbiddenEvidenceEdit):
        apply_edit(cut, InsertText(0, "x"), other.snapshot, other.normalized)


@pytest.mark.parametrize(
    "build",
    [
        lambda: SetMarkup([build_card_span()]),  # type: ignore[arg-type]
        lambda: AddInterpolation(0, b"bytes"),  # type: ignore[arg-type]
        lambda: EditTag(None),  # type: ignore[arg-type]
        lambda: EditCite({"title": "x"}),  # type: ignore[arg-type]
        lambda: RemoveInterpolation(-2),
    ],
    ids=["markup-list", "interpolation-bytes", "tag-none", "cite-dict", "remove-negative"],
)
def test_an_edit_whose_fields_have_the_wrong_type_is_refused_when_it_is_built(
    build: Callable[[], object],
) -> None:
    """Edits will arrive deserialized from an editor, past the type checker."""
    with pytest.raises(InvalidEvidenceEdit) as refused:
        build()
    assert refused.value.problem in {EditProblem.NOT_AN_EDIT, EditProblem.NOT_AN_OFFSET}


def test_anything_that_is_not_an_edit_is_refused() -> None:
    with pytest.raises(InvalidEvidenceEdit) as refused:
        kind_of("delete 0-4")
    assert refused.value.problem is EditProblem.NOT_AN_EDIT
    assert refused.value.kind is None


# =============================================================================================
# An edit does what it says and nothing else
# =============================================================================================


@pytest.mark.parametrize(
    "operation",
    [DeleteRange(8, 13), EditTag("A new tag"), AddInterpolation(0, "x"), SetMarkup((build_card_span(),))],
    ids=repr,
)
def test_an_edit_to_a_card_that_does_not_match_its_snapshot_is_refused_not_repaired(
    source: LoadedSnapshot, cut: Card, operation: EvidenceEdit
) -> None:
    """ "council" altered to "cooncil": the same length, so the card is constructible and storable.
    Re-cutting would quietly restore the snapshot's word; the edit is refused instead."""
    altered = cut.evolve(evidence_text="cooncil" + cut.evidence_text[7:])

    with pytest.raises(InvalidEvidenceEdit) as refused:
        edit(altered, operation, source)
    assert refused.value.problem is EditProblem.QUOTATION_DOES_NOT_MATCH_SNAPSHOT


def test_an_edit_needs_the_cards_own_snapshot(world: VerificationWorld, cut: Card) -> None:
    other = world.add_source("An unrelated passage.")
    with pytest.raises(ValueError, match="quotes snapshot"):
        apply_edit(cut, EditTag("x"), other.snapshot, other.normalized)


# =============================================================================================
# The inverse mapping the policy relies on
# =============================================================================================


@pytest.mark.parametrize(
    ("start", "end", "ranges"),
    [
        (0, 24, ((4, 28),)),
        (0, 101, CUT_RANGES),
        (20, 30, ((24, 28), (75, 81))),
        (24, 24, ()),
        (66, 101, ((129, 164),)),
        (65, 67, ((116, 117), (129, 130))),
    ],
)
def test_snapshot_ranges_of_maps_an_evidence_range_to_the_snapshot_pieces_it_was_cut_from(
    cut: Card, start: int, end: int, ranges: tuple[tuple[int, int], ...]
) -> None:
    assert snapshot_ranges_of(cut, start, end) == ranges


@pytest.mark.parametrize(("start", "end"), [(-1, 3), (5, 4), (0, 102)])
def test_snapshot_ranges_of_refuses_a_range_outside_the_text(cut: Card, start: int, end: int) -> None:
    with pytest.raises(ValueError, match="is not a range"):
        snapshot_ranges_of(cut, start, end)

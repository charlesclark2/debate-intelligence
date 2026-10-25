"""CP texts, K alternatives, roles of the ballot and overviews, found, placed and ranked (`v1-e32-t11` ac2).

The PM's rulings of 2026-10-24 on the counts: CP texts by label, and by their place (the first `should`
analytic of a block placed under a CP the team reads) past the actor guard; the label lists as proposed,
with what they leave out; overviews counted only; the top 3 texts per position; a text naming a school
of the caselist withheld and counted; and a text belongs to the nearest placed heading over its label,
never a guess.

Every taxonomy, heading, school and text here is invented, and every expected value is written by hand.
"""

from __future__ import annotations

from typing import Any

import pytest

from debate_core.arguments.landscape.analytic_texts import (
    AnalyticTextRules,
    CounterplanActors,
    SectionParagraph,
    SourceParagraphs,
    TextGroup,
    names_a_school,
    passes_actor_guard,
    read_analytic_texts,
    read_back_texts,
    text_digest,
    top_texts,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, PositionRole
from debate_core.domain.landscape_texts import (
    AnalyticTextKind,
    AnalyticTextReading,
    MoreTexts,
    QuotedText,
    TextForm,
    TextPlacement,
)
from debate_core.domain.style_profile import StructuralUnit

POCKET = StructuralUnit.POCKET
HAT = StructuralUnit.HAT
BLOCK = StructuralUnit.BLOCK
TAG = StructuralUnit.TAG
CITE = StructuralUnit.CITE
EVIDENCE = StructuralUnit.EVIDENCE
ANALYTIC = StructuralUnit.ANALYTIC
OTHER = StructuralUnit.OTHER

CP = AnalyticTextKind.CP_TEXT
ALT = AnalyticTextKind.K_ALTERNATIVE
ROB = AnalyticTextKind.ROLE_OF_THE_BALLOT
OVERVIEW = AnalyticTextKind.OVERVIEW

FIFTY_STATES = "The fifty states should establish a sample single payer system."
CONGRESS = "Congress should establish a sample payment cap."
THEORY = "Our counter interpretation is that we should get one conditional advocacy."
ALTERNATIVE = "The alternative is to reject the market in sample care."
ROLE = "The role of the ballot is to vote for the best sample methodology."
SCHOOLS = CaselistNames({"Lakeside Academy": ("LA",), "Harbor High": ("HH",)})


def _position(identifier: str, kind: str, side: str, aliases: list[str]) -> dict[str, Any]:
    label = identifier.replace("-", " ").capitalize()
    return {"id": identifier, "label": label, "kind": kind, "side": side, "aliases": aliases}


TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            _position("sample-aff", "aff", "aff", ["sample aff"]),
            _position("states-cp", "cp", "neg", ["states cp"]),
            _position("cap-k", "k", "neg", ["cap k"]),
            _position("midterms-da", "da", "neg", ["midterms da"]),
        ],
    }
)
OVERRIDES = OverrideRules.model_validate(
    {"topic_id": "sample-topic", "overrides": [{"heading": "extra", "position_id": None}]}
)
ACTORS = CounterplanActors(topic_id="sample-topic", cp_text_actors=("fifty states", "congress", "usfg"))
RULES = AnalyticTextRules(TAXONOMY, OVERRIDES, ACTORS)


def p(index: int, unit: StructuralUnit, text: str, *path: str) -> SectionParagraph:
    return SectionParagraph(element_index=index, unit=unit, text=text, section_path=tuple(path))


def read(*paragraphs: SectionParagraph, in_cards: frozenset[int] = frozenset(), own: tuple[str, ...] = ()):
    return read_analytic_texts(
        SourceParagraphs(paragraphs=paragraphs, in_cards=in_cards), RULES, own_names=own, caselist=SCHOOLS
    )


def reading(
    kind: AnalyticTextKind,
    form: TextForm,
    label: int,
    index: int,
    unit: StructuralUnit,
    text: str | None,
    position: str | None,
    *,
    kept: bool = False,
    role: PositionRole | None = PositionRole.READS,
    placement: TextPlacement = TextPlacement.PLACED,
) -> AnalyticTextReading:
    return AnalyticTextReading(
        kind=kind,
        form=form,
        label_element_index=label,
        element_index=index,
        unit=unit,
        kept=kept,
        digest=None if text is None else text_digest(text),
        placement=placement,
        position_id=position,
        role=role if position is not None else None,
    )


# ------------------------------------------------------------------------------------------------
# CP texts
# ------------------------------------------------------------------------------------------------


def test_an_inline_text_label_with_should_under_a_placed_cp_is_its_cp_text() -> None:
    found = read(
        p(0, HAT, "States CP"),
        p(1, ANALYTIC, "Text: " + FIFTY_STATES, "States CP"),
    )
    assert found.readings == (
        reading(CP, TextForm.INLINE, 1, 1, ANALYTIC, "Text: " + FIFTY_STATES, "states-cp"),
    )


@pytest.mark.parametrize("label", ["CP Text:", "Counterplan Text:", "CP:", "Counterplan:", "The CP:"])
def test_every_inline_cp_label_opens_a_cp_text(label: str) -> None:
    text = f"{label} {CONGRESS}"
    found = read(p(4, HAT, "States CP"), p(5, OTHER, text, "States CP"))
    assert [(one.kind, one.form, one.element_index) for one in found.readings] == [(CP, TextForm.INLINE, 5)]


def test_an_inline_label_without_should_is_a_heading_naming_the_cp_not_its_text() -> None:
    assert read(p(0, HAT, "CP: States"), p(1, TAG, "States solve", "CP: States")).readings == ()


def test_a_cp_text_label_on_its_own_quotes_the_paragraph_under_it() -> None:
    found = read(
        p(0, HAT, "States CP"),
        p(1, BLOCK, "CP Text", "States CP"),
        p(2, ANALYTIC, CONGRESS, "States CP", "CP Text"),
    )
    assert found.readings == (reading(CP, TextForm.LABEL, 1, 2, ANALYTIC, CONGRESS, "states-cp"),)


def test_a_cp_text_label_over_a_paragraph_without_should_is_not_counted() -> None:
    found = read(
        p(0, HAT, "States CP"),
        p(1, BLOCK, "Text", "States CP"),
        p(2, ANALYTIC, "States solve better", "States CP", "Text"),
    )
    assert found.readings == ()


def test_the_first_should_analytic_of_a_block_under_a_placed_cp_is_its_text_by_place() -> None:
    found = read(
        p(0, HAT, "States CP"),
        p(1, BLOCK, "1NC", "States CP"),
        p(2, ANALYTIC, FIFTY_STATES, "States CP", "1NC"),
        p(3, ANALYTIC, CONGRESS, "States CP", "1NC"),
        p(4, BLOCK, "Solvency", "States CP"),
        p(5, ANALYTIC, CONGRESS, "States CP", "Solvency"),
    )
    assert found.readings == (
        reading(CP, TextForm.BY_PLACE, 2, 2, ANALYTIC, FIFTY_STATES, "states-cp"),
        reading(CP, TextForm.BY_PLACE, 5, 5, ANALYTIC, CONGRESS, "states-cp"),
    )
    assert found.refused_by_guard == 0


def test_the_actor_guard_refuses_a_should_analytic_naming_no_actor_and_counts_it() -> None:
    found = read(p(0, HAT, "States CP"), p(1, ANALYTIC, THEORY, "States CP"))
    assert (found.readings, found.refused_by_guard) == ((), 1)


def test_the_actor_guard_refuses_an_actor_more_than_twelve_words_before_should() -> None:
    late = (
        "In a world of sample markets and many sample hospitals across every region "
        "the fifty states should act."
    )
    assert not passes_actor_guard(late, ACTORS.cp_text_actors)
    found = read(p(0, HAT, "States CP"), p(1, ANALYTIC, late, "States CP"))
    assert (found.readings, found.refused_by_guard) == ((), 1)


@pytest.mark.parametrize(
    ("text", "passes"),
    [
        (FIFTY_STATES, True),
        (CONGRESS, True),
        ("The USFG should establish a sample cap.", True),
        ("Twelve words come first here before the actor so that congress should act.", True),
        (THEORY, False),
        ("The states should act.", False),
        ("Congressional staff say the plan works.", False),
        ("Sample congressmen should act.", False),
    ],
)
def test_the_actor_guard_needs_an_actor_phrase_as_whole_words_before_should(text: str, passes: bool) -> None:
    assert passes_actor_guard(text, ACTORS.cp_text_actors) is passes


def test_a_text_by_place_needs_a_cp_the_team_reads() -> None:
    assert read(p(0, HAT, "Midterms DA"), p(1, ANALYTIC, CONGRESS, "Midterms DA")).readings == ()
    assert read(p(0, HAT, "AT: States CP"), p(1, ANALYTIC, CONGRESS, "AT: States CP")).readings == ()
    assert read(p(0, HAT, "OFF"), p(1, ANALYTIC, CONGRESS, "OFF")).readings == ()


def test_a_text_by_place_is_an_analytic_the_store_does_not_keep_and_the_first_should_of_its_block() -> None:
    kept = read(p(0, HAT, "States CP"), p(1, ANALYTIC, CONGRESS, "States CP"), in_cards=frozenset({1}))
    assert kept.readings == ()
    tag_first = read(
        p(0, HAT, "States CP"),
        p(1, TAG, "States should act first", "States CP"),
        p(2, ANALYTIC, CONGRESS, "States CP"),
    )
    assert tag_first.readings == ()


def test_a_should_paragraph_over_120_words_does_not_take_the_blocks_first_place() -> None:
    long = "Congress should act " + "and sample words " * 40
    found = read(
        p(0, HAT, "States CP"), p(1, ANALYTIC, long, "States CP"), p(2, ANALYTIC, CONGRESS, "States CP")
    )
    assert [one.element_index for one in found.readings] == [2]


def test_an_inline_label_is_not_read_twice_by_its_place() -> None:
    found = read(p(0, HAT, "States CP"), p(1, ANALYTIC, "Text: " + CONGRESS, "States CP"))
    assert [(one.form, one.element_index) for one in found.readings] == [(TextForm.INLINE, 1)]


def test_a_shape_rule_needs_its_actors_and_without_config_reads_nothing_by_place() -> None:
    rules = AnalyticTextRules(TAXONOMY, OVERRIDES, None)
    found = read_analytic_texts(
        SourceParagraphs(paragraphs=(p(0, HAT, "States CP"), p(1, ANALYTIC, CONGRESS, "States CP"))),
        rules,
        caselist=SCHOOLS,
    )
    assert (found.readings, found.refused_by_guard) == ((), 1)


# ------------------------------------------------------------------------------------------------
# Alternatives and roles of the ballot
# ------------------------------------------------------------------------------------------------


def test_an_alternative_sentence_is_its_own_text_kept_as_a_card_tag() -> None:
    found = read(p(0, HAT, "Cap K"), p(1, TAG, ALTERNATIVE, "Cap K"), in_cards=frozenset({1, 2, 3}))
    assert found.readings == (reading(ALT, TextForm.SENTENCE, 1, 1, TAG, ALTERNATIVE, "cap-k", kept=True),)


@pytest.mark.parametrize(
    "sentence",
    [
        "The alt is to vote negative.",
        "Our alternative is sample refusal.",
        "The alternative should be refusal.",
    ],
)
def test_every_alternative_sentence_is_read(sentence: str) -> None:
    assert [one.kind for one in read(p(0, HAT, "Cap K"), p(1, ANALYTIC, sentence, "Cap K")).readings] == [ALT]


def test_an_alt_label_quotes_the_tag_under_it() -> None:
    found = read(
        p(0, HAT, "Cap K"),
        p(1, BLOCK, "Alt", "Cap K"),
        p(2, TAG, "Reject sample markets", "Cap K", "Alt"),
    )
    assert found.readings == (reading(ALT, TextForm.LABEL, 1, 2, TAG, "Reject sample markets", "cap-k"),)


def test_an_alt_label_over_a_heading_or_evidence_holds_no_text() -> None:
    over_heading = read(p(0, HAT, "Cap K"), p(1, BLOCK, "Alt", "Cap K"), p(2, BLOCK, "Socialism", "Cap K"))
    over_evidence = read(
        p(0, HAT, "Cap K"), p(1, BLOCK, "Alternative", "Cap K"), p(2, EVIDENCE, "Quoted", "Cap K")
    )
    assert over_heading.readings == over_evidence.readings == ()


def test_an_inline_alt_in_an_analytic_is_read_and_as_a_heading_is_left_out() -> None:
    inline = read(p(0, HAT, "Cap K"), p(1, ANALYTIC, "Alt: reject sample markets", "Cap K"))
    assert [(one.kind, one.form) for one in inline.readings] == [(ALT, TextForm.INLINE)]
    assert read(p(0, HAT, "Cap K"), p(1, BLOCK, "Alt - Socialism", "Cap K")).readings == ()


@pytest.mark.parametrize("answer", ["Alt causes", "Alt fails", "Perm do the alt", "Alt cause to rural care"])
def test_answers_to_an_alt_are_left_out(answer: str) -> None:
    assert (
        read(p(0, HAT, "Cap K"), p(1, BLOCK, answer, "Cap K"), p(2, TAG, "Sample tag", "Cap K")).readings
        == ()
    )


def test_a_role_of_the_ballot_label_and_sentence_are_read() -> None:
    found = read(
        p(0, HAT, "Cap K"),
        p(1, BLOCK, "Role of the Ballot", "Cap K"),
        p(2, ANALYTIC, "Vote for the sample method.", "Cap K", "Role of the Ballot"),
        p(3, ANALYTIC, ROLE, "Cap K", "Role of the Ballot"),
    )
    assert found.readings == (
        reading(ROB, TextForm.LABEL, 1, 2, ANALYTIC, "Vote for the sample method.", "cap-k"),
        reading(ROB, TextForm.SENTENCE, 3, 3, ANALYTIC, ROLE, "cap-k"),
    )


@pytest.mark.parametrize("label", ["ROB", "ROJ", "Role of the judge", "Role of judge"])
def test_every_role_of_the_ballot_label_is_read(label: str) -> None:
    found = read(p(0, HAT, "Cap K"), p(1, BLOCK, label, "Cap K"), p(2, ANALYTIC, "Vote sample.", "Cap K"))
    assert [one.kind for one in found.readings] == [ROB]


@pytest.mark.parametrize("left_out", ["Ballot", "Ballot PIK", "Presumption ballot"])
def test_ballot_on_its_own_or_a_ballot_pik_is_left_out(left_out: str) -> None:
    assert (
        read(p(0, HAT, "Cap K"), p(1, BLOCK, left_out, "Cap K"), p(2, ANALYTIC, "Vote.", "Cap K")).readings
        == ()
    )


# ------------------------------------------------------------------------------------------------
# Overviews: counted, never quoted
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label", ["Overview", "O/V", "OV", "OVW", "Impact overview", "Link O/V", "Overview - Cap K"]
)
def test_an_overview_label_is_counted_with_no_digest(label: str) -> None:
    found = read(
        p(0, HAT, "Midterms DA"), p(1, BLOCK, label, "Midterms DA"), p(2, BLOCK, "Uniqueness", "Midterms DA")
    )
    assert found.readings == (reading(OVERVIEW, TextForm.LABEL, 1, 1, BLOCK, None, "midterms-da"),)


def test_outweighs_is_not_an_overview() -> None:
    assert read(p(0, HAT, "Midterms DA"), p(1, BLOCK, "Extinction O/W", "Midterms DA")).readings == ()


# ------------------------------------------------------------------------------------------------
# Placement: the nearest placed heading over the label, never a guess
# ------------------------------------------------------------------------------------------------


def test_a_label_under_headings_that_normalize_to_nothing_is_under_no_heading() -> None:
    found = read(p(0, POCKET, "1NC"), p(1, HAT, "OFF", "1NC"), p(2, TAG, ALTERNATIVE, "1NC", "OFF"))
    assert found.readings == (
        reading(ALT, TextForm.SENTENCE, 2, 2, TAG, ALTERNATIVE, None, placement=TextPlacement.NO_HEADING),
    )


def test_a_label_under_headings_that_place_nothing_is_kept_unplaced() -> None:
    found = read(p(0, HAT, "Sample criticism"), p(1, TAG, ALTERNATIVE, "Sample criticism"))
    assert [(one.placement, one.position_id) for one in found.readings] == [
        (TextPlacement.HEADINGS_PLACE_NOTHING, None)
    ]


def test_a_heading_the_coach_ruled_names_no_position_places_nothing() -> None:
    found = read(p(0, HAT, "Extra"), p(1, TAG, ALTERNATIVE, "Extra"))
    assert [one.placement for one in found.readings] == [TextPlacement.HEADINGS_PLACE_NOTHING]


def test_the_nearest_placed_heading_wins_and_an_answer_heading_makes_it_an_answer() -> None:
    nearest = read(
        p(0, HAT, "Cap K"), p(1, BLOCK, "States CP", "Cap K"), p(2, TAG, ALTERNATIVE, "Cap K", "States CP")
    )
    assert [one.position_id for one in nearest.readings] == ["states-cp"]
    inherited = read(
        p(0, HAT, "Cap K"), p(1, BLOCK, "Links", "Cap K"), p(2, TAG, ALTERNATIVE, "Cap K", "Links")
    )
    assert [(one.position_id, one.role) for one in inherited.readings] == [("cap-k", PositionRole.READS)]
    answered = read(p(0, HAT, "AT: Cap K"), p(1, TAG, ALTERNATIVE, "AT: Cap K"))
    assert [(one.position_id, one.role) for one in answered.readings] == [("cap-k", PositionRole.ANSWERS)]


def test_an_open_tag_in_the_path_is_no_heading() -> None:
    source = SourceParagraphs(
        paragraphs=(
            p(0, HAT, "Cap K"),
            p(1, TAG, "States CP", "Cap K"),
            p(2, ANALYTIC, ALTERNATIVE, "Cap K", "States CP"),
        ),
        tags=frozenset({"States CP"}),
    )
    found = read_analytic_texts(source, RULES, caselist=SCHOOLS)
    assert [(one.element_index, one.position_id) for one in found.readings] == [(2, "cap-k")]


def test_the_teams_own_names_and_the_caselists_schools_are_taken_out_of_a_heading() -> None:
    own = read(
        p(0, HAT, "Riverside RS States CP"),
        p(1, ANALYTIC, CONGRESS, "Riverside RS States CP"),
        own=("Riverside", "RS"),
    )
    assert [one.position_id for one in own.readings] == ["states-cp"]
    school = read(
        p(0, HAT, "Lakeside Academy States CP"), p(1, ANALYTIC, CONGRESS, "Lakeside Academy States CP")
    )
    assert [one.position_id for one in school.readings] == ["states-cp"]


def test_a_label_is_normalized_with_the_teams_own_names_taken_out() -> None:
    found = read(
        p(0, HAT, "Cap K"), p(1, BLOCK, "RS Alt", "Cap K"), p(2, TAG, "Reject markets", "Cap K"), own=("RS",)
    )
    assert [one.kind for one in found.readings] == [ALT]


# ------------------------------------------------------------------------------------------------
# The cache key, reading back, and showing texts
# ------------------------------------------------------------------------------------------------


def test_the_rules_digest_moves_with_the_actors_the_taxonomy_and_the_overrides() -> None:
    same = AnalyticTextRules(TAXONOMY, OVERRIDES, ACTORS)
    assert same.digest == RULES.digest
    other_actors = CounterplanActors(topic_id="sample-topic", cp_text_actors=("fifty states",))
    bumped = Taxonomy.model_validate({**TAXONOMY.model_dump(mode="json"), "taxonomy_version": "1.0.1"})
    no_overrides = OverrideRules(topic_id="sample-topic")
    assert (
        len(
            {
                RULES.digest,
                AnalyticTextRules(TAXONOMY, OVERRIDES, other_actors).digest,
                AnalyticTextRules(bumped, OVERRIDES, ACTORS).digest,
                AnalyticTextRules(TAXONOMY, no_overrides, ACTORS).digest,
                AnalyticTextRules(TAXONOMY, OVERRIDES, None).digest,
            }
        )
        == 5
    )


def test_a_reading_keeps_no_text_in_its_repr_or_dump() -> None:
    (one,) = read(p(0, HAT, "Cap K"), p(1, TAG, ALTERNATIVE, "Cap K")).readings
    assert "market" not in repr(one) and "market" not in one.model_dump_json()


def test_reading_back_returns_only_paragraphs_that_still_hash_to_their_digest() -> None:
    wanted = (
        reading(ALT, TextForm.SENTENCE, 1, 1, TAG, ALTERNATIVE, "cap-k"),
        reading(CP, TextForm.BY_PLACE, 2, 2, ANALYTIC, CONGRESS, "states-cp"),
        reading(CP, TextForm.BY_PLACE, 9, 9, ANALYTIC, CONGRESS, "states-cp"),
    )
    paragraphs = (
        p(1, TAG, "  The alternative IS to reject the market, in sample care!  "),
        p(2, ANALYTIC, "Congress should establish a different cap."),
    )
    assert read_back_texts(paragraphs, wanted) == {
        1: "  The alternative IS to reject the market, in sample care!  "
    }


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("Lakeside Academy should lead sample reform.", True),
        ("The harbor high tide should rise.", True),
        ("The lakeside should lead.", False),
        ("Congress should act.", False),
    ],
)
def test_a_text_names_a_school_when_it_holds_the_schools_whole_name(text: str, names: bool) -> None:
    assert names_a_school(text, SCHOOLS) is names


def _group(teams: int, *texts: tuple[str, int, str], first_team: int = 0) -> TextGroup:
    return TextGroup(teams=frozenset(range(first_team, first_team + teams)), texts=texts)


def test_top_texts_rank_by_teams_then_digest_and_count_the_rest() -> None:
    a, b, c, d = ("Alpha should act.", "Bravo should act.", "Charlie should act.", "Delta should act.")
    groups = {
        text_digest(a): _group(1, ("s1", 1, a), first_team=10),
        text_digest(b): _group(4, ("s2", 1, b)),
        text_digest(c): _group(2, ("s3", 1, c), first_team=20),
        text_digest(d): _group(2, ("s4", 1, d), first_team=30),
    }
    quoted, more, withheld = top_texts("states-cp", CP, groups, limit=3, caselist=SCHOOLS)
    tied = sorted([(text_digest(c), c), (text_digest(d), d)])
    assert [(one.rank, one.teams, one.text) for one in quoted] == [
        (1, 4, b),
        (2, 2, tied[0][1]),
        (3, 2, tied[1][1]),
    ]
    assert more == MoreTexts(position_id="states-cp", kind=CP, texts=1, teams=1)
    assert withheld == 0
    assert all(one == QuotedText.model_validate(one.model_dump()) for one in quoted)


def test_a_text_naming_a_school_is_withheld_counted_and_the_next_moves_up() -> None:
    named, plain = "Lakeside Academy should act.", "Bravo should act."
    groups = {
        text_digest(named): _group(5, ("s1", 1, named)),
        text_digest(plain): _group(1, ("s2", 1, plain)),
    }
    quoted, more, withheld = top_texts("states-cp", CP, groups, limit=1, caselist=SCHOOLS)
    assert [(one.rank, one.text) for one in quoted] == [(1, plain)]
    assert (more, withheld) == (None, 1)


def test_the_more_line_counts_distinct_teams_past_the_cut_off() -> None:
    texts = [f"Sample {word} should act." for word in ("one", "two", "three", "four", "five")]
    groups = {
        text_digest(one): TextGroup(teams=frozenset({"team"}), texts=(("s", i, one),))
        for i, one in enumerate(texts)
    }
    _, more, _ = top_texts("states-cp", CP, groups, limit=3, caselist=SCHOOLS)
    assert more == MoreTexts(position_id="states-cp", kind=CP, texts=2, teams=1)


def test_a_group_shows_its_commonest_wording_then_the_first_by_source_and_paragraph() -> None:
    upper, lower = "Congress Should Act.", "congress should act."
    group = TextGroup(teams=frozenset({1, 2, 3}), texts=(("b", 1, upper), ("a", 5, lower), ("c", 2, upper)))
    quoted, _, _ = top_texts("states-cp", CP, {text_digest(upper): group}, limit=3, caselist=SCHOOLS)
    assert [one.text for one in quoted] == [upper]
    tie = TextGroup(teams=frozenset({1}), texts=(("b", 1, upper), ("a", 5, lower)))
    quoted, _, _ = top_texts("states-cp", CP, {text_digest(upper): tie}, limit=3, caselist=SCHOOLS)
    assert [one.text for one in quoted] == [lower]


def test_a_group_with_no_text_read_again_is_not_shown_or_withheld() -> None:
    groups = {text_digest("Gone should act."): TextGroup(teams=frozenset({1}))}
    assert top_texts("states-cp", CP, groups, limit=3, caselist=SCHOOLS) == ((), None, 0)

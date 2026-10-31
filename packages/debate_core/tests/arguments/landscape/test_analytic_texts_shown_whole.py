"""A CP text shown whole: its listed planks, or the paragraphs continuing it, under it (`v1-e32-t35` ac1).

The PM's context of 2026-11-01, from the coach's read of hspolicy26's report and the count over the store:
* A CP text ending in a colon is shown with the planks `v1-e32-t16` lists after it, by t16's rules and caps
  (list paragraphs up to the block's first card or heading, at most 60 words, an alias-only label not a
  plank, none when the CP text fails the actor guard), each on its own line under it.
* A CP text ending with no sentence end (a word or a dash), whose next paragraph is an analytic outside a
  card, is continued by the analytics after it, up to the first paragraph that is not one: the shape the
  count found (a plank list with no colon). Never across a heading, a card or another CP text.
* The PM's review of 2026-10-31: texts are grouped and ranked by their opening paragraph, as before t35, and
  a group shows the whole text the most of its teams read, with how many read it. Read-back and the school
  check cover every line of the text shown, and a whole text naming a school is passed over for the next.

Every taxonomy, heading, school and text here is invented, and every expected value is written by hand.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.arguments.landscape.analytic_texts import (
    AnalyticTextRules,
    CounterplanActors,
    SectionParagraph,
    SourceParagraphs,
    SourceTexts,
    TextGroup,
    read_analytic_texts,
    read_back_texts,
    text_digest,
    top_texts,
    whole_text,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, PositionRole
from debate_core.domain.landscape_texts import (
    AnalyticTextKind,
    AnalyticTextReading,
    QuotedText,
    TextForm,
    TextPlacement,
)
from debate_core.domain.style_profile import StructuralUnit

BLOCK = StructuralUnit.BLOCK
TAG = StructuralUnit.TAG
EVIDENCE = StructuralUnit.EVIDENCE
ANALYTIC = StructuralUnit.ANALYTIC
UNDERTAG = StructuralUnit.UNDERTAG

CP = AnalyticTextKind.CP_TEXT
PLANK = AnalyticTextKind.CP_PLANK
STATES = "States CP"
SCHOOLS = CaselistNames({"Lakeside Academy": ("LA",)})

STEM = "The fifty states and all relevant territories should:"
OPEN_STEM = "The fifty states and all relevant territories should"
CLINICS = "Expand sample clinics in rural areas."
PRIZE = "Fund a sample research prize."


def _position(identifier: str, kind: str, side: str, aliases: list[str]) -> dict[str, Any]:
    label = identifier.replace("-", " ").capitalize()
    return {"id": identifier, "label": label, "kind": kind, "side": side, "aliases": aliases}


TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            _position("single-payer-aff", "aff", "aff", ["single payer"]),
            _position("costs-advantage", "advantage", "aff", ["costs"]),
            _position("states-cp", "cp", "neg", ["states cp"]),
        ],
    }
)
OVERRIDES = OverrideRules.model_validate({"topic_id": "sample-topic", "overrides": []})
ACTORS = CounterplanActors(topic_id="sample-topic", cp_text_actors=("fifty states", "congress"))
RULES = AnalyticTextRules(TAXONOMY, OVERRIDES, ACTORS)


def p(index: int, unit: StructuralUnit, text: str, *path: str) -> SectionParagraph:
    return SectionParagraph(element_index=index, unit=unit, text=text, section_path=tuple(path))


def read(*paragraphs: SectionParagraph, in_cards: frozenset[int] = frozenset()) -> SourceTexts:
    return read_analytic_texts(
        SourceParagraphs(paragraphs=paragraphs, in_cards=in_cards), RULES, own_names=(), caselist=SCHOOLS
    )


def cp_texts(found: SourceTexts) -> list[AnalyticTextReading]:
    return [one for one in found.readings if one.kind is CP]


def card(index: int, tag: str, *path: str) -> tuple[SectionParagraph, SectionParagraph]:
    return p(index, TAG, tag, *path), p(index + 1, EVIDENCE, "Sample evidence words.", *path)


def quoted(found: SourceTexts, *paragraphs: SectionParagraph) -> dict[int, str]:
    return read_back_texts(paragraphs, cp_texts(found))


# -- a CP text ending in a colon -----------------------------------------------------------------


def test_a_cp_text_ending_in_a_colon_is_shown_with_the_planks_it_lists() -> None:
    paragraphs = (
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, STEM, STATES),
        p(3, ANALYTIC, CLINICS, STATES),
        p(4, UNDERTAG, PRIZE, STATES),
        *card(5, "Clinics are sample care", STATES),
    )
    found = read(*paragraphs, in_cards=frozenset({5, 6}))
    (stem,) = cp_texts(found)
    assert (stem.element_index, stem.lines) == (2, (3, 4))
    # The whole text is checked on reading again; the opening paragraph is what the text is grouped by.
    assert (stem.digest, stem.opening_digest) == (text_digest(f"{STEM} {CLINICS} {PRIZE}"), text_digest(STEM))
    # t16's planks are still read and placed as they were.
    assert [(one.element_index, one.form) for one in found.readings if one.kind is PLANK] == [
        (3, TextForm.LIST),
        (4, TextForm.LIST),
    ]
    assert quoted(found, *paragraphs) == {2: f"{STEM}\n{CLINICS}\n{PRIZE}"}


def test_a_listed_plank_is_a_line_by_t16s_rules_and_caps() -> None:
    long_plank = "Expand " + " ".join(["sample"] * 60) + " clinics."
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, STEM, STATES),
        # An advantage's alias alone is a label naming the plank after it, not a plank, so not a line.
        p(3, ANALYTIC, "Costs", STATES),
        p(4, ANALYTIC, CLINICS, STATES),
        # Over 60 words is no plank.
        p(5, ANALYTIC, long_plank, STATES),
        p(6, ANALYTIC, PRIZE, STATES),
        p(7, TAG, "Prizes are sample care", STATES),
        # After the first card the list is over.
        p(8, ANALYTIC, "Publish a sample price list.", STATES),
    )
    (stem,) = cp_texts(found)
    assert stem.lines == (4, 6)


def test_a_colon_cp_text_failing_the_actor_guard_is_shown_alone() -> None:
    # A list plank's actor is its CP text's: t16 reads none here, so none is shown.
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, "Text", STATES),
        p(3, ANALYTIC, "The sample panel should:", STATES),
        p(4, ANALYTIC, CLINICS, STATES),
    )
    (stem,) = cp_texts(found)
    assert (stem.element_index, stem.lines) == (3, ())
    assert stem.digest == text_digest("The sample panel should:")


def test_an_inline_label_is_no_part_of_the_whole_text() -> None:
    paragraphs = (
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, "CP Text: " + STEM, STATES),
        p(3, ANALYTIC, CLINICS, STATES),
    )
    found = read(*paragraphs)
    (stem,) = cp_texts(found)
    assert (stem.form, stem.lines) == (TextForm.INLINE, (3,))
    assert quoted(found, *paragraphs) == {2: f"{STEM}\n{CLINICS}"}


# -- a CP text continued in the next paragraph -----------------------------------------------------


def test_a_cp_text_ending_with_no_sentence_end_is_joined_to_the_analytics_continuing_it() -> None:
    paragraphs = (
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, OPEN_STEM, STATES),
        p(3, ANALYTIC, "- Expand sample clinics in rural areas", STATES),
        p(4, ANALYTIC, "- Fund a sample research prize", STATES),
        *card(5, "Clinics are sample care", STATES),
    )
    found = read(*paragraphs, in_cards=frozenset({5, 6}))
    (stem,) = cp_texts(found)
    assert stem.lines == (3, 4)
    # Worded alike with the colon text and its planks: one text, whatever the punctuation.
    assert (stem.digest, stem.opening_digest) == (text_digest(f"{STEM} {CLINICS} {PRIZE}"), text_digest(STEM))
    # A continuation is shown, not read as planks: t16's planks are unchanged.
    assert [one for one in found.readings if one.kind is PLANK] == []
    assert quoted(found, *paragraphs) == {
        2: f"{OPEN_STEM}\n- Expand sample clinics in rural areas\n- Fund a sample research prize"
    }


def test_a_cp_text_ending_in_a_dash_is_continued_too() -> None:
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, "The fifty states should \u2014", STATES),
        p(3, ANALYTIC, "\u2013 expand sample clinics", STATES),
    )
    (stem,) = cp_texts(found)
    assert stem.lines == (3,)


def test_a_continuation_ends_at_the_first_paragraph_that_is_not_an_analytic() -> None:
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, OPEN_STEM, STATES),
        p(3, ANALYTIC, "- Expand sample clinics", STATES),
        p(4, UNDERTAG, "Sample undertag words.", STATES),
        p(5, ANALYTIC, "- Fund a sample prize", STATES),
    )
    (stem,) = cp_texts(found)
    assert stem.lines == (3,)


def test_a_continuation_ends_at_an_analytic_over_60_words() -> None:
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, OPEN_STEM, STATES),
        p(3, ANALYTIC, "- Expand sample clinics", STATES),
        p(4, ANALYTIC, "This is why " + " ".join(["sample"] * 60) + " works", STATES),
        p(5, ANALYTIC, "- Fund a sample prize", STATES),
    )
    (stem,) = cp_texts(found)
    assert stem.lines == (3,)


def test_a_cp_text_with_no_actor_is_not_continued() -> None:
    # As a list plank's actor is its CP text's, a continuation's is too: a labelled text with no actor is
    # shown alone.
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, "Text: The sample panel should", STATES),
        p(3, ANALYTIC, "- expand sample clinics", STATES),
    )
    (stem,) = cp_texts(found)
    assert (stem.form, stem.lines) == (TextForm.INLINE, ())


@pytest.mark.parametrize(
    ("label", "after", "in_cards"),
    [
        ("a heading", (p(3, BLOCK, STATES), p(4, ANALYTIC, "- Expand sample clinics", STATES)), ()),
        ("a card", card(3, "Clinics are sample care", STATES), (3, 4)),
        ("an analytic in a card", (p(3, ANALYTIC, "- Expand sample clinics", STATES),), (3,)),
        ("an undertag", (p(3, UNDERTAG, "- Expand sample clinics", STATES),), ()),
    ],
)
def test_a_cp_text_is_never_joined_across_a_heading_a_card_or_to_an_undertag(
    label: str, after: tuple[SectionParagraph, ...], in_cards: tuple[int, ...]
) -> None:
    found = read(p(1, BLOCK, STATES), p(2, ANALYTIC, OPEN_STEM, STATES), *after, in_cards=frozenset(in_cards))
    stems = [one for one in cp_texts(found) if one.element_index == 2]
    assert [one.lines for one in stems] == [()], label


def test_a_cp_text_ending_in_a_sentence_end_is_not_joined() -> None:
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, "The fifty states should establish a sample single payer system.", STATES),
        p(3, ANALYTIC, "This avoids the sample spending link", STATES),
    )
    (stem,) = cp_texts(found)
    assert stem.lines == ()


def test_a_cp_text_is_never_joined_to_the_next_cp_text() -> None:
    found = read(
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, "Text: " + OPEN_STEM, STATES),
        p(3, ANALYTIC, "Text: Congress should fund sample clinics", STATES),
    )
    assert [(one.element_index, one.lines) for one in cp_texts(found)] == [(2, ()), (3, ())]


# -- what the digest covers ------------------------------------------------------------------------


def test_a_cp_text_with_its_planks_and_one_without_open_alike_and_differ_whole() -> None:
    listed = read(p(1, BLOCK, STATES), p(2, ANALYTIC, STEM, STATES), p(3, ANALYTIC, CLINICS, STATES))
    alone = read(p(1, BLOCK, STATES), p(2, ANALYTIC, STEM, STATES), *card(3, "Sample", STATES))
    (with_planks,) = cp_texts(listed)
    (without,) = cp_texts(alone)
    # One group, by the opening paragraph; two whole texts, by what is checked and shown.
    assert with_planks.opening_digest == without.opening_digest == without.digest == text_digest(STEM)
    assert with_planks.digest != without.digest


def test_a_whole_text_whose_plank_reads_differently_now_is_not_quoted() -> None:
    found = read(p(1, BLOCK, STATES), p(2, ANALYTIC, STEM, STATES), p(3, ANALYTIC, CLINICS, STATES))
    edited = (p(2, ANALYTIC, STEM, STATES), p(3, ANALYTIC, "Expand sample hospitals.", STATES))
    assert quoted(found, *edited) == {}
    # And a line no longer in the file is no whole text either.
    assert quoted(found, p(2, ANALYTIC, STEM, STATES)) == {}


def test_a_whole_text_is_read_again_only_with_every_line_even_one_with_no_words() -> None:
    # A line of no words leaves the digest as it is, so its paragraph's absence is checked on its own.
    paragraphs = (
        p(1, BLOCK, STATES),
        p(2, ANALYTIC, STEM, STATES),
        p(3, ANALYTIC, CLINICS, STATES),
        p(4, ANALYTIC, "\u2013", STATES),
    )
    found = read(*paragraphs)
    (stem,) = cp_texts(found)
    assert stem.lines == (3, 4)
    assert quoted(found, *paragraphs) == {2: f"{STEM}\n{CLINICS}\n\u2013"}
    assert quoted(found, *paragraphs[:3]) == {}


def test_a_whole_text_is_its_parts_one_line_each() -> None:
    assert whole_text("The fifty states\nshould:", ["Expand  sample clinics.", " Fund a prize. "]) == (
        "The fifty states should:\nExpand sample clinics.\nFund a prize."
    )
    # A text with no lines is word for word as it was read.
    assert whole_text("The fifty states  should.", []) == "The fifty states  should."


# -- withholding ---------------------------------------------------------------------------------


def _group(*copies: tuple[str, str, frozenset[str]]) -> TextGroup:
    """A group of copies (source, whole text, that source's teams), keyed by its opening paragraph."""
    return TextGroup(
        teams=frozenset(team for _, _, teams in copies for team in teams),
        texts=tuple((sha * 32, 2, text) for sha, text, _ in copies),
        source_teams={sha * 32: teams for sha, _, teams in copies},
    )


PLAIN = whole_text(STEM, [CLINICS, PRIZE])
NAMED = whole_text(STEM, [CLINICS, "Let Lakeside Academy host a sample pilot."])
OPEN = whole_text(OPEN_STEM, ["- Expand sample clinics in rural areas", "- Fund a sample research prize"])


def test_a_group_shows_the_whole_text_the_most_of_its_teams_read_and_how_many() -> None:
    group = _group(
        ("a1", PLAIN, frozenset({"YY", "JJ"})),
        ("a2", PLAIN, frozenset({"QQ"})),
        # More copies, fewer teams: copies do not choose the text shown, teams do.
        ("a3", OPEN, frozenset({"WW"})),
        ("a4", OPEN, frozenset({"WW"})),
        ("a5", OPEN, frozenset({"WW"})),
        ("a6", STEM, frozenset({"KK"})),
    )
    shown, more, withheld = top_texts("states-cp", CP, {text_digest(STEM): group}, limit=3, caselist=SCHOOLS)
    assert [(row.rank, row.teams, row.text_teams, row.text) for row in shown] == [(1, 5, 3, PLAIN)]
    assert (more, withheld) == (None, 0)


def test_a_tie_in_teams_goes_to_the_first_copy_by_source_and_paragraph() -> None:
    group = _group(("b2", PLAIN, frozenset({"QQ"})), ("b1", OPEN, frozenset({"WW"})))
    shown, _, _ = top_texts("states-cp", CP, {text_digest(STEM): group}, limit=3, caselist=SCHOOLS)
    assert [(row.text_teams, row.text) for row in shown] == [(1, OPEN)]


def test_a_whole_text_any_plank_of_which_names_a_school_is_passed_over_for_the_next() -> None:
    group = _group(
        ("a1", NAMED, frozenset({"YY", "JJ"})),
        ("a2", NAMED, frozenset({"QQ"})),
        ("a3", PLAIN, frozenset({"WW"})),
    )
    shown, more, withheld = top_texts("states-cp", CP, {text_digest(STEM): group}, limit=3, caselist=SCHOOLS)
    # The group keeps its teams and its rank; the text shown is the next whole text.
    assert [(row.rank, row.teams, row.text_teams, row.text) for row in shown] == [(1, 4, 1, PLAIN)]
    assert (more, withheld) == (None, 1)


def test_a_group_every_whole_text_of_which_names_a_school_is_withheld() -> None:
    opening_named = whole_text("Lakeside Academy should:", [CLINICS])
    group = _group(("a1", NAMED, frozenset({"YY"})), ("a2", opening_named, frozenset({"QQ"})))
    shown, more, withheld = top_texts("states-cp", CP, {text_digest(STEM): group}, limit=3, caselist=SCHOOLS)
    assert (shown, more, withheld) == ((), None, 2)


# -- the reading's shape ---------------------------------------------------------------------------


def _reading(**changes: Any) -> AnalyticTextReading:
    fields: dict[str, Any] = {
        "kind": CP,
        "form": TextForm.BY_PLACE,
        "label_element_index": 2,
        "element_index": 2,
        "unit": ANALYTIC,
        "kept": False,
        "digest": text_digest(STEM),
        "placement": TextPlacement.PLACED,
        "position_id": "states-cp",
        "role": PositionRole.READS,
    }
    return AnalyticTextReading(**{**fields, **changes})


def test_only_a_cp_text_has_lines_after_it_in_file_order() -> None:
    opening = {"digest": text_digest(f"{STEM} {CLINICS}"), "opening_digest": text_digest(STEM)}
    assert _reading(lines=(3, 5), **opening).lines == (3, 5)
    with pytest.raises(ValidationError):
        _reading(lines=(5, 3), **opening)
    with pytest.raises(ValidationError):
        _reading(lines=(2,), **opening)
    with pytest.raises(ValidationError):
        _reading(kind=AnalyticTextKind.K_ALTERNATIVE, form=TextForm.SENTENCE, lines=(3,))


def test_only_a_cp_text_has_an_opening_digest_and_one_with_lines_must() -> None:
    whole = text_digest(f"{STEM} {CLINICS}")
    assert _reading(lines=(3,), digest=whole, opening_digest=text_digest(STEM)).opening_digest == text_digest(
        STEM
    )
    assert _reading(opening_digest=text_digest(STEM)).opening_digest == text_digest(STEM)
    with pytest.raises(ValidationError):
        _reading(lines=(3,), digest=whole)
    with pytest.raises(ValidationError):
        # With no lines, the text is its opening paragraph.
        _reading(opening_digest=whole)
    with pytest.raises(ValidationError):
        _reading(
            kind=AnalyticTextKind.K_ALTERNATIVE, form=TextForm.SENTENCE, opening_digest=text_digest(STEM)
        )


def test_a_shown_texts_own_teams_are_never_more_than_its_groups() -> None:
    assert (
        QuotedText(position_id="states-cp", kind=CP, rank=1, teams=5, text_teams=3, text=PLAIN).text_teams
        == 3
    )
    with pytest.raises(ValidationError):
        QuotedText(position_id="states-cp", kind=CP, rank=1, teams=2, text_teams=3, text=PLAIN)

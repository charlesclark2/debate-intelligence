"""A CP's planks, found, placed and named (`v1-e32-t16` ac2).

The PM's rulings of 2026-10-25 on the counts:
* A CP text ending in a colon lists its planks in the paragraphs after it, up to the block's first card or
  heading: analytic, undertag or unstyled, not kept, at most 60 words. A list paragraph that is only an
  advantage's alias is a label naming the plank after it, and is counted, not a plank.
* Separate planks, later in the CP text's block, are `should` analytics past the actor guard, or
  paragraphs opening with a plank label (`Plank 2:`, `2.`, `Second,`).
* A list plank passes the guard through its CP text, which must pass it itself; a separate plank on its
  own words or its label.
* A plank names every advantage its own words, its label or a card under it name by an alias, as whole
  phrases; a plan is never named, and a card saying `solves` with other words is counted, never shown.

Every taxonomy, heading and text here is invented, and every expected value is written by hand.
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
    advantage_aliases_in,
    plank_words,
    read_analytic_texts,
    read_back_texts,
    text_digest,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, PositionRole
from debate_core.domain.landscape_texts import (
    AnalyticTextKind,
    AnalyticTextReading,
    TextForm,
    TextPlacement,
)
from debate_core.domain.style_profile import StructuralUnit

BLOCK = StructuralUnit.BLOCK
TAG = StructuralUnit.TAG
EVIDENCE = StructuralUnit.EVIDENCE
ANALYTIC = StructuralUnit.ANALYTIC
UNDERTAG = StructuralUnit.UNDERTAG
OTHER = StructuralUnit.OTHER

CP = AnalyticTextKind.CP_TEXT
PLANK = AnalyticTextKind.CP_PLANK
ADV_CP = "Advantage CP"
SCHOOLS = CaselistNames({"Lakeside Academy": ("LA",)})


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
            _position("costs-advantage", "advantage", "aff", ["costs", "adv costs"]),
            _position("innovation-advantage", "advantage", "aff", ["innovation", "medical innovation"]),
            _position("advantage-cp", "cp", "neg", ["advantage cp"]),
            _position("states-cp", "cp", "neg", ["states cp"]),
        ],
    }
)
OVERRIDES = OverrideRules.model_validate({"topic_id": "sample-topic", "overrides": []})
ACTORS = CounterplanActors(topic_id="sample-topic", cp_text_actors=("fifty states", "congress", "usfg"))
RULES = AnalyticTextRules(TAXONOMY, OVERRIDES, ACTORS)
COSTS = "costs-advantage"
INNOVATION = "innovation-advantage"


def p(index: int, unit: StructuralUnit, text: str, *path: str) -> SectionParagraph:
    return SectionParagraph(element_index=index, unit=unit, text=text, section_path=tuple(path))


def read(*paragraphs: SectionParagraph, in_cards: frozenset[int] = frozenset()) -> SourceTexts:
    return read_analytic_texts(
        SourceParagraphs(paragraphs=paragraphs, in_cards=in_cards), RULES, own_names=(), caselist=SCHOOLS
    )


def planks(found: SourceTexts) -> list[tuple[int, TextForm, int, tuple[str, ...]]]:
    """(paragraph, form, CP text's paragraph, advantages) of each plank."""
    return [
        (one.element_index, one.form, one.stem_element_index or 0, one.solves)
        for one in found.readings
        if one.kind is PLANK
    ]


def card(index: int, tag: str, *path: str) -> tuple[SectionParagraph, SectionParagraph]:
    return p(index, TAG, tag, *path), p(index + 1, EVIDENCE, "Sample evidence words.", *path)


# -- the list -------------------------------------------------------------------------------------


def test_a_list_after_a_cp_text_ending_in_a_colon_is_its_planks_up_to_the_first_card() -> None:
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, ANALYTIC, "Expand sample clinics.", ADV_CP),
        p(4, UNDERTAG, "Fund a sample prize.", ADV_CP),
        p(5, OTHER, "Ban sample surprise bills.", ADV_CP),
        *card(6, "Clinics are sample care", ADV_CP),
        p(8, ANALYTIC, "Publish a sample price list.", ADV_CP),
        in_cards=frozenset({6, 7}),
    )
    assert planks(found) == [
        (3, TextForm.LIST, 2, ()),
        (4, TextForm.LIST, 2, ()),
        (5, TextForm.LIST, 2, ()),
    ]
    one = next(one for one in found.readings if one.kind is PLANK)
    assert (one.placement, one.position_id, one.role) == (
        TextPlacement.PLACED,
        "advantage-cp",
        PositionRole.READS,
    )
    assert (one.unit, one.kept, one.digest) == (ANALYTIC, False, text_digest("Expand sample clinics."))
    # The CP text itself is still t11's, read by its place.
    assert [(one.kind, one.form, one.element_index) for one in found.readings if one.kind is CP] == [
        (CP, TextForm.BY_PLACE, 2)
    ]


def test_the_list_ends_at_a_heading() -> None:
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, ANALYTIC, "Expand sample clinics.", ADV_CP),
        p(4, BLOCK, "Solvency", ADV_CP),
        p(5, ANALYTIC, "Fund a sample prize.", ADV_CP, "Solvency"),
    )
    assert planks(found) == [(3, TextForm.LIST, 2, ())]


def test_a_list_paragraph_over_60_words_is_no_plank_and_the_list_goes_on() -> None:
    sixty = " ".join(["sample"] * 59) + " clinics."
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, ANALYTIC, sixty, ADV_CP),
        p(4, ANALYTIC, "sample " + sixty, ADV_CP),
        p(5, ANALYTIC, "Fund a sample prize.", ADV_CP),
    )
    assert [one[0] for one in planks(found)] == [3, 5]


def test_a_paragraph_in_a_card_ends_the_list() -> None:
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, ANALYTIC, "Expand sample clinics.", ADV_CP),
        p(4, ANALYTIC, "A sample analytic the store keeps in a card.", ADV_CP),
        p(5, ANALYTIC, "Fund a sample prize.", ADV_CP),
        in_cards=frozenset({4}),
    )
    assert [one[0] for one in planks(found)] == [3]


def test_a_cp_text_without_a_colon_lists_no_planks() -> None:
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should expand sample clinics.", ADV_CP),
        p(3, ANALYTIC, "Fund a sample prize.", ADV_CP),
    )
    assert planks(found) == []


def test_a_list_paragraph_that_is_only_an_advantages_alias_names_the_plank_after_it() -> None:
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, OTHER, "Costs", ADV_CP),
        p(4, ANALYTIC, "Ban sample surprise bills.", ADV_CP),
        p(5, OTHER, "2. Medical Innovation:", ADV_CP),
        p(6, ANALYTIC, "Fund a sample prize.", ADV_CP),
        p(7, ANALYTIC, "Publish a sample price list.", ADV_CP),
    )
    assert planks(found) == [
        (4, TextForm.LIST, 2, (COSTS,)),
        (6, TextForm.LIST, 2, (INNOVATION,)),
        (7, TextForm.LIST, 2, ()),
    ]
    assert found.plank_labels == 2
    # The label is the reading's label paragraph; the plank is its own paragraph.
    assert [(one.label_element_index, one.element_index) for one in found.readings if one.kind is PLANK] == [
        (3, 4),
        (5, 6),
        (7, 7),
    ]


def test_a_list_plank_passes_the_actor_guard_through_its_cp_text() -> None:
    # A labelled CP text needs no actor to be quoted (t11), but its list does: no actor, no planks.
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "Text: The sample panel should:", ADV_CP),
        p(3, ANALYTIC, "Expand sample clinics.", ADV_CP),
        p(4, ANALYTIC, "Fund a sample prize.", ADV_CP),
    )
    assert [(one.kind, one.form) for one in found.readings] == [(CP, TextForm.INLINE)]
    assert (found.planks_refused_by_guard, found.plank_labels) == (2, 0)
    # With an actor before its `should`, the same list is two planks.
    passing = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "Text: The USFG should:", ADV_CP),
        p(3, ANALYTIC, "Expand sample clinics.", ADV_CP),
        p(4, ANALYTIC, "Fund a sample prize.", ADV_CP),
    )
    assert [one[0] for one in planks(passing)] == [3, 4]
    assert passing.planks_refused_by_guard == 0


# -- separate planks --------------------------------------------------------------------------


def test_separate_planks_are_should_analytics_past_the_guard_or_labelled_paragraphs() -> None:
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The fifty states should establish a sample exchange.", ADV_CP),
        *card(3, "Solves sample debt", ADV_CP),
        p(5, ANALYTIC, "Congress should fund sample clinics.", ADV_CP),
        *card(6, "Clinics solve costs for sample patients", ADV_CP),
        p(8, ANALYTIC, "Our interpretation is that we should get sample fiat.", ADV_CP),
        p(9, ANALYTIC, "Plank 3: Ban sample surprise bills.", ADV_CP),
        *card(10, "Solves sample debt", ADV_CP),
        p(12, OTHER, "Second, fund a sample prize.", ADV_CP),
        *card(13, "Innovation", ADV_CP),
        in_cards=frozenset({3, 4, 6, 7, 10, 11, 13, 14}),
    )
    # The card under the CP text is no plank's; paragraph 8 has no actor and no label.
    assert planks(found) == [
        (5, TextForm.SEPARATE, 2, (COSTS,)),
        (9, TextForm.SEPARATE, 2, ()),
        (12, TextForm.SEPARATE, 2, (INNOVATION,)),
    ]
    other = {one.element_index: one.solves_other_words for one in found.readings if one.kind is PLANK}
    assert other == {5: 0, 9: 1, 12: 0}


def test_a_plank_label_is_no_part_of_its_words() -> None:
    assert plank_words("Plank 3: Ban sample surprise bills.") == "Ban sample surprise bills."
    assert plank_words("2. Ban sample surprise bills.") == "Ban sample surprise bills."
    assert plank_words("Second, ban sample surprise bills.") == "ban sample surprise bills."
    assert plank_words("Ban sample surprise bills.") == "Ban sample surprise bills."
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The fifty states should establish a sample exchange.", ADV_CP),
        p(3, ANALYTIC, "Plank 2: Ban sample surprise bills.", ADV_CP),
    )
    plank = next(one for one in found.readings if one.kind is PLANK)
    assert plank.digest == text_digest("Ban sample surprise bills.")
    paragraphs = (p(3, ANALYTIC, "Plank 2: Ban sample surprise bills.", ADV_CP),)
    assert read_back_texts(paragraphs, [plank]) == {3: "Ban sample surprise bills."}


def test_planks_stop_at_the_next_cp_text_of_the_block() -> None:
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, ANALYTIC, "Expand sample clinics.", ADV_CP),
        p(4, ANALYTIC, "Text: The fifty states should:", ADV_CP),
        p(5, ANALYTIC, "Fund a sample prize.", ADV_CP),
    )
    assert planks(found) == [(3, TextForm.LIST, 2, ()), (5, TextForm.LIST, 4, ())]


def test_planks_are_placed_with_their_cp_text() -> None:
    found = read(
        p(1, BLOCK, "Sample file"),
        p(2, ANALYTIC, "Text: The USFG should:", "Sample file"),
        p(3, ANALYTIC, "Expand sample clinics.", "Sample file"),
    )
    plank = next(one for one in found.readings if one.kind is PLANK)
    assert (plank.placement, plank.position_id, plank.stem_element_index) == (
        TextPlacement.HEADINGS_PLACE_NOTHING,
        None,
        2,
    )


# -- naming -------------------------------------------------------------------------------------


def test_a_planks_own_words_name_every_advantage_alias_as_whole_phrases() -> None:
    aliases = RULES.advantage_aliases
    assert advantage_aliases_in("cut sample costs and fund medical innovation", aliases) == (
        "costs",
        "innovation",
        "medical innovation",
    )
    # Never part of a word, and never a plan.
    assert advantage_aliases_in("cap sample costsharing for innovations", aliases) == ()
    assert advantage_aliases_in("pass a sample single payer system", aliases) == ()
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, ANALYTIC, "Cut sample costs and fund medical innovation.", ADV_CP),
        p(4, ANALYTIC, "Cap sample costsharing for innovations.", ADV_CP),
        p(5, ANALYTIC, "Pass a sample single payer system.", ADV_CP),
    )
    assert [one[3] for one in planks(found)] == [(COSTS, INNOVATION), (), ()]


def test_only_an_active_advantage_is_named() -> None:
    assert RULES.advantage_aliases == {
        "costs": COSTS,
        "adv costs": COSTS,
        "innovation": INNOVATION,
        "medical innovation": INNOVATION,
    }


def test_a_plank_naming_a_school_is_read_like_any_other() -> None:
    # The report withholds it; the reader keeps only its digest.
    found = read(
        p(1, BLOCK, ADV_CP),
        p(2, ANALYTIC, "The USFG should:", ADV_CP),
        p(3, ANALYTIC, "Lakeside Academy should host a sample pilot.", ADV_CP),
    )
    assert [one[0] for one in planks(found)] == [3]


# -- the reading itself ----------------------------------------------------------------------------


def _reading(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": PLANK,
        "form": TextForm.LIST,
        "label_element_index": 3,
        "element_index": 3,
        "unit": ANALYTIC,
        "kept": False,
        "digest": "a" * 64,
        "placement": TextPlacement.NO_HEADING,
        "stem_element_index": 2,
    }
    return {**base, **changes}


@pytest.mark.parametrize(
    "changes",
    [
        {"stem_element_index": None},
        {"form": TextForm.BY_PLACE},
        {"kind": CP, "form": TextForm.LIST},
        {"kind": CP, "form": TextForm.BY_PLACE, "solves": (COSTS,)},
        {"kind": CP, "form": TextForm.BY_PLACE, "solves_other_words": 1},
        {"solves": (INNOVATION, COSTS)},
        {"solves": (COSTS, COSTS)},
    ],
)
def test_only_a_plank_names_its_cp_text_and_what_it_solves(changes: dict[str, Any]) -> None:
    AnalyticTextReading.model_validate(_reading())
    if changes.get("kind") is CP:
        changes.setdefault("stem_element_index", None)
    with pytest.raises(ValidationError):
        AnalyticTextReading.model_validate(_reading(**changes))

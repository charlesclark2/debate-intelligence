"""A plan text under a transition label t09's labels miss (`v1-e32-t24-unlabelled-plan-affs` ac2).

The PM's rulings of 2026-10-26: in a file t09 reads as having no plan text, a plan text under `Thus the
plan`, `Thus plan`, inline `Thus the plan:` or a bare `Thus` is read with t09's shape (`should` with a
federal actor before it) and t09's vocabulary, the resolutional rule included. `Therefore` and
unlabelled analytics are left out. As t09's are, only what is derived is kept, never the words.

Every taxonomy, label, word and paragraph here is invented.
"""

from __future__ import annotations

import pytest

from debate_core.arguments.landscape.plan_text import (
    PLAN_TEXT_LABELS,
    TRANSITION_PLAN_LABELS,
    DocumentPlanText,
    PlanTextParagraph,
    PlanTextVerdict,
    PlanTextVocabulary,
    document_plan_text,
    read_plan_texts,
    read_transition_plan_texts,
)
from debate_core.domain.style_profile import StructuralUnit

from .test_plan_text import (
    ANALYTIC,
    BLOCK,
    FIFTY_STATES,
    NATIONAL,
    RESOLUTIONAL,
    SHAPED_NOTHING,
    SHAPED_SAMPLE,
    TAG,
    WORDS,
    digest,
    paragraphs,
)

EVIDENCE = StructuralUnit.EVIDENCE
CITE = StructuralUnit.CITE
SHAPED_OTHER = "The United States federal government should establish an other plan."


def read(
    *specs: tuple[StructuralUnit, str],
    in_cards: frozenset[int] = frozenset(),
    vocabulary: PlanTextVocabulary = WORDS,
) -> tuple[PlanTextParagraph, ...]:
    return read_transition_plan_texts(paragraphs(*specs), in_cards, vocabulary)


def verdict(*specs: tuple[StructuralUnit, str], vocabulary: PlanTextVocabulary = WORDS) -> DocumentPlanText:
    return document_plan_text(read(*specs, vocabulary=vocabulary), vocabulary)


def test_the_labels_are_thus_the_plan_thus_plan_and_a_bare_thus() -> None:
    assert frozenset({"thus the plan", "thus plan", "thus"}) == TRANSITION_PLAN_LABELS
    assert not TRANSITION_PLAN_LABELS & PLAN_TEXT_LABELS


def test_the_paragraph_under_thus_the_plan_is_a_plan_text_named_by_t09s_vocabulary() -> None:
    found = read((BLOCK, "Advantage One"), (ANALYTIC, "Thus the plan:"), (ANALYTIC, SHAPED_SAMPLE))
    assert found == (
        PlanTextParagraph(
            label_element_index=1,
            element_index=2,
            unit=ANALYTIC,
            kept=False,
            shaped=True,
            digest=digest("the united states federal government should establish a sample plan"),
            named=("sample-plan-aff",),
        ),
    )


@pytest.mark.parametrize(
    "label", ["Thus the plan", "Thus, the plan:", "THUS PLAN", "Thus plan", "Thus", "Thus:"]
)
def test_each_transition_label_form_is_read(label: str) -> None:
    assert [one.named for one in read((ANALYTIC, label), (ANALYTIC, SHAPED_SAMPLE))] == [("sample-plan-aff",)]


@pytest.mark.parametrize(
    "label", ["Therefore", "Therefore:", "Therefore the plan", "Hence", "So", "Thus solvency"]
)
def test_therefore_and_other_transitions_are_left_out(label: str) -> None:
    assert read((ANALYTIC, label), (ANALYTIC, SHAPED_SAMPLE)) == ()


def test_inline_thus_the_plan_is_its_own_plan_text() -> None:
    (found,) = read(
        (ANALYTIC, "Thus, the plan: The United States federal government should establish a sample plan.")
    )
    assert (found.label_element_index, found.element_index, found.named) == (0, 0, ("sample-plan-aff",))


@pytest.mark.parametrize(
    "text",
    [
        "Thus: The United States federal government should establish a sample plan.",
        "Therefore, the plan: The United States federal government should establish a sample plan.",
        "Thus the plan solves costs.",
    ],
)
def test_no_other_inline_form_is_read(text: str) -> None:
    assert read((ANALYTIC, text)) == ()


@pytest.mark.parametrize(
    "text",
    [
        "Congress should establish a sample plan.",
        FIFTY_STATES,
        "A sample plan solves costs and the advantages.",
    ],
)
def test_the_plan_text_must_have_t09s_shape(text: str) -> None:
    assert read((ANALYTIC, "Thus the plan"), (ANALYTIC, text)) == ()
    assert read((ANALYTIC, "Thus"), (ANALYTIC, text)) == ()


@pytest.mark.parametrize("unit", [EVIDENCE, CITE])
def test_card_text_is_no_plan_text(unit: StructuralUnit) -> None:
    assert read((ANALYTIC, "Thus"), (unit, SHAPED_SAMPLE)) == ()


@pytest.mark.parametrize("unit", [ANALYTIC, TAG, BLOCK])
def test_any_other_unit_under_the_label_is_read(unit: StructuralUnit) -> None:
    assert [one.unit for one in read((ANALYTIC, "Thus the plan"), (unit, SHAPED_SAMPLE))] == [unit]


def test_a_label_over_another_label_reads_the_paragraph_under_the_second() -> None:
    found = read((ANALYTIC, "Thus"), (ANALYTIC, "Thus the plan"), (ANALYTIC, SHAPED_SAMPLE))
    assert [(one.label_element_index, one.element_index) for one in found] == [(1, 2)]


def test_a_transition_over_t09s_own_label_is_left_to_t09() -> None:
    specs = ((ANALYTIC, "Thus"), (BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE))
    assert read(*specs) == ()
    assert [one.label_element_index for one in read_plan_texts(paragraphs(*specs), frozenset(), WORDS)] == [1]


def test_a_transition_over_t09s_inline_label_is_left_to_t09() -> None:
    assert read((ANALYTIC, "Thus"), (ANALYTIC, "Plan: The USFG should adopt a sample plan.")) == ()


def test_kept_says_whether_the_plan_text_is_inside_a_stored_card() -> None:
    specs = ((ANALYTIC, "Thus the plan"), (TAG, SHAPED_SAMPLE))
    assert [one.kept for one in read(*specs, in_cards=frozenset({1}))] == [True]
    assert [one.kept for one in read(*specs, in_cards=frozenset({0}))] == [False]


def test_a_plan_text_naming_no_aff_is_unnamed() -> None:
    assert verdict((ANALYTIC, "Thus"), (ANALYTIC, SHAPED_NOTHING)) == DocumentPlanText(
        PlanTextVerdict.UNNAMED
    )


def test_two_plan_texts_naming_two_affs_conflict() -> None:
    found = verdict(
        (ANALYTIC, "Thus the plan"), (ANALYTIC, SHAPED_SAMPLE), (ANALYTIC, "Thus"), (ANALYTIC, SHAPED_OTHER)
    )
    assert found == DocumentPlanText(PlanTextVerdict.CONFLICTING)


def test_one_aff_named_twice_names_it() -> None:
    found = verdict(
        (ANALYTIC, "Thus the plan"),
        (ANALYTIC, SHAPED_SAMPLE),
        (ANALYTIC, "Thus plan"),
        (ANALYTIC, SHAPED_SAMPLE),
    )
    assert found == DocumentPlanText(PlanTextVerdict.NAMES, "sample-plan-aff")


def test_the_resolutional_rule_names_the_resolutional_aff() -> None:
    vocabulary = PlanTextVocabulary(NATIONAL, RESOLUTIONAL)
    found = verdict(
        (ANALYTIC, "Thus the plan"),
        (ANALYTIC, SHAPED_NOTHING),
        vocabulary=vocabulary,
    )
    assert found == DocumentPlanText(PlanTextVerdict.NAMES, RESOLUTIONAL.position_id)


def test_a_file_with_no_transition_label_has_none() -> None:
    assert verdict((BLOCK, "Advantage One"), (ANALYTIC, SHAPED_SAMPLE)) == DocumentPlanText(
        PlanTextVerdict.NONE
    )


def test_t09s_plan_texts_do_not_change() -> None:
    specs = ((ANALYTIC, "Thus the plan"), (ANALYTIC, SHAPED_SAMPLE))
    assert read_plan_texts(paragraphs(*specs), frozenset(), WORDS) == ()

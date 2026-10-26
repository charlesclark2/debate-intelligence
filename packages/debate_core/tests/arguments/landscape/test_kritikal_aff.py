"""A kritikal affirmative's markers and the K families its headings name (`v1-e32-t17`).

The PM's rulings of 2026-10-25: the markers are t11's role-of-the-ballot labels; `Advocacy`, `Advocacy
statement`, `Our advocacy (statement) is` and inline `Advocacy:`; `The 1AC is`; `Method` alone, `Our
method is` and inline `Method:`; never `Methods`. The families are a count of words in headings, never a
placement, and nothing is read from a tag. Every paragraph here is invented wording, not a team's.
"""

from __future__ import annotations

from dataclasses import fields

import pytest
from pydantic import ValidationError

from debate_core.arguments.landscape.kritikal_aff import (
    KritikalAffConfig,
    KritikalFamily,
    KritikalMarker,
    KritikalMarkerKind,
    heading_families,
    kritikal_rules,
    read_kritikal_markers,
)
from debate_core.arguments.landscape.plan_text import Paragraph
from debate_core.domain.landscape_texts import TextForm
from debate_core.domain.style_profile import StructuralUnit

BLOCK = StructuralUnit.BLOCK
HAT = StructuralUnit.HAT
POCKET = StructuralUnit.POCKET
TAG = StructuralUnit.TAG
ANALYTIC = StructuralUnit.ANALYTIC
EVIDENCE = StructuralUnit.EVIDENCE

CONFIG = KritikalAffConfig(
    topic_id="sample-topic",
    position_id="sample-kritikal-aff",
    families=(
        KritikalFamily(id="cap", label="Capitalism", phrases=("cap", "capitalism")),
        KritikalFamily(
            id="racial-capitalism", label="Racial capitalism", phrases=("racial cap", "racial capitalism")
        ),
        KritikalFamily(id="colonialism", label="Colonialism", phrases=("colonialism",)),
        KritikalFamily(
            id="settler-colonialism", label="Settler colonialism", phrases=("settler colonialism", "set col")
        ),
        KritikalFamily(
            id="afropessimism", label="Afropessimism", phrases=("afropessimism", "afro pessimism")
        ),
    ),
)


def source(*specs: tuple[StructuralUnit, str]) -> tuple[Paragraph, ...]:
    return tuple(
        Paragraph(element_index=index, unit=unit, text=text) for index, (unit, text) in enumerate(specs)
    )


def kinds(*specs: tuple[StructuralUnit, str]) -> list[tuple[KritikalMarkerKind, TextForm, int]]:
    return [
        (one.kind, one.form, one.element_index)
        for one in read_kritikal_markers(source(*specs), CONFIG).markers
    ]


# -- role of the ballot: t11's own rule ------------------------------------------------------------


def test_a_role_of_the_ballot_sentence_is_a_marker() -> None:
    found = kinds(
        (BLOCK, "Framing"), (TAG, "The role of the ballot is to vote for the team that best resists")
    )
    assert found == [(KritikalMarkerKind.ROLE_OF_THE_BALLOT, TextForm.SENTENCE, 1)]


def test_a_role_of_the_ballot_label_counts_over_a_text_and_not_over_a_heading() -> None:
    assert kinds((BLOCK, "Role of the Ballot"), (ANALYTIC, "Vote for the better pedagogy")) == [
        (KritikalMarkerKind.ROLE_OF_THE_BALLOT, TextForm.LABEL, 0)
    ]
    assert kinds((BLOCK, "ROB"), (BLOCK, "Contention one")) == []


def test_an_inline_role_of_the_ballot_counts_in_an_analytic_and_never_in_a_heading() -> None:
    assert kinds((ANALYTIC, "ROB: vote for the debater who best resists the frame")) == [
        (KritikalMarkerKind.ROLE_OF_THE_BALLOT, TextForm.INLINE, 0)
    ]
    assert kinds((BLOCK, "ROB: vote for the debater who best resists the frame"), (TAG, "A tag")) == []


# -- advocacy statements -----------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["Advocacy", "Advocacy Statement", "Advocacy:", "ADVOCACY STATEMENT"])
def test_an_advocacy_label_over_a_text_is_a_marker(label: str) -> None:
    assert kinds((BLOCK, label), (ANALYTIC, "We affirm a politics of refusal")) == [
        (KritikalMarkerKind.ADVOCACY, TextForm.LABEL, 0)
    ]


def test_an_advocacy_label_over_a_heading_or_at_the_end_is_not_a_marker() -> None:
    assert kinds((BLOCK, "Advocacy"), (BLOCK, "Contention one")) == []
    assert kinds((TAG, "A tag"), (BLOCK, "Advocacy")) == []


@pytest.mark.parametrize(
    "text", ["Our advocacy is a refusal of the frame", "Our advocacy statement is that we affirm refusal"]
)
def test_an_our_advocacy_is_sentence_is_a_marker(text: str) -> None:
    assert kinds((ANALYTIC, text)) == [(KritikalMarkerKind.ADVOCACY, TextForm.SENTENCE, 0)]


def test_an_inline_advocacy_label_counts_in_an_analytic_and_never_in_a_heading() -> None:
    long_text = "Advocacy: we affirm a refusal of the frame that the resolution gives us today"
    assert kinds((ANALYTIC, long_text)) == [(KritikalMarkerKind.ADVOCACY, TextForm.INLINE, 0)]
    assert kinds((BLOCK, long_text), (TAG, "A tag")) == []


@pytest.mark.parametrize(
    "label",
    ["Our advocacy", "Advocacy good", "Interp an unconditional advocacy", "Their advocacy is bad for debate"],
)
def test_other_wordings_with_advocacy_are_not_markers(label: str) -> None:
    assert kinds((BLOCK, label), (ANALYTIC, "Some analytic words")) == []


# -- the 1AC -----------------------------------------------------------------------------------------


def test_a_the_1ac_is_sentence_is_a_marker_and_other_1ac_words_are_not() -> None:
    assert kinds((ANALYTIC, "The 1AC is an act of refusal")) == [
        (KritikalMarkerKind.THE_1AC, TextForm.SENTENCE, 0)
    ]
    assert kinds((ANALYTIC, "This 1AC was written for a single payer plan")) == []
    assert kinds((BLOCK, "1AC"), (TAG, "A tag")) == []


# -- method --------------------------------------------------------------------------------------------


def test_a_method_label_over_a_text_is_a_marker() -> None:
    assert kinds((BLOCK, "Method"), (TAG, "Our method is refusal")) == [
        (KritikalMarkerKind.METHOD, TextForm.LABEL, 0),
        (KritikalMarkerKind.METHOD, TextForm.SENTENCE, 1),
    ]


def test_an_our_method_is_sentence_and_an_inline_method_label_are_markers() -> None:
    assert kinds((ANALYTIC, "Our method is a refusal of the frame")) == [
        (KritikalMarkerKind.METHOD, TextForm.SENTENCE, 0)
    ]
    assert kinds((ANALYTIC, "Method: we read the resolution against itself to refuse its frame today")) == [
        (KritikalMarkerKind.METHOD, TextForm.INLINE, 0)
    ]


@pytest.mark.parametrize("label", ["Methods", "Methodology", "Method mutual aid", "Study methods"])
def test_methods_and_other_method_words_are_not_markers(label: str) -> None:
    assert kinds((BLOCK, label), (ANALYTIC, "The study surveyed four states")) == []


# -- what is never read ----------------------------------------------------------------------------


def test_evidence_is_never_read_for_a_marker() -> None:
    assert kinds((TAG, "A tag"), (EVIDENCE, "The role of the ballot is to vote for the better scholar")) == []
    assert kinds((EVIDENCE, "Our advocacy is the refusal"), (EVIDENCE, "Our method is refusal")) == []


def test_a_paragraph_of_more_than_eight_words_is_not_a_label() -> None:
    assert kinds((BLOCK, "Advocacy and what it means for the frame we read"), (ANALYTIC, "Words")) == []


def test_without_a_config_the_topic_reads_no_k_aff() -> None:
    paragraphs = source((BLOCK, "Advocacy"), (ANALYTIC, "We affirm refusal"), (BLOCK, "Cap K"))
    assert read_kritikal_markers(paragraphs, None).markers == ()
    assert read_kritikal_markers(paragraphs, None).heading_families == ()


def test_a_marker_keeps_no_words() -> None:
    assert [one.name for one in fields(KritikalMarker)] == ["kind", "form", "element_index", "unit"]


def test_markers_come_in_file_order_one_per_paragraph_kind() -> None:
    found = kinds(
        (BLOCK, "Advocacy Statement"),
        (ANALYTIC, "Our advocacy is refusal"),
        (BLOCK, "Framing"),
        (TAG, "The role of the ballot is to vote for refusal"),
    )
    assert found == [
        (KritikalMarkerKind.ADVOCACY, TextForm.LABEL, 0),
        (KritikalMarkerKind.ADVOCACY, TextForm.SENTENCE, 1),
        (KritikalMarkerKind.ROLE_OF_THE_BALLOT, TextForm.SENTENCE, 3),
    ]


# -- the K families in headings --------------------------------------------------------------------


def test_a_longer_phrase_is_matched_first_so_racial_cap_is_not_also_cap() -> None:
    assert heading_families("contention racial cap", CONFIG.families) == ("racial-capitalism",)
    assert heading_families("settler colonialism", CONFIG.families) == ("settler-colonialism",)
    assert heading_families("cap and settler colonialism", CONFIG.families) == ("cap", "settler-colonialism")


def test_a_family_phrase_is_matched_whole() -> None:
    assert heading_families("capital flight", CONFIG.families) == ()
    assert heading_families("set collection", CONFIG.families) == ()
    assert heading_families("the cap", CONFIG.families) == ("cap",)


def test_families_come_from_pocket_hat_and_block_headings_only_never_a_tag() -> None:
    reading = read_kritikal_markers(
        source(
            (POCKET, "1AC - Afro-pessimism"),
            (HAT, "Contention 1: Racial Capitalism"),
            (BLOCK, "Set Col"),
            (TAG, "Capitalism causes colonialism"),
            (ANALYTIC, "Capitalism is the root cause"),
        ),
        CONFIG,
    )
    assert reading.heading_families == ("afropessimism", "racial-capitalism", "settler-colonialism")


# -- the config and the digest ---------------------------------------------------------------------


def test_a_family_listed_twice_or_a_phrase_in_two_families_is_refused() -> None:
    with pytest.raises(ValidationError, match="listed twice"):
        KritikalAffConfig(
            topic_id="t",
            position_id="k-aff",
            families=(
                KritikalFamily(id="cap", label="Cap", phrases=("cap",)),
                KritikalFamily(id="cap", label="Cap", phrases=("capitalism",)),
            ),
        )
    with pytest.raises(ValidationError, match="names two families"):
        KritikalAffConfig(
            topic_id="t",
            position_id="k-aff",
            families=(
                KritikalFamily(id="cap", label="Cap", phrases=("cap",)),
                KritikalFamily(id="racial-cap", label="Racial cap", phrases=("cap",)),
            ),
        )


def test_the_rules_change_with_the_config_and_are_empty_without_one() -> None:
    other = CONFIG.model_copy(update={"families": CONFIG.families[:1]})
    assert kritikal_rules(CONFIG) != kritikal_rules(other)
    assert kritikal_rules(CONFIG) != kritikal_rules(CONFIG.model_copy(update={"position_id": "other-aff"}))
    assert kritikal_rules(None) == []

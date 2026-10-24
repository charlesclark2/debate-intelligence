"""Finding a plan text and reading the aff it names (`v1-e32-t09-policy-plan-texts` ac4).

The PM's rulings of 2026-10-24: the plan text is the paragraph directly under a plan-text label, it
identifies a round when it names an aff's alias or tag keyword (`medicare for all` and `m4a` naming
single payer until the coach names a child), a paragraph that only looks like a plan text identifies
nothing, and only what is derived from a plan text is kept, never its words.

Every taxonomy, label and paragraph here is invented. `single-payer-aff` is the one real id, because
the interim words are tied to it.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

import pytest

from debate_core.arguments.landscape.plan_text import (
    PLAN_TEXT_LABELS,
    DocumentPlanText,
    Paragraph,
    PlanTextParagraph,
    PlanTextVerdict,
    PlanTextVocabulary,
    document_plan_text,
    paragraphs_of,
    read_plan_texts,
)
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.style_profile import StructuralUnit

BLOCK = StructuralUnit.BLOCK
ANALYTIC = StructuralUnit.ANALYTIC
TAG = StructuralUnit.TAG
SHAPED_SAMPLE = "The United States federal government should establish a sample plan."
SHAPED_NOTHING = "The United States federal government should establish a national program."


def position(identifier: str, kind: str = "aff", **fields: Any) -> dict[str, Any]:
    side = "neg" if kind in ("da", "cp") else "aff"
    return {
        "id": identifier,
        "label": identifier.replace("-", " ").capitalize(),
        "kind": kind,
        "side": side,
        **fields,
    }


def taxonomy(*positions: dict[str, Any]) -> Taxonomy:
    return Taxonomy.model_validate(
        {
            "topic_id": "sample-topic",
            "taxonomy_version": "1.0.0",
            "event": "POLICY",
            "positions": list(positions),
        }
    )


SAMPLE = taxonomy(
    position("sample-plan-aff", aliases=["sample plan", "sample plan aff"]),
    position("route-plan-aff", parent="sample-plan-aff", tag_keywords=["voucher route"]),
    position("other-plan-aff", aliases=["other plan"]),
    position("single-payer-aff", aliases=["single payer"]),
    position("costs-advantage", kind="advantage", aliases=["adv costs", "costs"]),
    position("spending-da", kind="da", aliases=["spending da", "national"]),
    position("old-plan-aff", aliases=["old plan"], deprecated=True, merged_into="other-plan-aff"),
    position("gone-plan-aff", aliases=["gone plan"], deprecated=True),
)
WORDS = PlanTextVocabulary(SAMPLE)


def paragraphs(*specs: tuple[StructuralUnit, str]) -> tuple[Paragraph, ...]:
    return tuple(
        Paragraph(element_index=index, unit=unit, text=text) for index, (unit, text) in enumerate(specs)
    )


def read(
    *specs: tuple[StructuralUnit, str], in_cards: frozenset[int] = frozenset()
) -> tuple[PlanTextParagraph, ...]:
    return read_plan_texts(paragraphs(*specs), in_cards, WORDS)


def verdict(*specs: tuple[StructuralUnit, str], vocabulary: PlanTextVocabulary = WORDS) -> DocumentPlanText:
    return document_plan_text(read_plan_texts(paragraphs(*specs), frozenset(), vocabulary), vocabulary)


def digest(words: str) -> str:
    return hashlib.sha256(words.encode()).hexdigest()


# ------------------------------------------------------------------------------------------------
# Finding it
# ------------------------------------------------------------------------------------------------


def test_the_paragraph_under_a_plan_label_is_the_plan_text() -> None:
    found = read((BLOCK, "Advantage One"), (BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE), (TAG, "Plan solves"))
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


@pytest.mark.parametrize("label", ["Plan", "Plan Text", "PT", "The Plan", "1AC - Plan", "Plan:", "PLAN TEXT"])
def test_each_label_form_is_a_label(label: str) -> None:
    assert [one.label_element_index for one in read((BLOCK, label), (ANALYTIC, SHAPED_SAMPLE))] == [0]


@pytest.mark.parametrize("heading", ["Plan solves costs", "Planning", "Explain the plan", "Solvency"])
def test_a_heading_that_only_holds_the_word_is_no_label(heading: str) -> None:
    assert read((BLOCK, heading), (ANALYTIC, SHAPED_SAMPLE)) == ()


def test_a_label_holding_its_text_inline_is_its_own_plan_text() -> None:
    (found,) = read((ANALYTIC, "Plan: The United States federal government should establish a sample plan."))
    assert (found.label_element_index, found.element_index, found.named) == (0, 0, ("sample-plan-aff",))


def test_a_label_over_an_inline_label_reads_the_paragraph_once() -> None:
    found = read((BLOCK, "Plan"), (ANALYTIC, "Plan: The USFG should adopt a sample plan."))
    assert [(one.label_element_index, one.element_index) for one in found] == [(1, 1)]


def test_an_inline_label_must_read_like_a_plan_text() -> None:
    assert read((TAG, "Plan: solves costs and the advantages")) == ()


def test_empty_paragraphs_and_a_second_label_are_passed_over() -> None:
    (found,) = read((BLOCK, "Plan"), (ANALYTIC, "  "), (ANALYTIC, "Plan Text"), (ANALYTIC, SHAPED_SAMPLE))
    assert (found.label_element_index, found.element_index) == (2, 3)


def test_a_label_with_nothing_under_it_has_no_plan_text() -> None:
    assert read((BLOCK, "Advantage One"), (BLOCK, "Plan")) == ()


def test_kept_says_whether_the_plan_text_is_inside_a_stored_card() -> None:
    specs = ((BLOCK, "Plan"), (TAG, SHAPED_SAMPLE))
    assert [one.kept for one in read(*specs, in_cards=frozenset({1, 2}))] == [True]
    assert [one.kept for one in read(*specs, in_cards=frozenset({0, 2}))] == [False]


def test_shaped_needs_should_and_a_federal_actor() -> None:
    shapes = [
        one.shaped
        for text in (
            SHAPED_SAMPLE,
            "The USFG should adopt a sample plan.",
            "A sample plan.",
            "Congress should act.",
        )
        for one in read((BLOCK, "Plan"), (ANALYTIC, text))
    ]
    assert shapes == [True, True, False, False]


def test_every_label_in_a_document_is_read() -> None:
    found = read((BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE), (BLOCK, "PT"), (ANALYTIC, "Other plan."))
    assert [one.named for one in found] == [("sample-plan-aff",), ("other-plan-aff",)]


def test_a_paragraph_that_only_looks_like_a_plan_text_is_not_one() -> None:
    assert read((BLOCK, "Solvency"), (ANALYTIC, SHAPED_SAMPLE)) == ()
    assert verdict((BLOCK, "Solvency"), (ANALYTIC, SHAPED_SAMPLE)) == DocumentPlanText(PlanTextVerdict.NONE)


def test_the_labels_are_fixed_points_of_the_normalizer() -> None:
    from debate_core.arguments.landscape.headings import normalize_heading

    assert all(normalize_heading(label).text == label for label in PLAN_TEXT_LABELS)


# ------------------------------------------------------------------------------------------------
# What it names
# ------------------------------------------------------------------------------------------------


def test_an_alias_names_its_aff_whatever_the_paragraphs_shape() -> None:
    assert verdict((BLOCK, "Plan"), (ANALYTIC, "Sample plan.")) == DocumentPlanText(
        PlanTextVerdict.NAMES, "sample-plan-aff"
    )


def test_words_match_whole() -> None:
    assert WORDS.named("the usfg should fund sample planning") == ()
    assert WORDS.named("the usfg should fund a sample plan") == ("sample-plan-aff",)


def test_a_tag_keyword_names_its_aff_and_a_child_beats_its_parent() -> None:
    assert WORDS.named("a sample plan by the voucher route") == ("route-plan-aff",)


def test_two_unrelated_affs_conflict() -> None:
    assert WORDS.named("a sample plan and the other plan") == ("other-plan-aff", "sample-plan-aff")
    assert verdict((BLOCK, "Plan"), (ANALYTIC, "A sample plan and the other plan.")) == DocumentPlanText(
        PlanTextVerdict.CONFLICTING
    )


def test_two_plan_texts_naming_different_affs_conflict() -> None:
    found = verdict((BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE), (BLOCK, "Plan"), (ANALYTIC, "Other plan."))
    assert found == DocumentPlanText(PlanTextVerdict.CONFLICTING)


def test_a_parent_and_a_child_in_two_plan_texts_name_the_child() -> None:
    found = verdict(
        (BLOCK, "Plan"), (ANALYTIC, "Sample plan."), (BLOCK, "Plan"), (ANALYTIC, "By the voucher route.")
    )
    assert found == DocumentPlanText(PlanTextVerdict.NAMES, "route-plan-aff")


def test_advantages_and_negative_positions_name_nothing() -> None:
    assert WORDS.named("the usfg should cut costs with a national spending da") == ()


def test_a_retired_alias_names_where_it_was_merged_and_nothing_when_retired_alone() -> None:
    assert WORDS.named("the old plan") == ("other-plan-aff",)
    assert WORDS.named("the gone plan") == ()


@pytest.mark.parametrize("words", ["medicare for all", "m4a"])
def test_the_interim_words_name_single_payer(words: str) -> None:
    assert WORDS.named(f"the usfg should adopt {words}") == ("single-payer-aff",)


def test_the_interim_words_go_to_a_child_whose_keywords_hold_them() -> None:
    named_child = PlanTextVocabulary(
        taxonomy(
            position("single-payer-aff", aliases=["single payer"]),
            position("medicare-for-all-aff", parent="single-payer-aff", tag_keywords=["medicare for all"]),
        )
    )
    assert named_child.named("the usfg should adopt medicare for all") == ("medicare-for-all-aff",)
    assert named_child.named("the usfg should adopt m4a") == ("single-payer-aff",)


def test_the_interim_words_name_nothing_without_single_payer() -> None:
    assert (
        PlanTextVocabulary(taxonomy(position("sample-plan-aff", aliases=["sample plan"]))).named(
            "medicare for all"
        )
        == ()
    )


# ------------------------------------------------------------------------------------------------
# A document's verdict
# ------------------------------------------------------------------------------------------------


def test_a_shaped_plan_text_naming_no_aff_is_unnamed() -> None:
    assert verdict((BLOCK, "Plan"), (ANALYTIC, SHAPED_NOTHING)) == DocumentPlanText(PlanTextVerdict.UNNAMED)


def test_an_unshaped_paragraph_naming_no_aff_is_no_plan_text() -> None:
    assert verdict((BLOCK, "Plan"), (BLOCK, "Advantage One")) == DocumentPlanText(PlanTextVerdict.NONE)


def test_a_named_plan_text_outweighs_an_unnamed_one() -> None:
    found = verdict((BLOCK, "Plan"), (ANALYTIC, SHAPED_NOTHING), (BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE))
    assert found == DocumentPlanText(PlanTextVerdict.NAMES, "sample-plan-aff")


def test_a_document_with_no_label_has_no_plan_text() -> None:
    assert verdict((BLOCK, "Advantage One"), (TAG, "Costs rise")) == DocumentPlanText(PlanTextVerdict.NONE)


# ------------------------------------------------------------------------------------------------
# Never the text
# ------------------------------------------------------------------------------------------------


def test_the_digest_is_of_the_words_and_not_their_case_or_punctuation() -> None:
    (one,) = read((BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE))
    (two,) = read(
        (BLOCK, "Plan"), (ANALYTIC, "THE United States -- federal government should establish a sample plan")
    )
    (three,) = read(
        (BLOCK, "Plan"), (ANALYTIC, "The United States federal government should establish one sample plan.")
    )
    assert one.digest == two.digest != three.digest


def test_what_is_kept_holds_no_text() -> None:
    (found,) = read((BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE))
    kept = dataclasses.asdict(found)
    assert set(kept) == {"label_element_index", "element_index", "unit", "kept", "shaped", "digest", "named"}
    assert "sample" not in repr(found).replace("sample-plan-aff", "")
    assert "sample" not in repr(paragraphs((ANALYTIC, SHAPED_SAMPLE)))


def test_the_vocabulary_digest_moves_with_the_words_and_only_with_them() -> None:
    again = PlanTextVocabulary(SAMPLE)
    renamed = PlanTextVocabulary(
        taxonomy(
            position("sample-plan-aff", aliases=["sample plan"]),
            position("other-plan-aff", aliases=["other plan"]),
        )
    )
    assert len(WORDS.digest) == 64
    assert WORDS.digest == again.digest != renamed.digest


# ------------------------------------------------------------------------------------------------
# A parsed document's paragraphs
# ------------------------------------------------------------------------------------------------


def test_paragraphs_of_a_parsed_document_carry_the_parsers_units_and_card_ranges() -> None:
    from datetime import date

    from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
    from debate_core.integrations.docx_parser import DebateDocxParser
    from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

    body = "".join(
        [
            paragraph_xml(run_xml("Plan"), style="Heading3"),
            paragraph_xml(run_xml(SHAPED_SAMPLE), style="Analytic"),
            paragraph_xml(run_xml("Costs rise"), style="Heading4"),
            paragraph_xml(run_xml("Sample 26", character_style="Style13ptBold") + run_xml(" invented cite")),
            paragraph_xml(
                run_xml("An invented body of evidence that goes on for a while.", underline="single")
            ),
        ]
    )
    content = build_docx(body)
    source = SourceDocument(
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspolicy26",
        first_seen_snapshot=date(2026, 10, 20),
        last_seen_snapshot=date(2026, 10, 20),
    )
    document = DebateDocxParser().parse(content, source, source_path="invented.docx")
    assert isinstance(document, ParsedDocument)
    found, in_cards = paragraphs_of(document)
    assert [(one.element_index, one.unit) for one in found[:2]] == [(0, BLOCK), (1, ANALYTIC)]
    assert in_cards == frozenset({2, 3, 4})
    assert document_plan_text(read_plan_texts(found, in_cards, WORDS), WORDS) == DocumentPlanText(
        PlanTextVerdict.NAMES, "sample-plan-aff"
    )

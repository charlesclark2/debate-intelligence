"""Finding a plan text and reading the aff it names (`v1-e32-t09-policy-plan-texts` ac4).

The PM's rulings of 2026-10-24: the plan text is the paragraph directly under a plan-text label, it
identifies a round when it names an aff's alias or tag keyword, a paragraph that only looks like a plan
text identifies nothing, and only what is derived from a plan text is kept, never its words. From the
PM's context for ac3 (2026-10-24): a text whose actor is not the federal government is no plan text (a
fifty-states counterplan), a plan text naming no aff whose words outside the frame are all
resolutional names the topic's resolutional aff, and `medicare for all` and `m4a` name only what the
taxonomy's own words say.

Every taxonomy, label, word and paragraph here is invented.
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
    ResolutionalPlanWords,
    document_plan_text,
    paragraphs_of,
    plan_text_words,
    read_back_plan_texts,
    read_plan_texts,
    sheet_plan_texts,
)
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.style_profile import StructuralUnit

BLOCK = StructuralUnit.BLOCK
ANALYTIC = StructuralUnit.ANALYTIC
TAG = StructuralUnit.TAG
SHAPED_SAMPLE = "The United States federal government should establish a sample plan."
SHAPED_NOTHING = "The United States federal government should establish a national program."
FIFTY_STATES = (
    "The fifty states and all relevant subnational actors should establish a sample plan "
    "in the United States."
)


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
    position("toll-plan-aff", parent="sample-plan-aff", tag_keywords=["toll route"]),
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


@pytest.mark.parametrize(
    "text",
    [
        FIFTY_STATES,
        "The fifty United States should establish a sample plan.",
        "Each state government should establish a sample plan, as the federal government has not.",
    ],
)
def test_a_text_whose_actor_is_not_the_federal_government_is_no_plan_text(text: str) -> None:
    (found,) = read((BLOCK, "Plan"), (ANALYTIC, text))
    assert (found.shaped, found.named) == (False, ())
    assert verdict((BLOCK, "Plan"), (ANALYTIC, text)) == DocumentPlanText(PlanTextVerdict.NONE)
    assert sheet_plan_texts((found,)) == ()


def test_the_federal_actor_may_follow_an_earlier_should() -> None:
    (found,) = read(
        (BLOCK, "Plan"),
        (
            ANALYTIC,
            "Care should be a right, so the United States federal government should establish a sample plan.",
        ),
    )
    assert (found.shaped, found.named) == (True, ("sample-plan-aff",))


def test_a_text_with_no_should_still_names_its_aff() -> None:
    (found,) = read((BLOCK, "Plan"), (ANALYTIC, "Sample plan."))
    assert (found.shaped, found.named) == (False, ("sample-plan-aff",))


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
def test_no_interim_words_name_an_aff_the_taxonomy_does_not_give_them(words: str) -> None:
    assert WORDS.named(f"the usfg should adopt {words}") == ()


def test_a_childs_keywords_name_the_child() -> None:
    named_child = PlanTextVocabulary(
        taxonomy(
            position("single-payer-aff", aliases=["single payer"]),
            position(
                "medicare-for-all-aff", parent="single-payer-aff", tag_keywords=["medicare for all", "m4a"]
            ),
        )
    )
    assert named_child.named("the usfg should adopt m4a") == ("medicare-for-all-aff",)
    assert named_child.named("the usfg should adopt single payer by medicare for all") == (
        "medicare-for-all-aff",
    )


def test_two_children_of_one_parent_conflict() -> None:
    assert verdict((BLOCK, "Plan"), (ANALYTIC, "A sample plan by the voucher route and the toll route.")) == (
        DocumentPlanText(PlanTextVerdict.CONFLICTING)
    )


# ------------------------------------------------------------------------------------------------
# A plan text that says only the resolution
# ------------------------------------------------------------------------------------------------

RESOLUTIONAL = ResolutionalPlanWords(
    topic_id="sample-topic",
    position_id="national-plan-aff",
    frame_words=("establish", "federal", "government", "should", "states", "united"),
    resolutional_words=("national", "program", "thus"),
)
NATIONAL = taxonomy(
    position("sample-plan-aff", aliases=["sample plan"]),
    position("other-plan-aff", aliases=["other plan"]),
    position("national-plan-aff"),
    position("spending-da", kind="da", aliases=["spending da"]),
)
WITH_RESOLUTIONAL = PlanTextVocabulary(NATIONAL, RESOLUTIONAL)


def resolutional_verdict(text: str) -> DocumentPlanText:
    return verdict((BLOCK, "Plan"), (ANALYTIC, text), vocabulary=WITH_RESOLUTIONAL)


@pytest.mark.parametrize(
    "text",
    [
        SHAPED_NOTHING,
        "Thus: the United States federal government should establish a national program in the United States",
        "The United States federal government should thus establish a national program.",
    ],
)
def test_a_plan_text_of_frame_and_resolutional_words_names_the_resolutional_aff(text: str) -> None:
    assert resolutional_verdict(text) == DocumentPlanText(PlanTextVerdict.NAMES, "national-plan-aff")


@pytest.mark.parametrize(
    "text",
    [
        "The United States federal government should establish a national voucher program.",
        "The United States federal government should establish a national program for Arctic cleanup.",
    ],
)
def test_one_word_outside_the_sets_leaves_it_unnamed(text: str) -> None:
    assert resolutional_verdict(text) == DocumentPlanText(PlanTextVerdict.UNNAMED)


def test_an_aff_the_plan_text_names_wins_over_the_resolutional_rule() -> None:
    found = resolutional_verdict(
        "The United States federal government should establish a national sample plan."
    )
    assert found == DocumentPlanText(PlanTextVerdict.NAMES, "sample-plan-aff")


def test_the_resolutional_aff_beside_one_other_aff_names_the_other() -> None:
    found = verdict(
        (BLOCK, "Plan"),
        (ANALYTIC, SHAPED_NOTHING),
        (BLOCK, "Plan"),
        (ANALYTIC, "Sample plan."),
        vocabulary=WITH_RESOLUTIONAL,
    )
    assert found == DocumentPlanText(PlanTextVerdict.NAMES, "sample-plan-aff")


def test_the_resolutional_aff_never_makes_a_conflict_and_never_settles_one() -> None:
    assert WITH_RESOLUTIONAL.narrowest({"national-plan-aff"}) == ("national-plan-aff",)
    assert WITH_RESOLUTIONAL.narrowest({"national-plan-aff", "sample-plan-aff"}) == ("sample-plan-aff",)
    assert WITH_RESOLUTIONAL.narrowest({"national-plan-aff", "sample-plan-aff", "other-plan-aff"}) == (
        "other-plan-aff",
        "sample-plan-aff",
    )


def test_without_the_rule_the_same_aff_conflicts_like_any_other() -> None:
    assert PlanTextVocabulary(NATIONAL).narrowest({"national-plan-aff", "sample-plan-aff"}) == (
        "national-plan-aff",
        "sample-plan-aff",
    )


def test_the_resolutional_rule_needs_a_federal_actor() -> None:
    assert resolutional_verdict("National program.") == DocumentPlanText(PlanTextVerdict.NONE)
    assert resolutional_verdict("The fifty states should establish a national program.") == DocumentPlanText(
        PlanTextVerdict.NONE
    )


def test_without_the_rule_a_resolutional_plan_text_is_unnamed() -> None:
    assert verdict((BLOCK, "Plan"), (ANALYTIC, SHAPED_NOTHING)) == DocumentPlanText(PlanTextVerdict.UNNAMED)


@pytest.mark.parametrize(
    ("position_id", "kind", "fields"),
    [
        ("absent-plan-aff", "aff", {}),
        ("national-plan-aff", "da", {}),
        ("national-plan-aff", "aff", {"deprecated": True}),
    ],
)
def test_the_resolutional_aff_must_be_an_active_aff_of_the_taxonomy(
    position_id: str, kind: str, fields: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match=position_id):
        PlanTextVocabulary(
            taxonomy(position("national-plan-aff", kind=kind, **fields)),
            RESOLUTIONAL.model_copy(update={"position_id": position_id}),
        )


@pytest.mark.parametrize(
    ("field", "words"),
    [("frame_words", ("Federal",)), ("resolutional_words", ("two words",)), ("resolutional_words", ())],
)
def test_the_word_sets_are_single_lowercase_words(field: str, words: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match=field):
        ResolutionalPlanWords.model_validate({**RESOLUTIONAL.model_dump(), field: words})


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


def test_the_vocabulary_digest_moves_with_the_resolutional_words() -> None:
    fewer = RESOLUTIONAL.model_copy(update={"resolutional_words": ("national", "program")})
    assert PlanTextVocabulary(NATIONAL).digest != WITH_RESOLUTIONAL.digest
    assert PlanTextVocabulary(NATIONAL, fewer).digest != WITH_RESOLUTIONAL.digest
    assert PlanTextVocabulary(NATIONAL, RESOLUTIONAL).digest == WITH_RESOLUTIONAL.digest


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


# ------------------------------------------------------------------------------------------------
# The words for the coach's sheet
# ------------------------------------------------------------------------------------------------


def test_the_sheet_shows_plan_texts_that_name_an_aff_or_read_like_one() -> None:
    found = read(
        (BLOCK, "Plan"),
        (ANALYTIC, SHAPED_SAMPLE),
        (BLOCK, "PT"),
        (BLOCK, "Advantage One"),
        (BLOCK, "Plan"),
        (ANALYTIC, "Other plan."),
    )
    assert [one.element_index for one in sheet_plan_texts(found)] == [1, 5]


def test_a_plan_texts_words_are_read_back_by_place_and_digest() -> None:
    specs = paragraphs((BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE), (BLOCK, "Plan"), (ANALYTIC, "Other plan."))
    found = read_plan_texts(specs, frozenset(), WORDS)
    assert plan_text_words(specs, found) == (
        *["the", "united", "states", "federal", "government", "should", "establish", "a", "sample", "plan"],
        "other",
        "plan",
    )


def test_a_paragraph_that_reads_differently_gives_no_words() -> None:
    found = read((BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE))
    changed = paragraphs((BLOCK, "Plan"), (ANALYTIC, SHAPED_NOTHING))
    assert plan_text_words(changed, found) is None
    assert plan_text_words(paragraphs((BLOCK, "Plan")), found) is None


def test_a_plan_text_is_read_back_word_for_word() -> None:
    specs = paragraphs((BLOCK, "Plan"), (ANALYTIC, SHAPED_SAMPLE), (BLOCK, "Plan"), (ANALYTIC, "Other plan."))
    found = read_plan_texts(specs, frozenset(), WORDS)
    assert read_back_plan_texts(specs, found) == (SHAPED_SAMPLE, "Other plan.")
    assert read_back_plan_texts(paragraphs((BLOCK, "Plan"), (ANALYTIC, SHAPED_NOTHING)), found[:1]) is None

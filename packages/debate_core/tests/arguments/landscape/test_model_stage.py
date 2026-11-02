"""The model stage's pure rules (`v1-e32-t07`): the echo check, a batch's coverage and what a card sends.

Every expected value is written by hand. Every heading, tag and evidence text is invented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.model_stage import (
    ECHO_WORDS,
    BatchProblem,
    ModelCandidate,
    ModelItem,
    Refusal,
    answer_problems,
    batches,
    bounded_words,
    echoes,
    judge,
    model_order,
    places_nothing,
    prompt_variables,
    refusal,
    refusal_reason,
    sent_headings,
)
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ModelPositionAnswer,
    ModelPositionAnswers,
    PositionRole,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository

REPOSITORY = Path(__file__).resolve().parents[5]
TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "2.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": "spending-da",
                "label": "Spending DA",
                "kind": "da",
                "side": "neg",
                "aliases": ["spending da"],
            },
            {
                "id": "cliff-da",
                "label": "Cliff DA",
                "kind": "da",
                "side": "neg",
                "parent": "spending-da",
                "description": "The fiscal cliff version.",
            },
            {"id": "old-da", "label": "Old DA", "kind": "da", "side": "neg", "deprecated": True},
        ],
    }
)
EVIDENCE = "One two three four five six seven eight nine ten eleven twelve thirteen."


def answer(
    position_id: str | None = "spending-da", rationale: str = "a reason", item: str = "item-1"
) -> ModelPositionAnswer:
    return ModelPositionAnswer(item=item, position_id=position_id, confidence=0.7, rationale=rationale)


def candidate(fingerprint: str = "a" * 64, cards: int = 1, *, answer_heading: bool = False) -> ModelCandidate:
    return ModelCandidate(
        fingerprint=fingerprint,
        source_sha256="0" * 64,
        first_element_index=3,
        headings=(NormalizedHeading(text="cliff", answer=answer_heading),),
        tag="the cliff nears",
        short_cite="smith 24",
        own_names=(),
        cards=cards,
    )


def judged(one: ModelPositionAnswer, *, evidence: str = EVIDENCE, answer_heading: bool = False):  # noqa: ANN201
    return judge(
        one,
        ModelItem(candidate=candidate(answer_heading=answer_heading), excerpt="one two", evidence=evidence),
        taxonomy=TAXONOMY,
        prompt_id="landscape.classify_position",
        prompt_version="1.0.0",
        model_id="sample-model",
    )


# ------------------------------------------------------------------------------------------------
# The echo check (ac2)
# ------------------------------------------------------------------------------------------------


def test_twelve_consecutive_words_of_the_evidence_are_an_echo() -> None:
    assert ECHO_WORDS == 12
    assert echoes("It says: ONE two, three four five six seven eight nine ten eleven twelve!", EVIDENCE)


def test_eleven_consecutive_words_are_not_an_echo() -> None:
    assert not echoes("one two three four five six seven eight nine ten eleven", EVIDENCE)
    assert not echoes("one two three four five six seven eight nine ten eleven zebra twelve", EVIDENCE)


def test_twelve_words_from_the_middle_of_the_evidence_are_an_echo() -> None:
    assert echoes(
        "so: two three four five six seven eight nine ten eleven twelve thirteen, it seems", EVIDENCE
    )


def test_no_evidence_is_never_echoed() -> None:
    assert not echoes("one two three four five six seven eight nine ten eleven twelve", None)
    assert not echoes("one two three four five six seven eight nine ten eleven twelve", "")


# ------------------------------------------------------------------------------------------------
# Judging an answer
# ------------------------------------------------------------------------------------------------


def test_an_accepted_answer_is_a_model_result_naming_its_prompt_and_model() -> None:
    result = judged(answer("cliff-da"))

    assert (result.position_id, result.method, result.confidence) == (
        "cliff-da",
        ClassificationMethod.MODEL,
        0.7,
    )
    assert (result.prompt_id, result.prompt_version, result.model_id) == (
        "landscape.classify_position",
        "1.0.0",
        "sample-model",
    )
    assert (result.role, result.taxonomy_version, result.rationale) == (
        PositionRole.READS,
        "2.0.0",
        "a reason",
    )


def test_a_card_under_an_answer_heading_answers_the_position() -> None:
    assert judged(answer(), answer_heading=True).role is PositionRole.ANSWERS


@pytest.mark.parametrize("position_id", ["made-up-da", "old-da", "Spending DA", "spending-da-"])
def test_an_unknown_or_retired_id_places_nothing(position_id: str) -> None:
    result = judged(answer(position_id))

    assert places_nothing(result)
    assert refusal_reason(result) is Refusal.UNKNOWN_POSITION


def test_an_echoing_rationale_places_nothing_and_keeps_no_word_of_it() -> None:
    result = judged(answer(rationale="one two three four five six seven eight nine ten eleven twelve"))

    assert refusal_reason(result) is Refusal.ECHOES_EVIDENCE
    assert "seven" not in result.rationale


def test_a_rationale_repeating_the_tag_places_nothing() -> None:
    long_tag = ModelItem(
        candidate=ModelCandidate(
            fingerprint="b" * 64,
            source_sha256="0" * 64,
            first_element_index=0,
            headings=(),
            tag="alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu",
            short_cite=None,
            own_names=(),
        ),
        excerpt=None,
    )
    result = judge(
        answer(rationale="beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu"),
        long_tag,
        taxonomy=TAXONOMY,
        prompt_id="landscape.classify_position",
        prompt_version="1.0.0",
        model_id="sample-model",
    )

    assert refusal_reason(result) is Refusal.ECHOES_EVIDENCE


def test_an_answer_naming_no_position_places_nothing() -> None:
    assert refusal_reason(judged(answer(None))) is Refusal.NO_POSITION


@pytest.mark.parametrize("reason", list(Refusal))
def test_each_refusal_is_read_back_from_its_result(reason: Refusal) -> None:
    result = refusal(
        reason,
        taxonomy_version="2.0.0",
        prompt_id="landscape.classify_position",
        prompt_version="1.0.0",
        model_id="m",
    )
    assert (result.method, result.position_id, result.confidence) == (ClassificationMethod.MODEL, None, 0.0)
    assert refusal_reason(result) is reason


def test_a_placed_result_is_no_refusal() -> None:
    assert refusal_reason(judged(answer())) is None
    assert not places_nothing(judged(answer()))


# ------------------------------------------------------------------------------------------------
# A batch's answer as a whole
# ------------------------------------------------------------------------------------------------


def test_a_batch_answering_every_item_once_has_no_problem() -> None:
    answers = ModelPositionAnswers(answers=(answer(item="item-2"), answer(item="item-1")))
    assert answer_problems(answers, 2) == ()


def test_a_batch_missing_duplicating_or_inventing_items_names_each_by_label() -> None:
    answers = ModelPositionAnswers(
        answers=(answer(item="item-1"), answer(item="item-1"), answer(item="item-4"), answer(item="item-10"))
    )
    assert answer_problems(answers, 3) == (
        BatchProblem("unknown_item", "item-4 is not an item of the request"),
        BatchProblem("unknown_item", "item-10 is not an item of the request"),
        BatchProblem("missing_item", "item-2 has no answer"),
        BatchProblem("missing_item", "item-3 has no answer"),
        BatchProblem("duplicate_item", "item-1 is answered 2 times"),
    )


# ------------------------------------------------------------------------------------------------
# What a card sends, and in what order
# ------------------------------------------------------------------------------------------------


def test_sent_headings_lose_team_code_words_and_empty_headings() -> None:
    headings = (
        NormalizedHeading(text="ab", answer=False),
        NormalizedHeading(text="ab cliff da", answer=True),
        NormalizedHeading(text="link", answer=False),
    )
    assert sent_headings(headings, frozenset({"ab", "kl"})) == (
        NormalizedHeading(text="cliff da", answer=True),
        NormalizedHeading(text="link", answer=False),
    )


def test_bounded_words_keeps_the_first_words_only() -> None:
    assert bounded_words("one two three four", 2) == "one two"
    assert bounded_words("one two", 5) == "one two"
    assert bounded_words("", 5) is None
    assert bounded_words(None, 5) is None


def test_the_most_shared_cards_are_asked_about_first_then_by_fingerprint() -> None:
    order = model_order([candidate("c" * 64, 1), candidate("b" * 64, 3), candidate("a" * 64, 1)])
    assert [(one.fingerprint[0], one.cards) for one in order] == [("b", 3), ("a", 1), ("c", 1)]


def test_batches_are_runs_of_the_batch_size() -> None:
    assert batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    with pytest.raises(ValueError, match="at least one"):
        batches([1], 0)


def test_the_prompt_lists_active_positions_and_numbers_the_cards() -> None:
    item = ModelItem(candidate=candidate(), excerpt="one two", evidence="never sent")
    variables = prompt_variables(TAXONOMY, [item, item])

    assert variables["taxonomy_version"] == "2.0.0"
    positions = json.loads(str(variables["positions"]))
    assert positions == [
        {"id": "spending-da", "kind": "da", "label": "Spending DA", "side": "neg"},
        {
            "description": "The fiscal cliff version.",
            "id": "cliff-da",
            "kind": "da",
            "label": "Cliff DA",
            "parent": "spending-da",
            "side": "neg",
        },
    ]
    items = json.loads(str(variables["items"]))
    assert [one["item"] for one in items] == ["item-1", "item-2"]
    assert items[0] == {
        "item": "item-1",
        "headings": ["cliff"],
        "under_an_answer_heading": False,
        "tag": "the cliff nears",
        "cite": "smith 24",
        "excerpt": "one two",
    }
    assert "never sent" not in json.dumps(variables)
    assert "0" * 64 not in json.dumps(variables)


def test_every_position_the_policy_prompt_sends_has_its_side_and_a_one_line_description() -> None:
    """`v1-e32-t40`: the committed Policy taxonomy, generic.yaml's Policy positions with it, as the prompt
    sends it. A position with no description gave the model its id and label alone to tell neighbours
    apart (`v1-e32-t39`)."""
    taxonomy = YamlTaxonomyRepository.load(REPOSITORY / "config" / "landscape").taxonomy("policy-2026-27-nhi")
    assert taxonomy is not None
    positions = json.loads(str(prompt_variables(taxonomy, ())["positions"]))

    assert len(positions) == len(taxonomy.active_positions) > 100
    assert [one["id"] for one in positions if not one.get("description", "").strip()] == []
    assert {one["side"] for one in positions} == {"aff", "neg", "both"}
    assert [
        one["id"] for one in positions if "\n" in one["description"] or len(one["description"]) > 140
    ] == []

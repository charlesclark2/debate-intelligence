"""The position classification contract (`v1-e32-t02-position-classification` ac2).

A classification names its item, the position or none, a role, a confidence, a rationale of at most
280 characters, the method and the taxonomy version; a MODEL result also names its prompt and model,
and every other result says its prompt version is `none`. Its position is one of the taxonomy's
active ids, whatever stage wrote it. Overrides are the coach's decisions, one per heading.

Every position, heading and digest here is invented for the test.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    DETERMINISTIC_PROMPT_VERSION,
    NO_OVERRIDE_DIGEST,
    ClassificationMethod,
    ClassificationResult,
    OverrideRules,
    PositionClassification,
    PositionRole,
    card_item_id,
    checked_against,
    classification_schema,
    section_item_id,
)

SOURCE = "a" * 64

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.2.0",
        "event": "POLICY",
        "positions": [
            {"id": "spending-da", "label": "Spending DA", "kind": "da", "side": "neg"},
            {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg"},
            {
                "id": "old-states-cp",
                "label": "Old states CP",
                "kind": "cp",
                "side": "neg",
                "deprecated": True,
                "merged_into": "states-cp",
            },
            {"id": "gone-k", "label": "Gone K", "kind": "k", "side": "neg", "deprecated": True},
        ],
    }
)


def card(**fields: Any) -> dict[str, Any]:
    """A deterministic card classification as a document, with `fields` changed."""
    document: dict[str, Any] = {
        "item_id": card_item_id(SOURCE, 12),
        "item_kind": "CARD",
        "source_sha256": SOURCE,
        "first_element_index": 12,
        "position_id": "spending-da",
        "role": "READS",
        "confidence": 1.0,
        "rationale": "the heading over it is the alias 'spending da'",
        "method": "ALIAS",
        "taxonomy_version": "1.2.0",
    }
    document.update(fields)
    return document


MODEL_FIELDS: dict[str, Any] = {
    "method": "MODEL",
    "prompt_id": "landscape.classify_position",
    "prompt_version": "1.0.0",
    "model_id": "sample-model",
    "confidence": 0.7,
}


# ------------------------------------------------------------------------------------------------
# What a classification records
# ------------------------------------------------------------------------------------------------


def test_a_classification_records_every_field_ac2_names() -> None:
    found = PositionClassification.model_validate(card())
    assert set(found.model_dump()) == {
        "item_id",
        "item_kind",
        "source_sha256",
        "first_element_index",
        "position_id",
        "role",
        "confidence",
        "rationale",
        "method",
        "taxonomy_version",
        "prompt_id",
        "prompt_version",
        "model_id",
    }
    assert (found.prompt_id, found.prompt_version, found.model_id) == (None, "none", None)
    assert DETERMINISTIC_PROMPT_VERSION == "none"


def test_the_methods_and_roles_are_the_ones_the_spec_names() -> None:
    assert [method.value for method in ClassificationMethod] == [
        "ALIAS",
        "TAG_KEYWORD",
        "INHERITED",
        "OVERRIDE",
        "MODEL",
    ]
    assert [role.value for role in PositionRole] == ["READS", "ANSWERS"]


def test_a_model_result_names_its_prompt_and_model() -> None:
    found = PositionClassification.model_validate(card(**MODEL_FIELDS))
    assert (found.prompt_id, found.prompt_version, found.model_id) == (
        "landscape.classify_position",
        "1.0.0",
        "sample-model",
    )


def test_a_rationale_of_280_characters_is_accepted() -> None:
    assert len(PositionClassification.model_validate(card(rationale="x" * 280)).rationale) == 280


def test_an_item_nothing_placed_has_no_position_role_or_method() -> None:
    found = PositionClassification.model_validate(
        card(position_id=None, role=None, method=None, confidence=0.0, rationale="no heading matched")
    )
    assert found.position_id is None


def test_an_override_may_rule_that_a_heading_names_no_position() -> None:
    found = PositionClassification.model_validate(
        card(position_id=None, role=None, method="OVERRIDE", rationale="the coach ruled 'link' no position")
    )
    assert found.method is ClassificationMethod.OVERRIDE


@pytest.mark.parametrize(
    ("case", "fields"),
    [
        ("an unknown field", {"heading": "Spending DA"}),
        ("a rationale of 281 characters", {"rationale": "x" * 281}),
        ("an empty rationale", {"rationale": " "}),
        ("confidence above 1", {"confidence": 1.01}),
        ("confidence below 0", {"confidence": -0.01}),
        ("a position with no role", {"role": None}),
        ("a role with no position", {"position_id": None}),
        ("a position with no method", {"method": None}),
        ("nothing placed it, yet it is sure", {"position_id": None, "role": None, "method": None}),
        ("an unknown method", {"method": "GUESS"}),
        ("an unknown role", {"role": "CITES"}),
        ("a version that is not semver", {"taxonomy_version": "v1.2"}),
        ("a model result with no prompt", {**MODEL_FIELDS, "prompt_id": None}),
        ("a model result with no model", {**MODEL_FIELDS, "model_id": None}),
        ("a model result with prompt version none", {**MODEL_FIELDS, "prompt_version": "none"}),
        ("a deterministic result naming a prompt", {"prompt_id": "landscape.classify_position"}),
        ("a deterministic result naming a model", {"model_id": "sample-model"}),
        ("a deterministic result with a prompt version", {"prompt_version": "1.0.0"}),
        ("a card with no paragraph", {"first_element_index": None}),
        ("a card whose id names another paragraph", {"item_id": card_item_id(SOURCE, 13)}),
        ("a card whose id names another source", {"item_id": card_item_id("b" * 64, 12)}),
        ("a section naming a paragraph", {"item_kind": "SECTION", "item_id": section_item_id(SOURCE, ["X"])}),
        (
            "a section whose id is not a digest",
            {"item_kind": "SECTION", "first_element_index": None, "item_id": f"{SOURCE}:section:spending"},
        ),
        ("a source that is not a digest", {"source_sha256": "abc", "item_id": "abc:card:12"}),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_a_classification_refuses(case: str, fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PositionClassification.model_validate(card(**fields))


def test_a_section_id_is_a_digest_of_the_path_as_written() -> None:
    one = section_item_id(SOURCE, ["1NC", "Spending DA"])
    assert one == section_item_id(SOURCE, ["1NC", "Spending DA"])
    assert one != section_item_id(SOURCE, ["2NC", "Spending DA"])
    assert "Spending" not in one
    found = PositionClassification.model_validate(
        card(item_kind="SECTION", first_element_index=None, item_id=one)
    )
    assert found.first_element_index is None


def test_the_result_is_the_placement_without_the_item() -> None:
    found = PositionClassification.model_validate(card())
    result = found.result
    assert type(result) is ClassificationResult
    assert result.model_dump() == {
        key: value
        for key, value in found.model_dump().items()
        if key not in {"item_id", "item_kind", "source_sha256", "first_element_index"}
    }


# ------------------------------------------------------------------------------------------------
# Only the taxonomy's own active ids
# ------------------------------------------------------------------------------------------------


def test_the_schema_lists_the_active_ids_and_no_retired_one() -> None:
    schema = classification_schema(TAXONOMY).model_json_schema()
    choices = schema["properties"]["position_id"]["anyOf"]
    assert {"enum": ["spending-da", "states-cp"], "type": "string"} in choices
    assert {"type": "null"} in choices
    assert schema["properties"]["taxonomy_version"]["const"] == "1.2.0"


def test_the_schema_is_built_once_per_taxonomy_version() -> None:
    assert classification_schema(TAXONOMY) is classification_schema(TAXONOMY)
    bumped = Taxonomy.model_validate({**TAXONOMY.model_dump(), "taxonomy_version": "1.3.0"})
    assert classification_schema(bumped) is not classification_schema(TAXONOMY)


@pytest.mark.parametrize("position_id", ["spending-da", "states-cp", None])
def test_a_result_naming_an_active_id_or_none_passes(position_id: str | None) -> None:
    fields = card(position_id=position_id)
    if position_id is None:
        fields.update(role=None, method=None, confidence=0.0)
    result = PositionClassification.model_validate(fields)
    assert checked_against(TAXONOMY, result) is result


@pytest.mark.parametrize(
    ("case", "fields"),
    [
        ("a retired id merged into another", {"position_id": "old-states-cp"}),
        ("a retired id with nowhere to go", {"position_id": "gone-k"}),
        ("an id no position has", {"position_id": "medicaid-da"}),
        ("another version", {"taxonomy_version": "1.1.0"}),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_a_result_outside_the_taxonomy_is_refused(case: str, fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        checked_against(TAXONOMY, PositionClassification.model_validate(card(**fields)))


def test_a_model_result_is_held_to_the_same_ids() -> None:
    with pytest.raises(ValidationError):
        checked_against(
            TAXONOMY, PositionClassification.model_validate(card(**MODEL_FIELDS, position_id="x-da"))
        )


# ------------------------------------------------------------------------------------------------
# Overrides
# ------------------------------------------------------------------------------------------------


def overrides(*rules: tuple[str, str | None]) -> OverrideRules:
    return OverrideRules.model_validate(
        {
            "topic_id": "policy-sample-topic",
            "overrides": [{"heading": heading, "position_id": position} for heading, position in rules],
        }
    )


def test_an_override_names_a_heading_once() -> None:
    with pytest.raises(ValidationError, match="overridden twice"):
        overrides(("fed key", "states-cp"), ("fed key", None))


def test_an_override_heading_is_written_as_a_normalized_heading() -> None:
    with pytest.raises(ValidationError, match="normalized heading"):
        overrides(("Fed Key", "states-cp"))


def test_an_override_may_name_an_active_id_a_merged_one_or_none() -> None:
    overrides(("fed key", "states-cp"), ("old fed", "old-states-cp"), ("link", None)).check_against(TAXONOMY)


@pytest.mark.parametrize(
    ("position_id", "expected"),
    [("medicaid-da", "not a position"), ("gone-k", "retired with no position")],
)
def test_an_override_naming_no_countable_position_is_refused(position_id: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        overrides(("fed key", position_id)).check_against(TAXONOMY)


def test_overrides_of_another_topic_are_refused() -> None:
    other = OverrideRules.model_validate({"topic_id": "policy-other-topic", "overrides": []})
    with pytest.raises(ValueError, match="cannot apply"):
        other.check_against(TAXONOMY)


def test_the_override_digest_changes_only_with_the_decisions_on_the_headings_named() -> None:
    before = overrides(("fed key", "states-cp"), ("link", None))
    assert before.digest_for(["spending da", "impact"]) == NO_OVERRIDE_DIGEST
    path = ["spending da", "fed key"]
    changed_here = overrides(("fed key", "spending-da"), ("link", None))
    changed_elsewhere = overrides(("fed key", "states-cp"), ("link", "spending-da"))
    added_elsewhere = overrides(("fed key", "states-cp"), ("link", None), ("impact", None))
    assert before.digest_for(path) != NO_OVERRIDE_DIGEST
    assert changed_here.digest_for(path) != before.digest_for(path)
    assert changed_elsewhere.digest_for(path) == before.digest_for(path)
    assert added_elsewhere.digest_for(path) == before.digest_for(path)
    assert before.digest_for(reversed(path)) == before.digest_for(path)

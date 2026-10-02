"""The card manifest model and its committed JSON Schema (`v1-e03-t06-verify-command`).

If the drift test fails, run `uv run scripts/export_schemas.py` and commit the result alongside the
model change.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.fixtures.verification.verification_world import VerificationWorld
from tests.fixtures.verify.published_schemas import violations

from debate_core.domain import Card
from debate_core.evidence.manifest import (
    CARD_MANIFEST_SCHEMA_FILENAME,
    CardManifest,
    render_card_manifest_schema,
)

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
GENERATED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def committed(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def manifest_document(cards: tuple[Card, ...]) -> dict[str, Any]:
    """A manifest of ``cards``, written by the model and read back as plain JSON."""
    manifest = CardManifest(manifest_version=1, generated_at=GENERATED_AT, cards=cards)
    return json.loads(manifest.model_dump_json())


@pytest.fixture(scope="module")
def cards() -> tuple[Card, Card]:
    world = VerificationWorld()
    source = world.add_source("Wells across the invented basin ran dry in 2031.\n\nNobody planned for it.")
    return world.cut_card(source, 0, 48), world.cut_card_from_ranges(source, ((0, 5), (13, 48)))


def test_the_committed_manifest_schema_matches_the_model() -> None:
    path = SCHEMA_DIR / CARD_MANIFEST_SCHEMA_FILENAME
    assert path.is_file(), "card_manifest.v1.json is missing; run: uv run scripts/export_schemas.py"
    assert committed(CARD_MANIFEST_SCHEMA_FILENAME) == render_card_manifest_schema(), (
        "card_manifest.v1.json is stale; run: uv run scripts/export_schemas.py"
    )


def test_the_manifest_schema_refers_to_the_card_schema_rather_than_restating_it() -> None:
    schema = committed(CARD_MANIFEST_SCHEMA_FILENAME)

    assert schema["properties"]["cards"]["items"] == {"$ref": "card.schema.json", "required": ["card_id"]}
    assert "$defs" not in schema
    # Not one of the card's own fields appears in the manifest schema.
    text = json.dumps(schema)
    for field in ("evidence_text", "omitted_ranges", "snapshot_id", "normalized_text_hash", "spans"):
        assert field not in text


def test_the_manifest_schema_names_its_dialect_and_forbids_unknown_keys() -> None:
    schema = committed(CARD_MANIFEST_SCHEMA_FILENAME)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["manifest_version", "generated_at", "cards"]
    assert schema["properties"]["manifest_version"]["const"] == 1


def test_a_manifest_the_model_writes_passes_the_committed_schemas(cards: tuple[Card, Card]) -> None:
    manifest = CardManifest(manifest_version=1, generated_at=GENERATED_AT, cards=cards)
    document = json.loads(manifest.model_dump_json())

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == []
    assert cards[1].omitted_ranges, "the second card should carry an omission through the round trip"
    assert CardManifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_the_committed_schemas_refuse_a_card_without_an_id(cards: tuple[Card, Card]) -> None:
    document = manifest_document(cards)
    del document["cards"][1]["card_id"]

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$.cards[1]", "required")]


def test_the_committed_schemas_enforce_a_rule_only_the_card_schema_has(cards: tuple[Card, Card]) -> None:
    """The reference is followed: a rule that exists only in card.schema.json is enforced."""
    document = manifest_document(cards)
    document["cards"][0]["evidence_start_offset"] = -1

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [
        ("$.cards[0].evidence_start_offset", "anyOf")
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_version", 2),
        ("generated_at", datetime(2026, 10, 1, 12, 0)),  # naive: refused
    ],
)
def test_the_model_refuses_another_version_and_a_naive_timestamp(
    field: str, value: object, cards: tuple[Card, Card]
) -> None:
    arguments: dict[str, Any] = {"manifest_version": 1, "generated_at": GENERATED_AT, "cards": cards}
    arguments[field] = value

    with pytest.raises(ValidationError) as refused:
        CardManifest(**arguments)

    assert [error["loc"] for error in refused.value.errors()] == [(field,)]


def test_a_manifest_lists_at_least_one_card(cards: tuple[Card, Card]) -> None:
    """An empty manifest would let a gate on `verify`'s exit code pass having checked nothing."""
    with pytest.raises(ValidationError) as refused:
        CardManifest(manifest_version=1, generated_at=GENERATED_AT, cards=())
    assert [error["loc"] for error in refused.value.errors()] == [("cards",)]

    document = manifest_document(cards)
    document["cards"] = []
    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$.cards", "minItems")]

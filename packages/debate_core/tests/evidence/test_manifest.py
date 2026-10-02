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
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from tests.fixtures.verification.verification_world import VerificationWorld

from debate_core.domain import Card
from debate_core.evidence.manifest import (
    CARD_MANIFEST_SCHEMA_FILENAME,
    CARD_SCHEMA_REFERENCE,
    CardManifest,
    render_card_manifest_schema,
)

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
GENERATED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def committed(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def committed_validator() -> Draft202012Validator:
    """The manifest schema as a consumer reads it: the two committed files, side by side."""
    card_schema = Resource.from_contents(committed(CARD_SCHEMA_REFERENCE))
    registry = Registry().with_resource(CARD_SCHEMA_REFERENCE, card_schema)
    return Draft202012Validator(committed(CARD_MANIFEST_SCHEMA_FILENAME), registry=registry)


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

    assert list(committed_validator().iter_errors(document)) == []
    assert cards[1].omitted_ranges, "the second card should carry an omission through the round trip"
    assert CardManifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_the_committed_schemas_refuse_a_card_without_an_id(cards: tuple[Card, Card]) -> None:
    document = manifest_document(cards)
    del document["cards"][1]["card_id"]

    errors = list(committed_validator().iter_errors(document))

    assert [(error.json_path, error.validator) for error in errors] == [("$.cards[1]", "required")]


def test_the_committed_schemas_enforce_a_rule_only_the_card_schema_has(cards: tuple[Card, Card]) -> None:
    """The reference is followed: a rule that exists only in card.schema.json is enforced."""
    document = manifest_document(cards)
    document["cards"][0]["evidence_start_offset"] = -1

    errors = list(committed_validator().iter_errors(document))

    assert [error.json_path for error in errors] == ["$.cards[0].evidence_start_offset"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_version", 2),
        ("generated_at", datetime(2026, 10, 1, 12, 0)),  # naive: refused
    ],
)
def test_the_model_refuses_another_version_and_a_naive_timestamp(field: str, value: object) -> None:
    arguments: dict[str, Any] = {"manifest_version": 1, "generated_at": GENERATED_AT, "cards": ()}
    arguments[field] = value

    with pytest.raises(ValidationError) as refused:
        CardManifest(**arguments)

    assert [error["loc"] for error in refused.value.errors()] == [(field,)]

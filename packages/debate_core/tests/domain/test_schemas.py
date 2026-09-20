"""The committed JSON Schemas are the published contract, so they must never drift from the models.

If one of these fails, run `uv run scripts/export_schemas.py` and commit the result alongside the
model change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from debate_core.domain import EXPORTED_MODELS, DomainModel, render_schemas, schema_filename

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

#: Every entity named in the epic's V1 subset plus the value objects exported beside them.
EXPECTED_ENTITY_NAMES = {
    "Article",
    "Card",
    "CardSpan",
    "Citation",
    "Search",
    "SearchResult",
    "SourceSnapshot",
}


def committed_schema(name: str) -> dict[str, Any]:
    """Load one committed schema file."""
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_every_v1_entity_is_exported() -> None:
    assert {model.__name__ for model in EXPORTED_MODELS} == EXPECTED_ENTITY_NAMES


@pytest.mark.parametrize("model", EXPORTED_MODELS, ids=lambda model: model.__name__)
def test_committed_schema_matches_the_model(model: type[DomainModel]) -> None:
    name = schema_filename(model)
    path = SCHEMA_DIR / name
    assert path.is_file(), f"{name} is missing; run: uv run scripts/export_schemas.py"
    assert committed_schema(name) == render_schemas()[name], (
        f"{name} is stale; run: uv run scripts/export_schemas.py"
    )


def test_no_schema_file_is_left_behind_by_a_removed_model() -> None:
    committed = {path.name for path in SCHEMA_DIR.glob("*.schema.json")}
    assert committed == set(render_schemas())


def test_schemas_declare_the_json_schema_dialect() -> None:
    for name in render_schemas():
        assert committed_schema(name)["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_schemas_forbid_unknown_properties() -> None:
    for name in render_schemas():
        assert committed_schema(name)["additionalProperties"] is False


def test_card_schema_documents_the_evidence_provenance_fields() -> None:
    properties = committed_schema("card.schema.json")["properties"]
    for field in (
        "snapshot_id",
        "evidence_text",
        "evidence_start_offset",
        "evidence_end_offset",
        "normalized_text_hash",
        "normalizer_version",
        "spans",
        "verification_status",
        "provenance_mode",
        "format_profile",
    ):
        assert field in properties


def test_ulid_fields_publish_their_pattern() -> None:
    article_id = committed_schema("article.schema.json")["properties"]["article_id"]
    assert article_id["pattern"] == "^[0-7][0-9ABCDEFGHJKMNPQRSTVWXYZ]{25}$"

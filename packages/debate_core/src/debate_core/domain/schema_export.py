"""Render the domain entities as JSON Schema.

The committed schemas under `packages/debate_core/schemas/` are the published contract for the
domain model: the web client, the V2 API and any future consumer read them instead of importing
Python. `scripts/export_schemas.py` writes them and `tests/domain/test_schemas.py` fails when they
drift, so a field cannot be added, renamed or removed without the schema change landing in the
same commit.

This module only *renders*; it never touches the filesystem, because nothing in
`debate_core.domain` performs I/O. The script does the writing.
"""

from __future__ import annotations

import re
from typing import Any

from debate_core.domain.article import Article, SourceSnapshot
from debate_core.domain.base import DomainModel
from debate_core.domain.card import Card, CardSpan
from debate_core.domain.citation import Citation
from debate_core.domain.search import Search, SearchResult

__all__ = ["EXPORTED_MODELS", "JSON_SCHEMA_DIALECT", "render_schemas", "schema_filename"]

#: JSON Schema dialect Pydantic v2 emits.
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

EXPORTED_MODELS: tuple[type[DomainModel], ...] = (
    Article,
    Card,
    CardSpan,
    Citation,
    Search,
    SearchResult,
    SourceSnapshot,
)
"""Every entity that gets its own schema file, ordered by name so the output is stable.

Value objects that only ever appear inside an entity (`ArticleIdentifiers`, `SearchFilters`,
`CitationField`) are not exported separately; they are inlined into their parent's `$defs`.
"""

_CAMEL_CASE_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def schema_filename(model: type[DomainModel]) -> str:
    """Return the schema file name for `model`, e.g. `SourceSnapshot` -> `source_snapshot.schema.json`."""
    return f"{_CAMEL_CASE_BOUNDARY.sub('_', model.__name__).lower()}.schema.json"


def render_schemas() -> dict[str, dict[str, Any]]:
    """Return every exported entity's JSON Schema, keyed by file name.

    Schemas are rendered in serialization mode: they describe the JSON a model produces, which is
    the shape stored in a repository and sent over the wire.
    """
    schemas: dict[str, dict[str, Any]] = {}
    for model in EXPORTED_MODELS:
        schema: dict[str, Any] = {"$schema": JSON_SCHEMA_DIALECT}
        schema.update(model.model_json_schema(mode="serialization"))
        schemas[schema_filename(model)] = schema
    return schemas

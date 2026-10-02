"""The committed schemas `debate-research verify` publishes, read the way an outside consumer reads them.

Validation here uses the files in `packages/debate_core/schemas/`, never the in-memory renderings the
code validates with, so a test that passes proves the committed contract and not only the code's
copy of it. jsonschema's types are loose; this module is the one place the verify tests touch them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "packages" / "debate_core" / "schemas"
CARD_SCHEMA = "card.schema.json"
MANIFEST_SCHEMA = "card_manifest.v1.json"
RESULT_SCHEMA = "verify_result.v1.json"


def committed_schema(name: str) -> dict[str, Any]:
    """One committed schema file, parsed."""
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def violations(schema_name: str, document: Any) -> list[tuple[str, str]]:
    """Every way ``document`` fails the committed schema, as ``(json_path, keyword)`` pairs.

    ``card.schema.json`` is available to a ``$ref``, as it is to a consumer holding both files.
    Nothing is fetched.
    """
    card = Resource.from_contents(committed_schema(CARD_SCHEMA))
    registry: Registry[Any] = Registry().with_resource(CARD_SCHEMA, card)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    validator = Draft202012Validator(committed_schema(schema_name), registry=registry)
    found: list[Any] = list(validator.iter_errors(document))  # pyright: ignore[reportUnknownMemberType]
    return sorted((str(error.json_path), str(error.validator)) for error in found)

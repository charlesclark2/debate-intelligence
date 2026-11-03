"""The committed file recipe schema is the published contract, so it must never drift from the models.

This is the drift check CI runs for `docs/data/file-recipe.schema.json`, wired the way
`packages/debate_core/tests/domain/test_schemas.py` checks the domain schemas that
`scripts/export_schemas.py` writes: a test in the default selection, so every `test` part of `ci.yml`
can run it. If the first test fails, run `uv run scripts/export_recipe_schema.py` and commit the
result with the model change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import export_recipe_schema as exporter  # noqa: E402

from debate_core.application.file_recipes import render_recipe_schema  # noqa: E402
from debate_core.domain.file_recipe import FileRecipe  # noqa: E402
from debate_core.evidence.fingerprints import EXACT_FINGERPRINT_VERSIONS  # noqa: E402


def test_the_committed_recipe_schema_matches_the_models() -> None:
    assert exporter.SCHEMA_PATH == REPO_ROOT / "docs" / "data" / "file-recipe.schema.json"
    assert exporter.is_current(exporter.SCHEMA_PATH), (
        "docs/data/file-recipe.schema.json is stale; run: uv run scripts/export_recipe_schema.py"
    )


def test_check_fails_on_a_stale_schema_and_leaves_it_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = tmp_path / "file-recipe.schema.json"
    stale.write_text(exporter.expected_text().replace('"title"', '"heading"', 1), encoding="utf-8")
    before = stale.read_bytes()

    assert exporter.main(["--check"], path=stale) == 1
    assert "stale" in capsys.readouterr().err
    assert stale.read_bytes() == before


def test_check_fails_on_a_missing_schema(tmp_path: Path) -> None:
    assert exporter.main(["--check"], path=tmp_path / "absent.schema.json") == 1


def test_writing_makes_the_check_pass(tmp_path: Path) -> None:
    target = tmp_path / "file-recipe.schema.json"
    assert exporter.main([], path=target) == 0
    assert exporter.main(["--check"], path=target) == 0


def test_the_schema_describes_a_recipe_as_written() -> None:
    schema = render_recipe_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "schema_version",
        "title",
        "topic",
        "format",
        "caselist",
        "position",
        "side",
        "fingerprint_version",
        "structure",
    }
    assert schema["properties"]["fingerprint_version"]["enum"] == sorted(EXACT_FINGERPRINT_VERSIONS)
    card = schema["$defs"]["CardRef"]["properties"]
    assert {"type": "string"} in card["tag_override"]["anyOf"]
    assert set(schema["$defs"]) >= {"Pocket", "Hat", "Block", "CardRef", "Analytic", "OccurrencePin"}
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False


def test_the_committed_schema_is_json_the_models_would_write() -> None:
    committed = json.loads(exporter.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed["title"] == FileRecipe.__name__

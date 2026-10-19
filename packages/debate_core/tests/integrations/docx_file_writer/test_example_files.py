"""The operator's fixture files for ac6: one per format, from t01's example recipes, never in the repo."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from debate_core.domain.file_provenance import FileProvenanceManifest

REPOSITORY = Path(__file__).resolve().parents[5]
SCRIPT = REPOSITORY / "scripts" / "build_example_evidence_files.py"
RECIPES = REPOSITORY / "tests" / "fixtures" / "file_builder" / "recipes"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_example_evidence_files", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _card_count(recipe: Path) -> int:
    return yaml.safe_load(recipe.read_text(encoding="utf-8")).__repr__().count("'fingerprint'")


def test_one_file_per_format_is_built_from_the_example_recipes(script: ModuleType, tmp_path: Path) -> None:
    assert script.main(["--output", str(tmp_path)]) == 0
    built = sorted(path.name for path in tmp_path.iterdir())
    assert built == sorted(
        name
        for recipe in RECIPES.glob("*.yaml")
        for name in (f"{recipe.stem}.docx", f"{recipe.stem}.docx.provenance.json")
    )
    formats: set[str] = set()
    for recipe in RECIPES.glob("*.yaml"):
        manifest = FileProvenanceManifest.model_validate_json(
            (tmp_path / f"{recipe.stem}.docx.provenance.json").read_bytes()
        )
        formats.add(manifest.format)
        assert len(manifest.cards) == _card_count(recipe)
        assert any(entry.resolution == "PINNED" for entry in manifest.cards), "each example pins one card"
    assert formats == {"POLICY", "LD", "PF"}


def test_the_examples_keep_their_recipes_structure_overrides_and_analytics(
    script: ModuleType, tmp_path: Path
) -> None:
    script.main(["--output", str(tmp_path)])
    recipe = yaml.safe_load((RECIPES / "policy-nhi-politics-da-answers.yaml").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "policy-nhi-politics-da-answers.docx.provenance.json").read_text())
    assert manifest["title"] == recipe["title"]
    assert [entry["tag_overridden"] for entry in manifest["cards"]] == [True, False, False, False, True]
    assert manifest["cards"][2]["school"] == "Maple Grove" and manifest["cards"][2]["round"] == "Round 3"


def test_two_runs_write_the_same_bytes(script: ModuleType, tmp_path: Path) -> None:
    script.main(["--output", str(tmp_path / "first")])
    script.main(["--output", str(tmp_path / "second")])
    for path in (tmp_path / "first").iterdir():
        assert path.read_bytes() == (tmp_path / "second" / path.name).read_bytes(), path.name


def test_it_refuses_to_write_inside_a_git_working_tree(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    inside = REPOSITORY / "never-written"
    assert script.main(["--output", str(inside)]) == 2
    assert not inside.exists()
    assert "inside a git working tree" in capsys.readouterr().err


def test_t01s_example_recipes_are_not_changed(script: ModuleType, tmp_path: Path) -> None:
    before = {path.name: path.read_bytes() for path in RECIPES.glob("*.yaml")}
    script.main(["--output", str(tmp_path)])
    assert {path.name: path.read_bytes() for path in RECIPES.glob("*.yaml")} == before

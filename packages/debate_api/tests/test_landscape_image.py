"""The function's image installs what renders the landscape pages (`v1-e39-t17`).

`scripts/tub_deploy.sh` builds the image from `uv export --package debate-api`, so the image holds
`debate-api`'s dependencies as `uv.lock` records them and nothing else. The landscape pages render a
bundle's Markdown with markdown-it-py. Until this task it was in the lock only through `rich`, which
the CLI and import-linter need and `debate-api` does not, so the function would have started and
failed on its first landscape page with `ModuleNotFoundError`: the failure `v1-e39-t08` guarded the
download's writer against. The renderer importing it, and the lock giving the image it, are checked
together here.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Any, Final

REPOSITORY: Final = Path(__file__).resolve().parents[3]
RENDERER: Final = REPOSITORY / "packages" / "debate_api" / "src" / "debate_api" / "landscape_markdown.py"


def _lock_package(lock: dict[str, Any], name: str) -> dict[str, Any]:
    return next(package for package in lock["package"] if package["name"] == name)


def test_the_landscape_renderer_is_markdown_it() -> None:
    tree = ast.parse(RENDERER.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert {"markdown_it", "markdown_it.token"} <= imported


def test_the_image_installs_markdown_it_py_as_debate_apis_own_dependency() -> None:
    lock = tomllib.loads((REPOSITORY / "uv.lock").read_text(encoding="utf-8"))

    api = _lock_package(lock, "debate-api")
    declared = {dependency["name"] for dependency in api["dependencies"]}
    renderer = _lock_package(lock, "markdown-it-py")

    assert "markdown-it-py" in declared
    assert "mdurl" in {dependency["name"] for dependency in renderer["dependencies"]}

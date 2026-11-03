"""The function's image installs what the download's writer needs (`v1-e39-t08`).

`scripts/tub_deploy.sh` builds the image from `uv export --package debate-api`, so the image holds
`debate-api`'s dependencies as `uv.lock` records them and nothing else. The download's writer and its
parser read WordprocessingML with lxml, which is `debate-core`'s `docx` extra. Without it the function
would start and fail on the first download with `ModuleNotFoundError`, the failure `v1-e01-t17` found
in the CLI's installed build. The composition root wiring the writer, and the lock giving the image
the extra, are checked together here.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Any, Final

REPOSITORY: Final = Path(__file__).resolve().parents[3]
CONTAINER: Final = REPOSITORY / "packages" / "debate_api" / "src" / "debate_api" / "container.py"


def _lock_package(lock: dict[str, Any], name: str) -> dict[str, Any]:
    return next(package for package in lock["package"] if package["name"] == name)


def test_download_writer_is_wired_by_the_composition_root() -> None:
    tree = ast.parse(CONTAINER.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert {
        "debate_core.integrations.docx_file_writer.writer",
        "debate_core.integrations.docx_parser.parser",
    } <= imported


def test_download_image_installs_debate_cores_docx_extra_and_lxml_with_it() -> None:
    lock = tomllib.loads((REPOSITORY / "uv.lock").read_text(encoding="utf-8"))

    api = _lock_package(lock, "debate-api")
    core = next(dependency for dependency in api["dependencies"] if dependency["name"] == "debate-core")
    extras = _lock_package(lock, "debate-core")["optional-dependencies"]

    assert "docx" in core.get("extra", [])
    assert "lxml" in {dependency["name"] for dependency in extras["docx"]}

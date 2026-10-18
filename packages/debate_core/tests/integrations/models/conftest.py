"""Writing prompt files for the prompt registry and lock tests (v1-e05-t04-prompt-registry).

Every file is written out as text, the way a person would write one, so a test can also write the
mistakes a person makes: an unquoted `1.0`, a key left out, a marker in the wrong place.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

CONTRACT_SCHEMA = "debate_core.testing.contracts.model_router.ContractPassage"
"""An output schema that resolves, with no module of its own to write."""

DEFAULT_BODY = "Choose the passage that best supports this tag: {{ tag }}\n"


def prompt_text(
    *,
    prompt_id: str = "example.written",
    version: str = "1.0.0",
    status: str = "released",
    task_class: str = "high_volume",
    output_schema: str = CONTRACT_SCHEMA,
    owner: str = "v1-e05-model-router",
    changelog_version: str | None = None,
    body: str = DEFAULT_BODY,
    front_matter: str | None = None,
) -> str:
    """The text of one prompt file. `front_matter` replaces the generated YAML whole."""
    if front_matter is None:
        front_matter = (
            f"prompt_id: {prompt_id}\n"
            f"version: {version}\n"
            f"status: {status}\n"
            f"task_class: {task_class}\n"
            f"output_schema: {output_schema}\n"
            f"owner: {owner}\n"
            "changelog:\n"
            f"  - version: {changelog_version or version}\n"
            "    date: 2026-10-17\n"
            "    summary: Written by a test.\n"
        )
    return f"---\n{front_matter}---\n{body}"


type PromptWriter = Callable[..., Path]
"""`write_prompt(relative_path, **prompt_text_arguments)`: writes one file under `prompt_dir`."""


@pytest.fixture
def prompt_dir(tmp_path: Path) -> Path:
    """An empty prompt directory for one test."""
    directory = tmp_path / "prompts"
    directory.mkdir()
    return directory


@pytest.fixture
def write_prompt(prompt_dir: Path) -> PromptWriter:
    """Write a prompt file under `prompt_dir` and return its path."""

    def write(relative_path: str, **fields: str) -> Path:
        path = prompt_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt_text(**fields), encoding="utf-8")
        return path

    return write

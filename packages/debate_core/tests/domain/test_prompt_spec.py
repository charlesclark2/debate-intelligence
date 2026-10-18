"""PromptSpec, the front matter of a prompt file (v1-e05-t04-prompt-registry)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.model_contracts import TaskClass
from debate_core.domain.prompt_spec import PromptSpec, PromptStatus, prompt_version_key


def spec(**changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "prompt_id": "card.select",
        "version": "1.0.0",
        "status": "released",
        "task_class": "complex_reasoning",
        "output_schema": "debate_core.testing.contracts.model_router.ContractPassage",
        "owner": "v1-e05-model-router",
        "changelog": [{"version": "1.0.0", "date": "2026-10-17", "summary": "First version."}],
    }
    document.update(changes)
    return document


def test_a_complete_front_matter_validates() -> None:
    parsed = PromptSpec.model_validate(spec())

    assert parsed.status is PromptStatus.RELEASED
    assert parsed.task_class is TaskClass.COMPLEX_REASONING
    assert parsed.is_released
    assert parsed.version_key == (1, 0, 0)


def test_versions_order_by_number_not_by_text() -> None:
    versions = ["1.10.0", "1.9.0", "0.10.0", "0.9.12", "10.0.0", "2.0.0", "1.9.10"]

    assert sorted(versions, key=prompt_version_key) == [
        "0.9.12",
        "0.10.0",
        "1.9.0",
        "1.9.10",
        "1.10.0",
        "2.0.0",
        "10.0.0",
    ]


@pytest.mark.parametrize("version", ["1.0", "1.0.0.0", "01.0.0", "1.0.0-rc.1", "x.y.z", "", " 1.0.0", "1.0.0\n"])
def test_a_version_that_is_not_major_minor_patch_has_no_key(version: str) -> None:
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        prompt_version_key(version)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt_id", "card/select"),
        ("version", "1.0"),
        ("task_class", "embeddings"),
        ("output_schema", "ContractPassage"),
        ("output_schema", "debate_core..ContractPassage"),
        ("owner", "  "),
        ("changelog", []),
    ],
)
def test_a_front_matter_value_that_breaks_a_rule_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValidationError) as caught:
        PromptSpec.model_validate(spec(**{field: value}))

    assert caught.value.errors()[0]["loc"][0] == field


def test_a_changelog_may_list_earlier_versions_but_not_the_same_one_twice() -> None:
    history = [
        {"version": "1.1.0", "date": "2026-10-18", "summary": "Second version."},
        {"version": "1.0.0", "date": "2026-10-17", "summary": "First version."},
    ]
    assert len(PromptSpec.model_validate(spec(version="1.1.0", changelog=history)).changelog) == 2

    with pytest.raises(ValidationError):
        PromptSpec.model_validate(spec(version="1.1.0", changelog=[history[0], history[0]]))

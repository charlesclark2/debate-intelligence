"""generic-k's description in the coach's words keys the model stage's calls again (`v1-e32-t53`).

The coach's review of 2026-11-08 replaced generic-k's description, so generic.yaml moved to 1.2.1 and the
Policy topic to 1.5.1. A cassette is filed under its call's key, which covers the prompt's variables, and
those carry the taxonomy's version and every position's description. So a request built from the
committed taxonomy has a key no recording made under 1.5.0 has: nothing recorded before replays under the
new version unless it is recorded again. Each change alone moves the key, so neither carries the other.
No card is sent: the positions alone decide what is shown here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.landscape_model_stage import (
    CLASSIFICATION_TASK_CLASS,
    CLASSIFY_POSITION_PROMPT_ID,
    CLASSIFY_POSITION_VERSION,
)
from debate_core.arguments.landscape.model_stage import answer_schema, prompt_variables
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.model_contracts import ModelPrompt, ModelRequest
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.models.fixture_key import fixture_key

REPOSITORY = Path(__file__).resolve().parents[5]
TOPIC = "policy-2026-27-nhi"
COACHS_DESCRIPTION = (
    "A card clearly related to a kritik that does not fall under any of the named kritiks in this list."
)
DESCRIPTION_BEFORE = (
    "A kritik card, a link, alternative, framework or impact, that fits no named kritik in this list."
)
VERSION_BEFORE = "1.5.0"


@pytest.fixture(scope="module")
def committed() -> Taxonomy:
    return YamlTaxonomyRepository.load(REPOSITORY / "config" / "landscape").taxonomy(TOPIC)


def _as(taxonomy: Taxonomy, *, version: str | None = None, description: str | None = None) -> Taxonomy:
    """The committed taxonomy with its version, generic-k's description, or both, as they were."""
    document = taxonomy.model_dump(mode="json")
    if version is not None:
        document["taxonomy_version"] = version
    if description is not None:
        for position in document["positions"]:
            if position["id"] == "generic-k":
                position["description"] = description
    return Taxonomy.model_validate(document)


def _key(taxonomy: Taxonomy) -> str:
    prompt = ModelPrompt(
        prompt_id=CLASSIFY_POSITION_PROMPT_ID,
        prompt_version=CLASSIFY_POSITION_VERSION,
        variables=prompt_variables(taxonomy, ()),
    )
    return fixture_key(
        ModelRequest.build(CLASSIFICATION_TASK_CLASS, prompt, answer_schema(CLASSIFY_POSITION_VERSION))
    )


def test_the_requests_carry_the_new_version_and_the_coachs_description(committed: Taxonomy) -> None:
    variables = prompt_variables(committed, ())

    assert variables["taxonomy_version"] == "1.5.1"
    assert COACHS_DESCRIPTION in str(variables["positions"])
    assert DESCRIPTION_BEFORE not in str(variables["positions"])


@pytest.mark.parametrize(
    ("version", "description"),
    [
        (VERSION_BEFORE, DESCRIPTION_BEFORE),
        (VERSION_BEFORE, None),
        (None, DESCRIPTION_BEFORE),
    ],
    ids=["as recorded under 1.5.0", "the version alone", "the description alone"],
)
def test_no_key_from_before_the_review_is_the_committed_taxonomys(
    committed: Taxonomy, version: str | None, description: str | None
) -> None:
    before = _as(committed, version=version, description=description)

    assert before != committed
    assert _key(before) != _key(committed)


def test_the_same_taxonomy_keeps_its_key(committed: Taxonomy) -> None:
    assert _key(_as(committed)) == _key(committed)

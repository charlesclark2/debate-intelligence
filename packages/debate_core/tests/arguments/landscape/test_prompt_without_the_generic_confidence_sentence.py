"""Prompt 1.3.1 (`v1-e32-t55`): 1.3.0 with the generic-confidence sentence taken out, and nothing else.

The PM's ruling 2 on `v1-e32-t49` kept 1.3.0's generic-confidence sentence on one condition: that the
answers naming a generic position above the threshold were not wrong more often than right. The re-record
on `deep_audit` had them right 0 times and wrong once (row 26), so 1.3.1 is 1.3.0 less that sentence, every
other bullet kept. A new version's front matter must name it and give it a changelog entry, so those two are
the only other lines that differ. Every other line is 1.3.0's, byte for byte.

1.3.1 is released, locked and the stage's default. Its cassettes are keyed by 1.3.1, and 1.3.0's recordings
still replay when 1.3.0 is asked for (`packages/debate_core/tests/application/test_coach_sample_stance.py`).
"""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.landscape_model_stage import (
    CLASSIFY_POSITION_PROMPT_ID,
    CLASSIFY_POSITION_VERSION,
    ModelClassificationStage,
    ParsedStoreCardTexts,
)
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain.landscape_classification import ModelStancedPositionAnswers
from debate_core.domain.model_contracts import TaskClass
from debate_core.integrations.models.prompt_lock import LockedVersion, PromptLock
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

PROMPTS: Final = Path(__file__).resolve().parents[5] / "prompts"
WITH_THE_SENTENCE: Final = PROMPTS / "landscape" / "classify_position@1.3.0.md"
WITHOUT_IT: Final = PROMPTS / "landscape" / "classify_position@1.3.1.md"

GENERIC_CONFIDENCE_SENTENCE: Final = (
    b"A generic position is never named by a tag or heading: give it 0.9 or more when the card is plainly "
    b"that kind's and no named position of the kind fits, and less than 0.6 when you are unsure the card is "
    b"that kind's."
)
"""The sentence 1.3.1 takes out, as 1.3.0 has it: the last of its confidence paragraph, after a space."""

FRONT_MATTER_FENCE: Final = b"---\n"


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.load(PROMPTS)


def lines_of(path: Path) -> list[bytes]:
    return path.read_bytes().splitlines(keepends=True)


def test_1_3_1_differs_from_1_3_0_by_the_one_sentence_its_version_and_its_changelog_entry() -> None:
    """The two files, diffed line by line: three changes, and the third removes only the sentence."""
    old, new = lines_of(WITH_THE_SENTENCE), lines_of(WITHOUT_IT)
    [confidence_line] = [line for line in old if GENERIC_CONFIDENCE_SENTENCE in line]
    assert b"".join(old).count(GENERIC_CONFIDENCE_SENTENCE) == 1
    closing_fence = old.index(FRONT_MATTER_FENCE, 1)

    changes = [
        (tag, i1, old[i1:i2], new[j1:j2])
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
        if tag != "equal"
    ]

    [version, changelog_entry, confidence] = changes
    assert version == ("replace", 2, [b"version: 1.3.0\n"], [b"version: 1.3.1\n"])
    assert changelog_entry[:3] == ("insert", closing_fence, [])
    assert changelog_entry[3][0] == b"  - version: 1.3.1\n"
    assert confidence == (
        "replace",
        old.index(confidence_line),
        [confidence_line],
        [confidence_line.replace(b" " + GENERIC_CONFIDENCE_SENTENCE, b"")],
    )


def test_the_inserted_lines_are_one_changelog_entry_for_1_3_1_and_the_rest_of_the_front_matter_is_kept(
    prompts: PromptRegistry,
) -> None:
    old = prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.3.0").spec
    new = prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.3.1").spec

    assert new.changelog[:-1] == old.changelog
    assert new.changelog[-1].version == "1.3.1"
    kept = {"version", "changelog"}
    assert new.model_dump(exclude=kept) == old.model_dump(exclude=kept)


def test_1_3_1_s_body_is_1_3_0_s_less_the_sentence(prompts: PromptRegistry) -> None:
    old = prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.3.0").body.encode("utf-8")
    new = prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.3.1").body.encode("utf-8")

    assert new == old.replace(b" " + GENERIC_CONFIDENCE_SENTENCE, b"")
    assert new != old


def test_1_3_1_is_released_and_locked_in_the_stanced_schema(prompts: PromptRegistry) -> None:
    registered = prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.3.1")
    lock = PromptLock.read(PROMPTS / "prompts.lock.json")

    assert registered.spec.status.value == "released"
    assert registered.schema is ModelStancedPositionAnswers
    assert registered.spec.task_class is TaskClass.HIGH_VOLUME
    assert lock.versions[(CLASSIFY_POSITION_PROMPT_ID, "1.3.1")] == LockedVersion.of(registered)


def test_the_stage_runs_1_3_1_unless_it_is_built_with_another(prompts: PromptRegistry) -> None:
    guard = StructuredOutputGuard(ScriptedModelRouter(model_id="unused"), prompts)
    texts = ParsedStoreCardTexts(InMemoryParsedStore())

    assert CLASSIFY_POSITION_VERSION == "1.3.1"
    assert ModelClassificationStage(guard, texts).prompt_version == "1.3.1"
    assert ModelClassificationStage(guard, texts, prompt_version="1.3.0").prompt_version == "1.3.0"

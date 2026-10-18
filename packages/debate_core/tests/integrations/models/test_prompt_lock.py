"""The released-version lock, `prompts/prompts.lock.json` (v1-e05-t04-prompt-registry, ac4).

The first test is the one that guards the repository: every released prompt under `prompts/` must
match the committed lock, so a released body edited without a version bump fails CI. The rest show
that comparison finds each way a released version can drift, on prompt trees written per test.

Body hashes are golden values computed by hand with `shasum -a 256` over the text after the front
matter, not read back from the code.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from debate_core.domain.model_contracts import TaskClass
from debate_core.integrations.models.errors import PromptLockError, PromptRegistryError
from debate_core.integrations.models.prompt_lock import (
    LockedVersion,
    LockProblem,
    LockProblemKind,
    PromptLock,
    compare_lock,
    extend_lock,
)
from debate_core.integrations.models.prompt_registry import PromptRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]

type PromptWriter = Callable[..., Path]
"""The `write_prompt` fixture of this directory's conftest."""
SAMPLE_PROMPTS = REPOSITORY_ROOT / "tests" / "fixtures" / "prompts"
SCHEMA = "debate_core.testing.contracts.model_router.ContractPassage"

DEFAULT_BODY_SHA256 = "feb58c2ecc3fad96a9727679ca876d7c217a634a3428848fbc51d84cef80cc95"
"""`printf 'Choose the passage that best supports this tag: {{ tag }}\\n' | shasum -a 256`"""

SAMPLE_BODY_SHA256 = "7fdbbf790c47b315e970ebb932556d58bc4f9fb622795c40d757ce9416166e7b"
"""The body of tests/fixtures/prompts/example/select-passage.md:
`awk 'f;/^---$/{c++; if(c==2) f=1}' tests/fixtures/prompts/example/select-passage.md | shasum -a 256`"""


def load(directory: Path) -> PromptRegistry:
    return PromptRegistry.load(directory)


def locked(registry: PromptRegistry) -> PromptLock:
    return extend_lock(registry, PromptLock({}))


# The repository -----------------------------------------------------------------------------------


def test_every_released_prompt_in_the_repository_matches_the_committed_lock() -> None:
    registry = load(REPOSITORY_ROOT / "prompts")
    lock = PromptLock.read(REPOSITORY_ROOT / "prompts" / "prompts.lock.json")

    assert compare_lock(registry, lock) == ()


def test_the_committed_lock_file_is_in_the_form_the_lock_script_writes() -> None:
    path = REPOSITORY_ROOT / "prompts" / "prompts.lock.json"

    assert PromptLock.read(path).to_json() == path.read_text(encoding="utf-8")


# Hashes -------------------------------------------------------------------------------------------


def test_a_body_hash_is_the_sha256_of_the_text_after_the_front_matter(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("p.md")

    [prompt] = load(prompt_dir).prompts

    assert prompt.body_sha256 == DEFAULT_BODY_SHA256


def test_the_sample_prompts_body_hash_matches_the_hand_computed_one() -> None:
    [prompt] = load(SAMPLE_PROMPTS).prompts

    assert prompt.body_sha256 == SAMPLE_BODY_SHA256


def test_a_body_with_windows_line_endings_hashes_like_the_same_body_with_unix_ones(prompt_dir: Path) -> None:
    text = (
        "---\nprompt_id: example.written\nversion: 1.0.0\nstatus: released\ntask_class: high_volume\n"
        f"output_schema: {SCHEMA}\nowner: v1-e05-model-router\n"
        "changelog:\n  - version: 1.0.0\n    date: 2026-10-17\n    summary: Written by a test.\n"
        "---\nChoose the passage that best supports this tag: {{ tag }}\n"
    )
    (prompt_dir / "p.md").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

    [prompt] = load(prompt_dir).prompts

    assert prompt.body_sha256 == DEFAULT_BODY_SHA256


# What comparison finds ----------------------------------------------------------------------------


def test_a_tree_that_matches_its_lock_has_no_problems(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    write_prompt("card/markup.md", prompt_id="card.markup", version="2.0.0")
    registry = load(prompt_dir)

    assert compare_lock(registry, locked(registry)) == ()


def test_editing_a_released_body_without_a_version_bump_is_found(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    write_prompt("card/select.md", prompt_id="card.select", body="Choose the best passage for: {{ tag }}\n")

    problems = compare_lock(load(prompt_dir), lock)

    assert [(p.kind, p.prompt_id, p.version) for p in problems] == [
        (LockProblemKind.CHANGED, "card.select", "1.0.0")
    ]
    assert DEFAULT_BODY_SHA256 in problems[0].detail


def test_a_one_character_edit_of_a_released_body_is_found(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    write_prompt(
        "card/select.md",
        prompt_id="card.select",
        body="Choose the passage that best supports this tag: {{ tag }}.\n",
    )

    [problem] = compare_lock(load(prompt_dir), lock)

    assert problem.kind is LockProblemKind.CHANGED


@pytest.mark.parametrize(
    ("field", "value"),
    [("output_schema", "debate_core.domain.model_contracts.ModelUsage"), ("task_class", "complex_reasoning")],
)
def test_changing_what_a_released_version_answers_or_how_it_is_routed_is_found(
    prompt_dir: Path, write_prompt: PromptWriter, field: str, value: str
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    write_prompt("card/select.md", prompt_id="card.select", **{field: value})

    [problem] = compare_lock(load(prompt_dir), lock)

    assert problem.kind is LockProblemKind.CHANGED
    assert field in problem.detail


def test_editing_the_owner_or_changelog_of_a_released_version_is_allowed(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    write_prompt(
        "card/select.md",
        front_matter=(
            "prompt_id: card.select\nversion: 1.0.0\nstatus: released\ntask_class: high_volume\n"
            f"output_schema: {SCHEMA}\nowner: v1-e06-another-area\n"
            "changelog:\n  - version: 1.0.0\n    date: 2026-10-18\n    summary: Reworded the history.\n"
        ),
    )

    assert compare_lock(load(prompt_dir), lock) == ()


def test_a_version_bump_is_a_new_lock_entry_beside_the_old_one(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    write_prompt(
        "card/select@1.1.0.md",
        prompt_id="card.select",
        version="1.1.0",
        body="Choose the best passage for: {{ tag }}\n",
    )
    registry = load(prompt_dir)

    assert [(p.kind, p.version) for p in compare_lock(registry, lock)] == [
        (LockProblemKind.UNLOCKED, "1.1.0")
    ]

    extended = extend_lock(registry, lock)

    assert set(extended.versions) == {("card.select", "1.0.0"), ("card.select", "1.1.0")}
    assert extended.versions[("card.select", "1.0.0")] == lock.versions[("card.select", "1.0.0")]
    assert compare_lock(registry, extended) == ()


def test_a_released_version_missing_from_the_lock_is_found(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")

    problems = compare_lock(load(prompt_dir), PromptLock({}))

    assert problems == (
        LockProblem(
            kind=LockProblemKind.UNLOCKED,
            prompt_id="card.select",
            version="1.0.0",
            detail=problems[0].detail,
        ),
    )
    assert "lock_prompts.py" in problems[0].detail


def test_a_locked_version_whose_file_is_gone_is_found(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    path = write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    path.unlink()

    [problem] = compare_lock(load(prompt_dir), lock)

    assert (problem.kind, problem.prompt_id, problem.version) == (
        LockProblemKind.MISSING,
        "card.select",
        "1.0.0",
    )


def test_a_locked_version_set_back_to_draft_is_found(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    write_prompt(
        "card/select.md", prompt_id="card.select", status="draft", body="Now free to edit {{ tag }}\n"
    )

    [problem] = compare_lock(load(prompt_dir), lock)

    assert problem.kind is LockProblemKind.UNRELEASED


def test_a_draft_may_change_freely_and_is_never_locked(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("card/select.md", prompt_id="card.select", status="draft")
    lock = locked(load(prompt_dir))
    write_prompt("card/select.md", prompt_id="card.select", status="draft", body="Rewritten {{ tag }}\n")
    registry = load(prompt_dir)

    assert lock.versions == {}
    assert compare_lock(registry, lock) == ()


def test_problems_are_reported_in_a_stable_order(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("b.md", prompt_id="b.prompt")
    write_prompt("a.md", prompt_id="a.prompt", version="1.10.0")
    write_prompt("a2.md", prompt_id="a.prompt", version="1.9.0")

    problems = compare_lock(load(prompt_dir), PromptLock({}))

    assert [(p.prompt_id, p.version) for p in problems] == [
        ("a.prompt", "1.9.0"),
        ("a.prompt", "1.10.0"),
        ("b.prompt", "1.0.0"),
    ]


# Extending the lock -------------------------------------------------------------------------------


def test_extending_the_lock_refuses_to_rehash_a_changed_body(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    write_prompt("card/select.md", prompt_id="card.select", body="Choose the best passage for: {{ tag }}\n")

    with pytest.raises(PromptLockError, match=r"card\.select@1\.0\.0"):
        extend_lock(load(prompt_dir), lock)


@pytest.mark.parametrize("change", ["deleted", "drafted"])
def test_extending_the_lock_refuses_to_drop_a_locked_version(
    prompt_dir: Path, write_prompt: PromptWriter, change: str
) -> None:
    path = write_prompt("card/select.md", prompt_id="card.select")
    lock = locked(load(prompt_dir))
    if change == "deleted":
        path.unlink()
    else:
        write_prompt("card/select.md", prompt_id="card.select", status="draft")

    with pytest.raises(PromptLockError, match=r"card\.select@1\.0\.0"):
        extend_lock(load(prompt_dir), lock)


# The lock file ------------------------------------------------------------------------------------


def test_the_lock_file_names_each_released_version_with_its_hash_schema_and_class(
    prompt_dir: Path, write_prompt: PromptWriter, tmp_path: Path
) -> None:
    write_prompt("card/select.md", prompt_id="card.select")
    write_prompt("card/draft.md", prompt_id="card.draft", status="draft")
    path = tmp_path / "prompts.lock.json"

    locked(load(prompt_dir)).write(path)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "format": 1,
        "prompts": {
            "card.select": {
                "1.0.0": {
                    "body_sha256": DEFAULT_BODY_SHA256,
                    "output_schema": SCHEMA,
                    "task_class": "high_volume",
                }
            }
        },
    }
    assert PromptLock.read(path).versions == {
        ("card.select", "1.0.0"): LockedVersion(DEFAULT_BODY_SHA256, SCHEMA, TaskClass.HIGH_VOLUME)
    }


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"format": 2, "prompts": {}}',
        '{"format": 1}',
        '{"format": 1, "prompts": {"card.select": {"1.0.0": {"body_sha256": "abc", '
        f'"output_schema": "{SCHEMA}", "task_class": "high_volume"}}}}}}}}',
        '{"format": 1, "prompts": {"card.select": {"1.0": {"body_sha256": "' + DEFAULT_BODY_SHA256 + '", '
        f'"output_schema": "{SCHEMA}", "task_class": "high_volume"}}}}}}}}',
        '{"format": 1, "prompts": {"card/select": {"1.0.0": {"body_sha256": "' + DEFAULT_BODY_SHA256 + '", '
        f'"output_schema": "{SCHEMA}", "task_class": "high_volume"}}}}}}}}',
        '{"format": 1, "prompts": {"card.select": {"1.0.0": {"body_sha256": "' + DEFAULT_BODY_SHA256 + '", '
        f'"output_schema": "{SCHEMA}", "task_class": "embeddings_please"}}}}}}}}',
    ],
    ids=[
        "not-json",
        "not-an-object",
        "unknown-format",
        "no-prompts",
        "short-hash",
        "bad-version",
        "bad-prompt-id",
        "bad-task-class",
    ],
)
def test_a_lock_file_that_is_not_a_valid_lock_is_refused_naming_it(tmp_path: Path, text: str) -> None:
    path = tmp_path / "prompts.lock.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(PromptRegistryError) as caught:
        PromptLock.read(path)

    assert caught.value.source == str(path)

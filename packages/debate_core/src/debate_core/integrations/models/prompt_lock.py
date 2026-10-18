"""The released-version lock: `prompts/prompts.lock.json` pins what each released prompt sends (ac4).

A released prompt version is immutable (v1-e05-t04-prompt-registry). The lock records, for each one,
the SHA-256 of its body and the output schema and task class it declares::

    {
      "format": 1,
      "prompts": {
        "card.select": {
          "1.0.0": {"body_sha256": "…", "output_schema": "…", "task_class": "complex_reasoning"}
        }
      }
    }

:func:`compare_lock` finds every way the prompt files and the lock disagree, as one
:class:`LockProblem` each:

* `changed`: a released version's body, schema or class was edited. Restore it, and make the
  change as a new version.
* `unreleased`: a released version was set back to `draft`. Set it back; a draft is a new version.
* `missing`: a released version's file is gone. Restore it; a released version is never deleted.
* `unlocked`: a version was released and not yet locked. Run `uv run scripts/lock_prompts.py`.

`packages/debate_core/tests/integrations/models/test_prompt_lock.py` fails on any of them for the
committed tree, so a released body edited in place fails CI. :func:`extend_lock`, which the script
runs, adds `unlocked` versions and refuses outright when any other problem exists, so relocking can
never launder an edit. `owner` and `changelog` are not locked: they describe a version without
changing what it sends.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from debate_core.domain.base import NonEmptyText, Sha256Hex
from debate_core.domain.model_contracts import TaskClass
from debate_core.domain.prompt_spec import PromptId, PromptVersion, prompt_version_key
from debate_core.integrations.models._recorded_files import write_pretty_json
from debate_core.integrations.models.errors import PromptLockError, PromptRegistryError
from debate_core.integrations.models.prompt_registry import PromptRegistry, RegisteredPrompt

__all__ = [
    "LOCK_FILE_NAME",
    "LOCK_FORMAT",
    "LockProblem",
    "LockProblemKind",
    "LockedVersion",
    "PromptLock",
    "compare_lock",
    "extend_lock",
]

LOCK_FILE_NAME: Final = "prompts.lock.json"
"""The lock's file name, in the prompt directory."""

LOCK_FORMAT: Final = 1
"""Version of the lock file's own shape."""

_LOCK_SCRIPT: Final = "uv run scripts/lock_prompts.py"


@dataclass(frozen=True, slots=True)
class LockedVersion:
    """What the lock pins for one released version."""

    body_sha256: str
    """SHA-256 of the body's UTF-8 text."""
    output_schema: str
    """The output schema the version declares."""
    task_class: TaskClass
    """The task class the version declares."""

    @classmethod
    def of(cls, prompt: RegisteredPrompt) -> LockedVersion:
        """What the lock would pin for `prompt` as it is now."""
        return cls(prompt.body_sha256, prompt.spec.output_schema, prompt.spec.task_class)


class LockProblemKind(StrEnum):
    """How a prompt file and the lock disagree (see the module's list)."""

    CHANGED = "changed"
    UNRELEASED = "unreleased"
    MISSING = "missing"
    UNLOCKED = "unlocked"


@dataclass(frozen=True, slots=True)
class LockProblem:
    """One disagreement between the prompt files and the lock."""

    kind: LockProblemKind
    prompt_id: str
    version: str
    detail: str
    """What is wrong and how to fix it, naming the prompt and version."""


class _LockEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    body_sha256: Sha256Hex
    output_schema: NonEmptyText
    task_class: TaskClass


class _LockDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal[1]
    prompts: dict[PromptId, dict[PromptVersion, _LockEntry]]


@dataclass(frozen=True, slots=True)
class PromptLock:
    """The lock file's content: every released version's pinned body hash, schema and class."""

    versions: Mapping[tuple[str, str], LockedVersion]
    """Keyed by `(prompt_id, version)`."""

    @classmethod
    def read(cls, path: Path) -> PromptLock:
        """The lock in `path`; a `PromptRegistryError` naming it when it is not a valid lock."""
        try:
            document = _LockDocument.model_validate_json(path.read_bytes())
        except OSError as error:
            raise PromptRegistryError(f"{path} could not be read: {error}", source=str(path)) from error
        except ValidationError as error:
            raise PromptRegistryError(
                f"{path} is not a valid prompt lock: {error}", source=str(path)
            ) from error
        return cls(
            {
                (prompt_id, version): LockedVersion(entry.body_sha256, entry.output_schema, entry.task_class)
                for prompt_id, entries in document.prompts.items()
                for version, entry in entries.items()
            }
        )

    def to_json(self) -> str:
        """The lock file's text: pretty-printed, keys sorted, one trailing newline."""
        return json.dumps(self._document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def write(self, path: Path) -> None:
        """Write the lock to `path`, replacing the file in one step."""
        write_pretty_json(path, self._document())

    def _document(self) -> dict[str, object]:
        prompts: dict[str, dict[str, dict[str, str]]] = {}
        for (prompt_id, version), locked in self.versions.items():
            prompts.setdefault(prompt_id, {})[version] = {
                "body_sha256": locked.body_sha256,
                "output_schema": locked.output_schema,
                "task_class": locked.task_class.value,
            }
        return {"format": LOCK_FORMAT, "prompts": prompts}


def compare_lock(registry: PromptRegistry, lock: PromptLock) -> tuple[LockProblem, ...]:
    """Every disagreement between `registry`'s prompts and `lock`, ordered by prompt id and version."""
    current = {(prompt.spec.prompt_id, prompt.spec.version): prompt for prompt in registry.prompts}
    released = {key for key, prompt in current.items() if prompt.spec.is_released}
    problems: list[LockProblem] = []
    for key in sorted(lock.versions.keys() | released, key=lambda key: (key[0], prompt_version_key(key[1]))):
        prompt_id, version = key
        label = f"{prompt_id}@{version}"
        locked = lock.versions.get(key)
        prompt = current.get(key)
        if locked is None:
            problems.append(
                LockProblem(
                    LockProblemKind.UNLOCKED,
                    prompt_id,
                    version,
                    f"{label} is released but not in the lock; record it with `{_LOCK_SCRIPT}`",
                )
            )
        elif prompt is None:
            problems.append(
                LockProblem(
                    LockProblemKind.MISSING,
                    prompt_id,
                    version,
                    f"{label} is in the lock but no prompt file defines it; a released version is never "
                    "deleted, so restore its file",
                )
            )
        elif not prompt.spec.is_released:
            problems.append(
                LockProblem(
                    LockProblemKind.UNRELEASED,
                    prompt_id,
                    version,
                    f"{label} is in the lock but {prompt.path} marks it draft; a released version stays "
                    "released, and further changes are a new version",
                )
            )
        else:
            changes = _changes(locked, LockedVersion.of(prompt))
            if changes:
                problems.append(
                    LockProblem(
                        LockProblemKind.CHANGED,
                        prompt_id,
                        version,
                        f"{label} in {prompt.path} has changed since it was released ({'; '.join(changes)}); "
                        "restore it and make the change as a new version",
                    )
                )
    return tuple(problems)


def extend_lock(registry: PromptRegistry, lock: PromptLock) -> PromptLock:
    """`lock` with every released version it lacks added; existing entries are never rewritten.

    Raises :class:`PromptLockError` when any released version has changed, gone missing or been set
    back to draft: rewriting its entry would hide exactly the edit the lock exists to catch.
    """
    problems = compare_lock(registry, lock)
    blocking = [problem for problem in problems if problem.kind is not LockProblemKind.UNLOCKED]
    if blocking:
        raise PromptLockError(
            "the lock was not updated, because released prompts no longer match it:\n"
            + "\n".join(f"  {problem.detail}" for problem in blocking)
        )
    current = {(prompt.spec.prompt_id, prompt.spec.version): prompt for prompt in registry.prompts}
    versions = dict(lock.versions)
    for problem in problems:
        key = (problem.prompt_id, problem.version)
        versions[key] = LockedVersion.of(current[key])
    return PromptLock(versions)


def _changes(locked: LockedVersion, now: LockedVersion) -> list[str]:
    """Each pinned value that differs, as `name locked X, now Y`."""
    changes: list[str] = []
    if locked.body_sha256 != now.body_sha256:
        changes.append(f"body_sha256 locked {locked.body_sha256}, now {now.body_sha256}")
    if locked.output_schema != now.output_schema:
        changes.append(f"output_schema locked {locked.output_schema}, now {now.output_schema}")
    if locked.task_class is not now.task_class:
        changes.append(f"task_class locked {locked.task_class.value}, now {now.task_class.value}")
    return changes

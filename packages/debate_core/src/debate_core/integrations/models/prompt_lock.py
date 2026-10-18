"""SKELETON for the red run: reads and writes the lock, finds no problem."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from debate_core.domain.model_contracts import TaskClass
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
LOCK_FORMAT: Final = 1


@dataclass(frozen=True, slots=True)
class LockedVersion:
    body_sha256: str
    output_schema: str
    task_class: TaskClass

    @classmethod
    def of(cls, prompt: RegisteredPrompt) -> LockedVersion:
        return cls(prompt.body_sha256, prompt.spec.output_schema, prompt.spec.task_class)


class LockProblemKind(StrEnum):
    CHANGED = "changed"
    UNRELEASED = "unreleased"
    MISSING = "missing"
    UNLOCKED = "unlocked"


@dataclass(frozen=True, slots=True)
class LockProblem:
    kind: LockProblemKind
    prompt_id: str
    version: str
    detail: str


@dataclass(frozen=True, slots=True)
class PromptLock:
    versions: Mapping[tuple[str, str], LockedVersion]

    @classmethod
    def read(cls, path: Path) -> PromptLock:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
        versions: dict[tuple[str, str], LockedVersion] = {}
        for prompt_id, entries in document["prompts"].items():
            for version, entry in entries.items():
                versions[(prompt_id, version)] = LockedVersion(
                    entry["body_sha256"], entry["output_schema"], TaskClass(entry["task_class"])
                )
        return cls(versions)

    def to_json(self) -> str:
        prompts: dict[str, dict[str, dict[str, str]]] = {}
        for (prompt_id, version), locked in sorted(self.versions.items()):
            prompts.setdefault(prompt_id, {})[version] = {
                "body_sha256": locked.body_sha256,
                "output_schema": locked.output_schema,
                "task_class": locked.task_class.value,
            }
        return json.dumps({"format": LOCK_FORMAT, "prompts": prompts}, indent=2, sort_keys=True) + "\n"

    def write(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")


def compare_lock(registry: PromptRegistry, lock: PromptLock) -> tuple[LockProblem, ...]:
    return ()


def extend_lock(registry: PromptRegistry, lock: PromptLock) -> PromptLock:
    versions = dict(lock.versions)
    for prompt in registry.prompts:
        if prompt.spec.is_released:
            versions[(prompt.spec.prompt_id, prompt.spec.version)] = LockedVersion.of(prompt)
    return PromptLock(versions)

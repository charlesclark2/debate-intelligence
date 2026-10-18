"""What a registered prompt says about itself: the front matter of a file under `prompts/`.

A prompt is a reviewed, versioned file in the repository, never text inside a Python module
(architecture proposal §10, v1-e05-t04-prompt-registry). Each file is one version of one prompt: a
YAML front matter block that this module's :class:`PromptSpec` validates, then a Jinja2 template
body. `prompts/README.md` documents the format, and
:mod:`debate_core.integrations.models.prompt_registry` loads, compiles and renders the files.

This module is the domain half: the shape and the rules a prompt's identity must keep. Reading
files and compiling templates is the registry's business.

* A prompt id names the fixture and cassette directories of v1-e05-t03-fake-replay-models, so it is
  letters, digits, `.`, `_` and `-`, starting with a letter or digit (:data:`PROMPT_ID_PATTERN`).
* A version is `MAJOR.MINOR.PATCH` (:func:`prompt_version_key`).
* A released version is immutable. Its body, schema and task class are pinned by
  `prompts/prompts.lock.json`, and a change to any of them is a new version.
"""

from __future__ import annotations

import datetime
import re
from enum import StrEnum
from typing import Annotated, Final

from pydantic import AfterValidator, Field, ValidationInfo, field_validator

from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.model_contracts import TaskClass

__all__ = [
    "PROMPT_ID_PATTERN",
    "PROMPT_VERSION_PATTERN",
    "ChangelogEntry",
    "PromptId",
    "PromptSpec",
    "PromptStatus",
    "PromptVersion",
    "PromptVersionKey",
    "is_prompt_id",
    "prompt_version_key",
]

PROMPT_ID_PATTERN: Final = r"[A-Za-z0-9][A-Za-z0-9._-]*"
"""A prompt id, matched in full: a directory name on every platform, with no separator and no leading dot."""

PROMPT_VERSION_PATTERN: Final = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
"""A prompt version, matched in full: `MAJOR.MINOR.PATCH` without leading zeros.

Semantic versioning's core triple only. A pre-release or build suffix is refused rather than
ordered: `latest` must have one answer, and a prompt that is not ready is a `draft`, not `-rc.1`.
"""

_OUTPUT_SCHEMA_PATTERN: Final = r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+"
"""A dotted path with a module and at least one name: what `ModelRequest.build` writes for a schema."""

type PromptVersionKey = tuple[int, int, int]
"""A version as numbers, so that `1.10.0` sorts after `1.9.0`."""


def is_prompt_id(text: str) -> bool:
    """Whether `text` may be a prompt id, and so a fixture or cassette directory name."""
    return re.fullmatch(PROMPT_ID_PATTERN, text) is not None


def prompt_version_key(version: str) -> PromptVersionKey:
    """`version` as `(major, minor, patch)`; a `ValueError` when it is not `MAJOR.MINOR.PATCH`."""
    match = re.fullmatch(PROMPT_VERSION_PATTERN, version)
    if match is None:
        raise ValueError(f"{version!r} is not a MAJOR.MINOR.PATCH version such as 1.0.0")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _require_prompt_id(text: str) -> str:
    if not is_prompt_id(text):
        raise ValueError(
            f"prompt id {text!r} cannot name a fixture directory; use letters, digits, '.', '_' and '-', "
            "starting with a letter or digit"
        )
    return text


def _require_version(text: str) -> str:
    prompt_version_key(text)
    return text


PromptId = Annotated[str, AfterValidator(_require_prompt_id)]
"""A prompt id: :data:`PROMPT_ID_PATTERN`, matched in full."""

PromptVersion = Annotated[str, AfterValidator(_require_version)]
"""A prompt version: `MAJOR.MINOR.PATCH`."""


class PromptStatus(StrEnum):
    """Whether a prompt version may still change."""

    DRAFT = "draft"
    """Being written. Its body may change, and `latest` never resolves to it."""

    RELEASED = "released"
    """Fixed for good. Its body, schema and task class are in the lock file, and a change is a new version."""


class ChangelogEntry(DomainModel):
    """One line of a prompt's history: which version, when, and what changed."""

    version: PromptVersion = Field(description="The version this entry describes.")
    date: datetime.date = Field(description="When that version was written.")
    summary: NonEmptyText = Field(description="What changed, in a sentence.")


class PromptSpec(DomainModel):
    """The front matter of one prompt file: which prompt, which version, and what it must answer."""

    prompt_id: PromptId = Field(
        description="The prompt's identifier; it names fixture and cassette directories."
    )
    version: PromptVersion = Field(description="This version of the prompt, `MAJOR.MINOR.PATCH`.")
    status: PromptStatus = Field(description="`draft` while it may change, `released` once it may not.")
    task_class: TaskClass = Field(description="The generative task class the prompt is written for.")
    output_schema: str = Field(
        pattern=_OUTPUT_SCHEMA_PATTERN,
        description="Dotted path of the Pydantic model the answer must validate as, `module.QualifiedName`.",
    )
    owner: NonEmptyText = Field(
        description="The epic or area that maintains the prompt, such as `v1-e05-model-router`; not a person."
    )
    changelog: tuple[ChangelogEntry, ...] = Field(
        min_length=1, description="The prompt's history, one entry per version, this one included."
    )

    @field_validator("task_class")
    @classmethod
    def _require_generative_class(cls, task_class: TaskClass) -> TaskClass:
        if not task_class.is_generative:
            raise ValueError(
                f"task class {task_class.value!r} does not generate output, so it takes no prompt"
            )
        return task_class

    @field_validator("changelog")
    @classmethod
    def _require_own_changelog_entry(
        cls, changelog: tuple[ChangelogEntry, ...], info: ValidationInfo
    ) -> tuple[ChangelogEntry, ...]:
        versions = [entry.version for entry in changelog]
        if len(set(versions)) != len(versions):
            raise ValueError("each version may have only one changelog entry")
        own_version = info.data.get("version")
        if own_version is not None and own_version not in versions:
            raise ValueError(f"there is no changelog entry for this file's own version, {own_version}")
        return changelog

    @property
    def version_key(self) -> PromptVersionKey:
        """This version as numbers, for ordering."""
        return prompt_version_key(self.version)

    @property
    def is_released(self) -> bool:
        """Whether this version is fixed for good."""
        return self.status is PromptStatus.RELEASED

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
from enum import StrEnum
from typing import Final

from pydantic import Field

from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.model_contracts import TaskClass

__all__ = [
    "PROMPT_ID_PATTERN",
    "PROMPT_VERSION_PATTERN",
    "ChangelogEntry",
    "PromptSpec",
    "PromptStatus",
    "PromptVersionKey",
    "prompt_version_key",
]

PROMPT_ID_PATTERN: Final = r"[A-Za-z0-9][A-Za-z0-9._-]*"
"""A prompt id, matched in full: a directory name on every platform, with no separator and no leading dot."""

PROMPT_VERSION_PATTERN: Final = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
"""A prompt version, matched in full: `MAJOR.MINOR.PATCH` without leading zeros."""

type PromptVersionKey = tuple[int, int, int]
"""A version as numbers, so that `1.10.0` sorts after `1.9.0`."""


def prompt_version_key(version: str) -> PromptVersionKey:
    """`version` as `(major, minor, patch)`; a `ValueError` when it is not `MAJOR.MINOR.PATCH`."""
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


class PromptStatus(StrEnum):
    """Whether a prompt version may still change."""

    DRAFT = "draft"
    """Being written. Its body may change, and `latest` never resolves to it."""

    RELEASED = "released"
    """Fixed for good. Its body, schema and task class are in the lock file, and a change is a new version."""


class ChangelogEntry(DomainModel):
    """One line of a prompt's history: which version, when, and what changed."""

    version: str = Field(description="The version this entry describes.")
    date: datetime.date = Field(description="When that version was written.")
    summary: NonEmptyText = Field(description="What changed, in a sentence.")


class PromptSpec(DomainModel):
    """The front matter of one prompt file: which prompt, which version, and what it must answer."""

    prompt_id: str = Field(description="The prompt's identifier; it names fixture and cassette directories.")
    version: str = Field(description="This version of the prompt, `MAJOR.MINOR.PATCH`.")
    status: PromptStatus = Field(description="`draft` while it may change, `released` once it may not.")
    task_class: TaskClass = Field(description="The generative task class the prompt is written for.")
    output_schema: str = Field(
        description="Dotted path of the Pydantic model the answer must validate as, `module.QualifiedName`."
    )
    owner: NonEmptyText = Field(
        description="The epic or area that maintains the prompt, such as `v1-e05-model-router`; never a person."
    )
    changelog: tuple[ChangelogEntry, ...] = Field(description="The prompt's history, one entry per version.")

    @property
    def version_key(self) -> PromptVersionKey:
        """This version as numbers, for ordering."""
        return prompt_version_key(self.version)

    @property
    def is_released(self) -> bool:
        """Whether this version is fixed for good."""
        return self.status is PromptStatus.RELEASED

"""SKELETON for the red run: loads and renders the happy path, refuses nothing."""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml
from jinja2 import Template
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel, JsonValue

from debate_core.domain.model_contracts import ModelPrompt, RenderedPrompt
from debate_core.domain.prompt_spec import PromptSpec
from debate_core.integrations.models.errors import PromptRegistryError, UnknownPromptError

__all__ = [
    "DEFAULT_PROMPT_DIRECTORY",
    "LATEST",
    "SYSTEM_MARKER",
    "USER_MARKER",
    "PromptRegistry",
    "RegisteredPrompt",
    "load_prompt_file",
    "resolve_schema",
]

DEFAULT_PROMPT_DIRECTORY: Final = Path("prompts")
LATEST: Final = "latest"
SYSTEM_MARKER: Final = "<!-- system -->"
USER_MARKER: Final = "<!-- user -->"
_FENCE: Final = "---"

_ENVIRONMENT = SandboxedEnvironment()


@dataclass(frozen=True, slots=True)
class RegisteredPrompt:
    spec: PromptSpec
    path: Path
    body: str
    schema: type[BaseModel]
    _system: Template | None
    _user: Template

    @property
    def body_sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    @property
    def variables(self) -> frozenset[str]:
        return frozenset()

    def render(self, variables: Mapping[str, JsonValue]) -> RenderedPrompt:
        system = self._system.render(dict(variables)).strip() if self._system is not None else None
        return RenderedPrompt(user=self._user.render(dict(variables)).strip(), system=system)


class PromptRegistry:
    def __init__(self, prompts: Iterable[RegisteredPrompt]) -> None:
        self._prompts: dict[tuple[str, str], RegisteredPrompt] = {}
        for prompt in prompts:
            self._prompts[(prompt.spec.prompt_id, prompt.spec.version)] = prompt

    @classmethod
    def load(cls, directory: Path) -> PromptRegistry:
        paths = sorted(path for path in directory.rglob("*.md") if path.name != "README.md")
        return cls(load_prompt_file(path) for path in paths)

    @property
    def prompts(self) -> tuple[RegisteredPrompt, ...]:
        return tuple(self._prompts[key] for key in sorted(self._prompts))

    def get(self, prompt_id: str, version: str = LATEST) -> RegisteredPrompt:
        if version == LATEST:
            versions = [v for (pid, v), p in self._prompts.items() if pid == prompt_id and p.spec.is_released]
            if not versions:
                raise UnknownPromptError(f"no released version of {prompt_id}")
            version = max(versions)
        try:
            return self._prompts[(prompt_id, version)]
        except KeyError:
            raise UnknownPromptError(f"no prompt {prompt_id}@{version}") from None

    def prompt(
        self, prompt_id: str, variables: Mapping[str, JsonValue] | None = None, *, version: str = LATEST
    ) -> ModelPrompt:
        registered = self.get(prompt_id, version)
        return ModelPrompt(
            prompt_id=prompt_id, prompt_version=registered.spec.version, variables=dict(variables or {})
        )

    def render(self, prompt: ModelPrompt) -> RenderedPrompt:
        return self.get(prompt.prompt_id, prompt.prompt_version).render(prompt.variables)


def load_prompt_file(path: Path) -> RegisteredPrompt:
    text = path.read_text(encoding="utf-8")
    _, front, body = text.split(f"{_FENCE}\n", 2)
    document: Any = yaml.safe_load(front)
    spec = PromptSpec.model_validate(document)
    if SYSTEM_MARKER in body:
        system_text, user_text = body.split(SYSTEM_MARKER, 1)[1].split(USER_MARKER, 1)
        system: Template | None = _ENVIRONMENT.from_string(system_text)
    else:
        system, user_text = None, body
    return RegisteredPrompt(
        spec=spec,
        path=path,
        body=body,
        schema=resolve_schema(spec.output_schema),
        _system=system,
        _user=_ENVIRONMENT.from_string(user_text),
    )


def resolve_schema(dotted_path: str) -> type[BaseModel]:
    module_name, _, name = dotted_path.rpartition(".")
    try:
        return getattr(importlib.import_module(module_name), name)
    except (ImportError, AttributeError) as error:
        raise PromptRegistryError(str(error)) from error

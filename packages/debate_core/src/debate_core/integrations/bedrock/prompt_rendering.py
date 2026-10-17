"""How the Bedrock adapter gets the words of a prompt: from a renderer it is given, never its own.

A :class:`~debate_core.domain.model_contracts.ModelPrompt` names a registered prompt by id and
version and carries its variables; it holds no text. Turning it into the system and user text a
model reads is the prompt registry's job (v1-e05-t04-prompt-registry), which is not built yet. So
the adapter takes a :data:`PromptRenderer`, and until the registry exists the only one shipped is
:func:`refuse_unregistered_prompt`, which fails closed. Prompt text is never written into an
adapter, so a production call can only ever send a registered, versioned prompt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from debate_core.application.settings import ConfigurationError
from debate_core.domain.model_contracts import ModelPrompt

__all__ = ["PromptRenderer", "RenderedPrompt", "refuse_unregistered_prompt"]


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """The text one call sends: an optional system prompt and the user turn."""

    user: str
    system: str | None = None

    def __post_init__(self) -> None:
        if not self.user.strip():
            raise ValueError("a rendered prompt needs a user turn")


type PromptRenderer = Callable[[ModelPrompt], RenderedPrompt]
"""Renders a registered prompt with its variables. The prompt registry provides one (t04)."""


def refuse_unregistered_prompt(prompt: ModelPrompt) -> RenderedPrompt:
    """The renderer a Bedrock router has until it is given the registry's: it renders nothing.

    Raises `ConfigurationError` naming the prompt, so a `generate_structured` call made before
    v1-e05-t04-prompt-registry wires its renderer in stops before anything is sent or billed.
    """
    raise ConfigurationError(
        f"no prompt renderer is configured, so prompt {prompt.prompt_id}@{prompt.prompt_version} cannot be "
        "sent to Bedrock; the prompt registry (v1-e05-t04-prompt-registry) provides one",
        field="models.provider",
    )

"""How the Bedrock adapter gets the words of a prompt: from a renderer it is given, never its own.

A :class:`~debate_core.domain.model_contracts.ModelPrompt` names a registered prompt by id and
version and carries its variables; it holds no text. Turning it into the system and user text a
model reads, a :class:`~debate_core.domain.model_contracts.RenderedPrompt`, is the prompt registry's
job (v1-e05-t04-prompt-registry). So the adapter takes a :data:`PromptRenderer`, and
:func:`~debate_core.integrations.bedrock.bedrock_router_factory` gives it
:meth:`PromptRegistry.render <debate_core.integrations.models.prompt_registry.PromptRegistry.render>`.

A router built without one gets :func:`refuse_unregistered_prompt`, which fails closed. Prompt text
is never written into an adapter, so a production call can only ever send a registered, versioned
prompt.
"""

from __future__ import annotations

from collections.abc import Callable

from debate_core.application.settings import ConfigurationError
from debate_core.domain.model_contracts import ModelPrompt, RenderedPrompt

__all__ = ["PromptRenderer", "refuse_unregistered_prompt"]


type PromptRenderer = Callable[[ModelPrompt], RenderedPrompt]
"""Renders a registered prompt with its variables: `PromptRegistry.render`."""


def refuse_unregistered_prompt(prompt: ModelPrompt) -> RenderedPrompt:
    """The renderer of a Bedrock router that was given none: it renders nothing.

    Raises `ConfigurationError` naming the prompt, so a `generate_structured` call on a router built
    without the prompt registry stops before anything is sent or billed.
    """
    raise ConfigurationError(
        f"no prompt renderer is configured, so prompt {prompt.prompt_id}@{prompt.prompt_version} cannot be "
        "sent to Bedrock; build the router with bedrock_router_factory(registry), which renders from the "
        "prompt registry (v1-e05-t04-prompt-registry)",
        field="models.provider",
    )

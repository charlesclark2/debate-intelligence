"""The Amazon Bedrock adapter: the production `ModelRouter` (v1-e05-t02-bedrock-adapter).

The only package in `debate_core` besides `integrations.s3` that may import boto3, and the only
one that imports it for Bedrock. boto3 is the `aws` extra (`debate-core[aws]`), not a dependency
of `debate-core` itself, so a student without AWS access can install the CLI and run it on the
fake router or on replayed cassettes, neither of which builds this adapter.

Importing this package therefore imports no AWS SDK. :func:`bedrock_model_router` is where boto3
is first needed, and where its absence is reported, as :class:`BedrockNotInstalledError` naming
the extra. :func:`bedrock_router_factory` binds it to the prompt registry's renderer
(v1-e05-t04-prompt-registry), and is the `real_router` a composition root passes to
:func:`~debate_core.integrations.models.factory.build_model_router`, which makes record and live
mode call Bedrock::

    registry = PromptRegistry.load(repository_root / DEFAULT_PROMPT_DIRECTORY)
    router = build_model_router(settings, mode=mode, real_router=bedrock_router_factory(registry))

`bedrock_model_router` on its own builds a router with no renderer, which embeds and reranks but
refuses every structured call before sending it.

The router itself, :class:`~debate_core.integrations.bedrock.router.BedrockModelRouter`, is
imported from :mod:`debate_core.integrations.bedrock.router`, which needs boto3.
"""

from __future__ import annotations

import functools
import importlib

from debate_core.application.ports.model_router import ModelRouter
from debate_core.integrations.bedrock.errors import AWS_EXTRA, BedrockNotInstalledError
from debate_core.integrations.bedrock.prompt_rendering import PromptRenderer, refuse_unregistered_prompt
from debate_core.integrations.models.factory import RealRouterFactory
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.routing_policy import RoutingPolicy

__all__ = [
    "AWS_EXTRA",
    "BedrockNotInstalledError",
    "PromptRenderer",
    "bedrock_model_router",
    "bedrock_router_factory",
    "refuse_unregistered_prompt",
    "require_aws_sdk",
]


def require_aws_sdk() -> None:
    """Raise :class:`BedrockNotInstalledError` unless boto3 and botocore can be imported."""
    try:
        for name in ("boto3", "botocore"):
            importlib.import_module(name)
    except ImportError as error:
        raise BedrockNotInstalledError() from error


def bedrock_model_router(
    policy: RoutingPolicy,
    *,
    aws_profile: str | None = None,
    render_prompt: PromptRenderer = refuse_unregistered_prompt,
) -> ModelRouter:
    """The Bedrock router for a validated routing policy, signed with `aws_profile`; a `RealRouterFactory`.

    `build_model_router` passes `aws_profile` from `models.aws_profile` (v1-e05-t08). Raises
    :class:`BedrockNotInstalledError`, a configuration error naming `debate-core[aws]`, when boto3
    is not installed. Nothing is sent and no credential is read until the first call.
    """
    require_aws_sdk()
    from debate_core.integrations.bedrock.router import BedrockModelRouter  # noqa: PLC0415 - needs boto3

    return BedrockModelRouter(policy, aws_profile=aws_profile, render_prompt=render_prompt)


def bedrock_router_factory(registry: PromptRegistry) -> RealRouterFactory:
    """The `real_router` for `build_model_router`: Bedrock, sending each prompt as `registry` renders it.

    This is what lets record and live mode send a structured call (v1-e05-t04-prompt-registry).
    The profile is not bound here: `build_model_router` passes `models.aws_profile` when it calls
    the factory. The SDK is still not imported until then.
    """
    return functools.partial(bedrock_model_router, render_prompt=registry.render)

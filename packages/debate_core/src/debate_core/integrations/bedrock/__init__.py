"""The Amazon Bedrock adapter: the production `ModelRouter` (v1-e05-t02-bedrock-adapter).

The only package in `debate_core` besides `integrations.s3` that may import boto3, and the only
one that imports it for Bedrock. boto3 is the `aws` extra (`debate-core[aws]`), not a dependency
of `debate-core` itself, so a student without AWS access can install the CLI and run it on the
fake router or on replayed cassettes, neither of which builds this adapter.

Importing this package therefore imports no AWS SDK. :func:`bedrock_model_router` is where boto3
is first needed, and where its absence is reported, as :class:`BedrockNotInstalledError` naming
the extra. It is the `real_router` a composition root passes to
:func:`~debate_core.integrations.models.factory.build_model_router`, which makes record and live
mode call Bedrock::

    router = build_model_router(settings, mode=mode, real_router=bedrock_model_router)

The router itself, :class:`~debate_core.integrations.bedrock.router.BedrockModelRouter`, is
imported from :mod:`debate_core.integrations.bedrock.router`, which needs boto3.
"""

from __future__ import annotations

import importlib

from debate_core.application.ports.model_router import ModelRouter
from debate_core.integrations.bedrock.errors import AWS_EXTRA, BedrockNotInstalledError
from debate_core.integrations.bedrock.prompt_rendering import (
    PromptRenderer,
    RenderedPrompt,
    refuse_unregistered_prompt,
)
from debate_core.integrations.models.routing_policy import RoutingPolicy

__all__ = [
    "AWS_EXTRA",
    "BedrockNotInstalledError",
    "PromptRenderer",
    "RenderedPrompt",
    "bedrock_model_router",
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
    policy: RoutingPolicy, *, render_prompt: PromptRenderer = refuse_unregistered_prompt
) -> ModelRouter:
    """The Bedrock router for a validated routing policy; a `RealRouterFactory`.

    Raises :class:`BedrockNotInstalledError`, a configuration error naming `debate-core[aws]`,
    when boto3 is not installed. Nothing is sent and no credential is read until the first call.
    """
    require_aws_sdk()
    from debate_core.integrations.bedrock.router import BedrockModelRouter  # noqa: PLC0415 - needs boto3

    return BedrockModelRouter(policy, render_prompt=render_prompt)

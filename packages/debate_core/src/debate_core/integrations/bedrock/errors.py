"""The Bedrock adapter's own failure: the AWS SDK it needs is not installed.

Every failure of a model *call* is one of the port's errors in
:mod:`debate_core.application.errors`. This module holds the one failure that comes before any
call, and it imports nothing from AWS, so it can be raised where boto3 is missing.
"""

from __future__ import annotations

from typing import Final

from debate_core.application.settings import ConfigurationError

__all__ = ["AWS_EXTRA", "BedrockNotInstalledError"]

AWS_EXTRA: Final = "debate-core[aws]"
"""The extra that installs boto3. The CLI depends on it; a bare `debate-core` does not have it."""


class BedrockNotInstalledError(ConfigurationError):
    """`models.provider` is `bedrock` and a real call was asked for, but boto3 is not installed.

    A configuration error, because the cure is a setting or an install, never a retry: install
    the extra, or set `models.provider` to `fake` (which needs no AWS SDK) or replay recorded
    cassettes, which never builds this adapter (`debate_core.integrations.models.factory`).
    """

    def __init__(self) -> None:
        super().__init__(
            f"models.provider is bedrock, and calling Bedrock needs boto3, which is not installed: "
            f"install {AWS_EXTRA} (`uv sync --all-packages --extra aws`, or "
            f"`pip install '{AWS_EXTRA}'`), or set models.provider to fake",
            field="models.provider",
        )

"""What the offline model routers raise when a recorded answer is missing, unusable or not allowed.

None of these is a :class:`~debate_core.application.errors.ProviderError`, on purpose. A provider
error is a normal condition that a caller may absorb, retry or report as a partial result. A missing
fixture is a test or an eval asking a question nobody recorded an answer to, and the only correct
response is to stop and say which answer is missing. Nothing falls back to a real model
(v1-e05-t03-fake-replay-models).
"""

from __future__ import annotations

from pathlib import Path

from debate_core.application.errors import DomainError
from debate_core.application.settings import ConfigurationError

__all__ = ["FixtureFileError", "MissingFixtureError", "ModelModeError", "RecordingRefusedError"]


class MissingFixtureError(DomainError):
    """No recorded answer exists for a call the fake or replay router was asked to make (ac3).

    Names the call by its prompt id and version (for `embed` and `rerank`, which have no prompt,
    by the call's name) and by its fixture key, and says where the answer was looked for.
    """

    def __init__(
        self,
        *,
        call: str,
        key: str,
        location: Path,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
        detail: str | None = None,
        hint: str,
    ) -> None:
        self.call = call
        """`generate_structured`, `embed` or `rerank`."""
        self.key = key
        """The fixture key the answer would be filed under."""
        self.location = location
        """The file the answer was looked for at."""
        self.prompt_id = prompt_id
        """The prompt the call ran, for a `generate_structured` call."""
        self.prompt_version = prompt_version
        """That prompt's version."""
        what = f"prompt {prompt_id}@{prompt_version}" if prompt_id is not None else f"{call} call"
        because = f" ({detail})" if detail else ""
        super().__init__(f"no recorded answer for {what}, fixture key {key}, at {location}{because}. {hint}")


class FixtureFileError(DomainError):
    """A fixture or cassette file exists but cannot be served: not JSON, the wrong shape, or misfiled."""

    def __init__(self, location: Path, reason: str) -> None:
        self.location = location
        """The file that could not be served."""
        self.reason = reason
        """What is wrong with it."""
        super().__init__(f"{location} cannot be served as a recorded model answer: {reason}")


class ModelModeError(ConfigurationError):
    """`DEBATE_MODEL_MODE` or `--model-mode` holds something other than record, replay or live."""


class RecordingRefusedError(ConfigurationError):
    """Record mode was asked for where it may not run: in CI (`CI=true`), or without a real router."""

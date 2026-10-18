"""Which `ModelRouter` a run gets, decided by settings and the model mode, never by code.

A composition root (the CLI's container, an eval runner, the shared `model_router` pytest fixture)
calls :func:`build_model_router` and gets a router typed as the port. Two inputs decide which, and
each has exactly one control (v1-e05-t03-fake-replay-models, ac5):

| `models.provider` | Mode (`--model-mode`, else `DEBATE_MODEL_MODE`, else replay) | Router |
|---|---|---|
| `fake` | not read | `FakeModelRouter`, over the committed fixtures |
| `bedrock` | `replay` | `RecordReplayModelRouter` serving cassettes, holding no real router |
| `bedrock` | `record` | the same, recording the real router's calls; refused when `CI=true` |
| `bedrock` | `live` | the same, passing the real router's calls through |

The `test` profile sets `fake`; dev and prod leave the default, `bedrock`, so an unconfigured run of
either replays and reaches no model. For a real provider the routing file is loaded and validated
first (:meth:`~debate_core.integrations.models.routing_policy.RoutingPolicy.from_settings`), so a
bad file fails before any router exists.

The real router is the Bedrock adapter (`v1-e05-t02-bedrock-adapter`). This module may not import
it, because nothing in `debate_core.integrations.models` may depend on the AWS SDK, so a
composition root passes it in: `real_router=debate_core.integrations.bedrock.bedrock_model_router`.
Without one, record and live fail with a configuration error naming `models.provider`. Nothing here
falls back to a real model, or from one mode to another.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import ConfigurationError, Settings, find_repository_root
from debate_core.domain.model_contracts import ModelProvider
from debate_core.integrations.models.fake_router import DEFAULT_FIXTURE_DIRECTORY, FakeModelRouter
from debate_core.integrations.models.model_mode import ModelMode, resolve_model_mode
from debate_core.integrations.models.record_replay import (
    DEFAULT_CASSETTE_DIRECTORY,
    RecordReplayModelRouter,
    refuse_recording_in_ci,
)
from debate_core.integrations.models.routing_policy import RoutingPolicy

__all__ = ["RealRouterFactory", "build_model_router"]

type RealRouterFactory = Callable[[RoutingPolicy], ModelRouter]
"""Builds the real router for a validated routing policy (`integrations.bedrock.bedrock_model_router`)."""


def build_model_router(
    settings: Settings,
    *,
    mode: str | ModelMode | None = None,
    environ: Mapping[str, str] | None = None,
    real_router: RealRouterFactory | None = None,
    repository_root: Path | None = None,
    fixture_dir: Path | None = None,
    cassette_dir: Path | None = None,
    clock: Clock | None = None,
) -> ModelRouter:
    """The router `settings` and the model mode select.

    `mode` is the `--model-mode` option's value when the program has one (`None` when it was not
    given); `environ` is where `DEBATE_MODEL_MODE` and `CI` are read, the process environment by
    default. `fixture_dir` and `cassette_dir` default to the committed directories under
    `repository_root`, itself the checkout around the working directory by default. `clock` dates
    the fake's responses.

    Raises :class:`~debate_core.application.ports.model_router.RoutingConfigError` for a bad
    routing file, :class:`~debate_core.integrations.models.errors.ModelModeError` for a bad mode,
    :class:`~debate_core.integrations.models.errors.RecordingRefusedError` for record mode in CI,
    and `ConfigurationError` when record or live has no real router to call.
    """
    if settings.models.provider is ModelProvider.FAKE:
        directory = fixture_dir or _committed(DEFAULT_FIXTURE_DIRECTORY, repository_root)
        return FakeModelRouter(directory, clock=clock)

    policy = RoutingPolicy.from_settings(settings)
    model_mode = resolve_model_mode(mode, environ=environ)
    cassettes = cassette_dir or _committed(DEFAULT_CASSETTE_DIRECTORY, repository_root)
    if model_mode is ModelMode.REPLAY:
        return RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=cassettes)
    if model_mode is ModelMode.RECORD:
        refuse_recording_in_ci(environ)
    if real_router is None:
        raise ConfigurationError(
            f"{model_mode.value} mode needs the {settings.models.provider.value} model router passed in as "
            "real_router (debate_core.integrations.bedrock.bedrock_model_router), and none was; replay, "
            "or set models.provider to fake",
            field="models.provider",
        )
    return RecordReplayModelRouter(
        real_router(policy), mode=model_mode, cassette_dir=cassettes, environ=environ
    )


def _committed(relative: Path, repository_root: Path | None) -> Path:
    """`relative` under the repository root, or a `ConfigurationError` outside a checkout."""
    root = repository_root or find_repository_root()
    if root is None:
        raise ConfigurationError(
            f"{relative} is read from a source checkout, and this run is not in one; pass its directory",
            field="models.provider",
        )
    return root / relative

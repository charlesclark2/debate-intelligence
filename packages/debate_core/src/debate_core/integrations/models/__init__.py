"""Model routing, and the offline routers that keep tests and evals from ever reaching a model.

:class:`~debate_core.integrations.models.routing_policy.RoutingPolicy` reads a
`config/model_routing.*.yaml` file and resolves a call into the route it takes
(v1-e05-t01-model-router-port). v1-e05-t03-fake-replay-models adds the routers that answer without a
model:

* :class:`~debate_core.integrations.models.fake_router.FakeModelRouter` answers from hand-written
  fixtures keyed by :func:`~debate_core.integrations.models.fixture_key.fixture_key`, and computes
  embeddings and rerank scores.
* :class:`~debate_core.integrations.models.record_replay.RecordReplayModelRouter` records a real
  router's calls as cassettes, replays them, or passes calls through, as
  :func:`~debate_core.integrations.models.model_mode.resolve_model_mode` says.
* :func:`~debate_core.integrations.models.factory.build_model_router` picks one from settings and
  the mode.

The Bedrock adapter has its own subpackage, because nothing in this one may depend on the AWS SDK.
"""

from debate_core.integrations.models.errors import (
    FixtureFileError,
    MissingFixtureError,
    ModelModeError,
    RecordingRefusedError,
)
from debate_core.integrations.models.factory import RealRouterFactory, build_model_router
from debate_core.integrations.models.fake_router import FakeModelRouter, FixtureDirectory
from debate_core.integrations.models.fixture_key import embedding_key, fixture_key, rerank_key
from debate_core.integrations.models.model_mode import (
    MODEL_MODE_OPTION,
    MODEL_MODE_VARIABLE,
    ModelMode,
    add_model_mode_option,
    resolve_model_mode,
)
from debate_core.integrations.models.record_replay import CassetteDirectory, RecordReplayModelRouter
from debate_core.integrations.models.routing_policy import ROUTING_SCHEMA_VERSION, ModelRoute, RoutingPolicy

__all__ = [
    "MODEL_MODE_OPTION",
    "MODEL_MODE_VARIABLE",
    "ROUTING_SCHEMA_VERSION",
    "CassetteDirectory",
    "FakeModelRouter",
    "FixtureDirectory",
    "FixtureFileError",
    "MissingFixtureError",
    "ModelMode",
    "ModelModeError",
    "ModelRoute",
    "RealRouterFactory",
    "RecordReplayModelRouter",
    "RecordingRefusedError",
    "RoutingPolicy",
    "add_model_mode_option",
    "build_model_router",
    "embedding_key",
    "fixture_key",
    "rerank_key",
    "resolve_model_mode",
]

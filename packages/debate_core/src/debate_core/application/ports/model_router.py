"""The single door every model call in the platform goes through.

A use case asks for a :class:`~debate_core.domain.model_contracts.TaskClass` of work, never for a
model. Which model, region and inference profile answer is the routing file's decision
(`config/model_routing.*.yaml`, read by
:class:`~debate_core.integrations.models.routing_policy.RoutingPolicy`), and the answer comes back
with the :class:`~debate_core.domain.model_contracts.ResolvedRoute` it took, so every generated
artifact can name the model behind it (architecture proposal §10, ADR-0005).

Three calls, one per kind of work:

* :meth:`ModelRouter.generate_structured` runs a registered prompt and returns an instance of the
  Pydantic schema the caller named. There is no call that returns free-form text.
* :meth:`ModelRouter.embed` turns texts into vectors (the `embeddings` class).
* :meth:`ModelRouter.rerank` orders documents by relevance to a query (the `rerank` class).

**A model never supplies evidence text.** A schema may ask a model for paragraph ids, offsets,
labels, confidences and explanations: *which* passage to cut and *why*. The quotation itself is
always sliced out of the stored snapshot afterwards, and a schema field meant to hold quoted
evidence is a defect (architecture proposal §8, ADR-0006). Rerank results name documents by
position for the same reason.

Implementations: the Bedrock adapter (v1-e05-t02-bedrock-adapter), the fixture-keyed
`FakeModelRouter` and the `RecordReplayModelRouter` in `debate_core.integrations.models`
(v1-e05-t03-fake-replay-models), and `ScriptedModelRouter` in `debate_core.testing`, which answers
from a queue. Each is held to :mod:`debate_core.testing.contracts.model_router`.

## Errors a router raises

| Error | When |
|---|---|
| :class:`RoutingConfigError` | The routing file is invalid, or has no route for the task class. |
| :class:`~debate_core.application.errors.InvalidModelOutput` | The answer does not validate as the schema. |
| :class:`~debate_core.application.errors.ModelUnavailableError` | The routed model could not be reached. |
| :class:`~debate_core.application.errors.ProviderRateLimited` | The provider refused the call for rate. |
| `ValueError` | A caller mistake: `generate_structured` on a scoring class, nothing to embed or rerank. |
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from debate_core.application.settings import ConfigurationError
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelResponse,
    RerankResponse,
    TaskClass,
)

__all__ = ["ModelRouter", "RoutingConfigError"]


class RoutingConfigError(ConfigurationError):
    """A routing file is missing, unreadable, or does not match the schema; or it has no route for a class.

    A subclass of :class:`~debate_core.application.settings.ConfigurationError` because that is
    what it is, one badly configured file, so the CLI reports it as a configuration problem the
    user can fix, with the same exit code as any other. `field` names the offending key, dotted
    as it appears in the file (`routes.high_volume.temperature`).
    """


@runtime_checkable
class ModelRouter(Protocol):
    """Routes each call by task class and returns validated, attributable results.

    Every response carries the :class:`~debate_core.domain.model_contracts.ResolvedRoute` it ran
    on (model id, inference profile, region and the parameters actually sent) and its
    :class:`~debate_core.domain.model_contracts.ModelUsage`.
    """

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        """Run `prompt` routed as `task_class` and return its output validated as `schema`.

        `params` overrides the route's defaults field by field; an unset field keeps the
        default, and the route on the response reports what was actually sent.

        Raises `ValueError` when `task_class` is not generative (`embeddings`, `rerank`), before
        anything is sent. Raises the errors in this module's table otherwise; never returns
        unvalidated text.
        """
        ...

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        """Embed `texts`, routed as `embeddings`: one vector per text, in the order given.

        Raises `ValueError` when `texts` is empty or any text is blank.
        """
        ...

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        """Order `documents` by relevance to `query`, routed as `rerank`; every document appears once.

        Results name documents by their position in `documents`. Raises `ValueError` when the
        query is blank or there are no documents.
        """
        ...

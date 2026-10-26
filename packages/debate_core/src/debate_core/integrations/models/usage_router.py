"""The router that logs what each real model call used, and the pricer the budget guard asks (v1-e05-t07).

:func:`~debate_core.integrations.models.factory.build_model_router` puts these around the real router,
inside the record-and-replay router, in record and live mode::

    RecordReplayModelRouter( BudgetGuard( UsageRecordingRouter( Bedrock ) ) )

* :class:`UsageRecordingRouter` times each call, reads the tokens the provider reported, prices them
  and appends a :class:`~debate_core.integrations.models.usage.UsageRecord` to the usage log. An
  answer that failed validation was still a billed call: the router's
  :class:`~debate_core.application.errors.InvalidModelOutput` carries its usage, and it is logged
  before the error goes on to the structured-output guard. So both attempts of a repaired call are
  in the log, the repair as attempt 2.
* :class:`RoutePricing` says what a call can cost at most, before it is made, for
  :class:`~debate_core.application.budget.BudgetGuard`.

Replay and the fake router make no call, so nothing here wraps them.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from pydantic import BaseModel

from debate_core.application.budget import CallCeiling
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.ports.providers import Clock
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelResponse,
    RerankResponse,
    TaskClass,
)
from debate_core.integrations.models.routing_policy import RoutingPolicy
from debate_core.integrations.models.usage import ModelPricing, UsageLog

__all__ = ["RoutePricing", "UsageRecordingRouter"]

type Timer = Callable[[], float]
"""Seconds from an arbitrary start, `time.perf_counter` by default."""


class UsageRecordingRouter:
    """A `ModelRouter` that appends a usage record for every call the router behind it makes."""

    def __init__(
        self,
        delegate: ModelRouter,
        *,
        log: UsageLog,
        pricing: ModelPricing,
        run_id: str,
        clock: Clock,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Record `delegate`'s calls in `log`, priced by `pricing`, as run `run_id`.

        `clock` stamps each record; `timer` measures the call, retries and backoff included.
        """
        self._delegate = delegate
        self._log = log
        self._pricing = pricing
        self.run_id = run_id
        """The run every record names."""
        self._clock = clock
        self._timer = timer

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        return await self._delegate.generate_structured(task_class, prompt, schema, params)

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        return await self._delegate.embed(texts)

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        return await self._delegate.rerank(query, documents)


class RoutePricing:
    """The most a call can cost: its route's model and output cap, at the pricing file's prices.

    The ceiling of a generative call is its route's `max_tokens` at the output price, plus its
    prompt variables at the input price, counting one token per UTF-8 byte of their JSON, which no
    tokenizer exceeds. It leaves out the prompt template's own wording, the system prompt and the
    schema's tool definition, which the router adds and this does not see. An embedding's ceiling
    counts its texts the same way, which bounds them fully. A rerank's is its search units.
    """

    def __init__(self, policy: RoutingPolicy, pricing: ModelPricing) -> None:
        self._policy = policy
        self._pricing = pricing

    def structured_ceiling(
        self, task_class: TaskClass, prompt: ModelPrompt, params: ModelParams | None
    ) -> CallCeiling:
        route = self._policy.resolve(task_class, params)
        return CallCeiling(model_id=route.model_id, usd=0.0)

    def embedding_ceiling(self, texts: Sequence[str]) -> CallCeiling:
        route = self._policy.resolve(TaskClass.EMBEDDINGS)
        return CallCeiling(model_id=route.model_id, usd=0.0)

    def rerank_ceiling(self, query: str, documents: Sequence[str]) -> CallCeiling:
        route = self._policy.resolve(TaskClass.RERANK)
        return CallCeiling(model_id=route.model_id, usd=0.0)

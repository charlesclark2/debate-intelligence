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

import json
import time
from collections.abc import Callable, Sequence
from typing import Final

from pydantic import BaseModel

from debate_core.application.budget import CallCeiling
from debate_core.application.errors import InvalidModelOutput
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.ports.providers import Clock
from debate_core.application.structured_output import REPAIR_PROMPT_ID
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelResponse,
    ModelUsage,
    RerankResponse,
    TaskClass,
)
from debate_core.integrations.models.routing_policy import RoutingPolicy
from debate_core.integrations.models.usage import ModelPricing, UsageLog, UsageRecord, search_units

__all__ = ["RoutePricing", "UsageRecordingRouter"]

type Timer = Callable[[], float]
"""Seconds from an arbitrary start, `time.perf_counter` by default."""

FIRST_ATTEMPT: Final = 1
REPAIR_ATTEMPT: Final = 2
"""The attempt a `model.repair` call is: the structured-output guard repairs a call exactly once."""


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
        """The delegate's answer; its usage is logged whether the answer validated or not.

        A repair is recorded as what was sent, `model.repair`, as attempt 2. A call that got no
        answer (refused, throttled, unreachable) reported no usage and is not logged.
        """
        attempt = REPAIR_ATTEMPT if prompt.prompt_id == REPAIR_PROMPT_ID else FIRST_ATTEMPT
        started = self._timer()
        try:
            response = await self._delegate.generate_structured(task_class, prompt, schema, params)
        except InvalidModelOutput as invalid:
            if invalid.model_id is not None:
                self._record_structured(prompt, invalid.model_id, invalid.usage, attempt, started)
            raise
        self._record_structured(prompt, response.route.model_id, response.usage, attempt, started)
        return response

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        started = self._timer()
        response = await self._delegate.embed(texts)
        model_id = response.route.model_id
        input_tokens = response.usage.input_tokens
        self._append(
            None,
            model_id,
            FIRST_ATTEMPT,
            input_tokens,
            None,
            started,
            self._pricing.embedding_cost(model_id, input_tokens),
        )
        return response

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        started = self._timer()
        response = await self._delegate.rerank(query, documents)
        model_id = response.route.model_id
        usage = response.usage
        self._append(
            None,
            model_id,
            FIRST_ATTEMPT,
            usage.input_tokens,
            usage.output_tokens,
            started,
            self._pricing.rerank_cost(model_id, len(documents)),
        )
        return response

    def _record_structured(
        self, prompt: ModelPrompt, model_id: str, usage: ModelUsage | None, attempt: int, started: float
    ) -> None:
        input_tokens = usage.input_tokens if usage is not None else None
        output_tokens = usage.output_tokens if usage is not None else None
        self._append(
            prompt,
            model_id,
            attempt,
            input_tokens,
            output_tokens,
            started,
            self._pricing.structured_cost(model_id, input_tokens, output_tokens),
        )

    def _append(
        self,
        prompt: ModelPrompt | None,
        model_id: str,
        attempt: int,
        input_tokens: int | None,
        output_tokens: int | None,
        started: float,
        cost: float | None,
    ) -> None:
        latency_ms = max(0.0, (self._timer() - started) * 1000)
        self._log.append(
            UsageRecord(
                run_id=self.run_id,
                prompt_id=prompt.prompt_id if prompt is not None else None,
                prompt_version=prompt.prompt_version if prompt is not None else None,
                model_id=model_id,
                attempt=attempt,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=cost,
                recorded_at=self._clock.now(),
            )
        )


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
        model_id = route.model_id
        price = self._pricing.price_for(model_id)
        if price is None or price.input_usd_per_1k_tokens is None or price.output_usd_per_1k_tokens is None:
            return self._unpriced(model_id, "input and output price per 1K tokens")
        if route.max_tokens is None:
            return CallCeiling(
                model_id=model_id,
                usd=None,
                unpriced_reason=(
                    f"its {task_class.value} route sets no max_tokens, so its output has no ceiling"
                ),
            )
        variables = json.dumps(prompt.variables, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        input_bound = len(variables.encode("utf-8"))
        usd = (
            input_bound * price.input_usd_per_1k_tokens + route.max_tokens * price.output_usd_per_1k_tokens
        ) / 1000
        return CallCeiling(model_id=model_id, usd=usd)

    def embedding_ceiling(self, texts: Sequence[str]) -> CallCeiling:
        model_id = self._policy.resolve(TaskClass.EMBEDDINGS).model_id
        price = self._pricing.price_for(model_id)
        if price is None or price.input_usd_per_1k_tokens is None:
            return self._unpriced(model_id, "input price per 1K tokens")
        input_bound = sum(len(text.encode("utf-8")) for text in texts)
        return CallCeiling(model_id=model_id, usd=input_bound * price.input_usd_per_1k_tokens / 1000)

    def rerank_ceiling(self, query: str, documents: Sequence[str]) -> CallCeiling:
        model_id = self._policy.resolve(TaskClass.RERANK).model_id
        price = self._pricing.price_for(model_id)
        if price is None or price.usd_per_1k_search_units is None:
            return self._unpriced(model_id, "price per 1K search units")
        return CallCeiling(
            model_id=model_id, usd=search_units(len(documents)) * price.usd_per_1k_search_units / 1000
        )

    def _unpriced(self, model_id: str, needed: str) -> CallCeiling:
        return CallCeiling(
            model_id=model_id,
            usd=None,
            unpriced_reason=f"{self._pricing.source} has no {needed} for it",
        )

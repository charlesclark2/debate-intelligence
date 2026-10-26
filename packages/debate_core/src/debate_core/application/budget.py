"""The budget guard: no model call is made that could take a run or a day past its limit (v1-e05-t07).

:class:`BudgetGuard` is a :class:`~debate_core.application.ports.model_router.ModelRouter` in front of
another. Before every call it asks a :class:`CallPricer` for the most that call can cost, its
**ceiling**, and a :class:`SpendLedger` for what this run and this day have already spent. When
spent, plus the ceilings of calls still in flight, plus this call's ceiling is over a limit, it
raises :class:`BudgetExceededError` and the call is never made. Afterwards the call's actual cost is
in the ledger, because the router behind the guard records it there
(:class:`~debate_core.integrations.models.usage_router.UsageRecordingRouter`), so the next check
reads it.

* **Two limits, from settings.** `per_run_usd` is one run's limit, a run being one router built by
  :func:`~debate_core.integrations.models.factory.build_model_router`, which is one command; the
  `--max-cost` option sets it for that command. `per_day_usd` is one local day's, across every run
  on this machine. Either may be unset, and code sets neither: there is no default limit.
* **The day is the local date** of the injected clock's time (:func:`local_day`), which also names
  the day's usage log file, so the guard and the ledger never disagree on which day a call is in.
* **Fail closed.** With a limit set, a call whose ceiling cannot be priced, because its model has no
  price or its route sets no output cap, is refused with :class:`UnpricedModelError` naming the
  model. It is never treated as free.
* **Parallel calls** each hold their ceiling until they finish, so a burst of calls started together
  cannot all pass a check that each would pass alone.

Without any limit the guard checks nothing and asks nothing; the composition root does not build it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from typing import Protocol

from pydantic import BaseModel

from debate_core.application.errors import DomainError
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

__all__ = [
    "BudgetExceededError",
    "BudgetGuard",
    "BudgetLimits",
    "CallCeiling",
    "CallPricer",
    "Spend",
    "SpendLedger",
    "UnpricedModelError",
    "UnreadableUsageLog",
    "local_day",
]


def local_day(moment: datetime, zone: tzinfo | None = None) -> date:
    """The date `moment` falls on in `zone`, this machine's local time zone when `None`.

    The one rule for which day a model call belongs to: the guard's per-day limit and the usage
    log's file name both use it.
    """
    return moment.astimezone(zone).date()


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """What a run and a day may spend on model calls, in USD; `None` is no limit."""

    per_run_usd: float | None = None
    """The most one run (one command) may spend."""
    per_day_usd: float | None = None
    """The most one local day may spend, across every run on this machine."""

    def __post_init__(self) -> None:
        for name, limit in (("per_run_usd", self.per_run_usd), ("per_day_usd", self.per_day_usd)):
            if limit is not None and limit < 0:
                raise ValueError(f"a budget limit cannot be negative; {name} is {limit!r}")

    @property
    def enforced(self) -> bool:
        """Whether either limit is set."""
        return self.per_run_usd is not None or self.per_day_usd is not None


@dataclass(frozen=True, slots=True)
class CallCeiling:
    """The most one call can cost, before it is made, and the model it goes to."""

    model_id: str
    """The model the call is routed to."""
    usd: float | None
    """The ceiling in USD; `None` when the call cannot be priced."""
    unpriced_reason: str | None = None
    """Why `usd` is `None`, in words for the person who has to fix it."""


@dataclass(frozen=True, slots=True)
class Spend:
    """What has been spent so far: by one run, and on one day."""

    run_usd: float
    """By the run asked about, across every day it has run on."""
    day_usd: float
    """On the day asked about, by every run on this machine."""


class CallPricer(Protocol):
    """Says what a call can cost at most, before it is made.

    :class:`~debate_core.integrations.models.usage_router.RoutePricing` is the implementation: the
    routing file says which model a call goes to and its output cap, and `config/model_pricing.yaml`
    what that model charges.
    """

    def structured_ceiling(
        self, task_class: TaskClass, prompt: ModelPrompt, params: ModelParams | None
    ) -> CallCeiling:
        """The ceiling of a `generate_structured` call."""
        ...

    def embedding_ceiling(self, texts: Sequence[str]) -> CallCeiling:
        """The ceiling of an `embed` call."""
        ...

    def rerank_ceiling(self, query: str, documents: Sequence[str]) -> CallCeiling:
        """The ceiling of a `rerank` call."""
        ...


class SpendLedger(Protocol):
    """What has been spent: :class:`~debate_core.integrations.models.usage.UsageLog`, the usage log."""

    def spent(self, run_id: str, day: date) -> Spend:
        """What run `run_id` has spent, and what `day` has. Raises :class:`UnreadableUsageLog`."""
        ...


class BudgetExceededError(DomainError):
    """A model call was refused, before it was made, because it could take a limit past its value."""

    def __init__(
        self,
        *,
        limit_name: str,
        limit_usd: float,
        spent_usd: float,
        ceiling_usd: float,
        model_id: str,
    ) -> None:
        self.limit_name = limit_name
        """`per-run` or `per-day`."""
        self.limit_usd = limit_usd
        """The limit's value."""
        self.spent_usd = spent_usd
        """What was already spent or held by calls in flight, against that limit."""
        self.ceiling_usd = ceiling_usd
        """The most the refused call could have cost."""
        self.model_id = model_id
        """The model the refused call was routed to."""
        super().__init__(
            f"model call to {model_id} refused: the {limit_name} budget is ${limit_usd:.4f}, "
            f"${spent_usd:.4f} is already spent or held, and this call could cost up to "
            f"${ceiling_usd:.4f}"
        )


class UnpricedModelError(DomainError):
    """A model call was refused because a budget limit is set and the call cannot be priced.

    Fail closed: an unpriced call is not a free one. Price the model in `config/model_pricing.yaml`,
    or run without a limit.
    """

    def __init__(self, model_id: str, reason: str | None) -> None:
        self.model_id = model_id
        """The model with no usable price."""
        self.reason = reason
        """Why the call could not be priced."""
        because = f": {reason}" if reason else ""
        super().__init__(
            f"model call to {model_id} refused: a budget limit is set and the call cannot be priced{because}"
        )


class UnreadableUsageLog(DomainError):
    """The usage log could not be read, so what has been spent is unknown, and no call is made."""

    def __init__(self, location: str, reason: str) -> None:
        self.location = location
        """The file, and the line when one line is at fault."""
        self.reason = reason
        """What is wrong with it."""
        super().__init__(f"the model usage log {location} could not be read: {reason}")


class BudgetGuard:
    """A `ModelRouter` that refuses, before it is made, any call that could take a limit past its value."""

    def __init__(
        self,
        delegate: ModelRouter,
        *,
        limits: BudgetLimits,
        pricer: CallPricer,
        ledger: SpendLedger,
        run_id: str,
        clock: Clock,
        local_zone: tzinfo | None = None,
    ) -> None:
        """Guard `delegate` with `limits`, for the run `run_id`.

        `ledger` must be the log the router behind `delegate` records into, so a finished call's
        cost is there for the next check. `local_zone` is the zone the day is read in, this
        machine's when `None`.
        """
        self._delegate = delegate
        self.limits = limits
        """The limits this guard holds calls to."""
        self.run_id = run_id
        """The run whose spend counts against `per_run_usd`."""
        self._pricer = pricer
        self._ledger = ledger
        self._clock = clock
        self._local_zone = local_zone

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

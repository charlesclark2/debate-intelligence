"""The budget guard: a call that could take a run or a day past its limit is never made (v1-e05-t07).

The guard's own rules are tested over a fake pricer and ledger; acceptance criterion ac3 and the
repaired-call rule are tested end to end, through the real pricer, usage log and recording router,
over a fixture pricing file. Every expected ceiling and cost is worked out by hand beside it from
the fixture's prices; none is taken from a run. No model is reached: the router at the bottom
answers from a queue.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel, JsonValue

from debate_core.application.budget import (
    BudgetExceededError,
    BudgetGuard,
    BudgetLimits,
    CallCeiling,
    Spend,
    UnpricedModelError,
    UnreadableUsageLog,
)
from debate_core.application.errors import ModelUnavailableError
from debate_core.application.model_errors import ValidationPolicy
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.settings import Settings, load_settings
from debate_core.application.structured_output import StructuredOutputGuard, validate_model_output
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelProvider,
    ModelResponse,
    ModelUsage,
    RerankResponse,
    RerankResult,
    TaskClass,
)
from debate_core.integrations.models.factory import build_model_router
from debate_core.integrations.models.prompt_registry import PromptRegistry, load_prompt_file
from debate_core.integrations.models.routing_policy import ModelRoute, RoutingPolicy
from debate_core.integrations.models.usage import ModelPricing, UsageLog, UsageRecord
from debate_core.integrations.models.usage_router import RoutePricing, UsageRecordingRouter
from debate_core.testing.contracts.model_router import ContractPassage
from debate_core.testing.fakes.clock_and_ids import FixedClock

pytestmark = pytest.mark.anyio

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"

CHICAGO = ZoneInfo("America/Chicago")
LATE_EVENING = datetime(2026, 9, 18, 3, 30, tzinfo=UTC)
"""22:30 on 2026-09-17 in Chicago."""
THE_DAY = date(2026, 9, 17)

RUN = "run-under-test"

FIXTURE_PRICES = """\
version: 1
models:
  test.haiku:
    input_usd_per_1k_tokens: 0.001
    output_usd_per_1k_tokens: 0.005
    as_of: 2026-10-26
    source: https://pricing.example.test/bedrock
  test.embed:
    input_usd_per_1k_tokens: 0.0002
    as_of: 2026-10-26
    source: https://pricing.example.test/bedrock
  test.rerank:
    usd_per_1k_search_units: 2.0
    as_of: 2026-10-26
    source: https://pricing.example.test/bedrock
  test.unpriced:
    input_usd_per_1k_tokens: null
    output_usd_per_1k_tokens: null
    as_of: null
    source: null
"""

VALID: Mapping[str, JsonValue] = {"paragraph_id": 3, "start_offset": 0, "end_offset": 42}
INVALID: Mapping[str, JsonValue] = {"paragraph_id": "the third", "start_offset": 0, "end_offset": 42}

WARMING = ModelPrompt(
    prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Warming kills"}
)
"""Its variables are `{"tag":"Warming kills"}` as compact JSON: 23 bytes."""

WARMING_CEILING = 0.000523
"""23 bytes at $0.001/1K = $0.000023, plus the route's 100 max_tokens at $0.005/1K = $0.0005."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    committed = PromptRegistry.load(REPOSITORY_ROOT / "prompts")
    example = load_prompt_file(FIXTURES / "prompts" / "example" / "select-passage.md")
    return PromptRegistry([*committed.prompts, example])


@pytest.fixture
def pricing(tmp_path: Path) -> ModelPricing:
    path = tmp_path / "model_pricing.yaml"
    path.write_text(FIXTURE_PRICES, encoding="utf-8")
    return ModelPricing.load(path)


@pytest.fixture
def log(tmp_path: Path) -> UsageLog:
    return UsageLog(tmp_path / "usage", local_zone=CHICAGO)


def policy() -> RoutingPolicy:
    def generative(model_id: str, max_tokens: int | None) -> ModelRoute:
        return ModelRoute(
            provider=ModelProvider.BEDROCK,
            model_id=model_id,
            region="us-east-1",
            max_tokens=max_tokens,
            timeout_seconds=30,
        )

    def scoring(model_id: str) -> ModelRoute:
        return ModelRoute(
            provider=ModelProvider.BEDROCK, model_id=model_id, region="us-east-1", timeout_seconds=30
        )

    return RoutingPolicy(
        routes={
            TaskClass.HIGH_VOLUME: generative("test.haiku", 100),
            TaskClass.COMPLEX_REASONING: generative("test.unpriced", 100),
            TaskClass.DEEP_AUDIT: generative("test.haiku", None),
            TaskClass.EMBEDDINGS: scoring("test.embed"),
            TaskClass.RERANK: scoring("test.rerank"),
        }
    )


type Planned = tuple[Mapping[str, JsonValue] | None, int | None, int | None]


class MeteredRouter:
    """Answers from a queue, reporting the tokens each answer is planned with; counts what reached it."""

    def __init__(self, planned: Sequence[Planned] = ()) -> None:
        self.planned = list(planned)
        self.calls: list[str] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        self.calls.append(prompt.prompt_id)
        route = policy().resolve(task_class, params)
        answer, input_tokens, output_tokens = self.planned.pop(0)
        usage = ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=10.0)
        output = validate_model_output(
            schema,
            None if answer is None else dict(answer),
            prompt=prompt,
            model_id=route.model_id,
            usage=usage,
        )
        return ModelResponse[schema](
            output=output,
            route=route,
            usage=usage,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            invoked_at=LATE_EVENING,
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        self.calls.append("embed")
        return EmbeddingResponse(
            vectors=tuple((1.0,) for _ in texts),
            route=policy().resolve(TaskClass.EMBEDDINGS),
            usage=ModelUsage(input_tokens=len(texts), latency_ms=10.0),
            invoked_at=LATE_EVENING,
        )

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        self.calls.append("rerank")
        return RerankResponse(
            results=tuple(
                RerankResult(index=index, relevance_score=-index) for index in range(len(documents))
            ),
            route=policy().resolve(TaskClass.RERANK),
            usage=ModelUsage(latency_ms=10.0),
            invoked_at=LATE_EVENING,
        )


def metered_chain(
    delegate: ModelRouter,
    log: UsageLog,
    pricing: ModelPricing,
    limits: BudgetLimits,
    *,
    clock: FixedClock | None = None,
) -> BudgetGuard:
    """The chain build_model_router puts round a real router: guard, then recorder, then the router."""
    clock = clock or FixedClock(LATE_EVENING)
    recording = UsageRecordingRouter(delegate, log=log, pricing=pricing, run_id=RUN, clock=clock)
    return BudgetGuard(
        recording,
        limits=limits,
        pricer=RoutePricing(policy(), pricing),
        ledger=log,
        run_id=RUN,
        clock=clock,
        local_zone=CHICAGO,
    )


def earlier_record(
    cost: float | None, *, run_id: str = "an-earlier-run", at: datetime = LATE_EVENING
) -> UsageRecord:
    return UsageRecord(
        run_id=run_id,
        prompt_id="example.select-passage",
        prompt_version="1.0.0",
        model_id="test.haiku",
        attempt=1,
        input_tokens=1,
        output_tokens=1,
        latency_ms=1.0,
        estimated_cost_usd=cost,
        recorded_at=at,
    )


# ---------------------------------------------------------------------------------------------
# Acceptance criterion ac3, and the repaired call
# ---------------------------------------------------------------------------------------------


async def test_ac3_with_a_five_cent_run_budget_spent_the_next_call_is_refused_and_reaches_no_router(
    log: UsageLog, pricing: ModelPricing
) -> None:
    # The first call's ceiling is $0.000523, under $0.05, so it is made. It reports 50,000 input
    # tokens ($0.05) and 2,000 output tokens ($0.01): $0.06 spent, over the budget.
    delegate = MeteredRouter([(VALID, 50_000, 2_000), (VALID, 1, 1)])
    guard = metered_chain(delegate, log, pricing, BudgetLimits(per_run_usd=0.05))

    await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)
    with pytest.raises(BudgetExceededError) as raised:
        await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)

    assert delegate.calls == ["example.select-passage"]
    error = raised.value
    assert (error.limit_name, error.limit_usd, error.model_id) == ("per-run", 0.05, "test.haiku")
    assert error.spent_usd == pytest.approx(0.06)
    assert error.ceiling_usd == pytest.approx(WARMING_CEILING)
    assert len(log.read(THE_DAY)) == 1


async def test_both_attempts_of_a_repaired_call_count_against_the_budget(
    log: UsageLog, pricing: ModelPricing, registry: PromptRegistry
) -> None:
    # Attempt 1 (invalid): 25,000 input tokens = $0.025. Attempt 2 (the repair): 25,000 = $0.025.
    # $0.05 spent, so the next call's $0.000523 ceiling takes the run over $0.05. Counting only the
    # repair would leave $0.025 spent, and the next call would be made.
    delegate = MeteredRouter([(INVALID, 25_000, 0), (VALID, 25_000, 0), (VALID, 1, 1)])
    guard = metered_chain(delegate, log, pricing, BudgetLimits(per_run_usd=0.05))
    structured = StructuredOutputGuard(guard, registry)

    result = await structured.generate(
        TaskClass.HIGH_VOLUME, WARMING, ContractPassage, policy=ValidationPolicy(fail_closed=True)
    )
    with pytest.raises(BudgetExceededError) as raised:
        await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)

    assert result.repair_attempted is True
    assert delegate.calls == ["example.select-passage", "model.repair"]
    assert raised.value.spent_usd == pytest.approx(0.05)


# ---------------------------------------------------------------------------------------------
# The per-day limit and the day it is read on
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("earlier_spend", "made"),
    [(1.999, True), (1.9996, False)],
    ids=["ceiling-fits", "ceiling-would-cross"],
)
async def test_per_day_budget_counts_every_run_of_the_day_and_this_calls_ceiling(
    earlier_spend: float, made: bool, log: UsageLog, pricing: ModelPricing
) -> None:
    # $1.999 + $0.000523 = $1.999523, under $2.00: made. $1.9996 + $0.000523 = $2.000123: refused.
    log.append(earlier_record(earlier_spend))
    delegate = MeteredRouter([(VALID, 1, 1)])
    guard = metered_chain(delegate, log, pricing, BudgetLimits(per_day_usd=2.0))

    if made:
        await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)
    else:
        with pytest.raises(BudgetExceededError) as raised:
            await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)
        assert raised.value.limit_name == "per-day"

    assert len(delegate.calls) == (1 if made else 0)


async def test_the_day_is_the_local_date_of_the_clock(log: UsageLog, pricing: ModelPricing) -> None:
    """Spend filed under 2026-09-17 counts at 22:30 that evening in Chicago, and not the next morning."""
    log.append(earlier_record(1.9999))
    delegate = MeteredRouter([(VALID, 1, 1)])

    with pytest.raises(BudgetExceededError):
        await metered_chain(delegate, log, pricing, BudgetLimits(per_day_usd=2.0)).generate_structured(
            TaskClass.HIGH_VOLUME, WARMING, ContractPassage
        )
    next_morning = FixedClock(LATE_EVENING + timedelta(hours=10))
    await metered_chain(
        delegate, log, pricing, BudgetLimits(per_day_usd=2.0), clock=next_morning
    ).generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)

    assert len(delegate.calls) == 1


# ---------------------------------------------------------------------------------------------
# Fail closed: what cannot be priced is not free
# ---------------------------------------------------------------------------------------------


async def test_an_unpriced_model_is_refused_naming_it_when_a_limit_is_set(
    log: UsageLog, pricing: ModelPricing
) -> None:
    delegate = MeteredRouter([(VALID, 1, 1)])
    guard = metered_chain(delegate, log, pricing, BudgetLimits(per_day_usd=100.0))

    with pytest.raises(UnpricedModelError, match="test.unpriced") as raised:
        await guard.generate_structured(TaskClass.COMPLEX_REASONING, WARMING, ContractPassage)

    assert raised.value.model_id == "test.unpriced"
    assert delegate.calls == []


async def test_a_route_with_no_output_cap_is_refused_when_a_limit_is_set(
    log: UsageLog, pricing: ModelPricing
) -> None:
    delegate = MeteredRouter([(VALID, 1, 1)])
    guard = metered_chain(delegate, log, pricing, BudgetLimits(per_run_usd=100.0))

    with pytest.raises(UnpricedModelError, match="max_tokens"):
        await guard.generate_structured(TaskClass.DEEP_AUDIT, WARMING, ContractPassage)

    assert delegate.calls == []


async def test_without_a_limit_the_guard_neither_prices_nor_refuses(
    log: UsageLog, pricing: ModelPricing
) -> None:
    delegate = MeteredRouter([(VALID, 1, 1)])

    await metered_chain(delegate, log, pricing, BudgetLimits()).generate_structured(
        TaskClass.COMPLEX_REASONING, WARMING, ContractPassage
    )

    assert delegate.calls == ["example.select-passage"]


async def test_a_usage_log_that_cannot_be_read_refuses_the_call(log: UsageLog, pricing: ModelPricing) -> None:
    log.append(earlier_record(0.01))
    with log.path_for(THE_DAY).open("a", encoding="utf-8") as file:
        file.write("not a record\n")
    delegate = MeteredRouter([(VALID, 1, 1)])

    with pytest.raises(UnreadableUsageLog):
        await metered_chain(delegate, log, pricing, BudgetLimits(per_day_usd=2.0)).generate_structured(
            TaskClass.HIGH_VOLUME, WARMING, ContractPassage
        )

    assert delegate.calls == []


# ---------------------------------------------------------------------------------------------
# Embeddings and rerank
# ---------------------------------------------------------------------------------------------


async def test_embed_and_rerank_are_held_to_the_budget_too(log: UsageLog, pricing: ModelPricing) -> None:
    # Embedding "abc" and "de": 5 bytes at $0.0002/1K = $0.000001, under $0.005: made.
    # Reranking 250 documents: 3 search units at $2.00/1K = $0.006, over $0.005: refused.
    delegate = MeteredRouter()
    guard = metered_chain(delegate, log, pricing, BudgetLimits(per_run_usd=0.005))

    await guard.embed(["abc", "de"])
    with pytest.raises(BudgetExceededError) as raised:
        await guard.rerank("query", [f"document {number}" for number in range(250)])

    assert delegate.calls == ["embed"]
    assert raised.value.ceiling_usd == pytest.approx(0.006)


# ---------------------------------------------------------------------------------------------
# The ceilings RoutePricing works out
# ---------------------------------------------------------------------------------------------


def test_ceiling_of_a_structured_call_is_its_output_cap_and_its_variables_bytes(
    pricing: ModelPricing,
) -> None:
    ceiling = RoutePricing(policy(), pricing).structured_ceiling(TaskClass.HIGH_VOLUME, WARMING, None)

    assert (ceiling.model_id, ceiling.usd) == ("test.haiku", pytest.approx(WARMING_CEILING))


def test_ceiling_counts_bytes_not_characters_and_a_call_s_own_output_cap(pricing: ModelPricing) -> None:
    # {"tag":"Débat"} is 15 characters and 16 UTF-8 bytes: $0.000016. A 50-token cap: $0.00025.
    prompt = ModelPrompt(
        prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Débat"}
    )

    ceiling = RoutePricing(policy(), pricing).structured_ceiling(
        TaskClass.HIGH_VOLUME, prompt, ModelParams(max_tokens=50)
    )

    assert ceiling.usd == pytest.approx(0.000266)


def test_ceiling_of_an_embedding_and_a_rerank(pricing: ModelPricing) -> None:
    pricer = RoutePricing(policy(), pricing)

    assert pricer.embedding_ceiling(["abc", "dé"]).usd == pytest.approx(6 * 0.0002 / 1000)
    assert pricer.rerank_ceiling("query", ["one"] * 101).usd == pytest.approx(2 * 2.0 / 1000)


def test_ceiling_of_an_unpriced_model_says_why() -> None:
    ceiling = RoutePricing(policy(), ModelPricing({})).structured_ceiling(
        TaskClass.HIGH_VOLUME, WARMING, None
    )

    assert (ceiling.model_id, ceiling.usd) == ("test.haiku", None)
    assert ceiling.unpriced_reason is not None
    assert "model_pricing" in ceiling.unpriced_reason


# ---------------------------------------------------------------------------------------------
# The guard's own rules, over a fake pricer and ledger
# ---------------------------------------------------------------------------------------------


class FixedPricer:
    def __init__(self, usd: float | None) -> None:
        self.usd = usd

    def structured_ceiling(
        self, task_class: TaskClass, prompt: ModelPrompt, params: ModelParams | None
    ) -> CallCeiling:
        return CallCeiling(model_id="test.haiku", usd=self.usd, unpriced_reason="no price in the test")

    def embedding_ceiling(self, texts: Sequence[str]) -> CallCeiling:
        return CallCeiling(model_id="test.embed", usd=self.usd)

    def rerank_ceiling(self, query: str, documents: Sequence[str]) -> CallCeiling:
        return CallCeiling(model_id="test.rerank", usd=self.usd)


class StillLedger:
    """A ledger whose spend never moves: only the guard's own holds change what it sees."""

    def __init__(self, run_usd: float = 0.0, day_usd: float = 0.0) -> None:
        self.spend = Spend(run_usd=run_usd, day_usd=day_usd)
        self.asked: list[tuple[str, date]] = []

    def spent(self, run_id: str, day: date) -> Spend:
        self.asked.append((run_id, day))
        return self.spend


class GatedRouter(MeteredRouter):
    """Holds every structured call until `gate` is set, so several are in flight at once."""

    def __init__(self) -> None:
        super().__init__([(VALID, 1, 1)] * 10)
        self.gate = asyncio.Event()

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        await self.gate.wait()
        return await super().generate_structured(task_class, prompt, schema, params)


def guard_over(
    delegate: ModelRouter, limits: BudgetLimits, pricer: FixedPricer, ledger: StillLedger
) -> BudgetGuard:
    return BudgetGuard(
        delegate,
        limits=limits,
        pricer=pricer,
        ledger=ledger,
        run_id=RUN,
        clock=FixedClock(LATE_EVENING),
        local_zone=CHICAGO,
    )


async def test_calls_in_flight_hold_their_ceilings_so_a_burst_cannot_overspend() -> None:
    # Each call could cost $0.02 under a $0.05 limit: two fit ($0.04), a third would make $0.06.
    delegate = GatedRouter()
    guard = guard_over(delegate, BudgetLimits(per_run_usd=0.05), FixedPricer(0.02), StillLedger())

    calls = [
        asyncio.ensure_future(guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage))
        for _ in range(4)
    ]
    await asyncio.sleep(0)
    delegate.gate.set()
    outcomes = await asyncio.gather(*calls, return_exceptions=True)

    assert [type(outcome).__name__ for outcome in outcomes] == [
        "ModelResponse[ContractPassage]",
        "ModelResponse[ContractPassage]",
        "BudgetExceededError",
        "BudgetExceededError",
    ]
    assert len(delegate.calls) == 2


async def test_a_finished_or_failed_call_lets_go_of_its_hold() -> None:
    class FailsOnce(MeteredRouter):
        failed = False

        async def generate_structured[OutputT: BaseModel](
            self,
            task_class: TaskClass,
            prompt: ModelPrompt,
            schema: type[OutputT],
            params: ModelParams | None = None,
        ) -> ModelResponse[OutputT]:
            if not self.failed:
                self.failed = True
                raise ModelUnavailableError("test.haiku", "unreachable")
            return await super().generate_structured(task_class, prompt, schema, params)

    delegate = FailsOnce([(VALID, 1, 1)] * 3)
    guard = guard_over(delegate, BudgetLimits(per_run_usd=0.05), FixedPricer(0.04), StillLedger())

    with pytest.raises(ModelUnavailableError):
        await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)
    for _ in range(3):
        await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)

    assert delegate.planned == []


async def test_the_guard_asks_the_ledger_for_this_run_on_the_local_day() -> None:
    ledger = StillLedger()
    guard = guard_over(
        MeteredRouter([(VALID, 1, 1)]), BudgetLimits(per_run_usd=1.0), FixedPricer(0.01), ledger
    )

    await guard.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)

    assert ledger.asked == [(RUN, THE_DAY)]


async def test_spend_exactly_at_the_limit_is_allowed_and_a_cent_more_is_not() -> None:
    at_limit = guard_over(
        MeteredRouter([(VALID, 1, 1)]),
        BudgetLimits(per_run_usd=0.05),
        FixedPricer(0.01),
        StillLedger(run_usd=0.04),
    )
    over = guard_over(
        MeteredRouter([(VALID, 1, 1)]),
        BudgetLimits(per_run_usd=0.05),
        FixedPricer(0.02),
        StillLedger(run_usd=0.04),
    )

    await at_limit.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)
    with pytest.raises(BudgetExceededError):
        await over.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)


def test_a_negative_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="per_day_usd"):
        BudgetLimits(per_day_usd=-1.0)


def test_the_refusal_names_the_model_the_limit_and_the_amounts() -> None:
    error = BudgetExceededError(
        limit_name="per-run", limit_usd=0.05, spent_usd=0.06, ceiling_usd=0.000523, model_id="test.haiku"
    )

    assert str(error) == (
        "model call to test.haiku refused: the per-run budget is $0.0500, $0.0600 is already spent or "
        "held, and this call could cost up to $0.0005"
    )


def test_the_log_ledger_is_what_the_guard_reads(log: UsageLog) -> None:
    """The record format the guard's ledger reads is the recorder's: one JSON object per line."""
    log.append(earlier_record(0.25, run_id=RUN))

    assert json.loads(log.path_for(THE_DAY).read_text(encoding="utf-8"))["estimated_cost_usd"] == 0.25
    assert log.spent(RUN, THE_DAY) == Spend(run_usd=0.25, day_usd=0.25)


# ---------------------------------------------------------------------------------------------
# Where the guard sits: built by build_model_router from the settings' limits
# ---------------------------------------------------------------------------------------------

EXAMPLE_ROUTING_FILE = REPOSITORY_ROOT / "config" / "model_routing.example.yaml"


def bedrock_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **models: object) -> Settings:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    return load_settings(
        environment="test",
        overrides={
            "models": {"provider": "bedrock", "routing_file": str(EXAMPLE_ROUTING_FILE)} | models,
            "storage": {"data_dir": str(tmp_path / "data")},
        },
        env_file=tmp_path / "no.env",
    )


def factory_router(
    settings: Settings, delegate: ModelRouter, mode: str, tmp_path: Path, pricing: Path | None
) -> ModelRouter:
    def real_router(routing: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
        return delegate

    return build_model_router(
        settings,
        mode=mode,
        environ={},
        real_router=real_router,
        cassette_dir=tmp_path / "cassettes",
        clock=FixedClock(LATE_EVENING),
        pricing_file=pricing,
        usage_log=UsageLog.for_data_dir(settings.storage.data_dir, local_zone=CHICAGO),
    )


@pytest.mark.parametrize("mode", ["live", "record"])
async def test_build_model_router_holds_a_real_router_to_the_settings_run_budget(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The example routing file sends high_volume to anthropic.claude-haiku-5-5 with 2048 max_tokens,
    # priced here as test.haiku is: a ceiling of $0.000023 + $0.01024 = $0.010263, under $0.05.
    # The first call reports $0.06 (as in ac3), so the second is refused before it is made.
    pricing = tmp_path / "model_pricing.yaml"
    pricing.write_text(
        FIXTURE_PRICES + "  anthropic.claude-haiku-5-5:\n"
        "    input_usd_per_1k_tokens: 0.001\n"
        "    output_usd_per_1k_tokens: 0.005\n"
        "    as_of: 2026-10-26\n"
        "    source: https://pricing.example.test/bedrock\n",
        encoding="utf-8",
    )
    settings = bedrock_settings(tmp_path, monkeypatch, budget_usd_per_run=0.05, budget_usd_daily=None)
    delegate = MeteredRouter([(VALID, 50_000, 2_000), (VALID, 1, 1)])
    router = factory_router(settings, delegate, mode, tmp_path, pricing)

    await router.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)
    with pytest.raises(BudgetExceededError) as raised:
        await router.generate_structured(TaskClass.HIGH_VOLUME, WARMING, ContractPassage)

    assert delegate.calls == ["example.select-passage"]
    assert (raised.value.limit_name, raised.value.model_id) == ("per-run", "anthropic.claude-haiku-5-5")
    assert raised.value.ceiling_usd == pytest.approx(0.010263)


async def test_the_test_profile_s_zero_daily_budget_refuses_a_live_call_to_an_unpriced_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The committed pricing file prices nothing yet, and the test profile's daily limit is $0."""
    settings = bedrock_settings(tmp_path, monkeypatch)
    delegate = MeteredRouter([(VALID, 1, 1)])

    assert settings.models.budget_usd_daily == 0.0
    with pytest.raises(UnpricedModelError, match="anthropic.claude-haiku-5-5"):
        await factory_router(settings, delegate, "live", tmp_path, None).generate_structured(
            TaskClass.HIGH_VOLUME, WARMING, ContractPassage
        )
    assert delegate.calls == []

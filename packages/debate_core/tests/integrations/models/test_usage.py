"""Usage records, the pricing table, the usage log and the recording router (v1-e05-t07-usage-telemetry).

Every price here is a fixture's, written into `tmp_path` by the test, and every expected cost is
worked out by hand in a comment beside it from those prices; none is taken from a run. Nothing here
reaches a model: the router behind the recorder is :class:`MeteredRouter`, which answers from a
queue and reports the tokens it is told to.

`-k pricing` is the `usage-pricing` node's criterion, `-k record` the `recording-router` node's.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml
from pydantic import BaseModel, JsonValue

from debate_core.application.errors import InvalidModelOutput, ModelUnavailableError
from debate_core.application.model_errors import ModelOutputError, ValidationPolicy
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.settings import ConfigurationError, Settings, load_settings
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
from debate_core.integrations.models import RoutingPolicy, build_model_router
from debate_core.integrations.models.prompt_registry import PromptRegistry, load_prompt_file
from debate_core.integrations.models.routing_policy import ModelRoute
from debate_core.integrations.models.usage import (
    ModelPricing,
    UsageLog,
    UsageRecord,
    search_units,
    summarize,
)
from debate_core.integrations.models.usage_router import UsageRecordingRouter
from debate_core.testing.contracts.model_router import ContractPassage
from debate_core.testing.fakes.clock_and_ids import FixedClock

pytestmark = pytest.mark.anyio

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"
COMMITTED_PRICING = REPOSITORY_ROOT / "config" / "model_pricing.yaml"

CHICAGO = ZoneInfo("America/Chicago")
"""The local zone of these tests: UTC-5 in September, so a late-evening call is the next day in UTC."""

LATE_EVENING = datetime(2026, 9, 18, 3, 30, tzinfo=UTC)
"""22:30 on 2026-09-17 in Chicago: its record goes in 2026-09-17.jsonl, not 2026-09-18.jsonl."""

RUN = "run-0001"

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

SENTINEL = "Sentinelword Northbrookhigh Okaforteam standing in for card, school and student words"
"""Invented text a call's variables and documents carry; no usage record may repeat its invented words."""

INVENTED_WORDS = ("Sentinelword", "Northbrookhigh", "Okaforteam")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def pricing_file(tmp_path: Path) -> Path:
    path = tmp_path / "model_pricing.yaml"
    path.write_text(FIXTURE_PRICES, encoding="utf-8")
    return path


@pytest.fixture
def pricing(pricing_file: Path) -> ModelPricing:
    return ModelPricing.load(pricing_file)


@pytest.fixture
def log(tmp_path: Path) -> UsageLog:
    return UsageLog(tmp_path / "data" / "usage", local_zone=CHICAGO)


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    """The committed prompts, `model.repair` among them, plus the worked example."""
    committed = PromptRegistry.load(REPOSITORY_ROOT / "prompts")
    example = load_prompt_file(FIXTURES / "prompts" / "example" / "select-passage.md")
    return PromptRegistry([*committed.prompts, example])


def policy() -> RoutingPolicy:
    """high_volume on a priced model, complex_reasoning on an unpriced one, deep_audit with no output cap."""

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


def example_prompt(tag: str = "Warming kills") -> ModelPrompt:
    return ModelPrompt(prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": tag})


type Planned = tuple[Mapping[str, JsonValue] | None, int | None, int | None]
"""One planned answer: the tool input (None: no tool call), and the input and output tokens reported."""


class MeteredRouter:
    """A router that answers from a queue and reports the tokens each answer is planned with.

    An invalid answer is refused by `validate_model_output`, as every router's is, with the call's
    usage on the error: what the Bedrock adapter does with Converse's `usage`.
    """

    def __init__(self, planned: Sequence[Planned] = (), *, routing: RoutingPolicy | None = None) -> None:
        self.planned = list(planned)
        self.routing = routing or policy()
        self.calls: list[str] = []

    def _next(self, what: str) -> Planned:
        self.calls.append(what)
        return self.planned.pop(0)

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        route = self.routing.resolve(task_class, params)
        answer, input_tokens, output_tokens = self._next(prompt.prompt_id)
        usage = ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=850.0)
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
        _, input_tokens, _ = self._next("embed")
        return EmbeddingResponse(
            vectors=tuple((1.0, 0.0) for _ in texts),
            route=self.routing.resolve(TaskClass.EMBEDDINGS),
            usage=ModelUsage(input_tokens=input_tokens, latency_ms=850.0),
            invoked_at=LATE_EVENING,
        )

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        self._next("rerank")
        return RerankResponse(
            results=tuple(
                RerankResult(index=index, relevance_score=-index) for index in range(len(documents))
            ),
            route=self.routing.resolve(TaskClass.RERANK),
            usage=ModelUsage(latency_ms=850.0),
            invoked_at=LATE_EVENING,
        )


class SteppingTimer:
    """`time.perf_counter` for a test: each call is `step` seconds after the one before."""

    def __init__(self, step: float = 0.25) -> None:
        self._now = 100.0
        self._step = step

    def __call__(self) -> float:
        self._now += self._step
        return self._now


def recorder(
    delegate: ModelRouter, log: UsageLog, pricing: ModelPricing, *, clock: FixedClock | None = None
) -> UsageRecordingRouter:
    return UsageRecordingRouter(
        delegate,
        log=log,
        pricing=pricing,
        run_id=RUN,
        clock=clock or FixedClock(LATE_EVENING),
        timer=SteppingTimer(),
    )


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def record(**fields: Any) -> UsageRecord:
    """A record with plausible defaults, for the log's own tests."""
    defaults: dict[str, Any] = {
        "run_id": RUN,
        "prompt_id": "example.select-passage",
        "prompt_version": "1.0.0",
        "model_id": "test.haiku",
        "attempt": 1,
        "input_tokens": 1000,
        "output_tokens": 100,
        "latency_ms": 250.0,
        "estimated_cost_usd": 0.0015,
        "recorded_at": LATE_EVENING,
    }
    return UsageRecord(**(defaults | fields))


# ---------------------------------------------------------------------------------------------
# The pricing table (node usage-pricing: -k pricing)
# ---------------------------------------------------------------------------------------------


BEDROCK_PRICING_PAGE = "https://aws.amazon.com/bedrock/pricing/"

COMMITTED_PRICES = {
    # Read by the operator off the AWS Bedrock pricing page (us-east-1, on-demand) on 2026-10-26.
    "anthropic.claude-haiku-5-5": {"input_usd_per_1k_tokens": 0.0001, "output_usd_per_1k_tokens": 0.0005},
    "anthropic.claude-sonnet-5-5": {"input_usd_per_1k_tokens": 0.002, "output_usd_per_1k_tokens": 0.01},
    "anthropic.claude-opus-5-5": {"input_usd_per_1k_tokens": 0.004, "output_usd_per_1k_tokens": 0.02},
    "amazon.titan-embed-text-v2:0": {"input_usd_per_1k_tokens": 0.00002},
    "cohere.rerank-v3-5:0": {"usd_per_1k_search_units": 2.0},
}
"""The prices the PM committed, written out by hand from the PM's table; every other price is unset."""


def test_pricing_file_has_an_entry_for_every_model_the_routing_files_route() -> None:
    routed = {
        route["model_id"]
        for path in sorted((REPOSITORY_ROOT / "config").glob("model_routing.*.yaml"))
        for route in yaml.safe_load(path.read_text(encoding="utf-8"))["routes"].values()
    }
    committed = ModelPricing.load(COMMITTED_PRICING)

    assert routed == {
        "anthropic.claude-haiku-5-5",
        "anthropic.claude-sonnet-5-5",
        "anthropic.claude-opus-5-5",
        "amazon.titan-embed-text-v2:0",
        "cohere.rerank-v3-5:0",
    }
    assert {model_id for model_id in routed if committed.price_for(model_id) is None} == set()


def test_pricing_every_committed_price_is_set_and_well_formed() -> None:
    """Each routed model has the prices its calls need, the day they were read and where."""
    committed = ModelPricing.load(COMMITTED_PRICING)

    for model_id, prices in COMMITTED_PRICES.items():
        entry = committed.price_for(model_id)
        assert entry is not None, model_id
        unset = {
            "input_usd_per_1k_tokens": None,
            "output_usd_per_1k_tokens": None,
            "usd_per_1k_search_units": None,
        }
        assert entry.model_dump() == unset | prices | {
            "as_of": date(2026, 10, 26),
            "source": BEDROCK_PRICING_PAGE,
        }


def test_pricing_the_committed_prices_price_each_kind_of_call() -> None:
    committed = ModelPricing.load(COMMITTED_PRICING)

    # Haiku: 2000 in at $0.0001/1K = $0.0002, 400 out at $0.0005/1K = $0.0002.
    assert committed.structured_cost("anthropic.claude-haiku-5-5", 2000, 400) == pytest.approx(0.0004)
    # Opus: 2000 in at $0.004/1K = $0.008, 400 out at $0.02/1K = $0.008.
    assert committed.structured_cost("anthropic.claude-opus-5-5", 2000, 400) == pytest.approx(0.016)
    # Titan: 1500 tokens at $0.00002/1K = $0.00003.
    assert committed.embedding_cost("amazon.titan-embed-text-v2:0", 1500) == pytest.approx(0.00003)
    # Cohere: 250 documents are 3 search units at $2.00/1K = $0.006.
    assert committed.rerank_cost("cohere.rerank-v3-5:0", 250) == pytest.approx(0.006)


def test_pricing_cost_of_a_structured_call_is_its_tokens_at_the_per_1k_prices(pricing: ModelPricing) -> None:
    # 2000 input tokens at $0.001/1K = $0.002; 400 output tokens at $0.005/1K = $0.002.
    assert pricing.structured_cost("test.haiku", 2000, 400) == pytest.approx(0.004)


def test_pricing_cost_of_an_embedding_is_its_input_tokens(pricing: ModelPricing) -> None:
    # 1500 tokens at $0.0002/1K = $0.0003.
    assert pricing.embedding_cost("test.embed", 1500) == pytest.approx(0.0003)


def test_pricing_cost_of_a_rerank_is_its_search_units(pricing: ModelPricing) -> None:
    # 250 documents are 3 search units (100 documents each); 3 at $2.00/1K = $0.006.
    assert pricing.rerank_cost("test.rerank", 250) == pytest.approx(0.006)


@pytest.mark.parametrize(("documents", "units"), [(0, 0), (1, 1), (100, 1), (101, 2), (250, 3)])
def test_pricing_search_units_are_one_per_started_hundred_documents(documents: int, units: int) -> None:
    assert search_units(documents) == units


@pytest.mark.parametrize(
    ("model_id", "why"),
    [("test.unknown", "no entry"), ("test.unpriced", "an entry with no price")],
)
def test_pricing_an_unpriced_model_costs_null_with_a_warning_naming_it(
    model_id: str, why: str, pricing: ModelPricing, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="debate_core.integrations.models.usage"):
        cost = pricing.structured_cost(model_id, 2000, 400)

    assert cost is None, why
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert model_id in caplog.records[0].getMessage()


def test_pricing_warns_once_per_model_not_once_per_call(
    pricing: ModelPricing, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="debate_core.integrations.models.usage"):
        for _ in range(3):
            pricing.structured_cost("test.unpriced", 10, 10)

    assert len(caplog.records) == 1


def test_pricing_a_model_priced_for_input_only_cannot_price_a_structured_call(pricing: ModelPricing) -> None:
    """The embedding model has an input price and no output price: a generative call to it is unpriced."""
    assert pricing.structured_cost("test.embed", 2000, 400) is None


def test_pricing_unreported_tokens_cost_null_rather_than_nothing(pricing: ModelPricing) -> None:
    assert pricing.structured_cost("test.haiku", None, 400) is None
    assert pricing.embedding_cost("test.embed", None) is None


def test_pricing_a_missing_file_prices_nothing(tmp_path: Path) -> None:
    pricing = ModelPricing.load(tmp_path / "absent.yaml")

    assert pricing.price_for("test.haiku") is None
    assert pricing.structured_cost("test.haiku", 2000, 400) is None


@pytest.mark.parametrize(
    ("text", "field"),
    [
        (
            "version: 1\nmodels:\n  test.haiku:\n    input_usd_per_1k_tokens: 0.001\n    source: https://x.test\n",
            "models.test.haiku",
        ),
        (
            "version: 1\nmodels:\n  test.haiku:\n    input_usd_per_1k_tokens: 0.001\n    as_of: 2026-10-26\n",
            "models.test.haiku",
        ),
        (
            "version: 1\nmodels:\n  test.haiku:\n    input_usd_per_1k_tokens: -0.001\n"
            "    as_of: 2026-10-26\n    source: https://x.test\n",
            "models.test.haiku.input_usd_per_1k_tokens",
        ),
        ("version: 1\nmodels:\n  test.haiku:\n    per_token: 0.001\n", "models.test.haiku.per_token"),
        ("version: 2\nmodels: {}\n", "version"),
    ],
    ids=["price-without-as-of", "price-without-source", "negative-price", "unknown-key", "unknown-version"],
)
def test_pricing_file_that_is_not_the_schema_is_a_configuration_error_naming_the_key(
    text: str, field: str, tmp_path: Path
) -> None:
    path = tmp_path / "model_pricing.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigurationError) as raised:
        ModelPricing.load(path)

    assert raised.value.field == field
    assert str(path) in str(raised.value)


def test_pricing_file_that_is_not_yaml_is_a_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "model_pricing.yaml"
    path.write_text("models: [unclosed\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not valid YAML"):
        ModelPricing.load(path)


# ---------------------------------------------------------------------------------------------
# The recording router (node recording-router: -k record)
# ---------------------------------------------------------------------------------------------


async def test_record_holds_exactly_the_telemetry_fields_and_no_others(
    log: UsageLog, pricing: ModelPricing
) -> None:
    router = recorder(MeteredRouter([(VALID, 2000, 400)]), log, pricing)

    await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    [written] = lines(log.path_for(date(2026, 9, 17)))
    assert set(written) == {
        "run_id",
        "prompt_id",
        "prompt_version",
        "model_id",
        "attempt",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "estimated_cost_usd",
        "recorded_at",
    }


async def test_record_of_a_structured_call_names_its_run_prompt_model_tokens_latency_cost_and_time(
    log: UsageLog, pricing: ModelPricing
) -> None:
    router = recorder(MeteredRouter([(VALID, 2000, 400)]), log, pricing)

    await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    # 2000 in at $0.001/1K + 400 out at $0.005/1K = $0.004; the timer steps 0.25 s per read.
    assert lines(log.path_for(date(2026, 9, 17))) == [
        {
            "run_id": RUN,
            "prompt_id": "example.select-passage",
            "prompt_version": "1.0.0",
            "model_id": "test.haiku",
            "attempt": 1,
            "input_tokens": 2000,
            "output_tokens": 400,
            "latency_ms": 250.0,
            "estimated_cost_usd": pytest.approx(0.004),
            "recorded_at": "2026-09-18T03:30:00Z",
        }
    ]


async def test_record_goes_in_the_file_of_the_local_day_not_the_utc_day(
    log: UsageLog, pricing: ModelPricing
) -> None:
    router = recorder(MeteredRouter([(VALID, 10, 10)]), log, pricing)

    await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    assert sorted(path.name for path in log.directory.iterdir()) == ["2026-09-17.jsonl"]


async def test_record_appends_one_line_per_call(log: UsageLog, pricing: ModelPricing) -> None:
    router = recorder(MeteredRouter([(VALID, 10, 10), (VALID, 20, 20), (VALID, 30, 30)]), log, pricing)

    for _ in range(3):
        await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    assert [line["input_tokens"] for line in lines(log.path_for(date(2026, 9, 17)))] == [10, 20, 30]


async def test_record_both_attempts_of_a_repaired_call_first_attempt_tokens_included(
    log: UsageLog, pricing: ModelPricing, registry: PromptRegistry
) -> None:
    """The PM's proof for the 2026-10-24 amendment: the invalid first answer's tokens are in the log."""
    delegate = MeteredRouter([(INVALID, 900, 60), (VALID, 1200, 40)])
    guard = StructuredOutputGuard(recorder(delegate, log, pricing), registry)

    result = await guard.generate(
        TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage, policy=ValidationPolicy(fail_closed=True)
    )

    written = lines(log.path_for(date(2026, 9, 17)))
    # Attempt 1: 900 in ($0.0009) + 60 out ($0.0003) = $0.0012.
    # Attempt 2: 1200 in ($0.0012) + 40 out ($0.0002) = $0.0014.
    assert [
        (line["attempt"], line["prompt_id"], line["input_tokens"], line["output_tokens"]) for line in written
    ] == [(1, "example.select-passage", 900, 60), (2, "model.repair", 1200, 40)]
    assert [line["estimated_cost_usd"] for line in written] == [pytest.approx(0.0012), pytest.approx(0.0014)]
    assert [(attempt.number, attempt.usage) for attempt in result.attempts] == [
        (1, ModelUsage(input_tokens=900, output_tokens=60, latency_ms=850.0)),
        (2, ModelUsage(input_tokens=1200, output_tokens=40, latency_ms=850.0)),
    ]


async def test_record_a_call_still_invalid_after_its_repair_logs_both_and_its_error_carries_both_usages(
    log: UsageLog, pricing: ModelPricing, registry: PromptRegistry
) -> None:
    delegate = MeteredRouter([(INVALID, 900, 60), (None, 1100, 30)])
    guard = StructuredOutputGuard(recorder(delegate, log, pricing), registry)

    with pytest.raises(ModelOutputError) as raised:
        await guard.generate(
            TaskClass.HIGH_VOLUME,
            example_prompt(),
            ContractPassage,
            policy=ValidationPolicy(fail_closed=True),
        )

    assert [(line["attempt"], line["input_tokens"]) for line in lines(log.path_for(date(2026, 9, 17)))] == [
        (1, 900),
        (2, 1100),
    ]
    assert [attempt.usage for attempt in raised.value.attempt_records] == [
        ModelUsage(input_tokens=900, output_tokens=60, latency_ms=850.0),
        ModelUsage(input_tokens=1100, output_tokens=30, latency_ms=850.0),
    ]


async def test_record_of_an_invalid_answer_is_logged_before_the_error_goes_on(
    log: UsageLog, pricing: ModelPricing
) -> None:
    router = recorder(MeteredRouter([(INVALID, 900, 60)]), log, pricing)

    with pytest.raises(InvalidModelOutput):
        await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    assert [line["input_tokens"] for line in lines(log.path_for(date(2026, 9, 17)))] == [900]


async def test_record_of_embed_and_rerank_calls_names_no_prompt(log: UsageLog, pricing: ModelPricing) -> None:
    router = recorder(MeteredRouter([(None, 1500, None), (None, None, None)]), log, pricing)

    await router.embed(["first", "second", "third"])
    await router.rerank("query", [f"document {number}" for number in range(250)])

    written = lines(log.path_for(date(2026, 9, 17)))
    assert [
        (line["prompt_id"], line["prompt_version"], line["model_id"], line["attempt"], line["input_tokens"])
        for line in written
    ] == [(None, None, "test.embed", 1, 1500), (None, None, "test.rerank", 1, None)]
    # 1500 tokens at $0.0002/1K = $0.0003; 250 documents = 3 search units at $2.00/1K = $0.006.
    assert [line["estimated_cost_usd"] for line in written] == [pytest.approx(0.0003), pytest.approx(0.006)]


async def test_record_of_an_unpriced_model_has_a_null_cost_not_zero(
    log: UsageLog, pricing: ModelPricing
) -> None:
    router = recorder(MeteredRouter([(VALID, 2000, 400)]), log, pricing)

    await router.generate_structured(
        TaskClass.COMPLEX_REASONING,
        ModelPrompt(prompt_id="example.reasoning", prompt_version="1.0.0"),
        ContractPassage,
    )

    [written] = lines(log.path_for(date(2026, 9, 17)))
    assert written["model_id"] == "test.unpriced"
    assert written["estimated_cost_usd"] is None


async def test_record_nothing_for_a_call_that_got_no_answer(log: UsageLog, pricing: ModelPricing) -> None:
    class Unreachable(MeteredRouter):
        async def generate_structured[OutputT: BaseModel](
            self,
            task_class: TaskClass,
            prompt: ModelPrompt,
            schema: type[OutputT],
            params: ModelParams | None = None,
        ) -> ModelResponse[OutputT]:
            raise ModelUnavailableError("test.haiku", "no route to the region")

    router = recorder(Unreachable(), log, pricing)

    with pytest.raises(ModelUnavailableError):
        await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    assert not log.path_for(date(2026, 9, 17)).exists()


async def test_record_never_holds_prompt_variables_or_document_text(
    log: UsageLog, pricing: ModelPricing
) -> None:
    router = recorder(MeteredRouter([(VALID, 10, 10), (None, 10, None), (None, None, None)]), log, pricing)

    await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(SENTINEL), ContractPassage)
    await router.embed([SENTINEL])
    await router.rerank(SENTINEL, [SENTINEL, f"{SENTINEL} again"])

    text = log.path_for(date(2026, 9, 17)).read_text(encoding="utf-8")
    assert len(text.splitlines()) == 3
    assert [word for word in INVENTED_WORDS if word.lower() in text.lower()] == [], text


async def test_record_lines_stay_whole_when_calls_and_threads_append_at_once(
    log: UsageLog, pricing: ModelPricing
) -> None:
    """Fifty calls in one event loop at once, and two hundred appends from four threads besides."""
    router = recorder(MeteredRouter([(VALID, number, number) for number in range(50)]), log, pricing)

    def append_from_a_thread(offset: int) -> None:
        for number in range(50):
            log.append(record(input_tokens=1000 + offset * 100 + number))

    threads = [threading.Thread(target=append_from_a_thread, args=(offset,)) for offset in range(4)]
    for thread in threads:
        thread.start()
    await asyncio.gather(
        *(
            router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)
            for _ in range(50)
        )
    )
    for thread in threads:
        thread.join()

    written = log.read(date(2026, 9, 17))
    assert len(written) == 250
    assert sorted(entry.input_tokens or 0 for entry in written) == sorted(
        [*range(50), *(1000 + offset * 100 + number for offset in range(4) for number in range(50))]
    )


# ---------------------------------------------------------------------------------------------
# The log as the per-day ledger, and its summary
# ---------------------------------------------------------------------------------------------


def test_record_ledger_spent_counts_this_run_and_this_day(log: UsageLog) -> None:
    log.append(record(run_id="run-a", estimated_cost_usd=0.25))
    log.append(record(run_id="run-b", estimated_cost_usd=0.5))
    log.append(record(run_id="run-a", estimated_cost_usd=0.125))
    log.append(record(run_id="run-a", estimated_cost_usd=None))

    spent = log.spent("run-a", date(2026, 9, 17))

    # run-a: 0.25 + 0.125 (the unpriced call adds nothing); the day: 0.25 + 0.5 + 0.125.
    assert (spent.run_usd, spent.day_usd) == (pytest.approx(0.375), pytest.approx(0.875))


def test_record_ledger_reads_lines_appended_after_its_last_read(log: UsageLog) -> None:
    log.append(record(estimated_cost_usd=0.25))
    assert log.spent(RUN, date(2026, 9, 17)).day_usd == pytest.approx(0.25)

    other_process = UsageLog(log.directory, local_zone=CHICAGO)
    other_process.append(record(run_id="run-other", estimated_cost_usd=0.5))

    assert log.spent(RUN, date(2026, 9, 17)).day_usd == pytest.approx(0.75)


def test_record_ledger_counts_a_run_across_midnight_and_each_day_on_its_own(log: UsageLog) -> None:
    log.append(record(estimated_cost_usd=0.25))
    log.spent(RUN, date(2026, 9, 17))
    log.append(record(estimated_cost_usd=0.5, recorded_at=LATE_EVENING + timedelta(hours=2)))

    spent = log.spent(RUN, date(2026, 9, 18))

    assert (spent.run_usd, spent.day_usd) == (pytest.approx(0.75), pytest.approx(0.5))


def test_record_ledger_of_a_day_with_no_file_is_zero(log: UsageLog) -> None:
    spent = log.spent(RUN, date(2026, 9, 17))

    assert (spent.run_usd, spent.day_usd) == (0.0, 0.0)


def test_record_ledger_refuses_a_line_it_cannot_read_rather_than_skip_its_cost(log: UsageLog) -> None:
    from debate_core.application.budget import UnreadableUsageLog

    log.append(record(estimated_cost_usd=0.25))
    with log.path_for(date(2026, 9, 17)).open("a", encoding="utf-8") as file:
        file.write('{"run_id": "run-0001", "estimated_cost_usd": \n')

    with pytest.raises(UnreadableUsageLog, match=r"2026-09-17\.jsonl, line 2"):
        log.spent(RUN, date(2026, 9, 17))


def test_record_summary_groups_by_prompt_and_model_and_keeps_unpriced_calls_apart() -> None:
    records = [
        record(
            prompt_id="landscape.classify",
            model_id="test.haiku",
            input_tokens=100,
            output_tokens=10,
            estimated_cost_usd=0.25,
        ),
        record(
            prompt_id="model.repair",
            model_id="test.haiku",
            attempt=2,
            input_tokens=50,
            output_tokens=5,
            estimated_cost_usd=0.125,
        ),
        record(
            prompt_id="landscape.classify",
            model_id="test.haiku",
            input_tokens=200,
            output_tokens=20,
            estimated_cost_usd=0.5,
        ),
        record(
            prompt_id="landscape.classify",
            model_id="test.unpriced",
            input_tokens=300,
            output_tokens=30,
            estimated_cost_usd=None,
        ),
        record(
            prompt_id=None,
            prompt_version=None,
            model_id="test.embed",
            input_tokens=400,
            output_tokens=None,
            estimated_cost_usd=0.0625,
        ),
    ]

    summary = summarize(date(2026, 9, 17), records)

    assert [
        (
            g.prompt_id,
            g.model_id,
            g.calls,
            g.input_tokens,
            g.output_tokens,
            g.estimated_cost_usd,
            g.unpriced_calls,
        )
        for g in summary.groups
    ] == [
        (None, "test.embed", 1, 400, 0, 0.0625, 0),
        ("landscape.classify", "test.haiku", 2, 300, 30, 0.75, 0),
        ("landscape.classify", "test.unpriced", 1, 300, 30, 0.0, 1),
        ("model.repair", "test.haiku", 1, 50, 5, 0.125, 0),
    ]
    assert (summary.calls, summary.input_tokens, summary.output_tokens) == (5, 1050, 65)
    assert (summary.estimated_cost_usd, summary.unpriced_calls) == (0.9375, 1)


# ---------------------------------------------------------------------------------------------
# Where the recorder sits: wrapped round the real router by build_model_router
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def no_inherited_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


def bedrock_settings(tmp_path: Path, **models: object) -> Settings:
    """The test profile on the bedrock provider, the example routing file, and no budget."""
    return load_settings(
        environment="test",
        overrides={
            "models": {
                "provider": "bedrock",
                "routing_file": str(REPOSITORY_ROOT / "config" / "model_routing.example.yaml"),
                "budget_usd_daily": None,
            }
            | models,
            "storage": {"data_dir": str(tmp_path / "data")},
        },
        env_file=tmp_path / "no.env",
    )


@pytest.mark.usefixtures("no_inherited_settings")
@pytest.mark.parametrize("mode", ["live", "record"])
async def test_record_build_model_router_logs_real_calls_in_live_and_record_mode(
    mode: str, tmp_path: Path, pricing_file: Path
) -> None:
    settings = bedrock_settings(tmp_path)
    delegate = MeteredRouter([(VALID, 2000, 400)], routing=RoutingPolicy.from_settings(settings))

    def real_router(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
        return delegate

    router = build_model_router(
        settings,
        mode=mode,
        environ={},
        real_router=real_router,
        cassette_dir=tmp_path / "cassettes",
        clock=FixedClock(LATE_EVENING),
        run_id="run-from-the-factory",
        pricing_file=pricing_file,
        usage_log=UsageLog.for_data_dir(settings.storage.data_dir, local_zone=CHICAGO),
    )

    await router.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    [written] = lines(tmp_path / "data" / "usage" / "2026-09-17.jsonl")
    assert (written["run_id"], written["model_id"], written["input_tokens"]) == (
        "run-from-the-factory",
        "anthropic.claude-haiku-5-5",
        2000,
    )


@pytest.mark.usefixtures("no_inherited_settings")
async def test_record_build_model_router_logs_nothing_on_replay_or_the_fake(tmp_path: Path) -> None:
    settings = bedrock_settings(tmp_path)
    cassettes = tmp_path / "cassettes"

    def real_router(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
        return MeteredRouter([(VALID, 2000, 400)], routing=policy)

    recording = build_model_router(
        settings,
        mode="record",
        environ={},
        real_router=real_router,
        cassette_dir=cassettes,
        clock=FixedClock(LATE_EVENING),
        usage_log=UsageLog.for_data_dir(settings.storage.data_dir, local_zone=CHICAGO),
    )
    await recording.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)
    day_file = tmp_path / "data" / "usage" / "2026-09-17.jsonl"
    assert len(lines(day_file)) == 1

    replaying = build_model_router(settings, mode="replay", environ={}, cassette_dir=cassettes)
    await replaying.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)
    fake = build_model_router(bedrock_settings(tmp_path, provider="fake"), repository_root=REPOSITORY_ROOT)
    await fake.generate_structured(TaskClass.HIGH_VOLUME, example_prompt(), ContractPassage)

    assert len(lines(day_file)) == 1
    assert sorted(path.name for path in (tmp_path / "data" / "usage").iterdir()) == ["2026-09-17.jsonl"]

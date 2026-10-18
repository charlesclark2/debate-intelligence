"""The Bedrock adapter, against a botocore `Stubber`: no network, no AWS account, no credential.

The client is a real `bedrock-runtime` client, so every request the adapter makes is validated
against Bedrock's own service model before the Stubber answers, and every planned response against
the operation's output shape. The Stubber answers from a queue: a test that leaves a planned answer
unconsumed, or makes a call nobody planned, fails. So a test that plans one answer and then sees a
failure has also shown that the call was sent exactly once.

The routing policy uses made-up identifiers and a made-up region. The real ones live only in
`config/model_routing.*.yaml`, and no test names them (the task spec forbids it).

The plan nodes select from this file by name: `-k client`, `-k structured`, `-k "embed or rerank"`.
Retries and the shared contract run with the whole directory.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from pydantic import BaseModel, ConfigDict

from debate_core.application.errors import (
    InvalidModelOutput,
    ModelAccessDenied,
    ModelRequestRejected,
    ModelUnavailableError,
    ProviderRateLimited,
)
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.settings import ConfigurationError
from debate_core.domain.model_contracts import (
    Effort,
    ModelParams,
    ModelPrompt,
    ModelProvider,
    RenderedPrompt,
    TaskClass,
)
from debate_core.integrations.bedrock import bedrock_model_router
from debate_core.integrations.bedrock.failures import RETRIED_CODES
from debate_core.integrations.bedrock.first_call import PROBE_MAX_TOKENS, run_first_call
from debate_core.integrations.bedrock.router import (
    CONNECT_TIMEOUT_SECONDS,
    BedrockModelRouter,
    build_bedrock_runtime_client,
    client_config,
)
from debate_core.integrations.models import ModelRoute, RoutingPolicy
from debate_core.testing import FixedClock
from debate_core.testing.contracts import (
    EmbeddingAnswer,
    ModelRouterContract,
    ModelRouterFactory,
    PlannedAnswer,
    RerankAnswer,
    RouteExpectation,
    StructuredAnswer,
)

pytestmark = pytest.mark.anyio

TEST_REGION = "test-region-1"
"""A region name botocore accepts and AWS does not have."""

REQUEST_ID = "request-0001"
INVOKED_AT = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class PassageChoice(BaseModel):
    """Name the passage that supports the tag, by paragraph and offsets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paragraph_id: int
    start_offset: int
    end_offset: int


TOOL = "PassageChoice"
ANSWER: dict[str, Any] = {"paragraph_id": 4, "start_offset": 10, "end_offset": 90}
PROMPT = ModelPrompt(
    prompt_id="test.choose-passage", prompt_version="2.1.0", variables={"tag": "Tariffs fail"}
)


def _route(task_class: TaskClass, **fields: Any) -> ModelRoute:
    model_id = f"provider-model-{task_class.value.replace('_', '-')}"
    defaults: dict[str, Any] = {
        "provider": ModelProvider.BEDROCK,
        "model_id": model_id,
        "region": TEST_REGION,
        "timeout_seconds": 30,
    }
    if task_class.is_generative:
        defaults |= {"inference_profile": f"geo.{model_id}", "max_tokens": 512}
    return ModelRoute(**(defaults | fields))


def routing_policy(**overrides: Mapping[str, Any]) -> RoutingPolicy:
    """Every class routed, with `overrides` (keyed by task class value) merged into its route."""
    return RoutingPolicy(
        routes={
            task_class: _route(task_class, **overrides.get(task_class.value, {})) for task_class in TaskClass
        }
    )


def render_for_tests(prompt: ModelPrompt) -> RenderedPrompt:
    """A renderer for these tests only: the prompt's identity and variables, as text."""
    return RenderedPrompt(
        system=f"system text for {prompt.prompt_id}",
        user=f"{prompt.prompt_id}@{prompt.prompt_version} {json.dumps(prompt.variables, sort_keys=True)}",
    )


def tool_use(name: str, answer: Mapping[str, Any], tool_use_id: str = "tooluse-1") -> dict[str, Any]:
    """A Converse content block calling tool `name` with `answer` as its input."""
    return {"toolUse": {"toolUseId": tool_use_id, "name": name, "input": dict(answer)}}


@dataclass
class StubbedBedrock:
    """One stubbed `bedrock-runtime` client, the answers planned for it, and the waits taken."""

    client: Any
    stubber: Stubber
    built: list[tuple[str, float]] = field(default_factory=list[tuple[str, float]])
    """Every (region, timeout) the router asked for a client with."""
    waits: list[float] = field(default_factory=list[float])
    """Every wait the router took between attempts, in seconds."""

    def factory(self, region: str, timeout_seconds: float) -> Any:
        self.built.append((region, timeout_seconds))
        return self.client

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)

    def router(self, policy: RoutingPolicy | None = None, **options: Any) -> BedrockModelRouter:
        """A router on `policy` that calls this client and records its waits instead of taking them.

        The jitter returns the ceiling it is given, so a recorded wait is the backoff's ceiling.
        """
        settings: dict[str, Any] = {
            "render_prompt": render_for_tests,
            "client_factory": self.factory,
            "clock": FixedClock(INVOKED_AT),
            "sleep": self.sleep,
            "jitter": lambda ceiling: ceiling,  # pyright: ignore[reportUnknownLambdaType]
        }
        return BedrockModelRouter(policy or routing_policy(), **(settings | options))

    def add_converse(
        self,
        content: list[dict[str, Any]],
        *,
        stop_reason: str = "tool_use",
        expected: Mapping[str, Any] | None = None,
        request_id: str = REQUEST_ID,
        input_tokens: int = 120,
        output_tokens: int = 18,
    ) -> None:
        response = {
            "output": {"message": {"role": "assistant", "content": content}},
            "stopReason": stop_reason,
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": input_tokens + output_tokens,
            },
            "metrics": {"latencyMs": 850},
            "ResponseMetadata": {"RequestId": request_id, "HTTPStatusCode": 200},
        }
        self.stubber.add_response("converse", response, dict(expected) if expected is not None else None)

    def add_answer(self, answer: Mapping[str, Any] = ANSWER, name: str = TOOL, **options: Any) -> None:
        self.add_converse([tool_use(name, answer)], **options)

    def add_invoke(
        self,
        body: Mapping[str, Any],
        *,
        expected: Mapping[str, Any] | None = None,
        request_id: str = REQUEST_ID,
    ) -> None:
        raw = json.dumps(body).encode("utf-8")
        response = {
            "body": StreamingBody(io.BytesIO(raw), len(raw)),
            "contentType": "application/json",
            "ResponseMetadata": {"RequestId": request_id, "HTTPStatusCode": 200},
        }
        self.stubber.add_response("invoke_model", response, dict(expected) if expected is not None else None)

    def add_error(self, operation: str, code: str, status: int, message: str = "refused") -> None:
        self.stubber.add_client_error(
            operation, service_error_code=code, service_message=message, http_status_code=status
        )


@pytest.fixture
def stubbed(fake_aws_credentials: None) -> Iterator[StubbedBedrock]:
    """A stubbed client; every planned answer must have been consumed when the test ends."""
    client: Any = build_bedrock_runtime_client(TEST_REGION, 30)
    with Stubber(client) as stubber:
        double = StubbedBedrock(client=client, stubber=stubber)
        yield double
        stubber.assert_no_pending_responses()


async def choose(router: ModelRouter, task_class: TaskClass = TaskClass.HIGH_VOLUME, **params: Any) -> Any:
    return await router.generate_structured(task_class, PROMPT, PassageChoice, ModelParams(**params))


# ---------------------------------------------------------------------------------------------
# The client: region, timeouts, credentials
# ---------------------------------------------------------------------------------------------


def test_the_client_config_bounds_connect_and_read_by_the_route_and_turns_botocore_retries_off() -> None:
    config: Any = client_config(300)

    assert (config.connect_timeout, config.read_timeout) == (CONNECT_TIMEOUT_SECONDS, 300)
    assert config.retries == {"total_max_attempts": 1, "mode": "standard"}


def test_the_client_connect_timeout_is_never_longer_than_the_call() -> None:
    config: Any = client_config(2)

    assert config.connect_timeout == 2


def test_the_client_is_built_from_the_region_and_profile_free_credential_chain(
    fake_aws_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Region and timeout in, nothing else: no key, no profile, no account."""
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    real_session = boto3.session.Session

    class SpySession(real_session):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(boto3.session, "Session", SpySession)

    client: Any = build_bedrock_runtime_client(TEST_REGION, 45)

    assert calls == [((), {"region_name": TEST_REGION})]
    assert client.meta.service_model.service_name == "bedrock-runtime"
    assert client.meta.region_name == TEST_REGION
    assert client.meta.config.read_timeout == 45


def test_the_client_for_a_profile_the_aws_config_lacks_is_a_typed_refusal(
    fake_aws_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_PROFILE", "a-profile-nobody-defined")

    with pytest.raises(ModelAccessDenied, match="AWS_PROFILE"):
        build_bedrock_runtime_client(TEST_REGION, 30)


async def test_the_client_comes_from_the_routes_region_and_timeout(stubbed: StubbedBedrock) -> None:
    policy = routing_policy(high_volume={"region": "test-region-2", "timeout_seconds": 12})
    stubbed.add_answer()

    await choose(stubbed.router(policy))

    assert stubbed.built == [("test-region-2", 12)]


async def test_a_client_is_built_once_per_region_and_timeout(stubbed: StubbedBedrock) -> None:
    router = stubbed.router()
    for _ in range(3):
        stubbed.add_answer()
    await choose(router)
    await choose(router)
    await choose(router, timeout_seconds=5)

    assert stubbed.built == [(TEST_REGION, 30), (TEST_REGION, 5)]


def test_the_client_factory_for_build_model_router_builds_a_bedrock_router() -> None:
    """`bedrock_model_router` is a `RealRouterFactory`: give it a policy, get a router, send nothing."""
    router = bedrock_model_router(routing_policy())

    assert isinstance(router, BedrockModelRouter)


# ---------------------------------------------------------------------------------------------
# Structured output through tool use (ac2, ac5, ac6)
# ---------------------------------------------------------------------------------------------


async def test_structured_output_sends_the_schema_as_the_single_tool_with_tool_choice_auto(
    stubbed: StubbedBedrock,
) -> None:
    """The whole request, written out by hand: one tool, `auto`, and nothing the route did not set."""
    description = "Name the passage that supports the tag, by paragraph and offsets."
    expected: dict[str, Any] = {
        "modelId": "geo.provider-model-high-volume",
        "messages": [
            {"role": "user", "content": [{"text": 'test.choose-passage@2.1.0 {"tag": "Tariffs fail"}'}]}
        ],
        "system": [{"text": "system text for test.choose-passage"}],
        "toolConfig": {
            "tools": [
                {
                    "toolSpec": {
                        "name": "PassageChoice",
                        "description": description,
                        "inputSchema": {
                            "json": {
                                "additionalProperties": False,
                                "description": description,
                                "properties": {
                                    "paragraph_id": {"title": "Paragraph Id", "type": "integer"},
                                    "start_offset": {"title": "Start Offset", "type": "integer"},
                                    "end_offset": {"title": "End Offset", "type": "integer"},
                                },
                                "required": ["paragraph_id", "start_offset", "end_offset"],
                                "title": "PassageChoice",
                                "type": "object",
                            }
                        },
                    }
                }
            ],
            "toolChoice": {"auto": {}},
        },
        "inferenceConfig": {"maxTokens": 512},
    }
    stubbed.add_answer(expected=expected)

    response = await choose(stubbed.router())

    assert response.output == PassageChoice(paragraph_id=4, start_offset=10, end_offset=90)


@pytest.mark.parametrize(
    "task_class", [TaskClass.COMPLEX_REASONING, TaskClass.HIGH_VOLUME, TaskClass.DEEP_AUDIT]
)
async def test_structured_output_never_forces_the_tool(
    task_class: TaskClass, stubbed: StubbedBedrock
) -> None:
    sent: list[dict[str, Any]] = []
    stubbed.client.meta.events.register(
        "provide-client-params.bedrock-runtime.Converse",
        lambda params, **_: sent.append(params),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    stubbed.add_answer()

    await choose(stubbed.router(), task_class)

    assert [request["toolConfig"]["toolChoice"] for request in sent] == [{"auto": {}}]
    assert len(sent[0]["toolConfig"]["tools"]) == 1


async def test_structured_output_parses_the_tool_input_into_the_schema(stubbed: StubbedBedrock) -> None:
    stubbed.add_converse([{"text": "Here is the passage."}, tool_use(TOOL, ANSWER)])

    response = await choose(stubbed.router())

    assert isinstance(response.output, PassageChoice)
    assert response.output.model_dump() == ANSWER


async def test_structured_output_with_no_tool_call_is_invalid_output_naming_the_prompt(
    stubbed: StubbedBedrock,
) -> None:
    """`auto` lets the model answer in prose. That is invalid output, for t05's guard to repair."""
    stubbed.add_converse([{"text": "Paragraph four, I think."}], stop_reason="end_turn")

    with pytest.raises(InvalidModelOutput, match="did not call the PassageChoice tool") as raised:
        await choose(stubbed.router())

    assert (raised.value.prompt_id, raised.value.prompt_version) == ("test.choose-passage", "2.1.0")
    assert raised.value.model_id == "provider-model-high-volume"


async def test_structured_output_from_another_tool_is_not_an_answer(stubbed: StubbedBedrock) -> None:
    stubbed.add_converse([tool_use("SomethingElse", ANSWER)])

    with pytest.raises(InvalidModelOutput, match="did not call the PassageChoice tool"):
        await choose(stubbed.router())


async def test_structured_output_called_twice_is_refused_rather_than_picked_from(
    stubbed: StubbedBedrock,
) -> None:
    stubbed.add_converse([tool_use(TOOL, ANSWER, "tooluse-1"), tool_use(TOOL, ANSWER, "tooluse-2")])

    with pytest.raises(InvalidModelOutput, match="2 times"):
        await choose(stubbed.router())


async def test_structured_output_that_fails_the_schema_is_invalid_output(stubbed: StubbedBedrock) -> None:
    stubbed.add_answer({"paragraph_id": "the fourth", "start_offset": 10, "end_offset": 90})

    with pytest.raises(InvalidModelOutput, match="paragraph_id"):
        await choose(stubbed.router())


@pytest.mark.parametrize("stop_reason", ["max_tokens", "guardrail_intervened", "content_filtered"])
async def test_structured_output_cut_off_or_withheld_is_invalid_even_with_a_tool_call(
    stop_reason: str, stubbed: StubbedBedrock
) -> None:
    stubbed.add_answer(stop_reason=stop_reason)

    with pytest.raises(InvalidModelOutput, match=stop_reason):
        await choose(stubbed.router())


@pytest.mark.parametrize("stop_reason", ["tool_use", "end_turn"])
async def test_structured_output_is_accepted_on_a_finished_turn(
    stop_reason: str, stubbed: StubbedBedrock
) -> None:
    stubbed.add_answer(stop_reason=stop_reason)

    assert (await choose(stubbed.router())).output.paragraph_id == 4


async def test_structured_output_reports_usage_from_the_response(stubbed: StubbedBedrock) -> None:
    stubbed.add_answer(input_tokens=321, output_tokens=45)

    usage = (await choose(stubbed.router())).usage

    assert (usage.input_tokens, usage.output_tokens) == (321, 45)
    assert usage.latency_ms >= 0


async def test_structured_output_reports_model_profile_region_and_request_id(stubbed: StubbedBedrock) -> None:
    """ac5: the resolved model id, inference profile, region and the provider's request id."""
    stubbed.add_answer(request_id="bedrock-request-77")

    response = await choose(stubbed.router(), TaskClass.DEEP_AUDIT)

    assert response.route.model_id == "provider-model-deep-audit"
    assert response.route.inference_profile == "geo.provider-model-deep-audit"
    assert response.route.region == TEST_REGION
    assert response.provider_request_id == "bedrock-request-77"
    assert response.invoked_at == INVOKED_AT


async def test_structured_output_sends_the_routes_effort_as_output_config(stubbed: StubbedBedrock) -> None:
    """ac6: a route's effort is sent as Converse `outputConfig.effort` and reported on the route."""
    policy = routing_policy(deep_audit={"effort": "xhigh"})
    sent: list[dict[str, Any]] = []
    stubbed.client.meta.events.register(
        "provide-client-params.bedrock-runtime.Converse",
        lambda params, **_: sent.append(params),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    stubbed.add_answer()

    response = await choose(stubbed.router(policy), TaskClass.DEEP_AUDIT)

    assert sent[0]["outputConfig"] == {"effort": "xhigh"}
    assert response.route.effort is Effort.XHIGH


async def test_structured_output_sends_a_per_call_effort_over_the_routes(stubbed: StubbedBedrock) -> None:
    policy = routing_policy(deep_audit={"effort": "xhigh"})
    sent: list[dict[str, Any]] = []
    stubbed.client.meta.events.register(
        "provide-client-params.bedrock-runtime.Converse",
        lambda params, **_: sent.append(params),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    stubbed.add_answer()

    response = await choose(stubbed.router(policy), TaskClass.DEEP_AUDIT, effort=Effort.LOW)

    assert sent[0]["outputConfig"] == {"effort": "low"}
    assert response.route.effort is Effort.LOW


async def test_structured_output_sends_no_effort_temperature_or_output_config_the_route_lacks(
    stubbed: StubbedBedrock,
) -> None:
    sent: list[dict[str, Any]] = []
    stubbed.client.meta.events.register(
        "provide-client-params.bedrock-runtime.Converse",
        lambda params, **_: sent.append(params),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    stubbed.add_answer()

    await choose(stubbed.router(routing_policy(high_volume={"max_tokens": None})))

    assert "outputConfig" not in sent[0]
    assert "inferenceConfig" not in sent[0]


async def test_structured_output_sends_a_temperature_only_when_one_is_set(stubbed: StubbedBedrock) -> None:
    sent: list[dict[str, Any]] = []
    stubbed.client.meta.events.register(
        "provide-client-params.bedrock-runtime.Converse",
        lambda params, **_: sent.append(params),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    stubbed.add_answer()
    stubbed.add_answer()
    router = stubbed.router()

    await choose(router)
    await choose(router, temperature=0.0)

    assert [request["inferenceConfig"] for request in sent] == [
        {"maxTokens": 512},
        {"maxTokens": 512, "temperature": 0.0},
    ]


async def test_structured_output_without_a_prompt_renderer_sends_nothing(stubbed: StubbedBedrock) -> None:
    """Until the prompt registry (t04) is wired in, a call fails closed before anything is sent."""
    router = BedrockModelRouter(routing_policy(), client_factory=stubbed.factory)

    with pytest.raises(ConfigurationError, match="v1-e05-t04-prompt-registry"):
        await choose(router)

    assert stubbed.built == []


# ---------------------------------------------------------------------------------------------
# Embeddings and rerank
# ---------------------------------------------------------------------------------------------


async def test_embed_sends_one_titan_request_per_text_in_order(stubbed: StubbedBedrock) -> None:
    for text, vector, request_id in (
        ("first text", [0.1, 0.2], "embed-1"),
        ("second text", [0.3, 0.4], "embed-2"),
    ):
        stubbed.add_invoke(
            {"embedding": vector, "inputTextTokenCount": 3},
            expected={
                "modelId": "provider-model-embeddings",
                "contentType": "application/json",
                "accept": "application/json",
                "body": json.dumps({"inputText": text}).encode("utf-8"),
            },
            request_id=request_id,
        )

    response = await stubbed.router().embed(["first text", "second text"])

    assert response.vectors == ((0.1, 0.2), (0.3, 0.4))
    assert response.usage.input_tokens == 6
    assert response.usage.output_tokens is None
    assert response.route.model_id == "provider-model-embeddings"
    assert response.provider_request_id == "embed-1"


async def test_embed_asks_for_the_dimensions_the_route_names(stubbed: StubbedBedrock) -> None:
    stubbed.add_invoke(
        {"embedding": [0.5] * 4, "inputTextTokenCount": 2},
        expected={
            "modelId": "provider-model-embeddings",
            "contentType": "application/json",
            "accept": "application/json",
            "body": json.dumps({"inputText": "a text", "dimensions": 256}).encode("utf-8"),
        },
    )

    await stubbed.router(routing_policy(embeddings={"dimensions": 256})).embed(["a text"])


async def test_embed_reports_no_token_count_when_a_response_lacks_one(stubbed: StubbedBedrock) -> None:
    stubbed.add_invoke({"embedding": [0.1], "inputTextTokenCount": 3})
    stubbed.add_invoke({"embedding": [0.2]})

    response = await stubbed.router().embed(["one", "two"])

    assert response.usage.input_tokens is None


@pytest.mark.parametrize("body", [{"embedding": []}, {"embedding": ["x"]}, {"vectors": [[0.1]]}])
async def test_embed_refuses_a_response_with_no_usable_vector(
    body: dict[str, Any], stubbed: StubbedBedrock
) -> None:
    stubbed.add_invoke(body)

    with pytest.raises(ModelUnavailableError, match="embedding"):
        await stubbed.router().embed(["a text"])


async def test_rerank_sends_every_document_in_one_cohere_request(stubbed: StubbedBedrock) -> None:
    stubbed.add_invoke(
        {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]},
        expected={
            "modelId": "provider-model-rerank",
            "contentType": "application/json",
            "accept": "application/json",
            "body": json.dumps(
                {"query": "does it?", "documents": ["card a", "card b"], "top_n": 2, "api_version": 2}
            ).encode("utf-8"),
        },
        request_id="rerank-1",
    )

    response = await stubbed.router().rerank("does it?", ["card a", "card b"])

    assert [(result.index, result.relevance_score) for result in response.results] == [(1, 0.9), (0, 0.2)]
    assert response.provider_request_id == "rerank-1"
    assert response.route.model_id == "provider-model-rerank"


async def test_rerank_orders_results_best_first_whatever_order_they_arrive_in(
    stubbed: StubbedBedrock,
) -> None:
    stubbed.add_invoke(
        {
            "results": [
                {"index": 0, "relevance_score": 0.2},
                {"index": 2, "relevance_score": 0.05},
                {"index": 1, "relevance_score": 0.9},
            ]
        }
    )

    response = await stubbed.router().rerank("q", ["a", "b", "c"])

    assert [result.index for result in response.results] == [1, 0, 2]


@pytest.mark.parametrize(
    "results",
    [
        [{"index": 0, "relevance_score": 0.2}],
        [{"index": 0, "relevance_score": 0.2}, {"index": 0, "relevance_score": 0.1}],
        [{"index": 0, "relevance_score": 0.2}, {"index": 5, "relevance_score": 0.1}],
        [{"index": 0}, {"index": 1, "relevance_score": 0.1}],
    ],
)
async def test_rerank_refuses_results_that_do_not_name_each_document_once(
    results: list[dict[str, Any]], stubbed: StubbedBedrock
) -> None:
    stubbed.add_invoke({"results": results})

    with pytest.raises(ModelUnavailableError, match="rerank|result|documents"):
        await stubbed.router().rerank("q", ["a", "b"])


# ---------------------------------------------------------------------------------------------
# Retries (ac3)
# ---------------------------------------------------------------------------------------------


async def test_retry_a_throttled_call_until_it_succeeds_counting_each_attempt(
    stubbed: StubbedBedrock,
) -> None:
    """Two throttles, then an answer: three requests, two waits, and the answer is returned."""
    stubbed.add_error("converse", "ThrottlingException", 429)
    stubbed.add_error("converse", "ThrottlingException", 429)
    stubbed.add_answer()

    response = await choose(stubbed.router())

    assert response.output.paragraph_id == 4
    assert len(stubbed.waits) == 2  # three attempts: the Stubber's queue of three is empty


async def test_retry_stops_at_the_routes_attempts_and_reports_the_rate_limit(stubbed: StubbedBedrock) -> None:
    policy = routing_policy(high_volume={"max_attempts": 4})
    for _ in range(4):
        stubbed.add_error("converse", "ThrottlingException", 429, "Too many requests")

    with pytest.raises(ProviderRateLimited, match="after 4 attempts") as raised:
        await choose(stubbed.router(policy))

    assert raised.value.provider == "bedrock"
    assert len(stubbed.waits) == 3


async def test_retry_bound_of_one_attempt_sends_once(stubbed: StubbedBedrock) -> None:
    stubbed.add_error("converse", "ThrottlingException", 429)

    with pytest.raises(ProviderRateLimited):
        await choose(stubbed.router(routing_policy(high_volume={"max_attempts": 1})))

    assert stubbed.waits == []


@pytest.mark.parametrize(
    ("code", "status"),
    [("ServiceUnavailableException", 503), ("ModelNotReadyException", 429), ("InternalServerException", 500)],
)
async def test_retry_an_unavailable_model_then_report_it_unavailable(
    code: str, status: int, stubbed: StubbedBedrock
) -> None:
    for _ in range(3):
        stubbed.add_error("converse", code, status)

    with pytest.raises(ModelUnavailableError, match=f"{code} after 3 attempts") as raised:
        await choose(stubbed.router())

    assert raised.value.model_id == "geo.provider-model-high-volume"
    assert len(stubbed.waits) == 2


@pytest.mark.parametrize(
    ("code", "status", "raised"),
    [
        ("ValidationException", 400, ModelRequestRejected),
        ("ResourceNotFoundException", 404, ModelRequestRejected),
        ("AccessDeniedException", 403, ModelAccessDenied),
        ("UnrecognizedClientException", 403, ModelAccessDenied),
        ("ExpiredTokenException", 403, ModelAccessDenied),
        ("ModelTimeoutException", 408, ModelUnavailableError),
        ("ModelErrorException", 424, ModelUnavailableError),
        ("ServiceQuotaExceededException", 400, ModelRequestRejected),
    ],
)
async def test_retry_never_resends_a_refusal_a_validation_error_or_a_model_that_ran(
    code: str, status: int, raised: type[Exception], stubbed: StubbedBedrock
) -> None:
    """One planned answer: a second attempt would find the Stubber's queue empty and fail differently."""
    stubbed.add_error("converse", code, status)

    with pytest.raises(raised, match=code):
        await choose(stubbed.router())

    assert stubbed.waits == []


async def test_retry_validation_error_keeps_the_providers_code_for_the_first_real_call(
    stubbed: StubbedBedrock,
) -> None:
    stubbed.add_error("converse", "ValidationException", 400, "temperature: not supported for this model")

    with pytest.raises(ModelRequestRejected) as raised:
        await choose(stubbed.router(), temperature=0.5)

    assert raised.value.provider_code == "ValidationException"
    assert "temperature" in str(raised.value)


def test_retry_codes_are_exactly_the_throttle_and_the_passing_outages() -> None:
    assert (
        frozenset(
            {
                "ThrottlingException",
                "ServiceUnavailableException",
                "ModelNotReadyException",
                "InternalServerException",
            }
        )
        == RETRIED_CODES
    )


async def test_retry_waits_grow_by_doubling_up_to_the_cap(stubbed: StubbedBedrock) -> None:
    """The jitter here returns its ceiling, so the waits are the ceilings: 1, 2, 4, 8, 10, 10, 10."""
    policy = routing_policy(high_volume={"max_attempts": 8})
    for _ in range(7):
        stubbed.add_error("converse", "ThrottlingException", 429)
    stubbed.add_answer()

    await choose(stubbed.router(policy, backoff_base_seconds=1.0, backoff_cap_seconds=10.0))

    assert stubbed.waits == [1.0, 2.0, 4.0, 8.0, 10.0, 10.0, 10.0]


async def test_retry_waits_are_jittered_below_their_ceiling(stubbed: StubbedBedrock) -> None:
    ceilings: list[float] = []

    def quarter(ceiling: float) -> float:
        ceilings.append(ceiling)
        return ceiling / 4

    stubbed.add_error("converse", "ThrottlingException", 429)
    stubbed.add_error("converse", "ThrottlingException", 429)
    stubbed.add_answer()

    await choose(stubbed.router(jitter=quarter, backoff_base_seconds=2.0))

    assert ceilings == [2.0, 4.0]
    assert stubbed.waits == [0.5, 1.0]


def test_retry_default_jitter_stays_between_zero_and_the_ceiling() -> None:
    from debate_core.integrations.bedrock.router import full_jitter

    draws = [full_jitter(3.0) for _ in range(200)]

    assert all(0.0 <= draw <= 3.0 for draw in draws)
    assert len(set(draws)) > 1


async def test_retry_applies_to_embeddings_and_rerank_too(stubbed: StubbedBedrock) -> None:
    stubbed.add_error("invoke_model", "ThrottlingException", 429)
    stubbed.add_invoke({"embedding": [0.1], "inputTextTokenCount": 1})
    stubbed.add_error("invoke_model", "ValidationException", 400)

    router = stubbed.router()
    await router.embed(["a text"])
    with pytest.raises(ModelRequestRejected):
        await router.rerank("q", ["a"])

    assert len(stubbed.waits) == 1


def test_a_backoff_with_no_positive_base_is_refused() -> None:
    with pytest.raises(ValueError, match="backoff"):
        BedrockModelRouter(routing_policy(), backoff_base_seconds=0)


# ---------------------------------------------------------------------------------------------
# The shared ModelRouter contract (ac1)
# ---------------------------------------------------------------------------------------------


class TestBedrockModelRouterContract(ModelRouterContract):
    """The contract every router passes, with Bedrock's answers played by the Stubber."""

    @pytest.fixture
    def policy(self) -> RoutingPolicy:
        return routing_policy()

    @pytest.fixture
    def expected_route(self, policy: RoutingPolicy) -> RouteExpectation:
        return policy.resolve

    @pytest.fixture
    def make_router(self, stubbed: StubbedBedrock, policy: RoutingPolicy) -> ModelRouterFactory:
        def build(answers: Sequence[PlannedAnswer]) -> ModelRouter:
            for answer in answers:
                plan(stubbed, answer)
            return stubbed.router(policy)

        return build


def plan(stubbed: StubbedBedrock, answer: PlannedAnswer) -> None:
    """Turn one of the contract's planned answers into the Bedrock response that carries it."""
    match answer:
        case StructuredAnswer():
            name = answer.request.output_schema.rsplit(".", 1)[-1]
            stubbed.add_converse([tool_use(name, answer.answer)])
        case EmbeddingAnswer():
            for vector in answer.vectors:
                stubbed.add_invoke({"embedding": list(vector), "inputTextTokenCount": 4})
        case RerankAnswer():
            results = [
                {"index": index, "relevance_score": score} for index, score in enumerate(answer.scores)
            ]
            stubbed.add_invoke({"results": results})


# ---------------------------------------------------------------------------------------------
# The first real call (ac7): the operator's probe, against the Stubber
# ---------------------------------------------------------------------------------------------

FIRST_CALL_PROBES = [
    "toolChoice any",
    "toolChoice tool",
    "temperature 0.5",
    "effort low",
    "structured output",
    "strict tool",
]


def first_call_policy() -> RoutingPolicy:
    """One Claude-like route and the two scoring routes: what one probe run covers per class."""
    every = routing_policy()
    return RoutingPolicy(
        routes={
            task_class: every.routes[task_class]
            for task_class in (TaskClass.HIGH_VOLUME, TaskClass.EMBEDDINGS, TaskClass.RERANK)
        }
    )


async def test_first_call_asks_each_question_by_changing_the_adapters_request_in_one_way(
    stubbed: StubbedBedrock,
) -> None:
    sent: list[dict[str, Any]] = []
    stubbed.client.meta.events.register(
        "provide-client-params.bedrock-runtime.Converse",
        lambda params, **_: sent.append(params),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    stubbed.add_answer({"colour": "blue"}, name="ProbeAnswer")
    for _ in FIRST_CALL_PROBES:
        stubbed.add_converse([{"text": "ok"}], stop_reason="end_turn")
    stubbed.add_invoke({"embedding": [0.1, 0.2], "inputTextTokenCount": 2})
    stubbed.add_invoke(
        {"results": [{"index": 0, "relevance_score": 0.8}, {"index": 1, "relevance_score": 0.1}]}
    )

    findings = await run_first_call(first_call_policy(), client_factory=stubbed.factory)

    adapter_call, *variants = sent
    assert adapter_call["toolConfig"]["toolChoice"] == {"auto": {}}
    assert adapter_call["inferenceConfig"] == {"maxTokens": PROBE_MAX_TOKENS}
    assert [request["toolConfig"]["toolChoice"] for request in variants[:2]] == [
        {"any": {}},
        {"tool": {"name": "ProbeAnswer"}},
    ]
    assert variants[2]["inferenceConfig"] == {"maxTokens": PROBE_MAX_TOKENS, "temperature": 0.5}
    assert variants[3]["outputConfig"] == {"effort": "low"}
    assert "toolConfig" not in variants[4]
    assert variants[4]["outputConfig"]["textFormat"]["type"] == "json_schema"
    assert variants[5]["toolConfig"]["tools"][0]["toolSpec"]["strict"] is True
    assert [finding.outcome for finding in findings] == ["accepted"] * 9
    assert [finding.probe for finding in findings][1:7] == FIRST_CALL_PROBES


async def test_first_call_records_each_refusal_with_bedrocks_code_and_message(
    stubbed: StubbedBedrock,
) -> None:
    policy = RoutingPolicy(routes={TaskClass.HIGH_VOLUME: routing_policy().routes[TaskClass.HIGH_VOLUME]})
    stubbed.add_answer({"colour": "blue"}, name="ProbeAnswer")
    stubbed.add_error(
        "converse", "ValidationException", 400, "tool_choice any is not supported for this model"
    )
    stubbed.add_error(
        "converse", "ValidationException", 400, "tool_choice tool is not supported for this model"
    )
    stubbed.add_error("converse", "ValidationException", 400, "temperature: only the default is supported")
    stubbed.add_converse([{"text": "ok"}], stop_reason="end_turn")
    stubbed.add_error("converse", "ValidationException", 400, "structured outputs are not supported")
    stubbed.add_converse([{"text": "ok"}], stop_reason="end_turn")

    findings = await run_first_call(policy, client_factory=stubbed.factory)

    outcomes = {finding.probe: finding.outcome for finding in findings}
    assert outcomes == {
        "toolChoice auto (the adapter's call)": "accepted",
        "toolChoice any": "refused",
        "toolChoice tool": "refused",
        "temperature 0.5": "refused",
        "effort low": "accepted",
        "structured output": "refused",
        "strict tool": "accepted",
    }
    refusal = next(finding for finding in findings if finding.probe == "temperature 0.5")
    assert "ValidationException" in refusal.detail
    assert "only the default is supported" in refusal.detail


async def test_first_call_denied_access_stops_a_route_without_sending_the_rest(
    stubbed: StubbedBedrock,
) -> None:
    policy = RoutingPolicy(routes={TaskClass.HIGH_VOLUME: routing_policy().routes[TaskClass.HIGH_VOLUME]})
    stubbed.add_error(
        "converse", "AccessDeniedException", 403, "not authorized to perform bedrock:InvokeModel"
    )

    findings = await run_first_call(policy, client_factory=stubbed.factory)

    assert [finding.outcome for finding in findings] == ["refused"] + ["not tried"] * len(FIRST_CALL_PROBES)
    assert "bedrock:InvokeModel" in findings[0].detail


def test_first_call_table_is_markdown_the_report_can_hold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from debate_core.integrations.bedrock import first_call

    canned = [
        first_call.Finding(TaskClass.HIGH_VOLUME, "geo.provider-model", "toolChoice any", "refused", "a | b"),
        first_call.Finding(TaskClass.RERANK, "provider-reranker", "rerank two documents", "not tried", "x"),
    ]

    async def fake_run(policy: RoutingPolicy, **_: Any) -> list[first_call.Finding]:
        return canned

    monkeypatch.setattr(first_call, "run_first_call", fake_run)
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        "routes:\n  rerank:\n    provider: bedrock\n    model_id: m\n    region: r\n    timeout_seconds: 5\n",
        encoding="utf-8",
    )

    status = first_call.main(["--routing-file", str(routing)])

    assert status == 1  # a probe that could not run is not a finding
    assert capsys.readouterr().out.splitlines() == [
        "| Class | Called as | Probe | Outcome | Detail |",
        "|---|---|---|---|---|",
        "| high_volume | `geo.provider-model` | toolChoice any | refused | a \\| b |",
        "| rerank | `provider-reranker` | rerank two documents | not tried | x |",
    ]

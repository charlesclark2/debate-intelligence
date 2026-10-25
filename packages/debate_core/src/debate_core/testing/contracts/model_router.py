"""The contract every `ModelRouter` must pass: the Bedrock adapter, the fake and replay routers.

:mod:`debate_core.application.ports.model_router` says in prose what a router does. This class
says it in tests, so that a use case tested against a fake router is tested against the rules the
Bedrock adapter is held to (v1-e05-t02-bedrock-adapter, v1-e05-t03-fake-replay-models).

## Opting a router in

Subclass :class:`ModelRouterContract` in a `Test…` class and override `make_router`::

    class TestBedrockModelRouter(ModelRouterContract):
        @pytest.fixture
        def make_router(self, stubbed_client) -> ModelRouterFactory:
            def build(answers: Sequence[PlannedAnswer]) -> ModelRouter:
                for answer in answers:
                    stub_converse_response(stubbed_client, answer)
                return BedrockModelRouter(policy, client=stubbed_client)
            return build

A router is not storage, so the factory is told what the model will say. Each test passes the
:data:`PlannedAnswer` values for the calls it is about to make, in call order, and the binding turns
them into whatever its router consumes: a fake's script, a replay router's cassettes, a botocore
`Stubber`'s responses. What the contract then checks is what the router does with an answer:
validates it, attributes it, reports what it cost. It never reaches a real model.

Override `expected_route` as well when the router resolves routes through a
:class:`~debate_core.integrations.models.routing_policy.RoutingPolicy`, and the contract checks
the reported route field for field rather than only for being populated.

**This module imports pytest**, like every contract here, so only a test reaches it.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue

from debate_core.application.errors import InvalidModelOutput
from debate_core.application.ports.model_router import ModelRouter
from debate_core.domain.model_contracts import (
    ModelParams,
    ModelPrompt,
    ModelRequest,
    ResolvedRoute,
    TaskClass,
)
from debate_core.testing.contracts.harness import AdapterContract

__all__ = [
    "CONTRACT_DOCUMENTS",
    "CONTRACT_QUERY",
    "CONTRACT_TEXTS",
    "ContractPassage",
    "EmbeddingAnswer",
    "ModelRouterContract",
    "ModelRouterFactory",
    "PlannedAnswer",
    "RerankAnswer",
    "RouteExpectation",
    "StructuredAnswer",
]


class ContractPassage(BaseModel):
    """The output schema the contract asks for: which passage, by id and offsets, never its text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paragraph_id: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class StructuredAnswer:
    """What the model answers to one `generate_structured` request, before any validation.

    `answer` is the raw object a model returns (for Bedrock, a forced tool's input). It may be
    invalid on purpose: the contract checks that a router refuses it.
    """

    request: ModelRequest
    answer: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class EmbeddingAnswer:
    """The vectors a model returns for `texts`, one per text, in order."""

    texts: tuple[str, ...]
    vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class RerankAnswer:
    """The relevance scores a reranker returns for `documents`, one per document, in document order."""

    query: str
    documents: tuple[str, ...]
    scores: tuple[float, ...] = field(default=())


type PlannedAnswer = StructuredAnswer | EmbeddingAnswer | RerankAnswer
"""One answer a binding prepares its router to give."""

type ModelRouterFactory = Callable[[Sequence[PlannedAnswer]], ModelRouter]
"""Builds a router that will give `answers` to the calls a test makes, in that order."""

type RouteExpectation = Callable[[TaskClass, ModelParams], ResolvedRoute]
"""The route a router should report for a call: usually `RoutingPolicy.resolve`."""


CONTRACT_TEXTS = ("The first passage to embed.", "The second passage to embed.")
CONTRACT_QUERY = "Does warming cause extinction?"
CONTRACT_DOCUMENTS = ("A card about sea levels.", "A card about extinction.", "A card about tariffs.")
CONTRACT_SCORES = (0.2, 0.9, 0.05)
"""Scores in document order; the best document is the second, then the first, then the third."""

GENERATIVE_CLASSES = tuple(member for member in TaskClass if member.is_generative)
SCORING_CLASSES = tuple(member for member in TaskClass if not member.is_generative)

VALID_ANSWER: Mapping[str, JsonValue] = {"paragraph_id": 3, "start_offset": 0, "end_offset": 42}
INVALID_ANSWER: Mapping[str, JsonValue] = {"paragraph_id": "the third one", "start_offset": 0}
COERCIBLE_ANSWER: Mapping[str, JsonValue] = {"paragraph_id": "3", "start_offset": 0.0, "end_offset": 42}
"""Lax validation would accept every value here; strict validation refuses the first two (v1-e05-t05)."""
REFUSED_VALUE_MARKER = "contract-refused-value-marker"
"""Invented text an answer carries in a refused field; no error a router raises may repeat it."""


def contract_prompt(prompt_id: str = "contract.select-passage") -> ModelPrompt:
    """The prompt every contract call runs: an id, a version and variables, never prompt text."""
    return ModelPrompt(prompt_id=prompt_id, prompt_version="1.0.0", variables={"tag": "Warming kills"})


def planned_structured(
    task_class: TaskClass,
    answer: Mapping[str, JsonValue] = VALID_ANSWER,
    *,
    prompt: ModelPrompt | None = None,
    params: ModelParams | None = None,
) -> StructuredAnswer:
    """The answer to one `generate_structured` call the contract is about to make."""
    request = ModelRequest.build(task_class, prompt or contract_prompt(), ContractPassage, params)
    return StructuredAnswer(request=request, answer=answer)


class ModelRouterContract(AdapterContract):
    """Subclass this in a `Test…` class and override `make_router` to hold a router to the contract."""

    @pytest.fixture
    def make_router(self) -> ModelRouterFactory:
        """Return a factory building a router that gives the planned answers.

        A binding must override this. See this module's docstring.
        """
        raise NotImplementedError(
            "a ModelRouterContract binding must override the `make_router` fixture with a factory "
            "that builds a router giving the planned answers"
        )

    @pytest.fixture
    def expected_route(self) -> RouteExpectation | None:
        """The route a call should report, or `None` to check only that the route is populated.

        Overriding it (usually with `RoutingPolicy.resolve`) turns on the field-by-field checks.
        """
        return None

    # ----------------------------------------------------------------------------------------
    # Structured output
    # ----------------------------------------------------------------------------------------

    async def test_the_router_satisfies_the_port(self, make_router: ModelRouterFactory) -> None:
        assert isinstance(make_router([]), ModelRouter)

    @pytest.mark.parametrize("task_class", GENERATIVE_CLASSES)
    async def test_structured_output_is_an_instance_of_the_requested_schema(
        self, task_class: TaskClass, make_router: ModelRouterFactory
    ) -> None:
        router = make_router([planned_structured(task_class)])

        response = await router.generate_structured(task_class, contract_prompt(), ContractPassage)

        assert isinstance(response.output, ContractPassage)
        assert response.output == ContractPassage.model_validate(VALID_ANSWER)
        assert (response.prompt_id, response.prompt_version) == ("contract.select-passage", "1.0.0")

    @pytest.mark.parametrize("task_class", GENERATIVE_CLASSES)
    async def test_the_resolved_route_is_populated(
        self,
        task_class: TaskClass,
        make_router: ModelRouterFactory,
        expected_route: RouteExpectation | None,
    ) -> None:
        router = make_router([planned_structured(task_class)])

        route = (await router.generate_structured(task_class, contract_prompt(), ContractPassage)).route

        assert route.task_class is task_class
        assert route.model_id
        assert route.timeout_seconds > 0
        if expected_route is not None:
            assert route == expected_route(task_class, ModelParams())

    async def test_per_call_overrides_are_reported_on_the_route(
        self, make_router: ModelRouterFactory, expected_route: RouteExpectation | None
    ) -> None:
        params = ModelParams(temperature=0.5, max_tokens=64, timeout_seconds=7)
        router = make_router([planned_structured(TaskClass.HIGH_VOLUME, params=params)])

        response = await router.generate_structured(
            TaskClass.HIGH_VOLUME, contract_prompt(), ContractPassage, params
        )

        assert (response.route.temperature, response.route.max_tokens) == (0.5, 64)
        assert response.route.timeout_seconds == 7
        if expected_route is not None:
            assert response.route == expected_route(TaskClass.HIGH_VOLUME, params)

    async def test_usage_is_reported(self, make_router: ModelRouterFactory) -> None:
        router = make_router([planned_structured(TaskClass.HIGH_VOLUME)])

        response = await router.generate_structured(TaskClass.HIGH_VOLUME, contract_prompt(), ContractPassage)
        usage = response.usage

        assert usage.latency_ms >= 0
        assert usage.input_tokens is not None and usage.input_tokens >= 0
        assert usage.output_tokens is not None and usage.output_tokens >= 0

    async def test_an_answer_that_does_not_fit_the_schema_is_refused_naming_the_prompt(
        self, make_router: ModelRouterFactory
    ) -> None:
        prompt = contract_prompt("contract.invalid-answer")
        router = make_router([planned_structured(TaskClass.HIGH_VOLUME, INVALID_ANSWER, prompt=prompt)])

        with pytest.raises(InvalidModelOutput) as raised:
            await router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage)

        assert (raised.value.prompt_id, raised.value.prompt_version) == ("contract.invalid-answer", "1.0.0")

    async def test_an_answer_is_validated_strictly_without_coercion(
        self, make_router: ModelRouterFactory
    ) -> None:
        """Every router validates strictly, so no router hands a caller a coerced object (v1-e05-t05)."""
        prompt = contract_prompt("contract.coercible-answer")
        router = make_router([planned_structured(TaskClass.HIGH_VOLUME, COERCIBLE_ANSWER, prompt=prompt)])

        with pytest.raises(InvalidModelOutput) as raised:
            await router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage)

        assert [(problem.loc, problem.type) for problem in raised.value.problems] == [
            (("paragraph_id",), "int_type"),
            (("start_offset",), "int_type"),
        ]

    async def test_a_refused_answer_is_described_without_its_values(
        self, make_router: ModelRouterFactory
    ) -> None:
        """The error names where and why, never what the model said: an answer may hold source text."""
        prompt = contract_prompt("contract.refused-value")
        answer: Mapping[str, JsonValue] = {"paragraph_id": REFUSED_VALUE_MARKER, "start_offset": 0}
        router = make_router([planned_structured(TaskClass.HIGH_VOLUME, answer, prompt=prompt)])

        with pytest.raises(InvalidModelOutput) as raised:
            await router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage)

        error = raised.value
        assert {(problem.loc, problem.type) for problem in error.problems} == {
            (("paragraph_id",), "int_type"),
            (("end_offset",), "missing"),
        }
        assert REFUSED_VALUE_MARKER not in "".join(traceback.format_exception(error))
        assert REFUSED_VALUE_MARKER not in repr(error.args) + repr(error.problems)

    @pytest.mark.parametrize("task_class", SCORING_CLASSES)
    async def test_a_scoring_class_is_refused_before_anything_is_sent(
        self, task_class: TaskClass, make_router: ModelRouterFactory
    ) -> None:
        """Nothing is planned, so a router that sent the call would fail some other way."""
        router = make_router([])

        with pytest.raises(ValueError, match="embed or rerank"):
            await router.generate_structured(task_class, contract_prompt(), ContractPassage)

    # ----------------------------------------------------------------------------------------
    # Embeddings
    # ----------------------------------------------------------------------------------------

    async def test_embed_returns_one_vector_per_text_in_order(
        self, make_router: ModelRouterFactory, expected_route: RouteExpectation | None
    ) -> None:
        vectors = ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6))
        router = make_router([EmbeddingAnswer(texts=CONTRACT_TEXTS, vectors=vectors)])

        response = await router.embed(CONTRACT_TEXTS)

        assert response.vectors == vectors
        assert response.dimensions == 3
        assert response.route.task_class is TaskClass.EMBEDDINGS
        assert response.usage.latency_ms >= 0
        if expected_route is not None:
            assert response.route == expected_route(TaskClass.EMBEDDINGS, ModelParams())

    @pytest.mark.parametrize("texts", [(), ("a text", "   ")])
    async def test_embed_refuses_nothing_to_embed(
        self, texts: tuple[str, ...], make_router: ModelRouterFactory
    ) -> None:
        with pytest.raises(ValueError, match="text"):
            await make_router([]).embed(texts)

    # ----------------------------------------------------------------------------------------
    # Rerank
    # ----------------------------------------------------------------------------------------

    async def test_rerank_names_every_document_once_best_first(
        self, make_router: ModelRouterFactory, expected_route: RouteExpectation | None
    ) -> None:
        planned = RerankAnswer(query=CONTRACT_QUERY, documents=CONTRACT_DOCUMENTS, scores=CONTRACT_SCORES)
        router = make_router([planned])

        response = await router.rerank(CONTRACT_QUERY, CONTRACT_DOCUMENTS)

        assert [result.index for result in response.results] == [1, 0, 2]
        assert [result.relevance_score for result in response.results] == [0.9, 0.2, 0.05]
        assert response.route.task_class is TaskClass.RERANK
        assert response.usage.latency_ms >= 0
        if expected_route is not None:
            assert response.route == expected_route(TaskClass.RERANK, ModelParams())

    @pytest.mark.parametrize(("query", "documents"), [(CONTRACT_QUERY, ()), ("  ", CONTRACT_DOCUMENTS)])
    async def test_rerank_refuses_a_blank_query_or_no_documents(
        self, query: str, documents: tuple[str, ...], make_router: ModelRouterFactory
    ) -> None:
        with pytest.raises(ValueError, match="query|document"):
            await make_router([]).rerank(query, documents)

"""The `ModelRouter` contract runs, against a stand-in written here and against the shipped fake.

The contract is what the Bedrock adapter (v1-e05-t02) and the fake and replay routers (v1-e05-t03)
must pass, so it is written against the port, not against any of them. Two bindings prove it runs
before they exist:

* :class:`StandInModelRouter`, a minimal router written in this file and nowhere else. It resolves
  routes through a :class:`RoutingPolicy`, as a real adapter does, so its binding switches on the
  contract's field-by-field route checks. Its identifiers are made up; real ones live only in
  `config/model_routing.*.yaml`.
* The `ScriptedModelRouter` that `debate_core.testing` ships, so the scripted fake other packages'
  tests wire in really is a `ModelRouter`. The fixture-keyed `FakeModelRouter` and the
  `RecordReplayModelRouter` are bound beside their own tests, in
  `packages/debate_core/tests/integrations/models/`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest
from pydantic import BaseModel, ValidationError

from debate_core.application.errors import InvalidModelOutput, ProviderUnavailable
from debate_core.application.ports.model_router import ModelRouter
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    RerankResponse,
    RerankResult,
    TaskClass,
)
from debate_core.integrations.models import ModelRoute, RoutingPolicy
from debate_core.testing.contracts import (
    EmbeddingAnswer,
    ModelRouterContract,
    ModelRouterFactory,
    PlannedAnswer,
    RerankAnswer,
    RouteExpectation,
    StructuredAnswer,
)
from debate_core.testing.fakes.clock_and_ids import FAKE_EPOCH
from debate_core.testing.fakes.model_router import ScriptedModelResponse, ScriptedModelRouter


def _route(task_class: TaskClass) -> ModelRoute:
    model_id = f"stand-in-{task_class.value}"
    return ModelRoute(
        provider=ModelProvider.BEDROCK,
        model_id=model_id,
        inference_profile=f"geo.{model_id}" if task_class.is_generative else None,
        region="test-region-1",
        max_tokens=256 if task_class.is_generative else None,
        timeout_seconds=30,
    )


STAND_IN_POLICY = RoutingPolicy(routes={task_class: _route(task_class) for task_class in TaskClass})


class StandInModelRouter:
    """The least a router can do and pass the contract: resolve, look up the answer, validate it."""

    def __init__(self, policy: RoutingPolicy, answers: Sequence[PlannedAnswer]) -> None:
        self._policy = policy
        self._answers = list(answers)

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        request = ModelRequest.build(task_class, prompt, schema, params)
        route = self._policy.resolve(task_class, request.params)
        planned = next(
            (a for a in self._answers if isinstance(a, StructuredAnswer) and a.request == request), None
        )
        if planned is None:
            raise ProviderUnavailable("stand-in", f"no answer planned for {prompt.prompt_id}")
        try:
            output = schema.model_validate(dict(planned.answer))
        except ValidationError as error:
            raise InvalidModelOutput(
                prompt.prompt_id, prompt.prompt_version, str(error), model_id=route.model_id
            ) from error
        return ModelResponse[schema](
            output=output,
            route=route,
            usage=ModelUsage(
                input_tokens=len(json.dumps(prompt.variables)),
                output_tokens=len(json.dumps(dict(planned.answer))),
                latency_ms=0.0,
            ),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            invoked_at=FAKE_EPOCH,
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embed needs at least one text, and no text may be blank")
        planned = next(a for a in self._answers if isinstance(a, EmbeddingAnswer) and a.texts == tuple(texts))
        return EmbeddingResponse(
            vectors=planned.vectors,
            route=self._policy.resolve(TaskClass.EMBEDDINGS),
            usage=ModelUsage(input_tokens=sum(len(text) for text in texts), latency_ms=0.0),
            invoked_at=FAKE_EPOCH,
        )

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        if not query.strip() or not documents:
            raise ValueError("rerank needs a query and at least one document")
        planned = next(
            a
            for a in self._answers
            if isinstance(a, RerankAnswer) and (a.query, a.documents) == (query, tuple(documents))
        )
        ranked = sorted(enumerate(planned.scores), key=lambda pair: -pair[1])
        return RerankResponse(
            results=tuple(RerankResult(index=index, relevance_score=score) for index, score in ranked),
            route=self._policy.resolve(TaskClass.RERANK),
            usage=ModelUsage(latency_ms=0.0),
            invoked_at=FAKE_EPOCH,
        )


def test_the_stand_in_is_a_model_router_to_the_type_checker_too() -> None:
    router: ModelRouter = StandInModelRouter(STAND_IN_POLICY, [])
    assert isinstance(router, ModelRouter)


class TestStandInModelRouter(ModelRouterContract):
    """The contract against a router nothing else uses, with its routes checked field by field."""

    @pytest.fixture
    def make_router(self) -> ModelRouterFactory:
        return lambda answers: StandInModelRouter(STAND_IN_POLICY, answers)

    @pytest.fixture
    def expected_route(self) -> RouteExpectation:
        return STAND_IN_POLICY.resolve


def _script(answer: PlannedAnswer) -> ScriptedModelResponse:
    """A planned answer in the form the scripted fake takes."""
    match answer:
        case StructuredAnswer():
            return dict(answer.answer)
        case EmbeddingAnswer():
            return answer.vectors
        case RerankAnswer():
            return answer.scores


class TestScriptedModelRouter(ModelRouterContract):
    """The scripted fake every other package's tests wire in. Its routes report provider `fake`."""

    @pytest.fixture
    def make_router(self) -> ModelRouterFactory:
        return lambda answers: ScriptedModelRouter([_script(answer) for answer in answers])

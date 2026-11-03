"""A model router that returns scripted answers, for tests that need a model to say something.

It satisfies :class:`~debate_core.application.ports.model_router.ModelRouter` structurally, and
reads the time from a :class:`~debate_core.testing.fakes.clock_and_ids.FixedClock`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import BaseModel

from debate_core.application.errors import InvalidModelOutput, ProviderUnavailable
from debate_core.application.structured_output import validate_model_output
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
    ResolvedRoute,
    TaskClass,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock

__all__ = ["FAKE_MODEL_TIMEOUT_SECONDS", "ScriptedModelResponse", "ScriptedModelRouter"]


FAKE_MODEL_TIMEOUT_SECONDS = 60.0
"""The timeout a :class:`ScriptedModelRouter` route reports when a call does not override it."""

type ScriptedModelResponse = (
    BaseModel | Mapping[str, object] | Sequence[Sequence[float]] | Sequence[float] | Exception
)
"""One scripted answer: a structured output (an instance or a mapping), embedding vectors, rerank
scores in document order, or an exception to raise."""


class ScriptedModelRouter:
    """A model router that returns scripted answers and records every structured call.

    Enqueue one answer per call, in call order:

    * for `generate_structured`, a Pydantic instance or a mapping to validate against the requested
      schema, strictly, as every router does; an answer that does not fit surfaces as
      :class:`~debate_core.application.errors.InvalidModelOutput`, as it would from a model;
    * for `embed`, one vector per text;
    * for `rerank`, one relevance score per document, in document order (the fake sorts them);
    * for any call, an exception to raise, such as a model that cannot be reached.

    Responses report a route with provider `fake`, so nothing a fake answered can pass for a billed
    model's answer. This one is for unit tests that only need a model to say something specific.
    Answers kept as files, keyed by the call, are what `FakeModelRouter` and
    `RecordReplayModelRouter` in `debate_core.integrations.models` serve
    (v1-e05-t03-fake-replay-models). Until that task this class was itself named `FakeModelRouter`.
    """

    def __init__(
        self,
        responses: Sequence[ScriptedModelResponse] = (),
        *,
        model_id: str = "fake-model",
        clock: FixedClock | None = None,
        latency_ms: float = 1.0,
    ) -> None:
        self._responses: deque[ScriptedModelResponse] = deque(responses)
        self._model_id = model_id
        self._clock: FixedClock = clock if clock is not None else FixedClock()
        self._latency_ms = latency_ms
        self.calls: list[ModelRequest] = []
        """Every structured call, in order, for assertions about routing and prompt versions."""

    def enqueue(self, response: ScriptedModelResponse) -> None:
        """Add one more scripted response to the end of the queue."""
        self._responses.append(response)

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        request = ModelRequest.build(task_class, prompt, schema, params)
        self.calls.append(request)
        scripted = self._next(f"prompt {prompt.prompt_id}@{prompt.prompt_version}")
        if isinstance(scripted, BaseModel | Mapping):
            output = self._coerce(scripted, schema, prompt)
        else:
            raise TypeError(f"scripted {type(scripted).__name__} where a structured output was expected")
        return ModelResponse[schema](
            output=output,
            route=self._route(task_class, request.params),
            usage=ModelUsage(input_tokens=0, output_tokens=0, latency_ms=self._latency_ms),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            invoked_at=self._clock.now(),
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embed needs at least one text, and no text may be blank")
        scripted = self._next("embed")
        vectors = tuple(_floats(vector, "a vector") for vector in _items(scripted, "vectors"))
        if len(vectors) != len(texts):
            raise TypeError(f"scripted {len(vectors)} vectors for {len(texts)} texts")
        return EmbeddingResponse(
            vectors=vectors,
            route=self._route(TaskClass.EMBEDDINGS, ModelParams()),
            usage=ModelUsage(input_tokens=0, latency_ms=self._latency_ms),
            invoked_at=self._clock.now(),
        )

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        if not query.strip() or not documents:
            raise ValueError("rerank needs a query and at least one document")
        scripted = self._next("rerank")
        scores = _floats(scripted, "rerank scores")
        if len(scores) != len(documents):
            raise TypeError(f"scripted {len(scores)} scores for {len(documents)} documents")
        ranked = sorted(enumerate(scores), key=lambda pair: (-pair[1], pair[0]))
        return RerankResponse(
            results=tuple(RerankResult(index=index, relevance_score=score) for index, score in ranked),
            route=self._route(TaskClass.RERANK, ModelParams()),
            usage=ModelUsage(latency_ms=self._latency_ms),
            invoked_at=self._clock.now(),
        )

    def _next(self, what: str) -> ScriptedModelResponse:
        """The next scripted answer, raised when it is an exception."""
        if not self._responses:
            raise ProviderUnavailable("fake-model-router", f"no scripted response left for {what}")
        scripted = self._responses.popleft()
        if isinstance(scripted, Exception):
            raise scripted
        return scripted

    def _route(self, task_class: TaskClass, params: ModelParams) -> ResolvedRoute:
        return ResolvedRoute(
            task_class=task_class,
            provider=ModelProvider.FAKE,
            model_id=self._model_id,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            timeout_seconds=params.timeout_seconds or FAKE_MODEL_TIMEOUT_SECONDS,
        )

    def _coerce[OutputT: BaseModel](
        self,
        scripted: BaseModel | Mapping[str, object],
        schema: type[OutputT],
        prompt: ModelPrompt,
    ) -> OutputT:
        """Turn a scripted response into an instance of the requested schema, or fail like a model."""
        if isinstance(scripted, schema):
            return scripted
        if isinstance(scripted, BaseModel):
            raise InvalidModelOutput(
                prompt.prompt_id,
                prompt.prompt_version,
                f"scripted a {type(scripted).__name__} where {schema.__name__} was requested",
                model_id=self._model_id,
            )
        return validate_model_output(schema, dict(scripted), prompt=prompt, model_id=self._model_id)


def _items(scripted: object, what: str) -> Sequence[object]:
    """`scripted` as a sequence, or a `TypeError` naming what the call expected instead."""
    kind = type(scripted).__name__
    if isinstance(scripted, str | bytes | BaseModel | Mapping) or not isinstance(scripted, Sequence):
        raise TypeError(f"scripted {kind} where {what} were expected")
    return cast("Sequence[object]", scripted)


def _floats(scripted: object, what: str) -> tuple[float, ...]:
    """`scripted` as a tuple of floats, or a `TypeError` naming what the call expected instead."""
    values = _items(scripted, what)
    numbers = [value for value in values if isinstance(value, int | float) and not isinstance(value, bool)]
    if len(numbers) != len(values):
        raise TypeError(f"{what} must be numbers")
    return tuple(float(number) for number in numbers)

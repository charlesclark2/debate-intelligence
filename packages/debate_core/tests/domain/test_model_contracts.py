"""The values a model call is made of refuse the shapes no real call can have.

Each test here pins one invariant of `debate_core.domain.model_contracts` that a router
implementation (v1-e05-t02, v1-e05-t03) relies on rather than re-checks: a request is always for a
generative class, a temperature is always in Claude's range, a set of vectors is rectangular, a
reranking names each document once, best first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

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

WHEN = datetime(2026, 10, 16, tzinfo=UTC)
PROMPT = ModelPrompt(prompt_id="select-passage", prompt_version="1.0.0", variables={"tag": "t"})


class Choice(BaseModel):
    paragraph_id: int


def route(task_class: TaskClass = TaskClass.HIGH_VOLUME, **changes: Any) -> ResolvedRoute:
    fields: dict[str, Any] = {
        "task_class": task_class,
        "provider": ModelProvider.FAKE,
        "model_id": "m",
        "timeout_seconds": 1,
    }
    return ResolvedRoute.model_validate({**fields, **changes})


USAGE = ModelUsage(latency_ms=1)


def test_the_five_task_classes_are_the_spec_s_and_two_of_them_only_score() -> None:
    assert [member.value for member in TaskClass] == [
        "complex_reasoning",
        "high_volume",
        "deep_audit",
        "embeddings",
        "rerank",
    ]
    assert {member for member in TaskClass if not member.is_generative} == {
        TaskClass.EMBEDDINGS,
        TaskClass.RERANK,
    }


@pytest.mark.parametrize("scoring_class", [TaskClass.EMBEDDINGS, TaskClass.RERANK])
def test_a_request_for_a_scoring_class_is_refused(scoring_class: TaskClass) -> None:
    with pytest.raises(ValidationError, match="use embed or rerank"):
        ModelRequest.build(scoring_class, PROMPT, Choice)


def test_a_request_names_its_schema_by_dotted_path() -> None:
    request = ModelRequest.build(TaskClass.COMPLEX_REASONING, PROMPT, Choice)

    assert request.output_schema == f"{__name__}.Choice"
    assert request.params == ModelParams()


@pytest.mark.parametrize("temperature", [-0.1, 1.01, 2.0])
def test_an_override_temperature_outside_claude_s_range_is_refused(temperature: float) -> None:
    with pytest.raises(ValidationError, match="temperature"):
        ModelParams(temperature=temperature)


@pytest.mark.parametrize("field", ["max_tokens", "timeout_seconds"])
def test_a_zero_output_cap_or_timeout_is_refused(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        ModelParams.model_validate({field: 0})


def test_a_route_is_addressed_to_its_profile_when_it_has_one() -> None:
    assert route(model_id="m").invocation_target == "m"
    assert route(model_id="m", inference_profile="us.m").invocation_target == "us.m"


def test_a_resolved_route_refuses_an_out_of_range_temperature() -> None:
    with pytest.raises(ValidationError, match="temperature"):
        route(temperature=1.5)


def test_a_response_validates_its_output_as_the_schema_it_is_parametrized_with() -> None:
    fields: dict[str, Any] = {
        "route": route(),
        "usage": USAGE,
        "prompt_id": "p",
        "prompt_version": "1.0.0",
        "invoked_at": WHEN,
    }

    assert ModelResponse[Choice](output=Choice(paragraph_id=3), **fields).output.paragraph_id == 3
    with pytest.raises(ValidationError, match="paragraph_id"):
        ModelResponse[Choice].model_validate({"output": {"paragraph_id": "three"}, **fields})


def test_a_response_has_no_free_text_field() -> None:
    """The forbidden list: no free-form text return on the router API."""
    assert set(ModelResponse[Choice].model_fields) == {
        "output",
        "route",
        "usage",
        "prompt_id",
        "prompt_version",
        "provider_request_id",
        "invoked_at",
    }


def test_negative_usage_is_refused() -> None:
    with pytest.raises(ValidationError, match="input_tokens"):
        ModelUsage(input_tokens=-1, latency_ms=1)
    with pytest.raises(ValidationError, match="latency_ms"):
        ModelUsage(latency_ms=-1)


def embedding(vectors: Any) -> EmbeddingResponse:
    return EmbeddingResponse(vectors=vectors, route=route(TaskClass.EMBEDDINGS), usage=USAGE, invoked_at=WHEN)


def test_embeddings_are_one_rectangular_set_of_vectors() -> None:
    assert embedding(((1.0, 2.0), (3.0, 4.0))).dimensions == 2
    with pytest.raises(ValidationError, match="same length"):
        embedding(((1.0, 2.0), (3.0,)))
    with pytest.raises(ValidationError, match="cannot be empty"):
        embedding(((),))
    with pytest.raises(ValidationError, match="vectors"):
        embedding(())


def reranking(*pairs: tuple[int, float]) -> RerankResponse:
    return RerankResponse(
        results=tuple(RerankResult(index=index, relevance_score=score) for index, score in pairs),
        route=route(TaskClass.RERANK),
        usage=USAGE,
        invoked_at=WHEN,
    )


def test_a_reranking_names_each_document_once_best_first() -> None:
    assert [result.index for result in reranking((2, 0.9), (0, 0.5), (1, 0.5)).results] == [2, 0, 1]
    with pytest.raises(ValidationError, match="only once"):
        reranking((0, 0.9), (0, 0.5))
    with pytest.raises(ValidationError, match="highest first"):
        reranking((0, 0.1), (1, 0.9))
    with pytest.raises(ValidationError, match="index"):
        reranking((-1, 0.5))

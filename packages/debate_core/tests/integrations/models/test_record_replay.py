"""`RecordReplayModelRouter`: the contract in every mode (ac1), unrecorded calls (ac3), cassettes (ac4).

The real router it wraps is the Bedrock adapter, which v1-e05-t02 has not built, so the wrapped
router here is :class:`StandInRealRouter`: written in this file, held to the shared contract itself
(the PM's ruling of 2026-10-16), and reporting the kind of values a real one would, an application
inference profile's ARN with an account id in it among them. Every identifier, account and key is
invented; `111122223333` and `AKIAIOSFODNN7EXAMPLE` are the placeholders AWS's own documentation uses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Coroutine, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, JsonValue

from debate_core.application.budget import (
    BudgetExceededError,
    BudgetGuard,
    BudgetLimits,
    CalendarMonth,
    CallCeiling,
    Spend,
    UnpricedModelError,
)
from debate_core.application.errors import (
    InvalidModelOutput,
    ModelAccessDenied,
    ModelRequestRejected,
    ModelUnavailableError,
    OutputProblem,
    ProviderRateLimited,
    ProviderUnavailable,
)
from debate_core.application.model_errors import ValidationPolicy, describe_problems
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.settings import ConfigurationError, Settings, load_settings
from debate_core.application.structured_output import (
    StructuredOutputGuard,
    StructuredResult,
    missing_tool_call,
    validate_model_output,
)
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
from debate_core.integrations.models import ModelRoute, RoutingPolicy, build_model_router
from debate_core.integrations.models.errors import (
    FixtureFileError,
    MissingFixtureError,
    ModelModeError,
    PromptRenderError,
    RecordingRefusedError,
)
from debate_core.integrations.models.fixture_key import fixture_key
from debate_core.integrations.models.model_mode import (
    ModelMode,
    add_model_mode_option,
    resolve_model_mode,
    running_in_ci,
)
from debate_core.integrations.models.prompt_registry import PromptRegistry, load_prompt_file
from debate_core.integrations.models.received_answer import hand_over_answer
from debate_core.integrations.models.record_replay import CassetteDirectory, RecordReplayModelRouter
from debate_core.integrations.models.redaction import REDACTED, redact, redactions
from debate_core.integrations.models.usage import UsageLog
from debate_core.testing.contracts.model_router import (
    ContractPassage,
    EmbeddingAnswer,
    ModelRouterContract,
    ModelRouterFactory,
    PlannedAnswer,
    RerankAnswer,
    RouteExpectation,
    StructuredAnswer,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
COMMITTED_CASSETTES = REPOSITORY_ROOT / "tests" / "fixtures" / "model_cassettes"
COMMITTED_FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "model_outputs"

ACCOUNT_ID = "111122223333"
ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
SIGNATURE = "5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7"
SIGNED_HEADER = (
    f"AWS4-HMAC-SHA256 Credential={ACCESS_KEY_ID}/20261016/test-region-1/bedrock/aws4_request, "
    f"SignedHeaders=host;x-amz-date, Signature={SIGNATURE}"
)
RECORDED_AT = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)
NO_CI: Mapping[str, str] = {}


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


# ---------------------------------------------------------------------------------------------
# The stand-in for a real router
# ---------------------------------------------------------------------------------------------


def _route(task_class: TaskClass) -> ModelRoute:
    model_id = f"stand-in-{task_class.value}"
    profile = (
        f"arn:aws:bedrock:test-region-1:{ACCOUNT_ID}:application-inference-profile/stand-in"
        if task_class is TaskClass.COMPLEX_REASONING
        else f"geo.{model_id}"
        if task_class.is_generative
        else None
    )
    return ModelRoute(
        provider=ModelProvider.BEDROCK,
        model_id=model_id,
        inference_profile=profile,
        region="test-region-1",
        max_tokens=256 if task_class.is_generative else None,
        timeout_seconds=30,
    )


STAND_IN_POLICY = RoutingPolicy(routes={task_class: _route(task_class) for task_class in TaskClass})


class StandInRealRouter:
    """Answers planned in advance, resolved and validated the way a real adapter would.

    Counts its calls, so a test can show replay never reached it.
    """

    def __init__(self, answers: Sequence[PlannedAnswer] = ()) -> None:
        self._answers = list(answers)
        self.calls = 0

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        self.calls += 1
        request = ModelRequest.build(task_class, prompt, schema, params)
        route = STAND_IN_POLICY.resolve(task_class, request.params)
        planned = next(
            (a for a in self._answers if isinstance(a, StructuredAnswer) and a.request == request), None
        )
        if planned is None:
            raise ProviderUnavailable("stand-in", f"no answer planned for {prompt.prompt_id}")
        output = validate_model_output(schema, dict(planned.answer), prompt=prompt, model_id=route.model_id)
        return ModelResponse[schema](
            output=output,
            route=route,
            usage=ModelUsage(input_tokens=40, output_tokens=12, latency_ms=310.0),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            provider_request_id="stand-in-request-0001",
            invoked_at=RECORDED_AT,
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        self.calls += 1
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embed needs at least one text, and no text may be blank")
        planned = next(a for a in self._answers if isinstance(a, EmbeddingAnswer) and a.texts == tuple(texts))
        return EmbeddingResponse(
            vectors=planned.vectors,
            route=STAND_IN_POLICY.resolve(TaskClass.EMBEDDINGS),
            usage=ModelUsage(input_tokens=8, latency_ms=40.0),
            invoked_at=RECORDED_AT,
        )

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        self.calls += 1
        if not query.strip() or not documents:
            raise ValueError("rerank needs a query and at least one document")
        planned = next(
            a
            for a in self._answers
            if isinstance(a, RerankAnswer) and (a.query, a.documents) == (query, tuple(documents))
        )
        ranked = sorted(enumerate(planned.scores), key=lambda pair: (-pair[1], pair[0]))
        return RerankResponse(
            results=tuple(RerankResult(index=index, relevance_score=score) for index, score in ranked),
            route=STAND_IN_POLICY.resolve(TaskClass.RERANK),
            usage=ModelUsage(latency_ms=55.0),
            invoked_at=RECORDED_AT,
        )


# ---------------------------------------------------------------------------------------------
# The shared contract (ac1): the stand-in, and the wrapper in each mode
# ---------------------------------------------------------------------------------------------


class TestStandInRealRouter(ModelRouterContract):
    """The stand-in passes the contract, so wrapping it is a fair test of the wrapper."""

    @pytest.fixture
    def make_router(self) -> ModelRouterFactory:
        return StandInRealRouter

    @pytest.fixture
    def expected_route(self) -> RouteExpectation:
        return STAND_IN_POLICY.resolve


class TestRecordMode(ModelRouterContract):
    """Recording passes the real router's answers through unchanged, routes and all."""

    @pytest.fixture
    def make_router(self, tmp_path: Path) -> ModelRouterFactory:
        return lambda answers: RecordReplayModelRouter(
            StandInRealRouter(answers), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ=NO_CI
        )

    @pytest.fixture
    def expected_route(self) -> RouteExpectation:
        return STAND_IN_POLICY.resolve


class TestLiveMode(ModelRouterContract):
    @pytest.fixture
    def make_router(self, tmp_path: Path) -> ModelRouterFactory:
        return lambda answers: RecordReplayModelRouter(
            StandInRealRouter(answers), mode=ModelMode.LIVE, cassette_dir=tmp_path, environ=NO_CI
        )

    @pytest.fixture
    def expected_route(self) -> RouteExpectation:
        return STAND_IN_POLICY.resolve


def cassettes_for(root: Path, answers: Sequence[PlannedAnswer]) -> CassetteDirectory:
    """Cassettes holding the planned answers as the stand-in would have answered them.

    Written directly rather than recorded, because the contract plans answers that do not fit
    their schema, and a real router refuses those before anything could be recorded.
    """
    cassettes = CassetteDirectory(root)
    invoked_at = RECORDED_AT.isoformat()
    for answer in answers:
        match answer:
            case StructuredAnswer(request=request):
                route = STAND_IN_POLICY.resolve(request.task_class, request.params)
                cassettes.write_structured(
                    request,
                    {
                        "output": dict(answer.answer),
                        "route": route.model_dump(mode="json"),
                        "usage": {"input_tokens": 40, "output_tokens": 12, "latency_ms": 310.0},
                        "prompt_id": request.prompt.prompt_id,
                        "prompt_version": request.prompt.prompt_version,
                        "provider_request_id": None,
                        "invoked_at": invoked_at,
                    },
                )
            case EmbeddingAnswer():
                cassettes.write_embedding(
                    answer.texts,
                    {
                        "vectors": [list(vector) for vector in answer.vectors],
                        "route": STAND_IN_POLICY.resolve(TaskClass.EMBEDDINGS).model_dump(mode="json"),
                        "usage": {"input_tokens": 8, "output_tokens": None, "latency_ms": 40.0},
                        "provider_request_id": None,
                        "invoked_at": invoked_at,
                    },
                )
            case RerankAnswer():
                ranked = sorted(enumerate(answer.scores), key=lambda pair: (-pair[1], pair[0]))
                cassettes.write_rerank(
                    answer.query,
                    answer.documents,
                    {
                        "results": [{"index": index, "relevance_score": score} for index, score in ranked],
                        "route": STAND_IN_POLICY.resolve(TaskClass.RERANK).model_dump(mode="json"),
                        "usage": {"input_tokens": None, "output_tokens": None, "latency_ms": 55.0},
                        "provider_request_id": None,
                        "invoked_at": invoked_at,
                    },
                )
    return cassettes


class TestReplayMode(ModelRouterContract):
    """Replay holds no real router at all: every answer comes from a cassette."""

    @pytest.fixture
    def make_router(self, tmp_path: Path) -> ModelRouterFactory:
        def build(answers: Sequence[PlannedAnswer]) -> ModelRouter:
            cassettes_for(tmp_path, answers)
            return RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)

        return build


# ---------------------------------------------------------------------------------------------
# Record, then replay
# ---------------------------------------------------------------------------------------------


class Explanation(BaseModel):
    """A schema with free text in it, which is where a secret could ride into a cassette."""

    note: str


PROMPT = ModelPrompt(prompt_id="example.explain", prompt_version="1.0.0", variables={"tag": "Warming kills"})
PASSAGE = {"paragraph_id": 3, "start_offset": 0, "end_offset": 42}


def planned(
    task_class: TaskClass, answer: Mapping[str, JsonValue], schema: type[BaseModel]
) -> StructuredAnswer:
    return StructuredAnswer(request=ModelRequest.build(task_class, PROMPT, schema), answer=answer)


def recorder(root: Path, *answers: PlannedAnswer) -> RecordReplayModelRouter:
    return RecordReplayModelRouter(
        StandInRealRouter(answers), mode=ModelMode.RECORD, cassette_dir=root, environ=NO_CI
    )


def replayer(root: Path, delegate: ModelRouter | None = None) -> RecordReplayModelRouter:
    return RecordReplayModelRouter(delegate, mode=ModelMode.REPLAY, cassette_dir=root)


def test_record_writes_one_pretty_printed_cassette_per_call(tmp_path: Path) -> None:
    router = recorder(tmp_path, planned(TaskClass.HIGH_VOLUME, PASSAGE, ContractPassage))

    run(router.generate_structured(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))
    run(router.generate_structured(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))

    request = ModelRequest.build(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage)
    written = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    assert written == [tmp_path / "example.explain" / f"{fixture_key(request)}.json"]
    text = written[0].read_text(encoding="utf-8")
    assert text.startswith('{\n  "call": "generate_structured",\n  "cassette_format": 1,\n')
    assert text.endswith("}\n")


def test_a_recorded_call_replays_without_the_real_router(tmp_path: Path) -> None:
    recorded = run(
        recorder(tmp_path, planned(TaskClass.HIGH_VOLUME, PASSAGE, ContractPassage)).generate_structured(
            TaskClass.HIGH_VOLUME, PROMPT, ContractPassage
        )
    )

    replayed = run(replayer(tmp_path).generate_structured(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))

    assert replayed.output == recorded.output == ContractPassage.model_validate(PASSAGE)
    assert (replayed.usage, replayed.invoked_at) == (recorded.usage, recorded.invoked_at)
    assert replayed.provider_request_id == "stand-in-request-0001"
    assert replayed.route.provider is ModelProvider.FAKE
    assert (replayed.route.region, replayed.route.inference_profile) == (None, None)
    assert replayed.route.model_id == recorded.route.model_id == "stand-in-high_volume"


def test_embed_and_rerank_replay_what_was_recorded(tmp_path: Path) -> None:
    texts = ("Warming causes extinction.", "Tariffs hurt trade.")
    documents = ("about tariffs", "about extinction")
    router = recorder(
        tmp_path,
        EmbeddingAnswer(texts=texts, vectors=((0.6, 0.8), (1.0, 0.0))),
        RerankAnswer(query="extinction", documents=documents, scores=(0.1, 0.7)),
    )
    run(router.embed(texts))
    run(router.rerank("extinction", documents))

    vectors = run(replayer(tmp_path).embed(texts))
    ranking = run(replayer(tmp_path).rerank("extinction", documents))

    assert vectors.vectors == ((0.6, 0.8), (1.0, 0.0))
    assert [(result.index, result.relevance_score) for result in ranking.results] == [(1, 0.7), (0, 0.1)]
    assert {vectors.route.provider, ranking.route.provider} == {ModelProvider.FAKE}
    assert sorted(path.parent.name for path in tmp_path.rglob("*.json")) == ["_embed", "_rerank"]


def test_live_mode_records_nothing(tmp_path: Path) -> None:
    router = RecordReplayModelRouter(
        StandInRealRouter([planned(TaskClass.HIGH_VOLUME, PASSAGE, ContractPassage)]),
        mode=ModelMode.LIVE,
        cassette_dir=tmp_path,
        environ=NO_CI,
    )

    run(router.generate_structured(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))

    assert not any(tmp_path.iterdir())


def test_a_failed_real_call_records_nothing(tmp_path: Path) -> None:
    router = recorder(tmp_path)

    with pytest.raises(ProviderUnavailable):
        run(router.generate_structured(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))

    assert not any(tmp_path.iterdir())


def test_the_committed_example_cassette_replays() -> None:
    prompt = ModelPrompt(
        prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Warming kills"}
    )

    response = run(
        replayer(COMMITTED_CASSETTES).generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage)
    )

    assert response.output == ContractPassage(paragraph_id=2, start_offset=12, end_offset=57)
    assert response.route.model_id == "example-recorded-model"
    assert response.usage == ModelUsage(input_tokens=120, output_tokens=18, latency_ms=850.0)
    assert response.invoked_at == datetime(2026, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------------------------
# Record mode keeps an invalid answer, so a repaired call replays both halves (v1-e05-t10)
# ---------------------------------------------------------------------------------------------

EXAMPLE_PROMPT = ModelPrompt(
    prompt_id="example.select-passage",
    prompt_version="1.0.0",
    variables={"tag": "A tag invented for recording a repaired call"},
)
"""The worked example prompt, registered as `high_volume` with `ContractPassage` as its schema."""

INVALID_PASSAGE: Mapping[str, JsonValue] = {"paragraph_id": "the third", "start_offset": 0, "end_offset": 42}

NO_TOOL_CALL = missing_tool_call("the model did not call the ContractPassage tool (stopReason 'end_turn')")
"""The Bedrock adapter's wording, which is not `validate_model_output`'s, so replay must keep it."""

CUT_OFF = OutputProblem(
    loc=(),
    type="unfinished_answer",
    msg="the model stopped with 'max_tokens', which is not a finished answer",
)

FAIL_CLOSED = ValidationPolicy(fail_closed=True)


@dataclass(frozen=True)
class CutOff:
    """An answer the router refuses before validating it, as Bedrock refuses a turn cut off at max_tokens."""

    answer: Mapping[str, JsonValue]


@dataclass(frozen=True)
class NotHandedOver:
    """An invalid answer that the router refuses without handing it to record mode."""

    answer: Mapping[str, JsonValue]


@dataclass(frozen=True)
class FailsAfterAnswering:
    """A provider error raised after the router had handed an answer over."""

    error: Exception


type LiveStep = Mapping[str, JsonValue] | None | CutOff | NotHandedOver | FailsAfterAnswering | Exception
"""What one structured call to :class:`StandInLiveRouter` does: answer with a tool input, answer
without calling the tool (`None`), be refused for how the turn ended, or fail."""


class StandInLiveRouter:
    """The real router record mode wraps: each structured call takes the next planned step.

    Like the Bedrock adapter, it hands record mode the answer it received before validating it,
    and refuses an invalid one with the call's usage on the error. Call N reports 100 * N input
    tokens, so each half of a repaired call has usage of its own.
    """

    def __init__(self, steps: Sequence[LiveStep], *, policy: RoutingPolicy = STAND_IN_POLICY) -> None:
        self._steps = list(steps)
        self._policy = policy
        self.requests: list[ModelRequest] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        request = ModelRequest.build(task_class, prompt, schema, params)
        self.requests.append(request)
        step = self._steps.pop(0)
        await asyncio.sleep(0)  # here, and after an answer is handed over, another call may run
        if isinstance(step, Exception):
            raise step
        route = self._policy.resolve(task_class, request.params)
        usage = ModelUsage(input_tokens=100 * len(self.requests), output_tokens=12, latency_ms=310.0)

        def refuse(problem: OutputProblem) -> InvalidModelOutput:
            return InvalidModelOutput(
                prompt.prompt_id,
                prompt.prompt_version,
                describe_problems((problem,)),
                model_id=route.model_id,
                problems=(problem,),
                usage=usage,
            )

        match step:
            case FailsAfterAnswering(error=error):
                hand_over_answer(dict(PASSAGE))
                raise error
            case NotHandedOver(answer=answer):
                answered: JsonValue | None = dict(answer)
            case CutOff(answer=answer):
                hand_over_answer(dict(answer))
                raise refuse(CUT_OFF)
            case None:
                hand_over_answer(None)
                await asyncio.sleep(0)
                raise refuse(NO_TOOL_CALL)
            case _:
                answered = dict(step)
                hand_over_answer(answered)
                await asyncio.sleep(0)
        output = validate_model_output(schema, answered, prompt=prompt, model_id=route.model_id, usage=usage)
        return ModelResponse[schema](
            output=output,
            route=route,
            usage=usage,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            provider_request_id=f"stand-in-request-{len(self.requests):04d}",
            invoked_at=RECORDED_AT,
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        raise AssertionError("these tests make structured calls only")

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        raise AssertionError("these tests make structured calls only")


type Outcome = tuple[object, ...]
"""What one structured call came back with, in the terms a live run and its replay can be compared in."""


def refusal(error: InvalidModelOutput) -> Outcome:
    return (
        "refused",
        str(error),
        error.prompt_id,
        error.prompt_version,
        error.model_id,
        error.problems,
        error.usage,
    )


class ObservingRouter:
    """Passes each call on, keeping each structured request and what came back: an answer or a refusal."""

    def __init__(self, router: ModelRouter) -> None:
        self._router = router
        self.requests: list[ModelRequest] = []
        self.outcomes: list[Outcome] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        self.requests.append(ModelRequest.build(task_class, prompt, schema, params))
        try:
            response = await self._router.generate_structured(task_class, prompt, schema, params)
        except InvalidModelOutput as error:
            self.outcomes.append(refusal(error))
            raise
        self.outcomes.append(("answered", response.output, response.usage, response.route.model_id))
        return response

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        return await self._router.embed(texts)

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        return await self._router.rerank(query, documents)


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    """The committed prompts, `model.repair` among them, plus the worked example."""
    committed = PromptRegistry.load(REPOSITORY_ROOT / "prompts")
    example = load_prompt_file(
        REPOSITORY_ROOT / "tests" / "fixtures" / "prompts" / "example" / "select-passage.md"
    )
    return PromptRegistry([*committed.prompts, example])


def guarded_call(router: ModelRouter, registry: PromptRegistry) -> StructuredResult[ContractPassage]:
    guard = StructuredOutputGuard(router, registry)
    return run(guard.generate(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage, policy=FAIL_CLOSED))


def recording(root: Path, live: ModelRouter) -> RecordReplayModelRouter:
    return RecordReplayModelRouter(live, mode=ModelMode.RECORD, cassette_dir=root, environ=NO_CI)


def written(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


def cassette_response(root: Path, request: ModelRequest) -> dict[str, Any]:
    path = CassetteDirectory(root).structured_path(request)
    return json.loads(path.read_text(encoding="utf-8"))["response"]


@dataclass(frozen=True)
class RepairedCall:
    """A call whose first answer is refused and whose repair answers PASSAGE, and what must be recorded."""

    first_answer: LiveStep
    recorded_output: JsonValue
    """The cassette's `output` for the first answer, written by hand."""
    recorded_problems: list[JsonValue]
    """The cassette's problems, written by hand."""
    problems: tuple[OutputProblem, ...]
    """The same problems, as the refusal carries them."""
    described: str
    """How the refusal's message describes them."""


REPAIRED_CALLS = {
    "an answer that does not fit the schema": RepairedCall(
        first_answer={"paragraph_id": "the third", "start_offset": 0},
        recorded_output={"paragraph_id": "the third", "start_offset": 0},
        recorded_problems=[
            {"loc": ["paragraph_id"], "msg": "Input should be a valid integer", "type": "int_type"},
            {"loc": ["end_offset"], "msg": "Field required", "type": "missing"},
        ],
        problems=(
            OutputProblem(loc=("paragraph_id",), type="int_type", msg="Input should be a valid integer"),
            OutputProblem(loc=("end_offset",), type="missing", msg="Field required"),
        ),
        described="2 problems: paragraph_id: Input should be a valid integer [int_type]; "
        "end_offset: Field required [missing]",
    ),
    "an answer that never called the tool": RepairedCall(
        first_answer=None,
        recorded_output=None,
        recorded_problems=[
            {
                "loc": [],
                "msg": "the model did not call the ContractPassage tool (stopReason 'end_turn')",
                "type": "missing_tool_call",
            }
        ],
        problems=(NO_TOOL_CALL,),
        described="1 problem: (answer): the model did not call the ContractPassage tool "
        "(stopReason 'end_turn') [missing_tool_call]",
    ),
    "a fitting answer refused for a cut-off turn": RepairedCall(
        first_answer=CutOff(PASSAGE),
        recorded_output={"paragraph_id": 3, "start_offset": 0, "end_offset": 42},
        recorded_problems=[
            {
                "loc": [],
                "msg": "the model stopped with 'max_tokens', which is not a finished answer",
                "type": "unfinished_answer",
            }
        ],
        problems=(CUT_OFF,),
        described="1 problem: (answer): the model stopped with 'max_tokens', which is not a finished "
        "answer [unfinished_answer]",
    ),
}


@pytest.mark.parametrize("case", list(REPAIRED_CALLS.values()), ids=list(REPAIRED_CALLS))
def test_record_a_repaired_call_writes_both_halves_and_replay_gives_the_same_error_repair_and_result(
    tmp_path: Path, registry: PromptRegistry, case: RepairedCall
) -> None:
    """ac1. The expected cassette and error are written by hand from the stand-in's plan."""
    live = StandInLiveRouter([case.first_answer, PASSAGE])
    recorder_seen = ObservingRouter(recording(tmp_path, live))
    recorded = guarded_call(recorder_seen, registry)

    first, repair = live.requests
    assert repair.prompt.prompt_id == "model.repair"
    assert written(tmp_path) == sorted(
        [
            Path("example.select-passage") / f"{fixture_key(first)}.json",
            Path("model.repair") / f"{fixture_key(repair)}.json",
        ]
    )
    response = cassette_response(tmp_path, first)
    assert response == {
        "model_id": "stand-in-high_volume",
        "output": case.recorded_output,
        "problems": case.recorded_problems,
        "prompt_id": "example.select-passage",
        "prompt_version": "1.0.0",
        "usage": {"input_tokens": 100, "latency_ms": 310.0, "output_tokens": 12},
    }

    replay_seen = ObservingRouter(replayer(tmp_path))
    replayed = guarded_call(replay_seen, registry)

    assert replay_seen.requests == recorder_seen.requests == [first, repair]
    assert replay_seen.outcomes == recorder_seen.outcomes
    assert replay_seen.outcomes[0] == (
        "refused",
        f"invalid output from stand-in-high_volume for prompt example.select-passage@1.0.0: {case.described}",
        "example.select-passage",
        "1.0.0",
        "stand-in-high_volume",
        case.problems,
        ModelUsage(input_tokens=100, output_tokens=12, latency_ms=310.0),
    )
    assert (
        replayed.output == recorded.output == ContractPassage(paragraph_id=3, start_offset=0, end_offset=42)
    )
    assert replayed.attempts == recorded.attempts
    assert len(replayed.attempts) == 2


def test_record_an_answer_that_never_called_the_tool_as_output_null(tmp_path: Path) -> None:
    router = recording(tmp_path, StandInLiveRouter([None]))

    with pytest.raises(InvalidModelOutput):
        run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    response = cassette_response(
        tmp_path, ModelRequest.build(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage)
    )
    assert "output" in response
    assert response["output"] is None


def test_replay_of_a_recorded_invalid_answer_raises_it_without_the_guard(tmp_path: Path) -> None:
    with pytest.raises(InvalidModelOutput) as live:
        run(
            recording(tmp_path, StandInLiveRouter([INVALID_PASSAGE])).generate_structured(
                TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage
            )
        )

    with pytest.raises(InvalidModelOutput) as replayed:
        run(replayer(tmp_path).generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert type(replayed.value) is InvalidModelOutput
    assert refusal(replayed.value) == refusal(live.value)
    assert replayed.value.__cause__ is None
    assert replayed.value.__context__ is None


def test_record_calls_made_together_each_keep_their_own_answer(tmp_path: Path) -> None:
    """Each call waits before and after handing its answer over, so the two hand-overs interleave."""
    router = recording(tmp_path, StandInLiveRouter([INVALID_PASSAGE, None]))
    other_prompt = EXAMPLE_PROMPT.model_copy(update={"variables": {"tag": "Another invented tag"}})

    async def both() -> Sequence[BaseException | ModelResponse[ContractPassage]]:
        return await asyncio.gather(
            router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage),
            router.generate_structured(TaskClass.HIGH_VOLUME, other_prompt, ContractPassage),
            return_exceptions=True,
        )

    outcomes = run(both())

    assert [type(outcome) for outcome in outcomes] == [InvalidModelOutput, InvalidModelOutput]
    first = ModelRequest.build(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage)
    second = ModelRequest.build(TaskClass.HIGH_VOLUME, other_prompt, ContractPassage)
    assert cassette_response(tmp_path, first)["output"] == {
        "paragraph_id": "the third",
        "start_offset": 0,
        "end_offset": 42,
    }
    assert cassette_response(tmp_path, second)["output"] is None


PROVIDER_ERRORS = {
    "access denied": ModelAccessDenied("bedrock", "stand-in-high_volume", "not authorized"),
    "throttled": ProviderRateLimited("bedrock"),
    "unavailable": ModelUnavailableError("bedrock", "stand-in-high_volume"),
    "request rejected": ModelRequestRejected(
        "bedrock", "stand-in-high_volume", "ValidationException", "temperature is not supported"
    ),
}


@pytest.mark.parametrize("error", list(PROVIDER_ERRORS.values()), ids=list(PROVIDER_ERRORS))
@pytest.mark.parametrize("answered_first", [False, True], ids=["no-answer", "after-an-answer"])
def test_record_a_provider_error_records_nothing(
    tmp_path: Path, error: Exception, answered_first: bool
) -> None:
    step = FailsAfterAnswering(error) if answered_first else error
    router = recording(tmp_path, StandInLiveRouter([step]))

    with pytest.raises(type(error)) as raised:
        run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert raised.value is error
    assert written(tmp_path) == []


class FixedCeiling:
    """Prices every call at `usd`; `None` is a call it cannot price."""

    def __init__(self, usd: float | None) -> None:
        self._ceiling = CallCeiling(
            model_id="stand-in-high_volume", usd=usd, unpriced_reason=None if usd is not None else "no price"
        )

    def structured_ceiling(
        self, task_class: TaskClass, prompt: ModelPrompt, params: ModelParams | None
    ) -> CallCeiling:
        return self._ceiling

    def embedding_ceiling(self, texts: Sequence[str]) -> CallCeiling:
        return self._ceiling

    def rerank_ceiling(self, query: str, documents: Sequence[str]) -> CallCeiling:
        return self._ceiling


class NothingSpent:
    def spent(self, run_id: str, day: date, month: CalendarMonth) -> Spend:
        return Spend(run_usd=0.0, day_usd=0.0, month_usd=0.0)


@pytest.mark.parametrize(
    ("ceiling_usd", "refusal_type"),
    [(1.0, BudgetExceededError), (None, UnpricedModelError)],
    ids=["over-the-limit", "unpriced"],
)
def test_record_a_budget_refusal_records_nothing_and_reaches_no_model(
    tmp_path: Path, ceiling_usd: float | None, refusal_type: type[Exception]
) -> None:
    live = StandInLiveRouter([INVALID_PASSAGE])
    budgeted = BudgetGuard(
        live,
        limits=BudgetLimits(per_run_usd=0.01),
        pricer=FixedCeiling(ceiling_usd),
        ledger=NothingSpent(),
        run_id="a-budgeted-run",
        clock=FixedClock(RECORDED_AT),
    )

    with pytest.raises(refusal_type):
        run(
            recording(tmp_path, budgeted).generate_structured(
                TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage
            )
        )

    assert live.requests == []
    assert written(tmp_path) == []


def test_record_a_call_that_never_reached_the_provider_records_nothing(tmp_path: Path) -> None:
    unrenderable = PromptRenderError(
        "example.select-passage", "1.0.0", "it uses `tag`, which the call did not give"
    )
    router = recording(tmp_path, StandInLiveRouter([unrenderable]))

    with pytest.raises(PromptRenderError):
        run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))
    with pytest.raises(ValueError, match="rerank"):
        run(router.generate_structured(TaskClass.RERANK, EXAMPLE_PROMPT, ContractPassage))

    assert written(tmp_path) == []


def test_record_never_writes_an_invalid_answer_it_was_not_handed(tmp_path: Path) -> None:
    """A router that refuses an answer without handing it over leaves record mode nothing true to write."""
    router = recording(tmp_path, StandInLiveRouter([NotHandedOver(INVALID_PASSAGE)]))

    with pytest.raises(InvalidModelOutput):
        run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert written(tmp_path) == []


def test_live_mode_keeps_no_invalid_answer(tmp_path: Path) -> None:
    router = RecordReplayModelRouter(
        StandInLiveRouter([INVALID_PASSAGE, None]), mode=ModelMode.LIVE, cassette_dir=tmp_path, environ=NO_CI
    )

    for _ in range(2):
        with pytest.raises(InvalidModelOutput):
            run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert written(tmp_path) == []


def test_a_recorded_invalid_answer_is_scrubbed_like_any_cassette(tmp_path: Path) -> None:
    leaky: Mapping[str, JsonValue] = {
        "paragraph_id": f"Authorization: {SIGNED_HEADER}",
        "start_offset": 0,
        "end_offset": f"arn:aws:iam::{ACCOUNT_ID}:role/x",
    }
    router = recording(tmp_path, StandInLiveRouter([leaky]))

    with pytest.raises(InvalidModelOutput):
        run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    (cassette,) = tmp_path.rglob("*.json")
    text = cassette.read_text(encoding="utf-8")
    for secret in (ACCOUNT_ID, ACCESS_KEY_ID, SIGNATURE, "AWS4-HMAC-SHA256"):
        assert secret not in text
    assert redactions(json.loads(text)) == []
    assert json.loads(text)["response"]["output"]["end_offset"] == f"arn:aws:iam::{REDACTED}:role/x"


UNREADABLE_REFUSALS: list[tuple[str, JsonValue, str]] = [
    ("problems", [{"loc": [], "type": "missing_tool_call"}], "recorded problems are not valid"),
    ("problems", "the model did not call the tool", "recorded problems are not valid"),
    ("usage", {"input_tokens": -1, "latency_ms": 1.0}, "ModelUsage"),
    ("model_id", 7, "recorded model id"),
]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    UNREADABLE_REFUSALS,
    ids=["a-problem-without-its-message", "problems-not-a-list", "negative-tokens", "model-id-not-text"],
)
def test_a_recorded_invalid_answer_that_cannot_be_read_is_refused(
    tmp_path: Path, field: str, value: JsonValue, reason: str
) -> None:
    with pytest.raises(InvalidModelOutput):
        run(
            recording(tmp_path, StandInLiveRouter([None])).generate_structured(
                TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage
            )
        )
    request = ModelRequest.build(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage)
    path = CassetteDirectory(tmp_path).structured_path(request)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["response"][field] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(FixtureFileError, match=reason):
        run(replayer(tmp_path).generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))


@pytest.fixture
def no_inherited_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


def bedrock_settings(tmp_path: Path) -> Settings:
    """The test profile on the bedrock provider, the example routing file, and no budget."""
    return load_settings(
        environment="test",
        overrides={
            "models": {
                "provider": "bedrock",
                "routing_file": str(REPOSITORY_ROOT / "config" / "model_routing.example.yaml"),
                "budget_usd_daily": None,
            },
            "storage": {"data_dir": str(tmp_path / "data")},
        },
        env_file=tmp_path / "no.env",
    )


def usage_lines(usage_dir: Path) -> list[tuple[object, ...]]:
    return [
        (line["prompt_id"], line["attempt"], line["input_tokens"], line["output_tokens"])
        for path in sorted(usage_dir.iterdir())
        for line in map(json.loads, path.read_text(encoding="utf-8").splitlines())
    ]


@pytest.mark.usefixtures("no_inherited_settings")
def test_record_through_the_built_router_logs_both_halves_once_and_replay_logs_nothing(
    tmp_path: Path, registry: PromptRegistry
) -> None:
    """RecordReplay(BudgetGuard(UsageRecordingRouter(real))): the usage recorder sits inside replay."""
    settings = bedrock_settings(tmp_path)
    live = StandInLiveRouter([INVALID_PASSAGE, PASSAGE], policy=RoutingPolicy.from_settings(settings))

    def real_router(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
        return live

    cassettes = tmp_path / "cassettes"
    recorder_seen = ObservingRouter(
        build_model_router(
            settings,
            mode="record",
            environ=NO_CI,
            real_router=real_router,
            cassette_dir=cassettes,
            clock=FixedClock(RECORDED_AT),
            run_id="a-recording-run",
            usage_log=UsageLog.for_data_dir(settings.storage.data_dir),
        )
    )
    guarded_call(recorder_seen, registry)
    usage_dir = tmp_path / "data" / "usage"
    logged = [("example.select-passage", 1, 100, 12), ("model.repair", 2, 200, 12)]
    assert usage_lines(usage_dir) == logged
    log_files = written(usage_dir)

    replay_seen = ObservingRouter(
        build_model_router(settings, mode="replay", environ=NO_CI, cassette_dir=cassettes)
    )
    guarded_call(replay_seen, registry)

    assert replay_seen.outcomes == recorder_seen.outcomes
    assert replay_seen.outcomes[0][-1] == ModelUsage(input_tokens=100, output_tokens=12, latency_ms=310.0)
    assert usage_lines(usage_dir) == logged
    assert written(usage_dir) == log_files


# ---------------------------------------------------------------------------------------------
# Replay errors on any unrecorded call (ac3)
# ---------------------------------------------------------------------------------------------


def test_an_unrecorded_call_names_the_prompt_and_key_and_never_reaches_the_real_router(
    tmp_path: Path,
) -> None:
    real = StandInRealRouter([planned(TaskClass.HIGH_VOLUME, PASSAGE, ContractPassage)])
    router = replayer(tmp_path, delegate=real)

    with pytest.raises(MissingFixtureError) as raised:
        run(router.generate_structured(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))

    key = fixture_key(ModelRequest.build(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))
    assert (raised.value.prompt_id, raised.value.key) == ("example.explain", key)
    assert "example.explain@1.0.0" in str(raised.value)
    assert key in str(raised.value)
    assert real.calls == 0


@pytest.mark.parametrize("call", ["embed", "rerank"])
def test_an_unrecorded_embed_or_rerank_is_named_by_its_call(tmp_path: Path, call: str) -> None:
    router = replayer(tmp_path)

    with pytest.raises(MissingFixtureError, match=f"{call} call") as raised:
        if call == "embed":
            run(router.embed(["a text"]))
        else:
            run(router.rerank("a query", ["a document"]))

    assert raised.value.call == call
    assert raised.value.prompt_id is None


@pytest.mark.parametrize(
    ("task_class", "params"),
    [
        (TaskClass.COMPLEX_REASONING, None),
        (TaskClass.HIGH_VOLUME, ModelParams(max_tokens=64)),
    ],
    ids=["another-task-class", "other-parameters"],
)
def test_a_call_that_differs_from_its_cassette_only_outside_the_key_is_unrecorded(
    tmp_path: Path, task_class: TaskClass, params: ModelParams | None
) -> None:
    run(
        recorder(tmp_path, planned(TaskClass.HIGH_VOLUME, PASSAGE, ContractPassage)).generate_structured(
            TaskClass.HIGH_VOLUME, PROMPT, ContractPassage
        )
    )

    with pytest.raises(MissingFixtureError, match="the cassette at this key recorded"):
        run(replayer(tmp_path).generate_structured(task_class, PROMPT, ContractPassage, params))


def test_a_cassette_filed_under_another_key_is_refused(tmp_path: Path) -> None:
    cassettes = cassettes_for(tmp_path, [planned(TaskClass.HIGH_VOLUME, PASSAGE, ContractPassage)])
    request = ModelRequest.build(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage)
    other = PROMPT.model_copy(update={"variables": {"tag": "Something else"}})
    cassettes.structured_path(request).rename(
        cassettes.structured_path(ModelRequest.build(TaskClass.HIGH_VOLUME, other, ContractPassage))
    )

    with pytest.raises(FixtureFileError, match="filed under this key"):
        run(replayer(tmp_path).generate_structured(TaskClass.HIGH_VOLUME, other, ContractPassage))


def test_a_cassette_with_a_broken_route_is_refused(tmp_path: Path) -> None:
    cassettes = cassettes_for(tmp_path, [planned(TaskClass.HIGH_VOLUME, PASSAGE, ContractPassage)])
    path = cassettes.structured_path(ModelRequest.build(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["response"]["route"]["model_id"]
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(FixtureFileError, match="ResolvedRoute"):
        run(replayer(tmp_path).generate_structured(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage))


# ---------------------------------------------------------------------------------------------
# Redaction (ac4)
# ---------------------------------------------------------------------------------------------


def test_a_recorded_cassette_carries_no_account_id_key_or_signature(tmp_path: Path) -> None:
    answer = {"note": f"Authorization: {SIGNED_HEADER}"}
    router = recorder(tmp_path, planned(TaskClass.COMPLEX_REASONING, answer, Explanation))

    response = run(router.generate_structured(TaskClass.COMPLEX_REASONING, PROMPT, Explanation))

    (cassette,) = tmp_path.rglob("*.json")
    text = cassette.read_text(encoding="utf-8")
    for secret in (ACCOUNT_ID, ACCESS_KEY_ID, SIGNATURE, "AWS4-HMAC-SHA256"):
        assert secret not in text
    route = json.loads(text)["response"]["route"]
    assert route["inference_profile"] == (
        f"arn:aws:bedrock:test-region-1:{REDACTED}:application-inference-profile/stand-in"
    )
    assert response.output.note == f"Authorization: {SIGNED_HEADER}", "the caller gets the real answer"
    assert ACCOUNT_ID in str(response.route.inference_profile)


def test_authorization_headers_are_redacted_wherever_a_cassette_holds_them(tmp_path: Path) -> None:
    request = ModelRequest.build(TaskClass.HIGH_VOLUME, PROMPT, ContractPassage)
    headers: dict[str, JsonValue] = {
        "Authorization": SIGNED_HEADER,
        "X-Amz-Security-Token": "FwoGZXIvYXdzEXAMPLETOKEN",
        "x-amz-date": "20261016T093000Z",
        "Content-Type": "application/json",
    }

    path = CassetteDirectory(tmp_path).write_structured(request, {"transport": {"headers": headers}})

    written = json.loads(path.read_text(encoding="utf-8"))["response"]["transport"]["headers"]
    assert written == {
        "Authorization": REDACTED,
        "X-Amz-Security-Token": REDACTED,
        "x-amz-date": "20261016T093000Z",
        "Content-Type": "application/json",
    }


@pytest.mark.parametrize(
    ("text", "scrubbed"),
    [
        (SIGNED_HEADER, REDACTED),
        (f"Bearer {ACCESS_KEY_ID}abc", f"Bearer {REDACTED}"),
        (f"key {ACCESS_KEY_ID} leaked", f"key {REDACTED} leaked"),
        (
            f"https://bucket.example/o?X-Amz-Credential=abc%2F20261016&X-Amz-Signature={SIGNATURE}",
            f"https://bucket.example/o?X-Amz-Credential={REDACTED}&X-Amz-Signature={REDACTED}",
        ),
        (f"arn:aws:iam::{ACCOUNT_ID}:role/x", f"arn:aws:iam::{REDACTED}:role/x"),
        (f"https://{ACCOUNT_ID}.signin.example/", f"https://{REDACTED}.signin.example/"),
    ],
)
def test_secrets_are_scrubbed_from_text(text: str, scrubbed: str) -> None:
    assert redact(text) == scrubbed


@pytest.mark.parametrize(
    "text",
    [
        "paragraph 3, offsets 0 to 42",
        "a1234567890123b0" * 4,
        "1234567890123",
        "2026-10-16T09:30:00Z",
        "Warming kills",
    ],
    ids=["prose", "digits-inside-a-hex-digest", "thirteen-digits", "timestamp", "tag"],
)
def test_ordinary_text_is_left_alone(text: str) -> None:
    assert redact(text) == text


def test_numbers_are_redacted_only_under_an_account_key() -> None:
    document: JsonValue = {"input_tokens": 111122223333, "account_id": 111122223333, "aws": {"Account": "x"}}

    assert redact(document) == {
        "input_tokens": 111122223333,
        "account_id": REDACTED,
        "aws": {"Account": REDACTED},
    }


def test_redaction_is_idempotent_and_leaves_nothing_to_find() -> None:
    document: JsonValue = {
        "Authorization": SIGNED_HEADER,
        "note": SIGNED_HEADER,
        "list": [f"arn:aws:s3::{ACCOUNT_ID}:x"],
    }

    once = redact(document)

    assert redact(once) == once
    assert redactions(once) == []
    assert redactions(document) == ["Authorization", "note", "list[0]"]


def test_no_committed_cassette_or_fixture_holds_anything_redaction_would_remove() -> None:
    """The check CI runs on every file a pull request commits under the two fixture directories."""
    files = sorted([*COMMITTED_CASSETTES.rglob("*.json"), *COMMITTED_FIXTURES.rglob("*.json")])

    assert files, "the example cassette and fixture are committed"
    findings = {
        str(path.relative_to(REPOSITORY_ROOT)): found
        for path in files
        if (found := redactions(json.loads(path.read_text(encoding="utf-8"))))
    }
    assert findings == {}


# ---------------------------------------------------------------------------------------------
# CI never records (ac4)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
def test_record_mode_is_refused_when_ci_is_true(tmp_path: Path, value: str) -> None:
    with pytest.raises(RecordingRefusedError, match="CI=true") as raised:
        RecordReplayModelRouter(
            StandInRealRouter(), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={"CI": value}
        )

    assert raised.value.source == "env:CI"
    assert not any(tmp_path.iterdir())


def test_record_mode_reads_ci_from_the_process_environment_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")

    with pytest.raises(RecordingRefusedError):
        RecordReplayModelRouter(StandInRealRouter(), mode=ModelMode.RECORD, cassette_dir=tmp_path)


@pytest.mark.parametrize("environ", [{}, {"CI": "false"}, {"CI": ""}])
def test_record_mode_runs_off_ci(tmp_path: Path, environ: Mapping[str, str]) -> None:
    assert not running_in_ci(environ)
    RecordReplayModelRouter(
        StandInRealRouter(), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ=environ
    )


@pytest.mark.parametrize("mode", [ModelMode.REPLAY, ModelMode.LIVE])
def test_replay_and_live_run_in_ci(tmp_path: Path, mode: ModelMode) -> None:
    RecordReplayModelRouter(StandInRealRouter(), mode=mode, cassette_dir=tmp_path, environ={"CI": "true"})


@pytest.mark.parametrize("mode", [ModelMode.RECORD, ModelMode.LIVE])
def test_record_and_live_need_a_real_router(tmp_path: Path, mode: ModelMode) -> None:
    with pytest.raises(ConfigurationError, match="none was given"):
        RecordReplayModelRouter(None, mode=mode, cassette_dir=tmp_path, environ=NO_CI)


# ---------------------------------------------------------------------------------------------
# The one control: --model-mode, then DEBATE_MODEL_MODE, then replay
# ---------------------------------------------------------------------------------------------


def test_the_mode_defaults_to_replay() -> None:
    assert resolve_model_mode(environ={}) is ModelMode.REPLAY


def test_the_variable_chooses_the_mode() -> None:
    assert resolve_model_mode(environ={"DEBATE_MODEL_MODE": "Live"}) is ModelMode.LIVE


def test_the_option_wins_over_the_variable() -> None:
    assert resolve_model_mode("record", environ={"DEBATE_MODEL_MODE": "live"}) is ModelMode.RECORD


def test_the_process_environment_is_read_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_MODEL_MODE", "live")

    assert resolve_model_mode() is ModelMode.LIVE


@pytest.mark.parametrize(
    ("option", "environ", "source"),
    [
        ("recrod", {}, "--model-mode"),
        (None, {"DEBATE_MODEL_MODE": "fake"}, "env:DEBATE_MODEL_MODE"),
        (None, {"DEBATE_MODEL_MODE": ""}, "env:DEBATE_MODEL_MODE"),
    ],
)
def test_an_unknown_mode_is_refused_naming_where_it_came_from(
    option: str | None, environ: Mapping[str, str], source: str
) -> None:
    with pytest.raises(ModelModeError, match="expected one of record, replay, live") as raised:
        resolve_model_mode(option, environ=environ)

    assert raised.value.source == source


def test_an_argparse_program_gets_the_option() -> None:
    parser = argparse.ArgumentParser()
    add_model_mode_option(parser)

    assert parser.parse_args(["--model-mode", "live"]).model_mode == "live"
    unset = parser.parse_args([]).model_mode
    assert unset is None
    assert resolve_model_mode(unset, environ={"DEBATE_MODEL_MODE": "record"}) is ModelMode.RECORD


def test_an_argparse_program_refuses_an_unknown_mode(capsys: pytest.CaptureFixture[str]) -> None:
    parser = argparse.ArgumentParser()
    add_model_mode_option(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["--model-mode", "fake"])

    assert "invalid choice: 'fake'" in capsys.readouterr().err

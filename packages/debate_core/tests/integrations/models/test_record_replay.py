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
from collections.abc import Coroutine, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from debate_core.application.errors import InvalidModelOutput, ProviderUnavailable
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.settings import ConfigurationError
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
from debate_core.integrations.models.errors import (
    FixtureFileError,
    MissingFixtureError,
    ModelModeError,
    RecordingRefusedError,
)
from debate_core.integrations.models.fixture_key import fixture_key
from debate_core.integrations.models.model_mode import (
    ModelMode,
    add_model_mode_option,
    resolve_model_mode,
    running_in_ci,
)
from debate_core.integrations.models.record_replay import CassetteDirectory, RecordReplayModelRouter
from debate_core.integrations.models.redaction import REDACTED, redact, redactions
from debate_core.testing.contracts import (
    EmbeddingAnswer,
    ModelRouterContract,
    ModelRouterFactory,
    PlannedAnswer,
    RerankAnswer,
    RouteExpectation,
    StructuredAnswer,
)
from debate_core.testing.contracts.model_router import ContractPassage

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
        try:
            output = schema.model_validate(dict(planned.answer))
        except ValidationError as error:
            raise InvalidModelOutput(
                prompt.prompt_id, prompt.prompt_version, str(error), model_id=route.model_id
            ) from error
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

"""The fixture-keyed `FakeModelRouter`: the shared contract (ac1), and a missing fixture fails loudly (ac3).

Expected keys and vectors here were derived by hand, from `shasum -a 256` of a hand-written
canonical text or word, never by running the router (working agreement 6).
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
from collections.abc import Coroutine, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.errors import InvalidModelOutput
from debate_core.application.ports.model_router import ModelRouter
from debate_core.domain.model_contracts import ModelPrompt, ModelProvider, ModelRequest, TaskClass
from debate_core.integrations.models.errors import FixtureFileError, MissingFixtureError
from debate_core.integrations.models.fake_router import (
    EMBEDDING_DIMENSIONS,
    FIXTURE_EPOCH,
    FakeModelRouter,
    FixtureDirectory,
    hashed_embedding,
    lexical_overlap_scores,
)
from debate_core.integrations.models.fixture_key import fixture_key
from debate_core.testing.contracts.model_router import (
    ContractPassage,
    EmbeddingAnswer,
    ModelRouterContract,
    ModelRouterFactory,
    PlannedAnswer,
    RerankAnswer,
    StructuredAnswer,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
COMMITTED_FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "model_outputs"

EXAMPLE_PROMPT = ModelPrompt(
    prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Warming kills"}
)
EXAMPLE_KEY = "e218aaf1f972b6dd32f494c9d6b6676974e48fef6346f284dc7b66a6fd50c66e"
"""sha256 of {"inputs":{"tag":"Warming kills"},"prompt_id":"example.select-passage",
"prompt_version":"1.0.0","schema":"debate_core.testing.contracts.model_router.ContractPassage"}."""


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


VALID_OUTPUT = {"paragraph_id": 3, "start_offset": 0, "end_offset": 1}


def example_request(prompt: ModelPrompt = EXAMPLE_PROMPT) -> ModelRequest:
    return ModelRequest.build(TaskClass.HIGH_VOLUME, prompt, ContractPassage)


def ask(router: FakeModelRouter, prompt: ModelPrompt = EXAMPLE_PROMPT) -> ContractPassage:
    """Run the example call on `router` and return its output."""
    return run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage)).output


# ---------------------------------------------------------------------------------------------
# The shared contract (ac1)
# ---------------------------------------------------------------------------------------------


def planned_router(root: Path, answers: Sequence[PlannedAnswer]) -> FakeModelRouter:
    """A fake whose fixture files hold the planned structured answers.

    The fake computes its own vectors and scores, which cannot equal arbitrary planned ones, so the
    planned embeddings and scores are handed in through the `embedder` and `reranker` arguments.
    Everything else the contract checks (validation, routes, usage, ordering, refusals) is the
    fake's own code.
    """
    fixtures = FixtureDirectory(root)
    vectors: dict[tuple[str, ...], tuple[tuple[float, ...], ...]] = {}
    scores: dict[tuple[str, tuple[str, ...]], tuple[float, ...]] = {}
    for answer in answers:
        match answer:
            case StructuredAnswer():
                fixtures.write(answer.request, answer.answer)
            case EmbeddingAnswer():
                vectors[answer.texts] = answer.vectors
            case RerankAnswer():
                scores[(answer.query, answer.documents)] = answer.scores
    return FakeModelRouter(
        root,
        embedder=lambda texts: vectors[tuple(texts)],
        reranker=lambda query, documents: scores[(query, tuple(documents))],
    )


class TestFakeModelRouter(ModelRouterContract):
    """Structured answers are read from fixture files written into a fresh directory per test."""

    @pytest.fixture
    def make_router(self, tmp_path: Path) -> ModelRouterFactory:
        return lambda answers: planned_router(tmp_path / "model_outputs", answers)


def test_the_fake_is_a_model_router_to_the_type_checker_too(tmp_path: Path) -> None:
    router: ModelRouter = FakeModelRouter(tmp_path)
    assert isinstance(router, ModelRouter)


# ---------------------------------------------------------------------------------------------
# Answers from files
# ---------------------------------------------------------------------------------------------


def test_the_committed_example_fixture_is_served() -> None:
    router = FakeModelRouter(COMMITTED_FIXTURES)

    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert response.output == ContractPassage(paragraph_id=3, start_offset=0, end_offset=42)
    assert response.route.provider is ModelProvider.FAKE
    assert response.invoked_at == FIXTURE_EPOCH


def test_an_answer_is_filed_under_its_prompt_id_and_key(tmp_path: Path) -> None:
    path = FixtureDirectory(tmp_path).path_for(example_request())

    assert path == tmp_path / "example.select-passage" / f"{EXAMPLE_KEY}.json"


def test_a_written_fixture_is_pretty_printed_and_names_its_request(tmp_path: Path) -> None:
    path = FixtureDirectory(tmp_path).write(example_request(), {"paragraph_id": 3})

    text = path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert '\n  "prompt_id": "example.select-passage",\n' in text
    assert json.loads(text)["output_schema"] == "debate_core.testing.contracts.model_router.ContractPassage"


def test_a_missing_fixture_names_the_prompt_and_the_key(tmp_path: Path) -> None:
    router = FakeModelRouter(tmp_path)

    with pytest.raises(MissingFixtureError) as raised:
        run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    error = raised.value
    assert (error.prompt_id, error.prompt_version) == ("example.select-passage", "1.0.0")
    assert error.key == EXAMPLE_KEY
    assert "example.select-passage@1.0.0" in str(error)
    assert EXAMPLE_KEY in str(error)
    assert error.location == tmp_path / "example.select-passage" / f"{EXAMPLE_KEY}.json"
    assert not any(tmp_path.iterdir()), "looking for a fixture must not create anything"


def test_a_fixture_for_another_prompt_version_does_not_answer(tmp_path: Path) -> None:
    FixtureDirectory(tmp_path).write(example_request(), VALID_OUTPUT)
    bumped = EXAMPLE_PROMPT.model_copy(update={"prompt_version": "1.0.1"})

    with pytest.raises(MissingFixtureError, match="example.select-passage@1.0.1"):
        ask(FakeModelRouter(tmp_path), bumped)


def test_a_fixture_filed_under_the_wrong_name_is_refused(tmp_path: Path) -> None:
    fixtures = FixtureDirectory(tmp_path)
    other = EXAMPLE_PROMPT.model_copy(update={"variables": {"tag": "Something else"}})
    written = fixtures.write(example_request(other), VALID_OUTPUT)
    shutil.move(written, fixtures.path_for(example_request()))

    with pytest.raises(FixtureFileError, match="answers some other request"):
        ask(FakeModelRouter(tmp_path))


@pytest.mark.parametrize(
    ("content", "reason"),
    [("{not json", "not valid JSON"), ("[1, 2]", "not an object"), ('{"prompt_id": "x"}', "no `output`")],
)
def test_an_unusable_fixture_file_is_refused(tmp_path: Path, content: str, reason: str) -> None:
    path = FixtureDirectory(tmp_path).path_for(example_request())
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")

    with pytest.raises(FixtureFileError, match=reason):
        ask(FakeModelRouter(tmp_path))


def test_a_fixture_answer_that_no_longer_fits_its_schema_is_invalid_output(tmp_path: Path) -> None:
    FixtureDirectory(tmp_path).write(example_request(), {"paragraph": 3})

    with pytest.raises(InvalidModelOutput, match="example.select-passage@1.0.0"):
        ask(FakeModelRouter(tmp_path))


@pytest.mark.parametrize("prompt_id", ["../escape", "a/b", ".hidden", "with space"])
def test_a_prompt_id_that_cannot_name_a_directory_is_refused(tmp_path: Path, prompt_id: str) -> None:
    prompt = EXAMPLE_PROMPT.model_copy(update={"prompt_id": prompt_id})

    with pytest.raises(ValueError, match="cannot name a fixture directory"):
        FixtureDirectory(tmp_path).path_for(example_request(prompt))


def test_a_given_clock_dates_the_response(tmp_path: Path) -> None:
    FixtureDirectory(tmp_path).write(example_request(), VALID_OUTPUT)
    moment = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)

    response = run(
        FakeModelRouter(tmp_path, clock=FixedClock(moment)).generate_structured(
            TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage
        )
    )

    assert response.invoked_at == moment
    assert fixture_key(example_request()) == EXAMPLE_KEY


# ---------------------------------------------------------------------------------------------
# Computed embeddings
# ---------------------------------------------------------------------------------------------


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_a_one_word_text_is_one_signed_dimension() -> None:
    """sha256("warming") = da065c50 e0…: 0xda065c50 mod 64 = 16, and 0xe0 is even, so -1 at 16."""
    vector = hashed_embedding("warming")

    assert vector == tuple(-1.0 if index == 16 else 0.0 for index in range(EMBEDDING_DIMENSIONS))


def test_an_embedding_depends_only_on_the_words() -> None:
    assert hashed_embedding("Warming causes EXTINCTION!") == hashed_embedding("extinction, causes warming")


def test_every_embedding_is_a_unit_vector_of_the_stated_length() -> None:
    for text in ("warming", "Warming causes extinction", "!!!", "a a a b"):
        vector = hashed_embedding(text)
        assert len(vector) == EMBEDDING_DIMENSIONS
        assert math.isclose(math.sqrt(cosine(vector, vector)), 1.0)


def test_texts_that_share_words_are_closer_than_texts_that_do_not() -> None:
    query = hashed_embedding("warming causes extinction")

    shared = cosine(query, hashed_embedding("warming causes mass extinction events"))
    disjoint = cosine(query, hashed_embedding("tariffs hurt manufacturing jobs"))

    assert shared > disjoint


def test_embed_is_the_same_on_every_router_and_call(tmp_path: Path) -> None:
    texts = ["Warming causes extinction", "Tariffs hurt trade"]

    first = run(FakeModelRouter(tmp_path).embed(texts))
    second = run(FakeModelRouter(tmp_path / "elsewhere").embed(texts))

    assert first.vectors == second.vectors == tuple(hashed_embedding(text) for text in texts)
    assert first.route.provider is ModelProvider.FAKE


def test_an_embedder_that_miscounts_is_refused(tmp_path: Path) -> None:
    router = FakeModelRouter(tmp_path, embedder=lambda texts: [(1.0,)])

    with pytest.raises(ValueError, match="1 vectors for 2 texts"):
        run(router.embed(["one", "two"]))


# ---------------------------------------------------------------------------------------------
# Computed rerank
# ---------------------------------------------------------------------------------------------


def test_rerank_scores_the_share_of_query_words_each_document_holds() -> None:
    documents = ["Tariffs hurt trade", "Warming causes extinction.", "Extinction risk"]

    assert lexical_overlap_scores("warming causes extinction", documents) == [0.0, 1.0, 1 / 3]


def test_rerank_puts_the_most_overlapping_document_first_and_keeps_ties_in_order(tmp_path: Path) -> None:
    documents = ["tariffs", "extinction risk", "warming causes extinction", "extinction again"]

    response = run(FakeModelRouter(tmp_path).rerank("warming causes extinction", documents))

    assert [result.index for result in response.results] == [2, 1, 3, 0]
    assert response.route.task_class is TaskClass.RERANK

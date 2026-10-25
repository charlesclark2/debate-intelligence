"""The fixture-keyed fake model router: answers from files, computed vectors and scores, no model.

`models.provider = "fake"` selects it (:mod:`debate_core.integrations.models.factory`), and the
shared `model_router` pytest fixture builds it, so a test, a golden run or an offline eval gets the
same answer to the same question every time without credentials or a network.

## Structured output: one file per answer

A `generate_structured` call is answered from `<fixture_dir>/<prompt_id>/<key>.json`, where the key
is :func:`~debate_core.integrations.models.fixture_key.fixture_key` of the call. The default
directory is `tests/fixtures/model_outputs/`. A file holds the four things the key is computed over
and the answer, so a reviewer can see what question it answers::

    {
      "output": {"end_offset": 42, "paragraph_id": 3, "start_offset": 0},
      "output_schema": "debate_core.application.cards.CardSelection",
      "prompt_id": "card.select-passage",
      "prompt_version": "1.0.0",
      "variables": {"need": "Warming causes extinction"}
    }

The fake recomputes the key from the file's own fields and refuses a file whose name does not match
it, so a fixture copied to the wrong name, or left behind by a prompt version bump, is reported
rather than served. :meth:`FixtureDirectory.write` writes a file correctly.

The answer is validated against the schema the call asked for, strictly, by the same
:func:`~debate_core.application.structured_output.validate_model_output` every router uses, and one
that does not fit is an :class:`~debate_core.application.errors.InvalidModelOutput`, exactly as from a
model. `"output": null` stands for a model that answered without calling the schema's tool, which
`toolChoice` `auto` allows (v1-e05-t05, ac5), and is refused the same way. **A missing
file is a** :class:`~debate_core.integrations.models.errors.MissingFixtureError` **naming the prompt
and the key, never a default answer and never a call to a real model.**

Fixtures are invented (v1-e05-t03 forbids credentials, request signatures, student names and real
card text in any of them); `tests/fixtures/model_cassettes/README.md` says how to write one.

## Embeddings and rerank: computed, not stored

`embed` returns :func:`hashed_embedding` vectors: each lower-cased word is hashed to one of
:data:`EMBEDDING_DIMENSIONS` signed dimensions and the sum is scaled to unit length. Texts that share
words point in similar directions, so an offline search test can tell a relevant passage from an
irrelevant one, and the same text always gets the same vector. `rerank` scores each document by
:func:`lexical_overlap_scores`, the share of the query's distinct words it contains. Both can be
replaced with the `embedder` and `reranker` arguments.

Every response reports provider `fake`, so nothing it answered passes for a billed model's answer.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from pydantic import BaseModel, JsonValue, ValidationError

from debate_core.application.ports.providers import Clock
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
from debate_core.integrations.models._recorded_files import (
    read_json_object,
    safe_directory_name,
    write_pretty_json,
)
from debate_core.integrations.models.errors import FixtureFileError, MissingFixtureError
from debate_core.integrations.models.fixture_key import fixture_key

__all__ = [
    "DEFAULT_FIXTURE_DIRECTORY",
    "EMBEDDING_DIMENSIONS",
    "FAKE_MODEL_ID",
    "FIXTURE_EPOCH",
    "Embedder",
    "FakeModelRouter",
    "FixtureDirectory",
    "Reranker",
    "hashed_embedding",
    "lexical_overlap_scores",
    "words",
]

DEFAULT_FIXTURE_DIRECTORY: Final = Path("tests/fixtures/model_outputs")
"""Where the fake's answers are committed, relative to the repository root."""

FAKE_MODEL_ID: Final = "fake-fixture-model"
"""The model id on every route the fake reports."""

FAKE_TIMEOUT_SECONDS: Final = 60.0
"""The timeout a route reports when a call does not override it."""

FIXTURE_EPOCH: Final = datetime(2026, 1, 1, tzinfo=UTC)
"""`invoked_at` on every response when no clock is given, so output is byte-identical across runs."""

EMBEDDING_DIMENSIONS: Final = 64
"""Length of every vector :func:`hashed_embedding` returns."""

type Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]
"""One vector per text, in order."""

type Reranker = Callable[[str, Sequence[str]], Sequence[float]]
"""One relevance score per document, in document order."""

_WORD: Final = re.compile(r"\w+")
_HINT: Final = (
    "Write the answer with FixtureDirectory.write (tests/fixtures/model_cassettes/README.md); "
    "the fake router never asks a real model."
)


class FixtureDirectory:
    """The fake's answers on disk: one JSON file per prompt, version, variables and schema."""

    def __init__(self, root: Path) -> None:
        self.root = root
        """The directory holding one subdirectory per prompt id."""

    def path_for(self, request: ModelRequest) -> Path:
        """Where the answer to `request` is filed."""
        return self.root / safe_directory_name(request.prompt.prompt_id) / f"{fixture_key(request)}.json"

    def write(self, request: ModelRequest, output: Mapping[str, JsonValue] | None) -> Path:
        """File `output` as the answer to `request`, and return where it went.

        `None` files an answer that never called the schema's tool.
        """
        path = self.path_for(request)
        write_pretty_json(
            path,
            {
                "output": dict(output) if output is not None else None,
                "output_schema": request.output_schema,
                "prompt_id": request.prompt.prompt_id,
                "prompt_version": request.prompt.prompt_version,
                "variables": request.prompt.variables,
            },
        )
        return path

    def read(self, request: ModelRequest) -> dict[str, Any] | None:
        """The recorded answer to `request`, not yet validated against its schema; `None` for no tool call.

        Raises :class:`MissingFixtureError` when there is none, and :class:`FixtureFileError` when
        the file is unusable or answers some other request.
        """
        path = self.path_for(request)
        document = read_json_object(path)
        if document is None:
            raise MissingFixtureError(
                call="generate_structured",
                key=fixture_key(request),
                location=path,
                prompt_id=request.prompt.prompt_id,
                prompt_version=request.prompt.prompt_version,
                hint=_HINT,
            )
        output = document.get("output")
        if "output" not in document or not (output is None or isinstance(output, dict)):
            raise FixtureFileError(path, "it has no `output` object, and no `null` for an answer without one")
        try:
            filed_for = ModelRequest.model_validate(
                {
                    "task_class": request.task_class,
                    "prompt": {
                        "prompt_id": document.get("prompt_id"),
                        "prompt_version": document.get("prompt_version"),
                        "variables": document.get("variables", {}),
                    },
                    "output_schema": document.get("output_schema"),
                }
            )
        except ValidationError as error:
            raise FixtureFileError(path, f"its request fields are not valid: {error}") from error
        if fixture_key(filed_for) != path.stem:
            raise FixtureFileError(
                path,
                "its prompt, version, variables or schema do not hash to its file name, so it answers "
                "some other request; rewrite it with FixtureDirectory.write",
            )
        return cast(dict[str, Any] | None, output)


class FakeModelRouter:
    """A `ModelRouter` that answers from fixture files and computes embeddings and rerank scores."""

    def __init__(
        self,
        fixture_dir: Path,
        *,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        clock: Clock | None = None,
        model_id: str = FAKE_MODEL_ID,
    ) -> None:
        self.fixtures = FixtureDirectory(fixture_dir)
        """Where structured answers are read from."""
        self._embed: Embedder = embedder if embedder is not None else _hashed_embeddings
        self._rerank: Reranker = reranker if reranker is not None else lexical_overlap_scores
        self._clock = clock
        self._model_id = model_id

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        request = ModelRequest.build(task_class, prompt, schema, params)
        output = validate_model_output(
            schema, self.fixtures.read(request), prompt=prompt, model_id=self._model_id
        )
        return ModelResponse[schema](
            output=output,
            route=self._route(task_class, request.params),
            usage=ModelUsage(input_tokens=0, output_tokens=0, latency_ms=0.0),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            invoked_at=self._now(),
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embed needs at least one text, and no text may be blank")
        vectors = tuple(tuple(float(value) for value in vector) for vector in self._embed(texts))
        if len(vectors) != len(texts):
            raise ValueError(f"the embedder returned {len(vectors)} vectors for {len(texts)} texts")
        return EmbeddingResponse(
            vectors=vectors,
            route=self._route(TaskClass.EMBEDDINGS, ModelParams()),
            usage=ModelUsage(input_tokens=0, latency_ms=0.0),
            invoked_at=self._now(),
        )

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        if not query.strip() or not documents:
            raise ValueError("rerank needs a query and at least one document")
        scores = [float(score) for score in self._rerank(query, documents)]
        if len(scores) != len(documents):
            raise ValueError(f"the reranker returned {len(scores)} scores for {len(documents)} documents")
        ranked = sorted(enumerate(scores), key=lambda pair: (-pair[1], pair[0]))
        return RerankResponse(
            results=tuple(RerankResult(index=index, relevance_score=score) for index, score in ranked),
            route=self._route(TaskClass.RERANK, ModelParams()),
            usage=ModelUsage(latency_ms=0.0),
            invoked_at=self._now(),
        )

    def _route(self, task_class: TaskClass, params: ModelParams) -> ResolvedRoute:
        return ResolvedRoute(
            task_class=task_class,
            provider=ModelProvider.FAKE,
            model_id=self._model_id,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            timeout_seconds=params.timeout_seconds or FAKE_TIMEOUT_SECONDS,
        )

    def _now(self) -> datetime:
        return self._clock.now() if self._clock is not None else FIXTURE_EPOCH


def words(text: str) -> list[str]:
    """`text`'s words, case-folded, in order: what the fake's embeddings and rerank compare."""
    return _WORD.findall(text.casefold())


def hashed_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> tuple[float, ...]:
    """A unit vector for `text` that depends only on which words it holds and how often.

    Each word adds ±1 to the dimension its SHA-256 picks (the first four bytes choose the dimension,
    the fifth byte's lowest bit the sign). A text with no words is hashed whole, as one word, and so
    is a text whose words happen to cancel out, so no vector is ever zero.
    """
    vector = _signed_counts(words(text) or [text], dimensions)
    if not any(vector):
        vector = _signed_counts([text], dimensions)
    norm = math.sqrt(sum(value * value for value in vector))
    return tuple(value / norm for value in vector)


def lexical_overlap_scores(query: str, documents: Sequence[str]) -> list[float]:
    """For each document, the share of the query's distinct words it contains, from 0.0 to 1.0."""
    wanted = set(words(query)) or {query.casefold()}
    return [len(wanted & set(words(document))) / len(wanted) for document in documents]


def _hashed_embeddings(texts: Sequence[str]) -> list[tuple[float, ...]]:
    return [hashed_embedding(text) for text in texts]


def _signed_counts(tokens: Sequence[str], dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    return vector

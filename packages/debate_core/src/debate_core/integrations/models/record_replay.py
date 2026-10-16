"""Record a real router's answers once, then replay them for every test and eval after.

:class:`RecordReplayModelRouter` wraps a real `ModelRouter` (the Bedrock adapter of
v1-e05-t02-bedrock-adapter) and does one of three things, chosen by the run's
:class:`~debate_core.integrations.models.model_mode.ModelMode` and nothing else:

* **replay** (the default): serve each call from its cassette. A call with no cassette is a
  :class:`~debate_core.integrations.models.errors.MissingFixtureError` naming the prompt and the key.
  The real router is not even held in this mode, so nothing can fall back to it.
* **record**: make the real call, then write the request and the response to a cassette, scrubbed
  by :func:`~debate_core.integrations.models.redaction.redact`. A developer opts in with
  `DEBATE_MODEL_MODE=record` or `--model-mode record`, with credentials; it is refused when
  `CI=true`, so CI never records.
* **live**: make the real call and write nothing.

## Cassettes

One pretty-printed JSON file per call, committed under `tests/fixtures/model_cassettes/` and read in
review like any other diff (`tests/fixtures/model_cassettes/README.md`):

| Call | File | Key (`debate_core.integrations.models.fixture_key`) |
|---|---|---|
| `generate_structured` | `<prompt_id>/<key>.json` | `fixture_key(request)` |
| `embed` | `_embed/<key>.json` | `embedding_key(texts)` |
| `rerank` | `_rerank/<key>.json` | `rerank_key(query, documents)` |

A cassette holds the call, its key, the whole request and the whole response. The key does not
cover a structured call's task class or parameters, so replay compares the recorded request with
the call's in full, and a call that differs in either is an unrecorded call, not a near miss.

A replayed response is the recorded one with its route marked as provider `fake` and no region or
inference profile, because no model was reached. The recorded model id is kept: it says which
model's answer is being replayed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, JsonValue, ValidationError

from debate_core.application.errors import InvalidModelOutput
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
    ResolvedRoute,
    TaskClass,
)
from debate_core.integrations.models._recorded_files import (
    read_json_object,
    safe_directory_name,
    write_pretty_json,
)
from debate_core.integrations.models.errors import (
    FixtureFileError,
    MissingFixtureError,
    RecordingRefusedError,
)
from debate_core.integrations.models.fixture_key import embedding_key, fixture_key, rerank_key
from debate_core.integrations.models.model_mode import (
    CI_VARIABLE,
    MODEL_MODE_VARIABLE,
    ModelMode,
    running_in_ci,
)
from debate_core.integrations.models.redaction import redact

__all__ = [
    "CASSETTE_FORMAT",
    "DEFAULT_CASSETTE_DIRECTORY",
    "CassetteDirectory",
    "RecordReplayModelRouter",
    "RecordedCall",
    "refuse_recording_in_ci",
]

DEFAULT_CASSETTE_DIRECTORY: Final = Path("tests/fixtures/model_cassettes")
"""Where cassettes are committed, relative to the repository root."""

CASSETTE_FORMAT: Final = 1
"""Version of a cassette's own shape. Bumped only by a change that breaks existing cassettes."""

_EMBED_DIRECTORY: Final = "_embed"
_RERANK_DIRECTORY: Final = "_rerank"
_HINT: Final = (
    f"Record it with {MODEL_MODE_VARIABLE}=record and credentials, outside CI "
    "(tests/fixtures/model_cassettes/README.md); replay never calls a real model."
)


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """A cassette that matched a call: where it is, and the response it recorded, unvalidated."""

    path: Path
    response: dict[str, Any]


class CassetteDirectory:
    """Cassettes on disk: written scrubbed, read back only for the exact request they recorded."""

    def __init__(self, root: Path) -> None:
        self.root = root
        """The directory holding one subdirectory per prompt id, plus `_embed` and `_rerank`."""

    # Paths ------------------------------------------------------------------------------------

    def structured_path(self, request: ModelRequest) -> Path:
        """Where the cassette of a `generate_structured` call is filed."""
        return self.root / safe_directory_name(request.prompt.prompt_id) / f"{fixture_key(request)}.json"

    def embedding_path(self, texts: Sequence[str]) -> Path:
        """Where the cassette of an `embed` call is filed."""
        return self.root / _EMBED_DIRECTORY / f"{embedding_key(texts)}.json"

    def rerank_path(self, query: str, documents: Sequence[str]) -> Path:
        """Where the cassette of a `rerank` call is filed."""
        return self.root / _RERANK_DIRECTORY / f"{rerank_key(query, documents)}.json"

    # Writing ----------------------------------------------------------------------------------

    def write_structured(self, request: ModelRequest, response: Mapping[str, JsonValue]) -> Path:
        """Write the cassette of a `generate_structured` call; `response` is its JSON form."""
        return self._write(
            "generate_structured", self.structured_path(request), request.model_dump(mode="json"), response
        )

    def write_embedding(self, texts: Sequence[str], response: Mapping[str, JsonValue]) -> Path:
        """Write the cassette of an `embed` call; `response` is its JSON form."""
        return self._write("embed", self.embedding_path(texts), {"texts": list(texts)}, response)

    def write_rerank(self, query: str, documents: Sequence[str], response: Mapping[str, JsonValue]) -> Path:
        """Write the cassette of a `rerank` call; `response` is its JSON form."""
        request: dict[str, JsonValue] = {"documents": list(documents), "query": query}
        return self._write("rerank", self.rerank_path(query, documents), request, response)

    # Reading ----------------------------------------------------------------------------------

    def read_structured(self, request: ModelRequest) -> RecordedCall:
        """The recorded response to `request`; :class:`MissingFixtureError` when nobody recorded it."""
        return self._read(
            "generate_structured",
            self.structured_path(request),
            request.model_dump(mode="json"),
            prompt=request.prompt,
        )

    def read_embedding(self, texts: Sequence[str]) -> RecordedCall:
        """The recorded response to embedding `texts`."""
        return self._read("embed", self.embedding_path(texts), {"texts": list(texts)})

    def read_rerank(self, query: str, documents: Sequence[str]) -> RecordedCall:
        """The recorded response to reranking `documents` for `query`."""
        request: dict[str, JsonValue] = {"documents": list(documents), "query": query}
        return self._read("rerank", self.rerank_path(query, documents), request)

    def _write(
        self, call: str, path: Path, request: Mapping[str, JsonValue], response: Mapping[str, JsonValue]
    ) -> Path:
        document: dict[str, JsonValue] = {
            "call": call,
            "cassette_format": CASSETTE_FORMAT,
            "key": path.stem,
            "request": dict(request),
            "response": dict(response),
        }
        write_pretty_json(path, redact(document))
        return path

    def _read(
        self,
        call: str,
        path: Path,
        request: Mapping[str, JsonValue],
        *,
        prompt: ModelPrompt | None = None,
    ) -> RecordedCall:
        document = read_json_object(path)
        if document is None:
            raise self._missing(call, path, prompt)
        if document.get("cassette_format") != CASSETTE_FORMAT:
            raise FixtureFileError(path, f"it is not a format-{CASSETTE_FORMAT} cassette")
        if document.get("call") != call or document.get("key") != path.stem:
            raise FixtureFileError(path, f"it is not the {call} cassette filed under this key")
        recorded_request = document.get("request")
        if recorded_request != dict(request):
            raise self._missing(
                call,
                path,
                prompt,
                detail=(
                    f"the cassette at this key recorded {recorded_request!r}; this call is {dict(request)!r}"
                ),
            )
        response = document.get("response")
        if not isinstance(response, dict):
            raise FixtureFileError(path, "it has no `response` object")
        return RecordedCall(path=path, response=dict(response))  # pyright: ignore[reportUnknownArgumentType]

    def _missing(
        self, call: str, path: Path, prompt: ModelPrompt | None, *, detail: str | None = None
    ) -> MissingFixtureError:
        return MissingFixtureError(
            call=call,
            key=path.stem,
            location=path,
            prompt_id=prompt.prompt_id if prompt is not None else None,
            prompt_version=prompt.prompt_version if prompt is not None else None,
            detail=detail,
            hint=_HINT,
        )


class RecordReplayModelRouter:
    """A `ModelRouter` that records a real router's calls, replays them, or passes them through."""

    def __init__(
        self,
        delegate: ModelRouter | None,
        *,
        mode: ModelMode,
        cassette_dir: Path,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        """Wrap `delegate` in `mode`, reading and writing cassettes under `cassette_dir`.

        `delegate` is the real router. Replay never holds it, so it may be `None` there; record
        and live need it. `environ` is where `CI` is read from, the process environment by default.

        Raises :class:`RecordingRefusedError` for record mode when `CI` is true, and
        `ConfigurationError` for record or live mode with no router to call.
        """
        if mode is ModelMode.RECORD:
            refuse_recording_in_ci(environ)
        if mode is not ModelMode.REPLAY and delegate is None:
            raise ConfigurationError(
                f"{mode.value} mode calls a real model router, and none was given", field="model_mode"
            )
        self.mode = mode
        """What this router does with each call."""
        self.cassettes = CassetteDirectory(cassette_dir)
        """Where cassettes are read from and written to."""
        self._delegate = None if mode is ModelMode.REPLAY else delegate

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        request = ModelRequest.build(task_class, prompt, schema, params)
        if self._delegate is None:
            return self._replay_structured(request, schema)
        response = await self._delegate.generate_structured(task_class, prompt, schema, params)
        if self.mode is ModelMode.RECORD:
            self.cassettes.write_structured(request, response.model_dump(mode="json"))
        return response

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embed needs at least one text, and no text may be blank")
        if self._delegate is None:
            return self._replay_embedding(texts)
        response = await self._delegate.embed(texts)
        if self.mode is ModelMode.RECORD:
            self.cassettes.write_embedding(texts, response.model_dump(mode="json"))
        return response

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        if not query.strip() or not documents:
            raise ValueError("rerank needs a query and at least one document")
        if self._delegate is None:
            return self._replay_rerank(query, documents)
        response = await self._delegate.rerank(query, documents)
        if self.mode is ModelMode.RECORD:
            self.cassettes.write_rerank(query, documents, response.model_dump(mode="json"))
        return response

    # Replay -----------------------------------------------------------------------------------

    def _replay_structured[OutputT: BaseModel](
        self, request: ModelRequest, schema: type[OutputT]
    ) -> ModelResponse[OutputT]:
        recorded = self.cassettes.read_structured(request)
        response = recorded.response
        route = _replayed_route(recorded, response.get("route"))
        usage = _validated(recorded, ModelUsage, response.get("usage"))
        prompt = request.prompt
        try:
            output = schema.model_validate(response.get("output"))
        except ValidationError as error:
            raise InvalidModelOutput(
                prompt.prompt_id, prompt.prompt_version, str(error), model_id=route.model_id
            ) from error
        return _validated(
            recorded,
            ModelResponse[schema],
            {
                "output": output,
                "route": route,
                "usage": usage,
                "prompt_id": prompt.prompt_id,
                "prompt_version": prompt.prompt_version,
                "provider_request_id": response.get("provider_request_id"),
                "invoked_at": response.get("invoked_at"),
            },
        )

    def _replay_embedding(self, texts: Sequence[str]) -> EmbeddingResponse:
        recorded = self.cassettes.read_embedding(texts)
        replayed = _validated(
            recorded,
            EmbeddingResponse,
            {**recorded.response, "route": _replayed_route(recorded, recorded.response.get("route"))},
        )
        if len(replayed.vectors) != len(texts):
            raise FixtureFileError(
                recorded.path, f"it holds {len(replayed.vectors)} vectors for {len(texts)} texts"
            )
        return replayed

    def _replay_rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        recorded = self.cassettes.read_rerank(query, documents)
        replayed = _validated(
            recorded,
            RerankResponse,
            {**recorded.response, "route": _replayed_route(recorded, recorded.response.get("route"))},
        )
        if sorted(result.index for result in replayed.results) != list(range(len(documents))):
            raise FixtureFileError(
                recorded.path, f"it does not rank each of the {len(documents)} documents once"
            )
        return replayed


def refuse_recording_in_ci(environ: Mapping[str, str] | None = None) -> None:
    """Raise :class:`RecordingRefusedError` when `CI` is true in `environ` (the process environment)."""
    if running_in_ci(environ):
        raise RecordingRefusedError(
            f"record mode is refused when {CI_VARIABLE}=true: CI replays cassettes and never "
            "records them. Record on a developer machine, with credentials, and commit the cassettes.",
            field="model_mode",
            source=f"env:{CI_VARIABLE}",
        )


def _replayed_route(recorded: RecordedCall, route: object) -> ResolvedRoute:
    """The recorded route, marked as answered offline: provider `fake`, no region, no profile."""
    original = _validated(recorded, ResolvedRoute, route)
    return original.model_copy(
        update={"provider": ModelProvider.FAKE, "region": None, "inference_profile": None}
    )


def _validated[ModelT: BaseModel](recorded: RecordedCall, model: type[ModelT], value: object) -> ModelT:
    try:
        return model.model_validate(value)
    except ValidationError as error:
        raise FixtureFileError(
            recorded.path, f"its recorded {model.__name__} is not valid: {error}"
        ) from error

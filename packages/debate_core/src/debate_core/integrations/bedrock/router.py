"""`BedrockModelRouter`: the production `ModelRouter`, on Amazon Bedrock's runtime API.

Every call is routed by the routing file (`config/model_routing.*.yaml`, read by
:class:`~debate_core.integrations.models.routing_policy.RoutingPolicy`): the model id, inference
profile, region and parameters all come from there, and none is written in this module.

* **Structured output** goes through Converse with the requested Pydantic schema's JSON Schema as
  the single tool, and `toolChoice` `auto`. Never a forced choice: the current Claude models reject
  `any` and `tool`, and Bedrock lists its structured-output option as unsupported for them (model
  cards checked 2026-10-16, cited in v1-e05-t01's report; amended spec, ac2). The tool's input is
  validated as the schema. A response that does not call the tool, or calls it with input the
  schema refuses, raises :class:`~debate_core.application.errors.InvalidModelOutput`, which the
  structured-output guard repairs (v1-e05-t05). The answer is first handed to record mode
  (:mod:`debate_core.integrations.models.received_answer`), which writes a refused one to its
  cassette, so a repaired call recorded live replays both halves (v1-e05-t10).
* **Embeddings** go through InvokeModel on Titan Text Embeddings V2, one text per request, which
  is how that model takes them; `dimensions` comes from the embeddings route when it names one.
* **Rerank** goes through InvokeModel on Cohere Rerank, every document in one request.

## Credentials

From the profile `models.aws_profile` names (v1-e05-t08-bedrock-invoke-access): the SSO profile of
the environment's `Debate<Env>BedrockInvoker` permission set, which the composition root passes in
as `aws_profile`. Never from `AWS_PROFILE`: the client's session reads no profile from the
environment, so a shell holding the evidence profile, or the other environment's, cannot decide
which role a model call is made as. With no profile the credentials come from the rest of botocore's
chain: the environment's keys, the config's default, an instance or container role. No key, account
id or profile name is written into this code.

## Retries

A call refused for rate (`ThrottlingException`) or briefly unavailable
(`ServiceUnavailableException`, `ModelNotReadyException`, `InternalServerException`) is sent again,
up to its route's `max_attempts` attempts in all, waiting a full-jitter backoff between them: a
random wait between zero and `min(cap, base * 2 ** (attempt - 1))`. Nothing else is retried
(:mod:`debate_core.integrations.bedrock.failures`). botocore's own retries are switched off, so the
route's bound is the only one.

## Threads

boto3 is synchronous, so each request runs in a worker thread (`asyncio.to_thread`) and the event
loop is free while it waits. A botocore client is safe to call from several threads; the router
keeps one per region and timeout, built on first use.
"""

from __future__ import annotations

import asyncio
import functools
import json
import random
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final, Protocol, cast

import boto3
import botocore.session
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ValidationError

from debate_core.application.errors import InvalidModelOutput, ModelUnavailableError, OutputProblem
from debate_core.application.model_errors import describe_problems
from debate_core.application.ports.providers import Clock
from debate_core.application.structured_output import missing_tool_call, validate_model_output
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    RerankResponse,
    RerankResult,
    ResolvedRoute,
    TaskClass,
)
from debate_core.integrations.bedrock.failures import PROVIDER, is_retried, translate_bedrock_error
from debate_core.integrations.bedrock.prompt_rendering import PromptRenderer, refuse_unregistered_prompt
from debate_core.integrations.models.received_answer import hand_over_answer
from debate_core.integrations.models.routing_policy import RoutingPolicy

__all__ = [
    "ACCEPTED_STOP_REASONS",
    "CONNECT_TIMEOUT_SECONDS",
    "DEFAULT_BACKOFF_BASE_SECONDS",
    "DEFAULT_BACKOFF_CAP_SECONDS",
    "REPEATED_TOOL_CALL",
    "SERVICE_NAME",
    "UNFINISHED_ANSWER",
    "BedrockModelRouter",
    "BedrockRuntimeClient",
    "ClientFactory",
    "build_bedrock_runtime_client",
    "client_config",
    "converse_request",
    "full_jitter",
    "tool_name_for",
]

SERVICE_NAME: Final = "bedrock-runtime"
"""The botocore service every call goes to."""

CONNECT_TIMEOUT_SECONDS: Final = 10.0
"""Longest wait for a connection to open. A route's `timeout_seconds` bounds the read instead."""

DEFAULT_BACKOFF_BASE_SECONDS: Final = 1.0
"""Ceiling of the first retry's wait. Each later ceiling doubles, up to the cap."""

DEFAULT_BACKOFF_CAP_SECONDS: Final = 20.0
"""Highest ceiling a retry's wait can have, however many attempts came before."""

ACCEPTED_STOP_REASONS: Final = frozenset({"tool_use", "end_turn"})
"""Converse stop reasons a structured answer may come with. `max_tokens` means the tool input was
cut off; `guardrail_intervened` or `content_filtered` mean it was withheld; any other is not an
answer either."""

UNFINISHED_ANSWER: Final = "unfinished_answer"
"""The problem type of an answer that stopped for a reason not in :data:`ACCEPTED_STOP_REASONS`."""

REPEATED_TOOL_CALL: Final = "repeated_tool_call"
"""The problem type of an answer that called the schema's tool more than once."""

_TOOL_NAME_UNSAFE: Final = re.compile(r"[^A-Za-z0-9_-]")
_TOOL_NAME_LIMIT: Final = 64
_JSON: Final = "application/json"
_COHERE_RERANK_API_VERSION: Final = 2


class BedrockRuntimeClient(Protocol):
    """The two `bedrock-runtime` operations this adapter calls, as a boto3 client exposes them."""

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        """Bedrock's Converse operation."""
        ...

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        """Bedrock's InvokeModel operation."""
        ...


type ClientFactory = Callable[[str, float], BedrockRuntimeClient]
"""Builds the client for a region and a read timeout in seconds. Tests pass one holding a Stubber."""

_NO_PROFILE_FROM_THE_ENVIRONMENT: Final = {"profile": (None, None, None, None)}
"""botocore's `profile` session variable with no environment variable behind it.

By default botocore reads the profile from `AWS_DEFAULT_PROFILE` and `AWS_PROFILE`
(`BOTOCORE_DEFAUT_SESSION_VARIABLES`); a session built with this reads it from nowhere but the
`profile` it is given.
"""

type Sleep = Callable[[float], Awaitable[None]]
"""Waits the given number of seconds between attempts."""

type Jitter = Callable[[float], float]
"""Picks the wait before a retry, given the ceiling for that attempt."""


def full_jitter(ceiling: float) -> float:
    """A wait drawn uniformly from zero to `ceiling`: the backoff's jitter."""
    return random.uniform(0.0, ceiling)  # noqa: S311 - spreading retries out, not cryptography


def client_config(timeout_seconds: float) -> Config:
    """The botocore settings of a client whose calls may take `timeout_seconds` to answer.

    botocore's own retries are off (`total_max_attempts` 1, the first attempt only), so a call is
    sent no more times than its route allows.
    """
    return Config(
        connect_timeout=min(CONNECT_TIMEOUT_SECONDS, timeout_seconds),
        read_timeout=timeout_seconds,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )


def build_bedrock_runtime_client(
    region: str, timeout_seconds: float, *, profile: str | None = None
) -> BedrockRuntimeClient:
    """A `bedrock-runtime` client for `region`, signed with `profile` and never with `AWS_PROFILE`.

    A new :class:`boto3.session.Session` over a botocore session that reads no profile from the
    environment (module docstring, "Credentials"). `profile` is `models.aws_profile`; with none, the
    credentials are what the rest of botocore's chain finds. A profile the AWS config lacks fails
    here, translated like any other failure (:mod:`debate_core.integrations.bedrock.failures`).
    """
    try:
        settings_only = botocore.session.Session(
            session_vars=_NO_PROFILE_FROM_THE_ENVIRONMENT, profile=profile
        )
        session = boto3.session.Session(botocore_session=settings_only, region_name=region)
        # boto3-stubs is installed for s3 only, so every other service's client is Unknown to the
        # type checker; narrowed to this line, and typed by the Protocol it is returned as.
        return session.client(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            SERVICE_NAME, config=client_config(timeout_seconds)
        )
    except BotoCoreError as error:
        raise translate_bedrock_error(error, f"{SERVICE_NAME} in {region}") from error


def tool_name_for(schema: type[BaseModel]) -> str:
    """The name of the one tool a structured call offers: the schema's class name, made safe for Bedrock."""
    return _TOOL_NAME_UNSAFE.sub("_", schema.__name__)[:_TOOL_NAME_LIMIT]


def converse_request(
    route: ResolvedRoute, user: str, system: str | None, schema: type[BaseModel]
) -> dict[str, Any]:
    """The Converse request for one structured call: the schema as the only tool, chosen `auto`.

    `inferenceConfig` carries only what the route sets, and `outputConfig` only an effort the
    route sets, so an unset parameter is never sent and the model's own default applies; the
    current Claude models refuse any temperature but theirs.
    """
    description = (schema.__doc__ or "").strip().split("\n\n")[0] or f"Record the {schema.__name__} answer."
    request: dict[str, Any] = {
        "modelId": route.invocation_target,
        "messages": [{"role": "user", "content": [{"text": user}]}],
        "toolConfig": {
            "tools": [
                {
                    "toolSpec": {
                        "name": tool_name_for(schema),
                        "description": " ".join(description.split()),
                        "inputSchema": {"json": schema.model_json_schema()},
                    }
                }
            ],
            "toolChoice": {"auto": {}},
        },
    }
    if system is not None:
        request["system"] = [{"text": system}]
    inference: dict[str, Any] = {}
    if route.max_tokens is not None:
        inference["maxTokens"] = route.max_tokens
    if route.temperature is not None:
        inference["temperature"] = route.temperature
    if inference:
        request["inferenceConfig"] = inference
    if route.effort is not None:
        request["outputConfig"] = {"effort": route.effort.value}
    return request


class BedrockModelRouter:
    """A `ModelRouter` that calls Amazon Bedrock, routed by a validated routing policy.

    `render_prompt` turns a registered prompt into text: the prompt registry's `render`
    (v1-e05-t04-prompt-registry, through `bedrock_router_factory`). Without one the default refuses,
    so `generate_structured` sends nothing. `aws_profile` is the profile every client is signed
    with, `models.aws_profile`. `client_factory` builds a client per region and read timeout
    (:func:`build_bedrock_runtime_client` with `aws_profile` by default; a Stubber-holding client in
    tests, which then ignores `aws_profile`). `sleep` and `jitter` are the backoff's wait and its random
    part, injected so a test can count waits without taking them.
    """

    def __init__(
        self,
        policy: RoutingPolicy,
        *,
        aws_profile: str | None = None,
        render_prompt: PromptRenderer = refuse_unregistered_prompt,
        client_factory: ClientFactory | None = None,
        clock: Clock | None = None,
        sleep: Sleep = asyncio.sleep,
        jitter: Jitter = full_jitter,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        backoff_cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS,
    ) -> None:
        if backoff_base_seconds <= 0 or backoff_cap_seconds < backoff_base_seconds:
            raise ValueError("the backoff needs a positive base no larger than its cap")
        self._policy = policy
        self._render_prompt = render_prompt
        self._client_factory: ClientFactory = client_factory or functools.partial(
            build_bedrock_runtime_client, profile=aws_profile
        )
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_cap_seconds = backoff_cap_seconds
        self._clients: dict[tuple[str, float], BedrockRuntimeClient] = {}

    # ----------------------------------------------------------------------------------------
    # The port
    # ----------------------------------------------------------------------------------------

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        ModelRequest.build(task_class, prompt, schema, params)  # refuses a scoring class first
        route = self._policy.resolve(task_class, params)
        rendered = self._render_prompt(prompt)
        request = converse_request(route, rendered.user, rendered.system, schema)
        invoked_at = self._now()
        response, latency_ms = await self._send(route, task_class, "converse", request)
        reported = response.get("usage", {})
        usage = ModelUsage(
            input_tokens=reported.get("inputTokens"),
            output_tokens=reported.get("outputTokens"),
            latency_ms=latency_ms,
        )
        output = _structured_output(response, schema, prompt, route, usage)
        return ModelResponse[schema](
            output=output,
            route=route,
            usage=usage,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            provider_request_id=_request_id(response),
            invoked_at=invoked_at,
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embed needs at least one text, and no text may be blank")
        route = self._policy.resolve(TaskClass.EMBEDDINGS)
        dimensions = self._policy.route_for(TaskClass.EMBEDDINGS).dimensions
        invoked_at = self._now()
        vectors: list[tuple[float, ...]] = []
        input_tokens: int | None = 0
        latency_ms = 0.0
        request_ids: list[str] = []
        for text in texts:
            body: dict[str, Any] = {"inputText": text}
            if dimensions is not None:
                body["dimensions"] = dimensions
            request = _invoke(route, body)
            response, elapsed = await self._send(route, TaskClass.EMBEDDINGS, "invoke_model", request)
            answer = _read_body(response, route)
            vectors.append(_embedding_of(answer, route))
            input_tokens = _add_count(input_tokens, answer.get("inputTextTokenCount"))
            latency_ms += elapsed
            request_id = _request_id(response)
            if request_id is not None:
                request_ids.append(request_id)
        return EmbeddingResponse(
            vectors=tuple(vectors),
            route=route,
            usage=ModelUsage(input_tokens=input_tokens, latency_ms=latency_ms),
            provider_request_id=request_ids[0] if request_ids else None,
            invoked_at=invoked_at,
        )

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        if not query.strip() or not documents:
            raise ValueError("rerank needs a query and at least one document")
        route = self._policy.resolve(TaskClass.RERANK)
        body = {
            "query": query,
            "documents": list(documents),
            "top_n": len(documents),
            "api_version": _COHERE_RERANK_API_VERSION,
        }
        invoked_at = self._now()
        response, latency_ms = await self._send(route, TaskClass.RERANK, "invoke_model", _invoke(route, body))
        results = _rerank_results(_read_body(response, route), len(documents), route)
        return RerankResponse(
            results=results,
            route=route,
            usage=ModelUsage(latency_ms=latency_ms),
            provider_request_id=_request_id(response),
            invoked_at=invoked_at,
        )

    # ----------------------------------------------------------------------------------------
    # Clients and attempts
    # ----------------------------------------------------------------------------------------

    def client_for(self, route: ResolvedRoute) -> BedrockRuntimeClient:
        """The client calls on `route` go through: one per region and read timeout, built on first use."""
        if route.region is None:  # a loaded Bedrock route always has one; a hand-built one may not
            raise ValueError(f"route {route.task_class.value} has no region to call Bedrock in")
        key = (route.region, route.timeout_seconds)
        client = self._clients.get(key)
        if client is None:
            client = self._client_factory(route.region, route.timeout_seconds)
            self._clients[key] = client
        return client

    async def _send(
        self, route: ResolvedRoute, task_class: TaskClass, operation: str, request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], float]:
        """Send `request` until it succeeds, fails for good, or uses up the route's attempts.

        Returns the response and the wall-clock milliseconds of the attempt that succeeded.
        """
        client = self.client_for(route)
        call: Callable[..., dict[str, Any]] = getattr(client, operation)
        max_attempts = self._policy.route_for(task_class).max_attempts
        attempt = 1
        while True:
            started = time.perf_counter()
            try:
                response = await asyncio.to_thread(call, **request)
            except (ClientError, BotoCoreError) as error:
                if is_retried(error) and attempt < max_attempts:
                    await self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise translate_bedrock_error(error, route.invocation_target, attempts=attempt) from error
            return response, (time.perf_counter() - started) * 1000

    def _backoff(self, attempt: int) -> float:
        """The wait after failed attempt number `attempt` (1-based): full jitter under a doubling ceiling."""
        ceiling = min(self._backoff_cap_seconds, self._backoff_base_seconds * 2 ** (attempt - 1))
        return self._jitter(ceiling)

    def _now(self) -> datetime:
        return self._clock.now() if self._clock is not None else datetime.now(UTC)


# --------------------------------------------------------------------------------------------
# Reading responses
# --------------------------------------------------------------------------------------------


def _structured_output[OutputT: BaseModel](
    response: Mapping[str, Any],
    schema: type[OutputT],
    prompt: ModelPrompt,
    route: ResolvedRoute,
    usage: ModelUsage,
) -> OutputT:
    """The schema instance the model's call of the tool carries, or `InvalidModelOutput`.

    The tool's input is validated by :func:`~debate_core.application.structured_output.validate_model_output`,
    strictly, like every router's; the error names the problems and never the model's words. It
    carries `usage`, the call's tokens: an invalid answer was still billed (v1-e05-t07).
    """
    name = tool_name_for(schema)
    stop_reason = response.get("stopReason")

    def refuse(problem: OutputProblem) -> InvalidModelOutput:
        return InvalidModelOutput(
            prompt.prompt_id,
            prompt.prompt_version,
            describe_problems((problem,)),
            model_id=route.model_id,
            problems=(problem,),
            usage=usage,
        )

    message = _as_mapping(_as_mapping(response.get("output")).get("message"))
    calls = [_as_mapping(_as_mapping(block).get("toolUse")) for block in _as_list(message.get("content"))]
    ours = [call for call in calls if call.get("name") == name]
    hand_over_answer(_received_answer(ours))
    if stop_reason not in ACCEPTED_STOP_REASONS:
        raise refuse(
            OutputProblem(
                loc=(),
                type=UNFINISHED_ANSWER,
                msg=f"the model stopped with {stop_reason!r}, which is not a finished answer",
            )
        )
    if not ours:
        raise refuse(
            missing_tool_call(f"the model did not call the {name} tool (stopReason {stop_reason!r})")
        )
    if len(ours) > 1:
        raise refuse(
            OutputProblem(
                loc=(),
                type=REPEATED_TOOL_CALL,
                msg=f"the model called the {name} tool {len(ours)} times; one answer was asked for",
            )
        )
    return validate_model_output(
        schema, ours[0].get("input"), prompt=prompt, model_id=route.model_id, usage=usage
    )


def _received_answer(calls: Sequence[Mapping[str, Any]]) -> Any:
    """What the model answered, for record mode: its call's input, every input when it called the
    tool more than once, and `None` when it never called it (v1-e05-t10)."""
    inputs = [call.get("input") for call in calls]
    if not inputs:
        return None
    return inputs[0] if len(inputs) == 1 else inputs


def _invoke(route: ResolvedRoute, body: Mapping[str, Any]) -> dict[str, Any]:
    """An InvokeModel request carrying `body` as JSON."""
    return {
        "modelId": route.invocation_target,
        "contentType": _JSON,
        "accept": _JSON,
        "body": json.dumps(body).encode("utf-8"),
    }


def _read_body(response: Mapping[str, Any], route: ResolvedRoute) -> dict[str, Any]:
    """The JSON object an InvokeModel response's body holds."""
    body: Any = response.get("body")
    raw: Any = body.read() if hasattr(body, "read") else body  # a StreamingBody, or bytes from a double
    try:
        answer: Any = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise _unreadable(route, "its body is not JSON") from error
    if not isinstance(answer, dict):
        raise _unreadable(route, "its body is not a JSON object")
    return cast("dict[str, Any]", answer)


def _embedding_of(answer: Mapping[str, Any], route: ResolvedRoute) -> tuple[float, ...]:
    vector = _as_list(answer.get("embedding"))
    if not vector:
        raise _unreadable(route, "it has no embedding")
    try:
        return tuple(float(value) for value in vector)
    except (TypeError, ValueError) as error:
        raise _unreadable(route, "its embedding is not a list of numbers") from error


def _rerank_results(
    answer: Mapping[str, Any], expected: int, route: ResolvedRoute
) -> tuple[RerankResult, ...]:
    """Every document's score, best first, checked to name each document exactly once."""
    if not isinstance(answer.get("results"), list):
        raise _unreadable(route, "it has no results")
    try:
        results = [
            RerankResult(index=entry["index"], relevance_score=entry["relevance_score"])
            for entry in map(_as_mapping, _as_list(answer.get("results")))
        ]
    except (KeyError, TypeError, ValidationError) as error:
        raise _unreadable(route, "a result has no usable index or relevance_score") from error
    if sorted(result.index for result in results) != list(range(expected)):
        raise _unreadable(route, f"its results do not name each of the {expected} documents once")
    return tuple(sorted(results, key=lambda result: (-result.relevance_score, result.index)))


def _as_mapping(value: object) -> Mapping[str, Any]:
    """`value` when it is a JSON object, else an empty one: a missing piece reads as absent."""
    return cast("Mapping[str, Any]", value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    """`value` when it is a JSON array, else an empty one."""
    return cast("list[Any]", value) if isinstance(value, list) else []


def _request_id(response: Mapping[str, Any]) -> str | None:
    request_id = response.get("ResponseMetadata", {}).get("RequestId")
    return request_id if isinstance(request_id, str) and request_id else None


def _add_count(total: int | None, value: object) -> int | None:
    """`total` plus a reported token count; `None` once any response has not reported one."""
    if total is None or not isinstance(value, int) or value < 0:
        return None
    return total + value


def _unreadable(route: ResolvedRoute, reason: str) -> ModelUnavailableError:
    """A response this adapter cannot read: reported as the model failing to answer, never passed on."""
    return ModelUnavailableError(PROVIDER, route.invocation_target, f"answered with a response that {reason}")

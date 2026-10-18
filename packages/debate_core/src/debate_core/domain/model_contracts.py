"""The values a model call is made of: what is asked, what it was routed to, and what came back.

Application code never names a model. It names a :class:`TaskClass` ("this is high-volume
classification"), a prompt by id and version, the Pydantic schema it wants back and, at most, a
few :class:`ModelParams` overrides. Which model, region and inference profile answer is decided by
the routing file (`config/model_routing.*.yaml`, loaded by
:mod:`debate_core.integrations.models.routing_policy`) and reported back on every response as a
:class:`ResolvedRoute`, so whatever a model influenced can be traced to the model that influenced
it (architecture proposal §10, ADR-0005).

The port that exchanges these values is
:class:`~debate_core.application.ports.model_router.ModelRouter`. They live in the domain rather
than beside the port because a resolved route is provenance: it is persisted with generated
artifacts (v1-e05-t04-prompt-registry), and the domain is where persisted shapes are defined.

Nothing here holds a model identifier. Identifiers live only in the routing files.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Self

from pydantic import BaseModel, Field, JsonValue, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, UtcDatetime

__all__ = [
    "MAX_OUTPUT_TOKENS",
    "MAX_TEMPERATURE",
    "MAX_TIMEOUT_SECONDS",
    "MIN_TEMPERATURE",
    "Effort",
    "EmbeddingResponse",
    "ModelParams",
    "ModelPrompt",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ModelUsage",
    "RerankResponse",
    "RerankResult",
    "ResolvedRoute",
    "TaskClass",
]

MIN_TEMPERATURE: Final = 0.0
"""Lowest sampling temperature a route or a call may ask for."""

MAX_TEMPERATURE: Final = 1.0
"""Highest sampling temperature a route or a call may ask for.

1.0 because every generative route is a Claude model on Bedrock, whose range is 0 to 1. A wider
range would let a file load that every call then fails on. The current Claude models accept only
their default, so their routes leave temperature unset (see `config/model_routing.example.yaml`).
"""

MAX_OUTPUT_TOKENS: Final = 1_000_000
"""Ceiling on `max_tokens`, well above any model's real limit; it only catches typos."""

MAX_TIMEOUT_SECONDS: Final = 3600.0
"""Ceiling on a call's timeout. A call that needs longer than an hour is a batch job, not a call."""


class TaskClass(StrEnum):
    """What kind of work a model call is, which is what routing is decided on.

    Application code names a task class, never a model id. Routing a class to a model, a region
    and an inference profile is configuration, so a Bedrock model upgrade is a change to the
    routing files rather than to code across the platform (architecture proposal §10, ADR-0005).
    """

    COMPLEX_REASONING = "complex_reasoning"
    """Argument analysis, card tagging, coverage analysis, judge reasoning."""

    HIGH_VOLUME = "high_volume"
    """Cheap, frequent classification and extraction where benchmark quality is sufficient."""

    DEEP_AUDIT = "deep_audit"
    """Expensive, low-frequency file and strategy audits."""

    EMBEDDINGS = "embeddings"
    """Vector embeddings for semantic search."""

    RERANK = "rerank"
    """Cross-encoder reranking of retrieved candidates."""

    @property
    def is_generative(self) -> bool:
        """Whether calls of this class generate output, and so take a prompt and sampling parameters.

        Embeddings and rerank are scoring calls: they have no prompt, no temperature and no output
        length, and are reached through `embed` and `rerank` rather than `generate_structured`.
        """
        return self not in (TaskClass.EMBEDDINGS, TaskClass.RERANK)


class ModelProvider(StrEnum):
    """Who answers a routed call."""

    BEDROCK = "bedrock"
    """Amazon Bedrock (v1-e05-t02-bedrock-adapter). The only provider a routing file may name today."""

    FAKE = "fake"
    """An offline router that answered without calling any model (`debate_core.testing`, t03).

    Reported on the routes of responses a fake or replay router produced, so a recorded answer can
    never be mistaken for one a billed model gave. A routing file that names it is refused.
    """


class Effort(StrEnum):
    """How much thinking and output a Claude model spends on a call: its quality lever.

    Sent as Converse's `outputConfig.effort`. The current Claude models take no temperature but their
    default and always think, so effort is the one knob that trades quality against tokens on them
    (v1-e05-t01-model-router-port, Follow-up work). Unset sends none, and the model's own default
    applies; that default differs by model, so a route that cares names a level.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class ModelParams(DomainModel):
    """Per-call overrides of a task class's default parameters.

    Every field is optional, and an unset field keeps the route's default: an override says only
    what it changes (acceptance criterion ac4 of v1-e05-t01-model-router-port).
    """

    temperature: float | None = Field(
        default=None,
        ge=MIN_TEMPERATURE,
        le=MAX_TEMPERATURE,
        description="Sampling temperature for this call; unset keeps the route's.",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=MAX_OUTPUT_TOKENS,
        description="Output cap for this call; unset keeps the route's.",
    )
    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        le=MAX_TIMEOUT_SECONDS,
        description="Wall-clock limit for this call; unset keeps the route's.",
    )
    effort: Effort | None = Field(
        default=None, description="Effort level for this call; unset keeps the route's."
    )


class ModelPrompt(DomainModel):
    """Which registered prompt a generative call runs, and the values that fill it.

    The prompt's text is not here. It lives in the prompt registry (v1-e05-t04-prompt-registry)
    under its id and version, so a call site cannot carry prompt wording of its own and a prompt
    change is always a new version. `variables` are JSON values so the same call hashes to the
    same fixture key on every run and platform (v1-e05-t03-fake-replay-models).
    """

    prompt_id: NonEmptyText = Field(description="Identifier of the registered prompt.")
    prompt_version: NonEmptyText = Field(description="Semantic version of that prompt.")
    variables: dict[str, JsonValue] = Field(
        default_factory=dict[str, JsonValue], description="Values for the prompt's placeholders."
    )


class ModelRequest(DomainModel):
    """One generative call as a value: everything that decides its answer, minus the Python type.

    A router builds one from the arguments of `generate_structured`. It is what a replay router
    keys its cassettes on and what a fake router records, and it holds the output schema by its
    dotted path so that it can be serialized and compared.
    """

    task_class: TaskClass = Field(description="The task class the call is routed as.")
    prompt: ModelPrompt = Field(description="The registered prompt and its variables.")
    output_schema: NonEmptyText = Field(
        description="Dotted path of the Pydantic schema the output must validate as."
    )
    params: ModelParams = Field(default_factory=ModelParams, description="Per-call overrides.")

    @classmethod
    def build(
        cls,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[BaseModel],
        params: ModelParams | None = None,
    ) -> Self:
        """The request for one `generate_structured` call."""
        return cls(
            task_class=task_class,
            prompt=prompt,
            output_schema=f"{schema.__module__}.{schema.__qualname__}",
            params=params if params is not None else ModelParams(),
        )

    @model_validator(mode="after")
    def _require_generative_class(self) -> Self:
        if not self.task_class.is_generative:
            raise ValueError(
                f"task class {self.task_class.value!r} does not generate output; "
                "use embed or rerank, not generate_structured"
            )
        return self


class ResolvedRoute(DomainModel):
    """Where one call actually went, with the parameters it actually ran with.

    Returned on every response (ac4), and the provenance a generated artifact keeps
    (v1-e05-t04-prompt-registry). `temperature` and `max_tokens` are `None` when nothing was sent
    and the model's own default applied; that is the normal case for the current Claude models,
    which reject a non-default temperature.
    """

    task_class: TaskClass = Field(description="The task class the call was routed as.")
    provider: ModelProvider = Field(description="Who answered the call.")
    model_id: NonEmptyText = Field(description="The provider's identifier of the foundation model.")
    inference_profile: NonEmptyText | None = Field(
        default=None,
        description="Inference profile the call was sent through, when the model is reached through one.",
    )
    region: NonEmptyText | None = Field(
        default=None, description="Region the call was sent to; None for an offline router."
    )
    temperature: float | None = Field(
        default=None,
        ge=MIN_TEMPERATURE,
        le=MAX_TEMPERATURE,
        description="Temperature sent with the call; None means none was sent.",
    )
    max_tokens: int | None = Field(
        default=None, ge=1, le=MAX_OUTPUT_TOKENS, description="Output cap sent with the call."
    )
    timeout_seconds: float = Field(
        gt=0, le=MAX_TIMEOUT_SECONDS, description="Wall-clock limit the call ran under."
    )
    effort: Effort | None = Field(
        default=None, description="Effort level sent with the call; None means none was sent."
    )

    @property
    def invocation_target(self) -> str:
        """The identifier a call is addressed to: the inference profile when there is one."""
        return self.inference_profile if self.inference_profile is not None else self.model_id


class ModelUsage(DomainModel):
    """What one call cost, in the units a provider reports.

    Token counts are `None` only when the provider reports none (a rerank call is billed per
    search unit, not per token). Telemetry and budgets (v1-e05-t07-usage-telemetry) read these.
    """

    input_tokens: int | None = Field(default=None, ge=0, description="Tokens sent, when reported.")
    output_tokens: int | None = Field(default=None, ge=0, description="Tokens generated, when reported.")
    latency_ms: float = Field(ge=0, description="Wall-clock time of the call, in milliseconds.")


class ModelResponse[OutputT: BaseModel](DomainModel):
    """A validated structured output, with the route, prompt and usage of the call that produced it.

    Generic over the output schema, so `generate_structured(..., schema=CardSelection, ...)` is
    statically known to return a `ModelResponse[CardSelection]`. There is no free-form text on it:
    the only answer a caller can read is an instance of the schema it asked for.
    """

    output: OutputT = Field(description="The model's answer, validated against the requested schema.")
    route: ResolvedRoute = Field(description="Where the call went and what it ran with.")
    usage: ModelUsage = Field(description="Tokens and latency of the call.")
    prompt_id: NonEmptyText = Field(description="Identifier of the prompt that was run.")
    prompt_version: NonEmptyText = Field(description="Semantic version of that prompt.")
    provider_request_id: NonEmptyText | None = Field(
        default=None, description="The provider's id for the request, when it gives one."
    )
    invoked_at: UtcDatetime = Field(description="When the call was made, in UTC.")


class EmbeddingResponse(DomainModel):
    """One vector per input text, in input order, all of one length."""

    vectors: tuple[tuple[float, ...], ...] = Field(
        min_length=1, description="One embedding per input text, in the order the texts were given."
    )
    route: ResolvedRoute = Field(description="Where the call went.")
    usage: ModelUsage = Field(description="Tokens and latency of the call.")
    provider_request_id: NonEmptyText | None = Field(
        default=None, description="The provider's id for the request, when it gives one."
    )
    invoked_at: UtcDatetime = Field(description="When the call was made, in UTC.")

    @property
    def dimensions(self) -> int:
        """Length of every vector in this response."""
        return len(self.vectors[0])

    @model_validator(mode="after")
    def _check_vectors(self) -> Self:
        lengths = {len(vector) for vector in self.vectors}
        if 0 in lengths:
            raise ValueError("an embedding vector cannot be empty")
        if len(lengths) != 1:
            raise ValueError(f"every vector must have the same length; got lengths {sorted(lengths)}")
        return self


class RerankResult(DomainModel):
    """One document's place in a reranking: which document, and how relevant it scored."""

    index: int = Field(ge=0, description="Position of the document in the list that was passed in.")
    relevance_score: float = Field(description="The reranker's score; higher is more relevant.")


class RerankResponse(DomainModel):
    """The documents of one rerank call, most relevant first, each named by its input position.

    Results carry positions, never document text: the caller already holds the documents, and a
    reranker has no business handing evidence text back.
    """

    results: tuple[RerankResult, ...] = Field(description="One entry per document, most relevant first.")
    route: ResolvedRoute = Field(description="Where the call went.")
    usage: ModelUsage = Field(description="Latency, and tokens when reported.")
    provider_request_id: NonEmptyText | None = Field(
        default=None, description="The provider's id for the request, when it gives one."
    )
    invoked_at: UtcDatetime = Field(description="When the call was made, in UTC.")

    @model_validator(mode="after")
    def _check_results(self) -> Self:
        indices = [result.index for result in self.results]
        if len(set(indices)) != len(indices):
            raise ValueError("a document may appear only once in a reranking")
        scores = [result.relevance_score for result in self.results]
        if scores != sorted(scores, reverse=True):
            raise ValueError("results must be ordered by relevance_score, highest first")
        return self

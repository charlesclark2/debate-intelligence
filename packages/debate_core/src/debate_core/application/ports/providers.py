"""Ports for everything outside the platform, plus the two ambient dependencies.

Six ports live here:

* :class:`SearchProvider` — one discovery source in the federated search (OpenAlex, an RSS feed,
  a government search endpoint).
* :class:`ArticleFetcher` — retrieves the bytes at a URL, politely and without circumventing any
  access control.
* :class:`ContentExtractor` — turns those bytes into readable paragraphs.
* :class:`ModelRouter` — the single door every LLM call goes through.
* :class:`Clock` and :class:`IdGenerator` — the two ambient dependencies that would otherwise be
  hidden calls to `datetime.now()` and a random id generator, and would make a service's output
  untestable.

The value objects the ports exchange are defined here too, because a port whose signature named
`httpx.Response`, a `botocore` payload or an OpenAlex work record would defeat the point: swapping
the adapter would change the use case.

**Later tasks finalize three of these contracts.** v1-e07-t01-search-provider-contract fills out
:class:`CandidateResult` and the provider registry; v1-e04-t02-http-fetcher and
v1-e04-t04-content-extraction fill out :class:`FetchResult` and :class:`ExtractedContent`;
v1-e05-t01-model-router-port adds the routing policy behind :class:`ModelRouter`. What is here is
the shape the application layer codes against in the meantime, and those tasks extend it rather
than replace it.

**Async where the work is I/O.** Searching, fetching and invoking a model are network calls and
are `async`. Extraction is pure CPU over bytes already in memory, and reading a clock or minting
an id is immediate, so those are ordinary methods: making them `async` would buy nothing and
would force every caller to await.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, Self, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from debate_core.domain import (
    AccessStatus,
    ArticleIdentifiers,
    DomainModel,
    HttpUrlStr,
    NonEmptyText,
    SearchFilters,
    SourceType,
    Ulid,
    UtcDatetime,
)

__all__ = [
    "ArticleFetcher",
    "CandidateResult",
    "Clock",
    "ContentExtractor",
    "ExtractedContent",
    "ExtractionQuality",
    "FetchResult",
    "IdGenerator",
    "ModelInvocation",
    "ModelInvocationMetadata",
    "ModelRouter",
    "ModelTaskClass",
    "ProviderQuery",
    "ProviderResponse",
    "SearchProvider",
    "SourceMetadataHints",
]


# --------------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------------


class ProviderQuery(DomainModel):
    """What one provider is asked for.

    Reuses :class:`~debate_core.domain.SearchFilters` rather than restating a date window and a
    result cap, so the constraints a user set on a search are the same object every provider sees.
    Provider-specific syntax (an OpenAlex filter expression, an RSS feed URL) is the adapter's
    business and is built from these fields, never passed through them.
    """

    query: NonEmptyText = Field(description="The query text, as entered by the user.")
    filters: SearchFilters = Field(
        default_factory=SearchFilters, description="Date window, source types, language and result cap."
    )


class CandidateResult(DomainModel):
    """One result from one provider, normalized into the platform's vocabulary.

    "Candidate" because it is not yet an :class:`~debate_core.domain.Article`: the same paper
    found by three providers is three candidates that deduplication (E08) merges into one article
    by DOI, canonical URL and title/author similarity.

    Provider-specific payloads do not belong in these fields. An adapter that needs to keep its
    raw record stores it itself and references it by `provider_record_id`.
    """

    provider: NonEmptyText = Field(description="Provider name, as it appears in settings.")
    provider_record_id: NonEmptyText | None = Field(
        default=None, description="The provider's own id for this record, for auditing and re-fetching."
    )
    title: NonEmptyText = Field(description="Title as the provider reports it.")
    url: HttpUrlStr = Field(description="The URL the provider gave, before canonicalization.")
    canonical_url: HttpUrlStr | None = Field(
        default=None, description="Canonical URL, once E04-t01 has canonicalized `url`."
    )
    identifiers: ArticleIdentifiers = Field(
        default_factory=ArticleIdentifiers, description="External identifiers used to deduplicate."
    )
    source_type: SourceType = Field(
        default=SourceType.OTHER, description="Descriptive category, never a quality score."
    )
    authors: tuple[NonEmptyText, ...] = Field(default=(), description="Author names, in published order.")
    publication: NonEmptyText | None = Field(default=None, description="Journal, outlet or issuing body.")
    published_at: UtcDatetime | None = Field(default=None, description="Publication timestamp, in UTC.")
    snippet: str | None = Field(
        default=None,
        description=(
            "Abstract or snippet as supplied by the provider. Discovery context only: it is never "
            "quoted on a card, because card evidence only ever comes out of a stored snapshot."
        ),
    )
    open_access_url: HttpUrlStr | None = Field(
        default=None, description="Publisher-declared open-access copy, when the provider exposes one."
    )


class ProviderResponse(DomainModel):
    """What one provider returned for one query, including how it failed.

    A provider that times out or errors degrades the federated search to
    :attr:`~debate_core.domain.SearchStatus.PARTIAL`; it never fails the search. That is only
    possible if a partial answer is representable, which is what `partial` and `error` are for.
    """

    provider: NonEmptyText = Field(description="Provider name, as it appears in settings.")
    results: tuple[CandidateResult, ...] = Field(default=(), description="Results in provider order.")
    elapsed_ms: float = Field(ge=0, description="Wall-clock time the call took, in milliseconds.")
    partial: bool = Field(
        default=False, description="True when this provider did not fully answer the query."
    )
    error: str | None = Field(
        default=None, description="Human-readable reason the provider fell short, when it did."
    )

    @model_validator(mode="after")
    def _check_partial_is_reported(self) -> Self:
        if self.error is not None and not self.partial:
            raise ValueError("a ProviderResponse carrying an error must be marked partial")
        return self


@runtime_checkable
class SearchProvider(Protocol):
    """One discovery source in the federated search.

    Every provider — scholarly, news, government — is reached through this one method, which is
    what lets a provider be enabled, disabled or added in configuration instead of in code
    (architecture proposal §9).

    An adapter answers a query as well as it can and says so when it cannot: a partial answer
    comes back as a :class:`ProviderResponse` with `partial=True`. It raises
    :class:`~debate_core.application.errors.ProviderUnavailable` or
    :class:`~debate_core.application.errors.ProviderRateLimited` only when it returned nothing at
    all, and never raises a transport library's own exception.
    """

    @property
    def name(self) -> str:
        """Provider name as it appears in settings and in `Search.provider_set`."""
        ...

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        """Run one query against this provider and return its normalized results."""
        ...


# --------------------------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------------------------


class FetchResult(DomainModel):
    """The outcome of one retrieval attempt: the bytes, and everything about the response.

    Carries bytes, not text. Decoding is part of extraction, and the SHA-256 that anchors a
    snapshot is taken over exactly these bytes (architecture proposal §8).

    `access_status` records only what the fetcher itself knows — a refusal under robots rules, a
    404, a transport failure. Deciding that a 200 response is actually a paywall or a bot
    challenge is classification, and belongs to v1-e04-t03-access-status.
    """

    requested_url: HttpUrlStr = Field(description="The URL the fetch was asked for.")
    final_url: HttpUrlStr = Field(description="The URL that answered, after any redirects.")
    status_code: int | None = Field(
        default=None, ge=100, le=599, description="HTTP status, or None when no response arrived."
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="Response headers, lowercased keys, as strings."
    )
    content_type: NonEmptyText | None = Field(
        default=None, description="Content type as reported, parameters included."
    )
    body: bytes = Field(default=b"", description="Exactly the bytes received, unmodified.")
    elapsed_ms: float = Field(ge=0, description="Wall-clock time the fetch took, in milliseconds.")
    fetched_at: UtcDatetime = Field(description="When the fetch completed, in UTC.")
    access_status: AccessStatus = Field(
        default=AccessStatus.UNKNOWN,
        description="Transport-level outcome only; paywall classification happens downstream.",
    )

    @property
    def byte_size(self) -> int:
        """Number of bytes received."""
        return len(self.body)


@runtime_checkable
class ArticleFetcher(Protocol):
    """Retrieves the bytes behind a URL.

    Transport only: timeouts, retries, per-host politeness, redirect and size limits, robots
    rules. It does not classify, decode or extract.

    The platform never circumvents an access control (architecture proposal §14). A paywall, a
    login wall or a robots rule is reported through
    :class:`~debate_core.domain.AccessStatus`, and the source is simply not used as evidence.
    """

    async def fetch(self, url: HttpUrlStr) -> FetchResult:
        """Retrieve `url` and return the response.

        A refused or failed retrieval is a :class:`FetchResult` carrying the matching
        `access_status`, not an exception: "we could not read this source, and here is why" is an
        answer the platform records. Raises
        :class:`~debate_core.application.errors.ProviderUnavailable` only when the fetcher itself
        could not run the attempt.
        """
        ...


class SourceMetadataHints(DomainModel):
    """Unverified metadata an extractor noticed on the page.

    Deliberately separate from :class:`~debate_core.domain.Citation`, and deliberately all
    strings: these are raw, unparsed hints. CitationService (E06) is what turns a hint into a
    citation field with a recorded source, and a hint that cannot be confirmed leaves the cite
    field missing rather than filled in (architecture proposal §8).
    """

    title: str | None = Field(default=None, description="Title as the document states it.")
    authors: tuple[str, ...] = Field(default=(), description="Byline text, unparsed, in page order.")
    published_at: str | None = Field(default=None, description="Date string exactly as found.")
    site_name: str | None = Field(default=None, description="Site or publication name as stated.")
    canonical_url: str | None = Field(default=None, description="`rel=canonical` target, if declared.")


class ExtractionQuality(DomainModel):
    """Signals about how well extraction went, used to decide whether to trust the text."""

    character_count: int = Field(ge=0, description="Characters of readable text extracted.")
    paragraph_count: int = Field(ge=0, description="Paragraphs extracted.")
    fallback_used: bool = Field(
        default=False, description="True when the primary extractor fell short and a fallback ran."
    )
    boilerplate_ratio: float | None = Field(
        default=None, ge=0, le=1, description="Share of the document discarded as navigation or ads."
    )


class ExtractedContent(DomainModel):
    """Readable text pulled out of a fetched document.

    Paragraphs are kept as a sequence in reading order rather than as one string, because the
    paragraph is the unit a card's offsets are anchored to and the unit a model is allowed to
    refer to when it selects a passage.

    Extraction never changes words. No spelling fixes, no summarizing, no model cleanup: the text
    that reaches a card has to be the publisher's.
    """

    paragraphs: tuple[str, ...] = Field(default=(), description="Body paragraphs in reading order.")
    extractor_name: NonEmptyText = Field(description="Extractor that produced this text.")
    extractor_version: NonEmptyText = Field(
        description="Its version; recorded on the snapshot so extraction stays reproducible."
    )
    metadata_hints: SourceMetadataHints = Field(
        default_factory=SourceMetadataHints, description="Unverified metadata seen on the page."
    )
    quality: ExtractionQuality = Field(description="Signals about the extraction itself.")

    @property
    def text(self) -> str:
        """The paragraphs joined by blank lines, the form the normalizer (E03-t01) takes."""
        return "\n\n".join(self.paragraphs)


@runtime_checkable
class ContentExtractor(Protocol):
    """Turns fetched bytes into readable paragraphs.

    Synchronous: it is CPU work over bytes already in memory. A caller running many extractions
    concurrently moves them to a worker thread or process; that is a scheduling decision, not
    something this port should impose on every caller.
    """

    @property
    def name(self) -> str:
        """Extractor name, recorded on the snapshot as `extractor_version`'s subject."""
        ...

    def extract(self, fetched: FetchResult) -> ExtractedContent:
        """Extract readable text from an already-retrieved document.

        Takes the whole :class:`FetchResult` rather than loose bytes, because an extractor needs
        the content type to choose a strategy and the final URL to resolve relative links.

        Raises `ValueError` when the content type is one this extractor does not handle; the
        caller chooses the extractor, so being handed a PDF by an HTML extractor is a caller bug.
        """
        ...


# --------------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------------


class ModelTaskClass(StrEnum):
    """What kind of work a model call is, which is what routing is decided on.

    Application code names a task class, never a model id. Routing a class to a model, a region
    and an inference profile is configuration, so a Bedrock model upgrade is a config change
    rather than a code change across the platform (architecture proposal §10, ADR-005).

    The full routing policy arrives with v1-e05-t01-model-router-port; these are the classes it
    routes.
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


class ModelInvocationMetadata(DomainModel):
    """What actually happened on one model call.

    Persisted alongside anything a model influenced, so a generated artifact can always be traced
    to the model and prompt version that produced it, and so a prompt regression can be found by
    version rather than by memory (architecture proposal §10, prompt/version governance).
    """

    task_class: ModelTaskClass = Field(description="The task class the call was routed as.")
    model_id: NonEmptyText = Field(description="Resolved model identifier, e.g. a Bedrock model id.")
    prompt_id: NonEmptyText = Field(description="Identifier of the prompt that was used.")
    prompt_version: NonEmptyText = Field(description="Semantic version of that prompt.")
    region: NonEmptyText | None = Field(
        default=None, description="Region or inference profile the call was routed to."
    )
    temperature: float | None = Field(default=None, ge=0, description="Temperature actually used.")
    input_tokens: int | None = Field(default=None, ge=0, description="Tokens sent, when reported.")
    output_tokens: int | None = Field(default=None, ge=0, description="Tokens generated, when reported.")
    latency_ms: float = Field(ge=0, description="Wall-clock time of the call, in milliseconds.")
    invoked_at: UtcDatetime = Field(description="When the call was made, in UTC.")


@dataclass(frozen=True, slots=True)
class ModelInvocation[OutputT: BaseModel]:
    """A validated model output together with the provenance of the call that produced it.

    Generic over the output schema, so `invoke(..., output_type=CardSelection)` is statically
    known to return a `CardSelection`. A frozen dataclass rather than a Pydantic model because
    `output` has already been validated against its own schema and `metadata` against its; wrapping
    them would re-validate both for nothing.
    """

    output: OutputT
    """The model's answer, validated against the requested schema."""

    metadata: ModelInvocationMetadata
    """Which model, which prompt version, how many tokens, how long."""


@runtime_checkable
class ModelRouter(Protocol):
    """The single door every LLM call in the platform goes through.

    Two rules hold for every call, and they are why this port exists:

    **Structured output only.** A call names the Pydantic type it expects back and receives a
    validated instance of it. No application code parses free-form model text (architecture
    proposal §2, §10).

    **A model never supplies evidence text.** A schema may ask a model for paragraph ids, offsets,
    labels, confidences and explanations — for *which* passage to cut and *why*. The quotation
    itself is always sliced out of the stored snapshot afterwards. A schema whose field is meant
    to hold quoted evidence is a defect, not a feature (architecture proposal §8).

    Callers also name a :class:`ModelTaskClass` and a prompt by id and version, never a model id:
    the mapping from task class to model, region and parameters is configuration
    (v1-e05-t01-model-router-port).
    """

    async def invoke[OutputT: BaseModel](
        self,
        *,
        task_class: ModelTaskClass,
        prompt_id: str,
        prompt_version: str,
        output_type: type[OutputT],
        variables: Mapping[str, object] | None = None,
    ) -> ModelInvocation[OutputT]:
        """Run one prompt and return its output validated as `output_type`, plus call metadata.

        `variables` fills the placeholders of the registered prompt; the prompt text itself lives
        in the prompt registry (v1-e05-t04-prompt-registry), not in the call site.

        Raises :class:`~debate_core.application.errors.InvalidModelOutput` when the model's answer
        cannot be validated as `output_type`, and
        :class:`~debate_core.application.errors.ProviderUnavailable` or
        :class:`~debate_core.application.errors.ProviderRateLimited` when the model could not be
        reached. Never returns unvalidated text.
        """
        ...


# --------------------------------------------------------------------------------------------
# Ambient dependencies
# --------------------------------------------------------------------------------------------


@runtime_checkable
class Clock(Protocol):
    """Supplies the current time.

    Injected rather than called ambiently because timestamps in this platform are provenance:
    `retrieved_at` on a snapshot and `accessed_at` on a cite are part of what a card claims. A
    service that reads the clock through this port can be tested to the second, and a replay of a
    recorded run reproduces the same timestamps.
    """

    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime.

        Must be timezone-aware: the domain rejects naive datetimes outright, because a silently
        mislabelled timezone in a retrieval time is a provenance error.
        """
        ...


@runtime_checkable
class IdGenerator(Protocol):
    """Supplies new entity ids.

    Entities default their own ids from `debate_core.domain.new_id`, which is right for an entity
    built in isolation. A service that has to *know* the id it is about to create — to log it, to
    return it, or to write a second record referring to it — takes this port instead, which also
    makes the ids of a recorded test run reproducible.
    """

    def new_id(self) -> Ulid:
        """Return a new ULID in its canonical 26-character form."""
        ...

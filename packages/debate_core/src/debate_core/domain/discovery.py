"""Discovery: what a provider is asked, what it answers, and how healthy it is.

Federated research asks several discovery providers (OpenAlex, Crossref, an RSS feed, a
government search endpoint) the same question and merges what comes back. These are the values
that cross that boundary, in the platform's vocabulary rather than any provider's:

* :class:`ProviderQuery` — what one provider is asked.
* :class:`CandidateResult` — one normalized result, with the :class:`Subject` values a provider
  says it is about (v1-e08-t15).
* :class:`ProviderResponse` — everything one provider returned for one query, including how it
  fell short.
* :class:`ProviderHealth` and :class:`BreakerState` — a provider's recent record, for the CLI's
  provider status footer.
* :class:`ProviderStatus` and :class:`ProviderOutcome` — how one call in a federated search ended,
  and what it returned. Stored with the search (v1-e08-t01-federated-search-service), so a search
  can be audited and replayed.

The port they travel through is :class:`~debate_core.application.ports.providers.SearchProvider`,
which re-exports the first three so that code written against the port keeps one import. They
were defined there by v1-e02-t02-ports and moved here, unchanged in meaning, when
v1-e07-t01-search-provider-contract finalized them: they are plain values with no behaviour that
needs the application layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.base import DomainModel, HttpUrlStr, NonEmptyText, UtcDatetime
from debate_core.domain.enums import DatePrecision, SourceType
from debate_core.domain.search import SearchFilters

__all__ = [
    "BreakerState",
    "CandidateResult",
    "DatePrecision",
    "ProviderHealth",
    "ProviderOutcome",
    "ProviderQuery",
    "ProviderResponse",
    "ProviderStatus",
    "Subject",
    "SubjectScheme",
]


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


class SubjectScheme(StrEnum):
    """Whose vocabulary a :class:`Subject` comes from (v1-e08-t15)."""

    OPENALEX_KEYWORD = "openalex_keyword"
    """OpenAlex's keywords: short phrases saying what the work is about, best first, assigned by a model
    from the title, abstract and venue; a keyword joins the vocabulary once it describes 100 works."""


class Subject(DomainModel):
    """What a provider says a work is about, in the provider's own vocabulary (v1-e08-t15).

    A search suggests narrower follow-up queries from the subjects its first page shares
    (:mod:`debate_core.application.search_narrowing`). A subject is metadata, never evidence text.
    """

    scheme: SubjectScheme = Field(description="Whose vocabulary the subject is in.")
    name: NonEmptyText = Field(description="The subject as the provider names it.")
    provider_id: NonEmptyText | None = Field(
        default=None, description="The provider's id for the subject, when it gives one."
    )


class CandidateResult(DomainModel):
    """One result from one provider, normalized into the platform's vocabulary.

    "Candidate" because it is not yet an :class:`~debate_core.domain.Article`: the same paper
    found by three providers is three candidates that deduplication (E08) merges into one article
    by DOI, canonical URL and title/author similarity.

    Provider-specific payloads do not belong in these fields. A provider's own ids go in
    `identifiers` (or `provider_record_id`), and an adapter that keeps its raw record stores it
    itself and points at it with `raw_ref`; nothing else on this model is a provider's field.
    `subjects` holds a provider's vocabulary as values that name their scheme, as `identifiers`
    holds its ids (v1-e08-t15).

    The identifiers validate themselves: a DOI is reduced to its bare lowercase form whichever
    spelling the provider used (`https://doi.org/10.1038/NATURE12373` becomes
    `10.1038/nature12373`), and `published_at` must be timezone-aware and is stored in UTC.
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
    date_precision: DatePrecision | None = Field(
        default=None,
        description=(
            "How much of `published_at` the provider knows. `year` and `month` mean `published_at` is "
            "the first instant of that year or month and no day is known; `day`, or None as for every "
            "provider before Crossref, means the date is known to the day."
        ),
    )
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
    open_access: bool | None = Field(
        default=None,
        description=(
            "Whether the provider says a free-to-read copy exists, even one it gives no usable link "
            "for; None when it does not say."
        ),
    )
    citation_count: int | None = Field(
        default=None,
        ge=0,
        description="How many works cite this one, by the provider's count; None when unknown.",
    )
    subjects: tuple[Subject, ...] = Field(
        default=(),
        exclude_if=lambda subjects: not subjects,
        description="What the provider says the work is about, in its order; left out when it says nothing.",
    )
    raw_ref: NonEmptyText | None = Field(
        default=None,
        description=(
            "Where the adapter kept the provider's raw record, if it kept one: an opaque reference "
            "(a blob key, a recorded fixture's name), never the payload itself."
        ),
    )

    @model_validator(mode="after")
    def _check_a_partial_date_starts_its_period(self) -> Self:
        precision, published = self.date_precision, self.published_at
        if precision is None:
            return self
        if published is None:
            raise ValueError("a candidate has a date_precision without a published_at")
        start = {
            DatePrecision.DAY: published,
            DatePrecision.MONTH: datetime(published.year, published.month, 1, tzinfo=UTC),
            DatePrecision.YEAR: datetime(published.year, 1, 1, tzinfo=UTC),
        }[precision]
        if published != start:
            raise ValueError(
                f"a {precision.value}-precision published_at must be the first instant of its "
                f"{precision.value}, {start.isoformat()}, not {published.isoformat()}"
            )
        return self


class ProviderResponse(DomainModel):
    """What one provider returned for one query, including how it failed.

    A provider that times out or errors degrades the federated search to
    :attr:`~debate_core.domain.SearchStatus.PARTIAL`; it never fails the search. That is only
    possible if a partial answer is representable, which is what `partial` and `error` are for.

    A shortfall that should be reported but not make the answer partial goes in `notes`: today, only
    a feed that has failed on every read for days, which a retry will not fix (PM ruling 2026-11-05).
    A search record stored before `notes` existed reads with none.

    Every result names the provider that answered. A response carrying another provider's result
    is refused, because deduplication (E08) and the health footer both attribute results by that
    name.
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
    notes: tuple[str, ...] = Field(
        default=(),
        description=(
            "Shortfalls reported without making the answer partial: a feed that has failed on every "
            "read for days, named with when it started failing (v1-e07-t14)."
        ),
    )

    @model_validator(mode="after")
    def _check_partial_is_reported(self) -> Self:
        if self.error is not None and not self.partial:
            raise ValueError("a ProviderResponse carrying an error must be marked partial")
        return self

    @model_validator(mode="after")
    def _check_results_name_this_provider(self) -> Self:
        strangers = sorted({result.provider for result in self.results if result.provider != self.provider})
        if strangers:
            named = ", ".join(map(repr, strangers))
            raise ValueError(f"a ProviderResponse from {self.provider!r} carries results from {named}")
        return self


class BreakerState(StrEnum):
    """Where a provider's circuit breaker stands.

    The breaker is what stops a federated search from waiting on a provider that has just failed
    several times in a row (architecture proposal §15).
    """

    CLOSED = "closed"
    """Calls go through. Consecutive failures are being counted."""

    OPEN = "open"
    """Calls are refused without reaching the provider until the cool-down ends."""

    HALF_OPEN = "half_open"
    """The cool-down has ended: the next call is a single probe that decides between the other two."""


class ProviderHealth(DomainModel):
    """A snapshot of one provider's recent record, for the CLI's provider status footer.

    `last_error` is the message the platform recorded, with every configured credential and the
    contact email removed. A snapshot is something a person reads and a log keeps, so nothing in it
    may be a secret.
    """

    provider: NonEmptyText = Field(description="Provider name, as it appears in settings.")
    state: BreakerState = Field(description="Where the circuit breaker stands right now.")
    consecutive_failures: int = Field(ge=0, description="Failures since the last success.")
    success_count: int = Field(ge=0, description="Calls the provider answered.")
    error_count: int = Field(ge=0, description="Calls that reached the provider and failed.")
    skipped_count: int = Field(
        ge=0, description="Calls refused without reaching the provider: breaker open or rate-limit hold."
    )
    not_asked_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Calls the adapter's own pace never sent, because their turn would have come too late; "
            "answered 'not asked', and neither a success, a failure nor a latency sample."
        ),
    )
    last_error: str | None = Field(default=None, description="The most recent failure, redacted.")
    last_error_at: UtcDatetime | None = Field(default=None, description="When that failure happened.")
    p50_latency_ms: float | None = Field(
        default=None, ge=0, description="Median latency of recent calls; None before the first call."
    )
    open_until: UtcDatetime | None = Field(
        default=None, description="When an open breaker lets a probe through."
    )
    rate_limited_until: UtcDatetime | None = Field(
        default=None, description="When the provider's own Retry-After ends, while one is in force."
    )

    @model_validator(mode="after")
    def _check_open_has_an_end(self) -> Self:
        if (self.state is BreakerState.OPEN) != (self.open_until is not None):
            raise ValueError("open_until is set exactly when the breaker is open")
        return self


class ProviderOutcome(StrEnum):
    """How one call to one provider ended, in a federated search.

    Only :attr:`OK` means the provider answered. Every other value is a different reason it did
    not, and the CLI says which, because "OpenAlex timed out" and "OpenAlex is benched after three
    failures" call for different things from the person reading the results.
    """

    OK = "ok"
    """The provider answered. Its answer may itself be partial (`ProviderResponse.partial`)."""

    TIMEOUT = "timeout"
    """No answer in time: the provider's own timeout, or the search's overall deadline."""

    ERROR = "error"
    """The provider was reached and failed: a server error, an unreadable answer, a refused connection."""

    RATE_LIMITED = "rate_limited"
    """The provider asked the platform to back off, on this call or on an earlier one still in force."""

    BREAKER_OPEN = "breaker_open"
    """Skipped without reaching the provider: its circuit breaker is open after repeated failures."""

    NOT_CONFIGURED = "not_configured"
    """The search asked for a provider that settings do not enable, so there was nothing to call."""


class ProviderStatus(DomainModel):
    """One provider's answer to one query in a federated search, or the reason there was none.

    The record a search keeps per call: the exact query asked, how the call ended and, when the
    provider answered, everything it returned as it returned it. That is what makes a search
    auditable after the fact ("why is this PARTIAL?") and its raw results replayable through later
    stages (deduplication, ranking) without asking the providers again.

    `error` is the message the platform recorded, which for a wrapped provider has every configured
    credential and the contact email already removed; it is never a provider's raw exception text.
    """

    provider: NonEmptyText = Field(description="Provider name, as it appears in settings.")
    query: ProviderQuery = Field(description="Exactly what the provider was asked.")
    outcome: ProviderOutcome = Field(description="How the call ended.")
    elapsed_ms: float = Field(ge=0, description="Time from the call starting to it ending, in milliseconds.")
    response: ProviderResponse | None = Field(
        default=None, description="What the provider returned; present exactly when the outcome is ok."
    )
    error: str | None = Field(
        default=None, description="Why there is no answer; present exactly when the outcome is not ok."
    )

    @model_validator(mode="after")
    def _check_answer_matches_outcome(self) -> Self:
        answered = self.outcome is ProviderOutcome.OK
        if answered != (self.response is not None):
            raise ValueError("a ProviderStatus carries a response exactly when its outcome is ok")
        if answered == (self.error is not None):
            raise ValueError("a ProviderStatus carries an error exactly when its outcome is not ok")
        if self.response is not None and self.response.provider != self.provider:
            raise ValueError(
                f"a ProviderStatus for {self.provider!r} carries a response from {self.response.provider!r}"
            )
        return self

"""Ports for everything outside the platform, plus the two ambient dependencies.

Six ports live here:

* :class:`SearchProvider` — one discovery source in the federated search (OpenAlex, an RSS feed,
  a government search endpoint).
* :class:`DiscoveryProviders` — the discovery sources settings enable, and how each is faring: what
  a federated search fans out over (v1-e08-t01-federated-search-service).
* :class:`ArticleFetcher` — retrieves the bytes at a URL, politely and without circumventing any
  access control.
* :class:`ContentExtractor` — turns those bytes into readable paragraphs.
* :class:`Clock` and :class:`IdGenerator` — the two ambient dependencies that would otherwise be
  hidden calls to `datetime.now()` and a random id generator, and would make a service's output
  untestable.

The value objects the ports exchange are defined here too, because a port whose signature named
`httpx.Response`, a `botocore` payload or an OpenAlex work record would defeat the point: swapping
the adapter would change the use case.

**Later tasks finalize two of these contracts.** v1-e07-t01-search-provider-contract finalized
:class:`SearchProvider`: its values (:class:`ProviderQuery`, :class:`CandidateResult`,
:class:`ProviderResponse`) now live in :mod:`debate_core.domain.discovery` and are re-exported
here, and the timeout, circuit breaker and registry every adapter is wrapped in live in
:mod:`debate_core.integrations.discovery`. v1-e04-t02-http-fetcher and
v1-e04-t04-content-extraction fill out :class:`FetchResult` and :class:`ExtractedContent`. What is
here is the shape the application layer codes against in the meantime, and those tasks extend it
rather than replace it. The model router began here too and now has its own module,
:mod:`debate_core.application.ports.model_router` (v1-e05-t01-model-router-port).

**Async where the work is I/O.** Searching and fetching are network calls and
are `async`. Extraction is pure CPU over bytes already in memory, and reading a clock or minting
an id is immediate, so those are ordinary methods: making them `async` would buy nothing and
would force every caller to await.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import Field

from debate_core.domain import (
    DomainModel,
    HttpUrlStr,
    NonEmptyText,
    Ulid,
)
from debate_core.domain.discovery import CandidateResult, ProviderHealth, ProviderQuery, ProviderResponse
from debate_core.retrieval.fetch_types import FetchResult

__all__ = [
    "ArticleFetcher",
    "CandidateResult",
    "Clock",
    "ContentExtractor",
    "DiscoveryProviders",
    "ExtractedContent",
    "ExtractionQuality",
    "FetchResult",
    "IdGenerator",
    "ProviderQuery",
    "ProviderResponse",
    "SearchProvider",
    "SourceMetadataHints",
]


# --------------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------------


@runtime_checkable
class SearchProvider(Protocol):
    """One discovery source in the federated search.

    The only discovery port. Every provider — scholarly, news, government — is reached through
    this one method, which is what lets a provider be enabled, disabled or added in configuration
    instead of in code (architecture proposal §9).

    An adapter answers a query as well as it can and says so when it cannot: a partial answer
    comes back as a :class:`ProviderResponse` with `partial=True`. It raises
    :class:`~debate_core.application.errors.ProviderUnavailable` or
    :class:`~debate_core.application.errors.ProviderRateLimited` only when it returned nothing at
    all, and never raises a transport library's own exception.

    An adapter does not time itself out, count its own failures or retry a refused call: the
    registry wraps every adapter in
    :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`, which does all three
    the same way for every provider and is itself a `SearchProvider`. The shared contract kit,
    :mod:`debate_core.testing.contracts.search_provider`, is what an adapter is held to.
    """

    @property
    def name(self) -> str:
        """Provider name as it appears in settings and in `Search.provider_set`."""
        ...

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        """Run one query against this provider and return its normalized results."""
        ...


@runtime_checkable
class DiscoveryProviders(Protocol):
    """The discovery providers settings enable, each ready to call, and the health of each.

    What a federated search fans out over. The application layer may not import
    :mod:`debate_core.integrations`, so it cannot take
    :class:`~debate_core.integrations.discovery.registry.ProviderRegistry` by name; this is the part
    of the registry a search needs, and the registry satisfies it as it stands. Every provider it
    hands out is already wrapped in its timeout, circuit breaker and rate-limit hold, so a caller
    adds none of its own.
    """

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        """The enabled providers, in settings order, each under its settings name."""
        ...

    def health(self) -> tuple[ProviderHealth, ...]:
        """One snapshot per enabled provider, in settings order, for the provider status footer."""
        ...


# --------------------------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------------------------

# FetchResult and the errors it carries live in debate_core.retrieval.fetch_types since
# v1-e04-t02-http-fetcher, beside the access classifier that reads them; FetchResult is re-exported
# here so the port's signature still names it.


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

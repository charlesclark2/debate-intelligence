"""Fakes of the provider ports: a discovery provider, a fetcher and a content extractor.

Each answers from a script or a rule, never from the network, for the ports in
:mod:`debate_core.application.ports.providers`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from debate_core.application.ports.providers import Clock
from debate_core.domain import AccessStatus
from debate_core.domain.discovery import CandidateResult, ProviderQuery, ProviderResponse
from debate_core.retrieval.extraction import (
    ExtractedContent,
    ExtractionQuality,
    UnverifiedMetadataHints,
)
from debate_core.retrieval.fetch_types import FetchResult
from debate_core.testing.fakes.clock_and_ids import FixedClock

__all__ = ["FakeArticleFetcher", "FakeContentExtractor", "FakeSearchProvider"]


class FakeSearchProvider:
    """A discovery provider that answers from a script.

    Configure it with results per query text, a default for anything else, and optionally a
    failure to raise — the three things a federated-search test needs in order to check that one
    provider dropping out downgrades the search to `PARTIAL` instead of failing it.
    """

    def __init__(
        self,
        name: str = "fake-provider",
        *,
        results_by_query: Mapping[str, Sequence[CandidateResult]] | None = None,
        default_results: Sequence[CandidateResult] = (),
        failure: Exception | None = None,
        partial: bool = False,
        elapsed_ms: float = 1.0,
    ) -> None:
        self._name = name
        self._results_by_query = dict(results_by_query or {})
        self._default_results = tuple(default_results)
        self._failure = failure
        self._partial = partial
        self._elapsed_ms = elapsed_ms
        self.queries: list[ProviderQuery] = []
        """Every query this provider was asked, in order, for assertions."""

    @property
    def name(self) -> str:
        return self._name

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        self.queries.append(query)
        if self._failure is not None:
            raise self._failure
        found = self._results_by_query.get(query.query, self._default_results)
        return ProviderResponse(
            provider=self._name,
            results=tuple(found)[: query.filters.max_results],
            elapsed_ms=self._elapsed_ms,
            partial=self._partial,
            error="configured to answer partially" if self._partial else None,
        )


class FakeArticleFetcher:
    """A fetcher that serves canned responses and 404s everything else.

    Unknown URLs come back as a `NOT_FOUND` :class:`~debate_core.application.ports.providers.
    FetchResult` rather than an exception, because that is what the port promises: a failed
    retrieval is an answer the platform records, not a crash.
    """

    def __init__(self, *, clock: Clock | None = None, elapsed_ms: float = 1.0) -> None:
        self._responses: dict[str, FetchResult] = {}
        self._clock: Clock = clock if clock is not None else FixedClock()
        self._elapsed_ms = elapsed_ms
        self.requested_urls: list[str] = []
        """Every URL this fetcher was asked for, in order."""

    def add(
        self,
        url: str,
        body: bytes,
        *,
        status_code: int = 200,
        content_type: str | None = "text/html; charset=utf-8",
        access_status: AccessStatus = AccessStatus.ACCESSIBLE,
        final_url: str | None = None,
    ) -> FetchResult:
        """Register the response this fetcher returns for `url`, and return it."""
        response = FetchResult(
            requested_url=url,
            final_url=final_url or url,
            status_code=status_code,
            headers={} if content_type is None else {"content-type": content_type},
            content_type=content_type,
            body=body,
            elapsed_ms=self._elapsed_ms,
            fetched_at=self._clock.now(),
            access_status=access_status,
        )
        self._responses[url] = response
        return response

    async def fetch(self, url: str) -> FetchResult:
        self.requested_urls.append(url)
        known = self._responses.get(url)
        if known is not None:
            return known
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=404,
            elapsed_ms=self._elapsed_ms,
            fetched_at=self._clock.now(),
            access_status=AccessStatus.NOT_FOUND,
        )


class FakeContentExtractor:
    """Splits a decoded body into paragraphs on blank lines.

    Deterministic and dependency-free, so a test that cares about what happens *around*
    extraction — snapshotting, hashing, cutting — does not need a real HTML sample or trafilatura.
    A test that cares about extraction itself belongs to v1-e04-t04-content-extraction.
    """

    version = "fake-1.0.0"

    def __init__(self, name: str = "fake-extractor") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def extract(self, fetched: FetchResult) -> ExtractedContent:
        content_type = (fetched.content_type or "text/plain").split(";")[0].strip().lower()
        if not content_type.startswith("text/") and content_type != "application/xhtml+xml":
            raise ValueError(f"{self._name} does not handle {content_type}")
        text = fetched.body.decode("utf-8", errors="replace")
        paragraphs = tuple(block.strip() for block in text.split("\n\n") if block.strip())
        return ExtractedContent(
            paragraphs=paragraphs,
            extractor_name=self._name,
            extractor_version=self.version,
            metadata_hints=UnverifiedMetadataHints(canonical_url=fetched.final_url),
            quality=ExtractionQuality(
                character_count=sum(len(paragraph) for paragraph in paragraphs),
                paragraph_count=len(paragraphs),
            ),
        )

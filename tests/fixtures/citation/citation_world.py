"""CitationService wired to in-memory stores and to the real Crossref client over respx (v1-e06-t01).

A case from this directory (`<case>.expected.json`) is stored the way ArticleService stores a
retrieval: the article saved, the page's raw bytes snapshotted by `SnapshotService.create` and read
back by `SnapshotService.load` with every integrity check. Crossref is the real
`CrossrefDoiClient`, answered by respx from `crossref/`; a request no answer was registered for
fails, and nothing leaves the process. The card edit service is wired beside it, so a student's
cite edit reaches the edit log exactly as it does in production (ac5).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
import respx
from tests.fixtures.verification.verification_world import card_from_markup

from debate_core.application.card_edit_service import CardEditService
from debate_core.application.citation_service import CitationService
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.settings import HttpSettings, ProviderSettings
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import AccessStatus, Article, ArticleIdentifiers, Card, Citation, ProvenanceMode
from debate_core.domain.enums import SpanPurpose
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan
from debate_core.evidence.selection import EvidenceSelection
from debate_core.integrations.crossref_doi import CROSSREF_WORKS_URL, InMemoryDoiCache, crossref_doi_client
from debate_core.testing.fakes.card_edit_log import InMemoryCardEditLog
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import (
    InMemoryArticleRepository,
    InMemoryCardRepository,
    InMemorySnapshotStore,
)

CITATION_FIXTURES: Final = Path(__file__).parent
FIXTURES: Final = CITATION_FIXTURES.parent
CASES: Final = (
    "news-article",
    "think-tank-report",
    "government-press-release",
    "journal-article-landing",
    "open-access-pdf",
    "user-supplied",
    "organization-report",
)
RETRIEVED_AT: Final = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
JOURNAL_DOI: Final = "10.5555/jscs.2026.0012"
EXTRACTED_TEXT: Final = (
    "Funders have committed large sums to reviving extinct species. The comparison with protecting "
    "species that are still alive is rarely made before a revival program is funded."
)
"""The snapshot's text for every case. The cite is read from the raw bytes, never from this."""


def load_case(name: str) -> dict[str, Any]:
    """`<name>.expected.json`, parsed."""
    case: dict[str, Any] = json.loads(
        (CITATION_FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8")
    )
    return case


class CrossrefAnswers:
    """Crossref's side, served by respx; every request kept; a transport failure raised by hand.

    The failure is raised in this transport rather than as a respx side effect, which would chain
    an error quoting the matched route.
    """

    def __init__(self) -> None:
        self.router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
        self.requests: list[httpx.Request] = []
        self.failure: type[httpx.TransportError] | None = None
        self._routes: dict[str, respx.Route] = {}

    def serve(self, doi: str, answer_file: str) -> None:
        """Answer `doi` with the Crossref answer in `crossref/<answer_file>`."""
        self.answer(doi, 200, (CITATION_FIXTURES / "crossref" / answer_file).read_bytes())

    def answer(self, doi: str, status: int, content: bytes = b"{}") -> None:
        """Answer `doi` with `status` and `content` from now on, replacing any earlier answer."""
        route = self._routes.get(doi)
        if route is None:
            route = self._routes[doi] = self.router.get(url__startswith=CROSSREF_WORKS_URL + doi)
        route.return_value = httpx.Response(status, content=content)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure("failed", request=request)
        return await self.router.async_handler(request)


class CitationWorld:
    """The stores, the snapshot service, the verifier, the card edit service and the citation service."""

    def __init__(self, *, with_crossref: bool = True) -> None:
        self.blobs = InMemorySnapshotStore()
        self.articles = InMemoryArticleRepository()
        self.clock = FixedClock(RETRIEVED_AT)
        self.snapshots = SnapshotService(
            blobs=self.blobs, clock=self.clock, id_generator=SequentialIdGenerator("SNAP")
        )
        self.cards = InMemoryCardRepository()
        self.edit_log = InMemoryCardEditLog()
        self.verifier = EvidenceVerifier(articles=self.articles, snapshots=self.snapshots, clock=self.clock)
        self.edits = CardEditService(
            cards=self.cards,
            articles=self.articles,
            snapshots=self.snapshots,
            verifier=self.verifier,
            edit_log=self.edit_log,
            clock=self.clock,
        )
        self.crossref = CrossrefAnswers()
        self.crossref.serve(JOURNAL_DOI, "works-10.5555-jscs.2026.0012.json")
        self.doi_cache = InMemoryDoiCache()
        self.doi_client = crossref_doi_client(
            HttpSettings(),
            ProviderSettings(),
            version="0.0.0-test",
            cache=self.doi_cache,
            transport=httpx.MockTransport(self.crossref.handle),
        )
        self.service = CitationService(
            articles=self.articles,
            snapshots=self.snapshots,
            edit_log=self.edit_log,
            doi_metadata=self.doi_client if with_crossref else None,
        )
        self._article_ids = SequentialIdGenerator("ART")
        self._card_ids = SequentialIdGenerator("CARD")

    async def add_case(self, name: str) -> tuple[Article, LoadedSnapshot]:
        """Store case `name` as ArticleService would have: its article, then its snapshot."""
        case = load_case(name)
        raw = (
            (FIXTURES / case["page"]).read_bytes()
            if case.get("page") is not None
            else str(case["user_text"]).encode("utf-8")
        )
        stated = case["article"]
        article = await self.articles.save(
            Article(
                article_id=self._article_ids.new_id(),
                canonical_url=stated["canonical_url"],
                title=stated["title"],
                access_status=AccessStatus.ACCESSIBLE,
                identifiers=ArticleIdentifiers(doi=stated["doi"]),
            )
        )
        return article, await self.add_snapshot(
            article, raw, case["retrieved_url"], ProvenanceMode(case["provenance_mode"]), case["content_type"]
        )

    async def add_snapshot(
        self,
        article: Article,
        raw: bytes,
        retrieved_url: str,
        provenance_mode: ProvenanceMode = ProvenanceMode.PUBLISHER_RETRIEVED,
        content_type: str | None = "text/html; charset=utf-8",
    ) -> LoadedSnapshot:
        snapshot = await self.snapshots.create(
            article_id=article.article_id,
            raw_bytes=raw,
            extracted_text=EXTRACTED_TEXT,
            canonical_url=retrieved_url,
            retrieved_at=RETRIEVED_AT,
            extractor_version="fixture-extractor/1",
            provenance_mode=provenance_mode,
            access_status=AccessStatus.ACCESSIBLE,
            content_type=content_type,
        )
        await self.articles.save_snapshot(snapshot)
        return await self.snapshots.load(snapshot)

    async def stored_card(self, source: LoadedSnapshot, citation: Citation) -> Card:
        """A card cut from the first sentence of `source` with `citation`, verified and stored."""
        evidence = EvidenceExtractor().extract(
            source.snapshot, source.normalized, EvidenceSelection.of_offsets((0, 62))
        )
        markup = CardMarkup(evidence, (EvidenceMarkupSpan.underline(0, 62, SpanPurpose.CLAIM),))
        card = card_from_markup(markup, card_id=self._card_ids.new_id(), citation=citation)
        recorded, _ = await self.verifier.verify_and_record(card)
        return await self.cards.create(recorded)

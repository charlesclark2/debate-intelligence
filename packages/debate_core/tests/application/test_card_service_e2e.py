"""From a URL to a stored card, offline: ArticleService over a replayed cassette, then CardService.cut_card.

The news article is fetched as production fetches it: the real HTTP fetcher (robots.txt, redirects,
limits) behind t06's replay transport, which serves only the cassette and never the network, and the
real extractors. Everything is stored in this machine's local adapters, SQLite and the filesystem, in
a temporary data directory. The card is cut by the production selector and guard over the fake
router's hand-written answers, cited by t01's CitationService, verified and saved. Then the store is
opened again, as a later command would open it, and a fresh verifier reproduces the card's status.

Task v1-e06-t02, node offline-e2e. Expected evidence is written by hand from t04's paragraphs
(`test_card_service.py`); no value here was saved from a run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
from pydantic import JsonValue
from tests.fixtures.card.card_world import MODEL_OUTPUTS, REPOSITORY_ROOT, CountingRouter, news_request
from tests.fixtures.http.cassettes import ReplayTransport, load_cassette

from debate_core.application.article_service import ArticleService
from debate_core.application.card_selection import CardSelector
from debate_core.application.card_service import CardService
from debate_core.application.card_types import CardFailureReason, CutResult
from debate_core.application.citation_service import CitationService
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.settings import ArticleSettings, HttpSettings
from debate_core.application.snapshot_service import SnapshotService
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain import AccessStatus, VerificationStatus
from debate_core.evidence.verification_types import ReasonCode
from debate_core.integrations.html_extractor import TrafilaturaExtractor
from debate_core.integrations.http_fetcher import HttpArticleFetcher
from debate_core.integrations.local import FsSnapshotStore, SqliteArticleRepository, SqliteDatabase
from debate_core.integrations.local.sqlite_repos import SqliteCardRepository
from debate_core.integrations.models.fake_router import FakeModelRouter
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.pdf_extractor import PdfExtractor
from debate_core.retrieval.extraction import ContentTypeDispatcher
from debate_core.testing.fakes.card_edit_log import InMemoryCardEditLog
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.model_router import ScriptedModelRouter

pytestmark = pytest.mark.anyio

NEWS_URL: Final = (
    "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter"
)
NEWS_PARAGRAPHS: Final[list[str]] = json.loads(
    (REPOSITORY_ROOT / "tests" / "fixtures" / "extraction" / "news-article.expected.json").read_text(
        encoding="utf-8"
    )
)["paragraphs"]
EVIDENCE: Final = (
    "The delay follows two years of failed attempts to grow edited elephant embryos to term in surrogate "
    "animals.Conservation biologists who have criticized the project said the timeline was never "
    "realistic. “Every year this slips, the money raised for it is money that did not go to elephants "
    "that are alive now,” said Priya Ramaswamy, who studies elephant populations and was not involved "
    "in the work."
)
"""P2's first sentence and all of P3, joined with nothing, written out by hand from t04's paragraphs."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class LocalStore:
    """The adapters a command on this machine opens over one data directory."""

    database: SqliteDatabase
    articles: SqliteArticleRepository
    cards: SqliteCardRepository
    snapshots: SnapshotService
    verifier: EvidenceVerifier


def open_store(data_dir: Path, clock: FixedClock) -> LocalStore:
    database = SqliteDatabase.open(data_dir)
    articles = SqliteArticleRepository(database)
    snapshots = SnapshotService(
        blobs=FsSnapshotStore(data_dir), clock=clock, id_generator=SequentialIdGenerator("SNAP")
    )
    return LocalStore(
        database=database,
        articles=articles,
        cards=SqliteCardRepository(database),
        snapshots=snapshots,
        verifier=EvidenceVerifier(articles=articles, snapshots=snapshots, clock=clock),
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


async def retrieve_news(store: LocalStore, clock: FixedClock) -> str:
    """Fetch the news cassette through ArticleService into `store`; the snapshot id."""
    limits = ArticleSettings()
    transport = ReplayTransport([load_cassette("news-article")])
    fetcher = HttpArticleFetcher(
        HttpSettings(per_host_interval_seconds=0), version="0.0.0-test", clock=clock, transport=transport
    )
    service = ArticleService(
        articles=store.articles,
        snapshots=store.snapshots,
        fetcher=fetcher,
        extractor=ContentTypeDispatcher(
            html=TrafilaturaExtractor(
                minimum_characters=limits.html_fallback_minimum_characters, max_bytes=limits.html_max_bytes
            ),
            pdf=PdfExtractor(
                max_bytes=limits.pdf_max_bytes,
                max_pages=limits.pdf_max_pages,
                max_stream_bytes=limits.pdf_max_stream_bytes,
            ),
        ),
        clock=clock,
        id_generator=SequentialIdGenerator("ART"),
        settings=limits,
        max_user_text_bytes=100_000,
    )
    try:
        outcome = await service.retrieve(NEWS_URL)
    finally:
        await fetcher.aclose()
    assert transport.unrecorded == [], "a request no cassette recorded"
    assert outcome.access_status is AccessStatus.ACCESSIBLE and outcome.snapshot is not None
    return outcome.snapshot.snapshot_id


async def cut_news(
    store: LocalStore, clock: FixedClock, router: ModelRouter
) -> tuple[CutResult, CountingRouter]:
    snapshot_id = await retrieve_news(store, clock)
    counting = CountingRouter(router)
    citations = CitationService(
        articles=store.articles, snapshots=store.snapshots, edit_log=InMemoryCardEditLog()
    )
    service = CardService(
        articles=store.articles,
        snapshots=store.snapshots,
        selector=CardSelector(
            StructuredOutputGuard(counting, PromptRegistry.load(REPOSITORY_ROOT / "prompts"))
        ),
        citations=citations,
        verifier=store.verifier,
        cards=store.cards,
        clock=clock,
        id_generator=SequentialIdGenerator("CVT"),
    )
    return await service.cut_card(news_request(snapshot_id)), counting


async def test_a_retrieved_article_is_cut_into_a_verified_card_that_verifies_again_from_the_reopened_store(
    data_dir: Path, clock: FixedClock
) -> None:
    store = open_store(data_dir, clock)
    try:
        result, router = await cut_news(store, clock, FakeModelRouter(MODEL_OUTPUTS))
        snapshot = await store.articles.get_snapshot(result.card.snapshot_id or "")
        loaded = await store.snapshots.load(snapshot)
    finally:
        store.database.close()

    assert loaded.normalized.text == "\n\n".join(NEWS_PARAGRAPHS)
    assert (result.is_verified, result.reasons) == (True, ())
    assert result.card.evidence_text == EVIDENCE
    assert (result.card.snapshot_id, result.card.normalized_text_hash) == (
        snapshot.snapshot_id,
        snapshot.normalized_text_hash,
    )
    assert [prompt.prompt_id for prompt in router.calls] == ["card.select", "card.markup"]

    reopened = open_store(data_dir, clock)
    try:
        stored = await reopened.cards.get(result.card.card_id)
        again = await reopened.verifier.verify(stored)
    finally:
        reopened.database.close()

    assert stored == result.card
    assert (stored.verification_status, again.status) == (
        VerificationStatus.VERIFIED,
        VerificationStatus.VERIFIED,
    )
    assert again.reasons == ()


REFUSED_MARKUP: Final[dict[str, JsonValue]] = {
    "spans": [
        {"paragraph": 3, "start_offset": 119, "end_offset": 199, "style": "highlight", "purpose": "impact"}
    ],
    "rationale": "The highlight carries the lost funding.",
}


async def test_a_card_whose_markup_was_refused_stays_unverified_for_the_same_reasons_in_the_reopened_store(
    data_dir: Path, clock: FixedClock
) -> None:
    selection: dict[str, JsonValue] = json.loads(
        next((MODEL_OUTPUTS / "card.select").glob("8ad9c020*.json")).read_text(encoding="utf-8")
    )["output"]
    store = open_store(data_dir, clock)
    try:
        result, _ = await cut_news(
            store, clock, ScriptedModelRouter([selection, REFUSED_MARKUP, REFUSED_MARKUP])
        )
    finally:
        store.database.close()

    reopened = open_store(data_dir, clock)
    try:
        stored = await reopened.cards.get(result.card.card_id)
        again = await reopened.verifier.verify(stored)
    finally:
        reopened.database.close()

    assert result.reason_codes == (
        CardFailureReason.MODEL_OUTPUT_INVALID,
        CardFailureReason.EVIDENCE_UNVERIFIED,
    )
    assert stored.evidence_text == EVIDENCE
    assert (stored.verification_status, again.status) == (
        VerificationStatus.UNVERIFIED,
        VerificationStatus.UNVERIFIED,
    )
    assert again.reason_codes == result.verification.reason_codes == (ReasonCode.CARD_INCOMPLETE,)

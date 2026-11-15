"""A snapshot's canonical URL is its article's, and the URL it was read from is kept beside it (v1-e04-t10).

Before this task a publisher snapshot's `canonical_url` held the URL that answered the fetch, tracking
parameters and all, so `search --auto-cut`'s manifest named the news page as
`…/mammoth-revival-years-away?utm_source=newsletter` while its article named it without them. Now
`canonical_url` is the article's canonical URL, decided by the article's own rules (v1-e04-t01's
canonical form, then the page's rel=canonical), and `retrieved_url` holds the URL that answered.

The rule that decides which query parameters go is v1-e04-t01's
(:mod:`debate_core.retrieval.canonical_url`, content rule 7): "Parameters on the tracking deny list
are removed (`query_parameters`). A parameter on no list is kept."

Every page here is a recorded one, served by the real HTTP fetcher from t06's replay transport (which
never reaches the network) and read by the real extractors, into this machine's SQLite store in a
temporary directory. A page is sometimes served under another URL than its cassette's, to carry the
parameters a test needs; its bytes are the committed sample's. Every expected URL is written by hand
from the URL fetched and the page's rel=canonical, never saved from a run.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import pytest
from tests.fixtures.http.cassettes import FIXTURES_ROOT, Cassette, ReplayTransport, load_cassette

from debate_core.application.article_service import ArticleService, RetrievalOutcome
from debate_core.application.citation_service import CitationService
from debate_core.application.settings import ArticleSettings, HttpSettings
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode, SourceSnapshot
from debate_core.evidence.manifest import SnapshotReference
from debate_core.integrations.html_extractor import TrafilaturaExtractor
from debate_core.integrations.http_fetcher import HttpArticleFetcher
from debate_core.integrations.local import FsSnapshotStore, SqliteArticleRepository, SqliteDatabase
from debate_core.integrations.local.sqlite_db import DATABASE_FILENAME
from debate_core.integrations.pdf_extractor import PdfExtractor
from debate_core.retrieval.extraction import ContentTypeDispatcher
from debate_core.testing.fakes.card_edit_log import InMemoryCardEditLog
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator

pytestmark = pytest.mark.anyio

NEWS_CANONICAL_URL: Final = "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away"
"""The news page's canonical URL: its path, as its relative rel=canonical states, with no query."""

NEWSLETTER_LINK: Final = f"{NEWS_CANONICAL_URL}?utm_source=newsletter"
"""The committed news cassette's URL, the link `search --auto-cut` followed in v1-e09-t05."""

MANY_TRACKERS_LINK: Final = (
    f"{NEWS_CANONICAL_URL}?utm_source=newsletter&utm_medium=email&utm_campaign=mammoth-week"
    "&fbclid=IwAR0abc&gclid=Cj0KCQjw&mc_eid=4f2a9c"
)
"""Three `utm_` parameters and three other deny-list names: Facebook's, Google Ads' and Mailchimp's."""

SHORT_LINK: Final = "https://www.dailymeridian.example/s/mammoth?utm_source=newsletter"
"""Another path on the same site, which serves the same page; its rel=canonical names the story's path."""

REPORT_PDF: Final = "https://www.fosw.example.gov/files/2026/habitat-grants-annual-report.pdf"
"""The government PDF cassette's URL. A PDF states no rel=canonical, so the URL's canonical form stands."""

REPORT_PDF_WITH_QUERY: Final = f"{REPORT_PDF}?utm_source=newsletter&id=7&edition=summary&fbclid=IwAR0abc"
"""`id` is on the allow list, `edition` on no list: both select content and are kept. The others go."""

REPORT_PDF_CANONICAL_URL: Final = f"{REPORT_PDF}?edition=summary&id=7"
"""What is kept, sorted by name (content rule 9)."""

NEWS_PARAGRAPHS: Final[list[str]] = json.loads(
    (FIXTURES_ROOT / "extraction" / "news-article.expected.json").read_text(encoding="utf-8")
)["paragraphs"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class LocalStore:
    data_dir: Path
    database: SqliteDatabase
    articles: SqliteArticleRepository
    snapshots: SnapshotService
    clock: FixedClock

    def close(self) -> None:
        self.database.close()


def open_store(data_dir: Path, clock: FixedClock) -> LocalStore:
    database = SqliteDatabase.open(data_dir)
    return LocalStore(
        data_dir=data_dir,
        database=database,
        articles=SqliteArticleRepository(database),
        snapshots=SnapshotService(
            blobs=FsSnapshotStore(data_dir), clock=clock, id_generator=SequentialIdGenerator("SNAP")
        ),
        clock=clock,
    )


@pytest.fixture
def store(tmp_path: Path) -> Iterator[LocalStore]:
    opened = open_store(tmp_path / "data", FixedClock())
    yield opened
    opened.close()


def served_at(cassette_name: str, url: str) -> Cassette:
    """The committed cassette `cassette_name`, its page served at `url`: the same bytes, another link."""
    cassette = load_cassette(cassette_name)
    page = cassette.page
    assert page is not None
    others = tuple(interaction for interaction in cassette.interactions if interaction is not page)
    return replace(cassette, url=url, interactions=(*others, replace(page, url=url)))


def service_over(store: LocalStore, fetcher: HttpArticleFetcher) -> ArticleService:
    limits = ArticleSettings()
    return ArticleService(
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
        clock=store.clock,
        id_generator=SequentialIdGenerator("ART"),
        settings=limits,
        max_user_text_bytes=100_000,
    )


async def retrieve(store: LocalStore, cassette: Cassette) -> RetrievalOutcome:
    """Fetch `cassette`'s URL through ArticleService into `store`, offline."""
    transport = ReplayTransport([cassette])
    fetcher = HttpArticleFetcher(
        HttpSettings(per_host_interval_seconds=0),
        version="0.0.0-test",
        clock=store.clock,
        transport=transport,
    )
    try:
        outcome = await service_over(store, fetcher).retrieve(cassette.url)
    finally:
        await fetcher.aclose()
    assert transport.unrecorded == [], "a request no cassette recorded"
    assert outcome.access_status is AccessStatus.ACCESSIBLE and outcome.snapshot is not None
    return outcome


def stored_row(store: LocalStore, snapshot_id: str) -> tuple[str, str, str | None]:
    """The `source_snapshots` row as SQLite holds it: its column, and the two URLs in its document."""
    connection = sqlite3.connect(f"file:{store.data_dir / DATABASE_FILENAME}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT canonical_url, json_extract(document, '$.canonical_url'), "
            "json_extract(document, '$.retrieved_url') FROM source_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row


async def stored(store: LocalStore, outcome: RetrievalOutcome) -> tuple[SourceSnapshot, str]:
    """The outcome's snapshot as read back from SQLite, and its article's canonical URL."""
    assert outcome.snapshot is not None
    snapshot = await store.articles.get_snapshot(outcome.snapshot.snapshot_id)
    article = await store.articles.get(snapshot.article_id)
    return snapshot, article.canonical_url


# --------------------------------------------------------------------------------------------
# Tracking parameters
# --------------------------------------------------------------------------------------------


async def test_the_newsletter_link_gives_a_snapshot_canonical_url_without_utm_source(
    store: LocalStore,
) -> None:
    snapshot, article_url = await stored(store, await retrieve(store, load_cassette("news-article")))

    assert (article_url, snapshot.canonical_url) == (NEWS_CANONICAL_URL, NEWS_CANONICAL_URL)
    assert snapshot.retrieved_url == NEWSLETTER_LINK
    assert stored_row(store, snapshot.snapshot_id) == (
        NEWS_CANONICAL_URL,
        NEWS_CANONICAL_URL,
        NEWSLETTER_LINK,
    )


async def test_utm_and_other_tracking_parameters_stay_out_of_the_snapshot_canonical_url(
    store: LocalStore,
) -> None:
    snapshot, article_url = await stored(
        store, await retrieve(store, served_at("news-article", MANY_TRACKERS_LINK))
    )

    assert (article_url, snapshot.canonical_url) == (NEWS_CANONICAL_URL, NEWS_CANONICAL_URL)
    assert snapshot.retrieved_url == MANY_TRACKERS_LINK


async def test_the_manifest_reference_names_the_snapshot_by_its_canonical_url(store: LocalStore) -> None:
    """What `search --auto-cut`'s `<name>.manifest.json` and `cut --json` show a coach for the snapshot."""
    snapshot, _ = await stored(store, await retrieve(store, served_at("news-article", MANY_TRACKERS_LINK)))

    assert SnapshotReference.of(snapshot).canonical_url == NEWS_CANONICAL_URL


async def test_a_snapshot_canonical_url_is_its_article_rel_canonical_not_the_link_that_was_followed(
    store: LocalStore,
) -> None:
    snapshot, article_url = await stored(store, await retrieve(store, served_at("news-article", SHORT_LINK)))

    assert (article_url, snapshot.canonical_url) == (NEWS_CANONICAL_URL, NEWS_CANONICAL_URL)
    assert snapshot.retrieved_url == SHORT_LINK


# --------------------------------------------------------------------------------------------
# A query that selects content
# --------------------------------------------------------------------------------------------


async def test_a_snapshot_canonical_url_keeps_the_query_parameters_that_select_content(
    store: LocalStore,
) -> None:
    snapshot, article_url = await stored(
        store, await retrieve(store, served_at("government-pdf", REPORT_PDF_WITH_QUERY))
    )

    assert (article_url, snapshot.canonical_url) == (REPORT_PDF_CANONICAL_URL, REPORT_PDF_CANONICAL_URL)
    assert snapshot.retrieved_url == REPORT_PDF_WITH_QUERY
    assert stored_row(store, snapshot.snapshot_id) == (
        REPORT_PDF_CANONICAL_URL,
        REPORT_PDF_CANONICAL_URL,
        REPORT_PDF_WITH_QUERY,
    )


# --------------------------------------------------------------------------------------------
# Text a user supplied, and a snapshot stored before this task
# --------------------------------------------------------------------------------------------


async def test_a_user_supplied_snapshot_canonical_url_is_its_article_and_it_records_no_retrieved_url(
    store: LocalStore,
) -> None:
    transport = ReplayTransport([])
    fetcher = HttpArticleFetcher(
        HttpSettings(per_host_interval_seconds=0),
        version="0.0.0-test",
        clock=store.clock,
        transport=transport,
    )
    try:
        outcome = await service_over(store, fetcher).ingest_user_text(
            source_url=MANY_TRACKERS_LINK, text="\n\n".join(NEWS_PARAGRAPHS), attested=True
        )
    finally:
        await fetcher.aclose()
    assert transport.requested == []
    snapshot, article_url = await stored(store, outcome)

    assert (article_url, snapshot.canonical_url) == (NEWS_CANONICAL_URL, NEWS_CANONICAL_URL)
    assert snapshot.retrieved_url is None
    assert stored_row(store, snapshot.snapshot_id) == (NEWS_CANONICAL_URL, NEWS_CANONICAL_URL, None)


async def test_a_snapshot_stored_with_the_retrieved_url_as_its_canonical_url_reads_and_cites_as_before(
    store: LocalStore,
) -> None:
    """A row written before v1-e04-t10: no `retrieved_url`, and `canonical_url` the URL that answered.

    It is never rewritten: snapshots are immutable, and the manifests already written name it so. It
    reads back as stored, its manifest reference is what those manifests say, and its cite is still
    harvested from the page as read at that URL.
    """
    article = (await retrieve(store, load_cassette("news-article"))).article
    page = load_cassette("news-article").page
    assert page is not None
    before = await store.articles.save_snapshot(
        await store.snapshots.create(
            article_id=article.article_id,
            raw_bytes=page.body,
            extracted_text="\n\n".join(NEWS_PARAGRAPHS),
            canonical_url=NEWSLETTER_LINK,
            retrieved_at=store.clock.now(),
            extractor_version="trafilatura/2.0.0",
            provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
            access_status=AccessStatus.ACCESSIBLE,
            content_type="text/html; charset=utf-8",
        )
    )
    assert stored_row(store, before.snapshot_id) == (NEWSLETTER_LINK, NEWSLETTER_LINK, None)

    read = await store.articles.get_snapshot(before.snapshot_id)
    assert read == before
    assert SnapshotReference.of(read).canonical_url == NEWSLETTER_LINK

    citations = CitationService(
        articles=store.articles, snapshots=store.snapshots, edit_log=InMemoryCardEditLog()
    )
    cite = (await citations.resolve(article, await store.snapshots.load(read))).citation

    # The page's relative rel=canonical, resolved against the URL the bytes were read from.
    assert (cite.canonical_url.value, cite.canonical_url.raw) == (
        NEWS_CANONICAL_URL,
        "/science/2026/09/14/mammoth-revival-years-away",
    )


async def test_a_page_stating_no_canonical_url_is_cited_from_the_url_it_was_read_from(
    store: LocalStore,
) -> None:
    """The cite's URL of last resort is the retrieved URL, canonicalized; its `raw` is that URL as read."""
    outcome = await retrieve(store, served_at("government-pdf", REPORT_PDF_WITH_QUERY))
    snapshot, _ = await stored(store, outcome)
    citations = CitationService(
        articles=store.articles, snapshots=store.snapshots, edit_log=InMemoryCardEditLog()
    )

    cite = (await citations.resolve(outcome.article, await store.snapshots.load(snapshot))).citation

    assert (cite.canonical_url.value, cite.canonical_url.raw) == (
        REPORT_PDF_CANONICAL_URL,
        REPORT_PDF_WITH_QUERY,
    )

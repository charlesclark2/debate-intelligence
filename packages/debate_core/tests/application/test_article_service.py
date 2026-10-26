"""ArticleService (`v1-e04-t05-article-service`): retrieval, refusals, dedupe and user-supplied text.

Tests are named so the plan's criteria select them: `-k accessible` runs the readable-page pipeline
(ac1, ac6), `-k failure` the non-ACCESSIBLE outcomes (ac2), `-k dedupe` the dedupe and re-fetch
policy (ac3), and `user_text` the USER_SUPPLIED path (ac4); `log_event` is ac5.

Every page is invented and written out in this file, and every expected value is written by hand
from it: the raw hash is SHA-256 of the literal body, the normalized hash SHA-256 of the paragraphs
as typed here (ASCII text the normalizer leaves alone), and each reason the sentence the access
classifier's table gives for that case (`docs/process/working-agreements.md` §6). Nothing reaches
the network: the fetcher and extractor are the in-memory fakes, the extractor wrapped below so a
test can give it a page's metadata hints or a refusal.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import logging
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any, cast

import pytest

from debate_core.application import article_service as article_service_module
from debate_core.application.article_service import (
    USER_TEXT_CONTENT_TYPE,
    USER_TEXT_EXTRACTOR_VERSION,
    ArticleService,
    InvalidSourceUrl,
    UserTextNotAttested,
    UserTextRejected,
    access_thresholds,
)
from debate_core.application.settings import ArticleSettings
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode
from debate_core.integrations import html_extractor, pdf_extractor
from debate_core.retrieval import RelCanonicalRule
from debate_core.retrieval.access import AccessThresholds
from debate_core.retrieval.extraction import (
    EncryptedDocument,
    ExtractedContent,
    ExtractionError,
    UnverifiedMetadataHints,
)
from debate_core.retrieval.fetch_types import (
    FetchResult,
    RobotsDisallowed,
    RobotsRefusalReason,
    Timeout,
    TimeoutPhase,
)
from debate_core.testing.fakes.clock_and_ids import FAKE_EPOCH, FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemoryArticleRepository, InMemorySnapshotStore
from debate_core.testing.fakes.providers import FakeArticleFetcher, FakeContentExtractor


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion; see the note in `test_fakes.py`."""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("an in-memory fake suspended; fakes must not perform real I/O")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------
# The pages
# --------------------------------------------------------------------------------------------

ARTICLE_URL = "https://www.example.org/energy/grid-storage"

PARAGRAPHS = (
    "Grid-scale batteries smoothed the evening peak in three of the four regions studied, cutting "
    "the hours in which gas peaker plants ran by roughly a third over the two summers measured.",
    "The authors caution that the fourth region, which leans on imported hydropower, saw no such "
    "change, and argue that storage pays off only where solar output and demand peaks are offset.",
    "Operators interviewed for the report said interconnection queues, not battery prices, were "
    "now the binding constraint, with some projects waiting more than four years for approval.",
)
TEXT = "\n\n".join(PARAGRAPHS)
BODY = TEXT.encode("utf-8")

CHANGED_PARAGRAPHS = (*PARAGRAPHS, "A correction was appended: the third region's figure was revised down.")
CHANGED_BODY = "\n\n".join(CHANGED_PARAGRAPHS).encode("utf-8")
CHANGED_TEXT_HASH = sha256("\n\n".join(CHANGED_PARAGRAPHS).encode("utf-8"))

SENTINEL = "QUOKKA-SENTINEL-NEVER-LOGGED"
"""A phrase in every page and every supplied text whose presence in a log event is a leak."""

SENTINEL_PARAGRAPHS = (*PARAGRAPHS, f"The sentinel {SENTINEL} closes this page.")
SENTINEL_BODY = "\n\n".join(SENTINEL_PARAGRAPHS).encode("utf-8")

METERED_PAGE = (
    '<html><head><meta name="article:content_tier" content="metered"><title>Grid storage</title></head>'
    f"<body><p>{PARAGRAPHS[0]}</p><p>{PARAGRAPHS[1]}</p><p>{PARAGRAPHS[2]}</p><p>{SENTINEL}</p></body></html>"
).encode()
"""The whole text, served, on a page that declares itself metered: PAYWALLED all the same."""

CHALLENGE_PAGE = (
    b"<html><head><title>Just a moment...</title></head><body>Checking your browser.</body></html>"
)
PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BODY = b"%PDF-1.7\n1 0 obj\n<< /Encrypt 2 0 R >>\nendobj\n"
SHORT_BODY = b"A paragraph of forty-odd characters only."


class ScriptedExtractor:
    """The fake extractor, plus per-URL metadata hints and refusals a test scripts."""

    def __init__(self) -> None:
        self._inner = FakeContentExtractor()
        self.hints: dict[str, UnverifiedMetadataHints] = {}
        self.refusals: dict[str, ExtractionError] = {}
        self.extracted: list[str] = []

    @property
    def name(self) -> str:
        return self._inner.name

    def extract(self, fetched: FetchResult) -> ExtractedContent:
        self.extracted.append(fetched.final_url)
        refusal = self.refusals.get(fetched.final_url)
        if refusal is not None:
            raise refusal
        content = self._inner.extract(fetched)
        hints = self.hints.get(fetched.final_url)
        return content if hints is None else content.evolve(metadata_hints=hints)


class SlowFetcher(FakeArticleFetcher):
    """The fake fetcher, taking 250 ms of the shared clock per fetch, so elapsed time is known."""

    def __init__(self, clock: FixedClock) -> None:
        super().__init__(clock=clock)
        self._shared_clock = clock

    async def fetch(self, url: str) -> FetchResult:
        result = await super().fetch(url)
        self._shared_clock.advance(timedelta(milliseconds=250))
        return result


@dataclass
class World:
    service: ArticleService
    articles: InMemoryArticleRepository
    blobs: InMemorySnapshotStore
    fetcher: SlowFetcher
    extractor: ScriptedExtractor
    clock: FixedClock


def build_world(settings: ArticleSettings | None = None, *, max_user_text_bytes: int = 1_000_000) -> World:
    clock = FixedClock()
    ids = SequentialIdGenerator()
    articles = InMemoryArticleRepository()
    blobs = InMemorySnapshotStore()
    fetcher = SlowFetcher(clock)
    extractor = ScriptedExtractor()
    service = ArticleService(
        articles=articles,
        snapshots=SnapshotService(blobs=blobs, clock=clock, id_generator=ids),
        fetcher=fetcher,
        extractor=extractor,
        clock=clock,
        id_generator=ids,
        settings=settings if settings is not None else ArticleSettings(),
        max_user_text_bytes=max_user_text_bytes,
    )
    return World(service, articles, blobs, fetcher, extractor, clock)


# --------------------------------------------------------------------------------------------
# ac1 and ac6: the readable page
# --------------------------------------------------------------------------------------------


def test_an_accessible_page_becomes_an_article_and_a_snapshot_with_both_hashes() -> None:
    world = build_world()
    url = "https://journals.example.org/doi/10.1234/grid.5678?utm_source=newsletter"
    world.fetcher.add(url, BODY)

    outcome = run(world.service.retrieve(url))

    assert outcome.access_status is AccessStatus.ACCESSIBLE
    assert outcome.fetched
    assert not outcome.snapshot_reused
    assert outcome.reason == "The text was extracted: 88 words"
    assert outcome.rules_version == "paywall_rules.v1"
    article = outcome.article
    assert article.canonical_url == "https://journals.example.org/doi/10.1234/grid.5678"
    assert article.identifiers.doi == "10.1234/grid.5678"
    assert article.access_status is AccessStatus.ACCESSIBLE
    assert run(world.articles.find_by_canonical_url(article.canonical_url)) == article

    snapshot = outcome.snapshot
    assert snapshot is not None
    assert snapshot.article_id == article.article_id
    assert snapshot.sha256 == sha256(BODY)
    assert snapshot.normalized_text_hash == sha256(TEXT.encode("utf-8"))
    assert snapshot.extractor_version == "fake-extractor/fake-1.0.0"
    assert snapshot.normalizer_version == "evidence-normalizer-v1"
    assert snapshot.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED
    assert snapshot.access_status is AccessStatus.ACCESSIBLE
    assert snapshot.content_type == "text/html; charset=utf-8"
    assert snapshot.byte_size == len(BODY)
    assert snapshot.retrieved_at == FAKE_EPOCH
    assert run(world.articles.list_snapshots(article.article_id)) == (snapshot,)
    assert sha256(BODY) in world.blobs.stored_keys()


def test_an_accessible_amp_page_is_fetched_where_it_was_given_never_at_the_guessed_www_host() -> None:
    world = build_world()
    amp = "https://amp.example-news.co.uk/world/grid-storage"
    world.fetcher.add(amp, BODY)

    outcome = run(world.service.retrieve(amp))

    assert world.fetcher.requested_urls == [amp]
    assert outcome.access_status is AccessStatus.ACCESSIBLE
    assert outcome.fetch_url == amp
    # The canonicalizer's guess is the identity key, and only that.
    assert outcome.article.canonical_url == "https://www.example-news.co.uk/world/grid-storage"
    assert outcome.snapshot is not None
    assert outcome.snapshot.canonical_url == amp


def test_an_accessible_page_behind_a_link_wrapper_is_fetched_at_its_literal_destination() -> None:
    world = build_world()
    destination = "https://www.example.org/report?utm_source=newsletter&id=7"
    wrapped = (
        "https://www.google.com/url?sa=t&q=https%3A%2F%2Fwww.example.org%2Freport%3Futm_source"
        "%3Dnewsletter%26id%3D7&usg=AOvVaw"
    )
    world.fetcher.add(destination, BODY)

    outcome = run(world.service.retrieve(wrapped))

    assert world.fetcher.requested_urls == [destination]
    assert outcome.access_status is AccessStatus.ACCESSIBLE
    assert outcome.requested_url == wrapped
    assert outcome.article.canonical_url == "https://www.example.org/report?id=7"


def test_an_accessible_page_naming_the_site_root_as_canonical_keeps_its_own_url() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    world.extractor.hints[ARTICLE_URL] = UnverifiedMetadataHints(canonical_url="https://www.example.org/")

    outcome = run(world.service.retrieve(ARTICLE_URL))

    assert outcome.article.canonical_url == ARTICLE_URL
    assert outcome.rel_canonical is not None
    assert outcome.rel_canonical.rule is RelCanonicalRule.SITE_ROOT_REFUSED
    assert outcome.rel_canonical.declared_url == "https://www.example.org/"
    assert run(world.articles.find_by_canonical_url("https://www.example.org/")) is None


def test_an_accessible_root_page_naming_the_site_root_as_canonical_is_accepted() -> None:
    world = build_world()
    world.fetcher.add("https://example.org/", BODY)
    world.extractor.hints["https://example.org/"] = UnverifiedMetadataHints(
        canonical_url="https://www.example.org/"
    )

    outcome = run(world.service.retrieve("https://example.org/"))

    assert outcome.rel_canonical is not None
    assert outcome.rel_canonical.rule is RelCanonicalRule.SAME_SITE
    assert outcome.article.canonical_url == "https://www.example.org/"


def test_an_accessible_page_with_a_same_site_canonical_is_stored_under_it_and_both_urls_are_kept() -> None:
    world = build_world()
    asked = "https://www.example.org/s/8812?utm_campaign=share"
    landed = "https://www.example.org/energy/2026/10/grid-storage?amp_device=1"
    canonical = "https://www.example.org/energy/2026/10/grid-storage"
    world.fetcher.add(asked, BODY, final_url=landed)
    world.extractor.hints[landed] = UnverifiedMetadataHints(
        title="Grid storage, two summers on", canonical_url=canonical
    )

    outcome = run(world.service.retrieve(asked))

    assert outcome.rel_canonical is not None
    assert outcome.rel_canonical.rule is RelCanonicalRule.SAME_SITE
    assert outcome.canonical_url == canonical
    assert outcome.article.canonical_url == canonical
    assert outcome.article.title == "Grid storage, two summers on"
    assert outcome.fetch_url == asked
    assert outcome.final_url == landed
    assert outcome.snapshot is not None
    assert outcome.snapshot.canonical_url == landed


def test_an_accessible_page_with_a_cross_site_canonical_keeps_the_fetched_url() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    world.extractor.hints[ARTICLE_URL] = UnverifiedMetadataHints(
        canonical_url="https://syndication.example.net/energy/grid-storage"
    )

    outcome = run(world.service.retrieve(ARTICLE_URL))

    assert outcome.rel_canonical is not None
    assert outcome.rel_canonical.rule is RelCanonicalRule.CROSS_SITE_REFUSED
    assert outcome.article.canonical_url == ARTICLE_URL


def test_an_accessible_page_without_a_title_hint_is_titled_by_its_url() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    outcome = run(world.service.retrieve(ARTICLE_URL))
    assert outcome.article.title == ARTICLE_URL


def test_an_invalid_url_is_refused_before_anything_is_fetched() -> None:
    world = build_world()
    with pytest.raises(InvalidSourceUrl, match="not a source URL"):
        run(world.service.retrieve("ftp://files.example.org/report.pdf"))
    assert world.fetcher.requested_urls == []


def test_the_classifier_thresholds_come_from_settings() -> None:
    assert access_thresholds(ArticleSettings()) == AccessThresholds(
        minimum_characters=500, truncation_ratio=0.5
    )
    tuned = ArticleSettings(access_minimum_characters=40, access_truncation_ratio=0.25)
    assert access_thresholds(tuned) == AccessThresholds(minimum_characters=40, truncation_ratio=0.25)

    # A 41-character page is ERROR under the default minimum and ACCESSIBLE under 40.
    strict, lenient = build_world(), build_world(tuned)
    for world in (strict, lenient):
        world.fetcher.add(ARTICLE_URL, SHORT_BODY)
    assert run(strict.service.retrieve(ARTICLE_URL)).access_status is AccessStatus.ERROR
    assert run(lenient.service.retrieve(ARTICLE_URL)).access_status is AccessStatus.ACCESSIBLE


def test_the_articles_settings_defaults_are_the_classifiers_and_extractors_own() -> None:
    settings = ArticleSettings()
    assert access_thresholds(settings) == AccessThresholds()
    assert settings.html_fallback_minimum_characters == html_extractor.DEFAULT_MINIMUM_CHARACTERS == 250
    assert settings.html_max_bytes == html_extractor.DEFAULT_MAX_BYTES == 10 * 1024 * 1024
    assert settings.pdf_max_bytes == pdf_extractor.DEFAULT_MAX_BYTES == 50 * 1024 * 1024
    assert settings.pdf_max_pages == pdf_extractor.DEFAULT_MAX_PAGES == 500
    assert settings.pdf_max_stream_bytes == pdf_extractor.DEFAULT_MAX_STREAM_BYTES == 20_000_000
    assert settings.refetch_after == timedelta(days=7)


# --------------------------------------------------------------------------------------------
# ac2: every other status, with its reason and no snapshot
# --------------------------------------------------------------------------------------------

HOST_TIMEOUT = Timeout(
    url=ARTICLE_URL,
    message="www.example.org did not answer in time",
    phase=TimeoutPhase.TOTAL,
    limit_seconds=30,
)
ROBOTS = RobotsDisallowed(
    url=ARTICLE_URL,
    message="robots.txt on www.example.org refuses this URL (disallowed)",
    robots_url="https://www.example.org/robots.txt",
    reason=RobotsRefusalReason.DISALLOWED,
)


@dataclass(frozen=True)
class FailureCase:
    body: bytes = b""
    status_code: int | None = 200
    content_type: str | None = "text/html; charset=utf-8"
    error: Timeout | RobotsDisallowed | None = None
    access_status: AccessStatus = AccessStatus.UNKNOWN
    refusal: ExtractionError | None = None
    registered: bool = True


FAILURES: Mapping[str, tuple[FailureCase, AccessStatus, str]] = {
    "not-found": (
        FailureCase(registered=False),
        AccessStatus.NOT_FOUND,
        "The server has no document at this URL (404)",
    ),
    "payment-required": (
        FailureCase(body=b"<html>Subscribe</html>", status_code=402),
        AccessStatus.PAYWALLED,
        "The server requires payment (402)",
    ),
    "metered-page-with-the-whole-text": (
        FailureCase(body=METERED_PAGE),
        AccessStatus.PAYWALLED,
        "The page is behind a paywall: paywall marker content-tier-metered-meta (",
    ),
    "bot-challenge": (
        FailureCase(body=CHALLENGE_PAGE),
        AccessStatus.BLOCKED,
        "A bot challenge was served, with challenge marker cloudflare-interstitial-title (",
    ),
    "forbidden": (
        FailureCase(body=b"<html>No.</html>", status_code=403),
        AccessStatus.BLOCKED,
        "The server refused the request (403)",
    ),
    "robots-disallowed": (
        FailureCase(
            status_code=None, content_type=None, error=ROBOTS, access_status=AccessStatus.ROBOTS_DISALLOWED
        ),
        AccessStatus.ROBOTS_DISALLOWED,
        "robots.txt keeps the platform from this URL: robots.txt on www.example.org refuses this URL "
        "(disallowed)",
    ),
    "timeout": (
        FailureCase(status_code=None, content_type=None, error=HOST_TIMEOUT),
        AccessStatus.ERROR,
        "The fetch ran out of time: www.example.org did not answer in time",
    ),
    "server-error": (
        FailureCase(body=b"oops", status_code=500),
        AccessStatus.ERROR,
        "The server answered 500",
    ),
    "too-short-to-be-an-article": (
        FailureCase(body=SHORT_BODY),
        AccessStatus.ERROR,
        "Only 41 characters were extracted, under the 500-character minimum for an article",
    ),
    "image": (
        FailureCase(body=PNG_BODY, content_type="image/png"),
        AccessStatus.UNSUPPORTED_TYPE,
        "No extractor reads this document (declared 'image/png', bytes look like 'image/png')",
    ),
    "plain-text-the-extractor-read": (
        FailureCase(body=BODY, content_type="text/plain; charset=utf-8"),
        AccessStatus.UNSUPPORTED_TYPE,
        "No extractor reads this document (declared 'text/plain', bytes look like None)",
    ),
    "encrypted-pdf": (
        FailureCase(body=PDF_BODY, content_type="application/pdf", refusal=EncryptedDocument()),
        AccessStatus.UNSUPPORTED_TYPE,
        "The extractor refused the document: the PDF is encrypted; its text is not extracted",
    ),
}


def register_failure(world: World, case: FailureCase) -> None:
    if case.registered:
        world.fetcher.add(
            ARTICLE_URL,
            case.body,
            status_code=case.status_code,
            content_type=case.content_type,
            access_status=case.access_status,
            error=case.error,
        )
    if case.refusal is not None:
        world.extractor.refusals[ARTICLE_URL] = case.refusal


@pytest.mark.parametrize("name", list(FAILURES))
def test_failure_outcomes_carry_the_status_and_reason_and_store_no_snapshot(name: str) -> None:
    case, expected_status, expected_reason = FAILURES[name]
    world = build_world()
    register_failure(world, case)

    outcome = run(world.service.retrieve(ARTICLE_URL))

    assert outcome.access_status is expected_status
    assert outcome.reason.startswith(expected_reason)
    assert outcome.rules_version == "paywall_rules.v1"
    assert outcome.decision is not None
    assert outcome.decision.status is expected_status
    assert outcome.fetched
    assert outcome.snapshot is None
    assert outcome.rel_canonical is None
    # Nothing of the page was kept: no snapshot record and no blob.
    assert run(world.articles.list_snapshots(outcome.article.article_id)) == ()
    assert world.blobs.stored_keys() == frozenset()
    # The article records the outcome, under the URL's canonical form.
    assert outcome.article.access_status is expected_status
    assert outcome.article.canonical_url == ARTICLE_URL
    assert run(world.articles.find_by_canonical_url(ARTICLE_URL)) == outcome.article


def test_failure_after_a_readable_retrieval_records_the_status_and_keeps_the_old_snapshot() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    first = run(world.service.retrieve(ARTICLE_URL))
    world.fetcher.add(ARTICLE_URL, b"<html>Gone</html>", status_code=410)

    second = run(world.service.retrieve(ARTICLE_URL, refresh=True))

    assert second.access_status is AccessStatus.NOT_FOUND
    assert second.snapshot is None
    assert second.article.article_id == first.article.article_id
    assert second.article.access_status is AccessStatus.NOT_FOUND
    assert first.snapshot is not None
    assert run(world.articles.list_snapshots(first.article.article_id)) == (first.snapshot,)
    # Its last retrieval was not readable, so the stored snapshot does not answer the next call.
    run(world.service.retrieve(ARTICLE_URL))
    assert world.fetcher.requested_urls == [ARTICLE_URL] * 3


def test_failure_outcome_cannot_carry_a_publisher_snapshot() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    readable = run(world.service.retrieve(ARTICLE_URL))
    with pytest.raises(ValueError, match="a PAYWALLED outcome cannot carry a publisher snapshot"):
        replace(readable, access_status=AccessStatus.PAYWALLED)


def test_failure_is_not_extracted_unless_the_response_was_a_2xx() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, b"<html>No.</html>", status_code=403)
    run(world.service.retrieve(ARTICLE_URL))
    assert world.extractor.extracted == []


# --------------------------------------------------------------------------------------------
# ac3: dedupe and the re-fetch policy
# --------------------------------------------------------------------------------------------


def test_dedupe_two_tracking_variants_are_one_article() -> None:
    world = build_world()
    first_link = f"{ARTICLE_URL}?utm_source=newsletter&utm_medium=email"
    second_link = f"{ARTICLE_URL}?fbclid=IwAR0abc"
    world.fetcher.add(first_link, BODY)
    world.fetcher.add(second_link, BODY)

    first = run(world.service.retrieve(first_link))
    second = run(world.service.retrieve(second_link))
    refreshed = run(world.service.retrieve(second_link, refresh=True))

    assert first.article.canonical_url == ARTICLE_URL
    assert second.article.article_id == first.article.article_id
    assert refreshed.article.article_id == first.article.article_id
    # Within the re-fetch age the second link was not fetched; refreshed, it reused the snapshot.
    assert world.fetcher.requested_urls == [first_link, second_link]
    assert first.snapshot is not None
    assert second.snapshot == first.snapshot
    assert refreshed.snapshot == first.snapshot
    assert refreshed.snapshot_reused
    assert run(world.articles.list_snapshots(first.article.article_id)) == (first.snapshot,)


def test_dedupe_within_the_refetch_age_makes_no_fetch_call() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    first = run(world.service.retrieve(ARTICLE_URL))
    world.clock.advance(timedelta(hours=167, minutes=59))

    again = run(world.service.retrieve(ARTICLE_URL))

    assert world.fetcher.requested_urls == [ARTICLE_URL]
    assert not again.fetched
    assert again.snapshot == first.snapshot
    assert again.snapshot_reused
    assert again.access_status is AccessStatus.ACCESSIBLE
    assert again.decision is None
    assert again.rules_version is None
    assert (
        again.reason
        == "Last read 168.0 hours ago, within the 168-hour re-fetch age; the stored snapshot is the answer"
    )


def test_dedupe_after_the_refetch_age_fetches_and_reuses_the_snapshot_when_the_text_is_unchanged() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    first = run(world.service.retrieve(ARTICLE_URL))
    world.clock.advance(timedelta(hours=168))
    # Different bytes, the same text: the page's blank lines changed, the paragraphs did not.
    reflowed = BODY.replace(b"\n\n", b"\n\n\n\n")
    world.fetcher.add(ARTICLE_URL, reflowed)

    again = run(world.service.retrieve(ARTICLE_URL))

    assert world.fetcher.requested_urls == [ARTICLE_URL, ARTICLE_URL]
    assert again.fetched
    assert again.snapshot_reused
    assert again.snapshot == first.snapshot
    assert run(world.articles.list_snapshots(first.article.article_id)) == (first.snapshot,)
    assert sha256(reflowed) not in world.blobs.stored_keys()

    # That re-fetch counts as the last readable retrieval, so the next call inside the age is not fetched.
    world.clock.advance(timedelta(hours=1))
    run(world.service.retrieve(ARTICLE_URL))
    assert world.fetcher.requested_urls == [ARTICLE_URL, ARTICLE_URL]


def test_dedupe_after_the_refetch_age_changed_text_makes_a_new_snapshot() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    first = run(world.service.retrieve(ARTICLE_URL))
    world.clock.advance(timedelta(hours=200))
    world.fetcher.add(ARTICLE_URL, CHANGED_BODY)

    again = run(world.service.retrieve(ARTICLE_URL))

    assert not again.snapshot_reused
    assert again.snapshot is not None
    assert first.snapshot is not None
    assert again.snapshot.snapshot_id != first.snapshot.snapshot_id
    assert again.snapshot.normalized_text_hash == CHANGED_TEXT_HASH
    assert again.article.article_id == first.article.article_id
    assert run(world.articles.list_snapshots(first.article.article_id)) == (again.snapshot, first.snapshot)


def test_dedupe_compares_with_the_newest_snapshot_only() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    original = run(world.service.retrieve(ARTICLE_URL))
    world.fetcher.add(ARTICLE_URL, CHANGED_BODY)
    world.clock.advance(timedelta(minutes=1))
    changed = run(world.service.retrieve(ARTICLE_URL, refresh=True))
    world.fetcher.add(ARTICLE_URL, BODY)
    world.clock.advance(timedelta(minutes=1))

    reverted = run(world.service.retrieve(ARTICLE_URL, refresh=True))

    # Back to the original text: a third snapshot, so the newest is always what was last read.
    assert reverted.snapshot is not None
    assert reverted.snapshot not in (original.snapshot, changed.snapshot)
    assert not reverted.snapshot_reused


def test_dedupe_finds_an_article_stored_under_its_rel_canonical() -> None:
    world = build_world()
    short_link = "https://www.example.org/s/8812"
    canonical = "https://www.example.org/energy/2026/10/grid-storage"
    for url in (short_link, canonical):
        world.fetcher.add(url, BODY)
        world.extractor.hints[url] = UnverifiedMetadataHints(canonical_url=canonical)

    through_the_short_link = run(world.service.retrieve(short_link))
    direct = run(world.service.retrieve(canonical))

    assert through_the_short_link.article.canonical_url == canonical
    # Found under the canonical URL before any fetch, so it was not fetched again.
    assert world.fetcher.requested_urls == [short_link]
    assert direct.article.article_id == through_the_short_link.article.article_id
    assert direct.snapshot == through_the_short_link.snapshot
    refreshed = run(world.service.retrieve(short_link, refresh=True))
    assert refreshed.article.article_id == through_the_short_link.article.article_id
    assert refreshed.snapshot_reused


def test_dedupe_never_reuses_a_snapshot_made_under_another_normalizer_version() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    first = run(world.service.retrieve(ARTICLE_URL))
    assert first.snapshot is not None
    older = first.snapshot.evolve(
        snapshot_id="0000000000000000000000AGED", normalizer_version="evidence-normalizer-v0"
    )
    world.clock.advance(timedelta(seconds=1))
    run(world.articles.save_snapshot(older.evolve(retrieved_at=world.clock.now())))

    again = run(world.service.retrieve(ARTICLE_URL, refresh=True))

    # The newest snapshot holds the same text hash, but under rules this build does not run.
    assert again.snapshot is not None
    assert not again.snapshot_reused
    assert again.snapshot.snapshot_id not in (first.snapshot.snapshot_id, "0000000000000000000000AGED")
    assert again.snapshot.normalizer_version == "evidence-normalizer-v1"


def test_dedupe_refresh_fetches_inside_the_refetch_age() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    first = run(world.service.retrieve(ARTICLE_URL))
    world.fetcher.add(ARTICLE_URL, CHANGED_BODY)

    refreshed = run(world.service.retrieve(ARTICLE_URL, refresh=True))

    assert world.fetcher.requested_urls == [ARTICLE_URL, ARTICLE_URL]
    assert refreshed.snapshot is not None
    assert first.snapshot is not None
    assert refreshed.snapshot.snapshot_id != first.snapshot.snapshot_id


def test_dedupe_refetch_age_comes_from_settings() -> None:
    world = build_world(ArticleSettings(refetch_after_hours=1))
    world.fetcher.add(ARTICLE_URL, BODY)
    run(world.service.retrieve(ARTICLE_URL))
    world.clock.advance(timedelta(minutes=59))
    run(world.service.retrieve(ARTICLE_URL))
    assert world.fetcher.requested_urls == [ARTICLE_URL]
    world.clock.advance(timedelta(minutes=1))
    run(world.service.retrieve(ARTICLE_URL))
    assert world.fetcher.requested_urls == [ARTICLE_URL, ARTICLE_URL]


def test_dedupe_a_failed_last_retrieval_is_fetched_again() -> None:
    world = build_world()
    first = run(world.service.retrieve(ARTICLE_URL))
    assert first.access_status is AccessStatus.NOT_FOUND
    world.fetcher.add(ARTICLE_URL, BODY)

    second = run(world.service.retrieve(ARTICLE_URL))

    assert world.fetcher.requested_urls == [ARTICLE_URL, ARTICLE_URL]
    assert second.access_status is AccessStatus.ACCESSIBLE
    assert second.article.article_id == first.article.article_id


def test_dedupe_a_known_article_with_only_user_text_is_fetched() -> None:
    world = build_world()
    run(
        world.service.ingest_user_text(
            source_url=ARTICLE_URL, text=TEXT, attested=True, reported_access_status=AccessStatus.ACCESSIBLE
        )
    )
    world.fetcher.add(ARTICLE_URL, BODY)

    outcome = run(world.service.retrieve(ARTICLE_URL))

    assert world.fetcher.requested_urls == [ARTICLE_URL]
    assert outcome.snapshot is not None
    assert outcome.snapshot.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED


# --------------------------------------------------------------------------------------------
# ac4: user-supplied text
# --------------------------------------------------------------------------------------------

PAYWALLED_URL = "https://www.example-daily.com/2026/10/grid-storage?utm_source=twitter"
PAYWALLED_CANONICAL = "https://www.example-daily.com/2026/10/grid-storage"


def test_user_text_is_snapshotted_as_user_supplied_with_the_reported_status() -> None:
    world = build_world()

    outcome = run(
        world.service.ingest_user_text(
            source_url=PAYWALLED_URL,
            text=TEXT,
            attested=True,
            reported_access_status=AccessStatus.PAYWALLED,
            title="Grid storage, two summers on",
        )
    )

    assert world.fetcher.requested_urls == []
    assert not outcome.fetched
    snapshot = outcome.snapshot
    assert snapshot is not None
    assert snapshot.provenance_mode is ProvenanceMode.USER_SUPPLIED
    assert snapshot.access_status is AccessStatus.PAYWALLED
    assert snapshot.sha256 == sha256(BODY)
    assert snapshot.normalized_text_hash == sha256(TEXT.encode("utf-8"))
    assert snapshot.extractor_version == USER_TEXT_EXTRACTOR_VERSION == "user-supplied-text-1"
    assert snapshot.content_type == USER_TEXT_CONTENT_TYPE == "text/plain; charset=utf-8"
    assert snapshot.canonical_url == PAYWALLED_CANONICAL
    assert outcome.access_status is AccessStatus.PAYWALLED
    assert outcome.article.canonical_url == PAYWALLED_CANONICAL
    assert outcome.article.access_status is AccessStatus.PAYWALLED
    assert outcome.article.title == "Grid storage, two summers on"
    assert run(world.articles.list_snapshots(outcome.article.article_id)) == (snapshot,)


def test_user_text_without_the_attestation_stores_nothing() -> None:
    world = build_world()
    with pytest.raises(UserTextNotAttested):
        run(world.service.ingest_user_text(source_url=PAYWALLED_URL, text=TEXT, attested=False))
    assert run(world.articles.find_by_canonical_url(PAYWALLED_CANONICAL)) is None
    assert world.blobs.stored_keys() == frozenset()


def test_user_text_with_a_truthy_attestation_that_is_not_true_stores_nothing() -> None:
    world = build_world()
    with pytest.raises(UserTextNotAttested):
        run(world.service.ingest_user_text(source_url=PAYWALLED_URL, text=TEXT, attested="yes"))  # type: ignore[arg-type]
    assert world.blobs.stored_keys() == frozenset()


@pytest.mark.parametrize("source_url", ["", "   ", "not a url", "mailto:editor@example.org"])
def test_user_text_without_a_source_url_stores_nothing(source_url: str) -> None:
    world = build_world()
    with pytest.raises(InvalidSourceUrl):
        run(world.service.ingest_user_text(source_url=source_url, text=TEXT, attested=True))
    assert world.blobs.stored_keys() == frozenset()


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        pytest.param("  \n\n \t", "the text is blank", id="blank"),
        pytest.param(
            SHORT_BODY.decode(), "the text is under the 500-character minimum for an article", id="short"
        ),
        pytest.param(TEXT + "x" * 1000, "the text is 1551 bytes, over the 1500-byte limit", id="too-large"),
        pytest.param(
            TEXT + "\ud800", "the text is not valid Unicode (it has a lone surrogate)", id="lone-surrogate"
        ),
    ],
)
def test_user_text_quality_gates_store_nothing(text: str, reason: str) -> None:
    world = build_world(max_user_text_bytes=1500)
    with pytest.raises(UserTextRejected) as refused:
        run(world.service.ingest_user_text(source_url=PAYWALLED_URL, text=text, attested=True))
    assert refused.value.reason == reason
    assert run(world.articles.find_by_canonical_url(PAYWALLED_CANONICAL)) is None
    assert world.blobs.stored_keys() == frozenset()


def test_user_text_attaches_to_the_article_a_paywalled_retrieval_recorded() -> None:
    world = build_world()
    world.fetcher.add(PAYWALLED_URL, b"<html>Subscribe</html>", status_code=402)
    refused = run(world.service.retrieve(PAYWALLED_URL))

    supplied = run(world.service.ingest_user_text(source_url=PAYWALLED_URL, text=TEXT, attested=True))

    assert supplied.article.article_id == refused.article.article_id
    # The platform measured PAYWALLED; a report does not overwrite it.
    assert supplied.article.access_status is AccessStatus.PAYWALLED
    assert supplied.snapshot is not None
    assert supplied.snapshot.access_status is AccessStatus.UNKNOWN
    assert supplied.snapshot.provenance_mode is ProvenanceMode.USER_SUPPLIED


def test_user_text_supplied_twice_reuses_its_snapshot() -> None:
    world = build_world()
    first = run(world.service.ingest_user_text(source_url=PAYWALLED_URL, text=TEXT, attested=True))
    second = run(world.service.ingest_user_text(source_url=PAYWALLED_URL, text=TEXT + "\n", attested=True))
    assert second.snapshot == first.snapshot
    assert second.snapshot_reused
    changed = run(
        world.service.ingest_user_text(
            source_url=PAYWALLED_URL, text="\n\n".join(CHANGED_PARAGRAPHS), attested=True
        )
    )
    assert changed.snapshot != first.snapshot
    assert not changed.snapshot_reused


def test_user_text_stays_distinguishable_from_the_publisher_snapshot() -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    readable = run(world.service.retrieve(ARTICLE_URL))
    supplied = run(world.service.ingest_user_text(source_url=ARTICLE_URL, text=TEXT, attested=True))

    again = run(world.service.retrieve(ARTICLE_URL))

    # The same text, but two snapshots: one the publisher served, one a user supplied.
    assert supplied.snapshot is not None
    assert readable.snapshot is not None
    assert supplied.snapshot.snapshot_id != readable.snapshot.snapshot_id
    assert supplied.snapshot.normalized_text_hash == readable.snapshot.normalized_text_hash
    assert supplied.snapshot.provenance_mode is ProvenanceMode.USER_SUPPLIED
    # A retrieval answers with the publisher's snapshot, never the user's.
    assert again.snapshot == readable.snapshot
    assert again.snapshot is not None
    assert again.snapshot.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED


# --------------------------------------------------------------------------------------------
# ac5: one structured log event per outcome, with no page content
# --------------------------------------------------------------------------------------------

LOG_FIELDS = (
    "correlation_id",
    "canonical_url",
    "access_status",
    "elapsed_ms",
    "fetched",
    "snapshot_id",
    "snapshot_reused",
    "provenance_mode",
    "reason",
    "rules_version",
)


def events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == article_service_module.__name__]


def extras(record: logging.LogRecord) -> dict[str, object]:
    """The event's structured fields, as `extra=` set them."""
    return {field: record.__dict__[field] for field in LOG_FIELDS}


def assert_no_page_text(record: logging.LogRecord) -> None:
    rendered = [record.getMessage(), *(str(value) for value in extras(record).values())]
    assert not any(SENTINEL in value for value in rendered)
    assert not any(PARAGRAPHS[0][:40] in value for value in rendered)


def test_log_event_for_a_readable_page(caplog: pytest.LogCaptureFixture) -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, SENTINEL_BODY)
    with caplog.at_level(logging.INFO, logger=article_service_module.__name__):
        outcome = run(world.service.retrieve(ARTICLE_URL, correlation_id="req-7f3a"))

    [record] = events(caplog)
    assert record.getMessage() == "article retrieval"
    assert outcome.snapshot is not None
    expected = {
        "correlation_id": "req-7f3a",
        "canonical_url": ARTICLE_URL,
        "access_status": "ACCESSIBLE",
        "elapsed_ms": 250.0,
        "fetched": True,
        "snapshot_id": outcome.snapshot.snapshot_id,
        "snapshot_reused": False,
        "provenance_mode": "PUBLISHER_RETRIEVED",
        "reason": "The text was extracted: 94 words",
        "rules_version": "paywall_rules.v1",
    }
    assert extras(record) == expected
    assert outcome.elapsed_ms == 250.0
    assert_no_page_text(record)


@pytest.mark.parametrize(
    "name", ["metered-page-with-the-whole-text", "bot-challenge", "not-found", "encrypted-pdf"]
)
def test_log_event_for_a_refusal(name: str, caplog: pytest.LogCaptureFixture) -> None:
    case, expected_status, _ = FAILURES[name]
    world = build_world()
    register_failure(world, case)
    with caplog.at_level(logging.INFO, logger=article_service_module.__name__):
        outcome = run(world.service.retrieve(ARTICLE_URL, correlation_id="req-0001"))

    [record] = events(caplog)
    assert extras(record)["correlation_id"] == "req-0001"
    assert extras(record)["canonical_url"] == ARTICLE_URL
    assert extras(record)["access_status"] == expected_status.value
    assert extras(record)["elapsed_ms"] == 250.0
    assert extras(record)["snapshot_id"] is None
    assert extras(record)["reason"] == outcome.reason
    assert extras(record)["rules_version"] == "paywall_rules.v1"
    assert_no_page_text(record)


def test_log_event_for_a_stored_snapshot_and_for_user_text(caplog: pytest.LogCaptureFixture) -> None:
    world = build_world()
    world.fetcher.add(ARTICLE_URL, BODY)
    run(world.service.retrieve(ARTICLE_URL))
    supplied = "\n\n".join(SENTINEL_PARAGRAPHS)
    with caplog.at_level(logging.INFO, logger=article_service_module.__name__):
        reused = run(world.service.retrieve(ARTICLE_URL))
        ingested = run(world.service.ingest_user_text(source_url=PAYWALLED_URL, text=supplied, attested=True))

    stored_event, user_event = events(caplog)
    assert stored_event.getMessage() == "article retrieval"
    assert extras(stored_event)["fetched"] is False
    assert extras(stored_event)["snapshot_reused"] is True
    assert extras(stored_event)["elapsed_ms"] == 0.0
    assert extras(stored_event)["correlation_id"] == reused.correlation_id
    assert user_event.getMessage() == "user text ingested"
    assert extras(user_event)["provenance_mode"] == "USER_SUPPLIED"
    assert extras(user_event)["canonical_url"] == PAYWALLED_CANONICAL
    assert extras(user_event)["access_status"] == "UNKNOWN"
    assert extras(user_event)["correlation_id"] == ingested.correlation_id
    assert ingested.correlation_id != reused.correlation_id
    assert_no_page_text(stored_event)
    assert_no_page_text(user_event)


# --------------------------------------------------------------------------------------------
# The constraint: ports only
# --------------------------------------------------------------------------------------------

FORBIDDEN_MODULES = frozenset(
    {
        "httpx",
        "trafilatura",
        "readability",
        "pypdf",
        "lxml",
        "os",
        "pathlib",
        "shutil",
        "io",
        "tempfile",
        "boto3",
    }
)


def test_the_service_imports_no_http_extraction_or_filesystem_code() -> None:
    tree = ast.parse(inspect.getsource(article_service_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert imported & FORBIDDEN_MODULES == set()
    assert "debate_core" in imported
    assert "open" not in called

"""The worked example of the injection pattern behaves, and is testable without any adapter.

The point of these tests is less the service — it is four lines of logic — than the demonstration
that a service built this way needs no filesystem, no database, no patching and no monkeypatched
clock to be tested down to the exact timestamp and id it writes.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import timedelta
from typing import Any, cast

from debate_core.application.services import ArticleRegistrationService
from debate_core.domain import SourceType
from debate_core.testing import (
    FAKE_EPOCH,
    FixedClock,
    InMemoryArticleRepository,
    SequentialIdGenerator,
)

OWNER_ID = "0STD0000000000000000000001"  # the ULID alphabet has no O, I, L or U


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion; see the note in `test_fakes.py`."""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("an in-memory fake suspended; fakes must not perform real I/O")


def build_service() -> tuple[ArticleRegistrationService, InMemoryArticleRepository]:
    articles = InMemoryArticleRepository()
    service = ArticleRegistrationService(
        articles=articles,
        clock=FixedClock(step=timedelta(minutes=1)),
        id_generator=SequentialIdGenerator("ART"),
    )
    return service, articles


def test_registering_a_new_source_records_it_with_injected_time_and_id() -> None:
    service, articles = build_service()
    article = run(service.register(canonical_url="https://example.org/methane", title="Arctic methane"))
    assert article.article_id == "0ART0000000000000000000001"
    assert article.created_at == FAKE_EPOCH
    assert article.updated_at == FAKE_EPOCH
    assert article.revision == 1
    assert run(articles.get(article.article_id)) == article


def test_registering_the_same_url_twice_returns_the_stored_article() -> None:
    service, articles = build_service()
    first = run(service.register(canonical_url="https://example.org/a", title="First title"))
    second = run(service.register(canonical_url="https://example.org/a", title="Different title"))

    assert second == first
    assert second.title == "First title"
    assert run(articles.find_by_canonical_url("https://example.org/a")) == first
    # The second call created nothing, so the next new source still gets the second id.
    third = run(service.register(canonical_url="https://example.org/b", title="B"))
    assert third.article_id == "0ART0000000000000000000002"


def test_a_second_distinct_url_gets_the_next_id_and_the_next_instant() -> None:
    service, _ = build_service()
    first = run(service.register(canonical_url="https://example.org/a", title="A"))
    second = run(
        service.register(
            canonical_url="https://example.org/b",
            title="B",
            owner_id=OWNER_ID,
            source_type=SourceType.SCHOLARLY,
        )
    )
    assert (first.article_id, second.article_id) == (
        "0ART0000000000000000000001",
        "0ART0000000000000000000002",
    )
    assert second.created_at == FAKE_EPOCH + timedelta(minutes=1)
    assert second.source_type is SourceType.SCHOLARLY
    assert second.owner_id == OWNER_ID

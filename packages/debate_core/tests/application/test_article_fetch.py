"""ArticleFetch: one ArticleService answer, reported for `debate-research fetch` (v1-e04-t06).

The service is the real one over the in-memory fakes; what is tested here is what the report adds: the
paragraph count read from the stored, re-hashed snapshot, the fields carried over, the connection
closed, and the published schema. Expected values are written by hand from the bodies below: the body
has three paragraphs, and its raw hash is SHA-256 of its bytes as written.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from debate_core.application.article_fetch import (
    FETCH_RESULT_SCHEMA_FILENAME,
    ArticleFetch,
    FetchReport,
    render_fetch_result_schema,
)
from debate_core.application.article_service import ArticleService, UserTextNotAttested
from debate_core.application.errors import SnapshotIntegrityError
from debate_core.application.settings import ArticleSettings
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemoryArticleRepository, InMemorySnapshotStore
from debate_core.testing.fakes.providers import FakeArticleFetcher, FakeContentExtractor

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
URL = "https://www.example.org/water/2026/basin-report?utm_campaign=autumn"
CANONICAL = "https://www.example.org/water/2026/basin-report"
PARAGRAPH = (
    "The basin council voted to open the reservoir after a summer in which three of the four regions "
    "drew down their groundwater faster than the aquifer recharged. "
)
BODY = "\n\n".join(PARAGRAPH * 2 for _ in range(3)).encode()
"""Three paragraphs, 572 characters of text: over the 500-character minimum."""


@dataclass
class Connection:
    closed: int = 0

    async def aclose(self) -> None:
        self.closed += 1


@dataclass
class World:
    fetch: ArticleFetch
    fetcher: FakeArticleFetcher
    articles: InMemoryArticleRepository
    blobs: InMemorySnapshotStore
    connection: Connection


def build_world() -> World:
    clock, ids = FixedClock(), SequentialIdGenerator()
    articles, blobs = InMemoryArticleRepository(), InMemorySnapshotStore()
    fetcher = FakeArticleFetcher(clock=clock)
    snapshots = SnapshotService(blobs=blobs, clock=clock, id_generator=ids)
    service = ArticleService(
        articles=articles,
        snapshots=snapshots,
        fetcher=fetcher,
        extractor=FakeContentExtractor(),
        clock=clock,
        id_generator=ids,
        settings=ArticleSettings(),
        max_user_text_bytes=100_000,
    )
    connection = Connection()
    return World(
        ArticleFetch(articles=service, snapshots=snapshots, connection=connection),
        fetcher,
        articles,
        blobs,
        connection,
    )


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def test_a_readable_page_is_reported_with_its_snapshot_hashes_and_paragraph_count() -> None:
    world = build_world()
    world.fetcher.add(URL, BODY)

    report = run(world.fetch.retrieve(URL))

    assert report.access_status is AccessStatus.ACCESSIBLE
    assert (report.requested_url, report.canonical_url, report.final_url) == (URL, CANONICAL, URL)
    assert report.fetched
    assert report.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED
    assert report.rules_version == "paywall_rules.v1"
    assert report.evidence is not None and report.evidence.status_code == 200
    snapshot = report.snapshot
    assert snapshot is not None
    assert snapshot.sha256 == hashlib.sha256(BODY).hexdigest()
    assert snapshot.paragraph_count == 3
    assert snapshot.extractor_version == "fake-extractor/fake-1.0.0"
    assert snapshot.normalizer_version == "evidence-normalizer-v1"
    assert snapshot.byte_size == len(BODY)
    assert not snapshot.reused


def test_a_second_run_within_the_refetch_age_reports_the_stored_snapshot_and_refresh_asks_again() -> None:
    world = build_world()
    world.fetcher.add(URL, BODY)
    first = run(world.fetch.retrieve(URL))

    again = run(world.fetch.retrieve(URL))
    refreshed = run(world.fetch.retrieve(URL, refresh=True))

    assert world.fetcher.requested_urls == [URL, URL]
    assert (again.fetched, refreshed.fetched) == (False, True)
    assert again.snapshot is not None and first.snapshot is not None
    assert (again.snapshot.snapshot_id, again.snapshot.reused) == (first.snapshot.snapshot_id, True)
    assert again.evidence is None


def test_a_page_that_is_not_accessible_is_reported_with_its_reason_and_no_snapshot() -> None:
    world = build_world()
    world.fetcher.add(URL, b"<p>Subscribe to read.</p>", status_code=402)

    report = run(world.fetch.retrieve(URL))

    assert report.access_status is AccessStatus.PAYWALLED
    assert report.reason == "The server requires payment (402)"
    assert report.rules_version == "paywall_rules.v1"
    assert (report.snapshot, report.provenance_mode) == (None, None)
    assert report.title == CANONICAL
    assert world.blobs.stored_keys() == frozenset()


def test_pasted_text_is_reported_as_user_supplied_and_nothing_is_fetched() -> None:
    world = build_world()

    report = run(world.fetch.ingest_pasted(source_url=URL, text=BODY.decode(), attested=True))

    assert report.provenance_mode is ProvenanceMode.USER_SUPPLIED
    assert report.access_status is AccessStatus.UNKNOWN
    assert not report.fetched
    assert report.snapshot is not None and report.snapshot.paragraph_count == 3
    assert world.fetcher.requested_urls == []


def test_unattested_pasted_text_is_refused_and_stores_nothing() -> None:
    world = build_world()

    with pytest.raises(UserTextNotAttested):
        run(world.fetch.ingest_pasted(source_url=URL, text=BODY.decode(), attested=False))

    assert world.blobs.stored_keys() == frozenset()


def test_a_snapshot_whose_stored_text_was_altered_is_refused_rather_than_reported() -> None:
    world = build_world()
    world.fetcher.add(URL, BODY)
    stored = run(world.fetch.retrieve(URL)).snapshot
    assert stored is not None
    record = run(world.articles.get_snapshot(stored.snapshot_id))
    world.blobs.corrupt(record.normalized_blob_key, b"not the text")

    with pytest.raises(SnapshotIntegrityError):
        run(world.fetch.retrieve(URL))


def test_leaving_the_context_closes_the_connection_even_when_the_run_fails() -> None:
    world = build_world()

    async def failing_run() -> None:
        async with world.fetch:
            await world.fetch.ingest_pasted(source_url=URL, text="", attested=True)

    with pytest.raises(Exception, match="blank"):
        run(failing_run())
    assert world.connection.closed == 1


def test_no_report_field_holds_page_text() -> None:
    world = build_world()
    world.fetcher.add(URL, BODY)

    dumped = json.dumps(run(world.fetch.retrieve(URL)).model_dump(mode="json"))

    assert "basin council" not in dumped


# --------------------------------------------------------------------------------------------
# The published schema
# --------------------------------------------------------------------------------------------


def committed_schema() -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / FETCH_RESULT_SCHEMA_FILENAME).read_text(encoding="utf-8"))


def test_the_committed_schema_is_what_the_code_renders() -> None:
    assert committed_schema() == render_fetch_result_schema(), (
        f"{FETCH_RESULT_SCHEMA_FILENAME} is stale; run: uv run scripts/export_schemas.py"
    )


def envelope(status: str, data: object, error: object) -> dict[str, object]:
    return {"schema_version": 1, "status": status, "command": "fetch", "data": data, "error": error}


def failure(code: str, exit_code: int, details: object) -> dict[str, object]:
    return {"code": code, "message": "m", "exit_code": exit_code, "details": details, "hint": None}


def errors(document: Any) -> list[str]:
    found: list[Any] = list(Draft202012Validator(committed_schema()).iter_errors(document))  # pyright: ignore[reportUnknownMemberType]
    return [str(error.message) for error in found]


def report_of(world_report: FetchReport) -> dict[str, Any]:
    return world_report.model_dump(mode="json")


def test_the_schema_takes_each_outcome_with_its_exit_code_and_refuses_a_mismatch() -> None:
    world = build_world()
    world.fetcher.add(URL, BODY)
    readable = report_of(run(world.fetch.retrieve(URL)))
    world.fetcher.add(URL, b"", status_code=404)
    missing = report_of(run(world.fetch.retrieve(URL, refresh=True)))

    assert errors(envelope("ok", readable, None)) == []
    assert errors(envelope("error", None, failure("SOURCE_NOT_ACCESSIBLE", 3, missing))) == []
    assert errors(envelope("error", None, failure("USER_TEXT_NOT_ATTESTED", 1, {}))) == []
    # A NOT_FOUND report is never a success, a readable one never a failure, and exit codes are fixed.
    assert errors(envelope("ok", missing, None)) != []
    assert errors(envelope("error", None, failure("SOURCE_NOT_ACCESSIBLE", 3, readable))) != []
    assert errors(envelope("error", None, failure("SOURCE_NOT_ACCESSIBLE", 1, missing))) != []
    assert errors(envelope("error", None, failure("USER_TEXT_NOT_ATTESTED", 3, {}))) != []

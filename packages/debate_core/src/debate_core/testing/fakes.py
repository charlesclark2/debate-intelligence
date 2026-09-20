"""In-memory implementations of every port, for tests anywhere in the codebase.

These are *fakes*, not mocks: each one really does the job its port describes, in a dictionary.
`InMemoryCardRepository` really refuses a stale write, `InMemorySnapshotStore` really deduplicates
identical bytes and really detects a corrupted blob. A test written against them exercises the
same code paths a test against SQLite would, which is what makes the shared contract suite
(v1-e02-t04-repo-contract-tests) able to run unchanged against both.

They ship in `debate_core` rather than in a test directory because every package's tests need them
— `debate_cli`, `debate_api` and `debate_workers` each wire a service to fakes — and because V2's
cloud adapters are held to the same contracts.

Nothing here touches the filesystem, the network or the clock. `FixedClock` and
`SequentialIdGenerator` exist precisely so that a service's output is byte-identical on every run.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ValidationError

from debate_core.application.errors import (
    AlreadyExists,
    BlobIntegrityError,
    Conflict,
    InvalidCursor,
    InvalidModelOutput,
    NotFound,
    ProviderUnavailable,
    RevisionMismatch,
)
from debate_core.application.ports import (
    DEFAULT_PAGE_SIZE,
    ArticleFetcher,
    ArticleRepository,
    BlobKey,
    CandidateResult,
    CardRepository,
    CaselistRepository,
    Clock,
    ContentExtractor,
    ExtractedContent,
    ExtractionQuality,
    FetchResult,
    IdGenerator,
    ModelInvocation,
    ModelInvocationMetadata,
    ModelRouter,
    ModelTaskClass,
    Page,
    ProviderQuery,
    ProviderResponse,
    SearchProvider,
    SearchRepository,
    SnapshotStore,
    SourceMetadataHints,
)
from debate_core.domain import (
    CROCKFORD_BASE32_ALPHABET,
    AccessStatus,
    Article,
    Card,
    Search,
    SearchResult,
    SourceSnapshot,
)
from debate_core.domain.caselist import (
    ArchiveSnapshot,
    CampFile,
    Disclosure,
    Event,
    SourceDocument,
)

__all__ = [
    "FAKE_EPOCH",
    "FakeArticleFetcher",
    "FakeContentExtractor",
    "FakeModelRouter",
    "FakePorts",
    "FakeSearchProvider",
    "FixedClock",
    "InMemoryArticleRepository",
    "InMemoryCardRepository",
    "InMemoryCaselistRepository",
    "InMemorySearchRepository",
    "InMemorySnapshotStore",
    "RecordedModelCall",
    "SequentialIdGenerator",
    "build_fake_caselist_repository",
    "build_fake_ports",
]

#: The instant a `FixedClock` starts at unless told otherwise. Obviously synthetic, and in the
#: past, so a timestamp that leaks into a golden file is recognisable at a glance.
FAKE_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


# --------------------------------------------------------------------------------------------
# Pagination shared by the in-memory repositories
# --------------------------------------------------------------------------------------------


def _newest_first[ItemT](rows: Iterable[tuple[str, datetime, ItemT]]) -> list[tuple[str, ItemT]]:
    """Order rows by `created_at` descending, breaking ties by id descending.

    The tie-break is what makes the order total, and therefore what makes pagination reproducible:
    two records created in the same millisecond must not be able to swap places between pages.
    """
    ordered = sorted(rows, key=lambda row: (row[1], row[0]), reverse=True)
    return [(row[0], row[2]) for row in ordered]


def _paginate[ItemT](
    rows: Sequence[tuple[str, ItemT]], *, kind: str, limit: int, cursor: str | None
) -> Page[ItemT]:
    """Cut one page out of an already-ordered sequence of (id, item) rows.

    The cursor is `"<kind>:<id of the last item on the previous page>"`. It is opaque to callers
    by contract, and a cursor minted by a different listing is rejected rather than silently
    treated as "start from the beginning".
    """
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")
    start = 0
    if cursor is not None:
        prefix = f"{kind}:"
        if not cursor.startswith(prefix):
            raise InvalidCursor(cursor)
        last_id = cursor[len(prefix) :]
        positions = [index for index, (row_id, _) in enumerate(rows) if row_id == last_id]
        if not positions:
            raise InvalidCursor(cursor)
        start = positions[0] + 1
    window = rows[start : start + limit]
    exhausted = start + limit >= len(rows)
    next_cursor = None if exhausted or not window else f"{kind}:{window[-1][0]}"
    return Page(items=tuple(item for _, item in window), next_cursor=next_cursor)


# --------------------------------------------------------------------------------------------
# Persistence fakes
# --------------------------------------------------------------------------------------------


class InMemoryArticleRepository:
    """Articles and snapshot metadata in two dictionaries.

    Saving an article is an upsert that bumps its revision; saving a snapshot refuses to overwrite
    one, because snapshots are immutable and re-retrieving a source is a new snapshot.
    """

    def __init__(self) -> None:
        self._articles: dict[str, Article] = {}
        self._snapshots: dict[str, SourceSnapshot] = {}

    async def get(self, article_id: str) -> Article:
        stored = self._articles.get(article_id)
        if stored is None:
            raise NotFound("Article", article_id)
        return stored

    async def find_by_canonical_url(self, canonical_url: str) -> Article | None:
        for article in self._articles.values():
            if article.canonical_url == canonical_url:
                return article
        return None

    async def save(self, article: Article) -> Article:
        stored = self._articles.get(article.article_id)
        revision = 1 if stored is None else stored.revision + 1
        saved = article.evolve(revision=revision)
        self._articles[saved.article_id] = saved
        return saved

    async def delete(self, article_id: str) -> None:
        if article_id not in self._articles:
            raise NotFound("Article", article_id)
        del self._articles[article_id]

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Article]:
        rows = _newest_first(
            (article.article_id, article.created_at, article)
            for article in self._articles.values()
            if article.owner_id == owner_id
        )
        return _paginate(rows, kind="article", limit=limit, cursor=cursor)

    async def save_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        if snapshot.snapshot_id in self._snapshots:
            raise AlreadyExists("SourceSnapshot", snapshot.snapshot_id)
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> SourceSnapshot:
        stored = self._snapshots.get(snapshot_id)
        if stored is None:
            raise NotFound("SourceSnapshot", snapshot_id)
        return stored

    async def list_snapshots(self, article_id: str) -> tuple[SourceSnapshot, ...]:
        matching = [snapshot for snapshot in self._snapshots.values() if snapshot.article_id == article_id]
        matching.sort(key=lambda snapshot: (snapshot.retrieved_at, snapshot.snapshot_id), reverse=True)
        return tuple(matching)


class InMemorySnapshotStore:
    """Content-addressed blobs in a dictionary, integrity check included.

    `get` re-hashes what it holds, exactly as the filesystem and S3 stores do, so a test can prove
    that a tampered snapshot is caught rather than served — see :meth:`corrupt`.
    """

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, data: bytes) -> BlobKey:
        key = hashlib.sha256(data).hexdigest()
        self._blobs.setdefault(key, data)
        return key

    async def get(self, key: BlobKey) -> bytes:
        stored = self._blobs.get(key)
        if stored is None:
            raise NotFound("snapshot blob", key)
        actual = hashlib.sha256(stored).hexdigest()
        if actual != key:
            raise BlobIntegrityError(key, actual)
        return stored

    async def exists(self, key: BlobKey) -> bool:
        return key in self._blobs

    def corrupt(self, key: BlobKey, replacement: bytes) -> None:
        """Replace a blob's bytes without changing its key, to test tamper detection.

        Test-only, and deliberately not part of the :class:`~debate_core.application.ports.
        persistence.SnapshotStore` port: no production code can rewrite a stored blob.
        """
        if key not in self._blobs:
            raise NotFound("snapshot blob", key)
        self._blobs[key] = replacement


class InMemoryCardRepository:
    """Cards in a dictionary, with the same optimistic-concurrency rules as SQLite and DynamoDB.

    The revision check is the whole point of the fake: a test that a reprocessing job cannot
    overwrite a student's edit must fail here for the same reason it would fail in production.
    """

    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}

    async def get(self, card_id: str) -> Card:
        stored = self._cards.get(card_id)
        if stored is None:
            raise NotFound("Card", card_id)
        return stored

    async def find(self, card_id: str) -> Card | None:
        return self._cards.get(card_id)

    async def create(self, card: Card) -> Card:
        if card.card_id in self._cards:
            raise AlreadyExists("Card", card.card_id)
        saved = card.evolve(revision=1)
        self._cards[saved.card_id] = saved
        return saved

    async def save(self, card: Card, *, expected_revision: int) -> Card:
        stored = self._cards.get(card.card_id)
        if stored is None:
            raise NotFound("Card", card.card_id)
        if stored.revision != expected_revision:
            raise RevisionMismatch("Card", card.card_id, expected_revision, stored.revision)
        saved = card.evolve(revision=stored.revision + 1)
        self._cards[saved.card_id] = saved
        return saved

    async def delete(self, card_id: str, *, expected_revision: int) -> None:
        stored = self._cards.get(card_id)
        if stored is None:
            raise NotFound("Card", card_id)
        if stored.revision != expected_revision:
            raise RevisionMismatch("Card", card_id, expected_revision, stored.revision)
        del self._cards[card_id]

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Card]:
        rows = _newest_first(
            (card.card_id, card.created_at, card)
            for card in self._cards.values()
            if card.owner_id == owner_id
        )
        return _paginate(rows, kind="card", limit=limit, cursor=cursor)

    async def list_by_article(
        self, article_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Card]:
        rows = _newest_first(
            (card.card_id, card.created_at, card)
            for card in self._cards.values()
            if card.article_id == article_id
        )
        return _paginate(rows, kind="card", limit=limit, cursor=cursor)


class InMemorySearchRepository:
    """Searches and their rankings, with the ranking replaced as a whole."""

    def __init__(self) -> None:
        self._searches: dict[str, Search] = {}
        self._results: dict[str, tuple[SearchResult, ...]] = {}

    async def get(self, search_id: str) -> Search:
        stored = self._searches.get(search_id)
        if stored is None:
            raise NotFound("Search", search_id)
        return stored

    async def save(self, search: Search) -> Search:
        stored = self._searches.get(search.search_id)
        revision = 1 if stored is None else stored.revision + 1
        saved = search.evolve(revision=revision)
        self._searches[saved.search_id] = saved
        return saved

    async def save_results(self, search_id: str, results: Sequence[SearchResult]) -> None:
        if search_id not in self._searches:
            raise NotFound("Search", search_id)
        foreign = [result.article_id for result in results if result.search_id != search_id]
        if foreign:
            raise ValueError(f"results for another search were given for {search_id}: {foreign}")
        ranks = [result.rank for result in results]
        if len(set(ranks)) != len(ranks):
            raise ValueError(f"two results share a rank in search {search_id}: {sorted(ranks)}")
        self._results[search_id] = tuple(sorted(results, key=lambda result: result.rank))

    async def list_results(self, search_id: str) -> tuple[SearchResult, ...]:
        if search_id not in self._searches:
            raise NotFound("Search", search_id)
        return self._results.get(search_id, ())

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Search]:
        rows = _newest_first(
            (search.search_id, search.created_at, search)
            for search in self._searches.values()
            if search.owner_id == owner_id
        )
        return _paginate(rows, kind="search", limit=limit, cursor=cursor)


class InMemoryCaselistRepository:
    """Imported caselist and camp-file records in dictionaries, keyed the way the port is keyed.

    The behaviour worth having a fake for is the cumulative-archive arithmetic: the same file
    arrives in every weekly archive until a team takes it down, so `put_source` widens a stored
    document's first/last seen range rather than replacing it, and it does that correctly even
    when archives are imported out of order. A fake that simply overwrote would let an importer
    test pass while the real thing lost the range that `caselist status` and the E32 reports read.

    It refuses a contradiction just as SQLite's unique constraint will: two different files cannot
    be filed under one SHA-256.
    """

    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, date], ArchiveSnapshot] = {}
        self._sources: dict[str, SourceDocument] = {}
        self._disclosures: dict[tuple[str, date, str], Disclosure] = {}
        self._camp_files: dict[tuple[str, int, str], CampFile] = {}

    # -- archive snapshots -----------------------------------------------------------------

    async def upsert_snapshot(self, snapshot: ArchiveSnapshot) -> ArchiveSnapshot:
        self._snapshots[(snapshot.caselist, snapshot.snapshot)] = snapshot
        return snapshot

    async def get_snapshot(self, caselist: str, snapshot: date) -> ArchiveSnapshot:
        stored = self._snapshots.get((caselist, snapshot))
        if stored is None:
            raise NotFound("ArchiveSnapshot", f"{caselist}/{snapshot.isoformat()}")
        return stored

    async def find_snapshot(self, caselist: str, snapshot: date) -> ArchiveSnapshot | None:
        return self._snapshots.get((caselist, snapshot))

    async def latest_snapshot(self, caselist: str) -> ArchiveSnapshot | None:
        for stored in await self.list_snapshots(caselist):
            return stored
        return None

    async def list_snapshots(self, caselist: str) -> tuple[ArchiveSnapshot, ...]:
        matching = [stored for stored in self._snapshots.values() if stored.caselist == caselist]
        matching.sort(key=lambda stored: stored.snapshot, reverse=True)
        return tuple(matching)

    # -- source documents ------------------------------------------------------------------

    async def put_source(self, source: SourceDocument) -> SourceDocument:
        stored = self._sources.get(source.sha256)
        if stored is None:
            self._sources[source.sha256] = source
            return source
        unchanged = (stored.byte_size, stored.source_format, stored.origin)
        incoming = (source.byte_size, source.source_format, source.origin)
        if unchanged != incoming:
            raise Conflict(
                f"SourceDocument {source.sha256} is already stored as "
                f"{stored.byte_size} bytes / {stored.source_format} / {stored.origin}, "
                f"and cannot be restored as {source.byte_size} bytes / "
                f"{source.source_format} / {source.origin}"
            )
        widened = stored.evolve(
            first_seen_snapshot=min(stored.first_seen_snapshot, source.first_seen_snapshot),
            last_seen_snapshot=max(stored.last_seen_snapshot, source.last_seen_snapshot),
        )
        self._sources[widened.sha256] = widened
        return widened

    async def get_source(self, sha256: str) -> SourceDocument:
        stored = self._sources.get(sha256)
        if stored is None:
            raise NotFound("SourceDocument", sha256)
        return stored

    async def find_source(self, sha256: str) -> SourceDocument | None:
        return self._sources.get(sha256)

    async def list_sources(
        self,
        *,
        caselist: str | None = None,
        snapshot: date | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[SourceDocument]:
        matching = [
            stored
            for stored in self._sources.values()
            if (caselist is None or stored.caselist == caselist)
            and (snapshot is None or stored.first_seen_snapshot <= snapshot <= stored.last_seen_snapshot)
        ]
        matching.sort(key=lambda stored: (_descending(stored.last_seen_snapshot), stored.sha256))
        rows = [(stored.sha256, stored) for stored in matching]
        return _paginate(rows, kind="caselist-source", limit=limit, cursor=cursor)

    # -- disclosures and camp files --------------------------------------------------------

    async def record_disclosure(self, disclosure: Disclosure) -> Disclosure:
        self._disclosures[_disclosure_key(disclosure)] = disclosure
        return disclosure

    async def record_camp_file(self, camp_file: CampFile) -> CampFile:
        self._camp_files[_camp_file_key(camp_file)] = camp_file
        return camp_file

    async def list_disclosures(
        self,
        *,
        caselist: str | None = None,
        snapshot: date | None = None,
        school: str | None = None,
        team_code: str | None = None,
        source_sha256: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Disclosure]:
        matching = [
            stored
            for stored in self._disclosures.values()
            if (caselist is None or stored.caselist == caselist)
            and (snapshot is None or stored.snapshot == snapshot)
            and (school is None or stored.school == school)
            and (team_code is None or stored.team_code == team_code)
            and (source_sha256 is None or stored.source_sha256 == source_sha256)
        ]
        matching.sort(key=lambda stored: (_descending(stored.snapshot), stored.caselist, stored.source_path))
        rows = [("|".join(str(part) for part in _disclosure_key(stored)), stored) for stored in matching]
        return _paginate(rows, kind="disclosure", limit=limit, cursor=cursor)

    async def list_camp_files(
        self,
        *,
        camp: str | None = None,
        year: int | None = None,
        event: Event | None = None,
        source_sha256: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[CampFile]:
        matching = [
            stored
            for stored in self._camp_files.values()
            if (camp is None or stored.camp == camp)
            and (year is None or stored.year == year)
            and (event is None or stored.event is event)
            and (source_sha256 is None or stored.source_sha256 == source_sha256)
        ]
        matching.sort(
            key=lambda stored: (_descending(stored.snapshot), stored.file_title, stored.source_sha256)
        )
        rows = [("|".join(str(part) for part in _camp_file_key(stored)), stored) for stored in matching]
        return _paginate(rows, kind="camp-file", limit=limit, cursor=cursor)


def _disclosure_key(disclosure: Disclosure) -> tuple[str, date, str]:
    """The natural key of a disclosure: one file, in one snapshot, at one path."""
    return (disclosure.caselist, disclosure.snapshot, disclosure.source_path)


def _camp_file_key(camp_file: CampFile) -> tuple[str, int, str]:
    """The natural key of a camp file: one file, released once, for one event."""
    return (camp_file.source_sha256, camp_file.year, str(camp_file.event))


def _descending(day: date) -> date:
    """Sort key helper: `date.max - day` puts the newest snapshot first inside an ascending sort.

    The listings order by snapshot *descending* and by their remaining key parts *ascending*, and
    one `sorted` call cannot mix directions. Inverting the date here keeps the whole key ascending,
    which is what makes the order total and the pagination reproducible.
    """
    return date.min + (date.max - day)


# --------------------------------------------------------------------------------------------
# Provider fakes
# --------------------------------------------------------------------------------------------


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
            metadata_hints=SourceMetadataHints(canonical_url=fetched.final_url),
            quality=ExtractionQuality(
                character_count=sum(len(paragraph) for paragraph in paragraphs),
                paragraph_count=len(paragraphs),
            ),
        )


@dataclass(frozen=True, slots=True)
class RecordedModelCall:
    """One call made to :class:`FakeModelRouter`, kept so a test can assert on it."""

    task_class: ModelTaskClass
    prompt_id: str
    prompt_version: str
    output_type: type[BaseModel]
    variables: Mapping[str, object]


class FakeModelRouter:
    """A model router that returns scripted outputs and records every call.

    Enqueue a Pydantic instance, a mapping to validate against the requested schema, or an
    exception to raise. That covers the three cases application code has to handle: a good answer,
    an answer that does not fit its schema (which surfaces as
    :class:`~debate_core.application.errors.InvalidModelOutput`), and a model that cannot be
    reached.

    The replay router that plays back *recorded* model responses is a different thing and belongs
    to v1-e05-t03-fake-replay-models; this one is for unit tests that only need a model to say
    something specific.
    """

    def __init__(
        self,
        responses: Sequence[BaseModel | Mapping[str, object] | Exception] = (),
        *,
        model_id: str = "fake-model",
        clock: Clock | None = None,
        latency_ms: float = 1.0,
    ) -> None:
        self._responses: deque[BaseModel | Mapping[str, object] | Exception] = deque(responses)
        self._model_id = model_id
        self._clock: Clock = clock if clock is not None else FixedClock()
        self._latency_ms = latency_ms
        self.calls: list[RecordedModelCall] = []
        """Every invocation, in order, for assertions about routing and prompt versions."""

    def enqueue(self, response: BaseModel | Mapping[str, object] | Exception) -> None:
        """Add one more scripted response to the end of the queue."""
        self._responses.append(response)

    async def invoke[OutputT: BaseModel](
        self,
        *,
        task_class: ModelTaskClass,
        prompt_id: str,
        prompt_version: str,
        output_type: type[OutputT],
        variables: Mapping[str, object] | None = None,
    ) -> ModelInvocation[OutputT]:
        self.calls.append(
            RecordedModelCall(
                task_class=task_class,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                output_type=output_type,
                variables=dict(variables or {}),
            )
        )
        if not self._responses:
            raise ProviderUnavailable(
                "fake-model-router",
                f"no scripted response left for prompt {prompt_id}@{prompt_version}",
            )
        scripted = self._responses.popleft()
        if isinstance(scripted, Exception):
            raise scripted
        output = self._coerce(scripted, output_type, prompt_id, prompt_version)
        return ModelInvocation(
            output=output,
            metadata=ModelInvocationMetadata(
                task_class=task_class,
                model_id=self._model_id,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                latency_ms=self._latency_ms,
                invoked_at=self._clock.now(),
            ),
        )

    def _coerce[OutputT: BaseModel](
        self,
        scripted: BaseModel | Mapping[str, object],
        output_type: type[OutputT],
        prompt_id: str,
        prompt_version: str,
    ) -> OutputT:
        """Turn a scripted response into an instance of the requested schema, or fail like a model."""
        if isinstance(scripted, output_type):
            return scripted
        if isinstance(scripted, BaseModel):
            raise InvalidModelOutput(
                prompt_id,
                prompt_version,
                f"scripted a {type(scripted).__name__} where {output_type.__name__} was requested",
                model_id=self._model_id,
            )
        try:
            return output_type.model_validate(dict(scripted))
        except ValidationError as error:
            raise InvalidModelOutput(
                prompt_id, prompt_version, str(error), model_id=self._model_id
            ) from error


# --------------------------------------------------------------------------------------------
# Ambient-dependency fakes
# --------------------------------------------------------------------------------------------


class FixedClock:
    """A clock that stays where it is put.

    By default every `now()` returns the same instant. Give it a `step` and each read advances by
    that much, which is how a test gives a sequence of records distinct, predictable timestamps
    without sleeping.
    """

    def __init__(self, start: datetime = FAKE_EPOCH, *, step: timedelta = timedelta(0)) -> None:
        self._moment = _require_aware(start)
        self._step = step

    def now(self) -> datetime:
        moment = self._moment
        self._moment = moment + self._step
        return moment

    def advance(self, delta: timedelta) -> datetime:
        """Move the clock forward by `delta` and return the new instant."""
        self._moment = self._moment + delta
        return self._moment

    def set(self, moment: datetime) -> None:
        """Move the clock to an exact instant, which must be timezone-aware."""
        self._moment = _require_aware(moment)


def _require_aware(moment: datetime) -> datetime:
    """Reject naive datetimes here, where the mistake is easy to see, not at model validation."""
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(f"a clock instant must be timezone-aware, got {moment!r}")
    return moment.astimezone(UTC)


class SequentialIdGenerator:
    """Deterministic, readable ULIDs: `0CARD000000000000000000001`, `…2`, `…3`.

    Real ULIDs are time-ordered and random, which makes a golden file impossible to check in.
    These are valid ULIDs — 26 Crockford-base32 characters starting below `8` — that count up, and
    an optional prefix labels which generator minted them when a test wires up several.
    """

    def __init__(self, prefix: str = "", *, start: int = 1) -> None:
        if len(prefix) > 24:
            raise ValueError(f"prefix must be at most 24 characters, got {len(prefix)}")
        unusable = sorted(set(prefix) - set(CROCKFORD_BASE32_ALPHABET))
        if unusable:
            raise ValueError(
                f"prefix must use the Crockford base32 alphabet ({CROCKFORD_BASE32_ALPHABET}); "
                f"cannot use {''.join(unusable)}"
            )
        self._prefix = prefix
        self._next = start
        self._digits = 25 - len(prefix)

    def new_id(self) -> str:
        counter = self._next
        self._next += 1
        rendered = str(counter)
        if len(rendered) > self._digits:
            raise ValueError(f"counter {counter} does not fit in {self._digits} characters")
        return f"0{self._prefix}{rendered.zfill(self._digits)}"


# --------------------------------------------------------------------------------------------
# Assembling the whole set
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakePorts:
    """One of every port, wired to its fake.

    The fields are annotated with the *Protocols*, not with the fake classes. That is deliberate,
    and it is what checks acceptance criterion ac4 of this task: if a fake drifts from its port —
    a renamed argument, a dropped method, a changed return type — pyright fails on the
    corresponding line of :func:`build_fake_ports`, in this package, rather than somewhere in a
    test months later.

    A test that needs a fake's own helpers (`FakeArticleFetcher.add`,
    `InMemorySnapshotStore.corrupt`) builds that fake directly instead of reaching through here.
    """

    article_repository: ArticleRepository
    snapshot_store: SnapshotStore
    card_repository: CardRepository
    search_repository: SearchRepository
    search_provider: SearchProvider
    article_fetcher: ArticleFetcher
    content_extractor: ContentExtractor
    model_router: ModelRouter
    clock: Clock
    id_generator: IdGenerator


def build_fake_ports(
    *,
    clock: FixedClock | None = None,
    id_generator: SequentialIdGenerator | None = None,
) -> FakePorts:
    """Build one fake for every port, sharing one clock so timestamps line up across them."""
    shared_clock = clock if clock is not None else FixedClock()
    return FakePorts(
        article_repository=InMemoryArticleRepository(),
        snapshot_store=InMemorySnapshotStore(),
        card_repository=InMemoryCardRepository(),
        search_repository=InMemorySearchRepository(),
        search_provider=FakeSearchProvider(),
        article_fetcher=FakeArticleFetcher(clock=shared_clock),
        content_extractor=FakeContentExtractor(),
        model_router=FakeModelRouter(clock=shared_clock),
        clock=shared_clock,
        id_generator=id_generator if id_generator is not None else SequentialIdGenerator(),
    )


def build_fake_caselist_repository() -> CaselistRepository:
    """Build the in-memory :class:`CaselistRepository` (v1-e30-t02), typed as the port.

    The annotation is the point, exactly as it is on :class:`FakePorts`: pyright strict checks the
    fake against the Protocol here, in this package, so a method renamed on the port or an
    argument dropped from the fake fails at this line rather than in an importer test months
    later.

    It is built separately from :func:`build_fake_ports` because a caselist repository is not one
    of the ten ports every service takes — only the E30 importers, the E31 parser and the E32
    reports reach for it, and they ask for it by name.
    """
    return InMemoryCaselistRepository()

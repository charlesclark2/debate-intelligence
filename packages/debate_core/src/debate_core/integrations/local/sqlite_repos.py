"""The SQLite repositories: articles and their snapshots, cards, searches and their rankings.

Four adapters for the four persistence ports, all sharing one
:class:`~debate_core.integrations.local.sqlite_db.SqliteDatabase`. They are V1's system of record
for everything that is not snapshot bytes, and the local counterpart of the DynamoDB `AppTable`
that replaces them in V2 (architecture proposal §7).

## How an entity is stored

Each row holds the entity as `document` — the JSON its own Pydantic model produced — plus a few
key columns copied out beside it. The document is the value of record and is revalidated through
the model on the way out, so a row that no longer fits the entity it claims to be is reported
(:class:`CorruptRecordError`) rather than returned half-built. The key columns exist only so
SQLite can find and order rows; nothing reads a value from them.

Storing the whole entity as JSON rather than a column per field is what keeps the local schema and
the cloud one the same shape. A field added to a model in E03 or E04 needs no migration here and
no new attribute in DynamoDB; only a *new way of finding* records needs either.

## What these adapters own, and what they do not

They own `revision`, and nothing else on an entity. A successful write returns the entity with
`revision` incremented, and the caller keeps that instance. They never touch `created_at` or
`updated_at`: those are provenance and come from the `Clock` port in the calling service, so a
test's timestamps stay deterministic and a record does not silently acquire the time zone of
whichever machine wrote it.

## Listings and cursors

Every listing is newest first — `created_at` descending, then the entity id descending — which is
a total order because ids are ULIDs, and that is what makes a page boundary reproducible. The
timestamp columns are written in a fixed-width UTC form (:func:`sort_timestamp`) so SQLite's
lexicographic comparison *is* chronological comparison.

A cursor is `"<kind>:<id of the last row on the previous page>"`, deliberately the same scheme
`debate_core.testing.fakes` mints, so one contract suite (v1-e02-t04-repo-contract-tests) can hold
the fakes and these adapters to the same behaviour, down to which cursors are rejected. It is
opaque by contract: a cursor from another listing is an
:class:`~debate_core.application.errors.InvalidCursor`, never a silent "start from the beginning".

## Errors

`sqlite3` exceptions are translated here and never cross a port: a missing row is
:class:`~debate_core.application.errors.NotFound`, a primary-key collision is
:class:`~debate_core.application.errors.AlreadyExists`, a failed revision check is
:class:`~debate_core.application.errors.RevisionMismatch`. A `sqlite3.Error` reaching a service
would be a bug in this module.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final, cast

from debate_core.application.errors import (
    AlreadyExists,
    DomainError,
    InvalidCursor,
    NotFound,
    RevisionMismatch,
)
from debate_core.application.ports import DEFAULT_PAGE_SIZE, Page
from debate_core.domain import (
    Article,
    Card,
    DomainModel,
    Search,
    SearchResult,
    SourceSnapshot,
)
from debate_core.integrations.local.sqlite_db import SqliteDatabase

__all__ = [
    "CorruptRecordError",
    "SqliteArticleRepository",
    "SqliteCardRepository",
    "SqliteSearchRepository",
    "sort_timestamp",
]

# `Page` and `DEFAULT_PAGE_SIZE` are the ports module's value object and its default page size,
# not the Protocols themselves. Importing them is how an adapter returns what its port promises;
# what an adapter must not do is subclass a Protocol, which would make conformance nominal.

#: Fixed-width UTC rendering for the sort columns, so lexicographic order is chronological order.
_SORT_TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%S.%f"


class CorruptRecordError(DomainError):
    """A stored row does not validate as the entity it is filed as.

    Only reachable through hand-editing, a failing disk, or a schema change that shipped without a
    migration. It is a :class:`~debate_core.application.errors.DomainError` so that the CLI's
    existing handler reports it, and it is raised rather than worked around for the same reason
    :class:`~debate_core.application.errors.BlobIntegrityError` is: a card built from a record the
    platform cannot read is a card no one should rely on.
    """

    def __init__(self, entity: str, key: str, reason: str) -> None:
        self.entity = entity
        """What was being read, e.g. `"Card"`."""
        self.key = key
        """The key of the unreadable record."""
        self.reason = reason
        """What validation objected to."""
        super().__init__(f"stored {entity} {key} is not readable as a {entity}: {reason}")


def sort_timestamp(value: datetime) -> str:
    """Render a timestamp for a sort column: UTC, fixed width, microseconds always present.

    Fixed width is the whole point. `datetime.isoformat()` omits microseconds when they are zero,
    so two timestamps one microsecond apart would differ in length and compare in the wrong order
    as text. The entity's own ISO 8601 spelling is preserved in `document`; this is only a key.
    """
    return value.astimezone(UTC).strftime(_SORT_TIMESTAMP_FORMAT)


def _decode[ModelT: DomainModel](model: type[ModelT], document: str, entity: str, key: str) -> ModelT:
    """Validate one stored document back into its entity, or report the row as unreadable."""
    try:
        return model.model_validate_json(document)
    except ValueError as invalid:
        raise CorruptRecordError(entity, key, str(invalid)) from invalid


def _document_of(entity: DomainModel) -> str:
    """Render an entity for storage, exactly as its own model serializes it."""
    return entity.model_dump_json()


def _encode_cursor(kind: str, entity_id: str) -> str:
    return f"{kind}:{entity_id}"


def _decode_cursor(cursor: str, kind: str) -> str:
    """Return the entity id a cursor points at, or reject a cursor this listing did not mint."""
    prefix = f"{kind}:"
    if not cursor.startswith(prefix):
        raise InvalidCursor(cursor)
    return cursor[len(prefix) :]


class _EntityTable[EntityT: DomainModel]:
    """The handful of facts a listing needs about one table, so paging is written once.

    Listings differ only in which table they read, which column identifies a row, which column
    they filter on and what the cursor kind is called. Holding those four facts here keeps the
    keyset query — the part that is easy to get subtly wrong — in one place rather than in five.
    """

    def __init__(
        self,
        *,
        name: str,
        id_column: str,
        model: type[EntityT],
        entity_name: str,
        cursor_kind: str,
    ) -> None:
        self.name = name
        self.id_column = id_column
        self.model = model
        self.entity_name = entity_name
        self.cursor_kind = cursor_kind

    def page(
        self,
        connection: sqlite3.Connection,
        *,
        filter_column: str,
        filter_value: str,
        limit: int,
        cursor: str | None,
    ) -> Page[EntityT]:
        """Read one page of rows matching `filter_column = filter_value`, newest first.

        Table and column names are interpolated into the SQL because they are this module's own
        literals, chosen by the repository and never by a caller; every value is a bound parameter.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")

        parameters: list[object] = [filter_value]
        keyset = ""
        if cursor is not None:
            last_id = _decode_cursor(cursor, self.cursor_kind)
            anchor = connection.execute(
                f"SELECT created_at FROM {self.name} WHERE {self.id_column} = ? AND {filter_column} = ?",
                (last_id, filter_value),
            ).fetchone()
            if anchor is None:
                # Either a cursor from another listing or a row that has since been deleted.
                # Both mean this cursor cannot name a page boundary any more.
                raise InvalidCursor(cursor)
            keyset = f"AND (created_at, {self.id_column}) < (?, ?) "
            parameters += [anchor["created_at"], last_id]

        # One row more than asked for: if it comes back, there is another page.
        parameters.append(limit + 1)
        rows = connection.execute(
            f"SELECT {self.id_column}, document FROM {self.name} "
            f"WHERE {filter_column} = ? {keyset}"
            f"ORDER BY created_at DESC, {self.id_column} DESC LIMIT ?",
            parameters,
        ).fetchall()

        window = rows[:limit]
        items = tuple(
            _decode(
                self.model,
                cast("str", row["document"]),
                self.entity_name,
                cast("str", row[self.id_column]),
            )
            for row in window
        )
        next_cursor = (
            _encode_cursor(self.cursor_kind, cast("str", window[-1][self.id_column]))
            if len(rows) > limit and window
            else None
        )
        return Page(items=items, next_cursor=next_cursor)


_ARTICLES = _EntityTable(
    name="articles",
    id_column="article_id",
    model=Article,
    entity_name="Article",
    cursor_kind="article",
)
_CARDS = _EntityTable(name="cards", id_column="card_id", model=Card, entity_name="Card", cursor_kind="card")
_SEARCHES = _EntityTable(
    name="searches",
    id_column="search_id",
    model=Search,
    entity_name="Search",
    cursor_kind="search",
)


# --------------------------------------------------------------------------------------------
# Articles, and the snapshots taken of them
# --------------------------------------------------------------------------------------------


class SqliteArticleRepository:
    """Articles in `articles`, and snapshot metadata in `source_snapshots`.

    Snapshot *bytes* are not here: they go to
    :class:`~debate_core.integrations.local.fs_blob_store.FsSnapshotStore` under their digest,
    and the record here holds the keys. A snapshot is article-side metadata — which article, when
    retrieved, under which extractor and normalizer versions — so it is stored beside the article
    it describes, exactly as the port describes it.

    `save` is an upsert and last-writer-wins: an article is a shared description of a public source
    that any retrieval may refresh. Snapshots are the opposite — immutable, one per retrieval — and
    saving one whose id is stored is a conflict rather than an update.
    """

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def get(self, article_id: str) -> Article:
        row = self._database.connection.execute(
            "SELECT document FROM articles WHERE article_id = ?", (article_id,)
        ).fetchone()
        if row is None:
            raise NotFound("Article", article_id)
        return _decode(Article, cast("str", row["document"]), "Article", article_id)

    async def find_by_canonical_url(self, canonical_url: str) -> Article | None:
        """Return the article stored under this URL, matched byte for byte.

        The port does not make the canonical URL unique, so the oldest matching article wins: it is
        the one other records already point at, and picking it makes the answer stable rather than
        dependent on which row SQLite happened to visit first.
        """
        row = self._database.connection.execute(
            "SELECT article_id, document FROM articles WHERE canonical_url = ? "
            "ORDER BY created_at ASC, article_id ASC LIMIT 1",
            (canonical_url,),
        ).fetchone()
        if row is None:
            return None
        return _decode(Article, cast("str", row["document"]), "Article", cast("str", row["article_id"]))

    async def save(self, article: Article) -> Article:
        """Insert or update the article, returning it with `revision` incremented."""
        with self._database.transaction() as connection:
            stored = connection.execute(
                "SELECT revision FROM articles WHERE article_id = ?", (article.article_id,)
            ).fetchone()
            revision = 1 if stored is None else int(stored["revision"]) + 1
            saved = article.evolve(revision=revision)
            connection.execute(
                "INSERT INTO articles "
                "(article_id, canonical_url, owner_id, organization_id, created_at, revision, document) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (article_id) DO UPDATE SET "
                "canonical_url = excluded.canonical_url, owner_id = excluded.owner_id, "
                "organization_id = excluded.organization_id, created_at = excluded.created_at, "
                "revision = excluded.revision, document = excluded.document",
                (
                    saved.article_id,
                    saved.canonical_url,
                    saved.owner_id,
                    saved.organization_id,
                    sort_timestamp(saved.created_at),
                    saved.revision,
                    _document_of(saved),
                ),
            )
        return saved

    async def delete(self, article_id: str) -> None:
        with self._database.transaction() as connection:
            deleted = connection.execute("DELETE FROM articles WHERE article_id = ?", (article_id,)).rowcount
        if deleted == 0:
            raise NotFound("Article", article_id)

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Article]:
        return _ARTICLES.page(
            self._database.connection,
            filter_column="owner_id",
            filter_value=owner_id,
            limit=limit,
            cursor=cursor,
        )

    async def save_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        """Store one retrieval's metadata. Snapshots are immutable, so a repeat id is a conflict."""
        try:
            with self._database.transaction() as connection:
                connection.execute(
                    "INSERT INTO source_snapshots "
                    "(snapshot_id, article_id, owner_id, organization_id, canonical_url, "
                    "retrieved_at, created_at, raw_blob_key, normalized_blob_key, document) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        snapshot.snapshot_id,
                        snapshot.article_id,
                        snapshot.owner_id,
                        snapshot.organization_id,
                        snapshot.canonical_url,
                        sort_timestamp(snapshot.retrieved_at),
                        sort_timestamp(snapshot.created_at),
                        snapshot.raw_blob_key,
                        snapshot.normalized_blob_key,
                        _document_of(snapshot),
                    ),
                )
        except sqlite3.IntegrityError as collision:
            raise AlreadyExists("SourceSnapshot", snapshot.snapshot_id) from collision
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> SourceSnapshot:
        row = self._database.connection.execute(
            "SELECT document FROM source_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise NotFound("SourceSnapshot", snapshot_id)
        return _decode(SourceSnapshot, cast("str", row["document"]), "SourceSnapshot", snapshot_id)

    async def list_snapshots(self, article_id: str) -> tuple[SourceSnapshot, ...]:
        """Every snapshot of one article, newest retrieval first. Unpaginated, as the port says."""
        rows = self._database.connection.execute(
            "SELECT snapshot_id, document FROM source_snapshots WHERE article_id = ? "
            "ORDER BY retrieved_at DESC, snapshot_id DESC",
            (article_id,),
        ).fetchall()
        return tuple(
            _decode(
                SourceSnapshot,
                cast("str", row["document"]),
                "SourceSnapshot",
                cast("str", row["snapshot_id"]),
            )
            for row in rows
        )


# --------------------------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------------------------


class SqliteCardRepository:
    """Cards in `cards`, written under an optimistic-concurrency check.

    A card is the one entity two writers really do race for: a student moves an underline while a
    reprocessing job writes a model's suggestion to the same card. Every update therefore states
    the revision it read, and :meth:`save` applies it with a conditional `UPDATE … WHERE card_id = ?
    AND revision = ?` — one statement, so there is no window between checking the revision and
    writing under it (architecture proposal §7).

    Creating and updating are separate methods, so neither a silent overwrite nor an accidental
    create is expressible.
    """

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def get(self, card_id: str) -> Card:
        card = await self.find(card_id)
        if card is None:
            raise NotFound("Card", card_id)
        return card

    async def find(self, card_id: str) -> Card | None:
        row = self._database.connection.execute(
            "SELECT document FROM cards WHERE card_id = ?", (card_id,)
        ).fetchone()
        if row is None:
            return None
        return _decode(Card, cast("str", row["document"]), "Card", card_id)

    async def create(self, card: Card) -> Card:
        """Store a new card at revision 1, refusing to overwrite one that is already stored."""
        saved = card.evolve(revision=1)
        try:
            with self._database.transaction() as connection:
                connection.execute(
                    "INSERT INTO cards "
                    "(card_id, owner_id, organization_id, article_id, snapshot_id, created_at, "
                    "revision, document) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        saved.card_id,
                        saved.owner_id,
                        saved.organization_id,
                        saved.article_id,
                        saved.snapshot_id,
                        sort_timestamp(saved.created_at),
                        saved.revision,
                        _document_of(saved),
                    ),
                )
        except sqlite3.IntegrityError as collision:
            raise AlreadyExists("Card", card.card_id) from collision
        return saved

    async def save(self, card: Card, *, expected_revision: int) -> Card:
        """Update a card whose stored revision is still `expected_revision`.

        Raises :class:`~debate_core.application.errors.RevisionMismatch` carrying both revisions
        when it moved, and :class:`~debate_core.application.errors.NotFound` when the card is gone.
        Nothing is written in either case.
        """
        saved = card.evolve(revision=expected_revision + 1)
        with self._database.transaction() as connection:
            updated = connection.execute(
                "UPDATE cards SET owner_id = ?, organization_id = ?, article_id = ?, "
                "snapshot_id = ?, created_at = ?, revision = ?, document = ? "
                "WHERE card_id = ? AND revision = ?",
                (
                    saved.owner_id,
                    saved.organization_id,
                    saved.article_id,
                    saved.snapshot_id,
                    sort_timestamp(saved.created_at),
                    saved.revision,
                    _document_of(saved),
                    saved.card_id,
                    expected_revision,
                ),
            ).rowcount
            # The conditional UPDATE is the check: no separate read can slip between them.
            if updated != 1:
                _raise_write_conflict(connection, card.card_id, expected_revision)
        return saved

    async def delete(self, card_id: str, *, expected_revision: int) -> None:
        """Delete a card whose stored revision is `expected_revision`, or report why not."""
        with self._database.transaction() as connection:
            deleted = connection.execute(
                "DELETE FROM cards WHERE card_id = ? AND revision = ?",
                (card_id, expected_revision),
            ).rowcount
            if deleted != 1:
                _raise_write_conflict(connection, card_id, expected_revision)

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Card]:
        return _CARDS.page(
            self._database.connection,
            filter_column="owner_id",
            filter_value=owner_id,
            limit=limit,
            cursor=cursor,
        )

    async def list_by_article(
        self, article_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Card]:
        return _CARDS.page(
            self._database.connection,
            filter_column="article_id",
            filter_value=article_id,
            limit=limit,
            cursor=cursor,
        )


def _raise_write_conflict(connection: sqlite3.Connection, card_id: str, expected_revision: int) -> None:
    """Explain why a guarded write matched no row: the card is gone, or its revision moved."""
    stored = connection.execute("SELECT revision FROM cards WHERE card_id = ?", (card_id,)).fetchone()
    if stored is None:
        raise NotFound("Card", card_id)
    raise RevisionMismatch("Card", card_id, expected_revision, int(stored["revision"]))


# --------------------------------------------------------------------------------------------
# Searches and their rankings
# --------------------------------------------------------------------------------------------


class SqliteSearchRepository:
    """Searches in `searches`, and their rankings in `search_results`.

    A ranking is stored as a set rather than a row at a time: an order is only meaningful as a
    whole, so :meth:`save_results` replaces all of it inside one transaction and a re-run cannot
    leave half an old order behind.
    """

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def get(self, search_id: str) -> Search:
        row = self._database.connection.execute(
            "SELECT document FROM searches WHERE search_id = ?", (search_id,)
        ).fetchone()
        if row is None:
            raise NotFound("Search", search_id)
        return _decode(Search, cast("str", row["document"]), "Search", search_id)

    async def save(self, search: Search) -> Search:
        with self._database.transaction() as connection:
            stored = connection.execute(
                "SELECT revision FROM searches WHERE search_id = ?", (search.search_id,)
            ).fetchone()
            revision = 1 if stored is None else int(stored["revision"]) + 1
            saved = search.evolve(revision=revision)
            connection.execute(
                "INSERT INTO searches "
                "(search_id, owner_id, organization_id, created_at, revision, document) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (search_id) DO UPDATE SET owner_id = excluded.owner_id, "
                "organization_id = excluded.organization_id, created_at = excluded.created_at, "
                "revision = excluded.revision, document = excluded.document",
                (
                    saved.search_id,
                    saved.owner_id,
                    saved.organization_id,
                    sort_timestamp(saved.created_at),
                    saved.revision,
                    _document_of(saved),
                ),
            )
        return saved

    async def save_results(self, search_id: str, results: Sequence[SearchResult]) -> None:
        """Replace one search's whole ranking.

        The caller's mistakes are checked before anything is written, so a rejected call leaves the
        stored ranking exactly as it was.
        """
        _check_results_belong_to(search_id, results)
        with self._database.transaction() as connection:
            if (
                connection.execute("SELECT 1 FROM searches WHERE search_id = ?", (search_id,)).fetchone()
                is None
            ):
                raise NotFound("Search", search_id)
            connection.execute("DELETE FROM search_results WHERE search_id = ?", (search_id,))
            connection.executemany(
                'INSERT INTO search_results (search_id, article_id, "rank", document) VALUES (?, ?, ?, ?)',
                [(search_id, result.article_id, result.rank, _document_of(result)) for result in results],
            )

    async def list_results(self, search_id: str) -> tuple[SearchResult, ...]:
        """One search's results by ascending rank; empty for a search that stored none."""
        connection = self._database.connection
        if connection.execute("SELECT 1 FROM searches WHERE search_id = ?", (search_id,)).fetchone() is None:
            raise NotFound("Search", search_id)
        rows = connection.execute(
            'SELECT article_id, document FROM search_results WHERE search_id = ? ORDER BY "rank" ASC',
            (search_id,),
        ).fetchall()
        return tuple(
            _decode(
                SearchResult,
                cast("str", row["document"]),
                "SearchResult",
                f"{search_id}/{cast('str', row['article_id'])}",
            )
            for row in rows
        )

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Search]:
        return _SEARCHES.page(
            self._database.connection,
            filter_column="owner_id",
            filter_value=owner_id,
            limit=limit,
            cursor=cursor,
        )


def _check_results_belong_to(search_id: str, results: Sequence[SearchResult]) -> None:
    """Reject a ranking that is not a ranking of this search — all caller bugs, not storage states.

    The third check has no counterpart in the in-memory fake, which would store two results for one
    article. The schema's primary key refuses them, and a raw `sqlite3.IntegrityError` crossing a
    port would be worse than a named `ValueError`, so the rule the domain already states — one
    search holds at most one result per article — is checked here explicitly.
    """
    foreign = [result.article_id for result in results if result.search_id != search_id]
    if foreign:
        raise ValueError(f"results for another search were given for {search_id}: {foreign}")
    ranks = [result.rank for result in results]
    if len(set(ranks)) != len(ranks):
        raise ValueError(f"two results share a rank in search {search_id}: {sorted(ranks)}")
    articles = [result.article_id for result in results]
    if len(set(articles)) != len(articles):
        raise ValueError(f"two results name the same article in search {search_id}: {sorted(articles)}")

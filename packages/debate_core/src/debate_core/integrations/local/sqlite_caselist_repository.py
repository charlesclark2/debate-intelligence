"""The SQLite side of the caselist store: snapshots, sources, disclosures and camp files.

V1's implementation of :class:`~debate_core.application.ports.caselist.CaselistRepository`, on
the same :class:`~debate_core.integrations.local.sqlite_db.SqliteDatabase` the other four local
repositories share. V2 replaces it with DynamoDB and no importer changes.

It is held to exactly the expectations
`packages/debate_core/tests/application/test_caselist_fake_repository.py` holds the in-memory
fake to — that suite says so in its own docstring — because the importer is developed against
the fake and run against this.

## The one piece of arithmetic worth reading

`put_source` **widens** rather than overwrites. Weekly archives are cumulative, so the same file
arrives again every week until the team takes it down, and the answer to "which weeks was this
file up?" is a range that has to survive being written to out of order: importing 09-15 and then
09-01 must leave `first_seen=09-01, last_seen=09-15`, not the other way round. The read and the
widening write happen inside one `BEGIN IMMEDIATE` transaction, so two importers cannot each read
the old range and each write half of it.

What it will not do is overwrite a stored record with one that differs. A different size or
format under a stored SHA-256 is a real contradiction; a different origin is refused only as a
defence, since the importers link to the existing record instead. Both raise
:class:`~debate_core.application.errors.Conflict`, for the reasons
:meth:`~debate_core.application.ports.caselist.CaselistRepository.put_source` gives.

## Ordering and cursors

Listings are newest snapshot first, then ascending by their remaining key parts. That is two
directions at once, so each row carries a `sort_key` whose plain ascending order is the
documented order — the snapshot date inverted, then the rest, joined by U+0001. A page boundary
is one `sort_key > ?` against the anchor row, which is what keeps pagination reproducible.

A cursor is `"<kind>:<natural key>"`, minted exactly as
:mod:`debate_core.testing.fakes` mints it, so a cursor is opaque but the two implementations
reject the same ones: a cursor from another listing, or one naming a row that has since gone, is
an :class:`~debate_core.application.errors.InvalidCursor` rather than a silent restart.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import cast

from debate_core.application.errors import Conflict, InvalidCursor, NotFound
from debate_core.application.ports import DEFAULT_PAGE_SIZE, Page
from debate_core.domain.caselist import (
    ArchiveSnapshot,
    CampFile,
    Disclosure,
    Event,
    SourceDocument,
)
from debate_core.integrations.local.sqlite_db import SqliteDatabase
from debate_core.integrations.local.sqlite_repos import CorruptRecordError

__all__ = ["SORT_KEY_SEPARATOR", "SqliteCaselistRepository", "descending_snapshot", "sort_key_for"]

SORT_KEY_SEPARATOR = "\u0001"
"""What joins the parts of a `sort_key`.

U+0001 rather than a printable character: it sorts below every character that can appear in a
caselist slug, a school name, a team code or an archive path, so `a\\x01b` never collides with a
path that happens to contain the separator.
"""

#: Cursor kinds, matching the ones `debate_core.testing.fakes` mints for the same listings.
_SOURCE_CURSOR_KIND = "caselist-source"
_DISCLOSURE_CURSOR_KIND = "disclosure"
_CAMP_FILE_CURSOR_KIND = "camp-file"


def descending_snapshot(day: date) -> str:
    """Render a snapshot date so that ascending text order is newest-first date order.

    `date.max - day` reflected back onto the calendar. The listings order by snapshot descending
    and by everything else ascending, and one ascending `sort_key` cannot hold both directions
    unless one of them is inverted first.
    """
    return (date.min + (date.max - day)).isoformat()


def sort_key_for(*parts: str) -> str:
    """Join the parts of a listing's order into one ascending text key."""
    return SORT_KEY_SEPARATOR.join(parts)


class SqliteCaselistRepository:
    """Imported caselist and camp-file records in SQLite.

    Built by the composition root from the shared database, exactly as the other local
    repositories are::

        database = SqliteDatabase.open(settings.storage.data_dir)
        caselist = SqliteCaselistRepository(database)
    """

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    # ------------------------------------------------------------------------------------
    # Archive snapshots
    # ------------------------------------------------------------------------------------

    async def upsert_snapshot(self, snapshot: ArchiveSnapshot) -> ArchiveSnapshot:
        """Insert or replace one archive's record. Re-importing rewrites the same row."""
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO caselist_snapshots (caselist, snapshot, archive_sha256, document) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (caselist, snapshot) DO UPDATE SET "
                "archive_sha256 = excluded.archive_sha256, document = excluded.document",
                (
                    snapshot.caselist,
                    snapshot.snapshot.isoformat(),
                    snapshot.archive_sha256,
                    snapshot.model_dump_json(),
                ),
            )
        return snapshot

    async def get_snapshot(self, caselist: str, snapshot: date) -> ArchiveSnapshot:
        found = await self.find_snapshot(caselist, snapshot)
        if found is None:
            raise NotFound("ArchiveSnapshot", f"{caselist}/{snapshot.isoformat()}")
        return found

    async def find_snapshot(self, caselist: str, snapshot: date) -> ArchiveSnapshot | None:
        row = self._database.connection.execute(
            "SELECT document FROM caselist_snapshots WHERE caselist = ? AND snapshot = ?",
            (caselist, snapshot.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return _decode(
            ArchiveSnapshot,
            cast("str", row["document"]),
            "ArchiveSnapshot",
            f"{caselist}/{snapshot.isoformat()}",
        )

    async def latest_snapshot(self, caselist: str) -> ArchiveSnapshot | None:
        """The newest archive imported for this caselist, which is what an import orders against."""
        row = self._database.connection.execute(
            "SELECT snapshot, document FROM caselist_snapshots WHERE caselist = ? "
            "ORDER BY snapshot DESC LIMIT 1",
            (caselist,),
        ).fetchone()
        if row is None:
            return None
        return _decode(
            ArchiveSnapshot,
            cast("str", row["document"]),
            "ArchiveSnapshot",
            f"{caselist}/{cast('str', row['snapshot'])}",
        )

    async def list_snapshots(self, caselist: str) -> tuple[ArchiveSnapshot, ...]:
        """Every archive for one caselist, newest first. Unpaginated: one a week for one season."""
        rows = self._database.connection.execute(
            "SELECT snapshot, document FROM caselist_snapshots WHERE caselist = ? ORDER BY snapshot DESC",
            (caselist,),
        ).fetchall()
        return tuple(
            _decode(
                ArchiveSnapshot,
                cast("str", row["document"]),
                "ArchiveSnapshot",
                f"{caselist}/{cast('str', row['snapshot'])}",
            )
            for row in rows
        )

    # ------------------------------------------------------------------------------------
    # Source documents
    # ------------------------------------------------------------------------------------

    async def put_source(self, source: SourceDocument) -> SourceDocument:
        """Store a source, or widen the snapshot range of the one already filed under its hash.

        The read and the write are one transaction, because the widening depends on what is
        already there. A second file claiming the same hash with different bytes is a
        :class:`~debate_core.application.errors.Conflict`, never an overwrite.
        """
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT document FROM caselist_sources WHERE sha256 = ?", (source.sha256,)
            ).fetchone()
            stored = (
                None
                if row is None
                else _decode(SourceDocument, cast("str", row["document"]), "SourceDocument", source.sha256)
            )
            to_store = source if stored is None else _widened(stored, source)
            connection.execute(
                "INSERT INTO caselist_sources (sha256, caselist, byte_size, source_format, origin, "
                "first_seen_snapshot, last_seen_snapshot, sort_key, document) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (sha256) DO UPDATE SET "
                "first_seen_snapshot = excluded.first_seen_snapshot, "
                "last_seen_snapshot = excluded.last_seen_snapshot, "
                "sort_key = excluded.sort_key, document = excluded.document",
                (
                    to_store.sha256,
                    to_store.caselist,
                    to_store.byte_size,
                    str(to_store.source_format),
                    str(to_store.origin),
                    to_store.first_seen_snapshot.isoformat(),
                    to_store.last_seen_snapshot.isoformat(),
                    _source_sort_key(to_store),
                    to_store.model_dump_json(),
                ),
            )
        return to_store

    async def get_source(self, sha256: str) -> SourceDocument:
        found = await self.find_source(sha256)
        if found is None:
            raise NotFound("SourceDocument", sha256)
        return found

    async def find_source(self, sha256: str) -> SourceDocument | None:
        """The deduplication lookup every import performs per file; absence is the ordinary answer."""
        row = self._database.connection.execute(
            "SELECT document FROM caselist_sources WHERE sha256 = ?", (sha256,)
        ).fetchone()
        if row is None:
            return None
        return _decode(SourceDocument, cast("str", row["document"]), "SourceDocument", sha256)

    async def list_sources(
        self,
        *,
        caselist: str | None = None,
        snapshot: date | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[SourceDocument]:
        """Newest snapshot first, then by hash ascending.

        `snapshot` selects the documents that were *present* in that week — whose first/last seen
        range covers it — which is the set the publisher uploads for one snapshot.
        """
        conditions: list[str] = []
        parameters: list[object] = []
        if caselist is not None:
            conditions.append("caselist = ?")
            parameters.append(caselist)
        if snapshot is not None:
            conditions.append("first_seen_snapshot <= ? AND last_seen_snapshot >= ?")
            parameters += [snapshot.isoformat(), snapshot.isoformat()]

        rows = self._page(
            table="caselist_sources",
            key_column="sha256",
            conditions=conditions,
            parameters=parameters,
            cursor_kind=_SOURCE_CURSOR_KIND,
            limit=limit,
            cursor=cursor,
        )
        return _page_of(SourceDocument, "SourceDocument", rows, _SOURCE_CURSOR_KIND, limit)

    # ------------------------------------------------------------------------------------
    # Disclosures and camp files
    # ------------------------------------------------------------------------------------

    async def record_disclosure(self, disclosure: Disclosure) -> Disclosure:
        """Record what one archive said about one file. Idempotent by caselist, snapshot and path."""
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO caselist_disclosures (caselist, snapshot, source_path, source_sha256, "
                "school, team_code, sort_key, document) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (caselist, snapshot, source_path) DO UPDATE SET "
                "source_sha256 = excluded.source_sha256, school = excluded.school, "
                "team_code = excluded.team_code, sort_key = excluded.sort_key, "
                "document = excluded.document",
                (
                    disclosure.caselist,
                    disclosure.snapshot.isoformat(),
                    disclosure.source_path,
                    disclosure.source_sha256,
                    disclosure.school,
                    disclosure.team_code,
                    _disclosure_sort_key(disclosure),
                    disclosure.model_dump_json(),
                ),
            )
        return disclosure

    async def record_camp_file(self, camp_file: CampFile) -> CampFile:
        """Record what one OpenEv release said about one file, keyed by hash, year and event."""
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO caselist_camp_files (source_sha256, year, event, camp, file_title, "
                "snapshot, sort_key, document) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (source_sha256, year, event) DO UPDATE SET "
                "camp = excluded.camp, file_title = excluded.file_title, "
                "snapshot = excluded.snapshot, sort_key = excluded.sort_key, "
                "document = excluded.document",
                (
                    camp_file.source_sha256,
                    camp_file.year,
                    str(camp_file.event),
                    camp_file.camp,
                    camp_file.file_title,
                    camp_file.snapshot.isoformat(),
                    _camp_file_sort_key(camp_file),
                    camp_file.model_dump_json(),
                ),
            )
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
        """Newest snapshot first, then by source path ascending. Filters combine with AND."""
        conditions: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("caselist", caselist),
            ("school", school),
            ("team_code", team_code),
            ("source_sha256", source_sha256),
        ):
            if value is not None:
                conditions.append(f"{column} = ?")
                parameters.append(value)
        if snapshot is not None:
            conditions.append("snapshot = ?")
            parameters.append(snapshot.isoformat())

        rows = self._page(
            table="caselist_disclosures",
            key_column="caselist || '|' || snapshot || '|' || source_path",
            conditions=conditions,
            parameters=parameters,
            cursor_kind=_DISCLOSURE_CURSOR_KIND,
            limit=limit,
            cursor=cursor,
        )
        return _page_of(Disclosure, "Disclosure", rows, _DISCLOSURE_CURSOR_KIND, limit)

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
        """Newest snapshot first, then by title ascending. Filters combine with AND."""
        conditions: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("camp", camp),
            ("year", year),
            ("event", None if event is None else str(event)),
            ("source_sha256", source_sha256),
        ):
            if value is not None:
                conditions.append(f"{column} = ?")
                parameters.append(value)

        rows = self._page(
            table="caselist_camp_files",
            key_column="source_sha256 || '|' || year || '|' || event",
            conditions=conditions,
            parameters=parameters,
            cursor_kind=_CAMP_FILE_CURSOR_KIND,
            limit=limit,
            cursor=cursor,
        )
        return _page_of(CampFile, "CampFile", rows, _CAMP_FILE_CURSOR_KIND, limit)

    # ------------------------------------------------------------------------------------
    # Paging
    # ------------------------------------------------------------------------------------

    def _page(
        self,
        *,
        table: str,
        key_column: str,
        conditions: list[str],
        parameters: list[object],
        cursor_kind: str,
        limit: int,
        cursor: str | None,
    ) -> list[sqlite3.Row]:
        """Read one page of `table`, in `sort_key` order, starting after `cursor`.

        Table and column expressions are this module's own literals, never a caller's; every
        value is a bound parameter. One row more than asked for is read, which is how the next
        cursor knows whether there is a page after this one.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
        connection = self._database.connection
        where = f"WHERE {' AND '.join(conditions)} " if conditions else ""
        query_parameters = list(parameters)

        keyset = ""
        if cursor is not None:
            natural_key = _cursor_key(cursor, cursor_kind)
            anchor = connection.execute(
                f"SELECT sort_key FROM {table} WHERE {key_column} = ?", (natural_key,)
            ).fetchone()
            if anchor is None:
                # A cursor from another listing, or one naming a row that has since gone. Either
                # way it can no longer name a page boundary.
                raise InvalidCursor(cursor)
            keyset = f"{'AND' if where else 'WHERE'} sort_key > ? "
            query_parameters.append(cast("str", anchor["sort_key"]))

        query_parameters.append(limit + 1)
        return connection.execute(
            f"SELECT {key_column} AS natural_key, document FROM {table} "
            f"{where}{keyset}ORDER BY sort_key LIMIT ?",
            query_parameters,
        ).fetchall()


# ------------------------------------------------------------------------------------------------
# Decoding and keys
# ------------------------------------------------------------------------------------------------


def _decode[ModelT: SourceDocument | Disclosure | CampFile | ArchiveSnapshot](
    model: type[ModelT], document: str, entity: str, key: str
) -> ModelT:
    """Validate one stored document back into its record, or report the row as unreadable."""
    try:
        return model.model_validate_json(document)
    except ValueError as invalid:
        raise CorruptRecordError(entity, key, str(invalid)) from invalid


def _page_of[ModelT: SourceDocument | Disclosure | CampFile](
    model: type[ModelT], entity: str, rows: list[sqlite3.Row], cursor_kind: str, limit: int
) -> Page[ModelT]:
    """Turn the rows of one over-read page into a `Page` and the cursor that continues it."""
    window = rows[:limit]
    items = tuple(
        _decode(model, cast("str", row["document"]), entity, cast("str", row["natural_key"]))
        for row in window
    )
    next_cursor = (
        f"{cursor_kind}:{cast('str', window[-1]['natural_key'])}" if len(rows) > limit and window else None
    )
    return Page(items=items, next_cursor=next_cursor)


def _cursor_key(cursor: str, kind: str) -> str:
    """The natural key a cursor points at, or a rejection of a cursor this listing did not mint."""
    prefix = f"{kind}:"
    if not cursor.startswith(prefix):
        raise InvalidCursor(cursor)
    return cursor[len(prefix) :]


def _source_sort_key(source: SourceDocument) -> str:
    return sort_key_for(descending_snapshot(source.last_seen_snapshot), source.sha256)


def _disclosure_sort_key(disclosure: Disclosure) -> str:
    return sort_key_for(descending_snapshot(disclosure.snapshot), disclosure.caselist, disclosure.source_path)


def _camp_file_sort_key(camp_file: CampFile) -> str:
    return sort_key_for(
        descending_snapshot(camp_file.snapshot), camp_file.file_title, camp_file.source_sha256
    )


def _widened(stored: SourceDocument, incoming: SourceDocument) -> SourceDocument:
    """The stored record with its seen range widened to cover the incoming one.

    Raises :class:`~debate_core.application.errors.Conflict` first when the two differ in size,
    format or origin. Size and format are facts about the bytes, so a difference there means the
    hash and the bytes have come apart. Origin is not: it records which import brought the bytes in
    first, and the same file under two origins is normal. It is refused only as a defence against
    a caller that skips :func:`~debate_core.application.caselist.pipeline.file_source`, which the
    importers never do. The rule is stated in full on
    :meth:`~debate_core.application.ports.caselist.CaselistRepository.put_source`.
    """
    unchanged = (stored.byte_size, stored.source_format, stored.origin)
    arriving = (incoming.byte_size, incoming.source_format, incoming.origin)
    if unchanged != arriving:
        raise Conflict(
            f"SourceDocument {incoming.sha256} is already stored as "
            f"{stored.byte_size} bytes / {stored.source_format} / {stored.origin}, "
            f"and cannot be restored as {incoming.byte_size} bytes / "
            f"{incoming.source_format} / {incoming.origin}"
        )
    return stored.evolve(
        first_seen_snapshot=min(stored.first_seen_snapshot, incoming.first_seen_snapshot),
        last_seen_snapshot=max(stored.last_seen_snapshot, incoming.last_seen_snapshot),
    )

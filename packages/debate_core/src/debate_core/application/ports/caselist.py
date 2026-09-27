"""The port the caselist importers, the publisher and the landscape reports store through.

One boundary, :class:`CaselistRepository`, covering the records an import of disclosed or camp
evidence produces. V1 satisfies it with SQLite (v1-e30-t03); V2 satisfies it with DynamoDB
without an importer changing. Blob *bytes* are not its business — those go to the
:class:`~debate_core.application.ports.persistence.SnapshotStore`, which already addresses them by
SHA-256; this port stores what the archive *said* about them.

It follows the conventions every port in this package follows (see
:mod:`debate_core.application.ports.persistence`): every method is `async`, implementations raise
only from :mod:`debate_core.application.errors`, `get_*` raises
:class:`~debate_core.application.errors.NotFound` while `find_*` returns `None`, and every
paginated listing returns a :class:`~debate_core.application.ports.persistence.Page` with an
opaque cursor.

Two conventions are this port's own, and both come from the fact that weekly archives are
cumulative — the same file arrives again every week until the team takes it down:

*Natural keys.* Nothing here is keyed by a minted ULID. A snapshot is its `(caselist, snapshot)`,
a source document is its `sha256`, a disclosure is its `(caselist, snapshot, source_path)` and a
camp file is its `(source_sha256, year, event)`. That is what makes a re-import of an unchanged
archive a no-op rather than a duplicate.

*Writes are idempotent, except where the bytes disagree.* `put_source`, `record_disclosure` and
`record_camp_file` may all be called again with the same record and change nothing. What they will
not do is quietly accept a *contradiction*: a second source document claiming the same SHA-256
with a different size or format means the hash and the bytes have come apart, and that raises
:class:`~debate_core.application.errors.Conflict` rather than overwriting the record that every
disclosure and manifest row already points at. A different *origin* also raises, but only as a
defence: the same bytes from a caselist and from OpenEv are one file, and the importers link to
the existing record rather than re-filing it (v1-e30-t04; see `put_source`).

*Listing order.* Snapshots list newest first. Sources, disclosures and camp files list newest
snapshot first, then by their remaining key parts ascending, which is a total order and therefore
a reproducible pagination.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from debate_core.application.ports.persistence import DEFAULT_PAGE_SIZE, Page
from debate_core.domain.caselist import (
    ArchiveSnapshot,
    CampFile,
    CaselistSlug,
    Disclosure,
    Event,
    Sha256Hex,
    SnapshotDate,
    SourceDocument,
)

__all__ = ["CaselistRepository"]


@runtime_checkable
class CaselistRepository(Protocol):
    """Stores what an import of disclosed or camp evidence learned.

    The importers (v1-e30-t03, t04) write through it, the publisher (t05) and the removal command
    (t07) read and delete through it, and the E31 parser and E32 reports read through it. It is
    the only way any of them reach caselist storage.
    """

    # ------------------------------------------------------------------------------------
    # Archive snapshots
    # ------------------------------------------------------------------------------------

    async def upsert_snapshot(self, snapshot: ArchiveSnapshot) -> ArchiveSnapshot:
        """Insert or replace the record of one weekly archive and return what was stored.

        Keyed by `(caselist, snapshot)`. Re-importing the same archive rewrites the same row,
        which is what makes an interrupted import safe to run again.
        """
        ...

    async def get_snapshot(self, caselist: CaselistSlug, snapshot: SnapshotDate) -> ArchiveSnapshot:
        """Return one archive record, or raise `NotFound`."""
        ...

    async def find_snapshot(self, caselist: CaselistSlug, snapshot: SnapshotDate) -> ArchiveSnapshot | None:
        """Return one archive record, or `None` when that archive has not been imported.

        This is the "have we already done this one?" question the importer asks first, so absence
        is an ordinary answer rather than a failure.
        """
        ...

    async def latest_snapshot(self, caselist: CaselistSlug) -> ArchiveSnapshot | None:
        """Return the most recent archive imported for this caselist, or `None` if there is none.

        The importer compares against this to refuse an archive older than one already imported,
        because applying an older cumulative archive would wrongly mark current files as removed.
        """
        ...

    async def list_snapshots(self, caselist: CaselistSlug) -> tuple[ArchiveSnapshot, ...]:
        """Return every archive imported for one caselist, newest snapshot date first.

        Unpaginated on purpose: a caselist accumulates one archive a week for one season.
        """
        ...

    # ------------------------------------------------------------------------------------
    # Source documents
    # ------------------------------------------------------------------------------------

    async def put_source(self, source: SourceDocument) -> SourceDocument:
        """Store a source document, or widen the snapshot range of the one already stored.

        Idempotent by SHA-256. When the hash is already known, the stored record's
        `first_seen_snapshot` and `last_seen_snapshot` are widened to cover the incoming one and
        the widened record is returned — that range is the whole answer to "which weeks was this
        file up?", and it must survive archives being imported out of order.

        Raises :class:`~debate_core.application.errors.Conflict` when the incoming record claims
        the same SHA-256 with a different `byte_size`, `source_format` or `origin`. The three are
        not the same kind of disagreement. A different size or format means the hash and the bytes
        have come apart, and two different files are being filed under one hash. A different
        origin does not: identical bytes arriving from a caselist archive and from an OpenEv
        release are one file, stored once and linked from both a disclosure and a camp-file record
        (v1-e30-t04). No caller should reach the refusal for that case, because the importers
        write through :func:`~debate_core.application.caselist.pipeline.file_source`, which keeps
        the record already filed under the other origin instead of calling this. The refusal
        stays as a defence: `origin` records which import first brought the bytes in, and a caller
        that bypassed `file_source` must not silently rewrite it.
        """
        ...

    async def get_source(self, sha256: Sha256Hex) -> SourceDocument:
        """Return the source document with this hash, or raise `NotFound`."""
        ...

    async def find_source(self, sha256: Sha256Hex) -> SourceDocument | None:
        """Return the source document with this hash, or `None`.

        The deduplication lookup every import performs per file, so "not stored yet" is the
        ordinary answer, not an error.
        """
        ...

    async def list_sources(
        self,
        *,
        caselist: CaselistSlug | None = None,
        snapshot: SnapshotDate | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[SourceDocument]:
        """List source documents, newest snapshot first, then by hash ascending.

        `snapshot` selects the documents that were present in that snapshot — that is, whose
        first/last seen range covers it — which is what the publisher uploads for one snapshot.
        With no filters, every source document is listed. `limit` must be at least 1.
        """
        ...

    # ------------------------------------------------------------------------------------
    # Disclosures and camp files
    # ------------------------------------------------------------------------------------

    async def record_disclosure(self, disclosure: Disclosure) -> Disclosure:
        """Record what one archive said about one file, keyed by caselist, snapshot and path.

        Idempotent: recording the same disclosure again replaces the identical row. One file
        disclosed under two paths is two disclosures of one source document, which is how a
        re-upload appears.
        """
        ...

    async def record_camp_file(self, camp_file: CampFile) -> CampFile:
        """Record what one OpenEv release said about one file, keyed by hash, year and event."""
        ...

    async def list_disclosures(
        self,
        *,
        caselist: CaselistSlug | None = None,
        snapshot: SnapshotDate | None = None,
        school: str | None = None,
        team_code: str | None = None,
        source_sha256: Sha256Hex | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Disclosure]:
        """List disclosures, newest snapshot first, then by source path ascending.

        Every filter is optional and they combine with AND. `team_code` without `school` is
        allowed — team codes are only unique within a school, so the wider listing is sometimes
        what an operator wants — and `source_sha256` answers "what does this file's removal
        affect?" for v1-e30-t07. `limit` must be at least 1.
        """
        ...

    async def list_camp_files(
        self,
        *,
        camp: str | None = None,
        year: int | None = None,
        event: Event | None = None,
        source_sha256: Sha256Hex | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[CampFile]:
        """List camp files, newest snapshot first, then by title ascending. Filters combine with AND."""
        ...

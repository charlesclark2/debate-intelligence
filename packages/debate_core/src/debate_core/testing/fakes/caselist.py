"""The in-memory fake of the caselist repository (`v1-e30-t02`).

Its port, :mod:`debate_core.application.ports.caselist`, pages with the persistence port's `Page`,
so this module pages with the persistence fakes' `paginate` and mints the same cursors.
"""

from __future__ import annotations

from datetime import date

from debate_core.application.errors import Conflict, NotFound
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.persistence import DEFAULT_PAGE_SIZE, Page
from debate_core.domain.caselist import ArchiveSnapshot, CampFile, Disclosure, Event, SourceDocument
from debate_core.testing.fakes.persistence import paginate

__all__ = ["InMemoryCaselistRepository", "build_fake_caselist_repository"]


class InMemoryCaselistRepository:
    """Imported caselist and camp-file records in dictionaries, keyed the way the port is keyed.

    The behaviour worth having a fake for is the seen-range arithmetic: the same file arrives in
    more than one archive, carried from one weekly window into the next and held by every complete
    archive until a team takes it down, so `put_source` widens a stored
    document's first/last seen range rather than replacing it, and it does that correctly even
    when archives are imported out of order. A fake that simply overwrote would let an importer
    test pass while the real thing lost the range that `caselist status` and the E32 reports read.

    It refuses a differing record under a stored SHA-256 just as SQLite's does: on size and format
    because the bytes have come apart, and on origin as the defence
    :meth:`~debate_core.application.ports.caselist.CaselistRepository.put_source` describes.
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
        return paginate(rows, kind="caselist-source", limit=limit, cursor=cursor)

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
        return paginate(rows, kind="disclosure", limit=limit, cursor=cursor)

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
        return paginate(rows, kind="camp-file", limit=limit, cursor=cursor)

    # -- removal ---------------------------------------------------------------------------

    async def delete_source(self, sha256: str) -> bool:
        return self._sources.pop(sha256, None) is not None

    async def delete_disclosure(self, caselist: str, snapshot: date, source_path: str) -> bool:
        return self._disclosures.pop((caselist, snapshot, source_path), None) is not None

    async def delete_camp_file(self, source_sha256: str, year: int, event: Event) -> bool:
        return self._camp_files.pop((source_sha256, year, str(event)), None) is not None


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

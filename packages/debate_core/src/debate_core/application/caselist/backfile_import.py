"""One earlier season's complete archive, imported, parsed and published as a backfile (`v1-e34-t34`).

Data-use policy 1.17 keeps earlier seasons' disclosures, from 2021-22 on, as **backfiles**: a
reservoir of evidence for research and team files, never classified into positions or given a
per-school view (Permitted uses 8). A backfile is a caselist named in `caselist.backfile_caselists`
(:meth:`~debate_core.application.settings.CaselistSettings.is_backfile`). That one setting is what
`caselist pull` and the weekly run refuse, what `landscape report` refuses, and what the annual purge
keeps. Removal, the suppression list and path holds need no marker: they act on every manifest, a
backfile's `full/<date>` one included.

`debate-research caselist backfile-import --caselist <slug>` is a dry run; `--execute` imports. The
PM's rulings of 2026-10-25 set what follows.

## What it refuses, before anything is fetched

* a caselist that is not a backfile, or is of a season before 2021-22;
* an environment not in bucket mode, or a bucket that is not seeded: the ledger and the lock are the
  bucket's, so any machine that runs the command, the Mac or a cloud task, reads the same ones;
* **the no-import window**, Tuesday 06:00 to Thursday 00:00 America/Chicago
  (:func:`in_no_import_window`). It covers the 24 hours the weekly run's ledger counts back from
  Wednesday 06:00, the Wednesday 03:00 login, the run itself, and any count by date the site keeps.
  The command refuses to start inside it, and each locked step asks again;
* **the backfile budget**: one complete archive in any rolling 24 hours, counted in its own ledger in
  the bucket (:data:`BACKFILE_LEDGER_KEY`), beside the run's state files and never one of them. The
  weekly run's ledger is never read or written, so its five a day are its own;
* a caselist that lists no complete archive (PF keeps weeklies only; policy 1.17 imports complete
  archives);
* **too little free space**: the estimate for this caselist, its archive in the inbox, its blobs and
  its parsed store (:func:`space_needed`), with 25% headroom, against the data directory's volume.

## The steps, and the lock

The bucket's run lock is the one the weekly run takes, held per step and never through the download
or the parse (the PM's ruling Q5):

1. **Locked**: restore the working copy (the run-state bundle, the state files, the parsed store of
   this caselist), note the bundle's version, check the budget, and record the download's start in
   the backfile ledger before the download, as a pull records its own.
2. **Not locked**: download the complete archive with `v1-e34-t04`'s downloader, import it into its
   `full/<date>` namespace with `v1-e34-t04`'s importer, and parse it.
3. **Locked**: publish the sources and the manifest, then save the run-state bundle, which then holds
   the backfile's manifest. Refused if the bucket's bundle changed since step 1: a removal in between
   rewrote it, and saving this copy over it would bring back what the removal took out.
4. **Locked**: publish the parsed store.

Nothing here touches the search index: backfiles stay out of the student search pilot's index until
`v1-e39-t18` decides. Nothing here classifies or builds a landscape.

**Counts only.** No path, school, team code or file name leaves this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import tempfile
import time
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol
from zoneinfo import ZoneInfo

from debate_core.application.caselist.backfile_survey import season_label, season_start_year
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService, Classification
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist.run_lock import BucketWriteGuard
from debate_core.application.caselist.run_state import RUN_STATE_BUNDLE_KEY, RunState
from debate_core.application.caselist_sync import (
    ArchiveReader,
    DownloadLedger,
    UnknownSyncEvent,
    VolumeReading,
    archive_entries,
    read_volume,
)
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.caselist_source import ArchiveKind, ArchiveListing, DownloadedFile
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.settings import FIRST_BACKFILE_SEASON_START, CaselistSettings
from debate_core.domain.caselist import Acquisition, Event

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
    from debate_core.application.caselist.publish_service import CaselistPublishService
    from debate_core.application.caselist_parse import CaselistParseService

__all__ = [
    "BACKFILE_DOWNLOADS_PER_DAY",
    "BACKFILE_LEDGER_FILENAME",
    "BACKFILE_LEDGER_KEY",
    "FREE_SPACE_HEADROOM",
    "IMPORT_COMMAND",
    "NO_IMPORT_WINDOW_ZONE",
    "PARSED_STORE_RATIO",
    "BackfileArchiveSource",
    "BackfileImportRefused",
    "BackfileImportService",
    "BackfilePlan",
    "BackfileReport",
    "BundleChangedSinceRestore",
    "Refusal",
    "SpaceNeeded",
    "in_no_import_window",
    "no_import_window_ends",
    "space_needed",
]

IMPORT_COMMAND: Final = "caselist backfile-import"

BACKFILE_DOWNLOADS_PER_DAY: Final = 1
"""Complete archives a backfile import may download in any rolling 24 hours (the PM's ruling Q1)."""

BACKFILE_LEDGER_FILENAME: Final = "caselist-backfile-download-starts.json"
BACKFILE_LEDGER_KEY: Final = f"reports/sync/state/{BACKFILE_LEDGER_FILENAME}"
"""Beside the run's state files, and not one of them: a weekly run neither restores nor saves it."""

NO_IMPORT_WINDOW_ZONE: Final = ZoneInfo("America/Chicago")

_TUESDAY, _WEDNESDAY, _THURSDAY = 1, 2, 3
_WINDOW_OPENS_AT_HOUR: Final = 6

PARSED_STORE_RATIO: Final = 4
"""Parsed-store bytes per source byte: 3.96 for LD and 3.88 for Policy, measured on the dev store on
2026-10-25 (`docs/session-reports/v1-e34-t34-backfile-seasons-import.md`), rounded up."""

FREE_SPACE_HEADROOM: Final = 1.25
"""A quarter on top of the estimate (the PM's ruling Q4), computed as `estimate * 5 / 4`, rounded up."""


class BackfileImportRefused(DomainError):
    """A backfile import refused to start, or to take the lock for a step. Nothing more was done."""

    def __init__(self, refusals: Sequence[Refusal]) -> None:
        self.refusals = tuple(refusals)
        self.codes = tuple(one.code for one in self.refusals)
        super().__init__("; ".join(f"{one.code}: {one.message}" for one in self.refusals))


class BundleChangedSinceRestore(DomainError):
    """The bucket's run-state bundle changed between this import's restore and its publish."""

    def __init__(self) -> None:
        super().__init__(
            "the run-state bundle in the bucket changed since this import restored it, most likely a "
            "removal; nothing was published. Run the import again: it restores the new bundle first"
        )


class BackfileArchiveSource(Protocol):
    """What the import asks of OpenCaselist. The API client answers it."""

    async def list_archives(self, caselist: str) -> list[ArchiveListing]: ...

    async def archive_size(self, archive: ArchiveListing) -> int | None: ...

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile: ...


@dataclass(frozen=True, slots=True)
class Refusal:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SpaceNeeded:
    """What one import needs on the data directory's volume, and what it has. Bytes."""

    archive_bytes: int
    estimate_bytes: int
    """The archive in the inbox (unless it is there already), its blobs and its parsed store."""
    required_bytes: int
    """The estimate with :data:`FREE_SPACE_HEADROOM`."""
    free_bytes: int

    @property
    def enough(self) -> bool:
        return self.free_bytes >= self.required_bytes


def space_needed(archive_bytes: int, *, free_bytes: int, in_inbox: bool = False) -> SpaceNeeded:
    """The free-space precheck's two numbers for an archive of `archive_bytes` (the PM's ruling Q4).

    The inbox holds the archive, the blob store about as much again (a `.docx` is already compressed,
    so a complete archive's members come to 0.96 of it, measured), and the parsed store
    :data:`PARSED_STORE_RATIO` times its sources.
    """
    inbox = 0 if in_inbox else archive_bytes
    estimate = inbox + archive_bytes + PARSED_STORE_RATIO * archive_bytes
    return SpaceNeeded(
        archive_bytes=archive_bytes,
        estimate_bytes=estimate,
        required_bytes=(estimate * 5 + 3) // 4,
        free_bytes=free_bytes,
    )


def in_no_import_window(now: datetime) -> bool:
    """Whether `now` is inside Tuesday 06:00 to Thursday 00:00, America/Chicago."""
    local = now.astimezone(NO_IMPORT_WINDOW_ZONE)
    if local.weekday() == _TUESDAY:
        return local.hour >= _WINDOW_OPENS_AT_HOUR
    return local.weekday() == _WEDNESDAY


def no_import_window_ends(now: datetime) -> datetime:
    """When the window `now` is inside closes: the Thursday 00:00 after it, America/Chicago."""
    local = now.astimezone(NO_IMPORT_WINDOW_ZONE)
    days = (_THURSDAY - local.weekday()) % 7 or 7
    thursday = (local + timedelta(days=days)).date()
    return datetime(thursday.year, thursday.month, thursday.day, tzinfo=NO_IMPORT_WINDOW_ZONE).astimezone(
        now.tzinfo
    )


@dataclass(frozen=True, slots=True)
class BackfilePlan:
    """What an import of one caselist would do, and every reason it would not. Counts only."""

    caselist: str
    season: str
    archive_date: date | None
    archive_bytes: int | None
    in_inbox: bool
    already_imported: bool
    downloads_left: int
    inside_window: bool
    window_ends: datetime | None
    space: SpaceNeeded | None
    refusals: tuple[Refusal, ...]
    archive: ArchiveListing | None = field(default=None, repr=False)
    """The listing itself, for the download: its URL is never shown."""

    @property
    def refused(self) -> bool:
        return bool(self.refusals)


@dataclass(slots=True)
class BackfileReport:
    """What one import did, step by step. Counts only."""

    plan: BackfilePlan
    downloaded_bytes: int = 0
    members: int = 0
    stored: int = 0
    suppressed: int = 0
    held_by_request: dict[str, int] = field(default_factory=dict[str, int])
    sources_uploaded: int = 0
    sources_skipped: int = 0
    sources_published: bool = False
    bundle: str | None = None
    bundle_saved: bool = False
    parsed: int = 0
    unsupported: int = 0
    failed: int = 0
    cards: int = 0
    parse_within_threshold: bool = False
    parsed_uploaded: int = 0
    parsed_published: bool = False
    archive_left_inbox: bool = False
    steps: dict[str, float] = field(default_factory=dict[str, float])

    @property
    def succeeded(self) -> bool:
        return (
            self.sources_published
            and self.bundle_saved
            and self.parse_within_threshold
            and self.parsed_published
        )


class BackfileImportService:
    """Imports one backfile caselist's complete archive. See the module docstring.

    Args:
        caselist_settings: `caselist`: which caselists are backfiles.
        bucket_mode: `caselist.run_state = bucket` in an environment that names a bucket.
        source: OpenCaselist: the listing, the size, the download.
        importer: `v1-e34-t04`'s importer, over the suppression list's two copies read as one.
        local: This machine's evidence store, where the manifest is written.
        read_full_archive: Reads a complete archive within its own ceilings.
        event_for_caselist: Which event a slug debates.
        inbox: Where the archive is downloaded to.
        data_dir: The data directory, whose volume the precheck reads.
        bucket: The bucket's everyday adapter, fenced by the run lock; `None` with no bucket.
        guard: The bucket's run lock, the weekly run's.
        run_state: The restore and the bundle's save; `None` with no bucket.
        seeded: Whether the bucket holds a lock object; `None` with no bucket.
        home_moved: The refusal of a lock held for good by the move of the run's home, or `None`
            (`v1-e40-t11`); itself `None` with no bucket.
        publisher: The source and manifest publisher; `None` with no bucket.
        parse: The parse pipeline, over the same suppression list as the importer.
        parsed_publisher: The parsed store's publisher; `None` with no bucket.
        parsed_version: The parsed store's version directory this build writes.
        clock: Now, in UTC.
        volume: Reads a directory's volume; :func:`read_volume` unless a test stubs it.
    """

    def __init__(
        self,
        *,
        caselist_settings: CaselistSettings,
        bucket_mode: bool,
        source: BackfileArchiveSource,
        importer: CaselistImportService,
        local: LocalEvidence,
        read_full_archive: ArchiveReader,
        event_for_caselist: Callable[[str], Event | None],
        inbox: Path,
        data_dir: Path,
        bucket: Callable[[], EvidenceObjectStore] | None,
        guard: BucketWriteGuard,
        run_state: Callable[[], RunState] | None,
        seeded: Callable[[], bool] | None,
        publisher: Callable[[], CaselistPublishService] | None,
        parse: Callable[[], CaselistParseService],
        parsed_publisher: Callable[[], ParsedStorePublisher] | None,
        parsed_version: str,
        clock: Callable[[], datetime],
        volume: Callable[[Path], VolumeReading] | None = None,
        home_moved: Callable[[], str | None] | None = None,
    ) -> None:
        self._settings = caselist_settings
        self._bucket_mode = bucket_mode
        self._source = source
        self._importer = importer
        self._local = local
        self._read_full_archive = read_full_archive
        self._event_for_caselist = event_for_caselist
        self._inbox = Path(inbox)
        self._data_dir = Path(data_dir)
        self._bucket = bucket
        self._guard = guard
        self._run_state = run_state
        self._seeded = seeded
        self._home_moved = home_moved
        self._publisher = publisher
        self._parse = parse
        self._parsed_publisher = parsed_publisher
        self._parsed_version = parsed_version
        self._clock = clock
        self._volume = volume

    # ------------------------------------------------------------------------------------------
    # The dry run
    # ------------------------------------------------------------------------------------------

    async def plan(self, caselist: str) -> BackfilePlan:
        """The dry run: the listing, a `HEAD`, the ledger and the volume read; nothing written or locked."""
        season = season_label(season_start_year(caselist)) if caselist[-2:].isdigit() else ""
        refusals: list[Refusal] = []
        now = self._clock()
        inside = in_no_import_window(now)
        ends = no_import_window_ends(now) if inside else None
        unlisted = self._unlisted(caselist)
        if unlisted is not None:
            return _plan(caselist, season, refusals=(unlisted,), inside=inside, ends=ends)
        refusals += await self._environment_refusals()
        if inside:
            refusals.append(
                Refusal(
                    "INSIDE_NO_IMPORT_WINDOW",
                    "no backfile import runs from Tuesday 06:00 to Thursday 00:00 America/Chicago, the "
                    f"weekly run's window; this one closes at {ends.isoformat() if ends else ''}",
                )
            )
        archive = await self._newest_complete_archive(caselist)
        if archive is None or archive.archive_date is None:
            refusals.append(
                Refusal("NO_COMPLETE_ARCHIVE", f"OpenCaselist lists no complete archive of {caselist}")
            )
            return _plan(caselist, season, refusals=tuple(refusals), inside=inside, ends=ends)
        in_inbox = (self._inbox / archive.name).is_file()
        already = await self._already_imported(caselist, archive.archive_date)
        size = (
            (self._inbox / archive.name).stat().st_size
            if in_inbox
            else await self._source.archive_size(archive)
        )
        left = await self._downloads_left(now)
        if left < 1 and not in_inbox and not already:
            refusals.append(
                Refusal(
                    "BACKFILE_BUDGET_SPENT",
                    f"a backfile import downloaded a complete archive in the 24 hours before now; the "
                    f"budget is {BACKFILE_DOWNLOADS_PER_DAY} a day, counted in the bucket's ledger",
                )
            )
        space = None
        if size is not None:
            # Imported already, it is a rebuild: the parsed store is restored and what it lacks is
            # parsed again from `raw/`, so the room is the archive's less the inbox's copy.
            space = space_needed(size, free_bytes=self._free_bytes(), in_inbox=in_inbox or already)
            if not space.enough:
                refusals.append(
                    Refusal(
                        "NOT_ENOUGH_FREE_SPACE",
                        f"the data directory's volume has {space.free_bytes:,} bytes free and this "
                        f"import needs {space.required_bytes:,}: an estimate of {space.estimate_bytes:,} "
                        "for the archive, its blobs and its parsed store, with 25% headroom",
                    )
                )
        return BackfilePlan(
            caselist=caselist,
            season=season,
            archive_date=archive.archive_date,
            archive_bytes=size,
            in_inbox=in_inbox,
            already_imported=already,
            downloads_left=left,
            inside_window=inside,
            window_ends=ends,
            space=space,
            refusals=tuple(refusals),
            archive=archive,
        )

    def _unlisted(self, caselist: str) -> Refusal | None:
        if not self._settings.is_backfile(caselist):
            return Refusal(
                "NOT_A_BACKFILE",
                f"{caselist} is not in caselist.backfile_caselists, so it is not imported as a backfile",
            )
        if (
            season_start_year(caselist) < FIRST_BACKFILE_SEASON_START
        ):  # pragma: no cover - the setting refuses it
            return Refusal("SEASON_BEFORE_BACKFILES", f"{caselist} is of a season before 2021-22")
        return None

    async def _environment_refusals(self) -> list[Refusal]:
        if not self._bucket_mode or self._bucket is None:
            return [
                Refusal(
                    "NOT_IN_BUCKET_MODE",
                    "a backfile import keeps its ledger and takes its lock in the bucket, so it runs in "
                    "bucket mode only (caselist.run_state = bucket)",
                )
            ]
        if self._seeded is not None and not await asyncio.to_thread(self._seeded):
            return [
                Refusal(
                    "RUN_STATE_NOT_SEEDED",
                    "the bucket holds no run lock yet; it is seeded at the cutover "
                    "(docs/runbooks/caselist-cutover.md)",
                )
            ]
        moved = await asyncio.to_thread(self._home_moved) if self._home_moved is not None else None
        if moved is not None:
            return [Refusal("RUN_HOME_MOVED", moved)]
        return []

    async def _newest_complete_archive(self, caselist: str) -> ArchiveListing | None:
        listed = await self._source.list_archives(caselist)
        complete = [one for one in listed if one.kind is ArchiveKind.FULL and one.archive_date is not None]
        return max(complete, key=lambda one: one.archive_date or date.min, default=None)

    async def _already_imported(self, caselist: str, archive_date: date) -> bool:
        key = manifest_key(caselist, archive_date)
        if self._bucket is None:
            return False
        try:
            await self._bucket().head(key)
        except NotFound:
            return False
        return True

    async def _downloads_left(self, now: datetime) -> int:
        with tempfile.TemporaryDirectory(prefix="backfile-ledger-") as scratch:
            ledger = await self._ledger_in(Path(scratch))
            return ledger.remaining_at(now)

    async def _ledger_in(self, directory: Path) -> DownloadLedger:
        """The bucket's backfile ledger, copied into `directory`: absent means nothing spent."""
        path = directory / BACKFILE_LEDGER_FILENAME
        if self._bucket is not None:
            with contextlib.suppress(NotFound):
                await self._bucket().get_file(BACKFILE_LEDGER_KEY, path)
        return DownloadLedger(path, limit=BACKFILE_DOWNLOADS_PER_DAY)

    def _free_bytes(self) -> int:
        reading = (self._volume or read_volume)(
            self._data_dir if self._data_dir.exists() else self._data_dir.parent
        )
        return reading.total_bytes - reading.used_bytes

    # ------------------------------------------------------------------------------------------
    # The import
    # ------------------------------------------------------------------------------------------

    async def run(self, caselist: str) -> BackfileReport:
        """The import, in the four steps of the module docstring.

        Raises :class:`BackfileImportRefused` for anything the plan refuses, before anything is
        downloaded, and for a locked step that would start inside the window; and
        :class:`BundleChangedSinceRestore` when the bucket's bundle moved under it.
        """
        plan = await self.plan(caselist)
        if plan.refused:
            raise BackfileImportRefused(plan.refusals)
        assert plan.archive is not None and plan.archive.archive_date is not None
        assert self._run_state is not None and self._bucket is not None
        report = BackfileReport(plan=plan)
        state = self._run_state()
        needs_download = not plan.in_inbox and not plan.already_imported
        with self._step(report, "restore"), self._locked():
            await state.restore([caselist], parsed_version=self._parsed_version)
            bundle = await self._bundle_tag()
            if needs_download:
                await self._record_the_download()
        if not plan.already_imported:
            with self._step(report, "download"):
                downloaded = await self._download(plan.archive)
                report.downloaded_bytes = 0 if plan.in_inbox else downloaded.byte_size
            with self._step(report, "import"):
                await self._import(plan.archive, downloaded, report)
        with self._step(report, "parse"):
            version = await self._parse_it(caselist, report)
        with self._step(report, "publish"), self._locked():
            if await self._bundle_tag() != bundle:
                raise BundleChangedSinceRestore
            await self._publish_sources(caselist, plan.archive.archive_date.isoformat(), state, report)
        if report.bundle_saved and report.parse_within_threshold:
            with self._step(report, "publish_parsed"), self._locked():
                await self._publish_parsed(caselist, version, report)
        if report.sources_published and report.bundle_saved:
            report.archive_left_inbox = self._leave_the_inbox(plan.archive)
        return report

    @contextmanager
    def _locked(self) -> Generator[None]:
        """The bucket's run lock for one step, after asking the window again (the PM's ruling Q1)."""
        now = self._clock()
        if in_no_import_window(now):
            raise BackfileImportRefused(
                (
                    Refusal(
                        "INSIDE_NO_IMPORT_WINDOW",
                        "the no-import window opened during the import, so this step did not take the "
                        f"lock; it closes at {no_import_window_ends(now).isoformat()}. Run the import "
                        "again after it: it resumes from what is published",
                    ),
                )
            )
        with self._guard.held(IMPORT_COMMAND):
            yield

    @contextmanager
    def _step(self, report: BackfileReport, name: str) -> Generator[None]:
        started = time.monotonic()
        try:
            yield
        finally:
            report.steps[name] = time.monotonic() - started

    async def _bundle_tag(self) -> str | None:
        assert self._bucket is not None
        try:
            info = await self._bucket().head(RUN_STATE_BUNDLE_KEY)
        except NotFound:
            return None
        return info.version_id or info.sha256

    async def _record_the_download(self) -> None:
        """Under the lock: refuse a spent budget, then record this download's start in the bucket's ledger."""
        assert self._bucket is not None
        now = self._clock()
        with tempfile.TemporaryDirectory(prefix="backfile-ledger-") as scratch:
            ledger = await self._ledger_in(Path(scratch))
            if ledger.remaining_at(now) < 1:
                raise BackfileImportRefused(
                    (
                        Refusal(
                            "BACKFILE_BUDGET_SPENT", "another backfile download started in the last 24 hours"
                        ),
                    )
                )
            ledger.record(now)
            await self._bucket().put_file(BACKFILE_LEDGER_KEY, ledger.path)

    async def _download(self, archive: ArchiveListing) -> DownloadedFile:
        path = self._inbox / archive.name
        if path.is_file():
            return DownloadedFile(
                path=path,
                sha256=await asyncio.to_thread(_sha256_of, path),
                byte_size=path.stat().st_size,
                source_name=archive.name,
                already_present=True,
            )
        self._inbox.mkdir(parents=True, exist_ok=True)
        return await self._source.download_archive(archive, self._inbox)

    async def _import(
        self, archive: ArchiveListing, downloaded: DownloadedFile, report: BackfileReport
    ) -> None:
        """The complete archive, read within its own ceilings, filed as the backfile's dated snapshot.

        Into `manifests/<slug>/<date>.jsonl`, the series every reader of a caselist reads, and not into
        `v1-e34-t04`'s `full/<date>` beside it: a backfile has no weekly series, so its complete
        archive is the whole of what it disclosed, and only the dated series is parsed, given card
        provenance, and counted by `caselist status` (see "Deviations" in this task's report).
        """
        assert archive.archive_date is not None
        event = self._event_for_caselist(archive.caselist)
        if event is None:
            raise UnknownSyncEvent(archive.caselist)
        imported = await self._importer.import_archive(
            archive_entries(self._read_full_archive, downloaded.path),
            caselist=archive.caselist,
            snapshot=archive.archive_date,
            event=event,
            archive_sha256=downloaded.sha256,
            acquisition=Acquisition.API,
        )
        path_for = self._local.object_path_for
        assert path_for is not None
        write_manifest(imported, path_for(manifest_key(archive.caselist, archive.archive_date)))
        report.members = sum(n for kind, n in imported.counts.items() if kind is not Classification.REMOVED)
        report.stored = imported.newly_stored_blobs
        report.suppressed = imported.counts.get(Classification.SUPPRESSED, 0)
        report.held_by_request = dict(imported.held_by_request)

    async def _parse_it(self, caselist: str, report: BackfileReport) -> str:
        service = self._parse()
        planned = await service.plan(caselist)
        parsed = await service.run(planned)
        report.parsed = parsed.parsed
        report.unsupported = sum(parsed.unsupported.values())
        report.failed = sum(parsed.failed.values())
        report.cards = parsed.cards
        report.parse_within_threshold = not parsed.exceeds_threshold
        return planned.version

    async def _publish_sources(
        self, caselist: str, snapshot: str, state: RunState, report: BackfileReport
    ) -> None:
        """Under the lock: the sources and the manifest, then the bundle, which then holds the manifest."""
        assert self._publisher is not None
        publisher = self._publisher()
        published = await publisher.execute(await publisher.plan(caselist, snapshot))
        report.sources_uploaded = published.count(SourceResult.UPLOADED)
        report.sources_skipped = published.count(SourceResult.SKIPPED)
        report.sources_published = published.succeeded
        if not published.succeeded:
            report.bundle = (
                "not saved: the sources' publish did not complete ("
                + ", ".join(published.failure_codes)
                + ")"
            )
            return
        saved = await state.save_bundle()
        report.bundle = saved.reason
        report.bundle_saved = saved.saved

    async def _publish_parsed(self, caselist: str, version: str, report: BackfileReport) -> None:
        assert self._parsed_publisher is not None
        published = await self._parsed_publisher().publish(caselist, version)
        report.parsed_uploaded = published.count(SourceResult.UPLOADED)
        report.parsed_published = published.succeeded

    def _leave_the_inbox(self, archive: ArchiveListing) -> bool:
        """The archive leaves the inbox once its sources and manifest are confirmed: the biggest file."""
        path = self._inbox / archive.name
        try:
            path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True


def _plan(
    caselist: str, season: str, *, refusals: tuple[Refusal, ...], inside: bool, ends: datetime | None
) -> BackfilePlan:
    return BackfilePlan(
        caselist=caselist,
        season=season,
        archive_date=None,
        archive_bytes=None,
        in_inbox=False,
        already_imported=False,
        downloads_left=0,
        inside_window=inside,
        window_ends=ends,
        space=None,
        refusals=refusals,
    )


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

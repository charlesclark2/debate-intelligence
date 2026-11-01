"""`caselist reimport-openev-metadata` in bucket mode: a camp table change reaches the records (`v1-e40-t34`).

Since the cutover, dev's records are the cloud run's run-state bundle
(`manifests/_run-state/run-state.tar.gz`, :mod:`~debate_core.application.caselist.run_state`), which
only a pull, a backfile import and a removal save. A metadata re-import over this machine's data
directory (`OpenEvImportService.reimport_metadata`, `v1-e30-t08`) changes a copy that the next cloud
run replaces. In bucket mode the re-import works on the bucket's copy instead, as `caselist remove
--execute` does
(:func:`~debate_core.application.caselist.removal_service.on_the_working_copy`, then
`CaselistRemovalService._rewrite_run_state`), and :meth:`OpenEvMetadataReimportInBucket.execute`
does, in order:

1. refuse inside the no-import window, Tuesday 06:00 to Thursday 00:00 America/Chicago, which holds
   the whole of every Wednesday: the backfile import's own rule
   (:func:`~debate_core.application.caselist.backfile_import.in_no_import_window`);
2. take the bucket's run lock through the command's
   :class:`~debate_core.application.caselist.run_lock.BucketWriteGuard`, with conditional writes, as
   the removal and the backfile import take it. Its refusals are the lock's own: a live lease
   (`RUN_LOCK_HELD`), a lock held for good by the move of the run's home (`RUN_HOME_MOVED`), a bucket
   never seeded (`RUN_STATE_NOT_SEEDED`). Then the window is asked again;
3. restore the working copy: the bundle (manifests and database) and the state files, the OpenEv
   delivery record among them;
4. re-derive the release and correct its camp-file records, then write the manifest;
5. refuse :class:`~debate_core.application.caselist.backfile_import.BundleChangedSinceRestore` when the
   bucket's bundle is no longer the one restored, before anything is published, as the backfile import
   does;
6. publish the release with `caselist publish --caselist openev --snapshot <year>-<event>`'s service.
   Its sources are in the bucket already and are only asked for, so it uploads the manifest alone;
7. save the bundle, which then holds the re-derived manifest and records;
8. release the lock, however it ended.

A release whose metadata is already right changes nothing, and publishes and saves nothing.

## The dry run

:meth:`OpenEvMetadataReimportInBucket.dry_run`, the command's default. It refuses inside the window,
and refuses a moved home and an unseeded bucket by reading the lock object. It then restores the
working copy, as `remove`'s dry run does, re-derives with no record or manifest written, and reports
what would change. It takes no lock and writes nothing to the bucket.

## Bytes

None are read. The re-derive asks the blob store only whether each digest is held, and in a restored
working copy, which fetches no raw source, none is: that is counted, not fetched. The publish asks
the bucket for each source's digest and uploads none it already holds.

## After it

The next cloud run's parse stage rebuilds the occurrence rows, taking each camp from the manifest
rows, and its search index stage rebuilds the index from them because the store's digest changed
(`v1-e30-t32`'s route table).

## What is logged

Counts, the year and the event
(:func:`~debate_core.application.caselist.openev_metadata_reimport.log_reimport`). Never a path, a
title or a lab.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from debate_core.application.caselist.backfile_import import (
    BundleChangedSinceRestore,
    in_no_import_window,
    no_import_window_ends,
)
from debate_core.application.caselist.camp_metadata import CampAliases
from debate_core.application.caselist.manifest import read_manifest_lines, write_manifest_lines
from debate_core.application.caselist.openev_manifest import openev_manifest_key, openev_release_name
from debate_core.application.caselist.openev_metadata_reimport import OpenEvMetadataReimport
from debate_core.application.caselist.publish_plan import OPENEV
from debate_core.application.caselist.run_lock import BucketRunLock, BucketWriteGuard, RunStateNotSeeded
from debate_core.application.caselist.run_state import (
    RUN_STATE_BUNDLE_KEY,
    BundleSave,
    RestoreReport,
    RunState,
)
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.domain.caselist import Event

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from debate_core.application.caselist.openev_import_service import OpenEvImportService
    from debate_core.application.caselist.publish_service import CaselistPublishService, PublishReport

__all__ = [
    "REIMPORT_COMMAND",
    "BucketReimport",
    "InsideTheNoImportWindow",
    "OpenEvMetadataReimportInBucket",
]

REIMPORT_COMMAND: Final = "caselist reimport-openev-metadata"
"""The name the re-import holds the bucket's run lock under."""


class InsideTheNoImportWindow(DomainError):
    """The no-import window is open: Tuesday 06:00 to Thursday 00:00 America/Chicago. Nothing was done."""

    ERROR_CODE = "INSIDE_NO_IMPORT_WINDOW"

    def __init__(self, closes_at: datetime) -> None:
        self.closes_at = closes_at
        super().__init__(
            "the no-import window (Tuesday 06:00 to Thursday 00:00 America/Chicago, the weekly cloud "
            "run's) is open, so the re-import neither restored nor wrote anything; it closes at "
            f"{closes_at.isoformat()}. Run it again after that"
        )


@dataclass(frozen=True, slots=True)
class BucketReimport:
    """What one re-import in bucket mode did, or under its dry run would do. Counts and outcomes only."""

    reimport: OpenEvMetadataReimport
    restored: RestoreReport
    published: PublishReport | None = None
    """The release's publish; `None` for a dry run, and for a release whose metadata was already right."""

    bundle: BundleSave | None = None
    """The save of the bundle after the publish; `None` whenever there was no publish, or it failed."""

    @property
    def executed(self) -> bool:
        return self.reimport.applied

    @property
    def changes_anything(self) -> bool:
        """Whether the manifest or a camp-file record differs from the restored copy's."""
        return self.reimport.manifest_changed or self.reimport.camp_files_updated > 0

    @property
    def succeeded(self) -> bool:
        """A dry run, a release already right, or a publish and a confirmed save of the bundle."""
        if not self.executed or not self.changes_anything:
            return True
        return (
            self.published is not None
            and self.published.succeeded
            and self.bundle is not None
            and self.bundle.saved
        )


class OpenEvMetadataReimportInBucket:
    """The re-import on the bucket's copy of the run's state. See the module docstring.

    Each collaborator that opens the database or reads the state files is a factory, called after the
    restore: the restore replaces the database whole and brings the delivery record with it.

    Args:
        guard: The command's :class:`BucketWriteGuard`, in bucket mode.
        lock: Builds the lease, read by the dry run to refuse what a take would.
        run_state: Builds the run's state in the bucket: the restore and the save.
        bucket: Builds the bucket's everyday adapter, asked for the bundle's version.
        importer: Builds the OpenEv importer over the restored database.
        publisher: Builds the publisher from the restored working copy to the bucket.
        upstream_paths: The restored delivery record's upstream path digests, by OpenEv id.
        manifest_path: Where the working copy keeps a manifest, by key.
        clock: Now, in UTC.
    """

    def __init__(
        self,
        *,
        guard: BucketWriteGuard,
        lock: Callable[[], BucketRunLock],
        run_state: Callable[[], RunState],
        bucket: Callable[[], EvidenceObjectStore],
        importer: Callable[[], OpenEvImportService],
        publisher: Callable[[], CaselistPublishService],
        upstream_paths: Callable[[], Mapping[int, str]],
        manifest_path: Callable[[ObjectKey], Path],
        clock: Callable[[], datetime],
    ) -> None:
        self._guard = guard
        self._lock = lock
        self._run_state = run_state
        self._bucket = bucket
        self._importer = importer
        self._publisher = publisher
        self._upstream_paths = upstream_paths
        self._manifest_path = manifest_path
        self._clock = clock

    async def dry_run(self, *, year: int, event: Event, aliases: CampAliases) -> BucketReimport:
        """Restore, re-derive with nothing written, and say what would change. No lock, no bucket write."""
        self._refuse_the_window()
        lock = self._lock()
        if not lock.bucket_is_seeded():
            raise RunStateNotSeeded
        moved = lock.home_moved()
        if moved is not None:
            raise moved
        restored = await self._run_state().restore((), parsed_version=None)
        return BucketReimport(
            reimport=await self._rederive(year, event, aliases, dry_run=True), restored=restored
        )

    async def execute(self, *, year: int, event: Event, aliases: CampAliases) -> BucketReimport:
        """Steps 1 to 8 of the module docstring: the run lock held from the restore to the save."""
        self._refuse_the_window()
        with self._locked():
            state = self._run_state()
            restored = await state.restore((), parsed_version=None)
            bundle = await self._bundle_tag()
            reimport = await self._rederive(year, event, aliases, dry_run=False)
            outcome = BucketReimport(reimport=reimport, restored=restored)
            if not outcome.changes_anything:
                return outcome
            if reimport.manifest_changed:
                write_manifest_lines(reimport.manifest_lines, self._manifest_path(reimport.manifest_key))
            if await self._bundle_tag() != bundle:
                raise BundleChangedSinceRestore
            publisher = self._publisher()
            published = await publisher.execute(
                await publisher.plan(OPENEV, openev_release_name(year, event))
            )
            if not published.succeeded:
                return BucketReimport(reimport=reimport, restored=restored, published=published)
            return BucketReimport(
                reimport=reimport, restored=restored, published=published, bundle=await state.save_bundle()
            )

    async def _rederive(
        self, year: int, event: Event, aliases: CampAliases, *, dry_run: bool
    ) -> OpenEvMetadataReimport:
        key = openev_manifest_key(year, event)
        return await self._importer().reimport_metadata(
            year=year,
            event=event,
            recorded_manifest=read_manifest_lines(self._manifest_path(key)),
            aliases=aliases,
            dry_run=dry_run,
            upstream_paths=self._upstream_paths(),
        )

    def _refuse_the_window(self) -> None:
        now = self._clock()
        if in_no_import_window(now):
            raise InsideTheNoImportWindow(no_import_window_ends(now))

    @contextmanager
    def _locked(self) -> Generator[None]:
        """The bucket's run lock for the whole re-import, with the window asked again once it is held."""
        with self._guard.held(REIMPORT_COMMAND):
            self._refuse_the_window()
            yield

    async def _bundle_tag(self) -> str | None:
        try:
            info = await self._bucket().head(RUN_STATE_BUNDLE_KEY)
        except NotFound:
            return None
        return info.version_id or info.sha256

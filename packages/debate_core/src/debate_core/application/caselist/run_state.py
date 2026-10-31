"""A cloud run keeps its state in the evidence bucket: the restore and the saves (ADR-0020 (3), `v1-e40-t04`).

In bucket mode (`caselist.run_state = "bucket"`) the evidence bucket of the run's home environment is
the record of the run's state, and the data directory a working copy. :class:`RunState` restores that
copy at a run's start and saves the state back as ADR-0020 (3) sets out. Nothing here takes the lock:
every write below goes through a client the run lock fences
(:mod:`debate_core.application.caselist.run_lock`), so none of it reaches the bucket from a runner
that does not hold the lease.

## What is restored, one way

1. **The run-state bundle**, `manifests/_run-state/run-state.tar.gz`: this machine's manifests and
   SQLite database, which must agree. It is downloaded and checked against the SHA-256 its publisher
   recorded, unpacked into a scratch directory, and asked the publisher's own withholding rule
   (:func:`~debate_core.application.caselist.publish_service.withheld_manifest_reason`, as `store
   sync --push` asks it) about every manifest in it. One the publisher withholds stops the restore
   with the publisher's message (:class:`RunStateWithheld`) and nothing is installed. There is no
   second copy of the rule. Otherwise the manifests and the database replace this machine's whole.
2. **The state files** under `reports/sync/state/` (:data:`STATE_FILES`): the run log, its details,
   the download ledger, the OpenEv deliveries, the pending-work file and, since `v1-e40-t08`, the
   parse-owed file, which a build before it neither restores nor saves. A file the bucket does not
   hold is left as it is. An empty object is the record of a file that was removed (the pending-work
   file is removed when nothing is owed, and nothing here may delete), and removes the local one.
3. **The published index's manifest**: `current.json` and the manifest it names, into
   `tub-index/<index id>/manifest.json`, marked as restored. The search index stage compares the
   stores' digests with it and skips a rebuild when they match; a restored directory holds the
   manifest alone, so it is never published from, and a changed digest rebuilds
   (:mod:`debate_core.application.search_index_refresh`). Beside it, since `v1-e39-t19`, the
   record of what an identical rebuild last checked it against, `checked-against.json`, when the
   bucket holds one that names that manifest's digest: what the cutover's comparison reads.
4. **The parsed store's current version directory** of each configured caselist and `openev`:
   `parsed/<caselist>/<version>/`, where the version is this build's parser version. Each object is
   downloaded and checked against the SHA-256 the parsed store's publisher recorded in its metadata;
   a file this machine already holds with that digest is kept. Nothing is ever written to `parsed/`
   in the bucket: its publisher stays its only writer (`v1-e29-t12`). A version the bucket does not
   hold restores nothing, and the parse stage parses afresh.

Raw sources are fetched only as the parse needs them (:meth:`RunState.fetch_sources`), from `raw/`,
where the key is the digest and the check is the key.

## What is saved, and when

* **The state files**, each as the local file is written (:meth:`RunState.save_state_file`): the
  download ledger before each download starts, the OpenEv deliveries when an import completes, the
  pending-work file whenever it is written, and the run log and details at the end of the run.
* **The bundle** only at a moment when every snapshot it records is confirmed in the bucket
  (:meth:`RunState.save_bundle`): every local manifest is in the bucket with the same SHA-256, and
  none is one the publisher withholds. Otherwise the bucket keeps the previous bundle, and the next
  run redoes the weeks after it, downloading them again within the ledger's limit. A week redone is
  late, never lost (ADR-0017 decision 3).
* **The held uploads**, at every save of the bundle and before it, whether or not the bundle is then
  saved (:meth:`RunState.save_held_digests`, `v1-e40-t12`): what this working copy's imports refused
  at a held path, appended to `manifests/_suppression/held-digests.jsonl`, which a removal and
  `caselist status` read from any machine. A working copy vanishes with its task, and this record
  is the one thing that names a refused upload once its archive has gone. Every save site holds the
  run's lock, so no bundle recording a snapshot is in the bucket without the uploads its import
  refused.

## What is logged

Keys, counts, bytes and digests. A manifest's key names a caselist and a date; nothing here names a
school, a team, a file or a path on this machine.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.manifest import MANIFEST_DIRECTORY
from debate_core.application.caselist.parse_sources import EnumeratedSource
from debate_core.application.caselist.publish_plan import local_blob_key, source_key
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.caselist_sync import (
    DOWNLOAD_LEDGER_FILENAME,
    OPENEV_DELIVERIES_FILENAME,
    PARSE_OWED_FILENAME,
    PENDING_WORK_FILENAME,
    ParseOwed,
    ParsesOwed,
)
from debate_core.application.errors import BlobIntegrityError, DomainError, NotFound
from debate_core.application.evidence_sync import WithheldManifests
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.parsed_store import OPENEV_STORE
from debate_core.application.ports.run_state import RUN_STATE_BUNDLE_KEY, RUN_STATE_PREFIX, RunStateFiles
from debate_core.application.ports.suppression import HeldDigestList, SuppressionList
from debate_core.application.search_index_publish import CHECKED_AGAINST_NAME, read_checked_against
from debate_core.application.search_index_refresh import RESTORED_INDEX_MARKER, SEARCH_INDEX_DIRECTORY
from debate_core.application.sync_runs import SYNC_RUN_DETAILS_FILENAME, SYNC_RUN_LOG_FILENAME
from debate_core.domain.search_index import (
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SearchIndexPointer,
    index_object_key,
)

__all__ = [
    "PARSED_PREFIX",
    "RUN_STATE_BUNDLE_KEY",
    "RUN_STATE_PREFIX",
    "STATE_FILES",
    "STATE_PREFIX",
    "BundleSave",
    "RestoreReport",
    "RunState",
    "RunStateBundleMissing",
    "RunStateWithheld",
    "state_key",
]

logger = logging.getLogger(__name__)

STATE_PREFIX: Final = "reports/sync/state/"
"""The state with no personal data, beside the run summaries' prefix."""

PARSED_PREFIX: Final = "parsed/"

STATE_FILES: Final = (
    SYNC_RUN_LOG_FILENAME,
    SYNC_RUN_DETAILS_FILENAME,
    DOWNLOAD_LEDGER_FILENAME,
    OPENEV_DELIVERIES_FILENAME,
    PENDING_WORK_FILENAME,
    PARSE_OWED_FILENAME,
)
"""The data directory's state files a later run needs, by their names there and in the bucket.

The parse-owed file is last and new in `v1-e40-t08`: an older build's own list of five is what it
restores and saves, so it neither reads this file nor writes over it."""

_PARALLEL_DOWNLOADS: Final = 16


def state_key(name: str) -> ObjectKey:
    """The bucket key of one state file: `reports/sync/state/<name>`."""
    if name not in STATE_FILES:
        raise ValueError(f"not a run state file: {name!r}")
    return f"{STATE_PREFIX}{name}"


class RunStateBundleMissing(DomainError):
    """The bucket holds a run lock and no run-state bundle: a seed that did not finish. Nothing is done."""

    record_stays_local = True

    def __init__(self) -> None:
        super().__init__(
            f"the bucket holds a run lock and no run-state bundle ({RUN_STATE_BUNDLE_KEY}), so there is "
            "no state to restore and nothing was done: run the seed again from the machine that holds "
            "the run's state"
        )


class RunStateWithheld(DomainError):
    """A manifest the publisher withholds is in the run's state: the bundle is neither saved nor restored.

    The message is the publisher's own (:class:`~debate_core.application.evidence_sync.ManifestWithholding`),
    which names the removal to run again; this class adds which side it stopped.
    """

    def __init__(self, *, saving: bool, publisher_says: str, request_ids: Sequence[str] = ()) -> None:
        self.publisher_says = publisher_says
        self.request_ids = tuple(request_ids)
        what = "saved" if saving else "restored"
        super().__init__(
            f"the run-state bundle was not {what}, because it holds a manifest a publish withholds: "
            f"{publisher_says}"
        )


@dataclass(frozen=True, slots=True)
class RestoreReport:
    """What one restore brought to this machine. Counts and ids only."""

    started_at: datetime
    finished_at: datetime
    state_files: tuple[str, ...]
    parsed_version: str | None = None
    parsed_objects: int = 0
    parsed_bytes: int = 0
    parsed_kept: int = 0
    index_id: str | None = None

    @property
    def sentence(self) -> str:
        said = (
            f"restored the run-state bundle and {len(self.state_files)} state file(s) "
            f"in {(self.finished_at - self.started_at).total_seconds():.1f}s"
        )
        if self.parsed_version is not None:
            said += (
                f"; the parsed store at {self.parsed_version}: {self.parsed_objects} object(s), "
                f"{self.parsed_bytes} bytes, {self.parsed_kept} already held"
            )
            said += (
                f"; the published index {self.index_id}'s manifest"
                if self.index_id is not None
                else "; no index is published yet"
            )
        return said


@dataclass(frozen=True, slots=True)
class BundleSave:
    """Whether a save of the bundle happened, and why not when it did not."""

    saved: bool
    reason: str
    sha256: str | None = None
    version_id: str | None = None


class RunState:
    """The bucket side of a bucket-mode run's state. See the module docstring.

    Args:
        bucket: The home environment's bucket, through a client the run lock fences.
        files: This machine's manifests and database, packed and installed.
        local: This machine's evidence store, whose manifests the bundle holds.
        staged: Builds the same view of a scratch directory, to ask the publisher about a bundle's
            manifests before they are installed.
        withheld: The publisher's rule (:data:`~debate_core.application.evidence_sync.WithheldManifests`)
            over a store; called with each manifest's listing entry.
        suppression: The removal suppression list the publisher's rule reads.
        data_dir: The data directory: where state files, `parsed/` and `tub-index/` are.
        clock: Now, in UTC.
    """

    def __init__(
        self,
        *,
        bucket: EvidenceObjectStore,
        files: RunStateFiles,
        local: LocalEvidence,
        staged: Callable[[Path], LocalEvidence],
        withheld: Callable[[LocalEvidence], WithheldManifests],
        suppression: SuppressionList,
        data_dir: Path,
        clock: Callable[[], datetime],
    ) -> None:
        self._bucket = bucket
        self._files = files
        self._local = local
        self._staged = staged
        self._withheld = withheld
        self._suppression = suppression
        self._data_dir = Path(data_dir)
        self._clock = clock

    # ------------------------------------------------------------------------------------------
    # The restore
    # ------------------------------------------------------------------------------------------

    async def restore(self, caselists: Sequence[str], *, parsed_version: str | None) -> RestoreReport:
        """Restore the working copy. `parsed_version` `None` restores the bundle and state files alone.

        Raises :class:`RunStateBundleMissing`, :class:`RunStateWithheld`, or the store's error, each
        before anything of the bundle is installed.
        """
        started = self._clock()
        await self.restore_bundle()
        state_files = await self._restore_state_files()
        if parsed_version is None:
            return RestoreReport(started_at=started, finished_at=self._clock(), state_files=state_files)
        index_id = await self._restore_index_manifest()
        objects = kept = size = 0
        for store in dict.fromkeys((*caselists, OPENEV_STORE)):
            fetched, held, fetched_bytes = await self._restore_parsed(store, parsed_version)
            objects, kept, size = objects + fetched, kept + held, size + fetched_bytes
        report = RestoreReport(
            started_at=started,
            finished_at=self._clock(),
            state_files=state_files,
            parsed_version=parsed_version,
            parsed_objects=objects,
            parsed_bytes=size,
            parsed_kept=kept,
            index_id=index_id,
        )
        logger.info(
            "run state restored",
            extra={
                "parsed_objects": objects,
                "parsed_bytes": size,
                "parsed_kept": kept,
                "index_id": index_id,
            },
        )
        return report

    async def restore_bundle(self) -> None:
        """Download, check, unpack, ask the publisher, then install. See the module docstring, item 1."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._data_dir, prefix=".run-state-restore-") as scratch:
            bundle = Path(scratch) / "run-state.tar.gz"
            try:
                await self._bucket.get_file(RUN_STATE_BUNDLE_KEY, bundle)
            except NotFound as absent:
                if absent.key != RUN_STATE_BUNDLE_KEY:
                    raise
                raise RunStateBundleMissing from None
            staging = Path(scratch) / "staging"
            staging.mkdir()
            self._files.unpack(bundle, staging)
            await self._refuse_withheld(self._staged(staging), saving=False)
            self._files.install(staging)

    async def _restore_state_files(self) -> tuple[str, ...]:
        listed = {info.key for info in await self._bucket.list_objects(STATE_PREFIX)}
        restored: list[str] = []
        for name in STATE_FILES:
            key = state_key(name)
            if key not in listed:
                continue
            local = self._data_dir / name
            with tempfile.TemporaryDirectory(dir=self._data_dir, prefix=".run-state-file-") as scratch:
                landed = Path(scratch) / name
                await self._bucket.get_file(key, landed)
                if landed.stat().st_size == 0:
                    local.unlink(missing_ok=True)
                else:
                    landed.replace(local)
            restored.append(name)
        return tuple(restored)

    async def _restore_index_manifest(self) -> str | None:
        out = self._data_dir / SEARCH_INDEX_DIRECTORY
        with tempfile.TemporaryDirectory(dir=self._data_dir, prefix=".run-state-index-") as scratch:
            landed = Path(scratch) / "current.json"
            try:
                await self._bucket.get_file(SEARCH_INDEX_POINTER_KEY, landed)
            except NotFound:
                return None
            pointer = SearchIndexPointer.model_validate_json(landed.read_bytes())
            directory = out / pointer.index_id
            if (directory / SEARCH_INDEX_MANIFEST_NAME).is_file() and not (
                directory / RESTORED_INDEX_MARKER
            ).exists():
                # Built on this machine: its files are whole, and a restored manifest would hide them.
                return pointer.index_id
            manifest = Path(scratch) / SEARCH_INDEX_MANIFEST_NAME
            await self._bucket.get_file(pointer.manifest_key, manifest)
            if hashlib.sha256(manifest.read_bytes()).hexdigest() != pointer.manifest_sha256:
                raise BlobIntegrityError(
                    pointer.manifest_key, hashlib.sha256(manifest.read_bytes()).hexdigest()
                )
            directory.mkdir(parents=True, exist_ok=True)
            (directory / RESTORED_INDEX_MARKER).write_text(
                "This directory holds the published index's manifest alone, restored from the bucket "
                "(v1-e40-t04). It is never published from.\n",
                encoding="utf-8",
            )
            manifest.replace(directory / SEARCH_INDEX_MANIFEST_NAME)
            await self._restore_checked_against(pointer, directory, Path(scratch))
        return pointer.index_id

    async def _restore_checked_against(
        self, pointer: SearchIndexPointer, directory: Path, scratch: Path
    ) -> None:
        """The record beside the published manifest of what it was last checked against (`v1-e39-t19`).

        Restored beside the manifest when it stands beside it, and otherwise not: a record that names
        another manifest, or that this build cannot read, is no record of this one.
        """
        restored = directory / CHECKED_AGAINST_NAME
        restored.unlink(missing_ok=True)
        landed = scratch / CHECKED_AGAINST_NAME
        try:
            await self._bucket.get_file(index_object_key(pointer.index_id, CHECKED_AGAINST_NAME), landed)
        except NotFound:
            return
        record = read_checked_against(landed.read_bytes())
        if record is not None and record.stands_beside(pointer):
            landed.replace(restored)

    async def _restore_parsed(self, store: str, version: str) -> tuple[int, int, int]:
        """One store's version directory: (objects fetched, objects already held, bytes fetched)."""
        prefix = f"{PARSED_PREFIX}{store}/{version}/"
        listed = await self._bucket.list_objects(prefix)
        limit = asyncio.Semaphore(_PARALLEL_DOWNLOADS)
        counts = {"fetched": 0, "kept": 0, "bytes": 0}

        async def one(info: ObjectInfo) -> None:
            path = self._data_dir / info.key
            async with limit:
                if path.is_file() and path.stat().st_size == info.size:
                    recorded = (await self._bucket.head(info.key)).sha256
                    if recorded is not None and recorded == _sha256_of(path):
                        counts["kept"] += 1
                        return
                path.parent.mkdir(parents=True, exist_ok=True)
                fetched = await self._bucket.get_file(info.key, path)
                if fetched.sha256 is None:  # pragma: no cover - get_file always states the landed digest
                    raise BlobIntegrityError(info.key, "")
                counts["fetched"] += 1
                counts["bytes"] += fetched.size

        await asyncio.gather(*(one(info) for info in listed))
        return counts["fetched"], counts["kept"], counts["bytes"]

    async def parses_owed(self) -> ParsesOwed:
        """What the bucket's parse-owed file says the cloud run owes, read without restoring (`v1-e40-t08`).

        What `caselist runs --remote` shows. Nothing owed when the bucket holds no such file, or the
        empty object that records it removed. Raises :class:`ParseOwedUnreadable` as the file's own
        reader does.
        """
        key = state_key(PARSE_OWED_FILENAME)
        # Listed first, as the restore lists: a read of a missing key under a prefix-conditioned grant
        # is refused rather than not found.
        if key not in {info.key for info in await self._bucket.list_objects(STATE_PREFIX)}:
            return ParsesOwed()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._data_dir, prefix=".run-state-file-") as scratch:
            landed = Path(scratch) / PARSE_OWED_FILENAME
            await self._bucket.get_file(key, landed)
            if landed.stat().st_size == 0:
                return ParsesOwed()
            return ParseOwed(landed).read()

    # ------------------------------------------------------------------------------------------
    # Raw sources, as the parse needs them
    # ------------------------------------------------------------------------------------------

    async def fetch_sources(self, caselist: str, sources: Sequence[EnumeratedSource]) -> int:
        """Fetch from `raw/` the parsable sources of `caselist` this machine does not hold. Returns how many.

        Each lands in the blob tree only once its bytes hash to its digest, which is its key.
        """
        path_for = self._local.blob_path_for
        if path_for is None:  # pragma: no cover - the composition root always gives one
            return 0
        missing = [
            source
            for source in sources
            if source.source_document().is_parsable and not path_for(local_blob_key(source.sha256)).is_file()
        ]
        limit = asyncio.Semaphore(_PARALLEL_DOWNLOADS)

        async def one(source: EnumeratedSource) -> None:
            key = source_key(caselist, source.disclosures[0].snapshot, source.sha256)
            path = path_for(local_blob_key(source.sha256))
            async with limit:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=path.parent, prefix=".raw-") as scratch:
                    landed = Path(scratch) / source.sha256
                    await self._bucket.get_file(key, landed)
                    digest = _sha256_of(landed)
                    if digest != source.sha256:
                        raise BlobIntegrityError(key, digest)
                    landed.replace(path)

        await asyncio.gather(*(one(source) for source in missing))
        if missing:
            logger.info(
                "raw sources fetched for the parse", extra={"caselist": caselist, "sources": len(missing)}
            )
        return len(missing)

    # ------------------------------------------------------------------------------------------
    # The saves
    # ------------------------------------------------------------------------------------------

    async def save_state_file(self, name: str) -> None:
        """Save one state file as it is now: its bytes, or an empty object when it is gone."""
        key = state_key(name)
        local = self._data_dir / name
        if local.is_file():
            await self._bucket.put_file(key, local)
            return
        with tempfile.TemporaryDirectory(dir=self._data_dir, prefix=".run-state-file-") as scratch:
            gone = Path(scratch) / name
            gone.touch()
            await self._bucket.put_file(key, gone)

    def save_state_file_now(self, path: Path) -> None:
        """:meth:`save_state_file`, from code that is not awaiting: the state files' own writers.

        The upload runs on an event loop of its own in a thread of its own, and this call waits for
        it, so the file is in the bucket before the code that wrote it goes on: a download's start
        is saved before the download starts.
        """
        failures: list[BaseException] = []

        def upload() -> None:
            try:
                asyncio.run(self.save_state_file(path.name))
            except BaseException as failed:  # noqa: BLE001 - re-raised in the caller's thread
                failures.append(failed)

        worker = threading.Thread(target=upload, name="run-state-file")
        worker.start()
        worker.join()
        if failures:
            raise failures[0]

    async def save_state_files(self, names: Iterable[str] = STATE_FILES) -> None:
        for name in names:
            await self.save_state_file(name)

    async def save_bundle(self) -> BundleSave:
        """Save the bundle if every snapshot it records is confirmed in the bucket. See the module docstring.

        Raises :class:`RunStateWithheld` when a local manifest is one the publisher withholds. The held
        uploads are given to the bucket first either way (:meth:`save_held_digests`).
        """
        await self.save_held_digests()
        await self._refuse_withheld(self._local, saving=True)
        unconfirmed = await self.unconfirmed_manifests()
        if unconfirmed:
            return BundleSave(
                saved=False,
                reason=(
                    f"not saved: {len(unconfirmed)} manifest(s) on this machine are not yet confirmed in the "
                    "bucket, so the bucket keeps the previous bundle"
                ),
            )
        with tempfile.TemporaryDirectory(dir=self._data_dir, prefix=".run-state-save-") as scratch:
            bundle = Path(scratch) / "run-state.tar.gz"
            self._files.pack(bundle)
            stored = await self._bucket.put_file(RUN_STATE_BUNDLE_KEY, bundle)
        confirmed = await self._bucket.head(RUN_STATE_BUNDLE_KEY)
        if confirmed.sha256 != stored.sha256 or (
            stored.version_id and confirmed.version_id != stored.version_id
        ):
            return BundleSave(
                saved=False, reason="not confirmed: the bucket holds another bundle than was written"
            )
        return BundleSave(
            saved=True,
            reason=f"saved, {stored.size} bytes, sha256 {stored.sha256}",
            sha256=stored.sha256,
            version_id=stored.version_id,
        )

    async def save_held_digests(self) -> None:
        """Give the bucket's held-digest record the lines this working copy holds and it lacks (`v1-e40-t12`).

        Appended after what is there, which stays byte for byte, a removal's own lines among them; a
        line already there is not written again, and with none to give nothing is written. Through
        the suppression list's own set-union append, over the same fenced adapter as the bundle.
        """
        if isinstance(self._suppression, HeldDigestList):
            await self._suppression.append_held_digests(())

    async def local_manifests(self) -> tuple[ObjectInfo, ...]:
        """This machine's manifests, which the bundle holds."""
        return await self._local.objects.list_objects(f"{MANIFEST_DIRECTORY}/")

    async def refuse_withheld(self) -> None:
        """Raise :class:`RunStateWithheld` when a local manifest is one the publisher withholds."""
        await self._refuse_withheld(self._local, saving=True)

    async def unconfirmed_manifests(self) -> tuple[ObjectKey, ...]:
        """The local manifests the bucket does not hold with the same SHA-256, by key."""
        local = await self._local.objects.list_objects(f"{MANIFEST_DIRECTORY}/")
        path_for = self._local.object_path_for
        unconfirmed: list[ObjectKey] = []
        for info in local:
            if path_for is None:  # pragma: no cover - the composition root always gives one
                digest = (await self._local.objects.head(info.key)).sha256
            else:
                digest = _sha256_of(path_for(info.key))
            try:
                remote = await self._bucket.head(info.key)
            except NotFound:
                unconfirmed.append(info.key)
                continue
            if remote.sha256 != digest:
                unconfirmed.append(info.key)
        return tuple(unconfirmed)

    async def _refuse_withheld(self, evidence: LocalEvidence, *, saving: bool) -> None:
        state = await load_suppression_state(self._suppression)
        ask = self._withheld(evidence)
        for info in await evidence.objects.list_objects(f"{MANIFEST_DIRECTORY}/"):
            withholding = await ask(info, state)
            if withholding is not None:
                raise RunStateWithheld(
                    saving=saving, publisher_says=withholding.message, request_ids=withholding.request_ids
                )


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

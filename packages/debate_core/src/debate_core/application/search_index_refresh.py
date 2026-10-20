"""The weekly run's search index stage: rebuild the index when the parsed store changed, and publish it.

`v1-e39-t09-weekly-index-refresh`. :class:`SearchIndexRefresh` is
:class:`~debate_core.application.caselist_sync.SearchIndexStage` over the two services `tub index
build` and `tub index publish` run (`v1-e39-t02`), and it adds no rule to either: what an index is
built from, what it holds and how it is published, pointer last and each object's sha256 checked as
it lands, are theirs. What is decided here is when each is asked, in the order the PM ruled on
2026-10-20:

1. **Reconcile the suppression list's copies**, when an AWS session exists
   (:meth:`~debate_core.application.caselist.suppression.RecordedSuppressionList.reconcile`), so that
   a removal made on another machine reaches this machine's copy, which is the one the build reads.
   Without a session, or with a bucket that cannot be reached, the build reads this machine's copy
   alone, and the stage says so. That is safe while one machine imports, the condition
   :class:`~debate_core.application.caselist.suppression.LocalFallbackSuppressionList` names for
   revisiting it.
2. **Compute the digests** through
   :meth:`~debate_core.application.search_index_build.SearchIndexBuildService.sources`, the method the
   build's own manifest is computed by: each store's `occurrences_sha256` and the list's `sha256`.
3. **Build, offline, when they differ** from the newest local index's manifest under
   `<data_dir>/tub-index/`, or when that index was built by other versions or settings
   (:func:`built_from`). Otherwise the newest local index is the one the stage keeps current.
4. **Publish it, when a session exists and the published `current.json` names another index**, to
   this environment's bucket. Without a session the stage is pending: "built, publish pending". The
   next run with a session finds `current.json` behind and publishes that same index, without a
   rebuild unless reconciling changed the suppression digest; `tub index publish --index <newest>`
   is the by-hand catch-up (`docs/runbooks/evidence-search.md`).

The agent publishes only to its own environment, dev today. Publishing the index to prod stays the
operator's step until the agent runs against prod (PM ruling 2026-10-20, question 1 (c)).

## What a failure leaves

The previous pointer and the previous local index. A build writes into a scratch directory under
`<data_dir>/tub-index/` and renames it into place only when it is whole, and removes it otherwise; a
publish writes the pointer last. So a failed build or upload changes neither, and the stage's reason
names the index still current: the newest local one and, once read, the one `current.json` names.

## Versions

A store parsed under another parser or fingerprint version than this build runs is
:class:`~debate_core.application.search_index_build.SearchIndexStoreVersionMismatch`, and the stage is
skipped with that reason (ac3): the parser moves to a new version on the day a re-parse lands, and
the agent's build may be the older one until it is reinstalled. Any other store that is not ready
fails the stage, and the previous index stays (PM ruling 2026-10-20, question 3).

## Size

Every build's SQLite bytes and bytes per document are reported, with a warning past either of
ADR-0019's lines: 900,000,000 SQLite bytes, under its 1 GB uncompressed ceiling, and 400,000,000
gzip bytes, its trigger for asking for a higher bandwidth quota (PM ruling 2026-10-20, question 5).

## What is logged and reported

Index ids, which are digests, counts, sizes and versions. No store's rows, no card, and no path: a
reason names a directory by its role.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.caselist_sync import (
    SearchIndexStageCounts,
    SearchIndexStageReport,
    StageOutcome,
)
from debate_core.application.errors import NotFound, StoreCredentialsExpired, StoreError
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.search_index_build import (
    SearchIndexBuildService,
    SearchIndexSources,
    SearchIndexStoreVersionMismatch,
)
from debate_core.application.search_index_publish import (
    SearchIndexFilesDamaged,
    SearchIndexPublishService,
    SearchIndexVersionMismatch,
    UnreadableSearchIndexManifest,
    read_search_index_manifest,
)
from debate_core.domain.search_index import (
    DEFAULT_PROVENANCE_LIMIT,
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SearchIndexManifest,
    SearchIndexPointer,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "GZIP_BYTES_WARNING",
    "SEARCH_INDEX_DIRECTORY",
    "SQLITE_BYTES_WARNING",
    "LocalSearchIndex",
    "SearchIndexRefresh",
    "built_from",
    "newest_local_index",
    "size_warnings",
]

logger = logging.getLogger(__name__)

SEARCH_INDEX_DIRECTORY: Final = "tub-index"
"""Where built indexes live under the data directory, `<data_dir>/tub-index/<index id>/`: where
`tub index build` writes by default, and where this stage builds and looks for the newest."""

SQLITE_BYTES_WARNING: Final = 900_000_000
"""SQLite bytes past which a build is warned of: under ADR-0019's 1 GB uncompressed ceiling."""

GZIP_BYTES_WARNING: Final = 400_000_000
"""Gzip bytes past which a build is warned of: ADR-0019's trigger for a higher bandwidth quota."""


@dataclass(frozen=True, slots=True)
class LocalSearchIndex:
    """One index built on this machine: its directory and its manifest."""

    directory: Path
    manifest: SearchIndexManifest

    @property
    def index_id(self) -> str:
        return self.manifest.index_id


def newest_local_index(out: Path) -> LocalSearchIndex | None:
    """The index under `out` whose manifest was written last, or `None` when there is none.

    A build's scratch directory (a name starting with a dot) and a directory without a readable
    manifest are not indexes and are passed over. Two manifests written in the same instant are
    ordered by index id, so the answer never depends on the order the directory is listed in.
    """
    if not out.is_dir():
        return None
    found: list[tuple[int, str, LocalSearchIndex]] = []
    for directory in out.iterdir():
        if directory.name.startswith(".") or not directory.is_dir():
            continue
        try:
            manifest = read_search_index_manifest(directory)
            written = (directory / SEARCH_INDEX_MANIFEST_NAME).stat().st_mtime_ns
        except (UnreadableSearchIndexManifest, OSError):
            continue
        found.append((written, directory.name, LocalSearchIndex(directory, manifest)))
    return max(found, key=lambda one: (one[0], one[1]))[2] if found else None


def built_from(
    manifest: SearchIndexManifest, sources: SearchIndexSources, *, parser_version: str, provenance_limit: int
) -> bool:
    """Whether `manifest` is an index of exactly `sources`, built by this build's versions and settings.

    The stores' digests and the suppression list's digest first (the PM's rule); then what else
    changes the bytes of an index of the same rows: the parser, fingerprint and format versions, and
    how many occurrences keep their provenance.
    """
    return (
        manifest.stores == sources.stores
        and manifest.suppression == sources.suppression_list
        and manifest.parser_version == parser_version
        and manifest.fingerprint_version == FINGERPRINT_VERSION
        and manifest.format_version == SEARCH_INDEX_FORMAT_VERSION
        and manifest.provenance_limit == provenance_limit
    )


def size_warnings(manifest: SearchIndexManifest) -> tuple[str, ...]:
    """A sentence for each of ADR-0019's lines the index has passed; none for an index under both."""
    warnings: list[str] = []
    if manifest.sqlite_file.bytes > SQLITE_BYTES_WARNING:
        warnings.append(
            f"the SQLite file is {manifest.sqlite_file.bytes:,} bytes, past {SQLITE_BYTES_WARNING:,}: "
            "ADR-0019 plans for 1 GB uncompressed at most, so revisit its sizing"
        )
    if manifest.gzip_object.bytes > GZIP_BYTES_WARNING:
        warnings.append(
            f"the gzip object is {manifest.gzip_object.bytes:,} bytes, past {GZIP_BYTES_WARNING:,}: "
            "ADR-0019's revisit trigger, at which v1-e39-t04 asks for a higher bandwidth quota"
        )
    return tuple(warnings)


def _counts(index: LocalSearchIndex, *, built: bool, published: bool) -> SearchIndexStageCounts:
    manifest = index.manifest
    documents = manifest.counts.documents
    return SearchIndexStageCounts(
        index_id=index.index_id,
        built=built,
        published=published,
        documents=documents,
        sqlite_bytes=manifest.sqlite_file.bytes,
        gzip_bytes=manifest.gzip_object.bytes,
        bytes_per_document=manifest.sqlite_file.bytes // documents if documents else None,
        warnings=size_warnings(manifest),
    )


def _size_sentence(counts: SearchIndexStageCounts) -> str:
    per_document = (
        f", {counts.bytes_per_document:,} bytes a document" if counts.bytes_per_document is not None else ""
    )
    said = (
        f"{counts.documents:,} documents, SQLite file {counts.sqlite_bytes:,} bytes{per_document}, "
        f"gzip object {counts.gzip_bytes:,} bytes"
    )
    return said + "".join(f"; warning: {one}" for one in counts.warnings)


def _locally(newest: LocalSearchIndex | None) -> str:
    """The index this machine keeps, as a failure's reason names it."""
    if newest is None:
        return "no index is built on this machine yet"
    return f"the newest index on this machine stays {newest.index_id}"


def _published(pointer: SearchIndexPointer | None) -> str:
    return (
        f"current.json still names {pointer.index_id}" if pointer is not None else "no index is published yet"
    )


class SearchIndexRefresh:
    """The search index stage of the weekly run: build when the store changed, publish when behind.

    Args:
        builder: `tub index build`'s service, over this machine's parsed store, caselist records and
            local copy of the suppression list.
        out: Where indexes are built: `<data_dir>/tub-index`.
        parser_version: The parser version this build runs, which the builder was built with.
        publisher: `tub index publish`'s service over this environment's bucket, or `None` for an
            environment that names none, where nothing is ever published.
        bucket: The same bucket, read for `current.json`. Required with `publisher`.
        reconcile: Writes each copy of the suppression list what another copy has and it lacks
            (:meth:`~debate_core.application.caselist.suppression.RecordedSuppressionList.reconcile`
            of the list over this machine's copy and the bucket's). Required with `publisher`.
        environment: The environment the agent runs in, which the by-hand catch-up names.
        provenance_limit: How many occurrences of a card keep who disclosed them; `tub index build`'s
            default.
    """

    def __init__(
        self,
        *,
        builder: SearchIndexBuildService,
        out: Path,
        parser_version: str,
        publisher: SearchIndexPublishService | None = None,
        bucket: EvidenceObjectStore | None = None,
        reconcile: Callable[[], Awaitable[None]] | None = None,
        environment: str,
        provenance_limit: int = DEFAULT_PROVENANCE_LIMIT,
    ) -> None:
        if publisher is not None and (bucket is None or reconcile is None):
            raise ValueError("a stage that publishes reads current.json from the bucket and reconciles first")
        self._builder = builder
        self._out = out
        self._parser_version = parser_version
        self._publisher = publisher
        self._bucket = bucket
        self._reconcile = reconcile
        self._environment = environment
        self._provenance_limit = provenance_limit

    async def refresh(self, stores: Sequence[str], *, no_session: str | None) -> SearchIndexStageReport:
        """Keep the index of `stores` current. `no_session` says why the run already knows it has no login.

        Every outcome is a report, failures included, so that the run records them as a stage. Only
        a bug in this method itself escapes, and the run records that as the stage's failure too.
        """
        newest = newest_local_index(self._out)
        publishing = self._publisher is not None

        # 1. Reconcile the suppression copies, when there is a session to do it with.
        local_only: str | None = None
        unreachable: StoreError | None = None
        if publishing and no_session is not None:
            local_only = no_session
        elif publishing:
            try:
                await self._reconciled()
            except StoreCredentialsExpired as expired:
                no_session = str(expired) or "the AWS session has expired"
                local_only = no_session
            except StoreError as refused:
                unreachable = refused
                local_only = f"the bucket's copy could not be reached ({type(refused).__name__})"

        # 2. The digests, through the method the build records them with.
        try:
            sources = await self._builder.sources(stores)
        except SearchIndexStoreVersionMismatch as mismatch:
            return SearchIndexStageReport(
                outcome=StageOutcome.SKIPPED,
                reason=(
                    f"skipped, the parsed store is not this build's version: {mismatch}; {_locally(newest)}"
                ),
                counts=_counts(newest, built=False, published=False) if newest is not None else None,
            )
        except Exception as failed:
            return self._failed(f"the index was not built; {_locally(newest)}", failed, newest, local_only)

        # 3. Build when they differ from the newest local index's.
        current = newest if newest is not None and self._reusable(newest, sources) else None
        if current is None:
            try:
                built = await self._builder.build(
                    stores, self._out, provenance_limit=self._provenance_limit, sources=sources
                )
            except Exception as failed:
                return self._failed(
                    f"the index was not built; {_locally(newest)}", failed, newest, local_only
                )
            current = LocalSearchIndex(built.directory, built.manifest)
        built_now = current is not newest
        said = f"built {current.index_id}" if built_now else f"unchanged since {current.index_id}"
        said += f" ({_size_sentence(_counts(current, built=built_now, published=False))})"
        if local_only is not None:
            said += f"; built from this machine's copy of the suppression list alone: {local_only}"

        def report(outcome: StageOutcome, reason: str, *, published: bool = False) -> SearchIndexStageReport:
            return SearchIndexStageReport(
                outcome=outcome,
                reason=reason,
                counts=_counts(current, built=built_now, published=published),
                local_copy_only=local_only,
            )

        # 4. Publish it when current.json is behind it, and there is a session to do it with.
        if self._publisher is None or self._bucket is None:
            return report(
                StageOutcome.COMPLETED if built_now else StageOutcome.SKIPPED,
                f"{said}; this environment names no evidence bucket, so it is not published",
            )
        if unreachable is not None:
            return self._failed(
                f"{said}; not published, and current.json is as it was",
                unreachable,
                current,
                local_only,
                counts=_counts(current, built=built_now, published=False),
            )
        if no_session is not None:
            return report(StageOutcome.PENDING, self._pending(said, no_session))
        try:
            pointer = await self._published_pointer()
        except StoreCredentialsExpired as expired:
            return report(
                StageOutcome.PENDING, self._pending(said, str(expired) or "the AWS session has expired")
            )
        except Exception as failed:
            return self._failed(
                f"{said}; current.json could not be read, so it is not published",
                failed,
                current,
                local_only,
                counts=_counts(current, built=built_now, published=False),
            )
        if pointer is not None and pointer.index_id == current.index_id:
            if built_now:
                return report(StageOutcome.COMPLETED, f"{said}; current.json already names it")
            return report(
                StageOutcome.SKIPPED, f"{said}, which current.json names: nothing to build or publish"
            )
        try:
            await self._publisher.publish(current.directory)
        except StoreCredentialsExpired as expired:
            return report(
                StageOutcome.PENDING,
                self._pending(
                    f"{said}; {_published(pointer)}", str(expired) or "the AWS session has expired"
                ),
            )
        except Exception as failed:
            return self._failed(
                f"{said}; not published, {_published(pointer)}",
                failed,
                current,
                local_only,
                counts=_counts(current, built=built_now, published=False),
            )
        logger.info(
            "search index published",
            extra={
                "index_id": current.index_id,
                "built": built_now,
                "replaced": pointer.index_id if pointer else None,
            },
        )
        return report(StageOutcome.COMPLETED, f"{said}; published, and current.json names it", published=True)

    # -- the steps ------------------------------------------------------------------------------

    async def _reconciled(self) -> None:
        if self._reconcile is not None:
            await self._reconcile()

    def _reusable(self, newest: LocalSearchIndex, sources: SearchIndexSources) -> bool:
        """The newest local index is an index of `sources`, and, where it may be published, whole.

        Its files are checked against its manifest before it is reused for a publish: a damaged one
        would otherwise fail every run's publish from then on, with nothing to rebuild it.
        """
        if not built_from(
            newest.manifest,
            sources,
            parser_version=self._parser_version,
            provenance_limit=self._provenance_limit,
        ):
            return False
        if self._publisher is None:
            return True
        try:
            self._publisher.check(newest.directory)
        except (SearchIndexFilesDamaged, SearchIndexVersionMismatch, UnreadableSearchIndexManifest):
            return False
        return True

    async def _published_pointer(self) -> SearchIndexPointer | None:
        """What `current.json` names, or `None` when nothing has been published to this bucket."""
        assert self._bucket is not None
        with tempfile.TemporaryDirectory(prefix="tub-index-current-") as scratch:
            landed = Path(scratch) / "current.json"
            try:
                await self._bucket.get_file(SEARCH_INDEX_POINTER_KEY, landed)
            except NotFound:
                return None
            try:
                return SearchIndexPointer.model_validate_json(landed.read_bytes())
            except ValidationError:
                # A pointer this build cannot read is behind by definition: publishing replaces it.
                return None

    def _pending(self, said: str, why: str) -> str:
        return (
            f"{said}; built, publish pending, for want of an AWS login ({why}): the next run with a "
            "session publishes it, and `debate-research tub index publish` with the newest index "
            "under the data directory's tub-index publishes it by hand"
        )

    def _failed(
        self,
        reason: str,
        failed: Exception,
        still: LocalSearchIndex | None,
        local_only: str | None,
        *,
        counts: SearchIndexStageCounts | None = None,
    ) -> SearchIndexStageReport:
        hint = (
            f"`DEBATE_ENV={self._environment} debate-research tub index publish --env {self._environment} "
            f"--index <data_dir>/{SEARCH_INDEX_DIRECTORY}/{still.index_id}` publishes the newest index by "
            "hand once the cause is fixed; the next weekly run tries again either way."
            if counts is not None and still is not None
            else None
        )
        return SearchIndexStageReport(
            outcome=StageOutcome.FAILED,
            reason=reason,
            counts=counts,
            failure=failed,
            hint=hint,
            local_copy_only=local_only,
        )

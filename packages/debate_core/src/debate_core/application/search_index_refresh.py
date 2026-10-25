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

## What is kept on this machine

An index directory is about a gigabyte (the SQLite file and its gzip object), so after a
successful build the stage removes superseded ones (PM amendment 2026-10-20, `v1-e39-t09` review;
:func:`remove_superseded`). It never removes the two newest (:data:`KEEP_NEWEST`, by
:func:`newest_local_index`'s order), the one `current.json` names when the stage read it this run,
a directory without a readable manifest, or a dot-directory, which is a build's scratch directory.
A run that built nothing removes nothing. The bucket's copies are not this stage's: pruning them is
`v1-e39-t07`'s, under the removal credential.

## Size

Every build's SQLite bytes and bytes per document are reported, with a warning past either of
ADR-0019's lines: 1,700,000,000 SQLite bytes, where a same-size swap would fill 79% of the function's
4,096 MB of temporary storage (moved from 900,000,000 by the PM's ruling of 2026-10-22, `v1-e39-t14`),
and 400,000,000 gzip bytes, its trigger for asking for a higher bandwidth quota (PM ruling
2026-10-20, question 5).

## What is logged and reported

Index ids, which are digests, counts, sizes and versions. No store's rows, no card, and no path: a
reason names a directory by its role.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from debate_core.application.caselist_sync import (
    SearchIndexStageCounts,
    SearchIndexStageReport,
    StageOutcome,
)
from debate_core.application.errors import StoreCredentialsExpired, StoreError
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.search_index_build import (
    NotCards,
    SearchIndexBuildService,
    SearchIndexSources,
    SearchIndexStoreVersionMismatch,
    not_cards_by_store,
    not_cards_sentence,
)
from debate_core.application.search_index_publish import (
    ALLOW_SHRINK_FLAG,
    CurrentSearchIndexUnreadable,
    SearchIndexFilesDamaged,
    SearchIndexPublishService,
    SearchIndexVersionMismatch,
    SearchIndexWouldShrink,
    UnreadableSearchIndexManifest,
    read_search_index_manifest,
)
from debate_core.domain.search_index import (
    DEFAULT_PROVENANCE_LIMIT,
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_MANIFEST_NAME,
    SearchIndexManifest,
    SearchIndexPointer,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "GZIP_BYTES_WARNING",
    "KEEP_NEWEST",
    "SEARCH_INDEX_DIRECTORY",
    "SQLITE_BYTES_WARNING",
    "LocalRetention",
    "RESTORED_INDEX_MARKER",
    "LocalSearchIndex",
    "SearchIndexRefresh",
    "built_from",
    "local_indexes",
    "newest_local_index",
    "remove_superseded",
    "restored_from_the_bucket",
    "size_warnings",
]

logger = logging.getLogger(__name__)

SEARCH_INDEX_DIRECTORY: Final = "tub-index"
"""Where built indexes live under the data directory, `<data_dir>/tub-index/<index id>/`: where
`tub index build` writes by default, and where this stage builds and looks for the newest."""

SQLITE_BYTES_WARNING: Final = 1_700_000_000
"""SQLite bytes past which a build is warned of: ADR-0019 (c) 6's storage line. A swap holds the old file
and the new one, so two of this size are 79% of the function's 4,096 MB (`v1-e39-t14`)."""

GZIP_BYTES_WARNING: Final = 400_000_000
"""Gzip bytes past which a build is warned of: ADR-0019's trigger for a higher bandwidth quota."""

RESTORED_INDEX_MARKER: Final = "restored-from-bucket"
"""A file beside the manifest of an index directory a bucket-mode run restored (`v1-e40-t04`).

Such a directory holds the published index's manifest and nothing else: ADR-0020 (3) restores the
manifest alone, so that the stage can compare digests and skip a rebuild. Two rules follow, and the
PM's ruling on the plan (2026-10-24) has a test for each. When the digests match, it is the index the
stage keeps current, without the check of files it does not hold; and it is never published from,
so a digest that differs builds afresh, and a pointer that names another index fails the stage
rather than publishing a manifest without its files."""

KEEP_NEWEST: Final = 2
"""How many of the newest local indexes a build never removes: the one it built and the one before."""


@dataclass(frozen=True, slots=True)
class LocalSearchIndex:
    """One index built on this machine: its directory and its manifest."""

    directory: Path
    manifest: SearchIndexManifest
    not_cards: NotCards | None = None
    """What its build left out as no card, for an index this run built; `None` for one read back from
    its directory, since the count is not in the manifest (`v1-e39-t12`, PM ruling 2026-10-22)."""

    @property
    def index_id(self) -> str:
        return self.manifest.index_id


def restored_from_the_bucket(index: LocalSearchIndex) -> bool:
    """Whether `index` is a published manifest a bucket-mode run restored (:data:`RESTORED_INDEX_MARKER`)."""
    return (index.directory / RESTORED_INDEX_MARKER).exists()


def newest_local_index(out: Path) -> LocalSearchIndex | None:
    """The index under `out` whose manifest was written last, or `None` when there is none.

    The first of :func:`local_indexes`: what this stage keeps current, and what `tub index publish
    --newest` publishes.
    """
    indexes = local_indexes(out)
    return indexes[0] if indexes else None


def local_indexes(out: Path) -> list[LocalSearchIndex]:
    """Every index under `out`, the newest first: by when its manifest was written, then by directory name.

    A build's scratch directory (a name starting with a dot) and a directory without a readable
    manifest are not indexes and are passed over. Two manifests written in the same instant are
    ordered by name, so the answer never depends on the order the directory is listed in.
    """
    if not out.is_dir():
        return []
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
    return [one[2] for one in sorted(found, key=lambda one: (one[0], one[1]), reverse=True)]


@dataclass(frozen=True, slots=True)
class LocalRetention:
    """What :func:`remove_superseded` removed from this machine, and what it could not."""

    removed: tuple[str, ...] = ()
    """The directories removed, by name."""

    bytes_freed: int = 0
    not_removed: tuple[str, ...] = ()
    """Superseded directories the operating system would not let go, by name and error class."""

    @property
    def sentence(self) -> str:
        if not self.removed:
            said = "no superseded index to remove"
        else:
            said = (
                f"removed {len(self.removed)} superseded {'index' if len(self.removed) == 1 else 'indexes'} "
                f"on this machine, {self.bytes_freed:,} bytes freed"
            )
        if self.not_removed:
            said += f"; could not remove {', '.join(self.not_removed)}"
        return said


def remove_superseded(out: Path, *, published: str | None, keep_newest: int = KEEP_NEWEST) -> LocalRetention:
    """Remove the indexes under `out` that are superseded, and say what that freed.

    Kept: the `keep_newest` newest (:func:`local_indexes`' order) and the one `published` names,
    the index id `current.json` gave when it was read, or `None` when it was not. Never touched,
    because :func:`local_indexes` never lists them: a directory without a readable manifest, and a
    dot-directory. A directory that cannot be removed is named and left; it is not a failure.
    """
    removed: list[str] = []
    not_removed: list[str] = []
    freed = 0
    for index in local_indexes(out)[keep_newest:]:
        if published is not None and published in (index.index_id, index.directory.name):
            continue
        size = sum(one.stat().st_size for one in index.directory.rglob("*") if one.is_file())
        try:
            shutil.rmtree(index.directory)
        except OSError as refused:
            not_removed.append(f"{index.directory.name} ({type(refused).__name__})")
            continue
        removed.append(index.directory.name)
        freed += size
    if removed:
        logger.info(
            "superseded search indexes removed", extra={"removed": len(removed), "bytes_freed": freed}
        )
    return LocalRetention(removed=tuple(removed), bytes_freed=freed, not_removed=tuple(not_removed))


@dataclass(slots=True)
class _Seen:
    """What one refresh found on its way, for what follows it: the index it built, and the pointer."""

    built: LocalSearchIndex | None = None
    pointer_read: bool = False
    pointer: SearchIndexPointer | None = field(default=None)


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
            "a swap holds two copies of it in the function's 4,096 MB of ephemeral storage, so revisit "
            "ADR-0019's storage line"
        )
    if manifest.gzip_object.bytes > GZIP_BYTES_WARNING:
        warnings.append(
            f"the gzip object is {manifest.gzip_object.bytes:,} bytes, past {GZIP_BYTES_WARNING:,}: "
            "ADR-0019's revisit trigger, at which v1-e39-t04 asks for a higher bandwidth quota"
        )
    return tuple(warnings)


def _counts(
    index: LocalSearchIndex,
    *,
    built: bool,
    published: bool,
    previous: SearchIndexManifest | None = None,
) -> SearchIndexStageCounts:
    """The stage's counts of `index`, and its growth against `previous`, the index it would replace."""
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
        previous_index_id=previous.index_id if previous is not None else None,
        documents_growth=documents - previous.counts.documents if previous is not None else None,
        sqlite_bytes_growth=manifest.sqlite_file.bytes - previous.sqlite_file.bytes
        if previous is not None
        else None,
        gzip_bytes_growth=manifest.gzip_object.bytes - previous.gzip_object.bytes
        if previous is not None
        else None,
        not_cards_by_store=not_cards_by_store(index.not_cards) if index.not_cards is not None else None,
    )


def _growth_sentence(counts: SearchIndexStageCounts) -> str:
    """`; growth against <id>: +3 documents, ...`, for counts measured against another index."""
    return (
        f"; growth against {counts.previous_index_id}: {counts.documents_growth:+,} documents, "
        f"{counts.sqlite_bytes_growth:+,} SQLite bytes, {counts.gzip_bytes_growth:+,} gzip bytes"
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
        After a successful build, superseded local indexes are removed (:func:`remove_superseded`),
        whatever the publish then did.
        """
        seen = _Seen()
        report = await self._keep_current(stores, no_session=no_session, seen=seen)
        if seen.built is None or report.counts is None:
            return report
        retention = remove_superseded(
            self._out, published=seen.pointer.index_id if seen.pointer_read and seen.pointer else None
        )
        return replace(
            report,
            reason=f"{report.reason}; {retention.sentence}",
            counts=replace(report.counts, removed=len(retention.removed), bytes_freed=retention.bytes_freed),
        )

    async def _keep_current(
        self, stores: Sequence[str], *, no_session: str | None, seen: _Seen
    ) -> SearchIndexStageReport:
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
        # The reason says `local_only` however the bucket's copy was missed. The summary's
        # `suppression_list_local_copy_only` is a login the run did not have and nothing else, so a
        # bucket that refused or did not answer is said in the reason alone.
        login_only = local_only if unreachable is None else None

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
            return self._failed(f"the index was not built; {_locally(newest)}", failed, newest, login_only)

        # 3. Build when they differ from the newest local index's.
        current = newest if newest is not None and self._reusable(newest, sources) else None
        if current is None:
            try:
                built = await self._builder.build(
                    stores, self._out, provenance_limit=self._provenance_limit, sources=sources
                )
            except Exception as failed:
                return self._failed(
                    f"the index was not built; {_locally(newest)}", failed, newest, login_only
                )
            current = LocalSearchIndex(built.directory, built.manifest, built.not_cards)
            seen.built = current
        built_now = current is not newest
        said = f"built {current.index_id}" if built_now else f"unchanged since {current.index_id}"
        said += f" ({_size_sentence(_counts(current, built=built_now, published=False))})"
        if current.not_cards is not None:
            said += f"; {not_cards_sentence(current.not_cards)}"
        if local_only is not None:
            said += f"; built from this machine's copy of the suppression list alone: {local_only}"

        previous: SearchIndexManifest | None = None
        """The index current.json named, once read, when it is another: what growth is against."""

        def counts(*, published: bool = False) -> SearchIndexStageCounts:
            return _counts(current, built=built_now, published=published, previous=previous)

        def report(outcome: StageOutcome, reason: str, *, published: bool = False) -> SearchIndexStageReport:
            return SearchIndexStageReport(
                outcome=outcome,
                reason=reason,
                counts=counts(published=published),
                local_copy_only=login_only,
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
                login_only,
                counts=counts(),
            )
        if no_session is not None:
            return report(StageOutcome.PENDING, self._pending(said, no_session))
        try:
            published = await self._publisher.current(for_index=current.index_id)
        except StoreCredentialsExpired as expired:
            return report(
                StageOutcome.PENDING, self._pending(said, str(expired) or "the AWS session has expired")
            )
        except Exception as failed:
            return self._failed(
                f"{said}; current.json could not be read, so it is not published",
                failed,
                current,
                login_only,
                counts=counts(),
            )
        pointer = published.pointer if published is not None else None
        seen.pointer_read, seen.pointer = True, pointer
        if published is not None and published.index_id != current.index_id:
            previous = published.manifest
            said += _growth_sentence(counts())
        if pointer is not None and pointer.index_id == current.index_id:
            if built_now:
                return report(StageOutcome.COMPLETED, f"{said}; current.json already names it")
            return report(
                StageOutcome.SKIPPED, f"{said}, which current.json names: nothing to build or publish"
            )
        if restored_from_the_bucket(current):
            return report(
                StageOutcome.FAILED,
                f"{said}; it is a copy of a published manifest restored from the bucket, without its "
                f"files, so it is never published, and {_published(pointer)}",
            )
        try:
            # Never with `allow_shrink`: a shrink the guard refuses is published by hand (v1-e39-t14).
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
                login_only,
                counts=counts(),
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
        if self._publisher is None or restored_from_the_bucket(newest):
            return True
        try:
            self._publisher.check(newest.directory)
        except (SearchIndexFilesDamaged, SearchIndexVersionMismatch, UnreadableSearchIndexManifest):
            return False
        return True

    def _pending(self, said: str, why: str) -> str:
        return (
            f"{said}; built, publish pending, for want of an AWS login ({why}): the next run with a "
            "session publishes it, and `debate-research tub index publish --newest` publishes it by hand"
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
        environment = self._environment
        by_hand = f"DEBATE_ENV={environment} debate-research tub index publish --env {environment} --newest"
        if counts is None or still is None:
            hint = None
        elif isinstance(failed, SearchIndexWouldShrink | CurrentSearchIndexUnreadable):
            hint = (
                f"If the shrink is real (a removal, the card-only rule), `{by_hand} {ALLOW_SHRINK_FLAG} "
                f'"<reason>"` publishes {still.index_id} by hand; otherwise restore the store whose '
                "documents went missing. The weekly run never publishes past the shrink guard."
            )
        else:
            hint = (
                f"`{by_hand}` publishes the newest index, {still.index_id}, by hand once the cause is "
                "fixed; the next weekly run tries again either way."
            )
        return SearchIndexStageReport(
            outcome=StageOutcome.FAILED,
            reason=reason,
            counts=counts,
            failure=failed,
            hint=hint,
            local_copy_only=local_only,
        )

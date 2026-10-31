"""`debate-research tub index publish`: one built index to an environment's evidence bucket (`v1-e39-t02`).

:class:`SearchIndexPublishService` takes a directory `tub index build` wrote and puts it under
`reports/tub/search/<index id>/` in the bucket, through the
:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` port the rest of the CLI
publishes through. The pilot's function reads `reports/tub/search/current.json` and follows it
(ADR-0019 (c) 3), so the order of the three writes is the whole safety argument:

1. the gzip object, `search-index.sqlite.gz`, checked against the manifest's digest as it lands;
2. the manifest, `manifest.json`, checked the same way;
3. the pointer, `current.json`, **last**, naming both by key and digest.

A failure at any step leaves the pointer where it was, so a reader that follows it finds the
previous index whole, and never this one half-written. The SQLite file itself is not uploaded:
the gzip object is what the function downloads, and the pointer carries the SQLite file's digest so
the function can check what it decompressed.

## What it refuses

Before anything is uploaded:

* **A version mismatch** (:class:`SearchIndexVersionMismatch`): a manifest whose parser or fingerprint
  version is not the running build's, or whose format version this build does not write. An index
  built by another build would hold card offsets and cluster ids this build's file builder and
  pages do not agree with.
* **Files that are not the manifest's** (:class:`SearchIndexFilesDamaged`): a gzip object whose size or
  digest is not the one the manifest records, or that does not decompress to the SQLite file the
  manifest records.

## The shrink guard (`v1-e39-t14`)

Then the bucket's `current.json` and the manifest it names are read (:meth:`~SearchIndexPublishService.
current`), and :func:`check_index_size` compares the two manifests' documents store by store (PM
ruling 2026-10-22: per store, not just the total). It is the one copy of the rule: `tub index publish`
and the weekly run's search index stage both reach it through :meth:`~SearchIndexPublishService.publish`.

* **A store whose aggregates hold no rows** (:class:`SearchIndexStoreEmpty`): a store the manifest
  records with no occurrence row. Refused with no current index to compare to as well, and never
  overridden: the fix is to rebuild that store's aggregates, or to build without it.
* **A store the current index holds, at 0 documents or under the configured share of its count
  there** (:class:`SearchIndexWouldShrink`; the share is `caselist.search_index_minimum_share_percent`,
  90 by default). A store the current index does not hold is not compared, so a first publish meets
  the empty-store rule alone.
* **A current index that cannot be read** (:class:`CurrentSearchIndexUnreadable`): a pointer or a
  manifest this build cannot read, or a manifest that is not the one the pointer names. There is
  nothing to compare with, so nothing is published.

Each refusal names the store, both counts and the index left current, and is raised before the first
upload, so `current.json` is untouched. `tub index publish --allow-shrink "<reason>"` publishes a real
shrink (a removal, `v1-e39-t12`'s card-only rule): the second and third refusals are then passed, and
the reason and what it passed are in the publish's result and its log line. They are not in the
manifest or the pointer: the deployed function reads both with `extra="forbid"`, so a new field
would make it refuse the index (PM ruling 2026-10-22). The weekly stage never passes a reason.

Nothing here deletes. Pruning superseded versions is `v1-e39-t07`'s, under the removal credential.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, ValidationError

from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo
from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.search_index import (
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    IndexCounts,
    SearchIndexManifest,
    SearchIndexPointer,
    StoreState,
    SuppressionListState,
    index_object_key,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "ALLOW_SHRINK_FLAG",
    "CHECKED_AGAINST_NAME",
    "CheckedAgainstRecord",
    "DEFAULT_MINIMUM_SHARE_PERCENT",
    "SHRINK_REASON_MAX_LENGTH",
    "AllowedShrink",
    "CurrentSearchIndex",
    "CurrentSearchIndexUnreadable",
    "PublishedSearchIndex",
    "RecordedCheck",
    "SearchIndexFilesDamaged",
    "SearchIndexPublishService",
    "SearchIndexStoreEmpty",
    "SearchIndexVersionMismatch",
    "SearchIndexWouldShrink",
    "StoreShrink",
    "UnreadableSearchIndexManifest",
    "check_index_size",
    "read_checked_against",
    "read_search_index_manifest",
]

logger = logging.getLogger(__name__)

_CHUNK: Final = 1024 * 1024

DEFAULT_MINIMUM_SHARE_PERCENT: Final = 90
"""The share of each store's documents in the current index a new index must keep (PM ruling 2026-10-22)."""

ALLOW_SHRINK_FLAG: Final = "--allow-shrink"
"""`tub index publish`'s override, which a refusal names as the way to publish a real shrink."""

SHRINK_REASON_MAX_LENGTH: Final = 200
"""A reason is a line, such as a removal's request id: long enough to say why, too short for a card."""


class SearchIndexVersionMismatch(DomainError):
    """An index built under a parser, fingerprint or format version the running build does not run."""

    def __init__(self, index_id: str, field: str, built: str, running: str) -> None:
        self.index_id = index_id
        self.field = field
        self.built = built
        self.running = running
        super().__init__(
            f"index {index_id} was built with {field} {built}, and this build runs {running}; "
            "rebuild it with `debate-research tub index build` from a store parsed by this build"
        )


class SearchIndexFilesDamaged(DomainError):
    """A file of a built index, or the object as the bucket stored it, is not the one its manifest records."""

    def __init__(self, index_id: str, name: str, reason: str) -> None:
        self.index_id = index_id
        self.name = name
        self.reason = reason
        super().__init__(f"index {index_id}'s {name} {reason}; nothing past it was published")


class UnreadableSearchIndexManifest(DomainError):
    """A directory with no manifest, or one that is not a search index manifest."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"not a built search index: {reason}")


def _left_current(current_index_id: str | None) -> str:
    return (
        f"current.json still names {current_index_id}"
        if current_index_id is not None
        else "no index is published yet"
    )


@dataclass(frozen=True, slots=True)
class StoreShrink:
    """One store a new index holds too few documents of, against the index `current.json` names."""

    store: str
    documents: int
    """The store's documents in the new index; 0 for a store it was not built from."""

    current_documents: int
    """The store's documents in the current index."""

    @property
    def sentence(self) -> str:
        return f"{self.store} has {self.documents:,} documents against {self.current_documents:,}"


class SearchIndexWouldShrink(DomainError):
    """An index that holds too few of a store's documents against the current index; nothing is published.

    The first store is on the error's attributes, for the `--json` envelope's details; the message
    names every one.
    """

    def __init__(
        self,
        index_id: str,
        current_index_id: str,
        shrinks: tuple[StoreShrink, ...],
        minimum_share_percent: int,
    ) -> None:
        first = shrinks[0]
        self.index_id = index_id
        self.current_index_id = current_index_id
        self.store = first.store
        self.documents = first.documents
        self.current_documents = first.current_documents
        self.minimum_share_percent = minimum_share_percent
        self.stores_shrunk = len(shrinks)
        self.shrinks = shrinks
        super().__init__(
            f"index {index_id} would shrink the published search index: "
            f"{'; '.join(one.sentence for one in shrinks)} in index {current_index_id}, at 0 or under "
            f"{minimum_share_percent}%; nothing was published, and {_left_current(current_index_id)}. "
            f'A real shrink (a removal, the card-only rule) is published with {ALLOW_SHRINK_FLAG} "<reason>"'
        )


class SearchIndexStoreEmpty(DomainError):
    """An index built from a store whose aggregates hold no rows; never published, overridden or not."""

    def __init__(
        self, index_id: str, store: str, current_documents: int | None, current_index_id: str | None
    ) -> None:
        self.index_id = index_id
        self.store = store
        self.documents = 0
        self.current_documents = current_documents
        self.current_index_id = current_index_id
        against = (
            f"against {current_documents:,} in index {current_index_id}"
            if current_documents is not None
            else "and the current index holds none of it"
            if current_index_id is not None
            else "with no index published to compare to"
        )
        super().__init__(
            f"index {index_id} was built from {store}, whose aggregates hold no occurrence rows: 0 "
            f"documents {against}; nothing was published, and {_left_current(current_index_id)}. "
            f"Rebuild {store}'s aggregates with `debate-research caselist parse --caselist {store}`, "
            "or build the index without it"
        )


class CurrentSearchIndexUnreadable(DomainError):
    """`current.json`, or the manifest it names, cannot be read, so a new index cannot be compared with it."""

    def __init__(self, index_id: str, reason: str, current_index_id: str | None = None) -> None:
        self.index_id = index_id
        self.reason = reason
        self.current_index_id = current_index_id
        super().__init__(
            f"index {index_id} was not published: {reason}, so its documents cannot be compared with "
            f"the current index's; current.json is as it was. Publish it with {ALLOW_SHRINK_FLAG} "
            '"<reason>" once the current index is understood'
        )


@dataclass(frozen=True, slots=True)
class CurrentSearchIndex:
    """What `current.json` names, and that index's manifest, checked against the pointer's digest."""

    pointer: SearchIndexPointer
    manifest: SearchIndexManifest

    @property
    def index_id(self) -> str:
        return self.pointer.index_id


@dataclass(frozen=True, slots=True)
class AllowedShrink:
    """What an operator's `--allow-shrink` let through: their reason, and the refusal it passed."""

    reason: str
    shrinks: tuple[StoreShrink, ...] = ()
    """The stores the index would otherwise have been refused for."""

    current_unreadable: str | None = None
    """Why the current index could not be compared, when that was the refusal passed."""


def check_index_size(
    manifest: SearchIndexManifest,
    current: CurrentSearchIndex | None,
    *,
    minimum_share_percent: int,
    allow_shrink: str | None = None,
) -> AllowedShrink | None:
    """The shrink guard: refuse an index of an empty store, or one that drops a store's documents.

    `current` is the index `current.json` names, or `None` before anything is published. Raises
    :class:`SearchIndexStoreEmpty` for a store whose aggregates hold no rows, whatever `allow_shrink`
    says, then :class:`SearchIndexWouldShrink` for every store `current` holds documents of that
    `manifest` holds none of, or fewer than `minimum_share_percent` of. With `allow_shrink`, the
    second is returned as what the reason allowed instead of raised.
    """
    held = current.manifest.counts.documents_by_store if current is not None else {}
    current_index_id = current.index_id if current is not None else None
    for store in manifest.stores:
        if store.occurrence_rows == 0:
            raise SearchIndexStoreEmpty(
                manifest.index_id, store.caselist, held.get(store.caselist), current_index_id
            )
    if current is None:
        return None
    documents = manifest.counts.documents_by_store
    shrinks: list[StoreShrink] = []
    for store, current_documents in sorted(held.items()):
        if current_documents == 0:
            continue
        kept = documents.get(store, 0)
        if kept == 0 or kept * 100 < minimum_share_percent * current_documents:
            shrinks.append(StoreShrink(store, kept, current_documents))
    if not shrinks:
        return None
    if allow_shrink is None:
        raise SearchIndexWouldShrink(
            manifest.index_id, current.index_id, tuple(shrinks), minimum_share_percent
        )
    return AllowedShrink(reason=allow_shrink, shrinks=tuple(shrinks))


def _shrink_reason(allow_shrink: str | None) -> str | None:
    """The `--allow-shrink` reason as given, or :class:`ValueError` for one that is not a short line."""
    if allow_shrink is None:
        return None
    reason = allow_shrink.strip()
    if not reason or "\n" in reason or "\r" in reason or len(reason) > SHRINK_REASON_MAX_LENGTH:
        raise ValueError(
            f"an {ALLOW_SHRINK_FLAG} reason is one line of 1 to {SHRINK_REASON_MAX_LENGTH} characters, "
            "such as a removal's request id"
        )
    return reason


@dataclass(frozen=True, slots=True)
class PublishedSearchIndex:
    """What a publish wrote, in the order it wrote it."""

    index_id: str
    object_key: str
    manifest_key: str
    pointer_key: str
    pointer: SearchIndexPointer
    replaced: str | None = None
    """The index `current.json` named before, or `None` for a first publish."""

    allowed_shrink: AllowedShrink | None = None
    """What `--allow-shrink` let through, or `None` for a publish the guard passed by itself."""


CHECKED_AGAINST_NAME: Final = "checked-against.json"
"""The record beside a published index's manifest, `reports/tub/search/<index id>/checked-against.json`."""


class CheckedAgainstRecord(DomainModel):
    """What the index `current.json` names was last checked against, beside its manifest (`v1-e39-t19`).

    An index id is the start of its SQLite file's digest, so a rebuild from a longer suppression list
    whose new entries stop nothing is the same index, and is not published again (`v1-e39-t09`). Its
    manifest then names the list it was first built from. This record says what the rebuild read:
    the part of a manifest a rebuild can change without changing a byte of the index. It stands
    beside the manifest whose digest it names, and beside no other: a manifest written again at that
    key, by a later publish of the same index, has another digest, and the record is then not read.

    Not in the manifest, and not in the pointer: the function checks the manifest's bytes against the
    pointer's digest and reads both with `extra="forbid"`, so either change would make it refuse the
    index. The function never reads this record.
    """

    record_version: Literal[1] = Field(default=1, description="This record's own shape: 1.")
    index_id: NonEmptyText = Field(description="The index it is about: the one `current.json` names.")
    manifest_sha256: Sha256Hex = Field(
        description="The manifest it stands beside, by the digest `current.json` names it with."
    )
    parser_version: NonEmptyText = Field(description="The parser version every store read was parsed by.")
    stores: tuple[StoreState, ...] = Field(description="Every store the rebuild read, by caselist slug.")
    snapshot: NonEmptyText = Field(description="The latest caselist snapshot among the stores read.")
    suppression: SuppressionListState = Field(description="The suppression list the rebuild applied.")
    counts: IndexCounts = Field(description="What the rebuild read, kept and left out.")

    @classmethod
    def of(cls, manifest: SearchIndexManifest, *, beside: SearchIndexPointer) -> CheckedAgainstRecord:
        """What `manifest`'s build read, as a record beside the manifest `beside` names."""
        return cls(
            index_id=manifest.index_id,
            manifest_sha256=beside.manifest_sha256,
            parser_version=manifest.parser_version,
            stores=manifest.stores,
            snapshot=manifest.snapshot,
            suppression=manifest.suppression,
            counts=manifest.counts,
        )

    def stands_beside(self, pointer: SearchIndexPointer) -> bool:
        """Whether this is a record of the index `pointer` names, beside the manifest it names."""
        return self.index_id == pointer.index_id and self.manifest_sha256 == pointer.manifest_sha256

    def to_json_bytes(self) -> bytes:
        """The record's bytes, written the way the manifest's are."""
        return (json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class RecordedCheck:
    """What :meth:`SearchIndexPublishService.record_checked_against` wrote, and what it replaced."""

    record: CheckedAgainstRecord
    key: str
    replaced: CheckedAgainstRecord
    """What the index was checked against before: the record beside its manifest, or the manifest's own."""

    @property
    def sentence(self) -> str:
        """`the suppression list at 6 entries and 0 path holds, where it said 5 and 0`, and the stores read again."""
        new, old = self.record, self.replaced
        said: list[str] = []
        if new.suppression != old.suppression:
            said.append(
                f"the suppression list at {new.suppression.entries:,} entries and "
                f"{new.suppression.path_holds:,} path holds, where it said {old.suppression.entries:,} and "
                f"{old.suppression.path_holds:,}"
            )
        read_again = [store.caselist for store in new.stores if store not in old.stores]
        if read_again:
            said.append(f"the rows of {', '.join(read_again)} as read now")
        return (
            f"recorded what it was checked against beside its manifest, {CHECKED_AGAINST_NAME}: "
            f"{'; '.join(said) or 'the counts of this rebuild'}"
        )


def read_checked_against(raw: bytes) -> CheckedAgainstRecord | None:
    """The record in `raw`, or `None` for bytes that are not one this build reads, which are not read."""
    try:
        return CheckedAgainstRecord.model_validate_json(raw)
    except ValidationError:
        return None


def read_search_index_manifest(directory: Path) -> SearchIndexManifest:
    """The manifest of the index built in `directory`. Raises :class:`UnreadableSearchIndexManifest`."""
    path = directory / SEARCH_INDEX_MANIFEST_NAME
    if not path.is_file():
        raise UnreadableSearchIndexManifest(f"{SEARCH_INDEX_MANIFEST_NAME} is missing")
    try:
        return SearchIndexManifest.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise UnreadableSearchIndexManifest(
            f"{SEARCH_INDEX_MANIFEST_NAME} does not validate ({error.error_count()} error(s))"
        ) from None


class SearchIndexPublishService:
    """Publishes a built index to one bucket, the pointer last."""

    def __init__(
        self,
        *,
        bucket: EvidenceObjectStore,
        parser_version: str,
        fingerprint_version: str = FINGERPRINT_VERSION,
        format_version: int = SEARCH_INDEX_FORMAT_VERSION,
        minimum_share_percent: int = DEFAULT_MINIMUM_SHARE_PERCENT,
    ) -> None:
        """`parser_version` and `fingerprint_version` are the running build's: an index must match both.

        `minimum_share_percent` is the shrink guard's share (:func:`check_index_size`), the setting
        `caselist.search_index_minimum_share_percent`.
        """
        if not 0 <= minimum_share_percent <= 100:
            raise ValueError(f"minimum_share_percent is 0 to 100; got {minimum_share_percent}")
        self._bucket = bucket
        self._minimum_share_percent = minimum_share_percent
        self._running = {
            "parser version": parser_version,
            "fingerprint version": fingerprint_version,
            "format version": str(format_version),
        }

    def check(self, directory: Path) -> SearchIndexManifest:
        """Everything :meth:`publish` refuses on, asked without touching the bucket."""
        manifest = read_search_index_manifest(directory)
        built = {
            "parser version": manifest.parser_version,
            "fingerprint version": manifest.fingerprint_version,
            "format version": str(manifest.format_version),
        }
        for field, running in self._running.items():
            if built[field] != running:
                raise SearchIndexVersionMismatch(manifest.index_id, field, built[field], running)
        _check_gzip_object(directory / SEARCH_INDEX_GZIP_NAME, manifest)
        return manifest

    async def current(self, *, for_index: str = "this") -> CurrentSearchIndex | None:
        """The index `current.json` names, with its manifest; `None` when nothing is published.

        Raises :class:`CurrentSearchIndexUnreadable` for a pointer or manifest this build cannot read,
        or a manifest whose bytes are not the ones the pointer names. `for_index` is the index a
        refusal is about. A session or a bucket that fails is the store's error, raised as it is.
        """
        with tempfile.TemporaryDirectory(prefix="tub-index-current-") as scratch:
            landed = Path(scratch) / "current.json"
            try:
                await self._bucket.get_file(SEARCH_INDEX_POINTER_KEY, landed)
            except NotFound:
                return None
            try:
                pointer = SearchIndexPointer.model_validate_json(landed.read_bytes())
            except ValidationError:
                raise CurrentSearchIndexUnreadable(
                    for_index, "current.json is not a pointer this build reads"
                ) from None
            manifest_path = Path(scratch) / SEARCH_INDEX_MANIFEST_NAME
            try:
                await self._bucket.get_file(pointer.manifest_key, manifest_path)
            except NotFound:
                raise CurrentSearchIndexUnreadable(
                    for_index, "the manifest current.json names is missing", pointer.index_id
                ) from None
            raw = manifest_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != pointer.manifest_sha256:
                raise CurrentSearchIndexUnreadable(
                    for_index,
                    "the manifest in the bucket is not the one current.json names",
                    pointer.index_id,
                )
            try:
                manifest = SearchIndexManifest.model_validate_json(raw)
            except ValidationError:
                raise CurrentSearchIndexUnreadable(
                    for_index, "the manifest current.json names is not one this build reads", pointer.index_id
                ) from None
            if manifest.index_id != pointer.index_id:
                raise CurrentSearchIndexUnreadable(
                    for_index, "the manifest current.json names is another index's", pointer.index_id
                )
            return CurrentSearchIndex(pointer=pointer, manifest=manifest)

    async def checked_against(self, current: CurrentSearchIndex) -> CheckedAgainstRecord:
        """What the index `current` names was last checked against (`v1-e39-t19`).

        The record beside its manifest, when there is one that stands beside it
        (:meth:`CheckedAgainstRecord.stands_beside`); otherwise what its manifest says. A record that
        is not one this build reads, or that names another manifest, is not read.
        """
        with tempfile.TemporaryDirectory(prefix="tub-index-checked-against-") as scratch:
            landed = Path(scratch) / CHECKED_AGAINST_NAME
            try:
                await self._bucket.get_file(index_object_key(current.index_id, CHECKED_AGAINST_NAME), landed)
            except NotFound:
                recorded = None
            else:
                recorded = read_checked_against(landed.read_bytes())
        if recorded is not None and recorded.stands_beside(current.pointer):
            return recorded
        return CheckedAgainstRecord.of(current.manifest, beside=current.pointer)

    async def record_checked_against(
        self, manifest: SearchIndexManifest, current: CurrentSearchIndex
    ) -> RecordedCheck | None:
        """Record beside `current`'s manifest what `manifest`, a rebuild of the same index, was built from.

        `None`, writing nothing, when that is what it was already checked against
        (:meth:`checked_against`). Otherwise the record is uploaded, checked as it lands, through the
        bucket the index is published through: in bucket mode a client the run lock fences, so it is
        written under the run's lock or not at all. Nothing of the index is uploaded, and the pointer
        is not touched.
        """
        return None

    async def publish(self, directory: Path, *, allow_shrink: str | None = None) -> PublishedSearchIndex:
        """Upload the gzip object, then the manifest, then the pointer; each checked as it lands.

        First :meth:`check`, then the shrink guard against :meth:`current`
        (:func:`check_index_size`), both before anything is uploaded. `allow_shrink` is an
        operator's reason for publishing a real shrink, `tub index publish --allow-shrink`'s; the
        weekly stage never passes one.
        """
        reason = _shrink_reason(allow_shrink)
        manifest = self.check(directory)
        unreadable: CurrentSearchIndexUnreadable | None = None
        try:
            current = await self.current(for_index=manifest.index_id)
        except CurrentSearchIndexUnreadable as refused:
            if reason is None:
                raise
            current, unreadable = None, refused
        allowed = check_index_size(
            manifest, current, minimum_share_percent=self._minimum_share_percent, allow_shrink=reason
        )
        if unreadable is not None and reason is not None:
            allowed = AllowedShrink(reason=reason, current_unreadable=unreadable.reason)
        manifest_path = directory / SEARCH_INDEX_MANIFEST_NAME
        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        object_key = index_object_key(manifest.index_id, SEARCH_INDEX_GZIP_NAME)
        manifest_key = index_object_key(manifest.index_id, SEARCH_INDEX_MANIFEST_NAME)

        _landed(
            manifest.index_id,
            SEARCH_INDEX_GZIP_NAME,
            await self._bucket.put_file(object_key, directory / SEARCH_INDEX_GZIP_NAME),
            manifest.gzip_object.sha256,
        )
        _landed(
            manifest.index_id,
            SEARCH_INDEX_MANIFEST_NAME,
            await self._bucket.put_file(manifest_key, manifest_path),
            manifest_sha256,
        )

        pointer = SearchIndexPointer(
            format_version=manifest.format_version,
            index_id=manifest.index_id,
            manifest_key=manifest_key,
            manifest_sha256=manifest_sha256,
            object_key=object_key,
            object_sha256=manifest.gzip_object.sha256,
            sqlite_sha256=manifest.sqlite_file.sha256,
        )
        with tempfile.TemporaryDirectory(prefix="tub-index-pointer-") as scratch:
            pointer_path = Path(scratch) / "current.json"
            pointer_path.write_bytes(pointer.to_json_bytes())
            _landed(
                manifest.index_id,
                "current.json",
                await self._bucket.put_file(SEARCH_INDEX_POINTER_KEY, pointer_path),
                hashlib.sha256(pointer.to_json_bytes()).hexdigest(),
            )
        replaced = (
            current.index_id
            if current is not None
            else unreadable.current_index_id
            if unreadable is not None
            else None
        )
        if allowed is not None:
            logger.warning(
                "search index published past the shrink guard with %s",
                ALLOW_SHRINK_FLAG,
                extra={
                    "index_id": manifest.index_id,
                    "replaced": replaced,
                    "reason": allowed.reason,
                    "stores_shrunk": [one.store for one in allowed.shrinks],
                },
            )
        return PublishedSearchIndex(
            index_id=manifest.index_id,
            object_key=object_key,
            manifest_key=manifest_key,
            pointer_key=SEARCH_INDEX_POINTER_KEY,
            pointer=pointer,
            replaced=replaced,
            allowed_shrink=allowed,
        )


def _check_gzip_object(path: Path, manifest: SearchIndexManifest) -> None:
    """The gzip object is the manifest's, and decompresses to the manifest's SQLite file."""
    name = manifest.gzip_object.name
    if not path.is_file():
        raise SearchIndexFilesDamaged(manifest.index_id, name, "is missing")
    if path.stat().st_size != manifest.gzip_object.bytes or _sha256_of(path) != manifest.gzip_object.sha256:
        raise SearchIndexFilesDamaged(manifest.index_id, name, "is not the file its manifest records")
    inner = hashlib.sha256()
    size = 0
    try:
        with gzip.open(path, "rb") as unzipped:
            for chunk in iter(lambda: unzipped.read(_CHUNK), b""):
                inner.update(chunk)
                size += len(chunk)
    except (OSError, EOFError):
        raise SearchIndexFilesDamaged(manifest.index_id, name, "does not decompress") from None
    if size != manifest.sqlite_file.bytes or inner.hexdigest() != manifest.sqlite_file.sha256:
        raise SearchIndexFilesDamaged(
            manifest.index_id, name, "does not decompress to the SQLite file its manifest records"
        )


def _landed(index_id: str, name: str, stored: ObjectInfo, expected: str) -> None:
    if stored.sha256 != expected:
        raise SearchIndexFilesDamaged(index_id, name, "landed in the bucket with another digest")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()

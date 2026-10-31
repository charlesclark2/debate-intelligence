"""The function's copy of the published search index: fetched, checked, kept fresh (`v1-e39-t06`).

ADR-0019 (c) 3 and 5, as the PM's ruling of 2026-10-20 gives them to this task. The index is not in
the image; the function fetches it the first time a request needs one, and
:class:`SearchIndexHolder` is what does that and hands each request an
:class:`~debate_core.application.evidence_search.EvidenceSearchService` over it.

## Fetching

1. Read the pointer, `reports/tub/search/current.json` (:class:`~debate_core.domain.search_index.
   SearchIndexPointer`), and refuse one whose format version this build does not read: format 2,
   and format 1 while the first weekly update after `v1-e39-t13` builds format 2
   (:data:`~debate_core.domain.search_index.READABLE_SEARCH_INDEX_FORMAT_VERSIONS`). A refused index
   is never served: the one already loaded goes on serving, and with none the search page says
   search is not available.
2. Read the manifest it names, check its bytes against the pointer's digest, and check it names the
   same index, format version and digests.
3. Stream the gzip object through `gunzip` and `sha256` into a new file in the holder's directory,
   counting as it goes, so neither the object nor the SQLite file is ever held in memory and an
   object that inflates past the manifest's size stops there. Refuse it unless both digests and the
   size are the manifest's.
4. Open it read-only and immutable, through the reader the composition root supplies
   (:class:`~debate_core.integrations.local.search_index_reader.SqliteSearchIndexReader`, which
   refuses a file whose application id or format version it does not know).

A refusal is a :class:`SearchIndexRefused`, and the file is deleted. Nothing is ever written to the
bucket, and a file once checked is never written again: it is made read-only.

## Freshness

The pointer is re-read by conditional GET, so an unchanged one costs a `304` and no body. A request
that finds the last check five minutes old or more (:data:`POINTER_RECHECK_INTERVAL`) checks again
before it is answered. That covers an execution environment Lambda froze for longer than that: its
first request after thawing rechecks before it answers, rather than serving a pointer read before the
freeze. A new pointer is fetched to a new path, swapped in, and the old file deleted once no request
is still reading it. An index is never rewritten in place.

A failed recheck leaves the current index serving, and the next check is a full interval later; a
refused pointer is not fetched again until the pointer changes. With no index loaded at all, every
request tries again, and is refused with :class:`SearchIndexUnavailable` until one loads.

**One refresh loop.** :meth:`SearchIndexHolder._refresh` is the one place a request's freshness is
decided, for the pointer and for the suppression list alike.

## The suppression list (`v1-e39-t07`)

The removal suppression list, `manifests/_suppression/suppression-list.jsonl`, is re-read in the same
pass as the pointer, first, by conditional GET, under the same interval. Every lease hands the
request a :class:`ScreenedSearch`, which passes the list read for that request to the search and the
card lookup as ``is_suppressed(source_sha256, disclosure_digest)``. So an occurrence suppressed after
the index was built is hidden from the first request that rechecks after the removal: within five
minutes, and on a thawed environment before it answers (data-use policy, E39 gate item 5). What a
hidden occurrence does to its card is :class:`~debate_core.application.evidence_search.
EvidenceSearchService`'s: a card whose representative is suppressed is not found until the next build.

The list is not allowed to go stale the way an index may. A pointer that cannot be read leaves the
current index serving; a list that cannot be read, or holds a line this build cannot read, refuses
the request with :class:`SearchIndexUnavailable` and leaves the check due, so the next request tries
again. ADR-0019 (c) 5: an environment "never serves a stale list". The log line names the failure's
type, never the list's contents.

A holder built without a list source hides nothing: the tests of `v1-e39-t06` that predate the list.
The function's composition root always gives it one.

## The parser version, for a download (`v1-e39-t08`)

Each loaded index keeps the parser version its manifest names, and every lease hands it on as
:attr:`ScreenedSearch.parser_version`. An occurrence's element indices are the paragraphs that
parser found the card in, so a download is built only when the function's own parser is the same
one: the card page and the download route ask, and switch download off when it is not.

## What the app log learns (`v1-e39-t10`)

Two `INFO` lines, which the function's logging configuration sends to its app log
(:mod:`debate_api.app_logging`), say how the pilot performs and nothing about who used it or for
what:

* `search index <id> loaded in <s> s: <n> bytes from a <m>-byte object; <t> bytes in its directory`,
  once per index an environment fetches. The time runs from the manifest's read to the reader's open,
  the fetch a cold start or a new pointer waits for. The directory's total is taken before the old
  index is deleted, so at a replacement it is the peak the holder puts on `/tmp`: both SQLite files.
* `search answered in <n> ms`, once per search a lease answers, the index already loaded. Not even
  the search's mode: a passage search's words could be any word, that one included. No query, card,
  cursor, filter or user is in either line.

## What never waits

Only a request that searches or shows a card leases the index. Sign-in, the callback, the health
check and the empty search page never do (:meth:`SearchIndexHolder.loaded_caselists` reads what is
loaded without waiting), so a cold environment answers them at once.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
import zlib
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from pydantic import ValidationError

from debate_core.application.errors import DomainError
from debate_core.application.evidence_search import CardSource, EvidenceSearchService, SuppressionPredicate
from debate_core.application.ports.search_index_reader import SearchIndexReader, UnreadableSearchIndex
from debate_core.application.ports.search_index_source import SearchIndexSource, SuppressionListSource
from debate_core.application.ports.suppression import SuppressionEntry, SuppressionState
from debate_core.domain.evidence_search import Card, SearchFilters, SearchPage
from debate_core.domain.search_index import (
    INDEX_ID_LENGTH,
    READABLE_SEARCH_INDEX_FORMAT_VERSIONS,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SearchIndexManifest,
    SearchIndexPointer,
    index_object_key,
)

__all__ = [
    "MANIFEST_MAX_BYTES",
    "ScreenedSearch",
    "SuppressionListUnavailable",
    "POINTER_RECHECK_INTERVAL",
    "ClosableSearchIndexReader",
    "SearchIndexHolder",
    "SearchIndexRefusal",
    "SearchIndexRefused",
    "SearchIndexUnavailable",
]

logger = logging.getLogger(__name__)

POINTER_RECHECK_INTERVAL: Final = timedelta(minutes=5)
"""The longest a request may be answered from a pointer read before it (ADR-0019 (c) 5)."""

MANIFEST_MAX_BYTES: Final = 1024 * 1024
"""A manifest is a few kilobytes; a pointer naming anything this large names no manifest."""

_INFLATE_CHUNK: Final = 1024 * 1024
_INDEX_FILE_SUFFIX: Final = ".sqlite"
_PARTIAL_FILE_SUFFIX: Final = ".part"


class SearchIndexRefusal(StrEnum):
    """Why a published index was not loaded."""

    UNREADABLE_POINTER = "UNREADABLE_POINTER"
    """The pointer is not a pointer, or names keys outside its own index's directory."""

    UNKNOWN_FORMAT_VERSION = "UNKNOWN_FORMAT_VERSION"
    """The pointer or the manifest names an index format version this build does not read."""

    UNREADABLE_MANIFEST = "UNREADABLE_MANIFEST"
    """The manifest is too large or not a search index manifest."""

    MANIFEST_DIGEST_MISMATCH = "MANIFEST_DIGEST_MISMATCH"
    """The manifest's bytes are not the ones the pointer's digest names."""

    MANIFEST_DISAGREES = "MANIFEST_DISAGREES"
    """The manifest names another index, format version or other digests than the pointer."""

    UNREADABLE_OBJECT = "UNREADABLE_OBJECT"
    """The object is not one whole gzip stream: damaged, cut short, or followed by other bytes."""

    OBJECT_DIGEST_MISMATCH = "OBJECT_DIGEST_MISMATCH"
    """The object's bytes, or their count, are not the ones the pointer and the manifest name."""

    INDEX_DIGEST_MISMATCH = "INDEX_DIGEST_MISMATCH"
    """The file the object inflates to, or its size, is not the one the pointer and the manifest name."""

    UNREADABLE_INDEX = "UNREADABLE_INDEX"
    """The file checks out, and the reader still refuses it, or it is another format than its manifest's."""


_REFUSAL_SENTENCES: Final = {
    SearchIndexRefusal.UNREADABLE_POINTER: "the pointer is not a search index pointer this build reads",
    SearchIndexRefusal.UNKNOWN_FORMAT_VERSION: (
        "its format version is not one this build reads, "
        + " or ".join(str(one) for one in sorted(READABLE_SEARCH_INDEX_FORMAT_VERSIONS))
    ),
    SearchIndexRefusal.UNREADABLE_MANIFEST: "its manifest is not a search index manifest",
    SearchIndexRefusal.MANIFEST_DIGEST_MISMATCH: "its manifest is not the one the pointer names",
    SearchIndexRefusal.MANIFEST_DISAGREES: "its manifest and the pointer name different files or formats",
    SearchIndexRefusal.UNREADABLE_OBJECT: "its object is not one whole gzip stream",
    SearchIndexRefusal.OBJECT_DIGEST_MISMATCH: "its object is not the one the pointer names",
    SearchIndexRefusal.INDEX_DIGEST_MISMATCH: "its object does not inflate to the file the pointer names",
    SearchIndexRefusal.UNREADABLE_INDEX: (
        "the reader refuses the file it inflates to, or it is not the format its manifest names"
    ),
}


class SearchIndexRefused(DomainError):
    """A published index that failed a check, and was not loaded. Its file, if any, is deleted."""

    def __init__(self, refusal: SearchIndexRefusal, index_id: str | None = None) -> None:
        self.refusal = refusal
        self.index_id = index_id
        named = f"search index {index_id}" if index_id else "the published search index"
        super().__init__(f"{named} was refused: {_REFUSAL_SENTENCES[refusal]}")


class SearchIndexUnavailable(DomainError):
    """No index is loaded, so nothing can be searched. The cause is on `__cause__`."""

    def __init__(self) -> None:
        super().__init__("no search index is loaded")


class SuppressionListUnavailable(DomainError):
    """The suppression list could not be read, or holds a line this build cannot read."""

    def __init__(self) -> None:
        super().__init__("the suppression list could not be read, so nothing is searched until it is")


class ScreenedSearch:
    """One request's search: the loaded index, with the suppression list read for this request applied.

    The only way a route reaches the index, so a results page, a card page, a copy and `v1-e39-t08`'s
    download all go through the same list. It offers no search without it.
    """

    __slots__ = ("_is_suppressed", "_parser_version", "_service", "_timer")

    def __init__(
        self,
        service: EvidenceSearchService,
        is_suppressed: SuppressionPredicate | None,
        *,
        parser_version: str,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._service = service
        self._is_suppressed = is_suppressed
        self._parser_version = parser_version
        self._timer = timer

    @property
    def parser_version(self) -> str:
        """The parser version the index's manifest says every store it read was parsed by."""
        return self._parser_version

    def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        cursor: str | None = None,
        *,
        passage: bool = False,
    ) -> SearchPage:
        started = self._timer()
        page = self._service.search(
            query, filters, cursor, passage=passage, is_suppressed=self._is_suppressed
        )
        logger.info("search answered in %d ms", round((self._timer() - started) * 1000))
        return page

    def card(self, caselist: str, cluster_id: str) -> Card | None:
        return self._service.card(caselist, cluster_id, is_suppressed=self._is_suppressed)

    def card_source(self, caselist: str, cluster_id: str) -> CardSource | None:
        """Where the card's representative was read from, under this request's list (`v1-e39-t08`)."""
        return self._service.card_source(caselist, cluster_id, is_suppressed=self._is_suppressed)

    def check_cursor(
        self, query: str, filters: SearchFilters | None, cursor: str, *, passage: bool = False
    ) -> None:
        """Refuse, with :class:`~debate_core.domain.evidence_search.InvalidSearchCursor`, a cursor that is
        not this query's, these filters' and this index's: what :meth:`search` would refuse."""
        self._service.check_cursor(query, filters, cursor, passage=passage)


class ClosableSearchIndexReader(SearchIndexReader, Protocol):
    """A reader the holder can close when its index is swapped out."""

    def close(self) -> None: ...


ReaderOpener = Callable[[Path, str], ClosableSearchIndexReader]
"""Opens one checked index file, read-only, given its path and index id."""


@dataclass(eq=False, slots=True)
class _LoadedIndex:
    """One index file in use, and how many requests are reading it."""

    index_id: str
    sqlite_sha256: str
    parser_version: str
    caselists: tuple[str, ...]
    path: Path
    reader: ClosableSearchIndexReader = field(repr=False)
    service: EvidenceSearchService = field(repr=False)
    leases: int = 0
    retired: bool = False


class SearchIndexHolder:
    """The index this execution environment searches, fetched on first need and kept fresh.

    Safe to share between threads. One request at a time checks the pointer, and while it fetches
    a new index the others wait for it: the function serves one request at a time anyway.
    """

    def __init__(
        self,
        source: SearchIndexSource,
        *,
        directory: Path,
        open_reader: ReaderOpener,
        clock: Callable[[], datetime],
        recheck_interval: timedelta = POINTER_RECHECK_INTERVAL,
        build_service: Callable[[SearchIndexReader], EvidenceSearchService] = EvidenceSearchService,
        suppression_list: SuppressionListSource | None = None,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        """`timer` measures the two `INFO` lines' times, in seconds; a test passes its own."""
        self._source = source
        self._suppression_source = suppression_list
        self._suppressed: SuppressionPredicate | None = None
        self._suppression_etag: str | None = None
        self._directory = directory
        self._open_reader = open_reader
        self._clock = clock
        self._interval = recheck_interval
        self._build_service = build_service
        self._timer = timer
        self._lock = threading.Lock()
        self._current: _LoadedIndex | None = None
        self._checked_at: datetime | None = None
        self._etag: str | None = None
        self._refused: SearchIndexRefused | None = None
        directory.mkdir(parents=True, exist_ok=True)
        self._clear_leftovers()

    # What a request asks for ----------------------------------------------------------------

    @contextmanager
    def lease(self) -> Generator[ScreenedSearch]:
        """The search over the current index and the suppression list, checked fresh, for one request.

        Raises :class:`SearchIndexUnavailable` when no index can be loaded, or the suppression list
        cannot be read. An index swapped out while a request holds it is deleted when that request
        lets it go.
        """
        with self._lock:
            self._refresh_if_due()
            loaded = self._current
            if loaded is None:
                raise SearchIndexUnavailable() from self._refused
            screened = ScreenedSearch(
                loaded.service, self._suppressed, parser_version=loaded.parser_version, timer=self._timer
            )
            loaded.leases += 1
        try:
            yield screened
        finally:
            with self._lock:
                loaded.leases -= 1
                if loaded.retired and loaded.leases == 0:
                    self._discard(loaded)

    def loaded_caselists(self) -> tuple[str, ...]:
        """The stores the loaded index was built from, or none: never fetches and never waits."""
        loaded = self._current
        return loaded.caselists if loaded is not None else ()

    @property
    def loaded_index_id(self) -> str | None:
        """The index being searched, or `None` before one loads. Never fetches."""
        loaded = self._current
        return loaded.index_id if loaded is not None else None

    def close(self) -> None:
        """Close the current index and delete its file; the next lease fetches one again."""
        with self._lock:
            if self._current is not None:
                self._discard(self._current)
            self._current, self._checked_at, self._etag, self._refused = None, None, None, None
            self._suppressed, self._suppression_etag = None, None

    # The refresh loop -----------------------------------------------------------------------

    def _refresh_if_due(self) -> None:
        now = self._clock()
        checked = self._checked_at
        if self._current is not None and checked is not None and checked <= now < checked + self._interval:
            return
        try:
            self._refresh()
        except SuppressionListUnavailable as problem:
            # The check stays due: the next request reads the list again before it answers.
            raise SearchIndexUnavailable() from problem
        except DomainError as problem:
            if self._current is None:
                self._checked_at = now
                raise SearchIndexUnavailable() from problem
            logger.warning(
                "the search index was not refreshed; index %s still serves: %s",
                self._current.index_id,
                type(problem).__name__,
            )
        self._checked_at = now

    def _refresh(self) -> None:
        """One pass of the refresh loop: the suppression list, then the pointer."""
        self._refresh_suppression_list()
        self._refresh_pointer()

    def _refresh_suppression_list(self) -> None:
        source = self._suppression_source
        if source is None:
            return
        try:
            read = source.read_suppression_list(if_none_match=self._suppression_etag)
            if read.body is None:
                if self._suppressed is not None:
                    return
                raise ValueError("the list answered unchanged to a holder that never read it")
            state = _suppression_state(read.body)
        except (DomainError, ValueError) as problem:
            logger.warning(
                "the suppression list was not read, so no search is answered until it is: %s",
                type(problem).__name__,
            )
            raise SuppressionListUnavailable() from None
        self._suppressed = _predicate(state)
        self._suppression_etag = read.etag

    def _refresh_pointer(self) -> None:
        read = self._source.read_pointer(if_none_match=self._etag)
        if read.body is None:
            if self._current is None and self._refused is not None:
                raise self._refused
            return
        try:
            pointer = _parse_pointer(read.body)
            current = self._current
            if current is not None and (pointer.index_id, pointer.sqlite_sha256) == (
                current.index_id,
                current.sqlite_sha256,
            ):
                self._etag, self._refused = read.etag, None
                return
            loaded = self._load(pointer)
        except SearchIndexRefused as refused:
            # Remembered by the pointer's tag, so the same refused index is not fetched again.
            self._etag, self._refused = read.etag, refused
            logger.warning("%s", refused)
            raise
        self._etag, self._refused = read.etag, None
        self._swap(loaded)

    # Fetching one index ---------------------------------------------------------------------

    def _load(self, pointer: SearchIndexPointer) -> _LoadedIndex:
        index_id = pointer.index_id
        started = self._timer()
        manifest = self._manifest(pointer)
        path = self._directory / f"{index_id}-{uuid.uuid4().hex}{_INDEX_FILE_SUFFIX}"
        self._download(pointer, manifest, path)
        try:
            reader = self._open_reader(path, index_id)
        except UnreadableSearchIndex:
            path.unlink(missing_ok=True)
            raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_INDEX, index_id) from None
        if reader.format_version != manifest.format_version:
            reader.close()
            path.unlink(missing_ok=True)
            raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_INDEX, index_id)
        logger.info(
            "search index %s loaded in %.2f s: %d bytes from a %d-byte object; %d bytes in its directory",
            index_id,
            self._timer() - started,
            path.stat().st_size,
            manifest.gzip_object.bytes,
            self._directory_bytes(),
        )
        return _LoadedIndex(
            index_id=index_id,
            sqlite_sha256=pointer.sqlite_sha256,
            parser_version=manifest.parser_version,
            caselists=tuple(store.caselist for store in manifest.stores),
            path=path,
            reader=reader,
            service=self._build_service(reader),
        )

    def _manifest(self, pointer: SearchIndexPointer) -> SearchIndexManifest:
        index_id = pointer.index_id
        try:
            raw = self._source.read_object(pointer.manifest_key, max_bytes=MANIFEST_MAX_BYTES)
        except ValueError:
            raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_MANIFEST, index_id) from None
        if hashlib.sha256(raw).hexdigest() != pointer.manifest_sha256:
            raise SearchIndexRefused(SearchIndexRefusal.MANIFEST_DIGEST_MISMATCH, index_id)
        try:
            manifest = SearchIndexManifest.model_validate_json(raw)
        except ValidationError:
            raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_MANIFEST, index_id) from None
        if manifest.format_version not in READABLE_SEARCH_INDEX_FORMAT_VERSIONS:
            raise SearchIndexRefused(SearchIndexRefusal.UNKNOWN_FORMAT_VERSION, index_id)
        if (
            manifest.index_id,
            manifest.format_version,
            manifest.gzip_object.sha256,
            manifest.sqlite_file.sha256,
        ) != (index_id, pointer.format_version, pointer.object_sha256, pointer.sqlite_sha256):
            raise SearchIndexRefused(SearchIndexRefusal.MANIFEST_DISAGREES, index_id)
        return manifest

    def _download(self, pointer: SearchIndexPointer, manifest: SearchIndexManifest, path: Path) -> None:
        """The object through gunzip and sha256 into `path`, or nothing at `path` and an error."""
        index_id = pointer.index_id
        object_limit, file_limit = manifest.gzip_object.bytes, manifest.sqlite_file.bytes
        compressed, inflated = hashlib.sha256(), hashlib.sha256()
        inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        received = written = 0
        partial = path.with_suffix(_PARTIAL_FILE_SUFFIX)
        chunks = self._source.stream_object(pointer.object_key)
        try:
            with partial.open("xb") as out:
                for chunk in chunks:
                    received += len(chunk)
                    if received > object_limit:
                        raise SearchIndexRefused(SearchIndexRefusal.OBJECT_DIGEST_MISMATCH, index_id)
                    compressed.update(chunk)
                    pending = chunk
                    while pending:
                        if inflater.eof:
                            raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_OBJECT, index_id)
                        data = inflater.decompress(pending, _INFLATE_CHUNK)
                        written += len(data)
                        if written > file_limit:
                            raise SearchIndexRefused(SearchIndexRefusal.INDEX_DIGEST_MISMATCH, index_id)
                        inflated.update(data)
                        out.write(data)
                        pending = inflater.unconsumed_tail or inflater.unused_data
            if not inflater.eof:
                raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_OBJECT, index_id)
            if received != object_limit or compressed.hexdigest() != pointer.object_sha256:
                raise SearchIndexRefused(SearchIndexRefusal.OBJECT_DIGEST_MISMATCH, index_id)
            if written != file_limit or inflated.hexdigest() != pointer.sqlite_sha256:
                raise SearchIndexRefused(SearchIndexRefusal.INDEX_DIGEST_MISMATCH, index_id)
            os.chmod(partial, 0o444)
            partial.rename(path)
        except zlib.error:
            partial.unlink(missing_ok=True)
            raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_OBJECT, index_id) from None
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        finally:
            close = getattr(chunks, "close", None)
            if callable(close):
                close()

    # Swapping -------------------------------------------------------------------------------

    def _swap(self, loaded: _LoadedIndex) -> None:
        previous, self._current = self._current, loaded
        if previous is not None:
            previous.retired = True
            if previous.leases == 0:
                self._discard(previous)

    def _discard(self, loaded: _LoadedIndex) -> None:
        loaded.reader.close()
        loaded.path.unlink(missing_ok=True)
        logger.info("search index %s closed and deleted", loaded.index_id)

    def _directory_bytes(self) -> int:
        """The bytes of every file in the holder's directory: what it has on `/tmp` at this moment."""
        return sum(entry.stat().st_size for entry in self._directory.iterdir() if entry.is_file())

    def _clear_leftovers(self) -> None:
        """Delete index files a previous process in this environment left: /tmp outlives a process."""
        for leftover in self._directory.iterdir():
            if leftover.is_file() and leftover.suffix in (_INDEX_FILE_SUFFIX, _PARTIAL_FILE_SUFFIX):
                leftover.unlink(missing_ok=True)


def _suppression_state(raw: bytes) -> SuppressionState:
    """The list in `raw`, every line read, or :class:`ValueError` at the first line this build cannot read.

    A list whose last line has no newline was cut off in the middle of an append, and is refused
    whole, as every reader of the list refuses it.
    """
    if raw and not raw.endswith(b"\n"):
        raise ValueError("the suppression list's last line is unfinished")
    try:
        lines = raw.decode("utf-8").splitlines()
        return SuppressionState.from_entries(
            SuppressionEntry.from_line(line) for line in lines if line.strip()
        )
    except (UnicodeDecodeError, ValidationError):
        raise ValueError("the suppression list holds a line this build cannot read") from None


def _predicate(state: SuppressionState) -> SuppressionPredicate:
    """``is_suppressed(source_sha256, disclosure_digest)`` over one reading of the list.

    The question the index build asked of every row: the whole source, or this one disclosure. A
    camp occurrence has no disclosure digest, so only a whole-source entry stops it.
    """

    def is_suppressed(source_sha256: str, disclosure: str | None) -> bool:
        return state.suppresses(source_sha256, disclosure=disclosure)

    return is_suppressed


def _parse_pointer(raw: bytes) -> SearchIndexPointer:
    """The pointer in `raw`, naming its own index's manifest and object, or :class:`SearchIndexRefused`."""
    try:
        pointer = SearchIndexPointer.model_validate_json(raw)
    except ValidationError:
        raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_POINTER) from None
    index_id = pointer.index_id
    if pointer.format_version not in READABLE_SEARCH_INDEX_FORMAT_VERSIONS:
        raise SearchIndexRefused(SearchIndexRefusal.UNKNOWN_FORMAT_VERSION, index_id)
    try:
        expected = (
            index_object_key(index_id, SEARCH_INDEX_MANIFEST_NAME),
            index_object_key(index_id, SEARCH_INDEX_GZIP_NAME),
        )
    except ValueError:
        raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_POINTER) from None
    if (pointer.manifest_key, pointer.object_key) != expected:
        raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_POINTER, index_id)
    if pointer.sqlite_sha256[:INDEX_ID_LENGTH] != index_id:
        raise SearchIndexRefused(SearchIndexRefusal.UNREADABLE_POINTER, index_id)
    return pointer

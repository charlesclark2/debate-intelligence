"""The port the pilot's function fetches its published index through (`v1-e39-t06`, ADR-0019 (c) 3 and 5).

`tub index publish` (`v1-e39-t02`) puts each index under `reports/tub/search/<index id>/` and writes
the pointer, `reports/tub/search/current.json`, last. The function reads three things, and only
these, through a :class:`SearchIndexSource`:

* **the pointer**, by conditional GET: an unchanged pointer costs a `304` and no body, which is what
  makes re-reading it every five minutes free (:meth:`SearchIndexSource.read_pointer`);
* **the manifest** the pointer names, a few kilobytes (:meth:`SearchIndexSource.read_object`);
* **the gzip object**, streamed in chunks and never held whole (:meth:`SearchIndexSource.stream_object`).

Beside them it reads the removal suppression list, through a :class:`SuppressionListSource`, the same
way it reads the pointer (`v1-e39-t07`).

What is done with them (the digests, the format version, where the file lands) is
:class:`~debate_core.application.search_index_holder.SearchIndexHolder`'s. An adapter only fetches.
:class:`~debate_core.integrations.s3.search_index_source.S3SearchIndexSource` is the one the function
wires, and its role may `s3:GetObject` under `reports/tub/search/` and nothing else there: no list,
no write (ADR-0019, The function's role).

Synchronous, unlike :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`: the
holder runs in the request's worker thread and blocks it on purpose, since a request that needs the
index cannot answer until it is there. Errors come from :mod:`debate_core.application.errors`:
:class:`~debate_core.application.errors.NotFound`, a
:class:`~debate_core.application.errors.StoreError`, and never a `botocore` exception.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

__all__ = ["SUPPRESSION_LIST_MAX_BYTES", "PointerRead", "SearchIndexSource", "SuppressionListSource"]

SUPPRESSION_LIST_MAX_BYTES: Final = 16 * 1024 * 1024
"""A suppression line is a few hundred bytes, so this is tens of thousands of removals; a list past
it is refused rather than read without a bound."""


@dataclass(frozen=True, slots=True)
class PointerRead:
    """What one conditional read of the pointer found.

    `body` is `None` when the pointer is the one the caller named by its entity tag (an HTTP `304`);
    otherwise it is the pointer's bytes and `etag` is the tag to name it by next time.
    """

    body: bytes | None = field(repr=False)
    etag: str | None

    @property
    def unchanged(self) -> bool:
        return self.body is None


@runtime_checkable
class SearchIndexSource(Protocol):
    """Fetches the published pointer, manifest and index object. Never writes or lists."""

    def read_pointer(self, *, if_none_match: str | None) -> PointerRead:
        """`current.json`, unless its entity tag is still `if_none_match`.

        Raises :class:`~debate_core.application.errors.NotFound` when nothing is published.
        """
        ...

    def read_object(self, key: str, *, max_bytes: int) -> bytes:
        """A small object whole, such as a manifest. Refuses one longer than `max_bytes`.

        A longer object raises :class:`ValueError` before more than `max_bytes` are read: a
        manifest is a few kilobytes, and anything far larger is not one.
        """
        ...

    def stream_object(self, key: str) -> Iterator[bytes]:
        """An object's bytes in order, in chunks. Closing the iterator releases the connection."""
        ...


@runtime_checkable
class SuppressionListSource(Protocol):
    """Reads the removal suppression list, `manifests/_suppression/suppression-list.jsonl` (`v1-e39-t07`).

    The fourth thing the function reads, and the only one outside `reports/tub/search/`. Read the way
    the pointer is, by conditional GET, so the five-minute re-read of an unchanged list costs a `304`.
    """

    def read_suppression_list(self, *, if_none_match: str | None) -> PointerRead:
        """The list's bytes, unless its entity tag is still `if_none_match`.

        A list that does not exist has no lines, and comes back as an empty body. Raises
        :class:`ValueError` for a list longer than :data:`SUPPRESSION_LIST_MAX_BYTES`.
        """
        ...

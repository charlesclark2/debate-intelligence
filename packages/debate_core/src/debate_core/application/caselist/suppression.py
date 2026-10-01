"""The suppression list and the removal log over their copies: merged, append-only, typed.

The port (:mod:`debate_core.application.ports.suppression`) says what an entry is and what a copy
may do. This module is the part that is the same whichever copies a command holds:

* :class:`RecordedSuppressionList` and :class:`RecordedRemovalLog` read every copy they are given as
  one set of lines and, on every append, write each copy the lines it lacks — the new entries, and
  any entry another copy already had. That is the set-union merge spec ac4 asks for, done on every
  write, and it is why a removal made from one machine reaches the bucket and a removal recorded in
  the bucket reaches this machine's copy the next time either is written.
* :class:`ObjectStoreAppendOnlyRecord` is one copy kept as a named object —
  `manifests/_suppression/suppression-list.jsonl` in the bucket — through the
  :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` port. An object cannot
  be appended to in place, so an append reads the object, adds lines to the end of what it read,
  writes it back, and checks that what is now there still begins with every byte that was there
  before. The bucket is versioned, so the previous version is kept as well.

The local copy is :class:`~debate_core.integrations.local.suppression_list.LocalAppendOnlyFile`.

## Which copies a command holds

The composition root decides, by one rule: a command reads every copy it can reach without being
given anything new to reach. `caselist import` never talks to a bucket — it runs offline — so it
reads this environment's local copy. `caselist publish`, `status`, `pull`, `remove` and
`unsuppress` already hold the bucket, so they read the union. Every command that writes the list
writes the union to both, so the local copy is never behind the bucket on the machine that made a
removal.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.errors import NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey, validate_object_key
from debate_core.application.ports.suppression import (
    AppendOnlyRecord,
    AppendOnlyViolation,
    RemovalLogEntry,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    UnreadableAppendOnlyRecord,
)

__all__ = [
    "REMOVAL_LOG_KEY",
    "SUPPRESSION_LIST_KEY",
    "SUPPRESSION_PREFIX",
    "ObjectStoreAppendOnlyRecord",
    "RecordedRemovalLog",
    "RecordedSuppressionList",
    "is_suppression_key",
    "load_suppression_state",
]

SUPPRESSION_PREFIX: Final = "manifests/_suppression/"
"""Where both records live in the bucket. The one prefix the takedown credential may write."""

SUPPRESSION_LIST_KEY: Final = validate_object_key(f"{SUPPRESSION_PREFIX}suppression-list.jsonl")
REMOVAL_LOG_KEY: Final = validate_object_key(f"{SUPPRESSION_PREFIX}removal-log.jsonl")


def is_suppression_key(key: str) -> bool:
    """Whether `key` is under `manifests/_suppression/`, which only remove and unsuppress may write."""
    return key.startswith(SUPPRESSION_PREFIX)


async def load_suppression_state(suppression: SuppressionList) -> SuppressionState:
    """What `suppression` currently suppresses."""
    return SuppressionState.from_entries(await suppression.entries())


class _MergedLines:
    """Several copies of one append-only record, read as one and written as a set union of lines."""

    def __init__(self, records: Sequence[AppendOnlyRecord]) -> None:
        if not records:
            raise ValueError("an append-only record needs at least one copy")
        self._records = tuple(records)

    @property
    def records(self) -> tuple[AppendOnlyRecord, ...]:
        return self._records

    async def read(self) -> list[tuple[str, str, int]]:
        """Every distinct line across the copies, first-seen order, with where it was first read."""
        seen: set[str] = set()
        merged: list[tuple[str, str, int]] = []
        for record in self._records:
            for number, line in enumerate(await record.read_lines(), start=1):
                if line not in seen:
                    seen.add(line)
                    merged.append((line, record.location, number))
        return merged

    async def append(self, lines: Sequence[str]) -> None:
        """Give every copy each line of the union, plus `lines`, that it does not already hold."""
        wanted = [line for line, _, _ in await self.read()]
        known = set(wanted)
        wanted.extend(line for line in dict.fromkeys(lines) if line not in known)
        for record in self._records:
            present = set(await record.read_lines())
            missing = [line for line in wanted if line not in present]
            if missing:
                await record.append_lines(missing)


class RecordedSuppressionList:
    """A :class:`~debate_core.application.ports.suppression.SuppressionList` over one or more copies.

    ::

        suppression = RecordedSuppressionList(local_copy, bucket_copy)
        state = await load_suppression_state(suppression)

    The first copy is the one a message names when a line cannot be read. Entries are returned
    deduplicated; their order does not matter (see
    :class:`~debate_core.application.ports.suppression.SuppressionState`).
    """

    def __init__(self, *records: AppendOnlyRecord) -> None:
        self._lines = _MergedLines(records)

    @property
    def records(self) -> tuple[AppendOnlyRecord, ...]:
        return self._lines.records

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        return tuple(_parse(SuppressionEntry, *read) for read in await self._lines.read())

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:
        await self._lines.append([entry.to_line() for entry in entries])

    async def reconcile(self) -> None:
        """Write every copy the entries another copy has and it lacks. Appends nothing new."""
        await self._lines.append([])


class RecordedRemovalLog:
    """A :class:`~debate_core.application.ports.suppression.RemovalLog` over one or more copies."""

    def __init__(self, *records: AppendOnlyRecord) -> None:
        self._lines = _MergedLines(records)

    @property
    def records(self) -> tuple[AppendOnlyRecord, ...]:
        return self._lines.records

    async def entries(self) -> tuple[RemovalLogEntry, ...]:
        return tuple(_parse(RemovalLogEntry, *read) for read in await self._lines.read())

    async def append(self, entries: Sequence[RemovalLogEntry]) -> None:
        await self._lines.append([entry.to_line() for entry in entries])


def _parse[EntryT: (SuppressionEntry, RemovalLogEntry)](
    kind: type[EntryT], line: str, location: str, number: int
) -> EntryT:
    try:
        return kind.model_validate_json(line)
    except ValidationError as refused:
        # Pydantic's description of the field that failed, never the line itself.
        raise UnreadableAppendOnlyRecord(location, number, refused.errors()[0]["msg"]) from None


class ObjectStoreAppendOnlyRecord:
    """One copy of an append-only record kept as a named object: the bucket's copy.

    Works over any :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`, so
    the same class keeps the bucket's copy through the S3 adapter and, in tests, a directory's copy
    through the filesystem one.

    An append is read, extend, write, verify:

    1. The object is downloaded (absent means empty).
    2. The new bytes are the old bytes followed by the new lines — built that way, so they cannot
       be anything else.
    3. They are uploaded over the object; the bucket keeps the previous version.
    4. The object is read back and must begin with every old byte and end with the new lines. If
       something else wrote it in between, that is an
       :class:`~debate_core.application.ports.suppression.AppendOnlyViolation` naming the key, and
       the caller re-runs; nothing is retried behind its back.
    """

    def __init__(self, store: EvidenceObjectStore, key: ObjectKey, *, location: str | None = None) -> None:
        self._store = store
        self._key = validate_object_key(key)
        self._location = location or key

    @property
    def location(self) -> str:
        return self._location

    @property
    def key(self) -> ObjectKey:
        return self._key

    async def read_lines(self) -> tuple[str, ...]:
        return _lines_of(await self._read_bytes(), self._location)

    async def append_lines(self, lines: Sequence[str]) -> None:
        if not lines:
            return
        for line in lines:
            if "\n" in line or "\r" in line:
                raise AppendOnlyViolation(self._location, "a line to append contains a line break")
        before = await self._read_bytes()
        _lines_of(before, self._location)  # refuses a torn last line before anything is written
        after = before + "".join(f"{line}\n" for line in lines).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="debate-append-") as directory:
            staged = Path(directory) / "record.jsonl"
            staged.write_bytes(after)
            await self._store.put_file(self._key, staged)
        landed = await self._read_bytes()
        if not landed.startswith(before) or landed != after:
            raise AppendOnlyViolation(
                self._location, "the object changed while it was being appended to; re-run the command"
            )

    async def _read_bytes(self) -> bytes:
        with tempfile.TemporaryDirectory(prefix="debate-append-") as directory:
            staged = Path(directory) / "record.jsonl"
            try:
                await self._store.get_file(self._key, staged)
            except NotFound:
                return b""
            return staged.read_bytes()


def _lines_of(data: bytes, location: str) -> tuple[str, ...]:
    """The lines of a record's bytes, refusing one whose last line was never finished."""
    if not data:
        return ()
    if not data.endswith(b"\n"):
        lines = data.count(b"\n") + 1
        raise UnreadableAppendOnlyRecord(
            location, lines, "the last line has no newline (a write was interrupted)"
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnreadableAppendOnlyRecord(location, 0, "not UTF-8") from None
    return tuple(line for line in text.split("\n")[:-1])

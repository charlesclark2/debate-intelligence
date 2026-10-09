"""The parsed card store as JSONL files under `<data_dir>/parsed/`.

The filesystem implementation of :class:`~debate_core.application.ports.parsed_store.ParsedStore`.
A key in the port's layout is a path under the store's root, so this directory and the bucket's
`parsed/` prefix hold the same files at the same names, and publishing is a copy
(:mod:`debate_core.application.caselist.parsed_publish`)::

    <data_dir>/parsed/hsld26/2026.09.20-docx-1/sha256/ab/cd/abcd…ef01.jsonl
    <data_dir>/parsed/hsld26/2026.09.20-docx-1/index.jsonl

## How a file is written

Whole or not at all: every write goes to a temporary file in the destination's directory and is
renamed into place (:func:`~debate_core.integrations.file_streaming.atomic_replacement`). A run
stopped part-way leaves only complete per-source files, which the next run skips.

Lines are compact JSON with sorted keys, so the same record always writes the same bytes. That is
what lets a re-publish compare a file's checksum with the bucket's and upload nothing.

## The two refusals

:meth:`LocalParsedStore.put_source` will not write into a version directory that is not the newest
generation of the entry's own parser version, and will not replace a source's file unless the entry
already there is one the next run retries. Those are the task spec's forbidden overwrite of an
earlier parser version, made a property of the adapter rather than of every caller.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

from debate_core.application.ports.parsed_store import (
    FAILURES_NAME,
    INDEX_NAME,
    OCCURRENCES_NAME,
    PARSED_PREFIX,
    DocumentRecord,
    OccurrenceRecord,
    ParsedStoreRefusal,
    SourceEntry,
    SourceOutcome,
    StoreRecord,
    parse_version_directory,
    source_object_key,
)
from debate_core.integrations.file_streaming import INCOMING_FILE_PREFIX, atomic_replacement

__all__ = ["LocalParsedStore", "UnreadableParsedStore"]

_SOURCE_DIRECTORY: Final = "sha256"


class UnreadableParsedStore(ValueError):
    """A file in the store holds a line that is not the record it should be.

    Names the file relative to the store's root and the line number, never the line: a document
    record holds card text.
    """

    def __init__(self, file: str, line: int, reason: str) -> None:
        self.file = file
        self.line = line
        super().__init__(f"parsed store file {file} line {line}: {reason}")


class LocalParsedStore:
    """JSONL files under `<data_dir>/parsed/`."""

    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / PARSED_PREFIX

    @property
    def root(self) -> Path:
        """`<data_dir>/parsed`: where the store's files are, and what a publish copies."""
        return self._root

    # -- reading ------------------------------------------------------------------------------

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        directory = self._root / caselist
        if not directory.is_dir():
            return ()
        names = [path.name for path in directory.iterdir() if path.is_dir()]
        return tuple(sorted(names, key=parse_version_directory))

    async def read_entries(
        self, caselist: str, version: str, *, snapshot: str | None = None
    ) -> tuple[SourceEntry, ...]:
        sources = self._root / caselist / version / _SOURCE_DIRECTORY
        if not sources.is_dir():
            return ()
        entries: list[SourceEntry] = []
        for path in sorted(sources.rglob("*.jsonl")):
            if path.name.startswith(INCOMING_FILE_PREFIX):
                continue
            with path.open(encoding="utf-8") as stream:
                first = stream.readline()
            entry = self._record(SourceEntry, first, path, 1)
            if snapshot is None or entry.snapshot == snapshot:
                entries.append(entry)
        return tuple(sorted(entries, key=lambda entry: entry.source_sha256))

    async def read_document(self, caselist: str, version: str, sha256: str) -> DocumentRecord | None:
        path = self._root / source_object_key(caselist, version, sha256)
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as stream:
            stream.readline()
            second = stream.readline()
        if not second.strip():
            return None
        return self._record(DocumentRecord, second, path, 2)

    async def read_index(self, caselist: str, version: str) -> tuple[SourceEntry, ...] | None:
        return self._read_lines(SourceEntry, self._root / caselist / version / INDEX_NAME)

    async def read_failures(self, caselist: str, version: str) -> tuple[SourceEntry, ...] | None:
        return self._read_lines(SourceEntry, self._root / caselist / version / FAILURES_NAME)

    async def read_occurrences(self, caselist: str, version: str) -> tuple[OccurrenceRecord, ...] | None:
        return self._read_lines(OccurrenceRecord, self._root / caselist / version / OCCURRENCES_NAME)

    # -- writing ------------------------------------------------------------------------------

    async def put_source(
        self, caselist: str, version: str, entry: SourceEntry, document: DocumentRecord | None
    ) -> None:
        await self._refuse_old_version(caselist, version, entry.parser_version)
        parsed = entry.outcome is SourceOutcome.PARSED
        if parsed != (document is not None) or (
            document is not None and document.source_sha256 != entry.source_sha256
        ):
            raise ParsedStoreRefusal(
                f"source {entry.source_sha256}: a parsed entry is written with its own document, "
                "and only a parsed entry is"
            )
        path = self._root / source_object_key(caselist, version, entry.source_sha256)
        if path.is_file():
            with path.open(encoding="utf-8") as stream:
                existing = self._record(SourceEntry, stream.readline(), path, 1)
            if not existing.retried_next_run:
                raise ParsedStoreRefusal(
                    f"source {entry.source_sha256} is already recorded in {caselist}/{version}; "
                    "a re-parse writes a new version directory"
                )
        records: list[StoreRecord] = [entry] if document is None else [entry, document]
        self._write_lines(path, records)

    async def write_aggregates(
        self,
        caselist: str,
        version: str,
        *,
        index: Sequence[SourceEntry],
        failures: Sequence[SourceEntry],
        occurrences: Sequence[OccurrenceRecord],
    ) -> None:
        await self._refuse_old_version(caselist, version, parse_version_directory(version)[0])
        directory = self._root / caselist / version
        self._write_lines(directory / INDEX_NAME, index)
        self._write_lines(directory / FAILURES_NAME, failures)
        self._write_lines(directory / OCCURRENCES_NAME, occurrences)

    # -- helpers ------------------------------------------------------------------------------

    async def _refuse_old_version(self, caselist: str, version: str, parser_version: str) -> None:
        named_version, generation = parse_version_directory(version)
        if named_version != parser_version:
            raise ParsedStoreRefusal(
                f"{caselist}/{version} belongs to parser version {named_version}, not {parser_version}"
            )
        newest = max(
            (
                parse_version_directory(name)[1]
                for name in await self.version_directories(caselist)
                if parse_version_directory(name)[0] == parser_version
            ),
            default=generation,
        )
        if generation < newest:
            raise ParsedStoreRefusal(
                f"{caselist}/{version} is an earlier generation of {parser_version}; it is never rewritten"
            )

    def _write_lines(self, path: Path, records: Iterable[StoreRecord]) -> None:
        text = "".join(f"{_render(record)}\n" for record in records)
        with atomic_replacement(path) as incoming:
            incoming.write_text(text, encoding="utf-8")

    def _read_lines[RecordT: StoreRecord](
        self, model: type[RecordT], path: Path
    ) -> tuple[RecordT, ...] | None:
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as stream:
            return tuple(
                self._record(model, line, path, number)
                for number, line in enumerate(stream, start=1)
                if line.strip()
            )

    def _record[RecordT: StoreRecord](
        self, model: type[RecordT], line: str, path: Path, number: int
    ) -> RecordT:
        relative = path.relative_to(self._root).as_posix()
        try:
            return model.model_validate_json(line)
        except ValueError as error:
            kind = "not JSON" if not line.strip().startswith("{") else f"not a {model.__name__}"
            raise UnreadableParsedStore(relative, number, kind) from error


def _render(record: StoreRecord) -> str:
    """One record as one line: compact, keys sorted, so a record always renders to the same bytes."""
    return json.dumps(
        record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

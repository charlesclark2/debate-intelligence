"""The in-memory fake of the parsed card store (`v1-e31-t06`)."""

from __future__ import annotations

from collections.abc import Sequence

from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    ParsedStore,
    ParsedStoreRefusal,
    SourceEntry,
    parse_version_directory,
)

__all__ = ["InMemoryParsedStore", "build_fake_parsed_store"]


class InMemoryParsedStore:
    """The parsed card store (`v1-e31-t06`) in dictionaries, with the local adapter's two refusals.

    Records are kept as the objects written; a test that cares about bytes on disk uses
    :class:`~debate_core.integrations.local.parsed_store.LocalParsedStore`.
    """

    def __init__(self) -> None:
        self.sources: dict[tuple[str, str, str], tuple[SourceEntry, DocumentRecord | None]] = {}
        """`(caselist, version, sha256)` to the source's entry and document."""
        self.aggregates: dict[
            tuple[str, str],
            tuple[tuple[SourceEntry, ...], tuple[SourceEntry, ...], tuple[OccurrenceRecord, ...]],
        ] = {}
        """`(caselist, version)` to its index, failures and occurrences."""

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        names = {version for name, version, _ in self.sources if name == caselist}
        names |= {version for name, version in self.aggregates if name == caselist}
        return tuple(sorted(names, key=parse_version_directory))

    async def read_entries(
        self, caselist: str, version: str, *, snapshot: str | None = None
    ) -> tuple[SourceEntry, ...]:
        return tuple(
            entry
            for (name, held, _), (entry, _) in sorted(self.sources.items())
            if name == caselist and held == version and (snapshot is None or entry.snapshot == snapshot)
        )

    async def read_document(self, caselist: str, version: str, sha256: str) -> DocumentRecord | None:
        held = self.sources.get((caselist, version, sha256))
        return held[1] if held is not None else None

    async def write_source(
        self, caselist: str, version: str, entry: SourceEntry, document: DocumentRecord | None
    ) -> None:
        named, generation = parse_version_directory(version)
        newest = max(
            (
                parse_version_directory(name)[1]
                for name in await self.version_directories(caselist)
                if parse_version_directory(name)[0] == named
            ),
            default=generation,
        )
        if named != entry.parser_version or generation < newest:
            raise ParsedStoreRefusal(
                f"{caselist}/{version} is not the newest generation of {entry.parser_version}"
            )
        existing = self.sources.get((caselist, version, entry.source_sha256))
        if existing is not None and not existing[0].retried_next_run:
            raise ParsedStoreRefusal(
                f"source {entry.source_sha256} is already recorded in {caselist}/{version}"
            )
        self.sources[(caselist, version, entry.source_sha256)] = (entry, document)

    async def write_aggregates(
        self,
        caselist: str,
        version: str,
        *,
        index: Sequence[SourceEntry],
        failures: Sequence[SourceEntry],
        occurrences: Sequence[OccurrenceRecord],
    ) -> None:
        self.aggregates[(caselist, version)] = (tuple(index), tuple(failures), tuple(occurrences))

    async def read_index(self, caselist: str, version: str) -> tuple[SourceEntry, ...] | None:
        held = self.aggregates.get((caselist, version))
        return held[0] if held is not None else None

    async def read_failures(self, caselist: str, version: str) -> tuple[SourceEntry, ...] | None:
        held = self.aggregates.get((caselist, version))
        return held[1] if held is not None else None

    async def read_occurrences(self, caselist: str, version: str) -> tuple[OccurrenceRecord, ...] | None:
        held = self.aggregates.get((caselist, version))
        return held[2] if held is not None else None

    async def read_occurrence_stamps(self, caselist: str, version: str) -> frozenset[str] | None:
        held = self.aggregates.get((caselist, version))
        return frozenset(row.fingerprint_version for row in held[2]) if held is not None else None

    async def read_occurrence_profiles(self, caselist: str, version: str) -> frozenset[str] | None:
        held = self.aggregates.get((caselist, version))
        return frozenset(row.profile_version for row in held[2]) if held is not None else None


def build_fake_parsed_store() -> ParsedStore:
    """Build the in-memory :class:`ParsedStore` (v1-e31-t06), typed as the port, for pyright's check."""
    return InMemoryParsedStore()

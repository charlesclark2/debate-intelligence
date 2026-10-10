"""The parsed card store: what `debate-research caselist parse` writes, and E32, E33 and E34 read.

`v1-e31-t06-parse-pipeline` turns imported caselist and camp sources into this store. Each
caselist has one directory per parser version, and in it one file per source plus three aggregates
rebuilt on every run::

    parsed/<caselist>/<version>/sha256/ab/cd/<sha256>.jsonl   one source: its entry, then its cards
    parsed/<caselist>/<version>/index.jsonl                   every source's entry, by sha256
    parsed/<caselist>/<version>/failures.jsonl                the entries that did not parse
    parsed/<caselist>/<version>/occurrences.jsonl             every card, once per disclosure

The same keys under `<data_dir>/parsed/` on this machine and under `parsed/` in the environment's
evidence bucket. `docs/data/parsed-card-store.md` is the reader's description of the layout; this
module is its definition.

## Every record says what produced it

Each line in each file is one record carrying :class:`StoreRecord`'s six fields: the caselist, the
snapshot, the source's SHA-256, and the parser, style-profile and fingerprint versions. A record
read on its own, by `jq` or a dataframe or the V2 debate tub, names the reading that made it
without a file name or a directory to interpret.

## Nothing in it identifies a person

A disclosure path names a school and a team code, and a team code is personal data about a minor.
The data-use policy lists the places such data may live, and the bucket's `parsed/` prefix is not
one of them (`docs/policies/caselist-data-use.md`, "Where personal data is allowed to live"). So
this store holds none: no path, no school, no team code, no tournament or round. The mapping from a
team to what it disclosed stays in the manifests, which is where the evidence-store layout puts it
and where a removal rewrites it.

What stands in for a disclosure is the :func:`~debate_core.application.ports.suppression.
disclosure_digest` of its caselist and path, the same pseudonym the suppression list records a
withdrawn disclosure under. A card's provenance path is left out of the stored document and put
back on read from the manifests (:meth:`DocumentRecord.to_parsed_document`).

## The skip key

A source is parsed once per :class:`SkipKey`: its SHA-256, the parser version and the style
profile version. The same bytes disclosed in fourteen weeks are one parse. A source whose key
matches an entry already in the version directory is skipped, and a parser or profile change makes
every key new.

The fingerprint version is not part of the key, and does not need to be. A source's file holds its
entry and its parsed document, and neither holds a fingerprint or a cluster id: those exist only in
the occurrence table, which every run rebuilds from scratch and stamps with the version it used. So
a change of :data:`~debate_core.evidence.fingerprints.FINGERPRINT_VERSION` re-parses nothing. The
next run rewrites every occurrence row under the new version, and the per-source records keep the
stamp of the day they were parsed (`v1-e31-t08`).

## Versions are never rewritten

A version directory is named for the parser version that wrote it. A forced re-parse, or a style
profile change under the same parser version, writes a new *generation* beside it,
`<parser_version>_reparse-<n>`, and leaves the old directory as it was. Only the current generation
of the running parser version is ever written to.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import Final, Literal, NamedTuple, Protocol, Self, runtime_checkable

from pydantic import Field, JsonValue, model_validator

from debate_core.domain import Sha256Hex
from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import SourceFormat
from debate_core.domain.debate_files import CardCompleteness, ParsedDocument, ParseFailureReason

__all__ = [
    "AGGREGATE_NAMES",
    "FAILURES_NAME",
    "INDEX_NAME",
    "OCCURRENCES_NAME",
    "OPENEV_STORE",
    "PARSED_PREFIX",
    "PARSED_STORE_SCHEMA_VERSION",
    "REPARSE_SEPARATOR",
    "DocumentRecord",
    "OccurrenceRecord",
    "ParsedStore",
    "ParsedStoreRefusal",
    "PipelineFailureReason",
    "SkipKey",
    "SourceEntry",
    "SourceOutcome",
    "StoreRecord",
    "parse_version_directory",
    "skip_key",
    "source_object_key",
    "version_directory_name",
]

PARSED_STORE_SCHEMA_VERSION: Final = 2
"""Version of every record's shape as it is written now. Bumped by a change that breaks a reader.

* **1**: what `2026.09.20-docx-1` wrote. A stored card's `tag` is always a string, and `""` means
  the file gave the card none.
* **2** (`v1-e31-t09`): a stored card's `tag` is a string or `null`, and is never `""`. A reader that
  calls a string function on `tag` needs a null check, which is what makes this a new shape.

Version-1 records stay on disk and in both buckets as they are; nothing rewrites a version
directory. Every reader takes both (:data:`ReadableSchemaVersion`).
"""

type ReadableSchemaVersion = Literal[1, 2]
"""Every record version a reader accepts. A record keeps the version it was written with."""

PARSED_PREFIX: Final = "parsed"
"""The directory under `<data_dir>` and the key prefix in the bucket that the store lives under."""

OPENEV_STORE: Final = "openev"
"""The store name camp files are filed under, as `manifests/openev/` and `--caselist openev` name them."""

INDEX_NAME: Final = "index.jsonl"
FAILURES_NAME: Final = "failures.jsonl"
OCCURRENCES_NAME: Final = "occurrences.jsonl"

AGGREGATE_NAMES: Final = (INDEX_NAME, FAILURES_NAME, OCCURRENCES_NAME)
"""The files rebuilt from the per-source files on every run, and deleted by a removal."""

REPARSE_SEPARATOR: Final = "_reparse-"
"""Between a parser version and its generation in a version directory's name."""

_STORE_NAME = re.compile(rf"^(?:[a-z]+[0-9]{{2}}|{OPENEV_STORE})$")
_RELEASE_NAME = re.compile(r"^[0-9]{4}-[a-z0-9][a-z0-9-]*$")
_GENERATION = re.compile(
    rf"^(?P<parser_version>.+?){re.escape(REPARSE_SEPARATOR)}(?P<generation>[2-9]|[1-9][0-9]+)$"
)


class ParsedStoreRefusal(ValueError):
    """A write the store will not make: into an old version, or over a source already recorded.

    A `ValueError` rather than a domain error because no input from outside can cause it: only a
    caller that chose the wrong directory, which is the bug the refusal exists to stop.
    """


# ------------------------------------------------------------------------------------------------
# Names
# ------------------------------------------------------------------------------------------------


def version_directory_name(parser_version: str, generation: int = 1) -> str:
    """`2026.09.20-docx-1` for the first parse, `2026.09.20-docx-1_reparse-2` for the next."""
    if generation < 1:
        raise ValueError(f"a generation counts from 1; got {generation}")
    if generation == 1:
        return parser_version
    return f"{parser_version}{REPARSE_SEPARATOR}{generation}"


def parse_version_directory(name: str) -> tuple[str, int]:
    """`(parser_version, generation)` for a version directory's name. Inverse of the above."""
    match = _GENERATION.match(name)
    if match is None:
        return name, 1
    return match["parser_version"], int(match["generation"])


def source_object_key(caselist: str, version: str, sha256: str) -> str:
    """`<caselist>/<version>/sha256/ab/cd/<sha256>.jsonl`, relative to the store's root.

    The fan-out is the blob store's, and the last segment begins with the digest, which is what
    `caselist remove` matches a parsed file by.
    """
    return f"{caselist}/{version}/sha256/{sha256[0:2]}/{sha256[2:4]}/{sha256}.jsonl"


class SkipKey(NamedTuple):
    """What decides whether a source has already been parsed: identical keys, identical output."""

    source_sha256: str
    parser_version: str
    profile_version: str


def skip_key(source_sha256: str, parser_version: str, profile_version: str) -> SkipKey:
    """The one place a skip key is built, for the store's entries and the sources a run considers."""
    return SkipKey(source_sha256, parser_version, profile_version)


# ------------------------------------------------------------------------------------------------
# Records
# ------------------------------------------------------------------------------------------------


class SourceOutcome(StrEnum):
    """What became of one source."""

    PARSED = "PARSED"
    """Read into a document; its cards are in the source's file."""

    UNSUPPORTED = "UNSUPPORTED"
    """A PDF, a legacy `.doc` or another format V1 stores unparsed. An outcome, not a failure."""

    FAILED = "FAILED"
    """Malformed, oversized, macro-enabled, timed out or otherwise unreadable. A failure."""


class PipelineFailureReason(StrEnum):
    """Why a source has no document, for the reasons the parser itself cannot report."""

    TIMEOUT = "TIMEOUT"
    """The parse ran past the per-file time limit and its worker was stopped."""

    WORKER_CRASHED = "WORKER_CRASHED"
    """The worker process died while parsing this source."""

    PARSER_ERROR = "PARSER_ERROR"
    """The parser raised instead of returning a failure: a parser bug, recorded by class name only."""

    SOURCE_MISSING = "SOURCE_MISSING"
    """A manifest names the source but this machine's blob store does not hold it. Retried next run."""

    SOURCE_INTEGRITY = "SOURCE_INTEGRITY"
    """The blob on disk no longer hashes to its own name. Never parsed."""


_FAILURE_REASONS: Final = frozenset(str(reason) for reason in ParseFailureReason) | frozenset(
    str(reason) for reason in PipelineFailureReason
)


class StoreRecord(DomainModel):
    """The six fields every record in the store carries (task spec ac2)."""

    schema_version: ReadableSchemaVersion = PARSED_STORE_SCHEMA_VERSION
    caselist: str = Field(description="Caselist slug, or `openev` for camp files.")
    snapshot: str = Field(
        description="`YYYY-MM-DD` for a caselist snapshot; `<year>-<event>` for an OpenEv release."
    )
    source_sha256: Sha256Hex = Field(description="SHA-256 of the source file's bytes.")
    parser_version: NonEmptyText = Field(description="Version of the parser that read the source.")
    profile_version: NonEmptyText = Field(description="Version of the style profile it resolved through.")
    fingerprint_version: NonEmptyText = Field(
        description=(
            "Version of the card matching rules. On an occurrence, the version its fingerprint and "
            "cluster id were computed under. On a source or document, the version in force when the "
            "source was parsed, which nothing in the record depends on."
        )
    )

    @model_validator(mode="after")
    def _check_names(self) -> Self:
        if _STORE_NAME.match(self.caselist) is None:
            raise ValueError(f"not a caselist slug or {OPENEV_STORE!r}: {self.caselist!r}")
        if self.caselist == OPENEV_STORE:
            if _RELEASE_NAME.match(self.snapshot) is None:
                raise ValueError(f"an OpenEv snapshot is <year>-<event>; got {self.snapshot!r}")
        else:
            try:
                parsed = date.fromisoformat(self.snapshot)
            except ValueError:
                parsed = None
            if parsed is None or parsed.isoformat() != self.snapshot:
                raise ValueError(f"a caselist snapshot is YYYY-MM-DD; got {self.snapshot!r}")
        return self

    @property
    def skip_key(self) -> SkipKey:
        return skip_key(self.source_sha256, self.parser_version, self.profile_version)


class SourceEntry(StoreRecord):
    """One source and what became of it: a line of `index.jsonl`, and the first line of its own file.

    `snapshot` is the snapshot the source was parsed under, the earliest one disclosing it at the
    time. `reason` is a :class:`~debate_core.domain.debate_files.ParseFailureReason` or a
    :class:`PipelineFailureReason`; `detail` is the parser's account of it, which names limits and
    formats and never document text or a path.
    """

    record: Literal["source"] = "source"
    source_format: SourceFormat = Field(description="DOCX, DOC, PDF or OTHER, from the manifest.")
    byte_size: int = Field(ge=0, description="Size of the source in bytes.")
    outcome: SourceOutcome
    reason: str | None = Field(default=None, description="Why it has no document; None when PARSED.")
    detail: str = Field(default="", description="What the parser saw, in limits and formats only.")
    cards: int = Field(default=0, ge=0, description="How many cards the source's document holds.")

    @model_validator(mode="after")
    def _check_outcome(self) -> Self:
        if self.outcome is SourceOutcome.PARSED:
            if self.reason is not None:
                raise ValueError(f"a parsed source has no failure reason; got {self.reason!r}")
            return self
        if self.reason not in _FAILURE_REASONS:
            raise ValueError(f"not a parse failure reason: {self.reason!r}")
        if self.cards:
            raise ValueError(f"a {self.outcome} source has no cards")
        unsupported = self.reason == ParseFailureReason.UNSUPPORTED_FORMAT
        if unsupported != (self.outcome is SourceOutcome.UNSUPPORTED):
            raise ValueError(f"reason {self.reason} cannot have outcome {self.outcome}")
        return self

    @classmethod
    def for_failure(
        cls,
        *,
        reason: str,
        detail: str,
        **fields: object,
    ) -> SourceEntry:
        """An entry for a source that has no document: UNSUPPORTED for a format V1 does not parse,
        FAILED for everything else."""
        outcome = (
            SourceOutcome.UNSUPPORTED
            if reason == ParseFailureReason.UNSUPPORTED_FORMAT
            else SourceOutcome.FAILED
        )
        return cls.model_validate({**fields, "outcome": outcome, "reason": reason, "detail": detail})

    @property
    def retried_next_run(self) -> bool:
        """True for an outcome that says nothing about the bytes, so the next run tries again."""
        return self.reason == PipelineFailureReason.SOURCE_MISSING


class DocumentRecord(StoreRecord):
    """The second line of a parsed source's file: its cards, as a ParsedDocument without its paths.

    `document` is :class:`~debate_core.domain.debate_files.ParsedDocument`'s JSON with two things
    left out. Its `sections` (every paragraph, ~9,000 for a 300-page file) are reproducible from the
    source bytes by the same parser version, and nothing that reads the store needs them. And its
    disclosure paths, the document's and every card's provenance `source_path`, are personal data
    this store does not hold; :meth:`to_parsed_document` puts the path back from the manifests.
    `camp` is the OpenEv camp the file was released by, and `None` for a caselist disclosure.
    """

    record: Literal["document"] = "document"
    camp: NonEmptyText | None = Field(default=None, description="Camp for an OpenEv file; None otherwise.")
    document: dict[str, JsonValue] = Field(description="The ParsedDocument, without sections or paths.")

    @model_validator(mode="after")
    def _check_document(self) -> Self:
        if "source_path" in self.document or "sections" in self.document:
            raise ValueError("a stored document carries neither its path nor its sections")
        if self.document.get("source_sha256") != self.source_sha256:
            raise ValueError("the stored document names another source than its record")
        if self.document.get("parser_version") != self.parser_version:
            raise ValueError("the stored document names another parser version than its record")
        if self.schema_version >= 2 and self._has_an_empty_tag:
            raise ValueError(
                'a version 2 document says "no tag" as null; an empty string is how version 1 said it'
            )
        return self

    @property
    def _has_an_empty_tag(self) -> bool:
        cards = self.document.get("cards")
        return isinstance(cards, list) and any(
            isinstance(card, dict) and card.get("tag") == "" for card in cards
        )

    @classmethod
    def from_parsed_document(
        cls,
        document: ParsedDocument,
        *,
        caselist: str,
        snapshot: str,
        fingerprint_version: str,
        camp: str | None,
    ) -> DocumentRecord:
        """The record for one parsed document, with its sections and every path left out."""
        stored = document.model_dump(
            mode="json",
            exclude={
                "sections": True,
                "source_path": True,
                "cards": {"__all__": {"provenance": {"source_path"}}},
            },
        )
        return cls(
            caselist=caselist,
            snapshot=snapshot,
            source_sha256=document.source_sha256,
            parser_version=document.parser_version,
            profile_version=document.profile_version,
            fingerprint_version=fingerprint_version,
            camp=camp,
            document=stored,
        )

    @property
    def card_count(self) -> int:
        cards = self.document.get("cards")
        return len(cards) if isinstance(cards, list) else 0

    def to_parsed_document(self, source_path: str) -> ParsedDocument:
        """The ParsedDocument again, with `source_path` as the document's and every card's path.

        The caller takes the path from the manifests, which are where a disclosure path lives.
        """
        cards: list[JsonValue] = []
        stored_cards = self.document.get("cards")
        for card in stored_cards if isinstance(stored_cards, list) else []:
            if not isinstance(card, dict):
                raise ValueError("a stored card is not a JSON object")
            provenance = card.get("provenance")
            if not isinstance(provenance, dict):
                raise ValueError("a stored card has no provenance")
            cards.append({**card, "provenance": {**provenance, "source_path": source_path}})
        return ParsedDocument.model_validate({**self.document, "source_path": source_path, "cards": cards})


class OccurrenceRecord(StoreRecord):
    """One card in one disclosure: a line of `occurrences.jsonl`.

    A disclosure is one path holding one file's bytes, named by `disclosure`, the digest of its
    caselist and path (:func:`~debate_core.application.ports.suppression.disclosure_digest`). It is
    one row however many weekly manifests list it: `snapshot` is the first that does and
    `last_snapshot` the latest. A path whose bytes change has a new digest, so it is a new source
    and a new row, with no special case. A camp file has no disclosure and records `None`, one row
    per card per release, with `last_snapshot` equal to `snapshot`. Who disclosed it is a join with
    the manifests, never a field here.
    """

    record: Literal["occurrence"] = "occurrence"
    last_snapshot: str = Field(
        description="The latest snapshot listing this disclosure; `snapshot` is the first. Same form."
    )
    disclosure: Sha256Hex | None = Field(description="Digest of `<caselist>/<path>`; None for a camp file.")
    camp: NonEmptyText | None = Field(default=None, description="Camp for an OpenEv file; None otherwise.")
    first_element_index: int = Field(ge=0, description="First paragraph of the card in its document.")
    last_element_index: int = Field(ge=0, description="Last paragraph of the card in its document.")
    exact_fingerprint: Sha256Hex = Field(description="The card's exact fingerprint.")
    cluster_id: Sha256Hex = Field(description="The near-duplicate cluster the card was placed in.")
    membership: ClusterMembership = Field(description="How the card joined its cluster.")
    completeness: CardCompleteness = Field(description="FULL, ABBREVIATED or CITE_ONLY, as parsed.")

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        if self.caselist == OPENEV_STORE:
            if self.last_snapshot != self.snapshot:
                raise ValueError("a camp file's occurrence is one release: last_snapshot is snapshot")
        else:
            try:
                parsed = date.fromisoformat(self.last_snapshot)
            except ValueError:
                parsed = None
            if parsed is None or parsed.isoformat() != self.last_snapshot:
                raise ValueError(f"a caselist snapshot is YYYY-MM-DD; got {self.last_snapshot!r}")
            if self.last_snapshot < self.snapshot:
                raise ValueError("last_snapshot is before snapshot")
        return self


# ------------------------------------------------------------------------------------------------
# The port
# ------------------------------------------------------------------------------------------------


@runtime_checkable
class ParsedStore(Protocol):
    """Reads and writes one machine's parsed card store.

    Async for the same reason the other storage ports are: every call waits on a disk. A write is
    atomic per file, so a run stopped part-way leaves whole per-source files that the next run
    skips, and aggregates that are either the previous run's or this one's.
    """

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        """Every version directory `caselist` has, sorted by parser version and then generation."""
        ...

    async def read_entries(
        self, caselist: str, version: str, *, snapshot: str | None = None
    ) -> tuple[SourceEntry, ...]:
        """The entry of every source in a version directory, by SHA-256; only `snapshot`'s when given.

        Read from the per-source files, not the index, so it is the truth even when an aggregate
        has been deleted by a removal or a run stopped before rewriting them.
        """
        ...

    async def read_document(self, caselist: str, version: str, sha256: str) -> DocumentRecord | None:
        """A parsed source's document record, or `None` when the source has none."""
        ...

    async def write_source(
        self, caselist: str, version: str, entry: SourceEntry, document: DocumentRecord | None
    ) -> None:
        """Write one source's file: its entry, then its document when it was parsed.

        Raises :class:`ParsedStoreRefusal` for a directory that is not the newest generation of the
        entry's own parser version, and for a source whose file is already there, unless that
        file's entry is one the next run retries.
        """
        ...

    async def write_aggregates(
        self,
        caselist: str,
        version: str,
        *,
        index: Sequence[SourceEntry],
        failures: Sequence[SourceEntry],
        occurrences: Sequence[OccurrenceRecord],
    ) -> None:
        """Replace the index, failures and occurrence files of a version directory, each atomically."""
        ...

    async def read_index(self, caselist: str, version: str) -> tuple[SourceEntry, ...] | None:
        """`index.jsonl`, or `None` when it is absent (a removal deletes it until the next run)."""
        ...

    async def read_failures(self, caselist: str, version: str) -> tuple[SourceEntry, ...] | None:
        """`failures.jsonl`, or `None` when it is absent."""
        ...

    async def read_occurrences(self, caselist: str, version: str) -> tuple[OccurrenceRecord, ...] | None:
        """`occurrences.jsonl`, or `None` when it is absent."""
        ...

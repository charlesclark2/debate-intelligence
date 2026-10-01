"""Read, hash, store, classify: the part of an import that is the same whatever the files are.

A weekly caselist archive (`v1-e30-t03`) and an OpenEv camp release (`v1-e30-t04`) are different
things with different metadata — a school, a team code and a round for one; a camp, a lab and a
file title for the other — but what happens to each member is the same five steps:

1. **Read.** The members arrive from an adapter
   (:func:`debate_core.integrations.local.archive_reader.read_archive`) already hashed, in path
   order, with junk turned into counted :class:`~debate_core.application.ports.archive.SkippedMember`
   values. Nothing here opens a file.
2. **Extract.** A *metadata extractor* — the one thing a caller supplies — turns a member's path
   into whatever that kind of import records about it. All the pipeline asks of the result is its
   :class:`~debate_core.domain.caselist.SourceFormat` and its warnings.
3. **Classify.** Against a *baseline* of `{path: sha256}` saying what the previous import held,
   and against the digests this run has already stored: `NEW`, `UNCHANGED`, `CHANGED`,
   `DUPLICATE`, `SUPPRESSED` and, for a path the baseline had and this run does not, `REMOVED`.
4. **Store.** The bytes to the content-addressed
   :class:`~debate_core.application.ports.persistence.SnapshotStore`, then the caller's *record
   writer*, which files whatever records that kind of import keeps.
5. **Report.** A :class:`PipelineRun` with every entry in path order and every count, which is
   what both the manifest writers and the command summaries read.

## The suppression list is not optional

A removal (`v1-e30-t07`) is undone by the next cumulative archive unless every import consults the
suppression list, so the pipeline is not built without one: :class:`SourceImportPipeline` takes a
:class:`~debate_core.application.ports.suppression.SuppressionList` as a required constructor
argument, reads it once at the start of every run, and checks it again at the one place a member's
bytes and records are written (:meth:`SourceImportPipeline._store`). An importer cannot opt out by
leaving an argument off — there is no default to fall back on — and an importer that bypassed the
pipeline to write records itself is what
`packages/debate_core/tests/application/caselist/test_import_paths_consult_suppression.py` fails on.

A suppressed member is counted as `SUPPRESSED` and nothing else happens to it: no blob, no record,
and — in the manifest writers — no row, because a row would put the requester's path, school and
team code back into the store they asked to be removed from. Only the count survives, in the
summary row.

The junk around a suppressed file goes with it. A skipped member has no digest, so the list cannot
name it, but its path can still name the removed file and the team that disclosed it: macOS's
`__MACOSX/<dir>/._<name>` and Word's `<dir>/~$<name minus two characters>` *shadow* a real file.
:func:`withheld_skipped_paths` marks a skipped member :attr:`ImportedEntry.withheld` when it shadows
a suppressed file, or when every real file in its directory is suppressed (a whole team removed);
it is still counted as skipped and given no row.

What stays with each service is what genuinely differs: where the baseline comes from (the
previous weekly snapshot, or the camp release's existing manifest), which records are written,
and whether a path that has gone is a removal (a weekly archive is cumulative, so yes; an OpenEv
download is whatever the operator happened to fetch, so no).

## One source document per digest, whichever import saw it first

:func:`file_source` is how both importers write a :class:`~debate_core.domain.caselist.SourceDocument`.
The repository refuses a second record under one digest with a different origin, because size,
format and origin are facts about the bytes. But a camp file that a team later discloses *is*
the same bytes, legitimately arriving from the other kind of import, and it must be stored once
and linked from both a disclosure and a camp-file record — that link is how E31 and E32 see that
a disclosed card came from a camp file. So when the digest is already filed under the other
origin, with the same size and format, the existing record is kept and returned, and the caller
goes on to write its disclosure or camp-file record against it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import DomainError
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember, SkipReason
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.application.ports.suppression import SuppressionList, SuppressionState, disclosure_digest
from debate_core.domain.caselist import Sha256Hex, SourceDocument, SourceFormat

__all__ = [
    "STORED_CLASSIFICATIONS",
    "Classification",
    "ExistingSourceLookup",
    "ImportedEntry",
    "MetadataExtractor",
    "PipelineRun",
    "RecordWriter",
    "SourceImportPipeline",
    "SourceMetadata",
    "SuppressedWriteRefused",
    "file_source",
    "withheld_skipped_paths",
]


class Classification(StrEnum):
    """What one member of an archive turned out to be, relative to what was already imported.

    `REMOVED` is the one that describes a member that is *not* in this archive — the path the
    previous one had and this one does not.
    """

    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    DUPLICATE = "DUPLICATE"
    REMOVED = "REMOVED"
    SUPPRESSED = "SUPPRESSED"


#: The classifications that describe a file present in the archive being imported and stored.
#: `REMOVED` is not one of them, and `SUPPRESSED` is present but deliberately not stored.
STORED_CLASSIFICATIONS = frozenset(
    {
        Classification.NEW,
        Classification.UNCHANGED,
        Classification.CHANGED,
        Classification.DUPLICATE,
    }
)


#: The classifications an :data:`ExistingSourceLookup` is consulted for. A `NEW` member found there
#: becomes a `DUPLICATE`; a `CHANGED` one stays `CHANGED` but carries the reference.
_LOOKED_UP = frozenset({Classification.NEW, Classification.DUPLICATE, Classification.CHANGED})


class SourceMetadata(Protocol):
    """What the pipeline needs from an extractor's result. Everything else is the caller's."""

    @property
    def source_format(self) -> SourceFormat: ...

    @property
    def warnings(self) -> tuple[str, ...]: ...


type MetadataExtractor[MetadataT] = Callable[[str], MetadataT]
"""A member's path relative to the archive root in, that import's metadata about it out."""

type RecordWriter[MetadataT] = Callable[
    [ArchiveMember, MetadataT, Classification, SourceDocument | None], Awaitable[None]
]
"""Files one stored member's records, after its bytes are in the blob store.

Called for every member whose classification is in :data:`STORED_CLASSIFICATIONS`, never under a
dry run. The last argument is the source document the member's bytes were already filed as, when
the pipeline was given an :data:`ExistingSourceLookup` and it found one, and `None` otherwise.
"""

type ExistingSourceLookup = Callable[[Sha256Hex], Awaitable[SourceDocument | None]]
"""Finds a source document already filed under a digest, from any earlier import of any origin."""


class SuppressedWriteRefused(DomainError):
    """A suppressed member reached the point where its bytes and records are written.

    Never raised by a correct run — classification has already counted the member as `SUPPRESSED`
    — and kept because the write is where the guarantee has to hold: if a change to classification
    ever let a suppressed member through, this stops the run before the bytes are stored rather
    than after. Names the digest only.
    """

    def __init__(self, sha256: str) -> None:
        self.sha256 = sha256
        super().__init__(f"refusing to store {sha256}: it is on the removal suppression list")


@dataclass(frozen=True, slots=True)
class ImportedEntry[MetadataT]:
    """One row of what an import saw: a member, or a path that has gone.

    Carries everything a manifest records and everything a summary counts, so the manifest
    writers do no parsing of their own and cannot disagree with the report about what happened.
    """

    path: str
    """The member's path relative to the archive root."""

    classification: Classification | None
    """What it was, or `None` for a member that was skipped before it was ever classified."""

    skip_reason: SkipReason | None = None
    """Why it was skipped, or `None` for a member that was not."""

    sha256: str | None = None
    """The digest of its bytes; `None` for a skipped member, which was never read."""

    byte_size: int | None = None
    source_format: SourceFormat | None = None
    parsed: MetadataT | None = None
    """What the metadata extractor read, or `None` for a skipped or removed entry."""

    existing_source: SourceDocument | None = None
    """The record these bytes were filed as *before this import*, when a lookup found one.

    `None` for a second copy within one archive, which duplicates the first copy rather than
    anything filed earlier.
    """

    withheld: bool = False
    """A skipped member that shadows suppressed files: counted as skipped, given no manifest row."""

    @property
    def is_skipped(self) -> bool:
        return self.skip_reason is not None


@dataclass(frozen=True, slots=True)
class PipelineRun[MetadataT]:
    """Everything one pass over an archive's members did, before a service names the archive."""

    entries: tuple[ImportedEntry[MetadataT], ...]
    """Every member and every removed path, in path order."""

    counts: Mapping[Classification, int] = field(default_factory=lambda: {})
    skipped: Mapping[SkipReason, int] = field(default_factory=lambda: {})
    member_count: int = 0
    """Members the archive held, skipped ones included; removed paths are not members."""

    distinct_digests: int = 0
    """Distinct files the archive holds once its duplicates are collapsed; suppressed ones excluded."""

    newly_stored_blobs: int = 0
    """Of those digests, how many the blob store did not already have (what a dry run would write)."""

    suppression: SuppressionState = field(default_factory=SuppressionState)
    """The suppression list as this run read it, which the manifest writers check every row against."""


class SourceImportPipeline:
    """Classifies and stores one archive's members for whichever importer hands them in.

    Holds the blob store and the suppression list, both required. The records are the caller's,
    written through the :data:`RecordWriter` it passes to :meth:`run`, so the same pipeline files
    disclosures for a caselist archive and camp-file records for an OpenEv release — and refuses to
    file either for a suppressed member.
    """

    def __init__(self, *, blobs: SnapshotStore, suppression: SuppressionList) -> None:
        self._blobs = blobs
        self._suppression = suppression

    async def run[MetadataT: SourceMetadata](
        self,
        entries: Iterable[ArchiveEntry],
        *,
        extract: MetadataExtractor[MetadataT],
        write: RecordWriter[MetadataT],
        baseline: Mapping[str, str],
        disclosure_scope: str | None,
        dry_run: bool = False,
        report_removed: bool = True,
        find_existing: ExistingSourceLookup | None = None,
    ) -> PipelineRun[MetadataT]:
        """Classify every member against `baseline`, store the stored ones, and report.

        `entries` is consumed once, in the order it yields, which the reader guarantees is path
        order. `baseline` is `{path: sha256}` for what the previous import held. With
        `report_removed`, each baseline path this archive lacks becomes a `REMOVED` entry. With
        `find_existing`, every new, duplicate or changed member is checked against the sources
        already filed by any import: a `NEW` one found there is a `DUPLICATE` of it, and each entry
        carries the record it matched.

        `disclosure_scope` is the caselist slug a disclosure-recording import files its members
        under, so a disclosure-scoped suppression (one team's copy of a shared file) can be matched
        by :func:`~debate_core.application.ports.suppression.disclosure_digest`; `None` for an
        import that records no disclosures, which only a whole-source suppression stops. Required,
        with no default, so that an importer has to say which it is.

        Writes nothing — no blob and no record — when `dry_run` is set.
        """
        suppression = await load_suppression_state(self._suppression)
        baseline_digests = frozenset(baseline.values())
        imported: list[ImportedEntry[MetadataT]] = []
        skipped: dict[SkipReason, int] = {}
        counts: dict[Classification, int] = {}
        stored_digests: set[str] = set()
        newly_stored: set[str] = set()
        seen_paths: set[str] = set()
        member_count = 0

        for entry in entries:
            if not isinstance(entry, ArchiveMember):
                skipped[entry.reason] = skipped.get(entry.reason, 0) + 1
                # Counted as a member: an archive's member count is how many members it held,
                # which is the number an operator can check against `unzip -l`.
                member_count += 1
                imported.append(ImportedEntry(path=entry.path, classification=None, skip_reason=entry.reason))
                continue

            member_count += 1
            seen_paths.add(entry.path)
            parsed = extract(entry.path)
            classification = _classify(
                entry,
                baseline=baseline,
                baseline_digests=baseline_digests,
                known=stored_digests,
                suppressed=_is_suppressed(suppression, entry, disclosure_scope),
            )
            existing: SourceDocument | None = None
            # Only bytes this run has not already stored: a second copy within one download
            # duplicates the first, not a record from before, and a dry run (which stores
            # nothing) must report the same thing a real run does.
            if (
                find_existing is not None
                and classification in _LOOKED_UP
                and entry.sha256 not in stored_digests
            ):
                existing = await find_existing(entry.sha256)
                if existing is not None and classification is Classification.NEW:
                    classification = Classification.DUPLICATE
            counts[classification] = counts.get(classification, 0) + 1
            if classification is not Classification.SUPPRESSED:
                if entry.sha256 not in stored_digests and not await self._blobs.exists(entry.sha256):
                    newly_stored.add(entry.sha256)
                stored_digests.add(entry.sha256)
            imported.append(
                ImportedEntry(
                    path=entry.path,
                    classification=classification,
                    sha256=entry.sha256,
                    byte_size=entry.byte_size,
                    source_format=parsed.source_format,
                    parsed=parsed,
                    existing_source=existing,
                )
            )
            if not dry_run and classification in STORED_CLASSIFICATIONS:
                await self._store(
                    entry,
                    parsed,
                    classification,
                    existing,
                    write=write,
                    suppression=suppression,
                    disclosure_scope=disclosure_scope,
                )

        withheld = withheld_skipped_paths(
            {
                entry.path: entry.classification is Classification.SUPPRESSED
                for entry in imported
                if entry.classification is not None
            },
            [entry.path for entry in imported if entry.is_skipped],
        )
        if withheld:
            imported = [
                ImportedEntry(
                    path=entry.path, classification=None, skip_reason=entry.skip_reason, withheld=True
                )
                if entry.path in withheld
                else entry
                for entry in imported
            ]

        if report_removed:
            for gone in sorted(baseline.keys() - seen_paths):
                counts[Classification.REMOVED] = counts.get(Classification.REMOVED, 0) + 1
                imported.append(ImportedEntry(path=gone, classification=Classification.REMOVED))

        return PipelineRun(
            entries=tuple(sorted(imported, key=lambda one: one.path)),
            counts=counts,
            skipped=skipped,
            member_count=member_count,
            distinct_digests=len(stored_digests),
            newly_stored_blobs=len(newly_stored),
            suppression=suppression,
        )

    async def _store[MetadataT](
        self,
        member: ArchiveMember,
        parsed: MetadataT,
        classification: Classification,
        existing: SourceDocument | None,
        *,
        write: RecordWriter[MetadataT],
        suppression: SuppressionState,
        disclosure_scope: str | None,
    ) -> None:
        """Write one member's bytes and records: the only place an import writes either.

        The suppression check is repeated here, at the write, rather than trusted from
        classification: see :class:`SuppressedWriteRefused`.
        """
        if _is_suppressed(suppression, member, disclosure_scope):
            raise SuppressedWriteRefused(member.sha256)
        await self._blobs.put(member.data)
        await write(member, parsed, classification, existing)


_MACOS_METADATA_DIRECTORY = "__MACOSX"
_APPLE_DOUBLE_PREFIX = "._"
_WORD_LOCK_PREFIX = "~$"


def withheld_skipped_paths(real: Mapping[str, bool], skipped: Iterable[str]) -> frozenset[str]:
    """The skipped paths whose manifest rows would name suppressed files, so get none.

    `real` maps every real (read and classified) member's path to whether it is suppressed;
    `skipped` is every skipped member's path. A skipped path is withheld when it shadows a
    suppressed real file — `__MACOSX/<dir>/._<name>` shadows `<dir>/<name>`, and a Word lock file
    `<dir>/~$<rest>` shadows any `<dir>/<name>` with `name[2:] == rest` — or when its directory
    holds at least one real file and every one of them is suppressed.

    Shared with the removal's manifest rewrite, so a manifest a removal rewrote and one an import
    wrote afterwards drop the same rows.
    """
    by_directory: dict[str, list[bool]] = {}
    for path, suppressed in real.items():
        by_directory.setdefault(_directory_of(path), []).append(suppressed)
    withheld: set[str] = set()
    for path in skipped:
        directory = _directory_of(path)
        everything_suppressed = bool(by_directory.get(directory)) and all(by_directory[directory])
        if everything_suppressed or any(real.get(shadowed, False) for shadowed in _shadowed(path, real)):
            withheld.add(path)
    return frozenset(withheld)


def _directory_of(path: str) -> str:
    """The directory a member belongs to, with macOS's metadata mirror folded onto the real one."""
    parts = path.split("/")
    if parts[0] == _MACOS_METADATA_DIRECTORY:
        parts = parts[1:]
    return "/".join(parts[:-1])


def _shadowed(path: str, real: Mapping[str, bool]) -> list[str]:
    """The real paths a junk member is metadata for, if it is one."""
    directory = _directory_of(path)
    name = path.rsplit("/", 1)[-1]
    prefix = f"{directory}/" if directory else ""
    if path.split("/")[0] == _MACOS_METADATA_DIRECTORY and name.startswith(_APPLE_DOUBLE_PREFIX):
        return [prefix + name[len(_APPLE_DOUBLE_PREFIX) :]]
    if name.startswith(_WORD_LOCK_PREFIX):
        rest = name[len(_WORD_LOCK_PREFIX) :]
        return [
            candidate
            for candidate in real
            if _directory_of(candidate) == directory and candidate.rsplit("/", 1)[-1][2:] == rest
        ]
    return []


def _is_suppressed(
    suppression: SuppressionState, member: ArchiveMember, disclosure_scope: str | None
) -> bool:
    """Whether the list stops this member: its bytes as a whole, or this one disclosure of them."""
    disclosure = disclosure_digest(disclosure_scope, member.path) if disclosure_scope is not None else None
    return suppression.suppresses(member.sha256, disclosure=disclosure)


def _classify(
    member: ArchiveMember,
    *,
    baseline: Mapping[str, str],
    baseline_digests: frozenset[str],
    known: set[str],
    suppressed: bool,
) -> Classification:
    """Decide what one member is, against the previous import and what this run has stored.

    `known` is the set of digests this run has already stored, which is what makes the second
    of two identical members in one archive a `DUPLICATE` rather than a second `NEW`.
    """
    if suppressed:
        return Classification.SUPPRESSED
    previously = baseline.get(member.path)
    if previously == member.sha256:
        return Classification.UNCHANGED
    if previously is not None:
        return Classification.CHANGED
    if member.sha256 in known or member.sha256 in baseline_digests:
        return Classification.DUPLICATE
    return Classification.NEW


async def file_source(caselists: CaselistRepository, source: SourceDocument) -> SourceDocument:
    """Store `source`, or keep the record another kind of import already filed for its bytes.

    Same origin: :meth:`~debate_core.application.ports.caselist.CaselistRepository.put_source`,
    which widens the seen range. Other origin with the same size and format: the existing record
    is returned untouched — the bytes are one source, first brought in by the other import, and
    the caller links to it with its own disclosure or camp-file record. Other origin with a
    different size or format is still handed to `put_source`, whose
    :class:`~debate_core.application.errors.Conflict` is the right answer to a digest that has
    come apart from its bytes.
    """
    existing = await caselists.find_source(source.sha256)
    if (
        existing is not None
        and existing.origin is not source.origin
        and (existing.byte_size, existing.source_format) == (source.byte_size, source.source_format)
    ):
        return existing
    return await caselists.put_source(source)

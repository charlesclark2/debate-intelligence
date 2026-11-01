"""`debate-research tub index build`: the student search pilot's index, from the parsed store (`v1-e39-t02`).

:class:`SearchIndexBuildService` reads four ports and writes through a fifth: the parsed card store
(:class:`~debate_core.application.ports.parsed_store.ParsedStore`, whose `occurrences.jsonl` is the E31
occurrence table and whose per-source files hold each card's text), the caselist records
(:class:`~debate_core.application.ports.caselist.CaselistRepository`, for who disclosed each
occurrence), the removal suppression list
(:class:`~debate_core.application.ports.suppression.SuppressionList`), and a
:class:`~debate_core.application.ports.search_index.SearchIndexWriter`. No model is called and
nothing reaches the network. It also reads the camp releases' manifests on this machine, for each camp
file's OpenEv id (`v1-e39-t16`, below). The output is one directory, `<out>/<index id>/`, holding the
SQLite file, its gzip object and :class:`~debate_core.domain.search_index.SearchIndexManifest`.

## Which rows

For each store named (a caselist slug, or `openev` for camp files), the newest generation of the
running parser version's directory, as the recipe resolver reads it. Its rows must all carry the
running :data:`~debate_core.evidence.fingerprints.FINGERPRINT_VERSION`, since a cluster id means
something only under the version it was computed by. A store with no such directory, no
`occurrences.jsonl` (a removal deletes the aggregates until the next `caselist parse`), no rows, or
rows of another fingerprint version is :class:`SearchIndexStoreNotReady`, never read as empty.

**The occurrence table, and nothing else, says what is indexed** (PM amendment 2026-10-20). A
source's document record is read only for a card an occurrence row names. Since `v1-e31-t26` the
table leaves out what an upload at a held path brought in, so a per-source file the table does not
name is never indexed, whatever it holds.

## The suppression list

A row the list stops is left out: its source suppressed as a whole, or its disclosure withdrawn (the
question the parse pipeline and the recipe resolver ask, with the row's source SHA-256 and
disclosure digest; a camp row has no disclosure, so only its source stops it). So is a caselist row
a path hold covers, asked through :func:`~debate_core.application.caselist.publish_plan.stored_row_hold`
for each disclosure record of the row, as `v1-e33-t03`'s resolver asks it. The table already leaves
both out once it is rebuilt; the build asks again because a list merged from another machine can stop
a row before this machine's next `caselist parse`. A cluster left with no row is left out of the index.

## One document per cluster, and its representative

A cluster is one cluster id in one store. Its representative is the first of its surviving rows in
this total order, over stored fields alone:

1. FULL, then ABBREVIATED, then CITE_ONLY;
2. an attributed row before an unattributed one, as `v1-e33-t03`'s AUTO rule: a caselist row with a
   disclosure on record, a camp row with its release record;
3. the latest `last_snapshot`: a caselist row by its date, a camp row by its release's year and then
   its name, as the resolver orders them;
4. the smallest occurrence key: source SHA-256, first element index, disclosure digest, and then the
   snapshot, which tells two camp releases of one file apart.

Each key is a field of the stored row or the record it joins, so the choice does not depend on the
order the store lists rows or the records list disclosures in. Every surviving row becomes an
occurrence of the document in the same order, the representative first.

## Only real cards (`v1-e39-t12`)

A cluster whose representative is no card is left out of the index, its other members with it:
CITE_ONLY, or no cite and fewer than 25 words of evidence text (:data:`CARD_ONLY_RULE`, rule C of the
PM's ruling of 2026-10-22). It is judged on the representative alone, as the spec words it: for
CITE_ONLY that is every member, since completeness leads the order; for a card with no cite, looking
at the other members would change the representative order. The parser, the parsed store and every
fingerprint are untouched: the rule is the index build's.

The card is in the source's document record, not the occurrence row, so the build reads the
representatives' sources twice: once to judge each card, then again to write the documents kept,
numbered by their rank among themselves. What was left out, by store and why, is in the build's
result (:attr:`BuiltSearchIndex.not_cards`), `tub index build`'s summary and the weekly run's
record, and not in the manifest, which the deployed function reads with `extra="forbid"`.

## What a document holds

The representative card's tag and cite come from its source's document record, read through
:meth:`~debate_core.application.ports.parsed_store.DocumentRecord.to_parsed_document` (PM amendment
2026-10-20): the occurrence table carries neither. "No tag" is `None` there since `v1-e31-t14`, and
`None` here. The card is matched to its row by its first and last element index and checked by its
exact fingerprint.

* **Searchable:** the tag; the cite as the card writes it, but for a cutter mark at its end; the
  evidence text; and the read-aloud text, the underlined or highlighted stretches of it, joined by a
  space.
* **Stored, never searchable:** the formatting and font-size spans the card page renders from; the
  event, from the caselist slug or the camp release; the caselist or camp; the sides disclosed; the
  first and last snapshot seen; the counts of files, teams and occurrences; and for each occurrence
  its source SHA-256 and disclosure digest, and for the first `provenance_limit` of them who
  disclosed it (school, team code, side, tournament and round as disclosed) or, for a camp card,
  the camp, year, event and file title of its release and, since format 3, its file's OpenEv id.
* **Never stored:** a cutter mark, a file name or a disclosure path, the card's section headings and
  undertag, or any name from a document body. The ports this reads hold no path, and the
  :class:`~debate_core.application.ports.search_index.SearchDocument` handed to the writer has no
  field for one.

## A camp file's OpenEv id (`v1-e39-t16`)

A camp occurrence keeps the OpenEv id its release's manifest (`manifests/openev/<release>.jsonl`)
records for its source, as
:func:`~debate_core.application.caselist.openev_manifest.openev_ids_by_source` reads it, so its card
page can link to the file on OpenEv. A row with no id gives none, and a manifest the importer did not
write is :class:`SearchIndexStoreNotReady`, never read as no ids. The manifests are not among the
digests the manifest records: a re-import that only adds ids to rows changes no store's digest, so the
weekly run keeps its index until a store or a version changes.

## What a build is built from, read before it

:meth:`SearchIndexBuildService.sources` reads the rows of every store and the suppression list, and
computes the digests the manifest records of them: each store's `occurrences_sha256` and the list's
`sha256`. It builds nothing. :meth:`~SearchIndexBuildService.build` reads them through the same
method, or takes what a caller read with it, so that the weekly run's question "has anything changed
since the newest index?" (`v1-e39-t09`) is asked of the very digests a build would record, and never
of a second copy of the rule (PM ruling 2026-10-20, question 2).

**A store parsed under another version** is :class:`SearchIndexStoreVersionMismatch`, a
:class:`SearchIndexStoreNotReady` reported under the same code: a store that holds only another
parser's directories, one a newer parser than this build's has written to, or rows of another
fingerprint version. The weekly run skips its index stage on it with that reason; a build by hand
fails on it as on any store not ready.

## The same store gives the same bytes

Documents kept are numbered by their (caselist, cluster id) rank, the writer lays them out by number, and
the manifest records digests and counts and no time. So five shuffles of a store give one index,
byte for byte, and one manifest.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Final

from debate_core.application.caselist.openev_manifest import openev_ids_by_source, read_recorded_release
from debate_core.application.caselist.publish_plan import (
    OPENEV,
    UnreadableManifest,
    snapshot_manifest_key,
    stored_row_hold,
)
from debate_core.application.caselist.suppression import read_path_holds
from debate_core.application.errors import DomainError
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.parsed_store import (
    OPENEV_STORE,
    OccurrenceRecord,
    ParsedStore,
    parse_version_directory,
    version_directory_name,
)
from debate_core.application.ports.persistence import Page
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument, SearchIndexWriter
from debate_core.application.ports.suppression import (
    SuppressionList,
    SuppressionState,
    canonical_line,
    disclosure_digest,
)
from debate_core.domain.caselist import CampFile, Disclosure, Event, Side
from debate_core.domain.debate_files import CardCompleteness, ParsedCard
from debate_core.domain.search_index import (
    DEFAULT_PROVENANCE_LIMIT,
    INDEX_ID_LENGTH,
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_SQLITE_NAME,
    SQLITE_FEATURE_CEILING,
    IndexCounts,
    IndexFile,
    SearchIndexManifest,
    StoreState,
    SuppressionListState,
    read_aloud_text,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint

__all__ = [
    "CARD_ONLY_RULE",
    "BuiltSearchIndex",
    "CardOnlyRule",
    "NotACard",
    "NotCards",
    "SearchIndexBuildService",
    "SearchIndexSources",
    "SearchIndexStoreNotReady",
    "SearchIndexStoreVersionMismatch",
    "cite_without_cutter_mark",
    "not_a_card",
    "not_cards_by_store",
    "not_cards_sentence",
    "representative_order",
]

_PAGE: Final = 500
_HASH_CHUNK: Final = 1024 * 1024

_NO_PATH: Final = "not-read-by-the-search-index"
"""What :meth:`DocumentRecord.to_parsed_document` is given as the disclosure path. The index stores no
path, so the build never looks one up; the card's provenance path is this, and is never read."""

_COMPLETENESS_RANK: Final = {
    CardCompleteness.FULL: 0,
    CardCompleteness.ABBREVIATED: 1,
    CardCompleteness.CITE_ONLY: 2,
}


#: `// JD` closing the last line of a cite: the convention a cutter signs with, of any length.
_CUTTER_MARK_TAIL: Final = re.compile(r"[ \t]*//[ \t]*[^\s/][^\s]*[ \t]*$")

_EVENT_BY_NAME: Final = {event.value.lower(): event for event in Event}


class SearchIndexStoreNotReady(DomainError):
    """A store the index needs cannot be read as it stands, or disagrees with itself. Never read as empty."""

    def __init__(self, caselist: str, reason: str) -> None:
        self.caselist = caselist
        self.reason = reason
        super().__init__(f"the parsed store of {caselist} cannot be indexed: {reason}")


class SearchIndexStoreVersionMismatch(SearchIndexStoreNotReady):
    """A store parsed under another parser or fingerprint version than this build runs.

    Reported under :class:`SearchIndexStoreNotReady`'s code, so `tub index build` fails on it as it
    always did; the weekly run tells it apart and skips its index stage with the reason (`v1-e39-t09`
    ac3).
    """

    ERROR_CODE: ClassVar[str] = "SEARCH_INDEX_STORE_NOT_READY"


@dataclass(frozen=True, slots=True)
class SearchIndexSources:
    """What an index of some stores is built from, read once, with the digests its manifest records."""

    tables: Mapping[str, tuple[tuple[OccurrenceRecord, ...], StoreState]]
    """Each store's occurrence rows and their state, by store name."""

    suppression: SuppressionState
    suppression_list: SuppressionListState
    """The suppression list's entry counts and digest, as the manifest's `suppression`."""

    @property
    def stores(self) -> tuple[StoreState, ...]:
        """Every store's state, by name: the manifest's `stores`."""
        return tuple(state for _, state in (self.tables[name] for name in sorted(self.tables)))


class NotACard(StrEnum):
    """Why a cluster is left out of the index as no card: what its representative is (`v1-e39-t12`)."""

    CITE_ONLY = "cite_only"
    """CITE_ONLY: a tag and a cite with no evidence text, so nothing to read or copy."""

    NO_CITE_FEW_WORDS = "no_cite_few_words"
    """No cite, and fewer words of evidence text than :attr:`CardOnlyRule.words_without_cite`: an
    analytic or a heading the parser kept as a card."""


type NotCards = Mapping[str, Mapping[NotACard, int]]
"""Documents left out as no card, by store and then by why: every store built, every reason, zeros too."""


@dataclass(frozen=True, slots=True)
class BuiltSearchIndex:
    """One built index: the directory holding its three files, and its manifest."""

    directory: Path
    manifest: SearchIndexManifest
    not_cards: NotCards
    """The clusters :func:`not_a_card` left out, by store and why. Not in the manifest: the deployed
    function reads it with `extra="forbid"`, so a new field would make it refuse the index (PM ruling
    2026-10-22)."""


# ------------------------------------------------------------------------------------------------
# Rules a test can name
# ------------------------------------------------------------------------------------------------


def cite_without_cutter_mark(full_cite: str) -> str:
    """The cite as the card writes it, without the `// JD` a cutter closes its last line with.

    The convention :func:`~debate_core.evidence.fingerprints.extract_cutter_mark` reads, matched here
    at any length: a token too long to be recorded as a mark is still not stored. A `//` that ends a
    URL's scheme (`https://`) is not a mark, and a cite of nothing but a mark is left as it is.
    """
    lines = full_cite.splitlines(keepends=True)
    for position in range(len(lines) - 1, -1, -1):
        line = lines[position]
        if not line.strip():
            continue
        ending = line[len(line.rstrip("\r\n")) :]
        body = line[: len(line) - len(ending)]
        match = _CUTTER_MARK_TAIL.search(body)
        if match is None:
            return full_cite
        mark_at = body.index("//", match.start())
        if mark_at > 0 and body[mark_at - 1] == ":":
            return full_cite
        kept = body[: match.start()]
        if not kept.strip() and not "".join(lines[:position]).strip():
            return full_cite
        return "".join(lines[:position]) + kept + ending
    return full_cite


@dataclass(frozen=True, slots=True)
class CardOnlyRule:
    """What makes a representative no card: both thresholds, in one place (PM ruling 2026-10-22)."""

    completeness: CardCompleteness
    """A representative of this completeness is left out, whatever its cite."""

    words_without_cite: int
    """A representative with no cite is left out below this many words of evidence text, counted as
    whitespace-separated words (`str.split()`)."""


CARD_ONLY_RULE: Final = CardOnlyRule(completeness=CardCompleteness.CITE_ONLY, words_without_cite=25)
"""Rule C of `v1-e39-t12` (PM ruling 2026-10-22): CITE_ONLY, or no cite and fewer than 25 words. Over the
dev index of 2026-10-22 it left out 1,625 of 52,059 documents, at most 3.86% of a caselist."""


def not_a_card(card: ParsedCard) -> NotACard | None:
    """Why `card`, a cluster's representative, is no card under :data:`CARD_ONLY_RULE`; `None` for a card.

    A cite is absent when the card's full cite is empty or only whitespace. Judged on the
    representative alone: for CITE_ONLY that is every member, since completeness leads the
    representative order.
    """
    if card.completeness is CARD_ONLY_RULE.completeness:
        return NotACard.CITE_ONLY
    if not card.full_cite.strip() and len(card.evidence_text.split()) < CARD_ONLY_RULE.words_without_cite:
        return NotACard.NO_CITE_FEW_WORDS
    return None


def not_cards_by_store(not_cards: NotCards) -> dict[str, dict[str, int]]:
    """`not_cards` as JSON: each store's counts by reason, keys sorted."""
    return {
        store: {reason.value: counts.get(reason, 0) for reason in NotACard}
        for store, counts in sorted(not_cards.items())
    }


def not_cards_sentence(not_cards: NotCards) -> str:
    """`12 left out as no card (10 cite only, 2 with no cite and under 25 words)`, for a summary."""
    cite_only = sum(counts.get(NotACard.CITE_ONLY, 0) for counts in not_cards.values())
    few_words = sum(counts.get(NotACard.NO_CITE_FEW_WORDS, 0) for counts in not_cards.values())
    return (
        f"{cite_only + few_words:,} left out as no card ({cite_only:,} cite only, {few_words:,} with no "
        f"cite and under {CARD_ONLY_RULE.words_without_cite} words)"
    )


def _recency(row: OccurrenceRecord) -> tuple[int, str]:
    """Latest first: a caselist row by the day of its last snapshot, a camp row by its release."""
    if row.caselist == OPENEV_STORE:
        return (-int(row.last_snapshot[:4]), row.last_snapshot)
    return (-date.fromisoformat(row.last_snapshot).toordinal(), "")


type RepresentativeKey = tuple[int, int, tuple[int, str], str, int, str, str]


def representative_order(row: OccurrenceRecord, *, attributed: bool) -> RepresentativeKey:
    """Where `row` stands among its cluster's rows: the smallest is the representative."""
    return (
        _COMPLETENESS_RANK[row.completeness],
        0 if attributed else 1,
        _recency(row),
        row.source_sha256,
        row.first_element_index,
        row.disclosure or "",
        row.snapshot,
    )


# ------------------------------------------------------------------------------------------------
# The service
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Joined:
    """A surviving row, with the records it joins: who disclosed it, or the camp release it is in."""

    row: OccurrenceRecord
    disclosure: Disclosure | None
    camp_file: CampFile | None
    openev_id: int | None = None

    @property
    def attributed(self) -> bool:
        return self.disclosure is not None or self.camp_file is not None

    @property
    def order(self) -> RepresentativeKey:
        return representative_order(self.row, attributed=self.attributed)


@dataclass(frozen=True, slots=True)
class _Cluster:
    caselist: str
    version: str
    cluster_id: str
    members: tuple[_Joined, ...]
    doc_id: int = 0
    """Its rank among the documents kept, from 1, in (caselist, cluster id) order; 0 until
    :meth:`SearchIndexBuildService._cards_only` has kept it."""

    @property
    def representative(self) -> _Joined:
        return self.members[0]


class SearchIndexBuildService:
    """Builds the pilot's index from this machine's parsed store, caselist records and suppression list."""

    def __init__(
        self,
        *,
        parsed_store: ParsedStore,
        caselists: CaselistRepository,
        suppression: SuppressionList,
        writer: SearchIndexWriter,
        parser_version: str,
        event_for_caselist: Callable[[str], Event | None],
        release_manifest_lines: Callable[[ObjectKey], Sequence[str]],
    ) -> None:
        """`parser_version` is the running parser's: its newest generation is the directory read.

        `event_for_caselist` names the event of a caselist slug, `None` for a slug this build does not
        know; it is the CLI's table, passed in. `release_manifest_lines` reads this machine's manifest
        at a key, no lines when it holds none: the camp releases' manifests give each camp file its
        OpenEv id (`v1-e39-t16`).
        """
        self._store = parsed_store
        self._caselists = caselists
        self._suppression = suppression
        self._writer = writer
        self._parser_version = parser_version
        self._event_for_caselist = event_for_caselist
        self._release_manifest_lines = release_manifest_lines

    async def sources(self, stores: Sequence[str]) -> SearchIndexSources:
        """Read what an index of `stores` would be built from, and its digests, building nothing.

        Raises :class:`SearchIndexStoreNotReady` for a store that cannot be read as it stands, and
        its :class:`SearchIndexStoreVersionMismatch` for one parsed under another version.
        """
        names = sorted(set(stores))
        if not names:
            raise ValueError("an index is built from at least one store")
        for name in names:
            if name != OPENEV_STORE and self._event_for_caselist(name) is None:
                raise SearchIndexStoreNotReady(
                    name, "this build does not know which event the caselist debates"
                )
        state, suppression_state = await self._suppression_state()
        tables = {name: await self._read(name) for name in names}
        return SearchIndexSources(tables=tables, suppression=state, suppression_list=suppression_state)

    async def build(
        self,
        stores: Sequence[str],
        out: Path,
        *,
        provenance_limit: int = DEFAULT_PROVENANCE_LIMIT,
        sources: SearchIndexSources | None = None,
    ) -> BuiltSearchIndex:
        """Build the index of `stores` under `out/<index id>/` and return it with its manifest.

        `sources` is what :meth:`sources` read of the same stores, when the caller has read it
        already; it is read here otherwise. Raises :class:`SearchIndexStoreNotReady` for a store that
        cannot be read as it stands. An index already at `out/<index id>/` is the same bytes, since
        the id is the SQLite file's digest, and is replaced by the new build.
        """
        if provenance_limit < 1:
            raise ValueError(f"provenance_limit is at least 1; got {provenance_limit}")
        names = sorted(set(stores))
        if sources is None:
            sources = await self.sources(names)
        elif sorted(sources.tables) != names:
            raise ValueError(
                f"these sources were read for other stores ({', '.join(sorted(sources.tables))}) "
                f"than the build is asked for ({', '.join(names)})"
            )
        tables = sources.tables
        out.mkdir(parents=True, exist_ok=True)
        candidates, counts = await self._clusters(tables, sources.suppression)
        clusters, not_cards = await self._cards_only(candidates, names)
        building = Path(tempfile.mkdtemp(prefix=".building-", dir=out))
        try:
            await self._write_index(building / SEARCH_INDEX_SQLITE_NAME, clusters, provenance_limit)
            self._writer.compress(building / SEARCH_INDEX_SQLITE_NAME, building / SEARCH_INDEX_GZIP_NAME)
            sqlite_file = _index_file(building / SEARCH_INDEX_SQLITE_NAME)
            gzip_object = _index_file(building / SEARCH_INDEX_GZIP_NAME)
            manifest = SearchIndexManifest(
                format_version=SEARCH_INDEX_FORMAT_VERSION,
                index_id=sqlite_file.sha256[:INDEX_ID_LENGTH],
                parser_version=self._parser_version,
                fingerprint_version=FINGERPRINT_VERSION,
                sqlite_version=self._writer.sqlite_version,
                sqlite_feature_ceiling=SQLITE_FEATURE_CEILING,
                provenance_limit=provenance_limit,
                stores=sources.stores,
                snapshot=_snapshot_of(tables),
                suppression=sources.suppression_list,
                counts=IndexCounts(
                    documents=len(clusters),
                    documents_by_store={
                        name: sum(1 for cluster in clusters if cluster.caselist == name) for name in names
                    },
                    occurrences=sum(len(cluster.members) for cluster in clusters),
                    provenance_rows=sum(min(len(cluster.members), provenance_limit) for cluster in clusters),
                    occurrence_rows_read=sum(len(rows) for rows, _ in tables.values()),
                    suppressed_occurrences=counts.suppressed,
                    clusters_left_out=counts.left_out,
                    unattributed_representatives=sum(
                        1 for cluster in clusters if not cluster.representative.attributed
                    ),
                ),
                sqlite_file=sqlite_file,
                gzip_object=gzip_object,
            )
            (building / SEARCH_INDEX_MANIFEST_NAME).write_bytes(manifest.to_json_bytes())
            final = out / manifest.index_id
            if final.exists():
                shutil.rmtree(final)
            building.rename(final)
        except BaseException:
            shutil.rmtree(building, ignore_errors=True)
            raise
        return BuiltSearchIndex(
            directory=final,
            manifest=manifest,
            not_cards=not_cards,
        )

    # -- reading --------------------------------------------------------------------------------

    async def _suppression_state(self) -> tuple[SuppressionState, SuppressionListState]:
        entries = await self._suppression.entries()
        holds = await read_path_holds(self._suppression)
        lines = sorted(
            [f"entry {canonical_line(one)}" for one in entries]
            + [f"hold {canonical_line(one)}" for one in holds]
        )
        digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
        return (
            SuppressionState.from_entries(entries, holds),
            SuppressionListState(entries=len(entries), path_holds=len(holds), sha256=digest),
        )

    async def _read(self, caselist: str) -> tuple[tuple[OccurrenceRecord, ...], StoreState]:
        """The rows of the newest generation of the running parser version's directory, and its state.

        A parser version begins with its date, so a version that sorts after this build's was written
        by a newer build (`v1-e31-t16`'s order).
        """
        directories = [
            parse_version_directory(name) for name in await self._store.version_directories(caselist)
        ]
        parsed_by = sorted({named for named, _ in directories})
        generations = [generation for named, generation in directories if named == self._parser_version]
        if not generations:
            refusal = SearchIndexStoreVersionMismatch if parsed_by else SearchIndexStoreNotReady
            raise refusal(
                caselist,
                f"no version directory of parser {self._parser_version}"
                + (f" (it was parsed by {', '.join(parsed_by)})" if parsed_by else "")
                + f"; run `debate-research caselist parse --caselist {caselist}`",
            )
        newer = [named for named in parsed_by if named > self._parser_version]
        if newer:
            raise SearchIndexStoreVersionMismatch(
                caselist,
                f"it was parsed by {newer[-1]}, a newer parser than this build's {self._parser_version}; "
                "index it with the build that parsed it",
            )
        version = version_directory_name(self._parser_version, max(generations))
        rows = await self._store.read_occurrences(caselist, version)
        if rows is None:
            raise SearchIndexStoreNotReady(
                caselist,
                f"{version} has no occurrences.jsonl; rebuild it with "
                f"`debate-research caselist parse --caselist {caselist}`",
            )
        if not rows:
            raise SearchIndexStoreNotReady(caselist, f"{version}'s occurrence table holds no rows")
        stale = sorted({row.fingerprint_version for row in rows} - {FINGERPRINT_VERSION})
        if stale:
            raise SearchIndexStoreVersionMismatch(
                caselist,
                f"its rows carry fingerprint version {', '.join(stale)}, "
                f"not this build's {FINGERPRINT_VERSION}; "
                f"rebuild it with `debate-research caselist parse --caselist {caselist}`",
            )
        lines = sorted(canonical_line(row) for row in rows)
        latest = min(rows, key=_recency).last_snapshot
        return rows, StoreState(
            caselist=caselist,
            version_directory=version,
            latest_snapshot=latest,
            occurrence_rows=len(rows),
            occurrences_sha256=hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        )

    async def _clusters(
        self, tables: Mapping[str, tuple[tuple[OccurrenceRecord, ...], StoreState]], state: SuppressionState
    ) -> tuple[list[_Cluster], _Dropped]:
        """Every cluster with a surviving row, in (caselist, cluster id) order, its rows in order."""
        dropped = _Dropped()
        grouped: dict[tuple[str, str], list[_Joined]] = {}
        versions: dict[str, str] = {}
        for caselist, (rows, store_state) in tables.items():
            versions[caselist] = store_state.version_directory
            records = _Records(self._caselists, self._release_manifest_lines)
            for row in rows:
                key = (row.caselist, row.cluster_id)
                members = grouped.setdefault(key, [])
                if state.suppresses(row.source_sha256, disclosure=row.disclosure):
                    dropped.suppressed += 1
                    continue
                disclosure, held = await records.disclosure_of(row, state)
                if held:
                    dropped.suppressed += 1
                    continue
                members.append(
                    _Joined(row, disclosure, await records.camp_file_of(row), records.openev_id_of(row))
                )
        clusters: list[_Cluster] = []
        for caselist, cluster_id in sorted(grouped):
            members = grouped[(caselist, cluster_id)]
            if not members:
                dropped.left_out += 1
                continue
            clusters.append(
                _Cluster(
                    caselist=caselist,
                    version=versions[caselist],
                    cluster_id=cluster_id,
                    members=tuple(sorted(members, key=lambda one: one.order)),
                )
            )
        return clusters, dropped

    async def _representatives(
        self, clusters: Sequence[_Cluster]
    ) -> AsyncIterator[tuple[_Cluster, ParsedCard]]:
        """Each cluster with its representative's card, read from its source's record, a source at a time."""
        by_source: dict[tuple[str, str, str], list[_Cluster]] = defaultdict(list)
        for cluster in clusters:
            row = cluster.representative.row
            by_source[(cluster.caselist, cluster.version, row.source_sha256)].append(cluster)
        for (caselist, version, sha256), waiting in sorted(by_source.items()):
            record = await self._store.read_document(caselist, version, sha256)
            if record is None:
                raise SearchIndexStoreNotReady(
                    caselist,
                    f"an occurrence names source {sha256[:12]}, which has no document in {version}",
                )
            cards = {
                (card.provenance.first_element_index, card.provenance.last_element_index): card
                for card in record.to_parsed_document(_NO_PATH).cards
            }
            for cluster in waiting:
                yield cluster, _card_of(cluster, cards)

    async def _cards_only(
        self, candidates: Sequence[_Cluster], names: Sequence[str]
    ) -> tuple[list[_Cluster], NotCards]:
        """The clusters whose representative is a card, numbered from 1, and what was left out, by store.

        A pass over the representatives' sources before the one that writes, so the documents kept are
        numbered by their rank among themselves and the writer is handed each card once, as it is read.
        """
        not_cards = {name: dict.fromkeys(NotACard, 0) for name in names}
        left_out: set[tuple[str, str]] = set()
        async for cluster, card in self._representatives(candidates):
            reason = not_a_card(card)
            if reason is not None:
                not_cards[cluster.caselist][reason] += 1
                left_out.add((cluster.caselist, cluster.cluster_id))
        kept = [one for one in candidates if (one.caselist, one.cluster_id) not in left_out]
        return [replace(one, doc_id=number) for number, one in enumerate(kept, start=1)], not_cards

    # -- writing --------------------------------------------------------------------------------

    async def _write_index(
        self, destination: Path, clusters: Sequence[_Cluster], provenance_limit: int
    ) -> None:
        """Read each representative's card from its source's record, and write every document."""
        sink = self._writer.create(destination)
        try:
            async for cluster, card in self._representatives(clusters):
                sink.add(_document(cluster, card, provenance_limit, self._event_for_caselist))
        except BaseException:
            sink.abandon()
            raise
        sink.finish()


@dataclass
class _Dropped:
    suppressed: int = 0
    left_out: int = 0


class _Records:
    """The caselist records one store's rows join, read once per source."""

    def __init__(
        self, caselists: CaselistRepository, release_manifest_lines: Callable[[ObjectKey], Sequence[str]]
    ) -> None:
        self._caselists = caselists
        self._release_manifest_lines = release_manifest_lines
        self._disclosures: dict[tuple[str, str], tuple[Disclosure, ...]] = {}
        self._camp_files: dict[str, tuple[CampFile, ...]] = {}
        self._openev_ids: dict[str, dict[str, int]] = {}

    async def disclosure_of(
        self, row: OccurrenceRecord, state: SuppressionState
    ) -> tuple[Disclosure | None, bool]:
        """The latest disclosure record whose digest is the row's, and whether a path hold covers the row.

        Latest by snapshot and then path, as the recipe resolver takes it. A row is held when a hold
        covers any of its records: the rule a rebuilt table already applied, asked again.
        """
        if row.disclosure is None:
            return None, False
        key = (row.caselist, row.source_sha256)
        if key not in self._disclosures:
            self._disclosures[key] = await _all_pages(
                lambda cursor: self._caselists.list_disclosures(
                    caselist=row.caselist, source_sha256=row.source_sha256, limit=_PAGE, cursor=cursor
                )
            )
        matching = [
            one
            for one in self._disclosures[key]
            if disclosure_digest(row.caselist, one.source_path) == row.disclosure
        ]
        held = any(
            stored_row_hold(row.caselist, one.snapshot.isoformat(), row.source_sha256, one.source_path, state)
            is not None
            for one in matching
        )
        latest = max(matching, key=lambda one: (one.snapshot, one.source_path)) if matching else None
        return latest, held

    async def camp_file_of(self, row: OccurrenceRecord) -> CampFile | None:
        """The release record of a camp row: the camp file's record whose release is the row's."""
        if row.caselist != OPENEV_STORE:
            return None
        if row.source_sha256 not in self._camp_files:
            self._camp_files[row.source_sha256] = await _all_pages(
                lambda cursor: self._caselists.list_camp_files(
                    source_sha256=row.source_sha256, limit=_PAGE, cursor=cursor
                )
            )
        matching = [
            one
            for one in self._camp_files[row.source_sha256]
            if _release_name(one.year, one.event) == row.snapshot
        ]
        return max(matching, key=lambda one: (one.snapshot, one.camp, one.file_title)) if matching else None

    def openev_id_of(self, row: OccurrenceRecord) -> int | None:
        """A camp row's OpenEv id: its file's, as its release's manifest records it; `None` without one.

        A manifest this build cannot read is :class:`SearchIndexStoreNotReady`, never read as no ids.
        """
        if row.caselist != OPENEV_STORE:
            return None
        if row.snapshot not in self._openev_ids:
            key = snapshot_manifest_key(OPENEV, row.snapshot)
            try:
                recorded = read_recorded_release(key, self._release_manifest_lines(key))
            except UnreadableManifest as error:
                raise SearchIndexStoreNotReady(OPENEV_STORE, str(error)) from None
            self._openev_ids[row.snapshot] = openev_ids_by_source(recorded)
        return self._openev_ids[row.snapshot].get(row.source_sha256)


async def _all_pages[ItemT](read: Callable[[str | None], Awaitable[Page[ItemT]]]) -> tuple[ItemT, ...]:
    """Every item of a listing, all pages."""
    found: list[ItemT] = []
    cursor: str | None = None
    while True:
        page = await read(cursor)
        found += page.items
        if page.next_cursor is None:
            return tuple(found)
        cursor = page.next_cursor


def _release_event(release: str) -> str | None:
    """The event a camp release names, `POLICY` for `2026-policy`; `None` for a name it does not know."""
    event = _EVENT_BY_NAME.get(release.partition("-")[2])
    return event.value if event is not None else None


def _release_name(year: int, event: Event) -> str:
    """`2026-policy`, as `openev_manifest.openev_release_name` names a camp release."""
    return f"{year:04d}-{event.value.lower()}"


def _card_of(cluster: _Cluster, cards: Mapping[tuple[int, int], ParsedCard]) -> ParsedCard:
    row = cluster.representative.row
    card = cards.get((row.first_element_index, row.last_element_index))
    if card is None or card_fingerprint(card).exact_fingerprint != row.exact_fingerprint:
        raise SearchIndexStoreNotReady(
            cluster.caselist,
            f"source {row.source_sha256[:12]} holds no card at elements {row.first_element_index} to "
            f"{row.last_element_index} with the fingerprint its occurrence row records; re-run "
            f"`debate-research caselist parse --caselist {cluster.caselist}`",
        )
    return card


def _event_of(cluster: _Cluster, event_for_caselist: Callable[[str], Event | None]) -> Event:
    row = cluster.representative.row
    if row.caselist == OPENEV_STORE:
        named = _release_event(row.snapshot)
        event = Event(named) if named is not None else None
    else:
        event = event_for_caselist(row.caselist)
    if event is None:
        raise SearchIndexStoreNotReady(
            cluster.caselist, f"no event is known for the release or slug {row.snapshot}"
        )
    return event


def _document(
    cluster: _Cluster,
    card: ParsedCard,
    provenance_limit: int,
    event_for_caselist: Callable[[str], Event | None],
) -> SearchDocument:
    members = cluster.members
    camp = cluster.caselist == OPENEV_STORE
    disclosures = [one.disclosure for one in members if one.disclosure is not None]
    return SearchDocument(
        doc_id=cluster.doc_id,
        caselist=cluster.caselist,
        cluster_id=cluster.cluster_id,
        event=_event_of(cluster, event_for_caselist).value,
        camp=cluster.representative.row.camp,
        tag=card.tag,
        cite=cite_without_cutter_mark(card.full_cite),
        short_cite=card.short_cite,
        read_aloud=read_aloud_text(card.evidence_text, card.formatting_spans),
        text=card.evidence_text,
        completeness=card.completeness.value,
        formatting_spans=card.formatting_spans,
        font_size_spans=card.font_size_spans,
        sides=tuple(sorted({one.side.value for one in disclosures if one.side is not Side.UNKNOWN})),
        first_seen=None if camp else min(one.row.snapshot for one in members),
        last_seen=None if camp else max(one.row.last_snapshot for one in members),
        file_count=len({one.row.source_sha256 for one in members}),
        team_count=len({(one.school, one.team_code) for one in disclosures}),
        occurrences=tuple(
            _occurrence(ordinal, joined, provenance=ordinal < provenance_limit)
            for ordinal, joined in enumerate(members)
        ),
    )


def _occurrence(ordinal: int, joined: _Joined, *, provenance: bool) -> IndexedOccurrence:
    row = joined.row
    base = IndexedOccurrence(
        ordinal=ordinal,
        caselist=row.caselist,
        source_sha256=row.source_sha256,
        disclosure=row.disclosure,
        first_element_index=row.first_element_index,
        last_element_index=row.last_element_index,
        snapshot=row.snapshot,
        last_snapshot=row.last_snapshot,
        completeness=row.completeness.value,
        attributed=joined.attributed,
        provenance=provenance,
    )
    if not provenance:
        return base
    disclosure, camp_file = joined.disclosure, joined.camp_file
    if disclosure is not None:
        return replace(
            base,
            side=disclosure.side.value,
            school=disclosure.school,
            team_code=disclosure.team_code,
            tournament=disclosure.tournament,
            round=disclosure.round_label.raw if disclosure.round_label is not None else None,
        )
    if row.caselist == OPENEV_STORE:
        return replace(
            base,
            camp=row.camp or (camp_file.camp if camp_file is not None else None),
            camp_year=camp_file.year if camp_file is not None else int(row.snapshot[:4]),
            camp_event=camp_file.event.value if camp_file is not None else _release_event(row.snapshot),
            camp_file_title=camp_file.file_title if camp_file is not None else None,
            openev_id=joined.openev_id,
        )
    return base


def _snapshot_of(tables: Mapping[str, tuple[tuple[OccurrenceRecord, ...], StoreState]]) -> str:
    """The latest caselist snapshot read; the latest release when only camp files were read."""
    caselist = [state.latest_snapshot for name, (_, state) in tables.items() if name != OPENEV_STORE]
    if caselist:
        return max(caselist)
    return tables[OPENEV_STORE][1].latest_snapshot


def _index_file(path: Path) -> IndexFile:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
            size += len(chunk)
    return IndexFile(name=path.name, bytes=size, sha256=digest.hexdigest())

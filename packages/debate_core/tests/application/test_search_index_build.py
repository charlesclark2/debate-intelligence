"""`tub index build` over a synthetic store: what is indexed, which occurrence represents it, what never is.

The store is in memory (`InMemoryParsedStore`, `InMemoryCaselistRepository`) and the suppression list is
a local file under `tmp_path`, as the composition root wires it. The index is the real SQLite FTS5 file,
read back with `sqlite3`. Every expected value is written by hand from the fixtures below (working
agreement 6): which row of each cluster represents it, which strings a query may and may not find.

Every school, team code, tournament, round, path and card in this file is invented (data-use policy,
rule 5): Maple Grove, Riverbend, `QX`, `ZT`, the Invented Invitational.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import random
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

import jsonschema
import pytest

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.application.search_index_build import (
    SearchIndexBuildService,
    SearchIndexStoreNotReady,
    cite_without_cutter_mark,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import (
    CampFile,
    Disclosure,
    Event,
    RoundLabel,
    Side,
    SourceFormat,
    SourceOrigin,
)
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FontSizeSpan,
    FormattingSpan,
    ParsedCard,
    ParsedDocument,
)
from debate_core.domain.file_provenance import formatting_sha256
from debate_core.domain.search_index import (
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_MANIFEST_SCHEMA_FILENAME,
    SEARCH_INDEX_SQLITE_NAME,
    IndexedFontSizeSpan,
    IndexedFormattingSpan,
    SearchIndexManifest,
    decode_font_size_spans,
    decode_formatting_spans,
    read_aloud_text,
    render_search_index_manifest_schema,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
SCHEMA_PATH: Final = REPO_ROOT / "docs" / "data" / SEARCH_INDEX_MANIFEST_SCHEMA_FILENAME

CASELIST: Final = "hsld26"
CAMP: Final = "openev"
PARSER: Final = "2026.10.18-docx-5"
PROFILE: Final = "2026.09.20-verbatim-1"

SCHOOL: Final = "Maple Grove"
TEAM: Final = "QX"
OTHER_SCHOOL: Final = "Riverbend"
OTHER_TEAM: Final = "ZT"
TOURNAMENT: Final = "Invented Invitational"
ROUND: Final = "Round 4"
CUTTER: Final = "WXYZ"
"""A cutter mark that is no word of any card below, so a query that finds it found the mark."""


def sha(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def path_of(source: str, school: str = SCHOOL, team: str = TEAM, round_raw: str = ROUND) -> str:
    return f"{school}/{team}/{school}-{team}-Neg-{TOURNAMENT}-{round_raw}-{source[:6]}.docx"


def event_for(caselist: str) -> Event | None:
    return {CASELIST: Event.LD, "hspf26": Event.PF}.get(caselist)


# ------------------------------------------------------------------------------------------------
# The store
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Card:
    """A card in a source, with the cluster its occurrence rows put it in."""

    source: str
    element: int
    cluster: str
    card: ParsedCard

    @property
    def fingerprint(self) -> str:
        return card_fingerprint(self.card).exact_fingerprint


def parsed_card(
    source: str,
    element: int,
    text: str,
    *,
    tag: str | None = "Invented growth claim",
    cite: str = "Okonkwo 26, Invented Journal of Growth",
    completeness: CardCompleteness = CardCompleteness.FULL,
    spans: Sequence[FormattingSpan] = (),
    font_sizes: Sequence[FontSizeSpan] = (),
    camp: str | None = None,
) -> ParsedCard:
    return ParsedCard(
        tag=tag,
        short_cite="Okonkwo 26",
        full_cite=cite,
        evidence_text=text,
        completeness=completeness,
        formatting_spans=tuple(spans),
        font_size_spans=tuple(font_sizes),
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.9,
        provenance=FileImportProvenance(
            source_sha256=source,
            source_path="placeholder.docx",
            origin=SourceOrigin.OPENEV if camp else SourceOrigin.CASELIST_ARCHIVE,
            caselist=None if camp else CASELIST,
            camp=camp,
            snapshot=date(2026, 9, 1),
            first_element_index=element,
            last_element_index=element + 2,
            parser_version=PARSER,
            profile_version=PROFILE,
        ),
    )


@dataclass
class Store:
    """A synthetic parsed store, caselist records and suppression list, written on :meth:`ports`."""

    cards: list[Card] = field(default_factory=lambda: [])
    rows: dict[str, list[OccurrenceRecord]] = field(default_factory=lambda: {})
    disclosures: list[Disclosure] = field(default_factory=lambda: [])
    camp_files: list[CampFile] = field(default_factory=lambda: [])
    suppressions: list[SuppressionEntry] = field(default_factory=lambda: [])
    holds: list[PathHoldEntry] = field(default_factory=lambda: [])

    def card(self, source: str, element: int, cluster: str, text: str, **fields: Any) -> Card:
        held = Card(source, element, cluster, parsed_card(source, element, text, **fields))
        self.cards.append(held)
        return held

    def occurs(
        self,
        card: Card,
        *,
        path: str | None = None,
        first: str = "2026-09-01",
        last: str = "2026-09-08",
        disclosed_by: tuple[str, str] | None = None,
        side: Side = Side.NEG,
    ) -> OccurrenceRecord:
        """A caselist row of `card` at `path`; with `disclosed_by`, its disclosure is on record."""
        where = path or path_of(card.source)
        row = OccurrenceRecord(
            caselist=CASELIST,
            snapshot=first,
            last_snapshot=last,
            source_sha256=card.source,
            parser_version=PARSER,
            profile_version=PROFILE,
            fingerprint_version=FINGERPRINT_VERSION,
            disclosure=disclosure_digest(CASELIST, where),
            first_element_index=card.element,
            last_element_index=card.element + 2,
            exact_fingerprint=card.fingerprint,
            cluster_id=card.cluster,
            membership=ClusterMembership.NEAR_DUPLICATE,
            completeness=card.card.completeness,
        )
        self.rows.setdefault(CASELIST, []).append(row)
        if disclosed_by is not None:
            school, team = disclosed_by
            recorded = {(one.snapshot, one.source_path) for one in self.disclosures}
            for snapshot in sorted({first, last}):
                if (date.fromisoformat(snapshot), where) in recorded:
                    continue
                self.disclosures.append(
                    Disclosure(
                        source_sha256=card.source,
                        caselist=CASELIST,
                        snapshot=date.fromisoformat(snapshot),
                        event=Event.LD,
                        school=school,
                        team_code=team,
                        side=side,
                        tournament=TOURNAMENT,
                        round_label=RoundLabel.from_raw(ROUND),
                        source_path=where,
                    )
                )
        return row

    def released(self, card: Card, release: str, *, recorded: bool, title: str = "Invented Adv CP") -> None:
        """A camp row of `card` in `release`; with `recorded`, its release record is on file."""
        self.rows.setdefault(CAMP, []).append(
            OccurrenceRecord(
                caselist=CAMP,
                snapshot=release,
                last_snapshot=release,
                source_sha256=card.source,
                parser_version=PARSER,
                profile_version=PROFILE,
                fingerprint_version=FINGERPRINT_VERSION,
                disclosure=None,
                camp="Cascade Institute",
                first_element_index=card.element,
                last_element_index=card.element + 2,
                exact_fingerprint=card.fingerprint,
                cluster_id=card.cluster,
                membership=ClusterMembership.NEAR_DUPLICATE,
                completeness=card.card.completeness,
            )
        )
        if recorded:
            year, _, event = release.partition("-")
            self.camp_files.append(
                CampFile(
                    source_sha256=card.source,
                    camp="Cascade Institute",
                    year=int(year),
                    event=Event(event.upper()),
                    file_title=title,
                    snapshot=date(int(year), 7, 1),
                )
            )

    def suppress(self, source: str, *, path: str | None = None) -> None:
        self.suppressions.append(
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=source,
                disclosure=disclosure_digest(CASELIST, path) if path is not None else None,
                recorded_at=datetime(2026, 10, 1, tzinfo=UTC),
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-01",
            )
        )

    def hold(self, removed: str, path: str, *, after: str = "2026-08-25") -> None:
        """A removal of `removed` that holds `path` against uploads after `after`."""
        self.suppress(removed)
        self.holds.append(
            PathHoldEntry(
                caselist=CASELIST,
                disclosure=disclosure_digest(CASELIST, path),
                sha256=removed,
                after_snapshot=date.fromisoformat(after),
                recorded_at=datetime(2026, 10, 1, tzinfo=UTC),
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-02",
            )
        )

    def service(
        self, data_dir: Path, *, seed: int | None = None, extra_sources: Sequence[Card] = ()
    ) -> Ports:
        """The four ports written, rows and records in a shuffled order when `seed` is given."""

        def shuffle(items: list[Any]) -> None:
            if seed is not None:
                random.Random(f"{seed}-{len(items)}").shuffle(items)

        store = InMemoryParsedStore()
        caselists = InMemoryCaselistRepository()
        by_source: dict[tuple[str, str], list[Card]] = {}
        for card in [*self.cards, *extra_sources]:
            caselist = CAMP if card.card.provenance.camp else CASELIST
            by_source.setdefault((caselist, card.source), []).append(card)
        sources = list(by_source.items())
        shuffle(sources)
        for (caselist, source), cards in sources:
            ordered = sorted(cards, key=lambda one: one.element)
            snapshot = "2026-policy" if caselist == CAMP else "2026-09-01"
            entry = SourceEntry(
                caselist=caselist,
                snapshot=snapshot,
                source_sha256=source,
                parser_version=PARSER,
                profile_version=PROFILE,
                fingerprint_version=FINGERPRINT_VERSION,
                source_format=SourceFormat.DOCX,
                byte_size=100,
                outcome=SourceOutcome.PARSED,
                cards=len(ordered),
            )
            document = ParsedDocument(
                source_sha256=source,
                source_path="placeholder.docx",
                parser_version=PARSER,
                profile_version=PROFILE,
                cards=tuple(one.card for one in ordered),
            )
            record = DocumentRecord.from_parsed_document(
                document,
                caselist=caselist,
                snapshot=snapshot,
                fingerprint_version=FINGERPRINT_VERSION,
                camp="Cascade Institute" if caselist == CAMP else None,
            )
            asyncio.run(store.write_source(caselist, PARSER, entry, record))
        for caselist, rows in sorted(self.rows.items()):
            listed = list(rows)
            shuffle(listed)
            asyncio.run(store.write_aggregates(caselist, PARSER, index=(), failures=(), occurrences=listed))
        disclosures, camp_files = list(self.disclosures), list(self.camp_files)
        shuffle(disclosures)
        shuffle(camp_files)
        for one in disclosures:
            asyncio.run(caselists.record_disclosure(one))
        for one in camp_files:
            asyncio.run(caselists.record_camp_file(one))
        suppression = RecordedSuppressionList(local_suppression_list_file(data_dir))
        entries, holds = list(self.suppressions), list(self.holds)
        shuffle(entries)
        shuffle(holds)
        if entries:
            asyncio.run(suppression.append(entries))
        if holds:
            asyncio.run(suppression.append_path_holds(holds))
        return Ports(
            SearchIndexBuildService(
                parsed_store=store,
                caselists=caselists,
                suppression=suppression,
                writer=SqliteSearchIndexWriter(),
                parser_version=PARSER,
                event_for_caselist=event_for,
            )
        )


@dataclass(frozen=True)
class Ports:
    service: SearchIndexBuildService

    def build(self, out: Path, stores: Sequence[str] = (CASELIST,), **options: Any) -> Built:
        built = asyncio.run(self.service.build(stores, out, **options))
        return Built(built.directory, built.manifest)


@dataclass(frozen=True)
class Built:
    directory: Path
    manifest: SearchIndexManifest

    @property
    def sqlite(self) -> Path:
        return self.directory / SEARCH_INDEX_SQLITE_NAME

    def query(self, sql: str, *parameters: object) -> list[tuple[Any, ...]]:
        with sqlite3.connect(f"file:{self.sqlite}?mode=ro", uri=True) as connection:
            return connection.execute(sql, parameters).fetchall()

    def matches(self, expression: str) -> int:
        return int(self.query("SELECT count(*) FROM search WHERE search MATCH ?", expression)[0][0])

    def representatives(self) -> dict[str, tuple[str, int, str | None]]:
        """Cluster id to the representative's (source, element, disclosure digest)."""
        rows = self.query(
            "SELECT d.cluster_id, o.source_sha256, o.first_element_index, o.disclosure "
            "FROM documents d JOIN occurrences o ON o.doc_id = d.doc_id AND o.ordinal = 0"
        )
        return {cluster: (source, element, disclosure) for cluster, source, element, disclosure in rows}


# ------------------------------------------------------------------------------------------------
# The standard store: one cluster for each step of the representative order
# ------------------------------------------------------------------------------------------------

S_ZERO, S_ONE, S_TWO, S_THREE, S_FOUR = "0" * 64, "1" * 64, "2" * 64, "3" * 64, "4" * 64
"""Five sources, in the order of their digests. Nobody's disclosure of source zero is on record."""

BY_COMPLETENESS, BY_ATTRIBUTION, BY_RECENCY, BY_KEY = (
    sha("cluster completeness"),
    sha("cluster attribution"),
    sha("cluster recency"),
    sha("cluster key"),
)
PATH_A, PATH_B = path_of(S_ONE, SCHOOL, TEAM, "Round 5"), path_of(S_ONE, OTHER_SCHOOL, OTHER_TEAM)
D_A, D_B = disclosure_digest(CASELIST, PATH_A), disclosure_digest(CASELIST, PATH_B)
FIRST_OF_TWO_DISCLOSURES: Final = min(D_A, D_B)
SCHOOLS_IN_KEY_ORDER: Final = (SCHOOL, OTHER_SCHOOL) if D_A < D_B else (OTHER_SCHOOL, SCHOOL)


def standard_store() -> Store:
    store = Store()
    # FULL beats ABBREVIATED, though the abbreviated row is attributed, later and the smaller key.
    abbreviated = store.card(
        S_ONE, 0, BY_COMPLETENESS, "Invented growth ... ends badly", completeness=CardCompleteness.ABBREVIATED
    )
    full = store.card(
        S_FOUR,
        0,
        BY_COMPLETENESS,
        "Invented growth always ends badly for everyone involved",
        spans=(span(RunEmphasis.UNDERLINE, 0, 22), span(RunEmphasis.HIGHLIGHT, 9, 15, "yellow")),
        font_sizes=(
            FontSizeSpan(start_offset=0, end_offset=22, half_points=22),
            FontSizeSpan(start_offset=23, end_offset=55, half_points=12),
        ),
    )
    store.occurs(abbreviated, last="2026-09-29", disclosed_by=(SCHOOL, TEAM))
    store.occurs(full, last="2026-09-08")
    # Attributed beats unattributed, though the unattributed row is later and the smaller key.
    loose = store.card(S_ZERO, 10, BY_ATTRIBUTION, "Invented tariffs collapse invented trade")
    owned = store.card(S_TWO, 10, BY_ATTRIBUTION, "Invented tariffs collapse invented trade")
    store.occurs(loose, last="2026-09-29")
    store.occurs(owned, last="2026-09-08", disclosed_by=(OTHER_SCHOOL, OTHER_TEAM))
    # The latest last snapshot beats the smaller key.
    older = store.card(S_ONE, 20, BY_RECENCY, "Invented warming melts invented ice")
    newer = store.card(S_TWO, 20, BY_RECENCY, "Invented warming melts invented ice")
    store.occurs(older, last="2026-09-08", disclosed_by=(SCHOOL, TEAM))
    store.occurs(newer, last="2026-09-15", disclosed_by=(OTHER_SCHOOL, OTHER_TEAM))
    # Then the smallest occurrence key: source, element, disclosure digest.
    # Formatted, so the byte-identity tests cover the stored spans (PM review 2026-10-20).
    shared = store.card(
        S_ONE,
        30,
        BY_KEY,
        "Invented hegemony prevents invented conflict",
        spans=(span(RunEmphasis.UNDERLINE, 0, 26), span(RunEmphasis.HIGHLIGHT, 9, 17, "cyan")),
    )
    bigger = store.card(
        S_THREE,
        30,
        BY_KEY,
        "Invented hegemony prevents invented conflict",
        spans=(span(RunEmphasis.UNDERLINE, 0, 17),),
    )
    store.occurs(shared, path=PATH_A, disclosed_by=(SCHOOL, TEAM))
    store.occurs(shared, path=PATH_B, disclosed_by=(OTHER_SCHOOL, OTHER_TEAM))
    store.occurs(bigger, disclosed_by=(SCHOOL, TEAM), side=Side.AFF)
    return store


#: Written by hand from :func:`standard_store`: the (source, element, disclosure) each cluster is read from.
STANDARD_REPRESENTATIVES: Final = {
    BY_COMPLETENESS: (S_FOUR, 0, disclosure_digest(CASELIST, path_of(S_FOUR))),
    BY_ATTRIBUTION: (S_TWO, 10, disclosure_digest(CASELIST, path_of(S_TWO))),
    BY_RECENCY: (S_TWO, 20, disclosure_digest(CASELIST, path_of(S_TWO))),
    BY_KEY: (S_ONE, 30, FIRST_OF_TWO_DISCLOSURES),
}


@pytest.fixture
def standard(tmp_path: Path) -> Built:
    return standard_store().service(tmp_path / "data").build(tmp_path / "out")


# ------------------------------------------------------------------------------------------------
# ac1: one document per cluster, its representative by the stated order, under five shuffles
# ------------------------------------------------------------------------------------------------


def test_search_index_holds_one_document_per_cluster(standard: Built) -> None:
    clusters = standard.query("SELECT cluster_id, caselist, occurrence_count FROM documents ORDER BY doc_id")
    assert clusters == sorted(
        [
            (BY_COMPLETENESS, CASELIST, 2),
            (BY_ATTRIBUTION, CASELIST, 2),
            (BY_RECENCY, CASELIST, 2),
            (BY_KEY, CASELIST, 3),
        ]
    )
    assert standard.manifest.counts.documents == 4
    assert standard.manifest.counts.occurrences == 9


@pytest.mark.parametrize("seed", [None, 1, 2, 3, 4, 5])
def test_search_index_representative_follows_the_order_under_five_shuffles(
    tmp_path: Path, seed: int | None
) -> None:
    built = standard_store().service(tmp_path / "data", seed=seed).build(tmp_path / "out")
    assert built.representatives() == STANDARD_REPRESENTATIVES


def test_search_index_occurrences_follow_the_order_after_the_representative(standard: Built) -> None:
    ordered = standard.query(
        "SELECT o.source_sha256, o.disclosure FROM occurrences o JOIN documents d USING (doc_id) "
        "WHERE d.cluster_id = ? ORDER BY o.ordinal",
        BY_KEY,
    )
    assert ordered == [
        (S_ONE, FIRST_OF_TWO_DISCLOSURES),
        (S_ONE, max(D_A, D_B)),
        (S_THREE, disclosure_digest(CASELIST, path_of(S_THREE))),
    ]


def test_search_index_camp_representative_is_the_attributed_latest_release(tmp_path: Path) -> None:
    store = Store()
    cluster = sha("camp cluster")
    unrecorded = store.card(
        S_ONE, 0, cluster, "Invented camp evidence about invented trade", camp="Cascade Institute"
    )
    recorded = store.card(
        S_TWO, 0, cluster, "Invented camp evidence about invented trade", camp="Cascade Institute"
    )
    store.released(unrecorded, "2026-policy", recorded=False)
    store.released(recorded, "2025-policy", recorded=True)
    store.released(recorded, "2026-policy", recorded=True)
    built = store.service(tmp_path / "data", seed=7).build(tmp_path / "out", stores=(CAMP,))
    representative = built.query(
        "SELECT source_sha256, snapshot, camp, camp_year, camp_event, camp_file_title "
        "FROM occurrences ORDER BY ordinal"
    )
    assert representative == [
        (S_TWO, "2026-policy", "Cascade Institute", 2026, "POLICY", "Invented Adv CP"),
        (S_TWO, "2025-policy", "Cascade Institute", 2025, "POLICY", "Invented Adv CP"),
        (S_ONE, "2026-policy", "Cascade Institute", 2026, "POLICY", None),
    ]
    assert built.query("SELECT event, camp, first_seen, last_seen FROM documents") == [
        ("POLICY", "Cascade Institute", None, None)
    ]


# ------------------------------------------------------------------------------------------------
# ac2: school, team code, tournament and round are stored, never searchable
# ------------------------------------------------------------------------------------------------


def test_search_index_school_and_team_code_match_nothing(standard: Built) -> None:
    stored = standard.query(
        "SELECT DISTINCT school, team_code, tournament, round FROM occurrences WHERE school IS NOT NULL"
    )
    assert set(stored) == {(SCHOOL, TEAM, TOURNAMENT, ROUND), (OTHER_SCHOOL, OTHER_TEAM, TOURNAMENT, ROUND)}
    for value in (
        SCHOOL,
        TEAM,
        OTHER_SCHOOL,
        OTHER_TEAM,
        TOURNAMENT,
        ROUND,
        "Grove",
        "Riverbend",
        "Invitational",
    ):
        assert standard.matches(f'"{value}"') == 0, value
    assert standard.matches('"invented hegemony"') == 1, "the same query finds what is searchable"


def test_search_index_searches_only_tag_cite_read_aloud_and_text(standard: Built) -> None:
    columns = [row[1] for row in standard.query("PRAGMA table_info(search)")]
    assert columns == ["tag", "cite", "read_aloud", "text"]
    fts_tables = {
        name for (name,) in standard.query("SELECT name FROM sqlite_master WHERE sql LIKE '%fts5%'")
    }
    assert fts_tables == {"search"}


# ------------------------------------------------------------------------------------------------
# ac3: suppression
# ------------------------------------------------------------------------------------------------


def test_search_index_leaves_out_a_suppressed_occurrence_and_an_emptied_cluster(tmp_path: Path) -> None:
    store = standard_store()
    store.suppress(S_FOUR)  # BY_COMPLETENESS's FULL card: the ABBREVIATED one represents it now
    store.suppress(S_ONE, path=PATH_A)  # one of BY_KEY's two disclosures of source one
    gone = sha("cluster suppressed whole")
    only = store.card(S_FOUR, 40, gone, "Invented sanctions fail against invented states")
    store.occurs(only, disclosed_by=(SCHOOL, TEAM))
    built = store.service(tmp_path / "data", seed=3).build(tmp_path / "out")

    assert gone not in {cluster for (cluster,) in built.query("SELECT cluster_id FROM documents")}
    assert built.matches('"invented sanctions"') == 0
    assert built.query("SELECT count(*) FROM occurrences WHERE source_sha256 = ?", S_FOUR) == [(0,)]
    assert built.query("SELECT count(*) FROM occurrences WHERE disclosure = ?", D_A) == [(0,)]
    representatives = built.representatives()
    assert representatives[BY_COMPLETENESS] == (S_ONE, 0, disclosure_digest(CASELIST, path_of(S_ONE)))
    assert representatives[BY_KEY] == (S_ONE, 30, D_B)
    counts = built.manifest.counts
    assert (counts.documents, counts.suppressed_occurrences, counts.clusters_left_out) == (4, 3, 1)


def test_search_index_leaves_out_a_row_a_path_hold_covers(tmp_path: Path) -> None:
    store = standard_store()
    store.hold(sha("the removed file"), path_of(S_THREE), after="2026-08-25")
    built = store.service(tmp_path / "data").build(tmp_path / "out")
    assert built.query("SELECT count(*) FROM occurrences WHERE source_sha256 = ?", S_THREE) == [(0,)]
    assert built.manifest.counts.suppressed_occurrences == 1


# ------------------------------------------------------------------------------------------------
# ac4 and ac7: byte-identical, the manifest's schema, digests, versions and gzip header
# ------------------------------------------------------------------------------------------------


def test_search_index_same_store_gives_identical_bytes_under_shuffles(tmp_path: Path) -> None:
    builds = [
        standard_store().service(tmp_path / f"data-{seed}", seed=seed).build(tmp_path / f"out-{seed}")
        for seed in (None, 11, 12, 13, 14, 15)
    ]
    for name in (SEARCH_INDEX_SQLITE_NAME, SEARCH_INDEX_GZIP_NAME, SEARCH_INDEX_MANIFEST_NAME):
        assert len({(built.directory / name).read_bytes() for built in builds}) == 1, name
    assert len({built.directory.name for built in builds}) == 1


def test_search_index_manifest_schema_committed_matches_the_models() -> None:
    assert SCHEMA_PATH.is_file(), "missing; run: uv run scripts/export_search_index_schema.py"
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == render_search_index_manifest_schema(), (
        "stale; run: uv run scripts/export_search_index_schema.py"
    )


def test_search_index_manifest_validates_against_the_committed_schema(standard: Built) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(json.loads((standard.directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes()), schema)


def test_search_index_manifest_records_both_digests_and_the_versions(standard: Built) -> None:
    manifest = standard.manifest
    sqlite_bytes = standard.sqlite.read_bytes()
    gzip_bytes = (standard.directory / SEARCH_INDEX_GZIP_NAME).read_bytes()
    assert manifest.sqlite_file.sha256 == hashlib.sha256(sqlite_bytes).hexdigest()
    assert manifest.sqlite_file.bytes == len(sqlite_bytes)
    assert manifest.gzip_object.sha256 == hashlib.sha256(gzip_bytes).hexdigest()
    assert manifest.gzip_object.bytes == len(gzip_bytes)
    assert gzip.decompress(gzip_bytes) == sqlite_bytes
    assert manifest.index_id == manifest.sqlite_file.sha256[:16] == standard.directory.name
    assert manifest.sqlite_version == sqlite3.sqlite_version
    assert (manifest.format_version, manifest.sqlite_feature_ceiling) == (
        SEARCH_INDEX_FORMAT_VERSION,
        "3.40.0",
    )
    assert (manifest.parser_version, manifest.fingerprint_version) == (PARSER, FINGERPRINT_VERSION)
    assert standard.query("PRAGMA user_version") == [(SEARCH_INDEX_FORMAT_VERSION,)]
    assert dict(standard.query("SELECT key, value FROM index_info")) == {
        "format_version": str(SEARCH_INDEX_FORMAT_VERSION),
        "sqlite_feature_ceiling": "3.40.0",
    }


def test_search_index_gzip_header_has_no_time_and_no_name(standard: Built) -> None:
    header = (standard.directory / SEARCH_INDEX_GZIP_NAME).read_bytes()[:10]
    magic, method, flags, mtime = header[:2], header[2], header[3], header[4:8]
    assert (magic, method, flags, mtime) == (b"\x1f\x8b", 8, 0, b"\x00\x00\x00\x00"), "no FNAME, no MTIME"


def test_search_index_manifest_counts_and_stores(standard: Built) -> None:
    manifest = standard.manifest
    assert manifest.counts.documents_by_store == {CASELIST: 4}
    assert manifest.counts.provenance_rows == 9
    assert manifest.counts.occurrence_rows_read == 9
    assert manifest.counts.unattributed_representatives == 1
    assert [
        (store.caselist, store.version_directory, store.latest_snapshot) for store in manifest.stores
    ] == [(CASELIST, PARSER, "2026-09-29")]
    assert manifest.snapshot == "2026-09-29"


# ------------------------------------------------------------------------------------------------
# ac8: tag and cite from the document record; nothing a row does not name
# ------------------------------------------------------------------------------------------------


def test_search_index_tag_and_cite_come_from_the_document_record(tmp_path: Path) -> None:
    store = Store()
    tagged = store.card(
        S_ONE, 0, sha("tagged"), "Invented deterrence holds", tag="Deterrence holds", cite="Adeyemi 25"
    )
    untagged = store.card(S_ONE, 5, sha("untagged"), "Invented diplomacy works", tag=None, cite="Brandt 24")
    store.occurs(tagged, disclosed_by=(SCHOOL, TEAM))
    store.occurs(untagged, disclosed_by=(SCHOOL, TEAM))
    built = store.service(tmp_path / "data").build(tmp_path / "out")
    assert built.query("SELECT cluster_id, tag, cite FROM documents ORDER BY cluster_id") == sorted(
        [(sha("tagged"), "Deterrence holds", "Adeyemi 25"), (sha("untagged"), None, "Brandt 24")]
    )


def test_search_index_holds_nothing_from_a_source_no_occurrence_row_names(tmp_path: Path) -> None:
    store = standard_store()
    unnamed = Card(
        S_FOUR, 50, sha("unnamed"), parsed_card(S_FOUR, 50, "Invented colonies thrive on invented moons")
    )
    held_upload = Card(
        sha("held upload"), 0, sha("held"), parsed_card(sha("held upload"), 0, "Invented tides rise")
    )
    built = store.service(tmp_path / "data", extra_sources=(unnamed, held_upload)).build(tmp_path / "out")
    assert built.matches('"invented colonies"') == 0
    assert built.matches('"invented tides"') == 0
    assert built.query(
        "SELECT count(*) FROM documents WHERE cluster_id IN (?, ?)", sha("unnamed"), sha("held")
    ) == [(0,)]
    assert built.query("SELECT count(*) FROM occurrences WHERE source_sha256 = ?", sha("held upload")) == [
        (0,)
    ]


# ------------------------------------------------------------------------------------------------
# What a document holds, and never holds
# ------------------------------------------------------------------------------------------------


def test_search_index_cite_keeps_no_cutter_mark(tmp_path: Path) -> None:
    store = Store()
    signed = store.card(
        S_ONE,
        0,
        sha("signed"),
        "Invented markets clear",
        cite=f"Okonkwo 26, https://example.org/a //{CUTTER}",
    )
    store.occurs(signed, disclosed_by=(SCHOOL, TEAM))
    built = store.service(tmp_path / "data").build(tmp_path / "out")
    assert built.query("SELECT cite FROM documents") == [("Okonkwo 26, https://example.org/a",)]
    assert built.matches(CUTTER) == 0
    assert CUTTER.encode() not in built.sqlite.read_bytes()
    assert CUTTER.lower().encode() not in built.sqlite.read_bytes()


@pytest.mark.parametrize(
    ("cite", "kept"),
    [
        ("Okonkwo 26 //JD", "Okonkwo 26"),
        ("Okonkwo 26 // averylongcutterhandle", "Okonkwo 26"),
        ("Okonkwo 26\nInvented Journal //ab/cd\n", "Okonkwo 26\nInvented Journal\n"),
        ("Okonkwo 26, https://example.org/a", "Okonkwo 26, https://example.org/a"),
        ("Okonkwo 26, at https://example.org", "Okonkwo 26, at https://example.org"),
        ("//JD", "//JD"),
        ("", ""),
    ],
)
def test_search_index_cite_without_cutter_mark(cite: str, kept: str) -> None:
    assert cite_without_cutter_mark(cite) == kept


def test_search_index_stores_no_path_or_file_name(standard: Built) -> None:
    raw = standard.sqlite.read_bytes()
    for text in (PATH_A, PATH_B, path_of(S_FOUR), ".docx", "placeholder", "not-read-by-the-search-index"):
        assert text.encode() not in raw, text


def test_search_index_read_aloud_is_the_underlined_or_highlighted_text(tmp_path: Path) -> None:
    text = "Invented growth always ends badly for everyone involved"
    spans = (
        FormattingSpan(
            emphasis=RunEmphasis.UNDERLINE,
            start_offset=0,
            end_offset=15,
            rule_id="test",
            match_source=StyleMatchSource.VERBATIM,
        ),
        FormattingSpan(
            emphasis=RunEmphasis.HIGHLIGHT,
            start_offset=9,
            end_offset=22,
            highlight_color="cyan",
            rule_id="test",
            match_source=StyleMatchSource.VERBATIM,
        ),
        FormattingSpan(
            emphasis=RunEmphasis.BOLD,
            start_offset=23,
            end_offset=27,
            rule_id="test",
            match_source=StyleMatchSource.VERBATIM,
        ),
        FormattingSpan(
            emphasis=RunEmphasis.UNDERLINE,
            start_offset=28,
            end_offset=33,
            rule_id="test",
            match_source=StyleMatchSource.VERBATIM,
        ),
    )
    store = Store()
    card = store.card(S_ONE, 0, sha("read aloud"), text, spans=spans)
    store.occurs(card, disclosed_by=(SCHOOL, TEAM))
    built = store.service(tmp_path / "data").build(tmp_path / "out")
    assert built.query("SELECT read_aloud FROM documents") == [("Invented growth always badly",)]
    assert built.query("SELECT formatting_spans FROM documents") == [
        ('[["UNDERLINE",0,15],["HIGHLIGHT",9,22,"cyan"],["BOLD",23,27],["UNDERLINE",28,33]]',)
    ]


def test_search_index_keeps_provenance_for_the_first_occurrences_only(tmp_path: Path) -> None:
    built = standard_store().service(tmp_path / "data").build(tmp_path / "out", provenance_limit=2)
    rows = built.query(
        "SELECT o.ordinal, o.provenance, o.school, o.side FROM occurrences o JOIN documents d USING (doc_id) "
        "WHERE d.cluster_id = ? ORDER BY o.ordinal",
        BY_KEY,
    )
    first, second = SCHOOLS_IN_KEY_ORDER
    assert rows == [(0, 1, first, "NEG"), (1, 1, second, "NEG"), (2, 0, None, None)]
    assert built.manifest.counts.provenance_rows == 8


def test_search_index_document_counts_sides_and_dates(standard: Built) -> None:
    rows = standard.query(
        "SELECT event, sides, first_seen, last_seen, file_count, team_count "
        "FROM documents WHERE cluster_id = ?",
        BY_KEY,
    )
    assert rows == [("LD", '["AFF","NEG"]', "2026-09-01", "2026-09-08", 2, 2)]


# ------------------------------------------------------------------------------------------------
# Refusals: a store that cannot be read as it stands is never read as empty
# ------------------------------------------------------------------------------------------------


def test_search_index_refuses_a_store_with_no_directory_of_this_parser(tmp_path: Path) -> None:
    ports = standard_store().service(tmp_path / "data")
    with pytest.raises(SearchIndexStoreNotReady, match="no version directory"):
        ports.build(tmp_path / "out", stores=(CASELIST, "hspf26"), provenance_limit=1)


def test_search_index_refuses_rows_of_another_fingerprint_version(tmp_path: Path) -> None:
    store = standard_store()
    store.rows[CASELIST] = [
        row.model_copy(update={"fingerprint_version": "card-fingerprint-v3"}) for row in store.rows[CASELIST]
    ]
    with pytest.raises(SearchIndexStoreNotReady, match="card-fingerprint-v3"):
        store.service(tmp_path / "data").build(tmp_path / "out")


def test_search_index_refuses_a_caselist_whose_event_it_does_not_know(tmp_path: Path) -> None:
    with pytest.raises(SearchIndexStoreNotReady, match="which event"):
        standard_store().service(tmp_path / "data").build(tmp_path / "out", stores=("zzzz26",))


def test_search_index_refuses_a_row_whose_card_is_not_in_its_source(tmp_path: Path) -> None:
    store = standard_store()
    representative = store.rows[CASELIST][1]  # BY_COMPLETENESS's FULL card, which represents it
    assert representative.source_sha256 == S_FOUR
    store.rows[CASELIST][1] = representative.model_copy(update={"exact_fingerprint": sha("another card")})
    with pytest.raises(SearchIndexStoreNotReady, match="holds no card"):
        store.service(tmp_path / "data").build(tmp_path / "out")
    assert [path.name for path in (tmp_path / "out").iterdir()] == [], "a failed build leaves nothing behind"


# ------------------------------------------------------------------------------------------------
# The stored spans: compact, and the same formatting (PM review 2026-10-20, question 4 (a))
# ------------------------------------------------------------------------------------------------

EVERY_EMPHASIS_TEXT: Final = "Invented growth always ends badly for everyone involved in invented trade"


def span(emphasis: RunEmphasis, start: int, end: int, colour: str | None = None) -> FormattingSpan:
    return FormattingSpan(
        emphasis=emphasis,
        start_offset=start,
        end_offset=end,
        highlight_color=colour,
        rule_id=f"verbatim-style-id:{emphasis.value.title()}",
        match_source=StyleMatchSource.VERBATIM,
    )


#: Every emphasis the parser writes, in the parser's order (not sorted), one with a colour.
EVERY_EMPHASIS: Final = (
    span(RunEmphasis.UNDERLINE, 0, 15),
    span(RunEmphasis.EMPHASIS, 9, 15),
    span(RunEmphasis.HIGHLIGHT, 9, 22, "cyan"),
    span(RunEmphasis.BOLD, 23, 27),
    span(RunEmphasis.UNDERLINE, 28, 33),
    span(RunEmphasis.SHRUNK, 34, 55),
    span(RunEmphasis.CITE, 56, 60),
    span(RunEmphasis.UNDERTAG, 60, 62),
    span(RunEmphasis.ANALYTIC, 62, 64),
    span(RunEmphasis.HEADING, 64, 66),
)
FONT_SIZES: Final = (
    FontSizeSpan(start_offset=0, end_offset=33, half_points=22),
    FontSizeSpan(start_offset=34, end_offset=55, half_points=12),
)

#: Written by hand from the two tuples above: what `documents` stores for them, byte for byte.
STORED_FORMATTING: Final = (
    '[["UNDERLINE",0,15],["EMPHASIS",9,15],["HIGHLIGHT",9,22,"cyan"],["BOLD",23,27],'
    '["UNDERLINE",28,33],["SHRUNK",34,55],["CITE",56,60],["UNDERTAG",60,62],["ANALYTIC",62,64],'
    '["HEADING",64,66]]'
)
STORED_FONT_SIZES: Final = "[[0,33,22],[34,55,12]]"


@pytest.fixture
def every_emphasis(tmp_path: Path) -> Built:
    store = Store()
    card = store.card(
        S_ONE, 0, sha("every emphasis"), EVERY_EMPHASIS_TEXT, spans=EVERY_EMPHASIS, font_sizes=FONT_SIZES
    )
    store.occurs(card, disclosed_by=(SCHOOL, TEAM))
    return store.service(tmp_path / "data").build(tmp_path / "out")


def test_search_index_stored_spans_decode_to_the_parser_spans_without_rule_or_match_source(
    every_emphasis: Built,
) -> None:
    assert {one.emphasis for one in EVERY_EMPHASIS} == set(RunEmphasis), "the fixture uses every emphasis"
    formatting, font_sizes = every_emphasis.query("SELECT formatting_spans, font_size_spans FROM documents")[
        0
    ]

    assert (formatting, font_sizes) == (STORED_FORMATTING, STORED_FONT_SIZES)
    assert decode_formatting_spans(formatting) == (
        IndexedFormattingSpan(RunEmphasis.UNDERLINE, 0, 15),
        IndexedFormattingSpan(RunEmphasis.EMPHASIS, 9, 15),
        IndexedFormattingSpan(RunEmphasis.HIGHLIGHT, 9, 22, "cyan"),
        IndexedFormattingSpan(RunEmphasis.BOLD, 23, 27),
        IndexedFormattingSpan(RunEmphasis.UNDERLINE, 28, 33),
        IndexedFormattingSpan(RunEmphasis.SHRUNK, 34, 55),
        IndexedFormattingSpan(RunEmphasis.CITE, 56, 60),
        IndexedFormattingSpan(RunEmphasis.UNDERTAG, 60, 62),
        IndexedFormattingSpan(RunEmphasis.ANALYTIC, 62, 64),
        IndexedFormattingSpan(RunEmphasis.HEADING, 64, 66),
    )
    assert decode_font_size_spans(font_sizes) == (
        IndexedFontSizeSpan(0, 33, 22),
        IndexedFontSizeSpan(34, 55, 12),
    )
    assert (
        "rule_id" not in formatting and "verbatim-style-id" not in formatting and "VERBATIM" not in formatting
    )


def test_search_index_read_aloud_and_formatting_coverage_are_unchanged_by_the_encoding(
    every_emphasis: Built,
) -> None:
    text, read_aloud, formatting, font_sizes = every_emphasis.query(
        "SELECT text, read_aloud, formatting_spans, font_size_spans FROM documents"
    )[0]
    decoded = decode_formatting_spans(formatting)

    assert read_aloud == "Invented growth always badly"
    assert (
        read_aloud_text(text, decoded) == read_aloud == read_aloud_text(EVERY_EMPHASIS_TEXT, EVERY_EMPHASIS)
    )
    rebuilt = tuple(
        FormattingSpan(
            emphasis=one.emphasis,
            start_offset=one.start_offset,
            end_offset=one.end_offset,
            highlight_color=one.highlight_color,
            rule_id="read back from the index",
            match_source=StyleMatchSource.HEURISTIC,
        )
        for one in decoded
    )
    sizes = tuple(
        FontSizeSpan(start_offset=one.start_offset, end_offset=one.end_offset, half_points=one.half_points)
        for one in decode_font_size_spans(font_sizes)
    )
    assert formatting_sha256(rebuilt, sizes) == formatting_sha256(EVERY_EMPHASIS, FONT_SIZES)


@pytest.mark.parametrize(
    "stored",
    ['{"emphasis": "UNDERLINE"}', '[["UNDERLINE",0]]', '[["NOT_AN_EMPHASIS",0,1]]', '[["UNDERLINE",5,2]]'],
)
def test_search_index_decode_refuses_what_the_encoder_never_writes(stored: str) -> None:
    with pytest.raises(ValueError):
        decode_formatting_spans(stored)


# ------------------------------------------------------------------------------------------------
# A camp file title is stored, never searchable (PM ruling 2026-10-20, question 1 (a))
# ------------------------------------------------------------------------------------------------


def test_search_index_camp_file_title_matches_nothing(tmp_path: Path) -> None:
    store = Store()
    card = store.card(
        S_ONE, 0, sha("camp title"), "Invented camp evidence about invented trade", camp="Cascade Institute"
    )
    store.released(card, "2026-policy", recorded=True, title="Zanzibar Quorum Counterplan")
    built = store.service(tmp_path / "data").build(tmp_path / "out", stores=(CAMP,))

    assert built.query("SELECT camp_file_title FROM occurrences") == [("Zanzibar Quorum Counterplan",)]
    for word in ("Zanzibar", "Quorum", "Counterplan", '"Zanzibar Quorum Counterplan"', "Cascade"):
        assert built.matches(word) == 0, word
    assert built.matches('"invented camp evidence"') == 1, "the same query finds what is searchable"


# ------------------------------------------------------------------------------------------------
# The digests the weekly run compares (v1-e39-t09, PM ruling 2026-10-20 Q2)
# ------------------------------------------------------------------------------------------------


def test_search_index_sources_digests_are_the_digests_a_real_build_records(tmp_path: Path) -> None:
    """One method computes both: what the weekly run compares with, and what the manifest records."""
    store = standard_store()
    store.suppress(S_THREE)
    store.released(
        store.card(S_ONE, 40, sha("camp digest"), "Invented camp trade evidence", camp="Cascade Institute"),
        "2026-ld",
        recorded=True,
    )
    ports = store.service(tmp_path / "data")

    sources = asyncio.run(ports.service.sources((CAMP, CASELIST)))
    built = ports.build(tmp_path / "out", stores=(CASELIST, CAMP))

    assert sources.stores == built.manifest.stores
    assert sources.suppression_list == built.manifest.suppression
    assert [one.caselist for one in sources.stores] == [CASELIST, CAMP], "by name, as the manifest lists them"
    assert built.manifest.suppression.entries == 1


def test_search_index_built_from_sources_read_first_is_the_same_index(tmp_path: Path) -> None:
    ports = standard_store().service(tmp_path / "data")

    sources = asyncio.run(ports.service.sources((CASELIST,)))
    given = asyncio.run(ports.service.build((CASELIST,), tmp_path / "given", sources=sources))
    read_again = ports.build(tmp_path / "read-again")

    assert given.manifest == read_again.manifest


def test_search_index_refuses_sources_read_for_other_stores(tmp_path: Path) -> None:
    ports = standard_store().service(tmp_path / "data")
    sources = asyncio.run(ports.service.sources((CASELIST,)))

    with pytest.raises(ValueError, match="read for other stores"):
        asyncio.run(ports.service.build((CASELIST, CAMP), tmp_path / "out", sources=sources))

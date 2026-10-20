"""A store rebuilt with cards that have no tag orders its tagged cards as before (`v1-e31-t14` ac3).

`v1-e31-t14` made "no tag" `None` in memory, where every build before it held `""`, and the cards
statistics sort and compare a cluster's (short cite, tag) labels. This test builds a parsed card
store with the real importer, parser and `caselist parse`, over four synthetic files whose cards are
tagged and untagged, rebuilds it, and checks the aggregates against an order worked out by hand
from the files below (working agreement 6): the occurrence table and the cards statistics.

It asks nothing of a tag beyond `tag or None`, so the same file runs on a build from before the
change: run with that build's `debate_core` first on `PYTHONPATH`, it passes there too. That run is
recorded in `docs/session-reports/v1-e31-t14-card-tag-optional.md`.

## The four files, and what they must give

Every school, team code, author, tag and word here is invented.

| File | Team | First card | Second card |
|---|---|---|---|
| `maple` | Maple Grove QX | "Canopy loss kills", Pellam heat | no tag, Thorne warehouse |
| `cedar` | Cedar Hollow ZaLu | no tag, Pellam heat | "Automation intensifies work", Thorne warehouse |
| `northgate` | Northgate BeCo | "Heat islands", Pellam heat | "Grid reserve margins are thinning", Okonkwo |
| `westfield` | Westfield XY | "Canopy loss kills", Pellam heat | |

* **Clusters, ranked by distinct teams:** heat (4 teams), warehouse (2), grid (1).
* **Labels**, the most frequent (short cite, tag) among a cluster's full cards, a tie going to the
  smallest, with no tag smallest of all as `""` was:
  heat: "Canopy loss kills" twice, no tag once, "Heat islands" once, so "Canopy loss kills";
  warehouse: no tag once, "Automation intensifies work" once, a tie, so no tag;
  grid: "Grid reserve margins are thinning".
* **Occurrence rows:** one per card per disclosure, 4 + 2 + 1 = 7, ordered by cluster id, then
  source, then paragraph.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardReport, CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.ports.parsed_store import SourceOutcome
from debate_core.domain.debate_files import ParsedCard
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore, SqliteDatabase
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.fakes import build_fake_caselist_repository

pytestmark = pytest.mark.anyio

CASELIST: Final = "testcl26"
SNAPSHOT: Final = date(2026, 9, 1)

HEAT: Final = (
    "Cities that pave over their green space do not merely lose shade; they lose the evening. The "
    "Varrow Commission's survey of forty mid-sized municipalities found that asphalt and roofing "
    "retain the afternoon's heat well past midnight, so that neighbourhoods with the least canopy "
    "cool the least overnight."
)
WAREHOUSE: Final = (
    "Automation rarely eliminates a job outright; it removes the tasks within a job that were "
    "easiest to measure. Injury reports rose in the eighteen months after installation, and "
    "turnover among new hires nearly doubled across every site the inspectors visited."
)
GRID: Final = (
    "Grid operators in the region reported that demand from new data centres rose faster than any "
    "other load category last year, and the increase outpaced every scenario the utility had "
    "planned against, leaving the reserve margin thinner than at any point in the past decade."
)
BODIES: Final = {"Pellam 26": HEAT, "Thorne 26": WAREHOUSE, "Okonkwo 26": GRID}


@dataclass(frozen=True, slots=True)
class SyntheticFile:
    name: str
    path: str
    cards: tuple[tuple[str | None, str], ...]
    """(tag, short cite) of each card in order; `None` is a card the file gives no tag."""

    @property
    def content(self) -> bytes:
        body = ""
        for tag, short_cite in self.cards:
            if tag is not None:
                body += paragraph_xml(run_xml(tag), style="Heading4")
            body += paragraph_xml(
                run_xml(short_cite, character_style="Style13ptBold")
                + run_xml(" (Invented Author, Fictional Review, 2026), example.invalid/review")
            )
            body += paragraph_xml(
                run_xml(BODIES[short_cite], character_style="StyleUnderline", underline="single")
            )
        return build_docx(body)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


FILES: Final = (
    SyntheticFile(
        "maple",
        "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
        (("Canopy loss kills", "Pellam 26"), (None, "Thorne 26")),
    ),
    SyntheticFile(
        "cedar",
        "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-Harbor Classic-Round 2.docx",
        ((None, "Pellam 26"), ("Automation intensifies work", "Thorne 26")),
    ),
    SyntheticFile(
        "northgate",
        "Northgate Prep/BeCo/Northgate Prep-BeCo-Neg-Ridgeline Round Robin-Round 3.docx",
        (("Heat islands", "Pellam 26"), ("Grid reserve margins are thinning", "Okonkwo 26")),
    ),
    SyntheticFile(
        "westfield",
        "Westfield/XY/Westfield-XY-Neg-Bayview Open-Round 6.docx",
        (("Canopy loss kills", "Pellam 26"),),
    ),
)
SOURCE_NAMES: Final = {file.sha256: file.name for file in FILES}

#: Each cluster by its short cite: its label's tag, and the files its rows come from, worked out by
#: hand in this module's docstring. Ranked by distinct teams.
EXPECTED_CLUSTERS: Final = (
    ("Pellam 26", "Canopy loss kills", 4, ("cedar", "maple", "northgate", "westfield")),
    ("Thorne 26", None, 2, ("cedar", "maple")),
    ("Okonkwo 26", "Grid reserve margins are thinning", 1, ("northgate",)),
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def import_files(data_dir: Path, zips_dir: Path) -> None:
    """One weekly archive holding the four files, imported by the real importer."""
    from debate_core.application.caselist.import_service import CaselistImportService
    from debate_core.application.caselist.manifest import manifest_key, write_manifest
    from debate_core.domain.caselist import Event
    from debate_core.integrations.local import FsSnapshotStore
    from debate_core.integrations.local.archive_reader import archive_digest, read_archive
    from debate_core.testing.fakes import empty_suppression_list

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in FILES:
            info = zipfile.ZipInfo(f"{CASELIST}-0901/{file.path}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, file.content)
    zips_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zips_dir / f"{CASELIST}-0901.zip"
    zip_path.write_bytes(buffer.getvalue())

    service = CaselistImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        suppression=empty_suppression_list(),
    )
    limit = 64 * 1024 * 1024
    report = await service.import_archive(
        read_archive(zip_path, max_archive_bytes=limit, max_unpacked_bytes=limit),
        caselist=CASELIST,
        snapshot=SNAPSHOT,
        event=Event("LD"),
        archive_sha256=archive_digest(zip_path),
    )
    write_manifest(report, FsEvidenceObjectStore(data_dir).path_for(manifest_key(CASELIST, SNAPSHOT)))


def parse_service(data_dir: Path) -> CaselistParseService:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return CaselistParseService(
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        store=LocalParsedStore(data_dir),
        parser=DebateDocxParser(),
        runner=InProcessParseRunner(),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        place_cards=CaselistCardStatsService(build_fake_caselist_repository()).place,
        failure_rate_threshold=1.0,
        failure_rate_minimum_sources=1,
    )


async def build_store(data_dir: Path) -> None:
    service = parse_service(data_dir)
    report = await service.run(await service.plan(CASELIST))
    assert report.store is not None


def aggregates(data_dir: Path) -> dict[str, bytes]:
    directory = LocalParsedStore(data_dir).root / CASELIST / DOCX_PARSER_VERSION
    return {name: (directory / name).read_bytes() for name in ("index.jsonl", "occurrences.jsonl")}


async def stored_cards(data_dir: Path) -> list[ParsedCard]:
    store = LocalParsedStore(data_dir)
    cards: list[ParsedCard] = []
    for entry in await store.read_entries(CASELIST, DOCX_PARSER_VERSION):
        assert entry.outcome is SourceOutcome.PARSED
        record = await store.read_document(CASELIST, DOCX_PARSER_VERSION, entry.source_sha256)
        assert record is not None
        cards.extend(record.to_parsed_document(f"{SOURCE_NAMES[entry.source_sha256]}.docx").cards)
    return cards


async def cards_report(data_dir: Path) -> CaselistCardReport:
    """What `caselist cards` reports over the store's cards and this machine's disclosures."""
    repository = SqliteCaselistRepository(SqliteDatabase.open(data_dir))
    return await CaselistCardStatsService(repository).report(
        await stored_cards(data_dir), caselist=CASELIST, top=10
    )


@pytest.fixture
async def data_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "evidence"
    await import_files(directory, tmp_path / "zips")
    await build_store(directory)
    return directory


async def test_the_files_are_read_as_the_table_says(data_dir: Path) -> None:
    """The premise: every card is read with the tag, or the lack of one, its file gives it."""
    cards = await stored_cards(data_dir)

    assert sorted(
        (SOURCE_NAMES[card.provenance.source_sha256], card.short_cite, card.tag or None) for card in cards
    ) == sorted((file.name, short_cite, tag) for file in FILES for tag, short_cite in file.cards)


async def test_a_rebuild_writes_the_same_aggregates_byte_for_byte(data_dir: Path) -> None:
    """The second run parses nothing and rebuilds the aggregates from the tags the store holds."""
    before = aggregates(data_dir)

    await build_store(data_dir)

    assert aggregates(data_dir) == before


async def test_the_occurrence_table_is_ordered_by_cluster_source_and_paragraph(data_dir: Path) -> None:
    await build_store(data_dir)
    rows = await LocalParsedStore(data_dir).read_occurrences(CASELIST, DOCX_PARSER_VERSION)
    assert rows is not None

    keys = [(row.cluster_id, row.source_sha256, row.first_element_index) for row in rows]
    assert keys == sorted(keys)
    assert len(rows) == 4 + 2 + 1
    report = await cards_report(data_dir)
    short_cite_of = {cluster.cluster_id: cluster.short_cite for cluster in report.top_clusters}
    by_cluster: dict[str | None, list[str]] = {}
    for row in rows:
        by_cluster.setdefault(short_cite_of[row.cluster_id], []).append(SOURCE_NAMES[row.source_sha256])
    assert {cite: sorted(names) for cite, names in by_cluster.items()} == {
        cite: list(names) for cite, _, _, names in EXPECTED_CLUSTERS
    }


async def test_the_cards_statistics_rank_and_label_the_clusters_as_before(data_dir: Path) -> None:
    await build_store(data_dir)
    report = await cards_report(data_dir)

    assert [
        (cluster.short_cite, cluster.tag or None, cluster.distinct_teams) for cluster in report.top_clusters
    ] == [(cite, tag, teams) for cite, tag, teams, _ in EXPECTED_CLUSTERS]


async def test_each_occurrence_keeps_its_cards_tag_in_the_order_of_the_table(data_dir: Path) -> None:
    report = await cards_report(data_dir)
    tags = {(file.name, short_cite): tag for file in FILES for tag, short_cite in file.cards}

    keys = [(occurrence.cluster_id, occurrence.occurrence_key) for occurrence in report.occurrences]
    assert keys == sorted(keys)
    assert [occurrence.tag or None for occurrence in report.occurrences] == [
        tags[(SOURCE_NAMES[occurrence.source_sha256], occurrence.short_cite or "")]
        for occurrence in report.occurrences
    ]
    assert sum(occurrence.tag is not None and occurrence.tag != "" for occurrence in report.occurrences) == 5

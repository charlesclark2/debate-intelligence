"""Michigan's three camps, filed apart as OpenEv files them, so their cards can link (`v1-e30-t32`).

Before this task `camp_aliases.yaml` merged `Michigan7`, `Michigan Classic`, `MNDI` and `Michigan
National Debate Institute` into one canonical camp, `Michigan`, which `v1-e39-t28`'s rule leaves
without an OpenEv word and so without a link. OpenEv's 2026 Files By Camp list, read by the PM on
2026-10-31, files three: `MNDI` ("Michigan (MNDI)"), `UM7` ("Michigan") and `UMC` ("Michigan
(Classic)"). The table now files `MNDI`, `Michigan7` and `Michigan Classic` apart, each with its word.
A bare `Michigan` may be any of the three, so it stays `Michigan`, with no word and no link: the count
of the stored files found nothing in a bare name that tells them apart (the session report).

Three parts:

* **The packaged table**, with its real camp names (camps are public, data-use policy rule 5) and
  invented titles and initials, in the naming shapes of the real release.
* **Whole-word matching, longest spelling first**, on an invented family of camps that overlap the
  way Michigan's do: a bare `Ridgeline` beside `Ridgeline Classic`, `Ridgeline7` and `RNDI`. The
  loader refuses only a spelling or a word given to two camps; overlapping spellings are told apart
  by the matcher, which tries the longest spelling first at each word, so the order of the table
  never matters.
* **Refiling the files already stored**: a release imported under the merged table, re-derived with
  the packaged one by the metadata re-import, which reads the recorded paths and never a file's bytes.

Every expected value is written by hand (working agreement 6).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.application.caselist.camp_metadata import (
    UNKNOWN_CAMP,
    CampAliases,
    InvalidCampAliases,
    load_camp_aliases,
    parse_camp_path,
)
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember
from debate_core.domain.caselist import Event
from debate_core.domain.evidence_search import OccurrenceProvenance
from debate_core.domain.search_source_links import SourceLink, source_link
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY, FsSnapshotStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.sqlite_db import SqliteDatabase
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord

PACKAGED: Final = load_camp_aliases()

# ------------------------------------------------------------------------------------------------
# The packaged table
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spelling", "camp"),
    [
        ("Michigan7", "Michigan7"),
        ("Michigan 7", "Michigan7"),
        ("UM7", "Michigan7"),
        ("Michigan Classic", "Michigan Classic"),
        ("Michigan (Classic)", "Michigan Classic"),
        ("UMC", "Michigan Classic"),
        ("MNDI", "MNDI"),
        ("Michigan National Debate Institute", "MNDI"),
        ("Michigan (MNDI)", "MNDI"),
        ("Michigan", "Michigan"),
    ],
)
def test_the_packaged_table_files_each_michigan_spelling_under_its_own_camp(spelling: str, camp: str) -> None:
    """OpenEv's words and labels among the spellings, so an OpenEv folder or label reads too."""
    assert PACKAGED.camp_for(spelling) == camp


def test_the_three_camps_have_openevs_words_and_a_bare_michigan_has_none() -> None:
    words = PACKAGED.openev_words
    assert {camp: words.get(camp) for camp in ("Michigan7", "Michigan Classic", "MNDI", "Michigan")} == {
        "Michigan7": "UM7",
        "Michigan Classic": "UMC",
        "MNDI": "MNDI",
        "Michigan": None,
    }


@pytest.mark.parametrize(
    ("path", "camp", "title"),
    [
        ("Disadvantages/Lantern DA - Michigan Classic 2026 PQR.docx", "Michigan Classic", "Lantern DA"),
        ("Kritiks/Tidewater Kritik 2 - Michigan7 2026 WXYZ.docx", "Michigan7", "Tidewater Kritik 2"),
        ("Kritiks/Tidewater Kritik - Michigan 7 2026 WX.docx", "Michigan7", "Tidewater Kritik"),
        ("Counterplans/Orchard Grants CP - MNDI 2026 JKT.docx", "MNDI", "Orchard Grants CP"),
        ("Topicality/Saltmarsh T - Michigan National Debate Institute 2026.docx", "MNDI", "Saltmarsh T"),
        ("Affirmatives/Ferry Aff - Michigan 2026 QRSV.docx", "Michigan", "Ferry Aff"),
        ("Affirmatives/Ferry Aff - Michigan 2026.docx", "Michigan", "Ferry Aff"),
        ("openev-41-Lantern_DA_-_Michigan_Classic_2026_PQR.docx", "Michigan Classic", "Lantern_DA"),
        ("2026/UM7/Lab Q/Basalt Advantage.docx", "Michigan7", "Basalt Advantage"),
        ("2026/UMC/Lab Q/Basalt Advantage.docx", "Michigan Classic", "Basalt Advantage"),
        ("2026/MNDI/Lab Q/Basalt Advantage.docx", "MNDI", "Basalt Advantage"),
        ("2026/Michigan Classic/Basalt Advantage.docx", "Michigan Classic", "Basalt Advantage"),
    ],
)  # fmt: skip
def test_a_michigan_file_is_filed_under_the_camp_its_name_spells(path: str, camp: str, title: str) -> None:
    parsed = parse_camp_path(path, aliases=PACKAGED)
    assert (parsed.camp, parsed.file_title, parsed.warnings) == (camp, title, ())


def camp_card(camp: str) -> OccurrenceProvenance:
    return OccurrenceProvenance(
        ordinal=0,
        caselist="openev",
        snapshot="2026-policy",
        last_snapshot="2026-policy",
        completeness="FULL",
        attributed=True,
        provenance=True,
        camp=camp,
        camp_year=2026,
        camp_event="POLICY",
        camp_file_title="Invented Adv CP",
    )


@pytest.mark.parametrize(
    ("camp", "expected"),
    [
        (
            "Michigan7",
            SourceLink(
                label="Find on OpenEv: Michigan7 2026 camp page",
                url="https://opencaselist.com/openev/2026/UM7",
            ),
        ),
        (
            "Michigan Classic",
            SourceLink(
                label="Find on OpenEv: Michigan Classic 2026 camp page",
                url="https://opencaselist.com/openev/2026/UMC",
            ),
        ),
        (
            "MNDI",
            SourceLink(
                label="Find on OpenEv: MNDI 2026 camp page", url="https://opencaselist.com/openev/2026/MNDI"
            ),
        ),
        ("Michigan", None),
    ],
)
def test_each_camp_card_links_to_its_own_camps_page_and_a_bare_michigan_to_none(
    camp: str, expected: SourceLink | None
) -> None:
    linked = source_link(camp_card(camp), openev_words=PACKAGED.openev_words, today=date(2026, 11, 1))
    assert linked == expected


# ------------------------------------------------------------------------------------------------
# Whole words, longest spelling first: an invented family of overlapping camps
# ------------------------------------------------------------------------------------------------

#: Invented camps that overlap as Michigan's do: a bare name that is the first word of the others.
FAMILY: Final[dict[str, list[str] | None]] = {
    "Ridgeline": None,
    "Ridgeline7": ["Ridgeline 7"],
    "Ridgeline Classic": None,
    "RNDI": ["Ridgeline National Debate Institute"],
}


def family(order: list[str]) -> CampAliases:
    return CampAliases.from_document({"camps": {camp: FAMILY[camp] for camp in order}}, source="t")


BARE_FIRST: Final = family(["Ridgeline", "Ridgeline7", "Ridgeline Classic", "RNDI"])
BARE_LAST: Final = family(["RNDI", "Ridgeline Classic", "Ridgeline7", "Ridgeline"])


@pytest.mark.parametrize("aliases", [BARE_FIRST, BARE_LAST], ids=["bare camp listed first", "listed last"])
@pytest.mark.parametrize(
    ("path", "camp", "title"),
    [
        ("Ferry Aff - Ridgeline Classic 2026 AB.docx", "Ridgeline Classic", "Ferry Aff"),
        ("Ridgeline Classic - Ferry Aff.docx", "Ridgeline Classic", "Ferry Aff"),
        ("Ferry Aff - Ridgeline7 2026 AB.docx", "Ridgeline7", "Ferry Aff"),
        ("Ferry Aff - Ridgeline 7 2026 AB.docx", "Ridgeline7", "Ferry Aff"),
        ("Ferry Aff - Ridgeline National Debate Institute 2026.docx", "RNDI", "Ferry Aff"),
        ("Ferry Aff - Ridgeline 2026 AB.docx", "Ridgeline", "Ferry Aff"),
        ("Ridgeline Classic/Lab Q/Ferry Aff.docx", "Ridgeline Classic", "Ferry Aff"),
        ("Ridgeline/Lab Q/Ferry Aff.docx", "Ridgeline", "Ferry Aff"),
    ],
)
def test_a_bare_spelling_never_swallows_a_longer_one_whatever_the_tables_order(
    aliases: CampAliases, path: str, camp: str, title: str
) -> None:
    parsed = parse_camp_path(path, aliases=aliases)
    assert (parsed.camp, parsed.file_title, parsed.warnings) == (camp, title, ())


def test_a_bare_name_beside_a_longer_camp_is_two_camps_and_never_a_guess() -> None:
    """`Ridgeline` in the title and `Ridgeline Classic` at the camp's place name two camps of the table."""
    parsed = parse_camp_path("Ridgeline Ferry Aff - Ridgeline Classic 2026.docx", aliases=BARE_FIRST)
    assert parsed.camp == UNKNOWN_CAMP
    assert parsed.warnings == (
        "the filename names more than one camp in the alias table (Ridgeline, Ridgeline Classic); "
        "camp recorded as UNKNOWN",
    )


def test_a_spelling_inside_a_longer_word_is_not_the_bare_camp() -> None:
    parsed = parse_camp_path("Ferry Aff - Ridgeline7X 2026.docx", aliases=BARE_FIRST)
    assert parsed.camp == UNKNOWN_CAMP


def test_the_loader_refuses_one_spelling_for_two_of_the_family() -> None:
    document = {"camps": {"Ridgeline": None, "Ridgeline7": ["Ridgeline"]}}
    with pytest.raises(InvalidCampAliases, match="'Ridgeline' is listed for both Ridgeline and Ridgeline7"):
        CampAliases.from_document(document, source="t")


def test_the_loader_refuses_one_openev_word_for_two_of_the_family() -> None:
    document = {"camps": FAMILY, "openev": {"Ridgeline7": "RDG7", "Ridgeline Classic": "RDG7"}}
    with pytest.raises(InvalidCampAliases, match="'RDG7' is given to both Ridgeline7 and Ridgeline Classic"):
        CampAliases.from_document(document, source="t")


# ------------------------------------------------------------------------------------------------
# Refiling the files already stored, from their recorded names
# ------------------------------------------------------------------------------------------------

#: The packaged table's Michigan entry as it was before this task, hand-copied: one merged camp.
MERGED: Final = CampAliases.from_document(
    {"camps": {"Michigan": ["Michigan7", "Michigan Classic", "MNDI", "Michigan National Debate Institute"]}},
    source="the table before v1-e30-t32",
)

YEAR, EVENT, IMPORTED_ON = 2026, Event.POLICY, date(2026, 9, 26)

#: Invented titles and initials in the real release's shape. Path, body, camp before and after.
RELEASE: Final[list[tuple[str, bytes, str, str]]] = [
    ("Disadvantages/Lantern DA - Michigan Classic 2026 PQR.docx", b"lantern", "Michigan", "Michigan Classic"),
    ("Kritiks/Tidewater Kritik - Michigan7 2026 WXYZ.docx", b"tidewater", "Michigan", "Michigan7"),
    ("Counterplans/Orchard Grants CP - MNDI 2026 JKT.docx", b"orchard", "Michigan", "MNDI"),
    ("Affirmatives/Ferry Aff - Michigan 2026 QRSV.docx", b"ferry", "Michigan", "Michigan"),
]  # fmt: skip


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(coroutine)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AnswersOnlyWhetherHeld:
    """The local blob store, answering `exists` and refusing to read, fetch or write a file's bytes."""

    def __init__(self, inner: FsSnapshotStore) -> None:
        self._inner = inner
        self.asked: list[str] = []

    async def exists(self, key: str) -> bool:
        self.asked.append(key)
        return await self._inner.exists(key)

    async def put(self, data: bytes) -> str:
        raise AssertionError("refiling wrote a blob")

    async def get(self, key: str) -> bytes:
        raise AssertionError("refiling read or fetched a file's bytes")


class StoredUnderTheMergedTable:
    """A data directory whose release went in when Michigan was one camp."""

    def __init__(self, root: Path) -> None:
        self.data_dir = root / "data"
        self.caselists = SqliteCaselistRepository(SqliteDatabase.open(self.data_dir))
        self.blobs = FsSnapshotStore(self.data_dir)
        suppression = RecordedSuppressionList(InMemoryAppendOnlyRecord("suppression list"))
        entries: list[ArchiveEntry] = [
            ArchiveMember(path=path, sha256=digest(body), byte_size=len(body), data=body)
            for path, body, _, _ in RELEASE
        ]
        imported = run(
            OpenEvImportService(
                caselists=self.caselists, blobs=self.blobs, suppression=suppression
            ).import_release(
                sorted(entries, key=lambda entry: entry.path),
                year=YEAR,
                event=EVENT,
                imported_on=IMPORTED_ON,
                archive_sha256="a" * 64,
                aliases=MERGED,
            )
        )
        self.recorded = imported.manifest_lines
        self.guarded = AnswersOnlyWhetherHeld(self.blobs)
        self.service = OpenEvImportService(
            caselists=self.caselists, blobs=self.guarded, suppression=suppression
        )

    def refile(self, **options: Any) -> Any:
        return run(
            self.service.reimport_metadata(
                year=YEAR, event=EVENT, recorded_manifest=self.recorded, aliases=PACKAGED, **options
            )
        )

    def stored_camps(self) -> dict[str, str]:
        """Each file's stored camp, by its path."""
        found: dict[str, str] = {}
        for path, body, _, _ in RELEASE:
            (record,) = run(
                self.caselists.list_camp_files(source_sha256=digest(body), year=YEAR, event=EVENT)
            ).items
            found[path] = record.camp
        return found

    def blob_tree(self) -> dict[str, str]:
        root = self.data_dir / BLOB_DIRECTORY
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


@pytest.fixture
def stored(tmp_path: Path) -> StoredUnderTheMergedTable:
    return StoredUnderTheMergedTable(tmp_path)


def test_the_files_start_filed_as_one_merged_michigan(stored: StoredUnderTheMergedTable) -> None:
    assert stored.stored_camps() == {path: before for path, _, before, _ in RELEASE}


def test_refiling_files_each_stored_file_under_its_own_camp_and_leaves_a_bare_michigan(
    stored: StoredUnderTheMergedTable,
) -> None:
    report = stored.refile()

    assert stored.stored_camps() == {path: after for path, _, _, after in RELEASE}
    assert dict(report.camps_before) == {"Michigan": 4}
    assert dict(report.camps_after) == {"MNDI": 1, "Michigan": 1, "Michigan Classic": 1, "Michigan7": 1}
    assert report.camp_files_updated == 3


def test_refiling_rewrites_each_manifest_rows_camp(stored: StoredUnderTheMergedTable) -> None:
    """The manifest's camp is what the next parse gives the occurrence rows."""
    report = stored.refile()

    rows = {row["path"]: row for row in map(json.loads, report.manifest_lines) if row["kind"] == "member"}
    assert {path: rows[path]["camp"] for path, _, _, _ in RELEASE} == {
        path: after for path, _, _, after in RELEASE
    }


def test_refiling_reads_no_file_and_writes_no_blob(stored: StoredUnderTheMergedTable) -> None:
    tree = stored.blob_tree()

    report = stored.refile()

    assert stored.blob_tree() == tree
    assert sorted(stored.guarded.asked) == sorted(digest(body) for _, body, _, _ in RELEASE)
    assert report.blobs_missing == 0


def test_refiling_a_file_not_held_here_reports_it_and_fetches_nothing(
    stored: StoredUnderTheMergedTable,
) -> None:
    """A file this machine no longer holds is still refiled from its recorded name, and only counted."""
    ferry = next(digest(body) for path, body, _, _ in RELEASE if path.startswith("Affirmatives/"))
    lantern = next(digest(body) for path, body, _, _ in RELEASE if path.startswith("Disadvantages/"))
    for gone in (stored.data_dir / BLOB_DIRECTORY).rglob(f"{lantern}*"):
        gone.unlink()

    report = stored.refile()

    assert report.blobs_missing == 1
    assert stored.stored_camps()["Disadvantages/Lantern DA - Michigan Classic 2026 PQR.docx"] == (
        "Michigan Classic"
    )
    assert not list((stored.data_dir / BLOB_DIRECTORY).rglob(f"{lantern}*"))
    assert ferry in stored.guarded.asked


def test_a_dry_run_refiles_nothing(stored: StoredUnderTheMergedTable) -> None:
    report = stored.refile(dry_run=True)

    assert report.camp_files_updated == 3
    assert stored.stored_camps() == {path: before for path, _, before, _ in RELEASE}

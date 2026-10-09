"""A fictional caselist whose documents hold cards, for the parse pipeline (`v1-e31-t06`).

The E30 synthetic archives (`tests/fixtures/caselist/`) are two plain paragraphs per file, which
the parser reads as documents with no cards. The parse pipeline needs cards to put in an
occurrence table, so this fixture files the `v1-e31-t03` structural fixtures under fictional
caselist paths instead. Their cards are known without running anything: each fixture's
`<name>.expected.json` was written by hand when the parser was built.

Nothing here is real (`docs/policies/caselist-data-use.md`): the schools, team codes and
tournaments are the E30 fixture's invented ones, and the documents are synthetic.

## The three weekly archives

`testcl26-0901`, `-0908` and `-0915`, cumulative, imported in order by the real importer:

| Body | Format | Cards | First week | Disclosures |
|---|---|---|---|---|
| `verbatim` | DOCX | 1 FULL | 09-01 | Maple Grove QX R1, its `(1)` copy and Riverbend MnPr R5 from 09-08 |
| `wiki` | DOCX | 1 ABBREVIATED, 1 CITE_ONLY | 09-01 | Cedar Hollow ZaLu R2 |
| `pdf` | PDF | unsupported | 09-01 | Riverbend MnPr quarters |
| `cardmirror` | DOCX | 1 FULL | 09-08 | Northgate BeCo R3 |
| `doc` | DOC | unsupported | 09-08 | Riverbend MnPr quarters |
| `broken` | DOCX | fails: `NOT_A_ZIP` | 09-08 | Cedar Hollow ZaLu R4 |
| `direct` | DOCX | 1 FULL | 09-15 | Westfield XY R6 |

The archives are cumulative: every file in a week is in the weeks after it. The `verbatim`,
`wiki`, `cardmirror` and `direct` bodies are the structural fixtures `team-verbatim-file`,
`wiki-converted-cite-entries`, `cardmirror-caselist-upload` and `pre-2026-direct-formatting`.

`verbatim` is the shared file: two teams disclose the same bytes, which is what a `--team` removal
withdraws without deleting. :data:`EXPECTED` is what the pipeline must report, worked out from this
table by hand; nothing in this module runs the parser.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Final

__all__ = [
    "BODIES",
    "CASELIST",
    "EXPECTED",
    "SHARED_TEAM",
    "STRUCTURAL",
    "WEEKS",
    "Week",
    "build_week_zips",
    "digest_of",
    "import_weeks",
]

CASELIST: Final = "testcl26"
STRUCTURAL: Final = Path(__file__).resolve().parents[1] / "debate_files" / "structural"

_PDF: Final = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\ntrailer<</Root 1 0 R>>\n%% parse world\n%%EOF\n"
)
_DOC: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 24 + b"parse world legacy doc" + b"\x00" * 64


def _structural(name: str) -> bytes:
    return (STRUCTURAL / f"{name}.docx").read_bytes()


BODIES: Final[dict[str, bytes]] = {
    "verbatim": _structural("team-verbatim-file"),
    "wiki": _structural("wiki-converted-cite-entries"),
    "pdf": _PDF,
    "cardmirror": _structural("cardmirror-caselist-upload"),
    "doc": _DOC,
    "broken": b"a file named .docx that is not a zip at all\n",
    "direct": _structural("pre-2026-direct-formatting"),
}


def digest_of(body: str) -> str:
    """The SHA-256 of one body, by its short name."""
    return hashlib.sha256(BODIES[body]).hexdigest()


_R1: Final = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
_R1_COPY: Final = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx"
_R5: Final = "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Round 5.docx"
_R2: Final = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-Harbor Classic-Round 2.docx"
_QUARTERS_PDF: Final = "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Quarters.pdf"
_R3: Final = "Northgate Prep/BeCo/Northgate Prep-BeCo-Neg-Ridgeline Round Robin-Round 3.docx"
_QUARTERS_DOC: Final = "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Neg-Seaside Cup-Quarters.doc"
_R4: Final = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Harbor Classic-Round 4.docx"
_R6: Final = "Westfield/XY/Westfield-XY-Neg-Bayview Open-Round 6.docx"

SHARED_TEAM: Final = f"{CASELIST}/Riverbend Academy/MnPr"
"""The team whose removal withdraws its copy of the shared `verbatim` file, and removes its PDF,
its `.doc` and nothing else."""


@dataclass(frozen=True, slots=True)
class Week:
    """One weekly archive: its date and `(path, body)` for every member."""

    snapshot: date
    members: tuple[tuple[str, str], ...]

    @property
    def archive_name(self) -> str:
        return f"{CASELIST}-{self.snapshot:%m%d}"


_WEEK_ONE: Final = ((_R1, "verbatim"), (_R2, "wiki"), (_QUARTERS_PDF, "pdf"))
_WEEK_TWO: Final = (
    *_WEEK_ONE,
    (_R1_COPY, "verbatim"),
    (_R5, "verbatim"),
    (_R3, "cardmirror"),
    (_QUARTERS_DOC, "doc"),
    (_R4, "broken"),
)

WEEKS: Final = (
    Week(date(2026, 9, 1), _WEEK_ONE),
    Week(date(2026, 9, 8), _WEEK_TWO),
    Week(date(2026, 9, 15), (*_WEEK_TWO, (_R6, "direct"))),
)

_ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
_LIMIT: Final = 64 * 1024 * 1024


async def import_weeks(data_dir: Path, zips_dir: Path, *, through: date, after: date | None = None) -> None:
    """Import the weeks after `after` and up to `through` into `data_dir` with the real importer.

    Writes each week's manifest where `caselist import` does, as `caselist import` does. The
    importer is set-up here, not the thing under test.
    """
    from debate_core.application.caselist.import_service import CaselistImportService
    from debate_core.application.caselist.manifest import manifest_key, write_manifest
    from debate_core.domain.caselist import Event
    from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
    from debate_core.integrations.local.archive_reader import archive_digest, read_archive
    from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
    from debate_core.testing.fakes import empty_suppression_list

    service = CaselistImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        suppression=empty_suppression_list(),
    )
    objects = FsEvidenceObjectStore(data_dir)
    zips = build_week_zips(zips_dir)
    for week in WEEKS:
        if week.snapshot > through:
            break
        if after is not None and week.snapshot <= after:
            continue
        report = await service.import_archive(
            read_archive(zips[week.snapshot], max_archive_bytes=_LIMIT, max_unpacked_bytes=_LIMIT),
            caselist=CASELIST,
            snapshot=week.snapshot,
            event=Event("LD"),
            archive_sha256=archive_digest(zips[week.snapshot]),
        )
        write_manifest(report, objects.path_for(manifest_key(CASELIST, week.snapshot)))


def build_week_zips(directory: Path) -> dict[date, Path]:
    """Write the three archives as deterministic zips into `directory`; return them by snapshot."""
    directory.mkdir(parents=True, exist_ok=True)
    built: dict[date, Path] = {}
    for week in WEEKS:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, body in sorted(week.members):
                info = zipfile.ZipInfo(f"{week.archive_name}/{path}", date_time=_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, BODIES[body])
        target = directory / f"{week.archive_name}.zip"
        target.write_bytes(buffer.getvalue())
        built[week.snapshot] = target
    return built


EXPECTED: Final[dict[str, dict[str, Any]]] = {
    "after_0908": {
        "sources": 6,
        "parsed": 3,
        "cards": 4,
        "unsupported": {"DOC": 1, "PDF": 1},
        "failed": {"NOT_A_ZIP": 1},
        "failure_rate": 0.25,
        # verbatim: 1 card x (09-01 R1; 09-08 R1, R1 (1), R5); wiki: 2 x (09-01, 09-08); cardmirror: 1
        "occurrences": 4 + 4 + 1,
    },
    "after_0915": {
        "sources": 7,
        "parsed_this_run": 1,
        "skipped_this_run": 6,
        "cards": 5,
        # verbatim 1 x 7 disclosures; wiki 2 x 3; cardmirror 1 x 2; direct 1 x 1
        "occurrences": 7 + 6 + 2 + 1,
    },
    "after_shared_team_removed": {
        # The PDF and the .doc go; verbatim stays for Maple Grove QX without Riverbend's 2 disclosures.
        "sources": 5,
        "unsupported": 0,
        "occurrences": (7 - 2) + 6 + 2 + 1,
    },
}
"""What the pipeline reports over :data:`WEEKS`, derived by hand from the table in the docstring.

`after_0908`: 09-01 and 09-08 imported, one run. Six distinct sources; three parse (verbatim 1 card,
wiki 2, cardmirror 1); the PDF and the `.doc` are unsupported; the broken file fails. The failure
rate is one failure over the four sources tried that are not an unsupported format.

`after_0915`: 09-15 imported, a second run. Only `direct` is new.
"""

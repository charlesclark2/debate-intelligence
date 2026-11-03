"""A `.cmir` file is imported as CMIR, and counted unsupported under its own format (`v1-e30-t26`).

`v1-e31-t15` added `SourceFormat.CMIR` for CardMirror's native format, a gzip stream holding a JSON
document, and the parser names one it finds under a `.docx` name. A file *named* `.cmir` still
reached the manifest as `OTHER`, because the importer maps a name to a format by its extension and
had no entry for `.cmir`. From this task on the manifest records it as `CMIR`, and the parse run,
which reads the format from the manifest, counts it unsupported under `CMIR`.

One synthetic weekly archive is imported by the real importer: a team's verbatim file and a
CardMirror `.cmir` of another round. Every expected value below is written by hand from those two
members (working agreement 6).
"""

from __future__ import annotations

import gzip
import json
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import STRUCTURAL

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.path_parser import source_format_for
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.domain.caselist import Event, SourceFormat
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.caselist import build_fake_caselist_repository
from debate_core.testing.fakes.suppression import empty_suppression_list

CASELIST: Final = "testcl26"
SNAPSHOT: Final = date(2026, 10, 5)
VERBATIM_PATH: Final = "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Round 1.docx"
CMIR_PATH: Final = "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Neg-Seaside Cup-Round 2.cmir"
CMIR_BODY: Final = gzip.compress(b'{"format":"cardmirror-native","doc":{"type":"doc"}}', mtime=0)
_LIMIT: Final = 64 * 1024 * 1024


def build_cmir_week(directory: Path) -> Path:
    """One weekly archive: a verbatim `.docx` and a CardMirror `.cmir`, as a deterministic zip."""
    members = {VERBATIM_PATH: (STRUCTURAL / "team-verbatim-file.docx").read_bytes(), CMIR_PATH: CMIR_BODY}
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, body in sorted(members.items()):
            info = zipfile.ZipInfo(f"{CASELIST}-weekly/{path}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{CASELIST}-weekly.zip"
    target.write_bytes(buffer.getvalue())
    return target


async def import_cmir_week(data_dir: Path, zips_dir: Path) -> Path:
    """Import the week into `data_dir` as `caselist import` does, and return its manifest's path."""
    archive = build_cmir_week(zips_dir)
    report = await CaselistImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        suppression=empty_suppression_list(),
    ).import_archive(
        read_archive(archive, max_archive_bytes=_LIMIT, max_unpacked_bytes=_LIMIT),
        caselist=CASELIST,
        snapshot=SNAPSHOT,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    return write_manifest(report, FsEvidenceObjectStore(data_dir).path_for(manifest_key(CASELIST, SNAPSHOT)))


def member_rows(manifest: Path) -> dict[str, dict[str, Any]]:
    rows = (json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines())
    return {row["path"]: row for row in rows if row["kind"] == "member"}


@pytest.mark.parametrize("name", ["round-2.cmir", "ROUND-2.CMIR", "Round 2 (1).Cmir"])
def test_a_cmir_name_is_the_cmir_format(name: str) -> None:
    assert source_format_for(name) is SourceFormat.CMIR


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("round-2.docx", SourceFormat.DOCX),
        ("round-2.doc", SourceFormat.DOC),
        ("round-2.pdf", SourceFormat.PDF),
        ("round-2.cmir.txt", SourceFormat.OTHER),
        ("round-2.cmirx", SourceFormat.OTHER),
        ("cmir", SourceFormat.OTHER),
    ],
)
def test_the_other_names_keep_their_formats(name: str, expected: SourceFormat) -> None:
    assert source_format_for(name) is expected


@pytest.mark.anyio
async def test_a_cmir_file_in_an_archive_is_recorded_as_cmir(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    manifest = await import_cmir_week(data_dir, tmp_path / "zips")

    rows = member_rows(manifest)
    assert {path: (row["classification"], row["format"]) for path, row in rows.items()} == {
        VERBATIM_PATH: ("NEW", "DOCX"),
        CMIR_PATH: ("NEW", "CMIR"),
    }
    sources = await SqliteCaselistRepository(SqliteDatabase.open(data_dir)).list_sources(limit=10)
    assert sorted(source.source_format for source in sources.items) == [SourceFormat.CMIR, SourceFormat.DOCX]


@pytest.mark.anyio
async def test_a_cmir_file_is_counted_unsupported_under_its_own_format(tmp_path: Path) -> None:
    """From the manifest on: the parse run reads the format the import recorded."""
    data_dir = tmp_path / "evidence"
    manifest = await import_cmir_week(data_dir, tmp_path / "zips")
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    service = CaselistParseService(
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        store=LocalParsedStore(data_dir),
        parser=DebateDocxParser(),
        runner=InProcessParseRunner(),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        card_placer=CaselistCardStatsService(build_fake_caselist_repository()).placer,
        failure_rate_threshold=0.5,
        failure_rate_minimum_sources=1,
    )

    report = await service.run(await service.plan(CASELIST))

    assert (report.parsed, report.unsupported, report.failed) == (1, {"CMIR": 1}, {})
    failures_file = LocalParsedStore(data_dir).root / CASELIST / DOCX_PARSER_VERSION / "failures.jsonl"
    failures = [json.loads(line) for line in failures_file.read_text(encoding="utf-8").splitlines()]
    cmir_digest = member_rows(manifest)[CMIR_PATH]["sha256"]
    assert [
        (row["source_sha256"], row["outcome"], row["reason"], row["source_format"]) for row in failures
    ] == [(cmir_digest, "UNSUPPORTED", "UNSUPPORTED_FORMAT", "CMIR")]

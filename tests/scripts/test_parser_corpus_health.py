"""`scripts/parser_corpus_health.py`, on an invented corpus built in a temporary directory.

The real run is operator-only. This checks the counting, the deduplication across snapshots, and
that no name, path or text reaches the report. The directory and file names below are fictional,
shaped like a caselist's `<School>/<TeamCode>/<file>` so the test can prove they do not leak.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import parser_corpus_health as health_script  # noqa: E402

TAG = "Moratoria collapse the reserve margin"


def _card_file() -> bytes:
    return build_docx(
        paragraph_xml(run_xml(TAG), style="Heading4")
        + paragraph_xml(
            run_xml("Okonkwo 26", character_style="Style13ptBold") + run_xml(", Fictional Review")
        )
        + paragraph_xml(
            run_xml(
                "Grid operators warn of shortfalls.", character_style="StyleUnderline", underline="single"
            )
        )
    )


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """Two snapshots sharing one file, a broken .docx, a PDF and a camp file."""
    first = tmp_path / "hsld26-0901" / "Maple Grove" / "QX"
    second = tmp_path / "hsld26-0908" / "Maple Grove" / "QX"
    for folder in (first, second):
        folder.mkdir(parents=True)
        (folder / "Maple-Grove-QX-Aff-Round1.docx").write_bytes(_card_file())
    (second / "Maple-Grove-QX-Neg-Round2.docx").write_bytes(b"not a zip at all")
    (second / "Maple-Grove-QX-Neg-Round3.pdf").write_bytes(b"%PDF-1.4 invented")
    camp = tmp_path / "camp" / "Invented Institute"
    camp.mkdir(parents=True)
    (camp / "Invented-Institute-Core-Files.docx").write_bytes(
        build_docx(paragraph_xml(run_xml("Invented camp file with no cards")))
    )
    return tmp_path


def _measure(corpus: Path) -> health_script.CorpusHealth:
    return health_script.measure(
        [
            ("caselist", corpus / "hsld26-0901"),
            ("caselist", corpus / "hsld26-0908"),
            ("camp", corpus / "camp"),
        ]
    )


def test_counts_files_seen_and_distinct_and_parses_each_docx_once(corpus: Path) -> None:
    caselist = _measure(corpus).categories["caselist"]
    assert caselist.files_seen == 4  # the shared file twice, the broken .docx, the PDF
    assert sum(caselist.formats.values()) == 3
    assert caselist.formats["pdf"] == 1
    assert caselist.docx == 2
    assert caselist.parsed == 1
    assert caselist.success_rate == 0.5


def test_a_refusal_is_counted_by_its_reason(corpus: Path) -> None:
    health = _measure(corpus)
    assert health.total.failures == {"refused: NOT_A_ZIP": 1}


def test_what_came_out_is_counted(corpus: Path) -> None:
    health = _measure(corpus)
    assert health.categories["caselist"].completeness == {"FULL": 1}
    assert health.categories["camp"].files_without_cards == 1


def test_a_parser_crash_is_a_count_not_a_stopped_run(corpus: Path) -> None:
    class ExplodingParser(health_script.DebateDocxParser):
        def parse(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise KeyError("Maple Grove QX — an exception message the report must never carry")

    health = health_script.measure([("camp", corpus / "camp")], parser=ExplodingParser())
    assert health.total.failures == {"parser exception: KeyError": 1}
    report = health_script.render_report(health, run_on=date(2026, 9, 21), corpus_description="invented")
    assert "Maple Grove" not in report


def test_the_report_carries_counts_and_no_names_paths_or_text(corpus: Path) -> None:
    report = health_script.render_report(
        _measure(corpus), run_on=date(2026, 9, 21), corpus_description="an invented corpus"
    )
    assert "Parse success rate" in report
    assert "parse success rate" in report  # the node's contentMatch
    assert "refused: NOT_A_ZIP" in report
    for leak in (
        "Maple",
        "Grove",
        "QX",
        "Round1",
        "Invented-Institute",
        "hsld26-0901",
        str(corpus),
        TAG,
        "Okonkwo",
    ):
        assert leak not in report, leak


def test_the_exit_status_follows_the_target(corpus: Path, tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    failing = health_script.main(["--input", f"caselist={corpus / 'hsld26-0908'}", "--output", str(output)])
    assert failing == 1  # 1 of 2 parsed
    passing = health_script.main(["--input", f"camp={corpus / 'camp'}", "--output", str(output)])
    assert passing == 0
    assert output.read_text(encoding="utf-8").startswith("# Parser corpus health")

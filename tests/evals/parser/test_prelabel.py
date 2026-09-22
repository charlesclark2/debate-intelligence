"""`scripts/prelabel_docx.py`: pre-labels are seeds, and a worksheet only becomes labels when a
person has checked every row without touching the text."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest
from tests.evals.parser.corpus import parse_evaluation_file
from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    Category,
    DebateFormat,
    LabelStatus,
    ManifestEntry,
    ReviewerRole,
    TemplateFamily,
    validate_label_file,
)
from tests.evals.parser.synthetic import CLOSING, OPENING, UNDERLINED, build_synthetic_file

from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.docx_parser import DebateDocxParser

sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import prelabel_docx as prelabel  # noqa: E402


@pytest.fixture(scope="module")
def document() -> ParsedDocument:
    synthetic = build_synthetic_file()
    entry = ManifestEntry(
        sha256=synthetic.sha256,
        category=Category.TEAM,
        season="2025-26",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
    )
    return parse_evaluation_file(DebateDocxParser(), entry, synthetic.content)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _checked(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{**row, "checked": "y"} for row in rows]


def test_prelabels_are_marked_prelabeled_and_hold_the_parser_version(document: ParsedDocument) -> None:
    labels = prelabel.prelabel_document(document)
    assert labels.header.status is LabelStatus.PRELABELED
    assert labels.header.corrected_by is None
    assert labels.header.prelabel_parser_version == document.parser_version
    assert validate_label_file(labels, check_cards=False) == []


def test_prelabel_card_membership_follows_each_card_range(document: ParsedDocument) -> None:
    """Paragraph 6 is blank and sits between the cards; nothing in a card range but card units joins it."""
    labels = prelabel.prelabel_document(document)
    for paragraph in labels.paragraphs:
        if paragraph.card is not None:
            assert paragraph.unit in {StructuralUnit.TAG, StructuralUnit.CITE, StructuralUnit.EVIDENCE}


def test_the_span_sample_is_a_stable_fifth_of_paragraphs() -> None:
    sampled = sum(prelabel.is_sampled("c" * 64, index) for index in range(10_000))
    assert 1_850 < sampled < 2_150
    assert [prelabel.is_sampled("c" * 64, i) for i in range(50)] == [
        prelabel.is_sampled("c" * 64, i) for i in range(50)
    ]


# --------------------------------------------------------------------------------------------
# Span markup
# --------------------------------------------------------------------------------------------


def test_markup_round_trips() -> None:
    text = OPENING + UNDERLINED + CLOSING
    ranges = ((len(OPENING), len(OPENING) + len(UNDERLINED)),)
    markup = prelabel.render_markup(text, ranges)
    assert markup == f"{OPENING}⟦{UNDERLINED}⟧{CLOSING}"
    assert prelabel.parse_markup(markup, text, row=2, column="underline") == ranges


def test_markup_that_changes_the_text_is_refused() -> None:
    with pytest.raises(prelabel.WorksheetError, match="text under the markup was edited"):
        prelabel.parse_markup("⟦Grid⟧ operator", "Grid operators", row=2, column="underline")


@pytest.mark.parametrize("markup", ["⟦a⟦b⟧⟧", "a⟧", "⟦ab"])
def test_unbalanced_markup_is_refused(markup: str) -> None:
    with pytest.raises(prelabel.WorksheetError):
        prelabel.parse_markup(markup, "ab", row=2, column="highlight")


# --------------------------------------------------------------------------------------------
# Worksheets
# --------------------------------------------------------------------------------------------


def test_a_worksheet_is_never_written_inside_the_repository(document: ParsedDocument) -> None:
    labels = prelabel.prelabel_document(document)
    with pytest.raises(prelabel.WorksheetError, match="outside the repository"):
        prelabel.write_worksheet(labels, document, REPOSITORY_ROOT / "build" / "worksheets")


def test_a_checked_corrected_worksheet_imports_as_corrected(document: ParsedDocument, tmp_path: Path) -> None:
    labels = prelabel.prelabel_document(document)
    rows = _checked(_rows(prelabel.write_worksheet(labels, document, tmp_path)))
    assert [row["text"] for row in rows] == [section.text for section in document.sections]
    rows[7] = {**rows[7], "unit": "TAG" if rows[7]["unit"] != "TAG" else "ANALYTIC"}

    corrected = prelabel.import_worksheet(
        rows, prelabels=labels, texts=[s.text for s in document.sections], corrected_by=ReviewerRole.COACH
    )
    assert corrected.header.status is LabelStatus.CORRECTED
    assert corrected.header.corrected_by is ReviewerRole.COACH
    assert corrected.header.rows_changed_from_prelabel == 1
    assert [s.index for s in corrected.spans] == [s.index for s in labels.spans]


def test_an_unchecked_row_is_refused(document: ParsedDocument, tmp_path: Path) -> None:
    labels = prelabel.prelabel_document(document)
    rows = _checked(_rows(prelabel.write_worksheet(labels, document, tmp_path)))
    rows[4] = {**rows[4], "checked": ""}
    with pytest.raises(prelabel.WorksheetError, match="row 6: not marked checked"):
        prelabel.import_worksheet(
            rows,
            prelabels=labels,
            texts=[s.text for s in document.sections],
            corrected_by=ReviewerRole.OPERATOR,
        )


def test_an_uncorrected_worksheet_nobody_checked_is_refused(document: ParsedDocument, tmp_path: Path) -> None:
    """The failure this whole evaluation exists to prevent: pre-labels passed through untouched."""
    labels = prelabel.prelabel_document(document)
    rows = _rows(prelabel.write_worksheet(labels, document, tmp_path))
    with pytest.raises(prelabel.WorksheetError, match=f"{len(rows)} problem"):
        prelabel.import_worksheet(
            rows,
            prelabels=labels,
            texts=[s.text for s in document.sections],
            corrected_by=ReviewerRole.OPERATOR,
        )


def test_edited_text_is_refused(document: ParsedDocument, tmp_path: Path) -> None:
    labels = prelabel.prelabel_document(document)
    rows = _checked(_rows(prelabel.write_worksheet(labels, document, tmp_path)))
    rows[3] = {**rows[3], "text": rows[3]["text"] + "!"}
    with pytest.raises(prelabel.WorksheetError, match="row 5: the text was edited"):
        prelabel.import_worksheet(
            rows,
            prelabels=labels,
            texts=[s.text for s in document.sections],
            corrected_by=ReviewerRole.OPERATOR,
        )


def test_reordered_or_dropped_rows_are_refused(document: ParsedDocument, tmp_path: Path) -> None:
    labels = prelabel.prelabel_document(document)
    rows = _checked(_rows(prelabel.write_worksheet(labels, document, tmp_path)))
    with pytest.raises(prelabel.WorksheetError, match="rows"):
        prelabel.import_worksheet(
            rows[:-1],
            prelabels=labels,
            texts=[s.text for s in document.sections],
            corrected_by=ReviewerRole.COACH,
        )


def test_a_card_without_completeness_is_refused(document: ParsedDocument, tmp_path: Path) -> None:
    labels = prelabel.prelabel_document(document)
    rows = _checked(_rows(prelabel.write_worksheet(labels, document, tmp_path)))
    rows = [{**row, "completeness": ""} for row in rows]
    with pytest.raises(prelabel.WorksheetError, match="has no completeness"):
        prelabel.import_worksheet(
            rows, prelabels=labels, texts=[s.text for s in document.sections], corrected_by=ReviewerRole.COACH
        )

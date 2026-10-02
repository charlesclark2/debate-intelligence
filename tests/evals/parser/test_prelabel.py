"""`scripts/prelabel_docx.py`: pre-labels are seeds, and a worksheet only becomes labels when a
person has checked every row without touching the text."""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.evals.parser.corpus import parse_evaluation_file
from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    Category,
    DebateFormat,
    FileSamplingPlan,
    LabelStatus,
    Manifest,
    ManifestEntry,
    ReviewerRole,
    SamplingPlan,
    TemplateFamily,
    label_path_for,
    validate_label_file,
    write_label_file,
)
from tests.evals.parser.synthetic import (
    CLOSING,
    OPENING,
    TEST_DIGEST_KEY,
    UNDERLINED,
    build_synthetic_file,
)

from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.docx_parser import DebateDocxParser

sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import prelabel_docx as prelabel  # noqa: E402

PLAN_ID = "abcdef0123456789"


@pytest.fixture(scope="module")
def document() -> ParsedDocument:
    synthetic = build_synthetic_file()
    entry = ManifestEntry(
        digest=synthetic.digest,
        category=Category.TEAM,
        season="2025-26",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
    )
    return parse_evaluation_file(DebateDocxParser(), entry, synthetic.content)


@pytest.fixture(scope="module")
def whole_file(document: ParsedDocument) -> FileSamplingPlan:
    """The PR-subset shape: every paragraph labeled."""
    return FileSamplingPlan(
        digest=build_synthetic_file().digest,
        paragraphs=len(document.sections),
        blocks=((0, len(document.sections) - 1),),
        full=True,
    )


@pytest.fixture(scope="module")
def sampled(document: ParsedDocument) -> FileSamplingPlan:
    """The sampled shape: one block covering the first card and the analytic after it."""
    return FileSamplingPlan(
        digest=build_synthetic_file().digest,
        paragraphs=len(document.sections),
        blocks=((0, 7),),
    )


def _prelabel(document: ParsedDocument, plan: FileSamplingPlan):  # type: ignore[no-untyped-def]
    return prelabel.prelabel_document(document, plan, PLAN_ID, TEST_DIGEST_KEY)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _checked(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{**row, "checked": "y"} for row in rows]


def _worksheet(labels, document, out_dir, plan):  # type: ignore[no-untyped-def]
    return prelabel.write_worksheet(labels, document, out_dir, TEST_DIGEST_KEY, plan.digest)


def _import(rows, labels, document, corrected_by=ReviewerRole.OPERATOR):  # type: ignore[no-untyped-def]
    return prelabel.import_worksheet(
        rows,
        prelabels=labels,
        texts=[s.text for s in document.sections],
        corrected_by=corrected_by,
        key=TEST_DIGEST_KEY,
    )


def test_prelabels_are_marked_prelabeled_and_hold_the_parser_version(
    document: ParsedDocument, whole_file: FileSamplingPlan
) -> None:
    labels = _prelabel(document, whole_file)
    assert labels.header.status is LabelStatus.PRELABELED
    assert labels.header.corrected_by is None
    assert labels.header.prelabel_parser_version == document.parser_version
    assert validate_label_file(labels, check_cards=False) == []


def test_prelabel_card_membership_follows_each_card_range(
    document: ParsedDocument, whole_file: FileSamplingPlan
) -> None:
    """Paragraph 6 is blank and sits between the cards; nothing in a card range but card units joins it."""
    labels = _prelabel(document, whole_file)
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


def test_a_worksheet_is_never_written_inside_the_repository(
    document: ParsedDocument, whole_file: FileSamplingPlan
) -> None:
    labels = _prelabel(document, whole_file)
    with pytest.raises(prelabel.WorksheetError, match="outside the repository"):
        prelabel.write_worksheet(
            labels,
            document,
            REPOSITORY_ROOT / "build" / "worksheets",
            TEST_DIGEST_KEY,
            whole_file.digest,
        )


def test_a_checked_corrected_worksheet_imports_as_corrected(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, whole_file)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, whole_file)))
    assert [row["text"] for row in rows] == [section.text for section in document.sections]
    rows[7] = {**rows[7], "unit": "TAG" if rows[7]["unit"] != "TAG" else "ANALYTIC"}

    corrected = _import(rows, labels, document, ReviewerRole.COACH)
    assert corrected.header.status is LabelStatus.CORRECTED
    assert corrected.header.corrected_by is ReviewerRole.COACH
    assert corrected.header.rows_changed_from_prelabel == 1
    assert [s.index for s in corrected.spans] == [s.index for s in labels.spans]


def test_an_unchecked_row_is_refused(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, whole_file)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, whole_file)))
    rows[4] = {**rows[4], "checked": ""}
    with pytest.raises(prelabel.WorksheetError, match="row 6: not marked checked"):
        _import(rows, labels, document, ReviewerRole.OPERATOR)


def test_an_uncorrected_worksheet_nobody_checked_is_refused(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    """The failure this whole evaluation exists to prevent: pre-labels passed through untouched."""
    labels = _prelabel(document, whole_file)
    rows = _rows(_worksheet(labels, document, tmp_path, whole_file))
    with pytest.raises(prelabel.WorksheetError, match=f"{len(rows)} problem"):
        _import(rows, labels, document, ReviewerRole.OPERATOR)


def test_edited_text_is_refused(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, whole_file)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, whole_file)))
    rows[3] = {**rows[3], "text": rows[3]["text"] + "!"}
    with pytest.raises(prelabel.WorksheetError, match="row 5: the text was edited"):
        _import(rows, labels, document, ReviewerRole.OPERATOR)


def test_reordered_or_dropped_rows_are_refused(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, whole_file)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, whole_file)))
    with pytest.raises(prelabel.WorksheetError, match="rows"):
        _import(rows[:-1], labels, document, ReviewerRole.COACH)


def test_a_card_without_completeness_is_refused(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, whole_file)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, whole_file)))
    rows = [{**row, "completeness": ""} for row in rows]
    with pytest.raises(prelabel.WorksheetError, match="has no completeness"):
        _import(rows, labels, document, ReviewerRole.COACH)


# --------------------------------------------------------------------------------------------
# Sampling: only the planned rows, and only the cards that can be judged
# --------------------------------------------------------------------------------------------


def test_prelabels_cover_only_the_planned_block(document: ParsedDocument, sampled: FileSamplingPlan) -> None:
    labels = _prelabel(document, sampled)
    assert [p.index for p in labels.paragraphs] == list(range(8))
    assert labels.header.paragraph_count == len(document.sections)
    assert labels.header.blocks == ((0, 7),)
    assert labels.header.plan_id == PLAN_ID


def test_a_card_outside_the_block_is_not_prelabeled(
    document: ParsedDocument, sampled: FileSamplingPlan
) -> None:
    """The second card (8-10) lies outside block 0-7 entirely, so it gets no rows and no number."""
    labels = _prelabel(document, sampled)
    assert {p.card for p in labels.paragraphs if p.card is not None} == {0}
    assert [card.card for card in labels.cards] == [0]


def test_a_card_straddling_the_block_edge_is_left_unnumbered(document: ParsedDocument) -> None:
    """Block 0-4 cuts the first card (3-5) in half. Its rows are labeled; the card is not."""
    half = FileSamplingPlan(
        digest=build_synthetic_file().digest, paragraphs=len(document.sections), blocks=((0, 4),)
    )
    labels = _prelabel(document, half)
    assert [p.index for p in labels.paragraphs] == [0, 1, 2, 3, 4]
    assert all(p.card is None for p in labels.paragraphs)
    assert labels.cards == ()


def test_a_sampled_worksheet_has_one_row_per_planned_paragraph(
    document: ParsedDocument, sampled: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, sampled)
    rows = _rows(_worksheet(labels, document, tmp_path, sampled))
    assert [int(row["index"]) for row in rows] == list(range(8))
    corrected = _import(_checked(rows), labels, document)
    assert corrected.header.blocks == ((0, 7),)
    assert corrected.header.paragraph_count == len(document.sections)
    assert len(corrected.paragraphs) == 8


def test_a_sampled_worksheet_missing_a_row_is_refused(
    document: ParsedDocument, sampled: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, sampled)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, sampled)))
    with pytest.raises(prelabel.WorksheetError, match="the sampling plan labels 8 paragraphs"):
        _import(rows[1:], labels, document)


def test_a_sampled_worksheet_whose_rows_moved_is_refused(
    document: ParsedDocument, sampled: FileSamplingPlan, tmp_path: Path
) -> None:
    """Row order is the plan's order, so a row in the wrong place is caught by the index it carries."""
    labels = _prelabel(document, sampled)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, sampled)))
    shuffled = [rows[1], rows[0], *rows[2:]]
    with pytest.raises(prelabel.WorksheetError, match="rows were reordered or removed"):
        _import(shuffled, labels, document)


# --------------------------------------------------------------------------------------------
# The spreadsheet round trip (v1-e31-t07): each failure seen on 2026-10-02, on invented text
# --------------------------------------------------------------------------------------------
#
# The worksheet below is the synthetic file's, written from its hand-written labels: spans are
# sampled on paragraphs 3, 5 and 10. A paragraph's row is its index plus 2, since the header is
# row 1 in Numbers. Paragraph 5 is the first card's body: OPENING, then UNDERLINED (underlined and
# highlighted), then CLOSING.

EVIDENCE_ROW = 7
CITE_ROW = 6


@pytest.fixture(scope="module")
def prelabels():  # type: ignore[no-untyped-def]
    return build_synthetic_file(LabelStatus.PRELABELED).labels


def _row_of(rows: list[dict[str, str]], number: int) -> dict[str, str]:
    return rows[number - 2]


def _refusal(rows, prelabels, document) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(prelabel.WorksheetError) as refused:
        _import(rows, prelabels, document)
    return str(refused.value)


def test_an_emptied_sampled_span_cell_is_named_as_empty_not_as_edited_text(
    document: ParsedDocument, prelabels, tmp_path: Path
) -> None:
    """2026-10-02: cells emptied to mean "nothing underlined" were refused as edited text."""
    rows = _checked(_rows(_worksheet(prelabels, document, tmp_path, prelabels.header)))
    _row_of(rows, EVIDENCE_ROW)["underline"] = ""

    message = _refusal(rows, prelabels, document)

    assert (
        f"row {EVIDENCE_ROW}, underline: empty: a row with nothing marked keeps its text with no marks"
        in (message)
    )
    assert "edited" not in message


def test_text_the_spreadsheet_changed_is_named_by_the_characters_that_differ(
    document: ParsedDocument, prelabels, tmp_path: Path
) -> None:
    """2026-10-02: Numbers changed whitespace, a non-breaking space and line breaks in six rows."""
    rows = _checked(_rows(_worksheet(prelabels, document, tmp_path, prelabels.header)))
    evidence = _row_of(rows, EVIDENCE_ROW)
    evidence["text"] = evidence["text"].replace("warn that ", "warn that ")
    cite = _row_of(rows, CITE_ROW)
    cite["text"] = cite["text"].replace(", Grid Analyst", ",\nGrid Analyst")

    message = _refusal(rows, prelabels, document)

    assert f"row {EVIDENCE_ROW}, text: " in message
    assert "a non-breaking space where the document has a space" in message
    assert f"row {CITE_ROW}, text: " in message
    assert "a line break where the document has a space" in message
    assert "check --repair" in message
    for text in (OPENING + UNDERLINED + CLOSING, "Okonkwo 26, Grid Analyst, Fictional Energy Review"):
        assert text not in message.replace(" ", " ").replace("\n", " ")


def test_every_problem_in_a_row_is_reported_not_only_the_first(
    document: ParsedDocument, prelabels, tmp_path: Path
) -> None:
    """2026-10-02: each fix uncovered the next problem in the same row, one run at a time."""
    rows = _checked(_rows(_worksheet(prelabels, document, tmp_path, prelabels.header)))
    evidence = _row_of(rows, EVIDENCE_ROW)
    evidence.update(checked="", unit="EVIDENSE", underline="", highlight=f"{prelabel.MARK_OPEN}{OPENING}")

    message = _refusal(rows, prelabels, document)

    for column in ("checked", "unit", "underline", "highlight"):
        assert f"row {EVIDENCE_ROW}, {column}: " in message, column


def test_an_untouched_worksheet_is_named_as_the_original_not_as_every_row_unchecked(
    document: ParsedDocument, prelabels, tmp_path: Path
) -> None:
    """2026-10-02: Cmd+S saved a .numbers file, the CSV stayed as written, and import listed 31 rows."""
    rows = _rows(_worksheet(prelabels, document, tmp_path, prelabels.header))

    message = _refusal(rows, prelabels, document)

    assert "looks like the worksheet as it was written" in message
    assert "not marked checked" not in message and "checked: empty" not in message


# --------------------------------------------------------------------------------------------
# The command line, on an invented evaluation in a scratch directory
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Evaluation:
    options: list[str]
    digest: str
    labels: Path
    worksheets: Path

    @property
    def prefix(self) -> str:
        return self.digest[:16]

    @property
    def csv(self) -> Path:
        return self.worksheets / f"{self.prefix}.csv"

    @property
    def numbers(self) -> Path:
        return self.worksheets / f"{self.prefix}.numbers"

    @property
    def label_file(self) -> Path:
        return label_path_for(self.digest, self.labels)

    def run(self, *arguments: str) -> int:
        return prelabel.main([*self.options, *arguments])


@pytest.fixture
def evaluation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Evaluation:
    """The synthetic file as a one-file evaluation: key, path map, manifest, plan and pre-labels."""
    synthetic = build_synthetic_file(LabelStatus.PRELABELED)
    private = tmp_path / "private"
    private.mkdir()
    (private / "digest.key").write_text(TEST_DIGEST_KEY.hex() + "\n", encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(private / "digest.key"))
    docx = tmp_path / "corpus" / "invented.docx"
    docx.parent.mkdir()
    docx.write_bytes(synthetic.content)
    (private / "paths.json").write_text(json.dumps({synthetic.digest: str(docx)}), encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_PATHS", str(private / "paths.json"))

    directory = tmp_path / "eval"
    labels = directory / "labels"
    entry = ManifestEntry(
        digest=synthetic.digest,
        category=Category.TEAM,
        season="2025-26",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
        pr_subset=True,
    )
    paragraphs = synthetic.labels.header.paragraph_count
    plan = SamplingPlan(
        plan_id=PLAN_ID,
        generated_on="2026-10-02",
        parser_version="test",
        files=(
            FileSamplingPlan(
                digest=synthetic.digest, paragraphs=paragraphs, blocks=((0, paragraphs - 1),), full=True
            ),
        ),
    )
    labels.mkdir(parents=True)
    (directory / "manifest.json").write_text(Manifest(entries=(entry,)).model_dump_json(), encoding="utf-8")
    (directory / "sampling-plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    write_label_file(synthetic.labels, labels, check_cards=False)
    options = [
        "--manifest",
        str(directory / "manifest.json"),
        "--plan",
        str(directory / "sampling-plan.json"),
        "--labels-dir",
        str(labels),
    ]
    made = _Evaluation(
        options=options, digest=synthetic.digest, labels=labels, worksheets=tmp_path / "worksheets"
    )
    assert made.run("worksheet", made.prefix, "--out-dir", str(made.worksheets)) == 0
    return made


def _write_csv(path: Path, rows: list[dict[str, str]], *, above_header: list[str] = ()) -> Path:  # type: ignore[assignment]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for line in above_header:
            writer.writerow([line])
        writer.writerow(prelabel.WORKSHEET_COLUMNS)
        writer.writerows([[row[column] for column in prelabel.WORKSHEET_COLUMNS] for row in rows])
    return path


def _write_numbers(path: Path, rows: list[dict[str, str]]) -> Path:
    """A .numbers file holding these rows, the way Numbers stores them: indices and cards as numbers."""
    from numbers_parser import Document

    columns = prelabel.WORKSHEET_COLUMNS
    document = Document(num_header_rows=1, num_header_cols=0, num_rows=len(rows) + 1, num_cols=len(columns))
    table = document.sheets[0].tables[0]
    for column, name in enumerate(columns):
        table.write(0, column, name)
    for number, row in enumerate(rows, start=1):
        for column, name in enumerate(columns):
            value = row[name]
            if value:
                table.write(number, column, int(value) if value.isdigit() else value)
    document.save(str(path))
    return path


def _age(path: Path, seconds: int) -> None:
    """Make a file look `seconds` older than now."""
    stamp = path.stat().st_mtime - seconds
    os.utime(path, (stamp, stamp))


def test_a_table_name_line_above_the_header_is_named(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    """2026-10-02: Numbers' export option "Include table names" puts a line above the header."""
    rows = _checked(_rows(evaluation.csv))
    _write_csv(evaluation.csv, rows, above_header=["Table 1"])
    before = evaluation.label_file.read_bytes()

    code = evaluation.run(
        "import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"
    )

    output = capsys.readouterr()
    assert code == 1
    assert "Include table names" in output.out + output.err
    assert evaluation.label_file.read_bytes() == before


def test_a_csv_older_than_the_numbers_file_beside_it_is_refused(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    """2026-10-02: Cmd+S wrote <digest>.numbers and the import read the untouched CSV, twice."""
    _write_numbers(evaluation.numbers, _checked(_rows(evaluation.csv)))
    _age(evaluation.csv, 60)
    before = evaluation.label_file.read_bytes()
    capsys.readouterr()

    code = evaluation.run(
        "import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"
    )

    output = capsys.readouterr()
    printed = output.out + output.err
    assert code == 1
    assert f"{evaluation.prefix}.csv is older than {evaluation.prefix}.numbers" in printed
    assert "not marked checked" not in printed and "checked: empty" not in printed
    assert evaluation.label_file.read_bytes() == before


def test_the_untouched_original_points_at_the_numbers_file_beside_it(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    """Even when the .numbers file is the older one, an untouched CSV names it as where the work may be."""
    _write_numbers(evaluation.numbers, _rows(evaluation.csv))
    _age(evaluation.numbers, 60)
    capsys.readouterr()

    code = evaluation.run(
        "import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"
    )

    output = capsys.readouterr()
    printed = output.out + output.err
    assert code == 1
    assert "looks like the worksheet as it was written" in printed
    assert f"{evaluation.prefix}.numbers" in printed

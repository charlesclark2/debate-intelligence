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
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st
from tests.evals.parser.corpus import parse_evaluation_file
from tests.evals.parser.labels_schema import (
    LABELS_DIRECTORY,
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
    load_label_file,
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
from tests.evals.parser.worksheets import (  # noqa: E402
    LABEL_COLUMNS,
    carry_marks,
    repair_worksheet,
    text_difference,
)

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
    with pytest.raises(prelabel.WorksheetError, match="text under the marks was edited"):
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
    with pytest.raises(prelabel.WorksheetError, match="row 6, checked: empty"):
        _import(rows, labels, document, ReviewerRole.OPERATOR)


def test_an_uncorrected_worksheet_nobody_checked_is_refused(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    """The failure this whole evaluation exists to prevent: pre-labels passed through untouched."""
    labels = _prelabel(document, whole_file)
    rows = _rows(_worksheet(labels, document, tmp_path, whole_file))
    with pytest.raises(prelabel.WorksheetError, match="looks like the worksheet as it was written"):
        _import(rows, labels, document, ReviewerRole.OPERATOR)


def test_edited_text_is_refused(
    document: ParsedDocument, whole_file: FileSamplingPlan, tmp_path: Path
) -> None:
    labels = _prelabel(document, whole_file)
    rows = _checked(_rows(_worksheet(labels, document, tmp_path, whole_file)))
    rows[3] = {**rows[3], "text": rows[3]["text"] + "!"}
    with pytest.raises(prelabel.WorksheetError, match="row 5, text: differs from the document"):
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
    with pytest.raises(prelabel.WorksheetError, match="rows were reordered"):
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


# --------------------------------------------------------------------------------------------
# check: every validation import runs, writing nothing
# --------------------------------------------------------------------------------------------


def _printed(capsys: pytest.CaptureFixture[str]) -> str:
    output = capsys.readouterr()
    return output.out + output.err


def _snapshot(*directories: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for directory in directories for path in sorted(directory.rglob("*"))}


def _problem_lines(printed: str) -> list[str]:
    return sorted(
        line.strip() for line in printed.splitlines() if line.startswith("  ") and "note:" not in line
    )


def test_check_of_a_worksheet_import_accepts_exits_0_and_writes_nothing(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_csv(evaluation.csv, _checked(_rows(evaluation.csv)))
    before = _snapshot(evaluation.labels, evaluation.worksheets)
    capsys.readouterr()

    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.csv)) == 0

    assert "ready to import; 11 rows checked, 0 labeled differently from the pre-labels" in _printed(capsys)
    assert _snapshot(evaluation.labels, evaluation.worksheets) == before


def test_check_lists_exactly_the_problems_import_refuses_with(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _checked(_rows(evaluation.csv))
    _row_of(rows, 2).update(unit="POCKETT", checked="")
    _row_of(rows, 6).update(card="7")
    _row_of(rows, EVIDENCE_ROW).update(underline="", text=_row_of(rows, EVIDENCE_ROW)["text"] + " ")
    _write_csv(evaluation.csv, rows)
    before = _snapshot(evaluation.labels, evaluation.worksheets)
    capsys.readouterr()

    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.csv)) == 1
    checked = _printed(capsys)
    assert _snapshot(evaluation.labels, evaluation.worksheets) == before
    assert (
        evaluation.run(
            "import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"
        )
        == 1
    )
    imported = _printed(capsys)

    assert _problem_lines(checked) == _problem_lines(imported)
    for expected in (
        "row 2, checked: ",
        "row 2, unit: ",
        "row 5, card: card 0 has no CITE row",
        "row 6, completeness: card 7 has no completeness",
        "row 7, text: ",
        "row 7, underline: ",
    ):
        assert any(line.startswith(expected) for line in _problem_lines(checked)), expected
    assert evaluation.label_file.read_bytes() == before[evaluation.label_file]


def test_check_catches_a_card_rule_import_used_to_meet_only_when_writing(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    """A card with no cite passed import's own checks and then failed inside write_label_file."""
    rows = _checked(_rows(evaluation.csv))
    _row_of(rows, 6).update(unit="EVIDENCE")
    _write_csv(evaluation.csv, rows)
    capsys.readouterr()

    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.csv)) == 1

    assert "row 5, card: card 0 has no CITE row" in _printed(capsys)


def test_check_and_import_read_a_numbers_file_directly(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _checked(_rows(evaluation.csv))
    _row_of(rows, 9).update(unit="TAG", card="5", completeness="")
    _row_of(rows, 9).update(unit="ANALYTIC", card="")
    _write_numbers(evaluation.numbers, rows)
    capsys.readouterr()

    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.numbers)) == 0
    assert "ready to import" in _printed(capsys)
    assert (
        evaluation.run(
            "import", evaluation.prefix, "--worksheet", str(evaluation.numbers), "--corrected-by", "coach"
        )
        == 0
    )
    assert load_label_file(evaluation.label_file).header.status is LabelStatus.CORRECTED


def test_a_numbers_file_older_than_the_csv_beside_it_is_refused(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_numbers(evaluation.numbers, _checked(_rows(evaluation.csv)))
    _age(evaluation.numbers, 60)
    capsys.readouterr()

    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.numbers)) == 1

    assert f"{evaluation.prefix}.numbers is older than {evaluation.prefix}.csv" in _printed(capsys)


def test_the_newer_of_the_two_is_read_without_complaint(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_numbers(evaluation.numbers, _checked(_rows(evaluation.csv)))
    _age(evaluation.csv, 60)
    capsys.readouterr()

    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.numbers)) == 0
    assert "older" not in _printed(capsys)


# --------------------------------------------------------------------------------------------
# check --repair: the document's text back, marks carried onto it, no label touched
# --------------------------------------------------------------------------------------------

EVIDENCE_TEXT = OPENING + UNDERLINED + CLOSING
UNDERLINED_RANGE = (len(OPENING), len(OPENING) + len(UNDERLINED))


def _repair(evaluation: _Evaluation, worksheet: Path, out: Path | None = None) -> int:
    out = out if out is not None else evaluation.csv
    return evaluation.run(
        "check", evaluation.prefix, "--worksheet", str(worksheet), "--repair", "--out", str(out)
    )


def _numbers_changes(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """What a spreadsheet does to text nobody edited: spacing, line breaks, dashes, quotes, dots."""
    changed = [dict(row) for row in rows]
    _row_of(changed, 4)["text"] = "AT:  Reserve Margin Turn"
    _row_of(changed, 5)["text"] = "Moratoria collapse the reserve margin\n"
    _row_of(changed, CITE_ROW)["text"] = "Okonkwo 26,\nGrid Analyst — Fictional Energy Review"
    evidence = _row_of(changed, EVIDENCE_ROW)
    evidence["text"] = EVIDENCE_TEXT.replace("warn that ", "warn that ").replace("summers.", "summers…")
    _row_of(changed, 9)["text"] = "“Their turn is non–unique”"
    return changed


def test_repair_restores_every_row_the_spreadsheet_changed_and_then_imports(
    evaluation: _Evaluation, document: ParsedDocument, capsys: pytest.CaptureFixture[str]
) -> None:
    original = _checked(_rows(evaluation.csv))
    _write_numbers(evaluation.numbers, _numbers_changes(original))
    capsys.readouterr()

    assert _repair(evaluation, evaluation.numbers) == 0

    printed = _printed(capsys)
    for number in (4, 5, CITE_ROW, EVIDENCE_ROW, 9):
        assert f"row {number}, text: restored the document's text" in printed, number
    assert "a line break where the document has a space" in printed
    assert "an em dash where the document has" in printed
    assert 'an ellipsis character where the document has "."' in printed
    assert "an opening curly double quote added" in printed
    assert "an en dash where the document has a hyphen" in printed
    assert "ready to import" in printed
    assert [row["text"] for row in _rows(evaluation.csv)] == [s.text for s in document.sections]
    assert (
        evaluation.run(
            "import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"
        )
        == 0
    )


def test_repair_carries_the_marks_onto_the_restored_text(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    """The person's marks, not the pre-label's: a mark they moved stays where they moved it."""
    rows = _checked(_rows(evaluation.csv))
    evidence = _row_of(rows, EVIDENCE_ROW)
    evidence["text"] = EVIDENCE_TEXT.replace("warn that ", "warn that ").replace(
        "margins fall", "margins\nfall"
    )
    evidence["underline"] = (
        f"Grid operators warn that {prelabel.MARK_OPEN}reserve margins\nfall below safe levels"
        f"{prelabel.MARK_CLOSE} within two summers."
    )
    evidence["highlight"] = (
        f"{prelabel.MARK_OPEN}Grid operators{prelabel.MARK_CLOSE} warn that reserve margins\nfall "
        "below safe levels within two summers."
    )
    _write_csv(evaluation.csv, rows)
    capsys.readouterr()

    assert _repair(evaluation, evaluation.csv) == 0

    printed = _printed(capsys)
    assert f"row {EVIDENCE_ROW}, underline: carried the marks onto the document's text" in printed
    assert f"row {EVIDENCE_ROW}, highlight: carried the marks onto the document's text" in printed
    repaired = _row_of(_rows(evaluation.csv), EVIDENCE_ROW)
    assert repaired["text"] == EVIDENCE_TEXT
    assert repaired["underline"] == prelabel.render_markup(EVIDENCE_TEXT, (UNDERLINED_RANGE,))
    assert repaired["highlight"] == prelabel.render_markup(EVIDENCE_TEXT, ((0, len("Grid operators")),))


def test_repair_fills_an_emptied_sampled_cell_with_its_text_and_no_marks(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _checked(_rows(evaluation.csv))
    _row_of(rows, EVIDENCE_ROW)["highlight"] = ""
    _row_of(rows, 12)["underline"] = " "
    _write_csv(evaluation.csv, rows)
    capsys.readouterr()

    assert _repair(evaluation, evaluation.csv) == 0

    printed = _printed(capsys)
    assert f"row {EVIDENCE_ROW}, highlight: was empty; filled with the row's text and no marks" in printed
    assert "row 12, underline: was empty; filled with the row's text and no marks" in printed
    repaired = _rows(evaluation.csv)
    assert _row_of(repaired, EVIDENCE_ROW)["highlight"] == EVIDENCE_TEXT
    assert (
        evaluation.run(
            "import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"
        )
        == 0
    )
    spans = {span.index: span for span in load_label_file(evaluation.label_file).spans}
    assert spans[5].highlight == () and spans[5].underline == (UNDERLINED_RANGE,)
    assert spans[10].underline == ()


def test_check_notes_span_cells_on_unsampled_rows_and_repair_empties_them(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    """Import ignores them, so check passes with a note; the repair clears them."""
    rows = _checked(_rows(evaluation.csv))
    _row_of(rows, CITE_ROW)["underline"] = f"{prelabel.MARK_OPEN}Okonkwo 26{prelabel.MARK_CLOSE}"
    _write_csv(evaluation.csv, rows)
    capsys.readouterr()

    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.csv)) == 0
    assert f"note: row {CITE_ROW}, underline: this row is not sampled for spans" in _printed(capsys)
    assert _repair(evaluation, evaluation.csv) == 0

    assert f"row {CITE_ROW}, underline: emptied; this row is not sampled" in _printed(capsys)
    assert _row_of(_rows(evaluation.csv), CITE_ROW)["underline"] == ""


def test_repair_removes_the_table_name_line(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_csv(evaluation.csv, _checked(_rows(evaluation.csv)), above_header=["Table 1"])
    capsys.readouterr()

    assert _repair(evaluation, evaluation.csv) == 0

    assert "removed the line above the header" in _printed(capsys)
    with evaluation.csv.open(encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle)) == list(prelabel.WORKSHEET_COLUMNS)


def test_repair_refuses_and_writes_nothing_when_letters_or_digits_changed(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _checked(_numbers_changes(_rows(evaluation.csv)))
    _row_of(rows, EVIDENCE_ROW)["text"] = EVIDENCE_TEXT.replace("Grid operators", "Grid Operators")
    _row_of(rows, 12)["underline"] = (
        f"{prelabel.MARK_OPEN}Moratoria shift load{prelabel.MARK_CLOSE} to older plant."
    )
    _write_numbers(evaluation.numbers, rows)
    out = evaluation.worksheets / "repaired.csv"
    capsys.readouterr()

    assert _repair(evaluation, evaluation.numbers, out) == 1

    printed = _printed(capsys)
    assert not out.exists()
    assert "REFUSED; nothing written" in printed
    assert f"row {EVIDENCE_ROW}, text: letters or digits differ from the document" in printed
    assert '"O" where the document has "o"' in printed
    assert "row 12, underline: the text under the marks was edited" in printed
    assert "restored" not in printed


def test_repair_output_is_never_written_inside_the_repository(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    inside = REPOSITORY_ROOT / "build" / "worksheets" / "repaired.csv"
    assert _repair(evaluation, evaluation.csv, inside) == 1
    assert "outside the repository" in _printed(capsys)
    assert not inside.exists()


def test_repair_needs_somewhere_to_write(evaluation: _Evaluation) -> None:
    with pytest.raises(SystemExit):
        evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.csv), "--repair")


def _label_cells(path: Path) -> list[tuple[str, ...]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [tuple(row[column] for column in LABEL_COLUMNS) for row in csv.DictReader(handle)]


def test_labels_are_byte_identical_before_and_after_a_repair(
    evaluation: _Evaluation, document: ParsedDocument, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every kind of repair at once, over labels a person changed, and not one label cell moves."""
    rows = _checked(_numbers_changes(_rows(evaluation.csv)))
    _row_of(rows, 2).update(checked="Y ")
    _row_of(rows, 9).update(unit="tag ")
    _row_of(rows, 9).update(unit="ANALYTIC")
    _row_of(rows, 3).update(unit="hat")
    _row_of(rows, 10).update(card=" 1", completeness="full")
    _row_of(rows, 11).update(card="1 ")
    _row_of(rows, 12).update(card="1", underline="")
    _row_of(rows, CITE_ROW).update(highlight="stray")
    _write_csv(evaluation.numbers.with_suffix(".edited.csv"), rows)
    before_labels = _label_cells(evaluation.numbers.with_suffix(".edited.csv"))
    label_file_before = evaluation.label_file.read_bytes()
    capsys.readouterr()

    assert _repair(evaluation, evaluation.numbers.with_suffix(".edited.csv")) == 0

    assert _label_cells(evaluation.csv) == before_labels
    assert evaluation.label_file.read_bytes() == label_file_before
    assert (
        evaluation.run(
            "import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"
        )
        == 0
    )
    by_hand = load_label_file(evaluation.label_file)
    assert [p.unit.value for p in by_hand.paragraphs] == [
        "POCKET", "HAT", "BLOCK", "TAG", "CITE", "EVIDENCE", "OTHER", "ANALYTIC", "TAG", "CITE", "EVIDENCE"
    ]  # fmt: skip
    assert [p.card for p in by_hand.paragraphs] == [None, None, None, 0, 0, 0, None, None, 1, 1, 1]
    assert [s.underline for s in by_hand.spans] == [(), (UNDERLINED_RANGE,), ()]


# --------------------------------------------------------------------------------------------
# Properties: alignment, the refusal threshold, labels, and how much text a message shows
# --------------------------------------------------------------------------------------------

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None)

#: What sits between words, before and after a spreadsheet: spacing, dashes, quotes, dots.
SEPARATORS = (" ", "  ", " ", "\n", "\r\n", "\t", "", " - ", " – ", "—", ", ", "“", "”", "'", "’", "…", "...")
WORDS = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGH0123456789éß", min_size=1, max_size=8)


def _assemble(
    words: list[str], separators: list[str], marked: list[bool]
) -> tuple[str, tuple[tuple[int, int], ...]]:
    """Text from words and the separators around them, and a mark over each run of marked words."""
    text = separators[0]
    starts: list[int] = []
    ends: list[int] = []
    for word, separator in zip(words, separators[1:], strict=True):
        starts.append(len(text))
        text += word
        ends.append(len(text))
        text += separator
    ranges: list[tuple[int, int]] = []
    run_start: int | None = None
    for position, mark in enumerate([*marked, False]):
        if mark and run_start is None:
            run_start = position
        elif not mark and run_start is not None:
            ranges.append((starts[run_start], ends[position - 1]))
            run_start = None
    return text, tuple(ranges)


@st.composite
def respaced(draw: st.DrawFn) -> tuple[str, tuple[tuple[int, int], ...], str, tuple[tuple[int, int], ...]]:
    """A document's text with marks, and the same words and marks after a spreadsheet re-spaced it."""
    words = draw(st.lists(WORDS, min_size=1, max_size=10))
    original = draw(st.lists(st.sampled_from(SEPARATORS), min_size=len(words) + 1, max_size=len(words) + 1))
    changed = [draw(st.sampled_from(SEPARATORS)) if draw(st.booleans()) else s for s in original]
    marked = draw(st.lists(st.booleans(), min_size=len(words), max_size=len(words)))
    text, ranges = _assemble(words, original, marked)
    found, found_ranges = _assemble(words, changed, marked)
    if ranges and found != text:
        moved = any(a != b for (a, _), (b, _) in zip(ranges, found_ranges, strict=True))
        event("a mark moved with the spacing" if moved else "the spacing changed but no mark moved")
    return text, ranges, found, found_ranges


@PROPERTY_SETTINGS
@given(respaced())
def test_marks_land_on_the_same_words_after_any_respacing(
    case: tuple[str, tuple[tuple[int, int], ...], str, tuple[tuple[int, int], ...]],
) -> None:
    text, ranges, found, found_ranges = case
    carried = carry_marks(prelabel.render_markup(found, found_ranges), text)
    assert carried == prelabel.render_markup(text, ranges)


def test_a_mark_over_a_space_the_spreadsheet_changed_keeps_the_space() -> None:
    text = "reserve margins fall"
    assert carry_marks("reserve⟦ margins⟧\nfall", text) == "reserve⟦ margins⟧ fall"
    assert carry_marks("⟦reserve  ⟧margins fall", text) == "⟦reserve ⟧margins fall"


#: Characters a one-character edit uses: letters and digits, Latin and not, and everything else.
EDIT_CHARACTERS = "aZ7éßΩ²١  \n\t,.;:'\"‘’“”-–—…()?!/"


@PROPERTY_SETTINGS
@given(st.text(alphabet=EDIT_CHARACTERS, min_size=1, max_size=30), st.data())
def test_a_row_is_refused_exactly_when_a_letter_or_digit_changed(text: str, data: st.DataObject) -> None:
    kind = data.draw(st.sampled_from(["insert", "delete", "replace"]))
    position = data.draw(st.integers(0, len(text) - (kind != "insert")))
    character = data.draw(st.sampled_from(EDIT_CHARACTERS))
    if kind == "insert":
        found, touched = text[:position] + character + text[position:], character
    elif kind == "delete":
        found, touched = text[:position] + text[position + 1 :], text[position]
    else:
        found, touched = text[:position] + character + text[position + 1 :], text[position] + character
    assume(found != text)
    words_changed = any(c.isalnum() for c in touched)
    event("refused" if words_changed else "repaired")
    row = {**dict.fromkeys(prelabel.WORKSHEET_COLUMNS, ""), "index": "0", "checked": "y", "text": found}

    repair = repair_worksheet(
        prelabel.Worksheet(columns=prelabel.WORKSHEET_COLUMNS, rows=(row,)),
        texts={0: text},
        sampled=frozenset(),
    )

    assert bool(repair.refused) is words_changed
    if not words_changed:
        assert repair.worksheet.rows[0]["text"] == text


LABEL_CELLS = st.text(alphabet="yYn TAGcitEVD0123456789 ,.-", max_size=6)


@PROPERTY_SETTINGS
@given(
    st.lists(
        st.tuples(
            respaced(), LABEL_CELLS, LABEL_CELLS, LABEL_CELLS, LABEL_CELLS, st.booleans(), st.integers(0, 3)
        ),
        min_size=1,
        max_size=4,
    )
)
def test_a_repair_never_writes_a_label_cell(
    rows: list[
        tuple[
            tuple[str, tuple[tuple[int, int], ...], str, tuple[tuple[int, int], ...]],
            str,
            str,
            str,
            str,
            bool,
            int,
        ]
    ],
) -> None:
    texts: dict[int, str] = {}
    sampled: set[int] = set()
    worksheet_rows = []
    for index, (
        (text, _, found, found_ranges),
        checked,
        unit,
        card,
        completeness,
        is_sampled,
        span_kind,
    ) in enumerate(rows):
        texts[index] = text
        if is_sampled:
            sampled.add(index)
        span = ["", " ", prelabel.render_markup(found, found_ranges), f"⟦{found}"][span_kind]
        worksheet_rows.append(
            {
                "index": str(index),
                "checked": checked,
                "unit": unit,
                "card": card,
                "completeness": completeness,
                "text": found,
                "underline": span,
                "highlight": span,
            }
        )
    worksheet = prelabel.Worksheet(columns=prelabel.WORKSHEET_COLUMNS, rows=tuple(worksheet_rows))

    repair = repair_worksheet(worksheet, texts=texts, sampled=frozenset(sampled))

    assert not repair.refused
    event("some row repaired" if repair.changes else "nothing to repair")
    for before, after in zip(worksheet.rows, repair.worksheet.rows, strict=True):
        assert {column: after[column] for column in LABEL_COLUMNS} == {
            column: before[column] for column in LABEL_COLUMNS
        }
    assert [row["text"] for row in repair.worksheet.rows] == [texts[i] for i in range(len(rows))]


@PROPERTY_SETTINGS
@given(st.text(alphabet="abcdefgh ", min_size=40, max_size=300), st.data())
def test_a_message_never_shows_a_whole_cell(text: str, data: st.DataObject) -> None:
    """Enough around each difference to find it, and never the paragraph itself."""
    edits = data.draw(
        st.lists(st.tuples(st.integers(0, len(text) - 1), st.sampled_from("X \n")), min_size=1, max_size=4)
    )
    found = list(text)
    for position, character in edits:
        found[position] = character
    found_text = "".join(found)
    assume(found_text != text)

    message = text_difference(found_text, text)

    for whole in (text, found_text):
        assert whole.translate(str.maketrans("\n", "↵")) not in message


def test_the_guides_loop_repairs_before_it_imports_and_deletes_both_files() -> None:
    """ac4: save, check --repair, import, then delete the worksheet and its .numbers file."""
    guide = (LABELS_DIRECTORY / "README.md").read_text(encoding="utf-8")
    loop = guide[guide.index("### 3. Each file") : guide.index("### 4. The finish")]
    blocks = [block for block in loop.split("```bash\n")[1:]]
    repair = next(i for i, block in enumerate(blocks) if "prelabel_docx.py check" in block)
    imported = next(i for i, block in enumerate(blocks) if "prelabel_docx.py import" in block)
    assert repair < imported
    assert (
        "--worksheet ~/parser-eval-worksheets/${f}.numbers --repair --out ~/parser-eval-worksheets/${f}.csv"
        in blocks[repair]
    )
    assert "rm ~/parser-eval-worksheets/${f}.csv &&" in blocks[imported]
    assert "rm -f -r ~/parser-eval-worksheets/${f}.numbers &&" in blocks[imported]
    assert "does not rewrite" not in guide and "Export To, CSV writes" not in guide

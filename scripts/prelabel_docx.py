#!/usr/bin/env python3
"""Seed the parser evaluation's labels from parser output, for a person to correct.

The labels are the acceptance evidence for `v1-e31-t05-parser-eval`, so they are written by a
person looking at the file, never accepted as the parser emitted them (working agreements §6). A
pre-label that goes in uncorrected is the parser grading its own homework. This script exists to
save the person typing, and every step of it is built so that a pre-label cannot become a label
without being looked at:

1. **`prelabel`** parses a file and writes `labels/<digest>.jsonl` marked `PRELABELED`. It holds
   no text: a unit and a card per labeled paragraph, keyed by index and a keyed digest of the text.
   Only the paragraphs the **sampling plan** covers are written — the PR subset in full, about a
   quarter of every other file, in contiguous blocks. The evaluation refuses a `PRELABELED` file.
2. **`worksheet`** writes a CSV for the person to correct, with each paragraph's text beside its
   pre-label. Because it holds text, **it is written outside the repository** and the script
   refuses a directory inside it. Open it in Numbers or LibreOffice (Excel rewrites some text on
   import; the check in step 3 would catch that and refuse it).
3. **`import`** reads the corrected worksheet back. It fails unless **every row is marked checked**
   and **no text was edited** — text is never edited to make a label line up — and then writes the
   label file as `CORRECTED`, recording which role corrected it and how many rows changed.
4. **`mark-reviewed`** records that the coach spot-checked a corrected file end to end.

What it prints is counts and keyed-digest prefixes, never text or paths.

## Worksheet columns

| Column | Meaning |
|---|---|
| `index` | The paragraph's position in the body. Not consecutive where the plan samples. Do not edit. |
| `checked` | Put `y` once the row is right. Import refuses a worksheet with an empty cell here. |
| `unit` | POCKET, HAT, BLOCK, TAG, CITE, EVIDENCE, ANALYTIC, UNDERTAG or OTHER. |
| `card` | A number shared by the paragraphs of one card (tag, undertags, cite, body); blank otherwise. |
| `completeness` | FULL, ABBREVIATED or CITE_ONLY, on the first row of each card only. |
| `text` | The paragraph as the parser read it. Never edit it. |
| `underline` | Sampled rows only: the text with `⟦` and `⟧` around every underlined stretch. |
| `highlight` | Sampled rows only: the same, around every highlighted stretch. |

See `tests/fixtures/debate_files/eval/labels/README.md` for the labeling guide.

## Running it

    uv run python scripts/prelabel_docx.py prelabel --all
    uv run python scripts/prelabel_docx.py worksheet 4f2c91ab --out-dir ~/parser-eval-worksheets
    uv run python scripts/prelabel_docx.py import 4f2c91ab \\
        --worksheet ~/parser-eval-worksheets/4f2c91ab....csv --corrected-by coach
    uv run python scripts/prelabel_docx.py mark-reviewed 4f2c91ab --reviewer coach

A file is named by any unambiguous prefix of its keyed digest. Every digest here is an HMAC under
the evaluation key (see `tests/evals/parser/digests.py`); a plain SHA-256 would be a join key back
to `<School>/<TeamCode>/<filename>`, because both this repository and the caselist archives are
public.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.evals.parser.corpus import load_evaluation_document, load_path_map  # noqa: E402
from tests.evals.parser.digests import require_key, text_digest  # noqa: E402
from tests.evals.parser.labels_schema import (  # noqa: E402
    CARD_UNITS,
    LABELS_DIRECTORY,
    MANIFEST_PATH,
    SAMPLING_PLAN_PATH,
    Block,
    CardLabel,
    FileLabelHeader,
    FileSamplingPlan,
    LabelFile,
    LabelStatus,
    Manifest,
    ManifestEntry,
    ParagraphLabel,
    ReviewerRole,
    SamplingPlan,
    SpanLabel,
    label_path_for,
    load_label_file,
    load_manifest,
    load_rejections,
    load_sampling_plan,
    validate_against_texts,
    validate_label_file,
    write_label_file,
)
from tests.evals.parser.metrics import prediction_from_document  # noqa: E402
from tests.evals.parser.worksheets import (  # noqa: E402
    MARK_CLOSE,
    MARK_OPEN,
    SPAN_COLUMNS,
    WORKSHEET_COLUMNS,
    MarkupError,
    Problem,
    Worksheet,
    WorksheetError,
    merge_ranges,
    older_worksheet,
    parse_index,
    read_worksheet,
    render_markup,
    repair_worksheet,
    row_number,
    split_markup,
    text_difference,
    write_worksheet_csv,
)

from debate_core.domain.debate_files import CardCompleteness, ParsedDocument  # noqa: E402
from debate_core.domain.style_profile import StructuralUnit  # noqa: E402
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION  # noqa: E402

__all__ = [
    "MARK_CLOSE",
    "MARK_OPEN",
    "WORKSHEET_COLUMNS",
    "Worksheet",
    "WorksheetError",
    "import_worksheet",
    "is_sampled",
    "main",
    "parse_markup",
    "prelabel_document",
    "render_markup",
    "worksheet_problems",
    "write_worksheet",
]

SPAN_SAMPLE_FRACTION = 0.2
UNIT_NAMES = tuple(unit.value for unit in StructuralUnit)
COMPLETENESS_NAMES = tuple(value.value for value in CardCompleteness)


# --------------------------------------------------------------------------------------------
# Pre-labels
# --------------------------------------------------------------------------------------------


def is_sampled(file_digest: str, index: int, fraction: float = SPAN_SAMPLE_FRACTION) -> bool:
    """Whether a labeled paragraph also gets its spans labeled: a stable hash, not anyone's choice.

    Derived from the file's keyed digest, so it is reproducible for whoever holds the key and
    meaningless to anybody else.
    """
    digest = hashlib.sha256(f"{file_digest}:span-sample:{index}".encode()).digest()
    return int.from_bytes(digest[:4], "big") < fraction * 2**32


def prelabel_document(
    document: ParsedDocument, plan: FileSamplingPlan, plan_id: str, key: bytes
) -> LabelFile:
    """Turn the parser's reading of a file into labels marked `PRELABELED`, over the plan's blocks.

    Card membership comes from each card's element range; a blank paragraph inside that range is
    not part of the card, and a card that is not wholly inside one labeled block is left unnumbered
    because it cannot be scored. Spans are recorded on the sampled non-empty labeled paragraphs.
    """
    prediction = prediction_from_document(document)
    card_of: dict[int, int] = {}
    cards: list[CardLabel] = []
    for card_id, (first, last, completeness) in enumerate(prediction.cards):
        if not _inside_one_block(plan.blocks, first, last):
            continue
        cards.append(CardLabel(card=card_id, completeness=completeness))
        for index in range(first, last + 1):
            card_of[index] = card_id
    paragraphs: list[ParagraphLabel] = []
    spans: list[SpanLabel] = []
    for section in document.sections:
        if not plan.contains(section.element_index):
            continue
        unit = section.unit
        in_card = card_of.get(section.element_index) if unit in CARD_UNITS else None
        paragraphs.append(
            ParagraphLabel(
                index=section.element_index,
                length=len(section.text),
                text_digest=text_digest(section.text, key),
                unit=unit,
                card=in_card,
            )
        )
        if section.text.strip() and is_sampled(plan.digest, section.element_index):
            spans.append(
                SpanLabel(
                    index=section.element_index,
                    underline=merge_ranges(prediction.underline.get(section.element_index, ())),
                    highlight=merge_ranges(prediction.highlight.get(section.element_index, ())),
                )
            )
    used = {p.card for p in paragraphs if p.card is not None}
    return LabelFile(
        header=FileLabelHeader(
            digest=plan.digest,
            paragraph_count=len(document.sections),
            blocks=plan.blocks,
            plan_id=plan_id,
            status=LabelStatus.PRELABELED,
            prelabel_parser_version=document.parser_version,
            span_sample_fraction=SPAN_SAMPLE_FRACTION,
        ),
        paragraphs=tuple(paragraphs),
        cards=tuple(card for card in cards if card.card in used),
        spans=tuple(spans),
    )


def _inside_one_block(blocks: Sequence[Block], first: int, last: int) -> bool:
    return any(start <= first and last <= end for start, end in blocks)


# --------------------------------------------------------------------------------------------
# Span markup
# --------------------------------------------------------------------------------------------


def parse_markup(markup: str, text: str, *, row: int, column: str) -> tuple[tuple[int, int], ...]:
    """Read `⟦…⟧` markup back into ranges, and refuse it if the text underneath is not `text`."""
    try:
        plain, ranges = split_markup(markup)
    except MarkupError as error:
        raise WorksheetError(str(Problem(str(error), row, column))) from error
    if plain != text:
        raise WorksheetError(str(Problem(text_difference(plain, text, under_marks=True), row, column)))
    return ranges


# --------------------------------------------------------------------------------------------
# Worksheets
# --------------------------------------------------------------------------------------------


def _outside_repository(directory: Path) -> Path:
    resolved = directory.expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return resolved
    raise WorksheetError("a worksheet holds paragraph text and must be written outside the repository")


def _label_cells(labels: LabelFile) -> dict[int, tuple[str, str, str]]:
    """Each row's `unit`, `card` and `completeness` cells as a worksheet of these labels shows them.

    Completeness goes on the first row of each card only.
    """
    completeness = {card.card: card.completeness.value for card in labels.cards}
    cells: dict[int, tuple[str, str, str]] = {}
    seen_cards: set[int] = set()
    for paragraph in labels.paragraphs:
        first_of_card = paragraph.card is not None and paragraph.card not in seen_cards
        if paragraph.card is not None:
            seen_cards.add(paragraph.card)
        cells[paragraph.index] = (
            paragraph.unit.value,
            "" if paragraph.card is None else str(paragraph.card),
            completeness.get(paragraph.card, "") if first_of_card and paragraph.card is not None else "",
        )
    return cells


def write_worksheet(
    labels: LabelFile, document: ParsedDocument, out_dir: Path, key: bytes, digest: str
) -> Path:
    """One CSV of the labeled rows, outside the repository, for a person to correct."""
    directory = _outside_repository(out_dir)
    texts = [section.text for section in document.sections]
    problems = validate_against_texts(labels, digest, texts, lambda text: text_digest(text, key))
    if problems:
        raise WorksheetError("the labels do not describe this file: " + "; ".join(problems[:3]))
    spans = {span.index: span for span in labels.spans}
    cells = _label_cells(labels)

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{labels.digest[:16]}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(WORKSHEET_COLUMNS)
        for paragraph in labels.paragraphs:
            span = spans.get(paragraph.index)
            text = texts[paragraph.index]
            unit, card, completeness = cells[paragraph.index]
            writer.writerow(
                [
                    paragraph.index,
                    "",
                    unit,
                    card,
                    completeness,
                    text,
                    "" if span is None else render_markup(text, span.underline),
                    "" if span is None else render_markup(text, span.highlight),
                ]
            )
    return path


def _cell(row: Mapping[str, str], column: str) -> str:
    return row.get(column) or ""


def _quoted(cell: str) -> str:
    return repr(cell.strip()) if cell.strip() else "an empty cell"


def _labels_untouched(
    rows: Sequence[Mapping[str, str]], indices: Sequence[int | None], prelabels: LabelFile
) -> bool:
    """No row checked, and every `unit`, `card` and `completeness` cell as the worksheet was written."""
    if not rows or any(_cell(row, "checked").strip() for row in rows):
        return False
    written = _label_cells(prelabels)
    for row, index in zip(rows, indices, strict=True):
        if index is None:
            return False
        unit, card, completeness = written[index]
        cells = (_cell(row, "unit").strip().upper(), _cell(row, "card").strip(), _cell(row, "completeness"))
        if cells != (unit, card, completeness):
            return False
    return True


def worksheet_problems(
    worksheet: Worksheet,
    *,
    prelabels: LabelFile,
    texts: Sequence[str],
    numbers_beside: str | None = None,
) -> tuple[list[Problem], list[Problem]]:
    """Every reason `import` would refuse this worksheet, and notes on cells it would ignore.

    Every row is checked in full: a problem in one column never hides one in another. The rows are
    the sampling plan's labeled paragraphs, in order, not every paragraph of the file. Text is
    compared exactly; the repair is how a worksheet gets there. `numbers_beside` names a `.numbers`
    file beside a CSV worksheet, for the message about an untouched worksheet.
    """
    problems: list[Problem] = []
    notes: list[Problem] = []
    rows = worksheet.rows
    if worksheet.lines_above_header:
        problems.append(
            Problem(
                'a line above the header, which Numbers\' export option "Include table names" adds. '
                "check --repair removes it; or export again with that option unticked"
            )
        )
    missing_columns = [column for column in WORKSHEET_COLUMNS if column not in worksheet.columns]
    if missing_columns:
        problems.append(
            Problem(
                f"the header has no {', '.join(missing_columns)} column. The header row reads "
                f"{','.join(WORKSHEET_COLUMNS)}"
            )
        )

    # Which paragraph each row is.
    expected = [paragraph.index for paragraph in prelabels.paragraphs]
    plan_position = {index: position for position, index in enumerate(expected)}
    row_of: dict[int, int] = {}
    indices: list[int | None] = []
    for position, row in enumerate(rows):
        number = row_number(position)
        cell = _cell(row, "index")
        index = parse_index(cell)
        if index is None:
            problems.append(
                Problem(
                    f"{_quoted(cell)} is not a paragraph number. Put back the number this row had",
                    number,
                    "index",
                )
            )
        elif index not in plan_position:
            problems.append(
                Problem(
                    f"paragraph {index} is not one of the paragraphs labeled in this file. Put back the "
                    "number this row had",
                    number,
                    "index",
                )
            )
            index = None
        elif index in row_of:
            problems.append(
                Problem(
                    f"paragraph {index} is also row {row_of[index]}: a row was copied. Delete one of them",
                    number,
                    "index",
                )
            )
            index = None
        else:
            row_of[index] = number
        indices.append(index)
    if len(rows) != len(expected):
        problems.append(
            Problem(
                f"the worksheet has {len(rows)} rows; the sampling plan labels {len(expected)} paragraphs "
                "of this file"
            )
        )
    for index in expected:
        if index not in row_of:
            problems.append(
                Problem(
                    f"paragraph {index} has no row: a row was deleted. Undo the deletion in the spreadsheet, "
                    "or copy the row back from a fresh worksheet"
                )
            )
    placed = [index for index in indices if index is not None]
    in_order = sorted(placed, key=plan_position.__getitem__)
    if placed != in_order:
        first = next(position for position, (a, b) in enumerate(zip(placed, in_order, strict=True)) if a != b)
        problems.append(
            Problem(
                "rows were reordered: from this row on they are out of index order. Sort the table by "
                "the index column, smallest first",
                row_of[placed[first]],
                "index",
            )
        )

    untouched = _labels_untouched(rows, indices, prelabels)
    if untouched:
        where = (
            f" {numbers_beside} is beside it: if you saved your work in Numbers, it is there. Run this "
            f"again with --worksheet naming {numbers_beside}"
            if numbers_beside
            else " If you saved your work in Numbers, Cmd+S wrote it to a .numbers file: give that file "
            "as --worksheet"
        )
        problems.append(
            Problem(
                "no row is checked and no label differs from the pre-labels, so this looks like the "
                "worksheet as it was written, before anyone worked on it." + where
            )
        )

    sampled = {span.index for span in prelabels.spans}
    units: dict[int, StructuralUnit] = {}
    completeness: dict[int, tuple[CardCompleteness, int]] = {}
    card_rows: dict[int, list[tuple[int | None, int]]] = {}
    for position, (row, index) in enumerate(zip(rows, indices, strict=True)):
        number = row_number(position)
        if not untouched and not _cell(row, "checked").strip():
            problems.append(Problem("empty. Put y here once the row is right", number, "checked"))
        unit_cell = _cell(row, "unit").strip().upper()
        if unit_cell in UNIT_NAMES:
            units[number] = StructuralUnit(unit_cell)
        else:
            problems.append(
                Problem(
                    f"{_quoted(_cell(row, 'unit'))} is not a unit. Use one of {', '.join(UNIT_NAMES)}",
                    number,
                    "unit",
                )
            )
        card_cell = _cell(row, "card").strip()
        card = int(card_cell) if card_cell.isdigit() else None
        if card_cell and card is None:
            problems.append(
                Problem(
                    f"{_quoted(card_cell)} is not a card number. Give every row of a card the same whole "
                    "number, and leave it empty elsewhere",
                    number,
                    "card",
                )
            )
        if card is not None:
            card_rows.setdefault(card, []).append((index, number))
        completeness_cell = _cell(row, "completeness").strip().upper()
        if completeness_cell and not card_cell:
            problems.append(
                Problem(
                    "filled on a row that is not in a card. Completeness goes on the first row of a card",
                    number,
                    "completeness",
                )
            )
        elif completeness_cell and card is not None:
            if completeness_cell not in COMPLETENESS_NAMES:
                problems.append(
                    Problem(
                        f"{_quoted(completeness_cell)} is not a completeness. Use one of "
                        f"{', '.join(COMPLETENESS_NAMES)}",
                        number,
                        "completeness",
                    )
                )
            else:
                value = CardCompleteness(completeness_cell)
                if card in completeness and completeness[card][0] is not value:
                    given, on_row = completeness[card]
                    problems.append(
                        Problem(
                            f"card {card} is already {given.value} on row {on_row}. Give a card one "
                            "completeness, on its first row",
                            number,
                            "completeness",
                        )
                    )
                completeness.setdefault(card, (value, number))

        if index is None:
            continue
        text = texts[index]
        if _cell(row, "text") != text:
            problems.append(Problem(text_difference(_cell(row, "text"), text), number, "text"))
        for column in SPAN_COLUMNS:
            cell = _cell(row, column)
            if index not in sampled:
                if cell.strip():
                    notes.append(
                        Problem(
                            "this row is not sampled for spans, so import ignores this cell. check --repair "
                            "empties it",
                            number,
                            column,
                        )
                    )
                continue
            if not cell.strip():
                problems.append(
                    Problem(
                        "empty: a row with nothing marked keeps its text with no marks. check --repair "
                        "fills it in",
                        number,
                        column,
                    )
                )
                continue
            try:
                plain, _ = split_markup(cell)
            except MarkupError as error:
                problems.append(Problem(f"{error}. Move or delete the stray mark", number, column))
                continue
            if plain != text:
                problems.append(Problem(text_difference(plain, text, under_marks=True), number, column))

    # Whole cards.
    for card, members in sorted(card_rows.items()):
        first_row = members[0][1]
        card_units = [units.get(number) for _, number in members]
        for (_, number), unit in zip(members, card_units, strict=True):
            if unit is not None and unit not in CARD_UNITS:
                problems.append(
                    Problem(
                        f"a {unit.value} row is never part of a card. Leave card empty here",
                        number,
                        "card",
                    )
                )
        if card not in completeness:
            problems.append(
                Problem(
                    f"card {card} has no completeness on any of its rows. Put one of "
                    f"{', '.join(COMPLETENESS_NAMES)} on its first row",
                    first_row,
                    "completeness",
                )
            )
        if None not in card_units:
            if StructuralUnit.CITE not in card_units:
                problems.append(
                    Problem(
                        f"card {card} has no CITE row. A card is a tag, its cite and its body",
                        first_row,
                        "card",
                    )
                )
            value = completeness.get(card, (None, 0))[0]
            has_body = StructuralUnit.EVIDENCE in card_units
            if value is CardCompleteness.CITE_ONLY and has_body:
                problems.append(
                    Problem(f"card {card} is CITE_ONLY but has an EVIDENCE row", first_row, "completeness")
                )
            if value is not None and value is not CardCompleteness.CITE_ONLY and not has_body:
                problems.append(
                    Problem(
                        f"card {card} is {value.value} but has no EVIDENCE row", first_row, "completeness"
                    )
                )
        placed_members = [index for index, _ in members if index is not None]
        if placed_members and not _inside_one_block(
            prelabels.header.blocks, min(placed_members), max(placed_members)
        ):
            problems.append(
                Problem(
                    f"card {card} crosses the edge of a sampled block (rows {first_row} to "
                    f"{members[-1][1]}). Number only the cards that lie wholly inside one block, and leave "
                    "the rest empty",
                    first_row,
                    "card",
                )
            )

    column_order = {column: position for position, column in enumerate(WORKSHEET_COLUMNS)}
    problems.sort(key=lambda problem: (problem.row or 0, column_order.get(problem.column or "", -1)))
    return problems, notes


def format_problems(problems: Sequence[Problem]) -> str:
    return f"{len(problems)} problem(s):\n  " + "\n  ".join(str(problem) for problem in problems)


def import_worksheet(
    worksheet: Worksheet | Sequence[Mapping[str, str]],
    *,
    prelabels: LabelFile,
    texts: Sequence[str],
    corrected_by: ReviewerRole,
    key: bytes,
    numbers_beside: str | None = None,
) -> LabelFile:
    """Turn a corrected worksheet into a `CORRECTED` label file, or list every reason it cannot.

    The label file is checked with the same rules `write_label_file` applies, so a worksheet this
    accepts is one `import` can write.
    """
    if not isinstance(worksheet, Worksheet):
        worksheet = Worksheet.of(worksheet)
    problems, _ = worksheet_problems(
        worksheet, prelabels=prelabels, texts=texts, numbers_beside=numbers_beside
    )
    if problems:
        raise WorksheetError(format_problems(problems))

    sampled = {span.index for span in prelabels.spans}
    paragraphs: list[ParagraphLabel] = []
    spans: list[SpanLabel] = []
    completeness: dict[int, CardCompleteness] = {}
    for row in worksheet.rows:
        index = parse_index(_cell(row, "index"))
        assert index is not None  # worksheet_problems found none that is not
        text = texts[index]
        card_cell = _cell(row, "card").strip()
        card = int(card_cell) if card_cell else None
        completeness_cell = _cell(row, "completeness").strip().upper()
        if card is not None and completeness_cell:
            completeness[card] = CardCompleteness(completeness_cell)
        paragraphs.append(
            ParagraphLabel(
                index=index,
                length=len(text),
                text_digest=text_digest(text, key),
                unit=StructuralUnit(_cell(row, "unit").strip().upper()),
                card=card,
            )
        )
        if index in sampled:
            spans.append(
                SpanLabel(
                    index=index,
                    underline=split_markup(_cell(row, "underline"))[1],
                    highlight=split_markup(_cell(row, "highlight"))[1],
                )
            )

    before = {p.index: (p.unit, p.card) for p in prelabels.paragraphs}
    changed = sum(1 for p in paragraphs if before.get(p.index) != (p.unit, p.card))
    labels = LabelFile(
        header=FileLabelHeader(
            digest=prelabels.digest,
            paragraph_count=prelabels.header.paragraph_count,
            blocks=prelabels.header.blocks,
            plan_id=prelabels.header.plan_id,
            status=LabelStatus.CORRECTED,
            prelabel_parser_version=prelabels.header.prelabel_parser_version,
            corrected_by=corrected_by,
            rows_changed_from_prelabel=changed,
            span_sample_fraction=prelabels.header.span_sample_fraction,
        ),
        paragraphs=tuple(paragraphs),
        cards=tuple(CardLabel(card=card, completeness=value) for card, value in sorted(completeness.items())),
        spans=tuple(spans),
    )
    remaining = validate_label_file(labels)
    if remaining:
        raise WorksheetError(format_problems([Problem(problem) for problem in remaining]))
    return labels


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


def _resolve(manifest: Manifest, prefix: str) -> ManifestEntry:
    matches = [entry for entry in manifest.entries if entry.digest.startswith(prefix.lower())]
    if len(matches) != 1:
        raise SystemExit(f"{prefix!r} matches {len(matches)} manifest entries; give a longer prefix")
    return matches[0]


def _document(entry: ManifestEntry, key: bytes) -> ParsedDocument:
    path_map = load_path_map()
    if path_map is None:
        raise SystemExit("no evaluation path map on this machine; run scripts/select_eval_files.py first")
    return load_evaluation_document(entry, path_map, key)


def _remove_rejected_prelabels(rejected: frozenset[str], labels_dir: Path) -> None:
    """A rejected file's pre-label goes; a correction of one is never deleted by a tool."""
    for digest in sorted(rejected):
        path = label_path_for(digest, labels_dir)
        if not path.exists():
            continue
        status = load_label_file(path).header.status
        if status is LabelStatus.PRELABELED:
            path.unlink()
            print(f"{digest[:16]}: rejected; its PRELABELED label file removed")
        else:
            print(
                f"{digest[:16]}: rejected, but its label file is {status}; left alone, delete it deliberately"
            )


def _all_worksheets(
    manifest: Manifest, rejected: frozenset[str], labels_dir: Path, out_dir: Path, key: bytes
) -> int:
    """Write the worksheets that are missing, never over one that may be half filled in.

    A rejected file's worksheet holds the text of a file no longer in the evaluation, so it goes.
    """
    directory = _outside_repository(out_dir)
    written = kept = 0
    for entry in manifest.entries:
        path = label_path_for(entry.digest, labels_dir)
        if not path.exists():
            print(f"{entry.digest[:16]}: no label file; run prelabel --all first")
            return 1
        labels = load_label_file(path)
        if (
            labels.header.status is not LabelStatus.PRELABELED
            or (directory / f"{entry.digest[:16]}.csv").exists()
        ):
            kept += 1
            continue
        write_worksheet(labels, _document(entry, key), directory, key, entry.digest)
        written += 1
        rows = len(labels.paragraphs)
        print(f"{entry.digest[:16]}: worksheet of {rows} rows written outside the repository")
    for digest in sorted(rejected):
        stale = directory / f"{digest[:16]}.csv"
        if stale.exists():
            stale.unlink()
            print(f"{digest[:16]}: rejected; its worksheet removed")
    print(f"{written} worksheet(s) written, {kept} left as they were (already there, or already corrected)")
    return 0


def _open(entry: ManifestEntry) -> int:
    """Open the file with the system's default application. The path is never printed."""
    opener = shutil.which("open")
    if opener is None:
        raise SystemExit("`open` is the macOS command for opening a file; this machine has none")
    path_map = load_path_map()
    if path_map is None or entry.digest not in path_map:
        raise SystemExit(f"{entry.digest[:16]}: not in this machine's path map")
    subprocess.run([opener, str(path_map[entry.digest])], check=True)
    print(f"{entry.digest[:16]}: opened")
    return 0


def _numbers_beside(path: Path) -> str | None:
    beside = path.with_suffix(".numbers")
    return beside.name if path.suffix.lower() == ".csv" and beside.exists() else None


def _load_worksheet(prefix: str, path: Path) -> Worksheet | None:
    """The worksheet at `path`, or None after saying why it cannot be used. Names files, never folders."""
    stale = older_worksheet(path)
    if stale is not None:
        print(f"{prefix}: STOPPED. {stale}", file=sys.stderr)
        return None
    try:
        return read_worksheet(path)
    except FileNotFoundError:
        print(f"{prefix}: {path.name} not found", file=sys.stderr)
    except WorksheetError as error:
        print(f"{prefix}: {error}", file=sys.stderr)
    return None


def _check(entry: ManifestEntry, labels: LabelFile, args: argparse.Namespace, key: bytes) -> int:
    """`check`: every validation `import` runs, and with `--repair` the repair first. Writes no label."""
    prefix = entry.digest[:16]
    path: Path = args.worksheet.expanduser()
    worksheet = _load_worksheet(prefix, path)
    if worksheet is None:
        return 1
    texts = [section.text for section in _document(entry, key).sections]
    numbers_beside = _numbers_beside(path)
    if args.repair:
        try:
            out = _outside_repository(args.out.expanduser().parent) / args.out.name
        except WorksheetError as error:
            print(f"{prefix}: {error}", file=sys.stderr)
            return 1
        repair = repair_worksheet(
            worksheet,
            texts={paragraph.index: texts[paragraph.index] for paragraph in labels.paragraphs},
            sampled=frozenset(span.index for span in labels.spans),
        )
        if repair.refused:
            print(
                f"{prefix}: REFUSED; nothing written. In these rows letters or digits differ from the "
                "document, which a repair never changes. Look at each one:"
            )
            for problem in repair.refused:
                print(f"  {problem}")
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        write_worksheet_csv(out, repair.worksheet)
        for change in repair.changes:
            print(f"  {change}")
        print(f"{prefix}: {len(repair.changes)} change(s) written to {out.name}; no label touched")
        worksheet, numbers_beside = repair.worksheet, None
    problems, notes = worksheet_problems(
        worksheet, prelabels=labels, texts=texts, numbers_beside=numbers_beside
    )
    for note in notes:
        print(f"  note: {note}")
    if problems:
        print(f"{prefix}: import would refuse this worksheet. {format_problems(problems)}")
        return 1
    corrected = import_worksheet(
        worksheet, prelabels=labels, texts=texts, corrected_by=ReviewerRole.OPERATOR, key=key
    )
    print(
        f"{prefix}: ready to import; {len(corrected.paragraphs)} rows checked, "
        f"{corrected.header.rows_changed_from_prelabel} labeled differently from the pre-labels"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--plan", type=Path, default=SAMPLING_PLAN_PATH)
    parser.add_argument("--labels-dir", type=Path, default=LABELS_DIRECTORY)
    parser.add_argument(
        "--rejections", type=Path, default=None, help="Defaults to rejections.json beside the manifest."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prelabel = commands.add_parser("prelabel", help="Seed PRELABELED label files from parser output.")
    prelabel.add_argument("digest", nargs="*", help="Keyed-digest prefixes; or --all.")
    prelabel.add_argument("--all", action="store_true")
    prelabel.add_argument(
        "--force", action="store_true", help="Overwrite a label file that is not PRELABELED."
    )

    worksheet = commands.add_parser("worksheet", help="Write a correction worksheet outside the repository.")
    worksheet.add_argument("digest", nargs="?", help="Keyed-digest prefix; or --all.")
    worksheet.add_argument(
        "--all",
        action="store_true",
        help="Write each missing worksheet of a PRELABELED file, and remove rejected files' worksheets.",
    )
    worksheet.add_argument("--out-dir", type=Path, required=True)

    opener = commands.add_parser("open", help="Open a file's .docx by keyed-digest prefix, printing no path.")
    opener.add_argument("digest")

    worksheet_help = "The worksheet: its .csv, or the .numbers file Numbers saves with Cmd+S."
    checker = commands.add_parser(
        "check", help="Run every check import runs and list every problem, writing no label."
    )
    checker.add_argument("digest")
    checker.add_argument("--worksheet", type=Path, required=True, help=worksheet_help)
    checker.add_argument(
        "--repair",
        action="store_true",
        help="First write a repaired worksheet to --out: the document's text restored and the marks "
        "carried onto it, emptied span cells filled, labels untouched.",
    )
    checker.add_argument("--out", type=Path, help="Where --repair writes the worksheet, as CSV.")

    importer = commands.add_parser("import", help="Read a corrected worksheet back as CORRECTED labels.")
    importer.add_argument("digest")
    importer.add_argument("--worksheet", type=Path, required=True, help=worksheet_help)
    importer.add_argument("--corrected-by", type=ReviewerRole, choices=list(ReviewerRole), required=True)

    review = commands.add_parser("mark-reviewed", help="Record the coach's end-to-end spot-check.")
    review.add_argument("digest")
    review.add_argument("--reviewer", type=ReviewerRole, choices=[ReviewerRole.COACH], required=True)

    args = parser.parse_args(argv)
    if args.command == "check" and args.repair != (args.out is not None):
        parser.error("check --repair writes to --out, and --out is only for --repair")
    if args.command == "check" and args.out is not None and args.out.suffix.lower() != ".csv":
        parser.error("--out names a .csv file")
    manifest = load_manifest(args.manifest)
    rejected = load_rejections(args.rejections or args.manifest.parent / "rejections.json").digests
    plan: SamplingPlan = load_sampling_plan(args.plan)
    key = require_key()

    if args.command == "open":
        return _open(_resolve(manifest, args.digest))
    if args.command == "worksheet" and args.all:
        return _all_worksheets(manifest, rejected, args.labels_dir, args.out_dir, key)
    if args.command == "worksheet" and not args.digest:
        parser.error("worksheet takes a digest prefix, or --all")

    if args.command == "prelabel":
        entries = list(manifest.entries) if args.all else [_resolve(manifest, p) for p in args.digest]
        for entry in entries:
            path = label_path_for(entry.digest, args.labels_dir)
            if (
                path.exists()
                and not args.force
                and load_label_file(path).header.status is not LabelStatus.PRELABELED
            ):
                print(
                    f"{entry.digest[:16]}: already corrected; left alone "
                    "(use --force to discard the correction)"
                )
                continue
            file_plan = plan.of(entry.digest)
            labels = prelabel_document(_document(entry, key), file_plan, plan.plan_id, key)
            # Pre-labels are the parser's opinion, and may break a rule a person's labels must keep
            # (a card with no cite, say). They are written anyway, to be corrected; import checks.
            write_label_file(labels, args.labels_dir, check_cards=False)
            print(
                f"{entry.digest[:16]}: {len(labels.paragraphs)} of {labels.header.paragraph_count} "
                f"paragraphs labeled ({file_plan.rate:.0%}, {len(file_plan.blocks)} block(s)), "
                f"{len(labels.cards)} cards, {len(labels.spans)} span rows, PRELABELED "
                f"(parser {DOCX_PARSER_VERSION})"
            )
        if args.all:
            _remove_rejected_prelabels(rejected, args.labels_dir)
        return 0

    entry = _resolve(manifest, args.digest)
    path = label_path_for(entry.digest, args.labels_dir)
    if not path.exists():
        raise SystemExit(f"{entry.digest[:16]}: no label file; run prelabel first")
    labels = load_label_file(path)

    if args.command == "worksheet":
        written = write_worksheet(labels, _document(entry, key), args.out_dir, key, entry.digest)
        print(
            f"{entry.digest[:16]}: worksheet with {len(labels.paragraphs)} rows "
            f"(of {labels.header.paragraph_count} paragraphs) written outside the repository"
        )
        print(f"  {written}")
        return 0

    if args.command == "check":
        return _check(entry, labels, args, key)

    if args.command == "import":
        worksheet_path = args.worksheet.expanduser()
        worksheet = _load_worksheet(entry.digest[:16], worksheet_path)
        if worksheet is None:
            return 1
        document = _document(entry, key)
        try:
            corrected = import_worksheet(
                worksheet,
                prelabels=labels,
                texts=[s.text for s in document.sections],
                corrected_by=args.corrected_by,
                key=key,
                numbers_beside=_numbers_beside(worksheet_path),
            )
        except WorksheetError as error:
            print(f"{entry.digest[:16]}: worksheet refused — {error}", file=sys.stderr)
            return 1
        write_label_file(corrected, args.labels_dir)
        print(
            f"{entry.digest[:16]}: CORRECTED by {args.corrected_by}; "
            f"{corrected.header.rows_changed_from_prelabel} of {len(corrected.paragraphs)} "
            "labeled rows changed from the pre-labels"
        )
        return 0

    if labels.header.status is LabelStatus.PRELABELED:
        raise SystemExit(
            f"{entry.digest[:16]}: still PRELABELED; it has to be corrected before it is reviewed"
        )
    reviewed = replace(
        labels,
        header=FileLabelHeader.model_validate(
            {**labels.header.model_dump(), "status": LabelStatus.COACH_REVIEWED, "reviewed_by": args.reviewer}
        ),
    )
    write_label_file(reviewed, args.labels_dir)
    print(f"{entry.digest[:16]}: COACH_REVIEWED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

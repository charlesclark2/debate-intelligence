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
    load_sampling_plan,
    validate_against_texts,
    write_label_file,
)
from tests.evals.parser.metrics import prediction_from_document  # noqa: E402

from debate_core.domain.debate_files import CardCompleteness, ParsedDocument  # noqa: E402
from debate_core.domain.style_profile import StructuralUnit  # noqa: E402
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION  # noqa: E402

__all__ = [
    "MARK_CLOSE",
    "MARK_OPEN",
    "WORKSHEET_COLUMNS",
    "WorksheetError",
    "import_worksheet",
    "is_sampled",
    "main",
    "parse_markup",
    "prelabel_document",
    "render_markup",
    "write_worksheet",
]

MARK_OPEN = "⟦"
MARK_CLOSE = "⟧"
WORKSHEET_COLUMNS = ("index", "checked", "unit", "card", "completeness", "text", "underline", "highlight")
SPAN_SAMPLE_FRACTION = 0.2


class WorksheetError(ValueError):
    """A worksheet that cannot become labels as it stands."""


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
                    underline=tuple(_merge(prediction.underline.get(section.element_index, ()))),
                    highlight=tuple(_merge(prediction.highlight.get(section.element_index, ()))),
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


def _merge(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort and join touching or overlapping ranges: underline and emphasis spans often abut."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# --------------------------------------------------------------------------------------------
# Span markup
# --------------------------------------------------------------------------------------------


def render_markup(text: str, ranges: Sequence[tuple[int, int]]) -> str:
    pieces: list[str] = []
    cursor = 0
    for start, end in ranges:
        pieces += [text[cursor:start], MARK_OPEN, text[start:end], MARK_CLOSE]
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def parse_markup(markup: str, text: str, *, row: int, column: str) -> tuple[tuple[int, int], ...]:
    """Read `⟦…⟧` markup back into ranges, and refuse it if the text underneath was changed."""
    ranges: list[tuple[int, int]] = []
    plain: list[str] = []
    start: int | None = None
    for character in markup:
        if character == MARK_OPEN:
            if start is not None:
                raise WorksheetError(f"row {row} {column}: {MARK_OPEN} opened twice")
            start = len(plain)
        elif character == MARK_CLOSE:
            if start is None:
                raise WorksheetError(f"row {row} {column}: {MARK_CLOSE} with no {MARK_OPEN}")
            if len(plain) > start:
                ranges.append((start, len(plain)))
            start = None
        else:
            plain.append(character)
    if start is not None:
        raise WorksheetError(f"row {row} {column}: {MARK_OPEN} never closed")
    if "".join(plain) != text:
        raise WorksheetError(f"row {row} {column}: the text under the markup was edited; only move the marks")
    return tuple(_merge(ranges))


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
    first_row_of_card: set[int] = set()
    seen_cards: set[int] = set()
    for paragraph in labels.paragraphs:
        if paragraph.card is not None and paragraph.card not in seen_cards:
            seen_cards.add(paragraph.card)
            first_row_of_card.add(paragraph.index)
    completeness = {card.card: card.completeness.value for card in labels.cards}

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{labels.digest[:16]}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(WORKSHEET_COLUMNS)
        for paragraph in labels.paragraphs:
            span = spans.get(paragraph.index)
            text = texts[paragraph.index]
            writer.writerow(
                [
                    paragraph.index,
                    "",
                    paragraph.unit.value,
                    "" if paragraph.card is None else paragraph.card,
                    completeness[paragraph.card] if paragraph.index in first_row_of_card else "",
                    text,
                    "" if span is None else render_markup(text, span.underline),
                    "" if span is None else render_markup(text, span.highlight),
                ]
            )
    return path


def import_worksheet(
    rows: Sequence[Mapping[str, str]],
    *,
    prelabels: LabelFile,
    texts: Sequence[str],
    corrected_by: ReviewerRole,
    key: bytes,
) -> LabelFile:
    """Turn a corrected worksheet into a `CORRECTED` label file, or say every reason it cannot.

    The rows are the sampling plan's labeled paragraphs, in order — not every paragraph of the
    file — so a row is checked against the index the plan expects at that position.
    """
    problems: list[str] = []
    expected_indices = [paragraph.index for paragraph in prelabels.paragraphs]
    if len(rows) != len(expected_indices):
        raise WorksheetError(
            f"the worksheet has {len(rows)} rows; the sampling plan labels {len(expected_indices)} "
            "paragraphs of this file"
        )
    sampled = {span.index for span in prelabels.spans}
    paragraphs: list[ParagraphLabel] = []
    spans: list[SpanLabel] = []
    completeness: dict[int, CardCompleteness] = {}
    for position, row in enumerate(rows):
        line = position + 2  # the header is row 1
        expected_index = expected_indices[position]
        try:
            index = int(row["index"])
        except (KeyError, ValueError):
            problems.append(f"row {line}: index is not a number")
            continue
        if index != expected_index:
            problems.append(
                f"row {line}: rows were reordered or removed (index {index}, expected {expected_index})"
            )
            continue
        text = texts[index]
        if not row.get("checked", "").strip():
            problems.append(f"row {line}: not marked checked")
        if row.get("text", "") != text:
            problems.append(f"row {line}: the text was edited; text is never edited to make a label fit")
        try:
            unit = StructuralUnit(row.get("unit", "").strip().upper())
        except ValueError:
            problems.append(f"row {line}: {row.get('unit')!r} is not a unit")
            continue
        card_cell = row.get("card", "").strip()
        card = int(card_cell) if card_cell.isdigit() else None
        if card_cell and card is None:
            problems.append(f"row {line}: card {card_cell!r} is not a number")
        completeness_cell = row.get("completeness", "").strip().upper()
        if completeness_cell:
            if card is None:
                problems.append(f"row {line}: completeness on a row that is not in a card")
            else:
                try:
                    value = CardCompleteness(completeness_cell)
                except ValueError:
                    problems.append(f"row {line}: {completeness_cell!r} is not a completeness")
                else:
                    if card in completeness and completeness[card] is not value:
                        problems.append(f"row {line}: card {card} is given two completeness values")
                    completeness[card] = value
        paragraphs.append(
            ParagraphLabel(
                index=index,
                length=len(text),
                text_digest=text_digest(text, key),
                unit=unit,
                card=card,
            )
        )
        if index in sampled:
            try:
                spans.append(
                    SpanLabel(
                        index=index,
                        underline=parse_markup(row.get("underline", ""), text, row=line, column="underline"),
                        highlight=parse_markup(row.get("highlight", ""), text, row=line, column="highlight"),
                    )
                )
            except WorksheetError as error:
                problems.append(str(error))
    for card in sorted({p.card for p in paragraphs if p.card is not None} - completeness.keys()):
        problems.append(f"card {card} has no completeness on any of its rows")
    numbered: dict[int, list[int]] = {}
    for paragraph in paragraphs:
        if paragraph.card is not None:
            numbered.setdefault(paragraph.card, []).append(paragraph.index)
    for card, indices in sorted(numbered.items()):
        if not _inside_one_block(prelabels.header.blocks, min(indices), max(indices)):
            problems.append(
                f"card {card} crosses a sampling-block edge; number only the cards that lie wholly "
                "inside one block, and leave the rest blank"
            )
    if problems:
        raise WorksheetError(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--plan", type=Path, default=SAMPLING_PLAN_PATH)
    parser.add_argument("--labels-dir", type=Path, default=LABELS_DIRECTORY)
    commands = parser.add_subparsers(dest="command", required=True)

    prelabel = commands.add_parser("prelabel", help="Seed PRELABELED label files from parser output.")
    prelabel.add_argument("digest", nargs="*", help="Keyed-digest prefixes; or --all.")
    prelabel.add_argument("--all", action="store_true")
    prelabel.add_argument(
        "--force", action="store_true", help="Overwrite a label file that is not PRELABELED."
    )

    worksheet = commands.add_parser("worksheet", help="Write a correction worksheet outside the repository.")
    worksheet.add_argument("digest")
    worksheet.add_argument("--out-dir", type=Path, required=True)

    importer = commands.add_parser("import", help="Read a corrected worksheet back as CORRECTED labels.")
    importer.add_argument("digest")
    importer.add_argument("--worksheet", type=Path, required=True)
    importer.add_argument("--corrected-by", type=ReviewerRole, choices=list(ReviewerRole), required=True)

    review = commands.add_parser("mark-reviewed", help="Record the coach's end-to-end spot-check.")
    review.add_argument("digest")
    review.add_argument("--reviewer", type=ReviewerRole, choices=[ReviewerRole.COACH], required=True)

    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    plan: SamplingPlan = load_sampling_plan(args.plan)
    key = require_key()

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

    if args.command == "import":
        document = _document(entry, key)
        with args.worksheet.expanduser().open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        try:
            corrected = import_worksheet(
                rows,
                prelabels=labels,
                texts=[s.text for s in document.sections],
                corrected_by=args.corrected_by,
                key=key,
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

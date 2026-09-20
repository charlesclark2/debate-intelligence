#!/usr/bin/env python3
"""Compare a debate .docx with its CardMirror round-trip and report what changed.

This is operator tooling for the CardMirror evaluation spike
(`plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml`). It is never
run in CI and nothing in `packages/` imports it. Its companion is
`scripts/cardmirror-roundtrip/roundtrip.mjs`, which produces the round-tripped files
and the manifest this script reads.

What it compares, per paragraph:

* **paragraph text** - the visible text of the paragraph, runs concatenated;
* **structural unit** - pocket / hat / block / tag / analytic / undertag / body,
  derived from the paragraph style id (or `w:outlineLvl` for files that do not use
  Verbatim styles);
* **underline, highlight, bold, cite and font-size spans** - character ranges over
  the paragraph text rather than runs, because any editor is free to split and merge
  runs without changing a document's meaning.

Underline is deliberately compared by *effect*, not encoding. Verbatim and CardMirror
both underline body text with the `StyleUnderline` character style and structural text
(tags, analytics, headings) with a direct `<w:u>`, and CardMirror normalizes a run that
arrives with the wrong one. A swap that leaves the underlined range identical is
recorded as a normalization, not a difference.

Privacy: the aggregate summary identifies files by a short sha256 prefix of the
original bytes and never contains document text, file names or paths. Differences carry
indices, offsets, counts and formatting values only. See the "forbidden" list in the
task spec.

Usage:

    python scripts/compare_docx_roundtrip.py --manifest <roundtrip-manifest.json> \\
        --output <summary.json>
    python scripts/compare_docx_roundtrip.py --pair <original.docx> <roundtripped.docx> \\
        --category team
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docx
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def w(tag: str) -> str:
    """Qualify a WordprocessingML tag name, e.g. ``w("pStyle")``."""
    return f"{{{W_NS}}}{tag}"


# Paragraph style ids, normalized (lower-cased, spaces and hyphens removed), mapped to
# the structural unit names this platform uses. Verbatim, Advanced Verbatim and
# CardMirror all write the same ids; the spellings with spaces show up in files that
# came out of Google Docs or a wiki-to-docx conversion.
PARAGRAPH_STYLE_UNITS: dict[str, str] = {
    "heading1": "pocket",
    "heading2": "hat",
    "heading3": "block",
    "heading4": "tag",
    "analytic": "analytic",
    "undertag": "undertag",
}

# `w:outlineLvl` fallback for files with no recognizable paragraph style. Outline level
# is zero-based: level 0 is Heading 1.
OUTLINE_LEVEL_UNITS: dict[int, str] = {0: "pocket", 1: "hat", 2: "block", 3: "tag"}

# Character style ids, normalized, mapped to the mark they carry.
CITE_STYLES = frozenset({"style13ptbold", "cite", "citechar"})
NAMED_UNDERLINE_STYLES = frozenset({"styleunderline", "underline", "underlinechar"})

# Units whose text is bold by default, so a run with no explicit `<w:b>` still reads as
# bold. Comparing effective bold rather than the literal element keeps a round-trip that
# drops a redundant `<w:b/>` on a tag from being reported as a loss.
BOLD_BY_DEFAULT_UNITS = frozenset({"pocket", "hat", "block", "tag", "analytic"})

# Ancestors whose runs are deleted or moved-away text. Word keeps them in the file;
# CardMirror drops them on import, and so do we.
REVISION_DROP_TAGS = frozenset({w("del"), w("moveFrom")})

DIMENSIONS = ("underline", "highlight", "bold", "cite", "font_size")


@dataclass(frozen=True)
class RunFormatting:
    """The formatting of one run, read straight off its `w:rPr`."""

    character_style: str | None
    bold: bool | None
    underline: str | None
    highlight: str | None
    font_size_half_points: int | None

    def is_underlined(self) -> bool:
        if self.underline is not None and self.underline != "none":
            return True
        return self.character_style in NAMED_UNDERLINE_STYLES

    def underline_encoding(self) -> str | None:
        """How this run's underline is written.

        `named_style` is the `StyleUnderline` character style, `direct` is a `<w:u>` with
        no character style, and `both` is a run carrying each. CardMirror's exporter
        writes `both` in body slots — the named style is what Verbatim's macros key on,
        the direct `<w:u>` makes the run render underlined even where the style is
        missing — so the three are distinguished rather than collapsed.
        """
        direct = self.underline is not None and self.underline != "none"
        named = self.character_style in NAMED_UNDERLINE_STYLES
        if direct and named:
            return "both"
        if direct:
            return "direct"
        if named:
            return "named_style"
        return None

    def is_cite(self) -> bool:
        return self.character_style in CITE_STYLES

    def is_bold(self, structural_unit: str) -> bool:
        if self.is_cite():
            return True
        if self.bold is not None:
            return self.bold
        return structural_unit in BOLD_BY_DEFAULT_UNITS


@dataclass(frozen=True)
class RunSnapshot:
    text: str
    formatting: RunFormatting


@dataclass(frozen=True)
class ParagraphSnapshot:
    structural_unit: str
    style_id: str | None
    runs: tuple[RunSnapshot, ...]

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    def spans(self, dimension: str) -> tuple[tuple[int, int, Any], ...]:
        """Character ranges over `text` carrying one formatting value, adjacent equals merged."""
        spans: list[list[Any]] = []
        offset = 0
        for run in self.runs:
            if not run.text:
                continue
            value = self._value(run.formatting, dimension)
            end = offset + len(run.text)
            if spans and spans[-1][2] == value:
                spans[-1][1] = end
            else:
                spans.append([offset, end, value])
            offset = end
        return tuple((start, end, value) for start, end, value in spans if value not in (False, None))

    def _value(self, formatting: RunFormatting, dimension: str) -> Any:
        if dimension == "underline":
            return formatting.is_underlined()
        if dimension == "highlight":
            return formatting.highlight
        if dimension == "bold":
            return formatting.is_bold(self.structural_unit)
        if dimension == "cite":
            return formatting.is_cite()
        if dimension == "font_size":
            return formatting.font_size_half_points
        if dimension == "underline_encoding":
            return formatting.underline_encoding()
        raise ValueError(f"unknown dimension: {dimension}")


@dataclass(frozen=True)
class Difference:
    """One thing the round-trip changed. `detail` never holds document text."""

    category: str
    paragraph_index: int | None
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "paragraphIndex": self.paragraph_index,
            "detail": self.detail,
        }


@dataclass
class FileComparison:
    sha256_prefix: str
    file_category: str
    original_paragraphs: int
    roundtripped_paragraphs: int
    differences: list[Difference] = field(default_factory=list)
    normalizations: list[Difference] = field(default_factory=list)
    error: str | None = None

    @property
    def status(self) -> str:
        if self.error is not None:
            return "error"
        return "differences" if self.differences else "clean"

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "sha256Prefix": self.sha256_prefix,
            "fileCategory": self.file_category,
            "status": self.status,
            "originalParagraphs": self.original_paragraphs,
            "roundtrippedParagraphs": self.roundtripped_paragraphs,
            "differences": [difference.as_dict() for difference in self.differences],
            "normalizations": [note.as_dict() for note in self.normalizations],
        }
        if self.error is not None:
            record["error"] = self.error
        return record


def normalize_style_id(style_id: str | None) -> str | None:
    if style_id is None:
        return None
    return style_id.replace(" ", "").replace("-", "").replace("_", "").lower()


def structural_unit_for(style_id: str | None, outline_level: int | None) -> str:
    normalized = normalize_style_id(style_id)
    if normalized in PARAGRAPH_STYLE_UNITS:
        return PARAGRAPH_STYLE_UNITS[normalized]
    if outline_level is not None and outline_level in OUTLINE_LEVEL_UNITS:
        return OUTLINE_LEVEL_UNITS[outline_level]
    return "body"


def _attr_is_on(element: etree._Element | None) -> bool | None:
    """Read an OOXML on/off element: absent is None, `w:val="0"`/`"false"` is False."""
    if element is None:
        return None
    value = element.get(w("val"))
    return value not in ("0", "false", "off")


def _is_dropped_revision(run: etree._Element, paragraph: etree._Element) -> bool:
    ancestor = run.getparent()
    while ancestor is not None and ancestor is not paragraph:
        if ancestor.tag in REVISION_DROP_TAGS:
            return True
        ancestor = ancestor.getparent()
    return False


def _run_text(run: etree._Element) -> str:
    pieces: list[str] = []
    for child in run:
        if child.tag == w("t"):
            pieces.append(child.text or "")
        elif child.tag == w("tab"):
            pieces.append("\t")
        elif child.tag in (w("br"), w("cr")):
            pieces.append("\n")
        elif child.tag == w("noBreakHyphen"):
            pieces.append("-")
    return "".join(pieces)


def _run_formatting(run: etree._Element) -> RunFormatting:
    properties = run.find(w("rPr"))
    if properties is None:
        return RunFormatting(None, None, None, None, None)
    style_element = properties.find(w("rStyle"))
    underline_element = properties.find(w("u"))
    highlight_element = properties.find(w("highlight"))
    size_element = properties.find(w("sz"))
    size: int | None = None
    if size_element is not None:
        try:
            size = int(size_element.get(w("val"), ""))
        except ValueError:
            size = None
    highlight = None if highlight_element is None else highlight_element.get(w("val"))
    return RunFormatting(
        character_style=normalize_style_id(
            None if style_element is None else style_element.get(w("val"))
        ),
        bold=_attr_is_on(properties.find(w("b"))),
        underline=None if underline_element is None else (underline_element.get(w("val")) or "single"),
        highlight=None if highlight in (None, "none") else highlight,
        font_size_half_points=size,
    )


def _paragraph_style(paragraph: etree._Element) -> tuple[str | None, int | None]:
    properties = paragraph.find(w("pPr"))
    if properties is None:
        return None, None
    style_element = properties.find(w("pStyle"))
    style_id = None if style_element is None else style_element.get(w("val"))
    outline_element = properties.find(w("outlineLvl"))
    outline_level: int | None = None
    if outline_element is not None:
        try:
            outline_level = int(outline_element.get(w("val"), ""))
        except ValueError:
            outline_level = None
    return style_id, outline_level


def _snapshot_paragraph(paragraph: etree._Element) -> ParagraphSnapshot:
    style_id, outline_level = _paragraph_style(paragraph)
    runs = tuple(
        RunSnapshot(text=_run_text(run), formatting=_run_formatting(run))
        for run in paragraph.iter(w("r"))
        if not _is_dropped_revision(run, paragraph)
    )
    return ParagraphSnapshot(
        structural_unit=structural_unit_for(style_id, outline_level),
        style_id=style_id,
        runs=runs,
    )


def read_paragraphs(path: Path, *, keep_empty_body: bool = False) -> list[ParagraphSnapshot]:
    """Every paragraph of a .docx in document order, table cells included.

    Empty unstyled paragraphs are dropped by default: Verbatim files are full of them as
    spacing, editors add and remove them freely, and keeping them makes every comparison
    noise. Empty *headings* are kept — an empty Heading 1 is how debate files separate
    two documents packed into one file.
    """
    document = docx.Document(str(path))
    body = document.element.body
    snapshots: list[ParagraphSnapshot] = []
    for paragraph in body.iter(w("p")):
        snapshot = _snapshot_paragraph(paragraph)
        if not keep_empty_body and not snapshot.text.strip() and snapshot.structural_unit == "body":
            continue
        snapshots.append(snapshot)
    return snapshots


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def sha256_prefix(path: Path, length: int = 8) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:length]


def _align(
    original: Sequence[ParagraphSnapshot], roundtripped: Sequence[ParagraphSnapshot]
) -> Iterator[tuple[int | None, int | None]]:
    """Pair up paragraphs by collapsed text, so one inserted paragraph does not
    misalign everything after it."""
    matcher = difflib.SequenceMatcher(
        a=[collapse_whitespace(p.text) for p in original],
        b=[collapse_whitespace(p.text) for p in roundtripped],
        autojunk=False,
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                yield i1 + offset, j1 + offset
        elif tag == "replace":
            for offset in range(max(i2 - i1, j2 - j1)):
                left = i1 + offset if i1 + offset < i2 else None
                right = j1 + offset if j1 + offset < j2 else None
                yield left, right
        elif tag == "delete":
            for index in range(i1, i2):
                yield index, None
        elif tag == "insert":
            for index in range(j1, j2):
                yield None, index


def compare_paragraphs(
    index: int, original: ParagraphSnapshot, roundtripped: ParagraphSnapshot
) -> tuple[list[Difference], list[Difference]]:
    differences: list[Difference] = []
    normalizations: list[Difference] = []

    if original.structural_unit != roundtripped.structural_unit:
        differences.append(
            Difference(
                "structural_unit",
                index,
                {"original": original.structural_unit, "roundtripped": roundtripped.structural_unit},
            )
        )

    original_text = collapse_whitespace(original.text)
    roundtripped_text = collapse_whitespace(roundtripped.text)
    if original_text != roundtripped_text:
        differences.append(
            Difference(
                "paragraph_text",
                index,
                {
                    "originalLength": len(original_text),
                    "roundtrippedLength": len(roundtripped_text),
                    "firstDifferingOffset": _first_difference(original_text, roundtripped_text),
                },
            )
        )
        # Character offsets no longer line up, so per-span comparison would be noise.
        return differences, normalizations

    if original.text != roundtripped.text:
        normalizations.append(
            Difference(
                "whitespace_normalized",
                index,
                {"originalLength": len(original.text), "roundtrippedLength": len(roundtripped.text)},
            )
        )

    for dimension in DIMENSIONS:
        original_spans = original.spans(dimension)
        roundtripped_spans = roundtripped.spans(dimension)
        if original_spans != roundtripped_spans:
            differences.append(
                Difference(
                    f"{dimension}_span",
                    index,
                    {
                        "original": [list(span) for span in original_spans],
                        "roundtripped": [list(span) for span in roundtripped_spans],
                    },
                )
            )

    original_encoding = original.spans("underline_encoding")
    roundtripped_encoding = roundtripped.spans("underline_encoding")
    if original_encoding != roundtripped_encoding and original.spans("underline") == roundtripped.spans(
        "underline"
    ):
        normalizations.append(
            Difference(
                "underline_encoding_changed",
                index,
                {
                    "original": [list(span) for span in original_encoding],
                    "roundtripped": [list(span) for span in roundtripped_encoding],
                },
            )
        )

    return differences, normalizations


def _first_difference(left: str, right: str) -> int:
    for offset, (a, b) in enumerate(zip(left, right, strict=False)):
        if a != b:
            return offset
    return min(len(left), len(right))


def compare_documents(
    original: Sequence[ParagraphSnapshot], roundtripped: Sequence[ParagraphSnapshot]
) -> tuple[list[Difference], list[Difference]]:
    differences: list[Difference] = []
    normalizations: list[Difference] = []
    for original_index, roundtripped_index in _align(original, roundtripped):
        if original_index is None:
            assert roundtripped_index is not None
            differences.append(
                Difference(
                    "paragraph_added",
                    roundtripped_index,
                    {"structuralUnit": roundtripped[roundtripped_index].structural_unit},
                )
            )
            continue
        if roundtripped_index is None:
            differences.append(
                Difference(
                    "paragraph_removed",
                    original_index,
                    {"structuralUnit": original[original_index].structural_unit},
                )
            )
            continue
        paragraph_differences, paragraph_normalizations = compare_paragraphs(
            original_index, original[original_index], roundtripped[roundtripped_index]
        )
        differences.extend(paragraph_differences)
        normalizations.extend(paragraph_normalizations)
    return differences, normalizations


def compare_file(original_path: Path, roundtripped_path: Path, file_category: str) -> FileComparison:
    prefix = sha256_prefix(original_path)
    try:
        original = read_paragraphs(original_path)
        roundtripped = read_paragraphs(roundtripped_path)
    except Exception as error:  # noqa: BLE001 - one unreadable file must not stop the run
        return FileComparison(prefix, file_category, 0, 0, error=f"{type(error).__name__}: {error}")
    differences, normalizations = compare_documents(original, roundtripped)
    return FileComparison(
        sha256_prefix=prefix,
        file_category=file_category,
        original_paragraphs=len(original),
        roundtripped_paragraphs=len(roundtripped),
        differences=differences,
        normalizations=normalizations,
    )


def summarize(comparisons: Iterable[FileComparison], *, cardmirror_commit: str | None = None) -> dict[str, Any]:
    """Aggregate per file category. Contains no document text, file names or paths."""
    comparisons = list(comparisons)
    categories: dict[str, dict[str, Any]] = {}
    for comparison in comparisons:
        bucket = categories.setdefault(
            comparison.file_category,
            {"files": 0, "clean": 0, "withDifferences": 0, "errors": 0, "differencesByCategory": {}},
        )
        bucket["files"] += 1
        if comparison.status == "clean":
            bucket["clean"] += 1
        elif comparison.status == "error":
            bucket["errors"] += 1
        else:
            bucket["withDifferences"] += 1
        counts: dict[str, int] = bucket["differencesByCategory"]
        for difference in comparison.differences:
            counts[difference.category] = counts.get(difference.category, 0) + 1
    return {
        "generatedAt": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "cardmirrorCommit": cardmirror_commit,
        "totals": {
            "files": len(comparisons),
            "clean": sum(1 for c in comparisons if c.status == "clean"),
            "withDifferences": sum(1 for c in comparisons if c.status == "differences"),
            "errors": sum(1 for c in comparisons if c.status == "error"),
        },
        "categories": categories,
        "files": [comparison.as_dict() for comparison in comparisons],
    }


def _pairs_from_manifest(manifest_path: Path) -> tuple[list[tuple[Path, Path, str]], str | None]:
    manifest = json.loads(manifest_path.read_text())
    base = manifest_path.parent
    pairs: list[tuple[Path, Path, str]] = []
    for entry in manifest.get("files", []):
        if entry.get("status") != "ok":
            continue
        original = Path(entry["originalPath"])
        roundtripped = Path(entry["roundtrippedPath"])
        pairs.append(
            (
                original if original.is_absolute() else base / original,
                roundtripped if roundtripped.is_absolute() else base / roundtripped,
                entry.get("fileCategory", "unknown"),
            )
        )
    return pairs, manifest.get("cardmirrorCommit")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--manifest",
        type=Path,
        help="roundtrip-manifest.json written by scripts/cardmirror-roundtrip/roundtrip.mjs",
    )
    source.add_argument(
        "--pair",
        nargs=2,
        metavar=("ORIGINAL", "ROUNDTRIPPED"),
        type=Path,
        help="compare a single pair of files",
    )
    parser.add_argument(
        "--category",
        default="unknown",
        help="file category for --pair (team, caselist, caselist-non-verbatim, caselist-wiki, camp)",
    )
    parser.add_argument("--output", type=Path, help="write the aggregate JSON summary here")
    arguments = parser.parse_args(argv)

    if arguments.manifest is not None:
        pairs, cardmirror_commit = _pairs_from_manifest(arguments.manifest)
    else:
        original, roundtripped = arguments.pair
        pairs = [(original, roundtripped, arguments.category)]
        cardmirror_commit = None

    comparisons = [compare_file(original, roundtripped, category) for original, roundtripped, category in pairs]
    summary = summarize(comparisons, cardmirror_commit=cardmirror_commit)
    rendered = json.dumps(summary, indent=2)
    if arguments.output is not None:
        arguments.output.write_text(rendered + "\n")
    else:
        print(rendered)

    totals = summary["totals"]
    print(
        f"{totals['files']} file(s): {totals['clean']} clean, "
        f"{totals['withDifferences']} with differences, {totals['errors']} error(s)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

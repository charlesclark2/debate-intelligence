"""Synthetic PDFs for the PDF extractor (`v1-e04-t04-content-extraction`).

Nothing here is a real publication. The journal, the article, its authors and its figures are
invented, so the fixture can be committed and redistributed without a licence question. The PDF is
written by the small writer below, with no PDF library, so the bytes are the same on every machine
and the layout is exactly what this file says it is.

`uv run python tests/fixtures/extraction/build_pdf_fixtures.py` rewrites `journal-article.pdf` beside
this file. `test_pdf_extractor.py` checks that the committed file is what this builder produces, so
the two cannot drift; the expected output, `journal-article.expected.json`, is written by hand from
the lines below (working agreement 6), never from the extractor.

## The journal article

Three US Letter pages (612 x 792 pt), Helvetica in WinAnsiEncoding, one text-showing operation per
line, every line starting at the left margin (x = 72) unless it opens a paragraph, which is indented
(x = 90). Headings, the title and the byline are set apart by a larger gap instead.

* Page 1 opens with a masthead line that appears on no other page, so it is body text.
* Pages 2 and 3 open with the running header `RUNNING_HEADER`.
* Every page ends with the running footer `RUNNING_FOOTER` and then `Page N of 3`.
* Page 2's first body line is the short heading `2. Methods`, page 3's third line is
  `4. Conclusion` and its last body line is a one-off date line, all inside the three-line edge
  zones a running header or footer is looked for in. Each appears once, so each is body text.
* The paragraph that ends page 2 continues on page 3, broken inside `envi-|ronmental`.

## The line-end hyphens

Thirteen lines end in a hyphen, each followed by a line that continues the same paragraph. Which
are broken words and which are real hyphens is known here, because this file is where the words
were written:

| Break | Really | Evidence elsewhere in the body |
|---|---|---|
| `extinc-` / `tion` | broken word | `extinction` twice |
| `de-` / `extinction` | compound | `De-extinction` twice |
| `well-` / `intentioned` | compound | none |
| `conser-` / `vation` | broken word | `conservation` twice |
| `2019-` / `2024` | year range | (digits) |
| `long-` / `term` | compound | `long-term` twice |
| `co-` / `operation` | either spelling | `cooperation` once and `co-operation` once |
| `bio` + soft hyphen / `diversity` | broken word | (U+00AD, a discretionary hyphen) |
| `popu-` / `lations` | broken word | `populations` three times |
| `cost-` / `effective` | compound | `cost-effective` once |
| `resur-` / `rection` | broken word | none |
| `envi-` / `ronmental` (across pages 2 and 3) | broken word | `environmental` once |
| `Okonkwo-` / `Hale` | compound name | `Okonkwo-Hale` once, in the byline |

A refusal fixture is the same writer with `encrypted=True`, which adds a standard security handler
dictionary to the trailer. The page content is left readable on purpose: the extractor must refuse
on the marker alone, before it reads a word.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PAGE_WIDTH: Final = 612
PAGE_HEIGHT: Final = 792
LEFT_MARGIN: Final = 72.0
PARAGRAPH_INDENT: Final = 90.0

RUNNING_HEADER: Final = "Okonkwo-Hale and Lindqvist · Moral Hazard and the Return of Lost Species"
RUNNING_FOOTER: Final = "Synthetic open-access test fixture, CC BY 4.0, not a real publication"
MASTHEAD: Final = "Journal of Synthetic Conservation Studies · Volume 12 (2026)"

JOURNAL_ARTICLE_FILE: Final = Path(__file__).with_name("journal-article.pdf")


@dataclass(frozen=True)
class DrawnLine:
    """One line of text as the writer draws it: its words, where its baseline starts, its size."""

    text: str
    x: float
    y: float
    size: float


# The page layout: (kind, text) in drawing order. `gap` lines are set apart by extra space; `indent`
# lines open a paragraph at PARAGRAPH_INDENT; `line` lines continue at the left margin.
_PAGE_ONE: Final = (
    ("masthead", MASTHEAD),
    ("title", "Moral Hazard and the Return of Lost Species"),
    ("gap", "R. Okonkwo-Hale and T. Lindqvist"),
    ("heading", "Abstract"),
    ("indent", "De-extinction promises to reverse losses that conservation once treated as"),
    ("line", "final. We ask whether the promise creates a moral hazard: if extinction can"),
    ("line", "be undone, the urgency of protecting living populations may fade. We find"),
    ("line", "that the cost-effective path for most agencies remains habitat protection,"),
    ("line", "and that long-term funding for revival programs competes directly with it."),
    ("heading", "1. Introduction"),
    ("indent", "The idea of bringing back the woolly mammoth or the passenger pigeon has"),
    ("line", "moved from fiction to grant proposals. Proponents describe the work as extinc-"),
    ("line", "tion reversed, a correction of past harm. Critics answer that every dollar"),
    ("line", "spent on revival is a dollar not spent on species still here, and that de-"),
    ("line", "extinction risks becoming a well-"),
    ("line", "intentioned distraction from the slower work of conser-"),
    ("line", "vation. Between 2019-"),
    ("line", "2024 the three largest revival programs raised more than the annual budgets of"),
    ("line", "most regional wildlife agencies combined."),
)

_PAGE_TWO: Final = (
    ("header", RUNNING_HEADER),
    ("heading", "2. Methods"),
    ("indent", "We compared funding records for revival programs with records for habitat"),
    ("line", "protection in the same regions. Where the two drew on the same donors, we"),
    ("line", "counted a dollar for revival as a dollar withdrawn from protection, which"),
    ("line", "overstates the competition; a long-"),
    ("line", "term view would also count donors who give only because revival is exciting."),
    ("line", "Agencies that relied on co-"),
    ("line", "operation with private funders reported the sharpest declines, and the bio­"),
    ("line", "diversity they protect is concentrated in small popu-"),
    ("line", "lations that cannot wait for a revived species to arrive."),
    ("heading", "3. Results"),
    ("indent", "Protecting habitat remained the cost-"),
    ("line", "effective choice in every region we studied. The populations that recovered"),
    ("line", "fastest were those whose habitat was protected before decline set in, and the"),
    ("line", "cooperation of landowners mattered more than any single grant. Some agencies"),
    ("line", "describe their partnerships as co-operation between equals; others call it"),
    ("line", "dependence. Either way, the resur-"),
    ("line", "rection of a lost species does nothing for the envi-"),
)

_PAGE_THREE: Final = (
    ("header", RUNNING_HEADER),
    ("line", "ronmental conditions that caused its loss."),
    ("heading", "4. Conclusion"),
    ("indent", "De-extinction is not a substitute for conservation. The long-term health of"),
    ("line", "living populations depends on environmental protection that is funded before"),
    ("line", "a species is lost, not after. A well-funded revival program is no answer to"),
    ("line", "an extinction that cheaper protection could have prevented."),
    ("heading", "Acknowledgments"),
    ("indent", "We thank the agencies that shared their records, and colleagues of Okonkwo-"),
    ("line", "Hale at the regional office for comments on an early draft."),
    ("gap", "Received 3 March 2026; accepted 9 June 2026."),
)

_BODY_SIZE: Final = 10.0
_LINE_STEP: Final = 14.0
_GAP: Final = 10.0
_FOOTER_Y: Final = 52.0
_PAGE_NUMBER_Y: Final = 40.0
_TOP_Y: Final = 760.0
_FIRST_BODY_Y: Final = 730.0


def lay_out(page: Sequence[tuple[str, str]], page_number: int, page_count: int) -> tuple[DrawnLine, ...]:
    """Place one page's lines, adding the running footer and the page number at the bottom."""
    lines: list[DrawnLine] = []
    y = _FIRST_BODY_Y
    for kind, text in page:
        if kind in {"masthead", "header"}:
            lines.append(DrawnLine(text, LEFT_MARGIN, _TOP_Y, 8.0))
            continue
        if kind == "title":
            y -= 2 * _GAP
            lines.append(DrawnLine(text, LEFT_MARGIN, y, 16.0))
            y -= 22.0
            continue
        if kind in {"gap", "heading"}:
            y -= _GAP
            lines.append(DrawnLine(text, LEFT_MARGIN, y, 11.0 if kind == "heading" else _BODY_SIZE))
            y -= _LINE_STEP + (_GAP if kind == "gap" else 0)
            continue
        x = PARAGRAPH_INDENT if kind == "indent" else LEFT_MARGIN
        lines.append(DrawnLine(text, x, y, _BODY_SIZE))
        y -= _LINE_STEP
    lines.append(DrawnLine(RUNNING_FOOTER, LEFT_MARGIN, _FOOTER_Y, 8.0))
    lines.append(DrawnLine(f"Page {page_number} of {page_count}", LEFT_MARGIN, _PAGE_NUMBER_Y, 8.0))
    return tuple(lines)


def journal_article_pages() -> tuple[tuple[DrawnLine, ...], ...]:
    """The three pages of the journal article, laid out."""
    pages = (_PAGE_ONE, _PAGE_TWO, _PAGE_THREE)
    return tuple(lay_out(page, number, len(pages)) for number, page in enumerate(pages, start=1))


def journal_article_pdf(*, encrypted: bool = False) -> bytes:
    """The journal article as PDF bytes."""
    return pdf_bytes(journal_article_pages(), encrypted=encrypted)


def plain_pages_pdf(page_count: int) -> bytes:
    """`page_count` pages of one sentence each, different on every page: the page-count limit's sample."""
    pages = [
        (DrawnLine(f"Sentence {number} of a long synthetic report.", LEFT_MARGIN, _FIRST_BODY_Y, _BODY_SIZE),)
        for number in range(1, page_count + 1)
    ]
    return pdf_bytes(pages)


def long_compressed_page_pdf(*, keep_compressed_bytes: int | None = None) -> bytes:
    """One page of 50 distinct lines in a FlateDecode stream that expands to about 3,700 bytes.

    What the decompression limit is tested with, and, cut short, a truncated download.
    """
    lines = tuple(
        DrawnLine(
            f"Line {index} of a long page, about topic {index * 7919 % 1000}.",
            LEFT_MARGIN,
            740.0 - 14 * index,
            10.0,
        )
        for index in range(50)
    )
    return pdf_bytes([lines], compressed=True, keep_compressed_bytes=keep_compressed_bytes)


# --------------------------------------------------------------------------------------------
# The writer: PDF 1.4, one standard Type 1 font, uncompressed content streams.
# --------------------------------------------------------------------------------------------


def _pdf_string(text: str) -> bytes:
    """`text` as a PDF literal string in WinAnsiEncoding (cp1252 for every character used here)."""
    encoded = text.encode("cp1252")
    escaped = encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + escaped + b")"


def _content_stream(lines: Sequence[DrawnLine]) -> bytes:
    operations = [
        b"BT /F1 %s Tf %s %s Td " % (_number(line.size), _number(line.x), _number(line.y))
        + _pdf_string(line.text)
        + b" Tj ET"
        for line in lines
    ]
    return b"\n".join(operations) + b"\n"


def _number(value: float) -> bytes:
    return (f"{value:.2f}".rstrip("0").rstrip(".")).encode("ascii")


def pdf_bytes(
    pages: Sequence[Sequence[DrawnLine]],
    *,
    encrypted: bool = False,
    compressed: bool = False,
    keep_compressed_bytes: int | None = None,
) -> bytes:
    """A PDF drawing each page's lines, deterministic for the same input.

    `compressed` writes each content stream with FlateDecode; `keep_compressed_bytes` then cuts each
    compressed stream to that many bytes, which is how a truncated download is simulated.
    """
    objects: list[bytes] = []
    font_id = 3
    first_page_id = 4
    page_ids = [first_page_id + 2 * index for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = b" ".join(b"%d 0 R" % page_id for page_id in page_ids)
    objects.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(pages))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for page_id, lines in zip(page_ids, pages, strict=True):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] " % (PAGE_WIDTH, PAGE_HEIGHT)
            + b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>" % (font_id, page_id + 1)
        )
        stream = _content_stream(lines)
        if not compressed:
            objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
            continue
        packed = zlib.compress(stream, 9)[:keep_compressed_bytes]
        objects.append(
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(packed) + packed + b"\nendstream"
        )
    encrypt_id = None
    if encrypted:
        objects.append(
            b"<< /Filter /Standard /V 1 /R 2 /P -3904 /O <"
            + b"28BF4E5E4E758A41" * 4
            + b"> /U <"
            + b"C4F4A9B2E7D5E5A6" * 4
            + b"> >>"
        )
        encrypt_id = len(objects)

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_offset = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        output += b"%010d 00000 n \n" % offset
    trailer = b"<< /Size %d /Root 1 0 R" % (len(objects) + 1)
    if encrypt_id is not None:
        trailer += (
            b" /Encrypt %d 0 R /ID [<00112233445566778899AABBCCDDEEFF> <00112233445566778899AABBCCDDEEFF>]"
            % (encrypt_id)
        )
    output += b"trailer\n" + trailer + b" >>\nstartxref\n%d\n%%%%EOF\n" % xref_offset
    return bytes(output)


def main() -> None:
    JOURNAL_ARTICLE_FILE.write_bytes(journal_article_pdf())
    print(f"wrote {JOURNAL_ARTICLE_FILE.name} ({JOURNAL_ARTICLE_FILE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

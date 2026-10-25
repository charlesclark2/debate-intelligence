"""From a PDF's positioned lines to paragraphs: the rules that decide what is body text (v1-e04-t04).

The PDF adapter (`debate_core.integrations.pdf_extractor`) reads each page's lines, with where each
starts and its type size, in the order the page draws them. Everything after that is decided here,
without a PDF library, so every rule can be tested and broken on purpose with lines written by hand.
The rules are the PM's rulings of 2026-10-25 on the session's proposal, recorded in
`docs/session-reports/v1-e04-t04-content-extraction.md`.

## Running headers, footers and page numbers

Only the :data:`EDGE_ZONE_LINES` lines nearest the top of a page and the same number nearest its
bottom are ever candidates, by position on the page. Of those:

* a line whose exact text (whitespace collapsed) is in an edge zone on two or more pages is a
  running header or footer;
* then, the outermost line left at each end of a page is a page number when its *whole* text is a
  page-number form (a bare integer, `Page n`, `n of m`, `Page n of m`, `- n -`, or a lowercase roman
  numeral) and its number advances with the page: the same offset from the page's position in the
  file on two or more pages. `Table 2` and `Table 3` are not forms, so captions stay.

Everything else stays, however short. A line that appears once is body text, and a one-page document
loses nothing. Each removed line is returned as a :class:`~debate_core.retrieval.extraction.RemovedLine`.

## Joining a line that ends in a hyphen

Lines of one paragraph are joined with a space, except where a line ends in a hyphen or dash straight
after a non-space character: there they are joined with no space, the line-end character is kept or
dropped, and the join is returned as a :class:`~debate_core.retrieval.extraction.LineJoin`:

1. a soft hyphen (U+00AD) is dropped;
2. a dash, or a hyphen without a letter on both sides (`2019-|2024`), is kept;
3. between letters, the body text elsewhere decides. Both spellings, `left-right` and `leftright`,
   are counted as whole words, case-insensitively, leaving out the fragments on either side of any
   line-end break (only spellings that are not themselves broken count). The hyphenated form alone
   keeps the hyphen; the joined form alone drops it; neither or both keeps it, as UNDETERMINED.

Keeping is the answer whenever the document cannot tell, because a kept hyphen loses no printed
character, and a dropped one can turn `cost-effective` into a word the author never wrote.

## Paragraphs

A paragraph starts at a line set in a different type size, after a vertical gap larger than 1.3
times the page's median line spacing, or at a line indented by more than half its type size from
the line above. At a page break, or where a line moves up the page (the next column), the paragraph
carries on unless the line before ended a sentence, the type size changes or the new line is
indented from the one after it. Paragraph breaks move only whitespace, never a word.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from debate_core.retrieval.extraction import (
    JoinDecision,
    LineEndCharacter,
    LineJoin,
    PageEdge,
    RemovalReason,
    RemovedLine,
)

__all__ = ["EDGE_ZONE_LINES", "PdfPageText", "PdfTextLayout", "PositionedLine", "lay_out_pages"]

EDGE_ZONE_LINES: Final = 3
"""How many lines at each end of a page can be a running header, footer or page number."""

MINIMUM_PAGES: Final = 2
"""On how many pages a running line, or a page number's offset, must appear."""

_GAP_FACTOR: Final = 1.3
_INDENT_FACTOR: Final = 0.5
_SIZE_TOLERANCE: Final = 0.5

_JOINING_CHARACTERS: Final[dict[str, LineEndCharacter]] = {
    "-": "-",
    "‐": "‐",
    "­": "­",
    "–": "–",
    "—": "—",
}
_DASHES: Final = frozenset({"–", "—"})
_WORD: Final = re.compile(r"[^\W\d_]+(?:['’\-‐‑][^\W\d_]+)*")
_WORD_AT_END: Final = re.compile(_WORD.pattern + r"\Z")
_SENTENCE_ENDS: Final = frozenset(".!?:")
_CLOSERS: Final = "\"')]”’"

_ARABIC_FORMS: Final = (
    re.compile(r"([0-9]+)"),
    re.compile(r"page\s+([0-9]+)", re.IGNORECASE),
    re.compile(r"([0-9]+)\s+of\s+[0-9]+", re.IGNORECASE),
    re.compile(r"page\s+([0-9]+)\s+of\s+[0-9]+", re.IGNORECASE),
    re.compile(r"[-–]\s*([0-9]+)\s*[-–]"),
)
_ROMAN_FORM: Final = re.compile(r"[ivxlcdm]+")
_ROMAN_VALUES: Final = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)


@dataclass(frozen=True, slots=True)
class PositionedLine:
    """One line of a page as the PDF draws it."""

    text: str
    x: float
    """Where the line starts, in points from the page's left edge."""
    y: float
    """Its baseline, in points from the page's bottom edge (PDF's own orientation)."""
    font_size: float
    """The type size it is set in, in points."""


@dataclass(frozen=True, slots=True)
class PdfPageText:
    """A page's lines in the order the page draws them, which is the order they are read in."""

    page_number: int
    """The page's position in the file, counting from 1; never the number printed on it."""
    lines: tuple[PositionedLine, ...]


@dataclass(frozen=True, slots=True)
class PdfTextLayout:
    """The body text of a PDF, and the record of every line left out and every hyphen join."""

    paragraphs: tuple[str, ...]
    line_joins: tuple[LineJoin, ...]
    removed_lines: tuple[RemovedLine, ...]
    kept_characters: int
    """Characters on the body lines, before they were joined."""
    removed_characters: int
    """Characters on the removed lines."""


@dataclass(frozen=True, slots=True)
class _Line:
    """A non-blank line, trimmed, with the page and the place on it that it came from."""

    page_number: int
    index: int
    text: str
    x: float
    y: float
    size: float


def lay_out_pages(pages: Sequence[PdfPageText]) -> PdfTextLayout:
    """Remove running headers, footers and page numbers, then build paragraphs from what is left."""
    lines_by_page = [
        [
            _Line(page.page_number, index, line.text.strip(), line.x, line.y, line.font_size)
            for index, line in enumerate(page.lines)
            if line.text.strip()
        ]
        for page in pages
    ]
    removals = _running_lines(lines_by_page)
    removals |= _page_numbers(lines_by_page, removals)
    body = [
        line
        for page_lines in lines_by_page
        for line in page_lines
        if (line.page_number, line.index) not in removals
    ]
    removed_lines = tuple(removals[key] for key in sorted(removals))

    evidence = _spellings(body)
    paragraphs: list[str] = []
    joins: list[LineJoin] = []
    for paragraph_lines in _paragraph_lines(body):
        text, paragraph_joins = _join_lines(paragraph_lines, len(paragraphs), evidence)
        paragraphs.append(text)
        joins += paragraph_joins
    return PdfTextLayout(
        paragraphs=tuple(paragraphs),
        line_joins=tuple(joins),
        removed_lines=removed_lines,
        kept_characters=sum(len(line.text) for line in body),
        removed_characters=sum(len(line.text) for line in removed_lines),
    )


# --------------------------------------------------------------------------------------------
# Running headers, footers and page numbers
# --------------------------------------------------------------------------------------------

type _LineKey = tuple[int, int]
"""(page number, index on the page): one line, wherever it ends up."""


def _edge_zones(page_lines: Sequence[_Line]) -> dict[int, PageEdge]:
    """The lines in a page's edge zones, by index, each with the edge it is nearer to."""
    from_top = sorted(page_lines, key=lambda line: (-line.y, line.index))
    from_bottom = sorted(page_lines, key=lambda line: (line.y, -line.index))
    top_rank = {line.index: rank for rank, line in enumerate(from_top[:EDGE_ZONE_LINES])}
    bottom_rank = {line.index: rank for rank, line in enumerate(from_bottom[:EDGE_ZONE_LINES])}
    zones = {index: PageEdge.BOTTOM for index in bottom_rank}
    zones |= {
        index: PageEdge.TOP
        for index, rank in top_rank.items()
        if rank <= bottom_rank.get(index, EDGE_ZONE_LINES)
    }
    return zones


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _running_lines(lines_by_page: Sequence[Sequence[_Line]]) -> dict[_LineKey, RemovedLine]:
    pages_with: defaultdict[str, set[int]] = defaultdict(set)
    candidates: list[tuple[_Line, PageEdge]] = []
    for page_lines in lines_by_page:
        by_index = {line.index: line for line in page_lines}
        for index, edge in _edge_zones(page_lines).items():
            candidates.append((by_index[index], edge))
            pages_with[_collapsed(by_index[index].text)].add(by_index[index].page_number)
    reasons = {PageEdge.TOP: RemovalReason.RUNNING_HEADER, PageEdge.BOTTOM: RemovalReason.RUNNING_FOOTER}
    return {
        (line.page_number, line.index): RemovedLine(
            page_number=line.page_number, edge=edge, reason=reasons[edge], text=line.text
        )
        for line, edge in candidates
        if len(pages_with[_collapsed(line.text)]) >= MINIMUM_PAGES
    }


def _page_numbers(
    lines_by_page: Sequence[Sequence[_Line]], already_removed: dict[_LineKey, RemovedLine]
) -> dict[_LineKey, RemovedLine]:
    offsets: defaultdict[tuple[str, int], list[tuple[_Line, PageEdge]]] = defaultdict(list)
    for page_lines in lines_by_page:
        zones = _edge_zones(page_lines)
        left = [line for line in page_lines if (line.page_number, line.index) not in already_removed]
        if not left:
            continue
        outermost = {
            max(left, key=lambda line: (line.y, -line.index)),
            min(left, key=lambda line: (line.y, -line.index)),
        }
        for line in outermost:
            number = _page_number_form(line.text)
            if line.index in zones and number is not None:
                system, value = number
                offsets[(system, value - line.page_number)].append((line, zones[line.index]))
    return {
        (line.page_number, line.index): RemovedLine(
            page_number=line.page_number, edge=edge, reason=RemovalReason.PAGE_NUMBER, text=line.text
        )
        for found in offsets.values()
        if len({line.page_number for line, _ in found}) >= MINIMUM_PAGES
        for line, edge in found
    }


def _page_number_form(text: str) -> tuple[str, int] | None:
    """`("arabic", n)` or `("roman", n)` when the whole of `text` is a page-number form."""
    for form in _ARABIC_FORMS:
        match = form.fullmatch(text)
        if match is not None:
            return "arabic", int(match[1])
    if _ROMAN_FORM.fullmatch(text):
        value = _roman_value(text)
        if value is not None:
            return "roman", value
    return None


def _roman_value(numeral: str) -> int | None:
    """The value of a lowercase roman numeral written the standard way, or None (`iiii`, `vx`)."""
    value, rest = 0, numeral
    for amount, symbol in _ROMAN_VALUES:
        while rest.startswith(symbol):
            value, rest = value + amount, rest[len(symbol) :]
    return value if not rest and _roman(value) == numeral else None


def _roman(value: int) -> str:
    written = ""
    for amount, symbol in _ROMAN_VALUES:
        count, value = divmod(value, amount)
        written += symbol * count
    return written


# --------------------------------------------------------------------------------------------
# Paragraphs
# --------------------------------------------------------------------------------------------


def _paragraph_lines(body: Sequence[_Line]) -> list[list[_Line]]:
    steps = _median_line_steps(body)
    paragraphs: list[list[_Line]] = []
    for position, line in enumerate(body):
        if position == 0:
            paragraphs.append([line])
            continue
        following = body[position + 1] if position + 1 < len(body) else None
        if _starts_paragraph(body[position - 1], line, following, steps):
            paragraphs.append([line])
        else:
            paragraphs[-1].append(line)
    return paragraphs


def _median_line_steps(body: Sequence[_Line]) -> dict[int, float]:
    steps: defaultdict[int, list[float]] = defaultdict(list)
    for above, below in pairwise(body):
        if above.page_number == below.page_number and below.y < above.y:
            steps[below.page_number].append(above.y - below.y)
    return {page_number: statistics.median(found) for page_number, found in steps.items()}


def _starts_paragraph(previous: _Line, line: _Line, following: _Line | None, steps: dict[int, float]) -> bool:
    if abs(line.size - previous.size) > _SIZE_TOLERANCE:
        return True
    if line.page_number == previous.page_number and line.y < previous.y:
        gap = previous.y - line.y
        return gap > _GAP_FACTOR * steps[line.page_number] or line.x - previous.x > _INDENT_FACTOR * line.size
    # A new page, or a move up the page into the next column.
    indented = (
        following is not None
        and following.page_number == line.page_number
        and following.y < line.y
        and line.x - following.x > _INDENT_FACTOR * line.size
    )
    return indented or _ends_sentence(previous.text)


def _ends_sentence(text: str) -> bool:
    return text.rstrip(_CLOSERS)[-1:] in _SENTENCE_ENDS


# --------------------------------------------------------------------------------------------
# Joining lines
# --------------------------------------------------------------------------------------------


def _ends_in_join(text: str) -> bool:
    """Whether a line ends in a hyphen or dash with no space before it."""
    return len(text) >= 2 and text[-1] in _JOINING_CHARACTERS and not text[-2].isspace()


def _spelling(word: str) -> str:
    return word.casefold().replace("‐", "-").replace("‑", "-")


def _spellings(body: Sequence[_Line]) -> Counter[str]:
    """Every whole word in the body text, case-folded, except the fragments beside a line-end break."""
    counts: Counter[str] = Counter()
    for position, line in enumerate(body):
        words = list(_WORD.finditer(line.text))
        broken_here = _ends_in_join(line.text)
        broken_above = position > 0 and _ends_in_join(body[position - 1].text)
        for number, word in enumerate(words):
            if broken_here and number == len(words) - 1 and word.end() == len(line.text) - 1:
                continue
            if broken_above and number == 0 and word.start() == 0:
                continue
            counts[_spelling(word[0])] += 1
    return counts


def _join_lines(
    lines: Sequence[_Line], paragraph_index: int, evidence: Counter[str]
) -> tuple[str, list[LineJoin]]:
    text = lines[0].text
    joins: list[LineJoin] = []
    for above, below in pairwise(lines):
        if not _ends_in_join(above.text):
            text = f"{text} {below.text}"
            continue
        character = _JOINING_CHARACTERS[above.text[-1]]
        decision, hyphenated, joined = _decide(above.text, below.text, evidence)
        kept = decision not in {JoinDecision.SOFT_HYPHEN, JoinDecision.JOINED_FORM_IN_DOCUMENT}
        offset = len(text) - 1
        text = text[:offset] + (character if kept else "") + below.text
        joins.append(
            LineJoin(
                paragraph_index=paragraph_index,
                offset=offset,
                page_number=above.page_number,
                character=character,
                hyphen_kept=kept,
                decision=decision,
                hyphenated_form_count=hyphenated,
                joined_form_count=joined,
            )
        )
    return text, joins


def _decide(above: str, below: str, evidence: Counter[str]) -> tuple[JoinDecision, int, int]:
    """The rule for one line-end character: the decision, and the two spellings' counts."""
    character = above[-1]
    if character == "­":
        return JoinDecision.SOFT_HYPHEN, 0, 0
    left = _WORD_AT_END.search(above[:-1])
    right = _WORD.match(below)
    if character in _DASHES or left is None or right is None:
        return JoinDecision.NOT_A_WORD_BREAK, 0, 0
    hyphenated = evidence[_spelling(f"{left[0]}-{right[0]}")]
    joined = evidence[_spelling(f"{left[0]}{right[0]}")]
    if hyphenated and not joined:
        return JoinDecision.HYPHENATED_FORM_IN_DOCUMENT, hyphenated, joined
    if joined and not hyphenated:
        return JoinDecision.JOINED_FORM_IN_DOCUMENT, hyphenated, joined
    return JoinDecision.UNDETERMINED, hyphenated, joined

"""From a PDF's positioned lines to paragraphs (v1-e04-t04). SKELETON: removes and decides nothing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from debate_core.retrieval.extraction import LineJoin, RemovedLine

__all__ = ["EDGE_ZONE_LINES", "PdfPageText", "PdfTextLayout", "PositionedLine", "lay_out_pages"]

EDGE_ZONE_LINES: Final = 3


@dataclass(frozen=True, slots=True)
class PositionedLine:
    text: str
    x: float
    y: float
    font_size: float


@dataclass(frozen=True, slots=True)
class PdfPageText:
    page_number: int
    lines: tuple[PositionedLine, ...]


@dataclass(frozen=True, slots=True)
class PdfTextLayout:
    paragraphs: tuple[str, ...]
    line_joins: tuple[LineJoin, ...]
    removed_lines: tuple[RemovedLine, ...]
    kept_characters: int
    removed_characters: int


def lay_out_pages(pages: Sequence[PdfPageText]) -> PdfTextLayout:
    paragraphs = tuple(
        " ".join(line.text.strip() for line in page.lines if line.text.strip())
        for page in pages
        if any(line.text.strip() for line in page.lines)
    )
    return PdfTextLayout(paragraphs, (), (), sum(len(paragraph) for paragraph in paragraphs), 0)

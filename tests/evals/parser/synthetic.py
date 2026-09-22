"""An invented debate file and its hand-written labels, for testing the evaluation harness.

The real evaluation files never reach CI (`caselist-data-use.md`), so the harness itself is tested
on a file built here from invented text. Its labels are written **by hand from the paragraphs
below**, not produced by running the parser: they say what each paragraph is because this file
was written to be exactly that (working agreements §6).

The school, the tag lines and the cites are fictional.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.style_profile import StructuralUnit
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

from tests.evals.parser.labels_schema import (
    CardLabel,
    FileLabelHeader,
    LabelFile,
    LabelStatus,
    ParagraphLabel,
    ReviewerRole,
    SpanLabel,
    text_sha256,
)

__all__ = ["SyntheticFile", "build_synthetic_file"]

OPENING = "Grid operators warn that "
UNDERLINED = "reserve margins fall below safe levels"
CLOSING = " within two summers."
SECOND_BODY = "Moratoria shift load to older plants and raise outage risk."


def _cite(short: str, tail: str) -> str:
    return paragraph_xml(run_xml(short, character_style="Style13ptBold") + run_xml(tail))


def _evidence() -> str:
    return paragraph_xml(
        run_xml(OPENING, half_points=16)
        + run_xml(UNDERLINED, character_style="StyleUnderline", underline="single", highlight="cyan")
        + run_xml(CLOSING, half_points=16)
    )


#: (paragraph markup, text, unit, card) in body order, written together so they cannot drift apart.
_PARAGRAPHS: tuple[tuple[str, str, StructuralUnit, int | None], ...] = (
    (paragraph_xml(run_xml("Maple Grove Negative"), style="Heading1"), "Maple Grove Negative",
     StructuralUnit.POCKET, None),
    (paragraph_xml(run_xml("Grid Reliability"), style="Heading2"), "Grid Reliability", StructuralUnit.HAT, None),
    (paragraph_xml(run_xml("AT: Reserve Margin Turn"), style="Heading3"), "AT: Reserve Margin Turn",
     StructuralUnit.BLOCK, None),
    (paragraph_xml(run_xml("Moratoria collapse the reserve margin"), style="Heading4"),
     "Moratoria collapse the reserve margin", StructuralUnit.TAG, 0),
    (_cite("Okonkwo 26", ", Grid Analyst, Fictional Energy Review"),
     "Okonkwo 26, Grid Analyst, Fictional Energy Review", StructuralUnit.CITE, 0),
    (_evidence(), OPENING + UNDERLINED + CLOSING, StructuralUnit.EVIDENCE, 0),
    (paragraph_xml(""), "", StructuralUnit.OTHER, None),
    (paragraph_xml(run_xml("Their turn is non-unique"), style="Heading4"), "Their turn is non-unique",
     StructuralUnit.ANALYTIC, None),
    (paragraph_xml(run_xml("Older plants fail first"), style="Heading4"), "Older plants fail first",
     StructuralUnit.TAG, 1),
    (_cite("Lindqvist 25", ", Professor, Invented University"), "Lindqvist 25, Professor, Invented University",
     StructuralUnit.CITE, 1),
    (paragraph_xml(run_xml(SECOND_BODY, character_style="StyleUnderline", underline="single")), SECOND_BODY,
     StructuralUnit.EVIDENCE, 1),
)  # fmt: skip


@dataclass(frozen=True)
class SyntheticFile:
    content: bytes
    labels: LabelFile

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def build_synthetic_file(status: LabelStatus = LabelStatus.CORRECTED) -> SyntheticFile:
    """The invented file, and labels for it in the given review status."""
    content = build_docx("".join(markup for markup, _, _, _ in _PARAGRAPHS))
    sha256 = hashlib.sha256(content).hexdigest()
    paragraphs = tuple(
        ParagraphLabel(index=index, length=len(text), text_sha256=text_sha256(text), unit=unit, card=card)
        for index, (_, text, unit, card) in enumerate(_PARAGRAPHS)
    )
    underlined = (len(OPENING), len(OPENING) + len(UNDERLINED))
    labels = LabelFile(
        header=FileLabelHeader(
            sha256=sha256,
            paragraph_count=len(paragraphs),
            status=status,
            prelabel_parser_version="hand-written",
            corrected_by=None if status is LabelStatus.PRELABELED else ReviewerRole.OPERATOR,
        ),
        paragraphs=paragraphs,
        cards=(
            CardLabel(card=0, completeness=CardCompleteness.FULL),
            CardLabel(card=1, completeness=CardCompleteness.FULL),
        ),
        spans=(
            SpanLabel(index=5, underline=(underlined,), highlight=(underlined,)),
            SpanLabel(index=10, underline=((0, len(SECOND_BODY)),)),
            SpanLabel(index=3),
        ),
    )
    return SyntheticFile(content=content, labels=labels)

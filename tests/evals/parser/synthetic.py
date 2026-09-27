"""An invented debate file and its hand-written labels, for testing the evaluation harness.

The real evaluation files never reach CI (`caselist-data-use.md`), so the harness itself is tested
on a file built here from invented text. Its labels are written **by hand from the paragraphs
below**, not produced by running the parser: they say what each paragraph is because this file
was written to be exactly that (working agreements §6).

The school, the tag lines and the cites are fictional.

The digests are keyed like the real ones, under a fixed test key: nothing here is corpus content,
so the key is a constant rather than a secret, and the shape stays the same as production's.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.evals.parser.digests import keyed_digest, text_digest
from tests.evals.parser.labels_schema import (
    Block,
    CardLabel,
    FileLabelHeader,
    LabelFile,
    LabelStatus,
    ParagraphLabel,
    ReviewerRole,
    SpanLabel,
)

from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.style_profile import StructuralUnit
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

__all__ = ["TEST_DIGEST_KEY", "SyntheticFile", "build_synthetic_file"]

#: Not a secret: this file is invented, so its digests protect nothing. Fixed so tests are stable.
TEST_DIGEST_KEY = bytes.fromhex("5e" * 32)

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
    (
        paragraph_xml(run_xml("Maple Grove Negative"), style="Heading1"),
        "Maple Grove Negative",
        StructuralUnit.POCKET,
        None,
    ),
    (
        paragraph_xml(run_xml("Grid Reliability"), style="Heading2"),
        "Grid Reliability",
        StructuralUnit.HAT,
        None,
    ),
    (
        paragraph_xml(run_xml("AT: Reserve Margin Turn"), style="Heading3"),
        "AT: Reserve Margin Turn",
        StructuralUnit.BLOCK,
        None,
    ),
    (
        paragraph_xml(run_xml("Moratoria collapse the reserve margin"), style="Heading4"),
        "Moratoria collapse the reserve margin",
        StructuralUnit.TAG,
        0,
    ),
    (
        _cite("Okonkwo 26", ", Grid Analyst, Fictional Energy Review"),
        "Okonkwo 26, Grid Analyst, Fictional Energy Review",
        StructuralUnit.CITE,
        0,
    ),
    (_evidence(), OPENING + UNDERLINED + CLOSING, StructuralUnit.EVIDENCE, 0),
    (paragraph_xml(""), "", StructuralUnit.OTHER, None),
    (
        paragraph_xml(run_xml("Their turn is non-unique"), style="Heading4"),
        "Their turn is non-unique",
        StructuralUnit.ANALYTIC,
        None,
    ),
    (
        paragraph_xml(run_xml("Older plants fail first"), style="Heading4"),
        "Older plants fail first",
        StructuralUnit.TAG,
        1,
    ),
    (
        _cite("Lindqvist 25", ", Professor, Invented University"),
        "Lindqvist 25, Professor, Invented University",
        StructuralUnit.CITE,
        1,
    ),
    (
        paragraph_xml(run_xml(SECOND_BODY, character_style="StyleUnderline", underline="single")),
        SECOND_BODY,
        StructuralUnit.EVIDENCE,
        1,
    ),
)


@dataclass(frozen=True)
class SyntheticFile:
    content: bytes
    labels: LabelFile
    key: bytes = TEST_DIGEST_KEY

    @property
    def digest(self) -> str:
        return keyed_digest(self.content, self.key)


def build_synthetic_file(
    status: LabelStatus = LabelStatus.CORRECTED,
    *,
    key: bytes = TEST_DIGEST_KEY,
    blocks: tuple[Block, ...] | None = None,
    plan_id: str = "",
) -> SyntheticFile:
    """The invented file, and labels for it in the given review status.

    `blocks` labels only part of the file, the way the sampling plan does outside the PR subset;
    the default labels all eleven paragraphs, as the PR subset is labeled.
    """
    content = build_docx("".join(markup for markup, _, _, _ in _PARAGRAPHS))
    digest = keyed_digest(content, key)
    labeled = blocks if blocks is not None else ((0, len(_PARAGRAPHS) - 1),)
    indices = [index for first, last in labeled for index in range(first, last + 1)]
    paragraphs = tuple(
        ParagraphLabel(
            index=index,
            length=len(_PARAGRAPHS[index][1]),
            text_digest=text_digest(_PARAGRAPHS[index][1], key),
            unit=_PARAGRAPHS[index][2],
            card=_PARAGRAPHS[index][3],
        )
        for index in indices
    )
    whole_cards = {
        card
        for card in {p.card for p in paragraphs if p.card is not None}
        if all(any(first <= p.index <= last for first, last in labeled) for p in paragraphs if p.card == card)
        and len([i for i, (_, _, _, c) in enumerate(_PARAGRAPHS) if c == card])
        == len([p for p in paragraphs if p.card == card])
    }
    paragraphs = tuple(
        p if p.card in whole_cards else p.model_copy(update={"card": None}) for p in paragraphs
    )
    underlined = (len(OPENING), len(OPENING) + len(UNDERLINED))
    spans = tuple(
        span
        for span in (
            SpanLabel(index=3),
            SpanLabel(index=5, underline=(underlined,), highlight=(underlined,)),
            SpanLabel(index=10, underline=((0, len(SECOND_BODY)),)),
        )
        if span.index in indices
    )
    labels = LabelFile(
        header=FileLabelHeader(
            digest=digest,
            paragraph_count=len(_PARAGRAPHS),
            blocks=labeled,
            plan_id=plan_id,
            status=status,
            prelabel_parser_version="hand-written",
            corrected_by=None if status is LabelStatus.PRELABELED else ReviewerRole.OPERATOR,
        ),
        paragraphs=paragraphs,
        cards=tuple(CardLabel(card=card, completeness=CardCompleteness.FULL) for card in sorted(whole_cards)),
        spans=spans,
    )
    return SyntheticFile(content=content, labels=labels, key=key)

#!/usr/bin/env python3
"""Build the synthetic structural `.docx` fixtures for the debate file parser.

`tests/fixtures/debate_files/structural/` holds one small document per template family the style
survey measured — a team file cut in Verbatim, a caselist upload that has been through CardMirror,
a camp file, an opencaselist wiki conversion, a Google Docs export, a hand-formatted file, and the
shapes that must *not* come out as cards. Each one is generated here and committed with a
`.expected.json` beside it.

**The expectations are written by hand in this file and never produced by running the parser.**
A fixture whose answers came from the code under test proves nothing; these are written from the
rules the profile and the parser document, and a disagreement is a finding either way.

    uv run python scripts/generate_structural_fixtures.py

Every string in here is invented. There is no real evidence, no real citation, no real cite tail
and no real team in any fixture, and there will not be: see the directory's `MANIFEST.md` for why
the repository holds no real or scrubbed debate files at all, and `v1-e31-t05-parser-eval` for
where real-file accuracy is measured instead.

Owned by `v1-e31-t03-debate-docx-parser`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "debate_core" / "src"))

from debate_core.domain.debate_files import CardCompleteness  # noqa: E402
from debate_core.domain.style_profile import (  # noqa: E402
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
)
from debate_core.evidence.style_profile_loader import load_style_profile  # noqa: E402
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION  # noqa: E402
from debate_core.testing.docx_builder import (  # noqa: E402
    DEFAULT_STYLE_DEFINITIONS,
    build_docx,
    build_styles_xml,
    paragraph_xml,
    run_xml,
)

FIXTURE_DIRECTORY: Final = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "structural"

VERBATIM = StyleMatchSource.VERBATIM
ALIAS = StyleMatchSource.VERBATIM_ALIAS
HEURISTIC = StyleMatchSource.HEURISTIC


# --------------------------------------------------------------------------------------------
# The fixture description
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureParagraph:
    """One paragraph, and what the parser is expected to make of it."""

    xml: str
    text: str
    unit: StructuralUnit
    rule_id: str
    match_source: StyleMatchSource
    section_path: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class FixtureCard:
    """One card the parser is expected to assemble, and where it came from."""

    tag: str
    short_cite: str | None
    full_cite: str
    evidence_text: str
    completeness: CardCompleteness
    section_path: tuple[str, ...] = ()
    undertag: str = ""
    element_range: tuple[int, int] = (0, 0)
    underlined_text: tuple[str, ...] = ()
    """The exact characters each UNDERLINE span must select, in offset order."""


@dataclass(frozen=True)
class StructuralFixture:
    """One fixture file: the family it stands for, what is in it, and what it should parse as."""

    filename: str
    family: str
    corpus: str
    summary: str
    paragraphs: tuple[FixtureParagraph, ...]
    cards: tuple[FixtureCard, ...] = ()
    style_definitions: Sequence[tuple[str, str, str, str | None]] = DEFAULT_STYLE_DEFINITIONS
    extra_parts: Mapping[str, str] = field(default_factory=dict)
    warnings_contain: tuple[str, ...] = ()


# --------------------------------------------------------------------------------------------
# Invented text, shared between fixtures so a reader can see what changed between them
# --------------------------------------------------------------------------------------------

POCKET_TEXT: Final = "Data Centre Moratorium Negative"
HAT_TEXT: Final = "Grid Reliability"
BLOCK_TEXT: Final = "AT: Reserve Margin Turn"
TAG_TEXT: Final = "Data centre demand collapses the reserve margin"

SHORT_CITE: Final = "Okonkwo 26"
CITE_TAIL: Final = (
    " (Adaeze Okonkwo, Professor of Energy Policy, invented for this fixture), Reserve Margins "
    "Under Load Growth, Journal of Grid Studies, 14 March 2026."
)
FULL_CITE: Final = SHORT_CITE + CITE_TAIL

BODY_OPENING: Final = "Grid operators in the region reported that demand from new data centres rose "
BODY_UNDERLINED: Final = "faster than any other load category last year"
BODY_CLOSING: Final = (
    ", and the increase outpaced every scenario the utility had planned against, leaving the "
    "reserve margin thinner than at any point in the past decade."
)
BODY_TEXT: Final = BODY_OPENING + BODY_UNDERLINED + BODY_CLOSING


def verbatim_body_paragraph(*, dual_underline: bool = False) -> str:
    """A card body: shrunk lead-in, an underlined and highlighted middle, shrunk tail.

    `dual_underline` writes the `StyleUnderline` character style *and* a direct `<w:u>` on the
    same run, which is what CardMirror emits on export. 63% of the surveyed corpus has been
    through CardMirror, so that is the common encoding rather than an edge case.
    """
    return paragraph_xml(
        run_xml(BODY_OPENING, half_points=16)
        + run_xml(
            BODY_UNDERLINED,
            character_style="StyleUnderline",
            underline="single" if dual_underline else None,
            highlight="cyan",
            half_points=22,
        )
        + run_xml(BODY_CLOSING, half_points=16)
    )


def cardmirror_heading(text: str, style: str, bookmark_id: int) -> str:
    """A heading carrying CardMirror's `pmd-heading-` bookmark, as its exporter writes one."""
    return (
        "<w:p>"
        f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
        f'<w:bookmarkStart w:id="{bookmark_id}" w:name="pmd-heading-{bookmark_id:08x}"/>'
        f"{run_xml(text)}"
        f'<w:bookmarkEnd w:id="{bookmark_id}"/>'
        "</w:p>"
    )


# --------------------------------------------------------------------------------------------
# The fixtures
# --------------------------------------------------------------------------------------------


def team_verbatim_file() -> StructuralFixture:
    """The `verbatim` family: 74% of the team corpus. Every unit carries its own style."""
    return StructuralFixture(
        filename="team-verbatim-file.docx",
        family="verbatim",
        corpus="team",
        summary=(
            "A card cut the ordinary way in Verbatim: pocket, hat, block, tag, cite and body, each "
            "resolving from its own style or, for the cite, from its cite character style. The "
            "shape 276 of 374 team files in the survey have."
        ),
        paragraphs=(
            FixtureParagraph(
                xml=paragraph_xml(run_xml(POCKET_TEXT), style="Heading1"),
                text=POCKET_TEXT,
                unit=StructuralUnit.POCKET,
                rule_id="verbatim-style-id:Heading1",
                match_source=VERBATIM,
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(HAT_TEXT), style="Heading2"),
                text=HAT_TEXT,
                unit=StructuralUnit.HAT,
                rule_id="verbatim-style-id:Heading2",
                match_source=VERBATIM,
                section_path=(POCKET_TEXT,),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(BLOCK_TEXT), style="Heading3"),
                text=BLOCK_TEXT,
                unit=StructuralUnit.BLOCK,
                rule_id="verbatim-style-id:Heading3",
                match_source=VERBATIM,
                section_path=(POCKET_TEXT, HAT_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(TAG_TEXT), style="Heading4"),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="verbatim-style-id:Heading4",
                match_source=VERBATIM,
                section_path=(POCKET_TEXT, HAT_TEXT, BLOCK_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(SHORT_CITE, character_style="Style13ptBold") + run_xml(CITE_TAIL)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=ALIAS,
                section_path=(POCKET_TEXT, HAT_TEXT, BLOCK_TEXT, TAG_TEXT),
                note="Verbatim gives a cite no paragraph style; its cite character style finds it.",
            ),
            FixtureParagraph(
                xml=verbatim_body_paragraph(),
                text=BODY_TEXT,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(POCKET_TEXT, HAT_TEXT, BLOCK_TEXT, TAG_TEXT),
                note="A card body carries no paragraph style either; its markup is what finds it.",
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=BODY_TEXT,
                completeness=CardCompleteness.FULL,
                section_path=(POCKET_TEXT, HAT_TEXT, BLOCK_TEXT),
                element_range=(3, 5),
                underlined_text=(BODY_UNDERLINED,),
            ),
        ),
    )


def cardmirror_caselist_upload() -> StructuralFixture:
    """The `cardmirror` family: 78% of the caselist corpus, 63% of the whole survey."""
    return StructuralFixture(
        filename="cardmirror-caselist-upload.docx",
        family="cardmirror",
        corpus="caselist",
        summary=(
            "A disclosure that has been through CardMirror: `pmd-heading-` bookmarks on the "
            "headings, and both underline encodings written on every body run. This is the most "
            "common shape in the whole corpus, not an edge case, and it is the one a reader that "
            "counts the two encodings separately doubles."
        ),
        paragraphs=(
            FixtureParagraph(
                xml=cardmirror_heading(POCKET_TEXT, "Heading1", 1),
                text=POCKET_TEXT,
                unit=StructuralUnit.POCKET,
                rule_id="verbatim-style-id:Heading1",
                match_source=VERBATIM,
                note="The bookmark contributes no text and no formatting.",
            ),
            FixtureParagraph(
                xml=cardmirror_heading(BLOCK_TEXT, "Heading3", 2),
                text=BLOCK_TEXT,
                unit=StructuralUnit.BLOCK,
                rule_id="verbatim-style-id:Heading3",
                match_source=VERBATIM,
                section_path=(POCKET_TEXT,),
            ),
            FixtureParagraph(
                xml=cardmirror_heading(TAG_TEXT, "Heading4", 3),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="verbatim-style-id:Heading4",
                match_source=VERBATIM,
                section_path=(POCKET_TEXT, BLOCK_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(SHORT_CITE, character_style="Style13ptBold") + run_xml(CITE_TAIL)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=ALIAS,
                section_path=(POCKET_TEXT, BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=verbatim_body_paragraph(dual_underline=True),
                text=BODY_TEXT,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(POCKET_TEXT, BLOCK_TEXT, TAG_TEXT),
                note="`StyleUnderline` and a direct `<w:u>` on one run are one underline.",
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=BODY_TEXT,
                completeness=CardCompleteness.FULL,
                section_path=(POCKET_TEXT, BLOCK_TEXT),
                element_range=(2, 4),
                underlined_text=(BODY_UNDERLINED,),
            ),
        ),
    )


def cardmirror_camp_file() -> StructuralFixture:
    """The camp corpus: 68% of it is `cardmirror`, and camp files stack many tags under one block."""
    second_tag = "Reserve margins are already below the planning standard"
    second_cite_short = "Ferreira 25"
    second_cite = second_cite_short + " (Journal of Grid Studies, 2 November 2025)."
    second_body_opening = "The regional planning authority's own filings show that "
    second_body_underlined = "three of five zones fell below the target margin"
    second_body_closing = " in the last planning cycle."
    second_body = second_body_opening + second_body_underlined + second_body_closing
    return StructuralFixture(
        filename="cardmirror-camp-file.docx",
        family="cardmirror",
        corpus="camp",
        summary=(
            "A camp release: one block with two cards stacked under it, the shape 75 of 110 camp "
            "files in the survey have. What it holds down is that a second tag closes the first "
            "card rather than extending it, and that both cards keep the same section path."
        ),
        paragraphs=(
            FixtureParagraph(
                xml=cardmirror_heading(BLOCK_TEXT, "Heading3", 11),
                text=BLOCK_TEXT,
                unit=StructuralUnit.BLOCK,
                rule_id="verbatim-style-id:Heading3",
                match_source=VERBATIM,
            ),
            FixtureParagraph(
                xml=cardmirror_heading(TAG_TEXT, "Heading4", 12),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="verbatim-style-id:Heading4",
                match_source=VERBATIM,
                section_path=(BLOCK_TEXT,),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(SHORT_CITE, character_style="Style13ptBold") + run_xml(CITE_TAIL)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=ALIAS,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=verbatim_body_paragraph(dual_underline=True),
                text=BODY_TEXT,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=cardmirror_heading(second_tag, "Heading4", 13),
                text=second_tag,
                unit=StructuralUnit.TAG,
                rule_id="verbatim-style-id:Heading4",
                match_source=VERBATIM,
                section_path=(BLOCK_TEXT,),
            ),
            FixtureParagraph(
                xml=paragraph_xml(
                    run_xml(second_cite_short, character_style="Style13ptBold")
                    + run_xml(second_cite[len(second_cite_short) :])
                ),
                text=second_cite,
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=ALIAS,
                section_path=(BLOCK_TEXT, second_tag),
            ),
            FixtureParagraph(
                xml=paragraph_xml(
                    run_xml(second_body_opening, half_points=16)
                    + run_xml(
                        second_body_underlined,
                        character_style="StyleUnderline",
                        underline="single",
                        half_points=22,
                    )
                    + run_xml(second_body_closing, half_points=16)
                ),
                text=second_body,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(BLOCK_TEXT, second_tag),
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=BODY_TEXT,
                completeness=CardCompleteness.FULL,
                section_path=(BLOCK_TEXT,),
                element_range=(1, 3),
                underlined_text=(BODY_UNDERLINED,),
            ),
            FixtureCard(
                tag=second_tag,
                short_cite=second_cite_short,
                full_cite=second_cite,
                evidence_text=second_body,
                completeness=CardCompleteness.FULL,
                section_path=(BLOCK_TEXT,),
                element_range=(4, 6),
                underlined_text=(second_body_underlined,),
            ),
        ),
    )


def wiki_converted_cite_entries() -> StructuralFixture:
    """The `wiki-converted` family: 58 files in the survey, and the reason ABBREVIATED exists."""
    abbreviated_body = (
        "Grid operators in the region reported that demand … thinner than at any point in the past decade."
    )
    cite_only_tag = "Load growth outpaced every planning scenario"
    cite_only_short = "Ferreira 25"
    cite_only_cite = cite_only_short + " (Journal of Grid Studies, 2 November 2025)."
    return StructuralFixture(
        filename="wiki-converted-cite-entries.docx",
        family="wiki-converted",
        corpus="caselist",
        summary=(
            "An opencaselist wiki-to-docx conversion: the Verbatim styles are all defined and not "
            "one paragraph references them, so every unit comes from a heuristic. A disclosure "
            "records a card's first and last words with an ellipsis between, which makes the card "
            "ABBREVIATED, and sometimes records no body at all, which makes it CITE_ONLY. Neither "
            "is padded out and neither is dropped."
        ),
        paragraphs=(
            FixtureParagraph(
                xml=paragraph_xml(run_xml(TAG_TEXT, bold=True, half_points=26)),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="heuristic-direct-formatted-heading-tag",
                match_source=HEURISTIC,
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(FULL_CITE)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="heuristic-cite-line-author-year",
                match_source=HEURISTIC,
                section_path=(TAG_TEXT,),
            ),
            FixtureParagraph(
                xml=paragraph_xml(
                    run_xml("Grid operators in the region reported that demand ")
                    + run_xml("…", underline="single")
                    + run_xml(" thinner than at any point in the past decade.")
                ),
                text=abbreviated_body,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(TAG_TEXT,),
                note="The ellipsis is what makes the card ABBREVIATED rather than truncated.",
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(cite_only_tag, bold=True, half_points=26)),
                text=cite_only_tag,
                unit=StructuralUnit.TAG,
                rule_id="heuristic-direct-formatted-heading-tag",
                match_source=HEURISTIC,
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(cite_only_cite)),
                text=cite_only_cite,
                unit=StructuralUnit.CITE,
                rule_id="heuristic-cite-line-author-year",
                match_source=HEURISTIC,
                section_path=(cite_only_tag,),
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=abbreviated_body,
                completeness=CardCompleteness.ABBREVIATED,
                element_range=(0, 2),
                underlined_text=("…",),
            ),
            FixtureCard(
                tag=cite_only_tag,
                short_cite=cite_only_short,
                full_cite=cite_only_cite,
                evidence_text="",
                completeness=CardCompleteness.CITE_ONLY,
                element_range=(3, 4),
            ),
        ),
        style_definitions=DEFAULT_STYLE_DEFINITIONS,
    )


def non_verbatim_caselist_upload() -> StructuralFixture:
    """The `other-heuristic` family: 9% of the caselist corpus. A Google Docs export."""
    return StructuralFixture(
        filename="non-verbatim-caselist-upload.docx",
        family="other-heuristic",
        corpus="caselist",
        summary=(
            "A disclosure that went through Google Docs, which keeps outline levels and the bold "
            "and sizes that go with them but references no Verbatim style. Structure survives as "
            "`w:outlineLvl` plus formatting, and the profile's size and weight guards are what "
            "make the promotion safe."
        ),
        style_definitions=(
            ("Normal", "paragraph", "Normal", None),
            ("DefaultParagraphFont", "character", "Default Paragraph Font", None),
        ),
        paragraphs=(
            FixtureParagraph(
                xml=paragraph_xml(run_xml(POCKET_TEXT, bold=True, half_points=52), outline_level=0),
                text=POCKET_TEXT,
                unit=StructuralUnit.POCKET,
                rule_id="heuristic-outline-level-0",
                match_source=HEURISTIC,
            ),
            FixtureParagraph(
                xml=paragraph_xml(
                    run_xml(BLOCK_TEXT, bold=True, underline="single", half_points=32),
                    outline_level=2,
                ),
                text=BLOCK_TEXT,
                unit=StructuralUnit.BLOCK,
                rule_id="heuristic-outline-level-2",
                match_source=HEURISTIC,
                section_path=(POCKET_TEXT,),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(TAG_TEXT, bold=True, half_points=26), outline_level=3),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="heuristic-outline-level-3",
                match_source=HEURISTIC,
                section_path=(POCKET_TEXT, BLOCK_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(FULL_CITE)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="heuristic-cite-line-author-year",
                match_source=HEURISTIC,
                section_path=(POCKET_TEXT, BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(
                    run_xml(BODY_OPENING)
                    + run_xml(BODY_UNDERLINED, underline="single", highlight="yellow")
                    + run_xml(BODY_CLOSING)
                ),
                text=BODY_TEXT,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(POCKET_TEXT, BLOCK_TEXT, TAG_TEXT),
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=BODY_TEXT,
                completeness=CardCompleteness.FULL,
                section_path=(POCKET_TEXT, BLOCK_TEXT),
                element_range=(2, 4),
                underlined_text=(BODY_UNDERLINED,),
            ),
        ),
    )


def pre_2026_direct_formatting() -> StructuralFixture:
    """An older team file: drifted style ids, and headings that are only bold text at a size."""
    return StructuralFixture(
        filename="pre-2026-direct-formatting.docx",
        family="other-heuristic",
        corpus="team",
        summary=(
            "A file that has been copied between documents for three seasons. `Heading411` is a "
            "Heading 4 that Word de-duplicated twice — 197 files in the survey carry one — and it "
            "must resolve to a tag rather than to the pocket its id starts with. The block heading "
            "below it survives only as bold underlined text at a heading size, with no outline "
            "level at all: the wall CardMirror hits and leaves flat."
        ),
        style_definitions=(
            *DEFAULT_STYLE_DEFINITIONS,
            ("Heading411", "paragraph", "heading 411", "Heading1"),
        ),
        paragraphs=(
            FixtureParagraph(
                xml=paragraph_xml(run_xml(BLOCK_TEXT, bold=True, underline="single", half_points=32)),
                text=BLOCK_TEXT,
                unit=StructuralUnit.BLOCK,
                rule_id="heuristic-direct-formatted-heading-block",
                match_source=HEURISTIC,
                note="No outline level, no style: bold, underlined and 16 pt is all there is.",
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(TAG_TEXT), style="Heading411"),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="verbatim-deduplicated:Heading411->Heading4",
                match_source=ALIAS,
                section_path=(BLOCK_TEXT,),
                note="Stripping Word's de-duplication digits reaches Heading4, not Heading1.",
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(SHORT_CITE, character_style="Style13ptBold") + run_xml(CITE_TAIL)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=ALIAS,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=verbatim_body_paragraph(),
                text=BODY_TEXT,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=BODY_TEXT,
                completeness=CardCompleteness.FULL,
                section_path=(BLOCK_TEXT,),
                element_range=(1, 3),
                underlined_text=(BODY_UNDERLINED,),
            ),
        ),
    )


def analytics_and_undertags() -> StructuralFixture:
    """The two units that are not cards, and the tag that turns out to be analysis."""
    analytic_text = "Their evidence predates the load growth their own author describes"
    undertag_text = "And the margin is already thin"
    return StructuralFixture(
        filename="analytics-and-undertags.docx",
        family="verbatim",
        corpus="team",
        summary=(
            "An `Analytic` paragraph, an `Undertag` under a tag, and a `Heading4` with no cite and "
            "no body under it. The last is the case only the assembly can decide: `Heading4` is "
            "what a debater types for a line of analysis too, so a tag with no card under it "
            "becomes an ANALYTIC rather than an empty card."
        ),
        paragraphs=(
            FixtureParagraph(
                xml=paragraph_xml(run_xml(BLOCK_TEXT), style="Heading3"),
                text=BLOCK_TEXT,
                unit=StructuralUnit.BLOCK,
                rule_id="verbatim-style-id:Heading3",
                match_source=VERBATIM,
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(TAG_TEXT), style="Heading4"),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="verbatim-style-id:Heading4",
                match_source=VERBATIM,
                section_path=(BLOCK_TEXT,),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(undertag_text), style="Undertag"),
                text=undertag_text,
                unit=StructuralUnit.UNDERTAG,
                rule_id="verbatim-style-id:Undertag",
                match_source=VERBATIM,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(SHORT_CITE, character_style="Style13ptBold") + run_xml(CITE_TAIL)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=ALIAS,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=verbatim_body_paragraph(),
                text=BODY_TEXT,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(analytic_text), style="Analytic"),
                text=analytic_text,
                unit=StructuralUnit.ANALYTIC,
                rule_id="verbatim-style-id:Analytic",
                match_source=VERBATIM,
                section_path=(BLOCK_TEXT, TAG_TEXT),
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml("No impact scenario survives the timeframe"), style="Heading4"),
                text="No impact scenario survives the timeframe",
                unit=StructuralUnit.ANALYTIC,
                rule_id="assembly-tag-without-cite-or-evidence:verbatim-style-id:Heading4",
                match_source=HEURISTIC,
                section_path=(BLOCK_TEXT,),
                note="A tag with no cite and no body under it is a line of analysis.",
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=BODY_TEXT,
                completeness=CardCompleteness.FULL,
                section_path=(BLOCK_TEXT,),
                undertag=undertag_text,
                element_range=(1, 4),
                underlined_text=(BODY_UNDERLINED,),
            ),
        ),
    )


def tables_and_text_boxes() -> StructuralFixture:
    """Page furniture: a speech-time chart and a page banner, neither of which is a card."""
    box = "<w:txbxContent>" + paragraph_xml(run_xml("Invitational — Octafinals")) + "</w:txbxContent>"
    return StructuralFixture(
        filename="tables-and-text-boxes.docx",
        family="verbatim",
        corpus="team",
        summary=(
            "A speech-time table whose first cell carries `Heading4`, and a page banner in a text "
            "box that Word wrote twice. Both are OTHER: a table cell and a text box are page "
            "furniture whatever style they carry, and the box is read once rather than twice."
        ),
        paragraphs=(
            FixtureParagraph(
                xml=(
                    "<w:tbl><w:tr><w:tc>"
                    + paragraph_xml(run_xml("Speech times"), style="Heading4")
                    + "</w:tc><w:tc>"
                    + paragraph_xml(run_xml("6 minutes"))
                    + "</w:tc></w:tr></w:tbl>"
                ),
                text="Speech times",
                unit=StructuralUnit.OTHER,
                rule_id="assembly-table-cell",
                match_source=HEURISTIC,
                note="Carries Heading4 and is still OTHER, because it sits in a table cell.",
            ),
            FixtureParagraph(
                xml="",
                text="6 minutes",
                unit=StructuralUnit.OTHER,
                rule_id="assembly-table-cell",
                match_source=HEURISTIC,
            ),
            FixtureParagraph(
                xml=(
                    "<w:p><w:r><w:t>Read this block first.</w:t>"
                    f'<mc:AlternateContent><mc:Choice Requires="wps">{box}</mc:Choice>'
                    f"<mc:Fallback>{box}</mc:Fallback></mc:AlternateContent>"
                    "</w:r></w:p>"
                ),
                text="Read this block first.",
                unit=StructuralUnit.OTHER,
                rule_id="heuristic-unclassified-paragraph",
                match_source=HEURISTIC,
            ),
            FixtureParagraph(
                xml="",
                text="Invitational — Octafinals",
                unit=StructuralUnit.OTHER,
                rule_id="assembly-text-box",
                match_source=HEURISTIC,
                note="Word writes the box twice; it is read once.",
            ),
        ),
    )


def tracked_changes_and_comments() -> StructuralFixture:
    """What an edited file contributes, and what its comments and authorship never do."""
    edited_body = (
        "Grid operators reported that demand rose sharply last year across every planning "
        "scenario the utility had on file."
    )
    return StructuralFixture(
        filename="tracked-changes-and-comments.docx",
        family="verbatim",
        corpus="team",
        summary=(
            "A card edited with track changes on, in a package that also carries comments and "
            "`docProps` authorship. The insertion is in the card and the deletion is not — a card "
            "is what the file would read as, not what it used to read as — and nothing from the "
            "comment or the authorship parts reaches the output, because neither part is opened."
        ),
        extra_parts={
            "docProps/core.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
                'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:creator>NEVER READ</dc:creator>"
                "<cp:lastModifiedBy>NEVER READ</cp:lastModifiedBy></cp:coreProperties>"
            ),
            "word/comments.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:comment w:id="1" w:author="NEVER READ">'
                "<w:p><w:r><w:t>NEVER READ</w:t></w:r></w:p></w:comment></w:comments>"
            ),
        },
        paragraphs=(
            FixtureParagraph(
                xml=paragraph_xml(run_xml(TAG_TEXT), style="Heading4"),
                text=TAG_TEXT,
                unit=StructuralUnit.TAG,
                rule_id="verbatim-style-id:Heading4",
                match_source=VERBATIM,
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(SHORT_CITE, character_style="Style13ptBold") + run_xml(CITE_TAIL)),
                text=FULL_CITE,
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=ALIAS,
                section_path=(TAG_TEXT,),
            ),
            FixtureParagraph(
                xml=(
                    "<w:p>"
                    + run_xml("Grid operators reported that demand rose ", half_points=16)
                    + '<w:ins w:id="1" w:author="NEVER READ" w:date="2026-03-14T00:00:00Z">'
                    + run_xml("sharply ", half_points=16)
                    + "</w:ins>"
                    + '<w:del w:id="2" w:author="NEVER READ" w:date="2026-03-14T00:00:00Z">'
                    + "<w:r><w:delText>slightly </w:delText></w:r></w:del>"
                    + run_xml(
                        "last year across every planning scenario the utility had on file.",
                        character_style="StyleUnderline",
                        underline="single",
                        half_points=22,
                    )
                    + "</w:p>"
                ),
                text=edited_body,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-marked-up-body-text",
                match_source=HEURISTIC,
                section_path=(TAG_TEXT,),
            ),
        ),
        cards=(
            FixtureCard(
                tag=TAG_TEXT,
                short_cite=SHORT_CITE,
                full_cite=FULL_CITE,
                evidence_text=edited_body,
                completeness=CardCompleteness.FULL,
                element_range=(0, 2),
                underlined_text=("last year across every planning scenario the utility had on file.",),
            ),
        ),
        warnings_contain=("tracked deletion",),
    )


def not_a_debate_file() -> StructuralFixture:
    """The negative fixture. A document that uses outline levels must not become a stack of pockets."""
    syllabus_heading = "Course outline"
    syllabus_body = (
        "Students are expected to complete the assigned reading before each seminar. The reading "
        "list is posted two weeks in advance and every item on it is available through the "
        "library's catalogue. Assessment is by two essays and a presentation, weighted equally, "
        "and late submissions are accepted only with prior agreement."
    )
    return StructuralFixture(
        filename="not-a-debate-file.docx",
        family="not-a-debate-file",
        corpus="negative",
        summary=(
            "A syllabus that uses outline levels and no Verbatim style. It must not come out as a "
            "stack of pockets, and it must produce no cards: this is what the profile's size and "
            "weight guards exist for, and what a parser without them gets wrong at scale."
        ),
        style_definitions=(
            ("Normal", "paragraph", "Normal", None),
            ("DefaultParagraphFont", "character", "Default Paragraph Font", None),
        ),
        paragraphs=(
            FixtureParagraph(
                xml=paragraph_xml(run_xml(syllabus_heading, half_points=24), outline_level=0),
                text=syllabus_heading,
                unit=StructuralUnit.OTHER,
                rule_id="heuristic-unclassified-paragraph",
                match_source=HEURISTIC,
                note="Outline level 0 with no bold and no heading size promotes nothing.",
            ),
            FixtureParagraph(
                xml=paragraph_xml(run_xml(syllabus_body)),
                text=syllabus_body,
                unit=StructuralUnit.EVIDENCE,
                rule_id="heuristic-prose-paragraph",
                match_source=HEURISTIC,
                note=(
                    "Long unmarked prose is the weakest evidence rule there is, and it says so in "
                    "its confidence. It produces no card, because there is no tag and no cite."
                ),
            ),
        ),
    )


FIXTURES: Final = (
    team_verbatim_file,
    cardmirror_caselist_upload,
    cardmirror_camp_file,
    wiki_converted_cite_entries,
    non_verbatim_caselist_upload,
    pre_2026_direct_formatting,
    analytics_and_undertags,
    tables_and_text_boxes,
    tracked_changes_and_comments,
    not_a_debate_file,
)


# --------------------------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------------------------


def write_fixture(fixture: StructuralFixture, profile: StyleProfile, directory: Path) -> tuple[Path, Path]:
    """Write one fixture's `.docx` and its `.expected.json`, returning both paths."""
    directory.mkdir(parents=True, exist_ok=True)
    body = "".join(paragraph.xml for paragraph in fixture.paragraphs)
    content = build_docx(
        body,
        styles_xml=build_styles_xml(fixture.style_definitions),
        extra_parts=dict(fixture.extra_parts),
    )
    docx_path = directory / fixture.filename
    docx_path.write_bytes(content)

    expectations = {
        "fixture": fixture.filename,
        "family": fixture.family,
        "corpus": fixture.corpus,
        "summary": fixture.summary,
        "profile_version": profile.profile_version,
        "parser_version": DOCX_PARSER_VERSION,
        "warnings_contain": list(fixture.warnings_contain),
        "paragraphs": [
            {
                "index": index,
                "text": paragraph.text,
                "unit": paragraph.unit.value,
                "rule_id": paragraph.rule_id,
                "match_source": paragraph.match_source.value,
                "section_path": list(paragraph.section_path),
                "note": paragraph.note,
            }
            for index, paragraph in enumerate(fixture.paragraphs)
        ],
        "cards": [
            {
                "tag": card.tag,
                "short_cite": card.short_cite,
                "full_cite": card.full_cite,
                "undertag": card.undertag,
                "evidence_text": card.evidence_text,
                "completeness": card.completeness.value,
                "section_path": list(card.section_path),
                "first_element_index": card.element_range[0],
                "last_element_index": card.element_range[1],
                "underlined_text": list(card.underlined_text),
            }
            for card in fixture.cards
        ],
    }
    expected_path = directory / f"{fixture.filename.removesuffix('.docx')}.expected.json"
    expected_path.write_text(json.dumps(expectations, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return docx_path, expected_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=FIXTURE_DIRECTORY,
        help="where to write the fixtures (default: the committed fixture directory)",
    )
    arguments = parser.parse_args()
    profile = load_style_profile()
    for build in FIXTURES:
        fixture = build()
        docx_path, expected_path = write_fixture(fixture, profile, arguments.directory)
        print(f"wrote {docx_path.name} and {expected_path.name}")
    print(f"{len(FIXTURES)} fixtures in {arguments.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

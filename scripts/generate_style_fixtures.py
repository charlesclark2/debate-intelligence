#!/usr/bin/env python3
"""Build the synthetic `.docx` fixtures for the style profile and its classifier.

`tests/fixtures/debate_files/style_profile/` holds one small document per shape a debate file
arrives in: a card cut in Verbatim, a Google Docs export whose only structural signal is an
outline level, a hand-formatted file with no outline levels at all, an opencaselist wiki
conversion, and an ordinary Word document that uses outline levels and must *not* parse as debate
structure. Each one is generated here, from the profile's own writer style definitions, so a
change to the profile shows up in the fixtures rather than leaving them quietly stale.

Alongside each `.docx` goes a `.expected.json` naming, for every paragraph, the structural unit,
the rule id and the match source the classifier should produce. **Those expectations are written
by hand in this file, never derived by running the classifier** — a fixture whose answers came
from the code under test proves nothing.

The text is invented for these fixtures. No real evidence, no real cite, no real team is in here;
scrubbed excerpts of real files are a separate part of the fixture directory and go through
`scripts/scrub_docx_fixture.py` and a coach's review first. See the directory's `MANIFEST.md`.

    uv run python scripts/generate_style_fixtures.py

Owned by `v1-e31-t02-verbatim-style-profile`.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from xml.sax.saxutils import escape, quoteattr

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "debate_core" / "src"))

from debate_core.domain.style_profile import (  # noqa: E402
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
    WriterStyleDefinition,
)
from debate_core.evidence.style_profile_loader import load_style_profile  # noqa: E402

FIXTURE_DIRECTORY: Final = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "style_profile"
W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES: Final = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

PACKAGE_RELS: Final = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>
"""

DOCUMENT_RELS: Final = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
    Target="styles.xml"/>
</Relationships>
"""


# --------------------------------------------------------------------------------------------
# The fixture description
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureRun:
    """One run of a fixture paragraph."""

    text: str
    character_style: str | None = None
    bold: bool | None = None
    underline: str | None = None
    highlight: str | None = None
    half_points: int | None = None

    def to_xml(self) -> str:
        properties: list[str] = []
        if self.character_style is not None:
            properties.append(f"<w:rStyle w:val={quoteattr(self.character_style)}/>")
        if self.bold is not None:
            properties.append("<w:b/>" if self.bold else '<w:b w:val="0"/>')
        if self.underline is not None:
            properties.append(f"<w:u w:val={quoteattr(self.underline)}/>")
        if self.highlight is not None:
            properties.append(f"<w:highlight w:val={quoteattr(self.highlight)}/>")
        if self.half_points is not None:
            properties.append(f'<w:sz w:val="{self.half_points}"/>')
        run_properties = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
        return f'<w:r>{run_properties}<w:t xml:space="preserve">{escape(self.text)}</w:t></w:r>'


@dataclass(frozen=True)
class FixtureParagraph:
    """One paragraph, and what the classifier is expected to make of it."""

    runs: tuple[FixtureRun, ...]
    expected_unit: StructuralUnit
    expected_rule_id: str
    expected_match_source: StyleMatchSource
    paragraph_style: str | None = None
    outline_level: int | None = None
    note: str = ""

    def to_xml(self) -> str:
        properties: list[str] = []
        if self.paragraph_style is not None:
            properties.append(f"<w:pStyle w:val={quoteattr(self.paragraph_style)}/>")
        if self.outline_level is not None:
            properties.append(f'<w:outlineLvl w:val="{self.outline_level}"/>')
        paragraph_properties = f"<w:pPr>{''.join(properties)}</w:pPr>" if properties else ""
        return f"<w:p>{paragraph_properties}{''.join(run.to_xml() for run in self.runs)}</w:p>"

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


@dataclass(frozen=True)
class FixtureDocument:
    """One fixture file: what it is for, what is in it, and what it should classify as."""

    filename: str
    category: str
    summary: str
    paragraphs: tuple[FixtureParagraph, ...]
    define_verbatim_styles: bool = True
    extra_style_definitions: tuple[tuple[str, str, str, str | None], ...] = field(default=())
    """`(styleId, type, name, basedOn)` for styles this fixture defines beyond the profile's."""


# --------------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------------


def _definition_to_xml(definition: WriterStyleDefinition) -> str:
    paragraph_properties: list[str] = []
    run_properties: list[str] = []
    if definition.outline_level is not None:
        paragraph_properties.append(f'<w:outlineLvl w:val="{definition.outline_level}"/>')
    if definition.page_break_before:
        paragraph_properties.append("<w:pageBreakBefore/>")
    if definition.keep_with_next:
        paragraph_properties.append("<w:keepNext/>")
    if definition.font is not None:
        run_properties.append(
            f"<w:rFonts w:ascii={quoteattr(definition.font)} w:hAnsi={quoteattr(definition.font)}/>"
        )
    if definition.bold is not None:
        run_properties.append("<w:b/>" if definition.bold else '<w:b w:val="0"/>')
    if definition.color is not None:
        run_properties.append(f"<w:color w:val={quoteattr(definition.color)}/>")
    if definition.half_points is not None:
        run_properties.append(f'<w:sz w:val="{definition.half_points}"/>')
    if definition.underline is not None:
        run_properties.append(f"<w:u w:val={quoteattr(definition.underline)}/>")

    parts = [f"<w:name w:val={quoteattr(definition.style_name)}/>"]
    if definition.based_on is not None:
        parts.append(f"<w:basedOn w:val={quoteattr(definition.based_on)}/>")
    if definition.next_style_id is not None:
        parts.append(f"<w:next w:val={quoteattr(definition.next_style_id)}/>")
    if paragraph_properties:
        parts.append(f"<w:pPr>{''.join(paragraph_properties)}</w:pPr>")
    if run_properties:
        parts.append(f"<w:rPr>{''.join(run_properties)}</w:rPr>")
    return (
        f"<w:style w:type={quoteattr(definition.style_type)} "
        f"w:styleId={quoteattr(definition.style_id)}>{''.join(parts)}</w:style>"
    )


def build_styles_xml(document: FixtureDocument, profile: StyleProfile) -> str:
    """Render `word/styles.xml` from the profile's own writer style definitions."""
    styles = [
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>',
        '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont">'
        '<w:name w:val="Default Paragraph Font"/></w:style>',
    ]
    if document.define_verbatim_styles:
        styles.extend(_definition_to_xml(definition) for definition in profile.writer_style_definitions)
    for style_id, style_type, name, based_on in document.extra_style_definitions:
        based = f"<w:basedOn w:val={quoteattr(based_on)}/>" if based_on else ""
        styles.append(
            f"<w:style w:type={quoteattr(style_type)} w:styleId={quoteattr(style_id)}>"
            f"<w:name w:val={quoteattr(name)}/>{based}</w:style>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NS}">' + "".join(styles) + "</w:styles>"
    )


def build_document_xml(document: FixtureDocument) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(paragraph.to_xml() for paragraph in document.paragraphs)
        + "</w:body></w:document>"
    )


def write_fixture(document: FixtureDocument, profile: StyleProfile, directory: Path) -> tuple[Path, Path]:
    """Write one fixture's `.docx` and its `.expected.json`, returning both paths."""
    directory.mkdir(parents=True, exist_ok=True)
    docx_path = directory / document.filename
    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        archive.writestr("word/styles.xml", build_styles_xml(document, profile))
        archive.writestr("word/document.xml", build_document_xml(document))

    expectations = {
        "fixture": document.filename,
        "category": document.category,
        "summary": document.summary,
        "profile_version": profile.profile_version,
        "paragraphs": [
            {
                "index": index,
                "text": paragraph.text,
                "expected_unit": paragraph.expected_unit.value,
                "expected_rule_id": paragraph.expected_rule_id,
                "expected_match_source": paragraph.expected_match_source.value,
                "note": paragraph.note,
            }
            for index, paragraph in enumerate(document.paragraphs)
        ],
    }
    expected_path = directory / f"{document.filename.removesuffix('.docx')}.expected.json"
    expected_path.write_text(json.dumps(expectations, indent=2) + "\n", encoding="utf-8")
    return docx_path, expected_path


# --------------------------------------------------------------------------------------------
# The fixtures themselves
# --------------------------------------------------------------------------------------------

# Invented for these fixtures. Nothing here is real evidence, a real cite or a real team.
EVIDENCE_OPENING = "Grid operators in the region reported that demand from new data centres rose "
EVIDENCE_UNDERLINED = "faster than any other load category last year"
EVIDENCE_CLOSING = (
    ", and the increase outpaced every scenario the utility had planned against, leaving the "
    "reserve margin thinner than at any point in the past decade."
)


def verbatim_cut_card() -> FixtureDocument:
    """A card cut the ordinary way: every unit carries its Verbatim paragraph or character style."""
    return FixtureDocument(
        filename="verbatim-cut-card.docx",
        category="verbatim",
        summary=(
            "A pocket, hat, block, tag, cite, evidence body, analytic and undertag, each carrying "
            "the Verbatim style the profile names. Nothing here needs a heuristic."
        ),
        paragraphs=(
            FixtureParagraph(
                runs=(FixtureRun("Data Centre Moratorium Negative"),),
                paragraph_style="Heading1",
                expected_unit=StructuralUnit.POCKET,
                expected_rule_id="verbatim-style-id:Heading1",
                expected_match_source=StyleMatchSource.VERBATIM,
            ),
            FixtureParagraph(
                runs=(FixtureRun("Grid Reliability"),),
                paragraph_style="Heading2",
                expected_unit=StructuralUnit.HAT,
                expected_rule_id="verbatim-style-id:Heading2",
                expected_match_source=StyleMatchSource.VERBATIM,
            ),
            FixtureParagraph(
                runs=(FixtureRun("AT: Reserve Margin Turn"),),
                paragraph_style="Heading3",
                expected_unit=StructuralUnit.BLOCK,
                expected_rule_id="verbatim-style-id:Heading3",
                expected_match_source=StyleMatchSource.VERBATIM,
            ),
            FixtureParagraph(
                runs=(FixtureRun("Data centre demand collapses the reserve margin"),),
                paragraph_style="Heading4",
                expected_unit=StructuralUnit.TAG,
                expected_rule_id="verbatim-style-id:Heading4",
                expected_match_source=StyleMatchSource.VERBATIM,
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun("Okonkwo 26", character_style="Style13ptBold"),
                    FixtureRun(
                        " (Adaeze Okonkwo, Professor of Energy Policy, invented for this fixture), "
                        "Reserve Margins Under Load Growth, Journal of Grid Studies, 14 March 2026."
                    ),
                ),
                expected_unit=StructuralUnit.CITE,
                expected_rule_id="verbatim-cite-run-style",
                expected_match_source=StyleMatchSource.VERBATIM_ALIAS,
                note="Verbatim gives a cite no paragraph style; the cite character style finds it.",
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun(EVIDENCE_OPENING, half_points=16),
                    FixtureRun(
                        EVIDENCE_UNDERLINED,
                        character_style="StyleUnderline",
                        underline="single",
                        highlight="cyan",
                        half_points=22,
                    ),
                    FixtureRun(EVIDENCE_CLOSING, half_points=16),
                ),
                expected_unit=StructuralUnit.EVIDENCE,
                expected_rule_id="heuristic-marked-up-body-text",
                expected_match_source=StyleMatchSource.HEURISTIC,
                note=(
                    "Evidence is unstyled Normal text in Verbatim, so even in a fully styled file "
                    "the body is found by its markup. The underlined run carries both encodings at "
                    "once, which is what CardMirror writes."
                ),
            ),
            FixtureParagraph(
                runs=(FixtureRun("Their evidence is about transmission, not generation."),),
                paragraph_style="Analytic",
                expected_unit=StructuralUnit.ANALYTIC,
                expected_rule_id="verbatim-style-id:Analytic",
                expected_match_source=StyleMatchSource.VERBATIM,
            ),
            FixtureParagraph(
                runs=(FixtureRun("And, the impact is fast"),),
                paragraph_style="Undertag",
                expected_unit=StructuralUnit.UNDERTAG,
                expected_rule_id="verbatim-style-id:Undertag",
                expected_match_source=StyleMatchSource.VERBATIM,
            ),
        ),
    )


def drifted_style_names() -> FixtureDocument:
    """The same card after three seasons of copying between documents.

    `Heading411` is Word's de-duplication of a second `Heading 4`, and it inherits from
    `Heading1` — it appears that way in 197 files of the surveyed corpus. `HeadingFake` is
    somebody's own style that inherits from `Heading3`. Both have to resolve, and `Heading411`
    has to resolve to a tag rather than to a pocket.
    """
    return FixtureDocument(
        filename="drifted-style-names.docx",
        category="verbatim",
        summary=(
            "Verbatim styles under the ids real files pick up over time: a Word-deduplicated "
            "`Heading411`, a team's own `HeadingFake`, and an `Analytics` plural."
        ),
        extra_style_definitions=(
            ("Heading411", "paragraph", "Heading 411", "Heading1"),
            ("HeadingFake", "paragraph", "Heading Fake", "Heading3"),
            ("Analytics", "paragraph", "Analytics", "Heading4"),
        ),
        paragraphs=(
            FixtureParagraph(
                runs=(FixtureRun("Warming Advantage"),),
                paragraph_style="Heading1",
                expected_unit=StructuralUnit.POCKET,
                expected_rule_id="verbatim-style-id:Heading1",
                expected_match_source=StyleMatchSource.VERBATIM,
            ),
            FixtureParagraph(
                runs=(FixtureRun("AT: Adaptation Solves"),),
                paragraph_style="HeadingFake",
                expected_unit=StructuralUnit.BLOCK,
                expected_rule_id="verbatim-based-on:Heading3",
                expected_match_source=StyleMatchSource.VERBATIM_ALIAS,
                note="Nobody's vocabulary but its own; it means what it inherits.",
            ),
            FixtureParagraph(
                runs=(FixtureRun("Adaptation fails in the agricultural sector"),),
                paragraph_style="Heading411",
                expected_unit=StructuralUnit.TAG,
                expected_rule_id="verbatim-deduplicated:Heading411->Heading4",
                expected_match_source=StyleMatchSource.VERBATIM_ALIAS,
                note=(
                    "Inherits from Heading1 and is a Heading 4. Resolving by basedOn would call "
                    "this a pocket, which is why de-duplication is tried first."
                ),
            ),
            FixtureParagraph(
                runs=(FixtureRun("Their author concedes this in the next paragraph."),),
                paragraph_style="Analytics",
                expected_unit=StructuralUnit.ANALYTIC,
                expected_rule_id="verbatim-alias-id:Analytics",
                expected_match_source=StyleMatchSource.VERBATIM_ALIAS,
            ),
        ),
    )


def outline_levels_only() -> FixtureDocument:
    """A Google Docs export: no Verbatim styles, but outline levels with the right formatting."""
    return FixtureDocument(
        filename="outline-levels-only.docx",
        category="heuristic",
        summary=(
            "No Verbatim style is defined or referenced. Structure survives only as `w:outlineLvl` "
            "plus the bold and the sizes that go with each level."
        ),
        define_verbatim_styles=False,
        paragraphs=(
            FixtureParagraph(
                runs=(FixtureRun("Data Centre Moratorium Negative", bold=True, half_points=52),),
                outline_level=0,
                expected_unit=StructuralUnit.POCKET,
                expected_rule_id="heuristic-outline-level-0",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(FixtureRun("Grid Reliability", bold=True, half_points=44),),
                outline_level=1,
                expected_unit=StructuralUnit.HAT,
                expected_rule_id="heuristic-outline-level-1",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(FixtureRun("AT: Reserve Margin Turn", bold=True, half_points=32, underline="single"),),
                outline_level=2,
                expected_unit=StructuralUnit.BLOCK,
                expected_rule_id="heuristic-outline-level-2",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun("Data centre demand collapses the reserve margin", bold=True, half_points=26),
                ),
                outline_level=3,
                expected_unit=StructuralUnit.TAG,
                expected_rule_id="heuristic-outline-level-3",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(FixtureRun("Okonkwo 26, Professor of Energy Policy, 14 March 2026.", half_points=22),),
                expected_unit=StructuralUnit.CITE,
                expected_rule_id="heuristic-cite-line-author-year",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun(EVIDENCE_OPENING, half_points=16),
                    FixtureRun(EVIDENCE_UNDERLINED, underline="single", half_points=22),
                    FixtureRun(EVIDENCE_CLOSING, half_points=16),
                ),
                expected_unit=StructuralUnit.EVIDENCE,
                expected_rule_id="heuristic-marked-up-body-text",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
        ),
    )


def direct_formatting_only() -> FixtureDocument:
    """The wall: no styles, no outline levels, structure expressed only as bold text at a size."""
    return FixtureDocument(
        filename="direct-formatting-only.docx",
        category="heuristic",
        summary=(
            "Neither Verbatim styles nor outline levels — the shape CardMirror imports as loose "
            "paragraphs. Headings are recognised from bold plus size alone, at a lower confidence."
        ),
        define_verbatim_styles=False,
        paragraphs=(
            FixtureParagraph(
                runs=(FixtureRun("Data Centre Moratorium Negative", bold=True, half_points=52),),
                expected_unit=StructuralUnit.POCKET,
                expected_rule_id="heuristic-direct-formatted-heading-pocket",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(FixtureRun("Grid Reliability", bold=True, half_points=44),),
                expected_unit=StructuralUnit.HAT,
                expected_rule_id="heuristic-direct-formatted-heading-hat",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun("Data centre demand collapses the reserve margin", bold=True, half_points=26),
                ),
                expected_unit=StructuralUnit.TAG,
                expected_rule_id="heuristic-direct-formatted-heading-tag",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(FixtureRun("Okonkwo et al. 2026, Journal of Grid Studies.", half_points=22),),
                expected_unit=StructuralUnit.CITE,
                expected_rule_id="heuristic-cite-line-author-year",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(FixtureRun(EVIDENCE_OPENING + EVIDENCE_UNDERLINED + EVIDENCE_CLOSING, half_points=16),),
                expected_unit=StructuralUnit.EVIDENCE,
                expected_rule_id="heuristic-shrunk-body-text",
                expected_match_source=StyleMatchSource.HEURISTIC,
                note="Shrunk, unread card body. Small is formatting, not a reason to drop text.",
            ),
        ),
    )


def wiki_converted_cite_entries() -> FixtureDocument:
    """An opencaselist wiki conversion: Verbatim styles defined, none referenced, cites abbreviated."""
    return FixtureDocument(
        filename="wiki-converted-cite-entries.docx",
        category="heuristic",
        summary=(
            "The signature the style survey found in 58 files: the whole Verbatim style set is "
            "defined and not one paragraph references it. Cites record a card's first and last "
            "words with an ellipsis between them, which makes the card ABBREVIATED, not truncated."
        ),
        paragraphs=(
            FixtureParagraph(
                runs=(FixtureRun("1AC — Grid", bold=True, half_points=52),),
                expected_unit=StructuralUnit.POCKET,
                expected_rule_id="heuristic-direct-formatted-heading-pocket",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun("Data centre demand collapses the reserve margin", bold=True, half_points=26),
                ),
                expected_unit=StructuralUnit.TAG,
                expected_rule_id="heuristic-direct-formatted-heading-tag",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun(
                        "Okonkwo 26 — Grid operators in the region reported … thinner than at any "
                        "point in the past decade.",
                        half_points=22,
                    ),
                ),
                expected_unit=StructuralUnit.CITE,
                expected_rule_id="heuristic-wiki-cite-entry",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun(
                        "Halvorsen 26 — Reserve margins across the interconnection … no slack left.",
                        half_points=22,
                    ),
                ),
                expected_unit=StructuralUnit.CITE,
                expected_rule_id="heuristic-wiki-cite-entry",
                expected_match_source=StyleMatchSource.HEURISTIC,
            ),
        ),
    )


def ordinary_document_with_outline_levels() -> FixtureDocument:
    """The negative fixture, and the reason the heuristics have guards.

    An ordinary Word document that uses outline levels and nothing else. Every paragraph here
    must stay out of the structural units: a syllabus is not a stack of pockets.
    """
    return FixtureDocument(
        filename="ordinary-document-with-outline-levels.docx",
        category="negative",
        summary=(
            "A document that uses outline levels without any of the formatting that accompanies "
            "them in a debate file. Nothing in it may be promoted to a pocket, hat, block or tag."
        ),
        define_verbatim_styles=False,
        paragraphs=(
            FixtureParagraph(
                runs=(FixtureRun("Course outline for the autumn term", half_points=22),),
                outline_level=0,
                expected_unit=StructuralUnit.OTHER,
                expected_rule_id="heuristic-unclassified-paragraph",
                expected_match_source=StyleMatchSource.HEURISTIC,
                note="Outline level 0, no bold, body size. Not a pocket.",
            ),
            FixtureParagraph(
                runs=(FixtureRun("Week one: introductions", bold=True, half_points=24),),
                outline_level=1,
                expected_unit=StructuralUnit.OTHER,
                expected_rule_id="heuristic-unclassified-paragraph",
                expected_match_source=StyleMatchSource.HEURISTIC,
                note="Bold but well below the 22 pt a hat carries. Not a hat.",
            ),
            FixtureParagraph(
                runs=(
                    FixtureRun(
                        "Students should bring a printed copy of the reading to the first session, "
                        "and should expect to be asked about it. Attendance is recorded from week "
                        "one onwards, and the participation mark depends on it.",
                        half_points=22,
                    ),
                ),
                expected_unit=StructuralUnit.EVIDENCE,
                expected_rule_id="heuristic-prose-paragraph",
                expected_match_source=StyleMatchSource.HEURISTIC,
                note=(
                    "The weakest rule in the set, at 0.4 confidence: inside a debate file this is "
                    "card body, and outside one it is a false positive the parser's grouping "
                    "discards because no tag precedes it."
                ),
            ),
        ),
    )


FIXTURES: Final = (
    verbatim_cut_card,
    drifted_style_names,
    outline_levels_only,
    direct_formatting_only,
    wiki_converted_cite_entries,
    ordinary_document_with_outline_levels,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_style_fixtures.py",
        description="Regenerate the synthetic style-profile fixtures.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=FIXTURE_DIRECTORY,
        help="Where to write the fixtures. Defaults to the committed fixture directory.",
    )
    arguments = parser.parse_args(argv)
    profile = load_style_profile()
    for build in FIXTURES:
        document = build()
        docx_path, expected_path = write_fixture(document, profile, arguments.directory)
        print(f"{docx_path.name}  ({len(document.paragraphs)} paragraphs)  -> {expected_path.name}")
    print(f"profile version {profile.profile_version}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

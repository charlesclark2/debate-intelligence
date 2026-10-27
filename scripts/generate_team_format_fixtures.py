#!/usr/bin/env python3
"""Build the synthetic team folders the formatting analysis is tested on.

`scripts/analyze_team_formatting.py` reads the operator's own season folders in place, and no
team file is copied into this repository in any form (`tests/fixtures/team_samples/MANIFEST.md`
says why). Its tests run on this tree instead: a few invented `.docx` files laid out the way the
operator's folders are, `<season>/<event>/<file>.docx`, each written to one card-formatting
convention, plus the files the analysis has to leave out (a caselist folder, a folder that names
no event, a duplicate, a Word lock file, a file that is not a package).

The styles come from the style profile's own writer definitions, through
`scripts/generate_style_fixtures.py`, so the analysis meets the same `word/styles.xml` the style
fixtures carry. The text is invented and says nothing; the analysis never reads it anyway.

**What each file should measure is written by hand** in
`tests/scripts/test_analyze_team_formatting.py`, from the descriptions below, never by running
the analysis. Each run here states the formatting it carries for that reason.

The archives are written with a fixed timestamp, so regenerating changes no bytes unless a
fixture changed; a test regenerates the tree and compares.

    uv run python scripts/generate_team_format_fixtures.py

Owned by `v1-e06-t03-format-profiles`.
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from xml.sax.saxutils import quoteattr

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "debate_core" / "src"))

from generate_style_fixtures import (  # noqa: E402
    CONTENT_TYPES,
    DOCUMENT_RELS,
    PACKAGE_RELS,
    W_NS,
    FixtureDocument,
    FixtureRun,
    build_styles_xml,
)

from debate_core.domain.style_profile import StyleProfile  # noqa: E402
from debate_core.evidence.style_profile_loader import load_style_profile  # noqa: E402

FIXTURE_DIRECTORY: Final = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "team_format"

#: Every archive member is stamped with this, so the bytes depend on the content alone.
FIXED_TIMESTAMP: Final = (2026, 10, 26, 0, 0, 0)


@dataclass(frozen=True)
class FormatParagraph:
    """One paragraph: its paragraph style, if any, and its runs."""

    runs: tuple[FixtureRun, ...]
    paragraph_style: str | None = None

    def to_xml(self) -> str:
        style = f"<w:pPr><w:pStyle w:val={quoteattr(self.paragraph_style)}/></w:pPr>" if self.paragraph_style else ""
        return f"<w:p>{style}{''.join(run.to_xml() for run in self.runs)}</w:p>"


@dataclass(frozen=True)
class TeamFormatFixture:
    """One file of the synthetic team tree, at `relative_path` below the tree's root."""

    relative_path: str
    paragraphs: tuple[FormatParagraph, ...]
    extra_style_definitions: tuple[tuple[str, str, str, str | None], ...] = ()
    """`(styleId, type, name, basedOn)` for styles beyond the profile's, as the style fixtures take them."""


def _words(text: str, variant: str) -> str:
    """The run text. `variant` replaces it, so a test can build the same formatting over other words."""
    return text if not variant else f"{variant} {len(text)} {variant}"


def _run(
    text: str,
    variant: str,
    *,
    character_style: str | None = None,
    bold: bool | None = None,
    underline: str | None = None,
    highlight: str | None = None,
    half_points: int | None = None,
) -> FixtureRun:
    return FixtureRun(
        _words(text, variant),
        character_style=character_style,
        bold=bold,
        underline=underline,
        highlight=highlight,
        half_points=half_points,
    )


def cyan_convention(variant: str = "") -> TeamFormatFixture:
    """2024-25 LD. Cyan highlighting, unread text at 8 pt, the full cite at 8 pt.

    Measures: 1 pocket, 2 tags. 2 cites, both led by the short cite (`Style13ptBold`, so bold and
    26 half-points from its definition). 2 full-cite runs at 16, not bold. 3 evidence paragraphs.
    4 underlined runs, all 22 (StyleUnderline and Emphasis carry 22 in their definitions), one of
    them bold by direct formatting. 5 not-underlined runs, all 16. 3 cyan runs. All 3 evidence
    paragraphs hold text at or below 16.
    """
    return TeamFormatFixture(
        relative_path="2024-2025/LD/cyan-convention.docx",
        paragraphs=(
            FormatParagraph((_run("Reliability Negative", variant),), paragraph_style="Heading1"),
            FormatParagraph((_run("Demand growth strains the reserve", variant),), paragraph_style="Heading4"),
            FormatParagraph(
                (
                    _run("Okonkwo 26", variant, character_style="Style13ptBold"),
                    _run(" Professor of Energy Policy, Journal of Grid Studies", variant, half_points=16),
                )
            ),
            FormatParagraph(
                (
                    _run("Operators in the region reported that ", variant, half_points=16),
                    _run("demand rose faster than", variant, character_style="StyleUnderline", highlight="cyan"),
                    _run("any other load", variant, character_style="Emphasis", highlight="cyan", bold=True),
                    _run(" in the planning period.", variant, half_points=16),
                )
            ),
            FormatParagraph((_run("The margin is already thin", variant),), paragraph_style="Heading4"),
            FormatParagraph(
                (
                    _run("Halvorsen 25", variant, character_style="Style13ptBold"),
                    _run(" Senior Analyst, Interconnection Review", variant, half_points=16),
                )
            ),
            FormatParagraph(
                (
                    _run("Across the interconnection, ", variant, half_points=16),
                    _run("reserve margins fell", variant, character_style="StyleUnderline", highlight="cyan"),
                    _run(" for a third year.", variant, half_points=16),
                )
            ),
            FormatParagraph(
                (
                    _run("No slack is left", variant, character_style="StyleUnderline"),
                    _run(" in the summer peak.", variant, half_points=16),
                )
            ),
        ),
    )


def green_convention(variant: str = "") -> TeamFormatFixture:
    """2025-26 PF. Green highlighting, unread text at 6 pt, the full cite at 10 pt.

    Measures: 1 block, 1 tag, 1 undertag, 1 analytic. 1 cite, led by the short cite; 1 full-cite
    run at 20. 1 evidence paragraph: 1 underlined run at 22 (green), 2 not-underlined runs at 12.
    The plain paragraph after the analytic is not evidence: the analytic ended the card.
    """
    return TeamFormatFixture(
        relative_path="2025-2026/Public Forum/green-convention.docx",
        paragraphs=(
            FormatParagraph((_run("AT: Adaptation", variant),), paragraph_style="Heading3"),
            FormatParagraph((_run("Adaptation fails in agriculture", variant),), paragraph_style="Heading4"),
            FormatParagraph((_run("And it fails fast", variant),), paragraph_style="Undertag"),
            FormatParagraph(
                (
                    _run("Lindqvist 26", variant, character_style="Style13ptBold"),
                    _run(" Agronomist, Field Trials Quarterly", variant, half_points=20),
                )
            ),
            FormatParagraph(
                (
                    _run("Trials across the region show ", variant, half_points=12),
                    _run("yields fell under heat", variant, character_style="StyleUnderline", highlight="green"),
                    _run(" in every variety tested.", variant, half_points=12),
                )
            ),
            FormatParagraph((_run("Their card is about irrigation.", variant),), paragraph_style="Analytic"),
            FormatParagraph((_run("A note the debater left after the analytic.", variant, half_points=22),)),
        ),
    )


def yellow_convention(variant: str = "") -> TeamFormatFixture:
    """2026-27 Policy. Yellow highlighting, nothing shrunk, underline as direct `w:u`.

    Measures: 2 tags. 2 cites; the first led by the short cite, the second not (a plain run comes
    first). 2 full-cite runs at 22. 2 evidence paragraphs: 2 underlined runs at 22 (direct
    underline, no character style), both yellow; 2 not-underlined runs at 22. No evidence
    paragraph holds text at or below 16.
    """
    return TeamFormatFixture(
        relative_path="2026-2027/Policy Debate/yellow-convention.docx",
        paragraphs=(
            FormatParagraph((_run("Deterrence holds", variant),), paragraph_style="Heading4"),
            FormatParagraph(
                (
                    _run("Marchetti 26", variant, character_style="Style13ptBold"),
                    _run(" Fellow, Strategic Review", variant, half_points=22),
                )
            ),
            FormatParagraph(
                (
                    _run("The record since the treaty shows ", variant, half_points=22),
                    _run("no state tested the line", variant, underline="single", highlight="yellow", half_points=22),
                )
            ),
            FormatParagraph((_run("Escalation is unlikely", variant),), paragraph_style="Heading4"),
            FormatParagraph(
                (
                    _run("As argued in ", variant, half_points=22),
                    _run("Brennan 25", variant, character_style="Style13ptBold"),
                )
            ),
            FormatParagraph(
                (
                    _run("Both sides kept ", variant, half_points=22),
                    _run("every channel open", variant, underline="single", highlight="yellow", half_points=22),
                )
            ),
        ),
    )


def caselist_upload(variant: str = "") -> TeamFormatFixture:
    """A file under a caselist folder: left out by `--exclude-dir Opencaselist`, so never counted."""
    return TeamFormatFixture(
        relative_path="2026-2027/LD Debate/Opencaselist/caselist-upload.docx",
        paragraphs=(
            FormatParagraph((_run("Another program's tag", variant),), paragraph_style="Heading4"),
            FormatParagraph((_run("Another program's evidence", variant, highlight="magenta", underline="single"),)),
        ),
    )


def no_event_folder(variant: str = "") -> TeamFormatFixture:
    """A file whose folders name a season but no event: skipped, and counted as skipped."""
    return TeamFormatFixture(
        relative_path="2026-2027/Practice Speech/practice-speech.docx",
        paragraphs=(FormatParagraph((_run("A practice speech", variant),), paragraph_style="Heading4"),),
    )


FIXTURES: Final = (cyan_convention, green_convention, yellow_convention, caselist_upload, no_event_folder)

#: A byte-identical copy of the cyan file in another folder: counted once.
DUPLICATE_PATH: Final = "2025-2026/LD/cyan-convention-copy.docx"
#: Word's lock file beside the cyan file: never read.
LOCK_FILE_PATH: Final = "2024-2025/LD/~$cyan-convention.docx"
#: Not a zip package: skipped as unreadable.
UNREADABLE_PATH: Final = "2025-2026/LD/not-a-package.docx"


def build_docx(fixture: TeamFormatFixture, profile: StyleProfile) -> bytes:
    """The fixture's `.docx` bytes, deterministic for a given fixture and profile."""
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(paragraph.to_xml() for paragraph in fixture.paragraphs)
        + "</w:body></w:document>"
    )
    styles_xml = build_styles_xml(
        FixtureDocument(
            filename=Path(fixture.relative_path).name,
            category="team",
            summary="",
            paragraphs=(),
            extra_style_definitions=fixture.extra_style_definitions,
        ),
        profile,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in (
            ("[Content_Types].xml", CONTENT_TYPES),
            ("_rels/.rels", PACKAGE_RELS),
            ("word/_rels/document.xml.rels", DOCUMENT_RELS),
            ("word/styles.xml", styles_xml),
            ("word/document.xml", document_xml),
        ):
            member = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, content)
    return buffer.getvalue()


def write_tree(directory: Path, profile: StyleProfile, *, variant: str = "") -> list[Path]:
    """Write the whole synthetic tree under `directory`, returning every path written."""
    written: list[Path] = []
    for build in FIXTURES:
        fixture = build(variant)
        path = directory / fixture.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_docx(fixture, profile))
        written.append(path)
    for extra_path, content in (
        (DUPLICATE_PATH, (directory / cyan_convention(variant).relative_path).read_bytes()),
        (LOCK_FILE_PATH, b"owner lock"),
        (UNREADABLE_PATH, b"this is not a zip package"),
    ):
        path = directory / extra_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_team_format_fixtures.py",
        description="Regenerate the synthetic team folders the formatting analysis is tested on.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=FIXTURE_DIRECTORY,
        help="Where to write the tree. Defaults to the committed fixture directory.",
    )
    arguments = parser.parse_args(argv)
    for path in write_tree(arguments.directory, load_style_profile()):
        print(path.relative_to(arguments.directory))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

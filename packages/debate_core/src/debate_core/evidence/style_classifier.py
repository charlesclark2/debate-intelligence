"""Work out what a paragraph is when the file does not use Verbatim styles.

Most debate files say what they are. `Heading4` is a tag, `StyleUnderline` is underlining, and
:class:`~debate_core.domain.style_profile.StyleProfile` resolves both without guessing. But 11% of
the surveyed corpus — 235 of 2,066 files, and a further 58 that were converted from wiki text —
carries no Verbatim style references at all. Those files are Google Docs exports, opencaselist
wiki conversions and documents somebody direct-formatted by hand, and they arrive from strangers
in bulk. This module is what reads them.

It is deliberately conservative. CardMirror promotes an outline-level paragraph to a heading only
when it also carries the Verbatim formatting signature, and a file with neither styles nor outline
levels stays flat rather than being mis-structured; the same guard applies here, for the same
reason. A syllabus that happens to use outline levels must not come out of the parser as a stack
of pockets. Where a rule is a guess it says so in its confidence, and every result names the rule
that produced it, so a misclassification in the accuracy evaluation (`v1-e31-t05`) can be traced
to one line rather than to "the heuristics".

## The input

:class:`ParagraphDescription` and :class:`RunDescription` are neutral: plain values a reader has
already pulled out of `word/document.xml`. Nothing here knows about OOXML, python-docx or lxml,
which is what lets the same rules be tested without building a `.docx` and reused by anything else
that can describe a paragraph.

## Determinism

Every function here is pure. Same description in, same classification out, no clock, no random
source, no model call, and rules are tried in a fixed order with the first match winning.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field

from debate_core.domain.base import DomainModel
from debate_core.domain.style_profile import (
    ParagraphStyleMatch,
    RunEmphasis,
    RunStyleMatch,
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
)

__all__ = [
    "MAXIMUM_CITE_LINE_CHARACTERS",
    "MAXIMUM_HEADING_CHARACTERS",
    "MINIMUM_PROSE_CHARACTERS",
    "ParagraphDescription",
    "RunDescription",
    "classify_paragraph",
    "classify_run",
]

#: A heading is short. Anything longer is a paragraph that happens to be bold.
MAXIMUM_HEADING_CHARACTERS = 300

#: A cite line is shorter still. The profile carries its own, larger bound for a full cite with a
#: URL in it; this one is the bound for recognising a cite from its *shape* alone, where a wrong
#: answer turns a piece of evidence into a citation.
MAXIMUM_CITE_LINE_CHARACTERS = 400

#: Below this a paragraph is too short to be prose, and the fallback declines to call it evidence.
MINIMUM_PROSE_CHARACTERS = 200

_SENTENCE_END = re.compile(r"[.!?][\"'’”)\]]*\s*$")


class RunDescription(DomainModel):
    """One run's text and formatting, as a reader found it.

    `bold`, `italic` and `all_caps` are tri-state on purpose: `None` means the run says nothing
    and inherits from its style, which is different from saying "not bold". Reading `<w:b w:val="0"/>`
    as `None` is how a bold-off on a heading run gets lost.
    """

    text: str = Field(default="", description="The run's text, exactly as it appears.")
    character_style_id: str | None = Field(default=None, description="`w:rStyle`, if the run carries one.")
    character_style_name: str | None = Field(
        default=None, description="The `w:name` of that character style, where the reader has it."
    )
    character_style_based_on: tuple[str, ...] = Field(
        default=(), description="The character style's ancestors, nearest first."
    )
    bold: bool | None = Field(default=None, description="`w:b`; None when the run does not say.")
    italic: bool | None = Field(default=None, description="`w:i`; None when the run does not say.")
    all_caps: bool | None = Field(default=None, description="`w:caps`; None when the run does not say.")
    underline: str | None = Field(
        default=None, description="`w:u w:val`, e.g. `single`; None or `none` for no underline."
    )
    highlight: str | None = Field(default=None, description="`w:highlight w:val`, if any.")
    half_points: int | None = Field(
        default=None, gt=0, description="`w:sz` in half-points; None when the run does not say."
    )

    @property
    def is_blank(self) -> bool:
        """True when the run carries no visible text."""
        return not self.text.strip()

    @property
    def is_directly_underlined(self) -> bool:
        """True when the run carries a direct `<w:u>` that is switched on."""
        return self.underline is not None and self.underline not in ("none", "0", "false")


class ParagraphDescription(DomainModel):
    """One paragraph's styling, outline level and runs, as a reader found it.

    `text` is derived from the runs rather than stored beside them, so a description cannot
    disagree with itself about what the paragraph says.
    """

    runs: tuple[RunDescription, ...] = Field(default=(), description="The paragraph's runs, in order.")
    style_id: str | None = Field(default=None, description="`w:pStyle`, if the paragraph carries one.")
    style_name: str | None = Field(
        default=None, description="The `w:name` of that paragraph style, where the reader has it."
    )
    style_based_on: tuple[str, ...] = Field(
        default=(), description="The paragraph style's ancestors, nearest first."
    )
    outline_level: int | None = Field(
        default=None, ge=0, le=8, description="`w:outlineLvl`, zero-based; None when there is none."
    )
    paragraph_bold: bool | None = Field(
        default=None, description="Bold set on the paragraph mark rather than on its runs."
    )
    paragraph_half_points: int | None = Field(
        default=None, gt=0, description="Size set on the paragraph mark rather than on its runs."
    )
    element_index: int | None = Field(
        default=None, ge=0, description="Position in the document body, for provenance."
    )
    in_table: bool = Field(default=False, description="Whether the paragraph sits inside a table cell.")

    @property
    def text(self) -> str:
        """The paragraph's text: its runs' text, concatenated in order."""
        return "".join(run.text for run in self.runs)

    @property
    def visible_runs(self) -> tuple[RunDescription, ...]:
        """The runs that carry visible text. Whitespace-only runs decide nothing."""
        return tuple(run for run in self.runs if not run.is_blank)

    @property
    def is_empty(self) -> bool:
        """True when the paragraph has no visible text."""
        return not self.text.strip()

    @property
    def effective_bold(self) -> bool:
        """True when every visible run is bold, or the paragraph mark says so and none contradicts.

        "Every run" rather than "any run": a sentence with one bold word is not a heading.
        """
        visible = self.visible_runs
        if not visible:
            return bool(self.paragraph_bold)
        return all(run.bold if run.bold is not None else bool(self.paragraph_bold) for run in visible)

    @property
    def effective_half_points(self) -> int | None:
        """The largest size any visible run declares, falling back to the paragraph mark.

        The largest rather than the average, because a heading whose last run was left at body
        size is still a heading.
        """
        sizes = [run.half_points for run in self.visible_runs if run.half_points is not None]
        if sizes:
            return max(sizes)
        return self.paragraph_half_points

    @property
    def has_underlined_run(self) -> bool:
        """True when any visible run carries a direct underline."""
        return any(run.is_directly_underlined for run in self.visible_runs)

    @property
    def has_highlighted_run(self) -> bool:
        """True when any visible run carries a highlight colour."""
        return any(run.highlight for run in self.visible_runs)


# --------------------------------------------------------------------------------------------
# Compiled patterns
# --------------------------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _compiled(pattern: str) -> re.Pattern[str]:
    """Compile and cache a pattern out of the profile. Profiles are few and long-lived."""
    return re.compile(pattern)


# --------------------------------------------------------------------------------------------
# Run classification
# --------------------------------------------------------------------------------------------


def classify_run(
    run: RunDescription, profile: StyleProfile, *, slot: StructuralUnit = StructuralUnit.EVIDENCE
) -> tuple[RunStyleMatch, ...]:
    """Return every emphasis a run carries, in a fixed order.

    A run can carry several at once — underlined, highlighted and bold is an ordinary state for a
    card's most important sentence — so this returns a tuple rather than one match.

    **Underline is reported once.** Verbatim encodes it two ways and CardMirror writes both on
    body runs; a run carrying `StyleUnderline` *and* a direct `<w:u>` is one underline, not two.
    `slot` is the structural unit the run sits in, and is used only to record which encoding was
    expected there.
    """
    matches: list[RunStyleMatch] = []
    style_match = profile.resolve_character_style(
        run.character_style_id, run.character_style_name, run.character_style_based_on
    )
    if style_match is not None:
        matches.append(style_match)

    already_underlined = any(match.emphasis is RunEmphasis.UNDERLINE for match in matches)
    if run.is_directly_underlined and not already_underlined:
        expected_here = slot in profile.underline_encoding.direct_slots
        matches.append(
            RunStyleMatch(
                emphasis=RunEmphasis.UNDERLINE,
                rule_id="direct-underline" if expected_here else "direct-underline-in-body-slot",
                match_source=StyleMatchSource.VERBATIM if expected_here else StyleMatchSource.VERBATIM_ALIAS,
                confidence=1.0,
            )
        )

    if run.highlight and profile.highlight_color(run.highlight) is not None:
        matches.append(
            RunStyleMatch(
                emphasis=RunEmphasis.HIGHLIGHT,
                rule_id=f"direct-highlight:{run.highlight}",
                match_source=StyleMatchSource.VERBATIM,
                confidence=1.0,
            )
        )

    if run.bold:
        matches.append(
            RunStyleMatch(
                emphasis=RunEmphasis.BOLD,
                rule_id="direct-bold",
                match_source=StyleMatchSource.VERBATIM,
                confidence=1.0,
            )
        )

    underlined = any(match.emphasis is RunEmphasis.UNDERLINE for match in matches)
    if profile.is_shrunk(run.half_points, underlined=underlined):
        matches.append(
            RunStyleMatch(
                emphasis=RunEmphasis.SHRUNK,
                rule_id=f"shrunk-below-{profile.shrink.maximum_half_points}-half-points",
                match_source=StyleMatchSource.HEURISTIC,
                confidence=0.9,
            )
        )
    return tuple(matches)


# --------------------------------------------------------------------------------------------
# Paragraph classification
# --------------------------------------------------------------------------------------------


def _cite_run_style_match(
    paragraph: ParagraphDescription, profile: StyleProfile
) -> ParagraphStyleMatch | None:
    """A short paragraph whose runs carry the cite character style is a cite line.

    Verbatim gives a cite no paragraph style of its own, so in nearly every real file this is how
    a cite is found. It is a Verbatim match arrived at indirectly, not a guess, which is why it
    is reported as `VERBATIM_ALIAS` rather than as a heuristic.
    """
    if len(paragraph.text) > profile.cite.maximum_cite_characters:
        return None
    for run in paragraph.visible_runs:
        match = profile.resolve_character_style(
            run.character_style_id, run.character_style_name, run.character_style_based_on
        )
        if match is not None and match.emphasis is RunEmphasis.CITE:
            return ParagraphStyleMatch(
                unit=StructuralUnit.CITE,
                rule_id="verbatim-cite-run-style",
                match_source=StyleMatchSource.VERBATIM_ALIAS,
                confidence=1.0,
            )
    return None


def _outline_level_match(
    paragraph: ParagraphDescription, profile: StyleProfile
) -> ParagraphStyleMatch | None:
    """Promote a paragraph that carries an outline level *and* the formatting that goes with it."""
    if paragraph.outline_level is None:
        return None
    for threshold in profile.heuristics:
        if threshold.outline_level != paragraph.outline_level:
            continue
        if threshold.requires_bold and not paragraph.effective_bold:
            return None
        if threshold.requires_underline and not paragraph.has_underlined_run:
            return None
        if threshold.minimum_half_points is not None:
            size = paragraph.effective_half_points
            if size is None or size < threshold.minimum_half_points:
                return None
        return ParagraphStyleMatch(
            unit=threshold.unit,
            rule_id=f"heuristic-outline-level-{threshold.outline_level}",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=threshold.confidence,
        )
    return None


def _wiki_cite_entry_match(
    paragraph: ParagraphDescription, profile: StyleProfile
) -> ParagraphStyleMatch | None:
    """A wiki-converted cite entry: first words, an ellipsis marker, last words.

    These come out of the opencaselist wiki-to-docx conversion, where a disclosure records only
    the beginning and end of a card. The card is ABBREVIATED, not truncated, and `v1-e31-t03`
    flags it as such rather than padding or dropping it.
    """
    text = paragraph.text.strip()
    if not any(marker in text for marker in profile.cite.wiki_ellipsis_markers):
        return None
    if not _compiled(profile.cite.author_year_pattern).search(text):
        return None
    return ParagraphStyleMatch(
        unit=StructuralUnit.CITE,
        rule_id="heuristic-wiki-cite-entry",
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.7,
    )


def _cite_line_match(paragraph: ParagraphDescription, profile: StyleProfile) -> ParagraphStyleMatch | None:
    """A short line that opens with a short cite — `Smith 26`, `Smith et al. 2026`."""
    text = paragraph.text.strip()
    if len(text) > MAXIMUM_CITE_LINE_CHARACTERS:
        return None
    if not _compiled(profile.cite.short_cite_pattern).match(text):
        return None
    return ParagraphStyleMatch(
        unit=StructuralUnit.CITE,
        rule_id="heuristic-cite-line-author-year",
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.6,
    )


def _direct_formatted_heading_match(
    paragraph: ParagraphDescription, profile: StyleProfile
) -> ParagraphStyleMatch | None:
    """A heading expressed only as bold text at a heading size, with no outline level at all.

    This is the wall CardMirror hits and leaves flat, and it is common in wiki conversions and
    Google Docs exports. The size thresholds are the profile's own, read largest first, so a
    26 pt bold line is a pocket and a 13 pt bold line is a tag. The confidences are lower than the
    outline-level rule's because a bold line is weaker evidence than a bold line Word itself has
    marked as a heading.
    """
    if paragraph.outline_level is not None or not paragraph.effective_bold:
        return None
    text = paragraph.text.strip()
    if len(text) > MAXIMUM_HEADING_CHARACTERS:
        return None
    size = paragraph.effective_half_points
    if size is None:
        return None
    sized = sorted(
        (t for t in profile.heuristics if t.minimum_half_points is not None),
        key=lambda t: t.minimum_half_points or 0,
        reverse=True,
    )
    for threshold in sized:
        minimum = threshold.minimum_half_points
        if minimum is not None and size >= minimum:
            if threshold.requires_underline and not paragraph.has_underlined_run:
                continue
            return ParagraphStyleMatch(
                unit=threshold.unit,
                rule_id=f"heuristic-direct-formatted-heading-{threshold.unit.value.lower()}",
                match_source=StyleMatchSource.HEURISTIC,
                confidence=max(threshold.confidence - 0.2, 0.1),
            )
    if size >= profile.shrink.body_half_points:
        return ParagraphStyleMatch(
            unit=StructuralUnit.TAG,
            rule_id="heuristic-direct-formatted-heading-tag",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=0.5,
        )
    return None


def _evidence_match(paragraph: ParagraphDescription, profile: StyleProfile) -> ParagraphStyleMatch | None:
    """Card body: underlined or highlighted text, shrunk text, or plain prose.

    Underlining and highlighting are what a debater does *to* evidence, so a paragraph carrying
    either is card body with very little doubt. Shrunk text is the unread remainder of a card and
    is evidence too. Plain prose long enough to be a paragraph of a source is the weakest of the
    three and says so.
    """
    if paragraph.has_underlined_run or paragraph.has_highlighted_run:
        return ParagraphStyleMatch(
            unit=StructuralUnit.EVIDENCE,
            rule_id="heuristic-marked-up-body-text",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=0.75,
        )
    size = paragraph.effective_half_points
    if profile.is_shrunk(size, underlined=False):
        return ParagraphStyleMatch(
            unit=StructuralUnit.EVIDENCE,
            rule_id="heuristic-shrunk-body-text",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=0.6,
        )
    text = paragraph.text.strip()
    if len(text) >= MINIMUM_PROSE_CHARACTERS and _SENTENCE_END.search(text):
        return ParagraphStyleMatch(
            unit=StructuralUnit.EVIDENCE,
            rule_id="heuristic-prose-paragraph",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=0.4,
        )
    return None


def classify_paragraph(paragraph: ParagraphDescription, profile: StyleProfile) -> ParagraphStyleMatch:
    """Return the structural unit of one paragraph, with the rule that decided it.

    Rules are tried in this order and the first match wins:

    1. the paragraph's own style, through the profile (`VERBATIM` or `VERBATIM_ALIAS`),
    2. a cite character style on one of its runs (`VERBATIM_ALIAS`),
    3. table cells and empty paragraphs, which are `OTHER` whatever else they look like,
    4. outline level plus the formatting that must accompany it,
    5. a wiki-converted cite entry,
    6. a line that opens with a short cite,
    7. a heading expressed only as bold text at a heading size,
    8. card body: marked up, shrunk, or prose,
    9. `OTHER`, which is what a paragraph is when nothing else fits.

    There is always an answer. A caller that wants to know how much to trust it reads
    `confidence` and `match_source`, which is what the parser records on every card.
    """
    style_match = profile.resolve_paragraph_style(
        paragraph.style_id, paragraph.style_name, paragraph.style_based_on
    )
    if style_match is not None:
        return style_match

    cite_match = _cite_run_style_match(paragraph, profile)
    if cite_match is not None:
        return cite_match

    if paragraph.in_table:
        return ParagraphStyleMatch(
            unit=StructuralUnit.OTHER,
            rule_id="heuristic-table-cell",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=1.0,
        )
    if paragraph.is_empty:
        return ParagraphStyleMatch(
            unit=StructuralUnit.OTHER,
            rule_id="heuristic-empty-paragraph",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=1.0,
        )

    for rule in (
        _outline_level_match,
        _wiki_cite_entry_match,
        _cite_line_match,
        _direct_formatted_heading_match,
        _evidence_match,
    ):
        match = rule(paragraph, profile)
        if match is not None:
            return match

    return ParagraphStyleMatch(
        unit=StructuralUnit.OTHER,
        rule_id="heuristic-unclassified-paragraph",
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.5,
    )

"""The one description of what a debate `.docx` looks like, shared by every reader and writer.

A debate file is a Word document shaped by [Verbatim](https://github.com/ashtarcommunications/verbatim),
the Word add-in most US teams use. Verbatim expresses a card's structure in paragraph styles —
`Heading1` is a pocket, `Heading4` is a tag — and its emphasis in character styles and direct run
formatting. Every component that reads or writes one of these files has to agree on that mapping,
so the mapping lives here, as data, once:

* the parser (`v1-e31-t03-debate-docx-parser`) resolves paragraph and run styles through it,
* the heuristic classifier (`debate_core.evidence.style_classifier`) falls back to it for files
  that use no Verbatim styles at all,
* the lossless writer (`v1-e33-t02`) emits the style definitions it records,
* the card format profiles (`v1-e06-t03`) build on the units it names.

Nothing here does I/O. The profile is loaded from a versioned YAML file by
`debate_core.evidence.style_profile_loader`; this module is the shape and the resolution rules.

## Resolving a style, and why the order is what it is

`resolve_paragraph_style` and `resolve_character_style` try five routes, in this order, and the
order is measured rather than chosen — see
[the style survey](../../../../../docs/data/debate-file-style-survey.md):

1. **The canonical style id.** `Heading4` → `TAG`. Match source `VERBATIM`.
2. **A recorded alias id.** `CardBody`, `Analytics`, `UnderlineFIXEDChar`. `VERBATIM_ALIAS`.
3. **The style's display name.** A file whose ids were mangled by a converter often keeps
   `<w:name w:val="heading 4"/>` intact. `VERBATIM_ALIAS`.
4. **Word's numeric de-duplication suffix.** Word appends a digit whenever it imports a style
   whose name collides with one already in the document, one digit per collision, so `Heading 4`
   becomes `Heading 41` and then `Heading 411`. Stripping trailing digits and retrying resolves
   it. `VERBATIM_ALIAS`.
5. **The `basedOn` chain**, nearest ancestor first. `VERBATIM_ALIAS`.

`basedOn` comes **last, and that is the point.** In the surveyed corpus `Heading411` appears in
197 files, and it is a Heading 4 that inherits from `Heading1`. Resolving it by `basedOn` would
call 197 files' tags pockets. The de-duplication rule gets it right, so the de-duplication rule
runs first.

A style that none of the five routes resolves returns `None`, and the caller — the parser, or
`style_classifier` — falls through to the heuristics, whose matches are `HEURISTIC`.

## CardMirror

Every unit and every emphasis records the CardMirror node or mark it corresponds to, per
[ADR-0014](../../../../../docs/adr/0014-debate-file-editor.md). CardMirror's schema is a second,
independent reading of Verbatim's conventions; recording the correspondence means a disagreement
between the two shows up as a failing test rather than as a file nobody can open. The mapping
also records what CardMirror models that we do not, and the reverse, so the coverage test can
tell a deliberate gap from a forgotten one.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText

__all__ = [
    "CardMirrorMarkMapping",
    "CardMirrorNodeMapping",
    "CharacterStyleRule",
    "CiteConvention",
    "HeuristicThreshold",
    "HighlightColor",
    "ParagraphStyleMatch",
    "ParagraphStyleRule",
    "RunEmphasis",
    "RunStyleMatch",
    "ShrinkRule",
    "StructuralUnit",
    "StyleMatchSource",
    "StyleProfile",
    "UnderlineEncodingRule",
    "WriterStyleDefinition",
    "normalize_style_key",
    "strip_deduplication_suffix",
]


# --------------------------------------------------------------------------------------------
# The closed vocabularies
# --------------------------------------------------------------------------------------------


class StructuralUnit(StrEnum):
    """What one paragraph of a debate file *is*.

    The values are the tokens the PlanSpecs use, in `SCREAMING_SNAKE_CASE` like the platform's
    other state enums. The order here is the order a file nests them in: a pocket holds hats,
    a hat holds blocks, a block holds tags, and a tag heads a card.
    """

    POCKET = "POCKET"
    """The outermost heading: an argument file inside a larger document (`Heading1`)."""

    HAT = "HAT"
    """A section of a pocket (`Heading2`)."""

    BLOCK = "BLOCK"
    """A block of cards inside a hat — what a debater reads together (`Heading3`)."""

    TAG = "TAG"
    """The claim a card is read for, written above its cite (`Heading4`). Starts a card."""

    CITE = "CITE"
    """The citation paragraph under a tag. Verbatim gives it no paragraph style of its own; it is
    recognised by its position and by the cite character style its runs carry."""

    EVIDENCE = "EVIDENCE"
    """The card's quoted body text."""

    ANALYTIC = "ANALYTIC"
    """Analysis written by the debater rather than quoted from a source (`Analytic`). It is not
    evidence and is never presented as such."""

    UNDERTAG = "UNDERTAG"
    """A subordinate line under a tag (`Undertag`). Belongs to the tag above it and does not start
    a new card."""

    OTHER = "OTHER"
    """Anything else: unstyled paragraphs, table cells, headers, footers, page furniture."""


class RunEmphasis(StrEnum):
    """What a run's formatting *means*, as opposed to how it is encoded.

    Underline is one member even though Verbatim encodes it two ways — see
    :class:`UnderlineEncodingRule`.
    """

    UNDERLINE = "UNDERLINE"
    """Underlined: the part of the evidence the debater reads aloud."""

    EMPHASIS = "EMPHASIS"
    """Verbatim's `Emphasis`: the words inside the underlining the debater leans on."""

    CITE = "CITE"
    """Cite styling (`Style13ptBold`), which is how a cite paragraph is recognised."""

    UNDERTAG = "UNDERTAG"
    """The run styling that goes with an undertag paragraph (`UndertagChar`)."""

    ANALYTIC = "ANALYTIC"
    """The run styling that goes with an analytic paragraph (`AnalyticChar`)."""

    HIGHLIGHT = "HIGHLIGHT"
    """A `w:highlight` colour. Always direct formatting; no character style carries it."""

    BOLD = "BOLD"
    """Bold, as direct formatting rather than as a consequence of a heading style."""

    SHRUNK = "SHRUNK"
    """Text reduced below the body size so it takes less page room — the part of a card that is
    not read aloud. See :class:`ShrinkRule`."""

    HEADING = "HEADING"
    """A `HeadingNChar` linked character style. It carries a structural style's run formatting
    into a run, which is a formatting fact rather than an emphasis, and CardMirror has no mark
    for it."""


class StyleMatchSource(StrEnum):
    """How a unit or emphasis was arrived at. Recorded on every match, and carried into
    `ParsedCard` provenance by the parser, so a card's structure can always be explained."""

    VERBATIM = "VERBATIM"
    """The style is one of Verbatim's own ids, spelled exactly."""

    VERBATIM_ALIAS = "VERBATIM_ALIAS"
    """A recorded alias, a display name, Word's de-duplication of one, or a `basedOn` ancestor."""

    HEURISTIC = "HEURISTIC"
    """No style matched; the unit came from outline level, size, weight or text shape."""


# --------------------------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------------------------

_SEPARATORS = re.compile(r"[\s\-_()]+")


def normalize_style_key(text: str) -> str:
    """Reduce a style id or name to the form the profile's lookup tables are keyed by.

    `Style 13 pt Bold`, `Style13ptBold` and `style-13pt-bold` are one style wearing three
    spellings; the same normalization is used by `scripts/survey_docx_styles.py` and
    `scripts/compare_docx_roundtrip.py`, because all three are looking at the same files.
    """
    return _SEPARATORS.sub("", text).lower()


def strip_deduplication_suffix(key: str) -> list[str]:
    """Return the successively de-duplicated forms of a normalized style key.

    Word appends one digit per name collision on import, so `heading4` can arrive as `heading41`
    or `heading411`. The returned list is every prefix reachable by removing trailing digits, most
    specific first and excluding `key` itself: `heading411` → `['heading41', 'heading4', 'heading']`.
    Stripping past the first match costs nothing, because the caller returns on the first form that
    resolves.
    """
    forms: list[str] = []
    candidate = key
    while candidate and candidate[-1].isdigit():
        candidate = candidate[:-1]
        if candidate:
            forms.append(candidate)
    return forms


# --------------------------------------------------------------------------------------------
# Style rules
# --------------------------------------------------------------------------------------------


class ParagraphStyleRule(DomainModel):
    """One Verbatim paragraph style and every spelling of it the survey found."""

    unit: StructuralUnit = Field(description="What a paragraph carrying this style is.")
    style_id: NonEmptyText = Field(description="The canonical `w:styleId`, e.g. `Heading4`.")
    style_name: NonEmptyText = Field(description="The canonical `w:name`, e.g. `heading 4`.")
    outline_level: int | None = Field(
        default=None,
        ge=0,
        le=8,
        description="The `w:outlineLvl` the canonical style carries, zero-based; None if it has none.",
    )
    cardmirror_node: str | None = Field(
        default=None, description="The CardMirror node name for this unit, per ADR-0014."
    )
    aliases: tuple[str, ...] = Field(
        default=(),
        description="Other style ids and names seen in real files that mean the same unit.",
    )
    notes: str = Field(default="", description="Why this rule is here, for a later reader.")

    @property
    def lookup_keys(self) -> frozenset[str]:
        """Every normalized key that resolves to this rule."""
        return frozenset(normalize_style_key(key) for key in (self.style_id, self.style_name, *self.aliases))


class CharacterStyleRule(DomainModel):
    """One Verbatim character style and every spelling of it the survey found."""

    emphasis: RunEmphasis = Field(description="What a run carrying this style means.")
    style_id: NonEmptyText = Field(description="The canonical `w:styleId`, e.g. `StyleUnderline`.")
    style_name: NonEmptyText = Field(description="The canonical `w:name`, e.g. `Style Underline`.")
    cardmirror_mark: str | None = Field(
        default=None, description="The CardMirror mark name for this emphasis, per ADR-0014."
    )
    aliases: tuple[str, ...] = Field(
        default=(), description="Other style ids and names that mean the same emphasis."
    )
    notes: str = Field(default="", description="Why this rule is here, for a later reader.")

    @property
    def lookup_keys(self) -> frozenset[str]:
        """Every normalized key that resolves to this rule."""
        return frozenset(normalize_style_key(key) for key in (self.style_id, self.style_name, *self.aliases))


class ParagraphStyleMatch(DomainModel):
    """The result of asking the profile, or the classifier, what a paragraph is."""

    unit: StructuralUnit = Field(description="The resolved structural unit.")
    rule_id: NonEmptyText = Field(
        description="Which rule fired, e.g. `verbatim-style-id:Heading4`. Recorded so a "
        "misclassification can be traced to the rule that caused it."
    )
    match_source: StyleMatchSource = Field(description="Style match, alias match, or heuristic.")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="1.0 for a style match; lower for a heuristic."
    )


class RunStyleMatch(DomainModel):
    """The result of asking the profile what a run's character style means."""

    emphasis: RunEmphasis = Field(description="The resolved emphasis.")
    rule_id: NonEmptyText = Field(description="Which rule fired.")
    match_source: StyleMatchSource = Field(description="Style match, alias match, or heuristic.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in the match.")


# --------------------------------------------------------------------------------------------
# Direct formatting: highlight, underline encoding, shrunk text
# --------------------------------------------------------------------------------------------


class HighlightColor(DomainModel):
    """One `w:highlight` value and what debaters use it for."""

    value: NonEmptyText = Field(description="The OOXML token, e.g. `cyan`. Case-sensitive.")
    reading_color: bool = Field(description="True when this colour is used to mark text that is read aloud.")
    notes: str = Field(default="", description="What the survey saw of this colour.")


class UnderlineEncodingRule(DomainModel):
    """How Verbatim and CardMirror encode underline, and the rule that follows for us.

    Underline is dual-encoded: a named character style in body slots, a direct `<w:u>` in
    structural slots, and CardMirror writes **both** on body runs when it exports. The two are
    one underline. A parser that counts them separately double-counts every underlined run in
    every file CardMirror has touched — which, per the style survey, is most of the corpus.
    """

    named_style_slots: tuple[StructuralUnit, ...] = Field(
        description="Units whose underline is normally the named character style."
    )
    direct_slots: tuple[StructuralUnit, ...] = Field(
        description="Units whose underline is normally a direct `<w:u>` with no character style."
    )
    both_encodings_on_body_runs: bool = Field(
        description="Whether a body run may legitimately carry both encodings at once."
    )
    notes: str = Field(default="", description="The rule in prose, for a later reader.")


class ShrinkRule(DomainModel):
    """When a run counts as shrunk — reduced below body size because it is not read aloud."""

    maximum_half_points: int = Field(
        gt=0,
        description="A run at or below this `w:sz` (half-points) counts as shrunk.",
    )
    body_half_points: int = Field(gt=0, description="The `w:sz` of ordinary, read body text.")
    underlined_text_is_never_shrunk: bool = Field(
        description="Whether underlined text is excluded from the shrunk classification."
    )
    notes: str = Field(default="", description="What the survey measured.")

    @model_validator(mode="after")
    def _check_thresholds(self) -> ShrinkRule:
        if self.maximum_half_points >= self.body_half_points:
            raise ValueError(
                f"shrunk text must be smaller than body text: maximum_half_points "
                f"({self.maximum_half_points}) is not below body_half_points ({self.body_half_points})"
            )
        return self


# --------------------------------------------------------------------------------------------
# Heuristics and cites
# --------------------------------------------------------------------------------------------


class HeuristicThreshold(DomainModel):
    """What a paragraph must look like to be promoted to a unit with no Verbatim style.

    The guards matter as much as the levels. An ordinary Word document that merely uses outline
    levels — a syllabus, a brief — must not come out of the parser as a stack of pockets, so a
    level alone is never enough.
    """

    unit: StructuralUnit = Field(description="The unit this threshold promotes a paragraph to.")
    outline_level: int = Field(ge=0, le=8, description="The required `w:outlineLvl`, zero-based.")
    minimum_half_points: int | None = Field(
        default=None, gt=0, description="Minimum effective `w:sz`, in half-points; None to skip."
    )
    requires_bold: bool = Field(default=False, description="Whether effective bold is required.")
    requires_underline: bool = Field(default=False, description="Whether an underline is required.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence a match by this threshold is reported with."
    )
    notes: str = Field(default="", description="Where the threshold comes from.")


class CiteConvention(DomainModel):
    """How a cite line is recognised, and how the short cite is split out of it.

    A cite carries no paragraph style of its own in Verbatim, so it is found by its cite character
    style, by its position under a tag, or — in files with no styles at all — by its shape. The
    short cite is the part a debater says out loud: `Smith 26`.
    """

    short_cite_pattern: NonEmptyText = Field(
        description="Regular expression matching a short cite at the start of a cite line."
    )
    author_year_pattern: NonEmptyText = Field(
        description="Regular expression matching an author-and-year cite anywhere in a line."
    )
    wiki_ellipsis_markers: tuple[str, ...] = Field(
        default=(),
        description=(
            "Markers a wiki-converted cite entry uses between its first and last words, which is "
            "what makes such a card ABBREVIATED rather than truncated."
        ),
    )
    maximum_cite_characters: int = Field(
        gt=0, description="A cite line longer than this is body text that merely looks like one."
    )
    notes: str = Field(default="", description="Where the conventions come from.")


# --------------------------------------------------------------------------------------------
# What a writer must emit
# --------------------------------------------------------------------------------------------


class WriterStyleDefinition(DomainModel):
    """One style definition a writer puts in `word/styles.xml`.

    These are measured from the corpus, not invented: every value is the one most files carry.
    A writer that emits them produces a file Verbatim's macros key on and Word renders the way a
    debater expects — which is the difference between a real debate file and one that merely
    parses.
    """

    style_id: NonEmptyText = Field(description="The `w:styleId` to write.")
    style_name: NonEmptyText = Field(description="The `w:name` to write.")
    style_type: NonEmptyText = Field(description="`paragraph` or `character`.")
    based_on: str | None = Field(default=None, description="`w:basedOn`, or None for no parent.")
    next_style_id: str | None = Field(
        default=None, description="`w:next`, the style for the following paragraph."
    )
    half_points: int | None = Field(default=None, gt=0, description="`w:sz`, in half-points.")
    bold: bool | None = Field(default=None, description="`w:b`; None leaves it inherited.")
    underline: str | None = Field(
        default=None, description="`w:u w:val`, e.g. `single` or `double`; None leaves it inherited."
    )
    color: str | None = Field(default=None, description="`w:color w:val`, six hex digits.")
    font: str | None = Field(default=None, description="`w:rFonts w:ascii`.")
    outline_level: int | None = Field(default=None, ge=0, le=8, description="`w:outlineLvl`.")
    page_break_before: bool = Field(default=False, description="`w:pageBreakBefore`.")
    keep_with_next: bool = Field(default=False, description="`w:keepNext`.")
    notes: str = Field(default="", description="What the survey measured for this style.")

    @model_validator(mode="after")
    def _check_type(self) -> WriterStyleDefinition:
        if self.style_type not in ("paragraph", "character"):
            raise ValueError(f"style_type must be 'paragraph' or 'character', got {self.style_type!r}")
        if self.color is not None and not re.fullmatch(r"[0-9A-Fa-f]{6}", self.color):
            raise ValueError(f"color must be six hex digits, got {self.color!r}")
        return self


# --------------------------------------------------------------------------------------------
# CardMirror correspondence
# --------------------------------------------------------------------------------------------


class CardMirrorNodeMapping(DomainModel):
    """One CardMirror node and the structural unit it corresponds to, or why there is none."""

    node: NonEmptyText = Field(description="The CardMirror node name, e.g. `cite_paragraph`.")
    unit: StructuralUnit | None = Field(
        default=None, description="Our unit, or None when we deliberately model nothing for it."
    )
    notes: str = Field(default="", description="Why. Required when `unit` is None.")

    @model_validator(mode="after")
    def _explain_gaps(self) -> CardMirrorNodeMapping:
        if self.unit is None and not self.notes:
            raise ValueError(f"CardMirror node {self.node!r} maps to no unit and says no why")
        return self


class CardMirrorMarkMapping(DomainModel):
    """One CardMirror mark and the run emphasis it corresponds to, or why there is none."""

    mark: NonEmptyText = Field(description="The CardMirror mark name, e.g. `underline_mark`.")
    emphasis: RunEmphasis | None = Field(
        default=None, description="Our emphasis, or None when we model nothing for it."
    )
    notes: str = Field(default="", description="Why. Required when `emphasis` is None.")

    @model_validator(mode="after")
    def _explain_gaps(self) -> CardMirrorMarkMapping:
        if self.emphasis is None and not self.notes:
            raise ValueError(f"CardMirror mark {self.mark!r} maps to no emphasis and says no why")
        return self


# --------------------------------------------------------------------------------------------
# The profile
# --------------------------------------------------------------------------------------------


class StyleProfile(DomainModel):
    """Everything a reader or writer of debate `.docx` files needs to agree on.

    Loaded from `debate_core/evidence/style_profiles/<name>.yaml`. `profile_version` is recorded
    on every `ParsedCard` the parser emits, so a card can always be re-read under the profile it
    was parsed with.
    """

    profile_version: NonEmptyText = Field(
        description="Version of this profile's contents. Bumped whenever a rule changes."
    )
    name: NonEmptyText = Field(description="Short name, e.g. `verbatim`.")
    description: NonEmptyText = Field(description="One paragraph on what this profile covers.")
    paragraph_styles: tuple[ParagraphStyleRule, ...] = Field(
        description="Paragraph style rules, one per structural unit that has a style."
    )
    character_styles: tuple[CharacterStyleRule, ...] = Field(
        description="Character style rules, one per emphasis that has a style."
    )
    highlight_colors: tuple[HighlightColor, ...] = Field(description="Recognised `w:highlight` values.")
    underline_encoding: UnderlineEncodingRule = Field(description="The dual-encoding rule.")
    shrink: ShrinkRule = Field(description="When a run counts as shrunk.")
    heuristics: tuple[HeuristicThreshold, ...] = Field(
        description="Thresholds for files that carry no Verbatim styles."
    )
    cite: CiteConvention = Field(description="How cite lines and short cites are recognised.")
    writer_style_definitions: tuple[WriterStyleDefinition, ...] = Field(
        description="The style definitions a writer emits."
    )
    cardmirror_nodes: tuple[CardMirrorNodeMapping, ...] = Field(
        description="Every CardMirror node, mapped to a unit or explicitly not."
    )
    cardmirror_marks: tuple[CardMirrorMarkMapping, ...] = Field(
        description="Every CardMirror mark, mapped to an emphasis or explicitly not."
    )

    @model_validator(mode="after")
    def _check_tables_are_unambiguous(self) -> StyleProfile:
        for label, rules in (
            ("paragraph", [rule.lookup_keys for rule in self.paragraph_styles]),
            ("character", [rule.lookup_keys for rule in self.character_styles]),
        ):
            seen: dict[str, int] = {}
            for index, keys in enumerate(rules):
                for key in keys:
                    if key in seen:
                        raise ValueError(
                            f"{label} style key {key!r} resolves to two rules "
                            f"(entries {seen[key]} and {index}); a lookup would be ambiguous"
                        )
                    seen[key] = index
        units_with_styles = {rule.unit for rule in self.paragraph_styles}
        missing = units_with_styles - {
            mapping.unit for mapping in self.cardmirror_nodes if mapping.unit is not None
        }
        if missing:
            raise ValueError(
                "every unit that has a paragraph style must record a CardMirror node; missing: "
                + ", ".join(sorted(unit.value for unit in missing))
            )
        return self

    # -- lookups ------------------------------------------------------------------------------

    def _resolve_paragraph_key(self, key: str) -> ParagraphStyleRule | None:
        for rule in self.paragraph_styles:
            if key in rule.lookup_keys:
                return rule
        return None

    def _resolve_character_key(self, key: str) -> CharacterStyleRule | None:
        for rule in self.character_styles:
            if key in rule.lookup_keys:
                return rule
        return None

    def resolve_paragraph_style(
        self,
        style_id: str | None,
        style_name: str | None = None,
        based_on_chain: tuple[str, ...] = (),
    ) -> ParagraphStyleMatch | None:
        """Resolve a paragraph style to a structural unit, or return None.

        `based_on_chain` is the style's ancestors, nearest first, as read from `word/styles.xml`.
        Returning None is not a failure: it is the signal to fall through to the heuristics.
        """
        if style_id:
            key = normalize_style_key(style_id)
            rule = self._resolve_paragraph_key(key)
            if rule is not None:
                exact = key == normalize_style_key(rule.style_id)
                return ParagraphStyleMatch(
                    unit=rule.unit,
                    rule_id=f"verbatim-style-id:{rule.style_id}"
                    if exact
                    else f"verbatim-alias-id:{style_id}",
                    match_source=StyleMatchSource.VERBATIM if exact else StyleMatchSource.VERBATIM_ALIAS,
                )
        if style_name:
            rule = self._resolve_paragraph_key(normalize_style_key(style_name))
            if rule is not None:
                return ParagraphStyleMatch(
                    unit=rule.unit,
                    rule_id=f"verbatim-alias-name:{style_name}",
                    match_source=StyleMatchSource.VERBATIM_ALIAS,
                )
        for candidate in (style_id, style_name):
            if not candidate:
                continue
            for stripped in strip_deduplication_suffix(normalize_style_key(candidate)):
                rule = self._resolve_paragraph_key(stripped)
                if rule is not None:
                    return ParagraphStyleMatch(
                        unit=rule.unit,
                        rule_id=f"verbatim-deduplicated:{candidate}->{rule.style_id}",
                        match_source=StyleMatchSource.VERBATIM_ALIAS,
                    )
        for ancestor in based_on_chain:
            rule = self._resolve_paragraph_key(normalize_style_key(ancestor))
            if rule is not None:
                return ParagraphStyleMatch(
                    unit=rule.unit,
                    rule_id=f"verbatim-based-on:{ancestor}",
                    match_source=StyleMatchSource.VERBATIM_ALIAS,
                )
        return None

    def resolve_character_style(
        self,
        style_id: str | None,
        style_name: str | None = None,
        based_on_chain: tuple[str, ...] = (),
    ) -> RunStyleMatch | None:
        """Resolve a character style to a run emphasis, or return None.

        The same five routes, in the same order, for the same reasons.
        """
        if style_id:
            key = normalize_style_key(style_id)
            rule = self._resolve_character_key(key)
            if rule is not None:
                exact = key == normalize_style_key(rule.style_id)
                return RunStyleMatch(
                    emphasis=rule.emphasis,
                    rule_id=f"verbatim-style-id:{rule.style_id}"
                    if exact
                    else f"verbatim-alias-id:{style_id}",
                    match_source=StyleMatchSource.VERBATIM if exact else StyleMatchSource.VERBATIM_ALIAS,
                )
        if style_name:
            rule = self._resolve_character_key(normalize_style_key(style_name))
            if rule is not None:
                return RunStyleMatch(
                    emphasis=rule.emphasis,
                    rule_id=f"verbatim-alias-name:{style_name}",
                    match_source=StyleMatchSource.VERBATIM_ALIAS,
                )
        for candidate in (style_id, style_name):
            if not candidate:
                continue
            for stripped in strip_deduplication_suffix(normalize_style_key(candidate)):
                rule = self._resolve_character_key(stripped)
                if rule is not None:
                    return RunStyleMatch(
                        emphasis=rule.emphasis,
                        rule_id=f"verbatim-deduplicated:{candidate}->{rule.style_id}",
                        match_source=StyleMatchSource.VERBATIM_ALIAS,
                    )
        for ancestor in based_on_chain:
            rule = self._resolve_character_key(normalize_style_key(ancestor))
            if rule is not None:
                return RunStyleMatch(
                    emphasis=rule.emphasis,
                    rule_id=f"verbatim-based-on:{ancestor}",
                    match_source=StyleMatchSource.VERBATIM_ALIAS,
                )
        return None

    def cardmirror_node_for(self, unit: StructuralUnit) -> str | None:
        """The CardMirror node name for `unit`, or None when CardMirror has no node for it."""
        for mapping in self.cardmirror_nodes:
            if mapping.unit is unit:
                return mapping.node
        return None

    def cardmirror_marks_for(self, emphasis: RunEmphasis) -> tuple[str, ...]:
        """Every CardMirror mark that carries `emphasis`.

        A tuple rather than one name because underline has two: the named style and the direct
        `<w:u>`, which are one underline to us.
        """
        return tuple(mapping.mark for mapping in self.cardmirror_marks if mapping.emphasis is emphasis)

    def highlight_color(self, value: str) -> HighlightColor | None:
        """The recorded meaning of a `w:highlight` value, or None if the profile has not seen it."""
        for color in self.highlight_colors:
            if color.value == value:
                return color
        return None

    def is_shrunk(self, half_points: int | None, *, underlined: bool) -> bool:
        """Whether a run at `half_points` counts as shrunk, per :class:`ShrinkRule`."""
        if half_points is None:
            return False
        if underlined and self.shrink.underlined_text_is_never_shrunk:
            return False
        return half_points <= self.shrink.maximum_half_points

    def writer_style_definition(self, style_id: str) -> WriterStyleDefinition | None:
        """The definition a writer should emit for `style_id`, or None if the profile has none."""
        key = normalize_style_key(style_id)
        for definition in self.writer_style_definitions:
            if normalize_style_key(definition.style_id) == key:
                return definition
        return None

"""Deterministic, versioned normalization of the text evidence is quoted from.

The rules are written down in ``docs/evidence/normalization.md``, which is the contract. This
module implements them. In short, for ``evidence-normalizer-v1``:

1. Horizontal whitespace, line breaks and U+2029 form *gaps* between runs of content.
2. Soft hyphen, zero-width space, word joiner and the byte-order mark are deleted, joining the
   content on either side.
3. Each run of content is put in Unicode NFC (Unicode 15.0.0, pinned).
4. A gap becomes one space, or ``"\\n\\n"`` when it holds a blank line, and gaps at either end of
   the text are dropped. The normalized text is split into paragraphs ``p0001``, ``p0002``, ...
   at every ``"\\n\\n"``.

Nothing else changes: no case folding, no quote or dash folding, no ligature expansion, no
rejoining of hyphenated words. This is the opposite job to the matching-only normalization in
:mod:`debate_core.evidence.fingerprints` (``v1-e31-t04``), which is lossy by design and whose output
is never stored. The two share no code on purpose.

## Versions are frozen

A snapshot's normalized-text hash (``v1-e03-t02``) and a card's offsets (``v1-e03-t03``) mean
something only under the rules that produced them, so :func:`normalize` takes the version as a
required argument. Every released version stays in :data:`SUPPORTED_NORMALIZER_VERSIONS` with its
rules and implementation untouched. A rule change adds a new version beside the old ones and never
edits one: ``_V1_RULES`` and ``_normalize_characters_v1`` are frozen as of v1's release.

## Offsets

:class:`OffsetMap` aligns the raw text with the normalized text as a sequence of segments. It is
built while the rules apply, never reconstructed afterwards by searching. Offsets are Python
string indices, which count code points.

## Determinism

No I/O, randomness, locale or clock. Character classes come from the explicit tables in
``_V1_RULES``, never from ``str.isspace()`` or a regex ``\\s``, whose membership follows the
running Python's Unicode version. The single external dependency, the Unicode database behind
:func:`unicodedata.normalize`, is checked against the version's pinned database on every call.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cache
from types import MappingProxyType
from typing import Final

__all__ = [
    "NORMALIZER_VERSION",
    "SUPPORTED_NORMALIZER_VERSIONS",
    "CharacterNormalization",
    "CharacterRules",
    "InvalidTextError",
    "NormalizationError",
    "NormalizedText",
    "OffsetMap",
    "OffsetSegment",
    "Paragraph",
    "UnicodeDatabaseMismatchError",
    "UnknownNormalizerVersionError",
    "UnknownParagraphError",
    "character_rules",
    "nfc_composing_code_points",
    "nfc_replaced_code_points",
    "normalize",
    "normalize_chars",
]

NORMALIZER_VERSION: Final = "evidence-normalizer-v1"
"""The version new snapshots are normalized under. Re-verification passes the card's own version."""


class NormalizationError(Exception):
    """Base class for every error the evidence normalizer raises."""


class UnknownNormalizerVersionError(NormalizationError, ValueError):
    """The requested normalizer version does not exist. There is never a fallback to another one."""


class UnicodeDatabaseMismatchError(NormalizationError, RuntimeError):
    """The running Python's Unicode database is not the one this normalizer version is pinned to."""


class InvalidTextError(NormalizationError, ValueError):
    """The input is not valid Unicode text (it contains a lone surrogate)."""


class UnknownParagraphError(NormalizationError, KeyError):
    """No paragraph with the requested ID exists in this normalized text."""


# ---------------------------------------------------------------------------------------------
# Rule tables
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CharacterRules:
    """One version's character classes. Every code point not listed here is content."""

    version: str
    unicode_version: str
    horizontal_whitespace: frozenset[str]
    line_breaks: frozenset[str]
    paragraph_separators: frozenset[str]
    removed: frozenset[str]


_V1_RULES: Final = CharacterRules(
    version="evidence-normalizer-v1",
    unicode_version="15.0.0",
    horizontal_whitespace=frozenset(
        "\u0009"  # CHARACTER TABULATION
        " "  # SPACE
        " "  # NO-BREAK SPACE
        " "  # OGHAM SPACE MARK
        " "  # EN QUAD
        " "  # EM QUAD
        " "  # EN SPACE
        " "  # EM SPACE
        " "  # THREE-PER-EM SPACE
        " "  # FOUR-PER-EM SPACE
        " "  # SIX-PER-EM SPACE
        " "  # FIGURE SPACE
        " "  # PUNCTUATION SPACE
        " "  # THIN SPACE
        " "  # HAIR SPACE
        " "  # NARROW NO-BREAK SPACE
        " "  # MEDIUM MATHEMATICAL SPACE
        "　"  # IDEOGRAPHIC SPACE
    ),
    line_breaks=frozenset(
        "\u000a"  # LINE FEED
        "\u000b"  # LINE TABULATION
        "\u000c"  # FORM FEED
        "\u000d"  # CARRIAGE RETURN (CR LF counts as one line break)
        "\u0085"  # NEXT LINE
        " "  # LINE SEPARATOR
    ),
    paragraph_separators=frozenset(" "),  # PARAGRAPH SEPARATOR
    removed=frozenset(
        "­"  # SOFT HYPHEN
        "​"  # ZERO WIDTH SPACE
        "⁠"  # WORD JOINER
        "﻿"  # ZERO WIDTH NO-BREAK SPACE (byte-order mark)
    ),
)

_CONTENT: Final = 0
_HORIZONTAL_WHITESPACE: Final = 1
_LINE_BREAK: Final = 2
_PARAGRAPH_SEPARATOR: Final = 3
_REMOVED: Final = 4

_SPACE: Final = " "
_PARAGRAPH_BREAK: Final = "\n\n"
_LONE_SURROGATE: Final = re.compile("[\ud800-\udfff]")

# The last code point with a canonical decomposition in any Unicode version to date is in plane 2
# (CJK COMPATIBILITY IDEOGRAPH-2FA1D); scanning planes 0-2 covers the whole database.
_DECOMPOSITION_SCAN_LIMIT: Final = 0x30000
_HANGUL_VOWEL_JAMO: Final = range(0x1161, 0x1176)
_HANGUL_TRAILING_JAMO: Final = range(0x11A8, 0x11C3)


@cache
def _class_table(rules: CharacterRules) -> Mapping[str, int]:
    table: dict[str, int] = {}
    for character in rules.horizontal_whitespace:
        table[character] = _HORIZONTAL_WHITESPACE
    for character in rules.line_breaks:
        table[character] = _LINE_BREAK
    for character in rules.paragraph_separators:
        table[character] = _PARAGRAPH_SEPARATOR
    for character in rules.removed:
        table[character] = _REMOVED
    return MappingProxyType(table)


@cache
def nfc_replaced_code_points() -> frozenset[int]:
    """Code points NFC always replaces, under the running Unicode database.

    The policy's appendix lists them for Unicode 15.0.0, and a test holds the two equal.
    """
    return frozenset(
        code_point
        for code_point in range(0x110000)
        if not 0xD800 <= code_point <= 0xDFFF
        and unicodedata.normalize("NFC", chr(code_point)) != chr(code_point)
    )


@cache
def nfc_composing_code_points() -> frozenset[int]:
    """Code points NFC may compose with a preceding character, under the running database.

    These are the second halves of every primary composite (a canonical pair that NFC recomposes),
    plus the Hangul vowel and trailing jamo, whose composition is algorithmic rather than listed.
    """
    composing: set[int] = set(_HANGUL_VOWEL_JAMO) | set(_HANGUL_TRAILING_JAMO)
    for code_point in range(_DECOMPOSITION_SCAN_LIMIT):
        if 0xD800 <= code_point <= 0xDFFF:
            continue
        decomposition = unicodedata.decomposition(chr(code_point))
        if not decomposition or decomposition.startswith("<"):
            continue
        parts = decomposition.split()
        if len(parts) != 2:
            continue
        first, second = chr(int(parts[0], 16)), chr(int(parts[1], 16))
        if unicodedata.normalize("NFC", first + second) == chr(code_point):
            composing.add(ord(second))
    return frozenset(composing)


@cache
def _starts_independent_nfc_run(character: str) -> bool:
    """True where NFC of the text before ``character`` cannot depend on what follows it.

    That holds before a starter (canonical combining class 0) that NFC leaves alone and that never
    composes with a preceding character, the ``NFC_Quick_Check=Yes`` starters of UAX #15. Content
    is normalized run by run between such boundaries, so the offset map can keep every unchanged
    character one to one and has to treat only a changed run as a unit.
    """
    return (
        unicodedata.combining(character) == 0
        and ord(character) not in nfc_composing_code_points()
        and unicodedata.is_normalized("NFC", character)
    )


# ---------------------------------------------------------------------------------------------
# Offset map
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OffsetSegment:
    """One aligned piece of raw and normalized text.

    ``exact`` segments are copied unchanged, character for character. Other segments were
    replaced (a whitespace gap, a deleted character or an NFC-changed run) and map only as a unit;
    a deletion has an empty normalized side.
    """

    raw_start: int
    raw_end: int
    normalized_start: int
    normalized_end: int
    exact: bool


@dataclass(frozen=True, slots=True)
class OffsetMap:
    """Bidirectional map between raw-text and normalized-text offsets (``[start, end)`` ranges)."""

    segments: tuple[OffsetSegment, ...]
    raw_length: int
    normalized_length: int
    _raw_starts: tuple[int, ...] = field(init=False, repr=False, compare=False)
    _visible: tuple[int, ...] = field(init=False, repr=False, compare=False)
    _visible_starts: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        raw_position = 0
        normalized_position = 0
        for segment in self.segments:
            raw_length = segment.raw_end - segment.raw_start
            normalized_length = segment.normalized_end - segment.normalized_start
            if (
                segment.raw_start != raw_position
                or segment.normalized_start != normalized_position
                or raw_length <= 0
                or normalized_length < 0
                or (segment.exact and raw_length != normalized_length)
            ):
                raise ValueError(f"offset segments are not a contiguous alignment at {segment!r}")
            raw_position = segment.raw_end
            normalized_position = segment.normalized_end
        if raw_position != self.raw_length or normalized_position != self.normalized_length:
            raise ValueError("offset segments do not cover both texts")
        visible = tuple(
            index
            for index, segment in enumerate(self.segments)
            if segment.normalized_end > segment.normalized_start
        )
        object.__setattr__(self, "_raw_starts", tuple(s.raw_start for s in self.segments))
        object.__setattr__(self, "_visible", visible)
        object.__setattr__(self, "_visible_starts", tuple(self.segments[i].normalized_start for i in visible))

    def to_raw_range(self, start: int, end: int) -> tuple[int, int]:
        """The smallest raw range whose characters produced normalized ``[start, end)``.

        An edge inside a replaced segment widens to the whole segment. Deleted raw characters just
        outside the range are left out.
        """
        _check_range(start, end, self.normalized_length, "normalized")
        if start == end:
            position = (
                self._raw_position_starting_at(start)
                if start < self.normalized_length
                else self._raw_position_ending_at(start)
            )
            return position, position
        return self._raw_position_starting_at(start), self._raw_position_ending_at(end)

    def to_normalized_range(self, start: int, end: int) -> tuple[int, int]:
        """The normalized range that raw ``[start, end)`` became, widened to whole segments."""
        _check_range(start, end, self.raw_length, "raw")
        if start == end:
            if start == self.raw_length:
                return self.normalized_length, self.normalized_length
            position = self._normalized_position_starting_at(start)
            return position, position
        return self._normalized_position_starting_at(start), self._normalized_position_ending_at(end)

    def _raw_position_starting_at(self, normalized: int) -> int:
        segment = self.segments[self._visible[bisect.bisect_right(self._visible_starts, normalized) - 1]]
        if segment.exact:
            return segment.raw_start + (normalized - segment.normalized_start)
        return segment.raw_start

    def _raw_position_ending_at(self, normalized: int) -> int:
        if normalized == 0:
            return 0
        segment = self.segments[self._visible[bisect.bisect_left(self._visible_starts, normalized) - 1]]
        if segment.exact:
            return segment.raw_start + (normalized - segment.normalized_start)
        return segment.raw_end

    def _normalized_position_starting_at(self, raw: int) -> int:
        segment = self.segments[bisect.bisect_right(self._raw_starts, raw) - 1]
        if segment.exact:
            return segment.normalized_start + (raw - segment.raw_start)
        return segment.normalized_start

    def _normalized_position_ending_at(self, raw: int) -> int:
        segment = self.segments[bisect.bisect_left(self._raw_starts, raw) - 1]
        if segment.exact:
            return segment.normalized_start + (raw - segment.raw_start)
        return segment.normalized_end


def _check_range(start: int, end: int, length: int, side: str) -> None:
    if not 0 <= start <= end <= length:
        raise ValueError(f"{side} range [{start}, {end}) is outside [0, {length}]")


class _SegmentBuilder:
    """Appends segments in raw order; raw text it is never told about becomes a deletion."""

    def __init__(self) -> None:
        self.segments: list[OffsetSegment] = []
        self.raw_position = 0
        self.normalized_position = 0

    def copy(self, raw_start: int, raw_end: int) -> None:
        self._delete_up_to(raw_start)
        self._append(raw_end, raw_end - raw_start, exact=True)

    def replace(self, raw_start: int, raw_end: int, normalized_length: int) -> None:
        self._delete_up_to(raw_start)
        self._append(raw_end, normalized_length, exact=False)

    def finish(self, raw_length: int) -> tuple[OffsetSegment, ...]:
        self._delete_up_to(raw_length)
        return tuple(self.segments)

    def _delete_up_to(self, raw_start: int) -> None:
        if raw_start > self.raw_position:
            self._append(raw_start, 0, exact=False)

    def _append(self, raw_end: int, normalized_length: int, *, exact: bool) -> None:
        normalized_end = self.normalized_position + normalized_length
        previous = self.segments[-1] if self.segments else None
        mergeable = previous is not None and (
            (exact and previous.exact)
            or (
                normalized_length == 0
                and not previous.exact
                and previous.normalized_start == previous.normalized_end
            )
        )
        if previous is not None and mergeable:
            self.segments[-1] = OffsetSegment(
                previous.raw_start,
                raw_end,
                previous.normalized_start,
                normalized_end,
                exact,
            )
        else:
            self.segments.append(
                OffsetSegment(self.raw_position, raw_end, self.normalized_position, normalized_end, exact)
            )
        self.raw_position = raw_end
        self.normalized_position = normalized_end


# ---------------------------------------------------------------------------------------------
# evidence-normalizer-v1 (frozen)
# ---------------------------------------------------------------------------------------------


def _normalize_characters_v1(text: str, rules: CharacterRules) -> tuple[str, tuple[OffsetSegment, ...]]:
    """Apply the v1 character rules in one pass, recording the alignment as each rule applies."""
    classes = _class_table(rules)
    output: list[str] = []
    builder = _SegmentBuilder()

    content: list[str] = []  # the current content run, removed characters already dropped
    origins: list[int] = []  # raw index of each character in ``content``
    gap_start = 0
    gap_has_whitespace = False
    gap_line_breaks = 0
    gap_has_paragraph_separator = False

    def flush_content() -> None:
        run_start = 0
        for index in range(1, len(content) + 1):
            if index < len(content) and not _starts_independent_nfc_run(content[index]):
                continue
            chunk = "".join(content[run_start:index])
            composed = unicodedata.normalize("NFC", chunk)
            if composed == chunk:
                for position in range(run_start, index):
                    builder.copy(origins[position], origins[position] + 1)
            else:
                builder.replace(origins[run_start], origins[index - 1] + 1, len(composed))
            output.append(composed)
            run_start = index
        content.clear()
        origins.clear()

    for index, character in enumerate(text):
        kind = classes.get(character, _CONTENT)
        if kind == _CONTENT:
            if content and gap_has_whitespace:
                flush_content()
                separator = (
                    _PARAGRAPH_BREAK if gap_has_paragraph_separator or gap_line_breaks >= 2 else _SPACE
                )
                if text[gap_start:index] == separator:
                    builder.copy(gap_start, index)
                else:
                    builder.replace(gap_start, index, len(separator))
                output.append(separator)
            content.append(character)
            origins.append(index)
            gap_start = index + 1
            gap_has_whitespace = False
            gap_line_breaks = 0
            gap_has_paragraph_separator = False
        elif kind == _HORIZONTAL_WHITESPACE:
            gap_has_whitespace = True
        elif kind == _LINE_BREAK:
            gap_has_whitespace = True
            if not (character == "\r" and text[index + 1 : index + 2] == "\n"):
                gap_line_breaks += 1
        elif kind == _PARAGRAPH_SEPARATOR:
            gap_has_whitespace = True
            gap_has_paragraph_separator = True
        # _REMOVED: dropped. The builder records it as a deletion when it moves past it.

    flush_content()
    return "".join(output), builder.finish(len(text))


def _paragraph_id_v1(number: int) -> str:
    return f"p{number:04d}"


def _segment_paragraphs_v1(normalized: str) -> tuple[Paragraph, ...]:
    if not normalized:
        return ()
    paragraphs: list[Paragraph] = []
    start = 0
    for number, body in enumerate(normalized.split(_PARAGRAPH_BREAK), start=1):
        paragraphs.append(Paragraph(_paragraph_id_v1(number), start, start + len(body)))
        start += len(body) + len(_PARAGRAPH_BREAK)
    return tuple(paragraphs)


# ---------------------------------------------------------------------------------------------
# Version registry and public API
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _NormalizerDefinition:
    rules: CharacterRules
    normalize_characters: Callable[[str, CharacterRules], tuple[str, tuple[OffsetSegment, ...]]]
    segment_paragraphs: Callable[[str], tuple[Paragraph, ...]]


_DEFINITIONS: Final[Mapping[str, _NormalizerDefinition]] = MappingProxyType(
    {
        _V1_RULES.version: _NormalizerDefinition(_V1_RULES, _normalize_characters_v1, _segment_paragraphs_v1),
    }
)

SUPPORTED_NORMALIZER_VERSIONS: Final[tuple[str, ...]] = tuple(_DEFINITIONS)
"""Every version ever released, oldest first. Versions are added here, never removed."""


def _definition(version: str) -> _NormalizerDefinition:
    definition = _DEFINITIONS.get(version)
    if definition is None:
        raise UnknownNormalizerVersionError(
            f"unknown normalizer version {version!r}; supported: " + ", ".join(SUPPORTED_NORMALIZER_VERSIONS)
        )
    if unicodedata.unidata_version != definition.rules.unicode_version:
        raise UnicodeDatabaseMismatchError(
            f"{version} is pinned to Unicode {definition.rules.unicode_version}, but this Python's "
            f"unicodedata is {unicodedata.unidata_version}; see docs/evidence/normalization.md"
        )
    return definition


def character_rules(version: str) -> CharacterRules:
    """The character tables of ``version``."""
    return _definition(version).rules


@dataclass(frozen=True, slots=True)
class CharacterNormalization:
    """The result of the character rules alone, before paragraph segmentation."""

    text: str
    normalizer_version: str
    offset_map: OffsetMap


@dataclass(frozen=True, slots=True)
class Paragraph:
    """One paragraph of normalized text: ``text[start:end]``, never containing a paragraph break."""

    paragraph_id: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class NormalizedText:
    """Normalized text, the version that produced it, its paragraphs and its raw offset map."""

    text: str
    normalizer_version: str
    paragraphs: tuple[Paragraph, ...]
    offset_map: OffsetMap

    def paragraph(self, paragraph_id: str) -> Paragraph:
        """The paragraph with ``paragraph_id``, or :class:`UnknownParagraphError`."""
        for paragraph in self.paragraphs:
            if paragraph.paragraph_id == paragraph_id:
                return paragraph
        raise UnknownParagraphError(paragraph_id)

    def paragraph_text(self, paragraph_id: str) -> str:
        paragraph = self.paragraph(paragraph_id)
        return self.text[paragraph.start : paragraph.end]

    def to_raw_range(self, start: int, end: int) -> tuple[int, int]:
        """See :meth:`OffsetMap.to_raw_range`."""
        return self.offset_map.to_raw_range(start, end)

    def to_normalized_range(self, start: int, end: int) -> tuple[int, int]:
        """See :meth:`OffsetMap.to_normalized_range`."""
        return self.offset_map.to_normalized_range(start, end)


def normalize_chars(text: str, version: str) -> CharacterNormalization:
    """Apply ``version``'s character rules to raw extracted ``text``, with the offset map."""
    definition = _definition(version)
    if _LONE_SURROGATE.search(text):
        raise InvalidTextError("text contains a lone surrogate and is not valid Unicode")
    normalized, segments = definition.normalize_characters(text, definition.rules)
    return CharacterNormalization(
        text=normalized,
        normalizer_version=version,
        offset_map=OffsetMap(segments, raw_length=len(text), normalized_length=len(normalized)),
    )


def normalize(text: str, version: str) -> NormalizedText:
    """Normalize raw extracted ``text`` under ``version`` (usually :data:`NORMALIZER_VERSION`)."""
    characters = normalize_chars(text, version)
    return NormalizedText(
        text=characters.text,
        normalizer_version=version,
        paragraphs=_DEFINITIONS[version].segment_paragraphs(characters.text),
        offset_map=characters.offset_map,
    )

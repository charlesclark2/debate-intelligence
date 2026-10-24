"""The headings over one stored card, read the one way seeding and the matcher both read them.

A taxonomy's aliases were seeded from headings read by these rules (`v1-e32-t01`), so the matcher
(`v1-e32-t02`) must read a heading by the same rules or an alias stops finding the heading it came
from. This module is that one reading; neither caller has a second.

* **The path.** A stored card's `section_path` holds the headings above it, outermost first, and
  leaves out a level the file skipped. A card the file gave no tag carries the tag still open
  above it as its last entry, which is a claim and not a heading; :func:`heading_path` drops it
  when it equals a tag in the same document. Anything past the third entry (pocket, hat, block)
  goes too.
* **The words.** Each heading is normalized
  (:func:`~debate_core.arguments.landscape.headings.normalize_heading`) with the disclosing team's
  own school, team code and tournament taken out first (:func:`normalize_source_heading`), and then
  every school the caselist's paths name, with that school's codes beside it
  (:class:`CaselistNames`).

Pure and deterministic: names arrive as arguments and are never logged or returned in a `repr`.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Final

from debate_core.arguments.landscape.headings import NormalizedHeading, normalize_heading

__all__ = ["HEADING_LEVELS", "CaselistNames", "heading_path", "normalize_source_heading"]

HEADING_LEVELS: Final = 3
"""Pocket, hat and block: the headings a path holds before the tags begin."""


def heading_path(
    tag: str | None, section_path: Sequence[str], document_tags: Collection[str]
) -> tuple[str, ...]:
    """The headings over a card: its path without an open tag, cut to :data:`HEADING_LEVELS`."""
    path = tuple(section_path)
    if tag is None and path and path[-1] in document_tags:
        path = path[:-1]
    return path[:HEADING_LEVELS]


class CaselistNames:
    """Every school of the caselist, and its codes, taken out of a normalized heading; cached by text."""

    def __init__(self, names: Mapping[str, Sequence[str]]) -> None:
        self._schools: list[tuple[str, tuple[str, ...]]] = []
        for name, codes in sorted(names.items()):
            school = _plain_words(name)
            if school:
                self._schools.append((school, tuple(code for code in map(_plain_words, codes) if code)))
        self._done: dict[str, str] = {}

    def __repr__(self) -> str:
        return f"CaselistNames(<{len(self._schools)} schools withheld>)"

    def __call__(self, text: str) -> str:
        found = self._done.get(text)
        if found is None:
            found = self.without_schools(text)
            if found != text:
                found = normalize_heading(found).text
            self._done[text] = found
        return found

    def without_schools(self, text: str) -> str:
        """`text`, lowercase words one space apart, without any school and the codes beside it.

        Not normalized again, so words that are not a heading (a plan text's, `v1-e32-t09`) keep their
        shape.
        """
        found = text
        for school, codes in self._schools:
            if f" {school} " in f" {found} ":
                found = _without_words(found, (school, *codes))
        return found


def normalize_source_heading(
    raw: str, own_names: Sequence[str], caselist: CaselistNames
) -> NormalizedHeading:
    """`raw` normalized, without the disclosing teams' own names or any school of the caselist."""
    normalized = _normalized_without_names(raw, own_names)
    if not normalized.text:
        return normalized
    text = caselist(normalized.text)
    return normalized if text == normalized.text else NormalizedHeading(text=text, answer=normalized.answer)


def _plain_words(name: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", name.casefold()).split())


def _without_words(text: str, phrases: Sequence[str]) -> str:
    for phrase in phrases:
        text = re.sub(rf"(?<!\S){re.escape(phrase)}(?!\S)", " ", text)
    return " ".join(text.split())


def _normalized_without_names(raw: str, names: Sequence[str]) -> NormalizedHeading:
    """`raw` normalized, with the disclosing teams' own school and team code taken out first."""
    for name in names:
        words = name.split()
        pattern = (
            r"(?<![0-9A-Za-z])" + r"[\s_-]+".join(re.escape(word) for word in words) + r"(?![0-9A-Za-z])"
        )
        raw = re.sub(pattern, " ", raw, flags=re.IGNORECASE)
    normalized = normalize_heading(raw)
    text = normalized.text
    for name in names:
        name_text = normalize_heading(name).text
        if name_text:
            text = " ".join(re.sub(rf"(?<!\S){re.escape(name_text)}(?!\S)", " ", text).split())
    return normalize_heading(text) if text != normalized.text else normalized

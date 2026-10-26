"""A card's free text as words, without the names of the teams that disclosed it or the caselist's.

A heading is normalized with the disclosing teams' own names and the caselist's schools taken out
(:mod:`~debate_core.arguments.landscape.source_headings`). A tag, a cite or an excerpt of evidence is
free text, not a heading, so it is read as lowercase words (:func:`~debate_core.arguments.landscape.
matcher.tag_words`) and loses the same names and, besides, every word of every team code of the
caselist, since a code can stand alone in free text where a heading's rule would keep it.
`v1-e32-t21` wrote this rule for its features (:func:`card_tag`); `v1-e32-t07` reads a card's prompt
input by it too, so the two never disagree on what a name is.

Pure: names arrive as arguments and are never logged or returned in a `repr`.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence

from debate_core.arguments.landscape.matcher import tag_words
from debate_core.arguments.landscape.source_headings import CaselistNames

__all__ = ["card_tag", "code_words"]


def card_tag(
    tag: str | None,
    own_names: Sequence[str],
    caselist: CaselistNames,
    codes: Collection[str] = frozenset(),
) -> str | None:
    """`tag` as words, without the disclosing teams' own names, any school of the caselist, or any word
    of `codes`, the caselist's team codes as :func:`code_words` gives them.

    A tag is free text, so a team code standing alone in it is taken out too, which a heading keeps
    (`v1-e32-t01`): a code that is also an ordinary word costs a tag one word.
    """
    if tag is None:
        return None
    words = tag_words(tag)
    for name in own_names:
        phrase = tag_words(name)
        if phrase:
            words = " ".join(re.sub(rf"(?<!\S){re.escape(phrase)}(?!\S)", " ", words).split())
    words = caselist.without_schools(words)
    return " ".join(word for word in words.split() if word not in codes) or None


def code_words(names: Mapping[str, Sequence[str]]) -> frozenset[str]:
    """Every word of every team code of a caselist's schools (`school -> codes`), as a tag's words are."""
    return frozenset(word for codes in names.values() for code in codes for word in tag_words(code).split())

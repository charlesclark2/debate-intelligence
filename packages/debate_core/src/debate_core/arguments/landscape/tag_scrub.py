"""A card's free text as words, without the names of the teams that disclosed it or the caselist's.

A heading is normalized with the disclosing teams' own names and the caselist's schools taken out
(:mod:`~debate_core.arguments.landscape.source_headings`). A tag, a cite or an excerpt of evidence is
free text, not a heading, so it is read as lowercase words (:func:`~debate_core.arguments.landscape.
matcher.tag_words`) and loses the same names and, besides, every word of every team code of the
caselist, since a code can stand alone in free text where a heading's rule would keep it.
`v1-e32-t21` wrote this rule for its features (:func:`card_tag`); `v1-e32-t07` reads a card's prompt
input by it too, so the two never disagree on what a name is. A prompt input loses, besides, the name
scan's whole third list, every disclosing team's school, code and tournament (:class:`DisclosedNames`,
`v1-e32-t40`).

Pure: names arrive as arguments and are never logged or returned in a `repr`.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Final

from debate_core.arguments.landscape.matcher import tag_words
from debate_core.arguments.landscape.seeding import SeedSource
from debate_core.arguments.landscape.source_headings import CaselistNames

__all__ = ["NO_NAMES", "DisclosedNames", "card_tag", "code_words"]


def card_tag(
    tag: str | None,
    own_names: Sequence[str],
    caselist: CaselistNames,
    codes: Collection[str] = frozenset(),
    disclosed: DisclosedNames | None = None,
) -> str | None:
    """`tag` as words, without the disclosing teams' own names, any school of the caselist, or any word
    of `codes`, the caselist's team codes as :func:`code_words` gives them.

    A tag is free text, so a team code standing alone in it is taken out too, which a heading keeps
    (`v1-e32-t01`): a code that is also an ordinary word costs a tag one word.

    With `disclosed`, every disclosing team's school, code and tournament comes out too
    (:class:`DisclosedNames`): what the model stage sends (`v1-e32-t40`). `v1-e32-t21`'s features are
    read without it, as its proxy model was trained.
    """
    if tag is None:
        return None
    words = tag_words(tag)
    for name in own_names:
        phrase = tag_words(name)
        if phrase:
            words = " ".join(re.sub(rf"(?<!\S){re.escape(phrase)}(?!\S)", " ", words).split())
    words = caselist.without_schools(words)
    words = " ".join(word for word in words.split() if word not in codes)
    if disclosed is not None:
        words = _without_names(words, caselist, codes, disclosed)
    return words or None


def _without_names(
    words: str, caselist: CaselistNames, codes: Collection[str], disclosed: DisclosedNames
) -> str:
    """`words` without the third list, and without any school or code word that taking it out brought
    together, until nothing more comes out."""
    while True:
        found = caselist.without_schools(disclosed.without(words))
        found = " ".join(word for word in found.split() if word not in codes)
        if found == words:
            return found
        words = found


def code_words(names: Mapping[str, Sequence[str]]) -> frozenset[str]:
    """Every word of every team code of a caselist's schools (`school -> codes`), as a tag's words are."""
    return frozenset(word for codes in names.values() for code in codes for word in tag_words(code).split())


class DisclosedNames:
    """Every disclosing team's school, team code and tournament in a reading, to take out of what a model
    is sent (`v1-e32-t40`).

    The name scan's third list (:func:`~debate_core.arguments.landscape.model_stage.name_scan`), as a
    scrub: `v1-e32-t39` found other teams' tournaments and codes in the heading paths the model stage
    sent, which the rules above leave in, since they take out the disclosing team's own names and the
    caselist's schools and code words only. Each name is matched as whole words of
    :func:`~debate_core.arguments.landscape.matcher.tag_words`, the longest first, until none is left:
    taking one name out can bring two words of another together. A name that is also an ordinary word
    costs the text that word, as a code word costs a tag.

    Holds the names, so its `repr` withholds them.
    """

    def __init__(self, names: Iterable[str]) -> None:
        phrases = {tuple(words.split()) for words in map(tag_words, names) if words}
        by_first: dict[str, list[tuple[str, ...]]] = {}
        for phrase in sorted(phrases, key=lambda one: (-len(one), one)):
            by_first.setdefault(phrase[0], []).append(phrase)
        self._by_first = {word: tuple(found) for word, found in by_first.items()}

    @classmethod
    def of_sources(cls, sources: Iterable[SeedSource]) -> DisclosedNames:
        """The names every team of every one of `sources` disclosed under."""
        return cls(name for source in sources for team in source.teams for name in team.names)

    def __repr__(self) -> str:
        return f"DisclosedNames(<{sum(map(len, self._by_first.values()))} names withheld>)"

    def without(self, words: str) -> str:
        """`words` (lowercase words, one space apart) without any of the names."""
        tokens = words.split()
        while self._by_first:
            kept = self._one_pass(tokens)
            if len(kept) == len(tokens):
                break
            tokens = kept
        return " ".join(tokens)

    def _one_pass(self, tokens: Sequence[str]) -> list[str]:
        kept: list[str] = []
        at = 0
        while at < len(tokens):
            size = next(
                (
                    len(phrase)
                    for phrase in self._by_first.get(tokens[at], ())
                    if tuple(tokens[at : at + len(phrase)]) == phrase
                ),
                0,
            )
            if size:
                at += size
            else:
                kept.append(tokens[at])
                at += 1
        return kept


NO_NAMES: Final = DisclosedNames(())
"""No names to take out: a candidate built without a reading's."""

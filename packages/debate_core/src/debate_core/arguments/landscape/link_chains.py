"""Which chain role a team labelled a card with, and which scenario it filed it under (`v1-e32-t14`).

The coach asked, of each DA's and advantage's impact cards, what the impact runs through, and for a
first deterministic link chain per position: its uniqueness, link, internal link and impact, and for
an advantage its harms, inherency and solvency. The rules are the PM's rulings of 2026-10-25 on
counts over hspolicy26. Only what a team wrote down counts, and a role or scenario no heading or label
gives is counted, never guessed.

## Where a card's labels are read

* **Its sub-headings**: the normalized headings below the one that placed it (the matcher's nearest
  alias or override, `v1-e32-t02`), each with its answer flag. A heading above the placing one belongs
  to something larger than the position and labels nothing here.
* **Its tag's opening**, past one leading enumerator, as `v1-e32-t10` reads a tag.

## Chain roles (:func:`heading_roles`, :func:`tag_role`, :func:`card_roles`)

A sub-heading labels a role when it holds the role's words, as whole words:

* **uniqueness:** `uniqueness`, `uq`, or `u` as its first word (never `u s`, which is U.S.);
* **link:** `link`, `links`, or `l` as its first word; not `link turn(s)`, `no link`, `link defense`,
  `lt`, `l t`, and not the `link` of `internal link`;
* **internal link:** `internal link(s)`, `internal`, `internals`, `il`, `i l`;
* **impact:** `v1-e32-t10`'s impact heading, reused, not rewritten;
* **advantages only:** harms `harms`, `harm`; inherency `inherency`, `inh`; solvency `solvency`, `solv`.

A tag labels uniqueness when it opens `uniqueness` or `uq`, a link when it opens `link`, `links` or
`the link` (not `link turn(s)` or `link defense`), and an internal link when it opens `internal link`,
`internal`, `il` or `i l`. `u` never labels in a tag: on hspolicy26, 105 of the 106 counted tags
opening `u` open `U.S.`.

An answer sub-heading (`AT: No Link`, the team's own frontline) fills no role, and a heading holding
two roles' labels fills neither. A card's impact role is `v1-e32-t10`'s impact card, whatever else
its heading holds, so the chain's impact is the impact section's first row. A heading the coach ruled
names no position still labels a role: `link`, `u` and `solvency` are such rulings. Whether a card
counts at all (READS, on the position's side) is the report's, so an answering or other-side card
never reaches these functions as a reading.

## Scenarios (:func:`card_scenario`)

A sub-heading is a **scenario heading** when it is numbered (`scenario`, `scenarios`, `scen`, `sc`,
`advantage` or `adv`, then a number, as its first words) or named: any other sub-heading that is no
role label, no answer, no heading the coach ruled names no position, and none of
:data:`NOT_A_SCENARIO`. A card's **scenario name** is the first of:

1. a numbered heading's words after `scenario N (is)`;
2. a named heading's words;
3. the words beside an impact or internal-link label (`Dome impact`, `Dome internal`), when what is
   left is not on the list either.

The innermost heading of each kind wins. Whether a name is shown (two or more teams of the position
use it) and whether it is withheld (:func:`is_withheld`) is the report's.

Pure and deterministic: no model, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Final, NamedTuple

from debate_core.arguments.landscape.impacts import is_impact_card, is_impact_heading, tag_opening
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape import Position, PositionKind
from debate_core.domain.landscape_report import CHAIN_ROLES, ChainRole

__all__ = [
    "LINK_TAG_OPENINGS",
    "MINIMUM_WITHHELD_WORD",
    "NOT_A_LINK",
    "NOT_A_SCENARIO",
    "CardScenario",
    "SubHeading",
    "caselist_words",
    "card_roles",
    "card_scenario",
    "heading_roles",
    "is_withheld",
    "scenario_name",
    "tag_role",
]

NOT_A_LINK: Final = ("link turn", "link turns", "no link", "link defense", "lt", "l t")
"""Answers and turns filed with a link word: a heading or tag holding one labels no link."""

_INTERNAL_LINK_WORDS: Final = ("internal link", "internal links", "internal", "internals", "il", "i l")
_ADVANTAGE_WORDS: Final = {
    ChainRole.HARMS: ("harms", "harm"),
    ChainRole.INHERENCY: ("inherency", "inh"),
    ChainRole.SOLVENCY: ("solvency", "solv"),
}
"""The labels only an advantage's cards carry."""

UNIQUENESS_TAG_OPENINGS: Final = ("uniqueness", "uq")
LINK_TAG_OPENINGS: Final = ("link", "links", "the link")
INTERNAL_LINK_TAG_OPENINGS: Final = ("internal link", "internal", "il", "i l")

_LABEL_WORDS: Final = frozenset(
    {"impact", "impacts", "internal", "internals", "link", "links", "il", "i", "l", "and"}
)
"""What is taken off an impact or internal-link heading to leave the words beside the label."""

_NUMBERED: Final = re.compile(
    r"^(?:scenario|scenarios|scen|sc|advantage|adv) "
    r"(?:\d{1,2}|one|two|three|four|five|i{1,3}|iv|v)(?: is)?(?: |$)"
)
NOT_A_SCENARIO: Final = re.compile(
    r"(?:^| )(?:overview|ov|o v|kick|extra|extras|defense|turn|turns|framing|solves case|da|disad|new|t c|tc"
    r"|k|cp|t|theory|counterplan|kritik|no link|link defense|lt|l t|no impact)(?: |$)"
    r"|^[12](?:ac|nc|ar|nr)\d*$|^[12](?:ac|nc|ar|nr)\d+ "
)
"""Structure, answers and other kinds of argument, which name no scenario: overviews, `kick`, `turns`,
`T/C`, a kind word (`da`, `k`, `cp`), a numbered speech answer (`2ac1`), and the role rules' own
answers (`no link`, `no impact`)."""

MINIMUM_WITHHELD_WORD: Final = 4
"""A school's or tournament's word is looked for when it is over three characters, as the scan before
sharing looks for a whole name: a shorter one is a word in every line. A team code is looked for at any
length."""


class SubHeading(NamedTuple):
    """One heading below the one that placed a card, normalized, with its answer flag."""

    text: str
    answer: bool


class CardScenario(NamedTuple):
    """Whether a card sits under a scenario heading, and the scenario name it is filed under."""

    heading: bool
    """Under a numbered or named scenario heading (`v1-e32-t14` ac3)."""
    name: str | None
    """The name, or None when no heading or label gives one."""


def _holds(words: str, phrase: str) -> bool:
    return f" {phrase} " in f" {words} "


def _opens(words: str, phrase: str) -> bool:
    return words == phrase or words.startswith(f"{phrase} ")


def heading_roles(heading: str, kind: PositionKind) -> frozenset[ChainRole]:
    """Every role whose label `heading`, normalized, holds; more than one means it labels none."""
    first = heading.split(" ", 1)[0]
    found: set[ChainRole] = set()
    if (
        _holds(heading, "uniqueness")
        or _holds(heading, "uq")
        or (first == "u" and not _opens(heading, "u s"))
    ):
        found.add(ChainRole.UNIQUENESS)
    outside_internal = re.sub(r"(?:^| )internal links?(?= |$)", " ", heading)
    if (
        _holds(outside_internal, "link")
        or _holds(outside_internal, "links")
        or (first == "l" and not _opens(heading, "l t"))
    ) and not any(_holds(heading, phrase) for phrase in NOT_A_LINK):
        found.add(ChainRole.LINK)
    if any(_holds(heading, phrase) for phrase in _INTERNAL_LINK_WORDS):
        found.add(ChainRole.INTERNAL_LINK)
    if is_impact_heading(heading):
        found.add(ChainRole.IMPACT)
    if kind is PositionKind.ADVANTAGE:
        found |= {
            role for role, words in _ADVANTAGE_WORDS.items() if any(_holds(heading, one) for one in words)
        }
    return frozenset(found)


def tag_role(tag: str | None) -> ChainRole | None:
    """The role the tag's opening labels, past one enumerator; never by `u` alone."""
    if not tag:
        return None
    words = tag_opening(tag)
    if any(_opens(words, one) for one in UNIQUENESS_TAG_OPENINGS):
        return ChainRole.UNIQUENESS
    if any(_opens(words, one) for one in INTERNAL_LINK_TAG_OPENINGS):
        return ChainRole.INTERNAL_LINK
    if any(_opens(words, one) for one in LINK_TAG_OPENINGS) and not any(
        _opens(words, one) for one in NOT_A_LINK
    ):
        return ChainRole.LINK
    return None


def card_roles(
    sub_headings: Sequence[SubHeading], headings: Sequence[str], tag: str | None, kind: PositionKind
) -> frozenset[ChainRole]:
    """The roles a counted card of a `kind` position fills: its sub-headings', its tag's, and impact.

    `headings` are all the card's normalized headings, which `v1-e32-t10`'s impact rule reads.
    """
    found: set[ChainRole] = set()
    for sub in sub_headings:
        if sub.answer:
            continue
        labels = heading_roles(sub.text, kind)
        if len(labels) == 1 and ChainRole.IMPACT not in labels:
            found |= labels
    opening = tag_role(tag)
    if opening is not None:
        found.add(opening)
    if is_impact_card(headings, tag):
        found.add(ChainRole.IMPACT)
    return frozenset(found) & frozenset(CHAIN_ROLES[kind])


def card_scenario(
    sub_headings: Sequence[SubHeading],
    kind: PositionKind,
    no_position: Iterable[str] = (),
    not_scenarios: Iterable[str] = (),
) -> CardScenario:
    """Whether the card sits under a scenario heading, and its scenario name, from its sub-headings."""
    decided = frozenset(no_position)
    heading = False
    numbered: str | None = None
    named: str | None = None
    beside: str | None = None
    for sub in sub_headings:
        if sub.answer:
            continue
        labels = heading_roles(sub.text, kind)
        if len(labels) > 1:
            continue
        if labels:
            if labels <= {ChainRole.IMPACT, ChainRole.INTERNAL_LINK}:
                words = " ".join(word for word in sub.text.split() if word not in _LABEL_WORDS)
                if words and not NOT_A_SCENARIO.search(words):
                    beside = words
            continue
        if sub.text in decided:
            continue
        found = _NUMBERED.match(sub.text)
        if found is not None:
            heading = True
            numbered = sub.text[found.end() :].strip() or None
        elif not NOT_A_SCENARIO.search(sub.text):
            heading = True
            named = sub.text
    return CardScenario(heading=heading, name=numbered or named or beside)


def scenario_name(position: Position, words: str | None) -> str | None:
    """The name `position` shows for `v1-e32-t14`'s scenario words."""
    return words


def caselist_words(disclosures: Iterable[Disclosure]) -> frozenset[str]:
    """Every word of the caselist's schools and tournaments over three characters, and every team code."""
    words: set[str] = set()
    for one in disclosures:
        for name in (one.school, one.tournament or ""):
            words |= {word for word in _plain_words(name) if len(word) >= MINIMUM_WITHHELD_WORD}
        words |= set(_plain_words(one.team_code))
    return frozenset(words)


def is_withheld(name: str, words: frozenset[str]) -> bool:
    """`name` holds a word of a caselist school, team code or tournament, so the report never shows it."""
    return any(word in words for word in name.split())


def _plain_words(text: str) -> list[str]:
    return re.findall(r"[0-9a-z]+", text.casefold())

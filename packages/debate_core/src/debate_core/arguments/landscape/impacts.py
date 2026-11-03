"""Which cards a team labelled as an impact: the rule behind a DA's and an advantage's impact cards.

`v1-e32-t10` lists, under each DA and advantage of the landscape report, the cards teams labelled as
its impact. The rule is the PM's ruling of 2026-10-24, made on counts over hspolicy26: deterministic,
no model, and only what a team wrote down. A card is an impact card when either holds:

* **A heading over it labels an impact.** The heading, normalized as the position matcher reads it
  (:func:`~debate_core.arguments.landscape.headings.normalize_heading`), holds `impact` or `impacts`
  as a whole word, but not `no impact`, `impact defense`, `impact turn` or `impact turns`, which are
  defense and answers filed under an impact heading; or it holds `turns case`. `T/C` and `I/L` are
  not impacts: the first is ambiguous, the second a link.
* **Its tag opens with an impact word**, after one leading enumerator (`2.`, `b)`, `Third,`): one of
  :data:`IMPACT_TAG_OPENINGS`. A 1AC rarely heads its impact; it opens the tag with the impact itself
  ("Extinction from ...").

An impact nobody labelled is not found. The report says, per kind, how many documents carry none,
and the model stage that would find them is `v1-e32-t07`'s.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from debate_core.arguments.landscape.matcher import tag_words

__all__ = [
    "IMPACT_HEADING_PHRASES",
    "IMPACT_HEADING_WORDS",
    "IMPACT_TAG_OPENINGS",
    "NOT_IMPACT_HEADING_PHRASES",
    "is_impact_card",
    "is_impact_heading",
    "tag_opening",
    "tag_opens_with_impact",
]

IMPACT_HEADING_WORDS: Final = ("impact", "impacts")
"""A heading holding one of these labels an impact, unless it holds an exclusion."""

NOT_IMPACT_HEADING_PHRASES: Final = ("no impact", "impact defense", "impact turn", "impact turns")
"""Defense and answers filed under an impact heading: a heading holding one labels nothing."""

IMPACT_HEADING_PHRASES: Final = ("turns case",)
"""A heading holding one of these labels an impact whatever else it holds."""

IMPACT_TAG_OPENINGS: Final = (
    "impact",
    "impacts",
    "the impact",
    "our impact",
    "extinction",
    "existential",
    "nuclear war",
    "nuke war",
    "goes nuclear",
    "escalation",
    "turns case",
    "outweighs",
    "magnitude",
    "timeframe",
    "probability",
)
"""A tag opening with one of these, as whole words, labels an impact."""

_ENUMERATOR: Final = re.compile(r"^(?:\d{1,2}|[a-h]|first|second|third|fourth|fifth) ")
"""One leading enumerator of a tag's words: `2`, `b`, `third`. A tag's punctuation is already gone."""


def _holds(words: str, phrase: str) -> bool:
    """`phrase` is in `words` as whole words; both are lowercase words one space apart."""
    return f" {phrase} " in f" {words} "


def is_impact_heading(heading: str) -> bool:
    """`heading`, normalized as the matcher reads it, labels the cards under it as impacts."""
    if any(_holds(heading, phrase) for phrase in IMPACT_HEADING_PHRASES):
        return True
    return any(_holds(heading, word) for word in IMPACT_HEADING_WORDS) and not any(
        _holds(heading, phrase) for phrase in NOT_IMPACT_HEADING_PHRASES
    )


def tag_opening(tag: str) -> str:
    """The tag's words past one leading enumerator: what a label at its start is read from."""
    return _ENUMERATOR.sub("", tag_words(tag), count=1)


def tag_opens_with_impact(tag: str | None) -> bool:
    """The tag, past one leading enumerator, opens with one of :data:`IMPACT_TAG_OPENINGS`."""
    if not tag:
        return False
    words = tag_opening(tag)
    return any(words == opening or words.startswith(f"{opening} ") for opening in IMPACT_TAG_OPENINGS)


def is_impact_card(headings: Iterable[str], tag: str | None) -> bool:
    """A heading over the card labels an impact, or its tag opens with an impact word."""
    return any(is_impact_heading(heading) for heading in headings) or tag_opens_with_impact(tag)

"""The coach's plan-mechanism words for a topic, and when a block heading holds one (`v1-e33-t14`).

`config/landscape/plan_mechanisms/<topic id>.yaml` lists words that name how a plan works on the topic
(`preempt`, `waiver`): a block under one may make sense only against a plan that has that mechanism, so
a counterplan's draft (`files suggest`, `v1-e33-t11`) marks it for the coach to check against the plan.
The coach edits the list; a topic with no file has no words, and its drafts are marked as before.

## A word

Lowercase letters, with single hyphens between them (`pre-empt`), from :data:`WORD_MIN_LENGTH` to
:data:`WORD_MAX_LENGTH` characters; a word listed twice is refused, naming it. A hyphen is a space once
headings are normalized, so `pre-empt` is the two words `pre empt`.

## When a heading holds one (:func:`holds_a_mechanism_word`)

The heading is a block heading as the position matcher normalizes it (lowercase words of letters and
digits, one space apart), the same text `v1-e33-t11`'s rule reads. It holds a listed word when the word,
or the word with `s` or `es` after it, is one of its words, or for a hyphenated word that run of its
words. So `waiver` holds in `waivers`, and `preempt` in `preempts`; nothing else is a form of a word, so
`waive` does not hold in `waiver`, and `preempt` does not hold in `preemption` unless that is listed
too. The plural is there because a block heading is so often one: the coach's waiver block on hspolicy26
is headed `waivers`.

Pure: no I/O, and nothing here is logged.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints, model_validator

from debate_core.domain.base import DomainModel
from debate_core.domain.landscape import POSITION_ID_PATTERN

__all__ = [
    "WORD_MAX_LENGTH",
    "WORD_MIN_LENGTH",
    "PlanMechanismWords",
    "holds_a_mechanism_word",
]

WORD_MIN_LENGTH: Final = 3
WORD_MAX_LENGTH: Final = 32

MechanismWord = str  # SKELETON: no constraint


class PlanMechanismWords(DomainModel):
    """`config/landscape/plan_mechanisms/<topic id>.yaml`: the words that name a plan's mechanism."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    topic_id: Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)] = Field(
        description="The topic, as `topics.yaml` names it."
    )
    words: tuple[MechanismWord, ...] = Field(
        default=(), description="Lowercase letters and hyphens, matched whole in a CP draft's block headings."
    )

    @model_validator(mode="after")
    def _check_words(self) -> PlanMechanismWords:
        return self  # SKELETON: refuses nothing


def holds_a_mechanism_word(heading: str, words: Iterable[str]) -> bool:
    """Whether `heading` (lowercase words, one space apart) holds one of `words`, or its plural."""
    return False  # SKELETON


def _pattern(word: str) -> re.Pattern[str]:
    """`word`'s words as one run of whole words, the last with an optional `s` or `es`."""
    spaced = r" ".join(map(re.escape, word.split("-")))
    return re.compile(rf"(?<!\S){spaced}(?:e?s)?(?!\S)")

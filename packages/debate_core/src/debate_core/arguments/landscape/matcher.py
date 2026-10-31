"""Deterministic position matching: headings, the coach's overrides and tag keywords (`v1-e32-t02`).

The matcher places each section and card of a parsed source under one position of the topic's
taxonomy, or under none, without a model. Pure: the same source, taxonomy and overrides give the
same results, and nothing here does I/O.

## Reading an item

:func:`read_items` turns one source into :class:`MatchItem`\\ s: one per card, and one per heading
path the cards record (a section). The headings over an item are read as seeding read them
(:mod:`~debate_core.arguments.landscape.source_headings`): the open tag dropped, three levels at
most, each heading normalized with the team's own names and the caselist's schools taken out. A
heading that normalizes to nothing (`1NC`, `Case`) says nothing and is left out. What placement
reads, the normalized headings with their answer flags and a card's tag as words, is hashed into
the item's :attr:`~MatchItem.fingerprint`, so two items alike in those are placed alike and share a
cached result.

## Placing an item (:meth:`PositionMatcher.place`)

1. **The nearest placed heading wins.** From the heading directly over the item outwards, the
   first heading that the coach's override names a position for, or that is an alias, places it.
   An override is read before the aliases. Directly over the item that is `OVERRIDE` or `ALIAS`
   (confidence 1); further up it is `INHERITED` (0.9). A heading the store saw at any level counts:
   a path leaves out the levels a file skipped, so a level is certain only on a full path.
2. **The role** is ANSWERS when the placing heading, or any heading above it, is an answer
   (`AT: Spending DA`, or a block under `AT: DAs`), and READS otherwise. An answer heading below
   the placing one (`Spending DA` > `AT: Link Turn`) is the reading team's own block.
3. **Tag keywords refine.** A card placed under a position whose children carry tag keywords goes
   under the child its tag names, when exactly one does, and stays with the parent otherwise
   (`TAG_KEYWORD`, 0.9; the PM's ruling of 2026-10-23).
4. **Tag keywords alone** place a card nothing else placed, when exactly one position's keywords
   are in its tag (`TAG_KEYWORD`, 0.5). That is under the review threshold by default, so such a card
   goes to the review queue with its candidate rather than into a count.
5. **Otherwise nothing places it.** An unplaced heading stays unplaced and is never a guessed
   position, whatever it looks like (a school's short form included); the item goes to the review
   queue. When every heading over it is one the coach ruled names no position, the item is decided
   (`OVERRIDE`, no position) and does not go back to the queue. Such a heading is otherwise passed
   over like any heading that places nothing.

A retired alias counts under the position its `merged_into` links end at, and one retired with
nowhere to go places nothing. Every result is checked against the taxonomy's active ids
(:func:`~debate_core.domain.landscape_classification.checked_against`).

The confidences are fixed per rule, not measured: they rank the rules for the review threshold.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final

from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.seeding import SeedSource
from debate_core.arguments.landscape.source_headings import (
    CaselistNames,
    heading_path,
    normalize_source_heading,
)
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    RATIONALE_LIMIT,
    ClassificationMethod,
    ClassificationResult,
    ItemKind,
    OverrideRules,
    PositionRole,
    card_item_id,
    checked_against,
    section_item_id,
)

__all__ = [
    "ALIAS_CONFIDENCE",
    "INHERITED_CONFIDENCE",
    "OVERRIDE_CONFIDENCE",
    "TAG_KEYWORD_ALONE_CONFIDENCE",
    "TAG_KEYWORD_UNDER_PARENT_CONFIDENCE",
    "MatchItem",
    "PositionMatcher",
    "read_items",
    "tag_words",
]

ALIAS_CONFIDENCE: Final = 1.0
OVERRIDE_CONFIDENCE: Final = 1.0
INHERITED_CONFIDENCE: Final = 0.9
TAG_KEYWORD_UNDER_PARENT_CONFIDENCE: Final = 0.9
TAG_KEYWORD_ALONE_CONFIDENCE: Final = 0.5

_CANDIDATE_LIMIT: Final = 3
_GENERIC_WORDS: Final = frozenset(
    {
        "a",
        "adv",
        "advantage",
        "aff",
        "an",
        "and",
        "at",
        "counterplan",
        "cp",
        "da",
        "disad",
        "for",
        "in",
        "k",
        "kritik",
        "neg",
        "of",
        "on",
        "t",
        "the",
        "to",
    }
)
"""Words that name a kind of argument or join others, so sharing one makes no position a candidate."""


def tag_words(text: str) -> str:
    """A tag or a keyword as lowercase words of letters and digits, one space apart, for word matching.

    Not a heading normalizer: a tag is a claim, and nothing is stripped from it.
    """
    return " ".join(re.findall(r"[0-9a-z]+", text.casefold()))


@dataclass(frozen=True, slots=True)
class MatchItem:
    """One section or card as placement reads it. Holds headings and a tag, so its `repr` withholds them."""

    item_id: str
    kind: ItemKind
    source_sha256: str
    first_element_index: int | None
    headings: tuple[NormalizedHeading, ...] = field(repr=False)
    """The non-empty normalized headings over the item, outermost first."""
    tag: str | None = field(repr=False)
    """A card's tag as :func:`tag_words` writes it; None for a section and for a card with no tag."""
    fingerprint: str = ""
    """SHA-256 of what placement reads: the headings with their answer flags, and the tag's words."""


def read_items(source: SeedSource, caselist: CaselistNames) -> tuple[MatchItem, ...]:
    """Every card of `source`, and every heading path its cards record, ready to place.

    Sections come first, in the order their paths first appear, then the cards in file order. A card
    the reader gave no first paragraph is a reader bug, and raises `ValueError`.
    """
    names = [name for team in source.teams for name in team.names if name.strip()]
    tags = {card.tag for card in source.cards if card.tag is not None}
    read: dict[str, NormalizedHeading] = {}

    def normalized(raw: Sequence[str]) -> tuple[NormalizedHeading, ...]:
        found: list[NormalizedHeading] = []
        for heading in raw:
            one = read.get(heading)
            if one is None:
                one = read[heading] = normalize_source_heading(heading, names, caselist)
            if one.text:
                found.append(one)
        return tuple(found)

    sections: dict[str, MatchItem] = {}
    cards: list[MatchItem] = []
    for card in source.cards:
        if card.first_element_index is None:
            raise ValueError(f"a card of {source.sha256} has no first paragraph; the reader must give one")
        path = heading_path(card.tag, card.section_path, tags)
        for depth in range(1, len(path) + 1):
            section_id = section_item_id(source.sha256, path[:depth])
            if section_id not in sections:
                headings = normalized(path[:depth])
                sections[section_id] = MatchItem(
                    item_id=section_id,
                    kind=ItemKind.SECTION,
                    source_sha256=source.sha256,
                    first_element_index=None,
                    headings=headings,
                    tag=None,
                    fingerprint=_fingerprint(headings, None),
                )
        headings = normalized(path)
        words = tag_words(card.tag) if card.tag is not None else None
        cards.append(
            MatchItem(
                item_id=card_item_id(source.sha256, card.first_element_index),
                kind=ItemKind.CARD,
                source_sha256=source.sha256,
                first_element_index=card.first_element_index,
                headings=headings,
                tag=words or None,
                fingerprint=_fingerprint(headings, words or None),
            )
        )
    return (*sections.values(), *cards)


def _fingerprint(headings: Sequence[NormalizedHeading], tag: str | None) -> str:
    payload = {"headings": [[one.text, one.answer] for one in headings], "tag": tag}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _Placement:
    position_id: str
    method: ClassificationMethod
    depth: int
    """Index of the placing heading in the item's headings."""
    matched: str
    """The alias or override heading that placed it: committed taxonomy or override text."""


class PositionMatcher:
    """Places items under one taxonomy and its overrides. Build one per (taxonomy, overrides)."""

    def __init__(self, taxonomy: Taxonomy, overrides: OverrideRules) -> None:
        overrides.check_against(taxonomy)
        self.taxonomy = taxonomy
        self.overrides = overrides
        self._aliases: dict[str, str | None] = {}
        for position in taxonomy.positions:
            resolved = taxonomy.resolve(position.id)
            for alias in position.aliases:
                self._aliases[alias] = None if resolved.deprecated else resolved.id
        self._overrides: dict[str, str | None] = {
            rule.heading: None if rule.position_id is None else taxonomy.resolve(rule.position_id).id
            for rule in overrides.overrides
        }
        active = taxonomy.active_positions
        self._keywords: dict[str, tuple[str, ...]] = {
            position.id: tuple(words for words in map(tag_words, position.tag_keywords) if words)
            for position in active
            if position.tag_keywords
        }
        self._children: dict[str, list[str]] = defaultdict(list)
        for position in active:
            if position.parent is not None and position.id in self._keywords:
                self._children[taxonomy.resolve(position.parent).id].append(position.id)
        self._parents = {position.id: position.parent for position in active}
        self._heading_candidates: dict[str, tuple[str, ...]] = {}
        self._by_word: dict[str, set[str]] = defaultdict(set)
        for alias, position_id in self._aliases.items():
            if position_id is not None:
                for word in alias.split():
                    if word not in _GENERIC_WORDS:
                        self._by_word[word].add(position_id)

    @property
    def taxonomy_version(self) -> str:
        return self.taxonomy.taxonomy_version

    def override_digest(self, item: MatchItem) -> str:
        """The digest of the coach's decisions on the headings over `item`, for its cache key."""
        return self.overrides.digest_for(heading.text for heading in item.headings)

    def place(self, item: MatchItem) -> ClassificationResult:
        """Where `item` goes under this taxonomy and these overrides, and why."""
        placement = self._placement(item.headings)
        if placement is None:
            return self._without_heading_placement(item)
        role = (
            PositionRole.ANSWERS
            if any(heading.answer for heading in item.headings[: placement.depth + 1])
            else PositionRole.READS
        )
        refined = self._refined(placement.position_id, item.tag)
        if refined is not None:
            child, keyword = refined
            return self._result(
                child,
                role,
                ClassificationMethod.TAG_KEYWORD,
                TAG_KEYWORD_UNDER_PARENT_CONFIDENCE,
                f"its tag holds the keyword '{keyword}' of {child}, under {placement.position_id}, "
                f"which {self._placed_by(placement, len(item.headings))}",
            )
        if placement.method is ClassificationMethod.INHERITED:
            confidence = INHERITED_CONFIDENCE
            rationale = (
                f"inherited from heading {placement.depth + 1} of {len(item.headings)} over it, "
                f"{self._match_phrase(placement)}"
            )
        else:
            confidence = (
                OVERRIDE_CONFIDENCE if placement.method is ClassificationMethod.OVERRIDE else ALIAS_CONFIDENCE
            )
            rationale = f"the heading directly over it {self._match_phrase(placement)}"
        if role is PositionRole.ANSWERS:
            rationale += "; an answer heading makes the role ANSWERS"
        return self._result(placement.position_id, role, placement.method, confidence, rationale)

    def placing_index(self, headings: Sequence[str]) -> int | None:
        """Which of `headings` (normalized, outermost first, as a card's are kept) places an item under them.

        The same nearest alias or override :meth:`place` finds, by its index; None when none does. The
        headings below it are the item's sub-headings, which `v1-e32-t14` reads roles and scenarios from.
        """
        placement = self._placement([NormalizedHeading(text=one, answer=False) for one in headings])
        return None if placement is None else placement.depth

    def heading_candidates(self, heading: str) -> tuple[str, ...]:
        """Positions the review queue offers for an undecided heading: up to three, best first.

        A position is a candidate when one of its aliases shares a word with the heading that is not a
        kind word (`da`, `cp`, `adv`...). Ranked by shared words, then id. Only a suggestion for the
        coach; nothing is placed by it.
        """
        found = self._heading_candidates.get(heading)
        if found is None:
            shared: Counter[str] = Counter()
            for word in set(heading.split()) - _GENERIC_WORDS:
                shared.update(self._by_word.get(word, ()))
            ranked = sorted(shared, key=lambda position_id: (-shared[position_id], position_id))
            found = self._heading_candidates[heading] = tuple(ranked[:_CANDIDATE_LIMIT])
        return found

    def tag_candidates(self, item: MatchItem) -> tuple[str, ...]:
        """Every position whose tag keywords are in the card's tag, by id: the queue's other suggestion."""
        return tuple(sorted(position_id for position_id, _ in self._keyword_matches(item.tag)))

    def undecided_headings(self, item: MatchItem) -> tuple[NormalizedHeading, ...]:
        """The headings over `item` that place nothing and carry no decision: what the coach can decide."""
        return tuple(
            heading
            for heading in item.headings
            if heading.text not in self._overrides and self._aliases.get(heading.text) is None
        )

    # --------------------------------------------------------------------------------------------

    def _placement(self, headings: Sequence[NormalizedHeading]) -> _Placement | None:
        for depth in range(len(headings) - 1, -1, -1):
            text = headings[depth].text
            directly_over = depth == len(headings) - 1
            if text in self._overrides:
                position_id = self._overrides[text]
                if position_id is not None:
                    method = (
                        ClassificationMethod.OVERRIDE if directly_over else ClassificationMethod.INHERITED
                    )
                    return _Placement(position_id, method, depth, text)
                continue
            position_id = self._aliases.get(text)
            if position_id is not None:
                method = ClassificationMethod.ALIAS if directly_over else ClassificationMethod.INHERITED
                return _Placement(position_id, method, depth, text)
        return None

    def _match_phrase(self, placement: _Placement) -> str:
        if placement.matched in self._overrides:
            return f"which the coach's override of '{placement.matched}' places under {placement.position_id}"
        return f"which is the alias '{placement.matched}' of {placement.position_id}"

    def _placed_by(self, placement: _Placement, count: int) -> str:
        where = (
            "the heading directly over it"
            if placement.depth == count - 1
            else f"heading {placement.depth + 1} of {count}"
        )
        how = "the coach's override" if placement.matched in self._overrides else "an alias"
        return f"{where} places by {how}"

    def _refined(self, position_id: str, tag: str | None) -> tuple[str, str] | None:
        """The descendant `tag`'s keywords pick out, one child at a time, and the keyword that did it."""
        if tag is None:
            return None
        found: tuple[str, str] | None = None
        current = position_id
        while True:
            matches = [
                (child, keyword)
                for child in self._children.get(current, ())
                if (keyword := self._keyword_in(child, tag)) is not None
            ]
            if len(matches) != 1:
                return found
            found = matches[0]
            current = found[0]

    def _keyword_matches(self, tag: str | None) -> list[tuple[str, str]]:
        """Every active position whose keywords `tag` holds, with the first keyword it holds."""
        if tag is None:
            return []
        return [
            (position_id, keyword)
            for position_id in self._keywords
            if (keyword := self._keyword_in(position_id, tag)) is not None
        ]

    def _keyword_in(self, position_id: str, tag: str) -> str | None:
        return next((one for one in self._keywords[position_id] if f" {one} " in f" {tag} "), None)

    def _without_heading_placement(self, item: MatchItem) -> ClassificationResult:
        matches = self._keyword_matches(item.tag)
        ancestors = {ancestor for position_id, _ in matches for ancestor in self._ancestors(position_id)}
        narrowest = [
            (position_id, keyword) for position_id, keyword in matches if position_id not in ancestors
        ]
        if len(narrowest) == 1:
            position_id, keyword = narrowest[0]
            answers = any(heading.answer for heading in item.headings)
            rationale = (
                f"no heading over it places it; its tag holds the keyword '{keyword}' of {position_id}"
            )
            return self._result(
                position_id,
                PositionRole.ANSWERS if answers else PositionRole.READS,
                ClassificationMethod.TAG_KEYWORD,
                TAG_KEYWORD_ALONE_CONFIDENCE,
                rationale + ("; an answer heading makes the role ANSWERS" if answers else ""),
            )
        if item.headings and all(self._overrides.get(heading.text, "") is None for heading in item.headings):
            return self._result(
                None,
                None,
                ClassificationMethod.OVERRIDE,
                OVERRIDE_CONFIDENCE,
                "the coach ruled that every heading over it names no position",
            )
        if len(narrowest) > 1:
            rationale = (
                f"no heading over it places it, and its tag holds keywords of {len(narrowest)} positions"
            )
        elif item.headings:
            rationale = "no heading over it is an alias or an override"
        else:
            rationale = "it sits under no heading"
        return self._result(None, None, None, 0.0, rationale)

    def _ancestors(self, position_id: str) -> Iterable[str]:
        parent = self._parents.get(position_id)
        while parent is not None:
            resolved = self.taxonomy.resolve(parent).id
            yield resolved
            parent = self._parents.get(resolved)

    def _result(
        self,
        position_id: str | None,
        role: PositionRole | None,
        method: ClassificationMethod | None,
        confidence: float,
        rationale: str,
    ) -> ClassificationResult:
        return checked_against(
            self.taxonomy,
            ClassificationResult(
                position_id=position_id,
                role=role,
                confidence=confidence,
                rationale=rationale[:RATIONALE_LIMIT],
                method=method,
                taxonomy_version=self.taxonomy.taxonomy_version,
            ),
        )

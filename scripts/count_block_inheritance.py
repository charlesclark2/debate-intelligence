#!/usr/bin/env python3
"""Count what a block could give the cards the matcher leaves unplaced (`v1-e32-t65`), counts only.

The product owner's point of 2026-11-14: a card's argument comes from the block it is read in. This script
measures that before any rule is built. It places every section and card of a caselist with the real
matcher (:class:`~debate_core.arguments.landscape.matcher.PositionMatcher`, the taxonomy and the coach's
overrides, no cache, no model) and then, for every card the matcher leaves for review, looks at the cards
around it that the matcher did place.

## What a block is here

The parsed store keeps cards only: each card's tag, its `section_path` (the raw pocket, hat and block
headings over it, as the reader cut them,
:func:`~debate_core.arguments.landscape.source_headings.heading_path`) and its first and last paragraph.
No heading paragraph is kept, so a block is built from paths:

* **run**: the cards next to each other in file order whose paths are equal. It stands for "the cards
  between two headings", but two headings written alike in a row (`OFF`, `OFF`) make one run. Every card
  of a run has the headings of every other, so the matcher places them alike, and only a tag can differ.
* **section**: the reader's section item of the card's innermost heading, with every section under it
  (each card whose path starts with the card's path). A card under no heading has the document.
* **parent**: the section one heading out (the path less its innermost heading).
* **nearest**: from the section outwards, the first section with a placed card in it decides; one that
  disagrees decides too (nothing is inherited, and no further section is read).
* **document**: the whole document.

## What a placed card is

`counted`: placed at or above the review threshold, what a report counts. `counted+keyword`: those, and the
cards placed by a tag keyword alone (0.5, under the threshold). A card is never its own block-mate.

## The rule measured

A card the matcher left for review (nothing placed it, or only its tag's keyword, under the threshold)
inherits position P from its block when the block's placed cards number at least `minimum`, and P is all of
them (`unanimous`) or at least two thirds (`two-thirds`). Its role is the role most of P's cards have
(READS on a tie); with `role=answer-heading`, ANSWERS whenever any heading over the card is an answer
heading (the PM's point: an answering card inherits as answering), and with `role=block`, the block's role
alone (the matcher's own reading of `Spending DA > AT: Link Turn`: an answer heading below the level that
decides is the reading team's own block). Scored as the evaluation scores a placement: its stance by
:func:`~debate_core.arguments.landscape.evaluation_breakdown.scored_stance`, from the role and the file's
sides.

## What it prints

Counts only, as JSON on stdout: no tag, heading, cite, path, school, team, row or item id. Position kinds,
never ids, and for the held-out sample nothing but its scores. The first sample is scored for every rule of
the grid; the holdout only with `--holdout-rule`, naming one rule chosen on the first sample, and refused
without one.

    uv run python scripts/count_block_inheritance.py --snapshot 2026-11-03 --sample <labels CSV> \\
        --sample-rows <rows file>
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from itertools import product
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.coach_sample_labels_file import read_labels_file
from debate_core.application.errors import DomainError
from debate_core.application.landscape_model_evaluation import LabelledCard, read_coach_sample
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.arguments.landscape.evaluation_breakdown import NO_POSITION_LABEL, related, scored_stance
from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.holdout_mark import holdout_header
from debate_core.arguments.landscape.link_chains import heading_roles, tag_role
from debate_core.arguments.landscape.matcher import PositionMatcher, read_items
from debate_core.arguments.landscape.review_queue import (
    DEFAULT_MINIMUM_REVIEW_TEAMS,
    DEFAULT_REVIEW_THRESHOLD,
    QueuedItem,
    build_review_queue,
    needs_review,
)
from debate_core.arguments.landscape.side_role import on_own_side
from debate_core.arguments.landscape.source_headings import (
    CaselistNames,
    heading_path,
    normalize_source_heading,
)
from debate_core.domain.landscape import PositionKind, Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ClassificationResult,
    ItemKind,
    PositionRole,
    Stance,
    card_item_id,
    section_item_id,
)
from debate_core.domain.landscape_report import ChainRole

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR: Final = REPO_ROOT / "config" / "landscape"
DEFAULT_DATA_DIR: Final = Path.home() / ".debate-research" / "dev"
DEFAULT_SNAPSHOT: Final = date(2026, 11, 3)
DEFAULT_CASELISTS: Final = ("hspolicy26", "hsld26")

LEVELS: Final = ("run", "section", "parent", "nearest", "document")
PLACED: Final = ("counted", "counted+keyword")
AGREEMENTS: Final = ("unanimous", "two-thirds")
MINIMUMS: Final = (1, 2, 3)
OWN: Final = ("any", "naming-nothing")
ROLES: Final = ("answer-heading", "block")
REFERENCE_RULE: Final = (
    "level=nearest,placed=counted,agreement=unanimous,minimum=1,own=any,role=answer-heading"
)
"""The rule the descriptive counts (answer headings, link-shaped tags) are given for."""

_LINK_ROLES: Final = frozenset({ChainRole.LINK, ChainRole.INTERNAL_LINK, ChainRole.UNIQUENESS})


class Refused(Exception):
    """A run this script will not make, with the reason to print."""


# ------------------------------------------------------------------------------------------------
# One card as the counts read it
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Placed:
    """A placement as a block reads it: the position, its kind and the role."""

    position_id: str
    kind: str
    role: PositionRole


@dataclass(frozen=True, slots=True)
class CardRecord:
    """One card: where it sits, what the matcher made of it, and what a link-shaped test reads."""

    document: str = field(repr=False)
    item_id: str = field(repr=False)
    path: tuple[str, ...] = field(repr=False)
    """The raw headings over it, as the reader cut them: the section item's path."""
    answers: tuple[bool, ...]
    names_nothing: tuple[bool, ...]
    """Per raw heading of `path`, whether it names nothing: it normalizes to no words, or the coach ruled it
    names no position (`solvency`, `link`)."""
    """Per raw heading of `path`, whether it is an answer heading (`AT:`)."""
    run: int
    """The card's run in its document: cards next to each other with equal paths share one."""
    status: str
    """`counted`, `keyword` (placed by its tag alone, under the threshold), `decided` (the coach ruled
    every heading over it names no position) or `unplaced`."""
    placed: Placed | None
    sides: tuple[str, ...]
    link_shaped: bool
    """Its tag opens as a link, internal link or uniqueness card, or a heading over it labels one."""
    sections: tuple[str, ...] = field(default=(), repr=False)
    """The section item ids over it, outermost first: one per prefix of `path`."""

    @property
    def eligible(self) -> bool:
        """Left for review by the matcher: what inheritance may place."""
        return self.status in ("unplaced", "keyword")

    @property
    def under_answer_heading(self) -> bool:
        return any(self.answers)


def _status(
    method: ClassificationMethod | None, position_id: str | None, confidence: float, threshold: float
) -> str:
    if method is None:
        return "unplaced"
    if position_id is None:
        return "decided"
    return "keyword" if confidence < threshold else "counted"


def read_cards(
    reading: SeedReading,
    taxonomy: Taxonomy,
    matcher: PositionMatcher,
    *,
    threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> tuple[list[CardRecord], dict[str, QueuedItem], list[QueuedItem]]:
    """Every card of `reading` placed by the matcher, and the review queue's items: its sections by item id,
    and its cards in the order of the cards left for review."""
    names = CaselistNames(reading.caselist_names)
    ruled_none = {rule.heading for rule in matcher.overrides.overrides if rule.position_id is None}
    placed_by_fingerprint: dict[str, ClassificationResult] = {}
    records: list[CardRecord] = []
    queued_sections: dict[str, QueuedItem] = {}
    queued_cards: list[QueuedItem] = []
    for source in reading.sources:
        own = [name for team in source.teams for name in team.names if name.strip()]
        sides = tuple(team.side.value for team in source.teams)
        tags = {card.tag for card in source.cards if card.tag is not None}
        cards = iter(source.cards)
        run = -1
        previous: tuple[str, ...] | None = None
        for item in read_items(source, names):
            result = placed_by_fingerprint.get(item.fingerprint)
            if result is None:
                result = placed_by_fingerprint[item.fingerprint] = matcher.place(item)
            result = on_own_side(taxonomy, result, sides)
            review = needs_review(result, threshold)
            queued = QueuedItem(
                source_sha256=source.sha256,
                kind=item.kind,
                teams=source.teams,
                headings=matcher.undecided_headings(item),
            )
            if item.kind is ItemKind.SECTION:
                if review:
                    queued_sections[item.item_id] = queued
                continue
            card = next(cards)
            path = heading_path(card.tag, card.section_path, tags)
            if path != previous:
                run += 1
                previous = path
            levels = [normalize_source_heading(raw, own, names) for raw in path]
            position = result.position_id
            records.append(
                CardRecord(
                    document=source.sha256,
                    item_id=card_item_id(source.sha256, card.first_element_index or 0),
                    path=path,
                    answers=tuple(one.answer for one in levels),
                    names_nothing=tuple(not one.text or one.text in ruled_none for one in levels),
                    run=run,
                    status=_status(result.method, position, result.confidence, threshold),
                    placed=None
                    if position is None or result.role is None
                    else Placed(position, taxonomy.resolve(position).kind.value, result.role),
                    sides=sides,
                    link_shaped=_link_shaped(card.tag, levels),
                    sections=tuple(
                        section_item_id(source.sha256, path[:depth]) for depth in range(1, len(path) + 1)
                    ),
                )
            )
            if review:
                queued_cards.append(queued)
    return records, queued_sections, queued_cards


def _link_shaped(tag: str | None, levels: Sequence[NormalizedHeading]) -> bool:
    if tag_role(tag) in _LINK_ROLES:
        return True
    return any(
        not one.answer
        and len(roles := heading_roles(one.text, PositionKind.DA)) == 1
        and roles <= _LINK_ROLES
        for one in levels
        if one.text
    )


# ------------------------------------------------------------------------------------------------
# Blocks
# ------------------------------------------------------------------------------------------------


Members = Counter[tuple[str, str, PositionRole]]
"""A block's placed cards by (position id, kind, role)."""


@dataclass(slots=True)
class DocumentBlocks:
    """One document's placed cards by section prefix and by run, for each kind of placed card."""

    by_prefix: dict[str, dict[tuple[str, ...], Members]] = field(
        default_factory=lambda: {placed: defaultdict(Counter) for placed in PLACED}
    )
    by_run: dict[str, dict[int, Members]] = field(
        default_factory=lambda: {placed: defaultdict(Counter) for placed in PLACED}
    )

    def add(self, card: CardRecord) -> None:
        if card.placed is None or card.status not in ("counted", "keyword"):
            return
        key = (card.placed.position_id, card.placed.kind, card.placed.role)
        kinds = PLACED if card.status == "counted" else PLACED[1:]
        for placed in kinds:
            self.by_run[placed][card.run][key] += 1
            for depth in range(len(card.path) + 1):
                self.by_prefix[placed][card.path[:depth]][key] += 1


def blocks_of(cards: Iterable[CardRecord]) -> dict[str, DocumentBlocks]:
    found: dict[str, DocumentBlocks] = defaultdict(DocumentBlocks)
    for card in cards:
        found[card.document].add(card)
    return found


def _without_self(members: Members, card: CardRecord) -> Members:
    """`members` less the card itself, when it is one of them (a keyword-placed card, read as placed)."""
    if card.placed is None or card.status != "keyword":
        return members
    key = (card.placed.position_id, card.placed.kind, card.placed.role)
    if members.get(key, 0) == 0:
        return members
    less = Counter(members)
    less[key] -= 1
    if less[key] <= 0:
        del less[key]
    return less


def block_members(card: CardRecord, blocks: DocumentBlocks, level: str, placed: str) -> tuple[Members, int]:
    """The placed cards of `card`'s block at `level`, and the depth of the section that decides (the
    number of raw headings it shares with the card; -1 for a run)."""
    if level == "run":
        return _without_self(blocks.by_run[placed].get(card.run, Counter()), card), len(card.path)
    prefixes = blocks.by_prefix[placed]
    depth = len(card.path)
    if level == "section":
        return _without_self(prefixes.get(card.path, Counter()), card), depth
    if level == "parent":
        if depth == 0:
            return Counter(), 0
        return _without_self(prefixes.get(card.path[:-1], Counter()), card), depth - 1
    if level == "document":
        return _without_self(prefixes.get((), Counter()), card), 0
    for shared in range(depth, -1, -1):
        members = _without_self(prefixes.get(card.path[:shared], Counter()), card)
        if members:
            return members, shared
    return Counter(), 0


@dataclass(frozen=True, slots=True)
class BlockReading:
    """What a block's placed cards say: how many, whether they agree, and on what."""

    placed: int
    agreeing: int
    position_id: str | None
    kind: str | None
    role: PositionRole | None
    roles_mixed: bool

    @property
    def nothing_placed(self) -> bool:
        return self.placed == 0

    @property
    def unanimous(self) -> bool:
        return self.placed > 0 and self.agreeing == self.placed


def read_block(members: Members) -> BlockReading:
    by_position: Counter[tuple[str, str]] = Counter()
    for (position_id, kind, _), count in members.items():
        by_position[(position_id, kind)] += count
    total = sum(by_position.values())
    if not total:
        return BlockReading(0, 0, None, None, None, roles_mixed=False)
    (position_id, kind), top = min(by_position.items(), key=lambda pair: (-pair[1], pair[0]))
    reads = members.get((position_id, kind, PositionRole.READS), 0)
    answers = members.get((position_id, kind, PositionRole.ANSWERS), 0)
    role = PositionRole.ANSWERS if answers > reads else PositionRole.READS
    return BlockReading(total, top, position_id, kind, role, roles_mixed=bool(reads and answers))


@dataclass(frozen=True, slots=True)
class Rule:
    level: str
    placed: str
    agreement: str
    minimum: int
    own: str = "any"
    """`naming-nothing`: inherit only when each heading over it below the deciding section names none."""
    role: str = "answer-heading"

    @property
    def name(self) -> str:
        return (
            f"level={self.level},placed={self.placed},agreement={self.agreement},"
            f"minimum={self.minimum},own={self.own},role={self.role}"
        )

    @classmethod
    def parse(cls, text: str) -> Rule:
        fields = dict(part.split("=", 1) for part in text.split(",") if "=" in part)
        try:
            rule = cls(
                level=fields["level"],
                placed=fields["placed"],
                agreement=fields["agreement"],
                minimum=int(fields["minimum"]),
                own=fields.get("own", "any"),
                role=fields.get("role", "answer-heading"),
            )
        except (KeyError, ValueError):
            raise Refused(f"a rule is written {REFERENCE_RULE}; got {text!r}") from None
        if (
            rule.level not in LEVELS
            or rule.placed not in PLACED
            or rule.agreement not in AGREEMENTS
            or rule.minimum not in MINIMUMS
            or rule.own not in OWN
            or rule.role not in ROLES
        ):
            raise Refused(f"the rule {text!r} is not one of the grid's")
        return rule

    def agrees(self, block: BlockReading) -> bool:
        if block.placed < self.minimum or block.position_id is None:
            return False
        if self.agreement == "unanimous":
            return block.unanimous
        return 3 * block.agreeing >= 2 * block.placed


def grid() -> list[Rule]:
    return [Rule(*one) for one in product(LEVELS, PLACED, AGREEMENTS, MINIMUMS, OWN)]


@dataclass(frozen=True, slots=True)
class Inherited:
    position_id: str
    kind: str
    role: PositionRole
    shared_depth: int
    block: BlockReading


@dataclass(frozen=True, slots=True)
class CardBlock:
    """A card's block read once at one level, for one kind of placed card: every rule tests this."""

    block: BlockReading
    shared_depth: int


def card_block(card: CardRecord, blocks: DocumentBlocks, level: str, placed: str) -> CardBlock:
    members, shared = block_members(card, blocks, level, placed)
    return CardBlock(read_block(members), shared)


def inherit_from(card: CardRecord, read: CardBlock, rule: Rule) -> Inherited | None:
    """The position `card` inherits from its block, read as `read`, under `rule`; None for nothing."""
    block = read.block
    if not rule.agrees(block) or block.position_id is None or block.kind is None or block.role is None:
        return None
    if rule.own == "naming-nothing" and not all(card.names_nothing[max(read.shared_depth, 0) :]):
        return None
    role = block.role
    if rule.role == "answer-heading" and card.under_answer_heading:
        role = PositionRole.ANSWERS
    return Inherited(block.position_id, block.kind, role, read.shared_depth, block)


def inherit(card: CardRecord, blocks: DocumentBlocks, rule: Rule) -> Inherited | None:
    """The position `card` inherits from its block under `rule`; None when it inherits nothing."""
    if not card.eligible:
        return None
    return inherit_from(card, card_block(card, blocks, rule.level, rule.placed), rule)


@dataclass(slots=True)
class BlockReadings:
    """Every card's block, read once per level and kind of placed card: the cards left for review, and the
    decided cards (read as if they were left, for one count)."""

    cards: Sequence[CardRecord]
    blocks: Mapping[str, DocumentBlocks]
    _read: dict[tuple[str, str], dict[int, CardBlock]] = field(default_factory=dict)

    def at(self, level: str, placed: str) -> dict[int, CardBlock]:
        found = self._read.get((level, placed))
        if found is None:
            found = self._read[(level, placed)] = {
                index: card_block(card, self.blocks[card.document], level, placed)
                for index, card in enumerate(self.cards)
                if card.eligible or card.status == "decided"
            }
        return found

    def inherited(self, rule: Rule) -> dict[int, Inherited]:
        """Each card left for review that `rule` places, by its index."""
        read = self.at(rule.level, rule.placed)
        found: dict[int, Inherited] = {}
        for index, one in read.items():
            card = self.cards[index]
            if not card.eligible:
                continue
            got = inherit_from(card, one, rule)
            if got is not None:
                found[index] = got
        return found


# ------------------------------------------------------------------------------------------------
# Scores against the coach's labels
# ------------------------------------------------------------------------------------------------


def names_a_label(
    taxonomy: Taxonomy, labelled: LabelledCard, position_id: str, role: PositionRole, sides: Sequence[str]
) -> bool:
    """Whether a placement is the coach's label or second label, each with its stance; never for `none`."""
    if labelled.label == NO_POSITION_LABEL:
        return False
    answered = (position_id, scored_stance(taxonomy, position_id, role, sides))
    labels = [(labelled.label, labelled.stance)]
    if labelled.also is not None:
        labels.append((labelled.also, labelled.also_stance))
    return answered in labels


def wilson(correct: int, counted: int) -> list[float] | None:
    """Wilson's score interval at 95%, as `v1-e32-t50` quotes intervals."""
    if not counted:
        return None
    z = 1.959963984540054
    share = correct / counted
    centre = (share + z * z / (2 * counted)) / (1 + z * z / counted)
    half = (
        z * math.sqrt(share * (1 - share) / counted + z * z / (4 * counted * counted)) / (1 + z * z / counted)
    )
    return [round(centre - half, 3), round(centre + half, 3)]


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


@dataclass(frozen=True, slots=True)
class SampleScore:
    labelled: int
    found: int
    counted_before: int
    correct_before: int
    inherited: int
    inherited_correct: int

    @property
    def counted_after(self) -> int:
        return self.counted_before + self.inherited

    @property
    def correct_after(self) -> int:
        return self.correct_before + self.inherited_correct

    def as_json(self) -> dict[str, object]:
        return {
            "labelled": self.labelled,
            "found": self.found,
            "before": {
                "counted": self.counted_before,
                "correct": self.correct_before,
                "accuracy": _ratio(self.correct_before, self.counted_before),
                "coverage": _ratio(self.counted_before, self.labelled),
                "placed_and_correct_share": _ratio(self.correct_before, self.labelled),
            },
            "inherited": {
                "counted": self.inherited,
                "correct": self.inherited_correct,
                "accuracy": _ratio(self.inherited_correct, self.inherited),
                "interval_95": wilson(self.inherited_correct, self.inherited),
            },
            "after": {
                "counted": self.counted_after,
                "correct": self.correct_after,
                "accuracy": _ratio(self.correct_after, self.counted_after),
                "interval_95": wilson(self.correct_after, self.counted_after),
                "coverage": _ratio(self.counted_after, self.labelled),
                "placed_and_correct_share": _ratio(self.correct_after, self.labelled),
            },
        }


def score_sample(
    taxonomy: Taxonomy,
    labelled: Sequence[LabelledCard],
    index_of: Mapping[str, int],
    readings: BlockReadings,
    rule: Rule | None,
) -> SampleScore:
    """The labelled cards as students would meet them: the matcher's counted placements, then (with
    `rule`) what the cards it left inherit. A decided card is never counted; a card labelled `none` that
    is placed counts against."""
    inherited_by = readings.inherited(rule) if rule is not None else {}
    found = counted = correct = inherited = inherited_correct = 0
    for one in labelled:
        index = index_of.get(one.item_id)
        if index is None:
            continue
        card = readings.cards[index]
        found += 1
        if card.status == "counted" and card.placed is not None:
            counted += 1
            correct += names_a_label(taxonomy, one, card.placed.position_id, card.placed.role, card.sides)
            continue
        got = inherited_by.get(index)
        if got is None:
            continue
        inherited += 1
        inherited_correct += names_a_label(taxonomy, one, got.position_id, got.role, card.sides)
    return SampleScore(len(labelled), found, counted, correct, inherited, inherited_correct)


def inherited_outcomes(
    taxonomy: Taxonomy,
    labelled: Sequence[LabelledCard],
    index_of: Mapping[str, int],
    readings: BlockReadings,
    rule: Rule,
) -> dict[str, int]:
    """First sample only: what each inherited placement is against the coach's label, as the evaluation's
    outcomes read it: right, the label's position with the other stance, a position related to it (an aff and
    its advantage), another of its kind, another kind, or a card labelled none."""
    inherited_by = readings.inherited(rule)
    found: Counter[str] = Counter()
    for one in labelled:
        index = index_of.get(one.item_id)
        got = inherited_by.get(index) if index is not None else None
        if index is None or got is None:
            continue
        card = readings.cards[index]
        if one.label == NO_POSITION_LABEL:
            found["labelled_none"] += 1
        elif names_a_label(taxonomy, one, got.position_id, got.role, card.sides):
            found["correct"] += 1
        elif got.position_id in (one.label, one.also):
            found["wrong_stance"] += 1
        elif related(taxonomy, got.position_id, one.label) or (
            one.also is not None and related(taxonomy, got.position_id, one.also)
        ):
            found["related"] += 1
        elif got.kind == taxonomy.resolve(one.label).kind.value:
            found["same_kind"] += 1
        else:
            found["other_kind"] += 1
    return dict(sorted(found.items()))


# ------------------------------------------------------------------------------------------------
# Counts over a caselist
# ------------------------------------------------------------------------------------------------


def _size(count: int) -> str:
    return "1" if count == 1 else "2" if count == 2 else "3-4" if count <= 4 else "5+"


def block_shapes(readings: BlockReadings) -> dict[str, object]:
    """Of the cards left for review, how many sit in a block whose placed cards agree, disagree, or are none,
    per level and kind of placed card; and for the agreeing, how many placed cards agree."""
    shapes: dict[str, object] = {}
    for level, placed in product(LEVELS, PLACED):
        tally: Counter[str] = Counter()
        sizes: Counter[str] = Counter()
        for index, one in readings.at(level, placed).items():
            if not readings.cards[index].eligible:
                continue
            block = one.block
            if block.nothing_placed:
                tally["nothing_placed"] += 1
            elif block.unanimous:
                tally["agree"] += 1
                sizes[_size(block.placed)] += 1
            else:
                tally["disagree"] += 1
                tally["disagree_two_thirds_agree"] += 3 * block.agreeing >= 2 * block.placed
        shapes[f"{level}/{placed}"] = {
            "agree": tally["agree"],
            "disagree": tally["disagree"],
            "of_which_two_thirds_agree": tally["disagree_two_thirds_agree"],
            "nothing_placed": tally["nothing_placed"],
            "agreeing_block_sizes": dict(sorted(sizes.items())),
        }
    return shapes


def answer_headings(readings: BlockReadings, rule: Rule) -> dict[str, int]:
    """How answer headings fall: over the cards left for review, and over those `rule` places, where the
    answer heading sits against the section that decides and what role the block's cards have."""
    eligible = [card for card in readings.cards if card.eligible]
    tally: Counter[str] = Counter()
    tally["left_for_review"] = len(eligible)
    tally["left_for_review_under_an_answer_heading"] = sum(card.under_answer_heading for card in eligible)
    for index, got in readings.inherited(rule).items():
        card = readings.cards[index]
        tally["inherit"] += 1
        block_role = got.block.role
        if got.block.roles_mixed:
            tally["inherit_block_roles_mixed"] += 1
        elif block_role is PositionRole.ANSWERS:
            tally["inherit_block_answers"] += 1
        else:
            tally["inherit_block_reads"] += 1
        if not card.under_answer_heading:
            continue
        tally["inherit_under_an_answer_heading"] += 1
        shared = max(got.shared_depth, 0)
        if any(card.answers[:shared]):
            tally["answer_heading_in_the_deciding_section"] += 1
        if any(card.answers[shared:]):
            tally["answer_heading_below_the_deciding_section"] += 1
            block = "answers" if block_role is PositionRole.ANSWERS else "reads"
            tally[f"answer_heading_below_and_block_{block}"] += 1
    return dict(sorted(tally.items()))


def link_shaped(readings: BlockReadings, rule: Rule) -> dict[str, object]:
    """Of the cards `rule` places, by the inherited position's kind: how many, and how many link-shaped."""
    by_kind: Counter[str] = Counter()
    link: Counter[str] = Counter()
    for index, got in readings.inherited(rule).items():
        by_kind[got.kind] += 1
        link[got.kind] += readings.cards[index].link_shaped
    return {kind: {"inherit": by_kind[kind], "link_shaped": link[kind]} for kind in sorted(by_kind)}


def population(readings: BlockReadings, rule: Rule) -> dict[str, object]:
    """What `rule` does to the caselist: cards placed before and after, by the inherited position's kind."""
    cards = readings.cards
    total = len(cards)
    counted = sum(card.status == "counted" for card in cards)
    inherited_by = readings.inherited(rule)
    by_kind = Counter(got.kind for got in inherited_by.values())
    from_keyword = sum(cards[index].status == "keyword" for index in inherited_by)
    decided_would = sum(
        inherit_from(cards[index], one, rule) is not None
        for index, one in readings.at(rule.level, rule.placed).items()
        if cards[index].status == "decided"
    )
    added = len(inherited_by)
    return {
        "inherited": added,
        "inherited_by_kind": dict(sorted(by_kind.items())),
        "of_which_were_keyword_placed": from_keyword,
        "placed_share_before": _ratio(counted, total),
        "placed_share_after": _ratio(counted + added, total),
        "decided_cards_that_would_inherit_if_eligible": decided_would,
    }


def _queue_counts(items: Sequence[QueuedItem]) -> dict[str, int]:
    counts = build_review_queue(items, minimum_teams=DEFAULT_MINIMUM_REVIEW_TEAMS).counts
    return {
        "items": counts.queued_items,
        "cards": counts.queued_cards,
        "headings": counts.headings,
        "rows": counts.rows,
        "under_no_heading": counts.without_heading,
    }


def queue_effect(
    sections: Mapping[str, QueuedItem],
    queued_cards: Mapping[int, QueuedItem],
    readings: BlockReadings,
    rule: Rule,
) -> dict[str, dict[str, int]]:
    """The review queue after `rule`, two ways. `sections_kept`: a card that inherits leaves it, and every
    section stays, as the matcher places a section by its headings alone. `sections_placed_leave`: a section
    leaves too once every card under it is placed (counted, inherited, or decided by the coach)."""
    inherited_by = readings.inherited(rule)
    kept = [queued for index, queued in queued_cards.items() if index not in inherited_by]
    open_sections: set[str] = set()
    for index, card in enumerate(readings.cards):
        if card.status in ("unplaced", "keyword") and index not in inherited_by:
            open_sections.update(card.sections)
    left = [queued for item_id, queued in sections.items() if item_id in open_sections]
    return {
        "sections_kept": _queue_counts([*sections.values(), *kept]),
        "sections_placed_leave": _queue_counts([*left, *kept]),
    }


def label_kinds_of_inheriting(
    taxonomy: Taxonomy,
    labelled: Sequence[LabelledCard],
    index_of: Mapping[str, int],
    readings: BlockReadings,
    rule: Rule,
) -> dict[str, object]:
    """First sample only: of the labelled cards `rule` places, the label's kind against the inherited kind,
    for link-shaped cards and under answer headings, with the label's stance. Kinds and stances only."""
    inherited_by = readings.inherited(rule)
    pairs: Counter[str] = Counter()
    link: Counter[str] = Counter()
    answering: Counter[str] = Counter()
    for one in labelled:
        index = index_of.get(one.item_id)
        got = inherited_by.get(index) if index is not None else None
        if index is None or got is None:
            continue
        card = readings.cards[index]
        label = (
            NO_POSITION_LABEL if one.label == NO_POSITION_LABEL else taxonomy.resolve(one.label).kind.value
        )
        right = names_a_label(taxonomy, one, got.position_id, got.role, card.sides)
        key = f"inherited {got.kind}, labelled {label}, {'right' if right else 'wrong'}"
        pairs[key] += 1
        if card.link_shaped:
            link[key] += 1
        if card.under_answer_heading:
            stance = "at" if one.stance is Stance.ANSWERS else "reads"
            answering[f"{key}, label {stance}"] += 1
    return {
        "by_kind": dict(sorted(pairs.items())),
        "link_shaped": dict(sorted(link.items())),
        "under_an_answer_heading": dict(sorted(answering.items())),
    }


# ------------------------------------------------------------------------------------------------
# Wiring
# ------------------------------------------------------------------------------------------------


async def _reading(
    arguments: argparse.Namespace, caselist: str
) -> tuple[SeedReading, Taxonomy, PositionMatcher]:
    from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
    from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
    from debate_core.integrations.local.parsed_store import LocalParsedStore
    from debate_core.integrations.local.suppression_list import local_suppression_list_file

    data_dir = arguments.data_dir.expanduser().resolve()
    repository = YamlTaxonomyRepository.load(arguments.config_dir)
    resolved = repository.resolve(caselist, arguments.snapshot)
    if resolved is None or resolved.taxonomy is None:
        raise Refused(f"topics.yaml puts {caselist} on {arguments.snapshot} on no topic with a taxonomy")
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    reading = await read_seed_sources(
        store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        topic=resolved.topic,
        caselist=caselist,
        version=arguments.version,
        through=arguments.snapshot,
        topic_map=repository.topic_map(),
    )
    if not reading.sources:
        raise Refused(
            f"0 sources of {caselist} on {resolved.topic.id} through {arguments.snapshot}; nothing counted"
        )
    taxonomy = repository.taxonomy(resolved.topic.id)
    return reading, taxonomy, PositionMatcher(taxonomy, repository.overrides(resolved.topic.id))


def _labelled(
    sample: Path, rows_path: Path, taxonomy: Taxonomy, *, holdout: bool
) -> tuple[LabelledCard, ...]:
    rows = rows_path.expanduser().read_text(encoding="utf-8").splitlines()
    marked = holdout_header(rows) is not None
    if marked != holdout:
        raise Refused(
            "the held-out sample's rows file is not marked a holdout"
            if holdout
            else "the first sample's rows file is marked a holdout"
        )
    return read_coach_sample(io.StringIO(read_labels_file(sample.expanduser()), newline=""), rows, taxonomy)


async def _count(arguments: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    holdout_rule = Rule.parse(arguments.holdout_rule) if arguments.holdout_rule else None
    if (arguments.holdout_sample is None) != (arguments.holdout_rows is None):
        raise Refused("the held-out sample is read from --holdout-sample and --holdout-rows together")
    if (arguments.holdout_sample is not None) != (holdout_rule is not None):
        raise Refused(
            "the holdout is scored once, with one rule: give --holdout-rule with its files, or neither"
        )
    if (arguments.sample is None) != (arguments.sample_rows is None):
        raise Refused("the first sample is read from --sample and --sample-rows together")
    reference = Rule.parse(REFERENCE_RULE)
    caselists: dict[str, object] = {}
    for caselist in arguments.caselist:
        begun = time.perf_counter()
        try:
            reading, taxonomy, matcher = await _reading(arguments, caselist)
        except Refused as refused:
            caselists[caselist] = {"refused": str(refused)}
            continue
        cards, sections, queued = read_cards(reading, taxonomy, matcher, threshold=arguments.threshold)
        readings = BlockReadings(cards, blocks_of(cards))
        index_of = {card.item_id: index for index, card in enumerate(cards)}
        eligible = [index for index, card in enumerate(cards) if card.eligible]
        if len(eligible) != len(queued):
            raise Refused("the queued cards and the cards left for review are not the same count")
        queued_cards = dict(zip(eligible, queued, strict=True))
        statuses = Counter(card.status for card in cards)
        entry: dict[str, object] = {
            "version": reading.version,
            "topic_id": reading.topic_id,
            "taxonomy_version": taxonomy.taxonomy_version,
            "sources": len(reading.sources),
            "cards": len(cards),
            "cards_by_status": dict(sorted(statuses.items())),
            "left_for_review": len(eligible),
            "block_shapes": block_shapes(readings),
            "reference_rule": REFERENCE_RULE,
            "answer_headings_under_the_reference_rule": answer_headings(readings, reference),
            "link_shaped_under_the_reference_rule": link_shaped(readings, reference),
            "review_queue_before": _queue_counts([*sections.values(), *queued]),
        }
        labelled_here = caselist == arguments.labelled_caselist
        first: tuple[LabelledCard, ...] = ()
        if labelled_here and arguments.sample is not None:
            first = _labelled(arguments.sample, arguments.sample_rows, taxonomy, holdout=False)
            entry["first_sample_before"] = score_sample(taxonomy, first, index_of, readings, None).as_json()
            entry["first_sample_under_the_reference_rule"] = label_kinds_of_inheriting(
                taxonomy, first, index_of, readings, reference
            )
        rules: dict[str, object] = {}
        for rule in grid():
            one: dict[str, object] = {
                "population": population(readings, rule),
                "review_queue_after": queue_effect(sections, queued_cards, readings, rule),
            }
            if first:
                scored: dict[str, object] = {}
                for role in ROLES:
                    written = score_sample(
                        taxonomy, first, index_of, readings, replace(rule, role=role)
                    ).as_json()
                    scored[role] = {
                        "inherited": written["inherited"],
                        "after": written["after"],
                        "outcomes": inherited_outcomes(
                            taxonomy, first, index_of, readings, replace(rule, role=role)
                        ),
                    }
                one["first_sample"] = scored
            rules[rule.name.rsplit(",role=", 1)[0]] = one
        entry["rules"] = rules
        if labelled_here and holdout_rule is not None:
            held = _labelled(arguments.holdout_sample, arguments.holdout_rows, taxonomy, holdout=True)
            entry["holdout"] = {
                "rule": holdout_rule.name,
                "score": score_sample(taxonomy, held, index_of, readings, holdout_rule).as_json(),
            }
        entry["seconds"] = round(time.perf_counter() - begun, 1)
        caselists[caselist] = entry
    return {
        "snapshot": arguments.snapshot.isoformat(),
        "caselists": caselists,
        "seconds": round(time.perf_counter() - started, 1),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--snapshot", type=date.fromisoformat, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--version", help="The parsed store's version directory. Default: the newest.")
    parser.add_argument(
        "--caselist", action="append", help="Repeat for each. Default: hspolicy26 and hsld26."
    )
    parser.add_argument(
        "--labelled-caselist", default="hspolicy26", help="The caselist the coach's samples are of."
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_REVIEW_THRESHOLD)
    parser.add_argument("--sample", type=Path, help="The first sample's labels CSV (v1-e32-t21).")
    parser.add_argument("--sample-rows", type=Path, help="The first sample's rows file.")
    parser.add_argument("--holdout-sample", type=Path, help="The held-out sample's labels CSV (v1-e32-t50).")
    parser.add_argument("--holdout-rows", type=Path, help="The held-out sample's rows file.")
    parser.add_argument(
        "--holdout-rule",
        help=f"The one rule, chosen on the first sample, to score the holdout with: {REFERENCE_RULE}.",
    )
    arguments = parser.parse_args(argv)
    arguments.caselist = arguments.caselist or list(DEFAULT_CASELISTS)
    try:
        result = asyncio.run(_count(arguments))
    except (Refused, DomainError, ValueError, OSError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=1, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

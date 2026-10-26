"""The positions a landscape report counts against, and which topic a caselist snapshot is on.

E32 reports what a caselist's teams read: the plans affirmatives run, and the DAs, CPs, Ks, T and
theory negatives answer them with. Counting needs a fixed list to count against, the topic's
*position taxonomy*, and a rule for which topic a disclosure was on. Both are coach-edited YAML
under `config/landscape/` (`v1-e32-t01-position-taxonomy`); this module is what that YAML must be.

## A taxonomy

One file per topic, `config/landscape/taxonomies/<topic id>.yaml`, holds a :class:`Taxonomy`: the
topic's positions, each with a stable kebab-case id, a label, a :class:`PositionKind`, a
:class:`PositionSide`, an optional parent (an advantage under its aff), the headings it is read
under (`aliases`) and words its card tags tend to carry (`tag_keywords`). A shared
`generic.yaml` holds the format-level positions every topic of an event has, condo bad or a
generic K, each naming the events it applies to; :meth:`Taxonomy.with_generic` merges them into
a topic of that event.

**An id is never deleted or reused once released.** A report classified under one version must
still mean the same thing under the next, so a position is retired by `deprecated: true`, and a
rename or a merge also names the position that replaces it in `merged_into`.
:meth:`Taxonomy.resolve` follows those links to the position a classification now counts under.

**An alias is written as the heading normalizer leaves a heading**: lowercase letters and digits
in words separated by single spaces (`spending da`). The normalizer
(:mod:`debate_core.arguments.landscape.headings`) sits in a layer above this one, so this module
checks the form and `tests/config/test_landscape_taxonomies.py` checks that every committed alias
is one the normalizer can produce. Two positions of one topic never claim the same alias, retired
ones included, because a heading must lead to one position.

## A DA's or advantage's scenarios

A DA or an advantage may carry the coach's scenario list (`v1-e32-t22`): :class:`Scenario` entries,
each a name and the heading words it is filed under (`forms`, written as an alias is), and
`not_scenarios`, forms the coach ruled name no scenario. A form is listed once per position, and a
name once, whatever its case. A position with either list shows the coach's names and no other words;
one with neither keeps `v1-e32-t14`'s rule. The rule itself is
:mod:`debate_core.arguments.landscape.link_chains`'s.

## The topic map

`config/landscape/topics.yaml` is a :class:`TopicMap`: each topic with its event, the resolution's
wording when the coach has given it, the taxonomy version in force, and the caselist date ranges
it covers. An LD or PF caselist changes topic during a season, so a snapshot is placed by
(caselist, date), and two ranges of one caselist may not overlap: :meth:`TopicMap.resolve` returns
one topic or none, never a choice. Caselist slugs live in this file and nowhere in code.

Nothing here names a person. A taxonomy describes arguments; the config test refuses an alias or
label shaped like a team code or a school.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.caselist import CaselistSlug, Event

__all__ = [
    "ALIAS_PATTERN",
    "GENERIC_TOPIC_ID",
    "POSITION_ID_PATTERN",
    "TAXONOMY_VERSION_PATTERN",
    "CaselistRange",
    "Position",
    "PositionKind",
    "PositionSide",
    "Scenario",
    "Taxonomy",
    "Topic",
    "TopicMap",
    "TopicResolution",
]

GENERIC_TOPIC_ID: Final = "generic"
"""The `topic_id` of `generic.yaml`, the format-level positions merged into every topic of an event."""

POSITION_ID_PATTERN: Final = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
"""Lowercase words joined by single hyphens: `spending-da`, `medicare-for-all-aff`."""

TAXONOMY_VERSION_PATTERN: Final = r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
"""`MAJOR.MINOR.PATCH`, with no prefix and no pre-release part."""

ALIAS_PATTERN: Final = re.compile(r"^[a-z0-9]+(?: [a-z0-9]+)*$")
"""What a normalized heading looks like: lowercase words of letters and digits, one space apart."""

PositionId = Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)]
TaxonomyVersion = Annotated[str, StringConstraints(pattern=TAXONOMY_VERSION_PATTERN)]


def _normalized_form(alias: str) -> str:
    if ALIAS_PATTERN.match(alias) is None:
        raise ValueError(
            f"an alias is written as a normalized heading (lowercase words of letters and digits, "
            f"one space apart); got {alias!r}"
        )
    return alias


Alias = Annotated[str, AfterValidator(_normalized_form)]


class PositionKind(StrEnum):
    """What sort of argument a position is. Policy uses the first seven; LD and PF the rest."""

    AFF = "aff"
    """An affirmative case: in Policy, one plan, named by its mechanism."""

    ADVANTAGE = "advantage"
    """An advantage of an aff; its `parent` is the aff when the headings show which one."""

    DA = "da"
    """A disadvantage."""

    CP = "cp"
    """A counterplan."""

    K = "k"
    """A kritik."""

    T = "t"
    """A topicality argument."""

    THEORY = "theory"
    """A theory argument: condo bad, PICs bad."""

    VALUE = "value"
    """An LD value."""

    CRITERION = "criterion"
    """An LD criterion or standard."""

    CONTENTION = "contention"
    """A contention of an LD or PF case."""

    RESPONSE = "response"
    """A common response to a contention."""


class PositionSide(StrEnum):
    """Which side reads a position. PF's pro and con are written `aff` and `neg`."""

    AFF = "aff"
    NEG = "neg"
    BOTH = "both"


_SCENARIO_KINDS: Final = frozenset({PositionKind.DA, PositionKind.ADVANTAGE})
"""The kinds whose impacts a report says the scenario of (`v1-e32-t14`), so the kinds that list one."""


class Scenario(DomainModel):
    """One scenario of a DA or advantage, as the coach names it (`v1-e32-t22`)."""

    name: NonEmptyText = Field(description="What the report calls it: the words a debater uses.")
    forms: tuple[Alias, ...] = Field(
        min_length=1,
        description="The heading words it is filed under, each as `v1-e32-t14` reads a scenario's words.",
    )


class Position(DomainModel):
    """One argument a report counts: a plan, a DA, a K, an LD value, a PF contention."""

    id: PositionId = Field(description="Stable kebab-case id; never deleted or reused once released.")
    label: NonEmptyText = Field(description="The name debaters use for it, as the report prints it.")
    kind: PositionKind = Field(description="What sort of argument it is.")
    side: PositionSide = Field(description="aff, neg or both. PF pro and con are aff and neg.")
    parent: PositionId | None = Field(
        default=None, description="The position this one belongs to: an advantage's aff. None for most."
    )
    aliases: tuple[Alias, ...] = Field(
        default=(), description="Normalized headings this position is read under."
    )
    tag_keywords: tuple[NonEmptyText, ...] = Field(
        default=(), description="Words its card tags tend to carry, for the matcher's second look."
    )
    description: str = Field(default="", description="A sentence for the coach; never card text.")
    events: tuple[Event, ...] = Field(
        default=(),
        description="generic.yaml only: the events it applies to. A topic's own positions omit it.",
    )
    deprecated: bool = Field(default=False, description="Retired: kept so earlier classifications resolve.")
    merged_into: PositionId | None = Field(
        default=None, description="The position a retired one was renamed or merged into."
    )
    scenarios: tuple[Scenario, ...] = Field(
        default=(), description="DAs and advantages only: the coach's scenarios, each with its forms."
    )
    not_scenarios: tuple[Alias, ...] = Field(
        default=(), description="DAs and advantages only: heading words the coach ruled name no scenario."
    )

    @property
    def has_scenario_list(self) -> bool:
        """The coach has listed this position's scenarios, so its names are the list's."""
        return bool(self.scenarios or self.not_scenarios)

    @model_validator(mode="after")
    def _check_own_fields(self) -> Self:
        if self.merged_into is not None and not self.deprecated:
            raise ValueError(
                f"{self.id} is merged into {self.merged_into} but not deprecated; "
                "a merged position is retired"
            )
        twice = sorted(alias for alias, count in Counter(self.aliases).items() if count > 1)
        if twice:
            raise ValueError(f"{self.id} lists the alias {twice[0]!r} twice")
        self._check_scenario_list()
        return self

    def _check_scenario_list(self) -> None:
        if not self.has_scenario_list:
            return
        if self.kind not in _SCENARIO_KINDS:
            raise ValueError(f"{self.id} is a {self.kind.value}; only DAs and advantages list scenarios")
        forms = [*(form for one in self.scenarios for form in one.forms), *self.not_scenarios]
        twice = sorted(form for form, count in Counter(forms).items() if count > 1)
        if twice:
            raise ValueError(
                f"{self.id} lists the scenario form {twice[0]!r} twice; a form names one scenario"
            )
        names = sorted(
            name
            for name, count in Counter(one.name.casefold() for one in self.scenarios).items()
            if count > 1
        )
        if names:
            raise ValueError(f"{self.id} names two scenarios {names[0]!r}; merge their forms under one")


class Taxonomy(DomainModel):
    """One topic's positions (`taxonomies/<topic id>.yaml`), or the generic ones (`generic.yaml`)."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    topic_id: PositionId = Field(
        description="The topic, as `topics.yaml` names it; `generic` for generic.yaml."
    )
    taxonomy_version: TaxonomyVersion = Field(description="Semver; bumped with every released edit.")
    event: Event | None = Field(
        description="The topic's event; None in generic.yaml, whose positions name theirs."
    )
    positions: tuple[Position, ...] = Field(
        description="Every position, retired ones included, in file order."
    )

    @model_validator(mode="after")
    def _check_positions(self) -> Self:
        self._check_event()
        by_id: dict[str, Position] = {}
        for one in self.positions:
            if one.id in by_id:
                raise ValueError(f"the position id {one.id} is used twice")
            by_id[one.id] = one
        for one in self.positions:
            if one.parent is not None and one.parent not in by_id:
                raise ValueError(f"{one.id} names the parent {one.parent}, which is not a position here")
            if one.merged_into is not None and one.merged_into not in by_id:
                raise ValueError(f"{one.id} is merged into {one.merged_into}, which is not a position here")
        for one in self.positions:
            _refuse_cycle(one.id, lambda position_id: by_id[position_id].parent, "parent")
            _refuse_cycle(one.id, lambda position_id: by_id[position_id].merged_into, "merged_into")
        claimed: dict[str, str] = {}
        for one in self.positions:
            for alias in one.aliases:
                if alias in claimed:
                    raise ValueError(
                        f"the alias {alias!r} is claimed by {claimed[alias]} and {one.id}; "
                        "a heading must lead to one position"
                    )
                claimed[alias] = one.id
        return self

    def _check_event(self) -> None:
        if self.topic_id == GENERIC_TOPIC_ID:
            if self.event is not None:
                raise ValueError("generic.yaml names no event; each of its positions names its events")
            for one in self.positions:
                if not one.events:
                    raise ValueError(f"{one.id} in generic.yaml must name the events it applies to")
            return
        if self.event is None:
            raise ValueError(f"the taxonomy of {self.topic_id} must name its event")
        for one in self.positions:
            if one.events and self.event not in one.events:
                applies = ", ".join(event.value for event in one.events)
                raise ValueError(
                    f"{one.id} applies to {applies}, not to this topic's event {self.event.value}"
                )

    @property
    def is_generic(self) -> bool:
        return self.topic_id == GENERIC_TOPIC_ID

    @property
    def active_positions(self) -> tuple[Position, ...]:
        """The positions a report counts under: every one not retired, in file order."""
        return tuple(one for one in self.positions if not one.deprecated)

    def position(self, position_id: str) -> Position:
        """The position with this id, retired or not. `KeyError` when there is none."""
        for one in self.positions:
            if one.id == position_id:
                return one
        raise KeyError(position_id)

    def resolve(self, position_id: str) -> Position:
        """The position `position_id` now counts under: itself, or the end of its `merged_into` links."""
        found = self.position(position_id)
        while found.merged_into is not None:
            found = self.position(found.merged_into)
        return found

    def with_generic(self, generic: Taxonomy) -> Taxonomy:
        """This topic's positions followed by generic.yaml's for its event, checked as one taxonomy.

        An id or an alias the two files both use is refused here, as it would be in one file.
        """
        if not generic.is_generic or self.is_generic:
            raise ValueError(f"only {GENERIC_TOPIC_ID}.yaml merges into a topic's taxonomy")
        shared = tuple(one for one in generic.positions if self.event in one.events)
        return Taxonomy.model_validate(
            {
                **self.model_dump(),
                "positions": [*self.model_dump()["positions"], *(one.model_dump() for one in shared)],
            }
        )


def _refuse_cycle(start: str, next_of: Callable[[str], str | None], field: str) -> None:
    """Follow `field` from `start`; a link back to a position already passed is a cycle."""
    seen = [start]
    current: str | None = next_of(start)
    while current is not None:
        if current in seen:
            path = " -> ".join([*seen[seen.index(current) :], current])
            raise ValueError(f"{field} links form a cycle: {path}")
        seen.append(current)
        current = next_of(current)


class CaselistRange(DomainModel):
    """The snapshots of one caselist that are on a topic: `from` and `to`, both included."""

    caselist: CaselistSlug = Field(description="The caselist slug, e.g. as the caselist site names it.")
    effective_from: date = Field(alias="from", description="First snapshot date on the topic.")
    effective_to: date = Field(alias="to", description="Last snapshot date on the topic, included.")

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.effective_to < self.effective_from:
            raise ValueError(
                f"{self.caselist}: the range ends ({self.effective_to}) "
                f"before it starts ({self.effective_from})"
            )
        return self

    def covers(self, caselist: str, snapshot: date) -> bool:
        return caselist == self.caselist and self.effective_from <= snapshot <= self.effective_to

    def overlaps(self, other: CaselistRange) -> bool:
        return (
            self.caselist == other.caselist
            and self.effective_from <= other.effective_to
            and other.effective_from <= self.effective_to
        )


def _not_generic(topic_id: str) -> str:
    if topic_id == GENERIC_TOPIC_ID:
        raise ValueError(f"{GENERIC_TOPIC_ID!r} names generic.yaml, not a topic")
    return topic_id


class Topic(DomainModel):
    """One resolution: its event, its wording when given, its taxonomy version, its date ranges."""

    id: Annotated[PositionId, AfterValidator(_not_generic)] = Field(
        description="Kebab-case topic id; also the stem of its taxonomy file when it has one."
    )
    event: Event = Field(description="POLICY, LD or PF.")
    resolution: NonEmptyText | None = Field(
        default=None, description="The resolution's wording exactly as the coach gave it; None until given."
    )
    taxonomy_version: TaxonomyVersion | None = Field(
        default=None,
        description="The version of taxonomies/<id>.yaml in force; None for a topic with no taxonomy.",
    )
    caselists: tuple[CaselistRange, ...] = Field(min_length=1, description="The snapshots on this topic.")


class TopicResolution(DomainModel):
    """What a (caselist, snapshot) is on: one topic, and the taxonomy version to count it under."""

    topic_id: PositionId
    event: Event
    taxonomy_version: TaxonomyVersion | None = Field(description="None when the topic has no taxonomy.")


class TopicMap(DomainModel):
    """`config/landscape/topics.yaml`: every topic, and the caselist ranges each one covers."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    topics: tuple[Topic, ...] = Field(description="Every topic, in file order.")

    @model_validator(mode="after")
    def _check_topics(self) -> Self:
        seen: set[str] = set()
        for topic in self.topics:
            if topic.id in seen:
                raise ValueError(f"the topic {topic.id} is listed twice")
            seen.add(topic.id)
        ranges = [(topic.id, one) for topic in self.topics for one in topic.caselists]
        for index, (first_topic, first) in enumerate(ranges):
            for second_topic, second in ranges[index + 1 :]:
                if first.overlaps(second):
                    raise ValueError(
                        f"{first.caselist}: {first_topic} ({first.effective_from} to {first.effective_to}) "
                        f"and {second_topic} ({second.effective_from} to {second.effective_to}) overlap, "
                        "so a snapshot between them would be on two topics"
                    )
        return self

    def topic(self, topic_id: str) -> Topic:
        """The topic with this id. `KeyError` when there is none."""
        for topic in self.topics:
            if topic.id == topic_id:
                return topic
        raise KeyError(topic_id)

    def resolve(self, caselist: str, snapshot: date) -> TopicResolution | None:
        """The one topic `caselist`'s snapshot of `snapshot` is on, or None when no range covers it."""
        for topic in self.topics:
            if any(one.covers(caselist, snapshot) for one in topic.caselists):
                return TopicResolution(
                    topic_id=topic.id, event=topic.event, taxonomy_version=topic.taxonomy_version
                )
        return None

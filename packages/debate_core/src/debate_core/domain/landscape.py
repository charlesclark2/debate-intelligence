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

## Tournament entries (`v1-e32-t06`)

LD's topic follows the tournament, not the snapshot alone: one weekly snapshot can hold a weekend's
tournaments on two topics (the PM's ruling of 2026-11-05). A topic may list :class:`TournamentEntry`
items beside its ranges: a caselist, the tournament's public name, the spellings a disclosure's
tournament text is matched by, and the snapshots the entry applies in. A disclosure resolves
(:meth:`TopicMap.resolve_disclosure`) to

1. the topic of an entry whose window covers its snapshot and one of whose spellings its tournament
   text holds, once reduced by :func:`tournament_key` (lower case, letters and digits only);
2. otherwise, the topic whose range covers its snapshot;
3. otherwise, no topic.

A snapshot as a whole (:meth:`TopicMap.resolve`) is on the topic of its range, or with no range on the
topic of the one entry covering it, flagged :attr:`TopicResolution.tournament_entries_only`, since then
only the entry's disclosures are on it. The map refuses an entry that would move a snapshot an older
topic's range already resolves, and two topics' entries covering one snapshot of a caselist. A disclosure
the stored rounds carry no date for is matched by its tournament text and its snapshot, nothing else:
the caselist's own paths are all there is to decide by.

Nothing here names a person. A taxonomy describes arguments; the config test refuses an alias or
label shaped like a team code or a school.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
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
    "LateCut",
    "LateDisclosures",
    "TournamentEntry",
    "TournamentEntrySnapshot",
    "first_seen_spellings",
    "tournament_key",
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
    late_disclosures_on_earlier_topic: bool = Field(
        default=False,
        description=(
            "True puts a late disclosure in this range's snapshots on the topic of the caselist's range "
            "before this one: one whose tournament spelling was first seen before this range began and "
            "holds none of this topic's entry spellings (`v1-e32-t51`)."
        ),
    )

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


TOURNAMENT_SPELLING_PATTERN: Final = r"^[a-z0-9]+$"
"""A tournament spelling as :func:`tournament_key` leaves one: lower-case letters and digits."""

_NOT_A_KEY_CHARACTER: Final = re.compile(r"[^a-z0-9]")


def tournament_key(text: str | None) -> str:
    """A disclosure's tournament text reduced for matching: lower case, letters and digits only."""
    return _NOT_A_KEY_CHARACTER.sub("", (text or "").casefold())


class TournamentEntry(DomainModel):
    """A tournament on a topic whatever its snapshot's range says, in the snapshots `from` to `to`.

    A disclosure of `caselist` in one of those snapshots whose tournament text, reduced by
    :func:`tournament_key`, holds one of `spellings` is on the entry's topic.
    """

    caselist: CaselistSlug = Field(description="The caselist slug the entry applies to.")
    name: NonEmptyText = Field(description="The tournament's public name, for people; never matched.")
    spellings: tuple[Annotated[str, StringConstraints(pattern=TOURNAMENT_SPELLING_PATTERN)], ...] = Field(
        min_length=1,
        description="Lower-case letters and digits; reduced tournament text holding one matches.",
    )
    effective_from: date = Field(alias="from", description="First snapshot date the entry applies in.")
    effective_to: date = Field(alias="to", description="Last snapshot date the entry applies in, included.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.effective_to < self.effective_from:
            raise ValueError(
                f"{self.caselist}: the tournament entry {self.name!r} ends ({self.effective_to}) "
                f"before it starts ({self.effective_from})"
            )
        repeated = sorted(spelling for spelling, n in Counter(self.spellings).items() if n > 1)
        if repeated:
            raise ValueError(f"the tournament entry {self.name!r} lists {', '.join(repeated)} twice")
        return self

    def covers_snapshot(self, caselist: str, snapshot: date) -> bool:
        return caselist == self.caselist and self.effective_from <= snapshot <= self.effective_to

    def matches(self, caselist: str, snapshot: date, tournament: str | None) -> bool:
        key = tournament_key(tournament)
        return self.covers_snapshot(caselist, snapshot) and any(one in key for one in self.spellings)


def _has_a_letter_or_digit(word: str) -> str:
    if not tournament_key(word):
        raise ValueError(f"the check word {word!r} has no letter or digit")
    return word


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
    tournaments: tuple[TournamentEntry, ...] = Field(
        default=(),
        description="Tournaments on this topic whatever their snapshot's range says (`v1-e32-t06`).",
    )
    label: NonEmptyText | None = Field(
        default=None, description="The topic's short name for a report's sentences; its id when None."
    )
    check_words: tuple[Annotated[str, AfterValidator(_has_a_letter_or_digit)], ...] = Field(
        default=(),
        description=(
            "Words of this topic that the late-disclosure check looks for in tags and headings, matched by "
            "letters and digits without case (`v1-e32-t51`). A check only: they place no disclosure."
        ),
    )

    @property
    def name(self) -> str:
        """The topic's name in a report's sentences: its label, or its id."""
        return self.label or self.id

    def range_covering(self, caselist: str, snapshot: date) -> CaselistRange | None:
        """This topic's range of `caselist` covering `snapshot`, or None."""
        return next((one for one in self.caselists if one.covers(caselist, snapshot)), None)


class TopicResolution(DomainModel):
    """What a (caselist, snapshot) is on: one topic, and the taxonomy version to count it under."""

    topic_id: PositionId
    event: Event
    taxonomy_version: TaxonomyVersion | None = Field(description="None when the topic has no taxonomy.")
    tournament_entries_only: bool = Field(
        default=False,
        description=(
            "True when no range covers the snapshot and the topic's tournament entries put it there: only "
            "the entries' disclosures are on the topic, not the whole week."
        ),
    )


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
        self._check_tournament_entries()
        for topic in self.topics:
            for one in topic.caselists:
                if one.late_disclosures_on_earlier_topic and self.earlier_topic(one.caselist, one) is None:
                    raise ValueError(
                        f"{one.caselist}: {topic.id}'s range ({one.effective_from} to {one.effective_to}) "
                        "puts late disclosures on the earlier topic, but no topic has a range of the "
                        "caselist before it"
                    )
        return self

    def _check_tournament_entries(self) -> None:
        """An entry moves no snapshot an older topic's range resolves; no two topics' entries meet."""
        entries = [(topic, entry) for topic in self.topics for entry in topic.tournaments]
        for topic, entry in entries:
            own = [one.effective_from for one in topic.caselists if one.caselist == entry.caselist]
            start = min([*own, entry.effective_from])
            for other in self.topics:
                if other.id == topic.id:
                    continue
                for one in other.caselists:
                    if (
                        one.caselist == entry.caselist
                        and one.effective_from < start
                        and one.effective_from <= entry.effective_to
                        and entry.effective_from <= one.effective_to
                    ):
                        raise ValueError(
                            f"{entry.caselist}: {topic.id}'s tournament entry {entry.name!r} "
                            f"({entry.effective_from} to {entry.effective_to}) "
                            f"reaches into {other.id}'s range ({one.effective_from} to {one.effective_to}), "
                            f"which began before {topic.id}; "
                            "it would move snapshots that resolve to the older topic"
                        )
        for index, (first_topic, first) in enumerate(entries):
            for second_topic, second in entries[index + 1 :]:
                if (
                    first_topic.id != second_topic.id
                    and first.caselist == second.caselist
                    and first.effective_from <= second.effective_to
                    and second.effective_from <= first.effective_to
                ):
                    raise ValueError(
                        f"{first.caselist}: {first_topic.id}'s tournament entry {first.name!r} and "
                        f"{second_topic.id}'s {second.name!r} cover the same snapshots, so a disclosure "
                        "in them could be on two topics"
                    )

    def topic(self, topic_id: str) -> Topic:
        """The topic with this id. `KeyError` when there is none."""
        for topic in self.topics:
            if topic.id == topic_id:
                return topic
        raise KeyError(topic_id)

    def resolve(self, caselist: str, snapshot: date) -> TopicResolution | None:
        """The topic `caselist`'s snapshot of `snapshot` is on: its range's, or else its tournament entry's.

        None when neither covers it. On an entry's topic, `tournament_entries_only` says that only the
        entry's disclosures are on it.
        """
        for topic in self.topics:
            if topic.range_covering(caselist, snapshot) is not None:
                return _resolution(topic)
        for topic in self.topics:
            if any(entry.covers_snapshot(caselist, snapshot) for entry in topic.tournaments):
                return _resolution(topic, tournament_entries_only=True)
        return None

    def earlier_topic(self, caselist: str, later: CaselistRange) -> Topic | None:
        """The topic of `caselist`'s latest range ending before `later` begins; None when there is none."""
        found = [
            (one.effective_to, topic)
            for topic in self.topics
            for one in topic.caselists
            if one.caselist == caselist and one.effective_to < later.effective_from
        ]
        return max(found, key=lambda pair: pair[0])[1] if found else None

    def late_cut(self, caselist: str, snapshot: date) -> LateCut | None:
        """The range covering `caselist`'s snapshot, its topic and the topic before it; None without both."""
        for topic in self.topics:
            covering = topic.range_covering(caselist, snapshot)
            if covering is not None:
                earlier = self.earlier_topic(caselist, covering)
                return None if earlier is None else LateCut(topic=topic, range=covering, earlier=earlier)
        return None

    def is_late(
        self, caselist: str, snapshot: date, tournament: str | None, first_seen: Mapping[str, date]
    ) -> bool:
        """One disclosure is late: its snapshot's range has an earlier topic, no tournament entry matches it,
        its spelling holds none of the range topic's entry spellings, and `first_seen` dates that spelling
        before the range began. Whether the range moves it is :meth:`resolve_disclosure`'s."""
        cut = self.late_cut(caselist, snapshot)
        if cut is None:
            return False
        if any(
            entry.matches(caselist, snapshot, tournament) for one in self.topics for entry in one.tournaments
        ):
            return False
        key = tournament_key(tournament)
        if not key or any(spelling in key for entry in cut.topic.tournaments for spelling in entry.spellings):
            return False
        seen = first_seen.get(key)
        return seen is not None and seen < cut.range.effective_from

    def resolve_disclosure(
        self, caselist: str, snapshot: date, tournament: str | None, *, first_seen: Mapping[str, date]
    ) -> TopicResolution | None:
        """The topic one disclosure is on: a matching entry's; else, when its snapshot's range says so and the
        disclosure is late (:meth:`is_late`, by `first_seen`, :func:`first_seen_spellings`), the earlier
        topic's; else its snapshot's range's; else None."""
        for topic in self.topics:
            if any(entry.matches(caselist, snapshot, tournament) for entry in topic.tournaments):
                return _resolution(topic)
        cut = self.late_cut(caselist, snapshot)
        if (
            cut is not None
            and cut.range.late_disclosures_on_earlier_topic
            and self.is_late(caselist, snapshot, tournament, first_seen)
        ):
            return _resolution(cut.earlier)
        for topic in self.topics:
            if topic.range_covering(caselist, snapshot) is not None:
                return _resolution(topic)
        return None


class TournamentEntrySnapshot(DomainModel):
    """A snapshot on a topic only through its tournament entries: a report on it reads part of a week."""

    snapshot: date
    tournaments: tuple[NonEmptyText, ...] = Field(
        min_length=1, description="The public names of the entries covering the snapshot."
    )
    disclosures_on_topic: int = Field(ge=0, description="Its live disclosures the entries put on the topic.")
    disclosures: int = Field(ge=0, description="Its live disclosures in all, on any topic or none.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.disclosures_on_topic > self.disclosures:
            raise ValueError("a snapshot's disclosures on the topic are some of its disclosures")
        return self


class LateCut(DomainModel):
    """A snapshot's range, its topic, and the topic of the caselist's range before it (`v1-e32-t51`)."""

    topic: Topic
    range: CaselistRange
    earlier: Topic


def first_seen_spellings(disclosures: Iterable[tuple[date, str | None]]) -> dict[str, date]:
    """Each tournament spelling (:func:`tournament_key`) with the first snapshot a disclosure carried it in.

    `disclosures` are (snapshot, tournament text) pairs: a caselist's live disclosures, every snapshot.
    """
    first: dict[str, date] = {}
    for snapshot, tournament in disclosures:
        key = tournament_key(tournament)
        if key and (key not in first or snapshot < first[key]):
            first[key] = snapshot
    return first


class LateDisclosures(DomainModel):
    """A snapshot's late disclosures, for the report's line: counts only, no tournament (`v1-e32-t51`)."""

    snapshot: date
    range_from: date = Field(
        description="The first day of the topic's range: late spellings were seen before."
    )
    earlier_topic: NonEmptyText = Field(description="The earlier topic's name in the line.")
    moved: bool = Field(
        description="True when the range puts them on the earlier topic; False, counted here."
    )
    disclosures: int = Field(ge=0, description="The snapshot's live disclosures, on any topic or none.")
    late: int = Field(ge=0)
    late_sources: int = Field(ge=0)
    this_topic_only: int | None = Field(
        default=None, ge=0, description="Late sources holding only this topic's check words; None unchecked."
    )
    earlier_topic_only: int | None = Field(
        default=None, ge=0, description="Late sources holding only the earlier topic's check words."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.late > self.disclosures or self.late_sources > self.late:
            raise ValueError("late disclosures are some of the snapshot's, and their sources some of them")
        if (self.this_topic_only is None) != (self.earlier_topic_only is None):
            raise ValueError("the check gives both topics' counts, or neither")
        return self


def _resolution(topic: Topic, *, tournament_entries_only: bool = False) -> TopicResolution:
    return TopicResolution(
        topic_id=topic.id,
        event=topic.event,
        taxonomy_version=topic.taxonomy_version,
        tournament_entries_only=tournament_entries_only,
    )

"""The reading half of taxonomy seeding: one topic's parsed sources and the teams that disclosed them.

`scripts/seed_landscape_taxonomy.py` (`v1-e32-t01-position-taxonomy`) counts a topic's headings with
:func:`~debate_core.arguments.landscape.seeding.seed_candidates`, which takes plain values. This
module builds them from this machine's stores:

* **the sources** are the parsed entries of one version directory of the caselist's parsed card
  store, the newest unless one is named;
* **a source is on the topic** when one of its live disclosures (the suppression list neither stops
  nor holds it, :func:`~debate_core.application.caselist.parse_sources.live_disclosures`) resolves to
  the topic in `topics.yaml`, and, when a `through` date is given, is dated on or before it: the store
  as it stood at that snapshot (the position classifier, `v1-e32-t02`). A disclosure resolves by its
  snapshot's range, or first by a tournament entry its filename's tournament matches
  (:meth:`~debate_core.domain.landscape.TopicMap.resolve_disclosure`, `v1-e32-t06`), and in a range that
  says so a late disclosure (its tournament spelling first seen, among the caselist's live disclosures,
  before the range began) is on the earlier topic (`v1-e32-t51`);
* **the snapshots on the topic only through a tournament entry** are listed with how many of their
  live disclosures the entry put on the topic and how many they hold in all, so that a report on one
  says it reads part of a week (the PM's ruling of 2026-11-05);
* **the caselist's names** are every school a disclosure's path names, with its team codes, whatever
  the date, so that seeding can take another school's name out of a heading;
* **its teams** come from those disclosures' paths, read by the importer's own path parser: the
  school and team code directories, and the side in the filename. A path with no readable school or
  team code is a disclosure by no known team. Teams are never read from the store, which holds no
  path, and never from heading text.
* **its disclosures**, for the landscape report (`v1-e32-t03`), are those same on-topic live
  disclosures as E30 records one (school, team code, side, tournament, round and snapshot), read by
  the same parser and held only in memory.

Names stay in memory. A team's school and code, and the tournament the file was disclosed at, go to
the seeding function only to be taken out of that file's headings (a pocket named for a tournament
is not a position); nothing here writes, logs or returns them in a `repr`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import (
    Disclosed,
    EnumeratedSource,
    enumerate_sources,
    live_disclosures,
)
from debate_core.application.caselist.path_parser import (
    UNKNOWN_SCHOOL,
    UNKNOWN_TEAM_CODE,
    parse_disclosure_path,
)
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import DomainError
from debate_core.application.ports.parsed_store import DocumentRecord, ParsedStore, SourceOutcome
from debate_core.application.ports.suppression import SuppressionList, SuppressionState
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape import Topic, TopicMap, TournamentEntrySnapshot, first_seen_spellings

__all__ = ["SeedReading", "SeedingCannotStart", "read_seed_sources"]


class SeedingCannotStart(DomainError):
    """The topic does not cover the caselist, or the caselist has no parsed version to read."""


@dataclass(frozen=True, slots=True)
class SeedReading:
    """What was read for one topic: the version directory, its counts, and the sources on the topic."""

    caselist: str
    version: str
    topic_id: str
    entries: int
    """Source entries in the version directory, whatever became of them."""
    parsed: int
    """Of those, the ones parsed into a document."""
    parsed_off_topic: int
    """Parsed sources with no live disclosure dated inside the topic's ranges."""
    sources: tuple[SeedSource, ...] = field(repr=False)
    """The parsed sources on the topic, in digest order."""
    caselist_names: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict[str, tuple[str, ...]](), repr=False
    )
    """Every school a disclosure of the caselist names, with its team codes, for seeding to strip."""
    newest_disclosure: date | None = None
    """The latest date among the on-topic disclosures read; None when no source was read."""
    disclosures: tuple[Disclosure, ...] = field(default=(), repr=False)
    """Every on-topic live disclosure of the sources read, as E30 records one, for the landscape report."""
    tournament_entry_snapshots: tuple[TournamentEntrySnapshot, ...] = ()
    """The snapshots on the topic only through a tournament entry, with their counts, in date order."""


async def read_seed_sources(
    *,
    store: ParsedStore,
    local: LocalEvidence,
    suppression: SuppressionList,
    topic: Topic,
    caselist: str,
    version: str | None = None,
    through: date | None = None,
    topic_map: TopicMap | None = None,
) -> SeedReading:
    """`caselist`'s parsed sources on `topic`, each with its disclosing teams and its cards' headings.

    With `through`, only disclosures dated on or before it count, so a source first disclosed later is
    left out as off the topic. `topic_map` is the whole of `topics.yaml`, whose other topics' tournament
    entries can take a disclosure off this one; None reads `topic` alone.
    """
    if not any(one.caselist == caselist for one in (*topic.caselists, *topic.tournaments)):
        raise SeedingCannotStart(f"topics.yaml gives {topic.id} no range of {caselist}")
    topics = topic_map if topic_map is not None else TopicMap(topics=(topic,))
    try:
        mapped = topics.topic(topic.id)
    except KeyError:
        mapped = None
    if mapped != topic:
        raise SeedingCannotStart(f"the topic map's {topic.id} is not the topic being read")
    versions = await store.version_directories(caselist)
    if version is None:
        if not versions:
            raise SeedingCannotStart(f"the parsed store holds no version of {caselist}")
        version = versions[-1]
    elif version not in versions:
        raise SeedingCannotStart(f"the parsed store holds no version {version} of {caselist}")
    disclosed = {source.sha256: source for source in await enumerate_sources(local, caselist)}
    names: dict[str, set[str]] = {}
    for enumerated in disclosed.values():
        for disclosure in enumerated.disclosures:
            read = parse_disclosure_path(disclosure.path, event=topic.event)
            if read.school != UNKNOWN_SCHOOL:
                codes = names.setdefault(read.school, set())
                if read.team_code != UNKNOWN_TEAM_CODE:
                    codes.add(read.team_code)
    state = await load_suppression_state(suppression)
    first_seen = first_seen_spellings(
        (disclosure.provenance_date, parse_disclosure_path(disclosure.path, event=topic.event).tournament)
        for enumerated in disclosed.values()
        for disclosure in live_disclosures(enumerated, state)
    )

    def on_the_topic(disclosure: Disclosed) -> bool:
        tournament = parse_disclosure_path(disclosure.path, event=topic.event).tournament
        resolved = topics.resolve_disclosure(
            caselist, disclosure.provenance_date, tournament, first_seen=first_seen
        )
        return resolved is not None and resolved.topic_id == topic.id

    entry_snapshots = _tournament_entry_snapshots(
        topics, topic, caselist, disclosed.values(), state, on_the_topic, through
    )
    entries = await store.read_entries(caselist, version)
    parsed = [entry for entry in entries if entry.outcome is SourceOutcome.PARSED]
    sources: list[SeedSource] = []
    disclosures: list[Disclosure] = []
    newest: date | None = None
    for entry in parsed:
        enumerated = disclosed.get(entry.source_sha256)
        on_topic = (
            [
                disclosure
                for disclosure in live_disclosures(enumerated, state)
                if (through is None or disclosure.provenance_date <= through) and on_the_topic(disclosure)
            ]
            if enumerated is not None
            else []
        )
        if not on_topic:
            continue
        record = await store.read_document(caselist, version, entry.source_sha256)
        if record is None:
            continue
        teams = tuple(_team(disclosure.path, topic) for disclosure in on_topic)
        disclosures.extend(_disclosure(caselist, entry.source_sha256, one, topic) for one in on_topic)
        latest = max(disclosure.provenance_date for disclosure in on_topic)
        newest = latest if newest is None else max(newest, latest)
        sources.append(SeedSource(sha256=entry.source_sha256, teams=teams, cards=_cards(record)))
    return SeedReading(
        caselist=caselist,
        version=version,
        topic_id=topic.id,
        entries=len(entries),
        parsed=len(parsed),
        parsed_off_topic=len(parsed) - len(sources),
        sources=tuple(sources),
        caselist_names={school: tuple(sorted(codes)) for school, codes in sorted(names.items())},
        newest_disclosure=newest,
        disclosures=tuple(disclosures),
        tournament_entry_snapshots=entry_snapshots,
    )


def _tournament_entry_snapshots(
    topics: TopicMap,
    topic: Topic,
    caselist: str,
    sources: Iterable[EnumeratedSource],
    state: SuppressionState,
    on_the_topic: Callable[[Disclosed], bool],
    through: date | None,
) -> tuple[TournamentEntrySnapshot, ...]:
    """Each snapshot on `topic` only through its tournament entries, with its live disclosures counted."""
    live = [disclosure for source in sources for disclosure in live_disclosures(source, state)]
    found: list[TournamentEntrySnapshot] = []
    for day in sorted({disclosure.provenance_date for disclosure in live}):
        if through is not None and day > through:
            continue
        resolved = topics.resolve(caselist, day)
        if resolved is None or resolved.topic_id != topic.id or not resolved.tournament_entries_only:
            continue
        week = [disclosure for disclosure in live if disclosure.provenance_date == day]
        found.append(
            TournamentEntrySnapshot(
                snapshot=day,
                tournaments=tuple(
                    entry.name for entry in topic.tournaments if entry.covers_snapshot(caselist, day)
                ),
                disclosures_on_topic=sum(1 for disclosure in week if on_the_topic(disclosure)),
                disclosures=len(week),
            )
        )
    return tuple(found)


def _team(path: str, topic: Topic) -> SeedTeam:
    read = parse_disclosure_path(path, event=topic.event)
    own = (read.school, read.team_code)
    names = tuple(name for name in own if name not in (UNKNOWN_SCHOOL, UNKNOWN_TEAM_CODE))
    names += (read.tournament,) if read.tournament else ()
    known = read.school != UNKNOWN_SCHOOL and read.team_code != UNKNOWN_TEAM_CODE
    identity = f"{read.school.casefold()}/{read.team_code.casefold()}" if known else ""
    return SeedTeam(identity=identity, side=read.side, names=names, tournament=read.tournament or None)


def _disclosure(caselist: str, sha256: str, disclosed: Disclosed, topic: Topic) -> Disclosure:
    read = parse_disclosure_path(disclosed.path, event=topic.event)
    return Disclosure(
        source_sha256=sha256,
        caselist=caselist,
        snapshot=disclosed.provenance_date,
        event=topic.event,
        school=read.school,
        team_code=read.team_code,
        side=read.side,
        tournament=read.tournament,
        round_label=read.round_label,
        source_path=disclosed.path,
        parse_warnings=read.warnings,
    )


def _cards(record: DocumentRecord) -> tuple[SeedCard, ...]:
    """Each stored card's tag, path, first paragraph and short cite, as stored (version 1 or 2)."""
    stored = record.document.get("cards")
    cards: list[SeedCard] = []
    for card in stored if isinstance(stored, list) else []:
        if not isinstance(card, dict):
            continue
        tag = card.get("tag")
        short_cite = card.get("short_cite")
        path = card.get("section_path")
        provenance = card.get("provenance")
        first = provenance.get("first_element_index") if isinstance(provenance, dict) else None
        cards.append(
            SeedCard(
                tag=tag if isinstance(tag, str) and tag else None,
                section_path=tuple(part for part in path if isinstance(part, str))
                if isinstance(path, list)
                else (),
                first_element_index=first if isinstance(first, int) and not isinstance(first, bool) else None,
                short_cite=short_cite if isinstance(short_cite, str) and short_cite else None,
            )
        )
    return tuple(cards)

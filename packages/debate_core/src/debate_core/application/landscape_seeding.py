"""The reading half of taxonomy seeding: one topic's parsed sources and the teams that disclosed them.

`scripts/seed_landscape_taxonomy.py` (`v1-e32-t01-position-taxonomy`) counts a topic's headings with
:func:`~debate_core.arguments.landscape.seeding.seed_candidates`, which takes plain values. This
module builds them from this machine's stores:

* **the sources** are the parsed entries of one version directory of the caselist's parsed card
  store, the newest unless one is named;
* **a source is on the topic** when one of its live disclosures (the suppression list neither stops
  nor holds it, :func:`~debate_core.application.caselist.parse_sources.live_disclosures`) is dated
  inside one of the topic's ranges for this caselist in `topics.yaml`;
* **the caselist's names** are every school a disclosure's path names, with its team codes, whatever
  the date, so that seeding can take another school's name out of a heading;
* **its teams** come from those disclosures' paths, read by the importer's own path parser: the
  school and team code directories, and the side in the filename. A path with no readable school or
  team code is a disclosure by no known team. Teams are never read from the store, which holds no
  path, and never from heading text.

Names stay in memory. A team's school and code, and the tournament the file was disclosed at, go to
the seeding function only to be taken out of that file's headings (a pocket named for a tournament
is not a position); nothing here writes, logs or returns them in a `repr`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources, live_disclosures
from debate_core.application.caselist.path_parser import (
    UNKNOWN_SCHOOL,
    UNKNOWN_TEAM_CODE,
    parse_disclosure_path,
)
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import DomainError
from debate_core.application.ports.parsed_store import DocumentRecord, ParsedStore, SourceOutcome
from debate_core.application.ports.suppression import SuppressionList
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.landscape import Topic

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


async def read_seed_sources(
    *,
    store: ParsedStore,
    local: LocalEvidence,
    suppression: SuppressionList,
    topic: Topic,
    caselist: str,
    version: str | None = None,
) -> SeedReading:
    """`caselist`'s parsed sources on `topic`, each with its disclosing teams and its cards' headings."""
    ranges = [one for one in topic.caselists if one.caselist == caselist]
    if not ranges:
        raise SeedingCannotStart(f"topics.yaml gives {topic.id} no range of {caselist}")
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
    entries = await store.read_entries(caselist, version)
    parsed = [entry for entry in entries if entry.outcome is SourceOutcome.PARSED]
    sources: list[SeedSource] = []
    for entry in parsed:
        enumerated = disclosed.get(entry.source_sha256)
        on_topic = (
            [
                disclosure
                for disclosure in live_disclosures(enumerated, state)
                if any(one.covers(caselist, disclosure.provenance_date) for one in ranges)
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
    )


def _team(path: str, topic: Topic) -> SeedTeam:
    read = parse_disclosure_path(path, event=topic.event)
    own = (read.school, read.team_code)
    names = tuple(name for name in own if name not in (UNKNOWN_SCHOOL, UNKNOWN_TEAM_CODE))
    names += (read.tournament,) if read.tournament else ()
    known = read.school != UNKNOWN_SCHOOL and read.team_code != UNKNOWN_TEAM_CODE
    identity = f"{read.school.casefold()}/{read.team_code.casefold()}" if known else ""
    return SeedTeam(identity=identity, side=read.side, names=names)


def _cards(record: DocumentRecord) -> tuple[SeedCard, ...]:
    """Each stored card's tag and section path, as the store holds them (version 1 or 2)."""
    stored = record.document.get("cards")
    cards: list[SeedCard] = []
    for card in stored if isinstance(stored, list) else []:
        if not isinstance(card, dict):
            continue
        tag = card.get("tag")
        path = card.get("section_path")
        cards.append(
            SeedCard(
                tag=tag if isinstance(tag, str) and tag else None,
                section_path=tuple(part for part in path if isinstance(part, str))
                if isinstance(path, list)
                else (),
            )
        )
    return tuple(cards)

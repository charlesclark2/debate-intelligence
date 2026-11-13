"""Late disclosures: a snapshot's disclosures from tournaments its topic's range began after (`v1-e32-t51`).

`topics.yaml` puts hsld26 on de-extinction from the snapshot of 2026-11-10 by its range: every disclosure
there is on the topic unless a tournament entry says otherwise (`v1-e32-t06`). A file disclosed late, from
a space colonization tournament before 2026-11-06, is counted on de-extinction all the same. The PM's
ruling of 2026-11-05 (Q2) was to count them, not to pre-list those tournaments. This module counts them
for one snapshot, from this machine's manifests and parsed store, in counts only:

* **the snapshot** must be on its topic by a range (not only through a tournament entry). Its range's
  first day is the cut: a disclosure is **late** when its tournament spelling (:func:`tournament_key`)
  was first seen, among the caselist's live disclosures, in a snapshot dated before that day, and the
  spelling holds no spelling of the topic's own tournament entries (Florida Blue Key's, on its topic
  already). A disclosure naming no tournament is never late.
* **its share** is of the snapshot's live disclosures, on any topic or none.
* **the topic-word check** classes each source of the snapshot by the words its cards' tags and headings
  hold: the topic's words, the other topic's, both, neither, or not parsed. The words are the caller's,
  given on the command line, never a list in code; and the class decides nothing. It is the check the PM
  asked for, beside the count, on the late disclosures and on the rest of the snapshot's on-topic ones.
* **spellings** are named only where two schools or more disclosed under them and no word of a caselist
  school or team code is in them (the landscape report's withholding words, :func:`caselist_words`);
  the others are counted, not named.

Nothing here writes, logs or returns a tag, a heading, a path, a school or a team code. The reading is
read-only: manifests, the suppression list and the parsed store are only read.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Final

from pydantic import ValidationError

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import (
    Disclosed,
    EnumeratedSource,
    enumerate_sources,
    live_disclosures,
)
from debate_core.application.caselist.path_parser import UNKNOWN_SCHOOL, parse_disclosure_path
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import DomainError
from debate_core.application.ports.parsed_store import DocumentRecord, ParsedStore, SourceOutcome
from debate_core.application.ports.suppression import SuppressionList
from debate_core.arguments.landscape.link_chains import MINIMUM_WITHHELD_WORD, caselist_words, is_withheld
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape import Topic, TopicMap, tournament_key

__all__ = [
    "LateDisclosureCount",
    "LateDisclosuresCannotBeCounted",
    "SpellingCount",
    "TopicWords",
    "WordClass",
    "count_late_disclosures",
]

MINIMUM_SCHOOLS_TO_NAME: Final = 2
"""A spelling is named only when this many schools disclosed under it; fewer, it is counted only."""


class LateDisclosuresCannotBeCounted(DomainError):
    """The snapshot is not in the store, or no topic's range covers it."""


class WordClass(StrEnum):
    """What one source's tags and headings hold, of the topic's words and the other topic's."""

    TOPIC_ONLY = "topic words only"
    BOTH = "both"
    OTHER_ONLY = "other topic words only"
    NEITHER = "neither"
    NOT_PARSED = "not parsed"


@dataclass(frozen=True, slots=True)
class TopicWords:
    """The check's words: the snapshot topic's, and the topic late files would really be on."""

    topic: tuple[str, ...]
    other: tuple[str, ...]

    def __post_init__(self) -> None:
        for words in (self.topic, self.other):
            if not words or not all(_reduced(word) for word in words):
                raise ValueError("each side of the topic-word check needs a word with a letter or digit")

    def classify(self, texts: Iterable[str]) -> WordClass:
        reduced = [_reduced(text) for text in texts]
        topic = any(_reduced(word) in text for word in self.topic for text in reduced)
        other = any(_reduced(word) in text for word in self.other for text in reduced)
        if topic and other:
            return WordClass.BOTH
        if topic:
            return WordClass.TOPIC_ONLY
        return WordClass.OTHER_ONLY if other else WordClass.NEITHER


def _word_classes() -> dict[str, int]:
    return {one.value: 0 for one in WordClass}


@dataclass(frozen=True, slots=True)
class GroupCheck:
    """One group's disclosures and sources, each counted by its source's word class."""

    disclosures: dict[str, int] = field(default_factory=_word_classes)
    sources: dict[str, int] = field(default_factory=_word_classes)


@dataclass(frozen=True, slots=True)
class SpellingCount:
    """One late spelling: named only when :data:`MINIMUM_SCHOOLS_TO_NAME` schools use it and none is in it."""

    spelling: str
    first_seen: date
    schools: int
    """Schools whose live disclosures of the caselist, in any snapshot, carry the spelling."""
    disclosures: int
    sources: int
    word_classes: dict[str, int]
    """This spelling's late sources by word class."""


@dataclass(frozen=True, slots=True)
class LateDisclosureCount:
    """One snapshot's late disclosures, their share, and the topic-word check: counts only."""

    caselist: str
    snapshot: date
    newest_snapshot: date
    topic_id: str
    range_from: date
    first_seen_through: date | None
    """The newest snapshot dated before `range_from`: a late spelling was first seen on or before it."""
    entry_spellings: tuple[str, ...]
    """The topic's own tournament entries' spellings (public configuration); none is late."""
    parsed_version: str | None
    disclosures: int
    """The snapshot's live disclosures, on any topic or none: the share's whole."""
    sources: int
    off_topic: int
    """Of `disclosures`, those a tournament entry puts on another topic, or on none."""
    no_tournament: int
    entry_spelling_disclosures: int
    late_disclosures: int
    late_sources: int
    late_schools: int
    late_spellings: int
    late_by_first_seen: dict[str, int]
    check: dict[str, GroupCheck]
    """`late`, `tournament entry spellings` and `other`: the snapshot's on-topic disclosures, partitioned."""
    named_spellings: tuple[SpellingCount, ...]
    one_school_spellings: tuple[int, int]
    """Late spellings fewer than two schools use, not named: (spellings, disclosures)."""
    school_word_spellings: tuple[int, int]
    """Late spellings two schools or more use that hold a school or team-code word, not named."""

    @property
    def late_share(self) -> float:
        return self.late_disclosures / self.disclosures if self.disclosures else 0.0

    def as_json(self) -> dict[str, object]:
        """Counts, dates, public configuration and the spellings that may be named: nothing else."""
        return {
            "caselist": self.caselist,
            "snapshot": self.snapshot.isoformat(),
            "newest_snapshot": self.newest_snapshot.isoformat(),
            "topic": self.topic_id,
            "range_from": self.range_from.isoformat(),
            "first_seen_through": self.first_seen_through.isoformat() if self.first_seen_through else None,
            "tournament_entry_spellings": list(self.entry_spellings),
            "parsed_version": self.parsed_version,
            "disclosures": self.disclosures,
            "sources": self.sources,
            "off_topic": self.off_topic,
            "no_tournament": self.no_tournament,
            "tournament_entry_spelling_disclosures": self.entry_spelling_disclosures,
            "late": {
                "disclosures": self.late_disclosures,
                "sources": self.late_sources,
                "schools": self.late_schools,
                "spellings": self.late_spellings,
                "share": round(self.late_share, 4),
                "by_first_seen": dict(self.late_by_first_seen),
            },
            "topic_word_check": {
                group: {"disclosures": dict(one.disclosures), "sources": dict(one.sources)}
                for group, one in self.check.items()
            },
            "late_spellings_named": [
                {
                    "spelling": one.spelling,
                    "first_seen": one.first_seen.isoformat(),
                    "schools": one.schools,
                    "disclosures": one.disclosures,
                    "sources": one.sources,
                    "sources_by_word_class": dict(one.word_classes),
                }
                for one in self.named_spellings
            ],
            "late_spellings_not_named": {
                "fewer_than_two_schools": {
                    "spellings": self.one_school_spellings[0],
                    "disclosures": self.one_school_spellings[1],
                },
                "holding_a_school_or_team_code_word": {
                    "spellings": self.school_word_spellings[0],
                    "disclosures": self.school_word_spellings[1],
                },
            },
        }


LATE: Final = "late"
ENTRY: Final = "tournament entry spellings"
OTHER: Final = "other"


@dataclass(frozen=True, slots=True)
class _Read:
    """One live disclosure, read: its source, its date, its tournament text and key, its school."""

    sha256: str
    when: date
    tournament: str | None
    key: str
    school: str
    disclosure: Disclosure


async def count_late_disclosures(
    *,
    store: ParsedStore,
    local: LocalEvidence,
    suppression: SuppressionList,
    topic_map: TopicMap,
    caselist: str,
    snapshot: date,
    words: TopicWords,
    version: str | None = None,
) -> LateDisclosureCount:
    """`caselist`'s late disclosures in `snapshot`, with their share and the topic-word check."""
    resolved = topic_map.resolve(caselist, snapshot)
    if resolved is None or resolved.tournament_entries_only:
        raise LateDisclosuresCannotBeCounted(
            f"no topic's range covers {caselist}'s snapshot of {snapshot.isoformat()}"
        )
    topic = topic_map.topic(resolved.topic_id)
    covering = topic.range_covering(caselist, snapshot)
    if covering is None:  # pragma: no cover - resolve() found this range
        raise LateDisclosuresCannotBeCounted(f"{topic.id} has no range covering {snapshot.isoformat()}")
    enumerated = await enumerate_sources(local, caselist)
    every_date = {disclosed.provenance_date for source in enumerated for disclosed in source.disclosures}
    if snapshot not in every_date:
        raise LateDisclosuresCannotBeCounted(
            f"the store holds no manifest of {caselist}'s snapshot of {snapshot.isoformat()}"
        )
    state = await load_suppression_state(suppression)
    read = [
        _read(caselist, source, disclosed, topic)
        for source in enumerated
        for disclosed in live_disclosures(source, state)
    ]
    entry_spellings = tuple(dict.fromkeys(s for entry in topic.tournaments for s in entry.spellings))
    first_seen = _first_seen(read)
    schools_by_key = _schools_by_key(read)
    texts_by_key = _texts_by_key(read)
    withholding = caselist_words(one.disclosure for one in read)

    week = [one for one in read if one.when == snapshot]
    on_topic: list[_Read] = []
    off_topic = 0
    for one in week:
        resolution = topic_map.resolve_disclosure(caselist, snapshot, one.tournament)
        if resolution is not None and resolution.topic_id == topic.id:
            on_topic.append(one)
        else:
            off_topic += 1

    def group_of(one: _Read) -> str:
        if one.key and any(spelling in one.key for spelling in entry_spellings):
            return ENTRY
        if one.key and first_seen[one.key] < covering.effective_from:
            return LATE
        return OTHER

    grouped = [(one, group_of(one)) for one in on_topic]
    version = await _version(store, caselist, version)
    classes = await _word_classes_of(store, caselist, version, {one.sha256 for one in week}, words)
    check = {LATE: GroupCheck(), ENTRY: GroupCheck(), OTHER: GroupCheck()}
    for one, group in grouped:
        check[group].disclosures[classes[one.sha256]] += 1
    for group in check:
        for digest in {one.sha256 for one, its in grouped if its == group}:
            check[group].sources[classes[digest]] += 1

    late = [one for one, group in grouped if group == LATE]
    named, one_school, school_word = _spellings(
        late, first_seen, schools_by_key, texts_by_key, withholding, classes
    )
    earlier = sorted(day for day in every_date if day < covering.effective_from)
    return LateDisclosureCount(
        caselist=caselist,
        snapshot=snapshot,
        newest_snapshot=max(every_date),
        topic_id=topic.id,
        range_from=covering.effective_from,
        first_seen_through=earlier[-1] if earlier else None,
        entry_spellings=entry_spellings,
        parsed_version=version,
        disclosures=len(week),
        sources=len({one.sha256 for one in week}),
        off_topic=off_topic,
        no_tournament=sum(1 for one in week if not one.key),
        entry_spelling_disclosures=sum(1 for _, group in grouped if group == ENTRY),
        late_disclosures=len(late),
        late_sources=len({one.sha256 for one in late}),
        late_schools=len({one.school for one in late if one.school}),
        late_spellings=len({one.key for one in late}),
        late_by_first_seen={
            day.isoformat(): n for day, n in sorted(Counter(first_seen[one.key] for one in late).items())
        },
        check=check,
        named_spellings=named,
        one_school_spellings=one_school,
        school_word_spellings=school_word,
    )


def _reduced(text: str) -> str:
    """Letters and digits without case, as a tournament spelling is reduced (:func:`tournament_key`)."""
    return tournament_key(text)


def _read(caselist: str, source: EnumeratedSource, disclosed: Disclosed, topic: Topic) -> _Read:
    parsed = parse_disclosure_path(disclosed.path, event=topic.event)
    school = parsed.school.casefold() if parsed.school != UNKNOWN_SCHOOL else ""
    try:
        disclosure = Disclosure(
            source_sha256=source.sha256,
            caselist=caselist,
            snapshot=disclosed.provenance_date,
            event=topic.event,
            school=parsed.school,
            team_code=parsed.team_code,
            side=parsed.side,
            tournament=parsed.tournament,
            round_label=parsed.round_label,
            source_path=disclosed.path,
            parse_warnings=parsed.warnings,
        )
    except ValidationError:
        # The error's text quotes the path's school and team code, which go nowhere.
        raise LateDisclosuresCannotBeCounted(
            f"a disclosure of {caselist}'s snapshot of {disclosed.snapshot} could not be read as one"
        ) from None
    return _Read(
        sha256=source.sha256,
        when=disclosed.provenance_date,
        tournament=parsed.tournament,
        key=tournament_key(parsed.tournament),
        school=school,
        disclosure=disclosure,
    )


def _first_seen(read: Iterable[_Read]) -> dict[str, date]:
    first: dict[str, date] = {}
    for one in read:
        if one.key and (one.key not in first or one.when < first[one.key]):
            first[one.key] = one.when
    return first


def _schools_by_key(read: Iterable[_Read]) -> dict[str, set[str]]:
    schools: dict[str, set[str]] = defaultdict(set)
    for one in read:
        if one.key and one.school:
            schools[one.key].add(one.school)
    return schools


def _texts_by_key(read: Iterable[_Read]) -> dict[str, set[str]]:
    texts: dict[str, set[str]] = defaultdict(set)
    for one in read:
        if one.key and one.tournament:
            texts[one.key].add(one.tournament)
    return texts


def _holds_a_caselist_word(key: str, texts: Iterable[str], words: frozenset[str]) -> bool:
    """A spelling is withheld when a tournament text of it holds a school or team-code word, or the
    spelling itself holds a school or team-code word long enough to be one (a name run together)."""
    return any(is_withheld(text, words) for text in texts) or any(
        word in key for word in words if len(word) >= MINIMUM_WITHHELD_WORD
    )


def _spellings(
    late: Sequence[_Read],
    first_seen: Mapping[str, date],
    schools_by_key: Mapping[str, set[str]],
    texts_by_key: Mapping[str, set[str]],
    withholding: frozenset[str],
    classes: Mapping[str, str],
) -> tuple[tuple[SpellingCount, ...], tuple[int, int], tuple[int, int]]:
    by_key: dict[str, list[_Read]] = defaultdict(list)
    for one in late:
        by_key[one.key].append(one)
    named: list[SpellingCount] = []
    one_school = [0, 0]
    school_word = [0, 0]
    for key, ones in by_key.items():
        if len(schools_by_key.get(key, ())) < MINIMUM_SCHOOLS_TO_NAME:
            one_school[0] += 1
            one_school[1] += len(ones)
            continue
        if _holds_a_caselist_word(key, texts_by_key.get(key, ()), withholding):
            school_word[0] += 1
            school_word[1] += len(ones)
            continue
        digests = {one.sha256 for one in ones}
        word_classes = _word_classes()
        for digest in digests:
            word_classes[classes[digest]] += 1
        named.append(
            SpellingCount(
                spelling=key,
                first_seen=first_seen[key],
                schools=len(schools_by_key[key]),
                disclosures=len(ones),
                sources=len(digests),
                word_classes=word_classes,
            )
        )
    named.sort(key=lambda one: (-one.disclosures, one.spelling))
    return tuple(named), (one_school[0], one_school[1]), (school_word[0], school_word[1])


async def _version(store: ParsedStore, caselist: str, version: str | None) -> str | None:
    versions = await store.version_directories(caselist)
    if version is None:
        return versions[-1] if versions else None
    if version not in versions:
        raise LateDisclosuresCannotBeCounted(f"the parsed store holds no version {version} of {caselist}")
    return version


async def _word_classes_of(
    store: ParsedStore, caselist: str, version: str | None, digests: set[str], words: TopicWords
) -> dict[str, str]:
    """Each source's word class; `not parsed` for one the version did not parse into a document."""
    classes = {digest: WordClass.NOT_PARSED.value for digest in digests}
    if version is None:
        return classes
    entries = await store.read_entries(caselist, version)
    parsed = {
        entry.source_sha256
        for entry in entries
        if entry.outcome is SourceOutcome.PARSED and entry.source_sha256 in digests
    }
    for digest in sorted(parsed):
        record = await store.read_document(caselist, version, digest)
        if record is not None:
            classes[digest] = words.classify(_tags_and_headings(record)).value
    return classes


def _tags_and_headings(record: DocumentRecord) -> list[str]:
    """Every card's tag and the headings over it, as stored."""
    stored = record.document.get("cards")
    texts: list[str] = []
    for card in stored if isinstance(stored, list) else []:
        if not isinstance(card, dict):
            continue
        tag = card.get("tag")
        if isinstance(tag, str):
            texts.append(tag)
        path = card.get("section_path")
        if isinstance(path, list):
            texts.extend(part for part in path if isinstance(part, str))
    return texts

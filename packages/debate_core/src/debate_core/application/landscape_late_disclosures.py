"""Late disclosures: a snapshot's disclosures from tournaments its topic's range began after (`v1-e32-t51`).

`topics.yaml` puts hsld26 on de-extinction from the snapshot of 2026-11-10 by its range. A file disclosed
late, from a space colonization tournament before 2026-11-06, would be counted on de-extinction too. On
2026-11-10 that was 356 of 1,639 disclosures. The PM's ruling of 2026-11-12 (Q1) put them on the earlier
topic by spelling history, behind a key on the range (:meth:`~debate_core.domain.landscape.TopicMap.is_late`
and :meth:`~debate_core.domain.landscape.TopicMap.resolve_disclosure`). This module counts them for one
snapshot, from this machine's manifests and parsed store, for `scripts/count_late_disclosures.py` and for
the landscape report's line (Q2), in counts only:

* **the snapshot** must be on its topic by a range, and the caselist must have an earlier topic's range.
* **late** is the domain's test: the spelling was first seen, among the caselist's live disclosures, in
  a snapshot before the range began, no tournament entry matches the disclosure, and the spelling holds
  none of the topic's own entry spellings. Whether the range moves them is the domain's too: `moved_to`
  names the earlier topic when it does.
* **the share** is of the snapshot's live disclosures, on any topic or none.
* **the topic-word check** classes each source of the snapshot by the words its cards' tags and headings
  hold: this topic's, the earlier topic's, both, neither, or not parsed. The words are each topic's
  `check_words` in `topics.yaml` unless the caller gives its own. They decide nothing.

No tournament spelling is named (the PM's Q3 ruling of 2026-11-12): only how many there are. Nothing here
writes, logs or returns a tag, a heading, a path, a school, a team code or a tournament. The reading is
read-only: manifests, the suppression list and the parsed store are only read.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources, live_disclosures
from debate_core.application.caselist.path_parser import UNKNOWN_SCHOOL, parse_disclosure_path
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import DomainError
from debate_core.application.ports.parsed_store import DocumentRecord, ParsedStore, SourceOutcome
from debate_core.application.ports.suppression import SuppressionList
from debate_core.domain.landscape import LateDisclosures, TopicMap, first_seen_spellings, tournament_key

__all__ = [
    "LateDisclosureCount",
    "LateDisclosuresCannotBeCounted",
    "TopicWords",
    "WordClass",
    "count_late_disclosures",
]


class LateDisclosuresCannotBeCounted(DomainError):
    """The snapshot is not in the store, no range covers it, or the caselist has no earlier topic."""


class WordClass(StrEnum):
    """What one source's tags and headings hold, of this topic's words and the earlier topic's."""

    TOPIC_ONLY = "topic words only"
    BOTH = "both"
    OTHER_ONLY = "other topic words only"
    NEITHER = "neither"
    NOT_PARSED = "not parsed"


@dataclass(frozen=True, slots=True)
class TopicWords:
    """The check's words: the snapshot topic's, and the earlier topic's."""

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


LATE: Final = "late"
ENTRY: Final = "tournament entry spellings"
OTHER: Final = "other"


@dataclass(frozen=True, slots=True)
class LateDisclosureCount:
    """One snapshot's late disclosures, their share, and the topic-word check: counts only."""

    caselist: str
    snapshot: date
    newest_snapshot: date
    topic_id: str
    earlier_topic_id: str
    earlier_topic_name: str
    moved: bool
    """True when the range puts late disclosures on the earlier topic (its key in `topics.yaml`)."""
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
    """Of `disclosures`, those not late that are not on the topic: another topic's entry's, or none."""
    no_tournament: int
    entry_spelling_disclosures: int
    late_disclosures: int
    late_sources: int
    late_schools: int
    late_spellings: int
    late_by_first_seen: dict[str, int]
    check: dict[str, GroupCheck] | None
    """`late`, `tournament entry spellings` and `other`, the snapshot's disclosures not off the topic;
    None when no words were given and `topics.yaml` gives a topic none."""

    @property
    def late_share(self) -> float:
        return self.late_disclosures / self.disclosures if self.disclosures else 0.0

    def for_the_report(self) -> LateDisclosures:
        """The report's line: the count, its share's whole, and the late sources' check."""
        late = self.check[LATE].sources if self.check is not None else None
        return LateDisclosures(
            snapshot=self.snapshot,
            range_from=self.range_from,
            earlier_topic=self.earlier_topic_name,
            moved=self.moved,
            disclosures=self.disclosures,
            late=self.late_disclosures,
            late_sources=self.late_sources,
            this_topic_only=late[WordClass.TOPIC_ONLY] if late is not None else None,
            earlier_topic_only=late[WordClass.OTHER_ONLY] if late is not None else None,
        )

    def as_json(self) -> dict[str, object]:
        """Counts, dates and public configuration: no tournament, school, team code, tag or heading."""
        return {
            "caselist": self.caselist,
            "snapshot": self.snapshot.isoformat(),
            "newest_snapshot": self.newest_snapshot.isoformat(),
            "topic": self.topic_id,
            "earlier_topic": self.earlier_topic_id,
            "moved_to": self.earlier_topic_id if self.moved else None,
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
            "topic_word_check": None
            if self.check is None
            else {
                group: {"disclosures": dict(one.disclosures), "sources": dict(one.sources)}
                for group, one in self.check.items()
            },
        }


@dataclass(frozen=True, slots=True)
class _Read:
    """One live disclosure, read: its source, its date, its tournament text and key, its school."""

    sha256: str
    when: date
    tournament: str | None
    key: str
    school: str


async def count_late_disclosures(
    *,
    store: ParsedStore,
    local: LocalEvidence,
    suppression: SuppressionList,
    topic_map: TopicMap,
    caselist: str,
    snapshot: date,
    words: TopicWords | None = None,
    version: str | None = None,
) -> LateDisclosureCount:
    """`caselist`'s late disclosures in `snapshot`, with their share and the topic-word check.

    Without `words`, the check reads each topic's `check_words`; with none on either topic, it is skipped.
    """
    cut = topic_map.late_cut(caselist, snapshot)
    if cut is None:
        raise LateDisclosuresCannotBeCounted(
            f"no topic's range covers {caselist}'s snapshot of {snapshot.isoformat()} with an earlier "
            "topic's range before it"
        )
    if words is None and cut.topic.check_words and cut.earlier.check_words:
        words = TopicWords(topic=cut.topic.check_words, other=cut.earlier.check_words)
    enumerated = await enumerate_sources(local, caselist)
    every_date = {disclosed.provenance_date for source in enumerated for disclosed in source.disclosures}
    if snapshot not in every_date:
        raise LateDisclosuresCannotBeCounted(
            f"the store holds no manifest of {caselist}'s snapshot of {snapshot.isoformat()}"
        )
    state = await load_suppression_state(suppression)
    read: list[_Read] = []
    for source in enumerated:
        for disclosed in live_disclosures(source, state):
            parsed = parse_disclosure_path(disclosed.path, event=cut.topic.event)
            read.append(
                _Read(
                    sha256=source.sha256,
                    when=disclosed.provenance_date,
                    tournament=parsed.tournament,
                    key=tournament_key(parsed.tournament),
                    school=parsed.school.casefold() if parsed.school != UNKNOWN_SCHOOL else "",
                )
            )
    first_seen = first_seen_spellings((one.when, one.tournament) for one in read)
    entry_spellings = tuple(dict.fromkeys(s for entry in cut.topic.tournaments for s in entry.spellings))

    week = [one for one in read if one.when == snapshot]
    grouped: list[tuple[_Read, str]] = []
    off_topic = 0
    for one in week:
        if topic_map.is_late(caselist, snapshot, one.tournament, first_seen):
            grouped.append((one, LATE))
            continue
        resolution = topic_map.resolve_disclosure(caselist, snapshot, one.tournament, first_seen=first_seen)
        if resolution is None or resolution.topic_id != cut.topic.id:
            off_topic += 1
        elif one.key and any(spelling in one.key for spelling in entry_spellings):
            grouped.append((one, ENTRY))
        else:
            grouped.append((one, OTHER))

    version = await _version(store, caselist, version)
    check: dict[str, GroupCheck] | None = None
    if words is not None:
        classes = await _word_classes_of(store, caselist, version, {one.sha256 for one in week}, words)
        check = {LATE: GroupCheck(), ENTRY: GroupCheck(), OTHER: GroupCheck()}
        for one, group in grouped:
            check[group].disclosures[classes[one.sha256]] += 1
        for group in check:
            for digest in {one.sha256 for one, its in grouped if its == group}:
                check[group].sources[classes[digest]] += 1

    late = [one for one, group in grouped if group == LATE]
    earlier = sorted(day for day in every_date if day < cut.range.effective_from)
    return LateDisclosureCount(
        caselist=caselist,
        snapshot=snapshot,
        newest_snapshot=max(every_date),
        topic_id=cut.topic.id,
        earlier_topic_id=cut.earlier.id,
        earlier_topic_name=cut.earlier.name,
        moved=cut.range.late_disclosures_on_earlier_topic,
        range_from=cut.range.effective_from,
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
    )


def _reduced(text: str) -> str:
    """Letters and digits without case, as a tournament spelling is reduced (:func:`tournament_key`)."""
    return tournament_key(text)


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

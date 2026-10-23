"""Taxonomy candidates seeded from the headings teams disclosed under (`v1-e32-t01` ac4).

A taxonomy is seeded, not invented: the positions a coach curates come from the pocket, hat and
block headings in the parsed card store. :func:`seed_candidates` reads one topic's sources, each
with the headings over its cards and the teams that disclosed it, and counts every normalized
heading (:func:`~debate_core.arguments.landscape.headings.normalize_heading`) by documents and by
distinct teams. :func:`write_candidates_csv` writes the rows for the coach; :func:`review_sheet`
sets a draft taxonomy beside them. Deterministic and pure: no model, no I/O of its own, the same
rows in the same order for the same sources.

## What is counted

* **A document** is one source, however many of its cards sit under a heading.
* **A team** is a disclosing team's opaque identity, taken from the source's disclosures by the
  caller. Never from heading text: two headings naming two teams are still one team's if one team
  disclosed both. A source no readable team disclosed counts as a document and as no team.
* **The side** is the disclosure's: `aff_teams` and `neg_teams` count the teams that disclosed the
  source on that side (PF's pro and con are counted as aff and neg).
* **The level** is certain only on a full path. A card's `section_path` leaves out a level the file
  skipped, so `(pocket, hat, block)` says which is which and a shorter path does not; a heading
  takes the level most of its documents show, or `unknown` when none shows one.
* **An answer** (`AT: Spending DA`) is a row of its own, beside the row of what it answers and in
  the same suggested position.

## What never reaches the CSV

* **Any heading fewer than `minimum_teams` teams use**, two by default. Such a heading can point
  at the one team that wrote it; the counts say how many were left out.
* **A team's own names.** A disclosure's school, team code and tournament are taken out of the
  headings of the file before anything is counted (`Maple Grove Neg` is `neg`, which is a side label
  and no heading at all).
* **A card's tag.** A card the file gave no tag carries the tag still open above it in its path,
  which is a claim and not a heading; it is left out, as is anything past the block level.

Nothing here logs, and the `repr` of every value that holds a name or a tag withholds it.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, TextIO

from debate_core.arguments.landscape.headings import NormalizedHeading, normalize_heading
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy

__all__ = [
    "CANDIDATE_COLUMNS",
    "DEFAULT_MINIMUM_TEAMS",
    "CandidateRow",
    "HeadingLevel",
    "SeedCard",
    "SeedSource",
    "SeedTeam",
    "Seeding",
    "SeedingCounts",
    "read_candidates_csv",
    "review_sheet",
    "seed_candidates",
    "suggest_position",
    "write_candidates_csv",
]

DEFAULT_MINIMUM_TEAMS: Final = 2
"""A heading fewer teams use than this is left out of the candidates (the PM's ruling, 2026-10-22)."""

_SUGGESTED_ID_WORDS: Final = 8


class HeadingLevel(StrEnum):
    """Where a heading sits over its cards, when the path says so."""

    POCKET = "pocket"
    HAT = "hat"
    BLOCK = "block"
    UNKNOWN = "unknown"


_LEVELS: Final = (HeadingLevel.POCKET, HeadingLevel.HAT, HeadingLevel.BLOCK)


@dataclass(frozen=True, slots=True)
class SeedTeam:
    """One disclosing team of a source: an opaque identity, the side, and the names to strip."""

    identity: str = field(repr=False)
    """Equal for two disclosures by one team; never written anywhere."""

    side: Side
    names: tuple[str, ...] = field(default=(), repr=False)
    """The school and team code the team disclosed under, taken out of its headings; never written."""


@dataclass(frozen=True, slots=True)
class SeedCard:
    """One card's place: the headings above it, and its tag only to tell an open tag from a heading."""

    tag: str | None = field(repr=False)
    section_path: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class SeedSource:
    """One parsed source on the topic: its digest, the teams that disclosed it, and its cards."""

    sha256: str
    teams: tuple[SeedTeam, ...]
    cards: tuple[SeedCard, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class CandidateRow:
    """One normalized heading and what reads it: a row of the candidates CSV."""

    suggested_position_id: str
    suggested_kind: str
    """A :class:`~debate_core.domain.landscape.PositionKind` value, or empty when no kind word shows."""
    cluster_teams: int
    """Distinct teams over every heading suggesting the same position, this one's left-out kin included."""
    normalized_heading: str
    answer: bool
    level: HeadingLevel
    documents: int
    teams: int
    aff_teams: int
    neg_teams: int


CANDIDATE_COLUMNS: Final = (
    "suggested_position_id",
    "suggested_kind",
    "cluster_teams",
    "normalized_heading",
    "answer",
    "level",
    "documents",
    "teams",
    "aff_teams",
    "neg_teams",
)


@dataclass(frozen=True, slots=True)
class SeedingCounts:
    """What one seeding read and wrote, for the run's summary and the session report."""

    sources: int
    sources_without_team: int
    cards: int
    headings: int
    """Heading occurrences counted: one per normalized heading per document."""
    distinct_headings: int
    candidates: int
    left_out_below_minimum_teams: int


@dataclass(frozen=True, slots=True)
class Seeding:
    rows: tuple[CandidateRow, ...]
    counts: SeedingCounts


@dataclass(slots=True)
class _Tally:
    documents: set[str] = field(default_factory=lambda: set[str]())
    teams: set[str] = field(default_factory=lambda: set[str]())
    aff: set[str] = field(default_factory=lambda: set[str]())
    neg: set[str] = field(default_factory=lambda: set[str]())
    levels: Counter[HeadingLevel] = field(default_factory=lambda: Counter[HeadingLevel]())


def seed_candidates(sources: Iterable[SeedSource], *, minimum_teams: int = DEFAULT_MINIMUM_TEAMS) -> Seeding:
    """Every normalized heading over `sources`' cards, counted, with the ones too few teams use left out."""
    if minimum_teams < 1:
        raise ValueError(f"the minimum number of teams is at least 1; got {minimum_teams}")
    tallies: dict[tuple[str, bool], _Tally] = defaultdict(_Tally)
    source_count = without_team = card_count = occurrences = 0
    for one in sources:
        source_count += 1
        card_count += len(one.cards)
        known = [team for team in one.teams if team.identity]
        if not known:
            without_team += 1
        seen = _headings_of(one)
        occurrences += len({heading for heading, _ in seen})
        for heading, level in seen:
            tally = tallies[heading]
            tally.documents.add(one.sha256)
            tally.levels[level] += 1
            for team in known:
                tally.teams.add(team.identity)
                if team.side in (Side.AFF, Side.PRO):
                    tally.aff.add(team.identity)
                elif team.side in (Side.NEG, Side.CON):
                    tally.neg.add(team.identity)
    clusters: dict[str, set[str]] = defaultdict(set)
    suggestions = {heading: suggest_position(heading[0]) for heading in tallies}
    for heading, tally in tallies.items():
        clusters[suggestions[heading][0]].update(tally.teams)
    rows = [
        CandidateRow(
            suggested_position_id=suggestions[heading][0],
            suggested_kind=suggestions[heading][1],
            cluster_teams=len(clusters[suggestions[heading][0]]),
            normalized_heading=heading[0],
            answer=heading[1],
            level=_level_of(tally.levels),
            documents=len(tally.documents),
            teams=len(tally.teams),
            aff_teams=len(tally.aff),
            neg_teams=len(tally.neg),
        )
        for heading, tally in tallies.items()
        if len(tally.teams) >= minimum_teams
    ]
    rows.sort(
        key=lambda row: (
            -row.cluster_teams,
            row.suggested_position_id,
            -row.teams,
            -row.documents,
            row.normalized_heading,
            row.answer,
        )
    )
    return Seeding(
        rows=tuple(rows),
        counts=SeedingCounts(
            sources=source_count,
            sources_without_team=without_team,
            cards=card_count,
            headings=occurrences,
            distinct_headings=len(tallies),
            candidates=len(rows),
            left_out_below_minimum_teams=len(tallies) - len(rows),
        ),
    )


def _headings_of(source: SeedSource) -> set[tuple[tuple[str, bool], HeadingLevel]]:
    """Each (normalized heading, answer) over the source's cards, once per level it is seen at."""
    names = [name for team in source.teams for name in team.names if name.strip()]
    tags = {card.tag for card in source.cards if card.tag is not None}
    seen: set[tuple[tuple[str, bool], HeadingLevel]] = set()
    for card in source.cards:
        path = card.section_path
        if card.tag is None and path and path[-1] in tags:
            path = path[:-1]
        path = path[: len(_LEVELS)]
        complete = len(path) == len(_LEVELS)
        for index, raw in enumerate(path):
            normalized = _normalized_without_names(raw, names)
            if normalized.is_empty:
                continue
            seen.add(
                ((normalized.text, normalized.answer), _LEVELS[index] if complete else HeadingLevel.UNKNOWN)
            )
    return seen


def _normalized_without_names(raw: str, names: Sequence[str]) -> NormalizedHeading:
    """`raw` normalized, with the disclosing teams' own school and team code taken out first."""
    for name in names:
        words = name.split()
        pattern = (
            r"(?<![0-9A-Za-z])" + r"[\s_-]+".join(re.escape(word) for word in words) + r"(?![0-9A-Za-z])"
        )
        raw = re.sub(pattern, " ", raw, flags=re.IGNORECASE)
    normalized = normalize_heading(raw)
    text = normalized.text
    for name in names:
        name_text = normalize_heading(name).text
        if name_text:
            text = " ".join(re.sub(rf"(?<!\S){re.escape(name_text)}(?!\S)", " ", text).split())
    return normalize_heading(text) if text != normalized.text else normalized


def _level_of(levels: Counter[HeadingLevel]) -> HeadingLevel:
    """The level most documents show, pocket before hat before block on a tie; else unknown."""
    certain = [(levels[level], -index, level) for index, level in enumerate(_LEVELS) if levels[level]]
    return max(certain)[2] if certain else HeadingLevel.UNKNOWN


# ------------------------------------------------------------------------------------------------
# Suggested positions
# ------------------------------------------------------------------------------------------------

_KIND_WORDS: Final = {
    "da": "da",
    "das": "da",
    "disad": "da",
    "disads": "da",
    "disadvantage": "da",
    "disadvantages": "da",
    "cp": "cp",
    "cps": "cp",
    "counterplan": "cp",
    "counterplans": "cp",
    "k": "k",
    "ks": "k",
    "kritik": "k",
    "kritiks": "k",
    "critique": "k",
    "t": "t",
    "topicality": "t",
    "adv": "advantage",
    "advs": "advantage",
    "advantage": "advantage",
    "advantages": "advantage",
    "aff": "aff",
    "affirmative": "aff",
}
_THEORY_LAST_WORDS: Final = frozenset({"bad", "good"})


def suggest_position(heading: str) -> tuple[str, str]:
    """`(suggested id, kind)` for a normalized heading: its words with the kind word moved last.

    `spending disad` and `spending da` both suggest `spending-da`; `adv growth` suggests
    `growth-advantage`; a heading ending in `bad` or `good`, or naming `theory`, is theory and keeps
    its words (`condo-bad`). With no kind word the id is the words and the kind is empty. Only a
    suggestion: the coach names the positions.
    """
    words = heading.replace("counter plan", "counterplan").split()
    if not words:
        return "", ""
    if "theory" in words or words[-1] in _THEORY_LAST_WORDS:
        return "-".join(words[:_SUGGESTED_ID_WORDS]), "theory"
    if words[-1] in _KIND_WORDS:
        kind, core = _KIND_WORDS[words[-1]], words[:-1]
    elif words[0] in _KIND_WORDS:
        kind, core = _KIND_WORDS[words[0]], words[1:]
    else:
        return "-".join(words[:_SUGGESTED_ID_WORDS]), ""
    return "-".join([*core[: _SUGGESTED_ID_WORDS - 1], kind]), kind


# ------------------------------------------------------------------------------------------------
# The CSV
# ------------------------------------------------------------------------------------------------


def write_candidates_csv(rows: Iterable[CandidateRow], stream: TextIO) -> None:
    """The rows under a header of :data:`CANDIDATE_COLUMNS`: headings and counts, nothing else."""
    writer = csv.writer(stream)
    writer.writerow(CANDIDATE_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.suggested_position_id,
                row.suggested_kind,
                row.cluster_teams,
                row.normalized_heading,
                "true" if row.answer else "false",
                row.level.value,
                row.documents,
                row.teams,
                row.aff_teams,
                row.neg_teams,
            ]
        )


def read_candidates_csv(stream: TextIO) -> tuple[CandidateRow, ...]:
    """The rows :func:`write_candidates_csv` wrote. `ValueError` for a file with other columns."""
    reader = csv.DictReader(stream)
    if tuple(reader.fieldnames or ()) != CANDIDATE_COLUMNS:
        raise ValueError(f"a candidates CSV has the columns {', '.join(CANDIDATE_COLUMNS)}")
    return tuple(
        CandidateRow(
            suggested_position_id=line["suggested_position_id"],
            suggested_kind=line["suggested_kind"],
            cluster_teams=int(line["cluster_teams"]),
            normalized_heading=line["normalized_heading"],
            answer=line["answer"] == "true",
            level=HeadingLevel(line["level"]),
            documents=int(line["documents"]),
            teams=int(line["teams"]),
            aff_teams=int(line["aff_teams"]),
            neg_teams=int(line["neg_teams"]),
        )
        for line in reader
    )


# ------------------------------------------------------------------------------------------------
# The coach's review sheet
# ------------------------------------------------------------------------------------------------


def review_sheet(rows: Sequence[CandidateRow], taxonomy: Taxonomy, *, unplaced_limit: int = 40) -> str:
    """A Markdown sheet: each position with the counts behind its aliases, then the top unplaced headings.

    Team counts are per alias: the CSV holds counts, not teams, so two aliases' teams cannot be
    added without counting a team twice.
    """
    by_heading: dict[str, list[CandidateRow]] = defaultdict(list)
    for row in rows:
        by_heading[row.normalized_heading].append(row)
    lines = [
        f"# Review: {taxonomy.topic_id} {taxonomy.taxonomy_version}",
        "",
        "Each position with its kind, side and aliases, and the documents and distinct teams behind",
        "each alias in the candidates file. Then the headings most teams use that no position claims.",
        "For each: keep, merge, rename, drop, or add a position.",
        "",
        "## Positions",
        "",
    ]
    for position in taxonomy.positions:
        status = " (retired)" if position.deprecated else ""
        parent = f", under {position.parent}" if position.parent else ""
        lines.append(f"### {position.label}{status}")
        lines.append("")
        lines.append(f"`{position.id}`: {position.kind.value}, {position.side.value}{parent}")
        lines.append("")
        if not position.aliases:
            lines.append("- no alias yet")
        for alias in position.aliases:
            found = by_heading.get(alias, [])
            if not found:
                lines.append(f"- `{alias}`: not in the candidates file")
            for row in sorted(found, key=lambda one: one.answer):
                lines.append(f"- `{alias}`: {row.documents} documents, {row.teams} teams{_sides(row)}")
        lines.append("")
    claimed = {alias for position in taxonomy.positions for alias in position.aliases}
    unplaced = [row for row in rows if row.normalized_heading not in claimed]
    unplaced.sort(key=lambda row: (-row.teams, -row.documents, row.normalized_heading, row.answer))
    lines += [
        f"## Top unplaced headings ({min(unplaced_limit, len(unplaced))} of {len(unplaced)})",
        "",
        "| Heading | Teams | Documents | Level | Suggested id |",
        "|---|---|---|---|---|",
    ]
    for row in unplaced[:unplaced_limit]:
        heading = f"`{row.normalized_heading}`" + (" (answer)" if row.answer else "")
        lines.append(
            f"| {heading} | {row.teams} | {row.documents} | {row.level.value} | {row.suggested_position_id} |"
        )
    return "\n".join(lines) + "\n"


def _sides(row: CandidateRow) -> str:
    parts = [f"{row.aff_teams} aff"] if row.aff_teams else []
    if row.neg_teams:
        parts.append(f"{row.neg_teams} neg")
    if row.answer:
        parts.append("answering it")
    return f" ({', '.join(parts)})" if parts else ""

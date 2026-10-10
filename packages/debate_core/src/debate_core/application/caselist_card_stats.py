"""The card occurrence table, and the statistics `debate-research caselist cards` prints.

Given the parsed cards of one caselist (JSONL in the `ParsedCard` schema `v1-e31-t03` defines) and
the disclosures the E30 importer recorded, :class:`CaselistCardStatsService` answers two questions:
*where does each card appear*, as a table of
:class:`~debate_core.domain.card_occurrence.CardOccurrence` rows, and *which cards are read most*,
as totals and a ranking of clusters by the number of distinct teams that read them.

## How a card becomes an occurrence

1. Every card is fingerprinted (:mod:`debate_core.evidence.fingerprints`).
2. FULL cards are clustered by near-duplicate text (:mod:`debate_core.evidence.near_duplicates`),
   with the thresholds from `settings.fingerprints`. Short bodies are matched as cuts of the one
   card that contains them (`v1-e31-t08`).
3. ABBREVIATED and CITE_ONLY cards are linked to one full card's cluster, which may be one of
   several that card was split across; failing that they are grouped with the other abbreviated
   cards that matched no full card; failing that they are left in a cluster of their own
   (:mod:`debate_core.evidence.abbreviated_links`, `v1-e31-t08`).
4. Each card is joined to every disclosure of the file it came from. One file disclosed by two
   teams is two occurrences; the same disclosure in three cumulative weekly archives is one, whose
   first and last seen snapshots span the three (:attr:`CardOccurrence.occurrence_key`).

A card whose file has no disclosure on record still gets an occurrence, with no school or team, so
it counts as a card but not as a team.

## What the statistics count

* **cards** — distinct card positions: one paragraph range in one file, however many snapshots or
  disclosures it appears under.
* **exact unique** — distinct exact fingerprints.
* **clusters** — distinct cluster ids: the number of *different* cards.
* **duplicate rate** — `1 - clusters / cards`: the share of card positions that repeat a card
  already counted.
* **top clusters** — ranked by distinct teams, then occurrences, then cluster id, so the order is
  total and reproducible.

## Identity, and what is never shown

A cluster's row carries a short cite and a tag, copied exactly from one of its cards, and counts.
Team codes appear only when the caller asks for them (`include_teams`, behind the command's
`--by-team`), and then as school plus team code, never more (`docs/policies/caselist-data-use.md`,
"What a report may show"). Cutter marks are recorded on the occurrence table and never appear in
statistics at all. Nothing in this module logs.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.errors import DomainError
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.domain.card_occurrence import CardOccurrence, ClusterMembership, OccurrenceKey
from debate_core.domain.caselist import Disclosure
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument
from debate_core.evidence.abbreviated_links import (
    AbbreviationAnchor,
    FullCardWords,
    abbreviation_anchor,
    group_unmatched_abbreviations,
    link_abbreviated,
    matching_full_cards,
    short_cite_key,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint, extract_cutter_mark
from debate_core.evidence.near_duplicates import (
    NearDuplicateThresholds,
    cluster_near_duplicates,
    matching_words,
)

__all__ = [
    "CardPlacement",
    "CaselistCardReport",
    "CaselistCardStatsService",
    "CardTotals",
    "ClusterSummary",
    "UnreadableParsedCards",
    "read_parsed_cards",
]

#: Page size for reading a caselist's disclosures.
_DISCLOSURE_PAGE: Final = 500


class UnreadableParsedCards(DomainError):
    """A parsed-card file holds a line that is not a ParsedCard or ParsedDocument.

    Names the file, relative to the directory it was read from, and the line number. Never the
    line's content: it holds evidence text, and possibly a cite with a cutter mark.
    """

    def __init__(self, file: str, line: int, reason: str) -> None:
        self.file = file
        self.line = line
        super().__init__(f"{file} line {line} is not a parsed card: {reason}")


def read_parsed_cards(directory: Path) -> list[ParsedCard]:
    """Every card in the `*.jsonl` files under `directory`, files in sorted path order.

    A line may be one `ParsedCard` or one `ParsedDocument`, whose cards are taken in document
    order. Blank lines are skipped. The parsed card store `caselist parse` writes (`v1-e31-t06`) is
    not read this way: its records leave out disclosure paths, and are read through
    :class:`~debate_core.application.ports.parsed_store.ParsedStore`.
    """
    root = Path(directory)
    cards: list[ParsedCard] = []
    for path in sorted(root.rglob("*.jsonl")):
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict) and "cards" in record:
                    cards.extend(ParsedDocument.model_validate(record).cards)
                else:
                    cards.append(ParsedCard.model_validate(record))
            except json.JSONDecodeError:
                raise UnreadableParsedCards(relative, number, "not JSON") from None
            except ValidationError as error:
                fields = sorted({".".join(str(part) for part in issue["loc"]) for issue in error.errors()})
                raise UnreadableParsedCards(relative, number, f"invalid {', '.join(fields)}") from None
    return cards


# ------------------------------------------------------------------------------------------------
# What the service returns
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CardTotals:
    """The headline counts; see this module's docstring for what each one counts."""

    parsed_cards: int
    cards: int
    occurrences: int
    exact_unique: int
    clusters: int
    teams: int
    linked_abbreviated: int
    unlinked_abbreviated: int

    @property
    def duplicate_rate(self) -> float:
        """The share of card positions that repeat a card already counted."""
        return 1 - self.clusters / self.cards if self.cards else 0.0


@dataclass(frozen=True, slots=True)
class ClusterSummary:
    """One cluster's row: who read it, how often, and how to recognise it."""

    cluster_id: str
    short_cite: str | None
    tag: str
    distinct_teams: int
    occurrences: int
    files: int
    teams: tuple[tuple[str, str], ...] | None
    """(school, team code) pairs, sorted; `None` unless teams were asked for."""


@dataclass(frozen=True, slots=True)
class CaselistCardReport:
    """The occurrence table and the statistics built from it, for one caselist."""

    caselist: str
    snapshot: date | None
    fingerprint_version: str
    totals: CardTotals
    top_clusters: tuple[ClusterSummary, ...]
    occurrences: tuple[CardOccurrence, ...]
    """Every occurrence, ordered by cluster, source and element. Carries team codes and cutter
    marks, so it is never printed. The parsed store (`v1-e31-t06`) does not persist it either: it
    writes one row per card per disclosure, keyed by the disclosure's digest, from :meth:`place`."""


# ------------------------------------------------------------------------------------------------
# The service
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CardPlacement:
    """One card with its fingerprint and the cluster it was placed in.

    What :meth:`CaselistCardStatsService.place` returns, and what the parse pipeline
    (`v1-e31-t06`) writes its occurrence table from.
    """

    card: ParsedCard
    fingerprint: str
    cluster_id: str
    membership: ClusterMembership


class CaselistCardStatsService:
    """Builds the occurrence table for one caselist and summarises it."""

    def __init__(
        self,
        caselists: CaselistRepository,
        thresholds: NearDuplicateThresholds | None = None,
        *,
        ellipsis_markers: Sequence[str] | None = None,
    ) -> None:
        self._caselists = caselists
        self._thresholds = thresholds or NearDuplicateThresholds()
        self._markers = tuple(ellipsis_markers) if ellipsis_markers is not None else None

    async def report(
        self,
        cards: Iterable[ParsedCard],
        *,
        caselist: str,
        snapshot: date | None = None,
        top: int = 10,
        include_teams: bool = False,
    ) -> CaselistCardReport:
        """The occurrence table and statistics for `caselist`, as of `snapshot` when one is given.

        `snapshot` leaves out parsed cards and disclosures from later snapshots, so the report is
        the one that could have been made on that date.
        """
        chosen = sorted(
            (
                card
                for card in cards
                if card.provenance.caselist == caselist
                and (snapshot is None or card.provenance.snapshot <= snapshot)
            ),
            key=_card_order,
        )
        placed = self.place(chosen)
        disclosures = await self._disclosures(caselist, snapshot)
        occurrences = _occurrences(placed, disclosures)
        return CaselistCardReport(
            caselist=caselist,
            snapshot=snapshot,
            fingerprint_version=FINGERPRINT_VERSION,
            totals=_totals(chosen, placed, occurrences),
            top_clusters=_top_clusters(placed, occurrences, top=top, include_teams=include_teams),
            occurrences=occurrences,
        )

    def place(self, cards: Sequence[ParsedCard]) -> list[CardPlacement]:
        """Fingerprint `cards`, cluster the full ones and link the abbreviated ones, in input order.

        Steps 1 to 3 of this module's docstring, without the join to disclosures: one placement per
        card, each in exactly one cluster. Cluster ids do not depend on the order of `cards`, and a
        full card's cluster does not depend on which abbreviated cards are present.
        """
        fingerprints = [card_fingerprint(card).exact_fingerprint for card in cards]
        bodies: dict[str, str] = {}
        for card, fingerprint in zip(cards, fingerprints, strict=True):
            if card.completeness is CardCompleteness.FULL:
                bodies.setdefault(fingerprint, card.evidence_text)
        clusters = cluster_near_duplicates(bodies, self._thresholds)

        copies: Counter[tuple[str, str | None]] = Counter()
        full_by_cite: defaultdict[str | None, dict[str, FullCardWords]] = defaultdict(dict)
        for card, fingerprint in zip(cards, fingerprints, strict=True):
            if card.completeness is CardCompleteness.FULL:
                copies[(fingerprint, short_cite_key(card.short_cite))] += 1
        for card, fingerprint in zip(cards, fingerprints, strict=True):
            if card.completeness is CardCompleteness.FULL:
                key = short_cite_key(card.short_cite)
                if fingerprint not in full_by_cite[key]:
                    full_by_cite[key][fingerprint] = FullCardWords(
                        clusters[fingerprint],
                        key,
                        tuple(matching_words(card.evidence_text)),
                        copies[(fingerprint, key)],
                    )

        # An abbreviated card links to a full card's cluster, or failing that is grouped with the
        # other abbreviated cards that matched no full card, or failing that is its own cluster.
        linked: dict[int, str] = {}
        keys: defaultdict[str, set[AbbreviationAnchor]] = defaultdict(set)
        not_grouped: set[str] = set()
        for position, (card, fingerprint) in enumerate(zip(cards, fingerprints, strict=True)):
            if card.completeness is CardCompleteness.FULL:
                continue
            anchor = abbreviation_anchor(card, self._markers)
            if anchor is None:
                continue
            matches = matching_full_cards(anchor, full_by_cite[anchor.short_cite_key].values())
            cluster = link_abbreviated(anchor, matches)
            if cluster is not None:
                linked[position] = cluster
                continue
            keys[fingerprint].add(anchor)
            if matches:
                not_grouped.add(fingerprint)  # it matched full cards, of two different cards
        groups = group_unmatched_abbreviations(
            {
                fingerprint: next(iter(anchors))
                for fingerprint, anchors in keys.items()
                # One text under two short cites could join two authors' groups: it joins neither.
                if len(anchors) == 1 and fingerprint not in not_grouped
            }
        )

        placed: list[CardPlacement] = []
        for position, (card, fingerprint) in enumerate(zip(cards, fingerprints, strict=True)):
            if card.completeness is CardCompleteness.FULL:
                placed.append(
                    CardPlacement(card, fingerprint, clusters[fingerprint], ClusterMembership.NEAR_DUPLICATE)
                )
            elif position in linked:
                placed.append(
                    CardPlacement(card, fingerprint, linked[position], ClusterMembership.ABBREVIATED_LINK)
                )
            elif fingerprint in groups:
                # Every unlinked card with this text goes with it, so identical text never splits.
                placed.append(
                    CardPlacement(card, fingerprint, groups[fingerprint], ClusterMembership.ABBREVIATED_LINK)
                )
            else:
                placed.append(CardPlacement(card, fingerprint, fingerprint, ClusterMembership.UNLINKED))
        return placed

    async def _disclosures(self, caselist: str, snapshot: date | None) -> dict[str, list[Disclosure]]:
        by_source: defaultdict[str, list[Disclosure]] = defaultdict(list)
        cursor: str | None = None
        while True:
            page = await self._caselists.list_disclosures(
                caselist=caselist, limit=_DISCLOSURE_PAGE, cursor=cursor
            )
            for disclosure in page.items:
                if snapshot is None or disclosure.snapshot <= snapshot:
                    by_source[disclosure.source_sha256].append(disclosure)
            if page.next_cursor is None:
                return dict(by_source)
            cursor = page.next_cursor


def _card_order(card: ParsedCard) -> tuple[str, int, date, str]:
    provenance = card.provenance
    return (
        provenance.source_sha256,
        provenance.first_element_index,
        provenance.snapshot,
        provenance.source_path,
    )


def _occurrences(
    placed: Sequence[CardPlacement], disclosures: dict[str, list[Disclosure]]
) -> tuple[CardOccurrence, ...]:
    """One occurrence per occurrence key; later sightings only widen its snapshot range."""
    table: dict[OccurrenceKey, CardOccurrence] = {}
    for item in placed:
        provenance = item.card.provenance
        common = {
            "cluster_id": item.cluster_id,
            "exact_fingerprint": item.fingerprint,
            "fingerprint_version": FINGERPRINT_VERSION,
            "completeness": item.card.completeness,
            "membership": item.membership,
            "source_sha256": provenance.source_sha256,
            "element_index": provenance.first_element_index,
            "cutter_mark": extract_cutter_mark(item.card.full_cite),
            "tag": item.card.tag,
            "short_cite": item.card.short_cite,
        }
        sightings = [
            CardOccurrence.model_validate(
                {
                    **common,
                    "caselist": disclosure.caselist,
                    "school": disclosure.school,
                    "team_code": disclosure.team_code,
                    "side": disclosure.side,
                    "tournament": disclosure.tournament,
                    "round_label": disclosure.round_label,
                    "first_seen_snapshot": disclosure.snapshot,
                    "last_seen_snapshot": disclosure.snapshot,
                }
            )
            for disclosure in disclosures.get(provenance.source_sha256, ())
        ] or [
            CardOccurrence.model_validate(
                {
                    **common,
                    "caselist": provenance.caselist,
                    "camp": provenance.camp,
                    "first_seen_snapshot": provenance.snapshot,
                    "last_seen_snapshot": provenance.snapshot,
                }
            )
        ]
        for sighting in sightings:
            key = sighting.occurrence_key
            known = table.get(key)
            if known is None:
                table[key] = sighting
                continue
            table[key] = known.model_copy(
                update={
                    "first_seen_snapshot": min(known.first_seen_snapshot, sighting.first_seen_snapshot),
                    "last_seen_snapshot": max(known.last_seen_snapshot, sighting.last_seen_snapshot),
                }
            )
    return tuple(
        sorted(table.values(), key=lambda occurrence: (occurrence.cluster_id, occurrence.occurrence_key))
    )


def _totals(
    chosen: Sequence[ParsedCard], placed: Sequence[CardPlacement], occurrences: Sequence[CardOccurrence]
) -> CardTotals:
    abbreviated = [item for item in placed if item.card.completeness is not CardCompleteness.FULL]
    positions = {
        (item.card.provenance.source_sha256, item.card.provenance.first_element_index) for item in placed
    }
    return CardTotals(
        parsed_cards=len(chosen),
        cards=len(positions),
        occurrences=len(occurrences),
        exact_unique=len({item.fingerprint for item in placed}),
        clusters=len({item.cluster_id for item in placed}),
        teams=len({occurrence.team for occurrence in occurrences if occurrence.team is not None}),
        linked_abbreviated=len(
            {_position(item) for item in abbreviated if item.membership is ClusterMembership.ABBREVIATED_LINK}
        ),
        unlinked_abbreviated=len(
            {_position(item) for item in abbreviated if item.membership is ClusterMembership.UNLINKED}
        ),
    )


def _position(item: CardPlacement) -> tuple[str, int]:
    return (item.card.provenance.source_sha256, item.card.provenance.first_element_index)


def _top_clusters(
    placed: Sequence[CardPlacement], occurrences: Sequence[CardOccurrence], *, top: int, include_teams: bool
) -> tuple[ClusterSummary, ...]:
    members: defaultdict[str, list[CardOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        members[occurrence.cluster_id].append(occurrence)
    # A full card's short cite and tag describe a cluster better than an abbreviated one's.
    labels: defaultdict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    for item in placed:
        if item.card.completeness is CardCompleteness.FULL or item.cluster_id == item.fingerprint:
            labels[item.cluster_id][(item.card.short_cite or "", item.card.tag)] += 1

    summaries: list[ClusterSummary] = []
    for cluster_id, rows in members.items():
        teams = sorted({(team[1], team[2]) for row in rows if (team := row.team) is not None})
        short_cite, tag = _most_common(labels[cluster_id])
        summaries.append(
            ClusterSummary(
                cluster_id=cluster_id,
                short_cite=short_cite or None,
                tag=tag,
                distinct_teams=len({row.team for row in rows if row.team is not None}),
                occurrences=len(rows),
                files=len({row.source_sha256 for row in rows}),
                teams=tuple(teams) if include_teams else None,
            )
        )
    summaries.sort(key=lambda summary: (-summary.distinct_teams, -summary.occurrences, summary.cluster_id))
    return tuple(summaries[:top])


def _most_common(counts: Counter[tuple[str, str]]) -> tuple[str, str]:
    """The most frequent (short cite, tag), ties broken by the smallest, so the choice is stable."""
    if not counts:
        return ("", "")
    return min(counts, key=lambda label: (-counts[label], label))

"""LandscapeReportService: one caselist's argument landscape through one snapshot (`v1-e32-t03`).

A pure aggregation: it reads nothing, writes nothing and calls no model. Its inputs are the
classifications `v1-e32-t02` wrote for the caselist's cards, the E30 disclosures that say who read
each file on which side in which round, the E31 fingerprints that say which cards are one card, the
topic's taxonomy and the coach's overrides, and, from `v1-e32-t09` when it lands, an aff per
affirmative round. Its output is a :class:`~debate_core.domain.landscape_report.LandscapeReport`
and that report's four files, rendered by :mod:`debate_core.arguments.landscape.render` and passed
through `v1-e34-t03`'s staleness hook.

## What is counted

* **A round** is one disclosed round: a team, a side, a tournament and a round as the filename
  gave them (the round's normalized form when it has one). A team that disclosed one file twice
  for one round, or whose file was carried from one weekly window into the next, read one round. A
  file whose name gave no tournament or no round is a round of its own, so two such files are never
  merged into one round.
* **A round reads a position** when one of its files holds a card `v1-e32-t02` placed under that
  position, READS role, at or above the review threshold, and the round is on the position's side or
  on no readable side. A card that ANSWERS a position (under an `AT:` heading) never counts as
  reading it, and neither does a placement in a round on the other side: a `Midterms DA` block in an
  affirmative file is the 2AC answering the DA, whatever its heading lacks. Such rounds are counted
  apart, as `other_side_position_rounds`. An item below the threshold or nothing placed is
  Unclassified; one the coach ruled names no position is neither counted nor Unclassified.
* **An affirmative round's aff** comes from `v1-e32-t09`'s assignment when there is one: the
  assigned aff is the round's aff, and an aff a card in that round was placed under does not count
  for it. Otherwise it comes from the round's placed cards (:data:`PLACED_CARD_METHOD`), and a round
  with neither is an affirmative round with no identified aff. Advantages and negative positions are
  counted as placed.
* **A team** is a school and team code, compared without case, never shown. A disclosure whose path
  named no school or team code reads a round but is no team.
* **Sides.** PF's pro and con count as aff and neg. A round on no readable side counts in a
  position's rounds and in neither split.
* **share_of_teams** is the teams that read a position on its own side over the teams that
  disclosed on that side in the report's range; for a position either side reads, over every team.
* **First seen and new.** A round is first seen in the earliest snapshot that lists it; a position in
  the earliest first-seen of the rounds reading it. A weekly archive is a window of about a week's
  changes (`v1-e30-t17`), so the earliest listing is when the round was first disclosed. A position
  is new when that is after the previous snapshot; in a caselist's first snapshot nothing is new.
* **The range** is every disclosure dated on or before `through`. The report's snapshot is the newest
  of those, the previous snapshot the one before it.

## Most-read cards

Per position, the cards counted for it are grouped by E31 cluster, so near-duplicate copies are one
card, and each cluster's teams are the distinct teams of the rounds holding one of its cards. Clusters
rank by teams, then by cluster id. A row shows one card of the cluster: the tag and short cite most
of the cluster's cards under the position carry (ties to the first in text order), from the first
such card by source digest and paragraph, with its file's content-addressed `raw/` key and the
snapshot that file was first disclosed in.

## Impact cards (`v1-e32-t10`)

Per DA and advantage, the cards counted for it that a team labelled as an impact
(:mod:`debate_core.arguments.landscape.impacts`), card by card: a cluster's teams are the teams of
the rounds holding one of its *labelled* copies, and the row shows one of those copies. Clusters rank
as top cards do, by teams then cluster id, up to N per position. Per kind, a document is a file
holding a card counted for a position of that kind, and the report counts those holding an impact
card among them, so it can say how many carry no labelled impact.

## Advantages by affirmative (`v1-e32-t15`)

Under each aff `v1-e32-t09` assigned rounds to, and each mechanism under it, the advantages those
rounds read, by the rules of :mod:`debate_core.application.landscape_advantages`: the report's own
reads, t09's assignments as the only source of a round's aff, and a mechanism's rounds counted once
under its aff. report.md shows them; no other file does.

## Scenarios and link chains (`v1-e32-t14`)

A card's sub-headings are its headings below the one that placed it, found by the matcher's own rule
(:meth:`~debate_core.arguments.landscape.matcher.PositionMatcher.placing_index`), and its roles and
scenario are read from them and its tag (:mod:`debate_core.arguments.landscape.link_chains`). Only the
cards counted for a position fill its roles or name its scenarios, so an answer or a card on the other
side never does. Per DA and advantage:

* **A scenario name** shows when two or more teams' counted cards under the position carry it, and is
  withheld, and counted, when it holds a word of a caselist school, team code or tournament. A row's
  scenario is the shown name the most teams of its labelled copies carry, ties by name.
* **A row's internal link** is, per labelled copy, the nearest card above it in its file under the same
  position heading that is counted for the position and labelled an internal link; the row shows the
  tag the most teams' copies have, ties by tag. With none, and only then, the row carries the tag of
  the card directly above a copy in its block when that card is not an impact card: the card above it
  in the file, for report.md, never called an internal link.
* **Its link chain** is its most-read cluster per role, ranked as impact cards are, by the teams of the
  copies labelled with the role; the impact role is the impact section's first row.
* **Per kind**, the documents with no scenario heading and no role label, the rows with a scenario, an
  internal link or the card above, the names withheld, and the positions with no card for each role.

## What never leaves this module

School, team code, tournament and round are read to tell rounds and teams apart, and are not in the
report: a round is a count, a team is a count. :func:`round_id` names a round by a digest of them.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Final

from debate_core.application.caselist.publish_plan import source_key
from debate_core.application.errors import DomainError
from debate_core.application.landscape_advantages import advantages_by_aff
from debate_core.application.landscape_bundle_files import CIRCUIT_WIDE_FILES, SCHOOL_VIEW_FILES
from debate_core.application.landscape_counts import (
    AFF_SIDE,
    LANDSCAPE_SIDE,
    NEG_SIDE,
    CountedReads,
    CountedRound,
    round_id,
    team_identity,
)
from debate_core.application.landscape_schools import school_view
from debate_core.application.landscape_staleness import (
    LandscapeStaleness,
    with_stale_banner,
    with_staleness_metadata,
)
from debate_core.application.landscape_trends import landscape_trends
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.arguments.landscape.analytic_texts import (
    AnalyticTextInputs,
    TextGroup,
    commonest_text,
    names_a_school,
    top_texts,
)
from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.impacts import is_impact_card
from debate_core.arguments.landscape.link_chains import (
    SubHeading,
    card_roles,
    card_scenario,
    caselist_words,
    is_withheld,
)
from debate_core.arguments.landscape.matcher import PositionMatcher
from debate_core.arguments.landscape.render import (
    header_metadata,
    render_impact_cards_csv,
    render_markdown,
    render_positions_csv,
    render_schools_csv,
    render_schools_markdown,
    render_top_cards_csv,
    render_trends_csv,
)
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD, needs_review
from debate_core.arguments.landscape.seeding import SeedSource
from debate_core.arguments.landscape.source_headings import (
    CaselistNames,
    heading_path,
    normalize_source_heading,
)
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape import Position, PositionKind, PositionSide, Taxonomy
from debate_core.domain.landscape_classification import (
    DETERMINISTIC_PROMPT_VERSION,
    ItemKind,
    OverrideRules,
    PositionClassification,
    PositionRole,
)
from debate_core.domain.landscape_report import (
    CHAIN_ROLES,
    DEFAULT_ADVANTAGES_PER_AFF,
    DEFAULT_IMPACT_CARDS,
    DEFAULT_TOP_CARDS,
    IMPACT_KINDS,
    PLACED_CARD_METHOD,
    AffAssignment,
    AffIdentification,
    ChainCard,
    ChainCoverage,
    ChainRole,
    ImpactCard,
    ImpactCoverage,
    LandscapeCard,
    LandscapeReport,
    PositionStats,
    ReportHeader,
    RoleGap,
    TopCard,
    UnclassifiedSummary,
)
from debate_core.domain.landscape_schools import SchoolView
from debate_core.domain.landscape_texts import (
    DEFAULT_TEXTS_PER_POSITION,
    POSITION_KIND_OF,
    AnalyticTextKind,
    CpPlanks,
    LandscapeTexts,
    OverviewCount,
    PlankGroup,
    PositionTexts,
    TextCoverage,
    TextPlacement,
)
from debate_core.domain.landscape_trends import (
    DEFAULT_TREND_MINIMUM_TEAMS,
    DEFAULT_TREND_THRESHOLD_POINTS,
    LandscapeTrends,
)

__all__ = [
    "CIRCUIT_WIDE_FILES",
    "SCHOOL_VIEW_FILES",
    "LandscapeReportBundle",
    "LandscapeReportInputs",
    "LandscapeReportService",
    "ReportCannotShip",
    "landscape_cards",
    "overrides_digest",
    "round_id",
]


_SIDE_ORDER: Final = {PositionSide.AFF: 0, PositionSide.NEG: 1, PositionSide.BOTH: 2}
_KIND_ORDER: Final = {kind: index for index, kind in enumerate(PositionKind)}
_AFF: Final = AFF_SIDE
_NEG: Final = NEG_SIDE
_OPPOSITE: Final = {PositionSide.AFF: _NEG, PositionSide.NEG: _AFF}
"""The round side on which a placement under a position of this side answers it."""


class ReportCannotShip(DomainError):
    """The report cannot say how old its data is, or its inputs contradict each other."""


def overrides_digest(rules: OverrideRules) -> str:
    """The digest of every decision in the coach's overrides file, or `none` when it holds none.

    The same digest t02's cache keys an item by, taken over every heading the file decides, so two
    reports with the same digest counted under the same decisions.
    """
    return rules.digest_for(one.heading for one in rules.overrides)


def landscape_cards(
    sources: Iterable[SeedSource],
    occurrences: Iterable[OccurrenceRecord],
    caselist_names: Mapping[str, Sequence[str]] | None = None,
) -> tuple[LandscapeCard, ...]:
    """Each card of `sources` with the cluster E31's occurrence table placed it in, and its headings.

    The occurrence table has a row per card per disclosure; a card's fingerprint and cluster are the
    same in each. A card with no row, or no first paragraph, has no cluster to rank and is left out.
    The headings are the ones the position matcher reads (`v1-e32-t02`): the card's path without an
    open tag, each normalized with the disclosing teams' names and `caselist_names`' schools taken
    out, the empty ones left out, each with whether it answers (`v1-e32-t14`).
    """
    names = CaselistNames(caselist_names or {})
    clusters: dict[tuple[str, int], tuple[str, str]] = {}
    for row in occurrences:
        clusters.setdefault(
            (row.source_sha256, row.first_element_index), (row.exact_fingerprint, row.cluster_id)
        )
    cards: list[LandscapeCard] = []
    for source in sources:
        own = [name for team in source.teams for name in team.names if name.strip()]
        tags = {card.tag for card in source.cards if card.tag is not None}
        normalized: dict[str, NormalizedHeading] = {}
        for card in source.cards:
            if card.first_element_index is None:
                continue
            found = clusters.get((source.sha256, card.first_element_index))
            if found is None:
                continue
            headings: list[NormalizedHeading] = []
            for raw in heading_path(card.tag, card.section_path, tags):
                heading = normalized.get(raw)
                if heading is None:
                    heading = normalized[raw] = normalize_source_heading(raw, own, names)
                if heading.text:
                    headings.append(heading)
            cards.append(
                LandscapeCard(
                    source_sha256=source.sha256,
                    element_index=card.first_element_index,
                    exact_fingerprint=found[0],
                    cluster_id=found[1],
                    tag=card.tag,
                    short_cite=card.short_cite,
                    headings=tuple(one.text for one in headings),
                    heading_answers=tuple(one.answer for one in headings)
                    if any(one.answer for one in headings)
                    else (),
                )
            )
    return tuple(cards)


@dataclass(frozen=True, slots=True)
class LandscapeReportInputs:
    """Everything one report is built from."""

    caselist: str
    through: date
    """Disclosures dated after this are out of range."""
    taxonomy: Taxonomy
    """The topic's merged taxonomy, as the classifications were placed under."""
    overrides: OverrideRules
    parser_version: str
    classifications: Sequence[PositionClassification] = field(repr=False)
    disclosures: Sequence[Disclosure] = field(repr=False)
    cards: Sequence[LandscapeCard] = field(repr=False)
    aff_assignments: Sequence[AffAssignment] = field(default=(), repr=False)
    """`v1-e32-t09`'s per-round affs; empty until it lands."""
    snapshot_topics: Mapping[date, str] | None = field(default=None, repr=False)
    """Each weekly snapshot of the caselist through `through` the store holds, with the topic
    `topics.yaml` puts it on, so the trends stop at a topic change (`v1-e32-t04`); None takes every
    disclosure's snapshot to be on the taxonomy's topic."""
    topic_range: tuple[date, date] | None = None
    """The first and last snapshot date `topics.yaml` gives the topic in this caselist, so the report can
    say whether its windows span a full topic cycle; None when not known."""
    analytic_texts: AnalyticTextInputs | None = field(default=None, repr=False)
    """`v1-e32-t11`'s readings of the caselist's CP texts, alternatives, roles of the ballot and overviews,
    with the texts to quote read again; None when the run read none, and the report has no such sections."""


@dataclass(frozen=True, slots=True)
class LandscapeReportBundle:
    """A report, its trends and school view, and their files, the staleness banner and flag in them."""

    report: LandscapeReport
    files: dict[str, str] = field(repr=False)
    """:data:`CIRCUIT_WIDE_FILES` and :data:`SCHOOL_VIEW_FILES`, by name."""
    trends: LandscapeTrends = field(repr=False)
    schools: SchoolView = field(repr=False)


@dataclass(slots=True)
class _Round:
    side: str
    team: tuple[str, str] | None
    first_seen: date


@dataclass(frozen=True, slots=True)
class _Assigned:
    position_id: str
    method: str


@dataclass(frozen=True, slots=True)
class _Range:
    """The disclosures in range, read into rounds."""

    rounds: dict[str, _Round]
    by_source: dict[str, set[str]]
    """Source digest to the rounds disclosing it."""
    source_first_seen: dict[str, date]
    snapshots: list[date]


class LandscapeReportService:
    """Builds a caselist's landscape report from its classifications, disclosures and fingerprints."""

    def __init__(
        self,
        *,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
        top_cards: int = DEFAULT_TOP_CARDS,
        impact_cards: int = DEFAULT_IMPACT_CARDS,
        trend_threshold_points: Decimal = DEFAULT_TREND_THRESHOLD_POINTS,
        trend_minimum_teams: int = DEFAULT_TREND_MINIMUM_TEAMS,
        texts_per_position: int = DEFAULT_TEXTS_PER_POSITION,
        advantages_per_aff: int = DEFAULT_ADVANTAGES_PER_AFF,
    ) -> None:
        if not 0.0 <= review_threshold <= 1.0:
            raise ValueError(f"the review threshold is between 0 and 1; got {review_threshold}")
        if top_cards < 1 or impact_cards < 1:
            raise ValueError(
                f"a report lists at least one card per position; got {top_cards} and {impact_cards} (impacts)"
            )
        if advantages_per_aff < 1:
            raise ValueError(f"a report lists at least one advantage per aff; got {advantages_per_aff}")
        self._threshold = review_threshold
        self._top = top_cards
        self._impact = impact_cards
        self._trend_threshold = trend_threshold_points
        self._trend_minimum = trend_minimum_teams
        self._texts = texts_per_position
        self._advantages = advantages_per_aff

    def bundle(self, inputs: LandscapeReportInputs, staleness: LandscapeStaleness) -> LandscapeReportBundle:
        """The report, its trends and its school view, with the hook's banner and `stale` flag in them."""
        report, counted = self.count(inputs, staleness)
        snapshot = report.header.snapshot
        trends = landscape_trends(
            caselist=inputs.caselist,
            taxonomy=inputs.taxonomy,
            counted=counted,
            snapshot=snapshot,
            snapshot_topics=inputs.snapshot_topics,
            topic_range=inputs.topic_range,
            threshold_points=self._trend_threshold,
            minimum_teams=self._trend_minimum,
        )
        schools = school_view(
            caselist=inputs.caselist, snapshot=snapshot, disclosures=inputs.disclosures, counted=counted
        )
        metadata = with_staleness_metadata(header_metadata(report), staleness)
        return LandscapeReportBundle(
            report=report,
            files={
                "report.md": with_stale_banner(render_markdown(report, trends), staleness),
                "positions.csv": render_positions_csv(report, metadata),
                "top_cards.csv": render_top_cards_csv(report, metadata),
                "impact_cards.csv": render_impact_cards_csv(report, metadata),
                "trends.csv": render_trends_csv(trends, metadata),
                "schools.csv": render_schools_csv(schools, metadata),
                "schools.md": with_stale_banner(render_schools_markdown(schools, report), staleness),
            },
            trends=trends,
            schools=schools,
        )

    def build(self, inputs: LandscapeReportInputs, staleness: LandscapeStaleness) -> LandscapeReport:
        """The report alone. :meth:`bundle` is what writes it out."""
        return self.count(inputs, staleness)[0]

    def count(
        self, inputs: LandscapeReportInputs, staleness: LandscapeStaleness
    ) -> tuple[LandscapeReport, CountedReads]:
        """The report, and the rounds and reads it was counted from, for the views beside it."""
        if staleness.newest_snapshot is None or staleness.age_days is None:
            raise ReportCannotShip(
                f"the staleness check found no snapshot of {inputs.caselist}, so the report cannot say "
                "how old its data is"
            )
        if staleness.caselist != inputs.caselist:
            raise ReportCannotShip(f"the staleness check is of {staleness.caselist}, not {inputs.caselist}")
        taxonomy = inputs.taxonomy
        in_range = _read_range(inputs)
        rounds = in_range.rounds
        assigned = _assignments(inputs.aff_assignments, rounds, taxonomy)

        reads: defaultdict[str, set[str]] = defaultdict(set)
        """Position id to the rounds reading it."""
        card_reads: defaultdict[str, dict[tuple[str, int], set[str]]] = defaultdict(dict)
        """Position id to each card counted for it, with the rounds it was counted in."""
        other_side: defaultdict[str, set[str]] = defaultdict(set)
        """Position id to the rounds on the other side that placed a card under it."""
        cards = unplaced = below = decided = placed = 0
        prompt_versions: set[str] = set()
        for item in inputs.classifications:
            if item.item_kind is not ItemKind.CARD or item.first_element_index is None:
                continue
            in_rounds = in_range.by_source.get(item.source_sha256)
            if not in_rounds:
                continue
            if item.taxonomy_version != taxonomy.taxonomy_version:
                raise ReportCannotShip(
                    f"{item.item_id} was placed under taxonomy {item.taxonomy_version}, not "
                    f"{taxonomy.taxonomy_version}"
                )
            cards += 1
            prompt_versions.add(item.prompt_version)
            if needs_review(item, self._threshold):
                unplaced += item.method is None
                below += item.method is not None
                continue
            if item.position_id is None:
                decided += 1
                continue
            placed += 1
            if item.role is not PositionRole.READS:
                continue
            position = _counted_position(taxonomy, item.position_id)
            opposite = _OPPOSITE.get(position.side)
            other_side[position.id] |= {one for one in in_rounds if rounds[one].side == opposite}
            counted = {
                one
                for one in in_rounds
                if rounds[one].side != opposite
                and (position.kind is not PositionKind.AFF or one not in assigned)
            }
            if not counted:
                continue
            reads[position.id] |= counted
            card_reads[position.id].setdefault((item.source_sha256, item.first_element_index), set()).update(
                counted
            )
        for one, assignment in assigned.items():
            reads[assignment.position_id].add(one)

        teams = {side: _teams(rounds, side) for side in (_AFF, _NEG, None)}
        previous = in_range.snapshots[-2] if len(in_range.snapshots) > 1 else None
        positions = sorted(
            (
                _stats(taxonomy.position(position_id), read, rounds, teams, previous)
                for position_id, read in reads.items()
            ),
            key=_report_order,
        )
        cards_by_key = {(card.source_sha256, card.element_index): card for card in inputs.cards}
        top_cards = [
            card
            for stats in positions
            for card in _ranked(
                TopCard,
                stats.position_id,
                card_reads[stats.position_id],
                cards_by_key,
                in_range,
                inputs.caselist,
                self._top,
            )
        ]
        labelled = {
            position_id: {key: read for key, read in reads.items() if _is_impact(cards_by_key.get(key))}
            for position_id, reads in card_reads.items()
        }
        impact_cards = [
            card
            for stats in positions
            if stats.kind in IMPACT_KINDS
            for card in _ranked(
                ImpactCard,
                stats.position_id,
                labelled[stats.position_id],
                cards_by_key,
                in_range,
                inputs.caselist,
                self._impact,
            )
        ]

        chains = _LinkChains(inputs, in_range, card_reads, labelled, cards_by_key)
        impact_cards = [chains.with_lead_in(card) for card in impact_cards]
        chain_cards = [
            card for stats in positions if stats.kind in IMPACT_KINDS for card in chains.chain(stats)
        ]

        aff_positions = {one.id for one in taxonomy.positions if one.kind is PositionKind.AFF}
        neg_positions = {
            one.id for one in taxonomy.positions if one.side in (PositionSide.NEG, PositionSide.BOTH)
        }
        aff_rounds = sorted(one for one, stated in rounds.items() if stated.side == _AFF)
        neg_rounds = sorted(one for one, stated in rounds.items() if stated.side == _NEG)
        identified: Counter[str] = Counter()
        placed_card_rounds: set[str] = set()
        for one in aff_rounds:
            if one in assigned:
                identified[assigned[one].method] += 1
            elif any(one in reads[position_id] for position_id in aff_positions if position_id in reads):
                identified[PLACED_CARD_METHOD] += 1
                placed_card_rounds.add(one)
        read_rounds = {one for read in reads.values() for one in read}
        neg_placed = {one for position_id in neg_positions for one in reads.get(position_id, ())}
        counted = CountedReads(
            rounds={
                one: CountedRound(side=stated.side, team=stated.team, first_seen=stated.first_seen)
                for one, stated in rounds.items()
            },
            reads={position_id: frozenset(read) for position_id, read in reads.items()},
        )
        report = LandscapeReport(
            header=ReportHeader(
                caselist=inputs.caselist,
                snapshot=in_range.snapshots[-1],
                previous_snapshot=previous,
                topic_id=taxonomy.topic_id,
                taxonomy_version=taxonomy.taxonomy_version,
                overrides_digest=overrides_digest(inputs.overrides),
                parser_version=inputs.parser_version,
                prompt_version=", ".join(sorted(prompt_versions)) or DETERMINISTIC_PROMPT_VERSION,
                review_threshold=self._threshold,
                top_cards_per_position=self._top,
                impact_cards_per_position=self._impact,
                cards=cards,
                cards_placed=placed,
                rounds=len(rounds),
                rounds_with_a_read=len(read_rounds),
                aff_rounds=len(aff_rounds),
                neg_rounds=len(neg_rounds),
                teams=len(teams[None]),
                aff_teams=len(teams[_AFF]),
                neg_teams=len(teams[_NEG]),
                stale=staleness.stale,
                newest_snapshot=staleness.newest_snapshot,
                snapshot_age_days=staleness.age_days,
                archives_awaiting_download=staleness.archives_awaiting_download,
            ),
            positions=tuple(positions),
            top_cards=tuple(top_cards),
            impact_cards=tuple(impact_cards),
            impact_coverage=tuple(
                _impact_coverage(kind, taxonomy, card_reads, labelled) for kind in IMPACT_KINDS
            ),
            chain_cards=tuple(chain_cards),
            chain_coverage=tuple(
                chains.coverage(kind, positions, impact_cards, chain_cards) for kind in IMPACT_KINDS
            ),
            unclassified=UnclassifiedSummary(
                cards=cards,
                unplaced_cards=unplaced,
                below_threshold_cards=below,
                decided_no_position_cards=decided,
                other_side_position_rounds=sum(len(found) for found in other_side.values()),
                aff_rounds=len(aff_rounds),
                aff_rounds_unidentified=len(aff_rounds) - sum(identified.values()),
                neg_rounds=len(neg_rounds),
                neg_rounds_unplaced=sum(one not in neg_placed for one in neg_rounds),
            ),
            aff_identification=tuple(
                AffIdentification(method=method, rounds=count) for method, count in sorted(identified.items())
            ),
            texts=None
            if inputs.analytic_texts is None
            else _landscape_texts(inputs.analytic_texts, in_range, taxonomy, self._texts),
            advantages_by_aff=advantages_by_aff(
                taxonomy=taxonomy,
                counted=counted,
                assigned={one: found.position_id for one, found in assigned.items()},
                placed_card_rounds=placed_card_rounds,
                limit=self._advantages,
            ),
        )
        return report, counted


def _landscape_texts(
    inputs: AnalyticTextInputs, in_range: _Range, taxonomy: Taxonomy, limit: int
) -> LandscapeTexts:
    """`v1-e32-t11`'s sections: each CP's and K's top texts by teams, and each position's overview teams.

    Only the files disclosed in range are read. A quoted kind's text counts for the teams of the rounds
    disclosing its file when it is placed under a position of its kind, READS, and the round is not on the
    position's other side, as a card's read does; an overview counts on either side, READS. Everything else
    found is counted where it went: elsewhere, under headings that place nothing, or under no heading.
    """
    caselist = CaselistNames(inputs.caselist_names)
    labels: Counter[AnalyticTextKind] = Counter()
    documents: defaultdict[AnalyticTextKind, set[str]] = defaultdict(set)
    where: defaultdict[AnalyticTextKind, Counter[str]] = defaultdict(Counter)
    unread: Counter[AnalyticTextKind] = Counter()
    groups: defaultdict[tuple[AnalyticTextKind, str], dict[str, _TextCopies]] = defaultdict(dict)
    planks: defaultdict[str, dict[str, _TextCopies]] = defaultdict(dict)
    solves_other_words = 0
    overview_teams: defaultdict[str, dict[str, set[tuple[str, str]]]] = defaultdict(
        lambda: {_AFF: set(), _NEG: set()}
    )
    for sha in sorted(inputs.readings):
        in_rounds = in_range.by_source.get(sha)
        if not in_rounds:
            continue
        for reading in inputs.readings[sha]:
            kind = reading.kind
            labels[kind] += 1
            documents[kind].add(sha)
            if reading.placement is not TextPlacement.PLACED or reading.position_id is None:
                where[kind][reading.placement.value] += 1
                continue
            position = _counted_position(taxonomy, reading.position_id)
            if reading.role is not PositionRole.READS:
                where[kind]["elsewhere"] += 1
                continue
            if kind is AnalyticTextKind.OVERVIEW:
                where[kind]["counted"] += 1
                for one in in_rounds:
                    stated = in_range.rounds[one]
                    if stated.team is not None and stated.side in (_AFF, _NEG):
                        overview_teams[position.id][stated.side].add(stated.team)
                continue
            opposite = _OPPOSITE.get(position.side)
            counted = [one for one in in_rounds if in_range.rounds[one].side != opposite]
            if position.kind is not POSITION_KIND_OF[kind] or not counted or reading.digest is None:
                where[kind]["elsewhere"] += 1
                continue
            where[kind]["counted"] += 1
            if kind is AnalyticTextKind.CP_PLANK:
                copies = planks[position.id].setdefault(reading.digest, _TextCopies())
                copies.solves |= set(reading.solves)
                solves_other_words += reading.solves_other_words
            else:
                copies = groups[(kind, position.id)].setdefault(reading.digest, _TextCopies())
            copies.teams |= {team for one in counted if (team := in_range.rounds[one].team) is not None}
            text = inputs.texts.get((sha, reading.element_index))
            if text is None:
                unread[kind] += 1
            else:
                copies.texts.append((sha, reading.element_index, text))
    withheld: Counter[AnalyticTextKind] = Counter()
    positions: list[tuple[int, PositionTexts]] = []
    for (kind, position_id), by_digest in groups.items():
        quoted, more, held = top_texts(
            position_id,
            kind,
            {
                digest: TextGroup(teams=frozenset(copies.teams), texts=tuple(copies.texts))
                for digest, copies in by_digest.items()
            },
            limit=limit,
            caselist=caselist,
        )
        withheld[kind] += held
        if quoted:
            teams = {team for copies in by_digest.values() for team in copies.teams}
            positions.append(
                (
                    len(teams),
                    PositionTexts(
                        position_id=position_id,
                        label=taxonomy.position(position_id).label,
                        kind=kind,
                        texts=quoted,
                        more=more,
                    ),
                )
            )
    by_cp = [
        _cp_planks(position_id, by_digest, taxonomy, caselist, limit)
        for position_id, by_digest in planks.items()
    ]
    withheld[AnalyticTextKind.CP_PLANK] = sum(one.withheld for one in by_cp)
    kinds = list(AnalyticTextKind)
    refused = sum(count for sha, count in inputs.refused_by_guard.items() if in_range.by_source.get(sha))
    planks_refused = sum(
        count for sha, count in inputs.planks_refused_by_guard.items() if in_range.by_source.get(sha)
    )
    plank_labels = sum(count for sha, count in inputs.plank_labels.items() if in_range.by_source.get(sha))
    overviews = [
        OverviewCount(
            position_id=position_id,
            label=taxonomy.position(position_id).label,
            position_kind=taxonomy.position(position_id).kind,
            aff_teams=len(sides[_AFF]),
            neg_teams=len(sides[_NEG]),
            teams=len(sides[_AFF] | sides[_NEG]),
        )
        for position_id, sides in overview_teams.items()
    ]
    return LandscapeTexts(
        texts_per_position=limit,
        positions=tuple(
            one
            for _, one in sorted(
                positions, key=lambda item: (kinds.index(item[1].kind), -item[0], item[1].position_id)
            )
        ),
        coverage=tuple(
            TextCoverage(
                kind=kind,
                labels=labels[kind],
                documents=len(documents[kind]),
                counted=where[kind]["counted"],
                elsewhere=where[kind]["elsewhere"],
                headings_place_nothing=where[kind][TextPlacement.HEADINGS_PLACE_NOTHING.value],
                no_heading=where[kind][TextPlacement.NO_HEADING.value],
                withheld_texts=withheld[kind],
                unread=unread[kind],
                refused_by_guard=(
                    refused
                    if kind is AnalyticTextKind.CP_TEXT
                    else planks_refused
                    if kind is AnalyticTextKind.CP_PLANK
                    else 0
                ),
                plank_labels=plank_labels if kind is AnalyticTextKind.CP_PLANK else 0,
                solves_other_words=solves_other_words if kind is AnalyticTextKind.CP_PLANK else 0,
            )
            for kind in kinds
        ),
        overviews=tuple(sorted(overviews, key=lambda one: (-one.teams, one.position_id))),
        planks=tuple(sorted(by_cp, key=lambda one: (-one.teams, one.position_id))),
    )


def _cp_planks(
    position_id: str,
    by_digest: dict[str, _TextCopies],
    taxonomy: Taxonomy,
    caselist: CaselistNames,
    limit: int,
) -> CpPlanks:
    """`v1-e32-t16`'s planks of one CP: grouped by the advantage each solves, the top `limit` per group.

    A plank naming two advantages is in both groups and once in the CP's totals; one naming none is in the
    last group, "solves: not named". A plank naming a school of the caselist is withheld, from every group,
    and counted once.
    """
    withheld = {
        digest
        for digest, copies in by_digest.items()
        if copies.texts and names_a_school(commonest_text(copies.texts), caselist)
    }
    members: defaultdict[str | None, dict[str, TextGroup]] = defaultdict(dict)
    for digest, copies in by_digest.items():
        if digest in withheld:
            continue
        for solves in sorted(copies.solves) or [None]:
            members[solves][digest] = TextGroup(teams=frozenset(copies.teams), texts=tuple(copies.texts))
    groups: list[tuple[int, str, PlankGroup]] = []
    for solves, group in members.items():
        quoted, more, _ = top_texts(
            position_id, AnalyticTextKind.CP_PLANK, group, limit=limit, caselist=caselist
        )
        if not quoted:
            continue
        teams = len({team for one in group.values() for team in one.teams})
        label = None if solves is None else taxonomy.position(solves).label
        groups.append((teams, solves or "", PlankGroup(solves=solves, label=label, planks=quoted, more=more)))
    return CpPlanks(
        position_id=position_id,
        label=taxonomy.position(position_id).label,
        planks=len(by_digest),
        teams=len({team for copies in by_digest.values() for team in copies.teams}),
        withheld=len(withheld),
        groups=tuple(
            one for _, _, one in sorted(groups, key=lambda item: (item[2].solves is None, -item[0], item[1]))
        ),
    )


@dataclass(slots=True)
class _TextCopies:
    """One position's copies of one text: the teams reading it, and the copies read again."""

    teams: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])
    texts: list[tuple[str, int, str]] = field(default_factory=list[tuple[str, int, str]])
    solves: set[str] = field(default_factory=set[str])
    """A plank's advantages, as any copy of it names them (`v1-e32-t16`)."""


def _ranked[RowT: TopCard](
    row: type[RowT],
    position_id: str,
    reads: dict[tuple[str, int], set[str]],
    cards: dict[tuple[str, int], LandscapeCard],
    in_range: _Range,
    caselist: str,
    limit: int,
) -> list[RowT]:
    """Up to `limit` clusters of the cards in `reads`, by distinct teams then cluster id, as `row`s."""
    members: defaultdict[str, list[LandscapeCard]] = defaultdict(list)
    teams: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
    for key, read in reads.items():
        card = cards.get(key)
        if card is None:
            continue
        members[card.cluster_id].append(card)
        teams[card.cluster_id] |= {team for one in read if (team := in_range.rounds[one].team) is not None}
    ranked = sorted(members, key=lambda cluster: (-len(teams[cluster]), cluster))[:limit]
    rows: list[RowT] = []
    for rank, cluster in enumerate(ranked, start=1):
        shown = _shown_card(members[cluster])
        first_seen = in_range.source_first_seen[shown.source_sha256]
        rows.append(
            row(
                position_id=position_id,
                rank=rank,
                fingerprint=cluster,
                teams_reading=len(teams[cluster]),
                tag=shown.tag,
                short_cite=shown.short_cite,
                source_object_key=source_key(caselist, first_seen.isoformat(), shown.source_sha256),
                element_index=shown.element_index,
                source_snapshot=first_seen,
            )
        )
    return rows


class _LinkChains:
    """`v1-e32-t14`'s reading of the counted DA and advantage cards: roles, scenarios and lead-ins."""

    def __init__(
        self,
        inputs: LandscapeReportInputs,
        in_range: _Range,
        card_reads: Mapping[str, dict[tuple[str, int], set[str]]],
        labelled: Mapping[str, dict[tuple[str, int], set[str]]],
        cards: dict[tuple[str, int], LandscapeCard],
    ) -> None:
        self._taxonomy = inputs.taxonomy
        self._caselist = inputs.caselist
        self._range = in_range
        self._reads = card_reads
        self._labelled = labelled
        self._cards = cards
        self._matcher = PositionMatcher(inputs.taxonomy, inputs.overrides)
        self._no_position = frozenset(
            one.heading for one in inputs.overrides.overrides if one.position_id is None
        )
        self._words = caselist_words(inputs.disclosures)
        files: defaultdict[str, list[LandscapeCard]] = defaultdict(list)
        for card in inputs.cards:
            files[card.source_sha256].append(card)
        self._files = {
            sha: sorted(found, key=lambda card: card.element_index) for sha, found in files.items()
        }
        self._place = {
            (card.source_sha256, card.element_index): number
            for found in self._files.values()
            for number, card in enumerate(found)
        }
        self._placing: dict[tuple[str, int], int | None] = {}
        self._shown: dict[str, dict[str, set[tuple[str, str]]]] = {}
        self._withheld: dict[str, int] = {}

    # Per card -----------------------------------------------------------------------------------

    def _placing_index(self, card: LandscapeCard) -> int | None:
        key = (card.source_sha256, card.element_index)
        if key not in self._placing:
            self._placing[key] = self._matcher.placing_index(card.headings)
        return self._placing[key]

    def _sub_headings(self, card: LandscapeCard) -> tuple[SubHeading, ...]:
        index = self._placing_index(card)
        if index is None:
            return ()
        return tuple(
            SubHeading(text, card.answers(number))
            for number, text in enumerate(card.headings)
            if number > index
        )

    def _section(self, card: LandscapeCard) -> tuple[tuple[str, bool], ...] | None:
        """The headings down to the placing one: the position heading a card sits under in its file."""
        index = self._placing_index(card)
        if index is None:
            return None
        return tuple((card.headings[number], card.answers(number)) for number in range(index + 1))

    def _roles(self, card: LandscapeCard, kind: PositionKind) -> frozenset[ChainRole]:
        return card_roles(self._sub_headings(card), card.headings, card.tag, kind)

    def _teams(self, rounds: Iterable[str]) -> set[tuple[str, str]]:
        return {team for one in rounds if (team := self._range.rounds[one].team) is not None}

    # Per position -------------------------------------------------------------------------------

    def _names(self, position_id: str) -> dict[str, set[tuple[str, str]]]:
        """The scenario names a position shows, with their teams: two or more teams, none withheld."""
        if position_id not in self._shown:
            kind = self._taxonomy.position(position_id).kind
            teams: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
            for key, rounds in self._reads.get(position_id, {}).items():
                card = self._cards.get(key)
                if card is None:
                    continue
                name = card_scenario(self._sub_headings(card), kind, self._no_position).name
                if name is not None:
                    teams[name] |= self._teams(rounds)
            used = {name: found for name, found in teams.items() if len(found) >= 2}
            withheld = {name for name in used if is_withheld(name, self._words)}
            self._withheld[position_id] = len(withheld)
            self._shown[position_id] = {name: found for name, found in used.items() if name not in withheld}
        return self._shown[position_id]

    def chain(self, stats: PositionStats) -> list[ChainCard]:
        """The position's most-read card for each role a team labelled, in role order."""
        found: list[ChainCard] = []
        counted = self._reads.get(stats.position_id, {})
        for role in CHAIN_ROLES[stats.kind]:
            if role is ChainRole.IMPACT:
                reads = self._labelled.get(stats.position_id, {})
            else:
                reads = {
                    key: rounds
                    for key, rounds in counted.items()
                    if (card := self._cards.get(key)) is not None and role in self._roles(card, stats.kind)
                }
            for top in _ranked(
                TopCard, stats.position_id, reads, self._cards, self._range, self._caselist, 1
            ):
                found.append(ChainCard(**top.model_dump(), role=role))
        return found

    # Per impact row -----------------------------------------------------------------------------

    def with_lead_in(self, row: ImpactCard) -> ImpactCard:
        """The row with its scenario and its labelled internal link, or else the card above it."""
        kind = self._taxonomy.position(row.position_id).kind
        names = self._names(row.position_id)
        scenario: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
        link: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
        above: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
        for key, rounds in self._labelled.get(row.position_id, {}).items():
            card = self._cards.get(key)
            if card is None or card.cluster_id != row.fingerprint:
                continue
            teams = self._teams(rounds)
            name = card_scenario(self._sub_headings(card), kind, self._no_position).name
            if name is not None and name in names:
                scenario[name] |= teams
            tag = self._internal_link_tag(card, row.position_id, kind)
            if tag is not None:
                link[tag] |= teams
            tag = self._card_above_tag(card)
            if tag is not None:
                above[tag] |= teams
        internal_link = _most_teams(link)
        return row.model_copy(
            update={
                "scenario": _most_teams(scenario),
                "internal_link_tag": internal_link,
                "card_above_tag": None if internal_link is not None else _most_teams(above),
            }
        )

    def _internal_link_tag(self, card: LandscapeCard, position_id: str, kind: PositionKind) -> str | None:
        """The tag of the nearest card above `card` under its position heading, counted and labelled IL."""
        section = self._section(card)
        if section is None:
            return None
        counted = self._reads.get(position_id, {})
        file = self._files[card.source_sha256]
        for prior in reversed(file[: self._place[(card.source_sha256, card.element_index)]]):
            if self._section(prior) != section:
                return None
            if (prior.source_sha256, prior.element_index) not in counted:
                continue
            if ChainRole.INTERNAL_LINK in self._roles(prior, kind):
                return prior.tag
        return None

    def _card_above_tag(self, card: LandscapeCard) -> str | None:
        """The tag of the card directly above `card` in its block, unless that card is an impact card."""
        number = self._place[(card.source_sha256, card.element_index)]
        if number == 0:
            return None
        prior = self._files[card.source_sha256][number - 1]
        same_block = prior.headings == card.headings and all(
            prior.answers(index) == card.answers(index) for index in range(len(card.headings))
        )
        if not same_block or _is_impact(prior):
            return None
        return prior.tag

    # Per kind -----------------------------------------------------------------------------------

    def coverage(
        self,
        kind: PositionKind,
        positions: Sequence[PositionStats],
        impact_cards: Sequence[ImpactCard],
        chain_cards: Sequence[ChainCard],
    ) -> ChainCoverage:
        """What the kind's scenarios and chains could not see, and what its rows show."""
        listed = [stats.position_id for stats in positions if stats.kind is kind]
        documents: set[str] = set()
        structured: set[str] = set()
        for position_id, reads in self._reads.items():
            if self._taxonomy.position(position_id).kind is not kind:
                continue
            for key in reads:
                documents.add(key[0])
                card = self._cards.get(key)
                if card is None or key[0] in structured:
                    continue
                if card_scenario(self._sub_headings(card), kind, self._no_position).heading or self._roles(
                    card, kind
                ):
                    structured.add(key[0])
        rows = [row for row in impact_cards if row.position_id in listed]
        for position_id in listed:
            self._names(position_id)
        filled = {(card.position_id, card.role) for card in chain_cards}
        return ChainCoverage(
            kind=kind,
            documents=len(documents),
            unstructured_documents=len(documents - structured),
            positions=len(listed),
            impact_rows=len(rows),
            rows_with_scenario=sum(row.scenario is not None for row in rows),
            rows_with_internal_link=sum(row.internal_link_tag is not None for row in rows),
            rows_with_card_above=sum(row.card_above_tag is not None for row in rows),
            withheld_names=sum(self._withheld[position_id] for position_id in listed),
            roles_without_card=tuple(
                RoleGap(role=role, positions=sum((one, role) not in filled for one in listed))
                for role in CHAIN_ROLES[kind]
            ),
        )


def _most_teams(found: Mapping[str, set[tuple[str, str]]]) -> str | None:
    """The key the most teams carry, ties to the first in text order; None when there is none."""
    if not found:
        return None
    return min(found, key=lambda one: (-len(found[one]), one))


def _is_impact(card: LandscapeCard | None) -> bool:
    """A card with a cluster that a heading over it or its tag labels as an impact."""
    return card is not None and is_impact_card(card.headings, card.tag)


def _impact_coverage(
    kind: PositionKind,
    taxonomy: Taxonomy,
    card_reads: Mapping[str, dict[tuple[str, int], set[str]]],
    labelled: Mapping[str, dict[tuple[str, int], set[str]]],
) -> ImpactCoverage:
    """The documents holding a card counted for a position of `kind`, and those holding an impact card."""
    of_kind = [position_id for position_id in card_reads if taxonomy.position(position_id).kind is kind]
    return ImpactCoverage(
        kind=kind,
        documents=len({sha for position_id in of_kind for sha, _ in card_reads[position_id]}),
        labelled_documents=len({sha for position_id in of_kind for sha, _ in labelled[position_id]}),
    )


def _read_range(inputs: LandscapeReportInputs) -> _Range:
    rounds: dict[str, _Round] = {}
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    first_seen: dict[str, date] = {}
    for disclosure in inputs.disclosures:
        if disclosure.caselist != inputs.caselist:
            raise ReportCannotShip(f"a disclosure of {disclosure.caselist} is not one of {inputs.caselist}")
        if disclosure.snapshot > inputs.through:
            continue
        one = round_id(disclosure)
        found = rounds.get(one)
        if found is None:
            found = rounds[one] = _Round(
                side=LANDSCAPE_SIDE.get(disclosure.side, ""),
                team=team_identity(disclosure),
                first_seen=disclosure.snapshot,
            )
        found.first_seen = min(found.first_seen, disclosure.snapshot)
        by_source[disclosure.source_sha256].add(one)
        sha = disclosure.source_sha256
        first_seen[sha] = min(first_seen.get(sha, disclosure.snapshot), disclosure.snapshot)
    if not rounds:
        raise ReportCannotShip(f"no disclosure of {inputs.caselist} is dated on or before {inputs.through}")
    snapshots = sorted(
        {disclosure.snapshot for disclosure in inputs.disclosures if disclosure.snapshot <= inputs.through}
    )
    return _Range(rounds=rounds, by_source=dict(by_source), source_first_seen=first_seen, snapshots=snapshots)


def _assignments(
    assignments: Sequence[AffAssignment], rounds: dict[str, _Round], taxonomy: Taxonomy
) -> dict[str, _Assigned]:
    """Round id to the aff `v1-e32-t09` assigned it, for the rounds in range."""
    assigned: dict[str, _Assigned] = {}
    seen: set[str] = set()
    for one in assignments:
        if one.round_id in seen:
            raise ReportCannotShip(f"round {one.round_id} is assigned an aff twice")
        seen.add(one.round_id)
        position = _counted_position(taxonomy, one.position_id)
        if position.kind is not PositionKind.AFF:
            raise ReportCannotShip(f"round {one.round_id} is assigned {one.position_id}, which is not an aff")
        stated = rounds.get(one.round_id)
        if stated is None:
            continue
        if stated.side != _AFF:
            raise ReportCannotShip(f"round {one.round_id} is assigned an aff but is not an affirmative round")
        assigned[one.round_id] = _Assigned(position.id, one.method)
    return assigned


def _counted_position(taxonomy: Taxonomy, position_id: str) -> Position:
    """The active position `position_id` counts under; refused when the taxonomy has none."""
    try:
        position = taxonomy.resolve(position_id)
    except KeyError:
        raise ReportCannotShip(
            f"{position_id} is not a position of {taxonomy.topic_id} {taxonomy.taxonomy_version}"
        ) from None
    if position.deprecated:
        raise ReportCannotShip(f"{position_id} is retired with no position to count under")
    return position


def _stats(
    position: Position,
    read: set[str],
    rounds: dict[str, _Round],
    teams: dict[str | None, set[tuple[str, str]]],
    previous: date | None,
) -> PositionStats:
    own_side = None if position.side is PositionSide.BOTH else position.side.value
    first_seen = min(rounds[one].first_seen for one in read)
    return PositionStats(
        position_id=position.id,
        label=position.label,
        kind=position.kind,
        side=position.side,
        rounds=len(read),
        teams=len({team for one in read if (team := rounds[one].team) is not None}),
        aff_rounds=sum(rounds[one].side == _AFF for one in read),
        neg_rounds=sum(rounds[one].side == _NEG for one in read),
        first_seen_snapshot=first_seen,
        is_new=previous is not None and first_seen > previous,
        side_teams_reading=len(
            {
                team
                for one in read
                if (team := rounds[one].team) is not None
                and (own_side is None or rounds[one].side == own_side)
            }
        ),
        side_teams_disclosing=len(teams[own_side]),
    )


def _teams(rounds: dict[str, _Round], side: str | None) -> set[tuple[str, str]]:
    """The distinct teams disclosing on `side`, or on any side for None."""
    return {
        stated.team
        for stated in rounds.values()
        if stated.team is not None and (side is None or stated.side == side)
    }


def _report_order(stats: PositionStats) -> tuple[int, int, int, int, str]:
    return (_SIDE_ORDER[stats.side], _KIND_ORDER[stats.kind], -stats.teams, -stats.rounds, stats.position_id)


def _shown_card(members: list[LandscapeCard]) -> LandscapeCard:
    """The card a top-card row shows: the commonest tag and short cite, then the first such card."""
    pairs = Counter((card.tag or "", card.short_cite or "") for card in members)
    commonest = min(pairs, key=lambda pair: (-pairs[pair], pair))
    return min(
        (card for card in members if (card.tag or "", card.short_cite or "") == commonest),
        key=lambda card: (card.source_sha256, card.element_index),
    )

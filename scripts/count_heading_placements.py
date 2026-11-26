#!/usr/bin/env python3
"""Count the headings that place cards, by how they place them (`v1-e32-t64`), counts only.

The review queue lists only headings nothing placed. `v1-e32-t64` adds a listing of the headings that
did place something, so the coach can correct a confident but wrong placement. This script measures that
listing before it is built. It places every section and card of a caselist with the real matcher
(:class:`~debate_core.arguments.landscape.matcher.PositionMatcher`, the taxonomy and the coach's overrides,
no cache, no model), as `scripts/count_block_inheritance.py` did for `v1-e32-t65`.

## What it counts

**Cards by method**, as the matcher places them: `ALIAS` and `OVERRIDE` (the heading directly over the
card), `INHERITED` (a heading further up, split by whether an alias or the coach's override placed it),
`TAG_KEYWORD` under a placing heading (a child its tag names, 0.9), `TAG_KEYWORD` alone (0.5, under the
review threshold, split by whether any heading over the card is one the coach could still decide), the
coach's no-position decision, and unplaced. Each with its cards, documents, teams and distinct placing
headings.

**Listing rows.** A row is a normalized heading with its answer flag, as the review queue keys one:

* `alias` and `override`: the heading that places an item (the nearest alias or override with a position).
  Its items are those it places, directly or further down.
* `none`: a heading the coach ruled names no position. Its items are those under it that no nearer heading
  places, the items a changed decision on it would move. Two such headings over one item both count it.

A row fewer than `minimum_teams` teams use is left out and counted, as in the queue. For each kind: rows,
rows listed and left out, and the cards, documents and teams of each.

**What a `none` decision on a placed heading would do** to the cards it places: a heading above still places
them (under the same position or another), their tag alone places them (under the threshold, so to the
queue), or nothing does (to the queue, or decided when every heading over them is ruled none).

**Finding the wrong ones:** how the listed cards concentrate in the largest rows, how many rows hold a card
whose tag names a position outside the row's own line (itself, its ancestors and descendants), and how many
positions the rows fall under.

Counts as JSON on stdout: no heading, tag, cite, path, school, team, row or item id.

    uv run python scripts/count_heading_placements.py --snapshot 2026-11-03 --caselist hspolicy26
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import median
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import DomainError
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.arguments.landscape.matcher import (
    TAG_KEYWORD_ALONE_CONFIDENCE,
    MatchItem,
    PositionMatcher,
    read_items,
)
from debate_core.arguments.landscape.review_queue import (
    DEFAULT_MINIMUM_REVIEW_TEAMS,
    DEFAULT_REVIEW_THRESHOLD,
    QueuedItem,
    build_review_queue,
    needs_review,
)
from debate_core.arguments.landscape.seeding import SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ClassificationResult,
    ItemKind,
    OverrideRules,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR: Final = REPO_ROOT / "config" / "landscape"
DEFAULT_DATA_DIR: Final = Path.home() / ".debate-research" / "dev"
DEFAULT_SNAPSHOT: Final = date(2026, 11, 3)
DEFAULT_CASELISTS: Final = ("hspolicy26",)
TOP_ROWS: Final = (25, 50, 100, 200, 500)
TEAM_BUCKETS: Final = ((2, 2), (3, 5), (6, 20), (21, None))

ALIAS: Final = "alias"
OVERRIDE: Final = "override"
NONE: Final = "none"
ROW_KINDS: Final = (ALIAS, OVERRIDE, NONE)


class Refused(Exception):
    """A run this script will not make, with the reason to print."""


# ------------------------------------------------------------------------------------------------
# Tallies
# ------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class Tally:
    """Documents, teams and cards under one key, counted as the review queue counts a row."""

    documents: set[str] = field(default_factory=lambda: set[str]())
    teams: set[str] = field(default_factory=lambda: set[str]())
    aff: set[str] = field(default_factory=lambda: set[str]())
    neg: set[str] = field(default_factory=lambda: set[str]())
    cards: int = 0
    positions: Counter[str] = field(default_factory=lambda: Counter[str]())
    cards_direct: int = 0
    cards_inherited: int = 0
    cards_refined_by_tag: int = 0
    cards_tag_names_another: int = 0

    def add(self, source: str, teams: Sequence[SeedTeam], card: bool) -> None:
        self.documents.add(source)
        self.cards += card
        for team in teams:
            if not team.identity:
                continue
            self.teams.add(team.identity)
            if team.side in (Side.AFF, Side.PRO):
                self.aff.add(team.identity)
            elif team.side in (Side.NEG, Side.CON):
                self.neg.add(team.identity)

    def totals(self) -> dict[str, int]:
        return {"cards": self.cards, "documents": len(self.documents), "teams": len(self.teams)}


@dataclass(slots=True)
class Counts:
    """Everything one caselist's run adds up, before it is written as JSON."""

    cards_by_method: dict[str, Tally] = field(default_factory=lambda: defaultdict(Tally))
    headings_by_method: dict[str, set[tuple[str, bool]]] = field(
        default_factory=lambda: defaultdict(set[tuple[str, bool]])
    )
    rows: dict[str, dict[tuple[str, bool], Tally]] = field(
        default_factory=lambda: {kind: defaultdict(Tally) for kind in ROW_KINDS}
    )
    if_ruled_none: Counter[str] = field(default_factory=lambda: Counter[str]())
    queued: list[QueuedItem] = field(default_factory=lambda: list[QueuedItem]())
    sections: int = 0
    cards: int = 0


def lineage(taxonomy: Taxonomy) -> Mapping[str, frozenset[str]]:
    """Each active position with its ancestors and descendants: a tag naming one of them agrees with it."""
    parents: dict[str, str | None] = {}
    for position in taxonomy.active_positions:
        parents[position.id] = None if position.parent is None else taxonomy.resolve(position.parent).id
    up: dict[str, set[str]] = {}
    for position_id in parents:
        chain = {position_id}
        parent = parents[position_id]
        while parent is not None and parent not in chain:
            chain.add(parent)
            parent = parents.get(parent)
        up[position_id] = chain
    related: dict[str, set[str]] = {position_id: set(chain) for position_id, chain in up.items()}
    for position_id, chain in up.items():
        for ancestor in chain:
            related.setdefault(ancestor, {ancestor}).add(position_id)
    return {position_id: frozenset(found) for position_id, found in related.items()}


def card_method(result: ClassificationResult, placing: int | None, *, by_override: bool) -> str:
    """The key a card is counted under in `cards_by_method`."""
    method = result.method
    if method is None:
        return "UNPLACED"
    if result.position_id is None:
        return "OVERRIDE_NO_POSITION"
    if method is ClassificationMethod.INHERITED:
        return "INHERITED_FROM_OVERRIDE" if by_override else "INHERITED_FROM_ALIAS"
    if method is ClassificationMethod.TAG_KEYWORD:
        return "TAG_KEYWORD_ALONE" if placing is None else "TAG_KEYWORD_UNDER_HEADING"
    return method.value


def if_ruled_none(matcher: PositionMatcher, item: MatchItem, placing: int, position_id: str) -> str:
    """Where `item` would go if the heading placing it were ruled to name no position."""
    above = matcher.place(dataclasses.replace(item, headings=item.headings[:placing]))
    if above.position_id is None:
        return "nothing_places_it"
    if above.method is ClassificationMethod.TAG_KEYWORD and above.confidence == TAG_KEYWORD_ALONE_CONFIDENCE:
        return "tag_keyword_alone"
    return (
        "heading_above_same_position" if above.position_id == position_id else "heading_above_other_position"
    )


def count_reading(
    reading: SeedReading,
    taxonomy: Taxonomy,
    overrides: OverrideRules,
    *,
    threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> Counts:
    """Place every item of `reading` and add it to the tallies."""
    matcher = PositionMatcher(taxonomy, overrides)
    names = CaselistNames(reading.caselist_names)
    decided = overrides.rules_by_heading()
    ruled_none = {heading for heading, rule in decided.items() if rule.position_id is None}
    by_override = {heading for heading, rule in decided.items() if rule.position_id is not None}
    related = lineage(taxonomy)
    counts = Counts()
    for source in reading.sources:
        for item in read_items(source, names):
            card = item.kind is ItemKind.CARD
            counts.cards += card
            counts.sections += not card
            result = matcher.place(item)
            texts = [heading.text for heading in item.headings]
            placing = matcher.placing_index(texts)
            placer = None if placing is None else item.headings[placing]
            if needs_review(result, threshold):
                counts.queued.append(
                    QueuedItem(
                        source_sha256=source.sha256,
                        kind=item.kind,
                        teams=source.teams,
                        headings=matcher.undecided_headings(item),
                        tag_candidates=matcher.tag_candidates(item),
                    )
                )
            if card:
                method = card_method(
                    result, placing, by_override=placer is not None and placer.text in by_override
                )
                if method == "TAG_KEYWORD_ALONE":
                    if not item.headings:
                        method += "_UNDER_NO_HEADING"
                    elif matcher.undecided_headings(item):
                        method += "_UNDER_AN_UNDECIDED_HEADING"
                    else:
                        method += "_UNDER_HEADINGS_RULED_NONE"
                counts.cards_by_method[method].add(source.sha256, source.teams, True)
                if placer is not None:
                    counts.headings_by_method[method].add((placer.text, placer.answer))
            if placer is not None and placing is not None and result.position_id is not None:
                kind = OVERRIDE if placer.text in by_override else ALIAS
                tally = counts.rows[kind][(placer.text, placer.answer)]
                tally.add(source.sha256, source.teams, card)
                if card:
                    tally.positions[result.position_id] += 1
                    direct = placing == len(item.headings) - 1
                    tally.cards_direct += direct
                    tally.cards_inherited += not direct
                    tally.cards_refined_by_tag += result.method is ClassificationMethod.TAG_KEYWORD
                    named = set(matcher.tag_candidates(item))
                    own = related.get(result.position_id, frozenset({result.position_id}))
                    tally.cards_tag_names_another += bool(named) and not (named & own)
                    counts.if_ruled_none[if_ruled_none(matcher, item, placing, result.position_id)] += 1
            nearest = -1 if placing is None else placing
            for index in {
                index
                for index, heading in enumerate(item.headings)
                if heading.text in ruled_none and index > nearest
            }:
                heading = item.headings[index]
                counts.rows[NONE][(heading.text, heading.answer)].add(source.sha256, source.teams, card)
    return counts


# ------------------------------------------------------------------------------------------------
# Writing the counts
# ------------------------------------------------------------------------------------------------


def _union(tallies: Iterable[Tally]) -> dict[str, int]:
    documents: set[str] = set()
    teams: set[str] = set()
    cards = 0
    for tally in tallies:
        documents |= tally.documents
        teams |= tally.teams
        cards += tally.cards
    return {"rows": 0, "cards": cards, "documents": len(documents), "teams": len(teams)}


def _rows_json(rows: Mapping[tuple[str, bool], Tally], minimum_teams: int) -> dict[str, object]:
    listed = [tally for tally in rows.values() if len(tally.teams) >= minimum_teams]
    left_out = [tally for tally in rows.values() if len(tally.teams) < minimum_teams]
    written: dict[str, object] = {
        "rows": len(rows),
        "distinct_headings": len({heading for heading, _ in rows}),
        "answer_rows": sum(1 for _, answer in rows if answer),
    }
    for name, part in (("listed", listed), ("left_out_below_minimum_teams", left_out)):
        summary = _union(part)
        summary["rows"] = len(part)
        summary["cards_direct"] = sum(tally.cards_direct for tally in part)
        summary["cards_inherited"] = sum(tally.cards_inherited for tally in part)
        summary["cards_refined_by_tag"] = sum(tally.cards_refined_by_tag for tally in part)
        summary["cards_tag_names_another_position"] = sum(tally.cards_tag_names_another for tally in part)
        summary["rows_with_a_card_whose_tag_names_another_position"] = sum(
            1 for tally in part if tally.cards_tag_names_another
        )
        written[name] = summary
    return written


def _finding(rows: Mapping[str, Mapping[tuple[str, bool], Tally]], minimum_teams: int) -> dict[str, object]:
    """How the listed placed rows (alias and override) spread, for choosing an order or a filter."""
    listed = [
        tally
        for kind in (ALIAS, OVERRIDE)
        for tally in rows[kind].values()
        if len(tally.teams) >= minimum_teams
    ]
    total = sum(tally.cards for tally in listed)
    by_cards = sorted((tally.cards for tally in listed), reverse=True)
    by_position: Counter[str] = Counter()
    for tally in listed:
        if tally.positions:
            by_position[tally.positions.most_common(1)[0][0]] += 1
    buckets: dict[str, int] = {}
    for low, high in TEAM_BUCKETS:
        label = f"{low}-{high}" if high is not None else f"{low}+"
        buckets[label] = sum(
            1 for tally in listed if len(tally.teams) >= low and (high is None or len(tally.teams) <= high)
        )
    mixed = sum(1 for tally in listed if len(tally.positions) > 1)
    return {
        "listed_rows": len(listed),
        "listed_cards": total,
        "cards_in_the_largest_rows": {str(top): sum(by_cards[:top]) for top in TOP_ROWS},
        "rows_by_teams": buckets,
        "rows_with_cards_under_more_than_one_position": mixed,
        "positions_with_a_row": len(by_position),
        "rows_per_position": {
            "max": max(by_position.values(), default=0),
            "median": median(by_position.values()) if by_position else 0,
        },
    }


def counts_json(counts: Counts, *, minimum_teams: int = DEFAULT_MINIMUM_REVIEW_TEAMS) -> dict[str, object]:
    queue = build_review_queue(counts.queued, minimum_teams=minimum_teams).counts
    return {
        "sections": counts.sections,
        "cards": counts.cards,
        "cards_by_method": {
            method: {**tally.totals(), "placing_headings": len(counts.headings_by_method.get(method, ()))}
            for method, tally in sorted(counts.cards_by_method.items())
        },
        "rows": {kind: _rows_json(counts.rows[kind], minimum_teams) for kind in ROW_KINDS},
        "placed_cards_if_their_heading_were_ruled_none": dict(sorted(counts.if_ruled_none.items())),
        "finding_the_wrong_ones": _finding(counts.rows, minimum_teams),
        "review_queue_for_comparison": {
            "rows": queue.rows,
            "headings": queue.headings,
            "left_out_below_minimum_teams": queue.left_out_below_minimum_teams,
            "queued_cards": queue.queued_cards,
            "queued_items_under_no_heading_to_decide": queue.without_heading,
        },
        "minimum_teams": minimum_teams,
    }


# ------------------------------------------------------------------------------------------------
# Wiring
# ------------------------------------------------------------------------------------------------


async def _reading(
    arguments: argparse.Namespace, caselist: str
) -> tuple[SeedReading, Taxonomy, OverrideRules]:
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
    topic = resolved.topic.id
    return reading, repository.taxonomy(topic), repository.overrides(topic)


async def _count(arguments: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    caselists: dict[str, object] = {}
    for caselist in arguments.caselist:
        begun = time.perf_counter()
        try:
            reading, taxonomy, overrides = await _reading(arguments, caselist)
        except Refused as refused:
            caselists[caselist] = {"refused": str(refused)}
            continue
        counts = count_reading(reading, taxonomy, overrides, threshold=arguments.threshold)
        caselists[caselist] = {
            "version": reading.version,
            "topic_id": reading.topic_id,
            "taxonomy_version": taxonomy.taxonomy_version,
            "overrides": len(overrides.overrides),
            "overrides_ruled_none": sum(1 for rule in overrides.overrides if rule.position_id is None),
            "sources": len(reading.sources),
            **counts_json(counts, minimum_teams=arguments.minimum_teams),
            "seconds": round(time.perf_counter() - begun, 1),
        }
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
    parser.add_argument("--caselist", action="append", help="Repeat for each. Default: hspolicy26.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_REVIEW_THRESHOLD)
    parser.add_argument("--minimum-teams", type=int, default=DEFAULT_MINIMUM_REVIEW_TEAMS)
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

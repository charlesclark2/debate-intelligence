#!/usr/bin/env python3
"""Classify a caselist's cards into its topic's positions, and apply the coach's review decisions.

`v1-e32-t02-position-classification`, deterministic stage: no model is called. Until
`debate-research landscape report` (`v1-e32-t05`) runs classification as part of a report, this is
how the operator classifies a snapshot and turns the coach's review into overrides. Two commands:

* **`classify`** reads the caselist's parsed card store (`<data dir>/parsed/`) and manifests as
  they stood at a snapshot (the newest weekly one unless `--snapshot` names one), resolves the topic
  from `config/landscape/topics.yaml`, and classifies every section and card with
  :class:`~debate_core.application.position_classification.PositionClassificationService`. Results
  are cached under `<data dir>/landscape/classifications/`, and the review queue's CSV is written to
  `<data dir>/landscape/review/<caselist>/<topic id>-review-queue.csv`. It prints counts only: cards
  by method, the unplaced share, the queue's size, the cache's hits and the runtime. With
  `--show-unplaced N` it also prints the queue's first N headings with their counts. The queue is
  ordered by the local proxy model when the caselist has one that stands (`v1-e32-t26`), with its
  suggestions, and kept in today's order otherwise; a line says which and why. It exits 1 when it read
  no source, so an empty store never looks like a run.
  Beside the queue it writes the placements listing (`v1-e32-t64`),
  `<data dir>/landscape/review/<caselist>/<topic id>-placements.csv`: every heading that places cards,
  or that the coach ruled names no position, so a confident but wrong placement can be corrected.
* **`apply-decisions`** reads a review queue CSV or a placements listing whose `decision` column the
  coach filled (a position id, or `none` for a heading that names no position), and refuses a decision
  naming no position of the taxonomy before anything is written. It then reads `--caselist` as it
  stood at the snapshot and prints, for each decision that changes the rules, how many cards it moves
  where (`v1-e32-t64`): under its position, under a heading above, to their tag keyword or the queue,
  or decided. Without `--execute` that summary is all it does; with it, it prints the summary and
  writes the topic's overrides to `config/landscape/overrides/<topic id>.yaml`. Commit that file after
  `tests/config` passes.

The queue and the decisions file hold headings from real disclosures, so neither may be inside the
repository; the script refuses a data directory or a decisions path there. Read-only for every store
but the cache, the queue and the placements listing.

    uv run python scripts/classify_landscape_positions.py classify --caselist hspolicy26
    uv run python scripts/classify_landscape_positions.py apply-decisions --topic policy-2026-27-nhi \\
        --caselist hspolicy26 --decisions ~/Documents/debate/landscape-review/policy-2026-27-nhi-decisions.csv
    uv run python scripts/classify_landscape_positions.py apply-decisions --topic policy-2026-27-nhi \\
        --caselist hspolicy26 \\
        --decisions ~/Documents/debate/landscape-review/policy-2026-27-nhi-decisions.csv \\
        --execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import DomainError
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.landscape_staleness import LandscapeStalenessCheck
from debate_core.application.position_classification import (
    DECIDED_NO_POSITION,
    UNPLACED,
    ClassificationRun,
    PositionClassificationService,
)
from debate_core.application.review_queue_order import ReviewQueueOrdering
from debate_core.arguments.landscape.matcher import HeadingRule, PositionMatcher
from debate_core.arguments.landscape.placements import DecisionEffect, Destination, placement_changes
from debate_core.arguments.landscape.review_queue import (
    DEFAULT_MINIMUM_REVIEW_TEAMS,
    DEFAULT_REVIEW_THRESHOLD,
    apply_decisions,
    read_decisions_csv,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape import TopicResolution
from debate_core.integrations.landscape.classification_store import (
    LocalClassificationStore,
    LocalQueueOrderModelStore,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    OVERRIDE_DIRECTORY,
    YamlTaxonomyRepository,
    render_override_file,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"
DEFAULT_DATA_DIR = Path.home() / ".debate-research" / "dev"
METHODS = ("ALIAS", "OVERRIDE", "INHERITED", "TAG_KEYWORD", DECIDED_NO_POSITION, UNPLACED)


class Refused(Exception):
    """A run this script will not make, with the reason to print."""


def _outside_the_repository(path: Path, what: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise Refused(f"{what} must be outside the repository ({REPO_ROOT}): it holds real headings")
    return resolved


def _share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def _print_run(run: ClassificationRun, seconds: float, show_unplaced: int) -> None:
    counts = run.counts
    print(
        f"Classified {run.caselist} on {run.topic_id} {run.taxonomy_version} "
        f"(prompt version {run.prompt_version})."
    )
    print(f"Sources {counts.sources}; sections {counts.sections}; cards {counts.cards}.")
    for method in METHODS:
        found = counts.cards_by_method.get(method, 0)
        print(f"  cards {method}: {found} ({_share(found, counts.cards)})")
    print(
        f"Cards counted (placed at or above the review threshold): {counts.cards_counted} "
        f"({_share(counts.cards_counted, counts.cards)}); "
        f"below the threshold: {counts.cards_below_threshold}."
    )
    queue = run.review_queue.counts
    print(
        f"Review queue: {queue.queued_items} items ({queue.queued_cards} cards, "
        f"{queue.without_heading} under no heading) under {queue.headings} headings; "
        f"{queue.rows} rows written, "
        f"{queue.left_out_below_minimum_teams} headings left out as used by too few teams."
    )
    print(f"Wrote the review queue to {run.review_queue_location}.")
    listed = run.placements.counts
    print(
        f"Wrote the placements listing to {run.placements_location}: {listed.rows} rows "
        f"({listed.placed_rows} placed, {listed.none_rows} ruled none), "
        f"{listed.left_out_below_minimum_teams} headings left out as used by too few teams."
    )
    if run.review_queue_order is not None:
        print(run.review_queue_order)
    print(
        f"Cache: {counts.lookups} distinct keys, {counts.hits} hits ({_share(counts.hits, counts.lookups)}), "
        f"{counts.misses} placed ({counts.refused_cached} cached results refused); "
        f"{'written' if counts.cache_written else 'unchanged'}."
    )
    for row in run.review_queue.rows[:show_unplaced]:
        answer = " (answer)" if row.answer else ""
        suggested = (
            f"; suggested: {row.suggested_position} (accept or override it in `decision`)"
            if row.suggested_position
            else ""
        )
        print(
            f"  unplaced: {row.normalized_heading}{answer}: {row.teams} teams, {row.documents} documents, "
            f"{row.cards} cards; candidates {', '.join(row.candidate_positions) or 'none'}{suggested}"
        )
    print(f"Runtime {seconds:.1f} s.")


async def _snapshot(
    arguments: argparse.Namespace,
    repository: YamlTaxonomyRepository,
    data_dir: Path,
    *,
    topic: str | None = None,
) -> tuple[date, TopicResolution]:
    """The snapshot to read (the newest weekly one unless given) and the topic topics.yaml puts it on.

    With `topic`, a caselist topics.yaml puts on another topic at the snapshot is refused.
    """
    objects = FsEvidenceObjectStore(data_dir)
    snapshot = arguments.snapshot
    if snapshot is None:
        snapshot = await LandscapeStalenessCheck(objects=objects, run_log=None).newest_snapshot(
            arguments.caselist
        )
        if snapshot is None:
            raise Refused(f"{arguments.caselist} has no weekly snapshot under {data_dir}")
    resolved = repository.resolve(arguments.caselist, snapshot)
    if resolved is None or resolved.taxonomy is None:
        raise Refused(f"topics.yaml puts {arguments.caselist} on {snapshot} on no topic with a taxonomy")
    if topic is not None and resolved.topic.id != topic:
        raise Refused(
            f"topics.yaml puts {arguments.caselist} on {snapshot} on {resolved.topic.id}, not {topic}: "
            "give the caselist the decisions are on"
        )
    return snapshot, resolved


async def _read(
    arguments: argparse.Namespace,
    repository: YamlTaxonomyRepository,
    data_dir: Path,
    snapshot: date,
    resolved: TopicResolution,
) -> SeedReading:
    """The caselist's sources on its topic as they stood at the snapshot."""
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    return await read_seed_sources(
        store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        topic=resolved.topic,
        caselist=arguments.caselist,
        version=arguments.version,
        through=snapshot,
        topic_map=repository.topic_map(),
    )


async def _classify(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    data_dir = _outside_the_repository(arguments.data_dir, "--data-dir")
    repository = YamlTaxonomyRepository.load(arguments.config_dir)
    snapshot, resolved = await _snapshot(arguments, repository, data_dir)
    reading = await _read(arguments, repository, data_dir, snapshot, resolved)
    suppression = RecordedSuppressionList(local_suppression_list_file(data_dir))
    print(
        f"Read {arguments.caselist} {reading.version} through {snapshot}: {reading.entries} source entries, "
        f"{reading.parsed} parsed, {len(reading.sources)} on {reading.topic_id}."
    )
    if not reading.sources:
        print(f"FAILED: 0 sources read for {reading.topic_id}; nothing was classified.", file=sys.stderr)
        return 1
    service = PositionClassificationService(
        taxonomies=repository,
        store=LocalClassificationStore(data_dir),
        review_threshold=arguments.threshold,
        minimum_review_teams=arguments.minimum_review_teams,
        queue_order=ReviewQueueOrdering(
            models=LocalQueueOrderModelStore(data_dir),
            parsed_store=LocalParsedStore(data_dir),
            suppression=suppression,
        ),
    )
    run = await service.classify(reading)
    _print_run(run, time.perf_counter() - started, arguments.show_unplaced)
    return 0


_WHERE: dict[Destination, str] = {
    Destination.HEADING_ABOVE_SAME_POSITION: "under a heading above, the same position",
    Destination.HEADING_ABOVE_OTHER_POSITION: "under a heading above, another position",
    Destination.TAG_KEYWORD: "to their tag keyword (the queue)",
    Destination.QUEUE: "to the queue",
    Destination.DECIDED: "decided (every heading over them ruled none)",
}


def _rule(rule: HeadingRule) -> str:
    if rule.kind == "alias":
        return f"alias of {rule.position_id}"
    if rule.kind == "override":
        return f"your decision {rule.position_id}"
    return "ruled none" if rule.kind == "none" else "undecided"


def effect_line(effect: DecisionEffect) -> str:
    """One changed decision as the apply step prints it: the heading, before and after, and its cards."""
    after = effect.after or "none"
    moves = ", ".join(
        f"{cards} {f'to {after}' if destination is Destination.DECISION else _WHERE[destination]}"
        for destination, cards in effect.moves.items()
    )
    return f"  {effect.heading}: {_rule(effect.before)} -> {after}: {effect.cards} cards: {moves}."


async def _apply_decisions(arguments: argparse.Namespace) -> int:
    decisions_path = _outside_the_repository(arguments.decisions, "--decisions")
    data_dir = _outside_the_repository(arguments.data_dir, "--data-dir")
    repository = YamlTaxonomyRepository.load(arguments.config_dir)
    snapshot, resolved = await _snapshot(arguments, repository, data_dir, topic=arguments.topic)
    with decisions_path.open(encoding="utf-8", newline="") as stream:
        decisions = read_decisions_csv(stream)
    taxonomy = repository.taxonomy(arguments.topic)
    current = repository.overrides(arguments.topic)
    applied = apply_decisions(current, decisions, taxonomy, decided=arguments.today)
    reading = await _read(arguments, repository, data_dir, snapshot, resolved)
    effects = placement_changes(
        reading.sources,
        CaselistNames(reading.caselist_names),
        PositionMatcher(taxonomy, current),
        PositionMatcher(taxonomy, applied.rules),
        applied.changed_headings,
        threshold=arguments.threshold,
    )
    print(
        f"Read {len(decisions)} decisions: {applied.added} added, {applied.changed} changed, "
        f"{applied.unchanged} unchanged."
    )
    print(
        f"Before anything is written, what each changed decision does to {arguments.caselist}'s cards "
        f"through {snapshot}:"
    )
    for effect in effects:
        if effect.cards:
            print(effect_line(effect))
    still = sum(1 for effect in effects if not effect.cards)
    if still:
        print(f"  {still} {'decision moves' if still == 1 else 'decisions move'} no card here.")
    target = arguments.config_dir / OVERRIDE_DIRECTORY / f"{arguments.topic}.yaml"
    if not arguments.execute:
        print(f"Dry run: nothing written. Run it again with --execute to write {target}.")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_override_file(applied.rules), encoding="utf-8")
    print(
        f"Applied {len(decisions)} decisions to {arguments.topic}: {applied.added} added, {applied.changed} "
        f"changed, {applied.unchanged} unchanged; {len(applied.rules.overrides)} overrides in {target}."
    )
    print("Run `uv run pytest tests/config` before committing it.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml, taxonomies/ and overrides/. Default: config/landscape.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    classify = commands.add_parser(
        "classify", help="Classify a caselist snapshot and write its review queue."
    )
    classify.add_argument("--caselist", required=True, help="The caselist slug.")
    classify.add_argument(
        "--snapshot", type=date.fromisoformat, help="YYYY-MM-DD. Default: the newest weekly snapshot."
    )
    classify.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="The data directory. Default: the dev one."
    )
    classify.add_argument("--version", help="The parsed store's version directory. Default: the newest.")
    classify.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_REVIEW_THRESHOLD,
        help=f"Queue a placed item less sure than this. Default: {DEFAULT_REVIEW_THRESHOLD}.",
    )
    classify.add_argument(
        "--minimum-review-teams",
        type=int,
        default=DEFAULT_MINIMUM_REVIEW_TEAMS,
        help=f"Leave out a queued heading fewer teams use. Default: {DEFAULT_MINIMUM_REVIEW_TEAMS}.",
    )
    classify.add_argument(
        "--show-unplaced", type=int, default=0, help="Print the queue's first N headings. Default: 0."
    )
    apply = commands.add_parser(
        "apply-decisions",
        help="Show what a filled queue or placements listing changes; with --execute, write the overrides.",
    )
    apply.add_argument("--topic", required=True, help="The topic id, as topics.yaml names it.")
    apply.add_argument(
        "--decisions", type=Path, required=True, help="The filled review queue or placements listing CSV."
    )
    apply.add_argument(
        "--today", type=date.fromisoformat, default=date.today(), help="The decision date. Default: today."
    )
    apply.add_argument(
        "--caselist", required=True, help="The caselist whose cards the summary counts, on --topic."
    )
    apply.add_argument(
        "--snapshot", type=date.fromisoformat, help="YYYY-MM-DD. Default: the newest weekly snapshot."
    )
    apply.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="The data directory. Default: the dev one."
    )
    apply.add_argument("--version", help="The parsed store's version directory. Default: the newest.")
    apply.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_REVIEW_THRESHOLD,
        help=f"A card placed less surely than this goes to the queue. Default: {DEFAULT_REVIEW_THRESHOLD}.",
    )
    apply.add_argument(
        "--execute", action="store_true", help="Write the overrides. Without it, only the summary is printed."
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "classify":
            return asyncio.run(_classify(arguments))
        return asyncio.run(_apply_decisions(arguments))
    except (Refused, DomainError, ValueError, OSError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

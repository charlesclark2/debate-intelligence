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
* **`apply-decisions`** reads a review queue CSV whose `decision` column the coach filled (a
  position id, or `none` for a heading that names no position) and writes the topic's overrides to
  `config/landscape/overrides/<topic id>.yaml`, refusing a decision naming no position of the
  taxonomy before anything is written. Commit that file after `tests/config` passes.

The queue and the decisions file hold headings from real disclosures, so neither may be inside the
repository; the script refuses a data directory or a decisions path there. Read-only for every store
but the cache and the queue.

    uv run python scripts/classify_landscape_positions.py classify --caselist hspolicy26
    uv run python scripts/classify_landscape_positions.py apply-decisions --topic policy-2026-27-nhi \\
        --decisions ~/Documents/debate/landscape-review/policy-2026-27-nhi-decisions.csv
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
from debate_core.application.landscape_seeding import read_seed_sources
from debate_core.application.landscape_staleness import LandscapeStalenessCheck
from debate_core.application.position_classification import (
    DECIDED_NO_POSITION,
    UNPLACED,
    ClassificationRun,
    PositionClassificationService,
)
from debate_core.application.review_queue_order import ReviewQueueOrdering
from debate_core.arguments.landscape.review_queue import (
    DEFAULT_MINIMUM_REVIEW_TEAMS,
    DEFAULT_REVIEW_THRESHOLD,
    apply_decisions,
    read_decisions_csv,
)
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


async def _classify(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    data_dir = _outside_the_repository(arguments.data_dir, "--data-dir")
    repository = YamlTaxonomyRepository.load(arguments.config_dir)
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
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
    suppression = RecordedSuppressionList(local_suppression_list_file(data_dir))
    reading = await read_seed_sources(
        store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=suppression,
        topic=resolved.topic,
        caselist=arguments.caselist,
        version=arguments.version,
        through=snapshot,
    )
    print(
        f"Read {arguments.caselist} {reading.version} through {snapshot}: {reading.entries} source entries, "
        f"{reading.parsed} parsed, {len(reading.sources)} on {resolved.topic.id}."
    )
    if not reading.sources:
        print(f"FAILED: 0 sources read for {resolved.topic.id}; nothing was classified.", file=sys.stderr)
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


def _apply_decisions(arguments: argparse.Namespace) -> int:
    decisions_path = _outside_the_repository(arguments.decisions, "--decisions")
    repository = YamlTaxonomyRepository.load(arguments.config_dir)
    with decisions_path.open(encoding="utf-8", newline="") as stream:
        decisions = read_decisions_csv(stream)
    applied = apply_decisions(
        repository.overrides(arguments.topic),
        decisions,
        repository.taxonomy(arguments.topic),
        decided=arguments.today,
    )
    target = arguments.config_dir / OVERRIDE_DIRECTORY / f"{arguments.topic}.yaml"
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
        "apply-decisions", help="Turn a filled review queue into the topic's overrides."
    )
    apply.add_argument("--topic", required=True, help="The topic id, as topics.yaml names it.")
    apply.add_argument("--decisions", type=Path, required=True, help="The filled review queue CSV.")
    apply.add_argument(
        "--today", type=date.fromisoformat, default=date.today(), help="The decision date. Default: today."
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "classify":
            return asyncio.run(_classify(arguments))
        return _apply_decisions(arguments)
    except (Refused, DomainError, ValueError, OSError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

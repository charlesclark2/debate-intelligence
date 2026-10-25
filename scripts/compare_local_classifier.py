#!/usr/bin/env python3
"""Compare a local text classifier with the deterministic placements of a caselist's cards (`v1-e32-t21`).

Headings and tags place about half of a caselist's cards. This measures whether TF-IDF word and
short-phrase weights with a logistic regression
(:mod:`~debate_core.arguments.landscape.local_classifier`), trained on this machine from the cards
they place, could place the rest. Nothing is wired: the report, the matcher and the review queue are
untouched. Four commands:

* **`features`** reads the caselist's parsed card store as it stood at a snapshot (the newest weekly
  one unless `--snapshot` names one), places every card as `v1-e32-t02` does, without its cache, and
  writes the feature table.
* **`compare`** trains on the labelled cards of nine tenths of the documents and measures on the
  tenth: precision and recall by kind and position, precision by confidence, the confidence at which
  held-out precision is at least 90%, and how many cards no label covers it would place there. It
  compares two models: the one specified (a card's tag and every heading over it) and a proxy trained
  and scored without the headings that place a card on their own, as no heading over an unplaced card
  does. It prints counts and position ids only, and writes them as JSON.
* **`sample`** trains the same way, with the same seed, and writes 60 unplaced cards for the coach to
  label: a CSV of each card's tag and headings with an empty `position` column, and beside it the
  sampled cards' ids and predictions, which the CSV does not show.
* **`score-sample`** reads the coach's labelled CSV and scores both models' predictions on it.

Every file is written under `<data dir>/landscape/local-classifier/<caselist>/`, and nowhere else:
they are derived from the caselist's cards, so they follow the data directory's retention and are
never committed. `compare`, `sample` and `score-sample` refuse a feature table whose sources a
removal has since reached; `features` builds it again from the store, which no longer holds them.

Every command refuses to start when a `DEBATE_*` variable is set or a `caselist pull` is running.
Read-only for every store; it starts no worker process.

    uv run python scripts/compare_local_classifier.py features --caselist hspolicy26 --snapshot 2026-10-20
    uv run python scripts/compare_local_classifier.py compare --caselist hspolicy26
    uv run python scripts/compare_local_classifier.py sample --caselist hspolicy26
    uv run python scripts/compare_local_classifier.py score-sample --caselist hspolicy26 \\
        --labels ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample.csv
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import DomainError
from debate_core.application.landscape_seeding import read_seed_sources
from debate_core.application.landscape_staleness import LandscapeStalenessCheck
from debate_core.application.local_classifier_comparison import (
    FeatureTable,
    build_feature_table,
    feature_table_lines,
    read_feature_table,
    sources_no_longer_live,
)
from debate_core.arguments.landscape.local_classifier import (
    DEFAULT_MINIMUM_FEATURE_TEAMS,
    DEFAULT_SEED,
    SAMPLE_STRATA,
    TARGET_PRECISION,
    UNPLACED,
    Band,
    Comparison,
    SampleScore,
    Tally,
    coach_sample,
    compare,
    heading_teams,
    read_sample,
    read_sample_labels,
    sample_lines,
    score_sample,
    write_sample_csv,
)
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD
from debate_core.domain.landscape import Taxonomy
from debate_core.integrations.file_streaming import atomic_replacement
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"
DEFAULT_DATA_DIR = Path.home() / ".debate-research" / "dev"
OUTPUT_DIRECTORY = Path("landscape") / "local-classifier"
SHELLS = frozenset({"zsh", "bash", "sh", "-zsh", "-bash", "-sh", "ps", "grep", "pgrep"})
"""Processes whose command line may hold the words `caselist pull` without being one."""
POSITION_ROWS_SHOWN = 20
"""A position is printed when at least this many held-out cards are labelled or predicted as it."""
MODELS = {"specified": False, "proxy": True}
"""Each model's name, and whether it is trained and scored without the headings that place on their own."""
STRATIFIED_BY = "proxy"
"""The model the coach sample is stratified on. The specified model reads the headings its labels come
from, so its held-out threshold says nothing about the cards those headings miss."""


class Refused(Exception):
    """A run this script will not make, with the reason to print."""


def running_processes() -> list[tuple[str, str]]:
    """`(command, arguments)` of every process on the machine, as `ps` lists them."""
    listed = subprocess.run(["ps", "-Ao", "comm=,args="], capture_output=True, text=True, check=True).stdout
    found: list[tuple[str, str]] = []
    for line in listed.splitlines():
        command, _, arguments = line.strip().partition(" ")
        found.append((Path(command).name, arguments))
    return found


def refuse_an_unsafe_environment(
    environ: Mapping[str, str], processes: Callable[[], Sequence[tuple[str, str]]]
) -> None:
    """Refuse a run with a `DEBATE_*` override set, or while a `caselist pull` is running."""
    overrides = sorted(name for name in environ if name.startswith("DEBATE_"))
    if overrides:
        raise Refused(f"{', '.join(overrides)} is set; unset it and run again")
    pulls = [
        command
        for command, arguments in processes()
        if "caselist pull" in arguments and command not in SHELLS
    ]
    if pulls:
        raise Refused("a caselist pull is running; wait for it to finish")


def _outside_the_repository(path: Path, what: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise Refused(f"{what} must be outside the repository ({REPO_ROOT}): it holds real cards")
    return resolved


def output_directory(data_dir: Path, caselist: str) -> Path:
    """`<data dir>/landscape/local-classifier/<caselist>/`: every file this script writes."""
    return data_dir / OUTPUT_DIRECTORY / caselist


def _write(path: Path, text: str) -> None:
    with atomic_replacement(path) as incoming:
        incoming.write_text(text, encoding="utf-8")


def _share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def _ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


# ------------------------------------------------------------------------------------------------
# features
# ------------------------------------------------------------------------------------------------


async def _features(arguments: argparse.Namespace) -> int:
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
        print(f"FAILED: 0 sources read for {resolved.topic.id}; no table was written.", file=sys.stderr)
        return 1
    table = await build_feature_table(
        reading, repository, suppression, through=snapshot, review_threshold=arguments.threshold
    )
    target = output_directory(data_dir, arguments.caselist) / f"{table.topic_id}-features.jsonl"
    _write(target, "".join(feature_table_lines(table)))
    placements = Counter(row.placement for row in table.rows)
    labelled = sum(row.label is not None for row in table.rows)
    print(f"Taxonomy {table.taxonomy_version}; review threshold {table.review_threshold}.")
    print(f"Cards {len(table.rows)}; labelled {labelled} ({_share(labelled, len(table.rows))}).")
    for placement, count in sorted(placements.items()):
        print(f"  cards {placement}: {count} ({_share(count, len(table.rows))})")
    print(f"Wrote the feature table to {target}.")
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


# ------------------------------------------------------------------------------------------------
# compare and sample
# ------------------------------------------------------------------------------------------------


async def _read_table(arguments: argparse.Namespace) -> tuple[Path, FeatureTable, Taxonomy, frozenset[str]]:
    """The caselist's feature table, its taxonomy, and the table's sources a removal has reached since."""
    data_dir = _outside_the_repository(arguments.data_dir, "--data-dir")
    directory = output_directory(data_dir, arguments.caselist)
    tables = sorted(directory.glob("*-features.jsonl")) if directory.is_dir() else []
    if len(tables) != 1:
        raise Refused(
            f"expected one feature table under {directory}, found {len(tables)}; run `features` first"
        )
    with tables[0].open(encoding="utf-8") as stream:
        table = read_feature_table(stream)
    gone = await sources_no_longer_live(
        table,
        store=LocalParsedStore(data_dir),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
    )
    taxonomy = YamlTaxonomyRepository.load(arguments.config_dir).taxonomy(table.topic_id)
    if taxonomy.taxonomy_version != table.taxonomy_version:
        raise Refused(
            f"the table was placed under taxonomy {table.taxonomy_version} and {table.topic_id} is now "
            f"{taxonomy.taxonomy_version}; run `features` again"
        )
    return directory, table, taxonomy, gone


async def _live_table(arguments: argparse.Namespace) -> tuple[Path, FeatureTable, Taxonomy]:
    """The feature table, refused when a removal has reached any of its sources since it was built."""
    directory, table, taxonomy, gone = await _read_table(arguments)
    if gone:
        raise Refused(
            f"a removal has reached {len(gone)} of the table's {len(table.sources)} sources since it was "
            "built; run `features` again"
        )
    return directory, table, taxonomy


def _comparisons(
    arguments: argparse.Namespace, table: FeatureTable, taxonomy: Taxonomy
) -> dict[str, Comparison]:
    return {
        name: compare(
            taxonomy,
            table.rows,
            seed=arguments.seed,
            minimum_teams=arguments.minimum_teams,
            without_placing_headings=without,
        )
        for name, without in MODELS.items()
    }


def _tally_json(tally: Tally) -> dict[str, object]:
    return {
        "name": tally.name,
        "held_out": tally.held_out,
        "predicted": tally.predicted,
        "correct": tally.correct,
        "right_kind": tally.right_kind,
        "precision": tally.precision,
        "recall": tally.recall,
    }


def _bands_json(bands: Sequence[Band]) -> list[dict[str, object]]:
    return [{"low": one.low, "high": one.high, "cards": one.cards, "correct": one.correct} for one in bands]


def comparison_json(name: str, comparison: Comparison) -> dict[str, object]:
    """One model's counts, position ids and confidences: nothing a card or heading says."""
    measure = comparison.held_out
    return {
        "model": name,
        "without_placing_headings": comparison.without_placing_headings,
        "seed": comparison.seed,
        "documents": comparison.documents,
        "held_out_documents": comparison.held_out_documents,
        "trained_cards": comparison.trained_cards,
        "classes": comparison.classes,
        "features": comparison.features,
        "held_out": {
            "cards": measure.cards,
            "predicted": measure.predicted,
            "correct": measure.correct,
            "seen_in_training": measure.seen_in_training,
            "seen_in_training_correct": measure.seen_in_training_correct,
            "by_kind": [_tally_json(one) for one in measure.by_kind],
            "by_position": [_tally_json(one) for one in measure.by_position],
            "bands": _bands_json(measure.bands),
            "at_or_above": _bands_json(measure.at_or_above),
            "unseen_at_or_above": _bands_json(measure.unseen_at_or_above),
            "confidence_at_target": measure.confidence_at_target,
        },
        "would_place": [
            {
                "placement": one.placement,
                "cards": one.cards,
                "without_features": one.without_features,
                "seen_in_training": one.seen_in_training,
                "at_threshold": one.at_threshold,
                "at_threshold_seen": one.at_threshold_seen,
                "by_kind": dict(one.by_kind),
                "estimated_threshold": one.estimated_threshold,
                "by_kind_at_estimated": dict(one.by_kind_at_estimated),
                "estimates": [
                    {
                        "confidence": estimate.confidence,
                        "cards": estimate.cards,
                        "seen": estimate.seen,
                        "held_out": estimate.held_out,
                        "precision": estimate.precision,
                    }
                    for estimate in one.estimates
                ],
            }
            for one in comparison.would_place
        ],
    }


def _print_tallies(title: str, tallies: Sequence[Tally], kinds: bool) -> None:
    print(f"  {title}: held out, predicted, correct, precision, recall" + (", right kind" if kinds else ""))
    for one in tallies:
        extra = f", {_ratio(one.right_kind / one.predicted if one.predicted else None)}" if kinds else ""
        print(
            f"    {one.name}: {one.held_out}, {one.predicted}, {one.correct}, "
            f"{_ratio(one.precision)}, {_ratio(one.recall)}{extra}"
        )


def _print_comparison(name: str, comparison: Comparison) -> None:
    measure = comparison.held_out
    reads = (
        "the tag and every heading"
        if not comparison.without_placing_headings
        else "the tag and the headings that place nothing on their own"
    )
    print(f"Model {name}: {reads}; seed {comparison.seed}.")
    print(
        f"  Split: {comparison.documents} documents, {comparison.held_out_documents} held out; trained on "
        f"{comparison.trained_cards} labelled cards, {comparison.classes} positions, "
        f"{comparison.features} features."
    )
    print(
        f"  Held out: {measure.cards} labelled cards, {measure.predicted} predicted, "
        f"{measure.correct} correct "
        f"(precision {_ratio(measure.correct / measure.predicted if measure.predicted else None)}, "
        f"recall {_ratio(measure.correct / measure.cards if measure.cards else None)})."
    )
    unseen = measure.predicted - measure.seen_in_training
    unseen_correct = measure.correct - measure.seen_in_training_correct
    print(
        f"  Of those predicted, {measure.seen_in_training} have a training card's features exactly "
        f"({measure.seen_in_training_correct} correct, "
        f"{_share(measure.seen_in_training_correct, measure.seen_in_training)}); the other {unseen}: "
        f"{unseen_correct} correct ({_share(unseen_correct, unseen)})."
    )
    _print_tallies("By kind", measure.by_kind, True)
    shown = [one for one in measure.by_position if max(one.held_out, one.predicted) >= POSITION_ROWS_SHOWN]
    _print_tallies(
        f"By position ({len(shown)} of {len(measure.by_position)} with {POSITION_ROWS_SHOWN} or more)",
        shown,
        False,
    )
    print("  By confidence band: cards, correct, precision")
    for band in measure.bands:
        print(
            f"    {band.low:.2f} to {band.high:.2f}: {band.cards}, {band.correct}, {_ratio(band.precision)}"
        )
    print("  At or above: cards, correct, precision; then the same over the cards unlike any training card")
    for every, unseen_band in zip(measure.at_or_above, measure.unseen_at_or_above, strict=True):
        print(
            f"    {every.low:.3f}: {every.cards}, {every.correct}, {_ratio(every.precision)}; "
            f"{unseen_band.cards}, {unseen_band.correct}, {_ratio(unseen_band.precision)}"
        )
    threshold = "none reaches it" if comparison.threshold is None else f"{comparison.threshold:.3f}"
    print(f"  Confidence at {TARGET_PRECISION:.0%} held-out precision: {threshold}.")
    for one in comparison.would_place:
        kinds = ", ".join(f"{kind} {count}" for kind, count in one.by_kind) or "none"
        print(
            f"  Would place {one.at_threshold} of {one.cards} {one.placement} cards "
            f"({_share(one.at_threshold, one.cards)}): {kinds}. "
            f"{one.without_features} have no known feature; "
            f"{one.seen_in_training} have a training card's features exactly, {one.at_threshold_seen} of "
            "them at the threshold."
        )
    unplaced = next(one for one in comparison.would_place if one.placement == UNPLACED)
    if unplaced.estimates:
        print(
            "  Estimated precision on the UNPLACED cards it would place, held-out precision weighed to their "
            "mix: confidence, cards, of them like a training card, estimate"
        )
        for estimate in unplaced.estimates:
            print(
                f"    {estimate.confidence:.3f}: {estimate.cards}, {estimate.seen}, "
                f"{_ratio(estimate.precision)}"
            )
        threshold = (
            "none reaches it"
            if unplaced.estimated_threshold is None
            else f"{unplaced.estimated_threshold:.3f}"
        )
        kinds = ", ".join(f"{kind} {count}" for kind, count in unplaced.by_kind_at_estimated) or "none"
        print(
            f"  Confidence at an estimated {TARGET_PRECISION:.0%} on the UNPLACED cards: {threshold}; "
            f"it would place {sum(count for _, count in unplaced.by_kind_at_estimated)}: {kinds}."
        )


async def _compare(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    directory, table, taxonomy = await _live_table(arguments)
    comparisons = _comparisons(arguments, table, taxonomy)
    for name, comparison in comparisons.items():
        _print_comparison(name, comparison)
    target = directory / f"{table.topic_id}-comparison.json"
    document = {
        "caselist": table.caselist,
        "topic_id": table.topic_id,
        "taxonomy_version": table.taxonomy_version,
        "through": None if table.through is None else table.through.isoformat(),
        "minimum_feature_teams": arguments.minimum_teams,
        "models": [comparison_json(name, comparison) for name, comparison in comparisons.items()],
    }
    _write(target, json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(f"Wrote the counts to {target}.")
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


def sample_paths(directory: Path, topic_id: str) -> tuple[Path, Path]:
    """The coach's CSV, and the sampled cards' ids and predictions beside it."""
    return directory / f"{topic_id}-coach-sample.csv", directory / f"{topic_id}-coach-sample.jsonl"


async def _sample(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    directory, table, taxonomy = await _live_table(arguments)
    comparisons = _comparisons(arguments, table, taxonomy)
    sample = coach_sample(taxonomy, table.rows, comparisons, stratified_by=STRATIFIED_BY, seed=arguments.seed)
    csv_path, items_path = sample_paths(directory, table.topic_id)
    with atomic_replacement(csv_path) as incoming, incoming.open("w", encoding="utf-8", newline="") as stream:
        write_sample_csv(stream, sample, heading_teams(table.rows))
    _write(items_path, "".join(sample_lines(sample)))
    thresholds = ", ".join(
        f"{name} {'none' if one is None else f'{one:.3f}'}" for name, one in sample.thresholds.items()
    )
    print(
        f"Sampled {len(sample.items)} unplaced cards from "
        f"{len({item.source_sha256 for item in sample.items})} "
        f"documents, stratified by the {sample.stratified_by} model's confidence; thresholds {thresholds}."
    )
    for stratum, _ in SAMPLE_STRATA:
        kinds = Counter(
            taxonomy.resolve(prediction.position_id).kind.value
            for item in sample.items
            if item.stratum == stratum and (prediction := item.predictions[sample.stratified_by]) is not None
        )
        count = sum(kinds.values())
        print(
            f"  {stratum}: {count} of {sample.populations[stratum]} unplaced cards "
            f"({', '.join(f'{kind} {n}' for kind, n in sorted(kinds.items())) or 'none'})"
        )
    print(f"Wrote the coach's file to {csv_path}.")
    print(f"Wrote the sampled cards' ids and predictions to {items_path}.")
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


# ------------------------------------------------------------------------------------------------
# score-sample
# ------------------------------------------------------------------------------------------------


def _print_score(score: SampleScore) -> None:
    threshold = "none" if score.threshold is None else f"{score.threshold:.3f}"
    print(
        f"Model {score.model}: {score.correct} of {score.labelled} labelled cards right "
        f"({_ratio(score.accuracy)}); the coach said {score.no_position} belong to no position."
    )
    print(
        f"  At its threshold {threshold}: {score.at_threshold.correct} of {score.at_threshold.labelled} "
        f"({_ratio(score.at_threshold.accuracy)}). Weighted by stratum over the unplaced cards: accuracy "
        f"{_ratio(score.weighted_accuracy)}, precision at the threshold "
        f"{_ratio(score.weighted_precision_at_threshold)}."
    )
    for one in score.by_stratum:
        print(
            f"  {one.name}: {one.correct} of {one.labelled} ({_ratio(one.accuracy)}), "
            f"from {one.population} unplaced cards"
        )
    for one in score.by_predicted_kind:
        print(f"  predicted {one.name}: {one.correct} of {one.labelled} ({_ratio(one.accuracy)})")


async def _score_sample(arguments: argparse.Namespace) -> int:
    directory, table, taxonomy, gone = await _read_table(arguments)
    labels_path = _outside_the_repository(arguments.labels, "--labels")
    _, items_path = sample_paths(directory, table.topic_id)
    if not items_path.is_file():
        raise Refused(f"no sample under {directory}; run `sample` first")
    with items_path.open(encoding="utf-8") as stream:
        sample = read_sample(stream)
    with labels_path.open(encoding="utf-8", newline="") as stream:
        labels = read_sample_labels(stream, taxonomy)
    unknown = sorted(set(labels) - {item.sample_row for item in sample.items})
    if unknown:
        raise Refused(f"the labelled file has {len(unknown)} rows the sample does not, from row {unknown[0]}")
    removed = sorted(item.sample_row for item in sample.items if item.source_sha256 in gone)
    if removed:
        print(
            f"A removal has reached {len(removed)} sampled cards' sources since the sample was drawn; rows "
            f"{', '.join(map(str, removed))} are not scored. Delete them from the labelled file."
        )
    kept = {row: label for row, label in labels.items() if row not in removed}
    print(
        f"Labels: {len(kept)} of {len(sample.items)} sampled cards (blank and `unsure` rows are not scored)."
    )
    scores = score_sample(taxonomy, sample, kept)
    for score in scores:
        _print_score(score)
    target = directory / f"{table.topic_id}-coach-sample-score.json"
    document = [
        {
            "model": score.model,
            "labelled": score.labelled,
            "correct": score.correct,
            "no_position": score.no_position,
            "threshold": score.threshold,
            "at_threshold": [score.at_threshold.correct, score.at_threshold.labelled],
            "weighted_accuracy": score.weighted_accuracy,
            "weighted_precision_at_threshold": score.weighted_precision_at_threshold,
            "by_stratum": {one.name: [one.correct, one.labelled, one.population] for one in score.by_stratum},
            "by_predicted_kind": {one.name: [one.correct, one.labelled] for one in score.by_predicted_kind},
        }
        for score in scores
    ]
    _write(target, json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(f"Wrote the score to {target}.")
    return 0


# ------------------------------------------------------------------------------------------------


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    processes: Callable[[], Sequence[tuple[str, str]]] = running_processes,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml, taxonomies/ and overrides/. Default: config/landscape.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("features", "Read the store and write the feature table."),
        ("compare", "Train, measure on the held-out tenth, and count what it would place."),
        ("sample", "Write 60 unplaced cards for the coach to label."),
        ("score-sample", "Score both models on the coach's labels."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--caselist", required=True, help="The caselist slug.")
        command.add_argument(
            "--data-dir",
            type=Path,
            default=DEFAULT_DATA_DIR,
            help="The data directory. Default: the dev one.",
        )
        if name == "features":
            command.add_argument(
                "--snapshot", type=date.fromisoformat, help="YYYY-MM-DD. Default: the newest weekly snapshot."
            )
            command.add_argument(
                "--version", help="The parsed store's version directory. Default: the newest."
            )
            command.add_argument(
                "--threshold",
                type=float,
                default=DEFAULT_REVIEW_THRESHOLD,
                help=f"A placement less sure than this is no label. Default: {DEFAULT_REVIEW_THRESHOLD}.",
            )
        elif name in ("compare", "sample"):
            command.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Default: {DEFAULT_SEED}.")
            command.add_argument(
                "--minimum-teams",
                type=int,
                default=DEFAULT_MINIMUM_FEATURE_TEAMS,
                help=f"A token fewer teams carry is no feature. Default: {DEFAULT_MINIMUM_FEATURE_TEAMS}.",
            )
        else:
            command.add_argument("--labels", type=Path, required=True, help="The coach's labelled CSV.")
    arguments = parser.parse_args(argv)
    runs = {"features": _features, "compare": _compare, "sample": _sample, "score-sample": _score_sample}
    try:
        refuse_an_unsafe_environment(os.environ if environ is None else environ, processes)
        return asyncio.run(runs[arguments.command](arguments))
    except (Refused, DomainError, ValueError, OSError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

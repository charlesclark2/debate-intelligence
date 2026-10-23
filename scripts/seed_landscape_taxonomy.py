#!/usr/bin/env python3
"""Seed a topic's position taxonomy from the parsed card store, and sheet a draft for the coach.

`v1-e32-t01-position-taxonomy`. A taxonomy is seeded, not invented: the coach curates positions
from the headings teams actually disclosed under. Two commands, both deterministic, neither calling
a model:

* **`candidates`** reads one caselist's parsed card store (`<data dir>/parsed/`) and its manifests,
  keeps the sources disclosed inside the topic's date ranges in `config/landscape/topics.yaml`, and
  writes a CSV of normalized headings with their level, documents, distinct teams (from the
  disclosures, never from heading text) and a suggested position id. A heading fewer than
  `--minimum-teams` teams use (two by default) is left out. It prints what it read and exits 1 when
  it read no source on the topic or wrote no candidate, so an empty store never looks like a run.
* **`review`** sets the committed draft taxonomy beside a candidates CSV: each position with its
  kind, side and aliases and the counts behind each alias, then the top unplaced headings.

Both write only where `--out` says, which must be outside the repository: the CSV and the sheet hold
headings from real disclosures and are never committed (the PM's ruling, 2026-10-22). Neither holds
a path, a file name, a school or a team code; a team's own names are taken out of its headings
before they are counted. Read-only for every store.

    uv run python scripts/seed_landscape_taxonomy.py candidates --topic policy-2026-27-nhi \\
        --out ~/Documents/debate/landscape-seed/policy-2026-27-nhi-candidates.csv
    uv run python scripts/seed_landscape_taxonomy.py review --topic policy-2026-27-nhi \\
        --candidates ~/Documents/debate/landscape-seed/policy-2026-27-nhi-candidates.csv \\
        --out ~/Documents/debate/landscape-seed/policy-2026-27-nhi-review.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import DomainError
from debate_core.application.landscape_seeding import read_seed_sources
from debate_core.arguments.landscape.seeding import (
    DEFAULT_MINIMUM_TEAMS,
    read_candidates_csv,
    review_sheet,
    seed_candidates,
    write_candidates_csv,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    TOPICS_FILE,
    YamlTaxonomyRepository,
    load_topic_map,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"
DEFAULT_DATA_DIR = Path.home() / ".debate-research" / "dev"


class Refused(Exception):
    """A run this script will not make, with the reason to print."""


def _outside_the_repository(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise Refused(
            f"--out must be outside the repository ({REPO_ROOT}); seeding output is never committed"
        )
    return resolved


async def _candidates(arguments: argparse.Namespace) -> int:
    out = _outside_the_repository(arguments.out)
    topic_map = load_topic_map(arguments.config_dir / TOPICS_FILE)
    try:
        topic = topic_map.topic(arguments.topic)
    except KeyError:
        raise Refused(f"{TOPICS_FILE} has no topic {arguments.topic}") from None
    caselists = sorted({one.caselist for one in topic.caselists})
    caselist = arguments.caselist or (caselists[0] if len(caselists) == 1 else None)
    if caselist is None:
        raise Refused(f"{topic.id} covers {', '.join(caselists)}; name one with --caselist")
    data_dir = arguments.data_dir.expanduser()
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    reading = await read_seed_sources(
        store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        topic=topic,
        caselist=caselist,
        version=arguments.version,
    )
    seeding = seed_candidates(
        reading.sources, minimum_teams=arguments.minimum_teams, caselist_names=reading.caselist_names
    )
    counts = seeding.counts
    print(f"Read {caselist} {reading.version}: {reading.entries} source entries, {reading.parsed} parsed.")
    print(
        f"On {topic.id}: {counts.sources} sources, {counts.cards} cards "
        f"({reading.parsed_off_topic} parsed sources had no live disclosure in its ranges; "
        f"{counts.sources_without_team} had no readable team)."
    )
    print(
        f"Headings: {counts.headings} counted, {counts.distinct_headings} distinct; "
        f"{counts.left_out_below_minimum_teams} used by fewer than {arguments.minimum_teams} teams left out."
    )
    if counts.sources == 0:
        print(f"FAILED: 0 sources read for {topic.id} from {caselist}; nothing was written.", file=sys.stderr)
        return 1
    if counts.candidates == 0:
        print(
            f"FAILED: {counts.sources} sources read but 0 candidates; nothing was written.", file=sys.stderr
        )
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as stream:
        write_candidates_csv(seeding.rows, stream)
    print(f"Wrote {counts.candidates} candidate rows to {out}.")
    print(f"{caselist} sources read: {counts.sources}; candidate rows: {counts.candidates}")
    return 0


def _review(arguments: argparse.Namespace) -> int:
    out = _outside_the_repository(arguments.out)
    taxonomy = YamlTaxonomyRepository.load(arguments.config_dir).taxonomy(arguments.topic)
    with arguments.candidates.expanduser().open(encoding="utf-8", newline="") as stream:
        rows = read_candidates_csv(stream)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(review_sheet(rows, taxonomy, unplaced_limit=arguments.unplaced), encoding="utf-8")
    print(f"Wrote the review of {len(taxonomy.positions)} positions and {len(rows)} candidate rows to {out}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml and taxonomies/. Default: config/landscape.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    candidates = commands.add_parser(
        "candidates", help="Write a topic's candidates CSV from the parsed store."
    )
    candidates.add_argument("--topic", required=True, help="The topic id, as topics.yaml names it.")
    candidates.add_argument(
        "--caselist", help="The caselist to read; needed only when the topic covers several."
    )
    candidates.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="The data directory whose parsed/ store and manifests are read. Default: the dev one.",
    )
    candidates.add_argument("--version", help="The version directory to read. Default: the newest.")
    candidates.add_argument(
        "--minimum-teams",
        type=int,
        default=DEFAULT_MINIMUM_TEAMS,
        help=f"Leave out a heading fewer teams than this use. Default: {DEFAULT_MINIMUM_TEAMS}.",
    )
    candidates.add_argument(
        "--out", type=Path, required=True, help="The CSV to write, outside the repository."
    )
    review = commands.add_parser("review", help="Sheet the committed taxonomy beside a candidates CSV.")
    review.add_argument("--topic", required=True, help="The topic id, as topics.yaml names it.")
    review.add_argument("--candidates", type=Path, required=True, help="A CSV the candidates command wrote.")
    review.add_argument(
        "--unplaced", type=int, default=40, help="How many unplaced headings to list. Default: 40."
    )
    review.add_argument(
        "--out", type=Path, required=True, help="The Markdown sheet to write, outside the repository."
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "candidates":
            return asyncio.run(_candidates(arguments))
        return _review(arguments)
    except (Refused, DomainError, ValueError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

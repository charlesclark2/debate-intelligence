#!/usr/bin/env python3
"""Read a Policy caselist's CP texts, alternatives, roles of the ballot and overviews (`v1-e32-t11`).

`debate-research landscape report` reads them on every run, from the analytic-text cache
(`<data dir>/landscape/analytic_texts/<caselist>.jsonl`). This is how the operator fills that cache the
first time, or after a taxonomy, overrides or actor-list edit, without the rest of a report run: it reads
the caselist's parsed sources on the topic through the snapshot (the newest weekly one unless `--snapshot`
names one), as `v1-e32-t02`'s classifier does, and reads every one from its own bytes in this machine's blob
store, parsing only what the cache does not hold. It writes the cache and nothing else, and prints counts
only: sources, cache hits, sources parsed, refused and unread, each kind's texts found and placed, and the
CP texts the actor guard kept and refused in negative files. With `--quote` it also reads again the texts a
report would quote, in memory, and counts them; it never prints one.

It exits 1 when it read no source, so an empty store never looks like a run. The first run over hspolicy26
parses every on-topic file: about 0.25 s of a worker's time each, so about 2 minutes over 8 workers.

    uv run python scripts/read_landscape_texts.py --caselist hspolicy26
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from debate_core.application.analytic_texts import AnalyticTextService
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.parse_workers import (
    InProcessParseRunner,
    ParseRunner,
    ProcessPoolParseRunner,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import DomainError
from debate_core.application.landscape_seeding import read_seed_sources
from debate_core.application.landscape_staleness import LandscapeStalenessCheck
from debate_core.arguments.landscape.analytic_texts import AnalyticTextRules
from debate_core.domain.caselist import Side
from debate_core.domain.landscape_texts import AnalyticTextKind, TextForm
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.landscape.analytic_text_store import LocalAnalyticTextStore
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"
DEFAULT_DATA_DIR = Path.home() / ".debate-research" / "dev"
DEFAULT_WORKERS = max(1, min(8, (os.cpu_count() or 2) - 1))
PER_FILE_TIMEOUT_SECONDS = 120.0


class Refused(Exception):
    """A run this script will not make, with the reason to print."""


async def _read(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    data_dir = arguments.data_dir.expanduser().resolve()
    if data_dir == REPO_ROOT or REPO_ROOT in data_dir.parents:
        raise Refused(f"--data-dir must be outside the repository ({REPO_ROOT})")
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )
    snapshot = arguments.snapshot
    if snapshot is None:
        snapshot = await LandscapeStalenessCheck(objects=objects, run_log=None).newest_snapshot(
            arguments.caselist
        )
        if snapshot is None:
            raise Refused(f"{arguments.caselist} has no weekly snapshot under {data_dir}")
    repository = YamlTaxonomyRepository.load(arguments.config_dir)
    resolved = repository.resolve(arguments.caselist, snapshot)
    if resolved is None or resolved.taxonomy is None:
        raise Refused(f"topics.yaml puts {arguments.caselist} on {snapshot} on no topic with a taxonomy")
    topic = resolved.topic.id
    reading = await read_seed_sources(
        store=LocalParsedStore(data_dir),
        local=local,
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        topic=resolved.topic,
        caselist=arguments.caselist,
        version=arguments.version,
        through=snapshot,
    )
    negative = {
        source.sha256 for source in reading.sources if any(team.side is Side.NEG for team in source.teams)
    }
    affirmative = sum(1 for source in reading.sources if any(team.side is Side.AFF for team in source.teams))
    print(
        f"Read {arguments.caselist} {reading.version} through {snapshot}: {len(reading.sources)} sources on "
        f"{topic}, {len(negative)} negative, {affirmative} affirmative."
    )
    if not reading.sources:
        print("FAILED: 0 sources read; nothing was read for analytic texts.", file=sys.stderr)
        return 1
    runner: ParseRunner = (
        InProcessParseRunner()
        if arguments.workers == 0
        else ProcessPoolParseRunner(workers=arguments.workers, timeout_seconds=PER_FILE_TIMEOUT_SECONDS)
    )
    service = AnalyticTextService(
        parser=DebateDocxParser(), runner=runner, store=LocalAnalyticTextStore(data_dir), local=local
    )
    on_topic = {source.sha256: source for source in reading.sources}
    documents = [
        one.source_document()
        for one in await enumerate_sources(local, arguments.caselist)
        if one.sha256 in on_topic
    ]
    taxonomy = repository.taxonomy(topic)
    run = await service.read(
        arguments.caselist,
        documents,
        AnalyticTextRules(taxonomy, repository.overrides(topic), repository.cp_text_actors(topic)),
        own_names={
            sha: tuple(name for team in source.teams for name in team.names if name.strip())
            for sha, source in on_topic.items()
        },
        caselist_names=reading.caselist_names,
    )
    counts = run.counts
    print(
        f"Analytic texts: {counts.sources} sources, {counts.hits} cached, {counts.parsed} parsed, "
        f"{counts.refused} refused by the parser, {counts.unread} unread; cache "
        f"{'written' if counts.cache_written else 'unchanged'}."
    )
    for kind in AnalyticTextKind:
        print(
            f"  {kind.value}: {counts.readings.get(kind.value, 0)} found, "
            f"{counts.placed.get(kind.value, 0)} placed"
        )
    kept = sum(
        1
        for sha, found in run.readings.items()
        if sha in negative
        for one in found
        if one.form is TextForm.BY_PLACE
    )
    refused = sum(count for sha, count in run.refused_by_guard.items() if sha in negative)
    print(f"CP texts by place in negative files: {kept} kept by the actor guard, {refused} refused.")
    if arguments.quote:
        quoted = await service.quote(arguments.caselist, documents, run, taxonomy)
        sources = "source" if quoted.sources == 1 else "sources"
        print(
            f"Quoted: {quoted.sources} {sources} read again for {quoted.wanted} texts; "
            f"{len(quoted.texts)} read as they were read, {quoted.mismatched} not, {quoted.unread} unread."
        )
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml, taxonomies/ and analytic_texts/. Default: config/landscape.",
    )
    parser.add_argument("--caselist", required=True, help="The caselist slug.")
    parser.add_argument(
        "--snapshot", type=date.fromisoformat, help="YYYY-MM-DD. Default: the newest weekly snapshot."
    )
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="The data directory. Default: the dev one."
    )
    parser.add_argument("--version", help="The parsed store's version directory. Default: the newest.")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Parser processes; 0 parses in this process. Default: {DEFAULT_WORKERS}.",
    )
    parser.add_argument(
        "--quote", action="store_true", help="Also read again the texts a report would quote, and count them."
    )
    arguments = parser.parse_args(argv)
    try:
        return asyncio.run(_read(arguments))
    except (Refused, DomainError, ValueError, OSError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

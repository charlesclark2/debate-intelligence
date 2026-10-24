#!/usr/bin/env python3
"""Read Policy affirmative files' plan texts, and write the coach's plan-text sheet (`v1-e32-t09`).

Until `debate-research landscape report` (`v1-e32-t05`) reads plan texts as part of a report, this is
how the operator reads them for a snapshot and writes the coach's sheet. Three commands:

* **`plan-texts`** reads the caselist's parsed sources on the topic through the snapshot (the newest
  weekly one unless `--snapshot` names one), as `v1-e32-t02`'s classifier does, and reads every
  affirmative source's plan text from its own bytes in this machine's blob store, parsing only what
  the plan-text cache (`<data dir>/landscape/plan_texts/<caselist>.jsonl`) does not hold. It prints
  counts only: sources, cache hits, sources parsed, refused and unread, and the documents and teams
  of each verdict and of each aff named. It exits 1 when it read no affirmative source, so an empty
  store never looks like a run. The first run over a caselist parses every affirmative file: about
  0.3 s of a worker's time each, so a few minutes for hspolicy26 over the default workers.
* **`sheet`** does the same, then reads again the plan texts the sheet shows and writes
  `<topic id>-plan-texts.md` and `plan-text-answers.csv` to `--out`: plan texts clustered by the
  mechanism words that tell them apart, clusters fewer than two teams read withheld
  (:mod:`debate_core.arguments.landscape.plan_text_sheet`). Both hold the teams' own words, so `--out`
  must be outside the repository, and the script refuses a path inside it. It prints counts only.

* **`assign`** reads plan texts as `plan-texts` does, classifies the snapshot's cards as `v1-e32-t02`'s
  classifier does (which may rewrite that classifier's own cache and review queue under the data
  directory), and assigns each affirmative round its aff
  (:class:`~debate_core.application.aff_assignment.AffAssignmentService`), printing counts by method.
  `v1-e32-t05` builds the same assignments for the report; this command is how they are counted
  before it does.

None writes anything but the plan-text cache, the classifier's files for `assign`, and the two files
for `sheet`. No plan text, team, school or path is printed.

    uv run python scripts/assign_landscape_affs.py plan-texts --caselist hspolicy26
    uv run python scripts/assign_landscape_affs.py sheet --caselist hspolicy26 \\
        --out ~/Documents/debate/landscape-seed
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from debate_core.application.aff_assignment import AffAssignmentService
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.parse_workers import (
    InProcessParseRunner,
    ParseRunner,
    ProcessPoolParseRunner,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import DomainError
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.landscape_staleness import LandscapeStalenessCheck
from debate_core.application.plan_texts import PlanTextRun, PlanTextService
from debate_core.arguments.landscape.plan_text import PlanTextVerdict, PlanTextVocabulary
from debate_core.arguments.landscape.plan_text_sheet import (
    ANSWERS_FILE,
    DEFAULT_MINIMUM_TEAMS,
    PlanTextWords,
    cluster_plan_texts,
    render_plan_text_sheet,
    write_answers_csv,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side, SourceDocument
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.landscape.classification_store import LocalClassificationStore
from debate_core.integrations.landscape.plan_text_store import LocalPlanTextStore
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


def _outside_the_repository(path: Path, what: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise Refused(f"{what} must be outside the repository ({REPO_ROOT}): it holds the teams' own words")
    return resolved


@dataclass(frozen=True, slots=True)
class _Read:
    reading: SeedReading
    topic_id: str
    taxonomy_version: str
    through: date
    affirmative: tuple[SourceDocument, ...]
    teams: dict[str, frozenset[str]]
    """Each affirmative source's affirmative teams, as opaque identities."""
    run: PlanTextRun
    service: PlanTextService


@dataclass(frozen=True, slots=True)
class _Stores:
    data_dir: Path
    repository: YamlTaxonomyRepository
    local: LocalEvidence
    plan_texts: PlanTextService
    snapshot: date


async def _stores(arguments: argparse.Namespace) -> _Stores:
    data_dir = _outside_the_repository(arguments.data_dir, "--data-dir")
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
    runner: ParseRunner = (
        InProcessParseRunner()
        if arguments.workers == 0
        else ProcessPoolParseRunner(workers=arguments.workers, timeout_seconds=PER_FILE_TIMEOUT_SECONDS)
    )
    return _Stores(
        data_dir=data_dir,
        repository=YamlTaxonomyRepository.load(arguments.config_dir),
        local=local,
        plan_texts=PlanTextService(
            parser=DebateDocxParser(), runner=runner, store=LocalPlanTextStore(data_dir), local=local
        ),
        snapshot=snapshot,
    )


async def _read(arguments: argparse.Namespace) -> _Read:
    stores = await _stores(arguments)
    repository, local, snapshot = stores.repository, stores.local, stores.snapshot
    resolved = repository.resolve(arguments.caselist, snapshot)
    if resolved is None or resolved.taxonomy is None:
        raise Refused(f"topics.yaml puts {arguments.caselist} on {snapshot} on no topic with a taxonomy")
    reading = await read_seed_sources(
        store=LocalParsedStore(stores.data_dir),
        local=local,
        suppression=RecordedSuppressionList(local_suppression_list_file(stores.data_dir)),
        topic=resolved.topic,
        caselist=arguments.caselist,
        version=arguments.version,
        through=snapshot,
    )
    teams = {
        source.sha256: frozenset(
            team.identity for team in source.teams if team.side is Side.AFF and team.identity
        )
        for source in reading.sources
        if any(team.side is Side.AFF for team in source.teams)
    }
    documents = {
        one.sha256: one.source_document() for one in await enumerate_sources(local, arguments.caselist)
    }
    affirmative = tuple(documents[sha] for sha in sorted(teams) if sha in documents)
    print(
        f"Read {arguments.caselist} {reading.version} through {snapshot}: {len(reading.sources)} sources on "
        f"{resolved.topic.id}, {len(affirmative)} affirmative."
    )
    taxonomy = repository.taxonomy(resolved.topic.id)
    service = stores.plan_texts
    run = await service.read(arguments.caselist, affirmative, PlanTextVocabulary(taxonomy))
    return _Read(
        reading=reading,
        topic_id=resolved.topic.id,
        taxonomy_version=taxonomy.taxonomy_version,
        through=snapshot,
        affirmative=affirmative,
        teams=teams,
        run=run,
        service=service,
    )


def _print_plan_texts(read: _Read) -> None:
    counts = read.run.counts
    print(
        f"Plan texts: {counts.sources} sources, {counts.hits} cached, {counts.parsed} parsed, "
        f"{counts.refused} refused by the parser, {counts.unread} unread; cache "
        f"{'written' if counts.cache_written else 'unchanged'}."
    )
    by_verdict: dict[str, set[str]] = defaultdict(set)
    by_aff: dict[str, set[str]] = defaultdict(set)
    documents: Counter[str] = Counter()
    named: Counter[str] = Counter()
    for sha, verdict in read.run.verdicts.items():
        documents[verdict.verdict.value] += 1
        by_verdict[verdict.verdict.value].update(read.teams.get(sha, frozenset()))
        if verdict.verdict is PlanTextVerdict.NAMES and verdict.position_id is not None:
            named[verdict.position_id] += 1
            by_aff[verdict.position_id].update(read.teams.get(sha, frozenset()))
    for verdict in PlanTextVerdict:
        print(
            f"  {verdict.value}: {documents[verdict.value]} documents, {len(by_verdict[verdict.value])} teams"
        )
    for position_id, count in sorted(named.items(), key=lambda item: (-item[1], item[0])):
        print(f"  names {position_id}: {count} documents, {len(by_aff[position_id])} teams")


async def _plan_texts(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    read = await _read(arguments)
    if not read.affirmative:
        print("FAILED: 0 affirmative sources read; nothing was read for plan texts.", file=sys.stderr)
        return 1
    _print_plan_texts(read)
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


async def _assign(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    stores = await _stores(arguments)
    service = AffAssignmentService(
        store=LocalParsedStore(stores.data_dir),
        local=stores.local,
        suppression=RecordedSuppressionList(local_suppression_list_file(stores.data_dir)),
        taxonomies=stores.repository,
        classifications=LocalClassificationStore(stores.data_dir),
        plan_texts=stores.plan_texts,
    )
    found = await service.run(arguments.caselist, stores.snapshot, version=arguments.version)
    plan = found.plan_texts.counts if found.plan_texts is not None else None
    if plan is None or not plan.sources:
        print("FAILED: 0 affirmative sources read; no round was assigned.", file=sys.stderr)
        return 1
    print(
        f"Assigned {arguments.caselist} through {stores.snapshot}: plan texts of {plan.sources} affirmative "
        f"sources, {plan.hits} cached, {plan.parsed} parsed, {plan.refused} refused, {plan.unread} unread."
    )
    counts = found.counts
    methods = ", ".join(f"{method} {count}" for method, count in counts.by_method.items()) or "none"
    print(
        f"Aff rounds: {counts.rounds} by {found.aff_teams} teams; assigned {len(found.assignments)} "
        f"({methods}), left to placed cards {counts.placed_only}, unidentified {counts.unidentified} "
        f"({counts.conflicting} with conflicting plan texts)."
    )
    print(
        f"Carry refused into {counts.carry_refused} rounds; teams identified {found.identified_teams} of "
        f"{found.aff_teams}; {counts.teams_disagreeing} teams whose rounds disagree."
    )
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


async def _sheet(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    out = _outside_the_repository(arguments.out, "--out")
    read = await _read(arguments)
    if not read.affirmative:
        print("FAILED: 0 affirmative sources read; no sheet was written.", file=sys.stderr)
        return 1
    _print_plan_texts(read)
    found = await read.service.words(arguments.caselist, read.affirmative, read.run)
    items = [
        PlanTextWords(
            source_sha256=sha,
            teams=read.teams.get(sha, frozenset()),
            named=read.run.verdicts[sha].position_id,
            words=words,
        )
        for sha, words in found.words.items()
    ]
    sheet = cluster_plan_texts(
        items, CaselistNames(read.reading.caselist_names), minimum_teams=arguments.minimum_teams
    )
    out.mkdir(parents=True, exist_ok=True)
    sheet_path = out / f"{read.topic_id}-plan-texts.md"
    sheet_path.write_text(
        render_plan_text_sheet(
            sheet,
            caselist=arguments.caselist,
            taxonomy_version=read.taxonomy_version,
            through=read.through.isoformat(),
        ),
        encoding="utf-8",
    )
    buffer = io.StringIO(newline="")
    write_answers_csv(sheet, buffer)
    (out / ANSWERS_FILE).write_text(buffer.getvalue(), encoding="utf-8", newline="")
    print(
        f"Sheet: {sheet.documents} documents with a plan text by {sheet.teams} teams; "
        f"{len(sheet.clusters)} clusters shown, {sheet.withheld_clusters} withheld "
        f"({sheet.withheld_documents} documents) as read by fewer than {sheet.minimum_teams} teams; "
        f"{found.mismatched} read differently and {found.unread} unread, left off."
    )
    print(f"Wrote {sheet_path.name} and {ANSWERS_FILE} to {out}.")
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


def _common(command: argparse.ArgumentParser) -> None:
    command.add_argument("--caselist", required=True, help="The caselist slug.")
    command.add_argument(
        "--snapshot", type=date.fromisoformat, help="YYYY-MM-DD. Default: the newest weekly snapshot."
    )
    command.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="The data directory. Default: the dev one."
    )
    command.add_argument("--version", help="The parsed store's version directory. Default: the newest.")
    command.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Parser processes; 0 parses in this process. Default: {DEFAULT_WORKERS}.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml and taxonomies/. Default: config/landscape.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan_texts = commands.add_parser(
        "plan-texts", help="Read the affirmative files' plan texts and count them."
    )
    _common(plan_texts)
    assign = commands.add_parser("assign", help="Assign each affirmative round its aff, and count them.")
    _common(assign)
    sheet = commands.add_parser("sheet", help="Write the coach's plan-text sheet outside the repository.")
    _common(sheet)
    sheet.add_argument("--out", type=Path, required=True, help="The directory to write the sheet to.")
    sheet.add_argument(
        "--minimum-teams",
        type=int,
        default=DEFAULT_MINIMUM_TEAMS,
        help=f"Withhold a cluster fewer teams read. Default: {DEFAULT_MINIMUM_TEAMS}.",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "plan-texts":
            return asyncio.run(_plan_texts(arguments))
        if arguments.command == "assign":
            return asyncio.run(_assign(arguments))
        return asyncio.run(_sheet(arguments))
    except (Refused, DomainError, ValueError, OSError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

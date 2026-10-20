"""An older build's own code, reading what this build writes for cards with no tag (`v1-e31-t14`).

Not collected: its name is not a test module's, and it is only ever run by its path, in two steps.
It writes nothing outside the directory named by `CHECK_UNTAGGED_DIR` and pytest's temporary
directory.

1. **This build writes** (`CHECK_UNTAGGED=write`, run with this build's source): the four synthetic
   files of `test_untagged_cards_keep_the_order_of_tagged_cards.py`, two of whose seven cards have
   no tag, imported and parsed into a parsed card store; and the store's cards as `ParsedCard`
   JSONL, the input `caselist cards --parsed` reads. It prints the cards statistics this build
   reports. The data directory is copied to `CHECK_UNTAGGED_DIR`.
2. **An older build reads** (`CHECK_UNTAGGED=read`, with the older build's source first on
   `PYTHONPATH`): its parsed store reads every record of the copy, its `read_parsed_cards` reads the
   JSONL, its cards statistics report over the stored cards, and its parse pipeline runs over the
   copy as the weekly agent's pull does. A build with this parser version rebuilds this build's
   directory; one with an older parser version starts its own, beside it.

What it asks of a tag is `tag or None`, which means "no tag" in every build. The commands and what
they printed are in `docs/session-reports/v1-e31-t14-card-tag-optional.md`.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import debate_core
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService, read_parsed_cards
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.ports.parsed_store import SourceOutcome
from debate_core.domain.debate_files import ParsedCard
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore, SqliteDatabase
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes import build_fake_caselist_repository

pytestmark = pytest.mark.anyio

STEP = os.environ.get("CHECK_UNTAGGED", "")
COPY = Path(os.environ.get("CHECK_UNTAGGED_DIR", "/nonexistent"))
CASELIST = "testcl26"
CARDS_DIRECTORY = "parsed-cards"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def accepted(factory: Any, **arguments: Any) -> dict[str, Any]:
    """The arguments `factory`'s signature takes: an older build's has fewer."""
    named = inspect.signature(factory).parameters
    return {name: value for name, value in arguments.items() if name in named}


def parse_service(data_dir: Path) -> CaselistParseService:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return CaselistParseService(
        **accepted(
            CaselistParseService,
            local=LocalEvidence(
                objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
            ),
            store=LocalParsedStore(data_dir),
            parser=DebateDocxParser(),
            runner=InProcessParseRunner(),
            suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
            place_cards=CaselistCardStatsService(build_fake_caselist_repository()).place,
            failure_rate_threshold=1.0,
            failure_rate_minimum_sources=1,
        )
    )


async def stored_cards(data_dir: Path, version: str) -> list[ParsedCard]:
    store = LocalParsedStore(data_dir)
    cards: list[ParsedCard] = []
    for entry in await store.read_entries(CASELIST, version):
        if entry.outcome is not SourceOutcome.PARSED:
            continue
        record = await store.read_document(CASELIST, version, entry.source_sha256)
        assert record is not None
        cards.extend(record.to_parsed_document("synthetic.docx").cards)
    return cards


async def statistics(data_dir: Path, cards: list[ParsedCard]) -> str:
    """The clusters as `caselist cards` ranks them: short cite, tag or None, distinct teams."""
    repository = SqliteCaselistRepository(SqliteDatabase.open(data_dir))
    report = await CaselistCardStatsService(repository).report(cards, caselist=CASELIST, top=10)
    clusters = [
        (cluster.short_cite, cluster.tag or None, cluster.distinct_teams) for cluster in report.top_clusters
    ]
    untagged = sum(not occurrence.tag for occurrence in report.occurrences)
    return f"clusters {clusters}; {len(report.occurrences)} occurrences, {untagged} with no tag"


def load_world() -> ModuleType:
    """The ac3 test's four files and its store builder, loaded from beside this file."""
    path = Path(__file__).with_name("test_untagged_cards_keep_the_order_of_tagged_cards.py")
    spec = importlib.util.spec_from_file_location("untagged_cards_world", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(STEP != "write", reason="run with CHECK_UNTAGGED=write")
async def test_this_build_writes_a_store_holding_cards_with_no_tag(tmp_path: Path) -> None:
    world = load_world()
    data_dir = tmp_path / "evidence"
    await world.import_files(data_dir, tmp_path / "zips")
    await world.build_store(data_dir)
    cards = await stored_cards(data_dir, DOCX_PARSER_VERSION)
    (data_dir / CARDS_DIRECTORY).mkdir()
    (data_dir / CARDS_DIRECTORY / "cards.jsonl").write_text(
        "".join(card.model_dump_json() + "\n" for card in cards), encoding="utf-8"
    )
    print(
        f"\nwriter: {Path(debate_core.__file__).parent}\n"
        f"this build wrote {DOCX_PARSER_VERSION}: {len(cards)} cards, "
        f"{sum(card.tag is None for card in cards)} with tag None\n"
        f"this build's statistics: {await statistics(data_dir, cards)}"
    )
    if COPY.exists():
        shutil.rmtree(COPY)
    shutil.copytree(data_dir, COPY)


@pytest.mark.skipif(STEP != "read", reason="run with CHECK_UNTAGGED=read and an older build first")
async def test_the_build_on_the_path_reads_and_parses_this_builds_store(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    shutil.copytree(COPY, data_dir)
    print(f"\nreader: {Path(debate_core.__file__).parent}, parser {DOCX_PARSER_VERSION}")
    store = LocalParsedStore(data_dir)
    written = await store.version_directories(CASELIST)
    for version in written:
        entries = await store.read_entries(CASELIST, version)
        cards = await stored_cards(data_dir, version)
        index = await store.read_index(CASELIST, version)
        failures = await store.read_failures(CASELIST, version)
        occurrences = await store.read_occurrences(CASELIST, version)
        assert index is not None and failures is not None and occurrences is not None
        print(
            f"read {version}: {len(entries)} per-source files, {len(cards)} cards "
            f"({sum(not card.tag for card in cards)} with no tag), {len(index)} index rows, "
            f"{len(failures)} failure rows, {len(occurrences)} occurrence rows"
        )
        print(f"its statistics over them: {await statistics(data_dir, cards)}")

    from_jsonl = read_parsed_cards(data_dir / CARDS_DIRECTORY)
    untagged = sum(not card.tag for card in from_jsonl)
    print(
        f"read_parsed_cards: {len(from_jsonl)} cards ({untagged} with no tag); "
        f"statistics {await statistics(data_dir, from_jsonl)}"
    )

    service = parse_service(data_dir)
    plan = await service.plan(CASELIST)
    report = await service.run(plan)
    assert report.store is not None
    print(
        f"parse: wrote {plan.version} ({'new' if plan.new_version else 'this build’s, again'}), "
        f"{report.attempted} parsed, store {report.store.sources} sources, {report.store.cards} cards, "
        f"{report.store.occurrences} occurrences"
    )
    reparsed = await stored_cards(data_dir, plan.version)
    print(f"its statistics after its parse: {await statistics(data_dir, reparsed)}")

"""PlanTextService: plan texts read from the sources' own bytes, cached as derived fields (`v1-e32-t09`).

The PM's ruling of 2026-10-24: read the raw sources in this task, through the parser port, read-only,
with a local cache of derived fields only, never text. Every source here is a synthetic `.docx` built
in memory; every word in it is invented.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.plan_texts import PLAN_TEXT_SOURCE_PATH, PlanTextService
from debate_core.arguments.landscape.plan_text import DocumentPlanText, PlanTextVerdict, PlanTextVocabulary
from debate_core.domain.caselist import SnapshotDate, SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument, ParseFailure
from debate_core.domain.landscape import Taxonomy
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.landscape.plan_text_store import LocalPlanTextStore
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

CASELIST = "hspolicy26"
NAMED_PLAN = "The United States federal government should establish a sample plan."
UNNAMED_PLAN = "The United States federal government should establish a national program."


def _position(identifier: str, aliases: list[str]) -> dict[str, Any]:
    label = identifier.replace("-", " ").capitalize()
    return {"id": identifier, "label": label, "kind": "aff", "side": "aff", "aliases": aliases}


def vocabulary(*aliases: str) -> PlanTextVocabulary:
    return PlanTextVocabulary(
        Taxonomy.model_validate(
            {
                "topic_id": "sample-topic",
                "taxonomy_version": "1.0.0",
                "event": "POLICY",
                "positions": [_position("sample-plan-aff", list(aliases or ("sample plan",)))],
            }
        )
    )


def affirmative(plan: str) -> bytes:
    return build_docx(
        "".join(
            [
                paragraph_xml(run_xml("Plan"), style="Heading3"),
                paragraph_xml(run_xml(plan), style="Analytic"),
                paragraph_xml(run_xml("Costs rise"), style="Heading4"),
                paragraph_xml(
                    run_xml("Sample 26", character_style="Style13ptBold") + run_xml(" invented cite")
                ),
                paragraph_xml(run_xml("An invented body of evidence that goes on.", underline="single")),
            ]
        )
    )


def source_of(content: bytes, source_format: SourceFormat = SourceFormat.DOCX) -> SourceDocument:
    return SourceDocument(
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        source_format=source_format,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=date(2026, 10, 20),
        last_seen_snapshot=date(2026, 10, 20),
    )


@dataclass
class CountingParser:
    """The real parser, counting its calls and recording the paths it was given."""

    version: str = ""
    paths: list[str] = field(default_factory=list[str])
    inner: DebateDocxParser = field(default_factory=DebateDocxParser)

    @property
    def parser_version(self) -> str:
        return self.version or self.inner.parser_version

    @property
    def profile_version(self) -> str:
        return self.inner.profile_version

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        self.paths.append(source_path)
        return self.inner.parse(content, source, source_path=source_path, snapshot=snapshot, camp=camp)


@dataclass
class World:
    data_dir: Path
    parser: CountingParser = field(default_factory=CountingParser)

    def plant(self, content: bytes, *, blob: bytes | None = None) -> SourceDocument:
        source = source_of(content)
        sha = source.sha256
        path = self.data_dir / "blobs" / "sha256" / sha[:2] / sha[2:4] / sha
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if blob is None else blob)
        return source

    @property
    def cache_file(self) -> Path:
        return self.data_dir / "landscape" / "plan_texts" / f"{CASELIST}.jsonl"

    def service(self) -> PlanTextService:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return PlanTextService(
            parser=self.parser,
            runner=InProcessParseRunner(),
            store=LocalPlanTextStore(self.data_dir),
            local=LocalEvidence(
                objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
            ),
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


@pytest.mark.anyio
async def test_a_source_s_plan_text_is_read_from_its_bytes(world: World) -> None:
    named = world.plant(affirmative(NAMED_PLAN))
    unnamed = world.plant(affirmative(UNNAMED_PLAN))
    run = await world.service().read(CASELIST, [named, unnamed], vocabulary())
    assert run.verdicts == {
        named.sha256: DocumentPlanText(PlanTextVerdict.NAMES, "sample-plan-aff"),
        unnamed.sha256: DocumentPlanText(PlanTextVerdict.UNNAMED),
    }
    (found,) = run.readings[named.sha256]
    assert (found.element_index, found.kept, found.shaped) == (1, False, True)
    counts = run.counts
    assert (counts.sources, counts.hits, counts.parsed, counts.cache_written) == (2, 0, 2, True)
    assert counts.verdicts == {"NAMES": 1, "UNNAMED": 1}


@pytest.mark.anyio
async def test_a_second_run_parses_nothing_and_writes_nothing(world: World) -> None:
    sources = [world.plant(affirmative(NAMED_PLAN)), world.plant(affirmative(UNNAMED_PLAN))]
    first = await world.service().read(CASELIST, sources, vocabulary())
    written = world.cache_file.read_bytes()
    calls = len(world.parser.paths)
    again = await world.service().read(CASELIST, sources, vocabulary())
    assert len(world.parser.paths) == calls
    assert (again.counts.hits, again.counts.parsed, again.counts.cache_written) == (2, 0, False)
    assert again.verdicts == first.verdicts
    assert again.readings == first.readings
    assert world.cache_file.read_bytes() == written


@pytest.mark.anyio
async def test_new_words_read_every_source_again_and_drop_the_old_readings(world: World) -> None:
    source = world.plant(affirmative("The United States federal government should establish a new plan."))
    before = await world.service().read(CASELIST, [source], vocabulary())
    after = await world.service().read(CASELIST, [source], vocabulary("sample plan", "new plan"))
    assert before.verdicts[source.sha256] == DocumentPlanText(PlanTextVerdict.UNNAMED)
    assert after.verdicts[source.sha256] == DocumentPlanText(PlanTextVerdict.NAMES, "sample-plan-aff")
    assert (after.counts.hits, after.counts.parsed) == (0, 1)
    assert len(world.cache_file.read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.anyio
async def test_a_new_parser_version_reads_every_source_again(world: World) -> None:
    source = world.plant(affirmative(NAMED_PLAN))
    await world.service().read(CASELIST, [source], vocabulary())
    world.parser.version = "2099.01.01-docx-99"
    again = await world.service().read(CASELIST, [source], vocabulary())
    assert (again.counts.hits, again.counts.parsed, again.parser_version) == (0, 1, "2099.01.01-docx-99")


@pytest.mark.anyio
async def test_readings_of_sources_not_in_this_run_are_kept(world: World) -> None:
    one = world.plant(affirmative(NAMED_PLAN))
    two = world.plant(affirmative(UNNAMED_PLAN))
    await world.service().read(CASELIST, [one, two], vocabulary())
    await world.service().read(CASELIST, [one], vocabulary())
    again = await world.service().read(CASELIST, [two], vocabulary())
    assert (again.counts.hits, again.counts.parsed) == (1, 0)


@pytest.mark.anyio
async def test_a_refused_source_is_unread_and_not_parsed_again(world: World) -> None:
    broken = world.plant(b"not a zip at all, invented bytes")
    run = await world.service().read(CASELIST, [broken], vocabulary())
    assert run.verdicts == {broken.sha256: DocumentPlanText(PlanTextVerdict.UNREAD)}
    assert (run.counts.refused, run.counts.unread, run.counts.cache_written) == (1, 0, True)
    calls = len(world.parser.paths)
    again = await world.service().read(CASELIST, [broken], vocabulary())
    assert len(world.parser.paths) == calls
    assert (again.counts.hits, again.counts.refused) == (1, 1)


@pytest.mark.anyio
async def test_a_missing_blob_is_unread_not_cached_and_tried_again(world: World) -> None:
    content = affirmative(NAMED_PLAN)
    source = source_of(content)
    missing = await world.service().read(CASELIST, [source], vocabulary())
    assert missing.verdicts == {source.sha256: DocumentPlanText(PlanTextVerdict.UNREAD)}
    assert (missing.counts.unread, missing.counts.cache_written) == (1, False)
    world.plant(content)
    found = await world.service().read(CASELIST, [source], vocabulary())
    assert found.verdicts[source.sha256].verdict is PlanTextVerdict.NAMES


@pytest.mark.anyio
async def test_a_blob_that_does_not_hash_to_its_name_is_unread(world: World) -> None:
    source = world.plant(affirmative(NAMED_PLAN), blob=affirmative(UNNAMED_PLAN))
    run = await world.service().read(CASELIST, [source], vocabulary())
    assert run.verdicts == {source.sha256: DocumentPlanText(PlanTextVerdict.UNREAD)}
    assert run.counts.unread == 1
    assert world.parser.paths == []


@pytest.mark.anyio
async def test_the_parser_never_gets_a_disclosure_path(world: World) -> None:
    await world.service().read(CASELIST, [world.plant(affirmative(NAMED_PLAN))], vocabulary())
    assert world.parser.paths == [PLAN_TEXT_SOURCE_PATH]


@pytest.mark.anyio
async def test_the_cache_holds_no_word_of_any_source(world: World) -> None:
    await world.service().read(
        CASELIST, [world.plant(affirmative(NAMED_PLAN)), world.plant(affirmative(UNNAMED_PLAN))], vocabulary()
    )
    written = world.cache_file.read_text(encoding="utf-8").casefold()
    for word in ("sample plan", "national program", "costs rise", "invented"):
        assert word not in written


def no_plan() -> bytes:
    return build_docx(paragraph_xml(run_xml("Advantage One"), style="Heading3"))


@pytest.mark.anyio
async def test_the_sheet_s_words_are_read_again_only_from_sources_with_a_plan_text(world: World) -> None:
    named = world.plant(affirmative(NAMED_PLAN))
    unnamed = world.plant(affirmative(UNNAMED_PLAN))
    without = world.plant(no_plan())
    service = world.service()
    run = await service.read(CASELIST, [named, unnamed, without], vocabulary())
    calls = len(world.parser.paths)
    found = await service.words(CASELIST, [named, unnamed, without], run)
    assert len(world.parser.paths) == calls + 2
    assert found.words == {
        named.sha256: tuple(NAMED_PLAN.casefold().rstrip(".").split()),
        unnamed.sha256: tuple(UNNAMED_PLAN.casefold().rstrip(".").split()),
    }
    assert (found.parsed, found.without_plan_text, found.mismatched, found.unread) == (2, 1, 0, 0)


@pytest.mark.anyio
async def test_a_source_that_reads_differently_from_its_reading_is_left_off(world: World) -> None:
    source = world.plant(affirmative(NAMED_PLAN))
    service = world.service()
    run = await service.read(CASELIST, [source], vocabulary())
    (reading,) = run.readings[source.sha256]
    changed = dataclasses.replace(
        run, readings={source.sha256: (dataclasses.replace(reading, digest="0" * 64),)}
    )
    found = await service.words(CASELIST, [source], changed)
    assert (found.words, found.mismatched) == ({}, 1)


@pytest.mark.anyio
async def test_reading_the_words_writes_nothing(world: World) -> None:
    source = world.plant(affirmative(NAMED_PLAN))
    service = world.service()
    run = await service.read(CASELIST, [source], vocabulary())
    before = sorted(path.relative_to(world.data_dir) for path in world.data_dir.rglob("*"))
    written = world.cache_file.read_bytes()
    await service.words(CASELIST, [source], run)
    assert sorted(path.relative_to(world.data_dir) for path in world.data_dir.rglob("*")) == before
    assert world.cache_file.read_bytes() == written

"""A landscape dry run fills the plan-text and analytic-text caches, and writes nothing else (`v1-e32-t30`).

The PM's ruling of 2026-10-31: both caches are keyed on the parser version, so the first report after a
parser bump reads every on-topic source again. A dry run may now write those two caches, and nothing
else `v1-e32-t05`'s rule covers, so the publish after it reads none of those sources again.

`synthetic26` (:mod:`debate_core.testing.landscape_run`) is the world: of its four sources only
`aff-two`'s bytes are in the blob store, a `Plan` heading over one plan text, so `aff-two` is the one
source either cache can read. The other three are not in the blob store and are never parsed. The
services are the real ones, over the real parser under a version each test sets, counting the sources
it is given.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from debate_core.application.aff_assignment import AffAssignmentService
from debate_core.application.analytic_texts import AnalyticTextService
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_run import (
    LandscapeRunRequest,
    LandscapeRunResult,
    LandscapeRunService,
    PublishAction,
)
from debate_core.application.landscape_scan import ScanAcceptanceLog
from debate_core.application.plan_texts import PlanTextService
from debate_core.domain.caselist import SnapshotDate, SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.landscape.analytic_text_store import LocalAnalyticTextStore
from debate_core.integrations.landscape.classification_store import LocalClassificationStore
from debate_core.integrations.landscape.plan_text_store import LocalPlanTextStore
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.landscape_run import (
    SYNTHETIC_RUN_CASELIST,
    SYNTHETIC_RUN_TODAY,
    SyntheticRun,
    plant_synthetic_run,
)

pytestmark = pytest.mark.anyio

CASELIST = SYNTHETIC_RUN_CASELIST
OLD_PARSER = "2026.10.20-docx-6"
NEW_PARSER = "2026.10.27-docx-7"
TEXT_CACHES = {
    Path("landscape") / "plan_texts" / f"{CASELIST}.jsonl",
    Path("landscape") / "analytic_texts" / f"{CASELIST}.jsonl",
}
PLAN_TEXT = "The United States federal government should establish single payer health insurance."
"""`aff-two`'s plan text, as `synthetic26` writes it into the file's bytes: evidence text."""


@dataclass
class ReadCountingParser:
    """The real parser under a version the test sets, recording each source it is given."""

    version: str
    reads: list[str] = field(default_factory=list[str])
    inner: DebateDocxParser = field(default_factory=DebateDocxParser)

    @property
    def parser_version(self) -> str:
        return self.version

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
        self.reads.append(source.sha256)
        return self.inner.parse(content, source, source_path=source_path, snapshot=snapshot, camp=camp)


@dataclass
class TextWorld:
    """`synthetic26`, a bucket, and one counting parser for each cache."""

    run: SyntheticRun
    bucket: FsEvidenceObjectStore
    plans: ReadCountingParser = field(default_factory=lambda: ReadCountingParser(OLD_PARSER))
    texts: ReadCountingParser = field(default_factory=lambda: ReadCountingParser(OLD_PARSER))

    @property
    def data_dir(self) -> Path:
        return self.run.data_dir

    def bump(self, version: str) -> None:
        """The parser bump: both caches' readings are now of another version, and the counts start again."""
        for parser in (self.plans, self.texts):
            parser.version = version
            parser.reads.clear()

    def reads(self) -> tuple[list[str], list[str]]:
        return list(self.plans.reads), list(self.texts.reads)

    def service(self) -> LandscapeRunService:
        data_dir = self.data_dir
        objects = FsEvidenceObjectStore(data_dir)
        blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
        local = LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        )
        taxonomies = YamlTaxonomyRepository.load(self.run.config_dir)
        suppression = RecordedSuppressionList(local_suppression_list_file(data_dir))
        classifications = LocalClassificationStore(data_dir)
        runner = InProcessParseRunner()
        return LandscapeRunService(
            taxonomies=taxonomies,
            config_dir=self.run.config_dir,
            parsed_store=LocalParsedStore(data_dir),
            local=local,
            suppression=suppression,
            classifications=classifications,
            objects=objects,
            run_log=None,
            reports_dir=data_dir / "reports" / "landscape",
            acceptances=ScanAcceptanceLog(data_dir / "landscape" / "scan-acceptances"),
            today=lambda: SYNTHETIC_RUN_TODAY,
            bucket=lambda: self.bucket,
            aff_assignments=AffAssignmentService(
                store=LocalParsedStore(data_dir),
                local=local,
                suppression=suppression,
                taxonomies=taxonomies,
                classifications=classifications,
                plan_texts=PlanTextService(
                    parser=self.plans, runner=runner, store=LocalPlanTextStore(data_dir), local=local
                ),
            ),
            analytic_texts=AnalyticTextService(
                parser=self.texts, runner=runner, store=LocalAnalyticTextStore(data_dir), local=local
            ),
        )


@pytest.fixture
def world(tmp_path: Path) -> TextWorld:
    return TextWorld(plant_synthetic_run(tmp_path), FsEvidenceObjectStore(tmp_path / "bucket"))


async def _run(world: TextWorld, **request: object) -> LandscapeRunResult:
    return await world.service().run(LandscapeRunRequest(caselist=CASELIST, **request))  # pyright: ignore[reportArgumentType]


def _blob_digests(data_dir: Path) -> list[str]:
    """Every source whose bytes are on this machine: here, `aff-two` alone."""
    return sorted(path.name for path in (data_dir / "blobs").rglob("*") if path.is_file())


def _listing(root: Path) -> dict[Path, str]:
    """Every file under `root`, by its path under it, with the SHA-256 of its bytes."""
    return {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _cache_lines(data_dir: Path) -> list[str]:
    return [
        line
        for cache in sorted(TEXT_CACHES)
        for line in (data_dir / cache).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def test_the_publish_after_a_dry_run_on_a_new_parser_version_reads_no_source_the_dry_run_read(
    world: TextWorld,
) -> None:
    (aff_two,) = _blob_digests(world.data_dir)
    first = await _run(world)
    assert world.reads() == ([aff_two], [aff_two]), "the report on the old parser filled both caches"
    world.bump(NEW_PARSER)

    dry = await _run(world, publish=True, dry_run=True)

    assert world.reads() == ([aff_two], [aff_two]), "a new parser version reads the source again"
    world.bump(NEW_PARSER)

    published = await _run(world, publish=True)

    assert world.reads() == ([], []), "the publish read no source: both caches held the dry run's readings"
    assert dry.analytic_texts is not None and dry.plan_texts is not None
    assert (dry.plan_texts.parsed, dry.plan_texts.cache_written) == (1, True)
    assert (dry.analytic_texts.read.parsed, dry.analytic_texts.read.cache_written) == (1, True)
    assert published.plan_texts is not None and published.analytic_texts is not None
    # Of the two affirmative and four on-topic sources, `aff-two` is the one with bytes to read.
    assert (published.plan_texts.sources, published.plan_texts.hits, published.plan_texts.parsed) == (2, 1, 0)
    read = published.analytic_texts.read
    assert (read.sources, read.hits, read.parsed) == (4, 1, 0)
    assert published.publish is not None
    assert {one.action for one in published.publish.planned} == {PublishAction.UPLOAD}
    assert len(published.publish.uploaded) == 7
    # The same report the old parser's run counted: the bump changed which version read the file only.
    assert published.aff_assignments == first.aff_assignments == 1


async def test_every_text_cache_entry_after_the_dry_run_is_the_new_parser_versions(world: TextWorld) -> None:
    await _run(world)
    world.bump(NEW_PARSER)

    await _run(world, dry_run=True)

    lines = _cache_lines(world.data_dir)
    assert len(lines) == 2, "one entry in each cache: `aff-two`'s, the old one dropped"
    assert {json.loads(line)["parser_version"] for line in lines} == {NEW_PARSER}


async def test_a_dry_run_writes_nothing_but_the_two_text_caches(world: TextWorld) -> None:
    before = _listing(world.data_dir)

    result = await _run(world, publish=True, dry_run=True)

    after = _listing(world.data_dir)
    assert set(after) - set(before) == TEXT_CACHES
    assert {path for path in before if after.get(path) != before[path]} == set(), "nothing changed or removed"
    assert result.classification.counts.cache_written is False
    assert result.classification.review_queue_location == "(not written: dry run)"
    assert not result.written
    assert await world.bucket.list_objects("") == ()


async def test_a_dry_run_over_caches_it_already_filled_writes_nothing_at_all(world: TextWorld) -> None:
    await _run(world, dry_run=True)
    before = _listing(world.data_dir)

    again = await _run(world, dry_run=True)

    assert _listing(world.data_dir) == before
    assert again.plan_texts is not None and again.analytic_texts is not None
    assert (again.plan_texts.cache_written, again.analytic_texts.read.cache_written) == (False, False)


async def test_no_text_cache_entry_holds_evidence_text(world: TextWorld) -> None:
    await _run(world, dry_run=True)

    held = "\n".join(_cache_lines(world.data_dir))
    assert held, "both caches were written"
    assert PLAN_TEXT not in held
    for word in ("United", "federal", "government", "establish", "health", "insurance"):
        assert word not in held, word

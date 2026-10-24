"""LandscapeRunService on `synthetic26`, the caselist :mod:`debate_core.testing.landscape_run` plants.

Every expected count here was worked out by hand from the table in that module's docstring (working
agreement 6): four sources by three teams in two weekly snapshots, nine cards, seven of them under a
heading an alias names. The "bucket" is a second filesystem store: the same port the S3 adapter
implements, and the CLI's tests run the same publish against moto.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_report import round_id
from debate_core.application.landscape_run import (
    BUNDLE_FILES,
    AffAssignmentsFromReading,
    LandscapeRunRequest,
    LandscapeRunResult,
    LandscapeRunService,
    ModelBudgetExceeded,
    NothingToReport,
    NoTopicMapping,
    PositionClassifier,
    PublishAction,
    PublishRefusal,
    UnknownCaselist,
    UnknownSnapshot,
)
from debate_core.application.landscape_scan import ScanAcceptanceLog, ScanKind, hits_digest
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.landscape_staleness import STALE_BANNER_HEADING
from debate_core.application.ports.classification_store import ClassificationStore
from debate_core.application.position_classification import ClassificationRun, PositionClassificationService
from debate_core.application.sync_runs import SYNC_RUN_LOG_FILENAME, SyncRunLog, SyncRunRecord
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import PositionClassification
from debate_core.domain.landscape_report import AffAssignment
from debate_core.integrations.landscape.classification_store import (
    LocalClassificationStore,
    review_queue_path,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.landscape_run import (
    SYNTHETIC_RUN_CASELIST,
    SYNTHETIC_RUN_TODAY,
    SYNTHETIC_RUN_TOPIC,
    SyntheticRun,
    plant_synthetic_run,
)
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

pytestmark = pytest.mark.anyio

CASELIST = SYNTHETIC_RUN_CASELIST
NEWEST = date(2026, 9, 15)
PLANTED_CODE = {("neg-two", 0): "As PX argued, new spending triggers a crowd-out"}
"""`PX` is Harrowgate Prep's code, planted in the tag of a spending card every report lists."""


def _service(
    world: SyntheticRun,
    *,
    bucket: FsEvidenceObjectStore | None = None,
    run_log: SyncRunLog | None = None,
    aff_assignments: AffAssignmentsFromReading | None = None,
    classifier: object = None,
) -> LandscapeRunService:
    data_dir = world.data_dir
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    taxonomies = YamlTaxonomyRepository.load(world.config_dir)
    return LandscapeRunService(
        taxonomies=taxonomies,
        config_dir=world.config_dir,
        parsed_store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        classifications=LocalClassificationStore(data_dir),
        objects=objects,
        run_log=run_log,
        reports_dir=data_dir / "reports" / "landscape",
        acceptances=ScanAcceptanceLog(data_dir / "landscape" / "scan-acceptances"),
        today=lambda: SYNTHETIC_RUN_TODAY,
        bucket=(lambda: bucket) if bucket is not None else None,
        aff_assignments=aff_assignments,
        classifier=classifier,  # pyright: ignore[reportArgumentType]
    )


@pytest.fixture
def world(tmp_path: Path) -> SyntheticRun:
    return plant_synthetic_run(tmp_path)


@pytest.fixture
def bucket(tmp_path: Path) -> FsEvidenceObjectStore:
    return FsEvidenceObjectStore(tmp_path / "bucket")


async def _run(service: LandscapeRunService, **request: object) -> LandscapeRunResult:
    return await service.run(LandscapeRunRequest(caselist=CASELIST, **request))  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------------------------------------------
# The run: resolve, classify, build, write (ac1)
# ------------------------------------------------------------------------------------------------


async def test_a_run_writes_the_four_files_under_the_newest_snapshot_and_counts_the_cards(
    world: SyntheticRun,
) -> None:
    result = await _run(_service(world))

    directory = world.data_dir / "reports" / "landscape" / CASELIST / "2026-09-15"
    assert result.snapshot == NEWEST
    assert result.directory == directory
    assert result.files == tuple(directory / name for name in BUNDLE_FILES)
    assert sorted(path.name for path in directory.iterdir()) == [
        "impact_cards.csv",
        "positions.csv",
        "report.md",
        "top_cards.csv",
    ]
    assert (result.topic_id, result.taxonomy_version, result.overrides_digest) == (
        SYNTHETIC_RUN_TOPIC,
        "1.0.0",
        "none",
    )
    counts = result.classification.counts
    assert (counts.sources, counts.cards) == (4, 9)
    assert counts.cards_by_method == {"ALIAS": 7, "UNPLACED": 2}
    assert result.model_calls == 0
    assert result.written and result.publish is None
    stats = {one.position_id: (one.rounds, one.teams) for one in result.report.positions}
    assert stats == {
        "single-payer-aff": (1, 1),
        "costs-advantage": (2, 2),
        "spending-da": (2, 2),
        "states-cp": (1, 1),
    }
    assert [(card.position_id, card.rank, card.teams_reading) for card in result.report.top_cards] == [
        ("single-payer-aff", 1, 1),
        ("costs-advantage", 1, 2),
        ("spending-da", 1, 2),
        ("spending-da", 2, 1),
        ("states-cp", 1, 1),
    ]
    assert review_queue_path(world.data_dir, CASELIST, SYNTHETIC_RUN_TOPIC).is_file()
    assert result.scan.hits == () and result.scan.pending == ()


async def test_a_named_snapshot_reads_the_store_as_it_stood_then(world: SyntheticRun) -> None:
    result = await _run(_service(world), snapshot=date(2026, 9, 8))

    assert result.directory.name == "2026-09-08"
    assert result.classification.counts.sources == 2
    assert {one.position_id: one.rounds for one in result.report.positions}["spending-da"] == 1


async def test_a_second_run_reads_every_card_from_the_cache(world: SyntheticRun) -> None:
    service = _service(world)
    await _run(service)
    second = await _run(service)

    assert second.classification.counts.misses == 0
    assert second.classification.counts.hits == second.classification.counts.lookups > 0


async def test_out_writes_the_bundle_where_it_is_told(world: SyntheticRun, tmp_path: Path) -> None:
    result = await _run(_service(world), out=tmp_path / "elsewhere")

    assert result.directory == tmp_path / "elsewhere"
    assert sorted(path.name for path in (tmp_path / "elsewhere").iterdir()) == sorted(BUNDLE_FILES)
    assert not (world.data_dir / "reports").exists()


# ------------------------------------------------------------------------------------------------
# Refusals (ac2)
# ------------------------------------------------------------------------------------------------


async def test_an_unknown_caselist_is_refused_with_the_known_ones(world: SyntheticRun) -> None:
    with pytest.raises(UnknownCaselist) as refused:
        await _service(world).run(LandscapeRunRequest(caselist="hsnope26"))

    assert refused.value.known == (CASELIST,)
    assert not (world.data_dir / "reports").exists()


async def test_an_unknown_snapshot_is_refused_with_the_known_ones(world: SyntheticRun) -> None:
    with pytest.raises(UnknownSnapshot) as refused:
        await _run(_service(world), snapshot=date(2026, 9, 9))

    assert refused.value.known == ("2026-09-08", "2026-09-15")


async def test_a_snapshot_no_topic_covers_is_refused_naming_topics_yaml(world: SyntheticRun) -> None:
    PlantedCaselist(world.data_dir, CASELIST).source(
        "early", [PlantedCard(("1NC", "Spending DA"))], disclosures=[("2026-08-25", "A/B/A-B-Neg.docx")]
    )

    with pytest.raises(NoTopicMapping) as refused:
        await _run(_service(world), snapshot=date(2026, 8, 25))

    assert refused.value.file_to_edit == str(world.config_dir / "topics.yaml")
    assert "on no topic" in str(refused.value)


async def test_a_topic_with_no_taxonomy_is_refused_naming_topics_yaml(world: SyntheticRun) -> None:
    PlantedCaselist(world.data_dir, "synthld26").source(
        "ld", [PlantedCard(("AC", "Value"))], disclosures=[("2026-09-15", "A/B/A-B-Aff.docx")]
    )

    with pytest.raises(NoTopicMapping) as refused:
        await _service(world).run(LandscapeRunRequest(caselist="synthld26"))

    assert refused.value.file_to_edit == str(world.config_dir / "topics.yaml")
    assert "ld-synthetic-topic, which has no taxonomy" in str(refused.value)


async def test_a_snapshot_with_no_parsed_source_on_the_topic_is_no_report(tmp_path: Path) -> None:
    world = plant_synthetic_run(tmp_path)
    for path in (world.data_dir / "parsed").rglob("*.jsonl"):
        path.unlink()

    with pytest.raises(NothingToReport):
        await _run(_service(world))
    assert not (world.data_dir / "reports").exists()


class _SendsToTheModel:
    """`v1-e32-t02`'s classifier, reporting that it sent `items` to a model, as `v1-e32-t07`'s would."""

    def __init__(self, inner: PositionClassifier, items: int) -> None:
        self._inner = inner
        self._items = items

    async def classify(self, reading: SeedReading) -> ClassificationRun:
        run = await self._inner.classify(reading)
        counts = dataclasses.replace(run.counts, model_items=self._items, model_calls=1)
        return dataclasses.replace(run, counts=counts)


async def test_a_stage_over_the_model_budget_is_refused_after_the_queue_and_before_the_report(
    world: SyntheticRun, bucket: FsEvidenceObjectStore
) -> None:
    taxonomies = YamlTaxonomyRepository.load(world.config_dir)

    def classifier(store: ClassificationStore) -> PositionClassifier:
        return _SendsToTheModel(PositionClassificationService(taxonomies=taxonomies, store=store), items=1)

    with pytest.raises(ModelBudgetExceeded) as refused:
        await _run(_service(world, bucket=bucket, classifier=classifier), publish=True)

    assert (refused.value.sent, refused.value.allowed) == (1, 0)
    assert review_queue_path(world.data_dir, CASELIST, SYNTHETIC_RUN_TOPIC).is_file()
    assert not (world.data_dir / "reports").exists()
    assert await bucket.list_objects("") == ()


# ------------------------------------------------------------------------------------------------
# Staleness and the aff seam
# ------------------------------------------------------------------------------------------------


async def test_a_run_the_download_cap_held_back_makes_the_report_stale(world: SyntheticRun) -> None:
    log = SyncRunLog(world.data_dir / SYNC_RUN_LOG_FILENAME)
    started = datetime(2026, 9, 16, 6, tzinfo=UTC)
    log.append(
        SyncRunRecord(
            run_id="20260916T060000Z",
            environment="dev",
            mode="run",
            started_at=started,
            finished_at=started,
            outcome="completed",  # pyright: ignore[reportArgumentType]
            caselists=(CASELIST,),
            archives_deferred=2,
            deferred_by_caselist={CASELIST: 2},
        )
    )

    result = await _run(_service(world, run_log=log))

    assert result.staleness.cap_bound and result.staleness.age_days == 2
    assert result.report.header.stale
    assert (result.directory / "report.md").read_text(encoding="utf-8").startswith(STALE_BANNER_HEADING)


async def test_without_the_run_log_the_same_store_reads_as_current(world: SyntheticRun) -> None:
    result = await _run(_service(world, run_log=None))

    assert not result.report.header.stale


class _PlanTextFor:
    """Assigns `aff-two`'s round the single payer aff, as `v1-e32-t09` would from its plan text."""

    def __init__(self) -> None:
        self.asked: list[tuple[date, int, str, bool]] = []

    async def assignments(
        self,
        *,
        reading: SeedReading,
        through: date,
        classifications: Sequence[PositionClassification],
        taxonomy: Taxonomy,
        writes: bool,
    ) -> Sequence[AffAssignment]:
        self.asked.append((through, len(classifications), taxonomy.taxonomy_version, writes))
        return [
            AffAssignment(round_id=round_id(one), position_id="single-payer-aff", method="PLAN_TEXT")
            for one in reading.disclosures
            if one.side is Side.AFF and one.tournament == "Thistle Open"
        ]


async def test_the_aff_seam_passes_t09s_assignments_to_the_report(world: SyntheticRun) -> None:
    source = _PlanTextFor()
    result = await _run(_service(world, aff_assignments=source))

    assert source.asked == [(NEWEST, 21, "1.0.0", True)]
    assert result.aff_assignments == 1
    assert {(one.method, one.rounds) for one in result.report.aff_identification} == {
        ("PLAN_TEXT", 1),
        ("PLACED_CARD", 1),
    }
    assert {one.position_id: one.rounds for one in result.report.positions}["single-payer-aff"] == 2


async def test_a_dry_run_asks_the_aff_source_not_to_write(world: SyntheticRun) -> None:
    source = _PlanTextFor()
    result = await _run(_service(world, aff_assignments=source), dry_run=True)

    assert [asked[3] for asked in source.asked] == [False]
    assert result.aff_assignments == 1


async def test_without_an_aff_source_the_report_shows_the_unidentified_share(world: SyntheticRun) -> None:
    result = await _run(_service(world))

    assert result.aff_assignments == 0
    assert (result.report.unclassified.aff_rounds, result.report.unclassified.aff_rounds_unidentified) == (
        2,
        1,
    )


# ------------------------------------------------------------------------------------------------
# Publishing (ac3) and the dry run
# ------------------------------------------------------------------------------------------------

KEYS = tuple(f"reports/landscape/{CASELIST}/2026-09-15/{name}" for name in BUNDLE_FILES)


async def test_publish_puts_the_bundle_under_the_reports_prefix(
    world: SyntheticRun, bucket: FsEvidenceObjectStore
) -> None:
    result = await _run(_service(world, bucket=bucket), publish=True)

    assert result.publish is not None and result.publish.refused is None
    assert result.publish.uploaded == KEYS
    assert tuple(info.key for info in await bucket.list_objects("")) == tuple(sorted(KEYS))
    for name, key in zip(BUNDLE_FILES, KEYS, strict=True):
        stored = bucket.path_for(key).read_bytes()
        assert stored == (result.directory / name).read_bytes()


async def test_a_second_identical_publish_uploads_nothing(
    world: SyntheticRun, bucket: FsEvidenceObjectStore
) -> None:
    service = _service(world, bucket=bucket)
    await _run(service, publish=True)
    second = await _run(service, publish=True)

    assert second.publish is not None
    assert second.publish.uploaded == ()
    assert second.publish.unchanged == KEYS


async def test_a_changed_file_is_the_only_one_uploaded_again(
    world: SyntheticRun, bucket: FsEvidenceObjectStore
) -> None:
    service = _service(world, bucket=bucket)
    await _run(service, publish=True)
    stale = world.data_dir / "stand-in.md"
    stale.write_text("an older report\n", encoding="utf-8")
    await bucket.put_file(KEYS[2], stale)

    second = await _run(service, publish=True)

    assert second.publish is not None and second.publish.uploaded == (KEYS[2],)


async def test_a_dry_run_lists_the_planned_uploads_and_writes_nothing(
    world: SyntheticRun, bucket: FsEvidenceObjectStore
) -> None:
    result = await _run(_service(world, bucket=bucket), publish=True, dry_run=True)

    assert result.publish is not None
    assert [(one.key, one.action) for one in result.publish.planned] == [
        (key, PublishAction.UPLOAD) for key in KEYS
    ]
    assert result.publish.uploaded == () and not result.written
    assert await bucket.list_objects("") == ()
    assert not (world.data_dir / "reports").exists()
    assert not (world.data_dir / "landscape").exists()
    assert result.classification.review_queue_location == "(not written: dry run)"
    assert result.classification.counts.misses > 0
    assert result.classification.counts.cache_written is False


async def test_a_dry_run_after_a_publish_plans_nothing_to_upload(
    world: SyntheticRun, bucket: FsEvidenceObjectStore
) -> None:
    service = _service(world, bucket=bucket)
    await _run(service, publish=True)
    result = await _run(service, publish=True, dry_run=True)

    assert result.publish is not None
    assert {one.action for one in result.publish.planned} == {PublishAction.UNCHANGED}


async def test_a_dry_run_without_publish_names_the_keys_and_asks_no_bucket(world: SyntheticRun) -> None:
    result = await _run(_service(world), dry_run=True)

    assert result.publish is not None
    assert [(one.key, one.action) for one in result.publish.planned] == [(key, None) for key in KEYS]


# ------------------------------------------------------------------------------------------------
# The scan before sharing (the PM's rulings of 2026-10-24)
# ------------------------------------------------------------------------------------------------


async def test_the_scan_lists_a_planted_team_code_with_its_line(tmp_path: Path) -> None:
    world = plant_synthetic_run(tmp_path, planted_tags=PLANTED_CODE)
    result = await _run(_service(world))

    assert [(hit.file, hit.kind, hit.term) for hit in result.scan.hits] == [
        ("top_cards.csv", ScanKind.TEAM_CODE, "PX")
    ]
    assert "As PX argued" in result.scan.hits[0].line
    assert result.scan.pending == result.scan.hits
    assert result.scan.digest == hits_digest(result.scan.hits)


async def test_publish_with_a_hit_nobody_accepted_is_refused_and_writes_locally(tmp_path: Path) -> None:
    world = plant_synthetic_run(tmp_path, planted_tags=PLANTED_CODE)
    bucket = FsEvidenceObjectStore(tmp_path / "bucket")
    result = await _run(_service(world, bucket=bucket), publish=True)

    assert result.publish is not None
    assert result.publish.refused is PublishRefusal.SCAN_HITS_NOT_ACCEPTED
    assert result.publish.uploaded == ()
    assert await bucket.list_objects("") == ()
    assert (result.directory / "top_cards.csv").is_file()
    assert not (world.data_dir / "landscape" / "scan-acceptances").exists()


async def test_publish_with_the_digest_of_the_hits_goes_ahead_and_records_them(tmp_path: Path) -> None:
    world = plant_synthetic_run(tmp_path, planted_tags=PLANTED_CODE)
    bucket = FsEvidenceObjectStore(tmp_path / "bucket")
    service = _service(world, bucket=bucket)
    digest = (await _run(service)).scan.digest

    result = await _run(service, publish=True, accept_scan_hits=digest)

    assert result.publish is not None and result.publish.refused is None
    assert result.publish.uploaded == KEYS
    assert result.scan.accepted_now
    log = ScanAcceptanceLog(world.data_dir / "landscape" / "scan-acceptances")
    assert log.accepted(CASELIST) == {hit.key for hit in result.scan.hits}


async def test_a_digest_of_other_hits_is_stale_and_refused(tmp_path: Path) -> None:
    world = plant_synthetic_run(tmp_path, planted_tags=PLANTED_CODE)
    bucket = FsEvidenceObjectStore(tmp_path / "bucket")
    service = _service(world, bucket=bucket)
    read_earlier = (await _run(service)).scan.digest
    plant_synthetic_run(tmp_path, planted_tags={**PLANTED_CODE, ("neg-one", 2): "QW says the states can"})

    result = await _run(service, publish=True, accept_scan_hits=read_earlier)

    assert result.publish is not None
    assert result.publish.refused is PublishRefusal.SCAN_DIGEST_STALE
    assert result.publish.uploaded == () and await bucket.list_objects("") == ()
    assert result.scan.digest != read_earlier
    assert not result.scan.accepted_now


async def test_a_later_run_stops_only_on_hits_not_yet_accepted(tmp_path: Path) -> None:
    world = plant_synthetic_run(tmp_path, planted_tags=PLANTED_CODE)
    bucket = FsEvidenceObjectStore(tmp_path / "bucket")
    service = _service(world, bucket=bucket)
    first = await _run(service)
    await _run(service, publish=True, accept_scan_hits=first.scan.digest)

    again = await _run(service, publish=True)
    assert again.publish is not None and again.publish.refused is None
    assert again.scan.pending == () and len(again.scan.hits) == 1

    plant_synthetic_run(tmp_path, planted_tags={**PLANTED_CODE, ("neg-one", 2): "QW says the states can"})
    later = await _run(service, publish=True)
    assert later.publish is not None and later.publish.refused is PublishRefusal.SCAN_HITS_NOT_ACCEPTED
    assert [hit.term for hit in later.scan.pending] == ["QW"]
    assert len(later.scan.hits) == 2


async def test_a_dry_run_records_no_acceptance(tmp_path: Path) -> None:
    world = plant_synthetic_run(tmp_path, planted_tags=PLANTED_CODE)
    bucket = FsEvidenceObjectStore(tmp_path / "bucket")
    service = _service(world, bucket=bucket)
    digest = (await _run(service, dry_run=True)).scan.digest

    result = await _run(service, publish=True, dry_run=True, accept_scan_hits=digest)

    assert result.publish is not None and result.publish.refused is None
    assert not result.scan.accepted_now
    assert not (world.data_dir / "landscape" / "scan-acceptances").exists()

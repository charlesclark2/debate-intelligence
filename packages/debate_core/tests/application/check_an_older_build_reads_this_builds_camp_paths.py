"""An earlier build's own code, reading the camp store and built camp file this build writes (`v1-e33-t07`).

Not collected: its name is not a test module's, and it is only ever run by its path, in three steps.
It writes nothing outside the directory named by `CHECK_CAMP_PATHS_DIR` and pytest's temporary
directory, and the bucket is moto's.

1. **This build writes** (`CHECK_CAMP_PATHS=write`, run with this build): one synthetic camp file in
   two releases, `2031-policy` at two paths and `2032-policy` at a third, parsed into `openev`, so the
   version directory holds `occurrences.jsonl` and `camp_paths.jsonl`. Then a recipe pinning the
   file's two cards, one in each release, built by `files build`'s service, so `files/built/` holds the
   `.docx`, its sidecar, the `.camp-paths.json` beside it and the quality report. The data directory
   is copied to `CHECK_CAMP_PATHS_DIR`.
2. **An earlier build reads** (`CHECK_CAMP_PATHS=read`, with that build installed): its parsed store
   reads every file of the copy, record by record; its resolver resolves the recipe; its publisher
   publishes the `openev` version directory to moto; its `files check` and `files publish` read the
   built file and its sidecar; and its parse pipeline runs over the copy, as the weekly agent's pull
   does, rewriting the aggregates it knows. The copy it leaves is written back to
   `CHECK_CAMP_PATHS_DIR/after-the-earlier-build`.
3. **This build reads what the earlier build left** (`CHECK_CAMP_PATHS=reread`): the table the earlier
   build rewrote, with this build's `camp_paths.jsonl` still beside it.

The commands and what they printed are in `docs/session-reports/v1-e33-t07-camp-path-on-occurrence-rows.md`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
import yaml

import debate_core
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.file_build_service import BuildFileRequest, FileBuildService
from debate_core.application.file_publish_service import FilePublishService, PublishRequest
from debate_core.application.file_quality_service import FileQualityService
from debate_core.application.file_recipes import RecipeResolver, load_recipe
from debate_core.application.ports.parsed_store import SourceOutcome
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    camp_path_disclosure,
)
from debate_core.domain.caselist import CampFile, Event
from debate_core.domain.file_provenance import FileProvenanceManifest
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository, build_fake_caselist_repository

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STEP = os.environ.get("CHECK_CAMP_PATHS", "")
COPY = Path(os.environ.get("CHECK_CAMP_PATHS_DIR", "/nonexistent"))
AFTER_THE_EARLIER_BUILD = "after-the-earlier-build"

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
CAMP_FILE: Final = (
    REPO_ROOT / "tests/fixtures/debate_files/structural/cardmirror-camp-file.docx"
).read_bytes()
SHA: Final = hashlib.sha256(CAMP_FILE).hexdigest()
CAMP: Final = "Lanternfield Institute"
RELEASES: Final = {
    "2031-policy": ("openev-512-Synthetic_Grid_CP.docx", "openev-513-Synthetic_Grid_CP.docx"),
    "2032-policy": ("openev-640-Synthetic_Grid_CP.docx",),
}
BUILT: Final = Path("files/built/synthetic-topic/synthetic-camp-file.docx")
RECIPE: Final = Path("files/recipes/synthetic-topic/synthetic-camp-file.yaml")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def accepted(factory: Any, **arguments: Any) -> dict[str, Any]:
    """The arguments `factory`'s signature takes: an earlier build's may have fewer."""
    named = inspect.signature(factory).parameters
    return {name: value for name, value in arguments.items() if name in named}


def local_evidence(data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def suppression(data_dir: Path) -> RecordedSuppressionList:
    return RecordedSuppressionList(local_suppression_list_file(data_dir))


def parse_service(data_dir: Path) -> CaselistParseService:
    return CaselistParseService(
        **accepted(
            CaselistParseService,
            local=local_evidence(data_dir),
            store=LocalParsedStore(data_dir),
            parser=DebateDocxParser(),
            runner=InProcessParseRunner(),
            suppression=suppression(data_dir),
            place_cards=CaselistCardStatsService(build_fake_caselist_repository()).place,
            failure_rate_threshold=1.0,
            failure_rate_minimum_sources=1,
        )
    )


async def camp_records() -> InMemoryCaselistRepository:
    """What the OpenEv importer records for each release: invented camp, title and years."""
    records = InMemoryCaselistRepository()
    for release in RELEASES:
        await records.record_camp_file(
            CampFile(
                source_sha256=SHA,
                camp=CAMP,
                year=int(release[:4]),
                event=Event.POLICY,
                file_title="Synthetic Grid CP",
                snapshot=date(2026, 7, 30),
            )
        )
    return records


def quality(data_dir: Path) -> FileQualityService:
    return FileQualityService(
        parser=DebateDocxParser(), snapshots=FsSnapshotStore(data_dir), suppression=suppression(data_dir)
    )


def describe(path: Path) -> str:
    return f"{path.name} {hashlib.sha256(path.read_bytes()).hexdigest()[:12]}"


@pytest.mark.skipif(STEP != "write", reason="run with CHECK_CAMP_PATHS=write")
async def test_this_build_writes_a_camp_store_and_a_built_camp_file(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    blob = data_dir / "blobs" / "sha256" / SHA[0:2] / SHA[2:4] / SHA
    blob.parent.mkdir(parents=True)
    blob.write_bytes(CAMP_FILE)
    for release, paths in RELEASES.items():
        manifest = data_dir / "objects" / "manifests" / "openev" / f"{release}.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "kind": "member",
                "classification": "NEW",
                "path": path,
                "sha256": SHA,
                "byte_size": len(CAMP_FILE),
                "format": "DOCX",
                "camp": CAMP,
                "imported_on": "2026-07-30",
            }
            for path in paths
        ]
        manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    service = parse_service(data_dir)
    report = await service.run(await service.plan("openev"))
    assert report.store is not None

    store = LocalParsedStore(data_dir)
    rows = await store.read_occurrences("openev", DOCX_PARSER_VERSION)
    assert rows is not None
    by_release = {row.snapshot: row for row in rows}
    cards = sorted({(row.first_element_index, row.exact_fingerprint) for row in rows})
    recipe = data_dir / RECIPE
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "title": "Synthetic camp file",
                "topic": "synthetic-topic",
                "format": "POLICY",
                "caselist": "openev",
                "position": "synthetic-position",
                "side": "NEG",
                "fingerprint_version": FINGERPRINT_VERSION,
                "status": "ready",
                "structure": [
                    {
                        "pocket": "Synthetic pocket",
                        "blocks": [
                            {
                                "block": "Synthetic block",
                                "items": [
                                    {
                                        "fingerprint": fingerprint,
                                        "pin": {
                                            "caselist": "openev",
                                            "source_sha256": SHA,
                                            "element_index": element,
                                            "snapshot": release,
                                        },
                                    }
                                    for (element, fingerprint), release in zip(cards, RELEASES, strict=True)
                                ],
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    blobs = FsSnapshotStore(data_dir)
    parser = DebateDocxParser()
    builder = FileBuildService(
        parsed_store=store,
        caselists=await camp_records(),
        suppression=suppression(data_dir),
        blobs=blobs,
        writer=DocxEvidenceFileWriter(snapshots=blobs, parser=parser),
        quality=quality(data_dir),
        parser_version=parser.parser_version,
        profile_version=parser.profile_version,
        files_dir=data_dir / "files",
        clock=lambda: datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
    )
    built = await builder.build(BuildFileRequest(recipe))
    assert built.files is not None, (built.refusal, built.recipe_errors)
    directory = data_dir / "parsed" / "openev" / DOCX_PARSER_VERSION
    print(
        f"\nwriter: {Path(debate_core.__file__).parent}\n"
        f"this build wrote parsed/openev/{DOCX_PARSER_VERSION}: {len(rows)} occurrence rows, releases "
        f"{sorted(by_release)}, camp paths per row "
        f"{sorted({len(one.camp_path_disclosures) for one in rows})}; "
        + ", ".join(
            describe(directory / name) for name in sorted(os.listdir(directory)) if name.endswith(".jsonl")
        )
        + f"\nthis build built {built.status}: "
        + ", ".join(describe(path) for path in sorted((data_dir / BUILT).parent.iterdir()))
    )
    if COPY.exists():
        shutil.rmtree(COPY)
    shutil.copytree(data_dir, COPY)


@pytest.mark.skipif(STEP != "read", reason="run with CHECK_CAMP_PATHS=read and an earlier build installed")
async def test_an_earlier_build_reads_resolves_checks_publishes_and_parses_this_builds_files(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    data_dir = tmp_path / "evidence"
    shutil.copytree(COPY, data_dir, ignore=shutil.ignore_patterns(AFTER_THE_EARLIER_BUILD))
    directory = data_dir / "parsed" / "openev" / DOCX_PARSER_VERSION
    print(f"\nreader: {Path(debate_core.__file__).parent}, parser {DOCX_PARSER_VERSION}")
    table_before = (directory / "occurrences.jsonl").read_bytes()

    store = LocalParsedStore(data_dir)
    entries = await store.read_entries("openev", DOCX_PARSER_VERSION)
    documents = [
        await store.read_document("openev", DOCX_PARSER_VERSION, entry.source_sha256)
        for entry in entries
        if entry.outcome is SourceOutcome.PARSED
    ]
    index = await store.read_index("openev", DOCX_PARSER_VERSION)
    failures = await store.read_failures("openev", DOCX_PARSER_VERSION)
    occurrences = await store.read_occurrences("openev", DOCX_PARSER_VERSION)
    stamps = await store.read_occurrence_stamps("openev", DOCX_PARSER_VERSION)
    assert None not in documents and index is not None and failures is not None and occurrences is not None
    print(
        f"its parsed store read: {len(entries)} per-source file(s), {len(documents)} document(s), "
        f"{len(index)} index row(s), {len(failures)} failure row(s), {len(occurrences)} occurrence row(s), "
        f"stamps {sorted(stamps or ())}"
    )

    loaded = load_recipe((data_dir / RECIPE).read_text(encoding="utf-8"))
    assert loaded.recipe is not None
    resolver = RecipeResolver(
        parsed_store=store,
        caselists=await camp_records(),
        suppression=suppression(data_dir),
        parser_version=DOCX_PARSER_VERSION,
    )
    resolved = await resolver.resolve(loaded.recipe, lines=loaded.lines)
    print(
        "its resolver: "
        + ", ".join(f"{card.resolution.value} {card.occurrence.snapshot}" for card in resolved.cards)
        + f"; errors {[str(error.code) for error in resolved.errors]}"
    )
    assert resolved.errors == ()

    bucket = S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)
    parsed = FsEvidenceObjectStore(data_dir, subdirectory=Path("parsed"))
    publisher = ParsedStorePublisher(
        **accepted(
            ParsedStorePublisher,
            local=parsed,
            local_path_for=parsed.path_for,
            remote=bucket,
            suppression=suppression(data_dir),
            evidence=local_evidence(data_dir),
        )
    )
    published = await publisher.publish("openev", DOCX_PARSER_VERSION)
    keys = sorted(
        str(item.get("Key")).rsplit("/", 1)[-1]
        for item in s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="parsed/").get("Contents", [])
        if not str(item.get("Key")).endswith(f"{SHA}.jsonl")
    )
    print(
        f"its publisher: succeeded {published.succeeded}, "
        + ", ".join(f"{result.value} {published.count(result)}" for result in SourceResult)
        + f"; aggregates in the bucket {keys}"
    )
    assert published.succeeded

    docx = data_dir / BUILT
    sidecar = FileProvenanceManifest.model_validate_json(
        docx.with_name(f"{docx.name}.provenance.json").read_bytes()
    )
    checked = await quality(data_dir).check(docx)
    print(
        f"its sidecar model read {len(sidecar.cards)} card(s), "
        f"releases {[one.snapshot for one in sidecar.cards]}; "
        f"its files check: {checked.report.status}"
    )
    assert str(checked.report.status) == "PASS"
    publish = FilePublishService(
        **accepted(
            FilePublishService, bucket=lambda: bucket, quality=quality(data_dir), files_dir=data_dir / "files"
        )
    )
    outcome = (await publish.run(PublishRequest(docx))).outcomes[0]
    print(f"its files publish: {outcome.status}, refusal {outcome.refusal.code if outcome.refusal else None}")
    assert str(outcome.status) == "PUBLISHED"

    await suppression(data_dir).append(
        [
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=SHA,
                disclosure=camp_path_disclosure("2032-policy", RELEASES["2032-policy"][0]),
                recorded_at=datetime(2026, 10, 31, 13, 0, tzinfo=UTC),
                reason=ReasonCode.REQUESTED_BY_CAMP,
                request_id="RM-2026-07",
            )
        ]
    )
    flagged = await quality(data_dir).check(docx)
    print(
        "its files check after 2032-policy's camp path is withdrawn: "
        + ", ".join(
            f"card {result.card_position} {result.status}"
            for result in flagged.report.results
            if result.check.name == "SUPPRESSION"
        )
    )

    service = parse_service(data_dir)
    plan = await service.plan("openev")
    report = await service.run(plan)
    assert report.store is not None
    table_after = (directory / "occurrences.jsonl").read_bytes()
    print(
        f"its parse: wrote {plan.version} ({'new' if plan.new_version else 'this build’s, again'}), "
        f"{report.attempted} parsed, {report.store.occurrences} occurrence rows; the table's bytes "
        f"{'unchanged' if table_after == table_before else 'changed'}; camp_paths.jsonl "
        f"{'still beside it' if (directory / 'camp_paths.jsonl').exists() else 'gone'}"
    )
    target = COPY / AFTER_THE_EARLIER_BUILD
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(data_dir, target)


@pytest.mark.skipif(STEP != "reread", reason="run with CHECK_CAMP_PATHS=reread after the read step")
async def test_this_build_reads_what_the_earlier_build_left() -> None:
    data_dir = COPY / AFTER_THE_EARLIER_BUILD
    rows = await LocalParsedStore(data_dir).read_occurrences("openev", DOCX_PARSER_VERSION)
    assert rows is not None
    by_release: dict[str, set[int]] = {}
    for row in rows:
        by_release.setdefault(row.snapshot, set()).add(len(row.camp_path_disclosures))
    loaded = load_recipe((data_dir / RECIPE).read_text(encoding="utf-8"))
    assert loaded.recipe is not None
    resolved = await RecipeResolver(
        parsed_store=LocalParsedStore(data_dir),
        caselists=await camp_records(),
        suppression=suppression(data_dir),
        parser_version=DOCX_PARSER_VERSION,
    ).resolve(loaded.recipe, lines=loaded.lines)
    print(
        f"\nreader: {Path(debate_core.__file__).parent}\n"
        f"this build read the table the earlier build rewrote: {len(rows)} rows, camp paths per row by "
        f"release {dict(sorted((release, sorted(counts)) for release, counts in by_release.items()))}\n"
        "this build's resolver, with 2032-policy's camp path withdrawn and no rebuild of its own: "
        + ", ".join(f"PINNED {card.occurrence.snapshot}" for card in resolved.cards)
        + "; errors "
        + ", ".join(f"{error.code} at {error.path}" for error in resolved.errors)
    )

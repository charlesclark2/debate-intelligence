"""FilePublishService: the quality gate, the `files/` layout, idempotence and the lookup (`v1-e33-t05`).

Each file is built by the real :class:`~debate_core.application.file_build_service.FileBuildService`
(the E31 parser, the lossless writer and the quality checks) from synthetic sources, into `tmp_path`,
which is in no git working tree, and published to moto's bucket through the real
:class:`~debate_core.integrations.s3.S3EvidenceObjectStore` (`tests/fixtures/moto_evidence_bucket.py`).
Nothing reaches AWS: moto answers botocore in-process and sockets are disabled.

Every expected key, status and refusal is written by hand from the recipe each test writes (working
agreement 6). Every school, team code, tournament and card is invented.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jsonschema
import pytest
import yaml

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.file_build_service import (
    BuildFileRequest,
    BuildStatus,
    FileBuildResult,
    FileBuildService,
)
from debate_core.application.file_publish_service import (
    STRIPPED_PIN_FIELDS,
    FilePublishService,
    FileRefusalCode,
    PublishedObjectMismatch,
    PublishRequest,
    PublishResult,
    PublishStatus,
    published_recipe,
)
from debate_core.application.file_quality_service import FileQualityService
from debate_core.application.file_recipes import RecipeResolver, load_recipe
from debate_core.application.file_suggest_service import CP_TEXT_SLOT
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.domain.built_file_metadata import BuiltFileMetadata
from debate_core.domain.caselist import Side
from debate_core.domain.file_provenance import FileProvenanceManifest
from debate_core.domain.file_recipe import FileRecipe
from debate_core.evidence.file_checks.report import QualityCheck
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord
from debate_core.testing.file_builder import DEFAULT_DISCLOSURE, FileBuilderWorld, SyntheticDisclosure

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

PARSER: Final = DebateDocxParser()
BUILT_AT: Final = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
CASELIST: Final = "hspolicy26"
TOPIC: Final = "synthetic-topic"
SCHEMA: Final = Path(__file__).resolve().parents[4] / "docs" / "data" / "built-file-metadata.schema.json"

CEDAR: Final = SyntheticDisclosure(
    school="Cedar Hollow",
    team_code="ZaLu",
    side=Side.NEG,
    tournament="Lakeshore Classic",
    round="Semis",
    path="Cedar Hollow/ZaLu/neg-lakeshore-semis.docx",
)


def card_xml(tag: str, short_cite: str | None, rest: str, lead: str, read: str) -> str:
    cite = (run_xml(short_cite, character_style="Style13ptBold") if short_cite else "") + run_xml(rest)
    return (
        paragraph_xml(run_xml(tag), style="Heading4")
        + paragraph_xml(cite)
        + paragraph_xml(
            run_xml(lead, half_points=16)
            + run_xml(read, character_style="StyleUnderline", highlight="cyan")
            + run_xml(" and the rest follows.", half_points=16)
        )
    )


SOURCE_ONE: Final = build_docx(
    card_xml(
        "Moratoria raise prices for every ratepayer",
        "Lindqvist 26",
        ", Senior Fellow, Synthetic Energy Review, 2026",
        "A moratorium ",
        "freezes supply",
    )
)
SOURCE_TWO: Final = build_docx(
    card_xml(
        "Data centres bring tax revenue",
        "Achterberg 26",
        ", Economist, Synthetic Fiscal Review, 2026",
        "Each campus ",
        "pays more in property tax",
    )
)
SOURCE_THREE: Final = build_docx(
    card_xml(
        "Grid operators shed load first",
        "Okonkwo 25",
        ", Grid Analyst, Synthetic Utility Quarterly, 2025",
        "Operators ",
        "shed load",
    )
)
#: A card whose cite has no short cite: `cite-present` warns, and nothing fails.
SOURCE_WITHOUT_A_SHORT_CITE: Final = build_docx(
    card_xml(
        "Water use rises with every campus",
        None,
        "Marsh, Hydrologist, Synthetic Water Review, 2026",
        "Cooling ",
        "draws on the aquifer",
    )
)


class RecordingBucket:
    """The real S3 store, with every `put_file` key recorded in order; one key's digest can be made to lie."""

    def __init__(self, inner: S3EvidenceObjectStore) -> None:
        self.inner = inner
        self.puts: list[str] = []
        self.lie_on_put: str | None = None
        self.lie_on_head: str | None = None

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self.inner.list_objects(prefix)

    async def head(self, key: str) -> ObjectInfo:
        info = await self.inner.head(key)
        if key == self.lie_on_head:
            return ObjectInfo(key=info.key, size=info.size, sha256="0" * 64)
        return info

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        self.puts.append(key)
        stored = await self.inner.put_file(key, source)
        if key == self.lie_on_put:
            return ObjectInfo(key=stored.key, size=stored.size, sha256="0" * 64)
        return stored

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        return await self.inner.get_file(key, destination)


@dataclass
class World:
    """One caselist's parsed store, records and blobs; a build service and a publish service over them."""

    root: Path
    bucket: RecordingBucket
    client: S3Client
    bucket_name: str
    files: FileBuilderWorld = field(default_factory=lambda: FileBuilderWorld(parser=PARSER))
    store: InMemoryParsedStore = field(default_factory=InMemoryParsedStore)
    caselists: InMemoryCaselistRepository = field(default_factory=InMemoryCaselistRepository)
    record: InMemoryAppendOnlyRecord = field(default_factory=lambda: InMemoryAppendOnlyRecord("suppression"))
    rows: list[OccurrenceRecord] = field(default_factory=lambda: [])
    bucket_built: int = 0

    @property
    def suppression(self) -> RecordedSuppressionList:
        return RecordedSuppressionList(self.record)

    @property
    def files_dir(self) -> Path:
        return self.root / "files"

    def add(self, content: bytes, disclosure: SyntheticDisclosure | None = DEFAULT_DISCLOSURE) -> str:
        """Add a source with one card; its fingerprint."""
        (card,) = asyncio.run(self.files.add_source(content, disclosure=disclosure))
        self.rows.append(card.occurrence)
        if card.disclosure is not None:
            asyncio.run(self.caselists.record_disclosure(card.disclosure))
        asyncio.run(
            self.store.write_aggregates(
                CASELIST, PARSER.parser_version, index=(), failures=(), occurrences=self.rows
            )
        )
        return card.fingerprint

    def source_of(self, fingerprint: str) -> str:
        return next(row.source_sha256 for row in self.rows if row.exact_fingerprint == fingerprint)

    def quality(self) -> FileQualityService:
        return FileQualityService(parser=PARSER, snapshots=self.files.snapshots, suppression=self.suppression)

    def recipe(
        self, items: Sequence[Mapping[str, Any]], *, name: str = "synthetic-file", status: str = "ready"
    ) -> Path:
        """A recipe of one pocket and one block, at `<files>/recipes/<topic>/<name>.yaml`, the default."""
        document = {
            "schema_version": 1,
            "title": "Synthetic file",
            "topic": TOPIC,
            "format": "POLICY",
            "caselist": CASELIST,
            "position": "synthetic-position",
            "side": "AFF",
            "fingerprint_version": FINGERPRINT_VERSION,
            "status": status,
            "structure": [
                {"pocket": "Synthetic pocket", "blocks": [{"block": "Synthetic block", "items": list(items)}]}
            ],
        }
        path = self.files_dir / "recipes" / TOPIC / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# a coach's note about Maple Grove QX\n" + yaml.safe_dump(document, sort_keys=False))
        return path

    def build(self, recipe: Path, *, allow_draft: bool = False) -> FileBuildResult:
        service = FileBuildService(
            parsed_store=self.store,
            caselists=self.caselists,
            suppression=self.suppression,
            blobs=self.files.snapshots,
            writer=DocxEvidenceFileWriter(snapshots=self.files.snapshots, parser=PARSER),
            quality=self.quality(),
            parser_version=PARSER.parser_version,
            profile_version=PARSER.profile_version,
            files_dir=self.files_dir,
            clock=lambda: BUILT_AT,
        )
        built = asyncio.run(service.build(BuildFileRequest(recipe, allow_draft=allow_draft)))
        assert built.status is BuildStatus.BUILT, (built.refusal, built.failing_checks)
        assert built.files is not None
        return built

    def built(self, *items: Mapping[str, Any], name: str = "synthetic-file") -> Path:
        result = self.build(self.recipe(list(items), name=name))
        assert result.files is not None
        return result.files.docx

    def service(self) -> FilePublishService:
        def bucket() -> EvidenceObjectStore:
            self.bucket_built += 1
            return self.bucket

        return FilePublishService(bucket=bucket, quality=self.quality(), files_dir=self.files_dir)

    def publish(self, path: Path, **request: Any) -> PublishResult:
        return asyncio.run(self.service().run(PublishRequest(path, **request)))

    def object_keys(self) -> list[str]:
        listed = self.client.list_objects_v2(Bucket=self.bucket_name).get("Contents", [])
        return sorted(str(one.get("Key")) for one in listed)

    def versions(self) -> int:
        return len(self.client.list_object_versions(Bucket=self.bucket_name).get("Versions", []))

    def body(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket_name, Key=key)["Body"].read()

    def suppress(self, source_sha256: str) -> None:
        entry = SuppressionEntry(
            action=SuppressionAction.SUPPRESS,
            sha256=source_sha256,
            recorded_at=datetime(2026, 10, 25, tzinfo=UTC),
            reason=ReasonCode.REQUESTED_BY_TEAM,
            request_id="RM-2026-09",
        )
        asyncio.run(self.suppression.append([entry]))

    def unsuppress(self, source_sha256: str) -> None:
        entry = SuppressionEntry(
            action=SuppressionAction.UNSUPPRESS,
            sha256=source_sha256,
            recorded_at=datetime(2026, 10, 25, 1, tzinfo=UTC),
            reason=ReasonCode.REMOVED_IN_ERROR,
            request_id="RM-2026-09",
        )
        asyncio.run(self.suppression.append([entry]))

    @staticmethod
    def sidecar_of(docx: Path) -> bytes:
        return docx.with_name(f"{docx.name}.provenance.json").read_bytes()


@pytest.fixture
def world(tmp_path: Path, evidence_bucket: str, s3_client: S3Client) -> World:
    store = S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)
    return World(root=tmp_path, bucket=RecordingBucket(store), client=s3_client, bucket_name=evidence_bucket)


def recipe_hash_of(docx: Path) -> str:
    sidecar = FileProvenanceManifest.model_validate_json(
        docx.with_name(f"{docx.name}.provenance.json").read_bytes()
    )
    return sidecar.recipe_hash


def prefix_of(docx: Path, slug: str = "synthetic-file") -> str:
    return f"files/synthetic-topic/aff/synthetic-position/{slug}/{recipe_hash_of(docx)[:12]}/"


def only(result: PublishResult) -> Any:
    (outcome,) = result.outcomes
    return outcome


# ------------------------------------------------------------------------------------------------
# ac2: five objects under files/<topic>/<side>/<position>/<slug>/<hash12>/, metadata.json last
# ------------------------------------------------------------------------------------------------


def test_a_pass_file_publishes_five_objects_under_its_prefix_metadata_last(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)}, {"fingerprint": world.add(SOURCE_TWO)})
    prefix = prefix_of(docx)

    outcome = only(world.publish(docx))

    expected = [
        f"{prefix}synthetic-file.docx",
        f"{prefix}synthetic-file.docx.provenance.json",
        f"{prefix}synthetic-file.docx.quality.json",
        f"{prefix}recipe.yaml",
        f"{prefix}metadata.json",
    ]
    assert outcome.status is PublishStatus.PUBLISHED
    assert list(outcome.written) == expected
    assert world.bucket.puts == expected
    assert world.object_keys() == sorted(expected)
    assert world.body(expected[0]) == docx.read_bytes()
    assert world.body(expected[1]) == docx.with_name("synthetic-file.docx.provenance.json").read_bytes()


def test_the_metadata_validates_against_the_committed_schema_and_names_the_file(world: World) -> None:
    one, two = world.add(SOURCE_ONE), world.add(SOURCE_TWO, CEDAR)
    docx = world.built({"fingerprint": one}, {"fingerprint": two})
    world.publish(docx)

    document = json.loads(world.body(f"{prefix_of(docx)}metadata.json"))

    jsonschema.validate(document, json.loads(SCHEMA.read_text(encoding="utf-8")))
    sources = sorted([world.source_of(one), world.source_of(two)])
    assert {key: document[key] for key in ("title", "topic", "format", "caselist", "position", "side")} == {
        "title": "Synthetic file",
        "topic": "synthetic-topic",
        "format": "POLICY",
        "caselist": "hspolicy26",
        "position": "synthetic-position",
        "side": "AFF",
    }
    assert (document["card_count"], document["quality_status"], document["recipe_status"]) == (
        2,
        "PASS",
        "ready",
    )
    assert document["recipe_hash"] == recipe_hash_of(docx)
    assert document["built_at"] == "2026-10-24T12:00:00.000000Z"
    assert document["docx_sha256"] == hashlib.sha256(docx.read_bytes()).hexdigest()
    assert document["caselists"] == ["hspolicy26"]
    assert document["source_sha256s"] == sources
    assert document["sources"] == [
        {"caselist": "hspolicy26", "snapshot": "2026-09-15", "source_sha256": sha} for sha in sources
    ]


def test_nothing_published_names_a_school_or_team_code_outside_the_sidecar(world: World) -> None:
    """The metadata, the recipe and the quality report carry none; the sidecar is where the policy allows."""
    one = world.add(SOURCE_ONE)
    pin = {
        "caselist": CASELIST,
        "source_sha256": world.source_of(one),
        "element_index": 0,
        "school": "Maple Grove",
        "team_code": "QX",
        "tournament": "Riverbend Invitational",
        "round": "Round 4",
    }
    docx = world.built({"fingerprint": one, "pin": pin})
    world.publish(docx)

    for key in world.object_keys():
        named = any(word in world.body(key) for word in (b"Maple Grove", b"QX", b"Riverbend", b"Round 4"))
        assert named == key.endswith(".provenance.json"), key


# ------------------------------------------------------------------------------------------------
# ac1 and ac8: missing, stale, FAIL or draft is refused before any upload; a warning never blocks
# ------------------------------------------------------------------------------------------------


def test_a_file_with_no_quality_report_is_refused_and_nothing_is_uploaded(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    docx.with_name("synthetic-file.docx.quality.json").unlink()

    outcome = only(world.publish(docx))

    assert outcome.status is PublishStatus.REFUSED
    assert outcome.refusal.code is FileRefusalCode.QUALITY_REPORT_MISSING
    assert world.object_keys() == [] and world.bucket_built == 0


def test_a_quality_report_for_other_bytes_is_stale_and_refused(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    docx.write_bytes(docx.read_bytes() + b"\0")

    outcome = only(world.publish(docx))

    assert outcome.refusal.code is FileRefusalCode.QUALITY_REPORT_STALE
    assert world.object_keys() == [] and world.bucket_built == 0


def test_a_file_whose_report_fails_is_refused_naming_the_failing_checks(world: World) -> None:
    one = world.add(SOURCE_ONE)
    docx = world.built({"fingerprint": one})
    world.suppress(world.source_of(one))
    asyncio.run(world.quality().check(docx))

    outcome = only(world.publish(docx))

    assert outcome.refusal.code is FileRefusalCode.QUALITY_FAILED
    assert outcome.refusal.failing_checks == (QualityCheck.SUPPRESSION,)
    assert "as its quality report records it" in outcome.refusal.message
    assert world.object_keys() == [] and world.bucket_built == 0


def test_a_fail_report_is_refused_even_when_a_check_run_now_would_pass(world: World) -> None:
    """ac1 reads the report: a FAIL stands until `files check` writes a PASS, though its cause has gone."""
    one = world.add(SOURCE_ONE)
    docx = world.built({"fingerprint": one})
    world.suppress(world.source_of(one))
    asyncio.run(world.quality().check(docx))
    world.unsuppress(world.source_of(one))
    assert asyncio.run(world.quality().check_file(docx.read_bytes(), world.sidecar_of(docx))).status == "PASS"

    outcome = only(world.publish(docx))

    assert outcome.refusal.code is FileRefusalCode.QUALITY_FAILED
    assert outcome.refusal.failing_checks == (QualityCheck.SUPPRESSION,)
    assert world.object_keys() == []


def test_a_pass_report_that_no_longer_holds_for_the_exact_bytes_is_refused(world: World) -> None:
    """The report on disk says PASS; a source was suppressed since, and the check run now fails."""
    one = world.add(SOURCE_ONE)
    docx = world.built({"fingerprint": one})
    world.suppress(world.source_of(one))

    outcome = only(world.publish(docx))

    assert outcome.refusal.code is FileRefusalCode.QUALITY_FAILED
    assert outcome.refusal.failing_checks == (QualityCheck.SUPPRESSION,)
    assert "checked again now" in outcome.refusal.message
    assert world.object_keys() == []


def test_a_file_built_from_a_draft_is_refused_though_it_passes(world: World) -> None:
    built = world.build(
        world.recipe([{"fingerprint": world.add(SOURCE_ONE)}], status="draft"), allow_draft=True
    )
    assert built.files is not None and built.quality is not None
    assert built.quality.status == "PASS"

    outcome = only(world.publish(built.files.docx))

    assert outcome.refusal.code is FileRefusalCode.BUILT_FROM_A_DRAFT
    assert world.object_keys() == [] and world.bucket_built == 0


def test_a_sidecar_that_records_no_recipe_status_is_refused_until_the_file_is_rebuilt(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    sidecar = docx.with_name("synthetic-file.docx.provenance.json")
    document = json.loads(sidecar.read_bytes())
    del document["recipe_status"]
    sidecar.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    assert asyncio.run(world.quality().check(docx)).report.status == "PASS"

    outcome = only(world.publish(docx))

    assert outcome.refusal.code is FileRefusalCode.RECIPE_STATUS_UNRECORDED
    assert world.object_keys() == []


def test_a_warning_never_blocks_and_is_recorded_in_the_metadata(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_WITHOUT_A_SHORT_CITE)})

    outcome = only(world.publish(docx))

    assert outcome.status is PublishStatus.PUBLISHED
    assert outcome.warned_checks == (QualityCheck.CITE_PRESENT,)
    document = json.loads(world.body(f"{prefix_of(docx)}metadata.json"))
    assert (document["quality_warnings"], document["warned_checks"]) == (1, ["cite-present"])


def test_a_file_still_holding_the_cp_text_slot_is_published_warned_not_blocked(world: World) -> None:
    """`v1-e33-t15`: the slot is a warning like any other (PM ruling B on t11's question 1)."""
    docx = world.built({"analytic": CP_TEXT_SLOT}, {"fingerprint": world.add(SOURCE_ONE)})

    outcome = only(world.publish(docx))

    assert outcome.status is PublishStatus.PUBLISHED
    assert outcome.warned_checks == (QualityCheck.PLACEHOLDERS_REPLACED,)
    document = json.loads(world.body(f"{prefix_of(docx)}metadata.json"))
    assert (document["quality_warnings"], document["warned_checks"]) == (1, ["placeholders-replaced"])


def test_a_refused_file_in_a_directory_does_not_stop_the_others_and_is_named(world: World) -> None:
    good = world.built({"fingerprint": world.add(SOURCE_ONE)}, name="good-file")
    bad = world.built({"fingerprint": world.add(SOURCE_TWO)}, name="bad-file")
    bad.with_name("bad-file.docx.quality.json").unlink()

    result = world.publish(good.parent)

    assert [(one.slug, one.status) for one in result.outcomes] == [
        ("bad-file", PublishStatus.REFUSED),
        ("good-file", PublishStatus.PUBLISHED),
    ]
    assert all("/bad-file/" not in key for key in world.object_keys())
    assert len(world.object_keys()) == 5


def test_a_recipe_that_is_missing_or_changed_since_the_build_is_refused(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    recipe = world.files_dir / "recipes" / TOPIC / "synthetic-file.yaml"
    recipe.write_text(recipe.read_text(encoding="utf-8").replace("Synthetic block", "Another block"))
    assert only(world.publish(docx)).refusal.code is FileRefusalCode.RECIPE_CHANGED
    recipe.unlink()
    assert only(world.publish(docx)).refusal.code is FileRefusalCode.RECIPE_NOT_FOUND
    assert world.object_keys() == []


def test_the_recipes_directory_can_be_named(world: World, tmp_path: Path) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (world.files_dir / "recipes" / TOPIC / "synthetic-file.yaml").rename(elsewhere / "synthetic-file.yaml")

    assert only(world.publish(docx, recipes_dir=elsewhere)).status is PublishStatus.PUBLISHED


# ------------------------------------------------------------------------------------------------
# ac3: idempotent, checksums verified after upload, and a dry run calls no S3
# ------------------------------------------------------------------------------------------------


def test_publishing_an_unchanged_file_again_is_skipped_and_writes_nothing(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    world.publish(docx)
    versions = world.versions()
    puts = len(world.bucket.puts)

    again = only(world.publish(docx))

    assert again.status is PublishStatus.SKIPPED
    assert (again.written, len(again.skipped)) == ((), 5)
    assert (world.versions(), len(world.bucket.puts)) == (versions, puts)


def test_a_dry_run_lists_the_keys_and_never_builds_a_bucket_client(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    prefix = prefix_of(docx)

    result = world.publish(docx, dry_run=True)

    outcome = only(result)
    assert (result.dry_run, outcome.status) == (True, PublishStatus.WOULD_PUBLISH)
    assert outcome.keys == (
        f"{prefix}synthetic-file.docx",
        f"{prefix}synthetic-file.docx.provenance.json",
        f"{prefix}synthetic-file.docx.quality.json",
        f"{prefix}recipe.yaml",
        f"{prefix}metadata.json",
    )
    assert (world.bucket_built, world.object_keys()) == (0, [])


def test_a_dry_run_still_refuses_what_a_publish_would(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    docx.with_name("synthetic-file.docx.quality.json").unlink()

    outcome = only(world.publish(docx, dry_run=True))

    assert outcome.refusal.code is FileRefusalCode.QUALITY_REPORT_MISSING
    assert world.bucket_built == 0


@pytest.mark.parametrize("lie", ["lie_on_put", "lie_on_head"])
def test_an_object_that_lands_with_another_digest_stops_the_publish_before_the_metadata(
    world: World, lie: str
) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    quality_key = f"{prefix_of(docx)}synthetic-file.docx.quality.json"
    setattr(world.bucket, lie, quality_key)

    with pytest.raises(PublishedObjectMismatch) as raised:
        world.publish(docx)

    assert raised.value.key == quality_key
    assert f"{prefix_of(docx)}metadata.json" not in world.object_keys()
    assert f"{prefix_of(docx)}recipe.yaml" not in world.object_keys()


# ------------------------------------------------------------------------------------------------
# ac6: a lookup by source finds exactly the files built from it; every sidecar source is in sources[]
# ------------------------------------------------------------------------------------------------


def test_find_by_source_returns_exactly_the_published_files_with_a_card_from_it(world: World) -> None:
    one, two, three = world.add(SOURCE_ONE), world.add(SOURCE_TWO, CEDAR), world.add(SOURCE_THREE)
    first = world.built({"fingerprint": one}, {"fingerprint": two}, name="first-file")
    second = world.built({"fingerprint": two}, {"fingerprint": three}, name="second-file")
    world.publish(first)
    world.publish(second)
    service = world.service()

    def found(fingerprint: str) -> list[str]:
        lookup = asyncio.run(service.find_by_source(world.source_of(fingerprint)))
        assert lookup.unreadable == ()
        return [one.key_prefix for one in lookup.found]

    assert found(one) == [prefix_of(first, "first-file")]
    assert found(two) == [prefix_of(first, "first-file"), prefix_of(second, "second-file")]
    assert found(three) == [prefix_of(second, "second-file")]
    assert asyncio.run(service.find_by_source("9" * 64)).found == ()


def test_find_by_source_reports_a_metadata_object_it_cannot_read(world: World) -> None:
    one = world.add(SOURCE_ONE)
    docx = world.built({"fingerprint": one})
    world.publish(docx)
    broken = "files/synthetic-topic/aff/synthetic-position/other-file/0123456789ab/metadata.json"
    world.client.put_object(Bucket=world.bucket_name, Key=broken, Body=b"{}")

    lookup = asyncio.run(world.service().find_by_source(world.source_of(one)))

    assert [found.key_prefix for found in lookup.found] == [prefix_of(docx)]
    assert lookup.unreadable == (broken,)


def test_find_by_source_every_source_in_a_published_sidecar_is_in_its_metadata_sources(world: World) -> None:
    fingerprints = [world.add(SOURCE_ONE), world.add(SOURCE_TWO, CEDAR), world.add(SOURCE_THREE, None)]
    docx = world.built(*({"fingerprint": one} for one in fingerprints))
    world.publish(docx)
    prefix = prefix_of(docx)

    sidecar = FileProvenanceManifest.model_validate_json(
        world.body(f"{prefix}synthetic-file.docx.provenance.json")
    )
    metadata = BuiltFileMetadata.model_validate_json(world.body(f"{prefix}metadata.json"))

    listed = {(one.caselist, one.snapshot, one.source_sha256) for one in metadata.sources}
    assert {(card.caselist, card.snapshot, card.source_sha256) for card in sidecar.cards} == listed
    assert len(listed) == 3


# ------------------------------------------------------------------------------------------------
# ac7: the uploaded recipe names no side, tournament, round, school or team, and resolves the same
# ------------------------------------------------------------------------------------------------


def test_the_uploaded_recipe_names_no_side_tournament_round_school_or_team_and_resolves_the_same(
    world: World,
) -> None:
    one, two = world.add(SOURCE_ONE), world.add(SOURCE_TWO, CEDAR)
    pins = [
        {
            "caselist": CASELIST,
            "source_sha256": world.source_of(one),
            "element_index": 0,
            "snapshot": "2026-09-15",
            "side": "AFF",
            "school": "Maple Grove",
            "team_code": "QX",
            "tournament": "Riverbend Invitational",
            "round": "Round 4",
        },
        {
            "caselist": CASELIST,
            "source_sha256": world.source_of(two),
            "element_index": 0,
            "school": "Cedar Hollow",
            "team_code": "ZaLu",
            "tournament": "Lakeshore Classic",
            "round": "Semis",
        },
    ]
    recipe = world.recipe([{"fingerprint": one, "pin": pins[0]}, {"fingerprint": two, "pin": pins[1]}])
    docx = world.build(recipe).files.docx  # pyright: ignore[reportOptionalMemberAccess]
    world.publish(docx)

    uploaded = world.body(f"{prefix_of(docx)}recipe.yaml").decode("utf-8")

    published_pins = [item["pin"] for item in yaml.safe_load(uploaded)["structure"][0]["blocks"][0]["items"]]
    assert published_pins == [
        {
            "caselist": CASELIST,
            "source_sha256": world.source_of(one),
            "element_index": 0,
            "snapshot": "2026-09-15",
        },
        {"caselist": CASELIST, "source_sha256": world.source_of(two), "element_index": 0},
    ]
    for word in (
        "Maple Grove",
        "QX",
        "Cedar Hollow",
        "ZaLu",
        "Riverbend",
        "Lakeshore",
        "Round 4",
        "Semis",
        "#",
    ):
        assert word not in uploaded, word
    assert not any(name in pin for pin in published_pins for name in STRIPPED_PIN_FIELDS)

    resolver = RecipeResolver(
        parsed_store=world.store,
        caselists=world.caselists,
        suppression=world.suppression,
        parser_version=PARSER.parser_version,
    )
    original, published = (
        asyncio.run(resolver.resolve(loaded.recipe))  # pyright: ignore[reportArgumentType]
        for loaded in (load_recipe(recipe.read_text(encoding="utf-8")), load_recipe(uploaded))
    )
    assert original.ok and published.ok, published.errors

    def occurrences(resolved: Any) -> list[tuple[str, str, int, str | None]]:
        return [
            (
                card.path,
                card.occurrence.source_sha256,
                card.occurrence.first_element_index,
                card.occurrence.disclosure,
            )
            for card in resolved.cards
        ]

    assert occurrences(published) == occurrences(original)


def test_the_published_recipe_is_the_same_bytes_whenever_the_file_is_published(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    first = world.service()
    plans = [asyncio.run(first.plan(PublishRequest(docx))) for _ in range(2)]
    staged = [plan.files[0].staged for plan in plans]
    assert staged[0] is not None and staged[1] is not None
    assert staged[0].bodies == staged[1].bodies


#: A third team, at the first team's school: a lookup by school finds both, by team code only one.
MAPLE_ZB: Final = SyntheticDisclosure(
    school="Maple Grove",
    team_code="ZB",
    side=Side.NEG,
    tournament="Lakeshore Classic",
    round="Round 2",
    path="Maple Grove/ZB/neg-lakeshore-r2.docx",
)


def published_three_files(world: World) -> tuple[str, str, str]:
    """Three files: Maple Grove QX's card alone, Cedar Hollow ZaLu's beside QX's, Maple Grove ZB's alone."""
    qx, zalu, zb = world.add(SOURCE_ONE), world.add(SOURCE_TWO, CEDAR), world.add(SOURCE_THREE, MAPLE_ZB)
    first = world.built({"fingerprint": qx}, name="first-file")
    second = world.built({"fingerprint": zalu}, {"fingerprint": qx}, name="second-file")
    third = world.built({"fingerprint": zb}, name="third-file")
    for docx in (first, second, third):
        world.publish(docx)
    return prefix_of(first, "first-file"), prefix_of(second, "second-file"), prefix_of(third, "third-file")


def by_disclosure(world: World, **asked: str) -> list[str]:
    lookup = asyncio.run(world.service().find_by_disclosure(**asked))
    assert lookup.unreadable == ()
    return list(lookup.found)


def test_find_by_source_school_or_team_reads_the_sidecars_and_finds_exactly_their_files(world: World) -> None:
    """PM ruling 2026-10-25 (Q1 B): a school or team code is looked up over the published sidecars."""
    first, second, third = published_three_files(world)

    assert by_disclosure(world, school="Maple Grove") == [first, second, third]
    assert by_disclosure(world, school="Cedar Hollow") == [second]
    assert by_disclosure(world, team_code="QX") == [first, second]
    assert by_disclosure(world, team_code="ZB") == [third]
    assert by_disclosure(world, school="Maple Grove", team_code="ZB") == [third]
    assert by_disclosure(world, school="Cedar Hollow", team_code="QX") == []


def test_find_by_source_school_or_team_finds_none_for_an_unknown_one_and_names_none_in_metadata(
    world: World,
) -> None:
    published_three_files(world)

    assert by_disclosure(world, school="Birch Valley") == []
    assert by_disclosure(world, team_code="QQ") == []
    assert by_disclosure(world, school="maple grove") == [], "as disclosed: no case folding"
    for key in world.object_keys():
        if key.endswith("/metadata.json"):
            assert b"Maple Grove" not in world.body(key) and b"ZaLu" not in world.body(key)


def test_find_by_source_school_or_team_reports_a_sidecar_it_cannot_read(world: World) -> None:
    first, _, _ = published_three_files(world)
    broken = (
        "files/synthetic-topic/aff/synthetic-position/other-file/0123456789ab/other-file.docx.provenance.json"
    )
    world.client.put_object(Bucket=world.bucket_name, Key=broken, Body=b"{}")

    lookup = asyncio.run(world.service().find_by_disclosure(team_code="QX"))

    assert first in lookup.found
    assert lookup.unreadable == (broken,)


def test_find_by_source_school_or_team_needs_one_of_them(world: World) -> None:
    with pytest.raises(ValueError, match="a school, a team code, or both"):
        asyncio.run(world.service().find_by_disclosure())


def test_find_by_source_over_an_empty_files_prefix_finds_nothing(world: World) -> None:
    lookup = asyncio.run(world.service().find_by_source("1" * 64))
    assert (lookup.found, lookup.unreadable) == ((), ())


def test_pins_inside_hats_lose_their_side_tournament_round_school_and_team_too() -> None:
    """A recipe with hats: every pin in every hat's blocks is stripped (PM amendment 2026-10-19)."""
    pin = {
        "caselist": CASELIST,
        "source_sha256": "a" * 64,
        "element_index": 3,
        "side": "NEG",
        "school": "Maple Grove",
        "team_code": "QX",
        "tournament": "Riverbend Invitational",
        "round": "Round 4",
    }
    recipe = FileRecipe.model_validate(
        {
            "schema_version": 1,
            "title": "Hatted file",
            "topic": TOPIC,
            "format": "POLICY",
            "caselist": CASELIST,
            "position": "synthetic-position",
            "side": "NEG",
            "fingerprint_version": FINGERPRINT_VERSION,
            "structure": [
                {
                    "pocket": "Pocket",
                    "hats": [
                        {
                            "hat": "First hat",
                            "blocks": [{"block": "A", "items": [{"fingerprint": "b" * 64, "pin": pin}]}],
                        },
                        {
                            "hat": "Second hat",
                            "blocks": [{"block": "B", "items": [{"fingerprint": "c" * 64, "pin": pin}]}],
                        },
                    ],
                }
            ],
        }
    )

    published = yaml.safe_load(published_recipe(recipe))

    pins = [item["pin"] for hat in published["structure"][0]["hats"] for item in hat["blocks"][0]["items"]]
    assert pins == [{"caselist": CASELIST, "source_sha256": "a" * 64, "element_index": 3}] * 2
    assert load_recipe(published_recipe(recipe).decode("utf-8")).ok


def test_a_file_whose_name_makes_no_key_is_refused(world: World) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)}, name="Synthetic_File")

    outcome = only(world.publish(docx))

    assert outcome.refusal.code is FileRefusalCode.SLUG_INVALID
    assert world.object_keys() == []


def test_a_quality_report_that_is_not_one_is_missing_and_a_missing_sidecar_fails_the_check(
    world: World,
) -> None:
    docx = world.built({"fingerprint": world.add(SOURCE_ONE)})
    report = docx.with_name("synthetic-file.docx.quality.json")
    kept = report.read_bytes()
    report.write_text("{}", encoding="utf-8")
    assert only(world.publish(docx)).refusal.code is FileRefusalCode.QUALITY_REPORT_MISSING

    report.write_bytes(kept)
    docx.with_name("synthetic-file.docx.provenance.json").unlink()
    outcome = only(world.publish(docx))
    assert outcome.refusal.code is FileRefusalCode.QUALITY_FAILED
    assert QualityCheck.SIDECAR in outcome.refusal.failing_checks
    assert world.object_keys() == []

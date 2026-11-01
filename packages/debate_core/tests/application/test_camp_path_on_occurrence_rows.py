"""A camp occurrence row carries its camp path's digest (`v1-e33-t07`).

One synthetic camp file, the `v1-e31-t03` structural fixture `cardmirror-camp-file.docx` (two cards),
is released twice: in `2031-policy` at two row paths (the same bytes uploaded under two OpenEv ids,
which three files on the operator's store are), and in `2032-policy` at a third. Every expected value
below is written from that table, not read from a run (working agreement 6):

* the parse writes 2 cards x 2 releases = 4 rows, the 2031 rows carrying the digests of both their
  paths and the 2032 rows the digest of theirs;
* `occurrences.jsonl` keeps the keys every earlier build reads, and `camp_paths.jsonl` beside it holds
  one line per camp path, 3 in all;
* a camp path withdrawn from one release stops that release's rows for the parse and, before any
  rebuild, for the resolver, and leaves the other release's alone.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from debate_core.application import file_recipes
from debate_core.application.caselist import removal_plan, removal_residue
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    camp_path_disclosure,
    disclosure_digest,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository, build_fake_caselist_repository

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
CAMP_FILE: Final = (
    REPO_ROOT / "tests/fixtures/debate_files/structural/cardmirror-camp-file.docx"
).read_bytes()
SHA: Final = hashlib.sha256(CAMP_FILE).hexdigest()
CAMP: Final = "Lanternfield Institute"

FIRST_PATH: Final = "openev-512-Synthetic_Grid_CP.docx"
SECOND_PATH: Final = "openev-513-Synthetic_Grid_CP.docx"
LATER_PATH: Final = "openev-640-Synthetic_Grid_CP.docx"
RELEASES: Final = {"2031-policy": (FIRST_PATH, SECOND_PATH), "2032-policy": (LATER_PATH,)}

IN_2031: Final = tuple(
    sorted(camp_path_disclosure("2031-policy", path) for path in (FIRST_PATH, SECOND_PATH))
)
IN_2032: Final = (camp_path_disclosure("2032-policy", LATER_PATH),)

OCCURRENCE_KEYS_EVERY_EARLIER_BUILD_READS: Final = {
    "schema_version",
    "caselist",
    "snapshot",
    "source_sha256",
    "parser_version",
    "profile_version",
    "fingerprint_version",
    "record",
    "last_snapshot",
    "disclosure",
    "camp",
    "first_element_index",
    "last_element_index",
    "exact_fingerprint",
    "cluster_id",
    "membership",
    "completeness",
}
"""The keys of an occurrence row `v1.1.0-dev.200` and `v1.1.0-dev.251` read, written out from their model."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class CampWorld:
    """A data directory holding one camp file in two releases' manifests, as the OpenEv import leaves it."""

    data_dir: Path

    @property
    def local(self) -> LocalEvidence:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        )

    @property
    def store(self) -> LocalParsedStore:
        return LocalParsedStore(self.data_dir)

    @property
    def suppression(self) -> RecordedSuppressionList:
        return RecordedSuppressionList(local_suppression_list_file(self.data_dir))

    @property
    def directory(self) -> Path:
        return self.data_dir / "parsed" / "openev" / DOCX_PARSER_VERSION

    def release(self, release: str, paths: tuple[str, ...]) -> None:
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
        manifest = self.data_dir / "objects" / "manifests" / "openev" / f"{release}.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def service(self) -> CaselistParseService:
        return CaselistParseService(
            local=self.local,
            store=self.store,
            parser=DebateDocxParser(),
            runner=InProcessParseRunner(),
            suppression=self.suppression,
            place_cards=CaselistCardStatsService(build_fake_caselist_repository()).place,
            failure_rate_threshold=0.5,
            failure_rate_minimum_sources=1,
        )

    async def parse(self) -> None:
        service = self.service()
        report = await service.run(await service.plan("openev"))
        assert report.store is not None

    async def rows(self) -> tuple[OccurrenceRecord, ...]:
        rows = await self.store.read_occurrences("openev", DOCX_PARSER_VERSION)
        assert rows is not None
        return rows

    def lines(self, name: str) -> list[dict[str, Any]]:
        return [json.loads(line) for line in (self.directory / name).read_text(encoding="utf-8").splitlines()]

    async def withdraw(self, release: str, path: str) -> None:
        """What a camp-path removal leaves on this machine's list when it was made on another one."""
        await self.withdraw_digest(camp_path_disclosure(release, path))

    async def withdraw_digest(self, disclosure: str) -> None:
        await self.suppression.append(
            [
                SuppressionEntry(
                    action=SuppressionAction.SUPPRESS,
                    sha256=SHA,
                    disclosure=disclosure,
                    recorded_at=datetime(2026, 10, 30, 18, 0, tzinfo=UTC),
                    reason=ReasonCode.REQUESTED_BY_CAMP,
                    request_id="RM-2026-07",
                )
            ]
        )


@pytest.fixture
async def world(tmp_path: Path) -> CampWorld:
    """Both releases imported and parsed once."""
    built = CampWorld(data_dir=tmp_path / "evidence")
    blob = built.data_dir / "blobs" / "sha256" / SHA[0:2] / SHA[2:4] / SHA
    blob.parent.mkdir(parents=True)
    blob.write_bytes(CAMP_FILE)
    for release, paths in RELEASES.items():
        built.release(release, paths)
    await built.parse()
    return built


def by_release(rows: tuple[OccurrenceRecord, ...]) -> dict[str, list[tuple[str, ...]]]:
    """Each release's rows, as the camp path digests each carries."""
    found: dict[str, list[tuple[str, ...]]] = {}
    for row in rows:
        found.setdefault(row.snapshot, []).append(row.camp_path_disclosures)
    return found


# ------------------------------------------------------------------------------------------------
# What the parse writes
# ------------------------------------------------------------------------------------------------


async def test_a_camp_row_carries_the_digest_of_each_live_path_of_its_file_in_its_release(
    world: CampWorld,
) -> None:
    assert by_release(await world.rows()) == {"2031-policy": [IN_2031] * 2, "2032-policy": [IN_2032] * 2}


async def test_the_occurrence_table_keeps_the_keys_and_record_version_every_earlier_build_reads(
    world: CampWorld,
) -> None:
    lines = world.lines("occurrences.jsonl")
    assert len(lines) == 4
    assert [set(line) for line in lines] == [OCCURRENCE_KEYS_EVERY_EARLIER_BUILD_READS] * 4
    assert {line["schema_version"] for line in lines} == {2}


async def test_the_camp_paths_sit_beside_the_table_one_line_per_path_naming_the_tables_sha256(
    world: CampWorld,
) -> None:
    table = hashlib.sha256((world.directory / "occurrences.jsonl").read_bytes()).hexdigest()
    lines = world.lines("camp_paths.jsonl")
    assert sorted(
        (line["snapshot"], line["source_sha256"], line["camp_path_disclosure"]) for line in lines
    ) == [
        ("2031-policy", SHA, IN_2031[0]),
        ("2031-policy", SHA, IN_2031[1]),
        ("2032-policy", SHA, IN_2032[0]),
    ]
    assert {(line["record"], line["caselist"], line["occurrence_table_sha256"]) for line in lines} == {
        ("camp_path", "openev", table)
    }
    text = (world.directory / "camp_paths.jsonl").read_text(encoding="utf-8")
    for named in (FIRST_PATH, SECOND_PATH, LATER_PATH, "Synthetic_Grid", CAMP):
        assert named not in text


async def test_the_parse_logs_no_camp_path(world: CampWorld, caplog: pytest.LogCaptureFixture) -> None:
    await world.withdraw("2032-policy", LATER_PATH)
    with caplog.at_level(logging.DEBUG):
        await world.parse()
    logged = " ".join(f"{record.getMessage()} {record.args!r}" for record in caplog.records)
    assert caplog.records
    for named in (FIRST_PATH, SECOND_PATH, LATER_PATH, "Synthetic_Grid", *IN_2031, *IN_2032):
        assert named not in logged


# ------------------------------------------------------------------------------------------------
# A camp path withdrawn: the parse
# ------------------------------------------------------------------------------------------------


async def test_a_camp_path_withdrawn_from_one_release_stops_its_rows_at_the_next_parse_though_still_listed(
    world: CampWorld,
) -> None:
    """The removal ran elsewhere: this machine's manifest still lists the path, and only the list knows."""
    await world.withdraw("2032-policy", LATER_PATH)
    await world.parse()
    assert by_release(await world.rows()) == {"2031-policy": [IN_2031] * 2}


async def test_a_camp_path_withdrawn_where_another_path_of_its_release_holds_the_file_keeps_that_paths_row(
    world: CampWorld,
) -> None:
    await world.withdraw("2031-policy", FIRST_PATH)
    await world.parse()
    left = (camp_path_disclosure("2031-policy", SECOND_PATH),)
    assert by_release(await world.rows()) == {"2031-policy": [left] * 2, "2032-policy": [IN_2032] * 2}


async def test_a_teams_withdrawn_disclosure_of_the_same_bytes_stops_no_camp_row(world: CampWorld) -> None:
    """A caselist disclosure's digest is never a camp path's: a team's withdrawal is its own."""
    await world.withdraw_digest(disclosure_digest("hspolicy26", f"2032-policy/{LATER_PATH}"))
    await world.parse()
    assert by_release(await world.rows()) == {"2031-policy": [IN_2031] * 2, "2032-policy": [IN_2032] * 2}


# ------------------------------------------------------------------------------------------------
# The local store: the digests go back on the table they were written beside, and no other
# ------------------------------------------------------------------------------------------------


async def test_a_table_rewritten_since_by_a_build_that_writes_no_camp_paths_reads_with_none(
    world: CampWorld,
) -> None:
    """An earlier build's rebuild leaves `camp_paths.jsonl` as it was: its rows behave as before."""
    table = world.directory / "occurrences.jsonl"
    table.write_text("".join(reversed(table.read_text(encoding="utf-8").splitlines(keepends=True))))
    rows = await world.rows()
    assert len(rows) == 4
    assert {row.camp_path_disclosures for row in rows} == {()}


async def test_a_table_with_no_camp_path_has_no_camp_paths_file_beside_it(world: CampWorld) -> None:
    rows = [row.evolve(camp_path_disclosures=()) for row in await world.rows()]
    await world.store.write_aggregates("openev", DOCX_PARSER_VERSION, index=(), failures=(), occurrences=rows)
    assert not (world.directory / "camp_paths.jsonl").exists()
    assert {row.camp_path_disclosures for row in await world.rows()} == {()}


# ------------------------------------------------------------------------------------------------
# A camp path withdrawn: the resolver, before any rebuild
# ------------------------------------------------------------------------------------------------


async def resolve_auto(world: CampWorld) -> file_recipes.ResolvedRecipe:
    fingerprint = (await world.rows())[0].exact_fingerprint
    text = (
        "schema_version: 1\ntitle: Synthetic camp file\ntopic: synthetic-topic\nformat: POLICY\n"
        "caselist: openev\nposition: synthetic-position\nside: NEG\n"
        f"fingerprint_version: {FINGERPRINT_VERSION}\n"
        "structure:\n  - pocket: P\n    blocks:\n      - block: B\n        items:\n"
        f"          - {json.dumps({'fingerprint': fingerprint})}\n"
    )
    loaded = file_recipes.load_recipe(text)
    assert loaded.recipe is not None, loaded.errors
    resolver = file_recipes.RecipeResolver(
        parsed_store=world.store,
        caselists=InMemoryCaselistRepository(),
        suppression=world.suppression,
        parser_version=DOCX_PARSER_VERSION,
    )
    return await resolver.resolve(loaded.recipe, lines=loaded.lines)


async def test_the_resolver_stops_a_release_whose_camp_path_was_withdrawn_after_the_table_was_built(
    world: CampWorld,
) -> None:
    before = await resolve_auto(world)
    await world.withdraw("2032-policy", LATER_PATH)
    after = await resolve_auto(world)
    assert [card.occurrence.snapshot for card in before.cards] == ["2032-policy"]
    assert ([card.occurrence.snapshot for card in after.cards], after.errors) == (["2031-policy"], ())
    assert after.cards[0].occurrence.camp_path_disclosures == IN_2031


# ------------------------------------------------------------------------------------------------
# Publishing and removal treat `camp_paths.jsonl` as the aggregates it is rebuilt with
# ------------------------------------------------------------------------------------------------


async def test_publish_sends_the_camp_paths_with_the_aggregates(
    world: CampWorld, s3_client: S3Client, evidence_bucket: str
) -> None:
    parsed = FsEvidenceObjectStore(world.data_dir, subdirectory=Path("parsed"))
    publisher = ParsedStorePublisher(
        local=parsed,
        local_path_for=parsed.path_for,
        remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        suppression=world.suppression,
        evidence=world.local,
    )
    published = await publisher.publish("openev", DOCX_PARSER_VERSION)
    assert published.succeeded
    key = f"parsed/openev/{DOCX_PARSER_VERSION}/camp_paths.jsonl"
    body = s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read()
    assert body == (world.directory / "camp_paths.jsonl").read_bytes()


@pytest.mark.parametrize("name", ["index.jsonl", "occurrences.jsonl", "camp_paths.jsonl"])
def test_a_removal_deletes_the_camp_paths_with_the_aggregates_and_the_residue_check_reads_them(
    name: str,
) -> None:
    key = f"parsed/openev/{DOCX_PARSER_VERSION}/{name}"
    assert removal_plan._is_parsed_aggregate(key, "parsed/openev/")  # pyright: ignore[reportPrivateUsage]
    assert removal_residue._aggregate_role(key, "parsed/openev/") == name  # pyright: ignore[reportPrivateUsage]


def test_a_removal_takes_no_other_file_of_a_version_directory_for_an_aggregate() -> None:
    for key in (
        f"parsed/openev/{DOCX_PARSER_VERSION}/camp_paths.json",
        f"parsed/openev/{DOCX_PARSER_VERSION}/x",
    ):
        assert not removal_plan._is_parsed_aggregate(key, "parsed/openev/")  # pyright: ignore[reportPrivateUsage]

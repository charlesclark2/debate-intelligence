"""A camp file's manifest row keeps OpenEv's own word for its camp, from the listing (`v1-e30-t31`).

OpenEv's page for a camp is `https://opencaselist.com/openev/<year>/<word>`, where the word is
OpenEv's own. `GET /openev` lists it on every file (`OpenEvFile.camp`), and until now the pull
stored it nowhere: a row's `camp` is the importer's canonical camp from `camp_aliases.yaml`, which
is often not OpenEv's word, so the camp link maps through a hand-filled table (`v1-e39-t28`).

Now each row the pull writes carries the listing's word as `openev_camp_word`, beside the
`openev_id` `v1-e30-t14` added, when it is one address word: letters and digits, matched whole,
the pattern the camp link checks (`OPENEV_CAMP_WORD_PATTERN`), and not `UNKNOWN`. Any other word is
not stored, and the row carries `null`. Rows written before carry no such key, and still read.

The listing is recorded: `fixtures/opencaselist/openev_camp_words.json`, read through the client's
own wire model, so the word reaches the pull as `GET /openev` hands it over. Every expected value is
written out by hand from that file (working agreements §6).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES

from debate_core.application.caselist.manifest import read_manifest_lines
from debate_core.application.caselist.openev_manifest import (
    CAMP_FIELDS,
    openev_manifest_key,
    read_recorded_release,
)
from debate_core.application.ports.caselist_source import OpenEvFile
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.opencaselist.models import OpenEvRecord

from .camp_manifest_scenario import MANIFEST_NAME, STORED
from .conftest import RemovalWorld
from .test_camp_manifest_is_read_by_every_build import OLDER_BUILDS, by_path, placed
from .test_sync_skips_suppressed_downloads import YEAR, FakeOpenEvSource, pull

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

CAMP_WORD = "openev_camp_word"
RELEASE_KEY = openev_manifest_key(YEAR, Event.POLICY)
LISTING = Path(__file__).parents[2] / "fixtures" / "opencaselist" / "openev_camp_words.json"

#: Each listed file's bytes: a different synthetic camp document each, so no row is a duplicate.
BODIES = {
    7101: DOCUMENT_BODIES["orchard-kritik"],
    7102: DOCUMENT_BODIES["tidewater-impact-turns"],
    7103: DOCUMENT_BODIES["harbor-tariffs-aff"],
    7104: DOCUMENT_BODIES["harbor-tariffs-neg"],
    7105: DOCUMENT_BODIES["lighthouse-politics"],
    7106: DOCUMENT_BODIES["canal-counterplan"],
    7107: DOCUMENT_BODIES["glacier-case-neg"],
    7108: DOCUMENT_BODIES["spillway-advantage"],
    7109: DOCUMENT_BODIES["estuary-solvency"],
    7110: DOCUMENT_BODIES["canal-counterplan-revised"],
    7111: DOCUMENT_BODIES["borrowed-grove-aff"],
}

#: What each row the pull writes carries as `openev_camp_word`, from the listing's `camp`, by hand.
EXPECTED_WORDS = {
    "openev-7101-Orchard_Kritik.docx": "Tamarack",  # one word of letters
    "openev-7102-Tidewater_Impact_Turns.docx": "QDI7",  # one word of letters and digits
    "openev-7103-Harbor_Tariffs_Aff.docx": None,  # "Quill Feather": a space
    "openev-7104-Harbor_Tariffs_Neg.docx": None,  # "Brightwater/Juniors": a slash
    "openev-7105-Lighthouse_Elections_DA.docx": None,  # "Zephyr\n": a trailing newline
    "openev-7106-Canal_Subsidies_Counterplan.docx": None,  # "": no word
    "openev-7107-Glacier_Case_Neg.docx": None,  # null
    "openev-7108-Spillway_Advantage.docx": None,  # "UNKNOWN": the importer's word for no camp
    "openev-7109-Estuary_Solvency_Advocate.docx": None,  # "Juniper-Lab": a hyphen
    "openev-7110-Canal_Counterplan_Revised.docx": None,  # no `camp` in the listing at all
    "openev-7111-Borrowed_Grove_Aff.docx": None,  # "Lindgård": a letter outside A to Z
}


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """This machine's data directory, which the pull imports into, and the dev bucket."""
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


def recorded_listing() -> list[OpenEvFile]:
    """`GET /openev`'s recorded answer, as the client hands it to the pull."""
    raw = json.loads(LISTING.read_text(encoding="utf-8"))
    return [OpenEvRecord.model_validate(one).to_file() for one in raw]


def listed_source() -> FakeOpenEvSource:
    return FakeOpenEvSource([(file, BODIES[file.openev_id]) for file in recorded_listing()])


def members(lines: list[str]) -> dict[str, dict[str, object]]:
    rows = [json.loads(line) for line in lines]
    return {str(row["path"]): row for row in rows if row["kind"] == "member"}


def local_lines(world: RemovalWorld) -> list[str]:
    return read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY))


def bucket_lines(world: RemovalWorld) -> list[str]:
    body = world.client.get_object(Bucket=world.bucket_name, Key=RELEASE_KEY)["Body"].read()
    return body.decode().splitlines()


def test_the_recorded_listing_hands_the_pull_each_camp_as_the_api_lists_it() -> None:
    """The words reach the pull unchanged: the client's model neither trims nor drops one."""
    assert {file.openev_id: file.camp for file in recorded_listing()} == {
        7101: "Tamarack",
        7102: "QDI7",
        7103: "Quill Feather",
        7104: "Brightwater/Juniors",
        7105: "Zephyr\n",
        7106: "",
        7107: None,
        7108: "UNKNOWN",
        7109: "Juniper-Lab",
        7110: None,
        7111: "Lindgård",
    }


async def test_each_row_the_pull_writes_carries_the_listings_camp_word_when_it_is_one_address_word(
    world: RemovalWorld,
) -> None:
    await pull(world, listed_source())

    rows = members(local_lines(world))
    assert {path: row.get(CAMP_WORD) for path, row in rows.items()} == EXPECTED_WORDS
    assert members(bucket_lines(world)) == rows, "the published manifest carries the same rows"


async def test_the_word_is_kept_beside_the_canonical_camp_not_in_its_place(world: RemovalWorld) -> None:
    """`camp` stays the alias table's, which knows none of these invented camps."""
    await pull(world, listed_source())

    rows = members(local_lines(world))
    assert {row["camp"] for row in rows.values()} == {"UNKNOWN"}
    assert rows["openev-7101-Orchard_Kritik.docx"].get(CAMP_WORD) == "Tamarack"
    assert rows["openev-7101-Orchard_Kritik.docx"]["openev_id"] == 7101


async def test_a_row_the_word_is_refused_for_still_carries_the_key_as_null(world: RemovalWorld) -> None:
    """One shape for every row this build writes: the key is there, and `null` says no word was kept."""
    await pull(world, listed_source())

    assert all(CAMP_WORD in row for row in members(local_lines(world)).values())
    assert CAMP_WORD in CAMP_FIELDS


@pytest.mark.parametrize("written_by", OLDER_BUILDS)
async def test_rows_written_before_carry_no_word_and_still_read(removal_world: RemovalWorld, written_by: str) -> None:
    """A manifest an older build wrote, then this build's pull of the listing merged into it."""
    world = removal_world
    theirs = members(await placed(world, written_by))
    assert theirs and not [row for row in theirs.values() if CAMP_WORD in row]

    await pull(world, listed_source())

    merged = local_lines(world)
    assert set(read_recorded_release(RELEASE_KEY, merged).rows) ^ (theirs.keys() | EXPECTED_WORDS.keys()) == set()
    assert {path: row for path, row in members(merged).items() if path in theirs} == theirs
    assert by_path(merged).items() >= by_path(release_lines_of(written_by)).items(), (
        "each row written before is kept byte for byte, still without the word"
    )
    new = {path: row.get(CAMP_WORD) for path, row in members(merged).items() if path not in theirs}
    assert new == EXPECTED_WORDS


def release_lines_of(written_by: str) -> list[str]:
    return (STORED / written_by / MANIFEST_NAME).read_text(encoding="utf-8").splitlines()

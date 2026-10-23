"""Reading one topic's sources for taxonomy seeding (`v1-e32-t01-position-taxonomy` ac4).

The reader joins the parsed card store, which holds no path, with the manifests, which say who
disclosed each source and when. A source is on the topic when a live disclosure of it is dated
inside the topic's ranges; its teams and sides come from those disclosures' paths alone.

Every school, team code, tournament and heading here is invented.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_seeding import SeedingCannotStart, SeedReading, read_seed_sources
from debate_core.application.ports.parsed_store import SourceOutcome
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Topic
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord, empty_suppression_list
from debate_core.testing.landscape_store import PARSER_VERSION, PlantedCard, PlantedCaselist

CASELIST = "hspolicy99"
TOPIC = Topic.model_validate(
    {
        "id": "policy-sample-topic",
        "event": "POLICY",
        "caselists": [{"caselist": CASELIST, "from": "2026-09-01", "to": "2026-12-31"}],
    }
)
ONE_NEG = "School One/CodeOne/School One-CodeOne-Neg-Sample Invitational-Round 1.docx"
TWO_AFF = "School Two/CodeTwo/School Two-CodeTwo-Aff-Sample Invitational-Round 2.docx"
NO_TEAM_DIRECTORY = "School Three/School Three-Neg-Sample Invitational-Round 3.docx"
SPENDING = (PlantedCard(("1NC", "Spending DA")),)


def local(data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


async def read(
    data_dir: Path,
    *,
    topic: Topic = TOPIC,
    version: str | None = None,
    suppression: RecordedSuppressionList | None = None,
) -> SeedReading:
    return await read_seed_sources(
        store=LocalParsedStore(data_dir),
        local=local(data_dir),
        suppression=suppression or empty_suppression_list(),
        topic=topic,
        caselist=CASELIST,
        version=version,
    )


@pytest.fixture
def planted(tmp_path: Path) -> PlantedCaselist:
    return PlantedCaselist(tmp_path, CASELIST)


@pytest.mark.anyio
async def test_teams_and_sides_come_from_the_disclosures(planted: PlantedCaselist) -> None:
    one = planted.source("one", SPENDING, disclosures=[("2026-09-08", ONE_NEG)])
    two = planted.source("two", SPENDING, disclosures=[("2026-09-15", TWO_AFF), ("2026-09-22", TWO_AFF)])
    reading = await read(planted.data_dir)
    assert (reading.entries, reading.parsed, reading.parsed_off_topic) == (2, 2, 0)
    by_digest = {source.sha256: source for source in reading.sources}
    (team_one,) = by_digest[one].teams
    assert (team_one.identity, team_one.side, team_one.names) == (
        "school one/codeone",
        Side.NEG,
        ("School One", "CodeOne", "Sample Invitational"),
    )
    assert {team.identity for team in by_digest[two].teams} == {"school two/codetwo"}
    assert {team.side for team in by_digest[two].teams} == {Side.AFF}
    assert by_digest[one].cards[0].section_path == ("1NC", "Spending DA")
    assert reading.caselist_names == {"School One": ("CodeOne",), "School Two": ("CodeTwo",)}


@pytest.mark.anyio
async def test_each_on_topic_disclosure_is_read_as_e30_records_it_for_the_landscape_report(
    planted: PlantedCaselist,
) -> None:
    cited = (PlantedCard(("1NC", "Spending DA"), short_cite="Okafor 25"), PlantedCard(("1NC", "Spending DA")))
    one = planted.source("one", cited, disclosures=[("2026-08-25", ONE_NEG), ("2026-09-08", ONE_NEG)])
    two = planted.source("two", SPENDING, disclosures=[("2026-09-15", TWO_AFF), ("2026-09-22", TWO_AFF)])
    reading = await read_seed_sources(
        store=LocalParsedStore(planted.data_dir),
        local=local(planted.data_dir),
        suppression=empty_suppression_list(),
        topic=TOPIC,
        caselist=CASELIST,
        through=date(2026, 9, 15),
    )
    assert sorted(
        (
            one.source_sha256,
            one.snapshot.isoformat(),
            one.school,
            one.team_code,
            one.side,
            one.tournament,
            one.round_label.normalized if one.round_label else None,
        )
        for one in reading.disclosures
    ) == sorted(
        [
            (one, "2026-09-08", "School One", "CodeOne", Side.NEG, "Sample Invitational", "R1"),
            (two, "2026-09-15", "School Two", "CodeTwo", Side.AFF, "Sample Invitational", "R2"),
        ]
    )
    by_digest = {source.sha256: source for source in reading.sources}
    assert [card.short_cite for card in by_digest[one].cards] == ["Okafor 25", None]
    assert "School" not in repr(reading)


@pytest.mark.anyio
async def test_only_disclosures_inside_the_topics_ranges_count(planted: PlantedCaselist) -> None:
    planted.source("before", SPENDING, disclosures=[("2026-08-25", ONE_NEG)])
    straddling = planted.source(
        "straddling", SPENDING, disclosures=[("2026-08-25", ONE_NEG), ("2026-09-15", TWO_AFF)]
    )
    reading = await read(planted.data_dir)
    assert [source.sha256 for source in reading.sources] == [straddling]
    assert [team.identity for team in reading.sources[0].teams] == ["school two/codetwo"]
    assert reading.parsed_off_topic == 1


@pytest.mark.anyio
async def test_a_source_no_manifest_names_is_off_the_topic(planted: PlantedCaselist) -> None:
    planted.source("undisclosed", SPENDING)
    reading = await read(planted.data_dir)
    assert reading.sources == ()
    assert (reading.parsed, reading.parsed_off_topic) == (1, 1)


@pytest.mark.anyio
async def test_a_source_that_did_not_parse_is_an_entry_and_nothing_more(planted: PlantedCaselist) -> None:
    planted.source("broken", (), disclosures=[("2026-09-08", ONE_NEG)], outcome=SourceOutcome.FAILED)
    reading = await read(planted.data_dir)
    assert (reading.entries, reading.parsed, len(reading.sources)) == (1, 0, 0)


@pytest.mark.anyio
async def test_a_path_with_no_team_directory_is_no_known_team(planted: PlantedCaselist) -> None:
    planted.source("unfiled", SPENDING, disclosures=[("2026-09-08", NO_TEAM_DIRECTORY)])
    (source,) = (await read(planted.data_dir)).sources
    (team,) = source.teams
    assert team.identity == ""


@pytest.mark.anyio
async def test_a_suppressed_source_is_not_read(planted: PlantedCaselist) -> None:
    withdrawn = planted.source("withdrawn", SPENDING, disclosures=[("2026-09-08", ONE_NEG)])
    kept = planted.source("kept", SPENDING, disclosures=[("2026-09-08", TWO_AFF)])
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=withdrawn,
        recorded_at=datetime(2026, 10, 1, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )
    suppression = RecordedSuppressionList(InMemoryAppendOnlyRecord(lines=[entry.model_dump_json()]))
    reading = await read(planted.data_dir, suppression=suppression)
    assert [source.sha256 for source in reading.sources] == [kept]


@pytest.mark.anyio
async def test_the_newest_version_is_read_unless_one_is_named(planted: PlantedCaselist) -> None:
    planted.source("older", SPENDING, disclosures=[("2026-09-08", ONE_NEG)], version="2026.10.18-docx-5")
    newer = planted.source("newer", SPENDING, disclosures=[("2026-09-08", TWO_AFF)])
    reading = await read(planted.data_dir)
    assert (reading.version, [source.sha256 for source in reading.sources]) == (PARSER_VERSION, [newer])
    named = await read(planted.data_dir, version="2026.10.18-docx-5")
    assert named.version == "2026.10.18-docx-5"
    with pytest.raises(SeedingCannotStart, match="2026.01.01-docx-0"):
        await read(planted.data_dir, version="2026.01.01-docx-0")


@pytest.mark.anyio
async def test_a_caselist_with_no_parsed_version_cannot_be_seeded(tmp_path: Path) -> None:
    with pytest.raises(SeedingCannotStart, match="no version"):
        await read(tmp_path)


@pytest.mark.anyio
async def test_a_topic_with_no_range_of_the_caselist_cannot_be_seeded(planted: PlantedCaselist) -> None:
    other = TOPIC.model_copy(update={"caselists": ()})
    with pytest.raises(SeedingCannotStart, match=CASELIST):
        await read(planted.data_dir, topic=other)


def test_a_readings_repr_holds_no_card_or_team() -> None:
    reading = SeedReading(
        caselist=CASELIST,
        version=PARSER_VERSION,
        topic_id="t",
        entries=0,
        parsed=0,
        parsed_off_topic=0,
        sources=(),
    )
    assert "sources" not in repr(reading)

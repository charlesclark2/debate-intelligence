"""Late disclosures counted on a synthetic store (`v1-e32-t51`).

The store is planted with :class:`~debate_core.testing.landscape_store.PlantedCaselist`: an older LD topic
whose range ends on 2026-10-31, and a newer one whose range starts on 2026-11-06 with one tournament entry
(`Harbor City Classic`, spelling `harborcity`) for the snapshot of 2026-11-03, as `topics.yaml` has
Florida Blue Key. Snapshots are weekly Tuesdays: 2026-10-27, 2026-11-03, 2026-11-10. Every school,
team code, tournament, tag and heading is invented. Each expected count is written by hand from what the
test plants.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_late_disclosures import (
    LateDisclosureCount,
    LateDisclosuresCannotBeCounted,
    TopicWords,
    WordClass,
    count_late_disclosures,
)
from debate_core.application.ports.parsed_store import SourceOutcome
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.domain.landscape import TopicMap
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord, empty_suppression_list
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

CASELIST = "synthld26"
OLD = "ld-sample-old-topic"
NEW = "ld-sample-new-topic"
OCT_27, NOV_03, NOV_10 = "2026-10-27", "2026-11-03", "2026-11-10"
WORDS = TopicWords(topic=("de-extinct",), other=("space col", "coloniz"))

NEW_WORDS = (PlantedCard(("1AC", "De-extinction harms"), tag="De-extinction diverts conservation"),)
OLD_WORDS = (PlantedCard(("1AC", "Space colonization good"), tag="Colonize Mars now"),)
BOTH_WORDS = (PlantedCard(("1NC", "De-extinction"), tag="Space colonization trades off"),)
NO_WORDS = (PlantedCard(("1AC", "Framework"), tag="Util is the standard"),)


def path(school: str, code: str, side: str, tournament: str, round_number: int) -> str:
    return f"{school}/{code}/{school}-{code}-{side}-{tournament}-Round {round_number}.docx"


def topics() -> TopicMap:
    return TopicMap.model_validate(
        {
            "schema_version": 1,
            "topics": [
                {
                    "id": OLD,
                    "event": "LD",
                    "caselists": [{"caselist": CASELIST, "from": "2026-09-01", "to": "2026-10-31"}],
                },
                {
                    "id": NEW,
                    "event": "LD",
                    "caselists": [{"caselist": CASELIST, "from": "2026-11-06", "to": "2026-12-31"}],
                    "tournaments": [
                        {
                            "caselist": CASELIST,
                            "name": "Harbor City Classic",
                            "spellings": ["harborcity"],
                            "from": NOV_03,
                            "to": NOV_03,
                        }
                    ],
                },
            ],
        }
    )


def local(data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


async def count(
    planted: PlantedCaselist,
    snapshot: str = NOV_10,
    *,
    topic_map: TopicMap | None = None,
    suppression: RecordedSuppressionList | None = None,
    version: str | None = None,
) -> LateDisclosureCount:
    return await count_late_disclosures(
        store=LocalParsedStore(planted.data_dir),
        local=local(planted.data_dir),
        suppression=suppression or empty_suppression_list(),
        topic_map=topic_map or topics(),
        caselist=CASELIST,
        snapshot=date.fromisoformat(snapshot),
        words=WORDS,
        version=version,
    )


@pytest.fixture
def planted(tmp_path: Path) -> PlantedCaselist:
    return PlantedCaselist(tmp_path, CASELIST)


@pytest.mark.anyio
async def test_a_late_disclosure_names_a_spelling_first_seen_before_the_topics_range(
    planted: PlantedCaselist,
) -> None:
    planted.source(
        "early", OLD_WORDS, disclosures=[(OCT_27, path("Alder", "AbCd", "Aff", "Lakeside Open", 1))]
    )
    planted.source(
        "late", OLD_WORDS, disclosures=[(NOV_10, path("Brook", "EfGh", "Neg", "Lakeside Open", 2))]
    )
    planted.source(
        "new-a", NEW_WORDS, disclosures=[(NOV_10, path("Alder", "AbCd", "Aff", "Pinecrest Open", 1))]
    )
    planted.source(
        "new-b", NEW_WORDS, disclosures=[(NOV_10, path("Cedar", "IjKl", "Neg", "Pinecrest Open", 1))]
    )

    counted = await count(planted)

    assert counted.topic_id == NEW
    assert counted.range_from == date(2026, 11, 6)
    assert counted.first_seen_through == date(2026, 10, 27)
    assert counted.newest_snapshot == date(2026, 11, 10)
    assert (counted.disclosures, counted.sources) == (3, 3)
    assert (counted.late_disclosures, counted.late_sources, counted.late_spellings) == (1, 1, 1)
    assert counted.late_share == pytest.approx(1 / 3)
    assert counted.late_by_first_seen == {OCT_27: 1}


@pytest.mark.anyio
async def test_a_spelling_first_seen_in_the_last_snapshot_before_the_range_is_late(
    planted: PlantedCaselist,
) -> None:
    planted.source(
        "shared", OLD_WORDS, disclosures=[(NOV_03, path("Alder", "AbCd", "Aff", "Lakeside Open", 1))]
    )
    planted.source("late", OLD_WORDS, disclosures=[(NOV_10, path("Brook", "EfGh", "Neg", "LakesideOpen", 2))])

    counted = await count(planted)

    assert counted.first_seen_through == date(2026, 11, 3)
    assert counted.late_disclosures == 1
    assert counted.late_by_first_seen == {NOV_03: 1}


@pytest.mark.anyio
async def test_the_topics_own_tournament_entry_spellings_are_not_late(planted: PlantedCaselist) -> None:
    planted.source(
        "entry", NEW_WORDS, disclosures=[(NOV_03, path("Alder", "AbCd", "Aff", "Harbor City Classic", 1))]
    )
    planted.source(
        "entry-late",
        NEW_WORDS,
        disclosures=[(NOV_10, path("Brook", "EfGh", "Neg", "Harbor City Classic", 5))],
    )
    planted.source(
        "round-robin", NEW_WORDS, disclosures=[(NOV_10, path("Cedar", "IjKl", "Aff", "Harbor City RR", 1))]
    )

    counted = await count(planted)

    assert counted.entry_spellings == ("harborcity",)
    assert counted.late_disclosures == 0
    assert counted.entry_spelling_disclosures == 2
    assert counted.check["tournament entry spellings"].disclosures[WordClass.TOPIC_ONLY] == 2


@pytest.mark.anyio
async def test_a_disclosure_naming_no_tournament_is_never_late(planted: PlantedCaselist) -> None:
    planted.source("early", OLD_WORDS, disclosures=[(OCT_27, "Alder/AbCd/Alder-AbCd-Round 1.docx")])
    planted.source("unnamed", OLD_WORDS, disclosures=[(NOV_10, "Brook/EfGh/Brook-EfGh-Round 2.docx")])

    counted = await count(planted)

    assert (counted.disclosures, counted.no_tournament, counted.late_disclosures) == (1, 1, 0)
    assert counted.check["other"].disclosures[WordClass.OTHER_ONLY] == 1


@pytest.mark.anyio
async def test_a_spelling_seen_earlier_only_in_a_suppressed_file_is_not_late(
    planted: PlantedCaselist,
) -> None:
    removed = planted.source(
        "removed", OLD_WORDS, disclosures=[(OCT_27, path("Alder", "AbCd", "Aff", "Lakeside Open", 1))]
    )
    planted.source(
        "later", OLD_WORDS, disclosures=[(NOV_10, path("Brook", "EfGh", "Neg", "Lakeside Open", 2))]
    )
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=removed,
        recorded_at=datetime(2026, 11, 1, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )
    record = InMemoryAppendOnlyRecord(lines=[entry.model_dump_json()])

    counted = await count(planted, suppression=RecordedSuppressionList(record))

    assert counted.late_disclosures == 0


@pytest.mark.anyio
async def test_the_topic_word_check_classes_each_group_by_its_sources_tags_and_headings(
    planted: PlantedCaselist,
) -> None:
    for name, school in (("a", "Alder"), ("b", "Brook")):
        planted.source(
            f"seen-{name}", OLD_WORDS, disclosures=[(OCT_27, path(school, "AbCd", "Aff", "Lakeside Open", 1))]
        )
    planted.source(
        "late-space", OLD_WORDS, disclosures=[(NOV_10, path("Cedar", "IjKl", "Neg", "Lakeside Open", 3))]
    )
    planted.source(
        "late-both", BOTH_WORDS, disclosures=[(NOV_10, path("Dune", "MnOp", "Neg", "Lakeside Open", 4))]
    )
    planted.source(
        "late-unparsed",
        (),
        disclosures=[(NOV_10, path("Elm", "QrSt", "Aff", "Lakeside Open", 5))],
        outcome=SourceOutcome.FAILED,
    )
    planted.source(
        "new-twice",
        NEW_WORDS,
        disclosures=[
            (NOV_10, path("Alder", "AbCd", "Aff", "Pinecrest Open", 1)),
            (NOV_10, path("Brook", "EfGh", "Aff", "Pinecrest Open", 2)),
        ],
    )
    planted.source(
        "new-none", NO_WORDS, disclosures=[(NOV_10, path("Cedar", "IjKl", "Neg", "Pinecrest Open", 1))]
    )

    counted = await count(planted)

    late, other = counted.check["late"], counted.check["other"]
    assert late.sources == {
        "topic words only": 0,
        "both": 1,
        "other topic words only": 1,
        "neither": 0,
        "not parsed": 1,
    }
    assert other.sources == {
        "topic words only": 1,
        "both": 0,
        "other topic words only": 0,
        "neither": 1,
        "not parsed": 0,
    }
    assert other.disclosures["topic words only"] == 2
    assert (counted.disclosures, counted.sources) == (6, 5)


@pytest.mark.anyio
async def test_a_spelling_is_named_only_when_two_schools_use_it_and_it_holds_no_school_word(
    planted: PlantedCaselist,
) -> None:
    planted.source(
        "shared-1", OLD_WORDS, disclosures=[(OCT_27, path("Alder", "AbCd", "Aff", "Lakeside Open", 1))]
    )
    planted.source(
        "shared-2", OLD_WORDS, disclosures=[(OCT_27, path("Brook", "EfGh", "Neg", "Lakeside Open", 1))]
    )
    planted.source(
        "shared-late", OLD_WORDS, disclosures=[(NOV_10, path("Alder", "AbCd", "Neg", "Lakeside Open", 2))]
    )
    planted.source(
        "one-1", OLD_WORDS, disclosures=[(OCT_27, path("Cedar", "IjKl", "Aff", "Cedar Scrimmage", 1))]
    )
    planted.source(
        "one-late", OLD_WORDS, disclosures=[(NOV_10, path("Cedar", "IjKl", "Neg", "Cedar Scrimmage", 2))]
    )
    planted.source(
        "host-1",
        OLD_WORDS,
        disclosures=[(OCT_27, path("Birchmoor Academy", "BaXy", "Aff", "BirchmoorClassic", 1))],
    )
    planted.source(
        "host-2", OLD_WORDS, disclosures=[(OCT_27, path("Dune", "MnOp", "Aff", "BirchmoorClassic", 1))]
    )
    planted.source(
        "host-late", OLD_WORDS, disclosures=[(NOV_10, path("Dune", "MnOp", "Neg", "BirchmoorClassic", 2))]
    )

    counted = await count(planted)

    assert [
        (one.spelling, one.schools, one.disclosures, one.first_seen) for one in counted.named_spellings
    ] == [("lakesideopen", 2, 1, date(2026, 10, 27))]
    assert counted.named_spellings[0].word_classes[WordClass.OTHER_ONLY] == 1
    assert counted.one_school_spellings == (1, 1)
    assert counted.school_word_spellings == (1, 1)
    assert counted.late_disclosures == 3


@pytest.mark.anyio
async def test_a_disclosure_another_topics_entry_takes_is_off_the_topic_and_not_late(
    planted: PlantedCaselist,
) -> None:
    planted.source(
        "early", OLD_WORDS, disclosures=[(OCT_27, path("Alder", "AbCd", "Aff", "Lakeside Open", 1))]
    )
    planted.source(
        "late", OLD_WORDS, disclosures=[(NOV_10, path("Brook", "EfGh", "Neg", "Lakeside Open", 2))]
    )
    with_entry = topics().model_dump(by_alias=True)
    with_entry["topics"][0]["tournaments"] = [
        {
            "caselist": CASELIST,
            "name": "Lakeside Open",
            "spellings": ["lakeside"],
            "from": date(2026, 11, 10),
            "to": date(2026, 12, 31),
        }
    ]

    counted = await count(planted, topic_map=TopicMap.model_validate(with_entry))

    assert (counted.disclosures, counted.off_topic, counted.late_disclosures) == (1, 1, 0)
    assert counted.late_share == 0.0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("snapshot", "why"),
    [
        (NOV_03, "no topic's range covers"),
        ("2026-11-17", "holds no manifest"),
    ],
)
async def test_a_snapshot_no_range_covers_or_the_store_lacks_is_refused(
    planted: PlantedCaselist, snapshot: str, why: str
) -> None:
    planted.source(
        "entry", NEW_WORDS, disclosures=[(NOV_03, path("Alder", "AbCd", "Aff", "Harbor City Classic", 1))]
    )
    planted.source(
        "new", NEW_WORDS, disclosures=[(NOV_10, path("Alder", "AbCd", "Aff", "Pinecrest Open", 1))]
    )

    with pytest.raises(LateDisclosuresCannotBeCounted, match=why):
        await count(planted, snapshot)


@pytest.mark.anyio
async def test_a_version_the_store_lacks_is_refused(planted: PlantedCaselist) -> None:
    planted.source(
        "new", NEW_WORDS, disclosures=[(NOV_10, path("Alder", "AbCd", "Aff", "Pinecrest Open", 1))]
    )

    with pytest.raises(LateDisclosuresCannotBeCounted, match="no version"):
        await count(planted, version="2026.01.01-docx-1")


def test_the_check_needs_a_word_on_each_side() -> None:
    with pytest.raises(ValueError, match="needs a word"):
        TopicWords(topic=("de-extinct",), other=())
    with pytest.raises(ValueError, match="needs a word"):
        TopicWords(topic=("--",), other=("coloniz",))


def test_the_check_matches_words_by_letters_and_digits_without_case() -> None:
    assert WORDS.classify(["DE EXTINCTION is unethical"]) is WordClass.TOPIC_ONLY
    assert WORDS.classify(["Space-Colonization"]) is WordClass.OTHER_ONLY
    assert WORDS.classify(["Deextinction", "colonizing Mars"]) is WordClass.BOTH
    assert WORDS.classify(["Util", "Kant"]) is WordClass.NEITHER


@pytest.mark.anyio
async def test_the_json_holds_counts_and_named_spellings_and_no_school_code_path_tag_or_heading(
    planted: PlantedCaselist,
) -> None:
    planted.source(
        "seen-1", OLD_WORDS, disclosures=[(OCT_27, path("Alder Ridge", "AbCd", "Aff", "Lakeside Open", 1))]
    )
    planted.source(
        "seen-2", OLD_WORDS, disclosures=[(OCT_27, path("Brookfield", "EfGh", "Neg", "Lakeside Open", 1))]
    )
    planted.source(
        "late", OLD_WORDS, disclosures=[(NOV_10, path("Alder Ridge", "AbCd", "Neg", "Lakeside Open", 2))]
    )
    planted.source(
        "only-one", OLD_WORDS, disclosures=[(OCT_27, path("Cedarvale", "IjKl", "Aff", "Quarry Scrimmage", 1))]
    )
    planted.source(
        "only-one-late",
        OLD_WORDS,
        disclosures=[(NOV_10, path("Cedarvale", "IjKl", "Neg", "Quarry Scrimmage", 2))],
    )

    text = json.dumps((await count(planted)).as_json()).casefold()

    for withheld in ("alder", "brookfield", "cedarvale", "abcd", "efgh", "ijkl", "quarry", "round", ".docx"):
        assert withheld not in text
    for card in OLD_WORDS:
        assert card.tag is not None and card.tag.casefold() not in text
        assert all(heading.casefold() not in text for heading in card.section_path)
    assert '"spelling": "lakesideopen"' in text
    assert '"share": 0.0' not in text

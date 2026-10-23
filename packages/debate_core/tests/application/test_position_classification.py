"""PositionClassificationService: the cache and the review queue (`v1-e32-t02` ac4, ac5).

* **The cache.** A second run over an unchanged reading places nothing (every key a hit, the
  matcher's `place` never called). A weekly window places only what no earlier run placed, and a
  complete archive afterwards places nothing. A taxonomy version bump misses that topic's results
  and no other topic's; a coach decision misses only the items under its heading; a cached result
  naming an id the taxonomy no longer has is placed again; MODEL results under a prompt version are
  kept for `v1-e32-t07`.
* **The review queue.** Unplaced headings and items below the threshold are listed by heading with
  hand-counted documents, teams, cards and candidates, a heading one team used is left out and
  counted, and the coach's decisions become overrides that place the heading on the next run.

Every expected count and row here was worked out by hand from the reading below (working
agreement 6). Every school, team, heading and tag is invented.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.ports.classification_store import CachedClassification
from debate_core.application.position_classification import (
    ClassificationRun,
    PositionClassificationService,
)
from debate_core.arguments.landscape.matcher import PositionMatcher
from debate_core.arguments.landscape.review_queue import (
    REVIEW_QUEUE_COLUMNS,
    apply_decisions,
    read_decisions_csv,
)
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy, TopicMap
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ClassificationResult,
    ItemKind,
    OverrideRules,
    PositionRole,
)
from debate_core.integrations.landscape.classification_store import (
    LocalClassificationStore,
    review_queue_path,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.fakes.suppression import empty_suppression_list
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

CASELIST = "hspolicy99"
TOPIC = "policy-sample-topic"


def taxonomy(topic_id: str = TOPIC, version: str = "1.0.0", event: str = "POLICY", **extra: Any) -> Taxonomy:
    positions = extra.get(
        "positions",
        [
            {
                "id": "spending-da",
                "label": "Spending DA",
                "kind": "da",
                "side": "neg",
                "aliases": ["spending da"],
            },
            {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg", "aliases": ["states cp"]},
            {
                "id": "sample-aff",
                "label": "Sample plan",
                "kind": "aff",
                "side": "aff",
                "aliases": ["sample plan"],
            },
            {
                "id": "election-da",
                "label": "Election DA",
                "kind": "da",
                "side": "neg",
                "tag_keywords": ["midterm"],
            },
        ],
    )
    return Taxonomy.model_validate(
        {"topic_id": topic_id, "taxonomy_version": version, "event": event, "positions": positions}
    )


def repository(*taxonomies: Taxonomy, overrides: Sequence[OverrideRules] = ()) -> YamlTaxonomyRepository:
    topic_map = TopicMap.model_validate(
        {
            "topics": [
                {
                    "id": one.topic_id,
                    "event": one.event,
                    "taxonomy_version": one.taxonomy_version,
                    "caselists": [
                        {
                            "caselist": CASELIST,
                            "from": f"2026-{7 + index:02d}-01",
                            "to": f"2026-{7 + index:02d}-28",
                        }
                    ],
                }
                for index, one in enumerate(taxonomies)
            ]
        }
    )
    return YamlTaxonomyRepository(
        topic_map,
        {one.topic_id: one for one in taxonomies},
        {rules.topic_id: rules for rules in overrides},
    )


def team(identity: str, side: Side) -> SeedTeam:
    return SeedTeam(identity=identity, side=side, names=(f"School {identity}", f"Code{identity}"))


def source(number: int, owner: SeedTeam, *cards: tuple[tuple[str, ...], str | None]) -> SeedSource:
    return SeedSource(
        sha256=f"{number:x}".rjust(64, "0"),
        teams=(owner,),
        cards=tuple(
            SeedCard(tag=tag, section_path=path, first_element_index=index * 3)
            for index, (path, tag) in enumerate(cards)
        ),
    )


ONE, TWO, THREE = team("one", Side.NEG), team("two", Side.AFF), team("three", Side.NEG)
FIRST = source(
    1,
    ONE,
    (("1NC", "Spending DA"), "Deficits rise"),
    (("1NC", "Spending DA", "Link"), "Plan spends"),
    (("1NC", "Spending Cliff DA"), "Cliff nears"),
    (("1NC", "Fed Key"), "Federal action key"),
)
SECOND = source(
    2,
    TWO,
    (("Sample Plan",), "Plan solves"),
    (("AT: Spending Cliff DA",), "No cliff"),
    (("Fed Key",), "Federal action key"),
    (("Solo Heading",), "Midterm swing"),
)
THIRD = source(
    3,
    THREE,
    (("Spending Cliff DA", "Impact"), "Recession"),
    (("Spending DA",), "Deficits rise"),
)


def reading(*sources: SeedSource, topic_id: str = TOPIC) -> SeedReading:
    return SeedReading(
        caselist=CASELIST,
        version="2026.10.20-docx-6",
        topic_id=topic_id,
        entries=len(sources),
        parsed=len(sources),
        parsed_off_topic=0,
        sources=tuple(sources),
    )


async def run(
    data_dir: Path,
    repo: YamlTaxonomyRepository,
    *sources: SeedSource,
    topic_id: str = TOPIC,
    threshold: float = 0.6,
) -> ClassificationRun:
    service = PositionClassificationService(
        taxonomies=repo, store=LocalClassificationStore(data_dir), review_threshold=threshold
    )
    return await service.classify(reading(*sources, topic_id=topic_id))


@pytest.fixture
def placements(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every item the matcher places, by fingerprint, for the tests that must see none."""
    calls: list[str] = []
    original = PositionMatcher.place

    def counted(self: PositionMatcher, item: Any) -> ClassificationResult:
        calls.append(item.fingerprint)
        return original(self, item)

    monkeypatch.setattr(PositionMatcher, "place", counted)
    return calls


def methods(found: ClassificationRun) -> dict[str, tuple[str | None, str | None, float]]:
    """Each card as `<source number>:<card number>` → (position, method, confidence)."""
    return {
        f"{int(one.source_sha256, 16)}:{(one.first_element_index or 0) // 3}": (
            one.position_id,
            None if one.method is None else one.method.value,
            one.confidence,
        )
        for one in found.classifications
        if one.item_kind is ItemKind.CARD
    }


# ------------------------------------------------------------------------------------------------
# One run, counted by hand
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_first_run_places_every_item_and_caches_each_key_once(tmp_path: Path) -> None:
    found = await run(tmp_path, repository(taxonomy()), FIRST, SECOND, THIRD)
    counts = found.counts
    assert (counts.sources, counts.sections, counts.cards) == (3, 12, 10)
    assert (counts.lookups, counts.hits, counts.misses) == (17, 0, 17)
    assert counts.cards_by_method == {"ALIAS": 3, "INHERITED": 1, "TAG_KEYWORD": 1, "UNPLACED": 5}
    assert (counts.cards_counted, counts.cards_below_threshold) == (4, 1)
    assert methods(found) == {
        "1:0": ("spending-da", "ALIAS", 1.0),
        "1:1": ("spending-da", "INHERITED", 0.9),
        "1:2": (None, None, 0.0),
        "1:3": (None, None, 0.0),
        "2:0": ("sample-aff", "ALIAS", 1.0),
        "2:1": (None, None, 0.0),
        "2:2": (None, None, 0.0),
        "2:3": ("election-da", "TAG_KEYWORD", 0.5),
        "3:0": (None, None, 0.0),
        "3:1": ("spending-da", "ALIAS", 1.0),
    }
    assert {one.prompt_version for one in found.classifications} == {"none"}
    assert {one.taxonomy_version for one in found.classifications} == {"1.0.0"}


# ------------------------------------------------------------------------------------------------
# The cache (ac5)
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cache_a_second_run_over_an_unchanged_snapshot_reclassifies_nothing(
    tmp_path: Path, placements: list[str]
) -> None:
    repo = repository(taxonomy())
    first = await run(tmp_path, repo, FIRST, SECOND, THIRD)
    assert len(placements) == 17
    cache_file = tmp_path / "landscape" / "classifications" / f"{CASELIST}.jsonl"
    written = cache_file.read_bytes()
    placements.clear()
    second = await run(tmp_path, repo, FIRST, SECOND, THIRD)
    assert placements == []
    assert (second.counts.lookups, second.counts.hits, second.counts.misses) == (17, 17, 0)
    assert second.counts.hit_rate == 1.0
    assert second.counts.cache_written is False
    assert cache_file.read_bytes() == written
    assert second.classifications == first.classifications


@pytest.mark.anyio
async def test_cache_a_weekly_window_places_only_what_no_run_placed_before(
    tmp_path: Path, placements: list[str]
) -> None:
    repo = repository(taxonomy())
    await run(tmp_path, repo, FIRST)
    assert len(placements) == 9
    placements.clear()
    window = await run(tmp_path, repo, THIRD)
    assert (window.counts.lookups, window.counts.hits, window.counts.misses) == (5, 3, 2)
    assert len(placements) == 2
    placements.clear()
    archive = await run(tmp_path, repo, FIRST, THIRD)
    assert placements == []
    assert archive.counts.hit_rate == 1.0


@pytest.mark.anyio
async def test_cache_items_read_alike_are_placed_once(tmp_path: Path, placements: list[str]) -> None:
    found = await run(tmp_path, repository(taxonomy()), FIRST, SECOND, THIRD)
    assert len(placements) == len(set(placements)) == found.counts.lookups == 17
    assert found.counts.sections + found.counts.cards == 22


LD_EARLY = taxonomy(
    "ld-sample-early",
    event="LD",
    positions=[
        {"id": "util-criterion", "label": "Util", "kind": "criterion", "side": "both", "aliases": ["util"]}
    ],
)
LD_LATE = taxonomy(
    "ld-sample-late",
    event="LD",
    positions=[
        {"id": "util-standard", "label": "Util", "kind": "criterion", "side": "both", "aliases": ["util"]}
    ],
)
LD_FILE = source(
    9, ONE, (("1AC", "Util"), "Consequences matter"), (("1AC", "Util", "Weighing"), "Weigh outcomes")
)


@pytest.mark.anyio
async def test_cache_two_topics_of_one_version_keep_their_own_results(tmp_path: Path) -> None:
    repo = repository(LD_EARLY, LD_LATE)
    early = await run(tmp_path, repo, LD_FILE, topic_id="ld-sample-early")
    late = await run(tmp_path, repo, LD_FILE, topic_id="ld-sample-late")
    assert late.counts.hits == 0

    def cards(found: ClassificationRun) -> set[str | None]:
        return {one.position_id for one in found.classifications if one.item_kind is ItemKind.CARD}

    assert (cards(early), cards(late)) == ({"util-criterion"}, {"util-standard"})


@pytest.mark.anyio
async def test_cache_a_taxonomy_version_bump_misses_only_that_topics_results(
    tmp_path: Path, placements: list[str]
) -> None:
    await run(tmp_path, repository(LD_EARLY, LD_LATE), LD_FILE, topic_id="ld-sample-early")
    await run(tmp_path, repository(LD_EARLY, LD_LATE), LD_FILE, topic_id="ld-sample-late")
    bumped = Taxonomy.model_validate({**LD_EARLY.model_dump(), "taxonomy_version": "1.1.0"})
    repo = repository(bumped, LD_LATE)
    placements.clear()
    early = await run(tmp_path, repo, LD_FILE, topic_id="ld-sample-early")
    assert (early.counts.hits, early.counts.misses) == (0, 5)
    assert {one.taxonomy_version for one in early.classifications} == {"1.1.0"}
    entries = await LocalClassificationStore(tmp_path).read(CASELIST)
    assert sorted({(entry.topic_id, entry.taxonomy_version) for entry in entries}) == [
        ("ld-sample-early", "1.1.0"),
        ("ld-sample-late", "1.0.0"),
    ]
    placements.clear()
    late = await run(tmp_path, repo, LD_FILE, topic_id="ld-sample-late")
    assert placements == []
    assert late.counts.hit_rate == 1.0


@pytest.mark.anyio
async def test_cache_keeps_model_results_it_does_not_read(tmp_path: Path) -> None:
    repo = repository(taxonomy())
    await run(tmp_path, repo, FIRST)
    store = LocalClassificationStore(tmp_path)
    model_entry = CachedClassification(
        topic_id=TOPIC,
        taxonomy_version="1.0.0",
        override_digest="none",
        prompt_version="1.0.0",
        item_fingerprint="f" * 64,
        result=ClassificationResult(
            position_id="spending-da",
            role=PositionRole.READS,
            confidence=0.8,
            rationale="a model result for the test",
            method=ClassificationMethod.MODEL,
            taxonomy_version="1.0.0",
            prompt_id="landscape.classify_position",
            prompt_version="1.0.0",
            model_id="sample-model",
        ),
    )
    await store.replace(CASELIST, [*await store.read(CASELIST), model_entry])
    again = await run(tmp_path, repo, FIRST, THIRD)
    assert again.counts.misses == 2
    assert model_entry in await store.read(CASELIST)


@pytest.mark.anyio
async def test_cache_a_cached_result_naming_an_id_that_is_gone_is_placed_again(tmp_path: Path) -> None:
    repo = repository(taxonomy())
    await run(tmp_path, repo, THIRD)
    store = LocalClassificationStore(tmp_path)
    entries = list(await store.read(CASELIST))
    aliased = next(entry for entry in entries if entry.result.method is ClassificationMethod.ALIAS)
    stale = aliased.model_copy(
        update={"result": aliased.result.model_copy(update={"position_id": "gone-da"})}
    )
    await store.replace(CASELIST, [stale if entry is aliased else entry for entry in entries])
    again = await run(tmp_path, repo, THIRD)
    assert (again.counts.refused_cached, again.counts.misses, again.counts.hits) == (1, 1, 4)
    assert "gone-da" not in {one.position_id for one in again.classifications}
    assert all(entry.result.position_id != "gone-da" for entry in await store.read(CASELIST))


@pytest.mark.anyio
async def test_cache_a_coach_decision_misses_only_the_items_under_its_heading(
    tmp_path: Path, placements: list[str]
) -> None:
    await run(tmp_path, repository(taxonomy()), FIRST, SECOND, THIRD)
    decided = OverrideRules.model_validate(
        {"topic_id": TOPIC, "overrides": [{"heading": "fed key", "position_id": "states-cp"}]}
    )
    placements.clear()
    found = await run(tmp_path, repository(taxonomy(), overrides=[decided]), FIRST, SECOND, THIRD)
    assert (found.counts.misses, found.counts.hits) == (2, 15)
    assert methods(found)["1:3"] == ("states-cp", "OVERRIDE", 1.0)
    assert methods(found)["2:2"] == ("states-cp", "OVERRIDE", 1.0)


@pytest.mark.anyio
async def test_cache_file_holds_no_heading_tag_or_team_name(tmp_path: Path) -> None:
    await run(tmp_path, repository(taxonomy()), FIRST, SECOND, THIRD)
    text = (
        (tmp_path / "landscape" / "classifications" / f"{CASELIST}.jsonl")
        .read_text(encoding="utf-8")
        .casefold()
    )
    for one in (FIRST, SECOND, THIRD):
        for card in one.cards:
            assert card.tag is not None and card.tag.casefold() not in text
            for heading in card.section_path:
                assert heading.casefold() not in text or heading.casefold() in {"spending da", "sample plan"}
        for name in one.teams[0].names:
            assert name.casefold() not in text
    for unplaced in ("spending cliff", "fed key", "solo heading", "impact"):
        assert unplaced not in text


@pytest.mark.anyio
async def test_cache_the_same_runs_write_the_same_bytes(tmp_path: Path) -> None:
    await run(tmp_path / "one", repository(taxonomy()), FIRST, SECOND, THIRD)
    await run(tmp_path / "two", repository(taxonomy()), THIRD, SECOND, FIRST)
    path = Path("landscape") / "classifications" / f"{CASELIST}.jsonl"
    assert (tmp_path / "one" / path).read_bytes() == (tmp_path / "two" / path).read_bytes()


# ------------------------------------------------------------------------------------------------
# The review queue (ac4)
# ------------------------------------------------------------------------------------------------


def queue_lines(found: ClassificationRun) -> list[str]:
    return Path(found.review_queue_location).read_text(encoding="utf-8").splitlines()


@pytest.mark.anyio
async def test_review_queue_lists_unplaced_headings_with_counts_and_candidates(tmp_path: Path) -> None:
    found = await run(tmp_path, repository(taxonomy()), FIRST, SECOND, THIRD)
    counts = found.review_queue.counts
    assert (counts.queued_items, counts.queued_cards, counts.without_heading) == (14, 6, 1)
    assert (counts.headings, counts.rows, counts.left_out_below_minimum_teams) == (5, 2, 3)
    assert found.review_queue_location == str(review_queue_path(tmp_path, CASELIST, TOPIC))
    assert queue_lines(found) == [
        ",".join(REVIEW_QUEUE_COLUMNS),
        "fed key,false,2,2,1,1,2,,",
        "spending cliff da,false,2,2,0,2,2,spending-da,",
    ]


@pytest.mark.anyio
async def test_review_queue_names_no_team_school_or_tag(tmp_path: Path) -> None:
    found = await run(tmp_path, repository(taxonomy()), FIRST, SECOND, THIRD)
    text = Path(found.review_queue_location).read_text(encoding="utf-8").casefold()
    for one in (FIRST, SECOND, THIRD):
        for name in (*one.teams[0].names, one.teams[0].identity):
            assert name.casefold() not in text
        for card in one.cards:
            assert card.tag is not None and card.tag.casefold() not in text


@pytest.mark.anyio
async def test_review_a_heading_one_team_used_is_counted_and_left_out(tmp_path: Path) -> None:
    service = PositionClassificationService(
        taxonomies=repository(taxonomy()), store=LocalClassificationStore(tmp_path), minimum_review_teams=1
    )
    found = await service.classify(reading(FIRST, SECOND, THIRD))
    assert [row.normalized_heading for row in found.review_queue.rows] == [
        "fed key",
        "spending cliff da",
        "impact",
        "solo heading",
        "spending cliff da",
    ]
    solo = next(row for row in found.review_queue.rows if row.normalized_heading == "solo heading")
    assert (solo.teams, solo.cards, solo.candidate_positions) == (1, 1, ("election-da",))
    answer = [row for row in found.review_queue.rows if row.answer]
    assert [(row.normalized_heading, row.aff_teams, row.neg_teams) for row in answer] == [
        ("spending cliff da", 1, 0)
    ]


@pytest.mark.anyio
async def test_review_items_below_the_threshold_are_queued(tmp_path: Path) -> None:
    strict = await PositionClassificationService(
        taxonomies=repository(taxonomy()),
        store=LocalClassificationStore(tmp_path / "strict"),
        review_threshold=0.95,
        minimum_review_teams=1,
    ).classify(reading(FIRST, THIRD))
    assert strict.counts.cards_below_threshold == 1
    assert strict.review_queue.counts.queued_cards == 4
    link = next(row for row in strict.review_queue.rows if row.normalized_heading == "link")
    assert (link.documents, link.teams, link.cards) == (1, 1, 1)
    loose = await run(tmp_path / "loose", repository(taxonomy()), SECOND, threshold=0.4)
    assert loose.counts.cards_below_threshold == 0
    assert loose.counts.cards_counted == 2


@pytest.mark.anyio
async def test_review_decisions_become_overrides_that_place_the_heading_next_run(
    tmp_path: Path, placements: list[str]
) -> None:
    repo = repository(taxonomy())
    first = await run(tmp_path, repo, FIRST, SECOND, THIRD)
    filled = Path(first.review_queue_location).read_text(encoding="utf-8")
    filled = filled.replace("fed key,false,2,2,1,1,2,,", "fed key,false,2,2,1,1,2,,states-cp")
    filled = filled.replace(
        "spending cliff da,false,2,2,0,2,2,spending-da,",
        "spending cliff da,false,2,2,0,2,2,spending-da,spending-da",
    )
    decisions = read_decisions_csv(io.StringIO(filled))
    applied = apply_decisions(
        repo.overrides(TOPIC), decisions, repo.taxonomy(TOPIC), decided=date(2026, 10, 24)
    )
    assert (applied.added, applied.changed, applied.unchanged) == (2, 0, 0)
    assert [(one.heading, one.position_id) for one in applied.rules.overrides] == [
        ("fed key", "states-cp"),
        ("spending cliff da", "spending-da"),
    ]
    placements.clear()
    second = await run(tmp_path, repository(taxonomy(), overrides=[applied.rules]), FIRST, SECOND, THIRD)
    assert (second.counts.misses, second.counts.hits) == (8, 9)
    assert second.counts.cards_by_method == {"ALIAS": 3, "INHERITED": 2, "OVERRIDE": 4, "TAG_KEYWORD": 1}
    assert methods(second)["3:0"] == ("spending-da", "INHERITED", 0.9)
    answered = next(
        one
        for one in second.classifications
        if one.item_id.endswith(":card:3") and int(one.source_sha256, 16) == 2
    )
    assert (answered.position_id, answered.role, answered.method) == (
        "spending-da",
        PositionRole.ANSWERS,
        ClassificationMethod.OVERRIDE,
    )
    assert second.review_queue.rows == ()
    assert second.review_queue.counts.queued_items == 3


@pytest.mark.anyio
async def test_review_a_heading_the_coach_ruled_on_is_not_queued_again(tmp_path: Path) -> None:
    ruled = OverrideRules.model_validate(
        {"topic_id": TOPIC, "overrides": [{"heading": "link", "position_id": None}]}
    )
    files = (
        source(7, ONE, (("Fed Key", "Link"), "Plan spends")),
        source(8, TWO, (("Fed Key", "Link"), "Plan spends")),
    )
    before = await PositionClassificationService(
        taxonomies=repository(taxonomy()),
        store=LocalClassificationStore(tmp_path / "before"),
        minimum_review_teams=1,
    ).classify(reading(*files))
    after = await PositionClassificationService(
        taxonomies=repository(taxonomy(), overrides=[ruled]),
        store=LocalClassificationStore(tmp_path / "after"),
        minimum_review_teams=1,
    ).classify(reading(*files))
    assert [(row.normalized_heading, row.teams) for row in before.review_queue.rows] == [
        ("fed key", 2),
        ("link", 2),
    ]
    assert [(row.normalized_heading, row.teams) for row in after.review_queue.rows] == [("fed key", 2)]


def test_review_a_decision_naming_no_position_is_refused() -> None:
    repo = repository(taxonomy())
    decisions = read_decisions_csv(io.StringIO("normalized_heading,decision\nfed key,medicaid-da\n"))
    with pytest.raises(ValueError, match="not a position"):
        apply_decisions(repo.overrides(TOPIC), decisions, repo.taxonomy(TOPIC), decided=date(2026, 10, 24))


def test_review_none_is_a_decision_that_the_heading_names_no_position() -> None:
    repo = repository(taxonomy())
    decisions = read_decisions_csv(io.StringIO("normalized_heading,decision\nlink,none\nimpact,\n"))
    applied = apply_decisions(
        repo.overrides(TOPIC), decisions, repo.taxonomy(TOPIC), decided=date(2026, 10, 24)
    )
    assert [(one.heading, one.position_id) for one in applied.rules.overrides] == [("link", None)]


def test_review_a_changed_decision_replaces_the_rule_and_an_unchanged_one_is_counted() -> None:
    repo = repository(taxonomy())
    current = OverrideRules.model_validate(
        {
            "topic_id": TOPIC,
            "overrides": [
                {"heading": "fed key", "position_id": "states-cp"},
                {"heading": "link", "position_id": None},
            ],
        }
    )
    decisions = read_decisions_csv(
        io.StringIO("normalized_heading,decision\nfed key,spending-da\nlink,none\nadd on,sample-aff\n")
    )
    applied = apply_decisions(current, decisions, repo.taxonomy(TOPIC), decided=date(2026, 10, 24))
    assert (applied.added, applied.changed, applied.unchanged) == (1, 1, 1)
    assert [(one.heading, one.position_id) for one in applied.rules.overrides] == [
        ("fed key", "spending-da"),
        ("link", None),
        ("add on", "sample-aff"),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("normalized_heading,decision\nFed Key,states-cp\n", "normalized heading"),
        ("normalized_heading,answer,decision\nfed key,false,states-cp\nfed key,true,none\n", "two decisions"),
        ("heading,decision\nfed key,states-cp\n", "review queue CSV"),
    ],
)
def test_review_a_decisions_file_is_refused(text: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        read_decisions_csv(io.StringIO(text))


def test_review_one_heading_decided_alike_on_both_rows_is_one_decision() -> None:
    decisions = read_decisions_csv(
        io.StringIO("normalized_heading,answer,decision\nfed key,false,states-cp\nfed key,true,states-cp\n")
    )
    assert len(decisions) == 1


# ------------------------------------------------------------------------------------------------
# From the planted store: the reader gives each card its paragraph, and stops at a snapshot
# ------------------------------------------------------------------------------------------------

NEG = "School One/CodeOne/School One-CodeOne-Neg-Sample Invitational-Round 1.docx"
AFF = "School Two/CodeTwo/School Two-CodeTwo-Aff-Sample Invitational-Round 2.docx"


@pytest.mark.anyio
async def test_cache_and_review_over_the_planted_store_through_a_snapshot(tmp_path: Path) -> None:
    planted = PlantedCaselist(tmp_path, CASELIST)
    early = planted.source(
        "early",
        [PlantedCard(("1NC", "Spending DA")), PlantedCard(("1NC", "School One Spending DA", "Link"))],
        disclosures=[("2026-07-07", NEG)],
    )
    planted.source("late", [PlantedCard(("Sample Plan",))], disclosures=[("2026-07-21", AFF)])
    objects = FsEvidenceObjectStore(tmp_path)
    blobs = FsEvidenceObjectStore(tmp_path, subdirectory=BLOB_DIRECTORY.parent)
    repo = repository(taxonomy())
    topic = repo.topic_map().topic(TOPIC)
    read = await read_seed_sources(
        store=LocalParsedStore(tmp_path),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=empty_suppression_list(),
        topic=topic,
        caselist=CASELIST,
        through=date(2026, 7, 14),
    )
    assert ([one.sha256 for one in read.sources], read.newest_disclosure) == ([early], date(2026, 7, 7))
    found = await PositionClassificationService(
        taxonomies=repo, store=LocalClassificationStore(tmp_path)
    ).classify(read)
    cards = [one for one in found.classifications if one.item_kind is ItemKind.CARD]
    assert [(one.item_id, one.position_id, one.method) for one in cards] == [
        (f"{early}:card:0", "spending-da", ClassificationMethod.ALIAS),
        (f"{early}:card:3", "spending-da", ClassificationMethod.INHERITED),
    ]

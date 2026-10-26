"""PositionClassificationService: the cache, the review queue and the model stage (`v1-e32-t02`, `t07`).

* **The cache.** A second run over an unchanged reading places nothing (every key a hit, the
  matcher's `place` never called). A weekly window places only what no earlier run placed, and a
  complete archive afterwards places nothing. A taxonomy version bump misses that topic's results
  and no other topic's; a coach decision misses only the items under its heading; a cached result
  naming an id the taxonomy no longer has is placed again; MODEL results under a prompt version are
  kept for `v1-e32-t07`.
* **The review queue.** Unplaced headings and items below the threshold are listed by heading with
  hand-counted documents, teams, cards and candidates, a heading one team used is left out and
  counted, and the coach's decisions become overrides that place the heading on the next run.

* **The model stage** (`v1-e32-t07`, every test named `model`). Only cards stage one left unplaced or
  below the threshold are sent, once per fingerprint, the most shared first, at most `max_items` of
  them; an unknown or retired id, a rationale repeating twelve consecutive words of the card, and an
  answer naming no position leave the card in the review queue; results name their prompt and model,
  a second run asks nothing, and a prompt version bump asks again about MODEL results only. A card
  sends no school, team code, tournament or digest, and only the first 120 words of its evidence.
  The routers are scripted fakes; no test reaches a model.

Every expected count and row here was worked out by hand from the reading below (working
agreement 6). Every school, team, heading and tag is invented.
"""

from __future__ import annotations

import io
import json
from collections.abc import Collection, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.errors import ModelUnavailableError
from debate_core.application.landscape_model_stage import (
    CLASSIFY_POSITION_PROMPT_ID,
    CLASSIFY_POSITION_VERSION,
    ModelClassificationStage,
)
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.ports.classification_store import CachedClassification
from debate_core.application.position_classification import (
    ClassificationRun,
    PositionClassificationService,
)
from debate_core.application.structured_output import StructuredOutputGuard
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
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations.landscape.classification_store import (
    LocalClassificationStore,
    review_queue_path,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.models.prompt_registry import PromptRegistry, load_prompt_file
from debate_core.testing.fakes.model_router import ScriptedModelResponse, ScriptedModelRouter
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


@pytest.mark.anyio
async def test_review_a_rows_candidates_are_its_own_headings_not_its_neighbours(tmp_path: Path) -> None:
    files = (
        source(5, ONE, (("Spending Tradeoff", "Fed Key"), "Plan spends")),
        source(6, TWO, (("Spending Tradeoff", "Fed Key"), "Plan spends")),
    )
    found = await run(tmp_path, repository(taxonomy()), *files)
    assert [(row.normalized_heading, row.candidate_positions) for row in found.review_queue.rows] == [
        ("fed key", ()),
        ("spending tradeoff", ("spending-da",)),
    ]


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


# ------------------------------------------------------------------------------------------------
# v1-e32-t07: the model stage
#
# Worked by hand from FIRST, SECOND and THIRD. Stage one leaves six cards needing review: 1:2
# (`spending cliff da`, "Cliff nears"), 1:3 and 2:2 (`fed key`, "Federal action key", one fingerprint),
# 2:1 (`AT: Spending Cliff DA`, "No cliff"), 2:3 (`solo heading`, "Midterm swing", TAG_KEYWORD at 0.5)
# and 3:0 (`spending cliff da` > `impact`, "Recession"). So five fingerprints reach the model, the
# shared one first because it stands for two cards. Every other card is placed at or above 0.6, and no
# section is ever sent.
# ------------------------------------------------------------------------------------------------

MODEL_REPOSITORY = Path(__file__).resolve().parents[4]
MODEL_ID = "fake-model"
LEFTOVER_TAGS = {"cliff nears", "federal action key", "no cliff", "midterm swing", "recession"}
"""The five tags stage one leaves for the model, as the prompt reads them: lowercase words."""

ANSWERS: dict[str, tuple[str | None, float, str]] = {
    "cliff nears": ("spending-da", 0.9, "a fiscal cliff story told as a spending disadvantage"),
    "federal action key": ("states-cp", 0.8, "argues only the federal government can act, against states"),
    "no cliff": ("spending-da", 0.85, "denies the disadvantage's fiscal cliff"),
    "midterm swing": ("election-da", 0.7, "an election disadvantage about the midterms"),
    "recession": ("spending-da", 0.4, "an impact that could serve several positions"),
}
"""What the answering router says about each leftover tag: position, confidence, rationale."""


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.load(MODEL_REPOSITORY / "prompts")


class AnsweringRouter(ScriptedModelRouter):
    """Answers each `landscape.classify_position` batch card by card from its tag, and keeps every batch."""

    def __init__(
        self,
        answers: Mapping[str, tuple[str | None, float, str]] | None = None,
        responses: Sequence[ScriptedModelResponse] = (),
    ) -> None:
        super().__init__(responses, model_id=MODEL_ID)
        self.answers = dict(ANSWERS if answers is None else answers)
        self.batches: list[list[dict[str, Any]]] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        if prompt.prompt_id == CLASSIFY_POSITION_PROMPT_ID and self.answers:
            items = json.loads(str(prompt.variables["items"]))
            self.batches.append(items)
            self.enqueue(
                {
                    "answers": [
                        {
                            "item": item["item"],
                            "position_id": self.answers[item["tag"]][0],
                            "confidence": self.answers[item["tag"]][1],
                            "rationale": self.answers[item["tag"]][2],
                        }
                        for item in items
                    ]
                }
            )
        return await super().generate_structured(task_class, prompt, schema, params)

    @property
    def tags(self) -> list[set[str]]:
        return [{item["tag"] for item in batch} for batch in self.batches]


class Evidence:
    """Evidence texts by (source number, card number); a card not listed has none."""

    def __init__(self, texts: Mapping[tuple[int, int], str] | None = None) -> None:
        self._texts = {
            (f"{number:x}".rjust(64, "0"), card * 3): text for (number, card), text in (texts or {}).items()
        }
        self.asked: list[dict[str, set[int]]] = []

    async def evidence_texts(
        self, caselist: str, version: str, wanted: Mapping[str, Collection[int]]
    ) -> Mapping[tuple[str, int], str]:
        self.asked.append({sha: set(indexes) for sha, indexes in wanted.items()})
        return {key: text for key, text in self._texts.items() if key[1] in wanted.get(key[0], ())}


def stage(
    router: ScriptedModelRouter,
    registry: PromptRegistry,
    *,
    evidence: Evidence | None = None,
    max_items: int = 100,
    batch_size: int = 20,
    prompt_version: str = CLASSIFY_POSITION_VERSION,
) -> ModelClassificationStage:
    return ModelClassificationStage(
        StructuredOutputGuard(router, registry),
        evidence or Evidence(),
        prompt_version=prompt_version,
        max_items=max_items,
        batch_size=batch_size,
    )


async def model_run(
    data_dir: Path,
    repo: YamlTaxonomyRepository,
    model: ModelClassificationStage,
    *sources: SeedSource,
) -> ClassificationRun:
    service = PositionClassificationService(
        taxonomies=repo, store=LocalClassificationStore(data_dir), model_stage=model
    )
    return await service.classify(reading(*sources))


ALIASED = source(
    7,
    ONE,
    (("1NC", "Spending DA"), "Deficits rise"),
    (("1NC", "Spending DA", "Link"), "Plan spends"),
    (("Sample Plan",), "Plan solves"),
    (("States CP",), "States solve"),
)


@pytest.mark.anyio
async def test_model_stage_asks_nothing_when_every_card_carries_an_alias(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    router = ScriptedModelRouter()
    found = await model_run(tmp_path, repository(taxonomy()), stage(router, prompts), ALIASED)

    assert router.calls == []
    assert (found.counts.model_items, found.counts.model_calls, found.counts.model_candidates) == (0, 0, 0)
    assert {one.method for one in found.classifications if one.item_kind is ItemKind.CARD} == {
        ClassificationMethod.ALIAS,
        ClassificationMethod.INHERITED,
    }


@pytest.mark.anyio
async def test_model_stage_asks_only_about_cards_stage_one_left_unplaced_or_below_the_threshold(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    router = AnsweringRouter()
    found = await model_run(tmp_path, repository(taxonomy()), stage(router, prompts), FIRST, SECOND, THIRD)

    assert len(router.calls) == 1
    assert router.tags == [LEFTOVER_TAGS]
    assert router.batches[0][0]["tag"] == "federal action key"
    assert [item["item"] for item in router.batches[0]] == ["item-1", "item-2", "item-3", "item-4", "item-5"]
    counts = found.counts
    assert (counts.model_candidates, counts.model_items, counts.model_calls, counts.model_held_back) == (
        5,
        5,
        1,
        0,
    )
    assert router.calls[0].task_class is TaskClass.HIGH_VOLUME


@pytest.mark.anyio
async def test_model_results_name_prompt_and_model_and_replace_stage_ones_for_their_cards(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    found = await model_run(
        tmp_path, repository(taxonomy()), stage(AnsweringRouter(), prompts), FIRST, SECOND, THIRD
    )

    assert methods(found) == {
        "1:0": ("spending-da", "ALIAS", 1.0),
        "1:1": ("spending-da", "INHERITED", 0.9),
        "1:2": ("spending-da", "MODEL", 0.9),
        "1:3": ("states-cp", "MODEL", 0.8),
        "2:0": ("sample-aff", "ALIAS", 1.0),
        "2:1": ("spending-da", "MODEL", 0.85),
        "2:2": ("states-cp", "MODEL", 0.8),
        "2:3": ("election-da", "MODEL", 0.7),
        "3:0": ("spending-da", "MODEL", 0.4),
        "3:1": ("spending-da", "ALIAS", 1.0),
    }
    model = [one for one in found.classifications if one.method is ClassificationMethod.MODEL]
    assert {(one.prompt_id, one.prompt_version, one.model_id) for one in model} == {
        (CLASSIFY_POSITION_PROMPT_ID, CLASSIFY_POSITION_VERSION, MODEL_ID)
    }
    roles = {f"{int(one.source_sha256, 16)}:{(one.first_element_index or 0) // 3}": one.role for one in model}
    assert roles["2:1"] is PositionRole.ANSWERS
    assert roles["1:2"] is PositionRole.READS
    assert found.counts.cards_by_method == {"ALIAS": 3, "INHERITED": 1, "MODEL": 6}
    assert (found.counts.cards_counted, found.counts.cards_below_threshold) == (9, 1)
    assert found.prompt_version == CLASSIFY_POSITION_VERSION
    assert found.review_queue.counts.queued_cards == 1


@pytest.mark.anyio
async def test_model_a_second_run_over_an_unchanged_snapshot_makes_no_model_call(
    tmp_path: Path, prompts: PromptRegistry, placements: list[str]
) -> None:
    repo = repository(taxonomy())
    first = await model_run(tmp_path, repo, stage(AnsweringRouter(), prompts), FIRST, SECOND, THIRD)
    placements.clear()
    router = ScriptedModelRouter()
    second = await model_run(tmp_path, repo, stage(router, prompts), FIRST, SECOND, THIRD)

    assert router.calls == []
    assert placements == []
    assert (second.counts.model_hits, second.counts.model_candidates, second.counts.model_items) == (5, 0, 0)
    assert second.counts.cache_written is False
    assert second.classifications == first.classifications


def bumped(registry: PromptRegistry, tmp_path: Path) -> PromptRegistry:
    """The committed prompts and `landscape.classify_position` at 1.1.0, the same text under a new version."""
    text = (MODEL_REPOSITORY / "prompts" / "landscape" / "classify_position.md").read_text(encoding="utf-8")
    text = text.replace("version: 1.0.0\nstatus:", "version: 1.1.0\nstatus:", 1).replace(
        "changelog:\n",
        "changelog:\n  - version: 1.1.0\n    date: 2026-10-26\n    summary: A test's bump.\n",
        1,
    )
    path = tmp_path / "classify_position@1.1.0.md"
    path.write_text(text, encoding="utf-8")
    return PromptRegistry([*registry.prompts, load_prompt_file(path)])


@pytest.mark.anyio
async def test_model_a_prompt_version_bump_asks_again_about_model_results_only(
    tmp_path: Path, prompts: PromptRegistry, placements: list[str]
) -> None:
    repo = repository(taxonomy())
    data = tmp_path / "data"
    await model_run(data, repo, stage(AnsweringRouter(), prompts), FIRST, SECOND, THIRD)
    placements.clear()
    router = AnsweringRouter()
    again = await model_run(
        data, repo, stage(router, bumped(prompts, tmp_path), prompt_version="1.1.0"), FIRST, SECOND, THIRD
    )

    assert placements == []
    assert router.tags == [LEFTOVER_TAGS]
    assert {
        one.prompt_version for one in again.classifications if one.method is ClassificationMethod.MODEL
    } == {"1.1.0"}
    kept = {entry.prompt_version for entry in await LocalClassificationStore(data).read(CASELIST)}
    assert kept == {"none", "1.1.0"}


CLIFF_EVIDENCE = (
    "Analysts warn that the looming fiscal cliff would force deep cuts across every federal program"
)


@pytest.mark.anyio
async def test_model_a_rationale_repeating_twelve_words_of_the_evidence_goes_to_the_review_queue(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    evidence = Evidence(
        {
            (
                1,
                2,
            ): CLIFF_EVIDENCE
        }
    )
    twelve = "that the looming fiscal cliff would force deep cuts across every federal"
    router = AnsweringRouter({**ANSWERS, "cliff nears": ("spending-da", 0.9, f"it says {twelve}")})
    found = await model_run(
        tmp_path, repository(taxonomy()), stage(router, prompts, evidence=evidence), FIRST, SECOND, THIRD
    )

    assert methods(found)["1:2"] == (None, None, 0.0)
    assert found.counts.model_refused == {"ECHOES_EVIDENCE": 1}
    assert found.counts.cards_by_method["UNPLACED"] == 1
    assert found.review_queue.counts.queued_cards == 2


@pytest.mark.anyio
async def test_model_a_rationale_repeating_eleven_words_of_the_evidence_is_accepted(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    evidence = Evidence(
        {
            (
                1,
                2,
            ): CLIFF_EVIDENCE
        }
    )
    eleven = "that the looming fiscal cliff would force deep cuts across every"
    router = AnsweringRouter({**ANSWERS, "cliff nears": ("spending-da", 0.9, f"it says {eleven} part")})
    found = await model_run(
        tmp_path, repository(taxonomy()), stage(router, prompts, evidence=evidence), FIRST, SECOND, THIRD
    )

    assert methods(found)["1:2"] == ("spending-da", "MODEL", 0.9)
    assert found.counts.model_refused == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("position_id", "why"),
    [("made-up-da", "invented"), ("util-criterion", "another topic's"), ("Spending DA", "not an id at all")],
)
async def test_model_an_unknown_position_id_goes_to_the_review_queue(
    tmp_path: Path, prompts: PromptRegistry, position_id: str, why: str
) -> None:
    router = AnsweringRouter({**ANSWERS, "midterm swing": (position_id, 0.95, "an election argument")})
    found = await model_run(tmp_path, repository(taxonomy()), stage(router, prompts), FIRST, SECOND, THIRD)

    assert methods(found)["2:3"] == ("election-da", "TAG_KEYWORD", 0.5), why
    assert found.counts.model_refused == {"UNKNOWN_POSITION": 1}
    assert found.counts.cards_below_threshold == 2


@pytest.mark.anyio
async def test_model_a_retired_position_id_goes_to_the_review_queue(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    retiring = taxonomy(
        positions=[
            *taxonomy().model_dump(mode="json")["positions"],
            {"id": "old-da", "label": "Old DA", "kind": "da", "side": "neg", "deprecated": True},
        ]
    )
    router = AnsweringRouter({**ANSWERS, "recession": ("old-da", 0.95, "an old disadvantage's impact")})
    found = await model_run(tmp_path, repository(retiring), stage(router, prompts), FIRST, SECOND, THIRD)

    assert methods(found)["3:0"] == (None, None, 0.0)
    assert found.counts.model_refused == {"UNKNOWN_POSITION": 1}


@pytest.mark.anyio
async def test_model_an_answer_naming_no_position_leaves_the_card_in_the_review_queue(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    router = AnsweringRouter({**ANSWERS, "recession": (None, 0.9, "a generic impact")})
    found = await model_run(tmp_path, repository(taxonomy()), stage(router, prompts), FIRST, SECOND, THIRD)

    assert methods(found)["3:0"] == (None, None, 0.0)
    assert found.counts.model_refused == {"NO_POSITION": 1}
    assert found.counts.cards_by_method["UNPLACED"] == 1


@pytest.mark.anyio
async def test_model_refused_answers_are_cached_and_not_asked_about_again(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    repo = repository(taxonomy())
    refusing = AnsweringRouter({**ANSWERS, "recession": ("made-up-da", 0.9, "a guess")})
    first = await model_run(tmp_path, repo, stage(refusing, prompts), FIRST, SECOND, THIRD)
    router = ScriptedModelRouter()
    second = await model_run(tmp_path, repo, stage(router, prompts), FIRST, SECOND, THIRD)

    assert router.calls == []
    assert methods(second)["3:0"] == methods(first)["3:0"] == (None, None, 0.0)


@pytest.mark.anyio
async def test_model_max_items_asks_about_the_most_shared_cards_first_and_holds_the_rest_back(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    router = AnsweringRouter()
    repo = repository(taxonomy())
    found = await model_run(tmp_path, repo, stage(router, prompts, max_items=2), FIRST, SECOND, THIRD)

    assert len(router.batches) == 1
    assert len(router.batches[0]) == 2
    assert router.batches[0][0]["tag"] == "federal action key"
    counts = found.counts
    assert (counts.model_candidates, counts.model_items, counts.model_held_back) == (5, 2, 3)
    cached = [
        entry
        for entry in await LocalClassificationStore(tmp_path).read(CASELIST)
        if entry.prompt_version != "none"
    ]
    assert len(cached) == 2

    rest = AnsweringRouter()
    after = await model_run(tmp_path, repo, stage(rest, prompts, max_items=100), FIRST, SECOND, THIRD)
    assert len(rest.batches[0]) == 3
    assert (after.counts.model_hits, after.counts.model_items, after.counts.model_held_back) == (2, 3, 0)


@pytest.mark.anyio
async def test_model_max_items_zero_asks_nothing_and_holds_every_candidate_back(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    router = ScriptedModelRouter()
    found = await model_run(
        tmp_path, repository(taxonomy()), stage(router, prompts, max_items=0), FIRST, SECOND, THIRD
    )

    assert router.calls == []
    assert (found.counts.model_items, found.counts.model_held_back) == (0, 5)


@pytest.mark.anyio
async def test_model_batches_hold_at_most_batch_size_cards(tmp_path: Path, prompts: PromptRegistry) -> None:
    router = AnsweringRouter()
    found = await model_run(
        tmp_path, repository(taxonomy()), stage(router, prompts, batch_size=2), FIRST, SECOND, THIRD
    )

    assert [len(batch) for batch in router.batches] == [2, 2, 1]
    assert set().union(*router.tags) == LEFTOVER_TAGS
    assert found.counts.model_calls == 3


@pytest.mark.anyio
async def test_model_a_batch_leaving_a_card_unanswered_is_repaired_once_then_refused_and_cached(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    partial = {
        "answers": [
            {"item": "item-1", "position_id": "states-cp", "confidence": 0.8, "rationale": "a reason"}
        ]
    }
    router = ScriptedModelRouter([partial, partial], model_id=MODEL_ID)
    repo = repository(taxonomy())
    found = await model_run(tmp_path, repo, stage(router, prompts), FIRST, SECOND, THIRD)

    assert [call.prompt.prompt_id for call in router.calls] == [CLASSIFY_POSITION_PROMPT_ID, "model.repair"]
    assert found.counts.model_refused == {"BATCH_REFUSED": 5}
    assert found.counts.model_calls == 2
    assert methods(found)["1:3"] == (None, None, 0.0)
    again = ScriptedModelRouter()
    await model_run(tmp_path, repo, stage(again, prompts), FIRST, SECOND, THIRD)
    assert again.calls == []


@pytest.mark.anyio
async def test_model_an_unreachable_model_keeps_the_answered_batches_and_names_the_error(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    class StopsOnTheSecondBatch(AnsweringRouter):
        async def generate_structured[OutputT: BaseModel](
            self,
            task_class: TaskClass,
            prompt: ModelPrompt,
            schema: type[OutputT],
            params: ModelParams | None = None,
        ) -> ModelResponse[OutputT]:
            if self.batches:
                raise ModelUnavailableError("fake", MODEL_ID)
            return await super().generate_structured(task_class, prompt, schema, params)

    found = await model_run(
        tmp_path,
        repository(taxonomy()),
        stage(StopsOnTheSecondBatch(), prompts, batch_size=2),
        FIRST,
        SECOND,
        THIRD,
    )

    assert found.counts.model_interrupted == "ModelUnavailableError"
    assert found.counts.model_items == 2
    cached = [
        entry
        for entry in await LocalClassificationStore(tmp_path).read(CASELIST)
        if entry.prompt_version != "none"
    ]
    assert len(cached) == 2


@pytest.mark.anyio
async def test_model_a_dry_run_stage_counts_and_asks_nothing(tmp_path: Path, prompts: PromptRegistry) -> None:
    router = ScriptedModelRouter()
    evidence = Evidence()
    found = await model_run(
        tmp_path,
        repository(taxonomy()),
        stage(router, prompts, evidence=evidence, max_items=3).planning(),
        FIRST,
        SECOND,
        THIRD,
    )

    assert router.calls == []
    assert evidence.asked == []
    assert (found.counts.model_items, found.counts.model_held_back) == (3, 2)


# ------------------------------------------------------------------------------------------------
# What a card sends
# ------------------------------------------------------------------------------------------------


NAMED = SeedSource(
    sha256=f"{11:x}".rjust(64, "0"),
    teams=(
        SeedTeam(identity="maple/ab", side=Side.NEG, names=("Maple Grove", "AB", "Lakeside Invitational")),
    ),
    cards=(
        SeedCard(
            tag="Maple Grove AB says Cedar Ridge cannot win the deficit debate",
            section_path=("Maple Grove AB 1NC", "Cedar Ridge KL Cliff"),
            first_element_index=0,
            short_cite="Thornbury 24 Maple Grove AB",
        ),
    ),
)
NAMED_EVIDENCE = " ".join(
    [
        "Cedar Ridge students and Maple Grove debaters with code KL watched the Lakeside Invitational",
        *(f"word{n}" for n in range(200)),
    ]
)


@pytest.mark.anyio
async def test_model_a_card_sends_no_school_team_code_tournament_digest_or_whole_evidence(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    router = AnsweringRouter({})
    router.enqueue(
        {
            "answers": [
                {"item": "item-1", "position_id": "spending-da", "confidence": 0.7, "rationale": "a cliff"}
            ]
        }
    )
    named = SeedReading(
        caselist=CASELIST,
        version="2026.10.20-docx-6",
        topic_id=TOPIC,
        entries=1,
        parsed=1,
        parsed_off_topic=0,
        sources=(NAMED,),
        caselist_names={"Maple Grove": ("AB",), "Cedar Ridge": ("KL",)},
    )
    service = PositionClassificationService(
        taxonomies=repository(taxonomy()),
        store=LocalClassificationStore(tmp_path),
        model_stage=stage(router, prompts, evidence=Evidence({(11, 0): NAMED_EVIDENCE})),
    )
    await service.classify(named)

    assert len(router.calls) == 1
    sent = json.dumps(router.calls[0].prompt.variables).casefold()
    for name in (
        "maple",
        "grove",
        "cedar",
        "ridge",
        "lakeside",
        "invitational",
        " ab ",
        " kl ",
        NAMED.sha256,
    ):
        assert name not in sent, name
    item = json.loads(str(router.calls[0].prompt.variables["items"]))[0]
    assert item["excerpt"].split()[:3] == ["students", "and", "debaters"]
    assert len(item["excerpt"].split()) == 120
    assert item["cite"] == "thornbury 24"
    assert item["headings"] == ["cliff"]
    assert set(item) == {"item", "headings", "under_an_answer_heading", "tag", "cite", "excerpt"}

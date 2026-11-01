"""The review queue ordered by the local proxy model, which places nothing (`v1-e32-t26` ac1).

A synthetic caselist of six invented teams, one document each, whose cards sit under headings no
alias places, so every one goes to the review queue. The order model is written by hand: four tag
words, three positions, every idf 1 and no intercept, so a card with one known word scores the
softmax of that word's column. Its confidences, worked out by hand (working agreement 6):

| Tag word  | Column (cap-k, spending-da, states-cp) | Guess       | Confidence |
|-----------|----------------------------------------|-------------|------------|
| `deficit` | 0, ln 8, 0                             | spending-da | 8/10 = 0.8 |
| `states`  | 0, 0, ln 3                             | states-cp   | 3/5 = 0.6  |
| `markets` | ln 2, 0, 0                             | cap-k       | 2/4 = 0.5  |
| `vague`   | 0, 0, 0                                | cap-k       | 1/3        |

Any other word is unknown to it. Its suggestion threshold is 0.5, t21's proxy threshold on hspolicy26.
The queue's rows, today's order first (most teams, then documents, cards and heading), and each row's
score (the largest per-position sum of its cards' confidences, over all its cards):

| Today | Heading         | Teams | Cards under it                       | Score            | Suggestion  |
|-------|-----------------|-------|--------------------------------------|------------------|-------------|
| 1     | fed key         | 6     | 6 vague                              | 6/3 / 6 = 1/3    | none        |
| 2     | mixed group     | 4     | 2 deficit, 1 states, 1 unknown       | 1.6 / 4 = 0.4    | none        |
| 3     | uniformity      | 3     | 3 states                             | 0.6              | states-cp   |
| 4     | commodity frame | 2     | 2 markets                            | 0.5, at the line | cap-k       |
| 5     | debt group      | 2     | 2 deficit                            | 0.8              | spending-da |
| 6     | deficits group  | 2     | 2 deficit                            | 0.8              | spending-da |
| 7     | theory group    | 2     | 2 unknown                            | no score         | none        |

`solo heading` (one team) is left out of the queue and only counted. Ordered: debt group and deficits
block (tied, so in today's order), uniformity, commodity frame, mixed group, fed key, and theory group
last, unscored.

Every school, team code, tournament, heading and tag here is invented.
"""

from __future__ import annotations

import ast
import asyncio
import csv
import io
import math
import random
import shutil
import subprocess
import sys
from array import array
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_run import (
    BUNDLE_FILES,
    LandscapeRunRequest,
    LandscapeRunResult,
    LandscapeRunService,
)
from debate_core.application.landscape_scan import ScanAcceptanceLog
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.application.review_queue_order import (
    QueueOrderModelFile,
    ReviewQueueOrdering,
    model_file_text,
    read_model_file,
)
from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.local_classifier import FeatureRow, LocalClassifier, compare
from debate_core.arguments.landscape.matcher import PositionMatcher, read_items
from debate_core.arguments.landscape.queue_order import (
    CardFeatures,
    Prediction,
    QueueOrderModel,
    RowScore,
    card_features,
    order_review_queue,
    row_scores,
)
from debate_core.arguments.landscape.review_queue import (
    ORDERED_REVIEW_QUEUE_COLUMNS,
    REVIEW_QUEUE_COLUMNS,
    QueuedItem,
    ReviewQueue,
    ReviewQueueCounts,
    ReviewRow,
    read_decisions_csv,
)
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import ItemKind, OverrideRules
from debate_core.integrations.landscape.classification_store import (
    LocalClassificationStore,
    LocalQueueOrderModelStore,
    queue_order_model_path,
    review_queue_path,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.landscape_store import PARSER_VERSION, PlantedCard, PlantedCaselist

REPO = Path(__file__).resolve().parents[5]
CASELIST = "hspolicy99"
TOPIC = "policy-sample-topic"
SNAPSHOT = "2026-09-15"
TOPICS = f"""\
schema_version: 1
topics:
  - id: {TOPIC}
    event: POLICY
    taxonomy_version: 1.0.0
    caselists:
      - {{caselist: {CASELIST}, from: 2026-09-01, to: 2026-12-31}}
"""
TAXONOMY = f"""\
schema_version: 1
topic_id: {TOPIC}
taxonomy_version: 1.0.0
event: POLICY
positions:
  - {{id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}}
  - {{id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp]}}
  - {{id: cap-k, label: Cap K, kind: k, side: neg, aliases: [cap k]}}
"""
TEAMS = (
    ("Larkspur Point", "LaPo"),
    ("Larkspur Point", "LaPt"),
    ("Juniper Bay", "JuBa"),
    ("Juniper Bay", "JuBy"),
    ("Hollis Mill", "HoMi"),
    ("Hollis Mill", "HoMl"),
)
TOURNAMENT = "Sample Classic"
TAGS = {
    "deficit": "Deficit rises fast",
    "states": "States act together",
    "markets": "Markets commodify all",
    "vague": "Vague claim here",
    "unknown": "Theory warrant here",
}
CARDS_BY_TEAM: tuple[tuple[tuple[str, str], ...], ...] = (
    (
        ("fed key", "vague"),
        ("mixed group", "deficit"),
        ("deficits group", "deficit"),
        ("theory group", "unknown"),
    ),
    (
        ("fed key", "vague"),
        ("mixed group", "deficit"),
        ("deficits group", "deficit"),
        ("theory group", "unknown"),
    ),
    (("fed key", "vague"), ("mixed group", "states"), ("uniformity", "states")),
    (("fed key", "vague"), ("mixed group", "unknown"), ("uniformity", "states"), ("debt group", "deficit")),
    (
        ("fed key", "vague"),
        ("uniformity", "states"),
        ("commodity frame", "markets"),
        ("debt group", "deficit"),
    ),
    (("fed key", "vague"), ("commodity frame", "markets"), ("solo heading", "deficit")),
)
"""Each team's cards: `(heading, tag word)`. One document per team."""

TODAYS_ORDER = (
    "fed key",
    "mixed group",
    "uniformity",
    "commodity frame",
    "debt group",
    "deficits group",
    "theory group",
)
ORDERED = (
    "debt group",
    "deficits group",
    "uniformity",
    "commodity frame",
    "mixed group",
    "fed key",
    "theory group",
)
SUGGESTED = {
    "debt group": "spending-da",
    "deficits group": "spending-da",
    "uniformity": "states-cp",
    "commodity frame": "cap-k",
}
THRESHOLD = 0.5


def hand_model(suggest_from: float | None = THRESHOLD) -> QueueOrderModel:
    """The table above: one column per known tag word, over (cap-k, spending-da, states-cp)."""
    columns = {
        "t:deficit": (0.0, math.log(8), 0.0),
        "t:markets": (math.log(2), 0.0, 0.0),
        "t:states": (0.0, 0.0, math.log(3)),
        "t:vague": (0.0, 0.0, 0.0),
    }
    vocabulary = tuple(sorted(columns))
    return QueueOrderModel(
        classes=("cap-k", "spending-da", "states-cp"),
        vocabulary=vocabulary,
        idf=array("d", [1.0] * len(vocabulary)),
        coefficients=array("d", [weight for token in vocabulary for weight in columns[token]]),
        intercepts=(0.0, 0.0, 0.0),
        suggest_from=suggest_from,
    )


# ------------------------------------------------------------------------------------------------
# The planted world
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class World:
    data_dir: Path
    config_dir: Path
    digests: tuple[str, ...]
    paths: tuple[str, ...]


@pytest.fixture
def world(tmp_path: Path) -> World:
    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    digests: list[str] = []
    paths: list[str] = []
    for number, ((school, code), cards) in enumerate(zip(TEAMS, CARDS_BY_TEAM, strict=True)):
        path = f"{school}/{code}/{school}-{code}-Neg-{TOURNAMENT}-Round {number + 1}.docx"
        planted = [PlantedCard((heading,), tag=TAGS[word]) for heading, word in cards]
        digests.append(store.source(f"source-{number}", planted, disclosures=[(SNAPSHOT, path)]))
        paths.append(path)
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return World(data_dir, config_dir, tuple(digests), tuple(paths))


def train(world: World, model: QueueOrderModel | None = None, **changed: object) -> Path:
    """Write the order model under the data directory, as `train-queue-order` does, from the planted table."""
    fields: dict[str, object] = {
        "caselist": CASELIST,
        "version": PARSER_VERSION,
        "topic_id": TOPIC,
        "taxonomy_version": "1.0.0",
        "through": date(2026, 9, 15),
        "seed": 21,
        "trained_cards": 22,
        "sources": tuple(sorted(world.digests)),
        "suppressed_at_build": (),
        "model": model or hand_model(),
    }
    fields.update(changed)
    text = model_file_text(QueueOrderModelFile(**fields))  # pyright: ignore[reportArgumentType]
    return Path(asyncio.run(LocalQueueOrderModelStore(world.data_dir).write(CASELIST, TOPIC, text)))


def suppress(world: World, sha256: str, path: str | None = None) -> None:
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha256,
        disclosure=disclosure_digest(CASELIST, path) if path is not None else None,
        recorded_at=datetime(2026, 10, 25, 12, 0, tzinfo=UTC),
        reason=ReasonCode.POLICY,
        request_id="RM-2026-99",
    )
    asyncio.run(RecordedSuppressionList(local_suppression_list_file(world.data_dir)).append([entry]))


def service(world: World, *, ordering: bool = True) -> LandscapeRunService:
    data_dir = world.data_dir
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    suppression = RecordedSuppressionList(local_suppression_list_file(data_dir))
    return LandscapeRunService(
        taxonomies=YamlTaxonomyRepository.load(world.config_dir),
        config_dir=world.config_dir,
        parsed_store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=suppression,
        classifications=LocalClassificationStore(data_dir),
        objects=objects,
        run_log=None,
        reports_dir=data_dir / "reports" / "landscape",
        acceptances=ScanAcceptanceLog(data_dir / "landscape" / "scan-acceptances"),
        today=lambda: date(2026, 9, 16),
        queue_order=ReviewQueueOrdering(
            models=LocalQueueOrderModelStore(data_dir),
            parsed_store=LocalParsedStore(data_dir),
            suppression=suppression,
        )
        if ordering
        else None,
    )


def run(world: World, out: str, *, ordering: bool = True) -> tuple[LandscapeRunResult, str]:
    """A landscape run into `<data dir>/../<out>`, and the review queue's CSV it wrote."""
    result = asyncio.run(
        service(world, ordering=ordering).run(
            LandscapeRunRequest(caselist=CASELIST, out=world.data_dir.parent / out)
        )
    )
    queue = review_queue_path(world.data_dir, CASELIST, TOPIC).read_text(encoding="utf-8")
    return result, queue


def headings_of(result: LandscapeRunResult) -> tuple[str, ...]:
    return tuple(row.normalized_heading for row in result.classification.review_queue.rows)


def csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


# ------------------------------------------------------------------------------------------------
# The model
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (("t:deficit", "t:rises", "h:debt group"), Prediction("spending-da", 0.8)),
        (("t:states",), Prediction("states-cp", 3 / 5)),
        (("t:markets", "t:markets all"), Prediction("cap-k", 0.5)),
        (("t:vague",), Prediction("cap-k", 1 / 3)),
    ],
)
def test_the_hand_model_scores_the_hand_worked_confidences(
    tokens: tuple[str, ...], expected: Prediction
) -> None:
    found = hand_model().predict(tokens)
    assert found is not None
    assert found.position_id == expected.position_id
    assert found.confidence == pytest.approx(expected.confidence, abs=1e-12)


def test_a_card_with_no_known_token_has_no_prediction() -> None:
    assert hand_model().predict(("t:theory", "t:warrant", "h:theory group")) is None
    assert hand_model().predict(()) is None


def test_two_known_words_are_weighed_as_tf_idf_normed() -> None:
    """`deficit` and `states` once each: each weighs 1/sqrt(2), so the scores are (0, ln 8, ln 3)/sqrt(2)."""
    scores = (0.0, math.log(8) / math.sqrt(2), math.log(3) / math.sqrt(2))
    total = sum(math.exp(one) for one in scores)
    found = hand_model().predict(("t:deficit", "t:states"))
    assert found == Prediction("spending-da", pytest.approx(math.exp(scores[1]) / total, abs=1e-12))  # pyright: ignore[reportArgumentType]


def test_the_model_file_reads_back_as_written(world: World) -> None:
    path = train(world)
    assert path == queue_order_model_path(world.data_dir, CASELIST, TOPIC)
    assert path.parent == world.data_dir / "landscape" / "local-classifier" / CASELIST
    read = read_model_file(path.read_text(encoding="utf-8"))
    assert read.model == hand_model()
    assert read.sources == tuple(sorted(world.digests))
    assert (read.caselist, read.version, read.topic_id, read.taxonomy_version) == (
        CASELIST,
        PARSER_VERSION,
        TOPIC,
        "1.0.0",
    )


def _rows(seed: int = 5) -> list[FeatureRow]:
    """Cards of twelve invented teams, three in four labelled, tags leaning toward one of three positions."""
    rng = random.Random(seed)
    words = {
        "spending-da": ("deficit", "debt", "spending"),
        "states-cp": ("states", "federalism", "fifty"),
        "cap-k": ("capitalism", "markets", "alienation"),
    }
    filler = ("evidence", "proves", "key", "now", "because")
    rows: list[FeatureRow] = []
    for number in range(240):
        team = f"team-{number % 12}"
        label = rng.choice(sorted(words))
        said = rng.choice(sorted(words)) if rng.random() < 0.3 else label
        tag = " ".join([*rng.sample(words[said], 2), *rng.sample(filler, 2)])
        placed = rng.random() < 0.75
        rows.append(
            FeatureRow(
                item_id=f"{number:04d}",
                source_sha256=f"{number // 4:064x}",
                teams=(team,),
                headings=("1nc", f"{label.split('-')[0]} block") if placed else ("1nc",),
                placing=(False, placed) if placed else (False,),
                tag=tag,
                placement="ALIAS" if placed else "UNPLACED",
                label=label if placed else None,
            )
        )
    return rows


def test_the_written_weights_score_what_scikit_learn_scores() -> None:
    """t21's proxy, trained by `compare` as `train-queue-order` trains it, exported and scored without it."""
    rows = _rows()
    taxonomy = Taxonomy.model_validate(
        {
            "topic_id": TOPIC,
            "taxonomy_version": "1.0.0",
            "event": "POLICY",
            "positions": [
                {"id": "spending-da", "label": "Spending DA", "kind": "da", "side": "neg"},
                {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg"},
                {"id": "cap-k", "label": "Cap K", "kind": "k", "side": "neg"},
            ],
        }
    )
    comparison = compare(taxonomy, rows, without_placing_headings=True, minimum_support=1)
    classifier: LocalClassifier = comparison.classifier
    exported = classifier.queue_order_model(comparison.threshold)
    assert exported.suggest_from == comparison.threshold
    assert exported.without_placing_headings
    reread = QueueOrderModel.from_json(exported.to_json())
    expected = classifier.predict(rows)
    found = [
        reread.predict(reread.tokens(CardFeatures(headings=row.headings, placing=row.placing, tag=row.tag)))
        for row in rows
    ]
    assert sum(one is not None for one in expected) > 200
    for want, got in zip(expected, found, strict=True):
        if want is None:
            assert got is None
            continue
        assert got is not None
        assert got.position_id == want.position_id
        assert got.confidence == pytest.approx(want.confidence, abs=1e-9)


def test_a_two_position_model_scores_as_scikit_learn_keeps_a_binary_one() -> None:
    model = QueueOrderModel(
        classes=("spending-da", "states-cp"),
        vocabulary=("t:deficit", "t:states"),
        idf=array("d", [1.0, 1.0]),
        coefficients=array("d", [-math.log(4), math.log(3)]),
        intercepts=(0.0,),
        suggest_from=THRESHOLD,
    )
    assert model.predict(("t:deficit",)) == Prediction("spending-da", pytest.approx(0.8))  # pyright: ignore[reportArgumentType]
    assert model.predict(("t:states",)) == Prediction("states-cp", pytest.approx(0.75))  # pyright: ignore[reportArgumentType]


def test_a_card_is_read_without_its_teams_names_the_caselists_schools_or_any_team_code() -> None:
    team = SeedTeam(
        identity="Larkspur Point/LaPo", side=Side.NEG, names=("Larkspur Point", "LaPo", TOURNAMENT)
    )
    source = SeedSource(
        sha256="a" * 64,
        teams=(team,),
        cards=(
            SeedCard(
                tag="Larkspur Point LaPo deficit at Sample Classic Juniper Bay JuBa",
                section_path=("Fed Key",),
                first_element_index=0,
            ),
        ),
    )
    names = CaselistNames({"Larkspur Point": ("LaPo",), "Juniper Bay": ("JuBa",)})
    taxonomy = Taxonomy.model_validate(
        {"topic_id": TOPIC, "taxonomy_version": "1.0.0", "event": "POLICY", "positions": []}
    )
    matcher = PositionMatcher(taxonomy, OverrideRules.model_validate({"topic_id": TOPIC, "overrides": []}))
    card = next(item for item in read_items(source, names) if item.kind is ItemKind.CARD)
    features = card_features(card, team.names, names, matcher, frozenset({"lapo", "juba"}))
    assert (features.headings, features.placing, features.tag) == (("fed key",), (False,), "deficit at")
    assert hand_model().tokens(features) == (
        "h:fed",
        "h:key",
        "h:fed key",
        "t:deficit",
        "t:at",
        "t:deficit at",
    )


# ------------------------------------------------------------------------------------------------
# The order
# ------------------------------------------------------------------------------------------------


def _row(heading: str, teams: int) -> ReviewRow:
    return ReviewRow(heading, False, teams, teams, 0, teams, teams, ())


def _queue(*rows: ReviewRow) -> ReviewQueue:
    return ReviewQueue(rows=rows, counts=ReviewQueueCounts(len(rows), len(rows), 0, len(rows), len(rows), 0))


def test_a_rows_score_is_its_best_positions_confidence_over_all_its_cards() -> None:
    def card(*headings: str) -> QueuedItem:
        return QueuedItem(
            source_sha256="b" * 64,
            kind=ItemKind.CARD,
            teams=(),
            headings=tuple(NormalizedHeading(text=one, answer=False) for one in headings),
        )

    section = QueuedItem(
        source_sha256="b" * 64,
        kind=ItemKind.SECTION,
        teams=(),
        headings=(NormalizedHeading(text="mixed group", answer=False),),
    )
    items = [card("mixed group"), card("mixed group"), card("mixed group"), card("mixed group"), section]
    predictions = [
        Prediction("spending-da", 0.8),
        Prediction("spending-da", 0.8),
        Prediction("states-cp", 0.6),
        None,
        Prediction("cap-k", 0.99),
    ]
    assert row_scores(items, predictions) == {
        ("mixed group", False): RowScore(pytest.approx(0.4), "spending-da")  # pyright: ignore[reportArgumentType]
    }
    assert row_scores([card("theory group")], [None]) == {}


def test_tied_rows_and_unscored_rows_keep_todays_order() -> None:
    today = _queue(
        _row("unscored one", 9), _row("tie first", 8), _row("tie second", 7), _row("unscored two", 6)
    )
    scores = {("tie second", False): RowScore(0.7, "cap-k"), ("tie first", False): RowScore(0.7, "cap-k")}
    ordered = order_review_queue(today, scores, THRESHOLD)
    assert [row.normalized_heading for row in ordered.rows] == [
        "tie first",
        "tie second",
        "unscored one",
        "unscored two",
    ]
    assert ordered.counts == today.counts


def test_the_queue_is_ordered_by_confidence_with_suggestions_only_at_or_above_the_threshold(
    world: World,
) -> None:
    train(world)
    result, text = run(world, "ordered")
    rows = result.classification.review_queue.rows
    assert headings_of(result) == ORDERED
    assert {row.normalized_heading: row.suggested_position for row in rows} == {
        heading: SUGGESTED.get(heading) for heading in ORDERED
    }
    confidence = {row.normalized_heading: row.proxy_confidence for row in rows}
    assert confidence == {
        "debt group": pytest.approx(0.8),
        "deficits group": pytest.approx(0.8),
        "uniformity": pytest.approx(0.6),
        "commodity frame": pytest.approx(0.5),
        "mixed group": pytest.approx(0.4),
        "fed key": pytest.approx(1 / 3),
        "theory group": None,
    }
    assert result.classification.review_queue_ordered
    assert result.classification.review_queue_order == (
        "Review queue order: by the local proxy model's confidence, highest first (trained on 22 cards "
        "through 2026-09-15); a suggestion is shown at 0.50 or above; nothing is placed by it."
    )
    written = csv_rows(text)
    assert tuple(written[0]) == ORDERED_REVIEW_QUEUE_COLUMNS
    assert [(one["normalized_heading"], one["suggested_position"], one["decision"]) for one in written] == [
        (heading, SUGGESTED.get(heading, ""), "") for heading in ORDERED
    ]


def test_without_a_model_the_queue_is_todays_with_a_line_saying_why(world: World) -> None:
    result, text = run(world, "today")
    assert headings_of(result) == TODAYS_ORDER
    assert all(row.suggested_position is None for row in result.classification.review_queue.rows)
    assert not result.classification.review_queue_ordered
    assert result.classification.review_queue_order == (
        f"Review queue order: off, today's order kept: no review-order model is trained for {CASELIST} on "
        f"{TOPIC} (`scripts/compare_local_classifier.py train-queue-order`)."
    )
    assert text.splitlines()[0] == ",".join(REVIEW_QUEUE_COLUMNS)
    _, unwired = run(world, "unwired", ordering=False)
    assert text == unwired


def test_a_model_suggests_nothing_when_no_confidence_reached_the_target(world: World) -> None:
    train(world, hand_model(suggest_from=None))
    result, text = run(world, "no-threshold")
    assert headings_of(result) == ORDERED
    assert all(row.suggested_position is None for row in result.classification.review_queue.rows)
    assert {one["suggested_position"] for one in csv_rows(text)} == {""}
    assert "no suggestion is shown" in (result.classification.review_queue_order or "")


# ------------------------------------------------------------------------------------------------
# Nothing is placed by it
# ------------------------------------------------------------------------------------------------


def test_the_reports_placements_counts_and_files_are_byte_identical_with_and_without_the_model(
    world: World,
) -> None:
    without, _ = run(world, "without")
    shutil.rmtree(world.data_dir / "landscape" / "classifications")
    train(world)
    with_model, text = run(world, "with")
    assert with_model.classification.counts.misses == without.classification.counts.misses > 0
    assert with_model.classification.review_queue_ordered
    assert with_model.classification.classifications == without.classification.classifications
    assert with_model.classification.counts == without.classification.counts
    assert with_model.classification.review_queue.counts == without.classification.review_queue.counts
    assert sorted(
        (row.normalized_heading, row.documents, row.teams, row.cards)
        for row in with_model.classification.review_queue.rows
    ) == sorted(
        (row.normalized_heading, row.documents, row.teams, row.cards)
        for row in without.classification.review_queue.rows
    )
    for name in BUNDLE_FILES:
        assert (world.data_dir.parent / "with" / name).read_bytes() == (
            world.data_dir.parent / "without" / name
        ).read_bytes(), name
    assert with_model.report == without.report
    assert read_decisions_csv(io.StringIO(text)) == ()


def test_no_card_is_placed_under_the_models_guess(world: World) -> None:
    train(world)
    result, _ = run(world, "placed")
    placed = {one.position_id for one in result.classification.classifications if one.position_id is not None}
    assert placed == set()
    assert result.classification.counts.cards_counted == 0


# ------------------------------------------------------------------------------------------------
# Refused: the queue is today's, with the reason
# ------------------------------------------------------------------------------------------------


def _refused(world: World, out: str) -> tuple[LandscapeRunResult, str]:
    """A run whose model is refused: its queue is exactly the one a run without any ordering writes."""
    result, text = run(world, out)
    today, unwired = run(world, f"{out}-unwired", ordering=False)
    assert text == unwired
    assert result.classification.review_queue.rows == today.classification.review_queue.rows
    assert not result.classification.review_queue_ordered
    assert text.splitlines()[0] == ",".join(REVIEW_QUEUE_COLUMNS)
    return result, text


def test_a_model_whose_training_source_a_removal_suppressed_is_refused(world: World) -> None:
    train(world)
    suppress(world, world.digests[2])
    result, _ = _refused(world, "suppressed")
    assert result.classification.review_queue_order == (
        "Review queue order: off, today's order kept: a removal has reached 1 of the 6 sources the "
        "review-order model was trained from, or this store no longer holds them parsed; train it again "
        "(`scripts/compare_local_classifier.py train-queue-order`)."
    )


def test_a_model_whose_training_disclosure_a_removal_suppressed_is_refused(world: World) -> None:
    train(world)
    suppress(world, world.digests[4], world.paths[4])
    result, _ = _refused(world, "disclosure")
    assert "a removal has reached 1 of the 6 sources" in (result.classification.review_queue_order or "")


def test_a_disclosure_suppressed_before_training_does_not_refuse_the_model(world: World) -> None:
    suppress(world, world.digests[4], world.paths[4])
    built = (world.digests[4], disclosure_digest(CASELIST, world.paths[4]))
    train(world, suppressed_at_build=(built,), sources=tuple(sorted(world.digests[:4] + world.digests[5:])))
    result, _ = run(world, "known")
    assert result.classification.review_queue_ordered


def test_a_model_trained_on_a_source_the_store_no_longer_holds_parsed_is_refused(world: World) -> None:
    train(world, sources=tuple(sorted((*world.digests, "f" * 64))))
    result, _ = _refused(world, "gone")
    assert "a removal has reached 1 of the 7 sources" in (result.classification.review_queue_order or "")


def test_a_model_trained_under_another_taxonomy_version_is_refused(world: World) -> None:
    train(world, taxonomy_version="0.9.0")
    result, _ = _refused(world, "taxonomy")
    assert result.classification.review_queue_order == (
        "Review queue order: off, today's order kept: the review-order model was trained under taxonomy "
        f"0.9.0 and {TOPIC} is now 1.0.0; train it again."
    )


@pytest.mark.parametrize("text", ["", "{}", '{"schema": "review-queue-order-model-1"}', "not json"])
def test_a_model_file_that_cannot_be_read_is_refused(world: World, text: str) -> None:
    path = train(world)
    path.write_text(text, encoding="utf-8")
    result, _ = _refused(world, "unreadable")
    assert result.classification.review_queue_order is not None
    assert result.classification.review_queue_order.startswith(
        f"Review queue order: off, today's order kept: the review-order model at {path} cannot be read ("
    )


def test_a_model_trained_for_another_caselist_is_refused(world: World) -> None:
    path = train(world, caselist="hsld99")
    assert path.parent.name == CASELIST
    result, _ = _refused(world, "elsewhere")
    assert "was trained for hsld99" in (result.classification.review_queue_order or "")


# ------------------------------------------------------------------------------------------------
# What it may import
# ------------------------------------------------------------------------------------------------

ORDERING_MODULES = (
    REPO / "packages/debate_core/src/debate_core/arguments/landscape/queue_order.py",
    REPO / "packages/debate_core/src/debate_core/application/review_queue_order.py",
)


def test_the_order_reads_no_network_model_or_download() -> None:
    allowed = {
        "__future__",
        "array",
        "base64",
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "itertools",
        "json",
        "math",
        "operator",
        "sys",
        "typing",
    }
    for path in ORDERING_MODULES:
        imported: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
        outside = {name for name in imported if name not in allowed and not name.startswith("debate_core.")}
        assert outside == set(), f"{path.name} imports {sorted(outside)}"
        assert not any(
            "local_classifier" in name or "integrations" in name or "model_router" in name
            for name in imported
        ), path.name


def test_a_run_orders_its_queue_without_scikit_learn() -> None:
    """An installed build has no scikit-learn: the run's modules never load it."""
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import debate_core.application.landscape_run, "
            "debate_core.application.review_queue_order, debate_core.arguments.landscape.queue_order; "
            "print(sorted(one for one in sys.modules if one.split('.')[0] in ('sklearn', 'numpy', 'scipy')))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.strip() == "[]"

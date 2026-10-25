"""The local classifier against the deterministic placements (`v1-e32-t21-local-classifier-comparison` ac1).

On a synthetic caselist: training and scoring are deterministic for a fixed seed, whatever order the
cards arrive in; no school, team code, tournament or debater's name is ever a feature, and no cite
is read; the held-out tenth is split by document; the labels are the deterministic placements at or
above the review threshold; and the counts, the threshold and the coach sample's strata and scores
are the ones worked out by hand below (working agreement 6).

Every school, team code, tournament, debater, author, heading and tag here is invented.
"""

from __future__ import annotations

import ast
import io
import random
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from debate_core.arguments.landscape import local_classifier as module
from debate_core.arguments.landscape.local_classifier import (
    BELOW_THRESHOLD,
    DECIDED_NO_POSITION,
    NO_POSITION_LABEL,
    SAMPLE_COLUMNS,
    UNPLACED,
    WITHHELD_HEADING,
    CoachSample,
    Comparison,
    FeatureRow,
    HeldOutMeasure,
    LocalClassifier,
    Prediction,
    SampleItem,
    card_tag,
    coach_sample,
    code_words,
    compare,
    feature_rows,
    feature_tokens,
    heading_teams,
    held_out_documents,
    measure_held_out,
    read_sample,
    read_sample_labels,
    row_from_json,
    row_to_json,
    sample_lines,
    score_sample,
    team_token,
    team_vocabulary,
    write_sample_csv,
)
from debate_core.arguments.landscape.matcher import PositionMatcher
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules

REPO = Path(__file__).resolve().parents[5]
MODULES = (
    REPO / "packages/debate_core/src/debate_core/arguments/landscape/local_classifier.py",
    REPO / "packages/debate_core/src/debate_core/application/local_classifier_comparison.py",
)

# ------------------------------------------------------------------------------------------------
# A synthetic caselist
# ------------------------------------------------------------------------------------------------

SCHOOLS = {
    "Maple Grove": ("MaGr", "MaGo"),
    "Cedar Ridge": ("CeRi", "CeRd"),
    "Birch Hollow": ("BiHo", "BiHl"),
    "Aspen Falls": ("AsFa", "AsFl"),
    "Willow Creek": ("WiCr", "WiCk"),
    "Oak Harbor": ("OaHa", "OaHr"),
}
TOURNAMENT = "Quarry Lakes Classic"
DEBATER = "Quillonsby"
"""A debater's name, only in the tags of the team `MaGr`."""
AUTHOR = "Zorblatt"
"""An author in every card's short cite, which the classifier never reads."""
OTHER_TEAMS_CODE = "CeRi"
"""A code of another school, alone in some of `MaGr`'s tags."""

WORDS = {
    "spending-da": ("Spending DA", ("deficit", "debt", "spending", "fiscal")),
    "states-cp": ("States CP", ("states", "federalism", "fifty", "uniformity")),
    "cap-k": ("Cap K", ("capitalism", "commodification", "markets", "alienation")),
    "costs-advantage": ("Costs Advantage", ("premiums", "affordability", "bankruptcy", "costs")),
}
FILLER = ("evidence", "proves", "key", "now", "only", "causes", "solves", "because")
KINDS = {"spending-da": "da", "states-cp": "cp", "cap-k": "k", "costs-advantage": "advantage"}
NOISE = 0.35
"""The share of placed cards whose tag speaks for a position drawn at random, as a real tag often does."""

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": position_id,
                "label": label,
                "kind": KINDS[position_id],
                "side": "aff" if KINDS[position_id] == "advantage" else "neg",
                "aliases": [label.casefold()],
            }
            for position_id, (label, _) in WORDS.items()
        ],
    }
)
NAMES = CaselistNames(SCHOOLS)
MATCHER = PositionMatcher(
    TAXONOMY, OverrideRules.model_validate({"topic_id": TAXONOMY.topic_id, "overrides": []})
)


def _tag(rng: random.Random, position_id: str, school: str, code: str) -> str:
    words = [*rng.sample(WORDS[position_id][1], 3), *rng.sample(FILLER, 2)]
    extra = rng.random()
    if extra < 0.2:
        words.insert(0, school)
    elif extra < 0.35:
        words.append(code)
    elif extra < 0.45:
        words.insert(1, "Cedar Ridge" if school != "Cedar Ridge" else "Oak Harbor")
    elif extra < 0.5:
        words.append(TOURNAMENT)
    if code == "MaGr" and rng.random() < 0.5:
        words.append(DEBATER)
    if code == "MaGr" and rng.random() < 0.3:
        words.append(OTHER_TEAMS_CODE)
    return " ".join(words).capitalize()


def synthetic_sources(seed: int = 7) -> tuple[SeedSource, ...]:
    """Twelve teams, three documents each: eight placed cards and two unplaced ones per document.

    About a third of the placed cards' tags speak for a position drawn at random, so a model reading
    tags alone is unsure of some cards and wrong about some.
    """
    rng = random.Random(seed)
    sources: list[SeedSource] = []
    number = 0
    for school, codes in SCHOOLS.items():
        for code in codes:
            team = SeedTeam(identity=f"{school}/{code}", side=Side.NEG, names=(school, code, TOURNAMENT))
            for _ in range(3):
                number += 1
                cards: list[SeedCard] = []
                for position_id in rng.sample(sorted(WORDS), 2):
                    label = WORDS[position_id][0]
                    pocket = rng.choice(("1NC", f"{school} {code} Neg", f"{TOURNAMENT} Round 2"))
                    for _ in range(4):
                        said = rng.choice(sorted(WORDS)) if rng.random() < NOISE else position_id
                        cards.append(
                            SeedCard(
                                tag=_tag(rng, said, school, code),
                                section_path=(pocket, label) if rng.random() < 0.7 else (label, "Link"),
                                short_cite=f"{AUTHOR} 24",
                            )
                        )
                for _ in range(2):
                    position_id = rng.choice(sorted(WORDS))
                    cards.append(
                        SeedCard(
                            tag=_tag(rng, position_id, school, code),
                            section_path=rng.choice((("1NC", "Solvency"), ("Off",), ())),
                            short_cite=f"{AUTHOR} 24",
                        )
                    )
                sources.append(
                    SeedSource(
                        sha256=f"{number:064x}",
                        teams=(team,),
                        cards=tuple(
                            SeedCard(
                                tag=card.tag,
                                section_path=card.section_path,
                                first_element_index=index * 3,
                                short_cite=card.short_cite,
                            )
                            for index, card in enumerate(cards)
                        ),
                    )
                )
    return tuple(sources)


SOURCES = synthetic_sources()
CODES = code_words(SCHOOLS)
SALT = b"an invented salt"
ROWS = tuple(
    row for source in SOURCES for row in feature_rows(source, NAMES, MATCHER, team_salt=SALT, codes=CODES)
)
FORBIDDEN = {
    word.casefold()
    for school, codes in SCHOOLS.items()
    for word in (*school.split(), *codes, *TOURNAMENT.split(), AUTHOR)
}


@pytest.fixture(scope="module")
def specified() -> Comparison:
    return compare(TAXONOMY, ROWS, seed=5, minimum_support=1)


@pytest.fixture(scope="module")
def proxy() -> Comparison:
    return compare(TAXONOMY, ROWS, seed=5, without_placing_headings=True, minimum_support=1)


def test_the_synthetic_caselist_is_as_planted() -> None:
    placements = Counter(row.placement for row in ROWS)
    assert len(SOURCES) == 36
    assert len(ROWS) == 36 * 10
    assert set(placements) == {"ALIAS", "INHERITED", UNPLACED}
    assert placements[UNPLACED] == 36 * 2
    assert placements["ALIAS"] + placements["INHERITED"] == 36 * 8
    assert sum(row.label is not None for row in ROWS) == 36 * 8


# ------------------------------------------------------------------------------------------------
# Deterministic for a seed
# ------------------------------------------------------------------------------------------------


def test_training_and_scoring_are_the_same_for_a_seed_whatever_order_the_cards_arrive_in() -> None:
    first = compare(TAXONOMY, ROWS, seed=5, minimum_support=1)
    shuffled = list(ROWS)
    random.Random(3).shuffle(shuffled)
    second = compare(TAXONOMY, shuffled, seed=5, minimum_support=1)
    assert first == second
    assert first.classifier.vocabulary == second.classifier.vocabulary
    assert dict(first.predictions) == dict(second.predictions)
    assert first.held_out.predicted > 0
    assert first.would_place[0].cards == 72


def test_the_coach_sample_is_the_same_for_a_seed() -> None:
    def drawn(rows: tuple[FeatureRow, ...]) -> CoachSample:
        models = {
            "specified": compare(TAXONOMY, rows, seed=5, minimum_support=1),
            "proxy": compare(TAXONOMY, rows, seed=5, without_placing_headings=True, minimum_support=1),
        }
        return coach_sample(TAXONOMY, rows, models, stratified_by="proxy", seed=5)

    first = drawn(ROWS)
    assert first == drawn(tuple(reversed(ROWS)))
    assert first.items


def test_another_seed_holds_out_other_documents() -> None:
    documents = [source.sha256 for source in SOURCES]
    assert held_out_documents(documents, 5) == held_out_documents(reversed(documents), 5)
    assert held_out_documents(documents, 5) != held_out_documents(documents, 6)


# ------------------------------------------------------------------------------------------------
# Never a school, team code or name
# ------------------------------------------------------------------------------------------------


def _words(tokens: object) -> set[str]:
    """The words of feature tokens, with or without their `h:` or `t:` field."""
    return {word for token in cast(list[str], tokens) for word in token.split(":", 1)[-1].split()}


def test_no_school_team_code_tournament_or_cite_reaches_a_cards_features() -> None:
    assert any(DEBATER.casefold() in (row.tag or "") for row in ROWS), "the debater's name is planted in tags"
    for row in ROWS:
        assert _words(list(feature_tokens(row))) & FORBIDDEN == set(), row.item_id


def test_no_school_team_code_or_name_is_a_feature(specified: Comparison, proxy: Comparison) -> None:
    for comparison in (specified, proxy):
        vocabulary = _words(list(comparison.classifier.vocabulary))
        assert vocabulary & FORBIDDEN == set()
        assert DEBATER.casefold() not in vocabulary
        assert OTHER_TEAMS_CODE.casefold() not in vocabulary
        assert {"deficit", "states", "capitalism", "premiums"} <= vocabulary


def test_only_the_team_rule_keeps_one_teams_words_out() -> None:
    """A debater's name one team writes is in its tags; with a one-team rule it would be a feature."""
    loose = LocalClassifier.train(ROWS, seed=5, minimum_teams=1)
    assert DEBATER.casefold() in _words(list(loose.vocabulary))


def test_another_teams_code_alone_in_a_tag_is_taken_out() -> None:
    planted = [
        card.tag
        for source in SOURCES
        for card in source.cards
        if OTHER_TEAMS_CODE.casefold() in (card.tag or "").casefold().split()
    ]
    assert planted, "another team's code is planted in tags"
    assert not any(OTHER_TEAMS_CODE.casefold() in (row.tag or "").split() for row in ROWS)


def test_a_cards_tag_loses_its_teams_names_and_the_caselists_schools() -> None:
    names = ["Maple Grove", "MaGr", TOURNAMENT]
    assert card_tag("Maple Grove's MaGr evidence proves deficit", names, NAMES) == "s evidence proves deficit"
    assert card_tag("Cedar Ridge CeRi says states solve", names, NAMES) == "says states solve"
    assert card_tag("CeRi alone is a word", names, NAMES) == "ceri alone is a word"
    assert card_tag("CeRi alone is a word", names, NAMES, code_words(SCHOOLS)) == "alone is a word"
    assert code_words({"Maple Grove": ("MaGr", "Ma-Go")}) == {"magr", "ma", "go"}
    assert card_tag("Quarry Lakes Classic", names, NAMES) is None
    assert card_tag(None, names, NAMES) is None


def test_team_vocabulary_counts_distinct_teams_and_no_unknown_team() -> None:
    documents = [
        (("t:a", "t:b"), ("one",)),
        (("t:a", "t:a"), ("two",)),
        (("t:a", "t:b"), ("one",)),
        (("t:b", "t:c"), ()),
        (("t:c",), ("two", "three")),
    ]
    assert team_vocabulary(documents, 2) == ("t:a", "t:c")
    assert team_vocabulary(documents, 3) == ()


def test_the_classifier_reads_no_network_model_or_download() -> None:
    allowed = {
        "__future__",
        "collections",
        "collections.abc",
        "csv",
        "dataclasses",
        "datetime",
        "hashlib",
        "itertools",
        "json",
        "re",
        "secrets",
        "typing",
        "sklearn.feature_extraction.text",
        "sklearn.linear_model",
    }
    for path in MODULES:
        imported: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
        outside = {name for name in imported if name not in allowed and not name.startswith("debate_core.")}
        assert outside == set(), f"{path.name} imports {sorted(outside)}"
        assert not any("model_router" in name or "integrations" in name for name in imported), path.name


# ------------------------------------------------------------------------------------------------
# What it reads, and the labels
# ------------------------------------------------------------------------------------------------

LABEL_TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": "spending-da",
                "label": "Spending",
                "kind": "da",
                "side": "neg",
                "aliases": ["spending da"],
            },
            {
                "id": "deficit-spending-da",
                "label": "Deficit",
                "kind": "da",
                "side": "neg",
                "parent": "spending-da",
                "tag_keywords": ["deficit hawks"],
            },
            {
                "id": "states-cp",
                "label": "States",
                "kind": "cp",
                "side": "neg",
                "tag_keywords": ["fifty states"],
            },
        ],
    }
)
LABEL_MATCHER = PositionMatcher(
    LABEL_TAXONOMY,
    OverrideRules.model_validate(
        {
            "topic_id": "policy-sample-topic",
            "overrides": [
                {"heading": "fiscal cliff", "position_id": "spending-da"},
                {"heading": "solvency", "position_id": None},
            ],
        }
    ),
)


def test_the_labels_are_the_deterministic_placements_at_or_above_the_threshold() -> None:
    source = SeedSource(
        sha256="a" * 64,
        teams=(SeedTeam(identity="one", side=Side.NEG, names=("Maple Grove",)),),
        cards=tuple(
            SeedCard(tag=tag, section_path=path, first_element_index=index * 3)
            for index, (path, tag) in enumerate(
                [
                    (("1NC", "Spending DA"), "Spending crowds out"),
                    (("Spending DA", "Link"), "Plan spends"),
                    (("Fiscal Cliff",), "Cliff now"),
                    (("Spending DA",), "Deficit hawks win"),
                    (("1NC",), "The fifty states solve"),
                    (("Solvency",), "It solves"),
                    (("Maple Grove Neg", "Framing"), "Utilitarianism"),
                ]
            )
        ),
    )
    rows = feature_rows(source, NAMES, LABEL_MATCHER, team_salt=SALT)
    assert [(row.placement, row.label) for row in rows] == [
        ("ALIAS", "spending-da"),
        ("INHERITED", "spending-da"),
        ("OVERRIDE", "spending-da"),
        ("TAG_KEYWORD", "deficit-spending-da"),
        (BELOW_THRESHOLD, None),
        (DECIDED_NO_POSITION, None),
        (UNPLACED, None),
    ]
    assert [row.headings for row in rows] == [
        ("spending da",),
        ("spending da", "link"),
        ("fiscal cliff",),
        ("spending da",),
        (),
        ("solvency",),
        ("framing",),
    ]
    assert [row.placing for row in rows][:3] == [(True,), (True, False), (True,)]
    assert rows[5].placing == (False,)
    assert rows[0].teams == (team_token("one", SALT),)
    assert team_token("one", SALT) != team_token("one", b"another salt")
    assert "one" not in row_to_json(rows[0])


def test_feature_tokens_keep_headings_and_the_tag_apart() -> None:
    row = FeatureRow(
        item_id="x",
        source_sha256="a" * 64,
        teams=("one",),
        headings=("spending da", "link"),
        placing=(True, False),
        tag="plan spends now",
        placement="INHERITED",
        label="spending-da",
    )
    assert feature_tokens(row) == (
        "h:spending",
        "h:da",
        "h:spending da",
        "h:link",
        "t:plan",
        "t:spends",
        "t:now",
        "t:plan spends",
        "t:spends now",
    )
    assert feature_tokens(row, without_placing_headings=True) == (
        "h:link",
        "t:plan",
        "t:spends",
        "t:now",
        "t:plan spends",
        "t:spends now",
    )
    assert row_from_json(row_to_json(row)) == row


# ------------------------------------------------------------------------------------------------
# The split and the measure
# ------------------------------------------------------------------------------------------------


def test_the_held_out_tenth_is_split_by_document(specified: Comparison) -> None:
    held = held_out_documents(source.sha256 for source in SOURCES)
    assert len(held) == 4  # round(36 / 10)
    assert specified.documents == 36 and specified.held_out_documents == 4
    assert specified.held_out.cards == 4 * 8
    assert held_out_documents(["a" * 64, "b" * 64]) and len(held_out_documents(["a" * 64])) == 0


def test_the_specified_model_reads_its_labels_headings_and_the_proxy_does_not(
    specified: Comparison, proxy: Comparison
) -> None:
    assert specified.held_out.correct == specified.held_out.cards
    assert proxy.held_out.correct <= specified.held_out.correct
    assert not any(token.startswith("h:") and "spending" in token for token in proxy.classifier.vocabulary)


MEASURE_TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "spending-da", "label": "Spending", "kind": "da", "side": "neg"},
            {"id": "politics-da", "label": "Politics", "kind": "da", "side": "neg"},
            {"id": "states-cp", "label": "States", "kind": "cp", "side": "neg"},
        ],
    }
)


def test_held_out_precision_and_recall_by_kind_position_and_confidence_worked_by_hand() -> None:
    labels = [
        "spending-da",  # 1 predicted spending 0.97, right
        "spending-da",  # 2 predicted spending 0.92, right
        "spending-da",  # 3 predicted politics 0.55: wrong, but the right kind
        "spending-da",  # 4 no feature, so no prediction
        "politics-da",  # 5 predicted politics 0.81, right
        "politics-da",  # 6 predicted states 0.42: wrong kind
        "states-cp",  # 7 predicted states 0.99, right
        "states-cp",  # 8 predicted states 0.65, right
        "states-cp",  # 9 predicted spending 0.31: wrong kind
        "states-cp",  # 10 predicted states 0.88, right
    ]
    predictions = [
        Prediction("spending-da", 0.97),
        Prediction("spending-da", 0.92),
        Prediction("politics-da", 0.55),
        None,
        Prediction("politics-da", 0.81),
        Prediction("states-cp", 0.42),
        Prediction("states-cp", 0.99),
        Prediction("states-cp", 0.65),
        Prediction("spending-da", 0.31),
        Prediction("states-cp", 0.88),
    ]
    seen = [True, False, False, False, True, False, True, False, False, False]
    measure = measure_held_out(MEASURE_TAXONOMY, labels, predictions, seen=seen, minimum_support=3)
    assert (measure.cards, measure.predicted, measure.correct) == (10, 9, 6)
    assert [
        (one.name, one.held_out, one.predicted, one.correct, one.right_kind) for one in measure.by_kind
    ] == [
        ("cp", 4, 4, 3, 3),
        ("da", 6, 5, 3, 4),
    ]
    assert [(one.name, one.held_out, one.predicted, one.correct) for one in measure.by_position] == [
        ("politics-da", 2, 2, 1),
        ("spending-da", 4, 3, 2),
        ("states-cp", 4, 4, 3),
    ]
    assert measure.by_position[1].precision == pytest.approx(2 / 3)
    assert measure.by_position[1].recall == pytest.approx(2 / 4)
    assert [(one.low, one.cards, one.correct) for one in measure.bands] == [
        (0.0, 0, 0),
        (0.3, 2, 0),  # 0.31, 0.42
        (0.5, 1, 0),  # 0.55
        (0.6, 1, 1),  # 0.65
        (0.7, 0, 0),
        (0.8, 2, 2),  # 0.81, 0.88
        (0.9, 1, 1),  # 0.92
        (0.95, 2, 2),  # 0.97, 0.99
    ]
    above = {round(one.low, 3): (one.cards, one.correct) for one in measure.at_or_above}
    assert above[0.3] == (9, 6)
    assert above[0.45] == (7, 6)
    assert above[0.6] == (6, 6)
    assert above[0.95] == (2, 2)
    assert above[0.99] == (1, 1)
    # Precision is 6/7 (85.7%) from 0.45 and 6/6 from 0.6; 0.975 and 0.99 have under 3 cards.
    assert measure.confidence_at_target == 0.6
    assert (measure.seen_in_training, measure.seen_in_training_correct) == (3, 3)
    unseen = {round(one.low, 3): (one.cards, one.correct) for one in measure.unseen_at_or_above}
    assert unseen[0.0] == (6, 3)
    assert unseen[0.6] == (3, 3)


def test_the_precision_estimate_weighs_held_out_precision_to_the_placed_cards_mix() -> None:
    labels = ["spending-da"] * 2 + ["politics-da"] * 2 + ["states-cp"] * 3
    held_out = measure_held_out(
        MEASURE_TAXONOMY,
        [*labels, "states-cp", "states-cp", "states-cp"],
        [
            Prediction("spending-da", 0.97),  # seen, right
            Prediction("spending-da", 0.92),  # unseen, right
            Prediction("politics-da", 0.81),  # seen, right
            Prediction("states-cp", 0.42),  # unseen, wrong
            Prediction("states-cp", 0.99),  # seen, right
            Prediction("states-cp", 0.65),  # unseen, right
            Prediction("states-cp", 0.88),  # unseen, right
            Prediction("politics-da", 0.55),  # unseen, wrong
            Prediction("spending-da", 0.31),  # unseen, wrong
            None,
        ],
        seen=[True, False, True, False, True, False, False, False, False, False],
        minimum_support=1,
    )
    placed = [
        (True, Prediction("spending-da", 0.5)),
        (False, Prediction("states-cp", 0.5)),
        (False, Prediction("states-cp", 0.7)),
        (False, Prediction("cap-k", 0.99)),
    ]
    estimates, threshold = module.estimate_precision(held_out, placed, minimum_support=1)
    found = {round(one.confidence, 3): (one.cards, one.seen, one.precision) for one in estimates}
    # From 0.45 the held-out seen cards are 3 of 3 right and the unseen 3 of 4 (0.92, 0.55, 0.65,
    # 0.88): all four placed cards, one seen, give (1 * 1 + 3 * 0.75) / 4.
    assert found[0.45] == (4, 1, pytest.approx(0.8125))
    # From 0.55 two unseen cards are placed, and the unseen held-out cards are still 3 of 4.
    assert found[0.55] == (2, 0, pytest.approx(0.75))
    # From 0.6 the unseen held-out cards are 0.92, 0.65 and 0.88, all right.
    assert found[0.6] == (2, 0, pytest.approx(1.0))
    # From 0.95 no unseen held-out card is left to say how the 0.99 card would do.
    assert found[0.95] == (1, 0, None)
    assert threshold == 0.6


def test_the_cards_placed_at_the_estimated_confidence_are_counted_by_kind() -> None:
    proxy = compare(TAXONOMY, ROWS, seed=7, without_placing_headings=True, minimum_support=1)
    unplaced = proxy.would_place[0]
    assert unplaced.placement == UNPLACED and unplaced.estimated_threshold is not None
    assert unplaced.estimated_threshold != proxy.threshold, "seed 7 puts the two confidences apart"
    at = next(one for one in unplaced.estimates if one.confidence == unplaced.estimated_threshold)
    assert sum(count for _, count in unplaced.by_kind_at_estimated) == at.cards > 0
    expected = Counter(
        KINDS[prediction.position_id]
        for row in ROWS
        if row.placement == UNPLACED
        and (prediction := proxy.predictions[row.item_id]) is not None
        and prediction.confidence >= unplaced.estimated_threshold
    )
    assert dict(unplaced.by_kind_at_estimated) == dict(expected)


def test_a_thin_point_is_passed_over_and_a_supported_failure_stops_the_threshold() -> None:
    labels = ["spending-da"] * 6
    predictions = [
        Prediction("states-cp", 0.995),  # one wrong card above 0.99: too few to fail on
        Prediction("spending-da", 0.96),
        Prediction("spending-da", 0.96),
        Prediction("spending-da", 0.96),
        Prediction("states-cp", 0.7),
        Prediction("states-cp", 0.7),
    ]
    measure = measure_held_out(MEASURE_TAXONOMY, labels, predictions, minimum_support=3)
    # From 0.95: 3 of 4 (75%), so no threshold reaches 90%.
    assert measure.confidence_at_target is None
    measure = measure_held_out(MEASURE_TAXONOMY, labels[:5], predictions[1:], minimum_support=3)
    # From 0.95 down to 0.75: 3 of 3; from 0.7: 3 of 5, supported, so the threshold stays at 0.75.
    assert measure.confidence_at_target == 0.75


# ------------------------------------------------------------------------------------------------
# The coach sample
# ------------------------------------------------------------------------------------------------


def _comparison(threshold: float | None, predictions: dict[str, Prediction | None]) -> Comparison:
    empty = HeldOutMeasure(0, 0, 0, (), (), (), (), threshold)
    return Comparison(
        without_placing_headings=True,
        seed=1,
        documents=0,
        held_out_documents=0,
        trained_cards=0,
        classes=0,
        features=0,
        held_out=empty,
        threshold=threshold,
        would_place=(),
        classifier=cast(Any, None),
        predictions=predictions,
    )


def _row(
    item_id: str, source: str, placement: str = UNPLACED, headings: tuple[str, ...] = ("link",)
) -> FeatureRow:
    return FeatureRow(
        item_id=item_id,
        source_sha256=source,
        teams=(source,),
        headings=headings,
        placing=tuple(False for _ in headings),
        tag=f"tag of {item_id}",
        placement=placement,
        label=None,
    )


def test_the_sample_strata_and_one_card_per_document_worked_by_hand() -> None:
    rows = [
        _row("c1", "d1"),
        _row("c2", "d2"),
        _row("c3", "d3"),
        _row("c4", "d4"),
        _row("c5", "d5"),
        _row("c6", "d6"),
        _row("c7", "d7"),
        _row("c8", "d7"),  # the same document as c7
        _row("c9", "d9", placement=DECIDED_NO_POSITION),  # not unplaced
        _row("c10", "d10"),  # no prediction
    ]
    confidences = {
        "c1": 0.9,
        "c2": 0.6,
        "c3": 0.5,
        "c4": 0.4,
        "c5": 0.3,
        "c6": 0.2,
        "c7": 0.1,
        "c8": 0.1,
        "c9": 0.95,
    }
    predictions: dict[str, Prediction | None] = {
        item_id: Prediction("spending-da" if item_id in ("c1", "c3") else "states-cp", one)
        for item_id, one in confidences.items()
    }
    predictions["c10"] = None
    sample = coach_sample(
        MEASURE_TAXONOMY,
        rows,
        {"proxy": _comparison(0.6, predictions), "specified": _comparison(0.0, predictions)},
        stratified_by="proxy",
    )
    # At or above 0.6: c1, c2. Below: 0.5, 0.4, 0.3, 0.2, 0.1, 0.1, median 0.3, so c3, c4, c5 just below
    # and c6 with one of c7 and c8, whichever comes first, far below.
    by_stratum = {item.item_id: item.stratum for item in sample.items}
    assert {key: value for key, value in by_stratum.items() if key not in ("c7", "c8")} == {
        "c1": "at-or-above-threshold",
        "c2": "at-or-above-threshold",
        "c3": "just-below-threshold",
        "c4": "just-below-threshold",
        "c5": "just-below-threshold",
        "c6": "far-below-threshold",
    }
    assert len({"c7", "c8"} & set(by_stratum)) == 1
    assert sample.populations == {
        "at-or-above-threshold": 2,
        "just-below-threshold": 3,
        "far-below-threshold": 3,
    }
    assert sorted(item.sample_row for item in sample.items) == list(range(1, 8))
    assert sample.thresholds == {"proxy": 0.6, "specified": 0.0}
    assert all(set(item.predictions) == {"proxy", "specified"} for item in sample.items)


def test_a_stratum_short_of_cards_passes_its_share_on() -> None:
    rows = [_row(f"c{number}", f"d{number}") for number in range(80)]
    predictions: dict[str, Prediction | None] = {
        f"c{number}": Prediction("spending-da", 0.95 if number < 5 else 0.4) for number in range(80)
    }
    sample = coach_sample(
        MEASURE_TAXONOMY, rows, {"proxy": _comparison(0.9, predictions)}, stratified_by="proxy"
    )
    strata = Counter(item.stratum for item in sample.items)
    assert len(sample.items) == 60
    # Every card below 0.9 is at 0.4, the median, so all 75 are just below and none far below: the top
    # stratum's 25 short pass on, and the far stratum's 10 come back to the just-below one.
    assert strata == {"at-or-above-threshold": 5, "just-below-threshold": 55}


def test_the_coachs_file_holds_a_row_number_tag_and_headings_and_nothing_else(
    specified: Comparison, proxy: Comparison
) -> None:
    sample = coach_sample(
        TAXONOMY, ROWS, {"specified": specified, "proxy": proxy}, stratified_by="proxy", seed=5
    )
    stream = io.StringIO()
    write_sample_csv(stream, sample, heading_teams(ROWS))
    lines = stream.getvalue().splitlines()
    assert lines[0] == ",".join(SAMPLE_COLUMNS)
    assert len(lines) == 1 + len(sample.items)
    assert len({item.source_sha256 for item in sample.items}) == len(sample.items)
    assert all(item.row is not None and item.row.placement == UNPLACED for item in sample.items)
    text = stream.getvalue().casefold()
    assert not any(position_id in text for position_id in WORDS)
    assert not any(word in _words([f"t:{text}"]) for word in FORBIDDEN)
    assert "0." not in text, "no confidence"


def test_a_heading_one_team_used_is_withheld_from_the_coachs_file() -> None:
    rows = [_row("c1", "d1", headings=("framing", "one team only")), _row("c2", "d2", headings=("framing",))]
    predictions: dict[str, Prediction | None] = {
        "c1": Prediction("spending-da", 0.5),
        "c2": Prediction("states-cp", 0.4),
    }
    sample = coach_sample(
        MEASURE_TAXONOMY, rows, {"proxy": _comparison(0.9, predictions)}, stratified_by="proxy"
    )
    stream = io.StringIO()
    write_sample_csv(stream, sample, heading_teams(rows))
    shown = {line.split(",")[0]: line for line in stream.getvalue().splitlines()[1:]}
    c1 = next(item.sample_row for item in sample.items if item.item_id == "c1")
    assert shown[str(c1)].endswith(f"tag of c1,framing > {WITHHELD_HEADING},,")
    assert "one team only" not in stream.getvalue()


def test_the_sample_kept_beside_the_file_holds_ids_and_predictions_only(
    specified: Comparison, proxy: Comparison
) -> None:
    sample = coach_sample(
        TAXONOMY, ROWS, {"specified": specified, "proxy": proxy}, stratified_by="proxy", seed=5
    )
    lines = sample_lines(sample)
    text = "".join(lines).casefold()
    assert not any(word in text for word in ("deficit", "states solve", "evidence", "link"))
    again = read_sample(lines)
    assert again.items == sample.items
    assert (again.thresholds, again.populations, again.stratified_by) == (
        sample.thresholds,
        sample.populations,
        "proxy",
    )


# ------------------------------------------------------------------------------------------------
# The coach's labels and the score
# ------------------------------------------------------------------------------------------------


def test_the_coachs_labels_are_read_and_a_label_naming_no_position_is_refused_by_row() -> None:
    good = "sample_row,tag,headings,position,note\n1,a,b,spending-da,\n2,a,b,None,\n3,a,b,unsure,\n4,a,b,,\n"
    assert read_sample_labels(io.StringIO(good), MEASURE_TAXONOMY) == {1: "spending-da", 2: NO_POSITION_LABEL}
    bad = "sample_row,tag,headings,position,note\n7,a secret tag,b,maple grove da,\n"
    with pytest.raises(ValueError) as raised:
        read_sample_labels(io.StringIO(bad), MEASURE_TAXONOMY)
    assert "row 7" in str(raised.value) and "maple" not in str(raised.value)


def test_the_score_by_stratum_and_weighted_by_population_worked_by_hand() -> None:
    def item(row: int, stratum: str, proxy: tuple[str, float], specified: tuple[str, float]) -> SampleItem:
        return SampleItem(
            sample_row=row,
            item_id=f"c{row}",
            source_sha256=f"d{row}",
            stratum=stratum,
            predictions={"proxy": Prediction(*proxy), "specified": Prediction(*specified)},
        )

    sample = CoachSample(
        stratified_by="proxy",
        thresholds={"proxy": 0.6, "specified": 0.0},
        populations={"at-or-above-threshold": 100, "just-below-threshold": 300, "far-below-threshold": 600},
        items=(
            item(1, "at-or-above-threshold", ("spending-da", 0.8), ("spending-da", 0.9)),
            item(2, "at-or-above-threshold", ("states-cp", 0.7), ("states-cp", 0.9)),
            item(3, "just-below-threshold", ("spending-da", 0.5), ("politics-da", 0.6)),
            item(4, "just-below-threshold", ("states-cp", 0.4), ("states-cp", 0.4)),
            item(5, "far-below-threshold", ("spending-da", 0.2), ("spending-da", 0.3)),
            item(6, "far-below-threshold", ("states-cp", 0.1), ("states-cp", 0.2)),
        ),
    )
    labels = {
        1: "spending-da",
        2: "politics-da",
        3: "politics-da",
        4: "states-cp",
        5: NO_POSITION_LABEL,
        6: "states-cp",
    }
    proxy_score, specified_score = score_sample(MEASURE_TAXONOMY, sample, labels)
    # proxy: right on 1, 4, 6. Weights: 100/2, 300/2, 600/2 per card.
    assert (proxy_score.model, proxy_score.labelled, proxy_score.correct, proxy_score.no_position) == (
        "proxy",
        6,
        3,
        1,
    )
    assert [(one.name, one.correct, one.labelled, one.population) for one in proxy_score.by_stratum] == [
        ("at-or-above-threshold", 1, 2, 100),
        ("just-below-threshold", 1, 2, 300),
        ("far-below-threshold", 1, 2, 600),
    ]
    assert (proxy_score.at_threshold.correct, proxy_score.at_threshold.labelled) == (1, 2)
    assert proxy_score.weighted_accuracy == pytest.approx((50 + 150 + 300) / 1000)
    assert proxy_score.weighted_precision_at_threshold == pytest.approx(50 / 100)
    # specified: right on 1, 3, 4, 6, and it places every card (threshold 0).
    assert (specified_score.correct, specified_score.at_threshold.labelled) == (4, 6)
    assert specified_score.weighted_accuracy == pytest.approx((50 + 150 + 150 + 300) / 1000)
    assert specified_score.weighted_precision_at_threshold == pytest.approx((50 + 150 + 150 + 300) / 1000)
    assert [(one.name, one.correct, one.labelled) for one in specified_score.by_predicted_kind] == [
        ("cp", 2, 3),
        ("da", 2, 3),
    ]


def test_module_exports_what_it_names() -> None:
    assert set(module.__all__) <= set(dir(module))

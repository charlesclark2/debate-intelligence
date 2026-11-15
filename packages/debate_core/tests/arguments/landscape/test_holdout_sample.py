"""The held-out coach sample (`v1-e32-t50`): drawn by the first sample's rule, sharing no card with it.

The PM's ruling of 2026-11-14: strata 60, 40 and 20, seed 20261114, and every candidate kept out that is in a
first-sample card's cluster, has one's exact fingerprint, is read alike to one or comes from a first-sample
document, measured against every first-sample card drawn; at most one card per cluster inside the holdout; a
first-sample card the occurrence table does not hold stops the draw, by count. Every card, document, cluster
and fingerprint here is invented, and the counts are worked out by hand (working agreement 6).
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, cast

import pytest

from debate_core.arguments.landscape.holdout_sample import (
    HOLDOUT_KEY,
    HOLDOUT_SEED,
    HOLDOUT_STRATA,
    CardIdentity,
    FirstSampleCardsMissing,
    holdout_header,
    holdout_sample,
    holdout_sample_lines,
    is_holdout,
)
from debate_core.arguments.landscape.local_classifier import (
    UNPLACED,
    CoachSample,
    Comparison,
    FeatureRow,
    HeldOutMeasure,
    Prediction,
    SampleItem,
    coach_sample,
    sample_lines,
)
from debate_core.domain.landscape import Taxonomy

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "spending-da", "label": "Spending", "kind": "da", "side": "neg"},
            {"id": "states-cp", "label": "States", "kind": "cp", "side": "neg"},
        ],
    }
)


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


def _row(item_id: str, document: str, placement: str = UNPLACED) -> FeatureRow:
    return FeatureRow(
        item_id=item_id,
        source_sha256=document,
        teams=(document,),
        headings=("link",),
        placing=(False,),
        tag=f"invented tag {item_id}",
        placement=placement,
        label=None,
    )


def _identity(item_id: str, document: str, cluster: str | None, exact: str | None, read: str) -> CardIdentity:
    return CardIdentity(
        item_id=item_id,
        source_sha256=document,
        read_fingerprint=read,
        exact_fingerprint=exact,
        cluster_id=cluster,
    )


def _first(*cards: tuple[str, str]) -> tuple[SampleItem, ...]:
    return tuple(
        SampleItem(
            sample_row=row,
            item_id=item_id,
            source_sha256=document,
            stratum="far-below-threshold",
            predictions={},
        )
        for row, (item_id, document) in enumerate(cards, start=1)
    )


# ------------------------------------------------------------------------------------------------
# By hand. The first sample drew f1 (document F1, cluster K1, exact E1, read R1) and f2 (F2, K2, E2,
# R2); the coach labelled f1 and left f2 unsure, and both are measured against. The candidates:
#   a  in another team's document D1, in f1's cluster K1, nothing else shared: the mutant's card
#   b  in D2, cluster Kb, but f2's exact fingerprint E2
#   c  in D3, read alike to f1 (R1), its own cluster and body
#   d  in F1, f1's own document, its own cluster, body and reading
#   e  in D5, with no occurrence row
#   g1 and g2 in D6 and D7, one cluster K9 between them
#   h1 to h6 in H1 to H6, nothing shared
#   p  in P1, placed by its heading, so never a candidate
# f1 and f2 are unplaced candidates themselves, and meet the cluster, body, reading and document rules each.
# a, b, c, d and e are kept out, one rule each; one of g1 and g2 is drawn, and h1 to h6. With fewer cards
# than the strata want, every eligible document gives its card.
# ------------------------------------------------------------------------------------------------

FIRST = _first(("f1", "F1"), ("f2", "F2"))
CANDIDATES = {
    "a": ("D1", "K1", "Ea", "Ra"),
    "b": ("D2", "Kb", "E2", "Rb"),
    "c": ("D3", "Kc", "Ec", "R1"),
    "d": ("F1", "Kd", "Ed", "Rd"),
    "e": ("D5", None, None, "Re"),
    "g1": ("D6", "K9", "Eg1", "Rg1"),
    "g2": ("D7", "K9", "Eg2", "Rg2"),
    **{f"h{n}": (f"H{n}", f"Kh{n}", f"Eh{n}", f"Rh{n}") for n in range(1, 7)},
}
IDENTITIES = {
    "f1": _identity("f1", "F1", "K1", "E1", "R1"),
    "f2": _identity("f2", "F2", "K2", "E2", "R2"),
    "p": _identity("p", "P1", "Kp", "Ep", "Rp"),
    **{
        item_id: _identity(item_id, document, cluster, exact, read)
        for item_id, (document, cluster, exact, read) in CANDIDATES.items()
        if cluster is not None
    },
}
ROWS = (
    _row("f1", "F1"),
    _row("f2", "F2"),
    _row("p", "P1", placement="ALIAS"),
    *(_row(item_id, document) for item_id, (document, *_) in CANDIDATES.items()),
)
PREDICTIONS: dict[str, Prediction | None] = {
    item_id: Prediction("spending-da" if number % 2 else "states-cp", 0.3 + number / 40)
    for number, item_id in enumerate(("p", "f1", "f2", *CANDIDATES))
}
MODELS = {"proxy": _comparison(0.6, PREDICTIONS)}


def drawn_by_hand() -> set[str]:
    draw = holdout_sample(TAXONOMY, ROWS, MODELS, IDENTITIES, FIRST, stratified_by="proxy")
    return {item.item_id for item in draw.sample.items}


def test_no_candidate_sharing_a_card_or_document_with_the_first_sample_is_drawn() -> None:
    drawn = drawn_by_hand()

    assert not drawn & {"a", "b", "c", "d", "e", "f1", "f2"}
    assert {f"h{n}" for n in range(1, 7)} <= drawn
    assert len(drawn & {"g1", "g2"}) == 1
    assert len(drawn) == 7


def test_a_card_sharing_a_cluster_with_a_first_sample_card_in_another_teams_file_is_never_drawn() -> None:
    """The mutant's card: `a` shares f1's cluster and nothing else, in a document of its own."""
    assert "a" not in drawn_by_hand()


def test_each_exclusion_is_counted_once_per_rule_it_meets() -> None:
    draw = holdout_sample(TAXONOMY, ROWS, MODELS, IDENTITIES, FIRST, stratified_by="proxy")

    assert draw.exclusions.as_json() == {
        "first_sample_cards": 2,
        "first_sample_documents": 2,
        "first_sample_clusters": 2,
        "candidates": 15,
        "same_cluster": 3,
        "same_exact_fingerprint": 3,
        "same_read_fingerprint": 3,
        "same_document": 3,
        "no_occurrence_row": 1,
        "excluded": 7,
        "eligible": 8,
        "one_per_cluster": 1,
    }


def test_a_card_meeting_two_rules_is_counted_under_each_and_kept_out_once() -> None:
    identities = {**IDENTITIES, "d": _identity("d", "F1", "K1", "Ed", "Rd")}

    draw = holdout_sample(TAXONOMY, ROWS, MODELS, identities, FIRST, stratified_by="proxy")

    assert (draw.exclusions.same_cluster, draw.exclusions.same_document) == (4, 3)
    assert draw.exclusions.excluded == 7


def test_an_unlabelled_first_sample_card_keeps_its_copies_out_too() -> None:
    """f2 was left unsure; b carries its body, and is still kept out."""
    assert "b" not in drawn_by_hand()


@pytest.mark.parametrize("dropped", ["f2", "f1"])
def test_a_first_sample_card_with_no_occurrence_row_stops_the_draw_by_count(dropped: str) -> None:
    identities = dict(IDENTITIES)
    if dropped == "f2":
        del identities["f2"]
    else:
        identities["f1"] = _identity("f1", "F1", None, None, "R1")

    with pytest.raises(FirstSampleCardsMissing) as stopped:
        holdout_sample(TAXONOMY, ROWS, MODELS, identities, FIRST, stratified_by="proxy")

    assert (stopped.value.missing, stopped.value.of) == (1, 2)
    assert dropped not in str(stopped.value) and "F1" not in str(stopped.value)


# ------------------------------------------------------------------------------------------------
# The strata, the seed and the clusters inside the holdout
# ------------------------------------------------------------------------------------------------


def _many(count: int) -> tuple[tuple[FeatureRow, ...], dict[str, Prediction | None], dict[str, CardIdentity]]:
    """`count` unplaced cards, one per document and cluster: a fifth at 0.95, the rest at distinct confidences
    below 0.9, so the median below the threshold splits them in half."""
    rows = tuple(_row(f"c{n}", f"D{n}") for n in range(count))
    predictions: dict[str, Prediction | None] = {
        f"c{n}": Prediction("spending-da" if n % 3 else "states-cp", 0.95 if n % 5 == 0 else n / 10_000)
        for n in range(count)
    }
    identities = {f"c{n}": _identity(f"c{n}", f"D{n}", f"K{n}", f"E{n}", f"R{n}") for n in range(count)}
    return rows, predictions, identities


def test_the_strata_take_60_40_and_20_and_the_seed_is_the_rulings_date() -> None:
    rows, predictions, identities = _many(600)

    draw = holdout_sample(
        TAXONOMY, rows, {"proxy": _comparison(0.9, predictions)}, identities, (), stratified_by="proxy"
    )

    assert HOLDOUT_SEED == 20261114 and draw.seed == HOLDOUT_SEED
    assert HOLDOUT_STRATA == (
        ("at-or-above-threshold", 60),
        ("just-below-threshold", 40),
        ("far-below-threshold", 20),
    )
    assert Counter(item.stratum for item in draw.sample.items) == {
        "at-or-above-threshold": 60,
        "just-below-threshold": 40,
        "far-below-threshold": 20,
    }
    assert draw.sample.populations == {
        "at-or-above-threshold": 120,
        "just-below-threshold": 240,
        "far-below-threshold": 240,
    }
    assert sorted(item.sample_row for item in draw.sample.items) == list(range(1, 121))


def test_the_draw_is_the_first_samples_rule_on_the_eligible_cards() -> None:
    """With nothing to keep out, the holdout is `coach_sample` at the holdout's shares and seed."""
    rows, predictions, identities = _many(600)
    models = {"proxy": _comparison(0.9, predictions)}

    draw = holdout_sample(TAXONOMY, rows, models, identities, (), stratified_by="proxy")
    plain = coach_sample(
        TAXONOMY, rows, models, stratified_by="proxy", seed=HOLDOUT_SEED, strata=HOLDOUT_STRATA
    )

    assert [item.item_id for item in draw.sample.items] == [item.item_id for item in plain.items]


def test_the_same_seed_draws_the_same_holdout_and_another_seed_another() -> None:
    rows, predictions, identities = _many(600)
    models = {"proxy": _comparison(0.9, predictions)}

    def draw(seed: int) -> list[str]:
        found = holdout_sample(TAXONOMY, rows, models, identities, (), stratified_by="proxy", seed=seed)
        return [item.item_id for item in found.sample.items]

    assert draw(HOLDOUT_SEED) == draw(HOLDOUT_SEED)
    assert draw(HOLDOUT_SEED) != draw(21)


def test_two_copies_of_one_card_are_never_both_in_the_holdout() -> None:
    """Every card of documents 0 to 299 shares one cluster with its partner 300 higher."""
    rows, predictions, identities = _many(600)
    paired = {
        item_id: _identity(
            item_id, one.source_sha256, f"K{int(item_id[1:]) % 300}", one.exact_fingerprint, item_id
        )
        for item_id, one in identities.items()
    }

    draw = holdout_sample(
        TAXONOMY, rows, {"proxy": _comparison(0.9, predictions)}, paired, (), stratified_by="proxy"
    )

    clusters = Counter(cast(str, paired[item.item_id].cluster_id) for item in draw.sample.items)
    assert len(draw.sample.items) == 120
    assert max(clusters.values()) == 1
    assert draw.exclusions.one_per_cluster == 120


# ------------------------------------------------------------------------------------------------
# The rows file
# ------------------------------------------------------------------------------------------------

DRAWN_FROM = {
    "caselist": "hspolicy99",
    "snapshot": "2026-09-22",
    "version": "2026.09.01-docx-1",
    "parser_version": "2026.09.01-docx",
}


def test_the_rows_file_is_marked_a_holdout_with_its_seed_strata_exclusions_and_snapshot() -> None:
    draw = holdout_sample(TAXONOMY, ROWS, MODELS, IDENTITIES, FIRST, stratified_by="proxy")

    lines = holdout_sample_lines(draw, drawn_from=DRAWN_FROM)

    header = json.loads(lines[0])
    assert header.get(HOLDOUT_KEY) is True
    assert (header["seed"], header["strata"]) == (
        20261114,
        {"at-or-above-threshold": 60, "just-below-threshold": 40, "far-below-threshold": 20},
    )
    assert header["exclusions"] == draw.exclusions.as_json()
    assert header["drawn_from"] == DRAWN_FROM
    assert header["schema"] == "local-classifier-sample-1"
    assert len(lines) == 1 + len(draw.sample.items)
    assert holdout_header(lines) == header and is_holdout(lines)
    assert "invented tag" not in "".join(lines)


def test_the_first_samples_rows_file_is_no_holdout() -> None:
    first = CoachSample(
        stratified_by="proxy", thresholds={}, populations={}, cell_populations={}, items=FIRST
    )

    assert not is_holdout(sample_lines(first))
    assert not is_holdout(['{"holdout": "yes"}\n']) and not is_holdout([]) and not is_holdout(["not json\n"])

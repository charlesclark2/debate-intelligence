"""The own-side rule (`v1-e32-t49`): a placement in a file disclosed only on its position's own side reads it.

Every expected value is written by hand from the invented taxonomy below. No card, heading or tag is real.
"""

from __future__ import annotations

import pytest

from debate_core.arguments.landscape.side_role import OWN_SIDE_NOTE, on_own_side, side_role
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    RATIONALE_LIMIT,
    ClassificationMethod,
    ClassificationResult,
    PositionRole,
)

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "rural-adv", "label": "Rural Advantage", "kind": "advantage", "side": "aff"},
            {"id": "spending-da", "label": "Spending DA", "kind": "da", "side": "neg"},
            {"id": "condo-bad", "label": "Condo Bad", "kind": "theory", "side": "both"},
        ],
    }
)

ANSWERS, READS = PositionRole.ANSWERS, PositionRole.READS


@pytest.mark.parametrize(
    ("position_id", "role", "sides", "expected"),
    [
        pytest.param("spending-da", ANSWERS, {"NEG"}, READS, id="neg position, neg file: reads"),
        pytest.param("spending-da", ANSWERS, {"CON"}, READS, id="con is neg"),
        pytest.param("spending-da", ANSWERS, {"NEG", "UNKNOWN"}, READS, id="unknown is no side"),
        pytest.param("rural-adv", ANSWERS, {"AFF"}, READS, id="aff position, aff file: reads"),
        pytest.param("rural-adv", ANSWERS, {"PRO"}, READS, id="pro is aff"),
        pytest.param("spending-da", READS, {"NEG"}, READS, id="a read on its own side stays"),
        pytest.param("spending-da", ANSWERS, {"AFF"}, ANSWERS, id="the other side still answers"),
        pytest.param("rural-adv", ANSWERS, {"NEG"}, ANSWERS, id="the other side still answers, aff"),
        pytest.param("spending-da", READS, {"AFF"}, READS, id="the other side's half is not decided here"),
        pytest.param("spending-da", ANSWERS, {"AFF", "NEG"}, ANSWERS, id="a file on both sides keeps"),
        pytest.param("spending-da", ANSWERS, {"UNKNOWN"}, ANSWERS, id="no readable side keeps"),
        pytest.param("spending-da", ANSWERS, set[str](), ANSWERS, id="no disclosure keeps"),
        pytest.param("condo-bad", ANSWERS, {"NEG"}, ANSWERS, id="a position either side reads keeps"),
        pytest.param("condo-bad", ANSWERS, {"AFF"}, ANSWERS, id="a position either side reads keeps, aff"),
    ],
)
def test_a_placement_on_its_own_side_reads_and_every_other_keeps_its_role(
    position_id: str, role: PositionRole, sides: set[str], expected: PositionRole
) -> None:
    assert side_role(TAXONOMY, position_id, role, frozenset(sides)) is expected


def placed(
    role: PositionRole | None, *, rationale: str = "an answer heading makes the role ANSWERS"
) -> ClassificationResult:
    return ClassificationResult(
        position_id=None if role is None else "spending-da",
        role=role,
        confidence=1.0 if role is not None else 0.0,
        rationale=rationale,
        method=ClassificationMethod.ALIAS if role is not None else None,
        taxonomy_version="1.0.0",
    )


def test_a_result_whose_role_changes_says_so_in_its_rationale() -> None:
    found = on_own_side(TAXONOMY, placed(ANSWERS), ["NEG"])

    assert found.role is READS
    assert found.rationale == "an answer heading makes the role ANSWERS" + OWN_SIDE_NOTE
    assert (found.position_id, found.confidence, found.method) == (
        "spending-da",
        1.0,
        ClassificationMethod.ALIAS,
    )


def test_a_long_rationale_keeps_within_the_limit_and_ends_with_the_note() -> None:
    found = on_own_side(TAXONOMY, placed(ANSWERS, rationale="w" * RATIONALE_LIMIT), ["NEG"])

    assert len(found.rationale) == RATIONALE_LIMIT
    assert found.rationale.endswith(OWN_SIDE_NOTE)


@pytest.mark.parametrize(
    ("result", "sides"),
    [
        pytest.param(placed(ANSWERS), ["AFF"], id="the other side"),
        pytest.param(placed(READS), ["NEG"], id="already reads"),
        pytest.param(placed(None, rationale="no heading over it places it"), ["NEG"], id="no position"),
    ],
)
def test_a_result_whose_role_stays_is_returned_as_it_is(
    result: ClassificationResult, sides: list[str]
) -> None:
    assert on_own_side(TAXONOMY, result, sides) is result

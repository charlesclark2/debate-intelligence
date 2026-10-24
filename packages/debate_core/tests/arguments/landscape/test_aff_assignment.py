"""Each affirmative round's aff and the signal that named it (`v1-e32-t09-policy-plan-texts` ac4).

The PM's rulings of 2026-10-24: `PLAN_TEXT` when a round's plan texts name one aff; `TEAM_CARRY` when
the team's identified rounds agree on one aff, never into a round whose own plan text names something
else; and a round no signal identifies stays unidentified. Rounds and teams here are invented keys.
"""

from __future__ import annotations

from typing import Any

from debate_core.arguments.landscape.aff_assignment import (
    PLAN_TEXT_METHOD,
    TEAM_CARRY_METHOD,
    AffRound,
    AssignedAff,
    assign_affs,
)
from debate_core.arguments.landscape.plan_text import DocumentPlanText, PlanTextVerdict, PlanTextVocabulary
from debate_core.domain.landscape import Taxonomy

SAMPLE = "sample-plan-aff"
CHILD = "route-plan-aff"
OTHER = "other-plan-aff"
NAMES_SAMPLE = DocumentPlanText(PlanTextVerdict.NAMES, SAMPLE)
NAMES_CHILD = DocumentPlanText(PlanTextVerdict.NAMES, CHILD)
NAMES_OTHER = DocumentPlanText(PlanTextVerdict.NAMES, OTHER)
CONFLICTING = DocumentPlanText(PlanTextVerdict.CONFLICTING)
UNNAMED = DocumentPlanText(PlanTextVerdict.UNNAMED)
NONE = DocumentPlanText(PlanTextVerdict.NONE)
UNREAD = DocumentPlanText(PlanTextVerdict.UNREAD)


def _position(identifier: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": identifier.replace("-", " ").capitalize(),
        "kind": "aff",
        "side": "aff",
        **fields,
    }


WORDS = PlanTextVocabulary(
    Taxonomy.model_validate(
        {
            "topic_id": "sample-topic",
            "taxonomy_version": "1.0.0",
            "event": "POLICY",
            "positions": [
                _position(SAMPLE, aliases=["sample plan"]),
                _position(CHILD, parent=SAMPLE, tag_keywords=["voucher route"]),
                _position(OTHER, aliases=["other plan"]),
            ],
        }
    )
)


def rounds(*specs: tuple[str, str | None, tuple[str, ...]]) -> list[AffRound]:
    return [AffRound(round_key=key, team=team, documents=documents) for key, team, documents in specs]


def assigned(
    specs: list[AffRound],
    plan_texts: dict[str, DocumentPlanText],
    placed: dict[str, frozenset[str]] | None = None,
) -> dict[str, tuple[str, str]]:
    found, _ = assign_affs(specs, plan_texts, placed or {}, WORDS)
    return {one.round_key: (one.position_id, one.method) for one in found}


def test_a_round_whose_plan_text_names_an_aff_reads_it() -> None:
    assert assigned(rounds(("r1", "team-a", ("d1",))), {"d1": NAMES_SAMPLE}) == {
        "r1": (SAMPLE, PLAN_TEXT_METHOD)
    }


def test_a_document_with_no_plan_text_beside_one_naming_an_aff_does_not_stop_it() -> None:
    found = assigned(rounds(("r1", "team-a", ("d1", "d2"))), {"d1": NAMES_SAMPLE, "d2": NONE})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_two_documents_naming_two_affs_leave_the_round_unassigned() -> None:
    assert assigned(rounds(("r1", "team-a", ("d1", "d2"))), {"d1": NAMES_SAMPLE, "d2": NAMES_OTHER}) == {}


def test_a_conflicting_document_leaves_the_round_unassigned() -> None:
    assert assigned(rounds(("r1", "team-a", ("d1", "d2"))), {"d1": NAMES_SAMPLE, "d2": CONFLICTING}) == {}


def test_a_parent_and_its_child_in_one_round_name_the_child() -> None:
    found = assigned(rounds(("r1", "team-a", ("d1", "d2"))), {"d1": NAMES_SAMPLE, "d2": NAMES_CHILD})
    assert found == {"r1": (CHILD, PLAN_TEXT_METHOD)}


def test_one_document_read_in_two_rounds_names_both() -> None:
    found = assigned(rounds(("r1", "team-a", ("d1",)), ("r2", "team-b", ("d1",))), {"d1": NAMES_SAMPLE})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD), "r2": (SAMPLE, PLAN_TEXT_METHOD)}


def test_a_round_no_signal_identifies_stays_unidentified() -> None:
    found, counts = assign_affs(rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {}, WORDS)
    assert found == ()
    assert (counts.rounds, counts.unidentified, counts.by_method) == (1, 1, {})


def test_a_placed_round_with_no_plan_text_is_left_to_the_report() -> None:
    found, counts = assign_affs(
        rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {"r1": frozenset({SAMPLE})}, WORDS
    )
    assert found == ()
    assert (counts.placed_only, counts.unidentified) == (1, 0)


def test_a_plan_text_outweighs_a_placed_card_in_its_own_round() -> None:
    found = assigned(rounds(("r1", "team-a", ("d1",))), {"d1": NAMES_SAMPLE}, {"r1": frozenset({OTHER})})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_a_team_carries_its_aff_into_a_round_with_no_plan_text() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-b", ("d3",)))
    found = assigned(specs, {"d1": NAMES_SAMPLE, "d2": NONE, "d3": NONE})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD), "r2": (SAMPLE, TEAM_CARRY_METHOD)}


def test_a_placed_card_identifies_a_round_for_the_carry() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)))
    found = assigned(specs, {"d1": NONE, "d2": NONE}, {"r1": frozenset({SAMPLE})})
    assert found == {"r2": (SAMPLE, TEAM_CARRY_METHOD)}


def test_never_carried_into_a_round_whose_own_plan_text_names_nothing_or_conflicts_or_was_unread() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1",)),
        ("r2", "team-a", ("d2",)),
        ("r3", "team-a", ("d3",)),
        ("r4", "team-a", ("d4", "d5")),
        ("r5", "team-a", ("d6",)),
    )
    plan_texts = {"d1": NAMES_SAMPLE, "d2": UNNAMED, "d3": UNREAD, "d4": NONE, "d5": UNNAMED, "d6": NONE}
    found, counts = assign_affs(specs, plan_texts, {}, WORDS)
    assert {one.round_key: one.method for one in found} == {"r1": PLAN_TEXT_METHOD, "r5": TEAM_CARRY_METHOD}
    assert counts.carry_refused == 3


def test_a_document_missing_from_the_readings_counts_as_unread() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)))
    assert assigned(specs, {"d1": NAMES_SAMPLE}) == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_a_team_whose_rounds_name_two_affs_carries_nothing() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found, counts = assign_affs(specs, {"d1": NAMES_SAMPLE, "d2": NAMES_OTHER, "d3": NONE}, {}, WORDS)
    assert {one.round_key for one in found} == {"r1", "r2"}
    assert (counts.teams_disagreeing, counts.teams_carrying) == (1, 0)


def test_a_placed_card_under_another_aff_is_a_disagreement() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found = assigned(specs, {"d1": NAMES_SAMPLE, "d2": NONE, "d3": NONE}, {"r2": frozenset({OTHER})})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_a_conflicting_round_is_a_disagreement() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found = assigned(specs, {"d1": NAMES_SAMPLE, "d2": CONFLICTING, "d3": NONE})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_a_team_naming_a_parent_and_its_child_carries_the_child() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found = assigned(specs, {"d1": NONE, "d2": NAMES_CHILD, "d3": NONE}, {"r1": frozenset({SAMPLE})})
    assert found == {"r2": (CHILD, PLAN_TEXT_METHOD), "r3": (CHILD, TEAM_CARRY_METHOD)}


def test_a_round_no_readable_team_disclosed_is_never_carried_into_or_from() -> None:
    specs = rounds(("r1", None, ("d1",)), ("r2", None, ("d2",)))
    assert assigned(specs, {"d1": NAMES_SAMPLE, "d2": NONE}) == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_a_round_no_readable_team_disclosed_is_not_carried_into_from_another_team() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", None, ("d2",)))
    assert assigned(specs, {"d1": NAMES_SAMPLE, "d2": NONE}) == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_the_counts_add_up() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1",)),
        ("r2", "team-a", ("d2",)),
        ("r3", "team-a", ("d3",)),
        ("r4", "team-b", ("d4",)),
        ("r5", "team-c", ("d5",)),
        ("r6", "team-d", ("d6", "d7")),
        ("r7", "team-d", ("d8",)),
    )
    plan_texts = {
        "d1": NAMES_SAMPLE,
        "d2": NONE,
        "d3": UNNAMED,
        "d4": NONE,
        "d5": NONE,
        "d6": NAMES_SAMPLE,
        "d7": NAMES_OTHER,
        "d8": NONE,
    }
    found, counts = assign_affs(specs, plan_texts, {"r4": frozenset({OTHER})}, WORDS)
    assert sorted((one.round_key, one.method) for one in found) == [
        ("r1", PLAN_TEXT_METHOD),
        ("r2", TEAM_CARRY_METHOD),
    ]
    assert counts.rounds == 7
    assert counts.by_method == {PLAN_TEXT_METHOD: 1, TEAM_CARRY_METHOD: 1}
    assert counts.placed_only == 1
    assert counts.unidentified == 4
    assert counts.conflicting == 1
    assert counts.carry_refused == 1
    assert (counts.teams_carrying, counts.teams_disagreeing) == (1, 1)


def test_assignments_come_in_round_key_order() -> None:
    specs = rounds(("r2", "team-a", ("d2",)), ("r1", "team-b", ("d1",)))
    found, _ = assign_affs(specs, {"d1": NAMES_SAMPLE, "d2": NAMES_OTHER}, {}, WORDS)
    assert found == (AssignedAff("r1", SAMPLE, PLAN_TEXT_METHOD), AssignedAff("r2", OTHER, PLAN_TEXT_METHOD))

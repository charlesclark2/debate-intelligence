"""Each affirmative round's aff and the signal that named it (`v1-e32-t09-policy-plan-texts` ac4).

The PM's rulings of 2026-10-24: `PLAN_TEXT` when a round's plan texts name one aff; `TEAM_CARRY` when
the team's identified rounds agree on one aff, never into a round whose own plan text names something
else; and a round no signal identifies stays unidentified. Rounds and teams here are invented keys.
"""

from __future__ import annotations

from typing import Any

from debate_core.arguments.landscape.aff_assignment import (
    KRITIKAL_AFF_CARRY_METHOD,
    KRITIKAL_AFF_MARKER_METHOD,
    PLAN_TEXT_METHOD,
    TEAM_CARRY_METHOD,
    TRANSITION_PLAN_CARRY_METHOD,
    TRANSITION_PLAN_TEXT_METHOD,
    AffRound,
    AssignedAff,
    AssignmentCounts,
    KritikalSignals,
    assign_affs,
)
from debate_core.arguments.landscape.plan_text import (
    DocumentPlanText,
    PlanTextVerdict,
    PlanTextVocabulary,
    ResolutionalPlanWords,
)
from debate_core.domain.landscape import Taxonomy

SAMPLE = "sample-plan-aff"
CHILD = "route-plan-aff"
OTHER = "other-plan-aff"
NATIONAL = "national-plan-aff"
NAMES_SAMPLE = DocumentPlanText(PlanTextVerdict.NAMES, SAMPLE)
NAMES_CHILD = DocumentPlanText(PlanTextVerdict.NAMES, CHILD)
NAMES_OTHER = DocumentPlanText(PlanTextVerdict.NAMES, OTHER)
NAMES_NATIONAL = DocumentPlanText(PlanTextVerdict.NAMES, NATIONAL)
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


TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            _position(SAMPLE, aliases=["sample plan"]),
            _position(CHILD, parent=SAMPLE, tag_keywords=["voucher route"]),
            _position(OTHER, aliases=["other plan"]),
            _position(NATIONAL),
        ],
    }
)
WORDS = PlanTextVocabulary(
    TAXONOMY,
    ResolutionalPlanWords(
        topic_id="sample-topic",
        position_id=NATIONAL,
        frame_words=("federal", "should"),
        resolutional_words=("national",),
    ),
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


def test_the_resolutional_aff_beside_another_in_one_round_gives_way_to_it() -> None:
    found = assigned(rounds(("r1", "team-a", ("d1", "d2"))), {"d1": NAMES_NATIONAL, "d2": NAMES_SAMPLE})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_the_resolutional_aff_never_settles_a_conflict_between_two_others() -> None:
    specs = rounds(("r1", "team-a", ("d1", "d2", "d3")))
    assert assigned(specs, {"d1": NAMES_NATIONAL, "d2": NAMES_SAMPLE, "d3": NAMES_OTHER}) == {}


def test_a_team_naming_the_resolutional_aff_and_one_other_carries_the_other() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found = assigned(specs, {"d1": NAMES_NATIONAL, "d2": NAMES_SAMPLE, "d3": NONE})
    assert found == {
        "r1": (NATIONAL, PLAN_TEXT_METHOD),
        "r2": (SAMPLE, PLAN_TEXT_METHOD),
        "r3": (SAMPLE, TEAM_CARRY_METHOD),
    }


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


# ------------------------------------------------------------------------------------------------
# Kritikal affirmatives (`v1-e32-t17`, the PM's rulings of 2026-10-25)
# ------------------------------------------------------------------------------------------------
#
# A round no other signal identifies reads the K aff when none of its documents holds a plan text and
# one holds a K-aff marker; a team whose only identified aff is the K aff carries it, by t09's carry rule
# and guard, and never into a round whose own file reads an advantage.

KRITIKAL = "sample-kritikal-aff"


def kritikal_assigned(
    specs: list[AffRound],
    plan_texts: dict[str, DocumentPlanText],
    markers: set[str],
    *,
    advantages: set[str] | None = None,
    placed: dict[str, frozenset[str]] | None = None,
) -> tuple[dict[str, tuple[str, str]], AssignmentCounts]:
    signals = KritikalSignals(KRITIKAL, frozenset(markers), frozenset(advantages or set()))
    found, counts = assign_affs(specs, plan_texts, placed or {}, WORDS, signals)
    return {one.round_key: (one.position_id, one.method) for one in found}, counts


def test_a_round_with_a_marker_file_and_no_plan_text_reads_the_k_aff() -> None:
    found, counts = kritikal_assigned(rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {"d1"})
    assert found == {"r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD)}
    assert (counts.unidentified, counts.by_method) == (0, {KRITIKAL_AFF_MARKER_METHOD: 1})


def test_a_marker_beside_a_file_with_no_marker_still_names_the_round() -> None:
    found, _ = kritikal_assigned(rounds(("r1", "team-a", ("d1", "d2"))), {"d1": NONE, "d2": NONE}, {"d2"})
    assert found == {"r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD)}


def test_a_plan_text_naming_an_aff_outweighs_a_marker() -> None:
    found, _ = kritikal_assigned(rounds(("r1", "team-a", ("d1",))), {"d1": NAMES_SAMPLE}, {"d1"})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD)}


def test_a_marker_never_names_a_round_holding_a_plan_text_of_its_own_or_an_unread_file() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1", "d2")),
        ("r2", "team-b", ("d3", "d4")),
        ("r3", "team-c", ("d5", "d6")),
        ("r4", "team-d", ("d7",)),
    )
    plan_texts = {"d1": NONE, "d2": UNNAMED, "d3": NONE, "d4": UNREAD, "d5": NONE, "d6": CONFLICTING}
    found, counts = kritikal_assigned(specs, plan_texts, {"d1", "d3", "d5", "d7"})
    assert found == {}
    assert counts.unidentified == 4


def test_a_round_t02_placed_under_an_aff_is_left_to_the_report_whatever_its_markers() -> None:
    found, counts = kritikal_assigned(
        rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {"d1"}, placed={"r1": frozenset({SAMPLE})}
    )
    assert found == {}
    assert (counts.placed_only, counts.unidentified) == (1, 0)


def test_a_policy_carry_keeps_its_rounds_and_a_marker_does_not_take_them() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)))
    found, _ = kritikal_assigned(specs, {"d1": NAMES_SAMPLE, "d2": NONE}, {"d2"})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD), "r2": (SAMPLE, TEAM_CARRY_METHOD)}


def test_a_team_whose_only_aff_is_the_k_aff_carries_it_into_its_rounds_with_no_plan_text() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-b", ("d3",)))
    found, counts = kritikal_assigned(specs, {"d1": NONE, "d2": NONE, "d3": NONE}, {"d1"})
    assert found == {
        "r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD),
        "r2": (KRITIKAL, KRITIKAL_AFF_CARRY_METHOD),
    }
    assert counts.unidentified == 1


def test_the_k_aff_is_never_carried_into_a_round_whose_own_file_reads_an_advantage() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found, counts = kritikal_assigned(specs, {"d1": NONE, "d2": NONE, "d3": NONE}, {"d1"}, advantages={"r2"})
    assert found == {
        "r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD),
        "r3": (KRITIKAL, KRITIKAL_AFF_CARRY_METHOD),
    }
    assert counts.refused_by_advantage == ("r2",)
    assert counts.unidentified == 1


def test_a_round_with_its_own_marker_reads_the_k_aff_even_when_it_reads_an_advantage() -> None:
    found, counts = kritikal_assigned(
        rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {"d1"}, advantages={"r1"}
    )
    assert found == {"r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD)}
    assert counts.refused_by_advantage == ()


def test_the_k_aff_carry_keeps_t09s_guard_and_counts_its_refusals() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1",)),
        ("r2", "team-a", ("d2",)),
        ("r3", "team-a", ("d3",)),
        ("r4", "team-a", ("d4",)),
    )
    found, counts = kritikal_assigned(specs, {"d1": NONE, "d2": UNNAMED, "d3": UNREAD, "d4": NONE}, {"d1"})
    assert found == {
        "r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD),
        "r4": (KRITIKAL, KRITIKAL_AFF_CARRY_METHOD),
    }
    assert (counts.carry_refused, counts.unidentified) == (2, 2)


def test_a_team_whose_rounds_disagree_reads_the_k_aff_by_its_own_marker_and_carries_nothing() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1",)),
        ("r2", "team-a", ("d2",)),
        ("r3", "team-a", ("d3",)),
        ("r4", "team-a", ("d4",)),
    )
    plan_texts = {"d1": NAMES_SAMPLE, "d2": NAMES_OTHER, "d3": NONE, "d4": NONE}
    found, counts = kritikal_assigned(specs, plan_texts, {"d3"})
    assert found == {
        "r1": (SAMPLE, PLAN_TEXT_METHOD),
        "r2": (OTHER, PLAN_TEXT_METHOD),
        "r3": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD),
    }
    assert counts.unidentified == 1


def test_a_team_with_a_conflicting_round_reads_the_k_aff_by_its_own_marker_and_carries_nothing() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found, counts = kritikal_assigned(specs, {"d1": CONFLICTING, "d2": NONE, "d3": NONE}, {"d2"})
    assert found == {"r2": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD)}
    assert counts.unidentified == 2


def test_a_round_no_readable_team_disclosed_reads_its_own_marker_and_is_never_carried_into() -> None:
    specs = rounds(("r1", None, ("d1",)), ("r2", None, ("d2",)))
    found, _ = kritikal_assigned(specs, {"d1": NONE, "d2": NONE}, {"d1"})
    assert found == {"r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD)}


def test_without_k_aff_signals_a_marker_round_stays_unidentified() -> None:
    found, counts = assign_affs(rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {}, WORDS)
    assert found == ()
    assert (counts.unidentified, counts.refused_by_advantage) == (1, ())


# ------------------------------------------------------------------------------------------------
# Plan texts under a transition label (`v1-e32-t24`, the PM's rulings of 2026-10-26)
# ------------------------------------------------------------------------------------------------
#
# A round every method above leaves open, every file of it without a plan text t09 reads, reads the aff
# its plan texts under `Thus the plan`, `Thus plan` or `Thus` name (`TRANSITION_PLAN_TEXT`); two affs are
# a conflict and name nothing. A team carries it by t09's rule and guard (`TRANSITION_PLAN_CARRY`). The K
# aff is never carried into a round whose own file holds such a plan text naming a policy aff. No
# assignment above moves; a round another method identifies against its own such plan text is counted.
# `transition` holds each document's verdict over its plan texts under a transition label.


def transition_assigned(
    specs: list[AffRound],
    plan_texts: dict[str, DocumentPlanText],
    transition: dict[str, DocumentPlanText],
    *,
    markers: set[str] | None = None,
    advantages: set[str] | None = None,
    placed: dict[str, frozenset[str]] | None = None,
) -> tuple[dict[str, tuple[str, str]], AssignmentCounts]:
    signals = (
        None
        if markers is None
        else KritikalSignals(KRITIKAL, frozenset(markers), frozenset(advantages or set()))
    )
    found, counts = assign_affs(specs, plan_texts, placed or {}, WORDS, signals, transition)
    return {one.round_key: (one.position_id, one.method) for one in found}, counts


def test_a_round_whose_transition_plan_text_names_an_aff_reads_it() -> None:
    found, counts = transition_assigned(rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {"d1": NAMES_SAMPLE})
    assert found == {"r1": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD)}
    assert (counts.unidentified, counts.by_method) == (0, {TRANSITION_PLAN_TEXT_METHOD: 1})


def test_a_file_with_no_transition_plan_text_beside_one_naming_an_aff_does_not_stop_it() -> None:
    found, _ = transition_assigned(
        rounds(("r1", "team-a", ("d1", "d2"))), {"d1": NONE, "d2": NONE}, {"d1": NONE, "d2": NAMES_SAMPLE}
    )
    assert found == {"r1": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD)}


def test_a_plan_text_t09_reads_outweighs_a_transition_plan_text_in_its_own_round() -> None:
    found, _ = transition_assigned(
        rounds(("r1", "team-a", ("d1", "d2"))),
        {"d1": NAMES_OTHER, "d2": NONE},
        {"d1": NONE, "d2": NAMES_SAMPLE},
    )
    assert found == {"r1": (OTHER, PLAN_TEXT_METHOD)}


def test_never_into_a_round_whose_own_file_holds_a_plan_text_t09_reads_or_was_unread() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1", "d2")),
        ("r2", "team-b", ("d3", "d4")),
        ("r3", "team-c", ("d5", "d6")),
        ("r4", "team-d", ("d7", "d8")),
    )
    plan_texts = {
        "d1": NONE,
        "d2": UNNAMED,
        "d3": NONE,
        "d4": CONFLICTING,
        "d5": NONE,
        "d6": UNREAD,
        "d7": NONE,
    }
    transition = {"d1": NAMES_SAMPLE, "d3": NAMES_SAMPLE, "d5": NAMES_SAMPLE, "d7": NAMES_SAMPLE}
    found, counts = transition_assigned(specs, plan_texts, transition)
    assert found == {}
    assert counts.unidentified == 4


def test_two_affs_named_across_a_rounds_files_are_a_conflict_and_name_nothing() -> None:
    found, counts = transition_assigned(
        rounds(("r1", "team-a", ("d1", "d2"))),
        {"d1": NONE, "d2": NONE},
        {"d1": NAMES_SAMPLE, "d2": NAMES_OTHER},
    )
    assert found == {}
    assert (counts.unidentified, counts.transition_conflicting) == (1, 1)


def test_a_file_whose_transition_plan_texts_conflict_names_nothing() -> None:
    found, counts = transition_assigned(
        rounds(("r1", "team-a", ("d1", "d2"))),
        {"d1": NONE, "d2": NONE},
        {"d1": CONFLICTING, "d2": NAMES_SAMPLE},
    )
    assert found == {}
    assert counts.transition_conflicting == 1


def test_a_parent_and_its_child_across_a_rounds_files_name_the_child() -> None:
    found, _ = transition_assigned(
        rounds(("r1", "team-a", ("d1", "d2"))),
        {"d1": NONE, "d2": NONE},
        {"d1": NAMES_SAMPLE, "d2": NAMES_CHILD},
    )
    assert found == {"r1": (CHILD, TRANSITION_PLAN_TEXT_METHOD)}


def test_an_unnamed_transition_plan_text_identifies_nothing() -> None:
    found, counts = transition_assigned(rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {"d1": UNNAMED})
    assert found == {}
    assert (counts.unidentified, counts.transition_conflicting) == (1, 0)


def test_a_round_t02_placed_under_an_aff_is_left_to_the_report() -> None:
    found, counts = transition_assigned(
        rounds(("r1", "team-a", ("d1",))),
        {"d1": NONE},
        {"d1": NAMES_SAMPLE},
        placed={"r1": frozenset({SAMPLE})},
    )
    assert found == {}
    assert counts.placed_only == 1


def test_a_team_carry_keeps_its_round_and_a_transition_plan_naming_another_aff_is_counted() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found, counts = transition_assigned(
        specs,
        {"d1": NAMES_SAMPLE, "d2": NONE, "d3": NONE},
        {"d1": NONE, "d2": NAMES_OTHER, "d3": NAMES_CHILD},
    )
    assert found == {
        "r1": (SAMPLE, PLAN_TEXT_METHOD),
        "r2": (SAMPLE, TEAM_CARRY_METHOD),
        "r3": (SAMPLE, TEAM_CARRY_METHOD),
    }
    assert counts.transition_control == ("r2",)


def test_a_team_carries_a_transition_plans_aff_into_its_rounds_with_no_plan_text() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1",)),
        ("r2", "team-a", ("d2",)),
        ("r3", "team-a", ("d3",)),
        ("r4", "team-a", ("d4",)),
        ("r5", "team-b", ("d5",)),
    )
    plan_texts = {"d1": NONE, "d2": NONE, "d3": NONE, "d4": UNNAMED, "d5": NONE}
    transition = {"d1": NAMES_SAMPLE, "d2": NONE, "d3": UNNAMED, "d4": NONE, "d5": NONE}
    found, counts = transition_assigned(specs, plan_texts, transition)
    assert found == {
        "r1": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD),
        "r2": (SAMPLE, TRANSITION_PLAN_CARRY_METHOD),
    }
    assert (counts.transition_carry_refused, counts.unidentified) == (2, 3)


def test_a_team_naming_two_affs_by_transition_plans_carries_nothing() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found, _ = transition_assigned(
        specs, {"d1": NONE, "d2": NONE, "d3": NONE}, {"d1": NAMES_SAMPLE, "d2": NAMES_OTHER, "d3": NONE}
    )
    assert found == {"r1": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD), "r2": (OTHER, TRANSITION_PLAN_TEXT_METHOD)}


def test_a_team_with_a_conflicting_round_carries_nothing() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2", "d3")), ("r3", "team-a", ("d4",)))
    plan_texts = {"d1": NONE, "d2": NONE, "d3": NONE, "d4": NONE}
    transition = {"d1": NAMES_SAMPLE, "d2": NAMES_SAMPLE, "d3": NAMES_OTHER, "d4": NONE}
    found, _ = transition_assigned(specs, plan_texts, transition)
    assert found == {"r1": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD)}
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found, _ = transition_assigned(
        specs, {"d1": NONE, "d2": CONFLICTING, "d3": NONE}, {"d1": NAMES_SAMPLE, "d2": NONE, "d3": NONE}
    )
    assert found == {"r1": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD)}


def test_a_team_naming_the_resolutional_aff_and_a_transition_aff_carries_the_other() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    found, _ = transition_assigned(
        specs, {"d1": NONE, "d2": NONE, "d3": NONE}, {"d1": NAMES_NATIONAL, "d2": NAMES_SAMPLE, "d3": NONE}
    )
    assert found == {
        "r1": (NATIONAL, TRANSITION_PLAN_TEXT_METHOD),
        "r2": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD),
        "r3": (SAMPLE, TRANSITION_PLAN_CARRY_METHOD),
    }


def test_a_round_no_readable_team_disclosed_reads_its_own_transition_plan_and_is_never_carried_into() -> None:
    specs = rounds(("r1", None, ("d1",)), ("r2", None, ("d2",)))
    found, _ = transition_assigned(specs, {"d1": NONE, "d2": NONE}, {"d1": NAMES_SAMPLE, "d2": NONE})
    assert found == {"r1": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD)}


def test_the_k_aff_is_never_carried_into_a_round_holding_a_transition_plan_naming_a_policy_aff() -> None:
    specs = rounds(
        ("r1", "team-a", ("d1",)),
        ("r2", "team-a", ("d2",)),
        ("r3", "team-a", ("d3",)),
        ("r4", "team-a", ("d4",)),
    )
    plan_texts = {"d1": NONE, "d2": NONE, "d3": NONE, "d4": NONE}
    transition = {"d1": NONE, "d2": NAMES_SAMPLE, "d3": CONFLICTING, "d4": UNNAMED}
    found, counts = transition_assigned(specs, plan_texts, transition, markers={"d1"})
    assert found == {
        "r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD),
        "r2": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD),
        "r4": (KRITIKAL, KRITIKAL_AFF_CARRY_METHOD),
    }
    assert counts.refused_by_transition_plan == ("r2", "r3")
    assert counts.transition_conflicting == 1


def test_the_advantage_guard_counts_its_refusals_first() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)))
    found, counts = transition_assigned(
        specs, {"d1": NONE, "d2": NONE}, {"d1": NONE, "d2": NAMES_SAMPLE}, markers={"d1"}, advantages={"r2"}
    )
    assert found == {
        "r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD),
        "r2": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD),
    }
    assert (counts.refused_by_advantage, counts.refused_by_transition_plan) == (("r2",), ())


def test_a_round_with_its_own_k_aff_marker_stays_a_k_aff_and_is_counted() -> None:
    found, counts = transition_assigned(
        rounds(("r1", "team-a", ("d1",))), {"d1": NONE}, {"d1": NAMES_SAMPLE}, markers={"d1"}
    )
    assert found == {"r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD)}
    assert counts.transition_control == ("r1",)


def test_a_k_aff_team_reading_a_transition_plan_carries_neither() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)), ("r3", "team-a", ("d3",)))
    plan_texts = {"d1": NONE, "d2": NONE, "d3": NONE}
    found, _ = transition_assigned(
        specs, plan_texts, {"d1": NONE, "d2": NAMES_SAMPLE, "d3": NONE}, markers={"d1"}, advantages={"r3"}
    )
    assert found == {
        "r1": (KRITIKAL, KRITIKAL_AFF_MARKER_METHOD),
        "r2": (SAMPLE, TRANSITION_PLAN_TEXT_METHOD),
    }


def test_the_control_counts_only_a_disagreeing_aff() -> None:
    specs = rounds(("r1", "team-a", ("d1", "d2")), ("r2", "team-b", ("d3", "d4")), ("r3", "team-c", ("d5",)))
    plan_texts = {"d1": NAMES_SAMPLE, "d2": NONE, "d3": NAMES_SAMPLE, "d4": NONE, "d5": NONE}
    transition = {"d1": NONE, "d2": NAMES_CHILD, "d3": NONE, "d4": NAMES_NATIONAL, "d5": NAMES_OTHER}
    found, counts = transition_assigned(specs, plan_texts, transition, placed={"r3": frozenset({SAMPLE})})
    assert found == {"r1": (SAMPLE, PLAN_TEXT_METHOD), "r2": (SAMPLE, PLAN_TEXT_METHOD)}
    assert counts.transition_control == ("r3",)


def test_without_transition_readings_nothing_is_read_or_refused() -> None:
    specs = rounds(("r1", "team-a", ("d1",)), ("r2", "team-a", ("d2",)))
    found, counts = assign_affs(
        specs, {"d1": NONE, "d2": NONE}, {}, WORDS, KritikalSignals(KRITIKAL, frozenset({"d1"}), frozenset())
    )
    assert {one.round_key: one.method for one in found} == {
        "r1": KRITIKAL_AFF_MARKER_METHOD,
        "r2": KRITIKAL_AFF_CARRY_METHOD,
    }
    assert (counts.refused_by_transition_plan, counts.transition_conflicting, counts.transition_control) == (
        (),
        0,
        (),
    )

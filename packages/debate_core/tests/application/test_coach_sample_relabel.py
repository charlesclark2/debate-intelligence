"""The coach's relabelling sitting (`v1-e32-t46`): its rows, its order, what it writes and what it counts.

The PM's ruling: the session's listed rows are mixed with six control rows drawn at random from the other
labelled rows, by a stated seed, all shown in one random order and unmarked; only changed labels are written,
and the end prints changed and unchanged, split into listed and control. Every CSV here is invented.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from debate_core.application.coach_sample_relabel import (
    CONTROL_ROWS,
    SittingRow,
    copy_path,
    disclosed_side,
    relabel_counts,
    relabelled_sample,
    sitting_rows,
)

LISTED = (5, 11, 13, 16, 20, 21, 25, 26, 31, 33, 41, 57, 59)
LABELLED = tuple(range(1, 61, 1))


def test_the_sitting_is_the_listed_rows_and_six_controls_from_the_other_labelled_rows() -> None:
    rows = sitting_rows(LISTED, LABELLED, seed=20261105)

    assert CONTROL_ROWS == 6
    assert len(rows) == 19
    assert sorted(one.row for one in rows if one.listed) == sorted(LISTED)
    controls = [one.row for one in rows if not one.listed]
    assert len(controls) == 6
    assert len(set(controls)) == 6
    assert not set(controls) & set(LISTED)
    assert set(controls) <= set(LABELLED)


def test_the_same_seed_gives_the_same_sitting_and_another_seed_another() -> None:
    first = sitting_rows(LISTED, LABELLED, seed=7)

    assert sitting_rows(LISTED, LABELLED, seed=7) == first
    assert sitting_rows(LISTED, LABELLED, seed=8) != first


def test_the_sitting_mixes_the_controls_among_the_listed_rows() -> None:
    orders = [tuple(one.listed for one in sitting_rows(LISTED, LABELLED, seed=seed)) for seed in range(20)]

    assert all(order != (True,) * 13 + (False,) * 6 for order in orders)
    assert len(set(orders)) > 1


def test_controls_are_drawn_only_from_labelled_rows_off_the_list() -> None:
    labelled = (*LISTED, 2, 3, 4, 6, 7, 8)

    rows = sitting_rows(LISTED, labelled, seed=1)

    assert sorted(one.row for one in rows if not one.listed) == [2, 3, 4, 6, 7, 8]


def test_too_few_rows_off_the_list_for_the_controls_is_refused() -> None:
    with pytest.raises(ValueError, match="control"):
        sitting_rows(LISTED, (*LISTED, 2, 3), seed=1)


def test_a_listed_row_the_coach_did_not_label_is_refused() -> None:
    with pytest.raises(ValueError, match="row 99"):
        sitting_rows((*LISTED, 99), LABELLED, seed=1)


SAMPLE = (
    "sample_row,tag,headings,position,note,also\n"
    '1,"An invented tag, with a comma",Off case > Politics,politics-da,,\n'
    '2,"A tag with ""quotes""",Case,rural-adv,a note,\n'
    "3,A third invented tag,Answers,unsure,,\n"
)


def cells(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_only_the_changed_rows_position_cells_are_written() -> None:
    written = relabelled_sample(SAMPLE, {1: "at:politics-da"})

    before, after = cells(SAMPLE), cells(written)
    assert after[0] == {**before[0], "position": "at:politics-da"}
    assert after[1:] == before[1:]
    assert written.splitlines()[0] == SAMPLE.splitlines()[0]


def test_no_change_writes_the_sample_as_it_was() -> None:
    assert relabelled_sample(SAMPLE, {}) == SAMPLE


def test_a_change_to_a_row_the_sample_does_not_have_is_refused() -> None:
    with pytest.raises(ValueError, match="row 4"):
        relabelled_sample(SAMPLE, {4: "politics-da"})


def test_the_end_counts_changed_and_unchanged_split_into_listed_and_control() -> None:
    rows = (
        SittingRow(1, True),
        SittingRow(2, False),
        SittingRow(3, True),
        SittingRow(4, False),
        SittingRow(5, True),
    )

    assert relabel_counts(rows, {1, 2, 3}) == {
        "listed": {"changed": 2, "unchanged": 1},
        "control": {"changed": 1, "unchanged": 1},
    }


@pytest.mark.parametrize(
    ("sides", "words"),
    [
        ({"AFF"}, "affirmative"),
        ({"NEG"}, "negative"),
        ({"AFF", "NEG"}, "both sides"),
        ({"NEG", "UNKNOWN"}, "negative"),
        ({"UNKNOWN"}, "no readable side"),
        (set[str](), "no readable side"),
    ],
)
def test_the_disclosed_side_is_said_in_words(sides: set[str], words: str) -> None:
    assert disclosed_side(frozenset(sides)) == words


def test_the_copy_is_kept_beside_the_sample() -> None:
    sample = Path("/somewhere/coach-sample-labelled.csv")

    assert copy_path(sample) == Path("/somewhere/coach-sample-labelled.before-stance-relabel.csv")


# ------------------------------------------------------------------------------------------------
# The sitting itself: what the coach is shown and asked
# ------------------------------------------------------------------------------------------------

from debate_core.application.coach_sample_relabel import ShownRow, run_sitting  # noqa: E402
from debate_core.domain.landscape import Taxonomy  # noqa: E402

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "politics-da", "label": "Politics DA", "kind": "da", "side": "neg"},
            {"id": "rural-adv", "label": "Rural Advantage", "kind": "advantage", "side": "aff"},
        ],
    }
)
SHOWN = {
    1: ShownRow(
        tag="An invented tag", headings="Off case > Politics", side="affirmative", label="politics-da"
    ),
    2: ShownRow(
        tag="Another invented tag", headings="Case", side="negative", label="rural-adv", also="politics-da"
    ),
    3: ShownRow(tag="A third invented tag", headings="Answers", side="both sides", label="at:politics-da"),
}
ORDER = (SittingRow(3, True), SittingRow(1, False), SittingRow(2, True))


def sat(answers: list[str]) -> tuple[dict[int, str], list[str]]:
    typed = iter(answers)
    said: list[str] = []
    changes = run_sitting(ORDER, SHOWN, TAXONOMY, ask=lambda _: next(typed), say=said.append)
    return changes, said


def test_enter_keeps_every_label_and_nothing_changes() -> None:
    changes, _ = sat(["", "", ""])

    assert changes == {}


def test_the_coach_s_labels_are_written_as_the_sample_writes_them_and_only_when_changed() -> None:
    changes, _ = sat(["AT: politics-da", "At:Politics-DA", "at:rural-adv"])

    assert changes == {1: "at:politics-da", 2: "at:rural-adv"}


def test_a_label_naming_no_position_is_asked_again_without_echoing_it() -> None:
    changes, said = sat(["at:none", "made-up-da", "none", "", "unsure"])

    assert changes == {3: "none", 2: "unsure"}
    refusals = [line for line in said if line.startswith("Not taken")]
    assert len(refusals) == 2
    assert not any("made-up" in line for line in said)


def test_a_label_its_row_s_second_label_refuses_is_asked_again() -> None:
    changes, said = sat(["", "", "politics-da", "none", "rural-adv"])

    assert changes == {}
    assert any("second label" in line for line in said)


def test_each_card_shows_its_tag_headings_side_and_label_and_nothing_of_the_list() -> None:
    _, said = sat(["", "", ""])
    shown = "\n".join(said)

    for row in SHOWN.values():
        assert row.tag in shown
        assert row.headings in shown
        assert f"Disclosed on: {row.side}" in shown
        assert f"Your label: {row.label}" in shown
    assert "Card 1 of 3" in shown and "Card 3 of 3" in shown
    for word in ("listed", "control", "model", "answer was", "score", "row 3", "row 1"):
        assert word not in shown.casefold()
    assert (
        shown.index("A third invented tag")
        < shown.index("An invented tag")
        < shown.index("Another invented tag")
    )

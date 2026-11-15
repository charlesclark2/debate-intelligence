"""The held-out sample's sitting (`v1-e32-t50`): what it shows, what it takes, and what it writes.

The PM's ruling of 2026-11-14: two sittings of 60; each card shows its tag, headings and side and nothing of a
model, a score, a stratum or a mark; the coach labels the stance and may add a second label; and at the end of
the second sitting the first sample's rows 16, 33 and 57 follow, each answered `at:<id>`, `also <label>` or
`side`, a `side` answer writing nothing and named on the last line. Every CSV and tag here is invented.
"""

from __future__ import annotations

import csv
import io

import pytest

from debate_core.application.coach_sample_relabel import ShownRow, rewritten_cells
from debate_core.application.holdout_sitting import (
    SIDE_RULE_ROWS,
    holdout_counts,
    run_holdout_sitting,
    run_side_rows,
    side_rule_line,
    sitting_range,
)
from debate_core.domain.landscape import Taxonomy

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


def test_the_two_sittings_cover_rows_1_to_60_then_61_to_120() -> None:
    assert sitting_range("1-60") == tuple(range(1, 61))
    assert sitting_range("61-120") == tuple(range(61, 121))
    assert sitting_range("3, 5-7, 3") == (3, 5, 6, 7)
    for wrong in ("", "0-4", "9-2", ","):
        with pytest.raises(ValueError):
            sitting_range(wrong)


def test_the_side_rule_rows_are_16_33_and_57() -> None:
    assert SIDE_RULE_ROWS == (16, 33, 57)


# ------------------------------------------------------------------------------------------------
# The holdout's cards
# ------------------------------------------------------------------------------------------------

FRESH = {
    row: ShownRow(
        tag=f"An invented tag {row}", headings=f"Invented > Heading {row}", side="negative", label=""
    )
    for row in (1, 2, 3, 4, 5)
}


def sat(
    answers: list[str], shown: dict[int, ShownRow] | None = None
) -> tuple[dict[int, dict[str, str]], list[str]]:
    typed = iter(answers)
    said: list[str] = []
    rows = shown or FRESH
    changes = run_holdout_sitting(tuple(rows), rows, TAXONOMY, ask=lambda _: next(typed), say=said.append)
    return changes, said


def test_each_label_is_written_with_its_stance_and_its_second_label() -> None:
    changes, _ = sat(["AT: Politics-DA", "rural-adv, at:politics-da", "none", "unsure", ""])

    assert changes == {
        1: {"position": "at:politics-da", "also": ""},
        2: {"position": "rural-adv", "also": "at:politics-da"},
        3: {"position": "none", "also": ""},
        4: {"position": "unsure", "also": ""},
    }


def test_a_label_the_evaluation_would_refuse_is_asked_again_without_echoing_it() -> None:
    answers = [
        "made-up-da",
        "at:none",
        "none, rural-adv",
        "unsure, rural-adv",
        "politics-da, politics-da",
        "rural-adv",
    ]
    changes, said = sat([*answers, "", "", "", ""])

    assert changes == {1: {"position": "rural-adv", "also": ""}}
    refusals = [line for line in said if line.startswith("Not taken")]
    assert len(refusals) == 5
    assert not any("made-up" in line for line in said)


def test_enter_leaves_a_labelled_card_as_it_is_and_a_new_label_replaces_it() -> None:
    shown = {
        1: ShownRow(tag="Tag one", headings="One", side="affirmative", label="rural-adv"),
        2: ShownRow(tag="Tag two", headings="Two", side="negative", label="politics-da", also="at:rural-adv"),
    }

    changes, said = sat(["", "politics-da"], shown)

    assert changes == {2: {"position": "politics-da", "also": ""}}
    assert "Your label: rural-adv" in said and "Your second label: at:rural-adv" in said


def test_each_card_shows_its_tag_headings_and_side_and_nothing_of_a_model_score_stratum_or_mark() -> None:
    _, said = sat(["", "", "", "", ""])

    allowed = ("Card ", "Tag: ", "Headings: ", "Disclosed on: ")
    assert all(line == "" or line.startswith(allowed) for line in said)
    shown = "\n".join(said)
    for row in FRESH.values():
        assert row.tag in shown and row.headings in shown
    assert "Card 1 of 5" in shown and "Card 5 of 5" in shown
    for word in (
        "model",
        "score",
        "stratum",
        "threshold",
        "confidence",
        "holdout",
        "listed",
        "control",
        "row ",
    ):
        assert word not in shown.casefold()


def test_the_end_counts_labelled_unsure_and_blank_rows() -> None:
    changes, _ = sat(["rural-adv, politics-da", "none", "unsure", "", ""])

    assert holdout_counts(tuple(FRESH), FRESH, changes) == {
        "labelled": 2,
        "unsure": 1,
        "blank": 2,
        "second_labels": 1,
    }


# ------------------------------------------------------------------------------------------------
# The first sample's rows 16, 33 and 57
# ------------------------------------------------------------------------------------------------

FIRST = {
    16: ShownRow(tag="An invented tag", headings="Case > Rural", side="negative", label="rural-adv"),
    33: ShownRow(tag="Another invented tag", headings="Case", side="negative", label="unsure"),
    57: ShownRow(
        tag="A third invented tag", headings="K", side="affirmative", label="politics-da", also="rural-adv"
    ),
}


def sides(answers: list[str]) -> tuple[dict[int, dict[str, str]], tuple[int, ...], list[str]]:
    typed = iter(answers)
    said: list[str] = []
    found = run_side_rows(SIDE_RULE_ROWS, FIRST, TAXONOMY, ask=lambda _: next(typed), say=said.append)
    return found.cells, found.side_rule, said


def test_each_row_takes_an_at_label_a_second_label_or_side() -> None:
    cells, side_rule, _ = sides(["at:rural-adv", "side", "also at:politics-da"])

    assert cells == {16: {"position": "at:rural-adv"}, 57: {"also": "at:politics-da"}}
    assert side_rule == (33,)


def test_side_writes_nothing_and_the_last_line_names_its_rows() -> None:
    cells, side_rule, _ = sides(["side", "side", "side"])

    assert cells == {}
    assert side_rule_line(side_rule) == "The side rule is wrong here, the coach says, on row(s) 16, 33, 57."
    assert side_rule_line(()) == "The side rule: no row was answered side."


def test_anything_else_or_a_choice_the_evaluation_would_refuse_is_asked_again() -> None:
    answers = [
        "",  # row 16: nothing typed
        "rural-adv",  # not one of the three choices
        "at:none",  # answers no position
        "also none",  # a second label names a position
        "also rural-adv",  # its own label
        "also made-up-da",  # no active id
        "side",
        "also politics-da",  # row 33 is unsure: no label to add a second to
        "at:rural-adv",
        "at:rural-adv",  # row 57: its second label is rural-adv, which still reads beside it
    ]

    cells, side_rule, said = sides(answers)

    assert cells == {33: {"position": "at:rural-adv"}, 57: {"position": "at:rural-adv"}}
    assert side_rule == (16,)
    assert len([line for line in said if line.startswith("Not taken")]) == 7
    assert not any("made-up" in line for line in said)


def test_each_first_sample_row_shows_its_tag_headings_side_and_labels() -> None:
    _, _, said = sides(["side", "side", "side"])

    for row in FIRST.values():
        assert f"Tag: {row.tag}" in said and f"Disclosed on: {row.side}" in said
    assert "Your label: politics-da" in said and "Your second label: rural-adv" in said
    shown = "\n".join(said).casefold()
    for word in ("model", "score", "stratum", "confidence"):
        assert word not in shown


# ------------------------------------------------------------------------------------------------
# What is written
# ------------------------------------------------------------------------------------------------

SAMPLE = (
    "sample_row,tag,headings,position,note,also\r\n"
    '1,"An invented tag, with a comma",Off case > Politics,politics-da,,\r\n'
    '2,"A tag with ""quotes""",Case,,,\r\n'
    "3,A third invented tag,Answers,unsure,a note,\r\n"
)


def test_the_position_and_also_cells_are_written_and_every_other_row_keeps_its_bytes() -> None:
    written = rewritten_cells(SAMPLE, {2: {"position": "at:rural-adv", "also": "politics-da"}})

    lines = written.splitlines(keepends=True)
    original = SAMPLE.splitlines(keepends=True)
    assert lines[0] == original[0] and lines[1] == original[1] and lines[3] == original[3]
    (row,) = [line for line in csv.DictReader(io.StringIO(written, newline="")) if line["sample_row"] == "2"]
    assert (row["tag"], row["position"], row["also"]) == (
        'A tag with "quotes"',
        "at:rural-adv",
        "politics-da",
    )
    assert lines[2].endswith("\r\n")


def test_a_column_the_sample_does_not_have_is_refused() -> None:
    with pytest.raises(ValueError, match="no also column"):
        rewritten_cells("sample_row,position\n1,none\n", {1: {"also": "politics-da"}})

"""`files suggest` counts what a counterplan's draft left out as another position's (`v1-e33-t11`).

One additive key in `--json`, `other_positions_left_out`: the blocks and cards a counterplan's draft
left out because the position matcher places their heading under another position, and null for any
other position's draft, which leaves nothing out that way. The table's caption says the same counts.

A second, `affirmative_side_kept` (`v1-e33-t13`): the blocks and cards a counterplan's draft kept,
marked, because the matcher places their heading under an aff or an advantage, and null for any other
position's draft. The caption says those counts too.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from debate_cli.output import TableSpec
from debate_cli.presenters.files_presenter import suggest_rendered
from debate_core.application.file_suggest_service import (
    AffirmativeSideKept,
    OtherPositionsLeftOut,
    SuggestedCard,
    SuggestResult,
)
from debate_core.domain.caselist import Side


def result(
    position: str,
    other_positions: OtherPositionsLeftOut | None,
    affirmative_side_kept: AffirmativeSideKept | None = None,
) -> SuggestResult:
    return SuggestResult(
        path=Path("/drafts/draft.yaml"),
        caselist="synthfile26",
        snapshot=date(2026, 9, 15),
        topic="policy-synthetic-files",
        position=position,
        side=Side.NEG,
        recipe_hash="a" * 64,
        cards=(
            SuggestedCard(rank=1, teams_reading=5, fingerprint="b" * 64, block="states cp", pin_fields=()),
        ),
        other_positions=other_positions,
        affirmative_side_kept=affirmative_side_kept,
    )


def caption_of(
    position: str,
    other_positions: OtherPositionsLeftOut | None,
    affirmative_side_kept: AffirmativeSideKept | None = None,
) -> str:
    display = suggest_rendered(result(position, other_positions, affirmative_side_kept)).display
    assert isinstance(display, TableSpec) and display.caption is not None
    return display.caption


def test_a_counterplans_draft_reports_the_blocks_and_cards_it_left_out_as_one_key() -> None:
    payload = suggest_rendered(result("states-cp", OtherPositionsLeftOut(blocks=2, cards=3))).payload
    assert payload["other_positions_left_out"] == {"blocks": 2, "cards": 3}


def test_a_counterplans_table_says_what_it_left_out_even_when_it_is_nothing() -> None:
    assert "2 block(s) holding 3 card(s)" in caption_of("states-cp", OtherPositionsLeftOut(blocks=2, cards=3))
    assert "0 block(s) holding 0 card(s)" in caption_of("states-cp", OtherPositionsLeftOut(blocks=0, cards=0))


def test_another_positions_draft_has_the_key_null_and_says_nothing_of_it() -> None:
    payload = suggest_rendered(result("politics-da", None)).payload
    assert payload["other_positions_left_out"] is None
    assert "another position" not in caption_of("politics-da", None)


def test_a_counterplans_draft_reports_the_affirmative_side_blocks_and_cards_it_kept_as_one_key() -> None:
    payload = suggest_rendered(
        result("states-cp", OtherPositionsLeftOut(blocks=3, cards=4), AffirmativeSideKept(blocks=2, cards=5))
    ).payload
    assert payload["other_positions_left_out"] == {"blocks": 3, "cards": 4}
    assert payload.get("affirmative_side_kept") == {"blocks": 2, "cards": 5}


def test_a_counterplans_table_says_what_it_kept_as_affirmative_side_even_when_it_is_nothing() -> None:
    kept = caption_of(
        "states-cp", OtherPositionsLeftOut(blocks=3, cards=4), AffirmativeSideKept(blocks=2, cards=5)
    )
    assert "3 block(s) holding 4 card(s) left out" in kept
    assert "2 block(s) holding 5 card(s) kept under an aff's or advantage's heading" in kept
    none = caption_of(
        "states-cp", OtherPositionsLeftOut(blocks=0, cards=0), AffirmativeSideKept(blocks=0, cards=0)
    )
    assert "0 block(s) holding 0 card(s) kept under an aff's or advantage's heading" in none


def test_another_positions_draft_has_the_affirmative_side_key_null_and_says_nothing_of_it() -> None:
    payload = suggest_rendered(result("politics-da", None)).payload
    assert "affirmative_side_kept" in payload
    assert payload["affirmative_side_kept"] is None
    assert "advantage" not in caption_of("politics-da", None)

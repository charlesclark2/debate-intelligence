"""`files suggest` counts what a counterplan's draft left out as another position's (`v1-e33-t11`).

One additive key in `--json`, `other_positions_left_out`: the blocks and cards a counterplan's draft
left out because the position matcher places their heading under another position, and null for any
other position's draft, which leaves nothing out that way. The table's caption says the same counts.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from debate_cli.output import TableSpec
from debate_cli.presenters.files_presenter import suggest_rendered
from debate_core.application.file_suggest_service import OtherPositionsLeftOut, SuggestedCard, SuggestResult
from debate_core.domain.caselist import Side


def result(position: str, other_positions: OtherPositionsLeftOut | None) -> SuggestResult:
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
    )


def caption_of(position: str, other_positions: OtherPositionsLeftOut | None) -> str:
    display = suggest_rendered(result(position, other_positions)).display
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

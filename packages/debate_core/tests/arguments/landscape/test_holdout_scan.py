"""The held-out sample's own scan hits (`v1-e32-t50`, the PM's ruling of 2026-11-14).

The evaluation's scan reads every cassette of the prompt, so the listing keeps the holdout's own: the
cassettes whose `items` are a card list its replay sent, and the repairs whose failed prompt holds one.
Every school, code, tag and cite here is invented.
"""

from __future__ import annotations

import json
from typing import Any

from debate_core.arguments.landscape.holdout_scan import holdout_scan_hits, own_cassettes, own_repairs
from debate_core.arguments.landscape.scan_hits import HitField, HitKind, ScanNames

HOLDOUT_ITEMS = [
    {"item": "c1", "headings": ["1NC", "Framing"], "tag": "Probability first", "cite": "Szabo 24"}
]
FIRST_ITEMS = [
    {"item": "c1", "headings": ["1AC", "Costs"], "tag": "Premiums are rising", "cite": "Delacroix 25"}
]
NAMES = ScanNames.of({"Brindle Valley": ["BV"], "Quillmere Academy": ["QW"]})


def _cassette(items: list[dict[str, Any]], rationale: str, *, compact: bool = False) -> str:
    separators = (",", ":") if compact else (", ", ": ")
    return json.dumps(
        {
            "request": {
                "prompt": {
                    "prompt_id": "landscape.classify_position",
                    "prompt_version": "1.3.1",
                    "variables": {"items": json.dumps(items, separators=separators)},
                }
            },
            "response": {"output": {"answers": [{"item": "c1", "rationale": rationale}]}},
        }
    )


def _repair(items: list[dict[str, Any]], rationale: str) -> str:
    failed_user = f"Place each card [one answer per card] on a position.\n\n{json.dumps(items)}\n"
    return json.dumps(
        {
            "request": {
                "prompt": {
                    "prompt_id": "model.repair",
                    "variables": {
                        "failed_prompt": "landscape.classify_position@1.3.1",
                        "failed_system": "You place debate cards.",
                        "failed_user": failed_user,
                    },
                }
            },
            "response": {"output": {"answers": [{"item": "c1", "rationale": rationale}]}},
        }
    )


SENT = (json.dumps(HOLDOUT_ITEMS),)


def test_only_cassettes_whose_items_the_holdout_sent_are_its_own_however_they_are_spaced() -> None:
    holdout = _cassette(HOLDOUT_ITEMS, "a plain answer", compact=True)
    first = _cassette(FIRST_ITEMS, "a plain answer")
    unreadable = "not a cassette's JSON"

    assert own_cassettes([first, holdout, unreadable], SENT) == [holdout]


def test_only_repairs_whose_failed_prompt_holds_a_list_the_holdout_sent_are_its_own() -> None:
    holdout = _repair(HOLDOUT_ITEMS, "a plain answer")
    first = _repair(FIRST_ITEMS, "a plain answer")

    assert own_repairs([first, holdout, "{}"], SENT) == [holdout]


def test_the_listing_numbers_the_holdouts_hits_alone_and_counts_those_no_mark_sets_aside() -> None:
    cassettes = [
        _cassette(FIRST_ITEMS, "as Quillmere Academy reads it"),
        _cassette(HOLDOUT_ITEMS, "as Brindle Valley reads it"),
    ]
    repairs = [
        _repair(FIRST_ITEMS, "Quillmere Academy again"),
        _repair(HOLDOUT_ITEMS, "Brindle Valley again"),
    ]

    listed = holdout_scan_hits(SENT, cassettes, repairs, NAMES)

    assert (listed.input_batches, listed.cassettes, listed.repair_cassettes) == (1, 1, 1)
    rationales = [hit for hit in listed.hits if hit.where is HitField.RATIONALE]
    assert [(hit.text, hit.kind, hit.matched) for hit in rationales] == [
        ("cassette 1", HitKind.SCHOOL, "brindle valley"),
        ("repair cassette 1", HitKind.SCHOOL, "brindle valley"),
    ]
    assert all("quillmere" not in hit.matched for hit in listed.hits)
    assert listed.left == len(rationales) == 2


def test_a_hit_a_mark_sets_aside_is_listed_but_not_left() -> None:
    names = ScanNames.of({"Lantern": ["LN"]}, taxonomy_text="the lantern view")
    listed = holdout_scan_hits(SENT, [_cassette(HOLDOUT_ITEMS, "a lantern reading")], [], names)

    assert [(hit.where, hit.in_taxonomy, hit.in_input) for hit in listed.hits] == [
        (HitField.RATIONALE, True, False)
    ]
    assert listed.left == 0

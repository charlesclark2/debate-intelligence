"""A scan hit marked as a JSON key's name or a taxonomy word leaves its text clean (`v1-e32-t44`).

The PM's rulings of 2026-11-05: a hit carrying a mark the scan trusts
(:data:`~debate_core.arguments.landscape.scan_hits.MARKS_THAT_SET_A_HIT_ASIDE`) no longer counts toward
`clean`; a hit with no mark, one naming a team, or one the text's own cards sent still does. Nothing is
hidden: the scan's counts and every hit's marks are the same either way, and what `clean` set aside is
counted by mark.

Every school, team code, tournament and word is invented. `Confidence` is a school spelled like a key of
every cassette (`confidence`), as `v1-e32-t39` found one; `OR` is a team code whose word is a word of the
taxonomy's description, as `v1-e32-t39`'s team-code hits were.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence

import pytest

from debate_core.arguments.landscape.model_stage import NameScan, name_scan, prompt_variables
from debate_core.arguments.landscape.scan_hits import (
    MARKS,
    MARKS_THAT_KEEP_A_HIT,
    MARKS_THAT_SET_A_HIT_ASIDE,
    HitField,
    HitKind,
    ScanHit,
    ScanNames,
    cassette_hits,
    hit_counts,
    input_batch_hits,
    mark_counts,
    marked_scan,
    sets_aside,
)
from debate_core.domain.landscape import Taxonomy

CASELIST_NAMES = {"Confidence": ("OR",), "Willow Bend": ("WB",)}
TOURNAMENTS = ("Pinecrest Open",)
TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": "localities-cp",
                "label": "Localities CP",
                "kind": "cp",
                "side": "neg",
                "description": "The states or the localities act instead",
            },
        ],
    }
)
POSITIONS = str(prompt_variables(TAXONOMY, ())["positions"])
NAMES = ScanNames.of(CASELIST_NAMES, TOURNAMENTS, taxonomy_text=POSITIONS)


def items(tag: str = "Spending tradeoff", headings: Sequence[str] = ("Budget",)) -> str:
    """One card's `items` variable as the prompt sends it."""
    return json.dumps(
        [{"id": "item-1", "headings": list(headings), "tag": tag, "cite": None, "excerpt": None}]
    )


def cassette(rationale: str, *, sent: str | None = None) -> str:
    """A `landscape.classify_position` cassette: the card sent, the positions and one answer."""
    return json.dumps(
        {
            "caselists": ["hspolicy99"],
            "request": {
                "prompt": {
                    "prompt_id": "landscape.classify_position",
                    "variables": {"items": sent or items(), "positions": POSITIONS},
                }
            },
            "response": {
                "output": {
                    "answers": [
                        {
                            "item": "item-1",
                            "position_id": "localities-cp",
                            "confidence": 0.8,
                            "rationale": rationale,
                        }
                    ]
                },
                "route": {"model_id": "recorded-model"},
            },
        }
    )


def scanned(texts: Sequence[str], names: ScanNames = NAMES, *, others: Sequence[str] = TOURNAMENTS):
    """The evaluation's cassette scan of `texts`, judged by their hits' marks."""
    return marked_scan(
        texts,
        lambda text: cassette_hits("cassette", text, names),
        CASELIST_NAMES,
        others,
        leave_out=(POSITIONS,),
    )


MARKED_ONLY = cassette("read with confidence: the states or the localities act")
"""A rationale whose two hits are a school spelled like a key and a team-code word of the taxonomy."""
UNMARKED = cassette("as willow bend reads the counterplan")


def test_scan_of_a_text_whose_every_hit_is_a_json_key_or_a_taxonomy_word_is_clean() -> None:
    hits = cassette_hits("cassette 1", MARKED_ONLY, NAMES)
    assert {(hit.kind, hit.matched, hit.json_key, hit.in_taxonomy) for hit in hits} == {
        (HitKind.SCHOOL, "confidence", True, False),
        (HitKind.TEAM_CODE, "or", False, True),
    }

    scan = scanned([MARKED_ONLY])

    assert scan.clean
    assert (scan.texts, scan.schools, scan.team_codes, scan.other_names, scan.texts_left) == (1, 1, 1, 0, 0)
    assert scan.set_aside == {"texts": 1, "hits": 2, "json_key": 1, "in_taxonomy": 1}


def test_scan_of_a_text_with_one_unmarked_hit_is_not_clean() -> None:
    marked_and_not = cassette("read with confidence, as willow bend reads it")

    scan = scanned([marked_and_not])

    assert not scan.clean
    assert (scan.schools, scan.texts_left) == (1, 1)
    assert scan.set_aside == {"texts": 0, "hits": 0, "json_key": 0, "in_taxonomy": 0}


def test_scan_counts_each_text_alone_one_set_aside_and_one_left() -> None:
    scan = scanned([MARKED_ONLY, UNMARKED, cassette("a plain reason")])

    assert not scan.clean
    assert (scan.texts, scan.schools, scan.team_codes, scan.texts_left) == (3, 2, 1, 1)
    assert scan.set_aside == {"texts": 1, "hits": 2, "json_key": 1, "in_taxonomy": 1}


def test_scan_of_a_text_whose_marked_hit_names_a_team_is_not_clean() -> None:
    """A tournament spelled like the school that is a key: its hit is a team's name, key or not."""
    names = ScanNames.of(CASELIST_NAMES, ("Confidence",), taxonomy_text=POSITIONS)
    hits = cassette_hits("cassette 1", cassette("read with confidence"), names)
    assert {(hit.kind, hit.json_key, hit.team_name) for hit in hits} == {
        (HitKind.SCHOOL, True, False),
        (HitKind.TOURNAMENT, True, True),
    }

    scan = scanned([cassette("read with confidence")], names, others=("Confidence",))

    assert not scan.clean
    assert (scan.schools, scan.other_names, scan.texts_left) == (1, 1, 1)


def test_scan_of_a_text_whose_marked_hit_its_cards_sent_is_not_clean() -> None:
    """The team-code word is a taxonomy word, but this card's tag sent it: copied from a card, it counts.
    So does the rationale repeating it."""
    text = cassette("the states or the localities", sent=items(tag="The states or the center"))
    hits = cassette_hits("cassette 1", text, NAMES)
    assert {(hit.where, hit.in_taxonomy, hit.in_input) for hit in hits} == {
        (HitField.TAG, True, True),
        (HitField.RATIONALE, True, True),
    }

    scan = scanned([text])

    assert not scan.clean
    assert (scan.team_codes, scan.texts_left) == (1, 1)


def test_scan_of_a_prompt_input_sets_none_of_its_hits_aside() -> None:
    """Every hit in a prompt input is in the cards it sends, so a taxonomy word there still counts."""
    sent = items(tag="The states or the center")

    scan = marked_scan(
        [sent], lambda text: input_batch_hits("input batch", text, NAMES), CASELIST_NAMES, TOURNAMENTS
    )

    assert not scan.clean
    assert (scan.team_codes, scan.texts_left) == (1, 1)


def test_scan_of_a_named_text_with_no_hit_listed_is_not_clean() -> None:
    """The listing fails toward unclean: a text the scan counts but whose hits are not all found is left."""
    scan = marked_scan([MARKED_ONLY], lambda _: [], CASELIST_NAMES, TOURNAMENTS, leave_out=(POSITIONS,))

    assert not scan.clean
    assert scan.texts_left == 1


def test_scan_of_a_named_text_whose_hits_cover_only_some_kinds_is_not_clean() -> None:
    """Set aside needs a set-aside hit of every kind the scan counted in the text."""

    def school_hits_only(text: str) -> list[ScanHit]:
        return [hit for hit in cassette_hits("cassette", text, NAMES) if hit.kind is HitKind.SCHOOL]

    scan = marked_scan([MARKED_ONLY], school_hits_only, CASELIST_NAMES, TOURNAMENTS, leave_out=(POSITIONS,))

    assert not scan.clean


def test_scan_not_judged_by_marks_is_unclean_with_any_count() -> None:
    """A scan built without its hits' marks keeps the rule before `v1-e32-t44`: any count is unclean."""
    assert not NameScan(texts=1, schools=1).clean
    assert not NameScan(texts=1, other_names=1, set_aside={"texts": 1}).clean
    assert NameScan(texts=1).clean


def test_scan_of_texts_naming_nothing_is_clean_and_sets_nothing_aside() -> None:
    scan = scanned([cassette("a plain reason"), cassette("another")])

    assert scan.clean
    assert (scan.texts, scan.texts_left) == (2, 0)
    assert scan.set_aside == {"texts": 0, "hits": 0, "json_key": 0, "in_taxonomy": 0}


def test_scan_counts_and_marks_are_the_same_whether_or_not_clean_sets_hits_aside() -> None:
    """Nothing is hidden: the counts are `name_scan`'s, and every hit keeps its marks."""
    texts = [MARKED_ONLY, UNMARKED]
    counted = name_scan(texts, CASELIST_NAMES, TOURNAMENTS, leave_out=(POSITIONS,))

    judged = scanned(texts)
    alone = scanned([MARKED_ONLY])

    assert (judged.texts, judged.schools, judged.team_codes, judged.other_names) == (
        counted.texts,
        counted.schools,
        counted.team_codes,
        counted.other_names,
    )
    assert (alone.texts, alone.schools, alone.team_codes, alone.other_names) == (1, 1, 1, 0)
    hits = [hit for text in texts for hit in cassette_hits("cassette", text, NAMES)]
    assert hit_counts(hits) == {"school": {"model rationale": 2}, "team-code word": {"model rationale": 1}}
    assert mark_counts(hits) == {
        "model rationale": {"hits": 3, "team_name": 0, "in_taxonomy": 1, "json_key": 1, "in_input": 0}
    }


def test_scan_trusts_only_the_json_key_and_taxonomy_word_marks() -> None:
    """The one place the trusted marks are named; a new mark on `ScanHit` must be added to `MARKS`."""
    marks = tuple(one.name for one in dataclasses.fields(ScanHit) if one.type in ("bool", bool))

    assert set(marks) == set(MARKS)
    assert MARKS_THAT_SET_A_HIT_ASIDE == ("json_key", "in_taxonomy")
    assert MARKS_THAT_KEEP_A_HIT == ("team_name", "in_input")


@pytest.mark.parametrize(
    ("marks", "set_aside"),
    [
        ({}, False),
        ({"json_key": True}, True),
        ({"in_taxonomy": True}, True),
        ({"json_key": True, "in_taxonomy": True}, True),
        ({"json_key": True, "in_input": True}, False),
        ({"in_taxonomy": True, "in_input": True}, False),
        ({"json_key": True, "team_name": True}, False),
        ({"in_taxonomy": True, "team_name": True}, False),
        ({"in_input": True}, False),
        ({"team_name": True}, False),
    ],
)
def test_scan_sets_a_hit_aside_by_its_marks(marks: dict[str, bool], set_aside: bool) -> None:
    hit = ScanHit(
        text="cassette 1",
        where=HitField.RATIONALE,
        kind=HitKind.TOURNAMENT,
        matched="pinecrest open",
        before="",
        after="",
        **marks,
    )

    assert sets_aside(hit) is set_aside

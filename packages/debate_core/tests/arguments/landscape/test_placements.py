"""The placements listing and the apply step's summary (`v1-e32-t64`), on invented disclosures.

The coach's overrides rule `politics` a Spending DA and `solvency` no position. Three sources, one team
each (ONE negative, TWO affirmative, THREE negative):

====  ==========================  ======================  ==============================================
card  path                        tag                     the matcher
====  ==========================  ======================  ==============================================
a0    Spending DA                 Deficits rise           spending-da, ALIAS
a1    Spending DA > Link          Plan spends             spending-da, INHERITED from the alias
a2    Spending DA > Solvency      Fifty states solve      spending-da, INHERITED; its tag names states-cp
a3    Politics                    Elections shift         spending-da, OVERRIDE
a4    NHI Aff                     Medicare saves lives    nhi-medicare, its tag under the alias nhi aff
b0    Spending DA                 Deficits rise           spending-da, ALIAS
b1    AT: Cap K                   No alt                  cap-k, ALIAS (the answer row)
b2    Solvency                    Fifty states solve      states-cp by its tag alone (0.5), nothing places
b3    Politics > Impact           War                     spending-da, INHERITED from the override
b4    NHI Aff                     Coverage rises          nhi-aff, ALIAS
c0    Cap K                       Cap bad                 cap-k, ALIAS (one team: left out)
c1    Solvency > Spending DA      Deficits rise           spending-da, ALIAS (Solvency above it)
c2    Politics                    Elections shift         spending-da, OVERRIDE
c3    AT: Cap K                   No alt                  cap-k, ALIAS (the answer row)
====  ==========================  ======================  ==============================================

Every row and count below was worked out by hand from this table (working agreement 6). Every school,
team, heading and tag is invented.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from debate_core.arguments.landscape.matcher import HeadingRule, PositionMatcher, read_items
from debate_core.arguments.landscape.placements import (
    PLACEMENT_COLUMNS,
    DecisionEffect,
    Destination,
    PlacedBy,
    PlacedItem,
    build_placement_listing,
    placed_item,
    placement_changes,
    write_placements_csv,
)
from debate_core.arguments.landscape.review_queue import REVIEW_QUEUE_COLUMNS
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules

TOPIC = "policy-sample-topic"

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": TOPIC,
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": "spending-da",
                "label": "Spending DA",
                "kind": "da",
                "side": "neg",
                "aliases": ["spending da"],
            },
            {
                "id": "states-cp",
                "label": "States CP",
                "kind": "cp",
                "side": "neg",
                "aliases": ["states cp"],
                "tag_keywords": ["fifty states"],
            },
            {"id": "cap-k", "label": "Cap K", "kind": "k", "side": "neg", "aliases": ["cap k"]},
            {"id": "nhi-aff", "label": "NHI Aff", "kind": "aff", "side": "aff", "aliases": ["nhi aff"]},
            {
                "id": "nhi-medicare",
                "label": "NHI Medicare",
                "kind": "aff",
                "side": "aff",
                "parent": "nhi-aff",
                "tag_keywords": ["medicare"],
            },
        ],
    }
)


def rules(*decided: tuple[str, str | None]) -> OverrideRules:
    return OverrideRules.model_validate(
        {
            "topic_id": TOPIC,
            "overrides": [{"heading": heading, "position_id": one} for heading, one in decided],
        }
    )


CURRENT = rules(("politics", "spending-da"), ("solvency", None))


def team(identity: str, side: Side) -> SeedTeam:
    return SeedTeam(identity=identity, side=side, names=(f"School {identity}", f"Code{identity}"))


def source(number: int, owner: SeedTeam, *cards: tuple[tuple[str, ...], str]) -> SeedSource:
    return SeedSource(
        sha256=f"{number:x}".rjust(64, "0"),
        teams=(owner,),
        cards=tuple(
            SeedCard(tag=tag, section_path=path, first_element_index=index * 3)
            for index, (path, tag) in enumerate(cards)
        ),
    )


ONE, TWO, THREE = team("one", Side.NEG), team("two", Side.AFF), team("three", Side.NEG)
SOURCES = (
    source(
        1,
        ONE,
        (("Spending DA",), "Deficits rise"),
        (("Spending DA", "Link"), "Plan spends"),
        (("Spending DA", "Solvency"), "Fifty states solve"),
        (("Politics",), "Elections shift"),
        (("NHI Aff",), "Medicare saves lives"),
    ),
    source(
        2,
        TWO,
        (("Spending DA",), "Deficits rise"),
        (("AT: Cap K",), "No alt"),
        (("Solvency",), "Fifty states solve"),
        (("Politics", "Impact"), "War"),
        (("NHI Aff",), "Coverage rises"),
    ),
    source(
        3,
        THREE,
        (("Cap K",), "Cap bad"),
        (("Solvency", "Spending DA"), "Deficits rise"),
        (("Politics",), "Elections shift"),
        (("AT: Cap K",), "No alt"),
    ),
)
NAMES = CaselistNames({})


def placed_items(
    overrides: OverrideRules = CURRENT, sources: tuple[SeedSource, ...] = SOURCES
) -> list[PlacedItem]:
    matcher = PositionMatcher(TAXONOMY, overrides)
    return [
        placed_item(matcher, item, matcher.place(item), one.teams)
        for one in sources
        for item in read_items(one, NAMES)
    ]


def listing(**options: Any) -> Any:
    matcher = PositionMatcher(TAXONOMY, CURRENT)
    return build_placement_listing(placed_items(), heading_candidates=matcher.heading_candidates, **options)


def written(rows: Any) -> str:
    stream = io.StringIO(newline="")
    write_placements_csv(rows, stream)
    return stream.getvalue()


HEADER = ",".join(PLACEMENT_COLUMNS) + "\r\n"


def test_placement_columns_are_the_queues_with_how_placed_and_the_position() -> None:
    queue = list(REVIEW_QUEUE_COLUMNS)
    assert [one for one in PLACEMENT_COLUMNS if one in queue] == queue
    assert set(PLACEMENT_COLUMNS) - set(queue) == {
        "placed_by",
        "position",
        "cards_inherited",
        "cards_tag_names_another",
    }
    assert PLACEMENT_COLUMNS[-1] == "decision"


def test_placement_listing_rows_counted_by_hand_placed_rows_first_by_cards() -> None:
    assert written(listing().rows) == (
        HEADER
        + "spending da,false,alias,spending-da,3,3,1,2,5,2,1,states-cp,\r\n"
        + "politics,false,override,spending-da,3,3,1,2,3,1,0,,\r\n"
        + "cap k,true,alias,cap-k,2,2,1,1,2,0,0,,\r\n"
        + "nhi aff,false,alias,nhi-aff,2,2,1,1,2,0,0,,\r\n"
        + "solvency,false,none,,3,3,1,2,2,,,states-cp,\r\n"
    )


def test_placement_listing_leaves_out_a_heading_fewer_teams_use_and_counts_it() -> None:
    found = listing()
    counts = found.counts
    assert (counts.headings, counts.rows, counts.placed_rows, counts.none_rows) == (6, 5, 4, 1)
    assert counts.left_out_below_minimum_teams == 1
    assert ("cap k", False) not in {(row.normalized_heading, row.answer) for row in found.rows}


def test_placement_listing_lists_the_rare_heading_with_a_lower_minimum() -> None:
    found = listing(minimum_teams=1)
    assert found.counts.left_out_below_minimum_teams == 0
    assert [(row.normalized_heading, row.answer, row.placed_by) for row in found.rows] == [
        ("spending da", False, PlacedBy.ALIAS),
        ("politics", False, PlacedBy.OVERRIDE),
        ("cap k", True, PlacedBy.ALIAS),
        ("nhi aff", False, PlacedBy.ALIAS),
        ("cap k", False, PlacedBy.ALIAS),
        ("solvency", False, PlacedBy.NONE),
    ]
    rare = found.rows[4]
    assert (rare.documents, rare.teams, rare.aff_teams, rare.neg_teams, rare.cards) == (1, 1, 0, 1, 1)


def test_placement_listing_refuses_a_minimum_under_one() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        listing(minimum_teams=0)


def test_placement_listing_names_no_school_team_or_tag() -> None:
    text = written(listing(minimum_teams=1).rows).casefold()
    for word in ("school", "codeone", "deficits", "fifty", "medicare saves", "elections"):
        assert word not in text


def test_placement_listing_is_read_back_by_the_queues_decision_reader() -> None:
    from debate_core.arguments.landscape.review_queue import Decision, read_decisions_csv

    filled = written(listing().rows).replace(
        "politics,false,override,spending-da,3,3,1,2,3,1,0,,",
        "politics,false,override,spending-da,3,3,1,2,3,1,0,,none",
    )
    assert read_decisions_csv(io.StringIO(filled)) == (Decision("politics", None),)


# ------------------------------------------------------------------------------------------------
# What a decision does before it is written
# ------------------------------------------------------------------------------------------------


def effects(
    after: OverrideRules, changed: set[str], sources: tuple[SeedSource, ...] = SOURCES
) -> tuple[DecisionEffect, ...]:
    return placement_changes(
        sources, NAMES, PositionMatcher(TAXONOMY, CURRENT), PositionMatcher(TAXONOMY, after), changed
    )


def test_placement_changes_say_where_each_decisions_cards_go() -> None:
    after = rules(("politics", "states-cp"), ("solvency", None), ("spending da", None))
    assert effects(after, {"politics", "spending da"}) == (
        DecisionEffect(
            heading="spending da",
            before=HeadingRule("alias", "spending-da"),
            after=None,
            cards=5,
            moves={Destination.DECIDED: 3, Destination.QUEUE: 1, Destination.TAG_KEYWORD: 1},
        ),
        DecisionEffect(
            heading="politics",
            before=HeadingRule("override", "spending-da"),
            after="states-cp",
            cards=3,
            moves={Destination.DECISION: 3},
        ),
    )


def test_placement_changes_name_a_heading_above_same_or_other_position() -> None:
    above = (
        source(
            4,
            ONE,
            (("Cap K", "Spending DA"), "Deficits rise"),
            (("Politics", "Spending DA"), "Deficits rise"),
        ),
    )
    after = rules(("politics", "spending-da"), ("solvency", None), ("spending da", None))
    assert effects(after, {"spending da"}, above) == (
        DecisionEffect(
            heading="spending da",
            before=HeadingRule("alias", "spending-da"),
            after=None,
            cards=2,
            moves={Destination.HEADING_ABOVE_OTHER_POSITION: 1, Destination.HEADING_ABOVE_SAME_POSITION: 1},
        ),
    )


def test_placement_changes_list_a_decision_that_moves_no_card() -> None:
    after = rules(("politics", "spending-da"), ("solvency", None), ("fed key", "states-cp"))
    assert effects(after, {"fed key"}) == (
        DecisionEffect(
            heading="fed key", before=HeadingRule("undecided", None), after="states-cp", cards=0, moves={}
        ),
    )

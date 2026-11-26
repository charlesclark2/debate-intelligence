"""`scripts/count_heading_placements.py` on a planted store (`v1-e32-t64`): the counts the proposal rests on.

Two invented sources. Every expected count below was worked out by hand from these cards (working
agreement 6), not printed by the script and copied. The overrides rule `politics` a Spending DA and
`solvency` no position.

* **one**, disclosed by a negative team and an affirmative team:

  ====  ==========================  ======================  =====================================
  card  path                        tag                     the matcher
  ====  ==========================  ======================  =====================================
  c0    Spending DA                 (invented claim)        spending-da, ALIAS
  c1    Spending DA > Link          (invented claim)        spending-da, INHERITED from an alias
  c2    Spending DA > Solvency      Fifty states solve      spending-da, INHERITED from an alias
  c3    Politics                    (invented claim)        spending-da, OVERRIDE
  c4    AT: Cap K                   (invented claim)        cap-k, ALIAS (an answer row)
  c5    Solvency                    (invented claim)        decided: ruled no position
  c6    (none)                      Fifty states solve      states-cp, tag keyword alone, no heading
  c7    NHI Aff                     Medicare saves lives    nhi-medicare, its tag under nhi-aff
  c8    Politics > Impact           (invented claim)        spending-da, INHERITED from an override
  ====  ==========================  ======================  =====================================

* **two**, disclosed by a third team, a negative one:

  ====  ==========================  ======================  =====================================
  card  path                        tag                     the matcher
  ====  ==========================  ======================  =====================================
  d0    Spending DA                 (invented claim)        spending-da, ALIAS
  d1    Cap K                       (invented claim)        cap-k, ALIAS (one team: left out)
  d2    Solvency                    Fifty states solve      states-cp, tag alone, headings ruled none
  d3    Uniqueness                  Fifty states solve      states-cp, tag alone, undecided heading
  d4    NHI Aff                     (invented claim)        nhi-aff, ALIAS
  d5    Cap K > Spending DA         (invented claim)        spending-da, ALIAS (Cap K above)
  d6    Politics > Spending DA      (invented claim)        spending-da, ALIAS (Politics above)
  d7    Solvency > Cap K            (invented claim)        cap-k, ALIAS (one team: left out)
  ====  ==========================  ======================  =====================================

Every school, team code, tournament and heading here is invented.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_heading_placements as script  # noqa: E402

CASELIST = "hspolicy99"
TOPIC = "policy-sample-topic"

TOPICS = f"""\
schema_version: 1
topics:
  - id: {TOPIC}
    event: POLICY
    taxonomy_version: 1.0.0
    caselists:
      - {{caselist: {CASELIST}, from: 2026-09-01, to: 2026-12-31}}
"""

TAXONOMY = f"""\
schema_version: 1
topic_id: {TOPIC}
taxonomy_version: 1.0.0
event: POLICY
positions:
  - {{id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}}
  - {{id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp],
     tag_keywords: [fifty states]}}
  - {{id: cap-k, label: Cap K, kind: k, side: neg, aliases: [cap k]}}
  - {{id: nhi-aff, label: NHI Aff, kind: aff, side: aff, aliases: [nhi aff]}}
  - {{id: nhi-medicare, label: NHI Medicare, kind: aff, side: aff, parent: nhi-aff,
     tag_keywords: [medicare]}}
"""

OVERRIDES = f"""\
schema_version: 1
topic_id: {TOPIC}
overrides:
  - heading: politics
    position_id: spending-da
    decided: '2026-10-24'
  - heading: solvency
    position_id: null
    decided: '2026-10-24'
"""

NEG_ONE = "School One/CodeOne/School One-CodeOne-Neg-Sample Invitational-Round 1.docx"
AFF_TWO = "School Two/CodeTwo/School Two-CodeTwo-Aff-Sample Invitational-Round 1.docx"
NEG_THREE = "School Three/CodeThree/School Three-CodeThree-Neg-Sample Invitational-Round 2.docx"
FIFTY = "Fifty states solve"

PLANTED_WORDS = (
    "School One",
    "CodeOne",
    "School Two",
    "School Three",
    "Sample Invitational",
    "spending da",
    "politics",
    "solvency",
    "uniqueness",
    "nhi aff",
    "cap k",
    "Fifty",
    "Medicare",
    "invented",
)


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.data_dir = tmp_path / "data"
        store = PlantedCaselist(self.data_dir, CASELIST)
        store.source(
            "one",
            [
                PlantedCard(("Spending DA",)),
                PlantedCard(("Spending DA", "Link")),
                PlantedCard(("Spending DA", "Solvency"), tag=FIFTY),
                PlantedCard(("Politics",)),
                PlantedCard(("AT: Cap K",)),
                PlantedCard(("Solvency",)),
                PlantedCard((), tag=FIFTY),
                PlantedCard(("NHI Aff",), tag="Medicare saves lives"),
                PlantedCard(("Politics", "Impact")),
            ],
            disclosures=[("2026-09-08", NEG_ONE), ("2026-09-08", AFF_TWO)],
        )
        store.source(
            "two",
            [
                PlantedCard(("Spending DA",)),
                PlantedCard(("Cap K",)),
                PlantedCard(("Solvency",), tag=FIFTY),
                PlantedCard(("Uniqueness",), tag=FIFTY),
                PlantedCard(("NHI Aff",)),
                PlantedCard(("Cap K", "Spending DA")),
                PlantedCard(("Politics", "Spending DA")),
                PlantedCard(("Solvency", "Cap K")),
            ],
            disclosures=[("2026-09-15", NEG_THREE)],
        )
        self.config_dir = tmp_path / "config"
        (self.config_dir / "taxonomies").mkdir(parents=True)
        (self.config_dir / "overrides").mkdir()
        (self.config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
        (self.config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
        (self.config_dir / "overrides" / f"{TOPIC}.yaml").write_text(OVERRIDES, encoding="utf-8")

    def run(self, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str, dict[str, Any]]:
        code = script.main(
            [
                "--config-dir",
                str(self.config_dir),
                "--data-dir",
                str(self.data_dir),
                "--snapshot",
                "2026-09-30",
                "--caselist",
                CASELIST,
                *extra,
            ]
        )
        out = capsys.readouterr().out
        return code, out, (json.loads(out)["caselists"][CASELIST] if code == 0 else {})


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_every_card_is_counted_once_by_how_the_matcher_placed_it(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, entry = world.run(capsys)
    assert code == 0
    assert (entry["sources"], entry["cards"], entry["sections"]) == (2, 17, 17)
    assert (entry["overrides"], entry["overrides_ruled_none"]) == (2, 1)
    by_method = {
        method: (one["cards"], one["documents"], one["teams"], one["placing_headings"])
        for method, one in entry["cards_by_method"].items()
    }
    assert by_method == {
        "ALIAS": (8, 2, 3, 4),
        "OVERRIDE": (1, 1, 2, 1),
        "INHERITED_FROM_ALIAS": (2, 1, 2, 1),
        "INHERITED_FROM_OVERRIDE": (1, 1, 2, 1),
        "TAG_KEYWORD_UNDER_HEADING": (1, 1, 2, 1),
        "OVERRIDE_NO_POSITION": (1, 1, 2, 0),
        "TAG_KEYWORD_ALONE_UNDER_NO_HEADING": (1, 1, 2, 0),
        "TAG_KEYWORD_ALONE_UNDER_HEADINGS_RULED_NONE": (1, 1, 1, 0),
        "TAG_KEYWORD_ALONE_UNDER_AN_UNDECIDED_HEADING": (1, 1, 1, 0),
    }


def test_alias_rows_are_the_placing_headings_with_the_rare_ones_left_out(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, entry = world.run(capsys)
    rows = entry["rows"]["alias"]
    assert (rows["rows"], rows["distinct_headings"], rows["answer_rows"]) == (4, 3, 1)
    assert rows["listed"] == {
        "rows": 3,
        "cards": 9,
        "documents": 2,
        "teams": 3,
        "cards_direct": 7,
        "cards_inherited": 2,
        "cards_refined_by_tag": 1,
        "cards_tag_names_another_position": 1,
        "rows_with_a_card_whose_tag_names_another_position": 1,
    }
    assert rows["left_out_below_minimum_teams"] == {
        "rows": 1,
        "cards": 2,
        "documents": 1,
        "teams": 1,
        "cards_direct": 2,
        "cards_inherited": 0,
        "cards_refined_by_tag": 0,
        "cards_tag_names_another_position": 0,
        "rows_with_a_card_whose_tag_names_another_position": 0,
    }


def test_override_and_none_rows(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _, _, entry = world.run(capsys)
    override = entry["rows"]["override"]
    assert override["rows"] == 1
    assert override["listed"]["rows"] == 1
    assert (override["listed"]["cards"], override["listed"]["documents"], override["listed"]["teams"]) == (
        2,
        2,
        3,
    )
    assert (override["listed"]["cards_direct"], override["listed"]["cards_inherited"]) == (1, 1)
    none = entry["rows"]["none"]
    assert none["rows"] == 1
    assert (none["listed"]["rows"], none["listed"]["cards"], none["listed"]["documents"]) == (1, 3, 2)
    assert none["listed"]["teams"] == 3


def test_a_none_heading_counts_only_the_cards_no_nearer_heading_places(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    """c2 sits under Solvency with Spending DA above it, so Solvency is the nearest heading a decision
    could place it by; d7 sits under Solvency with Cap K below it, which places it, so it is not
    Solvency's: c2, c5 and d2, not d7."""
    _, _, entry = world.run(capsys)
    assert entry["rows"]["none"]["listed"]["cards"] == 3


def test_what_a_none_decision_on_a_placed_heading_would_do(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, entry = world.run(capsys)
    assert entry["placed_cards_if_their_heading_were_ruled_none"] == {
        "heading_above_other_position": 1,
        "heading_above_same_position": 1,
        "nothing_places_it": 9,
        "tag_keyword_alone": 2,
    }


def test_the_spread_of_the_listed_rows(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _, _, entry = world.run(capsys)
    finding = entry["finding_the_wrong_ones"]
    assert (finding["listed_rows"], finding["listed_cards"]) == (4, 11)
    assert finding["cards_in_the_largest_rows"]["25"] == 11
    assert finding["rows_by_teams"] == {"2-2": 1, "3-5": 3, "6-20": 0, "21+": 0}
    assert finding["rows_with_cards_under_more_than_one_position"] == 1
    assert finding["positions_with_a_row"] == 3
    assert finding["rows_per_position"] == {"max": 2, "median": 1}


def test_the_review_queue_beside_it(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _, _, entry = world.run(capsys)
    assert entry["review_queue_for_comparison"] == {
        "rows": 0,
        "headings": 1,
        "left_out_below_minimum_teams": 1,
        "queued_cards": 3,
        "queued_items_under_no_heading_to_decide": 2,
    }


def test_a_lower_minimum_lists_the_rare_rows(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _, _, entry = world.run(capsys, "--minimum-teams", "1")
    assert entry["rows"]["alias"]["listed"]["rows"] == 4
    assert entry["rows"]["alias"]["left_out_below_minimum_teams"]["rows"] == 0
    assert entry["review_queue_for_comparison"]["rows"] == 1


def test_the_output_holds_counts_only(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = world.run(capsys)
    for word in PLANTED_WORDS:
        assert word.casefold() not in out.casefold()


def test_a_caselist_with_no_topic_is_refused_in_its_entry(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    code = script.main(
        [
            "--config-dir",
            str(world.config_dir),
            "--data-dir",
            str(world.data_dir),
            "--snapshot",
            "2026-09-30",
            "--caselist",
            "hsld99",
        ]
    )
    assert code == 0
    assert "refused" in json.loads(capsys.readouterr().out)["caselists"]["hsld99"]

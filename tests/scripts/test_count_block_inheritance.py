"""`scripts/count_block_inheritance.py` on a planted store (`v1-e32-t65`): the counts the PM rules on.

Two invented sources. Every expected count below was worked out by hand from these cards (working
agreement 6), not printed by the script and copied:

* **one**, disclosed by a negative and an affirmative team, so its roles are the matcher's:

  ====  =============================  =========================  =========================
  card  path                           tag                        the matcher
  ====  =============================  =========================  =========================
  0     Federalism > States CP         (invented claim)           states-cp, ALIAS (counted)
  1     Federalism > Net Benefit       Link: federal spending     unplaced
  2     Federalism > AT: Perm          (invented claim)           unplaced, under an answer
  3     1NC                            (invented claim)           unplaced, under no heading
  4     1NC > Spending DA              (invented claim)           spending-da, ALIAS (counted)
  5     1NC > Cap K                    (invented claim)           cap-k, ALIAS (counted)
  6     Solvency                       (invented claim)           decided: ruled no position
  ====  =============================  =========================  =========================

* **two**, disclosed by a negative team: card 0, under no heading, tagged `Fifty states solve` (states-cp's
  keyword, so placed by its tag alone, under the threshold), and card 1, under no heading, unplaced.

Cards 1 and 2 of **one** inherit States CP from their parent section, `Federalism`; card 3's section, `1NC`,
holds a Spending DA and a Cap K, which disagree; card 1 of **two** shares a run with a keyword-placed card.

Every school, team code, tournament and heading here is invented.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.coach_sample_labels_file import digest_line, digest_path, labels_digest
from debate_core.domain.landscape_classification import card_item_id
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_block_inheritance as script  # noqa: E402

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
"""

OVERRIDES = f"""\
schema_version: 1
topic_id: {TOPIC}
overrides:
  - heading: solvency
    position_id: null
    decided: '2026-10-24'
"""

NEG_ONE = "School One/CodeOne/School One-CodeOne-Neg-Sample Invitational-Round 1.docx"
AFF_TWO = "School Two/CodeTwo/School Two-CodeTwo-Aff-Sample Invitational-Round 1.docx"
NEG_THREE = "School Three/CodeThree/School Three-CodeThree-Neg-Sample Invitational-Round 2.docx"

REFERENCE = "level=nearest,placed=counted,agreement=unanimous,minimum=1,own=any"
WITH_KEYWORDS = "level=nearest,placed=counted+keyword,agreement=unanimous,minimum=1,own=any"


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.data_dir = tmp_path / "data"
        store = PlantedCaselist(self.data_dir, CASELIST)
        self.one = store.source(
            "one",
            [
                PlantedCard(("Federalism", "States CP")),
                PlantedCard(("Federalism", "Net Benefit"), tag="Link: federal spending"),
                PlantedCard(("Federalism", "AT: Perm")),
                PlantedCard(("1NC",)),
                PlantedCard(("1NC", "Spending DA")),
                PlantedCard(("1NC", "Cap K")),
                PlantedCard(("Solvency",)),
            ],
            disclosures=[("2026-09-08", NEG_ONE), ("2026-09-08", AFF_TWO)],
        )
        self.two = store.source(
            "two",
            [PlantedCard((), tag="Fifty states solve"), PlantedCard(())],
            disclosures=[("2026-09-15", NEG_THREE)],
        )
        self.config_dir = tmp_path / "config"
        (self.config_dir / "taxonomies").mkdir(parents=True)
        (self.config_dir / "overrides").mkdir()
        (self.config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
        (self.config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
        (self.config_dir / "overrides" / f"{TOPIC}.yaml").write_text(OVERRIDES, encoding="utf-8")
        self.labels = tmp_path / "labels"
        self.labels.mkdir()

    def card(self, source: str, index: int) -> str:
        """A planted card's item id: its first paragraph is three times its place in the source."""
        return card_item_id(source, index * 3)

    def sample(self, name: str, labels: list[tuple[str, str]], *, holdout: bool) -> tuple[Path, Path]:
        """A labels CSV with its sidecar, and its rows file: `labels` are (item id, label) in row order."""
        csv_path = self.labels / f"{name}.csv"
        csv_path.write_bytes(
            (
                "sample_row,position\n"
                + "".join(f"{row},{label}\n" for row, (_, label) in enumerate(labels, 1))
            ).encode()
        )
        digest_path(csv_path).write_text(
            digest_line(labels_digest(csv_path.read_bytes()), csv_path), encoding="utf-8"
        )
        rows = self.labels / f"{name}.jsonl"
        header: dict[str, Any] = {"holdout": True} if holdout else {"seed": 1}
        rows.write_text(
            json.dumps(header)
            + "\n"
            + "".join(
                json.dumps({"sample_row": row, "item_id": item_id}) + "\n"
                for row, (item_id, _) in enumerate(labels, 1)
            ),
            encoding="utf-8",
        )
        return csv_path, rows

    def first_sample(self) -> tuple[Path, Path]:
        return self.sample(
            "first",
            [
                (self.card(self.one, 1), "states-cp"),
                (self.card(self.one, 2), "at:states-cp"),
                (self.card(self.one, 3), "spending-da"),
                (self.card(self.two, 1), "none"),
                (self.card(self.one, 4), "spending-da"),
            ],
            holdout=False,
        )

    def run(self, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, dict[str, Any]]:
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
                "--labelled-caselist",
                CASELIST,
                *extra,
            ]
        )
        out = capsys.readouterr().out
        return code, (json.loads(out) if code == 0 else {})


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_the_cards_are_read_and_placed_by_the_matcher(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = world.run(capsys)
    assert code == 0
    entry = out["caselists"][CASELIST]
    assert entry["cards"] == 9
    assert entry["cards_by_status"] == {"counted": 3, "decided": 1, "keyword": 1, "unplaced": 4}
    assert entry["left_for_review"] == 5


def test_each_block_says_agree_disagree_or_nothing_placed(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = world.run(capsys)
    shapes = out["caselists"][CASELIST]["block_shapes"]

    def shape(key: str) -> tuple[int, int, int]:
        one = shapes[key]
        return one["agree"], one["disagree"], one["nothing_placed"]

    assert shape("run/counted") == (0, 0, 5)
    assert shape("run/counted+keyword") == (1, 0, 4)
    assert shape("section/counted") == (0, 1, 4)
    assert shape("section/counted+keyword") == (1, 1, 3)
    assert shape("parent/counted") == (2, 1, 2)
    assert shape("parent/counted+keyword") == (2, 1, 2)
    assert shape("nearest/counted") == (2, 1, 2)
    assert shape("nearest/counted+keyword") == (3, 1, 1)
    assert shape("document/counted") == (0, 3, 2)
    assert shape("document/counted+keyword") == (1, 3, 1)
    assert shapes["parent/counted"]["agreeing_block_sizes"] == {"1": 2}


def test_a_disagreeing_block_gives_nothing_and_an_agreeing_one_its_position(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = world.run(capsys)
    rules = out["caselists"][CASELIST]["rules"]
    reference = rules[REFERENCE]["population"]
    assert reference == {
        "inherited": 2,
        "inherited_by_kind": {"cp": 2},
        "of_which_were_keyword_placed": 0,
        "placed_share_before": round(3 / 9, 4),
        "placed_share_after": round(5 / 9, 4),
        "decided_cards_that_would_inherit_if_eligible": 0,
    }
    assert (
        rules["level=document,placed=counted,agreement=unanimous,minimum=1,own=any"]["population"][
            "inherited"
        ]
        == 0
    )
    assert (
        rules["level=nearest,placed=counted,agreement=unanimous,minimum=2,own=any"]["population"]["inherited"]
        == 0
    )
    assert rules[WITH_KEYWORDS]["population"]["inherited"] == 3


def test_answer_headings_and_link_shaped_tags_are_counted(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = world.run(capsys)
    entry = out["caselists"][CASELIST]
    assert entry["answer_headings_under_the_reference_rule"] == {
        "answer_heading_below_and_block_reads": 1,
        "answer_heading_below_the_deciding_section": 1,
        "inherit": 2,
        "inherit_block_reads": 2,
        "inherit_under_an_answer_heading": 1,
        "left_for_review": 5,
        "left_for_review_under_an_answer_heading": 1,
    }
    assert entry["link_shaped_under_the_reference_rule"] == {"cp": {"inherit": 2, "link_shaped": 1}}


def test_the_review_queue_before_and_after(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _, out = world.run(capsys)
    entry = out["caselists"][CASELIST]
    assert entry["review_queue_before"] == {
        "items": 9,
        "cards": 5,
        "headings": 3,
        "rows": 3,
        "under_no_heading": 4,
    }
    after = entry["rules"][REFERENCE]["review_queue_after"]
    assert after["sections_kept"] == {"items": 7, "cards": 3, "headings": 3, "rows": 3, "under_no_heading": 4}
    assert after["sections_placed_leave"] == {
        "items": 4,
        "cards": 3,
        "headings": 0,
        "rows": 0,
        "under_no_heading": 4,
    }


def test_the_first_sample_is_scored_for_each_rule_and_role(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    sample, rows = world.first_sample()
    code, out = world.run(capsys, "--sample", str(sample), "--sample-rows", str(rows))
    assert code == 0
    entry = out["caselists"][CASELIST]
    before = entry["first_sample_before"]
    assert (before["labelled"], before["found"]) == (5, 5)
    assert (before["before"]["counted"], before["before"]["correct"]) == (1, 1)
    scored = entry["rules"][REFERENCE]["first_sample"]
    assert (
        scored["answer-heading"]["inherited"]["counted"],
        scored["answer-heading"]["inherited"]["correct"],
    ) == (2, 2)
    assert (scored["answer-heading"]["after"]["counted"], scored["answer-heading"]["after"]["correct"]) == (
        3,
        3,
    )
    assert scored["answer-heading"]["after"]["coverage"] == 0.6
    assert (scored["block"]["inherited"]["counted"], scored["block"]["inherited"]["correct"]) == (2, 1)
    keyword = entry["rules"][WITH_KEYWORDS]["first_sample"]["answer-heading"]["inherited"]
    assert (keyword["counted"], keyword["correct"]) == (3, 2)
    assert entry["first_sample_under_the_reference_rule"] == {
        "by_kind": {"inherited cp, labelled cp, right": 2},
        "link_shaped": {"inherited cp, labelled cp, right": 1},
        "under_an_answer_heading": {"inherited cp, labelled cp, right, label at": 1},
    }
    assert "holdout" not in entry


def test_the_holdout_is_scored_once_with_the_one_rule_named(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    sample, rows = world.sample("held", [(world.card(world.one, 1), "states-cp")], holdout=True)
    code, out = world.run(
        capsys,
        "--holdout-sample",
        str(sample),
        "--holdout-rows",
        str(rows),
        "--holdout-rule",
        f"{REFERENCE},role=answer-heading",
    )
    assert code == 0
    held = out["caselists"][CASELIST]["holdout"]
    assert held["rule"] == f"{REFERENCE},role=answer-heading"
    assert held["score"]["inherited"]["counted"] == 1
    assert held["score"]["inherited"]["correct"] == 1
    assert held["score"]["before"]["counted"] == 0


def test_the_holdout_is_refused_without_a_rule_and_a_first_sample_marked_holdout_is_refused(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    sample, rows = world.sample("held", [(world.card(world.one, 1), "states-cp")], holdout=True)
    code, _ = world.run(capsys, "--holdout-sample", str(sample), "--holdout-rows", str(rows))
    assert code == 2
    code, _ = world.run(capsys, "--sample", str(sample), "--sample-rows", str(rows))
    assert code == 2
    first, first_rows = world.first_sample()
    code, _ = world.run(
        capsys,
        "--holdout-sample",
        str(first),
        "--holdout-rows",
        str(first_rows),
        "--holdout-rule",
        f"{REFERENCE},role=answer-heading",
    )
    assert code == 2


def test_nothing_printed_holds_a_heading_or_a_tag(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    sample, rows = world.first_sample()
    _, out = world.run(capsys, "--sample", str(sample), "--sample-rows", str(rows))
    text = json.dumps(out).casefold()
    for word in (
        "federalism",
        "net benefit",
        "perm",
        "fifty",
        "federal spending",
        "school",
        "code",
        world.one,
    ):
        assert word not in text


def test_a_caselist_on_no_topic_is_refused_and_the_others_still_counted(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = world.run(capsys, "--caselist", "hsld99")
    assert code == 0
    assert out["caselists"]["hsld99"] == {
        "refused": "topics.yaml puts hsld99 on 2026-09-30 on no topic with a taxonomy"
    }
    assert out["caselists"][CASELIST]["cards"] == 9


def test_naming_nothing_keeps_a_card_under_a_heading_of_its_own_from_inheriting(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    sample, rows = world.first_sample()
    _, out = world.run(capsys, "--sample", str(sample), "--sample-rows", str(rows))
    rules = out["caselists"][CASELIST]["rules"]
    assert rules[REFERENCE.replace("own=any", "own=naming-nothing")]["population"]["inherited"] == 0
    keyword = rules[WITH_KEYWORDS.replace("own=any", "own=naming-nothing")]
    assert keyword["population"]["inherited"] == 1
    assert keyword["first_sample"]["answer-heading"]["outcomes"] == {"labelled_none": 1}


def test_each_inherited_card_of_the_first_sample_has_an_outcome(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    sample, rows = world.first_sample()
    _, out = world.run(capsys, "--sample", str(sample), "--sample-rows", str(rows))
    scored = out["caselists"][CASELIST]["rules"][REFERENCE]["first_sample"]
    assert scored["answer-heading"]["outcomes"] == {"correct": 2}
    assert scored["block"]["outcomes"] == {"correct": 1, "wrong_stance": 1}
    assert out["caselists"][CASELIST]["rules"][WITH_KEYWORDS]["first_sample"]["answer-heading"][
        "outcomes"
    ] == {
        "correct": 2,
        "labelled_none": 1,
    }

"""`scripts/landscape_table_tag_words.py`: the tags the tables quote that hold a caselist word (`v1-e32-t28`).

Over the synthetic caselist (`tests/fixtures/landscape/synthetic_caselist`), unchanged, with `v1-e32-t25`'s
edits (`tests/fixtures/landscape/readable_impact_chains/`) and with `v1-e32-t28`'s
(`tests/fixtures/landscape/tags_in_the_tables/`). Every expected line was written by hand from those
directories' READMEs and the golden files. A tag is counted as parsed, whether the report withheld it or
not; since the PM's ruling (b) of 2026-10-27 the report withholds the school words and team codes, 13 of
the 18 words:

* **The words.** Schools `Ashgrove Fictional`, `Birchmoor`, `Cedarvale Fictional`, `Driftwood Fictional`:
  5 school words. Team codes `XX`, `YY`, `QQ`, `ZZ`, `VV`, `WW`, `JJ`, `KK`: 8. Tournaments `Fictional
  Invitational`, `Imaginary Classic`, `Later Tournament`: 6 words. `fictional` is in two kinds: 18 words.
* **The rows.** golden/impact_cards.csv has 7 rows, golden/top_cards.csv 23, and golden/report.md's
  link-chain tables 9 rows with a card. No tag of the unchanged caselist holds a caselist word.
* **The edits.** The Costs advantage's rank-1 impact card (`a1`, paragraph 6, cluster 2) is tagged
  `2. Extinction from a Cedarvale collapse`, so the impact table and that position's chain Impact row each
  have one tag holding `cedarvale`, a school word, withheld. top_cards.csv shows the tag most of
  cluster 2's cards carry, which is not the edited one. `a3`'s paragraph 15, cluster 37's only card, loses its tag, so an
  impact row and a top_cards.csv row have none.
* **t28's edits** add `later` to the Costs advantage's rank-2 impact tag (`a4`, paragraph 3) and
  `classic` to the Spending DA's uniqueness tag (`b5`, paragraph 6), tournament words, both shown; and
  `birchmoor` and `VV` to two top_cards.csv rows (`nhi-t` rank 2, `condo-bad` rank 1), both withheld.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest
import yaml

from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.arguments.landscape.link_chains import caselist_words
from debate_core.domain.landscape import Taxonomy
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import landscape_table_tag_words as script  # noqa: E402

LANDSCAPE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "landscape"
FIXTURE = LANDSCAPE / "synthetic_caselist"
EDITS = LANDSCAPE / "readable_impact_chains" / "edits.yaml"
T28_EDITS = LANDSCAPE / "tags_in_the_tables" / "edits.yaml"
HEADER = [
    "Tags the tables quote that hold a caselist word: synthpolicy26 through 2026-09-15, taxonomy 1.2.0.",
    "Caselist words: 18; school word 5, team-code shape 8, tournament word 6; in two kinds or more 1; "
    "withheld, the school words and team codes: 13.",
]
HOLDING = "holding a word of a caselist school, team code or tournament"
IMPACT = "Impact table (report.md's Tag column, impact_cards.csv's tag)"


def _with_edits(
    tags: dict[tuple[str, int], str | None] | None = None, *, edits_file: Path = EDITS
) -> LandscapeReportInputs:
    """The synthetic caselist with `edits_file`'s edits (t25's), then `tags`' tags, by file and paragraph."""
    inputs = read_synthetic_caselist(FIXTURE)
    edits = yaml.safe_load(edits_file.read_text(encoding="utf-8"))
    changed = {(one["file"], one["element_index"]): one["tag"] for one in edits["cards"]}
    changed.update(tags or {})
    cards = tuple(
        card.model_copy(update={"tag": changed[(card.source_sha256[:2], card.element_index)]})
        if (card.source_sha256[:2], card.element_index) in changed
        else card
        for card in inputs.cards
    )
    document = inputs.taxonomy.model_dump()
    lists = edits["scenario_lists"]
    document["positions"] = [{**one, **lists.get(one["id"], {})} for one in document["positions"]]
    return dataclasses.replace(inputs, cards=cards, taxonomy=Taxonomy.model_validate(document))


def _lines(inputs: LandscapeReportInputs, *, show_words: bool = False) -> list[str]:
    report = LandscapeReportService().build(inputs, synthetic_staleness())
    return script.report_lines(report, inputs.disclosures, inputs.cards, show_words=show_words)


def test_the_words_by_kind_and_the_withheld_ones_are_the_school_words_and_team_codes() -> None:
    disclosures = read_synthetic_caselist(FIXTURE).disclosures
    kinds = script.words_by_kind(disclosures)
    assert kinds == {
        "school word": frozenset({"ashgrove", "fictional", "birchmoor", "cedarvale", "driftwood"}),
        "team-code shape": frozenset({"xx", "yy", "qq", "zz", "vv", "ww", "jj", "kk"}),
        "tournament word": frozenset(
            {"fictional", "invitational", "imaginary", "classic", "later", "tournament"}
        ),
    }
    assert kinds["school word"] | kinds["team-code shape"] == caselist_words(disclosures)


def test_the_unchanged_caselist_quotes_no_tag_holding_a_caselist_word() -> None:
    assert _lines(read_synthetic_caselist(FIXTURE)) == [
        *HEADER,
        f"{IMPACT}: 7 rows, 7 with a tag, 0 {HOLDING} (0.0%), 0 of them withheld (0.0%); by kind of word: "
        "school word 0, team-code shape 0, tournament word 0; the most-matched word is in 0.",
        f"Link-chain table: 9 rows, 9 with a tag, 0 {HOLDING} (0.0%), 0 of them withheld (0.0%); by kind of "
        "word: school word 0, team-code shape 0, tournament word 0; the most-matched word is in 0.",
        f"top_cards.csv: 23 rows, 23 with a tag, 0 {HOLDING} (0.0%), 0 of them withheld (0.0%); by kind of "
        "word: school word 0, team-code shape 0, tournament word 0; the most-matched word is in 0.",
    ]


def test_the_edited_tag_is_counted_in_the_impact_and_link_chain_tables_and_no_word_is_printed() -> None:
    lines = _lines(_with_edits())
    assert lines == [
        *HEADER,
        f"{IMPACT}: 7 rows, 6 with a tag, 1 {HOLDING} (16.7%), 1 of them withheld (16.7%); by kind of word: "
        "school word 1, team-code shape 0, tournament word 0; the most-matched word is in 1.",
        f"Link-chain table: 9 rows, 9 with a tag, 1 {HOLDING} (11.1%), 1 of them withheld (11.1%); by kind of "
        "word: school word 1, team-code shape 0, tournament word 0; the most-matched word is in 1.",
        f"top_cards.csv: 23 rows, 22 with a tag, 0 {HOLDING} (0.0%), 0 of them withheld (0.0%); by kind of "
        "word: school word 0, team-code shape 0, tournament word 0; the most-matched word is in 0.",
    ]
    assert not any("edarvale" in line or "Extinction" in line for line in lines)


def test_a_tournament_word_is_counted_and_not_withheld() -> None:
    lines = _lines(_with_edits(edits_file=T28_EDITS))
    assert lines[2:] == [
        f"{IMPACT}: 7 rows, 6 with a tag, 2 {HOLDING} (33.3%), 1 of them withheld (16.7%); by kind of word: "
        "school word 1, team-code shape 0, tournament word 1; the most-matched word is in 1.",
        f"Link-chain table: 9 rows, 9 with a tag, 2 {HOLDING} (22.2%), 1 of them withheld (11.1%); by kind of "
        "word: school word 1, team-code shape 0, tournament word 1; the most-matched word is in 1.",
        f"top_cards.csv: 23 rows, 22 with a tag, 4 {HOLDING} (18.2%), 2 of them withheld (9.1%); by kind of "
        "word: school word 1, team-code shape 1, tournament word 2; the most-matched word is in 1.",
    ]


def test_a_tag_holding_two_kinds_counts_under_both() -> None:
    """`b5`'s paragraph 6, cluster 40's only card, is the Spending DA's Uniqueness row, by its `u` heading."""
    lines = _lines(_with_edits({("b5", 6): "XX says Fictional spending is at a record high"}))
    assert lines[3] == (
        f"Link-chain table: 9 rows, 9 with a tag, 2 {HOLDING} (22.2%), 2 of them withheld (22.2%); by kind of "
        "word: school word 2, team-code shape 1, tournament word 1; the most-matched word is in 1."
    )


def test_the_words_are_shown_only_when_asked_with_a_warning() -> None:
    assert _lines(_with_edits(), show_words=True) == [
        *HEADER,
        "The words below are for this screen only: never paste them into a report, a log or a commit.",
        f"{IMPACT}: 7 rows, 6 with a tag, 1 {HOLDING} (16.7%), 1 of them withheld (16.7%); by kind of word: "
        "school word 1, team-code shape 0, tournament word 0; the most-matched word is in 1.",
        "  cedarvale (school word): 1",
        f"Link-chain table: 9 rows, 9 with a tag, 1 {HOLDING} (11.1%), 1 of them withheld (11.1%); by kind of "
        "word: school word 1, team-code shape 0, tournament word 0; the most-matched word is in 1.",
        "  cedarvale (school word): 1",
        f"top_cards.csv: 23 rows, 22 with a tag, 0 {HOLDING} (0.0%), 0 of them withheld (0.0%); by kind of "
        "word: school word 0, team-code shape 0, tournament word 0; the most-matched word is in 0.",
    ]


def test_a_report_withholding_other_tags_than_the_rule_is_refused() -> None:
    inputs = _with_edits()
    report = LandscapeReportService().build(inputs, synthetic_staleness())
    first = report.top_cards[0]
    tampered = report.model_copy(update={"top_cards": (first.model_copy(update={"tag": None}), *report.top_cards[1:])})
    with pytest.raises(ValueError, match="withheld"):
        script.report_lines(tampered, inputs.disclosures, inputs.cards)

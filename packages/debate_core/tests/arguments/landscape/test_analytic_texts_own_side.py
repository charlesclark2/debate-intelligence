"""An analytic text under an answer heading in its own side's file reads its position (`v1-e32-t56`).

`v1-e32-t49`'s own-side rule, :func:`~debate_core.arguments.landscape.side_role.side_role`, applied to the
analytic texts as their readings meet their file's sides (the PM's ruling of 2026-11-07): an overview, a CP
text and an alternative placed under an answer heading in a file disclosed only on their position's own
side read it; in a file on the other side, or on both, they keep the role the matcher gave them.

Every taxonomy, heading and text here is invented, and every expected value is written by hand.
"""

from __future__ import annotations

from typing import Any

import pytest

from debate_core.arguments.landscape.analytic_texts import (
    AnalyticTextRules,
    CounterplanActors,
    SectionParagraph,
    SourceParagraphs,
    read_analytic_texts,
    readings_on_own_side,
)
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, PositionRole
from debate_core.domain.landscape_texts import AnalyticTextKind, AnalyticTextReading
from debate_core.domain.style_profile import StructuralUnit

ANSWERS, READS = PositionRole.ANSWERS, PositionRole.READS
CP = AnalyticTextKind.CP_TEXT
ALT = AnalyticTextKind.K_ALTERNATIVE
OVERVIEW = AnalyticTextKind.OVERVIEW


def _position(identifier: str, kind: str, side: str, aliases: list[str]) -> dict[str, Any]:
    label = identifier.replace("-", " ").capitalize()
    return {"id": identifier, "label": label, "kind": kind, "side": side, "aliases": aliases}


TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            _position("sample-aff", "aff", "aff", ["sample aff"]),
            _position("states-cp", "cp", "neg", ["states cp"]),
            _position("cap-k", "k", "neg", ["cap k"]),
            _position("midterms-da", "da", "neg", ["midterms da"]),
        ],
    }
)
RULES = AnalyticTextRules(
    TAXONOMY,
    OverrideRules(topic_id="sample-topic"),
    CounterplanActors(topic_id="sample-topic", cp_text_actors=("fifty states", "congress")),
)


def p(index: int, unit: StructuralUnit, text: str, *path: str) -> SectionParagraph:
    return SectionParagraph(element_index=index, unit=unit, text=text, section_path=tuple(path))


def answered() -> tuple[AnalyticTextReading, ...]:
    """An overview, a CP text and an alternative, each under an answer heading naming a negative position."""
    readings = read_analytic_texts(
        SourceParagraphs(
            paragraphs=(
                p(0, StructuralUnit.HAT, "AT: Midterms DA"),
                p(1, StructuralUnit.ANALYTIC, "Overview", "AT: Midterms DA"),
                p(2, StructuralUnit.HAT, "AT: States CP"),
                p(3, StructuralUnit.ANALYTIC, "Text: Congress should fund a sample clinic.", "AT: States CP"),
                p(4, StructuralUnit.HAT, "AT: Cap K"),
                p(5, StructuralUnit.TAG, "The alternative is to reject sample markets.", "AT: Cap K"),
            )
        ),
        RULES,
    ).readings
    # The matcher's roles, before any side: each is placed under its position, answering it.
    assert [(one.kind, one.position_id, one.role) for one in readings] == [
        (OVERVIEW, "midterms-da", ANSWERS),
        (CP, "states-cp", ANSWERS),
        (ALT, "cap-k", ANSWERS),
    ]
    return readings


def _roles(readings: tuple[AnalyticTextReading, ...]) -> list[tuple[AnalyticTextKind, PositionRole | None]]:
    return [(one.kind, one.role) for one in readings]


@pytest.mark.parametrize("own_side", [["NEG"], ["CON"], ["NEG", "NEG"], ["NEG", "UNKNOWN"]])
def test_analytic_texts_under_an_answer_heading_in_their_own_sides_file_read_it(own_side: list[str]) -> None:
    assert _roles(readings_on_own_side(TAXONOMY, answered(), own_side)) == [
        (OVERVIEW, READS),
        (CP, READS),
        (ALT, READS),
    ]


@pytest.mark.parametrize(
    "file_sides",
    [
        pytest.param(["AFF"], id="the other side"),
        pytest.param(["PRO"], id="the other side, pro"),
        pytest.param(["AFF", "NEG"], id="both sides"),
        pytest.param(["UNKNOWN"], id="no readable side"),
        pytest.param([], id="no disclosure"),
    ],
)
def test_analytic_texts_in_a_file_on_the_other_side_or_both_keep_their_role(file_sides: list[str]) -> None:
    assert _roles(readings_on_own_side(TAXONOMY, answered(), file_sides)) == [
        (OVERVIEW, ANSWERS),
        (CP, ANSWERS),
        (ALT, ANSWERS),
    ]


def test_an_affirmative_analytic_text_in_an_affirmative_file_reads_its_advantage() -> None:
    readings = read_analytic_texts(
        SourceParagraphs(
            paragraphs=(
                p(0, StructuralUnit.HAT, "AT: Sample Aff"),
                p(1, StructuralUnit.ANALYTIC, "Overview", "AT: Sample Aff"),
            )
        ),
        RULES,
    ).readings
    assert [(one.position_id, one.role) for one in readings] == [("sample-aff", ANSWERS)]
    assert _roles(readings_on_own_side(TAXONOMY, readings, ["AFF"])) == [(OVERVIEW, READS)]
    assert _roles(readings_on_own_side(TAXONOMY, readings, ["NEG"])) == [(OVERVIEW, ANSWERS)]


def test_only_the_role_changes_and_unplaced_texts_are_left_as_they_are() -> None:
    placed = answered()
    unplaced = read_analytic_texts(
        SourceParagraphs(
            paragraphs=(
                p(7, StructuralUnit.HAT, "OFF"),
                p(8, StructuralUnit.TAG, "The alternative is sample refusal.", "OFF"),
            )
        ),
        RULES,
    ).readings
    assert [(one.position_id, one.role) for one in unplaced] == [(None, None)]
    found = readings_on_own_side(TAXONOMY, (*placed, *unplaced), ["NEG"])
    assert [one.model_copy(update={"role": ANSWERS}) for one in found[:3]] == list(placed)
    assert found[3:] == unplaced

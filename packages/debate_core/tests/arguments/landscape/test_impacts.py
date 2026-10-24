"""The impact rule (`v1-e32-t10`): which headings and tag openings label a card as an impact.

Every expectation is the PM's ruling of 2026-10-24, written here by hand: the heading words, their
three exclusions, and the fifteen tag openings after one leading enumerator. A heading reaches the
rule normalized, so some cases go through t01's normalizer to show what a real heading becomes.
"""

from __future__ import annotations

import pytest

from debate_core.arguments.landscape.headings import normalize_heading
from debate_core.arguments.landscape.impacts import (
    IMPACT_TAG_OPENINGS,
    is_impact_card,
    is_impact_heading,
    tag_opens_with_impact,
)


@pytest.mark.parametrize(
    "heading",
    [
        "impact",
        "impacts",
        "spending da impact",
        "impact overview",
        "dome impact",
        "turns case",
        "da turns case",
    ],
)
def test_an_impact_or_turns_case_heading_labels_an_impact(heading: str) -> None:
    assert is_impact_heading(heading)


@pytest.mark.parametrize(
    "heading",
    [
        "no impact",
        "impact defense",
        "impact turn",
        "impact turns",
        "spending da no impact",
        "midterms da impact turns",
    ],
)
def test_no_impact_impact_defense_and_impact_turns_label_nothing(heading: str) -> None:
    assert not is_impact_heading(heading)


@pytest.mark.parametrize(
    "heading",
    [
        "impactful",
        "impacted",
        "i l",
        "il",
        "internal link",
        "t c",
        "tc",
        "turns",
        "case turns",
        "turns the case",
        "magnitude",
        "extinction",
        "overview",
        "",
    ],
)
def test_other_headings_label_nothing(heading: str) -> None:
    assert not is_impact_heading(heading)


@pytest.mark.parametrize(
    ("raw", "labels"),
    [
        ("2NC — Impact Overview", True),
        ("I/L and Impact", True),
        ("Impacts---1NC", True),
        ("Turns Case", True),
        ("A2: No Impact", False),
        ("Impact Defense", False),
        ("T/C", False),
        ("I/L", False),
    ],
)
def test_real_headings_once_normalized(raw: str, labels: bool) -> None:
    assert is_impact_heading(normalize_heading(raw).text) is labels


@pytest.mark.parametrize(
    "tag",
    [
        "Extinction",
        "Extinction-level risk is high",
        "Existential pandemics are coming",
        "The impact is extinction",
        "Our impact outweighs",
        "Impact: nuclear war",
        "Impacts — two scenarios",
        "Nuclear war causes extinction",
        "Nuke war",
        "Goes nuclear fast",
        "Escalation is quick",
        "Turns case – the economy collapses",
        "Outweighs on probability",
        "Magnitude: billions die",
        "Timeframe comes first",
        "Probability is high now",
    ],
)
def test_a_tag_opening_with_an_impact_word_labels_an_impact(tag: str) -> None:
    assert tag_opens_with_impact(tag)


@pytest.mark.parametrize(
    "tag",
    [
        "2. Extinction from economic collapse",
        "1) Nuclear war",
        "12 — the impact is extinction",
        "B) Timeframe: the DA comes first",
        "c. Turns case",
        "Third, magnitude",
        "First — extinction",
    ],
)
def test_one_leading_enumerator_is_skipped(tag: str) -> None:
    assert tag_opens_with_impact(tag)


@pytest.mark.parametrize(
    "tag",
    [
        "1 2 extinction",
        "123 extinction",
        "i. Extinction",
        "Sixth, extinction",
        "Independently, extinction",
        "No impact to the economy",
        "Nuclear deterrence holds",
        "War is likely",
        "Otherwise extinction",
        "Extinctions are accelerating",
        "Impactful reforms pass",
        "The economy causes extinction",
        "Prior to extinction",
        "",
        None,
    ],
)
def test_other_tags_label_nothing(tag: str | None) -> None:
    assert not tag_opens_with_impact(tag)


def test_the_tag_openings_are_the_rulings_fifteen() -> None:
    assert IMPACT_TAG_OPENINGS == (
        "impact",
        "impacts",
        "the impact",
        "our impact",
        "extinction",
        "existential",
        "nuclear war",
        "nuke war",
        "goes nuclear",
        "escalation",
        "turns case",
        "outweighs",
        "magnitude",
        "timeframe",
        "probability",
    )


def test_a_card_is_an_impact_card_by_either_signal() -> None:
    assert is_impact_card(("spending da", "impact"), "Debt spirals")
    assert is_impact_card(("spending da", "link"), "2. Extinction")
    assert is_impact_card(("midterms da", "no impact"), "Extinction outweighs")
    assert not is_impact_card(("midterms da", "no impact"), "Polls are wrong")
    assert not is_impact_card((), None)


def test_any_heading_on_the_path_labels_it_not_only_the_innermost() -> None:
    assert is_impact_card(("impacts", "spending da", "uniqueness"), "Spending is high now")


def test_a_one_letter_word_is_read_as_an_enumerator_as_the_counts_were() -> None:
    """`a` to `h` alone are enumerators, so the article in "A nuclear war" is skipped too.

    The ruling was made on counts taken this way; an article before an impact word labels an impact
    anyway.
    """
    assert tag_opens_with_impact("A nuclear war ends everything")
    assert not tag_opens_with_impact("A strong economy prevents war")

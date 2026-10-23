"""The heading normalizer (`v1-e32-t01-position-taxonomy` ac4, node heading-normalizer).

Two teams reading the same DA write its pocket, hat or block heading differently: `1NC — Spending
DA Shell`, `2. spending DA`, `AT: Spending DA`. The normalizer reduces each to the form a taxonomy
alias is written in (`spending da`) and says whether the heading answers the position rather than
reading it. Each rule it strips by has a case of its own below, written before the rule was.

Every heading here is invented. The opponents, tournaments and rounds are placeholders shaped like
the real thing (`Sample Squad`, `Harbor Classic R3`), never a real team, school or person.
"""

from __future__ import annotations

import pytest

from debate_core.arguments.landscape.headings import NormalizedHeading, normalize_heading
from debate_core.domain.landscape import ALIAS_PATTERN

READ = False
ANSWER = True

CASES: list[tuple[str, str, str, bool]] = [
    # rule, raw heading, normalized text, answer marker
    ("case-fold", "Spending DA", "spending da", READ),
    ("whitespace", "  Spending \t  DA  ", "spending da", READ),
    ("hyphens inside a name", "Medicare-for-All Aff", "medicare for all aff", READ),
    ("punctuation", "Spending DA.", "spending da", READ),
    ("ampersand", "Courts & Congress CP", "courts and congress cp", READ),
    ("apostrophes", "The People’s Plan", "the peoples plan", READ),
    ("unicode compatibility forms", "Ｓｐｅｎｄｉｎｇ DA", "spending da", READ),
    ("numbering with a period", "1. Spending DA", "spending da", READ),
    ("numbering with a bracket", "2) Courts CP", "courts cp", READ),
    ("roman numbering", "IV. Cap K", "cap k", READ),
    ("letter numbering", "b) Spending DA", "spending da", READ),
    ("hash numbering", "#3 Spending DA", "spending da", READ),
    ("a number on its own segment", "3 - Spending DA", "spending da", READ),
    ("round prefix", "1NC Spending DA", "spending da", READ),
    ("round prefix with a dash", "1NC — Spending DA", "spending da", READ),
    ("round prefix with a colon", "2NR: Courts CP", "courts cp", READ),
    ("two round prefixes", "2AC/1AR Spending DA", "spending da", READ),
    ("a round name and nothing else", "1AC", "", READ),
    ("round suffix", "Single Payer 1AC", "single payer", READ),
    ("round suffix on its own segment", "Spending DA - 2NC", "spending da", READ),
    ("AT with a colon", "AT: Spending DA", "spending da", ANSWER),
    ("AT in capitals without a colon", "AT Spending DA", "spending da", ANSWER),
    ("at in lowercase with a colon", "at: spending da", "spending da", ANSWER),
    ("A2", "A2 Spending DA", "spending da", ANSWER),
    ("A2 with a colon", "A2: Courts CP", "courts cp", ANSWER),
    ("A/T", "A/T Courts CP", "courts cp", ANSWER),
    ("answers to", "Answers to Spending DA", "spending da", ANSWER),
    ("a round prefix before the answer marker", "2AC AT: Spending DA", "spending da", ANSWER),
    ("an answer marker after a round segment", "2AC - A2: Spending DA", "spending da", ANSWER),
    ("shell suffix", "Spending DA Shell", "spending da", READ),
    ("round shell suffix", "Spending DA - 1NC Shell", "spending da", READ),
    ("block suffix", "Courts CP Block", "courts cp", READ),
    ("blocks suffix", "Spending DA Blocks", "spending da", READ),
    ("frontlines suffix", "Single-Payer 2AC Frontlines", "single payer", READ),
    ("extensions suffix", "Spending DA - 2NC Extensions", "spending da", READ),
    ("off suffix", "Spending DA Off", "spending da", READ),
    ("off on its own", "Off", "", READ),
    ("a count of off-case positions", "7 Off", "", READ),
    ("a side label on its own", "Neg", "", READ),
    ("a side label segment", "Neg - Spending DA", "spending da", READ),
    ("the affirmative on its own", "Affirmative", "", READ),
    ("on case", "On Case", "", READ),
    ("vs opponent", "Spending DA vs Sample Squad", "spending da", READ),
    ("vs. opponent", "Spending DA vs. Sample Squad", "spending da", READ),
    ("v. opponent", "Courts CP v. Sample Squad", "courts cp", READ),
    ("a round label after the heading", "Spending DA R2", "spending da", READ),
    ("a tournament and round segment", "Spending DA - Harbor Classic R3", "spending da", READ),
    ("a tournament and elimination round", "Spending DA – Lakeside Invitational Octas", "spending da", READ),
    ("a round in brackets", "Spending DA (Round 4)", "spending da", READ),
    ("a round and opponent segment", "Courts CP | Octas v. Sample Squad", "courts cp", READ),
    ("a tournament on its own", "Harbor Classic Round 3", "", READ),
    ("a tournament segment with no round", "Spending DA - Lakeside Invitational", "spending da", READ),
]

KEPT: list[tuple[str, str, str]] = [
    # guard, raw heading, normalized text: words a strip rule must leave alone
    ("an at that is an English word", "At the Margin DA", "at the margin da"),
    ("a v with no period", "Brown v Board CP", "brown v board cp"),
    ("a K and a T keep their letters", "T. Health Insurance", "t health insurance"),
    ("a bracket that is not a label", "Spending DA (Econ)", "spending da econ"),
    ("a segment that is not a label", "Spending DA - Hospitals Link", "spending da hospitals link"),
    ("an acronym beginning with a round's letters", "ACA Expansion Aff", "aca expansion aff"),
    ("an offset is not off", "Offsets CP", "offsets cp"),
]


@pytest.mark.parametrize(("rule", "raw", "text", "answer"), CASES, ids=[case[0] for case in CASES])
def test_each_rule(rule: str, raw: str, text: str, answer: bool) -> None:
    assert normalize_heading(raw) == NormalizedHeading(text=text, answer=answer), rule


@pytest.mark.parametrize(("guard", "raw", "text"), KEPT, ids=[case[0] for case in KEPT])
def test_words_no_rule_strips(guard: str, raw: str, text: str) -> None:
    assert normalize_heading(raw) == NormalizedHeading(text=text, answer=False), guard


@pytest.mark.parametrize("raw", [raw for _, raw, _, _ in CASES] + [raw for _, raw, _ in KEPT])
def test_a_normalized_heading_is_a_fixed_point_and_reads_as_an_alias(raw: str) -> None:
    normalized = normalize_heading(raw)
    assert normalize_heading(normalized.text).text == normalized.text
    if normalized.text:
        assert ALIAS_PATTERN.match(normalized.text)


def test_an_empty_heading_is_empty() -> None:
    assert normalize_heading("   ") == NormalizedHeading(text="", answer=False)
    assert normalize_heading("   ").is_empty

"""The query parser's prefixes and passages, and the limits on both (`v1-e39-t13`).

The PM's rulings of 2026-10-23, enforced in the parser and nowhere else:

* a prefix term (`grow*`) needs at least :data:`MIN_PREFIX_CHARACTERS`, 3, before its `*`; a shorter
  one refuses the whole query, which the search page says;
* a passage keeps at most :data:`MAX_PASSAGE_WORDS`, 40, content words, and says it dropped the rest;
* the stop words a passage leaves out are one constant, :data:`PASSAGE_STOP_WORDS`.

Every expected value is written by hand from the input beside it (working agreement 6). That every
expression parses in a real FTS5 index is checked in
`tests/integrations/local/test_search_index_reader_sqlite_features.py`.
"""

from __future__ import annotations

import re
import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from debate_core.domain.evidence_search import (
    DEFAULT_PASSAGE_SHARE_PERCENT,
    MAX_PASSAGE_WORDS,
    MAX_QUERY_CHARACTERS,
    MIN_PREFIX_CHARACTERS,
    PASSAGE_STOP_WORDS,
    ParsedQuery,
    QueryTerm,
    SearchField,
    SearchFilters,
    parse_passage,
    parse_query,
    passage_minimum,
    search_binding,
)

TAG = SearchField.TAG


# ------------------------------------------------------------------------------------------------
# Prefixes
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "terms"),
    [
        ("grow*", [QueryTerm("grow", prefix=True)]),
        ("escal* war", [QueryTerm("escal", prefix=True), QueryTerm("war")]),
        ("tag:grow*", [QueryTerm("grow", field=TAG, prefix=True)]),
        ("-grow* war", [QueryTerm("grow", excluded=True, prefix=True), QueryTerm("war")]),
        ("grow**", [QueryTerm("grow", prefix=True)]),
        ("a-bcd*", [QueryTerm("a-bcd", prefix=True)]),
        ('"grow*"', [QueryTerm("grow*", phrase=True)]),
        ("grow*th", [QueryTerm("grow*th")]),
        ("*grow", [QueryTerm("*grow")]),
        ("*** grow", [QueryTerm("grow")]),
    ],
)
def test_search_query_reads_a_trailing_star_as_a_prefix_and_nothing_else(
    raw: str, terms: list[QueryTerm]
) -> None:
    assert parse_query(raw) == ParsedQuery(tuple(terms))


@pytest.mark.parametrize(
    ("raw", "expression"),
    [
        ("grow*", '"grow" *'),
        ("escal* war", '"escal" * AND "war"'),
        ("tag:grow*", 'tag : "grow" *'),
        ("-grow* war", '("war") NOT "grow" *'),
        ("a-bcd*", '"a-bcd" *'),
        ("x1y*", '"x1y" *'),
        ('"grow*"', '"grow*"'),
    ],
)
def test_search_query_prefix_is_an_fts5_prefix_phrase(raw: str, expression: str) -> None:
    assert parse_query(raw).fts5_expression() == expression


def test_search_query_prefix_needs_three_characters_before_its_star() -> None:
    assert MIN_PREFIX_CHARACTERS == 3
    assert not parse_query("gro*").prefix_too_short


@pytest.mark.parametrize("raw", ["gr*", "g*", "war gr*", "-gr* war", "tag:gr*", "a-bc*", "ab**"])
def test_search_query_with_a_shorter_prefix_is_refused_whole(raw: str) -> None:
    """A two-letter prefix would read most of the index's terms: the query is refused, not searched."""
    parsed = parse_query(raw)
    assert parsed.prefix_too_short
    assert parsed.fts5_expression() is None


def test_search_query_prefix_counts_the_characters_of_the_last_word_only() -> None:
    """`a-bc*` is the phrase `a bc*` to the tokenizer: its prefix is `bc`, two characters."""
    assert parse_query("abc-de*").prefix_too_short
    assert not parse_query("ab-cde*").prefix_too_short


def test_search_binding_tells_a_prefix_from_the_same_word() -> None:
    filters = SearchFilters()
    assert search_binding("0123456789abcdef", parse_query("grow*"), filters) != search_binding(
        "0123456789abcdef", parse_query("grow"), filters
    )


# ------------------------------------------------------------------------------------------------
# Passages
# ------------------------------------------------------------------------------------------------


def test_search_passage_keeps_its_content_words_in_order_once_each() -> None:
    parsed = parse_passage("Warming causes the economic collapse of the region, and warming spreads")
    assert parsed.passage
    assert [term.text for term in parsed.terms] == [
        "Warming",
        "causes",
        "economic",
        "collapse",
        "region",
        "spreads",
    ]
    assert all(not (term.phrase or term.excluded or term.prefix or term.field) for term in parsed.terms)
    assert parsed.minimum_shared == 4, "two thirds of 6, rounded up"


def test_search_passage_reads_every_operator_as_punctuation() -> None:
    parsed = parse_passage('NOT "nuclear deterrence" -escalation author:Okonkwo grow* NEAR(war)')
    assert [term.text for term in parsed.terms] == [
        "nuclear",
        "deterrence",
        "escalation",
        "author",
        "Okonkwo",
        "grow",
        "NEAR",
        "war",
    ]
    assert parsed.fts5_expression() == (
        '"nuclear" OR "deterrence" OR "escalation" OR "author" OR "Okonkwo" OR "grow" OR "NEAR" OR "war"'
    )
    assert parsed.passage_words() == (
        '"nuclear"',
        '"deterrence"',
        '"escalation"',
        '"author"',
        '"Okonkwo"',
        '"grow"',
        '"NEAR"',
        '"war"',
    )


def test_search_passage_leaves_out_one_character_words_and_contraction_pieces() -> None:
    parsed = parse_passage("The U.S. economy's growth doesn't stop at 2 percent")
    assert [term.text for term in parsed.terms] == ["economy", "growth", "stop", "percent"]


def test_search_passage_keeps_forty_content_words_and_says_it_dropped_the_rest() -> None:
    assert MAX_PASSAGE_WORDS == 40
    parsed = parse_passage(" ".join(f"word{number} the" for number in range(45)))
    assert len(parsed.terms) == 40
    assert parsed.terms[-1] == QueryTerm("word39")
    assert parsed.shortened
    assert parsed.minimum_shared == 27
    exactly = parse_passage(" ".join(f"word{number} of" for number in range(40)))
    assert len(exactly.terms) == 40
    assert not exactly.shortened


def test_search_passage_counts_repeats_and_stop_words_toward_no_limit() -> None:
    """Forty-one content words among repeats and stop words, inside 512 characters: one is dropped."""
    words = [f"w{number}" for number in range(41)]
    raw = " the ".join(words + words[:10])
    assert len(raw) <= MAX_QUERY_CHARACTERS
    parsed = parse_passage(raw)
    assert len(parsed.terms) == 40
    assert parsed.terms[-1] == QueryTerm("w39")
    assert parsed.shortened
    assert not parse_passage(" the ".join(words[:40] + words[:10])).shortened


def test_search_passage_reads_five_hundred_twelve_characters_and_says_it_dropped_the_rest() -> None:
    parsed = parse_passage("growth " * 100)
    assert parsed.terms == (QueryTerm("growth"),)
    assert parsed.shortened
    assert not parse_passage("x" * MAX_QUERY_CHARACTERS).shortened


@pytest.mark.parametrize("raw", ["", "the and of to", "It is what it is.", "a b c d", "- * ^ ()"])
def test_search_passage_of_no_content_word_has_nothing_to_search(raw: str) -> None:
    parsed = parse_passage(raw)
    assert parsed.terms == ()
    assert parsed.fts5_expression() is None
    assert parsed.minimum_shared == 0


@pytest.mark.parametrize(
    ("words", "share", "minimum"),
    [
        (1, 66, 1),
        (2, 66, 2),
        (3, 66, 2),
        (4, 66, 3),
        (6, 66, 4),
        (9, 66, 6),
        (40, 66, 27),
        (5, 50, 3),
        (40, 100, 40),
        (40, 1, 1),
        (0, 66, 0),
    ],
)
def test_search_passage_minimum_is_the_share_of_its_words_rounded_up(
    words: int, share: int, minimum: int
) -> None:
    assert passage_minimum(words, share) == minimum


def test_search_passage_share_is_about_two_thirds_by_default() -> None:
    assert DEFAULT_PASSAGE_SHARE_PERCENT == 66
    assert parse_passage("alpha bravo charlie").minimum_shared == 2
    assert parse_passage("alpha bravo charlie", share_percent=100).minimum_shared == 3


@pytest.mark.parametrize("share", [0, 101, -5])
def test_search_passage_share_is_a_percent_from_one_to_a_hundred(share: int) -> None:
    with pytest.raises(ValueError, match="1 to 100"):
        passage_minimum(3, share)


def test_search_binding_tells_a_passage_from_the_same_words_and_one_share_from_another() -> None:
    filters = SearchFilters()
    plain = search_binding("0123456789abcdef", parse_query("alpha bravo charlie"), filters)
    passage = search_binding("0123456789abcdef", parse_passage("alpha bravo charlie"), filters)
    stricter = search_binding(
        "0123456789abcdef", parse_passage("alpha bravo charlie", share_percent=100), filters
    )
    assert len({plain, passage, stricter}) == 3


# ------------------------------------------------------------------------------------------------
# The stop words
# ------------------------------------------------------------------------------------------------


def test_search_passage_stop_words_are_one_constant_of_lowercase_words() -> None:
    assert isinstance(PASSAGE_STOP_WORDS, frozenset)
    assert all(re.fullmatch(r"[a-z]{2,}", word) for word in PASSAGE_STOP_WORDS)
    assert {
        "the",
        "and",
        "of",
        "to",
        "is",
        "that",
        "because",
        "which",
        "would",
        "doesn",
    } <= PASSAGE_STOP_WORDS


def test_search_passage_stop_words_leave_a_debaters_words_alone() -> None:
    kept = {"nuclear", "war", "growth", "warming", "won", "risk", "causes", "extinction", "solvency"}
    assert kept.isdisjoint(PASSAGE_STOP_WORDS)


def test_search_passage_stop_words_match_in_any_case() -> None:
    assert parse_passage("THE War Of The Worlds").terms == (QueryTerm("War"), QueryTerm("Worlds"))


# ------------------------------------------------------------------------------------------------
# What reaches FTS5
# ------------------------------------------------------------------------------------------------

PIECES = st.sampled_from(
    ["AND", "OR", "NOT", "NEAR(", "*", "^", "(", ")", '"', ":", "-", "tag:", "author:", "\x00", "the", "grow"]
)
PREFIXES = st.sampled_from(
    ["g*", "gr*", "gro*", "grow**", "a-bc*", "ab-cde*", "-gr*", "tag:gr*", '"gr*"', "é*"]
)
"""Prefixes either side of the three-character line, so the property meets both often."""
PASSAGES = st.one_of(
    st.text(max_size=120),
    st.lists(st.one_of(PIECES, st.text(max_size=8)), max_size=60).map(" ".join),
)


def _outside_strings(expression: str) -> str:
    return re.sub(r'"(?:[^"]|"")*"', '""', expression)


@settings(max_examples=400, deadline=None)
@given(PASSAGES)
def test_search_passage_expression_is_only_strings_joined_by_or(raw: str) -> None:
    parsed = parse_passage(raw)
    expression = parsed.fts5_expression()
    if expression is None:
        assert parsed.terms == ()
        return
    assert re.fullmatch(r'""( OR "")*', _outside_strings(expression))
    assert len(parsed.terms) <= MAX_PASSAGE_WORDS
    assert 1 <= parsed.minimum_shared <= len(parsed.terms)
    assert len(parsed.passage_words()) == len(parsed.terms)
    assert all(re.fullmatch(r'"[^"\x00-\x1f]+"', word) for word in parsed.passage_words())


@settings(max_examples=400, deadline=None)
@given(
    st.lists(st.one_of(PIECES, PREFIXES, st.text(alphabet=string.printable, max_size=8)), max_size=14).map(
        " ".join
    )
)
def test_search_query_prefix_never_shorter_than_three_reaches_fts5(raw: str) -> None:
    """Every `*` outside a string follows a phrase whose last word has three characters or more.

    ASCII only, so a word is a run of letters and digits and nothing else.
    """
    expression = parse_query(raw).fts5_expression()
    if expression is None:
        return
    for phrase in re.findall(r'"((?:[^"]|"")*)" \*', expression):
        last = re.findall(r"[A-Za-z0-9]+", phrase)[-1]
        assert len(last) >= MIN_PREFIX_CHARACTERS

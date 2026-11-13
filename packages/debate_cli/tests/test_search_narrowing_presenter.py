"""The narrowed search's command line, as `search` prints it (v1-e08-t15).

The PM's ruling: a printed command pastes safely when the query or a keyword holds an apostrophe, and a
command that would break is never printed. Every expected command is written by hand (working
agreement 6). `test_search_command.py` checks the same commands end to end, through `sh` and zsh.
"""

from __future__ import annotations

import shlex
from datetime import date

import pytest

from debate_cli.presenters.search_narrowing import DEFAULT_MAX_RESULTS, SearchCommandLine, shell_word


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("de-extinction ethics", "'de-extinction ethics'"),
        ("nature's value", "'nature'\\''s value'"),
        ("''", "''\\'''\\'''"),
        ("it's $HOME and `date` and !! and \\n", "'it'\\''s $HOME and `date` and !! and \\n'"),
        ("café über", "'café über'"),
    ],
)
def test_a_word_is_single_quoted_with_each_apostrophe_closed_escaped_and_reopened(
    text: str, word: str
) -> None:
    assert shell_word(text) == word
    assert shlex.split(word) == [text]


@pytest.mark.parametrize(
    "text", ["two\nlines", "a\ttab", "an \x1b[31mescape", "zero\u200bwidth", "a\x00null"]
)
def test_a_word_that_would_not_paste_as_shown_is_refused(text: str) -> None:
    assert shell_word(text) is None


def test_the_default_command_is_the_search_and_its_query_alone() -> None:
    assert (
        SearchCommandLine().for_query("de-extinction cloning")
        == "debate-research search 'de-extinction cloning'"
    )


def test_every_kept_option_follows_the_query_in_the_order_help_lists_them() -> None:
    line = SearchCommandLine(
        since=date(2020, 1, 1),
        until=date(2025, 12, 31),
        max_results=50,
        providers=("openalex", "rss"),
        topic="policy-2026-27-nhi",
    )
    assert line.for_query("de-extinction cloning") == (
        "debate-research search 'de-extinction cloning' --since 2020-01-01 --until 2025-12-31"
        " --max-results 50 --topic policy-2026-27-nhi --providers openalex,rss"
    )


def test_the_default_cap_is_left_out_and_any_other_kept() -> None:
    assert DEFAULT_MAX_RESULTS == 20
    assert SearchCommandLine(max_results=20).for_query("q") == "debate-research search 'q'"
    assert SearchCommandLine(max_results=1).for_query("q") == "debate-research search 'q' --max-results 1"


def test_a_query_that_starts_with_a_hyphen_goes_after_a_double_hyphen() -> None:
    assert SearchCommandLine(max_results=50).for_query("-omega cloning") == (
        "debate-research search --max-results 50 -- '-omega cloning'"
    )


def test_a_query_that_would_not_paste_gets_no_command() -> None:
    assert SearchCommandLine().for_query("de-extinction\ncloning") is None

"""When a block heading holds one of the coach's plan-mechanism words (`v1-e33-t14`).

A heading here is a block heading as the position matcher normalizes it, lowercase words one space apart.
It holds a listed word when the word, or the word with `s` or `es` after it, is one of its words; a
hyphenated word is that run of words. Nothing else is a form of a word: `waive` does not hold in `waiver`.
The file name holds `topic_config` so the task's acceptance command selects it.
"""

from __future__ import annotations

import pytest

from debate_core.application.plan_mechanism_words import holds_a_mechanism_word


@pytest.mark.parametrize(
    ("heading", "words"),
    [
        ("preemption", ("preemption",)),
        ("federal preemption bad", ("preemption",)),
        ("states preempt", ("preempt",)),
        ("waivers", ("waiver",)),
        ("waives the rule", ("waive",)),
        ("section 1332 waivers", ("preempt", "waiver")),
        ("state opt out", ("opt-out",)),
        ("state opt outs", ("opt-out",)),
        ("fees", ("fee",)),
        ("taxes", ("tax",)),
    ],
)
def test_a_heading_holding_a_listed_word_or_its_plural_holds_it(heading: str, words: tuple[str, ...]) -> None:
    assert holds_a_mechanism_word(heading, words)


@pytest.mark.parametrize(
    ("heading", "words"),
    [
        ("waiver", ("waive",)),
        ("waivers", ("waive",)),
        ("preemption", ("preempt",)),
        ("preemptive federalism", ("preempt",)),
        ("nonpreemption", ("preemption",)),
        ("waived", ("waive",)),
        ("opt in", ("opt-out",)),
        ("out opt", ("opt-out",)),
        ("optout", ("opt-out",)),
        ("states cp", ("preempt", "waiver")),
        ("preemption", ()),
    ],
)
def test_a_heading_holding_a_listed_word_only_inside_another_word_does_not_hold_it(
    heading: str, words: tuple[str, ...]
) -> None:
    assert not holds_a_mechanism_word(heading, words)

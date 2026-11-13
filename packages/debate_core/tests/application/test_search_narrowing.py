"""Narrower follow-up queries from the subjects a search's first page shares (v1-e08-t15).

The PM's ruling of 2026-11-12: OpenAlex keywords only, counted over the ranked page shown, once per
distinct result; kept on 2 or more results; left out when on a single result, on every result that
carries a keyword, or when every word of it is in the query already; ordered by result count, then the
best rank among those results, then name; at most 5.

The fixture is `works_keywords.body.json`, written by hand (its README), and every expected count,
rank and query below is worked out by hand from it (working agreement 6). Each rule has a case of its
own that no other rule answers the same way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from debate_core.application.federated_dedupe import merge_group
from debate_core.application.federated_ranking import RankedCandidate
from debate_core.application.federated_ranking_features import FEATURE_NAMES
from debate_core.application.search_narrowing import (
    MAX_SUGGESTIONS,
    MIN_RESULTS,
    NarrowingSuggestion,
    narrowing_suggestions,
)
from debate_core.domain.discovery import CandidateResult, Subject, SubjectScheme
from debate_core.integrations.discovery.openalex import candidate_from_work

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures" / "discovery" / "openalex"
KEYWORD: Final = SubjectScheme.OPENALEX_KEYWORD
KEYWORDS: Final = "https://openalex.org/keywords/"


def keyword(name: str, slug: str | None = None) -> Subject:
    return Subject(scheme=KEYWORD, name=name, provider_id=KEYWORDS + (slug or name.replace(" ", "-")))


def fixture_page() -> list[RankedCandidate]:
    """The fixture's eight works, ranked in the order the body lists them."""
    body: dict[str, Any] = json.loads((FIXTURES / "works_keywords.body.json").read_text(encoding="utf-8"))
    candidates = [candidate_from_work(work) for work in body["results"]]
    return [ranked(candidate, rank) for rank, candidate in enumerate(candidates, start=1) if candidate]


def ranked(candidate: CandidateResult | list[CandidateResult], rank: int) -> RankedCandidate:
    members = candidate if isinstance(candidate, list) else [candidate]
    return RankedCandidate(
        candidate=merge_group(members),
        rank=rank,
        total_score=0.0,
        lexical_score=None,
        features=dict.fromkeys(FEATURE_NAMES, None),
        contributions=dict.fromkeys(FEATURE_NAMES, 0.0),
        explanation="placeholder",
    )


def work(number: int, *names: str, provider: str = "openalex") -> CandidateResult:
    """A result whose only interesting field is its subjects; distinct by its number."""
    return CandidateResult(
        provider=provider,
        title=f"Invented work number {number}",
        url=f"https://journal.example.org/invented/{provider}/{number}",
        subjects=tuple(keyword(name) for name in names),
    )


def page(*works: CandidateResult) -> list[RankedCandidate]:
    return [ranked(item, rank) for rank, item in enumerate(works, start=1)]


def summary(suggestions: tuple[NarrowingSuggestion, ...]) -> list[tuple[str, int, int, str]]:
    return [(item.subject.name, item.results, item.best_rank, item.query) for item in suggestions]


def test_the_rules_are_the_pms_numbers() -> None:
    assert (MIN_RESULTS, MAX_SUGGESTIONS) == (2, 5)


def test_the_fixtures_first_page_suggests_its_five_shared_keywords_in_order() -> None:
    """By hand: six of the eight works carry keywords. `de-extinction` and `biotechnology` are on all
    six, `extinction` (3) is all in the query, `woolly mammoth` is on one work, and `human-animal
    relations` is the sixth: on works 5 and 6, as `biodiversity conservation` and `genetic rescue` are,
    and last of the three by name."""
    assert summary(narrowing_suggestions("de-extinction", fixture_page())) == [
        ("conservation ethics", 5, 1, "de-extinction conservation ethics"),
        ("animal welfare", 4, 1, "de-extinction animal welfare"),
        ("nature's value", 3, 2, "de-extinction nature's value"),
        ("biodiversity conservation", 2, 5, "de-extinction biodiversity conservation"),
        ("genetic rescue", 2, 5, "de-extinction genetic rescue"),
    ]


def test_a_suggestion_keeps_the_providers_subject_with_its_id() -> None:
    first = narrowing_suggestions("de-extinction", fixture_page())[0]
    assert first.subject == keyword("conservation ethics")


def test_a_subject_on_one_result_only_is_left_out() -> None:
    suggestions = narrowing_suggestions(
        "rewilding", page(work(1, "seed banks", "zoos"), work(2, "seed banks"), work(3, "rare breeds"))
    )
    assert summary(suggestions) == [("seed banks", 2, 1, "rewilding seed banks")]


def test_a_subject_on_every_keyword_carrying_result_is_left_out_and_a_result_without_any_does_not_count() -> (
    None
):
    """`zoos` is on both results that carry a keyword; the third result carries none, so it is still
    every one. `seed banks`, on two of the three, is kept."""
    suggestions = narrowing_suggestions(
        "rewilding",
        page(work(1, "zoos", "seed banks"), work(2, "zoos"), work(3), work(4, "zoos", "seed banks")),
    )
    assert summary(suggestions) == [("seed banks", 2, 1, "rewilding seed banks")]


def test_a_subject_on_two_of_three_keyword_carrying_results_is_kept() -> None:
    suggestions = narrowing_suggestions(
        "rewilding", page(work(1, "zoos"), work(2, "zoos"), work(3, "seed banks"))
    )
    assert summary(suggestions) == [("zoos", 2, 1, "rewilding zoos")]


def test_a_subject_whose_words_are_all_in_the_query_is_left_out_ignoring_case_and_hyphens() -> None:
    """The query's words are `de`, `extinction` and `ethics`: `Extinction`, `ethics` and `de extinction`
    add nothing, while `ethics debate` adds `debate`."""
    suggestions = narrowing_suggestions(
        "De-Extinction ethics",
        page(
            work(1, "Extinction", "ethics", "de extinction", "ethics debate", "zoos"),
            work(2, "Extinction", "ethics", "de extinction", "ethics debate"),
            work(3, "zoos"),
        ),
    )
    assert summary(suggestions) == [
        ("ethics debate", 2, 1, "De-Extinction ethics ethics debate"),
        ("zoos", 2, 1, "De-Extinction ethics zoos"),
    ]


def test_ties_on_count_go_to_the_better_best_rank_and_then_to_the_name() -> None:
    suggestions = narrowing_suggestions(
        "rewilding",
        page(
            work(1, "lynx"),
            work(2, "bison", "aurochs"),
            work(3, "bison", "aurochs", "lynx", "wolves"),
            work(4, "wolves", "beavers"),
            work(5, "wolves", "beavers"),
        ),
    )
    assert summary(suggestions) == [
        ("wolves", 3, 3, "rewilding wolves"),
        ("lynx", 2, 1, "rewilding lynx"),
        ("aurochs", 2, 2, "rewilding aurochs"),
        ("bison", 2, 2, "rewilding bison"),
        ("beavers", 2, 4, "rewilding beavers"),
    ]


def test_no_more_than_five_are_suggested() -> None:
    names = ("a1", "b2", "c3", "d4", "e5", "f6", "g7")
    suggestions = narrowing_suggestions("rewilding", page(work(1, *names), work(2, *names), work(3, "z9")))
    assert [item.subject.name for item in suggestions] == ["a1", "b2", "c3", "d4", "e5"]


def test_a_source_two_providers_found_counts_a_subject_once_from_either_member() -> None:
    """Result 1 merges an OpenAlex record carrying `zoos` twice (once in another case) and a second
    record carrying `zoos` and `seed banks`: one result each. Result 2 carries both too."""
    merged = ranked([work(1, "zoos", "Zoos"), work(1, "zoos", "seed banks", provider="semantic_scholar")], 1)
    second = ranked(work(2, "zoos", "seed banks"), 2)
    third = ranked(work(3, "lynx"), 3)
    suggestions = narrowing_suggestions("rewilding", [merged, second, third])
    assert summary(suggestions) == [
        ("seed banks", 2, 1, "rewilding seed banks"),
        ("zoos", 2, 1, "rewilding zoos"),
    ]


def test_a_subject_in_two_cases_is_one_subject_named_as_the_best_ranked_result_names_it() -> None:
    suggestions = narrowing_suggestions(
        "rewilding", page(work(1, "Animal Welfare"), work(2, "animal welfare"), work(3, "lynx"))
    )
    assert summary(suggestions) == [("Animal Welfare", 2, 1, "rewilding Animal Welfare")]


def test_a_page_without_subjects_suggests_nothing() -> None:
    assert narrowing_suggestions("rewilding", page(work(1), work(2))) == ()
    assert narrowing_suggestions("rewilding", []) == ()

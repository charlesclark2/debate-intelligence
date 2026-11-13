"""Narrower follow-up queries from what a search's first page is about (v1-e08-t15).

The coach on LD research (2026-11-02): start high level, then hone in on what the surface research
finds. A search's own results say what they are about: OpenAlex gives each work its keywords, short
phrases best first. The subjects several results on the page share are directions the broad query
already found, so each becomes a narrower query, the student's query with the subject's words added.
No model is asked, and no provider: the subjects came with the answer the search already has.

**The rule** (the PM's ruling of 2026-11-12):

* counted over the page the search shows, `ranked`, once per distinct result: a source two
  providers found is one result, and a subject on either record counts for it once;
* subjects are one subject when their names are the same ignoring case, named as the best-ranked
  result carrying it names it;
* kept when on :data:`MIN_RESULTS` results or more; left out when it is on a single result, on every
  result that carries any subject (narrowing by it changes nothing), or when every one of its words
  is in the query already (:func:`words`);
* ordered by how many results carry it, then by the best rank among them, then by name;
* at most :data:`MAX_SUGGESTIONS`.

An expanded search (`--argument` with `--need`) is asked the taxonomy's queries, not the one a student
typed, so :func:`narrowing_for` suggests nothing for it. Which command a suggestion prints is the
CLI's (`debate_cli.presenters.search_narrowing`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from debate_core.application.federated_ranking import RankedCandidate
from debate_core.application.federated_search_types import SearchOutcome
from debate_core.domain.discovery import Subject

__all__ = [
    "MAX_SUGGESTIONS",
    "MIN_RESULTS",
    "NarrowingSuggestion",
    "narrowing_for",
    "narrowing_suggestions",
    "words",
]

MAX_SUGGESTIONS: Final = 5
"""The most suggestions a search shows."""

MIN_RESULTS: Final = 2
"""The fewest results on the page a subject must be on to be suggested."""

_WORD: Final = re.compile(r"[^\W_]+")


@dataclass(frozen=True, slots=True)
class NarrowingSuggestion:
    """One narrower query: the subject it adds, how much of the page carries it, and the query."""

    subject: Subject
    results: int
    """How many results on the page carry the subject."""
    best_rank: int
    """The best (lowest) rank among them."""
    query: str
    """The search's query with the subject's name added after a space."""


def words(text: str) -> frozenset[str]:
    """The words of `text`, ignoring case: runs of letters and digits, so a hyphen or apostrophe splits."""
    return frozenset(_WORD.findall(text.casefold()))


@dataclass(slots=True)
class _Tally:
    subject: Subject
    results: int
    best_rank: int


def narrowing_suggestions(query: str, ranked: Sequence[RankedCandidate]) -> tuple[NarrowingSuggestion, ...]:
    """The narrower queries the page `ranked` suggests for `query` (see the module docstring)."""
    asked = words(query)
    tallies: dict[str, _Tally] = {}
    carrying = 0
    for result in sorted(ranked, key=lambda item: item.rank):
        names: dict[str, Subject] = {}
        for member in result.candidate.members:
            for subject in member.subjects:
                names.setdefault(subject.name.casefold(), subject)
        if names:
            carrying += 1
        for key, subject in names.items():
            tally = tallies.get(key)
            if tally is None:
                tallies[key] = _Tally(subject, 1, result.rank)
            else:
                tally.results += 1
    kept = [
        tally
        for tally in tallies.values()
        if MIN_RESULTS <= tally.results < carrying and not words(tally.subject.name) <= asked
    ]
    kept.sort(key=lambda tally: (-tally.results, tally.best_rank, tally.subject.name.casefold()))
    return tuple(
        NarrowingSuggestion(
            subject=tally.subject,
            results=tally.results,
            best_rank=tally.best_rank,
            query=f"{query} {tally.subject.name}",
        )
        for tally in kept[:MAX_SUGGESTIONS]
    )


def narrowing_for(outcome: SearchOutcome) -> tuple[NarrowingSuggestion, ...]:
    """What a finished search suggests: nothing for an expanded search, else its page's suggestions."""
    if outcome.search.expansion is not None:
        return ()
    return narrowing_suggestions(outcome.search.query, outcome.ranked_candidates)

"""The ranking's BM25 weights, justified on a small synthetic relevance set (`v1-e39-t03`).

The set is twelve queries over thirty-six invented documents, each query with its relevant documents
graded by hand: 2 for the card a debater typing the query wants, 1 for a card worth seeing, 0 for the
rest. It encodes three judgments about debate evidence, and the documents are built so that each
weight has to earn its place:

* **A word in the tag says what the card argues.** For each topic the card tagged with it (grade 2)
  competes with a card that repeats the word in its body without arguing it (grade 0), and with one
  whose cite names it as a journal (grade 1).
* **A name with no prefix is usually an author.** For each author the card by them (grade 2) competes
  with a card whose body discusses them (grade 1) and one whose tag mentions them in passing (grade 1).
* **What is read aloud is the card.** For two-word claims the card that reads both words aloud
  (grade 2) competes with one that has one of them in its tag and the other only in unread text
  (grade 1), and one with both only in unread text (grade 0).

The score is the mean nDCG at 5. :data:`CANDIDATES` are the weightings the session report compares;
the test holds that :data:`~debate_core.domain.evidence_search.RANKING_WEIGHTS` scores at least as
well as every one of them and better than equal weights. The text is generic English and invented
names, never card text (data-use policy, rule 5).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.evidence_search import EvidenceSearchService
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.domain.debate_files import FormattingSpan
from debate_core.domain.evidence_search import RANKING_WEIGHTS, RankingWeights
from debate_core.domain.search_index import read_aloud_text
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader

TOPICS: Final = ("deterrence", "inflation", "automation", "sanctions")
AUTHORS: Final = ("Okafor", "Lindqvist", "Haddad", "Moreau")
CLAIMS: Final = (
    ("tariffs", "recession"),
    ("drones", "escalation"),
    ("warming", "migration"),
    ("privacy", "surveillance"),
)

FILLER: Final = (
    "the evidence suggests that policy makers should weigh the long term effects of any change "
    "before acting because the costs of a mistake are often larger than the benefits of speed"
)
"""Generic words, so the bodies have realistic length and no term of the queries."""


def _span(start: int, end: int) -> FormattingSpan:
    return FormattingSpan(
        emphasis=RunEmphasis.UNDERLINE,
        start_offset=start,
        end_offset=end,
        rule_id="synthetic",
        match_source=StyleMatchSource.VERBATIM,
    )


def _body(read: str, unread: str = "") -> tuple[str, tuple[FormattingSpan, ...]]:
    """A body of filler with `read` underlined in the middle and `unread` after it, not underlined."""
    head = f"{FILLER} "
    text = f"{head}{read} {FILLER} {unread}".strip()
    return text, ((_span(len(head), len(head) + len(read)),) if read else ())


class Corpus:
    """The thirty-six documents, and each query's grades."""

    def __init__(self) -> None:
        self.documents: list[SearchDocument] = []
        self.grades: dict[str, dict[int, int]] = {}

    def add(self, *, tag: str, cite: str, read: str = "", unread: str = "") -> int:
        doc_id = len(self.documents) + 1
        text, spans = _body(read, unread)
        self.documents.append(
            SearchDocument(
                doc_id=doc_id,
                caselist="hsld26",
                cluster_id=f"{doc_id:064x}",
                event="LD",
                camp=None,
                tag=tag,
                cite=cite,
                short_cite=cite.split(",")[0],
                read_aloud=read_aloud_text(text, spans),
                text=text,
                completeness="FULL",
                formatting_spans=spans,
                font_size_spans=(),
                sides=("AFF",),
                first_seen="2026-09-01",
                last_seen="2026-09-01",
                file_count=1,
                team_count=1,
                occurrences=(
                    IndexedOccurrence(
                        ordinal=0,
                        caselist="hsld26",
                        source_sha256=f"{doc_id:064x}",
                        disclosure=None,
                        first_element_index=0,
                        last_element_index=2,
                        snapshot="2026-09-01",
                        last_snapshot="2026-09-01",
                        completeness="FULL",
                        attributed=False,
                        provenance=True,
                    ),
                ),
            )
        )
        return doc_id


FIELDS: Final = ("economics", "international relations", "public policy", "computer science")
TITLES: Final = (
    "Rethinking the Costs of Delay",
    "What the Record Shows",
    "A Second Look at the Evidence on Long Term Change",
    "Why Forecasts Fail",
)


def cite(author: str, number: int, journal: str = "Invented Policy Review") -> str:
    """A cite of realistic length, 16 to 30 words: author, year, credentials, title, journal, date."""
    title = TITLES[number % len(TITLES)]
    field = FIELDS[number % len(FIELDS)]
    return (
        f"{author} {20 + number % 7}, Dr. {author}, professor of {field} at Invented University, "
        f"{title}, {journal}, Volume {number}, accessed 2026-09-0{1 + number % 8}"
    )


def tag(words: str, number: int) -> str:
    """A tag of 4 to 13 words: the claim, and for some cards the reason after it."""
    reasons = (
        "",
        " because the data shows it",
        " and the impact is large and fast",
        " because history proves it",
    )
    return words + reasons[number % len(reasons)]


def corpus() -> Corpus:
    built = Corpus()
    for number, topic in enumerate(TOPICS):
        wanted = built.add(
            tag=tag(f"{topic.title()} fails and the harms follow", number),
            cite=cite("Novak", number),
            read=f"{topic} fails",
        )
        repeated = built.add(
            tag=tag("Experts disagree about the future", number + 1),
            cite=cite("Tanaka", number + 1, "Invented Quarterly"),
            read="the future is uncertain",
            unread=" ".join([topic] * 6),
        )
        journal = built.add(
            tag=tag("Leaders often misjudge the risks", number + 2),
            cite=cite("Novak", number + 2, f"Invented Journal of {topic.title()}"),
            read=f"leaders misjudge {topic} risks",
        )
        built.grades[topic] = {wanted: 2, journal: 1, repeated: 0}
    for number, author in enumerate(AUTHORS):
        theirs = built.add(
            tag=tag("Cooperation is possible", number), cite=cite(author, number), read="cooperation works"
        )
        about = built.add(
            tag=tag("Critics answer the cooperation thesis", number + 1),
            cite=cite("Novak", number + 1),
            read=f"{author} argues that cooperation works but {author} is wrong",
            unread=f"{author} {author}",
        )
        passing = built.add(
            tag=tag(f"{author} style arguments fail", number + 2),
            cite=cite("Tanaka", number + 2, "Invented Quarterly"),
            read="those arguments fail",
        )
        built.grades[author.lower()] = {theirs: 2, about: 1, passing: 1}
    for number, (first, second) in enumerate(CLAIMS):
        both = built.add(
            tag=tag("The link is strong", number),
            cite=cite("Novak", number + 3),
            read=f"{first} cause {second}",
        )
        split = built.add(
            tag=tag(f"{first.title()} matter", number + 1),
            cite=cite("Tanaka", number + 3, "Invented Quarterly"),
            read="the stakes are high",
            unread=second,
        )
        unread = built.add(
            tag=tag("Unrelated claim", number + 2),
            cite=cite("Tanaka", number + 4, "Invented Quarterly"),
            read="nothing is certain",
            unread=f"{first} {second}",
        )
        built.grades[f"{first} {second}"] = {both: 2, split: 1, unread: 0}
    return built


CANDIDATES: Final = {
    "equal": RankingWeights(tag=1.0, cite=1.0, read_aloud=1.0, text=1.0),
    "t02 probe": RankingWeights(tag=4.0, cite=2.0, read_aloud=2.0, text=1.0),
    "tag only heavy": RankingWeights(tag=10.0, cite=1.0, read_aloud=1.0, text=1.0),
    "cite as tag": RankingWeights(tag=8.0, cite=8.0, read_aloud=2.0, text=1.0),
    "cite light": RankingWeights(tag=8.0, cite=3.0, read_aloud=2.0, text=1.0),
    "no read-aloud boost": RankingWeights(tag=10.0, cite=6.0, read_aloud=1.0, text=1.0),
    "text heavy": RankingWeights(tag=1.0, cite=1.0, read_aloud=1.0, text=4.0),
}
"""The weightings the session report compares with :data:`RANKING_WEIGHTS`."""


def ndcg_at_5(ranked: list[int], grades: dict[int, int]) -> float:
    def dcg(gains: list[int]) -> float:
        return sum((2**gain - 1) / math.log2(position + 2) for position, gain in enumerate(gains[:5]))

    ideal = dcg(sorted(grades.values(), reverse=True))
    return dcg([grades.get(doc_id, 0) for doc_id in ranked]) / ideal


def mean_ndcg(path: Path, weights: RankingWeights, grades: dict[str, dict[int, int]]) -> float:
    searched = EvidenceSearchService(SqliteSearchIndexReader(path, index_id="0" * 16), weights=weights)
    scores = [
        ndcg_at_5([int(hit.cluster_id, 16) for hit in searched.search(query).hits], judged)
        for query, judged in grades.items()
    ]
    return sum(scores) / len(scores)


@pytest.fixture(scope="module")
def relevance_set(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, dict[int, int]]]:
    built = corpus()
    path = tmp_path_factory.mktemp("relevance") / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for document in built.documents:
        sink.add(document)
    sink.finish()
    return path, built.grades


def test_search_relevance_set_is_twelve_queries_over_thirty_six_documents(
    relevance_set: tuple[Path, dict[str, dict[int, int]]],
) -> None:
    _, grades = relevance_set
    assert len(grades) == 12
    assert sorted(doc_id for judged in grades.values() for doc_id in judged) == list(range(1, 37))


def test_search_ranking_weights_score_at_least_every_candidate_on_the_relevance_set(
    relevance_set: tuple[Path, dict[str, dict[int, int]]],
) -> None:
    path, grades = relevance_set
    chosen = mean_ndcg(path, RANKING_WEIGHTS, grades)
    scores = {name: mean_ndcg(path, weights, grades) for name, weights in CANDIDATES.items()}
    print(
        f"\nmean nDCG@5: chosen {chosen:.4f}; "
        + "; ".join(f"{name} {score:.4f}" for name, score in scores.items())
    )
    assert all(chosen >= score for score in scores.values()), scores
    assert chosen > scores["equal"]

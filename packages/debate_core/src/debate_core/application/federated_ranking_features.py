"""The seven ranking features of a federated search, each a value between 0 and 1 or unknown.

:mod:`debate_core.application.federated_ranking` weighs these into a score and an explanation. This
module only measures: every number that decides how much a feature counts, or where its scale
saturates, is a parameter here and comes from `config/federated_ranking.yaml`.

Each feature, and when it is unknown:

* `bm25`: Okapi BM25 of the title and snippet against the query terms, scaled so the best result in
  the set is 1. Unknown when the query has no terms.
* `recency`: the result's position in the date window, or a half-life decay without one. Unknown
  when the result is undated.
* `source_type`: the configured value of its category. Always known.
* `peer_reviewed`: always unknown, because no provider reports it yet.
* `open_access`: 1 when a provider names an open copy or says one exists, 0 when the provider
  trusted for it says none does and nobody named one. Unknown when no provider said.
* `citations`: the log-scaled count, for scholarship only. Unknown for anything else, or with no
  count.
* `provider_agreement`: the share of the other answering providers that also found it. Unknown when
  one provider answered, or none.

**Unknown is not 0.** An unknown feature contributes nothing to the score and is not mentioned in
the explanation, so "no provider said" never reads as "the answer is no".

**Peer review is never inferred.** A preprint is scholarly and not peer-reviewed, which is why
deduplication keeps it apart from its published version (v1-e08-t02). No adapter reports peer
review yet, so :func:`peer_reviewed` is unknown for every result; it reads the provider's field
when one exists, and never `source_type`, the venue or the DOI.

## The tokenizer

:func:`ranking_tokens` turns a title, snippet or query into the words BM25 counts. The query and
the documents go through the same steps, so two spellings of one word meet:

1. HTML entities are decoded and markup removed, accents dropped and case folded
   (:func:`~debate_core.application.federated_dedupe.plain_text`, which deduplication uses too);
2. a possessive `'s` is dropped (`China's` is `china`), and an apostrophe or full stop between two
   letters joins them (`don't` is `dont`, `U.S.` is `us`);
3. every other character that is not a letter or digit separates words, hyphens included, so
   `pass-through` is `pass` and `through` and either half of a query matches it;
4. each word takes its American spelling
   (:func:`~debate_core.application.federated_dedupe.american_spelling`), so `labour` and `labor`,
   `defence` and `defense`, are one word.

Numbers are words (`230`, `2026`). Nothing is stemmed and no stop words are removed: in a result
set, a word every document has gets a near-zero inverse document frequency anyway.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from debate_core.application.federated_dedupe import MergedCandidate, american_spelling, plain_text
from debate_core.domain.enums import SourceType

__all__ = [
    "FEATURE_NAMES",
    "FeatureVector",
    "age_in_days",
    "bm25_scores",
    "citations",
    "document_tokens",
    "open_access",
    "peer_reviewed",
    "provider_agreement",
    "query_terms",
    "ranking_tokens",
    "recency",
    "source_type_value",
]

FEATURE_NAMES: Final = (
    "bm25",
    "recency",
    "source_type",
    "peer_reviewed",
    "open_access",
    "citations",
    "provider_agreement",
)
"""The seven features, in the order a result's feature vector names them."""

_SECONDS_PER_DAY: Final = 86_400


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureVector:
    """One result's seven features, each between 0 and 1, or None when unknown."""

    bm25: float | None
    recency: float | None
    source_type: float | None
    peer_reviewed: float | None
    open_access: float | None
    citations: float | None
    provider_agreement: float | None

    def as_dict(self) -> dict[str, float | None]:
        """The features by name, in :data:`FEATURE_NAMES` order."""
        return {name: getattr(self, name) for name in FEATURE_NAMES}


# ---------------------------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------------------------

_POSSESSIVE = re.compile(r"(?<=[^\W_])['’]s\b")
_JOINED_BETWEEN_LETTERS = re.compile(r"(?<=[^\W_])['’.](?=[^\W_])")
_WORD = re.compile(r"[^\W_]+")


def ranking_tokens(text: str) -> tuple[str, ...]:
    """The words BM25 counts in `text`, by the steps in the module docstring."""
    plain = _JOINED_BETWEEN_LETTERS.sub("", _POSSESSIVE.sub("", plain_text(text)))
    return tuple(american_spelling(word) for word in _WORD.findall(plain))


def document_tokens(candidate: MergedCandidate) -> tuple[str, ...]:
    """What BM25 reads of one result: its title's words, then its snippet's."""
    return ranking_tokens(candidate.title) + ranking_tokens(candidate.snippet or "")


def query_terms(queries: Iterable[str]) -> tuple[str, ...]:
    """Every distinct word of every query asked, in the order each first appears.

    Distinct, so a term that several expanded queries share counts once rather than once per query.
    """
    return tuple(dict.fromkeys(token for query in queries for token in ranking_tokens(query)))


# ---------------------------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------------------------


def bm25_scores(
    documents: Sequence[Sequence[str]], terms: Sequence[str], *, k1: float, b: float
) -> tuple[float, ...]:
    """Okapi BM25 of each document against the distinct `terms`, over `documents` as the corpus.

    For N documents of average length L, a term in n of them has inverse document frequency
    `ln(1 + (N - n + 0.5) / (n + 0.5))`, which is never negative. A document of length d holding the
    term f times gains `idf * f * (k1 + 1) / (f + k1 * (1 - b + b * d / L))` for it.
    """
    if not documents:
        return ()
    average = sum(len(document) for document in documents) / len(documents)
    if average == 0:
        return tuple(0.0 for _ in documents)
    counts = [Counter(document) for document in documents]
    count = len(documents)
    idf: dict[str, float] = {}
    for term in dict.fromkeys(terms):
        holders = sum(1 for frequencies in counts if term in frequencies)
        idf[term] = math.log(1 + (count - holders + 0.5) / (holders + 0.5))
    scores: list[float] = []
    for document, frequencies in zip(documents, counts, strict=True):
        length_norm = 1 - b + b * len(document) / average
        scores.append(
            sum(
                weight * frequencies[term] * (k1 + 1) / (frequencies[term] + k1 * length_norm)
                for term, weight in idf.items()
                if frequencies[term]
            )
        )
    return tuple(scores)


# ---------------------------------------------------------------------------------------------
# Recency
# ---------------------------------------------------------------------------------------------


def age_in_days(published_at: datetime | None, reference: datetime) -> int | None:
    """Whole days from publication to `reference`, never negative; None for an undated result."""
    if published_at is None:
        return None
    return max(int((reference - published_at).total_seconds() // _SECONDS_PER_DAY), 0)


def recency(
    published_at: datetime | None, *, reference: datetime, since: datetime | None, half_life_days: float
) -> float | None:
    """How recent a result is, between 0 and 1; None when it is undated.

    With a date window (`since` before `reference`, the window's end), the result's position in it:
    0 at `since` or before, 1 at `reference` or after. Without one, `0.5 ** (age / half_life_days)`:
    1 for a result published at `reference` or later, 0.5 one half-life before it.
    """
    if published_at is None:
        return None
    if since is not None and since < reference:
        position = (published_at - since) / (reference - since)
        return min(max(position, 0.0), 1.0)
    age = max((reference - published_at).total_seconds() / _SECONDS_PER_DAY, 0.0)
    return 0.5 ** (age / half_life_days)


# ---------------------------------------------------------------------------------------------
# Source type, peer review, open access, citations, provider agreement
# ---------------------------------------------------------------------------------------------


def source_type_value(source_type: SourceType, values: Mapping[SourceType, float]) -> float:
    """The configured value of a result's category: a category, never an outlet."""
    return values[source_type]


def peer_reviewed(candidate: MergedCandidate) -> float | None:
    """Unknown for every result: no provider reports peer review yet.

    Deliberately not derived from `source_type`, the venue or the DOI. A preprint is scholarly and
    not peer-reviewed, and a guess here would be a hidden judgment presented as a fact.
    """
    return None


def open_access(candidate: MergedCandidate) -> float | None:
    """Whether a debater can read the result free: 1, 0, or unknown.

    An open copy that some provider named is 1 even when the provider trusted for the open-access
    flag says there is none: the copy is there to be read. Otherwise the flag decides (OpenAlex,
    then Semantic Scholar, by deduplication's precedence), and with no flag nobody said, which is
    not 0.
    """
    if candidate.open_access_url is not None or candidate.open_access is True:
        return 1.0
    if candidate.open_access is False:
        return 0.0
    return None


def citations(candidate: MergedCandidate, *, saturation: int) -> float | None:
    """`log(1 + count) / log(1 + saturation)`, at most 1, for scholarship; unknown otherwise.

    Only scholarship: a citation count measures how much other papers rely on a paper, and a news
    story, a government report or a think-tank brief that no index counts is not thereby uncited.
    """
    if candidate.source_type is not SourceType.SCHOLARLY or candidate.citation_count is None:
        return None
    return min(math.log1p(candidate.citation_count) / math.log1p(saturation), 1.0)


def provider_agreement(candidate: MergedCandidate, *, answered: int) -> float | None:
    """The share of the other providers that answered which also found this result.

    `answered` is how many distinct providers answered the search. With one or none there is
    nothing to agree with, so the feature is unknown.
    """
    if answered <= 1:
        return None
    return min((len(candidate.providers) - 1) / (answered - 1), 1.0)

"""Federated ranking: the features, the weighted score and its tie order, the explanations, the stage.

Every expected value here is written out by hand (working agreement 6): BM25 scores as the Okapi
formula applied to the token counts, totals as weight times value summed over the features, the
order a tie falls in and each explanation's wording. None of it was produced by running the code
under test. The weights are this file's own table, `TEST_CONFIG`, so tuning the committed
`config/federated_ranking.yaml` never moves an expectation; the tests that read the committed
file say so.

The spec's plan nodes select these tests by name: `-k feature` for the feature extractors,
`-k "score or explain"` for the scorer and the explanations, and the whole file for the rest.
"""

from __future__ import annotations

import asyncio
import math
import socket
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from debate_core.application import federated_ranking, federated_ranking_features
from debate_core.application.federated_dedupe import (
    DedupeStage,
    MergedCandidate,
    merge_candidates,
    merge_group,
)
from debate_core.application.federated_ranking import (
    FEDERATED_RANKING_CONFIG_PATH,
    FederatedRankingConfig,
    FederatedRankStage,
    InvalidFederatedRankingConfig,
    RankedCandidate,
    load_federated_ranking_config,
    parse_federated_ranking_config,
    rank_merged_candidates,
    search_result_for,
)
from debate_core.application.federated_ranking_features import (
    FEATURE_NAMES,
    FeatureVector,
    age_in_days,
    bm25_scores,
    document_tokens,
    open_access,
    peer_reviewed,
    provider_agreement,
    query_terms,
    ranking_tokens,
    recency,
    source_type_value,
)
from debate_core.application.federated_search import FederatedSearchService
from debate_core.application.federated_search_types import SearchRequest, SearchState
from debate_core.application.ports import SearchProvider
from debate_core.domain import SearchFilters
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import (
    CandidateResult,
    ProviderHealth,
    ProviderOutcome,
    ProviderQuery,
    ProviderResponse,
    ProviderStatus,
)
from debate_core.domain.enums import SourceType
from debate_core.testing.builders import build_search, readable_id
from debate_core.testing.fakes import (
    FakeSearchProvider,
    FixedClock,
    InMemorySearchRepository,
    SequentialIdGenerator,
)
from debate_core.testing.virtual_time import EventLoopClock, run_in_virtual_time

REPOSITORY = Path(__file__).resolve().parents[4]

NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)

TEST_CONFIG_TEXT = """\
weights:
  bm25: 0.5
  recency: 0.3
  source_type: 0.1
  peer_reviewed: 0.1
  open_access: 0.05
  citations: 0.2
  provider_agreement: 0.05
bm25:
  k1: 1.2
  b: 0.75
recency:
  half_life_days: 90
citations:
  saturation: 1000
source_type_values:
  scholarly: 1.0
  government: 0.9
  think_tank: 0.7
  news: 0.5
  other: 0.0
explanation:
  max_features: 4
  strong_term_match: 0.6
"""

TEST_CONFIG = parse_federated_ranking_config(TEST_CONFIG_TEXT, source="TEST_CONFIG")


def config_with(**sections: dict[str, object]) -> FederatedRankingConfig:
    """`TEST_CONFIG` with whole sections replaced, e.g. `weights={...}`."""
    return TEST_CONFIG.model_validate({**TEST_CONFIG.model_dump(), **sections})


def only_weight(feature: str, *, others: float = 0.0) -> FederatedRankingConfig:
    """A config in which one feature has weight 1 and every other feature `others`."""
    return config_with(weights={name: 1.0 if name == feature else others for name in FEATURE_NAMES})


def record(
    *,
    provider: str = "openalex",
    title: str = "Carbon tax and emissions",
    url: str = "https://example.org/papers/carbon-tax",
    canonical_url: str | None = None,
    source_type: SourceType = SourceType.SCHOLARLY,
    published_at: datetime | None = None,
    snippet: str | None = None,
    open_access_url: str | None = None,
    publication: str | None = None,
    doi: str | None = None,
) -> CandidateResult:
    return CandidateResult(
        provider=provider,
        title=title,
        url=url,
        canonical_url=canonical_url,
        source_type=source_type,
        published_at=published_at,
        snippet=snippet,
        open_access_url=open_access_url,
        publication=publication,
        identifiers=ArticleIdentifiers(doi=doi),
    )


def merged(*records: CandidateResult) -> MergedCandidate:
    return merge_group(records)


def one(**fields: object) -> MergedCandidate:
    return merge_group([record(**fields)])  # type: ignore[arg-type]


def rank(
    candidates: Sequence[MergedCandidate],
    *,
    query: str | Sequence[str] = "carbon tax",
    filters: SearchFilters | None = None,
    answered: int = 2,
    config: FederatedRankingConfig = TEST_CONFIG,
) -> tuple[RankedCandidate, ...]:
    return rank_merged_candidates(
        candidates,
        queries=(query,) if isinstance(query, str) else tuple(query),
        filters=SearchFilters() if filters is None else filters,
        answered_providers=answered,
        now=NOW,
        config=config,
    )


def titles(ranked: Sequence[RankedCandidate]) -> list[str]:
    return [entry.candidate.title for entry in ranked]


def urls(ranked: Sequence[RankedCandidate]) -> list[str]:
    return [entry.candidate.url for entry in ranked]


# --------------------------------------------------------------------------------------------
# The tokenizer
# --------------------------------------------------------------------------------------------


def test_feature_tokens_fold_case_accents_markup_possessives_and_british_spelling() -> None:
    assert ranking_tokens("The <i>Labour</i> Market's “Défense” of U.S.-China trade") == (
        "the",
        "labor",
        "market",
        "defense",
        "of",
        "us",
        "china",
        "trade",
    )


def test_feature_tokens_split_a_hyphenated_word_so_a_query_matches_either_half() -> None:
    assert ranking_tokens("Tariff pass-through to consumers") == (
        "tariff",
        "pass",
        "through",
        "to",
        "consumers",
    )


def test_feature_tokens_keep_numbers_and_decode_entities() -> None:
    assert ranking_tokens("Section 230 &amp; platform reform, 2026") == (
        "section",
        "230",
        "platform",
        "reform",
        "2026",
    )


def test_feature_tokens_of_a_query_and_a_document_spelled_differently_agree() -> None:
    assert ranking_tokens("defence organisations") == ranking_tokens("Defense organizations")


def test_feature_document_tokens_read_the_title_then_the_snippet() -> None:
    with_snippet = one(title="Carbon tax", snippet="A price on emissions.")
    without = one(title="Carbon tax")

    assert document_tokens(with_snippet) == ("carbon", "tax", "a", "price", "on", "emissions")
    assert document_tokens(without) == ("carbon", "tax")


def test_feature_query_terms_are_distinct_across_the_expanded_queries_in_first_appearance_order() -> None:
    assert query_terms(["carbon tax", "Carbon tax effects", "tax policy"]) == (
        "carbon",
        "tax",
        "effects",
        "policy",
    )


# --------------------------------------------------------------------------------------------
# BM25
# --------------------------------------------------------------------------------------------


def okapi(tf: int, length: int, average: float, idf: float, *, k1: float = 1.2, b: float = 0.75) -> float:
    """One term's Okapi BM25 contribution, written out from the formula."""
    return idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / average))


def test_feature_bm25_is_the_okapi_formula_over_the_result_set() -> None:
    documents = [("carbon", "tax", "policy"), ("carbon", "carbon", "price"), ("wind", "power")]
    # N = 3 documents, average length 8/3. "carbon" is in 2 of them, "tax" in 1.
    idf_carbon = math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
    idf_tax = math.log(1 + (3 - 1 + 0.5) / (1 + 0.5))
    average = 8 / 3

    scores = bm25_scores(documents, ("carbon", "tax"), k1=1.2, b=0.75)

    assert scores == pytest.approx(
        (
            okapi(1, 3, average, idf_carbon) + okapi(1, 3, average, idf_tax),
            okapi(2, 3, average, idf_carbon),
            0.0,
        )
    )


def test_feature_bm25_uses_its_length_parameter_b() -> None:
    short, long = ("carbon",), ("carbon", "wind", "solar", "hydro")

    flat = bm25_scores([short, long], ("carbon",), k1=1.2, b=0.0)
    discounted = bm25_scores([short, long], ("carbon",), k1=1.2, b=0.75)

    assert flat[0] == pytest.approx(flat[1])
    assert discounted[0] > discounted[1]


def test_feature_bm25_uses_its_saturation_parameter_k1() -> None:
    once, thrice = ("carbon", "tax", "x"), ("carbon", "carbon", "carbon")
    idf = math.log(1 + (2 - 2 + 0.5) / (2 + 0.5))

    scores = bm25_scores([once, thrice], ("carbon",), k1=2.0, b=0.0)

    assert scores == pytest.approx((idf * 1 * 3.0 / (1 + 2.0), idf * 3 * 3.0 / (3 + 2.0)))


def test_feature_bm25_counts_a_repeated_query_term_once() -> None:
    documents = [("carbon", "tax"), ("wind",)]

    assert bm25_scores(documents, ("carbon", "carbon"), k1=1.2, b=0.75) == pytest.approx(
        bm25_scores(documents, ("carbon",), k1=1.2, b=0.75)
    )


def test_feature_bm25_of_no_documents_no_terms_or_empty_documents() -> None:
    assert bm25_scores([], ("carbon",), k1=1.2, b=0.75) == ()
    assert bm25_scores([("carbon",)], (), k1=1.2, b=0.75) == (0.0,)
    assert bm25_scores([(), ()], ("carbon",), k1=1.2, b=0.75) == (0.0, 0.0)


# --------------------------------------------------------------------------------------------
# Recency
# --------------------------------------------------------------------------------------------


def test_feature_recency_of_an_undated_result_is_unknown() -> None:
    assert recency(None, reference=NOW, since=None, half_life_days=90) is None
    assert recency(None, reference=NOW, since=NOW - timedelta(days=10), half_life_days=90) is None


@pytest.mark.parametrize(
    ("days_old", "expected"),
    [(0, 1.0), (90, 0.5), (180, 0.25), (45, 2**-0.5), (-5, 1.0)],
)
def test_feature_recency_without_a_window_halves_every_half_life(days_old: int, expected: float) -> None:
    published = NOW - timedelta(days=days_old)

    assert recency(published, reference=NOW, since=None, half_life_days=90) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        (datetime(2026, 10, 1, tzinfo=UTC), 0.0),
        (datetime(2026, 10, 6, tzinfo=UTC), 0.5),
        (datetime(2026, 10, 11, tzinfo=UTC), 1.0),
        (datetime(2026, 9, 1, tzinfo=UTC), 0.0),
        (datetime(2026, 10, 20, tzinfo=UTC), 1.0),
    ],
)
def test_feature_recency_within_a_window_is_the_position_in_it(published: datetime, expected: float) -> None:
    since, until = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 11, tzinfo=UTC)

    assert recency(published, reference=until, since=since, half_life_days=90) == pytest.approx(expected)


def test_feature_recency_of_a_window_with_no_length_falls_back_to_the_half_life() -> None:
    published = NOW - timedelta(days=90)

    assert recency(published, reference=NOW, since=NOW, half_life_days=90) == pytest.approx(0.5)


def test_feature_age_in_days_is_whole_days_never_negative() -> None:
    assert age_in_days(NOW - timedelta(days=3, hours=23), NOW) == 3
    assert age_in_days(NOW + timedelta(days=2), NOW) == 0
    assert age_in_days(None, NOW) is None


# --------------------------------------------------------------------------------------------
# Source type, peer review, open access, provider agreement
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source_type", "expected"),
    [
        (SourceType.SCHOLARLY, 1.0),
        (SourceType.GOVERNMENT, 0.9),
        (SourceType.THINK_TANK, 0.7),
        (SourceType.NEWS, 0.5),
        (SourceType.OTHER, 0.0),
    ],
)
def test_feature_source_type_is_the_configured_value_for_its_category(
    source_type: SourceType, expected: float
) -> None:
    assert source_type_value(source_type, TEST_CONFIG.source_type_values) == expected


@pytest.mark.parametrize(
    "candidate",
    [
        one(source_type=SourceType.SCHOLARLY, publication="Journal of Example Studies", doi="10.1000/jes.1"),
        one(
            source_type=SourceType.SCHOLARLY,
            url="https://arxiv.org/abs/2601.00001",
            publication="arXiv",
            doi="10.48550/arxiv.2601.00001",
        ),
        one(source_type=SourceType.GOVERNMENT),
        one(source_type=SourceType.NEWS),
        one(source_type=SourceType.OTHER),
    ],
    ids=["journal-article", "arxiv-preprint", "government", "news", "other"],
)
def test_feature_peer_review_is_unknown_and_never_read_from_the_source_type(
    candidate: MergedCandidate,
) -> None:
    """No adapter reports peer review, and a preprint is scholarly but not reviewed (PM, 2026-10-22)."""
    assert peer_reviewed(candidate) is None


def test_feature_open_access_is_known_only_when_a_provider_names_an_open_copy() -> None:
    assert open_access(one(open_access_url="https://repository.example.edu/carbon.pdf")) == 1.0
    assert open_access(one()) is None


@pytest.mark.parametrize(
    ("providers", "answered", "expected"),
    [
        (("openalex", "crossref", "semantic_scholar"), 3, 1.0),
        (("openalex", "crossref"), 3, 0.5),
        (("openalex",), 3, 0.0),
        (("openalex",), 1, None),
        (("openalex",), 0, None),
    ],
)
def test_feature_provider_agreement_is_the_share_of_the_other_providers_that_answered(
    providers: tuple[str, ...], answered: int, expected: float | None
) -> None:
    candidate = merged(*(record(provider=name, doi="10.1000/shared") for name in providers))

    assert provider_agreement(candidate, answered=answered) == expected


def test_feature_vector_names_the_seven_features_in_order() -> None:
    vector = FeatureVector(
        bm25=1.0,
        recency=None,
        source_type=0.5,
        peer_reviewed=None,
        open_access=None,
        citations=None,
        provider_agreement=0.0,
    )

    assert FEATURE_NAMES == (
        "bm25",
        "recency",
        "source_type",
        "peer_reviewed",
        "open_access",
        "citations",
        "provider_agreement",
    )
    assert list(vector.as_dict().items()) == [
        ("bm25", 1.0),
        ("recency", None),
        ("source_type", 0.5),
        ("peer_reviewed", None),
        ("open_access", None),
        ("citations", None),
        ("provider_agreement", 0.0),
    ]


# --------------------------------------------------------------------------------------------
# The weight table
# --------------------------------------------------------------------------------------------


def test_score_config_in_the_repository_loads() -> None:
    """The committed table itself: it loads, and weighs exactly the seven features."""
    config = load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH)

    assert set(config.weights.model_dump()) == set(FEATURE_NAMES)
    assert set(config.source_type_values) == set(SourceType)


def test_score_config_path_is_the_committed_table() -> None:
    assert FEDERATED_RANKING_CONFIG_PATH.as_posix() == "config/federated_ranking.yaml"


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("  citations: 0.2\n", "", "weights.citations"),
        ("  citations: 0.2\n", "  citations: 0.2\n  credibility: 0.5\n", "weights.credibility"),
        ("  recency: 0.3\n", "  recency: -0.3\n", "weights.recency"),
        ("  b: 0.75\n", "  b: 1.5\n", "bm25.b"),
        ("  k1: 1.2\n", "  k1: -1\n", "bm25.k1"),
        ("  half_life_days: 90\n", "  half_life_days: 0\n", "recency.half_life_days"),
        ("  saturation: 1000\n", "  saturation: 0\n", "citations.saturation"),
        ("  news: 0.5\n", "", "source_type_values"),
        ("  news: 0.5\n", "  news: 1.5\n", "source_type_values.news"),
        ("  news: 0.5\n", "  news: 0.5\n  example-daily: 0.0\n", "source_type_values.example-daily"),
        ("  max_features: 4\n", "  max_features: 0\n", "explanation.max_features"),
        ("  strong_term_match: 0.6\n", "  strong_term_match: 0\n", "explanation.strong_term_match"),
    ],
    ids=[
        "missing-weight",
        "unknown-weight",
        "negative-weight",
        "b-above-one",
        "negative-k1",
        "zero-half-life",
        "zero-saturation",
        "missing-source-type",
        "source-type-above-one",
        "publisher-as-source-type",
        "explains-nothing",
        "zero-strong-match",
    ],
)
def test_score_config_refuses_a_table_it_could_not_rank_by(old: str, new: str, field: str) -> None:
    assert TEST_CONFIG_TEXT.count(old) == 1
    text = TEST_CONFIG_TEXT.replace(old, new)

    with pytest.raises(InvalidFederatedRankingConfig) as refused:
        parse_federated_ranking_config(text, source="edited.yaml")

    assert refused.value.source == "edited.yaml"
    assert refused.value.field == field


def test_score_config_refuses_weights_that_are_all_zero() -> None:
    weights = "weights:\n" + "".join(f"  {name}: 0\n" for name in FEATURE_NAMES)
    text = weights + TEST_CONFIG_TEXT[TEST_CONFIG_TEXT.index("bm25:\n") :]

    with pytest.raises(InvalidFederatedRankingConfig) as refused:
        parse_federated_ranking_config(text, source="zero.yaml")

    assert refused.value.field == "weights"


def test_score_config_refuses_yaml_it_cannot_read_and_a_file_that_is_not_there(tmp_path: Path) -> None:
    with pytest.raises(InvalidFederatedRankingConfig, match="not valid YAML"):
        parse_federated_ranking_config("weights: [unclosed", source="broken.yaml")
    with pytest.raises(InvalidFederatedRankingConfig, match="a mapping"):
        parse_federated_ranking_config("- just\n- a list\n", source="list.yaml")
    with pytest.raises(InvalidFederatedRankingConfig, match="could not be read"):
        load_federated_ranking_config(tmp_path / "absent.yaml")


# --------------------------------------------------------------------------------------------
# The score (ac1, ac2)
# --------------------------------------------------------------------------------------------

STUDY_OPENALEX = record(
    provider="openalex",
    title="Carbon tax and emissions",
    url="https://openalex.org/W1",
    published_at=NOW - timedelta(days=90),
    open_access_url="https://repository.example.edu/carbon-tax.pdf",
    doi="10.1000/carbon.1",
)
STUDY_CROSSREF = record(
    provider="crossref",
    title="Carbon tax and emissions",
    url="https://doi.org/10.1000/carbon.1",
    published_at=NOW - timedelta(days=90),
    doi="10.1000/carbon.1",
)
STUDY = merged(STUDY_OPENALEX, STUDY_CROSSREF)
"""Two providers, 90 days old, scholarly, with an open copy: every term of the query in its title."""

STORY = one(
    provider="rss",
    title="Wind power subsidies",
    url="https://news.example.com/wind",
    source_type=SourceType.NEWS,
)
"""One provider, undated, news, no open copy, and none of the query's terms."""


def test_score_is_the_sum_of_weight_times_value_over_what_is_known() -> None:
    study, story = rank([STORY, STUDY])

    assert study.candidate is STUDY
    assert study.features == {
        "bm25": 1.0,
        "recency": pytest.approx(0.5),
        "source_type": 1.0,
        "peer_reviewed": None,
        "open_access": 1.0,
        "citations": None,
        "provider_agreement": 1.0,
    }
    assert study.contributions == pytest.approx(
        {
            "bm25": 0.5,
            "recency": 0.15,
            "source_type": 0.1,
            "peer_reviewed": 0.0,
            "open_access": 0.05,
            "citations": 0.0,
            "provider_agreement": 0.05,
        }
    )
    assert study.total_score == pytest.approx(0.85)
    assert story.features == {
        "bm25": 0.0,
        "recency": None,
        "source_type": 0.5,
        "peer_reviewed": None,
        "open_access": None,
        "citations": None,
        "provider_agreement": 0.0,
    }
    assert story.total_score == pytest.approx(0.05)


def test_score_keeps_the_raw_bm25_as_the_lexical_score() -> None:
    study, story = rank([STUDY, STORY])
    # Two documents of 4 and 3 tokens (average 3.5); "carbon" and "tax" each in one of them.
    idf = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))

    assert study.lexical_score == pytest.approx(2 * okapi(1, 4, 3.5, idf))
    assert story.lexical_score == 0.0


def test_score_bm25_is_unknown_when_the_query_has_no_terms() -> None:
    (study,) = rank([STUDY], query="!!!")

    assert study.features["bm25"] is None
    assert study.lexical_score is None
    assert study.contributions["bm25"] == 0.0


def test_score_reads_every_expanded_query() -> None:
    wind = one(title="Offshore wind leasing", url="https://example.org/wind")
    carbon = one(title="Carbon pricing", url="https://example.org/carbon")

    wind_only = rank([carbon, wind], query="offshore wind", config=only_weight("bm25"))
    both = rank([carbon, wind], query=["carbon", "offshore wind"], config=only_weight("bm25"))

    assert [entry.features["bm25"] for entry in wind_only] == [1.0, 0.0]
    assert titles(wind_only) == ["Offshore wind leasing", "Carbon pricing"]
    for entry in both:
        bm25 = entry.features["bm25"]
        assert bm25 is not None and bm25 > 0, entry.candidate.title


def test_score_unknown_values_contribute_nothing() -> None:
    (story,) = rank([STORY])

    for name in ("recency", "peer_reviewed", "open_access", "citations"):
        assert story.features[name] is None
        assert story.contributions[name] == 0.0


def test_score_ranks_by_total_score_descending_and_numbers_the_ranks_from_one() -> None:
    middling = one(title="Carbon pricing in practice", url="https://example.org/middling")

    ranked = rank([STORY, middling, STUDY])

    assert [entry.rank for entry in ranked] == [1, 2, 3]
    assert titles(ranked) == [
        "Carbon tax and emissions",
        "Carbon pricing in practice",
        "Wind power subsidies",
    ]
    assert ranked[0].total_score > ranked[1].total_score > ranked[2].total_score


def tied(**fields: object) -> MergedCandidate:
    """A news story that scores the same as every other `tied` story under `TIE_CONFIG`."""
    return one(title="Senate passes stopgap budget", source_type=SourceType.NEWS, provider="rss", **fields)  # type: ignore[arg-type]


TIE_CONFIG = config_with(weights={**dict.fromkeys(FEATURE_NAMES, 0.0), "bm25": 1.0, "source_type": 1.0})
"""Recency weighs nothing, so stories differing only in date and URL tie on score."""


def test_score_ties_break_by_published_at_newest_first_with_undated_last() -> None:
    older = tied(url="https://a.example.com/1", published_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = tied(url="https://b.example.com/2", published_at=datetime(2026, 3, 1, tzinfo=UTC))
    undated = tied(url="https://0.example.com/3")

    ranked = rank([older, undated, newer], query="senate budget", config=TIE_CONFIG)

    assert len({entry.total_score for entry in ranked}) == 1
    assert urls(ranked) == ["https://b.example.com/2", "https://a.example.com/1", "https://0.example.com/3"]


def test_score_ties_then_break_by_canonical_url_ascending() -> None:
    day = datetime(2026, 10, 14, tzinfo=UTC)
    # The URL sorts last, but the canonical URL the provider gave sorts first.
    by_canonical = tied(
        url="https://z.example.com/q?utm_source=feed",
        canonical_url="https://a.example.com/q",
        published_at=day,
    )
    plain = tied(url="https://m.example.com/q", published_at=day)

    ranked = rank([plain, by_canonical], query="senate budget", config=TIE_CONFIG)

    assert [entry.candidate.canonical_url for entry in ranked] == [
        "https://a.example.com/q",
        "https://m.example.com/q",
    ]


def test_score_ties_fall_back_to_the_url_when_there_is_no_canonical_form() -> None:
    day = datetime(2026, 10, 14, tzinfo=UTC)
    no_canonical_form = tied(url="https://z.example.com/q", published_at=day)
    no_canonical_form = no_canonical_form.evolve(
        canonical_url=None,
        field_sources={
            key: value for key, value in no_canonical_form.field_sources.items() if key != "canonical_url"
        },
    )
    canonical = tied(url="https://m.example.com/q", published_at=day)

    ranked = rank([no_canonical_form, canonical], query="senate budget", config=TIE_CONFIG)

    assert urls(ranked) == ["https://m.example.com/q", "https://z.example.com/q"]


def test_score_identical_inputs_and_config_give_identical_order_whatever_the_input_order() -> None:
    day = datetime(2026, 10, 14, tzinfo=UTC)
    candidates = [
        STUDY,
        STORY,
        tied(url="https://b.example.com/1", published_at=day),
        tied(url="https://a.example.com/2", published_at=day),
        tied(url="https://c.example.com/3"),
        one(title="Carbon tax incidence", url="https://example.org/incidence", published_at=day),
    ]

    first = rank(candidates)
    again = rank(candidates)
    reversed_input = rank(list(reversed(candidates)))

    assert first == again
    assert urls(reversed_input) == urls(first)


def test_score_never_reads_the_publication_or_the_site() -> None:
    """No publisher list: two results that differ only in outlet and host score the same."""
    day = datetime(2026, 10, 14, tzinfo=UTC)
    daily = tied(url="https://daily.example.com/q", publication="The Example Daily", published_at=day)
    times = tied(url="https://times.example.net/q", publication="Sample Times", published_at=day)

    first, second = rank([daily, times], query="senate budget")

    assert first.total_score == second.total_score
    assert first.features == second.features


def test_score_applies_the_source_types_filter() -> None:
    ranked = rank([STUDY, STORY], filters=SearchFilters(source_types=(SourceType.NEWS,)))

    assert titles(ranked) == ["Wind power subsidies"]
    assert ranked[0].rank == 1


def test_score_keeps_every_source_type_when_the_filter_is_empty() -> None:
    assert len(rank([STUDY, STORY], filters=SearchFilters(source_types=()))) == 2


def test_score_keeps_at_most_max_results() -> None:
    middling = one(title="Carbon pricing in practice", url="https://example.org/middling")

    ranked = rank([STORY, middling, STUDY], filters=SearchFilters(max_results=2))

    assert titles(ranked) == ["Carbon tax and emissions", "Carbon pricing in practice"]


def test_score_bm25_is_computed_over_the_filtered_set() -> None:
    """The filtered-out study does not set the scale: the best story left scores 1."""
    relevant_story = one(
        provider="rss",
        title="Carbon tax vote delayed",
        url="https://news.example.com/carbon",
        source_type=SourceType.NEWS,
    )

    (story, _) = rank([STUDY, relevant_story, STORY], filters=SearchFilters(source_types=(SourceType.NEWS,)))

    assert story.features["bm25"] == 1.0


def test_score_recency_is_measured_from_the_end_of_the_window_when_there_is_one() -> None:
    window = SearchFilters(since=datetime(2026, 10, 1, tzinfo=UTC), until=datetime(2026, 10, 11, tzinfo=UTC))
    mid_window = one(published_at=datetime(2026, 10, 6, tzinfo=UTC))

    (in_window,) = rank([mid_window], filters=window)
    (no_window,) = rank([mid_window])

    assert in_window.features["recency"] == pytest.approx(0.5)
    # 16.5 days from midnight on 6 October to noon on 22 October.
    assert no_window.features["recency"] == pytest.approx(0.5 ** (16.5 / 90))


def test_score_changing_a_weight_in_the_yaml_changes_the_order_without_code_changes(tmp_path: Path) -> None:
    """ac3, against the committed table: one edited line in a copy of it reverses two results."""
    on_topic_but_old = one(
        title="Carbon tax and emissions",
        url="https://example.org/old",
        published_at=NOW - timedelta(days=1100),
    )
    partly_on_topic_but_new = one(
        title="Carbon markets this week", url="https://example.org/new", published_at=NOW
    )
    committed = (REPOSITORY / FEDERATED_RANKING_CONFIG_PATH).read_text(encoding="utf-8")
    assert committed.count("\n  recency: 0.15\n") == 1
    edited = tmp_path / "federated_ranking.yaml"
    edited.write_text(committed.replace("\n  recency: 0.15\n", "\n  recency: 0.6\n"), encoding="utf-8")
    candidates = [partly_on_topic_but_new, on_topic_but_old]

    as_committed = rank(
        candidates, config=load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH)
    )
    as_edited = rank(candidates, config=load_federated_ranking_config(edited))

    assert urls(as_committed) == ["https://example.org/old", "https://example.org/new"]
    assert urls(as_edited) == ["https://example.org/new", "https://example.org/old"]


# --------------------------------------------------------------------------------------------
# The stored record (ac1)
# --------------------------------------------------------------------------------------------


def test_score_search_result_for_carries_rank_scores_the_vector_the_explanation_and_providers() -> None:
    study, _ = rank([STUDY, STORY])

    result = search_result_for(study, search_id=readable_id("SRCH"), article_id=readable_id("ART", 7))

    assert result.search_id == readable_id("SRCH")
    assert result.article_id == readable_id("ART", 7)
    assert result.rank == 1
    assert result.total_score == study.total_score
    assert result.lexical_score == study.lexical_score
    assert result.semantic_score is None
    assert result.rerank_score is None
    assert result.source_quality_features == study.features
    assert list(result.source_quality_features) == list(FEATURE_NAMES)
    assert result.source_quality_features["peer_reviewed"] is None
    assert result.explanation == study.explanation
    assert result.providers == ("openalex", "crossref")


def test_score_search_result_for_a_stored_ranking_comes_back_as_built() -> None:
    repository = InMemorySearchRepository()
    ranked = rank([STUDY, STORY])

    async def store_and_reload() -> tuple[object, ...]:
        search = await repository.save(build_search(search_id=readable_id("SRCH")))
        results = [
            search_result_for(entry, search_id=search.search_id, article_id=readable_id("ART", entry.rank))
            for entry in ranked
        ]
        await repository.save_results(search.search_id, results)
        return (tuple(results), await repository.list_results(search.search_id))

    built, stored = asyncio.run(store_and_reload())

    assert stored == built


def test_score_ranked_candidate_names_exactly_the_seven() -> None:
    (study,) = rank([STUDY])

    with pytest.raises(ValueError, match="features"):
        study.evolve(features={**study.features, "credibility": 1.0})
    with pytest.raises(ValueError, match="contributions"):
        study.evolve(contributions={name: 0.0 for name in FEATURE_NAMES if name != "bm25"})


# --------------------------------------------------------------------------------------------
# Explanations
# --------------------------------------------------------------------------------------------


def test_explain_names_the_largest_contributions_largest_first() -> None:
    study, _ = rank([STUDY, STORY])

    # bm25 0.5, recency 0.15, source type 0.1, then open access and agreement tie at 0.05 and the
    # earlier feature wins; four are named.
    assert study.explanation == "strong term match, published 3 months ago, scholarly source, open access"


def test_explain_says_nothing_about_what_is_unknown() -> None:
    """Undated, peer review unknown, no open copy: none of them is mentioned (PM, 2026-10-22)."""
    _, story = rank([STUDY, STORY])

    assert story.explanation == "news source"
    for entry in rank([STUDY, STORY]):
        assert "peer" not in entry.explanation
    assert "recent" not in story.explanation
    assert "published" not in story.explanation


def test_explain_says_so_when_nothing_contributed() -> None:
    nothing = one(title="Wind power subsidies", source_type=SourceType.OTHER)

    (entry,) = rank([nothing], answered=1)

    assert entry.explanation == "no feature contributed to the score"


def test_explain_names_at_most_the_configured_number() -> None:
    two = config_with(explanation={"max_features": 2, "strong_term_match": 0.6})

    study, _ = rank([STUDY, STORY], config=two)

    assert study.explanation == "strong term match, published 3 months ago"


@pytest.mark.parametrize(
    ("days_old", "phrase"),
    [
        (0, "recent (today)"),
        (1, "recent (1 day)"),
        (3, "recent (3 days)"),
        (59, "recent (59 days)"),
        (60, "published 2 months ago"),
        (729, "published 24 months ago"),
        (730, "published 2 years ago"),
    ],
)
def test_explain_recency_phrase(days_old: int, phrase: str) -> None:
    (entry,) = rank(
        [one(published_at=NOW - timedelta(days=days_old, hours=1))], config=only_weight("recency")
    )

    assert entry.explanation == phrase


def test_explain_term_match_is_strong_above_the_threshold_and_some_below_it() -> None:
    full = one(title="Carbon tax", url="https://example.org/full")
    half = one(title="Carbon dividends explained in full detail", url="https://example.org/half")

    strong, some = rank([half, full], config=only_weight("bm25"))

    assert strong.explanation == "strong term match"
    assert some.features["bm25"] is not None and some.features["bm25"] < 0.6
    assert some.explanation == "some term match"


@pytest.mark.parametrize(
    ("source_type", "phrase"),
    [
        (SourceType.SCHOLARLY, "scholarly source"),
        (SourceType.GOVERNMENT, "government source"),
        (SourceType.THINK_TANK, "think-tank source"),
        (SourceType.NEWS, "news source"),
    ],
)
def test_explain_source_type_phrase(source_type: SourceType, phrase: str) -> None:
    (entry,) = rank([one(source_type=source_type)], config=only_weight("source_type"))

    assert entry.explanation == phrase


def test_explain_open_access_and_agreement_phrases() -> None:
    (open_copy,) = rank(
        [one(open_access_url="https://repository.example.edu/a.pdf")], config=only_weight("open_access")
    )
    (agreed,) = rank([STUDY], answered=3, config=only_weight("provider_agreement"))

    assert open_copy.explanation == "open access"
    assert agreed.explanation == "found by 2 providers"


# --------------------------------------------------------------------------------------------
# The rank stage
# --------------------------------------------------------------------------------------------


def status(provider: str, results: Sequence[CandidateResult] = (), *, failed: bool = False) -> ProviderStatus:
    query = ProviderQuery(query="carbon tax")
    if failed:
        return ProviderStatus(
            provider=provider, query=query, outcome=ProviderOutcome.TIMEOUT, elapsed_ms=1.0, error="timed out"
        )
    return ProviderStatus(
        provider=provider,
        query=query,
        outcome=ProviderOutcome.OK,
        elapsed_ms=1.0,
        response=ProviderResponse(provider=provider, results=tuple(results), elapsed_ms=1.0),
    )


def state_with(
    merged_candidates: Sequence[MergedCandidate],
    statuses: Sequence[ProviderStatus],
    *,
    filters: SearchFilters | None = None,
) -> SearchState:
    request = SearchRequest(query="carbon tax", filters=SearchFilters() if filters is None else filters)
    return SearchState.start(readable_id("SRCH"), request).evolve(
        provider_statuses=tuple(statuses),
        candidates=tuple(member for candidate in merged_candidates for member in candidate.members),
        merged_candidates=tuple(merged_candidates),
    )


def test_the_rank_stage_ranks_the_merged_candidates_and_leaves_everything_else_alone() -> None:
    statuses = [
        status("openalex", [STUDY_OPENALEX]),
        status("crossref", [STUDY_CROSSREF]),
        status("rss", STORY.members),
    ]
    state = state_with([STORY, STUDY], statuses)

    after = asyncio.run(FederatedRankStage(TEST_CONFIG, clock=FixedClock(NOW)).run(state))

    assert [entry.candidate for entry in after.ranked_candidates] == [STUDY, STORY]
    assert after.ranked_candidates == rank([STORY, STUDY], answered=3)
    assert after.provider_statuses is state.provider_statuses
    assert after.candidates is state.candidates
    assert after.merged_candidates is state.merged_candidates
    assert after.queries is state.queries
    assert after.results == ()


def test_the_rank_stage_counts_only_the_providers_that_answered() -> None:
    statuses = [
        status("openalex", [STUDY_OPENALEX]),
        status("crossref", [STUDY_CROSSREF]),
        status("semantic_scholar", failed=True),
        status("openalex", [STUDY_OPENALEX]),
    ]

    after = asyncio.run(
        FederatedRankStage(TEST_CONFIG, clock=FixedClock(NOW)).run(state_with([STUDY], statuses))
    )

    assert after.ranked_candidates[0].features["provider_agreement"] == 1.0


def test_the_rank_stage_reads_the_clock_for_recency_and_the_window_when_there_is_one() -> None:
    study = one(published_at=NOW - timedelta(days=90))
    window = SearchFilters(since=NOW - timedelta(days=100), until=NOW - timedelta(days=50))

    (dated,) = asyncio.run(
        FederatedRankStage(TEST_CONFIG, clock=FixedClock(NOW)).run(state_with([study], [status("openalex")]))
    ).ranked_candidates
    (windowed,) = asyncio.run(
        FederatedRankStage(TEST_CONFIG, clock=FixedClock(NOW)).run(
            state_with([study], [status("openalex")], filters=window)
        )
    ).ranked_candidates

    assert dated.features["recency"] == pytest.approx(0.5)
    assert windowed.features["recency"] == pytest.approx(0.2)


class ProvidersOnHand:
    """The `DiscoveryProviders` port over providers given directly, with no health to report."""

    def __init__(self, *providers: SearchProvider) -> None:
        self._providers = providers

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


class Recording:
    """Runs a stage and keeps the state it returned."""

    def __init__(self, stage: FederatedRankStage) -> None:
        self._stage = stage
        self.returned: list[SearchState] = []

    async def run(self, state: SearchState) -> SearchState:
        after = await self._stage.run(state)
        self.returned.append(after)
        return after


def test_the_rank_stage_plugs_into_the_rank_slot_after_deduplication() -> None:
    providers = ProvidersOnHand(
        FakeSearchProvider("openalex", default_results=(STUDY_OPENALEX,)),
        FakeSearchProvider("crossref", default_results=(STUDY_CROSSREF,)),
        FakeSearchProvider("rss", default_results=STORY.members),
    )
    rank_stage = Recording(FederatedRankStage(TEST_CONFIG, clock=FixedClock(NOW)))
    service = FederatedSearchService(
        providers,
        InMemorySearchRepository(),
        clock=EventLoopClock(),
        ids=SequentialIdGenerator("SRCH"),
        normalize=DedupeStage(),
        rank=rank_stage,
    )

    outcome = run_in_virtual_time(service.search(SearchRequest(query="carbon tax")))

    (state,) = rank_stage.returned
    assert titles(state.ranked_candidates) == ["Carbon tax and emissions", "Wind power subsidies"]
    assert state.ranked_candidates[0].candidate.providers == ("openalex", "crossref")
    assert outcome.results == ()


def test_the_rank_stage_repr_names_no_weights() -> None:
    assert repr(FederatedRankStage(TEST_CONFIG, clock=FixedClock(NOW))) == "FederatedRankStage()"


# --------------------------------------------------------------------------------------------
# The forbidden list: no model call, no network, no weight in Python
# --------------------------------------------------------------------------------------------


def test_ranking_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("ranking tried to use the network")

    refusal: Callable[..., None] = refuse
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, refusal)

    assert rank([STUDY, STORY])


@pytest.mark.parametrize("module", [federated_ranking, federated_ranking_features])
def test_the_ranking_modules_import_no_model_router_and_no_network_client(module: object) -> None:
    source = Path(str(getattr(module, "__file__", ""))).read_text(encoding="utf-8")

    for client in ("httpx", "urllib.request", "requests", "socket", "aiohttp"):
        assert f"import {client}" not in source, client
        assert f"from {client}" not in source, client
    assert "ModelRouter" not in source
    assert "debate_core.integrations" not in source


@pytest.mark.parametrize("module", [federated_ranking, federated_ranking_features])
def test_the_ranking_modules_hold_no_weight_of_their_own(module: object) -> None:
    """Every number the ranking uses comes from the table: no float literal in either module."""
    import ast

    tree = ast.parse(Path(str(getattr(module, "__file__", ""))).read_text(encoding="utf-8"))
    floats = sorted(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, float)
        and node.value not in (0.0, 0.5, 1.0)
    )

    assert floats == []


# --------------------------------------------------------------------------------------------
# The coach-labelled relevance check (ac4)
# --------------------------------------------------------------------------------------------

RELEVANCE_FIXTURE = REPOSITORY / "tests" / "fixtures" / "federated_ranking" / "labeled_queries.json"


class LabelledRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    item: str
    record: CandidateResult


class LabelledQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    format: str
    query: str
    records: tuple[LabelledRecord, ...]
    relevant: tuple[str, ...] | None


class LabelledQueries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str
    now: datetime
    labelled_by: str | None
    labelled_on: str | None
    queries: tuple[LabelledQuery, ...]


def labelled_queries() -> LabelledQueries:
    return LabelledQueries.model_validate_json(RELEVANCE_FIXTURE.read_text(encoding="utf-8"))


def ndcg_at_10(order: Sequence[str], relevant: set[str]) -> float:
    """Binary-gain nDCG@10: each relevant item in the first ten gains 1 / log2(position + 1)."""
    gained = sum(
        1 / math.log2(position + 1) for position, item in enumerate(order[:10], start=1) if item in relevant
    )
    ideal = sum(1 / math.log2(position + 1) for position in range(1, min(len(relevant), 10) + 1))
    return gained / ideal if ideal else 0.0


def test_relevance_ndcg_at_10_by_hand() -> None:
    assert ndcg_at_10(["a", "b", "c"], {"a"}) == 1.0
    assert ndcg_at_10(["a", "b", "c"], {"b"}) == pytest.approx(1 / math.log2(3))
    assert ndcg_at_10(["a", "b", "c"], {"a", "c"}) == pytest.approx((1 + 1 / 2) / (1 + 1 / math.log2(3)))
    assert ndcg_at_10([str(n) for n in range(12)], {"11"}) == 0.0
    assert ndcg_at_10(["a"], set()) == 0.0


def test_relevance_fixture_has_three_labelled_queries_one_per_format() -> None:
    fixture = labelled_queries()

    assert [query.format for query in fixture.queries] == ["Policy", "LD", "PF"]
    assert fixture.labelled_by is not None, "the coach has not labelled labelling_sheet.md yet"
    for query in fixture.queries:
        items = {entry.item for entry in query.records}
        assert query.relevant is not None, f"{query.id} is not labelled yet"
        assert set(query.relevant) <= items, query.id


def raw_and_ranked(query: LabelledQuery, now: datetime) -> tuple[list[str], list[str]]:
    """The items in raw provider order (merged, first appearance) and in the committed table's order."""
    item_of = {id(entry.record): entry.item for entry in query.records}
    merged_candidates = merge_candidates([entry.record for entry in query.records])
    raw = [item_of[id(candidate.members[0])] for candidate in merged_candidates]
    ranked = rank_merged_candidates(
        merged_candidates,
        queries=(query.query,),
        filters=SearchFilters(max_results=200),
        answered_providers=len({entry.record.provider for entry in query.records}),
        now=now,
        config=load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH),
    )
    return raw, [item_of[id(entry.candidate.members[0])] for entry in ranked]


def test_relevance_ranking_puts_relevant_items_in_the_top_10_at_least_as_well_as_provider_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ac4: mean nDCG@10 over the three coach-labelled queries is not lower than raw provider order."""
    fixture = labelled_queries()
    raw_scores: list[float] = []
    ranked_scores: list[float] = []
    for query in fixture.queries:
        assert query.relevant is not None, f"{query.id} is not labelled yet"
        relevant = set(query.relevant)
        raw, ranked = raw_and_ranked(query, fixture.now)
        assert sorted(raw) == sorted(ranked), query.id
        raw_scores.append(ndcg_at_10(raw, relevant))
        ranked_scores.append(ndcg_at_10(ranked, relevant))
        with capsys.disabled():
            print(
                f"\n{query.id}: {len(relevant)} of {len(raw)} relevant; nDCG@10 raw "
                f"{raw_scores[-1]:.3f}, ranked {ranked_scores[-1]:.3f}"
            )
    raw_mean, ranked_mean = sum(raw_scores) / 3, sum(ranked_scores) / 3
    with capsys.disabled():
        print(f"mean nDCG@10: raw {raw_mean:.3f}, ranked {ranked_mean:.3f}")

    assert ranked_mean >= raw_mean

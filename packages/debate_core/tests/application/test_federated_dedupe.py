"""Federated deduplication: exact keys, the fuzzy title rule and its gates, field precedence, the stage.

Every expected value here is written out by hand (working agreement 6): the merged record the three
providers' descriptions of one paper should produce, the provider each merged field should come from,
and in `tests/fixtures/dedupe/pairs.json` whether each labelled pair is one source or two. None of it
was produced by running the code under test.

The spec's plan nodes select these tests by name: `-k exact` for DOI, canonical URL and provider-id
matching, `-k labeled` for the labelled pairs, and the whole file for the rest.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from debate_core.application import federated_dedupe
from debate_core.application.federated_dedupe import (
    FIELD_PRECEDENCE,
    MERGED_FIELDS,
    DedupeStage,
    MatchRule,
    MergedCandidate,
    merge_candidates,
    merge_group,
    surname_key,
    title_tokens,
    titles_agree,
)
from debate_core.application.federated_search import FederatedSearchService
from debate_core.application.federated_search_types import SearchRequest, SearchState
from debate_core.application.ports import SearchProvider
from debate_core.application.settings import SearchProviderName
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult, ProviderHealth
from debate_core.domain.enums import SourceType
from debate_core.testing.fakes import FakeSearchProvider, InMemorySearchRepository, SequentialIdGenerator
from debate_core.testing.virtual_time import EventLoopClock, run_in_virtual_time

FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "dedupe"


def at(year: int, month: int = 1, day: int = 1, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def paper(
    *,
    provider: str = "openalex",
    title: str = "Glacier retreat and downstream water security",
    url: str = "https://openalex.org/W1000000001",
    authors: tuple[str, ...] = ("Ana Rivera",),
    published_at: datetime | None = None,
    source_type: SourceType = SourceType.SCHOLARLY,
    identifiers: ArticleIdentifiers | None = None,
    canonical_url: str | None = None,
) -> CandidateResult:
    """A scholarly record with no identifiers unless given: what the fuzzy rule has to work with."""
    return CandidateResult(
        provider=provider,
        title=title,
        url=url,
        canonical_url=canonical_url,
        authors=authors,
        published_at=at(2024, 3) if published_at is None else published_at,
        source_type=source_type,
        identifiers=ArticleIdentifiers() if identifiers is None else identifiers,
    )


def story(
    *,
    provider: str = "rss",
    title: str = "Senate passes stopgap budget to avert shutdown",
    url: str = "https://www.example-news.com/2026/10/14/senate-stopgap",
    authors: tuple[str, ...] = ("Jordan Lee",),
    published_at: datetime | None = None,
) -> CandidateResult:
    """A news record: no identifiers, as feeds give none."""
    return CandidateResult(
        provider=provider,
        title=title,
        url=url,
        authors=authors,
        published_at=at(2026, 10, 14, 9) if published_at is None else published_at,
        source_type=SourceType.NEWS,
    )


def groups(candidates: Sequence[CandidateResult]) -> list[list[int]]:
    """Which input positions each merged candidate holds, in output order."""
    position = {id(candidate): index for index, candidate in enumerate(candidates)}
    return [[position[id(member)] for member in merged.members] for merged in merge_candidates(candidates)]


# --------------------------------------------------------------------------------------------
# The same paper from three providers (ac1)
# --------------------------------------------------------------------------------------------


class _CandidateFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str
    candidates: tuple[CandidateResult, ...]


def test_exact_the_same_paper_from_openalex_crossref_and_semantic_scholar_is_one_merged_candidate() -> None:
    fixture = (FIXTURES / "one_paper_three_providers.json").read_text(encoding="utf-8")
    openalex, crossref, semantic_scholar = _CandidateFile.model_validate_json(fixture).candidates

    (merged,) = merge_candidates((openalex, crossref, semantic_scholar))

    assert merged.providers == ("openalex", "crossref", "semantic_scholar")
    assert merged.members == (openalex, crossref, semantic_scholar)
    assert merged.matched_on == (MatchRule.DOI,)
    assert merged.title == "Glacier Retreat and Downstream Water Security in High Mountain Asia"
    assert merged.url == "https://doi.org/10.1126/science.adj1234"
    assert merged.canonical_url == "https://doi.org/10.1126/science.adj1234"
    assert merged.identifiers == ArticleIdentifiers(
        doi="10.1126/science.adj1234",
        pmid="38123456",
        openalex_id="W4390012345",
        semantic_scholar_id="9f8e7d6c5b4a39281706f5e4d3c2b1a098765432",
    )
    assert merged.source_type is SourceType.SCHOLARLY
    assert merged.authors == ("Sherpa, Tenzing", "Rivera, Ana", "Chen, Wei")
    assert merged.publication == "Science"
    assert merged.published_at == at(2024, 1, 11)
    assert merged.snippet == (
        "Glaciers in High Mountain Asia lost mass faster between 2000 and 2023 than in any comparable "
        "period on record."
    )
    assert merged.open_access_url == "https://europepmc.org/articles/PMC10789012"
    assert merged.field_sources == {
        "title": "crossref",
        "url": "crossref",
        "canonical_url": "crossref",
        "identifiers.doi": "crossref",
        "identifiers.pmid": "openalex",
        "identifiers.openalex_id": "openalex",
        "identifiers.semantic_scholar_id": "semantic_scholar",
        "source_type": "crossref",
        "authors": "crossref",
        "publication": "crossref",
        "published_at": "crossref",
        "snippet": "openalex",
        "open_access_url": "openalex",
    }


# --------------------------------------------------------------------------------------------
# Exact keys: DOI, canonical URL, provider ids
# --------------------------------------------------------------------------------------------


def test_exact_doi_merges_records_that_spell_it_differently_and_disagree_on_everything_else() -> None:
    bare = paper(provider="openalex", identifiers=ArticleIdentifiers(doi="10.1038/s41558-021-01001-1"))
    resolver = paper(
        provider="crossref",
        title="Methane emissions from thawing permafrost",
        url="https://doi.org/10.1038/s41558-021-01001-1",
        authors=("Okafor, James",),
        published_at=at(2019, 12, 20),
        identifiers=ArticleIdentifiers(doi="https://doi.org/10.1038/S41558-021-01001-1"),
    )

    (merged,) = merge_candidates((bare, resolver))

    assert merged.matched_on == (MatchRule.DOI,)


def test_exact_canonical_url_merges_a_story_shared_with_utm_parameters_and_an_amp_path() -> None:
    """ac2: one story, from the publisher's feed, a utm-tagged share and its AMP page."""
    published = story(url="https://www.example-news.com/2026/10/14/senate-stopgap", authors=())
    tracked = story(
        provider="gdelt",
        title="Senate passes stopgap budget",
        url="https://www.example-news.com/2026/10/14/senate-stopgap?utm_source=twitter&utm_medium=social",
        authors=(),
    )
    amp = story(
        provider="gdelt", url="https://www.example-news.com/amp/2026/10/14/senate-stopgap", authors=()
    )

    (merged,) = merge_candidates((published, tracked, amp))

    assert merged.matched_on == (MatchRule.CANONICAL_URL,)
    assert merged.canonical_url == "https://www.example-news.com/2026/10/14/senate-stopgap"
    assert merged.providers == ("rss", "gdelt")


def test_exact_canonical_url_takes_the_providers_canonical_url_when_it_gave_one() -> None:
    redirect = story(url="https://feeds.example-news.com/r/12345", authors=())
    with_canonical = redirect.evolve(canonical_url="https://www.example-news.com/2026/10/14/senate-stopgap")
    plain = story(provider="gdelt", url="https://www.example-news.com/2026/10/14/senate-stopgap", authors=())

    assert groups((with_canonical, plain)) == [[0, 1]]
    assert groups((redirect, plain)) == [[0], [1]]


def test_exact_canonical_url_of_a_sites_front_page_is_not_a_key() -> None:
    storm = story(
        title="Storm closes schools across the county", url="https://www.example-news.com/", authors=()
    )
    levy = story(
        title="City council approves transit levy",
        url="https://www.example-news.com/?utm_source=rss",
        authors=(),
    )

    assert groups((storm, levy)) == [[0], [1]]


def test_exact_canonical_url_with_a_path_below_the_front_page_is_a_key() -> None:
    section = story(url="https://www.example-news.com/politics", authors=())
    same_section = story(
        provider="gdelt", url="https://www.example-news.com/politics?utm_source=x", authors=()
    )

    assert groups((section, same_section)) == [[0, 1]]


def test_exact_provider_ids_link_records_by_pmid() -> None:
    openalex = paper(provider="openalex", identifiers=ArticleIdentifiers(pmid="34567890", openalex_id="W1"))
    semantic_scholar = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/abc",
        title="A different title entirely",
        identifiers=ArticleIdentifiers(pmid="34567890", semantic_scholar_id="abc"),
    )

    (merged,) = merge_candidates((openalex, semantic_scholar))

    assert merged.matched_on == (MatchRule.PROVIDER_ID,)


def test_exact_provider_ids_link_arxiv_ids_whatever_their_version_suffix_or_prefix() -> None:
    plain = paper(provider="openalex", identifiers=ArticleIdentifiers(arxiv_id="2310.01234"))
    versioned = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/def",
        title="Unrelated wording",
        identifiers=ArticleIdentifiers(arxiv_id="arXiv:2310.01234v2"),
    )

    assert groups((plain, versioned)) == [[0, 1]]


def test_exact_provider_ids_link_openalex_and_semantic_scholar_ids_in_any_spelling() -> None:
    first = paper(identifiers=ArticleIdentifiers(openalex_id="https://openalex.org/W4390012345"))
    again = paper(
        url="https://openalex.org/works/other",
        title="Unrelated wording",
        identifiers=ArticleIdentifiers(openalex_id="w4390012345"),
    )
    s2 = paper(provider="semantic_scholar", identifiers=ArticleIdentifiers(semantic_scholar_id="ABCDEF12"))
    s2_again = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/x",
        title="Other wording",
        identifiers=ArticleIdentifiers(semantic_scholar_id="abcdef12"),
    )

    assert groups((first, again)) == [[0, 1]]
    assert groups((s2, s2_again)) == [[0, 1]]


def test_exact_keys_chain_one_record_to_the_next() -> None:
    """Crossref and OpenAlex share a DOI; OpenAlex and Semantic Scholar share a PMID."""
    crossref = paper(
        provider="crossref", url="https://doi.org/10.5555/x", identifiers=ArticleIdentifiers(doi="10.5555/x")
    )
    openalex = paper(provider="openalex", identifiers=ArticleIdentifiers(doi="10.5555/x", pmid="123"))
    semantic_scholar = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/x",
        title="Other wording",
        identifiers=ArticleIdentifiers(pmid="123"),
    )

    (merged,) = merge_candidates((crossref, openalex, semantic_scholar))

    assert merged.matched_on == (MatchRule.DOI, MatchRule.PROVIDER_ID)
    assert merged.providers == ("crossref", "openalex", "semantic_scholar")


def test_exact_keys_never_merge_records_with_different_dois_even_at_one_url() -> None:
    first = paper(
        url="https://journal.example.org/issue/3.pdf", identifiers=ArticleIdentifiers(doi="10.5555/a")
    )
    second = paper(
        url="https://journal.example.org/issue/3.pdf?utm_source=alerts",
        title="Desalination costs in the Gulf states",
        identifiers=ArticleIdentifiers(doi="10.5555/b"),
    )

    assert groups((first, second)) == [[0], [1]]


@pytest.mark.parametrize(
    ("left", "right"),
    [
        pytest.param(ArticleIdentifiers(pmid="1"), ArticleIdentifiers(pmid="2"), id="pmid"),
        pytest.param(
            ArticleIdentifiers(arxiv_id="2301.00001"), ArticleIdentifiers(arxiv_id="2301.00002"), id="arxiv"
        ),
        pytest.param(
            ArticleIdentifiers(openalex_id="W1"), ArticleIdentifiers(openalex_id="W2"), id="openalex"
        ),
        pytest.param(
            ArticleIdentifiers(semantic_scholar_id="a1"),
            ArticleIdentifiers(semantic_scholar_id="b2"),
            id="s2",
        ),
    ],
)
def test_exact_keys_never_merge_records_that_carry_different_values_of_one_identifier(
    left: ArticleIdentifiers, right: ArticleIdentifiers
) -> None:
    """Same URL, same title, author and year: everything agrees except one identifier, which wins."""
    first = paper(identifiers=left)
    second = paper(identifiers=right)

    assert groups((first, second)) == [[0], [1]]


def test_exact_keys_keep_an_arxiv_preprint_apart_from_the_published_record_that_cross_links_it() -> None:
    published = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/b3c4",
        identifiers=ArticleIdentifiers(doi="10.1126/sciadv.adk1234", arxiv_id="2302.04567"),
    )
    preprint = paper(
        provider="openalex",
        url="https://arxiv.org/abs/2302.04567",
        identifiers=ArticleIdentifiers(arxiv_id="2302.04567"),
    )

    assert groups((published, preprint)) == [[0], [1]]


def test_exact_keys_treat_an_arxiv_doi_and_its_arxiv_id_as_one_preprint() -> None:
    by_doi = paper(identifiers=ArticleIdentifiers(doi="10.48550/arXiv.2302.04567"))
    by_id = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/b3c4",
        title="Other wording",
        identifiers=ArticleIdentifiers(arxiv_id="2302.04567"),
    )

    assert groups((by_doi, by_id)) == [[0, 1]]


def test_exact_keys_merge_the_same_record_returned_for_two_queries() -> None:
    record = paper(identifiers=ArticleIdentifiers(openalex_id="W1"))

    (merged,) = merge_candidates((record, record))

    assert merged.providers == ("openalex",)
    assert merged.members == (record, record)


def test_exact_merged_candidates_come_out_in_the_order_their_first_record_went_in() -> None:
    a = paper(
        url="https://example.org/a",
        title="Arctic sea ice minimum extent",
        identifiers=ArticleIdentifiers(doi="10.5555/a"),
    )
    b = paper(
        url="https://example.org/b",
        title="Permafrost carbon feedback loops",
        identifiers=ArticleIdentifiers(doi="10.5555/b"),
    )
    a_again = paper(
        provider="crossref", url="https://doi.org/10.5555/a", identifiers=ArticleIdentifiers(doi="10.5555/a")
    )

    assert groups((a, b, a_again)) == [[0, 2], [1]]
    assert merge_candidates(()) == ()


# --------------------------------------------------------------------------------------------
# Fuzzy title matching and its gates
# --------------------------------------------------------------------------------------------


def test_fuzzy_title_merges_records_whose_title_first_author_and_year_agree() -> None:
    openalex = paper(
        title="Trade Wars and U.S. Farm Income", authors=("Okafor, James",), published_at=at(2023, 4)
    )
    semantic_scholar = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/3b4c",
        title="Trade wars and US farm income",
        authors=("James Okafor",),
        published_at=at(2023, 11),
    )

    (merged,) = merge_candidates((openalex, semantic_scholar))

    assert merged.matched_on == (MatchRule.TITLE,)


def test_fuzzy_title_needs_the_first_authors_surname_to_agree() -> None:
    """ac2: near-identical headlines by different authors do not merge."""
    one = paper(title="Climate change and armed conflict in East Africa", authors=("Hendrix, Cullen",))
    other = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/91a2",
        title="Climate Change and Armed Conflict in East Africa",
        authors=("Okonjo, Grace",),
    )

    assert groups((one, other)) == [[0], [1]]


def test_fuzzy_title_reads_only_the_first_author() -> None:
    one = paper(authors=("Rivera, Ana", "Okafor, James"))
    swapped = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/1",
        authors=("Okafor, James", "Rivera, Ana"),
    )
    later_authors_differ = paper(
        provider="crossref", url="https://example.org/x", authors=("Ana Rivera", "Wei Chen")
    )

    assert groups((one, swapped)) == [[0], [1]]
    assert groups((one, later_authors_differ)) == [[0, 1]]


def test_fuzzy_title_needs_the_publication_year_to_agree_for_scholarship() -> None:
    one = paper(title="The year in climate science", published_at=at(2024, 12, 18))
    next_year = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/a2b3",
        title="The Year in Climate Science",
        published_at=at(2025, 12, 17),
    )
    same_year = paper(
        provider="semantic_scholar",
        url="https://www.semanticscholar.org/paper/a2b3",
        title="The Year in Climate Science",
        published_at=at(2024, 1, 2),
    )

    assert groups((one, next_year)) == [[0], [1]]
    assert groups((one, same_year)) == [[0, 1]]


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param({"authors": ()}, id="no-author"),
        pytest.param({"published_at": None}, id="no-date"),
        pytest.param({"authors": (), "published_at": None}, id="neither"),
    ],
)
def test_fuzzy_title_never_merges_on_title_alone(missing: dict[str, object]) -> None:
    """The forbidden case: identical titles and nothing else to go on."""
    one = paper()
    other = paper(provider="semantic_scholar", url="https://www.semanticscholar.org/paper/1").evolve(
        **missing
    )

    assert groups((one, other)) == [[0], [1]]
    assert groups((other, one)) == [[0], [1]]


def test_fuzzy_title_outside_scholarship_needs_the_same_site() -> None:
    """The same wire story on two outlets is two sources: a card cites the outlet it was read at."""
    seattle = story(url="https://www.seattletimes.com/nation-world/wildfire-smoke-east-coast/")
    post = story(provider="gdelt", url="https://www.washingtonpost.com/national/wildfire-smoke-east-coast/")
    post_bare_host = story(
        provider="gdelt", url="https://seattletimes.com/nation-world/wildfire-smoke-east-coast"
    )

    assert groups((seattle, post)) == [[0], [1]]
    assert groups((seattle, post_bare_host)) == [[0, 1]]


def test_fuzzy_title_outside_scholarship_needs_the_same_day() -> None:
    election_night = story(title="Live updates: midterm election results", published_at=at(2026, 11, 3, 23))
    morning_after = story(
        title="Live updates: midterm election results",
        url="https://www.example-news.com/live/midterms-day-two",
        published_at=at(2026, 11, 4, 11),
    )
    same_day = story(
        title="Live updates: midterm election results",
        url="https://www.example-news.com/live/midterms",
        published_at=at(2026, 11, 3, 1),
    )

    assert groups((election_night, morning_after)) == [[0], [1]]
    assert groups((election_night, same_day)) == [[0, 1]]


def test_fuzzy_title_keeps_a_paper_apart_from_a_news_piece_with_its_title() -> None:
    study = paper(
        title="Why sea level rise is accelerating along the Gulf Coast", published_at=at(2025, 3, 1)
    )
    explainer = story(
        title="Why sea level rise is accelerating along the Gulf Coast",
        url="https://theconversation.com/why-sea-level-rise-is-accelerating-240001",
        authors=("Ana Rivera",),
        published_at=at(2025, 3, 1, 10),
    )

    assert groups((study, explainer)) == [[0], [1]]


def test_fuzzy_title_never_joins_records_whose_identifiers_say_they_differ() -> None:
    preprint = paper(identifiers=ArticleIdentifiers(doi="10.1101/2025.04.12.648512"))
    published = paper(
        provider="crossref", url="https://doi.org/10.1038/x", identifiers=ArticleIdentifiers(doi="10.1038/x")
    )

    assert groups((preprint, published)) == [[0], [1]]


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Rivera, Ana", "rivera"),
        ("Ana Rivera", "rivera"),
        ("A. Rivera", "rivera"),
        ("Rivera A", "rivera"),
        ("Rivera AM", "rivera"),
        ("RIVERA, ANA", "rivera"),
        ("Ana Rivera Jr.", "rivera"),
        ("Müller, Jonas", "muller"),
        ("Jonas Muller", "muller"),
        ("Hanna-Attisha, Mona", "attisha"),
        ("Mona Hanna-Attisha", "attisha"),
        ("van Beethoven, Ludwig", "beethoven"),
        ("Ludwig van Beethoven", "beethoven"),
        ("G. John Ikenberry", "ikenberry"),
        ("Ikenberry, G. John", "ikenberry"),
        ("World Economic Forum", "forum"),
        ("O'Brien, Siobhan", "obrien"),
        ("  ", None),
        ("A. B.", None),
    ],
)
def test_fuzzy_surname_key_reads_the_surname_in_every_common_name_format(name: str, key: str | None) -> None:
    assert surname_key(name) == key


@pytest.mark.parametrize(
    ("left", "right"),
    [
        pytest.param(
            "Trade Wars and U.S. Farm Income", "Trade wars and US farm income", id="case-and-abbreviation"
        ),
        pytest.param(
            "Migration & Labour Markets in the EU", "Migration and labour markets in the EU", id="ampersand"
        ),
        pytest.param(
            "<i>Vibrio cholerae</i> outbreaks after flooding",
            "Vibrio cholerae outbreaks after flooding",
            id="markup",
        ),
        pytest.param(
            "Organisational behaviour and climate adaptation",
            "Organizational behavior and climate adaptation",
            id="spelling-variants",
        ),
        pytest.param(
            "Arctic methane feedbacks: a review of the evidence",
            "Arctic methane feedbacks",
            id="subtitle-dropped",
        ),
        pytest.param(
            "Arctic methane feedbacks", "Arctic methane feedbacks - The Journal", id="outlet-suffix-dropped"
        ),
        pytest.param("Co-operation among rival states", "Cooperation among rival states", id="hyphenation"),
        pytest.param("China’s exports fall again", "Chinas exports fall again", id="apostrophe"),
        pytest.param(
            "Heat waves and emergency visits.", "Heat waves and emergency visits", id="trailing-period"
        ),
    ],
)
def test_fuzzy_titles_agree_across_the_ways_providers_write_one_title(left: str, right: str) -> None:
    assert titles_agree(left, right)
    assert titles_agree(right, left)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        pytest.param(
            "The case for a carbon tax", "The case for a carbon tax in Canada", id="one-extends-the-other"
        ),
        pytest.param(
            "Carbon tax effects on employment in British Columbia",
            "Carbon tax effects on emissions in British Columbia",
            id="one-word-differs",
        ),
        pytest.param(
            "Tariff pass-through to consumer prices, 2018-2020",
            "Tariff pass-through to consumer prices, 2018-2022",
            id="a-number-differs",
        ),
        pytest.param(
            "Nuclear deterrence after the Cold War: Part 1",
            "Nuclear deterrence after the Cold War: Part 2",
            id="part-number",
        ),
        pytest.param("Introduction", "Introduction", id="too-short"),
        pytest.param("Book review", "Book review", id="still-too-short"),
        pytest.param(
            "Climate: a review", "Climate: the politics", id="short-main-titles-with-different-subtitles"
        ),
        pytest.param("Arctic methane: a review", "Arctic methane", id="main-title-too-short"),
        pytest.param("Police reform in Chicago", "Policy reform in Chicago", id="police-and-policy"),
        pytest.param(
            "Immigration policy in Europe", "Emigration policy in Europe", id="immigration-and-emigration"
        ),
        pytest.param(
            "Election security in Georgia", "Selection security in Georgia", id="election-and-selection"
        ),
        pytest.param("Man bites dog in Ohio", "Dog bites man in Ohio", id="word-order"),
    ],
)
def test_fuzzy_titles_disagree_when_the_words_say_different_works(left: str, right: str) -> None:
    assert not titles_agree(left, right)
    assert not titles_agree(right, left)


@pytest.mark.parametrize(
    ("title", "tokens"),
    [
        ("Trade Wars and U.S. Farm Income", ("trade", "wars", "and", "us", "farm", "income")),
        ("<i>E. coli</i> &amp; CO<sub>2</sub>", ("e", "coli", "and", "co2")),
        ("Ça change: São Paulo’s favelas", ("ca", "change", "sao", "paulos", "favelas")),
        ("Co-operation, 2018–2020", ("cooperation", "2018", "2020")),
        ("Behaviour, labour and colour", ("behavior", "labor", "and", "color")),
        ("Organisations analyse the centre", ("organizations", "analyze", "the", "center")),
        ("Organisational change", ("organizational", "change")),
        ("Defence catalogue: travelled programme", ("defense", "catalog", "traveled", "program")),
        ("Paediatric anaemia and ageing", ("pediatric", "anemia", "and", "aging")),
        ("Four hours for your tour", ("four", "hours", "for", "your", "tour")),
        ("", ()),
    ],
)
def test_fuzzy_title_tokens_absorb_case_accents_markup_punctuation_and_british_spelling(
    title: str, tokens: tuple[str, ...]
) -> None:
    assert title_tokens(title) == tokens


# --------------------------------------------------------------------------------------------
# The labelled pairs (ac4)
# --------------------------------------------------------------------------------------------


class LabelledPair(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    expected: Literal["same", "different"]
    tags: tuple[str, ...]
    why: str
    left: CandidateResult
    right: CandidateResult


class LabelledPairFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str
    pairs: tuple[LabelledPair, ...]


HARD_NEGATIVE_TAGS = (
    "near-identical-headlines-different-authors",
    "same-title-different-years",
    "preprint-and-published",
    "syndicated-news",
)


def labelled_pairs() -> tuple[LabelledPair, ...]:
    return LabelledPairFile.model_validate_json((FIXTURES / "pairs.json").read_text(encoding="utf-8")).pairs


def merged_as_one(pair: LabelledPair) -> bool:
    return len(merge_candidates((pair.left, pair.right))) == 1


def test_labeled_pairs_number_at_least_40_and_include_every_hard_negative() -> None:
    pairs = labelled_pairs()

    assert len(pairs) >= 40
    assert len({pair.id for pair in pairs}) == len(pairs)
    for tag in HARD_NEGATIVE_TAGS:
        assert any(pair.expected == "different" and tag in pair.tags for pair in pairs), tag


def test_labeled_pairs_have_zero_false_merges_and_at_least_90_percent_recall() -> None:
    pairs = labelled_pairs()
    same = [pair for pair in pairs if pair.expected == "same"]
    different = [pair for pair in pairs if pair.expected == "different"]

    false_merges = [pair.id for pair in different if merged_as_one(pair)]
    found = [pair for pair in same if merged_as_one(pair)]
    missed = [pair.id for pair in same if not merged_as_one(pair)]
    recall = len(found) / len(same)
    print(f"\nlabelled pairs: {len(pairs)} ({len(same)} same, {len(different)} different)")
    print(f"false merges: {len(false_merges)} {false_merges}")
    print(f"recall: {len(found)}/{len(same)} = {recall:.1%}; missed {missed}")

    assert false_merges == []
    assert recall >= 0.9


def test_labeled_pairs_missed_are_exactly_the_ones_labelled_as_known_misses() -> None:
    """The file says which merges the rules cannot make, and why; this keeps that true both ways."""
    pairs = labelled_pairs()
    missed = {pair.id for pair in pairs if pair.expected == "same" and not merged_as_one(pair)}
    labelled_as_misses = {pair.id for pair in pairs if "expected-miss" in pair.tags}

    assert missed == labelled_as_misses


def test_labeled_pairs_deduplicated_all_at_once_agree_with_each_pair_alone() -> None:
    """Chains across pairs could merge what no pair alone would; every pair is a different work."""
    pairs = labelled_pairs()
    records = [record for pair in pairs for record in (pair.left, pair.right)]
    pair_of = {id(record): index for index, pair in enumerate(pairs) for record in (pair.left, pair.right)}

    together = merge_candidates(records)

    for merged in together:
        assert len({pair_of[id(member)] for member in merged.members}) == 1, [m.title for m in merged.members]
    merged_together = {pair_of[id(merged.members[0])] for merged in together if len(merged.members) == 2}
    merged_alone = {index for index, pair in enumerate(pairs) if merged_as_one(pair)}
    assert merged_together == merged_alone


# --------------------------------------------------------------------------------------------
# Field precedence and provenance (ac3)
# --------------------------------------------------------------------------------------------

#: Each merged field's expected source when all five providers supply it, and the next one when the
#: first does not. Written by hand from the precedence the report justifies, not read from the table.
EXPECTED_PRECEDENCE: dict[str, tuple[str, str]] = {
    "title": ("crossref", "openalex"),
    "url": ("rss", "crossref"),
    "identifiers.doi": ("crossref", "openalex"),
    "identifiers.arxiv_id": ("semantic_scholar", "openalex"),
    "identifiers.pmid": ("openalex", "semantic_scholar"),
    "identifiers.openalex_id": ("openalex", "semantic_scholar"),
    "identifiers.semantic_scholar_id": ("semantic_scholar", "openalex"),
    "source_type": ("crossref", "openalex"),
    "authors": ("crossref", "openalex"),
    "publication": ("crossref", "openalex"),
    "published_at": ("crossref", "rss"),
    "snippet": ("openalex", "semantic_scholar"),
    "open_access_url": ("openalex", "semantic_scholar"),
}

PROVIDERS = ("gdelt", "semantic_scholar", "rss", "openalex", "crossref")
"""The five configured providers, deliberately not in any precedence order."""

SOURCE_TYPE_OF = {
    "crossref": SourceType.SCHOLARLY,
    "openalex": SourceType.GOVERNMENT,
    "semantic_scholar": SourceType.THINK_TANK,
    "rss": SourceType.NEWS,
    "gdelt": SourceType.OTHER,
}


def record_from(provider: str, *, without: str | None = None) -> CandidateResult:
    """A record whose every field names `provider`, with the field `without` left empty."""
    number = PROVIDERS.index(provider) + 1
    fields: dict[str, object] = {
        "provider": provider,
        "title": f"Title from {provider}",
        "url": f"https://{provider}.example.org/record",
        "identifiers": ArticleIdentifiers(
            doi=None if without == "identifiers.doi" else f"10.{1000 + number}/{provider}",
            arxiv_id=None if without == "identifiers.arxiv_id" else f"2401.0000{number}",
            pmid=None if without == "identifiers.pmid" else f"{number}{number}{number}",
            openalex_id=None if without == "identifiers.openalex_id" else f"W{number}",
            semantic_scholar_id=None if without == "identifiers.semantic_scholar_id" else f"s2-{provider}",
        ),
        "source_type": SourceType.OTHER if without == "source_type" else SOURCE_TYPE_OF[provider],
        "authors": () if without == "authors" else (f"Author {provider}",),
        "publication": None if without == "publication" else f"Venue of {provider}",
        "published_at": None if without == "published_at" else at(2020 + number),
        "snippet": None if without == "snippet" else f"Snippet from {provider}",
        "open_access_url": None if without == "open_access_url" else f"https://{provider}.example.org/oa.pdf",
    }
    if without in ("title", "url"):
        raise ValueError(f"every record has a {without}; its precedence is tested by which one is chosen")
    return CandidateResult.model_validate(fields)


def merged_value(merged: MergedCandidate, field: str) -> object:
    if field.startswith("identifiers."):
        return getattr(merged.identifiers, field.removeprefix("identifiers."))
    return getattr(merged, field)


def record_value(record: CandidateResult, field: str) -> object:
    if field.startswith("identifiers."):
        return getattr(record.identifiers, field.removeprefix("identifiers."))
    return getattr(record, field)


def test_precedence_table_has_one_row_per_merged_field_naming_every_configured_provider_once() -> None:
    configured = sorted(name.value for name in SearchProviderName)

    assert set(FIELD_PRECEDENCE) == set(MERGED_FIELDS) - {"canonical_url"}
    for field, order in FIELD_PRECEDENCE.items():
        assert sorted(order) == configured, field


def test_precedence_expectations_cover_every_row_of_the_table() -> None:
    assert set(EXPECTED_PRECEDENCE) == set(FIELD_PRECEDENCE)


@pytest.mark.parametrize("field", sorted(EXPECTED_PRECEDENCE))
def test_precedence_rule_picks_the_first_provider_in_its_row(field: str) -> None:
    winner, _ = EXPECTED_PRECEDENCE[field]
    records = [record_from(provider) for provider in PROVIDERS]

    merged = merge_group(records)

    assert merged_value(merged, field) == record_value(record_from(winner), field)
    assert merged.field_sources[field] == winner


@pytest.mark.parametrize("field", sorted(set(EXPECTED_PRECEDENCE) - {"title", "url"}))
def test_precedence_rule_falls_back_to_the_next_provider_when_the_first_has_no_value(field: str) -> None:
    winner, runner_up = EXPECTED_PRECEDENCE[field]
    records = [record_from(provider, without=field if provider == winner else None) for provider in PROVIDERS]

    merged = merge_group(records)

    assert merged_value(merged, field) == record_value(record_from(runner_up), field)
    assert merged.field_sources[field] == runner_up


def test_precedence_url_falls_back_to_crossref_when_no_feed_found_the_source() -> None:
    records = [record_from(provider) for provider in PROVIDERS if provider != "rss"]

    merged = merge_group(records)

    assert merged.url == "https://crossref.example.org/record"
    assert merged.field_sources["url"] == "crossref"


def test_precedence_puts_a_provider_outside_the_table_after_every_provider_in_it() -> None:
    core = record_from("gdelt").evolve(provider="core", title="Title from core")
    gdelt = record_from("gdelt")

    assert merge_group((core, gdelt)).field_sources["title"] == "gdelt"
    assert merge_group((core,)).field_sources["title"] == "core"


def test_precedence_between_two_records_from_one_provider_takes_the_first() -> None:
    first = paper(title="First wording of the title")
    second = paper(title="Second wording of the title")

    assert merge_group((first, second)).title == "First wording of the title"
    assert merge_group((second, first)).title == "Second wording of the title"


def test_precedence_skips_an_empty_snippet() -> None:
    blank = record_from("openalex").evolve(snippet="  ")
    semantic_scholar = record_from("semantic_scholar")

    merged = merge_group((blank, semantic_scholar))

    assert merged.snippet == "Snippet from semantic_scholar"
    assert merged.field_sources["snippet"] == "semantic_scholar"


def test_precedence_keeps_other_as_the_source_type_only_when_no_provider_knows_better() -> None:
    unknown = record_from("crossref").evolve(source_type=SourceType.OTHER)
    known = record_from("gdelt").evolve(source_type=SourceType.NEWS)

    assert merge_group((unknown, known)).source_type is SourceType.NEWS
    assert merge_group((unknown, known)).field_sources["source_type"] == "gdelt"
    assert merge_group((unknown,)).source_type is SourceType.OTHER
    assert merge_group((unknown,)).field_sources["source_type"] == "crossref"


def test_precedence_canonical_url_is_the_merged_urls_canonical_form_from_the_same_provider() -> None:
    feed = story(url="https://www.example-news.com/2026/10/14/senate-stopgap?utm_source=rss")
    crawl = story(provider="gdelt", url="https://www.example-news.com/amp/2026/10/14/senate-stopgap")

    merged = merge_group((crawl, feed))

    assert merged.url == "https://www.example-news.com/2026/10/14/senate-stopgap?utm_source=rss"
    assert merged.canonical_url == "https://www.example-news.com/2026/10/14/senate-stopgap"
    assert merged.field_sources["url"] == merged.field_sources["canonical_url"] == "rss"


def test_every_merged_field_with_a_value_records_its_source_provider_and_no_other_field_does() -> None:
    sparse = story(authors=())

    merged = merge_group((sparse,))

    assert merged.field_sources == {
        "title": "rss",
        "url": "rss",
        "canonical_url": "rss",
        "source_type": "rss",
        "published_at": "rss",
    }


def test_merged_candidate_refuses_a_value_with_no_source() -> None:
    merged = merge_group((story(),))
    sources = {field: provider for field, provider in merged.field_sources.items() if field != "title"}

    with pytest.raises(ValidationError, match="title"):
        merged.evolve(field_sources=sources)


def test_merged_candidate_refuses_a_source_for_a_field_with_no_value() -> None:
    merged = merge_group((story(),))

    with pytest.raises(ValidationError, match="snippet"):
        merged.evolve(field_sources={**merged.field_sources, "snippet": "rss"})


def test_merged_candidate_refuses_a_source_that_is_not_one_of_its_providers() -> None:
    merged = merge_group((story(),))

    with pytest.raises(ValidationError, match="crossref"):
        merged.evolve(field_sources={**merged.field_sources, "title": "crossref"})


def test_merged_candidate_refuses_a_value_its_named_source_did_not_supply() -> None:
    merged = merge_group((story(), story(provider="gdelt", title="The crawler's headline")))

    with pytest.raises(ValidationError, match="title"):
        merged.evolve(title="A headline nobody supplied")
    with pytest.raises(ValidationError, match="title"):
        merged.evolve(field_sources={**merged.field_sources, "title": "gdelt"})


def test_merged_candidate_refuses_providers_that_do_not_match_its_members() -> None:
    merged = merge_group((story(), story(provider="gdelt")))

    with pytest.raises(ValidationError, match="providers"):
        merged.evolve(providers=("rss",))
    with pytest.raises(ValidationError, match="members"):
        merged.evolve(members=(), providers=())


# --------------------------------------------------------------------------------------------
# The normalize stage
# --------------------------------------------------------------------------------------------


class ProvidersOnHand:
    """The `DiscoveryProviders` port over providers given directly, with no health to report."""

    def __init__(self, *providers: SearchProvider) -> None:
        self._providers = providers

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


class KeepState:
    """A rank stage that changes nothing and keeps the state it was handed."""

    def __init__(self) -> None:
        self.seen: list[SearchState] = []

    async def run(self, state: SearchState) -> SearchState:
        self.seen.append(state)
        return state


METHANE_OPENALEX = paper(provider="openalex", identifiers=ArticleIdentifiers(doi="10.1038/methane"))
METHANE_CROSSREF = paper(
    provider="crossref",
    url="https://doi.org/10.1038/methane",
    identifiers=ArticleIdentifiers(doi="10.1038/methane"),
)


def search_with(normalize: DedupeStage | None) -> tuple[SearchState, tuple[object, ...]]:
    providers = ProvidersOnHand(
        FakeSearchProvider("openalex", default_results=(METHANE_OPENALEX,)),
        FakeSearchProvider("crossref", default_results=(METHANE_CROSSREF,)),
    )
    rank = KeepState()
    service = FederatedSearchService(
        providers,
        InMemorySearchRepository(),
        clock=EventLoopClock(),
        ids=SequentialIdGenerator("SRCH"),
        normalize=normalize,
        rank=rank,
    )
    outcome = run_in_virtual_time(service.search(SearchRequest(query="arctic methane")))
    (state,) = rank.seen
    return state, (outcome.provider_statuses, outcome.candidates, outcome.status)


def test_the_dedupe_stage_plugs_into_the_normalize_slot_and_the_rank_stage_sees_its_merge() -> None:
    plain_state, plain_outcome = search_with(None)
    deduplicated_state, deduplicated_outcome = search_with(DedupeStage())

    assert plain_state.merged_candidates == ()
    (merged,) = deduplicated_state.merged_candidates
    assert merged.members == (METHANE_OPENALEX, METHANE_CROSSREF)
    assert deduplicated_outcome == plain_outcome


def test_the_dedupe_stage_leaves_provider_statuses_candidates_and_results_alone() -> None:
    state, _ = search_with(None)

    after = run_in_virtual_time(DedupeStage().run(state))

    assert after.provider_statuses is state.provider_statuses
    assert after.candidates is state.candidates
    assert after.results is state.results
    assert after.queries is state.queries
    assert len(after.merged_candidates) == 1


def test_deduplication_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The forbidden list: nothing during normalization may reach the network, DNS included."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("deduplication tried to use the network")

    refusal: Callable[..., None] = refuse
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, refusal)
    records = [record for pair in labelled_pairs() for record in (pair.left, pair.right)]

    assert merge_candidates(records)


def test_the_dedupe_module_imports_no_network_client() -> None:
    source = Path(federated_dedupe.__file__).read_text(encoding="utf-8")

    for client in ("httpx", "urllib.request", "requests", "socket", "aiohttp"):
        assert f"import {client}" not in source, client
        assert f"from {client}" not in source, client

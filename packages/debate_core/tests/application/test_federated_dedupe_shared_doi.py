"""A shared DOI overrules differing OpenAlex work ids (v1-e08-t21, from v1-e08-t10's question 4).

OpenAlex sometimes lists one paper as two works: one at a repository's PDF, one at its `doi.org` page,
with one DOI and two work ids. Dedupe kept them as two results because different values of one
identifier win over every rule. A shared normalized DOI now overrules differing OpenAlex ids, and
nothing else: works with no DOI, or with different DOIs, stay apart, and a shared DOI does not
overrule a differing PMID, arXiv id or Semantic Scholar id.

The OpenAlex works are `fixtures/discovery/openalex/works_one_doi_two_work_ids.body.json`, written
by hand (invented titles, people and `10.5555` DOIs) and read through the OpenAlex adapter's own
`candidate_from_work`, so the records are the ones a search would merge. Every expected value below
is written out by hand from that file (working agreement 6).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from debate_core.application.federated_dedupe import MatchRule, MergedCandidate, merge_candidates, merge_group
from debate_core.application.federated_ranking_features import provider_agreement
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.openalex import candidate_from_work

FIXTURE: Final = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "discovery"
    / "openalex"
    / "works_one_doi_two_work_ids.body.json"
)

DOI: Final = "10.5555/fdt.2025.0031"
REPOSITORY_PDF: Final = "https://eprints.example.ac.uk/1207/1/fdt-0031.pdf"
DOI_PAGE: Final = "https://doi.org/10.5555/fdt.2025.0031"


def openalex_works() -> list[CandidateResult]:
    """The fixture's six works as the OpenAlex adapter maps them, in the body's order."""
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    candidates = [candidate_from_work(work) for work in body["results"]]
    assert all(candidate is not None for candidate in candidates)
    return [candidate for candidate in candidates if candidate is not None]


def groups(candidates: list[CandidateResult]) -> list[list[int]]:
    """Which input positions each merged candidate holds, in output order."""
    position = {id(candidate): index for index, candidate in enumerate(candidates)}
    return [[position[id(member)] for member in merged.members] for merged in merge_candidates(candidates)]


def one_work(candidates: tuple[CandidateResult, ...]) -> MergedCandidate:
    """The single work `candidates` merge into; fails at an assertion when they are not one."""
    merged = merge_candidates(candidates)
    assert len(merged) == 1, f"expected one work, got {len(merged)}: {[m.url for m in merged]}"
    return merged[0]


def record(
    *,
    provider: str = "openalex",
    url: str,
    identifiers: ArticleIdentifiers,
    title: str = "Fiscal devolution and the territorial politics of health budgets",
    authors: tuple[str, ...] = ("Mara Okonjo",),
    source_type: SourceType = SourceType.SCHOLARLY,
    publication: str | None = None,
    snippet: str | None = None,
    citation_count: int | None = None,
) -> CandidateResult:
    return CandidateResult(
        provider=provider,
        title=title,
        url=url,
        identifiers=identifiers,
        source_type=source_type,
        authors=authors,
        publication=publication,
        published_at=datetime(2025, 4, 2, tzinfo=UTC),
        snippet=snippet,
        citation_count=citation_count,
    )


# --------------------------------------------------------------------------------------------
# The fixture: one DOI under two work ids, and the pairs that stay apart
# --------------------------------------------------------------------------------------------


def test_shared_doi_the_fixture_maps_to_the_records_the_tests_expect() -> None:
    """The adapter reads both spellings of the DOI as one, and drops the one that is not a DOI."""
    works = openalex_works()

    assert [work.identifiers.openalex_id for work in works] == [
        "W7100000002",
        "W7100000001",
        "W7100000003",
        "W7100000004",
        "W7100000005",
        "W7100000006",
    ]
    assert [work.identifiers.doi for work in works] == [
        DOI,
        DOI,
        "10.5555/fdt.2025.0032",
        "10.5555/fdt.2025.0033",
        None,
        None,
    ]
    assert [work.url for work in works[:2]] == [DOI_PAGE, REPOSITORY_PDF]


def test_shared_doi_two_openalex_work_ids_with_one_doi_merge_into_one_work_with_both_locations() -> None:
    doi_page_copy, repository_copy = openalex_works()[:2]

    merged = one_work((doi_page_copy, repository_copy))

    assert merged.matched_on == (MatchRule.DOI,)
    assert merged.members == (doi_page_copy, repository_copy)
    assert {member.url for member in merged.members} == {DOI_PAGE, REPOSITORY_PDF}
    assert merged.providers == ("openalex",)
    assert merged.identifiers.doi == DOI


def test_shared_doi_works_with_different_dois_stay_two_and_so_do_works_with_none() -> None:
    """Works 3 and 4 agree on title, author and year but not DOI; works 5 and 6 agree on title,
    author, day and site and have no DOI (6's `doi` is not one, so the adapter drops it)."""
    works = openalex_works()

    assert groups(works) == [[0, 1], [2], [3], [4], [5]]


def test_shared_doi_the_fuller_records_fields_win_over_the_earlier_ones() -> None:
    """The repository copy comes second but is fuller (10 fields to 7), so where the two differ
    its values win: title, URL, work id, open-access status and citations. Fields only it has
    (venue, abstract, open copy) come from it either way."""
    doi_page_copy, repository_copy = openalex_works()[:2]

    merged = merge_group((doi_page_copy, repository_copy), (MatchRule.DOI,))

    assert merged.title == "Fiscal devolution and the territorial politics of health budgets"
    assert merged.url == REPOSITORY_PDF
    assert merged.identifiers.openalex_id == "W7100000001"
    assert merged.open_access is True
    assert merged.citation_count == 9
    assert merged.publication == "Invented University Research Repository"
    assert merged.snippet == "Devolved health budgets shift blame between tiers."
    assert merged.open_access_url == REPOSITORY_PDF


def test_shared_doi_a_field_the_fuller_record_lacks_comes_from_the_other() -> None:
    fuller = record(
        url=REPOSITORY_PDF,
        identifiers=ArticleIdentifiers(doi=DOI, openalex_id="W7100000001"),
        publication="Invented University Research Repository",
        snippet="An abstract.",
    )
    thinner = record(
        url=DOI_PAGE,
        identifiers=ArticleIdentifiers(doi=DOI, openalex_id="W7100000002"),
        citation_count=4,
    )

    merged = merge_group((thinner, fuller), (MatchRule.DOI,))

    assert merged.url == REPOSITORY_PDF
    assert merged.citation_count == 4


def test_shared_doi_empty_values_do_not_make_a_record_fuller() -> None:
    """No authors, a blank abstract and source type `other` are empty, as the precedence reads them:
    the earlier copy has 3 values (DOI, work id, date) to the later one's 6, so the later one wins."""
    empty_valued = record(
        url=DOI_PAGE,
        identifiers=ArticleIdentifiers(doi=DOI, openalex_id="W7100000002"),
        authors=(),
        source_type=SourceType.OTHER,
        snippet="   ",
    )
    filled = record(
        url=REPOSITORY_PDF,
        identifiers=ArticleIdentifiers(doi=DOI, openalex_id="W7100000001"),
        snippet="An abstract.",
    )

    merged = one_work((empty_valued, filled))

    assert merged.url == REPOSITORY_PDF
    assert merged.identifiers.openalex_id == "W7100000001"


def test_shared_doi_between_equally_full_records_the_earlier_one_wins() -> None:
    """The tie-break is input order, the order the provider returned them in: deterministic for a
    given answer, and the same rule dedupe already applies between two records of one provider."""
    first = record(url=REPOSITORY_PDF, identifiers=ArticleIdentifiers(doi=DOI, openalex_id="W7100000001"))
    second = record(
        url=DOI_PAGE,
        title="Fiscal Devolution and the Territorial Politics of Health Budgets",
        identifiers=ArticleIdentifiers(doi=DOI, openalex_id="W7100000002"),
    )

    forward = merge_candidates((first, second))
    backward = merge_candidates((second, first))

    assert [(m.url, m.title, m.identifiers.openalex_id) for m in forward] == [
        (REPOSITORY_PDF, "Fiscal devolution and the territorial politics of health budgets", "W7100000001")
    ]
    assert [(m.url, m.title, m.identifiers.openalex_id) for m in backward] == [
        (DOI_PAGE, "Fiscal Devolution and the Territorial Politics of Health Budgets", "W7100000002")
    ]


# --------------------------------------------------------------------------------------------
# Provider agreement
# --------------------------------------------------------------------------------------------


def test_shared_doi_provider_agreement_counts_openalex_once_for_the_merged_work() -> None:
    """Two providers answered. The merged work was found by one of them (OpenAlex, twice), so it
    agrees with none of the other providers: 0, not the 1.0 that counting OpenAlex twice gives."""
    doi_page_copy, repository_copy = openalex_works()[:2]

    merged = one_work((doi_page_copy, repository_copy))

    assert provider_agreement(merged, answered=2) == 0.0


def test_shared_doi_provider_agreement_with_crossref_counts_two_providers_not_three() -> None:
    doi_page_copy, repository_copy = openalex_works()[:2]
    crossref = record(
        provider="crossref",
        url="https://doi.org/10.5555/FDT.2025.0031",
        identifiers=ArticleIdentifiers(doi="doi:10.5555/FDT.2025.0031"),
    )

    merged = one_work((doi_page_copy, crossref, repository_copy))

    assert merged.providers == ("openalex", "crossref")
    assert provider_agreement(merged, answered=3) == 0.5


# --------------------------------------------------------------------------------------------
# Everything else as before
# --------------------------------------------------------------------------------------------


def test_shared_doi_across_openalex_and_crossref_still_merges_with_crossrefs_title() -> None:
    """The rule from before this task: a DOI shared across providers merges, and Crossref, the
    publisher's deposit, gives the title. The second OpenAlex copy joins the same work."""
    doi_page_copy, repository_copy = openalex_works()[:2]
    crossref = record(
        provider="crossref",
        title="Fiscal Devolution and the Territorial Politics of Health Budgets: Evidence",
        url="https://doi.org/10.5555/FDT.2025.0031",
        identifiers=ArticleIdentifiers(doi="https://doi.org/10.5555/FDT.2025.0031"),
    )

    alone = one_work((repository_copy, crossref))
    all_three = one_work((doi_page_copy, repository_copy, crossref))

    assert alone.matched_on == (MatchRule.DOI,)
    assert alone.field_sources["title"] == "crossref"
    assert alone.identifiers.openalex_id == "W7100000001"
    assert all_three.members == (doi_page_copy, repository_copy, crossref)
    assert all_three.title == "Fiscal Devolution and the Territorial Politics of Health Budgets: Evidence"
    assert all_three.identifiers.openalex_id == "W7100000001"


def test_shared_doi_does_not_overrule_a_differing_pmid() -> None:
    """Only OpenAlex's own duplicates are overruled; two PubMed records are two papers."""
    first = record(url=REPOSITORY_PDF, identifiers=ArticleIdentifiers(doi=DOI, pmid="31000001"))
    second = record(url=DOI_PAGE, identifiers=ArticleIdentifiers(doi=DOI, pmid="31000002"))

    assert groups([first, second]) == [[0], [1]]


def test_shared_doi_two_works_with_no_doi_but_one_arxiv_id_stay_two() -> None:
    """Dedupe gives an arXiv record its arXiv DOI for the identifier rule, but neither record states a
    DOI, so this rule does not join them: two OpenAlex works with no DOI are never merged by it."""
    first = record(
        url="https://arxiv.org/abs/2502.01234",
        identifiers=ArticleIdentifiers(arxiv_id="2502.01234", openalex_id="W7100000011"),
    )
    second = record(
        url="https://arxiv.org/pdf/2502.01234v2",
        identifiers=ArticleIdentifiers(arxiv_id="2502.01234v2", openalex_id="W7100000012"),
    )

    assert groups([first, second]) == [[0], [1]]


def test_shared_doi_a_record_naming_either_work_id_joins_the_merged_work() -> None:
    """Once one DOI holds both work ids, a record carrying either id (and no DOI) is that work."""
    doi_page_copy, repository_copy = openalex_works()[:2]
    by_first_id = record(
        url="https://openalex.org/W7100000002", identifiers=ArticleIdentifiers(openalex_id="W7100000002")
    )
    by_second_id = record(
        url="https://openalex.org/W7100000001", identifiers=ArticleIdentifiers(openalex_id="W7100000001")
    )

    assert groups([doi_page_copy, repository_copy, by_first_id, by_second_id]) == [[0, 1, 2, 3]]


def test_shared_doi_records_of_one_provider_joined_by_another_rule_keep_the_earlier_ones_fields() -> None:
    """Fullness decides only between the copies of a work held under two OpenAlex ids. Two records
    of one work id still take the earlier one's value, however full the later one is."""
    thinner = record(url=DOI_PAGE, identifiers=ArticleIdentifiers(openalex_id="W7100000001"))
    fuller = record(
        url=REPOSITORY_PDF,
        title="Fiscal Devolution and the Territorial Politics of Health Budgets",
        identifiers=ArticleIdentifiers(doi=DOI, openalex_id="W7100000001"),
        publication="Invented University Research Repository",
        snippet="An abstract.",
        citation_count=9,
    )

    merged = one_work((thinner, fuller))

    assert merged.matched_on == (MatchRule.PROVIDER_ID,)
    assert merged.url == DOI_PAGE
    assert merged.title == "Fiscal devolution and the territorial politics of health budgets"

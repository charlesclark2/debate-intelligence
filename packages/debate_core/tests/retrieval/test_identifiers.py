"""DOI, arXiv and PMID detection (`v1-e04-t01-url-canonicalization`, ac4).

Every expected identifier is written by hand. The URL and citation shapes are real public shapes
(doi.org, publisher landing pages, arXiv, PubMed, Europe PMC); nothing is resolved or fetched.
Each kind is tested in running text with the punctuation that ends a sentence or a parenthesis
right after it, because that is where a greedy pattern takes one character too many.
"""

from __future__ import annotations

import pytest

from debate_core.domain.article import ArticleIdentifiers
from debate_core.retrieval.identifiers import ScholarlyIdentifiers, detect_identifiers

# ---------------------------------------------------------------------------------------------
# DOI
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "doi"),
    [
        pytest.param("https://doi.org/10.1038/nature12373", "10.1038/nature12373", id="doi-org"),
        pytest.param(
            "https://dx.doi.org/10.1016/S0140-6736(20)30183-5",
            "10.1016/s0140-6736(20)30183-5",
            id="dx-doi-org-with-parentheses-lowercased",
        ),
        pytest.param("http://doi.org/10.1000%2F182", "10.1000/182", id="percent-encoded-slash"),
        pytest.param("http://doi.org/10.1000%2f182", "10.1000/182", id="percent-encoded-slash-lower-hex"),
        pytest.param(
            "https://doi.org/10.1016%2FS0140-6736%2820%2930183-5",
            "10.1016/s0140-6736(20)30183-5",
            id="percent-encoded-throughout",
        ),
        pytest.param(
            "https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0230000&utm_source=x",
            "10.1371/journal.pone.0230000",
            id="publisher-query-parameter",
        ),
        pytest.param(
            "https://onlinelibrary.wiley.com/doi/full/10.1111/ajps.12345",
            "10.1111/ajps.12345",
            id="publisher-path",
        ),
        pytest.param(
            "https://www.frontiersin.org/articles/10.3389/fpsyg.2020.01234/full",
            "10.3389/fpsyg.2020.01234",
            id="publisher-path-with-viewer-suffix",
        ),
        pytest.param(
            "https://link.springer.com/content/pdf/10.1007/s11109-020-09611-1.pdf",
            "10.1007/s11109-020-09611-1",
            id="publisher-pdf-link",
        ),
        pytest.param(
            "https://doi.org/10.1000/182?utm_source=x#ref", "10.1000/182", id="query-and-fragment-after"
        ),
        pytest.param(
            "DOI: 10.1126/SCIENCE.ABC1234, accessed today", "10.1126/science.abc1234", id="text-upper-case"
        ),
        pytest.param("Available at doi:10.1093/ajae/aaq063", "10.1093/ajae/aaq063", id="text-doi-prefix"),
    ],
)
def test_a_doi_is_found_and_lowercased(source: str, doi: str) -> None:
    assert detect_identifiers(source).dois == (doi,)


@pytest.mark.parametrize(
    ("text", "doi"),
    [
        pytest.param("Available at doi:10.1093/ajae/aaq063.", "10.1093/ajae/aaq063", id="full-stop"),
        pytest.param(
            "(see https://doi.org/10.1038/nature12373)", "10.1038/nature12373", id="closing-parenthesis"
        ),
        pytest.param(
            "(Horton, 2020, doi:10.1016/S0140-6736(20)30183-5).",
            "10.1016/s0140-6736(20)30183-5",
            id="own-parentheses-then-closing-parenthesis-and-full-stop",
        ),
        pytest.param("cited as 10.1000/182, 10.1000/183;", "10.1000/182", id="comma"),
        pytest.param('the link "https://doi.org/10.1038/nature12373".', "10.1038/nature12373", id="quotes"),
        pytest.param("[10.1038/nature12373]", "10.1038/nature12373", id="closing-bracket"),
        pytest.param(
            "(ASCE, doi:10.1061/(ASCE)0733-9445(2004)130:4(605)).",
            "10.1061/(asce)0733-9445(2004)130:4(605)",
            id="ending-in-its-own-parenthesis",
        ),
        pytest.param(
            "<a href=https://doi.org/10.1038/nature12373>paper</a>", "10.1038/nature12373", id="markup"
        ),
    ],
)
def test_a_doi_in_running_text_leaves_the_punctuation_after_it(text: str, doi: str) -> None:
    assert detect_identifiers(text).dois[0] == doi


def test_several_dois_are_returned_once_each_in_order_of_appearance() -> None:
    text = "See 10.1000/182 and doi:10.1038/NATURE12373, and again https://doi.org/10.1000/182."
    assert detect_identifiers(text).dois == ("10.1000/182", "10.1038/nature12373")


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Version 10.12 of the report", id="version-number"),
        pytest.param("call 10.1234 now", id="no-suffix"),
        pytest.param("ISBN 978-0-12-345678-9", id="isbn"),
        pytest.param(
            "https://www.sciencedirect.com/science/article/pii/S0140673620301835", id="elsevier-pii"
        ),
        pytest.param("110.1234/abc", id="inside-a-longer-number"),
    ],
)
def test_no_doi_is_invented(text: str) -> None:
    assert detect_identifiers(text).dois == ()


def test_arxiv_ids_from_dois_and_labels_keep_their_order_in_the_text() -> None:
    found = detect_identifiers("https://doi.org/10.48550/arXiv.2101.01234 and then arXiv:2002.06199")
    assert found.arxiv_ids == ("2101.01234", "2002.06199")


def test_an_arxiv_doi_also_yields_its_arxiv_id() -> None:
    found = detect_identifiers("https://doi.org/10.48550/arXiv.2101.01234")
    assert found.dois == ("10.48550/arxiv.2101.01234",)
    assert found.arxiv_ids == ("2101.01234",)


# ---------------------------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "arxiv_id"),
    [
        pytest.param("https://arxiv.org/abs/2101.01234v3", "2101.01234", id="new-style-abs-version-dropped"),
        pytest.param("https://arxiv.org/pdf/2101.01234v3.pdf", "2101.01234", id="new-style-pdf"),
        pytest.param("https://export.arxiv.org/abs/1501.00001", "1501.00001", id="new-style-five-digits"),
        pytest.param("arXiv:0706.0001v2", "0706.0001", id="new-style-four-digits"),
        pytest.param("ARXIV: 2101.01234", "2101.01234", id="prefix-any-case-and-space"),
        pytest.param("https://arxiv.org/abs/hep-th/9901001", "hep-th/9901001", id="old-style-url"),
        pytest.param("arXiv:hep-th/9901001v2", "hep-th/9901001", id="old-style-version-dropped"),
        pytest.param("arXiv:math.GT/0309136", "math/0309136", id="old-style-subject-class-dropped"),
        pytest.param(
            "https://arxiv.org/abs/cond-mat/0102536v1", "cond-mat/0102536", id="old-style-hyphenated"
        ),
    ],
)
def test_an_arxiv_id_is_found_without_its_version(source: str, arxiv_id: str) -> None:
    assert detect_identifiers(source).arxiv_ids == (arxiv_id,)


@pytest.mark.parametrize(
    ("text", "arxiv_id"),
    [
        pytest.param("preprint arXiv:2101.01234v3.", "2101.01234", id="new-style-full-stop"),
        pytest.param("(arXiv:2101.01234)", "2101.01234", id="new-style-closing-parenthesis"),
        pytest.param("(arXiv:hep-th/9901001v2).", "hep-th/9901001", id="old-style-parenthesis-and-full-stop"),
        pytest.param("arXiv:hep-th/9901001, arXiv:2101.01234;", "hep-th/9901001", id="old-style-comma"),
    ],
)
def test_an_arxiv_id_in_running_text_leaves_the_punctuation_after_it(text: str, arxiv_id: str) -> None:
    assert detect_identifiers(text).arxiv_ids[0] == arxiv_id


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("figure 2101.01234 shows", id="bare-number-without-arxiv"),
        pytest.param("arXiv:2113.01234", id="month-thirteen"),
        pytest.param("https://arxiv.org/abs/2101.012345", id="six-digit-sequence"),
        pytest.param("arXiv:hep-th/99010", id="old-style-too-short"),
    ],
)
def test_no_arxiv_id_is_invented(text: str) -> None:
    assert detect_identifiers(text).arxiv_ids == ()


# ---------------------------------------------------------------------------------------------
# PMID
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("https://pubmed.ncbi.nlm.nih.gov/32109013/", id="pubmed-url"),
        pytest.param("https://www.ncbi.nlm.nih.gov/pubmed/32109013", id="legacy-ncbi-url"),
        pytest.param("https://europepmc.org/article/MED/32109013", id="europe-pmc-med-url"),
        pytest.param("PMID: 32109013", id="text-label-colon"),
        pytest.param("PMID 32109013", id="text-label-space"),
        pytest.param("pmid:32109013", id="text-label-lower-case"),
    ],
)
def test_a_pmid_is_found(source: str) -> None:
    assert detect_identifiers(source).pmids == ("32109013",)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("PMID: 32109013.", id="full-stop"),
        pytest.param("(PMID: 32109013)", id="closing-parenthesis"),
        pytest.param("PMID:32109013;", id="semicolon"),
        pytest.param("https://pubmed.ncbi.nlm.nih.gov/32109013).", id="url-then-parenthesis-and-full-stop"),
    ],
)
def test_a_pmid_in_running_text_leaves_the_punctuation_after_it(text: str) -> None:
    assert detect_identifiers(text).pmids == ("32109013",)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("PMCID: PMC7092803", id="pmcid"),
        pytest.param("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7092803/", id="pmc-url"),
        pytest.param("https://pubmed.ncbi.nlm.nih.gov/?term=covid", id="pubmed-search"),
        pytest.param("PMID: 0", id="zero"),
    ],
)
def test_no_pmid_is_invented(text: str) -> None:
    assert detect_identifiers(text).pmids == ()


# ---------------------------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------------------------


def test_a_reference_finds_all_three_kinds() -> None:
    reference = (
        "Huang C, et al. Clinical features of patients infected with 2019 novel coronavirus. Lancet. "
        "2020;395(10223):497-506. doi:10.1016/S0140-6736(20)30183-5. PMID: 31986264. "
        "Preprint: arXiv:2002.06199v1."
    )
    assert detect_identifiers(reference) == ScholarlyIdentifiers(
        dois=("10.1016/s0140-6736(20)30183-5",), arxiv_ids=("2002.06199",), pmids=("31986264",)
    )


def test_nothing_found_is_empty() -> None:
    found = detect_identifiers("https://www.cfr.org/backgrounder/what-nato")
    assert found == ScholarlyIdentifiers()
    assert found.is_empty


def test_something_found_is_not_empty() -> None:
    assert not detect_identifiers("PMID: 31986264").is_empty


def test_the_first_of_each_kind_becomes_the_article_identifiers() -> None:
    found = detect_identifiers("doi:10.1000/182 then doi:10.1000/183, arXiv:2101.01234, PMID: 31986264")
    assert found.as_article_identifiers() == ArticleIdentifiers(
        doi="10.1000/182", arxiv_id="2101.01234", pmid="31986264"
    )


def test_an_empty_result_becomes_empty_article_identifiers() -> None:
    assert ScholarlyIdentifiers().as_article_identifiers().is_empty

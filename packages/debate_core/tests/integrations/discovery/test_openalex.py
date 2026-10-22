"""OpenAlexProvider: the request it sends, how works map to candidates, and the contract kit.

Every OpenAlex answer here is hand-written from OpenAlex's documented response shape and lives in
`packages/debate_core/tests/fixtures/discovery/openalex/`, beside the fake provider's; every
expected mapping is written by hand from those bodies (working agreement 6). Nothing here reaches
the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.domain.discovery import CandidateResult
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.openalex import (
    candidate_from_work,
    rebuild_abstract,
    source_type_for,
)

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "openalex"


def body(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def a_work(**fields: Any) -> dict[str, Any]:
    """A minimal mappable work, with `fields` laid over it."""
    return {"id": "https://openalex.org/W100", "display_name": "A title", **fields}


# --------------------------------------------------------------------------------------------
# Work type to source type
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("work_type", "expected"),
    [
        ("article", SourceType.SCHOLARLY),
        ("book", SourceType.SCHOLARLY),
        ("book-chapter", SourceType.SCHOLARLY),
        ("book-review", SourceType.SCHOLARLY),
        ("conference-abstract", SourceType.SCHOLARLY),
        ("conference-paper", SourceType.SCHOLARLY),
        ("data-paper", SourceType.SCHOLARLY),
        ("dissertation", SourceType.SCHOLARLY),
        ("editorial", SourceType.SCHOLARLY),
        ("erratum", SourceType.SCHOLARLY),
        ("letter", SourceType.SCHOLARLY),
        ("peer-review", SourceType.SCHOLARLY),
        ("preprint", SourceType.SCHOLARLY),
        ("reference-entry", SourceType.SCHOLARLY),
        ("retraction", SourceType.SCHOLARLY),
        ("review", SourceType.SCHOLARLY),
        ("software-paper", SourceType.SCHOLARLY),
        ("report", SourceType.OTHER),
        ("standard", SourceType.OTHER),
        ("dataset", SourceType.OTHER),
        ("libguides", SourceType.OTHER),
        ("other", SourceType.OTHER),
        ("paratext", SourceType.OTHER),
        ("software", SourceType.OTHER),
        ("supplementary-materials", SourceType.OTHER),
    ],
)
def test_each_documented_work_type_maps_to_its_source_type(work_type: str, expected: SourceType) -> None:
    assert source_type_for(work_type) is expected


@pytest.mark.parametrize(
    "work_type",
    ["journal-article", "posted-content", "Article", "book-section", "", None, 7, ["article"]],
    ids=repr,
)
def test_an_unknown_or_missing_work_type_maps_to_other(work_type: object) -> None:
    assert source_type_for(work_type) is SourceType.OTHER


# --------------------------------------------------------------------------------------------
# Abstract rebuild
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inverted_index", "expected"),
    [
        ({"Despite": [0], "growing": [1], "interest": [2]}, "Despite growing interest"),
        ({"interest": [2], "Despite": [0], "growing": [1]}, "Despite growing interest"),
        ({"the": [0, 3], "cat": [1], "saw": [2], "dog.": [4]}, "the cat saw the dog."),
        ({"later": [9], "first": [0]}, "first later"),
        ({"only": [0], "skipped": [], "bool": [True], "negative": [-1], "text": ["1"]}, "only"),
        ({"kept": [0], "not a list": 1, "also": [1]}, "kept also"),
        ({}, None),
        ({"ghost": []}, None),
        (None, None),
        ("Despite growing interest", None),
        ([["Despite", [0]]], None),
    ],
    ids=[
        "in order",
        "keys out of order",
        "a word at two positions",
        "a gap in the positions",
        "unreadable positions ignored",
        "unreadable entries ignored",
        "empty index",
        "no positions at all",
        "null",
        "plain text instead of an index",
        "a list instead of an index",
    ],
)
def test_the_abstract_is_rebuilt_in_word_order(inverted_index: object, expected: str | None) -> None:
    assert rebuild_abstract(inverted_index) == expected


# --------------------------------------------------------------------------------------------
# Work to CandidateResult mapping
# --------------------------------------------------------------------------------------------


def test_the_recorded_works_map_to_the_hand_written_candidates() -> None:
    works = body("works_search.body.json")["results"]
    expected = json.loads((FIXTURES / "works_search.expected.json").read_text(encoding="utf-8"))
    mapped = [candidate_from_work(work) for work in works]
    assert mapped == [CandidateResult.model_validate(item) for item in expected]


def test_the_mapping_keeps_no_affiliation_orcid_or_raw_author_name() -> None:
    works = body("works_search.body.json")["results"]
    stored = json.dumps(
        [candidate.model_dump(mode="json") for work in works if (candidate := candidate_from_work(work))]
    )
    for absent in (
        "orcid",
        "0000-0000-0000-0001",
        "University of Nowhere",
        "Example Policy Institute",
        "Department of Invented Economics",
        "A. Placeholder",
        "Q. Unmatched",
        "openalex.org/A5000000001",
    ):
        assert absent not in stored


@pytest.mark.parametrize(
    "work",
    [
        {"id": "https://openalex.org/W100"},
        a_work(display_name=None),
        a_work(display_name="   "),
        a_work(id=None),
        a_work(id="https://openalex.org/A100"),
        a_work(id="https://openalex.org/W"),
        a_work(id="https://openalex.org/W12x"),
    ],
    ids=["no title", "null title", "blank title", "no id", "an author id", "a bare W", "not digits"],
)
def test_a_work_with_no_title_or_no_work_id_is_not_a_candidate(work: dict[str, Any]) -> None:
    assert candidate_from_work(work) is None


def test_the_work_id_is_read_from_the_url_or_bare() -> None:
    for spelling in ("https://openalex.org/W2741809807", "https://openalex.org/W2741809807/", "W2741809807"):
        candidate = candidate_from_work(a_work(id=spelling))
        assert candidate is not None
        assert candidate.provider_record_id == "W2741809807"
        assert candidate.identifiers.openalex_id == "W2741809807"


def test_the_url_is_the_landing_page_then_the_doi_then_the_openalex_record() -> None:
    landing = a_work(
        doi="https://doi.org/10.5555/x.1",
        primary_location={"landing_page_url": "https://publisher.example.org/x1"},
    )
    doi_only = a_work(doi="https://doi.org/10.5555/X.2", primary_location={"landing_page_url": "ftp://x"})
    neither = a_work(primary_location=None)
    assert [candidate_from_work(work).url for work in (landing, doi_only, neither)] == [  # type: ignore[union-attr]
        "https://publisher.example.org/x1",
        "https://doi.org/10.5555/x.2",
        "https://openalex.org/W100",
    ]


def test_a_doi_that_is_not_a_doi_is_dropped_rather_than_failing_the_work() -> None:
    candidate = candidate_from_work(a_work(doi="https://doi.org/not-a-doi"))
    assert candidate is not None
    assert candidate.identifiers.doi is None
    assert candidate.url == "https://openalex.org/W100"


@pytest.mark.parametrize(
    ("work", "expected"),
    [
        (
            a_work(
                best_oa_location={
                    "is_oa": True,
                    "pdf_url": "https://a.example.org/p.pdf",
                    "landing_page_url": "https://a.example.org/p",
                }
            ),
            "https://a.example.org/p.pdf",
        ),
        (
            a_work(
                best_oa_location={
                    "is_oa": True,
                    "pdf_url": None,
                    "landing_page_url": "https://a.example.org/p",
                }
            ),
            "https://a.example.org/p",
        ),
        (
            a_work(
                best_oa_location={"is_oa": False, "pdf_url": "https://a.example.org/closed.pdf"},
                open_access={"is_oa": True, "oa_url": "https://b.example.org/open"},
            ),
            "https://b.example.org/open",
        ),
        (
            a_work(
                best_oa_location=None, open_access={"is_oa": True, "oa_url": "https://b.example.org/open"}
            ),
            "https://b.example.org/open",
        ),
        (
            a_work(best_oa_location=None, open_access={"is_oa": False, "oa_url": "https://b.example.org/x"}),
            None,
        ),
        (a_work(best_oa_location={"is_oa": True, "pdf_url": "not a url"}), None),
        (a_work(), None),
    ],
    ids=[
        "best location pdf",
        "best location landing page",
        "closed best location falls back to oa_url",
        "no best location falls back to oa_url",
        "closed work",
        "unusable url",
        "nothing said",
    ],
)
def test_the_open_access_url_is_the_best_open_copy(work: dict[str, Any], expected: str | None) -> None:
    candidate = candidate_from_work(work)
    assert candidate is not None
    assert candidate.open_access_url == expected


@pytest.mark.parametrize(
    ("publication_date", "expected"),
    [
        ("2024-02-29", "2024-02-29T00:00:00+00:00"),
        ("2024-02-30", None),
        ("2024", None),
        (None, None),
        (20240229, None),
    ],
)
def test_the_publication_date_is_midnight_utc(publication_date: object, expected: str | None) -> None:
    candidate = candidate_from_work(a_work(publication_date=publication_date))
    assert candidate is not None
    assert (candidate.published_at.isoformat() if candidate.published_at else None) == expected


def test_authors_are_display_names_in_byline_order_and_unnamed_authors_are_left_out() -> None:
    work = a_work(
        authorships=[
            {"author": {"display_name": " First Person "}},
            {"author": {"display_name": None}, "raw_author_name": "Raw Name"},
            {"author": None},
            "not an authorship",
            {"author": {"display_name": "Last Person"}},
        ]
    )
    candidate = candidate_from_work(work)
    assert candidate is not None
    assert candidate.authors == ("First Person", "Last Person")


def test_the_venue_is_the_primary_locations_source_and_absent_without_one() -> None:
    named = candidate_from_work(a_work(primary_location={"source": {"display_name": "Invented Review"}}))
    unnamed = candidate_from_work(a_work(primary_location={"source": None}))
    assert named is not None and named.publication == "Invented Review"
    assert unnamed is not None and unnamed.publication is None

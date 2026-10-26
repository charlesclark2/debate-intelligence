"""The page metadata harvester on the synthetic fixture pages and on pages written for one rule (v1-e06-t01).

The harvester is :mod:`debate_core.retrieval.citation_harvest`, not a module of
`debate_core.evidence`: it reads JSON-LD through the walk it shares with the access classifier and
the HTML extractor (:mod:`debate_core.retrieval.json_ld`), and the layers contract keeps
`debate_core.evidence` from importing `debate_core.retrieval`. The task spec named
`debate_core.evidence` for both; the PM ruled on 2026-10-26 that the harvester and this file live in
retrieval (session report, Deviations).

Every expectation below is written by hand from the page it is about (working agreement 6). The four
pages are t04's synthetic news, think-tank and government samples, served at the addresses t06's
cassettes give them, and this task's journal landing page (`tests/fixtures/citation/README.md`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Final

import pytest

from debate_core.domain.enums import CitationFieldSource
from debate_core.retrieval.citation_harvest import (
    CitationCandidates,
    Harvested,
    StatedDate,
    harvest_page,
    harvest_url,
    parse_stated_date,
)

FIXTURES: Final = Path(__file__).resolve().parents[4] / "tests" / "fixtures"
HTML: Final = "text/html; charset=utf-8"

JSON_LD: Final = CitationFieldSource.JSON_LD
META_TAG: Final = CitationFieldSource.META_TAG
OPENGRAPH: Final = CitationFieldSource.OPENGRAPH
BYLINE: Final = CitationFieldSource.BYLINE
HEURISTIC: Final = CitationFieldSource.HEURISTIC

NEWS_URL: Final = (
    "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter"
)
NEWS_CANONICAL: Final = "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away"
THINK_TANK_URL: Final = "https://www.harwell-institute.example/research/opportunity-cost-of-de-extinction"
GOVERNMENT_URL: Final = "https://www.fosw.example.gov/news/2026/06/agency-announces-grants"
JOURNAL_URL: Final = "https://journal.synthetic-conservation.example/doi/10.5555/jscs.2026.0012"
JOURNAL_PDF_URL: Final = "https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012"


def harvested_fixture(path: str, url: str) -> CitationCandidates:
    return harvest_page((FIXTURES / path).read_bytes(), content_type=HTML, retrieved_url=url)


def page(body: str = "", head: str = "") -> bytes:
    return f"<!DOCTYPE html><html><head>{head}</head><body>{body}</body></html>".encode()


def harvested(body: str = "", head: str = "", url: str = "https://site.example/a") -> CitationCandidates:
    return harvest_page(page(body, head), content_type=HTML, retrieved_url=url)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def values[ValueT](candidates: tuple[Harvested[ValueT], ...]) -> list[tuple[ValueT, CitationFieldSource]]:
    return [(candidate.value, candidate.source) for candidate in candidates]


# --------------------------------------------------------------------------------------------
# The four fixture pages
# --------------------------------------------------------------------------------------------


def test_the_news_page_states_its_cite_in_json_ld_meta_tags_opengraph_and_a_byline() -> None:
    found = harvested_fixture("extraction/news-article.html", NEWS_URL)

    assert values(found.title) == [
        ("Scientists Say Mammoth Revival Is Years Away", JSON_LD),
        ("Scientists say mammoth revival is years away", OPENGRAPH),
        ("Scientists Say Mammoth Revival Is Years Away | The Daily Meridian", HEURISTIC),
    ]
    assert values(found.authors) == [
        (("Dana Whitfield",), JSON_LD),
        (("Dana Whitfield",), META_TAG),
        (("Dana Whitfield",), BYLINE),
    ]
    assert values(found.publication) == [("The Daily Meridian", JSON_LD), ("The Daily Meridian", OPENGRAPH)]
    assert values(found.published_at) == [
        (utc(2026, 9, 14, 12, 30), JSON_LD),
        (utc(2026, 9, 14, 12, 30), META_TAG),
        (utc(2026, 9, 14), HEURISTIC),
    ]
    assert values(found.canonical_url) == [(NEWS_CANONICAL, META_TAG), (NEWS_CANONICAL, HEURISTIC)]
    assert found.dois == ()


def test_a_job_title_after_a_byline_is_not_a_credential() -> None:
    """ "By Dana Whitfield, Science Correspondent" is a byline, not an author bio (ac3)."""
    found = harvested_fixture("extraction/news-article.html", NEWS_URL)

    assert found.author_credentials == ()


def test_the_think_tank_report_takes_its_credentials_from_the_author_bios() -> None:
    found = harvested_fixture("extraction/think-tank-report.html", THINK_TANK_URL)

    assert values(found.title) == [
        ("The Opportunity Cost of De-Extinction", JSON_LD),
        ("The Opportunity Cost of De-Extinction - Harwell Institute for Conservation Policy", HEURISTIC),
    ]
    assert values(found.authors) == [(("Marcus Ellery", "Hana Okafor"), JSON_LD)]
    assert values(found.author_credentials) == [
        (
            "Marcus Ellery is a senior fellow at the Harwell Institute. "
            "Hana Okafor directs its biodiversity program.",
            BYLINE,
        )
    ]
    assert values(found.publication) == [
        ("Harwell Institute", JSON_LD),
        ("Harwell Institute for Conservation Policy", OPENGRAPH),
    ]
    assert values(found.published_at) == [(utc(2026, 3, 3), JSON_LD)]
    assert found.published_at[0].raw == "March 3, 2026"
    assert values(found.canonical_url) == [(THINK_TANK_URL, META_TAG), (THINK_TANK_URL, HEURISTIC)]


def test_the_government_release_has_no_author_and_only_its_html_title() -> None:
    found = harvested_fixture("extraction/gov-press-release.html", GOVERNMENT_URL)

    assert values(found.title) == [
        ("Agency Announces Grants for Habitat Protection | Federal Office of Synthetic Wildlife", HEURISTIC)
    ]
    assert found.authors == ()
    assert found.author_credentials == ()
    assert values(found.publication) == [("Federal Office of Synthetic Wildlife", OPENGRAPH)]
    assert values(found.published_at) == [(utc(2026, 6, 2), META_TAG)]
    assert values(found.canonical_url) == [(GOVERNMENT_URL, META_TAG), (GOVERNMENT_URL, HEURISTIC)]


def test_the_journal_landing_page_states_its_cite_in_citation_meta_tags_and_its_doi() -> None:
    found = harvested_fixture("citation/journal-article-landing.html", JOURNAL_URL)

    title = "Moral Hazard and the Return of Lost Species"
    assert values(found.title) == [
        (title, META_TAG),
        (title, OPENGRAPH),
        (f"{title} | Journal of Synthetic Conservation Studies", HEURISTIC),
    ]
    assert values(found.authors) == [
        (("Okonkwo-Hale, R.", "Lindqvist, T."), META_TAG),
        (("R. Okonkwo-Hale", "T. Lindqvist"), BYLINE),
    ]
    assert values(found.publication) == [
        ("Journal of Synthetic Conservation Studies", META_TAG),
        ("Synthetic Conservation Press", OPENGRAPH),
    ]
    assert values(found.published_at) == [(utc(2026, 4, 20), META_TAG)]
    assert values(found.canonical_url) == [(JOURNAL_URL, META_TAG), (JOURNAL_URL, HEURISTIC)]
    assert found.dois == ("10.5555/jscs.2026.0012",)


def test_an_author_institution_meta_tag_is_not_a_credential() -> None:
    """`citation_author_institution` is not one of the three sources ac3 allows."""
    found = harvested_fixture("citation/journal-article-landing.html", JOURNAL_URL)

    assert found.author_credentials == ()


# --------------------------------------------------------------------------------------------
# Credentials: only an explicit bio or JSON-LD's jobTitle and affiliation (ac3)
# --------------------------------------------------------------------------------------------


def test_json_ld_job_title_and_affiliation_are_credentials_naming_the_author() -> None:
    script = (
        '<script type="application/ld+json">{"@type": "NewsArticle", "headline": "H", "author": ['
        '{"@type": "Person", "name": "Jane Smith", "jobTitle": "Professor of Hydrology",'
        ' "affiliation": {"@type": "Organization", "name": "University of Example"}},'
        '{"@type": "Person", "name": "Lee Park"},'
        '{"@type": "Person", "name": "Ana Ruiz", "affiliation": ["Example Lab", {"name": "Example U"}]}'
        "]}</script>"
    )

    found = harvested(head=script)

    assert values(found.author_credentials) == [
        (
            "Jane Smith, Professor of Hydrology, University of Example; Ana Ruiz, Example Lab, Example U",
            JSON_LD,
        )
    ]


def test_a_bio_that_names_no_author_of_the_page_is_not_a_credential() -> None:
    body = (
        '<div class="byline">By Jane Smith</div>'
        '<div class="author-bio"><p>Lee Park is a professor of hydrology.</p></div>'
    )

    assert harvested(body).author_credentials == ()


def test_only_the_bio_paragraphs_that_name_an_author_are_kept() -> None:
    body = (
        '<div class="byline">By Jane Smith</div>'
        '<div class="author-bio"><h3>About the author</h3>'
        "<p>Jane Smith is a professor of hydrology at Example University.</p>"
        "<p>Follow the newsletter for more.</p></div>"
    )

    assert values(harvested(body).author_credentials) == [
        ("Jane Smith is a professor of hydrology at Example University.", BYLINE)
    ]


def test_nothing_else_on_the_page_becomes_a_credential() -> None:
    """A description, a job title in the byline, an institution tag: none is a bio or JSON-LD."""
    head = (
        '<meta name="description" content="Jane Smith, professor of hydrology, explains.">'
        '<meta name="citation_author" content="Jane Smith">'
        '<meta name="citation_author_institution" content="Example University">'
    )
    body = '<div class="byline">By Jane Smith, Professor of Hydrology</div><p>Jane Smith is a professor.</p>'

    assert harvested(body, head).author_credentials == ()


# --------------------------------------------------------------------------------------------
# Bylines
# --------------------------------------------------------------------------------------------


def test_a_byline_without_links_is_split_into_names_before_the_first_comma() -> None:
    body = '<p class="byline">By Jane Smith and Lee Park, Staff Writers</p>'

    assert values(harvested(body).authors) == [(("Jane Smith", "Lee Park"), BYLINE)]


def test_byline_links_name_the_authors() -> None:
    body = (
        '<div class="byline">By <a href="/a">Jane Smith</a> &amp; <a href="/b">Lee Park</a> | Updated</div>'
    )

    assert values(harvested(body).authors) == [(("Jane Smith", "Lee Park"), BYLINE)]


def test_a_rel_author_link_names_an_author() -> None:
    body = '<p>Story by <a rel="author" href="/staff/jane">Jane Smith</a></p>'

    assert values(harvested(body).authors) == [(("Jane Smith",), BYLINE)]


def test_a_time_inside_a_byline_is_a_byline_date() -> None:
    body = '<div class="byline">By Jane Smith <time datetime="2026-02-01">Feb. 1</time></div>'

    assert values(harvested(body).published_at) == [(utc(2026, 2, 1), BYLINE)]


def test_a_time_outside_any_byline_is_not_a_date_source() -> None:
    body = '<div class="byline">By Jane Smith</div><time datetime="2026-02-01">Feb. 1</time>'

    assert harvested(body).published_at == ()


def test_a_meta_author_that_is_a_url_is_not_an_author() -> None:
    head = '<meta property="article:author" content="https://social.example/janesmith">'

    assert harvested(head=head).authors == ()


# --------------------------------------------------------------------------------------------
# JSON-LD and meta tags
# --------------------------------------------------------------------------------------------


def test_an_article_node_is_preferred_to_a_web_page_node() -> None:
    script = (
        '<script type="application/ld+json">{"@graph": ['
        '{"@type": "WebPage", "name": "Site page", "url": "https://site.example/page"},'
        '{"@type": "NewsArticle", "headline": "The story", "url": "https://site.example/story",'
        ' "isPartOf": {"@type": "Periodical", "name": "Example Weekly"},'
        ' "publisher": {"name": "Example Media"}}]}</script>'
    )

    found = harvested(head=script)

    assert values(found.title) == [("The story", JSON_LD)]
    assert values(found.publication) == [("Example Weekly", JSON_LD), ("Example Media", JSON_LD)]
    assert values(found.canonical_url)[0] == ("https://site.example/story", JSON_LD)


def test_meta_tag_names_are_read_in_any_case_and_in_their_listed_order() -> None:
    head = (
        '<meta name="DC.Title" content="Dublin Core title">'
        '<meta name="citation_title" content="Citation title">'
        '<meta name="citation_author" content="Jane Smith">'
        '<meta name="citation_author" content="Lee Park">'
        '<meta name="DC.creator" content="Ana Ruiz">'
    )

    found = harvested(head=head)

    assert values(found.title)[:2] == [("Citation title", META_TAG), ("Dublin Core title", META_TAG)]
    assert values(found.authors) == [(("Jane Smith", "Lee Park"), META_TAG), (("Ana Ruiz",), META_TAG)]


def test_a_relative_canonical_is_resolved_and_a_non_http_one_dropped() -> None:
    head = '<link rel="canonical" href="ftp://site.example/x"><meta property="og:url" content="/story">'

    found = harvested(head=head, url="https://site.example/story?utm_source=feed")

    assert values(found.canonical_url) == [
        ("https://site.example/story", OPENGRAPH),
        ("https://site.example/story", HEURISTIC),
    ]


def test_dois_come_from_the_metadata_and_the_url_never_the_body_text() -> None:
    head = (
        '<meta name="citation_doi" content="10.5555/first"><meta name="prism.doi" content="10.5555/second">'
    )
    body = "<p>See also https://doi.org/10.5555/in-the-body.</p>"

    found = harvested(body, head, url="https://journal.example/doi/10.5555/third")

    assert found.dois == ("10.5555/first", "10.5555/second", "10.5555/third")


def test_a_json_ld_identifier_names_a_doi() -> None:
    script = (
        '<script type="application/ld+json">{"@type": "ScholarlyArticle", "name": "T",'
        ' "identifier": {"@type": "PropertyValue", "propertyID": "doi", "value": "10.5555/ld"},'
        ' "sameAs": "https://doi.org/10.5555/same"}</script>'
    )

    assert harvested(head=script).dois == ("10.5555/ld", "10.5555/same")


# --------------------------------------------------------------------------------------------
# What is not a page, and the URL's own heuristics
# --------------------------------------------------------------------------------------------


def test_a_pdf_yields_only_what_its_url_says() -> None:
    found = harvest_page(
        (FIXTURES / "extraction/journal-article.pdf").read_bytes(),
        content_type="application/pdf",
        retrieved_url=JOURNAL_PDF_URL,
    )

    assert found == CitationCandidates(
        canonical_url=(Harvested(JOURNAL_PDF_URL, HEURISTIC, JOURNAL_PDF_URL),),
        dois=("10.5555/jscs.2026.0012",),
    )


def test_a_page_that_does_not_decode_yields_only_what_its_url_says() -> None:
    found = harvest_page(
        b"<html><head><title>T\xff\xfe</title></head></html>",
        content_type="text/html; charset=utf-8",
        retrieved_url="https://site.example/2026/01/02/story",
    )

    assert values(found.published_at) == [(utc(2026, 1, 2), HEURISTIC)]
    assert found.title == ()


def test_a_date_in_the_url_path_is_a_heuristic_and_a_partial_one_is_nothing() -> None:
    assert values(harvest_url("https://site.example/news/2026/03/14/story").published_at) == [
        (utc(2026, 3, 14), HEURISTIC)
    ]
    assert values(harvest_url("https://site.example/news/2026-03-14-story").published_at) == [
        (utc(2026, 3, 14), HEURISTIC)
    ]
    assert harvest_url("https://site.example/news/2026/03/story").published_at == ()
    assert harvest_url("https://site.example/news/2026/13/40/story").published_at == ()


def test_the_heuristic_canonical_url_is_the_retrieved_url_canonicalized() -> None:
    found = harvest_url("https://Site.Example/story?utm_source=feed")

    assert values(found.canonical_url) == [("https://site.example/story", HEURISTIC)]


# --------------------------------------------------------------------------------------------
# Dates as pages state them
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "moment", "calendar"),
    [
        ("2026-09-14T08:30:00-04:00", utc(2026, 9, 14, 12, 30), date(2026, 9, 14)),
        ("2026-09-14T22:30:00-04:00", utc(2026, 9, 15, 2, 30), date(2026, 9, 14)),
        ("2026-09-14T08:30:00Z", utc(2026, 9, 14, 8, 30), date(2026, 9, 14)),
        ("2026-09-14T08:30:00", utc(2026, 9, 14), date(2026, 9, 14)),
        ("2026-06-02", utc(2026, 6, 2), date(2026, 6, 2)),
        ("2026/04/20", utc(2026, 4, 20), date(2026, 4, 20)),
        ("March 3, 2026", utc(2026, 3, 3), date(2026, 3, 3)),
        ("Sept. 14, 2026", utc(2026, 9, 14), date(2026, 9, 14)),
        ("3 March 2026", utc(2026, 3, 3), date(2026, 3, 3)),
        ("  2026-06-02  ", utc(2026, 6, 2), date(2026, 6, 2)),
    ],
)
def test_a_stated_date_keeps_the_instant_in_utc_and_the_day_the_page_named(
    text: str, moment: datetime, calendar: date
) -> None:
    assert parse_stated_date(text) == StatedDate(moment, calendar)


@pytest.mark.parametrize(
    "text", ["2026", "2026-04", "April 2026", "2026-02-30", "yesterday", "", "14/09/2026", "2026-09-14T25:00"]
)
def test_a_partial_impossible_or_ambiguous_date_is_no_date(text: str) -> None:
    """A year or a month alone would have to be given a day the page never stated."""
    assert parse_stated_date(text) is None


def test_an_offset_is_kept_only_to_name_the_day() -> None:
    stated = parse_stated_date("2026-09-14T22:30:00-04:00")

    assert stated is not None
    assert stated.moment.tzinfo is UTC
    assert stated.moment.astimezone(timezone(timedelta(hours=-4))).date() == stated.calendar_date


def test_a_bio_must_name_the_author_as_whole_words() -> None:
    """An agency byline "AP" is not named by a bio about an "APPLE" grower."""
    body = '<div class="byline">By AP</div><div class="bio"><p>The APPLE growers are a co-op.</p></div>'

    assert harvested(body).author_credentials == ()

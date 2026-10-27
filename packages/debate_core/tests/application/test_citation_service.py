"""CitationService: per-field provenance, Crossref preferred, cites formatted, student edits kept.

ac1: every field of each fixture page's cite matches the hand-written `<case>.expected.json` in
`tests/fixtures/citation/` (value, source and verified flag). ac2: a DOI is looked up once, Crossref is
preferred for title, container, date and authors, and a failure degrades to the page's metadata.
ac3: credentials only from a bio, JSON-LD or Crossref affiliations. ac4: `format_cite`. ac5: a cite
field a student changed is verified on re-resolution only when it equals the derived value.

Task v1-e06-t01. Everything is offline: the pages are synthetic, Crossref is respx (`citation_world.py`).
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Final, cast

import httpx
import pytest
from tests.fixtures.citation.citation_world import (
    CASES,
    JOURNAL_DOI,
    RETRIEVED_AT,
    CitationWorld,
    load_case,
)

from debate_core.application.citation_service import (
    CITATION_FIELD_NAMES,
    SOURCE_PRECEDENCE,
    CitationResolution,
    CrossrefOutcome,
    format_cite,
    keep_student_edits,
    resolve_citation,
)
from debate_core.application.ports.doi_metadata import DoiAuthor, DoiDate, DoiWork
from debate_core.domain import Card, Citation, CitationField, ProvenanceMode, VerificationStatus
from debate_core.domain.enums import CitationFieldSource
from debate_core.evidence.edits import EditCite
from debate_core.retrieval.citation_harvest import CitationCandidates, Harvested

pytestmark = pytest.mark.anyio

CROSSREF: Final = CitationFieldSource.CROSSREF
JSON_LD: Final = CitationFieldSource.JSON_LD
META_TAG: Final = CitationFieldSource.META_TAG
OPENGRAPH: Final = CitationFieldSource.OPENGRAPH
BYLINE: Final = CitationFieldSource.BYLINE
HEURISTIC: Final = CitationFieldSource.HEURISTIC
RETRIEVAL: Final = CitationFieldSource.RETRIEVAL
MISSING: Final = CitationFieldSource.MISSING
PUBLISHER: Final = ProvenanceMode.PUBLISHER_RETRIEVED
USER_SUPPLIED: Final = ProvenanceMode.USER_SUPPLIED
STUDENT: Final = "0ACT0R00000000000000000001"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world() -> CitationWorld:
    return CitationWorld()


def triples(citation: Citation) -> dict[str, tuple[object, str, bool]]:
    """Each field as (value, source, verified), with values in the expected files' JSON shapes."""
    found: dict[str, tuple[object, str, bool]] = {}
    for name in CITATION_FIELD_NAMES:
        field: CitationField[Any] = getattr(citation, name)
        value: object = field.value
        if isinstance(value, datetime):
            value = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        elif isinstance(value, tuple):
            value = list(cast(tuple[object, ...], value))
        found[name] = (value, field.source.value, field.verified)
    return found


def expected_triples(case: dict[str, Any]) -> dict[str, tuple[object, str, bool]]:
    stated: dict[str, dict[str, Any]] = case["citation"]
    return {
        name: (stated[name]["value"], stated[name]["source"], stated[name]["verified"])
        for name in CITATION_FIELD_NAMES
    }


async def resolved(world: CitationWorld, case: str) -> CitationResolution:
    article, source = await world.add_case(case)
    return await world.service.resolve(article, source)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def field[ValueT](
    value: ValueT, source: CitationFieldSource, verified: bool = False
) -> CitationField[ValueT]:
    return CitationField[ValueT](value=value, source=source, verified=verified)


# --------------------------------------------------------------------------------------------
# ac1: each fixture page's cite, field by field
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
async def test_every_cite_field_has_the_value_source_and_flag_the_fixture_expects(
    world: CitationWorld, case: str
) -> None:
    expected = load_case(case)

    resolution = await resolved(world, case)

    assert triples(resolution.citation) == expected_triples(expected)
    assert resolution.doi == expected["doi"]
    assert resolution.crossref.value == expected["crossref"]
    assert resolution.provenance_mode.value == expected["provenance_mode"]
    assert resolution.citation.authors_are_organizations is expected.get("authors_are_organizations", False)


async def test_the_raw_text_each_value_was_read_from_is_kept(world: CitationWorld) -> None:
    resolution = await resolved(world, "think-tank-report")

    assert resolution.citation.published_at.raw == "March 3, 2026"
    assert resolution.citation.accessed_at.raw == "2026-10-26T15:00:00+00:00"


# --------------------------------------------------------------------------------------------
# ac2: Crossref, once per DOI, preferred, and never a reason to fail
# --------------------------------------------------------------------------------------------


async def test_a_doi_is_looked_up_once_however_many_times_its_cite_is_resolved(world: CitationWorld) -> None:
    article, source = await world.add_case("journal-article-landing")
    pdf_article, pdf = await world.add_case("open-access-pdf")

    await world.service.resolve(article, source)
    await world.service.resolve(article, source)
    second = await world.service.resolve(pdf_article, pdf)

    assert second.crossref is CrossrefOutcome.FOUND
    assert len(world.crossref.requests) == 1


async def test_crossref_is_preferred_to_the_pages_own_meta_tags(world: CitationWorld) -> None:
    """The landing page says "Okonkwo-Hale, R."; the deposit says "Rhea Okonkwo-Hale"."""
    citation = (await resolved(world, "journal-article-landing")).citation

    authors = citation.authors
    assert (authors.value, authors.source, authors.verified) == (
        ("Rhea Okonkwo-Hale", "Tomas Lindqvist"),
        CROSSREF,
        True,
    )
    for name in ("title", "publication", "published_at"):
        assert getattr(citation, name).source is CROSSREF, name
    assert citation.canonical_url.source is META_TAG


PAGE_METADATA_OF_THE_JOURNAL: Final = {
    "authors": (["Okonkwo-Hale, R.", "Lindqvist, T."], "meta_tag", True),
    "author_credentials": (None, "missing", False),
    "title": ("Moral Hazard and the Return of Lost Species", "meta_tag", True),
    "publication": ("Journal of Synthetic Conservation Studies", "meta_tag", True),
    "published_at": ("2026-04-20T00:00:00Z", "meta_tag", True),
    "canonical_url": (
        "https://journal.synthetic-conservation.example/doi/10.5555/jscs.2026.0012",
        "meta_tag",
        True,
    ),
    "accessed_at": ("2026-10-26T15:00:00Z", "retrieval", True),
}
"""The landing page's cite with no Crossref answer, written by hand from the page."""


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
async def test_a_crossref_transport_failure_degrades_to_the_page_metadata(
    world: CitationWorld, failure: type[httpx.TransportError]
) -> None:
    world.crossref.failure = failure

    resolution = await resolved(world, "journal-article-landing")

    assert resolution.crossref is CrossrefOutcome.FAILED
    assert triples(resolution.citation) == PAGE_METADATA_OF_THE_JOURNAL


@pytest.mark.parametrize(
    ("status", "content"), [(500, b"{}"), (429, b"{}"), (200, b"not json"), (200, b'{"status": "failed"}')]
)
async def test_a_crossref_error_answer_degrades_to_the_page_metadata(
    world: CitationWorld, status: int, content: bytes
) -> None:
    world.crossref.answer(JOURNAL_DOI, status, content)

    resolution = await resolved(world, "journal-article-landing")

    assert resolution.crossref is CrossrefOutcome.FAILED
    assert triples(resolution.citation) == PAGE_METADATA_OF_THE_JOURNAL


async def test_a_doi_crossref_does_not_hold_cites_from_the_page(world: CitationWorld) -> None:
    world.crossref.answer(JOURNAL_DOI, 404)

    resolution = await resolved(world, "journal-article-landing")

    assert resolution.crossref is CrossrefOutcome.NOT_REGISTERED
    assert triples(resolution.citation) == PAGE_METADATA_OF_THE_JOURNAL


async def test_with_no_doi_lookup_wired_the_page_metadata_is_the_cite() -> None:
    world = CitationWorld(with_crossref=False)

    resolution = await resolved(world, "journal-article-landing")

    assert resolution.crossref is CrossrefOutcome.NOT_CONFIGURED
    assert resolution.doi == JOURNAL_DOI
    assert triples(resolution.citation) == PAGE_METADATA_OF_THE_JOURNAL
    assert world.crossref.requests == []


async def test_a_failed_lookup_is_logged_without_raising(
    world: CitationWorld, caplog: pytest.LogCaptureFixture
) -> None:
    world.crossref.failure = httpx.ConnectError

    with caplog.at_level(logging.WARNING, logger="debate_core.application.citation_service"):
        await resolved(world, "journal-article-landing")

    (record,) = [r for r in caplog.records if r.name == "debate_core.application.citation_service"]
    assert record.levelno == logging.WARNING
    assert getattr(record, "doi", None) == JOURNAL_DOI


async def test_the_articles_own_doi_is_looked_up_when_the_page_states_none(world: CitationWorld) -> None:
    article, _ = await world.add_case("news-article")
    article = article.evolve(identifiers=article.identifiers.evolve(doi=JOURNAL_DOI))
    source = await world.add_snapshot(
        article, b"<html><head></head><body></body></html>", article.canonical_url
    )

    resolution = await world.service.resolve(article, source)

    assert resolution.doi == JOURNAL_DOI
    assert resolution.citation.title.source is CROSSREF


def work(**changes: Any) -> DoiWork:
    base = DoiWork(
        doi=JOURNAL_DOI,
        title="Deposited title",
        container_title="Deposited Journal",
        authors=(
            DoiAuthor(given="Rhea", family="Okonkwo-Hale", affiliations=("University of Synthetic Studies",)),
        ),
        dates=(DoiDate(kind="published", year=2026, month=4, day=20),),
    )
    return base.evolve(**changes)


PAGE: Final = CitationCandidates(
    authors=(Harvested(("Page Author",), META_TAG, "Page Author"),),
    author_credentials=(Harvested("Page Author is a fellow.", BYLINE, "Page Author is a fellow."),),
    title=(Harvested("Page title", META_TAG, "Page title"),),
    publication=(Harvested("Page Journal", META_TAG, "Page Journal"),),
    published_at=(Harvested(utc(2026, 4, 1), META_TAG, "2026-04-01"),),
    canonical_url=(Harvested("https://journal.example/a", META_TAG, "https://journal.example/a"),),
)


def resolve(
    candidates: CitationCandidates, deposit: DoiWork | None, mode: ProvenanceMode = PUBLISHER
) -> Citation:
    return resolve_citation(candidates, deposit, provenance_mode=mode, accessed_at=RETRIEVED_AT)


def test_a_field_the_deposit_leaves_out_comes_from_the_page() -> None:
    citation = resolve(PAGE, work(container_title=None, authors=()))

    assert citation.title.value == "Deposited title"
    assert citation.publication == CitationField[str](
        value="Page Journal", source=META_TAG, verified=True, raw="Page Journal"
    )
    assert citation.authors.value == ("Page Author",)
    assert citation.author_credentials.value == "Page Author is a fellow."


def test_a_deposit_date_without_a_day_is_not_used() -> None:
    month_only = work(dates=(DoiDate(kind="published", year=2026, month=4),))

    assert resolve(PAGE, month_only).published_at.value == utc(2026, 4, 1)
    assert resolve(PAGE, month_only).published_at.source is META_TAG


def test_the_first_whole_deposit_date_is_used() -> None:
    dates = (
        DoiDate(kind="published", year=2026),
        DoiDate(kind="published-online", year=2026, month=5, day=2),
    )

    published = resolve(PAGE, work(dates=dates)).published_at

    assert (published.value, published.source, published.raw) == (utc(2026, 5, 2), CROSSREF, "2026-05-02")


def test_a_deposited_author_with_no_name_is_left_out() -> None:
    authors = (DoiAuthor(given="Only a given name"), DoiAuthor(family="Lindqvist"))

    assert resolve(PAGE, work(authors=authors)).authors.value == ("Lindqvist",)


# --------------------------------------------------------------------------------------------
# Precedence and the verified flag
# --------------------------------------------------------------------------------------------


PAGE_SOURCES: Final = SOURCE_PRECEDENCE[1:]


def test_the_precedence_is_crossref_json_ld_meta_tag_opengraph_byline_retrieval_heuristic() -> None:
    assert SOURCE_PRECEDENCE == (CROSSREF, JSON_LD, META_TAG, OPENGRAPH, BYLINE, RETRIEVAL, HEURISTIC)


@pytest.mark.parametrize(
    ("higher", "lower"),
    list(zip(PAGE_SOURCES, PAGE_SOURCES[1:], strict=False)),
    ids=lambda source: source.value,
)
def test_a_higher_source_wins_wherever_it_is_listed(
    higher: CitationFieldSource, lower: CitationFieldSource
) -> None:
    for name in ("title", "publication", "author_credentials"):
        listed = (Harvested("lower", lower, "lower"), Harvested("higher", higher, "higher"))
        candidates = replace(CitationCandidates(), **{name: listed})

        chosen: CitationField[str] = getattr(resolve(candidates, None), name)

        assert (chosen.value, chosen.source) == ("higher", higher), name


@pytest.mark.parametrize("lower", PAGE_SOURCES, ids=lambda source: source.value)
def test_crossref_wins_over_every_page_source(lower: CitationFieldSource) -> None:
    candidates = CitationCandidates(title=(Harvested("Page title", lower, "Page title"),))

    assert resolve(candidates, work()).title.source is CROSSREF


def test_within_one_source_the_first_candidate_wins() -> None:
    candidates = CitationCandidates(
        published_at=(Harvested(utc(2026, 1, 2), META_TAG, "a"), Harvested(utc(2026, 1, 3), META_TAG, "b"))
    )

    assert resolve(candidates, None).published_at.value == utc(2026, 1, 2)


@pytest.mark.parametrize("source", SOURCE_PRECEDENCE[:-1], ids=lambda source: source.value)
def test_every_explicit_source_verifies_a_publisher_retrieved_value(source: CitationFieldSource) -> None:
    deposit = work() if source is CROSSREF else None
    candidates = CitationCandidates(
        title=(Harvested("A title", source, "A title"),) if source is not CROSSREF else ()
    )

    title = resolve(candidates, deposit).title

    assert title.source is source
    assert title.verified


def test_a_heuristic_value_is_never_verified() -> None:
    """A date read from a URL slug is a guess (forbidden: marking a heuristic verified)."""
    candidates = CitationCandidates(
        title=(Harvested("Title | Site", HEURISTIC, "Title | Site"),),
        published_at=(Harvested(utc(2026, 3, 14), HEURISTIC, "2026/03/14"),),
        canonical_url=(
            Harvested("https://site.example/2026/03/14/a", HEURISTIC, "https://site.example/2026/03/14/a"),
        ),
    )

    citation = resolve(candidates, None)

    for name in ("title", "published_at", "canonical_url"):
        assert getattr(citation, name).source is HEURISTIC, name
        assert not getattr(citation, name).verified, name


@pytest.mark.parametrize("mode", [mode for mode in ProvenanceMode if mode is not PUBLISHER], ids=str)
def test_no_field_is_verified_unless_the_platform_retrieved_the_source(mode: ProvenanceMode) -> None:
    """A user's text is not the publisher's page, so not even Crossref's answer about its DOI verifies it."""
    citation = resolve(PAGE, work(), mode)

    assert citation.title.source is CROSSREF
    assert not any(getattr(citation, name).verified for name in CITATION_FIELD_NAMES)


async def test_a_user_supplied_snapshot_with_a_doi_in_its_url_is_cited_from_crossref_unverified(
    world: CitationWorld,
) -> None:
    article, _ = await world.add_case("user-supplied")
    url = f"https://journal.synthetic-conservation.example/doi/{JOURNAL_DOI}"
    source = await world.add_snapshot(
        article, b"Pasted text.", url, USER_SUPPLIED, "text/plain; charset=utf-8"
    )

    resolution = await world.service.resolve(article, source)

    assert resolution.provenance_mode is USER_SUPPLIED
    assert resolution.citation.title.source is CROSSREF
    assert not any(getattr(resolution.citation, name).verified for name in CITATION_FIELD_NAMES)
    assert format_cite(resolution.citation, provenance_mode=USER_SUPPLIED).full_cite.endswith(
        "; user-supplied text]"
    )


def test_nothing_found_is_missing_and_unverified() -> None:
    citation = resolve(CitationCandidates(), None)

    for name in CITATION_FIELD_NAMES[:-1]:
        assert getattr(citation, name) == CitationField[Any](), name


async def test_a_snapshot_of_another_article_is_refused(world: CitationWorld) -> None:
    article, _ = await world.add_case("news-article")
    _, other = await world.add_case("think-tank-report")

    with pytest.raises(ValueError, match="snapshot"):
        await world.service.resolve(article, other)


# --------------------------------------------------------------------------------------------
# ac3: credentials only when the source states them
# --------------------------------------------------------------------------------------------


def test_crossref_affiliations_are_credentials_naming_each_person_author() -> None:
    """Changed by v1-e06-t02 (ac5): a deposited organization is not an author beside named people,
    so its affiliation is no author's credential."""
    authors = (
        DoiAuthor(
            given="Rhea", family="Okonkwo-Hale", affiliations=("Dept. of Ecology", "Synthetic University")
        ),
        DoiAuthor(given="Tomas", family="Lindqvist"),
        DoiAuthor(name="Synthetic Consortium", affiliations=("Example Lab",)),
    )

    citation = resolve(CitationCandidates(), work(authors=authors))

    credentials = citation.author_credentials
    assert (credentials.value, credentials.source, credentials.verified) == (
        "Rhea Okonkwo-Hale, Dept. of Ecology, Synthetic University",
        CROSSREF,
        True,
    )
    assert citation.authors.value == ("Rhea Okonkwo-Hale", "Tomas Lindqvist")
    assert not citation.authors_are_organizations


def test_crossref_credentials_are_preferred_to_a_bio() -> None:
    assert resolve(PAGE, work()).author_credentials.source is CROSSREF


def test_a_deposit_with_no_affiliation_leaves_the_bio() -> None:
    no_affiliation = work(authors=(DoiAuthor(given="Rhea", family="Okonkwo-Hale"),))

    assert resolve(PAGE, no_affiliation).author_credentials.source is BYLINE


async def test_a_source_stating_no_credentials_gets_a_cite_with_no_qualification(
    world: CitationWorld,
) -> None:
    citation = (await resolved(world, "news-article")).citation

    assert citation.author_credentials == CitationField[str]()
    assert "Correspondent" not in format_cite(citation, provenance_mode=PUBLISHER).full_cite


# --------------------------------------------------------------------------------------------
# ac4: format_cite
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
async def test_each_fixture_cite_formats_as_the_fixture_expects(world: CitationWorld, case: str) -> None:
    expected = load_case(case)
    resolution = await resolved(world, case)

    cite = format_cite(resolution.citation, provenance_mode=resolution.provenance_mode)

    assert cite.short_cite == expected["short_cite"]
    assert cite.full_cite == expected["full_cite"]
    assert list(cite.unverified_fields) == expected["unverified_fields"]
    assert list(cite.missing_fields) == expected["missing_fields"]
    assert cite.provenance_mode is resolution.provenance_mode


def cite_of(**fields: CitationField[Any]) -> Citation:
    return Citation(**fields)


@pytest.mark.parametrize(
    ("authors", "short"),
    [
        (("Jane Smith",), "Smith 26"),
        (("Jane Smith", "Lee Park"), "Smith et al. 26"),
        (("Smith, Jane",), "Smith 26"),
        (("Martin Luther King Jr.",), "King 26"),
        (("Ana Ruiz III",), "Ruiz 26"),
        (("Plato",), "Plato 26"),
    ],
)
def test_the_short_cite_is_the_first_authors_last_name_and_the_year(
    authors: tuple[str, ...], short: str
) -> None:
    citation = cite_of(
        authors=field(authors, META_TAG, True), published_at=field(utc(2026, 1, 1), META_TAG, True)
    )

    assert format_cite(citation, provenance_mode=PUBLISHER).short_cite == short


def test_with_no_author_the_short_cite_names_the_publication_then_the_title() -> None:
    year = field(utc(2009, 1, 1), META_TAG, True)

    with_publication = cite_of(
        publication=field("Example Weekly", OPENGRAPH, True), title=field("T", META_TAG), published_at=year
    )
    with_title = cite_of(title=field("The story", META_TAG, True), published_at=year)
    with_nothing = cite_of(published_at=year)

    assert format_cite(with_publication, provenance_mode=PUBLISHER).short_cite == "Example Weekly 09"
    assert format_cite(with_title, provenance_mode=PUBLISHER).short_cite == "The story 09"
    assert format_cite(with_nothing, provenance_mode=PUBLISHER).short_cite == "[no author] 09"


def test_with_no_date_the_short_cite_says_no_date() -> None:
    citation = cite_of(authors=field(("Jane Smith",), BYLINE, True))

    assert format_cite(citation, provenance_mode=PUBLISHER).short_cite == "Smith ND"


def test_the_cite_prints_the_day_the_page_named_not_the_utc_day() -> None:
    """22:30 at -04:00 on the 14th is 02:30 UTC on the 15th; the page said the 14th."""
    citation = cite_of(
        authors=field(("Jane Smith",), BYLINE, True),
        published_at=CitationField[datetime](
            value=utc(2026, 9, 15, 2, 30), source=META_TAG, verified=True, raw="2026-09-14T22:30:00-04:00"
        ),
    )

    assert "; September 14, 2026" in format_cite(citation, provenance_mode=PUBLISHER).full_cite


def test_the_full_cite_lists_three_or_more_authors_with_commas() -> None:
    citation = cite_of(authors=field(("A One", "B Two", "C Three"), JSON_LD, True))

    assert (
        format_cite(citation, provenance_mode=PUBLISHER).full_cite
        == "One et al. ND [A One, B Two, and C Three]"
    )


def test_every_shown_field_that_is_not_verified_is_flagged() -> None:
    citation = cite_of(
        authors=field(("Jane Smith",), BYLINE, False),
        title=field("Title | Site", HEURISTIC),
        publication=field("Example Weekly", OPENGRAPH, True),
    )

    cite = format_cite(citation, provenance_mode=PUBLISHER)

    assert cite.unverified_fields == ("authors", "title")
    assert cite.missing_fields == ("author_credentials", "published_at", "canonical_url", "accessed_at")


@pytest.mark.parametrize(
    ("mode", "note"),
    [
        (USER_SUPPLIED, "user-supplied text"),
        (ProvenanceMode.PASTED, "pasted text"),
        (ProvenanceMode.FILE_IMPORT, "imported from a debate file"),
    ],
)
def test_where_the_text_came_from_is_in_the_cite_unless_the_platform_retrieved_it(
    mode: ProvenanceMode, note: str
) -> None:
    citation = cite_of(title=field("T", HEURISTIC))

    assert format_cite(citation, provenance_mode=mode).full_cite == f'T ND ["T"; {note}]'
    assert format_cite(citation, provenance_mode=PUBLISHER).full_cite == 'T ND ["T"]'


# --------------------------------------------------------------------------------------------
# ac5: a student's cite edit is verified only when it is what the source says
# --------------------------------------------------------------------------------------------


async def card_with_derived_cite(world: CitationWorld, case: str = "think-tank-report") -> Card:
    article, source = await world.add_case(case)
    resolution = await world.service.resolve(article, source)
    return await world.stored_card(source, resolution.citation)


async def edited(world: CitationWorld, card: Card, **fields: CitationField[Any]) -> Card:
    result = await world.edits.edit(
        card.card_id,
        EditCite(card.citation.evolve(**fields)),
        expected_revision=card.revision,
        actor_id=STUDENT,
    )
    return result.card


async def test_a_changed_field_that_differs_from_the_source_is_kept_unverified_and_marked(
    world: CitationWorld,
) -> None:
    card = await card_with_derived_cite(world)
    student_title = field("De-extinction's hidden bill", BYLINE)
    card = await edited(world, card, title=student_title)

    resolution = await world.service.re_resolve(card)

    assert resolution.citation.title == student_title
    assert resolution.student_fields == ("title",)
    assert resolution.citation.authors == card.citation.authors
    assert (
        "title"
        in format_cite(resolution.citation, provenance_mode=resolution.provenance_mode).unverified_fields
    )


async def test_a_changed_field_equal_to_the_derived_value_is_verified(world: CitationWorld) -> None:
    card = await card_with_derived_cite(world)
    derived_title = card.citation.title
    card = await edited(world, card, title=field("A placeholder", BYLINE))
    card = await edited(world, card, title=field(derived_title.value, HEURISTIC))
    assert not card.citation.title.verified

    resolution = await world.service.re_resolve(card)

    assert resolution.citation.title == derived_title
    assert resolution.citation.title.verified
    assert resolution.student_fields == ()


async def test_a_re_resolved_cite_that_matches_the_source_lets_the_card_verify_again(
    world: CitationWorld,
) -> None:
    card = await card_with_derived_cite(world)
    card = await edited(world, card, title=field(card.citation.title.value, HEURISTIC))
    assert card.verification_status is VerificationStatus.UNVERIFIED

    resolution = await world.service.re_resolve(card)
    recorded, verdict = await world.verifier.verify_and_record(card.evolve(citation=resolution.citation))

    assert verdict.is_verified
    assert recorded.verification_status is VerificationStatus.VERIFIED


async def test_a_changed_field_equal_to_a_heuristic_value_stays_unverified(world: CitationWorld) -> None:
    card = await card_with_derived_cite(world, "government-press-release")
    heuristic_title = card.citation.title
    card = await edited(world, card, title=field(heuristic_title.value, BYLINE))

    resolution = await world.service.re_resolve(card)

    assert resolution.citation.title == heuristic_title
    assert not resolution.citation.title.verified


async def test_only_the_changed_fields_are_kept(world: CitationWorld) -> None:
    card = await card_with_derived_cite(world)
    derived = card.citation
    card = await edited(
        world, card, title=field("Student title", BYLINE), publication=field("Student publication", BYLINE)
    )

    resolution = await world.service.re_resolve(card)

    assert resolution.student_fields == ("title", "publication")
    for name in ("authors", "author_credentials", "published_at", "canonical_url", "accessed_at"):
        assert getattr(resolution.citation, name) == getattr(derived, name), name


async def test_a_card_never_cite_edited_takes_the_derived_cite_whole(world: CitationWorld) -> None:
    """An unverified value no student wrote is the service's own, from an earlier resolution."""
    article, source = await world.add_case("journal-article-landing")
    stale = Citation(title=field("Moral hazard and lost species", HEURISTIC))
    card = await world.stored_card(source, stale)

    resolution = await world.service.re_resolve(card)

    assert resolution.citation == (await world.service.resolve(article, source)).citation
    assert resolution.student_fields == ()


async def test_a_field_the_student_emptied_is_derived_again(world: CitationWorld) -> None:
    card = await card_with_derived_cite(world)
    card = await edited(world, card, author_credentials=CitationField[str]())

    resolution = await world.service.re_resolve(card)

    assert resolution.citation.author_credentials.source is BYLINE
    assert resolution.student_fields == ()


async def test_a_card_with_no_snapshot_has_no_source_to_re_resolve_from(world: CitationWorld) -> None:
    article, _ = await world.add_case("news-article")
    blank = await world.cards.create(
        Card(owner_id=STUDENT, article_id=article.article_id, tag="A tag", provenance_mode=PUBLISHER)
    )

    with pytest.raises(ValueError, match="snapshot"):
        await world.service.re_resolve(blank)


def test_keep_student_edits_takes_the_derived_field_whenever_the_values_match() -> None:
    derived = Citation(title=field("Same", JSON_LD, True), publication=field("Derived", OPENGRAPH, True))
    stored = Citation(title=field("Same", BYLINE), publication=field("Student", BYLINE))

    kept, student_fields = keep_student_edits(stored, derived)

    assert kept.title == derived.title
    assert kept.publication == stored.publication
    assert student_fields == ("publication",)


def test_keep_student_edits_never_keeps_a_value_marked_verified() -> None:
    """Only the service verifies; a verified stored value that differs is an older derivation."""
    derived = Citation(title=field("New", JSON_LD, True))
    stored = Citation(title=field("Old", META_TAG, True))

    assert keep_student_edits(stored, derived) == (derived, ())


def test_the_expected_files_name_every_field() -> None:
    for case in CASES:
        assert set(load_case(case)["citation"]) == set(CITATION_FIELD_NAMES), case
    assert json.dumps(CITATION_FIELD_NAMES)


# --------------------------------------------------------------------------------------------
# v1-e06-t02 ac5: the platform's own retrieval record is a source, verified only when the
# platform retrieved the text
# --------------------------------------------------------------------------------------------


async def test_the_accessed_date_of_a_publisher_retrieved_snapshot_is_a_verified_retrieval_value(
    world: CitationWorld,
) -> None:
    resolution = await resolved(world, "news-article")

    assert resolution.citation.accessed_at == CitationField[datetime](
        value=RETRIEVED_AT, source=RETRIEVAL, verified=True, raw="2026-10-26T15:00:00+00:00"
    )


async def test_a_canonical_less_url_of_a_publisher_retrieved_snapshot_is_a_verified_retrieval_value(
    world: CitationWorld,
) -> None:
    resolution = await resolved(world, "open-access-pdf")

    url = resolution.citation.canonical_url
    assert (url.value, url.source, url.verified) == (
        "https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012",
        RETRIEVAL,
        True,
    )
    assert resolution.citation.is_fully_verified


@pytest.mark.parametrize(
    "mode", [mode for mode in ProvenanceMode if mode is not ProvenanceMode.PUBLISHER_RETRIEVED]
)
def test_retrieval_values_of_text_the_platform_did_not_retrieve_are_unverified(mode: ProvenanceMode) -> None:
    candidates = CitationCandidates(
        canonical_url=(Harvested("https://site.example/story", RETRIEVAL, "https://site.example/story"),)
    )

    citation = resolve_citation(candidates, None, provenance_mode=mode, accessed_at=RETRIEVED_AT)

    for name in ("canonical_url", "accessed_at"):
        field_: CitationField[Any] = getattr(citation, name)
        assert (field_.source, field_.verified) == (RETRIEVAL, False), name


def test_a_page_canonical_url_outranks_the_retrieval_record() -> None:
    candidates = CitationCandidates(
        canonical_url=(
            Harvested("https://site.example/story", RETRIEVAL, "https://site.example/story?x=1"),
            Harvested("https://site.example/canonical", BYLINE, "https://site.example/canonical"),
        )
    )

    url = resolve(candidates, None).canonical_url

    assert (url.value, url.source) == ("https://site.example/canonical", BYLINE)


# --------------------------------------------------------------------------------------------
# v1-e06-t02 ac5: an organization stands in as the author only when no person is named
# --------------------------------------------------------------------------------------------

ORGANIZATION: Final = Harvested(("Synthetic Policy Office",), JSON_LD, "Synthetic Policy Office")


def test_an_organization_stands_in_as_the_author_when_no_person_is_named() -> None:
    citation = resolve(CitationCandidates(organization_authors=(ORGANIZATION,)), None)

    assert citation.authors == CitationField[tuple[str, ...]](
        value=("Synthetic Policy Office",), source=JSON_LD, verified=True, raw="Synthetic Policy Office"
    )
    assert citation.authors_are_organizations


@pytest.mark.parametrize("source", [META_TAG, BYLINE, JSON_LD])
def test_an_organization_never_stands_in_beside_a_named_person(source: CitationFieldSource) -> None:
    person = Harvested(("Ana Ruiz",), source, "Ana Ruiz")

    citation = resolve(CitationCandidates(authors=(person,), organization_authors=(ORGANIZATION,)), None)

    assert (citation.authors.value, citation.authors.source) == (("Ana Ruiz",), source)
    assert not citation.authors_are_organizations


def test_a_crossref_author_with_a_name_and_no_family_name_is_an_organization() -> None:
    deposit = work(authors=(DoiAuthor(name="Synthetic Consortium", affiliations=("Example Lab",)),))

    citation = resolve(CitationCandidates(organization_authors=(ORGANIZATION,)), deposit)

    assert (citation.authors.value, citation.authors.source) == (("Synthetic Consortium",), CROSSREF)
    assert citation.authors_are_organizations
    assert citation.author_credentials.value is None


def test_a_crossref_person_outranks_a_page_organization_and_a_page_person_a_crossref_organization() -> None:
    person_deposit = work(authors=(DoiAuthor(given="Rhea", family="Okonkwo-Hale"),))
    organization_deposit = work(authors=(DoiAuthor(name="Synthetic Consortium"),))
    page_person = Harvested(("Ana Ruiz",), BYLINE, "Ana Ruiz")

    by_deposit = resolve(CitationCandidates(organization_authors=(ORGANIZATION,)), person_deposit)
    by_page = resolve(CitationCandidates(authors=(page_person,)), organization_deposit)

    assert (by_deposit.authors.value, by_deposit.authors_are_organizations) == (("Rhea Okonkwo-Hale",), False)
    assert (by_page.authors.value, by_page.authors_are_organizations) == (("Ana Ruiz",), False)


def test_with_no_typed_organization_and_no_person_the_authors_stay_missing() -> None:
    citation = resolve(
        CitationCandidates(publication=(Harvested("Synthetic Policy Office", OPENGRAPH, "x"),)), None
    )

    assert citation.authors.source is MISSING
    assert not citation.authors_are_organizations


def test_the_short_cite_keeps_an_organization_name_whole() -> None:
    citation = resolve(
        CitationCandidates(
            organization_authors=(
                Harvested(
                    ("Federal Office of Synthetic Wildlife",), JSON_LD, "Federal Office of Synthetic Wildlife"
                ),
            ),
            published_at=(Harvested(utc(2026, 6, 2), JSON_LD, "2026-06-02"),),
        ),
        None,
    )

    assert (
        format_cite(citation, provenance_mode=PUBLISHER).short_cite
        == "Federal Office of Synthetic Wildlife 26"
    )
    person = citation.evolve(authors_are_organizations=False)
    assert format_cite(person, provenance_mode=PUBLISHER).short_cite == "Wildlife 26"


def test_a_cite_cannot_mark_missing_authors_as_organizations() -> None:
    with pytest.raises(ValueError, match="organization"):
        Citation(authors_are_organizations=True)

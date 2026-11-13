"""A cite can carry a year-only or year-and-month date without inventing a day (`v1-e06-t13`).

A date's precision travels beside it, from where it is stated to where it is printed:

* a user states a year, a month or a day with `fetch --paste --date` (:func:`stated_citation`);
* a discovery candidate's year or month reaches its Article (:func:`discovery_article`) and, through the
  Crossref deposit its DOI names, the cite (:func:`resolve_citation`), which takes a year or a month only
  when no source states a day, so no cite that had a day loses it;
* :func:`format_cite` prints the date at its precision, the short cite's two digits being the year at
  any precision, and the .docx of every committed format profile prints that line;
* the SQLite repositories store the precision beside the date, and read a row that has none (every row
  an older build wrote) as a day.

Every expected value is written by hand: the dates, the cite lines and the stored keys.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import docx
import pytest
from tests.fixtures.citation.citation_world import RETRIEVED_AT, CitationWorld

from debate_core.application.citation_service import (
    InvalidStatedCite,
    format_cite,
    keep_student_edits,
    resolve_citation,
    stated_citation,
)
from debate_core.application.export_service import ExportService
from debate_core.application.federated_dedupe import merge_candidates
from debate_core.application.federated_ranking import (
    FEDERATED_RANKING_CONFIG_PATH,
    load_federated_ranking_config,
    rank_merged_candidates,
)
from debate_core.application.federated_search_articles import ArticleMatchingStage
from debate_core.application.federated_search_types import SearchRequest, SearchState
from debate_core.application.ports.doi_metadata import DoiDate, DoiWork
from debate_core.domain import (
    AccessStatus,
    Article,
    ArticleIdentifiers,
    Card,
    Citation,
    CitationField,
    CitationFieldSource,
    ProvenanceMode,
    SearchFilters,
    SourceSnapshot,
    SourceType,
    VerificationStatus,
)
from debate_core.domain.discovery import CandidateResult
from debate_core.domain.enums import DatePrecision
from debate_core.evidence.docx_renderer import render_cards_docx
from debate_core.evidence.format_profile import FORMAT_PROFILES_DIRECTORY, load_format_profile
from debate_core.integrations.local import SqliteArticleRepository, SqliteCardRepository, SqliteDatabase
from debate_core.retrieval.citation_harvest import CitationCandidates, Harvested
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator

pytestmark = pytest.mark.anyio

REPOSITORY: Final = Path(__file__).resolve().parents[4]
PROFILES: Final = ("team-default", "flow", "plain")
YEAR: Final = DatePrecision.YEAR
MONTH: Final = DatePrecision.MONTH
DAY: Final = DatePrecision.DAY
CROSSREF: Final = CitationFieldSource.CROSSREF
META_TAG: Final = CitationFieldSource.META_TAG
HEURISTIC: Final = CitationFieldSource.HEURISTIC
PUBLISHER: Final = ProvenanceMode.PUBLISHER_RETRIEVED
USER_SUPPLIED: Final = ProvenanceMode.USER_SUPPLIED


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


# --------------------------------------------------------------------------------------------
# A stated date: a year, a month or a day, and nothing else
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("date_text", "moment", "precision"),
    [
        ("2026", utc(2026), YEAR),
        ("2026-10", utc(2026, 10), MONTH),
        ("2026-10-03", utc(2026, 10, 3), DAY),
        (" 2026-10 ", utc(2026, 10), MONTH),
    ],
    ids=["year", "month", "day", "stripped"],
)
def test_a_stated_date_is_recorded_at_the_start_of_the_period_it_names_with_that_precision(
    date_text: str, moment: datetime, precision: DatePrecision
) -> None:
    citation = stated_citation(published_on=date_text)

    assert citation is not None
    assert citation.published_at == CitationField[datetime](
        value=moment, source=HEURISTIC, raw=date_text.strip()
    )
    assert citation.published_at_precision is precision


@pytest.mark.parametrize(
    "date_text", ["2026-13", "2026-00", "0000", "2026-1", "202", "2026-10-", "10-2026", "2026/10", "Oct 2026"]
)
def test_a_year_or_a_month_that_is_no_date_is_refused_naming_the_three_forms(date_text: str) -> None:
    with pytest.raises(InvalidStatedCite) as refused:
        stated_citation(published_on=date_text)

    assert refused.value.field == "published_at"
    assert refused.value.detail == (
        f"{date_text!r} is not a date in the form YYYY, YYYY-MM or YYYY-MM-DD, "
        "such as 2026, 2026-09 or 2026-09-14"
    )


# --------------------------------------------------------------------------------------------
# format_cite: the date at its precision
# --------------------------------------------------------------------------------------------


def whole_cite(published: datetime, precision: DatePrecision, raw: str) -> Citation:
    return Citation(
        authors=CitationField[tuple[str, ...]](
            value=("Jane Smith",), source=META_TAG, verified=True, raw="Jane Smith"
        ),
        title=CitationField[str](value="Seed Banks", source=META_TAG, verified=True, raw="Seed Banks"),
        publication=CitationField[str](
            value="Policy Review", source=META_TAG, verified=True, raw="Policy Review"
        ),
        published_at=CitationField[datetime](value=published, source=CROSSREF, verified=True, raw=raw),
        published_at_precision=precision,
        canonical_url=CitationField[str](
            value="https://papers.example/seed-banks",
            source=META_TAG,
            verified=True,
            raw="https://papers.example/seed-banks",
        ),
        accessed_at=CitationField[datetime](
            value=RETRIEVED_AT,
            source=CitationFieldSource.RETRIEVAL,
            verified=True,
            raw=RETRIEVED_AT.isoformat(),
        ),
    )


@pytest.mark.parametrize(
    ("published", "precision", "raw", "short", "full"),
    [
        (
            utc(2021),
            YEAR,
            "2021",
            "Smith 21",
            'Smith 21 [Jane Smith; "Seed Banks"; Policy Review; 2021; https://papers.example/seed-banks; '
            "accessed October 26, 2026]",
        ),
        (
            utc(2021, 3),
            MONTH,
            "2021-03",
            "Smith 21",
            'Smith 21 [Jane Smith; "Seed Banks"; Policy Review; March 2021; '
            "https://papers.example/seed-banks; accessed October 26, 2026]",
        ),
        (
            utc(2021, 3, 4),
            DAY,
            "2021-03-04",
            "Smith 21",
            'Smith 21 [Jane Smith; "Seed Banks"; Policy Review; March 4, 2021; '
            "https://papers.example/seed-banks; accessed October 26, 2026]",
        ),
        (
            utc(2021),
            DAY,
            "2021-01-01",
            "Smith 21",
            'Smith 21 [Jane Smith; "Seed Banks"; Policy Review; January 1, 2021; '
            "https://papers.example/seed-banks; accessed October 26, 2026]",
        ),
    ],
    ids=["year", "month", "day", "the first of January, stated as a day"],
)
def test_the_cite_prints_the_date_at_its_precision_and_the_short_cite_the_year(
    published: datetime, precision: DatePrecision, raw: str, short: str, full: str
) -> None:
    formatted = format_cite(whole_cite(published, precision, raw), provenance_mode=PUBLISHER)

    assert (formatted.short_cite, formatted.full_cite) == (short, full)
    assert (formatted.unverified_fields, formatted.missing_fields) == ((), ("author_credentials",))


# --------------------------------------------------------------------------------------------
# resolve_citation: a deposit's year or month, only when no source states a day
# --------------------------------------------------------------------------------------------

DOI: Final = "10.5555/sprp.2021.0003"
NO_DATE: Final = CitationCandidates(
    title=(Harvested("Page title", META_TAG, "Page title"),),
    canonical_url=(Harvested("https://papers.example/a", META_TAG, "https://papers.example/a"),),
)
"""A page that states no date."""
SLUG_DAY: Final = CitationCandidates(published_at=(Harvested(utc(2021, 6, 9), HEURISTIC, "2021/06/09"),))
"""A page whose only date is its URL's, a heuristic day."""


def deposit(*dates: DoiDate) -> DoiWork:
    return DoiWork(doi=DOI, title="Seed Banks", dates=dates)


def resolved(candidates: CitationCandidates, work: DoiWork, mode: ProvenanceMode = PUBLISHER) -> Citation:
    return resolve_citation(candidates, work, provenance_mode=mode, accessed_at=RETRIEVED_AT)


@pytest.mark.parametrize(
    ("dates", "moment", "raw", "precision"),
    [
        ((DoiDate(kind="issued", year=2021),), utc(2021), "2021", YEAR),
        ((DoiDate(kind="issued", year=2021, month=3),), utc(2021, 3), "2021-03", MONTH),
        (
            (DoiDate(kind="published", year=2021), DoiDate(kind="published-print", year=2021, month=5)),
            utc(2021, 5),
            "2021-05",
            MONTH,
        ),
        (
            (DoiDate(kind="published", year=2020), DoiDate(kind="issued", year=2021)),
            utc(2020),
            "2020",
            YEAR,
        ),
    ],
    ids=["a year", "a month", "a month before an earlier-listed year", "the first of two years"],
)
def test_with_no_day_anywhere_the_deposits_finest_partial_date_is_the_cites_at_its_precision(
    dates: tuple[DoiDate, ...], moment: datetime, raw: str, precision: DatePrecision
) -> None:
    citation = resolved(NO_DATE, deposit(*dates))

    assert citation.published_at == CitationField[datetime](
        value=moment, source=CROSSREF, verified=True, raw=raw
    )
    assert citation.published_at_precision is precision


def test_a_day_from_any_source_wins_over_a_deposits_year_so_no_cite_loses_its_day() -> None:
    citation = resolved(SLUG_DAY, deposit(DoiDate(kind="issued", year=2021)))

    assert (citation.published_at.value, citation.published_at.source, citation.published_at_precision) == (
        utc(2021, 6, 9),
        HEURISTIC,
        DAY,
    )


def test_a_deposits_whole_date_wins_over_its_own_year_as_before() -> None:
    work = deposit(DoiDate(kind="published", year=2021), DoiDate(kind="issued", year=2021, month=2, day=8))

    citation = resolved(NO_DATE, work)

    assert (citation.published_at.value, citation.published_at.raw, citation.published_at_precision) == (
        utc(2021, 2, 8),
        "2021-02-08",
        DAY,
    )


def test_a_deposits_year_for_text_the_platform_did_not_retrieve_is_unverified() -> None:
    citation = resolved(NO_DATE, deposit(DoiDate(kind="issued", year=2021)), USER_SUPPLIED)

    assert (citation.published_at.value, citation.published_at.verified, citation.published_at_precision) == (
        utc(2021),
        False,
        YEAR,
    )


def test_with_no_date_anywhere_the_cite_has_none_and_a_day_precision() -> None:
    citation = resolved(NO_DATE, deposit())

    assert (citation.published_at.is_present, citation.published_at_precision) == (False, DAY)


# --------------------------------------------------------------------------------------------
# keep_student_edits: a date is the same only at the same precision
# --------------------------------------------------------------------------------------------


def dated(
    moment: datetime, precision: DatePrecision, source: CitationFieldSource, verified: bool
) -> Citation:
    raw = {YEAR: f"{moment.year}", MONTH: moment.strftime("%Y-%m"), DAY: moment.date().isoformat()}[precision]
    return Citation(
        published_at=CitationField[datetime](value=moment, source=source, verified=verified, raw=raw),
        published_at_precision=precision,
    )


def test_a_stated_year_is_kept_beside_a_derived_first_of_january_and_keeps_its_precision() -> None:
    stated = dated(utc(2021), YEAR, HEURISTIC, False)
    derived = dated(utc(2021), DAY, META_TAG, True)

    kept, names = keep_student_edits(stated, derived)

    assert names == ("published_at",)
    assert (kept.published_at, kept.published_at_precision) == (stated.published_at, YEAR)


def test_a_stated_day_equal_to_the_derived_day_takes_the_derived_field_as_before() -> None:
    stated = dated(utc(2021, 6, 9), DAY, HEURISTIC, False)
    derived = dated(utc(2021, 6, 9), DAY, META_TAG, True)

    kept, names = keep_student_edits(stated, derived)

    assert (names, kept.published_at, kept.published_at_precision) == ((), derived.published_at, DAY)


def test_a_derived_year_keeps_its_precision_when_another_field_is_kept() -> None:
    stated = Citation(title=CitationField[str](value="My title", source=HEURISTIC, raw="My title"))
    derived = dated(utc(2021), YEAR, CROSSREF, True)

    kept, names = keep_student_edits(stated, derived)

    assert names == ("title",)
    assert (kept.published_at, kept.published_at_precision) == (derived.published_at, YEAR)


def test_a_derived_year_never_lends_its_precision_to_a_kept_day() -> None:
    stated = dated(utc(2021, 6, 9), DAY, HEURISTIC, False)
    derived = dated(utc(2021), YEAR, CROSSREF, True)

    kept, names = keep_student_edits(stated, derived)

    assert names == ("published_at",)
    assert (kept.published_at, kept.published_at_precision) == (stated.published_at, DAY)


# --------------------------------------------------------------------------------------------
# A stated year on a pasted copy, through CitationService
# --------------------------------------------------------------------------------------------

USER_URL: Final = "https://www.harborreview.example/politics/2026/10/02/inside-the-tariff-talks"
"""A URL whose path names a day, the 2nd, which the rules derive as a heuristic. The case's Article is
titled "Inside the tariff talks", which the rules take as a heuristic title and the short cite's name."""


@pytest.fixture
def world() -> CitationWorld:
    return CitationWorld()


async def pasted_copy_stating(world: CitationWorld, date_text: str) -> Citation:
    article, _ = await world.add_case("user-supplied")
    snapshot = await world.snapshots.create(
        article_id=article.article_id,
        raw_bytes=b"Pasted text.",
        extracted_text="Pasted text.",
        canonical_url=USER_URL,
        retrieved_at=RETRIEVED_AT,
        extractor_version="user-supplied-text-1",
        provenance_mode=USER_SUPPLIED,
        access_status=AccessStatus.UNKNOWN,
        content_type="text/plain; charset=utf-8",
        stated_citation=stated_citation(published_on=date_text),
    )
    await world.articles.save_snapshot(snapshot)
    resolution = await world.service.resolve(article, await world.snapshots.load(snapshot))
    assert resolution.stated_fields == ("published_at",)
    return resolution.citation


@pytest.mark.parametrize(
    ("date_text", "moment", "precision", "printed"),
    [("2026", utc(2026), YEAR, "2026"), ("2026-10", utc(2026, 10), MONTH, "October 2026")],
    ids=["year", "month"],
)
async def test_a_pasted_copys_stated_year_or_month_replaces_the_urls_day_at_its_precision(
    world: CitationWorld, date_text: str, moment: datetime, precision: DatePrecision, printed: str
) -> None:
    citation = await pasted_copy_stating(world, date_text)

    assert citation.published_at == CitationField[datetime](value=moment, source=HEURISTIC, raw=date_text)
    assert citation.published_at_precision is precision
    assert format_cite(citation, provenance_mode=USER_SUPPLIED).full_cite == (
        f'Inside the tariff talks 26 ["Inside the tariff talks"; {printed}; {USER_URL}; '
        "accessed October 26, 2026; user-supplied text]"
    )


# --------------------------------------------------------------------------------------------
# A discovery candidate's year or month: the Article, the cite and the .docx
# --------------------------------------------------------------------------------------------

DISCOVERED_URL: Final = "https://papers.synthetic-policy.example/seed-banks-and-the-long-drought"
SEARCHED_AT: Final = datetime(2026, 10, 21, 12, tzinfo=UTC)
PAGE: Final = (
    b"<!doctype html><html><head><title>Seed Banks</title></head>"
    b"<body><h1>Seed Banks</h1><p>A synthetic paper with no date on its page.</p></body></html>"
)
"""A landing page that states no date, so the cite's date can only be the deposit's."""


def candidate(published: datetime, precision: DatePrecision) -> CandidateResult:
    """A Crossref candidate for an invented paper under the `10.5555` test prefix."""
    return CandidateResult(
        provider="crossref",
        provider_record_id=DOI,
        title="Seed Banks and the Long Drought",
        url=DISCOVERED_URL,
        canonical_url=DISCOVERED_URL,
        identifiers=ArticleIdentifiers(doi=DOI),
        source_type=SourceType.SCHOLARLY,
        authors=("Noor Haddad-Whitcombe",),
        publication="Synthetic Policy Review",
        published_at=published,
        date_precision=precision,
    )


def crossref_answer(date_parts: list[int]) -> bytes:
    """Crossref's `/works/{doi}` answer for the same invented paper, written by hand."""
    message = {
        "DOI": DOI,
        "type": "journal-article",
        "title": ["Seed Banks and the Long Drought"],
        "container-title": ["Synthetic Policy Review"],
        "author": [{"given": "Noor", "family": "Haddad-Whitcombe", "sequence": "first", "affiliation": []}],
        "issued": {"date-parts": [date_parts]},
    }
    return json.dumps({"status": "ok", "message-type": "work", "message": message}).encode()


async def discovered(world: CitationWorld, published: datetime, precision: DatePrecision) -> Article:
    """The Article a search registers for the candidate, in the citation world's repository."""
    request = SearchRequest(query="seed banks")
    ranked = rank_merged_candidates(
        merge_candidates((candidate(published, precision),)),
        queries=("seed banks",),
        filters=SearchFilters(),
        answered_providers=1,
        now=SEARCHED_AT,
        config=load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH),
    )
    state = SearchState.start("0SRCH000000000000000000001", request).evolve(ranked_candidates=ranked)
    stage = ArticleMatchingStage(
        world.articles, clock=FixedClock(SEARCHED_AT), ids=SequentialIdGenerator("ART")
    )
    [article] = (await stage.run(state)).articles
    return article


DISCOVERED_CASES: Final = [
    (utc(2021), YEAR, [2021], "2021"),
    (utc(2021, 3), MONTH, [2021, 3], "March 2021"),
]


@pytest.mark.parametrize(
    ("published", "precision", "date_parts", "printed"), DISCOVERED_CASES, ids=["year", "month"]
)
async def test_a_discovery_candidates_year_or_month_reaches_the_article_the_cite_and_every_profiles_docx(
    world: CitationWorld, published: datetime, precision: DatePrecision, date_parts: list[int], printed: str
) -> None:
    article = await discovered(world, published, precision)
    assert (article.published_at, article.date_precision) == (published, precision)

    world.crossref.answer(DOI, 200, crossref_answer(date_parts))
    source = await world.add_snapshot(article, PAGE, DISCOVERED_URL)
    citation = (await world.service.resolve(article, source)).citation
    assert citation.published_at == CitationField[datetime](
        value=published, source=CROSSREF, verified=True, raw="-".join(f"{part:02d}" for part in date_parts)
    )
    assert citation.published_at_precision is precision

    card = await world.stored_card(source, citation)
    assert card.verification_status is VerificationStatus.VERIFIED
    expected = (
        'Haddad-Whitcombe 21 [Noor Haddad-Whitcombe; "Seed Banks and the Long Drought"; '
        f"Synthetic Policy Review; {printed}; {DISCOVERED_URL}; accessed October 26, 2026]"
    )
    export = ExportService(articles=world.articles, clock=world.clock, render_docx=render_cards_docx)
    for name in PROFILES:
        profile = load_format_profile(name, REPOSITORY / FORMAT_PROFILES_DIRECTORY)
        data = await export.export_docx([card], profile=profile)
        paragraphs = [paragraph.text for paragraph in docx.Document(io.BytesIO(data)).paragraphs]
        assert paragraphs[1] == expected, name


# --------------------------------------------------------------------------------------------
# Stored and read back; a row an older build wrote reads as a day
# --------------------------------------------------------------------------------------------


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    with SqliteDatabase.open(tmp_path) as opened:
        yield opened


def stored_document(database: SqliteDatabase, table: str, key: str, value: str) -> dict[str, Any]:
    row = database.connection.execute(f"SELECT document FROM {table} WHERE {key} = ?", (value,)).fetchone()
    document: dict[str, Any] = json.loads(row[0])
    return document


ARTICLE_ID: Final = "0ART0000000000000000000001"
CARD_ID: Final = "0CARD000000000000000000001"


def article_dated(published: datetime | None, precision: DatePrecision) -> Article:
    return Article(
        article_id=ARTICLE_ID,
        canonical_url=DISCOVERED_URL,
        title="Seed Banks and the Long Drought",
        published_at=published,
        date_precision=precision,
        created_at=SEARCHED_AT,
        updated_at=SEARCHED_AT,
    )


@pytest.mark.parametrize(
    ("published", "precision", "stored_key"),
    [(utc(2021), YEAR, "year"), (utc(2021, 3), MONTH, "month"), (utc(2021, 3, 4), DAY, None)],
    ids=["year", "month", "day"],
)
async def test_an_articles_date_is_stored_and_read_back_at_its_precision(
    database: SqliteDatabase, published: datetime, precision: DatePrecision, stored_key: str | None
) -> None:
    articles = SqliteArticleRepository(database)
    await articles.save(article_dated(published, precision))

    document = stored_document(database, "articles", "article_id", ARTICLE_ID)
    assert document.get("date_precision") == stored_key
    assert ("date_precision" in document) is (stored_key is not None)
    read = await articles.get(ARTICLE_ID)
    assert (read.published_at, read.date_precision) == (published, precision)


@pytest.mark.parametrize(
    ("date_text", "stored_key"),
    [("2021", "year"), ("2021-03", "month"), ("2021-03-04", None)],
    ids=["year", "month", "day"],
)
async def test_a_cards_date_and_a_snapshots_stated_date_are_stored_and_read_back_at_their_precision(
    database: SqliteDatabase, date_text: str, stored_key: str | None
) -> None:
    stated = stated_citation(published_on=date_text)
    assert stated is not None
    articles, cards = SqliteArticleRepository(database), SqliteCardRepository(database)
    await articles.save(article_dated(None, DAY))
    snapshot = SourceSnapshot(
        snapshot_id="0SNAP000000000000000000001",
        article_id=ARTICLE_ID,
        canonical_url=DISCOVERED_URL,
        retrieved_at=RETRIEVED_AT,
        access_status=AccessStatus.UNKNOWN,
        provenance_mode=USER_SUPPLIED,
        raw_blob_key="raw/a",
        normalized_blob_key="normalized/a",
        sha256="a" * 64,
        normalized_text_hash="b" * 64,
        extractor_version="user-supplied-text-1",
        normalizer_version="1",
        stated_citation=stated,
        created_at=RETRIEVED_AT,
        updated_at=RETRIEVED_AT,
    )
    await articles.save_snapshot(snapshot)
    card = Card(
        card_id=CARD_ID,
        owner_id="0ACT0R00000000000000000001",
        article_id=ARTICLE_ID,
        tag="Seed banks fail in a long drought",
        provenance_mode=USER_SUPPLIED,
        citation=stated,
        created_at=RETRIEVED_AT,
        updated_at=RETRIEVED_AT,
    )
    await cards.create(card)

    snapshot_row = stored_document(database, "source_snapshots", "snapshot_id", snapshot.snapshot_id)
    card_row = stored_document(database, "cards", "card_id", CARD_ID)
    for cite in (snapshot_row["stated_citation"], card_row["citation"]):
        assert cite.get("published_at_precision") == stored_key
        assert ("published_at_precision" in cite) is (stored_key is not None)
    assert (await articles.get_snapshot(snapshot.snapshot_id)).stated_citation == stated
    assert (await cards.get(CARD_ID)).citation == stated


def test_a_row_written_before_the_precision_existed_reads_as_a_day() -> None:
    """The documents an older build wrote, with no precision key, written out by hand."""
    article = Article.model_validate_json(
        '{"article_id":"0ART0000000000000000000001","canonical_url":"https://papers.example/a",'
        '"title":"A paper","published_at":"2021-01-01T00:00:00Z",'
        '"created_at":"2026-10-21T12:00:00Z","updated_at":"2026-10-21T12:00:00Z"}'
    )
    citation = Citation.model_validate_json(
        '{"published_at":{"value":"2021-01-01T00:00:00Z","source":"meta_tag","verified":true,"raw":"2021-01-01"}}'
    )

    assert (article.published_at, article.date_precision) == (utc(2021), DAY)
    assert (citation.published_at.value, citation.published_at_precision) == (utc(2021), DAY)
    assert format_cite(citation, provenance_mode=PUBLISHER).full_cite == "[no author] 21 [January 1, 2021]"

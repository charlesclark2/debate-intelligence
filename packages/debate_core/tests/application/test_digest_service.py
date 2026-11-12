"""DigestService: a preset's searches for a window, the seen-set, and the grouping (v1-e08-t07).

The search is `search`'s own: :class:`FederatedSearchService` with the expansion stage over the
committed taxonomy, the real dedupe and rank stages and Article matching, over in-memory stores. The
one provider is :class:`TermProvider`, which answers a query with the records whose phrase the query
contains. It ignores the date window on purpose, as a provider that cannot filter by date would, so
the seen-set is what keeps yesterday's results out of today's digest; another test reads the window
every query was sent with.

The preset is written here, not read from `config/daily_presets.yaml`, so the coach's edits there do
not move these expectations. Expected groups, titles and the seen-set file are written by hand from
the records below (working agreement 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo

import pytest

from debate_core.application.batch_cut_service import BatchNeed
from debate_core.application.digest_seen_set import DigestSeenSet, DigestSeenSetError, FileDigestSeenStore
from debate_core.application.digest_service import (
    Digest,
    DigestRequest,
    DigestService,
    DigestWindow,
    digest_batch_candidates,
)
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.federated_dedupe import DedupeStage
from debate_core.application.federated_ranking import (
    FEDERATED_RANKING_CONFIG_PATH,
    FederatedRankStage,
    load_federated_ranking_config,
)
from debate_core.application.federated_search import FederatedSearchService
from debate_core.application.federated_search_articles import ArticleMatchingStage
from debate_core.application.federated_search_types import StagesInOrder
from debate_core.application.ports.providers import SearchProvider
from debate_core.application.query_expansion import (
    ARGUMENT_TAXONOMY_PATH,
    QueryExpansionStage,
    load_argument_taxonomy,
)
from debate_core.domain import AccessStatus, ArticleIdentifiers, SearchStatus, SourceType
from debate_core.domain.daily_preset import DailyPair, DailyPreset
from debate_core.domain.discovery import CandidateResult, ProviderHealth, ProviderQuery, ProviderResponse
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemoryArticleRepository, InMemorySearchRepository

pytestmark = pytest.mark.anyio

REPOSITORY: Final = Path(__file__).resolve().parents[4]
TAXONOMY: Final = load_argument_taxonomy(REPOSITORY / ARGUMENT_TAXONOMY_PATH)
RANKING: Final = load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH)
SEPTEMBER_17: Final = date(2026, 9, 17)
SEPTEMBER_18: Final = date(2026, 9, 18)
NOW: Final = datetime(2026, 9, 18, 23, 0, tzinfo=UTC)
ONE_DAY: Final = DigestWindow()

PRESET: Final = DailyPreset(
    name="politics",
    label="Politics",
    description="The test's politics preset: one query, two uniqueness pairs.",
    queries=("bill",),
    pairs=(
        DailyPair(argument="politics-da", need="uniqueness"),
        DailyPair(argument="midterms-da", need="uniqueness"),
    ),
    providers=("rss",),
    feed_topics=("politics",),
)
"""Politics DA uniqueness expands `bill` into `bill vote count Senate`, `bill likely to pass Congress`
and `bill will not pass` (its `{bill} whip count` needs a bill); midterms DA uniqueness into
`bill midterms polling` and `bill election forecast` (taxonomy 1.5.0)."""


def news(slug: str, title: str, day: int) -> CandidateResult:
    return CandidateResult(
        provider="rss",
        title=title,
        url=f"https://news.example.org/2026/09/{day}/{slug}",
        source_type=SourceType.NEWS,
        publication="The Example Courier",
        published_at=datetime(2026, 9, day, 12, tzinfo=UTC),
    )


VOTE: Final = news("senate-vote-count", "Senate vote count on the invented spending bill", 17)
PASS: Final = news("farm-bill", "Invented farm bill likely to pass Congress", 17)
FORECAST: Final = news("forecast", "Election forecast moves toward the House majority", 17)
PAPER: Final = CandidateResult(
    provider="rss",
    title="Midterms polling and the invented bill",
    url="https://doi.org/10.5555/invented.polling.2026",
    identifiers=ArticleIdentifiers(doi="10.5555/invented.polling.2026"),
    source_type=SourceType.SCHOLARLY,
    publication="Invented Polling Quarterly",
    published_at=datetime(2026, 9, 17, tzinfo=UTC),
)
PAPER_AT_PUBLISHER: Final = PAPER.model_copy(
    update={"url": "https://quarterly.example.edu/articles/midterms-polling-2026"}
)
"""The same paper the next day, at its publisher's URL: only its DOI says it is the same."""
NEW_VOTE: Final = news("senate-vote-count-again", "Second Senate vote count on the spending bill", 18)
BOTH_GROUPS: Final = news("pass-forecast", "Bill likely to pass and the election forecast", 17)
"""Matches a politics DA template and a midterms DA template: found by both groups' searches."""

DAY_ONE: Final = {
    "vote count": [VOTE],
    "likely to pass": [PASS],
    "election forecast": [FORECAST],
    "midterms polling": [PAPER],
}


@dataclass
class TermProvider:
    """Answers each query with the records filed under a phrase it contains; ignores the window."""

    records: dict[str, list[CandidateResult]]
    failure: Exception | None = None
    asked: list[ProviderQuery] = field(default_factory=list[ProviderQuery])

    @property
    def name(self) -> str:
        return "rss"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        self.asked.append(query)
        if self.failure is not None:
            raise self.failure
        found = [
            record
            for phrase, records in self.records.items()
            if phrase in query.query.lower()
            for record in records
        ]
        return ProviderResponse(provider="rss", results=tuple(found), elapsed_ms=1.0)


class ProvidersOnHand:
    def __init__(self, *providers: SearchProvider, not_configured: dict[str, str] | None = None) -> None:
        self._providers = providers
        self._not_configured = not_configured or {}

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    @property
    def not_configured(self) -> dict[str, str]:
        return self._not_configured

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


@dataclass
class World:
    provider: TermProvider
    seen_dir: Path
    feed_reviews: dict[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])
    written: list[Digest] = field(default_factory=list[Digest])

    def service(
        self, *providers: SearchProvider, not_configured: dict[str, str] | None = None
    ) -> DigestService:
        clock = FixedClock(NOW)
        ids = SequentialIdGenerator("SRCH")
        search = FederatedSearchService(
            ProvidersOnHand(*(providers or (self.provider,)), not_configured=not_configured),
            InMemorySearchRepository(),
            clock=clock,
            ids=ids,
            expand=QueryExpansionStage(TAXONOMY, clock=clock),
            normalize=DedupeStage(),
            rank=StagesInOrder(
                FederatedRankStage(RANKING, clock=clock),
                ArticleMatchingStage(
                    InMemoryArticleRepository(), clock=clock, ids=SequentialIdGenerator("ART")
                ),
            ),
        )
        return DigestService(
            searching=search,
            seen=FileDigestSeenStore(self.seen_dir),
            taxonomy=TAXONOMY,
            feed_reviews=self.feed_reviews,
        )

    def write(self, digest: Digest) -> Path:
        self.written.append(digest)
        path = self.seen_dir.parent / f"{digest.preset.name}-{digest.day.isoformat()}.md"
        path.write_text("\n".join(item.ranked.candidate.title for item in digest.items), encoding="utf-8")
        return path

    async def run(self, day: date, window: DigestWindow = ONE_DAY) -> Digest:
        return await self.service().run(DigestRequest(PRESET, day, window), self.write)

    def seen_file(self) -> dict[str, Any]:
        document: dict[str, Any] = json.loads((self.seen_dir / "politics.json").read_text(encoding="utf-8"))
        return document


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(
        TermProvider({phrase: list(records) for phrase, records in DAY_ONE.items()}), tmp_path / "seen"
    )


def groups(digest: Digest) -> list[tuple[str, set[str]]]:
    """Each group's heading and its results' titles. Their order inside a group is the ranking's
    (v1-e08-t03), which :func:`test_a_groups_results_keep_their_searchs_rank_order` checks."""
    return [(group.heading, {item.ranked.candidate.title for item in group.items}) for group in digest.groups]


# ------------------------------------------------------------------------------------------------
# The searches and the grouping
# ------------------------------------------------------------------------------------------------


async def test_the_digest_groups_new_results_by_argument_and_need_in_preset_order(world: World) -> None:
    digest = await world.run(SEPTEMBER_17)

    assert groups(digest) == [
        (
            "Politics DA — Uniqueness",
            {"Senate vote count on the invented spending bill", "Invented farm bill likely to pass Congress"},
        ),
        (
            "Midterms DA — Uniqueness",
            {"Midterms polling and the invented bill", "Election forecast moves toward the House majority"},
        ),
    ]
    assert digest.status is SearchStatus.COMPLETE
    assert digest.listed_before == 0
    assert digest.heading == "Politics daily digest: 2026-09-17"
    assert [item.need.argument for item in digest.items] == [
        "Politics DA",
        "Politics DA",
        "Midterms DA",
        "Midterms DA",
    ]
    assert (
        digest.items[0].need.need == "Uniqueness for bill: Where things stand now, before the plan or action."
    )
    assert digest.file == world.seen_dir.parent / "politics-2026-09-17.md"


async def test_every_query_is_the_pairs_expansion_asked_inside_the_window(world: World) -> None:
    await world.run(SEPTEMBER_17)

    assert [query.query for query in world.provider.asked] == [
        "bill vote count Senate",
        "bill likely to pass Congress",
        "bill will not pass",
        "bill midterms polling",
        "bill election forecast",
    ]
    window = {(query.filters.since, query.filters.until) for query in world.provider.asked}
    assert window == {
        (datetime(2026, 9, 17, tzinfo=UTC), datetime(2026, 9, 17, 23, 59, 59, 999999, tzinfo=UTC))
    }


async def test_a_wider_window_starts_that_many_days_back(world: World) -> None:
    await world.run(SEPTEMBER_17, DigestWindow.parse("3d"))

    assert {query.filters.since for query in world.provider.asked} == {datetime(2026, 9, 15, tzinfo=UTC)}


async def test_a_source_two_groups_find_is_listed_once_in_the_first(world: World) -> None:
    world.provider.records = {"likely to pass": [BOTH_GROUPS], "election forecast": [BOTH_GROUPS, FORECAST]}

    digest = await world.run(SEPTEMBER_17)

    assert groups(digest) == [
        ("Politics DA — Uniqueness", {"Bill likely to pass and the election forecast"}),
        ("Midterms DA — Uniqueness", {"Election forecast moves toward the House majority"}),
    ]


async def test_a_groups_results_keep_their_searchs_rank_order(world: World) -> None:
    digest = await world.run(SEPTEMBER_17)

    for group, outcome in zip(digest.groups, digest.outcomes, strict=True):
        ranked = [ranked.candidate.title for ranked in outcome.ranked_candidates]
        assert [item.ranked.candidate.title for item in group.items] == ranked
        assert [item.ranked.rank for item in group.items] == list(range(1, len(ranked) + 1))


# ------------------------------------------------------------------------------------------------
# The seen-set
# ------------------------------------------------------------------------------------------------


async def test_the_next_date_omits_what_the_previous_day_listed(world: World) -> None:
    await world.run(SEPTEMBER_17)
    world.provider.records["vote count"].append(NEW_VOTE)

    digest = await world.run(SEPTEMBER_18)

    assert groups(digest) == [
        ("Politics DA — Uniqueness", {"Second Senate vote count on the spending bill"}),
        ("Midterms DA — Uniqueness", set()),
    ]
    assert digest.listed_before == 4


async def test_a_result_seen_under_its_doi_is_omitted_at_another_url(world: World) -> None:
    await world.run(SEPTEMBER_17)
    world.provider.records = {"midterms polling": [PAPER_AT_PUBLISHER]}

    digest = await world.run(SEPTEMBER_18)

    assert digest.items == ()
    assert digest.listed_before == 1


async def test_a_source_merged_from_two_urls_is_seen_at_either(world: World) -> None:
    """Two records of one work at two URLs, merged by their OpenAlex id, with no DOI: the digest lists
    the merged source under the first URL, and the next day the second URL alone is the same source."""
    first = news("report", "Midterms polling report on the invented bill", 17).model_copy(
        update={"identifiers": ArticleIdentifiers(openalex_id="W4410000099")}
    )
    mirror = first.model_copy(update={"url": "https://mirror.example.com/reports/midterms-polling"})
    world.provider.records = {"midterms polling": [first, mirror]}
    [listed] = (await world.run(SEPTEMBER_17)).items
    assert listed.ranked.candidate.canonical_url == "https://news.example.org/2026/09/17/report"
    world.provider.records = {"midterms polling": [mirror]}

    digest = await world.run(SEPTEMBER_18)

    assert (digest.items, digest.listed_before) == ((), 1)


async def test_running_the_same_date_again_gives_the_same_digest(world: World) -> None:
    first = await world.run(SEPTEMBER_17)
    again = await world.run(SEPTEMBER_17)

    assert groups(again) == groups(first)
    assert again.listed_before == 0


async def test_the_seen_set_records_each_canonical_url_and_doi_under_the_date_that_listed_it(
    world: World,
) -> None:
    await world.run(SEPTEMBER_17)
    world.provider.records["vote count"].append(NEW_VOTE)
    await world.run(SEPTEMBER_18)

    assert world.seen_file() == {
        "schema_version": 1,
        "preset": "politics",
        "urls": {
            "https://doi.org/10.5555/invented.polling.2026": "2026-09-17",
            "https://news.example.org/2026/09/17/farm-bill": "2026-09-17",
            "https://news.example.org/2026/09/17/forecast": "2026-09-17",
            "https://news.example.org/2026/09/17/senate-vote-count": "2026-09-17",
            "https://news.example.org/2026/09/18/senate-vote-count-again": "2026-09-18",
        },
        "dois": {"10.5555/invented.polling.2026": "2026-09-17"},
    }
    assert sorted(path.name for path in world.seen_dir.iterdir()) == ["politics.json"]


async def test_a_run_whose_writer_fails_marks_nothing_seen(world: World) -> None:
    def failing(digest: Digest) -> Path:
        raise OSError("the disk is full")

    with pytest.raises(OSError, match="the disk is full"):
        await world.service().run(DigestRequest(PRESET, SEPTEMBER_17), failing)

    assert not (world.seen_dir / "politics.json").exists()
    assert len((await world.run(SEPTEMBER_18)).items) == 4


async def test_a_digest_no_provider_answered_is_not_written_and_marks_nothing(world: World) -> None:
    world.provider.failure = ProviderUnavailable("rss: every feed failed")

    digest = await world.run(SEPTEMBER_17)

    assert digest.status is SearchStatus.FAILED
    assert (digest.file, world.written) == (None, [])
    assert not (world.seen_dir / "politics.json").exists()


class FailingOpenAlex:
    """A second provider that never answers."""

    @property
    def name(self) -> str:
        return "openalex"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        raise ProviderUnavailable("openalex: HTTP 503")


async def test_a_partial_digest_is_written_and_its_results_count_as_listed(world: World) -> None:
    preset = PRESET.evolve(providers=("rss", "openalex"))

    service = world.service(world.provider, FailingOpenAlex())
    digest = await service.run(DigestRequest(preset, SEPTEMBER_17), world.write)

    assert digest.status is SearchStatus.PARTIAL
    assert len(digest.items) == 4
    assert digest.file is not None
    assert len(world.seen_file()["urls"]) == 4


CROSSREF_WITHOUT_ITS_EMAIL: Final = "crossref: no contact email (invented for this test)"
"""A preset provider settings enable but cannot build. Crossref really searches its public pool without
an email; the stand-in is unbuilt so the digest's rule is tested apart from GovInfo's topic gate."""


async def test_a_preset_provider_without_its_credential_not_configured_is_named_and_not_counted(
    world: World,
) -> None:
    """The coach's preset is configuration (the PM's ruling 3 on v1-e07-t15): counted like the
    providers the profile enables, so an unbuilt one leaves the digest COMPLETE and is named with its cure."""
    preset = PRESET.evolve(providers=("rss", "crossref"))

    service = world.service(world.provider, not_configured={"crossref": CROSSREF_WITHOUT_ITS_EMAIL})
    digest = await service.run(DigestRequest(preset, SEPTEMBER_17), world.write)

    assert digest.status is SearchStatus.COMPLETE
    assert digest.uncounted == ("crossref",)
    crossref = {status.error for status in digest.provider_statuses if status.provider == "crossref"}
    assert crossref == {f"{CROSSREF_WITHOUT_ITS_EMAIL}; set a contact email for Crossref's polite pool"}
    assert len(digest.items) == 4
    assert digest.file is not None


async def test_a_preset_provider_not_configured_beside_one_that_failed_leaves_the_digest_partial(
    world: World,
) -> None:
    preset = PRESET.evolve(providers=("rss", "openalex", "crossref"))

    service = world.service(
        world.provider, FailingOpenAlex(), not_configured={"crossref": CROSSREF_WITHOUT_ITS_EMAIL}
    )
    digest = await service.run(DigestRequest(preset, SEPTEMBER_17), world.write)

    assert digest.status is SearchStatus.PARTIAL
    assert digest.uncounted == ("crossref",)


async def test_a_preset_provider_the_profile_does_not_enable_is_uncounted_and_named_with_its_cure(
    world: World,
) -> None:
    """v1-e07-t23 (the PM's ruling on v1-e07-t15's follow-up 1): a preset provider settings do not enable
    is configuration too. It is named on every search with `enable it in providers.enabled`, and the
    digest is COMPLETE and written."""
    preset = PRESET.evolve(providers=("rss", "google_news"))

    digest = await world.service(world.provider).run(DigestRequest(preset, SEPTEMBER_17), world.write)

    assert digest.status is SearchStatus.COMPLETE
    assert digest.uncounted == ("google_news",)
    reasons = {status.error for status in digest.provider_statuses if status.provider == "google_news"}
    assert reasons == {
        "google_news: not enabled in settings (providers.enabled); enable it in providers.enabled"
    }
    assert len(digest.items) == 4
    assert digest.file is not None


async def test_an_unreadable_seen_set_is_an_error_not_an_empty_set(world: World) -> None:
    world.seen_dir.mkdir(parents=True)
    (world.seen_dir / "politics.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(DigestSeenSetError, match="politics.json: is not a seen-set"):
        await world.run(SEPTEMBER_17)


def test_recording_no_sources_changes_nothing() -> None:
    seen = DigestSeenSet(preset="politics", urls={"https://news.example.org/a": SEPTEMBER_17})

    assert seen.with_listed([], SEPTEMBER_18) == seen


# ------------------------------------------------------------------------------------------------
# Feed topics awaiting review, the window, and the auto-cut candidates
# ------------------------------------------------------------------------------------------------


async def test_a_feed_topic_awaiting_review_runs_and_the_digest_says_so(world: World) -> None:
    world.feed_reviews = {"politics": ("The Example Courier",), "health-insurance": ("STAT",)}

    digest = await world.run(SEPTEMBER_17)

    assert len(digest.items) == 4
    assert [(topic.topic, topic.awaiting_coach_review) for topic in digest.awaiting_review] == [
        ("politics", ("The Example Courier",))
    ]


@pytest.mark.parametrize(("text", "days"), [("1d", 1), ("7d", 7), ("31d", 31), (" 2d ", 2)])
def test_a_window_is_a_number_of_days(text: str, days: int) -> None:
    assert DigestWindow.parse(text).days == days


@pytest.mark.parametrize("text", ["0d", "32d", "1", "1w", "d", "-1d", "01d"])
def test_anything_else_is_not_a_window(text: str) -> None:
    with pytest.raises(ValueError, match="is not a window|a window is 1 to 31 days"):
        DigestWindow.parse(text)


async def test_auto_cut_candidates_take_each_groups_first_then_each_ones_second(world: World) -> None:
    digest = await world.run(SEPTEMBER_17)

    candidates = digest_batch_candidates(digest)

    politics, midterms = (group.items for group in digest.groups)
    order = [politics[0], midterms[0], politics[1], midterms[1]]
    assert [(c.rank, c.title, c.url) for c in candidates] == [
        (number, item.ranked.candidate.title, item.ranked.candidate.url)
        for number, item in enumerate(order, start=1)
    ]
    politics_need = BatchNeed(
        argument="Politics DA",
        need="Uniqueness for bill: Where things stand now, before the plan or action.",
        heading="Politics DA — Uniqueness: bill",
    )
    assert [c.need for c in candidates] == [politics_need, midterms[0].need, politics_need, midterms[1].need]
    assert midterms[0].need.argument == "Midterms DA"
    assert {c.known_access for c in candidates} == {AccessStatus.UNKNOWN}


async def test_an_empty_digest_has_no_auto_cut_candidates(world: World) -> None:
    world.provider.records = {}

    assert digest_batch_candidates(await world.run(SEPTEMBER_17)) == ()


# ------------------------------------------------------------------------------------------------
# A digest run with no --date (v1-e08-t25, the PM's ruling of 2026-11-12)
#
# With no --date a digest covers the 24 hours before the run, by the injected clock, and is dated by
# the run's local date in the configured IANA zone; --date keeps whole UTC days and --window widens
# either. The case behind it is 2026-11-11: a politics digest run at 23:00 in Chicago took the UTC
# date, 2026-11-12, and searched only the five hours since UTC midnight. Every expected instant is
# written by hand from the zone's offset on that date: Chicago is UTC-6 in November (CST) and UTC-5
# from the second Sunday of March to the first Sunday of November (CDT); Los Angeles is UTC-8 in
# November and Tokyo UTC+9 all year.
# ------------------------------------------------------------------------------------------------

CHICAGO: Final = ZoneInfo("America/Chicago")


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_a_run_at_23_00_in_chicago_is_that_evenings_date_and_its_24_hours() -> None:
    request = DigestRequest.before_the_run(PRESET, now=utc(2026, 11, 12, 5), zone=CHICAGO)

    assert request.day == date(2026, 11, 11)
    assert request.bounds() == (utc(2026, 11, 11, 5), utc(2026, 11, 12, 5))


def test_a_run_at_07_00_in_chicago_reaches_back_into_the_evening_before() -> None:
    request = DigestRequest.before_the_run(PRESET, now=utc(2026, 11, 12, 13), zone=CHICAGO)

    assert request.day == date(2026, 11, 12)
    assert request.bounds() == (utc(2026, 11, 11, 13), utc(2026, 11, 12, 13))


def test_on_the_day_the_clocks_fall_back_it_is_still_24_hours_and_that_days_date() -> None:
    """1 November 2026: 02:00 CDT becomes 01:00 CST. A run at 23:00 CST reaches back to 00:00 CDT, 23
    hours of the wall clock and 24 of time."""
    request = DigestRequest.before_the_run(PRESET, now=utc(2026, 11, 2, 5), zone=CHICAGO)

    assert request.day == date(2026, 11, 1)
    since, until = request.bounds()
    assert (since, until) == (utc(2026, 11, 1, 5), utc(2026, 11, 2, 5))
    assert since.astimezone(CHICAGO).replace(tzinfo=None) == datetime(2026, 11, 1, 0, 0)


def test_on_the_day_the_clocks_spring_forward_it_is_still_24_hours_and_that_days_date() -> None:
    """8 March 2026: 02:00 CST becomes 03:00 CDT. A run at 23:00 CDT reaches back to 22:00 CST the
    evening before."""
    request = DigestRequest.before_the_run(PRESET, now=utc(2026, 3, 9, 4), zone=CHICAGO)

    assert request.day == date(2026, 3, 8)
    since, until = request.bounds()
    assert (since, until) == (utc(2026, 3, 8, 4), utc(2026, 3, 9, 4))
    assert since.astimezone(CHICAGO).replace(tzinfo=None) == datetime(2026, 3, 7, 22, 0)


@pytest.mark.parametrize(
    ("zone", "now", "day"),
    [
        ("America/Los_Angeles", utc(2026, 11, 12, 6), date(2026, 11, 11)),
        ("Asia/Tokyo", utc(2026, 11, 12, 20), date(2026, 11, 13)),
    ],
    ids=["los angeles, where it is still the 11th", "tokyo, where it is already the 13th"],
)
def test_another_zone_dates_the_run_by_its_own_clock(zone: str, now: datetime, day: date) -> None:
    """At 06:00Z on the 12th Chicago's date is the 12th and Los Angeles's the 11th; at 20:00Z UTC's and
    Chicago's are the 12th and Tokyo's the 13th. The window is the same 24 hours in every zone."""
    request = DigestRequest.before_the_run(PRESET, now=now, zone=ZoneInfo(zone))

    assert request.day == day
    assert request.bounds() == (now - timedelta(hours=24), now)


def test_a_wider_window_with_no_date_is_that_many_days_of_24_hours_before_the_run() -> None:
    request = DigestRequest.before_the_run(
        PRESET, now=utc(2026, 11, 12, 5), zone=CHICAGO, window=DigestWindow(3)
    )

    assert request.day == date(2026, 11, 11)
    assert request.bounds() == (utc(2026, 11, 9, 5), utc(2026, 11, 12, 5))


def test_a_date_keeps_whole_utc_days_ending_with_it() -> None:
    request = DigestRequest(PRESET, date(2026, 11, 11), DigestWindow(3))

    assert request.bounds() == (utc(2026, 11, 9, 0), datetime(2026, 11, 11, 23, 59, 59, 999999, tzinfo=UTC))
    assert (request.run_at, request.zone) == (None, None)


def test_a_run_time_with_no_zone_of_its_own_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        DigestRequest.before_the_run(PRESET, now=datetime(2026, 11, 11, 23), zone=CHICAGO)


# ------------------------------------------------------------------------------------------------
# The searches and the seen-set follow the local date
# ------------------------------------------------------------------------------------------------


async def test_every_query_is_asked_for_the_24_hours_and_the_digest_is_dated_in_the_zone(
    world: World,
) -> None:
    request = DigestRequest.before_the_run(PRESET, now=utc(2026, 9, 18, 4), zone=CHICAGO)

    digest = await world.service().run(request, world.write)

    assert {(query.filters.since, query.filters.until) for query in world.provider.asked} == {
        (utc(2026, 9, 17, 4), utc(2026, 9, 18, 4))
    }
    assert (digest.day, digest.since, digest.until, digest.zone) == (
        date(2026, 9, 17),
        utc(2026, 9, 17, 4),
        utc(2026, 9, 18, 4),
        CHICAGO,
    )
    assert digest.file == world.seen_dir.parent / "politics-2026-09-17.md"
    assert set(world.seen_file()["urls"].values()) == {"2026-09-17"}


async def test_the_next_evenings_run_leaves_out_what_this_evenings_listed(world: World) -> None:
    first = await world.service().run(
        DigestRequest.before_the_run(PRESET, now=utc(2026, 9, 18, 4), zone=CHICAGO), world.write
    )

    second = await world.service().run(
        DigestRequest.before_the_run(PRESET, now=utc(2026, 9, 19, 4), zone=CHICAGO), world.write
    )

    assert len(first.items) == 4
    assert (second.day, second.items, second.listed_before) == (date(2026, 9, 18), (), 4)


async def test_a_morning_and_an_evening_run_of_one_local_date_are_the_same_digest_twice(world: World) -> None:
    """Two runs on 18 September, at 07:00 and 23:00 Chicago: the second rewrites the 18th's digest and
    lists again what the first did, as a second run of a `--date` does (v1-e08-t07's ruling 1)."""
    morning = await world.service().run(
        DigestRequest.before_the_run(PRESET, now=utc(2026, 9, 18, 12), zone=CHICAGO), world.write
    )

    evening = await world.service().run(
        DigestRequest.before_the_run(PRESET, now=utc(2026, 9, 19, 4), zone=CHICAGO), world.write
    )

    assert morning.day == evening.day == date(2026, 9, 18)
    assert evening.listed_before == 0
    assert {item.ranked.candidate.title for item in evening.items} >= {VOTE.title}


async def test_a_source_an_evening_run_recorded_under_the_utc_date_is_listed_once_more_on_that_local_date(
    world: World,
) -> None:
    """The changeover: a build before this one dated a 23:00 Chicago run on 17 September by the UTC
    date, the 18th, and recorded what it listed under the 18th. The next evening's run is dated the
    18th by this build, so those sources are the same date's own and are listed again, once; the run
    after that leaves them out."""
    await world.run(date(2026, 9, 18))

    changeover = await world.service().run(
        DigestRequest.before_the_run(PRESET, now=utc(2026, 9, 19, 4), zone=CHICAGO), world.write
    )
    after = await world.service().run(
        DigestRequest.before_the_run(PRESET, now=utc(2026, 9, 20, 4), zone=CHICAGO), world.write
    )

    assert (changeover.day, len(changeover.items), changeover.listed_before) == (date(2026, 9, 18), 4, 0)
    assert (after.day, len(after.items), after.listed_before) == (date(2026, 9, 19), 0, 4)

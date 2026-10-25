"""The backfile survey (`v1-e34-t34` ac1): what the API serves for earlier seasons, counted read-only.

Against a fake source that records every question. Every slug and date is synthetic.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from debate_core.application.caselist.backfile_survey import (
    BackfileSurvey,
    is_high_school,
    season_label,
    season_start_year,
)
from debate_core.application.errors import ProviderRateLimited
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    ArchiveUnavailable,
    CaselistAuthExpired,
    CaselistInfo,
)
from debate_core.application.settings import ConfigurationError

FILES = "https://caselist-files.example.invalid/weekly"


def info(slug: str, *, level: str | None = "hs", archived: bool = True, event: str = "ld") -> CaselistInfo:
    return CaselistInfo(slug=slug, level=level, archived=archived, event=event, year=season_start_year(slug))


def weekly(slug: str, day: date) -> ArchiveListing:
    name = f"{slug}-weekly-{day.isoformat()}.zip"
    return ArchiveListing(
        caselist=slug, name=name, kind=ArchiveKind.WEEKLY, archive_date=day, url=f"{FILES}/{name}"
    )


def complete(slug: str, day: date) -> ArchiveListing:
    name = f"{slug}-all-{day.isoformat()}.zip"
    return ArchiveListing(
        caselist=slug, name=name, kind=ArchiveKind.FULL, archive_date=day, url=f"{FILES}/{name}"
    )


class FakeSource:
    """Answers the survey's three questions from tables, and records each one asked."""

    def __init__(
        self,
        *,
        current: list[CaselistInfo],
        archived: list[CaselistInfo],
        archives: dict[str, list[ArchiveListing]],
        sizes: dict[str, int | None | BaseException],
    ) -> None:
        self.current = current
        self.archived = archived
        self.archives = archives
        self.sizes = sizes
        self.asked: list[str] = []
        self.closed = False

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        self.asked.append(f"caselists archived={archived}")
        return self.archived if archived else self.current

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        self.asked.append(f"archives {caselist}")
        return self.archives.get(caselist, [])

    async def archive_size(self, archive: ArchiveListing) -> int | None:
        self.asked.append(f"size {archive.name}")
        answer = self.sizes[archive.name]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    async def aclose(self) -> None:
        self.closed = True


def a_source() -> FakeSource:
    return FakeSource(
        current=[
            info("testcl26", archived=False),
            info("testcl25", archived=False),
            info("collegecl25", level="college"),
        ],
        archived=[
            info("testcl25"),  # listed by both calls: counted once
            info("testcl24"),
            info("testpf24", event="pf"),
            info("testcl21"),
            info("testcl20"),
            info("testcl19"),
        ],
        archives={
            "testcl25": [
                weekly("testcl25", date(2026, 7, 28)),
                complete("testcl25", date(2026, 6, 30)),
                complete("testcl25", date(2026, 7, 28)),
            ],
            "testcl24": [complete("testcl24", date(2025, 7, 29))],
            "testpf24": [weekly("testpf24", date(2025, 7, 29))],
            "testcl21": [complete("testcl21", date(2022, 7, 26))],
        },
        sizes={
            "testcl25-all-2026-07-28.zip": 3_000_000_000,
            "testcl24-all-2025-07-29.zip": 2_500_000_000,
            "testcl21-all-2022-07-26.zip": None,
        },
    )


def survey(source: FakeSource, first: int = 2021, last: int = 2025, *, sizes: bool = True):
    return asyncio.run(
        BackfileSurvey(source).survey(first_season_start=first, last_season_start=last, sizes=sizes)
    )


def test_seasons_are_read_from_the_year_a_slug_starts_in() -> None:
    assert season_start_year("testcl21") == 2021
    assert season_label(2021) == "2021-22"
    assert season_label(2099) == "2099-00"


def test_each_surveyed_season_is_counted_newest_first_with_the_newest_complete_archives_size() -> None:
    result = survey(a_source())

    rows = {one.slug: one for one in result.caselists}
    assert [one.slug for one in result.caselists] == ["testcl25", "testcl24", "testpf24", "testcl21"]
    assert rows["testcl25"].season == "2025-26"
    assert rows["testcl25"].weeklies_listed == 1
    assert rows["testcl25"].complete_archives_listed == 2
    assert rows["testcl25"].newest_complete_archive == date(2026, 7, 28)
    assert rows["testcl25"].complete_archive_bytes == 3_000_000_000
    assert rows["testpf24"].complete_archives_listed == 0
    assert rows["testpf24"].complete_archive_bytes is None
    assert rows["testpf24"].unanswered is None
    assert rows["testcl21"].unanswered == "NO_CONTENT_LENGTH"
    assert result.complete_archive_bytes == 5_500_000_000
    totals = {one.season: one for one in result.season_totals()}
    assert totals["2024-25"].caselists == 2
    assert totals["2024-25"].with_complete_archive == 1
    assert totals["2024-25"].complete_archive_bytes == 2_500_000_000
    assert totals["2021-22"].sized == 0


def test_only_the_newest_complete_archive_is_sized_and_nothing_is_downloaded() -> None:
    source = a_source()

    result = survey(source)

    sized = [one for one in source.asked if one.startswith("size ")]
    assert sized == [
        "size testcl25-all-2026-07-28.zip",
        "size testcl24-all-2025-07-29.zip",
        "size testcl21-all-2022-07-26.zip",
    ]
    assert result.size_requests == 3
    assert result.listing_requests == 2 + 4
    assert not hasattr(source, "download_archive")


def test_seasons_before_2021_22_and_the_current_season_are_counted_never_asked_about() -> None:
    source = a_source()

    result = survey(source)

    assert "archives testcl20" not in source.asked
    assert "archives testcl19" not in source.asked
    assert "archives testcl26" not in source.asked
    assert result.high_school_before_backfiles == 2
    assert result.high_school_after_survey == 1
    assert result.not_high_school == 1
    assert result.listed_caselists == 8  # nine answers, one slug in both


def test_a_first_season_before_2021_22_is_refused_before_any_request() -> None:
    source = a_source()

    with pytest.raises(ConfigurationError, match="before 2021-22 are not imported"):
        survey(source, first=2020)
    with pytest.raises(ConfigurationError, match="before the first"):
        survey(source, first=2024, last=2023)
    assert source.asked == []


def test_without_sizes_no_size_is_asked() -> None:
    source = a_source()

    result = survey(source, sizes=False)

    assert not [one for one in source.asked if one.startswith("size ")]
    assert {one.unanswered for one in result.caselists if one.complete_archives_listed} == {"NOT_ASKED"}


def test_a_file_host_that_refuses_one_size_leaves_that_size_unknown_and_goes_on() -> None:
    source = a_source()
    source.sizes["testcl25-all-2026-07-28.zip"] = ArchiveUnavailable("testcl25-all-2026-07-28.zip", 403)

    result = survey(source)

    rows = {one.slug: one for one in result.caselists}
    assert rows["testcl25"].complete_archive_bytes is None
    assert rows["testcl25"].unanswered == "ARCHIVE_UNAVAILABLE"
    assert rows["testcl24"].complete_archive_bytes == 2_500_000_000


@pytest.mark.parametrize(
    "stop",
    [
        ProviderRateLimited("opencaselist", "rate limited", retry_after_seconds=86_400.0),
        CaselistAuthExpired(401, "x"),
    ],
)
def test_the_rate_limiter_or_an_expired_token_stops_the_survey(stop: BaseException) -> None:
    source = a_source()
    source.sizes["testcl25-all-2026-07-28.zip"] = stop

    with pytest.raises(type(stop)):
        survey(source)
    assert "archives testcl24" not in source.asked


def test_a_level_the_api_gives_decides_high_school_and_the_slug_decides_only_without_one() -> None:
    assert is_high_school(info("testcl24", level="HS"))
    assert not is_high_school(info("hsld24", level="college"))
    assert is_high_school(info("hsld24", level=None))
    assert not is_high_school(info("testcl24", level=None))


def test_the_survey_closes_its_source() -> None:
    source = a_source()

    async def run() -> None:
        async with BackfileSurvey(source) as survey:
            await survey.survey(first_season_start=2021, last_season_start=2025)

    asyncio.run(run())
    assert source.closed

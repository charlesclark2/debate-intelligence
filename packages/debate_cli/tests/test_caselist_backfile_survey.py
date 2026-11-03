"""`caselist backfile-survey` (`v1-e34-t34` ac1): the rendering, the season options and the defaults.

The survey itself is :mod:`debate_core.application.caselist.backfile_survey`'s and is tested there;
here a fake source stands behind the container's `backfile_survey` seam, and the rest is the real
command. Every slug and date is synthetic.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Annotated, Any

import typer
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands import caselist_backfile
from debate_cli.commands.caselist_backfile import current_season_start
from debate_cli.context import cli_context
from debate_core.application.caselist.backfile_survey import BackfileSurvey
from debate_core.application.ports.caselist_source import ArchiveKind, ArchiveListing, CaselistInfo
from debate_core.domain import season

runner = CliRunner()
ON_A_SUNDAY_IN_OCTOBER = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)


class FakeSource:
    def __init__(self) -> None:
        self.asked: list[str] = []
        self.closed = False

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        self.asked.append(f"caselists archived={archived}")
        if not archived:
            return [CaselistInfo(slug="testcl26", level="hs", event="ld", year=2026)]
        return [
            CaselistInfo(slug=f"testcl{year}", level="hs", event="ld", year=2000 + year, archived=True)
            for year in (19, 20, 21, 22, 23, 24, 25)
        ]

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        self.asked.append(f"archives {caselist}")
        name = f"{caselist}-all-2026-07-28.zip"
        url = f"https://caselist-files.example.invalid/weekly/{caselist}/{name}"
        return [
            ArchiveListing(
                caselist=caselist, name=name, kind=ArchiveKind.FULL, archive_date=date(2026, 7, 28), url=url
            )
        ]

    async def archive_size(self, archive: ArchiveListing) -> int | None:
        self.asked.append(f"size {archive.caselist}")
        return 1_000_000 * int(archive.caselist[-2:])

    async def aclose(self) -> None:
        self.closed = True


def app_over(source: FakeSource) -> typer.Typer:
    def backfile_survey(
        ctx: typer.Context,
        first_season: Annotated[str | None, typer.Option("--first-season")] = None,
        last_season: Annotated[str | None, typer.Option("--last-season")] = None,
        sizes: Annotated[bool, typer.Option("--sizes/--no-sizes")] = True,
    ) -> None:
        services = cli_context(ctx).services
        services.override("backfile_survey", BackfileSurvey(source))
        services.override("clock", lambda: ON_A_SUNDAY_IN_OCTOBER)
        caselist_backfile.backfile_survey(ctx, first_season, last_season, sizes)

    app = create_app()
    caselist = next(
        group.typer_instance
        for group in app.registered_groups
        if group.typer_instance is not None and group.typer_instance.info.name == "caselist"
    )
    commands = caselist.registered_commands
    caselist.registered_commands = [one for one in commands if one.name != "backfile-survey"]
    caselist.command("backfile-survey")(backfile_survey)
    return app


def invoke(source: FakeSource, *arguments: str) -> Result:
    return runner.invoke(app_over(source), list(arguments))


def data_of(result: Result) -> dict[str, Any]:
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert isinstance(envelope, dict)
    return envelope["data"]


def test_by_default_it_surveys_2021_22_to_the_season_before_this_one() -> None:
    source = FakeSource()

    data = data_of(invoke(source, "--json", "caselist", "backfile-survey"))

    assert (data["first_season"], data["last_season"]) == ("2021-22", "2025-26")
    assert [one["slug"] for one in data["caselists"]] == [
        "testcl25",
        "testcl24",
        "testcl23",
        "testcl22",
        "testcl21",
    ]
    assert data["high_school_before_backfiles"] == 2
    assert data["high_school_after_survey"] == 1
    assert data["complete_archive_bytes"] == 1_000_000 * (25 + 24 + 23 + 22 + 21)
    assert data["seasons"][0] == {
        "season": "2025-26",
        "caselists": 1,
        "with_complete_archive": 1,
        "sized": 1,
        "complete_archive_bytes": 25_000_000,
    }
    assert source.closed


def test_the_json_names_no_archive_url_or_file_name() -> None:
    result = invoke(FakeSource(), "--json", "caselist", "backfile-survey")

    assert result.exit_code == 0
    assert ".zip" not in result.stdout
    assert "example.invalid" not in result.stdout


def test_the_seasons_can_be_narrowed() -> None:
    source = FakeSource()

    data = data_of(
        invoke(
            source,
            "--json",
            "caselist",
            "backfile-survey",
            "--first-season",
            "2024-25",
            "--last-season",
            "2025-26",
        )
    )

    assert [one["slug"] for one in data["caselists"]] == ["testcl25", "testcl24"]
    assert "archives testcl23" not in source.asked


def test_a_season_before_2021_22_is_refused_and_nothing_is_asked() -> None:
    source = FakeSource()

    result = invoke(source, "--json", "caselist", "backfile-survey", "--first-season", "2020-21")

    assert result.exit_code != 0
    assert "2021-22" in result.stdout
    assert source.asked == []


def test_a_season_that_is_not_two_consecutive_years_is_refused() -> None:
    for text in ("2021", "2021-23", "21-22"):
        result = invoke(FakeSource(), "--json", "caselist", "backfile-survey", "--last-season", text)
        assert result.exit_code != 0, text


def test_the_table_says_nothing_was_downloaded() -> None:
    result = invoke(FakeSource(), "caselist", "backfile-survey", "--no-sizes")

    assert result.exit_code == 0, result.output
    assert "nothing was downloaded" in " ".join(result.stdout.split())
    assert "NOT_ASKED" in result.stdout


def test_a_season_starts_on_the_first_of_august() -> None:
    assert current_season_start(date(2026, 7, 31)) == 2025
    assert current_season_start(date(2026, 8, 1)) == 2026


def test_the_command_reads_the_domains_season_rule_unchanged() -> None:
    """Moved to `debate_core.domain.season` in `v1-e39-t28`, for the camp link: the CLI keeps no copy."""
    assert current_season_start is season.current_season_start

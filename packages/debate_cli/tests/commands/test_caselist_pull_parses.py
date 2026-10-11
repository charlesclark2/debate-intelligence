"""`debate-research caselist pull` parses the sources it imported (`v1-e34-t17`).

Through Typer's `CliRunner` against the real application and the real composition root, as
`test_caselist_pull.py` runs it: the real OpenCaselist client answered by respx, the real importers,
the real parse pipeline. So what is under test here is the wiring: that `caselist pull` builds the
parse stage unless the setting turns it off, hands it the caselists the run imported, and reports
its counts.

Two things are replaced, both to make the parser countable from this process. The `.docx` parser
the composition root builds is a subclass that records every source it is asked to read, and the
pool is the in-process runner, because a worker process's list is not this one's. The pool has its
own tests (`debate_core/tests/application/test_caselist_parse.py`).

The archives are the fictional caselist of `tests/fixtures/parse_pipeline/build_parse_world.py`,
whose documents hold cards. Every expected count is that fixture's hand-written table (working
agreement 6): 09-01 and 09-08 hold six distinct sources, of which three parse into four cards, a
PDF and a `.doc` are unsupported, and one is not a zip; 09-15 adds one source holding one card.
The `test` environment names no bucket, so nothing is published here; publishing is covered against
moto in `debate_core/tests/application/caselist/test_pull_parses_new_sources.py`.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

import pytest
import respx
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS, build_week_zips, digest_of
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist_pull_parse import PullParseStage
from debate_core.application.settings import load_settings
from debate_core.domain.caselist import SnapshotDate, SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser

API = "https://api.opencaselist.example.invalid/v1"
FILE_HOST = "https://files.opencaselist.example.invalid"
WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)

FIRST_TWO_WEEKS = ("verbatim", "wiki", "pdf", "cardmirror", "doc", "broken")
"""The six distinct sources 09-01 and 09-08 hold, by the fixture's short names."""

runner = CliRunner()


def weekly_name(day: date) -> str:
    return f"{CASELIST}-weekly-{day.isoformat()}.zip"


class CountingDocxParser(DebateDocxParser):
    """The real parser, recording the digest of every source it is asked to read."""

    asked: ClassVar[list[str]] = []

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        type(self).asked.append(source.sha256)
        return super().parse(content, source, source_path=source_path, snapshot=snapshot, camp=camp)


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every source the composition root's parser was asked to read, in order."""
    CountingDocxParser.asked.clear()
    monkeypatch.setattr("debate_core.integrations.docx_parser.DebateDocxParser", CountingDocxParser)
    monkeypatch.setattr("debate_cli.container.ProcessPoolParseRunner", lambda **_: InProcessParseRunner())
    yield CountingDocxParser.asked
    CountingDocxParser.asked.clear()


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A `test` environment of this test's own: the API on, a token in the environment, no bucket."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    data = tmp_path / "data"
    for name, value in {
        "DEBATE_ENV": "test",
        "DEBATE_STORAGE__DATA_DIR": str(data),
        "DEBATE_ALLOW_NETWORK": "true",
        "DEBATE_CASELIST__API_ENABLED": "true",
        "DEBATE_CASELIST__API_BASE_URL": API,
        "DEBATE_CASELIST__MIN_REQUEST_INTERVAL_SECONDS": "0.5",
        "DEBATE_PROVIDERS__CASELIST_TOKEN": f"fixture-token-{secrets.token_hex(8)}",
        "DEBATE_CASELIST__FULL_ARCHIVE_ROTATION": "false",
    }.items():
        monkeypatch.setenv(name, value)
    yield data


@pytest.fixture
def site(tmp_path: Path) -> Iterator[respx.MockRouter]:
    """OpenCaselist serving the fictional caselist's weeklies; :func:`listing` says which it lists."""
    zips = build_week_zips(tmp_path / "published")
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/openev").respond(200, json=[])
        for week in WEEKS:
            router.get(f"{FILE_HOST}/{weekly_name(week.snapshot)}").respond(
                200, content=zips[week.snapshot].read_bytes()
            )
        yield router


def listing(site: respx.MockRouter, *weeks: date) -> None:
    """Make the site list exactly `weeks`, as it does once a new weekly archive is published."""
    site.get(f"{API}/caselists/{CASELIST}/downloads").respond(
        200, json=[{"name": weekly_name(day), "url": f"{FILE_HOST}/{weekly_name(day)}"} for day in weeks]
    )


def pull(*arguments: str) -> dict[str, Any]:
    """Run `caselist pull` asking for JSON, and return its envelope with the exit code on it."""
    result: Result = runner.invoke(create_app(), ["--json", "caselist", "pull", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}"
    envelope = json.loads(lines[0])
    assert isinstance(envelope, dict)
    envelope["exit_code"] = result.exit_code
    return envelope  # pyright: ignore[reportUnknownVariableType]


def stage(envelope: dict[str, Any], name: str) -> dict[str, Any]:
    [found] = [one for one in envelope["data"]["stages"] if one["stage"] == name]
    return found


def parsed_tree(data_dir: Path) -> dict[str, tuple[bytes, int]]:
    """Every file of the parsed store with its bytes and modification time."""
    root = data_dir / "parsed"
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def aggregate(data_dir: Path, name: str) -> list[dict[str, Any]]:
    path = data_dir / "parsed" / CASELIST / DOCX_PARSER_VERSION / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ------------------------------------------------------------------------------------------------
# ac1: a pull parses what it imported, and nothing when it imported nothing
# ------------------------------------------------------------------------------------------------


def test_a_pull_that_imports_a_new_snapshot_parses_only_that_snapshots_new_sources(
    installation: Path, site: respx.MockRouter, asked: list[str]
) -> None:
    """Two weeks, then a third: the second pull's parser is asked for the one source 09-15 adds.

    The first pull finds no version directory, so it parses all six sources the two weeks hold. The
    second finds those six recorded under the same skip key and parses `direct` alone, and rebuilds
    the aggregates over all seven.
    """
    listing(site, WEEK_1, WEEK_2)
    first = pull("--caselist", CASELIST)

    assert first["exit_code"] == ExitCode.OK, first
    assert sorted(asked) == sorted(digest_of(body) for body in FIRST_TWO_WEEKS)
    assert stage(first, "parse")["outcome"] == "completed", stage(first, "parse")
    assert first["data"]["parse"] == {
        "caselists": 1,
        "full_parses": 1,
        "attempted": 6,
        "skipped": 0,
        "unsupported": 2,
        "failed": 1,
        "cards": 4,
        "uploaded": 0,
        "not_published": 0,
    }

    asked.clear()
    listing(site, WEEK_1, WEEK_2, WEEK_3)
    second = pull("--caselist", CASELIST)

    assert second["exit_code"] == ExitCode.OK, second
    assert second["data"]["snapshots_imported"] == [f"{CASELIST} {WEEK_3.isoformat()}"]
    assert asked == [digest_of("direct")]
    assert second["data"]["parse"] == {
        "caselists": 1,
        "full_parses": 0,
        "attempted": 1,
        "skipped": 6,
        "unsupported": 0,
        "failed": 0,
        "cards": 1,
        "uploaded": 0,
        "not_published": 0,
    }
    # The aggregates were rebuilt over every source the caselist holds, not only the new one.
    assert len(aggregate(installation, "index.jsonl")) == 7
    assert len(aggregate(installation, "occurrences.jsonl")) == 7
    assert {row["last_snapshot"] for row in aggregate(installation, "occurrences.jsonl")} == {"2026-09-15"}


def test_a_pull_that_imports_nothing_parses_nothing(
    installation: Path, site: respx.MockRouter, asked: list[str]
) -> None:
    """The same listing again: no parser call, no rebuild, and a stage that says why it was skipped."""
    listing(site, WEEK_1, WEEK_2)
    pull("--caselist", CASELIST)
    before = parsed_tree(installation)
    assert before, "the first pull parsed"
    asked.clear()

    again = pull("--caselist", CASELIST)

    assert again["exit_code"] == ExitCode.OK
    assert again["data"]["snapshots_imported"] == []
    assert asked == []
    assert stage(again, "parse") == {
        "stage": "parse",
        "outcome": "skipped",
        "reason": "nothing new was imported",
        "error_codes": [],
        "hint": None,
    }
    assert again["data"]["parse"] is None
    assert parsed_tree(installation) == before


# ------------------------------------------------------------------------------------------------
# ac3: counts only, under a new schema version
# ------------------------------------------------------------------------------------------------


def test_the_summary_carries_the_stages_counts_and_nothing_else_under_schema_version_five(
    installation: Path, site: respx.MockRouter, asked: list[str]
) -> None:
    listing(site, WEEK_1, WEEK_2)

    envelope = pull("--caselist", CASELIST)

    data = envelope["data"]
    assert data["schema_version"] == 5
    assert all(type(count) is int for count in data["parse"].values()), data["parse"]
    assert {"attempted", "skipped", "unsupported", "failed", "cards", "uploaded"} <= set(data["parse"])
    # The two keys the object replaces, which no stage ever filled, are gone.
    assert "cards_parsed" not in data and "parse_failures" not in data
    written = json.loads(Path(data["summary_written_to"]).read_text(encoding="utf-8"))
    assert written["parse"] == data["parse"]


def test_nothing_the_pull_prints_or_logs_names_a_school_a_team_a_file_or_a_card(
    installation: Path, site: respx.MockRouter, asked: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Forbidden item 2: the summary, the run record, and every log record at INFO or above."""
    listing(site, WEEK_1, WEEK_2)
    with caplog.at_level(logging.INFO):
        result = runner.invoke(create_app(), ["--json", "caselist", "pull", "--caselist", CASELIST])

    assert result.exit_code == ExitCode.OK
    summaries = "".join(
        path.read_text(encoding="utf-8") for path in sorted((installation / "caselist-sync-runs").glob("*"))
    )
    run_log = (installation / "caselist-sync-runs.jsonl").read_text(encoding="utf-8")
    logged = "\n".join(record.getMessage() for record in caplog.records if record.levelno >= logging.INFO)
    assert "caselist parse" in logged, "the parse pipeline's own count line was captured"
    for text in (result.stdout, summaries, run_log, logged):
        for forbidden in (*FICTIONAL_IDENTIFIERS, ".docx", ".pdf", "Invitational", "Round 1"):
            assert forbidden not in text, f"{forbidden!r} must never reach a summary or a log"


# ------------------------------------------------------------------------------------------------
# ac4: the setting that turns the stage off
# ------------------------------------------------------------------------------------------------


def test_the_stage_is_on_unless_the_setting_turns_it_off(
    installation: Path, site: respx.MockRouter, asked: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__PARSE_IMPORTED_SOURCES", "false")
    listing(site, WEEK_1, WEEK_2)

    envelope = pull("--caselist", CASELIST)

    assert envelope["exit_code"] == ExitCode.OK
    assert envelope["data"]["snapshots_imported"], "the pull itself is unchanged"
    assert asked == []
    assert stage(envelope, "parse")["outcome"] == "skipped"
    assert "caselist.parse_imported_sources" in stage(envelope, "parse")["reason"]
    assert envelope["data"]["parse"] is None
    assert not (installation / "parsed").exists()


def test_a_dry_run_says_it_would_parse_and_parses_nothing(
    installation: Path, site: respx.MockRouter, asked: list[str]
) -> None:
    listing(site, WEEK_1, WEEK_2)

    envelope = pull("--caselist", CASELIST, "--dry-run")

    assert stage(envelope, "parse")["outcome"] == "planned"
    assert asked == []
    assert not (installation / "parsed").exists()


def test_the_composition_root_builds_the_stage_over_the_pulls_own_suppression_list(
    installation: Path,
) -> None:
    """The stage's pipeline holds the very list the pull holds, and the settings' two defaults.

    The same object, not an equal one: the run tells that the list was read from this machine's
    copy alone by that object's fallback count, and a pipeline built over another list would never
    move it. No bucket in `test`, so the stage has no publisher.
    """
    container = ServiceContainer(settings_loader=load_settings)

    sync = container.caselist_sync(event_for_caselist=lambda _: None)

    stage_built = sync._parse  # pyright: ignore[reportPrivateUsage]
    assert isinstance(stage_built, PullParseStage)
    pipeline = stage_built._parse  # pyright: ignore[reportPrivateUsage]
    assert pipeline._suppression is sync._suppression  # pyright: ignore[reportPrivateUsage]
    assert stage_built._publisher is None  # pyright: ignore[reportPrivateUsage]
    assert pipeline._threshold == 0.05  # pyright: ignore[reportPrivateUsage]
    assert pipeline._minimum_sources == 100  # pyright: ignore[reportPrivateUsage]


# ------------------------------------------------------------------------------------------------
# ac2: a failed parse stage is reported with its code, and the exit is v1-e34-t13's
# ------------------------------------------------------------------------------------------------


def test_a_parse_stage_over_the_failure_rate_is_reported_and_the_run_still_exits_zero(
    installation: Path, site: respx.MockRouter, asked: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One of the four sources tried fails: 25%, over a 20% threshold, in a run of at least four.

    `v1-e34-t13`'s rule reads the stages that put bytes somewhere durable, and parse is not one:
    the stage is failed with its code, the import stands, and the command exits 0.
    """
    monkeypatch.setenv("DEBATE_PARSE__FAILURE_RATE_THRESHOLD", "0.2")
    monkeypatch.setenv("DEBATE_PARSE__FAILURE_RATE_MINIMUM_SOURCES", "4")
    listing(site, WEEK_1, WEEK_2)

    envelope = pull("--caselist", CASELIST)

    assert envelope["exit_code"] == ExitCode.OK
    parse = stage(envelope, "parse")
    assert (parse["outcome"], parse["error_codes"]) == ("failed", ["PARSE_FAILURE_RATE_EXCEEDED"])
    assert envelope["data"]["succeeded"] is True
    assert envelope["data"]["snapshots_imported"] == [
        f"{CASELIST} {WEEK_1.isoformat()}",
        f"{CASELIST} {WEEK_2.isoformat()}",
    ]
    assert envelope["data"]["parse"]["failed"] == 1
    assert envelope["data"]["run_record"]["outcome"] == "incomplete"

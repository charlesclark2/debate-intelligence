"""The weekly run logs each stage as it starts and ends, and the parse its progress (`v1-e40-t43`).

`caselist pull`'s result is one line when it ends, so the hand run of 2026-11-05 left its log empty
for over an hour. :meth:`CaselistSyncService.run` now tells its `on_line` of each stage as it starts
and ends, in `v1-e40-t32`'s step lines, and the parse of its progress. These tests hold:

* the lines' order, one start and one end per stage, a landscape stage's only when one is installed;
* each end line's seconds and memory figures, which are its `stage_times` entry's, its counts, which
  are the fixture's where the fixture fixes them and the summary's elsewhere, and its outcome;
* the parse's progress lines at the interval, on a clock the test moves, with the sources and the
  caselists done and left, worked out by hand;
* a stage that fails without raising ends `step_ended` with the outcome `failed`, and one that
  raises ends `step_failed` with no stage after it;
* no line holds a school, a team, a tournament, a file name, a caselist or a path.

The restore's and the saves' lines are `run_pull`'s, over the real bucket-mode bracket: the CLI's
`bucket_mode/test_pull_stage_lines.py` holds them, with the lines as written and the metric filter.

The installation is `test_inbox_retention.py`'s: the real importers, publisher, status comparison and
parse pipeline against moto, and the fictional caselist of `tests/fixtures/parse_pipeline/`. No socket.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import build_week_zips

from debate_core.application.caselist.memory_high_water import MemoryHighWater
from debate_core.application.caselist.step_lines import (
    PARSE_PROGRESS_INTERVAL_SECONDS,
    SourceProgress,
    StepEvent,
    StepLine,
)
from debate_core.application.caselist_sync import (
    LandscapeStageResult,
    ParsedCaselist,
    PublishedParsedStore,
    RunSummary,
    StageOutcome,
    SyncStage,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_inbox_retention import (
    CASELIST,
    ESTUARY,
    ESTUARY_BODY,
    RUN_CLOCK,
    WEEK_1,
    WEEK_2,
    FakeSource,
    Installation,
)
from .test_pull_parses_new_sources import parse_stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

MEMORY: Final = MemoryHighWater(
    container_peak_bytes=12_884_901_888, cgroup="v1", main_process_peak_bytes=2_147_483_648
)
"""What every end and progress line says of the memory: the stand-in reader's one answer."""

STAGES: Final = ("select", "download", "import", "publish", "parse", "search_index", "report", "retention")
"""A whole run's stages in order, with no landscape service installed, as `SyncStage` lists them."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    """An empty data directory, a moto bucket, and the fictional caselist's weeklies to serve."""
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_week_zips(tmp_path / "published"),
    )


@dataclass
class TickingClock:
    """The run's clock, a second and a half later each time it is read, or moved by the test."""

    now: datetime = RUN_CLOCK
    tick: timedelta = timedelta(seconds=1.5)

    def __call__(self) -> datetime:
        self.now += self.tick
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Heard(list[StepLine]):
    """Every line the run told, in order."""

    def events(self) -> list[tuple[str, str]]:
        return [(str(line.event), line.step) for line in self]

    def ends(self) -> dict[str, StepLine]:
        return {line.step: line for line in self if line.event is StepEvent.ENDED}

    def progress(self) -> list[StepLine]:
        return [line for line in self if line.event is StepEvent.PARSE_PROGRESS]


def start_and_end(*steps: str) -> list[tuple[str, str]]:
    return [pair for step in steps for pair in (("step_started", step), ("step_ended", step))]


def durations(summary: RunSummary) -> dict[str, float]:
    return {str(one.stage): one.duration_seconds for one in summary.stage_times}


class TenSourcesEach:
    """A parse stage whose every caselist has ten sources, each taking 100 s on the run's clock."""

    def __init__(self, clock: TickingClock) -> None:
        self._clock = clock
        self.parsed: list[str] = []

    async def parse_new_sources(
        self, caselist: str, *, progress: SourceProgress | None = None
    ) -> ParsedCaselist:
        self.parsed.append(caselist)
        assert progress is not None, "the run hands every parse its progress"
        progress.start(10)
        for done in range(1, 11):
            self._clock.advance(100)
            progress(done)
        return ParsedCaselist(version="2026.11.03-docx-9", attempted=10, cards=10, tried=10)

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:
        return PublishedParsedStore(uploaded=1)


class StoppedInTheParse:
    """A parse stage the run's SIGTERM cancels: what `BucketRun.terminate` does to the run's task."""

    async def parse_new_sources(
        self, caselist: str, *, progress: SourceProgress | None = None
    ) -> ParsedCaselist:
        raise asyncio.CancelledError

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:  # pragma: no cover
        raise AssertionError("never reached")


class WritesTwoReports:
    """An installed landscape stage."""

    async def regenerate(self, *, caselists: Sequence[str]) -> LandscapeStageResult:
        return LandscapeStageResult(reports_written=2)


async def test_each_stage_logs_its_start_and_its_end_in_order_with_its_seconds_counts_and_memory(
    installation: Installation,
) -> None:
    """A first pull of 09-01 and 09-08, parsed: the fixture's table gives the counts.

    Two weeklies listed, both wanted and fetched; six distinct sources, of which three parse
    (`verbatim` 1 card, `wiki` 2, `cardmirror` 1), two are unsupported and one fails; nine objects
    of the parsed store uploaded. The run's clock ticks, so every stage takes some seconds.
    """
    heard = Heard()
    clock = TickingClock()
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    service = installation.sync(
        source, parse=parse_stage(installation), clock=clock, read_memory=lambda: MEMORY
    )

    summary = await service.run([CASELIST], on_line=heard.append)

    progress = [("parse_progress", "parse")] * 2
    assert heard.events() == [
        *start_and_end(*STAGES[:4]),
        ("step_started", "parse"),
        *progress,
        ("step_ended", "parse"),
        *start_and_end(*STAGES[5:]),
    ]
    ends = heard.ends()
    timed = durations(summary)
    assert timed.pop("landscape") > 0, "timed in `stage_times` without a service, and said nowhere"
    assert {step: line.seconds for step, line in ends.items()} == timed
    assert all(line.seconds is not None and line.seconds > 0 for line in ends.values())
    assert {line.memory for line in heard if line.event is not StepEvent.STARTED} == {MEMORY}
    assert [line.memory for line in heard if line.event is StepEvent.STARTED] == [None] * len(STAGES)
    assert all(line.seconds is None and not line.counts for line in heard if line.event is StepEvent.STARTED)
    served = sum(installation.archives[week].stat().st_size for week in (WEEK_1, WEEK_2))
    assert ends["select"].counts == {
        "archives_seen": 2,
        "archives_wanted": 2,
        "archives_deferred": 0,
        "openev_seen": 0,
    }
    assert ends["download"].counts == {
        "archives_downloaded": 2,
        "openev_downloaded": 0,
        "downloaded_bytes": served,
    }
    assert ends["import"].counts == {
        "snapshots_imported": 2,
        "files_imported": summary.files_imported,
        "files_duplicate": summary.files_duplicate,
        "files_skipped": summary.files_skipped,
        "blobs_stored": summary.blobs_stored,
        "held_by_request": 0,
    }
    assert ends["publish"].counts == {
        "objects_published": summary.objects_published,
        "manifests_published": 2,
        "pending_publish": 0,
    }
    assert ends["parse"].counts == {
        "caselists": 1,
        "full_parses": 1,
        "attempted": 6,
        "skipped": 0,
        "unsupported": 2,
        "failed": 1,
        "cards": 4,
        "uploaded": 9,
        "not_published": 0,
    }
    assert ends["search_index"].counts == {}, "no search index stage is wired in here"
    assert ends["report"].counts == {"snapshots_confirmed": 2}
    assert ends["retention"].counts == {
        "files_removed": 2,
        "files_kept": 0,
        "bytes_freed": served,
    }
    assert {step: line.outcome for step, line in ends.items()} == {
        **dict.fromkeys(STAGES, "completed"),
        "search_index": "skipped",
    }


async def test_the_parse_logs_its_progress_every_five_minutes_with_the_sources_and_caselists_done_and_left(
    installation: Installation,
) -> None:
    """Two caselists, the weekly one and `openev`, of ten sources of 100 s each, at five minutes.

    Worked by hand for each caselist: a line at 0 done once it knows ten, then one at the first
    source to finish 300 s or more after the last line (3 at 300 s, 6 at 600 s, 9 at 900 s), and one
    when the last is done (10 at 1000 s). Its seconds count from the caselist's start; the interval
    from the last line, not from the start.
    """
    heard = Heard()
    clock = TickingClock(tick=timedelta(0))
    stage = TenSourcesEach(clock)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2], openev=[(ESTUARY, ESTUARY_BODY)])
    service = installation.sync(source, parse=stage, clock=clock, read_memory=lambda: MEMORY)

    await service.run([CASELIST], on_line=heard.append)

    assert PARSE_PROGRESS_INTERVAL_SECONDS == 300.0
    assert stage.parsed == [CASELIST, "openev"]
    each = [(0, 10, 0.0), (3, 7, 300.0), (6, 4, 600.0), (9, 1, 900.0), (10, 0, 1000.0)]
    assert [(line.seconds, dict(line.counts)) for line in heard.progress()] == [
        (
            seconds,
            {
                "sources_done": done,
                "sources_left": left,
                "caselists_done": number,
                "caselists_left": 2 - number,
            },
        )
        for number in (0, 1)
        for done, left, seconds in each
    ]
    events = heard.events()
    started, ended = events.index(("step_started", "parse")), events.index(("step_ended", "parse"))
    assert [index for index, pair in enumerate(events) if pair[0] == "parse_progress"] == list(
        range(started + 1, ended)
    ), "every progress line falls between the parse's start and its end"
    assert {line.memory for line in heard.progress()} == {MEMORY}


async def test_a_stage_that_fails_without_raising_ends_with_the_outcome_failed_and_the_run_goes_on(
    installation: Installation,
) -> None:
    """One of the four sources tried fails, in a run just large enough for 25% to fail the stage."""
    heard = Heard()
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    service = installation.sync(source, parse=parse_stage(installation, threshold=0.2, minimum=4))

    summary = await service.run([CASELIST], on_line=heard.append)

    parse = summary.stage(SyncStage.PARSE)
    assert parse is not None and parse.outcome is StageOutcome.FAILED
    ends = heard.ends()
    assert ends["parse"].outcome == "failed"
    assert ends["parse"].counts["failed"] == 1
    assert ("step_failed", "parse") not in heard.events()
    assert heard.events()[-2:] == start_and_end("retention"), "the run goes on to its last stage"


async def test_a_stage_that_raises_ends_step_failed_and_no_stage_starts_after_it(
    installation: Installation,
) -> None:
    """A SIGTERM in the parse: its line says how long it ran and how full the task was, then nothing."""
    heard = Heard()
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    service = installation.sync(
        source, parse=StoppedInTheParse(), clock=TickingClock(), read_memory=lambda: MEMORY
    )

    with pytest.raises(asyncio.CancelledError):
        await service.run([CASELIST], on_line=heard.append)

    assert heard.events() == [
        *start_and_end(*STAGES[:4]),
        ("step_started", "parse"),
        ("step_failed", "parse"),
    ]
    failed = heard[-1]
    assert failed.seconds is not None and failed.seconds > 0
    assert failed.memory == MEMORY
    assert failed.outcome is None, "a stage that raised recorded no outcome"


async def test_a_landscape_stage_logs_its_start_and_end_only_when_one_is_installed(
    installation: Installation,
) -> None:
    without, with_one = Heard(), Heard()
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    await installation.sync(source).run([CASELIST], on_line=without.append)
    source.weeks = [WEEK_1, WEEK_2]
    await installation.sync(source, landscape=WritesTwoReports()).run([CASELIST], on_line=with_one.append)

    assert "landscape" not in {step for _, step in without.events()}
    assert [pair for pair in with_one.events() if pair[1] == "landscape"] == start_and_end("landscape")
    assert with_one.ends()["landscape"].counts == {"reports_written": 2}
    assert with_one.ends()["landscape"].outcome == "completed"


async def test_a_dry_run_and_publish_pending_log_the_stages_they_carry_out(
    installation: Installation,
) -> None:
    dry, pending = Heard(), Heard()
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    await installation.sync(source).run([CASELIST], dry_run=True, on_line=dry.append)
    await installation.sync(source).publish_pending(on_line=pending.append)

    assert dry.events() == start_and_end("select", "retention")
    assert dry.ends()["select"].counts == {
        "archives_seen": 1,
        "archives_wanted": 1,
        "archives_deferred": 0,
        "openev_seen": 0,
    }
    assert pending.events() == start_and_end("publish", "report")


async def test_no_line_names_a_school_a_team_a_tournament_a_file_a_caselist_or_a_path(
    installation: Installation, tmp_path: Path
) -> None:
    """Every line of a run that imports both weeks and a camp file, and parses them, read whole."""
    heard = Heard()
    clock = TickingClock(tick=timedelta(0))
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2], openev=[(ESTUARY, ESTUARY_BODY)])
    await installation.sync(source, parse=parse_stage(installation), clock=clock).run(
        [CASELIST], on_line=heard.append
    )

    assert {line.step for line in heard} == set(STAGES)
    said = [repr(line) for line in heard]
    # `openev` is a count's own word (`openev_seen`), never a name a line was handed.
    names = [*FICTIONAL_IDENTIFIERS, CASELIST, "Tamarack", "Estuary", ".docx", ".zip", str(tmp_path)]
    assert [name for name in names if any(name.lower() in one.lower() for one in said)] == []
    assert not [one for one in said if "/" in one or "\\" in one]
    assert all(type(count) is int for line in heard for count in line.counts.values())

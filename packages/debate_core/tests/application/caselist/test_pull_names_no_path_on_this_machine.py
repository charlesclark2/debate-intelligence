"""Nothing a pull leaves for a person to paste names a path on this machine (`v1-e34-t16`).

The scheduled-sync runbook says the run's output can be pasted into an issue as it is. A dry run
planned its download stage as `would download N file(s) into /Users/…/inbox`, so the operator's
home directory reached the JSON summary, which is what `caselist pull --json` prints and what the
launchd agent's stdout log keeps. The inbox is now named by its role, `into the inbox`, as every
failed stage's reason already named it (`v1-e34-t13`).

Every test here runs pulls in a data directory under :data:`DATA_PROBE`, with `HOME` set to a
directory under :data:`HOME_PROBE`, so that a string built from the data directory, from `~` or
from :meth:`Path.home` is caught alike. It then looks for either probe, for the test's temporary
directory, for the user's name and for any absolute path, in everything the pulls left for a
person: each run's JSON summary and summary file, its run record and its details, the run log and
the details log on this machine, both of them in the bucket, the text of every notification as the
macOS notifier would post it, the message of an error that stopped a run, and the log lines.

The pulls are `run_record_scenarios.SCENARIOS`, which `v1-e34-t19` wrote to cover every kind of run
a record describes (a week imported and published; a publish the bucket did not take, or refused; a
week that cannot be read; a publish left for a login and then drained; drift and then an expiry; an
expired token; an error nobody modelled; a parse; a refusal to start), and five more for the
outputs those do not reach: a dry run, camp files fetched and cleared from the inbox, a run another
run's lock refused, a camp download the inbox refused, and a manifest directory this machine
refused. What `caselist pull` and `caselist runs` render of the same runs is checked in `debate_cli`'s
`test_caselist_pull_names_no_path.py`.
"""

from __future__ import annotations

import getpass
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.permissions import needs_permissions

from debate_core.application.caselist_sync import (
    LOCK_FILENAME,
    RUN_SUMMARY_DIRECTORY,
    RunLock,
    StageOutcome,
    SyncStage,
    run_pull,
)
from debate_core.application.errors import DomainError, reported_error_message
from debate_core.application.sync_runs import SYNC_RUN_DETAILS_FILENAME, SYNC_RUN_LOG_FILENAME, SyncRunMonitor
from debate_core.integrations.local.macos_notifier import MacOsNotifier
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .run_record_scenarios import AWS_LOGIN, SCENARIOS, SECOND_RUN, World
from .test_inbox_retention import (
    CASELIST,
    ESTUARY,
    ESTUARY_BODY,
    RELEASE,
    RELEASE_BODY,
    WEEK_1,
    WEEK_2,
    FakeSource,
    Installation,
)
from .test_summary_names_no_camp_file import InboxRefusingSource

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

DATA_PROBE = "Zqxdataprobe"
"""In the path of the data directory, and so of the inbox inside it. Searched for case-insensitively."""

HOME_PROBE = "Zqxhomeprobe"
"""In the path `HOME` is set to, apart from the data directory. Searched for case-insensitively."""

ABSOLUTE_PATH = re.compile(r"(?<![\w.:/~-])(?:~/|/(?:Users|home|private|var|tmp|Volumes|opt|etc)/)")
"""The start of a path on a machine: what `sync_runs.hint_for_a_record` takes out of a hint.

Not after a word, a dot, a colon or a slash, so that `https://files.example.invalid/home/` and the
`docs/runbooks/…` a hint cites are not taken for one.
"""


@dataclass(frozen=True)
class Probe:
    """Where this test's data directory and home directory are, and how to tell either in a text."""

    root: Path
    data_dir: Path
    home: Path

    def found_in(self, text: str) -> list[str]:
        """What of this machine `text` names, by what it is; empty when it names nothing."""
        found = [
            what
            for what, needle in (
                ("the data directory's probe", DATA_PROBE),
                ("the home directory's probe", HOME_PROBE),
                ("the temporary directory", str(self.root)),
                ("the temporary directory, resolved", str(self.root.resolve())),
            )
            if needle.casefold() in text.casefold()
        ]
        user = getpass.getuser()
        if len(user) >= 3 and re.search(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", text, re.I):
            found.append("the user's name")
        if match := ABSOLUTE_PATH.search(text):
            around = text[max(match.start() - 60, 0) : match.end() + 60]
            found.append(f"an absolute path at {match.start()}: {around!r}")
        return found


@pytest.fixture
def probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Probe:
    """A data directory where the operator's is, under a home of its own, and `HOME` set to that home.

    The data directory is not under `HOME`, so that a string built from either is told apart.
    """
    home = tmp_path / HOME_PROBE / "operator"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    assert Path.home() == home
    return Probe(root=tmp_path, data_dir=tmp_path / DATA_PROBE / ".debate-research" / "dev", home=home)


@pytest.fixture
def world(
    probe: Probe, tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> World:
    """`run_record_scenarios.World`, as `test_pull_run_record_is_read_by_every_build.py` builds it,
    in the probe's data directory."""

    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    return World(
        installation=Installation(
            data_dir=probe.data_dir,
            bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            archives=build_snapshot_zips(tmp_path / "published"),
        ),
        s3_client=s3_client,
        bucket_name=evidence_bucket,
        scratch=tmp_path,
        set_clock=set_clock,
    )


@pytest.fixture
def logged(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="debate_core")
    return caplog


@dataclass
class Progress:
    """The one-line accounts a pull gives of what it starts: the CLI's `--verbose` lines."""

    lines: list[str]


def everything_left_to_paste(
    world: World, logged: pytest.LogCaptureFixture, progress: Progress
) -> dict[str, str]:
    """Every text the world's pulls left for a person to read or paste, by what it is."""
    texts: dict[str, str] = {}
    for number, pulled in enumerate(world.pulled, 1):
        run = f"run {number}"
        texts[f"{run}: the JSON summary (`caselist pull --json`, the agent's stdout)"] = json.dumps(
            pulled.summary.as_json()
        )
        if pulled.record is not None:
            texts[f"{run}: the run record"] = pulled.record.model_dump_json()
        if pulled.details is not None:
            texts[f"{run}: the run's details"] = pulled.details.model_dump_json()
    for number, stopped in enumerate(world.raised, 1):
        hint = getattr(stopped, "hint", None)
        message = str(stopped) if isinstance(stopped, DomainError) else reported_error_message(stopped)
        texts[f"stopped run {number}: the error the command reports"] = f"{message} {hint or ''}"
    data_dir = world.installation.data_dir
    for summary_file in sorted((data_dir / RUN_SUMMARY_DIRECTORY).glob("*.json")):
        texts[f"the summary file {summary_file.name}"] = summary_file.read_text(encoding="utf-8")
    for name in (SYNC_RUN_LOG_FILENAME, SYNC_RUN_DETAILS_FILENAME):
        if (data_dir / name).is_file():
            texts[f"this machine's {name}"] = (data_dir / name).read_text(encoding="utf-8")
    listed = world.s3_client.list_objects_v2(Bucket=world.bucket_name, Prefix="reports/")
    for one in listed.get("Contents", []):
        key = str(one.get("Key"))
        body = world.s3_client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read()
        texts[f"the bucket's {key}"] = body.decode("utf-8")
    notifier = MacOsNotifier(executable="osascript")
    texts["the notifications"] = "\n".join(" ".join(notifier.command_for(one)) for one in world.notifier.sent)
    texts["the log lines"] = "\n".join(
        f"{record.getMessage()} {json.dumps(extras_of(record), default=str)}" for record in logged.records
    )
    texts["the progress lines"] = "\n".join(progress.lines)
    return texts


_LOG_RECORD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}
"""What every log record carries of itself: `pathname` is the source file that logged it, not output."""


def extras_of(record: logging.LogRecord) -> dict[str, object]:
    """What the caller passed with a log line (`extra=`), which a structured log handler writes out."""
    return {key: value for key, value in vars(record).items() if key not in _LOG_RECORD_ATTRIBUTES}


def assert_names_nothing_of_this_machine(texts: dict[str, str], probe: Probe) -> None:
    named = {where: found for where, text in texts.items() if (found := probe.found_in(text))}
    assert not named, f"a path on this machine reached {json.dumps(named, indent=2)}"


async def dry_run(world: World, source: FakeSource, progress: Progress) -> None:
    """`caselist pull --dry-run`: no monitor, no record, no file."""
    service = world.installation.sync(source)
    world.pulled.append(
        await run_pull(
            lambda: service,
            [CASELIST],
            dry_run=True,
            publish_pending=False,
            monitor=lambda: pytest.fail("a dry run builds no run monitor"),
            progress=progress.lines.append,
        )
    )


async def watched_pull(world: World, source: FakeSource, progress: Progress) -> None:
    """:meth:`World.pull`, keeping the progress lines the command prints under `--verbose`."""
    monitor = SyncRunMonitor(
        state_dir=world.installation.data_dir,
        environment="dev",
        notifier=world.notifier,
        remote=world.installation.bucket,
        aws_login_command=AWS_LOGIN,
        clock=lambda: inbox_retention.RUN_CLOCK,
    )
    service = world.installation.sync(source)
    world.pulled.append(
        await run_pull(
            lambda: service,
            [CASELIST],
            dry_run=False,
            publish_pending=False,
            monitor=lambda: monitor,
            progress=progress.lines.append,
        )
    )


# ------------------------------------------------------------------------------------------------
# ac1: the dry run
# ------------------------------------------------------------------------------------------------


async def test_a_dry_run_names_the_inbox_by_its_role_and_no_path_on_this_machine(
    world: World, probe: Probe, logged: pytest.LogCaptureFixture
) -> None:
    """Two weeks and two camp files to fetch, one week already in the inbox: the download plan says
    where they would go as "the inbox", and nothing the dry run printed names a path.

    A dry run writes no summary file and no record (`v1-e34-t02` ac2), so its JSON summary is all it
    leaves; the rendered table is `debate_cli`'s test.
    """
    progress = Progress(lines=[])
    world.installation.inbox.mkdir(parents=True)
    (world.installation.inbox / inbox_retention.weekly_name(WEEK_1)).write_bytes(
        world.installation.archives[WEEK_1].read_bytes()
    )
    source = FakeSource(
        world.installation.archives,
        weeks=[WEEK_1, WEEK_2, inbox_retention.WEEK_3],
        openev=[(ESTUARY, ESTUARY_BODY), (RELEASE, RELEASE_BODY)],
    )

    await dry_run(world, source, progress)

    assert_names_nothing_of_this_machine(everything_left_to_paste(world, logged, progress), probe)
    (pulled,) = world.pulled
    download = pulled.summary.stage(SyncStage.DOWNLOAD)
    assert download is not None and download.outcome is StageOutcome.PLANNED
    assert download.reason == "would download 4 file(s) into the inbox"
    imported = pulled.summary.stage(SyncStage.IMPORT)
    assert imported is not None
    assert imported.reason == (
        "would import 4 downloaded file(s) and 1 already in the inbox, oldest first, "
        "and write their manifests"
    )
    assert pulled.summary_path is None and pulled.record is None
    assert not (probe.data_dir / RUN_SUMMARY_DIRECTORY).exists(), "a dry run writes no summary file"
    assert source.archive_fetches == [] and source.openev_fetches == []


def test_the_probe_is_in_the_data_directory_and_the_home_directory_and_nowhere_else() -> None:
    """Without this a probe could pass by looking for a string that was never there, or by finding
    one that is in every text whatever the code does."""
    root = Path("/private/var/folders/xy/T/pytest-of-someone/pytest-1/test0")
    probe = Probe(root=root, data_dir=root / DATA_PROBE / ".debate-research" / "dev", home=root / HOME_PROBE)
    assert probe.found_in(f"would download 4 file(s) into {probe.data_dir / 'inbox'}")
    assert probe.found_in(f"look under {probe.home}/Library/Logs")
    assert probe.found_in("lock held at ~/.debate-research/dev/.caselist-sync.lock")
    assert probe.found_in("could not open /Users/someone/.debate-research/dev/inbox/Maple Grove-QX.docx")
    assert not probe.found_in("would download 4 file(s) into the inbox")
    assert not probe.found_in(
        "This machine refused the manifest directory: check that this user can read and write it, "
        "under the environment's data directory (storage.data_dir). See docs/runbooks/evidence-store.md "
        "or https://files.opencaselist.example.invalid/home/testcl26-weekly-2026-09-01.zip"
    )


# ------------------------------------------------------------------------------------------------
# ac2: every other stage of a pull, and what a run leaves beside its summary
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
async def test_a_recorded_run_names_no_path_on_this_machine(
    scenario: str, world: World, probe: Probe, logged: pytest.LogCaptureFixture
) -> None:
    """Each of the runs `v1-e34-t19` records across builds, in the probe's data directory."""
    await SCENARIOS[scenario](world)

    assert world.pulled or world.raised, "the scenario ran no pull"
    assert_names_nothing_of_this_machine(everything_left_to_paste(world, logged, Progress(lines=[])), probe)


async def camp_files_fetched_imported_published_and_cleared(world: World, progress: Progress) -> None:
    """A week and two camp files, the second a release, which retention then clears from the inbox;
    the week after, a run that finds nothing new."""
    source = FakeSource(
        world.installation.archives, weeks=[WEEK_1], openev=[(ESTUARY, ESTUARY_BODY), (RELEASE, RELEASE_BODY)]
    )
    await watched_pull(world, source, progress)
    first = world.pulled[0].summary
    assert first.succeeded, first.stages
    retention = first.stage(SyncStage.RETENTION)
    assert retention is not None and retention.outcome is StageOutcome.COMPLETED, first.stages
    assert first.inbox_retention is not None and len(first.inbox_retention.removed) == 3
    world.set_clock(SECOND_RUN)
    await watched_pull(world, source, progress)
    assert world.pulled[1].summary.nothing_new, world.pulled[1].summary.stages


async def a_run_another_runs_lock_refused(world: World, progress: Progress) -> None:
    """`SyncRunInProgress`: the run did nothing, and the command prints the error's message."""
    world.installation.data_dir.mkdir(parents=True)
    with RunLock(world.installation.data_dir / LOCK_FILENAME):
        try:
            await watched_pull(world, FakeSource(world.installation.archives, weeks=[WEEK_1]), progress)
        except DomainError as refused:
            world.raised.append(refused)
    assert [type(one).__name__ for one in world.raised] == ["SyncRunInProgress"]


async def a_camp_download_the_inbox_refused(world: World, progress: Progress) -> None:
    """An `OSError` quoting the inbox path and the file's name: a failed download, named by id."""
    await watched_pull(
        world, InboxRefusingSource(world.installation.archives, openev=[(ESTUARY, ESTUARY_BODY)]), progress
    )
    download = world.pulled[0].summary.stage(SyncStage.DOWNLOAD)
    assert download is not None and download.outcome is StageOutcome.FAILED


async def a_manifest_directory_this_machine_refused(world: World, progress: Progress) -> None:
    """Week one imported; this machine will not let week two's manifest be written: the import fails
    on `STORE_ACCESS_DENIED`, with the data directory's fix as its hint."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    await watched_pull(world, source, progress)
    manifests = world.installation.data_dir / "objects" / "manifests" / CASELIST
    manifests.chmod(0o500)
    world.set_clock(SECOND_RUN)
    try:
        await watched_pull(world, FakeSource(world.installation.archives, weeks=[WEEK_1, WEEK_2]), progress)
    finally:
        manifests.chmod(0o700)
    imported = world.pulled[1].summary.stage(SyncStage.IMPORT)
    assert imported is not None and imported.outcome is StageOutcome.FAILED
    assert imported.hint is not None and "storage.data_dir" in imported.hint


MORE: dict[str, Callable[[World, Progress], Awaitable[None]]] = {
    one.__name__: one
    for one in (
        camp_files_fetched_imported_published_and_cleared,
        a_run_another_runs_lock_refused,
        a_camp_download_the_inbox_refused,
        a_manifest_directory_this_machine_refused,
    )
}


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(name, marks=needs_permissions)
        if name == "a_manifest_directory_this_machine_refused"
        else name
        for name in sorted(MORE)
    ],
)
async def test_a_run_the_recorded_scenarios_do_not_cover_names_no_path_on_this_machine(
    scenario: str, world: World, probe: Probe, logged: pytest.LogCaptureFixture
) -> None:
    """Camp files and retention, a refused lock, and two refusals by this machine."""
    progress = Progress(lines=[])

    await MORE[scenario](world, progress)

    assert_names_nothing_of_this_machine(everything_left_to_paste(world, logged, progress), probe)

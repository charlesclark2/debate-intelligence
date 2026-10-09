"""Nothing a pull writes for a person to read names a camp file by its title (`v1-e34-t12`).

A camp download sits in the inbox as `openev-<id>-<file name>`, and a camp file's name is its title
(`docs/policies/caselist-data-use.md` rule 4). The sync's docstring said a run summary never carries
one and the scheduled-sync runbook said the run log can be pasted into an issue as it is, while
`OpenEvSelection.as_json()` carried `inbox_name`, and an import that refused a camp download quoted
the archive reader's message, which names the file it could not read.

Each test here pulls one camp file whose upstream path, file name and so its inbox name carry
:data:`PROBE`, through :func:`run_pull` and a real :class:`SyncRunMonitor`, and then looks for the
probe in everything the run left for a person: the JSON summary (what `caselist pull --json` and the
launchd agent's stdout print), the run-summary file, the run record in the local log and in the
bucket, the text of every notification as the macOS notifier would post it, and the log lines. The
CLI's own rendering is checked in `debate_cli`'s `test_caselist_pull.py`.

Everything is real except the OpenCaselist source, as in `test_inbox_retention.py`, whose
installation this borrows. Every expected value is written by hand from the fixture (working
agreement 6): an id, a decision, and a digest prefix read off the bytes the test serves.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES as CAMP_BODIES

from debate_core.application.caselist_sync import (
    RUN_SUMMARY_SCHEMA_VERSION,
    PulledRun,
    StageOutcome,
    SyncStage,
    run_pull,
)
from debate_core.application.ports.caselist_source import OpenEvFile, openev_inbox_name
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.application.sync_runs import SYNC_RUN_LOG_FILENAME, SyncRunMonitor
from debate_core.integrations.local.macos_notifier import MacOsNotifier

from .test_inbox_retention import (
    CASELIST,
    FakeSource,
    Installation,
    installation,  # noqa: F401  # pyright: ignore[reportUnusedImport] - a fixture, used by name
    sha256_label,
)

pytestmark = pytest.mark.anyio

PROBE = "Zqxprobe"
"""In the camp's folder, the file's title and so its inbox name. Searched for case-insensitively."""

PROBED = OpenEvFile(
    openev_id=512,
    path=f"openev/2026/{PROBE} Institute/{PROBE} Estuary Solvency Advocate.docx",
    filename=f"{PROBE} Estuary Solvency Advocate.docx",
    year=2026,
    tags=("policy",),
)
PROBED_BODY = CAMP_BODIES["estuary-solvency"]

REVISION = PROBED.model_copy(update={"openev_id": 640})
"""The same file uploaded again: OpenEv deletes 512 and lists 640 at its path (`v1-e34-t08`)."""
REVISION_BODY = CAMP_BODIES["canal-counterplan-revised"]

BROKEN = OpenEvFile(
    openev_id=777,
    path=f"openev/2026/{PROBE} Institute/{PROBE} Camp Release.zip",
    filename=f"{PROBE} Camp Release.zip",
    year=2026,
    tags=("policy",),
)
BROKEN_BODY = b"PK\x03\x04 an invented camp release, cut short: not a zip any reader can open"
"""A camp release the archive reader refuses, which names the file it could not read."""

AWS_LOGIN = "aws sso login --profile debate-dev-evidence"


def test_the_probe_is_in_every_name_the_camp_file_goes_by() -> None:
    """Without this the tests below could pass by searching for a string that was never there."""
    for file in (PROBED, REVISION, BROKEN):
        assert PROBE in file.path
        assert PROBE in openev_inbox_name(file)


@dataclass
class Watched:
    """One monitored pull and the notifier it reported to."""

    pulled: PulledRun
    notifier: RecordingNotifier


async def pull(installation: Installation, source: FakeSource, *, dry_run: bool = False) -> Watched:
    """`caselist pull` as the command runs it: `run_pull` inside a real run monitor."""
    notifier = RecordingNotifier()
    monitor = SyncRunMonitor(
        state_dir=installation.data_dir,
        environment="dev",
        notifier=notifier,
        remote=installation.bucket,
        aws_login_command=AWS_LOGIN,
    )
    service = installation.sync(source)
    pulled = await run_pull(
        lambda: service,
        [CASELIST],
        dry_run=dry_run,
        publish_pending=False,
        monitor=lambda: monitor,
        progress=lambda _: None,
    )
    return Watched(pulled=pulled, notifier=notifier)


async def pasteable(
    installation: Installation, watched: Watched, logged: pytest.LogCaptureFixture
) -> dict[str, str]:
    """Everything this run left that a person may read or paste, by what it is."""
    pulled = watched.pulled
    texts = {
        "the JSON summary (`caselist pull --json`, the agent's stdout)": json.dumps(pulled.summary.as_json()),
        "the log lines": "\n".join(
            f"{record.getMessage()} {json.dumps(vars(record), default=str)}" for record in logged.records
        ),
    }
    if pulled.summary_path is not None:
        texts["the run-summary file"] = pulled.summary_path.read_text(encoding="utf-8")
    if pulled.record is not None:
        texts["the run record"] = pulled.record.model_dump_json()
        texts["the run log"] = (installation.data_dir / SYNC_RUN_LOG_FILENAME).read_text(encoding="utf-8")
        copy = installation.data_dir.parent / "bucket-copy.json"
        await installation.bucket.get_file(pulled.record.object_key, copy)
        texts["the bucket's copy of the run record"] = copy.read_text(encoding="utf-8")
    notifier = MacOsNotifier(executable="osascript")
    texts["the notifications"] = "\n".join(
        " ".join(notifier.command_for(one)) for one in watched.notifier.sent
    )
    return texts


def assert_no_probe(texts: dict[str, str]) -> None:
    named = sorted(where for where, text in texts.items() if PROBE.casefold() in text.casefold())
    assert not named, f"a camp file's title reached {named}"


def openev_selections(watched: Watched) -> list[dict[str, object]]:
    selections = watched.pulled.summary.as_json()["openev_selections"]
    assert isinstance(selections, list)
    return selections  # pyright: ignore[reportUnknownVariableType]


def reason(watched: Watched, stage: SyncStage) -> str:
    record = watched.pulled.summary.stage(stage)
    assert record is not None and record.reason is not None, watched.pulled.summary.stages
    return record.reason


@pytest.fixture
def logged(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="debate_core")
    return caplog


# ------------------------------------------------------------------------------------------------
# ac1: selected, downloaded, imported, revised: named by id, never by title
# ------------------------------------------------------------------------------------------------


async def test_a_pull_that_fetches_and_imports_a_camp_file_names_it_by_id_and_digest_alone(
    installation: Installation, logged: pytest.LogCaptureFixture
) -> None:
    """A dry run selects it, a run downloads, imports, publishes and confirms it, and it leaves the
    inbox. Every summary names it as `openev-512` and the start of its SHA-256."""
    source = FakeSource(installation.archives, openev=[(PROBED, PROBED_BODY)])

    dry = await pull(installation, source, dry_run=True)

    assert_no_probe(await pasteable(installation, dry, logged))
    assert openev_selections(dry) == [
        {
            "openev_id": 512,
            "inbox_file": None,
            "year": 2026,
            "event": "POLICY",
            "decision": "download",
            "note": None,
            "revision_of": None,
        }
    ]

    run = await pull(installation, source)

    assert run.pulled.summary.succeeded, run.pulled.summary.stages
    assert source.openev_fetches == [512]
    assert run.pulled.summary.snapshots_imported == ("openev 2026-policy",)
    assert_no_probe(await pasteable(installation, run, logged))
    assert openev_selections(run) == [
        {
            "openev_id": 512,
            "inbox_file": sha256_label(PROBED_BODY),
            "year": 2026,
            "event": "POLICY",
            "decision": "download",
            "note": None,
            "revision_of": None,
        }
    ]
    assert run.pulled.summary_path is not None
    written = json.loads(run.pulled.summary_path.read_text(encoding="utf-8"))
    assert written["schema_version"] == 3
    assert written["openev_selections"] == openev_selections(run)


async def test_a_pull_that_fetches_a_revision_names_both_versions_by_id_alone(
    installation: Installation, logged: pytest.LogCaptureFixture
) -> None:
    """512 is pulled; upstream deletes it and lists 640 at its path, and the next pull fetches 640 as
    its revision. The select stage names the two by id; nothing names either by title."""
    source = FakeSource(installation.archives, openev=[(PROBED, PROBED_BODY)])
    first = await pull(installation, source)
    assert first.pulled.summary.succeeded, first.pulled.summary.stages
    source.openev = [(REVISION, REVISION_BODY)]

    revised = await pull(installation, source)

    assert revised.pulled.summary.succeeded, revised.pulled.summary.stages
    assert source.openev_fetches == [512, 640]
    assert_no_probe(await pasteable(installation, revised, logged))
    assert openev_selections(revised) == [
        {
            "openev_id": 640,
            "inbox_file": sha256_label(REVISION_BODY),
            "year": 2026,
            "event": "POLICY",
            "decision": "download",
            "note": None,
            "revision_of": 512,
        }
    ]
    assert reason(revised, SyncStage.SELECT).endswith(
        "; 1 taken as a revision of an id no longer listed (openev-512 -> openev-640)"
    )


async def test_a_camp_download_whose_import_is_refused_is_named_by_id_and_digest_alone(
    installation: Installation, logged: pytest.LogCaptureFixture
) -> None:
    """The archive reader refuses a camp release, and its message names the file it could not read.

    The import stage's reason, the run record built from it, the failure notification and the next
    run, which finds the download in the inbox and is refused the same way, name it `openev-777` and
    its digest prefix.
    """
    source = FakeSource(installation.archives, openev=[(BROKEN, BROKEN_BODY)])
    refused = (
        f"0 imported; 1 refused: openev-777 ({sha256_label(BROKEN_BODY)}): "
        "the download cannot be read as an archive: not a readable zip file"
    )

    first = await pull(installation, source)

    assert not first.pulled.summary.succeeded
    assert_no_probe(await pasteable(installation, first, logged))
    import_stage = first.pulled.summary.stage(SyncStage.IMPORT)
    assert import_stage is not None and import_stage.outcome is StageOutcome.FAILED
    assert import_stage.reason == refused
    assert [one.title for one in first.notifier.sent] == ["caselist pull failed"]

    again = await pull(installation, source)

    assert source.openev_fetches == [777], "an inbox copy was fetched again"
    assert_no_probe(await pasteable(installation, again, logged))
    assert [(one["openev_id"], one["inbox_file"], one["decision"]) for one in openev_selections(again)] == [
        (777, sha256_label(BROKEN_BODY), "already_in_inbox")
    ]
    assert reason(again, SyncStage.IMPORT) == refused


def test_the_summary_schema_is_version_3_because_a_key_was_removed() -> None:
    """`inbox_name` left the summary: not an additive change under `v1-e34-t07`'s rule."""
    assert RUN_SUMMARY_SCHEMA_VERSION == 3

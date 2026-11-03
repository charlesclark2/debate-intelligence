"""A stage's reason names an error this project did not write by its class and errno, never its text.

`v1-e34-t26`, item 4, from `v1-e29-t09`'s Follow-up 3. `CaselistSyncService._failure` is how every
stage words a failure that does not stop the run. For an error that is not a `DomainError` it used
the class alone, where the publisher's result used `reported_error_message`, the class and the
errno: one `OSError` read two ways in one summary. And an `OSError`'s own text is never safe to
quote, because it ends with the path it failed on, which holds the home directory and, under the
inbox or the parsed store, a camp file's title.

`v1-e34-t23` (its Decision 2) changed `_failure` to `reported_error_message` already, with this
task's spec still to be filed. This file is the test the spec asks for. It was shown failing by
putting each of the two wordings it rules out back into `_failure`; the session report gives those
runs.

The stage here is the parse stage, the one that catches anything at all, because a caselist's parse
raising is the plainest way for an arbitrary error to reach `_failure`. Every expectation is written
by hand.
"""

from __future__ import annotations

import errno
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist_sync import (
    ParsedCaselist,
    PublishedParsedStore,
    SyncStage,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_inbox_retention import WEEK_1, FakeSource, Installation
from .test_pull_stage_failure_codes import assert_names_nothing_of_this_machine, pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

A_CAMP_FILES_TITLE = "Bayview Camp Aff - Lab Leak.docx"
NOTHING_PARSED = (
    "0 caselist(s) parsed: 0 source(s) attempted, 0 skipped as parsed already, 0 unsupported, "
    "0 failed, 0 card(s); 0 object(s) of the parsed store uploaded"
)
NOT_PUBLISHED = "the parsed store of testcl26 is not published"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )


class ParseRaises:
    """A parse stage whose every caselist raises `error`."""

    def __init__(self, error: BaseException) -> None:
        self.error = error

    async def parse_new_sources(self, caselist: str) -> ParsedCaselist:
        raise self.error

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:
        raise AssertionError("nothing was parsed, so nothing is published")


def under_the_parsed_store(installation: Installation) -> str:
    """Where an `OSError` from the parse would say it failed: a camp file's title under this machine's
    data directory."""
    return str(installation.data_dir / "parsed" / "testcl26" / A_CAMP_FILES_TITLE)


async def parse_reason_when_it_raises(installation: Installation, error: BaseException) -> str:
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    watched = await pull(installation, installation.sync(source, parse=ParseRaises(error)))
    parsed = stage(watched.summary, SyncStage.PARSE)
    assert parsed["outcome"] == "failed"
    assert_names_nothing_of_this_machine(watched.summary, installation)
    for notification in watched.notifier.sent:
        assert A_CAMP_FILES_TITLE not in notification.text
        assert str(installation.data_dir) not in notification.text
    return str(parsed["reason"])


async def test_a_permission_error_is_named_by_its_class_and_errno(installation: Installation) -> None:
    error = PermissionError(errno.EACCES, "Permission denied", under_the_parsed_store(installation))

    reason = await parse_reason_when_it_raises(installation, error)

    assert reason == f"{NOTHING_PARSED}; testcl26: PermissionError (errno 13); {NOT_PUBLISHED}"
    assert "Permission denied" not in reason
    assert A_CAMP_FILES_TITLE not in reason


async def test_a_missing_file_is_named_by_its_class_and_errno(installation: Installation) -> None:
    error = FileNotFoundError(errno.ENOENT, "No such file or directory", under_the_parsed_store(installation))

    reason = await parse_reason_when_it_raises(installation, error)

    assert reason == f"{NOTHING_PARSED}; testcl26: FileNotFoundError (errno 2); {NOT_PUBLISHED}"
    assert "No such file" not in reason


async def test_an_os_error_with_no_errno_is_named_by_its_class_alone(installation: Installation) -> None:
    error = OSError(f"could not open {under_the_parsed_store(installation)}")

    reason = await parse_reason_when_it_raises(installation, error)

    assert reason == f"{NOTHING_PARSED}; testcl26: OSError; {NOT_PUBLISHED}"
    assert "could not open" not in reason


async def test_an_error_nobody_modelled_is_named_by_its_class_alone(installation: Installation) -> None:
    error = RuntimeError(f"unexpected state at {under_the_parsed_store(installation)}")

    reason = await parse_reason_when_it_raises(installation, error)

    assert reason == f"{NOTHING_PARSED}; testcl26: RuntimeError; {NOT_PUBLISHED}"
    assert "unexpected state" not in reason

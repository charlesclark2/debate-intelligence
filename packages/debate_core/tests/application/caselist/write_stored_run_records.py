"""Writes `stored_run_records/written_by_the_start_commit/`: what a build before `v1-e34-t19` wrote.

Not collected: its name is not a test module's, and it is only ever run by its path, against the
source of the commit on `dev` this task started from (`0a9c1e6`), so that what it stores was
written by that build's code and not by this one's. `stored_run_records/README.md` gives the
command.

For each scenario in `run_record_scenarios.py` it keeps two things, byte for byte: the run log the
build left on this machine, and every object it put under the bucket prefix records live under.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application import errors
from debate_core.integrations.s3 import S3EvidenceObjectStore

THE_ADAPTERS_FIX_FOR_A_PROFILE_NOT_DEFINED = (
    "set storage.s3.aws_profile to a profile this machine's AWS config defines, or add the profile to "
    "it: docs/runbooks/evidence-store.md lists the evidence profiles and how they are added. It is "
    "not an expired session, and logging in changes nothing"
)
"""The hint this build's S3 adapter writes for a profile the AWS config lacks, copied out by hand."""


class StoreProfileNotConfigured(errors.StoreError):
    """`v1-e29-t07`'s error, for a source that does not have it: the start commit's.

    Named and worded as this build's is, by hand, because the run record keeps an error's class
    name and its message, and `a_refusal_to_start_published_by_the_next_run` hands the start
    commit's run monitor this error to record (`v1-e34-t22`). If the copy and this build's class
    ever part ways, the test that compares the two builds' records for that scenario fails.
    """

    def __init__(self, profile: str | None, *, setting: str | None = None, hint: str | None = None) -> None:
        self.profile, self.setting, self.hint = profile, setting, hint
        named = f"AWS profile {profile!r}" if profile else "the AWS profile"
        named_by = f", named by {setting}," if setting else ""
        Exception.__init__(
            self,
            f"{named}{named_by} is not defined in this machine's AWS config" + (f": {hint}" if hint else ""),
        )


def the_refusal_written_out() -> Exception:
    """The refusal `run_record_scenarios.the_adapters_refusal_of_a_session` builds, for a source
    whose adapter cannot build it."""
    return StoreProfileNotConfigured(
        MISSPELT_PROFILE, setting=PROFILE_SETTING, hint=THE_ADAPTERS_FIX_FOR_A_PROFILE_NOT_DEFINED
    )


THE_SOURCE_LACKS_THE_ERROR = not hasattr(errors, "StoreProfileNotConfigured")
if THE_SOURCE_LACKS_THE_ERROR:
    # `v1-e29-t07` added this error after the start commit, and a test module the scenarios borrow
    # their installation from imports it by name and builds one for a test of its own. The start
    # commit's source never looks for it: the name is supplied so that those modules import, and
    # nothing of that source is changed on disk.
    errors.StoreProfileNotConfigured = StoreProfileNotConfigured  # type: ignore[attr-defined]

from . import test_inbox_retention as inbox_retention  # noqa: E402
from .run_record_scenarios import (  # noqa: E402
    MISSPELT_PROFILE,
    PROFILE_SETTING,
    SCENARIOS,
    World,
    stored_bucket_text,
    the_adapters_refusal_of_a_session,
)
from .test_inbox_retention import Installation  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STORED = Path(__file__).parent / "stored_run_records" / "written_by_the_start_commit"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_write_what_this_source_writes(
    name: str, tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert os.environ.get("WRITE_STORED_RUN_RECORDS") == "from-the-start-commit", (
        "this rewrites the stored records; see stored_run_records/README.md"
    )

    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    world = World(
        installation=Installation(
            data_dir=tmp_path / "evidence",
            bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            archives=build_snapshot_zips(tmp_path / "published"),
        ),
        s3_client=s3_client,
        bucket_name=evidence_bucket,
        scratch=tmp_path,
        set_clock=set_clock,
        # The one thing a scenario needs that this source may not have. A source that has the
        # error is given its own adapter's; the start commit's is given the copy above.
        profile_not_defined=(
            the_refusal_written_out if THE_SOURCE_LACKS_THE_ERROR else the_adapters_refusal_of_a_session
        ),
    )

    await SCENARIOS[name](world)

    STORED.mkdir(parents=True, exist_ok=True)
    (STORED / f"{name}.run-log.jsonl").write_bytes(world.run_log())
    (STORED / f"{name}.bucket.json").write_text(
        stored_bucket_text(world.records_in_the_bucket()), encoding="utf-8"
    )

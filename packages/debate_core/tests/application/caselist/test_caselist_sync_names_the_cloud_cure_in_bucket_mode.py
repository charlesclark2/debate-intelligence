"""A bucket-mode parse stage names the cloud cure, never a publish from the operator's Mac (`v1-e40-t18`).

`v1-e34-t31` has a bucket-mode run name `caselist parse --caselist <slug> --publish` for every
caselist whose parsed store it did not publish complete. Run on the operator's Mac, that command
rebuilds the Mac's own, older working copy and publishes it over the parsed store the cloud run
owns. Now a bucket-mode run names the cloud cure instead, in the stage's fix text (its hint, or its
reason when pending), in the failed-stage banner, in the login banner and in what the run records:
the next cloud run that imports into the caselist, weekly or started by hand, publishes it. The run
parses only the caselists it imports into, so that is the cure, and `caselist-cloud-run.md`'s "A
failed parse stage" says so. Local mode keeps `v1-e34-t31`'s command for each caselist.

Bucket mode is told two ways, each from what is already known: the pull from the composition root
(`bucket_mode`, the container's `_in_bucket_mode`), and the banners from what the run records, its
details' `bucket_run`, which every bucket-mode run writes (`v1-e40-t04`). Here the bracket around
the pull is a stand-in that says what a bucket-mode bracket says of the lock; the real one is in
`packages/debate_cli/tests/bucket_mode/test_bucket_mode_parse_fix_names_the_cloud_run.py`.

The run is the real one inside the real run monitor, against moto, with `v1-e34-t31`'s scripted
parse stage. Every expected sentence is written out by hand.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jsonschema
import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist.suppression import LocalFallbackSuppressionList
from debate_core.application.caselist_sync import CaselistSyncService, SyncStage, run_pull
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    BucketRunDetails,
    SyncRunDetails,
    SyncRunMonitor,
    SyncRunRecord,
    notifications_for,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.suppression import empty_suppression_list

from .retry_rule import the_commands_retry_rule
from .test_caselist_sync_names_publish_only_per_caselist import (
    OPENEV,
    PUBLISH_ONLY_THE_WEEKLY,
    REBUILD_OPENEV,
    BucketCopy,
    ScriptedParse,
    bucket_objects,
    details_line,
    login_notification,
    owed,
    parse_notification,
    stored_schema,
)
from .test_inbox_retention import CASELIST, ESTUARY, ESTUARY_BODY, WEEK_1, FakeSource, Installation
from .test_pull_stage_failure_codes import AWS_LOGIN, Watched, outage, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPO_ROOT: Final = Path(__file__).resolve().parents[5]
CLOUD_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"

THE_WEEKLYS_CURE: Final = (
    f"the next cloud run that imports into {CASELIST} publishes that caselist's parsed store: the weekly "
    'run, or one started by hand (caselist-cloud-run.md, "A failed parse stage"); never a publish from '
    "the operator's Mac"
)
"""The banner's fix for the weekly caselist's parsed store, in bucket mode."""

THE_WEEKLYS_HINT: Final = (
    f"The cloud run publishes the parsed store of {CASELIST}, never the operator's Mac, whose working "
    "copy is not the one the cloud run owns: the next weekly run that imports into a caselist rebuilds "
    "its parsed store and publishes it, and so does a run started by hand that imports into it "
    '(caselist-cloud-run.md, "A failed parse stage").'
)
"""The stage's fix text for the same, in bucket mode."""

BOTH_CURE: Final = (
    f"the next cloud run that imports into {CASELIST} or openev publishes that caselist's parsed store: "
    'the weekly run, or one started by hand (caselist-cloud-run.md, "A failed parse stage"); never a '
    "publish from the operator's Mac"
)
BOTH_HINT: Final = (
    f"The cloud run publishes the parsed store of {CASELIST} and openev, never the operator's Mac, whose "
    "working copy is not the one the cloud run owns: the next weekly run that imports into a caselist "
    "rebuilds its parsed store and publishes it, and so does a run started by hand that imports into "
    'it (caselist-cloud-run.md, "A failed parse stage").'
)

CURE_THAT_NAMES_NO_CASELIST: Final = (
    "the next cloud run that imports into a caselist the parse stage names publishes that caselist's "
    'parsed store: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed parse '
    "stage\"); never a publish from the operator's Mac"
)
"""For bucket-mode details that name no caselist: what a build before `v1-e34-t31` wrote."""

NO_MAC_SIDE_PUBLISH: Final = ("--publish", "caselist parse")
"""Neither a publish flag nor the command that takes one may be in a bucket-mode parse cure."""


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


class BucketModeBracket:
    """What a bucket-mode :class:`~debate_core.application.caselist_sync.PullBracket` says of the run.

    The lock and the restore are the real bracket's, tested where it is built; here the run only
    needs what its details record of them, as every bucket-mode run's do.
    """

    bucket_mode = True

    def watching(self, task: asyncio.Task[object]) -> None:
        return None

    async def start(self, caselists: Sequence[str], *, dry_run: bool, restore_parsed: bool = True) -> None:
        return None

    async def after_run(self) -> None:
        return None

    async def finish(self) -> None:
        return None

    def details(self) -> BucketRunDetails | None:
        return BucketRunDetails(bundle="saved")

    def as_terminated(self, cancelled: asyncio.CancelledError) -> BaseException:  # pragma: no cover
        return cancelled


async def run(
    installation: Installation,
    *,
    bucket_mode: bool,
    with_a_camp_file: bool = False,
    **scripted: Any,
) -> Watched:
    """One weekly pull of week one, in bucket mode as the composition root builds it, or in local mode."""
    bucket_copy = BucketCopy()
    listed = LocalFallbackSuppressionList(bucket_copy, local=empty_suppression_list())
    installation.suppression = listed
    service = installation.sync(
        FakeSource(
            installation.archives,
            weeks=[WEEK_1],
            openev=[(ESTUARY, ESTUARY_BODY)] if with_a_camp_file else [],
        ),
        parse=ScriptedParse(listed, bucket_copy, **scripted),
        working_copy_outlives_the_run=not bucket_mode,
        bucket_mode=bucket_mode,
    )
    return await pull(installation, service, bracket=BucketModeBracket() if bucket_mode else None)


async def pull(installation: Installation, service: CaselistSyncService, *, bracket: Any) -> Watched:
    """`caselist pull` as the command runs it: `run_pull` inside a real run monitor, with its bracket."""
    notifier = RecordingNotifier()
    monitor = SyncRunMonitor(
        state_dir=installation.data_dir,
        environment="dev",
        notifier=notifier,
        remote=installation.bucket,
        aws_login_command=AWS_LOGIN,
        **the_commands_retry_rule(),
    )
    pulled = await run_pull(
        lambda: service,
        [CASELIST],
        dry_run=False,
        publish_pending=False,
        monitor=lambda: monitor,
        progress=lambda _: None,
        bracket=bracket,
    )
    return Watched(pulled=pulled, notifier=notifier)


def names_no_mac_side_publish(text: str) -> bool:
    return not any(word in text for word in NO_MAC_SIDE_PUBLISH)


def record_line(installation: Installation) -> dict[str, Any]:
    [line] = (installation.data_dir / SYNC_RUN_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    return json.loads(line)


# ------------------------------------------------------------------------------------------------
# Bucket mode: the fix text, the banner and the record name the cloud cure
# ------------------------------------------------------------------------------------------------


async def test_a_bucket_mode_run_whose_parsed_publish_failed_names_the_cloud_cure_and_no_mac_side_publish(
    installation: Installation,
) -> None:
    """The bucket did not answer for the parsed store, after a rebuild that read every copy of the list."""
    watched = await run(installation, bucket_mode=True, refused={CASELIST: outage()})

    found = stage(watched.summary, SyncStage.PARSE)
    assert (found["outcome"], found["error_codes"]) == ("failed", ["STORE_UNAVAILABLE"])
    assert found["hint"] == THE_WEEKLYS_HINT
    assert names_no_mac_side_publish(str(found["reason"]))
    banner = parse_notification(watched)
    assert banner.fix_command == THE_WEEKLYS_CURE
    assert banner.hint == THE_WEEKLYS_HINT
    assert names_no_mac_side_publish(banner.text)

    details = details_line(installation)
    assert details["bucket_run"] is not None, "the premise: the run records that it was a bucket-mode run"
    assert details["parsed_stores_owed"] == [{"caselist": CASELIST, "publish_only": False}]
    [parse_details] = [one for one in details["stages"] if one["stage"] == "parse"]
    assert parse_details["hint"] == THE_WEEKLYS_HINT
    [parse_entry] = [one for one in record_line(installation)["stages"] if one["stage"] == "parse"]
    assert parse_entry["outcome"] == "failed"
    assert names_no_mac_side_publish(parse_entry["reason"])


async def test_a_bucket_mode_run_owing_two_parsed_stores_names_both_and_no_mac_side_publish(
    installation: Installation,
) -> None:
    """The weekly's publish refused; the camp file's rebuild read the run's own copy of the list alone.
    In local mode these are `--publish-only` and `--publish`; in bucket mode both are the cloud's."""
    watched = await run(
        installation,
        bucket_mode=True,
        with_a_camp_file=True,
        refused={CASELIST: outage()},
        local_list_only=[OPENEV],
    )

    assert owed(watched) == [(CASELIST, False), (OPENEV, False)]
    found = stage(watched.summary, SyncStage.PARSE)
    assert found["outcome"] == "failed"
    assert found["hint"] == BOTH_HINT
    banner = parse_notification(watched)
    assert banner.fix_command == BOTH_CURE
    assert names_no_mac_side_publish(banner.text)


async def test_a_bucket_mode_parse_stage_waiting_for_a_login_names_the_cloud_cure(
    installation: Installation,
) -> None:
    """The bucket's copy of the list needed a login during the rebuild: a pending stage, and the login
    banner's sentence on the parsed store names the cloud cure, not a command to run after the login."""
    watched = await run(installation, bucket_mode=True, local_list_only=[CASELIST])

    found = stage(watched.summary, SyncStage.PARSE)
    assert found["outcome"] == "pending"
    assert (
        f"the parsed store of {CASELIST} is not published, for want of an AWS login (the suppression "
        f"list's bucket copy needed an AWS login): {THE_WEEKLYS_HINT.removesuffix('.')}; "
    ) in str(found["reason"]), "the hint, its full stop given to the next sentence's semicolon (`v1-e40-t22`)"
    assert names_no_mac_side_publish(str(found["reason"]))
    message = login_notification(watched).message
    assert message.endswith(f" The parsed store waits too: {THE_WEEKLYS_CURE}.")
    assert names_no_mac_side_publish(message)


def notified(record: SyncRunRecord, details: SyncRunDetails, *, credentials_expired: bool) -> list[Any]:
    return notifications_for(
        record, details, aws_login_command=AWS_LOGIN, credentials_expired=credentials_expired
    )


async def test_bucket_mode_details_that_name_no_caselist_name_the_cloud_cure(
    installation: Installation,
) -> None:
    """Details with `bucket_run` and no `parsed_stores_owed`: what the cloud image before `v1-e34-t31`
    (`v1.1.0-dev.164`) writes. What cannot be told in bucket mode is still the cloud's to cure."""
    watched = await run(installation, bucket_mode=True, refused={CASELIST: outage()})
    record, details = watched.pulled.record, watched.pulled.details
    assert record is not None and details is not None
    written = json.loads(details.model_dump_json())
    del written["parsed_stores_owed"]

    [failed] = notified(record, SyncRunDetails.model_validate(written), credentials_expired=False)

    assert failed.fix_command == CURE_THAT_NAMES_NO_CASELIST


# ------------------------------------------------------------------------------------------------
# Local mode: unchanged
# ------------------------------------------------------------------------------------------------


async def test_a_local_mode_run_still_names_each_caselist_its_own_command(installation: Installation) -> None:
    """The same run as the bucket-mode one above, on the operator's Mac: `v1-e34-t31`'s commands."""
    watched = await run(
        installation,
        bucket_mode=False,
        with_a_camp_file=True,
        refused={CASELIST: outage()},
        local_list_only=[OPENEV],
    )

    assert details_line(installation)["bucket_run"] is None, "the premise: a local-mode run"
    assert owed(watched) == [(CASELIST, True), (OPENEV, False)]
    banner = parse_notification(watched)
    assert banner.fix_command == f"{PUBLISH_ONLY_THE_WEEKLY}; {REBUILD_OPENEV}"
    assert "cloud" not in banner.text


async def test_local_mode_details_that_name_no_caselist_still_name_the_generic_command(
    installation: Installation,
) -> None:
    watched = await run(installation, bucket_mode=False, refused={CASELIST: outage()})
    record, details = watched.pulled.record, watched.pulled.details
    assert record is not None and details is not None
    written = json.loads(details.model_dump_json())
    del written["parsed_stores_owed"]

    [failed] = notified(record, SyncRunDetails.model_validate(written), credentials_expired=False)

    assert failed.fix_command == "debate-research caselist parse --caselist <slug> --publish"


# ------------------------------------------------------------------------------------------------
# The runbook section the run names is there, and says what the run says
# ------------------------------------------------------------------------------------------------


def test_the_runbook_section_the_run_names_says_what_the_run_now_says() -> None:
    text = CLOUD_RUNBOOK.read_text(encoding="utf-8")
    assert "\n## A failed parse stage\n" in text, "the section the cure names"
    section = " ".join(text.split("\n## A failed parse stage\n", 1)[1].split("\n## ", 1)[0].split())

    assert "the next weekly run that imports into a caselist rebuilds its parsed store" in section
    assert "a run started by hand that imports into it" in section
    assert "Never run `caselist parse --caselist <slug> --publish` on the operator's Mac" in section
    assert "#step-8--the-seed-bucket-mode-and-one-run-by-hand-at-the-cutover-after-v1-e40-t04" in section
    assert (
        "\n## Step 8 — The seed, bucket mode, and one run by hand (at the cutover, after `v1-e40-t04`)\n"
        in text
    )


# ------------------------------------------------------------------------------------------------
# The earlier builds read every record and every details line this build writes in bucket mode
# ------------------------------------------------------------------------------------------------


async def test_the_earlier_builds_read_every_bucket_mode_record_and_details_line_this_build_writes(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Against what those builds validate with, each printed by its own code (`stored_run_records/`).

    The record's schema is the cloud image's, `v1.1.0-dev.164`, and `v1-e34-t19`'s start commit's:
    each forbids a key it does not define. The details' is `v1.1.0-dev.155`'s and `v1.1.0-dev.164`'s,
    byte for byte the same file.
    """
    watched = await run(
        installation,
        bucket_mode=True,
        with_a_camp_file=True,
        refused={CASELIST: outage()},
        local_list_only=[OPENEV],
    )
    assert len(watched.summary.parsed_stores_owed) == 2, "the premise: both caselists are owed"
    details_schema = stored_schema("details_schema_before_parsed_stores_owed.json")

    record = record_line(installation)
    details = details_line(installation)
    assert bucket_objects(s3_client, evidence_bucket, "reports/sync-runs/") == [record]
    assert bucket_objects(s3_client, evidence_bucket, "reports/sync-run-details/") == [details]
    for name in ("record_schema_of_the_cloud_image.json", "record_schema_of_the_start_commit.json"):
        jsonschema.validate(record, stored_schema(name))
    jsonschema.validate(details, details_schema)
    assert all(set(one) == {"stage", "outcome", "reason"} for one in record["stages"])
    assert set(details) - set(details_schema["properties"]) == {"parsed_stores_owed"}, (
        "no key but `v1-e34-t31`'s that the earlier builds pass over"
    )


def test_the_cloud_images_record_schema_refuses_a_key_it_does_not_define() -> None:
    """The check above can fail: the cloud image refuses a record with a stage key it does not define."""
    schema = stored_schema("record_schema_of_the_cloud_image.json")
    stage_entry = {"stage": "parse", "outcome": "failed", "reason": "1 caselist(s) parsed"}
    jsonschema.validate(stage_entry, {**schema["$defs"]["StageEntry"], "$defs": schema["$defs"]})

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**stage_entry, "cure": "cloud"}, {**schema["$defs"]["StageEntry"], "$defs": schema["$defs"]}
        )

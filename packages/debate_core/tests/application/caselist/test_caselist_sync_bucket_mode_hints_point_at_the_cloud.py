"""In bucket mode the login banner and the parse stage's other hints point at the cloud run (`v1-e40-t22`).

`v1-e40-t18` made a failed parse stage name the cloud cure in bucket mode. Three hints there still
pointed at the operator's Mac:

* **The login banner's fix**, `aws sso login && debate-research caselist pull --publish-pending`,
  publishes snapshots from wherever it is run. A cloud run's AWS session is its task role's, so the
  banner now says the role is the PM's to look into, and that nothing is published from the Mac. Its
  message names no command either: the report stage's check cut short and an index that waits are
  said without `--publish-pending` or `tub index publish`.
* **The failure-rate hint** named `caselist parse --caselist <slug> --failures`, which lists the
  Mac's own parsed store's failures, not the cloud run's. It now names the failures file the cloud
  run publishes with the caselist's parsed store, and says why they failed is the PM's.
* **The newer-fingerprint hint** said "install that build for the weekly agent". The weekly run is
  the cloud task's image now, so it names a new image, through the runbook.

Bucket mode is decided as `v1-e40-t18` decides it: the service's `bucket_mode` from the composition
root, and the details' `bucket_run` for the banners. Local mode keeps every word, and every record
and details line this build writes is one the cloud image (`v1.1.0-dev.164`) and the Mac's installed
build (`v1.1.0-dev.200`) read. Every expected sentence is written out by hand.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jsonschema
import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist.occurrence_table_guard import THE_BUCKET, NewerFingerprintTable
from debate_core.application.caselist.suppression import LocalFallbackSuppressionList
from debate_core.application.caselist_sync import ParsedCaselist, SyncStage
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.application.sync_runs import (
    BucketRunDetails,
    SearchIndexCounts,
    SyncRunDetails,
    SyncRunMonitor,
    SyncRunRecord,
    notifications_for,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.suppression import empty_suppression_list

from .retry_rule import the_commands_retry_rule
from .test_caselist_sync_names_publish_only_per_caselist import (
    BucketCopy,
    ScriptedParse,
    bucket_objects,
    details_line,
    login_notification,
    parse_notification,
    stored_schema,
)
from .test_caselist_sync_names_the_cloud_cure_in_bucket_mode import (
    BucketModeBracket,
    pull,
    record_line,
)
from .test_inbox_retention import CASELIST, WEEK_1, FakeSource, Installation
from .test_pull_stage_failure_codes import AWS_LOGIN, Watched, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPO_ROOT: Final = Path(__file__).resolve().parents[5]
CLOUD_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"

VERSION: Final = "2026.10.20-docx-6"
BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
INDEX_ID: Final = "20260916T061500Z-synthetic"

# ------------------------------------------------------------------------------------------------
# What each hint says, by hand
# ------------------------------------------------------------------------------------------------

THE_LOGIN_BANNERS_CLOUD_FIX: Final = (
    "the PM looks into the cloud run's task role, which gave the run no AWS session "
    '(caselist-cloud-run.md, "A run that found no AWS session"); never a login and a publish from the '
    "operator's Mac"
)
THE_LOGIN_BANNERS_LOCAL_FIX: Final = f"{AWS_LOGIN} && debate-research caselist pull --publish-pending"

THE_CHECK_CUT_SHORT_IN_THE_CLOUD: Final = (
    " The report stage's check that the bucket holds what this run published was cut short."
)
THE_CHECK_CUT_SHORT_ON_THE_MAC: Final = (
    " The report stage's check that the bucket holds what this run published was cut short; "
    "the next pull, or caselist pull --publish-pending after the login, makes it again."
)
THE_INDEX_WAITS_IN_THE_CLOUD: Final = f" The search index {INDEX_ID} waits too."
THE_INDEX_WAITS_ON_THE_MAC: Final = (
    f" The search index {INDEX_ID} waits too; the next run with a session publishes it, or after the "
    "login: DEBATE_ENV=dev debate-research tub index publish --env dev --newest"
)

THE_FAILURE_RATE_HINT_IN_THE_CLOUD: Final = (
    "The cloud run's failed sources are listed in failures.jsonl of the caselist's parsed store in the "
    "bucket, once the run has published it, never in the operator's Mac's own store; why they failed is "
    'the PM\'s to look into (caselist-cloud-run.md, "A parse stage over its failure rate").'
)
NOTHING_OWED_AFTER_THE_FAILURE_RATE: Final = (
    'none owed: the parsed store was published (caselist-cloud-run.md, "A parse stage over its failure rate")'
)
"""The banner's fix line for a stage over its failure rate whose parsed store was published: no cure."""
THE_FAILURE_RATE_HINT_ON_THE_MAC: Final = (
    "`debate-research caselist parse --caselist <slug> --failures` lists the sources that failed, "
    "with their reasons."
)

THE_NEWER_TABLE_HINT_IN_THE_CLOUD: Final = (
    f"The occurrence table of {CASELIST} {VERSION} in the bucket is stamped {NEWER}, and the cloud "
    f"run's image's fingerprint version is {BUILD}. The next cloud run on an image whose fingerprint "
    f"version is {NEWER} or later rebuilds and publishes it: a new image is "
    'built and applied as caselist-cloud-run.md, "A new image, later" says, after the PM\'s word; never '
    "a rebuild or a publish from the operator's Mac."
)
THE_NEWER_TABLE_HINT_ON_THE_MAC: Final = (
    f"The occurrence table of {CASELIST} {VERSION} in the bucket is stamped {NEWER}, and this build's "
    f"fingerprint version is {BUILD}. Rebuild and publish it with a build at {NEWER} or later, and "
    "install that build for the weekly agent."
)

POINTS_AT_THE_MAC: Final = (
    "--publish",
    "--failures",
    "caselist parse",
    "caselist pull",
    "aws sso login",
    "tub index publish",
    "weekly agent",
)
"""Nothing a bucket-mode hint may name: a Mac-side publish, the Mac's failure list, the Mac's agent."""


def points_at_the_mac(text: str) -> list[str]:
    return [word for word in POINTS_AT_THE_MAC if word in text]


# ------------------------------------------------------------------------------------------------
# The run
# ------------------------------------------------------------------------------------------------


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


class ScriptedParseWithHints(ScriptedParse):
    """`v1-e34-t31`'s scripted parse stage, and two more outcomes: a caselist in `over_the_rate`
    parses with six of its ten sources failed, over the threshold; one in `newer_table` is refused
    because the bucket's occurrence table is stamped by a newer build (`v1-e34-t29`)."""

    def __init__(
        self,
        listed: LocalFallbackSuppressionList,
        bucket_copy: BucketCopy,
        *,
        over_the_rate: Sequence[str] = (),
        newer_table: Sequence[str] = (),
        **scripted: Any,
    ) -> None:
        super().__init__(listed, bucket_copy, **scripted)
        self._over_the_rate = frozenset(over_the_rate)
        self._newer_table = frozenset(newer_table)

    async def parse_new_sources(self, caselist: str) -> ParsedCaselist:
        if caselist in self._newer_table:
            raise NewerFingerprintTable(
                caselist=caselist, version=VERSION, store=THE_BUCKET, stamped=NEWER, build=BUILD
            )
        parsed = await super().parse_new_sources(caselist)
        if caselist in self._over_the_rate:
            return replace(parsed, attempted=10, tried=10, failed=6, failure_rate_exceeded=True)
        return parsed


async def run(installation: Installation, *, bucket_mode: bool, **scripted: Any) -> Watched:
    """One weekly pull of week one, in bucket mode as the composition root builds it, or in local mode."""
    bucket_copy = BucketCopy()
    listed = LocalFallbackSuppressionList(bucket_copy, local=empty_suppression_list())
    installation.suppression = listed
    service = installation.sync(
        FakeSource(installation.archives, weeks=[WEEK_1]),
        parse=ScriptedParseWithHints(listed, bucket_copy, **scripted),
        working_copy_outlives_the_run=not bucket_mode,
        bucket_mode=bucket_mode,
    )
    return await pull(installation, service, bracket=BucketModeBracket() if bucket_mode else None)


def parse_hint(watched: Watched) -> object:
    return stage(watched.summary, SyncStage.PARSE)["hint"]


def with_the_check_cut_short_and_an_index_waiting(
    record: SyncRunRecord, details: SyncRunDetails
) -> tuple[SyncRunRecord, SyncRunDetails]:
    """The same run, but with the report stage's check and the search index's publish pending too."""
    pending = {"report", "search_index"}
    stages = tuple(
        one.model_copy(update={"outcome": "pending"}) if one.stage in pending else one
        for one in record.stages
    )
    index = SearchIndexCounts(
        index_id=INDEX_ID, built=True, published=False, documents=3, sqlite_bytes=4096, gzip_bytes=1024
    )
    return record.model_copy(update={"stages": stages}), details.model_copy(update={"search_index": index})


def login_banner(record: SyncRunRecord, details: SyncRunDetails) -> Any:
    sent = notifications_for(record, details, aws_login_command=AWS_LOGIN, credentials_expired=True)
    [one] = [one for one in sent if one.title == "caselist publish waiting for an AWS login"]
    return one


# ------------------------------------------------------------------------------------------------
# The login banner
# ------------------------------------------------------------------------------------------------


async def test_a_bucket_mode_login_banner_names_the_cloud_runs_role_and_no_mac_side_publish(
    installation: Installation,
) -> None:
    """The suppression list's bucket copy needed a login while the parse stage rebuilt: a pending
    stage, and the login banner. Its fix is the cloud run's role, the PM's, never a Mac-side publish."""
    watched = await run(installation, bucket_mode=True, local_list_only=[CASELIST])

    assert details_line(installation)["bucket_run"] is not None, "the premise: a bucket-mode run"
    banner = login_notification(watched)
    assert banner.fix_command == THE_LOGIN_BANNERS_CLOUD_FIX
    assert points_at_the_mac(banner.text) == []


async def test_a_bucket_mode_login_banner_says_what_waits_without_a_command(
    installation: Installation,
) -> None:
    """With the report stage's check cut short and the index's publish pending as well: both are said,
    and neither names `--publish-pending` or `tub index publish`."""
    watched = await run(installation, bucket_mode=True, local_list_only=[CASELIST])
    assert watched.pulled.record is not None and watched.pulled.details is not None
    record, details = with_the_check_cut_short_and_an_index_waiting(
        watched.pulled.record, watched.pulled.details
    )

    banner = login_banner(record, details)

    assert THE_CHECK_CUT_SHORT_IN_THE_CLOUD in banner.message
    assert banner.message.endswith(THE_INDEX_WAITS_IN_THE_CLOUD)
    assert banner.fix_command == THE_LOGIN_BANNERS_CLOUD_FIX
    assert points_at_the_mac(banner.text) == []


async def test_a_local_mode_login_banner_is_unchanged(installation: Installation) -> None:
    watched = await run(installation, bucket_mode=False, local_list_only=[CASELIST])
    assert details_line(installation)["bucket_run"] is None, "the premise: a local-mode run"
    assert login_notification(watched).fix_command == THE_LOGIN_BANNERS_LOCAL_FIX
    assert watched.pulled.record is not None and watched.pulled.details is not None
    record, details = with_the_check_cut_short_and_an_index_waiting(
        watched.pulled.record, watched.pulled.details
    )

    banner = login_banner(record, details)

    assert THE_CHECK_CUT_SHORT_ON_THE_MAC in banner.message
    assert banner.message.endswith(THE_INDEX_WAITS_ON_THE_MAC)
    assert banner.fix_command == THE_LOGIN_BANNERS_LOCAL_FIX
    assert "cloud" not in banner.text


# ------------------------------------------------------------------------------------------------
# The failure-rate hint
# ------------------------------------------------------------------------------------------------


async def test_a_bucket_mode_parse_stage_over_its_failure_rate_points_at_the_cloud_runs_failures(
    installation: Installation,
) -> None:
    watched = await run(installation, bucket_mode=True, over_the_rate=[CASELIST])

    found = stage(watched.summary, SyncStage.PARSE)
    assert (found["outcome"], found["error_codes"]) == ("failed", ["PARSE_FAILURE_RATE_EXCEEDED"])
    assert found["hint"] == THE_FAILURE_RATE_HINT_IN_THE_CLOUD
    banner = parse_notification(watched)
    assert banner.hint == THE_FAILURE_RATE_HINT_IN_THE_CLOUD
    assert points_at_the_mac(banner.text) == []
    [told] = [one for one in details_line(installation)["stages"] if one["stage"] == "parse"]
    assert told["hint"] == THE_FAILURE_RATE_HINT_IN_THE_CLOUD
    # Its parsed store was published, so nothing is owed and no cure is named (`v1-e40-t08`, the PM's
    # amendment of 2026-11-01, from `v1-e40-t22`'s Follow-up 3).
    assert details_line(installation)["parsed_stores_owed"] == [], "the premise: the store was published"
    assert banner.fix_command == NOTHING_OWED_AFTER_THE_FAILURE_RATE
    assert "next cloud run" not in banner.text


async def test_a_local_mode_parse_stage_over_its_failure_rate_still_names_the_failures_listing(
    installation: Installation,
) -> None:
    watched = await run(installation, bucket_mode=False, over_the_rate=[CASELIST])

    assert parse_hint(watched) == THE_FAILURE_RATE_HINT_ON_THE_MAC
    assert parse_notification(watched).hint == THE_FAILURE_RATE_HINT_ON_THE_MAC


# ------------------------------------------------------------------------------------------------
# The newer-fingerprint hint
# ------------------------------------------------------------------------------------------------


async def test_a_bucket_mode_parse_stage_refused_a_newer_table_names_a_new_image(
    installation: Installation,
) -> None:
    watched = await run(installation, bucket_mode=True, newer_table=[CASELIST])

    found = stage(watched.summary, SyncStage.PARSE)
    assert (found["outcome"], found["error_codes"]) == ("failed", ["NEWER_FINGERPRINT_TABLE"])
    banner = parse_notification(watched)
    assert banner.hint is not None and banner.hint.startswith(THE_NEWER_TABLE_HINT_IN_THE_CLOUD)
    assert THE_NEWER_TABLE_HINT_IN_THE_CLOUD in str(found["hint"])
    assert points_at_the_mac(banner.text) == []


async def test_a_local_mode_parse_stage_refused_a_newer_table_still_names_the_weekly_agent(
    installation: Installation,
) -> None:
    watched = await run(installation, bucket_mode=False, newer_table=[CASELIST])

    assert THE_NEWER_TABLE_HINT_ON_THE_MAC in str(parse_hint(watched))
    assert "cloud" not in parse_notification(watched).text


async def watch_a_run_that_raised(installation: Installation, error: Exception, *, bucket_mode: bool) -> Any:
    """A pull that raised before any stage could record it: the monitor's own details of it."""
    monitor = SyncRunMonitor(
        state_dir=installation.data_dir,
        environment="dev",
        notifier=RecordingNotifier(),
        remote=installation.bucket,
        aws_login_command=AWS_LOGIN,
        clock=lambda: datetime(2026, 9, 16, 6, 0, tzinfo=UTC),
        **the_commands_retry_rule(),
    )

    async def raises() -> Any:
        raise error

    with pytest.raises(NewerFingerprintTable):
        await monitor.watch(
            raises,
            caselists=[CASELIST],
            mode="run",
            bucket_run=lambda: BucketRunDetails(bundle="saved") if bucket_mode else None,
        )
    return details_line(installation)


@pytest.mark.parametrize(
    ("bucket_mode", "hint"),
    [(True, THE_NEWER_TABLE_HINT_IN_THE_CLOUD), (False, THE_NEWER_TABLE_HINT_ON_THE_MAC)],
    ids=["bucket", "local"],
)
async def test_a_run_that_stopped_on_a_newer_table_gives_its_modes_hint(
    installation: Installation, bucket_mode: bool, hint: str
) -> None:
    """The fix a stage would give, given by the monitor for a run that raised instead (`v1-e34-t19`)."""
    error = NewerFingerprintTable(
        caselist=CASELIST, version=VERSION, store=THE_BUCKET, stamped=NEWER, build=BUILD
    )

    details = await watch_a_run_that_raised(installation, error, bucket_mode=bucket_mode)

    assert details["hint"] == hint


# ------------------------------------------------------------------------------------------------
# The pending reason's join
# ------------------------------------------------------------------------------------------------


async def test_a_pending_parse_reason_joins_its_next_sentence_without_a_stray_full_stop(
    installation: Installation,
) -> None:
    """`v1-e40-t18` found `…stage").; this machine's copy…` in a bucket-mode run's pending reason."""
    watched = await run(installation, bucket_mode=True, local_list_only=[CASELIST])

    reason = str(stage(watched.summary, SyncStage.PARSE)["reason"])
    assert (
        '(caselist-cloud-run.md, "A failed parse stage"); this machine\'s copy of the suppression list'
        in reason
    )
    assert ".;" not in reason


# ------------------------------------------------------------------------------------------------
# The runbook sections the hints name are there, and say what the hints say
# ------------------------------------------------------------------------------------------------


def section(heading: str) -> str:
    text = CLOUD_RUNBOOK.read_text(encoding="utf-8")
    assert f"\n## {heading}\n" in text, f"the section a hint names: {heading}"
    return " ".join(text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0].split())


def test_the_runbook_sections_the_hints_name_are_there_and_keep_the_rule() -> None:
    no_session = section("A run that found no AWS session")
    assert "Never run `aws sso login && debate-research caselist pull --publish-pending`" in no_session
    assert "the PM" in no_session

    over_the_rate = section("A parse stage over its failure rate")
    assert "failures.jsonl" in over_the_rate
    assert "`caselist parse --caselist <slug> --failures` on the operator's Mac" in over_the_rate

    new_image = section("A new image, later")
    assert "A parse stage refused a newer occurrence table" in new_image
    assert "install that build for the weekly agent" in new_image


# ------------------------------------------------------------------------------------------------
# The earlier builds read every record and details line these runs write
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scripted",
    [{"local_list_only": [CASELIST]}, {"over_the_rate": [CASELIST]}, {"newer_table": [CASELIST]}],
    ids=["login", "failure_rate", "newer_table"],
)
async def test_the_cloud_image_and_the_macs_build_read_every_record_and_details_line_these_runs_write(
    installation: Installation, s3_client: S3Client, evidence_bucket: str, scripted: dict[str, Any]
) -> None:
    """Against what those builds validate with, each printed by its own code (`stored_run_records/`).

    The record's schema is the one `v1.1.0-dev.164` (the cloud image) and `v1.1.0-dev.200` (the Mac's
    installed build) both print, byte for byte; it forbids a key it does not define. The details' are
    dev.164's (`details_schema_before_parsed_stores_owed.json`) and dev.200's.
    """
    await run(installation, bucket_mode=True, **scripted)

    record = record_line(installation)
    details = details_line(installation)
    assert bucket_objects(s3_client, evidence_bucket, "reports/sync-runs/") == [record]
    assert bucket_objects(s3_client, evidence_bucket, "reports/sync-run-details/") == [details]
    jsonschema.validate(record, stored_schema("record_schema_of_the_cloud_image.json"))
    assert all(set(one) == {"stage", "outcome", "reason"} for one in record["stages"])
    for name in (
        "details_schema_before_parsed_stores_owed.json",
        "details_schema_of_the_macs_installed_build.json",
    ):
        jsonschema.validate(details, stored_schema(name))
    assert set(details) <= set(
        stored_schema("details_schema_of_the_macs_installed_build.json")["properties"]
    ), "no details key the Mac's installed build does not define"

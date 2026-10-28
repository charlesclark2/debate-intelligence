"""The weekly run names `caselist parse --publish-only` where a publish alone is owed (`v1-e34-t31`).

When the parse stage rebuilt a caselist's aggregates from every copy of the suppression list and
then could not publish them, only the publish is owed, and `caselist parse --publish-only`
(`v1-e31-t30`) finishes it without a rebuild. Before this task the stage's fix text, the banners and
`sync_runs.PARSE_COMMAND` always said `--publish`. Now each caselist owed is named with its own
command:

* `--publish-only` for a caselist the stage rebuilt from every copy of the list, in a run whose
  working copy is still there afterwards (local mode);
* `--publish` for one whose aggregates may come from the run's own copy of the list alone, which
  must never be published; for one whose rebuild did not finish; and for every caselist of a run
  whose working copy goes with it (bucket mode), where the directory `--publish-only` would publish
  is not the one the run rebuilt.

Each caselist is decided from what the stage itself recorded, never from the machine. Details that
do not say, which every build before this task wrote, are named with `--publish`: failing toward the
command that rebuilds first.

The parse stage here is scripted per caselist: which rebuild reads the bucket's copy of the list on
a day it needs a login, which rebuild crashes, which publish the bucket refuses. The list is the
pull's own :class:`~debate_core.application.caselist.suppression.LocalFallbackSuppressionList`, the
run is the real one inside the real run monitor, against moto. Every expected command is written out
by hand.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jsonschema
import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist.suppression import LocalFallbackSuppressionList
from debate_core.application.caselist_sync import (
    ParsedCaselist,
    ParsedStoreOwed,
    PublishedParsedStore,
    SyncStage,
)
from debate_core.application.errors import StoreCredentialsExpired
from debate_core.application.ports.suppression import SuppressionEntry
from debate_core.application.sync_runs import (
    PARSE_COMMAND,
    SYNC_RUN_DETAILS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
    SyncRunDetails,
    SyncRunOutcome,
    SyncRunRecord,
    notifications_for,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.suppression import empty_suppression_list

from .test_inbox_retention import CASELIST, ESTUARY, ESTUARY_BODY, WEEK_1, FakeSource, Installation
from .test_pull_stage_failure_codes import Watched, outage, pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STORED: Final = Path(__file__).parent / "stored_run_records"

OPENEV: Final = "openev"
"""The caselist a camp file is parsed under: the run's second caselist here."""

PUBLISH_ONLY_THE_WEEKLY: Final = f"debate-research caselist parse --caselist {CASELIST} --publish-only"
REBUILD_THE_WEEKLY: Final = f"debate-research caselist parse --caselist {CASELIST} --publish"
PUBLISH_ONLY_OPENEV: Final = "debate-research caselist parse --caselist openev --publish-only"
REBUILD_OPENEV: Final = "debate-research caselist parse --caselist openev --publish"

AWS_LOGIN: Final = "aws sso login --profile debate-dev-evidence"


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


class BucketCopy:
    """The bucket's copy of the suppression list, which needs a login while `expired` is set."""

    def __init__(self) -> None:
        self.expired = False

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        if self.expired:
            raise StoreCredentialsExpired(hint=AWS_LOGIN)
        return ()

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:  # pragma: no cover - never written
        raise AssertionError("a pull never writes the suppression list")


class ScriptedParse:
    """The parse stage, scripted per caselist, over the pull's own suppression list.

    A rebuild reads the list as the pipeline's does. For a caselist in `local_list_only` the bucket's
    copy needs a login while it reads, so the list falls back to the run's own copy alone and the run
    sees the fallback. A caselist in `crashes` has a rebuild that raises; one in `refused` has a
    publish the bucket refuses with that error.
    """

    def __init__(
        self,
        listed: LocalFallbackSuppressionList,
        bucket_copy: BucketCopy,
        *,
        local_list_only: Sequence[str] = (),
        crashes: Sequence[str] = (),
        refused: Mapping[str, Exception] | None = None,
    ) -> None:
        self._listed = listed
        self._bucket_copy = bucket_copy
        self._local_list_only = frozenset(local_list_only)
        self._crashes = frozenset(crashes)
        self._refused = dict(refused or {})
        self.asked: list[tuple[str, str]] = []

    async def parse_new_sources(self, caselist: str) -> ParsedCaselist:
        self.asked.append(("parse", caselist))
        if caselist in self._crashes:
            raise RuntimeError("the parse pool died")
        self._bucket_copy.expired = caselist in self._local_list_only
        try:
            await self._listed.entries()
        finally:
            self._bucket_copy.expired = False
        return ParsedCaselist(version="2026.10.20-docx-6")

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:
        self.asked.append(("publish", caselist))
        refusal = self._refused.get(caselist)
        if refusal is not None:
            raise refusal
        return PublishedParsedStore(uploaded=3)


async def run(
    installation: Installation,
    *,
    with_a_camp_file: bool = False,
    working_copy_outlives_the_run: bool = True,
    **scripted: Any,
) -> tuple[Watched, ScriptedParse]:
    """One weekly pull of week one, and a camp file when asked, through the real run monitor."""
    bucket_copy = BucketCopy()
    listed = LocalFallbackSuppressionList(bucket_copy, local=empty_suppression_list())
    installation.suppression = listed
    parse = ScriptedParse(listed, bucket_copy, **scripted)
    source = FakeSource(
        installation.archives,
        weeks=[WEEK_1],
        openev=[(ESTUARY, ESTUARY_BODY)] if with_a_camp_file else [],
    )
    service = installation.sync(
        source, parse=parse, working_copy_outlives_the_run=working_copy_outlives_the_run
    )
    return await pull(installation, service), parse


def owed(watched: Watched) -> list[tuple[str, bool]]:
    return [(one.caselist, one.publish_only) for one in watched.summary.parsed_stores_owed]


def details_line(installation: Installation) -> dict[str, Any]:
    [line] = (installation.data_dir / SYNC_RUN_DETAILS_FILENAME).read_text(encoding="utf-8").splitlines()
    return json.loads(line)


def parse_notification(watched: Watched) -> Any:
    [one] = [
        sent for sent in watched.notifier.sent if sent.title == "caselist pull finished with a failed stage"
    ]
    return one


def login_notification(watched: Watched) -> Any:
    [one] = [
        sent for sent in watched.notifier.sent if sent.title == "caselist publish waiting for an AWS login"
    ]
    return one


# ------------------------------------------------------------------------------------------------
# One caselist: a publish alone owed, and a rebuild owed
# ------------------------------------------------------------------------------------------------


async def test_a_stage_whose_publish_alone_failed_names_publish_only_for_that_caselist(
    installation: Installation,
) -> None:
    """The rebuild read every copy of the list; the bucket did not answer for the parsed store."""
    watched, parse = await run(installation, refused={CASELIST: outage()})

    assert parse.asked == [("parse", CASELIST), ("publish", CASELIST)]
    assert watched.summary.suppression_list_local_copy_only is None, "the premise: every copy was read"
    found = stage(watched.summary, SyncStage.PARSE)
    assert (found["outcome"], found["error_codes"]) == ("failed", ["STORE_UNAVAILABLE"])
    assert owed(watched) == [(CASELIST, True)]
    hint = str(found["hint"])
    assert f"`{PUBLISH_ONLY_THE_WEEKLY}`" in hint
    assert f"`{REBUILD_THE_WEEKLY}`" not in hint
    assert parse_notification(watched).fix_command == PUBLISH_ONLY_THE_WEEKLY
    assert details_line(installation)["parsed_stores_owed"] == [{"caselist": CASELIST, "publish_only": True}]


async def test_a_stage_whose_aggregates_read_only_the_runs_own_list_names_publish(
    installation: Installation,
) -> None:
    """The bucket's copy of the list needed a login during the rebuild: the aggregates stay here."""
    watched, parse = await run(installation, local_list_only=[CASELIST])

    assert parse.asked == [("parse", CASELIST)], "aggregates from the run's own list are never offered"
    assert watched.summary.suppression_list_local_copy_only is not None
    found = stage(watched.summary, SyncStage.PARSE)
    assert found["outcome"] == "pending"
    assert owed(watched) == [(CASELIST, False)]
    reason = str(found["reason"])
    assert f"`{REBUILD_THE_WEEKLY}`" in reason
    assert "--publish-only" not in reason
    assert watched.pulled.record is not None
    assert watched.pulled.record.outcome is SyncRunOutcome.PUBLISH_PENDING
    message = login_notification(watched).message
    assert f"The parsed store waits too; after the login: {REBUILD_THE_WEEKLY}" in message
    assert "--publish-only" not in message
    assert details_line(installation)["parsed_stores_owed"] == [{"caselist": CASELIST, "publish_only": False}]


async def test_a_bucket_mode_run_names_publish_even_where_only_the_publish_failed(
    installation: Installation,
) -> None:
    """The cloud run's working copy goes with its task, so the rebuilt directory is nowhere to publish."""
    watched, _ = await run(installation, refused={CASELIST: outage()}, working_copy_outlives_the_run=False)

    assert watched.summary.suppression_list_local_copy_only is None
    assert owed(watched) == [(CASELIST, False)]
    hint = str(stage(watched.summary, SyncStage.PARSE)["hint"])
    assert f"`{REBUILD_THE_WEEKLY}`" in hint
    assert "--publish-only" not in hint
    assert parse_notification(watched).fix_command == REBUILD_THE_WEEKLY


# ------------------------------------------------------------------------------------------------
# One of each in a run: each caselist its own command
# ------------------------------------------------------------------------------------------------


async def test_a_run_with_one_of_each_names_each_caselist_its_own_command(installation: Installation) -> None:
    """The weekly's publish is refused after a rebuild from every copy; the camp file's rebuild read
    the run's own list alone. A failed stage."""
    watched, parse = await run(
        installation, with_a_camp_file=True, refused={CASELIST: outage()}, local_list_only=[OPENEV]
    )

    assert parse.asked == [("parse", CASELIST), ("publish", CASELIST), ("parse", OPENEV)]
    found = stage(watched.summary, SyncStage.PARSE)
    assert found["outcome"] == "failed"
    assert owed(watched) == [(CASELIST, True), (OPENEV, False)]
    hint = str(found["hint"])
    assert f"`{PUBLISH_ONLY_THE_WEEKLY}`" in hint
    assert f"`{REBUILD_OPENEV}`" in hint
    assert f"`{REBUILD_THE_WEEKLY}`" not in hint
    assert f"`{PUBLISH_ONLY_OPENEV}`" not in hint
    assert parse_notification(watched).fix_command == f"{PUBLISH_ONLY_THE_WEEKLY}; {REBUILD_OPENEV}"
    assert details_line(installation)["parsed_stores_owed"] == [
        {"caselist": CASELIST, "publish_only": True},
        {"caselist": OPENEV, "publish_only": False},
    ]


async def test_the_other_way_round_each_caselist_still_gets_its_own_command(
    installation: Installation,
) -> None:
    """The weekly's rebuild read the run's own list alone, so nothing more is offered to the bucket; the
    camp file's rebuild read every copy and waits for the publish alone. A pending stage."""
    watched, parse = await run(installation, with_a_camp_file=True, local_list_only=[CASELIST])

    assert parse.asked == [("parse", CASELIST), ("parse", OPENEV)]
    found = stage(watched.summary, SyncStage.PARSE)
    assert found["outcome"] == "pending"
    assert owed(watched) == [(CASELIST, False), (OPENEV, True)]
    reason = str(found["reason"])
    assert f"`{REBUILD_THE_WEEKLY}`" in reason
    assert f"`{PUBLISH_ONLY_OPENEV}`" in reason
    assert f"`{PUBLISH_ONLY_THE_WEEKLY}`" not in reason
    assert f"`{REBUILD_OPENEV}`" not in reason
    message = login_notification(watched).message
    assert f"after the login: {REBUILD_THE_WEEKLY}; {PUBLISH_ONLY_OPENEV}" in message


async def test_a_caselist_whose_rebuild_crashed_is_named_with_publish(installation: Installation) -> None:
    """No rebuild finished for the weekly, so there is nothing for `--publish-only` to publish of it."""
    watched, parse = await run(
        installation, with_a_camp_file=True, crashes=[CASELIST], refused={OPENEV: outage()}
    )

    assert parse.asked == [("parse", CASELIST), ("parse", OPENEV), ("publish", OPENEV)]
    assert owed(watched) == [(CASELIST, False), (OPENEV, True)]
    assert parse_notification(watched).fix_command == f"{REBUILD_THE_WEEKLY}; {PUBLISH_ONLY_OPENEV}"


async def test_a_parse_stage_that_published_everything_owes_nothing(installation: Installation) -> None:
    watched, _ = await run(installation, with_a_camp_file=True)

    assert stage(watched.summary, SyncStage.PARSE)["outcome"] == "completed"
    assert owed(watched) == []
    assert watched.summary.as_json()["parsed_stores_owed"] == []
    assert details_line(installation)["parsed_stores_owed"] == []


# ------------------------------------------------------------------------------------------------
# Details that cannot tell: an earlier build's, or an entry that does not say
# ------------------------------------------------------------------------------------------------


def as_an_earlier_build_wrote_them(details: SyncRunDetails) -> SyncRunDetails:
    """The same details with no word on the parsed stores owed: what every build before this one writes."""
    written = json.loads(details.model_dump_json())
    del written["parsed_stores_owed"]
    return SyncRunDetails.model_validate(written)


def notified(record: SyncRunRecord, details: SyncRunDetails, *, credentials_expired: bool) -> list[Any]:
    return notifications_for(
        record, details, aws_login_command=AWS_LOGIN, credentials_expired=credentials_expired
    )


async def test_details_from_an_earlier_build_name_publish(installation: Installation) -> None:
    """A run this build would name `--publish-only`, as a build that kept no such word recorded it."""
    watched, _ = await run(installation, refused={CASELIST: outage()})
    record, details = watched.pulled.record, watched.pulled.details
    assert record is not None and details is not None

    [failed] = notified(record, as_an_earlier_build_wrote_them(details), credentials_expired=False)

    assert failed.fix_command == PARSE_COMMAND
    assert "--publish-only" not in failed.fix_command


async def test_a_login_banner_from_details_an_earlier_build_wrote_names_publish(
    installation: Installation,
) -> None:
    watched, _ = await run(installation, with_a_camp_file=True, local_list_only=[CASELIST])
    record, details = watched.pulled.record, watched.pulled.details
    assert record is not None and details is not None

    [login] = notified(record, as_an_earlier_build_wrote_them(details), credentials_expired=True)

    assert f"The parsed store waits too; after the login: {PARSE_COMMAND}" in login.message
    assert "--publish-only" not in login.message


async def test_an_entry_that_does_not_say_how_its_aggregates_were_built_is_named_with_publish(
    installation: Installation,
) -> None:
    watched, _ = await run(installation, refused={CASELIST: outage()})
    record, details = watched.pulled.record, watched.pulled.details
    assert record is not None and details is not None
    written = json.loads(details.model_dump_json())
    written["parsed_stores_owed"] = [{"caselist": CASELIST}]

    [failed] = notified(record, SyncRunDetails.model_validate(written), credentials_expired=False)

    assert failed.fix_command == REBUILD_THE_WEEKLY


def test_a_parsed_store_owed_says_publish_unless_it_says_publish_only() -> None:
    assert ParsedStoreOwed(caselist=CASELIST).command == REBUILD_THE_WEEKLY
    assert ParsedStoreOwed(caselist=CASELIST, publish_only=True).command == PUBLISH_ONLY_THE_WEEKLY


# ------------------------------------------------------------------------------------------------
# The earlier builds read every record and every details line this build writes
# ------------------------------------------------------------------------------------------------


def stored_schema(name: str) -> dict[str, Any]:
    return json.loads((STORED / name).read_text(encoding="utf-8"))


def bucket_objects(s3_client: S3Client, bucket: str, prefix: str) -> list[Any]:
    listed = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
    return [
        json.loads(s3_client.get_object(Bucket=bucket, Key=str(one.get("Key")))["Body"].read())
        for one in listed
    ]


async def test_the_earlier_builds_read_every_record_and_every_details_line_this_build_writes(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Against what those builds validate with, each printed by its own code (`stored_run_records/`).

    The record's schema is `v1-e34-t19`'s, which forbids a key it does not define; the details'
    is `v1.1.0-dev.155`'s, the Mac's installed build, and this task's start commit's, byte for byte
    the same, which pass over a key they do not define and refuse their own keys with another type.
    """
    watched, _ = await run(
        installation, with_a_camp_file=True, refused={CASELIST: outage()}, local_list_only=[OPENEV]
    )
    assert len(watched.summary.parsed_stores_owed) == 2, "the premise: both kinds are written"
    record_schema = stored_schema("record_schema_of_the_start_commit.json")
    details_schema = stored_schema("details_schema_before_parsed_stores_owed.json")
    assert record_schema == stored_schema("record_schema_of_the_installed_build.json")

    [record] = [
        json.loads(line)
        for line in (installation.data_dir / SYNC_RUN_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    ]
    details = details_line(installation)
    published_records = bucket_objects(s3_client, evidence_bucket, "reports/sync-runs/")
    published_details = bucket_objects(s3_client, evidence_bucket, "reports/sync-run-details/")

    assert published_records == [record]
    assert published_details == [details]
    jsonschema.validate(record, record_schema)
    jsonschema.validate(details, details_schema)
    assert "parsed_stores_owed" not in json.dumps(record), "nothing of it in the record"
    assert all(set(one) == {"stage", "outcome", "reason"} for one in record["stages"])
    assert "parsed_stores_owed" not in details_schema["properties"], "the premise: a key they pass over"


def test_details_that_change_a_key_the_earlier_builds_define_are_refused_by_their_schema() -> None:
    """The check above can fail: the same schema refuses a details line whose `parse` is not counts."""
    details_schema = stored_schema("details_schema_before_parsed_stores_owed.json")
    line = json.loads(SyncRunDetails(run_id="20260916T060000Z").model_dump_json())
    jsonschema.validate(line, details_schema)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**line, "parse": [{"caselist": CASELIST, "publish_only": True}]}, details_schema)

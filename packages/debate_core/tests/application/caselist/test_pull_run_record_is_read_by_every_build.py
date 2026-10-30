"""A run's record is one every build reads, and what it cannot hold travels beside it (`v1-e34-t19`).

The run record forbids unknown fields, in the record and in each stage entry, and pins its
`schema_version` to `1`. So does every build already installed: the weekly agent's
(`0.1.0.dev60`, which predates `v1-e34-t17`) and `v1-e34-t17`'s own. A record with one more key is
a line those builds skip, and a skipped line is a run that vanishes from `caselist runs`, from the
backlog history, and from the list of records still owed to the bucket. No field can be added to
the record, and none is.

What this task has to keep (each failed stage's error codes and hint, a pending stage's earlier
findings, the codes the exit was decided from, the parse stage's nine counts) is kept in a second
file and a second bucket prefix, keyed by run id, that no older build opens: the run's **details**.
The details are read by a rule the record never had: a reader ignores a key it does not know.

## What is compared with what

`stored_run_records/` holds what the older builds say and wrote, none of it written by hand:

* `record_schema_of_the_start_commit.json` and `record_schema_of_the_installed_build.json`: the
  record model's own JSON Schema, printed by each build's code. They are byte for byte the same.
* `written_by_the_start_commit/`: for each scenario in `run_record_scenarios.py`, the run log and
  the bucket objects the start commit's code wrote. `stored_run_records/README.md` says how.

**An older build reads what this build writes**: the model both older builds validate with is this
build's record model, schema for schema; every record line and bucket object this build writes for
a scenario validates against that stored schema and equals, field for field, what the start commit
wrote for the same run; and the bucket prefix an older build lists holds nothing but records.
**This build reads what an older build wrote**: every stored log and bucket object reads back,
with no details, and serialises again to the bytes it was read from.

A name this task adds is looked up when a test runs, never imported at the top.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

import jsonschema
import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.caselist.interruptible_bucket import ScriptedBucket, SimulatedKill

from debate_core.application import errors, sync_runs
from debate_core.application.caselist_sync import SyncStage
from debate_core.application.sync_runs import SYNC_RUN_LOG_FILENAME, SyncRunLog, SyncRunRecord
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .run_record_scenarios import (
    RECORDS_PREFIX,
    SCENARIOS,
    SECOND_RUN,
    World,
    a_publish_left_for_a_login_and_then_drained,
    a_publish_the_bucket_refused_with_the_adapters_fix,
    a_week_imported_and_published,
)
from .test_inbox_retention import WEEK_1, ExpiredBucket, FakeSource, Installation
from .test_pull_stage_failure_codes import stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STORED = Path(__file__).parent / "stored_run_records"
WRITTEN_BY_THE_START_COMMIT = STORED / "written_by_the_start_commit"

DETAILS_FILE = "caselist-sync-run-details.jsonl"
"""The details file's name beside the run log, written out as the runbook gives it."""

DETAILS_PREFIX = "reports/sync-run-details/"
"""Where a run's details go in the bucket: a prefix no older build lists."""

FIRST_RUN_ID = "20260916T060000Z"
SECOND_RUN_ID = "20260923T060000Z"

REFUSAL = "a_refusal_to_start_published_by_the_next_run"
"""`v1-e34-t22`'s scenario, by the name its stored files have."""

THE_ADAPTERS_FIX = (
    "The bucket refused ListObjectsV2: the AWS profile debate-dev-evidence is signed in and lacks a "
    "grant for this; it is not an expired session, and logging in again changes nothing. "
    "docs/runbooks/evidence-store.md lists what each profile is granted."
)
"""The fix the bucket's adapter writes into its refusal (`v1-e29-t07`), as the publish stage gives it."""

THE_FIX_FOR_A_PROFILE_NOT_DEFINED = (
    "The bucket was never reached: set storage.s3.aws_profile to a profile this machine's AWS config "
    "defines, or add the profile to it: docs/runbooks/evidence-store.md lists the evidence profiles "
    "and how they are added. It is not an expired session, and logging in changes nothing."
)
"""The fix the adapter writes for a profile the AWS config lacks (`v1-e29-t07`), as a run that the
want of a bucket stopped gives it (`v1-e34-t22`)."""

NO_DETAILS_TO_SPEAK_OF: dict[str, Any] = {
    "stages": [],
    "failure_codes": [],
    "hint": None,
    "parse": None,
    "search_index": None,
    "held_by_request": {},
    "manifests_published": 0,
    # Added by `v1-e34-t31`: no scenario here owes a parsed store.
    "parsed_stores_owed": [],
}

WEEK_ONE_PUBLISHED: dict[str, Any] = {**NO_DETAILS_TO_SPEAK_OF, "manifests_published": 1}
"""A run that published week one: one manifest, beside its sources (`v1-e34-t28`)."""

EXPECTED_DETAILS: dict[str, list[dict[str, Any]]] = {
    "a_week_imported_and_published": [{"run_id": FIRST_RUN_ID, **WEEK_ONE_PUBLISHED}],
    "a_publish_the_bucket_did_not_take": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [
                {
                    "stage": "publish",
                    "error_codes": ["STORE_UNAVAILABLE"],
                    "hint": None,
                    "earlier_findings": [],
                    "drift": [],
                    "not_compared": [],
                }
            ],
            "failure_codes": ["STORE_UNAVAILABLE"],
            "hint": None,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            "parsed_stores_owed": [],
        }
    ],
    "a_publish_the_bucket_refused": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [
                {
                    "stage": "publish",
                    "error_codes": ["STORE_ACCESS_DENIED"],
                    "hint": None,
                    "earlier_findings": [],
                    "drift": [],
                    "not_compared": [],
                }
            ],
            "failure_codes": ["STORE_ACCESS_DENIED"],
            "hint": None,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            "parsed_stores_owed": [],
        }
    ],
    "a_week_that_cannot_be_read": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [
                {
                    "stage": "import",
                    "error_codes": ["UNREADABLE_ARCHIVE"],
                    "hint": None,
                    "earlier_findings": [],
                    "drift": [],
                    "not_compared": [],
                }
            ],
            "failure_codes": ["UNREADABLE_ARCHIVE"],
            "hint": None,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            "parsed_stores_owed": [],
        }
    ],
    "a_publish_left_for_a_login_and_then_drained": [
        {"run_id": FIRST_RUN_ID, **NO_DETAILS_TO_SPEAK_OF},
        {"run_id": SECOND_RUN_ID, **WEEK_ONE_PUBLISHED},
    ],
    "a_mismatch_and_then_an_expiry": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [
                {
                    "stage": "publish",
                    "error_codes": [],
                    "hint": None,
                    "earlier_findings": ["CHECKSUM_MISMATCH"],
                    "drift": [],
                    "not_compared": [],
                }
            ],
            "failure_codes": [],
            "hint": None,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            "parsed_stores_owed": [],
        }
    ],
    "a_run_stopped_by_an_expired_token": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [],
            "failure_codes": ["CASELIST_AUTH_EXPIRED"],
            "hint": None,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            "parsed_stores_owed": [],
        }
    ],
    "a_run_stopped_by_an_error_nobody_modelled": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [],
            "failure_codes": ["INTERNAL_ERROR"],
            "hint": None,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            "parsed_stores_owed": [],
        }
    ],
    "two_weeks_imported_and_parsed": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [],
            "failure_codes": [],
            "hint": None,
            # The nine counts `v1-e34-t17` wrote by hand for a first pull of these two weeks.
            "parse": {
                "caselists": 1,
                "full_parses": 1,
                "attempted": 6,
                "skipped": 0,
                "unsupported": 2,
                "failed": 1,
                "cards": 4,
                "uploaded": 9,
                "not_published": 0,
            },
            "search_index": None,
            "held_by_request": {},
            # Both weeks' manifests (`v1-e34-t28`).
            "manifests_published": 2,
            "parsed_stores_owed": [],
        }
    ],
    # `v1-e34-t22`: the run the want of a bucket refused, then the run that published its record.
    "a_refusal_to_start_published_by_the_next_run": [
        {
            "run_id": FIRST_RUN_ID,
            "stages": [],
            "failure_codes": ["STORE_PROFILE_NOT_CONFIGURED"],
            "hint": THE_FIX_FOR_A_PROFILE_NOT_DEFINED,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            "parsed_stores_owed": [],
        },
        {"run_id": SECOND_RUN_ID, **WEEK_ONE_PUBLISHED},
    ],
}
"""What each scenario's runs leave beside their records, written by hand from what the scenario
sets up. `schema_version` is `1` on every one and is checked apart."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> World:
    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    return World(
        installation=Installation(
            data_dir=tmp_path / "evidence",
            bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            archives=build_snapshot_zips(tmp_path / "published"),
        ),
        s3_client=s3_client,
        bucket_name=evidence_bucket,
        scratch=tmp_path,
        set_clock=set_clock,
    )


def older_builds_schema(build: str) -> dict[str, Any]:
    stored: dict[str, Any] = json.loads((STORED / f"record_schema_of_the_{build}.json").read_text("utf-8"))
    return stored


def read_as_an_older_build_reads(record: object) -> None:
    """Validate `record` as the older builds do: their model's schema, which forbids unknown fields."""
    for build in ("start_commit", "installed_build"):
        validator = jsonschema.Draft202012Validator(older_builds_schema(build))
        validator.validate(record)  # pyright: ignore[reportUnknownMemberType]


def stored_lines(name: str) -> list[str]:
    stored = (WRITTEN_BY_THE_START_COMMIT / f"{name}.run-log.jsonl").read_text("utf-8")
    return stored.splitlines()


def stored_bucket_objects(name: str) -> dict[str, str]:
    stored: dict[str, str] = json.loads(
        (WRITTEN_BY_THE_START_COMMIT / f"{name}.bucket.json").read_text("utf-8")
    )
    return stored


WORDS_THIS_BUILD_KEEPS: Final = {
    "[redacted] lists the evidence profiles": "docs/runbooks/evidence-store.md lists the evidence profiles"
}
"""What the start commit's redaction took and this build's keeps (`v1-e34-t23`): the runbook the
refusal's message points at. The stored files stay as that build wrote them; the comparison reads
them with these words in place of those, and with nothing else changed."""


def as_this_build_words_it(text: str) -> str:
    for theirs, ours in WORDS_THIS_BUILD_KEEPS.items():
        text = text.replace(theirs, ours)
    return text


SEARCH_INDEX_STAGE_THIS_BUILD_ADDS: Final = {
    "run": "no search index stage is wired in: an environment that names no evidence bucket has none",
    "publish_pending": "publish-pending runs no derived stages",
}
"""The stage entry this build records after parse and the start commit did not (`v1-e39-t09`): the
search index stage, skipped, by the reason each mode gives. These scenarios build their run with no
search index stage. A stage entry is a name, an outcome and a reason, all strings, so an older build
reads it: :func:`read_as_an_older_build_reads` holds every written record to that."""


A_COMPLETED_PUBLISH_AS_THE_START_COMMIT_COUNTED_IT: Final = re.compile(
    r"(?P<sources>\d+) object\(s\) uploaded across (?P<snapshots>\d+) snapshot\(s\)"
)
"""A completed publish stage's reason as the start commit wrote it: its sources alone (`v1-e34-t28`).

This build counts each snapshot's manifest too, in `objects_published` and in the reason, which
says how many of each. In every stored scenario a completed publish uploaded every snapshot's
manifest, into a bucket that held none, so this build's numbers are the start commit's plus one
manifest a snapshot. The reason is a string and `objects_published` an integer, so the record's
shape is unchanged: :func:`read_as_an_older_build_reads` holds every written record to that."""


def as_this_build_counts_it(record: dict[str, Any]) -> None:
    """A completed publish's count, and the record's `objects_published`, with the manifests in them."""
    for one in record.get("stages", []):
        found = A_COMPLETED_PUBLISH_AS_THE_START_COMMIT_COUNTED_IT.fullmatch(one.get("reason") or "")
        if one["stage"] != "publish" or one["outcome"] != "completed" or found is None:
            continue
        sources, manifests = int(found["sources"]), int(found["snapshots"])
        assert record["objects_published"] == sources, "the stored record counts its sources alone"
        one["reason"] = (
            f"{sources + manifests} object(s) uploaded across {manifests} snapshot(s): {sources} source(s) "
            f"and {manifests} manifest(s)"
        )
        record["objects_published"] = sources + manifests


def as_this_build_records_it(text: str) -> str:
    """A stored record as this build writes it: :func:`as_this_build_words_it`, a completed publish
    counted with its manifests (:func:`as_this_build_counts_it`), and the search index stage's entry
    after the parse stage's, where the start commit's has a parse stage and no search index stage.
    Nothing else changes."""
    record = json.loads(as_this_build_words_it(text))
    as_this_build_counts_it(record)
    stages = record.get("stages", [])
    names = [one["stage"] for one in stages]
    if "parse" in names and "search_index" not in names:
        stages.insert(
            names.index("parse") + 1,
            {
                "stage": "search_index",
                "outcome": "skipped",
                "reason": SEARCH_INDEX_STAGE_THIS_BUILD_ADDS[record["mode"]],
            },
        )
    return json.dumps(record)


def details_file(world: World) -> Path:
    return world.installation.data_dir / DETAILS_FILE


def details_written(world: World) -> list[dict[str, Any]]:
    """The details file as JSON, a line a run, read by its name and not through the code under test."""
    return [json.loads(line) for line in details_file(world).read_text("utf-8").splitlines()]


def objects_under(world: World, prefix: str) -> dict[str, Any]:
    listed = world.s3_client.list_objects_v2(Bucket=world.bucket_name, Prefix=prefix).get("Contents", [])
    return {
        str(one.get("Key")): json.loads(
            world.s3_client.get_object(Bucket=world.bucket_name, Key=str(one.get("Key")))["Body"].read()
        )
        for one in listed
    }


#: Keys `v1-e40-t03` added to the details: each stage's start and end, and the data volume's
#: reading. Their values are pinned by hand in `test_caselist_sync_stage_times_and_volume.py`; here
#: they are checked for their shape apart from the rest (`times_and_volume_in_run_order`).
TIMES_AND_VOLUME: Final = ("stage_times", "data_volume")

#: The key `v1-e40-t04` added to the details: what a bucket-mode run did with the bucket's run lock and
#: its state. `None` in local mode, which every scenario here runs in; its values are pinned by
#: `debate_cli/tests/bucket_mode/`. A build from before it passes over it (`extra="ignore"`).
BUCKET_RUN: Final = "bucket_run"

#: The stages a run times, in the order it carries them out.
RUN_ORDER: Final = [str(stage) for stage in SyncStage]


def without_the_version(details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in details.items()
        if key not in ("schema_version", *TIMES_AND_VOLUME, BUCKET_RUN)
    }


def times_and_volume_in_run_order(details: Mapping[str, Any]) -> bool:
    """Stage times in the run's order, each ending no earlier than it started, and no volume read:
    nothing in these scenarios sets `storage.volume_warning_percent`."""
    named = [one["stage"] for one in details["stage_times"]]
    return (
        named == [stage for stage in RUN_ORDER if stage in named]
        and all(one["started_at"] <= one["finished_at"] for one in details["stage_times"])
        and details["data_volume"] is None
        and details.get(BUCKET_RUN) is None
    )


# ------------------------------------------------------------------------------------------------
# The older builds' contract, and this build's record against it
# ------------------------------------------------------------------------------------------------


def test_the_stored_schemas_forbid_an_unknown_field_in_a_record_and_in_a_stage() -> None:
    """The fixture is what it says: neither older build reads a record with one more key."""
    for build in ("start_commit", "installed_build"):
        schema = older_builds_schema(build)
        assert schema["additionalProperties"] is False
        assert schema["$defs"]["StageEntry"]["additionalProperties"] is False
        assert schema["properties"]["schema_version"]["const"] == 1
    assert older_builds_schema("start_commit") == older_builds_schema("installed_build")


def what_a_record_must_be(schema: object) -> object:
    """A schema less its prose: the docstrings a model's schema quotes validate nothing."""
    if isinstance(schema, dict):
        fields = cast("dict[str, object]", schema)
        return {key: what_a_record_must_be(value) for key, value in fields.items() if key != "description"}
    if isinstance(schema, list):
        return [what_a_record_must_be(one) for one in cast("list[object]", schema)]
    return schema


def test_this_builds_record_model_is_the_one_both_older_builds_read_with() -> None:
    """Schema for schema: every field, type, default, pattern and limit, and that nothing else is
    allowed. A field added to the record, a type changed, a version moved: each makes this build's
    records ones an installed build skips, and each fails here."""
    ours = what_a_record_must_be(SyncRunRecord.model_json_schema())

    assert ours == what_a_record_must_be(older_builds_schema("installed_build"))
    assert ours == what_a_record_must_be(older_builds_schema("start_commit"))


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_the_run_log_this_build_writes_is_read_by_the_older_builds(name: str, world: World) -> None:
    """Each line this build appends validates as the older builds validate it, and is the line the
    start commit's build wrote for the same run."""
    await SCENARIOS[name](world)

    written = world.run_log().decode("utf-8").splitlines()
    stored = [as_this_build_records_it(line) for line in stored_lines(name)]
    assert len(written) == len(stored) == len(EXPECTED_DETAILS[name])
    for ours, theirs in zip(written, stored, strict=True):
        read_as_an_older_build_reads(json.loads(ours))
        assert json.loads(ours) == json.loads(theirs)
        assert list(json.loads(ours)) == list(json.loads(theirs)), "the same keys in the same order"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_the_bucket_prefix_an_older_build_lists_holds_only_records_it_reads(
    name: str, world: World
) -> None:
    """An older build's `caselist runs --remote` lists `reports/sync-runs/` and reads every `.json`
    under it. What this build puts there is what the start commit put there, key for key and field
    for field: nothing an older build would skip, and nothing that would crowd a record out."""
    await SCENARIOS[name](world)

    ours = world.records_in_the_bucket()
    theirs = {key: as_this_build_records_it(body) for key, body in stored_bucket_objects(name).items()}
    assert sorted(ours) == sorted(theirs)
    for key, body in ours.items():
        assert key.startswith(RECORDS_PREFIX)
        read_as_an_older_build_reads(json.loads(body))
        assert json.loads(body) == json.loads(theirs[key])
    assert not DETAILS_PREFIX.startswith(RECORDS_PREFIX)


async def test_a_refusal_that_carries_the_adapters_fix_is_still_a_record_the_older_builds_read(
    world: World,
) -> None:
    """`v1-e29-t07` put the fix into the refusal, and a stage's reason quotes the refusal, so this
    run's record says more than the start commit's did for the same run. It says it in the same
    field: the record is the stored one but for the words of the publish stage's reason, and the
    older builds read it, from the log and from the bucket."""
    await a_publish_the_bucket_refused_with_the_adapters_fix(world)

    [written] = world.run_log().decode("utf-8").splitlines()
    [stored] = [as_this_build_records_it(line) for line in stored_lines("a_publish_the_bucket_refused")]
    [(key, in_the_bucket)] = world.records_in_the_bucket().items()
    assert [key] == list(stored_bucket_objects("a_publish_the_bucket_refused"))
    for ours in (json.loads(written), json.loads(in_the_bucket)):
        read_as_an_older_build_reads(ours)
        theirs = json.loads(stored)
        assert list(ours) == list(theirs), "the same keys in the same order"
        [reason] = [one.pop("reason") for one in ours["stages"] if one["stage"] == "publish"]
        [stored_reason] = [one.pop("reason") for one in theirs["stages"] if one["stage"] == "publish"]
        assert ours == theirs
        assert reason.startswith(stored_reason.removesuffix("[redacted]"))
        assert "lacks a grant" in reason and reason != stored_reason


def test_the_stored_refusal_is_a_failed_run_that_names_its_error_and_has_no_stage() -> None:
    """`v1-e34-t22`. What the start commit's code wrote when it was handed a run the want of a
    bucket stopped, read by hand: an ordinary failed record, the kind every build has always
    written for a run that stopped on an error, with nothing in it that build did not define. The
    second line is the run that published it. The scenario tests above hold this build to both."""
    refused, published = (json.loads(line) for line in stored_lines(REFUSAL))

    assert (refused["run_id"], refused["outcome"], refused["mode"]) == (FIRST_RUN_ID, "failed", "run")
    assert refused["error_class"] == "StoreProfileNotConfigured"
    assert refused["error_message"].startswith(
        "AWS profile 'debate-dev-evidence-typo', named by storage.s3.aws_profile, is not defined in "
        "this machine's AWS config: set storage.s3.aws_profile to a profile"
    )
    assert refused["stages"] == [] and refused["pending_publish"] == []
    assert (published["run_id"], published["outcome"]) == (SECOND_RUN_ID, "completed")
    assert sorted(stored_bucket_objects(REFUSAL)) == [
        f"{RECORDS_PREFIX}2026/{FIRST_RUN_ID}.json",
        f"{RECORDS_PREFIX}2026/{SECOND_RUN_ID}.json",
    ], "the older build's next run published the refused run's record"
    for line in stored_lines(REFUSAL):
        read_as_an_older_build_reads(json.loads(line))


# ------------------------------------------------------------------------------------------------
# This build reads what the older builds wrote
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_a_run_log_an_older_build_wrote_is_read_whole_and_written_back_byte_for_byte(
    name: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Every line is a record, none is skipped, and each serialises to the line it was read from:
    this build republishing an older build's record sends the bytes that build would have."""
    log = tmp_path / SYNC_RUN_LOG_FILENAME
    log.write_bytes((WRITTEN_BY_THE_START_COMMIT / f"{name}.run-log.jsonl").read_bytes())

    with caplog.at_level(logging.WARNING):
        records = SyncRunLog(log).read()

    assert [one.model_dump_json() for one in records] == stored_lines(name)
    assert caplog.records == []
    history = sync_runs.SyncRunHistory(
        log=SyncRunLog(log), remote=None, scratch_dir=tmp_path, overdue_after_days=8
    )
    runs = await history.recent_runs(5)
    assert [one.record for one in runs] == list(reversed(records))
    assert [one.details for one in runs] == [None] * len(records), "an older build wrote no details"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_the_records_an_older_build_published_are_read_from_the_bucket(
    name: str, tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    stored = stored_bucket_objects(name)
    for key, body in stored.items():
        s3_client.put_object(Bucket=evidence_bucket, Key=key, Body=body.encode("utf-8"))
    bucket = S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)

    runs = await sync_runs.read_remote_runs(bucket, last=5, scratch_dir=tmp_path)

    assert [one.record.run_id for one in runs] == sorted(
        (json.loads(body)["run_id"] for body in stored.values()), reverse=True
    )
    assert [one.record.model_dump_json(indent=2) + "\n" for one in runs] == [
        stored[key] for key in sorted(stored, reverse=True)
    ]
    assert [one.details for one in runs] == [None] * len(stored)


# ------------------------------------------------------------------------------------------------
# ac3, ac9: what travels beside the record
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_the_codes_and_the_parse_counts_travel_beside_the_record_keyed_by_run_id(
    name: str, world: World
) -> None:
    """One line of details a run, in the file beside the run log, and one object a run under the
    details prefix: each failed stage's codes and its hint, a pending stage's earlier findings, the
    codes the exit was decided from, and the parse stage's nine counts or `null`."""
    await SCENARIOS[name](world)

    written = details_written(world)
    assert [without_the_version(one) for one in written] == EXPECTED_DETAILS[name]
    assert [one["schema_version"] for one in written] == [1] * len(written)
    assert all(times_and_volume_in_run_order(one) for one in written)
    in_the_bucket = objects_under(world, DETAILS_PREFIX)
    assert in_the_bucket == {f"{DETAILS_PREFIX}2026/{one['run_id']}.json": one for one in written}
    assert sorted(key.removeprefix(DETAILS_PREFIX) for key in in_the_bucket) == sorted(
        key.removeprefix(RECORDS_PREFIX) for key in world.records_in_the_bucket()
    ), "a record in the bucket has its details there too"


async def test_a_stages_hint_beside_the_record_is_the_fix_the_summary_gives(world: World) -> None:
    await a_publish_the_bucket_refused_with_the_adapters_fix(world)

    [pulled] = world.pulled
    [details] = details_written(world)
    assert details["stages"][0]["hint"] == THE_ADAPTERS_FIX
    assert details["stages"][0]["hint"] == stage(pulled.summary, SyncStage.PUBLISH)["hint"]
    assert pulled.details is not None
    assert pulled.details.model_dump(mode="json") == details


async def test_a_run_and_its_details_read_back_together_from_the_log_and_from_the_bucket(
    world: World, tmp_path: Path
) -> None:
    """What `caselist runs` is given: each record with the details of the same run id, newest first."""
    await a_publish_left_for_a_login_and_then_drained(world)
    history = sync_runs.SyncRunHistory(
        log=SyncRunLog(world.installation.data_dir / SYNC_RUN_LOG_FILENAME),
        remote=lambda: world.installation.bucket,
        scratch_dir=tmp_path,
        overdue_after_days=8,
    )

    for remote in (False, True):
        runs = await history.recent_runs(5, remote=remote)

        assert [one.record.run_id for one in runs] == [SECOND_RUN_ID, FIRST_RUN_ID]
        assert [one.details.run_id for one in runs if one.details] == [SECOND_RUN_ID, FIRST_RUN_ID]
        assert [one.record.mode for one in runs] == ["publish_pending", "run"]


async def test_a_record_left_owed_by_an_expired_session_is_published_with_its_details_by_the_next_run(
    world: World,
) -> None:
    """The first run finds no session: neither its record nor its details reach the bucket. The
    second run publishes both for both runs, and each record's details go up before it does, so a
    record in the bucket never waits for its details."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    world.installation.bucket = ExpiredBucket()
    await world.pull(world.installation.sync(source))
    assert world.records_in_the_bucket() == {}
    assert objects_under(world, DETAILS_PREFIX) == {}

    world.installation.bucket = S3EvidenceObjectStore(bucket=world.bucket_name, client=world.s3_client)
    world.set_clock(SECOND_RUN)
    await world.pull(world.installation.sync(source))

    assert sorted(world.records_in_the_bucket()) == [
        f"{RECORDS_PREFIX}2026/{FIRST_RUN_ID}.json",
        f"{RECORDS_PREFIX}2026/{SECOND_RUN_ID}.json",
    ]
    assert sorted(objects_under(world, DETAILS_PREFIX)) == [
        f"{DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json",
        f"{DETAILS_PREFIX}2026/{SECOND_RUN_ID}.json",
    ]


async def test_a_record_does_not_reach_the_bucket_ahead_of_its_details(world: World) -> None:
    """The bucket takes everything but the details. The record is then not sent either: the run
    stays owed as a whole, so that when the bucket takes both, both go up, and a record in the
    bucket is never one whose details were left behind. This machine's log has the record
    regardless."""
    bucket = world.installation.bucket
    assert isinstance(bucket, S3EvidenceObjectStore)

    def will_not_take_details(key: str, _: int) -> None:
        if key.startswith(DETAILS_PREFIX):
            raise errors.StoreUnavailable("PutObject", key, "simulated 503 SlowDown")

    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    world.installation.bucket = ScriptedBucket(bucket, will_not_take_details)
    await world.pull(world.installation.sync(source))

    assert world.records_in_the_bucket() == {}
    assert objects_under(world, DETAILS_PREFIX) == {}
    assert len(world.run_log().splitlines()) == 1
    owed = json.loads((world.installation.data_dir / "caselist-sync-records-pending.json").read_text("utf-8"))
    assert owed == {"run_ids": [FIRST_RUN_ID]}

    world.installation.bucket = bucket
    world.set_clock(SECOND_RUN)
    await world.pull(world.installation.sync(source))

    assert sorted(key.removeprefix(RECORDS_PREFIX) for key in world.records_in_the_bucket()) == sorted(
        key.removeprefix(DETAILS_PREFIX) for key in objects_under(world, DETAILS_PREFIX)
    )
    assert len(world.records_in_the_bucket()) == 2


async def test_details_that_cannot_be_written_never_cost_the_run_its_record(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The details are the lesser file. If this machine will not take the line, the record is still
    logged and published and the run still ends as it would have."""

    def will_not_append(self: object, details: object) -> None:
        raise PermissionError(13, "Permission denied", str(details_file(world)))

    monkeypatch.setattr(sync_runs.SyncRunDetailsLog, "append", will_not_append)

    await a_week_imported_and_published(world)

    assert world.raised == []
    assert len(world.run_log().splitlines()) == 1
    assert len(world.records_in_the_bucket()) == 1
    assert not details_file(world).exists()


async def test_the_record_is_in_the_log_before_the_details_are_written(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process dies as the details are appended. The record is already in the run log: it is
    written first, because it is what a run is, and a run with no details still reads as a run."""

    def killed(self: object, details: object) -> None:
        raise SimulatedKill

    monkeypatch.setattr(sync_runs.SyncRunDetailsLog, "append", killed)

    with pytest.raises(SimulatedKill):
        await a_week_imported_and_published(world)

    [record] = SyncRunLog(world.installation.data_dir / SYNC_RUN_LOG_FILENAME).read()
    assert record.run_id == FIRST_RUN_ID
    assert not details_file(world).exists()


# ------------------------------------------------------------------------------------------------
# The details' own rule: a reader ignores what it does not know
# ------------------------------------------------------------------------------------------------


def test_details_with_a_key_this_build_does_not_know_are_read_and_the_key_ignored(tmp_path: Path) -> None:
    """The rule that would have made this task a field and not a second file. A later build may add
    to the details, at any depth, and this build still reads the line."""
    path = tmp_path / DETAILS_FILE
    path.write_text(
        '{"schema_version": 1, "run_id": "20260916T060000Z", "added_later": {"anything": [1, 2]}, '
        '"stages": [{"stage": "publish", "error_codes": ["STORE_UNAVAILABLE"], "added_later": true}], '
        '"failure_codes": ["STORE_UNAVAILABLE"], '
        '"parse": {"caselists": 1, "full_parses": 0, "attempted": 2, "skipped": 0, "unsupported": 0, '
        '"failed": 0, "cards": 7, "uploaded": 3, "not_published": 0, "added_later": 4}}\n',
        encoding="utf-8",
    )

    read = sync_runs.SyncRunDetailsLog(path).read()

    details = read["20260916T060000Z"]
    assert details.failure_codes == ("STORE_UNAVAILABLE",)
    assert details.stages[0].error_codes == ("STORE_UNAVAILABLE",)
    assert details.parse is not None and details.parse.cards == 7


def test_details_this_build_cannot_read_are_no_details_and_never_a_lost_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A line that is not details, and one whose version says a later build changed its meaning,
    are skipped with a warning naming the line. The runs they belong to are still runs: the record
    is in the other file."""
    path = tmp_path / DETAILS_FILE
    path.write_text(
        "{not json at all\n"
        '{"schema_version": 2, "run_id": "20260916T060000Z", "stages": []}\n'
        '{"schema_version": 1, "run_id": "20260923T060000Z", "stages": []}\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        read = sync_runs.SyncRunDetailsLog(path).read()

    assert sorted(read) == ["20260923T060000Z"]
    assert [one.getMessage() for one in caplog.records] == [
        "caselist run details: line 1 is not details this build reads; skipped",
        "caselist run details: line 2 is not details this build reads; skipped",
    ]
    assert str(tmp_path) not in caplog.text
    assert sync_runs.SyncRunDetailsLog(tmp_path / "no-such-file.jsonl").read() == {}


def test_a_details_file_that_cannot_be_read_at_all_is_no_details_and_blank_lines_are_passed_over(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    unreadable = tmp_path / "not-text" / DETAILS_FILE
    unreadable.parent.mkdir()
    unreadable.write_bytes(b"\xff\xfe\x00 not text in any encoding this reads")
    spaced = tmp_path / DETAILS_FILE
    spaced.write_text('\n{"schema_version": 1, "run_id": "20260916T060000Z"}\n\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert sync_runs.SyncRunDetailsLog(unreadable).read() == {}
        assert sorted(sync_runs.SyncRunDetailsLog(spaced).read()) == ["20260916T060000Z"]

    assert [one.getMessage() for one in caplog.records] == [
        "caselist run details: could not be read (UnicodeDecodeError)"
    ]
    assert str(tmp_path) not in caplog.text


class DetailsGoneSinceTheyWereListed:
    """The bucket, with every details object deleted between the listing and the read."""

    def __init__(self, inner: S3EvidenceObjectStore) -> None:
        self.inner = inner

    async def list_objects(self, prefix: str) -> Any:
        return await self.inner.list_objects(prefix)

    async def head(self, key: str) -> Any:
        return await self.inner.head(key)

    async def put_file(self, key: str, source: Path) -> Any:
        return await self.inner.put_file(key, source)

    async def get_file(self, key: str, destination: Path) -> Any:
        if key.startswith(DETAILS_PREFIX):
            raise errors.NotFound("evidence object", key)
        return await self.inner.get_file(key, destination)


async def test_what_the_bucket_holds_that_this_build_cannot_read_costs_no_run_that_it_can(
    world: World, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Two runs are in the bucket with their details. Then the details of one are replaced by
    something that is not details, and an object that is not a record is put beside the records.
    Both runs are still listed: the first without details, which is how a run nobody kept details
    for reads. The same when the details vanish between the listing and the read."""
    await a_publish_left_for_a_login_and_then_drained(world)
    bucket = world.installation.bucket
    assert isinstance(bucket, S3EvidenceObjectStore)
    world.s3_client.put_object(
        Bucket=world.bucket_name,
        Key=f"{DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json",
        Body=b'{"schema_version": 2}',
    )
    world.s3_client.put_object(
        Bucket=world.bucket_name,
        Key=f"{RECORDS_PREFIX}2026/20260930T060000Z.json",
        Body=b'{"not": "a record"}',
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        runs = await sync_runs.read_remote_runs(bucket, last=5, scratch_dir=tmp_path)
    warned = [one.getMessage() for one in caplog.records]
    gone = await sync_runs.read_remote_runs(
        DetailsGoneSinceTheyWereListed(bucket), last=5, scratch_dir=tmp_path
    )

    assert [one.record.run_id for one in runs] == [SECOND_RUN_ID, FIRST_RUN_ID]
    assert [one.details.run_id if one.details else None for one in runs] == [SECOND_RUN_ID, None]
    assert warned == [
        "caselist run log: reports/sync-runs/2026/20260930T060000Z.json in the bucket is not a valid "
        "run record; skipped",
        f"caselist run details: {DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json in the bucket is not details "
        "this build reads; skipped",
    ]
    assert [one.record.run_id for one in gone] == [SECOND_RUN_ID, FIRST_RUN_ID]
    assert [one.details for one in gone] == [None, None]


# ------------------------------------------------------------------------------------------------
# Forbidden: a path in a record
# ------------------------------------------------------------------------------------------------


def test_a_run_stopped_by_a_refusal_keeps_the_code_and_the_fix_a_stage_would_have_given() -> None:
    """A manifest this machine will not let the selection read stops the run before any stage can
    record it (`v1-e34-t13`). Its details still say what it failed on, and what to do about it."""
    refusal = errors.LocalStoreAccessDenied("read", "the manifest directory", hint="unused here")

    details = sync_runs.details_for_failure(refusal, run_id="20260916T060000Z")

    assert details.failure_codes == ("STORE_ACCESS_DENIED",)
    assert details.hint == (
        "This machine refused the manifest directory: check that this user can read and write it, "
        "under the environment's data directory (storage.data_dir). It is a permission on this "
        "machine, not the AWS session."
    )
    assert details.stages == ()
    assert details.parse is None


def test_a_hint_is_kept_as_written_apart_from_a_secret_or_an_absolute_path() -> None:
    """Every hint this project writes names a directory by its role, so there is nothing to take
    out, and the runbook it points at survives. This is the backstop for one that did not."""
    kept = (
        "This machine refused the manifest directory: check that this user can read and write it, "
        "under the environment's data directory (storage.data_dir). docs/runbooks/evidence-store.md "
        "lists what each profile is granted. `debate-research caselist parse --caselist <slug> --publish`"
    )

    assert sync_runs.hint_for_a_record(kept, secrets=()) == kept
    leaked = sync_runs.hint_for_a_record(
        "Look in /Users/someone/.debate-research/dev/objects and ~/Library/Logs with token hunter2-token",
        secrets=("hunter2-token",),
    )
    assert leaked == "Look in [redacted] and [redacted] with token [redacted]"
    long = sync_runs.hint_for_a_record("Fix it. " * 400)
    assert len(long) == 1200 and long.endswith("…"), "a hint is a sentence or two, never a page"


async def test_nothing_beside_a_record_names_a_path_on_this_machine(world: World) -> None:
    await a_publish_the_bucket_refused_with_the_adapters_fix(world)

    text = details_file(world).read_text("utf-8") + json.dumps(objects_under(world, DETAILS_PREFIX))
    for forbidden in (str(world.installation.data_dir), str(world.scratch), str(Path.home())):
        assert forbidden not in text

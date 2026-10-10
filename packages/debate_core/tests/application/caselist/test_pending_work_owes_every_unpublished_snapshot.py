"""Every snapshot a publish did not confirm stays owed, however the stage ended (`v1-e34-t18`).

When the AWS session expired part-way through the publish stage of `caselist pull`, the stage wrote
only the snapshots it had not reached to the pending-work file. Two things were then wrong with the
file, both noticed by `v1-e34-t13`:

* a snapshot that had ended incomplete earlier in the same stage was not in it, so nothing owed it:
  the next pull found it imported, and `--publish-pending` had never heard of it;
* a snapshot owed from before that this stage had published stayed in it, because that one exit
  merged into the file where every other exit rewrote it.

And the file itself could lose work: one that could not be read was taken for nothing owed, and the
next write replaced it.

Everything here is real except the OpenCaselist source and the one thing each test breaks: the
importers, the manifests, the publisher and the status comparison, against moto, in the installation
`test_inbox_retention.py` builds. What the file holds is read here as JSON, by name, and never
through the class under test, and what the bucket confirmed is read from the bucket. Every expected
list, code and outcome is written by hand from what the test sets up (working agreement 6).

A name this task adds is looked up when a test runs, never imported at the top, so that every test
here can be collected and run against the source as it was before the change.
"""

from __future__ import annotations

import errno
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.caselist.interruptible_bucket import ScriptedBucket, SimulatedKill
from tests.fixtures.caselist.publish_expectations import expected_publish, expected_source_key

from debate_core.application import caselist_sync as sync_module
from debate_core.application.caselist_sync import PendingSnapshot, PendingWork, SyncStage
from debate_core.application.errors import (
    DomainError,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreUnavailable,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_inbox_retention import (
    CASELIST,
    WEEK_1,
    WEEK_2,
    WEEK_3,
    ExpiredBucket,
    FakeSource,
    Installation,
    kept,
    label,
    removed,
    weekly_name,
)
from .test_pull_stage_failure_codes import (
    RefusingBucket,
    assert_names_nothing_of_this_machine,
    outage,
    pull,
    stage,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

AWS_LOGIN = "aws sso login --profile debate-dev-evidence"

PENDING_WORK_FILE = "caselist-sync-pending.json"
"""The file's name as the runbook gives it to an operator, written out and not imported."""

OWED_1, OWED_2, OWED_3 = "testcl26 2026-09-01", "testcl26 2026-09-08", "testcl26 2026-09-15"

MANIFEST = {
    WEEK_1: "manifests/testcl26/2026-09-01.jsonl",
    WEEK_2: "manifests/testcl26/2026-09-08.jsonl",
    WEEK_3: "manifests/testcl26/2026-09-15.jsonl",
}
"""A snapshot's manifest is uploaded last and only once every source is confirmed, so its key is
the one upload that belongs to exactly one snapshot: breaking it breaks that snapshot and no other."""

ONLY_IN_WEEK_1 = "grove-round-2-neg-first"
"""The one synthetic body week one stores and no later week does (`expected_publish.json`)."""

NEW_IN_WEEK_2 = "grove-round-2-neg-revised"
"""A body week two is the first to store, so its upload is first asked for by week two's publish."""


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


# ------------------------------------------------------------------------------------------------
# What the file holds and what the bucket confirmed, each read without the code under test
# ------------------------------------------------------------------------------------------------


def pending_file(installation: Installation) -> Path:
    return installation.data_dir / PENDING_WORK_FILE


def owed(installation: Installation) -> list[str]:
    """The snapshots the pending-work file names, in its order; none when there is no file."""
    path = pending_file(installation)
    if not path.exists():
        return []
    body = json.loads(path.read_text(encoding="utf-8"))
    return [f"{one['caselist']} {one['snapshot']}" for one in body["publish"]]


def write_owed(installation: Installation, *snapshots: tuple[str, str]) -> None:
    """The pending-work file as a person would write it by hand: the shape the runbook documents."""
    installation.data_dir.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(
        f'{{"caselist": "{caselist}", "snapshot": "{snapshot}"}}' for caselist, snapshot in snapshots
    )
    pending_file(installation).write_text(f'{{"publish": [{entries}]}}\n', encoding="utf-8")


def confirmed_in(s3_client: S3Client, bucket: str) -> list[str]:
    """The snapshots whose manifest the bucket holds: the ones a publish completed, named as owed are."""
    prefix = "manifests/testcl26/"
    listed = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
    return sorted(f"testcl26 {str(one.get('Key'))[len(prefix) : -len('.jsonl')]}" for one in listed)


# ------------------------------------------------------------------------------------------------
# An AWS session that goes wrong at one upload a test names
# ------------------------------------------------------------------------------------------------


def answered_503(key: ObjectKey) -> DomainError:
    """The bucket did not take the upload. The publisher carries on, and the snapshot is incomplete."""
    return StoreUnavailable("PutObject", key, "simulated 503 SlowDown")


def not_granted(key: ObjectKey) -> DomainError:
    """The bucket refused the profile. True of every upload still to come, so the stage stops."""
    return StoreAccessDenied("PutObject", key)


class Session(ScriptedBucket):
    """The real bucket, behind an AWS session that goes wrong where a test says.

    Args:
        answers: What the upload of a key is answered with, instead of being taken.
        expires_on: The key whose upload finds the session expired. Every call after it is refused
            the same way, as an expired session refuses everything.
        goes_quiet_after: The key after whose upload no listing is answered: an outage that starts
            between two snapshots, which the next one's plan is the first to meet.
        killed_on: The key at whose upload the process is killed.
    """

    def __init__(
        self,
        inner: EvidenceObjectStore,
        *,
        answers: Mapping[ObjectKey, Callable[[ObjectKey], DomainError]] | None = None,
        expires_on: ObjectKey | None = None,
        goes_quiet_after: ObjectKey | None = None,
        killed_on: ObjectKey | None = None,
    ) -> None:
        assert isinstance(inner, S3EvidenceObjectStore)
        super().__init__(inner, self._before_put)
        self.answers = dict(answers or {})
        self.expires_on = expires_on
        self.goes_quiet_after = goes_quiet_after
        self.killed_on = killed_on
        self.expired = False
        self.quiet = False

    def _refuse_once_expired(self) -> None:
        if self.expired:
            raise StoreCredentialsExpired(hint=AWS_LOGIN)

    def _before_put(self, key: ObjectKey, _: int) -> None:
        self._refuse_once_expired()
        if key == self.killed_on:
            raise SimulatedKill
        if key == self.expires_on:
            self.expired = True
            self._refuse_once_expired()
        answer = self.answers.get(key)
        if answer is not None:
            raise answer(key)

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        self._refuse_once_expired()
        if self.quiet:
            raise StoreUnavailable("ListObjectsV2", prefix, "simulated 503 SlowDown")
        return await super().list_objects(prefix)

    async def head(self, key: ObjectKey) -> ObjectInfo:
        self._refuse_once_expired()
        return await super().head(key)

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        sent = await super().put_file(key, source)
        if key == self.goes_quiet_after:
            self.quiet = True
        return sent

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        self._refuse_once_expired()
        return await super().get_file(key, destination)


# ------------------------------------------------------------------------------------------------
# ac1: incomplete, then the session expires. Both are owed.
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "other_bytes_under_the_key",
    [
        pytest.param(False, id="an upload the bucket answered 503"),
        pytest.param(True, id="an upload the bucket did not take over other bytes"),
    ],
)
async def test_a_snapshot_left_incomplete_before_the_session_expired_is_owed_beside_the_one_it_expired_on(
    installation: Installation, s3_client: S3Client, evidence_bucket: str, other_bytes_under_the_key: bool
) -> None:
    """Two weeks are imported. Week one's publish ends incomplete: one of its uploads is not taken.
    The session then expires on week two. Until this task only week two was written down, and
    nothing owed week one."""
    week_one_only = expected_source_key(ONLY_IN_WEEK_1)
    if other_bytes_under_the_key:
        s3_client.put_object(Bucket=evidence_bucket, Key=week_one_only, Body=b"other bytes")
    session = Session(
        installation.bucket,
        answers={} if other_bytes_under_the_key else {week_one_only: answered_503},
        expires_on=expected_source_key(NEW_IN_WEEK_2),
    )
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    watched = await pull(installation, installation.sync(source, publish_to=session))
    await session.settle()

    summary = watched.summary
    assert summary.snapshots_imported == (OWED_1, OWED_2)
    assert stage(summary, SyncStage.PUBLISH)["outcome"] == "pending"
    assert confirmed_in(s3_client, evidence_bucket) == [], "neither week's manifest reached the bucket"
    assert owed(installation) == [OWED_1, OWED_2]
    assert summary.pending_publish == (OWED_1, OWED_2)
    assert summary.succeeded, "an expired session is pending, not a failed run (v1-e34-t13, unchanged)"
    assert stage(summary, SyncStage.PUBLISH).get("error_codes") == []
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# ac2: `--publish-pending` after a fresh session
# ------------------------------------------------------------------------------------------------


async def test_publish_pending_after_a_fresh_session_publishes_every_snapshot_the_stage_left(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """ac1's run, with a third week the stage never reached. After `aws sso login`,
    `--publish-pending` publishes all three, and the bucket then holds what a clean publish of the
    three synthetic weeks holds: the fixture's own hand-written totals."""
    session = Session(
        installation.bucket,
        answers={expected_source_key(ONLY_IN_WEEK_1): answered_503},
        expires_on=expected_source_key(NEW_IN_WEEK_2),
    )
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2, WEEK_3])
    await installation.sync(source, publish_to=session).run([CASELIST])
    await session.settle()
    assert owed(installation) == [OWED_1, OWED_2, OWED_3]

    drained = await pull(installation, installation.sync(source), publish_pending=True)

    assert stage(drained.summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert stage(drained.summary, SyncStage.REPORT)["outcome"] == "completed"
    assert drained.summary.succeeded
    assert drained.summary.pending_publish == ()
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1, OWED_2, OWED_3]
    assert owed(installation) == []
    assert not pending_file(installation).exists(), "a file with nothing owed is removed"
    totals = expected_publish()["totals"]
    sources = s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="raw/caselist/testcl26/")
    assert len(sources.get("Contents", [])) == totals["source_objects"] == 14
    assert source.archive_fetches == [weekly_name(WEEK_1), weekly_name(WEEK_2), weekly_name(WEEK_3)], (
        "the retry fetched or imported something again"
    )


async def test_a_second_expiry_part_way_through_the_retry_takes_only_the_confirmed_snapshots_off_the_file(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Three weeks are owed. The retry publishes week one and the session expires again on week
    two. Until this task week one stayed in the file although the bucket had confirmed it. The
    second retry, after another login, publishes the other two and removes the file."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2, WEEK_3])
    await installation.sync(source, publish_to=ExpiredBucket()).run([CASELIST])
    assert owed(installation) == [OWED_1, OWED_2, OWED_3]

    session = Session(installation.bucket, expires_on=MANIFEST[WEEK_2])
    first = await pull(installation, installation.sync(source, publish_to=session), publish_pending=True)
    await session.settle()

    assert stage(first.summary, SyncStage.PUBLISH)["outcome"] == "pending"
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1]
    assert owed(installation) == [OWED_2, OWED_3]
    assert first.summary.pending_publish == (OWED_2, OWED_3)
    assert [one.title for one in first.notifier.sent] == ["caselist publish waiting for an AWS login"]
    assert AWS_LOGIN in first.notified

    second = await pull(installation, installation.sync(source), publish_pending=True)

    assert stage(second.summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1, OWED_2, OWED_3]
    assert owed(installation) == []
    assert second.summary.pending_publish == ()


# ------------------------------------------------------------------------------------------------
# ac3: every way the stage can end
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ending:
    """One way the publish stage can end, and what the pending-work file must hold afterwards.

    Every ending starts from the same place. An earlier run imported weeks one and two with the
    session expired, so both are owed. This run imports week three. The stage publishes what this
    run imported first and then what was owed: week three, week one, week two.
    """

    outcome: str
    error_codes: list[str]
    owed: list[str]
    session: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    """How this run's session goes wrong: the arguments of :class:`Session`."""
    expired_from_the_start: bool = False
    other_bytes_under: str | None = None
    """A synthetic body under whose key the bucket already holds something else."""


ENDINGS = [
    pytest.param(Ending(outcome="completed", error_codes=[], owed=[]), id="completed"),
    pytest.param(
        Ending(
            session={"answers": {MANIFEST[WEEK_1]: answered_503}},
            outcome="failed",
            error_codes=["STORE_UNAVAILABLE"],
            owed=[OWED_1],
        ),
        id="failed on a code: one snapshot's upload answered 503, the others confirmed",
    ),
    pytest.param(
        Ending(
            other_bytes_under=ONLY_IN_WEEK_1,
            outcome="failed",
            error_codes=["CHECKSUM_MISMATCH"],
            owed=[OWED_1],
        ),
        id="failed on a code: other bytes under one snapshot's key, a verdict",
    ),
    pytest.param(
        Ending(
            session={"answers": {MANIFEST[WEEK_1]: not_granted}},
            outcome="failed",
            error_codes=["STORE_ACCESS_DENIED"],
            owed=[OWED_1, OWED_2],
        ),
        id="failed on a code: stopped by a refusal after one snapshot was confirmed",
    ),
    pytest.param(
        Ending(
            session={"goes_quiet_after": MANIFEST[WEEK_3]},
            outcome="failed",
            error_codes=["STORE_UNAVAILABLE"],
            owed=[OWED_1, OWED_2],
        ),
        id="failed on a code: stopped by an outage after one snapshot was confirmed",
    ),
    pytest.param(
        Ending(
            session={"answers": {MANIFEST[WEEK_3]: answered_503, MANIFEST[WEEK_1]: not_granted}},
            outcome="failed",
            error_codes=["STORE_UNAVAILABLE", "STORE_ACCESS_DENIED"],
            owed=[OWED_1, OWED_2, OWED_3],
        ),
        id="failed on a code: one snapshot incomplete, then stopped by a refusal",
    ),
    pytest.param(
        Ending(expired_from_the_start=True, outcome="pending", error_codes=[], owed=[OWED_1, OWED_2, OWED_3]),
        id="pending: the session had expired before the first upload",
    ),
    pytest.param(
        Ending(
            session={"expires_on": MANIFEST[WEEK_1]},
            outcome="pending",
            error_codes=[],
            owed=[OWED_1, OWED_2],
        ),
        id="pending: the session expired after this run's snapshot was confirmed",
    ),
    pytest.param(
        Ending(session={"expires_on": MANIFEST[WEEK_2]}, outcome="pending", error_codes=[], owed=[OWED_2]),
        id="pending: the session expired after a snapshot owed from before was confirmed",
    ),
    pytest.param(
        Ending(
            session={"answers": {MANIFEST[WEEK_3]: answered_503}, "expires_on": MANIFEST[WEEK_1]},
            outcome="pending",
            error_codes=[],
            owed=[OWED_1, OWED_2, OWED_3],
        ),
        id="pending: one snapshot incomplete, then the session expired",
    ),
]


async def reach(
    ending: Ending,
    installation: Installation,
    s3_client: S3Client,
    evidence_bucket: str,
    *,
    once_two_weeks_are_owed: Callable[[], None] = lambda: None,
) -> sync_module.RunSummary:
    """Run the pull that ends its publish stage the way `ending` says, from the common start."""
    earlier = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(earlier, publish_to=ExpiredBucket()).run([CASELIST])
    assert owed(installation) == [OWED_1, OWED_2]
    once_two_weeks_are_owed()
    if ending.other_bytes_under is not None:
        s3_client.put_object(
            Bucket=evidence_bucket, Key=expected_source_key(ending.other_bytes_under), Body=b"other bytes"
        )
    session = Session(installation.bucket, **ending.session)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2, WEEK_3])

    summary = await installation.sync(
        source, publish_to=ExpiredBucket() if ending.expired_from_the_start else session
    ).run([CASELIST])
    await session.settle()

    assert summary.snapshots_imported == (OWED_3,)
    return summary


@pytest.mark.parametrize("ending", ENDINGS)
async def test_however_the_publish_stage_ends_the_file_holds_exactly_the_snapshots_not_confirmed(
    ending: Ending, installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The file afterwards is the hand-written list, and the bucket agrees with it: a snapshot is in
    the file exactly when the bucket does not hold its manifest."""
    summary = await reach(ending, installation, s3_client, evidence_bucket)

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == ending.outcome
    assert published.get("error_codes") == ending.error_codes
    assert owed(installation) == ending.owed
    assert summary.pending_publish == tuple(ending.owed)
    assert confirmed_in(s3_client, evidence_bucket) == sorted({OWED_1, OWED_2, OWED_3} - set(ending.owed))
    assert_names_nothing_of_this_machine(summary, installation)


@pytest.mark.parametrize("ending", ENDINGS)
async def test_however_the_publish_stage_ends_the_file_is_what_the_one_computation_returned(
    ending: Ending,
    installation: Installation,
    s3_client: S3Client,
    evidence_bucket: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ending keeps a rule of its own. The one function is made to answer with a snapshot nobody
    owes, a different one each time it is asked. Whatever ended the stage, the file and the summary
    hold its last answer, and it was told what the bucket had confirmed."""
    asked: list[dict[str, Any]] = []

    def nobody_owes_this(*_: object, **named: Any) -> tuple[PendingSnapshot, ...]:
        asked.append(named)
        return (PendingSnapshot("testcl26", f"1999-01-{len(asked):02d}"),)

    summary = await reach(
        ending,
        installation,
        s3_client,
        evidence_bucket,
        once_two_weeks_are_owed=lambda: monkeypatch.setattr(
            sync_module, "snapshots_still_owed", nobody_owes_this
        ),
    )

    assert stage(summary, SyncStage.PUBLISH)["outcome"] == ending.outcome
    last_answer = f"testcl26 1999-01-{len(asked):02d}"
    assert owed(installation) == [last_answer]
    assert summary.pending_publish == (last_answer,)
    told_confirmed = sorted(f"{one.caselist} {one.snapshot}" for one in asked[-1]["confirmed"])
    assert told_confirmed == confirmed_in(s3_client, evidence_bucket)


A, B, C = (PendingSnapshot("testcl26", day) for day in ("2026-09-01", "2026-09-08", "2026-09-15"))
RELEASE = PendingSnapshot("openev", "2026-policy")

STILL_OWED = [
    pytest.param([], [], [], [], [], id="nothing owed and nothing to publish"),
    pytest.param([], [A, B], [A, B], [], [], id="everything confirmed"),
    pytest.param([], [A, B, C], [], [], [A, B, C], id="nothing confirmed: all of it is owed"),
    pytest.param([A], [A, B], [A], [], [B], id="the one owed from before confirmed, the new one not"),
    pytest.param([A, B], [C, A, B], [C], [], [A, B], id="owed from before keeps its place in the file"),
    pytest.param([A], [B, A], [], [], [A, B], id="newly owed goes after what was owed before"),
    pytest.param([A], [B], [B], [], [A], id="owed from before and never attempted is still owed"),
    pytest.param([A, RELEASE], [A, RELEASE], [A], [], [RELEASE], id="a camp release is owed like a week"),
    pytest.param([A, B], [A, B], [B], [A], [], id="no manifest on this machine: not owed"),
    pytest.param([], [A], [], [A], [], id="no manifest on this machine, and never owed before"),
    pytest.param([A], [A], [B, C], [], [A], id="a confirmation of something else settles nothing"),
]


@pytest.mark.parametrize(
    ("previously_owed", "targets", "confirmed", "without_local_manifest", "expected"), STILL_OWED
)
def test_what_is_still_owed_is_everything_owed_or_targeted_that_the_bucket_did_not_confirm(
    previously_owed: list[PendingSnapshot],
    targets: list[PendingSnapshot],
    confirmed: list[PendingSnapshot],
    without_local_manifest: list[PendingSnapshot],
    expected: list[PendingSnapshot],
) -> None:
    """The one computation, on hand-written cases. Owed from before, plus everything the stage set
    out to publish, minus what the bucket confirmed; and never a snapshot this machine holds no
    manifest for, which no run here could ever publish."""
    still_owed = sync_module.snapshots_still_owed(
        previously_owed, targets, confirmed=confirmed, without_local_manifest=without_local_manifest
    )

    assert list(still_owed) == expected


# ------------------------------------------------------------------------------------------------
# A snapshot with no manifest on this machine is reported, and is not owed
# ------------------------------------------------------------------------------------------------


async def test_an_owed_snapshot_this_machine_holds_no_manifest_for_is_reported_once_and_owed_no_longer(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The file names week one, which is imported, and a week this machine holds no manifest for.
    No run here can publish the second, so owing it would fail every run from now on. It is
    reported, with its code, and leaves the file; week one publishes; the next retry has nothing
    to do."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    await installation.sync(source, publish_to=ExpiredBucket()).run([CASELIST])
    write_owed(installation, ("testcl26", "2026-09-01"), ("testcl26", "2026-08-25"))

    drained = await installation.sync(source).publish_pending()

    published = stage(drained, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["NOTHING_TO_PUBLISH"]
    assert "testcl26 2026-08-25: no local manifest" in str(published["reason"])
    assert drained.failure_codes == ("NOTHING_TO_PUBLISH",)
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1]
    assert owed(installation) == []
    assert drained.pending_publish == ()

    again = await installation.sync(source).publish_pending()

    assert stage(again, SyncStage.PUBLISH)["outcome"] == "skipped"
    assert again.succeeded


async def test_an_owed_snapshot_the_stage_never_reached_stays_owed_whatever_this_machine_holds(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The same file, and the session expires on week one. Nobody has asked for the second snapshot
    yet, so nobody has learnt that it has no manifest: it is not yet attempted, and stays."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    await installation.sync(source, publish_to=ExpiredBucket()).run([CASELIST])
    write_owed(installation, ("testcl26", "2026-09-01"), ("testcl26", "2026-08-25"))
    session = Session(installation.bucket, expires_on=MANIFEST[WEEK_1])

    drained = await installation.sync(source, publish_to=session).publish_pending()
    await session.settle()

    assert stage(drained, SyncStage.PUBLISH)["outcome"] == "pending"
    assert confirmed_in(s3_client, evidence_bucket) == []
    assert owed(installation) == [OWED_1, "testcl26 2026-08-25"]


# ------------------------------------------------------------------------------------------------
# A publish that is killed
# ------------------------------------------------------------------------------------------------


async def test_a_publish_killed_part_way_has_already_written_down_everything_it_set_out_to_publish(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The process dies on week two, as it does when the Mac shuts down under the agent. No code
    runs afterwards, so what is owed has to be on disk before the first upload. Week one is in the
    file although the bucket confirmed it: the file may name more than is owed, never less, and the
    next run publishes week two and finds week one already there."""
    session = Session(installation.bucket, killed_on=MANIFEST[WEEK_2])
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    with pytest.raises(SimulatedKill):
        await installation.sync(source, publish_to=session).run([CASELIST])
    await session.settle()

    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1]
    assert owed(installation) == [OWED_1, OWED_2]

    again = await installation.sync(source).run([CASELIST])

    assert again.snapshots_imported == (), "nothing is imported twice"
    assert stage(again, SyncStage.PUBLISH)["outcome"] == "completed"
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1, OWED_2]
    assert owed(installation) == []


# ------------------------------------------------------------------------------------------------
# ac5: the file itself does not lose work
# ------------------------------------------------------------------------------------------------

ONE_GOOD_ENTRY_AND_ONE_NOT = (
    b'{"publish": [{"caselist": "testcl26", "snapshot": "2026-08-25"}, '
    b'{"caselist": "testcl26", "snapshot": 20260901}]}'
)
"""The dangerous one: a build that skipped the entry it could not read and went on would write the
file back without it."""

MALFORMED = [
    pytest.param(b"", id="empty"),
    pytest.param(b'{"publish": [{"caselist": "testcl26", "snap', id="cut short part-way through"),
    pytest.param(b"{not json at all", id="not JSON"),
    pytest.param(b"\xff\xfe\x00{", id="not UTF-8"),
    pytest.param(b'[{"caselist": "testcl26", "snapshot": "2026-09-01"}]', id="a list, not an object"),
    pytest.param(b'{"owed": []}', id="no publish list"),
    pytest.param(
        b'{"publish": {"caselist": "testcl26", "snapshot": "2026-09-01"}}', id="publish is not a list"
    ),
    pytest.param(b'{"publish": ["testcl26 2026-09-01"]}', id="an entry that is not an object"),
    pytest.param(b'{"publish": [{"caselist": "testcl26"}]}', id="an entry with no snapshot"),
    pytest.param(ONE_GOOD_ENTRY_AND_ONE_NOT, id="one entry readable and one not"),
    pytest.param(
        b'{"publish": [{"caselist": "testcl26", "snapshot": "next tuesday"}]}',
        id="a snapshot name with no place in the store",
    ),
    pytest.param(
        b'{"publish": [{"caselist": "../elsewhere", "snapshot": "2026-09-01"}]}',
        id="a caselist name with no place in the store",
    ),
]


@pytest.mark.parametrize("contents", MALFORMED)
def test_a_pending_work_file_that_cannot_be_read_is_an_error_and_never_nothing_owed(
    tmp_path: Path, contents: bytes
) -> None:
    """Reading it raises, by a name of its own, and says nothing of where the file is."""
    path = tmp_path / PENDING_WORK_FILE
    path.write_bytes(contents)

    with pytest.raises(DomainError) as raised:
        PendingWork(path).read()

    assert type(raised.value) is sync_module.PendingWorkUnreadable
    assert "the pending-work file under storage.data_dir" in str(raised.value)
    assert str(tmp_path) not in str(raised.value)
    assert path.read_bytes() == contents


def test_a_pending_work_file_holds_weeks_complete_archives_and_camp_releases_and_reads_back(
    tmp_path: Path,
) -> None:
    """The three kinds of snapshot a pull imports, in the file's one shape, written here by hand."""
    path = tmp_path / PENDING_WORK_FILE
    path.write_text(
        '{"publish": ['
        '{"caselist": "testcl26", "snapshot": "2026-09-01"}, '
        '{"caselist": "testcl26", "snapshot": "full/2026-09-15"}, '
        '{"caselist": "openev", "snapshot": "2026-policy"}]}',
        encoding="utf-8",
    )
    three = (
        PendingSnapshot("testcl26", "2026-09-01"),
        PendingSnapshot("testcl26", "full/2026-09-15"),
        PendingSnapshot("openev", "2026-policy"),
    )

    assert PendingWork(path).read() == three

    PendingWork(path).write(three[1:])

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "publish": [
            {"caselist": "testcl26", "snapshot": "full/2026-09-15"},
            {"caselist": "openev", "snapshot": "2026-policy"},
        ]
    }
    assert PendingWork(tmp_path / "no-such-file.json").read() == ()


UNREADABLE_IN_A_RUN = [
    pytest.param(b'{"publish": [{"caselist": "testcl26", "snap', id="cut short part-way through"),
    pytest.param(b"{not json at all", id="not JSON"),
    pytest.param(ONE_GOOD_ENTRY_AND_ONE_NOT, id="one entry readable and one not"),
]


@pytest.mark.parametrize("contents", UNREADABLE_IN_A_RUN)
async def test_a_pull_that_finds_the_file_unreadable_leaves_it_and_fails_publish_naming_it_by_role(
    installation: Installation, s3_client: S3Client, evidence_bucket: str, contents: bytes
) -> None:
    """The file was there before the run and cannot be read. The run does not know what it owed, so
    it must not write over it: the stage fails on a verdict, the file is byte for byte what it was,
    and the hint names it by what it is for. The week this run imported needs nothing from the
    file, so it is published and confirmed all the same."""
    installation.data_dir.mkdir(parents=True)
    pending_file(installation).write_bytes(contents)
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    watched = await pull(installation, installation.sync(source))

    summary = watched.summary
    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["PENDING_WORK_UNREADABLE"]
    assert "the pending-work file under storage.data_dir" in str(published.get("hint"))
    assert "docs/runbooks/caselist-scheduled-sync.md" in str(published.get("hint"))
    assert RUNBOOK.is_file()
    assert pending_file(installation).read_bytes() == contents
    assert summary.failure_codes == ("PENDING_WORK_UNREADABLE",)
    assert not summary.succeeded
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1]
    assert summary.pending_publish == ()
    assert stage(summary, SyncStage.REPORT)["outcome"] == "completed"
    assert "aws sso login" not in watched.notified
    assert "aws sso login" not in json.dumps(published)
    assert_names_nothing_of_this_machine(summary, installation)


async def test_an_unreadable_file_and_an_expired_session_fail_publish_and_name_what_could_not_be_recorded(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Nothing can be published and nothing can be written down, so this is not "pending": pending
    means recorded for a later run. The stage fails, the file is untouched, and the reason and the
    summary name the week that is owed and is in no file, for the person who repairs it."""
    installation.data_dir.mkdir(parents=True)
    pending_file(installation).write_bytes(b"{not json at all")
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source, publish_to=ExpiredBucket()).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["PENDING_WORK_UNREADABLE"]
    assert pending_file(installation).read_bytes() == b"{not json at all"
    assert confirmed_in(s3_client, evidence_bucket) == []
    assert summary.pending_publish == (OWED_1,)
    assert "not recorded as owed: testcl26 2026-09-01" in str(published["reason"])
    assert_names_nothing_of_this_machine(summary, installation)


async def test_an_unreadable_file_and_a_bucket_that_did_not_answer_record_both_and_the_verdict_decides(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The outage alone would be a run a retry cures. The file is not: both codes are recorded, so
    the one a person has to look at is not hidden behind the one that passes by itself."""
    installation.data_dir.mkdir(parents=True)
    pending_file(installation).write_bytes(b"{not json at all")
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source, publish_to=RefusingBucket(outage())).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["STORE_UNAVAILABLE", "PENDING_WORK_UNREADABLE"]
    assert summary.failure_codes == ("STORE_UNAVAILABLE", "PENDING_WORK_UNREADABLE")
    assert pending_file(installation).read_bytes() == b"{not json at all"
    assert confirmed_in(s3_client, evidence_bucket) == []
    assert summary.pending_publish == (OWED_1,)
    assert "not recorded as owed: testcl26 2026-09-01" in str(published["reason"])
    assert_names_nothing_of_this_machine(summary, installation)


async def test_publish_pending_leaves_an_unreadable_file_alone_and_drains_it_once_a_person_has_repaired_it(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """`--publish-pending` reads the file before anything else. Unreadable, it publishes nothing and
    changes nothing. Once the file is written again by hand, in the shape the runbook gives, the
    same command publishes what it names and removes it."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    await installation.sync(source, bucket=False).run([CASELIST])
    pending_file(installation).write_bytes(b'{"publish": [{"caselist": "testcl26", "snap')

    refused = await pull(installation, installation.sync(source), publish_pending=True)

    published = stage(refused.summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["PENDING_WORK_UNREADABLE"]
    assert pending_file(installation).read_bytes() == b'{"publish": [{"caselist": "testcl26", "snap'
    assert confirmed_in(s3_client, evidence_bucket) == []
    assert_names_nothing_of_this_machine(refused.summary, installation)

    write_owed(installation, ("testcl26", "2026-09-01"))
    drained = await pull(installation, installation.sync(source), publish_pending=True)

    assert stage(drained.summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1]
    assert not pending_file(installation).exists()


def test_a_write_that_dies_part_way_leaves_the_file_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk fills half-way through writing the file. What was owed before is still what the
    file says, whole and readable: the new contents go to another file in the same directory and
    take the name only once they are complete. Written in place, the file would be left cut short,
    which is the very thing the read above refuses."""
    path = tmp_path / PENDING_WORK_FILE
    before = (PendingSnapshot("testcl26", "2026-09-01"),)
    PendingWork(path).write(before)
    as_written = path.read_bytes()
    write_text = Path.write_text
    died: list[Path] = []

    def dies_half_way(self: Path, data: str, *arguments: Any, **named: Any) -> int:
        died.append(self)
        write_text(self, data[: len(data) // 2], *arguments, **named)
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "write_text", dies_half_way)
    with pytest.raises(OSError, match="No space left on device"):
        PendingWork(path).write([*before, PendingSnapshot("testcl26", "2026-09-08")])
    monkeypatch.undo()

    assert died, "the write did not go through the call this test breaks, so it proved nothing"
    assert path.read_bytes() == as_written
    assert PendingWork(path).read() == before
    assert {one.parent for one in died} == {tmp_path}, "a rename is atomic only inside one directory"

    PendingWork(path).write([PendingSnapshot("testcl26", "2026-09-08")])

    assert PendingWork(path).read() == (PendingSnapshot("testcl26", "2026-09-08"),)
    left = sorted(one.name for one in tmp_path.iterdir())
    assert left == [PENDING_WORK_FILE], "a part-written file was left behind"


# ------------------------------------------------------------------------------------------------
# ac4: the runbook's account of the file is the file
# ------------------------------------------------------------------------------------------------

RUNBOOK = Path(__file__).resolve().parents[5] / "docs" / "runbooks" / "caselist-scheduled-sync.md"


def test_the_runbook_names_the_pending_work_file_and_its_example_is_one_the_sync_reads(
    tmp_path: Path,
) -> None:
    """The hint of an unreadable file sends a person to the runbook for the file's name and shape,
    to write it again by hand. So the name there is the one the sync uses, and the example there,
    copied out as it stands, reads back as the three snapshots it shows."""
    runbook = RUNBOOK.read_text(encoding="utf-8")
    section = runbook.split("\n## The pending-work file\n", 1)[1].split("\n## ", 1)[0]
    example = section.split("```json\n", 1)[1].split("```", 1)[0]
    copied = tmp_path / sync_module.PENDING_WORK_FILENAME
    copied.write_text(example, encoding="utf-8")

    assert sync_module.PENDING_WORK_FILENAME == PENDING_WORK_FILE
    assert f"<data_dir>/{PENDING_WORK_FILE}" in section
    assert PendingWork(copied).read() == (
        PendingSnapshot("hsld26", "2026-10-07"),
        PendingSnapshot("hsld26", "full/2026-10-07"),
        PendingSnapshot("openev", "2026-policy"),
    )
    assert "Checking it is empty after a retry" in section
    assert "PENDING_WORK_UNREADABLE" in section


# ------------------------------------------------------------------------------------------------
# Retention is the safety net: an owed snapshot's zip stays until the bucket has confirmed it
# ------------------------------------------------------------------------------------------------


async def test_a_snapshot_left_owed_by_an_expiry_keeps_its_zip_through_the_next_runs_retention(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """ac1's run leaves two weeks owed and two zips in the inbox. The next run still has no session
    to publish with, and its retention stage, which can read the bucket, keeps both zips because
    the bucket confirms neither. Only the run that publishes and confirms them removes them."""
    session = Session(
        installation.bucket,
        answers={expected_source_key(ONLY_IN_WEEK_1): answered_503},
        expires_on=expected_source_key(NEW_IN_WEEK_2),
    )
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    expired = await installation.sync(source, publish_to=session).run([CASELIST])
    await session.settle()

    assert kept(expired) == {label(WEEK_1): "not_confirmed", label(WEEK_2): "not_confirmed"}
    assert installation.inbox_names() == {weekly_name(WEEK_1), weekly_name(WEEK_2)}

    still_expired = await installation.sync(source, publish_to=ExpiredBucket()).run([CASELIST])

    assert stage(still_expired, SyncStage.PUBLISH)["outcome"] == "pending"
    assert stage(still_expired, SyncStage.RETENTION)["outcome"] == "completed"
    assert removed(still_expired) == []
    assert kept(still_expired) == {label(WEEK_1): "not_confirmed", label(WEEK_2): "not_confirmed"}
    assert installation.inbox_names() == {weekly_name(WEEK_1), weekly_name(WEEK_2)}

    logged_in = await installation.sync(source).run([CASELIST])

    assert stage(logged_in, SyncStage.PUBLISH)["outcome"] == "completed"
    assert confirmed_in(s3_client, evidence_bucket) == [OWED_1, OWED_2]
    assert removed(logged_in) == [label(WEEK_1), label(WEEK_2)]
    assert installation.inbox_names() == set()
    assert owed(installation) == []
    assert source.archive_fetches == [weekly_name(WEEK_1), weekly_name(WEEK_2)]

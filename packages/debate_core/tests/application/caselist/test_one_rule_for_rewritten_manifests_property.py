"""After the same removal runs again, status counts no version of a manifest it rewrote (`v1-e30-t24`).

The property behind item (2), over generated version listings rather than t19's fixed ones. Each
example is a key some runs of `RM-2026-01` rewrote in dev, each run completed or stopped, each
carrying on for a while after its rewrite (more than the fifteen-minute margin included); versions
of the key at generated times (the same second as a rewrite, either side of a completion less the
margin, long before, long after), some of them delete markers; a rewrite the bucket may no longer
hold; and a publish after everything, or not, which decides what is current.

Both sides are the real code, given the same log entries and scopes: the sweep is
:func:`~debate_core.application.caselist.manifest_sweep.swept_manifest_versions` over the planner's
:func:`~debate_core.application.caselist.manifest_sweep.earlier_rewrites`, and status is
:func:`~debate_core.application.caselist.removal_residue.removal_residue` over
:func:`~debate_core.application.caselist.removal_residue.completed_removals`. Only the bucket is a
stand-in, a list of versions in memory, which lists the way S3 does: by key, the current version
first.

What must hold, every example:

* after the versions the sweep names are deleted, status counts no manifest version of `testcl26`;
* the sweep names no current version, no delete marker, no version of another key, and neither the
  latest rewrite of the key nor a publish after every run;
* records of another request, and of another environment, change nothing the sweep names.

The moto worlds for the three states the PM named are `test_status_and_the_sweep_share_one_rule.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import anyio
from hypothesis import event, given, settings
from hypothesis import strategies as st

from debate_core.application.caselist.manifest_sweep import earlier_rewrites, swept_manifest_versions
from debate_core.application.caselist.removal_residue import (
    CLOCK_SKEW_MARGIN,
    MANIFEST_ROLE,
    completed_removals,
    removal_residue,
)
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import (
    ManifestRewriteRecord,
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    RemovalSelectorKind,
    SuppressionState,
)

CASELIST: Final = "testcl26"
KEY: Final = f"manifests/{CASELIST}/2026-09-15.jsonl"
"""The manifest every run of the request rewrote."""
OTHER_CASELIST: Final = "testclb26"
OTHER_KEY: Final = f"manifests/{OTHER_CASELIST}/2026-09-15.jsonl"
"""A manifest another request's run rewrote, in another caselist."""
REQUEST: Final = "RM-2026-01"
ANOTHER_REQUEST: Final = "RM-2026-12"
START: Final = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
SECOND: Final = timedelta(seconds=1)
MINUTE: Final = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class Run:
    rewritten_at: datetime
    ended_at: datetime
    completed: bool
    rewrite_held: bool


class VersionsInMemory:
    """A versioned bucket's listing in memory: S3's order, by key and then the current version first."""

    def __init__(self, versions: Sequence[ObjectVersion]) -> None:
        self.versions = list(versions)

    @property
    def location(self) -> str:
        return "s3://in-memory"

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        found = [one for one in self.versions if one.key.startswith(prefix)]
        return tuple(sorted(found, key=lambda one: (one.key, not one.is_latest, -_seconds(one))))

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        raise AssertionError("the rule for a rewritten key reads no version's contents")

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        gone = {(one.key, one.version_id) for one in versions}
        self.versions = [one for one in self.versions if (one.key, one.version_id) not in gone]
        return len(gone)


def _seconds(version: ObjectVersion) -> float:
    return version.last_modified.timestamp() if version.last_modified is not None else 0.0


@st.composite
def runs(draw: st.DrawFn) -> tuple[Run, ...]:
    """One to three runs of the request, one after another, each rewriting the key once."""
    found: list[Run] = []
    moment = START
    for _ in range(draw(st.integers(min_value=1, max_value=3))):
        rewritten_at = moment + draw(st.sampled_from((1, 5, 30, 120))) * MINUTE
        carries_on = (
            draw(st.sampled_from((0, 2, 14, 15, 16, 25, 40, 90))) * MINUTE
            + draw(st.sampled_from((0, 1, 59))) * SECOND
        )
        found.append(
            Run(
                rewritten_at=rewritten_at,
                ended_at=rewritten_at + carries_on,
                completed=draw(st.booleans()),
                rewrite_held=draw(st.integers(min_value=0, max_value=5)) > 0,
            )
        )
        moment = rewritten_at + carries_on
    return tuple(found)


@st.composite
def histories(draw: st.DrawFn) -> tuple[tuple[Run, ...], list[tuple[datetime, bool]], bool]:
    """The runs, the key's other versions as `(when, is a delete marker)`, and a publish on top."""
    the_runs = draw(runs())
    special = [START - timedelta(days=1), the_runs[-1].ended_at + timedelta(days=1)]
    for run in the_runs:
        cut = run.ended_at - CLOCK_SKEW_MARGIN
        special += [run.rewritten_at, run.rewritten_at - SECOND, run.rewritten_at + SECOND]
        special += [cut - SECOND, cut, cut + SECOND, run.ended_at]
    span = int((the_runs[-1].ended_at - START).total_seconds()) + 7200
    when = st.one_of(
        st.sampled_from(special),
        st.integers(min_value=-7200, max_value=span).map(lambda seconds: START + seconds * SECOND),
    )
    others = draw(
        st.lists(st.tuples(when, st.integers(min_value=0, max_value=5).map(lambda n: n == 0)), max_size=6)
    )
    return the_runs, others, draw(st.booleans())


def bucket_of(
    the_runs: Sequence[Run], others: Sequence[tuple[datetime, bool]], publish_on_top: bool
) -> tuple[list[ObjectVersion], dict[int, str], str | None]:
    """The key's versions as S3 would hold them, with each run's rewrite id and the top publish's.

    Written in time order, a tie in the order they were put, so the last written is current. A
    rewrite the bucket no longer holds keeps its id in the scope and is gone from the listing.
    """
    written: list[tuple[datetime, int, str, bool, bool]] = []
    for index, run in enumerate(the_runs):
        written.append((run.rewritten_at, len(written), f"rewrite-{index}", False, run.rewrite_held))
    for index, (when, marker) in enumerate(others):
        written.append((when, len(written), f"other-{index}", marker, True))
    top = None
    if publish_on_top:
        top = "published-after"
        written.append((the_runs[-1].ended_at + timedelta(hours=2), len(written), top, False, True))
    written.sort(key=lambda one: (one[0], one[1]))
    latest = written[-1][2]
    versions = [
        ObjectVersion(
            key=KEY,
            version_id=version_id,
            is_latest=version_id == latest,
            is_delete_marker=marker,
            last_modified=when,
        )
        for when, _, version_id, marker, held in written
        if held
    ]
    return versions, {index: f"rewrite-{index}" for index in range(len(the_runs))}, top


def records_of(
    the_runs: Sequence[Run],
    rewrite_ids: dict[int, str],
    *,
    request_id: str = REQUEST,
    environment: str = "dev",
) -> tuple[list[RemovalLogEntry], list[RemovalScopeEntry]]:
    entries: list[RemovalLogEntry] = []
    scopes: list[RemovalScopeEntry] = []
    for index, run in enumerate(the_runs):
        entries.append(
            RemovalLogEntry(
                kind=RemovalLogKind.REMOVAL,
                recorded_at=run.ended_at,
                request_id=request_id,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                environment=environment,
                outcome=RemovalOutcome.COMPLETED if run.completed else RemovalOutcome.INCOMPLETE,
                selector=RemovalSelectorKind.SOURCE,
                error_code=None if run.completed else "STORE_UNAVAILABLE",
            )
        )
        scopes.append(
            RemovalScopeEntry(
                recorded_at=run.ended_at,
                request_id=request_id,
                environment=environment,
                caselists=(CASELIST,),
                manifest_rewrites=(ManifestRewriteRecord(key=KEY, version_id=rewrite_ids[index]),),
            )
        )
    return entries, scopes


def elsewhere(
    the_runs: Sequence[Run],
) -> tuple[list[RemovalLogEntry], list[RemovalScopeEntry], list[ObjectVersion]]:
    """Another request's completed run of `testclb26`, with an old version of its key; and this
    request's own runs in prod, rewriting the same key as in dev, completed a day later."""
    later = the_runs[-1].ended_at + timedelta(days=1)
    other_run = Run(rewritten_at=later - MINUTE, ended_at=later, completed=True, rewrite_held=True)
    other_entries, other_scopes = records_of(
        (other_run,), {0: "rewrite-of-another"}, request_id=ANOTHER_REQUEST
    )
    other_scopes = [
        one.model_copy(
            update={
                "caselists": (OTHER_CASELIST,),
                "manifest_rewrites": (ManifestRewriteRecord(key=OTHER_KEY, version_id="rewrite-of-another"),),
            }
        )
        for one in other_scopes
    ]
    prod_runs = tuple(replace(run, ended_at=later, completed=True) for run in the_runs)
    prod_entries, prod_scopes = records_of(
        prod_runs, {index: f"other-{index}" for index in range(len(the_runs))}, environment="prod"
    )
    other_versions = [
        ObjectVersion(
            key=OTHER_KEY, version_id="rewrite-of-another", is_latest=True, last_modified=later - MINUTE
        ),
        ObjectVersion(key=OTHER_KEY, version_id="before-it", is_latest=False, last_modified=START),
    ]
    return [*other_entries, *prod_entries], [*other_scopes, *prod_scopes], other_versions


async def swept(
    bucket: VersionsInMemory, entries: Sequence[RemovalLogEntry], scopes: Sequence[RemovalScopeEntry]
) -> set[tuple[str, str | None]]:
    found = await swept_manifest_versions(
        bucket,
        caselists=(),
        rewritten_now=(),
        earlier_rewrites=earlier_rewrites(entries, scopes, request_id=REQUEST, environment="dev"),
        names_removed=lambda caselist, line, key: False,
    )
    return {(one.key, one.version_id) for one in found}


async def manifest_versions_status_counts(
    bucket: VersionsInMemory, entries: Sequence[RemovalLogEntry], scopes: Sequence[RemovalScopeEntry]
) -> int:
    residue = await removal_residue(
        bucket, CASELIST, SuppressionState(), completed_removals(entries, scopes, "dev")
    )
    return sum(one.versions for one in residue.older_versions if one.role == MANIFEST_ROLE)


def describe(the_runs: Sequence[Run], versions: Sequence[ObjectVersion]) -> None:
    """What the example holds that the property is for, for `--hypothesis-show-statistics`."""
    for run in the_runs:
        if run.completed and run.ended_at - run.rewritten_at > CLOCK_SKEW_MARGIN:
            event("a completed run carries on more than the margin after its rewrite")
            window = [
                one
                for one in versions
                if not one.is_latest
                and not one.is_delete_marker
                and one.last_modified is not None
                and run.rewritten_at <= one.last_modified < run.ended_at - CLOCK_SKEW_MARGIN
                and not (one.version_id or "").startswith("rewrite")
            ]
            if window:
                event("a noncurrent version in that window, which the strictly-older rule kept")
        if any(
            one.last_modified == run.rewritten_at and not (one.version_id or "").startswith("rewrite")
            for one in versions
        ):
            event("a version in the same second as a rewrite")
        if not run.rewrite_held:
            event("a rewrite the bucket no longer holds")
    if any(not run.completed for run in the_runs):
        event("a run that stopped")


@settings(max_examples=300, deadline=None)
@given(histories())
def test_after_the_same_removal_runs_again_status_counts_no_version_of_a_manifest_it_rewrote(
    history: tuple[tuple[Run, ...], list[tuple[datetime, bool]], bool],
) -> None:
    the_runs, others, publish_on_top = history
    versions, rewrite_ids, top = bucket_of(the_runs, others, publish_on_top)
    entries, scopes = records_of(the_runs, rewrite_ids)
    other_entries, other_scopes, other_versions = elsewhere(the_runs)
    describe(the_runs, versions)

    async def check() -> None:
        bucket = VersionsInMemory([*versions, *other_versions])
        every_entry, every_scope = [*entries, *other_entries], [*scopes, *other_scopes]
        taken = await swept(bucket, every_entry, every_scope)

        assert taken == await swept(VersionsInMemory([*versions, *other_versions]), entries, scopes), (
            "another request's or environment's records changed what the sweep takes"
        )
        current = {(one.key, one.version_id) for one in bucket.versions if one.is_latest}
        markers = {(one.key, one.version_id) for one in bucket.versions if one.is_delete_marker}
        assert not taken & current, "a current version"
        assert not taken & markers, "a delete marker"
        assert {key for key, _ in taken} <= {KEY}, "a version of another key"
        assert (KEY, rewrite_ids[len(the_runs) - 1]) not in taken, "the latest rewrite"
        assert (KEY, top) not in taken, "a publish after every run"

        await bucket.delete_versions([one for one in bucket.versions if (one.key, one.version_id) in taken])
        assert await manifest_versions_status_counts(bucket, every_entry, every_scope) == 0

    anyio.run(check)

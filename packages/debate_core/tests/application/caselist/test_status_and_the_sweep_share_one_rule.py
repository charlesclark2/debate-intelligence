"""What status counts of a rewritten manifest, the same removal run again clears (`v1-e30-t24`, item 2).

For a manifest a completed removal rewrote, `caselist status` counts a noncurrent version other than
the rewrite that is older than the run's completion less the clock-skew margin (`v1-e30-t15`). The
re-run's sweep took one only if it was strictly older than the rewrite (`v1-e30-t19`). So a version
stamped between the two was counted and never cleared: one in the same second as the rewrite, or a
publish from another machine while the run carried on. It needs a run that carries on more than
fifteen minutes after its own rewrite, which no removal so far has done (t19's PM review).

The fix widens the sweep to status's rule, by one predicate both call. It does not narrow status,
which cannot read a version's contents. These are the states the PM's notes name, built against
moto with the real planner, executor and status:

* a run that carries on more than fifteen minutes after its rewrite, with a later noncurrent version
  in that window;
* a version stamped in the same second as the rewrite;
* a later publish whose version becomes noncurrent, which is an ordinary later write and stays.

After the same removal runs again, status counts no manifest version. A run that stopped keeps the
sweep's strictly-older rule (status never counts a stopped run). The property over generated
listings is `test_one_rule_for_rewritten_manifests_property.py`.

The world is t15's and t19's: `RM-2026-01` removed the Seaside Cup round 5 affirmative, completed at
:data:`COMPLETED`, and rewrote `manifests/testcl26/2026-09-15.jsonl`. moto stamps what it writes
with the time the test runs, after the completion; a version the test needs older is backdated.
Every expected count is worked out by hand beside the step that causes it (working agreement 6).

No test imports a name this task adds, so each runs against the start commit's source too.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Final

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST

from debate_core.application.caselist.removal_residue import OlderVersions
from debate_core.application.ports.suppression import (
    ManifestRewriteRecord,
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    RemovalSelectorKind,
)

from .conftest import REQUEST, RemovalWorld
from .test_manifest_and_aggregate_residue import (
    LONG_BEFORE,
    NOT_REWRITTEN,
    backdate,
    current_bytes,
    of,
    put,
    remove,
    status,
    versions_of,
)
from .test_residue_clearing_gaps import (
    AN_OLD_BODY,
    COMPLETED,
    INSIDE_THE_RUN,
    REWRITTEN_KEY,
    rewrite_of,
)

pytestmark = pytest.mark.anyio

MARGIN: Final = timedelta(minutes=15)
LONG_RUN_REWRITE: Final = COMPLETED - timedelta(minutes=40)
"""A run that rewrote the manifest forty minutes before it completed: the inbox's zips were slow."""
IN_THE_WINDOW: Final = COMPLETED - timedelta(minutes=30)
"""After that rewrite, and more than the margin before the completion: status counts a version then."""


def one_manifest_version() -> tuple[OlderVersions, ...]:
    return (OlderVersions(role="manifest", versions=1),)


async def republish(world: RemovalWorld, scratch: Path) -> str:
    """This machine's manifest published again, as `caselist publish` would: the current version now."""
    same_bytes = scratch / "republished.jsonl"
    same_bytes.write_bytes(current_bytes(world, REWRITTEN_KEY))
    return str((await world.bucket.put_file(REWRITTEN_KEY, same_bytes)).version_id)


@pytest.fixture
async def removed(removal_world: RemovalWorld) -> RemovalWorld:
    """t19's world of the same name: `RM-2026-01` removed the round 5 affirmative, its rewrite put back
    inside the run, two minutes before its completion."""
    await remove(removal_world)
    (rewrite,) = versions_of(removal_world, REWRITTEN_KEY)
    backdate(removal_world, REWRITTEN_KEY, rewrite, INSIDE_THE_RUN)
    return removal_world


@pytest.fixture
async def long_run(removed: RemovalWorld) -> RemovalWorld:
    """`RM-2026-01`'s run, its rewrite put back forty minutes before its completion."""
    backdate(removed, REWRITTEN_KEY, rewrite_of(removed), LONG_RUN_REWRITE)
    return removed


class TestARunThatCarriesOnAfterItsRewrite:
    async def test_a_noncurrent_version_written_in_the_window_is_counted_and_then_cleared(
        self, long_run: RemovalWorld, tmp_path: Path
    ) -> None:
        """Another machine published the manifest ten minutes after the rewrite, and a publish since
        sits on top of it. Status counts it: older than the completion less fifteen minutes, and not
        the rewrite. The sweep kept it, as newer than the rewrite; now it takes it."""
        world = long_run
        rewrite = rewrite_of(world)
        during = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=IN_THE_WINDOW)
        current = await republish(world, tmp_path)
        assert versions_of(world, REWRITTEN_KEY) == [current, during, rewrite]
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == one_manifest_version()

        await remove(world)

        assert versions_of(world, REWRITTEN_KEY) == [current, rewrite]
        cleared = await status(world)
        assert of(cleared, SYNTHETIC_CASELIST).older_versions == ()
        assert cleared.in_sync

    async def test_a_version_in_the_same_second_as_the_rewrite_is_counted_and_then_cleared(
        self, long_run: RemovalWorld, tmp_path: Path
    ) -> None:
        """S3 states times to the second, so it cannot be told older or newer than the rewrite. It is
        older than the completion less the margin, and not the rewrite: status counts it."""
        world = long_run
        rewrite = rewrite_of(world)
        same_second = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_RUN_REWRITE)
        current = await republish(world, tmp_path)
        assert set(versions_of(world, REWRITTEN_KEY)) == {current, same_second, rewrite}
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == one_manifest_version()

        await remove(world)

        assert set(versions_of(world, REWRITTEN_KEY)) == {current, rewrite}
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == ()

    async def test_a_version_inside_the_margin_is_neither_counted_nor_taken(
        self, long_run: RemovalWorld, tmp_path: Path
    ) -> None:
        """Written ten minutes before the completion: it may be the next write by S3's clock, so status
        gives it the benefit of the margin, and the sweep, by the same rule, leaves it."""
        world = long_run
        inside = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=COMPLETED - timedelta(minutes=10))
        await republish(world, tmp_path)
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == ()

        await remove(world)

        assert inside in versions_of(world, REWRITTEN_KEY)

    async def test_a_later_publish_whose_version_becomes_noncurrent_stays(
        self, long_run: RemovalWorld, tmp_path: Path
    ) -> None:
        """Two publishes after the removal: the first is noncurrent under the second, and both are
        ordinary later writes. A version a day before the removal goes, so the re-run has work."""
        world = long_run
        rewrite = rewrite_of(world)
        old = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        first = await republish(world, tmp_path)
        second = await republish(world, tmp_path)
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == one_manifest_version()

        await remove(world)

        assert versions_of(world, REWRITTEN_KEY) == [second, first, rewrite]
        assert old not in versions_of(world, REWRITTEN_KEY)
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == ()


class TestARunThatStopped:
    """Status compares nothing with a run that stopped, so the sweep keeps its own rule for one:
    strictly older than that run's rewrite (`v1-e30-t19`), which the scope records only once the
    rewrite's purge is done."""

    async def test_its_rewrites_older_versions_go_and_one_after_its_rewrite_stays(
        self,
        removed: RemovalWorld,
        tmp_path: Path,
    ) -> None:
        """A run of the same request that stopped an hour before the one that completed, after it had
        rewritten the week of 2026-09-01. One version a day before that rewrite, one half an hour
        after it, and a publish on top of both."""
        world = removed
        (published,) = versions_of(world, NOT_REWRITTEN)
        stopped_at = COMPLETED - timedelta(hours=2)
        backdate(world, NOT_REWRITTEN, published, stopped_at - timedelta(hours=1))
        older = put(world, NOT_REWRITTEN, AN_OLD_BODY, written=LONG_BEFORE)
        after_it = put(world, NOT_REWRITTEN, AN_OLD_BODY, written=stopped_at - timedelta(minutes=30))
        same_bytes = tmp_path / "republished.jsonl"
        same_bytes.write_bytes(current_bytes(world, NOT_REWRITTEN))
        await world.bucket.put_file(NOT_REWRITTEN, same_bytes)
        stopped = RemovalLogEntry(
            kind=RemovalLogKind.REMOVAL,
            recorded_at=stopped_at,
            request_id=REQUEST,
            reason=ReasonCode.REQUESTED_BY_TEAM,
            environment="dev",
            outcome=RemovalOutcome.INCOMPLETE,
            selector=RemovalSelectorKind.SOURCE,
            error_code="STORE_UNAVAILABLE",
        )
        await world.removal_log().append(
            [stopped],
            scopes=[
                RemovalScopeEntry(
                    recorded_at=stopped_at,
                    request_id=REQUEST,
                    environment="dev",
                    caselists=(SYNTHETIC_CASELIST,),
                    manifest_rewrites=(ManifestRewriteRecord(key=NOT_REWRITTEN, version_id=published),),
                )
            ],
        )
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == ()

        await remove(world)

        assert older not in versions_of(world, NOT_REWRITTEN)
        assert {after_it, published} <= set(versions_of(world, NOT_REWRITTEN))
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == ()

"""A removal reaches the run-state bundle, and purges its old versions only once it confirms its rewrite.

`v1-e40-t04`, ADR-0020 (3), "Removal covers it", and the PM's ruling of 2026-10-23: `caselist remove`,
under the removal credential, purges the noncurrent versions of the objects under
`manifests/_run-state/` after its rewrite of the bundle is confirmed in the bucket. Nothing else
deletes, and the run's role cannot (its Terraform test is `the_run_role_never_deletes`).

The bundle holds the manifests and the database, so before a removal every version of it names the
removed file. After it, no version may: the bucket keeps exactly one, the rewrite, and that one does
not hold the file's digest anywhere in its bytes, the database's free pages included.
"""

from __future__ import annotations

import gzip
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import WEEKS, digest_of

import debate_core.integrations.s3 as s3_package
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.run_state import RUN_STATE_BUNDLE_KEY, BundleSave, RunState

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
REMOVED: Final = digest_of("wiki")
"""Cedar Hollow ZaLu's round 2 file, disclosed once, in 09-01 and every week after."""


@pytest.fixture
def a_week_on(world: World, tmp_path: Path) -> Iterator[World]:
    """Seeded from the Mac, then a cloud run's week: the bucket holds several versions of the bundle."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)
    world.use(tmp_path / "cloud")
    assert world.pull()["exit_code"] == ExitCode.OK
    assert len(world.versions(RUN_STATE_BUNDLE_KEY)) >= 2
    world.monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal")
    world.use(tmp_path / "the-macs-copy")
    yield world


def remove(world: World) -> dict[str, Any]:
    return world.run(
        "caselist", "remove", "--source", REMOVED, "--reason", "REQUESTED_BY_TEAM", "--request", "RM-2026-03",
        "--execute",
    )  # fmt: skip


def bundle_bytes(world: World, version_id: str) -> bytes:
    """One version of the bundle, unzipped: the tar of the manifests and the database, as bytes."""
    body = world.client.get_object(Bucket=world.bucket, Key=RUN_STATE_BUNDLE_KEY, VersionId=version_id)[
        "Body"
    ]
    return gzip.decompress(body.read())


def test_before_a_removal_every_version_of_the_bundle_names_the_file(a_week_on: World) -> None:
    """The premise: what the removal has to reach."""
    for version in a_week_on.versions(RUN_STATE_BUNDLE_KEY):
        assert REMOVED.encode() in bundle_bytes(a_week_on, version["VersionId"])


def test_a_removal_leaves_one_version_of_the_bundle_and_it_does_not_hold_the_removed_file(
    a_week_on: World,
) -> None:
    removed = remove(a_week_on)

    assert removed["exit_code"] == ExitCode.OK, removed
    versions = a_week_on.versions(RUN_STATE_BUNDLE_KEY)
    assert len(versions) == 1, "every noncurrent version purged, and no delete marker left"
    assert "DeleteMarkers" not in a_week_on.client.list_object_versions(
        Bucket=a_week_on.bucket, Prefix=RUN_STATE_BUNDLE_KEY
    )
    assert REMOVED.encode() not in bundle_bytes(a_week_on, versions[0]["VersionId"])
    assert a_week_on.lock()["state"] == "free"


class Recorder:
    """Every write any client of the command sends to the bundle's key, in order: put or delete."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        build = s3_package.build_s3_client

        def built(**arguments: Any) -> Any:
            client = build(**arguments)

            def record(params: dict[str, Any], model: Any, **_: object) -> None:
                name = str(model.name)
                keys = [params.get("Key")] + [
                    one.get("Key") for one in params.get("Delete", {}).get("Objects", [])
                ]
                if RUN_STATE_BUNDLE_KEY in keys and name in {"PutObject", "DeleteObject", "DeleteObjects"}:
                    self.calls.append("delete" if name.startswith("Delete") else "put")

            client.meta.events.register("before-parameter-build.s3", record)
            return client

        monkeypatch.setattr(s3_package, "build_s3_client", built)


def test_the_purge_comes_after_the_rewrite_is_written(
    a_week_on: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    recorder.install(monkeypatch)

    assert remove(a_week_on)["exit_code"] == ExitCode.OK

    assert recorder.calls[:1] == ["put"], recorder.calls
    assert "delete" in recorder.calls
    assert recorder.calls.index("delete") > max(i for i, call in enumerate(recorder.calls) if call == "put")


def test_a_rewrite_the_bucket_does_not_confirm_purges_nothing_and_the_removal_is_incomplete(
    a_week_on: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unconfirmed(self: RunState) -> BundleSave:
        return BundleSave(
            saved=False, reason="not confirmed: the bucket holds another bundle than was written"
        )

    monkeypatch.setattr(RunState, "save_bundle", unconfirmed)
    before = a_week_on.versions(RUN_STATE_BUNDLE_KEY)

    incomplete = remove(a_week_on)

    assert incomplete["exit_code"] != ExitCode.OK, incomplete
    assert incomplete["error"]["code"] == "REMOVAL_INCOMPLETE", incomplete["error"]
    assert a_week_on.versions(RUN_STATE_BUNDLE_KEY) == before, "nothing purged"
    assert a_week_on.lock()["state"] == "free"

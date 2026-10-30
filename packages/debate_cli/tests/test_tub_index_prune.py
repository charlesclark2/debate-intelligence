"""`debate-research tub index prune`, run the way an operator runs it (`v1-e39-t15`).

Through Typer's `CliRunner` against the real application and composition root: the real S3 adapters
over moto's versioned bucket, the everyday profile reading `current.json` and the takedown profile
listing and deleting, each signed in as its Identity Center role (`tests/fixtures/identity_center_roles.py`),
in bucket mode with the bucket's run lock, as dev has been since the cutover. Each test writes its
indexes the way `tub index publish` does and keeps the version id of every write; what the command
must delete and keep is written down from those writes.

Nothing here reaches AWS: moto answers botocore in-process and sockets are disabled.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.run_lock import RUN_LOCK_KEY, BucketWriteGuard, TakenLock
from debate_core.domain.search_index import (
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SEARCH_INDEX_PREFIX,
    SearchIndexPointer,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET: Final = "debate-dev-evidence-moto"
PROFILE: Final = "debate-dev-evidence"
REMOVAL_PROFILE: Final = "debate-dev-evidence-removal"

FIRST: Final = "aaaaaaaaaaaaaaaa"
SECOND: Final = "bbbbbbbbbbbbbbbb"
CURRENT: Final = "cccccccccccccccc"
NEVER_UPLOADED: Final = "dddddddddddddddd"
LATER: Final = "eeeeeeeeeeeeeeee"

FRIDAY: Final = datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
WEDNESDAY_NOON_IN_CHICAGO: Final = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)

Written = tuple[str, str]
"""One write: its key and the version id S3 gave it."""


@dataclass
class Clock:
    now: datetime = FRIDAY

    def __call__(self) -> datetime:
        return self.now


@dataclass
class World:
    """The moto bucket, written to as `tub index publish` writes, every version id kept."""

    client: S3Client
    clock: Clock
    monkeypatch: pytest.MonkeyPatch
    files: dict[str, set[Written]] = field(default_factory=dict[str, set[Written]])
    pointers: dict[str, Written] = field(default_factory=dict[str, Written])

    def put(self, key: str, body: bytes = b"index bytes") -> Written:
        return key, self.client.put_object(Bucket=BUCKET, Key=key, Body=body)["VersionId"]

    def publish(self, index_id: str) -> None:
        for name in (SEARCH_INDEX_MANIFEST_NAME, SEARCH_INDEX_GZIP_NAME):
            self.files.setdefault(index_id, set()).add(self.put(f"{SEARCH_INDEX_PREFIX}{index_id}/{name}"))
        self.point_at(index_id)

    def point_at(self, index_id: str) -> None:
        self.pointers[index_id] = self.put(SEARCH_INDEX_POINTER_KEY, pointer(index_id).to_json_bytes())

    def delete(self, key: str) -> Written:
        return key, self.client.delete_object(Bucket=BUCKET, Key=key)["VersionId"]

    def listing(self) -> set[Written]:
        listed = self.client.list_object_versions(Bucket=BUCKET, Prefix=SEARCH_INDEX_PREFIX)
        return {
            (str(one.get("Key")), str(one.get("VersionId")))
            for one in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]
        }

    def lock(self) -> dict[str, Any]:
        return json.loads(self.client.get_object(Bucket=BUCKET, Key=RUN_LOCK_KEY)["Body"].read())

    def lock_holders(self) -> list[str]:
        """The command of every version of the lock object a holder wrote."""
        listed = self.client.list_object_versions(Bucket=BUCKET, Prefix=RUN_LOCK_KEY).get("Versions", [])
        bodies = [
            json.loads(
                self.client.get_object(Bucket=BUCKET, Key=RUN_LOCK_KEY, VersionId=str(one.get("VersionId")))[
                    "Body"
                ].read()
            )
            for one in listed
        ]
        return [body["holder"]["command"] for body in bodies if body.get("holder")]

    def invoke(self, *arguments: str) -> Result:
        return runner.invoke(create_app(), ["tub", "index", "prune", *arguments])

    def run(self, *arguments: str) -> dict[str, Any]:
        """The command with `--json`: its envelope, with the exit code on it."""
        result = self.invoke(*arguments, "--json")
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert lines, f"no JSON on stdout: {result.output!r} {result.exception!r}"
        envelope: dict[str, Any] = json.loads(lines[-1])
        envelope["exit_code"] = result.exit_code
        return envelope

    def dry_run(self) -> str:
        """The dry run's confirmation code, after checking it refused nothing."""
        planned = self.run("--env", "dev")
        assert planned["exit_code"] == ExitCode.OK, planned
        return str(planned["data"]["confirmation"])


def pointer(index_id: str) -> SearchIndexPointer:
    return SearchIndexPointer(
        format_version=1,
        index_id=index_id,
        manifest_key=f"{SEARCH_INDEX_PREFIX}{index_id}/{SEARCH_INDEX_MANIFEST_NAME}",
        manifest_sha256="1" * 64,
        object_key=f"{SEARCH_INDEX_PREFIX}{index_id}/{SEARCH_INDEX_GZIP_NAME}",
        object_sha256="2" * 64,
        sqlite_sha256="3" * 64,
    )


def free_lock() -> bytes:
    """The run lock as the seed leaves it and every holder releases it."""
    return json.dumps(
        {
            "format_version": 1,
            "home_environment": "dev",
            "state": "free",
            "holder": None,
            "acquired_at": None,
            "renewed_at": None,
            "lease_expires_at": None,
            "took_over_from": None,
        }
    ).encode()


def held_lock(now: datetime) -> bytes:
    """Another runner's live lease: the cloud run, ten minutes from its expiry."""

    def at(moment: datetime) -> str:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    return json.dumps(
        {
            "format_version": 1,
            "home_environment": "dev",
            "state": "held",
            "holder": {
                "kind": "cloud",
                "run_id": "20261030T110005Z",
                "task": None,
                "command": "caselist pull",
            },
            "acquired_at": at(now - timedelta(minutes=20)),
            "renewed_at": at(now - timedelta(minutes=20)),
            "lease_expires_at": at(now + timedelta(minutes=10)),
            "took_over_from": None,
        }
    ).encode()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    """A dev installation in bucket mode, both evidence profiles signed in as their roles."""
    for name in list(os.environ):
        if name.startswith(("DEBATE_", "AWS_")):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / "aws-config"
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (PROFILE, REMOVAL_PROFILE)),
        encoding="utf-8",
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{PROFILE}]\naws_access_key_id = testing\naws_secret_access_key = testing\n", encoding="utf-8"
    )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{PROFILE}"\n',
        encoding="utf-8",
    )
    (profiles / "prod.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "prod-data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{PROFILE}"\n',
        encoding="utf-8",
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
        "DEBATE_PROFILE_DIR": str(profiles),
        "DEBATE_ENV": "dev",
        "DEBATE_CASELIST__RUN_STATE": "bucket",
        "DEBATE_REMOVAL_PROFILE": REMOVAL_PROFILE,
    }.items():
        monkeypatch.setenv(name, value)
    clock = Clock()
    monkeypatch.setattr("debate_cli.container._utc_now", clock)
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        client.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        client.put_object(Bucket=BUCKET, Key=RUN_LOCK_KEY, Body=free_lock())
        sign_in(credentials, {PROFILE: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE})
        yield World(client=client, clock=clock, monkeypatch=monkeypatch)


@pytest.fixture
def three_published(world: World) -> World:
    """Three indexes published in turn, the first's gzip object deleted by hand (a delete marker)."""
    world.publish(FIRST)
    world.publish(SECOND)
    world.files[FIRST].add(world.delete(f"{SEARCH_INDEX_PREFIX}{FIRST}/{SEARCH_INDEX_GZIP_NAME}"))
    world.publish(CURRENT)
    return world


def superseded(world: World) -> set[Written]:
    return world.files[FIRST] | world.files[SECOND] | {world.pointers[FIRST], world.pointers[SECOND]}


def current(world: World) -> set[Written]:
    return world.files[CURRENT] | {world.pointers[CURRENT]}


def listed_for_deletion(envelope: dict[str, Any]) -> set[Written]:
    return {(one["key"], one["version_id"]) for one in envelope["data"]["delete"]}


# ------------------------------------------------------------------------------------------------
# The dry run
# ------------------------------------------------------------------------------------------------


def test_tub_index_prune_dry_run_lists_every_superseded_version_and_keeps_the_current(
    three_published: World,
) -> None:
    before = three_published.listing()

    planned = three_published.run("--env", "dev")

    assert planned["exit_code"] == ExitCode.OK, planned
    data = planned["data"]
    assert listed_for_deletion(planned) == superseded(three_published)
    assert data["applied"] is False
    assert data["index_id"] == CURRENT
    assert data["keeps"] == f"{SEARCH_INDEX_PREFIX}{CURRENT}/"
    assert data["counts"] == {
        "versions": 6,
        "delete_markers": 1,
        "keys": 5,
        "superseded_directories": 2,
        "kept": 3,
    }
    assert three_published.listing() == before
    assert three_published.lock_holders() == [], "a dry run takes no lock"


def test_tub_index_prune_dry_run_prints_counts_short_prefixes_and_the_code_but_no_key(
    three_published: World,
) -> None:
    code = three_published.dry_run()

    printed = three_published.invoke("--env", "dev")

    assert printed.exit_code == ExitCode.OK, printed.output
    flat = " ".join(printed.output.split())
    assert f"--execute --confirm {code}" in flat
    assert "6 version(s) and 1 delete marker(s) of 5 key(s)" in flat
    for name in (SEARCH_INDEX_MANIFEST_NAME, SEARCH_INDEX_GZIP_NAME, SEARCH_INDEX_PREFIX):
        assert name not in printed.output, f"a key reached the console: {name}"
    for index_id in (FIRST, SECOND, CURRENT):
        assert index_id[:8] in printed.output


def test_tub_index_prune_refuses_a_pointer_the_listing_does_not_hold(three_published: World) -> None:
    three_published.point_at(NEVER_UPLOADED)
    before = three_published.listing()

    refused = three_published.run("--env", "dev")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "POINTER_NOT_IN_LISTING"
    assert three_published.listing() == before


def test_tub_index_prune_refuses_an_env_that_is_not_debate_env(three_published: World) -> None:
    refused = three_published.run("--env", "prod")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "ENVIRONMENT_MISMATCH"


def test_tub_index_prune_needs_the_takedown_profile(three_published: World) -> None:
    three_published.monkeypatch.delenv("DEBATE_REMOVAL_PROFILE")

    refused = three_published.run("--env", "dev")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "TAKEDOWN_NOT_CONFIGURED"
    assert "DEBATE_REMOVAL_PROFILE" in refused["error"]["message"]


def test_tub_index_prune_refuses_the_everyday_profile_named_as_the_takedown(three_published: World) -> None:
    three_published.monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", PROFILE)

    refused = three_published.run("--env", "dev")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "NOT_THE_TAKEDOWN_ROLE"


# ------------------------------------------------------------------------------------------------
# --execute
# ------------------------------------------------------------------------------------------------


def test_tub_index_prune_execute_with_the_code_deletes_exactly_what_the_dry_run_listed(
    three_published: World,
) -> None:
    code = three_published.dry_run()

    pruned = three_published.run("--env", "dev", "--execute", "--confirm", code)

    assert pruned["exit_code"] == ExitCode.OK, pruned
    assert pruned["data"]["applied"] is True
    assert pruned["data"]["deleted"] == 7
    assert listed_for_deletion(pruned) == superseded(three_published)
    assert three_published.listing() == current(three_published)
    again = three_published.run("--env", "dev")
    assert again["data"]["delete"] == []
    assert again["data"]["index_id"] == CURRENT


def test_tub_index_prune_execute_holds_the_run_lock_and_releases_it(three_published: World) -> None:
    code = three_published.dry_run()

    assert three_published.run("--env", "dev", "--execute", "--confirm", code)["exit_code"] == ExitCode.OK

    assert set(three_published.lock_holders()) == {"tub index prune"}
    assert three_published.lock()["state"] == "free"


@pytest.mark.parametrize("confirmation", [None, "000000000000"])
def test_tub_index_prune_execute_without_the_dry_runs_code_refuses_and_deletes_nothing(
    three_published: World, confirmation: str | None
) -> None:
    before = three_published.listing()
    arguments = ["--env", "dev", "--execute", *(["--confirm", confirmation] if confirmation else [])]

    refused = three_published.run(*arguments)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "CONFIRMATION_MISMATCH"
    assert three_published.listing() == before


def test_tub_index_prune_execute_refuses_when_the_pointer_moved_since_the_dry_run(
    three_published: World,
) -> None:
    code = three_published.dry_run()
    three_published.publish(LATER)
    before = three_published.listing()

    refused = three_published.run("--env", "dev", "--execute", "--confirm", code)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "CONFIRMATION_MISMATCH"
    assert three_published.listing() == before


def test_tub_index_prune_execute_refuses_when_the_pointer_moves_while_it_waits_for_the_lock(
    three_published: World,
) -> None:
    """A publish that lands after the command has read the pointer and before it holds the lock: the
    re-read inside the lock is the only thing that sees it."""
    code = three_published.dry_run()
    taking = BucketWriteGuard.held

    @contextmanager
    def held_after_a_publish(guard: BucketWriteGuard, command: str) -> Generator[TakenLock | None]:
        three_published.publish(LATER)
        with taking(guard, command) as taken:
            yield taken

    three_published.monkeypatch.setattr(BucketWriteGuard, "held", held_after_a_publish)
    listed_before_the_publish = three_published.listing()

    refused = three_published.run("--env", "dev", "--execute", "--confirm", code)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "SEARCH_INDEX_POINTER_MOVED"
    assert listed_before_the_publish <= three_published.listing(), "nothing was deleted"
    assert three_published.lock()["state"] == "free"


def test_tub_index_prune_execute_refuses_on_a_wednesday_in_chicago(three_published: World) -> None:
    code = three_published.dry_run()
    three_published.clock.now = WEDNESDAY_NOON_IN_CHICAGO
    before = three_published.listing()

    refused = three_published.run("--env", "dev", "--execute", "--confirm", code)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "PRUNE_ON_CLOUD_RUN_DAY"
    assert three_published.listing() == before
    assert three_published.lock_holders() == [], "refused before it takes the lock"


def test_tub_index_prune_dry_run_still_runs_on_a_wednesday(three_published: World) -> None:
    three_published.clock.now = WEDNESDAY_NOON_IN_CHICAGO

    assert three_published.run("--env", "dev")["exit_code"] == ExitCode.OK


def test_tub_index_prune_execute_refuses_while_another_runner_holds_the_lock(three_published: World) -> None:
    code = three_published.dry_run()
    three_published.client.put_object(Bucket=BUCKET, Key=RUN_LOCK_KEY, Body=held_lock(FRIDAY))
    before = three_published.listing()

    refused = three_published.run("--env", "dev", "--execute", "--confirm", code)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RUN_LOCK_HELD"
    assert three_published.listing() == before


def test_tub_index_prune_execute_in_prod_needs_confirm_prod(
    three_published: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")
    before = three_published.listing()

    refused = three_published.run("--env", "prod", "--execute", "--confirm", "000000000000")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert three_published.listing() == before

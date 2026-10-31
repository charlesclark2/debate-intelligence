"""A cloud run's missing-session reasons name its task role, not `aws sso login` (`v1-e40-t28`).

Every record reason a run writes for a session that is not usable ends with the S3 adapter's login
hint, and it was `aws sso login …` whatever ran the command. The composition root now gives the S3
adapters a hint for what runs it:

* **The cloud run**: bucket mode (`caselist.run_state = "bucket"` with a bucket named) inside an ECS
  task, which ECS marks with `ECS_CONTAINER_METADATA_URI_V4` in every container it starts, as the run
  lock already tells its holder (`v1-e40-t04`). Its hint is the login banner's cloud fix
  (`v1-e40-t22`): the PM looks into the task role, `caselist-cloud-run.md`'s "A run that found no AWS
  session".
* **Anything else** keeps the adapters' own `aws sso login` hint: local mode, and a bucket-mode command
  an operator runs by hand on the Mac, where an SSO session is what is missing.

The takedown profile's adapters keep theirs everywhere: `DEBATE_REMOVAL_PROFILE` is an SSO profile an
operator signs in to. The adapters' own tests are
`packages/debate_core/tests/integrations/s3/test_s3_login_hint_for_a_bucket_mode_cloud_run.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from botocore.exceptions import NoCredentialsError
from tests.fixtures.parse_pipeline.build_parse_world import WEEKS

from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.settings import load_settings
from debate_core.integrations.s3 import S3EvidenceObjectStore, S3EvidenceVersionStore, mapped_s3_errors
from debate_core.integrations.s3.run_lock_object import S3LockObject
from debate_core.integrations.s3.version_directories import S3VersionDirectories

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)

THE_TASK_ROLES_HINT: Final = (
    "the PM looks into the cloud run's task role, which gave the run no AWS session "
    '(caselist-cloud-run.md, "A run that found no AWS session"); never a login and a publish from the '
    "operator's Mac"
)
THE_PROFILES_LOGIN: Final = "aws sso login --profile debate-dev-evidence"
"""The world's everyday profile, as the adapters name it: as before, word for word."""

ECS_METADATA: Final = "ECS_CONTAINER_METADATA_URI_V4"
A_TASKS_METADATA: Final = "http://169.254.170.2/v4/0a1b2c3d4e5f4a5b8c9d0e1f2a3b4c5d-1234567890"
EVERYDAY: Final = "storage.s3.aws_profile"
TAKEDOWN: Final = "DEBATE_REMOVAL_PROFILE"

ADAPTERS: Final = (S3EvidenceObjectStore, S3EvidenceVersionStore, S3VersionDirectories, S3LockObject)


@dataclass(frozen=True)
class Built:
    """One S3 adapter the container built: its class, the setting its profile came from, its hint."""

    adapter: str
    profile_setting: str | None
    login_hint: str | None


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Built]]:
    """Every S3 adapter built while the test runs, as its constructor was called."""
    seen: list[Built] = []
    for adapter in ADAPTERS:
        original = adapter.__init__

        def recording(self: object, *args: Any, _original: Any = original, **kwargs: Any) -> None:
            seen.append(Built(type(self).__name__, kwargs.get("profile_setting"), kwargs.get("login_hint")))
            _original(self, *args, **kwargs)

        monkeypatch.setattr(adapter, "__init__", recording)
    yield seen


def runs_as(world: World, *, run_state: str, in_an_ecs_task: bool) -> None:
    world.mode(run_state)
    if in_an_ecs_task:
        world.monkeypatch.setenv(ECS_METADATA, A_TASKS_METADATA)
        # As the run task's definition sets it: no profile, so the task role signs.
        world.monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", "")
    else:
        world.monkeypatch.delenv(ECS_METADATA, raising=False)


# ------------------------------------------------------------------------------------------------
# Which hint the composition root gives
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("run_state", "in_an_ecs_task", "hint"),
    [
        ("bucket", True, THE_TASK_ROLES_HINT),
        ("bucket", False, None),
        ("local", True, None),
        ("local", False, None),
    ],
    ids=["the-cloud-run", "bucket-mode-by-hand-on-the-mac", "local-mode-in-a-task", "local-mode"],
)
def test_every_everyday_s3_adapter_gets_the_hint_for_what_runs_the_command(
    world: World, built: list[Built], run_state: str, in_an_ecs_task: bool, hint: str | None
) -> None:
    runs_as(world, run_state=run_state, in_an_ecs_task=in_an_ecs_task)
    world.monkeypatch.setenv(TAKEDOWN, "debate-dev-evidence-removal")
    container = ServiceContainer(settings_loader=load_settings)

    container.caselist_status()
    container.caselist_removal()
    container.version_retention(bucket=True)
    container.evidence_sync()
    container.bucket_run_lock()
    container.takedown_access()

    everyday = {one for one in built if one.profile_setting == EVERYDAY}
    assert {one.adapter for one in everyday} == {adapter.__name__ for adapter in ADAPTERS}
    assert {one.login_hint for one in everyday} == {hint}
    takedown = {one for one in built if one.profile_setting == TAKEDOWN}
    assert {one.adapter for one in takedown} == {"S3EvidenceObjectStore", "S3EvidenceVersionStore"}
    assert {one.login_hint for one in takedown} == {None}


# ------------------------------------------------------------------------------------------------
# What a run's record says when its session goes
# ------------------------------------------------------------------------------------------------


STATE_FILES: Final = "reports/sync/state/"


def no_session_for_writes(*, but_the_state_files: bool) -> Any:
    """The bucket's uploads find no credentials, through the adapter's own error mapping: every one, or
    every one but the run's state files, so that the run gets as far as its publish."""
    original = S3EvidenceObjectStore.put_file

    async def put_file(self: S3EvidenceObjectStore, key: str, source: Path) -> Any:
        if but_the_state_files and key.startswith(STATE_FILES):
            return await original(self, key, source)
        with mapped_s3_errors(self._call("PutObject", key)):  # pyright: ignore[reportPrivateUsage]
            raise NoCredentialsError

    return put_file


def everything_it_said(pulled: dict[str, Any], record: dict[str, Any], details: dict[str, Any]) -> list[str]:
    """Every sentence the run printed or kept: the envelope's error, the record's and details' reasons
    and hints."""
    error = pulled.get("error") or {}
    said = [
        error.get("message"),
        error.get("hint"),
        details.get("hint"),
        *(one.get("reason") for one in record["stages"]),
        *(one.get("reason") for one in details.get("stages", [])),
        *(one.get("hint") for one in details.get("stages", [])),
    ]
    return [one for one in said if one]


def quoting_the_adapter(pulled: dict[str, Any], record: dict[str, Any], details: dict[str, Any]) -> list[str]:
    """What quotes the S3 adapter's error for a session that is not usable, or is its hint alone."""
    hints = {(pulled.get("error") or {}).get("hint"), details.get("hint")}
    return [
        one
        for one in everything_it_said(pulled, record, details)
        if "the AWS session for" in one or (one in hints and "AWS" in one)
    ]


@pytest.mark.parametrize(
    ("in_an_ecs_task", "hint", "never"),
    [(True, THE_TASK_ROLES_HINT, "aws sso login"), (False, THE_PROFILES_LOGIN, "task role")],
    ids=["the-cloud-run", "bucket-mode-by-hand-on-the-mac"],
)
@pytest.mark.parametrize(
    ("but_the_state_files", "publish"),
    [(False, None), (True, "pending")],
    ids=["at-the-first-state-file", "at-the-publish"],
)
def test_a_bucket_mode_pull_whose_session_went_names_the_hint_for_what_ran_it(
    world: World, in_an_ecs_task: bool, hint: str, never: str, but_the_state_files: bool, publish: str | None
) -> None:
    """Weeks one and two pulled on "the Mac" and seeded; week three pulled in bucket mode, where the
    bucket's uploads find no session. With every upload refused the run stops at its first state file,
    before any stage; with the state files let through it gets to its publish, which waits for a
    session. Either way, every sentence it prints or keeps about the session names the hint for what
    ran the pull, and never the other's."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)
    runs_as(world, run_state="bucket", in_an_ecs_task=in_an_ecs_task)
    world.monkeypatch.setattr(
        S3EvidenceObjectStore, "put_file", no_session_for_writes(but_the_state_files=but_the_state_files)
    )

    pulled = world.pull()

    record, details = world.last_record()
    stages = {one["stage"]: one["outcome"] for one in record["stages"]}
    assert stages.get("publish") == publish, (pulled.get("error"), record)
    quoting = quoting_the_adapter(pulled, record, details)
    assert quoting, (pulled.get("error"), record, details)
    assert all(hint in one for one in quoting), quoting
    said = everything_it_said(pulled, record, details)
    assert all(never not in one for one in said), said

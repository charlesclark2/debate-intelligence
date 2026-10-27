"""Start one backfile import as a one-off cloud task, on the weekly run's task definition (`v1-e40-t09`).

The four backfile complete archives do not fit the operator's machine (`v1-e34-t34`), so each is
imported by a Fargate task: the run's own task definition, started by hand with its command
overridden to `v1-e34-t34`'s `caselist backfile-import --caselist <slug>` (the PM's ruling of
2026-10-27, Q1). Never on a schedule. Run by the operator, on the Mac, from the checkout
(docs/runbooks/caselist-cloud-run.md, "Backfile imports"):

    python3 -I ops/caselist_run/start_backfile_import.py --env dev --caselist hspolicy25 \\
        --subnets subnet-aaa,subnet-bbb --security-group sg-ccc --dry-run

What it does, in order, and what stops it:

1. **The no-import window.** Tuesday 06:00 to Thursday 00:00 America/Chicago, `v1-e34-t34`'s window
   around the weekly run: inside it, nothing is started. The task asks again itself, at its start
   and before each locked step.
2. **The bucket's run lock**, `reports/sync/run-lock.json`, read with one `GetObject` as the everyday
   evidence profile (`debate-<env>-evidence`, named by `config/profiles/<env>.toml`): while a run
   holds it, nothing is started (the PM's ruling Q2). A lease that ran out more than the skew margin
   ago is not held: the task's first locked step takes it over, as any runner does
   (:mod:`debate_core.application.caselist.run_lock`). A lock that is missing, unreadable, homed in
   another environment or moved away also stops it.
3. **The revision.** The schedule's target cannot be read from the deployer's profile (it holds no
   `scheduler:GetSchedule`), so the revision is the run family's newest ACTIVE one, or the one
   `--task-definition` names, which the runbook reads from Terraform's output. Either must be the
   run's family, run as the run role, with one container named `run` and an image pinned by digest.
   The revision and the digest are printed, for the runbook to compare with Terraform's.
4. **Start it**, as the run deployer (`debate-<env>-caselist-run-deployer`): `ecs run-task` with the
   command `--json caselist backfile-import --caselist <slug>`, and `--execute` unless `--dry-run`.
   The container keeps the run's entry point, so its 6-hour deadline holds, and the task is the run
   role's, with no role override. `startedBy` says `backfile-import`.
5. **Print** the task's id and the two commands that watch it.

The budget (one complete archive a day, in the bucket's backfile ledger), the free-space check and the
token are the task's own: the command it starts refuses each before any download. A rebuild after a
whole-file removal is this same command, which then downloads nothing and spends no budget.

Exit `0` when the task started, `1` when it was refused (the line beginning `REFUSED:` says why;
nothing was started), `2` for arguments it cannot use.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
REGION = "us-east-1"
LOCK_KEY = "reports/sync/run-lock.json"
CONTAINER = "run"
STARTED_BY = "backfile-import"
SLUG = re.compile(r"^[a-z]+[0-9]{2}$")
DIGEST = re.compile(r"@(sha256:[0-9a-f]{64})$")

WINDOW_ZONE = ZoneInfo("America/Chicago")
TUESDAY, WEDNESDAY, THURSDAY = 1, 2, 3
WINDOW_OPENS_AT_HOUR = 6
CLOCK_SKEW_MARGIN = timedelta(minutes=5)
"""`run_lock.CLOCK_SKEW_MARGIN`: how far past its expiry a lease must be before it is not held."""

Aws = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


class Refused(Exception):
    """Nothing was started. The message says why."""


@dataclass(frozen=True)
class TaskDefinition:
    arn: str
    revision: int
    digest: str
    ephemeral_gib: int | None


# ------------------------------------------------------------------------------------------------
# The window
# ------------------------------------------------------------------------------------------------


def in_no_import_window(now: datetime) -> bool:
    """Tuesday 06:00 to Thursday 00:00, America/Chicago: `backfile_import.in_no_import_window`."""
    local = now.astimezone(WINDOW_ZONE)
    if local.weekday() == TUESDAY:
        return local.hour >= WINDOW_OPENS_AT_HOUR
    return local.weekday() == WEDNESDAY


def window_closes(now: datetime) -> datetime:
    """The Thursday 00:00 America/Chicago after `now`."""
    local = now.astimezone(WINDOW_ZONE)
    days = (THURSDAY - local.weekday()) % 7 or 7
    thursday = (local + timedelta(days=days)).date()
    return datetime(thursday.year, thursday.month, thursday.day, tzinfo=WINDOW_ZONE)


def window_refusal(now: datetime) -> str | None:
    if not in_no_import_window(now):
        return None
    return (
        "inside the no-import window, Tuesday 06:00 to Thursday 00:00 America/Chicago, around the "
        f"weekly run; it closes at {window_closes(now).isoformat()}"
    )


# ------------------------------------------------------------------------------------------------
# The run lock
# ------------------------------------------------------------------------------------------------


def evidence_store(environment: str) -> tuple[str, str]:
    """The bucket and the everyday profile, from the committed `config/profiles/<env>.toml`."""
    text = (REPO_ROOT / "config" / "profiles" / f"{environment}.toml").read_text(encoding="utf-8")
    section = re.search(r"^\[storage\.s3\]\n(.*?)(?=^\[|\Z)", text, flags=re.M | re.S)
    found = {
        name: re.search(rf'^{name}\s*=\s*"([^"]+)"', section.group(1), flags=re.M) if section else None
        for name in ("bucket", "aws_profile")
    }
    if found["bucket"] is None or found["aws_profile"] is None:
        raise Refused(f"config/profiles/{environment}.toml names no [storage.s3] bucket and aws_profile")
    return found["bucket"].group(1), found["aws_profile"].group(1)


def read_lock(aws: Aws, environment: str) -> dict[str, object]:
    bucket, profile = evidence_store(environment)
    with tempfile.TemporaryDirectory(prefix="backfile-import-lock-") as scratch:
        body = Path(scratch) / "run-lock.json"
        ran = aws(
            [
                "s3api", "get-object", "--profile", profile, "--region", REGION,
                "--bucket", bucket, "--key", LOCK_KEY, str(body),
            ]
        )  # fmt: skip
        if ran.returncode != 0:
            raise Refused(
                f"could not read the bucket's run lock as {profile} ({_last_line(ran.stderr)}); sign in "
                f"with `aws sso login --profile {profile}`. A bucket with no lock is not seeded"
            )
        try:
            lock = json.loads(body.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise Refused("the bucket's run lock is not JSON") from None
    if not isinstance(lock, dict):
        raise Refused("the bucket's run lock is not a JSON object")
    return lock


def lock_refusal(lock: dict[str, object], environment: str, now: datetime) -> str | None:
    """Why a lock in this state stops the start, or `None` when it is free or its lease ran out."""
    if lock.get("home_environment") != environment:
        return f"the run lock's home is {lock.get('home_environment')!r}, not {environment!r}"
    if lock.get("state") == "free":
        return None
    if lock.get("state") != "held":
        return f"the run lock's state is {lock.get('state')!r}, neither held nor free"
    holder = lock.get("holder")
    held_by = (
        f"{holder.get('kind')} run {holder.get('run_id')} (`{holder.get('command')}`)"
        if isinstance(holder, dict)
        else "nobody named"
    )
    if isinstance(holder, dict) and holder.get("kind") == "moved":
        return f"the run lock is held for good by {held_by}: the weekly run's home moved"
    expires = _parsed_time(lock.get("lease_expires_at"))
    if expires is not None and now <= expires + CLOCK_SKEW_MARGIN:
        return (
            f"the run lock is held by {held_by} until {expires.isoformat()}; start it once that run is done"
        )
    return None


def _parsed_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# ------------------------------------------------------------------------------------------------
# The revision, and the start
# ------------------------------------------------------------------------------------------------


def family_of(environment: str) -> str:
    return f"debate-{environment}-caselist-run"


def deployer_profile(environment: str) -> str:
    return f"debate-{environment}-caselist-run-deployer"


def task_definition(aws: Aws, environment: str, named: str | None) -> TaskDefinition:
    """The run family's newest ACTIVE revision, or the one named, checked to be the run's."""
    ran = aws(
        [
            "ecs", "describe-task-definition", "--profile", deployer_profile(environment),
            "--region", REGION, "--task-definition", named or family_of(environment), "--output", "json",
        ]
    )  # fmt: skip
    if ran.returncode != 0:
        profile = deployer_profile(environment)
        raise Refused(
            f"could not read the run's task definition as {profile} ({_last_line(ran.stderr)}); "
            f"sign in with `aws sso login --profile {profile}`"
        )
    try:
        definition = json.loads(ran.stdout)["taskDefinition"]
    except (ValueError, KeyError, TypeError):
        raise Refused("describe-task-definition answered something other than a task definition") from None
    problems = definition_problems(definition, environment)
    if problems:
        raise Refused(f"{definition.get('taskDefinitionArn')} is not one this starts: " + "; ".join(problems))
    [container] = definition["containerDefinitions"]
    digest = DIGEST.search(str(container.get("image", "")))
    assert digest is not None
    return TaskDefinition(
        arn=str(definition["taskDefinitionArn"]),
        revision=int(definition["revision"]),
        digest=digest.group(1),
        ephemeral_gib=(definition.get("ephemeralStorage") or {}).get("sizeInGiB"),
    )


def definition_problems(definition: dict[str, object], environment: str) -> list[str]:
    family = family_of(environment)
    problems: list[str] = []
    if definition.get("family") != family:
        problems.append(f"its family is {definition.get('family')!r}, not {family!r}")
    if definition.get("status") != "ACTIVE":
        problems.append(f"it is {definition.get('status')!r}, not ACTIVE")
    if not str(definition.get("taskRoleArn", "")).endswith(f":role/{family}"):
        problems.append("its task role is not the run role")
    containers = definition.get("containerDefinitions")
    if not isinstance(containers, list) or len(containers) != 1:
        problems.append("it does not have exactly one container")
    else:
        [container] = containers
        if not isinstance(container, dict) or container.get("name") != CONTAINER:
            problems.append(f"its container is not named {CONTAINER!r}")
        elif DIGEST.search(str(container.get("image", ""))) is None:
            problems.append("its image is not pinned by digest")
    return problems


def import_command(caselist: str, *, execute: bool, environment: str) -> list[str]:
    """The container's command: `v1-e34-t34`'s import, with the run's entry point in front of it."""
    command = ["--json", "caselist", "backfile-import", "--caselist", caselist]
    if execute:
        command.append("--execute")
        if environment == "prod":
            command.append("--confirm-prod")
    return command


def start_task(
    aws: Aws,
    environment: str,
    definition: TaskDefinition,
    command: list[str],
    subnets: str,
    security_group: str,
) -> str:
    overrides = {"containerOverrides": [{"name": CONTAINER, "command": command}]}
    network = (
        f"awsvpcConfiguration={{subnets=[{subnets}],securityGroups=[{security_group}],"
        "assignPublicIp=ENABLED}"
    )
    ran = aws(
        [
            "ecs", "run-task", "--profile", deployer_profile(environment), "--region", REGION,
            "--cluster", family_of(environment), "--task-definition", definition.arn,
            "--launch-type", "FARGATE", "--platform-version", "LATEST", "--count", "1",
            "--network-configuration", network, "--overrides", json.dumps(overrides),
            "--started-by", STARTED_BY, "--output", "json",
        ]
    )  # fmt: skip
    if ran.returncode != 0:
        raise Refused(f"run-task was refused ({_last_line(ran.stderr)})")
    try:
        answer = json.loads(ran.stdout)
        tasks, failures = answer.get("tasks") or [], answer.get("failures") or []
    except (ValueError, AttributeError):
        raise Refused("run-task answered something other than JSON") from None
    if failures or len(tasks) != 1:
        raise Refused(f"run-task started {len(tasks)} task(s), with failures {failures}")
    return str(tasks[0]["taskArn"])


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else "no message"


def _run_aws(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["aws", *arguments], capture_output=True, text=True, check=False)


# ------------------------------------------------------------------------------------------------
# The command
# ------------------------------------------------------------------------------------------------


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="start_backfile_import.py",
        description="Start one backfile import on the run's task definition. Never scheduled.",
    )
    parser.add_argument("--env", required=True, choices=("dev", "prod"))
    parser.add_argument("--caselist", required=True, help="The backfile caselist, e.g. hspolicy25.")
    parser.add_argument("--subnets", required=True, help="The run's subnets, comma-separated.")
    parser.add_argument("--security-group", required=True, help="The run's security group.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Listings and a HEAD in the task; no download."
    )
    parser.add_argument(
        "--task-definition", help="A revision's ARN; default: the family's newest ACTIVE one."
    )
    parser.add_argument("--confirm-prod", action="store_true", help="Required to import into prod.")
    arguments = parser.parse_args(argv)
    if not SLUG.match(arguments.caselist):
        parser.error(f"--caselist {arguments.caselist!r} is not a caselist slug such as hspolicy25")
    if not re.fullmatch(r"subnet-[0-9a-f]+(,subnet-[0-9a-f]+)*", arguments.subnets):
        parser.error("--subnets takes subnet ids joined by commas, from Terraform's caselist_run_subnet_ids")
    if not re.fullmatch(r"sg-[0-9a-f]+", arguments.security_group):
        parser.error("--security-group takes one sg- id, from Terraform's caselist_run_security_group_id")
    if arguments.env == "prod" and not arguments.dry_run and not arguments.confirm_prod:
        parser.error("an import into prod needs --confirm-prod")
    return arguments


def main(argv: Sequence[str] | None = None, *, now: datetime | None = None, aws: Aws | None = None) -> int:
    arguments = _arguments(argv)
    clock = now or datetime.now(UTC)
    call = aws or _run_aws
    environment = arguments.env
    mode = "dry run" if arguments.dry_run else "import"
    print(f"backfile {mode} of {arguments.caselist} in {environment}")
    try:
        refusal = window_refusal(clock)
        if refusal is not None:
            raise Refused(refusal)
        print(f"  outside the no-import window: {clock.astimezone(WINDOW_ZONE).isoformat()} America/Chicago")
        lock = read_lock(call, environment)
        refusal = lock_refusal(lock, environment, clock)
        if refusal is not None:
            raise Refused(refusal)
        print(f"  run lock: {lock.get('state')}, not held by a run (home {lock.get('home_environment')})")
        definition = task_definition(call, environment, arguments.task_definition)
        print(f"  task definition: {definition.arn} (revision {definition.revision})")
        print(f"  image digest: {definition.digest}")
        print(f"  ephemeral storage: {definition.ephemeral_gib} GiB")
        command = import_command(arguments.caselist, execute=not arguments.dry_run, environment=environment)
        task = start_task(call, environment, definition, command, arguments.subnets, arguments.security_group)
    except Refused as refused:
        print(f"REFUSED: {refused}; nothing was started")
        return 1
    task_id = task.rsplit("/", 1)[-1]
    profile, family = deployer_profile(environment), family_of(environment)
    print(f"started {task}")
    print(f"task id: {task_id}")
    print("Watch it (STOPPED with exit code 0 is done):")
    print(
        f"  aws ecs describe-tasks --profile {profile} --region {REGION} --cluster {family} "
        f"--tasks {task_id} --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text"
    )
    print(
        f"  aws logs tail {family} --profile {profile} --region {REGION} "
        f"--log-stream-names {CONTAINER}/{CONTAINER}/{task_id} --since 6h"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

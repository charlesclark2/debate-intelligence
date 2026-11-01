"""Check a new run image's plan after the cutover, before the PM reads it (`v1-e40-t15`).

Each new release reaches the weekly run by an apply that puts the new image's digest in the login and
run task definitions (docs/runbooks/caselist-cloud-run.md, "A new image, later"). The cutover
runbook's image-plan check was written for the first such apply, while the run's schedule was still
`DISABLED`; since the cutover the schedule stays `ENABLED`, so this check is that one with the
schedule left on. Run by the operator, on the Mac, from the checkout, on the saved plan's JSON:

    terraform -chdir=infrastructure/envs/dev show -json caselist-new-image.tfplan > /tmp/plan.json
    python3 -I ops/caselist_run/check_image_plan.py /tmp/plan.json infrastructure/envs/dev/owner.auto.tfvars

It reads `resource_changes`, never the plan's text: `terraform plan` prints a "Refreshing state..."
line for every resource in state, so a count over the text cannot tell a refresh from a change (on
2026-10-29 a clean plan's Identity Center count read 40). Entries whose actions are `no-op` or `read`
are not changes. Every other entry is exactly one of:

* **an Identity Center change** (`aws_ssoadmin_*`, `aws_identitystore_*`), anywhere: never passes;
* **a change outside `module.caselist_run`**;
* **one of the six expected changes**: the login and run task definitions replaced (delete and
  create, in either order), and the two schedules and their scheduler roles' policies updated;
* **an unexpected change in the module**, such as 2026-10-29's in-place update of the run's
  task-stopped event target, which a person reads.

`PLAN OK` only when every change is one of the six and each is what an image change makes it: each
task definition's image changed to the digest in `owner.auto.tfvars` and nothing else in it (its
environment, entry point and command, roles and size); each schedule's target repointed at the new
revision and nothing else in it, both schedules `ENABLED` before and after; each policy's document
and nothing else. Anything else is `PLAN STOP`, naming each address and its actions, and goes to the
PM before any apply.

Prints one line. Exit `0` for `PLAN OK`, `1` for `PLAN STOP`, `2` when a file cannot be read as a
plan's JSON or an owner file (also `PLAN STOP`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

MODULE = "module.caselist_run."
REPLACE = "replace"
UPDATE = "update"
TASK_DEFINITIONS = (MODULE + "aws_ecs_task_definition.login[0]", MODULE + "aws_ecs_task_definition.run[0]")
SCHEDULES = (MODULE + "aws_scheduler_schedule.login[0]", MODULE + "aws_scheduler_schedule.run[0]")
REPOINTED = {
    SCHEDULES[0]: "target",
    SCHEDULES[1]: "target",
    MODULE + "aws_iam_role_policy.scheduler[0]": "policy",
    MODULE + "aws_iam_role_policy.run_scheduler[0]": "policy",
}
EXPECTED = {address: REPLACE for address in TASK_DEFINITIONS} | {address: UPDATE for address in REPOINTED}
SCHEDULE_STATE = "ENABLED"
IDENTITY_CENTER = ("aws_ssoadmin_", "aws_identitystore_")
DIGEST = re.compile(r'^caselist_image_digest\s*=\s*"(sha256:[0-9a-f]{64})"\s*$', re.M)
CONTAINER_KEYS = (
    "name",
    "essential",
    "entryPoint",
    "command",
    "linuxParameters",
    "stopTimeout",
    "logConfiguration",
    "secrets",
    "user",
    "workingDirectory",
)
TASK_KEYS = (
    "task_role_arn",
    "execution_role_arn",
    "cpu",
    "memory",
    "family",
    "network_mode",
    "requires_compatibilities",
    "runtime_platform",
    "ephemeral_storage",
)
NOT_CHANGES = (["no-op"], ["read"])


class PlanUnreadable(Exception):
    """The file is not `terraform show -json`'s output for a saved plan. The message says why."""


def load_changes(text: str) -> list[dict[str, Any]]:
    try:
        plan = json.loads(text)
    except ValueError as error:
        raise PlanUnreadable(
            f"the plan file is not JSON ({error}); give it `terraform show -json`'s output"
        ) from None
    changes = plan.get("resource_changes") if isinstance(plan, dict) else None
    shaped = isinstance(changes, list) and all(
        isinstance(found, dict)
        and isinstance(found.get("address"), str)
        and isinstance(found.get("type"), str)
        and isinstance(found.get("change"), dict)
        and isinstance(found["change"].get("actions"), list)
        for found in changes
    )
    if not shaped:
        raise PlanUnreadable(
            "the plan file has no resource_changes in the shape `terraform show -json` gives"
        )
    return changes  # type: ignore[return-value]


def key(found: dict[str, Any]) -> str:
    """The address, and for a deposed object (an old instance left by a failed replace) its key."""
    deposed = found.get("deposed")
    return found["address"] + (f" deposed {deposed}" if deposed else "")


def kind(found: dict[str, Any]) -> str:
    actions = found["change"]["actions"]
    if sorted(actions) == ["create", "delete"]:
        return REPLACE
    return "/".join(actions)


def label(found: dict[str, Any]) -> str:
    return f"{key(found)} ({'/'.join(found['change']['actions'])})"


def identity_center(found: dict[str, Any]) -> bool:
    return found["type"].startswith(IDENTITY_CENTER)


def unknown(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return False


def without_arn(value: object) -> object:
    if isinstance(value, dict):
        return {k: without_arn(v) for k, v in value.items() if k != "task_definition_arn"}
    if isinstance(value, list):
        return [without_arn(v) for v in value]
    return value


def container(change: dict[str, Any], side: str) -> dict[str, Any] | None:
    try:
        [only] = json.loads((change[side] or {})["container_definitions"])
    except (TypeError, ValueError, KeyError):
        return None
    return only if isinstance(only, dict) else None


def container_problems(
    address: str, before: dict[str, Any], after: dict[str, Any], keys: Sequence[str]
) -> list[str]:
    """Its environment, and each of `keys`, the same before and after."""
    problems = []
    old = {v["name"]: v["value"] for v in before.get("environment", [])}
    new = {v["name"]: v["value"] for v in after.get("environment", [])}
    if old != new:
        problems.append(
            f"{address} changes its environment: adds {sorted(set(new) - set(old))}, "
            f"removes {sorted(set(old) - set(new))}, "
            f"changes {sorted(k for k in set(old) & set(new) if old[k] != new[k])}"
        )
    changed = sorted(k for k in keys if before.get(k) != after.get(k))
    if changed:
        problems.append(f"{address} also changes {changed}")
    return problems


def task_definition_problems(address: str, change: dict[str, Any], digest: str | None) -> list[str]:
    before, after = container(change, "before"), container(change, "after")
    if before is None or after is None:
        return [address + ": its container definitions cannot be read from the plan"]
    problems = container_problems(address, before, after, CONTAINER_KEYS)
    if digest is not None and not str(after.get("image", "")).endswith("@" + digest):
        problems.append(
            f"{address}'s image is {after.get('image')}, expected the digest in owner.auto.tfvars"
        )
    if before.get("image") == after.get("image"):
        problems.append(f"{address} keeps its image, so there is no image change to apply")
    task = sorted(k for k in TASK_KEYS if (change["before"] or {}).get(k) != (change["after"] or {}).get(k))
    if task:
        problems.append(f"{address} changes its {task}")
    return problems


def repointed_problems(address: str, field: str, change: dict[str, Any]) -> list[str]:
    before, after = change["before"] or {}, change["after"] or {}
    unknowns = {k for k, v in (change.get("after_unknown") or {}).items() if unknown(v)}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k) or k in unknowns)
    problems = []
    if changed != [field]:
        problems.append(f"{address} changes {changed}, expected only {field}")
    if field == "target" and without_arn(before.get("target")) != without_arn(after.get("target")):
        problems.append(f"{address} changes its target beyond the task definition it starts")
    return problems


def state_problem(address: str, change: dict[str, Any]) -> str | None:
    def state(side: str) -> str:
        if side == "after" and unknown((change.get("after_unknown") or {}).get("state")):
            return "(unknown)"
        return str((change[side] or {}).get("state", "(none)"))

    before, after = state("before"), state("after")
    if before == after == SCHEDULE_STATE:
        return None
    return f"{address} is {before} -> {after}, expected {SCHEDULE_STATE} throughout"


def screened(
    changes: list[dict[str, Any]], owner: str
) -> tuple[str | None, list[dict[str, Any]], list[str], dict[str, dict[str, Any]]]:
    """What every mode checks first: the owner file's digest, the changes, the problems with them so
    far (no digest, an Identity Center change, a change outside the module), and the module's changes
    by key."""
    found_digest = DIGEST.search(owner)
    digest = found_digest.group(1) if found_digest else None
    changed = [found for found in changes if found["change"]["actions"] not in NOT_CHANGES]
    problems = []
    if digest is None:
        problems.append("owner.auto.tfvars names no image digest")

    forbidden = [label(found) for found in changed if identity_center(found)]
    if forbidden:
        problems.append(
            "an Identity Center change, which never passes: "
            + ", ".join(sorted(forbidden))
            + "; never apply this plan"
        )
    rest = [found for found in changed if not identity_center(found)]
    outside = [label(found) for found in rest if not found["address"].startswith(MODULE)]
    if outside:
        problems.append("a change outside module.caselist_run: " + ", ".join(sorted(outside)))
    inside = {key(found): found for found in rest if found["address"].startswith(MODULE)}
    return digest, changed, problems, inside


def counts(changed: list[dict[str, Any]]) -> str:
    adds = sum("create" in found["change"]["actions"] for found in changed)
    updates = sum(found["change"]["actions"] == ["update"] for found in changed)
    destroys = sum("delete" in found["change"]["actions"] for found in changed)
    return f"{adds} to add, {updates} to change, {destroys} to destroy"


def check(changes: list[dict[str, Any]], owner: str) -> tuple[list[str], str]:
    """The problems with the plan, and what `PLAN OK` says when there are none."""
    digest, changed, problems, inside = screened(changes, owner)

    for address, expected in EXPECTED.items():
        found = inside.get(address)
        if found is None or kind(found) != expected:
            actual = "no change" if found is None else "/".join(found["change"]["actions"])
            wanted = "a replace (delete and create)" if expected == REPLACE else "an update"
            problems.append(f"{address}: {actual}, expected {wanted}")
        elif expected == REPLACE:
            problems += task_definition_problems(address, found["change"], digest)
        else:
            problems += repointed_problems(address, REPOINTED[address], found["change"])
    for address in SCHEDULES:
        found = inside.get(address)
        problem = None if found is None else state_problem(address, found["change"])
        if problem is not None:
            problems.append(problem)
    unexpected = [label(found) for address, found in inside.items() if address not in EXPECTED]
    if unexpected:
        problems.append("an unexpected change in module.caselist_run: " + ", ".join(sorted(unexpected)))

    said = (
        f"{counts(changed)}; the login and run task definitions "
        f"replaced with the image {(digest or '')[:19]}... and nothing else in them changed; the two "
        f"schedules and their roles' policies repointed at the new revisions; both schedules "
        f"{SCHEDULE_STATE} throughout; nothing else changes"
    )
    return problems, said


def check_memory(changes: list[dict[str, Any]], owner: str) -> tuple[list[str], str]:
    """The run task's memory change (`v1-e40-t30`). Skeleton: refuses nothing yet."""
    return [], "skeleton"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a new run image's plan after the cutover.")
    parser.add_argument("plan", help="The saved plan as JSON: `terraform show -json <plan>`.")
    parser.add_argument("owner", help="The environment's owner.auto.tfvars.")
    parser.add_argument("--memory", action="store_true", help="Check the run task's memory change instead.")
    arguments = parser.parse_args(argv)
    try:
        with open(arguments.plan, encoding="utf-8") as plan:
            changes = load_changes(plan.read())
        with open(arguments.owner, encoding="utf-8") as owner_file:
            owner = owner_file.read()
    except (OSError, PlanUnreadable) as error:
        print(f"PLAN STOP: {error}")
        return 2
    problems, said = (check_memory if arguments.memory else check)(changes, owner)
    if problems:
        print("PLAN STOP: " + "; ".join(problems))
        return 1
    print("PLAN OK: " + said)
    return 0


if __name__ == "__main__":
    sys.exit(main())

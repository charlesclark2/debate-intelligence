"""The shape of back-merge.yml (v1-e01-t12, v1-e01-t15 ac1, ac3, ac4, v1-e01-t26 ac1, ac2).

Both jobs act only after a merge into main, on a schedule or on a dispatch, so no task pull request
exercises them. These tests hold the parts whose loss would be silent: a trigger that stops reaching
a job, a second copy of the re-run, a write permission that spreads or reaches pull-request code, a
dispatch input that reaches a shell, a record the sweep can no longer find, and an open job that
opens a second back-merge pull request or acts when there is nothing to back-merge.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import rerun_promotion_guards as sweep_script  # noqa: E402

SWEEP_SCRIPT = "scripts/rerun_promotion_guards.py"


def workflow(name: str) -> dict[Any, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(flow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    return flow[True]


def back_merge() -> dict[Any, Any]:
    return workflow("back-merge.yml")


def rerun_job() -> dict[str, Any]:
    return back_merge()["jobs"]["rerun-promotion-guards"]


WRITE = "write"


# --------------------------------------------------------------------------------------------
# Triggers: the fast path, the backstop and the manual route all reach the same job
# --------------------------------------------------------------------------------------------


def test_back_merge_runs_on_push_to_main_a_schedule_and_a_dispatch_and_never_on_a_pull_request() -> None:
    on = triggers(back_merge())
    assert set(on) == {"push", "schedule", "workflow_dispatch"}
    assert on["push"] == {"branches": ["main"]}


def test_the_dispatch_takes_no_input() -> None:
    """Nothing typed into the dispatch form can reach a shell, because there is no form."""
    assert triggers(back_merge())["workflow_dispatch"] in (None, {})


def test_the_schedule_sweeps_every_fifteen_minutes_off_the_hour() -> None:
    [schedule] = triggers(back_merge())["schedule"]
    minutes, *rest = schedule["cron"].split()
    assert rest == ["*", "*", "*", "*"]
    sweeps = sorted(int(minute) for minute in minutes.split(","))
    assert len(sweeps) == 4
    assert 0 not in sweeps
    assert {b - a for a, b in zip(sweeps, sweeps[1:] + [sweeps[0] + 60], strict=True)} == {15}


def test_every_trigger_runs_both_the_rerun_job_and_the_open_job() -> None:
    """A push, the schedule and a dispatch each open the back-merge pull request when dev lacks
    something, as well as sweeping (v1-e01-t26). With the triggers pinned above, a job with no
    `if` runs on exactly those three events."""
    jobs = back_merge()["jobs"]
    assert set(jobs) == {"open-back-merge-pull-request", "rerun-promotion-guards"}
    for name, job in jobs.items():
        assert "if" not in job, name


def test_both_jobs_refuse_any_ref_but_main_or_dev_before_checking_anything_out() -> None:
    """Both jobs hold a write permission and run the ref they were started from. A push runs from
    main and the schedule from dev; a dispatch could name any branch, so both refuse it there."""
    for name, job in back_merge()["jobs"].items():
        gate, checkout = job["steps"][:2]
        assert gate.get("if") == "github.ref != 'refs/heads/main' && github.ref != 'refs/heads/dev'", name
        assert "exit 1" in gate["run"], name
        assert checkout["uses"].startswith("actions/checkout@"), name
        assert checkout["with"]["persist-credentials"] is False, name


def test_there_is_one_re_run_and_it_is_the_script() -> None:
    """Forbidden: duplicating the re-run. Exactly one step in any workflow re-runs guard runs, and
    it is the script; no workflow calls the rerun endpoint itself."""
    rerun_call = re.compile(r"runs/\S*/rerun|gh run rerun")
    callers = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        flow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in flow["jobs"].items():
            for step in job.get("steps", []):
                assert not rerun_call.search(step.get("run", "")), f"{path.name} {name} re-runs runs itself"
                if SWEEP_SCRIPT in step.get("run", ""):
                    callers.append((path.name, name))
    assert callers == [("back-merge.yml", "rerun-promotion-guards")]


# --------------------------------------------------------------------------------------------
# Permissions: the shape t12 established (ac4)
# --------------------------------------------------------------------------------------------


def test_back_merge_grants_nothing_at_the_top_and_actions_write_only_to_the_rerun_job() -> None:
    flow = back_merge()
    assert flow["permissions"] == {}
    granted = {name: job["permissions"] for name, job in flow["jobs"].items()}
    assert granted == {
        "open-back-merge-pull-request": {"contents": "read", "pull-requests": "write"},
        "rerun-promotion-guards": {
            "actions": "write",
            "checks": "read",
            "contents": "read",
            "pull-requests": "read",
        },
    }


def test_no_other_workflow_job_holds_actions_write_except_the_ones_that_dispatch() -> None:
    holders = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        flow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in flow["jobs"].items():
            if (job.get("permissions") or {}).get("actions") == WRITE:
                holders.append((path.name, name))
        assert (flow.get("permissions") or {}).get("actions") != WRITE, path.name
    # dev-prerelease dispatches validate-dev (v1-e01-t10); refresh-generated-files dispatches ci (v1-e01-t16).
    assert holders == [
        ("back-merge.yml", "rerun-promotion-guards"),
        ("dev-prerelease.yml", "publish"),
        ("refresh-generated-files.yml", "dispatch-ci"),
    ]


def test_no_other_workflow_job_holds_pull_requests_write_or_contents_write() -> None:
    """Forbidden (v1-e01-t26): either write on any job but the one that opens the back-merge pull
    request. In back-merge.yml that job holds `pull-requests: write` and only `contents: read`; the
    other holders are refresh-generated-files' branch and pull request (v1-e01-t16) and the
    pre-release tag and release (v1-e01-t09)."""
    holders = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        flow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for scope in ("pull-requests", "contents"):
            assert (flow.get("permissions") or {}).get(scope) != WRITE, path.name
        for name, job in flow["jobs"].items():
            granted = job.get("permissions") or {}
            holders += [
                (path.name, name, scope)
                for scope in ("pull-requests", "contents")
                if granted.get(scope) == WRITE
            ]
    assert holders == [
        ("back-merge.yml", "open-back-merge-pull-request", "pull-requests"),
        ("dev-prerelease.yml", "publish", "contents"),
        ("refresh-generated-files.yml", "regenerate", "pull-requests"),
        ("refresh-generated-files.yml", "regenerate", "contents"),
    ]


def test_promotion_guard_holds_no_write_permission() -> None:
    flow = workflow("promotion-guard.yml")
    assert set(triggers(flow)) == {"pull_request"}
    assert flow["permissions"] == {"contents": "read"}
    for job in flow["jobs"].values():
        assert job["permissions"] == {"contents": "read"}


def test_the_rerun_job_checks_out_only_the_script_from_its_own_commit_of_main_or_dev() -> None:
    steps = rerun_job()["steps"]
    [checkout] = [step for step in steps if step.get("uses", "").startswith("actions/checkout@")]
    assert checkout["with"] == {
        "persist-credentials": False,
        "sparse-checkout": SWEEP_SCRIPT,
        "sparse-checkout-cone-mode": False,
    }
    # No `ref`: the commit the workflow itself runs from. The gate before it refuses any ref but
    # main and dev, so a dispatch on a pull request's branch checks out nothing.
    gate = steps[0]
    assert steps.index(checkout) == 1
    assert gate.get("if") == "github.ref != 'refs/heads/main' && github.ref != 'refs/heads/dev'"
    assert "exit 1" in gate["run"]


def test_no_expression_reaches_a_run_block_of_the_rerun_job() -> None:
    for step in rerun_job()["steps"]:
        assert "${{" not in step.get("run", ""), step.get("name")


def test_the_rerun_job_passes_the_repository_and_token_through_env() -> None:
    [sweep] = [step for step in rerun_job()["steps"] if SWEEP_SCRIPT in step.get("run", "")]
    assert sweep["run"] == f'python3 {SWEEP_SCRIPT} --repo "$REPO"'
    assert sweep["env"] == {"GH_TOKEN": "${{ github.token }}", "REPO": "${{ github.repository }}"}


def test_two_open_jobs_never_run_at_once_and_a_sweep_never_waits_behind_one() -> None:
    """Every route's open job is in one fixed group, never cancelled in progress, so a push's and a
    dispatch's can never both find no pull request open and both open one (forbidden, v1-e01-t26).
    A pending open job replaced by a newer one loses nothing: the newer one does the same from the
    live branches. Concurrency is per job, so a sweep never queues behind an open job."""
    flow = back_merge()
    assert "concurrency" not in flow
    assert flow["jobs"]["open-back-merge-pull-request"]["concurrency"] == {
        "group": "back-merge",
        "cancel-in-progress": False,
    }
    sweep_group = flow["jobs"]["rerun-promotion-guards"]["concurrency"]
    assert sweep_group["cancel-in-progress"] is False
    assert "github.event_name == 'push'" in sweep_group["group"]


# --------------------------------------------------------------------------------------------
# The record the sweep reads
# --------------------------------------------------------------------------------------------


def test_promotion_guards_back_merge_job_records_main_before_it_checks() -> None:
    job = workflow("promotion-guard.yml")["jobs"][sweep_script.RECORDING_JOB]
    names = [step.get("name") for step in job["steps"]]
    record = names.index("Record the main commit this run compares")
    assert names.index("Fetch main and dev") < record < names.index("main holds nothing that dev lacks")
    run = job["steps"][record]["run"]
    title = sweep_script.RECORD_TITLE
    assert run == f'echo "::notice title={title}::$(git rev-parse refs/remotes/origin/main)"'
    assert "if" not in job["steps"][record]


# --------------------------------------------------------------------------------------------
# The open job's own steps, against a throwaway repository and a recording `gh` (v1-e01-t26)
# --------------------------------------------------------------------------------------------

COMPARE_STEP = "Find the commits on main that dev lacks"
OPEN_STEP = "Open the back-merge pull request unless one is open"
REPO = "owner/sandbox"

# Records each call's arguments, one JSON list per line. `pr list` answers with the open pull
# request's number, or nothing, as the real `--jq '.[0].number // empty'` would. It refuses what the
# workflow token was refused in the sandbox proof (v1-e01-t26, 2026-10-15): a label put on a pull
# request through GraphQL's `updatePullRequest`, which `gh pr create --label` and
# `gh pr edit --add-label` use. GitHub had already opened the pull request when `--label` failed.
FAKE_GH = """\
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
refused = (
    (args[:2] == ["pr", "create"] and "--label" in args)
    or (args[:2] == ["pr", "edit"] and "--add-label" in args)
    or (args[:2] == ["api", "graphql"] and any("updatePullRequest" in arg for arg in args))
)
if refused:
    print(
        "pull request update failed: GraphQL: github-actions[bot] does not have permission to update"
        " the pull request (updatePullRequest)",
        file=sys.stderr,
    )
    sys.exit(1)
if args[:2] == ["pr", "list"]:
    print(os.environ["FAKE_GH_OPEN_PR"])
elif args[:2] == ["pr", "create"]:
    print("https://github.com/owner/sandbox/pull/99")
"""


@dataclass
class OpenJobRun:
    calls: list[list[str]]
    outputs: dict[str, str]
    log: str
    workdir: Path


def option(call: list[str], name: str) -> str:
    return call[call.index(name) + 1]


def labels_added(calls: list[list[str]]) -> list[tuple[str, str]]:
    """(number, label) for each REST call that adds a label to an issue or pull request, which a
    `pull-requests: write` token may make: `POST /repos/{owner}/{repo}/issues/{number}/labels`."""
    added = []
    for call in calls:
        if call[:1] != ["api"] or "--method" not in call or option(call, "--method") != "POST":
            continue
        for arg in call[1:]:
            if found := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/labels", arg):
                added += [
                    (found[1], field.split("=", 1)[1]) for field in call if field.startswith("labels[]=")
                ]
    return added


def open_job_step(name: str) -> dict[str, Any]:
    [step] = [
        step
        for step in back_merge()["jobs"]["open-back-merge-pull-request"]["steps"]
        if step.get("name") == name
    ]
    return step


def run_open_job(tmp_path: Path, *, main: str, open_pr: str = "") -> OpenJobRun:
    """Runs the compare step and, when its output says so, the open step, as the runner would:
    `bash -e`, from a full clone whose origin/main and origin/dev are already fetched.

    `main` is "hotfix" (a non-merge commit dev lacks) or "promotion" (only a merge commit)."""
    workdir, bin_dir = tmp_path / "clone", tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "fake_gh.py").write_text(FAKE_GH, encoding="utf-8")
    for name, target in (
        ("gh", f'"{sys.executable}" "{tmp_path / "fake_gh.py"}"'),
        ("python3", f'"{sys.executable}"'),
    ):
        (bin_dir / name).write_text(f'#!/bin/sh\nexec {target} "$@"\n', encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    gh_log, outputs = tmp_path / "gh.log", tmp_path / "github_output"
    gh_log.touch()
    outputs.touch()
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "FAKE_GH_LOG": str(gh_log),
        "FAKE_GH_OPEN_PR": open_pr,
        "GITHUB_OUTPUT": str(outputs),
    }

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(workdir), *args], check=True, env=env, capture_output=True, text=True
        )
        return done.stdout.strip()

    subprocess.run(["git", "init", "-q", "-b", "main", str(workdir)], check=True, env=env)
    git("commit", "-q", "--allow-empty", "-m", "Shared history")
    git("branch", "dev")
    if main == "hotfix":
        git("commit", "-q", "--allow-empty", "-m", "Hotfix dev lacks")
    else:
        git("switch", "-q", "dev")
        git("commit", "-q", "--allow-empty", "-m", "Work validated in dev")
        git("switch", "-q", "main")
        git("merge", "-q", "--no-ff", "-m", "Promotion", "dev")
    for branch in ("main", "dev"):
        git("update-ref", f"refs/remotes/origin/{branch}", branch)
    (workdir / "scripts").mkdir()
    shutil.copy(REPO_ROOT / "scripts" / "check_promotion_source.py", workdir / "scripts")

    log = []
    compare = open_job_step(COMPARE_STEP)
    assert compare["id"] == "compare"
    steps = [compare]
    done = subprocess.run(
        ["bash", "-e", "-c", compare["run"]], cwd=workdir, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    log.append(done.stdout + done.stderr)
    step_outputs = dict(line.split("=", 1) for line in outputs.read_text(encoding="utf-8").splitlines())

    opener = open_job_step(OPEN_STEP)
    # The runner's reading of the condition: a step with no `if` always runs.
    condition = opener.get("if")
    assert condition in (None, "steps.compare.outputs.needed == 'true'"), condition
    assert opener["env"] == {"GH_TOKEN": "${{ github.token }}", "REPO": "${{ github.repository }}"}
    if condition is None or step_outputs.get("needed") == "true":
        steps.append(opener)
        step_env = {**env, "GH_TOKEN": "fake-token", "REPO": REPO}
        done = subprocess.run(
            ["bash", "-e", "-c", opener["run"]], cwd=workdir, env=step_env, capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr
        log.append(done.stdout + done.stderr)
    for step in steps:
        assert "${{" not in step["run"], step["name"]

    calls = [json.loads(line) for line in gh_log.read_text(encoding="utf-8").splitlines()]
    return OpenJobRun(calls=calls, outputs=step_outputs, log="".join(log), workdir=workdir)


def test_with_no_back_merge_pull_request_open_the_job_opens_one(tmp_path: Path) -> None:
    run = run_open_job(tmp_path, main="hotfix")
    assert run.outputs == {"needed": "true"}
    lists = [call for call in run.calls if call[:2] == ["pr", "list"]]
    creates = [call for call in run.calls if call[:2] == ["pr", "create"]]
    assert len(lists) == 1
    assert len(creates) == 1
    [listing], [create] = lists, creates
    assert run.calls.index(listing) < run.calls.index(create)
    assert (option(listing, "--base"), option(listing, "--head"), option(listing, "--state")) == (
        "dev",
        "main",
        "open",
    )
    assert option(create, "--repo") == REPO
    assert (option(create, "--base"), option(create, "--head")) == ("dev", "main")
    assert "--label" not in create
    # The label goes on the pull request just opened, #99 in the fake's answer, through REST.
    assert labels_added(run.calls) == [("99", "back-merge")]
    [label_call] = [call for call in run.calls if labels_added([call])]
    assert run.calls.index(create) < run.calls.index(label_call)
    hotfix = subprocess.run(
        ["git", "-C", str(run.workdir), "rev-parse", "main"], check=True, capture_output=True, text=True
    ).stdout.strip()
    body = (run.workdir / option(create, "--body-file")).read_text(encoding="utf-8")
    assert f"{hotfix} Hotfix dev lacks" in body


def test_with_one_back_merge_pull_request_open_the_job_names_it_and_opens_no_second(tmp_path: Path) -> None:
    run = run_open_job(tmp_path, main="hotfix", open_pr="17")
    assert run.outputs == {"needed": "true"}
    assert [call for call in run.calls if call[:2] == ["pr", "create"]] == []
    assert labels_added(run.calls) == [("17", "back-merge")]
    assert "Back-merge pull request #17 is open" in run.log


def test_when_main_and_dev_agree_the_job_does_nothing_visible(tmp_path: Path) -> None:
    """A scheduled or dispatched run with nothing to back-merge: main holds only a promotion's
    merge commit. No call to GitHub at all, so no pull request, label or comment, and no workflow
    command in the log, so no annotation."""
    run = run_open_job(tmp_path, main="promotion")
    assert run.outputs == {"needed": "false"}
    assert run.calls == []
    assert "::" not in run.log
    assert run.log.startswith("OK: ")

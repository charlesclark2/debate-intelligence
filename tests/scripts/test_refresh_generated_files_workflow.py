"""The shape of the mechanism that keeps ROADMAP.md and docs/README.md fresh on dev (v1-e01-t16 ac5).

refresh-generated-files.yml only runs after a merge into dev, and its pull request's `ci` only
exists because ci.yml can be dispatched, so no task pull request ever exercises either. These
tests hold the parts whose loss would be silent: a refresh pull request that never gets its
required check, a write permission that reaches code it should not, a freshness check that runs
where it would make task pull requests conflict, or a check that regenerates instead of reporting.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def workflow(name: str) -> dict[Any, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(flow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    return flow[True]


def steps(flow: dict[Any, Any]) -> list[dict[str, Any]]:
    return [step for job in flow["jobs"].values() for step in job.get("steps", [])]


# --------------------------------------------------------------------------------------------
# ci.yml: where the two checks run
# --------------------------------------------------------------------------------------------


def test_ci_can_be_dispatched_so_the_refresh_pull_request_gets_its_required_check() -> None:
    assert "workflow_dispatch" in triggers(workflow("ci.yml"))


def test_docs_index_check_runs_exactly_where_spec_index_check_runs() -> None:
    def running(script: str) -> list[dict[str, Any]]:
        check = re.compile(rf"scripts/{script} --check(\s|$)", re.MULTILINE)
        return [step for step in steps(workflow("ci.yml")) if check.search(step.get("run", ""))]

    spec, docs = running("spec_index.py"), running("docs_index.py")
    assert spec and docs
    conditions = [step.get("if") for step in spec]
    assert conditions == [step.get("if") for step in docs] == ["github.base_ref == 'main'"]


def test_check_descriptions_runs_on_every_trigger() -> None:
    command = "docs_index.py --check-descriptions"
    [step] = [s for s in steps(workflow("ci.yml")) if command in s.get("run", "")]
    assert "if" not in step


def test_no_check_in_ci_regenerates_a_generated_file() -> None:
    """Forbidden: regenerating in CI, which hides drift. Every invocation in ci.yml is a check."""
    for step in steps(workflow("ci.yml")):
        for line in step.get("run", "").splitlines():
            if "spec_index.py" in line or "docs_index.py" in line:
                assert "--check" in line, line


# --------------------------------------------------------------------------------------------
# refresh-generated-files.yml: triggers and permissions
# --------------------------------------------------------------------------------------------


def test_refresh_runs_only_on_merged_code() -> None:
    flow = workflow("refresh-generated-files.yml")
    assert set(triggers(flow)) == {"push", "workflow_dispatch"}
    assert triggers(flow)["push"] == {"branches": ["dev"]}
    assert flow["jobs"]["regenerate"]["if"] == "github.ref == 'refs/heads/dev'"


def test_refresh_grants_nothing_by_default_and_each_write_to_one_job() -> None:
    flow = workflow("refresh-generated-files.yml")
    assert flow["permissions"] == {}
    granted = {name: job["permissions"] for name, job in flow["jobs"].items()}
    assert granted == {
        "regenerate": {"contents": "write", "pull-requests": "write"},
        "dispatch-ci": {"actions": "write"},
    }


def test_the_job_holding_actions_write_checks_out_nothing() -> None:
    job = workflow("refresh-generated-files.yml")["jobs"]["dispatch-ci"]
    assert not any("uses" in step for step in job["steps"])
    assert any("gh workflow run ci.yml" in step["run"] for step in job["steps"])


def test_the_regenerating_job_persists_no_credentials_for_the_generators() -> None:
    job = workflow("refresh-generated-files.yml")["jobs"]["regenerate"]
    [checkout] = [step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")]
    assert checkout["with"]["persist-credentials"] is False
    assert checkout["with"]["ref"] == "dev"
    [regenerate] = [step for step in job["steps"] if "scripts/docs_index.py" in step.get("run", "")]
    assert "env" not in regenerate
    assert "--check" not in regenerate["run"]

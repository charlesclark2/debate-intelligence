# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Validate every PlanSpec under plan_specs/.

Checks (see plan_specs/README.md for the conventions they enforce):
  * every document is planspec.io/v1alpha1 with a known kind and a unique metadata.name
  * task files hold exactly one Goal + one Plan, labels match their folder, goalRef matches
  * Plan graph node ids are unique, dependsOn resolves, graphs are acyclic
  * every Task node has typed acceptance criteria with the required fields for its type
  * cross-task prerequisites (Goal.spec.context TaskRef) resolve, never point to a later release,
    and the global task graph is acyclic
  * every epic lives in exactly one major version and one release, and its Plan lists every task file
  * every release references existing epics whose release label matches

Usage:
  uv run scripts/validate_specs.py                      # validate everything
  uv run scripts/validate_specs.py --require-succeeded NAME   # exit 1 unless NAME's status.phase is Succeeded
  uv run scripts/validate_specs.py --status             # print a status roll-up
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "plan_specs"
API = "planspec.io/v1alpha1"
KINDS = {"Goal", "Plan", "Gate", "Task", "Execution", "Binding", "Capability"}
NODE_KINDS = {"Task", "Gate", "Group", "External"}
PHASES = {"Pending", "Ready", "InProgress", "Blocked", "Succeeded", "Failed", "Cancelled"}
CRITERIA_FIELDS = {
    "artifact_exists": {"name", "path"},
    "test_passes": {"name", "command"},
    "command_succeeds": {"name", "command"},
    "endpoint_responds": {"name", "url"},
    "custom": {"name"},
}
RELEASE_ORDER = ["v1.0", "v1.1", "v1.2", "v1.3", "v1.4", "v1.5", "v1.6", "v2.0", "v2.1", "v2.2", "v2.3", "v2.4",
                 "v3.0", "v3.1", "v3.2", "v3.3", "v3.4", "v3.5", "v3.6", "v3.7"]

errors: list[str] = []


def err(path: Path, msg: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {msg}")


def load(path: Path) -> list[dict]:
    try:
        docs = [d for d in yaml.safe_load_all(path.read_text()) if d is not None]
    except yaml.YAMLError as exc:  # pragma: no cover - reported, not raised
        err(path, f"YAML parse error: {exc}")
        return []
    for d in docs:
        if d.get("apiVersion") != API:
            err(path, f"apiVersion must be {API}")
        if d.get("kind") not in KINDS:
            err(path, f"unknown kind {d.get('kind')!r}")
        if not (d.get("metadata") or {}).get("name"):
            err(path, "metadata.name is required")
    return docs


def check_graph(path: Path, plan: dict) -> None:
    nodes = (((plan.get("spec") or {}).get("graph") or {}).get("nodes")) or []
    if not nodes:
        err(path, "Plan graph has no nodes")
        return
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        err(path, f"duplicate node ids: {sorted(i for i in ids if ids.count(i) > 1)}")
    idset = set(ids)
    edges = {}
    for n in nodes:
        if n.get("kind") not in NODE_KINDS:
            err(path, f"node {n.get('id')}: kind must be one of {sorted(NODE_KINDS)}")
        deps = n.get("dependsOn") or []
        for d in deps:
            if d not in idset:
                err(path, f"node {n.get('id')}: dependsOn {d!r} does not resolve")
        edges[n.get("id")] = deps
        if n.get("kind") == "Task":
            crit = n.get("acceptanceCriteria") or []
            if not crit:
                err(path, f"node {n.get('id')}: Task nodes need acceptanceCriteria")
            for c in crit:
                ctype = c.get("type")
                if ctype not in CRITERIA_FIELDS:
                    err(path, f"node {n.get('id')}: unknown criteria type {ctype!r}")
                    continue
                missing = CRITERIA_FIELDS[ctype] - set(c)
                if missing:
                    err(path, f"node {n.get('id')}: {ctype} criteria missing {sorted(missing)}")
        if n.get("kind") == "Gate" and not (n.get("gateRef") or {}).get("name"):
            err(path, f"node {n.get('id')}: Gate nodes need gateRef.name")
    if has_cycle(edges):
        err(path, "Plan graph contains a cycle")


def has_cycle(edges: dict[str, list[str]]) -> bool:
    state: dict[str, int] = {}

    def visit(n: str) -> bool:
        if state.get(n) == 1:
            return True
        if state.get(n) == 2:
            return False
        state[n] = 1
        for d in edges.get(n, []):
            if visit(d):
                return True
        state[n] = 2
        return False

    return any(visit(n) for n in list(edges))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-succeeded", metavar="NAME")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    names: dict[str, Path] = {}
    goals: dict[str, dict] = {}
    task_release: dict[str, str] = {}
    task_prereqs: dict[str, list[str]] = {}
    epics: dict[str, dict] = {}
    epic_tasks: dict[str, list[str]] = defaultdict(list)
    releases: dict[str, list[str]] = {}

    files = sorted(p for p in SPECS.rglob("*.yaml") if "_templates" not in p.parts)
    for path in files:
        docs = load(path)
        for d in docs:
            n = (d.get("metadata") or {}).get("name")
            if n in names:
                err(path, f"duplicate metadata.name {n!r} (also in {names[n].relative_to(ROOT)})")
            names[n] = path
            if d.get("kind") == "Goal":
                goals[n] = d
                phase = (d.get("status") or {}).get("phase", "Pending")
                if phase not in PHASES:
                    err(path, f"status.phase {phase!r} not in {sorted(PHASES)}")
                if not (d.get("spec") or {}).get("acceptanceCriteria"):
                    err(path, "Goal needs spec.acceptanceCriteria")
        by_kind = defaultdict(list)
        for d in docs:
            by_kind[d.get("kind")].append(d)
        for plan in by_kind["Plan"]:
            check_graph(path, plan)
            ref = ((plan.get("spec") or {}).get("goalRef") or {}).get("name")
            if ref not in {g["metadata"]["name"] for g in by_kind["Goal"]}:
                err(path, f"Plan goalRef {ref!r} does not match a Goal in the same file")

        rel = path.relative_to(SPECS).parts
        if rel[0] == "releases":
            if len(by_kind["Goal"]) != 1 or len(by_kind["Plan"]) != 1 or len(by_kind["Gate"]) != 1:
                err(path, "release files need exactly one Goal, one Gate and one Plan")
                continue
            version = by_kind["Goal"][0]["metadata"]["labels"].get("debate/release")
            if version != path.stem:
                err(path, "debate/release label must equal the file name")
            releases[version] = [
                (node.get("inputs") or {}).get("goalRef")
                for node in by_kind["Plan"][0]["spec"]["graph"]["nodes"] if node.get("kind") == "External"
            ]
            continue
        if len(rel) != 3 or rel[0] not in {"v1", "v2", "v3"}:
            continue
        major, epic_dir, fname = rel
        if len(by_kind["Goal"]) != 1 or len(by_kind["Plan"]) != 1:
            err(path, "epic/task files need exactly one Goal and one Plan")
            continue
        goal = by_kind["Goal"][0]
        labels = goal["metadata"].get("labels") or {}
        if labels.get("debate/major-version") != major:
            err(path, f"debate/major-version label must be {major!r} (folder)")
        for d in docs:
            if (d.get("metadata") or {}).get("labels") != labels:
                err(path, "every document in a file must carry identical labels")
                break
        release = labels.get("debate/release")
        if release not in RELEASE_ORDER or not release.startswith(major):
            err(path, f"debate/release {release!r} must be a {major} release")
        if fname == "epic.yaml":
            epics[goal["metadata"]["name"]] = dict(path=path, release=release, major=major, dir=epic_dir, plan=by_kind["Plan"][0])
        else:
            tn = goal["metadata"]["name"]
            expected_prefix = f"{major}-{epic_dir.split('-')[0]}-{fname.split('-')[0]}-"
            if not tn.startswith(expected_prefix):
                err(path, f"task name {tn!r} must start with {expected_prefix!r}")
            task_release[tn] = release
            epic_tasks[labels.get("debate/epic")].append(tn)
            task_prereqs[tn] = [c["name"] for c in (goal["spec"].get("context") or [])
                                if c.get("kind") == "TaskRef" and c.get("relation") == "dependsOn"]

    # epic rules
    for en, e in epics.items():
        members = epic_tasks.get(en, [])
        if not members:
            err(e["path"], "epic has no task files")
        for tn in members:
            if task_release[tn] != e["release"]:
                err(names[tn], f"task release {task_release[tn]} differs from epic release {e['release']}")
            if not names[tn].parent == e["path"].parent:
                err(names[tn], "task file must live in its epic's folder")
        listed = {(n.get("inputs") or {}).get("goalRef") for n in e["plan"]["spec"]["graph"]["nodes"] if n.get("kind") == "Task"}
        for tn in members:
            if tn not in listed:
                err(e["path"], f"epic Plan does not list task {tn}")
        for tn in listed - set(members):
            err(e["path"], f"epic Plan lists {tn} but no task file declares it")
    for en in epic_tasks:
        if en not in epics:
            err(SPECS, f"tasks reference unknown epic {en!r}")

    # cross-task prerequisites
    for tn, pres in task_prereqs.items():
        for p in pres:
            if p not in task_release:
                err(names[tn], f"context TaskRef {p!r} does not resolve to a task")
            elif RELEASE_ORDER.index(task_release[p]) > RELEASE_ORDER.index(task_release[tn]):
                err(names[tn], f"prerequisite {p} ships in a later release ({task_release[p]})")
    if has_cycle(task_prereqs):
        err(SPECS, "cross-task prerequisite graph contains a cycle")

    # releases
    for version, epic_refs in releases.items():
        for en in epic_refs:
            if en not in epics:
                err(SPECS / "releases" / f"{version}.yaml", f"unknown epic {en!r}")
            elif epics[en]["release"] != version:
                err(SPECS / "releases" / f"{version}.yaml", f"epic {en} is labeled {epics[en]['release']}")
    for en, e in epics.items():
        if e["release"] not in releases or en not in releases[e["release"]]:
            err(e["path"], f"epic is not referenced by release {e['release']}")

    if args.require_succeeded:
        g = goals.get(args.require_succeeded)
        phase = (g or {}).get("status", {}).get("phase")
        print(f"{args.require_succeeded}: {phase}")
        return 0 if phase == "Succeeded" else 1

    if args.status:
        counts = defaultdict(lambda: defaultdict(int))
        for tn, r in task_release.items():
            counts[r][goals[tn].get("status", {}).get("phase", "Pending")] += 1
        for r in RELEASE_ORDER:
            if r in counts:
                print(r, dict(counts[r]))

    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} error(s) in {len(files)} files", file=sys.stderr)
        return 1
    print(f"OK: {len(files)} files, {len(epics)} epics, {len(task_release)} tasks, {len(releases)} releases")
    return 0


if __name__ == "__main__":
    sys.exit(main())

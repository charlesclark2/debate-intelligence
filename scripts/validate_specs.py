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

Release order is read from the file names in plan_specs/releases/ (sorted by version number), so a
new release needs no change here.

Usage:
  uv run scripts/validate_specs.py                      # validate everything
  uv run scripts/validate_specs.py --require-succeeded NAME   # exit 1 unless NAME's status.phase is Succeeded
  uv run scripts/validate_specs.py --status             # print a status roll-up per release and epic
  uv run scripts/validate_specs.py --root DIR           # validate the spec tree under another root
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API = "planspec.io/v1alpha1"
KINDS = {"Goal", "Plan", "Gate", "Task", "Execution", "Binding", "Capability"}
NODE_KINDS = {"Task", "Gate", "Group", "External"}
MAJOR_VERSIONS = {"v1", "v2", "v3"}
# The lifecycle order from plan_specs/README.md; the status roll-up reports phases in this order.
PHASE_ORDER = ["Pending", "Ready", "InProgress", "Blocked", "Succeeded", "Failed", "Cancelled"]
PHASES = set(PHASE_ORDER)
# Phases a reader of the roll-up needs to see by name rather than as a count.
NEEDS_ATTENTION = ["Blocked", "Failed"]
CRITERIA_FIELDS = {
    "artifact_exists": {"name", "path"},
    "test_passes": {"name", "command"},
    "command_succeeds": {"name", "command"},
    "endpoint_responds": {"name", "url"},
    "custom": {"name"},
}
RELEASE_FILE_NAME = re.compile(r"^v(\d+)\.(\d+)$")


def release_order(specs: Path) -> list[str]:
    """The releases that have a file, in version order (v1.2 before v1.10)."""
    versions = {}
    for path in (specs / "releases").glob("*.yaml"):
        match = RELEASE_FILE_NAME.match(path.stem)
        if match:
            versions[path.stem] = (int(match[1]), int(match[2]))
    return sorted(versions, key=lambda v: versions[v])


@dataclass
class SpecTree:
    """Everything the validator learned about one plan_specs/ tree."""

    root: Path
    errors: list[str] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    release_order: list[str] = field(default_factory=list)
    #: metadata.name -> the file that declares it
    names: dict[str, Path] = field(default_factory=dict)
    #: metadata.name -> the Goal document
    goals: dict[str, dict] = field(default_factory=dict)
    #: release version -> its Goal's debate/title annotation
    release_titles: dict[str, str] = field(default_factory=dict)
    #: release version -> the epic names its Plan references
    release_epics: dict[str, list[str]] = field(default_factory=dict)
    #: epic name -> {path, release, major, dir, plan}
    epics: dict[str, dict] = field(default_factory=dict)
    #: epic name -> the task names that carry its debate/epic label
    epic_tasks: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    #: task name -> its release version
    task_release: dict[str, str] = field(default_factory=dict)
    #: task name -> its epic name
    task_epic: dict[str, str] = field(default_factory=dict)
    #: task name -> the task names it lists as prerequisites
    task_prereqs: dict[str, list[str]] = field(default_factory=dict)

    @property
    def specs(self) -> Path:
        return self.root / "plan_specs"

    def err(self, path: Path, msg: str) -> None:
        self.errors.append(f"{path.relative_to(self.root)}: {msg}")

    def phase(self, name: str) -> str:
        return (self.goals.get(name, {}).get("status") or {}).get("phase", "Pending")


def load(tree: SpecTree, path: Path) -> list[dict]:
    try:
        docs = [d for d in yaml.safe_load_all(path.read_text()) if d is not None]
    except yaml.YAMLError as exc:
        tree.err(path, f"YAML parse error: {exc}")
        return []
    for d in docs:
        if d.get("apiVersion") != API:
            tree.err(path, f"apiVersion must be {API}")
        if d.get("kind") not in KINDS:
            tree.err(path, f"unknown kind {d.get('kind')!r}")
        if not (d.get("metadata") or {}).get("name"):
            tree.err(path, "metadata.name is required")
    return docs


def check_graph(tree: SpecTree, path: Path, plan: dict) -> None:
    nodes = (((plan.get("spec") or {}).get("graph") or {}).get("nodes")) or []
    if not nodes:
        tree.err(path, "Plan graph has no nodes")
        return
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        tree.err(path, f"duplicate node ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    idset = set(ids)
    edges = {}
    for n in nodes:
        if n.get("kind") not in NODE_KINDS:
            tree.err(path, f"node {n.get('id')}: kind must be one of {sorted(NODE_KINDS)}")
        deps = n.get("dependsOn") or []
        for d in deps:
            if d not in idset:
                tree.err(path, f"node {n.get('id')}: dependsOn {d!r} does not resolve")
        edges[n.get("id")] = deps
        if n.get("kind") == "Task":
            check_criteria(tree, path, n)
        if n.get("kind") == "Gate" and not (n.get("gateRef") or {}).get("name"):
            tree.err(path, f"node {n.get('id')}: Gate nodes need gateRef.name")
    if has_cycle(edges):
        tree.err(path, "Plan graph contains a cycle")


def check_criteria(tree: SpecTree, path: Path, node: dict) -> None:
    criteria = node.get("acceptanceCriteria") or []
    if not criteria:
        tree.err(path, f"node {node.get('id')}: Task nodes need acceptanceCriteria")
    for c in criteria:
        ctype = c.get("type")
        if ctype not in CRITERIA_FIELDS:
            tree.err(path, f"node {node.get('id')}: unknown criteria type {ctype!r}")
            continue
        missing = CRITERIA_FIELDS[ctype] - set(c)
        if missing:
            tree.err(path, f"node {node.get('id')}: {ctype} criteria missing {sorted(missing)}")


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


def collect(root: Path) -> SpecTree:
    """Read and check every spec under root/plan_specs, returning what was found."""
    tree = SpecTree(root=root)
    tree.release_order = release_order(tree.specs)
    tree.files = sorted(p for p in tree.specs.rglob("*.yaml") if "_templates" not in p.parts)
    for path in tree.files:
        docs = load(tree, path)
        by_kind: dict[str | None, list[dict]] = defaultdict(list)
        for d in docs:
            by_kind[d.get("kind")].append(d)
            read_document(tree, path, d)
        for plan in by_kind["Plan"]:
            check_graph(tree, path, plan)
            ref = ((plan.get("spec") or {}).get("goalRef") or {}).get("name")
            if ref not in {g.get("metadata", {}).get("name") for g in by_kind["Goal"]}:
                tree.err(path, f"Plan goalRef {ref!r} does not match a Goal in the same file")

        rel = path.relative_to(tree.specs).parts
        if rel[0] == "releases":
            read_release(tree, path, by_kind)
        elif len(rel) == 3 and rel[0] in MAJOR_VERSIONS:
            read_epic_or_task(tree, path, by_kind, major=rel[0], epic_dir=rel[1], fname=rel[2])

    check_epics(tree)
    check_prerequisites(tree)
    check_releases(tree)
    return tree


def read_document(tree: SpecTree, path: Path, d: dict) -> None:
    name = (d.get("metadata") or {}).get("name")
    if name in tree.names:
        first = tree.names[name].relative_to(tree.root)
        tree.err(path, f"duplicate metadata.name {name!r} (also in {first})")
    tree.names[name] = path
    if d.get("kind") != "Goal":
        return
    tree.goals[name] = d
    phase = (d.get("status") or {}).get("phase", "Pending")
    if phase not in PHASES:
        tree.err(path, f"status.phase {phase!r} not in {sorted(PHASES)}")
    if not (d.get("spec") or {}).get("acceptanceCriteria"):
        tree.err(path, "Goal needs spec.acceptanceCriteria")


def read_release(tree: SpecTree, path: Path, by_kind: dict[str | None, list[dict]]) -> None:
    if not RELEASE_FILE_NAME.match(path.stem):
        tree.err(path, "release file name must be vMAJOR.MINOR.yaml")
        return
    if len(by_kind["Goal"]) != 1 or len(by_kind["Plan"]) != 1 or len(by_kind["Gate"]) != 1:
        tree.err(path, "release files need exactly one Goal, one Gate and one Plan")
        return
    goal = by_kind["Goal"][0]
    version = (goal["metadata"].get("labels") or {}).get("debate/release")
    if version != path.stem:
        tree.err(path, "debate/release label must equal the file name")
        return
    tree.release_titles[version] = (goal["metadata"].get("annotations") or {}).get("debate/title", version)
    tree.release_epics[version] = [
        (node.get("inputs") or {}).get("goalRef")
        for node in by_kind["Plan"][0]["spec"]["graph"]["nodes"]
        if node.get("kind") == "External"
    ]


def read_epic_or_task(
    tree: SpecTree,
    path: Path,
    by_kind: dict[str | None, list[dict]],
    *,
    major: str,
    epic_dir: str,
    fname: str,
) -> None:
    if len(by_kind["Goal"]) != 1 or len(by_kind["Plan"]) != 1:
        tree.err(path, "epic/task files need exactly one Goal and one Plan")
        return
    goal = by_kind["Goal"][0]
    name = (goal.get("metadata") or {}).get("name")
    if not name:
        return  # load() already reported the missing metadata.name
    labels = goal["metadata"].get("labels") or {}
    if labels.get("debate/major-version") != major:
        tree.err(path, f"debate/major-version label must be {major!r} (folder)")
    for d in by_kind["Goal"] + by_kind["Plan"]:
        if (d.get("metadata") or {}).get("labels") != labels:
            tree.err(path, "every document in a file must carry identical labels")
            break
    release = labels.get("debate/release")
    if release not in tree.release_order:
        tree.err(path, f"debate/release {release!r} has no file in plan_specs/releases/")
    elif not release.startswith(f"{major}."):
        tree.err(path, f"debate/release {release!r} must be a {major} release")
    if fname == "epic.yaml":
        tree.epics[name] = dict(
            path=path, release=release, major=major, dir=epic_dir, plan=by_kind["Plan"][0]
        )
        return
    expected_prefix = f"{major}-{epic_dir.split('-')[0]}-{fname.split('-')[0]}-"
    if not name.startswith(expected_prefix):
        tree.err(path, f"task name {name!r} must start with {expected_prefix!r}")
    tree.task_release[name] = release
    tree.task_epic[name] = labels.get("debate/epic")
    tree.epic_tasks[labels.get("debate/epic")].append(name)
    tree.task_prereqs[name] = [
        c["name"]
        for c in (goal["spec"].get("context") or [])
        if c.get("kind") == "TaskRef" and c.get("relation") == "dependsOn"
    ]


def check_epics(tree: SpecTree) -> None:
    for epic_name, epic in tree.epics.items():
        members = tree.epic_tasks.get(epic_name, [])
        if not members:
            tree.err(epic["path"], "epic has no task files")
        for task in members:
            if tree.task_release[task] != epic["release"]:
                tree.err(
                    tree.names[task],
                    f"task release {tree.task_release[task]} differs from epic release {epic['release']}",
                )
            if tree.names[task].parent != epic["path"].parent:
                tree.err(tree.names[task], "task file must live in its epic's folder")
        listed = {
            (n.get("inputs") or {}).get("goalRef")
            for n in epic["plan"]["spec"]["graph"]["nodes"]
            if n.get("kind") == "Task"
        }
        for task in members:
            if task not in listed:
                tree.err(epic["path"], f"epic Plan does not list task {task}")
        for task in sorted(listed - set(members)):
            tree.err(epic["path"], f"epic Plan lists {task} but no task file declares it")
    for epic_name in tree.epic_tasks:
        if epic_name not in tree.epics:
            tree.err(tree.specs, f"tasks reference unknown epic {epic_name!r}")


def check_prerequisites(tree: SpecTree) -> None:
    for task, prereqs in tree.task_prereqs.items():
        for prereq in prereqs:
            if prereq not in tree.task_release:
                tree.err(tree.names[task], f"context TaskRef {prereq!r} does not resolve to a task")
                continue
            order = tree.release_order
            if tree.task_release[prereq] not in order or tree.task_release[task] not in order:
                continue
            if order.index(tree.task_release[prereq]) > order.index(tree.task_release[task]):
                tree.err(
                    tree.names[task],
                    f"prerequisite {prereq} ships in a later release ({tree.task_release[prereq]})",
                )
    if has_cycle(tree.task_prereqs):
        tree.err(tree.specs, "cross-task prerequisite graph contains a cycle")


def check_releases(tree: SpecTree) -> None:
    for version, epic_refs in tree.release_epics.items():
        release_file = tree.specs / "releases" / f"{version}.yaml"
        for epic_name in epic_refs:
            if epic_name not in tree.epics:
                tree.err(release_file, f"unknown epic {epic_name!r}")
            elif tree.epics[epic_name]["release"] != version:
                tree.err(release_file, f"epic {epic_name} is labeled {tree.epics[epic_name]['release']}")
    for epic_name, epic in tree.epics.items():
        if epic["release"] not in tree.release_epics or epic_name not in tree.release_epics[epic["release"]]:
            tree.err(epic["path"], f"epic is not referenced by release {epic['release']}")


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def phase_counts(tree: SpecTree, tasks: list[str]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for task in tasks:
        counts[tree.phase(task)] += 1
    return ", ".join(f"{phase} {counts[phase]}" for phase in PHASE_ORDER if counts[phase])


def render_status(tree: SpecTree) -> list[str]:
    """The --status roll-up: phase counts per release and per epic, then what needs attention."""
    lines = ["Status by release and epic", ""]
    for version in tree.release_order:
        epics = sorted(name for name, e in tree.epics.items() if e["release"] == version)
        tasks = [t for t, r in tree.task_release.items() if r == version]
        title = tree.release_titles.get(version, version)
        summary = phase_counts(tree, tasks) or "no tasks"
        lines.append(f"{title}: {plural(len(epics), 'epic')}, {plural(len(tasks), 'task')} — {summary}")
        for epic_name in epics:
            epic_task_names = sorted(tree.epic_tasks.get(epic_name, []))
            epic_summary = phase_counts(tree, epic_task_names) or "no tasks"
            lines.append(f"  {epic_name}: {plural(len(epic_task_names), 'task')} — {epic_summary}")
        lines.append("")
    attention = sorted(t for t in tree.task_release if tree.phase(t) in NEEDS_ATTENTION)
    if attention:
        lines.append("Blocked or Failed tasks:")
        lines += [f"  {t}: {tree.phase(t)} ({tree.task_release[t]}, {tree.task_epic[t]})" for t in attention]
    else:
        lines.append("No Blocked or Failed tasks.")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--require-succeeded", metavar="NAME")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root holding plan_specs/")
    args = ap.parse_args(argv)

    tree = collect(args.root.resolve())

    if args.require_succeeded:
        name = args.require_succeeded
        if name not in tree.goals:
            print(f"{name}: no such Goal")
            return 1
        phase = tree.phase(name)
        print(f"{name}: {phase}")
        return 0 if phase == "Succeeded" else 1

    if args.status:
        print("\n".join(render_status(tree)))

    if tree.errors:
        print("\n".join(tree.errors))
        print(f"\n{len(tree.errors)} error(s) in {len(tree.files)} files", file=sys.stderr)
        return 1
    print(
        f"OK: {len(tree.files)} files, {len(tree.epics)} epics, "
        f"{len(tree.task_release)} tasks, {len(tree.release_epics)} releases"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

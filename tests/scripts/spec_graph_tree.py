"""Synthetic spec trees for the epic-graph and task-helper tests (v1-e41-t07).

A test describes releases, epics and tasks as data, changes the one thing it is about, and writes the
tree under `tmp_path`. By default an epic's graph is drawn from its tasks' `spec.context`: a
same-epic prerequisite is an edge to that task's node, and a cross-epic one is an edge to an
`External` node, one per prerequisite. `Task.graph` draws the edges from a different list instead,
which is how a test makes the graph and the context disagree, and `Task.depends_on` names node ids
as written.

`baseline()` is the clean tree: two releases, two epics and three tasks, shaped like the real tree's
commonest case (a same-epic edge and a cross-epic one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

API = "planspec.io/v1alpha1"


@dataclass
class Task:
    number: str
    slug: str
    phase: str = "Pending"
    #: the task names the Goal's spec.context lists
    context: list[str] = field(default_factory=list)
    #: the task names the epic graph's node for this task depends on; None draws them from context
    graph: list[str] | None = None
    #: node ids the task's node depends on, as written; overrides `graph`
    depends_on: list[str] | None = None


@dataclass
class Epic:
    number: str
    slug: str
    release: str
    tasks: list[Task]
    phase: str = "Pending"
    #: task names given an External node that no task node depends on
    externals: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"v1-{self.number}-{self.slug}"

    def task_name(self, task: Task) -> str:
        return f"v1-{self.number}-{task.number}-{task.slug}"

    def task(self, number: str) -> Task:
        return next(t for t in self.tasks if t.number == number)


@dataclass
class SpecTree:
    #: release version -> its Goal's phase
    releases: dict[str, str]
    epics: list[Epic]

    def epic(self, number: str) -> Epic:
        return next(e for e in self.epics if e.number == number)

    def write(self, root: Path) -> Path:
        specs = root / "plan_specs"
        (specs / "releases").mkdir(parents=True)
        for version, phase in self.releases.items():
            epics = [e.name for e in self.epics if e.release == version]
            write_documents(specs / "releases" / f"{version}.yaml", release_documents(version, phase, epics))
        for epic in self.epics:
            folder = specs / "v1" / f"{epic.number}-{epic.slug}"
            folder.mkdir(parents=True)
            write_documents(folder / "epic.yaml", epic_documents(epic, self.task_epics()))
            for task in epic.tasks:
                write_documents(folder / f"{task.number}-{task.slug}.yaml", task_documents(epic, task))
        return root

    def task_epics(self) -> dict[str, Epic]:
        return {e.task_name(t): e for e in self.epics for t in e.tasks}


E01_T01 = "v1-e01-t01-first-step"
E01_T02 = "v1-e01-t02-second-step"
E02_T01 = "v1-e02-t01-later-step"
E01_EPIC = "plan_specs/v1/e01-foundation/epic.yaml"
E02_EPIC = "plan_specs/v1/e02-followup/epic.yaml"
RELEASE_V10 = "plan_specs/releases/v1.0.yaml"


def baseline() -> SpecTree:
    return SpecTree(
        releases={"v1.0": "Pending", "v1.1": "Pending"},
        epics=[
            Epic(
                "e01",
                "foundation",
                "v1.0",
                [
                    Task("t01", "first-step", phase="Succeeded"),
                    Task("t02", "second-step", phase="InProgress", context=[E01_T01]),
                ],
            ),
            Epic("e02", "followup", "v1.1", [Task("t01", "later-step", context=[E01_T01])]),
        ],
    )


def write_documents(path: Path, documents: list[dict]) -> None:
    path.write_text(yaml.safe_dump_all(documents, sort_keys=False, explicit_start=True))


def labels(kind: str, release: str, epic: str | None = None) -> dict:
    out = {"planspec.io/kind": kind, "debate/major-version": "v1", "debate/release": release}
    if epic:
        out["debate/epic"] = epic
    return out


def goal(name: str, title: str, kind: str, release: str, phase: str, epic: str | None = None) -> dict:
    return {
        "apiVersion": API,
        "kind": "Goal",
        "metadata": {"name": name, "labels": labels(kind, release, epic), "annotations": {"debate/title": title}},
        "spec": {
            "description": title,
            "acceptanceCriteria": [{"id": "ac1", "description": "It is done."}],
        },
        "status": {"phase": phase},
    }


def plan(name: str, kind: str, release: str, nodes: list[dict], epic: str | None = None) -> dict:
    return {
        "apiVersion": API,
        "kind": "Plan",
        "metadata": {"name": f"{name}-plan", "labels": labels(kind, release, epic)},
        "spec": {"description": "Graph.", "goalRef": {"name": name}, "graph": {"nodes": nodes}},
        "status": {"phase": "Pending"},
    }


def criteria(name: str) -> list[dict]:
    return [{"type": "command_succeeds", "name": f"{name} succeeds", "command": "true"}]


def release_documents(version: str, phase: str, epics: list[str]) -> list[dict]:
    name = f"release-{version.replace('.', '-')}"
    gate = {
        "apiVersion": API,
        "kind": "Gate",
        "metadata": {"name": f"{name}-gate", "labels": labels("release", version)},
        "spec": {"description": "Review.", "acceptanceCriteria": [{"id": "ac1", "description": "Reviewed."}]},
        "status": {"phase": "Pending"},
    }
    nodes = [{"id": f"epic-{e}", "kind": "External", "name": e, "inputs": {"goalRef": e}} for e in epics]
    return [goal(name, f"{version} release", "release", version, phase), gate, plan(name, "release", version, nodes)]


def epic_documents(epic: Epic, task_epics: dict[str, Epic]) -> list[dict]:
    own = {epic.task_name(t): t.number for t in epic.tasks}
    external_ids: dict[str, str] = {}

    def node_id(prereq: str) -> str:
        if prereq in own:
            return own[prereq]
        return external_ids.setdefault(prereq, f"ext-{prereq}")

    task_nodes = []
    for task in epic.tasks:
        name = epic.task_name(task)
        prereqs = task.context if task.graph is None else task.graph
        node = {
            "id": task.number,
            "kind": "Task",
            "name": task.slug,
            "inputs": {"goalRef": name},
            "dependsOn": task.depends_on if task.depends_on is not None else [node_id(p) for p in prereqs],
            "acceptanceCriteria": criteria(name),
        }
        task_nodes.append(node)
    for prereq in epic.externals:
        external_ids.setdefault(prereq, f"ext-{prereq}")
    external_nodes = [
        {
            "id": ext_id,
            "kind": "External",
            "name": f"Prerequisite {prereq}",
            "inputs": {"goalRef": prereq},
            "description": f"Owned by {task_epics[prereq].name}." if prereq in task_epics else "Owned elsewhere.",
        }
        for prereq, ext_id in external_ids.items()
    ]
    return [
        goal(epic.name, epic.slug, "epic", epic.release, epic.phase, epic.name),
        plan(epic.name, "epic", epic.release, external_nodes + task_nodes, epic.name),
    ]


def task_documents(epic: Epic, task: Task) -> list[dict]:
    name = epic.task_name(task)
    document = goal(name, task.slug, "task", epic.release, task.phase, epic.name)
    if task.context:
        document["spec"]["context"] = [{"kind": "TaskRef", "name": p, "relation": "dependsOn"} for p in task.context]
    node = {"id": "do-it", "kind": "Task", "name": "Do it", "acceptanceCriteria": criteria("it")}
    return [document, plan(name, "task", epic.release, [node], epic.name)]

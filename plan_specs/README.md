# Plan specs

Every unit of work on the Debate Intelligence Platform is described by a
[PlanSpec](https://planspec.io/) document (`apiVersion: planspec.io/v1alpha1`) before
implementation starts. Specs are reviewed in pull requests like code, and
`scripts/validate_specs.py` enforces the rules below in CI.

## Hierarchy

```
Major version (V1 / V2 / V3)
└── Release (minor version, e.g. v1.1)          plan_specs/releases/v1.1.yaml   Goal + Gate + Plan
    └── Epic (belongs to exactly ONE release)    plan_specs/v1/e04-.../epic.yaml Goal + Plan
        └── Task                                 plan_specs/v1/e04-.../t02-*.yaml Goal + Plan
            └── Plan graph nodes (steps with typed acceptance criteria)
```

* **An epic never crosses a major version** and targets a single minor release. Every
  task in an epic ships in that epic's release.
* **Releases** are the incremental in-season drops. A release is done when all of its
  epics' Goals are `Succeeded`, the tag is pushed, and its review Gate is approved.
* Tasks may depend on tasks from *earlier or the same* release in any epic, never on a
  later release.

## Naming

| Thing | `metadata.name` | File |
|---|---|---|
| Release | `release-v1-1` | `plan_specs/releases/v1.1.yaml` |
| Epic | `v1-e04-article-retrieval` | `plan_specs/v1/e04-article-retrieval/epic.yaml` |
| Task | `v1-e04-t02-http-fetcher` | `plan_specs/v1/e04-article-retrieval/t02-http-fetcher.yaml` |
| Task plan | `<task-name>-plan` | same file as the task Goal |

Epic numbers (E01–E28) are global and never reused.

## Labels (identical on every document in a file)

```yaml
labels:
  planspec.io/kind: task | epic | release
  debate/major-version: v1
  debate/release: v1.1
  debate/epic: v1-e04-article-retrieval   # not on releases
```

## Dependencies

* **Inside a task:** `Plan.spec.graph.nodes[].dependsOn` orders the steps.
* **Between tasks:** the task Goal lists prerequisites in
  `spec.context: [{kind: TaskRef, name: <task-name>, relation: dependsOn}]`.
* **Inside an epic:** `epic.yaml`'s Plan is the source of truth for task ordering. Cross-epic
  prerequisites appear there as `External` nodes.
* **Releases** reference their epics as `External` nodes and end in a review `Gate`.

## Acceptance criteria

Goal-level criteria describe observable outcomes. Every `Task` graph node carries at least
one typed, machine-checkable criterion:

| type | required fields |
|---|---|
| `artifact_exists` | `name`, `path` (optional `contentMatch`) |
| `test_passes` | `name`, `command`, `args` |
| `command_succeeds` | `name`, `command`, `args` |
| `endpoint_responds` | `name`, `url` (optional `method`, `expectedStatus`) |
| `custom` | `name` + a description of the manual/human check |

## Status lifecycle

`status.phase` on a task Goal: `Pending → Ready → InProgress → Succeeded` (or `Blocked`,
`Failed`, `Cancelled`). Update it in the same PR that completes the work. An epic Goal is
`Succeeded` when all its tasks are; the epic Plan's criteria check that with
`uv run scripts/validate_specs.py --require-succeeded <task-name>`.

## Repository conventions assumed by task criteria

* Python packages use a `src/` layout: `packages/<pkg>/src/<pkg>/...`, tests in
  `packages/<pkg>/tests/`. Cross-package tests live in `tests/`.
* Tooling: `uv`, `ruff`, `pyright`, `pytest` (+ `respx` for HTTP mocks), `import-linter`
  (`lint-imports`), `terraform` under `infrastructure/`, `pnpm` for `web/`.
* CI never makes live network or model calls; use recorded fixtures and the fake/replay
  ModelRouter.

## Workflow

1. Pick a `Ready` task whose prerequisites are `Succeeded`.
2. Branch `task/<task-name>`, set the Goal to `InProgress`.
3. Implement node by node; each node's criteria must pass before the next.
4. Open a PR referencing the spec path; set the Goal to `Succeeded` in the PR.
5. Scope changes are made by editing the spec in a PR — never silently.

Run `uv run scripts/validate_specs.py` (add `--status` for a roll-up) before pushing.

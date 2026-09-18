# Repo guide for Claude sessions

* **Branching:** `main` = production, `dev` = development environment. Branch `task/<task-name>` from
  `dev` and open PRs into `dev` only. Never push to `dev` or `main` directly, never target `main`
  from a task branch. See docs/process/branching-and-environments.md.

* Work is specified in `plan_specs/` (PlanSpec v1alpha1). **Read the task spec you were
  assigned, its epic.yaml, and `plan_specs/README.md` before editing code.** Implement plan
  nodes in `dependsOn` order; a node is done only when its acceptance criteria pass.
* Never start a task whose `spec.context` prerequisites are not `Succeeded` — say so instead.
* Scope changes go into the spec (in the same PR), never silently into code.
* Keep business logic in `packages/debate_core`; CLI/API/workers stay thin. No boto3,
  typer, fastapi or httpx imports in `debate_core/domain` or `debate_core/application`.
* Evidence integrity is absolute: model output may contain offsets/paragraph ids and
  metadata, never quoted evidence text; unverifiable cards are UNVERIFIED.
* Tests never hit the live network or real models — recorded fixtures and the fake/replay
  ModelRouter only.
* Before finishing: `uv run scripts/validate_specs.py` and `uv run scripts/spec_index.py`,
  set the task Goal `status.phase`, and list any follow-ups in the PR description.

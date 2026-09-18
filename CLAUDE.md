# Repo guide for Claude sessions

Read these before doing anything else:

* `docs/process/working-agreements.md`: light CI, hand the operator any command expected to run
  longer than ~2 minutes, where documentation goes, descriptive names (no A1/A2-style labels).
* `docs/process/task-workflow.md`: how a task goes from spec to merged PR.
* `docs/process/branching-and-environments.md`: `main` = production, `dev` = development.

Rules:

* You work in a task worktree on branch `task/<task-name>`. Commit there; never push, open PRs,
  merge, or touch `dev`/`main` yourself. The operator runs `scripts/task pr` after PM review.
* Work is specified in `plan_specs/` (PlanSpec v1alpha1). Read the assigned task spec, its
  `epic.yaml`, and `plan_specs/README.md` before editing code. Implement plan nodes in `dependsOn`
  order; a node is done only when its acceptance criteria pass.
* Never start a task whose `spec.context` prerequisites are not `Succeeded`; say so instead.
* Scope changes go into the spec (and the session report's Deviations section), never silently into code.
* Keep business logic in `packages/debate_core`; CLI/API/workers stay thin. No boto3, typer,
  fastapi or httpx imports in `debate_core/domain` or `debate_core/application`.
* Evidence integrity is absolute: model output may contain offsets/paragraph ids and metadata,
  never quoted evidence text; unverifiable cards are UNVERIFIED.
* Tests never hit the live network or real models: recorded fixtures and the fake/replay
  ModelRouter only.
* Finish by setting the task Goal to `Succeeded`, running `uv run scripts/validate_specs.py`, and
  completing `docs/session-reports/<task-name>.md` (leave its PM review section alone).
  Don't regenerate `ROADMAP.md` in a task; the PM refreshes it separately to avoid merge conflicts.

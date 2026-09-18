# Contributing

1. Read [docs/process/branching-and-environments.md](docs/process/branching-and-environments.md).
   `main` = prod, `dev` = development environment; everything is validated in dev first.
2. Pick a task spec in `plan_specs/` whose prerequisites are `Succeeded`.
3. `git switch dev && git pull && git switch -c task/<task-name>`
4. Implement the plan nodes in order; each node's acceptance criteria must pass.
5. Run `uv run scripts/validate_specs.py` and `uv run scripts/spec_index.py`; set the task Goal's
   `status.phase` to `Succeeded`.
6. Open a PR **into `dev`** referencing the spec path. Squash-merge when CI is green.
7. Promotion to `main` happens through a `dev` → `main` promotion PR once dev is validated.

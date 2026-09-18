# Contributing

Start with [docs/process/working-agreements.md](docs/process/working-agreements.md) and
[docs/process/task-workflow.md](docs/process/task-workflow.md).

```bash
scripts/task ready                 # tasks whose prerequisites are done
scripts/task start <task>          # worktree + branch off dev, launches the Claude session
scripts/task report <task>         # hand the session report to the PM
scripts/task pr <task>             # after PM verdict ACCEPTED: push + PR into dev
scripts/task finish <task>         # after the PR is merged: remove worktree and branches
```

`main` = production, `dev` = development environment; everything is validated in dev before a
`dev` → `main` promotion ([details](docs/process/branching-and-environments.md)).
Squash-merge task PRs into `dev`; promotions into `main` are merge commits.

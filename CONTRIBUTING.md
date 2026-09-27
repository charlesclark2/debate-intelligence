# Contributing

Start with [docs/process/working-agreements.md](docs/process/working-agreements.md) and
[docs/process/task-workflow.md](docs/process/task-workflow.md).

## No real debate data, ever

This repository is public. No real debate file, disclosure, card or excerpt, and no real school
name, team code or debater name, goes into it: not in code, fixtures, tests, logs, docs, issues or
pull requests, and not "scrubbed". Fixtures use invented schools and team codes. The rule is
[prohibited use 9](docs/policies/caselist-data-use.md#prohibited-uses) of the caselist data-use
policy. Requests to remove something from the evidence corpus go by email as described in
[Removal](docs/policies/caselist-data-use.md#removal), never in an issue.

## Branches and the task flow

`main` = production, `dev` = development environment; everything is validated in dev before a
`dev` → `main` promotion ([details](docs/process/branching-and-environments.md)).

1. Every piece of work is a PlanSpec task under [`plan_specs/`](plan_specs/README.md).
2. It is built on a branch `task/<task-name>` (for example `task/v1-e04-t02-http-fetcher`),
   branched from `dev` in its own worktree.
3. The task's pull request targets `dev`, the default branch, and is squash-merged.
4. `dev` reaches `main` only through a promotion pull request, merged with a merge commit.
   Urgent production fixes use `hotfix/<slug>` from `main` and are back-merged into `dev`.

Nobody pushes directly to `dev` or `main`, and neither is force-pushed or rebased; the
`protect-dev` and `protect-main` rulesets enforce that.

```bash
scripts/task ready                 # tasks whose prerequisites are done
scripts/task start <task>          # worktree + branch off dev, launches the Claude session
scripts/task report <task>         # hand the session report to the PM
scripts/task pr <task>             # after PM verdict ACCEPTED: push + PR into dev
scripts/task finish <task>         # after the PR is merged: remove worktree and branches
```

## Issues

Use the **Bug** or **Task** issue form. A task issue points at its spec path under
`plan_specs/`; the spec, not the issue, is the contract.

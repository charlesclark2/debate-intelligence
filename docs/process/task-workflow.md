# Task workflow: from spec to merged PR

Every piece of implementation work is one PlanSpec task, done by one Claude session in its own
git worktree, reviewed by the PM against its spec, and merged into `dev` through a pull request.
`scripts/task` automates each step. Branching and environments are described in
[branching-and-environments.md](branching-and-environments.md); the rules every session follows
are in [working-agreements.md](working-agreements.md).

## Roles

| Role | Who | Responsibilities |
|---|---|---|
| Operator | Charlie | Starts tasks, runs anything over ~2 minutes, opens and merges PRs, owns GitHub/AWS settings |
| Implementation session | Claude Code, one per task, launched in the task's worktree | Implements the spec, runs the acceptance criteria, writes the session report, commits locally |
| PM | Claude in the project chat | Reviews the report and diff against the spec, records the verdict, maintains specs and roadmap |

## Lifecycle

```
scripts/task ready ──▶ scripts/task start <task> ──▶ session implements + writes report
                                                         │
                               scripts/task report <task> ▼  (hand to PM)
                                                   PM review ──CHANGES_REQUESTED──▶ scripts/task resume <task>
                                                         │ ACCEPTED
                                    scripts/task pr <task> ▼
                                   CI green, you squash-merge into dev
                                                         │
                                scripts/task finish <task> ▼  worktree + branches removed, local dev updated
```

### 1. Pick a task

```bash
scripts/task ready
```

Lists every `Pending` task on `origin/dev` whose prerequisites are all `Succeeded`, ordered by
release. Pick from the lowest release first.

### 2. Start it

```bash
scripts/task start v1-e01-t03-uv-workspace-tooling
```

This:

1. fetches `origin/dev` and creates a worktree at
   `../debate-intelligence-worktrees/<task>` on a new branch `task/<task>`;
2. refuses (and cleans up) if any prerequisite is not `Succeeded` on `origin/dev` (`--force`
   overrides);
3. sets the task Goal's `status.phase` to `InProgress`, creates
   `docs/session-reports/<task>.md` from the [template](session-report-template.md), and commits both;
4. writes the kickoff prompt to `<worktree>/.task/prompt.md` (not committed);
5. launches `claude` in the worktree with that prompt. Use `--no-launch` to skip, and paste the
   prompt yourself (`scripts/task prompt <task>`).

Several tasks can run at once, one worktree each, as long as their prerequisites allow it.

### 3. The session works

The prompt tells the session which spec to execute, to implement the plan nodes in order, to
hand you any command that runs longer than about 2 minutes, to commit locally but never push,
and to finish by setting the phase to `Succeeded` and completing the session report.

If you close the terminal, `scripts/task resume <task>` reopens the same conversation.

### 4. PM review

```bash
scripts/task report <task>     # prints the report and copies it to the clipboard
scripts/task review <task>     # commits and diffstat against origin/dev
```

Give the report to the PM (paste it, or just name the task: the worktrees live under the
connected `Debate Intelligence Tool` folder, so the PM can read the report and diff directly).
The PM checks the work against the spec: every Goal criterion and node criterion, scope,
architecture guardrails, and the working agreements. The PM then writes the **PM review**
section of the report:

* `ACCEPTED`: ready for a PR.
* `CHANGES_REQUESTED`: the notes list what to fix. Run `scripts/task resume <task>` and tell the
  session to address the PM notes; repeat the review.

The PM commits the verdict on the task branch, or tells you the exact edit to make.

### 5. Open the PR

```bash
scripts/task pr <task>
```

Refuses unless the worktree is clean, the verdict is `ACCEPTED`, the spec phase is `Succeeded`,
and the branch contains the latest `origin/dev` (otherwise run `scripts/task sync <task>`). It
runs spec validation, pushes `task/<task>`, and opens a PR into `dev` whose body is built from
the report. With the GitHub CLI (`brew install gh`, then `gh auth login`) the PR is created
directly; without it the compare page opens in your browser with the body on the clipboard.

### 6. Merge

When the `ci` check is green, **squash-merge** the PR into `dev` on GitHub.

### 7. Close out

```bash
scripts/task finish <task>
```

Confirms the merge (through `gh`, or by checking that `origin/dev` records the task as
`Succeeded`), removes the worktree, deletes the local and remote `task/<task>` branches, prunes
worktree metadata, and fast-forwards your local `dev`. It refuses to delete uncommitted work
unless you pass `--force`. To throw a task away without merging: `scripts/task finish <task> --abandon`.

`scripts/task list` shows every open task worktree with its phase, PM verdict and PR state, so
nothing is left hanging.

## Keep your main checkout on `dev`

The main clone (`Debate Intelligence Tool/debate-intelligence`) should stay on `dev` with no
local edits; all work happens in task worktrees. `scripts/task` lives on `dev`, and `finish`
fast-forwards that checkout for you.

## Changes that are not a task

Process, documentation, or spec-only changes that no task spec covers follow the same path by
hand: a branch off `dev` (`docs/<slug>` or `specs/<slug>`), a PR into `dev`, merge, delete the
branch. If the change is substantial, the PM writes a task spec for it first.

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
| Implementation session | Claude Code (VS Code extension by default), one per task, opened on the task's worktree | Implements the spec, runs the acceptance criteria, writes the session report, commits locally |
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
release. Pick from the lowest release first. Tasks that are already started are hidden, because
`origin/dev` still records them as `Pending` until their PR merges. A task counts as started when a
local `task/<name>` branch exists or `origin/task/<name>` has been pushed. The footer shows how
many were hidden. `scripts/task ready --all` lists them too, marked `[started]`, and
`scripts/task list` shows the ones with a worktree on this machine.

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
5. opens the session, using the launcher chosen with `--launch` or `DEBATE_TASK_LAUNCHER`:
   * **`vscode` (default):** opens the worktree in a **new VS Code window** and copies the kickoff
     prompt to the clipboard. In that window, open Claude Code (Cmd+Esc), paste, press Enter.
     Check the window title is the task folder, not the main clone; the session must run
     inside the worktree.
   * **`terminal`:** runs `claude` in the worktree with the prompt already submitted.
   * **`none`** (or `--no-launch`): prints where the prompt is; `scripts/task prompt <task>`
     prints it again and copies it to the clipboard.

The VS Code launcher uses the `code` command if it's installed (VS Code Command Palette →
*Shell Command: Install 'code' command in PATH*); otherwise it falls back to `open -a`.

Several tasks can run at once, one worktree each, as long as their prerequisites allow it.

### 3. The session works

The prompt tells the session which spec to execute, to implement the plan nodes in order, to
hand you any command that runs longer than about 2 minutes, to commit locally but never push,
and to finish by setting the phase to `Succeeded` and completing the session report.

`scripts/task resume <task>` reopens the worktree in VS Code; continue the task's conversation
from Claude Code's past-conversations list. With `--launch terminal` it runs `claude --continue`.

### 4. PM review

```bash
scripts/task report <task>     # prints the report and copies it to the clipboard
scripts/task review <task>     # commits and diffstat against origin/dev
```

Give the report to the PM (paste it, or just name the task: the worktrees live under the
connected `debate-intelligence-tool` folder, so the PM can read the report and diff directly).
The PM checks the work against the spec: every Goal criterion and node criterion, scope,
architecture guardrails, and the working agreements. The PM then writes the **PM review**
section of the report:

* `ACCEPTED`: ready for a PR.
* `CHANGES_REQUESTED`: the notes list what to fix. Reopen the session (`scripts/task resume
  <task>`) and ask it to address the PM notes in the report; repeat the review.

The PM writes the verdict straight into the report file in the worktree but does not commit
it (the PM's shell can't run git against your worktrees). With `CHANGES_REQUESTED`, the
session commits the report along with its fixes. With `ACCEPTED`, `scripts/task pr` commits
the report for you (`PM review: ACCEPTED`) when it is the only uncommitted change.

If you move or rename the folder that holds the repo and worktrees, run `git worktree repair`
from the main clone, passing each worktree's new path. Worktrees store absolute paths.

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

The main clone (`debate-intelligence-tool/debate-intelligence`) should stay on `dev` with no
local edits; all work happens in task worktrees. `scripts/task` lives on `dev`, and `finish`
fast-forwards that checkout for you.

## Changes that are not a task

The PM also refreshes `ROADMAP.md` this way (`specs/roadmap-refresh`) after a batch of merges.
Task sessions never regenerate it, so parallel task PRs don't conflict on it.

Process, documentation, or spec-only changes that no task spec covers follow the same path by
hand: a branch off `dev` (`docs/<slug>`, `specs/<slug>` or `tooling/<slug>`), a PR into `dev`, merge, delete the
branch. If the change is substantial, the PM writes a task spec for it first.

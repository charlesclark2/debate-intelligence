# Session report: v1-e01-t18-restart-partial-tasks

| | |
|---|---|
| Task | `v1-e01-t18-restart-partial-tasks` — scripts/task restarts a task that merged partially |
| Spec | [`plan_specs/v1/e01-repo-foundation/t18-restart-partial-tasks.yaml`](../../plan_specs/v1/e01-repo-foundation/t18-restart-partial-tasks.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t18-restart-partial-tasks` |
| Session status | COMPLETE |

## Summary

`scripts/task resume <task>` now restarts a task merged with `--partial`. If the task is
InProgress on `origin/dev`, its report is there, and it has no worktree and no branch, `resume`:

* recreates both from `origin/dev`;
* runs `uv sync --all-packages`;
* writes a `.task/prompt.md` that opens with "This is a resumed task: append to the existing
  report, keep every earlier PM review";
* commits nothing.

`resume --dry-run` runs every check and creates nothing. `start` now refuses such a task and points
at `resume`, where it used to die part-way. A failure after the worktree is created removes that
run's worktree and branch through an EXIT trap. The trap is armed only after the existence checks,
so it never touches anything that was already there.

The verdict rule is now the last verdict line in the report, everywhere the tooling reads one:

* `scripts/task pr` and `list`;
* `finish --partial`, which also requires `origin/dev`'s report to be the branch's report;
* the PR body's PM review section.

All 68 reports that read ACCEPTED before this change still do, and a test walks every one of them.

**What the PM should look at first:**

* Deviations 2 and 3: two verdict-reading paths I fixed that the brief did not name.
* Deviation 1: v1-e31-t07's report does not show the renamed-label workaround.

The dry run against the real v1-e01-t16, which is InProgress on `origin/dev` with no worktree,
read its state correctly and created nothing.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `restart` (Resume a partly merged task) | Done | Tests committed first (`624756b`) and run against today's scripts: both failures reproduced. Then the implementation (`af8449c`), docs and spec amendment (`c894c47`), PR-body fix (`1a7a86c`). |

## Acceptance criteria

All test runs below used a fresh `HYPOTHESIS_STORAGE_DIRECTORY`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: one documented command recreates the worktree and branch from origin/dev, syncs, writes a resumed prompt, commits nothing; shown failing first with today's `start` | PASS | **Failing first.** With today's scripts, `scripts/task start v1-e99-t01-partly-merged` in the throwaway repo exits 1 with no error message (stdout ends `nothing to commit, working tree clean`) and leaves both the worktree and the branch: `worktree left behind: True`, `branch left behind: True`, 2 registered worktrees. That is 2026-10-02 reproduced. With the tests committed and the scripts unchanged, `test_start_refuses_a_partly_merged_task_and_points_at_resume`, `test_resume_recreates_the_worktree_and_branch_from_origin_dev` and the resume rollback cases failed. **After:** `uv run --frozen pytest tests/scripts/test_task_restart.py` → `90 passed in 5.12s`. `test_resume_recreates…` asserts the branch is `task/<task>` at exactly `origin/dev`'s commit (no commit of any kind), a clean tree, and a report byte-identical to `dev`'s. It also asserts the prompt's resumed-task note and the `uv sync --quiet --all-packages` call. `test_start_refuses…` asserts the message names `scripts/task resume <task>` and that nothing is created. Documented in `docs/process/task-workflow.md` § "Coming back to a partly merged task". |
| ac2: a step that fails part-way removes what that run created, so a retry starts clean; forced failure after the worktree is created | PASS | `test_a_failure_after_the_worktree_exists_removes_what_the_run_created` (5 cases) forces a failure after "Creating worktree" by making the stubbed `uv` fail one helper subcommand: `start` at `info`, `set-phase` and `prompt` (the last after the start commit); `resume` at `info` and `prompt-resumed`. Each asserts no worktree directory, no branch and only the main worktree registered. A retry then succeeds. Today's scripts failed 4 of the 5; only `start`/`info` already cleaned up by hand. `test_a_refused_start_leaves_an_existing_worktree_and_its_work_alone` and `test_a_refused_run_leaves_an_existing_branch_alone` (start and resume) show the rollback never touches a worktree, branch, uncommitted file, `.task/` or report that existed first. |
| ac3: the verdict check reads the current review; a report with an earlier ACCEPTED and a current PENDING is refused by `scripts/task pr`, shown with a fixture; the convention is in task-workflow.md and the template | PASS | Fixture `tests/scripts/fixtures/task_restart/resumed_review_pending.md` is hand-written: the first session's review ACCEPTED, then a resumed section, then an empty PENDING review. **Failing first:** today's `scripts/task pr <task> --partial` exits 0 on it, pushes the branch and calls `gh pr create`. **After:** `test_pr_refuses_a_report_whose_current_review_is_pending` sees `PM verdict is PENDING`, no push and no `gh pr create`. The positive control, `test_pr_opens_once_the_current_review_is_accepted`, opens the PR, and its body quotes the new review, not the 2026-09-23 one. `test_an_existing_accepted_report_still_reads_accepted` × 68 and `test_the_walk_over_existing_reports_is_not_vacuous` pass. Convention: `task-workflow.md` § "4. PM review" ("A later review is appended; no earlier review is ever renamed or edited") and the template's session rules and PM-review comment. |
| Node `restart`: both failures shown, then fixed | PASS | As ac1 and ac3 above. |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 310 files, 38 epics, 252 tasks, 20 releases` |
| Neighbouring suites | PASS | `uv run --frozen pytest tests/docs tests/architecture tests/specs tests/scripts -q --no-cov` → `782 passed in 30.69s` (includes the link checker's test, which caught a fixture link I then removed). `ruff check`/`ruff format --check` on `scripts tests/scripts` → clean. `shellcheck scripts/task` → clean. `scripts/check_links.py` → `OK: 1268 relative links and anchors in 175 Markdown files`. `docs_index.py --check-descriptions` → all 30 documents have a description. |

### Hypothesis

`test_the_last_review_decides_whatever_the_earlier_ones_say` builds a report of 1 to 5 reviews. Each
review's verdict is ACCEPTED, CHANGES_REQUESTED, PENDING or an unknown word, and its notes sometimes
include a renamed label. The test asserts the result is the last review's verdict.

`--hypothesis-show-statistics` on a fresh database: 100 passing examples. **46.79% have first and
last verdicts that differ**, the case where reading the first verdict gives the wrong answer; 44.95%
agree. The property is not the only check of the rule: the fixture tests catch the same mutant.

## Mutation testing

Method:

* Each mutant was applied to the committed code (`af8449c`).
* For each, the whole test file ran on a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`.
* The file was then restored byte for byte, and `git diff --quiet` confirmed it matched HEAD.
* The runs went in two batches of four, 36.7 s and 37.0 s.
* Times are the whole file's pytest wall time. Every mutant was caught by assertions, not by a
  collection error.

| Mutant | Result | Caught by |
|---|---|---|
| First verdict read instead of last (`found[0]` for `found[-1]`) | CAUGHT, 11.1 s, 3 failed | `test_pr_refuses_a_report_whose_current_review_is_pending`, the property, `test_the_last_verdict_line_decides` |
| start's refusal of a partly merged task removed | CAUGHT, 6.9 s, 1 failed | `test_start_refuses_a_partly_merged_task_and_points_at_resume` |
| Rollback skipped (trap never armed) | CAUGHT, 7.9 s, 5 failed | all five forced-failure cases |
| Rollback removes a pre-existing worktree, armed before start's existence checks | CAUGHT, 10.8 s, 2 failed | `test_a_refused_start_leaves_an_existing_worktree_and_its_work_alone`, `test_a_refused_run_leaves_an_existing_branch_alone[start]` |
| Rollback removes a pre-existing worktree, armed before resume reopens one | CAUGHT, 11.2 s, 2 failed | `test_resume_on_an_existing_worktree_still_just_reopens_it`, `test_a_refused_run_leaves_an_existing_branch_alone[resume]` |
| Empty commit restored (`commit --allow-empty` in resume) | CAUGHT, 6.4 s, 1 failed | `test_resume_recreates_the_worktree_and_branch_from_origin_dev` |
| Empty commit restored the way start commits (`add` + `commit`, dies with nothing to commit) | CAUGHT, 8.4 s, 5 failed | the resume tests; the rollback then leaves nothing behind |
| finish --partial's branch-report comparison removed (my addition, Deviation 2) | CAUGHT, 10.8 s, 1 failed | `test_finish_partial_refuses_until_the_resumed_report_reaches_dev` |

The walk over existing reports does not catch the first-verdict mutant, as expected. No report in
the repo has two unrenamed verdict lines, so first and last agree on every one. That walk guards the
other direction: a new rule that breaks an accepted report.

## Proof against a real partial task (read-only)

Before the run: `origin/dev` had `v1-e01-t16-generated-docs-index` InProgress with its report
present; there was no worktree and no `task/` branch, local or on origin. The run, from this
worktree, took 0.66 s:

```text
$ scripts/task resume v1-e01-t16-generated-docs-index --dry-run
==> Fetching origin/dev
Dry run: v1-e01-t16-generated-docs-index was merged with --partial and can be resumed. Nothing was created.
  origin/dev:   37e2b17; plan_specs/v1/e01-repo-foundation/t16-generated-docs-index.yaml says InProgress
  report:       docs/session-reports/v1-e01-t16-generated-docs-index.md is on origin/dev; its last PM verdict is ACCEPTED
  would create: worktree …/debate-intelligence-worktrees/v1-e01-t16-generated-docs-index on a new branch task/v1-e01-t16-generated-docs-index from origin/dev
  would sync:   uv sync --all-packages in the worktree
  would write:  …/v1-e01-t16-generated-docs-index/.task/prompt.md, the resumed-task prompt
  would commit: nothing
```

Afterwards: still 7 registered worktrees, no t16 directory, no `task/v1-e01-t16…` branch, and the
main checkout clean. The only writes were the remote-tracking refs from `git fetch`, which every
`scripts/task` command does. Two more read-only checks against the real repo:

* `resume v1-e01-t19-paste-safe-command-blocks --dry-run` exits 1 with `… is Pending on origin/dev,
  so there is nothing to resume; use: scripts/task start …`.
* `resume v1-e01-t18-restart-partial-tasks --dry-run` reports this worktree and that resume would
  reopen it.

t16 was not resumed. Operator follow-up 1 says how to do it.

## Files changed

* `scripts/task`:
  * `resume` gains the recreate path, `--dry-run` and `--no-launch`;
  * `start` refuses a task whose report is already on `origin/dev`;
  * the shared `create_task_worktree`/`rollback` (EXIT trap) and `sync_workspace_venv`;
  * `finish --partial` checks the last verdict and that `dev`'s report is the branch's;
  * help text updated.
* `scripts/task_helper.py`:
  * `report_verdict` (the last verdict line), used by `verdict` and the new `verdict-of <file|->`;
  * `prompt-resumed` and its prompt variant (the `start` prompt is byte-identical to before);
  * `section()` takes the last section with a heading, for the PR body.
* `tests/scripts/test_task_restart.py`, `tests/scripts/fixtures/task_restart/` (2 hand-written
  reports): every test above. The shell tests run the real scripts in a throwaway repo with a bare
  `origin`; `uv`, `gh`, `pbcopy`, `code` and `open` are stubs.
* `docs/process/task-workflow.md`:
  * start's refusal and rollback;
  * resume's new path;
  * the appended-review rule in § 4;
  * § 5 and the `finish --partial` text;
  * a new section, "Coming back to a partly merged task".

  v1-e01-t16's newer text ("Changes that are not a task") is unchanged.
* `docs/process/session-report-template.md`: the appended-review rule in the session rules, and the
  PM-review comment new reports copy.
* `plan_specs/v1/e01-repo-foundation/t18-restart-partial-tasks.yaml`: `constraints.packages`
  amended with the template and `tests/scripts`, with the comment "added on the PM's instruction,
  2026-10-08". Goal phase set to `Succeeded`.

## Deviations from the spec

1. **v1-e31-t07's report does not show the renamed-label workaround.** The brief said all three
   named reports did. v1-e31-t07 has one PM review and no renamed label. What it does show is a
   session appending a section ("PM-requested check") *after* the PM review. Only v1-e31-t05
   (`**Verdict (first session):**`) and v1-e03-t05 (`**Verdict (first review):**`) renamed one, so
   `task-workflow.md` says "two reports". All three still read ACCEPTED under the new rule. t07's
   pattern is harmless under it, because the appended section has no verdict line.
2. **`finish --partial` changed, though only `pr` was named.** Its merge check was `grep -q` for any
   line reading `**Verdict:** ACCEPTED` in `origin/dev`'s report. That is a verdict check that
   passes on a review of earlier work, which the forbidden list rules out. For a resumed task whose
   second pull request is still open, `dev` already carries the first session's accepted report. So
   `finish --partial` would have "confirmed" the merge and deleted the worktree, the local branch
   and the remote branch, closing the open PR. Today's script did exactly that in the test.

   The check now takes the last verdict, and, while the task branch exists, requires `dev`'s report
   to be the same blob as the branch's (a squash merge carries it over byte for byte). With no local
   branch it falls back to the last verdict alone. If `dev` later edits the report, finish refuses,
   and `--force` is the way past.
3. **The PR body quotes the last PM review.** `pr-body` took the first `## PM review` section. A
   resumed task's pull request would have quoted the first session's review and notes under the new
   review's ACCEPTED. It now takes the last. A test failed first, and the PR body for all 69 reports
   in the repo is byte-identical before and after.
4. **The template entry in `constraints.packages`** is already under `docs/process`. I listed it
   explicitly anyway, as the brief asked for the template's location to be named.

## Decisions and assumptions

1. **One command, `resume`, two paths.** With a worktree present it reopens it exactly as before.
   Without one it recreates a partly merged task. The recreated session launches like `start` (the
   prompt goes on the clipboard, or `claude` runs with it), because it is a new conversation.
2. **What resume refuses**, each before creating anything:
   * A task that is Pending or Ready (pointed at `start`).
   * Any phase other than InProgress.
   * InProgress without a report on `dev`.
   * A local branch with no worktree. Resume never adopts an existing branch: it names the branch
     and prints the `git worktree add` that attaches it.
   * An `origin/task/<task>` branch, which probably means a PR is open.
3. **start refuses any task whose report is on `origin/dev`**, not only InProgress ones. The message
   points at `resume` when the phase is InProgress, and says start never overwrites a report
   otherwise.
4. **How the rollback works.**
   * Both commands check that the worktree and branch are absent, then arm the trap, then create.
     So everything the trap removes was created by that run.
   * INT/TERM become `exit 130`, so Ctrl-C also rolls back.
   * `rm -rf` is used only as a fallback when `git worktree remove --force` fails, and only on the
     path this run created.
   * `.task/` and `.venv` go with the worktree. The empty worktree parent is removed with `rmdir`,
     as `finish` already does.
   * The trap is disarmed once the prompt is written and the venv synced, before the launcher. A
     launcher failure leaves a finished worktree in place.
5. **The verdict rule is literal**: the last line starting with the label, wherever it is. One change
   to the regex: the gap after the label is `[ \t]*`, not `\s*`, so a match cannot run onto the next
   line. The 68-report walk shows this changed nothing. I did not exclude fenced code blocks; see
   Follow-up work.
6. **The 68-report test compares against the old rule, copied by hand into the test**, not against
   the helper's own output. Under the old rule 68 reports read ACCEPTED, and this task's reads
   PENDING. The test asserts each of the 68 reads ACCEPTED under `report_verdict`. A second test
   keeps the walk from being vacuous: at least 60 reports, including both renamed-label ones.
7. **What the tests stub.** The `uv` stub runs the helper with the test interpreter, so `uv sync` is
   logged, not run. `sync_workspace_venv` is the code `start` already ran, moved into a function
   unchanged.
8. **`--dry-run` fetches**, which updates remote-tracking refs as every `scripts/task` command does,
   and runs `ls-remote`. It also prints the last verdict in `dev`'s report, so the operator sees what
   they are reopening.

## Operator follow-ups

None required.

**1. Resuming v1-e01-t16 (when the PM wants it, not before).** Expected runtime: under a minute,
most of it `uv sync`. Run from the main clone, after this task's PR has merged and `finish` has
fast-forwarded local `dev`, because that is where the new `scripts/task` will be. First check where
you are and do the read-only check. Success looks like: the branch line prints `dev`, and the dry
run prints `can be resumed. Nothing was created.` with t16's spec `InProgress`.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
scripts/task resume v1-e01-t16-generated-docs-index --dry-run
```

Then the real resume:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
scripts/task resume v1-e01-t16-generated-docs-index
```

Success looks like:

* the summary ends `Branch: task/v1-e01-t16-generated-docs-index, at origin/dev; nothing committed`;
* a VS Code window opens on the new worktree, with the prompt on the clipboard;
* `git -C ../debate-intelligence-worktrees/v1-e01-t16-generated-docs-index log -1 --oneline` shows
  `origin/dev`'s tip.

Paste the prompt together with the PM's instructions for that session.

**2. The full suite** runs in CI on this PR. The suites these changes could affect ran here
(782 passed); the full default selection is over the two-minute line, so I did not run it.

## Follow-up work

1. **`pr --partial`'s "the report records what is still open" check reads the whole report**
   (`grep NOT RUN|PARTIAL|…`). A resumed report always contains the first session's `NOT RUN`, so
   the check passes even when the resumed session's own section closes everything. It is not a
   verdict check, so I left it. It could read only the text after the last-but-one PM review.
   Belongs to E01 tooling; the PM decides.
2. **Verdict lines inside fenced code blocks count.** A session that quotes the label at the start
   of a line inside a code block, after the PM review, would change what `scripts/task pr` reads.
   Ignoring fenced blocks is a small hardening, but it changes the PM's literal rule, so I didn't.
3. **`task-workflow.md` § 4's command block has `#` comments**, against working agreement 9. That
   is v1-e01-t19's fix (its check and its fixes). I left the block alone so the two PRs don't
   conflict.
4. `pyright scripts/task_helper.py` reports 2 errors, both present before this task (`die()`'s
   `None` return and `die(__doc__)`). CI type-checks only `packages/`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

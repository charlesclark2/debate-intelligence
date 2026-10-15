# Session report: v1-e01-t26-dispatch-opens-back-merge

| | |
|---|---|
| Task | `v1-e01-t26-dispatch-opens-back-merge` — The manual sweep also opens the back-merge pull request |
| Spec | [`plan_specs/v1/e01-repo-foundation/t26-dispatch-opens-back-merge.yaml`](../../plan_specs/v1/e01-repo-foundation/t26-dispatch-opens-back-merge.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t26-dispatch-opens-back-merge` |
| Session status | PARTIAL: built and tested offline. The sandbox half of ac1 is the operator's. Goal stays `InProgress` |

## Summary

`back-merge.yml`'s `open-back-merge-pull-request` job now runs on every trigger the workflow has:
a push to `main`, the schedule and a dispatch. Before this, it ran on a push only. After a lost
push, a dispatch from the Actions tab now opens the back-merge pull request that the red
`back-merge` check names, so recovery takes one click.

The schedule opens it too. The justification is under Decisions. When `main` and `dev` agree, the
job calls nothing on GitHub and prints one `OK:` line.

The job keeps its permissions, `contents: read` and `pull-requests: write`, and its concurrency
group. It gains the sweep's gate, which refuses any ref but `main` or `dev`, because a dispatch can
name any branch and the job runs the checked-out script before the step that holds the token.

The process doc and the hotfix template no longer say that only a push opens the pull request. The
hand-run `gh pr create` stays in the doc for one case: the job itself cannot open it.

**For the PM:** read Decisions first (the schedule), then Deviations 1 and 2. The Goal stays
`InProgress` until the operator runs the sandbox proof under Operator follow-ups. It needs their
GitHub credentials and takes about 10 minutes.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `dispatch-opens` — Dispatch reaches the open job | Done, except the sandbox check (operator) | Tests first (fbdbd73, red), the workflow (ba68365), the doc and the hotfix template (9ff02bd), and a sharper step-logic harness (6bc5621). The sandbox procedure is under Operator follow-ups. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a dispatch on a repository where `main` holds a commit `dev` lacks opens the back-merge pull request, or names the open one, by shape test and in a sandbox | **Shape test: PASS. Sandbox: NOT RUN (operator)** | **Shape.** `test_every_trigger_runs_both_the_rerun_job_and_the_open_job`: the triggers are pinned to exactly `push`, `schedule` and `workflow_dispatch`, and neither job has an `if`. `test_both_jobs_refuse_any_ref_but_main_or_dev_before_checking_anything_out` covers the ref gate. **Step logic.** These tests run the job's own `run:` blocks with `bash -e` against a throwaway repository and a recording fake `gh`: `test_with_no_back_merge_pull_request_open_the_job_opens_one` (one `pr list --base dev --head main --state open`, then exactly one `pr create --base dev --head main --label back-merge`, with the hotfix's SHA in the body); `test_with_one_back_merge_pull_request_open_the_job_names_it_and_opens_no_second` (no `pr create`, `pr edit 17 --add-label back-merge`, and the log says `Back-merge pull request #17 is open`); `test_when_main_and_dev_agree_the_job_does_nothing_visible` (`main` holds only a promotion's merge commit: zero `gh` calls, no `::` workflow command, and the log starts `OK: `). **Sandbox:** operator follow-up 1. |
| ac2: the permission shape v1-e01-t15 established is otherwise unchanged, and actionlint stays clean | PASS | `test_back_merge_grants_nothing_at_the_top_and_actions_write_only_to_the_rerun_job` passes unchanged: `permissions: {}` at the top; the open job `{contents: read, pull-requests: write}`; the sweep `{actions: write, checks: read, contents: read, pull-requests: read}`. A new test, `test_no_other_workflow_job_holds_pull_requests_write_or_contents_write`, lists every holder of either write across all workflows. It finds exactly the open job's `pull-requests: write`, `dev-prerelease.yml` `publish`'s `contents: write`, and `refresh-generated-files.yml` `regenerate`'s two writes, and no top-level grant of either. `uv run --frozen scripts/actionlint.sh` → `actionlint 1.7.12 (darwin_arm64, checksum verified), with shellcheck 0.11.0 …`, no findings, exit 0. |
| ac3: branching-and-environments.md drops the hand-run `gh pr create` from the recovery steps or says when it is still needed | PASS | The lost-push recovery is now a dispatch: "dispatch it: that one run re-runs the guards and opens the back-merge pull request." The hand-run command stays under a renamed bullet, **A back-merge pull request the workflow could not open**, for the one case where it is still needed: a run's `open-back-merge-pull-request` job fails, and a dispatch fails the same way. One cause is the Actions setting that lets workflows create pull requests being off. The cadence wording ("about every two to five hours … measured on 2026-10-15") and the promotion checklist's dispatch step are unchanged. `uv run scripts/check_links.py` → `OK: 1560 relative links and anchors in 222 Markdown files`. |
| dispatch-opens: A dispatch opened the back-merge pull request in a sandbox | **NOT RUN** | Needs the operator's GitHub credentials. Operator follow-up 1. |

### Shown failing first

The tests were committed before the workflow changed (fbdbd73), then run against the unchanged
`back-merge.yml`:

```bash
uv run --frozen pytest tests/scripts/test_back_merge_workflow.py -q
```

```text
E           AssertionError: open-back-merge-pull-request
E           assert 'if' not in {'if': "github.event_name == 'push'", 'concurrency': {'group': 'back-merge', 'cancel-in-progress': False}, 'runs-on': 'ubuntu-24.04', 'timeout-minutes': 5, ...}
E           AssertionError: open-back-merge-pull-request
E           assert None == "github.ref != 'refs/heads/main' && github.ref != 'refs/heads/dev'"
FAILED tests/scripts/test_back_merge_workflow.py::test_every_trigger_runs_both_the_rerun_job_and_the_open_job
FAILED tests/scripts/test_back_merge_workflow.py::test_both_jobs_refuse_any_ref_but_main_or_dev_before_checking_anything_out
2 failed, 16 passed in 2.25s
```

The three step-logic tests passed on the old file. The job was already idempotent, and the tests
pin that behaviour rather than add it. The mutants below show that each of them can fail. After
ba68365: `18 passed in 1.75s`.

### Mutation run

Each mutant was applied to the committed file. Then `test_back_merge_workflow.py`,
`test_rerun_promotion_guards.py` and `test_workflow_runners.py` ran (59 tests), and the file was
restored with `git checkout`. Its SHA-256 matched before and after for all 13. Every run had a new,
empty `HYPOTHESIS_STORAGE_DIRECTORY`; no Hypothesis property is involved. `git status --porcelain`
was empty afterwards. The script is `mutate.py` in the session scratchpad and is not committed.
Wall time was 28 s.

| Mutant | File | Caught by (failed / 59) |
|---|---|---|
| open job back to push only (`if: github.event_name == 'push'`) | back-merge.yml | 1: `test_every_trigger_runs_both_the_rerun_job_and_the_open_job` |
| open job skips the schedule (`!= 'schedule'`) | back-merge.yml | 1: the same |
| open job skips the dispatch (`!= 'workflow_dispatch'`) | back-merge.yml | 1: the same |
| open job's ref gate removed | back-merge.yml | 1: `test_both_jobs_refuse_any_ref_but_main_or_dev_before_checking_anything_out` |
| `pull-requests: write` moved off the open job | back-merge.yml | 2: `…grants_nothing_at_the_top…`, `test_no_other_workflow_job_holds_pull_requests_write_or_contents_write` |
| `contents: write` on the open job | back-merge.yml | 2: the same two |
| `pull-requests: write` added to the sweep | back-merge.yml | 2: the same two |
| `pull-requests: write` at the workflow's top level | back-merge.yml | 2: the same two |
| `pull-requests: write` on promotion-guard's `promotion-source` job | promotion-guard.yml | 2: `…pull_requests_write_or_contents_write`, `test_promotion_guard_holds_no_write_permission` |
| open jobs grouped per event (`back-merge-${{ github.event_name }}`) | back-merge.yml | 1: `test_two_open_jobs_never_run_at_once_and_a_sweep_never_waits_behind_one` |
| the "one is open" branch skipped (`if false; then`) | back-merge.yml | 1: `test_with_one_back_merge_pull_request_open_the_job_names_it_and_opens_no_second` |
| the listing asks for `--state closed` | back-merge.yml | 1: `test_with_no_back_merge_pull_request_open_the_job_opens_one` |
| the open step's `if` removed (runs whatever the compare said) | back-merge.yml | 1: `test_when_main_and_dev_agree_the_job_does_nothing_visible` |

The first pass caught all 13 as well. In that pass, though, the last mutant was caught by the
harness's assertion of the exact `if` text, not by running the step. 6bc5621 makes the harness
treat a step with no `if` the way the runner does, so it always runs. The second pass, tabled
above, catches it by behaviour: with nothing to back-merge, the step called `gh`. The `--state
closed` mutant is caught by the arguments the listing passes. The fake `gh` does not filter pull
requests the way GitHub does.

### The rest of the checks

The load average was 2.79 / 3.49 / 3.46 before the mutation run and 5.04 / 4.00 / 3.65 before part 1
of the suite. During the suite it rose to 11.28, mostly from the suite's own workers. Each part ran
as one command with `set -o pipefail`, under a 115 s `alarm`:

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/5` | `1431 passed, 1 skipped in 45.83s` (an earlier run of the same part: `1431 passed, 1 skipped in 41.87s`) |
| `… --part 2/5` | `1430 passed, 1 xfailed in 36.66s` |
| `… --part 3/5` | `1416 passed, 1 warning in 37.08s` |
| `… --part 4/5` | `1419 passed, 1 xfailed, 1 warning in 34.32s` |
| `… --part 5/5` | `1427 passed, 1 warning in 44.77s` |
| `uv run --frozen ruff format --check .` | `695 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run --frozen scripts/actionlint.sh` | no findings, exit 0 |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 269 shell code blocks in 117 Markdown files (1 session reports changed since origin/dev)`, this report included |
| `uv run scripts/check_links.py` | `OK: 1560 relative links and anchors in 222 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK: 348 files, 38 epics, 290 tasks, 20 releases` |

The skip is the parser evaluation's "4 of 6 pr-subset files are not yet corrected by a person", as
on `dev`.

## Files changed

* `.github/workflows/back-merge.yml`:
  * the open job loses `if: github.event_name == 'push'`;
  * it gains a first step, `Run only from main or dev`, identical to the sweep's;
  * its comment and the header now say that every trigger opens or names the pull request, and why
    the schedule does;
  * permissions, concurrency group and step logic are unchanged.
* `tests/scripts/test_back_merge_workflow.py`:
  * two tests rewritten: which events run which job, and the concurrency group's stated purpose;
  * two shape tests added: the ref gate on both jobs, and the holders of `pull-requests: write` and
    `contents: write` across all workflows;
  * three step-logic tests added, with a harness that runs the compare and open steps.
* `docs/process/branching-and-environments.md`:
  * the back-merge paragraph, the permissions paragraph, the routes table and "What is mechanical"
    now say every run opens or names the pull request;
  * the hand-run `gh pr create` is kept only for a job that cannot open it.
* `.github/PULL_REQUEST_TEMPLATE/hotfix.md`: the dispatch now opens the pull request, so the
  checklist item no longer says to open it by hand (Deviation 1).
* `plan_specs/v1/e01-repo-foundation/t26-dispatch-opens-back-merge.yaml`: the hotfix template added
  to `constraints.packages`, with a dated comment. The phase is still `InProgress`.

## Deviations from the spec

1. **The hotfix template is outside `constraints.packages`, and it is changed anyway.** Its last
   checklist item said to "open the back-merge pull request by hand, since only the push opens it".
   After this task, that would send someone to do by hand what the dispatch they were just told to
   run has already done. The change is two lines, and the template is now in the spec's packages
   with a comment naming this report. If the PM would rather keep the template out of scope, revert
   9ff02bd's template hunk and the spec line, and file the wording as its own task.
2. **The brief says `contents: write` "stays on" the open job, but that job has never held it.**
   It holds `contents: read` and `pull-requests: write`, as in t08, t12 and t15. Its pull request's
   head is `main` itself, so it writes no contents. I kept `contents: read` rather than grant a
   write to match the wording. The new holders test pins that no job in `back-merge.yml` holds
   `contents: write`. The spec's forbidden item ("Granting `pull-requests: write` or
   `contents: write` to any job other than the one that opens …") is met either way.

## Decisions and assumptions

* **The schedule opens it too.** The spec allows this "if justified". Two reasons:
  * **A lost push with no promotion open shows nowhere else.** The sweep can only turn a promotion
    red, and when none is open it has nothing to turn red. The back-merge pull request is then the
    only sign that a hotfix's push was lost. The process doc's "back-merge the same day" depends on
    it appearing. A dispatch needs someone who already knows the push was lost; the schedule is the
    one route that needs nobody.
  * **When a promotion is open, its red check names a pull request that exists.** The schedule turns
    the promotion red in the same run that opens the back-merge pull request, so the red check
    points at something real.

  GitHub runs the schedule every two to five hours in practice (t15's close-out, 2026-10-15). That
  bounds how fast the schedule acts, not whether it is worth having. It is still the only unattended
  route, and the promotion checklist's dispatch covers the time before a merge.
* **What a scheduled run does when `main` and `dev` agree:** the compare step prints one line,
  ``OK: `dev` holds every non-merge commit on `main`.``, and sets `needed=false`. The open step is
  skipped, so `gh` is never called: no pull request, no label (the `gh label create --force` is
  inside the skipped step), no comment and no annotation. All that appears is one more green job
  inside a scheduled run that exists anyway for the sweep.
  `test_when_main_and_dev_agree_the_job_does_nothing_visible` holds this. The case it uses is a
  promotion's merge commit on `main`, which is today's normal state.
* **Running from `dev`.** A scheduled run uses `dev`'s copy of the workflow and of
  `check_promotion_source.py`, both merged code. As soon as this merges into `dev`, the schedule
  opens back-merge pull requests, before the promotion that puts this on `main`. Read locally from
  this checkout's `origin` refs (`origin/main` f2195e6, `origin/dev` 0d64c1b), the check reports
  ``OK: `dev` holds every non-merge commit on `main`.``. So the merge should open nothing by itself,
  unless `main` gains a hotfix first.
* **No `if` instead of a list of three events.** With the triggers pinned to exactly `push`,
  `schedule` and `workflow_dispatch` (and never `pull_request`, by an existing test), no `if` means
  those three events. That matches the sweep job, and the "skips one event" mutants are caught.
* **The ref gate on the open job.** It is new, but not new scope. The job checks out the ref it was
  started from, and its compare step runs that checkout's `scripts/check_promotion_source.py`
  before the step that has `GH_TOKEN`. Code run there could reach the later step through
  `$GITHUB_ENV` or `$GITHUB_PATH`. A push and the schedule only ever run `main` and `dev`. A
  dispatch can name any branch, and a dispatch is now a route into this job. The sweep already
  refuses that for the same reason (t15), and the open job now uses the same step, word for word.
* **One concurrency group for every trigger.** The group stays `back-merge` with
  `cancel-in-progress: false`. A push's, a dispatch's and a schedule's open jobs therefore never run
  at once, and two of them can never both find nothing open and both open one. A per-event group
  would allow exactly that, and the per-event mutant above is caught. The cost: GitHub keeps one pending job per group, so a newer
  open job can replace a pending older one, and that older run then shows the job as cancelled.
  Nothing is lost, because the newer job does the same from the live branches. The hotfix template
  asks about the sweep job's result on the push, not this one's.
* **The step-logic harness runs the workflow's own `run:` text.** It does not use a copy. It reads
  the compare and open steps from `back-merge.yml` and runs them with `bash -e`, the runner's default
  shell. It skips only the network fetch, by setting `origin/main` and `origin/dev` with
  `update-ref`, and it puts a `python3` shim and a recording `gh` on `PATH`. A change to the step's
  shell is therefore what the tests exercise. The `sed` in the body works under both BSD (here) and
  GNU (the runner) sed.
* **A closed, unmerged back-merge pull request is not respected.** The listing asks only for open
  pull requests, so if someone closes one without merging, the next run (now including a scheduled
  one) opens a new one. That is intended: `main` still holds commits `dev` lacks, and every
  promotion stays blocked until they arrive.

## Operator follow-ups

### 1. The sandbox proof (ac1, the `dispatch-opens` node)

Expected runtime is about 10 minutes. The procedure creates a public sandbox repository under your
account, `charlesclark2/back-merge-dispatch-sandbox`, and pushes to it. It never reads or touches
`charlesclark2/debate-intelligence`. No ruleset is copied, because nothing is merged.

It relies on what t15's two sandboxes showed (2026-10-09 and 2026-10-14): in a fresh repository,
GitHub starts no push- or pull-request-triggered run, while `workflow_dispatch` works. A commit
pushed to the sandbox's `main` is therefore a lost push by itself.

Everything runs from the task worktree, plus a separate scratch worktree for the sandbox's
branches, so the task worktree's checkout never changes. Paste back the output at each bracketed
label, [A] to [H].

*Set up the sandbox.* This makes a sandbox-only commit that deletes the four workflows not under
test, and leaves `back-merge.yml` and `promotion-guard.yml` byte-identical to this branch. It pushes
that commit as both `main` and `dev`, makes `dev` the default branch, and turns on the setting that
lets workflows create pull requests (the open job needs it).

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t26-dispatch-opens-back-merge
SANDBOX=charlesclark2/back-merge-dispatch-sandbox
SB="https://github.com/${SANDBOX}.git"
PATTERN='OK: |FAILED: |Back-merge pull request #|/pull/[0-9]+|Swept|No pull requests|##\[(warning|error)\]'
git worktree add -b sandbox-base /tmp/t26-dispatch-sandbox task/v1-e01-t26-dispatch-opens-back-merge
cd /tmp/t26-dispatch-sandbox
git rm -q .github/workflows/ci.yml .github/workflows/dev-prerelease.yml .github/workflows/validate-dev.yml .github/workflows/refresh-generated-files.yml
git commit -q -m "Sandbox: only the promotion guards and back-merge run"
BASE=$(git rev-parse HEAD)
gh repo create "$SANDBOX" --public --description "Throwaway for the v1-e01-t26 sandbox proof; delete afterwards"
git push "$SB" "${BASE}:refs/heads/main" "${BASE}:refs/heads/dev"
gh repo edit "$SANDBOX" --default-branch dev
gh api -X PUT "repos/${SANDBOX}/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
gh api "repos/${SANDBOX}/actions/permissions/workflow"
```

The last command prints `"can_approve_pull_request_reviews":true`.

*The quiet case: dispatch while `main` and `dev` agree.*

```bash
gh workflow run back-merge.yml --repo "$SANDBOX" --ref dev
sleep 20; QUIET=$(gh run list --repo "$SANDBOX" --workflow back-merge.yml --event workflow_dispatch --limit 1 --json databaseId --jq '.[0].databaseId'); echo "$QUIET"
gh run watch --repo "$SANDBOX" "$QUIET" --exit-status
gh run view --repo "$SANDBOX" "$QUIET" --log | grep -E "$PATTERN"
gh pr list --repo "$SANDBOX" --state all --json number
gh label list --repo "$SANDBOX" --search back-merge --json name
```

* **[A]**: the run succeeds. The log shows one line from each job:
  ``OK: `dev` holds every non-merge commit on `main`.`` and `No pull requests are open against
  main.`. There is no `##[warning]` or `##[error]` line.
* **[B]**: `[]` and `[]`. No pull request was opened, and no `back-merge` label was created.

*The lost push: a commit on `main` that `dev` lacks, pushed with nothing to deliver it to.*

```bash
git switch -q -c hotfix/sandbox-lost-push "$BASE"
echo fix > SANDBOX_HOTFIX.txt && git add SANDBOX_HOTFIX.txt && git commit -q -m "Sandbox hotfix whose push starts nothing"
git push "$SB" HEAD:refs/heads/main
MAIN=$(git rev-parse HEAD); echo "$MAIN"
sleep 60
gh run list --repo "$SANDBOX" --json workflowName,event,headSha,conclusion
gh api "repos/${SANDBOX}/compare/dev...main" --jq '[.commits[] | select(.parents | length == 1) | .commit.message]'
gh pr list --repo "$SANDBOX" --state all --json number
```

* **[C]**: the run list holds only the quiet dispatch from [A] (`"event":"workflow_dispatch"`).
  Nothing ran for `$MAIN`.
* **[D]**: `["Sandbox hotfix whose push starts nothing"]` and `[]`. `main` holds a commit `dev`
  lacks, and no back-merge pull request exists.

If [C] lists a `push` run, GitHub delivered the push in this sandbox, so this was not a lost push.
Paste it and stop; t15's Deviation 5 (disabling `back-merge.yml` for the push) is the fallback,
and the PM decides.

*Dispatch: it opens the back-merge pull request.*

```bash
gh workflow run back-merge.yml --repo "$SANDBOX" --ref dev
sleep 20; FIRST=$(gh run list --repo "$SANDBOX" --workflow back-merge.yml --event workflow_dispatch --limit 1 --json databaseId --jq '.[0].databaseId'); echo "$QUIET $FIRST"
gh run watch --repo "$SANDBOX" "$FIRST" --exit-status
gh run view --repo "$SANDBOX" "$FIRST" --log | grep -E "$PATTERN"
gh pr list --repo "$SANDBOX" --state all --json number,state,baseRefName,headRefName,labels --jq '[.[] | {number, state, baseRefName, headRefName, labels: [.labels[].name]}]'
```

* **[E]**: two different run ids, and the run succeeds. The log shows
  ``FAILED: `main` has 1 non-merge commit(s) that `dev` lacks`` naming the sandbox hotfix, the new
  pull request's URL ending `/pull/1`, and `No pull requests are open against main.`. There is no
  `##[warning]` or `##[error]` line.
* **[F]**: exactly one pull request:
  `[{"number":1,"state":"OPEN","baseRefName":"dev","headRefName":"main","labels":["back-merge"]}]`.

*Dispatch again: it names the open one and opens no second.*

```bash
gh workflow run back-merge.yml --repo "$SANDBOX" --ref dev
sleep 20; SECOND=$(gh run list --repo "$SANDBOX" --workflow back-merge.yml --event workflow_dispatch --limit 1 --json databaseId --jq '.[0].databaseId'); echo "$FIRST $SECOND"
gh run watch --repo "$SANDBOX" "$SECOND" --exit-status
gh run view --repo "$SANDBOX" "$SECOND" --log | grep -E "$PATTERN"
gh pr list --repo "$SANDBOX" --state all --json number,state,baseRefName,headRefName,labels --jq '[.[] | {number, state, baseRefName, headRefName, labels: [.labels[].name]}]'
```

* **[G]**: two different run ids, and the run succeeds. The log shows the same `FAILED:` line and
  `Back-merge pull request #1 is open; its head is main, so it already has these commits.`. Any
  URL it prints ends `/pull/1`, never `/pull/2`. There is no `##[warning]` or `##[error]` line.
* **[H]**: the same single pull request as [F], still `#1`.

If [E] shows `##[error]` with `GitHub Actions is not permitted to create or approve pull requests`,
the setting from the setup block did not take. Paste the setup block's last line and the log.

*Clean up* once the results are pasted back:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t26-dispatch-opens-back-merge
git worktree remove --force /tmp/t26-dispatch-sandbox
git branch -D sandbox-base hotfix/sandbox-lost-push
gh auth refresh -h github.com -s delete_repo
gh repo delete charlesclark2/back-merge-dispatch-sandbox --yes
gh auth refresh -h github.com -r delete_repo
```

When [A] to [H] hold, the sandbox half of ac1 and the `dispatch-opens` node pass, and the Goal can
be set to `Succeeded`, as in t15's close-out.

### 2. Sync before the pull request

`origin/dev` has moved since this branch was cut (local `origin/dev` is 0d64c1b, 2026-10-15 13:03,
and this branch starts from a65543d). Run `scripts/task sync` before `scripts/task pr`.

### 3. After this merges into `dev`

Each scheduled *Back-merge main into dev* run on the real repository now has two jobs. While
`main` and `dev` agree, `open-back-merge-pull-request` should be green and log only
``OK: `dev` holds every non-merge commit on `main`.``, and no pull request appears. If a hotfix is
merged into `main` before this is promoted, the next scheduled run, or a dispatch from `dev`, opens
its back-merge pull request even if the push was lost.

## Follow-up work

* **A back-merge pull request merged between the compare and the open fails the job once.** If
  someone merges the open back-merge pull request after the compare step has run but before the
  listing, the listing finds nothing open, and `gh pr create` is refused because `main` and `dev`
  now have no commits between them. The job goes red for that one run, and the next run is green.
  This already applied to the push. The schedule makes it marginally more likely, but the window is
  seconds wide. Not worth a task unless it is seen.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

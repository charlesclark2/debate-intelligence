# Session report: v1-e01-t36-prerelease-superseded-commit

| | |
|---|---|
| Task | `v1-e01-t36-prerelease-superseded-commit` — A dev pre-release for a commit dev has moved past with a workflow change is reported superseded, not failed |
| Spec | [`plan_specs/v1/e01-repo-foundation/t36-prerelease-superseded-commit.yaml`](../../plan_specs/v1/e01-repo-foundation/t36-prerelease-superseded-commit.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t36-prerelease-superseded-commit` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A dev pre-release claim for a commit dev's head has passed with a change to `.github/workflows/`
now ends superseded. Before its first push, the claim fetches dev's head; if that head is past the
commit and the workflow files differ, the claim prints a notice naming dev's head, writes
`superseded=true`, pushes no tag and exits 0, and `dev-prerelease.yml` skips every later step.
Nothing is built, published, dispatched or pruned, and the run reads as succeeded with a notice and
a short summary. GitHub's refusal wording is only a second guard: a push still refused with it
re-checks against a fresh head, and is superseded only if that holds. Hotfix claims are unchanged.
The work started with a count (below) that withdrew the PM's hypothesis; the PM then ruled
(2026-10-24) to build the spec as written and to document what is known as observed, not as
GitHub's rule. Worth looking at first: the check is conservative (it may skip a commit GitHub would
have tagged, never the reverse), and `d47c851` (`dev.16`) is still unconfirmed either way. Its query
is under Operator follow-ups.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `superseded-claim` (Superseded pre-release claim) | Done | Counted first (two hand-offs, PM ruling), then red against a skeleton (`51b1e8c`), green (`51b2d78`), docs and one coverage test (`1024a49`). 17 of 17 mutants caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: with a stubbed git and tag store, a claim behind dev's head with a later workflow change ends superseded naming dev's head, pushes no tag, exits 0; at dev's head, or behind with no workflow change, claims as today; any other refusal fails after the retries; shown failing first | PASS | `uv run pytest tests/scripts/test_release_version.py` → `60 passed`. Superseded: `test_a_commit_behind_a_workflow_change_on_dev_is_superseded_and_no_tag_is_attempted` (stub store and dev branch, `store.pushed == []`), `test_claim_ends_superseded_with_a_notice_outputs_and_exit_zero` (exit 0, notice naming dev's head, outputs). Claims as today: `test_a_commit_that_is_not_superseded_claims_as_today[at-devs-head / behind-with-no-workflow-change-after-it / not-on-dev]`. Other refusals: `test_any_other_refusal_fails_after_the_retries_even_when_dev_has_moved_past`, `test_the_refusal_text_alone_does_not_make_a_commit_superseded`. Red first: `51b1e8c`, 11 failed, 61 passed (below). |
| ac2: the workflow's run for a superseded commit reads as skipped, not failed, and the next commit's pre-release is unaffected, by test over the workflow's steps | PASS | `.venv/bin/python -m pytest tests/scripts/test_dev_prerelease_workflow.py` → `13 passed` (part of the 514 below). `test_a_superseded_commit_runs_nothing_after_the_claim_but_its_summary` evaluates every step's `if:`: only checkout, claim and the superseded summary run. `test_the_next_commits_pre_release_runs_every_step_as_before[new / reused]` and `test_a_commit_already_published_still_skips_the_build_and_re_dispatches` show the other paths unchanged. In release_version: `test_the_next_commits_claim_is_unaffected_and_takes_the_number_the_superseded_one_did_not`. "Reads as skipped" means the run succeeds with a notice and every later step skipped; a job-level `skipped` would need a second job (Decisions). |
| Node `superseded-claim`: Release version tests pass (`uv run pytest tests/scripts/test_release_version.py`) | PASS | `60 passed in 7.10s` |

## Files changed

* `scripts/release_version.py`: the superseded check (`DevBranch`, `GitDevBranch`, `superseded_by`,
  `CommitSuperseded`), the second guard (`PushResult.WORKFLOW_REFUSED`, `is_workflow_refusal`,
  pinned to run 40149948706's wording), the claim loop and `main`. The docstring section "A commit
  dev has moved past" records what is known, labelled as observed or reported. `_git` is now a module
  function that `GitTagStore` and `GitDevBranch` share.
* `.github/workflows/dev-prerelease.yml`: the header paragraph on the same, a "Summary of a superseded
  commit" step, and `if: steps.claim.outputs.superseded != 'true'` on the three steps that were not
  already gated behind the published check. The claim's command line is unchanged.
* `tests/scripts/test_release_version.py`: 17 new tests (one parametrized over three cases and one
  over five refusals); stub dev branch and scripted store, plus real git against a bare remote for
  `GitDevBranch`, `push_tag`'s classification (pre-receive hook), `main` and the hotfix path.
* `tests/scripts/test_dev_prerelease_workflow.py` (new): which steps run, by evaluating each step's
  `if:` over scenario outputs, and that the claim's command line is unchanged.
* `docs/process/branching-and-environments.md`: one paragraph under "How N is numbered".
* `plan_specs/.../t36-prerelease-superseded-commit.yaml`: Goal phase Succeeded.

## Deviations from the spec

None. The PM's ruling of 2026-10-24 kept the spec as written; the hypothesis it withdrew was in the
PM's brief, not in the spec.

## Decisions and assumptions

### The PM's ruling (2026-10-24) and how it was built

* **Option 1, the spec as written.** Before the first push, against a dev head fetched at that
  moment (`git fetch <remote> refs/heads/dev`, then `FETCH_HEAD`, never the checkout's
  `origin/dev`): a commit that is not dev's head, is an ancestor of it, and whose
  `.github/workflows/` differ from dev's head's ends superseded.
* **"Differ" is a tree diff** (`git diff --name-only sha head -- .github/workflows`), not "some
  later commit touched it". A change that was later reverted leaves identical workflow files, and
  both readings of GitHub's rule tag those.
* **The second guard.** `push_tag` returns `WORKFLOW_REFUSED` only for GitHub's wording (the regex
  matches the GitHub App sentence with the path in backticks; the OAuth App and ruleset wordings do
  not match). On it the claim fetches dev's head again and is superseded only if the condition
  holds. Otherwise the refusal counts toward the existing three retries and fails with today's
  message.
* **Checked once, before the first push**, not before every attempt. Later attempts follow a
  collision (`TAKEN`), and any refusal they meet goes through the second guard. Checking before
  every attempt would turn an unrelated push failure, while dev moved, into a superseded outcome,
  which "any other refusal fails as today" rules out (mutant 9 below).
* **A commit that already has its tag gets it back first**, so a re-run for a commit whose release
  never appeared still publishes under its claimed tag, as the workflow header promises.
* **The superseded ending is an exception** (`CommitSuperseded`), so `claim_dev_tag` still returns
  `Claim` and no existing test or caller changed.
* **Output.** For a superseded claim, stdout is the `::notice` line alone (no JSON), and
  `$GITHUB_OUTPUT` gets `superseded=true`, `sha=` and `superseded_by=`; no `tag=`, so the existing
  `Summary` step skips itself.
* **"Reads as skipped".** GitHub can skip a job only on a condition known before it starts, and this
  one is learnt in the claim step. Splitting the claim into its own job would move the token and the
  checkout. So the run succeeds with a notice annotation, every later step skipped, and a job
  summary saying why; the PM may want to confirm that this is the reading they meant.
* **The workflow and the script take effect at different times.** The YAML runs from the default
  branch and the script from the commit being tagged, so the claim's command line takes no new flag
  (pinned by `test_the_claim_command_line_is_unchanged`). A commit merged before this change and
  claimed after it runs the old script under the new YAML, which behaves exactly as today:
  `superseded` is empty and every step runs as before.
* **Hotfix claims are not checked** (`dev_branch=None` for `--source hotfix`), pinned by
  `test_a_hotfix_head_is_claimed_as_today_even_when_dev_has_moved_past_it_with_a_workflow_change`
  (a hotfix commit back-merged into dev, then dev changes a workflow). `next` is also unchanged: it
  still prints the number a claim would take, without the superseded check.

### Red run, mutants and coverage

* **Red** (`51b1e8c`): the skeleton had every new name with real signatures and refused nothing.
  `.venv/bin/python -m pytest -q -p no:randomly -n 0 tests/scripts/test_release_version.py
  tests/scripts/test_dev_prerelease_workflow.py` → 11 failed, 61 passed. By `E` line: "DID NOT
  RAISE CommitSuperseded" (1); `IndexError: pop from empty list` (3, the skeleton kept pushing
  after refusals it did not count, until the scripted store ran out); the pre-check never fetched,
  `[] == [OLDER]` (1); `is_workflow_refusal` false (1); `push_tag` returned `FAILED` (1); JSON where
  the notice belongs (1); the workflow ran every step for a superseded claim (2); no superseded
  summary step (1). The 61 that passed were expected to: the existing tests, the must-not-supersede
  cases (three claims as today, reuse, five other refusals, a hook-declined push staying `FAILED`,
  the hotfix path), `GitDevBranch`'s git plumbing and `CommitSuperseded`'s outputs (both written in
  the skeleton), and the workflow's unchanged paths and evaluator cases.
* **Mutants**: 17 of 17 caught. One at a time, byte-restored, `scripts/__pycache__` deleted, each
  classified from pytest's summary line, tree clean before and after. Selection: both test files at
  `-n 0`, 7 to 23 s each. No Hypothesis is involved, so agreement 8's database rule does not apply.

  | # | Mutant | Caught by |
  |---|---|---|
  | 0 | head check inverted | 4 tests, incl. the superseded and command-line tests |
  | 1 | workflow-change check dropped | `claims_as_today[behind-with-no-workflow-change-after-it]` |
  | 2 | a non-workflow refusal treated as the workflow refusal (the claim loop) | `any_other_refusal_fails_after_the_retries_even_when_dev_has_moved_past` |
  | 3 | stale dev head: the checkout's `origin/dev`, not fetched | `devs_head_is_fetched_from_the_remote_not_read_from_the_checkouts_stale_ref` |
  | 4 | second guard's re-check dropped | `a_refusal_after_dev_moved_during_the_claim_is_superseded_by_the_fresh_head` |
  | 5 | the refusal text alone supersedes | `the_refusal_text_alone_does_not_make_a_commit_superseded` |
  | 6 | ancestry check dropped | `claims_as_today[not-on-dev]` |
  | 7 | hotfix claims checked against dev | the hotfix test |
  | 8 | pre-check dropped, second guard only | 5 tests, incl. "no tag is attempted" |
  | 9 | pre-check on every attempt | `any_other_refusal_fails_after_the_retries_even_when_dev_has_moved_past` |
  | 10 | refusal wording widened to any "refusing to allow" | `other_refusals_are_not_read_as_the_workflow_refusal` |
  | 11 | `push_tag` never classifies the refusal | the pre-receive-hook classification test |
  | 12 | superseded claim exits 1 | `claim_ends_superseded_with_a_notice_outputs_and_exit_zero` |
  | 13 | superseded check before the reuse check | 3 tests, incl. the reuse test |
  | 14 | workflow: the published check not gated | both superseded workflow tests |
  | 15 | workflow: the dispatch not gated | both superseded workflow tests |
  | 16 | workflow: the prune not gated | both superseded workflow tests |

  Mutant 3 is the stale-dev-head mutant the PM asked for.
* **Coverage**: `pytest tests/scripts/test_release_version.py --cov=release_version
  --cov-report=term-missing` showed one rewritten line untested, `GitDevBranch.contains`' error for
  a commit git cannot read. `test_a_commit_git_cannot_read_is_an_error_not_a_commit_off_dev` covers
  it and fails with that check removed (1 failed, then restored and verified). The other uncovered
  lines predate this task.


### Counted first, from local git (2026-10-24, before any code)

All from the shared repository's local refs; nothing fetched.

* **The incident, confirmed locally.** `f1f31d9` (#470) is an ancestor of `09fcd05`. `git diff
  v1.1.0-dev.136 f1f31d9 -- .github/workflows` is empty: the workflows are byte-identical to
  `dev.136`'s (`cadafe7`). The next first-parent commit, `8378f5c` (#472, merged 6 minutes after
  `f1f31d9`), modified `.github/workflows/validate-dev.yml` (61 insertions, 2 deletions), and
  `v1.1.0-dev.137` points at `09fcd05`. `f1f31d9` has no tag.
* **Workflow-changing dev commits**, counted by comparing each first-parent commit's
  `.github/workflows` tree with its first parent's. Since the channel was added (`c5cb1e8`,
  2026-09-28) 16 commits changed it. The commit just before one went untagged three times, each
  with a short gap: `f1f31d9` (6 min before `8378f5c`), `ec6cffa` (6 min before `5f11f33`,
  validate-dev.yml) and `7a9c4ff` (2 min before `beb0f20`, ci.yml). CI never cancels a dev push
  (`ci.yml` cancels only pull-request runs), so a short gap alone does not explain a missing tag.
  An earlier count with `git diff-tree -m --first-parent` said 21 and included back-merges
  (`057b3f7`, `4200fe2`) whose trees did not change; it is withdrawn.
* **One dev counterexample candidate, not confirmed either way.** `d47c851` (`v0.1.0-dev.16`) was
  tagged although the back-merge `c4c515a`, which changed `back-merge.yml` and `promotion-guard.yml`,
  landed one minute after it. If its claim ran after the back-merge, it is a dev commit GitHub tagged
  that the new check would skip, as the conservative check allows. The run-history query is under
  Operator follow-ups; the session did not run it (live call).
* **What the claim step can see.** The checkout uses `fetch-depth: 0`, so every branch and tag as
  of the checkout is there, and the claim step already holds the token as a git header, so it can
  also ask the remote for dev's current head (`ls-remote`, `fetch`) before it pushes.
* **Which workflow file and which script run.** `workflow_run` runs `dev-prerelease.yml` from the
  default branch, but the claim runs `scripts/release_version.py` from the checkout of `HEAD_SHA`,
  the commit being tagged. A change to the YAML takes effect from the first run after it merges; a
  change to the script only for commits that contain it. A commit merged before this task, run
  after it, gets the new YAML with the old script, so the YAML must not pass the old script a new
  flag.

### What the run history says (operator commands, 2026-10-24)

* **Default branch:** `dev` (`gh api repos/charlesclark2/debate-intelligence --jq .default_branch`).
* **Runs of `dev-prerelease.yml`:** 296 success, 76 skipped, 2 failure.
* **Both failures are this refusal.** Run 40149948706 (2026-10-25T01:15:51Z) and run 38647659339
  (2026-10-14T22:26:29Z). The `headSha` that `gh` reports for a `workflow_run` run is the default
  branch's head when the run started (`09fcd05` and `beb0f20`), not the commit it tags. The 10-14
  run started 83 seconds after `beb0f20` (ci.yml) landed, which fits a claim for `7a9c4ff`, still
  untagged. So the refusal has happened twice in 374 runs, and both times the spec's condition
  held.
* **The refusal's exact wording**, from run 40149948706's claim step:

  ```text
  release_version: pushing v1.1.0-dev.137 failed 3 times for a reason other than the tag existing; last error: To https://github.com/charlesclark2/debate-intelligence
   ! [remote rejected] f1f31d9eb1c5f0305ddc8697d4f4600631ad91ed -> v1.1.0-dev.137 (refusing to allow a GitHub App to create or update workflow `.github/workflows/validate-dev.yml` without `workflows` permission)
  ```
* **The claim-time query was wrong.** `gh run list --commit X` matches the default branch's head
  when a run started, for the reason above, so its output does not say when `d47c851` was claimed.
  The session's mistake; a corrected query is under Operator follow-ups.
* **Open branches at the refusal.** At 01:16:01Z the only open pull request was #473, whose head's
  workflows are the new tree (`9d13ab3`). No branch head that the session can see still had
  `f1f31d9`'s tree (`d65eaeb`), so this incident fits both readings of the rule.

### The hotfix tags contradict the default-branch reading (PM: hypothesis withdrawn)

* `v1.0.1-dev.1` (`82afb9c`) and `v1.0.1-dev.2` (`298bc37`) are the hotfix pre-releases of
  `hotfix/schedule-2026-10-22` (merged into main as `a8aebae`, PR #431, 2026-10-23T05:18Z). Both
  commits have workflows tree `23bf80b`. Every first-parent dev commit from 2026-10-22T22:59 to
  2026-10-23T01:25 (-05:00) has tree `d65eaeb`. So both tags were pushed at commits whose workflows
  differed from the default branch's head, and both went through.
* A hotfix head is the head of its own branch, so under "matches the latest commit of any branch"
  its tag is never refused. That fits. Under "compared with the default branch's head", both would
  have been refused.
* Not confirmed by the session: that both tags were pushed by the workflow's claim step, with
  `GITHUB_TOKEN`, rather than by hand. The PM accepted the evidence (2026-10-24); the query is under
  Operator follow-ups for the record.
* Tags do not count as a match: `f1f31d9`'s workflows were identical to the tag
  `v1.1.0-dev.136`'s, and its push was still refused.

### GitHub's documentation, searched by the session

A documentation search, not a call against this repository, so the session ran it itself.

* GitHub's "Choosing permissions for a GitHub App" page says only: "If your app specifically needs
  to access or edit Actions files in the `.github/workflows` directory", request the "Workflows"
  repository permission
  (https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).
  Its permission reference lists `POST /repos/{owner}/{repo}/git/refs` as needing "additional
  permissions" (https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps).
  Neither says when a ref push counts as creating or updating a workflow.
* Community discussion #151442 (February 2025, no GitHub staff answer;
  https://github.com/orgs/community/discussions/151442) reports that a `GITHUB_TOKEN` tag push is
  refused "if the tag points to a commit where the contents of `.github/workflows/` are not
  identical to the contents of `.github/workflows/` on the latest commit of any branch". Two
  replies from January 2026 say the behaviour changed then. Discussion #26164 (2020;
  https://github.com/orgs/community/discussions/26164) reports the same refusal for tags on older
  commits.
* So the documented rule is none, and the reported one is "any branch", which is broader than the
  PM's "the default branch". The hotfix tags above fit the reported one. For a dev commit that is an ancestor of dev's
  head, both readings refuse only when its workflows differ from dev's head: dev's head is itself a branch head. They
  differ only when the workflows match another branch's head (main, or an open task branch). Then
  "any branch" lets the push through and a check against dev's head alone would skip a commit
  that could have been tagged. It would never miss a refusal. This incident cannot tell the two readings apart (no
  branch head had `d65eaeb` at 01:16Z); the hotfix tags can.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

Nothing is required before the pull request. The counting hand-offs (2026-10-24) ran and their
results are under Decisions.

**Checks run before this report**, all from the worktree, all passing:

* The affected set, once. `uv run scripts/affected_tests.py` listed 47 files. One run of all 47 with
  CI's markers (`-n auto -m "not slow and not live"`) was stopped by its 115-second alarm with the
  machine at load average 38 (other sessions), with no orphaned workers afterwards. The same 47 then
  ran once, in three time-boxed parts with `.venv/bin/python -m pytest -q -n 4 -m "not slow and not
  live"`: the tests that read the changed script, workflow or docs, `tests/docs` and
  `test_single_interpreter_source.py` (514 passed, 49 s); the always-run list, `tests/architecture
  tests/specs` and the two CLI wiring tests (316 passed, 15 s); the other 27 files (1348 passed,
  100 s). 2,178 passed, 0 failed.
* `uv run ruff format --check .` → 1256 files already formatted. `uv run ruff check .` → All checks
  passed. `uv run lint-imports` → 16 kept, 0 broken. `uv run --frozen python
  scripts/check_thin_handlers.py` → 50 handlers within 25 statements.
* pyright: no package changed, so CI's `pyright` (which includes only `packages/`) sees nothing new.
  `uv run pyright scripts/release_version.py tests/scripts/test_dev_prerelease_workflow.py
  tests/scripts/test_release_version.py` → one error, the `sys.path` import of `release_version` in
  the test file (`reportMissingImports`), which was already there at the start commit.
* `uv run scripts/check_command_blocks.py --base origin/dev` → OK; `scripts/docs_index.py
  --check-descriptions` → all 47 documents described; `scripts/check_links.py` → OK.
* ShellCheck over the new summary step's `run:` block → clean. actionlint was not run here:
  `scripts/actionlint.sh` downloads it from GitHub, so CI's `workflow-lint` job runs it on the pull
  request.
* `uv run scripts/validate_specs.py` → `OK: 439 files, 40 epics, 377 tasks, 22 releases`.

**Two optional read-only queries** remain for the record, a few seconds each. Neither blocks the
pull request.

The first confirms that the hotfix tags came from the workflow's claim step. For each
`workflow_dispatch` run it prints the run id, branch, head, start time, conclusion, and the tag,
commit and `reused` value from the claim's output. Success looks like two runs on
`hotfix/schedule-2026-10-22` with `reused: false`, tagging `82afb9c` and `298bc37`.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t36-prerelease-superseded-commit
for id in $(gh run list --repo charlesclark2/debate-intelligence --workflow dev-prerelease.yml --event workflow_dispatch --limit 50 --json databaseId --jq '.[].databaseId'); do echo "$id $(gh run view "$id" --repo charlesclark2/debate-intelligence --json headBranch,headSha,createdAt,conclusion --jq '.headBranch + " " + .headSha[0:7] + " " + .createdAt + " " + .conclusion') $(gh run view "$id" --repo charlesclark2/debate-intelligence --log 2>/dev/null | grep -oE '"(tag|sha|reused)": "[^"]+"' | head -3 | tr '\n' ' ')"; done
```

The second says when `d47c851` was claimed: the runs that started between its merge and 25
minutes later, with the tag, commit and `reused` value each one's claim printed. Success looks
like a line naming `v0.1.0-dev.16`; its start time, against `c4c515a`'s landing at
2026-09-30T03:21:56Z, is the answer.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t36-prerelease-superseded-commit
for id in $(gh run list --repo charlesclark2/debate-intelligence --workflow dev-prerelease.yml --created '2026-09-30T03:19:00Z..2026-09-30T03:45:00Z' --limit 50 --json databaseId --jq '.[].databaseId'); do echo "$id $(gh run view "$id" --repo charlesclark2/debate-intelligence --json createdAt,conclusion --jq '.createdAt + " " + .conclusion') $(gh run view "$id" --repo charlesclark2/debate-intelligence --log 2>/dev/null | grep -oE '"(tag|sha|reused)": "[^"]+"' | head -3 | tr '\n' ' ')"; done
```

## Follow-up work

* **`d47c851` (`v0.1.0-dev.16`)**: the second query above says whether a dev commit GitHub tagged
  would now be skipped. It does not change the code (the PM ruled the conservative check), but it is
  the one number that measures what the conservativeness costs.
* **A tag through the REST API instead of a push**: discussion #26164 reports that creating tags via
  the API worked where the push was refused, but GitHub's permission reference lists `POST
  /repos/{owner}/{repo}/git/refs` as needing additional permissions. Not pursued; it would change
  the claim's atomic step (v1-e01-t09) and would need its own count. E01, if the PM wants it.
* **`next` does not report superseded.** It still prints the number a claim would take. Adding the
  check there would make `next` fetch, which it does not do today. Left as it is.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

1. **The count did its job.** It withdrew the PM's hypothesis with evidence: the hotfix tags
   `v1.0.1-dev.1` and `.2` went through at commits that differed from the default branch's head.
   It also found the second refusal (10-14, `7a9c4ff`) and showed that the spec's condition held
   both times. It withdrew its own 21-commit miscount and its own wrong claim-time query. Exactly
   the right habits.
2. **Built as ruled (option 1).**
   * The pre-check uses a freshly fetched dev head (`FETCH_HEAD`, never the checkout's
     `origin/dev`), checks ancestry, and compares the workflow trees, so a reverted change still
     tags.
   * GitHub's wording, pinned from run 40149948706, is a second guard only, re-checked against a
     fresh head.
   * The check runs once, before the first push, which keeps "any other refusal fails as today"
     true.
   * Hotfix claims are unchanged, and a test pins it.
3. **The rest is accepted as made:**
   * **"Reads as skipped" means a run that succeeds with a notice annotation, every later step
     skipped, and a job summary saying why.** A job-level `skipped` would need a second job that
     moves the token and the checkout. That's not worth it, and this is the reading the PM meant.
   * The workflow and the script deliberately take effect at different times, with the claim's
     command line unchanged and pinned. A commit merged before this change behaves exactly as today.
   * **What's known is documented as observed or reported,** with the conservative direction stated
     (it may skip a commit GitHub would have tagged, never the reverse): two refusals in 374 runs,
     GitHub's documentation silent, discussion #151442.
4. **Red, then green.** 11 failed against the skeleton, and 17 of 17 mutants were caught, including
   the stale-dev-head mutant the PM asked for. The coverage gap that turned up got its own test. The
   affected set was run in three parts (2,178 passed).
5. **The two read-only queries are optional, for the record only.** The PM won't block on them. If
   the operator runs the `d47c851` one, its answer goes in a PM record.
6. **Follow-up work:** the REST-API tag is not pursued, because it would change v1-e01-t09's atomic
   claim and its permissions. `next` stays as it is.

No re-review is needed. The Goal is `Succeeded`.

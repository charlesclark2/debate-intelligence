# Session report: v1-e01-t36-prerelease-superseded-commit

| | |
|---|---|
| Task | `v1-e01-t36-prerelease-superseded-commit` — A dev pre-release for a commit dev has moved past with a workflow change is reported superseded, not failed |
| Spec | [`plan_specs/v1/e01-repo-foundation/t36-prerelease-superseded-commit.yaml`](../../plan_specs/v1/e01-repo-foundation/t36-prerelease-superseded-commit.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t36-prerelease-superseded-commit` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped after counting, before any code, because the evidence says something other than the PM's
hypothesis, and the brief says to report that and stop. The default branch is `dev`, and both
refusals in the run history (2026-10-14 and 2026-10-25) hit a dev commit that was behind dev's head
when a later commit had changed `.github/workflows/`. But the two hotfix pre-releases,
`v1.0.1-dev.1` and `v1.0.1-dev.2` (2026-10-23), were tagged with the same token at commits whose
workflows differed from dev's head throughout the hour around them. If GitHub compared a pushed tag
with the default branch's head, both would have been refused. Every observation fits the one
public description instead: a push is refused only when the tagged commit's workflows match no
branch's head. The spec's condition is still safe under that reading: it never misses a refusal,
but it would skip some pre-releases GitHub would have allowed. Which condition to build is the PM's
call (question below). No code has changed.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

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
* **One dev counterexample candidate.** `d47c851` (`v0.1.0-dev.16`) was tagged although the
  back-merge `c4c515a`, which changed `back-merge.yml` and `promotion-guard.yml`, landed one minute
  after it. Whether its claim ran before or after that back-merge is still unknown (below).
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

### The hotfix tags contradict the default-branch reading

* `v1.0.1-dev.1` (`82afb9c`) and `v1.0.1-dev.2` (`298bc37`) are the hotfix pre-releases of
  `hotfix/schedule-2026-10-22` (merged into main as `a8aebae`, PR #431, 2026-10-23T05:18Z). Both
  commits have workflows tree `23bf80b`. Every first-parent dev commit from 2026-10-22T22:59 to
  2026-10-23T01:25 (-05:00) has tree `d65eaeb`. So both tags were pushed at commits whose workflows
  differed from the default branch's head, and both went through.
* A hotfix head is the head of its own branch, so under "matches the latest commit of any branch"
  its tag is never refused. That fits. Under "compared with the default branch's head", both would
  have been refused.
* Not yet confirmed: that both tags were pushed by the workflow's claim step, with
  `GITHUB_TOKEN`, rather than by hand. The query is under Operator follow-ups.
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
  PM's "the default branch". The hotfix tags above fit the reported one. For a dev commit that is an ancestor of dev's head, both readings
  refuse only when its workflows differ from dev's head: dev's head is itself a branch head. They
  differ only when the workflows match another branch's head (main, or an open task branch). Then
  "any branch" lets the push through and a check against dev's head alone would skip a commit
  that could have been tagged. It would never miss a refusal. This incident cannot tell the two readings apart (no branch head had `d65eaeb` at
  01:16Z); the hotfix tags can.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

The first counting hand-off (2026-10-24) ran; its results are under Decisions. Two queries remain,
both read-only and a few seconds each.

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

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

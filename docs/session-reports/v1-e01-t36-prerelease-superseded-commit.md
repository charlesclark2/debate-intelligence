# Session report: v1-e01-t36-prerelease-superseded-commit

| | |
|---|---|
| Task | `v1-e01-t36-prerelease-superseded-commit` — A dev pre-release for a commit dev has moved past with a workflow change is reported superseded, not failed |
| Spec | [`plan_specs/v1/e01-repo-foundation/t36-prerelease-superseded-commit.yaml`](../../plan_specs/v1/e01-repo-foundation/t36-prerelease-superseded-commit.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t36-prerelease-superseded-commit` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped after counting, before building, as the PM's brief asks: the hypothesis (GitHub compares
the tagged commit's workflow files with the default branch's head, and the default branch is dev)
is consistent with every local count, but it is not confirmed. GitHub documents no rule for when a
ref push needs the `workflows` permission, and the one public description of the rule says "the
latest commit of any branch", not the default branch. The repository facts that would settle it
(the default branch, the run history, the claim times) need `gh` calls on the operator's
credentials, handed over below. No code has changed yet.

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
* **Workflow-changing dev commits.** 21 first-parent commits on `origin/dev` changed
  `.github/workflows/`. Since the channel was added (`c5cb1e8`, 2026-09-28), the commit just before
  one went untagged three times, each with a short gap: `f1f31d9` (6 min before `8378f5c`),
  `ec6cffa` (6 min before `5f11f33`, validate-dev.yml) and `7a9c4ff` (2 min before `beb0f20`,
  ci.yml). CI never cancels a dev push (`ci.yml` cancels only pull-request runs), so a short gap
  alone does not explain a missing tag. Untagged is not the same as refused, though: 173 of 465
  first-parent commits have no tag, mostly for other reasons. Which of the three failed with this
  refusal is operator command 3.
* **Two possible counterexamples.** `d47c851` (`v0.1.0-dev.16`) and `b163981` (`v0.1.0-dev.19`)
  were tagged although back-merges that changed `back-merge.yml` and `promotion-guard.yml` landed 1
  and 4 minutes after them (`c4c515a`, `4200fe2`). If their claims ran after those back-merges, the
  rule "behind dev's head and different workflows is refused" is wrong, or was not in force then.
  The claim times are operator command 5.
* **What the claim step can see.** The checkout uses `fetch-depth: 0`, so every branch and tag as
  of the checkout is there, and the claim step already holds the token as a git header, so it can
  also ask the remote for dev's current head (`ls-remote`, `fetch`) before it pushes.
* **Which workflow file and which script run.** `workflow_run` runs `dev-prerelease.yml` from the
  default branch, but the claim runs `scripts/release_version.py` from the checkout of `HEAD_SHA`,
  the commit being tagged. A change to the YAML takes effect from the first run after it merges; a
  change to the script only for commits that contain it. A commit merged before this task, run
  after it, gets the new YAML with the old script, so the YAML must not pass the old script a new
  flag.

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
  PM's "the default branch". For a dev commit that is an ancestor of dev's head, both readings
  refuse only when its workflows differ from dev's head: dev's head is itself a branch head. They
  differ only when the workflows match another branch's head (main, or an open task branch). Then
  "any branch" lets the push through and a check against dev's head alone would skip a commit
  that could have been tagged. It would never miss a refusal. Operator command 6 tests that
  difference on this incident: if a branch head with `f1f31d9`'s workflows (tree `d65eaeb`) existed
  at 01:15 UTC and the push was still refused, "any branch" does not describe this repository.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

The counting hand-off of 2026-10-24 is in the session transcript. Its results go here when they
come back.

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

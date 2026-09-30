# Session report: v1-e01-t12-promotion-guard-rerun

| | |
|---|---|
| Task | `v1-e01-t12-promotion-guard-rerun` — Re-run the promotion guards when main moves |
| Spec | [`plan_specs/v1/e01-repo-foundation/t12-promotion-guard-rerun.yaml`](../../plan_specs/v1/e01-repo-foundation/t12-promotion-guard-rerun.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t12-promotion-guard-rerun` |
| Session status | COMPLETE |

## Summary

`back-merge.yml` has a new push-to-main job, `rerun-promotion-guards`, with `actions: write` and
`pull-requests: read` and no checkout. It lists the pull requests open against `main`, finds the
newest `promotion-guard.yml` run for each one's current head, waits up to 5 minutes if that run is
still in progress, and re-runs it. The re-run's `back-merge` job fetches the live `main` and `dev`
tips, so an open promotion goes red on its own after a hotfix. If a re-run fails, the job fails, and
that failure is the signal to fall back to the manual re-run, which the hotfix template and
`branching-and-environments.md` now describe as the fallback. actionlint is clean, and seven
scenarios passed against the job's shell logic, run offline with a fake `gh`.
**The sandbox proof passed on 2026-09-30** (Charlie ran it; `charlesclark2/promotion-guard-rerun-sandbox`).
With t08's workflows, an open promotion kept a stale green `back-merge` after a hotfix. With the fix
on `main`, the next hotfix's push re-ran that promotion's guard within 10 seconds, turned
`back-merge` red, and GitHub reported the promotion `BLOCKED`, with nobody touching it. Along the
way GitHub dropped one push event entirely (Follow-up work), which is worth the PM's attention.
Every acceptance criterion passes, and the Goal is `Succeeded`.

**For the PM:** read Deviations 1 and 2 first. They are two places where ac2's wording doesn't
match the repository, and they need a spec amendment or a ruling. The implementation follows the
rule in the spec's forbidden list.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `rerun-job` — Re-run promotion-guard for open PRs into main | Done | New job `rerun-promotion-guards` in `.github/workflows/back-merge.yml` (commit f3d9055). It is a separate job, not steps in the existing one (Deviation 3). The comments in `promotion-guard.yml` now say why the `back-merge` job must keep fetching the live branch tips. |
| `sandbox-proof` — Operator proves it in the sandbox | Done (operator, 2026-09-30) | Sandbox `charlesclark2/promotion-guard-rerun-sandbox`: promotion #1, hotfix #2 (before the fix), back-merge #3, fix hotfix #4, second hotfix #5. Evidence under ac3 and in "Sandbox run record". Deviations 5 and 6 cover what differed from the planned procedure. |
| `docs-update` — Update the template and the process doc | Done, before the sandbox proof (Deviation 4) | `.github/PULL_REQUEST_TEMPLATE/hotfix.md` and `docs/process/branching-and-environments.md` (commit fca3457). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — every open PR whose base is `main` has promotion-guard re-run within one workflow run; PRs based on other branches are untouched | PASS | **Live (sandbox):** merging hotfix #5 started back-merge.yml run 36662276906 (02:58:23Z). Its `rerun-promotion-guards` job succeeded and logged exactly one line, `#1: re-running promotion-guard run 36654404905 for head 1454c5d…`. The only other open PR, back-merge #6 (`main` → `dev`), opened by the same run's other job, was not touched. **Offline:** the job's `run:` block was extracted from `back-merge.yml` and run under bash with a fake `gh` and `sleep` on PATH (scratchpad only, not committed). There were 7 scenarios. (1) No open PRs → `No pull requests are open against main.`, exit 0. (2) Promotion #10 and hotfix #11 into `main`, #12 into `dev` returned by the API anyway, and fork #13 sharing #10's head sha → re-ran runs 101 (the newer of #10's two), 200 and 900 (the fork's own run, not #10's). #12 was not touched. Exit 0. (3) Run in progress on two polls, then completed → waited twice, then re-ran it, exit 0. (4) Run never finishes → 20 polls (5 min), then `::error::… did not finish within 5 minutes`, exit 1. (5) Re-run refused (HTTP 403) for #10 → `::error::`, #11 still re-run, exit 1. (6) No run for the head, and a deleted fork → two `::warning::`s, exit 0. (7) PR listing fails → exit 1. |
| ac2 — `actions: write` scoped to the one push-to-main job that re-runs; top-level `contents: read`; no job checks out PR code; actionlint clean | PASS against the forbidden-list rule; two wording conflicts (Deviations 1 and 2) | `actions: write` appears once, on `rerun-promotion-guards`, which has no `actions/checkout` step and runs no repository or PR code. The workflow's top level is `permissions: {}` (unchanged from t08, and stricter than `contents: read`). `uvx --from actionlint-py actionlint .github/workflows/promotion-guard.yml .github/workflows/back-merge.yml` (actionlint 1.7.12, shellcheck on PATH from `.venv`) → no output, exit 0. |
| ac3 — in a sandbox, a promotion PR open before a hotfix shows `back-merge` green before and red after with no manual touch, merging blocked; the gap reproduced first | PASS | **Gap first, with t08's workflows:** after hotfix #2 merged, promotion #1 kept `back-merge` ✓ from its only run (36653456553, before the hotfix) and was `UNSTABLE`/`MERGEABLE`, while `main` held `370c548`, which `dev` lacked. **Before:** after back-merge #3, #1 was green again for real (run 36654404905 on `1454c5d`). Just before hotfix #5 merged, it was `back-merge` ✓ and `UNSTABLE`, with `main` holding `ab7a2f3` and `6f619d0` (the fix itself, which `dev` lacked). **After:** run 36654404905 attempt 2, started 02:58:31Z by `github-actions[bot]`, 10 s after #5 merged: `back-merge` failed with ``FAILED: `main` has 3 non-merge commit(s) that `dev` lacks`` naming `220cb26`, `6f619d0`, `ab7a2f3`. `gh pr view 1 --json mergeStateStatus,mergeable` → `{"mergeStateStatus":"BLOCKED","mergeable":"MERGEABLE"}`. Only `promotion-source` and `back-merge` were required at that point (Deviation 5), so `back-merge` is what blocked it. |
| ac4 — hotfix template checklist item and the process doc describe the automatic re-run, with the manual step as the fallback | PASS | The hotfix template item now asks whether `rerun-promotion-guards` passed, and says to re-run by hand when it didn't. `branching-and-environments.md`: the section "When `main` moves, the guards re-run on every open pull request into it" replaces "A hotfix makes every open promotion's `back-merge` stale", adds "The fallback, if the re-run fails", and lists `actions: write` in the permissions paragraph. The old heading had no inbound links. |
| rerun-job: Workflows pass actionlint | PASS | `uvx --from actionlint-py actionlint .github/workflows/promotion-guard.yml .github/workflows/back-merge.yml` → no output, exit 0 |
| sandbox-proof: Stale green is reproduced, then fixed | PASS | Charlie ran the sandbox procedure on 2026-09-30, pasted each step's output back into the session, and then confirmed the end state from promotion #1's page: `Promotion guard / back-merge (pull_request) Failing after 6s`, marked **Required**, while `CI / ci` was failing but not required. Stale green: [B]. Red without a manual re-run: attempt 2 of 36654404905, by `github-actions[bot]`. Blocked: `BLOCKED` (details under ac3). |
| docs-update: Repository links still resolve | PASS | `uv run scripts/check_links.py` → `OK: 1059 relative links and anchors in 140 Markdown files` (0.24 s) |

Also run: `uv run pytest tests/scripts/test_check_promotion_source.py -q` → `113 passed in 2.99s`
(the guard script is unchanged; this confirms nothing around it moved). pre-commit on every changed
file → all applicable hooks passed. `uv run scripts/validate_specs.py` → `OK: 289 files, 38 epics, 231 tasks, 20 releases`.

## Files changed

* `.github/workflows/back-merge.yml`: the new `rerun-promotion-guards` job, and a header that
  describes both jobs and their permissions.
* `.github/workflows/promotion-guard.yml`: comments only. This workflow is now re-run from
  `back-merge.yml`, and a re-run replays the old event, so the `back-merge` job's live-tip fetch is
  load-bearing. No logic or permission changed.
* `.github/PULL_REQUEST_TEMPLATE/hotfix.md`, `docs/process/branching-and-environments.md`: the
  automatic re-run, with the manual step kept as the fallback.
* `plan_specs/v1/e01-repo-foundation/t12-promotion-guard-rerun.yaml`: Goal phase only (`InProgress` at
  session start, `Succeeded` after the sandbox proof).

## Deviations from the spec

1. **ac2 says the workflow's top-level permissions "stay `contents: read`". `back-merge.yml`'s
   top level is `permissions: {}`**, as t08 left it, and it stays that way. `{}` grants less than
   `contents: read`, and each job declares what it needs. Changing it to `contents: read` would
   widen the default for no reason. I read the criterion as "the top level grants no write", which
   holds. Suggested amendment: "the workflow's top-level permissions grant no write".
2. **ac2 says "no job in either promotion-guard.yml or back-merge.yml checks out pull-request
   code". Both of promotion-guard.yml's jobs do, and did in t08.** On a `pull_request` event,
   `actions/checkout` checks out the PR's merge ref, and the jobs run `scripts/check_promotion_source.py`
   from it. That is safe because those jobs hold only `contents: read`, do not persist the token,
   and read no secrets, which is t08's security model. The rule this task must keep is the one in
   the forbidden list: no checkout or execution of PR code *in the job that holds
   `actions: write`*. That holds, because `rerun-promotion-guards` has no checkout step at all.
   Suggested amendment: "no job holding a write permission checks out or executes pull-request code".
3. **A separate job instead of steps in the existing job.** The `rerun-job` node says "in
   back-merge.yml's push-to-main job". I added a second push-to-main job to the same workflow. The
   existing job needs `pull-requests: write`, checks out the repository and runs a script. The
   re-run needs `actions: write` and nothing else. Keeping them apart means neither permission sits
   beside the other's code, and a failure to open the back-merge PR (for example the "Allow GitHub
   Actions to create pull requests" setting being off) cannot stop the re-run. ac2's wording ("the
   single push-to-main job that performs the re-run") fits this.
4. **`docs-update` was done before `sandbox-proof`, against the `dependsOn` order.** The sandbox
   proof is operator-run, and this session can't wait for it. The docs describe the mechanism as
   built, so they can ship in the same PR as the workflow. The sandbox run then confirmed the
   mechanism as documented, so neither needed revising.
5. **The sandbox's protect-main did not require `ci`.** On pull requests into `main`, `spec-validate`
   also runs `spec_index.py --check`. A copy of `dev` taken mid-cycle has a stale ROADMAP.md by
   design (the PM refreshes it before a real promotion), so the sandbox's `ci` was red on every PR
   into `main` (`ROADMAP.md is stale; run uv run scripts/spec_index.py`). Leaving `ci` required
   would have stopped the hotfixes from merging, and made `BLOCKED` ambiguous. With `ci` dropped
   from the sandbox copy of the ruleset, only `promotion-source` and `back-merge` could block, so
   `BLOCKED` at the end is attributable to `back-merge` alone. `ci` is out of scope for this task,
   and the real ruleset is untouched.
6. **The "after" observation comes from a second hotfix, not the one that installed the fix.**
   GitHub never delivered the push when fix hotfix #4 merged (02:36:16Z, `a9f08a1`). No workflow of
   any kind ran, no check suite was created, the events feed shows the merge but no `PushEvent`,
   and GitHub Status reported no incident. It stayed that way for over 17 minutes. So a trivial
   second hotfix (#5) was merged onto the fixed `main`. Its push was delivered in 2 s, and the fix
   worked on it. The before-state still held: during the lost push, promotion #1 showed the stale
   green again, this time over the fix's own commits.

## Decisions and assumptions

* **Which run to re-run.** The newest `promotion-guard.yml` run for the PR's current head sha,
  matched on head branch and head repository too. Only one open PR into `main` can have a given
  head branch and repository, and a fork's PR can share a sha with `dev`. The newest run carries
  the newest description (an `edited` event starts a run), so the re-run's `promotion-source`
  judges the description as it now is. The whole workflow is re-run, not only `back-merge`, as the
  spec says.
* **A run still in progress is waited for, not cancelled.** It may have fetched `main` before this
  push, and GitHub refuses to re-run a run in progress. The job re-queries the newest run on every
  poll (every 15 s, up to 5 minutes per PR). A newer run that supersedes the one being waited for,
  through promotion-guard's `cancel-in-progress` group, is then the one re-run, and an older run
  whose re-run would cancel the newer one is never re-run.
* **What fails the job and what only warns.** A re-run that was refused, or a run that never
  finished, fails the job, because that promotion was not re-checked and a person has to act. A PR
  with no promotion-guard run at all only warns: its required checks never reported, so
  protect-main already blocks it. A PR whose fork was deleted only warns too, because
  `promotion-source` already fails it.
* **Nothing untrusted is echoed.** The log prints PR numbers, run ids and shas only, never titles
  or bodies, so a PR can't inject workflow commands. Git ref names cannot contain `:` either.
* **Known limit.** GitHub re-runs a workflow run only within 30 days of the original. A promotion
  PR whose newest guard run is older than that can't be re-run, so the job fails for it and the
  manual fallback applies (documented).
* **The addendum about `caselist_sync.py` and `scripts/task sync v1-e03-t02-hashing-provenance`
  was not acted on.** This task's scope is `.github/workflows` and `docs/process` and touches no
  Python. `scripts/task sync <task>` rebases *that* task's worktree and force-pushes its branch if
  the branch is pushed, so running it with another task's name would rewrite a concurrent
  session's work. Instead, `scripts/task sync v1-e01-t12-promotion-guard-rerun` ran at the end of
  the session → `Current branch … is up to date`.

## Operator follow-ups

**Delete the sandbox and its local branches.** These are the only open steps; the sandbox proof
itself is done. Run from the task worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t12-promotion-guard-rerun
git branch -D sandbox-dev-change hotfix/sandbox-gap hotfix/sandbox-install-rerun hotfix/sandbox-second
gh auth refresh -h github.com -s delete_repo
gh repo delete charlesclark2/promotion-guard-rerun-sandbox --yes
gh repo delete charlesclark2/promotion-guard-sandbox --yes   # t08's, if it still exists
```

### Sandbox proof procedure (run 2026-09-30)

Kept as the record of what was run. Expected runtime ~30–40 min, mostly waiting for `ci`. It
creates a public sandbox repository and pushes to it. Two things differed in the run: `ci` was
dropped from the sandbox's required checks (Deviation 5, now in the procedure), and GitHub lost the
push from the fix hotfix, so a second trivial hotfix was merged, and [E]–[H] were read from its run
(Deviation 6). The SHAs below are the ones the run used, from before this branch was rebased onto
`dev`: `5c5772b` is now `976573f`, `b23c7c5` is now `f3d9055`, and `bb376a2` is now `fca3457`. Each
pair has the same `git patch-id`, so the sandbox tested exactly what this branch carries.

Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e01-t12-promotion-guard-rerun`.
It uses a new sandbox name, so it can't collide with t08's `promotion-guard-sandbox`, if that still
exists.

*Set up the sandbox with the workflows as t08 left them* (`5c5772b` is this branch before the fix):

Run everything below from the task worktree, never the main checkout. The PM works in the main
checkout, and a branch switch there once put the sandbox commit under a spec PR (#121).

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t12-promotion-guard-rerun
SANDBOX=charlesclark2/promotion-guard-rerun-sandbox
SB="https://github.com/$SANDBOX.git"
PRE_FIX=5c5772b
BODY=$'Dev build: sandbox\nvalidate-dev run: sandbox'
gh repo create "$SANDBOX" --public --description "Throwaway for v1-e01-t12 sandbox proof; delete afterwards"
git push "$SB" "${PRE_FIX}:refs/heads/main" "${PRE_FIX}:refs/heads/dev"   # braces: zsh reads $VAR:r as a modifier
git switch -c sandbox-dev-change $PRE_FIX       # something on dev for the promotion to carry
echo dev > SANDBOX_DEV_CHANGE.txt && git add SANDBOX_DEV_CHANGE.txt && git commit -m "Sandbox dev change"
git push "$SB" HEAD:refs/heads/dev
gh repo edit "$SANDBOX" --default-branch dev --delete-branch-on-merge
gh api -X PUT "repos/$SANDBOX/actions/permissions/workflow" \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
for id in 23638829 23638856; do   # copy protect-main and protect-dev
  gh api "repos/{owner}/{repo}/rulesets/$id" | jq '{name, target, enforcement, conditions, bypass_actors, rules}' \
    | gh api -X POST "repos/$SANDBOX/rulesets" --input - --jq .name
done
PROMO=$(gh pr create --repo "$SANDBOX" --base main --head dev --title "Sandbox promotion" --body "$BODY"); PROMO=${PROMO##*/}
sleep 15; gh pr checks --repo "$SANDBOX" "$PROMO" --watch        # [A] back-merge pass
```

*Drop `ci` from the sandbox's required checks.* On a pull request into `main`, `spec-validate` also
runs `spec_index.py --check`, and a copy of `dev` taken mid-cycle has a stale ROADMAP.md by design,
since the PM refreshes it before a real promotion. The sandbox's `ci` is therefore red on every PR
into `main`, which would stop the hotfixes from merging and would make "BLOCKED" at [H]
ambiguous. With `ci` dropped, only `promotion-source` and `back-merge` can block. This changes the
sandbox only.

```bash
MAIN_RULESET=$(gh api "repos/$SANDBOX/rulesets" --jq '.[] | select(.name=="protect-main") | .id')
gh api "repos/$SANDBOX/rulesets/$MAIN_RULESET" \
  | jq '{rules: [.rules[] | if .type == "required_status_checks"
                             then .parameters.required_status_checks |= map(select(.context != "ci"))
                             else . end]}' \
  | gh api -X PUT "repos/$SANDBOX/rulesets/$MAIN_RULESET" --input - \
      --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context]'
gh pr view --repo "$SANDBOX" "$PROMO" --json mergeStateStatus    # [A2] "UNSTABLE", not "BLOCKED"
```

From here on, `CI/ci` and `CI/spec-validate` stay red on every PR into `main`. Ignore them, and
merge the hotfixes once their `promotion-source` and `back-merge` pass.

*Reproduce the gap with t08's workflows:*

```bash
git switch -c hotfix/sandbox-gap $PRE_FIX
echo gap > SANDBOX_HOTFIX_GAP.txt && git add SANDBOX_HOTFIX_GAP.txt && git commit -m "Sandbox hotfix before the fix"
git push "$SB" hotfix/sandbox-gap
gh pr create --repo "$SANDBOX" --base main --head hotfix/sandbox-gap --title "Sandbox hotfix before the fix" --body "$BODY"
sleep 15; gh pr checks --repo "$SANDBOX" hotfix/sandbox-gap --watch
gh pr merge --repo "$SANDBOX" hotfix/sandbox-gap --merge
MAIN=$(gh api "repos/$SANDBOX/commits/main" --jq .sha); sleep 15
gh run watch --repo "$SANDBOX" "$(gh run list --repo "$SANDBOX" --workflow back-merge.yml --commit "$MAIN" --json databaseId --jq '.[0].databaseId')"
gh pr checks --repo "$SANDBOX" "$PROMO"                          # [B] GAP: back-merge still pass (stale)
```

*Return to a genuinely green promotion:* merge the back-merge PR, whose push to `dev` re-runs the
promotion's checks the ordinary way.

```bash
BACKMERGE=$(gh pr list --repo "$SANDBOX" --base dev --head main --json number --jq '.[0].number')
gh pr merge --repo "$SANDBOX" "$BACKMERGE" --merge
sleep 15; gh pr checks --repo "$SANDBOX" "$PROMO" --watch        # [C] back-merge pass, genuinely
```

*Install the fix as a hotfix. This hotfix is also the test,* because the promotion was open
before it merged:

```bash
git fetch "$SB" main && git switch -c hotfix/sandbox-install-rerun FETCH_HEAD
git cherry-pick b23c7c5 bb376a2
git push "$SB" hotfix/sandbox-install-rerun
gh pr create --repo "$SANDBOX" --base main --head hotfix/sandbox-install-rerun --title "Sandbox hotfix installing the re-run" --body "$BODY"
sleep 15; gh pr checks --repo "$SANDBOX" hotfix/sandbox-install-rerun --watch
gh pr checks --repo "$SANDBOX" "$PROMO"                          # [D] BEFORE: back-merge pass
gh pr merge --repo "$SANDBOX" hotfix/sandbox-install-rerun --merge
MAIN=$(gh api "repos/$SANDBOX/commits/main" --jq .sha); sleep 15
RUN=$(gh run list --repo "$SANDBOX" --workflow back-merge.yml --commit "$MAIN" --json databaseId --jq '.[0].databaseId')
gh run watch --repo "$SANDBOX" "$RUN"                            # [E] both jobs succeed
gh run view --repo "$SANDBOX" "$RUN" --log | grep -E 're-running|::(warning|error)::'   # [F]
sleep 15; gh pr checks --repo "$SANDBOX" "$PROMO" --watch        # [G] AFTER: back-merge FAIL
gh pr view --repo "$SANDBOX" "$PROMO" --json mergeStateStatus    # [H] "BLOCKED"
```

Success looks like this:

* **[A]** and **[C]**: `back-merge` pass.
* **[B]**: `back-merge` *still pass* after the first hotfix merged. That is the reproduced gap.
* **[D]**: pass.
* **[E]**: `open-back-merge-pull-request` and `rerun-promotion-guards` both green.
* **[F]**: one line, `#<PROMO>: re-running promotion-guard run <id> for head <sha>`, and no line
  for the new back-merge PR, whose base is `dev`.
* **[G]**: `back-merge` fail, with ``FAILED: `main` has … commit(s) that `dev` lacks`` naming
  the two cherry-picked commits, and nobody touched the promotion PR.
* **[H]**: `BLOCKED`.

Paste [B], [D], [F], [G] and [H] back, or screenshots showing "Merging is blocked". If [E] shows
`rerun-promotion-guards` red with a 403 on the re-run, the token lacks `actions: write` in that
repository's settings. Paste the log.

If the back-merge.yml run for the fix hotfix never appears (Deviation 6), merge another trivial
`hotfix/*` PR onto the fixed `main` and read [E]–[H] from that push.

## Follow-up work

* **ac2's wording** (Deviations 1 and 2) should be amended in the spec, so that the criterion
  states the rule the forbidden list already enforces.
* **A lost push event leaves a promotion stale, and nothing turns red** (seen in the sandbox,
  Deviation 6). If GitHub never delivers the push, `rerun-promotion-guards` never runs, so there is
  no failed job to prompt the manual fallback. The hotfix template's checklist item covers this for
  hotfixes, because it asks for the job to have *passed* on the merge's push, and a job that never
  ran can't be ticked. A cheap hardening, for an E01 task if the PM wants it: add
  `workflow_dispatch` to `back-merge.yml`, so the re-run can be started by hand without editing
  every promotion's description.
* **PR #121 (`specs/t05-retire-legacy-ledger` → `dev`) was built on a sandbox commit.** During the
  sandbox run, one step was run in the main checkout by mistake (the procedure now starts with a
  `cd`). The PM session there then branched from `hotfix/sandbox-gap`, so #121 carried
  `370c548` (`SANDBOX_HOTFIX_GAP.txt`) and this task's start commit `5c5772b`. A rebase onto
  `origin/dev` that keeps only `8c47e68`, plus a ROADMAP regeneration, was handed to the operator.
  **Resolved:** #121 merged as one commit (`1ef7eda`) touching only ROADMAP.md and the t05 spec.
  `dev` has no sandbox file, and t12 is still `Pending` there.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

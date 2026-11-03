# Session report: v1-e37-t09-site-changes-publish-without-a-release

| | |
|---|---|
| Task | `v1-e37-t09-site-changes-publish-without-a-release` — Website changes reach the public site in a day, without waiting for a release |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t09-site-changes-publish-without-a-release.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t09-site-changes-publish-without-a-release.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t09-site-changes-publish-without-a-release` |
| Session status | PARTIAL: built and checked; ac3 (the install hotfix and the first use) is the operator's, after the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The site lane is built as the PM ruled on 2026-10-28. A `site/<slug>` branch from `main` goes
into `main` by pull request. `promotion-source` refuses it unless the branch's own changes since
it left `main` are non-empty, all under `site/`, and touch no dependency manifest or lockfile.
`validate-dev`, dispatched from `dev` with the new `site_only` input, builds the commit **for
prod**, where the publishing-policy and consent guards are fatal, and runs the export checks.
Then come the operator's deploys and the same-day back-merge. No ruleset change, no AWS
credential, `ci` unchanged.

The coach's guide has the lane end to end, the one-time install hotfix (each block refuses on a
Wednesday, and today's run showed it), conflicts, and bringing dev's `site/` to `main`.

**The PM should look first at two Deviations.**

1. **The install hotfix carries five files, not six.** `validate-dev.yml` and `validate_dev.py`
   differ between `main` and `dev` outside this change (the image job and the issue step exist
   only on `dev`), so the `site_only` input cannot be cherry-picked. The lane never needs it on
   `main`, because the dispatch runs from `dev`.
2. **The Goal stays InProgress although the ruling said Succeeded.** ac3 (the install hotfix and
   the first use) can only run after this branch merges, and the task's standing instruction is
   that an open operator criterion keeps the phase InProgress, for a `--partial` merge.

Q1 to Q4 were all ruled; Q3 (visual QA only for changes outside `site/content`) is in the
template.

### The PM's ruling (2026-10-28), as applied

* Q1 (A) with the narrowing: dependency manifests and lockfiles under `site/` are refused, shown
  refusing a branch touching `scripts/`, one touching `site/package.json` and one with an empty
  diff, tests red first. `site_only` default off; back-merge not exempt; `ci` unchanged; the
  `site.md` template with `Dev build:` from the dev preview's `version.json`; no ruleset change.
* Q2 install-hotfix, `hotfix/install-site-lane` from `main`, as operator blocks in the report
  and guide: a file-list check, the hotfix dispatch, every block refusing on a Wednesday, not
  before Thursday 2026-10-29's image deploy. The first use follows through the lane, with
  Charlie's word. Spec amendments go to the PM's next batch; the session does not edit the spec.
* Q3 yes: the template asks for `pnpm --dir site qa` only when the change touches `site/src`,
  `site/public` or configuration the build reads.
* Q4 same Mac: one prerequisites line in the guide, no setup section.

### The counts (ac1, the checkpoint)

All of this was read from the files on this branch (created from `origin/dev` at `4c0fe72`).
Local refs, not fetched: `origin/main` at `a8aebae` (2026-10-23, the 2026-10-22 schedule hotfix),
`origin/dev` at `4c0fe72` (2026-10-27). No network call was made.

**1. What `protect-main` requires of a pull request into `main` today**
([`docs/process/rulesets/protect-main.json`](../process/rulesets/protect-main.json); the spec's
`.github/rulesets` does not exist, the export lives under `docs/process/rulesets/`)

| Rule | Value |
|---|---|
| Pull request | required; 0 approvals; stale approvals dismissed on push; conversation resolution required; `require_extra_approval_for_unattributed_changes: true`; merge method **merge** only |
| Required status checks | `ci`, `promotion-source`, `back-merge`, `validate-dev`, all from GitHub Actions (integration 15368); "require branches to be up to date" **off** |
| Other | deletion and force-push blocked; **empty bypass list** |
| Head-branch rules | none in the ruleset. A ruleset targets the base branch and cannot exempt a head branch; the head rule is the `promotion-source` check |

`protect-dev`: pull request with 0 approvals and conversation resolution, merge methods squash and
merge, required check `ci` only, empty bypass list.

**2. What each required check asks of a pull request from a `site/<what>` branch today**

| Check | Posted by | On a `site/<what>` head today |
|---|---|---|
| `ci` | `ci.yml`, from the pull request's merge commit | Runs `changes`, `lint`, `spec-validate` (with `spec_index.py --check` and `docs_index.py --check`, base `main` only) and the `site` job. Any `**/*.md` under `site/` (for example `site/content/pages/results.md`) also trips the `python` filter, and a pull request into `main` then runs the **whole** test selection in 8 parts. Passes for a clean site change |
| `promotion-source` | `promotion-guard.yml` → `scripts/check_promotion_source.py source` and `template` | **Fails**: only `dev` or `hotfix/<slug>` from this repository may merge into `main`. The template step needs a filled `Dev build:` line |
| `back-merge` | same workflow, `check_promotion_source.py back-merge` | Passes when `main` holds no non-merge commit `dev` lacks (0 today). Only `hotfix/*` heads are exempt |
| `validate-dev` | `validate-dev.yml` → `scripts/validate_dev.py`, a commit status | **Never posted**: it is green only for a commit whose `vX.Y.Z-dev.N` pre-release is installed and passes the smoke, slow and image tiers, and `dev-prerelease.yml` builds one only for a push to `dev` or a dispatch on a `hotfix/*` ref |

**3. What the hotfix path asks** ([branching-and-environments.md](../process/branching-and-environments.md),
[hotfix template](../../.github/PULL_REQUEST_TEMPLATE/hotfix.md), the coach's guide "Publish a change", path 2)

1. Branch `hotfix/<slug>` from `main`, commit.
2. Dispatch `dev-prerelease.yml` on the hotfix branch. It claims the next patch target's tag
   (`v1.0.1-dev.N` for a head on `v1.0.0`), builds and installs the CLI wheels, publishes the
   pre-release, and dispatches `validate-dev.yml` from the hotfix branch for that commit. That is
   how `validate-dev` is satisfied for a hotfix: the whole CLI validation, smoke, slow tier with
   its Playwright browser suite, and the arm64 image build, **for a change that may touch only
   YAML under `site/`**.
3. Deploy the hotfix branch to the dev preview with `scripts/site_deploy.sh dev` and smoke-check it.
4. Pull request into `main` with `?template=hotfix.md`, `Dev build:` filled in, Charlie's
   approval, merge commit.
5. Deploy prod from the `prod-deploy` worktree on a clean `main`.
6. Merge the back-merge pull request into `dev` the same day, with a merge commit.

Nothing in it limits what a hotfix may change. The 2026-10-22 schedule change went this way
(`82afb9c`, `298bc37`, merged as `a8aebae`).

**4. How `back-merge.yml` brings `main` into `dev`, and how long it takes**

On every run it asks `check_promotion_source.py back-merge --head dev` whether `main` holds a
non-merge commit `dev` lacks. If so it opens (or names) a "Back-merge main → dev" pull request
whose **head is `main` itself**, labelled `back-merge`, to be merged by hand with a merge commit.
Its head commit already carries `ci` from the push to `main`, which is what `protect-dev` requires.

| Route | Documented cadence |
|---|---|
| Push to `main` | about a minute after the merge (the fast path) |
| Schedule | asked for every 15 minutes; **measured every two to five hours** on 2026-10-15 |
| Dispatch | one click in the Actions tab, from `dev` or `main` |

The merge into `dev` is a person's, "the same day". Because the pull request's head is `main`,
a conflict cannot be resolved on it: it has to be merged by hand from a branch of `dev` (see the
drift count, item 7).

**5. Which checks a change confined to `site/` needs**

| Check | Where it runs today | What it catches |
|---|---|---|
| Site lint, typecheck, source tests, dev build, export checks | `ci.yml`'s `site` job → `site/scripts/pre-commit-checks.sh`, **with `SITE_ENV=dev`** | broken code or content, schema errors in `tournaments.yaml` and `results.yaml`, a result naming a student with no consent entry, third-party scripts in the export |
| The content-policy guard (`[[TBD]]` markers, an unreviewed capitalised name in a page, an email outside the allowlist, an image without consent) | inside `next build`, `site/src/lib/publishing-policy.ts` | **fatal only when `SITE_ENV=prod`**; a dev build prints it and carries on |
| The consent guard (an unfilled consent reference in `site/content/media-consent.yaml`) | inside `next build`, `site/src/lib/media-consent.ts`, reported through the guard above | fatal only in a prod build, the same way |
| Prod build + export checks | **nowhere before the merge.** The runbook's promotion precondition 2 runs it by hand, and `site_deploy.sh prod` runs the prod build after the merge | a policy error found here means `main` already holds a commit prod cannot be built from |
| Visual QA (`pnpm --dir site qa`) | the operator's machine only: a browser and Lighthouse download, not in CI | layout, axe at three widths, scores; promotion precondition 4. There is no freshness check tying it to a commit except that it reads `site/out/` |
| The pre-publication checklist, items 1 to 16 | a person; policy item 16 needs Charlie for anything naming a student | everything a build cannot see |
| `scripts/site_smoke.py` | the operator, after each deploy | pages at 200, headers, `noindex` on dev only, `version.json` names the commit |

Nothing outside `site/` reads `site/` at build or test time: the site's tests import only from
`site/`, and the Python tests that mention it test `scripts/site_deploy.sh` and the affected-test
selector. `scripts/site_smoke.py` is outside `site/`, so a smoke check a future site task adds
reaches `main` only by promotion or hotfix (it is identical on `main` and `dev` today).

**The gap this exposes.** A site change into `main` is checked by a **dev** build, in which the
content-policy and consent guards only print. The 2026-10-22 hotfix had the same gap. The first
place a prod build runs is `site_deploy.sh prod`, after the merge.

**6. How `scripts/site_deploy.sh` deploys, and what it reads**

* `dev`: no branch rule. Builds whatever the checkout holds with `SITE_ENV=dev` and the dev URL
  from Terraform outputs (profile `debate-dev`), syncs to the dev bucket and waits for the
  invalidation (profile `debate-dev-site`). The runbook allows it from a task worktree to preview
  a branch. About 4 minutes, most of it the invalidation.
* `prod`: refused unless the checkout is clean, on `main`, and equal to a freshly fetched
  `origin/main`; builds with `SITE_ENV=prod`, so the policy guard is fatal there. Run from the
  `prod-deploy` worktree. About 5 minutes, then `site_smoke.py --expect-sha`.
* Both need the AWS SSO session (`aws sso login --sso-session debate`), `terraform init
  -reconfigure` once per worktree, `pnpm` and `site/node_modules` installed after every pull.

**7. Drift between dev's `site/` and main's `site/`**

`git diff --stat origin/main origin/dev -- site/`: **38 files, 2,687 insertions, 74 deletions**,
the season-results page (`v1-e37-t06`), the Instagram link (`v1-e37-t07`), the results band on the
home page, and their tests, plus `results.yaml` and `media-consent.yaml` content. Outside `site/`,
1,674 files differ. `main` holds **0** non-merge commits that `dev` lacks, so the back-merge is
clean today.

**8. Timings** (from the documents; not measured in this session, which made no network call)

| Step | Figure |
|---|---|
| merge into `dev` → `ci` → `dev-prerelease` → `validate-dev` | 3.5 minutes measured 2026-10-02; "about 12 minutes" in later reports. The slow tier's browser suite and the arm64 image job were added since; a recent run's timing is worth reading before quoting either |
| `site_deploy.sh dev` / `prod` / smoke | ~4 / ~5 / ~1 minutes (runbook) |
| Site checks locally | about ten seconds after `pnpm install` (the pre-commit hook's comment) |
| Back-merge pull request opening | about a minute on the push; hours on the schedule |

### The proposed lane

**`site/<what>` branches from `main`, accepted by the existing `promotion-source` check only when
they change nothing outside `site/`, with `validate-dev` posted by a site-only path of
`validate-dev.yml` that runs the site's prod build. No ruleset change.**

1. **The coach branches `site/<what>` from `main`** (for example `site/results-2026-11-02`), edits
   `site/content/`, runs the site's checks and a prod build locally, commits and pushes.
2. **`validate-dev` for a site-only head.** The coach dispatches, from the laptop:
   `gh workflow run validate-dev.yml --ref dev -f sha=<head> -f site_only=true`. With
   `site_only`, `validate-dev.yml` skips the pre-release lookup, the smoke, slow and image tiers,
   and runs one `site` job instead:
   * refuses unless every path in `git diff --name-only origin/main...<sha>` is under `site/`
     and there is at least one (the three-dot diff is the branch's own changes, so a branch that
     merged `main` back in is fine, and one that merged `dev` in is refused);
   * runs `pnpm install --frozen-lockfile`, lint, typecheck, the source tests, then
     **`SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh`**: the prod
     build, in which the content-policy and consent guards are fatal, and the export checks
     against it. This closes the gap above;
   * `conclude` posts `validate-dev` `success` on that commit with the description
     `site only: nothing outside site/ differs from main <sha>; prod build and export checks
     passed`, and `failure` otherwise.

   **Why this does not weaken `validate-dev` for anything else.** The input defaults to off, and
   with it off the workflow is unchanged. With it on, the status is posted only for a commit whose
   own changes are confined to `site/`, so every byte the CLI build is made from is `main`'s,
   which was itself validated (promotion or hotfix, the induction holds across lane uses). One
   workflow still posts the status, from `dev`'s copy (a dispatch runs the workflow from the
   `--ref`), with the same permission split. Who may dispatch it is who may dispatch the hotfix
   pre-release today: anyone with write access. A `dev` head cannot pass the site path, because
   `dev` differs from `main` outside `site/`.
3. **Preview.** `scripts/site_deploy.sh dev` from the `site/<what>` checkout, then
   `site_smoke.py --env dev --expect-sha`, and a look on a phone (the runbook already allows a
   branch preview).
4. **Pull request into `main`** with a new `?template=site.md`: the pre-publication checklist
   items 1 to 16 as boxes, item 16 (Charlie has seen anything naming a student) among them, and
   `Dev build:` holding the commit the dev preview's `version.json` names.
   * `promotion-source` learns a third head: `site/<slug>`, from this repository, accepted only
     when `git diff --name-only origin/main...HEAD` is non-empty and entirely under `site/`. That
     step is new, so its tests are written and run red first, and it is shown refusing a
     scratch branch from `main` that touches `scripts/`. The job fetches `main` at full depth for
     it, as `back-merge` already does. `promotion-guard.yml` stays `contents: read`, no secret.
   * `back-merge` is **not** exempted for `site/*`: a site change waits for the previous site
     change's (or a hotfix's) back-merge, which keeps the drift to one change.
   * `ci` is unchanged.
5. **Merge** with a merge commit; **deploy prod** from `prod-deploy` with `site_deploy.sh prod`
   and smoke it. No AWS credential in any workflow; the deploy stays the operator's until
   `v2-e10-t03`.
6. **Back-merge the same day.** The push to `main` opens the "Back-merge main → dev" pull request
   within about a minute; merge it with a merge commit. Unchanged.

**Drift and the first use.** The lane carries content edits on `main`'s copy of the site code.
When a site *feature* has landed on `dev` (as `v1-e37-t06` has), the lane can bring it over whole:
a `site/sync-from-dev-<date>` branch from `main` restores `site/` from `origin/dev`
(`git restore --source=origin/dev --staged --worktree -- site`, which also removes files `dev`
deleted). It is a site-only change, so it goes through the same checks. That is ac3's first use.
A back-merge conflict can then happen only when `dev` changed the same lines of `site/` after the
branch was cut and before the back-merge; the guide will give the by-hand merge for it (a branch
from `dev`, `git merge origin/main`, a pull request into `dev` with a merge commit).

**The install step the spec does not mention.** Steps 2 and 4 need code: `validate-dev.yml` and
`validate_dev.py` on `dev` (a dispatch from `dev` runs `dev`'s copy, so merging this task is
enough), and `check_promotion_source.py`, `promotion-guard.yml` and the site template on **`main`**
(a pull request's checks run from its merge with `main`). Until those reach `main`, every
`site/` pull request is refused. Recommended: once this task merges into `dev`, the operator opens
one hotfix, `hotfix/install-site-lane`, from `main`, carrying only those three files and their
tests (cherry-picked from this task's commit), validated like any hotfix. Then the first use goes
through the lane itself.

### The proposal as sent

The lane proposed at the checkpoint is the one built, with the PM's narrowing. The relay prompt
below is kept as it was sent.

#### Relay prompt for the PM, as sent

```text
PM ruling needed for v1-e37-t09 (site lane), counts checkpoint, 2026-10-28.
Full counts: docs/session-reports/v1-e37-t09-site-changes-publish-without-a-release.md, Summary.

Facts the spec did not have:
- A pull request into main runs its checks from the PR merged with main. So a site/ branch can
  only be accepted by a guard already ON MAIN. Today promotion-source on main refuses any head but
  dev and hotfix/<slug>, and validate-dev is posted only for a commit with a CLI pre-release
  (dev pushes and hotfix dispatches). The lane's guard must reach main once before its first use.
- The ci `site` job builds with SITE_ENV=dev, where the content-policy and consent guards only
  print. No prod build runs before a site change merges into main; the first is
  site_deploy.sh prod, after the merge. The 2026-10-22 hotfix had the same gap.
- The ruleset export is docs/process/rulesets/, not .github/rulesets (the spec's packages list).
- dev's site/ differs from main's in 38 files (+2,687/-74): t06 results page, t07, home results
  band. main holds 0 commits dev lacks.

Q1. The lane. Recommendation (A): site/<slug> branches from main.
  - promotion-source accepts site/<slug> only when `git diff origin/main...HEAD` is non-empty
    and all under site/ (new step: tests red first, shown refusing a branch touching scripts/).
  - validate-dev.yml gets a `site_only` dispatch input: refuses a non-site diff, runs pnpm
    lint/typecheck/test and the PROD build + export checks (policy and consent guards fatal),
    posts validate-dev on that commit. Default off; with it off nothing changes.
  - back-merge NOT exempt for site/* (bounds drift to one change); ci unchanged.
  - New PR template site.md: pre-publication checklist 1-16 as boxes, Dev build: = the commit
    the dev preview's version.json names.
  - No ruleset change.
  Why: the head rule already lives in promotion-source, so no new required context; validate-dev
  keeps one poster and its meaning (every byte the CLI is built from is main's, already
  validated); it closes the dev-build gap before main, not after.
  Alternatives:
  (B) hotfix/site-<slug> naming on the existing hotfix path: works with no validate-dev change,
      but every weekly edit burns a CLI pre-release and runs the slow tier, browser suite and
      arm64 image (minutes, flake risk) for YAML; hotfix heads skip back-merge; and it still
      needs a site-only check on main.
  (C) as (A) but a separate required check `site-only` in promotion-guard.yml: a clearer red,
      but needs protect-main's required list changed (I'd write the exact JSON for you to read
      and apply).

Q2. How the guard reaches main (not in the spec). Recommendation: after this task merges into
  dev, the operator opens ONE hotfix, hotfix/install-site-lane, from main, carrying only
  check_promotion_source.py, promotion-guard.yml, the site template and their tests (cherry-
  picked), validated like any hotfix; then ac3's first use goes through the lane itself.
  Alternatives: fold dev's site/ into that same hotfix (one cycle, but it is the content hotfix
  the coach declined); or wait for the next promotion (the delay the task exists to end).
  Either way ac3 now includes that install step; the spec should say so. It also needs
  .github/PULL_REQUEST_TEMPLATE in constraints.packages (only .github/workflows and
  .github/rulesets are listed).

Q3. Visual QA on the lane. It needs a browser download and is not in CI. Recommendation: the
  site template asks for a green `pnpm --dir site qa` run only when the change touches
  site/src, site/public or site/package.json; a content-only change (site/content) does not.

Q4. The laptop. The guide's steps need gh, git, uv, pnpm, the AWS SSO profiles and terraform
  init'd prod-deploy and dev-preview worktrees. Is the laptop Charlie travels with from
  2026-11-01 the Mac that holds the worktrees today? If not, I add a one-time "set up the
  laptop" section to the guide (clone, gh auth login, the SSO profiles, the two worktrees).

FYI, proceeding unless told otherwise:
- First use: site/sync-from-dev-<date> from main, `git restore --source=origin/dev --staged
  --worktree -- site`, through the lane, after Charlie's word. Blocks written, not run.
- The guide replaces "Publish a change" path 2 for site edits with the lane, keeps the hotfix
  path for non-site emergencies and the takedown flow pointing at the lane.

Reply with: Q1 A/B/C, Q2 install-hotfix / fold / wait, Q3 yes/no, Q4 same Mac / other laptop,
and any change to the FYIs.
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `site-lane` | DONE in the session; ac3 open for the operator | Counts (ac1), the ruling, then the guard, the validate-dev site path, the template and the documents (ac2). The node's own command passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — counts first: what main's protection and the hotfix path require today, and a proposed lane, sent to the PM before building | **PASS** | The counts above, committed at the checkpoint (`b45e950`) before any code; the PM ruled on 2026-10-28 |
| ac2 — a pull request into main changing anything outside `site/` is refused by a check, shown failing first | **PASS** (locally; on GitHub once the install hotfix is on `main`, which is ac3) | **Red first:** with a refuse-nothing skeleton of `check_site_only`, `.venv/bin/python -m pytest tests/scripts/test_check_promotion_source.py -p no:randomly -n 0 --tb=line` → `37 failed, 129 passed`: 34 `AssertionError`, among them `test_git_a_branch_touching_scripts_is_refused`, `test_git_a_branch_touching_site_package_json_is_refused` and `test_git_a_branch_with_an_empty_diff_is_refused` (`assert 0 == 1`), and 3 `FileNotFoundError` for the `site.md` template not yet written. **Green:** `166 passed`. **The workflow's own step**, run with bash against real branches (`tests/scripts/test_promotion_guard_workflow.py`): `touches-scripts`, `touches-site-package-json` and `empty-diff` exit 1 with `FAILED:` naming the file or "changes nothing"; a results change exits 0; a branch that merged `dev` exits 1 naming `packages.py`. **Mutants:** 10 of 10 caught in `check_promotion_source.py` (empty allowed, outside allowed, dependency files allowed, dependency files only at the top level, two dots for three, renames on, `site` prefix without the slash, any `site/...` head, the CLI skipping site heads, no shallow check), each by 2 to 13 tests; script restored and re-run green |
| ac2 — a site-only one passes the site's checks | **PASS** (locally) | The `site` job's commands on this tree, which is `dev`'s `site/`, the first use's content: `pnpm --dir site lint && … typecheck && … test` → `26 passed (26)` files, `921 passed` tests; `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh` → exit 0, `12 passed (12)` files, `109 passed` tests, 13.5 s. **The gap it closes, planted:** `The [[TBD]] results summary.` appended to `site/content/pages/results.md` → the dev build CI runs (`SITE_ENV=dev node site/scripts/build-export.mjs`) exit 0 with `Publishing policy problems, which will fail a prod build:`; the site job's prod export checks exit 1, `Error [PublishingPolicyError]: Content breaks docs/policies/website-publishing.md`; file restored. Driver and workflow: `site-resolve` refuses an empty, outside-`site/`, `package.json` or lockfile diff **posting nothing** and posts `pending` only after accepting; `site-conclude` posts success only for `site=success` on the requested commit (`tests/scripts/test_validate_dev.py`, `100 passed`; workflow shape `tests/scripts/test_validate_dev_workflow.py`, with the pre-release jobs gated on `inputs.site_only != true`) |
| ac2 — the back-merge carries it to dev | **PASS** (mechanism unchanged and tested); live in ac3 | `back-merge.yml` is untouched: a site merge leaves the branch's non-merge commits on `main`, which `check_promotion_source.py back-merge` finds as it finds a hotfix's (`tests/scripts/test_back_merge_workflow.py` and the back-merge tests pass). `site/*` heads are held to the check (`test_which_heads_the_back_merge_check_applies_to[site/results]` → applies) |
| ac2 — documented in the coach's editing guide with every command | **PASS** | [Publish a change](../guides/coach-website-editing.md#publish-a-change): ten steps, every block with where, what success looks like, and what stops; conflicts; bringing dev's site to main; installing the lane. All 22 new blocks parse under `zsh -n` and `bash -n`; `check_command_blocks.py --base origin/dev` → `OK: no # comments in 552 shell code blocks`; `check_links.py` → `OK: 2805 relative links and anchors` |
| ac3 — the first use: dev's `site/` reaches main and prod through the lane, after Charlie's word, results page live (operator) | **NOT RUN** | It needs this branch merged into `dev`, the install hotfix (from Thursday 2026-10-29, after the image deploy, never on a Wednesday) and Charlie's word. Blocks under Operator follow-ups. Rehearsed what can be run here: the install's file-list block, as written, today → `STOP: it is Wednesday, the cloud run's day.`; with that test removed, in a scratch worktree of `origin/main` holding the five files → `OK: only the lane's five guard files differ from main.`; `main`'s copies equal this task's starting copies of the five (`git diff --quiet origin/main 1359440 -- <files>` → identical); the five files' tests on `main`'s tree → `192 passed` |
| Node: `uv run pytest tests/scripts -k workflow` | **PASS** | `.venv/bin/python -m pytest tests/scripts -k workflow -q` → `147 passed in 29.84s` |

## Checks run before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `80 of 553 test files (14.5%) chosen in 10.8 s from 14 changed files` |
| that list under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not slow and not live"` | stopped by the alarm at 1:55 (exit 142) with about 60% run and **no failure** in what ran, at load 13 to 17. Past two minutes, so the rest is the pull request's `ci` (agreement 10) |
| the changed test directories and the always-run list from that selection (41 files: `tests/scripts`, `tests/architecture`, `tests/specs`, `tests/docs`, `packages/debate_cli/tests`) | `1884 passed in 84.21s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1551 files already formatted` / `All checks passed!` |
| `pyright` | no package changed; `[tool.pyright] include` is `packages/` only, so CI's `pyright` does not read `scripts/` or `tests/`. Given the changed files directly it reports only the four `sys.path` imports (`check_promotion_source`, `validate_dev`) that the existing test files use the same way |
| `uv run --frozen lint-imports` / `check_thin_handlers.py` | `Contracts: 18 kept, 0 broken.` / `OK: 67 CLI command and API route handlers within 25 statements` |
| `scripts/actionlint.sh` | clean (`actionlint 1.7.12 … with shellcheck 0.11.0`, no findings) |
| `uv run scripts/validate_specs.py` | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |
| `docs_index.py --check-descriptions` | `All 56 indexed documents under docs/ have a description` |

## Files changed

* `scripts/check_promotion_source.py`: `site/<slug>` heads, and the `site-only` subcommand (non-empty,
  under `site/`, no dependency manifest or lockfile; `main...head` with renames split).
* `.github/workflows/promotion-guard.yml`: `promotion-source` checks out full history, fetches
  `main`, and runs the site-only step on the head commit. Still `contents: read`, no secret.
* `.github/workflows/validate-dev.yml`, `scripts/validate_dev.py`: the `site_only` dispatch input and
  the `site-resolve`, `site` and `site-conclude` jobs; `site-resolve` and `site-conclude`
  subcommands. With the input off, the pre-release path is unchanged.
* `.github/PULL_REQUEST_TEMPLATE/site.md`: the site template (checklist items 1 to 16, conditional
  visual QA, `Dev build:` from the preview's `version.json`).
* `tests/scripts/test_check_promotion_source.py`, `test_validate_dev.py`,
  `test_validate_dev_workflow.py`, new `test_promotion_guard_workflow.py`.
* `docs/guides/coach-website-editing.md`: Publish a change is the lane; takedowns go through it;
  four new rows under When something goes wrong.
* `docs/process/branching-and-environments.md`: the `site/<slug>` branch, the validate-dev site
  path, the guards table, and a new section, The site lane.
* `docs/runbooks/team-website.md`: a pointer to the lane above The order, every time.

## Deviations from the spec

* **The install hotfix carries five files, not validate-dev's `site_only` input.** The ruling
  listed `validate-dev.yml`'s input among the cherry-picked files. `validate-dev.yml`,
  `validate_dev.py`, `test_validate_dev.py` and `test_validate_dev_workflow.py` differ between
  `main` and `dev` outside this change (127/152/266/424 lines: the image job, the issue step, the
  slow tier's setup; the workflow test file does not exist on `main`), so taking them would carry
  other tasks' changes to `main`, and a cherry-pick of only this change does not apply to
  `main`'s older files. The lane never runs `main`'s copy: the coach dispatches
  `validate-dev.yml --ref dev`, which runs `dev`'s workflow and driver, and a promotion brings
  them to `main` in due course. The hotfix carries the five files that **are** byte-identical on
  both (`check_promotion_source.py`, `promotion-guard.yml`, `site.md` and the two test files), and
  the first block refuses if that stops being true. If the PM still wants the input on `main`
  before a promotion, that is a hand port by a session, not a cherry-pick.
* **The phase stays InProgress.** The ruling said to set Succeeded, but ac3 is an operator
  criterion that cannot run before this branch merges, and the task's standing instruction is to
  leave the phase InProgress with that criterion NOT RUN (for a `--partial` merge).
* **Scope, per the ruling:** `.github/PULL_REQUEST_TEMPLATE/site.md` is outside the spec's
  `constraints.packages` as written; the ruling adds `.github/PULL_REQUEST_TEMPLATE` and
  `docs/process/rulesets` (and drops `.github/rulesets`) in the PM's next batch. The spec was not
  edited. No ruleset file changed.
* **Red first, where it was and was not.** The refusal rule and the three named branches were red
  first (ac2). `test_promotion_guard_workflow.py` was written after the workflow step, so it was
  never seen red; the driver and validate-dev workflow tests were red (`20 failed, 115 passed`)
  before their code existed, by missing functions and jobs rather than by assertions.

## Decisions and assumptions

* **Dependency files** are matched by file name anywhere under `site/` (the visual QA tools keep
  their own `package.json` and lockfile): `package.json`, `pnpm-lock.yaml`,
  `pnpm-workspace.yaml`, `.pnpmfile.cjs`, `.npmrc`, `package-lock.json`, `npm-shrinkwrap.json`,
  `yarn.lock`, `.yarnrc`, `.yarnrc.yml`, `bun.lock`, `bun.lockb`, and the Node version pins
  `.nvmrc` and `.node-version`.
* **`site-resolve` posts nothing on a refusal**, so a mistyped SHA (dev's head) cannot turn that
  commit's `validate-dev` red; `site-conclude` runs only after `site-resolve` accepted. A site run
  opens no `validate-dev` issue.
* **The lane works in the `dev-preview` worktree.** It is already initialised for the dev root's
  Terraform outputs, the runbook's rollback already moves it to other commits, and step 10 puts
  it back on `origin/dev`. No third worktree, as Q4 ruled.
* **The guide's install blocks** find the task's squash commit by its subject
  (`^v1-e37-t09-site-changes-publish-without-a-release`), as `scripts/task pr` titles it.
* **Wednesday** is `date +%u` = 3 on the Mac's clock (Chicago, the cloud run's zone).

## Operator follow-ups

**1. After this merges into `dev`, from Thursday 2026-10-29 once the image deploy has finished,
never on a Wednesday: install the lane's guard on `main`.** Where: the `dev-preview` worktree
(each block `cd`s or runs there). These are the guide's
[Installing the lane, once](../guides/coach-website-editing.md#installing-the-lane-once) blocks,
copied. Expected runtime: about 30 minutes, most of it the hotfix's `ci` and `validate-dev`.

The first block builds the hotfix branch in the `dev-preview` worktree from `main`, takes the five
files from the task's commit on `dev`, and refuses if `main`'s copies were not the ones the task
started from (then the hotfix would carry someone else's change too).

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; elif [ "$(date +%Y%m%d)" -lt 20261029 ]; then echo "STOP: not before Thursday 2026-10-29's image deploy."; elif [ -n "$(git -C ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview status --porcelain)" ]; then echo "STOP: dev-preview has uncommitted changes."; else cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview && git fetch origin && LANE_COMMIT="$(git log origin/dev -1 --format=%H --grep='^v1-e37-t09-site-changes-publish-without-a-release')" && echo "lane commit: ${LANE_COMMIT}" && LANE_FILES=(scripts/check_promotion_source.py .github/workflows/promotion-guard.yml .github/PULL_REQUEST_TEMPLATE/site.md tests/scripts/test_check_promotion_source.py tests/scripts/test_promotion_guard_workflow.py) && git diff --quiet origin/main "${LANE_COMMIT}^" -- "${LANE_FILES[@]}" && git switch -c hotfix/install-site-lane origin/main && git checkout "${LANE_COMMIT}" -- "${LANE_FILES[@]}" && git commit -m "Hotfix: install the site lane's guard on main (v1-e37-t09)"; fi
```

Success looks like `lane commit:` and a 40-character commit, then `Switched to a new branch
'hotfix/install-site-lane'` and a commit of 5 files. A `STOP:` line, an empty `lane commit:`, or
the block ending without a commit means stop: say what it printed.

The second block checks the branch carries those five files and nothing else, against `main`.

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; elif [ "$(git diff --name-only origin/main...HEAD | LC_ALL=C sort | tr '\n' ' ')" = ".github/PULL_REQUEST_TEMPLATE/site.md .github/workflows/promotion-guard.yml scripts/check_promotion_source.py tests/scripts/test_check_promotion_source.py tests/scripts/test_promotion_guard_workflow.py " ]; then echo "OK: only the lane's five guard files differ from main."; else echo "STOP: the branch differs from main in:"; git diff --name-only origin/main...HEAD; fi
```

Success looks like `OK: only the lane's five guard files differ from main.` Anything else: stop.

The third block pushes the branch and dispatches the hotfix pre-release, which builds it and asks
`validate-dev` to validate it, like any hotfix.

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else git push -u origin hotfix/install-site-lane && gh workflow run dev-prerelease.yml --ref hotfix/install-site-lane; fi
```

The fourth block asks for the status on the hotfix head; run it until it says `success`, then
note the pre-release it names for the `Dev build:` line. It opens the pull request with the hotfix
template; write "The site lane's guard is not on main" as the incident.

```bash
gh api "repos/charlesclark2/debate-intelligence/commits/$(git rev-parse HEAD)/status" --jq '.statuses[] | select(.context == "validate-dev") | .state + "  " + .description'
```

```bash
open "https://github.com/charlesclark2/debate-intelligence/compare/main...hotfix/install-site-lane?template=hotfix.md&expand=1"
```

The fifth block merges it once every check is green and Charlie has approved it, and the sixth,
after the back-merge pull request has opened, merges that into `dev` (its number from
`gh pr list --base dev --head main --state open`). `dev` already holds these files, so it merges
without conflicts.

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else gh pr checks hotfix/install-site-lane --watch && gh pr merge hotfix/install-site-lane --merge; fi
```

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else gh pr list --base dev --head main --state open; fi
```

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else gh pr checks <number> --watch && gh pr merge <number> --merge && cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview && git switch --detach origin/dev && git branch -D hotfix/install-site-lane; fi
```

**2. The first use (ac3), only with Charlie's word, after follow-up 1.** Dev's `site/` to `main`
through the lane: the season-results page and the home page's results band. Where: the
`dev-preview` worktree, then `prod-deploy`. Expected runtime about an hour, most of it waiting
for checks. Every block runs in one terminal window.

The first block starts the branch, named for today, and makes its `site/` exactly `dev`'s.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
SITE_BRANCH="site/sync-from-dev-$(date +%Y-%m-%d)"
if [ -n "$(git status --porcelain)" ]; then echo "STOP: dev-preview has uncommitted changes:"; git status --short; else git fetch origin && git switch -c "${SITE_BRANCH}" origin/main && git restore --source=origin/dev --staged --worktree -- site && pnpm --dir site install --frozen-lockfile; fi
```

Success looks like `Switched to a new branch 'site/sync-from-dev-…'` and pnpm ending `Done`.

The second block runs the site's checks and the prod build, commits, and asks the lane's question.

```bash
pnpm --dir site lint && pnpm --dir site typecheck && pnpm --dir site test
SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh
git add site
git commit -m "Bring dev's site to main: the season-results page and the home page's results band"
uv run scripts/check_promotion_source.py site-only --head "${SITE_BRANCH}"
```

Success looks like the source tests and the export checks passing (on 2026-10-28, 921 and 109
tests) and `OK: Every one of the N changed path(s) is under site/ and none is a dependency file.`
with N about 38. `FAILED` naming `site/package.json` or `site/pnpm-lock.yaml` means `dev`'s site
dependencies moved since 2026-10-28: stop, and the first use waits for a promotion.

Then steps 4 to 10 of the guide's [Publish a change](../guides/coach-website-editing.md#publish-a-change),
unchanged: preview on dev and read `/results/` on a phone, push and dispatch `validate-dev` with
`site_only=true`, open the pull request with the site template (checklist item 16: Charlie has
seen every named result), merge, deploy prod, back-merge into `dev` the same day, put
`dev-preview` back. The last block confirms the results page is live on prod:

```bash
curl -sS -o /dev/null -w '%{http_code} %{url_effective}\n' https://wfbdebate.com/results/
curl -sS https://wfbdebate.com/version.json
```

Success looks like `200 https://wfbdebate.com/results/`, and `version.json`'s `commit` equal to
the merge commit the prod deploy printed. Paste both back to the PM with the merge and back-merge
pull request numbers.

## Follow-up work

* **The hotfix path has the same dev-build gap.** A `hotfix/*` change to `site/` is validated by
  the CLI pre-release, and its first prod build is still the deploy after the merge. Running the
  site job for any pull request into `main` that touches `site/` would close it; `ci.yml` is shared
  test ground, so that is a task of its own (E36 or v1-e01).
* **`scripts/site_smoke.py` is outside `site/`**, so a smoke check a future site task adds (for
  example `v1-e37-t08`'s results band) reaches `main` only by promotion or hotfix. The lane's prod
  smoke runs `main`'s copy.
* **Spec amendments, for the PM's batch:** ac3 includes the install step; `constraints.packages`
  adds `.github/PULL_REQUEST_TEMPLATE` and `docs/process/rulesets` and drops `.github/rulesets`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-28

**Notes:**

The site lane is built as ruled, and it closes a gap nobody had named: a site change reached `main`
having been built only for dev.
1. **ac1 passes.** The counts were committed before any code (`b45e950`), and they found three facts
   the spec lacked: the guard must already be on `main`, the `site` job builds for dev, and the
   ruleset export's real path.
2. **ac2 passes, locally.**
   * The refusal rule was red first (37 failed with a refuse-nothing skeleton). The three named
     branches (touching `scripts/`, touching `site/package.json`, an empty diff) are refused by the
     script and by the workflow's own step run against real branches.
   * 10 of 10 mutants are caught, two-dot for three-dot and the slashless `site` prefix among them.
   * The planted `[[TBD]]` passes the dev build CI runs today and fails the lane's prod build: the
     gap, shown closed.
   * `site-resolve` posts nothing on a refusal, so a mistyped SHA can't turn another commit red.
   * The guide carries every command, and all 22 blocks parse under zsh and bash.
3. **Deviation 1, five files in the install hotfix: accepted.** The lane dispatches validate-dev from
   `dev` (`--ref dev`), so `main` never runs its own copy for a site head. A cherry-pick of
   `validate-dev.yml` would carry other tasks' changes to `main`. The first block refuses if the five
   files stop being byte-identical. No hand port.
4. **Deviation 2, the phase stays InProgress: accepted,** and my ruling's "Succeeded" is withdrawn.
   ac3 is the operator's after the merge, so this merges `--partial`, like the other operator-run
   criteria.
5. **Deviation 3 (scope) and 4 (red first): accepted.** The package amendments go into the PM's next
   batch. `test_promotion_guard_workflow.py` was not seen red, but the rule it exercises was, through
   the script's own tests, and the workflow test runs that rule against real branches.
6. **Decisions accepted:**
   * dependency files matched by name anywhere under `site/`, the Node version pins included;
   * the lane works in `dev-preview` and puts it back on `origin/dev`;
   * the install blocks find the task's commit by its subject;
   * Wednesday is `date +%u` = 3.

   The lane's ordinary steps rightly don't refuse Wednesdays: a site deploy doesn't touch the cloud
   run.
7. **One cost to know about:** a `site/**/*.md` change trips `ci`'s python filter, so a pull request
   into `main` that edits a page runs the whole test selection. A `results.yaml` or
   `tournaments.yaml` edit does not. The PM's next batch files a task joining your follow-up 1: run the
   site job's prod build for any pull request into `main` touching `site/` (the hotfix path's gap),
   and keep `site/` out of the python filter.
8. **One risk for the install hotfix:** it is validated by `main`'s own slow tier, like the
   2026-10-22 hotfix, which passed. If `main`'s slow tier fails on something this change didn't
   touch, stop and bring the run to the PM. Don't retry it blindly.
9. **Follow-up 2 (`site_smoke.py` outside `site/`):** noted on `v1-e37-t08`. No task.
10. **The affected set** (80 files) ran past two minutes with no failure in its first 60%. The rest is
    the PR's `ci`. The changed test directories, the always-run list, actionlint, ruff, lint-imports,
    the specs and the docs checks pass.
11. **Merge timing and order:** after Thursday 2026-10-29's tag has a green validate-dev run, and
    second in the held order, straight after e31-t31. It changes `validate-dev.yml`, so it must not
    ride the tag, but the coach travels from 2026-11-01, and the install hotfix (operator follow-up
    1) should be on `main` before then. The first use (follow-up 2) waits for the coach's word.

## Operator records (recorded by the PM, 2026-10-30)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3, the install hotfix | NOT RUN | PASS | 2026-10-29: `hotfix/install-site-lane` from `main`, the five guard files only (`6e233dc`), validate-dev green on `v1.0.1-dev.3`, merged as #594 with every check green; back-merge #596 into `dev` |
| ac3, the first use | NOT RUN | PASS | 2026-10-30, with the coach's word: #604 (dev's `site/`, 38 files, no dependency file), validate-dev `site only … green`, prod `2525841`, 38 smoke checks, back-merge #605. A second use the same night, #616 (the coach's Ronald Reagan edit and `v1-e37-t10`'s tests, 15 files), ran only the site checks, deployed as `5e51217`, back-merge #618 |

Every criterion passes, so the Goal is `Succeeded`.

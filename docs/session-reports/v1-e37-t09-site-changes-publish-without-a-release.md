# Session report: v1-e37-t09-site-changes-publish-without-a-release

| | |
|---|---|
| Task | `v1-e37-t09-site-changes-publish-without-a-release` — Website changes reach the public site in a day, without waiting for a release |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t09-site-changes-publish-without-a-release.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t09-site-changes-publish-without-a-release.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t09-site-changes-publish-without-a-release` |
| Session status | BLOCKED: waiting for the PM's ruling on the proposed lane (counts checkpoint) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Counts checkpoint, as the PM's context for this task asks: what `main` requires today, what the
hotfix path and the back-merge do, and which checks a `site/`-only change needs, all read from the
repository without changing anything. Then one proposed lane, with a relay prompt for the PM at
the end of this section. Nothing is built yet.

The fact that shapes the proposal: **the checks on a pull request into `main` run from the pull
request merged with `main`**, so a `site/` branch can only be accepted by a guard that is already
on `main`. Today `promotion-source` on `main` refuses every head but `dev` and `hotfix/<slug>`, and
`validate-dev` is posted only for a commit with a CLI pre-release, which only `dev` and `hotfix/*`
can get. The lane's guard therefore has to reach `main` once, by a hotfix or a promotion, before
its first use. That is a step the spec does not mention (Q2 below).

### The counts

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

### Relay prompt for the PM

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
| `site-lane` | IN PROGRESS | Counts done (ac1); waiting for the PM's ruling before building |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — counts first, and a proposed lane sent to the PM before building | PASS (pending the PM's reading) | Summary above, from `docs/process/rulesets/*.json`, `.github/workflows/{ci,promotion-guard,back-merge,dev-prerelease,validate-dev}.yml`, `scripts/check_promotion_source.py`, `scripts/site_deploy.sh`, `site/scripts/*.sh`, `site/src/lib/{publishing-policy,media-consent}.ts`, the hotfix template, the branching doc, the coach's guide and the runbook; `git diff --stat origin/main origin/dev -- site/` → `38 files changed, 2687 insertions(+), 74 deletions(-)`; `git rev-list --no-merges --count origin/dev..origin/main` → `0` |
| ac2 — the lane as ruled, the outside-`site/` refusal shown failing first, documented in the guide | NOT RUN | waiting for the ruling |
| ac3 — the first use, dev's `site/` to main and prod (operator) | NOT RUN | waiting for the ruling, then Charlie's word |
| Node: `uv run pytest tests/scripts -k workflow` | NOT RUN | waiting for the build |

## Files changed

* `docs/session-reports/v1-e37-t09-site-changes-publish-without-a-release.md`: the counts and the
  relay prompt.

## Deviations from the spec

* **Not yet ruled.** The lane's guard must reach `main` before its first use (Q2), which ac3 does
  not mention, and the site template needs `.github/PULL_REQUEST_TEMPLATE` added to
  `constraints.packages`. The ruleset export lives at `docs/process/rulesets/`, not
  `.github/rulesets`.

## Decisions and assumptions

* The counts read local `origin/main` and `origin/dev` refs without fetching, as the PM's context
  allows no network call but `scripts/task sync`. Timings come from the repository's documents,
  not from GitHub run history.

## Operator follow-ups

None yet.

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

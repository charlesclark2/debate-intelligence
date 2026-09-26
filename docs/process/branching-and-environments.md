# Branching, environments and promotion

Decided 2026-09-17 ([ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md)). This is the authoritative workflow; task
specs and CI implement it.

## The rule

**`main` is production. `dev` is the development environment. Nothing reaches `main` that has
not been deployed to and validated in dev.**

```
task/<task-name> ──PR──▶ dev ──(deploy to dev, validate)──▶ promotion PR dev → main ──▶ prod
                          ▲                                                      │
hotfix/<slug> ──PR──▶ main ─────────────── back-merge main → dev ◀───────────────┘
```

## Branches

| Branch | Purpose | Who writes to it |
|---|---|---|
| `main` | Production. Every commit on `main` is releasable and is what the team uses. | Merge of a promotion PR from `dev`, or a `hotfix/*` PR. Never a direct push. |
| `dev` | Integration + development environment. GitHub **default branch**, so PRs target it by default. | Merges of `task/*` PRs. Never a direct push. |
| `task/<task-name>` | One PlanSpec task (e.g. `task/v1-e04-t02-http-fetcher`). Branched from `dev`. | You / an agent session. |
| `hotfix/<slug>` | Urgent production fix. Branched from `main`, **deployed to dev and validated like any other change** (manual `workflow_dispatch` of the dev deploy/pre-release for the hotfix head), PR to `main`, then back-merged to `dev` the same day. | Rare; same gates as a promotion — no exception to "validated in dev". |

Rules: squash-merge `task/*` → `dev`; **merge commit** (not squash) for `dev` → `main` so the
two branches share history and never drift; never rebase or force-push `dev` or `main`.

## Environments

There are exactly two: **dev** and **prod**. (The architecture proposal's `stage` is dropped;
dev is the pre-production validation environment.)

| | dev | prod |
|---|---|---|
| Fed by | every merge to `dev` | every merge to `main` (after approval) |
| **V1 (CLI, v1.0–v1.3)** | Pre-release build `vX.Y.Z-dev.N` published as a GitHub pre-release; installed with `uv tool install` from the pre-release tag; `DEBATE_ENV=dev` uses a separate data dir and dev provider/model config | Stable tagged release `vX.Y.Z` the team installs; `DEBATE_ENV=prod` |
| **V2+ (AWS)** | Separate AWS account/state (`infrastructure/envs/dev`), dev Cognito pool, dev domain | `infrastructure/envs/prod`, prod Cognito pool, prod domain |
| Data | Cloud dev (V2+): synthetic/test accounts and scrubbed fixtures only — **never real student data**. V1 dev channel: runs on the tester's own machine against public sources; nothing leaves it | Real users (students may be minors — §14) |
| Model spend | Low daily budget; replay router where possible | Production quotas (E19) |
| Deploy | Automatic on merge to `dev` | Automatic on merge to `main`, **after** the `production` environment approval |

## What "validated in dev" means

A promotion PR (`dev` → `main`) can merge only when **all** of these hold:

1. **CI green** on the `dev` head commit (lint, types, tests, import boundaries, spec validation).
2. **Deployed to dev**: the pre-release build (V1) or the dev AWS deploy (V2+) for that exact commit
   succeeded.
3. **`validate-dev` passed**: the automated smoke suite ran against the dev environment for that
   commit and posted a green `validate-dev` status. The suite grows with every release — any task
   that changes a user-facing surface adds or updates its smoke checks (`tests/smoke/`, and
   `tests/smoke/cloud/` from V2), and says so in its spec.
4. **Evaluation gates** (from v1.3): prompt/model changes pass their promotion evals.
5. **Your approval**: Charlie signs off the promotion checklist on the PR, and (V2+) approves the
   `production` GitHub Environment deployment.

The promotion PR uses the [promotion template](../../.github/PULL_REQUEST_TEMPLATE/promotion.md):
the release/tasks included, the dev build or deploy id, the `validate-dev` run link, evaluation
results, a manual check note for anything automation cannot cover yet, and a rollback note. A
hotfix PR uses the [hotfix template](../../.github/PULL_REQUEST_TEMPLATE/hotfix.md): the incident,
the dev build of the hotfix head, its `validate-dev` run link and the back-merge reminder. Open
either by adding `?template=promotion.md` or `?template=hotfix.md` to the compare URL. Task PRs into
`dev` use the [default template](../../.github/pull_request_template.md), which `scripts/task pr`
fills in for you.

## Guards on pull requests into `main`

[`promotion-guard.yml`](../../.github/workflows/promotion-guard.yml) posts two checks on every pull
request into `main`, both required by **protect-main**. Both run
[`scripts/check_promotion_source.py`](../../scripts/check_promotion_source.py).

| Check | Fails when |
|---|---|
| `promotion-source` | The head is not `dev` or `hotfix/<slug>` from this repository (a fork can name its branch `dev` too), or the description leaves the `Dev build:` or `validate-dev run:` line blank. Editing the description re-runs it. |
| `back-merge` | `main` holds a non-merge commit that `dev` lacks: a hotfix that was never back-merged. A `hotfix/*` head always passes it, so a second urgent fix is never blocked by the first one's back-merge. |

Before `v1-e01-t09` (dev pre-releases) and `v1-e01-t10` (`validate-dev`) have merged there is no
build or run to link. Write that on the line, with what was checked instead: the check refuses a
blank line, not an honest one.

**After a hotfix merges**, [`back-merge.yml`](../../.github/workflows/back-merge.yml) opens a
"Back-merge main → dev" pull request whose head is `main` itself. Merge it into `dev` the same day
with **Create a merge commit**: a squash leaves `main`'s commits unreachable from `dev`, and
`back-merge` stays red on every promotion until they are. A promotion puts only a merge commit on
`main`, which the check ignores, so promotions never open a back-merge PR.

Guard workflows run on `pull_request` with `contents: read` and no secrets, because this repository
is public and a fork's pull request runs its own code. Only `back-merge.yml`, which runs on push to
`main`, holds a write permission (`pull-requests: write`, on its one job).

## GitHub settings

Set now:

* Default branch → `dev`.
* Ruleset **protect-main** (target: pattern `main`, empty bypass list): restrict deletions, block
  force pushes, require a pull request with **0** required approvals (GitHub does not let you
  approve your own PR; the manual approval is the promotion checklist and, from V2, the
  `production` environment approval), dismiss stale approvals, require conversation resolution,
  allowed merge method **Merge** only. No linear-history rule (promotions are merge commits).
  Required status checks `ci`, `promotion-source` and `back-merge`, **not** "require branches to be
  up to date": every promotion leaves a merge commit on `main` that `dev` never receives, so that
  setting would report every later promotion out of date. `back-merge` checks what it was meant to.
* Ruleset **protect-dev** (target: pattern `dev`, empty bypass list): restrict deletions, block
  force pushes, require a pull request with 0 approvals and conversation resolution, allowed merge
  methods **Squash** (task PRs) and **Merge** (hotfix back-merges). No linear-history rule.
  Required status check `ci`.
* Settings → General → Pull Requests: enable **Automatically delete head branches**.

Added as the tasks land:

* `v1-e01-t04-ci-pipeline` → require status check `ci` on `dev` and `main`.
* `v1-e01-t08-branch-promotion-workflow` → require `promotion-source` and `back-merge` on `main`
  (see [Guards on pull requests into `main`](#guards-on-pull-requests-into-main)), the task,
  promotion and hotfix PR templates, and Settings → Actions → General → **Allow GitHub Actions to
  create and approve pull requests**, which `back-merge.yml` needs to open its pull request.
* `v1-e01-t10-validate-dev-gate` → require `validate-dev` on `main`.
* `v2-e12-t07-promotion-pipeline` → `development` / `production` GitHub Environments with
  branch-scoped deploy rules and Charlie as required reviewer on `production`.

## Releases

Release tags (`v1.1.0` …) are cut **from `main`** after the promotion that completes a release's
epics. Each `dev` merge produces the next pre-release (`v1.1.0-dev.7`). The release review Gate
in `plan_specs/releases/<version>.yaml` is approved on the promotion PR.

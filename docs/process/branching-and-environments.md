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

The promotion PR uses the promotion template: the release/tasks included, the dev build or
deploy id, the `validate-dev` run link, and a manual check note for anything automation cannot
cover yet.

## GitHub settings

Set now:

* Default branch → `dev`.
* Ruleset **protect-main** (target: pattern `main`, empty bypass list): restrict deletions, block
  force pushes, require a pull request with **0** required approvals (GitHub does not let you
  approve your own PR; the manual approval is the promotion checklist and, from V2, the
  `production` environment approval), dismiss stale approvals, require conversation resolution,
  allowed merge method **Merge** only. No linear-history rule (promotions are merge commits).
* Ruleset **protect-dev** (target: pattern `dev`, empty bypass list): restrict deletions, block
  force pushes, require a pull request with 0 approvals and conversation resolution, allowed merge
  methods **Squash** (task PRs) and **Merge** (hotfix back-merges). No linear-history rule.
* Settings → General → Pull Requests: enable **Automatically delete head branches**.

Added as the tasks land:

* `v1-e01-t04-ci-pipeline` → require status check `ci` on `dev` and `main`.
* `v1-e01-t08-branch-promotion-workflow` → `promotion-source` check (fails any PR to `main`
  whose head is not `dev` or `hotfix/*`) and the promotion PR template.
* `v1-e01-t10-validate-dev-gate` → require `validate-dev` on `main`.
* `v2-e12-t07-promotion-pipeline` → `development` / `production` GitHub Environments with
  branch-scoped deploy rules and Charlie as required reviewer on `production`.

## Releases

Release tags (`v1.1.0` …) are cut **from `main`** after the promotion that completes a release's
epics. Each `dev` merge produces the next pre-release (`v1.1.0-dev.7`). The release review Gate
in `plan_specs/releases/<version>.yaml` is approved on the promotion PR.

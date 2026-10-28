<!-- docs-index: `main` = prod, `dev` = development; promotion rules -->
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
site/<slug>   ──PR──▶ main ─────────────── back-merge main → dev   (website content only)
```

## Branches

| Branch | Purpose | Who writes to it |
|---|---|---|
| `main` | Production. Every commit on `main` is releasable and is what the team uses. | Merge of a promotion PR from `dev`, or a `hotfix/*` PR. Never a direct push. |
| `dev` | Integration + development environment. GitHub **default branch**, so PRs target it by default. | Merges of `task/*` PRs. Never a direct push. |
| `task/<task-name>` | One PlanSpec task (e.g. `task/v1-e04-t02-http-fetcher`). Branched from `dev`. | You / an agent session. |
| `site/<slug>` | **The site lane** (`v1-e37-t09`): a change to the public website's content, pages or assets, branched from `main` and merged into `main` the same day, then back-merged to `dev`. `promotion-source` refuses it unless the branch's own changes are something, all under `site/`, and no dependency manifest or lockfile; `validate-dev` comes from the site's prod build ([below](#the-site-lane)). The coach's [editing guide](../guides/coach-website-editing.md#publish-a-change) has every command. | Charlie, from the Mac with the deploy worktrees. |
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
| Model spend | $2 a day and $50 a month; replay router where possible | $1.50 a day and $50 a month (E19 sets production quotas) |
| Deploy | Automatic on merge to `dev` | Automatic on merge to `main`, **after** the `production` environment approval |

## What "validated in dev" means

A promotion PR (`dev` → `main`) can merge only when **all** of these hold:

1. **CI green** on the `dev` head commit (lint, types, tests, import boundaries, spec validation).
2. **Deployed to dev**: the pre-release build (V1) or the dev AWS deploy (V2+) for that exact commit
   succeeded.
3. **`validate-dev` passed**: the automated smoke suite ran against the dev build of that exact
   commit and posted a green `validate-dev` commit status on it, which protect-main requires (see
   [validate-dev](#validate-dev-the-status-protect-main-requires)). The suite grows with every
   release — any task that changes a user-facing surface adds or updates its smoke checks
   (`tests/smoke/`, and `tests/smoke/cloud/` from V2), and says so in its spec;
   [tests/smoke/README.md](../../tests/smoke/README.md#adding-a-smoke-check) says how.
4. **Evaluation gates** (from v1.3): prompt/model changes pass their promotion evals.
5. **Your approval**: Charlie signs off the promotion checklist on the PR, and (V2+) approves the
   `production` GitHub Environment deployment.

The promotion PR uses the [promotion template](../../.github/PULL_REQUEST_TEMPLATE/promotion.md):
the release/tasks included, the dev build or deploy id, evaluation results, a manual check note for
anything automation cannot cover yet, and a rollback note. A hotfix PR uses the
[hotfix template](../../.github/PULL_REQUEST_TEMPLATE/hotfix.md): the incident, the dev build of
the hotfix head and the back-merge reminder. Neither asks for a link to the validate-dev run: the
required `validate-dev` status on the head commit links it, and is the one record of whether that
commit was validated. Open
either by adding `?template=promotion.md` or `?template=hotfix.md` to the compare URL. Task PRs into
`dev` use the [default template](../../.github/pull_request_template.md), which `scripts/task pr`
fills in for you.

## validate-dev: the status protect-main requires

`validate-dev` is a commit status, posted by
[`validate-dev.yml`](../../.github/workflows/validate-dev.yml) through
[`scripts/validate_dev.py`](../../scripts/validate_dev.py), and required by protect-main. It is
green on a commit only when all of these held for that exact commit:

1. A published dev pre-release has its tag at that commit.
2. That pre-release was installed with `scripts/install_channel.sh` into a scratch tool directory,
   so its checksums, its wheels' provenance and its completeness were checked.
3. The installed `debate-research --version --json`, with `DEBATE_ENV` unset, reported that commit,
   that tag, channel `dev` and environment `dev`.
4. The recorded smoke tier in `tests/smoke/` passed against **that installed binary**, offline,
   from a checkout of the same commit, with nothing skipped.
5. The offline slow tier, `pytest -m "slow and not live and not eval and not operator_data"`,
   passed from a checkout of the same commit, with nothing skipped. The parser evaluation is left
   out because its corpus never reaches a runner; it runs on Charlie's Mac before any promotion that
   changes the parser. A test marked `operator_data` is left out for the same reason: it needs data
   only Charlie's Mac holds, such as the tub's own search index.

Anything else posts `failure` (or `error`, if the run was cancelled) on the requested commit. The
status's link is the run, whose log shows the installed version and commit, and its description
names the pre-release.

**When it runs.** `dev-prerelease.yml` dispatches it after publishing each pre-release: from `dev`
for a merge to `dev`, and from the hotfix branch for a `hotfix/*` head, which is validated in
exactly the same way. A release created with the workflow token starts no workflow by itself, so
the dispatch is what triggers it. It also runs nightly against the head of `dev`, on
`release: prereleased` for a pre-release a person publishes, and on a manual dispatch with a commit
SHA. The opt-in live canary tier runs only when dispatched with `live: true` or with the repository
variable `VALIDATE_DEV_LIVE` set to `true`, and never calls OpenCaselist.

**For a `site/<slug>` commit**, the person publishing dispatches it from `dev` with
`site_only: true`. The pre-release jobs are skipped; `site-resolve` refuses the commit, posting no
status at all, unless its own changes since it left `main` are site content (the same rule as
`promotion-source`); the `site` job runs the site's lint, type check and tests, then its **prod**
build, where the publishing-policy and consent guards are fatal, and the export checks against it;
`site-conclude` posts the status. This is "validated in dev" for a change that leaves every byte
outside `site/` as `main`'s, which was validated when it got there. With the input off, which is
every other trigger, nothing about the status changes.

**Why a promotion whose `dev` moved is blocked.** The status belongs to a commit, and a promotion
pull request's required checks are read from its current head. When another merge lands on `dev`
while a promotion is open, the head becomes a commit with no `validate-dev` status yet, and the
merge button stays blocked until that commit's own pre-release has been built and validated.

**One record, not two.** Promotion and hotfix descriptions used to carry a `validate-dev run:`
line, which `promotion-source` refused while blank. With the status required, that line could only
repeat what the status already says, or say something different when `dev` moved after it was
written, so it was removed (v1-e01-t10). `Dev build:` stays as the human-readable name of what is
being promoted, and the status's description names the pre-release it installed, for comparison.

[tests/smoke/README.md](../../tests/smoke/README.md) describes the tiers, the markers and how a
task adds a smoke check.

## Guards on pull requests into `main`

[`promotion-guard.yml`](../../.github/workflows/promotion-guard.yml) posts two checks on every pull
request into `main`, both required by **protect-main**. Both run
[`scripts/check_promotion_source.py`](../../scripts/check_promotion_source.py).

| Check | Fails when |
|---|---|
| `promotion-source` | The head is not `dev`, `hotfix/<slug>` or `site/<slug>` from this repository (a fork can name its branch `dev` too), or the description leaves the `Dev build:` line blank. For a `site/<slug>` head, also when the branch's own changes since it left `main` are empty, reach outside `site/`, or touch a dependency manifest or lockfile under `site/` ([The site lane](#the-site-lane)). Editing the description re-runs it. |
| `back-merge` | `main` holds a non-merge commit that `dev` lacks: a hotfix or site change that was never back-merged. A `hotfix/*` head always passes it, so a second urgent fix is never blocked by the first one's back-merge. A `site/*` head does not: a site change waits for the previous one's back-merge, which keeps `dev` and `main` at most one change apart. |

### The site lane

The public site serves `main`, and a promotion carries all of `dev`, so before `v1-e37-t09` a
schedule or results change waited for the next CLI release or went out as a hotfix. The site lane
is a third way into `main`, for website content only, ruled by the PM on 2026-10-28:

* **What it may carry:** a non-empty change, every path under `site/`, and no dependency manifest
  or lockfile (`package.json`, `pnpm-lock.yaml`, `.npmrc` and the rest, anywhere under `site/`). A
  dependency change goes through a promotion. The rule is `check_promotion_source.py site-only`,
  measured from where the branch left `main` (`main...head`), with renames split so a file moved
  in from outside counts as outside.
* **What checks it:** `ci` as for any pull request into `main`; `promotion-source` with the rule
  above as a step of the same job, so protect-main's required list is unchanged; `back-merge`,
  not exempted; and `validate-dev` from the site's prod build ([above](#validate-dev-the-status-protect-main-requires)).
  The policy's pre-publication checklist is the [site template](../../.github/PULL_REQUEST_TEMPLATE/site.md)'s.
* **What it does not change:** deploys stay the operator's `scripts/site_deploy.sh` (no AWS
  credential in any workflow until `v2-e10-t03`), the consent guard runs in every build, and the
  back-merge into `dev` is the same day, as for a hotfix.
* **Its guard lives on `main`.** A pull request's checks run from its merge with `main`, so the
  lane works only once `check_promotion_source.py`, `promotion-guard.yml` and the site template are
  there. They reached `main` by one hotfix, `hotfix/install-site-lane`
  ([Installing the lane, once](../guides/coach-website-editing.md#installing-the-lane-once)).
  `validate-dev.yml`'s site path is dispatched from `dev` and runs `dev`'s copy.

**After a hotfix merges**, [`back-merge.yml`](../../.github/workflows/back-merge.yml) opens a
"Back-merge main → dev" pull request, labelled `back-merge`, whose head is `main` itself. The
merge's push opens it; if GitHub loses that push, the next scheduled or dispatched run of the same
workflow does, and a run that finds one already open names it and opens no second. Merge it
into `dev` the same day with **Create a merge commit**, never squash: a squash leaves `main`'s commits unreachable from `dev`, and
`back-merge` stays red on every promotion until they are. A promotion puts only a merge commit on
`main`, which the check ignores, so promotions never open a back-merge PR.

Guard workflows run on `pull_request` with `contents: read` and no secrets, because this repository
is public and a fork's pull request runs its own code. Only `back-merge.yml`, which runs on push to
`main`, on a schedule and on a manual dispatch, never on a pull request, holds write permissions,
each on the one job that needs it: `pull-requests: write` to open the back-merge pull request, and
`actions: write` to re-run the guards (below). Neither job holds `contents: write`. Both check out
only the workflow's own commit of `main` or `dev`, refuse to run from any other ref, and never run
pull-request code; the job holding `actions: write` checks out only its re-run script.

### When `main` moves, the guards re-run on every open pull request into it

Merging into `main` does not, by itself, re-run checks on pull requests already open against it.
GitHub has no "base branch moved" event, and "require branches to be up to date" is deliberately
off, because a promotion leaves a merge commit on `main` that `dev` never receives and the setting
would block every subsequent promotion. Left alone, a promotion opened before a hotfix would keep
the green `back-merge` it had before the hotfix landed, and could merge a combination onto prod
that `dev` never validated, which is the one thing the check exists to prevent.

So the `rerun-promotion-guards` job in [`back-merge.yml`](../../.github/workflows/back-merge.yml)
re-runs the newest `promotion-guard.yml` run of each pull request open against `main`. The
re-run's `back-merge` job fetches `main` and `dev` as they are now, so an open promotion goes red
on its own, and protect-main blocks it until the back-merge pull request is merged into `dev`. Pull
requests into any other branch are never touched. Three routes start that job, and all three run
the same [`scripts/rerun_promotion_guards.py`](../../scripts/rerun_promotion_guards.py). Each
route also opens the back-merge pull request when `dev` lacks a commit of `main`'s, or names the
open one, and does nothing visible when they agree (`v1-e01-t26-dispatch-opens-back-merge`):

| Route | Trigger | What it covers |
|---|---|---|
| **Fast path** | every push to `main` | A hotfix's promotions go red within about a minute of the merge. Added by `v1-e01-t12-promotion-guard-rerun`. |
| **Backstop** | a schedule, every 15 minutes (minutes 7, 22, 37 and 52 of each hour) | Needs no event at all. On 2026-09-30 GitHub never delivered the push for a merged hotfix, and with nothing to start the fast path the promotion stayed green and wrong, with no red anywhere. The sweep is asked for every 15 minutes, but GitHub ran it about every two to five hours when measured on 2026-10-15, so it catches a lost push within hours. It also opens the back-merge pull request, so a lost push shows on the pull request list even when no promotion is open to turn red. Added by `v1-e01-t15-promotion-guard-sweep`. |
| **Manual route** | **Run workflow** on *Back-merge main into dev* in the Actions tab, from `dev` or `main` | The same sweep, and the back-merge pull request, on demand in one click, for anyone who notices a lost push before the next scheduled run. Every promotion runs it once just before it merges (the promotion template's checklist), because the schedule runs only every few hours. |

**Which pull requests it re-runs.** The `back-merge` job of each guard run records the `main`
commit it compared, as a notice titled `promotion-guard evaluated main` on its check run. A pull
request whose newest guard run recorded the commit `main` points at now already reflects it and is
left alone, so a sweep where nothing moved re-runs nothing and logs one line. A run that recorded an
older commit, or none, is re-run; a run still in progress is waited for (up to 5 minutes), because
GitHub refuses to re-run a run in progress and it may have fetched `main` before it moved.

**What is mechanical now, and what is not.** Mechanical: a delivered push re-runs every stale
promotion's guards within a minute, and a lost one is caught by the next scheduled sweep without
anyone noticing it first. Whichever run catches it also opens the back-merge pull request that the
red `back-merge` check tells you to merge. Not mechanical:

* **The minutes between a lost push and the next sweep.** A promotion merged in that window merges
  stale. GitHub does not promise when a scheduled run starts; measured on 2026-10-15, it ran this one
  about every two to five hours. A promotion dispatches the sweep before it merges for that reason.
  What catches a merge in that window is a person: the hotfix template asks for the
  `rerun-promotion-guards` job to have *passed on the hotfix's own push*, and a job that never ran
  cannot be ticked. If no *Back-merge main into dev* run appears for the merge commit, dispatch it:
  that one run re-runs the guards and opens the back-merge pull request.
* **A back-merge pull request the workflow could not open.** Every run opens it when `dev` lacks
  something, so it is opened by hand only when a run's `open-back-merge-pull-request` job fails
  and a dispatch fails the same way. One cause is the repository setting **Allow GitHub Actions to create
  and approve pull requests** being off, which makes the job's `gh pr create` refused. Open it
  yourself, base `dev` and head `main`, labelled `back-merge`, and merge it with a merge commit as
  usual:

  ```bash
  gh pr create --base dev --head main --label back-merge --title "Back-merge main → dev" --body "Opened by hand: the back-merge workflow could not open it."
  ```

* **A re-run that fails.** A red `rerun-promotion-guards` job, with an error naming the pull
  request, means that promotion was not re-checked. Causes include a run older than GitHub's 30-day
  re-run limit, or a run that stayed in progress too long. The scheduled sweep stays red for it
  on every scheduled pass until someone acts. Re-run the checks on that pull request by hand: re-run its
  promotion-guard run in the Actions tab, or edit its description, which retriggers the workflow.
* **A pull request with no guard run at all**, because its own `pull_request` event was lost. There
  is nothing to re-run, so the sweep warns about it on every pass. protect-main already blocks it,
  since its required checks never reported; push to it or edit its description to start a run.
* **The schedule itself.** GitHub disables scheduled workflows in a public repository after 60 days
  without activity on it, and a scheduled run uses `back-merge.yml` as it is on `dev`, the default
  branch. Neither matters while work is merging, but a repository left idle for two months loses
  its backstop until someone re-enables the workflow.

## GitHub settings

Set now:

* Default branch → `dev`.
* Ruleset **protect-main** (target: pattern `main`, empty bypass list): restrict deletions, block
  force pushes, require a pull request with **0** required approvals (GitHub does not let you
  approve your own PR; the manual approval is the promotion checklist and, from V2, the
  `production` environment approval), dismiss stale approvals, require conversation resolution,
  allowed merge method **Merge** only. No linear-history rule (promotions are merge commits).
  Required status checks `ci`, `promotion-source`, `back-merge` and `validate-dev`, **not**
  "require branches to be up to date": every promotion leaves a merge commit on `main` that `dev` never receives, so that
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
* `v1-e01-t10-validate-dev-gate` → require the `validate-dev` commit status on `main`, from the
  GitHub Actions source (see [validate-dev](#validate-dev-the-status-protect-main-requires)).
* `v2-e12-t07-promotion-pipeline` → `development` / `production` GitHub Environments with
  branch-scoped deploy rules and Charlie as required reviewer on `production`.

## Releases

Release tags (`v1.1.0` …) are cut **from `main`** after the promotion that completes a release's
epics. Each `dev` merge produces the next pre-release (`v1.1.0-dev.7`). The release review Gate
in `plan_specs/releases/<version>.yaml` is approved on the promotion PR.

### The V1 CLI channels: dev pre-releases and stable releases

| | dev channel | stable channel |
|---|---|---|
| Tag | `vX.Y.Z-dev.N`, where `X.Y.Z` is the **next** stable release | `vX.Y.Z` (v1-e09-t06) |
| Wheel version | PEP 440 `X.Y.Z.devN`, which sorts **before** `X.Y.Z` | `X.Y.Z` |
| Published by | [`dev-prerelease.yml`](../../.github/workflows/dev-prerelease.yml), after `ci` is green on a push to `dev`; or a manual dispatch on a `hotfix/*` branch | the release workflow (v1-e09-t06) |
| GitHub release | always a **pre-release**; never PyPI | a full release |
| Default `DEBATE_ENV` | `dev` | `prod` |

**Where `X.Y.Z` comes from.** For a merge to `dev`, the `version` in
`packages/debate_cli/pyproject.toml`, the single version source. Once `vX.Y.Z` is released, that
version must be bumped before the next dev build: the workflow refuses to build dev pre-releases of
a version that already has a stable tag, because they would sort before it. For a hotfix
dispatch, the patch after the newest stable tag the hotfix head contains (`v1.1.1-dev.1` for a fix
to `v1.1.0`).

**How N is numbered.** `scripts/release_version.py` pushes the tag at the head commit before
anything is built, and the push is the claim: if an overlapping run pushed that number first, the
push is rejected and the next number is tried. N is therefore never reused, and increases in the
order runs claim it, which is the order their `ci` runs finished. Tags are immutable once
published. Pruning deletes the GitHub releases of dev builds older than the newest 30 and keeps
their tags.

**A commit dev has moved past** (v1-e01-t36). GitHub sometimes refuses the workflow's token a tag
("refusing to allow a GitHub App to create or update workflow ... without `workflows` permission")
and does not document when. Observed: both refusals in 374 runs to 2026-10-24 were for a dev commit
behind dev's head after a later commit changed `.github/workflows/`, while `v1.0.1-dev.1` and `.2`
were tagged at hotfix heads whose workflows differed from dev's. Reported (GitHub community
discussion #151442): a tag is refused when no branch head has the commit's workflow files. So the
claim for a merge to dev first fetches dev's head, and if dev is past the commit with different
workflow files, the run ends superseded: a notice names dev's head, no tag is pushed, nothing is
built, published or dispatched, and the run succeeds. Dev's head, which already contains the skipped
commit, gets its own pre-release. The check is conservative: it may skip a commit GitHub
would have tagged, never the reverse. Hotfix claims are not checked.
[`scripts/release_version.py`](../../scripts/release_version.py) has the details.

**What a pre-release contains.** The `debate_core` and `debate_cli` wheels (debate_cli pins
debate_core to the same version), `SHA256SUMS`, and `build-info.json`: version, tag, channel,
commit SHA, build time and workflow run id. The same values are stamped into the wheel, and
`debate-research --version --json` reports them with the environment the build will run as.

**Installing one.** `scripts/install_channel.sh <tag>` downloads the assets with `gh`, refuses
anything not matching `SHA256SUMS`, and installs `debate-cli` and `debate-core` **by the file URLs of
those verified wheels**, so no index can supply either name. Neither is registered on PyPI, and a
`--find-links` install would let anyone who registers `debate-core` there take the install over,
even at the exact pinned version. Third-party dependencies still come from PyPI. The result lives in
uv's tool directory (`uv tool dir --bin`), outside every checkout and project `.venv`, and stays that
build until another tag is installed. `debate-cli` requires the `debate-core` extras its composition
root wires (`aws`, `docx`, `opencaselist`), so boto3, lxml, httpx and keyring arrive with it from
PyPI. After installing, the script runs `python -m debate_cli.installation` in the new tool
environment, which imports every integration the CLI wires and fails the install unless all of
them import. `dev-prerelease.yml` runs the same install against every build before publishing it,
so a build that cannot run `caselist pull` is never released (v1-e01-t17). Builds published before
that change have no boto3 and are refused by the current script. Anything that
runs on a schedule (the caselist launchd agent, v1-e34-t05) should run an installed tag, never a
checkout's `.venv/bin/debate-research`, which `uv sync` rebuilds from whatever `dev` holds.

**Environments of an installed build.** `DEBATE_ENV` unset: a dev pre-release runs as `dev`, a
stable build as `prod`, a source checkout as `dev`. An explicit `DEBATE_ENV` (or one in `.env`)
always wins. An installed build reads the `config/profiles/` and model-routing files bundled in its
wheel, the ones it was built and validated with, from any working directory; `DEBATE_PROFILE_DIR`
overrides them. That includes the E34 `[caselist] api_enabled` gate: it is fixed per build, so
turning the API off for an installed build means installing a build whose profile says so, or
setting `DEBATE_CASELIST__API_ENABLED=false` in its environment. Editing `config/` in a checkout
does not reach it. Dev and prod never share a data directory (`~/.debate-research/dev` and `…/prod`)
or a model-routing file (`config/model_routing.dev.yaml` routes to cheaper models).

**Model spend.** The coach's ceiling is **$50 a month** of model spend across dev and prod
(`MONTHLY_MODEL_BUDGET_CEILING_USD`, 2026-10-27), and no committed budget is above it. Both
profiles set `models.budget_usd_monthly = 50.0`, a calendar month in America/Chicago, because only
one environment calls models today; the AWS Budgets alarm (`v1-e05-t16`) watches the account's real
total, which no one machine's usage log sees. The dev budget is capped at **$2/day**
(`DEV_DAILY_BUDGET_CAP_USD`), the capped landscape sample's allowance (the PM's ruling of
2026-10-27). Prod's is **$1.50/day**, the $50 over thirty days, rounded down. Dev's daily limit is
above prod's on purpose: dev is where the first live pass runs (`v1-e05-t15`).

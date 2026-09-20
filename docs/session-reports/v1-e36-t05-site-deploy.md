# Session report: v1-e36-t05-site-deploy

| | |
|---|---|
| Task | `v1-e36-t05-site-deploy` — Deploy flow: dev preview then prod |
| Spec | [`plan_specs/v1/e36-team-website/t05-site-deploy.yaml`](../../plan_specs/v1/e36-team-website/t05-site-deploy.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t05-site-deploy` |
| Session status | PARTIAL |

## Summary

The publishing machinery is written, linted and tested offline; nothing has been published,
because every step that touches AWS is an operator step and none of them has run yet.

`scripts/site_deploy.sh <dev|prod> [--dry-run]` builds `site/` for one environment, writes
`site/out/version.json` with the commit sha, syncs the export into that environment's bucket with
cache headers by path, and creates and **waits for** a CloudFront invalidation. Prod is refused
unless the checkout is clean, on `main` and equal to `origin/main` (ADR-0013).
`scripts/site_smoke.py --env <dev|prod> --url <url> [--expect-sha]` checks a deployed site: every
page in the sitemap, the HTTPS redirect, the six security headers, `X-Robots-Tag: noindex` on the
preview and its absence on prod, `robots.txt`, and the commit in `version.json`.
`tests/smoke/test_site.py` is the first entry in a new `tests/smoke/` directory.

Two things the PM should look at first. **One infrastructure change is in this PR**: the site
publisher permission set gains `cloudfront:GetInvalidation`, because `v1-e36-t02` granted
`CreateInvalidation` alone and a deploy could therefore start an invalidation but never confirm
the edge had picked the new files up — which is exactly what the publishing policy's 24-hour
student-removal clock depends on. That is outside this task's stated `constraints.packages` and is
written up under Deviations. **And the session stops before the deploys**: applying that policy,
deploying dev, promoting, and launching prod are five operator blocks below, one of which is
blocked on a fact only Charlie has (the room for the October 1 session, still `[[TBD]]` on the home
page, which correctly fails a prod build).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `deploy-script` | Done | `scripts/site_deploy.sh`: argument parsing, tool preflight, prod guard, Terraform outputs, build, `version.json`, three sync passes, invalidation with wait, `--dry-run`. |
| `deploy-script-tests` | Done | `tests/scripts/test_site_deploy.py`: 21 cases against a throwaway checkout with stub `git`, `terraform`, `pnpm` and `aws` on `PATH`. |
| `smoke-check` | Done | `scripts/site_smoke.py`, `tests/scripts/test_site_smoke.py` (27 respx cases), `tests/smoke/test_site.py` + `tests/smoke/README.md`. |
| `dev-preview` | Partial | Runbook procedures written (deploy, rollback, takedown). The dev deploy and its smoke check are operator follow-ups 3 and 4; not run. |
| `prod-launch` | Not started | Needs the promotion and the room fact. The *First prod launch* record exists in the runbook with `_pending_` fields for the operator to fill; operator follow-up 5. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1 — deploy script passes shellcheck; offline tests show prod refused from a non-main branch, a dirty tree or a commit ≠ `origin/main`, and `--dry-run` makes no `aws s3`/`cloudfront` write | PASS | `uv run shellcheck scripts/site_deploy.sh` → no output, exit 0. `uv run pytest tests/scripts/test_site_deploy.py` → `21 passed in 14.17s`, including `test_prod_is_refused_from_a_branch_other_than_main`, `..._when_the_tree_is_dirty`, `..._when_head_has_drifted_from_origin_main`, `..._when_origin_cannot_be_fetched` and `test_dry_run_makes_no_aws_call_at_all`. |
| Goal ac2 — smoke checker fails on a non-200 page, a missing HSTS/CSP/`X-Content-Type-Options` header, a missing http→https redirect, `noindex` on prod, or a `version.json` sha mismatch, with no live call | PASS | `uv run pytest tests/scripts/test_site_smoke.py` → `27 passed in 1.20s`. One test per failure, all respx-mocked; the default pytest run also has `--disable-socket`. |
| Goal ac3 — the dev preview has been deployed, passes the smoke check with its `noindex` header, and the same commit reached `main` through a validated promotion | PARTIAL, redeploy needed | Deployed and checked: `scripts/site_deploy.sh dev` at `f15fa16` on 2026-09-20, invalidation `IAM1U04QZPV5D7HUB6CQL4WGCH` created and waited on; `scripts/site_smoke.py --env dev --url https://dev.wfbdebate.com --expect-sha f15fa16…` → **All 28 checks passed**, including `X-Robots-Tag: noindex` on all eight pages. Not yet satisfied: that was the task branch, and a squash merge gives the work a new sha on `dev`, so the commit actually promoted is re-deployed and re-checked before the promotion PR. |
| Goal ac4 — runbook has a deploy and rollback procedure and a *First prod launch* entry (date, sha, URL, smoke result, no account ids) | PARTIAL | Procedures: `docs/runbooks/team-website.md` §*Deploying the site*, §*Rolling back a deploy*, §*Taking something down on request*. Entry: §*First prod launch* exists with its fields `_pending_`; the launch has not happened, so there is nothing truthful to put in them yet. Operator follow-up 5 fills it. |
| Goal ac5 — the prod site is live and passes the smoke check before the October 1, 2026 parent session | NOT RUN | Operator follow-up 5. Blocked behind follow-ups 1 to 4 and the room fact. |
| `deploy-script` — `shellcheck scripts/site_deploy.sh` | PASS | `uv run shellcheck scripts/site_deploy.sh` → exit 0. (Run through `uv run`: ShellCheck is now a dev dependency, see Deviations.) |
| `deploy-script-tests` — `uv run pytest tests/scripts/test_site_deploy.py` | PASS | `21 passed in 14.17s`. |
| `smoke-check` — `uv run pytest tests/scripts/test_site_smoke.py` | PASS | `27 passed in 1.20s`. |
| `smoke-check` — `uv run ruff check scripts/site_smoke.py tests/scripts tests/smoke/test_site.py` | PASS | `All checks passed!` Repo-wide: `uv run ruff check .` → `All checks passed!`, `uv run ruff format --check .` → `125 files already formatted`. |
| `dev-preview` — `docs/runbooks/team-website.md` contains `site_deploy.sh` | PASS | `grep -c site_deploy.sh docs/runbooks/team-website.md` → `11` matching lines, in the deploy, rollback, takedown and launch sections. |
| `dev-preview` — custom: Charlie confirms the dev smoke check passed for the commit being promoted, including `noindex`, and the preview looks right on a phone | PARTIAL | Round 1: smoke check passed in full for `f15fa16` (28/28), but the phone review **failed** and was worth more than the 28 automated checks — the page rendered unstyled (deviation 3). Round 2, after the stylesheet fix: Charlie confirmed the mobile rendering looks good and found the desktop reading column off centre, fixed in `2dbe4b0`; he redeployed dev and confirmed the centring. Outstanding: the same run against the commit actually promoted, and the polish items under *Site polish before the October 1 parent session*, which he wants addressed before parents see the site. |
| `prod-launch` — `docs/runbooks/team-website.md` contains `First prod launch` | PASS (placeholder) | The section exists with the right fields; its values are `_pending_` until the launch. Reported as PASS against the literal criterion and as not-yet-true in substance. |
| `prod-launch` — custom: Charlie confirms, on or before September 30 2026, that the prod site passes the smoke check at the URL he will give parents | NOT RUN | Operator follow-up 5. |
| Regression — Terraform static checks still pass after the policy change | PASS | Re-run after the rebase onto `dev` at `9a3e86f`: `scripts/terraform_checks.sh` → `ok test infrastructure/modules/static_site`, `All Terraform checks passed.` The script now runs `terraform test` itself (#23), so the module suite is covered rather than hand-run; the direct run earlier in the session gave `Success! 11 passed, 0 failed.` |
| Regression — spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 278 files, 38 epics, 220 tasks, 20 releases`. |
| Regression — cross-package tests and pre-commit | PASS | `uv run pytest tests` → `78 passed in 14.39s` after the rebase. `uv run pre-commit run --files <changed>` → every hook Passed or Skipped. |
| Operator step 4 — both maintainer profiles can read their root's Terraform outputs | PASS | `AWS_PROFILE=debate-dev terraform -chdir=infrastructure/envs/dev output -raw site_bucket_name` → `debate-dev-site-a7508de8`; the same with `debate-prod` → `debate-prod-site-a7508de8`. So the script's default split holds in both environments and no `SITE_TERRAFORM_PROFILE=debate-admin` override is needed — an open question at the time the script was written. |
| Operator step 3 — prod converged, and the extra changes are accounted for | PASS | The prod apply reported `0 added, 9 changed, 0 destroyed` where the policy change alone is 1. Prod holds exactly eight taggable resources (`terraform state list`: the site bucket, distribution and certificate, the evidence bucket and KMS key, and three permission sets), and a changed `owner` rewrites the `Owner` tag on all of them through the provider's `default_tags` — eight tag updates plus the inline policy is nine. The `Owner` tag now reads `ctcb57@gmail.com`. A read-only `terraform plan -lock=false` afterwards reports `No changes. Your infrastructure matches the configuration.`, so nothing is outstanding and no resource was replaced. Cause: the operator block in this report supplied a concrete `OWNER_EMAIL` where the runbook had a placeholder; the runbook now says to read the deployed value back instead. |
| Operator step 3 — the publisher policy is applied in both environments | PASS | `aws sso-admin get-inline-policy-for-permission-set` for `DebateDevSitePublisher` and `DebateProdSitePublisher` both return six actions, ending `cloudfront:CreateInvalidation`, `cloudfront:GetInvalidation`. Confirmed in use: the dev deploy's wait on the invalidation returned rather than failing `AccessDenied`. |
| Regression — the branch is current with `dev` | PASS | `scripts/task sync v1-e36-t05-site-deploy` → `Successfully rebased and updated refs/heads/task/v1-e36-t05-site-deploy` onto `9a3e86f`, no conflicts, nothing pushed (the branch is not on origin). `uv run shellcheck scripts/site_deploy.sh`, `uv run ruff check .` and `uv run scripts/validate_specs.py` all clean afterwards. |

## Files changed

**`scripts/`** — `site_deploy.sh` (new) publishes one environment; `site_smoke.py` (new) checks a
deployed one.

**`tests/scripts/`** — `test_site_deploy.py` and `test_site_smoke.py` (new): the offline suites for
both, stub executables for the first and respx for the second.

**`tests/smoke/`** — new directory. `test_site.py` runs the smoke checker against a deployed site
when `SITE_SMOKE_URL` is set, marked `live` plus `dev`/`prod`; `README.md` says what belongs here
and how `validate-dev` invokes it.

**`docs/runbooks/team-website.md`** — step 9 (widen the publisher policy, with its apply block),
then *Deploying the site*, *Rolling back a deploy*, *Taking something down on request* and
*First prod launch*. The header, step 7, step 8 and the *does not do* list were corrected where
they described the publisher as unable to poll an invalidation. `docs/README.md` — index line.

**`infrastructure/modules/static_site/`** — `publisher_access.tf` adds
`cloudfront:GetInvalidation` on the module's own distribution; the module test asserts six actions
rather than five; `README.md` records why. See Deviations.

**`pyproject.toml`, `uv.lock`** — `httpx` and `shellcheck-py` join the dev group, and ruff's
`scripts/` exclusion now names the five legacy files instead of the directory. See Deviations.

## Deviations from the spec

1. **The Terraform publisher policy was widened, which is outside this task's
   `constraints.packages`** (`scripts`, `tests/smoke`, `tests/scripts`, `docs/runbooks`).
   `v1-e36-t02` granted `cloudfront:CreateInvalidation` and not `GetInvalidation`, and its own
   session report recorded that this task would therefore be unable to poll an invalidation. This
   task's spec says the deploy "creates and waits for a CloudFront invalidation", so the two
   cannot both stand. The PM directed this session to add the one action and keep the wait,
   because the publishing policy's 24-hour student-removal clock is only honest if something
   confirms the edge stopped serving the page. `infrastructure/modules/static_site` now grants six
   actions; the module test and README were updated with it. **The PM should amend `t02`'s spec
   (its five-action list) and either widen `t05`'s `constraints.packages` or record this as an
   accepted crossing.** Applying it is operator follow-up 1; until then, a real deploy fails at
   the wait with `AccessDenied` after a successful upload.

2. **`pyproject.toml` was changed, also outside `constraints.packages`.** Three edits, all in
   service of this task's own criteria: `shellcheck-py` in the dev group so that
   `uv run shellcheck` satisfies the `deploy-script` criterion on a laptop and on a CI runner with
   no `brew install`; `httpx` in the dev group because `scripts/site_smoke.py` imports it and it
   was previously only present as a transitive dependency of `respx`; and ruff's
   `extend-exclude = ["./scripts"]` replaced by the five legacy file names, so that
   `scripts/site_smoke.py` is actually linted. Without the last one the `smoke-check` lint
   criterion would have passed vacuously — ruff would have reported "No Python files found" and
   exited 0.

3. **The site shipped with no CSS, and this task fixed it. `v1-e36-t04` caused it.**
   `v1-e36-t03-site-scaffold` imported `@/styles/globals.css` from `site/src/app/layout.tsx`
   (`fa480cd`), which is the one line that makes Next emit a stylesheet and link it from every
   page. `v1-e36-t04-core-pages` removed it (`cdd8203`). Every build since exported markup with
   **no CSS at all**: correct content, headings and landmarks, rendered in the browser's default
   styling. That is what this task deployed to the dev preview, and Charlie looking at it on a
   phone is what caught it, which is exactly what the `dev-preview` node's human criterion is for.

   The fix is the one line restored. The build now emits `_next/static/chunks/*.css` and
   `index.html` links it; 211 site tests pass and both builds are clean.

   **Nothing in the suite could have caught this**, which is the more important half.
   `tokens.test.ts` reads the stylesheets from disk and verifies their contrast ratios, which says
   nothing about whether they ship. `layout.test.tsx` and `pages-a11y.test.tsx` run axe under
   jsdom, which has no layout engine and therefore skips colour contrast, so unstyled HTML passes
   them cleanly. So `site/tests/stylesheet-ships.test.ts` is new: it asserts the layout keeps the
   side-effect import, that `globals.css` still `@import`s the other three, and, whenever a build
   has produced `site/out/`, that every exported page links a stylesheet which exists in the
   export and contains the design tokens. Verified that it fails when the import is removed.

   This is `v1-e36-t03`/`t04` code, outside this task's `constraints.packages`. Fixed here rather
   than deferred because it blocked the launch outright: an unstyled site is not something to put
   in front of parents on October 1, and the deploy flow this task exists to deliver had already
   published it once. **The PM should decide whether `v1-e36-t04`'s Goal should go back from
   `Succeeded`**, since its acceptance criteria were met by a build that shipped no styling.

4. **The home page copy was changed, which is `v1-e36-t04`'s file, not this task's.**
   `site/content/pages/home.md` carried `[[TBD: room for the October 1 parent information
   session]]`, and the content guard fails a prod build on a placeholder, so `ac5` could not be met
   while it stood. The room is still undecided, so there was no fact to fill in. Rather than
   bypass the guard, the sentence was rewritten to be true and complete without the room:

   > **Wednesday, October 1, 2026, 6:00 PM, Whitefish Bay High School.**
   >
   > The room is not set yet. It will be posted here before the session.

   That is the guard working as intended — it exists to stop half-written copy shipping, not to
   force a fact to be invented. `SITE_ENV=prod pnpm --dir site build` now exits 0 with no
   publishing-policy problems, and `site/scripts/pre-commit-checks.sh` (lint, typecheck, test,
   build) passes. When the room is decided it is a one-line content change and a redeploy, which
   is what the deploy flow is for. The PM should confirm the wording; it is copy for parents.

5. **The `Owner` tag on eight prod resources was rewritten as a side effect.** The step 3 operator
   block in this report gave `OWNER_EMAIL` a concrete value, where the runbook's own *Before you
   start* block deliberately carries a placeholder and the variable's description says it is kept
   out of the repository. The value that reached the apply differed from the one the previous
   applies used, so every taggable resource in each root picked up a new `Owner` tag: benign, not
   reverted, and the reason prod reported nine changes rather than one. The runbook now tells the
   operator to read the deployed value back with `aws s3api get-bucket-tagging` rather than retype
   it, and says what each change count means. **Decided: the new value stands** — it is consistent
   across both roots and every resource in them, so it is now the canonical `owner` and the one a
   future apply must match.

6. **`prod-launch`'s `artifact_exists` criterion passes on a placeholder.** The runbook has the
   *First prod launch* section and the string the criterion matches, but its fields are `_pending_`
   because the launch has not happened. Flagged rather than left to look like a pass.

7. **Prod is not deployed yet.** The dev preview is live and passes its smoke check, but the
   `prod-launch` node needs the promotion first, so the task Goal stays `InProgress` until the
   prod deploy and its runbook entry.

## Decisions and assumptions

* **Two AWS profiles per environment.** `terraform output` runs as `debate-<env>` and everything
  else as `debate-<env>-site`, because the publisher permission set cannot read Terraform state.
  Both are overridable (`SITE_TERRAFORM_PROFILE`, `SITE_PUBLISHER_PROFILE`), so a root whose state
  a maintainer cannot read is a variable away from working rather than a script edit away.

* **`--dry-run` runs the prod guard and the build.** A rehearsal that skipped either would
  rehearse the wrong thing; the only thing it skips is the `aws` calls. The consequence is that a
  prod dry run from a task branch is refused, which is why the runbook says to rehearse on dev.

* **Three sync passes rather than one.** Hashed `_next/static` assets go up first with a year of
  cache and no `--delete`, so a page is never served before the chunks it references exist; then
  everything else with `--delete` and `no-cache`; then the hashed prefix again with `--delete` to
  prune chunks nothing references. One pass cannot both order the uploads and set two different
  cache headers.

* **The smoke check asserts indexability on every page, not once.** Per the PM: the dev preview
  must send `X-Robots-Tag: noindex` on every page and prod must not send it at all. `robots.txt`
  is checked the same way. A findable preview is the privacy failure the publishing policy exists
  to prevent, so it is worth the extra assertions.

* **Six security headers, not the three the criterion names.** `v1-e36-t02` sets HSTS, CSP,
  `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` and `Permissions-Policy` on every
  response, and the runbook records all of them as present in both environments, so requiring the
  full set costs nothing and catches a Terraform regression the three-header version would miss.

* **A clean prod build is a precondition, not something to work around.** `SITE_ENV=prod` fails
  today on the `[[TBD]]` room marker in `site/content/pages/home.md`. The deploy script uploads
  nothing when the build fails, and the runbook says to fill the fact in rather than deploy around
  it.

* **`tests/smoke/` is new, and nothing runs it automatically yet.** The `validate-dev` gate itself
  is `v1-e01-t10`, which has not landed; until it does, these are run by hand (or by an operator
  after a deploy) with the command in `tests/smoke/README.md`. The suite is marked `live` so the
  default `pytest` run excludes it, and pytest-socket's `enable_socket` marker is what lets these
  two tests — and only these two — reach the network.

* **`version.json` carries the commit, the environment, the site URL and a build timestamp.** No
  account id, no profile name, nothing about who ran the deploy.

## Operator follow-ups

Run these in order. 1 and 2 are prerequisites for any deploy; 3 to 5 are the deploy flow itself.

### 1. Apply the widened publisher policy (runbook step 9)

**Ordering: resolved, and this branch is ready to apply from.**
`v1-e29-t03-evidence-buckets` applied fifteen evidence-store resources to each env root on
2026-09-20, so for a while a plan from this branch would have proposed fifteen destroys and then
failed on `prevent_destroy`. That task merged to `dev` as #22 (`de1367d`) and this branch has been
rebased onto `dev` at `9a3e86f`, so its configuration now covers everything in both roots. A plan
should show one change and no evidence resources; if it shows evidence resources being created,
the rebase was lost. (Deploying never depended on this: `terraform output` reads state, not
configuration.)

`owner.auto.tfvars` now needs four lines, not two: `site_publisher_user_names`,
`evidence_operator_user_names` and `evidence_removal_user_names` all default to `[]`, so a fresh
checkout plans a destroy of all three sets of account assignments with nothing louder than the
`var.owner` prompt. Names verified against
`infrastructure/envs/dev/owner.auto.tfvars.example` after the rebase.

**Operator command** (expected runtime ~6 min, mostly two applies)
Where: your Mac, in a checkout holding this branch — set `WT` to it
`owner.auto.tfvars` is gitignored, so it does not exist in this worktree and the `t02` worktree
that held it is gone. `site_publisher_user_names` defaults to `[]`, so applying without it
**destroys the account assignment** that makes the publisher profiles assumable. Write both files
first (runbook *Before you start*).

```bash
cd "$WT"
for env in dev prod; do
  cat > "infrastructure/envs/$env/owner.auto.tfvars" <<TFVARS
owner                        = "$OWNER_EMAIL"
site_publisher_user_names    = ["$SSO_USER_NAME"]
evidence_operator_user_names = ["$SSO_USER_NAME"]
evidence_removal_user_names  = ["$SSO_USER_NAME"]
TFVARS
done
terraform fmt infrastructure/envs/dev infrastructure/envs/prod

export AWS_PROFILE=debate-admin
aws sso login --sso-session debate
aws sts get-caller-identity --query Arn --output text   # expect AWSReservedSSO_DebateBreakGlassAdmin

for env in dev prod; do
  terraform -chdir="infrastructure/envs/$env" init -reconfigure -input=false
  terraform -chdir="infrastructure/envs/$env" apply
done
```
Success looks like: one plan per environment showing **1 to change, 0 to add, 0 to destroy**; the
resource is `module.site.aws_ssoadmin_permission_set_inline_policy.site_publisher[0]` and the diff
adds `cloudfront:GetInvalidation` beside `cloudfront:CreateInvalidation` (the permission set
description changes too). A planned destroy of `aws_ssoadmin_account_assignment.site_publishers`
means the tfvars are missing: answer `no`.

### 2. Refresh the publisher sessions and confirm the widening is one action wide

**Operator command** (expected runtime ~2 min)
Where: your Mac, anywhere
```bash
aws sso logout
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-site  --query Arn --output text
aws sts get-caller-identity --profile debate-prod-site --query Arn --output text
```
Then run the `simulate-principal-policy` block in runbook step 9. Success looks like: `allowed`
for `cloudfront:CreateInvalidation` and `cloudfront:GetInvalidation` on each publisher's **own**
distribution, `implicitDeny` on the other environment's. The `logout` matters: a cached session
carries the old policy, and a deploy that skips it fails on the wait with an `AccessDenied` the
console will contradict.

### 3. Install the site dependencies and check the prod build

**Operator command** (expected runtime ~3 min, mostly `pnpm install`)
Where: `$WT`
```bash
cd "$WT"
pnpm --dir site install
SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build
```
Success looks like: the build completes. **It is expected to fail today** on the `[[TBD]]` room
marker in `site/content/pages/home.md` — the room for the October 1 parent information session.
That is the content guard doing its job. Supply the room, commit it, and re-run; a dev build
succeeds either way, so follow-up 4 does not have to wait for it.

### 4. Deploy and smoke-check the dev preview

**Operator command** (expected runtime ~5 min, most of it the invalidation)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
scripts/site_deploy.sh dev
uv run scripts/site_smoke.py --env dev --url https://dev.wfbdebate.com \
  --expect-sha "$(git rev-parse HEAD)"
```
Success looks like: the deploy prints the bucket, distribution and URL it read from Terraform, a
clean build, three `aws s3 sync` passes, an invalidation that completes, and
`Deployed <sha> to dev: https://dev.wfbdebate.com`; then `All N checks passed.` from the smoke
check. Paste the last 20 lines of each back into the session. Then open the preview on a phone and
read it as a parent would — that is the part no check covers.

### 5. Promote, launch prod, and record it

After this PR and the dev-to-main promotion PR have merged.

**Operator command** (expected runtime ~5 min)
Where: your Mac, in the **main clone** on `main`
```bash
git checkout main && git pull --ff-only
git status --porcelain        # must print nothing
aws sso login --sso-session debate
scripts/site_deploy.sh prod
uv run scripts/site_smoke.py --env prod --url https://wfbdebate.com \
  --expect-sha "$(git rev-parse HEAD)"
```
Success looks like: `clean, on main, and equal to origin/main.`, a clean prod build, three syncs,
an invalidation that completes, then `All N checks passed.` with no `X-Robots-Tag` on prod. Then
fill in the *First prod launch* table and the four `_pending_` rows in *What to record* in
`docs/runbooks/team-website.md` (date, sha, URL, invalidation id, smoke result — **no account
ids**), and set the task Goal to `Succeeded`.

### 6. Optional: the full test suite

**Operator command** (expected runtime ~2-5 min)
Where: `$WT`
```bash
uv run pytest
```
This session ran `tests/` (78 passed) and both new suites, but not the package suites. The changes
outside `scripts/`, `tests/` and `docs/` are the Terraform policy and `pyproject.toml`, so a full
run is a cheap confirmation rather than a suspicion.

## Follow-up work

### Site polish before the October 1 parent session

Raised by Charlie after reviewing the dev preview on a phone and a laptop. He wants the site
polished before parents see it, and asked whether that means moving off the static export to a
server-rendered Next.js app. **It does not**, and the recommendation is not to: see the last item.
Everything below is a task for the PM to spec; none of it was done in `v1-e36-t05`, whose scope is
the deploy flow.

1. **The Parent FAQ is sixteen questions in one wall of text** (1,044 words,
   `site/content/pages/faq.md`). It is the page a parent arrives at with exactly one question, and
   today they scan past fifteen others to find it. Make each question a disclosure using native
   `<details>` and `<summary>` rather than a JavaScript component: keyboard operation, screen-reader
   expand/collapse announcement and focus handling come free and are more reliable than a
   hand-rolled ARIA widget; Ctrl+F still finds and auto-expands collapsed text in current Chrome,
   Edge and Safari, which a component that unmounts its content breaks, as it breaks printing; and
   it degrades to visible text if anything fails. Needs a content convention for question/answer
   pairs, a 44px tappable summary row, and markup plus axe tests. Roughly half a day.

2. **The Events page is the longest on the site** (1,207 words) and has the same shape: Policy,
   Lincoln-Douglas and Public Forum explained in undifferentiated prose. Whatever pattern the FAQ
   gets should be considered here, or at least per-event sections with jump links from the top.

3. **`site/src/components/Card.tsx` is used by zero pages.** The scaffold built a card with a
   brand-accent rule under its title and nothing ever rendered one, which is a large part of why
   the pages read flat: every page is `<h1>` plus one undifferentiated prose column. Worth a pass
   that uses the design system that already exists, starting with the home page's information
   session block and the Join page's three ways to sign up.

4. **The home page has no visual anchor.** No hero, no photograph, no pull-out for the one thing
   the page is for, which is the October 1 session. Any photograph is gated on the media-consent
   process in `docs/policies/website-publishing.md`, so a non-photographic treatment is the fast
   path.

5. **Do not move to a server-rendered Next.js app for this.** The polish above is all
   client-side, and a static export already ships client-side React: `site/src/components/SiteNav.tsx`
   is a `'use client'` component, and the navigation menu that opens with Enter or Space and closes
   with Escape is running in the browser today. The static-export constraint forbids API routes,
   middleware, server actions and ISR, none of which an accordion, a tab strip, a filter or an
   image carousel needs.

   A server would cost three things that matter here. It amends
   [ADR-0012](../adr/0012-web-hosting.md), which chose S3 and CloudFront. It means new hosting,
   cost and operational surface for a school team site that is read a few thousand times a year.
   And it breaks ADR-0012 decision 8 — no CloudFront access logging, so **no per-request record of
   visitor IP addresses exists** — because a server has request logs by default and turning them
   off is a thing you have to remember rather than a thing you never built. The audience is
   schoolchildren and their families; that decision was deliberate and should not be spent on
   styling. If something genuinely needs a server later, `v2-e14-t03-app-hosting` already exists to
   mount the authenticated app under the same domain.

* **The env roots are shared and nothing sequences applies across tasks.** Two tasks in flight
  today (`v1-e29-t03-evidence-buckets` and this one) each change `infrastructure/envs/*`, and an
  apply from whichever branch is behind either destroys the other's resources or silently reverts
  its policy. **A revert is invisible in the plan's counts**: undoing a shared module's change
  reads as `1 to change`, indistinguishable from an intended edit, so only reading the diff body
  for that resource catches it. Counts catch the destroy case and nothing else. Raised from both
  sides — `v1-e29-t03`'s report carries the same item — and it wants a rule in `docs/process/`
  (apply only from a branch rebased on the latest `dev`; never from a task branch once another
  task's resources are live in that root). Neither session wrote that rule: `working-agreements.md`
  says changes to it go through their own PR, so it is the PM's to make rather than something to
  slip into a task branch.
  **This one has not reached the PM yet**: `v1-e29-t03`'s PM review was written before that
  session recorded it, so this copy may be the first one read.

* **`validate-dev` does not exist yet** (`v1-e01-t10-validate-dev-gate`). `tests/smoke/test_site.py`
  is written to be invoked by it, and until that task lands the dev smoke check is a manual step in
  the runbook. Worth confirming that `v1-e01-t10` knows to pass `SITE_SMOKE_URL`, `SITE_SMOKE_ENV`
  and `SITE_SMOKE_SHA` and to select `-m dev`.
* **CI does not run `shellcheck` or the site smoke suite.** `scripts/site_deploy.sh` now has a lint
  criterion and a dev dependency that satisfies it, but no workflow file exists in this repository
  yet (`.github/workflows/` is absent). Whichever task adds the `ci` workflow should include
  `uv run shellcheck scripts/*.sh` in the fast path.
* **The five legacy `scripts/*.py` files are still unlinted** (`v1-e01-t05-spec-tooling`,
  `v1-e01-t11-task-workflow-cli`). They are now named individually in `pyproject.toml`, so bringing
  them in is deleting a line each.
* **`wfbdebate.org`** remains blocked in an AWS Support case. Nothing here builds for it; if it is
  ever issued it becomes a redirect to `.com`, which is a tfvars change and an apply.
* **`terraform test` in the checks script: closed, no task needed.** This session first ran
  `terraform test` in `infrastructure/modules/static_site` by hand (11 passed) because
  `scripts/terraform_checks.sh` ran only `fmt`, `validate` and `tflint`. The PM closed that gap in
  `Specs: evidence key/alias/profile alignment; run module tests in the checks script` (#23, on
  `dev` as `9a3e86f`): the script now runs `terraform test` for every module with a `tests/`
  directory, with `--no-test` to skip. After the rebase onto that commit the static_site suite runs
  from the script rather than by hand, so this is recorded as resolved, not proposed.
* **Automatic republish on a content change** is `v1-e37-t04`, and **keyless CI deploys** are
  `v2-e10-t03`. When the latter lands, the prod guard in `scripts/site_deploy.sh` has to be
  reproduced in the workflow, or the script has to be what the workflow runs.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

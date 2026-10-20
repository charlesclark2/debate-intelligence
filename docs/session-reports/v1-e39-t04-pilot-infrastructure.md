# Session report: v1-e39-t04-pilot-infrastructure

| | |
|---|---|
| Task | `v1-e39-t04-pilot-infrastructure` — Pilot infrastructure: the function, CloudFront, the user pool and the audit log, in dev and prod |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t04-pilot-infrastructure` |
| Session status | PARTIAL: the PM's rulings are applied; waiting on the operator's dev outputs (runbook steps 1–10) to close ac5 and set `Succeeded` |

## Summary

ADR-0019's pilot infrastructure is built as one new module, `infrastructure/modules/evidence_search`,
called identically from `envs/dev` and `envs/prod`, which differ only in `terraform.tfvars` (and
`backend.tf`, as before). The module holds the image repository, the arm64 container function with
an `AWS_IAM` function URL behind CloudFront's origin access control, the distribution and its
headers, one certificate for the pilot and login hosts, the Cognito pool with its managed login
domain and confidential client, the SES identity, the audit (400 days) and app (30 days) log groups,
the two SecureString parameters, the $10 budget, and the `TubDeployer` and `TubAccounts` permission
sets. `debate_api` gets the placeholder app (FastAPI and uvicorn, `/healthz`, one page), with a
Dockerfile and `scripts/tub_deploy.sh`. `docs/runbooks/evidence-search.md` writes out the
operator's order with expected output at every step. The mocked `terraform test` (16 runs) checks the
role against ADR-0019's role table entry by entry, the pool, and the evidence bucket beside it. All
29 mutants were caught by an assertion failing.

**Look first at:** the one PM question. Provider 5.100.0 cannot set the login domain's minimum TLS
version, a third setting the ADR's list of provider gaps leaves out. It is a runbook step with a
read-back, pending your ruling. **The Goal stays `InProgress`**: ac5's "measured asset hosts" can only
be measured by the operator on a deployed dev. That is runbook step 10, and nothing else is open.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `infrastructure` | Done (its criterion passes) | The module, both roots, the placeholder app, the image, the deploy script and the runbook. The Goal's ac5 has one part only the operator can close (below) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `infrastructure`: Terraform checks pass | PASS | `bash scripts/terraform_checks.sh` → `ok` for fmt, validate of all 9 directories, the tflint configs, `tflint --recursive`, and `test` of all 4 modules; `All Terraform checks passed.` (21 s with providers cached; 1 min 49 s on the first run under load) |
| ac1: checks pass for both roots and the new module; the roots differ only in their tfvars, as the website's do | PASS | As above. `diff -r infrastructure/envs/dev infrastructure/envs/prod -x .terraform -x owner.auto.tfvars` → only `backend.tf` and `terraform.tfvars` differ, as before this task. `evidence_search.tf`, `variables.tf`, `outputs.tf` and `owner.auto.tfvars.example` are identical. `tests/scripts/test_tub_deploy.py::test_the_script_names_the_resources_adr_0019_names` also reads the root's module call |
| ac2: mocked test: evidence buckets keep all four BPA flags; no bucket policy grants CloudFront or the public; the role reads only the three key patterns, writes nothing in the bucket, holds no delete on its log group; the log group keeps 400 days | PASS | `terraform -chdir=infrastructure/modules/evidence_search test` → `Success! 16 passed, 0 failed.` Runs: `evidence_bucket_keeps_block_public_access_and_grants_cloudfront_nothing` plans `../evidence_bucket` with the roots' inputs and asserts the four flags, no `Allow` in the bucket policy and no CloudFront or public principal in the key policy. `cloudfront_reaches_the_function_url_and_nothing_else` asserts the only origin is the function URL. `function_role_is_the_adr_role_table_entry_by_entry` covers GetObject on exactly the three patterns, no other S3 action, and only CreateLogStream/PutLogEvents on the log groups. `audit_log_keeps_four_hundred_days_and_the_app_log_thirty` |
| ac3: mocked test: no self sign-up, TOTP required, email MFA offered, no SMS configuration, no attribute beyond username and optional email | PASS | Same command. `user_pool_admits_only_coach_created_accounts_with_totp`: admin-only creation, MFA `ON`, TOTP enabled, email MFA present, the password as the only first factor, no device remembering. `user_pool_has_no_sms_and_nothing_beyond_a_username_and_an_optional_email`: no `sms_configuration`, no schema block, no username or alias attributes, case-insensitive, email the only auto-verified attribute, client reads `email`/`email_verified` and writes `email` only |
| ac4: the runbook writes out apply dev, deploy a placeholder page that requires sign-in, apply prod, request SES production access, and the web-filter request (hostnames only), with expected output | PASS | [`docs/runbooks/evidence-search.md`](../runbooks/evidence-search.md), steps 1–12 in the PM's order, each with "Success looks like". Step 8 proves the path as the PM defined it: through CloudFront `200 private, no-store`; a direct call to the function URL gets `{"Message":"Forbidden"}`/`403`, Lambda's own refusal. Step 10 renders the managed login at the login host. Step 4 is SES, moved to right after the dev apply by the PM's review; step 12 is the IT text (prod hostnames only). `check_links.py`, `docs_index.py --check-descriptions`, `check_command_blocks.py --base origin/dev` → all OK. The outputs are the expected ones; nobody has run the steps yet |
| ac5: the role checked against the role table entry by entry, incl. the app log group, the two SSM parameters and no other grant; the runbook's CLI steps for branding and deletion protection, and the measured asset hosts, written out with expected output | **NOT RUN** (in part) | **Done:** `function_role_is_the_adr_role_table_entry_by_entry` compares every action with every resource against a hand-written copy of the table (`expected_role_table`, app group and both parameters included). `function_role_has_no_other_grant` checks the exclusive-policy resources (one inline policy, zero managed) and the trust policy. Runbook steps 5a and 5b have their CLI commands and read-backs. **Open:** "the measured asset hosts". Measuring them needs a deployed dev and a person signing in with the network panel open (runbook step 10). The table in the runbook says `Not measured yet`. No session can close this |

The Goal is left `InProgress` because ac5 is not closed.

**Mutation runs** (agreement 8; agreement 10 caps them at about 20, and this ran 29: 24 on the
module, aimed at the role and the pool, and 5 on the deploy script). Every mutant was applied to the
committed file, run, and restored; the tree was clean afterwards. Each one counted is a failed
assertion, not a Terraform or collection error. The harness is in the scratchpad, not the repository.

| Mutant | Caught by |
|---|---|
| role: + `s3:GetObjectVersion`; `raw/*` → `parsed/*`; + `bucket/*`; kms without `kms:ViaService`; + `logs:DeleteLogStream`; app group dropped; `ssm:GetParameter*`; ssm on `*`; + a Cognito grant | `function_role_is_the_adr_role_table_entry_by_entry` (9 of 9) |
| role: `AWSLambdaBasicExecutionRole` attached | `function_role_has_no_other_grant` |
| audit retention 365 | `audit_log_keeps_four_hundred_days_and_the_app_log_thirty` |
| function URL auth `NONE` | `cloudfront_reaches_the_function_url_and_nothing_else` |
| pool: self sign-up; MFA `OPTIONAL`; TOTP off; no email MFA; + `EMAIL_OTP` first factor | `user_pool_admits_only_coach_created_accounts_with_totp` |
| pool: an SMS configuration; email required; sign-in by email; case-sensitive; client reads `phone_number` | `user_pool_has_no_sms_and_nothing_beyond_a_username_and_an_optional_email` |
| client: + `ALLOW_USER_PASSWORD_AUTH` | `app_client_is_confidential_code_flow_only` |
| prod pool unprotected | `prod_protects_its_pool_and_is_not_marked_noindex` |
| script: provenance left on; amd64; no Docker check; function pointed at the tag; first deploy as an error | `test_the_image_is_built_for_arm64_without_provenance_from_the_declared_python` (2), `test_without_docker_the_script_refuses_and_says_so`, `test_a_deploy_points_the_function_at_the_pushed_digest`, `test_the_first_deploy_pushes_and_stops_before_a_function_exists` |

**Red runs** against refuse-nothing skeletons:

- the deploy script as `exit 0` → `17 failed, 3 passed`; the 3 read only the Dockerfile;
- `create_app` returning a bare `FastAPI()` → `9 failed, 4 passed`;
- then green: `33 passed`.

**The image, checked by running it.** `scripts/tub_deploy.sh dev --dry-run` made no AWS call and
took 8 s. It built the image from the cached base image and the public adapter image, read by digest
anonymously. Running the image locally:

- `aarch64`;
- `3.12.15 3.40.0`, which is Python and SQLite, matching ADR-0019 (c) 1's probe;
- `/opt/extensions/lambda-adapter` present;
- `/healthz` → `HTTP/1.1 200`, `cache-control: private, no-store`, `{"status":"ok"}`;
- the page's `<title>Team evidence search</title>`;
- `docker logs` showing uvicorn's start-up lines and no access-log line.

**Run before this report** (agreement 10; `scripts/affected_tests.py` does not exist yet):

- `uv run pytest -q packages/debate_api/tests tests/scripts/test_tub_deploy.py tests/architecture tests/specs packages/debate_core/tests/application/test_settings.py packages/debate_core/tests/application/caselist/test_version_retention_lifecycle.py` → `282 passed, 11 warnings`. The last two read the Terraform files this task changes.
- `uv run ruff format --check .` → `876 files already formatted`; `uv run ruff check .` → `All checks passed!`
- `uv run pyright packages/debate_api` → `0 errors`; `uv run lint-imports` → `12 kept, 0 broken`; `uv run scripts/check_thin_handlers.py` → OK.
- `uv run shellcheck scripts/tub_deploy.sh` → clean; `uv lock --check` → OK.
- `uv run scripts/validate_specs.py` → `OK: 394 files, 39 epics, 334 tasks, 21 releases`.

The 11 warnings are one warning per xdist worker: Starlette 1.9 deprecates `httpx` under its test
client (`StarletteDeprecationWarning ... install httpx2`). It is harmless today; see Follow-up work.

## Files changed

- **`infrastructure/modules/evidence_search/`** (new): the module, its README, its lock file and
  `.tflint.hcl`, and `tests/evidence_search.tftest.hcl`.
- **`infrastructure/envs/{dev,prod}/`**: an identical `evidence_search.tf` and identical additions
  to `variables.tf`, `outputs.tf` and `owner.auto.tfvars.example`. `terraform.tfvars` gains the
  host.
- **`infrastructure/README.md`**: the layout row and a pilot section.
- **`packages/debate_api/`**:
  - `pyproject.toml`: fastapi and uvicorn;
  - `src/debate_api/app.py`: the placeholder app;
  - `tests/test_pilot_placeholder_app.py`;
  - `Dockerfile`;
  - `README.md`.
- **`uv.lock`**: regenerated by `uv lock`. Adds fastapi 0.146.0, starlette 1.9.0, uvicorn 0.54.0,
  opentelemetry-api 1.45.1 (a FastAPI dependency) and annotated-doc.
- **`scripts/tub_deploy.sh`** (new) and **`tests/scripts/test_tub_deploy.py`** (new).
- **`docs/runbooks/evidence-search.md`** (new) and this report.

## Deviations from the spec

The ADR wins where the two differ (PM notes); each difference is recorded here, and the spec is not
edited.

1. **The function's role writes its app log group and reads two parameters.** The spec's
   description says the role writes "only to its audit log group". ADR-0019's role table, which the
   PM amendment adopts, adds the app group (`debate-<env>-tub-app`) and `ssm:GetParameter` on the two
   parameters. Built to the table.
2. **Caching is off for every response, not only signed-in pages.** The spec says "caching off for
   signed-in pages". ADR-0019 (a) 4 gives the distribution one behaviour with the managed
   `CachingDisabled` policy, so nothing is cached at the edge. The app's hashed static assets
   (`v1-e39-t06`) will still be cached by browsers through their own `Cache-Control`.
3. **"No attribute beyond the username" is enforced as far as Cognito allows.** Every pool has
   Cognito's standard attributes (`phone_number` among them) and they cannot be removed. The pool
   declares no schema, so no attribute is required and none is custom. The only attribute the app
   client may read is `email`/`email_verified`, and the only one it may write is `email`. The ac3
   test asserts exactly that.
4. **A third CLI-only setting: the login domain's minimum TLS version.** ADR-0019 (d) puts managed
   login on the custom domain "with a `TLS_V1_2_2021` security policy". Cognito sets it through
   `CustomDomainConfig.SecurityPolicy`. Provider 5.100.0's `aws_cognito_user_pool_domain` has no
   argument for it (checked from the provider's schema), and the AWS CLI 2.27.6 on this Mac does not
   know it either. The spec and the ADR list two such settings, branding and deletion protection.
   Runbook step 5c reads the policy back and sets it with `update-user-pool-domain` if it is not
   `TLS_V1_2_2021`. **This is the PM question below.** I did not stop the session for it, because
   the decision changes one runbook step and nothing else.
5. **Files outside `constraints.packages`.** The constraint is `[infrastructure, scripts,
   docs/runbooks, packages/debate_api]`.
   - `tests/scripts/test_tub_deploy.py` sits where every script's test sits (`test_site_deploy.py`
     beside it).
   - `uv.lock` changed because the PM's own instruction adds two dependencies.
   - This report.

   Proposed spec amendment: add `tests/scripts` and `uv.lock` to `constraints.packages`.

## Decisions and assumptions

- **The first apply in an environment is targeted at the repository.** ADR-0019 (f) 2 says the first
  apply creates the repository and the first deploy pushes an image before the function is created.
  - The function is created from the newest image, read with `data "aws_ecr_image"`
    (`most_recent = true`), and Terraform ignores `image_uri` after that.
  - On a fresh environment that read fails, so the runbook's step 1 is
    `apply -target=module.evidence_search.aws_ecr_repository.function`.
  - The first deploy runs as `debate-admin` through `TUB_DEPLOY_PROFILE`, because the permission
    sets do not exist yet.
  - The deploy script recognises the missing function, says to apply, and exits 0.
  - The alternative was a tfvars toggle that the operator flips between applies. I rejected it,
    because it is a committed value that would differ between environments for a week.
- **"No other grant" is enforced by Terraform.** `aws_iam_role_policies_exclusive` and
  `aws_iam_role_policy_attachments_exclusive` (with `policy_arns = []`) remove any inline or managed
  policy attached to the role out of band, at the next apply.
- **The budget's scope.** Two filter keys, which AWS Budgets ANDs:
  - `Service` in Lambda, CloudFront, Cognito, SES, ECR and CloudWatch;
  - this environment's `Environment` tag.

  This is how the Bedrock budget in `bootstrap/organization` scopes itself. CloudFront also counts
  the website's few cents: an over-count, which is the safe direction. A dedicated cost-allocation
  tag would be exact, but would need activating in Billing first. The address is
  `evidence_search_budget_emails` from `owner.auto.tfvars`, and `owner` when that is empty.
- **The SES identity** is a domain identity for the pilot host. It is verified by Easy DKIM (three
  CNAMEs in the zone), and mail comes from `no-reply@<pilot host>`. Cognito's DEVELOPER mode uses a
  service-linked role it creates at the first apply, so no sending policy is attached. The pool
  `depends_on` the DKIM records, and the runbook says to re-apply if SES has not yet verified them.
- **`TubAccounts`'s actions** are those ADR-0019 (d)'s account lifecycle names, listed one by one:
  - add, list, reset (including `AdminDeleteSoftwareToken`), disable, enable and remove, on its own
    pool;
  - `logs:PutLogEvents` on one stream, `tub-users`, which Terraform creates in the audit group, so
    the set needs no `CreateLogStream`.

  `v1-e39-t05` may need one more action (for example `AdminRemoveUserFromGroup` for a role change);
  it adds it here.
- **`TubDeployer`** may push to its own repository, call `UpdateFunctionCode`, and read
  `GetFunction`/`GetFunctionConfiguration`. `aws lambda wait function-updated` polls the latter, and
  the script reads the pilot's origin from it. `ecr:GetAuthorizationToken` is on `*`, because AWS
  defines no resource for it.
- **The deploy script reads no Terraform state.**
  - It derives `debate-<env>-tub` (ADR-0019 (a) 1), and a test ties that to the module's names.
  - It derives the base image's tag from `requires-python`, which must be `>=X.Y,<X.Y+1`; a wider
    declaration is refused.
  - It takes the CloudFront origin to check from the function's `TUB_PUBLIC_ORIGIN`.
  - Dev may deploy from a dirty tree; the image tag then says `-uncommitted-<time>`.
- **The image.**
  - The build context is a staging directory holding the `uv export` (hashes, no dev, no workspace
    packages) and two wheels built by uv, so nothing else in the checkout can reach the image.
  - pip installs `--require-hashes --only-binary=:all:`.
  - The adapter is pinned to the 1.1.0 index digest
    `sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1`, read anonymously from
    the public registry with `docker buildx imagetools inspect`.
  - The base image follows `requires-python` by tag, as the PM said, and is not digest-pinned.
  - uvicorn binds `0.0.0.0:8080` with `--no-access-log`. `AWS_LWA_PORT` and
    `AWS_LWA_READINESS_CHECK_PATH=/healthz` are set in the function's environment by Terraform, and a
    test ties them to the Dockerfile.
- **The cookie keys' format**, which `v1-e39-t05` must read: a JSON object
  `{"current": "<base64>", "previous": "<base64>"}`, each key 32 random bytes. The placeholder is
  `{"placeholder": "..."}`, which the app must refuse. The runbook writes the keys through a mode-600
  temporary file, so they never sit on a command line or in shell history.
- **Pool details the ADR implies rather than states:**
  - `sign_in_policy` allows `PASSWORD` only, so an emailed code can never replace the password as
    first factor;
  - `explicit_auth_flows` is `ALLOW_REFRESH_TOKEN_AUTH` only ("no password flow");
  - refresh token rotation is written out as `DISABLED`;
  - `auto_verified_attributes = ["email"]`, which Cognito requires for an attribute in
    `attributes_require_verification_before_update`.
- **Derived from the environment, not tfvars:** the prod pool's deletion protection and dev's
  `X-Robots-Tag`. The ADR fixes both per environment, so a tfvars mistake cannot turn either off.
- **The audit group has `skip_destroy`.** A `terraform destroy` forgets the group rather than
  deleting the record of who saw what.
- **The login host gets A and AAAA aliases** to Cognito's distribution, as ADR (a) 6 says for both
  hosts.
- **The placeholder app has no `/auth/callback`.** The PM limited it to `/healthz` and a page.
  Runbook step 10's sign-in therefore ends at FastAPI's `{"detail":"Not Found"}` on the pilot host.
  The runbook says this is expected, and it still shows the redirect reached the function.
- **A mocking limit, written into the test.** In provider 5.100.0, `aws_cloudfront_cache_policy` and
  `aws_cloudfront_origin_request_policy` have a plain optional `id`, which neither `mock_data` nor
  `override_data` fills. So the test asserts the two data sources' names, and its comparison of the
  behaviour's ids is null against null.

## PM questions

```text
PM questions from v1-e39-t04-pilot-infrastructure, 2026-10-19

1. The managed login domain's minimum TLS version. ADR-0019 (d) puts managed login on the custom
   domain "with a TLS_V1_2_2021 security policy". Cognito sets that through
   CustomDomainConfig.SecurityPolicy, and provider 5.100.0's aws_cognito_user_pool_domain has no
   argument for it (checked from the provider schema). ADR-0019 and the spec name two CLI-only
   settings (branding, deletion protection), not this third one.
   Options:
   a) Accept it as a third CLI-only setting: runbook step 4c reads it back with
      describe-user-pool-domain and sets it with update-user-pool-domain when it is not
      TLS_V1_2_2021. This is what the branch does.
   b) Rely on AWS's default for a managed login version 2 domain and drop step 4c.
   c) Move the repository's provider past 5.100.0 for this one argument.
   Recommendation: a). It matches how the other two gaps are handled. The read-back makes the setting
   visible whatever AWS's default is, and c) is the separate change ADR-0019 already defers. If a),
   the ADR's Consequences line about "two settings" wants "three" in a later edit.

2. Closing ac5. Its "measured asset hosts" can only be measured by the operator, on a deployed dev,
   by signing in with the browser's network panel open (runbook steps 1-9). The Goal stays
   InProgress.
   Options:
   a) Merge --partial now. The operator runs steps 1-9 on dev and pastes back the hosts and the step
      7 outputs; a short follow-up commit fills in the runbook's table, sets Succeeded and adds the
      record to this report.
   b) Hold the PR until the operator has run dev.
   Recommendation: a). t05 depends on this task and needs the infrastructure merged, and the
   measurement does not change any code.

3. constraints.packages. The deploy script's test lives in tests/scripts, as every script's does,
   and uv.lock changed because of the two dependencies your notes add. Neither is in
   [infrastructure, scripts, docs/runbooks, packages/debate_api].
   Recommendation: amend the spec to add tests/scripts and uv.lock.
```

## Operator follow-ups

Everything is in [`docs/runbooks/evidence-search.md`](../runbooks/evidence-search.md), in order,
with expected output. Its "Before you start" section covers:

- the `WT` variables and `uv sync --all-packages`;
- the Docker and AWS CLI versions; the CLI needs upgrading on this Mac for step 5a;
- `debate-admin`;
- the three lines for each `owner.auto.tfvars`;
- the Lambda concurrency check.

**Dev, now, from this task's worktree:** runbook steps 1 to 10, with `debate-admin` for steps 1–6. Step 4, the SES production-access request, goes as soon as step 3 has verified the dev SES identity.
The first three, for orientation:

**Operator command** (expected runtime ~2 min)
Where: `debate-intelligence-worktrees/v1-e39-t04-pilot-infrastructure`
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t04-pilot-infrastructure
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev init
terraform -chdir=infrastructure/envs/dev apply -target=module.evidence_search.aws_ecr_repository.function
```
Success looks like: `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.`

**Operator command** (expected runtime ~2 min)
Where: the same worktree
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t04-pilot-infrastructure
TUB_DEPLOY_PROFILE=debate-admin scripts/tub_deploy.sh dev
```
Success looks like: `pushed: ...debate-dev-tub@sha256:...` and `the function debate-dev-tub does not exist yet`.

**Operator command** (expected runtime ~25 min)
Where: the same worktree
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t04-pilot-infrastructure
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev apply
```
Success looks like: the plan reads `Plan: 41 to add, 0 to change, 0 to destroy.`, all under
`module.evidence_search`, with nothing under `module.evidence_store` or `module.site`. After
approving: `Apply complete! Resources: 41 added, 0 changed, 0 destroyed.`

Then steps 4 to 10. **Paste back:**

- step 3's apply summary;
- step 4's `True` and `False	PENDING`, with the date sent;
- the read-backs from 5a, 5b and 5c;
- step 6's `2` and `['current', 'previous'] True`;
- step 8's two `curl` results and its `Init Duration` lines;
- step 10's list of hosts.

Those fill in the runbook's tables and close ac5.

**Prod, after this task is merged and promoted:** runbook step 11. The deploys run from a `main`
worktree. The SES request was step 4, on dev, and covers prod too. Step 12 goes to school IT once
step 10's hosts are recorded.

**No whole-selection run:** the PM's review ruled it unnecessary; CI runs it on the pull request.

**Merging `uv.lock`:** `v1-e01-t28` may add `grimp` to the dev dependencies. Whichever task merges
second regenerates the lock as `docs/process/task-workflow.md` says
(`git checkout --ours uv.lock && uv lock`), never by hand.

## Follow-up work

- **`v1-e39-t05`** inherits from this branch:
  - the cookie keys' JSON format;
  - the environment variables `TUB_PUBLIC_ORIGIN`, `TUB_LOGIN_ORIGIN`, `TUB_USER_POOL_ID`,
    `TUB_CLIENT_ID`, `TUB_CLIENT_SECRET_PARAMETER`, `TUB_COOKIE_KEYS_PARAMETER`,
    `TUB_EVIDENCE_BUCKET` and `TUB_AUDIT_LOG_GROUP`;
  - the `tub-users` audit stream;
  - the `TubAccounts` action list;
  - the duty to enforce PKCE (Cognito does not enforce it for a confidential client).

  It also replaces runbook step 10's CLI account creation with `tub users add`.
- **`v1-e39-t05` or `v1-e39-t06`:** Starlette 1.9 deprecates `httpx` under `TestClient` and asks
  for `httpx2`. A dev-dependency change for whichever task first writes many app tests.
- **ADR-0019's Consequences** say "two settings are runbook steps". If PM question 1 is answered
  a), that becomes three: a small edit to the ADR by the PM or a docs task.
- **ADR-0019 (c) 8's revisit trigger** (a gzipped index above 400 MB) is `v1-e39-t02`'s measurement.
  This task only records the init duration, in runbook step 8.

## PM review follow-through (2026-10-19)

The PM accepted the review on condition that ac5 closes in this session, with no `--partial` merge.

**Done in this round:**

- **SES production access moved to dev.** The request is now runbook step 4, sent as soon as the dev
  apply (step 3) has verified the dev SES identity. The step first reads `VerifiedForSendingStatus`
  and expects `True`. The request text names the prod URL, `https://tub.wfbdebate.com/`, as the
  address the pilot opens at. Sandbox status is per account and Region and the environments share
  one account (ADR-0010), so this request covers prod as well. The old step 11 and the pointer to
  it from the prod apply are gone. The record table has a step 4 row.
- **Renumbering:** inserting step 4 moved the old steps 4–10 to 5–11. The old step 11 is gone and
  step 12 keeps its number. Headings, sub-steps (5a–5c, 11a–11e), anchors, the order table, the
  record table and every cross-reference were renumbered by one script and read back.
  `check_links.py` → `OK: 1818 relative links and anchors`; `check_command_blocks.py --base
  origin/dev` → OK. This report's own sections use the new numbers; the PM questions block keeps
  the numbers it was asked with.
- **Question 1 (a):** as built, runbook step 5c.
- **Question 3:** the PM amends `constraints.packages`; this branch does not edit the spec.
- **No whole-selection run:** removed from the operator follow-ups.

**Not done yet: ac5, the runbook's tables, and the phase.** The PM's message said "with the dev
outputs below", but it carried no outputs. No step of the runbook has been reported as run, so this
round records no measured hosts and no read-backs, and does not set `Succeeded`. The Goal stays
`InProgress` until the operator pastes back the outputs listed under Operator follow-ups. Then this
session:

- fills in the runbook's "The managed login's asset hosts" and "What to record" tables;
- records the outputs in a section here;
- sets the phase `Succeeded`, runs `validate_specs.py`, and commits.

## Dev run, as reported by the operator

**2026-10-19, "Before you start":**

- **A1–A4: done.** The worktree had no `owner.auto.tfvars`; A2 copied them in from the `dev-preview`
  and `prod-deploy` worktrees and checked `owner` against the deployed `Owner` tag. That step was
  added to the runbook in `d08e4ec`, because appending the pilot's lines to an absent file and
  applying would have removed the website's and the evidence store's permission-set assignments.
- **A5:** the pilot's three lines were added to each file (`grep -c` → `3` and `3`; `terraform fmt`
  aligned both files).
- **The Lambda concurrency check returned `10	10`.** The account's "Concurrent executions" quota
  (`L-B99A9384`) is `10.0`, and ADR-0019's reserved concurrency of 10 per environment needs at least
  120, so step 3 cannot create the function yet. An increase to 1,000 was requested: request id
  `1187e55997dc4721b6a9a816aeba97c6H6usQepv`, status `PENDING`. A re-check straight after still read
  `10	10`.
- **The runbook now carries the quota commands.** It says steps 1 and 2 may run meanwhile, and that
  step 3, with step 4 after it, waits for the increase.

**2026-10-19, steps 1 and 2:**

- **Step 1** (the targeted apply): `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.` The
  only new output is `evidence_search_repository_url = "<account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-tub"`;
  every other output is as it was.
- **Step 2** (the first deploy, as `debate-admin`):
  - `requires-python >=3.12,<3.13: public.ecr.aws/lambda/python:3.12`, built from the clean commit
    `e2b30ed`;
  - the build took 6.2 s, with the adapter resolved by its pinned digest;
  - `pushed: <account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-tub@sha256:5bbd667aee32b933367257d513da0f2d1c8ae341068421ef39dca44187dc617b`;
  - then the expected stop: `the function debate-dev-tub does not exist yet`.

**2026-10-19, step 4 ahead of step 3:** the quota was still pending, so the SES identity was
created on its own to start SES's review clock, with
`terraform -chdir=infrastructure/envs/dev apply -target=module.evidence_search.aws_route53_record.ses_dkim`:
`Apply complete! Resources: 4 added, 0 changed, 0 destroyed.` (the identity and its three DKIM
records). The runbook's step 4 now describes this route. The verification check and the
production-access request itself are not yet reported.

**2026-10-19, the SES identity did not verify.** Hours after the targeted apply,
`VerifiedForSendingStatus` was still `False`.

- **SES reported** `DkimAttributes.Status: PENDING` and `VerificationInfo.ErrorType: HOST_NOT_FOUND`.
- **The records are right.** SES's three tokens match the three `_domainkey.tub.dev.wfbdebate.com`
  CNAMEs in Route 53 exactly, so no token rotation or module bug is involved.
- **Public DNS cannot reach them.** Run by the session at 19:40 CDT (read-only, no AWS profile):
  - all three CNAMEs return nothing, from the default resolver and from 8.8.8.8;
  - the `.com` servers answer `NXDOMAIN` for the domain;
  - `whois -h whois.verisign-grs.com wfbdebate.com` shows `Domain Status: clientHold`, `Creation
    Date: 2026-09-20`, `Updated Date: 2026-10-05`, with the four Route 53 name servers still
    listed.

The registrar has suspended the domain's resolution. The 15 days from registration to the hold
match ICANN's registrant-email verification deadline, so an unverified contact email is the likely
cause. The operator was given the `route53domains` commands to check and resend it. **The public
website at `wfbdebate.com` does not resolve either**, probably since 2026-10-05; that is outside
this task and was flagged to the operator at once.

Until the hold is lifted, nothing under `wfbdebate.com` can be validated:

- the SES identity (step 4);
- the ACM certificate, CloudFront and the managed login domain (step 3, which would time out
  waiting for ACM).

**The cause, found by the operator:** `resend-contact-reachability-email` showed the domain's
registrant contact email had been entered with the wrong top-level domain, so the ICANN verification
email could never be confirmed, and the registrar put the domain on hold at the 15-day deadline.
The operator is correcting the address on all three contacts in the Route 53 Domains console,
because `update-domain-contact` needs the whole contact record written out, and then verifying the
new address. Neither address is recorded here.

**Steps 3 and 5–10: not yet run.** They need both the domain hold lifted and the concurrency
increase. Step 3 waits for the concurrency increase, and will plan 37 to
add, not 41. ac5, the runbook's tables
and the `Succeeded` phase wait for steps 3–10.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, on one condition: ac5 closes in this session before the pull request, not by `--partial`
(question 2 below). When the operator has run the runbook's dev steps, the session does three things
in its own sections above this review: records the outputs, fills in the runbook's tables, and sets
the phase `Succeeded`. The pull request then needs no `--partial`.

**The work itself:**

* **Built to ADR-0019,** with every difference from the spec named under Deviations rather than
  silently resolved. The roots differ only in tfvars and backend, as the website's do.
* **The role is checked entry by entry against a hand-written copy of the ADR's table,** and Terraform
  itself removes any policy attached out of band (`*_exclusive`). That is "no other grant" enforced,
  not only tested.
* **Settings the ADR fixes per environment are derived from the environment,** so a tfvars slip
  cannot turn them off: prod deletion protection and dev's noindex.
* **Hardened where the ADR implies rather than states:**
  * `sign_in_policy` is password only;
  * there is no password auth flow;
  * the audit group has `skip_destroy`;
  * the cookie keys are written through a mode-600 file and never sit on a command line.
* **The image was proven by running it:** arm64, Python 3.12.15, SQLite 3.40.0, the adapter present,
  `/healthz` private and no-store, and no access-log line. The build context holds only hashed wheels.
* **The first-apply problem is solved without a committed toggle:** a targeted apply, a deploy that
  recognises the missing function, then the full apply.
* **29 mutants, each caught by an assertion.** That is above agreement 10's cap, but 24 are aimed at
  the role and the pool, which is where I asked for them.

**Rulings:**

1. **Question 1: (a).** The login domain's TLS policy is a third CLI-only setting, with step 4c's
   read-back. The PM corrects ADR-0019's "two settings" to three in the next batch.
2. **Question 2: (b), not (a).** `v1-e39-t05` lists this task as a prerequisite, and `scripts/task
   ready` offers a task only when its prerequisites are `Succeeded`. A `--partial` merge would leave
   t05 blocked until a later close-out, so closing ac5 here is the faster route to t05. The operator
   runs dev steps 1 to 9 from this worktree and pastes the outputs back.
3. **SES production access moves to dev.** Sandbox status is per account and Region, and dev and prod
   share the account (ADR-0010), so the dev identity is enough to ask. The runbook's step 11 moves
   to right after the dev apply has verified the SES identity, with the pilot's prod URL in the
   request. AWS's answer can take up to 96 hours, and prod waits for a promotion, so this starts
   the clock days earlier. Edit the runbook's order and the step's text accordingly.
4. **Question 3:** `tests/scripts` and `uv.lock` are agreed. The PM adds them to
   `constraints.packages` in the next batch, since the deviation is already recorded.
5. **The optional whole-selection run is not needed.** CI runs it on the pull request.
6. **Follow-ups to v1-e39-t05 are agreed as listed:**
   * the cookie-key format;
   * the environment variables;
   * the `tub-users` stream;
   * the `TubAccounts` actions;
   * PKCE enforced by the app;
   * `tub users add` replacing step 9's CLI account creation;
   * the Starlette `httpx2` dev dependency.

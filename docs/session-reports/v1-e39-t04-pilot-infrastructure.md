# Session report: v1-e39-t04-pilot-infrastructure

| | |
|---|---|
| Task | `v1-e39-t04-pilot-infrastructure` — Pilot infrastructure: the function, CloudFront, the user pool and the audit log, in dev and prod |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t04-pilot-infrastructure` |
| Session status | COMPLETE: every criterion passes; dev is applied, deployed and checked; the Goal is `Succeeded`. Prod (runbook steps 11–12) follows the promotion |

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

**Look first at:** [Dev run, as reported by the operator](#dev-run-as-reported-by-the-operator).
Dev is applied, deployed and checked, and ac5's asset hosts are measured. Three things outside the
code held it up:

- the account's Lambda concurrency quota was 10, and was raised to 1,000;
- `wfbdebate.com` was on registrar `clientHold`, which also took the public website offline;
- a provider bug on the app client, fixed in `beafdbe`.

The operator's own run of `scripts/terraform_checks.sh` passed every check, and the Goal is
`Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `infrastructure` | Done; its criterion passes | The module, both roots, the placeholder app, the image, the deploy script and the runbook, all applied and checked on dev |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `infrastructure`: Terraform checks pass | PASS | Before the dev applies: `bash scripts/terraform_checks.sh` → `All Terraform checks passed.` After the grace-period fix (`beafdbe`), in this session: every check `ok` except `validate infrastructure/envs/dev`, which fails with `No valid credential sources found`. The operator's `terraform init` gave that directory the S3 backend, and the session has no AWS credentials. The same configuration validated with `TF_DATA_DIR` in a scratch directory → `Success! The configuration is valid.`; all four module tests and `tflint --recursive` → `ok`. **The operator's run, with credentials, after step 10:** `bash scripts/terraform_checks.sh` → `ok` for fmt, all nine validates (`envs/dev` included), the nine tflint configs, `tflint --recursive` and the four module tests; `All Terraform checks passed.` |
| ac1: checks pass for both roots and the new module; the roots differ only in their tfvars, as the website's do | PASS | As above. `diff -r infrastructure/envs/dev infrastructure/envs/prod -x .terraform -x owner.auto.tfvars` → only `backend.tf` and `terraform.tfvars` differ, as before this task. `evidence_search.tf`, `variables.tf`, `outputs.tf` and `owner.auto.tfvars.example` are identical. `tests/scripts/test_tub_deploy.py::test_the_script_names_the_resources_adr_0019_names` also reads the root's module call |
| ac2: mocked test: evidence buckets keep all four BPA flags; no bucket policy grants CloudFront or the public; the role reads only the three key patterns, writes nothing in the bucket, holds no delete on its log group; the log group keeps 400 days | PASS | `terraform -chdir=infrastructure/modules/evidence_search test` → `Success! 16 passed, 0 failed.` Runs: `evidence_bucket_keeps_block_public_access_and_grants_cloudfront_nothing` plans `../evidence_bucket` with the roots' inputs and asserts the four flags, no `Allow` in the bucket policy and no CloudFront or public principal in the key policy. `cloudfront_reaches_the_function_url_and_nothing_else` asserts the only origin is the function URL. `function_role_is_the_adr_role_table_entry_by_entry` covers GetObject on exactly the three patterns, no other S3 action, and only CreateLogStream/PutLogEvents on the log groups. `audit_log_keeps_four_hundred_days_and_the_app_log_thirty` |
| ac3: mocked test: no self sign-up, TOTP required, email MFA offered, no SMS configuration, no attribute beyond username and optional email | PASS | Same command. `user_pool_admits_only_coach_created_accounts_with_totp`: admin-only creation, MFA `ON`, TOTP enabled, email MFA present, the password as the only first factor, no device remembering. `user_pool_has_no_sms_and_nothing_beyond_a_username_and_an_optional_email`: no `sms_configuration`, no schema block, no username or alias attributes, case-insensitive, email the only auto-verified attribute, client reads `email`/`email_verified` and writes `email` only |
| ac4: the runbook writes out apply dev, deploy a placeholder page that requires sign-in, apply prod, request SES production access, and the web-filter request (hostnames only), with expected output | PASS | [`docs/runbooks/evidence-search.md`](../runbooks/evidence-search.md), steps 1–12 in the PM's order, each with "Success looks like". Step 8 proves the path as the PM defined it: through CloudFront `200 private, no-store`; a direct call to the function URL gets `{"Message":"Forbidden"}`/`403`, Lambda's own refusal. Step 10 renders the managed login at the login host. Step 4 is SES, moved to right after the dev apply by the PM's review; step 12 is the IT text (prod hostnames only). `check_links.py`, `docs_index.py --check-descriptions`, `check_command_blocks.py --base origin/dev` → all OK. Steps 1–10 have since been run on dev, with the outputs in [Dev run](#dev-run-as-reported-by-the-operator) and in the runbook's "What to record" table |
| ac5: the role checked against the role table entry by entry, incl. the app log group, the two SSM parameters and no other grant; the runbook's CLI steps for branding and deletion protection, and the measured asset hosts, written out with expected output | PASS | **The role:** `function_role_is_the_adr_role_table_entry_by_entry` compares every action with every resource against a hand-written copy of the table (`expected_role_table`, app group and both parameters included). `function_role_has_no_other_grant` checks the exclusive-policy resources (one inline policy, zero managed) and the trust policy. On dev, step 9's `simulate-principal-policy` gave the same decisions. **The CLI steps:** runbook steps 5a and 5b, run on dev with read-backs `debate-dev-tub-audit 400 True` and `True`. **The measured asset hosts:** runbook step 10, measured on dev on 2026-10-19 over a first and an ordinary sign-in. They are `auth.tub.dev.wfbdebate.com`, `dnh6qh3zeqkj3.cloudfront.net`, `d14wtojjlkahd9.cloudfront.net` and `d2gc27jy00o0yk.cloudfront.net` (plus the callback on `tub.dev.wfbdebate.com`), now in the runbook's table, with step 12 confirming them on prod's login page before the IT request |

Every criterion passes, and the Goal is `Succeeded` (`uv run scripts/task_helper.py set-phase v1-e39-t04-pilot-infrastructure Succeeded`; `validate_specs.py --require-succeeded` → `Succeeded`).

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

**Dev is done.** Runbook steps 1–10 were run on 2026-10-19 and are recorded under
[Dev run](#dev-run-as-reported-by-the-operator). The SES production-access request was step 4; it
covers prod too, and the account is already out of the sandbox.

**Next: sync with `dev`.** `v1-e01-t28` merged first, and both tasks change `uv.lock`. Run
`scripts/task sync v1-e39-t04-pilot-infrastructure`. If the rebase stops on `uv.lock`, resolve it
with `git checkout --ours uv.lock && uv lock && git add uv.lock`, then `git rebase --continue`
(`pyproject.toml` first, if it conflicts too; this branch changes only `debate_api`'s). After the
sync, the session runs:

- `uv run scripts/affected_tests.py --run`, which should run nothing and say CI covers it, since a
  lock change selects the whole suite;
- `uv lock --check`;
- `scripts/terraform_checks.sh`. In this worktree the session's run fails `validate
  infrastructure/envs/dev` on credentials, so the operator runs it, as after step 10.

**Prod, after this task is merged and promoted:** runbook step 11, with the deploys from a `main`
worktree. Then step 12:

- confirm the three CloudFront hosts on prod's login page;
- send the request to school IT.

**No whole-selection run:** the PM's review ruled it unnecessary; CI runs it on the pull request.

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

**Then: ac5, the runbook's tables, and the phase.** The PM's message said "with the dev outputs
below" but carried none, so that round recorded nothing and set nothing. The operator then ran dev
steps 1–10 over the evening of 2026-10-19; the next section records each. The runbook's two tables
are filled in, and ac5 is closed. The operator's run of `scripts/terraform_checks.sh` passed, and
the phase is `Succeeded`.

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
The operator corrected the address on all three contacts in the Route 53 Domains console, because
`update-domain-contact` needs the whole contact record written out, and then verified the new
address: `get-contact-reachability-status` → `"status": "DONE"`, with `clientHold` still in the
domain's status list straight afterwards. At 19:50 CDT the registry still showed `clientHold` and
`NXDOMAIN`. The session is polling the `.com` servers until the domain is delegated again. Neither
address is recorded here.

**The concurrency quota was raised.** `get-requested-service-quota-change` → `CASE_CLOSED`, and
`get-account-settings` → `1000	1000`. At 19:52 CDT the domain was still on `clientHold`.

**The hold lifted at 20:15 CDT.** The session's poll of `a.gtld-servers.net` found the domain
delegated again to the four Route 53 name servers, and the registry whois read
`Domain Status: ok`. At 20:16 CDT, from public DNS:

- `dev.wfbdebate.com` resolves;
- all three DKIM CNAMEs resolve to their `dkim.amazonses.com` targets;
- `https://wfbdebate.com/` answers `200`.

**2026-10-19, step 4 (SES production access).**

- After a fresh SSO sign-in, `VerifiedForSendingStatus` read `True`, once the domain resolved again.
- `put-account-details` was sent the same evening, with the prod URL and the coach as contact.
- `get-account` then read `True	PENDING`. The review is pending; the first value was not the
  runbook's expected `False`. The runbook now reads the sandbox state from `SendQuota` instead,
  and that read-back is awaited.
- The read-back: `get-account --query '[SendQuota.Max24HourSend,SendQuota.MaxSendRate,EnforcementStatus]'`
  → `50000.0	14.0	HEALTHY`. The account is already out of the SES sandbox, so the `True` was
  real.

**2026-10-19, step 3, first attempt.**

- After a fresh sign-in the plan read `Plan: 37 to add, 0 to change, 0 to destroy.` (the SES
  identity and DKIM records were already there), all under `module.evidence_search`.
- 22 resources were created: the pool, the groups, the log groups and stream, the role, the
  certificate and its validation, the permission sets and assignments, the budget, and the rest.
- The apply then stopped on `aws_cognito_user_pool_client.web`, with `Provider produced inconsistent
  result after apply ... .refresh_token_rotation[0].retry_grace_period_seconds: was null, but now
  cty.NumberIntVal(0)`. This is a provider 5.100.0 bug: AWS reports the grace period of a disabled
  rotation as 0.

The fix, on this branch, writes `retry_grace_period_seconds = 0` in the module, and
`app_client_is_confidential_code_flow_only` asserts it. Without the line the run fails
(`15 passed, 1 failed`); with it, `16 passed`. `scripts/terraform_checks.sh` → **one failure**, `validate
infrastructure/envs/dev`, with `No valid credential sources found`. The operator's `terraform init`
gave this worktree's `envs/dev` the S3 backend, so its `init -backend=false` now reaches for state,
and the session has no AWS credentials. Every other check in the script passed. The same
configuration, validated with `TF_DATA_DIR` pointing at a scratch directory, gives
`Success! The configuration is valid.` The operator's `.terraform` was not modified (its state
file keeps its 12:27 timestamp). An earlier commit of this report (`beafdbe`) said the script
passed; it did not, and this paragraph replaces that line.

**2026-10-19, step 3, second attempt (with the fix):**

- `Apply complete! Resources: 15 added, 0 changed, 1 destroyed.` Terraform had recorded the failed
  client as tainted and replaced it, so the 22 resources from the first attempt and these 15 make
  the plan's 37.
- Outputs include `evidence_search_url = "https://tub.dev.wfbdebate.com/"`,
  `evidence_search_login_host = "auth.tub.dev.wfbdebate.com"` and
  `evidence_search_function_name = "debate-dev-tub"`.
- `list-user-pool-clients` lists exactly one client, `debate-dev-tub-web`, whose id equals the
  `evidence_search_client_id` output, so no orphan client was left behind.

**2026-10-19, step 5 (the three CLI-only settings):**

- **5a:** `put-log-group-deletion-protection` printed nothing; the read-back is
  `debate-dev-tub-audit	400	True`.
- **5b:** `create-managed-login-branding` returned a branding id (a UUID);
  `UseCognitoProvidedValues` reads `True`.
- **5c:** `describe-user-pool-domain` → `ACTIVE	2	TLS_V1_2_2021` at the first read-back, so the
  `update-user-pool-domain` fallback was not needed. AWS's default for a managed login version 2
  custom domain is already `TLS_V1_2_2021`, and the step stays as a read-back.

**2026-10-19, step 6 (the cookie keys):** `put-parameter` → `2`, and the check printed
`['current', 'previous'] True`, without printing either key.

**2026-10-19, step 7 (the permission-set profiles):** after `aws sso login`, the two dev profiles
resolve to `assumed-role/AWSReservedSSO_DebateDevTubDeployer_…` and
`assumed-role/AWSReservedSSO_DebateDevTubAccounts_…`. The prod pair is configured, and works once
prod is applied.

**2026-10-19, step 8 (deploy as TubDeployer; the path through CloudFront):**

- **The deploy:** `scripts/tub_deploy.sh dev` ended
  `Deployed 47bf8a25b66a6835226e3fdedda48b50cf6640ed to dev: https://tub.dev.wfbdebate.com/`, with
  the function on `<account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-tub@sha256:7ddc815bbda13a5e60676abfaa3514f299bb66366ae8661f067b68bb2cbd0e9a`.
- **Through CloudFront:** `200 private, no-store` and `<title>Team evidence search</title>`.
- **The headers:**
  - `content-security-policy: default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self' https://auth.tub.dev.wfbdebate.com`
  - `strict-transport-security: max-age=31536000; includeSubDomains`
  - `referrer-policy: no-referrer`
  - `x-frame-options: DENY`
  - `x-content-type-options: nosniff`
  - `x-robots-tag: noindex, nofollow`
- **Direct calls to the function URL** (`/healthz` and `/`): `{"Message":"Forbidden"}` / `403`
  both times. That is Lambda's own refusal, from before the function runs; the app never answers
  403.
- **Cold starts from the `REPORT` lines (ADR-0019 (c) 7):**
  - `Init Duration: 4115.24 ms` (the first environment after the deploy, pulling the new image);
  - `Init Duration: 1848.35 ms` (within the ADR's expected 1–2 s);
  - `Max Memory Used` 81–82 MB of 2,048 MB.

**2026-10-19, step 9 (least privilege, `simulate-principal-policy`):** every decision as expected.

- **The function's role:**
  - `allowed`: `s3:GetObject` on `reports/tub/search/current.json`, `raw/example/file.docx` and
    `manifests/_suppression/suppression-list.jsonl`; `logs:CreateLogStream` and
    `logs:PutLogEvents` on the audit group; `ssm:GetParameter` on the cookie-keys parameter.
  - `implicitDeny`: `s3:GetObjectVersion`, `s3:PutObject` and `s3:DeleteObject` under `raw/`;
    `s3:GetObject` under `parsed/`; `s3:ListBucket`; `logs:DeleteLogGroup`, `logs:DeleteLogStream`
    and `logs:PutRetentionPolicy`; `cognito-idp:AdminCreateUser` and `cognito-idp:ListUsers`.
  - No attached managed policy.
- **TubDeployer:**
  - `allowed`: `lambda:UpdateFunctionCode` on `debate-dev-tub`.
  - `implicitDeny`: the same action on `debate-prod-tub`; `lambda:UpdateFunctionConfiguration`,
    `iam:PassRole` and `s3:GetObject`.
- **TubAccounts:**
  - `allowed`: `cognito-idp:AdminCreateUser` on the dev pool.
  - `implicitDeny`: `cognito-idp:AdminInitiateAuth` and `cognito-idp:AdminUpdateUserAttributes`.

ADR-0019's role table is thus confirmed against AWS's own evaluation, not only the mocked test.

**2026-10-19, step 10 (sign-in on dev; the managed login's asset hosts):**

- `admin-create-user` under `debate-dev-tub-accounts` created the maintainer's dev account, in the
  `coach` group. Its name is not recorded; it is the maintainer's, not a student's.
- The managed login rendered at `auth.tub.dev.wfbdebate.com`. The first sign-in went through the
  password change and authenticator setup and reached the callback page,
  `{"detail":"Not Found"}` on `tub.dev.wfbdebate.com`, as expected until `v1-e39-t05`.
- The hosts were captured over a first and an ordinary sign-in, the second in an Incognito window,
  with the Network panel exported to HAR. A Python block listed each distinct host, what it served
  and what loaded it, then deleted the HAR files (`grep -c` → `0`).
- **The managed login's hosts:**
  - `auth.tub.dev.wfbdebate.com`: document, fetch;
  - `dnh6qh3zeqkj3.cloudfront.net`: script, stylesheet;
  - `d14wtojjlkahd9.cloudfront.net`: stylesheet;
  - `d2gc27jy00o0yk.cloudfront.net`: image;
  - `tub.dev.wfbdebate.com`: the callback document.
- **Excluded:** `ogs.google.com`, `www.gstatic.com`, `fonts.gstatic.com`, `ssl.gstatic.com`,
  `lh3.googleusercontent.com`, `play.google.com` and `accounts.google.com`. Every one traced back
  to `ogs.google.com`, the account widget of Chrome's new-tab page, so none is the login's.

**What changed in the runbook as a result:**

- Step 10 now uses Incognito windows and the HAR listing, because the Domain-column method proved
  hard to follow and logged the new-tab page.
- Step 12 confirms the three CloudFront hosts on prod's login page before the request (AWS does not
  say whether they are the same for every pool), and its text lists all five hostnames.
- The asset-host and "What to record" tables are filled in for dev.

**After step 10, in this session:**

- `uv run pytest -q tests/specs tests/architecture tests/scripts/test_tub_deploy.py packages/debate_api/tests`
  → `214 passed`.
- `uv run scripts/validate_specs.py` → OK.
- `check_links.py`, `docs_index.py --check-descriptions` and `check_command_blocks.py --base
  origin/dev` → OK.
- `scripts/terraform_checks.sh` → one failure, `validate infrastructure/envs/dev`, on credentials,
  as described in the node row. Step 3 waits for the concurrency increase, and will plan 37 to
add, not 41. ac5, the runbook's tables
and the `Succeeded` phase wait for steps 3–10.

## Sync with dev (2026-10-19)

`v1-e01-t28` merged into `dev` first, and both tasks change `uv.lock`.

- **The rebase:** the operator ran `scripts/task sync v1-e39-t04-pilot-infrastructure` →
  `Successfully rebased and updated refs/heads/task/v1-e39-t04-pilot-infrastructure.` It did not
  stop: git merged the two lock changes itself, so the PM's `git checkout --ours uv.lock && uv lock`
  resolution was not needed. The branch now sits on `origin/dev` at `cd69a3d`.
- **The lock:** `uv lock --check` (run bare) → `Resolved 116 packages`, exit 0. It holds dev's
  `grimp`, and against `origin/dev` this branch adds only `fastapi`, `starlette`, `uvicorn` and
  `opentelemetry-api`.
- **The environment:** `uv sync --all-packages` reinstalled `debate-api` only.
- **The affected tests:** `uv run scripts/affected_tests.py --run` → `The whole selection is affected:
  packages/debate_api/pyproject.toml is shared test ground. CI runs it on the pull request; a session
  does not (working agreement 10).` Exit 0, nothing run.
- **The cheap whole-repo checks:**
  - `uv run lint-imports` → `12 kept, 0 broken`;
  - `uv run pytest -q tests/architecture tests/specs` → `181 passed`;
  - `validate_specs.py` → OK, and `--require-succeeded v1-e39-t04-pilot-infrastructure` →
    `Succeeded`;
  - `ruff check .` → `All checks passed!`; `ruff format --check .` → `899 files already formatted`;
  - `pyright packages/debate_api` → `0 errors`.
- **The Terraform checks:** the operator, with credentials, ran `bash scripts/terraform_checks.sh` →
  `ok` for all 24 checks, `All Terraform checks passed.`

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

## PM review, second

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

The first review's condition is met. ac5 closed in this session: dev steps 1 to 10 are recorded,
the runbook's tables are filled in, the phase is `Succeeded`, and the branch is synced onto `dev`
with the operator's `scripts/terraform_checks.sh` passing all 24 checks. The pull request needs no
`--partial`.

**What the dev run proved, beyond the mocked tests:**

* **Least privilege, by AWS's own evaluation.** `simulate-principal-policy` agrees with ADR-0019's
  role table for the function and for both permission sets, including the denials.
* **The path.** Through CloudFront the page is `200 private, no-store` with every header the ADR
  names. A direct call to the function URL gets Lambda's own `403` before the function runs.
* **The cold start:** 1.8 s for an ordinary environment, inside the ADR's 1 to 2 s; 4.1 s for the
  first after a deploy.
* **SES is already out of the sandbox,** so emailed codes are not waiting on AWS.
* **The asset hosts for school IT are measured,** with Chrome's own new-tab traffic traced and left
  out. Step 12 re-confirms them on prod before the request goes.

**Three problems outside the code, each handled and written into the runbook:**

* **The Lambda concurrency quota (10) was raised to 1,000.** The runbook now checks it first.
* **The registrar's `clientHold` on `wfbdebate.com`,** caused by a mistyped registrant email, had
  taken the public website offline as well, probably since 2026-10-05. The session diagnosed it from
  public DNS and whois, the operator corrected the contacts, and the hold lifted at 20:15 CDT.
* **A provider 5.100.0 bug on the app client** (`retry_grace_period_seconds`) is fixed in the module
  and pinned by a test.

**The step 5c read-back** found AWS's default already `TLS_V1_2_2021`, so the step stays as a
check, as ruled. The report's own correction of `beafdbe`'s claim that the checks had passed is the
right instinct.

**Prod** (runbook steps 11 and 12) follows the promotion, as the runbook says.

# Session report: v1-e05-t08-bedrock-invoke-access

| | |
|---|---|
| Task | `v1-e05-t08-bedrock-invoke-access` — A profile that may call Bedrock, and the model access its first call needs |
| Spec | [`plan_specs/v1/e05-model-router/t08-bedrock-invoke-access.yaml`](../../plan_specs/v1/e05-model-router/t08-bedrock-invoke-access.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t08-bedrock-invoke-access` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task adds a credential a model call can use.

- **The permission set.** `Debate<Env>BedrockInvoker`, one per environment, holds `bedrock:InvokeModel` and nothing else. It covers exactly the fourteen resources t02's report lists, and it reads them from the two routing files rather than from a list written in Terraform. The Claude models are granted only through the three `us.` profiles (`bedrock:InferenceProfileArn`).
- **Where it lives.** A new module, `infrastructure/modules/bedrock_access`, called from both environment roots. The roots gain a module call, a variable and two outputs, and nothing existing changes.
- **The setting.** `models.aws_profile` names `debate-dev-bedrock` and `debate-prod-bedrock` in the bundled profiles. The Bedrock client is built on a botocore session that reads no profile from the environment, so `AWS_PROFILE` can no longer decide which role a call runs as. `build_model_router` passes the profile to the real router itself, so no composition root can leave it out.
- **doctor.** `doctor --evidence-profiles` reports the profile on a `Model profile` row, in the same words as the evidence profiles. It never fails on that row: Decision 3.
- **The runbook.** [`docs/runbooks/bedrock-access.md`](../runbooks/bedrock-access.md) gives the plan, a plan check, the apply, the profile, the account's one-time model access, the policy's question 4 steps and the first call.

**The Goal stays `InProgress`.** ac4 (the PM reads the plans, then the dev apply and t02's probe) and ac5 (the first real call on each Claude route) are operator steps after the apply, so this merges `--partial`. Everything a session can run passes. That includes the module tests, which were shown failing first, 20 of 20 Terraform mutants, and 10 of 10 Python mutants.

**Look at first:** Deviation 1 (a new module rather than the evidence module) and Decision 2 (dev's set reaches Opus too). Then the relay prompt under Operator follow-ups: three questions, with my recommendation on each.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `invoke-access`: the permission sets, the setting, the runbook and the operator's probe | Done, except the operator's runs | The module and its tests (red first), the roots, the setting, the client, the probe, doctor and the runbook. The probe's real run is ac5, an operator step |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: one permission set per environment holding `bedrock:InvokeModel` on exactly the listed resources, with the inference-profile condition on the foundation models, held by the module's Terraform tests and shown failing first | PASS | **Red first.** I ran the tests against a skeleton module that granted `bedrock:*` on `*`: `terraform -chdir=infrastructure/modules/bedrock_access test` → `Failure! 6 passed, 3 failed`. Four assertions failed: the action list, the fourteen resources, prod's fourteen, and the one-route file. **Green:** `Success! 9 passed, 0 failed` (about 1 s). **Mutants:** 20 of 20 caught (table below), each run a clean assertion failure with 0 skipped. **Repo-wide:** `TF_CLI_CONFIG_FILE=<offline mirror> bash scripts/terraform_checks.sh` → `All Terraform checks passed.` (30 ok, 33 s, lock files unchanged). `terraform validate` passes in both roots |
| ac2: `models.aws_profile` has a value in each bundled profile; the Bedrock client is built from it and never from `AWS_PROFILE`; doctor's evidence-profile check reports it in the same words, by tests | PASS | **Red first.** Over the new and changed test files: `25 failed, 98 passed, 10 errors`. Every reason was the missing setting or parameter, and one was today's behaviour: `assert 'KEY-OF-THE-SHELL' == 'KEY-OF-DEFAULT'`, a client signed with the shell's `AWS_PROFILE`. The doctor tests' red: `4 failed`, the profile not reported. **Green:** the same files `136 passed`; doctor, profile-check and s3 `197 passed`. The tests that pin it: `test_settings_model_profile.py` (7 tests, including the committed name against the root's `name_prefix`); `test_the_client_is_signed_with_the_profile_it_is_given_and_not_the_one_aws_profile_names`, `test_with_no_profile_the_client_ignores_aws_profile`, `test_an_aws_profile_the_config_lacks_changes_nothing`, `test_the_real_router_is_built_with_the_settings_aws_profile`; and the four `model` tests in `test_doctor_evidence_profiles.py` |
| ac3: the runbook gives the profile's configuration, the account's one-time model-access steps, and the plan, apply and check commands | PASS | [`docs/runbooks/bedrock-access.md`](../runbooks/bedrock-access.md): Before you start, Steps 1 to 3 (plan, plan check, apply), 4 (profile), 5 (use-case form and model availability), 6 (open question 4), 7 (the first call), and Prod. `uv run python scripts/check_command_blocks.py` → `OK: no # comments in 500 shell code blocks in 169 Markdown files`. `docs_index.py --check-descriptions` → `All 51 indexed documents under docs/ have a description` |
| ac4: operator-run: the PM reads the dev and prod plans before apply; after the dev apply, t02's probe runs with the new profile and its tables are recorded in t02's report | NOT RUN | Needs the operator's credentials, an apply and the PM's reading, so no session can close it. Runbook Steps 1 to 3 and 7. Recording the tables in t02's report is the next session's: Follow-up work |
| ac5: operator-run with the new profile: the first real call on each Claude route, recorded here; t02's Stubber tests pin each answer | NOT RUN | Runbook Step 7, after the dev apply. The probe is ready: it signs with `models.aws_profile`, asks each model once, masks account ids and counts the tokens it is billed. The Stubber tests that pin the answers are written after the run (Follow-up work) |
| Node: `terraform test` in the evidence module's directory passes, and `uv run pytest packages/debate_core/tests -k 'settings or bedrock'` passes | PASS | Run in the new module's directory (Deviation 1): `Success! 9 passed, 0 failed`. `.venv/bin/python -m pytest packages/debate_core/tests -k 'settings or bedrock' -n 8` → `315 passed in 44.68s` |

### Terraform mutants (ac1)

Each mutant was run as `terraform test` over the whole file. Each one ended with `N passed, 1-3 failed, 0 skipped`, so every catch is a failed assertion and none is an error. The validation mutant is caught by `Missing expected failure`, and Terraform then skips the rest of the file.

| # | Mutant | Caught by |
|---|---|---|
| 1 | the profiles' statement also allows `InvokeModelWithResponseStream` | the action list |
| 2 | the models-behind-profiles statement allows `bedrock:*` | the action list |
| 3 | the direct models' statement allows `bedrock:InvokeModel*` | the action list |
| 4 | an extra statement: `bedrock:ListFoundationModels` on `*` | the resources, prod's count, the one-route file |
| 5 | us-west-2 dropped from a profile's regions | the resources, prod's count, the one-route file |
| 6 | us-west-1 added | the same three |
| 7 | the models behind profiles wildcarded (`foundation-model/*`) | the same three |
| 8 | a profile in any account (`:*:inference-profile/`) | the resources, the one-route file |
| 9 | the direct models in any region | the resources |
| 10 | the scoring models treated as behind a profile (three regions) | the resources, prod's count |
| 11 | the profiles not de-duplicated across the two files | the resources, prod's count |
| 12 | the first routing file only (dev's: no Opus) | the resources, prod's count |
| 13 | the condition dropped | the condition |
| 14 | `StringLike` for `StringEquals` | the condition |
| 15 | the wrong condition key (`aws:SourceArn`) | the condition |
| 16 | the condition naming the models' own ARNs | the condition |
| 17 | the condition put on the profiles too | "the profiles carry no condition" |
| 18 | `NotResource` beside `Resource` | "plain Allow, no NotAction or NotResource" |
| 19 | the empty-statement filter removed | "a statement with nothing to grant is left out" |
| 20 | the geography validation disarmed | `a_profile_outside_the_us_is_refused` (`Missing expected failure`) |

### Python mutants

| # | Mutant | Caught by |
|---|---|---|
| 1 | the client's session reads `AWS_PROFILE` again | `test_with_no_profile_the_client_ignores_aws_profile` |
| 2 | the client drops its profile | `test_the_client_is_signed_with_the_profile_it_is_given_and_not_the_one_aws_profile_names` |
| 3 | the router's default factory has no profile | `test_the_router_builds_each_client_with_its_profile` |
| 4 | `build_model_router` passes no profile | `test_the_real_router_is_built_with_the_settings_aws_profile` |
| 5 | the probe ignores the setting's profile | `test_first_call_takes_its_profile_and_routing_file_from_settings` |
| 6 | the probe asks each route, not each model | `test_first_call_probes_each_model_once_however_many_routes_name_it` |
| 7 | a blank profile is kept | `test_a_blank_value_is_no_profile[]` |
| 8 | doctor fails on the model profile | `test_a_model_profile_the_aws_config_lacks_is_reported_with_its_fix_and_fails_nothing` |
| 9 | the container leaves the model profile out | `test_the_model_profile_is_reported_in_the_same_words_under_its_own_setting` |
| 10 | the probe table's account-id mask removed | `test_first_call_table_masks_the_account_id_bedrocks_refusal_names` |

Each was run against its own test files with `-n 0 -p no:randomly` and a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests use Hypothesis). I read `git status` after the run: clean.

### Checks before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `361 of 504 test files (71.6%) chosen in 7.8 s from 41 changed files`. The root conftest imports `settings.py`, which changed. That is well over two minutes, so under agreement 10 (and the PM's note for this task) the affected set is the pull request's `ci`, not a hand-off |
| The changed test files and the always-run list: `.venv/bin/python -m pytest -n 8 -m "not slow and not live"` over `test_settings*.py`, `test_evidence_profiles.py`, `integrations/{bedrock,models,s3}`, the four doctor and installation files, `test_runbook_reinstall_runs_the_profile_check.py`, `tests/smoke/test_cli_smoke.py`, `tests/integration/test_launchd_install.py`, `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `tests/docs` and the two docs-script tests | `1635 passed in 103.77s`. An earlier run that also included all of `packages/debate_core/tests/application` stopped at the 115 s alarm at 77%, with no failure up to there |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1402 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli tests/smoke` (after the last format) | `0 errors, 0 warnings, 0 informations` (22 s) |
| `uv run --frozen lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 62 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 464 files, 40 epics, 402 tasks, 22 releases` |
| The installed-build branch of the two smoke checks | Not run here: it runs in `validate-dev` against the next pre-release. On a checkout the console script reads the built-in profiles, which name no model profile (Decision 4) |

## Files changed

- **`infrastructure/modules/bedrock_access/`** (new): the permission set, its policy and assignment, read from the routing files; the tests, with two synthetic routing files; the README, the lock file copied from a sibling module, and `.tflint.hcl`.
- **`infrastructure/envs/{dev,prod}/`**: `bedrock_access.tf` (identical in the two roots), the `bedrock_invoker_user_names` variable, two outputs, and the `owner.auto.tfvars.example` line. **`infrastructure/README.md`**: the module row and a section.
- **`config/profiles/{dev,prod}.toml`**: `models.aws_profile`.
- **`debate_core.application`**: `settings.py` (`ModelSettings.aws_profile`, where blank means none) and `evidence_profiles.py` (`MODEL_PROFILE_SETTING`, a docstring).
- **`debate_core.integrations`**:
  - `bedrock/router.py`: the profile-only session, and `aws_profile` on the router.
  - `bedrock/__init__.py`: `bedrock_model_router(aws_profile=...)`.
  - `bedrock/failures.py`: the hints name `models.aws_profile` and the runbook.
  - `bedrock/first_call.py`: several routing files, each model once, the profile from settings, token totals, masked account ids.
  - `models/factory.py`: `RealRouterFactory` takes `aws_profile`, and `build_model_router` passes the setting.
  - `s3/errors.py`: a model profile the AWS config lacks is pointed at this runbook.
- **`packages/debate_core/tests`**: `test_settings_model_profile.py` (new); `test_router.py` (client, router and probe tests); `test_factory.py` (the spy takes the profile, two tests, and the pinned `ModelSettings` field list).
- **`debate_cli`** (Deviation 2): `container.py` adds the model profile to the check. `commands/doctor.py` gives it the `Model profile` label, its row's fix, its docstring and help, and the rule that it fails nothing. `README.md`, and `tests/commands/test_doctor_evidence_profiles.py` (four tests).
- **`tests/smoke/test_cli_smoke.py`** (Deviation 2): an installed build's dev profile now reports the model profile beside the everyday one, and `config show` names both profiles.
- **`docs/runbooks/`**: `bedrock-access.md` (new); `caselist-scheduled-sync.md` (one paragraph: the new row never changes the exit code).

## Deviations from the spec

1. **A module of its own rather than the evidence module.** The spec puts the set "in the Terraform root that already holds the evidence permission sets", which I did: both environment roots. The node's criterion names "the evidence module's directory". I wrote a new module, `bedrock_access`, and ran that criterion in its directory. My reasons:
   - Every permission set here lives in the module for its purpose (`caselist_run`, `evidence_search`, `static_site`). A Bedrock grant in `evidence_bucket` would describe nothing in that module.
   - A new module is what lets the plan touch nothing else by construction. The only change to existing files is a module call, a variable and two outputs, and the runbook's plan check enforces it on the real plan.

   If the PM wants it inside `evidence_bucket`, the move is mechanical: one `moved` block per resource, before the first apply or after.
2. **Files outside `constraints.packages`.** ac2's "doctor's evidence-profile check reports it" can only be met in `debate_cli`: the container builds the check's profile list, and doctor renders and fails it. So `container.py`, `doctor.py`, the CLI README and the doctor tests changed. The installed-build smoke check in `tests/smoke/test_cli_smoke.py` pins the bundled dev profile's findings whole, so it changed too.
3. **The probe asks each model once.** The PM asked for "one call per Claude route". I read that as one probe per Claude target across both routing files. The probe now takes several `--routing-file`s and de-duplicates routes by inference profile and region, so one run asks the three Claude models seven requests each, plus one embedding and one rerank: 23 requests where t02's runbook made 46. One request per route cannot answer ac5's questions (which `toolChoice` types, structured output, temperature, `strict`), since each is a separate request. Requests Bedrock refuses as invalid are refused before the model runs. The runbook gives the cost: under ten cents at Anthropic's list prices with 300 output tokens a request, and about 45 cents with every request at its 2,048-token cap. Question 2 in the relay prompt.

## Decisions and assumptions

1. **The grant is read from the routing files, not written in Terraform.** The module `yamldecode`s the files the root names, so "a resource the routing files do not name" cannot be granted. Its tests pin the fourteen resources the committed files name, written by hand from t02's report. A routing change is therefore a grant change that fails those tests and shows in the next plan of both roots. The regions behind a `us.` profile (us-east-1, us-east-2, us-west-2, from v1-e05-t01's report) are the one list written in the module. A profile of any other geography is refused by a validation rather than granted on regions nobody checked.
2. **Both roots grant what both files name, so dev's set can call Opus 5.5,** which only prod's routes use. There is one account (ADR-0010), so separating the two grants would separate nothing. And the first call on each Claude route (ac5) is made after the dev apply, with dev's profile, before prod is applied. Dev's calls still go through dev's routing file and dev's $2 daily budget. Question 3 in the relay prompt.
3. **A model profile that is not defined is reported and never fails doctor.** `doctor --evidence-profiles` is what the weekly run's `--check` and `install.sh --check-launchd` run before a pull, and no command calls a model yet. Failing there would block the fallback week's pull for a profile the pull does not use. Its row carries the fix, since no failure panel will. When a model stage joins the weekly run, the rule should flip: one line in `_profiles_not_defined`. Question 1 in the relay prompt.
4. **`models.aws_profile` is in the bundled profiles only, not in `_builtin_profiles`.** "A value in each bundled profile" is the spec's wording, and every build ships `config/profiles`. Adding it to the built-in defaults as well would put a model profile into every CLI test that writes its own `dev.toml`, and those tests pin their profile lists whole. A wheel without its bundled configuration names no profile, and gets the credential chain without `AWS_PROFILE`. `test` names none either: it routes to the fake.
5. **No profile means the chain without `AWS_PROFILE`,** not the chain with it. The spec's "never from `AWS_PROFILE`" applies to the unset case too: environment keys, the config's default, or a task or instance role. `DEBATE_MODELS__AWS_PROFILE=` (blank) is how a cloud task with its own role will say so, as it does for the bucket.
6. **`RealRouterFactory` became a Protocol** taking `aws_profile` as a keyword, and `build_model_router` passes `settings.models.aws_profile`. Binding the profile into `bedrock_router_factory` instead would let a composition root forget it. Only the test spy needed changing.
7. **The probe masks 12-digit numbers as `<account-id>`.** Bedrock's AccessDenied names the caller's role and the resource by ARN, and the table goes into this report. The probe also counts the input and output tokens of its accepted requests, so the cost is measured rather than estimated.
8. **The permission set's session is eight hours**, the same as `EvidenceOperator`: a working day, since a model run may be long.
9. **The model-availability check in Step 5** uses `aws bedrock get-foundation-model-availability`. I have not run it, because AWS calls are the operator's. If the operator's CLI lacks it, the runbook says to skip it and read the probe's refusals, which name a missing subscription.
10. **The mock account `111122223333`** in the module's tests is AWS's documentation example, as in the other module tests. It is not the account's id. No account id, ARN with an account id, or SSO start URL is in any committed file: a scan of the branch's added lines finds only that example.

## Operator follow-ups

All of this is in [`docs/runbooks/bedrock-access.md`](../runbooks/bedrock-access.md), in order. Run each block as written there:

1. **Before you start** (about 3 min): the worktree `caselist-credentials-dev` at `origin/dev` with this task merged. The check reads the cutover's step 9 as done (`true`); a `false` stops you. Then sign in as `debate-admin`, and add the one `owner.auto.tfvars` line.
2. **Steps 1 and 2** (about 3 min): the dev plan, then the plan check. Expect `Plan: 3 to add, 0 to change, 0 to destroy.` and `PLAN OK: 3 to create, nothing else; bedrock:InvokeModel on 14 resources, 9 Claude models through the 3 profiles`. **Send the PM the plan (`/tmp/bedrock-access-dev-plan.txt`) and the check's line.**
3. **Step 3, after the PM's word** (about 1 min): the apply. Expect `Resources: 3 added, 0 changed, 0 destroyed.`
4. **Step 4** (about 2 min): the profile, then `doctor`'s `Model profile` row.
5. **Step 5** (about 5 min, console): the Anthropic use-case form, and the read-only availability check.
6. **Step 6** (about 5 min): the policy's open question 4. Read the AWS page and send the date read, then run the read-only logging check (`None None None` in each region). The PM records both in the policy.
7. **Step 7** (about 2 min, billed in cents): the first call. **Paste `/tmp/bedrock-first-call-dev.md` back into the session**, which records it here (ac5) and in t02's report (ac4) and writes the Stubber tests.
8. **Prod**, after the release carrying this task is promoted: the runbook's Prod section, with the same plan check. The PM reads that plan too.

**Relay prompt for the PM** (three questions, one batch):

> v1-e05-t08 has three choices for you; the session went with the first option in each.
>
> 1. **doctor and a missing model profile.** `doctor --evidence-profiles` reports `models.aws_profile` in the same words as the evidence profiles, on a `Model profile` row. (a) It never fails on it, because no command calls a model yet and this check runs before every weekly pull and agent install (recommended). (b) It fails like an evidence profile, which would block the Mac's fallback-week pull on a profile the pull does not use.
> 2. **"One call per Claude route".** (a) One probe run over both routing files asks each of the three Claude models its seven questions once: 23 requests, under ten cents at list prices (recommended, since ac5's questions are separate requests). (b) Literally one request per route, which cannot answer which toolChoice types, structured output or temperature a model accepts, so ac5 would need rewording.
> 3. **Dev's grant.** (a) Both sets grant what both routing files name, so dev's set can call Opus 5.5 too. It is one account, and the first call on each route runs after the dev apply alone (recommended). (b) Each set grants only its own file's routes, so the Opus probe waits for the prod apply.

## Follow-up work

- **This task, after the operator's Step 7:** record the table under ac5 and in t02's report (ac4), add one Stubber test in `test_router.py` pinning each answer, and set the Goal to `Succeeded` once the PM has read both plans and the dev apply is recorded. If `strict` is accepted, consider sending it. If a temperature is refused, the routing files stay without one.
- **The PM's policy batch:** record the open question 4 answers from Step 6 in [the data-use policy](../policies/caselist-data-use.md), as the PM asked. This task does not edit the policy.
- **When a model stage joins the weekly run** (v1-e32-t07's live run, or the first CLI command that calls a model): make a missing model profile fail `doctor --evidence-profiles` (Decision 3), and pass `real_router=bedrock_router_factory(registry)` from the composition root. The profile then comes from settings with no further wiring.
- **If the PM wants the set inside `evidence_bucket`** (Deviation 1): `moved` blocks, one per resource.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

A grant that cannot drift from the routing files, and a client that can no longer be steered by
whatever `AWS_PROFILE` the shell holds.
1. **ac1 to ac3 and the node's criterion pass.**
   * The module's tests were red against a `bedrock:*` on `*` skeleton.
   * All 20 Terraform mutants were caught as clean assertion failures, with the geography validation
     caught by `Missing expected failure`.
   * All 10 Python mutants were caught.
   * The client test that showed today's behaviour (`KEY-OF-THE-SHELL`) is the right red.
   * `terraform_checks.sh` passed with the lock files unchanged.
2. **ac4 and ac5 are the operator's,** after the cloud cutover's step 9. The runbook's own check reads
   that. The PR merges `--partial`.
3. **Rulings on the three questions:**
   1. **(a): a missing model profile is reported and fails nothing,** while no weekly-run command
      calls a model. It flips when a model stage joins the weekly run, as the follow-up says.
   2. **(a): one probe run over both routing files,** 23 requests, each model asked its seven
      questions once. ac5's questions are separate requests, so this is the reading that answers
      them.
   3. **(a): both sets grant what both files name.** It's one account, dev's calls still go through
      dev's routing file and its $2 daily budget, and the Opus probe needn't wait for prod.
4. **Deviations accepted:**
   * a module of its own, `bedrock_access`, so the plan touches nothing else by construction;
   * the probe asking each model once.

   The PM adds `debate_cli`, `packages/debate_cli/tests` and `tests/smoke` to `constraints.packages`
   in the next batch. ac2's doctor row can only be met there.
5. **Accepted as made:**
   * the grant read from the routing files with `yamldecode`, and the `us.` regions the one written
     list, with other geographies refused;
   * the setting in the bundled profiles only;
   * no profile meaning the chain without `AWS_PROFILE`;
   * `RealRouterFactory` as a Protocol, so no composition root can forget the profile;
   * account ids masked in the probe's table, and tokens counted;
   * an eight-hour session;
   * only AWS's documentation account id in the tests.
6. **Open question 4:** the operator sends the PM the AWS page's date read and the logging check's
   output (Step 6). The PM records both in the data-use policy's next version, with rule 3's wording
   from `v1-e32-t07`'s review.
7. **The affected set** (361 files, through the root conftest) is left to the PR's `ci` under
   agreement 10. The changed areas, the doctor and installation tests, the smoke check, the always-run
   list and the static checks passed (1,635 tests).

No re-review is needed. The PM records the plan, the apply and the first call when the operator runs
them.

## PM record, 2026-10-27

Added by the PM. Nothing above is changed, and this section is not a review.

The runbook's steps in dev, on 2026-10-27, from the `caselist-credentials-dev` worktree at
`origin/dev` `8051c77`.

* **Before you start.** Signed in as `AWSReservedSSO_DebateBreakGlassAdmin`. The cutover's step 9
  output read `true`. `bedrock_invoker_user_names` was added to `owner.auto.tfvars` (count `1`).
* **Steps 1 and 2.** The plan read `Plan: 3 to add, 0 to change, 0 to destroy.`, with nothing replaced
  or destroyed and every change under `module.bedrock_access`. The check printed `PLAN OK: 3 to
  create, nothing else; bedrock:InvokeModel on 14 resources, 9 Claude models through the 3 profiles`.
  The PM read both before the apply.
* **Step 3.** `Apply complete! Resources: 3 added, 0 changed, 0 destroyed.`, then
  `"DebateDevBedrockInvoker"` and `"debate-dev-bedrock"`.
* **Step 4.** The profile signed in as `AWSReservedSSO_DebateDevBedrockInvoker`. `doctor
  --evidence-profiles` read `debate-dev-bedrock (models.aws_profile): defined, and signed in as
  DebateDevBedrockInvoker`.
* **Step 5.** The Anthropic use-case form was submitted on 2026-10-27, and
  `get-use-case-for-model-access` reads it as recorded.
  * Bedrock no longer shows an offer to accept: a first call as `debate-admin` makes the Marketplace
    subscription. The runbook's step 5 is rewritten in the PM batch of 2026-10-27 (t).
  * Cohere Rerank 3.5 answered its first call (`application/json`). Titan read `AVAILABLE` throughout.
  * **Claude Haiku, Sonnet and Opus 5.5 were refused** as "not available for this account". Their
    applied cross-region tokens-per-minute quotas are all `0.0`, against AWS defaults of 10M, 6M and
    30M. A quota request refuses any value at or below the default, so a support case was opened on
    2026-10-27 to restore them.
  * **Claude Haiku 4.5 and Sonnet 4.6** hold non-zero quotas (5M and 6M) and answered their first
    calls (`end_turn`), Haiku 4.5 after the form reached it. Dev routes to them until the 5.5 quotas
    are restored (`v1-e05-t13`).
* **Step 6, the policy's open question 4.**
  * The operator read Data protection on 2026-10-27, and the PM read its Data retention and Abuse
    detection subpages the same day:
    * model providers receive no prompts or completions;
    * retention is set per region and defaults to each model's policy, with AWS possibly retaining
      content for abuse prevention;
    * a zero-retention mode exists;
    * the pages do not say whether prompts are used for training.
  * Invocation logging read `None None None` in us-east-1, us-east-2 and us-west-2. The policy's
    next version records this, with the coach's decision on zero-retention mode.
* **Still open, so the Goal stays `InProgress`:** ac5's first call (step 7), after `v1-e05-t13`
  re-plans the invoker policy for the dev models.

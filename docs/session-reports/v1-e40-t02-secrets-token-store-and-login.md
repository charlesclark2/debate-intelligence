# Session report: v1-e40-t02-secrets-token-store-and-login

| | |
|---|---|
| Task | `v1-e40-t02-secrets-token-store-and-login` — The caselist token in Secrets Manager, and a scheduled login that renews it |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t02-secrets-token-store-and-login.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t02-secrets-token-store-and-login.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t02-secrets-token-store-and-login` |
| Session status | PARTIAL: accepted by the PM 2026-10-24, merged `--partial`; ac2's operator parts follow the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Built everything the session can build and test offline. The code: a small Secrets Manager client
in `debate_core.integrations.secrets_manager`; a `secretsmanager` backend for the existing
caselist token store; the scheduled login as an application service; and `caselist auth
set-password`, `caselist auth renew` and `caselist auth login --token-backend secretsmanager`. The
infrastructure: one Terraform module, `infrastructure/modules/caselist_run`, called from both roots.
It holds the KMS key, both secrets with their resource policies, the login and run roles and the
writer permission set (apply A), plus the login task pinned by digest and its Wednesday 03:00
America/Chicago schedule (apply B, gated on `v1-e40-t03`'s inputs). There's also a runbook for it.

Three things to look at first:

1. **The writer permission set cannot have the ADR's name.** `DebateDevCaselistCredentialWriter` is
   33 characters and Identity Center allows 32. The module uses `Debate<Env>CaselistSecretWriter`,
   which the PM ruled for (ruling 1); the spec now says so (Deviation 1).
2. **botocore really does log both secrets at DEBUG.** `botocore.endpoint` logs `PutSecretValue`'s
   `SecretString` and `botocore.parsers` logs `GetSecretValue`'s answer. The client quiets those two
   loggers on the calling thread for each call. The redaction tests drive real botocore through its
   `before-send` hook, and two control tests show the leak when nothing quiets it.
3. **The phase stays `InProgress`.** ac2's operator parts (apply in dev, prod at promotion, one
   scheduled login stores a token) cannot be closed by a session. Every other criterion passes. The
   task merges `--partial`, and apply A runs after the merge, from a fresh worktree at `origin/dev`
   (ruling 6): a dev apply from a checkout without `module.caselist_run` would destroy what it
   created.

**After the PM's review (2026-10-24, accepted with conditions), closed in this session:** the spec
names the writer `Debate<Env>CaselistSecretWriter` with a PM-ruling comment giving the 32-character
reason (condition 1); the runbook's "Before you start" and the operator follow-ups below run apply A
from a fresh `caselist-credentials-dev` worktree at `origin/dev`, after checking that the merged
module is in it, with `owner.auto.tfvars`'s block and the plan check unchanged (condition 2); and
this report's stale parts are updated (condition 3).

**Apply A's first run in dev (2026-10-24), and the fix, resumed in this session.** Run from a fresh
`origin/dev` worktree at `30ba804`, the apply created 8 of the 17 and destroyed nothing, then both
`CreateSecret` calls failed with `AccessDeniedException: Access to KMS is not allowed`. Creating a
secret under a customer-managed key has Secrets Manager call `kms:GenerateDataKey` as the caller,
and the key policy gave break-glass administration only. The fix is one Allow,
`BreakGlassEncryptsWhenCreatingTheTwoSecrets`: `kms:GenerateDataKey` for break-glass's role
(`aws:PrincipalArn` like its pattern, the account root as principal, as the other statements do),
through Secrets Manager in this region, for the two secrets' ARN patterns. No decrypt, no other key
action, no grant. The three decrypt denies and `NoGrantsAndNoReEncryption` are byte-identical to
before. A 14th Terraform test holds it, and the three mutations the PM named, plus three more, are
each killed. The runbook now has the re-plan's exact check (`Plan: 9 to add, 1 to change, 0 to
destroy.`), a corrected reading of `MalformedPolicyDocumentException`, and how to recover from a
partial apply. The task merges `--partial` again; the operator re-plans from `caselist-credentials-dev`
after the merge, and the PM reads the plan first.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `token-store` — Token store and login | Done (its criterion PASS) | Code, Terraform for both applies, runbook. The Goal's ac2 waits on the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `token-store`: Token store tests pass (`uv run pytest packages/debate_core/tests -k token`) | PASS | `.venv/bin/python -m pytest packages/debate_core/tests -k token -q` under `perl -e 'alarm 115'` → `145 passed in 15.17s` |
| ac1 — the Secrets Manager backend passes the token store's contract tests with a stubbed client | PASS | `test_token_store_contract.py`: one suite parametrized over the keyring, file and secretsmanager backends (the last over a stubbed client raising botocore's own `ClientError`), plus four Secrets-Manager-only cases (one read per process, a save is one write and no read, built only when named, refused without a secret). Run with `test_token_store.py` → `45 passed in 2.18s` |
| ac1 — a redaction test shows neither secret reaches a log or an error | PASS | `secrets_manager/test_managed_secret.py` (22 tests) and `commands/test_caselist_auth_secrets_manager.py` (8): every record at DEBUG, botocore's wire loggers included, checked for each secret raw, JSON-escaped once and twice, and by its random core. Two controls show botocore logs both values when the client is bypassed. Against a mutant that turns the quieting off, 10 tests fail and pytest's whole output holds **0** secret-shaped strings; with the harness's guard also off, the same scan finds 11, so it can see them |
| ac2 — Terraform's tests show only the login role can read the password and only the run role the token, both under the dedicated key | PASS | `terraform -chdir=infrastructure/modules/caselist_run test` → `Success! 13 passed, 0 failed.`; with the break-glass encryption fix, `Success! 14 passed, 0 failed.` (the 14th: break-glass may GenerateDataKey for the two secrets through Secrets Manager, holds nothing else beyond administration, and every decrypt deny excepts only the login and run roles; mutants below) Every role and secret has an ARN of its own (`override_resource`). Mutation: 22 of 22 mutants caught (below) |
| ac2 — the operator applies dev | NOT RUN | The first run (2026-10-24, `origin/dev` at `30ba804`) created 8 of 17 and stopped at both `CreateSecret` calls: the key policy did not let break-glass encrypt. Fixed in this branch; the re-plan from `caselist-credentials-dev` follows its merge, read by the PM first. Operator follow-ups below |
| ac2 — prod at promotion | NOT RUN | At the pilot's promotion, after this branch merges (runbook, "Prod") |
| ac2 — one scheduled login stores a token (operator) | NOT RUN | Waits for apply B, which needs `v1-e40-t03`'s network and first image (the PM's ruling (2)) |
| ac3 — Terraform's tests show the writer permission set can write both secrets and read neither | PASS | Runs `the_writer_writes_both_secrets_and_reads_neither` and `each_secret_policy_refuses_a_read_by_anyone_but_its_one_reader` in the 13 above. Mutants "writer may read the secrets" and "writer may decrypt" caught |
| ac3 — `set-password` writes the secret from hidden input without the password reaching a log, an error or its output, by test with a stubbed client | PASS | `test_caselist_auth_secrets_manager.py`: refuses without a terminal before any prompt or AWS call; takes no `--password`; ignores password environment variables; describes before prompting; writes exactly the typed username and password; nothing in stdout, stderr, the exception or any log record. Smoke checks in the installed build: `tests/smoke/test_caselist_auth.py` → `6 passed` (2 new) |

**Mutation runs** (agreement 10: integrity-critical access rules; agreement 8 does not apply,
because none of these tests uses Hypothesis, though the Python run set a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` anyway).

* **The policy documents' read rules**, as the PM asked: 22 mutants over `credentials.tf`,
  `roles.tf`, `credential_writer.tf` and `login_task.tf`, each one widening or dropping one rule.
  Every one was caught by an assertion that evaluated false. The first run counted three catches
  that were really errors (an assertion that indexed a missing key or interpolated a list), and my
  `drop` regex had swallowed neighbouring statements in one case. I fixed both and reran:
  `22 of 22 mutants caught; sources restored`. The mutants:
  * Key policy (11): drop each of the three decrypt denies; the password deny excepting the run
    role; the general deny excepting the writer; the login role decrypting the token; the run role
    decrypting the password; the writer decrypting; administration delegated to the whole account;
    administration including decrypt; grants and re-encryption allowed.
  * Secret policies (5): drop the password read deny; the password read deny excepting the run role;
    the token read deny excepting the login role; the login role writing the password; the writer
    changing who may read.
  * Role and writer policies (5): the run role reading the password; the login role reading the
    token; the login role reading S3; the writer reading; the writer decrypting.
  * Schedule (1): the schedule retrying.
* **The break-glass encryption statement** (the apply A fix): 6 mutants, the PM's three (remove
  the statement; widen it to `kms:*`; drop the `kms:ViaService` condition) and three more (add
  `kms:Decrypt`; drop the secrets' encryption context; drop the break-glass principal pattern, so any
  principal in the account). `6 of 6 caught by a false assertion (none skipped); source restored`.
  The original 22, rerun with the statement in place: `22 of 22 mutants caught`.
* **The Python rules**: 16 mutants: set-password without a terminal; set-password printing the
  password; prompting before the secret is checked; a refused login tried again; the alert naming
  the account; the password read before the API is checked; a failure not notified; the token
  secret read on every request; the run writing a validation stamp; `auto` choosing Secrets Manager;
  a refused write chained to botocore's error; a malformed value's error chained; the password
  document's parse error chained; the credentials' repr showing the username; `--token-backend`
  ignored; `renew` signing with a named profile. The first run missed the parse-error chaining
  (`__cause__` was checked, `__suppress_context__` was not). With that check added:
  `16 of 16 caught; sources restored`.

**The checks run before this report**

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (before the `pyproject.toml` edit) | `305 of 447 test files (68.2%) chosen ... from 37 changed files`: `settings.py` reaches the root conftest. At about six minutes for the whole selection, that is about four, over the two-minute line, so per agreement 10 it is left to the pull request's `ci` and not run or handed over |
| The directories of what changed and the always-run list, under `perl -e 'alarm 115'` on `.venv/bin/python -m pytest -m "not slow and not live"`: `tests/architecture tests/specs` `debate_cli/tests/test_app.py test_help_rendering.py` `tests/docs` and the two docs-script tests, `integrations/secrets_manager integrations/opencaselist`, the three `test_settings*` files, `test_caselist_login.py`, `test_version_retention_lifecycle.py` (it reads the tfvars), `debate_cli/tests/commands`, `test_config_command.py`, `tests/smoke/test_caselist_auth.py` | First run: 2 failed, in `test_doctor.py`, whose hand-written list of wired integrations lacked the new one. Fixed: `1239 passed in 27.18s` |
| The logging-state check (agreement 10): opencaselist's suites (redaction included), both auth CLI suites, the Secrets Manager suite and the login service, `-n 0 -p no:randomly`, in both orders | `223 passed in 3.59s`; reversed, `217 passed in 3.45s` |
| `uv run scripts/affected_tests.py` after the `pyproject.toml` edit | `The whole selection is affected: pyproject.toml is shared test ground.` The edit adds the new subpackage to four import-linter lists and touches no test ground, so no whole-selection hand-off; it is CI's |
| The pull request's `ci`, first push | 3 failed, all in `packages/debate_cli/tests/test_installation.py`, which pins the container's wired integrations (18), the installation check's count and the `aws` extra's boto3 gaps by hand, like `test_doctor.py`; the in-session run took `debate_cli/tests/commands/` but not this sibling file. All three now name `secrets_manager`: `test_installation.py` → `28 passed`; the whole `packages/debate_cli/tests` → `906 passed in 36.59s`; `packages/debate_api/tests` → `766 passed in 8.16s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1232 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (the whole configuration, as CI runs it) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 16 kept, 0 broken.` With `import httpx` added to the new adapter: `The HTTP client stays inside the adapters that talk HTTP BROKEN` (reverted) |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 50 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/validate_specs.py` | `OK: 434 files, 40 epics, 372 tasks, 22 releases` |
| `scripts/docs_index.py --check-descriptions`, `check_command_blocks.py`, `check_links.py` | `All 46 indexed documents ... have a description`; `OK: no # comments in 387 shell code blocks`; `OK: 2242 relative links and anchors` |
| `terraform fmt -check -recursive infrastructure`; `validate` of the module and both roots | Clean; `Success! The configuration is valid.` three times. Initialised offline from the provider already unpacked in the main checkout (a `filesystem_mirror` CLI config), with the roots' data directories in the scratchpad, so nothing was downloaded and no `envs/*/.terraform` was left behind |
| `tflint` on the module, and on both roots with `--call-module-type=all`, with and without `caselist_login_task` set | Exit 0, four times |

`scripts/terraform_checks.sh` itself was not run: it initialises every root and module from the
registry. Its parts that this change touches are the rows above; CI runs the script.

## Files changed

* **`packages/debate_core/src/debate_core/integrations/secrets_manager/`** (new): the one small
  Secrets Manager client of ADR-0020 (2). Quiets botocore's wire loggers during each call, raises
  the application's store errors `from None`, and always ignores configured endpoint URLs.
* **`.../integrations/opencaselist/token_store.py`**: the `secretsmanager` backend behind a
  `SecretSlot` Protocol, so the package never imports the SDK. It reads once per process, keeps no
  validation stamp, and refuses `logout`. Each backend now reports its own location.
* **`.../application/caselist_login.py`** (new): `ScheduledLogin` (password in, one login, token out,
  every failure notified then raised); the password document's one shape; the failure notification.
* **`.../application/settings.py`**: `caselist.token_backend = secretsmanager`, plus
  `token_secret_id`, `password_secret_id` and `secrets_region`.
* **`packages/debate_cli`**: `set-password`, `renew` and the two new options on `login`
  (`commands/caselist_auth.py`, `commands/__init__.py`); the container's builders for the secrets,
  the store on a named backend and the scheduled login.
* **Tests**: `debate_core/tests/integrations/secrets_manager/` (new),
  `opencaselist/test_token_store_contract.py` (new), `application/test_caselist_login.py` (new),
  `debate_cli/tests/commands/test_caselist_auth_secrets_manager.py` (new), `test_doctor.py`
  (the wired list), `tests/smoke/test_caselist_auth.py` (two checks, no notifier).
* **`infrastructure/modules/caselist_run/`** (new): the module, its README, tests, `.tflint.hcl`
  and the lock file (copied from `evidence_search`, which pins the same provider with all 16
  platform hashes; the offline init's own lock had only this Mac's).
* **`infrastructure/envs/{dev,prod}/`**: `caselist_run.tf`, variables, outputs and the tfvars
  example, identical in both roots. **`infrastructure/README.md`**: the module's row.
* **`docs/runbooks/caselist-cloud-credentials.md`** (new).
* **`pyproject.toml`**: the new subpackage on the httpx, keyring, lxml and defusedxml import lists.

## Deviations from the spec

1. **The writer permission set is `Debate<Env>CaselistSecretWriter`, not
   `Debate<Env>CaselistCredentialWriter`.** The spec's amendment and ADR-0020 (2) give the latter.
   Identity Center caps a permission set's name at 32 characters, and that name is 33 in dev and 34
   in prod, which the provider refused in the first test run. I used a real name, said so in the
   module, its README, the runbook and the CLI's help. The PM ruled for it (ruling 1): the spec is
   amended in this branch, and the PM amends ADR-0020.
2. **Files outside `constraints.packages`**: `pyproject.toml`, for the four import-linter lists (the
   AWS contract's own comment asks each adapter's PR to do this), and `tests/smoke/test_caselist_auth.py`,
   for working agreement 5's smoke checks of the two new commands.
3. **The password is not registered with the caselist redaction filter.** ADR-0020 (2) says each
   task "holds the value as a `SecretStr`, and registers it with the redaction filter, as the token
   store does today". The token store registers the *token*. `redaction.register_secret` documents
   that the password is deliberately never registered: that would keep it in a process-wide set for
   the life of the process. I kept that rule. What keeps the password out of logs is that nothing
   formats it, and that botocore's two wire loggers are silent during the call; the tests check both.
   The PM ruled to keep it (ruling 4) and amends ADR-0020's sentence.
4. **The secrets' policies refuse a little more than the ADR lists.** Writes include
   `UpdateSecretVersionStage`, which moves the current label to an older value. Break-glass-only
   actions add `RotateSecret` and `RestoreSecret` to the ADR's five, since each changes which value
   or key a read reaches. The PM ruled to keep them (ruling 5) and adds them to ADR-0020's lists.
5. **"The token store's contract tests"** did not exist as a shared suite: the keychain and file
   backends had per-backend tests. I wrote the contract as one parametrized file beside them, over
   all three backends. A suite in `debate_core.testing.contracts`, where the repo keeps shared
   contracts, is outside this task's packages, and nothing else needs to import this one.
6. **The SNS alert path is the existing `Notifier` port.** The scheduled login notifies through
   `ServiceContainer.sync_notifier()`, which `caselist.notifier` chooses. Today that is nothing in
   the cloud; `v1-e40-t05` adds the `sns` kind. The login role's `sns:Publish` names t05's topic,
   `debate-<env>-caselist-run-alerts`, which does not exist yet. The PM ruled that t05 builds the
   SNS adapter, and adds `debate_core.integrations` to t05's packages (ruling 2).

## Decisions and assumptions

* **`set-password` asks for the password twice** (Typer's confirmation prompt): nobody can read the
  stored value back, so a typo would otherwise be found by the Wednesday login. It describes the
  secret before prompting, so a missing grant or expired session is found before anything is typed.
* **`--aws-profile` is a command option**, not a setting: the cloud tasks must use no profile (the
  task role), and a profile in the committed dev profile would follow the build into the cloud.
* **The secret names default from the environment** (`debate-<env>-caselist-token`,
  `debate-<env>-caselist-tabroom-password`), matching Terraform's, and can be overridden by setting.
* **`renew` always writes the token to Secrets Manager**, whatever `caselist.token_backend` says,
  and builds the OpenCaselist session before reading the password, so a disabled API reads no
  secret.
* **The Secrets Manager backend reads the token once per process.** The client loads the token for
  every request, and the ADR expects one read a run in CloudTrail. It also keeps no validation stamp,
  because the run role may not write the token.
* **The key policy names the secrets by ARN pattern** (`<name>-??????`). The secrets are encrypted
  under the key and so are created after it. A pattern lets the key be created with its final policy,
  where a later `aws_kms_key_policy` would leave the default, IAM-delegating policy in place for a
  window. `??????` matches exactly Secrets Manager's six random characters.
* **The writer and break-glass are matched by `aws:PrincipalArn` patterns**
  (`role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_<set>_*`), so a reprovisioned role keeps its
  access. Allows that name the account always carry such a pattern; the tests check that none
  delegates to IAM.
* **An apply-time risk I could not test offline:** KMS's lockout check at `CreateKey` must accept
  that the break-glass role may `PutKeyPolicy` through a statement conditioned on `aws:PrincipalArn`.
  If it does not, the apply fails at the key and creates nothing (the runbook says what to look for).
* **The login task has an execution role and a log group of its own** (90 days), rather than
  waiting for t03's. It pins `entryPoint` and `command` in the definition, sets no `secrets`, sets
  the data directory under `/tmp`, and does not make the root filesystem read-only, since the image
  does not exist yet to test against.
* **The schedule never retries** (`maximum_retry_attempts = 0`), has no dead-letter queue yet (t05),
  runs `LATEST` Fargate (at least 1.4.0), and starts enabled once apply B exists
  (`login_schedule_enabled` pauses it).
* **`login_task` is a variable** for now. When t03 builds the cluster and repository in the same
  module, those six inputs become references.
* **A commit message slip:** `beb9fa6` says it renames the permission set in the CLI help and the
  client docstring; those edits were not staged and landed in `85a57ae`. History was not rewritten.

## Operator follow-ups

**After this fix merges: re-plan apply A in dev, as the PM ruled (plan, PM reads it, apply, then the
coach writes the password).** Not from this branch: from the `caselist-credentials-dev` worktree,
moved to `origin/dev` once it holds the fix. These are the runbook's blocks
([caselist-cloud-credentials.md](../runbooks/caselist-cloud-credentials.md), "Before you start" and
steps 1 to 4), with `WT` set to that worktree. Each block's success check is beneath it. Dev's state
holds the 8 resources the first run created; nothing is created or deleted by hand, and nothing is
`-target`ed.

**1. The worktree, at `origin/dev` with the fix** (~1 min). The worktree exists from the first run.
Set `SSO_USER_NAME` to your Identity Center user name:

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || { echo "WT does not exist: $WT"; }
git fetch origin
git switch --detach origin/dev
test -f infrastructure/modules/caselist_run/credentials.tf && test -f infrastructure/envs/dev/caselist_run.tf \
  && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), caselist_run merged" \
  || echo "NOT MERGED: $(pwd) at origin/dev has no infrastructure/modules/caselist_run; wait for v1-e40-t02 to merge"
grep -c BreakGlassEncryptsWhenCreatingTheTwoSecrets infrastructure/modules/caselist_run/credentials.tf
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: ... at origin/dev <commit>, caselist_run merged`, then `1`, and nothing after
it. A `0` means the fix has not merged into `dev` yet: stop and wait.

**2. Sign in as break-glass** (~1 min).

```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```
Success looks like an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

**3. The root's `owner.auto.tfvars`** (~1 min). `PREVIOUS_DEV_WT` is the checkout that last applied
dev.

```bash
cd "$WT"
PREVIOUS_DEV_WT=/path/to/the/checkout/that/last/applied/dev
test -f infrastructure/envs/dev/owner.auto.tfvars || cp "${PREVIOUS_DEV_WT}/infrastructure/envs/dev/owner.auto.tfvars" infrastructure/envs/dev/
grep -q '^caselist_credential_writer_user_names' infrastructure/envs/dev/owner.auto.tfvars \
  || printf 'caselist_credential_writer_user_names = ["%s"]\n' "$SSO_USER_NAME" >> infrastructure/envs/dev/owner.auto.tfvars
terraform fmt infrastructure/envs/dev
grep -c -E '^(owner|site_publisher_user_names|evidence_operator_user_names|evidence_removal_user_names|evidence_search_deployer_user_names|evidence_search_accounts_user_names|caselist_credential_writer_user_names) ' infrastructure/envs/dev/owner.auto.tfvars
grep -h '^owner' infrastructure/envs/dev/owner.auto.tfvars
AWS_PROFILE=debate-admin aws s3api get-bucket-tagging --bucket debate-dev-site-a7508de8 --query "TagSet[?Key=='Owner'].Value" --output text
```
Success looks like `7`, then an `owner = "..."` line and the same address as the tag. Fewer than 7:
a line is missing, so find it before planning.

**4. The plan** (~2 min). Paste `/tmp/caselist-credentials-plan.txt` to the PM.

```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell:"; env | grep -oE '^(TF_VAR_[A-Za-z_]*|TF_WORKSPACE|TF_DATA_DIR|TF_CLI_ARGS[A-Za-z_]*)'; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-credentials.tfplan | tee /tmp/caselist-credentials-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-credentials-plan.txt
grep -E '^  # ' /tmp/caselist-credentials-plan.txt | grep -v 'module.caselist_run' | head
```
What to read: exactly `Plan: 9 to add, 1 to change, 0 to destroy.`, no `must be replaced` or `will
be destroyed` line, and nothing printed by the last `grep`. **A destroyed or replaced
`aws_ssoadmin_account_assignment` or `aws_ssoadmin_permission_set` stops everything:** fix
`owner.auto.tfvars` and plan again, never apply. No `Plan:` line at all means the plan failed; read
the end of the file. (A fresh environment, such as prod, plans `17 to add, 0 to change, 0 to
destroy.` instead.)

Then check the plan itself (~1 min). It prints `PLAN STOP` with the reason for anything but the 9
creates and the key's policy changing in place:

```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-credentials.tfplan > /tmp/caselist-credentials-plan.json
python3 -I - /tmp/caselist-credentials-plan.json <<'PLANCHECK'
import json, sys
plan = json.load(open(sys.argv[1]))
key = "module.caselist_run.aws_kms_key.credentials"
expected_creates = {
    "module.caselist_run.aws_secretsmanager_secret.tabroom_password",
    "module.caselist_run.aws_secretsmanager_secret.token",
    "module.caselist_run.aws_secretsmanager_secret_policy.tabroom_password",
    "module.caselist_run.aws_secretsmanager_secret_policy.token",
    "module.caselist_run.aws_iam_role_policy.login",
    "module.caselist_run.aws_iam_role_policy.run_credentials",
    "module.caselist_run.aws_iam_role_policies_exclusive.login",
    "module.caselist_run.aws_iam_role_policies_exclusive.run",
    "module.caselist_run.aws_ssoadmin_permission_set_inline_policy.credential_writer[0]",
}
def unknown(value):
    if value is True:
        return True
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return False
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
creates = {c["address"] for c in changes if c["change"]["actions"] == ["create"]}
updates = [c for c in changes if c["change"]["actions"] == ["update"]]
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["change"]["actions"] not in (["create"], ["update"]))
problems = []
if creates != expected_creates:
    problems.append("creates missing " + str(sorted(expected_creates - creates)) + ", unexpected " + str(sorted(creates - expected_creates)))
if [u["address"] for u in updates] != [key]:
    problems.append("updates are " + str(sorted(u["address"] for u in updates)) + ", expected only " + key)
else:
    change = updates[0]["change"]
    before, after = change["before"] or {}, change["after"] or {}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    unknowns = sorted(k for k, v in (change.get("after_unknown") or {}).items() if unknown(v))
    if changed != ["policy"] or unknowns:
        problems.append("the key changes " + str(changed) + " with unknown " + str(unknowns) + ", expected only policy")
if others:
    problems.append("other actions " + str(others))
print("PLAN OK: 9 to create, the key's policy updated in place, nothing else" if not problems else "PLAN STOP: " + "; ".join(problems))
PLANCHECK
```
Success looks like `PLAN OK: 9 to create, the key's policy updated in place, nothing else`. The 9
are both secrets, both secret policies, both roles' inline policies, both `policies_exclusive` and
the permission set's inline policy; the 1 is `module.caselist_run.aws_kms_key.credentials`, updated
in place, with only `policy` changing. `PLAN STOP` stops everything: send its line and the plan to
the PM, and do not apply. The check was tested against nine plan shapes (the expected one and eight
wrong ones: a tenth create, a missing create, the key replaced, its tags changing, its policy
unknown, a second update, an assignment destroyed, the key unchanged); only the expected one prints
`PLAN OK`.

**5. After the PM's word: apply the saved plan** (~2 min).

```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-credentials.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_secret_writer_permission_set_name
```
Success looks like `Apply complete! Resources: 9 added, 1 changed, 0 destroyed.` and
`"DebateDevCaselistSecretWriter"`. **If it stops partway**, re-plan from this worktree after
`git switch --detach origin/dev` (block 1), then blocks 4 and 5 with the PM reading the new counts;
never `-target`, never by hand. A `MalformedPolicyDocumentException` that the provider retries and
then gets past is IAM catching up with a role created seconds earlier (four retries in about four
seconds on 2026-10-24); only one that persists and ends the apply means the caller is not
break-glass's role.

**6. The coach writes the password.** First the worktree's environment, which `set-password` runs
from (~1 min):

```bash
cd "$WT"
uv sync --all-packages
uv run debate-research caselist auth set-password --help | grep -c -- '--aws-profile'
```
Success looks like `Resolved ... packages`, then `1`.

Then the writer's profile (~1 min):

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --profile debate-admin --query Account --output text)
aws configure set profile.debate-dev-caselist-writer.sso_session debate
aws configure set profile.debate-dev-caselist-writer.sso_account_id "$ACCOUNT_ID"
aws configure set profile.debate-dev-caselist-writer.sso_role_name DebateDevCaselistSecretWriter
aws configure set profile.debate-dev-caselist-writer.region us-east-1
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-caselist-writer --query Arn --output text
```
Success looks like an ARN containing `AWSReservedSSO_DebateDevCaselistSecretWriter`.

Then, typed by hand in a terminal (~1 min):

```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell:"; env | grep -oE '^DEBATE_[A-Z_]*'; else DEBATE_ENV=dev uv run debate-research caselist auth set-password --aws-profile debate-dev-caselist-writer; fi
aws secretsmanager describe-secret --profile debate-dev-caselist-writer --region us-east-1 \
  --secret-id debate-dev-caselist-tabroom-password --query 'length(VersionIdsToStages)' --output text
```
Success looks like `Written to Secrets Manager secret debate-dev-caselist-tabroom-password.`, then
`1` (a version exists; `None` would mean nothing was written).

**7. Nobody else can read it, and CloudTrail saw them try** (~1 min, then up to 5 for CloudTrail).
Each read asks for the name only, so a read that wrongly succeeds prints the name, not the password.

```bash
for profile in debate-dev-caselist-writer debate-dev debate-admin; do
  printf '%s: ' "$profile"
  aws secretsmanager get-secret-value --profile "$profile" --region us-east-1 \
    --secret-id debate-dev-caselist-tabroom-password --query Name --output text 2>&1 | grep -oE 'AccessDeniedException|debate-dev-caselist-tabroom-password' | head -1
done
aws cloudtrail lookup-events --profile debate-admin --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue --max-results 20 \
  --query 'Events[].CloudTrailEvent' --output text | grep -o '"errorCode":"AccessDenied[A-Za-z]*"' | sort | uniq -c
```
Success looks like three lines ending `AccessDeniedException`, then a count of at least `3`. A line
ending in the secret's name means that profile can read the password: stop and tell the PM.

**Later, not now:**

* **Apply B in dev**, after `v1-e40-t03`'s first image push: the runbook's step 5. The plan should
  be `11 to add` (counted the same way), then the first Wednesday's check that the token secret has a
  version from that morning. This closes ac2's "one scheduled login stores a token".
* **Prod**, at the pilot's promotion: the runbook's "Prod" section, from a `main` checkout.
* **No whole-selection test run is handed over.** The affected set was over two minutes and the
  `pyproject.toml` change is lint lists only; the pull request's `ci` runs everything.

## Follow-up work

* **ADR-0020, v1-e40-t05 and v1-e40-t06**: the PM amends them for rulings 1 to 5 (the writer's
  name, t05's packages, the Mac's session check on the first scheduled login's Wednesday, the
  password's redaction sentence, the added policy actions). This task's spec is amended here.
* **`v1-e40-t03`**: replace `login_task` with references to the cluster, subnets, security group and
  repository it builds in this module. Add its inline policy to `aws_iam_role_policies_exclusive.run`.
  The image must put `debate-research` on `PATH`, because the login task's `entryPoint` names it.
* **`v1-e40-t05`**: the `sns` kind of `caselist.notifier`, which the login's failures already go to.
  A dead-letter queue on the login schedule (it has none, and never retries). The topic name the
  login role may already publish to, `debate-<env>-caselist-run-alerts`. The SNS adapter is t05's,
  with `debate_core.integrations` added to its packages (ruling 2).
* **`v2-e10-t04`** adopts the key and both secrets, and `AwsSecretsProvider` can build on
  `debate_core.integrations.secrets_manager.ManagedSecret`, as ADR-0020 plans.

### Questions for the PM

Paste-ready, one block, each with my recommendation. **Ruled by the PM on 2026-10-24** (see PM
review): 1 (a), 2 (a), 3 as recommended, 4 and 5 kept, 6 merge `--partial` now with apply A from
`dev` after the merge. Kept below as asked.

```text
v1-e40-t02 questions (session report: docs/session-reports/v1-e40-t02-secrets-token-store-and-login.md)

1. Writer permission set name. ADR-0020 (2) and the t02 amendment say Debate<Env>CaselistCredentialWriter:
   33 characters in dev, 34 in prod; Identity Center allows 32 (the provider refused it). Options:
   (a) Debate<Env>CaselistSecretWriter (29/30), (b) Debate<Env>CaselistCredWriter (28/29),
   (c) Debate<Env>CaselistPasswordWriter (31/32, but it writes the token too).
   Recommend (a): it says what the set does, writing the two secrets. The branch uses it; the ADR and
   the spec need your amendment.

2. Who builds the SNS publisher? t02 sends a failed login to the existing Notifier port
   (caselist.notifier), as the "interface for now". t05 adds the `sns` kind, but t05's
   constraints.packages has no debate_core.integrations, where a boto3 SNS adapter has to live
   (import contract). Options: (a) add debate_core.integrations to t05's packages; (b) a small t02
   follow-up adds the adapter. Recommend (a): the topic, the subscription and the run's notifier are
   all t05's.

3. Does a weekly login end the Mac's keychain session? Each `POST /login` with remember: true issues
   a new token. Nothing recorded says whether OpenCaselist keeps more than one token per user. Before
   the cutover, the Mac's agent still uses its keychain token. Recommend: apply B with the schedule
   enabled, and on the Wednesday of the first scheduled login run
   `debate-research caselist auth status --check` on the Mac. If it fails, log the Mac in by hand
   until t06 stops its schedule, and record the answer in ADR-0020.

4. ADR-0020 (2) says the task "registers [the password] with the redaction filter, as the token
   store does today". The token store registers the token. redaction.py deliberately never registers
   the password, because that keeps it in a process-wide set for the process's life. The branch keeps
   that rule and silences botocore's two wire loggers during each call instead. Recommend: keep it,
   and amend the ADR's sentence to say the token is registered and the password is never formatted.

5. The secret policies refuse slightly more than ADR-0020 (2) lists: UpdateSecretVersionStage
   counts as a write, and RotateSecret and RestoreSecret are break-glass only. Recommend: keep them
   (each changes which value or key a read reaches), and add them to the ADR's list.

6. Merging. ac2's operator parts (apply in dev, prod at promotion, the first scheduled login) cannot
   close in this session, and apply B waits for t03. Recommend: once apply A is verified (operator
   steps 1-7 in the report), merge --partial with the phase InProgress, and set Succeeded once apply
   B's first Wednesday login has written a token and prod is applied at promotion.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with conditions closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-24

**Notes:**

Careful security work.
* The botocore DEBUG leak was found, not assumed. The client quiets the two wire loggers per call,
  and two control tests prove the leak exists without it.
* The scan of pytest's own output finds 0 secret-shaped strings against a mutant, and 11 with the
  guard off, so it can see them.
* 22 policy mutants and 16 Python mutants were caught. The first-run errors that were counted as
  catches were found and fixed.
* The KMS lockout risk is named, with what to look for.

**Rulings**

1. **(a), `Debate<Env>CaselistSecretWriter`.** Amend this task's spec with a PM-ruling comment
   (condition 1). The PM amends ADR-0020 (2) in the next PM batch.
2. **(a).** The PM adds `debate_core.integrations` to v1-e40-t05's packages in the next batch.
3. **As recommended.** On the Wednesday of the first scheduled login, the operator runs
   `caselist auth status --check` on the Mac. If the Mac's token was ended, the Mac is logged in by
   hand until t06 stops its schedule, and the answer goes into ADR-0020. The PM adds this to t06.
4. **Keep it.** The password is never registered with the redaction filter and never formatted.
   The PM amends ADR-0020's sentence.
5. **Keep them.** The PM adds `UpdateSecretVersionStage`, `RotateSecret` and `RestoreSecret` to
   ADR-0020's lists.
6. **Merge `--partial` now, then apply A from `dev`, not from this branch.** A dev apply from any
   checkout without `caselist_run` would destroy what this branch created. So the resources must
   first exist in `dev`'s configuration. Condition 2.

**Deviations 1 to 6 and the Decisions are accepted.** Asking for the password twice, `--aws-profile`
as an option, one token read per process, and the ARN-pattern key policy are all sound.

**Conditions, to close in this session before the PR:**

1. **Amend the spec** for ruling 1 (`Debate<Env>CaselistSecretWriter`, and why: Identity Center's
   32-character limit).
2. **Rewrite Operator follow-ups and the runbook's apply A steps** to run after the merge, from a
   fresh worktree at `origin/dev`. Check first that the merged `infrastructure/modules/caselist_run`
   is in it, and set `WT` to that worktree.
   * Block 3's `PREVIOUS_DEV_WT` stays: the operator copies `owner.auto.tfvars` from the checkout
     that last applied dev.
   * The plan's check stays exactly as written: `17 to add, 0 to change, 0 to destroy`, no replaced
     or destroyed assignment or permission set, and nothing outside `module.caselist_run`.
3. **Update the stale parts of this report.** No re-review is needed.

**The PR:** opened with `--partial`. ac2's operator parts (apply A, then B after t03, then prod at
promotion) are recorded by the PM, who sets the Goal `Succeeded` after the first scheduled login
has written a token and prod is applied.

If anything comes out differently, stop and ask for another review.

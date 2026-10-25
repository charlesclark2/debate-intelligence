# Session report: v1-e40-t03-run-image-and-schedule

| | |
|---|---|
| Task | `v1-e40-t03-run-image-and-schedule` — The weekly run as a container on a schedule |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t03-run-image-and-schedule.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t03-run-image-and-schedule.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t03-run-image-and-schedule` |
| Session status | PARTIAL: everything a session can build and test is done; ac1's CI run, ac2 and the applies follow the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Built on t02's module, as the PM asked. **The Terraform** is all in
`infrastructure/modules/caselist_run`, called from both roots:

* the run's VPC: public subnets, no inbound rule, outbound HTTPS, an S3 gateway endpoint;
* the cluster and the immutable, KMS-encrypted ECR repository;
* the run's execution role and log group;
* the run task definition: on-demand Fargate, arm64, 8 vCPU, 16 GB, 100 GiB, `parse.workers` 8, a
  6-hour `timeout` in the container, ECS Exec off;
* its Wednesday 06:00 America/Chicago schedule, **created disabled** behind `run_schedule_enabled`;
* `Debate<Env>CaselistRunDeployer`.

t02's `login_task` variable and its six inputs are now references, plus one `image_digest`. The run
role's evidence grant is in `aws_iam_role_policies_exclusive.run`. **The image** (`ops/caselist_run/Dockerfile`)
installs one tagged release with `scripts/install_channel.sh`, for arm64, with `debate-research` on
`PATH`. `scripts/caselist_run_deploy.sh` builds it, checks it offline, pushes it and registers a run
task definition. A new validate-dev job builds it from each pre-release on GitHub's native arm64
runner and runs `caselist pull` inside it against the S3 and OpenCaselist stand-ins. **ac3**: the
summary and the run's details now carry each stage's start and end, and a run under
`storage.volume_warning_percent` (70 in the task) warns in its summary past it. The record's fields
are unchanged.

Four things to look at first:

1. **The run role holds the EvidenceOperator set's own policy, not a copy.** `module.evidence_store`
   gains an output, `operator_policy_json`. The run role's `everyday-evidence` policy is that document.
   `evidence_policy_json` is refused at plan time if it allows a delete, a wildcard or anything outside
   the ten everyday actions, or names another bucket or key. The only thing outside
   `module.caselist_run` that changes is that new output, which adds no resource to a plan.
2. **ac2 is not safe before `v1-e40-t04`**, and ADR-0020 does not make it so. A cloud run today starts
   from an empty data directory and has no bucket lock. The PM ruled that ac2 waits for t04, and
   accepted a `--dry-run` rehearsal in the cloud first: the runbook's step 7.
3. **The scheduled run would refuse to start today, on purpose.** ADR-0020 (5) puts the caselists in
   `caselist.sync_caselists` in the bundled profile, and the task names none. `config/profiles/dev.toml`
   has none yet (they are in the Mac's plist). The PM ruled that `v1-e40-t06` adds them in the
   cutover pull request.
4. **The phase stays `InProgress`.** ac1's CI part runs in validate-dev after the merge, and ac2 is
   the operator's. Every other criterion passes. This merges `--partial`, like t02.

**After the PM review (ACCEPTED with conditions, 2026-10-24)**, the three conditions are closed in
this session:

1. **The spec's `constraints.packages`** now lists `scripts`, `.github/workflows`, `tests/scripts` and
   `tests/smoke`, under a `# PM ruling 2026-10-24` comment (ruling 5). `validate_specs` passes, and
   the parsed list shows all eleven entries.
2. **Two runbook steps** in [caselist-cloud-run.md](../runbooks/caselist-cloud-run.md), each block
   with its success check. The steps after them are renumbered: the profile is now 4, the image 5,
   apply B 6, and the hand run 8.
   * **Step 3, before apply B: does a new login end the Mac's token?** (ruling 6). It runs
     `caselist auth status --check` on the Mac's keychain token, with the agent's plist environment.
     Then it runs the hand login, `caselist auth login --token-backend secretsmanager` under the
     writer's profile, and the check again. If the token is ended, the coach logs the Mac in again
     and adds `caselist_login_schedule_enabled = false` to `owner.auto.tfvars` until t06. Step 6's
     plan check then expects the login's schedule `DISABLED`. Either way, the output goes to the PM
     for ADR-0020.
   * **Step 7, after apply B: the cloud rehearsal** (ruling 1). The deployer starts the run task
     with the command overridden to `--json caselist pull --dry-run --caselist <slug>`, the slug
     read from the agent's plist. It checks for a stop with exit code 0, and for a result with
     `"dry_run": true`, `"archives_downloaded": 0` and `"objects_published": 0`. It also checks that
     `caselist runs --remote` shows no new record. It runs after step 3's hand login, or after the
     first scheduled login.
   * One thing follows from ruling 6 that the ruling did not say, so it is written into step 7. If
     step 3 finds that a login ends the other token, the Mac's second login ends the secret's token
     in turn. The login is then paused, so the rehearsal waits for t06.
3. **This summary and the Operator follow-ups** below. The token check sits between B4 and B5, and
   B6 points to it. The rehearsal follows B6. The credentials runbook's step 5 now names the
   cloud-run runbook's steps 1 to 6.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `image-schedule` — Run image and schedule | Done (its criterion PASS) | Terraform, image, deploy script, CI job, ac3's code, runbook. ac1's CI run and ac2 wait for the merge and the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `image-schedule`: Terraform checks pass (`bash scripts/terraform_checks.sh`) | PASS | Run as written, with the registry replaced by the provider already unpacked in the main checkout (`TF_CLI_CONFIG_FILE` naming a `filesystem_mirror`; every directory needs only `hashicorp/aws`): `All Terraform checks passed.`, exit 0, 27.5 s (after the sync below). fmt, validate, tflint and `terraform test` of every root and module. No lock file changed, and the `.terraform` directories it left were removed |
| ac1 — Terraform's tests show the run role's grants and the schedule | PASS | `terraform -chdir=infrastructure/modules/caselist_run test` → `Success! 26 passed, 0 failed.` t02's 14 runs pass (its first 13 on the new inputs, and the break-glass run its pull request #465 added); 12 are new (below). Mutation: 22 of 22 caught (below) |
| ac1 — the image builds from a tag and runs `debate-research caselist pull` against stubbed services in CI | NOT RUN | It runs in validate-dev's new `image` job, which runs only after a merge into `dev`. What can run before the merge did. `tests/scripts/test_caselist_run_deploy.py` → `20 passed` (the build's arguments, the offline check, the push and registration, the prod guard; 7 of 7 mutants caught). `tests/smoke/test_caselist_pull.py` against the workspace's build → `9 passed`, now asserting stage times. Operator follow-up A built a real tag locally: `scripts/caselist_run_deploy.sh dev v1.1.0-dev.134 --dry-run` printed all six `ok:` lines (linux/arm64, user 10001:10001, entrypoint `debate-research`; no credential name in the environment; no credential file; `debate-research` and `timeout` on `PATH`; `v1.1.0-dev.134`; SQLite 3.50.4 with FTS5), then `Dry run complete`, in 26 s. That build ran the release's installer but not the pull against stubbed services, which only the CI job does. The first validate-dev run after the merge closes this, and gives the CI build's time |
| ac2 — the operator applies dev and starts one run by hand; its record matches a Mac run's shape | NOT RUN | Operator, after the merge, and the hand run only after `v1-e40-t04` (question 1). Runbook [caselist-cloud-run.md](../runbooks/caselist-cloud-run.md), steps 1 to 8 (the hand run is step 8) |
| ac3 — each stage's start and end in the run's details, a 70% volume warning in the summary by test with a stubbed volume, the record's fields unchanged | PASS | `test_caselist_sync_stage_times_and_volume.py` → `11 passed`: every stage timed in order, a stage's 7 minutes read from a stub that moves the clock, dry runs and `--publish-pending` timed for what they carry out, a 75% stub warning with its text, exactly 70% not warning and one byte more warning, the fullest reading kept, no reading without the setting, a failed reading costing no stage. Against a skeleton that times and reads nothing, 10 of them fail. The record: the test lists its 23 fields by hand, and `test_pull_run_record_is_read_by_every_build.py`'s schema checks against the two older builds pass unchanged (83 passed with the refusal suite). The CLI shows the warning in its caption (`test_caselist_pull.py`, 3 new) |

**The 12 new Terraform runs**:

* the network has no inbound rule and outbound HTTPS only;
* the run role holds the everyday evidence permissions and the token, nothing more, with no delete
  and no password;
* evidence policies that delete, use a wildcard, name another bucket, use the credentials key, or
  read the password are each refused (5 runs);
* the run task: pinned image, size, deadline, environment, no `secrets`;
* the run schedule starts after the login (field by field), and is disabled by default;
* `run_schedule_enabled` turns it on;
* the deployer passes the run's roles and never the login's;
* prod's deployer name fits in 32 characters.

**Mutation runs** (agreement 10: access rules, the PassRole and secret-read rules as the PM asked;
no Hypothesis is involved).

* **Terraform, 22 mutants, 22 caught; sources restored after each** (`git checkout`, worktree clean
  after), run again on the synced tree with the same result. 19 were caught by a failing assertion
  with nothing skipped (`25 passed, 1 failed` or `24 passed, 2 failed`). 3 were caught as `Missing
  expected failure` on the very run written for that validation, which Terraform follows by
  skipping the rest of the file. No assertion errored, which memory says to rule out first.
  * The deployer (8): it may pass the login role; it may pass any role; no `iam:PassedToService`; the
    deny becomes an allow; the deny spares the login's execution role; the deny names the run role;
    it runs any family; it runs on any cluster.
  * The run's scheduler (3): it may pass the login role; no `iam:PassedToService`; it runs any
    revision.
  * The run role (3): it reads the password secret; it decrypts for the password; it loses
    `everyday-evidence` from the exclusive list.
  * The evidence policy's validation (3): delete allowed; any bucket; any key.
  * The run task and schedule (5): runs as the login role; names the password secret; takes
    `secrets` from ECS; schedule enabled by default; starts at 02:00, before the login.
* **The first run found two weaknesses, now fixed.** "The run scheduler passes to any service"
  survived, so the run gained an assertion. A validation that the evidence policy name no secret
  could not be told apart from its absence: the action list already refuses `GetSecretValue`. I
  removed it, as agreement 8 says, and replaced it with what it had hidden: the policy could name
  any KMS key. It now has to name `module.evidence_store.kms_key_arn`, and a new run refuses the
  credentials key.
* **The deploy script and the image check, 7 mutants, 7 caught**: no image check; provenance on; no
  task-role check before registering; the credential pattern blind to `TOKEN`; the SQLite floor
  unchecked; checks with the network on; prod taking a dev tag.

**The checks run before this report**, after syncing with `scripts/task sync` onto `origin/dev` at
`337a78c`. Two syncs were needed, because `dev` moved twice: t02's key-policy fix (#465) and the PM's
batch (#468). The first conflicted in two files, both resolved by keeping both sides. In the module's
tests, each side had appended a block, dev's break-glass run and this task's runs. In the module's
README, two mutation sentences were joined. Everything below was run after the first sync, and the
spec and docs checks again after the second, which changed only docs and specs. The affected set is
`312 of 453 test files (68.9%) ... from 48 changed files`, because `settings.py` reaches the root
conftest. At about six minutes for the whole selection that is about four, over the two-minute line,
so per agreement 10 it is left to the pull request's `ci`, not run or handed over. Within the two
minutes, each under `perl -e 'alarm 115'` on `.venv/bin/python -m pytest -m "not slow and not live"`:

| Command | Result |
|---|---|
| `packages/debate_cli/tests` (all of it, for the pinned integration lists) | Before the sync, first run: 1 failed, `test_pull_refused_before_the_bucket_is_built.py`, a hand-written details pin I had missed, fixed by hand. After the sync: `909 passed in 37.01s` |
| `tests/architecture tests/specs tests/docs tests/scripts` | `1684 passed in 59.38s`; after the second sync, `tests/specs tests/docs tests/architecture` → `333 passed` |
| `packages/debate_core/tests/application/caselist` | `1564 passed in 77.11s` |
| The rest of `packages/debate_core/tests/application` | `1900 passed in 17.09s` |
| `tests/smoke/test_caselist_pull.py test_caselist_runs.py test_smoke_harness.py` against the workspace's build | `11 passed in 19.77s` |
| The logging check (agreement 10): `test_caselist_sync.py` and the new volume tests, `-n 0 -p no:randomly`, both orders | `87 passed`; reversed, `87 passed` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1251 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (the whole configuration, as CI runs it) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 50 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/validate_specs.py` | `OK: 437 files, 40 epics, 375 tasks, 22 releases` |
| `check_command_blocks.py --base origin/dev`, `check_links.py`, `docs_index.py --check-descriptions` | `OK: no # comments in 414 shell code blocks in 151 Markdown files (1 session reports changed since origin/dev)`; `OK: 2274 relative links and anchors`; `All 47 indexed documents under docs/ have a description`. No `!` in any bash block of either runbook or this report |
| `shellcheck` on the deploy script and the image check | Clean |
| `scripts/actionlint.sh` | Not run: it downloads actionlint, a live call. The pull request's `ci` runs it |

## Files changed

* **`packages/debate_core/.../application/caselist_sync.py`**: `StageTime`, `VolumeReading`,
  `DataVolumeUsage`, `read_volume`. The service times every stage it carries out and, with a
  threshold, reads the data directory's volume after each one. `RunSummary` gains `stage_times` and
  `data_volume`, additively; the summary's version stays.
* **`.../application/sync_runs.py`**: the details gain `stage_times` and `data_volume`, read by every
  build's rule that an unknown key is passed over. The record is untouched.
* **`.../application/settings.py`**: `storage.volume_warning_percent` (1 to 99, unset by default),
  and a blank `storage.s3.aws_profile` now means no profile, so the task signs with its role.
* **`packages/debate_cli`**: the container passes the setting; the pull's caption carries the warning.
* **Tests**: `test_caselist_sync_stage_times_and_volume.py` and `test_settings_cloud_run.py` (new),
  `debate_cli/tests/commands/test_caselist_pull.py` (3 new), three hand-written details pins given
  the two keys, and `tests/smoke/test_caselist_pull.py` (stage times on the installed build).
* **`infrastructure/modules/caselist_run/`**:
  * new: `network.tf`, `cluster.tf`, `run_task.tf`, `deployer.tf`;
  * `login_task.tf` takes references instead of `login_task`;
  * `roles.tf` adds `everyday-evidence`;
  * `variables.tf`, `outputs.tf`, `main.tf` and the README follow;
  * the tests: t02's 13 adapted, 12 new.
* **`infrastructure/modules/evidence_bucket/`**: the `operator_policy_json` output, and an assertion
  in its tests that the output is the permission set's own policy (`13 passed`).
* **`infrastructure/envs/{dev,prod}/`**: the module's new inputs, three variables, eight outputs, a
  check that someone can deploy, the tfvars example. Still identical in both roots.
* **`ops/caselist_run/`** (new): the Dockerfile and `check_image.sh`. **`scripts/caselist_run_deploy.sh`**
  (new), with `tests/scripts/test_caselist_run_deploy.py`.
* **`.github/workflows/validate-dev.yml`**: the `image` job, which `conclude` waits for.
  **`scripts/validate_dev.py`**: `conclude` requires every job the workflow reports, and a
  `tier-report` command judges the image's smoke run by a tier's rules. Their tests, and
  `test_workflow_runners.py` (the `ubuntu-24.04-arm` runner).
* **Docs**: [`docs/runbooks/caselist-cloud-run.md`](../runbooks/caselist-cloud-run.md) (new); t02's
  runbook's apply B points at it; the module, `ops/` and `infrastructure/` READMEs.

## Deviations from the spec

1. **Files outside `constraints.packages`.** The ADR names `scripts/caselist_run_deploy.sh`, and the
   PM asked for CI to build the image. That meant `.github/workflows/validate-dev.yml`,
   `scripts/validate_dev.py`, their tests in `tests/scripts/`, and `tests/smoke/test_caselist_pull.py`
   for agreement 5's smoke check. Question 5 asks for the packages list to be amended.
2. **t02's Terraform runs pass, but three of its first 13 changed.** Their names and assertions are
   unchanged, and so is the break-glass run #465 added. The three apply-B runs take `image_digest` where they took `login_task`. The
   no-Identity-Center run sets `deployer_user_names = []` (its validation needs it) and gains one
   assertion. One message says `image_digest` for `login_task`.
3. **Three hand-written expectations gained the details' two keys**, written by hand
   (`stage_times: []`, `data_volume: null` for a run refused before any stage). One scenario table
   checks those two keys apart, for their shape, because its 10 scenarios' times all come from one
   fixed clock and are pinned in the new test.
4. **A blank `storage.s3.aws_profile` now means none.** ADR-0020 (5) wants the task to have no AWS
   profile, the committed dev profile names one, and an environment variable can only override.
   botocore would take `""` for a profile named "" and refuse it.

## Decisions and assumptions

* **CI builds the image on an arm64 runner (`ubuntu-24.04-arm`), not buildx under QEMU.** The build
  runs Python (install_channel.sh's rehearsal, `doctor`), and the smoke check runs the CLI and its
  parse workers. Emulated, each is several times slower. GitHub's arm64 runners are free for public
  repositories. **How long it takes is an estimate until the first run: about 8 to 12 minutes.** The
  build installs every dependency twice, once for the rehearsal and once for real, with uv's cache
  serving the second. Then the smoke check's own environment is synced and the pull's 9 checks run.
  The job has a 30-minute timeout. On the operator's Mac (Apple silicon, so arm64 with no
  emulation) the dry-run build of `v1.1.0-dev.134` took 26 s, download and offline check included.
  I can't tell whether Docker already had the base images cached there. A fresh runner pulls
  everything and then runs the smoke check, so the estimate stands until the first validate-dev run
  gives CI's figure.
* **The schedule is Wednesday 06:00 America/Chicago**, from ADR-0020 (2): "three hours before the run"
  and "the run at 06:00". It is in the login's zone, so daylight saving moves both together. A test
  compares the two expressions field by field: same zone, same day, later hour.
* **The schedule pins Terraform's revision**, as the login's does, so what runs on Wednesday is what
  the PM read in a plan. The deploy script registers later revisions of the family for a run started
  by hand. The schedule moves when `caselist_image_digest` does.
* **The digest goes in the gitignored `owner.auto.tfvars`**, which every dev apply already carries
  between worktrees, rather than a committed `terraform.tfvars`, which would need a pull request per
  image. If it is missing, the plan shows both tasks destroyed, and the runbook's plan check stops
  that. Question 4.
* **The image** is `python:3.12-slim-bookworm`, the tag derived from `requires-python` as for the
  pilot, with uv pinned at 0.11.7 from `ghcr.io`. It runs as uid 10001 with its data directory under
  `/var/lib/debate-research`. install_channel.sh insists on a Python uv manages, so `debate-research`
  runs on uv's Python and not the base image's own `python3`. That is why the SQLite check (FTS5,
  3.40.0 or later) runs that interpreter by path. The base images are pinned by tag, not digest: I
  had no offline way to read their digests.
* **No credential in the image, its environment or its logs.** The check refuses any `AWS_*` key, and
  anything named a token, password, secret or credential, in the image's environment (the value is
  never printed). It also refuses `~/.aws`, `secrets/` and `.env`. The task's environment names the
  token's secret and nothing secret (a Terraform test lists it whole). The run reads the token only
  through t02's Secrets Manager backend, which keeps botocore's two wire loggers quiet. I added no
  boto3 call, so there is no new path to quiet, and nothing turns on DEBUG.
* **The deadline** is `timeout --signal=TERM --kill-after=120s 6h` as the entry point, with ECS's
  `stopTimeout` 120 and `initProcessEnabled`. A run killed at six hours exits non-zero. Saving state
  and releasing the bucket lock on SIGTERM belong to t04, which owns both (Follow-up work).
* **The volume check** reads the data directory's volume after each stage and keeps the fullest
  reading. It warns strictly past the threshold, compared in whole bytes, and never fails a stage.
  Off unless the setting is set, because a laptop's disk is not the run's to judge.
* **ECR**: immutable tags, scan on push, the AWS-managed `aws/ecr` key, and the five newest images
  kept, the ADR's cost line. So the runbook says to apply a new digest before five more pushes.
* **The VPC's default security group** is taken over with no rule, so nothing in the VPC has an
  inbound rule. **The subnets** go in the first two available zones by name.
* **The deployer** may push, register, start, describe and stop. It reads the run's log. It passes
  the run role and the run's execution role to ECS tasks, and is denied the login's two roles by
  name. `ecs:RegisterTaskDefinition` takes no resource. A hand run reads its subnets and security
  group from two new root outputs, not from the schedule, so the deployer holds no scheduler read.
* **Apply-time risks I could not test offline.** Fargate must have arm64 capacity in the two zones
  chosen. Taking over the default security group removes its default rules. Docker Hub and `ghcr.io`
  must answer the Mac's build.
* **The counts for the plans** come from the module's resource blocks: my apply adds 23 and changes 1,
  apply B adds 17 (t02's 11 and the run's 6). The runbook lists them one by one.

## Operator follow-ups

**A. Done before the PR: the image builds from a real tag.** On 2026-10-24 the operator ran
`scripts/caselist_run_deploy.sh dev v1.1.0-dev.134 --dry-run` from this worktree. It printed all six
`ok:` lines, the last `ok: SQLite 3.50.4 with FTS5`, then `Dry run complete. debate-dev-caselist-run:v1.1.0-dev.134
built and checked; nothing was pushed and no AWS call was made.`, in 26 s. The first attempt passed
the block's placeholder tag word for word, and the script refused it as an unrecognised argument
before building anything. So the runbook's image step (step 5 since the renumbering) now sets `TAG` from `gh` itself and stops if it is
empty.

**After the merge, in this order.** These are the runbook's blocks
([caselist-cloud-run.md](../runbooks/caselist-cloud-run.md)), from the `caselist-credentials-dev`
worktree at `origin/dev`, after t02's apply A. Each success check is beneath its block.

**B1. The worktree at `origin/dev`, and the check that this task is merged** (~1 min).

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || { echo "WT does not exist: $WT"; }
git fetch origin
git switch --detach origin/dev
test -f infrastructure/modules/caselist_run/run_task.tf && test -f ops/caselist_run/Dockerfile \
  && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), the run merged" \
  || echo "NOT MERGED: origin/dev has no infrastructure/modules/caselist_run/run_task.tf; wait for v1-e40-t03 to merge"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: ... the run merged` and nothing after it.

**B2. Break-glass, and the deployer's line in `owner.auto.tfvars`** (~1 min).

```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```

```bash
cd "$WT"
grep -q '^caselist_run_deployer_user_names' infrastructure/envs/dev/owner.auto.tfvars \
  || printf 'caselist_run_deployer_user_names = ["%s"]\n' "$SSO_USER_NAME" >> infrastructure/envs/dev/owner.auto.tfvars
terraform fmt infrastructure/envs/dev
grep -c -E '^(owner|site_publisher_user_names|evidence_operator_user_names|evidence_removal_user_names|evidence_search_deployer_user_names|evidence_search_accounts_user_names|caselist_credential_writer_user_names|caselist_run_deployer_user_names) ' infrastructure/envs/dev/owner.auto.tfvars
grep -c '^caselist_image_digest' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`, then `8`, then `0`.

**B3. The plan of this task's apply** (~2 min). Paste `/tmp/caselist-run-plan.txt` to the PM.

```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell:"; env | grep -oE '^(TF_VAR_[A-Za-z_]*|TF_WORKSPACE|TF_DATA_DIR|TF_CLI_ARGS[A-Za-z_]*)'; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-run.tfplan | tee /tmp/caselist-run-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-run-plan.txt
grep -E '^  # ' /tmp/caselist-run-plan.txt | grep -v 'module.caselist_run' | head
grep -E '^  # .* will be updated in-place' /tmp/caselist-run-plan.txt
```

What to read:

* Exactly `Plan: 23 to add, 1 to change, 0 to destroy.`, with no `must be replaced` or `will be
  destroyed` line.
* Nothing from the second `grep`: no change outside `module.caselist_run`.
* Exactly one line from the third:
  `module.caselist_run.aws_iam_role_policies_exclusive.run will be updated in-place`.
* **A destroyed or replaced `aws_ssoadmin_account_assignment` or `aws_ssoadmin_permission_set` stops
  everything**: fix `owner.auto.tfvars`, plan again, never apply.
* `Plan: 40 to add` means t02's apply A has not been applied.

The 23 are listed in the runbook's step 1.

**B4. After the PM's word: apply the saved plan** (~2 min).

```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-run.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_deployer_permission_set_name
```
Success looks like `Apply complete! Resources: 23 added, 1 changed, 0 destroyed.` and
`"DebateDevCaselistRunDeployer"`.

**The token check, before B5 and B6** (PM ruling 6): the runbook's step 3, about 5 minutes. It
does not depend on B5. Run it after B4 and before apply B, because apply B enables the login's
schedule. First, `caselist auth status --check` on the Mac, with the agent's environment. Then the
hand login as the writer into the token secret, which prompts for the Tabroom password. Then the
check again. If the second check prints `"status": "ok"`, go on. If it prints
`"code": "CASELIST_AUTH_EXPIRED"`, the new login ended the Mac's token: log the Mac in again and add
`caselist_login_schedule_enabled = false` to `owner.auto.tfvars` (the step's two last blocks). Send
the PM the output either way.

**B5. The deployer's profile, then the first image**: the runbook's steps 4 and 5. First the profile
block. Then the dry run, which builds and checks with no AWS call (~1 min; 26 s in follow-up A). Then the push, which
prints `pushed: ...@sha256:<digest>` and the `caselist_image_digest = "sha256:..."` line, and
registers nothing before apply B. The tag to use is the newest dev pre-release containing this merge
whose validate-dev run, image job included, is green.

**B6. Apply B**: the runbook's step 6, **only after the token check above**. Add the digest to
`owner.auto.tfvars`, then plan.

* The plan must read exactly `Plan: 17 to add, 0 to change, 0 to destroy.`, with no change outside
  `module.caselist_run`.
* The login's `cron(0 3 ? * WED *)` must be `ENABLED`, or `DISABLED` if the token check paused it,
  and the run's `cron(0 6 ? * WED *)` **`DISABLED`**.
* `0` lines may name `secrets`.

The PM reads the plan, and then it is applied. That closes t02's apply B too, and the first
Wednesday login is t02's follow-up.

**The rehearsal, after B6** (PM ruling 1): the runbook's step 7, about 15 minutes. The deployer
starts the run task once as `--json caselist pull --dry-run --caselist <slug>`, with the slug read
from the agent's plist. Success looks like:

* `STOPPED	EssentialContainerExited	0`;
* in the log, `"status": "ok"`, `"dry_run": true`, `"archives_downloaded": 0` and
  `"objects_published": 0`;
* no new record in `caselist runs --remote --last 3`.

It needs the token check's hand login, or a Wednesday's scheduled login. If the token check paused
the login, the rehearsal waits for `v1-e40-t06`.

**Later, not now:**

* **ac2, one run by hand**: the runbook's step 8, **after `v1-e40-t04`** is applied and the lock
  seeded (question 1). The record check is `debate-research caselist runs --remote --last 3` on the
  Mac.
* **ac1's CI part**: the first validate-dev run on `dev` after the merge. Its `image` job must be
  green. Its duration is the CI build time to record.
* **Prod**, at the pilot's promotion: the runbook's "Prod" section, from `main`, with a stable tag.
* **No whole-selection test run is handed over.** The affected set was over two minutes, and no
  shared test ground (`pyproject.toml`, `uv.lock`, a conftest) changed. The pull request's `ci` runs
  everything.

## Follow-up work

* **`v1-e40-t04`**: SIGTERM, from the 6-hour deadline or `stop-task`, kills the CLI with Python's
  default handler. It writes no failed record and releases nothing, and the local `flock` goes with
  the process. ADR-0020 (1) 6 wants such a run to save what it may and release the lock. Both are
  t04's, so the handler is too. A first run with an empty data directory is t04's restore.
* **`v1-e40-t05`**: the run's environment needs `caselist.notifier = sns` and the topic. The run role
  needs `sns:Publish` on `debate-<env>-caselist-run-alerts`. That is the one grant "nothing more"
  leaves out today, and the module's tests list the run role's actions exactly, so t05 updates
  them. The run schedule has no dead-letter queue (it never retries), and the late-run metric filter
  reads the run's log group, `debate-<env>-caselist-run`, where the `--json` summary lands.
* **`v1-e40-t06`**: `caselist.sync_caselists` in the bundled profile (question 2); then
  `caselist_run_schedule_enabled = true` at the cutover.
* **A copied `owner.auto.tfvars`** now carries `caselist_image_digest` too. The memory note on
  recovering it from deployed state applies: `aws ecs describe-task-definition` on the run's family
  shows the digest.

### Questions for the PM

Paste-ready, one block, each with my recommendation.

```text
v1-e40-t03 questions (session report: docs/session-reports/v1-e40-t03-run-image-and-schedule.md)

1. ac2 before v1-e40-t04? ADR-0020 does not make a hand-started cloud run safe before t04: with no
   bucket mode the task starts from an empty data directory, selects every week as new, spends the
   day's five downloads against a ledger the Mac does not share, and publishes to the dev bucket
   with no lock between it and the Mac's agent. Recommend: run ac2 after t04 is applied and the lock
   seeded (runbook step 6), merging this --partial. Optionally, right after apply B, a cloud
   rehearsal that is safe today: the run task started by hand with its command overridden to
   `--json caselist pull --dry-run --caselist <slug>`. It lists only, downloads and writes nothing,
   and proves the image, the network, the run role and the token read from Secrets Manager.
   If you want it, I add it to the runbook as a step before step 6.

2. The run's caselists. ADR-0020 (5): `caselist.sync_caselists` in the bundled profile, and the task
   names no --caselist (it does not). config/profiles/dev.toml has none today; the Mac's plist
   passes them, and settings.py says "no slug is a default". So the scheduled run, once enabled,
   would refuse with NoCaselistsConfigured. Recommend: t06 adds the slugs to config/profiles/dev.toml
   (and prod.toml at the home move) in the cutover pull request that removes them from the plist,
   with your ruling that committing them is the ADR's decision; config/ is outside this task.

3. validate-dev gating. The new image job is one conclude now requires, so a red image blocks a
   dev-to-main promotion like a red smoke tier. Recommend: keep it required; the image is what the
   cloud run will be.

4. Where the image digest lives. The branch puts `caselist_image_digest` in the gitignored
   owner.auto.tfvars (no pull request per image; a missing line plans both tasks destroyed, which
   the plan check stops). Alternative: committed terraform.tfvars, one small pull request per
   image, auditable in git. Recommend owner.auto.tfvars until v2-e10-t03's OIDC applies.

5. Scope. The branch changes files outside constraints.packages: scripts/caselist_run_deploy.sh
   (named by ADR-0020), .github/workflows/validate-dev.yml and scripts/validate_dev.py (the image job
   you asked for), tests/scripts/ (their tests) and tests/smoke/test_caselist_pull.py (agreement 5's
   smoke check). Recommend: amend the spec's packages to add scripts, .github/workflows,
   tests/scripts and tests/smoke.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with conditions to close in this session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

Careful work that builds on t02 rather than beside it.
* The run role takes the EvidenceOperator set's own policy through a new output. That's better
  than a copy, and a plan-time validation refuses a delete, a wildcard, another bucket or another
  key.
* t02's `login_task` is now references. Its 14 runs pass, and 12 new runs cover the network, the
  run role, the task, the schedule and the deployer.
* 22 of 22 Terraform mutants were caught, and the two weaknesses the first run found were fixed
  rather than counted. The test that hid the any-KMS-key gap was replaced, as agreement 8 says.
* I read `network.tf`: no inbound rule, egress 443 only, and the default security group taken over
  with none. The tasks get a public IP rather than a NAT gateway, as the ADR's cost line chose.
* ac3 is additive, and the record's 23 fields are pinned by hand.
* The schedule is created disabled, and starts after the login by a field-by-field test.

**Rulings**

1. **ac2 waits for `v1-e40-t04`, as recommended.** A hand run before t04 starts from an empty data
   directory, with no bucket lock and a download ledger the Mac doesn't share. **Yes to the cloud
   rehearsal.** Add it to the runbook as a step after apply B and before step 6: the run task
   started by the deployer with its command overridden to `--json caselist pull --dry-run
   --caselist <slug>`. Its success check is that it lists, downloads nothing and writes nothing. It
   needs a token in the token secret, so the step says it runs after the first scheduled login, or
   after the token step in ruling 6 (condition 2).
2. **The caselists:** `v1-e40-t06` adds `caselist.sync_caselists` to `config/profiles/dev.toml`
   (and to `prod.toml` at the home move), in the cutover pull request that removes the slugs from
   the plist. Committing caselist slugs to config is ADR-0020 (5)'s decision. Code never hardcodes
   them. The PM amends t06 in the next batch.
3. **Keep the `image` job required by `conclude`.** The image is what the cloud run will be.
4. **The digest in the gitignored `owner.auto.tfvars`: accepted until `v2-e10-t03`'s OIDC
   applies.** The plan check stops a copy without it. The runbook's note on reading the digest back
   from the deployed task definition stays.
5. **Amend `constraints.packages`** to add `scripts`, `.github/workflows`, `tests/scripts` and
   `tests/smoke`, with a PM-ruling comment dated 2026-10-24 (condition 1).
6. **Before apply B enables the login schedule, answer t06's token question by hand (PM ruling).**
   Apply B's login schedule starts enabled, and the Mac's agent still runs the weeks on its
   keychain token. If a new login ends that token, the Mac's next run fails. Nobody may run the
   login task, but the coach can log in by hand with `caselist auth login --token-backend
   secretsmanager` under the writer's profile. That issues a new token exactly as the scheduled
   login would. So the runbook gets a step before apply B, in three parts:
   1. `caselist auth status --check` on the Mac's keychain token;
   2. the hand login to Secrets Manager;
   3. `caselist auth status --check` again.

   If the keychain token still checks, apply B as written. If it doesn't, the coach logs the Mac
   in again, and apply B sets `login_schedule_enabled = false` until t06. Either way, the answer goes
   to the PM for ADR-0020. The hand login also puts a token in the secret, which ruling 1's
   rehearsal needs (condition 2).

**Accepted as made:**
* deviations 1 to 4 (the blank AWS profile meaning none is right for a task signing with its
  role);
* the arm64 runner (the repository is public, so it costs nothing);
* Wednesday 06:00 America/Chicago;
* the schedule pinned to Terraform's revision;
* the six-hour `timeout` entry point;
* the volume check off by default;
* ECR immutable with five images kept. The runbook already says to apply a new digest before five
  more pushes.

**Follow-up work, the PM's to file or fold in:**
* SIGTERM, saving state and releasing the lock go to `v1-e40-t04`, which owns them.
* `sns:Publish` for the run role, `caselist.notifier = sns` and the run log's metric filter go to
  `v1-e40-t05`.
* Pinning the two base images by digest goes into `v1-e40-t06`, before the cutover.

**Conditions, to close in this session (no re-review needed):**

1. **Amend the spec's packages** for ruling 5.
2. **Add the two runbook steps**, the token check before apply B (ruling 6) and the cloud rehearsal
   after it (ruling 1), each with its success check. Point Operator follow-ups B6 at the first.
   Command blocks keep the house rules: no `#`, no `!` inside double quotes.
3. **Update this report's summary and Operator follow-ups**, and commit.

**The PR** merges `--partial`, as for t02, with the phase `InProgress`. After the merge: B1 to B4
(the PM reads B3's plan before B4), then the token step, then B5 and B6 (the PM reads apply B's
plan), then the rehearsal. ac2 follows t04.

If anything comes out differently, stop and ask for another review.

## PM review, second

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

The three conditions are closed. I read the runbook's step 3 in full, and step 7's checks as the
report gives them.

1. **Step 3, the token check, is what ruling 6 asked for.**
   * The Mac's check runs with the agent's own plist environment, under `env -i`, so it tests the
     token the agent actually uses.
   * The hand login is guarded against stray `DEBATE_` overrides, and stores only the token.
   * An already-expired Mac token is caught before the test, rather than read as the answer.
   * The pause is one gitignored line that step 6's plan check expects.
   * The blocks keep the house rules.
2. **Step 7, the rehearsal:** a deployer-started dry-run pull. Its checks are a zero exit, `dry_run`
   true, nothing downloaded or published, and no new run record. Those are the right four.
3. **The consequence the session added is correct, and it is accepted.** If one login ends the
   other's token, the Mac's second login ends the secret's token in turn. So with the login paused,
   the rehearsal waits for `v1-e40-t06`.
4. **The packages amendment** is under its PM-ruling comment, and `validate_specs` passes.

Nothing else changes from the first review. The PR merges `--partial`, with the phase
`InProgress`. After the merge: B1 to B4 (the PM reads B3's plan), the token check (its output to
the PM), B5, B6 (the PM reads apply B's plan), then the rehearsal. ac2 follows `v1-e40-t04`.

## Criteria open at the partial merge

This restates the open criteria already recorded above and in both PM reviews. It adds nothing new.
`scripts/task pr --partial` reads open criteria only after the last-but-one PM review ends. In this
report that point falls after the first review, because the second review was in the same session.

| Criterion | Result | What closes it |
|---|---|---|
| ac1 — the image builds from a tag and runs `debate-research caselist pull` against stubbed services in CI | NOT RUN | The first validate-dev run on `dev` after the merge: its `image` job green, and its time recorded |
| ac2 — the operator applies dev and starts one run by hand; its record matches a Mac run's shape | NOT RUN | The runbook's steps 1 to 7 after the merge, then step 8 after `v1-e40-t04` |

ac1's Terraform part and ac3 passed, as the table in "Acceptance criteria" shows. The phase stays
`InProgress`.

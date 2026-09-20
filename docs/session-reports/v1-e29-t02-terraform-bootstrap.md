# Session report: v1-e29-t02-terraform-bootstrap

| | |
|---|---|
| Task | `v1-e29-t02-terraform-bootstrap` — Terraform bootstrap and environments |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t02-terraform-bootstrap` |
| Session status | PARTIAL |

## Summary

Every file this task owns is written, committed and passing its checks: the state bootstrap root,
the shared tagging module, the `dev` and `prod` environment roots, the tflint configuration, the
credential-free checks script with its pre-commit hook, and the operator runbook. The task Goal
stays `InProgress`, because two of the five Goal criteria (`ac1` and `ac5`) describe applied AWS
infrastructure — buckets that exist, a lock that is actually contended, a deny that is actually
evaluated, and a state file that has actually moved — and every apply and state migration is an
operator step. They are handed over under **Operator follow-ups** with the exact commands and what
success looks like; the runbook is the durable copy.

Three things are worth the PM's attention. **Terraform's floor moved from 1.7 to 1.10** across
every root, which is what buys native S3 state locking (`use_lockfile`) and means the project owns
no DynamoDB lock table — the operator's installed Terraform is 1.7.3, so the pre-commit hook and
the checks script will fail until it is upgraded. **tflint inherits no configuration from a parent
directory**, which was only visible by testing it: a single `infrastructure/.tflint.hcl` silently
lints nothing in the subdirectories, so the config is copied per directory and the checks script
fails when a copy is missing or has drifted. **tflint cannot see through a child module's output**,
so feeding the provider's `default_tags` from `module.tags.tags` would have made
`aws_resource_missing_tags` fail everywhere; each root now repeats the tag map as a literal
`local.tags` and a `check` block fails the plan if it drifts from the module.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `state-bootstrap` — Remote state bucket and locking module | Done | `infrastructure/bootstrap/state`, one apply per environment, partial backend plus a gitignored `backend_override.tf` for the first (local-state) apply |
| `env-layout` — dev and prod environment roots | Done | `envs/dev` and `envs/prod` identical except `terraform.tfvars` and `backend.tf`; `infrastructure/README.md` rewritten |
| `tagging-standard` — Tagging standard via `default_tags` | Done | `modules/tags` + per-directory `.tflint.hcl`; `bootstrap/organization` is the one documented exception |
| `ci-static-checks` — checks script, pre-commit hook, CI wiring | Done, CI wiring handed off | `.github/workflows/ci.yml` does not exist; the job definition is under **Follow-up work** for `v1-e01-t04`, as the spec directs |
| `operator-apply-state` — Operator applies the state bootstrap | Handed to operator | Runbook written and committed; the applies, the lock test, the deny check and the organization-state migration are outstanding |

## Acceptance criteria

Tooling used for the runs below: Terraform 1.16.3 and tflint 0.64.0 with the AWS ruleset 0.44.0,
both fetched into the session scratchpad because the machine has Terraform 1.7.3 and no tflint.
The pinned version is recorded in `.terraform-version`.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `ac1` — per-environment private, versioned, encrypted state buckets with locking; second concurrent plan fails the lock; `debate-dev` cannot read prod state | NOT RUN | Requires `terraform apply` and live IAM evaluation, both operator-only. Configuration is in place and validates: `aws_s3_bucket_versioning` (Enabled), `aws_s3_bucket_server_side_encryption_configuration` (AES256), `aws_s3_bucket_public_access_block` (all four true), `aws_s3_bucket_ownership_controls` (BucketOwnerEnforced), a `DenyInsecureTransport` bucket policy, `use_lockfile = true` in every backend, names `debate-{dev,prod}-tfstate-a7508de8`. Steps 1, 2, 4 and 5 of the runbook |
| `ac2` — `infrastructure/` contains `bootstrap/`, `modules/` and `envs/{dev,prod}` only, with a README on adding a module, how environments differ, and operator-run applies | PASS | `ls -A infrastructure` → `.tflint.hcl bootstrap envs modules README.md`; `envs/dev` vs `envs/prod` compared file by file → `main.tf`, `providers.tf`, `versions.tf`, `variables.tf`, `outputs.tf`, `.tflint.hcl` byte-identical, only `backend.tf` and `terraform.tfvars` differ. [`infrastructure/README.md`](../../infrastructure/README.md) covers all three |
| `ac3` — every resource inherits the five `default_tags`, and a tflint rule fails when a module drops them | PASS | With `default_tags` removed from `infrastructure/bootstrap/state/versions.tf`: `tflint --chdir=infrastructure --recursive` → `Notice: The resource is missing the following tags: "CostCenter", "Environment", "ManagedBy", "Owner", "Project". (aws_resource_missing_tags)`, exit 2. Restored → exit 0 |
| `ac4` — `scripts/terraform_checks.sh` runs fmt, validate for both envs and every bootstrap root, and tflint, without AWS credentials, under two minutes, non-zero on error, from pre-commit | PASS | `bash scripts/terraform_checks.sh` → 12 `ok` lines, `All Terraform checks passed.`, exit 0, **7.4 s** warm / **72 s** cold (first run, downloading the AWS provider and the tflint plugin). Non-zero path: a drifted `.tflint.hcl` copy → `FAIL … differs from infrastructure/.tflint.hcl`, exit 1. `uv run pre-commit run --from-ref 937da88 --to-ref HEAD` → `terraform fmt, validate and tflint … Passed`. No AWS credential is resolved: `init` runs `-backend=false` |
| `ac5` — `bootstrap/organization` uses the S3 backend in the prod bucket; `init -migrate-state` then a clean plan, no local `terraform.tfstate` left, dated backup kept | NOT RUN | `infrastructure/bootstrap/organization/backend.tf` is written and validates. The migration itself is operator-only and the local state file is in the operator's main clone, not this worktree. Runbook step 6 |

### Node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| State bootstrap module validates — `terraform -chdir=infrastructure/bootstrap/state validate` | PASS | exit 0 |
| dev environment validates — `terraform -chdir=infrastructure/envs/dev validate` | PASS | exit 0 |
| prod environment validates — `terraform -chdir=infrastructure/envs/prod validate` | PASS | exit 0 |
| tflint passes with tagging rules — `tflint --chdir=infrastructure --recursive` | PASS | exit 0 |
| Terraform checks script passes without AWS credentials — `bash scripts/terraform_checks.sh` | PASS | exit 0 |
| Formatting is clean — `terraform fmt -check -recursive infrastructure` | PASS | exit 0 |
| Runbook records the dev and prod bootstrap applies — `docs/runbooks/terraform-bootstrap.md` contains `prod` | PASS | File exists, 371 lines; the per-environment table and step 2 are prod-specific |
| Operator confirms remote state and locking | NOT RUN | Operator step; runbook steps 3 and 4, handed over below |

## Files changed

**`infrastructure/bootstrap/state/`** (new) — the per-environment state bucket root: `main.tf`
(bucket, versioning, SSE-S3, public-access block, ownership controls, lifecycle, deny-insecure-transport
policy, `prevent_destroy`), `versions.tf`, `backend.tf` (deliberately partial), `variables.tf`,
`outputs.tf`, committed `dev.tfvars`/`prod.tfvars` and `dev.s3.tfbackend`/`prod.s3.tfbackend`,
`terraform.tfvars.example`, `README.md`, `.terraform.lock.hcl`.

**`infrastructure/modules/tags/`** (new) — the five-tag standard with its validations, plus a
`README.md` naming the one documented exception.

**`infrastructure/envs/dev/`, `infrastructure/envs/prod/`** (new) — the two environment roots.
Identical apart from `backend.tf` and `terraform.tfvars`. No resources yet.

**`infrastructure/.tflint.hcl`** (new) and its per-directory copies — the shared lint config,
including `aws_resource_missing_tags` for the five keys.
**`infrastructure/bootstrap/organization/.tflint.hcl`** (new) — the account-wide exception, which
requires the other four keys and leaves `Environment` out.

**`infrastructure/bootstrap/organization/`** — added `backend.tf` (prod state bucket, own key),
moved the version pin to `>= 1.10.0`, removed an unused `local.environments` that tflint flagged,
and rewrote the README's state section.

**`scripts/terraform_checks.sh`** (new), **`.pre-commit-config.yaml`**, **`.gitignore`**,
**`.terraform-version`** (new) — the checks and the files they depend on.

**`docs/runbooks/terraform-bootstrap.md`** (new), **`docs/runbooks/aws-account-baseline.md`**,
**`docs/README.md`**, **`infrastructure/README.md`** — the operator steps and the doc index.

## Deviations from the spec

**The Goal is left `InProgress`, not `Succeeded`.** `ac1` and `ac5` assert facts about applied AWS
infrastructure, and the spec itself makes every apply and state migration an operator step. Marking
the Goal `Succeeded` before those steps run would record two criteria as met when they have not
been checked. The PM or the operator should flip it after the follow-ups below come back clean;
`uv run scripts/task_helper.py set-phase v1-e29-t02-terraform-bootstrap Succeeded` is the command.

**No `terraform-checks` CI job.** `.github/workflows/ci.yml` does not exist in this repository yet,
which is the branch of `ac4` the spec anticipated: the script and the pre-commit hook ship here and
the job goes to `v1-e01-t04`. The job definition is under **Follow-up work**.

**Terraform's floor moved from 1.7 to 1.10**, including in `bootstrap/organization`, which
`v1-e29-t01` had pinned at `>= 1.7.0`. The spec asks for native S3 state locking and allows a
DynamoDB lock table "only if the pinned Terraform version requires it"; `use_lockfile` does not
exist before 1.10, so the choice was to raise the floor or to own a lock table per environment.
Raising the floor is the smaller commitment. Verified against a real binary rather than from
memory: with Terraform 1.16.3 an `s3` backend carrying `use_lockfile = true` passes configuration
validation and fails only on credentials.

Nothing else was added, removed or reinterpreted.

## Decisions and assumptions

**One state bucket per environment, suffix `a7508de8`.** S3 bucket names are global, and
`debate-dev-tfstate` is not a name this project can count on owning. The suffix is a committed
constant rather than a `random_id` because an environment root's `backend` block cannot contain
expressions, so the name has to be knowable before the first apply. It is deliberately not the
account id: the runbook records bucket names, and ADR-0010 keeps account ids out of the repository.
If the name turns out to be taken, the runbook says which five files to change.

**SSE-S3, not a customer-managed KMS key.** A CMK for state would be a second bootstrap dependency
with its own key policy, applied before any state exists to record it, and a key whose accidental
deletion makes the state unreadable. Access is already controlled by the bucket policy, by
block-public-access and by the permission sets that separate `debate-dev-*` from `debate-prod-*`.
The evidence buckets in `v1-e29-t03` do get a customer-managed key — they hold the data, and they
are created after this root exists.

**The first apply uses a gitignored `backend_override.tf`, not an edit to `backend.tf`.** The
bootstrap root stores its state in the bucket it creates. `terraform init -backend=false` followed
by `apply` does not work — tested, Terraform refuses with a backend-change error — so the temporary
local backend comes from an override file, whose `path` is per environment so dev's local state can
never be picked up by a prod apply. Tested end to end against a throwaway root.

**A `check` block ties `var.environment` to the directory name.** With no account boundary, a
tfvars mix-up is what creates a prod resource named and tagged as dev; the directory name is the one
thing that cannot be passed in by accident.

**`bootstrap/organization` state goes to the prod bucket.** Its resources are account-wide and
admin-applied, and its state names every permission set and policy in the account, so it belongs
behind `DebateMaintainer`'s deny on `debate-prod-*` rather than in the dev bucket.

**Assumed a `debate-admin` SSO profile for `DebateBreakGlassAdmin`.** `debate-dev`
(`DebateMaintainer`) is denied `debate-prod-*` and `debate-prod` (`DebateReadOnly`) cannot write, so
creating the prod state bucket needs break-glass. The runbook's "Before you start" has the
`~/.aws/config` stanza. `iam:SimulatePrincipalPolicy` is also not in `PowerUserAccess`, so the deny
checks run under that profile against the `DebateMaintainer` role as the simulated principal.

## Operator follow-ups

All of these are in [docs/runbooks/terraform-bootstrap.md](../runbooks/terraform-bootstrap.md),
which has the surrounding checks, the failure cases and the table to record results in. Run them in
order; each later step assumes the earlier one came back clean.

### 1. Upgrade the Terraform CLI and install tflint (~3 min)

Where: your Mac, anywhere.

```bash
terraform version                     # currently 1.7.3
brew trust hashicorp/tap              # brew refused the formula as untrusted when I checked
brew upgrade hashicorp/tap/terraform
brew install tflint
terraform version && tflint --version
```

Success: Terraform reports 1.10 or newer (1.16.3 is what this task was tested on and what
`.terraform-version` pins) and tflint reports a version. Until this is done,
`scripts/terraform_checks.sh` and the new pre-commit hook fail on every root with
"Unsupported Terraform Core version".

### 2. Create the dev and prod state buckets and migrate their state (~5 min)

Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e29-t02-terraform-bootstrap`,
in `infrastructure/bootstrap/state`. Runbook steps 1 and 2 — please follow them rather than this
summary, because each `apply` has a plan to read before approving and a dated backup afterwards.
Create `infrastructure/bootstrap/state/terraform.tfvars` with your email first
(`printf 'owner = "<your-email>"\n' > terraform.tfvars`).

Success: `debate-dev-tfstate-a7508de8` and `debate-prod-tfstate-a7508de8` exist; after
`init -migrate-state`, `terraform plan -var-file=<env>.tfvars` reports **No changes** for both; the
local `bootstrap-<env>.tfstate` files are backed up to `~/aws-backups/debate-terraform-state/` and
removed. Paste the two bucket names and the two "No changes" lines back.

### 3. Point the environment roots at their backends and test locking (~3 min)

Where: the same worktree, repository root. Runbook steps 3 and 4.

```bash
printf 'owner = "<your-email>"\n' > infrastructure/envs/dev/owner.auto.tfvars
printf 'owner = "<your-email>"\n' > infrastructure/envs/prod/owner.auto.tfvars
AWS_PROFILE=debate-dev   terraform -chdir=infrastructure/envs/dev  init
AWS_PROFILE=debate-dev   terraform -chdir=infrastructure/envs/dev  plan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/prod init
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/prod plan
```

Success: each `init` prints `Successfully configured the backend "s3"!` and each `plan` reports no
changes. Then run the concurrent-plan race in runbook step 4; success is one of the two runs
containing `Error acquiring the state lock`. If both succeed, use the step-4 fallback against
`infrastructure/bootstrap/state`, which holds the lock long enough to collide.

### 4. Confirm a dev credential is denied the prod state bucket (~2 min)

Where: your Mac, anywhere. Runbook step 5. Uses `iam simulate-principal-policy` under
`debate-admin`, never an attempted read.

Success: every row of the prod simulation reads `explicitDeny`, and the dev simulation reads
`allowed`. Paste both tables back.

### 5. Migrate the organization root's state out of the main clone (~5 min)

Where: **the main clone**, `debate-intelligence/`, which is where the local `terraform.tfstate`
lives. Runbook step 6. It needs `infrastructure/bootstrap/organization/backend.tf`, which arrives
with this PR — either run it after the merge into `dev`, or bring that one file over first with
`git checkout task/v1-e29-t02-terraform-bootstrap -- infrastructure/bootstrap/organization/backend.tf`.

The backup comes first:

```bash
cd <main-clone>
mkdir -p ~/aws-backups/debate-terraform-state
cp infrastructure/bootstrap/organization/terraform.tfstate \
   ~/aws-backups/debate-terraform-state/organization-$(date +%Y%m%d-%H%M%S).tfstate
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/bootstrap/organization init -migrate-state
terraform -chdir=infrastructure/bootstrap/organization plan
```

Success: `plan` reports **No changes**. If it proposes creating the permission sets or the trail
again, the state did not come across — stop, restore the backup over `terraform.tfstate`, and do
not apply. On a clean plan, delete the local `terraform.tfstate` and `terraform.tfstate.backup`
from the clone and confirm `bootstrap/organization/terraform.tfstate` is listed in
`debate-prod-tfstate-a7508de8`.

### 6. Record the results and close the task

Fill in the "What to record" tables in the runbook, then set the Goal phase:

```bash
uv run scripts/task_helper.py set-phase v1-e29-t02-terraform-bootstrap Succeeded
uv run scripts/validate_specs.py
```

## Follow-up work

**`terraform-checks` CI job — `v1-e01-t04`.** When `.github/workflows/ci.yml` is created, add this
job and put `terraform-checks` in the aggregate `ci` job's `needs`. It is gated on the
`infrastructure` path filter and needs no AWS credentials or secrets.

```yaml
  terraform-checks:
    needs: changes
    if: needs.changes.outputs.infrastructure == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.16.3      # keep in step with .terraform-version
          terraform_wrapper: false       # the script checks exit codes itself
      - uses: terraform-linters/setup-tflint@v4
        with:
          tflint_version: v0.64.0
      - run: scripts/terraform_checks.sh
```

The `infrastructure` path filter should cover `infrastructure/**` and
`scripts/terraform_checks.sh`, which is what the pre-commit hook watches.

**Lock files carry only a `darwin_arm64` `h1:` hash.** Each `.terraform.lock.hcl` also carries the
registry `zh:` hashes, which cover every platform, so a Linux CI runner verifies fine. If a future
task wants the stricter form, `terraform providers lock -platform=linux_amd64 -platform=darwin_arm64`
in each root adds it; it re-downloads the provider per root, so it is an operator-scale command
rather than something to run inside CI.

**`envs/dev` and `envs/prod` manage no resources yet**, so `terraform plan` against them proves
only that the backend works. They stop being empty in `v1-e29-t03-evidence-buckets`.

**The `debate-prod` profile stays read-only.** Creating prod resources needs `DebateBreakGlassAdmin`
until `v1-e29-t03` adds the least-privilege operator permission set, as
`docs/runbooks/aws-account-baseline.md` step 6 already notes.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

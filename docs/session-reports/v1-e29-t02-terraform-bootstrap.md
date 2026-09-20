# Session report: v1-e29-t02-terraform-bootstrap

| | |
|---|---|
| Task | `v1-e29-t02-terraform-bootstrap` — Terraform bootstrap and environments |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t02-terraform-bootstrap` |
| Session status | COMPLETE |

## Summary

The Terraform foundation for every later infrastructure task is in place and applied: a state
bootstrap root, the shared tagging standard, the `dev` and `prod` environment roots, a
credential-free checks script wired into pre-commit, and an operator runbook. The operator applied
both state buckets, migrated all five state files into them and ran the verification steps on
2026-09-20; every Goal criterion passes, and the two that describe live AWS (`ac1`, `ac5`) were
confirmed read-only after the fact rather than assumed.

Three findings are worth the PM's attention, because each one would have shipped a check that
looked like it was working and was not. **Terraform's floor moved from 1.7 to 1.10** across every
root, which is what buys native S3 state locking (`use_lockfile`) and means the project owns no
DynamoDB lock table; the lock test's HTTP 412 `PreconditionFailed` is the proof it is the
conditional-write mechanism doing the work. **tflint inherits no configuration from a parent
directory** — a single `infrastructure/.tflint.hcl` silently lints nothing in the subdirectories,
so the config is copied per directory and the checks script fails when a copy is missing or has
drifted. **tflint cannot see through a child module's output**, so feeding the provider's
`default_tags` from `module.tags.tags` would have made `aws_resource_missing_tags` fail everywhere;
each root repeats the tag map as a literal `local.tags`, with a `check` block failing the plan if
it drifts from the module.

The one piece of this task's scope that does not ship here is the CI job, because
`.github/workflows/ci.yml` does not exist yet — the branch of `ac4` the spec anticipated. The job
definition is under **Follow-up work** for `v1-e01-t04`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `state-bootstrap` — Remote state bucket and locking module | Done | `infrastructure/bootstrap/state`, one apply per environment, partial backend plus a gitignored `backend_override.tf` for the first (local-state) apply |
| `env-layout` — dev and prod environment roots | Done | `envs/dev` and `envs/prod` identical except `terraform.tfvars` and `backend.tf`; `infrastructure/README.md` rewritten |
| `tagging-standard` — Tagging standard via `default_tags` | Done | `modules/tags` + per-directory `.tflint.hcl`; `bootstrap/organization` is the one documented exception |
| `ci-static-checks` — checks script, pre-commit hook, CI wiring | Done, CI wiring handed off | `.github/workflows/ci.yml` does not exist; the job definition is under **Follow-up work** for `v1-e01-t04`, as the spec directs |
| `operator-apply-state` — Operator applies the state bootstrap | Done | Operator ran it 2026-09-20: both buckets applied, all five state files migrated, lock and deny checks passed, organization root moved out of the main clone. Results recorded in the runbook's tables |

## Acceptance criteria

Tooling used for the runs below: Terraform 1.16.3 and tflint 0.64.0 with the AWS ruleset 0.44.0,
both fetched into the session scratchpad because the machine has Terraform 1.7.3 and no tflint.
The pinned version is recorded in `.terraform-version`.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `ac1` — per-environment private, versioned, encrypted state buckets with locking; second concurrent plan fails the lock; `debate-dev` cannot read prod state | PASS | Applied by the operator 2026-09-20 and verified read-only afterwards. `debate-dev-tfstate-a7508de8` and `debate-prod-tfstate-a7508de8`, both: versioning `Enabled`, encryption `AES256`, public access block `True True True True`, ownership `BucketOwnerEnforced`, policy sids `DenyInsecureTransport, DenyUnencryptedObjectUploads`, tags carrying `Environment=dev`/`prod` with the other four keys. Locking: two concurrent `plan`s, the loser failed `Error acquiring the state lock … api error PreconditionFailed` (HTTP 412 on `PutObject`) against `debate-dev-tfstate-a7508de8/bootstrap/state/dev/terraform.tfstate` — the conditional write behind `use_lockfile`, not a DynamoDB table. Deny: `iam simulate-principal-policy` for the `DebateMaintainer` role → `explicitDeny` on `ListBucket`/`GetObject`/`PutObject`/`DeleteObject` against the prod bucket ARN and both prod state keys by name, and `allowed` for the same actions on the dev bucket |
| `ac2` — `infrastructure/` contains `bootstrap/`, `modules/` and `envs/{dev,prod}` only, with a README on adding a module, how environments differ, and operator-run applies | PASS | `ls -A infrastructure` → `.tflint.hcl bootstrap envs modules README.md`; `envs/dev` vs `envs/prod` compared file by file → `main.tf`, `providers.tf`, `versions.tf`, `variables.tf`, `outputs.tf`, `.tflint.hcl` byte-identical, only `backend.tf` and `terraform.tfvars` differ. [`infrastructure/README.md`](../../infrastructure/README.md) covers all three |
| `ac3` — every resource inherits the five `default_tags`, and a tflint rule fails when a module drops them | PASS | With `default_tags` removed from `infrastructure/bootstrap/state/versions.tf`: `tflint --chdir=infrastructure --recursive` → `Notice: The resource is missing the following tags: "CostCenter", "Environment", "ManagedBy", "Owner", "Project". (aws_resource_missing_tags)`, exit 2. Restored → exit 0 |
| `ac4` — `scripts/terraform_checks.sh` runs fmt, validate for both envs and every bootstrap root, and tflint, without AWS credentials, under two minutes, non-zero on error, from pre-commit | PASS | `bash scripts/terraform_checks.sh` → 12 `ok` lines, `All Terraform checks passed.`, exit 0, **7.4 s** warm / **72 s** cold (first run, downloading the AWS provider and the tflint plugin). Non-zero path: a drifted `.tflint.hcl` copy → `FAIL … differs from infrastructure/.tflint.hcl`, exit 1. `uv run pre-commit run --from-ref 937da88 --to-ref HEAD` → `terraform fmt, validate and tflint … Passed`. No AWS credential is resolved: `init` runs `-backend=false` |
| `ac5` — `bootstrap/organization` uses the S3 backend in the prod bucket; `init -migrate-state` then a clean plan, no local `terraform.tfstate` left, dated backup kept | PASS | Migrated by the operator from the main clone 2026-09-20. `terraform plan` reported `No changes.` both immediately after `init -migrate-state` and again after the local file was deleted. Verified read-only: no `*.tfstate*` remains in `debate-intelligence/infrastructure/bootstrap/organization/`; `debate-prod-tfstate-a7508de8` holds `bootstrap/organization/terraform.tfstate` alongside `bootstrap/state/prod/` and `envs/prod/`; the dated backup `organization-20260920-021156.tfstate` (86,743 bytes, serial 31, 31 resources) is in `~/aws-backups/debate-terraform-state/` with the two bootstrap-state backups |

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
| Operator confirms remote state and locking | PASS | `terraform -chdir=infrastructure/envs/<env> init` printed `Successfully configured the backend "s3"!` for both environments 2026-09-20, and the concurrent-plan race produced one `Error acquiring the state lock`. Both env roots were then applied (outputs only, no resources), so `envs/dev/terraform.tfstate` and `envs/prod/terraform.tfstate` exist in their own buckets — each profile writing its own state proves the split end to end |

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

**No `terraform-checks` CI job.** `.github/workflows/ci.yml` does not exist in this repository yet,
which is the branch of `ac4` the spec anticipated: the script and the pre-commit hook ship here and
the job goes to `v1-e01-t04`. The job definition is under **Follow-up work**.

**Terraform's floor moved from 1.7 to 1.10**, including in `bootstrap/organization`, which
`v1-e29-t01` had pinned at `>= 1.7.0`. The spec asks for native S3 state locking and allows a
DynamoDB lock table "only if the pinned Terraform version requires it"; `use_lockfile` does not
exist before 1.10, so the choice was to raise the floor or to own a lock table per environment.
Raising the floor is the smaller commitment. A side effect the operator has now taken: migrating
the organization state with 1.16.3 upgraded its recorded version one way, so 1.7.3 can no longer
read it. The dated backup predates the upgrade.

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

**All complete, 2026-09-20.** The steps and their results are in
[docs/runbooks/terraform-bootstrap.md](../runbooks/terraform-bootstrap.md), whose record tables are
filled in. In summary:

| Step | Result |
|---|---|
| Terraform ≥ 1.10 and tflint installed | Terraform 1.16.3, tflint 0.64.0. `tflint` is not in homebrew-core; it comes from `terraform-linters/tap` |
| `debate-dev` state bucket applied and migrated | `debate-dev-tfstate-a7508de8`, `plan` clean |
| `debate-prod` state bucket applied and migrated | `debate-prod-tfstate-a7508de8`, applied under `debate-admin` (`DebateBreakGlassAdmin`), `plan` clean |
| Environment roots pointed at their backends | Both printed `Successfully configured the backend "s3"!`; both then applied their outputs, so each profile has written its own state bucket |
| Concurrent-plan lock | One plan failed with HTTP 412 `PreconditionFailed` — the `use_lockfile` conditional write |
| `DebateMaintainer` denied prod state | `explicitDeny` on all four actions against the bucket and both prod state keys by name; `allowed` on the dev bucket |
| `bootstrap/organization` migrated | `plan` clean before and after deleting the local file; no `*.tfstate*` left in the main clone; dated backups kept in `~/aws-backups/debate-terraform-state/` |

Nothing further is required before PM review. `scripts/task pr` is the operator's next action once
the verdict is recorded below.

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

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Notes:**

- All five Goal criteria pass, and the evidence comes from the live account.
  - Both state buckets are in place, with native locking checked by two concurrent plans. The
    debate-dev profile is denied the prod bucket, confirmed with the policy simulator.
  - The organization root's state is migrated, no local state remains in the main clone, and dated
    backups sit outside the repo.
- Leaving the Goal InProgress until the operator steps had been verified was the right call.
- Security check: no account ids, org ids or Identity Center ids are committed. The committed
  tfvars carry only the environment, region and a random suffix.
- Accepted deviations:
  - The Terraform floor is now 1.10, and `.terraform-version` pins it. The organization state was
    rewritten by 1.16.3 and can no longer be read by older versions, so the pin and the runbook
    both need to say so.
  - There is no CI job yet because ci.yml does not exist. The job definition in Follow-up work
    carries forward to v1-e01-t04, which its spec already allows for.
- Carried forward:
  - v1-e01-t04 adds the terraform-checks job.
  - v1-e36-t02 (site hosting) is unblocked once this merges.

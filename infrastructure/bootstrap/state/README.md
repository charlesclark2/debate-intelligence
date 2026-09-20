# Remote state bootstrap

Creates one environment's Terraform state bucket. Spec:
[`v1-e29-t02-terraform-bootstrap`](../../../plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml).
Decision: [ADR-0010](../../../docs/adr/0010-primary-aws-region.md).
How to run it: [docs/runbooks/terraform-bootstrap.md](../../../docs/runbooks/terraform-bootstrap.md).

| File | What it defines |
|---|---|
| `versions.tf` | Terraform and provider pins, and the provider with its `default_tags` |
| `backend.tf` | A deliberately partial S3 backend; the values come from `<environment>.s3.tfbackend` |
| `variables.tf` | Inputs. `owner` comes from a gitignored `terraform.tfvars` |
| `main.tf` | The bucket, its versioning, encryption, public-access block, lifecycle and policy |
| `dev.tfvars`, `prod.tfvars` | The per-environment inputs, committed |
| `dev.s3.tfbackend`, `prod.s3.tfbackend` | The per-environment backend config, committed |

## One bucket per environment

ADR-0010 puts dev and prod in the same AWS account and separates them by resource-name prefix and
tag, with `DebateMaintainer` denying `debate-prod-*`. State has to respect that boundary, so this
root is applied once per environment and produces `debate-dev-tfstate-*` and
`debate-prod-tfstate-*`. A single shared state bucket would hand every dev session the prod state
file, which lists every prod resource.

Locking is the S3 backend's native lock object (`use_lockfile`, Terraform >= 1.10): a second
concurrent plan finds `<key>.tflock` already present and fails to acquire the lock. There is no
DynamoDB table.

The bucket name ends in a fixed suffix, committed in `dev.tfvars`/`prod.tfvars`, because S3 bucket
names are a global namespace and `debate-dev-tfstate` is not a name this project can count on
owning. It is a constant rather than a `random_id` so that the environment roots' `backend` blocks
— which cannot contain expressions — can name the bucket directly. It is not the account id.

## The chicken-and-egg, and how it is resolved

This root stores its own state in the bucket it creates, so the first apply of each environment
runs on a local backend and the state is migrated afterwards. `backend.tf` stays partial and is
never edited; the temporary local backend comes from a gitignored `backend_override.tf`, which
Terraform's override-file mechanism merges over the real one:

```bash
cat > backend_override.tf <<'OVERRIDE'
terraform {
  backend "local" {
    path = "bootstrap-dev.tfstate"
  }
}
OVERRIDE
terraform init -reconfigure
terraform apply -var-file=dev.tfvars
rm backend_override.tf
terraform init -migrate-state -backend-config=dev.s3.tfbackend
```

The local state path is per environment so that dev's local state can never be picked up by a
prod apply. The runbook has the full sequence, including the backup step and the prod
credentials.

## Operator-only

`terraform apply` here is an operator step; the prod apply needs `DebateBreakGlassAdmin`, because
`DebateMaintainer` cannot write `debate-prod-*`. CI never runs plan or apply against this root —
there are no OIDC deploy roles until `v2-e10-t03` — and neither does an agent session.

The bucket carries `prevent_destroy`. Losing it means losing the record of every resource
Terraform manages in the environment and re-importing them one at a time.

## Switching environments afterwards

The working directory is bound to whichever environment was initialised last, so switching is an
explicit `init`:

```bash
terraform init -reconfigure -backend-config=prod.s3.tfbackend
terraform plan -var-file=prod.tfvars
```

Passing `dev.tfvars` against the prod backend would try to rename the prod bucket; the `-var-file`
and the `-backend-config` always name the same environment.

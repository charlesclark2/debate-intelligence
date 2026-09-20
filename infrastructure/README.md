# infrastructure

Terraform for the platform's AWS resources. Specs:
[`v1-e29-t01-aws-account-baseline`](../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml)
and [`v1-e29-t02-terraform-bootstrap`](../plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml).

There are exactly two environments, `dev` and `prod`
([ADR-0013](../docs/adr/0013-two-environments-and-dev-main-promotion.md)), both in `us-east-1`
([ADR-0010](../docs/adr/0010-primary-aws-region.md)). ADR-0010 also records that they live in one
AWS account, separated by tag and resource name rather than by an account boundary, and the rules
that keeps binding.

## Layout

| Directory | What | Owning spec |
|---|---|---|
| [`bootstrap/organization/`](bootstrap/organization/) | Identity Center permission sets, organization CloudTrail, budgets and cost anomaly detection | `v1-e29-t01-aws-account-baseline` |
| [`bootstrap/state/`](bootstrap/state/) | The remote-state bucket for one environment; applied once per environment | `v1-e29-t02-terraform-bootstrap` |
| [`modules/`](modules/) | Reusable modules. No account ids, regions or credentials inside them — those are inputs | `v1-e29-t02-terraform-bootstrap` |
| [`envs/dev/`](envs/dev/), [`envs/prod/`](envs/prod/) | The two environment roots | `v1-e29-t02-terraform-bootstrap` |

There is no `envs/stage`, and adding one means changing ADR-0013 first.

## How the environments differ

`envs/dev` and `envs/prod` hold the same files, and `main.tf`, `providers.tf`, `versions.tf`,
`variables.tf` and `outputs.tf` are character-for-character identical in both. Only two files
differ:

* `terraform.tfvars` — `environment = "dev"` or `"prod"`.
* `backend.tf` — the environment's own state bucket and key.

A `check` block in `main.tf` refuses to plan if `var.environment` does not match the directory
name, because in a single-account setup a tfvars mix-up is what creates a prod resource named and
tagged as dev.

**Never copy a resource block from one root to the other.** Anything both environments need goes
in `modules/` and is called from both roots with different inputs. Two copies of a resource drift
the moment one of them is fixed, and there is no account boundary here to make the drift obvious.

## How to add a module

1. Create `modules/<descriptive-name>/` with `main.tf`, `variables.tf`, `outputs.tf`,
   `versions.tf` and a `README.md` saying what it is for and which spec owns it.
2. Take account id, region, bucket names and anything else account-specific as **variables**.
   Hard-coding them is forbidden by the task spec: it is what stops the module being usable in
   both environments.
3. Pin what the module requires: `required_version` and, if it declares providers, a
   `required_providers` constraint.
4. Copy `infrastructure/.tflint.hcl` into the new directory — `scripts/terraform_checks.sh
   --sync-tflint` does it for you. tflint inherits nothing from a parent directory, so a
   directory without its own copy is silently linted with tflint's defaults; the checks script
   fails when a copy is missing or has drifted.
5. Call it from `envs/dev` and `envs/prod` and run `scripts/terraform_checks.sh`.

## Tagging

Every resource inherits five tags through the provider's `default_tags`:
`Project`, `Environment` (`dev` or `prod`), `Owner`, `CostCenter` and `ManagedBy=terraform`.
[`modules/tags`](modules/tags/) defines the standard; each root repeats it as a literal
`local.tags` map (which is what tflint can read) and a `check` block fails the plan if the two
disagree. `tflint`'s `aws_resource_missing_tags` rule fails a root that drops the block.

`bootstrap/organization` is the one documented exception: its resources are account-wide, so they
carry no `Environment` tag. That exception is a `.tflint.hcl` of its own in that directory.

## Versions

| Thing | Pin | Where |
|---|---|---|
| Terraform | `>= 1.10.0, < 2.0.0`, tested on the version in [`.terraform-version`](../.terraform-version) | every root's `versions.tf` |
| `hashicorp/aws` | `~> 5.100`, exact version in each root's `.terraform.lock.hcl` | every root's `versions.tf` |
| tflint AWS ruleset | `0.44.0` | [`.tflint.hcl`](.tflint.hcl) |

The floor of 1.10 is what makes the S3 backend's native state locking (`use_lockfile`) available,
so there is no DynamoDB lock table for this project to own.

## Applies are operator-run

The only Terraform CI runs is [`scripts/terraform_checks.sh`](../scripts/terraform_checks.sh) —
`fmt -check`, `validate -backend=false` and `tflint`. It has no AWS credentials to run a plan
with: the GitHub OIDC plan/apply roles arrive in `v2-e10-t03`. Until then every `init
-migrate-state`, `plan` and `apply` is run by the operator and recorded in
[docs/runbooks/terraform-bootstrap.md](../docs/runbooks/terraform-bootstrap.md). Agent sessions
never apply.

The script runs from pre-commit today. `.github/workflows/ci.yml` does not exist yet, so the
`terraform-checks` job that calls it is added by `v1-e01-t04` along with the workflow itself; the
session report for `v1-e29-t02-terraform-bootstrap` carries the job definition to drop in.

## Operator-local files

`terraform.tfvars` under `bootstrap/` and `*.auto.tfvars` anywhere under `infrastructure/` are
gitignored: they carry the maintainer's email. Each directory that needs one ships a
`.example` beside it. Everything else — including `envs/<env>/terraform.tfvars` and
`bootstrap/state/<env>.tfvars` — is committed and account-agnostic.

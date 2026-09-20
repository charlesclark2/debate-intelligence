# Account baseline bootstrap

Identity, audit and cost guardrails for the account the Debate Intelligence Platform runs in.
Spec: [`v1-e29-t01-aws-account-baseline`](../../../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml).
Decision: [ADR-0010](../../../docs/adr/0010-primary-aws-region.md).
How to run it: [docs/runbooks/aws-account-baseline.md](../../../docs/runbooks/aws-account-baseline.md).

| File | What it defines |
|---|---|
| `versions.tf` | Terraform and provider pins, and the `default_tags` every resource inherits |
| `backend.tf` | The S3 backend: this root's state key in the prod state bucket |
| `variables.tf` | Inputs; the real values live in a gitignored `terraform.tfvars` |
| `main.tf` | Data sources for the existing Organization and Identity Center instance, naming locals, pre-apply checks |
| `identity.tf` | The three permission sets, their policies, and account assignments |
| `cloudtrail.tf` | Organization trail, its KMS key, and its log bucket |
| `budgets.tf` | Per-environment budgets, the Bedrock budget, cost anomaly detection |

## Operator-only

`terraform apply` here is an operator step. CI never runs plan or apply against this root, and
neither does an agent session — there are no OIDC deploy roles until `v2-e10-t03`, and this root
holds the controls that would be used to grant them.

## Where the state lives

In the **prod** state bucket, under `bootstrap/organization/terraform.tfstate`; see
[`backend.tf`](backend.tf). This root held local state until `v1-e29-t02-terraform-bootstrap`
created the state buckets, and the migration is step 6 of
[docs/runbooks/terraform-bootstrap.md](../../../docs/runbooks/terraform-bootstrap.md).

The prod bucket rather than the dev one because these resources are account-wide and
admin-applied: `DebateMaintainer` is denied `debate-prod-*`, so a dev session cannot read a state
file that names every permission set and policy in the account. It holds no secrets, but treat it
as sensitive anyway.

Keep the dated backup the migration produced. Losing this state means re-importing the permission
sets, the trail and the budgets by hand.

## What is deliberately not managed here

The Organization and the IAM Identity Center instance predate this project and are read through
data sources, never adopted as resources. Both are shared with unrelated projects in the same
account, and a `terraform destroy` in this root must not be able to reach them. For the same
reason the pre-existing `AdministratorAccess` permission set is left alone; this root adds its
own `Debate*` sets beside it.

Enabling CloudTrail's trusted access to the Organization is likewise a one-line operator command
rather than a resource, for the same reason. A `check` block in `main.tf` turns the resulting
apply failure into a readable message pointing at the runbook step.

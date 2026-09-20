# `tags` module

Builds the tag map every resource in this project carries. Spec:
[`v1-e29-t02-terraform-bootstrap`](../../../plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml).
Decision: [ADR-0010](../../../docs/adr/0010-primary-aws-region.md).

| Tag | Value | Why |
|---|---|---|
| `Project` | `debate-intelligence` | Budgets and cost anomaly detection filter on it; the account also runs unrelated projects |
| `Environment` | `dev` or `prod` | Half of the dev/prod boundary in a single-account setup (resource names are the other half) |
| `Owner` | maintainer email | Who is accountable; never committed, supplied per operator |
| `CostCenter` | `debate-intelligence` | Separates this project's spend inside one bill |
| `ManagedBy` | `terraform` | Marks anything created by hand as a defect worth finding |

## Use

Every root feeds the output into the provider's `default_tags` rather than tagging resources one
by one:

```hcl
module "tags" {
  source      = "../../modules/tags"
  environment = var.environment
  owner       = var.owner
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = module.tags.tags
  }
}
```

`additional_tags` merges extra keys on top (for example `SpecRef`), and refuses to redefine one
of the five above.

## Enforcement

[`infrastructure/.tflint.hcl`](../../.tflint.hcl) enables `aws_resource_missing_tags` for those
five keys. The rule reads the provider's `default_tags`, so a root that drops the block — or a
module that configures its own provider without it — fails
[`scripts/terraform_checks.sh`](../../../scripts/terraform_checks.sh) rather than reaching AWS
untagged.

The account-wide root [`bootstrap/organization`](../../bootstrap/organization/) is the one
documented exception: its trail, budgets and permission sets protect both environments at once,
so they carry no `Environment` tag. That exception is a `.tflint.hcl` of its own in that
directory, not a blanket relaxation of the rule.

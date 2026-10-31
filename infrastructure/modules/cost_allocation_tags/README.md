# `cost_allocation_tags` module

The account's `Project` and `Environment` cost allocation tags, kept Active. Spec:
[`v1-e05-t18-cost-allocation-tags-in-terraform`](../../../plan_specs/v1/e05-model-router/t18-cost-allocation-tags-in-terraform.yaml).
Operator steps: [docs/runbooks/aws-account-baseline.md](../../../docs/runbooks/aws-account-baseline.md#the-cost-allocation-tags).

Called once, from [`bootstrap/organization`](../../bootstrap/organization/budgets.tf): cost
allocation tags are account billing settings, and dev and prod share one account (ADR-0010). The
environment budgets filter on `user:Environment` and the cost anomaly monitor on `user:Project`; an
inactive tag makes them read $0. The operator activated both by hand on 2026-10-30, and two `import`
blocks in the root adopt them without changing them.

## What it creates

Two `aws_ce_cost_allocation_tag` resources, `Project` and `Environment`, each `Active`, and nothing
else. `tests/cost_allocation_tags.tftest.hcl` holds the keys and the status;
`tests/infrastructure/test_cost_allocation_tags_are_the_only_ones_managed.py` holds that no other
cost allocation tag is managed anywhere under `infrastructure/`.

## How the provider's resource behaves

Read from hashicorp/aws 5.100.0, the version the root's lock file pins, run against a loopback
stand-in for Cost Explorer (the task's session report):

| Terraform does | Cost Explorer sees |
|---|---|
| Create | `UpdateCostAllocationTagsStatus` with the configured status: a tag already Active is adopted unchanged, with no import needed |
| Import, then plan | `ListCostAllocationTags`: Active shows as imported with nothing to change, Inactive as updated to Active |
| Destroy | `UpdateCostAllocationTagsStatus` with `Inactive`: the budgets read $0 again |

A key AWS has not seen on any resource cannot be imported or activated. In a new account that means
waiting up to 24 hours after the first tagged resource (the runbook's step 5).

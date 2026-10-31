# Offline tests for the cost_allocation_tags module: the account's Project and Environment cost
# allocation tags kept Active (task v1-e05-t18-cost-allocation-tags-in-terraform).
#
# `mock_provider "aws"` means no credentials, no network and no AWS account.
#
#   terraform -chdir=infrastructure/modules/cost_allocation_tags init -backend=false
#   terraform -chdir=infrastructure/modules/cost_allocation_tags test
#
# What these runs hold the module to:
#
#   * exactly two cost allocation tags, Project and Environment, written out by hand below (working
#     agreement 6): the keys the anomaly monitor and the environment budgets filter on;
#   * each of them Active, so the budgets read real spend rather than $0.
#
# That no other cost allocation tag is managed anywhere under infrastructure/, through another
# resource block in this module or in a root, is held by
# tests/infrastructure/test_cost_allocation_tags_are_the_only_ones_managed.py: a Terraform test
# cannot list a module's resources.

mock_provider "aws" {}

run "exactly_the_project_and_environment_tags" {
  command = apply

  assert {
    condition     = toset(keys(aws_ce_cost_allocation_tag.this)) == toset(["Environment", "Project"])
    error_message = "The module manages the Project and Environment tags, and no other."
  }

  assert {
    condition     = toset([for tag in aws_ce_cost_allocation_tag.this : tag.tag_key]) == toset(["Environment", "Project"])
    error_message = "Each tag resource carries the key it is named for: Project and Environment, and no other."
  }

  assert {
    condition     = output.tag_keys == tolist(["Environment", "Project"])
    error_message = "The tag_keys output names the two keys, which the organization root checks the anomaly monitor's key against."
  }
}

run "both_tags_active" {
  command = apply

  assert {
    condition     = try(aws_ce_cost_allocation_tag.this["Project"].status, "") == "Active"
    error_message = "The Project tag is Active: the anomaly monitor filters on it, and an inactive tag reads $0."
  }

  assert {
    condition     = try(aws_ce_cost_allocation_tag.this["Environment"].status, "") == "Active"
    error_message = "The Environment tag is Active: the environment budgets filter on it, and an inactive tag reads $0."
  }

  assert {
    condition     = length(aws_ce_cost_allocation_tag.this) == 2 && alltrue([for tag in aws_ce_cost_allocation_tag.this : tag.status == "Active"])
    error_message = "Every tag the module manages is Active."
  }
}

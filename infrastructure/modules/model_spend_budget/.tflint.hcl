# Static checks for every Terraform root and module in this repository.
#
# tflint does not inherit configuration from parent directories: with `--recursive` it looks for
# a `.tflint.hcl` in each directory it visits and falls back to its built-in defaults when there
# is none. So this file is copied verbatim into every Terraform directory under infrastructure/,
# and scripts/terraform_checks.sh fails if a copy drifts from it or if a directory holding .tf
# files has no copy at all. Edit this file and rerun `scripts/terraform_checks.sh --sync-tflint`
# to update the copies.
#
# The one deliberate difference is infrastructure/bootstrap/organization/.tflint.hcl, which
# documents its own exception to the tagging standard.
#
# Run through scripts/terraform_checks.sh alongside `terraform fmt -check` and
# `terraform validate -backend=false`. None of it needs AWS credentials, which is what lets it
# run in pre-commit and in CI while every plan and apply stays an operator step.

config {
  # Follow `source = "../../modules/..."` calls so a module that drops the tagging standard is
  # caught where it is written, not only where it is used.
  call_module_type = "local"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.44.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# The tagging standard of ADR-0010. In a single-account setup these tags are half of the boundary
# between dev and prod, and the only way the budgets can tell debate spend from the unrelated
# projects sharing the account, so a resource missing one is a defect.
#
# The rule reads the provider's `default_tags`, so a root that feeds it infrastructure/modules/tags
# passes without tagging resources one at a time, and a root that drops the block fails here
# rather than at apply.
rule "aws_resource_missing_tags" {
  enabled = true
  tags    = ["Project", "Environment", "Owner", "CostCenter", "ManagedBy"]
}

# The account-wide exception to the tagging standard. The only Terraform directory under
# infrastructure/ that does not hold a verbatim copy of infrastructure/.tflint.hcl.
#
# This root's permission sets, organization trail, budgets and cost anomaly monitor protect both
# environments at once; ADR-0010 calls that the `shared` scope. Tagging them Environment = dev or
# Environment = prod would be a false statement about what they cover, so the rule here requires
# the other four keys and leaves Environment out. Every other directory requires all five.
#
# Kept as a config file next to the code it applies to, rather than as a path exclusion in the
# shared config, so that the exception is visible to whoever is reading this root.
#
# scripts/terraform_checks.sh knows this directory is the exception and does not overwrite this
# file. If a rule is added to infrastructure/.tflint.hcl, add it here too.

config {
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

rule "aws_resource_missing_tags" {
  enabled = true
  tags    = ["Project", "Owner", "CostCenter", "ManagedBy"]
}

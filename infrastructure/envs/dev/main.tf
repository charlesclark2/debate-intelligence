# One of the two environment roots (ADR-0013: dev and prod, and no third). This file is
# character-for-character the same in envs/dev and envs/prod: the environments differ only in
# terraform.tfvars and backend.tf. Copying a resource block from one root to the other instead of
# putting it in infrastructure/modules is what this layout exists to prevent — see
# infrastructure/README.md.
#
# v1-e29-t02-terraform-bootstrap creates the layout and the conventions only, so there are no
# resources here yet. The evidence buckets arrive in v1-e29-t03-evidence-buckets as a module call.
#
# Applies are operator-run. There are no GitHub OIDC roles until v2-e10-t03, so CI never runs
# plan or apply against this root, and neither does an agent session.

locals {
  # The tagging standard of ADR-0010, written out here rather than taken straight from
  # module.tags. tflint's aws_resource_missing_tags rule reads the provider's `default_tags`, and
  # it evaluates one module at a time: a child module's output is opaque to it, so feeding
  # `default_tags` from module.tags.tags would turn the rule into a check that always fails. This
  # literal map is what the rule can read, and the check below is what stops it from drifting
  # away from the shared module that defines the standard.
  tags = {
    Project     = var.project
    Environment = var.environment
    Owner       = var.owner
    CostCenter  = var.cost_center
    ManagedBy   = "terraform"
  }
}

module "tags" {
  source = "../../modules/tags"

  project     = var.project
  environment = var.environment
  owner       = var.owner
  cost_center = var.cost_center
}

check "tagging_standard_matches_shared_module" {
  assert {
    condition = local.tags == module.tags.tags
    error_message = join(" ", [
      "The default_tags in this root no longer match infrastructure/modules/tags, which is the",
      "definition of the tagging standard. Update local.tags to match the module, or change the",
      "module and every root together.",
    ])
  }
}

# The environment is a tfvars value, and tfvars values can be pointed at the wrong root. In a
# single-account setup that mistake tags prod resources as dev and names them debate-dev-*, which
# is the boundary ADR-0010 relies on. The directory name is the one thing that cannot be passed
# in by accident.
check "environment_matches_directory" {
  assert {
    condition = var.environment == basename(abspath(path.root))
    error_message = join(" ", [
      "var.environment is '${var.environment}' but this root is infrastructure/envs/${basename(abspath(path.root))}.",
      "Run terraform with -chdir=infrastructure/envs/${var.environment}, or fix terraform.tfvars.",
    ])
  }
}

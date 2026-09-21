# The tagging standard for every resource this project creates.
#
# ADR-0010 puts dev and prod in one AWS account with unrelated personal projects, so there is no
# account boundary to tell debate resources apart from anything else, and no boundary between the
# two environments. Tags are half of what replaces it (resource names are the other half), which
# is why these five keys are not optional and why `tflint`'s aws_resource_missing_tags rule fails
# a root that drops them.
#
# Roots consume this through the provider's `default_tags`, so that every resource inherits the
# standard without a per-resource `tags` argument to forget.

locals {
  standard_tags = {
    Project     = var.project
    Environment = var.environment
    Owner       = var.owner
    CostCenter  = var.cost_center
    ManagedBy   = "terraform"
  }

  tags = merge(local.standard_tags, var.additional_tags)
}

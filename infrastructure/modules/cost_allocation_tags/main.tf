# The account's cost allocation tags, kept Active (v1-e05-t18-cost-allocation-tags-in-terraform).
#
# The environment budgets filter on `user:Environment` and the cost anomaly monitor on `user:Project`
# (bootstrap/organization/budgets.tf). AWS bills a tag only once its key is activated, so until then
# both read $0, and a budget that always reads zero never alerts. The keys were never activated until
# the operator set both Active by hand on 2026-10-30 (v1-e05-t16's report); this module is what keeps
# them that way, so a plan shows a reset as drift.
#
# The provider's resource has no create of its own: creating one calls UpdateCostAllocationTagsStatus
# with the status below, which leaves a tag that is already Active unchanged. Destroying one sets the
# tag Inactive, which zeroes the budgets again; a plan that destroys one of these is never applied.
#
# A key can only be activated once AWS has seen a resource carrying it, which can take up to 24 hours
# after the first tagged resource exists (docs/runbooks/aws-account-baseline.md, step 5).

locals {
  tag_keys = ["Project", "Environment"]
}

# Not taggable: a cost allocation tag is account billing state, not a resource with tags of its own.
resource "aws_ce_cost_allocation_tag" "this" {
  for_each = toset(local.tag_keys)

  tag_key = each.key
  status  = "Active"
}

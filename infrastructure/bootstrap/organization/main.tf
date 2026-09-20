# Account baseline for the Debate Intelligence Platform.
#
# The Organization and the IAM Identity Center instance already existed before this project, so
# both are read through data sources and never managed here: adopting them into this state would
# let a `terraform destroy` in this root tear down unrelated personal projects that share the
# account. What this root does own is the project's identity, audit and cost guardrails.
#
# Applied by the operator only (see README.md); CI never runs plan or apply against this root.

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_organizations_organization" "current" {}

data "aws_ssoadmin_instances" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.name

  organization_id = data.aws_organizations_organization.current.id

  identity_center_instance_arn = tolist(data.aws_ssoadmin_instances.current.arns)[0]
  identity_store_id            = tolist(data.aws_ssoadmin_instances.current.identity_store_ids)[0]

  # ADR-0010 names every resource debate-<environment>-<purpose>. Account-wide controls that
  # protect both environments use the `shared` scope and are treated as prod for access.
  environments = ["dev", "prod"]

  # Resource-name and tag patterns the permission sets use to separate environments. Written
  # once here so identity.tf cannot drift from the naming rule.
  prod_bucket_arns = [
    "arn:${local.partition}:s3:::${var.name_prefix}-prod-*",
    "arn:${local.partition}:s3:::${var.name_prefix}-prod-*/*",
    "arn:${local.partition}:s3:::${var.name_prefix}-shared-*",
    "arn:${local.partition}:s3:::${var.name_prefix}-shared-*/*",
  ]
}

# An organization trail can only be created once CloudTrail has trusted access to the
# Organization. That is an operator step (`aws organizations enable-aws-service-access`) rather
# than a resource here, because enabling it through the aws_organizations_organization resource
# would mean importing and managing the whole Organization. This check turns a confusing apply
# failure into a readable one.
check "cloudtrail_trusted_access_enabled" {
  assert {
    condition = contains(
      data.aws_organizations_organization.current.aws_service_access_principals,
      "cloudtrail.amazonaws.com"
    )
    error_message = join(" ", [
      "CloudTrail does not have trusted access to the Organization, so the organization trail",
      "in cloudtrail.tf cannot be created. Run the enable-aws-service-access step in",
      "docs/runbooks/aws-account-baseline.md first.",
    ])
  }
}

# The budgets and the anomaly monitor filter on the Project and Environment cost allocation
# tags. Those tags must be activated by hand in Billing before they report real numbers, and no
# AWS provider resource can activate them, so the runbook carries that step and its verification.

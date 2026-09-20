output "permission_set_arns" {
  description = "Identity Center permission set ARNs, for the least-privilege operator set added in v1-e29-t03."
  value = {
    break_glass_admin = aws_ssoadmin_permission_set.break_glass_admin.arn
    maintainer        = aws_ssoadmin_permission_set.maintainer.arn
    read_only         = aws_ssoadmin_permission_set.read_only.arn
  }
}

output "permission_set_names" {
  description = "Permission set names, as they appear in the AWS access portal and in `aws configure sso`."
  value = {
    break_glass_admin = aws_ssoadmin_permission_set.break_glass_admin.name
    maintainer        = aws_ssoadmin_permission_set.maintainer.name
    read_only         = aws_ssoadmin_permission_set.read_only.name
  }
}

output "cloudtrail_name" {
  description = "Name of the organization trail."
  value       = aws_cloudtrail.organization.name
}

output "cloudtrail_bucket_name" {
  description = "Bucket holding the organization trail's log files."
  value       = aws_s3_bucket.cloudtrail.id
}

output "cloudtrail_kms_key_alias" {
  description = "Alias of the KMS key encrypting CloudTrail log files."
  value       = aws_kms_alias.cloudtrail.name
}

output "budget_names" {
  description = "Budget names, for confirming a test alert arrived from the right budget."
  value = concat(
    [for budget in aws_budgets_budget.environment_monthly : budget.name],
    [aws_budgets_budget.bedrock_monthly.name],
  )
}

output "primary_region" {
  description = "Primary region for every resource in this root (ADR-0010)."
  value       = local.region
}

output "bucket_name" {
  description = "The site bucket. v1-e36-t05-site-deploy syncs the built export into it."
  value       = aws_s3_bucket.site.id
}

output "bucket_arn" {
  description = "ARN of the site bucket, for permission checks with `aws iam simulate-principal-policy`."
  value       = aws_s3_bucket.site.arn
}

output "distribution_id" {
  description = "The distribution to invalidate after a deploy."
  value       = aws_cloudfront_distribution.site.id
}

output "distribution_arn" {
  description = "ARN of the distribution, for permission checks with `aws iam simulate-principal-policy`."
  value       = aws_cloudfront_distribution.site.arn
}

output "distribution_domain_name" {
  description = "The *.cloudfront.net domain. The site answers here whether or not a team domain is configured, which is how a first deploy goes out while a certificate is still validating."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "site_url" {
  description = "Where the site actually is: the canonical domain once one is configured, otherwise the CloudFront domain."
  value       = local.site_url
}

output "canonical_host" {
  description = "The host every other alias is 301'd to. Empty until a team domain is configured."
  value       = local.canonical_host
}

output "domain_names" {
  description = "Every name the distribution answers on."
  value       = var.domain_names
}

output "certificate_arn" {
  description = "The ACM certificate serving this site, or null while it runs on the CloudFront default certificate."
  value       = local.certificate_arn
}

output "certificate_validation_records" {
  description = <<-EOT
    The DNS records that prove domain ownership to ACM, as name/type/value triples. Terraform
    writes them itself when route53_zone_id is set; this output is what the operator pastes into
    an external registrar when it is not (docs/runbooks/team-website.md).
  EOT
  value = [
    for option in try(aws_acm_certificate.site[0].domain_validation_options, []) : {
      domain_name = option.domain_name
      name        = option.resource_record_name
      type        = option.resource_record_type
      value       = option.resource_record_value
    }
  ]
}

output "publisher_permission_set_name" {
  description = "Identity Center permission set that may publish this site, as it appears in the AWS access portal and in `aws configure sso`. Null when no Identity Center instance was given."
  value       = one(aws_ssoadmin_permission_set.site_publisher[*].name)
}

output "publisher_permission_set_arn" {
  description = "ARN of the publisher permission set, for `aws iam simulate-principal-policy` against the role it provisions."
  value       = one(aws_ssoadmin_permission_set.site_publisher[*].arn)
}

output "publisher_profile_name" {
  description = "The name to give the operator's SSO profile for this environment (debate-dev-site / debate-prod-site), so the runbook and the deploy script agree on it."
  value       = var.name_prefix
}

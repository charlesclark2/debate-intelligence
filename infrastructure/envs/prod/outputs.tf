output "environment" {
  description = "The environment this root manages."
  value       = var.environment
}

output "aws_region" {
  description = "The region this root creates resources in (ADR-0010)."
  value       = var.aws_region
}

output "standard_tags" {
  description = "The default_tags every resource in this root inherits."
  value       = module.tags.tags
}

# --- The public team website (v1-e36-t02-site-hosting) ---------------------------------------
#
# v1-e36-t05-site-deploy reads these to know where to sync and what to invalidate, so renaming
# one is a change to the deploy script too.

output "site_bucket_name" {
  description = "The bucket the built site is synced into."
  value       = module.site.bucket_name
}

output "site_distribution_id" {
  description = "The distribution to invalidate after a deploy."
  value       = module.site.distribution_id
}

output "site_distribution_domain_name" {
  description = "The *.cloudfront.net domain. The site answers here whether or not the team domain is configured."
  value       = module.site.distribution_domain_name
}

output "site_url" {
  description = "Where this environment's site actually is."
  value       = module.site.site_url
}

output "site_certificate_validation_records" {
  description = "DNS records proving domain ownership to ACM. Terraform writes them itself when the hosted zone is known; this is what the operator pastes into an external registrar when it is not."
  value       = module.site.certificate_validation_records
}

output "site_publisher_permission_set_name" {
  description = "The Identity Center permission set that may publish this site, as it appears in `aws configure sso`."
  value       = module.site.publisher_permission_set_name
}

output "site_publisher_profile_name" {
  description = "The name to give the operator's SSO profile for publishing this environment (debate-dev-site / debate-prod-site)."
  value       = module.site.publisher_profile_name
}

output "site_redirect_domain_names" {
  description = "Names that 301 to the canonical site host. Empty in dev."
  value       = try(module.site_domain_redirect[0].domain_names, [])
}

output "site_redirect_distribution_id" {
  description = "The redirect distribution, or null where there is none."
  value       = try(module.site_domain_redirect[0].distribution_id, null)
}

output "site_redirect_certificate_validation_records" {
  description = "DNS records proving ownership of the redirected names, for an operator to add by hand when the zone is not managed here."
  value       = try(module.site_domain_redirect[0].certificate_validation_records, [])
}

# --- The evidence store (v1-e29-t03-evidence-buckets) -----------------------------------------
#
# v1-e29-t04-s3-blob-store and v1-e29-t05-evidence-sync-cli read these to know which bucket and
# key they are talking to, so renaming one is a change to the CLI's configuration too.

output "evidence_bucket_name" {
  description = "The bucket that is this environment's system of record for evidence."
  value       = module.evidence_store.bucket_name
}

output "evidence_bucket_arn" {
  description = "ARN of the evidence bucket."
  value       = module.evidence_store.bucket_arn
}

output "evidence_kms_key_arn" {
  description = "ARN of the customer-managed key this environment's evidence is encrypted with. v2-e10-t04 adopts this key rather than creating a second one."
  value       = module.evidence_store.kms_key_arn
}

output "evidence_kms_alias_name" {
  description = "Alias of the evidence key (alias/debate-<env>-evidence)."
  value       = module.evidence_store.kms_alias_name
}

output "evidence_prefixes" {
  description = "The documented top-level key prefixes of docs/architecture/evidence-store-layout.md, which are also what the EvidenceOperator permission set may list."
  value       = module.evidence_store.evidence_prefixes
}

output "evidence_operator_permission_set_name" {
  description = "The Identity Center permission set for everyday evidence work, as it appears in `aws configure sso`."
  value       = module.evidence_store.operator_permission_set_name
}

output "evidence_operator_profile_name" {
  description = "The name to give the operator's SSO profile for this environment's evidence (debate-dev-evidence / debate-prod-evidence)."
  value       = module.evidence_store.operator_profile_name
}

output "evidence_removal_permission_set_name" {
  description = "The Identity Center permission set used only for takedowns under the data-use policy."
  value       = module.evidence_store.removal_permission_set_name
}

output "evidence_removal_profile_name" {
  description = "The name to give the takedown SSO profile for this environment."
  value       = module.evidence_store.removal_profile_name
}

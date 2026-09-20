output "bucket_name" {
  description = "The evidence bucket. `debate-research store` (v1-e29-t05) and the runbooks name it directly rather than reading Terraform state, which is why the suffix is a committed constant."
  value       = aws_s3_bucket.evidence.id
}

output "bucket_arn" {
  description = "ARN of the evidence bucket, for policies in later tasks that grant access to it."
  value       = aws_s3_bucket.evidence.arn
}

output "bucket_regional_domain_name" {
  description = "Regional domain name of the bucket, which is what a presigned URL and an S3 event notification (V2) are built against."
  value       = aws_s3_bucket.evidence.bucket_regional_domain_name
}

# The key is exposed as three separate outputs, and the alias as its own resource, so that
# v2-e10-t04 can adopt this key with `moved` blocks instead of creating a second one and
# re-encrypting the corpus (task spec ac6).

output "kms_key_id" {
  description = "Key id of the customer-managed key this environment's evidence is encrypted with."
  value       = aws_kms_key.evidence.key_id
}

output "kms_key_arn" {
  description = "ARN of the evidence key. What a later task's IAM policy grants kms:Decrypt on."
  value       = aws_kms_key.evidence.arn
}

output "kms_alias_name" {
  description = "Alias of the evidence key (alias/debate-<env>-evidence). DebateMaintainer's guardrail denies KMS actions on alias/debate-prod-*, so the environment prefix here is load-bearing (ADR-0010 rule 4)."
  value       = aws_kms_alias.evidence.name
}

output "kms_alias_arn" {
  description = "ARN of the key alias."
  value       = aws_kms_alias.evidence.arn
}

output "evidence_prefixes" {
  description = "The documented top-level key prefixes (docs/architecture/evidence-store-layout.md). This is what the EvidenceOperator permission set may list, so a CLI or runbook that walks the store can read the list from here rather than repeating it."
  value       = local.evidence_prefixes
}

output "removable_prefixes" {
  description = "The prefixes a takedown may delete from. reports/ is deliberately not among them."
  value       = local.removable_prefixes
}

output "operator_permission_set_name" {
  description = "The Identity Center permission set for everyday evidence work, as it appears in `aws configure sso`. Null where no Identity Center instance was given."
  value       = one(aws_ssoadmin_permission_set.evidence_operator[*].name)
}

output "operator_permission_set_arn" {
  description = "ARN of the EvidenceOperator permission set."
  value       = one(aws_ssoadmin_permission_set.evidence_operator[*].arn)
}

output "operator_profile_name" {
  description = "The name to give the operator's SSO profile for this environment's evidence (debate-dev-evidence / debate-prod-evidence)."
  value       = local.operator_profile_name
}

output "removal_permission_set_name" {
  description = "The Identity Center permission set used only for takedowns under the data-use policy. Null where no Identity Center instance was given."
  value       = one(aws_ssoadmin_permission_set.evidence_removal[*].name)
}

output "removal_permission_set_arn" {
  description = "ARN of the EvidenceRemoval permission set."
  value       = one(aws_ssoadmin_permission_set.evidence_removal[*].arn)
}

output "removal_profile_name" {
  description = "The name to give the takedown SSO profile for this environment (debate-dev-evidence-removal / debate-prod-evidence-removal)."
  value       = local.removal_profile_name
}

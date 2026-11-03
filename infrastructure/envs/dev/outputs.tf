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

# --- The student evidence search pilot (v1-e39-t04-pilot-infrastructure) ----------------------
#
# docs/runbooks/evidence-search.md reads these. scripts/tub_deploy.sh does not: it derives the
# repository and function names from the environment, so a deploy never reads Terraform state.

output "evidence_search_url" {
  description = "Where students open the pilot in this environment."
  value       = module.evidence_search.pilot_url
}

output "evidence_search_login_host" {
  description = "The managed login's host, which school IT allows alongside the pilot host."
  value       = module.evidence_search.login_host
}

output "evidence_search_repository_url" {
  description = "The image repository scripts/tub_deploy.sh pushes to."
  value       = module.evidence_search.repository_url
}

output "evidence_search_function_name" {
  description = "The pilot's function."
  value       = module.evidence_search.function_name
}

output "evidence_search_function_url" {
  description = "The function URL, which refuses a direct request with 403; the runbook checks that it does."
  value       = module.evidence_search.function_url
}

output "evidence_search_distribution_id" {
  description = "The pilot's CloudFront distribution."
  value       = module.evidence_search.distribution_id
}

output "evidence_search_user_pool_id" {
  description = "The pilot's user pool."
  value       = module.evidence_search.user_pool_id
}

output "evidence_search_client_id" {
  description = "The confidential app client's id. Not a secret."
  value       = module.evidence_search.client_id
}

output "evidence_search_cookie_keys_parameter_name" {
  description = "The SecureString parameter the operator writes the session cookie keys to."
  value       = module.evidence_search.cookie_keys_parameter_name
}

output "evidence_search_audit_log_group_name" {
  description = "The append-only access audit log, kept 400 days."
  value       = module.evidence_search.audit_log_group_name
}

output "evidence_search_account_changes_log_stream_name" {
  description = "The audit stream the coach's `tub users` commands write to."
  value       = module.evidence_search.account_changes_log_stream_name
}

output "evidence_search_app_log_group_name" {
  description = "The function's application log, kept 30 days."
  value       = module.evidence_search.app_log_group_name
}

output "evidence_search_deployer_profile_name" {
  description = "The name to give the deployer's SSO profile (debate-dev-tub-deployer / debate-prod-tub-deployer)."
  value       = module.evidence_search.deployer_profile_name
}

output "evidence_search_accounts_profile_name" {
  description = "The name to give the accounts SSO profile (debate-dev-tub-accounts / debate-prod-tub-accounts)."
  value       = module.evidence_search.accounts_profile_name
}

output "caselist_password_secret_name" {
  description = "The Tabroom password secret (debate-<env>-caselist-tabroom-password), which `caselist auth set-password` writes."
  value       = module.caselist_run.password_secret_name
}

output "caselist_token_secret_name" {
  description = "The caselist token secret (debate-<env>-caselist-token), which the login task writes and the run reads."
  value       = module.caselist_run.token_secret_name
}

output "caselist_credentials_key_alias" {
  description = "The key that encrypts the two caselist secrets and nothing else."
  value       = module.caselist_run.credentials_key_alias
}

output "caselist_login_role_arn" {
  description = "The login task's role, the only reader of the Tabroom password."
  value       = module.caselist_run.login_role_arn
}

output "caselist_run_role_arn" {
  description = "The run's role, the only reader of the token."
  value       = module.caselist_run.run_role_arn
}

output "caselist_secret_writer_permission_set_name" {
  description = "The coach's writer permission set (DebateDevCaselistSecretWriter / DebateProdCaselistSecretWriter)."
  value       = module.caselist_run.credential_writer_permission_set_name
}

output "caselist_secret_writer_profile_name" {
  description = "The name to give the writer's SSO profile (debate-dev-caselist-writer / debate-prod-caselist-writer), passed as --aws-profile."
  value       = module.caselist_run.credential_writer_profile_name
}

output "caselist_login_schedule_name" {
  description = "The Wednesday login schedule. Null until caselist_image_digest is set (apply B)."
  value       = module.caselist_run.login_schedule_name
}

output "caselist_run_repository_url" {
  description = "Where scripts/caselist_run_deploy.sh pushes the run image (debate-<env>-caselist-run)."
  value       = module.caselist_run.repository_url
}

output "caselist_run_cluster_name" {
  description = "The cluster the login and run tasks run on (debate-<env>-caselist-run)."
  value       = module.caselist_run.cluster_name
}

output "caselist_run_subnet_ids" {
  description = "The run's two public subnets, where a run started by hand runs."
  value       = module.caselist_run.run_subnet_ids
}

output "caselist_run_security_group_id" {
  description = "The tasks' security group: no inbound rule, outbound HTTPS only."
  value       = module.caselist_run.run_security_group_id
}

output "caselist_run_task_definition_arn" {
  description = "The run task definition the schedule runs, pinned by digest. Null until caselist_image_digest is set (apply B)."
  value       = module.caselist_run.run_task_definition_arn
}

output "caselist_run_schedule_name" {
  description = "The Wednesday 06:00 America/Chicago run schedule. Null until caselist_image_digest is set (apply B)."
  value       = module.caselist_run.run_schedule_name
}

output "caselist_run_schedule_state" {
  description = "ENABLED or DISABLED; disabled until the cutover. Null until apply B."
  value       = module.caselist_run.run_schedule_state
}

output "caselist_run_deployer_permission_set_name" {
  description = "The run's deployer permission set (DebateDevCaselistRunDeployer / DebateProdCaselistRunDeployer)."
  value       = module.caselist_run.deployer_permission_set_name
}

output "caselist_run_deployer_profile_name" {
  description = "The name to give the deployer's SSO profile (debate-dev-caselist-run-deployer / debate-prod-caselist-run-deployer), which scripts/caselist_run_deploy.sh uses."
  value       = module.caselist_run.deployer_profile_name
}

output "caselist_alert_topic_arn" {
  description = "The alert topic (debate-<env>-caselist-run-alerts), which emails the coach when a run or login fails, a run is late, a schedule cannot start, or someone changes who may read the password."
  value       = module.caselist_run.alert_topic_arn
}

output "caselist_alert_subscription_arn" {
  description = "The coach's email subscription to the alert topic: `pending confirmation` until the link AWS emails is followed."
  value       = module.caselist_run.alert_subscription_arn
}

output "caselist_run_late_alarm_actions_enabled" {
  description = "Whether the late-run alarm emails the coach: false until the cutover's first recorded run."
  value       = module.caselist_run.late_run_alarm_actions_enabled
}

# --- Calling the routed Bedrock models (v1-e05-t08-bedrock-invoke-access) ------------------------

output "bedrock_invoker_permission_set_name" {
  description = "The permission set a model call is made with (DebateDevBedrockInvoker / DebateProdBedrockInvoker)."
  value       = module.bedrock_access.permission_set_name
}

output "bedrock_profile_name" {
  description = "The name to give the BedrockInvoker SSO profile (debate-dev-bedrock / debate-prod-bedrock): what models.aws_profile names in config/profiles/<env>.toml."
  value       = module.bedrock_access.profile_name
}

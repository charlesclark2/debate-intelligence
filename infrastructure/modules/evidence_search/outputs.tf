output "pilot_url" {
  description = "Where students open the pilot in this environment."
  value       = "${local.pilot_origin}/"
}

output "login_host" {
  description = "The managed login's host, which school IT allows alongside the pilot host (ADR-0019 (a) 7)."
  value       = local.login_host
}

output "repository_name" {
  description = "The image repository scripts/tub_deploy.sh pushes to. The script derives the same name itself."
  value       = aws_ecr_repository.function.name
}

output "repository_url" {
  description = "The repository's registry URL."
  value       = aws_ecr_repository.function.repository_url
}

output "function_name" {
  description = "The function scripts/tub_deploy.sh points at each new image."
  value       = aws_lambda_function.pilot.function_name
}

output "function_url" {
  description = "The function URL. A direct request to it is refused with 403 before the function runs; the runbook checks exactly that."
  value       = aws_lambda_function_url.pilot.function_url
}

output "distribution_id" {
  description = "The pilot's CloudFront distribution."
  value       = aws_cloudfront_distribution.pilot.id
}

output "distribution_domain_name" {
  description = "The distribution's *.cloudfront.net domain."
  value       = aws_cloudfront_distribution.pilot.domain_name
}

output "user_pool_id" {
  description = "The user pool. v1-e39-t05's `tub users` commands name it."
  value       = aws_cognito_user_pool.pilot.id
}

output "user_pool_arn" {
  description = "ARN of the user pool."
  value       = aws_cognito_user_pool.pilot.arn
}

output "client_id" {
  description = "The confidential app client's id. Not a secret; the secret is in client_secret_parameter_name."
  value       = aws_cognito_user_pool_client.web.id
}

output "client_secret_parameter_name" {
  description = "The SecureString parameter holding the app client's secret."
  value       = aws_ssm_parameter.client_secret.name
}

output "cookie_keys_parameter_name" {
  description = "The SecureString parameter holding the session cookie keys, which the operator writes."
  value       = aws_ssm_parameter.cookie_keys.name
}

output "audit_log_group_name" {
  description = "The append-only access audit log, kept 400 days (ADR-0019 (e))."
  value       = aws_cloudwatch_log_group.audit.name
}

output "account_changes_log_stream_name" {
  description = "The audit group's stream the coach's `tub users` commands write to."
  value       = aws_cloudwatch_log_stream.account_changes.name
}

output "app_log_group_name" {
  description = "The function's application log, kept 30 days."
  value       = aws_cloudwatch_log_group.app.name
}

output "function_role_arn" {
  description = "The function's role: ADR-0019's role table, exactly."
  value       = aws_iam_role.function.arn
}

output "ses_identity" {
  description = "The SES domain identity the pool sends its email codes from."
  value       = aws_sesv2_email_identity.pilot.email_identity
}

output "deployer_permission_set_name" {
  description = "The Identity Center permission set scripts/tub_deploy.sh runs as. Null where no Identity Center instance was given."
  value       = one(aws_ssoadmin_permission_set.deployer[*].name)
}

output "deployer_profile_name" {
  description = "The name to give the deployer's SSO profile (debate-dev-tub-deployer / debate-prod-tub-deployer)."
  value       = local.deployer_profile_name
}

output "accounts_permission_set_name" {
  description = "The Identity Center permission set the coach's `tub users` commands run as. Null where no Identity Center instance was given."
  value       = one(aws_ssoadmin_permission_set.accounts[*].name)
}

output "accounts_profile_name" {
  description = "The name to give the accounts SSO profile (debate-dev-tub-accounts / debate-prod-tub-accounts)."
  value       = local.accounts_profile_name
}

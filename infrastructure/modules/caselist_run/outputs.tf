output "credentials_key_arn" {
  description = "ARN of the key that encrypts the two caselist secrets and nothing else."
  value       = aws_kms_key.credentials.arn
}

output "credentials_key_alias" {
  description = "Alias of the credentials key: alias/debate-<env>-caselist-credentials."
  value       = aws_kms_alias.credentials.name
}

output "password_secret_name" {
  description = "The Tabroom password secret. `caselist.password_secret_id` defaults to this name."
  value       = aws_secretsmanager_secret.tabroom_password.name
}

output "password_secret_arn" {
  description = "ARN of the Tabroom password secret."
  value       = aws_secretsmanager_secret.tabroom_password.arn
}

output "token_secret_name" {
  description = "The caselist token secret. `caselist.token_secret_id` defaults to this name."
  value       = aws_secretsmanager_secret.token.name
}

output "token_secret_arn" {
  description = "ARN of the caselist token secret."
  value       = aws_secretsmanager_secret.token.arn
}

output "login_role_arn" {
  description = "The login task's role, the only reader of the password."
  value       = aws_iam_role.login.arn
}

output "run_role_name" {
  description = "The run's role, the only reader of the token. v1-e40-t03 and t04 add its other grants."
  value       = aws_iam_role.run.name
}

output "run_role_arn" {
  description = "ARN of the run's role."
  value       = aws_iam_role.run.arn
}

output "credential_writer_permission_set_name" {
  description = "Debate<Env>CaselistSecretWriter, the coach's writer. Null when no Identity Center instance was given."
  value       = local.create_permission_sets ? aws_ssoadmin_permission_set.credential_writer[0].name : null
}

output "credential_writer_profile_name" {
  description = "The SSO profile name the runbook configures for the writer, and passes as --aws-profile."
  value       = local.credential_writer_profile_name
}

output "login_task_definition_arn" {
  description = "The login task definition, pinned by digest. Null until login_task is set (apply B)."
  value       = local.create_login_task ? aws_ecs_task_definition.login[0].arn : null
}

output "login_schedule_name" {
  description = "The Wednesday login schedule. Null until login_task is set (apply B)."
  value       = local.create_login_task ? aws_scheduler_schedule.login[0].name : null
}

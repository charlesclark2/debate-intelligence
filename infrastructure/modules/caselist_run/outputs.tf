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
  description = "The run's role: the only reader of the token, with the everyday evidence permissions and nothing more."
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
  description = "The login task definition, pinned by digest. Null until image_digest is set (apply B)."
  value       = local.create_login_task ? aws_ecs_task_definition.login[0].arn : null
}

output "login_schedule_name" {
  description = "The Wednesday login schedule. Null until image_digest is set (apply B)."
  value       = local.create_login_task ? aws_scheduler_schedule.login[0].name : null
}

output "cluster_name" {
  description = "The run's ECS cluster, debate-<env>-caselist-run, which both tasks run on."
  value       = aws_ecs_cluster.run.name
}

output "repository_name" {
  description = "The run's image repository, debate-<env>-caselist-run, which scripts/caselist_run_deploy.sh pushes to."
  value       = aws_ecr_repository.run.name
}

output "repository_url" {
  description = "Where scripts/caselist_run_deploy.sh pushes the run image."
  value       = aws_ecr_repository.run.repository_url
}

output "run_subnet_ids" {
  description = "The run's two public subnets."
  value       = [for subnet in aws_subnet.public : subnet.id]
}

output "run_security_group_id" {
  description = "The tasks' security group: no inbound rule, outbound HTTPS only."
  value       = aws_security_group.run.id
}

output "run_log_group_name" {
  description = "The run's log group, debate-<env>-caselist-run."
  value       = aws_cloudwatch_log_group.run.name
}

output "run_task_family" {
  description = "The run task definition's family, debate-<env>-caselist-run."
  value       = local.run_family
}

output "run_task_definition_arn" {
  description = "The run task definition Terraform made, pinned by digest, which the schedule runs. Null until image_digest is set (apply B)."
  value       = local.create_run_task ? aws_ecs_task_definition.run[0].arn : null
}

output "run_schedule_name" {
  description = "The Wednesday 06:00 America/Chicago run schedule. Null until image_digest is set (apply B)."
  value       = local.create_run_task ? aws_scheduler_schedule.run[0].name : null
}

output "run_schedule_state" {
  description = "ENABLED or DISABLED. Disabled until v1-e40-t06's cutover turns run_schedule_enabled on. Null until apply B."
  value       = local.create_run_task ? aws_scheduler_schedule.run[0].state : null
}

output "deployer_permission_set_name" {
  description = "Debate<Env>CaselistRunDeployer, which scripts/caselist_run_deploy.sh runs as. Null when no Identity Center instance was given."
  value       = local.create_permission_sets ? aws_ssoadmin_permission_set.deployer[0].name : null
}

output "deployer_profile_name" {
  description = "The SSO profile name the runbook configures for the deployer, and scripts/caselist_run_deploy.sh uses by default."
  value       = local.deployer_profile_name
}

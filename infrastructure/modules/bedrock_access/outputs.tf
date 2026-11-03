output "permission_set_name" {
  description = "The Identity Center permission set that may call the routed Bedrock models, as it appears in `aws configure sso`. Null where no Identity Center instance was given."
  value       = one(aws_ssoadmin_permission_set.invoker[*].name)
}

output "permission_set_arn" {
  description = "ARN of the BedrockInvoker permission set."
  value       = one(aws_ssoadmin_permission_set.invoker[*].arn)
}

output "profile_name" {
  description = "The name to give the SSO profile for this permission set (debate-dev-bedrock / debate-prod-bedrock): what `models.aws_profile` names in config/profiles/<env>.toml."
  value       = local.profile_name
}

output "policy_json" {
  description = "The permission set's inline policy, as JSON: bedrock:InvokeModel on what the routing files name, and nothing else."
  value       = local.policy
}

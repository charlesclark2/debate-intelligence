# One environment's weekly caselist run in the cloud (ADR-0020, epic E40). This module is the one
# place its Terraform lives, called from both environment roots, so that V2's foundation
# (v2-e10-t04, v2-e10-t05) can lift its pieces out with `moved` blocks (ADR-0020, What V2
# replaces).
#
# v1-e40-t02 builds the credentials and the scheduled login:
#
#   credentials.tf        the key, the two secrets and their resource policies
#   roles.tf              the login role, and the run role with its two grants
#   credential_writer.tf  the coach's Debate<Env>CaselistSecretWriter permission set
#   login_task.tf         the login task definition and its Wednesday 03:00 schedule, once
#                         var.image_digest names a pushed image
#
# v1-e40-t03 builds the run:
#
#   network.tf            the run's VPC: public subnets, no inbound rule, outbound HTTPS, S3
#                         gateway endpoint
#   cluster.tf            the cluster and the image repository
#   run_task.tf           the run's execution role, log group, task definition and Wednesday 06:00
#                         schedule, disabled until the cutover
#   deployer.tf           the Debate<Env>CaselistRunDeployer permission set
#
# Applies are operator-run (docs/runbooks/caselist-cloud-credentials.md). There are no GitHub OIDC
# roles until v2-e10-t03, so CI never runs plan or apply against this module, and neither does an
# agent session. tests/caselist_run.tftest.hcl runs under a mocked provider.

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.name

  password_secret_name = "${var.name_prefix}-tabroom-password"
  token_secret_name    = "${var.name_prefix}-token"
  key_alias            = "alias/${var.name_prefix}-credentials"
  login_role_name      = "${var.name_prefix}-login"
  run_role_name        = "${var.name_prefix}-run"

  # A secret's ARN is its name, a hyphen and six random characters. The key policy names the two
  # secrets by these patterns because the secrets are encrypted under the key and so are created
  # after it; `??????` matches exactly the six, so no other secret's name fits.
  password_secret_arn_pattern = "arn:${local.partition}:secretsmanager:${local.region}:${local.account_id}:secret:${local.password_secret_name}-??????"
  token_secret_arn_pattern    = "arn:${local.partition}:secretsmanager:${local.region}:${local.account_id}:secret:${local.token_secret_name}-??????"

  secrets_manager_service = "secretsmanager.${local.region}.amazonaws.com"

  # An Identity Center permission set is a role in the account named AWSReservedSSO_<set>_<hash>,
  # under a path that may carry the Identity Center region. Matched by name, so a role recreated
  # when the set is reprovisioned is still the same principal here.
  sso_role_arn_prefix        = "arn:${local.partition}:iam::${local.account_id}:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_"
  break_glass_principal_arns = "${local.sso_role_arn_prefix}${var.break_glass_permission_set_name}_*"
  # ADR-0020 calls it Debate<Env>CaselistCredentialWriter, which is 33 characters in dev and 34 in
  # prod; Identity Center allows a permission set 32. This name says what the set does.
  credential_writer_set_name   = "Debate${title(var.environment)}CaselistSecretWriter"
  credential_writer_principals = "${local.sso_role_arn_prefix}${local.credential_writer_set_name}_*"

  # The alert topic is v1-e40-t05's, by the name ADR-0020 (6) gives it. The login role may publish
  # to it before it exists; the publish fails until then, and the task's non-zero exit is what
  # t05's task-state rule catches meanwhile.
  alert_topic_arn = "arn:${local.partition}:sns:${local.region}:${local.account_id}:${var.name_prefix}-run-alerts"

  ecs_tasks_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EcsTasksInThisAccountOnly"
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = { "aws:SourceAccount" = local.account_id }
        }
      },
    ]
  })
}

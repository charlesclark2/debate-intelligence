# What scripts/caselist_run_deploy.sh runs as, Debate<Env>CaselistRunDeployer (ADR-0020, What each
# E40 task builds: t03). 28 characters in dev and 29 in prod, inside Identity Center's 32.
#
# It may push an image to the run's repository, register a run task definition, and start, watch
# and stop a run on the run's cluster. The subnets and security group a run by hand starts in come
# from the root's outputs (docs/runbooks/caselist-cloud-run.md).
# It may pass the run's two roles to ECS, and never the login's: ECS checks iam:PassRole on a task
# definition's task and execution roles when it is registered and on any role override when a
# task is started, so this set can neither register a definition naming the login role nor run
# anything as it. An explicit deny says so as well, so that no later allow can loosen it. The run
# role reads the token and never the password (roles.tf), which is why a person may start a run
# and nobody may start the login (ADR-0020 (2), "Who can make the login role run").
#
# ecs:RegisterTaskDefinition and ecs:DescribeTaskDefinition take no resource, so they cannot be
# held to the run's family. What keeps a registration harmless is the pass-role rule above: any
# definition this set registers runs as the run's roles or does not register, and both schedules
# pin the revision Terraform made.
#
# Assigned to the users named in deployer_user_names, sessions of one hour, like TubDeployer.

locals {
  deployer_set_name     = "Debate${title(var.environment)}CaselistRunDeployer"
  deployer_profile_name = "${var.name_prefix}-run-deployer"

  # The login's roles by name, so the deny holds whether or not apply B has created them yet.
  login_role_arns = [
    "arn:${local.partition}:iam::${local.account_id}:role/${local.login_role_name}",
    "arn:${local.partition}:iam::${local.account_id}:role/${local.login_role_name}-execution",
  ]

  run_task_definition_arns = "arn:${local.partition}:ecs:${local.region}:${local.account_id}:task-definition/${local.run_family}:*"
  run_cluster_task_arns    = "arn:${local.partition}:ecs:${local.region}:${local.account_id}:task/${local.cluster_name}/*"

  deployer_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # `docker login` to ECR. AWS defines no resource for this action, so it cannot be scoped.
        Sid      = "SignInToTheImageRegistry"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "PushToTheRunsRepository"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:DescribeImages",
        ]
        Resource = aws_ecr_repository.run.arn
      },
      {
        # Neither action takes a resource. See the file's header for what makes this safe.
        Sid      = "RegisterARunTaskDefinition"
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
        Resource = "*"
      },
      {
        Sid    = "PassTheRunRolesToEcsOnly"
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.run.arn,
          aws_iam_role.run_execution.arn,
        ]
        Condition = {
          StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" }
        }
      },
      {
        Sid      = "NeverPassTheLoginRoles"
        Effect   = "Deny"
        Action   = "iam:PassRole"
        Resource = local.login_role_arns
      },
      {
        Sid      = "StartARunByHandOnTheRunsCluster"
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = local.run_task_definition_arns
        Condition = {
          ArnEquals = { "ecs:cluster" = aws_ecs_cluster.run.arn }
        }
      },
      {
        Sid      = "WatchAndStopARunOnTheRunsCluster"
        Effect   = "Allow"
        Action   = ["ecs:DescribeTasks", "ecs:StopTask"]
        Resource = local.run_cluster_task_arns
      },
      {
        Sid    = "ReadTheRunLog"
        Effect = "Allow"
        Action = [
          "logs:DescribeLogStreams",
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
        ]
        Resource = [
          aws_cloudwatch_log_group.run.arn,
          "${aws_cloudwatch_log_group.run.arn}:*",
        ]
      },
    ]
  })
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "deployer" {
  count = local.create_permission_sets ? 1 : 0

  name             = local.deployer_set_name
  description      = "Deploys the ${var.environment} weekly caselist run: push to ${local.repository_name}, register its task definition, start a run. Passes the run's roles, never the login's (ADR-0020)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT1H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "deployer" {
  count = local.create_permission_sets ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.deployer[0].arn
  inline_policy      = local.deployer_policy
}

data "aws_identitystore_user" "deployer" {
  for_each = local.create_permission_sets ? toset(var.deployer_user_names) : toset([])

  identity_store_id = var.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

resource "aws_ssoadmin_account_assignment" "deployer" {
  for_each = local.create_permission_sets ? toset(var.deployer_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.deployer[0].arn

  principal_id   = data.aws_identitystore_user.deployer[each.value].user_id
  principal_type = "USER"

  target_id   = local.account_id
  target_type = "AWS_ACCOUNT"
}

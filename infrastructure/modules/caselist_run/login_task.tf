# The scheduled login (ADR-0020 (2), "When the login runs" and "Who can make the login role run").
#
# Every Wednesday at 03:00 America/Chicago, three hours before the run, EventBridge Scheduler
# starts one Fargate task as the login role. Its command is `debate-research caselist auth renew`:
# read the password, log in once, write the token. A refused login is never retried, and neither
# is a start that failed: the schedule's retry policy is zero, so a wrong password costs one
# attempt a week.
#
# None of this exists until var.login_task names the run's cluster, subnets, security group and
# image (v1-e40-t03), so the credentials can be applied first ("apply A") and this second
# ("apply B"), after t03's first image push.
#
# Who can make the login role run: the task definition is Terraform's, and pins its image by
# digest and its command, and only the schedule's role (assumable by scheduler.amazonaws.com for
# this one schedule) and break-glass hold iam:PassRole on the login role. No secret reaches the
# task through ECS's `secrets` field, which would make the execution role a reader and put the
# password in the container's environment; the command reads it with the task role instead.

locals {
  create_login_task = var.login_task != null

  login_family         = "${var.name_prefix}-login"
  login_schedule_name  = "${var.name_prefix}-login"
  login_log_group_name = "${var.name_prefix}-login"
  login_container_name = "login"

  # The schedule's ARN, written out because the scheduler role's trust policy names it and the
  # schedule names the role.
  login_schedule_arn = "arn:${local.partition}:scheduler:${local.region}:${local.account_id}:schedule/default/${local.login_schedule_name}"

  login_image = local.create_login_task ? "${var.login_task.repository_url}@${var.login_task.image_digest}" : null

  # What makes the CLI the cloud login (ADR-0020 (5)): no secret, only names and switches. No AWS
  # profile, so the SDK signs with the task role.
  login_environment = [
    { name = "DEBATE_ENV", value = var.environment },
    { name = "DEBATE_ALLOW_NETWORK", value = "true" },
    { name = "DEBATE_CASELIST__API_ENABLED", value = "true" },
    { name = "DEBATE_CASELIST__TOKEN_BACKEND", value = "secretsmanager" },
    { name = "DEBATE_CASELIST__TOKEN_SECRET_ID", value = local.token_secret_name },
    { name = "DEBATE_CASELIST__PASSWORD_SECRET_ID", value = local.password_secret_name },
    { name = "DEBATE_CASELIST__SECRETS_REGION", value = local.region },
    { name = "DEBATE_STORAGE__DATA_DIR", value = "/tmp/debate-research" },
    { name = "AWS_REGION", value = local.region },
  ]

  login_container_definitions = local.create_login_task ? jsonencode([
    {
      name        = local.login_container_name
      image       = local.login_image
      essential   = true
      entryPoint  = ["debate-research"]
      command     = ["--json", "caselist", "auth", "renew"]
      environment = local.login_environment
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.login[0].name
          awslogs-region        = local.region
          awslogs-stream-prefix = local.login_container_name
        }
      }
    },
  ]) : null

  login_execution_policy = local.create_login_task ? jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # `docker pull` from ECR. AWS defines no resource for this action, so it cannot be scoped.
        Sid      = "SignInToTheImageRegistry"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "PullFromTheRunsRepository"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = var.login_task.repository_arn
      },
      {
        Sid    = "WriteTheLoginLog"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.login[0].arn}:*"
      },
    ]
  }) : null

  scheduler_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "TheLoginScheduleOnly"
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = local.account_id
            "aws:SourceArn"     = local.login_schedule_arn
          }
        }
      },
    ]
  })

  scheduler_policy = local.create_login_task ? jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RunThisLoginTaskDefinitionOnTheRunsCluster"
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = aws_ecs_task_definition.login[0].arn
        Condition = {
          ArnEquals = { "ecs:cluster" = var.login_task.cluster_arn }
        }
      },
      {
        Sid    = "PassTheLoginRolesToEcsOnly"
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.login.arn,
          aws_iam_role.login_execution[0].arn,
        ]
        Condition = {
          StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" }
        }
      },
    ]
  }) : null
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_log_group" "login" {
  count = local.create_login_task ? 1 : 0

  name              = local.login_log_group_name
  retention_in_days = var.login_log_retention_days
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_iam_role" "login_execution" {
  count = local.create_login_task ? 1 : 0

  name                 = "${var.name_prefix}-login-execution"
  description          = "Starts the ${var.environment} login task: pulls its image and writes its log. Reads no secret."
  assume_role_policy   = local.ecs_tasks_assume_role_policy
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "login_execution" {
  count = local.create_login_task ? 1 : 0

  name   = "start-the-login-task"
  role   = aws_iam_role.login_execution[0].id
  policy = local.login_execution_policy
}

resource "aws_iam_role_policies_exclusive" "login_execution" {
  count = local.create_login_task ? 1 : 0

  role_name    = aws_iam_role.login_execution[0].name
  policy_names = [aws_iam_role_policy.login_execution[0].name]
}

resource "aws_iam_role_policy_attachments_exclusive" "login_execution" {
  count = local.create_login_task ? 1 : 0

  role_name   = aws_iam_role.login_execution[0].name
  policy_arns = []
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ecs_task_definition" "login" {
  count = local.create_login_task ? 1 : 0

  family                   = local.login_family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  # The smallest Fargate size: one POST and two Secrets Manager calls (ADR-0020 (8)).
  cpu                   = "256"
  memory                = "512"
  task_role_arn         = aws_iam_role.login.arn
  execution_role_arn    = aws_iam_role.login_execution[0].arn
  container_definitions = local.login_container_definitions

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_iam_role" "scheduler" {
  count = local.create_login_task ? 1 : 0

  name                 = "${var.name_prefix}-scheduler"
  description          = "The ${var.environment} login schedule: starts the login task definition, and passes its two roles to ECS."
  assume_role_policy   = local.scheduler_assume_role_policy
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "scheduler" {
  count = local.create_login_task ? 1 : 0

  name   = "start-the-login-task"
  role   = aws_iam_role.scheduler[0].id
  policy = local.scheduler_policy
}

resource "aws_iam_role_policies_exclusive" "scheduler" {
  count = local.create_login_task ? 1 : 0

  role_name    = aws_iam_role.scheduler[0].name
  policy_names = [aws_iam_role_policy.scheduler[0].name]
}

resource "aws_iam_role_policy_attachments_exclusive" "scheduler" {
  count = local.create_login_task ? 1 : 0

  role_name   = aws_iam_role.scheduler[0].name
  policy_arns = []
}

resource "aws_scheduler_schedule" "login" {
  count = local.create_login_task ? 1 : 0

  name        = local.login_schedule_name
  group_name  = "default"
  description = "The ${var.environment} weekly caselist login, three hours before the run (ADR-0020 (2))."
  state       = var.login_schedule_enabled ? "ENABLED" : "DISABLED"

  schedule_expression          = "cron(0 3 ? * WED *)"
  schedule_expression_timezone = "America/Chicago"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.login_task.cluster_arn
    role_arn = aws_iam_role.scheduler[0].arn

    ecs_parameters {
      task_definition_arn     = aws_ecs_task_definition.login[0].arn
      task_count              = 1
      launch_type             = "FARGATE"
      platform_version        = "LATEST"
      enable_execute_command  = false
      enable_ecs_managed_tags = false

      network_configuration {
        subnets          = var.login_task.subnet_ids
        security_groups  = var.login_task.security_group_ids
        assign_public_ip = true
      }
    }

    # Never twice in a week: a start that failed is the dead-letter alarm's to report (v1-e40-t05),
    # and a refused login is not tried again.
    retry_policy {
      maximum_retry_attempts       = 0
      maximum_event_age_in_seconds = 3600
    }
  }
}

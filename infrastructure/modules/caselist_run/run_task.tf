# The weekly run (ADR-0020 (1), (5)): one on-demand Fargate task, arm64, 8 vCPU, 32 GB and 100 GiB
# of ephemeral storage, started every Wednesday at 06:00 America/Chicago, three hours after the
# login (login_task.tf), as the run role.
#
#   debate-<env>-caselist-run              its log group, and its task definition's family
#   debate-<env>-caselist-run-execution    pulls its image and writes its log; reads no secret
#   debate-<env>-caselist-run-scheduler    starts this one revision on the run's cluster
#   debate-<env>-caselist-run              the schedule, created DISABLED (run_schedule_enabled),
#                                          alone in its own schedule group of the same name
#
# The command is `debate-research --json caselist pull` under a 6-hour deadline in the container
# (ADR-0020 (1) 6): `timeout` sends the CLI SIGTERM at six hours, as `docker stop` would, and
# SIGKILL two minutes later, and the task exits non-zero. ECS's own stop gives the same two
# minutes. The caselists are `caselist.sync_caselists` in the bundled profile (ADR-0020 (5)): the
# command names none. The schedule overrides the command with `--json caselist pull --scheduled`
# (v1-e40-t48), through Scheduler's universal RunTask target; a run started by hand keeps the
# task definition's.
#
# Only the execution role pulls the image and writes the log, and no secret reaches the task
# through ECS's `secrets` field: the CLI reads the token itself, with the run role, through the
# token store's secretsmanager backend (v1-e40-t02). The environment below names that secret and
# holds nothing secret. No AWS profile: the SDK signs with the task role.
#
# The task definitions and both schedules exist once var.image_digest names a pushed image (t02's
# "apply B"). The schedule pins this revision, so what runs on Wednesday is what Terraform's plan
# showed. scripts/caselist_run_deploy.sh may register later revisions of the family, passing the
# run's two roles only, for a run started by hand; the schedule moves to a new image when
# image_digest does.

locals {
  create_run_task = var.image_digest != null

  run_family         = "${var.name_prefix}-run"
  run_schedule_name  = "${var.name_prefix}-run"
  run_log_group_name = "${var.name_prefix}-run"
  run_container_name = "run"

  # Scheduler assumes the run's scheduler role with aws:SourceArn set to the schedule's group, never
  # the schedule itself (login_task.tf says why, with AWS's page). The run's schedule is its own
  # group's only member, so the role trusts this schedule and no other.
  run_schedule_group_name = "${var.name_prefix}-run"
  run_schedule_group_arn  = "arn:${local.partition}:scheduler:${local.region}:${local.account_id}:schedule-group/${local.run_schedule_group_name}"

  # ADR-0020 (1) 2 and 6. Fargate's ephemeral storage above its 20 GiB default needs platform
  # version 1.4.0 or later, which LATEST is. 32 GB since v1-e40-t30: 16 GB, the least Fargate allows
  # at 8 vCPU, was killed for memory by the hspolicy25 import of 2026-10-31 (ADR-0020's amendment).
  run_cpu                = "8192"
  run_memory             = "32768"
  run_ephemeral_gib      = 100
  run_parse_workers      = 8
  run_deadline           = "6h"
  run_stop_grace_seconds = 120
  volume_warning_percent = 70

  # The data directory, on the ephemeral volume; the image makes it and gives it to its user.
  run_data_dir = "/var/lib/debate-research/${var.environment}"

  # What makes the CLI the cloud run (ADR-0020 (5)): names and switches, never a secret.
  # `DEBATE_STORAGE__S3__AWS_PROFILE` empty is no profile, overriding the bundled profile's SSO one.
  run_environment = [
    { name = "DEBATE_ENV", value = var.environment },
    { name = "DEBATE_ALLOW_NETWORK", value = "true" },
    { name = "DEBATE_CASELIST__API_ENABLED", value = "true" },
    { name = "DEBATE_CASELIST__TOKEN_BACKEND", value = "secretsmanager" },
    { name = "DEBATE_CASELIST__TOKEN_SECRET_ID", value = local.token_secret_name },
    { name = "DEBATE_CASELIST__SECRETS_REGION", value = local.region },
    # Bucket mode (v1-e40-t04, ADR-0020 (3) and (4)): the run restores its working copy from the
    # evidence bucket, saves its state back, and holds the bucket's run lock while it writes.
    { name = "DEBATE_CASELIST__RUN_STATE", value = "bucket" },
    { name = "DEBATE_STORAGE__DATA_DIR", value = local.run_data_dir },
    { name = "DEBATE_STORAGE__S3__AWS_PROFILE", value = "" },
    { name = "DEBATE_STORAGE__VOLUME_WARNING_PERCENT", value = tostring(local.volume_warning_percent) },
    { name = "DEBATE_PARSE__WORKERS", value = tostring(local.run_parse_workers) },
    # A failed run emails the coach through the alert topic (v1-e40-t05, ADR-0020 (6)).
    { name = "DEBATE_CASELIST__NOTIFIER", value = "sns" },
    { name = "DEBATE_CASELIST__ALERT_TOPIC_ARN", value = local.alert_topic_arn },
    { name = "AWS_REGION", value = local.region },
  ]

  # What the schedule runs (v1-e40-t48): the task definition's command, `--json caselist pull`, with
  # `--scheduled`, so v1-e40-t44's guard refuses a start within 24 hours of a recorded run. A run
  # started by hand keeps the task definition's command, and the guard never asks it.
  run_scheduled_command = ["--json", "caselist", "pull", "--scheduled"]

  # Scheduler's universal target for RunTask, and the request it sends, in the camelCase of ECS's
  # RunTask API reference (https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_RunTask.html,
  # read 2026-11-13). AWS's Scheduler pages do not say whether a templated ECS target's Input reaches
  # RunTask as overrides (read 2026-11-13; v1-e40-t48's report quotes them), and the universal target's
  # Input is documented as "the request parameters that EventBridge Scheduler sends to the target API"
  # (the PM's ruling of 2026-11-14). It is the request the templated target sent, with the override:
  # the same revision by its full ARN, which RunTask requires to match the scheduler role's Resource;
  # the same cluster by ARN, so the role's ecs:cluster condition holds; no tags, so no ecs:TagResource.
  # The scheduler role's policy is unchanged.
  #
  # The revision's ARN is in the Input, so a plan that replaces the task definition shows the whole
  # Input as known after apply. The module's tests pin it, and the runbook reads it back after the
  # apply ("The schedule passes --scheduled").
  run_task_target_arn = "arn:${local.partition}:scheduler:::aws-sdk:ecs:runTask"
  run_task_request = local.create_run_task ? {
    cluster              = aws_ecs_cluster.run.arn
    taskDefinition       = aws_ecs_task_definition.run[0].arn
    count                = 1
    launchType           = "FARGATE"
    platformVersion      = "LATEST"
    enableExecuteCommand = false
    enableECSManagedTags = false
    networkConfiguration = {
      awsvpcConfiguration = {
        subnets        = [for subnet in aws_subnet.public : subnet.id]
        securityGroups = [aws_security_group.run.id]
        assignPublicIp = "ENABLED"
      }
    }
    overrides = {
      containerOverrides = [{ name = local.run_container_name, command = local.run_scheduled_command }]
    }
  } : null

  run_image = local.create_run_task ? "${aws_ecr_repository.run.repository_url}@${var.image_digest}" : null

  run_container_definitions = local.create_run_task ? jsonencode([
    {
      name       = local.run_container_name
      image      = local.run_image
      essential  = true
      entryPoint = ["timeout", "--signal=TERM", "--kill-after=${local.run_stop_grace_seconds}s", local.run_deadline, "debate-research"]
      command    = ["--json", "caselist", "pull"]
      # An init process as PID 1 passes ECS's stop on to the CLI and reaps the parse workers.
      linuxParameters = { initProcessEnabled = true }
      stopTimeout     = local.run_stop_grace_seconds
      environment     = local.run_environment
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.run.name
          awslogs-region        = local.region
          awslogs-stream-prefix = local.run_container_name
        }
      }
    },
  ]) : null

  run_execution_policy = jsonencode({
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
        Resource = aws_ecr_repository.run.arn
      },
      {
        Sid    = "WriteTheRunLog"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.run.arn}:*"
      },
    ]
  })

  run_scheduler_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "TheRunScheduleOnly"
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = local.account_id
            "aws:SourceArn"     = local.run_schedule_group_arn
          }
        }
      },
    ]
  })

  run_scheduler_policy = local.create_run_task ? jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RunThisRunTaskDefinitionOnTheRunsCluster"
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = aws_ecs_task_definition.run[0].arn
        Condition = {
          ArnEquals = { "ecs:cluster" = aws_ecs_cluster.run.arn }
        }
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
        # A start Scheduler could not deliver goes to the run's dead-letter queue, sent with this
        # role (alerts.tf).
        Sid      = "KeepAStartThatFailed"
        Effect   = "Allow"
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.schedule_dead_letters["run"].arn
      },
    ]
  }) : null
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_log_group" "run" {
  name              = local.run_log_group_name
  retention_in_days = var.run_log_retention_days
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_iam_role" "run_execution" {
  name                 = "${var.name_prefix}-run-execution"
  description          = "Starts the ${var.environment} weekly caselist run: pulls its image and writes its log. Reads no secret."
  assume_role_policy   = local.ecs_tasks_assume_role_policy
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "run_execution" {
  name   = "start-the-run-task"
  role   = aws_iam_role.run_execution.id
  policy = local.run_execution_policy
}

resource "aws_iam_role_policies_exclusive" "run_execution" {
  role_name    = aws_iam_role.run_execution.name
  policy_names = [aws_iam_role_policy.run_execution.name]
}

resource "aws_iam_role_policy_attachments_exclusive" "run_execution" {
  role_name   = aws_iam_role.run_execution.name
  policy_arns = []
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ecs_task_definition" "run" {
  count = local.create_run_task ? 1 : 0

  family                   = local.run_family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.run_cpu
  memory                   = local.run_memory
  task_role_arn            = aws_iam_role.run.arn
  execution_role_arn       = aws_iam_role.run_execution.arn
  container_definitions    = local.run_container_definitions

  ephemeral_storage {
    size_in_gib = local.run_ephemeral_gib
  }

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_iam_role" "run_scheduler" {
  count = local.create_run_task ? 1 : 0

  name                 = "${var.name_prefix}-run-scheduler"
  description          = "The ${var.environment} run schedule: starts the run task definition, and passes the run's two roles to ECS."
  assume_role_policy   = local.run_scheduler_assume_role_policy
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "run_scheduler" {
  count = local.create_run_task ? 1 : 0

  name   = "start-the-run-task"
  role   = aws_iam_role.run_scheduler[0].id
  policy = local.run_scheduler_policy
}

resource "aws_iam_role_policies_exclusive" "run_scheduler" {
  count = local.create_run_task ? 1 : 0

  role_name    = aws_iam_role.run_scheduler[0].name
  policy_names = [aws_iam_role_policy.run_scheduler[0].name]
}

resource "aws_iam_role_policy_attachments_exclusive" "run_scheduler" {
  count = local.create_run_task ? 1 : 0

  role_name   = aws_iam_role.run_scheduler[0].name
  policy_arns = []
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_scheduler_schedule_group" "run" {
  count = local.create_run_task ? 1 : 0

  name = local.run_schedule_group_name
}

resource "aws_scheduler_schedule" "run" {
  count = local.create_run_task ? 1 : 0

  name        = local.run_schedule_name
  group_name  = aws_scheduler_schedule_group.run[0].name
  description = "The ${var.environment} weekly caselist run, three hours after the login (ADR-0020 (1), (2))."
  state       = var.run_schedule_enabled ? "ENABLED" : "DISABLED"

  # The login's day, three hours later, in the same zone: daylight saving moves both together, so
  # the run always starts after the login that renews its token.
  schedule_expression          = "cron(0 6 ? * WED *)"
  schedule_expression_timezone = "America/Chicago"

  flexible_time_window {
    mode = "OFF"
  }

  # The universal RunTask target and its request (run_task_request above, v1-e40-t48): this revision
  # on the run's cluster, as the templated target started it, with the command `--scheduled`.
  target {
    arn      = local.run_task_target_arn
    role_arn = aws_iam_role.run_scheduler[0].arn
    input    = jsonencode(local.run_task_request)

    # A launch ECS refused is tried again (v1-e40-t42, the PM's ruling of 2026-11-05): three times at
    # most, all within an hour of 06:00. On 2026-11-04 RunTask answered ServerException, nothing
    # tried again, and the week ran only because the operator started it by hand the next day.
    #
    # Why a retry cannot make a second run. Scheduler retries only an invocation that failed, and a
    # run that started is a RunTask that returned a task: whatever its container then does, that
    # Wednesday is never invoked again. A refused launch started no container, downloaded nothing and
    # took no lock. The one gap is an ambiguous answer, a task placed and an error returned: Scheduler
    # passes ECS no idempotency token, so its retry would start a second task. That task meets the
    # bucket's run lock, which `caselist pull` takes before it restores anything or calls
    # OpenCaselist; while the first run holds its lease, the second is refused (RunLockHeld),
    # downloads nothing and writes nothing. It could take the lock only after the first run had
    # finished and released it. A run has finished in 56 minutes (2026-10-28), inside the event age,
    # but three retries land far earlier than any run's end. And since v1-e40-t48 the schedule's pull
    # is `--scheduled`, which refuses to start within 24 hours of a run the bucket's log records
    # (v1-e40-t44), so a retry after the first run's end does nothing either.
    #
    # Nor would a second run spend the week's downloads again: the download ledger, five per rolling
    # 24 hours, is kept in the bucket and saved before each download, so a run starts from what is
    # left; its weeklies are already imported, and it could fetch at most the one complete archive a
    # run may. A start whose retries are spent goes to the dead-letter queue, whose alarm emails the
    # coach; a RunTask refused, or answered with a failure, emails at once (alerts.tf).
    retry_policy {
      maximum_retry_attempts       = local.schedule_retry_attempts
      maximum_event_age_in_seconds = local.schedule_event_age_in_seconds
    }

    dead_letter_config {
      arn = aws_sqs_queue.schedule_dead_letters["run"].arn
    }
  }
}

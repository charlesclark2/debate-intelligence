# What emails the coach when the cloud run or its login goes wrong, or when someone changes who may
# read the Tabroom password (ADR-0020 (6), v1-e40-t05).
#
#   debate-<env>-caselist-run-alerts          the SNS topic, with the coach's address as its one
#                                             email subscription, confirmed once by the coach
#   debate-<env>-caselist-run-stopped         a run task that stopped non-zero, or never started
#   debate-<env>-caselist-login-stopped       the same for the login task
#   debate-<env>-caselist-run-late            no run recorded in seven days: the RunsRecorded
#                                             metric from the run's log group, actions off until
#                                             the cutover's first recorded run
#   debate-<env>-caselist-login-dlq           what each schedule could not start, kept 14 days
#   debate-<env>-caselist-run-dlq
#   debate-<env>-caselist-schedule-failed     an alarm on either queue holding a message
#   debate-<env>-caselist-credentials-*       the CloudTrail rules of ADR-0020 (2): a change to the
#   debate-<env>-caselist-login-*             key, either secret's policy, the login role or its
#   debate-<env>-caselist-password-read       task definition; a read of the password by anyone but
#                                             the login role, refused reads included
#
# The run itself publishes too: `caselist.notifier = sns` in both tasks' environments sends what the
# Mac's banners say (run_task.tf, login_task.tf; the run role's caselist-alerts policy in roles.tf).
# Nothing published names a school, a team code, a file or a card, and none of it is a secret, so the
# topic is not encrypted with a key of ours: EventBridge and CloudWatch could not publish to one
# under the AWS-managed SNS key anyway.

locals {
  alert_topic_name = "${var.name_prefix}-run-alerts"

  run_stopped_rule_name   = "${var.name_prefix}-run-stopped"
  login_stopped_rule_name = "${var.name_prefix}-login-stopped"
  late_run_alarm_name     = "${var.name_prefix}-run-late"
  schedule_alarm_name     = "${var.name_prefix}-schedule-failed"

  # ADR-0020 (6): one per run that writes its record, so a week with none breaches.
  runs_recorded_namespace = "debate/caselist-run"
  runs_recorded_metric    = "RunsRecorded"

  # Fourteen days, SQS's longest, so a schedule that failed on a Wednesday is still there to read the
  # week after.
  dead_letter_retention_seconds = 1209600

  task_definition_arn_prefix = "arn:${local.partition}:ecs:${local.region}:${local.account_id}:task-definition/"
  assumed_role_arn_prefix    = "arn:${local.partition}:sts::${local.account_id}:assumed-role/"

  # A task of the family stopped with a container exit code other than 0, or never started at all
  # (an image it could not pull, a network it could not join), which has no exit code. Matched by
  # task definition ARN with the revision's colon, so `debate-<env>-caselist-run-anything` is not
  # the run; and so every revision matches, the deployer's included.
  task_stopped_pattern = {
    for which, family in { run = local.run_family, login = local.login_family } : which => jsonencode({
      source        = ["aws.ecs"]
      "detail-type" = ["ECS Task State Change"]
      detail = {
        clusterArn        = [aws_ecs_cluster.run.arn]
        lastStatus        = ["STOPPED"]
        taskDefinitionArn = [{ prefix = "${local.task_definition_arn_prefix}${family}:" }]
        "$or" = [
          { containers = { exitCode = [{ "anything-but" = 0 }] } },
          { stopCode = ["TaskFailedToStart"] },
        ]
      }
    })
  }

  # The secret's name, or its full ARN: Secrets Manager takes either as a secretId. The ARN is the
  # name, a hyphen and six random characters, so the prefix with its hyphen is this secret alone.
  secret_ids = {
    password = [local.password_secret_name, { prefix = "arn:${local.partition}:secretsmanager:${local.region}:${local.account_id}:secret:${local.password_secret_name}-" }]
    token    = [local.token_secret_name, { prefix = "arn:${local.partition}:secretsmanager:${local.region}:${local.account_id}:secret:${local.token_secret_name}-" }]
  }

  # ADR-0020 (2), "Break-glass, without widening the read": every path to reading the password is an
  # administrative act the trail records, and each of these rules emails it as it happens. Write
  # events reach a rule in the ENABLED state; a refused write is recorded too, with its errorCode.
  credential_write_rules = {
    # The key: its policy, a grant (which the key policy refuses anyway), disabling or deleting it.
    # KMS records the key as the caller named it (an id or an ARN), and the key's ARN in resources.
    credentials-key-changed = {
      description = "A change to the ${var.environment} caselist credentials key: its policy, a grant, disabling or deleting it (ADR-0020 (2))."
      pattern = {
        source        = ["aws.kms"]
        "detail-type" = ["AWS API Call via CloudTrail"]
        detail = {
          eventSource = ["kms.amazonaws.com"]
          eventName   = ["PutKeyPolicy", "CreateGrant", "DisableKey", "ScheduleKeyDeletion"]
          "$or" = [
            { resources = { ARN = [aws_kms_key.credentials.arn] } },
            { requestParameters = { keyId = [aws_kms_key.credentials.arn, aws_kms_key.credentials.key_id] } },
          ]
        }
      }
    }
    # Either secret's resource policy, or what else only break-glass may do to a secret: move it to
    # another key, rotate, delete, restore or replicate it (credentials.tf).
    credentials-secret-policy-changed = {
      description = "A change to who may read a ${var.environment} caselist secret: its resource policy, its key, its deletion (ADR-0020 (2))."
      pattern = {
        source        = ["aws.secretsmanager"]
        "detail-type" = ["AWS API Call via CloudTrail"]
        detail = {
          eventSource       = ["secretsmanager.amazonaws.com"]
          eventName         = [for action in local.secret_administration_actions : trimprefix(action, "secretsmanager:")]
          requestParameters = { secretId = concat(local.secret_ids.password, local.secret_ids.token) }
        }
      }
    }
    # Any IAM write naming the login role: its policies, its trust, its boundary, its deletion.
    login-role-changed = {
      description = "An IAM change to the ${var.environment} caselist login role, the only reader of the Tabroom password (ADR-0020 (2))."
      pattern = {
        source        = ["aws.iam"]
        "detail-type" = ["AWS API Call via CloudTrail"]
        detail = {
          eventSource       = ["iam.amazonaws.com"]
          requestParameters = { roleName = [local.login_role_name] }
        }
      }
    }
    # A task definition that names the login role, or a new revision of its family; or the login
    # family run by anyone but its schedule's role, which could override its command.
    login-task-changed = {
      description = "A task definition naming the ${var.environment} caselist login role, or the login task run by anyone but its schedule (ADR-0020 (2))."
      pattern = {
        source        = ["aws.ecs"]
        "detail-type" = ["AWS API Call via CloudTrail"]
        detail = {
          eventSource = ["ecs.amazonaws.com"]
          "$or" = [
            { eventName = ["RegisterTaskDefinition"], requestParameters = { taskRoleArn = [aws_iam_role.login.arn] } },
            { eventName = ["RegisterTaskDefinition"], requestParameters = { executionRoleArn = [aws_iam_role.login.arn] } },
            { eventName = ["RegisterTaskDefinition"], requestParameters = { family = [local.login_family] } },
            {
              eventName = ["RunTask", "StartTask"]
              requestParameters = { taskDefinition = [
                local.login_family,
                { prefix = "${local.login_family}:" },
                { prefix = "${local.task_definition_arn_prefix}${local.login_family}:" },
              ] }
              userIdentity = { arn = [{ "anything-but" = { prefix = "${local.assumed_role_arn_prefix}${var.name_prefix}-scheduler/" } }] }
            },
          ]
        }
      }
    }
  }

  # A read of the password by anyone but the login role, refused or not. GetSecretValue is a
  # read-only event, which reaches a rule only in the ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS
  # state (ADR-0020 (6)). The login role's own reads are its task sessions, assumed-role/<role>/<id>;
  # every other caller has an ARN outside that prefix, the account root and IAM users included.
  # BatchGetSecretValue is matched whatever it names: it can select by filter, and nothing here uses it.
  password_read_pattern = jsonencode({
    source        = ["aws.secretsmanager"]
    "detail-type" = ["AWS API Call via CloudTrail"]
    detail = {
      eventSource  = ["secretsmanager.amazonaws.com"]
      userIdentity = { arn = [{ "anything-but" = { prefix = "${local.assumed_role_arn_prefix}${local.login_role_name}/" } }] }
      "$or" = [
        { eventName = ["GetSecretValue"], requestParameters = { secretId = local.secret_ids.password } },
        { eventName = ["BatchGetSecretValue"] },
      ]
    }
  })

  # What the coach reads: the event, who, when, and whether it was refused. Never a value.
  credential_event_input_paths = {
    event     = "$.detail.eventName"
    principal = "$.detail.userIdentity.arn"
    time      = "$.detail.eventTime"
    refused   = "$.detail.errorCode"
  }

  # An SNS target takes a template that is one JSON string, delivered as the email's text. Written
  # out, not jsonencode()d: jsonencode escapes `<` and `>`, and EventBridge would no longer see the
  # placeholders. No text here holds a double quote.
  task_stopped_message = {
    run   = "\"The ${var.environment} weekly caselist run task stopped with exit code <exit_code> (<stop_code>: <reason>). Task <task>. Read its log, debate-${var.environment}-caselist-run, and debate-research caselist runs --remote; docs/runbooks/caselist-cloud-run.md.\""
    login = "\"The ${var.environment} weekly caselist login task stopped with exit code <exit_code> (<stop_code>: <reason>). Task <task>. The run three hours later uses the previous token if it still works; docs/runbooks/caselist-cloud-credentials.md.\""
  }

  task_stopped_input_paths = {
    task      = "$.detail.taskArn"
    exit_code = "$.detail.containers[0].exitCode"
    stop_code = "$.detail.stopCode"
    reason    = "$.detail.stoppedReason"
  }

  alert_topic_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "TheseRulesPublish"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = concat(
              [aws_cloudwatch_event_rule.task_stopped["run"].arn, aws_cloudwatch_event_rule.task_stopped["login"].arn],
              [for name in sort(keys(local.credential_write_rules)) : aws_cloudwatch_event_rule.credential_write[name].arn],
              [aws_cloudwatch_event_rule.password_read.arn],
            )
          }
        }
      },
      {
        Sid       = "TheseAlarmsPublish"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = {
          ArnEquals    = { "aws:SourceArn" = [aws_cloudwatch_metric_alarm.late_run.arn, aws_cloudwatch_metric_alarm.schedule_failed.arn] }
          StringEquals = { "aws:SourceAccount" = local.account_id }
        }
      },
    ]
  })
}

# ---------------------------------------------------------------------------------------------
# The topic and the coach's subscription
# ---------------------------------------------------------------------------------------------

# tflint-ignore: aws_resource_missing_tags
resource "aws_sns_topic" "alerts" {
  name         = local.alert_topic_name
  display_name = "Debate ${var.environment} caselist run"
}

# The run and login roles publish through IAM (roles.tf); a policy here would only repeat it. The
# rules and alarms are services, and publish only through this.
resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = local.alert_topic_policy
}

# An email subscription stays pending until the coach follows the link AWS sends, once
# (docs/runbooks/caselist-cloud-run.md). Until then nothing published reaches anyone.
resource "aws_sns_topic_subscription" "coach" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------------------------------------------------------
# A task that stopped non-zero, or never started: the run, and the login
# ---------------------------------------------------------------------------------------------

# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_event_rule" "task_stopped" {
  for_each = { run = local.run_stopped_rule_name, login = local.login_stopped_rule_name }

  name          = each.value
  description   = "The ${var.environment} caselist ${each.key} task stopped with a non-zero exit code, or never started (ADR-0020 (6))."
  event_pattern = local.task_stopped_pattern[each.key]
  state         = "ENABLED"
}

resource "aws_cloudwatch_event_target" "task_stopped" {
  for_each = aws_cloudwatch_event_rule.task_stopped

  rule      = each.value.name
  target_id = "tell-the-coach"
  arn       = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths    = local.task_stopped_input_paths
    input_template = local.task_stopped_message[each.key]
  }
}

# ---------------------------------------------------------------------------------------------
# A late run: no run recorded in seven days
# ---------------------------------------------------------------------------------------------

# One per `--json caselist pull` envelope that carries the run's record: under `data` for a run that
# succeeded, under `error.details` for one that ended with a failed stage. A dry run records nothing
# (`run_record` is null), so the rehearsal never counts. A run that raised before recording a stage
# writes its record without printing it, and is announced as a failed run instead.
resource "aws_cloudwatch_log_metric_filter" "runs_recorded" {
  name           = "${var.name_prefix}-runs-recorded"
  log_group_name = aws_cloudwatch_log_group.run.name
  pattern        = "{ ($.command = \"caselist pull\") && (($.data.run_record.run_id = \"*\") || ($.error.details.run_record.run_id = \"*\")) }"

  metric_transformation {
    name      = local.runs_recorded_metric
    namespace = local.runs_recorded_namespace
    value     = "1"
    unit      = "Count"
  }
}

# Seven one-day periods, each breaching: a week with no run. Missing data breaches, because a week
# with no run is a week with no data. So a new alarm is in ALARM at once, and its actions stay off
# until the cutover's first recorded run (var.late_run_alarm_actions_enabled; ADR-0020 (4) 6).
# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_metric_alarm" "late_run" {
  alarm_name        = local.late_run_alarm_name
  alarm_description = "No ${var.environment} weekly caselist run has recorded itself in seven days: the Wednesday run did not start, or did not finish. Read the run's log (debate-${var.environment}-caselist-run) and the schedule; docs/runbooks/caselist-cloud-run.md."

  namespace           = local.runs_recorded_namespace
  metric_name         = local.runs_recorded_metric
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 7
  datapoints_to_alarm = 7
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  actions_enabled = var.late_run_alarm_actions_enabled
  alarm_actions   = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------------------------
# A schedule that could not start its task
# ---------------------------------------------------------------------------------------------

# Where EventBridge Scheduler puts an invocation it could not deliver: a RunTask refused, a role it
# could not assume. Neither schedule retries (login_task.tf, run_task.tf), so each failure is here
# at once. The message names the schedule. Encrypted with SQS's own key.
# tflint-ignore: aws_resource_missing_tags
resource "aws_sqs_queue" "schedule_dead_letters" {
  for_each = toset(["login", "run"])

  name                      = "${var.name_prefix}-${each.key}-dlq"
  message_retention_seconds = local.dead_letter_retention_seconds
  sqs_managed_sse_enabled   = true
}

# Either queue holding a message. One alarm over both, as ADR-0020 (8) counts it: the email names the
# alarm, and the queue that holds the message names the schedule.
# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_metric_alarm" "schedule_failed" {
  alarm_name          = local.schedule_alarm_name
  alarm_description   = "A ${var.environment} caselist schedule could not start its task. The message in ${aws_sqs_queue.schedule_dead_letters["login"].name} or ${aws_sqs_queue.schedule_dead_letters["run"].name} names the schedule; docs/runbooks/caselist-cloud-run.md."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  # An idle queue stops reporting: no data is no message.
  treat_missing_data = "notBreaching"

  metric_query {
    id          = "held"
    expression  = "FILL(login, 0) + FILL(run, 0)"
    label       = "Messages a schedule could not deliver"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = aws_sqs_queue.schedule_dead_letters

    content {
      id = metric_query.key

      metric {
        namespace   = "AWS/SQS"
        metric_name = "ApproximateNumberOfMessagesVisible"
        dimensions  = { QueueName = metric_query.value.name }
        stat        = "Maximum"
        period      = 300
      }
    }
  }

  actions_enabled = true
  alarm_actions   = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------------------------
# Who may read the password: the CloudTrail rules (ADR-0020 (2) and (6))
# ---------------------------------------------------------------------------------------------

# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_event_rule" "credential_write" {
  for_each = local.credential_write_rules

  name          = "${var.name_prefix}-${each.key}"
  description   = each.value.description
  event_pattern = jsonencode(each.value.pattern)
  # Write events, refused ones included, reach a rule in the default state.
  state = "ENABLED"
}

resource "aws_cloudwatch_event_target" "credential_write" {
  for_each = aws_cloudwatch_event_rule.credential_write

  rule      = each.value.name
  target_id = "tell-the-coach"
  arn       = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths    = local.credential_event_input_paths
    input_template = "\"${each.value.description} <event> by <principal> at <time>; refused: <refused>. If nobody you know did this, docs/runbooks/caselist-cloud-credentials.md.\""
  }
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_event_rule" "password_read" {
  name          = "${var.name_prefix}-password-read"
  description   = "The ${var.environment} Tabroom password read, or a read refused, by anyone but the login role (ADR-0020 (2))."
  event_pattern = local.password_read_pattern
  # GetSecretValue is read-only, and reaches a rule only in this state.
  state = "ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS"
}

resource "aws_cloudwatch_event_target" "password_read" {
  rule      = aws_cloudwatch_event_rule.password_read.name
  target_id = "tell-the-coach"
  arn       = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths    = local.credential_event_input_paths
    input_template = "\"The ${var.environment} Tabroom password: <event> by <principal> at <time>; refused: <refused>. Only the weekly login reads it. If nobody you know did this, docs/runbooks/caselist-cloud-credentials.md.\""
  }
}

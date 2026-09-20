# Budgets, billing alerts and cost anomaly detection.
#
# The account also carries unrelated personal projects, so every budget here filters on the
# Project cost allocation tag: without that filter these numbers would report someone else's
# spend. Those tags must be activated in Billing, which can only happen after this applies (a tag
# key is activatable only once AWS has seen a resource carrying it) - see the runbook. Until they
# are, these budgets report zero, which is the failure mode the test alert in the runbook catches.
#
# AWS Budgets notifies; it never stops spend. Hard model quotas arrive with E19.

locals {
  budget_notification_emails = var.budget_notification_emails

  budget_project_filter = format("user:Project$%s", var.project)
}

resource "aws_budgets_budget" "environment_monthly" {
  for_each = var.monthly_budget_usd

  name         = "${var.name_prefix}-${each.key}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(each.value)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = [local.budget_project_filter]
  }

  cost_filter {
    name   = "TagKeyValue"
    values = [format("user:Environment$%s", each.key)]
  }

  # 50 and 80 are early warnings; 100 actual means the cap is already spent, so the forecast
  # notification is the one that arrives in time to act on.
  dynamic "notification" {
    for_each = [50, 80, 100]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = local.budget_notification_emails
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = local.budget_notification_emails
  }

  tags = {
    Name        = "${var.name_prefix}-${each.key}-monthly"
    Environment = each.key
    Purpose     = "monthly-cost-budget"
  }
}

# Model spend is the line item most likely to move suddenly - a loop in a research workflow costs
# far more per hour than storage does. It gets its own budget so Bedrock does not hide inside the
# environment totals.
resource "aws_budgets_budget" "bedrock_monthly" {
  name         = "${var.name_prefix}-shared-bedrock-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.bedrock_monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Bedrock"]
  }

  cost_filter {
    name   = "TagKeyValue"
    values = [local.budget_project_filter]
  }

  dynamic "notification" {
    for_each = [50, 80, 100]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = local.budget_notification_emails
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = local.budget_notification_emails
  }

  tags = {
    Name        = "${var.name_prefix}-shared-bedrock-monthly"
    Environment = "shared"
    Purpose     = "model-spend-budget"
  }
}

# Budgets only fire against a threshold somebody guessed in advance. Anomaly detection catches
# the shape of spend changing - a new service switched on, a job retrying in a loop - well below
# the monthly cap.
resource "aws_ce_anomaly_monitor" "project" {
  name         = "${var.name_prefix}-shared-spend-monitor"
  monitor_type = "CUSTOM"

  monitor_specification = jsonencode({
    Tags = {
      Key          = "Project"
      Values       = [var.project]
      MatchOptions = ["EQUALS"]
    }
  })

  tags = {
    Name        = "${var.name_prefix}-shared-spend-monitor"
    Environment = "shared"
    Purpose     = "cost-anomaly-detection"
  }
}

resource "aws_ce_anomaly_subscription" "project" {
  name      = "${var.name_prefix}-shared-spend-alerts"
  frequency = "DAILY"

  monitor_arn_list = [aws_ce_anomaly_monitor.project.arn]

  dynamic "subscriber" {
    for_each = toset(local.budget_notification_emails)

    content {
      type    = "EMAIL"
      address = subscriber.value
    }
  }

  # At V1 scale a $10 unexpected swing is already worth a look; percentage thresholds are
  # useless against a baseline of a few dollars.
  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = [tostring(var.cost_anomaly_threshold_usd)]
    }
  }

  tags = {
    Name        = "${var.name_prefix}-shared-spend-alerts"
    Environment = "shared"
    Purpose     = "cost-anomaly-detection"
  }
}

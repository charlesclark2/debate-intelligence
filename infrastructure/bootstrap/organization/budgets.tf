# Budgets, billing alerts and cost anomaly detection.
#
# The account also carries unrelated personal projects, so the environment budgets and the anomaly
# monitor filter on a cost allocation tag: without that filter these numbers would report someone
# else's spend. Those tags report spend only while they are Active as cost allocation tags, which
# modules/cost_allocation_tags below keeps them (v1-e05-t18). Were they inactive, these budgets would
# report zero, which is the failure mode the test alert in the runbook catches.
#
# The model spend budget is the exception: model charges carry no cost allocation tag, so it filters
# on the services and usage types they are billed under instead (modules/model_spend_budget).
#
# AWS Budgets notifies; it never stops spend. Hard model quotas arrive with E19.

locals {
  budget_notification_emails = var.budget_notification_emails
}

resource "aws_budgets_budget" "environment_monthly" {
  for_each = var.monthly_budget_usd

  name         = "${var.name_prefix}-${each.key}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(each.value)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Environment only, deliberately. AWS Budgets stores every TagKeyValue filter under one key and
  # ORs the values, so adding the Project filter here would widen this budget to "Environment=dev
  # OR Project=debate-intelligence" - both environments at once - rather than narrowing it. The
  # legacy CostFilters API has no way to AND two tag filters and the provider exposes no
  # filter_expression, so the project scope is carried by the Environment values being ours.
  #
  # Failure mode if another project in this account ever adopts an Environment tag: this budget
  # over-counts and alerts early, which is the safe direction. The quarterly check in the runbook
  # is where that gets caught.
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
# far more per hour than storage does. It gets its own budget so model calls do not hide inside the
# environment totals. The budget, its limit, its notices and its filter live in the module, where its
# tests can read them (v1-e05-t16-bedrock-budget-alarm).
module "model_spend_budget" {
  source = "../../modules/model_spend_budget"

  name_prefix         = var.name_prefix
  notification_emails = var.model_budget_notification_emails
}

# The budget v1-e29-t01 created here, debate-shared-bedrock-monthly, is the one the module now
# holds: same name, updated in place, never destroyed and created again.
moved {
  from = aws_budgets_budget.bedrock_monthly
  to   = module.model_spend_budget.aws_budgets_budget.model_spend
}

# The Project and Environment cost allocation tags the budgets and the anomaly monitor filter on, kept
# Active. The operator activated both by hand on 2026-10-30, before this module existed.
module "cost_allocation_tags" {
  source = "../../modules/cost_allocation_tags"
}

# Both tags were already Active when this module arrived, so two import blocks adopted them into
# state, applied on 2026-10-31 (v1-e05-t18). They were removed once both tags were in state
# (v1-e05-t19): here they did nothing more, and in a new account they would fail the whole root's
# plan until AWS has seen both keys. A new account creates the tags instead (the runbook's step 5).

# The monitor's tag key is a variable; the module's keys are fixed. If they ever differ, the monitor
# filters on a key nothing keeps Active and reads $0.
check "anomaly_monitor_tag_is_kept_active" {
  assert {
    condition     = contains(module.cost_allocation_tags.tag_keys, var.project_tag_key)
    error_message = "The cost anomaly monitor filters on user:${var.project_tag_key}, which modules/cost_allocation_tags does not keep Active, so the monitor reads $0."
  }
}

# Budgets only fire against a threshold somebody guessed in advance. Anomaly detection catches
# the shape of spend changing - a new service switched on, a job retrying in a loop - well below
# the monthly cap.
resource "aws_ce_anomaly_monitor" "project" {
  name         = "${var.name_prefix}-shared-spend-monitor"
  monitor_type = "CUSTOM"

  # "user:Project", not "Project": Cost Explorer stores user-defined tag keys in their cost
  # allocation form and returns them that way, so the bare key reads as permanent drift and
  # Terraform replaces the monitor on every apply - discarding the ~10 days of history it needs
  # before it can detect anything.
  # The explicit nulls are not noise: Cost Explorer returns every unused expression member, and
  # the provider compares the encoded JSON as a string. Omit them and the config never matches
  # what AWS stores, so every plan wants to replace the monitor.
  monitor_specification = jsonencode({
    And            = null
    CostCategories = null
    Dimensions     = null
    Not            = null
    Or             = null
    Tags = {
      Key          = "user:${var.project_tag_key}"
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

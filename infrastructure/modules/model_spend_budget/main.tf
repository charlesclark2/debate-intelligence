# The account's model spend, held to the coach's ceiling (v1-e05-t16-bedrock-budget-alarm).
#
# The ceiling is $100 a month across dev and prod, $50 in each profile, on the condition that model
# work is never duplicated between them (the PM's amendment of 2026-10-27). The budget's notices are
# in dollars, as the coach gave them: $50 (the coach's first preference), $80 and $100 of actual
# spend, and $100 of forecast spend, which is the one that arrives in time to act on.
#
# AWS Budgets notifies; it never stops spend. What refuses a call is the usage log's monthly limit,
# `models.budget_usd_monthly` (v1-e05-t15). This budget watches what AWS actually bills, including
# calls that log never sees.

locals {
  budget_name = "${var.name_prefix}-shared-bedrock-monthly"

  monthly_limit_usd   = 100
  actual_notices_usd  = [50, 80, 100]
  forecast_notice_usd = 100

  # What this project's model calls are billed under, read from Cost Explorer by the operator on
  # 2026-10-29 (the session report's Counts). Claude and Cohere models bill as AWS Marketplace
  # services named after the model; Titan bills under Amazon Bedrock itself.
  #
  # The filter is service AND usage type: AWS Budgets ORs the values inside one filter key and ANDs
  # different keys. Amazon Bedrock also bills Nova Micro tokens that are not this project's, and the
  # usage-type key is what leaves them out.
  #
  # A model that has never been billed has no name here yet. The 5.5 models of prod's routes are
  # added by v1-e05-t17, after their first billed call, by re-running the same counts.
  model_services = [
    "Amazon Bedrock",
    "Claude Haiku 4.5 (Amazon Bedrock Edition)",
    "Claude Sonnet 4.6 (Amazon Bedrock Edition)",
    "Cohere Rerank v3.5 (Amazon Bedrock Edition)",
  ]

  model_usage_types = [
    "USE1-MP:USE1_InputTokenCount-Units",
    "USE1-MP:USE1_OutputTokenCount-Units",
    "USE1-MP:USE1_search_units-Units",
    "USE1-TitanEmbeddingV2-Text-input-tokens",
  ]
}

resource "aws_budgets_budget" "model_spend" {
  name         = local.budget_name
  budget_type  = "COST"
  limit_amount = tostring(local.monthly_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # No Project tag here. Model charges carry no cost allocation tag (every row of the counts had an
  # empty Project), so ANDing one in would hold this budget at $0.
  cost_filter {
    name   = "Service"
    values = local.model_services
  }

  cost_filter {
    name   = "UsageType"
    values = local.model_usage_types
  }

  dynamic "notification" {
    for_each = local.actual_notices_usd

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.notification_emails
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = local.forecast_notice_usd
    threshold_type             = "ABSOLUTE_VALUE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.notification_emails
  }

  # Project, Owner, CostCenter and ManagedBy reach this budget through the organization root's
  # provider `default_tags`, which tflint cannot see when it lints this directory on its own; linting
  # the root follows the module call and does check them.
  # tflint-ignore: aws_resource_missing_tags
  tags = {
    Name        = local.budget_name
    Environment = "shared"
    Purpose     = "model-spend-budget"
  }
}

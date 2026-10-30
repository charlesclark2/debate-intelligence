# Skeleton for the red run: the Bedrock budget exactly as v1-e29-t01 left it in
# bootstrap/organization/budgets.tf ($40, percentage notices, forecast at 80%, Amazon Bedrock AND
# the Project tag). Replaced by the real module in the next commit.

locals {
  budget_name = "${var.name_prefix}-shared-bedrock-monthly"
}

resource "aws_budgets_budget" "model_spend" {
  name         = local.budget_name
  budget_type  = "COST"
  limit_amount = tostring(40)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Bedrock"]
  }

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$debate-intelligence"]
  }

  dynamic "notification" {
    for_each = [50, 80, 100]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.notification_emails
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.notification_emails
  }

  # tflint-ignore: aws_resource_missing_tags
  tags = {
    Name        = local.budget_name
    Environment = "shared"
    Purpose     = "model-spend-budget"
  }
}

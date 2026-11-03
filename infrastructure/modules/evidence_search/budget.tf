# The pilot's own monthly budget (ADR-0019 (g)): $10 an environment, against an expected cost of
# about forty cents for both together. It notifies; it never stops spend.
#
# Scoped like the Bedrock budget in infrastructure/bootstrap/organization/budgets.tf, by two
# different filter keys, which AWS Budgets ANDs: this environment's Environment tag, and the
# services the pilot runs on. CloudFront is shared with the website, whose cost is a few cents, so
# the budget over-counts slightly, which is the safe direction. The S3 and KMS calls that fetch
# the index are counted in the evidence store's environment budget, not here.

locals {
  budget_services = [
    "AWS Lambda",
    "Amazon CloudFront",
    "Amazon Cognito",
    "Amazon Simple Email Service",
    "Amazon EC2 Container Registry (ECR)",
    "AmazonCloudWatch",
  ]
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_budgets_budget" "pilot_monthly" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = local.budget_services
  }

  cost_filter {
    name   = "TagKeyValue"
    values = [format("user:Environment$%s", var.environment)]
  }

  dynamic "notification" {
    for_each = [80, 100]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.budget_notification_emails
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_notification_emails
  }
}

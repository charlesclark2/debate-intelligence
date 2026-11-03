# Offline tests for the model_spend_budget module: the account's model spend held to the coach's
# ceiling (task v1-e05-t16-bedrock-budget-alarm).
#
# `mock_provider "aws"` means no credentials, no network and no AWS account.
#
#   terraform -chdir=infrastructure/modules/model_spend_budget init -backend=false
#   terraform -chdir=infrastructure/modules/model_spend_budget test
#
# What these runs hold the module to (ac2):
#
#   * one cost budget, debate-shared-bedrock-monthly, of 100 USD a month;
#   * the filter: the four services and the four usage types the operator's Cost Explorer counts
#     found model calls billed under (2026-10-29), written out by hand below (working agreement 6),
#     and no other filter key, so no Project tag;
#   * four notices in dollars: actual spend above $50, $80 and $100, forecast spend above $100,
#     each to the addresses given and to nobody else.
#
# That the module grants nothing (no permission set, no account assignment, no other resource) is
# held by tests/infrastructure/test_model_spend_budget_grants_nothing.py: a Terraform test cannot
# list a module's resources.
#
# The address below is invented.

mock_provider "aws" {}

variables {
  name_prefix         = "debate"
  notification_emails = ["coach@example.org"]
}

run "one_budget_of_100_usd_a_month" {
  command = apply

  assert {
    condition     = aws_budgets_budget.model_spend.name == "debate-shared-bedrock-monthly" && output.budget_name == "debate-shared-bedrock-monthly"
    error_message = "The budget keeps the name it has carried since v1-e29-t01, so the moved block updates it in place."
  }

  assert {
    condition     = aws_budgets_budget.model_spend.budget_type == "COST" && aws_budgets_budget.model_spend.time_unit == "MONTHLY"
    error_message = "The budget is a monthly cost budget."
  }

  assert {
    condition     = tonumber(aws_budgets_budget.model_spend.limit_amount) == 100 && aws_budgets_budget.model_spend.limit_unit == "USD"
    error_message = "The limit is the coach's ceiling: 100 USD a month."
  }
}

run "the_filter_is_the_counted_services_and_usage_types" {
  command = apply

  assert {
    condition     = toset([for f in aws_budgets_budget.model_spend.cost_filter : f.name]) == toset(["Service", "UsageType"])
    error_message = "The filter has two keys, Service and UsageType, and no other: no Project tag."
  }

  assert {
    condition = toset(flatten([for f in aws_budgets_budget.model_spend.cost_filter : f.values if f.name == "Service"])) == toset([
      "Amazon Bedrock",
      "Claude Haiku 4.5 (Amazon Bedrock Edition)",
      "Claude Sonnet 4.6 (Amazon Bedrock Edition)",
      "Cohere Rerank v3.5 (Amazon Bedrock Edition)",
    ])
    error_message = "The Service values are exactly the four services the counts found model calls billed under."
  }

  assert {
    condition = toset(flatten([for f in aws_budgets_budget.model_spend.cost_filter : f.values if f.name == "UsageType"])) == toset([
      "USE1-MP:USE1_InputTokenCount-Units",
      "USE1-MP:USE1_OutputTokenCount-Units",
      "USE1-MP:USE1_search_units-Units",
      "USE1-TitanEmbeddingV2-Text-input-tokens",
    ])
    error_message = "The UsageType values are exactly the four usage types the counts found, which leaves out Amazon Bedrock's Nova Micro tokens."
  }
}

run "four_notices_in_dollars" {
  command = apply

  assert {
    condition = toset([
      for n in aws_budgets_budget.model_spend.notification :
      format("%s %s %s %s", n.notification_type, n.comparison_operator, n.threshold, n.threshold_type)
      ]) == toset([
      "ACTUAL GREATER_THAN 50 ABSOLUTE_VALUE",
      "ACTUAL GREATER_THAN 80 ABSOLUTE_VALUE",
      "ACTUAL GREATER_THAN 100 ABSOLUTE_VALUE",
      "FORECASTED GREATER_THAN 100 ABSOLUTE_VALUE",
    ])
    error_message = "The notices are actual spend above $50, $80 and $100 and forecast spend above $100, in dollars, and no others."
  }

  assert {
    condition     = length(aws_budgets_budget.model_spend.notification) == 4
    error_message = "There are exactly four notices."
  }

  assert {
    condition = alltrue([
      for n in aws_budgets_budget.model_spend.notification :
      toset(n.subscriber_email_addresses) == toset(["coach@example.org"]) && try(length(n.subscriber_sns_topic_arns), 0) == 0
    ])
    error_message = "Every notice goes to the addresses given, by email, and to no topic."
  }
}

run "a_budget_nobody_receives_is_refused" {
  command = plan

  variables {
    notification_emails = []
  }

  expect_failures = [var.notification_emails]
}

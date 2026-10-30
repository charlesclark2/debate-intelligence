output "budget_name" {
  description = "The budget's name, for confirming a notice came from it and for `aws budgets describe-budget`."
  value       = aws_budgets_budget.model_spend.name
}

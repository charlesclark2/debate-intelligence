variable "name_prefix" {
  description = <<-EOT
    Resource-name prefix, `debate` (ADR-0010). The budget is account-wide, so it takes the `shared`
    scope: debate-shared-bedrock-monthly, the name the budget has carried since v1-e29-t01.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 2-21 characters."
  }
}

variable "notification_emails" {
  description = <<-EOT
    Who receives the budget's four notices: the coach's address, from the organization root's
    gitignored terraform.tfvars (model_budget_notification_emails). Never committed.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.notification_emails) > 0
    error_message = "At least one notification email is required; a budget nobody receives is not a control."
  }
}

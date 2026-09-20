variable "aws_region" {
  description = "Primary region for every resource in this root. ADR-0010 pins this to us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project tag applied to every resource, and the prefix of every resource name."
  type        = string
  default     = "debate-intelligence"
}

variable "name_prefix" {
  description = <<-EOT
    Short prefix for resource names. ADR-0010 requires names of the form
    debate-<environment>-<purpose> so that IAM policies can separate environments by
    resource-name prefix, not only by tag.
  EOT
  type        = string
  default     = "debate"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 2-21 characters."
  }
}

variable "owner" {
  description = "Owner tag: the email of the adult maintainer accountable for these resources."
  type        = string
}

variable "cost_center" {
  description = "CostCenter tag, used to separate this project's spend from others in the account."
  type        = string
  default     = "debate-intelligence"
}

variable "identity_center_user_names" {
  description = <<-EOT
    IAM Identity Center user names (adult maintainers only) that receive the permission sets
    defined in identity.tf. Students never appear here: the platform gives them no AWS access
    of any kind (architecture proposal section 14).
  EOT
  type        = list(string)
  default     = []
}

variable "break_glass_user_names" {
  description = <<-EOT
    Subset of identity_center_user_names allowed to assume DebateBreakGlassAdmin. Kept separate
    so that adding a maintainer does not silently hand out administrator access.
  EOT
  type        = list(string)
  default     = []
}

variable "monthly_budget_usd" {
  description = <<-EOT
    Monthly cost cap per environment, in USD. V1 spend is S3 storage for caselist evidence plus
    light Bedrock use; these are alert thresholds, not hard limits - AWS Budgets notifies, it
    does not stop spend.
  EOT
  type        = map(number)
  default = {
    dev  = 25
    prod = 50
  }

  validation {
    condition     = alltrue([for env in keys(var.monthly_budget_usd) : contains(["dev", "prod"], env)])
    error_message = "Only dev and prod budgets may be defined (ADR-0013: there is no stage environment)."
  }
}

variable "bedrock_monthly_budget_usd" {
  description = <<-EOT
    Monthly cap for Amazon Bedrock spend across both environments, as early warning on model
    cost before the ModelRouter quotas of E19 exist.
  EOT
  type        = number
  default     = 40
}

variable "budget_notification_emails" {
  description = "Email addresses that receive budget and cost-anomaly alerts."
  type        = list(string)

  validation {
    condition     = length(var.budget_notification_emails) > 0
    error_message = "At least one notification email is required; a budget nobody receives is not a control."
  }
}

variable "cost_anomaly_threshold_usd" {
  description = "Absolute dollar impact above which a detected cost anomaly raises an alert."
  type        = number
  default     = 10
}

variable "cloudtrail_noncurrent_version_retention_days" {
  description = "Days to keep noncurrent versions of CloudTrail log objects before expiring them."
  type        = number
  default     = 365
}

variable "cloudtrail_log_retention_days" {
  description = <<-EOT
    Days to keep current CloudTrail log objects. The trail is the audit boundary for a
    single-account setup where environments are separated only by tag and name (ADR-0010), so
    this should not be shortened without a replacement control.
  EOT
  type        = number
  default     = 400

  validation {
    condition     = var.cloudtrail_log_retention_days >= 365
    error_message = "Keep at least a year of management events: the trail is the only after-the-fact check on the tag boundary."
  }
}

variable "project_tag_key" {
  description = <<-EOT
    Tag key carrying the project name. Cost Explorer and AWS Budgets refer to user-defined tags
    as `user:<key>`, so this is the bare key and the `user:` prefix is added where those APIs
    need it.
  EOT
  type        = string
  default     = "Project"
}

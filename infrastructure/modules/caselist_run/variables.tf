variable "name_prefix" {
  description = <<-EOT
    Full resource-name prefix for this environment's caselist run, following ADR-0010's
    debate-<environment>-<purpose> rule: `debate-dev-caselist` or `debate-prod-caselist`. It names
    the two secrets, the key's alias, the roles, the login task and its schedule (ADR-0020 (2)), so
    the two environments can never share one.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,40}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 3-41 characters, starting with a letter."
  }
}

variable "environment" {
  description = "Which environment this is: dev or prod (ADR-0013 allows no third). Names the writer permission set: DebateDevCaselistSecretWriter, DebateProdCaselistSecretWriter."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "break_glass_permission_set_name" {
  description = <<-EOT
    The Identity Center permission set Terraform applies under, and the only identity allowed to
    administer the credentials key or change either secret's policy (ADR-0020 (2)). Its role in the
    account is matched by name, `AWSReservedSSO_<name>_*`, so a reprovisioned role keeps the grant.
  EOT
  type        = string
  default     = "DebateBreakGlassAdmin"
}

variable "identity_center_instance_arn" {
  description = <<-EOT
    IAM Identity Center instance that owns the CaselistSecretWriter permission set, read by the
    calling root from `aws_ssoadmin_instances`. Null creates no permission set, which is what any
    reuse outside this account wants.
  EOT
  type        = string
  default     = null
}

variable "identity_store_id" {
  description = "Identity store behind identity_center_instance_arn, used to resolve credential_writer_user_names. Required when that list is non-empty."
  type        = string
  default     = null

  validation {
    condition     = var.identity_store_id != null || length(var.credential_writer_user_names) == 0
    error_message = "identity_store_id is required when credential_writer_user_names is set: user names are resolved through the identity store."
  }
}

variable "credential_writer_user_names" {
  description = <<-EOT
    The Identity Center user assigned this environment's CaselistSecretWriter permission set:
    the coach, who writes the Tabroom password with `caselist auth set-password` and never reads it
    back. One person at most (ADR-0020 (2)). Supplied through the gitignored owner.auto.tfvars,
    because it is a person's name and the repository is public.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.credential_writer_user_names) <= 1
    error_message = "credential_writer_user_names names one person at most: the coach whose Tabroom account the run uses (ADR-0020 (2))."
  }
}

variable "login_task" {
  description = <<-EOT
    Where the scheduled login task runs, and which image it runs: the run's cluster, its public
    subnets and security group, and the run's image repository with the digest of a pushed image
    (v1-e40-t03). Null, the default, creates the credentials, the roles and the writer permission
    set only, which need no network ("apply A"). Set, it adds the login task definition, pinned by
    digest, and its Wednesday schedule ("apply B"), applied after t03's first image push.
  EOT
  type = object({
    cluster_arn        = string
    subnet_ids         = list(string)
    security_group_ids = list(string)
    repository_arn     = string
    repository_url     = string
    image_digest       = string
  })
  default = null

  validation {
    condition     = var.login_task == null || can(regex("^sha256:[0-9a-f]{64}$", var.login_task.image_digest))
    error_message = "login_task.image_digest must be an image digest, sha256:<64 hex digits>, never a tag: the login role runs exactly the image Terraform names (ADR-0020 (2))."
  }

  validation {
    condition     = var.login_task == null || (length(var.login_task.subnet_ids) > 0 && length(var.login_task.security_group_ids) > 0)
    error_message = "login_task needs at least one subnet and one security group."
  }
}

variable "login_schedule_enabled" {
  description = "Whether the Wednesday login schedule is enabled. On by default once the task exists; off pauses the weekly login without destroying anything."
  type        = bool
  default     = true
}

variable "login_log_retention_days" {
  description = "How long the login task's own log is kept. It says when a login ran and how it ended, never a credential."
  type        = number
  default     = 90
}

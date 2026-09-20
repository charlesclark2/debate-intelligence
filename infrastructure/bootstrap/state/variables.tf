variable "aws_region" {
  description = "Region holding the state bucket. ADR-0010 pins this to us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment this state bucket serves: dev or prod. One bucket per environment (ADR-0010)."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "project" {
  description = "Project tag applied to every resource in this root."
  type        = string
  default     = "debate-intelligence"
}

variable "name_prefix" {
  description = <<-EOT
    Short prefix for resource names. ADR-0010 requires debate-<environment>-<purpose> so that
    IAM policies can separate environments by resource-name prefix and not only by tag; the
    DebateMaintainer permission set denies debate-prod-* on exactly this pattern.
  EOT
  type        = string
  default     = "debate"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 2-21 characters."
  }
}

variable "state_bucket_suffix" {
  description = <<-EOT
    Suffix that makes the bucket name globally unique, since S3 bucket names are a global
    namespace and debate-dev-tfstate is not a name this project can count on owning. It is a
    fixed, committed string rather than a random_id so that the environment roots' backend
    blocks — which cannot contain expressions — can name the bucket directly. It is not a
    secret, and it deliberately is not the account id: the runbook records bucket names.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{6,12}$", var.state_bucket_suffix))
    error_message = "state_bucket_suffix must be 6-12 lowercase alphanumeric characters (for example the output of `openssl rand -hex 4`)."
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

variable "noncurrent_version_retention_days" {
  description = <<-EOT
    Days to keep superseded state versions. Versioning is the undo for a bad apply or a
    corrupted state file, so this is a recovery window, not a cleanup setting; state objects are
    kilobytes, and keeping a quarter of them costs nothing worth saving.
  EOT
  type        = number
  default     = 90

  validation {
    condition     = var.noncurrent_version_retention_days >= 30
    error_message = "Keep at least 30 days of superseded state: a state file is only known to be wrong after someone notices."
  }
}

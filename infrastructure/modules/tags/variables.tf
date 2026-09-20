variable "project" {
  description = "Project tag. Budgets and cost anomaly detection filter on it (ADR-0010), so it is the same string in every environment."
  type        = string
  default     = "debate-intelligence"

  validation {
    condition     = length(var.project) > 0
    error_message = "project must not be empty: an untagged resource is invisible to the cost controls."
  }
}

variable "environment" {
  description = "Environment tag: dev or prod. ADR-0013 allows no third environment, and ADR-0010 makes this tag half of the boundary between them."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "owner" {
  description = "Owner tag: the email of the adult maintainer accountable for these resources. Supplied per operator, never committed."
  type        = string

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.owner))
    error_message = "owner must be an email address."
  }
}

variable "cost_center" {
  description = "CostCenter tag, separating this project's spend from the unrelated projects sharing the account (ADR-0010)."
  type        = string
  default     = "debate-intelligence"
}

variable "additional_tags" {
  description = <<-EOT
    Extra tags merged on top of the standard five, for roots that carry something worth
    recording beyond them (for example SpecRef, naming the task that owns the resources).
    A key from the standard set cannot be overridden here.
  EOT
  type        = map(string)
  default     = {}

  validation {
    condition = length(setintersection(
      keys(var.additional_tags),
      ["Project", "Environment", "Owner", "CostCenter", "ManagedBy"],
    )) == 0
    error_message = "additional_tags must not redefine Project, Environment, Owner, CostCenter or ManagedBy; those are the tagging standard."
  }
}

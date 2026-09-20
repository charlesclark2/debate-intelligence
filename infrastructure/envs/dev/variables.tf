variable "aws_region" {
  description = "Region for every resource in this root. ADR-0010 pins this to us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = <<-EOT
    Which environment this root is: dev or prod. Set in terraform.tfvars beside this file, and
    checked against the directory name in main.tf, because in a single-account setup (ADR-0010)
    this value is half of what keeps prod resources apart from dev ones.
  EOT
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

variable "owner" {
  description = <<-EOT
    Owner tag: the email of the adult maintainer accountable for these resources. Not committed;
    supply it through a gitignored owner.auto.tfvars beside this file or TF_VAR_owner.
  EOT
  type        = string
}

variable "cost_center" {
  description = "CostCenter tag, used to separate this project's spend from others in the account."
  type        = string
  default     = "debate-intelligence"
}

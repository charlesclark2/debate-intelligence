variable "name_prefix" {
  description = <<-EOT
    Resource-name prefix for this environment's Bedrock access, following ADR-0010's
    debate-<environment>-<purpose> rule: `debate-dev-bedrock` or `debate-prod-bedrock`. It is the
    name of the SSO profile the runbook configures, which is what `models.aws_profile` names in
    config/profiles/<env>.toml.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,40}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 3-41 characters, starting with a letter."
  }

  validation {
    condition     = strcontains(var.name_prefix, "-${var.environment}-")
    error_message = "name_prefix must contain the environment, as in debate-${var.environment}-bedrock (ADR-0010: debate-<environment>-<purpose>)."
  }
}

variable "environment" {
  description = "Which environment this access belongs to: dev or prod. ADR-0013 allows no third."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "routing_files" {
  description = <<-EOT
    Paths of the model routing files whose Bedrock routes the permission set may call:
    config/model_routing.dev.yaml and config/model_routing.prod.yaml. Every identifier the grant
    names is read from these files, so a route the files do not name is never granted, and a
    routing change that needs a new grant shows up in the next plan.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.routing_files) > 0
    error_message = "routing_files must name at least one routing file: with none, the permission set would grant nothing."
  }

  validation {
    # A geographic profile is granted on the foundation models in the regions it routes to, and
    # those regions are written in this module (local.profile_destination_regions), not read from
    # AWS. A profile of any other geography would be granted on regions nobody checked.
    condition = alltrue(flatten([
      for path in var.routing_files : [
        for route in values(yamldecode(file(path)).routes) :
        try(route.inference_profile, null) == null || startswith(try(route.inference_profile, ""), "us.")
      ]
    ]))
    error_message = "Every inference_profile in routing_files must be a us. geographic profile: the regions this module grants the models behind a profile in are written for us. alone (local.profile_destination_regions)."
  }
}

variable "identity_center_instance_arn" {
  description = <<-EOT
    The IAM Identity Center instance that owns the BedrockInvoker permission set, read by the
    calling root from `aws_ssoadmin_instances`. Null creates no permission set, which is what any
    reuse outside this account needs.
  EOT
  type        = string
  default     = null
}

variable "identity_store_id" {
  description = "Identity store behind identity_center_instance_arn, used to resolve user names to ids. Required when any user name is given."
  type        = string
  default     = null
}

variable "invoker_user_names" {
  description = <<-EOT
    Identity Center user names assigned this environment's BedrockInvoker permission set: adult
    maintainers only, never students. Supplied through the gitignored owner.auto.tfvars, because
    these are people's names and the repository is public.
  EOT
  type        = list(string)
  default     = []
}

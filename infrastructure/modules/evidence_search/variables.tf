variable "name_prefix" {
  description = <<-EOT
    Full resource-name prefix for this environment's pilot, following ADR-0010's
    debate-<environment>-<purpose> rule: `debate-dev-tub` or `debate-prod-tub` (ADR-0019 (a) 1).
    It names the repository, the function, the user pool, the log groups, the parameters and the
    budget, so the two environments can never share one.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,40}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 3-41 characters, starting with a letter."
  }

  validation {
    # ADR-0010 rule 2: the environment is part of every resource name, so an IAM policy can
    # separate dev from prod by prefix and not only by tag.
    condition     = strcontains(var.name_prefix, "-${var.environment}-")
    error_message = "name_prefix must contain the environment, as in debate-${var.environment}-tub (ADR-0010: debate-<environment>-<purpose>)."
  }
}

variable "environment" {
  description = <<-EOT
    Which environment this pilot belongs to: dev or prod (ADR-0013 allows no third). It decides
    the two settings ADR-0019 fixes per environment rather than leaving to tfvars: the user pool's
    deletion protection is on in prod, and dev sends `X-Robots-Tag: noindex, nofollow`.
  EOT
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "pilot_host" {
  description = <<-EOT
    The host students open: tub.wfbdebate.com in prod, tub.dev.wfbdebate.com in dev (ADR-0019
    (a) 6). The login host is `auth.` in front of it. Unlike the website there is no empty escape
    hatch: the user pool's callback URLs and its custom domain both need the real name.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.pilot_host))
    error_message = "pilot_host must be a lowercase hostname such as tub.wfbdebate.com."
  }
}

variable "route53_zone_id" {
  description = <<-EOT
    The existing hosted zone holding pilot_host (wfbdebate.com), read by the calling root through a
    data source and never created (ADR-0019 (a) 6). The certificate's validation records, the
    alias records for both hosts and the SES identity's DKIM records are written into it.
  EOT
  type        = string
}

variable "evidence_bucket_arn" {
  description = <<-EOT
    ARN of this environment's evidence bucket (module.evidence_store.bucket_arn). The function may
    read three key patterns in it and nothing else. The bucket itself, its Block Public Access
    settings and its policy are not touched by this module (ADR-0019, gate item 3).
  EOT
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::[a-z0-9.-]+$", var.evidence_bucket_arn))
    error_message = "evidence_bucket_arn must be an S3 bucket ARN such as arn:aws:s3:::debate-dev-evidence-a7508de8."
  }
}

variable "evidence_kms_key_arn" {
  description = "ARN of the evidence bucket's key (module.evidence_store.kms_key_arn). The function may decrypt with it through S3 only."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:", var.evidence_kms_key_arn))
    error_message = "evidence_kms_key_arn must be a KMS key ARN."
  }
}

variable "budget_limit_usd" {
  description = "The pilot's own monthly budget in this environment. ADR-0019 (g): $10, against an expected cost well under a dollar."
  type        = number
  default     = 10

  validation {
    condition     = var.budget_limit_usd > 0
    error_message = "budget_limit_usd must be positive."
  }
}

variable "budget_notification_emails" {
  description = <<-EOT
    Where the budget alarm writes. Supplied by the calling root from the gitignored
    owner.auto.tfvars, never committed, because these are people's addresses and the repository
    is public.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.budget_notification_emails) > 0
    error_message = "budget_notification_emails needs at least one address: AWS Budgets refuses a notification with no subscriber."
  }
}

variable "identity_center_instance_arn" {
  description = <<-EOT
    IAM Identity Center instance that owns the TubDeployer and TubAccounts permission sets, read by
    the calling root from `aws_ssoadmin_instances`. Null creates neither, which is what any reuse
    outside this account wants.
  EOT
  type        = string
  default     = null
}

variable "identity_store_id" {
  description = "Identity store behind identity_center_instance_arn, used to resolve the user names below. Required when either list is non-empty."
  type        = string
  default     = null

  validation {
    condition     = var.identity_store_id != null || length(concat(var.deployer_user_names, var.accounts_user_names)) == 0
    error_message = "identity_store_id is required when deployer_user_names or accounts_user_names is set: user names are resolved through the identity store."
  }
}

variable "deployer_user_names" {
  description = <<-EOT
    Identity Center user names assigned this environment's TubDeployer permission set, which
    `scripts/tub_deploy.sh` runs as. Adult maintainers only. Supplied through the gitignored
    owner.auto.tfvars, because these are people's names and the repository is public.
  EOT
  type        = list(string)
  default     = []
}

variable "accounts_user_names" {
  description = <<-EOT
    Identity Center user names assigned this environment's TubAccounts permission set, which the
    coach's `tub users` commands run as (v1-e39-t05). Adult maintainers only, never a student.
    Supplied through the gitignored owner.auto.tfvars.
  EOT
  type        = list(string)
  default     = []
}

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

variable "evidence_bucket_arn" {
  description = "ARN of this environment's evidence bucket, which the run reads from and publishes to. From module.evidence_store.bucket_arn in the calling root."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::[a-z0-9][a-z0-9.-]+$", var.evidence_bucket_arn))
    error_message = "evidence_bucket_arn must be an S3 bucket ARN."
  }
}

variable "evidence_key_arn" {
  description = "ARN of the key this environment's evidence is encrypted with. From module.evidence_store.kms_key_arn. The one key the run's evidence policy may use."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/[0-9a-f-]+$", var.evidence_key_arn))
    error_message = "evidence_key_arn must be a KMS key ARN."
  }
}

variable "evidence_policy_json" {
  description = <<-EOT
    The everyday evidence permissions, as the EvidenceOperator permission set holds them
    (module.evidence_store.operator_policy_json): list the documented prefixes, read, publish, tag
    a retired parsed/ directory, use the evidence key. The run role holds exactly this document
    beside its read of the token (ADR-0020 (2) and (3)), so the run can never do more with the
    evidence than the operator's everyday credential does. Refused if any statement allows a
    delete, a wildcard action, or anything outside S3 and the evidence key's use.
  EOT
  type        = string

  validation {
    condition = alltrue([
      for statement in try(jsondecode(var.evidence_policy_json).Statement, [{ Action = "*" }]) :
      alltrue([
        for action in flatten([statement.Action]) :
        contains([
          "s3:ListBucket",
          "s3:ListBucketVersions",
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:GetObjectTagging",
          "s3:PutObjectTagging",
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ], action)
      ])
      if statement.Effect == "Allow"
    ])
    error_message = "evidence_policy_json may allow only the everyday evidence actions: no s3:DeleteObject, no s3:DeleteObjectVersion, no wildcard, nothing outside S3 and the evidence key's use (ADR-0020 (3); the everyday credential never deletes)."
  }

  validation {
    condition = alltrue([
      for statement in try(jsondecode(var.evidence_policy_json).Statement, [{ Resource = "*" }]) :
      alltrue([
        for resource in flatten([statement.Resource]) :
        resource == var.evidence_bucket_arn || startswith(resource, "${var.evidence_bucket_arn}/") || resource == var.evidence_key_arn
      ])
    ])
    error_message = "evidence_policy_json may name this environment's evidence bucket, its objects and its evidence key, and nothing else: not the credentials key, not another bucket."
  }

}

variable "image_digest" {
  description = <<-EOT
    Digest of a run image pushed to this module's repository by scripts/caselist_run_deploy.sh,
    sha256:<64 hex digits>. Both task definitions run it by digest, never by tag: the login task
    and the run (ADR-0020 (1), (2)). Null, the default, creates the network, the cluster, the
    repository, the run's roles and the deployer permission set, which need no image; set, it adds
    the two task definitions and their Wednesday schedules (t02's "apply B"), after the first push.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.image_digest == null || can(regex("^sha256:[0-9a-f]{64}$", var.image_digest))
    error_message = "image_digest must be an image digest, sha256:<64 hex digits>, never a tag: the login role and the run role run exactly the image Terraform names (ADR-0020 (2))."
  }
}

variable "vpc_cidr" {
  description = "Address range of the run's own VPC (ADR-0020 (1) 5). Two public subnets split it in half. Nothing peers with it, so it only has to be a valid private range."
  type        = string
  default     = "10.40.0.0/24"

  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 1, 1)) && tonumber(split("/", var.vpc_cidr)[1]) <= 27
    error_message = "vpc_cidr must be an IPv4 CIDR block of /27 or larger, so it splits into two subnets."
  }
}

variable "run_schedule_enabled" {
  description = <<-EOT
    Whether the Wednesday run schedule is enabled once it exists. Off by default: until
    v1-e40-t04's bucket mode and its lock are applied, a cloud run would start from an empty data
    directory, download every archive again and publish without the bucket's lock (the PM's
    ruling for v1-e40-t03). ADR-0020 (4)'s cutover (v1-e40-t06) turns it on.
  EOT
  type        = bool
  default     = false
}

variable "run_log_retention_days" {
  description = "How long the run's own log is kept: its JSON summary, counts and stage times, never a credential or a disclosure's path."
  type        = number
  default     = 90
}

variable "deployer_user_names" {
  description = <<-EOT
    The Identity Center users assigned this environment's CaselistRunDeployer permission set,
    which scripts/caselist_run_deploy.sh runs as: push an image, register a run task definition
    passing the run's roles, start and watch a run. Adult maintainers only. Supplied through the
    gitignored owner.auto.tfvars, because they are people's names and the repository is public.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = var.identity_store_id != null || length(var.deployer_user_names) == 0
    error_message = "identity_store_id is required when deployer_user_names is set: user names are resolved through the identity store."
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

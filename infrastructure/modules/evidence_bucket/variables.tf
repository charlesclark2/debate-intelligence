variable "name_prefix" {
  description = <<-EOT
    Full resource-name prefix for this environment's evidence store, following ADR-0010's
    debate-<environment>-<purpose> rule: `debate-dev-evidence` or `debate-prod-evidence`. It names
    the bucket, the KMS alias, the permission sets and the SSO profiles the operator uses, so the
    two environments can never share a resource and an IAM policy can separate them by name.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,40}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 3-41 characters, starting with a letter."
  }

  validation {
    # ADR-0010 rule 2, and rule 4 depends on it: DebateMaintainer denies s3:* on debate-prod-*
    # buckets and kms:* on alias/debate-prod-*. A prefix that does not carry its environment in
    # that position silently removes the boundary between dev and prod evidence.
    condition     = strcontains(var.name_prefix, "-${var.environment}-")
    error_message = "name_prefix must contain the environment, as in debate-${var.environment}-evidence (ADR-0010: debate-<environment>-<purpose>)."
  }
}

variable "environment" {
  description = "Which environment this evidence store belongs to: dev or prod. ADR-0013 allows no third."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "bucket_suffix" {
  description = <<-EOT
    Suffix that makes the bucket name unique in S3's global namespace, as the state buckets of
    v1-e29-t02 and the site buckets of v1-e36-t02 already do. A committed constant, not an account
    id and not a `random_id`: the runbook, `debate-research store` (v1-e29-t05) and every removal
    have to be able to name the bucket without reading Terraform state.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{4,16}$", var.bucket_suffix))
    error_message = "bucket_suffix must be 4-16 lowercase letters and digits."
  }
}

variable "noncurrent_version_retention_days" {
  description = <<-EOT
    How long a superseded object version is kept before it is expired: 365 in prod, 30 in dev.
    Versioning is the recovery path for a bad publish or a wrong delete (ADR-0003, ADR-0010), and
    this is how long that path stays open. Current versions are never expired by this rule.
  EOT
  type        = number
  default     = 365

  validation {
    condition     = var.noncurrent_version_retention_days >= 1 && floor(var.noncurrent_version_retention_days) == var.noncurrent_version_retention_days
    error_message = "noncurrent_version_retention_days must be a whole number of days, at least 1."
  }
}

variable "noncurrent_version_transition_days" {
  description = <<-EOT
    How long a superseded version stays in S3 Standard before moving to Standard-IA. S3's own
    floor for a noncurrent-version transition to STANDARD_IA is 30 days, which a validation
    enforces. When noncurrent_version_retention_days is not longer than this, the transition is
    omitted entirely rather than written as a rule S3 would reject: a version that expires on the
    day it would move has nothing to move. That is what happens in dev, where both are 30.
  EOT
  type        = number
  default     = 30

  validation {
    condition     = var.noncurrent_version_transition_days >= 30
    error_message = "noncurrent_version_transition_days must be at least 30: S3 rejects an earlier noncurrent-version transition to STANDARD_IA."
  }
}

variable "additional_reader_principal_arns" {
  description = <<-EOT
    Extra IAM principals granted read and presign access to this bucket: `s3:ListBucket`,
    `s3:GetObject`, `s3:GetObjectVersion` and `kms:Decrypt`/`kms:DescribeKey`, in the bucket
    policy and the key policy. Never write, never delete, never KMS encrypt or admin (task spec:
    forbidden).

    Empty in V1, which is the whole point of the input existing now: the V2 worker and API roles
    (v2-e10-t03, v2-e35-debate-tub) attach themselves by adding their ARNs here, without editing
    this module and without a second key.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for principal_arn in var.additional_reader_principal_arns : can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:(role|user)/", principal_arn))])
    error_message = "Each entry must be an IAM role or user ARN, as in arn:aws:iam::111122223333:role/debate-prod-api."
  }
}

variable "identity_center_instance_arn" {
  description = <<-EOT
    The IAM Identity Center instance that owns the EvidenceOperator and EvidenceRemoval permission
    sets, read by the calling root from `aws_ssoadmin_instances`. Null creates neither permission
    set, which is what this module's own tests use and what any reuse outside this account needs.
  EOT
  type        = string
  default     = null
}

variable "identity_store_id" {
  description = "Identity store behind identity_center_instance_arn, used to resolve user names to ids. Required when any user name is given."
  type        = string
  default     = null
}

variable "evidence_operator_user_names" {
  description = <<-EOT
    Identity Center user names assigned this environment's EvidenceOperator permission set — adult
    maintainers only, never students. Supplied through the gitignored owner.auto.tfvars, because
    these are people's names and the repository is public.
  EOT
  type        = list(string)
  default     = []
}

variable "evidence_removal_user_names" {
  description = <<-EOT
    Identity Center user names assigned this environment's EvidenceRemoval permission set, which
    is the only credential in the account that can delete evidence and its noncurrent versions.

    One person (the task spec: assigned to Charlie alone), enforced by the validation below.
    Takedowns under docs/policies/caselist-data-use.md are destructive and irreversible — there is
    no version left to restore from — so the list of people who can run one is a decision, not a
    default.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.evidence_removal_user_names) <= 1
    error_message = "evidence_removal_user_names holds at most one user: the EvidenceRemoval permission set is assigned to the accountable operator alone (v1-e29-t03 ac3). Widening it is a spec change."
  }
}

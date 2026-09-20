# Offline tests for the evidence_bucket module.
#
# `mock_provider "aws"` means no credentials, no network and no AWS account: Terraform generates
# the values a real provider would return, and everything these runs assert on is either
# configured in the module or mocked here on purpose. That is what lets them run in pre-commit and
# in CI while every plan and apply stays an operator step
# (docs/process/working-agreements.md section 2).
#
#   terraform -chdir=infrastructure/modules/evidence_bucket init -backend=false
#   terraform -chdir=infrastructure/modules/evidence_bucket test
#
# `init` first — `terraform test` does not initialise for you, and scripts/terraform_checks.sh has
# usually done it already.
#
# What is worth asserting here is the set of properties the module exists to guarantee and that a
# later edit could quietly drop: the bucket is private, versioned and encrypted with this
# environment's own key; no lifecycle rule expires a current version outside exports/; the
# everyday credential cannot delete anything; the takedown credential can delete disclosed
# material and nothing else; and an additional reader is a reader.
#
# No real caselist data and no student names appear here (task spec: forbidden). The bucket names,
# account id and user names below are invented.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "111122223333"
    }
  }

  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }

  mock_data "aws_identitystore_user" {
    defaults = {
      # The provider validates the shape of an identity store user id.
      user_id = "a1b2c3d4e5-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::debate-mock-evidence"
    }
  }

  # Mocked rather than generated, because the bucket policy, the key policy and both permission-set
  # policies are asserted to name this exact key and nothing else.
  mock_resource "aws_kms_key" {
    defaults = {
      arn    = "arn:aws:kms:us-east-1:111122223333:key/mock-evidence-key"
      key_id = "mock-evidence-key"
    }
  }

  mock_resource "aws_ssoadmin_permission_set" {
    defaults = {
      arn = "arn:aws:sso:::permissionSet/ssoins-mock/ps-mock"
    }
  }
}

# The default shape is dev: a 30-day recovery window on superseded versions, which is short
# enough that the Standard-IA transition drops out (main.tf).
variables {
  name_prefix                       = "debate-dev-evidence"
  environment                       = "dev"
  bucket_suffix                     = "a7508de8"
  noncurrent_version_retention_days = 30
}

# ---------------------------------------------------------------------------------------------
# The bucket itself (ac1)
# ---------------------------------------------------------------------------------------------

run "bucket_is_private_versioned_and_kms_encrypted" {
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.evidence.block_public_acls,
      aws_s3_bucket_public_access_block.evidence.block_public_policy,
      aws_s3_bucket_public_access_block.evidence.ignore_public_acls,
      aws_s3_bucket_public_access_block.evidence.restrict_public_buckets,
    ])
    error_message = "All four block-public-access flags must be on: three of the four still leave a way to publish the bucket."
  }

  assert {
    condition     = aws_s3_bucket_ownership_controls.evidence.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "Object ownership must be BucketOwnerEnforced, so no ACL can grant access to evidence."
  }

  assert {
    condition     = aws_s3_bucket_versioning.evidence.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning must be on: ADR-0003 makes this bucket the system of record, and a superseded version is the only recovery path a single-account setup has."
  }

  assert {
    # `rule` is a set here, so it has no addressable index.
    condition = alltrue([
      for rule in aws_s3_bucket_server_side_encryption_configuration.evidence.rule :
      rule.apply_server_side_encryption_by_default[0].sse_algorithm == "aws:kms" &&
      rule.apply_server_side_encryption_by_default[0].kms_master_key_id == aws_kms_key.evidence.arn
    ])
    error_message = "Default encryption must be SSE-KMS with this module's own key, not SSE-S3 and not the AWS-managed aws/s3 key (ADR-0010 rule 4)."
  }

  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_server_side_encryption_configuration.evidence.rule :
      rule.bucket_key_enabled
    ])
    error_message = "S3 Bucket Keys must be on, or a backfill pays for one KMS call per object (v1-e30-t06)."
  }

  assert {
    condition     = aws_s3_bucket.evidence.bucket == "debate-dev-evidence-a7508de8"
    error_message = "The bucket name must be <name_prefix>-<bucket_suffix>, as the runbook, the removal procedure and `debate-research store` all assume."
  }

  assert {
    condition     = !aws_s3_bucket.evidence.force_destroy
    error_message = "force_destroy must stay false: with it, `terraform destroy` would empty the system of record before deleting it."
  }
}

run "bucket_policy_requires_tls_and_this_key" {
  assert {
    condition = anytrue([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      try(statement.Condition.Bool["aws:SecureTransport"], null) == "false" if statement.Effect == "Deny"
    ])
    error_message = "The bucket must deny requests that are not over TLS."
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      statement if statement.Effect == "Allow"
    ]) == 0
    error_message = "With no additional readers the bucket policy must contain no Allow at all: access comes from the permission sets, and an Allow here would widen what they carefully do not grant."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      try(statement.Condition.StringNotEquals["s3:x-amz-server-side-encryption-aws-kms-key-id"], null) == aws_kms_key.evidence.arn
    ])
    error_message = "An upload that names another KMS key must be denied; default encryption alone does not stop a client that asks for something else."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      try(statement.Condition.Null["s3:x-amz-server-side-encryption"], "false") == "false"
      if try(statement.Sid, "") == "DenyUploadsThatOverrideEvidenceEncryption"
    ])
    error_message = "The encryption-override deny must be guarded by a Null condition, or every ordinary PutObject that omits the header would be denied."
  }
}

# ---------------------------------------------------------------------------------------------
# Lifecycle (ac2)
# ---------------------------------------------------------------------------------------------

run "dev_ages_out_superseded_versions_after_thirty_days" {
  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "age-out-superseded-evidence-versions"
    ]).noncurrent_version_expiration[0].noncurrent_days == 30
    error_message = "dev must expire superseded versions after 30 days."
  }

  assert {
    condition = length(one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "age-out-superseded-evidence-versions"
    ]).noncurrent_version_transition) == 0
    error_message = "With a 30-day retention there must be no Standard-IA transition: S3 rejects a version that expires on the day it would move, and a 30-day-minimum storage class would cost more than Standard."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "abort-incomplete-multipart-uploads"
    ]).abort_incomplete_multipart_upload[0].days_after_initiation == 7
    error_message = "Incomplete multipart uploads must be aborted after 7 days; their parts are billed and invisible in a normal listing."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "expire-bulk-export-archives"
    ]).expiration[0].days == 1
    error_message = "Bulk export archives under exports/ must expire after 1 day."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "expire-bulk-export-archives"
    ]).filter[0].prefix == "exports/"
    error_message = "The only rule that expires current versions must be scoped to the exports/ prefix."
  }

  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      length(rule.expiration) == 0 || try(rule.filter[0].prefix, null) == "exports/"
    ])
    error_message = "No lifecycle rule may expire current object versions outside exports/ (task spec: forbidden). Evidence is deleted on request or not at all."
  }

  assert {
    condition     = alltrue([for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule : rule.status == "Enabled"])
    error_message = "A Disabled lifecycle rule is a rule that is not running; remove it instead."
  }
}

run "prod_moves_superseded_versions_to_infrequent_access_then_expires_them" {
  variables {
    name_prefix                       = "debate-prod-evidence"
    environment                       = "prod"
    noncurrent_version_retention_days = 365
  }

  assert {
    # `noncurrent_version_transition` is a set, so it is matched rather than indexed.
    condition = one([
      for transition in one([
        for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
        rule if rule.id == "age-out-superseded-evidence-versions"
      ]).noncurrent_version_transition :
      transition
      if transition.noncurrent_days == 30 && transition.storage_class == "STANDARD_IA"
    ]) != null
    error_message = "prod must move superseded versions to Standard-IA after 30 days, and to no other storage class."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "age-out-superseded-evidence-versions"
    ]).noncurrent_version_expiration[0].noncurrent_days == 365
    error_message = "prod must keep superseded versions for a year before expiring them."
  }

  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      length(rule.expiration) == 0 || try(rule.filter[0].prefix, null) == "exports/"
    ])
    error_message = "No lifecycle rule may expire current object versions outside exports/, in prod least of all."
  }

  assert {
    condition     = aws_s3_bucket.evidence.bucket == "debate-prod-evidence-a7508de8"
    error_message = "The prod bucket must carry the prod prefix: DebateMaintainer is denied debate-prod-* by name (ADR-0010 rules 2 and 4)."
  }
}

# ---------------------------------------------------------------------------------------------
# The key, as an adoptable resource of its own (ac6)
# ---------------------------------------------------------------------------------------------

run "key_is_customer_managed_rotated_and_separately_addressable" {
  assert {
    condition     = aws_kms_key.evidence.enable_key_rotation
    error_message = "Key rotation must be on."
  }

  assert {
    condition     = aws_kms_key.evidence.deletion_window_in_days == 30
    error_message = "The deletion window must be the longest AWS offers: scheduling this key for deletion makes every object in the bucket permanently unreadable."
  }

  assert {
    condition     = aws_kms_alias.evidence.name == "alias/debate-dev-evidence"
    error_message = "The alias must start with the environment prefix, or DebateMaintainer's deny on alias/debate-prod-* does not reach the prod key (ADR-0010 rule 4)."
  }

  assert {
    condition     = aws_kms_alias.evidence.target_key_id == aws_kms_key.evidence.key_id
    error_message = "The alias must point at this module's key."
  }

  assert {
    condition     = output.kms_key_arn == aws_kms_key.evidence.arn && output.kms_alias_name == aws_kms_alias.evidence.name
    error_message = "The key and its alias must be exposed as outputs, so v2-e10-t04 can adopt them with `moved` blocks instead of creating a second key."
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_kms_key.evidence.policy).Statement :
      statement if statement.Effect == "Allow"
    ]) == 1
    error_message = "With no additional readers the key policy must hold exactly one Allow: the account delegation that keeps the key manageable."
  }
}

run "additional_readers_may_read_and_decrypt_and_nothing_else" {
  variables {
    additional_reader_principal_arns = [
      "arn:aws:iam::111122223333:role/debate-dev-evidence-api",
      "arn:aws:iam::111122223333:role/debate-dev-evidence-worker",
    ]
  }

  assert {
    condition = alltrue([
      for principal_arn in var.additional_reader_principal_arns :
      anytrue([
        for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
        contains(tolist(flatten([try(statement.Principal.AWS, [])])), principal_arn) if statement.Effect == "Allow"
      ])
    ])
    error_message = "Every additional reader principal must appear in the bucket policy (ac6)."
  }

  assert {
    condition = alltrue([
      for principal_arn in var.additional_reader_principal_arns :
      anytrue([
        for statement in jsondecode(aws_kms_key.evidence.policy).Statement :
        contains(tolist(flatten([try(statement.Principal.AWS, [])])), principal_arn)
        if try(statement.Sid, "") == "AllowAdditionalReadersDecryptEvidence"
      ])
    ])
    error_message = "Every additional reader principal must appear in the key policy, or a presigned URL it hands out cannot be redeemed."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      statement.Action if statement.Effect == "Allow"
      ])) == toset([
      "s3:ListBucket",
      "s3:GetObject",
      "s3:GetObjectVersion",
    ])
    error_message = "Additional readers get read actions only: no PutObject, no DeleteObject, nothing that writes (task spec: forbidden)."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_kms_key.evidence.policy).Statement :
      statement.Action if try(statement.Sid, "") == "AllowAdditionalReadersDecryptEvidence"
      ])) == toset([
      "kms:Decrypt",
      "kms:DescribeKey",
    ])
    error_message = "Additional readers get kms:Decrypt and kms:DescribeKey only: no Encrypt, no GenerateDataKey, no key administration (task spec: forbidden)."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        startswith(resource, aws_s3_bucket.evidence.arn)
      ]) if statement.Effect == "Allow"
    ])
    error_message = "Every resource an additional reader is granted must be this environment's own bucket."
  }
}

# ---------------------------------------------------------------------------------------------
# The two credentials (ac3)
# ---------------------------------------------------------------------------------------------

run "operator_permission_set_reads_and_publishes_but_cannot_delete" {
  variables {
    identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
    identity_store_id            = "d-mock000000"
    evidence_operator_user_names = ["maintainer"]
  }

  assert {
    condition     = aws_ssoadmin_permission_set.evidence_operator[0].name == "DebateDevEvidenceOperator"
    error_message = "The permission set must be named for its environment, so a dev credential and a prod credential can never be confused."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement :
      statement.Action
      ])) == toset([
      "s3:ListBucket",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ])
    error_message = "The everyday evidence credential may do exactly seven things. s3:DeleteObject, s3:PutBucketPolicy and kms:* are forbidden by the task spec; a delete is a takedown, and takedowns use the other permission set."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement :
      statement.Effect == "Allow"
    ])
    error_message = "The operator policy is an allow-list; a Deny in it would mean something broader had been granted."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        startswith(resource, aws_s3_bucket.evidence.arn) || resource == aws_kms_key.evidence.arn
      ])
    ])
    error_message = "Every resource in the operator policy must be this environment's own bucket or its own key."
  }

  assert {
    condition = toset(one([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement :
      statement if try(statement.Sid, "") == "ListDocumentedEvidencePrefixes"
      ]).Condition.StringLike["s3:prefix"]) == toset([
      "raw/", "raw/*",
      "parsed/", "parsed/*",
      "files/", "files/*",
      "manifests/", "manifests/*",
      "reports/", "reports/*",
      "uploads/", "uploads/*",
      "exports/", "exports/*",
      "quarantine/", "quarantine/*",
    ])
    error_message = "ListBucket must be scoped to the documented prefixes of docs/architecture/evidence-store-layout.md, and to all of them: a prefix missing here is a prefix the CLI cannot see."
  }

  assert {
    condition     = length(aws_ssoadmin_account_assignment.evidence_operators) == 1
    error_message = "The named operator must actually be assigned the permission set, or the SSO profile has nothing to assume."
  }

  assert {
    condition     = output.operator_profile_name == "debate-dev-evidence"
    error_message = "The operator's SSO profile name must follow name_prefix, as the runbook and v1-e29-t05 assume."
  }
}

run "removal_permission_set_deletes_disclosed_material_and_nothing_else" {
  variables {
    identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
    identity_store_id            = "d-mock000000"
    evidence_removal_user_names  = ["maintainer"]
  }

  assert {
    condition     = aws_ssoadmin_permission_set.evidence_removal[0].name == "DebateDevEvidenceRemoval"
    error_message = "The takedown permission set must be named for its environment."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement :
      statement.Action
      ])) == toset([
      "s3:ListBucketVersions",
      "s3:GetObjectVersion",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ])
    error_message = "The takedown credential may list versions, read, delete and append to the suppression list. s3:DeleteBucket, s3:PutBucketPolicy, s3:PutLifecycleConfiguration and kms:* admin actions are forbidden by the task spec."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        anytrue([
          for prefix in ["raw/", "parsed/", "files/", "manifests/", "quarantine/"] :
          startswith(resource, "${aws_s3_bucket.evidence.arn}/${prefix}")
        ])
      ])
      if anytrue([for action in tolist(flatten([statement.Action])) : startswith(action, "s3:Delete")])
    ])
    error_message = "Delete rights must be scoped to raw/, parsed/, files/, manifests/ and quarantine/. A delete under reports/ must be denied (task spec: forbidden)."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        startswith(resource, "${aws_s3_bucket.evidence.arn}/manifests/_suppression/")
      ])
      if contains(tolist(flatten([statement.Action])), "s3:PutObject")
    ])
    error_message = "The only thing a takedown may write is the suppression list under manifests/_suppression/."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        startswith(resource, aws_s3_bucket.evidence.arn) || resource == aws_kms_key.evidence.arn
      ])
    ])
    error_message = "Every resource in the takedown policy must be this environment's own bucket or its own key."
  }

  assert {
    condition     = length(aws_ssoadmin_account_assignment.evidence_removers) == 1
    error_message = "The one accountable person must actually be assigned the takedown permission set."
  }

  assert {
    condition     = aws_ssoadmin_permission_set.evidence_removal[0].session_duration == "PT1H"
    error_message = "The takedown session must be short: this credential is assumed to run one removal and then let go of."
  }

  assert {
    condition     = output.removal_profile_name == "debate-dev-evidence-removal"
    error_message = "The takedown SSO profile must be named separately from the everyday one, so the operator has to choose it on purpose."
  }
}

run "takedown_rights_are_refused_to_a_second_person" {
  command = plan

  variables {
    identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
    identity_store_id            = "d-mock000000"
    evidence_removal_user_names  = ["maintainer", "someone-else"]
  }

  expect_failures = [var.evidence_removal_user_names]
}

run "a_name_prefix_without_its_environment_is_refused" {
  command = plan

  variables {
    name_prefix = "debate-evidence"
  }

  expect_failures = [var.name_prefix]
}

run "no_identity_center_instance_means_no_permission_sets" {
  assert {
    condition     = length(aws_ssoadmin_permission_set.evidence_operator) == 0 && length(aws_ssoadmin_permission_set.evidence_removal) == 0
    error_message = "Both permission sets are optional: the module has to be usable without an Identity Center instance."
  }
}

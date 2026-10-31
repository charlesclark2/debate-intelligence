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
# environment's own key; no lifecycle rule expires a current version outside exports/, except a
# parsed/ object tagged as retired (v1-e31-t16); the everyday credential cannot delete anything,
# and may tag nothing outside parsed/; the takedown credential can delete disclosed material and
# nothing else; and an additional reader is a reader.
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

  # Not a module input either: the run lock's object ARN under the mocked bucket, written out by
  # hand (v1-e40-t07). The key is debate_core's RUN_LOCK_KEY.
  run_lock_object_arn = "arn:aws:s3:::debate-mock-evidence/reports/sync/run-lock.json"

  # The two tables below are not module inputs. They are the hand-written expectations the
  # statement-coverage assertions of both permission sets read (v1-e29-t06), kept here once so
  # the two assertions cannot drift apart.
  #
  # Every action either permission set may hold, and the resource it has to be granted on. S3
  # authorises ListBucket and ListBucketVersions against the bucket ARN; granted on an object ARN
  # they match nothing, and the first anyone hears of it is an AccessDenied, during a takedown if
  # it is the removal statement. Object actions are authorised against object ARNs, key actions
  # against the key. An action missing from this table leaves its statement uncovered, and the
  # coverage assertion fails on the count: add the action here, with its shape, on purpose.
  resource_shape_of_action = {
    "s3:ListBucket"          = "bucket"
    "s3:ListBucketVersions"  = "bucket"
    "s3:GetObject"           = "object"
    "s3:GetObjectVersion"    = "object"
    "s3:PutObject"           = "object"
    "s3:GetObjectTagging"    = "object"
    "s3:PutObjectTagging"    = "object"
    "s3:DeleteObject"        = "object"
    "s3:DeleteObjectVersion" = "object"
    "kms:Encrypt"            = "key"
    "kms:Decrypt"            = "key"
    "kms:GenerateDataKey"    = "key"
  }

  # The s3:prefix condition each bucket-level action must carry, exactly. Without one, a listing
  # grant covers the whole bucket while the action set stays the same.
  #
  # ListBucket: the documented prefixes of docs/architecture/evidence-store-layout.md, all of them,
  # and the student search pilot's reports/tub/search/ by name (v1-e39-t02). A prefix missing here is
  # a prefix the CLI cannot see.
  #
  # ListBucketVersions: the prefixes of disclosed material a takedown may delete from, and no
  # others. reports/ is not one of them (operator_access.tf). This is the everyday credential's
  # table; the takedown run below gives its own, which adds reports/tub/search/ (v1-e39-t07).
  list_prefixes_of_action = {
    "s3:ListBucket" = [
      "raw/", "raw/*",
      "parsed/", "parsed/*",
      "files/", "files/*",
      "manifests/", "manifests/*",
      "reports/", "reports/*",
      "uploads/", "uploads/*",
      "exports/", "exports/*",
      "quarantine/", "quarantine/*",
      "reports/tub/search/", "reports/tub/search/*",
    ]
    "s3:ListBucketVersions" = [
      "raw/", "raw/*",
      "parsed/", "parsed/*",
      "files/", "files/*",
      "manifests/", "manifests/*",
      "quarantine/", "quarantine/*",
    ]
  }
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
# The run lock is written only by compare-and-swap (v1-e40-t07)
# ---------------------------------------------------------------------------------------------

# reports/sync/run-lock.json is v1-e40-t04's lock, and its every write in debate_core is a PutObject
# with If-Match or If-None-Match. The bucket refuses one with neither, on that key alone. The three
# assertions each catch a way of widening it that the other two let through: the statement itself
# (another key, a prefix, another action, a lost condition), the requirement moved into a statement
# that reaches further, and a statement added or dropped. The expected statement is written out here
# by hand, from AWS's condition keys, not read back from main.tf.
run "bucket_policy_refuses_an_unconditional_write_of_the_run_lock_and_nothing_else" {
  assert {
    # The whole statement rather than field by field, so that a field nobody thought to read
    # (NotResource, NotAction, a narrower Principal, a third condition key) cannot change what it
    # does. A wildcard or a prefix in Resource, a second resource, another action, or a condition
    # that lost a key all fail here: without the condition the deny refuses the lock's own writes,
    # and with one key alone the seed's If-None-Match or every renewal's If-Match.
    condition = alltrue([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      jsonencode(statement) == jsonencode({
        Sid       = "DenyUnconditionalWritesOfTheRunLock"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "s3:PutObject"
        Resource  = var.run_lock_object_arn
        Condition = {
          Null = {
            "s3:if-match"      = "true"
            "s3:if-none-match" = "true"
          }
        }
      })
      if try(statement.Sid, "") == "DenyUnconditionalWritesOfTheRunLock"
    ])
    error_message = "The run lock deny must be exactly: Deny, every principal, s3:PutObject, ${var.run_lock_object_arn} and no other key, unless s3:if-match or s3:if-none-match is present."
  }

  assert {
    # The statement above is found by its Sid, so this is what stops the requirement from moving
    # into another statement, which would reach every key that statement reaches.
    condition = alltrue([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      !strcontains(jsonencode(statement), "s3:if-match") && !strcontains(jsonencode(statement), "s3:if-none-match") && !strcontains(jsonencode(statement), "run-lock")
      if try(statement.Sid, "") != "DenyUnconditionalWritesOfTheRunLock"
    ])
    error_message = "No other statement may require a conditional write or name the run lock: the requirement is on reports/sync/run-lock.json and no other key (task spec: forbidden)."
  }

  assert {
    # Every statement the bucket policy holds with no additional readers, by Sid, and how many. A
    # second deny that reached another key fails here, under a Sid of its own or a repeated one, and
    # so does a policy that lost the run lock deny, which the first assertion would pass unread.
    condition = toset([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement : try(statement.Sid, "")
      ]) == toset([
      "DenyInsecureTransport",
      "DenyUploadsThatOverrideEvidenceEncryption",
      "DenyUploadsUnderAnotherKey",
      "DenyUnconditionalWritesOfTheRunLock",
    ]) && length(jsondecode(aws_s3_bucket_policy.evidence.policy).Statement) == 4
    error_message = "The bucket policy must hold the TLS deny, the two encryption denies and the run lock deny, and nothing else."
  }
}

# Both environments call this one module (infrastructure/envs/*/evidence_store.tf), so prod carries
# the same statement. Asserted under prod's inputs as well, so that a later per-environment switch
# cannot leave prod's lock unguarded.
run "prod_refuses_an_unconditional_write_of_the_run_lock_too" {
  variables {
    name_prefix                       = "debate-prod-evidence"
    environment                       = "prod"
    noncurrent_version_retention_days = 365
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      statement if jsonencode(statement) == jsonencode({
        Sid       = "DenyUnconditionalWritesOfTheRunLock"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "s3:PutObject"
        Resource  = var.run_lock_object_arn
        Condition = {
          Null = {
            "s3:if-match"      = "true"
            "s3:if-none-match" = "true"
          }
        }
      })
    ]) == 1
    error_message = "prod's bucket policy must refuse an unconditional write of the run lock, exactly as dev's does."
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
      length(rule.expiration) == 0
      || try(rule.filter[0].prefix, null) == "exports/"
      || (
        try(rule.filter[0].and[0].prefix, null) == "parsed/"
        && try(rule.filter[0].and[0].tags, null) == tomap({ "debate-retention" = "superseded" })
      )
      || alltrue([
        for expiration in rule.expiration :
        expiration.expired_object_delete_marker == true
        && coalesce(expiration.days, 0) == 0
        && expiration.date == null
      ])
    ])
    error_message = "No lifecycle rule may expire current object versions outside exports/, except parsed/ objects tagged debate-retention=superseded (v1-e31-t16). A rule that only removes expired delete markers expires no object. Evidence is deleted on request or not at all."
  }

  assert {
    condition     = alltrue([for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule : rule.status == "Enabled"])
    error_message = "A Disabled lifecycle rule is a rule that is not running; remove it instead."
  }
}

# v1-e31-t16. The one rule outside exports/ that expires a current version, and only one the operator
# has tagged as retired with `caselist retire --bucket`. Expiration counts days from an object's
# creation, not from its tagging, so a tagged object older than a day is expired at the next
# lifecycle run; the grace period is how long it is then kept as a noncurrent version, counted from
# that day. The values are hand-written here, from the grace period the session report proposes.
run "retired_parsed_version_directories_expire_after_a_grace_period" {
  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "expire-retired-parsed-version-directories"
    ]).filter[0].and[0].prefix == "parsed/"
    error_message = "The retirement rule must be scoped to parsed/: nothing else in the bucket is retired by tag."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "expire-retired-parsed-version-directories"
    ]).filter[0].and[0].tags == tomap({ "debate-retention" = "superseded" })
    error_message = "The retirement rule must match exactly the tag `caselist retire` writes, debate-retention=superseded (debate_core's ports/version_directories.py)."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "expire-retired-parsed-version-directories"
    ]).expiration[0].days == 1
    error_message = "A retired object's current version expires 1 day after creation, so the grace period starts when it is retired, not when it was written."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "expire-retired-parsed-version-directories"
    ]).noncurrent_version_expiration[0].noncurrent_days == 30
    error_message = "A retired object is kept for a 30-day grace period as a noncurrent version before it is deleted."
  }
}

# v1-e31-t16, PM ruling 2026-10-16. Expiring a retired object's current version leaves a delete
# marker, which is orphaned once the grace period deletes the noncurrent version behind it. A delete
# marker carries no tags, so the tagged rule never matches it, and S3 refuses ExpiredObjectDeleteMarker
# beside a tag filter. So a rule of its own, on the prefix alone, removes it. It expires no object:
# an expired delete marker is one with no version left behind it.
run "orphaned_delete_markers_under_parsed_are_removed" {
  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "remove-orphaned-parsed-delete-markers"
    ]).filter[0].prefix == "parsed/"
    error_message = "The delete-marker rule must be scoped to parsed/, where retirement leaves markers."
  }

  assert {
    condition = length(one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "remove-orphaned-parsed-delete-markers"
    ]).filter[0].and) == 0
    error_message = "The delete-marker rule has no tag filter: a delete marker carries no tags, and S3 refuses ExpiredObjectDeleteMarker beside one."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "remove-orphaned-parsed-delete-markers"
    ]).expiration[0].expired_object_delete_marker == true
    error_message = "The delete-marker rule must remove expired object delete markers."
  }

  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      coalesce(rule.expiration[0].days, 0) == 0 && rule.expiration[0].date == null
      && length(rule.noncurrent_version_expiration) == 0 && length(rule.noncurrent_version_transition) == 0
      if rule.id == "remove-orphaned-parsed-delete-markers"
    ])
    error_message = "The delete-marker rule must do nothing else: no days, no date, no noncurrent action. Untagged parsed/ objects, the current directory among them, are never expired."
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
      length(rule.expiration) == 0
      || try(rule.filter[0].prefix, null) == "exports/"
      || (
        try(rule.filter[0].and[0].prefix, null) == "parsed/"
        && try(rule.filter[0].and[0].tags, null) == tomap({ "debate-retention" = "superseded" })
      )
      || alltrue([
        for expiration in rule.expiration :
        expiration.expired_object_delete_marker == true
        && coalesce(expiration.days, 0) == 0
        && expiration.date == null
      ])
    ])
    error_message = "No lifecycle rule may expire current object versions outside exports/, except parsed/ objects tagged debate-retention=superseded, in prod least of all."
  }

  assert {
    condition = one([
      for rule in aws_s3_bucket_lifecycle_configuration.evidence.rule :
      rule if rule.id == "expire-retired-parsed-version-directories"
    ]).noncurrent_version_expiration[0].noncurrent_days == 30
    error_message = "prod keeps a retired parsed/ object for the same 30-day grace as dev, not the 365 days of other superseded versions: it is derived, reproducible data the operator retired on purpose (v1-e31-t16)."
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
      "s3:ListBucketVersions",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:GetObjectTagging",
      "s3:PutObjectTagging",
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ])
    error_message = "The everyday evidence credential may do exactly ten things. s3:ListBucketVersions is read-only, so a removal's dry run can count versions (v1-e29-t06); the two tagging actions retire a superseded parsed/ directory for the lifecycle rule (v1-e31-t16). s3:DeleteObject, s3:DeleteObjectVersion, s3:PutBucketPolicy and kms:* are forbidden by the task spec; a delete is a takedown, and takedowns use the other permission set."
  }

  # v1-e39-t07: the takedown credential gained delete and version listing under reports/tub/search/;
  # this credential gained nothing. Its version listing still reaches no part of reports/.
  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement :
      alltrue([
        for prefix in try(statement.Condition.StringLike["s3:prefix"], []) : !startswith(prefix, "reports/")
      ])
      if contains(flatten([statement.Action]), "s3:ListBucketVersions")
    ])
    error_message = "The everyday credential lists no versions under reports/: the index prefix is the takedown credential's alone (v1-e39-t07)."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        resource == "${aws_s3_bucket.evidence.arn}/parsed/*"
      ])
      if anytrue([for action in tolist(flatten([statement.Action])) : endswith(action, "ObjectTagging")])
    ])
    error_message = "The everyday credential may read and write object tags under parsed/ only: retiring a superseded version directory is the one thing it tags for (v1-e31-t16, task spec: forbidden)."
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement :
      statement if anytrue([for action in tolist(flatten([statement.Action])) : endswith(action, "ObjectTagging")])
    ]) == 1
    error_message = "The two tagging actions belong in one statement of their own, so that its resource is theirs alone and cannot widen a grant beside it."
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

  # Every statement, not a chosen few (v1-e29-t06). Each is classified by the resource shape its
  # actions need (var.resource_shape_of_action) and checked against that shape: bucket-level
  # actions on the bucket ARN and under exactly the s3:prefix condition var.list_prefixes_of_action
  # gives them; object-level actions on object ARNs in this bucket; key actions on this key; and no
  # condition anywhere else. A statement whose actions are unknown, or need different shapes, is
  # not covered, and the count makes that a failure rather than a statement nobody checks.
  assert {
    condition = alltrue([
      for statements in [[
        for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy).Statement : {
          statement = statement
          actions   = flatten([try(statement.Action, "no Action")])
          resources = flatten([try(statement.Resource, "no Resource")])
          shape = try(one(distinct([
            for action in flatten([try(statement.Action, "no Action")]) :
            lookup(var.resource_shape_of_action, action, "unknown")
          ])), "mixed")
        }
      ]] :
      length([
        for covered in statements : covered if contains(["bucket", "object", "key"], covered.shape)
      ]) == length(statements)
      && alltrue([
        for covered in statements :
        covered.shape == "bucket" ? (
          alltrue([for resource in covered.resources : resource == aws_s3_bucket.evidence.arn])
          && alltrue([
            for action in covered.actions :
            toset(try(covered.statement.Condition.StringLike["s3:prefix"], []))
            == toset(lookup(var.list_prefixes_of_action, action, ["no expected prefixes"]))
          ])
          ) : covered.shape == "object" ? (
          alltrue([for resource in covered.resources : startswith(resource, "${aws_s3_bucket.evidence.arn}/")])
          && try(covered.statement.Condition, null) == null
          ) : (
          alltrue([for resource in covered.resources : resource == aws_kms_key.evidence.arn])
          && try(covered.statement.Condition, null) == null
        )
        if contains(["bucket", "object", "key"], covered.shape)
      ])
    ])
    error_message = "Every operator statement must be covered and scoped to its shape: ListBucket and ListBucketVersions on the bucket ARN under exactly their s3:prefix condition, object actions on object ARNs, key actions on the key, no other conditions. A statement with an action not in resource_shape_of_action, or mixing shapes, is uncovered: give it a shape here or split it."
  }

  assert {
    condition     = length(aws_ssoadmin_account_assignment.evidence_operators) == 1
    error_message = "The named operator must actually be assigned the permission set, or the SSO profile has nothing to assume."
  }

  assert {
    condition     = output.operator_profile_name == "debate-dev-evidence"
    error_message = "The operator's SSO profile name must follow name_prefix, as the runbook and v1-e29-t05 assume."
  }

  assert {
    condition     = output.operator_policy_json == aws_ssoadmin_permission_set_inline_policy.evidence_operator[0].inline_policy
    error_message = "operator_policy_json is the permission set's own policy: the weekly cloud run's role holds it as the everyday evidence permissions (v1-e40-t03), so what this run asserts of the one holds of the other."
  }
}

run "removal_permission_set_deletes_disclosed_material_and_nothing_else" {
  variables {
    identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
    identity_store_id            = "d-mock000000"
    evidence_removal_user_names  = ["maintainer"]

    # The takedown's own listing: the everyday table's ListBucketVersions prefixes, the student
    # search pilot's index versions, so a removal can find their noncurrent versions (v1-e39-t07),
    # and the landscape bundles, so it can find a school view's (v1-e32-t13).
    list_prefixes_of_action = {
      "s3:ListBucketVersions" = [
        "raw/", "raw/*",
        "parsed/", "parsed/*",
        "files/", "files/*",
        "manifests/", "manifests/*",
        "quarantine/", "quarantine/*",
        "reports/tub/search/", "reports/tub/search/*",
        "reports/landscape/", "reports/landscape/*",
      ]
    }
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
          for prefix in ["raw/", "parsed/", "files/", "manifests/", "quarantine/", "reports/tub/search/", "reports/landscape/"] :
          startswith(resource, "${aws_s3_bucket.evidence.arn}/${prefix}")
        ])
      ])
      if anytrue([for action in tolist(flatten([statement.Action])) : startswith(action, "s3:Delete")])
    ])
    error_message = "Delete rights must be scoped to raw/, parsed/, files/, manifests/, quarantine/, reports/tub/search/ (v1-e39-t07) and the landscape school views under reports/landscape/ (v1-e32-t13). A delete anywhere else under reports/ must be denied (task spec: forbidden)."
  }

  # v1-e39-t07 (PM amendment 2026-10-19): the takedown credential may delete the student search
  # pilot's superseded index versions, under reports/tub/search/ and nowhere else under reports/.
  # Every object a delete statement names, exactly: the five prefixes of disclosed material and the
  # index's one, so a widened prefix (reports/*, reports/tub/*) fails here by name.
  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement :
      flatten([statement.Resource])
      if anytrue([for action in tolist(flatten([statement.Action])) : startswith(action, "s3:Delete")])
      ])) == toset([
      "${aws_s3_bucket.evidence.arn}/raw/*",
      "${aws_s3_bucket.evidence.arn}/parsed/*",
      "${aws_s3_bucket.evidence.arn}/files/*",
      "${aws_s3_bucket.evidence.arn}/manifests/*",
      "${aws_s3_bucket.evidence.arn}/quarantine/*",
      "${aws_s3_bucket.evidence.arn}/reports/tub/search/*",
      "${aws_s3_bucket.evidence.arn}/reports/landscape/*/schools.csv",
      "${aws_s3_bucket.evidence.arn}/reports/landscape/*/schools.md",
    ])
    error_message = "A takedown deletes under the five prefixes of disclosed material and reports/tub/search/, and the landscape bundles' two school-view files, exactly. Nothing else under reports/ gains a delete (v1-e39-t07, v1-e32-t13)."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        !startswith(resource, "${aws_s3_bucket.evidence.arn}/reports/")
        || startswith(resource, "${aws_s3_bucket.evidence.arn}/reports/tub/search/")
        || contains([
          "${aws_s3_bucket.evidence.arn}/reports/landscape/*/schools.csv",
          "${aws_s3_bucket.evidence.arn}/reports/landscape/*/schools.md",
        ], resource)
      ])
    ])
    error_message = "Under reports/, the takedown credential reaches reports/tub/search/ and the landscape school views, and nothing else."
  }

  # v1-e32-t13: the landscape bundles' school views, which name schools and team codes, go with a
  # removal. Exactly the two file names v1-e32-t04 gives them, in one statement of their own that
  # may delete and do nothing else; no circuit-wide file (report.md, positions.csv, top_cards.csv,
  # impact_cards.csv, trends.csv) and no bundle as a whole.
  assert {
    condition = [
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement : {
        actions   = toset(flatten([statement.Action]))
        resources = toset(flatten([statement.Resource]))
      }
      if anytrue([for resource in flatten([statement.Resource]) : startswith(resource, "${aws_s3_bucket.evidence.arn}/reports/landscape/")])
      ] == [{
        actions = toset(["s3:DeleteObject", "s3:DeleteObjectVersion"])
        resources = toset([
          "${aws_s3_bucket.evidence.arn}/reports/landscape/*/schools.csv",
          "${aws_s3_bucket.evidence.arn}/reports/landscape/*/schools.md",
        ])
    }]
    error_message = "One statement reaches reports/landscape/ objects: it deletes schools.csv and schools.md, every version, and nothing else of a bundle (v1-e32-t13)."
  }

  assert {
    condition = alltrue(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement : [
        for resource in flatten([statement.Resource]) : [
          for name in ["report.md", "positions.csv", "top_cards.csv", "impact_cards.csv", "trends.csv"] :
          !endswith(resource, name) && !endswith(resource, "reports/landscape/*") && !endswith(resource, "reports/*")
        ]
      ]
    ]))
    error_message = "No takedown resource names a circuit-wide landscape file, or every file of a bundle (task spec: forbidden)."
  }

  assert {
    condition     = output.removable_index_prefix == "reports/tub/search/" && !contains(output.removable_prefixes, "reports/tub/search/")
    error_message = "The index prefix is the takedown's alone: kept out of removable_prefixes, which the everyday credential's version listing reads."
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

  # The same coverage as the operator policy's, over every takedown statement. The two
  # delete-scoping assertions above narrow which object ARNs a delete or a write may name; this one
  # is what holds ListBucketVersions to the bucket ARN and the removable prefixes. Before
  # v1-e29-t06 nothing did, and pointing it at an object ARN left every assertion green.
  assert {
    condition = alltrue([
      for statements in [[
        for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.evidence_removal[0].inline_policy).Statement : {
          statement = statement
          actions   = flatten([try(statement.Action, "no Action")])
          resources = flatten([try(statement.Resource, "no Resource")])
          shape = try(one(distinct([
            for action in flatten([try(statement.Action, "no Action")]) :
            lookup(var.resource_shape_of_action, action, "unknown")
          ])), "mixed")
        }
      ]] :
      length([
        for covered in statements : covered if contains(["bucket", "object", "key"], covered.shape)
      ]) == length(statements)
      && alltrue([
        for covered in statements :
        covered.shape == "bucket" ? (
          alltrue([for resource in covered.resources : resource == aws_s3_bucket.evidence.arn])
          && alltrue([
            for action in covered.actions :
            toset(try(covered.statement.Condition.StringLike["s3:prefix"], []))
            == toset(lookup(var.list_prefixes_of_action, action, ["no expected prefixes"]))
          ])
          ) : covered.shape == "object" ? (
          alltrue([for resource in covered.resources : startswith(resource, "${aws_s3_bucket.evidence.arn}/")])
          && try(covered.statement.Condition, null) == null
          ) : (
          alltrue([for resource in covered.resources : resource == aws_kms_key.evidence.arn])
          && try(covered.statement.Condition, null) == null
        )
        if contains(["bucket", "object", "key"], covered.shape)
      ])
    ])
    error_message = "Every takedown statement must be covered and scoped to its shape: ListBucketVersions on the bucket ARN under exactly the removable-prefix condition (an object ARN matches nothing, and the takedown fails with AccessDenied), object actions on object ARNs, key actions on the key, no other conditions. A statement with an action not in resource_shape_of_action, or mixing shapes, is uncovered: give it a shape here or split it."
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

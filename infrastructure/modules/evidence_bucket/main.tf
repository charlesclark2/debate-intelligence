# One environment's evidence store: the private, versioned, KMS-encrypted S3 bucket that is the
# system of record for disclosed caselist evidence, camp files, parsed cards, built team files and
# reports. Decision: ADR-0003. Region and account structure: ADR-0010. Spec:
# v1-e29-t03-evidence-buckets.
#
# Called once from infrastructure/envs/dev and once from infrastructure/envs/prod, with different
# inputs and nothing copied between them (infrastructure/README.md). It hard-codes no account id
# and no region: the region comes from the calling root's provider.
#
# Three properties this module exists to guarantee, each asserted in
# tests/evidence_bucket.tftest.hcl because each is something a later edit could quietly drop:
#
#   1. Nothing here is ever public, and nothing here is ever fetched over plain HTTP.
#   2. Every object is encrypted with this environment's own customer-managed key, so that
#      ADR-0010 rule 4 — prod evidence unreadable by a dev-scoped credential — is enforced by a
#      key policy and a name-scoped IAM deny rather than by convention.
#   3. No lifecycle rule ever expires a current object version, except under exports/, which
#      holds regenerable zip downloads. Evidence is deleted on request (docs/runbooks/caselist-removal.md)
#      or not at all.
#
# The key layout that lives in this bucket is documented in
# docs/architecture/evidence-store-layout.md; local.evidence_prefixes below is the machine-readable
# half of that document and is what the operator's ListBucket grant is scoped to.

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "${var.name_prefix}-${var.bucket_suffix}"

  # The top-level prefixes of docs/architecture/evidence-store-layout.md. Adding one here without
  # adding it there (or the other way round) is the drift this comment exists to prevent: this
  # list is what the EvidenceOperator permission set may list, so a prefix missing from it is a
  # prefix the CLI cannot see.
  evidence_prefixes = [
    "raw/",
    "parsed/",
    "files/",
    "manifests/",
    "reports/",
    "uploads/",
    "exports/",
    "quarantine/",
  ]

  # Bulk zip downloads (V2 v2-e35-t03). Regenerable by definition, so this is the one prefix whose
  # current versions a lifecycle rule may expire.
  export_prefix          = "exports/"
  export_expiration_days = 1

  # Nothing here is large enough that an abandoned multipart upload should be paid for for a week
  # and a day. Parts of an incomplete upload are billed and are invisible in a normal listing.
  abort_incomplete_multipart_upload_days = 7

  # A noncurrent version that expires on or before the day it would move to Standard-IA has
  # nothing to move: S3 rejects the pair, and a 30-day minimum-billing class would cost more than
  # Standard for a version that is about to be deleted anyway. dev (30/30) therefore gets the
  # expiry without the transition; prod (30/365) gets both. See variables.tf.
  transition_noncurrent_versions = var.noncurrent_version_retention_days > var.noncurrent_version_transition_days

  has_additional_readers = length(var.additional_reader_principal_arns) > 0
}

# ---------------------------------------------------------------------------------------------
# The key
# ---------------------------------------------------------------------------------------------

# A customer-managed key of its own, rather than SSE-S3 or the AWS-managed aws/s3 key, for two
# reasons the site bucket (SSE-S3, modules/static_site) does not have: this content is private
# disclosed evidence rather than public web pages, and ADR-0010 rule 4 needs a per-environment key
# whose policy and alias a dev-scoped credential is denied.
#
# aws_kms_key.evidence and aws_kms_alias.evidence are deliberately separate, ordinary resources
# with outputs of their own, so that v2-e10-t04 can adopt this key with `moved` blocks instead of
# creating a second one and re-encrypting the corpus (task spec, ac6).
#
# tflint-ignore: aws_resource_missing_tags
resource "aws_kms_key" "evidence" {
  description = "Encrypts the ${var.environment} evidence store (${local.bucket_name}). Created by v1-e29-t03-evidence-buckets; adopted by v2-e10-t04."

  # Annual rotation. Old versions of the key material are kept, so objects written under a
  # previous version stay readable without being rewritten.
  enable_key_rotation = true

  # The longest window AWS offers. Scheduling this key for deletion makes every object in the
  # bucket permanently unreadable, versions included; 30 days is how long there is to notice.
  deletion_window_in_days = 30

  policy = local.key_policy

  # Destroying the key destroys the bucket's contents in every way that matters: the objects
  # remain, and nothing can ever read them again.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "evidence" {
  # alias/debate-dev-evidence, alias/debate-prod-evidence. The prefix, not a
  # alias/debate-evidence-<env> form: DebateMaintainer's guardrail denies KMS actions on
  # alias/debate-prod-*, and an alias that does not start with the environment prefix would slip
  # past that deny (infrastructure/bootstrap/organization/identity.tf, ADR-0010 rules 2 and 4).
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.evidence.key_id
}

# Built with jsonencode rather than an aws_iam_policy_document data source so that the module's
# tests can read it back under a mocked provider — a policy document's rendered JSON is opaque
# there, and who may decrypt evidence is precisely what is worth asserting on.
locals {
  key_policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          # Without this the key is unmanageable: KMS does not fall back to IAM for a key whose
          # policy does not delegate to the account. It is the account's own root principal, not
          # a human and not a long-lived credential; who in the account may actually use the key
          # is decided by the permission sets in operator_access.tf.
          Sid       = "EnableAccountIamPoliciesForThisKey"
          Effect    = "Allow"
          Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root" }
          Action    = "kms:*"
          Resource  = "*"
        },
      ],
      flatten([
        for _ in range(local.has_additional_readers ? 1 : 0) : [
          {
            # Read and presign only. A presigned GET is authorised against the principal that signed
            # it, so a V2 worker or API role that hands out download links needs Decrypt on this key
            # and nothing else; Encrypt, ReEncrypt, GenerateDataKey and every admin action are
            # withheld (task spec: forbidden).
            Sid       = "AllowAdditionalReadersDecryptEvidence"
            Effect    = "Allow"
            Principal = { AWS = var.additional_reader_principal_arns }
            Action = [
              "kms:Decrypt",
              "kms:DescribeKey",
            ]
            Resource = "*"
          },
        ]
      ]),
    )
  })
}

data "aws_partition" "current" {}

# ---------------------------------------------------------------------------------------------
# The bucket
# ---------------------------------------------------------------------------------------------

# The five standard tags reach every resource in this module through the calling root's provider
# `default_tags` (infrastructure/README.md). tflint's aws_resource_missing_tags rule reads that
# block and cannot see it when it lints this directory on its own, so the taggable resources here
# carry the annotation; linting envs/dev or envs/prod follows the module call and does check them.
# tflint-ignore: aws_resource_missing_tags
resource "aws_s3_bucket" "evidence" {
  bucket = local.bucket_name

  # force_destroy stays false, which is the default and is said out loud here: with it, a
  # `terraform destroy` would empty the system of record before deleting it. Without it, S3
  # refuses to delete a bucket that still holds objects or versions, which is the behaviour this
  # bucket wants.
  force_destroy = false

  # The bootstrap state bucket carries the same guard, for the same reason: `terraform destroy`
  # in a root that holds this module has no legitimate use, and the system of record is not
  # something to lose to a mistyped command or a rename that forces replacement. Removing this
  # block is a deliberate edit to the module, which is the point.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  # All four, deliberately. Blocking public ACLs without restricting public bucket policies (or
  # the other way round) leaves a way to publish the bucket that a later task would not notice.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ACLs off entirely: every grant on this bucket is in the bucket policy or in a permission set,
# where it can be read in one place.
resource "aws_s3_bucket_ownership_controls" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.evidence.arn
    }

    # A bucket key collapses the per-object KMS calls for a prefix into one, which matters when a
    # backfill writes tens of thousands of objects (v1-e30-t06): without it every PUT and every
    # GET is a billed GenerateDataKey or Decrypt.
    bucket_key_enabled = true
  }
}

# ADR-0003: the store is versioned, and every card is reproducible from the snapshot it was cut
# from. Versioning is also the recovery path ADR-0010 leans on, now that dev and prod share an
# account and a mistake in one can reach the other.
resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  depends_on = [aws_s3_bucket_versioning.evidence]

  # Superseded versions only. There is no expiration block here, and that is the point: a current
  # object in this bucket is deleted by a removal request (docs/runbooks/caselist-removal.md) or
  # not at all (task spec: forbidden).
  rule {
    id     = "age-out-superseded-evidence-versions"
    status = "Enabled"

    filter {}

    dynamic "noncurrent_version_transition" {
      for_each = local.transition_noncurrent_versions ? [1] : []

      content {
        noncurrent_days = var.noncurrent_version_transition_days
        storage_class   = "STANDARD_IA"
      }
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  # The one rule that expires current versions, and the reason it is allowed to: an export is a
  # zip of objects that are still in the bucket, built for one download. Keeping them would mean
  # paying to store a second copy of the corpus in an ever-growing pile of archives.
  rule {
    id     = "expire-bulk-export-archives"
    status = "Enabled"

    filter {
      prefix = local.export_prefix
    }

    expiration {
      days = local.export_expiration_days
    }

    # Without this the expired archives would simply become noncurrent versions and sit here for
    # the retention window instead.
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = local.abort_incomplete_multipart_upload_days
    }
  }
}

# The bucket policy. jsonencode, for the same reason as the key policy: the tests have to be able
# to read it back under a mocked provider.
#
# There is no Allow here at all unless additional_reader_principal_arns is non-empty. Access for
# the operator and for `debate-research store` comes from the permission sets in
# operator_access.tf; a bucket policy that granted the account would only widen what those sets
# carefully do not grant.
locals {
  bucket_policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid       = "DenyInsecureTransport"
          Effect    = "Deny"
          Principal = { AWS = "*" }
          Action    = "s3:*"
          Resource = [
            aws_s3_bucket.evidence.arn,
            "${aws_s3_bucket.evidence.arn}/*",
          ]
          Condition = {
            Bool = { "aws:SecureTransport" = "false" }
          }
        },
        {
          # Default encryption applies this key to any PUT that asks for nothing, but a client may
          # still ask for something else. The Null guard is what keeps that from breaking the
          # ordinary case: the deny bites only when the header is present and names another
          # algorithm, never when it is absent.
          Sid       = "DenyUploadsThatOverrideEvidenceEncryption"
          Effect    = "Deny"
          Principal = { AWS = "*" }
          Action    = "s3:PutObject"
          Resource  = "${aws_s3_bucket.evidence.arn}/*"
          Condition = {
            Null            = { "s3:x-amz-server-side-encryption" = "false" }
            StringNotEquals = { "s3:x-amz-server-side-encryption" = "aws:kms" }
          }
        },
        {
          Sid       = "DenyUploadsUnderAnotherKey"
          Effect    = "Deny"
          Principal = { AWS = "*" }
          Action    = "s3:PutObject"
          Resource  = "${aws_s3_bucket.evidence.arn}/*"
          Condition = {
            Null            = { "s3:x-amz-server-side-encryption-aws-kms-key-id" = "false" }
            StringNotEquals = { "s3:x-amz-server-side-encryption-aws-kms-key-id" = aws_kms_key.evidence.arn }
          }
        },
      ],
      flatten([
        for _ in range(local.has_additional_readers ? 1 : 0) : [
          {
            Sid       = "AllowAdditionalReadersListEvidenceBucket"
            Effect    = "Allow"
            Principal = { AWS = var.additional_reader_principal_arns }
            Action    = "s3:ListBucket"
            Resource  = aws_s3_bucket.evidence.arn
          },
          {
            Sid       = "AllowAdditionalReadersReadEvidenceObjects"
            Effect    = "Allow"
            Principal = { AWS = var.additional_reader_principal_arns }
            Action = [
              "s3:GetObject",
              "s3:GetObjectVersion",
            ]
            Resource = "${aws_s3_bucket.evidence.arn}/*"
          },
        ]
      ]),
    )
  })
}

resource "aws_s3_bucket_policy" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  policy = local.bucket_policy

  # Never attach a policy to a bucket whose public access is not yet blocked: the window between
  # the two is the only moment this bucket could be made public by a mistake in the policy.
  depends_on = [aws_s3_bucket_public_access_block.evidence]
}

# Organization CloudTrail.
#
# With dev and prod separated only by tag and resource name (ADR-0010), the trail is the control
# that makes a breach of that boundary visible after the fact: a hand-made resource without tags,
# or a broad grant that lets a dev credential touch prod. It covers every region and the whole
# Organization, and its log files are integrity-validated so tampering is detectable.

locals {
  cloudtrail_name        = "${var.name_prefix}-shared-organization-trail"
  cloudtrail_bucket_name = "${var.name_prefix}-shared-cloudtrail-${local.account_id}"

  # Built by hand rather than read from aws_cloudtrail.organization.arn: the trail depends on the
  # bucket policy, so referencing the trail from that policy would be a dependency cycle.
  cloudtrail_arn = "arn:${local.partition}:cloudtrail:${local.region}:${local.account_id}:trail/${local.cloudtrail_name}"
}

# A dedicated key, not the evidence key of v1-e29-t03: audit logs and evidence have different
# readers, and a single key would let anyone who can read evidence read the audit trail too.
resource "aws_kms_key" "cloudtrail" {
  description             = "Encrypts CloudTrail log files for the debate platform organization trail"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.cloudtrail_kms.json

  tags = {
    Name        = "${var.name_prefix}-shared-cloudtrail"
    Environment = "shared"
    Purpose     = "cloudtrail-log-encryption"
  }
}

resource "aws_kms_alias" "cloudtrail" {
  name          = "alias/${var.name_prefix}-shared-cloudtrail"
  target_key_id = aws_kms_key.cloudtrail.key_id
}

data "aws_iam_policy_document" "cloudtrail_kms" {
  statement {
    sid       = "AllowAccountAdministration"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid       = "AllowCloudTrailToEncryptLogs"
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey*"]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:aws:cloudtrail:arn"
      values   = ["arn:${local.partition}:cloudtrail:*:${local.account_id}:trail/*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.cloudtrail_arn]
    }
  }

  statement {
    sid       = "AllowCloudTrailToDescribeKey"
    effect    = "Allow"
    actions   = ["kms:DescribeKey"]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }

  # Reading the trail is an audit action; member-account principals across the Organization may
  # decrypt what the trail wrote, but only through CloudTrail's own encryption context.
  statement {
    sid       = "AllowOrganizationPrincipalsToDecryptLogs"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:ReEncryptFrom"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalOrgID"
      values   = [local.organization_id]
    }

    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:aws:cloudtrail:arn"
      values   = ["arn:${local.partition}:cloudtrail:*:${local.account_id}:trail/*"]
    }
  }
}

resource "aws_s3_bucket" "cloudtrail" {
  bucket = local.cloudtrail_bucket_name

  tags = {
    Name        = local.cloudtrail_bucket_name
    Environment = "shared"
    Purpose     = "cloudtrail-logs"
  }
}

resource "aws_s3_bucket_public_access_block" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.cloudtrail.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  depends_on = [aws_s3_bucket_versioning.cloudtrail]

  rule {
    id     = "expire-logs"
    status = "Enabled"

    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = var.cloudtrail_log_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.cloudtrail_noncurrent_version_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "cloudtrail_bucket" {
  statement {
    sid       = "AWSCloudTrailAclCheck"
    effect    = "Allow"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.cloudtrail_arn]
    }
  }

  # Two prefixes: an organization trail writes member-account logs under the organization id,
  # and the management account's own logs under its account id.
  statement {
    sid     = "AWSCloudTrailWrite"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${local.account_id}/*",
      "${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${local.organization_id}/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.cloudtrail_arn]
    }
  }

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.cloudtrail.arn,
      "${aws_s3_bucket.cloudtrail.arn}/*",
    ]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  # Log files are evidence. Nobody deletes them through the bucket API; expiry is the lifecycle
  # rule's job.
  statement {
    sid       = "DenyLogDeletion"
    effect    = "Deny"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.cloudtrail.arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "aws:PrincipalArn"
      values   = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id
  policy = data.aws_iam_policy_document.cloudtrail_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.cloudtrail]
}

resource "aws_cloudtrail" "organization" {
  name           = local.cloudtrail_name
  s3_bucket_name = aws_s3_bucket.cloudtrail.id
  kms_key_id     = aws_kms_key.cloudtrail.arn

  is_organization_trail         = true
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_logging                = true

  # Digest files let a reader prove after the fact that delivered log files were not altered.
  # Kept in its own alignment group so `terraform fmt` leaves the single space: the task spec's
  # acceptance criterion matches this line literally.
  enable_log_file_validation = true

  tags = {
    Name        = local.cloudtrail_name
    Environment = "shared"
    Purpose     = "organization-audit-trail"
  }

  depends_on = [
    aws_s3_bucket_policy.cloudtrail,
    aws_kms_key.cloudtrail,
  ]
}

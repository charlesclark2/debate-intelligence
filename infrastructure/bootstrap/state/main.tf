# Remote Terraform state for one environment.
#
# ADR-0010 puts dev and prod in the same AWS account, separated by resource-name prefix and tag,
# with the DebateMaintainer permission set denying debate-prod-*. State has to respect the same
# boundary: one bucket per environment, each named with its environment prefix, so that a
# dev-scoped credential is denied the prod state file by the same policy that denies it prod
# evidence. A single shared state bucket would hand every dev session the prod state — which
# lists every prod resource and, for some resource types, their secrets.
#
# This root is applied once per environment and is the one place where the chicken-and-egg is
# unavoidable: the first apply writes local state, and that state is then migrated into the
# bucket this file creates. README.md has the sequence. Both applies are operator steps; prod
# needs DebateBreakGlassAdmin, because DebateMaintainer cannot write debate-prod-*.

module "tags" {
  source = "../../modules/tags"

  project     = var.project
  environment = var.environment
  owner       = var.owner
  cost_center = var.cost_center

  additional_tags = {
    SpecRef = "v1-e29-t02-terraform-bootstrap"
  }
}

locals {
  bucket_name = "${var.name_prefix}-${var.environment}-tfstate-${var.state_bucket_suffix}"

  # The tagging standard of ADR-0010, written out here rather than taken straight from
  # module.tags. tflint's aws_resource_missing_tags rule reads the provider's `default_tags`, and
  # it evaluates one module at a time: a child module's output is opaque to it, so feeding
  # `default_tags` from module.tags.tags would turn the rule into a check that always fails. This
  # literal map is what the rule can read, and the check below is what stops it from drifting
  # away from the shared module that defines the standard.
  tags = {
    Project     = var.project
    Environment = var.environment
    Owner       = var.owner
    CostCenter  = var.cost_center
    ManagedBy   = "terraform"
    SpecRef     = "v1-e29-t02-terraform-bootstrap"
  }
}

check "tagging_standard_matches_shared_module" {
  assert {
    condition = local.tags == module.tags.tags
    error_message = join(" ", [
      "The default_tags in this root no longer match infrastructure/modules/tags, which is the",
      "definition of the tagging standard. Update local.tags to match the module, or change the",
      "module and every root together.",
    ])
  }
}

resource "aws_s3_bucket" "state" {
  bucket = local.bucket_name

  # Losing this bucket means losing the record of every resource Terraform manages in the
  # environment, and rebuilding it by importing resources one at a time. `terraform destroy` in
  # this root has no legitimate use.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Versioning is what makes a bad apply recoverable, so noncurrent versions are kept for a
# recovery window rather than expired immediately. Incomplete multipart uploads are aborted
# because nothing here is large enough to need one.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  depends_on = [aws_s3_bucket_versioning.state]

  rule {
    id     = "expire-superseded-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# SSE-S3 rather than a customer-managed KMS key. A KMS key would be a second bootstrap
# dependency with its own key policy, applied before any state exists to record it, and a key
# whose accidental deletion makes the state unreadable. Access to state is already controlled by
# the bucket policy below, by block-public-access, and by the permission sets that separate
# debate-dev-* from debate-prod-*. The evidence buckets in v1-e29-t03-evidence-buckets do use a
# customer-managed key; they hold the data, and they are created after this root exists.
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ACLs are disabled outright: every grant to this bucket goes through IAM and the bucket policy,
# where it is reviewable in one place.
resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

data "aws_iam_policy_document" "state" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyUnencryptedObjectUploads"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["AES256"]
    }

    # A PutObject that asks for no encryption header at all is served by the bucket default
    # above, so only an explicit request for something else is denied.
    condition {
      test     = "Null"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state.json

  # Attaching a policy before public access is blocked would leave a window in which the policy
  # is the only thing standing between the bucket and the internet.
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# One environment's student evidence search pilot: one container-image Lambda function behind its
# own CloudFront distribution, a Cognito user pool for the accounts the coach creates, and an
# append-only audit log. Decision: ADR-0019. Spec: v1-e39-t04-pilot-infrastructure.
#
# Called once from infrastructure/envs/dev and once from infrastructure/envs/prod, with different
# inputs and nothing copied between them (infrastructure/README.md). It hard-codes no account id,
# region or domain: the region comes from the calling root's provider, and the host, the zone and
# the evidence bucket are inputs.
#
#   main.tf             the repository, the function, its URL, its role and its two log groups
#   distribution.tf     CloudFront, its origin access control and the security headers
#   certificate.tf      the certificate for both hosts and every DNS record
#   user_pool.tf        the user pool, its groups, domain and app client, and the SES identity
#   parameters.tf       the client secret and the cookie keys, in Parameter Store
#   budget.tf           the pilot's own monthly budget
#   pilot_access.tf     the TubDeployer and TubAccounts permission sets
#
# The function's role is ADR-0019's role table, exactly, and tests/evidence_search.tftest.hcl
# checks it entry by entry. Every policy here is built with jsonencode rather than an
# aws_iam_policy_document data source, because a data source's rendered JSON is opaque to
# `terraform test` under a mocked provider and these policies are what the tests have to read.
#
# Applies and deploys are operator-run (docs/runbooks/evidence-search.md). The very first apply
# is targeted at the repository alone, because the function cannot be created until the first
# deploy has pushed an image into it (ADR-0019 (f) 2).

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  login_host    = "auth.${var.pilot_host}"
  pilot_origin  = "https://${var.pilot_host}"
  login_origin  = "https://${local.login_host}"
  is_production = var.environment == "prod"

  # The name `scripts/tub_deploy.sh` derives on its own, so a deploy never reads Terraform state.
  # Renaming one is a change to the script too.
  function_name   = var.name_prefix
  repository_name = var.name_prefix

  # ADR-0019 (a) 1. Fixed by the decision record rather than offered as inputs: changing one is a
  # change to the ADR first.
  function_memory_mb            = 2048
  function_ephemeral_storage_mb = 4096
  function_timeout_seconds      = 30
  function_reserved_concurrency = 10

  # ADR-0019 (e). The audit group is named debate-<env>-tub-audit, not /aws/lambda/..., so that
  # ADR-0010's debate-prod-* deny reaches it.
  audit_log_group_name         = "${var.name_prefix}-audit"
  app_log_group_name           = "${var.name_prefix}-app"
  audit_log_retention_days     = 400
  app_log_retention_days       = 30
  account_changes_stream_name  = "tub-users"
  function_role_name           = "${var.name_prefix}-function"
  function_role_policy_name    = "${var.name_prefix}-function"
  evidence_bucket_name         = split(":::", var.evidence_bucket_arn)[1]
  repository_images_kept       = 5
  lambda_web_adapter_port      = 8080
  lambda_web_adapter_readiness = "/healthz"
}

# ---------------------------------------------------------------------------------------------
# The image repository
# ---------------------------------------------------------------------------------------------

# Terraform owns the configuration; scripts/tub_deploy.sh owns the code (ADR-0019 (f) 2). Tags
# are mutable because nothing deploys by tag: the function is pointed at an image by digest.
#
# Tagged through the calling root's provider `default_tags`, which tflint cannot see from here;
# README.md explains the annotation.
# tflint-ignore: aws_resource_missing_tags
resource "aws_ecr_repository" "function" {
  name                 = local.repository_name
  image_tag_mutability = "MUTABLE"

  # force_delete stays false: a destroy that took the images with it would leave the function
  # pointing at nothing.
  force_delete = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "function" {
  repository = aws_ecr_repository.function.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last ${local.repository_images_kept} images (ADR-0019 (f) 3)."
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = local.repository_images_kept
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}

# The newest image in the repository, read once to create the function. Every later deploy moves
# the function by digest and Terraform ignores the image from then on, so this matters only at
# creation. On a fresh environment the repository is empty and this read fails, which is why the
# runbook's first apply targets the repository alone and the first deploy runs before the full one.
data "aws_ecr_image" "newest" {
  repository_name = aws_ecr_repository.function.name
  most_recent     = true
}

# ---------------------------------------------------------------------------------------------
# The two log groups (ADR-0019 (e))
# ---------------------------------------------------------------------------------------------

# Append-only by construction: no CloudWatch Logs API edits or deletes a single event, and the
# function's role holds nothing but CreateLogStream and PutLogEvents on it. Deletion protection on
# the group is a runbook step (`aws logs put-log-group-deletion-protection`), because provider
# 5.100.0 has no argument for it.
#
# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_log_group" "audit" {
  name              = local.audit_log_group_name
  retention_in_days = local.audit_log_retention_days

  # A `terraform destroy` forgets the group rather than deleting the record of who saw what. With
  # deletion protection on, a delete would be refused anyway; this keeps a destroy from failing
  # on it.
  skip_destroy = true
}

# The coach's `tub users` commands write their account-change records here, in a stream of their
# own (ADR-0019 (e) 3), under the TubAccounts permission set. Created here so that set needs
# PutLogEvents on this one stream and no CreateLogStream at all.
resource "aws_cloudwatch_log_stream" "account_changes" {
  name           = local.account_changes_stream_name
  log_group_name = aws_cloudwatch_log_group.audit.name
}

# The function's own application log, through its logging configuration. Not under /aws/lambda/
# for the same reason as the audit group.
#
# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudwatch_log_group" "app" {
  name              = local.app_log_group_name
  retention_in_days = local.app_log_retention_days
}

# ---------------------------------------------------------------------------------------------
# The function's role: ADR-0019's role table, exactly
# ---------------------------------------------------------------------------------------------

locals {
  function_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "LambdaInThisAccountOnly"
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      },
    ]
  })

  # The four key patterns of the role table. `raw/*` with GetObject and no GetObjectVersion is
  # what "current objects under raw/" means: a request without a version id reads the current
  # version, and a request naming an older one needs the action this role does not hold.
  # `reports/landscape/*` is the landscape pages' bundles (v1-e39-t17, data-use policy 1.16).
  function_readable_object_arns = [
    "${var.evidence_bucket_arn}/reports/tub/search/*",
    "${var.evidence_bucket_arn}/reports/landscape/*",
    "${var.evidence_bucket_arn}/raw/*",
    "${var.evidence_bucket_arn}/manifests/_suppression/suppression-list.jsonl",
  ]

  # The one listing the role may make: the landscape bundles, to find each caselist's newest
  # snapshot, since a bundle has no pointer to it. `s3:prefix` is what ListObjectsV2's Prefix is
  # checked against; a listing of the bucket root or of any other prefix is refused.
  function_listable_prefixes = ["reports/landscape/*"]

  function_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # No GetObjectVersion and no write.
        Sid      = "ReadThePilotIndexLandscapeBundlesCurrentRawEvidenceAndTheSuppressionList"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = local.function_readable_object_arns
      },
      {
        # No ListBucketVersions, and no listing outside the landscape bundles.
        Sid       = "ListTheLandscapeBundlesOnly"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = var.evidence_bucket_arn
        Condition = { StringLike = { "s3:prefix" = local.function_listable_prefixes } }
      },
      {
        # The evidence bucket's key, and only through S3: the role cannot call KMS directly on a
        # ciphertext it obtained some other way.
        Sid      = "DecryptEvidenceThroughS3Only"
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = var.evidence_kms_key_arn
        Condition = {
          StringEquals = { "kms:ViaService" = "s3.${data.aws_region.current.name}.amazonaws.com" }
        }
      },
      {
        # No delete, retention or policy action: the role can add to its logs and do nothing
        # else to them (ADR-0019 (e) 2).
        Sid    = "AppendToItsAuditAndApplicationLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = [
          "${aws_cloudwatch_log_group.audit.arn}:*",
          "${aws_cloudwatch_log_group.app.arn}:*",
        ]
      },
      {
        # The client secret and the cookie keys. SecureStrings under the AWS-managed aws/ssm key,
        # whose key policy already lets SSM decrypt for a caller in this account, so no KMS grant
        # is needed for them.
        Sid    = "ReadItsOwnParameters"
        Effect = "Allow"
        Action = "ssm:GetParameter"
        Resource = [
          aws_ssm_parameter.client_secret.arn,
          aws_ssm_parameter.cookie_keys.arn,
        ]
      },
    ]
  })
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_iam_role" "function" {
  name               = local.function_role_name
  description        = "The ${var.environment} student search pilot's function (ADR-0019, the function's role)."
  assume_role_policy = local.function_assume_role_policy
}

resource "aws_iam_role_policy" "function" {
  name   = local.function_role_policy_name
  role   = aws_iam_role.function.name
  policy = local.function_role_policy
}

# "No other grant", enforced rather than hoped for: these two make Terraform remove any inline
# policy or managed policy attached to the role outside this module, AWSLambdaBasicExecutionRole
# included, at the next apply.
resource "aws_iam_role_policies_exclusive" "function" {
  role_name    = aws_iam_role.function.name
  policy_names = [aws_iam_role_policy.function.name]
}

resource "aws_iam_role_policy_attachments_exclusive" "function" {
  role_name   = aws_iam_role.function.name
  policy_arns = []
}

# ---------------------------------------------------------------------------------------------
# The function and its URL (ADR-0019 (a) 1 and 2)
# ---------------------------------------------------------------------------------------------

# tflint-ignore: aws_resource_missing_tags
resource "aws_lambda_function" "pilot" {
  function_name = local.function_name
  description   = "The ${var.environment} student evidence search pilot (ADR-0019)."
  role          = aws_iam_role.function.arn

  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.function.repository_url}@${data.aws_ecr_image.newest.image_digest}"
  architectures = ["arm64"]

  memory_size                    = local.function_memory_mb
  timeout                        = local.function_timeout_seconds
  reserved_concurrent_executions = local.function_reserved_concurrency

  ephemeral_storage {
    size = local.function_ephemeral_storage_mb
  }

  # Text, with no application log level, keeps the Lambda Web Adapter above debug. v1.1.0 logs a
  # request's URL and headers only at debug (src/lib.rs lines 1543, 1624 and 1665), at the level
  # AWS_LAMBDA_LOG_LEVEL sets (src/main.rs lines 20-23), which Lambda sets only for the JSON format.
  # The dev pilot's app log held no request path in 30 days of use (v1-e39-t17, 2026-10-25), and a
  # page's path can name a school.
  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.app.name
  }

  # Configuration, not secrets. The app takes its own origin and the login host from here and
  # never from a forwarded Host header (ADR-0019 (b) 3); the client secret and the cookie keys are
  # read from Parameter Store by name at cold start.
  environment {
    variables = {
      TUB_ENVIRONMENT              = var.environment
      TUB_PUBLIC_ORIGIN            = local.pilot_origin
      TUB_LOGIN_ORIGIN             = local.login_origin
      TUB_USER_POOL_ID             = aws_cognito_user_pool.pilot.id
      TUB_CLIENT_ID                = aws_cognito_user_pool_client.web.id
      TUB_CLIENT_SECRET_PARAMETER  = aws_ssm_parameter.client_secret.name
      TUB_COOKIE_KEYS_PARAMETER    = aws_ssm_parameter.cookie_keys.name
      TUB_EVIDENCE_BUCKET          = local.evidence_bucket_name
      TUB_AUDIT_LOG_GROUP          = aws_cloudwatch_log_group.audit.name
      AWS_LWA_PORT                 = tostring(local.lambda_web_adapter_port)
      AWS_LWA_READINESS_CHECK_PATH = local.lambda_web_adapter_readiness
    }
  }

  lifecycle {
    # The deploy script owns the code (ADR-0019 (f) 2): it moves the function to a new digest on
    # every deploy, and Terraform must not move it back.
    ignore_changes = [image_uri]
  }

  # The role's grants exist before the function first runs, so the first cold start does not
  # race them.
  depends_on = [
    aws_iam_role_policy.function,
    aws_cloudwatch_log_group.app,
  ]
}

# AWS_IAM: Lambda refuses any request not signed by a principal it trusts, before the function
# runs. CloudFront's origin access control is the only such principal (distribution.tf).
resource "aws_lambda_function_url" "pilot" {
  function_name      = aws_lambda_function.pilot.function_name
  authorization_type = "AWS_IAM"
  invoke_mode        = "BUFFERED"
}

# Both permissions, each conditioned on this environment's distribution. CloudFront's
# documentation for a function URL origin requires the pair.
resource "aws_lambda_permission" "cloudfront_invoke_function_url" {
  statement_id           = "AllowThisDistributionToInvokeTheFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.pilot.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.pilot.arn
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "cloudfront_invoke_function" {
  statement_id  = "AllowThisDistributionToInvokeTheFunction"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pilot.function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.pilot.arn
}

# The credential the site is deployed with: an Identity Center permission set that can publish
# this environment's site and do nothing else.
#
# v1-e36-t05-site-deploy syncs the built export into the bucket and invalidates the distribution.
# Prod is the reason this exists: the everyday `debate-prod` profile is DebateReadOnly and cannot
# write, and DebateMaintainer is denied every debate-prod-* resource by ADR-0010 rule 4, so
# without this the only way to publish prod would be break-glass administrator access for a
# routine act.
#
# The policy names exactly six actions on exactly two resources, both of them this environment's
# own. It is built with jsonencode rather than an aws_iam_policy_document data source so that the
# module's tests can read it back under a mocked provider — a policy document's rendered JSON is
# opaque there, and this is precisely the policy worth asserting on.
#
# There are no long-lived access keys anywhere in this path: the operator signs in with SSO and
# assumes this set through the profile named after it (task spec: forbidden).

locals {
  create_publisher_permission_set = var.identity_center_instance_arn != null

  # DebateDevSitePublisher / DebateProdSitePublisher.
  publisher_permission_set_name = "Debate${title(var.environment)}SitePublisher"

  publisher_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # A bucket-level action: `aws s3 sync --delete` has to enumerate what is already there
        # before it can work out what to upload and what to remove.
        Sid      = "ListSiteBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.site.arn
      },
      {
        Sid    = "PublishSiteObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "${aws_s3_bucket.site.arn}/*"
      },
      {
        # A static export behind a CDN serves stale HTML until it is invalidated, so the deploy is
        # not finished without this.
        #
        # GetInvalidation is here because creating an invalidation is not the same as it having
        # finished, and the difference matters: docs/policies/website-publishing.md promises that
        # something published about a student comes down within 24 hours of a request, and "down"
        # means gone from the edge caches, not gone from the bucket. `aws cloudfront wait
        # invalidation-completed`, which scripts/site_deploy.sh runs, polls GetInvalidation. It
        # reads the progress of an invalidation on this distribution and nothing else, so the set
        # is still an allow-list of exactly what one deploy does (v1-e36-t05).
        Sid    = "InvalidateSiteDistribution"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
        ]
        Resource = aws_cloudfront_distribution.site.arn
      },
    ]
  })
}

# Tagged through the calling root's provider `default_tags`, which tflint cannot see from here;
# README.md explains the annotation.
# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "site_publisher" {
  count = local.create_publisher_permission_set ? 1 : 0

  name             = local.publisher_permission_set_name
  description      = "Publishes the ${var.environment} team website: sync ${local.bucket_name}, invalidate its distribution and watch that invalidation finish. Nothing else (ADR-0012)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT1H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "site_publisher" {
  count = local.create_publisher_permission_set ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.site_publisher[0].arn
  inline_policy      = local.publisher_policy
}

data "aws_caller_identity" "current" {}

data "aws_identitystore_user" "publishers" {
  for_each = local.create_publisher_permission_set ? toset(var.publisher_user_names) : toset([])

  identity_store_id = var.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

resource "aws_ssoadmin_account_assignment" "site_publishers" {
  for_each = local.create_publisher_permission_set ? toset(var.publisher_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.site_publisher[0].arn

  principal_id   = data.aws_identitystore_user.publishers[each.value].user_id
  principal_type = "USER"

  target_id   = data.aws_caller_identity.current.account_id
  target_type = "AWS_ACCOUNT"
}

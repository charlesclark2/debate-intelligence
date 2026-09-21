# One environment's public static website: a private S3 bucket served through CloudFront with
# origin access control. Decision: ADR-0012. Spec: v1-e36-t02-site-hosting.
#
# Called once from infrastructure/envs/dev and once from infrastructure/envs/prod, with different
# inputs and nothing copied between them (infrastructure/README.md). It hard-codes no account id,
# region or domain name: the region comes from the calling root's provider, and the domain is an
# input that is empty until one is bought.
#
# The bucket is never public and is never reachable except through its own distribution. That is
# the whole point of the arrangement, and the three things that make it true — the four
# block-public-access flags, BucketOwnerEnforced ownership, and a bucket policy whose only Allow
# is conditioned on this distribution's ARN — are each asserted in tests/static_site.tftest.hcl.

locals {
  bucket_name = "${var.name_prefix}-${var.bucket_suffix}"

  has_custom_domain = length(var.domain_names) > 0

  # The certificate the distribution serves. Null means the CloudFront default certificate on the
  # *.cloudfront.net domain, which is how the site runs until a team domain exists. With the zone
  # in Route 53 the ARN comes from aws_acm_certificate_validation, so the distribution is not
  # updated until ACM has actually issued; with DNS at an external registrar there is nothing to
  # wait on in Terraform and the operator runs the apply twice (certificate.tf).
  certificate_arn = (
    !local.has_custom_domain ? null :
    local.manage_dns ? aws_acm_certificate_validation.site[0].certificate_arn :
    aws_acm_certificate.site[0].arn
  )

  # The one name the site answers on for real; every other alias is 301'd to it by the viewer
  # function. Empty when there is no team domain yet, which turns the redirect off so the
  # *.cloudfront.net domain keeps working.
  canonical_host = local.has_custom_domain ? coalesce(var.canonical_domain_name, var.domain_names[0]) : ""

  site_url = local.has_custom_domain ? "https://${local.canonical_host}/" : "https://${aws_cloudfront_distribution.site.domain_name}/"
}

# ---------------------------------------------------------------------------------------------
# Origin: a private bucket
# ---------------------------------------------------------------------------------------------

# The five standard tags reach every resource in this module through the calling root's provider
# `default_tags` (infrastructure/README.md). tflint's aws_resource_missing_tags rule reads that
# block, and cannot see it when it lints this directory on its own — linting envs/dev or envs/prod
# follows the module call and does check it. Hence the annotation, rather than a tags argument on
# every resource or a relaxed .tflint.hcl for this directory.
# tflint-ignore: aws_resource_missing_tags
resource "aws_s3_bucket" "site" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  # All four, deliberately. Blocking public ACLs without restricting public bucket policies (or
  # the other way round) leaves a way to publish the bucket that a later task would not notice.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ACLs off entirely: every grant on this bucket is in the bucket policy below, where it can be
# read in one place. It is also what origin access control expects.
resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# SSE-S3, not a customer-managed KMS key. The objects are the public pages of a public website;
# a KMS key would add per-request cost and a key policy CloudFront has to be granted, and would
# protect content that is served to anyone who asks for it.
resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Deploys are `aws s3 sync --delete` (v1-e36-t05-site-deploy). Versioning is what turns a wrong
# --delete into an inconvenience instead of a lost site.
resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  depends_on = [aws_s3_bucket_versioning.site]

  rule {
    id     = "expire-superseded-site-versions"
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

# The bucket policy, built with jsonencode rather than an aws_iam_policy_document data source.
# A data source's rendered JSON is opaque to `terraform test` under a mocked provider, and this
# policy is precisely what the tests have to be able to read: one Allow, to CloudFront, for one
# distribution.
locals {
  bucket_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Origin access control: CloudFront signs its origin requests with SigV4, and this
        # condition ties the grant to one distribution. Not an origin access identity, which is
        # the legacy mechanism and grants an IAM principal instead.
        Sid       = "AllowCloudFrontOriginAccessControlRead"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.site.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.site.arn
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.site.arn,
          "${aws_s3_bucket.site.arn}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
    ]
  })
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = local.bucket_policy

  # Never attach a policy to a bucket whose public access is not yet blocked: the window between
  # the two is the only moment this bucket could be made public by a mistake in the policy.
  depends_on = [aws_s3_bucket_public_access_block.site]
}

# ---------------------------------------------------------------------------------------------
# Delivery: CloudFront
# ---------------------------------------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = var.name_prefix
  description                       = "Signs CloudFront's requests to the ${var.environment} site bucket so the bucket can stay private (ADR-0012)."
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# One viewer-request function: the canonical-host 301 and the page-URL-to-object rewrite.
# A cache behaviour takes exactly one function per event type, and functions/site_request.js.tftpl
# explains why both jobs land here rather than in an S3 website redirect bucket.
resource "aws_cloudfront_function" "site_request" {
  name    = "${var.name_prefix}-site-request"
  runtime = "cloudfront-js-2.0"
  comment = "Redirects non-canonical hosts and maps /path/ to /path/index.html for the Next.js static export (ADR-0012)."
  publish = true

  code = templatefile("${path.module}/functions/site_request.js.tftpl", {
    canonical_host = local.canonical_host
  })
}

# Caching is the AWS managed CachingOptimized policy: compress, respect the origin's
# Cache-Control, and forward no cookies, headers or query strings. The deploy script sets the
# per-object Cache-Control (a year for hashed _next/static assets, no-cache for HTML), so the
# cache behaviour is a property of what was uploaded rather than a second place to configure.
data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

# Security headers, set at the edge. A static export cannot set a response header itself, and
# putting them here means every object gets them, including ones uploaded by a later task.
resource "aws_cloudfront_response_headers_policy" "site" {
  name    = "${var.name_prefix}-security-headers"
  comment = "HSTS, CSP and the rest for the ${var.environment} team website (ADR-0012)."

  security_headers_config {
    strict_transport_security {
      override                   = true
      access_control_max_age_sec = var.hsts_max_age_seconds
      include_subdomains         = true
      # Not preloaded. Preloading is baked into browsers and effectively permanent; committing a
      # school team's domain to it is not this module's call to make.
      preload = false
    }

    content_security_policy {
      override                = true
      content_security_policy = var.content_security_policy
    }

    content_type_options {
      override = true
    }

    referrer_policy {
      override        = true
      referrer_policy = "strict-origin-when-cross-origin"
    }

    # Belt and braces with the CSP's frame-ancestors 'none', for anything that still reads the
    # older header.
    frame_options {
      override     = true
      frame_option = "DENY"
    }
  }

  custom_headers_config {
    items {
      header   = "Permissions-Policy"
      value    = var.permissions_policy
      override = true
    }

    dynamic "items" {
      for_each = var.noindex ? [1] : []

      content {
        header   = "X-Robots-Tag"
        value    = "noindex, nofollow"
        override = true
      }
    }
  }
}

# The five standard tags reach every resource in this module through the calling root's provider
# `default_tags` (infrastructure/README.md). tflint's aws_resource_missing_tags rule reads that
# block, and cannot see it when it lints this directory on its own — linting envs/dev or envs/prod
# follows the module call and does check it. Hence the annotation, rather than a tags argument on
# every resource or a relaxed .tflint.hcl for this directory.
# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "${var.name_prefix} — public team website (ADR-0012)"
  default_root_object = "index.html"
  price_class         = var.price_class
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  aliases             = var.domain_names

  # No logging_config, and no aws_cloudfront_realtime_log_config. ADR-0012 decision 8: the
  # audience is schoolchildren and their families, so no per-request record of visitor IP
  # addresses is created. CloudFront's own aggregate reports are the only traffic data the team
  # gets. Turning this on is a spec and publishing-policy change, not a configuration tweak.

  origin {
    origin_id                = local.bucket_name
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = local.bucket_name
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.site_request.arn
    }
  }

  # A private bucket answers a request for a missing key with 403, not 404, because the
  # distribution is not granted s3:ListBucket. Both become the site's own 404 page; without the
  # 403 mapping a mistyped URL would show CloudFront's XML error document.
  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  viewer_certificate {
    cloudfront_default_certificate = local.certificate_arn == null
    acm_certificate_arn            = local.certificate_arn
    # AWS forces the `TLSv1` security policy on a distribution using the CloudFront default
    # certificate and rejects any other value, so the TLS floor this project wants can only be
    # set once a certificate of our own is attached (ADR-0012 consequences).
    minimum_protocol_version = local.certificate_arn == null ? null : var.minimum_tls_version
    ssl_support_method       = local.certificate_arn == null ? null : "sni-only"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}

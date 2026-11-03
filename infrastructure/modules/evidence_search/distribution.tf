# The pilot's own CloudFront distribution (ADR-0019 (a) 4), separate from the website's so that a
# problem here cannot reach the parents' pages.
#
# Its one origin is the function URL, signed by an origin access control of type `lambda`. The
# evidence bucket is not an origin of this or any distribution: CloudFront never reads it, and the
# bucket's policy grants CloudFront nothing (tests/evidence_search.tftest.hcl).

locals {
  # The function URL is https://<id>.lambda-url.<region>.on.aws/; an origin wants the bare host.
  function_url_host = trimsuffix(trimprefix(aws_lambda_function_url.pilot.function_url, "https://"), "/")
  function_origin   = "${var.name_prefix}-function-url"

  # ADR-0019 (a) 4, directive by directive. form-action names the login host because a sign-out
  # or sign-in step may submit a form that lands there.
  content_security_policy = join("; ", [
    "default-src 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self' ${local.login_origin}",
  ])

  # Every device capability a page could ask for, turned off. The pilot asks for none.
  permissions_policy = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), interest-cohort=(), magnetometer=(), microphone=(), payment=(), usb=()"

  hsts_max_age_seconds = 31536000
  minimum_tls_version  = "TLSv1.2_2021"
}

resource "aws_cloudfront_origin_access_control" "function_url" {
  name                              = var.name_prefix
  description                       = "Signs CloudFront's requests to the ${var.environment} pilot's function URL, so Lambda refuses any request that did not come through this distribution (ADR-0019)."
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Signed-in pages are never cached at the edge: the app sends `Cache-Control: private, no-store`
# and this policy caches nothing whatever the origin says (ADR-0019 (a) 4 and 5).
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

# Every viewer header, cookie and query string except Host: the function URL expects its own
# Host, and the app takes its public origin from configuration instead (ADR-0019 (b) 3).
data "aws_cloudfront_origin_request_policy" "all_viewer_except_host_header" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_response_headers_policy" "pilot" {
  name    = "${var.name_prefix}-security-headers"
  comment = "CSP, HSTS and the rest for the ${var.environment} student search pilot (ADR-0019)."

  security_headers_config {
    strict_transport_security {
      override                   = true
      access_control_max_age_sec = local.hsts_max_age_seconds
      include_subdomains         = true
      preload                    = false
    }

    content_security_policy {
      override                = true
      content_security_policy = local.content_security_policy
    }

    content_type_options {
      override = true
    }

    referrer_policy {
      override        = true
      referrer_policy = "no-referrer"
    }

    frame_options {
      override     = true
      frame_option = "DENY"
    }
  }

  custom_headers_config {
    items {
      header   = "Permissions-Policy"
      value    = local.permissions_policy
      override = true
    }

    dynamic "items" {
      for_each = local.is_production ? [] : [1]

      content {
        header   = "X-Robots-Tag"
        value    = "noindex, nofollow"
        override = true
      }
    }
  }
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudfront_distribution" "pilot" {
  enabled         = true
  comment         = "${var.name_prefix} — student evidence search pilot (ADR-0019)"
  price_class     = "PriceClass_100"
  is_ipv6_enabled = true
  http_version    = "http2and3"
  aliases         = [var.pilot_host]

  # No logging_config, no aws_cloudfront_realtime_log_config and no web_acl_id (ADR-0019 (a) 4,
  # ADR-0012 decision 8): no per-request record of a student's address is created anywhere.

  origin {
    origin_id                = local.function_origin
    domain_name              = local.function_url_host
    origin_access_control_id = aws_cloudfront_origin_access_control.function_url.id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = local.function_origin
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.pilot.id
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.pilot.certificate_arn
    minimum_protocol_version = local.minimum_tls_version
    ssl_support_method       = "sni-only"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}

# A domain that exists only to send people somewhere else.
#
# wfbdebate.com and www.wfbdebate.com were registered alongside wfbdebate.org so that neither
# spelling reaches a stranger's site. They are not a second copy of the website: every request to
# them is answered with a 301 to the same path on wfbdebate.org, so there is one address in
# search results, one address on a flyer, and one place content actually lives.
#
# Decision: ADR-0012. Spec: v1-e36-t02-site-hosting.
#
# The redirect is a CloudFront Function on viewer request, not an S3 bucket with
# `redirect_all_requests_to`. The bucket version is the older recipe, and it needs the S3 website
# endpoint — which is plain HTTP, has to be public, and cannot be restricted to a distribution.
# The task spec forbids all three. This way there is no bucket at all: nothing to make public,
# nothing to leave objects in, nothing to pay for beyond the requests.
#
# A distribution still has to name an origin even when nothing ever reaches it, so the origin is
# the site itself. If the function were ever removed, the failure mode is serving the real site
# from the .com name rather than an error page.

locals {
  # Certificate names are known in advance, so the for_each keys below do not depend on anything
  # ACM returns.
  certificate_validation_options = {
    for option in aws_acm_certificate.redirect.domain_validation_options :
    option.domain_name => option
  }

  manage_dns         = var.route53_zone_id != null
  alias_record_types = ["A", "AAAA"]
}

data "aws_region" "current" {}

# CloudFront reads certificates from us-east-1 and nowhere else. ADR-0010 already pins this
# project to us-east-1; the check turns a change to that into a readable message at plan time.
check "certificate_region_supports_cloudfront" {
  assert {
    condition = data.aws_region.current.name == "us-east-1"
    error_message = join(" ", [
      "This module is being applied in ${data.aws_region.current.name}, but CloudFront only accepts",
      "ACM certificates from us-east-1. Apply it from a us-east-1 root (ADR-0010).",
    ])
  }
}

# Tagged through the calling root's provider `default_tags`, which tflint cannot see from here;
# README.md explains the annotation.
# tflint-ignore: aws_resource_missing_tags
resource "aws_acm_certificate" "redirect" {
  domain_name               = var.domain_names[0]
  subject_alternative_names = [for domain in var.domain_names : domain if domain != var.domain_names[0]]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  for_each = local.manage_dns ? toset(var.domain_names) : toset([])

  zone_id         = var.route53_zone_id
  name            = local.certificate_validation_options[each.key].resource_record_name
  type            = local.certificate_validation_options[each.key].resource_record_type
  records         = [local.certificate_validation_options[each.key].resource_record_value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "redirect" {
  count = local.manage_dns ? 1 : 0

  certificate_arn         = aws_acm_certificate.redirect.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]

  timeouts {
    # Long enough for a domain registered the same day to finish delegating, short enough that a
    # zone whose name servers were never updated fails the apply the operator is watching.
    create = "30m"
  }
}

resource "aws_cloudfront_function" "redirect" {
  name    = "${var.name_prefix}-redirect"
  runtime = "cloudfront-js-2.0"
  comment = "301s every request to https://${var.target_host} with the path preserved (ADR-0012)."
  publish = true

  code = templatefile("${path.module}/functions/redirect.js.tftpl", {
    target_host               = var.target_host
    strict_transport_security = var.strict_transport_security
  })
}

# Nothing is ever fetched from the origin, so nothing should be cached either. Saying so with the
# managed CachingDisabled policy is clearer than picking a TTL for responses that do not exist.
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

# The five standard tags reach this resource through the calling root's provider `default_tags`
# (infrastructure/README.md), which tflint cannot see when it lints this directory on its own.
# tflint-ignore: aws_resource_missing_tags
resource "aws_cloudfront_distribution" "redirect" {
  enabled         = true
  comment         = "${var.name_prefix} — 301 to https://${var.target_host} (ADR-0012)"
  price_class     = var.price_class
  is_ipv6_enabled = true
  http_version    = "http2and3"
  aliases         = var.domain_names

  # No logging_config, for the same reason as the site itself (ADR-0012 decision 8).

  # Never contacted: the viewer-request function returns before CloudFront looks at the origin.
  # Pointing it at the real site means a missing function degrades to serving the site from the
  # wrong name rather than to an error.
  origin {
    origin_id   = var.target_host
    domain_name = var.target_host

    custom_origin_config {
      origin_protocol_policy = "https-only"
      http_port              = 80
      https_port             = 443
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = var.target_host
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id = data.aws_cloudfront_cache_policy.caching_disabled.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.redirect.arn
    }
  }

  viewer_certificate {
    acm_certificate_arn      = local.manage_dns ? aws_acm_certificate_validation.redirect[0].certificate_arn : aws_acm_certificate.redirect.arn
    minimum_protocol_version = var.minimum_tls_version
    ssl_support_method       = "sni-only"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}

resource "aws_route53_record" "redirect_alias" {
  for_each = local.manage_dns ? {
    for pair in setproduct(var.domain_names, local.alias_record_types) :
    "${pair[0]}-${pair[1]}" => { name = pair[0], type = pair[1] }
  } : {}

  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type

  alias {
    name                   = aws_cloudfront_distribution.redirect.domain_name
    zone_id                = aws_cloudfront_distribution.redirect.hosted_zone_id
    evaluate_target_health = false
  }
}

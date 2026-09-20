# The certificate and the DNS records for this environment's domain names.
#
# Everything here is conditional on domain_names being non-empty, so the site can be applied,
# deployed and reviewed on its *.cloudfront.net domain before a domain exists or while a
# certificate is still validating. That is the point of keeping the domain a variable: an apply
# with `-var 'site_domain_names=[]'` always works.
#
# The hosted zone is an input, never a resource. The zones for wfbdebate.com and wfbdebate.org
# came with the registration, and a `terraform destroy` that took a hosted zone with it would
# strand the domain (task spec: forbidden).

data "aws_region" "current" {}

# CloudFront reads certificates from us-east-1 and nowhere else. ADR-0010 already pins every
# resource in this project to us-east-1, so this only fires if that ever changes — as a readable
# warning rather than an apply that fails deep inside the distribution.
check "certificate_region_supports_cloudfront" {
  assert {
    condition = !local.has_custom_domain || data.aws_region.current.name == "us-east-1"
    error_message = join(" ", [
      "This module is being applied in ${data.aws_region.current.name}, but CloudFront only accepts",
      "ACM certificates from us-east-1. Apply the site from a us-east-1 root (ADR-0010), or give the",
      "module a provider aliased to us-east-1.",
    ])
  }
}

# Tagged through the calling root's provider `default_tags`, which tflint cannot see from here;
# README.md explains the annotation.
# tflint-ignore: aws_resource_missing_tags
resource "aws_acm_certificate" "site" {
  count = local.has_custom_domain ? 1 : 0

  domain_name               = local.canonical_host
  subject_alternative_names = [for domain in var.domain_names : domain if domain != local.canonical_host]
  validation_method         = "DNS"

  # A certificate cannot be deleted while a distribution is using it, so a change to the name list
  # has to create the replacement before the old one goes away.
  lifecycle {
    create_before_destroy = true
  }
}

locals {
  # Keyed by the domain names we asked for, which are known at plan time. Keying the for_each on
  # ACM's own output instead would make the resource addresses depend on a value that does not
  # exist until the certificate has been created.
  certificate_validation_options = {
    for option in try(aws_acm_certificate.site[0].domain_validation_options, []) :
    option.domain_name => option
  }

  manage_dns         = local.has_custom_domain && var.route53_zone_id != null
  alias_record_types = ["A", "AAAA"]
}

# DNS validation records. With the zone in Route 53 Terraform writes them and the apply completes
# in one pass; with DNS at an external registrar route53_zone_id is null, nothing is written here,
# and the operator adds the records from the certificate_validation_records output by hand.
resource "aws_route53_record" "certificate_validation" {
  for_each = local.manage_dns ? toset(var.domain_names) : toset([])

  zone_id = var.route53_zone_id
  name    = local.certificate_validation_options[each.key].resource_record_name
  type    = local.certificate_validation_options[each.key].resource_record_type
  records = [local.certificate_validation_options[each.key].resource_record_value]
  ttl     = 60

  # ACM issues the same validation record for names that share a certificate, and a re-request
  # after a name change writes the same record again. Overwriting is what we want; failing the
  # apply on an existing record is not.
  allow_overwrite = true
}

# Blocks until ACM has issued. The distribution reads its certificate ARN from here rather than
# from aws_acm_certificate, so CloudFront is never handed a certificate that is still
# PENDING_VALIDATION — which it rejects.
resource "aws_acm_certificate_validation" "site" {
  count = local.manage_dns ? 1 : 0

  certificate_arn         = aws_acm_certificate.site[0].arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]

  timeouts {
    # Long enough for a domain registered the same day to finish delegating, short enough that a
    # zone whose name servers were never updated fails the apply the operator is sitting in front
    # of instead of an hour later.
    create = "30m"
  }
}

# Alias records for every name on the distribution, including the ones that only exist to be
# redirected: a 301 from www can only be served by a distribution the browser reached first.
resource "aws_route53_record" "site_alias" {
  for_each = local.manage_dns ? {
    for pair in setproduct(var.domain_names, local.alias_record_types) :
    "${pair[0]}-${pair[1]}" => { name = pair[0], type = pair[1] }
  } : {}

  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

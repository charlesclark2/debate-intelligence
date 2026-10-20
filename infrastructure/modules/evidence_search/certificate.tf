# The certificate for the pilot host and the login host, and every DNS record the pilot needs, in
# the existing zone (ADR-0019 (a) 6). The zone is an input read by the calling root through a data
# source; nothing here creates or destroys a zone.
#
# One certificate covers both names: the distribution serves it for the pilot host, and Cognito's
# own distribution for the managed login serves it for the login host. Both read certificates
# from us-east-1 only, where ADR-0010 already puts everything.

check "certificate_region_supports_cloudfront_and_cognito" {
  assert {
    condition = data.aws_region.current.name == "us-east-1"
    error_message = join(" ", [
      "This module is being applied in ${data.aws_region.current.name}, but CloudFront and Cognito's",
      "custom domains only accept ACM certificates from us-east-1 (ADR-0010, ADR-0019).",
    ])
  }
}

locals {
  certificate_names  = [var.pilot_host, local.login_host]
  alias_record_types = ["A", "AAAA"]

  # Keyed by the names asked for, which are known at plan time, rather than by ACM's output.
  certificate_validation_options = {
    for option in aws_acm_certificate.pilot.domain_validation_options :
    option.domain_name => option
  }
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_acm_certificate" "pilot" {
  domain_name               = var.pilot_host
  subject_alternative_names = [local.login_host]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  for_each = toset(local.certificate_names)

  zone_id = var.route53_zone_id
  name    = local.certificate_validation_options[each.key].resource_record_name
  type    = local.certificate_validation_options[each.key].resource_record_type
  records = [local.certificate_validation_options[each.key].resource_record_value]
  ttl     = 60

  allow_overwrite = true
}

# Blocks until ACM has issued, so neither distribution is handed a certificate still pending.
resource "aws_acm_certificate_validation" "pilot" {
  certificate_arn         = aws_acm_certificate.pilot.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]

  timeouts {
    create = "30m"
  }
}

# The pilot host, at this environment's distribution.
resource "aws_route53_record" "pilot_alias" {
  for_each = toset(local.alias_record_types)

  zone_id = var.route53_zone_id
  name    = var.pilot_host
  type    = each.key

  alias {
    name                   = aws_cloudfront_distribution.pilot.domain_name
    zone_id                = aws_cloudfront_distribution.pilot.hosted_zone_id
    evaluate_target_health = false
  }
}

# The login host, at the distribution Cognito runs for the managed login. Cognito owns that
# distribution; the pool domain's outputs say where it is.
resource "aws_route53_record" "login_alias" {
  for_each = toset(local.alias_record_types)

  zone_id = var.route53_zone_id
  name    = local.login_host
  type    = each.key

  alias {
    name                   = aws_cognito_user_pool_domain.login.cloudfront_distribution
    zone_id                = aws_cognito_user_pool_domain.login.cloudfront_distribution_zone_id
    evaluate_target_health = false
  }
}

# Easy DKIM for the SES identity the pool sends its email codes from (user_pool.tf). SES always
# issues three tokens for a domain identity, which is why this is a count and not a for_each over
# a list that does not exist until the identity does.
resource "aws_route53_record" "ses_dkim" {
  count = 3

  zone_id = var.route53_zone_id
  name    = "${aws_sesv2_email_identity.pilot.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.pilot_host}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_sesv2_email_identity.pilot.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

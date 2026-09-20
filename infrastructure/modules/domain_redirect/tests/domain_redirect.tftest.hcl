# Offline tests for the domain_redirect module. `mock_provider "aws"` means no credentials, no
# network and no AWS account.
#
#   terraform -chdir=infrastructure/modules/domain_redirect init -backend=false
#   terraform -chdir=infrastructure/modules/domain_redirect test
#
# The properties worth holding on to here are that the redirect is permanent, that it keeps the
# path, that it never becomes a second copy of the site, and that nothing in its path is a public
# bucket or a plain-HTTP endpoint.

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      name = "us-east-1"
    }
  }

  mock_data "aws_cloudfront_cache_policy" {
    defaults = {
      id = "mock-caching-disabled"
    }
  }

  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::111122223333:function/mock-redirect"
    }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::111122223333:distribution/EMOCKREDIRECT"
      domain_name    = "dmockredirect.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:111122223333:certificate/mock"
      domain_validation_options = [
        {
          domain_name           = "wfbdebate.com"
          resource_record_name  = "_mock1.wfbdebate.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock1.acm-validations.aws."
        },
        {
          domain_name           = "www.wfbdebate.com"
          resource_record_name  = "_mock2.www.wfbdebate.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock2.acm-validations.aws."
        },
      ]
    }
  }
}

variables {
  name_prefix     = "debate-prod-site-redirect"
  domain_names    = ["wfbdebate.com", "www.wfbdebate.com"]
  target_host     = "wfbdebate.org"
  route53_zone_id = "Z0MOCKCOMZONE"
}

run "every_request_is_answered_with_a_permanent_redirect" {
  assert {
    condition     = strcontains(aws_cloudfront_function.redirect.code, "statusCode: 301")
    error_message = "The redirect must be permanent: a 302 leaves the .com name in search results and in browser history."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.redirect.code, "var TARGET_HOST = 'wfbdebate.org';")
    error_message = "The function must know where it is redirecting to."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.redirect.code, "request.uri")
    error_message = "The redirect must preserve the path, so a bookmarked .com page lands on the same .org page."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.redirect.code, "strict-transport-security")
    error_message = "The redirect is often the first response a browser sees for these names; it must carry HSTS."
  }

  assert {
    condition     = aws_cloudfront_function.redirect.publish
    error_message = "The function must be published, not left in DEVELOPMENT."
  }

  assert {
    condition = length([
      for association in aws_cloudfront_distribution.redirect.default_cache_behavior[0].function_association :
      association
      if association.event_type == "viewer-request" && association.function_arn == aws_cloudfront_function.redirect.arn
    ]) == 1
    error_message = "The redirect has to run on viewer request, before CloudFront ever looks at an origin."
  }
}

run "the_redirect_is_https_only_and_has_its_own_certificate" {
  assert {
    condition     = aws_cloudfront_distribution.redirect.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "http:// must redirect to https:// on the .com names too."
  }

  assert {
    condition     = aws_cloudfront_distribution.redirect.viewer_certificate[0].minimum_protocol_version == "TLSv1.2_2021"
    error_message = "The TLS floor must be 1.2 (task spec: forbidden below 1.2)."
  }

  assert {
    # Unset rather than false, which is what "we never asked for it" looks like in state.
    condition     = coalesce(aws_cloudfront_distribution.redirect.viewer_certificate[0].cloudfront_default_certificate, false) == false
    error_message = "The redirect must serve its own certificate: the CloudFront default certificate does not cover the .com names."
  }

  assert {
    condition     = aws_acm_certificate.redirect.domain_name == "wfbdebate.com"
    error_message = "The certificate's common name must be the apex of the redirected domain."
  }

  assert {
    condition     = aws_acm_certificate.redirect.subject_alternative_names == toset(["www.wfbdebate.com"])
    error_message = "Every other redirected name must be a subject alternative name on the same certificate."
  }

  assert {
    condition     = aws_acm_certificate.redirect.validation_method == "DNS"
    error_message = "The certificate must be DNS validated."
  }

  assert {
    condition     = aws_cloudfront_distribution.redirect.aliases == toset(["wfbdebate.com", "www.wfbdebate.com"])
    error_message = "The distribution must claim both .com names, or one of them will not resolve to it."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.redirect.logging_config) == 0
    error_message = "No access logging here either (ADR-0012 decision 8)."
  }
}

run "the_origin_is_never_a_public_bucket_or_a_website_endpoint" {
  assert {
    condition = alltrue([
      for origin in aws_cloudfront_distribution.redirect.origin :
      origin.custom_origin_config[0].origin_protocol_policy == "https-only"
    ])
    error_message = "The origin must be HTTPS only. An S3 website endpoint, the other way to build a redirect, is plain HTTP and public — which is why this module has no bucket at all."
  }

  assert {
    condition = alltrue([
      for origin in aws_cloudfront_distribution.redirect.origin :
      !strcontains(origin.domain_name, "s3-website")
    ])
    error_message = "No S3 website endpoint anywhere in the path (task spec: forbidden)."
  }

  assert {
    condition     = alltrue([for origin in aws_cloudfront_distribution.redirect.origin : origin.domain_name == "wfbdebate.org"])
    error_message = "If the function ever went missing, the origin should degrade to the real site rather than to an error."
  }
}

run "dns_records_are_written_in_the_com_zone" {
  assert {
    condition     = length(aws_route53_record.certificate_validation) == 2
    error_message = "One validation record per redirected name."
  }

  assert {
    condition     = length(aws_route53_record.redirect_alias) == 4
    error_message = "Each redirected name needs an A and an AAAA alias record."
  }

  assert {
    condition     = alltrue([for record in aws_route53_record.redirect_alias : record.zone_id == "Z0MOCKCOMZONE"])
    error_message = "The alias records belong in the .com zone, not the site's zone."
  }

  assert {
    condition     = length(aws_acm_certificate_validation.redirect) == 1
    error_message = "With the zone in Route 53 the apply must wait for ACM to issue."
  }

  assert {
    condition     = output.target_url == "https://wfbdebate.org/"
    error_message = "target_url must name the site the .com domain points at."
  }
}

run "an_external_registrar_gets_the_validation_records_as_an_output" {
  variables {
    route53_zone_id = null
  }

  assert {
    condition     = length(aws_route53_record.certificate_validation) == 0 && length(aws_route53_record.redirect_alias) == 0
    error_message = "With no hosted zone id the module must not try to write DNS records."
  }

  assert {
    condition     = length(output.certificate_validation_records) == 2
    error_message = "The validation records must be an output, because at an external registrar they are typed in by hand."
  }
}

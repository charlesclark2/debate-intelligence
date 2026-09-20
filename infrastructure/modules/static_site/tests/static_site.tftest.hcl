# Offline tests for the static_site module.
#
# `mock_provider "aws"` means no credentials, no network and no AWS account: Terraform generates
# the values a real provider would return, and everything these runs assert on is either
# configured in the module or mocked here on purpose. That is what lets them run in pre-commit and
# in CI while every plan and apply stays an operator step
# (docs/process/working-agreements.md section 1).
#
#   terraform -chdir=infrastructure/modules/static_site init -backend=false
#   terraform -chdir=infrastructure/modules/static_site test
#
# What is worth asserting here is the set of properties the module exists to guarantee and that a
# later edit could quietly drop: the bucket is private and reachable only by its own distribution,
# viewers are on HTTPS, the security headers are sent, the preview is not indexable, nothing logs
# visitor IPs, and the publisher credential can do nothing but publish.

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      name = "us-east-1"
    }
  }

  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "111122223333"
    }
  }

  mock_data "aws_cloudfront_cache_policy" {
    defaults = {
      id = "mock-caching-optimized"
    }
  }

  mock_data "aws_identitystore_user" {
    defaults = {
      # The provider validates the shape of an identity store user id.
      user_id = "a1b2c3d4e5-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::debate-mock-site"
    }
  }

  # The provider validates that a function association really is an ARN, so this one has to look
  # like an ARN rather than a generated mock string.
  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::111122223333:function/mock-site-request"
    }
  }

  mock_resource "aws_ssoadmin_permission_set" {
    defaults = {
      arn = "arn:aws:sso:::permissionSet/ssoins-mock/ps-mock"
    }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::111122223333:distribution/EMOCKDISTRIBUTION"
      domain_name    = "dmockdistribution.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  # A superset of the names any run below asks for. ACM returns one validation record per name on
  # the certificate; the module looks up only the names it was given, so extra entries here are
  # harmless and one mock serves every run.
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
        {
          domain_name           = "dev.wfbdebate.com"
          resource_record_name  = "_mock3.dev.wfbdebate.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock3.acm-validations.aws."
        },
      ]
    }
  }
}

variables {
  name_prefix   = "debate-dev-site"
  environment   = "dev"
  bucket_suffix = "a7508de8"
}

# ---------------------------------------------------------------------------------------------
# The default shape: no team domain yet, so the site runs on its CloudFront domain.
# ---------------------------------------------------------------------------------------------

run "bucket_is_private_and_encrypted" {
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.site.block_public_acls,
      aws_s3_bucket_public_access_block.site.block_public_policy,
      aws_s3_bucket_public_access_block.site.ignore_public_acls,
      aws_s3_bucket_public_access_block.site.restrict_public_buckets,
    ])
    error_message = "All four block-public-access flags must be on: three of the four still leave a way to publish the bucket."
  }

  assert {
    condition     = aws_s3_bucket_ownership_controls.site.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "Object ownership must be BucketOwnerEnforced, so no ACL can grant access to site objects."
  }

  assert {
    # `rule` is a set here, so it has no addressable index.
    condition = alltrue([
      for rule in aws_s3_bucket_server_side_encryption_configuration.site.rule :
      rule.apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    ])
    error_message = "The site bucket must have SSE-S3 default encryption."
  }

  assert {
    condition     = aws_s3_bucket_versioning.site.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning must be on: deploys are `aws s3 sync --delete`."
  }

  assert {
    condition     = aws_s3_bucket.site.bucket == "debate-dev-site-a7508de8"
    error_message = "The bucket name must be <name_prefix>-<bucket_suffix>, as the runbook and the deploy script assume."
  }
}

run "bucket_policy_grants_only_this_distribution" {
  assert {
    condition     = length(jsondecode(aws_s3_bucket_policy.site.policy).Statement) == 2
    error_message = "The bucket policy should hold exactly two statements: the CloudFront read grant and the TLS-only deny."
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_s3_bucket_policy.site.policy).Statement :
      statement if statement.Effect == "Allow"
    ]) == 1
    error_message = "The bucket policy must contain exactly one Allow. A second one is how a private bucket stops being private."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_s3_bucket_policy.site.policy).Statement :
      (
        statement.Principal.Service == "cloudfront.amazonaws.com" &&
        statement.Action == "s3:GetObject" &&
        statement.Condition.StringEquals["AWS:SourceArn"] == aws_cloudfront_distribution.site.arn
      ) if statement.Effect == "Allow"
    ])
    error_message = "The only Allow must be s3:GetObject for cloudfront.amazonaws.com, conditioned on this distribution's ARN (origin access control, not a public grant)."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_s3_bucket_policy.site.policy).Statement :
      statement.Condition.Bool["aws:SecureTransport"] == "false" if statement.Effect == "Deny"
    ])
    error_message = "The bucket must deny non-TLS requests."
  }

  assert {
    condition     = aws_cloudfront_origin_access_control.site.signing_protocol == "sigv4"
    error_message = "Origin access must be an origin access control signing with SigV4, not a legacy origin access identity."
  }
}

run "viewers_are_on_https_and_nothing_is_logged" {
  assert {
    condition     = aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "http:// must redirect to https://."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.site.logging_config) == 0
    error_message = "CloudFront access logging must stay off (ADR-0012 decision 8): no per-request record of visitor IP addresses."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.default_cache_behavior[0].compress
    error_message = "Responses must be compressed."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.price_class == "PriceClass_100"
    error_message = "The default price class should be the cheapest one that covers North America and Europe."
  }

  assert {
    condition = length([
      for response in aws_cloudfront_distribution.site.custom_error_response :
      response if response.response_page_path == "/404.html"
    ]) == 2
    error_message = "Both 404 and the 403 a private bucket returns for a missing key must be answered with the site's own 404 page."
  }
}

run "security_headers_are_sent" {
  assert {
    condition     = aws_cloudfront_response_headers_policy.site.security_headers_config[0].strict_transport_security[0].access_control_max_age_sec >= 31536000
    error_message = "HSTS must be at least a year."
  }

  assert {
    condition     = aws_cloudfront_response_headers_policy.site.security_headers_config[0].strict_transport_security[0].include_subdomains
    error_message = "HSTS must cover subdomains: the V2 app will live on one."
  }

  assert {
    condition     = aws_cloudfront_response_headers_policy.site.security_headers_config[0].content_type_options[0].override
    error_message = "X-Content-Type-Options: nosniff must be sent and must override the origin."
  }

  assert {
    condition     = strcontains(aws_cloudfront_response_headers_policy.site.security_headers_config[0].content_security_policy[0].content_security_policy, "frame-ancestors 'none'")
    error_message = "The Content-Security-Policy must forbid framing."
  }

  assert {
    condition     = strcontains(aws_cloudfront_response_headers_policy.site.security_headers_config[0].content_security_policy[0].content_security_policy, "default-src 'self'")
    error_message = "The Content-Security-Policy must default to this origin only."
  }

  assert {
    condition     = aws_cloudfront_response_headers_policy.site.security_headers_config[0].frame_options[0].frame_option == "DENY"
    error_message = "X-Frame-Options: DENY must be sent alongside the CSP for older clients."
  }

  assert {
    condition     = aws_cloudfront_response_headers_policy.site.security_headers_config[0].referrer_policy[0].referrer_policy == "strict-origin-when-cross-origin"
    error_message = "A Referrer-Policy must be set."
  }

  assert {
    condition = length([
      for item in aws_cloudfront_response_headers_policy.site.custom_headers_config[0].items :
      item if item.header == "Permissions-Policy"
    ]) == 1
    error_message = "A Permissions-Policy must be sent."
  }

  assert {
    condition = length([
      for item in aws_cloudfront_response_headers_policy.site.custom_headers_config[0].items :
      item if item.header == "X-Robots-Tag"
    ]) == 0
    error_message = "X-Robots-Tag must not be sent unless noindex is set: prod has to be indexable."
  }
}

run "no_domain_means_the_cloudfront_domain_and_no_certificate" {
  assert {
    condition     = length(aws_acm_certificate.site) == 0
    error_message = "No certificate should be requested until domain_names is set, so a first apply can go out before the domain is ready."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].cloudfront_default_certificate
    error_message = "Without a domain the distribution must serve the CloudFront default certificate."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.site.aliases) == 0
    error_message = "A distribution with no domain names must claim no aliases."
  }

  assert {
    condition     = length(aws_route53_record.certificate_validation) == 0 && length(aws_route53_record.site_alias) == 0
    error_message = "No DNS records should be written when there is no domain."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.site_request.code, "var CANONICAL_HOST = '';")
    error_message = "With no domain the canonical-host redirect must be switched off, or the CloudFront domain would redirect to nothing."
  }

  assert {
    condition     = output.site_url == "https://dmockdistribution.cloudfront.net/"
    error_message = "site_url must fall back to the CloudFront domain."
  }
}

run "the_index_rewrite_is_published_at_the_edge" {
  assert {
    # `function_association` is a set, so it is matched rather than indexed.
    condition = length([
      for association in aws_cloudfront_distribution.site.default_cache_behavior[0].function_association :
      association
      if association.event_type == "viewer-request" && association.function_arn == aws_cloudfront_function.site_request.arn
    ]) == 1
    error_message = "The URI rewrite has to run on viewer request."
  }

  assert {
    condition     = aws_cloudfront_function.site_request.publish
    error_message = "The function must be published, not left in DEVELOPMENT."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.site_request.code, "index.html")
    error_message = "The function must map a page URL to its index.html object; without it every page below the root 404s."
  }
}

# ---------------------------------------------------------------------------------------------
# Prod: the team domain, with www redirecting to the apex.
# ---------------------------------------------------------------------------------------------

run "prod_serves_the_team_domain_and_redirects_www" {
  variables {
    name_prefix           = "debate-prod-site"
    environment           = "prod"
    domain_names          = ["wfbdebate.com", "www.wfbdebate.com"]
    canonical_domain_name = "wfbdebate.com"
    route53_zone_id       = "Z0MOCKCOMZONE"
  }

  assert {
    condition     = aws_cloudfront_distribution.site.aliases == toset(["wfbdebate.com", "www.wfbdebate.com"])
    error_message = "The distribution must answer on both the apex and www, or the www redirect can never be served."
  }

  assert {
    condition     = aws_acm_certificate.site[0].domain_name == "wfbdebate.com"
    error_message = "The certificate's common name must be the canonical host."
  }

  assert {
    condition     = aws_acm_certificate.site[0].subject_alternative_names == toset(["www.wfbdebate.com"])
    error_message = "Every non-canonical name must be a subject alternative name on the same certificate."
  }

  assert {
    condition     = aws_acm_certificate.site[0].validation_method == "DNS"
    error_message = "The certificate must be DNS validated."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].minimum_protocol_version == "TLSv1.2_2021"
    error_message = "With a certificate of our own the TLS floor must be 1.2 (task spec: forbidden below 1.2)."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].ssl_support_method == "sni-only"
    error_message = "A dedicated-IP certificate costs hundreds of dollars a month; SNI is what this site uses."
  }

  assert {
    condition     = !aws_cloudfront_distribution.site.viewer_certificate[0].cloudfront_default_certificate
    error_message = "With a domain configured the distribution must stop using the CloudFront default certificate."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.site_request.code, "var CANONICAL_HOST = 'wfbdebate.com';")
    error_message = "The viewer function must know the canonical host."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.site_request.code, "statusCode: 301")
    error_message = "A non-canonical host must be answered with a permanent redirect, not a rewrite."
  }

  assert {
    condition     = output.site_url == "https://wfbdebate.com/"
    error_message = "site_url must be the canonical host once a domain is configured."
  }

  assert {
    condition     = length(aws_route53_record.certificate_validation) == 2
    error_message = "With the zone in Route 53 the module must write one validation record per name."
  }

  assert {
    condition     = length(aws_route53_record.site_alias) == 4
    error_message = "Each name needs an A and an AAAA alias record; the distribution is IPv6 enabled."
  }

  assert {
    condition = alltrue([
      for record in aws_route53_record.site_alias :
      record.alias[0].name == aws_cloudfront_distribution.site.domain_name
    ])
    error_message = "Every alias record must point at this distribution."
  }

  assert {
    condition     = length(aws_acm_certificate_validation.site) == 1
    error_message = "With DNS in Route 53 the apply must wait for ACM to issue, so CloudFront is never handed a pending certificate."
  }
}

run "an_external_registrar_gets_the_validation_records_as_an_output" {
  variables {
    name_prefix           = "debate-prod-site"
    environment           = "prod"
    domain_names          = ["wfbdebate.com", "www.wfbdebate.com"]
    canonical_domain_name = "wfbdebate.com"
    route53_zone_id       = null
  }

  assert {
    condition     = length(aws_route53_record.certificate_validation) == 0 && length(aws_route53_record.site_alias) == 0
    error_message = "With no hosted zone id the module must not try to write DNS records."
  }

  assert {
    condition     = length(aws_acm_certificate_validation.site) == 0
    error_message = "Without Route 53 there is nothing for Terraform to wait on; the operator adds the records and re-applies."
  }

  assert {
    condition     = length(output.certificate_validation_records) == 3
    error_message = "The validation records must be an output, because at an external registrar they are typed in by hand."
  }

  assert {
    condition = alltrue([
      for record in output.certificate_validation_records :
      record.type == "CNAME" && record.name != "" && record.value != ""
    ])
    error_message = "Each validation record must carry a usable name, type and value."
  }
}

# ---------------------------------------------------------------------------------------------
# Dev: the preview host, which must never be indexed.
# ---------------------------------------------------------------------------------------------

run "dev_preview_is_not_indexable" {
  variables {
    domain_names    = ["dev.wfbdebate.com"]
    route53_zone_id = "Z0MOCKCOMZONE"
    noindex         = true
  }

  assert {
    condition = length([
      for item in aws_cloudfront_response_headers_policy.site.custom_headers_config[0].items :
      item if item.header == "X-Robots-Tag" && item.value == "noindex, nofollow" && item.override
    ]) == 1
    error_message = "With noindex set the distribution must send X-Robots-Tag: noindex, nofollow, overriding whatever the object carries."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.site_request.code, "var CANONICAL_HOST = 'dev.wfbdebate.com';")
    error_message = "A single-name environment is its own canonical host, so it must not redirect to itself."
  }

  assert {
    condition     = length(aws_route53_record.site_alias) == 2
    error_message = "The preview host needs its own A and AAAA alias records."
  }

  assert {
    condition     = output.site_url == "https://dev.wfbdebate.com/"
    error_message = "The dev preview URL must be the preview host."
  }
}

# ---------------------------------------------------------------------------------------------
# The credential the site is published with.
# ---------------------------------------------------------------------------------------------

run "publisher_permission_set_can_publish_and_nothing_else" {
  variables {
    identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
    identity_store_id            = "d-mock000000"
    publisher_user_names         = ["maintainer"]
  }

  assert {
    condition     = aws_ssoadmin_permission_set.site_publisher[0].name == "DebateDevSitePublisher"
    error_message = "The permission set must be named for its environment, so dev and prod publishers can never be confused."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.site_publisher[0].inline_policy).Statement :
      statement.Action
      ])) == toset([
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "cloudfront:CreateInvalidation",
    ])
    error_message = "The publisher may do exactly five things: list, read, write and delete its own site objects, and invalidate its own distribution."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.site_publisher[0].inline_policy).Statement :
      statement.Effect == "Allow"
    ])
    error_message = "The publisher policy is an allow-list; a Deny in it would mean something broader had been granted."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.site_publisher[0].inline_policy).Statement :
      alltrue([
        for resource in tolist(flatten([statement.Resource])) :
        startswith(resource, aws_s3_bucket.site.arn) || resource == aws_cloudfront_distribution.site.arn
      ])
    ])
    error_message = "Every resource in the publisher policy must be this environment's own bucket or its own distribution."
  }

  assert {
    condition     = length(aws_ssoadmin_account_assignment.site_publishers) == 1
    error_message = "The named publisher must actually be assigned the permission set, or the SSO profile has nothing to assume."
  }
}

run "no_identity_center_instance_means_no_permission_set" {
  assert {
    condition     = length(aws_ssoadmin_permission_set.site_publisher) == 0
    error_message = "The permission set is optional: the module has to be usable without an Identity Center instance."
  }
}

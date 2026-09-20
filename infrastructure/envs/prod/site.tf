# The public team website for this environment (ADR-0012, spec v1-e36-t02-site-hosting).
#
# This file is character-for-character the same in envs/dev and envs/prod, like every other file
# in these roots except terraform.tfvars and backend.tf. dev and prod differ only in what their
# tfvars say: dev gets the preview host dev.wfbdebate.org and noindex, prod gets wfbdebate.org
# with www redirecting to it plus the .com redirect. Copying a resource block between the two
# roots instead of putting it in infrastructure/modules is what this layout exists to prevent —
# see infrastructure/README.md.
#
# The domain names are variables with empty defaults, so `terraform apply -var 'site_domain_names=[]'`
# brings the site up on its *.cloudfront.net domain with no certificate at all. That is the
# escape hatch for applying while DNS is still settling: the site is deployable and reviewable
# before the certificate is issued, and adding the names later is one more apply.
#
# Applies are operator-run (docs/runbooks/team-website.md). There are no GitHub OIDC roles until
# v2-e10-t03, so CI never runs plan or apply against this root, and neither does an agent session.

# The Identity Center instance that owns the SitePublisher permission set. Read, never managed:
# it predates this project and belongs to the account, not to the website
# (infrastructure/bootstrap/organization).
data "aws_ssoadmin_instances" "current" {}

# The hosted zones came with the domain registration. They are read, never created and never
# destroyed: a `terraform destroy` that took a hosted zone with it would strand the domain (task
# spec: forbidden).
data "aws_route53_zone" "site" {
  count = local.manage_site_dns ? 1 : 0

  name         = var.site_dns_zone_name
  private_zone = false
}

data "aws_route53_zone" "site_redirect" {
  count = local.manage_redirect_dns ? 1 : 0

  name         = var.redirect_dns_zone_name
  private_zone = false
}

locals {
  manage_site_dns     = length(var.site_domain_names) > 0 && var.site_dns_zone_name != null
  manage_redirect_dns = length(var.redirect_domain_names) > 0 && var.redirect_dns_zone_name != null

  identity_center_instance_arn = tolist(data.aws_ssoadmin_instances.current.arns)[0]
  identity_store_id            = tolist(data.aws_ssoadmin_instances.current.identity_store_ids)[0]
}

module "site" {
  source = "../../modules/static_site"

  name_prefix   = "${var.name_prefix}-${var.environment}-site"
  environment   = var.environment
  bucket_suffix = var.site_bucket_suffix

  domain_names          = var.site_domain_names
  canonical_domain_name = var.site_canonical_domain_name
  route53_zone_id       = one(data.aws_route53_zone.site[*].zone_id)
  noindex               = var.site_noindex

  identity_center_instance_arn = local.identity_center_instance_arn
  identity_store_id            = local.identity_store_id
  publisher_user_names         = var.site_publisher_user_names
}

# Only prod has redirected domains; dev's redirect_domain_names is empty, so this module is not
# instantiated there. The count is what keeps one file correct in both roots.
module "site_domain_redirect" {
  source = "../../modules/domain_redirect"

  count = length(var.redirect_domain_names) > 0 ? 1 : 0

  name_prefix     = "${var.name_prefix}-${var.environment}-site-redirect"
  domain_names    = var.redirect_domain_names
  target_host     = module.site.canonical_host
  route53_zone_id = one(data.aws_route53_zone.site_redirect[*].zone_id)
}

# A redirect to nowhere is worse than no redirect: it would send every visitor who typed the .com
# name to a host that does not answer. The site has a canonical host only once site_domain_names
# is set, so the two have to be configured together.
check "redirect_has_somewhere_to_point" {
  assert {
    condition = length(var.redirect_domain_names) == 0 || length(var.site_domain_names) > 0
    error_message = join(" ", [
      "redirect_domain_names is set but site_domain_names is empty, so there is no canonical host",
      "to redirect to. Set both, or neither, in terraform.tfvars.",
    ])
  }
}

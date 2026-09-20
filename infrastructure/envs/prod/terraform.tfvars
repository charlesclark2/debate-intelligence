# Committed. The only per-environment difference between envs/dev and envs/prod besides
# backend.tf. The maintainer's email is not here; it comes from a gitignored owner.auto.tfvars
# beside this file, or from TF_VAR_owner.

environment = "prod"
aws_region  = "us-east-1"

# The website (v1-e36-t02-site-hosting, ADR-0012). wfbdebate.com is what parents see and what goes
# on a flyer; www.wfbdebate.com answers too, and 301s to the apex, so there is one address in
# search results. The zone came with the registration and is read, not created.
#
# wfbdebate.org was the first choice and its registration failed three times on 2026-09-20, each
# in under a second, with no reason given; an AWS Support case is open. The team website is due
# before a parent information session on October 1, so the canonical name moved to the domain that
# actually exists rather than waiting.
site_domain_names          = ["wfbdebate.com", "www.wfbdebate.com"]
site_canonical_domain_name = "wfbdebate.com"
site_dns_zone_name         = "wfbdebate.com"
site_noindex               = false

# Empty until a second registrable domain is in hand. If wfbdebate.org is ever issued, this is
# where it goes — the .org names 301 to their .com equivalents through modules/domain_redirect,
# which is built and tested and simply not instantiated yet:
#
#   redirect_domain_names  = ["wfbdebate.org", "www.wfbdebate.org"]
#   redirect_dns_zone_name = "wfbdebate.org"
redirect_domain_names = []

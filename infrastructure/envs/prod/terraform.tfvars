# Committed. The only per-environment difference between envs/dev and envs/prod besides
# backend.tf. The maintainer's email is not here; it comes from a gitignored owner.auto.tfvars
# beside this file, or from TF_VAR_owner.

environment = "prod"
aws_region  = "us-east-1"

# The website (v1-e36-t02-site-hosting, ADR-0012). wfbdebate.org is what parents see and what
# goes on a flyer; www.wfbdebate.org answers too, and 301s to the apex, so there is one address
# in search results. Both zones came with the registration and are read, not created.
site_domain_names          = ["wfbdebate.org", "www.wfbdebate.org"]
site_canonical_domain_name = "wfbdebate.org"
site_dns_zone_name         = "wfbdebate.org"
site_noindex               = false

# The .com spelling exists so that nobody who mistypes lands on a stranger's site. It holds no
# content: every request 301s to the same path on wfbdebate.org.
redirect_domain_names  = ["wfbdebate.com", "www.wfbdebate.com"]
redirect_dns_zone_name = "wfbdebate.com"

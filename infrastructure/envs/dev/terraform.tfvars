# Committed. The only per-environment difference between envs/dev and envs/prod besides
# backend.tf. The maintainer's email is not here; it comes from a gitignored owner.auto.tfvars
# beside this file, or from TF_VAR_owner.

environment = "dev"
aws_region  = "us-east-1"

# The website (v1-e36-t02-site-hosting, ADR-0012). dev is the preview: one host, and never
# indexable. The zone is the .org zone that came with the registration; it is read, not created.
site_domain_names  = ["dev.wfbdebate.org"]
site_dns_zone_name = "wfbdebate.org"
site_noindex       = true

# No redirected domains in dev: wfbdebate.com points at prod.
redirect_domain_names = []

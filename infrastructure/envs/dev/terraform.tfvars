# Committed. The only per-environment difference between envs/dev and envs/prod besides
# backend.tf. The maintainer's email is not here; it comes from a gitignored owner.auto.tfvars
# beside this file, or from TF_VAR_owner.

environment = "dev"
aws_region  = "us-east-1"

# The website (v1-e36-t02-site-hosting, ADR-0012). dev is the preview: one host, and never
# indexable. The zone is the .com zone that came with the registration; it is read, not created.
#
# wfbdebate.com and not wfbdebate.org: the .org registration failed three times on 2026-09-20 and
# an AWS Support case is open. If it is ever issued, the .org names become redirects to these,
# through redirect_domain_names in envs/prod — the canonical name does not move again.
site_domain_names  = ["dev.wfbdebate.com"]
site_dns_zone_name = "wfbdebate.com"
site_noindex       = true

# No redirected domains in dev: a second registrable domain points at prod, not at the preview.
redirect_domain_names = []

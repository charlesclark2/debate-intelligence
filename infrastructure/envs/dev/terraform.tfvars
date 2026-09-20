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

# The evidence store (v1-e29-t03-evidence-buckets, ADR-0003). dev holds synthetic and sample data
# only, unless the backfill task (v1-e30-t06) says the operator loads the real corpus here for
# validation, so a superseded version is worth a month rather than a year. At 30 days the
# Standard-IA transition drops out on purpose: S3 rejects a version that expires on the day it
# would move, and Standard-IA bills a 30-day minimum for a version that is about to be deleted.
evidence_noncurrent_version_retention_days = 30

# The student evidence search pilot for this environment (ADR-0019, spec
# v1-e39-t04-pilot-infrastructure): one function behind its own CloudFront distribution, the
# Cognito user pool for the accounts the coach creates, the append-only audit log and the pilot's
# own budget.
#
# This file is character-for-character the same in envs/dev and envs/prod, like every other file
# in these roots except terraform.tfvars and backend.tf. dev and prod differ only in what their
# tfvars say: the pilot host (tub.dev.wfbdebate.com, tub.wfbdebate.com). The module derives the
# rest from the environment: deletion protection on the prod pool, noindex on dev.
#
# The Identity Center instance and identity store come from the data source and locals in site.tf;
# the evidence bucket and its key from evidence_store.tf.
#
# Applies are operator-run (docs/runbooks/evidence-search.md). The first apply in an environment
# targets the image repository alone, because the function can only be created once the first
# deploy has pushed an image. There are no GitHub OIDC roles until v2-e10-t03, so CI never runs
# plan or apply against this root, and neither does an agent session.

# The zone came with the domain registration. Read, never created and never destroyed, as site.tf
# reads it.
data "aws_route53_zone" "evidence_search" {
  name         = var.evidence_search_dns_zone_name
  private_zone = false
}

module "evidence_search" {
  source = "../../modules/evidence_search"

  name_prefix = "${var.name_prefix}-${var.environment}-tub"
  environment = var.environment
  pilot_host  = var.evidence_search_host

  route53_zone_id = data.aws_route53_zone.evidence_search.zone_id

  evidence_bucket_arn  = module.evidence_store.bucket_arn
  evidence_kms_key_arn = module.evidence_store.kms_key_arn

  # The maintainer's address from the gitignored owner.auto.tfvars: the list set there, or the
  # Owner address when it is not set. Never a committed address.
  budget_notification_emails = length(var.evidence_search_budget_emails) > 0 ? var.evidence_search_budget_emails : [var.owner]

  identity_center_instance_arn = local.identity_center_instance_arn
  identity_store_id            = local.identity_store_id

  deployer_user_names = var.evidence_search_deployer_user_names
  accounts_user_names = var.evidence_search_accounts_user_names
}

# As for the evidence store: a permission set nobody is assigned is easy to end up with, because
# the user names live in a gitignored file, and invisible until a deploy fails with AccessDenied.
check "someone_can_deploy_the_pilot" {
  assert {
    condition = length(var.evidence_search_deployer_user_names) > 0
    error_message = join(" ", [
      "evidence_search_deployer_user_names is empty, so the TubDeployer permission set for",
      "${var.environment} would exist with nobody assigned to it and no way to deploy the pilot.",
      "Set it in the gitignored owner.auto.tfvars beside this file (see owner.auto.tfvars.example).",
    ])
  }
}

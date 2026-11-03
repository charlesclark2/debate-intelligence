# The weekly caselist run in the cloud for this environment (ADR-0020, epic E40): the credentials
# key, the Tabroom password and caselist token secrets, the login and run roles, the coach's
# CaselistSecretWriter permission set (v1-e40-t02); the run's network, cluster, image repository
# and CaselistRunDeployer permission set (v1-e40-t03); and, once caselist_image_digest names a
# pushed image, the login and run task definitions with their Wednesday schedules, the run's
# disabled until the cutover (v1-e40-t06); and the alerts that email the coach (v1-e40-t05).
#
# This file is character-for-character the same in envs/dev and envs/prod, like every other file
# in these roots except terraform.tfvars and backend.tf. The two differ only in the names the
# module derives from the environment.
#
# The Identity Center instance and identity store come from the data source and locals in site.tf.
#
# Applies are operator-run (docs/runbooks/caselist-cloud-credentials.md and
# docs/runbooks/caselist-cloud-run.md): the credentials first ("apply A"), the run's network,
# cluster, repository and deployer next, with caselist_image_digest unset, then, after the first
# image push, the two tasks and their schedules ("apply B"). There are no GitHub OIDC roles until
# v2-e10-t03, so CI never runs plan or apply against this root, and neither does an agent session.

module "caselist_run" {
  source = "../../modules/caselist_run"

  name_prefix = "${var.name_prefix}-${var.environment}-caselist"
  environment = var.environment

  identity_center_instance_arn = local.identity_center_instance_arn
  identity_store_id            = local.identity_store_id

  credential_writer_user_names = var.caselist_credential_writer_user_names
  deployer_user_names          = var.caselist_run_deployer_user_names

  # The run role holds the everyday evidence permissions, the EvidenceOperator set's own document.
  evidence_bucket_arn  = module.evidence_store.bucket_arn
  evidence_key_arn     = module.evidence_store.kms_key_arn
  evidence_policy_json = module.evidence_store.operator_policy_json

  image_digest           = var.caselist_image_digest
  login_schedule_enabled = var.caselist_login_schedule_enabled
  run_schedule_enabled   = var.caselist_run_schedule_enabled

  # The alerts (v1-e40-t05, ADR-0020 (6)): to the address the pilot's budget alarm writes to, the
  # Owner address unless owner.auto.tfvars names another; the late-run alarm silent until the
  # cutover's first recorded run.
  alert_email                    = length(var.evidence_search_budget_emails) > 0 ? var.evidence_search_budget_emails[0] : var.owner
  late_run_alarm_actions_enabled = var.caselist_run_late_alarm_actions_enabled
}

# A writer nobody is assigned is easy to end up with, because the user name lives in a gitignored
# file, and invisible until `caselist auth set-password` fails with AccessDenied.
check "someone_can_write_the_tabroom_password" {
  assert {
    condition = length(var.caselist_credential_writer_user_names) > 0
    error_message = join(" ", [
      "caselist_credential_writer_user_names is empty, so the CaselistSecretWriter permission set",
      "for ${var.environment} would exist with nobody assigned to it and no way to write the Tabroom",
      "password. Set it in the gitignored owner.auto.tfvars beside this file (see owner.auto.tfvars.example).",
    ])
  }
}

# The same for the deployer: without a name in owner.auto.tfvars the permission set exists and
# scripts/caselist_run_deploy.sh has nobody to run as.
check "someone_can_deploy_the_caselist_run" {
  assert {
    condition = length(var.caselist_run_deployer_user_names) > 0
    error_message = join(" ", [
      "caselist_run_deployer_user_names is empty, so the CaselistRunDeployer permission set for",
      "${var.environment} would exist with nobody assigned to it and no way to push the run's image.",
      "Set it in the gitignored owner.auto.tfvars beside this file (see owner.auto.tfvars.example).",
    ])
  }
}

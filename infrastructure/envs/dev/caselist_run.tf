# The weekly caselist run in the cloud for this environment (ADR-0020, epic E40): the credentials
# key, the Tabroom password and caselist token secrets, the login and run roles, the coach's
# CaselistSecretWriter permission set (v1-e40-t02), and, once caselist_login_task names the run's
# network and image (v1-e40-t03), the scheduled login.
#
# This file is character-for-character the same in envs/dev and envs/prod, like every other file
# in these roots except terraform.tfvars and backend.tf. The two differ only in the names the
# module derives from the environment.
#
# The Identity Center instance and identity store come from the data source and locals in site.tf.
#
# Applies are operator-run (docs/runbooks/caselist-cloud-credentials.md): the credentials first,
# with caselist_login_task unset ("apply A"), then the login task after v1-e40-t03's first image
# push ("apply B"). There are no GitHub OIDC roles until v2-e10-t03, so CI never runs plan or apply
# against this root, and neither does an agent session.

module "caselist_run" {
  source = "../../modules/caselist_run"

  name_prefix = "${var.name_prefix}-${var.environment}-caselist"
  environment = var.environment

  identity_center_instance_arn = local.identity_center_instance_arn
  identity_store_id            = local.identity_store_id

  credential_writer_user_names = var.caselist_credential_writer_user_names

  login_task             = var.caselist_login_task
  login_schedule_enabled = var.caselist_login_schedule_enabled
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

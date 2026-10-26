# The permission set this environment's model calls are made with, Debate<Env>BedrockInvoker, and
# its one account assignment (task v1-e05-t08-bedrock-invoke-access): bedrock:InvokeModel on the
# inference profiles and models the routing files name, read from config/ itself, and nothing else.
# Its SSO profile, debate-<env>-bedrock, is what `models.aws_profile` names in
# config/profiles/<env>.toml, and what the Bedrock client is built from.
#
# This file is character-for-character the same in envs/dev and envs/prod, like every other file
# in these roots except terraform.tfvars and backend.tf.
#
# Both roots read both routing files. There is one account (ADR-0010), so dev's set reaching a model
# only prod routes to separates nothing, and the first call on each Claude route
# (docs/runbooks/bedrock-access.md) is made after the dev apply, with dev's profile, before prod is
# applied. Every model call still goes through the router, whose routing file is the environment's
# own and whose daily budget is the environment's (models.budget_usd_daily).
#
# The Identity Center instance and identity store come from the data source and locals in site.tf.
#
# Applies are operator-run (docs/runbooks/bedrock-access.md), and the PM reads each plan first.
# There are no GitHub OIDC roles until v2-e10-t03, so CI never runs plan or apply against this
# root, and neither does an agent session.

module "bedrock_access" {
  source = "../../modules/bedrock_access"

  name_prefix = "${var.name_prefix}-${var.environment}-bedrock"
  environment = var.environment

  routing_files = [
    "${path.root}/../../../config/model_routing.dev.yaml",
    "${path.root}/../../../config/model_routing.prod.yaml",
  ]

  identity_center_instance_arn = local.identity_center_instance_arn
  identity_store_id            = local.identity_store_id

  invoker_user_names = var.bedrock_invoker_user_names
}

# A set nobody is assigned is easy to end up with, because the user name lives in a gitignored
# file, and invisible until the first model call is refused. A `check` warns at plan time rather
# than failing: a root with nobody assigned is still applyable.
check "someone_can_call_the_routed_models" {
  assert {
    condition = length(var.bedrock_invoker_user_names) > 0
    error_message = join(" ", [
      "bedrock_invoker_user_names is empty, so the BedrockInvoker permission set for",
      "${var.environment} would exist with nobody assigned to it and no way to call a model.",
      "Set it in the gitignored owner.auto.tfvars beside this file (see owner.auto.tfvars.example).",
    ])
  }
}

# Offline tests for the bedrock_access module: the permission set that may call the routed Bedrock
# models (task v1-e05-t08-bedrock-invoke-access).
#
# `mock_provider "aws"` means no credentials, no network and no AWS account. The routing files are
# the real ones in config/, read the way the environment roots read them, so these runs hold the
# grant to what the committed routes name.
#
#   terraform -chdir=infrastructure/modules/bedrock_access init -backend=false
#   terraform -chdir=infrastructure/modules/bedrock_access test
#
# What these runs hold the module to (ac1):
#
#   * one permission set per environment, Debate<Env>BedrockInvoker, assigned to the users named;
#   * bedrock:InvokeModel and no other action, Allow only, in every statement;
#   * on exactly the resources the routing files name: the two us. inference profiles in us-east-1
#     (Haiku 4.5 and Sonnet 4.6, which dev and, since v1-e05-t20, prod route to while the account's
#     5.5 quotas are held at zero), the two Claude models behind them in us-east-1, us-east-2 and
#     us-west-2, and the Titan embedding and Cohere rerank models in us-east-1. Ten ARNs, written
#     out by hand below (working agreement 6), each once, and none of the 5.5 models;
#   * the Claude models only through the profiles: their statement carries
#     bedrock:InferenceProfileArn, equal to the two profiles' ARNs, and no other statement does;
#   * the same at plan time, for both environments: the policy is known before anything is applied,
#     so a plan shows exactly what an apply would grant (v1-e05-t20).
#
# The account id and user name below are invented.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "111122223333"
    }
  }

  mock_data "aws_identitystore_user" {
    defaults = {
      user_id = "a1b2c3d4e5-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    }
  }

  mock_resource "aws_ssoadmin_permission_set" {
    defaults = {
      arn = "arn:aws:sso:::permissionSet/ssoins-mock/ps-mockinvoker"
    }
  }
}

variables {
  name_prefix   = "debate-dev-bedrock"
  environment   = "dev"
  routing_files = ["../../../config/model_routing.dev.yaml", "../../../config/model_routing.prod.yaml"]

  identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
  identity_store_id            = "d-mock000000"
  invoker_user_names           = ["mock-maintainer"]
}

# ---------------------------------------------------------------------------------------------
# The grant
# ---------------------------------------------------------------------------------------------

run "the_set_may_invoke_and_do_nothing_else" {
  command = apply

  assert {
    condition     = jsondecode(output.policy_json).Version == "2012-10-17" && length(jsondecode(output.policy_json).Statement) > 0
    error_message = "The policy is a 2012-10-17 document with at least one statement."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(output.policy_json).Statement :
      jsonencode(flatten([statement.Action])) == jsonencode(["bedrock:InvokeModel"])
    ])
    error_message = "Every statement's action is bedrock:InvokeModel and nothing else: Converse is authorised by it, and nothing here streams (task spec: forbidden)."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(output.policy_json).Statement :
      statement.Effect == "Allow" && length(setsubtract(keys(statement), ["Sid", "Effect", "Action", "Resource", "Condition"])) == 0
    ])
    error_message = "Every statement allows, with Action and Resource: no NotAction or NotResource, which would grant everything a list leaves out."
  }

  assert {
    condition = jsonencode(sort(flatten([
      for statement in jsondecode(output.policy_json).Statement : flatten([statement.Resource])
      ]))) == jsonencode(sort([
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
      "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0",
    ]))
    error_message = "The resources are exactly the ten the routing files name, each once: no wildcard, no 5.5 model, no other model, region or profile."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(output.policy_json).Statement :
      !anytrue([for resource in flatten([statement.Resource]) : strcontains(resource, ":foundation-model/anthropic.")])
      || (
        jsonencode(keys(try(statement.Condition, {}))) == jsonencode(["StringEquals"])
        && jsonencode(keys(try(statement.Condition.StringEquals, {}))) == jsonencode(["bedrock:InferenceProfileArn"])
        && jsonencode(sort(flatten([try(statement.Condition.StringEquals["bedrock:InferenceProfileArn"], [])]))) == jsonencode(sort([
          "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
          "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-sonnet-4-6",
        ]))
      )
    ])
    error_message = "A statement naming a Claude model carries bedrock:InferenceProfileArn, StringEquals the two profiles and nothing else: the models are called through the profiles only."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(output.policy_json).Statement :
      alltrue([for resource in flatten([statement.Resource]) : strcontains(resource, ":foundation-model/anthropic.")])
      || !anytrue([for resource in flatten([statement.Resource]) : strcontains(resource, ":foundation-model/anthropic.")])
    ])
    error_message = "No statement mixes a Claude model with a profile or a scoring model, so the profile condition reaches the Claude models and nothing else."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(output.policy_json).Statement :
      anytrue([for resource in flatten([statement.Resource]) : strcontains(resource, ":foundation-model/anthropic.")])
      || try(statement.Condition, null) == null
    ])
    error_message = "The profiles and the scoring models carry no condition: they are what a call names, so a condition there would refuse the call itself."
  }
}

run "the_set_is_named_for_its_environment_and_assigned_to_the_user_named" {
  command = apply

  assert {
    condition     = aws_ssoadmin_permission_set.invoker[0].name == "DebateDevBedrockInvoker" && aws_ssoadmin_permission_set.invoker[0].session_duration == "PT8H"
    error_message = "dev's set is DebateDevBedrockInvoker, with a working day's session."
  }

  assert {
    condition     = aws_ssoadmin_permission_set_inline_policy.invoker[0].inline_policy == output.policy_json
    error_message = "The set's inline policy is the policy the other runs read."
  }

  assert {
    condition = jsonencode([
      for assignment in values(aws_ssoadmin_account_assignment.invokers) :
      [assignment.principal_type, assignment.principal_id, assignment.target_type, assignment.target_id]
      ]) == jsonencode([
      ["USER", "a1b2c3d4e5-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d", "AWS_ACCOUNT", "111122223333"],
    ])
    error_message = "The set has one account assignment, to the one user named, in this account."
  }

  assert {
    condition     = output.profile_name == "debate-dev-bedrock" && output.permission_set_name == "DebateDevBedrockInvoker"
    error_message = "The outputs name the profile models.aws_profile names, and the set."
  }
}

run "prod_names_its_own_set_and_grants_the_same_models" {
  command = apply

  variables {
    name_prefix = "debate-prod-bedrock"
    environment = "prod"
  }

  assert {
    condition     = aws_ssoadmin_permission_set.invoker[0].name == "DebateProdBedrockInvoker" && output.profile_name == "debate-prod-bedrock"
    error_message = "prod's set and profile carry prod's names (ADR-0010 rule 2)."
  }

  assert {
    condition     = length(flatten([for statement in jsondecode(output.policy_json).Statement : flatten([statement.Resource])])) == 10
    error_message = "prod grants the same ten resources: both roots read both routing files."
  }
}

# ---------------------------------------------------------------------------------------------
# The grant at plan time: what the PM reads before an apply (v1-e05-t20)
# ---------------------------------------------------------------------------------------------

run "prod_plans_exactly_the_4x_models_both_routing_files_route_to" {
  command = plan

  variables {
    name_prefix = "debate-prod-bedrock"
    environment = "prod"
  }

  assert {
    condition = jsonencode(sort(flatten([
      for statement in jsondecode(output.policy_json).Statement : flatten([statement.Resource])
      ]))) == jsonencode(sort([
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
      "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0",
    ]))
    error_message = "prod's plan grants exactly the ten resources the two routing files name: the Haiku 4.5 and Sonnet 4.6 profiles, their models in the three regions, Titan and Cohere."
  }

  assert {
    condition = jsonencode(sort(distinct(flatten([
      for statement in jsondecode(output.policy_json).Statement :
      flatten([try(statement.Condition.StringEquals["bedrock:InferenceProfileArn"], [])])
      ])))) == jsonencode(sort([
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-sonnet-4-6",
    ]))
    error_message = "prod's plan reaches the Claude models through the Haiku 4.5 and Sonnet 4.6 profiles alone."
  }

  assert {
    condition = !anytrue([
      for resource in flatten([for statement in jsondecode(output.policy_json).Statement : flatten([statement.Resource])]) :
      strcontains(resource, "*") || strcontains(resource, "-5-5")
    ])
    error_message = "No resource is a wildcard and none is a 5.5 model, whose quotas the account holds at zero (task spec: forbidden)."
  }
}

run "dev_plans_the_same_grant_as_prod" {
  command = plan

  assert {
    condition = jsonencode(sort(flatten([
      for statement in jsondecode(output.policy_json).Statement : flatten([statement.Resource])
      ]))) == jsonencode(sort([
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
      "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0",
    ]))
    error_message = "dev's plan grants the same ten resources: both roots read both routing files."
  }
}

# ---------------------------------------------------------------------------------------------
# Read from the routing files, and nothing else
# ---------------------------------------------------------------------------------------------

run "a_routing_file_with_one_route_grants_that_route_alone" {
  command = apply

  variables {
    routing_files = ["tests/routing_files/one_profile_and_no_scoring_route.yaml"]
  }

  assert {
    condition = jsonencode(sort(flatten([
      for statement in jsondecode(output.policy_json).Statement : flatten([statement.Resource])
      ]))) == jsonencode(sort([
      "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-haiku-5-5",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-5-5",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-5-5",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-5-5",
    ]))
    error_message = "One Claude route grants its profile and its model in the three regions, and nothing a routing file does not name."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(output.policy_json).Statement : length(flatten([statement.Resource])) > 0
    ])
    error_message = "A statement with nothing to grant is left out: IAM refuses a statement with no resource."
  }
}

run "a_profile_outside_the_us_is_refused" {
  command = plan

  variables {
    routing_files = ["tests/routing_files/a_profile_outside_the_us.yaml"]
  }

  expect_failures = [var.routing_files]
}

run "no_routing_file_is_refused" {
  command = plan

  variables {
    routing_files = []
  }

  expect_failures = [var.routing_files]
}

run "a_prefix_without_its_environment_is_refused" {
  command = plan

  variables {
    name_prefix = "debate-bedrock"
  }

  expect_failures = [var.name_prefix]
}

# ---------------------------------------------------------------------------------------------
# What exists without Identity Center, or without a user
# ---------------------------------------------------------------------------------------------

run "nobody_named_is_a_set_with_no_assignment" {
  command = apply

  variables {
    invoker_user_names = []
  }

  assert {
    condition     = length(aws_ssoadmin_permission_set.invoker) == 1 && length(aws_ssoadmin_account_assignment.invokers) == 0
    error_message = "With no user named, the set exists and nobody is assigned it."
  }
}

run "no_identity_center_creates_no_permission_set" {
  command = apply

  variables {
    identity_center_instance_arn = null
    identity_store_id            = null
    invoker_user_names           = []
  }

  assert {
    condition = (
      length(aws_ssoadmin_permission_set.invoker) == 0
      && length(aws_ssoadmin_permission_set_inline_policy.invoker) == 0
      && output.permission_set_name == null
    )
    error_message = "Without an Identity Center instance there is no permission set and no policy attached to one."
  }
}

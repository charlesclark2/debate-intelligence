# The credential a model call is made with, as an Identity Center permission set:
# Debate<Env>BedrockInvoker (task v1-e05-t08-bedrock-invoke-access).
#
# `bedrock:InvokeModel` and nothing else. Converse, which the Bedrock adapter sends its structured
# calls through, is authorised by InvokeModel; there is no `bedrock:Converse` action, and the
# adapter does not stream, so InvokeModelWithResponseStream is not granted either
# (v1-e05-t02-bedrock-adapter's report). No model-access, logging, guardrail or provisioning
# action: the account's one-time model-access steps are done once, as break-glass, by the runbook
# (docs/runbooks/bedrock-access.md), never by this set.
#
# On exactly what the routing files name, read from them (var.routing_files), so no identifier is
# written here and none can be granted that a route does not use:
#
#   * each route's inference profile, in the route's region. That is the identifier a Claude call
#     names (ADR-0010: the `us.` profile ids, never a bare model id);
#   * the model behind each profile, in every region the profile may send the call to, and only
#     when the call came through one of these profiles: bedrock:InferenceProfileArn. A profile
#     authorises the call on itself and on the model in whichever region serves it, so without
#     the model statement every call is refused, and without the condition the set could call the
#     model directly;
#   * each route with no profile (Titan embeddings, Cohere rerank), on its model in its region.
#
# Like every permission set here it needs an Identity Center instance, so the module stays testable
# without one, and it carries no long-lived access key: the operator signs in with SSO and assumes
# the set through the profile named after name_prefix. The policy is built with jsonencode rather
# than an aws_iam_policy_document data source so that the module's tests can read it back under a
# mocked provider.

data "aws_caller_identity" "current" {}

locals {
  create_permission_set = var.identity_center_instance_arn != null

  # DebateDevBedrockInvoker / DebateProdBedrockInvoker: 24 characters in prod, under Identity
  # Center's 32.
  permission_set_name = "Debate${title(var.environment)}BedrockInvoker"

  # debate-dev-bedrock / debate-prod-bedrock: the profile `models.aws_profile` names.
  profile_name = var.name_prefix

  account_id = data.aws_caller_identity.current.account_id

  # Where a `us.` geographic inference profile may send a call: the regions the model cards list
  # for calls from us-east-1 (v1-e05-t01's report, ADR-0010). A profile of another geography is
  # refused by a validation on var.routing_files rather than granted on regions nobody checked.
  profile_destination_regions = ["us-east-1", "us-east-2", "us-west-2"]

  bedrock_routes = [
    for route in flatten([for path in var.routing_files : values(yamldecode(file(path)).routes)]) :
    route if route.provider == "bedrock"
  ]

  profile_routes = [for route in local.bedrock_routes : route if try(route.inference_profile, null) != null]
  direct_routes  = [for route in local.bedrock_routes : route if try(route.inference_profile, null) == null]

  inference_profile_arns = sort(distinct([
    for route in local.profile_routes :
    "arn:aws:bedrock:${route.region}:${local.account_id}:inference-profile/${route.inference_profile}"
  ]))

  # A foundation model's ARN names no account.
  models_behind_profiles_arns = sort(distinct(flatten([
    for route in local.profile_routes : [
      for region in local.profile_destination_regions :
      "arn:aws:bedrock:${region}::foundation-model/${route.model_id}"
    ]
  ])))

  direct_model_arns = sort(distinct([
    for route in local.direct_routes :
    "arn:aws:bedrock:${route.region}::foundation-model/${route.model_id}"
  ]))

  statements = [
    {
      Sid      = "InvokeTheRoutedInferenceProfiles"
      Effect   = "Allow"
      Action   = "bedrock:InvokeModel"
      Resource = local.inference_profile_arns
    },
    {
      Sid      = "InvokeTheModelsBehindTheProfilesThroughThemOnly"
      Effect   = "Allow"
      Action   = "bedrock:InvokeModel"
      Resource = local.models_behind_profiles_arns
      Condition = {
        StringEquals = { "bedrock:InferenceProfileArn" = local.inference_profile_arns }
      }
    },
    {
      Sid      = "InvokeTheModelsRoutedWithoutAProfile"
      Effect   = "Allow"
      Action   = "bedrock:InvokeModel"
      Resource = local.direct_model_arns
    },
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    # IAM refuses a statement with no resource, so one with nothing to grant is left out.
    Statement = [for statement in local.statements : statement if length(statement.Resource) > 0]
  })
}

# Tagged through the calling root's provider `default_tags`, which tflint cannot see from here.
# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "invoker" {
  count = local.create_permission_set ? 1 : 0

  name             = local.permission_set_name
  description      = "Calls the ${var.environment} routed Bedrock models: bedrock:InvokeModel on the inference profiles and models config/model_routing.*.yaml names, nothing else (v1-e05-t08)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT8H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "invoker" {
  count = local.create_permission_set ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.invoker[0].arn
  inline_policy      = local.policy
}

# Assignments. Students are never assigned a permission set; the list holds adult maintainers only,
# and it comes from the gitignored owner.auto.tfvars because it is people's names.

data "aws_identitystore_user" "invokers" {
  for_each = local.create_permission_set ? toset(var.invoker_user_names) : toset([])

  identity_store_id = var.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

resource "aws_ssoadmin_account_assignment" "invokers" {
  for_each = local.create_permission_set ? toset(var.invoker_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.invoker[0].arn

  principal_id   = data.aws_identitystore_user.invokers[each.value].user_id
  principal_type = "USER"

  target_id   = local.account_id
  target_type = "AWS_ACCOUNT"
}

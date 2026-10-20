# The two credentials the operator reaches the pilot with, as Identity Center permission sets
# (ADR-0019 (f) 3 and 4).
#
#   TubDeployer   what scripts/tub_deploy.sh runs as: push to this environment's repository,
#                 point this environment's function at the pushed image, and read the function
#                 back while waiting for the update. Nothing else.
#   TubAccounts   what the coach's `tub users` commands run as (v1-e39-t05): the administrative
#                 Cognito actions the account lifecycle of ADR-0019 (d) names, on this
#                 environment's pool, and PutLogEvents on the account-changes stream of its audit
#                 group.
#
# Neither exists without an Identity Center instance, so the module stays testable without one.
# Neither carries a long-lived access key: the operator signs in with SSO and assumes the set
# through the profile named after it. Creating them needs break-glass, which is why the runbook's
# applies run as debate-admin, as the website's do.

locals {
  create_permission_sets = var.identity_center_instance_arn != null

  # DebateDevTubDeployer / DebateProdTubDeployer, and the matching account sets.
  deployer_permission_set_name = "Debate${title(var.environment)}TubDeployer"
  accounts_permission_set_name = "Debate${title(var.environment)}TubAccounts"

  # The SSO profile names the runbook tells the operator to configure, and the default profile
  # scripts/tub_deploy.sh uses.
  deployer_profile_name = "${var.name_prefix}-deployer"
  accounts_profile_name = "${var.name_prefix}-accounts"

  deployer_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # `docker login` to ECR. AWS defines no resource for this action, so it cannot be scoped.
        Sid      = "SignInToTheImageRegistry"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        # A push, and the two reads Lambda makes as the caller when UpdateFunctionCode names an
        # image in this repository.
        Sid    = "PushToItsOwnRepository"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = aws_ecr_repository.function.arn
      },
      {
        # Point the function at a digest, then read it back: `aws lambda wait function-updated`
        # polls GetFunctionConfiguration, and the script reads the pilot's origin from it to check
        # /healthz through CloudFront.
        Sid    = "UpdateItsOwnFunctionCode"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
        ]
        Resource = aws_lambda_function.pilot.arn
      },
    ]
  })

  # The account lifecycle of ADR-0019 (d), command by command: add (create, add to group), list
  # (list, get, groups), reset (set a temporary password, remove the authenticator, sign out
  # everywhere), disable and enable, remove (sign out, delete).
  accounts_cognito_actions = [
    "cognito-idp:AdminCreateUser",
    "cognito-idp:AdminAddUserToGroup",
    "cognito-idp:ListUsers",
    "cognito-idp:ListUsersInGroup",
    "cognito-idp:AdminGetUser",
    "cognito-idp:AdminListGroupsForUser",
    "cognito-idp:AdminSetUserPassword",
    "cognito-idp:AdminDeleteSoftwareToken",
    "cognito-idp:AdminUserGlobalSignOut",
    "cognito-idp:AdminDisableUser",
    "cognito-idp:AdminEnableUser",
    "cognito-idp:AdminDeleteUser",
  ]

  accounts_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ManageAccountsInItsOwnPool"
        Effect   = "Allow"
        Action   = local.accounts_cognito_actions
        Resource = aws_cognito_user_pool.pilot.arn
      },
      {
        # One stream, append only. The stream exists already (main.tf), so no CreateLogStream.
        Sid      = "RecordAccountChangesInTheAuditLog"
        Effect   = "Allow"
        Action   = "logs:PutLogEvents"
        Resource = aws_cloudwatch_log_stream.account_changes.arn
      },
    ]
  })
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "deployer" {
  count = local.create_permission_sets ? 1 : 0

  name             = local.deployer_permission_set_name
  description      = "Deploys the ${var.environment} student search pilot: push to ${local.repository_name} and update that function's code. Nothing else (ADR-0019)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT1H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "deployer" {
  count = local.create_permission_sets ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.deployer[0].arn
  inline_policy      = local.deployer_policy
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "accounts" {
  count = local.create_permission_sets ? 1 : 0

  name             = local.accounts_permission_set_name
  description      = "The coach's tub users commands for the ${var.environment} pilot: manage accounts in its pool and record each change in its audit log (ADR-0019)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT1H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "accounts" {
  count = local.create_permission_sets ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.accounts[0].arn
  inline_policy      = local.accounts_policy
}

data "aws_identitystore_user" "permission_set_users" {
  for_each = local.create_permission_sets ? toset(concat(var.deployer_user_names, var.accounts_user_names)) : toset([])

  identity_store_id = var.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

resource "aws_ssoadmin_account_assignment" "deployers" {
  for_each = local.create_permission_sets ? toset(var.deployer_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.deployer[0].arn

  principal_id   = data.aws_identitystore_user.permission_set_users[each.value].user_id
  principal_type = "USER"

  target_id   = data.aws_caller_identity.current.account_id
  target_type = "AWS_ACCOUNT"
}

resource "aws_ssoadmin_account_assignment" "accounts" {
  for_each = local.create_permission_sets ? toset(var.accounts_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.accounts[0].arn

  principal_id   = data.aws_identitystore_user.permission_set_users[each.value].user_id
  principal_type = "USER"

  target_id   = data.aws_caller_identity.current.account_id
  target_type = "AWS_ACCOUNT"
}

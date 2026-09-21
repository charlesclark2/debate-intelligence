# IAM Identity Center permission sets.
#
# Humans reach this account only through Identity Center; there are no IAM users for people and
# no long-lived access keys. Three sets are defined here:
#
#   DebateBreakGlassAdmin - full administrator, short session, emergencies only.
#   DebateMaintainer      - day-to-day work, denied everything tagged or named prod.
#   DebateReadOnly        - read-only across the account; the prod CLI profile until
#                           v1-e29-t03-evidence-buckets adds a least-privilege prod operator set.
#
# The DebateMaintainer denies are what make ADR-0010's single-account fallback real: with no
# account boundary between dev and prod, a dev-scoped credential must be unable to reach prod
# evidence by policy rather than by convention.
#
# The pre-existing AdministratorAccess permission set in this instance belongs to the account's
# other projects and is deliberately not managed here.

resource "aws_ssoadmin_permission_set" "break_glass_admin" {
  name             = "DebateBreakGlassAdmin"
  description      = "Emergency administrator access. Use only with a recorded reason; every action lands in the organization trail."
  instance_arn     = local.identity_center_instance_arn
  session_duration = "PT1H"

  tags = {
    Environment = "shared"
    Purpose     = "break-glass-admin"
  }
}

resource "aws_ssoadmin_managed_policy_attachment" "break_glass_admin" {
  instance_arn       = local.identity_center_instance_arn
  managed_policy_arn = "arn:${local.partition}:iam::aws:policy/AdministratorAccess"
  permission_set_arn = aws_ssoadmin_permission_set.break_glass_admin.arn
}

resource "aws_ssoadmin_permission_set" "maintainer" {
  name             = "DebateMaintainer"
  description      = "Day-to-day maintainer access for the dev environment. Denied every prod-scoped resource."
  instance_arn     = local.identity_center_instance_arn
  session_duration = "PT8H"

  tags = {
    Environment = "dev"
    Purpose     = "maintainer"
  }
}

resource "aws_ssoadmin_managed_policy_attachment" "maintainer" {
  instance_arn       = local.identity_center_instance_arn
  managed_policy_arn = "arn:${local.partition}:iam::aws:policy/PowerUserAccess"
  permission_set_arn = aws_ssoadmin_permission_set.maintainer.arn
}

data "aws_iam_policy_document" "maintainer_guardrails" {
  # Rule 4 of ADR-0010: prod evidence is never reachable from a dev-scoped credential. Two
  # overlapping denies, because the tag condition only bites on services that support resource
  # tags in authorization, while the name condition always does.
  statement {
    sid       = "DenyProdAndSharedBucketsByName"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = local.prod_bucket_arns
  }

  statement {
    sid       = "DenyAnythingTaggedProd"
    effect    = "Deny"
    actions   = ["*"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Environment"
      values   = ["prod"]
    }
  }

  statement {
    sid    = "DenyProdKmsKeysByAlias"
    effect = "Deny"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
      "kms:ScheduleKeyDeletion",
      "kms:DisableKey",
    ]
    resources = ["*"]

    condition {
      test     = "ForAnyValue:StringLike"
      variable = "kms:ResourceAliases"
      values = [
        "alias/${var.name_prefix}-prod-*",
        "alias/${var.name_prefix}-shared-*",
      ]
    }
  }

  # No human or workload in this account gets long-lived credentials (task spec: forbidden).
  statement {
    sid    = "DenyLongLivedCredentials"
    effect = "Deny"
    actions = [
      "iam:CreateUser",
      "iam:CreateAccessKey",
      "iam:CreateLoginProfile",
      "iam:UpdateAccessKey",
    ]
    resources = ["*"]
  }

  # A maintainer must not be able to quietly remove the controls this task exists to install.
  #
  # Mutating actions only. An earlier version denied organizations:*, sso:* and sso-directory:*,
  # which also blocked harmless reads - describe-organization, list-permission-sets, list-users.
  # That is worse than it sounds: the denies that matter here are the ones separating dev from
  # prod, and an AccessDenied that shows up during ordinary work teaches the operator to wave the
  # next one through. Reads stay allowed so a refusal keeps meaning something.
  statement {
    sid    = "DenyTamperingWithGuardrails"
    effect = "Deny"
    actions = [
      "cloudtrail:DeleteTrail",
      "cloudtrail:StopLogging",
      "cloudtrail:UpdateTrail",
      "cloudtrail:PutEventSelectors",
      "budgets:DeleteBudget",
      "budgets:ModifyBudget",
      "ce:DeleteAnomalyMonitor",
      "ce:DeleteAnomalySubscription",
      "ce:UpdateAnomalyMonitor",
      "ce:UpdateAnomalySubscription",
      "organizations:LeaveOrganization",
      "organizations:DeleteOrganization",
      "organizations:RemoveAccountFromOrganization",
      "organizations:EnableAWSServiceAccess",
      "organizations:DisableAWSServiceAccess",
      "organizations:AttachPolicy",
      "organizations:DetachPolicy",
      "organizations:CreatePolicy",
      "organizations:UpdatePolicy",
      "organizations:DeletePolicy",
      "sso:Create*",
      "sso:Delete*",
      "sso:Update*",
      "sso:Put*",
      "sso:Attach*",
      "sso:Detach*",
      "sso:Provision*",
      "sso:Associate*",
      "sso:Disassociate*",
      "sso-directory:Create*",
      "sso-directory:Delete*",
      "sso-directory:Update*",
      "identitystore:Create*",
      "identitystore:Delete*",
      "identitystore:Update*",
    ]
    resources = ["*"]
  }
}

resource "aws_ssoadmin_permission_set_inline_policy" "maintainer" {
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.maintainer.arn
  inline_policy      = data.aws_iam_policy_document.maintainer_guardrails.json
}

resource "aws_ssoadmin_permission_set" "read_only" {
  name             = "DebateReadOnly"
  description      = "Read-only access. Used by the debate-prod CLI profile until v1-e29-t03 adds a least-privilege prod operator set."
  instance_arn     = local.identity_center_instance_arn
  session_duration = "PT4H"

  tags = {
    Environment = "prod"
    Purpose     = "read-only"
  }
}

resource "aws_ssoadmin_managed_policy_attachment" "read_only" {
  instance_arn       = local.identity_center_instance_arn
  managed_policy_arn = "arn:${local.partition}:iam::aws:policy/ReadOnlyAccess"
  permission_set_arn = aws_ssoadmin_permission_set.read_only.arn
}

# Assignments. Students are never assigned a permission set; var.identity_center_user_names
# holds adult maintainers only.

data "aws_identitystore_user" "maintainers" {
  for_each = toset(var.identity_center_user_names)

  identity_store_id = local.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

locals {
  # Every maintainer gets DebateMaintainer and DebateReadOnly; only the named break-glass users
  # additionally get DebateBreakGlassAdmin.
  standard_assignments = flatten([
    for user_name in var.identity_center_user_names : [
      for set_key, set_arn in {
        maintainer = aws_ssoadmin_permission_set.maintainer.arn
        read-only  = aws_ssoadmin_permission_set.read_only.arn
        } : {
        key                = "${user_name}-${set_key}"
        user_name          = user_name
        permission_set_arn = set_arn
      }
    ]
  ])

  break_glass_assignments = [
    for user_name in var.break_glass_user_names : {
      key                = "${user_name}-break-glass-admin"
      user_name          = user_name
      permission_set_arn = aws_ssoadmin_permission_set.break_glass_admin.arn
    }
  ]

  account_assignments = {
    for assignment in concat(local.standard_assignments, local.break_glass_assignments) :
    assignment.key => assignment
  }
}

resource "aws_ssoadmin_account_assignment" "maintainers" {
  for_each = local.account_assignments

  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = each.value.permission_set_arn

  principal_id   = data.aws_identitystore_user.maintainers[each.value.user_name].user_id
  principal_type = "USER"

  target_id   = local.account_id
  target_type = "AWS_ACCOUNT"
}

check "break_glass_users_are_maintainers" {
  assert {
    condition = length(setsubtract(
      toset(var.break_glass_user_names),
      toset(var.identity_center_user_names)
    )) == 0
    error_message = "Every break_glass_user_names entry must also appear in identity_center_user_names."
  }
}

# The coach's writer, Debate<Env>CaselistSecretWriter (ADR-0020 (2), principal 3, which names it
# Debate<Env>CaselistCredentialWriter: one character too long for Identity Center's 32 in dev).
#
# What `debate-research caselist auth set-password` and `caselist auth login --token-backend
# secretsmanager` run as on the coach's Mac: write either secret and describe it, and encrypt for
# it through Secrets Manager. No GetSecretValue and no kms:Decrypt, on anything: the coach writes
# the password again after changing it at Tabroom and never reads it back.
#
# Assigned to one user, sessions of one hour. Like every permission set here it needs an Identity
# Center instance, so the module stays testable without one; and creating it needs break-glass,
# which is why the runbook's applies run as debate-admin.

locals {
  create_permission_sets = var.identity_center_instance_arn != null

  # The SSO profile the runbook tells the coach to configure for this permission set.
  credential_writer_profile_name = "${var.name_prefix}-writer"

  credential_writer_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "WriteAndDescribeTheTwoSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:PutSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = [
          aws_secretsmanager_secret.tabroom_password.arn,
          aws_secretsmanager_secret.token.arn,
        ]
      },
      {
        Sid      = "EncryptForTheTwoSecretsThroughSecretsManager"
        Effect   = "Allow"
        Action   = "kms:GenerateDataKey"
        Resource = aws_kms_key.credentials.arn
        Condition = {
          StringEquals = { "kms:ViaService" = local.secrets_manager_service }
          StringLike = {
            "kms:EncryptionContext:SecretARN" = [
              aws_secretsmanager_secret.tabroom_password.arn,
              aws_secretsmanager_secret.token.arn,
            ]
          }
        }
      },
    ]
  })
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "credential_writer" {
  count = local.create_permission_sets ? 1 : 0

  name             = local.credential_writer_set_name
  description      = "The coach writes the ${var.environment} caselist run's Tabroom password and token. Never reads either back (ADR-0020)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT1H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "credential_writer" {
  count = local.create_permission_sets ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.credential_writer[0].arn
  inline_policy      = local.credential_writer_policy
}

data "aws_identitystore_user" "credential_writer" {
  for_each = local.create_permission_sets ? toset(var.credential_writer_user_names) : toset([])

  identity_store_id = var.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

resource "aws_ssoadmin_account_assignment" "credential_writer" {
  for_each = local.create_permission_sets ? toset(var.credential_writer_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.credential_writer[0].arn

  principal_id   = data.aws_identitystore_user.credential_writer[each.value].user_id
  principal_type = "USER"

  target_id   = local.account_id
  target_type = "AWS_ACCOUNT"
}

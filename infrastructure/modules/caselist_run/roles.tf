# The two task roles (ADR-0020 (2), "The three principals, exactly").
#
#   debate-<env>-caselist-login   the login task's role: reads the password, writes the token,
#                                 publishes a failed login to the alert topic. Nothing else: no S3,
#                                 no other secret.
#   debate-<env>-caselist-run     the run's role: reads the token only, never the password, and
#                                 holds the everyday evidence permissions (v1-e40-t03), the same
#                                 document as the EvidenceOperator permission set's, which lists,
#                                 reads, publishes and never deletes. Nothing more. The run's state
#                                 (ADR-0020 (3)) lives under prefixes that document already writes.
#
# Each role's policies are held exclusive, so a policy attached or written by hand is removed at
# the next apply. Only DebateBreakGlassAdmin (the apply) and the login schedule's own role hold
# iam:PassRole on the login role (login_task.tf); DebateMaintainer's PowerUserAccess has none, and
# the run's deployer is allowed the run's roles and denied the login's (deployer.tf).

# tflint-ignore: aws_resource_missing_tags
resource "aws_iam_role" "login" {
  name                 = local.login_role_name
  description          = "The ${var.environment} weekly caselist login task: reads the Tabroom password, writes the caselist token (ADR-0020 (2))."
  assume_role_policy   = local.ecs_tasks_assume_role_policy
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "login" {
  name   = "caselist-credentials"
  role   = aws_iam_role.login.id
  policy = local.login_role_policy
}

resource "aws_iam_role_policies_exclusive" "login" {
  role_name    = aws_iam_role.login.name
  policy_names = [aws_iam_role_policy.login.name]
}

resource "aws_iam_role_policy_attachments_exclusive" "login" {
  role_name   = aws_iam_role.login.name
  policy_arns = []
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_iam_role" "run" {
  name                 = local.run_role_name
  description          = "The ${var.environment} weekly caselist run. Reads the caselist token, never the Tabroom password (ADR-0020 (2))."
  assume_role_policy   = local.ecs_tasks_assume_role_policy
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "run_credentials" {
  name   = "caselist-credentials"
  role   = aws_iam_role.run.id
  policy = local.run_role_credentials_policy
}

# The everyday evidence permissions, exactly as the EvidenceOperator permission set holds them:
# variables.tf refuses a document that deletes, uses a wildcard or names anything but the evidence
# bucket and its key.
resource "aws_iam_role_policy" "run_evidence" {
  name   = "everyday-evidence"
  role   = aws_iam_role.run.id
  policy = var.evidence_policy_json
}

# The run role's two policies, and no other: one written or attached by hand is removed at the
# next apply.
resource "aws_iam_role_policies_exclusive" "run" {
  role_name    = aws_iam_role.run.name
  policy_names = [aws_iam_role_policy.run_credentials.name, aws_iam_role_policy.run_evidence.name]
}

resource "aws_iam_role_policy_attachments_exclusive" "run" {
  role_name   = aws_iam_role.run.name
  policy_arns = []
}

locals {
  login_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadThePassword"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.tabroom_password.arn
      },
      {
        Sid      = "DecryptThePasswordThroughSecretsManager"
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = aws_kms_key.credentials.arn
        Condition = {
          StringEquals = {
            "kms:ViaService"                  = local.secrets_manager_service
            "kms:EncryptionContext:SecretARN" = aws_secretsmanager_secret.tabroom_password.arn
          }
        }
      },
      {
        Sid      = "WriteTheToken"
        Effect   = "Allow"
        Action   = "secretsmanager:PutSecretValue"
        Resource = aws_secretsmanager_secret.token.arn
      },
      {
        Sid      = "EncryptTheTokenThroughSecretsManager"
        Effect   = "Allow"
        Action   = "kms:GenerateDataKey"
        Resource = aws_kms_key.credentials.arn
        Condition = {
          StringEquals = {
            "kms:ViaService"                  = local.secrets_manager_service
            "kms:EncryptionContext:SecretARN" = aws_secretsmanager_secret.token.arn
          }
        }
      },
      {
        # ADR-0020 (6): a failed login tells the coach, without naming the account.
        Sid      = "TellTheCoachALoginFailed"
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = local.alert_topic_arn
      },
    ]
  })

  run_role_credentials_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadTheToken"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.token.arn
      },
      {
        Sid      = "DecryptTheTokenThroughSecretsManager"
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = aws_kms_key.credentials.arn
        Condition = {
          StringEquals = {
            "kms:ViaService"                  = local.secrets_manager_service
            "kms:EncryptionContext:SecretARN" = aws_secretsmanager_secret.token.arn
          }
        }
      },
    ]
  })
}

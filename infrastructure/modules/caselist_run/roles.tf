# The two task roles (ADR-0020 (2), "The three principals, exactly").
#
#   debate-<env>-caselist-login   the login task's role: reads the password, writes the token,
#                                 publishes a failed login to the alert topic. Nothing else: no S3,
#                                 no other secret.
#   debate-<env>-caselist-run     the run's role. Its credentials grant is here and reads the token
#                                 only; it never reads the password. The run's other grants (the
#                                 evidence bucket, its state, ADR-0020 (3)) are v1-e40-t03's and
#                                 t04's, as a second inline policy beside this one.
#
# Each role's policies are held exclusive, so a policy attached or written by hand is removed at
# the next apply. Only DebateBreakGlassAdmin (the apply) and the login schedule's own role hold
# iam:PassRole on the login role (login_task.tf); DebateMaintainer's PowerUserAccess has none.

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

# v1-e40-t03 and t04 add their inline policy's name here.
resource "aws_iam_role_policies_exclusive" "run" {
  role_name    = aws_iam_role.run.name
  policy_names = [aws_iam_role_policy.run_credentials.name]
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

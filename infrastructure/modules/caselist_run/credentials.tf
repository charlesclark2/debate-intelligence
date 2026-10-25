# The two secrets and the key they are encrypted under (ADR-0020 (2), "The secrets" and "The key").
#
#   debate-<env>-caselist-tabroom-password   the coach's Tabroom username and password, as JSON.
#                                            Written by the coach; read by the login role only.
#   debate-<env>-caselist-token              the caselist_token record the token store writes.
#                                            Written by the login role and the coach; read by the
#                                            run role only.
#
# Both are created as empty shells: there is no aws_secretsmanager_secret_version here, so no value
# is ever in Terraform state (v2-e10-t04's rule). The coach writes the password with
# `debate-research caselist auth set-password`; the login task writes the token.
#
# The key policy and each secret's resource policy enforce the read rules on their own, so that
# neither an IAM grant nor a policy left off by mistake widens a read. The policies are built with
# jsonencode so the module's tests can read them back under a mocked provider.

# Tagged by the calling root's provider default_tags, which tflint cannot see from inside the
# module; linting envs/dev or envs/prod follows the module call and checks them there.
# tflint-ignore: aws_resource_missing_tags
resource "aws_kms_key" "credentials" {
  description             = "Encrypts the ${var.environment} caselist run's two secrets, the Tabroom password and the caselist token, and nothing else (ADR-0020 (2))."
  key_usage               = "ENCRYPT_DECRYPT"
  enable_key_rotation     = true
  rotation_period_in_days = 365
  deletion_window_in_days = 30
  policy                  = local.credentials_key_policy
}

resource "aws_kms_alias" "credentials" {
  name          = local.key_alias
  target_key_id = aws_kms_key.credentials.key_id
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_secretsmanager_secret" "tabroom_password" {
  name        = local.password_secret_name
  description = "The coach's Tabroom username and password for the ${var.environment} weekly login. Written with `caselist auth set-password`; read by the login role only (ADR-0020 (2))."
  kms_key_id  = aws_kms_key.credentials.arn
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_secretsmanager_secret" "token" {
  name        = local.token_secret_name
  description = "The ${var.environment} caselist_token record. Written by the login role and the coach's writer; read by the run role only (ADR-0020 (2))."
  kms_key_id  = aws_kms_key.credentials.arn
}

resource "aws_secretsmanager_secret_policy" "tabroom_password" {
  secret_arn          = aws_secretsmanager_secret.tabroom_password.arn
  policy              = local.password_secret_policy
  block_public_policy = true
}

resource "aws_secretsmanager_secret_policy" "token" {
  secret_arn          = aws_secretsmanager_secret.token.arn
  policy              = local.token_secret_policy
  block_public_policy = true
}

locals {
  login_role_arn = aws_iam_role.login.arn
  run_role_arn   = aws_iam_role.run.arn

  # The SecretVersionId Secrets Manager puts in the encryption context of the GenerateDataKey and
  # Decrypt it makes to validate a caller's access to a secret's key (the page cited below).
  key_validation_version_id = "RequestToValidateKeyAccess"

  # What administering the key means: everything Terraform does to create, read, rotate, tag and
  # retire it. No cryptographic operation, and no grant.
  key_administration_actions = [
    "kms:DescribeKey",
    "kms:GetKeyPolicy",
    "kms:PutKeyPolicy",
    "kms:GetKeyRotationStatus",
    "kms:EnableKeyRotation",
    "kms:DisableKeyRotation",
    "kms:RotateKeyOnDemand",
    "kms:ListKeyRotations",
    "kms:ListResourceTags",
    "kms:TagResource",
    "kms:UntagResource",
    "kms:UpdateKeyDescription",
    "kms:EnableKey",
    "kms:DisableKey",
    "kms:CreateAlias",
    "kms:UpdateAlias",
    "kms:DeleteAlias",
    "kms:ScheduleKeyDeletion",
    "kms:CancelKeyDeletion",
  ]

  # ADR-0020 (2), "Key policy". No statement delegates the key's use to IAM: the account is named
  # only together with a principal pattern, so DebateMaintainer's PowerUserAccess, which allows
  # kms:* in IAM, can neither use the key nor change this policy.
  credentials_key_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "KeyAdministrationByBreakGlassOnly"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = local.key_administration_actions
        Resource  = "*"
        Condition = {
          ArnLike = { "aws:PrincipalArn" = local.break_glass_principal_arns }
        }
      },
      {
        # Break-glass creates both secrets (the apply), and Secrets Manager validates the caller's
        # access to the key when a secret's key is set: it calls GenerateDataKey and Decrypt as the
        # caller and discards the results, with SecretVersionId the literal RequestToValidateKeyAccess
        # ("Validating access to the KMS key" in "Secret encryption and decryption in AWS Secrets
        # Manager", https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html).
        # Without this, the first apply's two CreateSecret calls were refused (2026-10-24). These two
        # statements allow exactly the validation, through Secrets Manager, for the two secrets.
        # Break-glass never writes or reads a secret value: a stored version's data key is bound to
        # its own SecretVersionId, so a decrypt that must carry the validation id cannot open one.
        Sid       = "BreakGlassEncryptsWhenCreatingTheTwoSecrets"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = "kms:GenerateDataKey"
        Resource  = "*"
        Condition = {
          ArnLike = { "aws:PrincipalArn" = local.break_glass_principal_arns }
          StringEquals = {
            "kms:ViaService"                        = local.secrets_manager_service
            "kms:EncryptionContext:SecretVersionId" = local.key_validation_version_id
          }
          StringLike = {
            "kms:EncryptionContext:SecretARN" = [local.password_secret_arn_pattern, local.token_secret_arn_pattern]
          }
        }
      },
      {
        Sid       = "BreakGlassDecryptsOnlyToValidateTheKey"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          ArnLike = { "aws:PrincipalArn" = local.break_glass_principal_arns }
          StringEquals = {
            "kms:ViaService"                        = local.secrets_manager_service
            "kms:EncryptionContext:SecretVersionId" = local.key_validation_version_id
          }
          StringLike = {
            "kms:EncryptionContext:SecretARN" = [local.password_secret_arn_pattern, local.token_secret_arn_pattern]
          }
        }
      },
      {
        Sid       = "TheLoginRoleDecryptsThePassword"
        Effect    = "Allow"
        Principal = { AWS = local.login_role_arn }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          StringEquals = { "kms:ViaService" = local.secrets_manager_service }
          StringLike   = { "kms:EncryptionContext:SecretARN" = local.password_secret_arn_pattern }
        }
      },
      {
        Sid       = "TheLoginRoleEncryptsTheToken"
        Effect    = "Allow"
        Principal = { AWS = local.login_role_arn }
        Action    = "kms:GenerateDataKey"
        Resource  = "*"
        Condition = {
          StringEquals = { "kms:ViaService" = local.secrets_manager_service }
          StringLike   = { "kms:EncryptionContext:SecretARN" = local.token_secret_arn_pattern }
        }
      },
      {
        Sid       = "TheRunRoleDecryptsTheToken"
        Effect    = "Allow"
        Principal = { AWS = local.run_role_arn }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          StringEquals = { "kms:ViaService" = local.secrets_manager_service }
          StringLike   = { "kms:EncryptionContext:SecretARN" = local.token_secret_arn_pattern }
        }
      },
      {
        # PutSecretValue needs GenerateDataKey and, for a new version, nothing else: Secrets
        # Manager decrypts only to compare a request that reuses an existing version's id.
        Sid       = "TheCoachsWriterEncryptsBothSecrets"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = "kms:GenerateDataKey"
        Resource  = "*"
        Condition = {
          ArnLike      = { "aws:PrincipalArn" = local.credential_writer_principals }
          StringEquals = { "kms:ViaService" = local.secrets_manager_service }
          StringLike = {
            "kms:EncryptionContext:SecretARN" = [local.password_secret_arn_pattern, local.token_secret_arn_pattern]
          }
        }
      },
      {
        # The read rules, said as refusals so no later Allow can loosen them. A Deny's conditions
        # are ANDed, so "unless break-glass validating" cannot be one statement. Each of the next
        # three denies everyone but its reader roles (ArnNotEquals) and break-glass (ArnNotLike, its
        # role being a pattern); BreakGlassDecryptsNothingButTheValidation then denies break-glass
        # every decrypt whose SecretVersionId is not the validation's, for any secret. It is the
        # union of the three break-glass halves the split leaves, so the four together exempt
        # exactly break-glass's validation and nothing wider. A negated operator is true when the
        # key is missing, so a decrypt carrying no SecretVersionId is denied to break-glass too.
        Sid       = "NobodyButTheLoginRoleDecryptsThePassword"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          StringLike   = { "kms:EncryptionContext:SecretARN" = local.password_secret_arn_pattern }
          ArnNotEquals = { "aws:PrincipalArn" = local.login_role_arn }
          ArnNotLike   = { "aws:PrincipalArn" = local.break_glass_principal_arns }
        }
      },
      {
        Sid       = "NobodyButTheRunRoleDecryptsTheToken"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          StringLike   = { "kms:EncryptionContext:SecretARN" = local.token_secret_arn_pattern }
          ArnNotEquals = { "aws:PrincipalArn" = local.run_role_arn }
          ArnNotLike   = { "aws:PrincipalArn" = local.break_glass_principal_arns }
        }
      },
      {
        Sid       = "NobodyElseDecryptsAnything"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          ArnNotEquals = { "aws:PrincipalArn" = [local.login_role_arn, local.run_role_arn] }
          ArnNotLike   = { "aws:PrincipalArn" = local.break_glass_principal_arns }
        }
      },
      {
        Sid       = "BreakGlassDecryptsNothingButTheValidation"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          ArnLike         = { "aws:PrincipalArn" = local.break_glass_principal_arns }
          StringNotEquals = { "kms:EncryptionContext:SecretVersionId" = local.key_validation_version_id }
        }
      },
      {
        # Secrets Manager needs no grant, and a re-encryption would move a ciphertext to a key with
        # other rules.
        Sid       = "NoGrantsAndNoReEncryption"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = ["kms:CreateGrant", "kms:ReEncryptFrom", "kms:ReEncryptTo"]
        Resource  = "*"
      },
    ]
  })

  # What only break-glass may do to a secret: change its policy, move it to another key, rotate
  # it, delete or restore it, or copy it to another region. ADR-0020 (2) names the first five;
  # rotation and restore are added because each changes which value or which key a read reaches.
  secret_administration_actions = [
    "secretsmanager:PutResourcePolicy",
    "secretsmanager:DeleteResourcePolicy",
    "secretsmanager:UpdateSecret",
    "secretsmanager:DeleteSecret",
    "secretsmanager:RestoreSecret",
    "secretsmanager:ReplicateSecretToRegions",
    "secretsmanager:RotateSecret",
  ]

  # Writing a value, or moving the current label to an older one, is a write.
  secret_write_actions = [
    "secretsmanager:PutSecretValue",
    "secretsmanager:UpdateSecretVersionStage",
  ]

  password_secret_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "NobodyButTheLoginRoleReadsThePassword"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "secretsmanager:GetSecretValue"
        Resource  = "*"
        Condition = {
          ArnNotLike = { "aws:PrincipalArn" = [local.login_role_arn] }
        }
      },
      {
        Sid       = "NobodyButTheCoachsWriterWritesThePassword"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = local.secret_write_actions
        Resource  = "*"
        Condition = {
          ArnNotLike = { "aws:PrincipalArn" = [local.credential_writer_principals] }
        }
      },
      {
        Sid       = "NobodyButBreakGlassChangesWhoMayReadIt"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = local.secret_administration_actions
        Resource  = "*"
        Condition = {
          ArnNotLike = { "aws:PrincipalArn" = [local.break_glass_principal_arns] }
        }
      },
    ]
  })

  token_secret_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "NobodyButTheRunRoleReadsTheToken"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = "secretsmanager:GetSecretValue"
        Resource  = "*"
        Condition = {
          ArnNotLike = { "aws:PrincipalArn" = [local.run_role_arn] }
        }
      },
      {
        Sid       = "NobodyButTheLoginRoleAndTheCoachsWriterWriteTheToken"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = local.secret_write_actions
        Resource  = "*"
        Condition = {
          ArnNotLike = { "aws:PrincipalArn" = [local.login_role_arn, local.credential_writer_principals] }
        }
      },
      {
        Sid       = "NobodyButBreakGlassChangesWhoMayReadIt"
        Effect    = "Deny"
        Principal = { AWS = "*" }
        Action    = local.secret_administration_actions
        Resource  = "*"
        Condition = {
          ArnNotLike = { "aws:PrincipalArn" = [local.break_glass_principal_arns] }
        }
      },
    ]
  })
}

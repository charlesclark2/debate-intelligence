# Offline tests for the caselist_run module: the credentials of ADR-0020 (2), the scheduled login,
# and the run (ADR-0020 (1)).
#
# `mock_provider "aws"` means no credentials, no network and no AWS account. Every role and secret
# gets an ARN of its own below (`override_resource`), because a mocked provider would otherwise give
# every role the same one, and "only the login role reads the password" would hold of any role.
#
#   terraform -chdir=infrastructure/modules/caselist_run init -backend=false
#   terraform -chdir=infrastructure/modules/caselist_run test
#
# What these runs hold the module to (task v1-e40-t02):
#
#   ac2  only the login role can read the password and only the run role the token, both under
#        the dedicated key: the key policy, both secrets' resource policies and both roles' IAM
#        policies, each on its own.
#   ac3  the writer permission set can write both secrets and read neither.
#   and  the two applies: credentials alone with no login task, then the task pinned by digest
#        and its Wednesday schedule, never retried.
#
# And what they hold it to for task v1-e40-t03, from "The run" below:
#
#   ac1  the run role holds the everyday evidence permissions and a read of the token, nothing
#        more: no read of the password, no s3:DeleteObject or s3:DeleteObjectVersion; the run's
#        network has no inbound rule; the run task is 8 vCPU, 16 GB, 100 GiB, arm64, under its
#        deadline, pinned by digest; its schedule starts after the login, disabled by default;
#        each schedule sits alone in its own group, and each scheduler role trusts that group's
#        ARN only (Scheduler's confused-deputy rule; apply B in dev, 2026-10-24);
#        Debate<Env>CaselistRunDeployer passes the run's roles and never the login's.
#
# The account id and user name below are invented.

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      name = "us-east-1"
    }
  }

  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "111122223333"
    }
  }

  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }

  mock_data "aws_availability_zones" {
    defaults = {
      names = ["us-east-1b", "us-east-1a", "us-east-1c"]
    }
  }

  mock_data "aws_identitystore_user" {
    defaults = {
      user_id = "a1b2c3d4e5-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    }
  }

  mock_resource "aws_kms_key" {
    defaults = {
      arn    = "arn:aws:kms:us-east-1:111122223333:key/00000000-0000-0000-0000-00000000c0de"
      key_id = "00000000-0000-0000-0000-00000000c0de"
    }
  }

  mock_resource "aws_ssoadmin_permission_set" {
    defaults = {
      arn = "arn:aws:sso:::permissionSet/ssoins-mock/ps-mockwriter"
    }
  }

  mock_resource "aws_ecs_task_definition" {
    defaults = {
      arn = "arn:aws:ecs:us-east-1:111122223333:task-definition/debate-mock-caselist-login:7"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:us-east-1:111122223333:log-group:debate-mock-caselist-login"
    }
  }

  mock_resource "aws_ecs_cluster" {
    defaults = {
      arn = "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
    }
  }

  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:us-east-1:111122223333:repository/debate-mock-caselist-run"
      repository_url = "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-caselist-run"
    }
  }

  mock_resource "aws_security_group" {
    defaults = {
      id = "sg-0000000000000000a"
    }
  }
}

override_resource {
  target = aws_ecs_task_definition.run
  values = {
    arn = "arn:aws:ecs:us-east-1:111122223333:task-definition/debate-mock-caselist-run:3"
  }
}

override_resource {
  target = aws_cloudwatch_log_group.run
  values = {
    arn = "arn:aws:logs:us-east-1:111122223333:log-group:debate-mock-caselist-run"
  }
}

override_resource {
  target = aws_iam_role.run_execution
  values = {
    arn  = "arn:aws:iam::111122223333:role/debate-mock-caselist-run-execution"
    name = "debate-mock-caselist-run-execution"
  }
}

override_resource {
  target = aws_iam_role.run_scheduler
  values = {
    arn  = "arn:aws:iam::111122223333:role/debate-mock-caselist-run-scheduler"
    name = "debate-mock-caselist-run-scheduler"
  }
}

override_resource {
  target = aws_iam_role.login
  values = {
    arn  = "arn:aws:iam::111122223333:role/debate-mock-caselist-login"
    name = "debate-mock-caselist-login"
  }
}

override_resource {
  target = aws_iam_role.run
  values = {
    arn  = "arn:aws:iam::111122223333:role/debate-mock-caselist-run"
    name = "debate-mock-caselist-run"
  }
}

override_resource {
  target = aws_iam_role.login_execution
  values = {
    arn  = "arn:aws:iam::111122223333:role/debate-mock-caselist-login-execution"
    name = "debate-mock-caselist-login-execution"
  }
}

override_resource {
  target = aws_iam_role.scheduler
  values = {
    arn  = "arn:aws:iam::111122223333:role/debate-mock-caselist-scheduler"
    name = "debate-mock-caselist-scheduler"
  }
}

override_resource {
  target = aws_secretsmanager_secret.tabroom_password
  values = {
    arn  = "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-PaSsWd"
    name = "debate-mock-caselist-tabroom-password"
  }
}

override_resource {
  target = aws_secretsmanager_secret.token
  values = {
    arn  = "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-ToKeNx"
    name = "debate-mock-caselist-token"
  }
}

variables {
  name_prefix                  = "debate-mock-caselist"
  environment                  = "dev"
  identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
  identity_store_id            = "d-mock000000"
  credential_writer_user_names = ["mock-coach"]
  deployer_user_names          = ["mock-maintainer"]

  # The everyday evidence permissions, in the shape module.evidence_store.operator_policy_json has
  # (infrastructure/modules/evidence_bucket/operator_access.tf), over an invented bucket and key.
  evidence_bucket_arn = "arn:aws:s3:::debate-mock-evidence-00000000"
  evidence_key_arn    = "arn:aws:kms:us-east-1:111122223333:key/00000000-0000-0000-0000-0000000e1de5"
  evidence_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ListDocumentedEvidencePrefixes"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = "arn:aws:s3:::debate-mock-evidence-00000000"
        Condition = { StringLike = { "s3:prefix" = ["raw/", "raw/*", "reports/", "reports/*"] } }
      },
      {
        Sid       = "ListEvidenceObjectVersionsForRemovalPlans"
        Effect    = "Allow"
        Action    = "s3:ListBucketVersions"
        Resource  = "arn:aws:s3:::debate-mock-evidence-00000000"
        Condition = { StringLike = { "s3:prefix" = ["raw/", "raw/*"] } }
      },
      {
        Sid      = "ReadAndPublishEvidenceObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
        Resource = "arn:aws:s3:::debate-mock-evidence-00000000/*"
      },
      {
        Sid      = "TagSupersededParsedVersionDirectories"
        Effect   = "Allow"
        Action   = ["s3:GetObjectTagging", "s3:PutObjectTagging"]
        Resource = "arn:aws:s3:::debate-mock-evidence-00000000/parsed/*"
      },
      {
        Sid      = "UseEvidenceKey"
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
        Resource = "arn:aws:kms:us-east-1:111122223333:key/00000000-0000-0000-0000-0000000e1de5"
      },
    ]
  })
}

# ---------------------------------------------------------------------------------------------
# Apply A: the credentials, the roles and the writer, with no network and no login task
# ---------------------------------------------------------------------------------------------

run "credentials_apply_creates_no_login_task" {
  command = apply

  assert {
    condition     = length(aws_ecs_task_definition.login) == 0 && length(aws_scheduler_schedule.login) == 0 && length(aws_iam_role.scheduler) == 0 && length(aws_scheduler_schedule_group.login) == 0 && length(aws_scheduler_schedule_group.run) == 0
    error_message = "Without image_digest, the module must create no login task definition, no schedule, no schedule group and no scheduler role (apply A)."
  }

  assert {
    condition     = output.login_task_definition_arn == null && output.login_schedule_name == null
    error_message = "The login task's outputs are null until apply B."
  }
}

run "both_secrets_use_the_dedicated_key_and_hold_no_value" {
  command = apply

  assert {
    condition     = aws_secretsmanager_secret.tabroom_password.kms_key_id == aws_kms_key.credentials.arn && aws_secretsmanager_secret.token.kms_key_id == aws_kms_key.credentials.arn
    error_message = "Both secrets must be encrypted under the credentials key (ADR-0020 (2))."
  }

  assert {
    condition     = aws_kms_key.credentials.enable_key_rotation && aws_kms_key.credentials.rotation_period_in_days == 365
    error_message = "The credentials key rotates every year (ADR-0020 (2))."
  }

  assert {
    condition     = aws_kms_alias.credentials.name == "alias/debate-mock-caselist-credentials"
    error_message = "The key's alias is alias/debate-<env>-caselist-credentials."
  }

  assert {
    condition     = aws_secretsmanager_secret.tabroom_password.name == "debate-mock-caselist-tabroom-password" && aws_secretsmanager_secret.token.name == "debate-mock-caselist-token"
    error_message = "The secrets are debate-<env>-caselist-tabroom-password and debate-<env>-caselist-token, the names the CLI defaults to."
  }

  assert {
    condition     = aws_secretsmanager_secret_policy.tabroom_password.block_public_policy && aws_secretsmanager_secret_policy.token.block_public_policy
    error_message = "Both secret policies must block a public policy."
  }
}

# ---------------------------------------------------------------------------------------------
# The key policy: who may decrypt what
# ---------------------------------------------------------------------------------------------

run "only_the_login_role_decrypts_the_password_and_only_the_run_role_the_token" {
  command = apply

  assert {
    # Every Allow of kms:Decrypt, by principal, principal pattern, service, secret and version id.
    # JSON-encoded, so a statement of any shape compares rather than failing to. The login role
    # decrypts the password and the run role the token, any version; break-glass decrypts only to
    # validate the key (SecretVersionId RequestToValidateKeyAccess), which opens no stored version.
    condition = toset([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      jsonencode({
        principal = statement.Principal.AWS
        pattern   = try(statement.Condition.ArnLike["aws:PrincipalArn"], null)
        service   = try(statement.Condition.StringEquals["kms:ViaService"], null)
        secret    = try(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"], null)
        version   = try(statement.Condition.StringEquals["kms:EncryptionContext:SecretVersionId"], null)
      })
      if statement.Effect == "Allow" && contains(flatten([statement.Action]), "kms:Decrypt")
      ]) == toset([
      jsonencode({
        principal = "arn:aws:iam::111122223333:role/debate-mock-caselist-login"
        pattern   = null
        service   = "secretsmanager.us-east-1.amazonaws.com"
        secret    = "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-??????"
        version   = null
      }),
      jsonencode({
        principal = "arn:aws:iam::111122223333:role/debate-mock-caselist-run"
        pattern   = null
        service   = "secretsmanager.us-east-1.amazonaws.com"
        secret    = "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-??????"
        version   = null
      }),
      jsonencode({
        principal = "arn:aws:iam::111122223333:root"
        pattern   = "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"
        service   = "secretsmanager.us-east-1.amazonaws.com"
        secret = [
          "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-??????",
          "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-??????",
        ]
        version = "RequestToValidateKeyAccess"
      }),
    ])
    error_message = "The key may let the login role decrypt the password, the run role the token, and break-glass only validate the key; nobody else decrypts anything."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["kms:Decrypt"]
      && try(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"], "") == "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-??????"
      && try(statement.Condition.ArnNotEquals["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/debate-mock-caselist-login"
      && try(statement.Condition.ArnNotLike["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"
      && toset(keys(statement.Condition)) == toset(["StringLike", "ArnNotEquals", "ArnNotLike"])
    ])
    error_message = "The key policy must deny decrypting the password to every principal but the login role and break-glass (whose decrypts the validation deny limits)."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["kms:Decrypt"]
      && try(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"], "") == "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-??????"
      && try(statement.Condition.ArnNotEquals["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/debate-mock-caselist-run"
      && try(statement.Condition.ArnNotLike["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"
      && toset(keys(statement.Condition)) == toset(["StringLike", "ArnNotEquals", "ArnNotLike"])
    ])
    error_message = "The key policy must deny decrypting the token to every principal but the run role and break-glass (whose decrypts the validation deny limits)."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["kms:Decrypt"]
      && !can(statement.Condition.StringLike)
      && toset(try(statement.Condition.ArnNotEquals["aws:PrincipalArn"], [])) == toset(["arn:aws:iam::111122223333:role/debate-mock-caselist-login", "arn:aws:iam::111122223333:role/debate-mock-caselist-run"])
      && try(statement.Condition.ArnNotLike["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"
      && toset(keys(statement.Condition)) == toset(["ArnNotEquals", "ArnNotLike"])
    ])
    error_message = "The key policy must deny every decrypt to every principal but the login and run roles and break-glass (ADR-0020 (2))."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && !can(statement.Condition)
      && toset(flatten([statement.Action])) == toset(["kms:CreateGrant", "kms:ReEncryptFrom", "kms:ReEncryptTo"])
    ])
    error_message = "The key policy must refuse grants and re-encryption to everyone."
  }

  assert {
    # Every Allow either names one of the two roles, or names the account with a principal pattern:
    # no statement delegates the key to IAM.
    condition = alltrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      contains(["arn:aws:iam::111122223333:role/debate-mock-caselist-login", "arn:aws:iam::111122223333:role/debate-mock-caselist-run"], statement.Principal.AWS)
      || can(statement.Condition.ArnLike["aws:PrincipalArn"])
      if statement.Effect == "Allow"
    ])
    error_message = "No key policy statement may allow the account as a whole: that would delegate the key to IAM, and DebateMaintainer's kms:* with it."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      !contains(flatten([statement.Action]), "kms:*") && !contains(flatten([statement.Action]), "kms:Decrypt") && !contains(flatten([statement.Action]), "kms:GenerateDataKey")
      if statement.Effect == "Allow" && can(statement.Condition.ArnLike["aws:PrincipalArn"]) && statement.Sid == "KeyAdministrationByBreakGlassOnly"
    ])
    error_message = "Key administration grants no cryptographic use of the key."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Sid == "KeyAdministrationByBreakGlassOnly" && try(statement.Condition.ArnLike["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"
      && contains(statement.Action, "kms:PutKeyPolicy")
    ])
    error_message = "Only DebateBreakGlassAdmin's role may administer the key, PutKeyPolicy included."
  }
}

# ---------------------------------------------------------------------------------------------
# The secrets' resource policies
# ---------------------------------------------------------------------------------------------

run "each_secret_policy_refuses_a_read_by_anyone_but_its_one_reader" {
  command = apply

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_secretsmanager_secret_policy.tabroom_password.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["secretsmanager:GetSecretValue"]
      && statement.Condition.ArnNotLike["aws:PrincipalArn"] == ["arn:aws:iam::111122223333:role/debate-mock-caselist-login"]
    ])
    error_message = "The password secret must deny GetSecretValue to every principal but the login role."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_secretsmanager_secret_policy.token.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["secretsmanager:GetSecretValue"]
      && statement.Condition.ArnNotLike["aws:PrincipalArn"] == ["arn:aws:iam::111122223333:role/debate-mock-caselist-run"]
    ])
    error_message = "The token secret must deny GetSecretValue to every principal but the run role."
  }

  assert {
    condition = alltrue([
      for policy in [aws_secretsmanager_secret_policy.tabroom_password.policy, aws_secretsmanager_secret_policy.token.policy] :
      alltrue([for statement in jsondecode(policy).Statement : statement.Effect == "Deny"])
    ])
    error_message = "A secret's resource policy only refuses; it grants nothing (reads and writes are granted to the roles and the writer, and refused to everyone else)."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_secretsmanager_secret_policy.tabroom_password.policy).Statement :
      statement.Effect == "Deny" && contains(statement.Action, "secretsmanager:PutSecretValue")
      && statement.Condition.ArnNotLike["aws:PrincipalArn"] == ["arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateDevCaselistSecretWriter_*"]
    ])
    error_message = "Only the coach's writer may write the password."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_secretsmanager_secret_policy.token.policy).Statement :
      statement.Effect == "Deny" && contains(statement.Action, "secretsmanager:PutSecretValue")
      && toset(statement.Condition.ArnNotLike["aws:PrincipalArn"]) == toset(["arn:aws:iam::111122223333:role/debate-mock-caselist-login", "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateDevCaselistSecretWriter_*"])
    ])
    error_message = "Only the login role and the coach's writer may write the token."
  }

  assert {
    condition = alltrue([
      for policy in [aws_secretsmanager_secret_policy.tabroom_password.policy, aws_secretsmanager_secret_policy.token.policy] :
      anytrue([
        for statement in jsondecode(policy).Statement :
        statement.Effect == "Deny"
        && length(setsubtract(["secretsmanager:PutResourcePolicy", "secretsmanager:DeleteResourcePolicy", "secretsmanager:UpdateSecret", "secretsmanager:DeleteSecret", "secretsmanager:ReplicateSecretToRegions"], statement.Action)) == 0
        && statement.Condition.ArnNotLike["aws:PrincipalArn"] == ["arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"]
      ])
    ])
    error_message = "Only DebateBreakGlassAdmin may change a secret's policy or key, delete it or replicate it (ADR-0020 (2))."
  }
}

# ---------------------------------------------------------------------------------------------
# The roles' own grants
# ---------------------------------------------------------------------------------------------

run "the_login_role_reads_the_password_writes_the_token_and_nothing_else" {
  command = apply

  assert {
    condition = flatten([
      for statement in jsondecode(aws_iam_role_policy.login.policy).Statement : statement.Resource
      if contains(flatten([statement.Action]), "secretsmanager:GetSecretValue")
    ]) == ["arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-PaSsWd"]
    error_message = "The login role reads the password secret and no other."
  }

  assert {
    condition = flatten([
      for statement in jsondecode(aws_iam_role_policy.login.policy).Statement : statement.Condition.StringEquals["kms:EncryptionContext:SecretARN"]
      if contains(flatten([statement.Action]), "kms:Decrypt")
    ]) == ["arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-PaSsWd"]
    error_message = "The login role decrypts only for the password secret."
  }

  assert {
    condition = toset(flatten([for statement in jsondecode(aws_iam_role_policy.login.policy).Statement : statement.Action])) == toset([
      "secretsmanager:GetSecretValue", "kms:Decrypt", "secretsmanager:PutSecretValue", "kms:GenerateDataKey", "sns:Publish",
    ])
    error_message = "The login role holds exactly the five actions of ADR-0020 (2): no S3, no other secret."
  }

  assert {
    condition = flatten([
      for statement in jsondecode(aws_iam_role_policy.login.policy).Statement : statement.Resource
      if contains(flatten([statement.Action]), "sns:Publish")
    ]) == ["arn:aws:sns:us-east-1:111122223333:debate-mock-caselist-run-alerts"]
    error_message = "The login role publishes only to the environment's alert topic."
  }

  assert {
    condition     = aws_iam_role_policies_exclusive.login.policy_names == toset(["caselist-credentials"]) && length(aws_iam_role_policy_attachments_exclusive.login.policy_arns) == 0
    error_message = "The login role's one inline policy is held exclusive, with no managed policy attached."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.login.assume_role_policy).Statement[0].Principal.Service == "ecs-tasks.amazonaws.com"
      && jsondecode(aws_iam_role.login.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "111122223333"
      && length(jsondecode(aws_iam_role.login.assume_role_policy).Statement) == 1
    )
    error_message = "Only ECS tasks in this account may assume the login role."
  }
}

run "the_run_role_reads_the_token_and_never_the_password" {
  command = apply

  assert {
    condition = flatten([
      for statement in jsondecode(aws_iam_role_policy.run_credentials.policy).Statement : statement.Resource
      if contains(flatten([statement.Action]), "secretsmanager:GetSecretValue")
    ]) == ["arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-ToKeNx"]
    error_message = "The run role reads the token secret and no other."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.run_credentials.policy, "tabroom-password")
    error_message = "The run role's credentials policy must not name the password secret at all."
  }

  assert {
    condition     = toset(flatten([for statement in jsondecode(aws_iam_role_policy.run_credentials.policy).Statement : statement.Action])) == toset(["secretsmanager:GetSecretValue", "kms:Decrypt"])
    error_message = "The run role's credentials grant is a read of the token and its decrypt, nothing more."
  }
}

# ---------------------------------------------------------------------------------------------
# The coach's writer permission set (ac3)
# ---------------------------------------------------------------------------------------------

run "the_writer_writes_both_secrets_and_reads_neither" {
  command = apply

  assert {
    condition     = aws_ssoadmin_permission_set.credential_writer[0].name == "DebateDevCaselistSecretWriter" && aws_ssoadmin_permission_set.credential_writer[0].session_duration == "PT1H"
    error_message = "The writer is DebateDevCaselistSecretWriter, with one-hour sessions."
  }

  assert {
    condition = alltrue([
      for action in flatten([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.credential_writer[0].inline_policy).Statement : statement.Action]) :
      !contains(["secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue", "kms:Decrypt", "kms:*", "secretsmanager:*"], action)
    ])
    error_message = "The writer must hold no GetSecretValue and no kms:Decrypt (ADR-0020 (2))."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.credential_writer[0].inline_policy).Statement :
      toset(flatten([statement.Action])) == toset(["secretsmanager:PutSecretValue", "secretsmanager:DescribeSecret"])
      && toset(flatten([statement.Resource])) == toset([
        "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-PaSsWd",
        "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-ToKeNx",
      ])
    ])
    error_message = "The writer may write and describe both secrets."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.credential_writer[0].inline_policy).Statement :
      statement.Action == "kms:GenerateDataKey" && statement.Condition.StringEquals["kms:ViaService"] == "secretsmanager.us-east-1.amazonaws.com"
      && length(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"]) == 2
    ])
    error_message = "The writer encrypts for the two secrets, through Secrets Manager only."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Allow" && statement.Action == "kms:GenerateDataKey"
      && try(statement.Condition.ArnLike["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateDevCaselistSecretWriter_*"
    ])
    error_message = "The key policy lets the writer's role encrypt, and only encrypt."
  }

  assert {
    condition     = length(aws_ssoadmin_account_assignment.credential_writer) == 1
    error_message = "The writer is assigned to the one user named."
  }
}

run "a_second_writer_is_refused" {
  command = plan

  variables {
    credential_writer_user_names = ["mock-coach", "mock-someone-else"]
  }

  expect_failures = [var.credential_writer_user_names]
}

run "prod_names_its_own_writer_and_secrets" {
  command = apply

  variables {
    name_prefix = "debate-prod-caselist"
    environment = "prod"
  }

  assert {
    condition     = aws_ssoadmin_permission_set.credential_writer[0].name == "DebateProdCaselistSecretWriter" && local.password_secret_name == "debate-prod-caselist-tabroom-password"
    error_message = "prod's writer and secrets carry prod's names, which DebateMaintainer's deny on debate-prod-* relies on (ADR-0010 rule 4)."
  }
}

run "no_identity_center_creates_no_permission_set" {
  command = apply

  variables {
    identity_center_instance_arn = null
    identity_store_id            = null
    credential_writer_user_names = []
    deployer_user_names          = []
  }

  assert {
    condition     = length(aws_ssoadmin_permission_set.credential_writer) == 0 && output.credential_writer_permission_set_name == null
    error_message = "Without an Identity Center instance there is no writer permission set."
  }

  assert {
    condition     = length(aws_ssoadmin_permission_set.deployer) == 0 && output.deployer_permission_set_name == null
    error_message = "Without an Identity Center instance there is no deployer permission set either (v1-e40-t03)."
  }
}

# ---------------------------------------------------------------------------------------------
# Apply B: the login task, pinned by digest, and its Wednesday schedule
# ---------------------------------------------------------------------------------------------

run "the_login_task_runs_the_pinned_image_as_the_login_role_every_wednesday" {
  command = apply

  variables {
    image_digest = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
  }

  assert {
    condition     = jsondecode(aws_ecs_task_definition.login[0].container_definitions)[0].image == "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-caselist-run@sha256:1111111111111111111111111111111111111111111111111111111111111111"
    error_message = "The login task runs the image by digest, never a tag."
  }

  assert {
    condition = (
      jsondecode(aws_ecs_task_definition.login[0].container_definitions)[0].entryPoint == ["debate-research"]
      && jsondecode(aws_ecs_task_definition.login[0].container_definitions)[0].command == ["--json", "caselist", "auth", "renew"]
    )
    error_message = "The login task's command is `debate-research caselist auth renew`, fixed in the definition."
  }

  assert {
    condition     = length(jsondecode(aws_ecs_task_definition.login[0].container_definitions)) == 1 && !can(jsondecode(aws_ecs_task_definition.login[0].container_definitions)[0].secrets)
    error_message = "No secret reaches the task through ECS's `secrets` field (ADR-0020 (2))."
  }

  assert {
    condition = alltrue([
      for variable in jsondecode(aws_ecs_task_definition.login[0].container_definitions)[0].environment :
      !strcontains(lower(variable.name), "password") || endswith(variable.name, "_SECRET_ID")
    ])
    error_message = "The task's environment names a secret at most, never holds one."
  }

  assert {
    condition     = aws_ecs_task_definition.login[0].task_role_arn == "arn:aws:iam::111122223333:role/debate-mock-caselist-login" && aws_ecs_task_definition.login[0].execution_role_arn == "arn:aws:iam::111122223333:role/debate-mock-caselist-login-execution"
    error_message = "The login task's task role is the login role; its execution role is its own and a different role."
  }

  assert {
    condition = alltrue([
      for action in flatten([for statement in jsondecode(aws_iam_role_policy.login_execution[0].policy).Statement : statement.Action]) :
      !startswith(action, "secretsmanager:") && !startswith(action, "kms:")
    ])
    error_message = "The execution role reads no secret and uses no key."
  }

  assert {
    condition = (
      aws_scheduler_schedule.login[0].schedule_expression == "cron(0 3 ? * WED *)"
      && aws_scheduler_schedule.login[0].schedule_expression_timezone == "America/Chicago"
      && aws_scheduler_schedule.login[0].state == "ENABLED"
    )
    error_message = "The login runs every Wednesday at 03:00 America/Chicago (ADR-0020 (2))."
  }

  assert {
    condition     = aws_scheduler_schedule.login[0].target[0].retry_policy[0].maximum_retry_attempts == 0
    error_message = "The schedule never retries: a refused login is not tried twice in a week."
  }

  assert {
    condition = (
      aws_scheduler_schedule.login[0].target[0].ecs_parameters[0].task_definition_arn == "arn:aws:ecs:us-east-1:111122223333:task-definition/debate-mock-caselist-login:7"
      && aws_scheduler_schedule.login[0].target[0].ecs_parameters[0].enable_execute_command == false
      && aws_scheduler_schedule.login[0].target[0].ecs_parameters[0].network_configuration[0].assign_public_ip == true
    )
    error_message = "The schedule starts this task definition, with no shell into it, on a public address (ADR-0020 (1) 5 and 7)."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_iam_role_policy.scheduler[0].policy).Statement : statement.Resource
      if statement.Action == "iam:PassRole"
      ])) == toset([
      "arn:aws:iam::111122223333:role/debate-mock-caselist-login",
      "arn:aws:iam::111122223333:role/debate-mock-caselist-login-execution",
    ])
    error_message = "The scheduler role passes the login task's two roles and no other."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_iam_role_policy.scheduler[0].policy).Statement :
      statement.Action == "ecs:RunTask" && statement.Resource == "arn:aws:ecs:us-east-1:111122223333:task-definition/debate-mock-caselist-login:7"
      && statement.Condition.ArnEquals["ecs:cluster"] == "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
    ])
    error_message = "The scheduler role runs this one task definition revision, on the run's cluster only."
  }

  assert {
    # The whole condition, compared as one value, so a wildcard ArnLike, a dropped
    # aws:SourceAccount or the schedule's own ARN each make this false rather than an error.
    condition = (
      length(jsondecode(aws_iam_role.scheduler[0].assume_role_policy).Statement) == 1
      && jsondecode(aws_iam_role.scheduler[0].assume_role_policy).Statement[0].Principal.Service == "scheduler.amazonaws.com"
      && jsondecode(aws_iam_role.scheduler[0].assume_role_policy).Statement[0].Condition == {
        StringEquals = {
          "aws:SourceAccount" = "111122223333"
          "aws:SourceArn"     = "arn:aws:scheduler:us-east-1:111122223333:schedule-group/debate-mock-caselist-login"
        }
      }
    )
    error_message = "Only the login schedule's own group may assume the scheduler role: aws:SourceArn is exactly that group's ARN, under StringEquals with aws:SourceAccount (Scheduler's confused-deputy rule)."
  }

  assert {
    condition = (
      aws_scheduler_schedule_group.login[0].name == "debate-mock-caselist-login"
      && aws_scheduler_schedule.login[0].group_name == aws_scheduler_schedule_group.login[0].name
    )
    error_message = "The login's schedule sits in its own group, debate-<env>-caselist-login, never the default group."
  }
}

run "a_login_image_named_by_tag_is_refused" {
  command = plan

  variables {
    image_digest = "latest"
  }

  expect_failures = [var.image_digest]
}

run "a_paused_schedule_is_disabled_not_destroyed" {
  command = apply

  variables {
    login_schedule_enabled = false
    image_digest           = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
  }

  assert {
    condition     = length(aws_scheduler_schedule.login) == 1 && aws_scheduler_schedule.login[0].state == "DISABLED"
    error_message = "login_schedule_enabled = false keeps the schedule, disabled."
  }
}

# ---------------------------------------------------------------------------------------------
# Break-glass creates the secrets: it may validate the key, and decrypts no stored version
# ---------------------------------------------------------------------------------------------
#
# CreateSecret has Secrets Manager validate the caller's access to the key with a GenerateDataKey
# and a Decrypt as the caller, SecretVersionId "RequestToValidateKeyAccess" ("Validating access to
# the KMS key", https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html).
# The apply runs as break-glass, and its first run in dev was refused at that GenerateDataKey.

run "break_glass_may_only_validate_the_key_and_decrypts_no_stored_version" {
  command = apply

  assert {
    # 1. Exactly two break-glass grants beyond administration: GenerateDataKey and Decrypt, each
    #    with the validation version id, through Secrets Manager, for the two secrets.
    condition = toset([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      jsonencode({
        action    = statement.Action
        principal = statement.Principal.AWS
        service   = try(statement.Condition.StringEquals["kms:ViaService"], null)
        version   = try(statement.Condition.StringEquals["kms:EncryptionContext:SecretVersionId"], null)
        secrets   = try(toset(flatten([statement.Condition.StringLike["kms:EncryptionContext:SecretARN"]])), null)
        keys      = sort(keys(statement.Condition))
      })
      if statement.Effect == "Allow" && try(statement.Condition.ArnLike["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*" && statement.Sid != "KeyAdministrationByBreakGlassOnly"
      ]) == toset([for action in ["kms:GenerateDataKey", "kms:Decrypt"] : jsonencode({
        action    = action
        principal = "arn:aws:iam::111122223333:root"
        service   = "secretsmanager.us-east-1.amazonaws.com"
        version   = "RequestToValidateKeyAccess"
        secrets = toset([
          "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-??????",
          "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-??????",
        ])
        keys = ["ArnLike", "StringEquals", "StringLike"]
    })])
    error_message = "Break-glass may GenerateDataKey and Decrypt only to validate the key: SecretVersionId RequestToValidateKeyAccess, through Secrets Manager, for the two secrets."
  }

  assert {
    # 2. Break-glass is denied any decrypt with another SecretVersionId, or none, for any secret.
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["kms:Decrypt"]
      && try(statement.Condition.ArnLike["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"
      && try(statement.Condition.StringNotEquals["kms:EncryptionContext:SecretVersionId"], "") == "RequestToValidateKeyAccess"
      && toset(keys(statement.Condition)) == toset(["ArnLike", "StringNotEquals"])
    ])
    error_message = "The key policy must deny break-glass every decrypt whose SecretVersionId is not RequestToValidateKeyAccess, whatever the secret."
  }

  assert {
    # 3. The login role alone decrypts the password and the run role alone the token: of the
    #    decrypt allows that do not demand the validation version id, those two and no others.
    condition = toset([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      "${statement.Principal.AWS} ${jsonencode(try(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"], null))}"
      if statement.Effect == "Allow" && contains(flatten([statement.Action]), "kms:Decrypt")
      && try(statement.Condition.StringEquals["kms:EncryptionContext:SecretVersionId"], null) != "RequestToValidateKeyAccess"
      ]) == toset([
      "arn:aws:iam::111122223333:role/debate-mock-caselist-login \"arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-??????\"",
      "arn:aws:iam::111122223333:role/debate-mock-caselist-run \"arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-??????\"",
    ])
    error_message = "Only the login role may decrypt a stored password, and only the run role a stored token."
  }

  assert {
    # 4. No other principal gains a decrypt: across every decrypt deny, the only principals exempted
    #    are the two roles (ArnNotEquals) and break-glass's pattern (ArnNotLike), which the deny in 2
    #    holds to the validation.
    condition = (
      toset(flatten([
        for statement in jsondecode(aws_kms_key.credentials.policy).Statement : flatten([try(statement.Condition.ArnNotEquals["aws:PrincipalArn"], [])])
        if statement.Effect == "Deny" && contains(flatten([statement.Action]), "kms:Decrypt")
      ])) == toset(["arn:aws:iam::111122223333:role/debate-mock-caselist-login", "arn:aws:iam::111122223333:role/debate-mock-caselist-run"])
      && toset(flatten([
        for statement in jsondecode(aws_kms_key.credentials.policy).Statement : flatten([try(statement.Condition.ArnNotLike["aws:PrincipalArn"], [])])
        if statement.Effect == "Deny" && contains(flatten([statement.Action]), "kms:Decrypt")
      ])) == toset(["arn:aws:iam::111122223333:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_DebateBreakGlassAdmin_*"])
      && length([
        for statement in jsondecode(aws_kms_key.credentials.policy).Statement : statement
        if statement.Effect == "Deny" && contains(flatten([statement.Action]), "kms:Decrypt") && can(statement.Condition.ArnNotEquals)
      ]) == 3
      && alltrue([
        for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
        !anytrue([for action in flatten([statement.Action]) : startswith(action, "kms:*") || startswith(action, "kms:ReEncrypt") || action == "kms:CreateGrant"])
        if statement.Effect == "Allow"
      ])
    )
    error_message = "Only the login and run roles, and break-glass's validation, may escape a decrypt deny; three such denies, and no Allow of a wildcard, a grant or a re-encryption."
  }
}

# ---------------------------------------------------------------------------------------------
# The run (v1-e40-t03): its network, cluster and repository, which need no image
# ---------------------------------------------------------------------------------------------

run "the_runs_network_has_no_inbound_rule_and_outbound_https_only" {
  command = apply

  assert {
    condition     = length(aws_security_group.run.ingress) == 0
    error_message = "The tasks' security group has no inbound rule (ADR-0020 (1) 5)."
  }

  assert {
    condition = jsonencode([
      for rule in aws_security_group.run.egress : {
        protocol = rule.protocol, from = rule.from_port, to = rule.to_port, cidrs = rule.cidr_blocks
        # Unset, these are null under the mocked provider and empty from AWS; either is none.
        ipv6         = try(length(rule.ipv6_cidr_blocks), 0), groups = try(length(rule.security_groups), 0)
        prefix_lists = try(length(rule.prefix_list_ids), 0), self = rule.self == true
      }
      ]) == jsonencode([{
        protocol = "tcp", from = 443, to = 443, cidrs = ["0.0.0.0/0"], ipv6 = 0, groups = 0, prefix_lists = 0, self = false
    }])
    error_message = "The tasks may reach out on HTTPS and nothing else."
  }

  assert {
    condition     = length(aws_default_security_group.run.ingress) == 0 && length(aws_default_security_group.run.egress) == 0
    error_message = "The VPC's default security group is held with no rule, so nothing in the VPC has an inbound rule."
  }

  assert {
    condition     = toset([for subnet in aws_subnet.public : subnet.availability_zone]) == toset(["us-east-1a", "us-east-1b"]) && toset([for subnet in aws_subnet.public : subnet.cidr_block]) == toset(["10.40.0.0/25", "10.40.0.128/25"])
    error_message = "Two public subnets, in the first two zones by name, each half of the VPC."
  }

  assert {
    condition     = aws_route.public_internet.destination_cidr_block == "0.0.0.0/0" && aws_route.public_internet.gateway_id == aws_internet_gateway.run.id && length(aws_route_table_association.public) == 2
    error_message = "Both subnets route the internet through the internet gateway: they are public."
  }

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway" && aws_vpc_endpoint.s3.service_name == "com.amazonaws.us-east-1.s3" && toset(aws_vpc_endpoint.s3.route_table_ids) == toset([aws_route_table.public.id])
    error_message = "An S3 gateway endpoint on the subnets' route table keeps bucket traffic inside AWS."
  }

  assert {
    condition     = aws_ecs_cluster.run.name == "debate-mock-caselist-run" && one([for setting in aws_ecs_cluster.run.setting : setting.value if setting.name == "containerInsights"]) == "disabled"
    error_message = "The run's cluster is debate-<env>-caselist-run, without Container Insights (ADR-0020, What E40 must not build)."
  }

  assert {
    condition = (
      aws_ecr_repository.run.name == "debate-mock-caselist-run"
      && aws_ecr_repository.run.image_tag_mutability == "IMMUTABLE"
      && aws_ecr_repository.run.image_scanning_configuration[0].scan_on_push
      && aws_ecr_repository.run.encryption_configuration[0].encryption_type == "KMS"
    )
    error_message = "The repository has immutable tags, a scan on push and KMS encryption, as v2-e10-t05's ecr module will (ADR-0020, What V2 replaces)."
  }

  assert {
    condition     = length(aws_ecs_task_definition.run) == 0 && length(aws_scheduler_schedule.run) == 0 && length(aws_iam_role.run_scheduler) == 0 && output.run_schedule_name == null
    error_message = "Without image_digest there is no run task definition and no run schedule: they need a pushed image."
  }
}

# ---------------------------------------------------------------------------------------------
# The run role: the everyday evidence permissions and the token, nothing more
# ---------------------------------------------------------------------------------------------

run "the_run_role_holds_the_everyday_evidence_permissions_and_the_token_and_nothing_more" {
  command = apply

  assert {
    condition     = aws_iam_role_policies_exclusive.run.policy_names == toset(["caselist-credentials", "everyday-evidence"]) && length(aws_iam_role_policy_attachments_exclusive.run.policy_arns) == 0
    error_message = "The run role holds exactly its credentials grant and the everyday evidence permissions, held exclusive, with no managed policy."
  }

  assert {
    condition     = aws_iam_role_policy.run_evidence.policy == var.evidence_policy_json
    error_message = "The run's evidence policy is the everyday document itself, not a copy that could drift from it."
  }

  assert {
    condition = toset(flatten([
      for policy in [aws_iam_role_policy.run_credentials.policy, aws_iam_role_policy.run_evidence.policy] : [
        for statement in jsondecode(policy).Statement : flatten([statement.Action]) if statement.Effect == "Allow"
      ]
      ])) == toset([
      "secretsmanager:GetSecretValue", "kms:Decrypt",
      "s3:ListBucket", "s3:ListBucketVersions", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject",
      "s3:GetObjectTagging", "s3:PutObjectTagging", "kms:Encrypt", "kms:GenerateDataKey",
    ])
    error_message = "The run role may do the everyday evidence actions and read the token, and nothing else."
  }

  assert {
    condition = alltrue([
      for policy in [aws_iam_role_policy.run_credentials.policy, aws_iam_role_policy.run_evidence.policy] :
      alltrue([
        for statement in jsondecode(policy).Statement :
        length(setintersection(toset(flatten([statement.Action])), toset(["s3:DeleteObject", "s3:DeleteObjectVersion", "s3:*", "*"]))) == 0
      ])
    ])
    error_message = "The run role may not delete an object or a version: a delete is a takedown, and takedowns use EvidenceRemoval."
  }

  assert {
    condition = alltrue([
      for policy in [aws_iam_role_policy.run_credentials.policy, aws_iam_role_policy.run_evidence.policy] :
      !strcontains(policy, "tabroom-password")
    ])
    error_message = "Neither of the run role's policies names the password secret."
  }

  assert {
    condition = flatten([
      for policy in [aws_iam_role_policy.run_credentials.policy, aws_iam_role_policy.run_evidence.policy] : [
        for statement in jsondecode(policy).Statement : flatten([statement.Resource])
        if contains(flatten([statement.Action]), "secretsmanager:GetSecretValue")
      ]
    ]) == ["arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-ToKeNx"]
    error_message = "The run role reads one secret, the token."
  }
}

run "an_evidence_policy_that_deletes_is_refused" {
  command = plan

  variables {
    evidence_policy_json = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:DeleteObject", "s3:DeleteObjectVersion"]
        Resource = "arn:aws:s3:::debate-mock-evidence-00000000/*"
      }]
    })
  }

  expect_failures = [var.evidence_policy_json]
}

run "an_evidence_policy_with_a_wildcard_action_is_refused" {
  command = plan

  variables {
    evidence_policy_json = jsonencode({
      Version   = "2012-10-17"
      Statement = [{ Effect = "Allow", Action = "s3:*", Resource = "arn:aws:s3:::debate-mock-evidence-00000000/*" }]
    })
  }

  expect_failures = [var.evidence_policy_json]
}

run "an_evidence_policy_naming_another_bucket_is_refused" {
  command = plan

  variables {
    evidence_policy_json = jsonencode({
      Version   = "2012-10-17"
      Statement = [{ Effect = "Allow", Action = "s3:GetObject", Resource = "arn:aws:s3:::debate-prod-evidence-00000000/*" }]
    })
  }

  expect_failures = [var.evidence_policy_json]
}

run "an_evidence_policy_using_the_credentials_key_is_refused" {
  command = plan

  variables {
    evidence_policy_json = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = "arn:aws:kms:us-east-1:111122223333:key/00000000-0000-0000-0000-00000000c0de"
      }]
    })
  }

  expect_failures = [var.evidence_policy_json]
}

run "an_evidence_policy_reading_the_password_is_refused" {
  command = plan

  variables {
    evidence_policy_json = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-PaSsWd"
      }]
    })
  }

  expect_failures = [var.evidence_policy_json]
}

# ---------------------------------------------------------------------------------------------
# The run task and its schedule, once an image is pushed
# ---------------------------------------------------------------------------------------------

run "the_run_task_runs_the_pinned_image_as_the_run_role_under_its_deadline" {
  command = apply

  variables {
    image_digest = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
  }

  assert {
    condition     = jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].image == "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-caselist-run@sha256:2222222222222222222222222222222222222222222222222222222222222222"
    error_message = "The run task runs its repository's image by digest, never a tag."
  }

  assert {
    condition = (
      aws_ecs_task_definition.run[0].cpu == "8192" && aws_ecs_task_definition.run[0].memory == "16384"
      && aws_ecs_task_definition.run[0].ephemeral_storage[0].size_in_gib == 100
      && aws_ecs_task_definition.run[0].runtime_platform[0].cpu_architecture == "ARM64"
      && aws_ecs_task_definition.run[0].requires_compatibilities == toset(["FARGATE"])
    )
    error_message = "Fargate, 8 vCPU, 16 GB, 100 GiB of ephemeral storage, arm64 (ADR-0020 (1) 2)."
  }

  assert {
    condition = (
      jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].entryPoint == ["timeout", "--signal=TERM", "--kill-after=120s", "6h", "debate-research"]
      && jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].command == ["--json", "caselist", "pull"]
      && jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].stopTimeout == 120
      && jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].linuxParameters.initProcessEnabled
    )
    error_message = "The command is `debate-research --json caselist pull`, naming no caselist, under a 6-hour deadline in the container (ADR-0020 (1) 6, (5))."
  }

  assert {
    condition = {
      for variable in jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].environment : variable.name => variable.value
      } == {
      DEBATE_ENV                             = "dev"
      DEBATE_ALLOW_NETWORK                   = "true"
      DEBATE_CASELIST__API_ENABLED           = "true"
      DEBATE_CASELIST__TOKEN_BACKEND         = "secretsmanager"
      DEBATE_CASELIST__TOKEN_SECRET_ID       = "debate-mock-caselist-token"
      DEBATE_CASELIST__SECRETS_REGION        = "us-east-1"
      DEBATE_STORAGE__DATA_DIR               = "/var/lib/debate-research/dev"
      DEBATE_STORAGE__S3__AWS_PROFILE        = ""
      DEBATE_STORAGE__VOLUME_WARNING_PERCENT = "70"
      DEBATE_PARSE__WORKERS                  = "8"
      AWS_REGION                             = "us-east-1"
    }
    error_message = "The run's environment is names and switches (ADR-0020 (5)): the token store's Secrets Manager backend, no AWS profile, 8 parse workers, the 70% volume warning. No secret, and no password secret's name."
  }

  assert {
    condition     = !can(jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].secrets) && !strcontains(aws_ecs_task_definition.run[0].container_definitions, "password")
    error_message = "No secret reaches the run through ECS's `secrets` field, and nothing in its definition names the password."
  }

  assert {
    condition     = aws_ecs_task_definition.run[0].task_role_arn == "arn:aws:iam::111122223333:role/debate-mock-caselist-run" && aws_ecs_task_definition.run[0].execution_role_arn == "arn:aws:iam::111122223333:role/debate-mock-caselist-run-execution"
    error_message = "The run task's role is the run role; its execution role is its own."
  }

  assert {
    condition = alltrue([
      for action in flatten([for statement in jsondecode(aws_iam_role_policy.run_execution.policy).Statement : statement.Action]) :
      !startswith(action, "secretsmanager:") && !startswith(action, "kms:") && !startswith(action, "s3:")
    ])
    error_message = "The run's execution role pulls the image and writes the log: no secret, no key, no bucket."
  }

  assert {
    condition     = jsondecode(aws_ecs_task_definition.login[0].container_definitions)[0].image == jsondecode(aws_ecs_task_definition.run[0].container_definitions)[0].image
    error_message = "The login and the run run the same image, by the same digest."
  }
}

run "the_run_schedule_starts_after_the_login_and_is_disabled_by_default" {
  command = apply

  variables {
    image_digest = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
  }

  assert {
    condition = (
      aws_scheduler_schedule.run[0].schedule_expression == "cron(0 6 ? * WED *)"
      && aws_scheduler_schedule.run[0].schedule_expression_timezone == "America/Chicago"
    )
    error_message = "The run starts every Wednesday at 06:00 America/Chicago (ADR-0020 (2), When the login runs)."
  }

  assert {
    # Field by field: the same zone, the same day of the week, a later hour, so daylight saving
    # moves both and the run never starts before the login that renews its token.
    condition = (
      aws_scheduler_schedule.run[0].schedule_expression_timezone == aws_scheduler_schedule.login[0].schedule_expression_timezone
      && slice(split(" ", trimsuffix(trimprefix(aws_scheduler_schedule.run[0].schedule_expression, "cron("), ")")), 2, 6) == slice(split(" ", trimsuffix(trimprefix(aws_scheduler_schedule.login[0].schedule_expression, "cron("), ")")), 2, 6)
      && tonumber(split(" ", trimprefix(aws_scheduler_schedule.run[0].schedule_expression, "cron("))[1]) > tonumber(split(" ", trimprefix(aws_scheduler_schedule.login[0].schedule_expression, "cron("))[1])
    )
    error_message = "The run must start after the Wednesday 03:00 America/Chicago login, never before it."
  }

  assert {
    condition     = aws_scheduler_schedule.run[0].state == "DISABLED" && aws_scheduler_schedule.login[0].state == "ENABLED" && output.run_schedule_state == "DISABLED"
    error_message = "The run's schedule ships disabled until v1-e40-t04's bucket mode and lock (the PM's ruling); the login's is enabled as t02 left it."
  }

  assert {
    condition = (
      aws_scheduler_schedule.run[0].target[0].arn == "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
      && aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].task_definition_arn == "arn:aws:ecs:us-east-1:111122223333:task-definition/debate-mock-caselist-run:3"
      && aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].launch_type == "FARGATE"
      && aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].platform_version == "LATEST"
      && aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].enable_execute_command == false
      && aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].network_configuration[0].assign_public_ip == true
      && aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].network_configuration[0].security_groups == toset(["sg-0000000000000000a"])
      && length(aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].network_configuration[0].subnets) > 0
    )
    error_message = "The schedule starts Terraform's revision of the run on the run's cluster: on-demand Fargate, platform 1.4.0 or later, no ECS Exec, a public address, the run's security group."
  }

  assert {
    condition     = aws_scheduler_schedule.run[0].target[0].ecs_parameters[0].network_configuration[0].subnets == aws_scheduler_schedule.login[0].target[0].ecs_parameters[0].network_configuration[0].subnets
    error_message = "The login runs in the run's subnets: one network for both tasks."
  }

  assert {
    condition     = aws_scheduler_schedule.run[0].target[0].retry_policy[0].maximum_retry_attempts == 0 && aws_scheduler_schedule.run[0].flexible_time_window[0].mode == "OFF"
    error_message = "Never twice in a week, and never late by a window: a second run would spend the week's downloads again."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_iam_role_policy.run_scheduler[0].policy).Statement : statement.Resource
      if statement.Action == "iam:PassRole"
      ])) == toset([
      "arn:aws:iam::111122223333:role/debate-mock-caselist-run",
      "arn:aws:iam::111122223333:role/debate-mock-caselist-run-execution",
    ])
    error_message = "The run's scheduler passes the run's two roles and no other."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_iam_role_policy.run_scheduler[0].policy).Statement :
      try(statement.Condition.StringEquals["iam:PassedToService"], "") == "ecs-tasks.amazonaws.com"
      if statement.Action == "iam:PassRole"
    ])
    error_message = "The run's scheduler passes the run's roles to ECS tasks and to nothing else (iam:PassedToService)."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_iam_role_policy.run_scheduler[0].policy).Statement :
      statement.Action == "ecs:RunTask" && statement.Resource == "arn:aws:ecs:us-east-1:111122223333:task-definition/debate-mock-caselist-run:3"
      && try(statement.Condition.ArnEquals["ecs:cluster"], "") == "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
    ])
    error_message = "The run's scheduler runs this one revision, on the run's cluster only."
  }

  assert {
    condition = (
      length(jsondecode(aws_iam_role.run_scheduler[0].assume_role_policy).Statement) == 1
      && jsondecode(aws_iam_role.run_scheduler[0].assume_role_policy).Statement[0].Principal.Service == "scheduler.amazonaws.com"
      && jsondecode(aws_iam_role.run_scheduler[0].assume_role_policy).Statement[0].Condition == {
        StringEquals = {
          "aws:SourceAccount" = "111122223333"
          "aws:SourceArn"     = "arn:aws:scheduler:us-east-1:111122223333:schedule-group/debate-mock-caselist-run"
        }
      }
    )
    error_message = "Only the run schedule's own group may assume the run's scheduler role: aws:SourceArn is exactly that group's ARN, under StringEquals with aws:SourceAccount (Scheduler's confused-deputy rule)."
  }

  assert {
    condition = (
      aws_scheduler_schedule_group.run[0].name == "debate-mock-caselist-run"
      && aws_scheduler_schedule.run[0].group_name == aws_scheduler_schedule_group.run[0].name
      && aws_scheduler_schedule.run[0].group_name != aws_scheduler_schedule.login[0].group_name
    )
    error_message = "The run's schedule sits in its own group, debate-<env>-caselist-run: not the login's group, and never the default group."
  }
}

run "run_schedule_enabled_turns_the_run_on" {
  command = apply

  variables {
    image_digest         = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
    run_schedule_enabled = true
  }

  assert {
    condition     = aws_scheduler_schedule.run[0].state == "ENABLED"
    error_message = "run_schedule_enabled = true enables the run's schedule (the cutover, v1-e40-t06)."
  }
}

# ---------------------------------------------------------------------------------------------
# Debate<Env>CaselistRunDeployer: passes the run's roles, never the login's
# ---------------------------------------------------------------------------------------------

run "the_deployer_passes_the_run_roles_and_never_the_login_roles" {
  command = apply

  assert {
    condition     = aws_ssoadmin_permission_set.deployer[0].name == "DebateDevCaselistRunDeployer" && length(aws_ssoadmin_permission_set.deployer[0].name) <= 32 && aws_ssoadmin_permission_set.deployer[0].session_duration == "PT1H"
    error_message = "The deployer is DebateDevCaselistRunDeployer, inside Identity Center's 32 characters, with one-hour sessions."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.deployer[0].inline_policy).Statement : flatten([statement.Resource])
      if statement.Effect == "Allow" && contains(flatten([statement.Action]), "iam:PassRole")
      ])) == toset([
      "arn:aws:iam::111122223333:role/debate-mock-caselist-run",
      "arn:aws:iam::111122223333:role/debate-mock-caselist-run-execution",
    ])
    error_message = "The deployer may pass the run role and the run's execution role, and no other role."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.deployer[0].inline_policy).Statement :
      try(statement.Condition.StringEquals["iam:PassedToService"], "") == "ecs-tasks.amazonaws.com"
      if statement.Effect == "Allow" && contains(flatten([statement.Action]), "iam:PassRole")
    ])
    error_message = "The deployer passes the run's roles to ECS tasks and to nothing else (iam:PassedToService)."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.deployer[0].inline_policy).Statement :
      statement.Effect == "Deny" && contains(flatten([statement.Action]), "iam:PassRole")
      && length(setsubtract(toset([
        "arn:aws:iam::111122223333:role/debate-mock-caselist-login",
        "arn:aws:iam::111122223333:role/debate-mock-caselist-login-execution",
      ]), toset(flatten([statement.Resource])))) == 0
      && !can(statement.Condition)
    ])
    error_message = "The deployer is refused, outright, passing the login role or the login's execution role (ADR-0020 (2), Who can make the login role run)."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.deployer[0].inline_policy).Statement :
      alltrue([for action in flatten([statement.Action]) : !contains(["*", "iam:*", "ecs:*", "ecr:*"], action) && !startswith(action, "secretsmanager:") && !startswith(action, "kms:") && !startswith(action, "s3:")])
      if statement.Effect == "Allow"
    ])
    error_message = "The deployer reads no secret, uses no key, touches no bucket and holds no wildcard."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.deployer[0].inline_policy).Statement :
      statement.Action == "ecs:RunTask" && statement.Resource == "arn:aws:ecs:us-east-1:111122223333:task-definition/debate-mock-caselist-run:*"
      && try(statement.Condition.ArnEquals["ecs:cluster"], "") == "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
    ])
    error_message = "The deployer starts the run's family, on the run's cluster, and nothing else: never the login's family."
  }

  assert {
    condition     = length(aws_ssoadmin_account_assignment.deployer) == 1 && output.deployer_profile_name == "debate-mock-caselist-run-deployer"
    error_message = "The deployer is assigned to the user named, and its profile is debate-<env>-caselist-run-deployer."
  }
}

run "prod_names_its_own_deployer_inside_thirty_two_characters" {
  command = apply

  variables {
    name_prefix = "debate-prod-caselist"
    environment = "prod"
  }

  assert {
    condition     = aws_ssoadmin_permission_set.deployer[0].name == "DebateProdCaselistRunDeployer" && length(aws_ssoadmin_permission_set.deployer[0].name) <= 32
    error_message = "prod's deployer is DebateProdCaselistRunDeployer, 29 characters (v1-e40-t02's lesson: Identity Center allows 32)."
  }
}

# v1-e40-t04 ac4 (the PM's ruling of 2026-10-23): the run, its role and every command but a removal
# never delete. The run role's policies may not allow s3:DeleteObject or s3:DeleteObjectVersion by
# any spelling IAM matches: the names themselves, a wildcard over them (s3:Delete*, s3:*Object*,
# s3:*), or an Allow with NotAction, which allows every action it does not name. The run above it
# lists the role's actions exactly; this one is the rule, so a policy that adds an action and a
# test that adds it to that list still cannot add a delete.
run "the_run_role_never_deletes" {
  command = apply

  assert {
    condition = length(flatten([
      for policy in [aws_iam_role_policy.run_credentials.policy, aws_iam_role_policy.run_evidence.policy] : [
        for statement in jsondecode(policy).Statement : [
          for action in flatten([try(statement.Action, [])]) : action
          if anytrue([
            for deleting in ["s3:DeleteObject", "s3:DeleteObjectVersion"] :
            can(regex("^(?i)${replace(replace(action, "*", ".*"), "?", ".")}$", deleting))
          ])
        ] if statement.Effect == "Allow"
      ]
    ])) == 0
    error_message = "The run role may not delete an object or a version, by name or by a wildcard over either: a delete is a removal's, under the EvidenceRemoval credential (ADR-0020 (3))."
  }

  assert {
    condition = alltrue(flatten([
      for policy in [aws_iam_role_policy.run_credentials.policy, aws_iam_role_policy.run_evidence.policy] : [
        for statement in jsondecode(policy).Statement : !(statement.Effect == "Allow" && can(statement.NotAction))
      ]
    ]))
    error_message = "No Allow statement of the run role's may use NotAction: it allows every action it does not name, deletes included."
  }
}

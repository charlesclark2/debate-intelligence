# Offline tests for the caselist_run module: the credentials of ADR-0020 (2) and the scheduled login.
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
}

# ---------------------------------------------------------------------------------------------
# Apply A: the credentials, the roles and the writer, with no network and no login task
# ---------------------------------------------------------------------------------------------

run "credentials_apply_creates_no_login_task" {
  command = apply

  assert {
    condition     = length(aws_ecs_task_definition.login) == 0 && length(aws_scheduler_schedule.login) == 0 && length(aws_iam_role.scheduler) == 0
    error_message = "Without login_task, the module must create the credentials only: no task definition, no schedule, no scheduler role (apply A)."
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
    # Every Allow of kms:Decrypt, by principal, principal pattern and the secret its context names.
    # JSON-encoded, so a statement of any shape compares rather than failing to.
    condition = toset([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      jsonencode({
        principal = statement.Principal.AWS
        pattern   = try(statement.Condition.ArnLike["aws:PrincipalArn"], null)
        secret    = try(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"], null)
      })
      if statement.Effect == "Allow" && contains(flatten([statement.Action]), "kms:Decrypt")
      ]) == toset([
      jsonencode({
        principal = "arn:aws:iam::111122223333:role/debate-mock-caselist-login"
        pattern   = null
        secret    = "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-??????"
      }),
      jsonencode({
        principal = "arn:aws:iam::111122223333:role/debate-mock-caselist-run"
        pattern   = null
        secret    = "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-??????"
      }),
    ])
    error_message = "The key may let the login role decrypt the password and the run role the token, and nobody else decrypt anything."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["kms:Decrypt"]
      && try(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"], "") == "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-tabroom-password-??????"
      && try(statement.Condition.ArnNotEquals["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/debate-mock-caselist-login"
    ])
    error_message = "The key policy must deny decrypting the password to every principal but the login role."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["kms:Decrypt"]
      && try(statement.Condition.StringLike["kms:EncryptionContext:SecretARN"], "") == "arn:aws:secretsmanager:us-east-1:111122223333:secret:debate-mock-caselist-token-??????"
      && try(statement.Condition.ArnNotEquals["aws:PrincipalArn"], "") == "arn:aws:iam::111122223333:role/debate-mock-caselist-run"
    ])
    error_message = "The key policy must deny decrypting the token to every principal but the run role."
  }

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_kms_key.credentials.policy).Statement :
      statement.Effect == "Deny" && statement.Principal.AWS == "*" && flatten([statement.Action]) == ["kms:Decrypt"]
      && !can(statement.Condition.StringLike)
      && toset(try(statement.Condition.ArnNotEquals["aws:PrincipalArn"], [])) == toset(["arn:aws:iam::111122223333:role/debate-mock-caselist-login", "arn:aws:iam::111122223333:role/debate-mock-caselist-run"])
    ])
    error_message = "The key policy must deny every decrypt to every principal but the login and run roles (ADR-0020 (2))."
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
  }

  assert {
    condition     = length(aws_ssoadmin_permission_set.credential_writer) == 0 && output.credential_writer_permission_set_name == null
    error_message = "Without an Identity Center instance there is no writer permission set."
  }
}

# ---------------------------------------------------------------------------------------------
# Apply B: the login task, pinned by digest, and its Wednesday schedule
# ---------------------------------------------------------------------------------------------

run "the_login_task_runs_the_pinned_image_as_the_login_role_every_wednesday" {
  command = apply

  variables {
    login_task = {
      cluster_arn        = "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
      subnet_ids         = ["subnet-0000000000000000a", "subnet-0000000000000000b"]
      security_group_ids = ["sg-0000000000000000a"]
      repository_arn     = "arn:aws:ecr:us-east-1:111122223333:repository/debate-mock-caselist-run"
      repository_url     = "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-caselist-run"
      image_digest       = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    }
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
    condition = (
      jsondecode(aws_iam_role.scheduler[0].assume_role_policy).Statement[0].Principal.Service == "scheduler.amazonaws.com"
      && jsondecode(aws_iam_role.scheduler[0].assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceArn"] == "arn:aws:scheduler:us-east-1:111122223333:schedule/default/debate-mock-caselist-login"
    )
    error_message = "Only the login schedule may assume the scheduler role."
  }
}

run "a_login_image_named_by_tag_is_refused" {
  command = plan

  variables {
    login_task = {
      cluster_arn        = "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
      subnet_ids         = ["subnet-0000000000000000a"]
      security_group_ids = ["sg-0000000000000000a"]
      repository_arn     = "arn:aws:ecr:us-east-1:111122223333:repository/debate-mock-caselist-run"
      repository_url     = "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-caselist-run"
      image_digest       = "latest"
    }
  }

  expect_failures = [var.login_task]
}

run "a_paused_schedule_is_disabled_not_destroyed" {
  command = apply

  variables {
    login_schedule_enabled = false
    login_task = {
      cluster_arn        = "arn:aws:ecs:us-east-1:111122223333:cluster/debate-mock-caselist-run"
      subnet_ids         = ["subnet-0000000000000000a"]
      security_group_ids = ["sg-0000000000000000a"]
      repository_arn     = "arn:aws:ecr:us-east-1:111122223333:repository/debate-mock-caselist-run"
      repository_url     = "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-caselist-run"
      image_digest       = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    }
  }

  assert {
    condition     = length(aws_scheduler_schedule.login) == 1 && aws_scheduler_schedule.login[0].state == "DISABLED"
    error_message = "login_schedule_enabled = false keeps the schedule, disabled."
  }
}

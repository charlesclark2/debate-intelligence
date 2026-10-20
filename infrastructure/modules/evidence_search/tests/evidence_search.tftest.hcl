# Offline tests for the evidence_search module, the student search pilot of ADR-0019.
#
# `mock_provider "aws"` means no credentials, no network and no AWS account: Terraform generates
# the values a real provider would return, and everything these runs assert on is either
# configured in the module or mocked here on purpose. Every plan and apply stays an operator step
# (docs/process/working-agreements.md section 2).
#
#   terraform -chdir=infrastructure/modules/evidence_search init -backend=false
#   terraform -chdir=infrastructure/modules/evidence_search test
#
# What these runs hold the module to, and the spec criterion each serves:
#
#   ac2  the evidence buckets keep all four Block Public Access flags and no bucket policy grants
#        CloudFront or the public (the evidence_bucket module, planned with the roots' inputs);
#        the function's role reads only the three key patterns, writes nothing in the bucket,
#        holds no delete on its log groups; the audit group keeps 400 days.
#   ac3  the user pool: no self sign-up, TOTP required, email MFA offered, no SMS configuration,
#        no attribute beyond the username and an optional email.
#   ac5  the role against ADR-0019's role table entry by entry, the app log group and the two
#        parameters included, and no other grant.
#
# No real student name, username or email appears here (task spec: forbidden). The account id,
# user names and addresses below are invented.

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

  mock_data "aws_ecr_image" {
    defaults = {
      image_digest = "sha256:0000000000000000000000000000000000000000000000000000000000000001"
    }
  }

  mock_data "aws_identitystore_user" {
    defaults = {
      # The provider validates the shape of an identity store user id.
      user_id = "a1b2c3d4e5-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    }
  }

  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:us-east-1:111122223333:repository/debate-mock-tub"
      repository_url = "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-tub"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::111122223333:role/debate-mock-tub-function"
    }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:us-east-1:111122223333:function:debate-mock-tub"
    }
  }

  mock_resource "aws_lambda_function_url" {
    defaults = {
      function_url = "https://mockfunctionurlid.lambda-url.us-east-1.on.aws/"
    }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::111122223333:distribution/EMOCKPILOT"
      domain_name    = "dmockpilot.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  mock_resource "aws_cognito_user_pool" {
    defaults = {
      id  = "us-east-1_MOCKPOOL"
      arn = "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_MOCKPOOL"
    }
  }

  mock_resource "aws_cognito_user_pool_domain" {
    defaults = {
      cloudfront_distribution         = "dmocklogin.cloudfront.net"
      cloudfront_distribution_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  mock_resource "aws_cloudwatch_log_stream" {
    defaults = {
      arn = "arn:aws:logs:us-east-1:111122223333:log-group:debate-mock-tub-audit:log-stream:tub-users"
    }
  }

  mock_resource "aws_sesv2_email_identity" {
    defaults = {
      arn = "arn:aws:ses:us-east-1:111122223333:identity/tub.mock.wfbdebate.com"
      # One block element, given as the object it holds: the module configures the block, and
      # the mock fills in its computed tokens.
      dkim_signing_attributes = {
        tokens = ["mocktokenone", "mocktokentwo", "mocktokenthree"]
      }
    }
  }

  mock_resource "aws_ssoadmin_permission_set" {
    defaults = {
      arn = "arn:aws:sso:::permissionSet/ssoins-mock/ps-mock"
    }
  }

  # A superset of the names any run below asks for; the module looks up only its own.
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:111122223333:certificate/mock-pilot"
      domain_validation_options = [
        {
          domain_name           = "tub.dev.wfbdebate.com"
          resource_record_name  = "_mock1.tub.dev.wfbdebate.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock1.acm-validations.aws."
        },
        {
          domain_name           = "auth.tub.dev.wfbdebate.com"
          resource_record_name  = "_mock2.auth.tub.dev.wfbdebate.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock2.acm-validations.aws."
        },
        {
          domain_name           = "tub.wfbdebate.com"
          resource_record_name  = "_mock3.tub.wfbdebate.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock3.acm-validations.aws."
        },
        {
          domain_name           = "auth.tub.wfbdebate.com"
          resource_record_name  = "_mock4.auth.tub.wfbdebate.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock4.acm-validations.aws."
        },
      ]
    }
  }

  # The evidence bucket module's own resources, for the run that plans it beside the pilot.
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::debate-dev-evidence-a7508de8"
    }
  }

  mock_resource "aws_kms_key" {
    defaults = {
      arn    = "arn:aws:kms:us-east-1:111122223333:key/mock-evidence-key"
      key_id = "mock-evidence-key"
    }
  }
}

# The two log groups and the two parameters share a resource type, so their ARNs are set one by
# one: the role's assertions have to tell them apart.
override_resource {
  target = aws_cloudwatch_log_group.audit
  values = {
    arn = "arn:aws:logs:us-east-1:111122223333:log-group:debate-dev-tub-audit"
  }
}

override_resource {
  target = aws_cloudwatch_log_group.app
  values = {
    arn = "arn:aws:logs:us-east-1:111122223333:log-group:debate-dev-tub-app"
  }
}

override_resource {
  target = aws_ssm_parameter.client_secret
  values = {
    arn = "arn:aws:ssm:us-east-1:111122223333:parameter/debate-dev-tub/client-secret"
  }
}

override_resource {
  target = aws_ssm_parameter.cookie_keys
  values = {
    arn = "arn:aws:ssm:us-east-1:111122223333:parameter/debate-dev-tub/cookie-keys"
  }
}

# The default shape is dev, called as envs/dev/evidence_search.tf calls it.
variables {
  name_prefix                = "debate-dev-tub"
  environment                = "dev"
  pilot_host                 = "tub.dev.wfbdebate.com"
  route53_zone_id            = "Z0MOCKCOMZONE"
  evidence_bucket_arn        = "arn:aws:s3:::debate-dev-evidence-a7508de8"
  evidence_kms_key_arn       = "arn:aws:kms:us-east-1:111122223333:key/mock-evidence-key"
  budget_notification_emails = ["maintainer@example.com"]

  # Not module inputs: ADR-0019's role table, written out by hand once, so that the assertions
  # below compare the policy with the decision record rather than with itself.
  expected_role_table = {
    "s3:GetObject" = [
      "arn:aws:s3:::debate-dev-evidence-a7508de8/reports/tub/search/*",
      "arn:aws:s3:::debate-dev-evidence-a7508de8/raw/*",
      "arn:aws:s3:::debate-dev-evidence-a7508de8/manifests/_suppression/suppression-list.jsonl",
    ]
    "kms:Decrypt" = [
      "arn:aws:kms:us-east-1:111122223333:key/mock-evidence-key",
    ]
    "logs:CreateLogStream" = [
      "arn:aws:logs:us-east-1:111122223333:log-group:debate-dev-tub-audit:*",
      "arn:aws:logs:us-east-1:111122223333:log-group:debate-dev-tub-app:*",
    ]
    "logs:PutLogEvents" = [
      "arn:aws:logs:us-east-1:111122223333:log-group:debate-dev-tub-audit:*",
      "arn:aws:logs:us-east-1:111122223333:log-group:debate-dev-tub-app:*",
    ]
    "ssm:GetParameter" = [
      "arn:aws:ssm:us-east-1:111122223333:parameter/debate-dev-tub/client-secret",
      "arn:aws:ssm:us-east-1:111122223333:parameter/debate-dev-tub/cookie-keys",
    ]
  }
}

# ---------------------------------------------------------------------------------------------
# ac2 and ac5: the function's role is ADR-0019's role table, exactly.
# ---------------------------------------------------------------------------------------------

run "function_role_is_the_adr_role_table_entry_by_entry" {
  # Every action the policy grants, with every resource it grants it on, compared with the table.
  # A statement that adds an action, a resource, or a second copy of an action fails here.
  assert {
    condition = {
      for action in distinct(flatten([
        for statement in jsondecode(aws_iam_role_policy.function.policy).Statement : flatten([statement.Action])
      ])) :
      action => toset(flatten([
        for statement in jsondecode(aws_iam_role_policy.function.policy).Statement :
        flatten([statement.Resource]) if contains(flatten([statement.Action]), action)
      ]))
      } == {
      for action, resources in var.expected_role_table : action => toset(resources)
    }
    error_message = "The function's role must grant exactly ADR-0019's role table: GetObject on the three key patterns, Decrypt on the bucket key, CreateLogStream and PutLogEvents on the audit and app groups, GetParameter on the two parameters. Nothing more, nothing less."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement : statement.Effect == "Allow"
    ])
    error_message = "The role's policy is an allow-list; a Deny in it would mean something broader had been granted somewhere."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement :
      !contains(flatten([statement.Resource]), "*")
    ])
    error_message = "No statement in the function's role may name every resource."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement :
      alltrue([for action in flatten([statement.Action]) : !strcontains(action, "*")])
    ])
    error_message = "No action in the function's role may be a wildcard: each is named in the role table."
  }

  assert {
    # The table's first row, said on its own: read three patterns, and not one write, list or
    # version read in the bucket.
    condition = toset(flatten([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement :
      [for action in flatten([statement.Action]) : action if startswith(action, "s3:")]
    ])) == toset(["s3:GetObject"])
    error_message = "The role's only S3 action is GetObject: no GetObjectVersion, no list and no write in the evidence bucket."
  }

  assert {
    condition = alltrue(flatten([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement : [
        for resource in flatten([statement.Resource]) :
        startswith(resource, "${var.evidence_bucket_arn}/") if contains(flatten([statement.Action]), "s3:GetObject")
      ]
    ]))
    error_message = "Every object the role reads must be in its own environment's evidence bucket."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement :
      statement.Condition.StringEquals["kms:ViaService"] == "s3.us-east-1.amazonaws.com"
      if contains(flatten([statement.Action]), "kms:Decrypt")
    ])
    error_message = "The role may decrypt with the bucket key through S3 only (kms:ViaService)."
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement :
      statement if contains(flatten([statement.Action]), "kms:Decrypt") && try(statement.Condition.StringEquals["kms:ViaService"], null) != null
    ]) == 1
    error_message = "Exactly one statement grants kms:Decrypt, and it carries the kms:ViaService condition."
  }

  assert {
    condition = length(flatten([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement : [
        for action in flatten([statement.Action]) : action
        if startswith(action, "logs:") && !contains(["logs:CreateLogStream", "logs:PutLogEvents"], action)
      ]
    ])) == 0
    error_message = "The role may only append to its log groups: no DeleteLogGroup, DeleteLogStream, PutRetentionPolicy or any other logs action."
  }

  assert {
    condition = length(flatten([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement : [
        for action in flatten([statement.Action]) : action if startswith(action, "cognito")
      ]
    ])) == 0
    error_message = "The role holds no Cognito permission: the self-service calls are authorised by the user's access token, the token endpoint by the client secret."
  }
}

run "function_role_has_no_other_grant" {
  assert {
    condition     = aws_iam_role_policies_exclusive.function.policy_names == toset([aws_iam_role_policy.function.name])
    error_message = "The role's one inline policy must be the only one: any other inline policy is removed at the next apply."
  }

  assert {
    condition     = length(aws_iam_role_policy_attachments_exclusive.function.policy_arns) == 0
    error_message = "No managed policy may be attached to the role, AWSLambdaBasicExecutionRole included."
  }

  assert {
    condition     = aws_iam_role_policies_exclusive.function.role_name == aws_iam_role.function.name && aws_iam_role_policy_attachments_exclusive.function.role_name == aws_iam_role.function.name
    error_message = "The exclusive-policy resources must guard the function's own role."
  }

  assert {
    condition = (
      length(jsondecode(aws_iam_role.function.assume_role_policy).Statement) == 1 &&
      jsondecode(aws_iam_role.function.assume_role_policy).Statement[0].Principal.Service == "lambda.amazonaws.com" &&
      jsondecode(aws_iam_role.function.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "111122223333"
    )
    error_message = "Only Lambda, in this account, may assume the function's role."
  }

  assert {
    condition     = aws_lambda_function.pilot.role == aws_iam_role.function.arn
    error_message = "The function must run as this role."
  }
}

run "audit_log_keeps_four_hundred_days_and_the_app_log_thirty" {
  assert {
    condition     = aws_cloudwatch_log_group.audit.name == "debate-dev-tub-audit" && aws_cloudwatch_log_group.audit.retention_in_days == 400
    error_message = "The audit group is debate-<env>-tub-audit, kept 400 days (ADR-0019 (e), gate item 4)."
  }

  assert {
    condition     = aws_cloudwatch_log_group.app.name == "debate-dev-tub-app" && aws_cloudwatch_log_group.app.retention_in_days == 30
    error_message = "The application log is debate-<env>-tub-app, kept 30 days."
  }

  assert {
    condition     = aws_lambda_function.pilot.logging_config[0].log_group == aws_cloudwatch_log_group.app.name
    error_message = "The function's own log goes to the application group, not to /aws/lambda/ and not to the audit group."
  }

  assert {
    condition     = aws_cloudwatch_log_stream.account_changes.log_group_name == aws_cloudwatch_log_group.audit.name && aws_cloudwatch_log_stream.account_changes.name == "tub-users"
    error_message = "The coach's account changes go to their own stream in the audit group."
  }

  assert {
    condition     = aws_lambda_function.pilot.environment[0].variables["TUB_AUDIT_LOG_GROUP"] == "debate-dev-tub-audit"
    error_message = "The function must be told which group is its audit log."
  }
}

# ---------------------------------------------------------------------------------------------
# ac2: the evidence buckets are untouched by the pilot.
# ---------------------------------------------------------------------------------------------

# The evidence bucket module, planned with the inputs envs/dev/evidence_store.tf gives it. The pilot
# module takes only the bucket's ARN and its key's ARN, as strings, and holds no bucket, no public
# access block and no bucket policy of its own; the run after this one shows CloudFront's only
# origin is the function URL. So what these assertions read is what the evidence bucket is with
# the pilot beside it.
run "evidence_bucket_keeps_block_public_access_and_grants_cloudfront_nothing" {
  module {
    source = "../evidence_bucket"
  }

  variables {
    name_prefix                       = "debate-dev-evidence"
    environment                       = "dev"
    bucket_suffix                     = "a7508de8"
    noncurrent_version_retention_days = 30
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.evidence.block_public_acls,
      aws_s3_bucket_public_access_block.evidence.block_public_policy,
      aws_s3_bucket_public_access_block.evidence.ignore_public_acls,
      aws_s3_bucket_public_access_block.evidence.restrict_public_buckets,
    ])
    error_message = "The evidence bucket must keep all four Block Public Access flags (ADR-0019, gate item 3)."
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      statement if statement.Effect == "Allow"
    ]) == 0
    error_message = "The evidence bucket's policy grants nobody anything as the roots call it: no CloudFront, no public, no pilot. The function reads through its role."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_s3_bucket_policy.evidence.policy).Statement :
      !strcontains(jsonencode(statement.Principal), "cloudfront") if statement.Effect == "Allow"
    ])
    error_message = "No bucket policy statement may grant CloudFront anything."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_kms_key.evidence.policy).Statement :
      !strcontains(jsonencode(statement.Principal), "cloudfront") && jsonencode(statement.Principal) != jsonencode({ AWS = "*" }) && jsonencode(statement.Principal) != jsonencode("*")
    ])
    error_message = "The evidence key's policy may grant neither CloudFront nor the public."
  }
}

run "cloudfront_reaches_the_function_url_and_nothing_else" {
  assert {
    condition     = length(aws_cloudfront_distribution.pilot.origin) == 1
    error_message = "The pilot's distribution has one origin."
  }

  assert {
    condition = alltrue([
      for origin in aws_cloudfront_distribution.pilot.origin :
      origin.domain_name == "mockfunctionurlid.lambda-url.us-east-1.on.aws" && origin.origin_access_control_id == aws_cloudfront_origin_access_control.function_url.id
    ])
    error_message = "That origin is the function URL's host, signed by this module's origin access control; never a bucket."
  }

  assert {
    condition = (
      aws_cloudfront_origin_access_control.function_url.origin_access_control_origin_type == "lambda" &&
      aws_cloudfront_origin_access_control.function_url.signing_behavior == "always" &&
      aws_cloudfront_origin_access_control.function_url.signing_protocol == "sigv4"
    )
    error_message = "CloudFront must sign every origin request with SigV4 through an OAC of type lambda (ADR-0019 (a) 2)."
  }

  assert {
    condition     = aws_lambda_function_url.pilot.authorization_type == "AWS_IAM" && aws_lambda_function_url.pilot.invoke_mode == "BUFFERED"
    error_message = "The function URL must require AWS_IAM, so a direct request is refused before the function runs, and buffer its responses."
  }

  assert {
    condition     = length(aws_lambda_function_url.pilot.cors) == 0
    error_message = "The app sends no CORS headers (ADR-0019 (d), CSRF), and neither does the function URL."
  }

  assert {
    condition = (
      aws_lambda_permission.cloudfront_invoke_function_url.action == "lambda:InvokeFunctionUrl" &&
      aws_lambda_permission.cloudfront_invoke_function_url.principal == "cloudfront.amazonaws.com" &&
      aws_lambda_permission.cloudfront_invoke_function_url.source_arn == aws_cloudfront_distribution.pilot.arn &&
      aws_lambda_permission.cloudfront_invoke_function_url.function_url_auth_type == "AWS_IAM"
    )
    error_message = "CloudFront may invoke the function URL only for this environment's distribution."
  }

  assert {
    condition = (
      aws_lambda_permission.cloudfront_invoke_function.action == "lambda:InvokeFunction" &&
      aws_lambda_permission.cloudfront_invoke_function.principal == "cloudfront.amazonaws.com" &&
      aws_lambda_permission.cloudfront_invoke_function.source_arn == aws_cloudfront_distribution.pilot.arn
    )
    error_message = "CloudFront may invoke the function only for this environment's distribution."
  }
}

# ---------------------------------------------------------------------------------------------
# ac3: the user pool.
# ---------------------------------------------------------------------------------------------

run "user_pool_admits_only_coach_created_accounts_with_totp" {
  assert {
    condition     = aws_cognito_user_pool.pilot.admin_create_user_config[0].allow_admin_create_user_only
    error_message = "No self sign-up: only the coach creates accounts."
  }

  assert {
    condition     = aws_cognito_user_pool.pilot.mfa_configuration == "ON"
    error_message = "MFA is required, not optional."
  }

  assert {
    condition     = aws_cognito_user_pool.pilot.software_token_mfa_configuration[0].enabled
    error_message = "The authenticator app (TOTP) must be enabled: it is the main second factor."
  }

  assert {
    condition     = length(aws_cognito_user_pool.pilot.email_mfa_configuration) == 1
    error_message = "Email MFA must be offered, as the opt-in fallback."
  }

  assert {
    condition     = aws_cognito_user_pool.pilot.email_configuration[0].email_sending_account == "DEVELOPER" && aws_cognito_user_pool.pilot.email_configuration[0].source_arn == aws_sesv2_email_identity.pilot.arn
    error_message = "Email codes go through the pool's own SES identity, which is what makes email MFA available."
  }

  assert {
    condition     = aws_cognito_user_pool.pilot.user_pool_tier == "ESSENTIALS"
    error_message = "Email MFA and managed login need the Essentials plan."
  }

  assert {
    condition     = toset(aws_cognito_user_pool.pilot.sign_in_policy[0].allowed_first_auth_factors) == toset(["PASSWORD"])
    error_message = "The first factor is the password and nothing else, so an emailed code can never replace it."
  }

  assert {
    condition     = length(aws_cognito_user_pool.pilot.device_configuration) == 0
    error_message = "Device remembering is off: every sign-in asks for the second factor."
  }

  assert {
    condition = alltrue([
      for mechanism in aws_cognito_user_pool.pilot.account_recovery_setting[0].recovery_mechanism :
      mechanism.name == "admin_only"
    ]) && length(aws_cognito_user_pool.pilot.account_recovery_setting[0].recovery_mechanism) == 1
    error_message = "Account recovery is admin_only: no forgot-password flow, the coach resets."
  }

  assert {
    condition = (
      aws_cognito_user_pool.pilot.password_policy[0].minimum_length == 12 &&
      !aws_cognito_user_pool.pilot.password_policy[0].require_lowercase &&
      !aws_cognito_user_pool.pilot.password_policy[0].require_uppercase &&
      !aws_cognito_user_pool.pilot.password_policy[0].require_numbers &&
      !aws_cognito_user_pool.pilot.password_policy[0].require_symbols &&
      aws_cognito_user_pool.pilot.password_policy[0].temporary_password_validity_days == 7
    )
    error_message = "Passwords: at least 12 characters with no character-class rules; temporary passwords last 7 days."
  }

  assert {
    condition     = aws_cognito_user_pool.pilot.deletion_protection == "INACTIVE"
    error_message = "Deletion protection is for prod; the dev pool holds only the maintainer and synthetic users."
  }

  assert {
    condition     = aws_cognito_user_group.coach.name == "coach" && aws_cognito_user_group.student.name == "student"
    error_message = "The pool's groups are coach and student."
  }

  assert {
    condition     = aws_cognito_user_group.email_second_factor.name == "email-second-factor" && aws_cognito_user_group.email_second_factor.user_pool_id == aws_cognito_user_pool.pilot.id
    error_message = "The pool has the email-second-factor group the app and tub users read (PM ruling, 2026-10-19)."
  }
}

run "user_pool_has_no_sms_and_nothing_beyond_a_username_and_an_optional_email" {
  assert {
    condition     = length(aws_cognito_user_pool.pilot.sms_configuration) == 0
    error_message = "No SMS configuration exists, so SMS MFA cannot be turned on (task spec: forbidden)."
  }

  assert {
    condition     = length(aws_cognito_user_pool.pilot.schema) == 0
    error_message = "No schema block: no custom attribute and no required one. Email, in particular, is never required."
  }

  assert {
    condition = (
      length(coalesce(aws_cognito_user_pool.pilot.username_attributes, [])) == 0 &&
      length(coalesce(aws_cognito_user_pool.pilot.alias_attributes, [])) == 0
    )
    error_message = "Sign-in is by username only: an email or a phone number can never be a sign-in name."
  }

  assert {
    condition     = aws_cognito_user_pool.pilot.username_configuration[0].case_sensitive == false
    error_message = "Usernames are case-insensitive. Cognito fixes this at creation, so it binds V2 too."
  }

  assert {
    condition     = toset(aws_cognito_user_pool.pilot.auto_verified_attributes) == toset(["email"])
    error_message = "Email is the only attribute Cognito verifies; there is no phone number to verify."
  }

  assert {
    condition     = toset(aws_cognito_user_pool.pilot.user_attribute_update_settings[0].attributes_require_verification_before_update) == toset(["email"])
    error_message = "A new email is held unverified until the student confirms the code."
  }

  assert {
    condition     = aws_cognito_user_pool_client.web.read_attributes == toset(["email", "email_verified"])
    error_message = "The app may read the email and whether it is verified, and no other attribute."
  }

  assert {
    condition     = aws_cognito_user_pool_client.web.write_attributes == toset(["email"])
    error_message = "The app may write the optional email and nothing else: no phone number, no name."
  }
}

run "app_client_is_confidential_code_flow_only" {
  assert {
    condition     = aws_cognito_user_pool_client.web.generate_secret
    error_message = "The client is confidential: it has a secret."
  }

  assert {
    condition = (
      aws_cognito_user_pool_client.web.allowed_oauth_flows == toset(["code"]) &&
      aws_cognito_user_pool_client.web.allowed_oauth_flows_user_pool_client &&
      aws_cognito_user_pool_client.web.supported_identity_providers == toset(["COGNITO"])
    )
    error_message = "Authorization code only, through Cognito's own identity provider only: no Google, no school account."
  }

  assert {
    condition     = aws_cognito_user_pool_client.web.allowed_oauth_scopes == toset(["openid", "aws.cognito.signin.user.admin"])
    error_message = "The scopes are openid and aws.cognito.signin.user.admin."
  }

  assert {
    condition     = aws_cognito_user_pool_client.web.explicit_auth_flows == toset(["ALLOW_REFRESH_TOKEN_AUTH"])
    error_message = "No explicit auth flow may let the app accept a password: refresh is the only one."
  }

  assert {
    condition = (
      aws_cognito_user_pool_client.web.callback_urls == toset(["https://tub.dev.wfbdebate.com/auth/callback"]) &&
      aws_cognito_user_pool_client.web.logout_urls == toset(["https://tub.dev.wfbdebate.com/signed-out"])
    )
    error_message = "The callback and sign-out URLs are the pilot host's /auth/callback and /signed-out."
  }

  assert {
    condition = (
      aws_cognito_user_pool_client.web.enable_token_revocation &&
      aws_cognito_user_pool_client.web.prevent_user_existence_errors == "ENABLED" &&
      aws_cognito_user_pool_client.web.refresh_token_rotation[0].feature == "DISABLED" &&
      aws_cognito_user_pool_client.web.refresh_token_rotation[0].retry_grace_period_seconds == 0
    )
    error_message = "Token revocation on, user-existence errors suppressed, refresh token rotation off."
  }

  assert {
    condition = (
      aws_cognito_user_pool_client.web.access_token_validity == 5 &&
      aws_cognito_user_pool_client.web.id_token_validity == 5 &&
      aws_cognito_user_pool_client.web.refresh_token_validity == 12 &&
      aws_cognito_user_pool_client.web.token_validity_units[0].access_token == "minutes" &&
      aws_cognito_user_pool_client.web.token_validity_units[0].id_token == "minutes" &&
      aws_cognito_user_pool_client.web.token_validity_units[0].refresh_token == "hours"
    )
    error_message = "Access and ID tokens last 5 minutes; the refresh token 12 hours, the absolute session lifetime."
  }

  assert {
    condition     = aws_ssm_parameter.client_secret.type == "SecureString" && aws_ssm_parameter.client_secret.name == "/debate-dev-tub/client-secret"
    error_message = "The client secret is a SecureString under /debate-<env>-tub/."
  }

  assert {
    condition = (
      aws_ssm_parameter.cookie_keys.type == "SecureString" &&
      aws_ssm_parameter.cookie_keys.name == "/debate-dev-tub/cookie-keys" &&
      strcontains(aws_ssm_parameter.cookie_keys.value, "placeholder")
    )
    error_message = "The cookie keys parameter is a SecureString created with a placeholder; the operator writes the real keys, never Terraform."
  }
}

run "managed_login_is_served_at_the_login_host" {
  assert {
    condition = (
      aws_cognito_user_pool_domain.login.domain == "auth.tub.dev.wfbdebate.com" &&
      aws_cognito_user_pool_domain.login.managed_login_version == 2 &&
      aws_cognito_user_pool_domain.login.certificate_arn == aws_acm_certificate_validation.pilot.certificate_arn
    )
    error_message = "Managed login (version 2) at auth.<pilot host>, with the validated certificate."
  }

  assert {
    condition = toset([for record in aws_route53_record.login_alias : record.type]) == toset(["A", "AAAA"]) && alltrue([
      for record in aws_route53_record.login_alias :
      record.name == "auth.tub.dev.wfbdebate.com" && record.alias[0].name == "dmocklogin.cloudfront.net"
    ])
    error_message = "The login host's A and AAAA records point at the distribution Cognito runs for it."
  }

  assert {
    condition = toset([for record in aws_route53_record.pilot_alias : record.type]) == toset(["A", "AAAA"]) && alltrue([
      for record in aws_route53_record.pilot_alias :
      record.name == "tub.dev.wfbdebate.com" && record.alias[0].name == aws_cloudfront_distribution.pilot.domain_name
    ])
    error_message = "The pilot host's A and AAAA records point at the pilot's distribution."
  }

  assert {
    condition = (
      aws_acm_certificate.pilot.domain_name == "tub.dev.wfbdebate.com" &&
      aws_acm_certificate.pilot.subject_alternative_names == toset(["auth.tub.dev.wfbdebate.com"]) &&
      aws_acm_certificate.pilot.validation_method == "DNS" &&
      length(aws_route53_record.certificate_validation) == 2
    )
    error_message = "One DNS-validated certificate covers the pilot host and the login host."
  }

  assert {
    condition = length(aws_route53_record.ses_dkim) == 3 && alltrue([
      for record in aws_route53_record.ses_dkim :
      record.type == "CNAME" && endswith(record.name, "._domainkey.tub.dev.wfbdebate.com")
    ])
    error_message = "The SES identity is verified by its three Easy DKIM records in the zone."
  }

  assert {
    condition     = aws_sesv2_email_identity.pilot.email_identity == "tub.dev.wfbdebate.com" && aws_cognito_user_pool.pilot.email_configuration[0].from_email_address == "no-reply@tub.dev.wfbdebate.com"
    error_message = "Email codes come from no-reply@<pilot host>, an address of the pool's own SES identity."
  }
}

# ---------------------------------------------------------------------------------------------
# The function and the distribution (ADR-0019 (a)).
# ---------------------------------------------------------------------------------------------

run "function_has_the_settings_adr_0019_gives_it" {
  assert {
    condition = (
      aws_lambda_function.pilot.function_name == "debate-dev-tub" &&
      aws_lambda_function.pilot.package_type == "Image" &&
      aws_lambda_function.pilot.architectures == tolist(["arm64"]) &&
      aws_lambda_function.pilot.memory_size == 2048 &&
      aws_lambda_function.pilot.ephemeral_storage[0].size == 4096 &&
      aws_lambda_function.pilot.timeout == 30 &&
      aws_lambda_function.pilot.reserved_concurrent_executions == 10
    )
    error_message = "debate-<env>-tub: an arm64 image, 2,048 MB, 4,096 MB of /tmp, 30 s, reserved concurrency 10."
  }

  assert {
    condition     = aws_lambda_function.pilot.image_uri == "111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-mock-tub@sha256:0000000000000000000000000000000000000000000000000000000000000001"
    error_message = "The function is created from an image in its own repository, named by digest, never by tag."
  }

  assert {
    condition = (
      aws_lambda_function.pilot.environment[0].variables["TUB_PUBLIC_ORIGIN"] == "https://tub.dev.wfbdebate.com" &&
      aws_lambda_function.pilot.environment[0].variables["TUB_LOGIN_ORIGIN"] == "https://auth.tub.dev.wfbdebate.com" &&
      aws_lambda_function.pilot.environment[0].variables["AWS_LWA_READINESS_CHECK_PATH"] == "/healthz" &&
      aws_lambda_function.pilot.environment[0].variables["AWS_LWA_PORT"] == "8080"
    )
    error_message = "The app takes its origin and the login host from configuration, and the Web Adapter checks /healthz on 8080."
  }

  assert {
    condition = alltrue([
      for name, value in aws_lambda_function.pilot.environment[0].variables :
      !strcontains(lower(name), "secret") || endswith(name, "_PARAMETER")
    ])
    error_message = "No secret is passed in the function's environment, only the name of the parameter that holds it."
  }

  assert {
    condition = (
      aws_ecr_repository.function.name == "debate-dev-tub" &&
      aws_ecr_repository.function.image_scanning_configuration[0].scan_on_push &&
      jsondecode(aws_ecr_lifecycle_policy.function.policy).rules[0].selection.countNumber == 5 &&
      jsondecode(aws_ecr_lifecycle_policy.function.policy).rules[0].selection.tagStatus == "any"
    )
    error_message = "The repository scans on push and keeps the last five images."
  }
}

run "distribution_sends_the_security_headers_and_caches_nothing" {
  assert {
    condition = (
      aws_cloudfront_distribution.pilot.aliases == toset(["tub.dev.wfbdebate.com"]) &&
      aws_cloudfront_distribution.pilot.viewer_certificate[0].minimum_protocol_version == "TLSv1.2_2021" &&
      aws_cloudfront_distribution.pilot.viewer_certificate[0].ssl_support_method == "sni-only" &&
      aws_cloudfront_distribution.pilot.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    )
    error_message = "The pilot host on TLSv1.2_2021 with SNI, and http:// redirected to https://."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.pilot.http_version == "http2and3" &&
      aws_cloudfront_distribution.pilot.price_class == "PriceClass_100" &&
      aws_cloudfront_distribution.pilot.default_cache_behavior[0].compress
    )
    error_message = "HTTP/2 and HTTP/3, PriceClass_100, compression on."
  }

  assert {
    condition = (
      length(aws_cloudfront_distribution.pilot.logging_config) == 0 &&
      (aws_cloudfront_distribution.pilot.web_acl_id == null ? "" : aws_cloudfront_distribution.pilot.web_acl_id) == ""
    )
    error_message = "No access logging and no WAF (ADR-0019 (a) 4): no per-request record of a student's address."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.pilot.default_cache_behavior[0].allowed_methods == toset(["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]) &&
      data.aws_cloudfront_cache_policy.caching_disabled.name == "Managed-CachingDisabled" &&
      data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header.name == "Managed-AllViewerExceptHostHeader" &&
      # In provider 5.100.0 these two data sources' `id` is a plain optional attribute, which
      # neither mock_data nor override_data fills, so under the mock both sides of these two
      # comparisons are null. They catch a literal policy id put in place of the data source,
      # not a policy removed altogether; what this run can really check is the two names.
      aws_cloudfront_distribution.pilot.default_cache_behavior[0].cache_policy_id == data.aws_cloudfront_cache_policy.caching_disabled.id &&
      aws_cloudfront_distribution.pilot.default_cache_behavior[0].origin_request_policy_id == data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header.id
    )
    error_message = "One behaviour: all seven methods, the managed CachingDisabled policy and AllViewerExceptHostHeader."
  }

  assert {
    condition = alltrue([
      for directive in ["default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'", "form-action 'self' https://auth.tub.dev.wfbdebate.com"] :
      strcontains(aws_cloudfront_response_headers_policy.pilot.security_headers_config[0].content_security_policy[0].content_security_policy, directive)
    ])
    error_message = "The Content-Security-Policy is default-src 'self' with frame-ancestors, object-src and base-uri 'none', and form-action 'self' plus the login host."
  }

  assert {
    condition = (
      aws_cloudfront_response_headers_policy.pilot.security_headers_config[0].strict_transport_security[0].access_control_max_age_sec >= 31536000 &&
      aws_cloudfront_response_headers_policy.pilot.security_headers_config[0].content_type_options[0].override &&
      aws_cloudfront_response_headers_policy.pilot.security_headers_config[0].referrer_policy[0].referrer_policy == "no-referrer" &&
      aws_cloudfront_response_headers_policy.pilot.security_headers_config[0].frame_options[0].frame_option == "DENY"
    )
    error_message = "HSTS for a year, nosniff, Referrer-Policy: no-referrer, X-Frame-Options: DENY."
  }

  assert {
    condition = length([
      for item in aws_cloudfront_response_headers_policy.pilot.custom_headers_config[0].items :
      item if item.header == "Permissions-Policy" && strcontains(item.value, "camera=()")
    ]) == 1
    error_message = "A Permissions-Policy turns devices off."
  }

  assert {
    condition = length([
      for item in aws_cloudfront_response_headers_policy.pilot.custom_headers_config[0].items :
      item if item.header == "X-Robots-Tag" && item.value == "noindex, nofollow"
    ]) == 1
    error_message = "dev sends X-Robots-Tag: noindex, nofollow."
  }
}

# ---------------------------------------------------------------------------------------------
# Prod: the same module with the prod inputs.
# ---------------------------------------------------------------------------------------------

run "prod_protects_its_pool_and_is_not_marked_noindex" {
  variables {
    name_prefix         = "debate-prod-tub"
    environment         = "prod"
    pilot_host          = "tub.wfbdebate.com"
    evidence_bucket_arn = "arn:aws:s3:::debate-prod-evidence-a7508de8"
  }

  assert {
    condition     = aws_cognito_user_pool.pilot.deletion_protection == "ACTIVE"
    error_message = "Deletion protection is on for the prod pool."
  }

  assert {
    condition = length([
      for item in aws_cloudfront_response_headers_policy.pilot.custom_headers_config[0].items :
      item if item.header == "X-Robots-Tag"
    ]) == 0
    error_message = "Prod sends no X-Robots-Tag; only dev is marked noindex."
  }

  assert {
    condition = (
      aws_cognito_user_pool.pilot.name == "debate-prod-tub" &&
      aws_cognito_user_pool_domain.login.domain == "auth.tub.wfbdebate.com" &&
      aws_cognito_user_pool_client.web.callback_urls == toset(["https://tub.wfbdebate.com/auth/callback"])
    )
    error_message = "Prod's pool, login host and callback are prod's own."
  }

  assert {
    condition = alltrue(flatten([
      for statement in jsondecode(aws_iam_role_policy.function.policy).Statement : [
        for resource in flatten([statement.Resource]) :
        startswith(resource, "arn:aws:s3:::debate-prod-evidence-a7508de8/") if contains(flatten([statement.Action]), "s3:GetObject")
      ]
    ]))
    error_message = "Prod's function reads prod's evidence bucket and no other."
  }
}

# ---------------------------------------------------------------------------------------------
# The budget and the two permission sets.
# ---------------------------------------------------------------------------------------------

run "budget_alarm_is_ten_dollars_for_this_environment" {
  assert {
    condition = (
      aws_budgets_budget.pilot_monthly.name == "debate-dev-tub-monthly" &&
      aws_budgets_budget.pilot_monthly.limit_amount == "10" &&
      aws_budgets_budget.pilot_monthly.time_unit == "MONTHLY"
    )
    error_message = "The pilot's budget is $10 a month per environment (ADR-0019 (g))."
  }

  assert {
    condition = anytrue([
      for filter in aws_budgets_budget.pilot_monthly.cost_filter :
      filter.name == "TagKeyValue" && filter.values == tolist(["user:Environment$dev"])
    ])
    error_message = "The budget counts this environment's spend only."
  }

  assert {
    condition = alltrue([
      for notification in aws_budgets_budget.pilot_monthly.notification :
      notification.subscriber_email_addresses == toset(["maintainer@example.com"])
    ])
    error_message = "Every notification goes to the address the root supplies from owner.auto.tfvars."
  }
}

run "deployer_can_push_and_update_its_own_function_and_nothing_else" {
  variables {
    identity_center_instance_arn = "arn:aws:sso:::instance/ssoins-mock"
    identity_store_id            = "d-mock000000"
    deployer_user_names          = ["maintainer"]
    accounts_user_names          = ["maintainer"]
  }

  assert {
    condition     = aws_ssoadmin_permission_set.deployer[0].name == "DebateDevTubDeployer" && aws_ssoadmin_permission_set.accounts[0].name == "DebateDevTubAccounts"
    error_message = "The permission sets are named for their environment."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.deployer[0].inline_policy).Statement : flatten([statement.Action])
      ])) == toset([
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
    ])
    error_message = "TubDeployer pushes an image and updates its function's code, and reads the function back. Nothing else."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.deployer[0].inline_policy).Statement :
      alltrue([
        for resource in flatten([statement.Resource]) :
        resource == aws_ecr_repository.function.arn || resource == aws_lambda_function.pilot.arn || (resource == "*" && flatten([statement.Action]) == ["ecr:GetAuthorizationToken"])
      ])
    ])
    error_message = "Every TubDeployer grant names its own repository or its own function; only the registry sign-in, which has no resource, is on *."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.accounts[0].inline_policy).Statement :
      alltrue([
        for resource in flatten([statement.Resource]) :
        resource == aws_cognito_user_pool.pilot.arn || resource == aws_cloudwatch_log_stream.account_changes.arn
      ])
    ])
    error_message = "TubAccounts acts on its own pool and its own audit stream only."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.accounts[0].inline_policy).Statement :
      [for action in flatten([statement.Action]) : action if startswith(action, "cognito-idp:")]
      ])) == toset([
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminAddUserToGroup",
      "cognito-idp:AdminRemoveUserFromGroup",
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
    ])
    error_message = "TubAccounts holds exactly the Cognito actions tub users calls (debate_core.integrations.cognito.accounts), and no other."
  }

  assert {
    condition = toset(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.accounts[0].inline_policy).Statement :
      [for action in flatten([statement.Action]) : action if startswith(action, "logs:")]
    ])) == toset(["logs:PutLogEvents"])
    error_message = "TubAccounts may append to the audit log and do nothing else to it."
  }

  assert {
    condition = length(flatten([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.accounts[0].inline_policy).Statement : [
        for action in flatten([statement.Action]) : action
        if contains(["cognito-idp:AdminInitiateAuth", "cognito-idp:AdminRespondToAuthChallenge", "cognito-idp:AdminUpdateUserAttributes", "cognito-idp:AdminSetUserMFAPreference"], action) || strcontains(action, "*")
      ]
    ])) == 0
    error_message = "TubAccounts cannot sign in as a student, set a student's attributes or MFA, or hold a wildcard."
  }

  assert {
    condition     = length(aws_ssoadmin_account_assignment.deployers) == 1 && length(aws_ssoadmin_account_assignment.accounts) == 1
    error_message = "The named maintainer is assigned both sets."
  }
}

run "no_identity_center_instance_means_no_permission_sets" {
  assert {
    condition     = length(aws_ssoadmin_permission_set.deployer) == 0 && length(aws_ssoadmin_permission_set.accounts) == 0
    error_message = "The permission sets are optional: the module has to be usable without an Identity Center instance."
  }
}

run "a_name_prefix_without_its_environment_is_refused" {
  command = plan

  variables {
    name_prefix = "debate-tub"
  }

  expect_failures = [var.name_prefix]
}


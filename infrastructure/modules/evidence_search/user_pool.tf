# Sign-in (ADR-0019 (d)): one Cognito user pool per environment, accounts only the coach creates,
# a password and an authenticator app, an emailed code as an opt-in fallback, and no SMS at all.
#
# V2 keeps this pool (v2-e12-t01's PM amendment), and Cognito fixes several of these settings at
# creation: username sign-in with no alias, case-insensitive usernames, and no required
# attribute. They bind V2 too, which is why the tests assert each of them.
#
# The managed login branding is not here: Cognito creates none for an API-made client and
# provider 5.100.0 has no resource for one, so the runbook creates it once with
# `aws cognito-idp create-managed-login-branding --use-cognito-provided-values`.

# ---------------------------------------------------------------------------------------------
# The SES identity the email codes are sent from
# ---------------------------------------------------------------------------------------------

# A domain identity for the pilot host, verified by the DKIM records in certificate.tf. The pool
# sends through it with the DEVELOPER sending account, which is what makes email MFA available.
# Cognito creates its own service-linked role for that the first time the pool is applied, so no
# sending authorization policy is attached here.
#
# Until SES production access is granted (a runbook step, after the first prod apply) the account
# is in the SES sandbox and the fallback reaches only verified addresses.
#
# tflint-ignore: aws_resource_missing_tags
resource "aws_sesv2_email_identity" "pilot" {
  email_identity = var.pilot_host

  # Easy DKIM with SES's own 2048-bit keys, which is SES's default, said here so that the block
  # carrying the three DKIM tokens certificate.tf publishes is always present.
  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }
}

# ---------------------------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------------------------

# tflint-ignore: aws_resource_missing_tags
resource "aws_cognito_user_pool" "pilot" {
  name = var.name_prefix

  # Essentials: email MFA and managed login need it, and 30 users are inside its free tier.
  user_pool_tier = "ESSENTIALS"

  deletion_protection = local.is_production ? "ACTIVE" : "INACTIVE"

  # Sign-in by username. No username_attributes and no alias_attributes, so an email can never be
  # a sign-in name, and usernames are case-insensitive. Both are fixed at creation.
  username_configuration {
    case_sensitive = false
  }

  # No schema block: no custom attribute and no required attribute. Email in particular is not
  # required, and Cognito never lets that change after creation. A student's account holds a
  # username, a group and, only if the student adds one, an email (gate item 9).

  # Only the coach creates accounts. The invitation is suppressed per call by `tub users add`
  # (v1-e39-t05), since there is no address to send it to.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  # No forgot-password flow: the coach resets.
  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }

  # At least 12 characters and no character-class rules.
  password_policy {
    minimum_length                   = 12
    require_lowercase                = false
    require_uppercase                = false
    require_numbers                  = false
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  # A password, and then a second factor. Never a passkey or an emailed code in place of the
  # password.
  sign_in_policy {
    allowed_first_auth_factors = ["PASSWORD"]
  }

  # MFA required: the authenticator app, and email messages for a student who adds an address.
  # There is no sms_configuration and no SMS message anywhere in this pool. Device remembering is
  # off, which is the absence of a device_configuration block.
  mfa_configuration = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  email_mfa_configuration {
    subject = "Your team evidence search sign-in code"
    message = "Your sign-in code for the team evidence search is {####}."
  }

  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = aws_sesv2_email_identity.pilot.arn
    from_email_address    = "no-reply@${var.pilot_host}"
  }

  # A new email is held unverified until the student confirms the code Cognito sends. Cognito
  # requires an attribute listed here to be auto-verified as well.
  auto_verified_attributes = ["email"]

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  # The pool cannot send through an identity SES has not verified yet; the DKIM records are what
  # verify it.
  depends_on = [aws_route53_record.ses_dkim]
}

resource "aws_cognito_user_group" "coach" {
  name         = "coach"
  user_pool_id = aws_cognito_user_pool.pilot.id
  description  = "The coach: creates, resets and removes accounts, and searches."
  precedence   = 1
}

resource "aws_cognito_user_group" "student" {
  name         = "student"
  user_pool_id = aws_cognito_user_pool.pilot.id
  description  = "A debater on the team: searches and takes cards out."
  precedence   = 2
}

# Not a role: the coach's ruling that this one account may sign in with a verified email as its only
# second factor, for a debater with no phone (PM ruling, 2026-10-19). The app gives an account with
# no authenticator a session only when it is in this group and its email is verified; every other
# such account is sent to enrol an authenticator. `tub users add --email-second-factor` and
# `tub users email-second-factor` put an account in it and take it out (v1-e39-t05).
resource "aws_cognito_user_group" "email_second_factor" {
  name         = "email-second-factor"
  user_pool_id = aws_cognito_user_pool.pilot.id
  description  = "May use a verified email as the only second factor (no phone). Set by the coach."
  precedence   = 3
}

# ---------------------------------------------------------------------------------------------
# Managed login, at the login host
# ---------------------------------------------------------------------------------------------

resource "aws_cognito_user_pool_domain" "login" {
  domain                = local.login_host
  user_pool_id          = aws_cognito_user_pool.pilot.id
  certificate_arn       = aws_acm_certificate_validation.pilot.certificate_arn
  managed_login_version = 2

  # Cognito refuses a custom domain whose parent has no A record, so the pilot host's records are
  # created first (ADR-0019 (a) 6).
  depends_on = [aws_route53_record.pilot_alias]
}

# ---------------------------------------------------------------------------------------------
# The one confidential app client
# ---------------------------------------------------------------------------------------------

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.pilot.id

  # Confidential: the secret is what makes the refresh token inside the session cookie useless to
  # anyone but the function. It is copied into Parameter Store (parameters.tf) and so sits in
  # Terraform state, which is encrypted and restricted.
  generate_secret = true

  # The authorization code flow through managed login, with COGNITO as the only identity
  # provider. The app adds PKCE (S256) to every request it starts (v1-e39-t05).
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "aws.cognito.signin.user.admin"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = ["${local.pilot_origin}/auth/callback"]
  logout_urls   = ["${local.pilot_origin}/signed-out"]

  # No password flow: nothing lets the app accept a password. Refreshing is the only explicit
  # flow, and the app never sees a password.
  explicit_auth_flows = ["ALLOW_REFRESH_TOKEN_AUTH"]

  read_attributes  = ["email", "email_verified"]
  write_attributes = ["email"]

  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"

  # Access and ID tokens live five minutes, the minimum, and are used once. The refresh token
  # lives twelve hours, the absolute session lifetime, so it cannot outlive the session.
  access_token_validity  = 5
  id_token_validity      = 5
  refresh_token_validity = 12

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }

  # The grace period is written out although rotation is off: AWS reports it back as 0, and
  # provider 5.100.0 fails the apply with "inconsistent result after apply" when the config leaves
  # it unset (seen on the first dev apply, 2026-10-19).
  refresh_token_rotation {
    feature                    = "DISABLED"
    retry_grace_period_seconds = 0
  }
}

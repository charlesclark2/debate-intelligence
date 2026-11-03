# The two SecureString parameters the function reads once per cold start (ADR-0019 (d), keys and
# the secret), under /debate-<env>-tub/. Both use the AWS-managed aws/ssm key.
#
# They differ in where the value comes from, and so in whether it is in Terraform state:
#
#   client-secret  Terraform creates the app client, so the secret is in state already. It is
#                  copied here so the function reads it by name. Accepted: the state bucket is
#                  encrypted and restricted (PM, 2026-10-19).
#   cookie-keys    Never in state. Terraform creates the parameter with a placeholder and then
#                  ignores its value; the operator generates the real keys once with
#                  `openssl rand` and writes them with `aws ssm put-parameter --overwrite`
#                  (docs/runbooks/evidence-search.md). The app refuses the placeholder.

locals {
  parameter_path = "/${var.name_prefix}"

  # What the cookie-keys parameter holds until the runbook's step writes the real value. Not a
  # key: v1-e39-t05's app refuses to start a session while it reads this.
  cookie_keys_placeholder = jsonencode({
    placeholder = "Not a key. Write the real keys with the runbook's put-parameter step (docs/runbooks/evidence-search.md)."
  })
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ssm_parameter" "client_secret" {
  name        = "${local.parameter_path}/client-secret"
  description = "The ${var.environment} pilot's Cognito app client secret, copied from the client Terraform creates (ADR-0019 (d))."
  type        = "SecureString"
  value       = aws_cognito_user_pool_client.web.client_secret
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ssm_parameter" "cookie_keys" {
  name        = "${local.parameter_path}/cookie-keys"
  description = "The ${var.environment} pilot's session cookie keys: a JSON object with a current and a previous key, each 32 random bytes in base64. Written by the operator, never by Terraform (ADR-0019 (d))."
  type        = "SecureString"
  value       = local.cookie_keys_placeholder

  lifecycle {
    # The operator's put-parameter replaces the placeholder; Terraform must never put it back,
    # and never learn the real value.
    ignore_changes = [value]
  }
}

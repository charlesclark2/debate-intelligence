# `evidence_search` module

One environment's student evidence search pilot: one container-image Lambda function behind its own
CloudFront distribution, the Cognito user pool for the accounts the coach creates, and the
append-only access audit log. Spec:
[`v1-e39-t04-pilot-infrastructure`](../../../plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml).
Decision: [ADR-0019](../../../docs/adr/0019-student-search-pilot-stack-sign-in-and-hosting.md).
Operator steps: [docs/runbooks/evidence-search.md](../../../docs/runbooks/evidence-search.md).

Called once from [`envs/dev`](../../envs/dev/evidence_search.tf) and once from
[`envs/prod`](../../envs/prod/evidence_search.tf), with the same arguments; the two differ only in
their `terraform.tfvars`. It holds no account id, region or domain: the host, the zone and the
evidence bucket are inputs.

## What it creates

| File | Resources | Why it is the way it is |
|---|---|---|
| `main.tf` | ECR repository and lifecycle policy | `debate-<env>-tub`, scan on push, the last five images kept. The deploy script owns the code |
| | Lambda function and its URL, two invoke permissions | arm64 image, 2,048 MB, 4,096 MB `/tmp`, 30 s, reserved concurrency 10. The URL requires `AWS_IAM`; CloudFront may invoke it only for this environment's distribution. The image URI is ignored after creation |
| | IAM role, its one inline policy, and the two exclusive-policy resources | ADR-0019's role table, exactly. The exclusive resources remove any other inline or managed policy at the next apply |
| | Two log groups and one stream | `debate-<env>-tub-audit`, 400 days, append-only; `debate-<env>-tub-app`, 30 days, the function's own log; `tub-users`, the coach's account changes |
| `distribution.tf` | Origin access control (type `lambda`), response headers policy, distribution | One origin, the function URL. CachingDisabled and AllViewerExceptHostHeader. CSP, HSTS, nosniff, `no-referrer`, `DENY`, a Permissions-Policy, and `noindex` on dev. **No logging and no WAF** |
| `certificate.tf` | ACM certificate, its validation, alias records, DKIM records | One certificate for the pilot and login hosts. A and AAAA aliases for both. The zone is read by the calling root, never created |
| `user_pool.tf` | SES identity, user pool, groups, managed login domain, app client | See [The pool](#the-pool) |
| `parameters.tf` | Two SecureString parameters | The client secret (copied from the client, so in state); the cookie keys (a placeholder, ignored after creation, written by the operator) |
| `budget.tf` | A $10 monthly budget | Scoped to this environment's tag and the pilot's services |
| `pilot_access.tf` | `TubDeployer` and `TubAccounts` permission sets with their assignments | Push and update one function; manage one pool and append to one audit stream |

### The pool

Essentials plan; sign-in by username only, case-insensitive; no required or custom attribute;
administrator-created users only; recovery `admin_only`; passwords of 12 or more characters with no
class rules; MFA required, with the authenticator app and email offered and no SMS configuration at
all; the password as the only first factor; no device remembering; email sent through the pool's
own SES identity; a new email held unverified until confirmed; groups `coach` and `student`;
deletion protection on in prod. The app client is confidential, authorization code only, scopes
`openid` and `aws.cognito.signin.user.admin`, `COGNITO` as the only identity provider, no password
flow, reads `email` and `email_verified`, writes `email`.

Several of these Cognito fixes at creation, and V2 keeps this pool (`v2-e12-t01`), so they bind V2
too.

## What it cannot do, and the runbook does

Provider 5.100.0 cannot make three settings. Each is a CLI step with a read-back in the runbook:

- deletion protection on the audit log group (`aws logs put-log-group-deletion-protection`);
- the managed login branding (`aws cognito-idp create-managed-login-branding`);
- the login domain's minimum TLS version (`CustomDomainConfig.SecurityPolicy`).

## The first apply in an environment

The function is created from the newest image in its repository, read through `aws_ecr_image`. A new
environment's repository is empty, so the first apply targets the repository alone, the first deploy
pushes an image, and then the full apply creates everything else. The runbook's steps 1 to 3.

## Tests

`tests/evidence_search.tftest.hcl` runs under a mocked provider: no credentials, no network. It
checks the role against ADR-0019's role table entry by entry and that it has no other grant; the
log groups' retention; the evidence bucket's Block Public Access flags and policy, planned with the
roots' inputs; that CloudFront's only origin is the function URL; the pool, the client and the
domain; the function's settings; the headers; prod's differences; the budget; and both permission
sets. `scripts/terraform_checks.sh` runs it.

tflint's `aws_resource_missing_tags` rule cannot see the calling root's `default_tags` when it lints
this directory alone, so the taggable resources carry a `tflint-ignore` annotation, as in
`static_site`. Linting the roots follows the module call and checks them.

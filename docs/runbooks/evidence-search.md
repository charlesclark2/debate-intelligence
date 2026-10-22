<!-- docs-index: Standing up the student evidence search pilot in dev and prod: applies, deploys, cookie keys, CLI-only settings, SES access and the school IT request -->
# Runbook: the student evidence search pilot

How the team's evidence search pilot is stood up in AWS, in dev and then in prod: the Terraform
applies, the image deploys, the settings Terraform cannot make, SES production access, and the
request to school IT. Spec:
[`v1-e39-t04-pilot-infrastructure`](../../plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml).
Decision: [ADR-0019](../adr/0019-student-search-pilot-stack-sign-in-and-hosting.md). One account
and one region: [ADR-0010](../adr/0010-primary-aws-region.md). Two environments:
[ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md).

Written for an adult engineer with administrator access to the account. **Every step here is run
by a human operator.** CI has no AWS credentials, and an agent session never applies, deploys or
calls AWS.

Permission questions are answered with `aws iam simulate-principal-policy`, which evaluates the
policies **without performing the action**, as in the [team website runbook](team-website.md).

## What this builds

| | dev | prod |
|---|---|---|
| Pilot host | `https://tub.dev.wfbdebate.com/` | `https://tub.wfbdebate.com/` |
| Login host (managed login) | `auth.tub.dev.wfbdebate.com` | `auth.tub.wfbdebate.com` |
| Function and image repository | `debate-dev-tub` | `debate-prod-tub` |
| User pool and app client | `debate-dev-tub`, `debate-dev-tub-web` | `debate-prod-tub`, `debate-prod-tub-web` |
| Pool deletion protection | Off | On |
| Audit log group (400 days) | `debate-dev-tub-audit` | `debate-prod-tub-audit` |
| App log group (30 days) | `debate-dev-tub-app` | `debate-prod-tub-app` |
| Parameters | `/debate-dev-tub/client-secret`, `/debate-dev-tub/cookie-keys` | `/debate-prod-tub/client-secret`, `/debate-prod-tub/cookie-keys` |
| Budget | `debate-dev-tub-monthly`, $10 | `debate-prod-tub-monthly`, $10 |
| Deploy permission set and profile | `DebateDevTubDeployer`, `debate-dev-tub-deployer` | `DebateProdTubDeployer`, `debate-prod-tub-deployer` |
| Accounts permission set and profile | `DebateDevTubAccounts`, `debate-dev-tub-accounts` | `DebateProdTubAccounts`, `debate-prod-tub-accounts` |
| Indexable | No: `X-Robots-Tag: noindex, nofollow` | Not marked |

The function is reachable only through CloudFront: its URL requires `AWS_IAM`, and CloudFront
signs every request through origin access control. The evidence bucket is untouched: its Block
Public Access settings and policy are as they were, and the function reads it through its own role,
which may read `reports/tub/search/*`, current objects under `raw/` and the suppression list, and
nothing else. **The dev pool holds the maintainer and synthetic users only, never a student**
(ADR-0013).

Three settings are made here with the CLI, because provider 5.100.0, the version this repository
locks, cannot make them: the audit group's deletion protection, the managed login branding, and the
login domain's minimum TLS version. Each has a read-back check.

## The order

| Step | What | Where it runs from |
|---|---|---|
| [Before you start](#before-you-start) | Variables, tools, sign-in, owner.auto.tfvars, the concurrency check | `$WT` |
| [1](#step-1--apply-dev-the-image-repository-alone) | Apply dev: the repository alone | `$WT`, as `debate-admin` |
| [2](#step-2--the-first-dev-deploy-pushes-an-image) | The first dev deploy pushes an image | `$WT`, as `debate-admin` |
| [3](#step-3--apply-dev-in-full) | Apply dev in full, which creates the function from that image | `$WT`, as `debate-admin` |
| [4](#step-4--request-ses-production-access) | Request SES production access, once the dev apply has verified the SES identity | anywhere, as `debate-admin` |
| [5](#step-5--the-settings-terraform-cannot-make) | The three CLI-only settings | `$WT`, as `debate-admin` |
| [6](#step-6--put-the-cookie-keys) | Put the cookie keys | anywhere, as `debate-admin` |
| [7](#step-7--sign-in-to-the-new-permission-sets) | Sign in to the new permission sets | your Mac |
| [8](#step-8--deploy-dev-as-tubdeployer-and-check-it-through-cloudfront) | Deploy dev as TubDeployer; check through CloudFront; check the function URL refuses a direct call | `$WT` |
| [9](#step-9--confirm-the-roles-are-least-privilege) | Confirm the function's role and the two permission sets are least-privilege | anywhere |
| [10](#step-10--sign-in-on-dev-and-record-the-managed-logins-asset-hosts) | Sign in on dev and record the managed login's asset hosts | Chrome on your Mac |
| [11](#step-11--prod) | Prod: the same sequence, the deploys from a `main` worktree | `$WT`, then a `main` worktree |
| [12](#step-12--the-web-filter-request-to-school-it) | The web-filter request to school IT | email |

## Before you start

**Shell variables**, used by every block below. `WT` is the checkout holding this task's
Terraform: the task worktree while the task is in flight, the main clone once it has merged.
`PILOT_USERNAME` is the dev sign-in name you will give yourself in step 10; make it up, and never
use a student's name.

```bash
WT=/path/to/your/checkout
OWNER_EMAIL='you@example.com'
SSO_USER_NAME='your-identity-center-user-name'
PILOT_USERNAME='your-dev-pilot-username'

cd "$WT" || { echo "WT does not exist: $WT"; }
test -f infrastructure/envs/dev/evidence_search.tf \
  && echo "ok: $(pwd) on branch $(git branch --show-current)" \
  || echo "WRONG CHECKOUT: $(pwd) has no infrastructure/envs/dev/evidence_search.tf"
```
Success looks like: `ok: <the checkout> on branch task/v1-e39-t04-pilot-infrastructure` (or `dev`
or `main` once merged). Anything else, fix `WT` before going on.

**A fresh worktree needs its environment** before the deploy script can stage the image:

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
uv sync --all-packages
```
Success looks like: `Resolved ... packages` and no error.

**The tools.** Docker Desktop must be running: the deploy script builds the image with it and
refuses without it. The AWS CLI must be new enough to know the log group deletion-protection
command, which is newer than many installed copies.

**Operator command** (expected runtime ~2 min if the CLI needs upgrading, seconds otherwise)
Where: your Mac, anywhere
```bash
docker info --format '{{.ServerVersion}}'
docker buildx version
aws --version
aws logs put-log-group-deletion-protection help > /dev/null 2>&1 && echo "cli: ok" || echo "cli: upgrade needed"
```
Success looks like: a Docker server version, a `github.com/docker/buildx` line, the CLI's version
and `cli: ok`. On `cli: upgrade needed`, run `brew upgrade awscli` and repeat the block. On a
Docker error, start Docker Desktop and wait until it says it is running.

**Sign in and confirm the identity the applies run as.** Creating the two permission sets needs
break-glass, as the website's did ([team-website.md](team-website.md), "Why the applies run as
`debate-admin`"), so every apply here runs as `debate-admin`.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```
Success looks like: an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

**A fresh worktree has no `owner.auto.tfvars` of its own.** The files are gitignored, so a new
task worktree starts without them. Applying without them is not harmless: with the website's and
the evidence store's user name lists empty, the plan would remove those permission sets'
assignments. Copy both files from the checkout that last applied each root, then check that
`owner` still matches the `Owner` tag on what is deployed (team-website.md, "Before you start").
`PREVIOUS_DEV_WT` and `PREVIOUS_PROD_WT` are those checkouts.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
PREVIOUS_DEV_WT=/path/to/the/checkout/that/last/applied/dev
PREVIOUS_PROD_WT=/path/to/the/checkout/that/last/applied/prod
test -f infrastructure/envs/dev/owner.auto.tfvars || cp "${PREVIOUS_DEV_WT}/infrastructure/envs/dev/owner.auto.tfvars" infrastructure/envs/dev/
test -f infrastructure/envs/prod/owner.auto.tfvars || cp "${PREVIOUS_PROD_WT}/infrastructure/envs/prod/owner.auto.tfvars" infrastructure/envs/prod/
grep -h '^owner' infrastructure/envs/dev/owner.auto.tfvars infrastructure/envs/prod/owner.auto.tfvars
AWS_PROFILE=debate-admin aws s3api get-bucket-tagging --bucket debate-dev-site-a7508de8 --query "TagSet[?Key=='Owner'].Value" --output text
AWS_PROFILE=debate-admin aws s3api get-bucket-tagging --bucket debate-prod-site-a7508de8 --query "TagSet[?Key=='Owner'].Value" --output text
```
Success looks like: two `owner = "..."` lines and then two tag values, all four the same address.
If they differ, set `owner` to the deployed tag's value before any apply.

**The operator-local tfvars.** Add the pilot's three lines to each root's gitignored
`owner.auto.tfvars`, beside the lines already there. They name you for the two permission sets and
the budget alarm; none of it is committed. Read back the file afterwards rather than trusting the
append: `terraform fmt` aligns it, and `scripts/terraform_checks.sh` fails on an unaligned file.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
for env in dev prod; do
  test -f "infrastructure/envs/$env/owner.auto.tfvars" || echo "MISSING: infrastructure/envs/$env/owner.auto.tfvars, see team-website.md, Before you start"
  cat >> "infrastructure/envs/$env/owner.auto.tfvars" <<TFVARS
evidence_search_deployer_user_names = ["$SSO_USER_NAME"]
evidence_search_accounts_user_names = ["$SSO_USER_NAME"]
evidence_search_budget_emails       = ["$OWNER_EMAIL"]
TFVARS
done

terraform fmt infrastructure/envs/dev infrastructure/envs/prod
grep -c evidence_search infrastructure/envs/dev/owner.auto.tfvars infrastructure/envs/prod/owner.auto.tfvars
```
Success looks like: no `MISSING` line, and `3` for each file. A `6` means the block was run twice:
delete the repeated lines. `git status` still reports a clean tree; these files are gitignored.

**Every later apply needs the same lines, from whichever worktree it runs.** A task's follow-up
that applies another module (the evidence store's listing grant, for example) from a worktree whose
`owner.auto.tfvars` lacks the pilot's lines plans to destroy the `TubDeployer` and `TubAccounts`
assignments. Before any `terraform apply` in `dev` or `prod`, `grep -c evidence_search` on that
root's file must print `3`. A plan that destroys an account assignment means the file is missing
or stale: stop and fix the file, never apply (seen on dev on 2026-10-20; added by the PM,
2026-10-21).

**Lambda's concurrency allowance.** Each environment reserves 10 concurrent executions for the
pilot, and Lambda refuses a reservation that would leave fewer than 100 unreserved. A new account's
allowance can be as low as 10, so check it before applying.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws lambda get-account-settings --profile debate-admin --region us-east-1 \
  --query '[AccountLimit.ConcurrentExecutions,AccountLimit.UnreservedConcurrentExecutions]' --output text
```
Success looks like: two numbers, each at least `120` (usually `1000 1000`). Below that, the
function's creation in step 3 fails, so request a quota increase now. Steps 1 and 2 do not need it
and can run while AWS decides; step 3, and step 4 after it, wait until the check above shows at
least `120` twice. This account's allowance was `10 10` on 2026-10-19, and an increase to 1,000
was requested that day.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws service-quotas list-service-quotas --profile debate-admin --region us-east-1 --service-code lambda \
  --query "Quotas[?QuotaName=='Concurrent executions'].[QuotaCode,Value]" --output text
aws service-quotas request-service-quota-increase --profile debate-admin --region us-east-1 \
  --service-code lambda --quota-code L-B99A9384 --desired-value 1000 \
  --query 'RequestedQuota.[Id,Status]' --output text
```
Success looks like: `L-B99A9384	10.0` (use the code it prints if it differs), then a request id and
`PENDING` or `CASE_OPENED`. To follow the request, with that id:

```bash
QUOTA_REQUEST_ID='the-request-id-printed-above'
aws service-quotas get-requested-service-quota-change --profile debate-admin --region us-east-1 \
  --request-id "$QUOTA_REQUEST_ID" --query 'RequestedQuota.Status' --output text
```
`APPROVED` is the end of it; then repeat the `get-account-settings` check.

## Step 1 — Apply dev: the image repository alone

The function is created from an image in its own repository, so the repository has to exist and
hold an image first (ADR-0019 (f) 2). This apply creates the repository and nothing else.
Terraform warns that a targeted apply is for exceptional cases; this is one, and it happens once
per environment.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev init
terraform -chdir=infrastructure/envs/dev apply -target=module.evidence_search.aws_ecr_repository.function
```
Read the plan before approving. It should create exactly one resource,
`module.evidence_search.aws_ecr_repository.function`, named `debate-dev-tub`, and change nothing
else. Success looks like `Warning: Applied changes may be incomplete` followed by
`Apply complete! Resources: 1 added, 0 changed, 0 destroyed.`

## Step 2 — The first dev deploy pushes an image

The deploy script normally runs as `TubDeployer`, which the full apply in step 3 creates. This
first run uses `debate-admin` instead, through `TUB_DEPLOY_PROFILE`. It builds the image, pushes
it, finds no function yet, and stops.

**Operator command** (expected runtime ~2 min, longer the first time Docker pulls the base image)
Where: `$WT`
```bash
cd "$WT"
TUB_DEPLOY_PROFILE=debate-admin scripts/tub_deploy.sh dev
```
Success looks like, in order: `requires-python ...: public.ecr.aws/lambda/python:<the version>`,
the build's output ending in `naming to docker.io/library/debate-dev-tub:<sha>`,
`pushed: <account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-tub@sha256:<64 hex digits>`, and then

```text
The image is in debate-dev-tub's repository, and the function debate-dev-tub does not exist yet.
This is an environment's first deploy: run the full apply now (docs/runbooks/evidence-search.md),
which creates the function from this image, then run this script again.
```

## Step 3 — Apply dev in full

This creates the function from the image step 2 pushed, its URL and role, CloudFront, the
certificate and DNS, the user pool with its domain and client, the SES identity, the two log groups,
the parameters, the budget and the two permission sets.

**Operator command** (expected runtime ~25 min: CloudFront, the certificate and Cognito's own
distribution for the login host each take several minutes)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev apply
```
Read the plan before approving. With one user name in each of the two lists, it should say
`Plan: 41 to add, 0 to change, 0 to destroy.` All 41 are under `module.evidence_search`. Check
for the names in [What this builds](#what-this-builds), and check that nothing outside
`module.evidence_search` changes: **no change to `module.evidence_store`**, the evidence bucket,
its public access block or its policy, and none to `module.site`. If any of those appears, stop.

Success looks like `Apply complete! Resources: 41 added, 0 changed, 0 destroyed.` and, among the
outputs, `evidence_search_url = "https://tub.dev.wfbdebate.com/"`.

**If the apply stops at `aws_cognito_user_pool.pilot`** with a message that the email identity is
not verified, SES has not yet seen the DKIM records the same apply wrote. Wait until this prints
`True`, then run the same apply again; it picks up where it stopped.

```bash
aws sesv2 get-email-identity --email-identity tub.dev.wfbdebate.com --region us-east-1 \
  --query VerifiedForSendingStatus --output text
```

**If the apply stops at `aws_cognito_user_pool_domain.login`** saying the parent domain does not
resolve, the `tub.dev.wfbdebate.com` A record has not propagated yet. Wait five minutes and run the
same apply again.

Then keep the values the next steps use:

```bash
cd "$WT"
POOL_ID=$(terraform -chdir=infrastructure/envs/dev output -raw evidence_search_user_pool_id)
CLIENT_ID=$(terraform -chdir=infrastructure/envs/dev output -raw evidence_search_client_id)
FUNCTION_URL=$(terraform -chdir=infrastructure/envs/dev output -raw evidence_search_function_url)
echo "$POOL_ID $CLIENT_ID $FUNCTION_URL"
```
Success looks like: `us-east-1_<letters and digits> <26 characters> https://<id>.lambda-url.us-east-1.on.aws/`.

## Step 4 — Request SES production access

Until AWS grants it, the account is in the SES sandbox: the email fallback reaches only verified
addresses, 200 a day. Sandbox status is per account and Region, and dev and prod share one account
(ADR-0010), so one request covers both, and dev's verified identity is enough to ask with. Send it
now, as soon as step 3 has verified the dev identity, rather than after prod: AWS's first answer
can take up to 96 hours, and prod waits for a promotion. TOTP sign-in and the coach's resets do not
depend on it.

The request names the pilot's prod address, because that is where students will use it, even
though prod is not applied yet.

**If step 3 is waiting on the concurrency quota** ([Before you start](#before-you-start)), this
step need not wait too: it needs only the SES identity, which a targeted apply creates on its own,
with its DKIM records. Step 3's full apply then finds those four resources already there and plans
37 to add instead of 41.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev apply -target=module.evidence_search.aws_route53_record.ses_dkim
```
Success looks like: a plan of `4 to add` (`aws_sesv2_email_identity.pilot` and three
`aws_route53_record.ses_dkim`), then `Apply complete! Resources: 4 added, 0 changed, 0 destroyed.`

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
aws sesv2 get-email-identity --region us-east-1 --email-identity tub.dev.wfbdebate.com \
  --query VerifiedForSendingStatus --output text
```
Success looks like: `True`. On `False`, wait a few minutes and repeat; the DKIM records step 3
wrote are what verify it. Do not send the request until this says `True`.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
aws sesv2 put-account-details --region us-east-1 \
  --production-access-enabled \
  --mail-type TRANSACTIONAL \
  --website-url https://tub.wfbdebate.com/ \
  --contact-language EN \
  --additional-contact-email-addresses "$OWNER_EMAIL" \
  --use-case-description "Transactional email only, for a high school debate team's evidence search at https://tub.wfbdebate.com/, which opens to the team's students in the coming weeks. Amazon Cognito sends two kinds of message through this account: a one-time sign-in code to a student who has chosen email as a backup second factor, and a code to confirm that student's own email address when they add it. About 30 accounts, each created by the team's coach; nobody can sign up. Expected volume is under 500 messages a month. No marketing or bulk mail. Bounces and complaints are handled with the account-level suppression list."
aws sesv2 get-account --region us-east-1 \
  --query '[ProductionAccessEnabled,Details.ReviewDetails.Status]' --output text
```
Success looks like: no output from the request, then a review status of `PENDING`. The first
value read `True` on 2026-10-19, straight after the request, rather than the `False` an account in
the sandbox might be expected to show. So whether the account has left the sandbox is read from its
sending quota instead:

```bash
aws sesv2 get-account --region us-east-1 \
  --query '[SendQuota.Max24HourSend,SendQuota.MaxSendRate,EnforcementStatus]' --output text
```
`200	1	HEALTHY` is the sandbox: the review is still pending. AWS writes to `$OWNER_EMAIL`. Run both
checks again later: a review status of `GRANTED` and a daily quota far above 200 (typically `50000`)
are the end of this step, and they hold for prod too. If AWS asks for more information, answer from the description above. Record
the dates in [What to record](#what-to-record).

## Step 5 — The settings Terraform cannot make

### 5a — Deletion protection on the audit log group

The function can only append to the audit group, and no API edits a log event. Deletion protection
also stops anyone deleting the group or its streams until the protection is turned off, and the
organization trail records that change (ADR-0019 (e) 2).

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
aws logs put-log-group-deletion-protection --region us-east-1 \
  --log-group-identifier debate-dev-tub-audit --deletion-protection-enabled
aws logs describe-log-groups --region us-east-1 --log-group-name-prefix debate-dev-tub-audit \
  --query 'logGroups[].[logGroupName,retentionInDays,deletionProtectionEnabled]' --output text
```
Success looks like: no output from the first command, then exactly one line:
`debate-dev-tub-audit	400	True`.

### 5b — The managed login branding

Cognito creates no branding for an app client made through the API, and without one the managed
login pages do not render. This creates Cognito's default branding for the pilot's client.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
aws cognito-idp create-managed-login-branding --region us-east-1 \
  --user-pool-id "$POOL_ID" --client-id "$CLIENT_ID" --use-cognito-provided-values \
  --query 'ManagedLoginBranding.ManagedLoginBrandingId' --output text
aws cognito-idp describe-managed-login-branding-by-client --region us-east-1 \
  --user-pool-id "$POOL_ID" --client-id "$CLIENT_ID" \
  --query 'ManagedLoginBranding.UseCognitoProvidedValues' --output text
```
Success looks like: a branding id (a UUID), then `True`. If the first command says a branding
already exists for the client, the second is the check that matters.

### 5c — The login domain's minimum TLS version

Managed login on a custom domain needs a security policy of `TLS_V1_2_2021` or stricter (ADR-0019
(d)). Cognito sets it through `CustomDomainConfig.SecurityPolicy`, which provider 5.100.0 cannot
send, so it is read back here and set if it is anything else.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
aws cognito-idp describe-user-pool-domain --region us-east-1 --domain auth.tub.dev.wfbdebate.com \
  --query 'DomainDescription.[Status,ManagedLoginVersion,CustomDomainConfig.SecurityPolicy]' --output text
```
Success looks like: `ACTIVE	2	TLS_V1_2_2021`. If the third value is anything else, including
`None`, set it, then repeat the read-back:

```bash
CERT_ARN=$(aws cognito-idp describe-user-pool-domain --region us-east-1 --domain auth.tub.dev.wfbdebate.com \
  --query 'DomainDescription.CustomDomainConfig.CertificateArn' --output text)
aws cognito-idp update-user-pool-domain --region us-east-1 --domain auth.tub.dev.wfbdebate.com \
  --user-pool-id "$POOL_ID" --managed-login-version 2 \
  --custom-domain-config "CertificateArn=${CERT_ARN},SecurityPolicy=TLS_V1_2_2021"
```
An `Unknown parameter` error means the CLI is older than the setting: `brew upgrade awscli` and run
it again.

## Step 6 — Put the cookie keys

The session cookie is encrypted under keys only the function holds (ADR-0019 (d)). Terraform
created `/debate-dev-tub/cookie-keys` with a placeholder and never reads or writes its value again,
so the real keys are never in Terraform state. They are generated here, once, and written straight
into the parameter.

The value is a JSON object with a `current` and a `previous` key, each 32 random bytes in base64.
At first both are new; a later rotation moves `current` to `previous` and generates a new
`current`. The keys go through a file readable only by you, removed at once, so they are never on a
command line or in your shell history.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
KEYS_FILE=$(mktemp)
chmod 600 "$KEYS_FILE"
printf '{"current":"%s","previous":"%s"}' "$(openssl rand -base64 32)" "$(openssl rand -base64 32)" > "$KEYS_FILE"
aws ssm put-parameter --region us-east-1 --name /debate-dev-tub/cookie-keys \
  --type SecureString --overwrite --value "file://${KEYS_FILE}" --query Version --output text
rm -f "$KEYS_FILE"
aws ssm get-parameter --region us-east-1 --name /debate-dev-tub/cookie-keys --with-decryption \
  --query Parameter.Value --output text \
  | python3 -c 'import base64, json, sys; keys = json.load(sys.stdin); print(sorted(keys), all(len(base64.b64decode(value)) == 32 for value in keys.values()))'
```
Success looks like: `2` (the placeholder was version 1), then `['current', 'previous'] True`. The
check prints no key.

A later `terraform apply` leaves this value alone: the parameter ignores changes to its value.

**The app will not start without this step.** Since `v1-e39-t05` the function reads the keys at
start-up and refuses Terraform's placeholder, so until the real keys are in place the Lambda Web
Adapter's readiness check never answers and step 8's `/healthz` check fails. After writing new
keys, deploy again (step 8) so a running environment picks them up.

## Step 7 — Sign in to the new permission sets

The deploy script runs as `TubDeployer`, and the coach's `tub users` commands (`v1-e39-t05`) as
`TubAccounts`. Add four profiles; the prod pair works once prod is applied in step 11.

**Operator command** (expected runtime ~3 min)
Where: your Mac, in `~/.aws/config`
```ini
[profile debate-dev-tub-deployer]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateDevTubDeployer
region = us-east-1
output = json

[profile debate-dev-tub-accounts]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateDevTubAccounts
region = us-east-1
output = json

[profile debate-prod-tub-deployer]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateProdTubDeployer
region = us-east-1
output = json

[profile debate-prod-tub-accounts]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateProdTubAccounts
region = us-east-1
output = json
```
Then:
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-tub-deployer --query Arn --output text
aws sts get-caller-identity --profile debate-dev-tub-accounts --query Arn --output text
```
Success looks like: two ARNs, containing `AWSReservedSSO_DebateDevTubDeployer` and
`AWSReservedSSO_DebateDevTubAccounts`. A failure usually means the user name lists were empty when
dev was applied: check `owner.auto.tfvars` and re-apply.

## Step 8 — Deploy dev as TubDeployer, and check it through CloudFront

This is the deploy every later change uses: no override, the deployer profile.

**Operator command** (expected runtime ~3 min)
Where: `$WT`
```bash
cd "$WT"
scripts/tub_deploy.sh dev
```
Success looks like, at the end:

```text
==> Checking https://tub.dev.wfbdebate.com/healthz through CloudFront
{"status":"ok"}

Deployed <sha> to dev: https://tub.dev.wfbdebate.com/
Function debate-dev-tub runs <account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-tub@sha256:<digest>
```

**The pilot through CloudFront, with the edge's headers.** A request through the distribution
reaches the function. Since `v1-e39-t05` every page needs a session, so a request without one is
sent to managed login, with `private, no-store`. (Before that, the function answered `/` with a
placeholder page and `200`.)

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
curl -sS -o /dev/null -w '%{http_code} %header{cache-control}\n' https://tub.dev.wfbdebate.com/
curl -sS -o /dev/null -w '%{redirect_url}\n' https://tub.dev.wfbdebate.com/ | cut -d '?' -f 1
curl -sSI https://tub.dev.wfbdebate.com/ \
  | grep -i -E '^(content-security-policy|strict-transport-security|referrer-policy|x-frame-options|x-content-type-options|x-robots-tag):'
```
Success looks like:

```text
302 private, no-store
https://auth.tub.dev.wfbdebate.com/oauth2/authorize
content-security-policy: default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self' https://auth.tub.dev.wfbdebate.com
strict-transport-security: max-age=31536000; includeSubDomains
referrer-policy: no-referrer
x-frame-options: DENY
x-content-type-options: nosniff
x-robots-tag: noindex, nofollow
```
The header lines may come in another order.

**A direct call to the function URL is refused before the function runs.** The function URL
requires `AWS_IAM`, and an unsigned request is refused by Lambda's own check with Lambda's own body.
The app never answers 403 and never says `Forbidden`, so this answer cannot have come from it.

```bash
curl -sS -w '\n%{http_code}\n' "${FUNCTION_URL}healthz"
curl -sS -w '\n%{http_code}\n' "${FUNCTION_URL}"
```
Success looks like, twice:

```text
{"Message":"Forbidden"}
403
```
A `200` or `{"status":"ok"}` here means the function URL is open to the internet: stop, and check
in the Lambda console that the URL's auth type is `AWS_IAM`.

**Record the cold start.** ADR-0019 (c) 7 asks for the function's init duration, from its
`REPORT` lines. The first request after a deploy starts a new environment, so step 8's own requests
produced one.

```bash
aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-app \
  --filter-pattern '"Init Duration"' --query 'events[-3:].message' --output text
```
Success looks like: up to three `REPORT RequestId: ...` lines, each with `Init Duration: <n> ms`.
Copy them into [What to record](#what-to-record).

## Step 9 — Confirm the roles are least-privilege

**The function's role** against ADR-0019's role table, with `simulate-principal-policy`. The bucket
and key names are dev's.

**Operator command** (expected runtime ~2 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
ROLE=$(aws iam get-role --role-name debate-dev-tub-function --query Role.Arn --output text)
BUCKET=arn:aws:s3:::debate-dev-evidence-a7508de8

echo "== reads it may make (expect allowed)"
for KEY in reports/tub/search/current.json raw/example/file.docx manifests/_suppression/suppression-list.jsonl; do
  aws iam simulate-principal-policy --policy-source-arn "$ROLE" --action-names s3:GetObject \
    --resource-arns "${BUCKET}/${KEY}" --query 'EvaluationResults[].[EvalResourceName,EvalDecision]' --output text
done

echo "== everything else in the bucket (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names s3:GetObjectVersion s3:PutObject s3:DeleteObject \
  --resource-arns "${BUCKET}/raw/example/file.docx" \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$ROLE" --action-names s3:GetObject \
  --resource-arns "${BUCKET}/parsed/example.json" \
  --query 'EvaluationResults[].[EvalResourceName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$ROLE" --action-names s3:ListBucket \
  --resource-arns "$BUCKET" --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text

echo "== its log groups: append only (expect allowed, then implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names logs:CreateLogStream logs:PutLogEvents \
  --resource-arns "arn:aws:logs:us-east-1:$(aws sts get-caller-identity --query Account --output text):log-group:debate-dev-tub-audit:log-stream:example" \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names logs:DeleteLogGroup logs:DeleteLogStream logs:PutRetentionPolicy \
  --resource-arns '*' --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text

echo "== its two parameters (expect allowed), and Cognito (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$ROLE" --action-names ssm:GetParameter \
  --resource-arns "arn:aws:ssm:us-east-1:$(aws sts get-caller-identity --query Account --output text):parameter/debate-dev-tub/cookie-keys" \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names cognito-idp:AdminCreateUser cognito-idp:ListUsers \
  --resource-arns '*' --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text

echo "== attached managed policies (expect nothing printed)"
aws iam list-attached-role-policies --role-name debate-dev-tub-function --query 'AttachedPolicies[].PolicyArn' --output text
```
Success looks like: `allowed` for the three reads, the two log actions and `ssm:GetParameter`;
`implicitDeny` for everything else, including `parsed/`; and an empty line for the attached
policies. Any `allowed` in the second, fourth or fifth group means the role is wider than the
table: stop.

**The two permission sets.**

**Operator command** (expected runtime ~2 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
DEPLOYER=$(aws iam list-roles --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateDevTubDeployer`)].Arn' --output text)
ACCOUNTS=$(aws iam list-roles --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateDevTubAccounts`)].Arn' --output text)

echo "== deployer on its own function (expect allowed), on prod's and on IAM (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$DEPLOYER" --action-names lambda:UpdateFunctionCode \
  --resource-arns "arn:aws:lambda:us-east-1:${ACCOUNT}:function:debate-dev-tub" \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$DEPLOYER" --action-names lambda:UpdateFunctionCode \
  --resource-arns "arn:aws:lambda:us-east-1:${ACCOUNT}:function:debate-prod-tub" \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$DEPLOYER" \
  --action-names lambda:UpdateFunctionConfiguration iam:PassRole s3:GetObject \
  --resource-arns '*' --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text

echo "== accounts on its own pool (expect allowed), and a sign-in as a student (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$ACCOUNTS" --action-names cognito-idp:AdminCreateUser \
  --resource-arns "arn:aws:cognito-idp:us-east-1:${ACCOUNT}:userpool/${POOL_ID}" \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$ACCOUNTS" \
  --action-names cognito-idp:AdminInitiateAuth cognito-idp:AdminUpdateUserAttributes \
  --resource-arns "arn:aws:cognito-idp:us-east-1:${ACCOUNT}:userpool/${POOL_ID}" \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
```
Success looks like: `allowed` on the deployer's own function and the accounts set's
`AdminCreateUser`; `implicitDeny` on everything else.

## Step 10 — Sign in on dev, and record the managed login's asset hosts

School IT will allow the pilot's hostnames and nothing else (ADR-0019 (a) 7), so every host the
managed login pages load from has to be on the request. The documentation names none beyond the
login host, so they are measured here, on dev, with the browser's network panel open.

This needs a dev account: the maintainer's own, in the `coach` group, made with the coach's
`tub users add` (`v1-e39-t05`, [the accounts guide](../guides/evidence-search-accounts.md)). Its
temporary password is printed once; you set a new one at the first sign-in. On 2026-10-19, before
`tub users` existed, this account was made with `aws cognito-idp admin-create-user`; if yours
exists already, run `tub users reset` in place of `add` for a new temporary password.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
export TUB_USER_POOL_ID="$POOL_ID"
uv run debate-research tub users add "$PILOT_USERNAME" --role coach --env dev
```
Success looks like `Created <your dev username> (coach).` and a temporary password, shown that once.
The command runs as `debate-dev-tub-accounts` and writes one record to the audit group's
`tub-users` stream.

Then, in Chrome on your Mac, in an **Incognito** window (⌘⇧N). A normal window logs the new-tab
page's Google traffic as well, and its saved managed-login session would skip the very pages this
step measures.

1. Open DevTools (⌥⌘I), the **Network** tab. Tick **Preserve log** and **Disable cache**.
2. Open `https://tub.dev.wfbdebate.com/` in that window. The pilot sends you to managed login.
3. Sign in with `$PILOT_USERNAME` and the temporary password, set a new password of at least 12
   characters, and set up the authenticator app: scan the QR code with an authenticator on your
   phone and enter its code.
4. You land back on `https://tub.dev.wfbdebate.com/`, signed in: the page says *Signed in as* your
   dev username. (Before `v1-e39-t05` was deployed, the callback answered `{"detail":"Not Found"}`,
   which still showed the redirect reached the pilot through CloudFront.)
5. Save the log: the Network toolbar's download arrow (Export HAR), as `tub-signin-1.har` in
   Downloads.
6. Sign out with the page's *Sign out* button, close the Incognito window, open a new one, and
   repeat steps 1 and 2. Sign in with the new password and an authenticator code: the ordinary
   sign-in. Save that log as `tub-signin-2.har`.

Then list the distinct hosts the two sign-ins loaded, with what each served and what loaded it.
The HAR files hold the sign-in form data, password included, so the same block deletes them.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
python3 - "$HOME/Downloads/tub-signin-1.har" "$HOME/Downloads/tub-signin-2.har" <<'PY'
import collections
import json
import sys
from urllib.parse import urlparse

seen = collections.defaultdict(lambda: [set(), set()])
for path in sys.argv[1:]:
    entries = json.load(open(path))["log"]["entries"]
    for entry in entries:
        host = urlparse(entry["request"]["url"]).hostname
        if not host:
            continue
        seen[host][0].add(entry.get("_resourceType", "?"))
        initiator = entry.get("_initiator", {})
        source = initiator.get("url") or ""
        if not source:
            frames = initiator.get("stack", {}).get("callFrames", [])
            source = frames[0]["url"] if frames else ""
        seen[host][1].add(urlparse(source).hostname or initiator.get("type", "?"))
for host in sorted(seen):
    types, sources = seen[host]
    print(f"{host}\t{','.join(sorted(types))}\tloaded by: {','.join(sorted(s for s in sources if s))}")
PY
rm -f "$HOME/Downloads/tub-signin-1.har" "$HOME/Downloads/tub-signin-2.har"
ls "$HOME/Downloads" | grep -c tub-signin
```
Success looks like:

- the managed login page rendered (a form for the username and password, in Cognito's default
  style), and the password change and the QR code were offered;
- one line per host, ending in `0` (both files deleted).

On 2026-10-19 the list was `auth.tub.dev.wfbdebate.com`, `tub.dev.wfbdebate.com` and three
`*.cloudfront.net` hosts. If any Google host appears (`ogs.google.com`, `*.gstatic.com`), it was
loaded by Chrome's new-tab page, not by the login: its "loaded by" column traces back to
`ogs.google.com`. Fill in [The managed login's asset hosts](#the-managed-logins-asset-hosts).

## Step 11 — Prod

The same sequence, with two differences: **the deploys run from a `main` worktree**, which the
deploy script enforces (a clean `main` equal to `origin/main`, ADR-0013), and so the prod function
can only be created after this task has been merged to `dev` and promoted to `main`. The targeted
apply can run before that.

Read every prod plan as carefully as dev's: it is the same 1, then 41, resources under
`module.evidence_search`, with prod's names, and nothing else changes.

**11a — The repository alone** (as step 1):

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/prod init
terraform -chdir=infrastructure/envs/prod apply -target=module.evidence_search.aws_ecr_repository.function
```
Success looks like `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.`

**11b — The first prod deploy**, from a `main` worktree after the promotion. `MAIN_WT` is that
worktree, set up as the [team website runbook's deploy worktrees](team-website.md#the-deploy-worktrees)
are, including `uv sync --all-packages` after every pull.

**Operator command** (expected runtime ~3 min)
Where: the `main` worktree
```bash
MAIN_WT=/path/to/your/main/worktree
cd "$MAIN_WT"
git pull --ff-only
uv sync --all-packages
TUB_DEPLOY_PROFILE=debate-admin scripts/tub_deploy.sh prod
```
Success looks like `clean, on main, and equal to origin/main.`, a pushed `debate-prod-tub@sha256:`
digest, and the message that the function `debate-prod-tub` does not exist yet.

**11c — Apply prod in full** (as step 3), from `$WT` if it is now the merged checkout, or from
`MAIN_WT`:

**Operator command** (expected runtime ~25 min)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/prod apply
```
Success looks like `Apply complete! Resources: 41 added, 0 changed, 0 destroyed.` and
`evidence_search_url = "https://tub.wfbdebate.com/"`.

**11d — The prod settings and keys.** Repeat steps 5 and 6 with prod's names:
`debate-prod-tub-audit`, `auth.tub.wfbdebate.com`, `/debate-prod-tub/cookie-keys`, and `POOL_ID`
and `CLIENT_ID` read from `infrastructure/envs/prod`. Generate new keys for prod; never copy dev's.
Each read-back should match dev's, with prod's names.

**11e — Deploy prod as TubDeployer and check it** (as step 8, from `MAIN_WT`):

```bash
cd "$MAIN_WT"
scripts/tub_deploy.sh prod
curl -sS -o /dev/null -w '%{http_code} %header{cache-control}\n' https://tub.wfbdebate.com/
curl -sSI https://tub.wfbdebate.com/ | grep -i -c '^x-robots-tag:'
```
Success looks like the deploy ending `Deployed <sha> to prod: https://tub.wfbdebate.com/`, then
`302 private, no-store` (the redirect to managed login), then `0`: prod is not marked noindex. The direct call to prod's function
URL is refused exactly as in step 8. Repeat step 9 with prod's names.

No account is made in the prod pool here. Students' accounts are the coach's, with `tub users add`
([the accounts guide](../guides/evidence-search-accounts.md)).

## Step 12 — The web-filter request to school IT

School IT allows the prod hostnames and nothing else (ADR-0019 (a) 7): the pilot host, the login
host, and any other host [step 10](#step-10--sign-in-on-dev-and-record-the-managed-logins-asset-hosts)
found, written with its prod name where it has one. Never the dev hostnames: dev holds no student.
The authenticator app runs on the student's phone and needs no hostname.

**First, confirm the asset hosts on prod's login page.** The three `*.cloudfront.net` hosts were
measured on dev's login page. AWS does not document whether every pool's managed login uses the
same ones, so prod's page is checked before the request goes out. No account is needed: loading
the login page is enough. In an Incognito window with the Network panel open, as in step 10, open
the URL this prints. Save the log as `tub-prod-login.har` in Downloads, and run step 10's listing
command with `"$HOME/Downloads/tub-prod-login.har"` in place of the two files, and that file in its
`rm` line.

```bash
cd "$WT"
PROD_CLIENT_ID=$(terraform -chdir=infrastructure/envs/prod output -raw evidence_search_client_id)
echo "https://auth.tub.wfbdebate.com/oauth2/authorize?response_type=code&client_id=${PROD_CLIENT_ID}&redirect_uri=https%3A%2F%2Ftub.wfbdebate.com%2Fauth%2Fcallback&scope=openid"
```
Success looks like: `auth.tub.wfbdebate.com` and the same three `*.cloudfront.net` hosts as the
[table](#the-managed-logins-asset-hosts). If prod lists different ones, send prod's.

Then send the request. The text, with the hosts as confirmed on prod:

```text
Subject: Web filter request: the debate team's evidence search

Hello,

The debate team's evidence search tool, approved for students by the activities director, needs
these hostnames allowed through the school web filter on student Chromebooks:

tub.wfbdebate.com
auth.tub.wfbdebate.com
dnh6qh3zeqkj3.cloudfront.net
d14wtojjlkahd9.cloudfront.net
d2gc27jy00o0yk.cloudfront.net

All five serve HTTPS only. The last three are Amazon Web Services' content network, which serves
the sign-in page's scripts, styles and images. Nothing needs installing, and students sign in with
an account the coach creates; no Google or school account is used.

Thank you,
```

Success looks like: IT's confirmation, and a Chromebook on the school network that opens
`https://tub.wfbdebate.com/` and shows the sign-in page at `auth.tub.wfbdebate.com`. Record the date.

## The managed login's asset hosts

Measured on dev in step 10. Each host here goes on the school IT request in step 12 under its prod
name.

| Host seen on dev | What it served | Prod name for the IT request |
|---|---|---|
| `auth.tub.dev.wfbdebate.com` | The login pages (document) and their own requests (fetch) | `auth.tub.wfbdebate.com` |
| `dnh6qh3zeqkj3.cloudfront.net` | The managed login's scripts and stylesheets | The same host, confirmed on prod's login page first (step 12) |
| `d14wtojjlkahd9.cloudfront.net` | A stylesheet, the login theme | The same host, confirmed on prod's login page first (step 12) |
| `d2gc27jy00o0yk.cloudfront.net` | Images, loaded by the login page's scripts | The same host, confirmed on prod's login page first (step 12) |
| `tub.dev.wfbdebate.com` | The callback page the sign-in returns to | `tub.wfbdebate.com` |

Measured 2026-10-19 over a first sign-in (password change and authenticator setup) and an ordinary
one. The capture also held `ogs.google.com`, `www.gstatic.com`, `fonts.gstatic.com`,
`ssl.gstatic.com`, `lh3.googleusercontent.com`, `play.google.com` and `accounts.google.com`. Every
one of them traced back to `ogs.google.com`, the account widget of Chrome's new-tab page, so none is
the login's, and none goes on the request.

## What to record

Fill these in as the steps complete; they are the evidence the spec's criteria and ADR-0019 ask
for.

| Item | dev | prod |
|---|---|---|
| Step 3 / 11c apply: resources added | 41 in four applies on 2026-10-19: 1 (step 1), 4 (the SES identity ahead of step 3), 22, then 15 with the app client replaced after the provider bug fixed in `beafdbe` | |
| 4: SES request sent; answer and date (one request covers both) | Sent 2026-10-19; review `PENDING`; `SendQuota` `50000.0 14.0 HEALTHY`, so already out of the sandbox | n/a |
| 5a: `deletion-protection` read-back | `debate-dev-tub-audit 400 True` | |
| 5b: branding read-back | Branding id returned; `UseCognitoProvidedValues` `True` | |
| 5c: domain security policy read-back | `ACTIVE 2 TLS_V1_2_2021` at the first read-back; no update needed | |
| 6: cookie keys version and check | `2`; `['current', 'previous'] True` | |
| 8: deploy digest | `debate-dev-tub@sha256:7ddc815bbda13a5e60676abfaa3514f299bb66366ae8661f067b68bb2cbd0e9a` (commit `47bf8a2`) | |
| 8: through CloudFront (code, cache-control) | `200 private, no-store`; all six headers as expected | |
| 8: direct function URL (code, body) | `403` `{"Message":"Forbidden"}`, for `/healthz` and `/` | |
| 8: init durations from `REPORT` lines | 4,115 ms (first environment after the deploy), 1,848 ms; 81–82 MB used | |
| 10: managed login rendered; asset hosts recorded | Rendered; both sign-ins reached the callback; hosts in the table above | n/a |
| 12: IT request sent; confirmed and date | n/a | |

## Rolling back a deploy

The repository keeps the last five images. To go back, point the function at an earlier digest,
read from the repository by an identity that may list it (the deployer cannot):

```bash
export AWS_PROFILE=debate-admin
aws ecr describe-images --region us-east-1 --repository-name debate-dev-tub \
  --query 'reverse(sort_by(imageDetails,&imagePushedAt))[].[imagePushedAt,imageDigest,imageTags[0]]' --output text
```
Then, with the digest you want:

```bash
ROLLBACK_DIGEST='sha256:the-digest-from-the-list'
ACCOUNT=$(aws sts get-caller-identity --profile debate-dev-tub-deployer --query Account --output text)
aws lambda update-function-code --profile debate-dev-tub-deployer --region us-east-1 --function-name debate-dev-tub \
  --image-uri "${ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/debate-dev-tub@${ROLLBACK_DIGEST}" \
  --query LastUpdateStatus --output text
aws lambda wait function-updated --profile debate-dev-tub-deployer --region us-east-1 --function-name debate-dev-tub
curl -sS https://tub.dev.wfbdebate.com/healthz
```
Success looks like `InProgress`, then `{"status":"ok"}`. For prod, the same with prod's names.

## What this runbook deliberately does not do

- **Create a student's account.** That is the coach's `tub users add`, in prod
  ([the accounts guide](../guides/evidence-search-accounts.md)). The dev pool never holds a student.
- **Publish an index.** `tub index publish` is `v1-e39-t02`'s, under the `EvidenceOperator`
  profile. The weekly agent run rebuilds the index when the parsed store changed and publishes it to
  dev (`v1-e39-t09`); publishing it to prod is the operator's, with `tub index publish --newest`, as
  [Publishing a pending index by hand](caselist-scheduled-sync.md#publishing-a-pending-index-by-hand)
  says.
- **Turn on access logging, a WAF or a second origin.** The pilot keeps no per-request record of a
  student's address, and CloudFront reaches nothing but the function (ADR-0019 (a) 4).
- **Change the evidence bucket.** Its Block Public Access settings and policy are untouched; the
  function reads through its role.

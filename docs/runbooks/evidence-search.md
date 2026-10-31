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
which may read `reports/tub/search/*`, `reports/landscape/*`, current objects under `raw/` and the
suppression list, and list `reports/landscape/` only (`v1-e39-t17`); nothing else. **The dev pool holds the maintainer and synthetic users only, never a student**
(ADR-0013), except at most two pilot validation students until the pilot's promotion to prod, whose
dev accounts the coach removes then (data-use policy 1.18).

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
| [Dev's smoke checks](#devs-smoke-checks-v1-e39-t10) | What validate-dev checks in dev with no account, and running it by hand | `$WT` |
| [The journey](#the-signed-in-journey-on-dev) | The signed-in journey on dev, with the synthetic seed in and out of dev's index | your Mac and `$WT` |
| [Promotion](#promoting-the-pilot-to-prod) | Everything prod needs before the coach's beta, in order, across the pilot's tasks | your Mac, `$WT` and the `main` worktree |
| [The beta](#the-coachs-beta-v1-e39-t10) | The coach's beta checklist on prod, after the promotion | a school Chromebook, and Word |
| [The app log](#measuring-the-pilot-from-the-app-log-v1-e39-t10) | Query time, cold-start index load and peak `/tmp`, from the app log | the CloudWatch console |

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
delete the repeated lines. The budget line is optional (the root falls back to the owner's address
without it), so a file that has only the deployer and accounts lines prints `2` and is also correct;
dev's file was written that way. `git status` still reports a clean tree; these files are gitignored.

**Every later apply needs the same lines, from whichever worktree it runs.** A task's follow-up
that applies another module (the evidence store's listing grant, for example) from a worktree whose
`owner.auto.tfvars` lacks the pilot's lines plans to destroy the `TubDeployer` and `TubAccounts`
assignments. Before any `terraform apply` in `dev` or `prod`, that root's file must hold both the
`evidence_search_deployer_user_names` and the `evidence_search_accounts_user_names` lines (the
budget line is optional), which this prints as `2`:

```bash
grep -c -E 'evidence_search_(deployer|accounts)_user_names' infrastructure/envs/dev/owner.auto.tfvars infrastructure/envs/prod/owner.auto.tfvars
```

A plan that destroys an account assignment means the file is missing or stale: stop and fix the
file, never apply (seen on dev on 2026-10-20; added by the PM, 2026-10-21; the count corrected by
the PM, 2026-10-22, since dev's file has no budget line).

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
for KEY in reports/tub/search/current.json reports/landscape/example26/2026-01-05/report.md raw/example/file.docx manifests/_suppression/suppression-list.jsonl; do
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
aws iam simulate-principal-policy --policy-source-arn "$ROLE" --action-names s3:ListBucket \
  --resource-arns "$BUCKET" --context-entries ContextKeyName=s3:prefix,ContextKeyValues=raw/,ContextKeyType=string \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text

echo "== the one listing it may make, of the landscape bundles (expect allowed)"
aws iam simulate-principal-policy --policy-source-arn "$ROLE" --action-names s3:ListBucket \
  --resource-arns "$BUCKET" --context-entries ContextKeyName=s3:prefix,ContextKeyValues=reports/landscape/,ContextKeyType=string \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text

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
Success looks like: `allowed` for the four reads, the landscape listing, the two log actions and
`ssm:GetParameter`; `implicitDeny` for everything else, including `parsed/`, a listing with no
prefix and a listing of `raw/`; and an empty line for the attached policies. Any `allowed` in the
second, fifth or sixth group means the role is wider than the table: stop. Before `v1-e39-t17` the
role had three reads and no listing at all.

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

## Dev's smoke checks (`v1-e39-t10`)

validate-dev's `cloud` job checks the pilot in dev on every run, through CloudFront, with no account:
`tests/smoke/cloud -m "live and dev"`. Eight `GET` requests, none signed in: `/healthz` answers
`{"status":"ok"}`; `/`, a search and `/account` asked for without a session are sent, `302`, to
`https://auth.tub.dev.wfbdebate.com/oauth2/authorize` with the pilot's callback; `/signed-out` links
`app.js` and `app.css` at content-hashed paths served `public, max-age=31536000, immutable`, and a
stale digest is `404`; and every answer carries CloudFront's Content-Security-Policy. The workflow
holds no secret, no AWS credential and no TOTP seed. It checks what dev serves, whichever commit was
last deployed there, so a pilot that is down in dev turns `validate-dev` red.

To run the same checks by hand, after a deploy to dev or to confirm a red `cloud` job:

**Operator command** (expected runtime ~10 s)
Where: `$WT`
```bash
cd "$WT"
uv run pytest tests/smoke/cloud -m "live and dev" -n 0 -p no:randomly
```
Success looks like `3 passed`. A failure names the request and what came back, for example
`GET /search?q=reserve+margin: 200` (a page answered without a session) or a CSP that is not the
distribution's.

## The signed-in journey on dev

What only a signed-in debater sees is checked by `scripts/tub_dev_journey.py`, which opens a Chromium
window and waits for **you to sign in** on managed login's own page with your dev account (step 10's)
and the code your authenticator app shows. Nothing stores a password, a seed or a session: the window's
profile is new and is deleted when the script ends. It then searches the dev seed's card, opens it,
copies it and downloads it; after a removal, a second command checks the card is gone.

Run it before the coach's beta, and after a deploy to dev that changes the pages. It needs the seed in
dev's index, which this section puts there by the ordinary commands and takes out again at the end,
because the weekly run indexes only the caselists it follows and its shrink guard refuses an index that
drops a store dev's current one holds: left in, the seed would stop the next Wednesday's publish.

**The seed.** One weekly archive of the synthetic caselist `testcl26`, dated 2026-10-27, three files
from three invented schools (Quillfern Academy, Ostrander Vale, Brindlecote High), each a structural
fixture of the repository (`tests/fixtures/debate_files/structural/`), so no real disclosure is in
it. `testcl26` is a slug `tub index build` accepts (`v1-e39-t22`) and no weekly run follows
(`caselist.sync_caselists` is `hsld26`, `hspolicy26`, `hspf26`), so no run imports into it, restores
it, indexes it or gives it a landscape report, and nothing of it reaches a real caselist's report.
Dev's `testcl26` already holds `RM-2026-90`'s synthetic weeks, up to 2026-09-29; none of their schools
is reused. The seed indexes to **2 documents** and 4 occurrences: one card in all three files, and the
card the journey opens, *Reserve margins are already below the planning standard*, in the Quillfern
Academy file alone, which is the file the removal takes.

**Where the stores come from.** Since the cutover the cloud run holds dev's state, and this Mac's data
directory no longer holds the weeks the cloud ran. So the index is built from a working copy restored
from the dev bucket (`caselist restore-run-state`, as for a hand publish to prod), the seed imported
into that copy, and the copy deleted at the end (data-use policy 1.18). Every block that writes runs
with the copy named for that one command (`env DEBATE_STORAGE__DATA_DIR=...`), so no override is left
set. Do it all in one terminal window, not on a Wednesday, and not while a cloud run holds the lock.

Once: `uv run playwright install chromium`, in `$WT`.

**Once, before J1: the seed's names are no real school's** (PM ruling 2026-11-01). The seed's three
school names and its tournament are invented; this checks that no disclosed path in this Mac's
manifests holds any of them. It prints a count, never a path or a name.

**Operator command** (expected runtime seconds)
Where: any terminal
```bash
grep -rliE 'quillfern|ostrander|brindlecote|lanternfield' "$HOME/.debate-research/dev/manifests" | grep -v '/testcl26/' | wc -l
```
Success looks like `0`. Anything else: stop and tell the PM, who renames the seed before it reaches
dev.

### J1 — Write the seed

**Operator command** (expected runtime seconds; writes one file under your home directory)
Where: `$WT`
```bash
cd "$WT"
uv run python scripts/tub_dev_journey.py seed --out "$HOME/tub-journey-seed"
```
Success looks like, as of `v1-e39-t10`:

```text
archive /Users/<you>/tub-journey-seed/testcl26-2026-10-27.zip
archive sha256 494c3359887c43ac5236c6d0f51701c6f978580efe9cb7c290451a0116948657
caselist testcl26, snapshot 2026-10-27
remove b3afe1c4f57df962b3200ec08b3d1efe023c0243a9b31154f787348864036fa8  Quillfern Academy/QfAn/...
keep   0cf11d8ceb4127b9cece994680afba6d38771a41d1b920ee508af25c0a7c0ab6  Ostrander Vale/OvTe/...
keep   dcb67b1adf100a78da2f7e96969b9e7d1e555eeddbe64be019f034a922a20268  Brindlecote High/BrHo/...
```
The `remove` line's sha256 is `REMOVE_SHA` in J7. The script writes the same bytes every time, so
running it again changes nothing.

### J2 — Restore a working copy from the dev bucket

It holds the dev lock while it restores and writes nothing to the bucket but the lock. About 10 GB.
It stops if a pull is running, a `DEBATE_*` override is set, or it is Wednesday.

**Operator command** (expected runtime several minutes)
Where: your Mac, the window you keep to J10
```bash
COPY="$HOME/.debate-research/dev-journey-copy"
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set (above), or it is Wednesday, the cloud run's day"
else
  aws sso login --profile debate-dev-evidence
  cd "$HOME" && env DEBATE_ENV=dev debate-research caselist restore-run-state --into "$COPY"
  ls "$COPY/debate-research-restored-copy.json"
fi
```
Success looks like the restore's summary and then the marker's path. `RUN_LOCK_HELD`: a cloud run is
going; wait for it (`debate-research caselist runs --remote --last 1`) and run the block again.

### J3 — Import the seed into the copy

Every block from here starts with the same check, and stops unless `COPY` names a restored copy.
First the dry run, which writes nothing:

**Operator command** (expected runtime seconds)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research caselist import \
    "$HOME/tub-journey-seed/testcl26-2026-10-27.zip" --caselist testcl26 --snapshot 2026-10-27 --dry-run
fi
```
Read: **3** members, **3** first seen, nothing skipped, held or warned about. Anything held at a
removed path means the seed reuses a path `RM-2026-90` removed: stop. `SnapshotOutOfOrder` means
`testcl26` has a week after 2026-10-27: stop, and take it to the PM. Then the import, which writes the
copy only:

**Operator command** (expected runtime seconds)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research caselist import \
    "$HOME/tub-journey-seed/testcl26-2026-10-27.zip" --caselist testcl26 --snapshot 2026-10-27
fi
```
Success looks like the same counts, now applied: 3 members, 3 first seen, 3 newly stored.

### J4 — Publish the seed's week, then parse it

The function downloads a card from the bucket's `raw/`, so the seed's sources go there. The dry run
first:

**Operator command** (expected runtime seconds)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research caselist publish \
    --caselist testcl26 --snapshot 2026-10-27 --dry-run
fi
```
Read: every planned upload is `testcl26`'s: its 2026-10-27 manifest and the seed's **3** sources
under `raw/caselist/testcl26/`. Anything of another caselist: stop. Then the publish, and the parse of
the copy, which writes the copy only and is the plan of the next block's publish:

**Operator command** (expected runtime ~1 min)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research caselist publish \
    --caselist testcl26 --snapshot 2026-10-27
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research caselist parse --caselist testcl26
fi
```
Success looks like the publish making the uploads its dry run planned, then the parse's table with
**Sources 3**, **Parsed 3** and **Cards 4**, and the version it wrote. `--publish-only` takes no
`--dry-run`: that table is its plan, and it publishes that version directory of `testcl26` and nothing
else. Anything but those counts: stop. Then its aggregates to the bucket, so a removal finds them:

**Operator command** (expected runtime seconds)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research caselist parse \
    --caselist testcl26 --publish-only
fi
```
Success looks like `parsed/testcl26/<version>/` published, its uploads above zero.

### J5 — Build dev's index with the seed, and check it before it is published

The build indexes the stores dev's current index holds, read from its manifest, and `testcl26`, from
the copy. It writes the copy only. The check then compares the new manifest with the current one: every
store dev's index holds must be the same store (its `occurrences_sha256`), the suppression list the
same list, and `testcl26` must hold 2 documents. A copy that is behind the bucket, or a list the copy
lacks, stops here, before anything is published.

**Operator command** (expected runtime a few minutes, a rebuild of the full corpus)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  SEED="$HOME/tub-journey-seed"
  BUCKET=$(cd "$WT" && python3 -c 'import tomllib; print(tomllib.load(open("config/profiles/dev.toml", "rb"))["storage"]["s3"]["bucket"])')
  aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" "$SEED/current.json" --profile debate-dev-evidence
  MANIFEST_KEY=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["manifest_key"])' "$SEED/current.json")
  aws s3 cp "s3://${BUCKET}/${MANIFEST_KEY}" "$SEED/before-manifest.json" --profile debate-dev-evidence
  STORES=$(python3 -I -c 'import json, sys; print(" ".join("--caselist " + one["caselist"] for one in json.load(open(sys.argv[1]))["stores"]))' "$SEED/before-manifest.json")
  echo "dev's index holds: $STORES"
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research --json tub index build \
    ${=STORES} --caselist testcl26 > "$SEED/seeded-build.json"
  echo "build exit $?"
  python3 -I - "$SEED/before-manifest.json" "$SEED/seeded-build.json" <<'PY'
import json, sys
before = json.load(open(sys.argv[1]))
built = json.load(open(sys.argv[2]))["data"]["manifest"]
old = {one["caselist"]: one["occurrences_sha256"] for one in before["stores"]}
new = {one["caselist"]: one["occurrences_sha256"] for one in built["stores"]}
problems = [f"{name}: not the store dev's index holds" for name in old if new.get(name) != old[name]]
if built["suppression"]["sha256"] != before["suppression"]["sha256"]:
    problems.append("the suppression list is not the one dev's index read")
seeded = built["counts"]["documents_by_store"].get("testcl26")
if seeded != 2:
    problems.append(f"testcl26 holds {seeded} documents, not 2")
print("built", built["index_id"], "from", sorted(new))
print("\n".join("STOP: " + one for one in problems) or "OK: dev's stores and list, and the seed's 2 documents")
PY
fi
```
Success looks like `build exit 0`, the new index id with the stores and `testcl26`, then `OK: ...`. Any
`STOP` line: publish nothing, delete the copy (J10) and take the lines to the PM. Then the publish,
whose shrink guard passes because no store shrinks:

**Operator command** (expected runtime ~2 min)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  INDEX_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["directory"])' "$HOME/tub-journey-seed/seeded-build.json")
  echo "publishing $INDEX_DIR"
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research tub index publish --env dev --index "$INDEX_DIR"
fi
```
Success looks like the table ending in `reports/tub/search/current.json`, naming the index J5's check
printed. Dev's function loads it within five minutes.

### J6 — The journey

Five minutes after J5's publish:

**Operator command** (expected runtime ~3 min, most of it your sign-in)
Where: `$WT`
```bash
cd "$WT"
uv run python scripts/tub_dev_journey.py journey
```
Sign in when the window shows managed login. Success looks like one `PASS` line a step (sign in, search,
result count, open the card, provenance on the card page, back link, Copy card, the copy holds the card,
no provenance line in the copy, download offered, download), then `card path /cards/testcl26/<64 hex>`
and `journey: every step passed`. Keep the card path for J8. `FAIL download offered` means the index
was parsed by another parser than the one dev's function runs: parse and build with the build dev runs.
Record the result in the session report or `docs/data/evidence-search-pilot.md`.

### J7 — Remove the seed's Quillfern Academy file

The removal runbook's procedure, with `--source` and the exercise id `RM-2026-91` (exercise ids run
from 90, [the register](../data/caselist-removal-requests.md)), on this Mac's own data directory: in
bucket mode the removal restores the run's state first. **The dry run decides whether to go on.** The
run's state was saved by the cloud run, which never saw the seed's week (the seed went in through the
copy), so read the plan before anything else.

**Operator command** (expected runtime seconds)
Where: `$WT`, a new window, so `COPY` and no other variable is set
```bash
REMOVE_SHA=b3afe1c4f57df962b3200ec08b3d1efe023c0243a9b31154f787348864036fa8
if env | grep -q '^DEBATE_'; then
  echo "STOP: DEBATE_ overrides are set in this shell"
else
  cd "$WT" && DEBATE_ENV=dev uv run debate-research caselist remove --source "$REMOVE_SHA" --request RM-2026-91 --reason POLICY
fi
```
Go on only if **WILL BE REMOVED** lists that one file, with its object under `raw/caselist/testcl26/`
and its parsed files under `parsed/testcl26/`, and **SHARED, KEPT** nothing. If the plan does not
find the file, stop: publish the teardown (J9), delete the copy (J10), and take the plan to the PM.
Then the removal runbook's [step 5](caselist-removal.md#step-5--execute-in-dev), the same flags with
`--execute`, and its [P1b](caselist-removal.md#p1b--right-after-done-rebuild-the-parsed-stores-aggregates)
for each caselist the plan listed, `testcl26` among them. Note the time `DONE` printed. Add
`RM-2026-91` to the register as an operator exercise, as `RM-2026-90` is.

### J8 — Five minutes after `DONE`: the card is gone

**Operator command** (expected runtime ~2 min, most of it your sign-in)
Where: `$WT`
```bash
cd "$WT"
uv run python scripts/tub_dev_journey.py removed --card-path "/cards/testcl26/the-64-hex-J6-printed"
```
Success looks like `PASS the removed card's page`, `PASS the removed card is not in the results` and
`removed: every step passed`. The other seed card stays, without Quillfern Academy's line.

### J9 — Take the seed out of dev's index

Rebuild from the copy with the stores J5 read, without `testcl26`, and publish it past the shrink guard,
which refuses an index that drops a store: that is the one store it drops. The check compares the
stores with J5's `before-manifest.json`.

**Operator command** (expected runtime a few minutes)
Where: the window J2 to J5 ran in
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  SEED="$HOME/tub-journey-seed"
  STORES=$(python3 -I -c 'import json, sys; print(" ".join("--caselist " + one["caselist"] for one in json.load(open(sys.argv[1]))["stores"]))' "$SEED/before-manifest.json")
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research --json tub index build \
    ${=STORES} > "$SEED/teardown-build.json"
  echo "build exit $?"
  python3 -I - "$SEED/before-manifest.json" "$SEED/teardown-build.json" <<'PY'
import json, sys
before = json.load(open(sys.argv[1]))
built = json.load(open(sys.argv[2]))["data"]["manifest"]
old = {one["caselist"]: one["occurrences_sha256"] for one in before["stores"]}
new = {one["caselist"]: one["occurrences_sha256"] for one in built["stores"]}
print("built", built["index_id"], "from", sorted(new))
print("OK: the stores dev's index held before the seed" if new == old else "STOP: the stores are not the ones before the seed")
PY
fi
```
Success looks like `build exit 0` and `OK: ...`. Then the publish:

**Operator command** (expected runtime ~2 min)
Where: the same window
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
  echo "STOP: COPY does not name a restored copy; run J2 in this window"
else
  INDEX_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["directory"])' "$HOME/tub-journey-seed/teardown-build.json")
  cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research tub index publish --env dev \
    --index "$INDEX_DIR" --allow-shrink "v1-e39-t10 dev journey: the testcl26 seed taken out of the index"
fi
```
Success looks like the table ending in `current.json` naming the teardown index, and the shrink it
allowed naming `testcl26` alone. A shrink naming any other store: that store changed under the copy;
take it to the PM before Wednesday.

### J10 — Delete the copy

**Operator command** (expected runtime seconds)
Where: the same window
```bash
if [[ -f "${COPY}/debate-research-restored-copy.json" ]]; then
  rm -rf "$COPY" "$HOME/tub-journey-seed"
  ls -d "$COPY" 2>/dev/null | wc -l
else
  echo "STOP: COPY does not name a restored copy, so nothing is deleted"
fi
```
Success looks like `0`. The seed archive goes with it; J1 writes it again, the same bytes.

## Measuring the pilot from the app log (`v1-e39-t10`)

The function's app log, `debate-<env>-tub-app`, holds two lines that the measurements ADR-0019 (c) 6
and 7 ask for come from, and nothing about who searched or for what
([What a refusal looks like in the app log](#what-a-refusal-looks-like-in-the-app-log)):

* `INFO debate_core.application.search_index_holder: search index <id> loaded in <s> s: <n> bytes from a <m>-byte object; <t> bytes in its directory`,
  once each time an environment fetches an index: the cold start's index load, the SQLite file's
  bytes, the gzip object's bytes, and what the holder has on `/tmp` at that moment. At a replacement
  that moment is before the old file is deleted, so `<t>` is the peak: both files.
* `INFO debate_core.application.search_index_holder: search answered in <n> ms`, once each search,
  the index already loaded.

The queries below are CloudWatch Logs Insights queries, read-only, in the console (CloudWatch, Logs
Insights, log group `debate-dev-tub-app` or `debate-prod-tub-app`, a time range that covers the use).

**Query time, p50 and p95:**

```text
fields @timestamp, @message
| filter @message like /search answered in/
| parse @message "search answered in * ms" as ms
| stats count() as searches, pct(ms, 50) as p50_ms, pct(ms, 95) as p95_ms, max(ms) as max_ms
```

**The cold-start index load, and `/tmp` at each load:**

```text
fields @timestamp, @logStream, @message
| filter @message like /search index .* loaded in/
| parse @message "search index * loaded in * s: * bytes from a *-byte object; * bytes in its directory" as index_id, seconds, sqlite_bytes, gzip_bytes, directory_bytes
| sort @timestamp asc
```

A line whose `directory_bytes` equals its `sqlite_bytes` is a cold start's load into an empty
directory; one whose `directory_bytes` is larger is a replacement, and its `directory_bytes` is the
peak `/tmp` use across that replacement. The cold start as a whole, the runtime's own start included,
is in the `REPORT` lines' `Init Duration`, as in step 8:

```text
fields @timestamp, @message
| filter @message like /Init Duration/
| parse @message "Init Duration: * ms" as init_ms
| stats count() as cold_starts, pct(init_ms, 50) as p50_init_ms, max(init_ms) as max_init_ms
```

Record each as [docs/data/evidence-search-pilot.md](../data/evidence-search-pilot.md) asks: dev after
the journey, and prod after the beta's first week.

## Promoting the pilot to prod

The prod work is spread over several tasks' operator follow-ups. This is the one list, in order,
written in by the PM on 2026-10-22. Each item names where its commands are; none is repeated here.
Tick each in `docs/data/evidence-search-pilot.md` as yes or no with its date, before the coach's
beta (`v1-e39-t10`). Agreement 11 applies to every block: a dry run or plan first, read, then the
real run, in a window with no leftover `DEBATE_*` override.

1. **Promote `dev` to `main`** as [branching and environments](../process/branching-and-environments.md)
   says, then set up or update the `main` worktree ([step 11b](#step-11--prod)).
2. **Prod's `owner.auto.tfvars`** holds the deployer and accounts lines, checked with
   [Before you start](#before-you-start)'s `grep -c -E` command, before any prod plan.
3. **Step 11, in full.** Prod's plan applies everything merged since the last prod apply. Besides the
   pilot itself that includes `v1-e39-t05`'s email-second-factor group and the accounts role's
   `AdminRemoveUserFromGroup`, `v1-e39-t02`'s listing grant on `reports/tub/search/`,
   `v1-e39-t07`'s removal grant, and `v1-e31-t16`'s tagging grants on `parsed/`. Read the plan as
   dev's was read on 2026-10-22: every resource named, nothing destroyed, no account assignment
   touched.
4. **`v1-e29-t08`'s prod plan**, as its report's operator follow-ups say, if step 3 did not already
   cover it.
5. **Prod's suppression list exists** in the prod bucket, by the check `v1-e39-t07`'s runbook
   section gives. If it does not, create it as that section says before anything is published.
6. **Prod's parsed store is current.** Not from the Mac's dev data directory, which since the
   cutover no longer holds the weeks the cloud ran (PM ruling 2026-11-01, `v1-e39-t10` Q3): from a
   working copy restored from the dev bucket, published to prod as
   [the cutover runbook's "Until the promotion"](caselist-cutover.md#until-the-promotion-prod-is-published-by-hand)
   publishes by hand. It refuses if prod's suppression list stops anything the aggregates name, and
   then the store is rebuilt with `--publish` instead.
7. **Prod's first index**, built by `tub index build` from that same restored copy, checked against
   dev's current manifest as [the journey's J5](#the-signed-in-journey-on-dev) checks it (each
   store's `occurrences_sha256`, the suppression list's sha256), then published against prod, and its
   `current.json` read back. The copy is deleted afterwards (data-use policy 1.18).
8. **`v1-e39-t07`'s prod removal exercise**, with a synthetic source, then the aggregate rebuild its
   runbook section gives, judged by `Sources` equal to `Skipped` and above zero.
9. **Retire the superseded parsed directories in prod** (`2026.09.20-docx-1`, `2026.10.10-docx-2`,
   `2026.10.12-docx-3`, `2026.10.18-docx-5`) by [the retention runbook](parsed-store-retention.md)'s
   step 3, and record the counts in `docs/data/parsed-card-store.md`.
10. **Step 12**, the request to school IT, with prod's hostnames only.
11. **The coach creates the beta's prod accounts.** The two debaters who used dev on 2026-10-22 get
    new prod accounts; dev accounts are never carried over.
12. **Ask AWS for a higher Lambda bandwidth quota** for the prod function, as ADR-0019 (c) 7's
    revisit trigger says, before the gzipped index reaches 400,000,000 bytes (about 5 s of cold
    start at the 625 Mbps cap). On 2026-10-22 it was 314,054,035 bytes and growing about 11.6% a
    week, so about three weeks out. AWS takes time to answer, so the request goes in at the
    promotion. Added by the PM, 2026-10-22, from `v1-e39-t14`'s storage working. **Requested
    2026-10-31**, ahead of the promotion (PM ruling): quota `L-14320ECE`, "Network bandwidth per
    execution environment", 625 → 1,250 Mbps, one request for the one account that holds dev and
    prod; AWS opened a support case for it. The gzip object was 318,115,067 bytes that day. Check
    it with `aws service-quotas get-requested-service-quota-change --request-id <id>`, the id in
    `v1-e39-t10`'s report, and tick this item when it reads `APPROVED`.

## The coach's beta (`v1-e39-t10`)

On prod, after every item of [Promoting the pilot to prod](#promoting-the-pilot-to-prod) is ticked in
[docs/data/evidence-search-pilot.md](../data/evidence-search-pilot.md), `v1-e39-t07`'s prod removal
exercise (item 8) and prod's suppression list (item 5) among them. Not before: the beta is the
first time anyone but the maintainer uses prod. The coach runs it with the beta's testers, in prod
accounts the coach made (item 11); the two debaters who used dev on 2026-10-22 get new prod accounts,
never their dev ones.

The record is counts and yes or no, never a name, a username, a screenshot with a name in it, or a
quotation with an identity (data-use policy, E39 gate items 8 and 9). The coach keeps the screenshots;
the record says what they show. Each item below is one row of the beta's table in
`docs/data/evidence-search-pilot.md`.

**Each tester's first sign-in**, on their own device, with a screenshot of each managed-login page
(`v1-e39-t05`'s open finding):

1. Which second factors managed login offered: the authenticator app, the emailed code, or both.
2. Which one the tester chose.
3. Whether the pilot's own authenticator page (`/account/authenticator`) then appeared.
4. Whether the tester reached the search page signed in, without help.

**On a real school Chromebook**, on the school's network (moved here from `v1-e39-t06`, which had no
Chromebook on 2026-10-21):

5. Sign in.
6. Search for words in a tag, an author or a card's text; filter by event, caselist and side.
7. The result count above the results (`v1-e39-t11`).
8. Open a card. Its provenance line is on the card page.
9. *Back to results* returns to the same results (`v1-e39-t11`).
10. *Open on openCaselist* opens the team's page in a new tab (`v1-e39-t11`).
11. *Search by passage*: paste a sentence from a card, and that card is among the results (`v1-e39-t13`).
12. *Copy card*, then paste into Google Docs: bold, underline, highlighting and sizes kept.
13. The pasted card carries no provenance line (data-use policy 1.11).
14. *Download .docx* opens in Google Docs, and a cart of several cards downloads as one file
    (`v1-e39-t08`, closed; the operator confirmed both in Word with Verbatim and in Google Docs on
    2026-10-31).

**Once, on any computer with Word:**

15. *Copy card*, then paste into Word: formatting kept, yes or no.
16. A downloaded card opens in Word with Verbatim.

**Then the app log**, by the operator, from [Measuring the pilot from the app log](#measuring-the-pilot-from-the-app-log-v1-e39-t10)
for `debate-prod-tub-app` over the beta's days: the query time's p50 and p95, the cold-start index
loads, and the peak `/tmp` use across an index replacement if a weekly publish to prod fell inside the
beta. And the refusal lines' query from
[What a refusal looks like in the app log](#what-a-refusal-looks-like-in-the-app-log), which should
print nothing.

**What ends the beta.** Every item answered for every tester, the problems found either fixed and
deployed or written down as accepted by the coach, and the PM's go for the student pilot: three to
five debaters for at least a week, whose tallies and themes the same document records.

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

## What the function fetches, and when

ADR-0019 (c) 3 and 5, as `v1-e39-t06` and `v1-e39-t07` built them. The function holds no index in
its image. It reads four things from its own environment's evidence bucket, with `s3:GetObject` and
nothing else, and only when a request needs them:

| What | Key | When it is read | What an unchanged read costs |
|---|---|---|---|
| The suppression list | `manifests/_suppression/suppression-list.jsonl` | Before the pointer, at most five minutes apart | A conditional GET answered `304`, no body |
| The pointer | `reports/tub/search/current.json` | Right after the list, in the same pass | A conditional GET answered `304`, no body |
| The manifest | `reports/tub/search/<index id>/manifest.json` | When the pointer names an index this environment has not loaded | — |
| The index | `reports/tub/search/<index id>/search-index.sqlite.gz` | Right after its manifest, streamed through `gunzip` and `sha256` into `/tmp/tub-index` | — |

- **Who waits.** Only a request that searches or shows a card: a results page, a card page, a copy
  and, from `v1-e39-t08`, a download. Sign-in, the callback, `/healthz`, the account page and the
  empty search page never read anything from the bucket, so a cold environment answers them at once.
- **Five minutes.** The first such request in a new environment reads the list, then the pointer,
  then fetches the index. After that, the first such request five minutes or more after the last
  check reads the list and the pointer again before it is answered. An environment Lambda froze for
  an hour does the same on its first request after thawing, so it never answers from a list or a
  pointer older than five minutes. A removal is therefore hidden within five minutes, and a weekly
  publish is picked up within five minutes, by each environment on its next request.
- **A new pointer.** The environment fetches the new index to a new file, checks both digests and
  the size against the manifest, swaps to it and deletes the old file once no request is reading it.
  That is one cold-start-length wait, once per environment per publish.
- **What the list does.** Every request that searches or shows a card hides each occurrence the
  list stops, by its source's sha256 or its disclosure digest. A card whose representative occurrence
  is stopped answers as not found until the next build chooses another; any other stopped occurrence
  leaves the card without its provenance line, with its file count recounted (and its team count
  dropped when the survivors cannot say which teams are left). A path hold is not read by the
  function: a removal that only holds a path is followed by a rebuild and publish straight away
  ([removal runbook, the student search pilot](caselist-removal.md#the-student-search-pilot-e39)).

**The list must exist before anyone searches.** The function may not list the bucket, so S3 answers
its read of a key that does not exist with `AccessDenied`, the same as a failure. The function then
refuses every search and card page, as it must for a list it cannot read. An environment that has
had a removal has the list; dev has had one since `RM-2026-90`. Check before the first deploy to an
environment, and before the pilot opens there:

**Operator command** (expected runtime seconds)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
for env in dev prod; do
  BUCKET=$(terraform -chdir="infrastructure/envs/$env" output -raw evidence_bucket_name)
  aws s3api head-object --bucket "$BUCKET" --key manifests/_suppression/suppression-list.jsonl \
    --query '[ContentLength,ServerSideEncryption]' --output text \
    || echo "NO LIST in $env: create it below before the pilot opens there"
done
unset AWS_PROFILE
```
Success looks like a size and `aws:kms` for each environment.

If an environment has no list, create it empty under the takedown profile, which is the one
credential that may write there, encrypted with the bucket's key as its policy requires. An empty
list stops nothing and every reader accepts it; the first removal appends to it.

**Operator command** (expected runtime seconds; changes the bucket)
Where: `$WT`. Set `ENV` to the environment the check named.
```bash
cd "$WT"
ENV=prod
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/$ENV" output -raw evidence_bucket_name)
KEY_ARN=$(AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/$ENV" output -raw evidence_kms_key_arn)
aws sso login --profile "debate-$ENV-evidence-removal"
aws s3api put-object --profile "debate-$ENV-evidence-removal" --bucket "$BUCKET" \
  --key manifests/_suppression/suppression-list.jsonl --body /dev/null \
  --server-side-encryption aws:kms --ssekms-key-id "$KEY_ARN" --if-none-match '*'
```
Success looks like an `ETag` and `"ServerSideEncryption": "aws:kms"`. `--if-none-match '*'` makes
S3 refuse the write with `PreconditionFailed` if a list appeared in the meantime, so an existing
list is never replaced.

## What an identical rebuild records beside the manifest

`v1-e39-t19`. An index id is the start of its SQLite file's sha256, so a weekly run that rebuilds
under a longer suppression list, whose new entries stop nothing in the corpus, gets the same index
id. The stage does not publish it again: `current.json` already names it, and no object of the index
is uploaded twice. The published `manifest.json` therefore goes on naming the list the index was
first built from. The cutover's comparison found exactly that: a manifest recording five entries
after `RM-2026-90` had made six.

So when `current.json` already names the index a run built or kept, and that run read other digests
than the manifest records (the suppression list's, or a store's occurrence rows), the stage writes
one more object beside the manifest:

| Key | What it holds |
|---|---|
| `reports/tub/search/<index id>/checked-against.json` | What that run's rebuild read: the parser version, each store's version directory and occurrence digest, the suppression list's entries, path holds and sha256, and the counts. And `manifest_sha256`, the digest `current.json` names the manifest with |

- **Which list an index was checked against** is the record's when there is one whose
  `manifest_sha256` is the digest `current.json` names, and the manifest's otherwise. A record
  naming another digest is left over from before the same index was published again, and says
  nothing about the manifest there now.
- **When it is written.** Only when what the run read differs from what the manifest, or the
  record already there, says. A run under the same list writes nothing. It is written through the
  same bucket client as the index, so in bucket mode under the run's lock: a run that lost its
  lease writes no record, and its index stage fails with the reason.
- **Who reads it.** `caselist restore-run-state` brings it back beside the restored manifest, and
  `ops/caselist_run/compare_cloud_run.py` reads it there, so a comparison of an identical rebuild
  under a longer list agrees. The function never reads it: it reads the three keys `current.json`
  names. `tub index prune` keeps it with the current index's directory, and deletes it with a
  superseded one, like the index's other files. It holds counts, digests, slugs and versions, and
  no card, path, school or team code.

To read it by hand, for a removal's audit or a comparison:

**Operator command** (expected runtime seconds; reads only)
Where: `$WT`. Set `ENV` to the environment to read.
```bash
cd "$WT"
ENV=dev
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/$ENV" output -raw evidence_bucket_name)
aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" - --profile "debate-$ENV-evidence" > /tmp/tub-current.json
INDEX_ID=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["index_id"])' /tmp/tub-current.json)
aws s3 cp "s3://${BUCKET}/reports/tub/search/${INDEX_ID}/checked-against.json" - --profile "debate-$ENV-evidence" \
  || echo "no record beside ${INDEX_ID}'s manifest: the manifest says what it was checked against"
python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["manifest_sha256"])' /tmp/tub-current.json
rm /tmp/tub-current.json
```
Success looks like the record's JSON, then a sha256. The record applies when its `manifest_sha256`
is that last line, and its `suppression.entries` is then the list the published index was last
checked against. Without a record, `aws s3 cp` prints a `404` and the line after it.

## Moving the index to format 2

`v1-e39-t13` changed the index's format from 1 to 2: its words are stemmed, so `grow` finds
`growing`, and search by passage needs it ([the index's data model](../data/search-index.md#the-schema-format-version-2)).
A function from `v1-e39-t13` on reads both formats; an older one reads format 1 only and refuses a
format 2 index. So the function goes first and the index second, in this order, once in dev after
the task merges and once in prod at its promotion. Agreement 11 applies to every block: a dry run or
a comparison first, read, then the real run, in a window with no leftover `DEBATE_*` override.

**1. Deploy dev's function**, from `$WT` on `dev` after the merge, with its environment synced
([Before you start](#before-you-start)). First the rehearsal, which builds the image and calls no AWS:

**Operator command** (expected runtime ~3 min)
Where: `$WT`
```bash
cd "$WT"
git pull --ff-only
uv sync --all-packages
scripts/tub_deploy.sh dev --dry-run
```
Success looks like the image built and the script stopping before the push. Then the deploy:

**Operator command** (expected runtime ~3 min; changes dev's function)
Where: `$WT`
```bash
cd "$WT"
scripts/tub_deploy.sh dev
```
Success looks like [step 8](#step-8--deploy-dev-as-tubdeployer-and-check-it-through-cloudfront)'s
`{"status":"ok"}` and `Deployed <sha> to dev`. Then sign in on dev and search for `zephyr`, or any
word: the results carry a count above zero and the line *Until the next weekly update of the
search, words are matched exactly as typed*. That line says the new function is serving the format
1 index; a count above zero says it is serving one at all.

**2. Build format 2 and compare it with the published index.** This builds every store the
published index holds, reads both manifests, and publishes nothing. A build of the whole dev store
took about 305 s on 2026-10-22.

**Operator command** (expected runtime ~6 min)
Where: `$WT`
```bash
cd "$WT"
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  BUCKET=$(python3 -c 'import tomllib; print(tomllib.load(open("config/profiles/dev.toml", "rb"))["storage"]["s3"]["bucket"])')
  FORMAT_TWO=$(mktemp -d)
  aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" "${FORMAT_TWO}/current.json" --profile debate-dev-evidence
  MANIFEST_KEY=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["manifest_key"])' "${FORMAT_TWO}/current.json")
  aws s3 cp "s3://${BUCKET}/${MANIFEST_KEY}" "${FORMAT_TWO}/current-manifest.json" --profile debate-dev-evidence
  STORES=$(python3 -c 'import json, sys; print(" ".join("--caselist " + one["caselist"] for one in json.load(open(sys.argv[1]))["stores"]))' "${FORMAT_TWO}/current-manifest.json")
  echo "building: ${STORES}"
  DEBATE_ENV=dev uv run debate-research --json tub index build ${=STORES} > "${FORMAT_TWO}/build.json"
  python3 - "${FORMAT_TWO}/current-manifest.json" "${FORMAT_TWO}/build.json" <<'EOF'
import json, sys
current = json.load(open(sys.argv[1]))
envelope = json.load(open(sys.argv[2]))
if not envelope.get("data"):
    print("STOP: the build failed:", (envelope.get("error") or {}).get("code"))
    raise SystemExit(1)
built = envelope["data"]["manifest"]
print("current index", current["index_id"], "format", current["format_version"], current["counts"]["documents"], "documents")
print("new index", built["index_id"], "format", built["format_version"], built["counts"]["documents"], "documents")
same_rows = {one["caselist"]: one["occurrences_sha256"] for one in current["stores"]} == {
    one["caselist"]: one["occurrences_sha256"] for one in built["stores"]
}
print("same stores and rows as the current index:", "yes" if same_rows else "no, the store changed since it was built")
before, after = current["counts"]["documents_by_store"], built["counts"]["documents_by_store"]
stop = built["format_version"] != 2
for store in sorted(set(before) | set(after)):
    was, now = before.get(store, 0), after.get(store, 0)
    print(f"{store}: {was:,} -> {now:,} documents")
    stop = stop or now == 0 or now < 0.9 * was or (same_rows and now != was)
print("STOP: not format 2, a store is empty or shrank, or the same rows gave other counts" if stop else "OK: format 2, every store kept")
print("INDEX_ID=" + built["index_id"])
EOF
fi
```
Success looks like `current index f29b81c276dd67c5 format 1` (or a later id), `new index <id>
format 2`, one line per store with the same number on both sides, and `OK: format 2, every store
kept`, then `INDEX_ID=<id>`. When the `same stores and rows` line says `yes`, the counts must be
equal: the format changes how words are matched and nothing else, and the block stops if they
differ. When it says `no`, a pull changed the store since the published index was built, and each
store may only have grown. **Stop, and take the output to the PM**, on a `STOP` line or a failed
build. Nothing has been published.

**3. Publish it, with no `--allow-shrink`.** Set `INDEX_ID` to the id the second block printed.

**Operator command** (expected runtime under a minute; changes dev's published index)
Where: `$WT`
```bash
cd "$WT"
INDEX_ID=put-the-id-from-the-block-above
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  DEBATE_ENV=dev uv run debate-research tub index publish --env dev --index "$HOME/.debate-research/dev/tub-index/${INDEX_ID}"
fi
```
Success looks like a table titled with `INDEX_ID`, whose last row is `reports/tub/search/current.json`,
and no `published past the shrink guard` line. **If it is refused** with `would shrink the published
search index`, stop and take the refusal to the PM: do not publish past the guard. Within five
minutes the function swaps to it: a search on dev no longer carries the *matched exactly as typed*
line, and *Search by passage* finds cards.

**4. Time three searches on dev**, from the function's `REPORT` lines. The function logs no query
text, so the lines are told apart by their order. Sign in on dev and search once for anything, so
the new index is fetched and the page's files are in the browser's cache. Then note the time:

**Operator command** (expected runtime seconds)
Where: the terminal you will read the lines from
```bash
START_MS=$(( $(date +%s) * 1000 ))
echo "$START_MS"
```
Then, about ten seconds apart, in this order: search `nuclear war`; tick *Search by passage* and
search `Nuclear war between great powers would cause human extinction`; untick it and search
`deter*`. Then read the lines:

**Operator command** (expected runtime seconds)
Where: the same terminal
```bash
aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-app \
  --start-time "$START_MS" --filter-pattern '"REPORT RequestId"' --query 'events[].message' --output text
```
Success looks like three `REPORT RequestId: ...` lines, each with a `Duration: <n> ms`: the plain
search, the passage and the prefix, in that order, each of whose pages showed a count above zero.
More than three lines means another request reached the function, such as a second tab: repeat from
the note of the time. Paste the three durations back to the PM; they go in the query-time table of
[the index's data model](../data/search-index.md#how-the-index-is-read).

**5. Reinstall the agent with this build before its next Wednesday run**, as
[Reinstalling the agent](caselist-scheduled-sync.md#reinstalling-the-agent) says. Until it is
reinstalled the agent runs a build that writes format 1: its weekly stage finds the format 2 index
is not one it would build, builds format 1 and publishes it, and dev's search is back to words
matched exactly as typed until format 2 is published again. Nothing breaks, because the function
reads both, but the move is undone.

**In prod** the order is the same, at the promotion: the prod function (step 11's deploy) before
prod's first format 2 index ([Promoting the pilot to prod](#promoting-the-pilot-to-prod), item 7).

## Download .docx and the cart

`v1-e39-t08`. A card page's **Download .docx** and the cart's **Download cart** build one Verbatim
file with the E33 writer, inside the function, and send it as an attachment. The cart is a list of
card references kept in the browser tab (`sessionStorage`), never in the session cookie; the
function checks every reference again (the PM's ruling of 2026-10-22).

- **What it reads.** Each card's source, by its sha256, from the current objects under
  `raw/caselist/<slug>/` or, for a camp card, `raw/openev/<year>/`: the role's `raw/*` read. It reads
  nothing else, writes nothing to the bucket, and writes nothing to `/tmp`: the sources and the file
  stay in memory. The file carries no provenance line (data-use policy 1.11); its sidecar is built
  and dropped, and the `cards-downloaded` audit record names the cards.
- **Download is off** on every card page, with *Download is off until the search's next weekly
  update*, when the function's parser version is not the one the loaded index's manifest names. A
  card's place in its source is the paragraphs that parser found it in, so another parser could copy
  the wrong paragraphs. It happens after a deploy that changes the parser and before the next index is
  published: rebuild and publish the index with the deployed build (`tub index build` and `publish`,
  [search index guide](../guides/search-index.md)), and download comes back within five minutes.
- **Failing closed.** A card the suppression list stops when the download is asked for is refused
  and named, whatever page it was added from. A download whose audit record cannot be written is not
  sent (`503`, and the `cards-downloaded` line in the table below).

### The download's limits, and timing a download on dev

The writer parses each source it copies from, whole, and holds every source until the file is read
back, so a download costs time and memory per distinct source, in proportion to its main document
part (`word/document.xml`). Measured on 2026-10-22 on the operator's Mac (Apple M3 Pro, under other
load), with synthetic sources the size of the mean disclosed file (236 KB, 3.6 MB of document XML):

| Cart | Build time | File |
|---|---|---|
| 1 card | 0.70 s | 7.2 KB |
| 10 cards from 10 sources | 10.0 s | 41.5 KB |
| 30 cards from 30 sources | 29.1 s | 117.9 KB |
| 30 cards from 1 source | 2.5 s | 118.1 KB |
| 1 card from a camp-sized source (1,004 KB) | 4.5 s | |
| 8 cards from 8 sources at both byte limits (20.6 MB of document XML, 51.2 MB of files) | 3.7 s | |

CloudFront and the function both stop a request at 30 s, and the function has 2,048 MB, so a
download has three limits (the PM's ruling of 2026-10-22):

| Limit | Value | What it bounds |
|---|---|---|
| `TUB_DOWNLOAD_CARD_CAP` (setting) | 8 (1 to 30) | Cards in one download, so sources in one build |
| `TUB_DOWNLOAD_SOURCE_XML_BYTES` (setting) | 20,000,000 | The cart's `document.xml` bytes, summed as each fetched file's zip directory declares them, read without a parse |
| The fetch ceiling (constant) | 52,000,000 | Bytes of files held before the build: a file is held whole, whatever its XML |

**Real source sizes** (2026-10-22, the operator's dev store, read-only, aggregates only; the sources
the occurrences of index `f29b81c276dd67c5` name; 3.1 s, and 5.1 s for the p99 and the zip
directories):

| Caselist | Sources | File p50 | File p95 | File p99 | Largest file | `document.xml` p99 | Largest `document.xml` |
|---|---|---|---|---|---|---|---|
| hsld26 | 5,965 | 69,708 | 353,223 | 1,323,225 | 7,133,832 | 965,762 | 6,412,100 |
| hspf26 | 3,524 | 72,419 | 1,431,736 | 6,404,597 | 7,823,779 | 1,573,448 | 3,754,072 |
| hspolicy26 | 3,799 | 157,358 | 884,755 | 1,803,342 | 7,679,194 | 2,016,564 | 6,583,540 |
| openev | 102 | 204,500 | 2,238,723 | 4,820,010 | 6,854,554 | 7,721,413 | 10,576,664 |

So no real source is refused on its own: its `document.xml` is at most 10,576,664 bytes, under the
20,000,000 budget, and its file at most 7,823,779 bytes, under the 52,000,000 ceiling, which also
holds eight files of the largest p99 (6,404,597). A file budget of 2,000,000 bytes, as first set, would
have refused 4.72% of hspf26's documents and 23.01% of openev's: big files are big for images and
other parts, and the ones over 2 MB have a median `document.xml` of 269 KB to 2.0 MB.

**Memory at both limits.** The 8-source cart above, built in a bare process: 52 MB with the modules
loaded, 101 MB holding the 51.2 MB of files, a 634 MB peak during the build. With 150 MB allowed for
the app and its index reader, that is about 732 MB at the measured rate and 1,314 MB at twice it.

**The declared size is a claim.** A file whose zip directory declares a smaller `document.xml` than
it holds passes the budget on the claim, and is then refused by the parser, never built: `zipfile`
never inflates a part past its declared size, so its CRC fails (*MALFORMED_PACKAGE*), or with a CRC
forged to match, its XML is cut short (*MALFORMED_XML*). Above that, the parser never reads more than
64 MiB of any part, or opens a package declaring more than 128 MiB in all.

A card whose own `document.xml` is over the budget is refused by name, *Its file is too large to
download. Copy card still works.*, and can be dropped from the cart like any refused card. A cart
whose parts only add up past the budget, or whose files pass the fetch ceiling, is refused with
*These cards come from files too large to read in one download*, as is a cart whose file would pass
3 MB with its own sentence: a function URL buffers at most 6 MB of response, and the Lambda Web Adapter
sends a binary body base64-encoded. Neither setting is set by Terraform; the defaults hold until
the dev timing below says otherwise, and changing one is a change to the module's environment block.

**Time a download on dev** after the deploy that ships it, with three carts and one refusal check
(the PM's rulings of 2026-10-22). Real carts cannot reach both byte limits at once: camp files are
heavy in XML, and the largest caselist files are heavy in images. So each cart tests one limit:

| Cart | What it tests | From the index `f29b81c276dd67c5` |
|---|---|---|
| First: eight mean-size cards | An ordinary cart: eight hspolicy26 files nearest 236 KB | 1,886,141 file bytes, 8,338,181 `document.xml` bytes |
| (a) The XML budget | Eight camp files, the two largest `document.xml` parts among them | 7,345,762 file bytes, 19,997,074 `document.xml` bytes |
| (b) The fetch ceiling | The eight largest hspolicy26 files | 44,855,560 file bytes, 2,491,293 `document.xml` bytes |
| (c) The refusal check | The eight largest camp files, over the budget | 26,309,272 file bytes, 44,031,336 `document.xml` bytes |

**List the carts' card pages.** A read-only block on the operator's store: it opens the index
read-only and reads only file sizes and zip directories. It prints, for each cart, its byte totals
and its eight card-page URLs, and nothing else: no file name, team code, school or card text. Set
`INDEX_ID` to the index dev serves (the id the latest `tub index publish` printed, or the app log's
`search index <id> loaded`). It stops if a `DEBATE_*` override is set or a `caselist pull` is running.

**Operator command** (expected runtime seconds)
Where: your Mac, anywhere
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  INDEX_ID=f29b81c276dd67c5
  python3 -I - "$INDEX_ID" <<'PY'
import sqlite3, sys, zipfile
from pathlib import Path
data = Path.home() / ".debate-research" / "dev"
index_id = sys.argv[1]
budget, ceiling = 20_000_000, 52_000_000
db = sqlite3.connect(f"{(data / 'tub-index' / index_id / 'search-index.sqlite').as_uri()}?mode=ro&immutable=1", uri=True)
blobs = data / "blobs" / "sha256"
def sources(caselist):
    found = {}
    rows = db.execute(
        "SELECT o.source_sha256, d.cluster_id FROM documents d JOIN occurrences o ON o.doc_id = d.doc_id "
        "AND o.ordinal = 0 WHERE d.caselist = ? AND d.completeness != 'CITE_ONLY' ORDER BY d.doc_id",
        (caselist,),
    )
    for sha, cluster in rows:
        if sha not in found:
            path = blobs / sha[0:2] / sha[2:4] / sha
            with zipfile.ZipFile(path) as archive:
                xml = archive.getinfo("word/document.xml").file_size
            found[sha] = (path.stat().st_size, xml, cluster)
    return [(size, xml, cluster) for size, xml, cluster in found.values()]
def show(name, caselist, cart):
    print(f"{name}: {len(cart)} cards, {sum(c[0] for c in cart):,} file bytes, {sum(c[1] for c in cart):,} document.xml bytes")
    for _, _, cluster in cart:
        print(f"  https://tub.dev.wfbdebate.com/cards/{caselist}/{cluster}")
policy, camp = sources("hspolicy26"), sources("openev")
show("first (mean-size)", "hspolicy26", sorted(policy, key=lambda c: (abs(c[0] - 236_000), c[2]))[:8])
by_xml = sorted(camp, key=lambda c: (-c[1], c[2]))
chosen, xml_total, file_total = [], 0, 0
for i, card in enumerate(by_xml):
    rest = sorted(c[1] for j, c in enumerate(by_xml) if j > i)[: 8 - len(chosen) - 1]
    if len(chosen) < 8 and xml_total + card[1] + sum(rest) <= budget and file_total + card[0] <= ceiling:
        chosen.append(card); xml_total += card[1]; file_total += card[0]
show("(a) XML budget", "openev", chosen)
show("(b) fetch ceiling", "hspolicy26", sorted(policy, key=lambda c: (-c[0], c[2]))[:8])
show("(c) refusal check", "openev", sorted(camp, key=lambda c: (-c[0], c[2]))[:8])
PY
fi
```
Success looks like two `none` lines and then, for index `f29b81c276dd67c5`, exactly these four
heading lines, each followed by eight `https://tub.dev.wfbdebate.com/cards/...` lines:

```text
first (mean-size): 8 cards, 1,886,141 file bytes, 8,338,181 document.xml bytes
(a) XML budget: 8 cards, 7,345,762 file bytes, 19,997,074 document.xml bytes
(b) fetch ceiling: 8 cards, 44,855,560 file bytes, 2,491,293 document.xml bytes
(c) refusal check: 8 cards, 26,309,272 file bytes, 44,031,336 document.xml bytes
```
Other totals mean the store or the index is not the one these were measured on. Stop and send the
four lines to the PM before timing anything.

**Time each cart.** Sign in on dev. For each cart in turn: choose **Empty the cart**, open its eight
URLs and choose **Add to cart** on each, then **Download cart**, then read the function's latest
`REPORT` line before the next cart:

**Operator command** (expected runtime seconds)
Where: your Mac, anywhere
```bash
aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-app \
  --filter-pattern '"REPORT RequestId"' --query 'events[-1:].message' --output text
```
Success looks like:

- **The first cart, (a) and (b):** the file downloads, and the `REPORT` line has `Duration` under
  20,000 ms and `Max Memory Used` under 1,400 MB. A card the download refuses by name (a picture
  inside it, say) has still had its file read and parsed. Record that line, choose *Remove these from
  the cart and download the rest*, and record the next line too.
- **(c):** the cart bar says *These cards come from files too large to read in one download*,
  within a few seconds, and no file downloads. Record its `Duration`.

Record every line in [What to record](#what-to-record). A line over 20,000 ms or 1,400 MB, or (c)
building a file or taking more than a few seconds: send all the lines to the PM before the pilot
opens. The fix would be lowering `TUB_DOWNLOAD_CARD_CAP` or `TUB_DOWNLOAD_SOURCE_XML_BYTES`, or the
fetch ceiling, in proportion.

## The landscape pages

`v1-e39-t17`, under data-use policy 1.16 and the E39 gate's item 11. A signed-in member, student or
coach, opens **Landscape** in the header and reads each caselist's newest landscape report and its
school view, rendered on the server from the bundle's own `report.md` and `schools.md`.

- **What it reads.** At most every five minutes, before answering, an environment lists
  `reports/landscape/` (the role's one listing, limited to that prefix by `s3:prefix`), takes each
  caselist's newest snapshot that holds `report.md` (which `landscape run` uploads last), and reads
  that snapshot's `report.md` and `schools.md` again only if their size or time changed. So a
  removal that deletes a school view (`v1-e32-t13`), a republished report or a newer snapshot shows
  within five minutes, and an older snapshot's view is never shown in place of a deleted one. If the
  bucket does not answer after five minutes, the pages answer `503` rather than an older copy.
- **The pages.** `/landscape`; `/landscape/<caselist>`, the report's header and its contents list;
  `/landscape/<caselist>/report/<part>`, one page per `#` part (Affirmative, Negative, Neither side),
  by its heading's anchor; `/landscape/<caselist>/schools`, the view's front page listing every
  school and position; one page per school (by its heading's anchor) and per position (by its id).
  The site's header, Search link and cart included, is the same as on every page; the reports
  themselves offer no search, download or share link. The only links out are the view's team pages
  on openCaselist, each checked at render.
- **The audit.** Every page view writes a `landscape-viewed` record to `debate-<env>-tub-audit`
  with the page's kind (`caselists`, `report`, `report-part`, `school-view`, `school` or
  `position`) and the bundle's caselist and snapshot, never which part, school or position. A view whose record is not
  written answers `503`.

### Granting the read, then deploying

The role's read of `reports/landscape/` is a Terraform change to one resource, then a deploy, in that
order: a function deployed before the apply answers `503` on every landscape page, since its role
may not list the bundles yet. Agreement 11 applies: the plan is one block and is read before the
apply, which is another. Run the plan and the apply from a checkout of `dev` that holds the merged
change. Each block stops on a leftover `DEBATE_*` override, and on an `owner.auto.tfvars` without the
pilot's two lines ([Before you start](#before-you-start)).

**Operator command, the plan** (expected runtime ~1 min)
Where: `$WT`, a checkout of `dev` with `v1-e39-t17` merged, its `infrastructure/envs/dev/owner.auto.tfvars` in place
```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: unset these first: $(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')"; elif [ "$(grep -c -E 'evidence_search_(deployer|accounts)_user_names' infrastructure/envs/dev/owner.auto.tfvars)" != 2 ]; then echo "STOP: owner.auto.tfvars lacks the pilot's two lines"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false > /dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -out=landscape-read.tfplan; fi
```
Read the plan. It should say `Plan: 0 to add, 1 to change, 0 to destroy.`, the one change
`module.evidence_search.aws_iam_role_policy.function` updated in place. Its policy diff adds
`reports/landscape/*` to the `s3:GetObject` statement's resources, renames that statement's `Sid` to
`ReadThePilotIndexLandscapeBundlesCurrentRawEvidenceAndTheSuppressionList`, and adds one statement,
`ListTheLandscapeBundlesOnly`: `s3:ListBucket` on the evidence bucket with the condition
`StringLike` `s3:prefix` `reports/landscape/*`. **Stop if anything else is in the plan**: another
resource, a destroy, an account assignment, or a listing without that condition. Something else
means `dev` holds another task's unapplied change or a stale `owner.auto.tfvars`; send the plan to
the PM before going on.

**Operator command, the apply** (expected runtime ~1 min)
Where: `$WT`, after the plan above was read
```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: unset the DEBATE_ overrides first"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false landscape-read.tfplan && rm landscape-read.tfplan; fi
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Then run
[step 9](#step-9--confirm-the-roles-are-least-privilege)'s first block, which now checks the
landscape read and listing too.

**Operator command, the deploy** (expected runtime ~4 min)
Where: `$WT`, the same checkout
```bash
cd "$WT"
uv sync --all-packages
scripts/tub_deploy.sh dev
```
The image installs what `uv.lock` records for `debate-api`, and since `v1-e39-t17` that includes
`markdown-it-py`, which renders the bundles; nothing else needs installing. Success looks like
step 8's: `{"status":"ok"}` from `/healthz` through CloudFront, and `Deployed <sha> to dev`.

**Check the pages.** First signed out, from your Mac: every landscape route needs a session.

**Operator command** (expected runtime seconds)
Where: your Mac, anywhere
```bash
for P in /landscape /landscape/hspolicy26 /landscape/hspolicy26/report/negative /landscape/hspolicy26/schools; do curl -sS -o /dev/null -w "$P %{http_code} %header{cache-control}\n" "https://tub.dev.wfbdebate.com$P"; done
```
Success looks like four lines ending `302 private, no-store`.

Then signed in as the coach, in a browser on `https://tub.dev.wfbdebate.com/`:

1. **Landscape** in the header lists `hspolicy26` with its newest snapshot's date, a link to
   the report and one to positions by school.
2. **The report** shows its title, its header and one contents list (`Affirmative`, `Negative`,
   `Neither side` with their sections, once the bundle is in `v1-e32-t20`'s shape). Each part's link
   opens that part's page, and each section's link opens its part at the section.
3. **Positions by school** lists the schools and the positions by kind. One school's page shows
   its table; one position's page shows its teams, and a team page opens openCaselist in a new tab.

Then the audit records those views wrote, which name no school, team code or position:

**Operator command** (expected runtime seconds)
Where: your Mac, anywhere
```bash
aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-audit \
  --filter-pattern '"landscape-viewed"' --query 'events[-5:].message' --output text
```
Success looks like up to five JSON lines, each with `"action":"landscape-viewed"`, a `page` of the
kind you opened, and `"caselist":"hspolicy26"` with the snapshot's date (none on the `caselists`
page). Record the deploy digest and these results in [What to record](#what-to-record). A `503` on
every landscape page after the deploy means the apply has not reached the role: check step 9.

## What a refusal looks like in the app log

The function logs to `debate-<env>-tub-app` (30 days), one line a record, `<LEVEL> <logger>: <message>`: every `WARNING`, and the index holder's `INFO` lines alone (`v1-e39-t10`). It never logs a query, a card id, a card's
text, a school, a team code, a username or an address (data-use policy, E39 gate item 4); what it
logs about the index is the index id and the kind of failure. A student sees one page for every
refusal below, **Search is not available right now** (`503`), or for Copy card the same sentence
beside the button.

| App log line (`WARNING` unless marked) | What happened | What to do |
|---|---|---|
| `search index <id> loaded in <s> s: <n> bytes from a <m>-byte object; <t> bytes in its directory` (`INFO`) | An environment fetched and checked an index, in that time, and has `<t>` bytes on `/tmp` (`v1-e39-t10`) | Nothing; [the app log's measurements](#measuring-the-pilot-from-the-app-log-v1-e39-t10) read it |
| `search answered in <n> ms` (`INFO`) | A search was answered in that time | Nothing; the query-time measurement reads it |
| `search index <id> closed and deleted` (`INFO`) | A newer index replaced it, or the environment closed it | Nothing |
| `the published search index was refused: the pointer is not a search index pointer this build reads` | `current.json` is not a pointer, or names keys outside its own index's directory | Publish again with `tub index publish`. If it says `current.json is not a pointer this build reads ... cannot be compared`, the shrink guard cannot read the current index either: compare the newest index's counts with the last run's `search_index` row, then publish with `--allow-shrink "<reason>"` ([the shrink guard](caselist-scheduled-sync.md#the-shrink-guard)) |
| `search index <id> was refused: its format version is not 1, the one this build reads` | The index was built by a build whose format this deploy does not read | Deploy the build that wrote it, or rebuild and publish with this one |
| `search index <id> was refused: its manifest is not a search index manifest` | The manifest is unreadable or too large | Publish again. The shrink guard reads that manifest first and refuses with `cannot be compared`; then publish with `--allow-shrink "<reason>"` ([the shrink guard](caselist-scheduled-sync.md#the-shrink-guard)) |
| `search index <id> was refused: its manifest is not the one the pointer names` | The manifest's sha256 is not the pointer's | Publish again, with `--allow-shrink "<reason>"` when the shrink guard says `cannot be compared`; if it repeats, compare the bucket's objects with the build directory |
| `search index <id> was refused: its manifest and the pointer name different files` | The manifest and the pointer disagree on the index or its digests | Publish again |
| `search index <id> was refused: its object is not one whole gzip stream` | The gzip object is cut short, damaged or followed by other bytes | Publish again |
| `search index <id> was refused: its object is not the one the pointer names` | The gzip object's bytes or size are not the pointer's | Publish again |
| `search index <id> was refused: its object does not inflate to the file the pointer names` | The SQLite file it inflates to is not the one the pointer names | Publish again |
| `search index <id> was refused: the reader refuses the file it inflates to` | The file checks out but is not a search index this build reads | Rebuild with this build, then publish |
| `the search index was not refreshed; index <id> still serves: <error type>` | A recheck of the pointer failed; the loaded index keeps serving and the next recheck is five minutes later | Nothing if it does not repeat; otherwise check the bucket and the role |
| `the suppression list was not read, so no search is answered until it is: <error type>` | The list could not be read (`StoreAccessDenied` when it does not exist, see above), or holds a line this build cannot read (`ValueError`). Every search and card page answers `503`, and every request tries again | Create the list if it is missing; otherwise read the list with the operator profile and find the line, as the removal runbook's residue section does |
| `tub audit: a card-viewed record was not written, so the card was not sent` (or `card-copied`, `cards-downloaded`) | The audit log refused a write; the card was not sent (gate item 4) | Check the audit group exists and the role may write to it (step 9) |
| `tub audit: a searched record was not written` | A search count was lost; the search was answered | Nothing if it does not repeat |
| `tub audit: a landscape-viewed record was not written, so the page was not sent` | The audit log refused a write; the landscape page was not sent (gate items 4 and 11) | As for a card view |

A refused index leaves the last loaded one serving in an environment that has one. An environment
with none, a new one, answers `503` to every search until an index loads, and tries again on every
request. Find the lines with:

**Operator command** (expected runtime seconds)
Where: your Mac, anywhere
```bash
aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-app \
  --filter-pattern '?refused ?"not read" ?"not refreshed" ?"not written"' \
  --query 'events[-20:].message' --output text
```
Success looks like nothing printed. Any line is one of the rows above. For prod, the same with
`debate-prod-tub-app`.

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
| Download: the four carts' totals from the listing block | | |
| Download: the first cart, eight mean-size cards (`Duration`, `Max Memory Used`) | | |
| Download: cart (a), the XML budget (`Duration`, `Max Memory Used`) | | |
| Download: cart (b), the fetch ceiling (`Duration`, `Max Memory Used`) | | |
| Download: cart (c), the refusal check (`Duration`; the message; no file) | | |
| 10: managed login rendered; asset hosts recorded | Rendered; both sign-ins reached the callback; hosts in the table above | n/a |
| 12: IT request sent; confirmed and date | n/a | |
| Landscape pages: the read grant's apply (`0 added, 1 changed`); deploy digest | | |
| Landscape pages: the coach saw the hspolicy26 report and its school view; the `landscape-viewed` lines | | |

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

**A format 2 index rolls back only to a function that reads format 2** (`v1-e39-t13`). An image
built before that task reads format 1 alone. Pointed at it while `current.json` names a format 2
index, a new environment refuses the index and answers every search with *Search is not available
right now* until a format 1 index is published, and only a build from before `v1-e39-t13` writes
one. So before you roll back, check that the digest's image reads format 2: its tag is the commit it
was built from, and that commit's `search_index.py` names the formats it reads.

```bash
cd "$WT"
git fetch origin
ROLLBACK_COMMIT='the-tag-from-the-list'
git show "${ROLLBACK_COMMIT%%-uncommitted-*}:packages/debate_core/src/debate_core/domain/search_index.py" \
  | grep -c 'READABLE_SEARCH_INDEX_FORMAT_VERSIONS: Final = frozenset({1, SEARCH_INDEX_FORMAT_VERSION})'
```
Success looks like `1`: that image reads formats 1 and 2, and the rollback is safe. `0`, or `fatal:`
for a commit git does not have, means it reads format 1 only: do not roll back to it while the
published index is format 2; take it to the PM.

## What this runbook deliberately does not do

- **Create a student's account.** That is the coach's `tub users add`, in prod
  ([the accounts guide](../guides/evidence-search-accounts.md)). The dev pool never holds a student, except the
  pilot validation students data-use policy 1.18 allows until the promotion.
- **Publish an index**, except the signed-in journey's two on dev ([J5 and J9](#the-signed-in-journey-on-dev)),
  which put the synthetic seed into dev's index and take it out again. `tub index publish` is
  `v1-e39-t02`'s, under the `EvidenceOperator` profile. The weekly agent run rebuilds the index when the parsed store changed and publishes it to
  dev (`v1-e39-t09`); publishing it to prod is the operator's, with `tub index publish --newest`, as
  [Publishing a pending index by hand](caselist-scheduled-sync.md#publishing-a-pending-index-by-hand)
  says. Both refuse an index that would drop a store's cards, and `--allow-shrink` is the
  operator's alone ([the shrink guard](caselist-scheduled-sync.md#the-shrink-guard), `v1-e39-t14`).
- **Delete superseded index versions.** That is `tub index prune` (`v1-e39-t15`), under the takedown
  profile, as the removal runbook's
  [P4](caselist-removal.md#p4--delete-the-superseded-index-versions-noncurrent-versions-included) runs
  it after a removal and the annual purge's step 5 each September.
- **Turn on access logging, a WAF or a second origin.** The pilot keeps no per-request record of a
  student's address, and CloudFront reaches nothing but the function (ADR-0019 (a) 4).
- **Change the evidence bucket.** Its Block Public Access settings and policy are untouched; the
  function reads through its role.

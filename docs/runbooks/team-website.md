# Runbook: team website hosting

How the public Whitefish Bay debate team website is stood up in AWS, and how the domains are
wired to it. Spec:
[`v1-e36-t02-site-hosting`](../../plan_specs/v1/e36-team-website/t02-site-hosting.yaml).
Decision: [ADR-0012](../adr/0012-web-hosting.md). One account and one region:
[ADR-0010](../adr/0010-primary-aws-region.md). Two environments and no third:
[ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md).

Runs after [terraform-bootstrap.md](terraform-bootstrap.md) and before
`v1-e36-t05-site-deploy`, which puts the built site into the buckets this creates.

Written for an adult engineer with administrator access to the account. **Every step here is run
by a human operator.** CI has no AWS credentials — the GitHub OIDC plan/apply roles arrive in
`v2-e10-t03` — and an agent session never runs `apply`, buys a domain or edits DNS.

Every permission question below is answered with `aws iam simulate-principal-policy`, which
evaluates the policies **without performing the action**. Never test a deny by attempting the
real call: if the deny has failed, the test itself is the damage.

## What this builds

| | dev | prod |
|---|---|---|
| Site | `https://dev.wfbdebate.org/` — the preview | `https://wfbdebate.org/` — what parents see |
| Also answers | — | `www.wfbdebate.org`, `wfbdebate.com`, `www.wfbdebate.com`, each a 301 to the apex |
| Bucket | `debate-dev-site-a7508de8` | `debate-prod-site-a7508de8` |
| Indexable | No — `X-Robots-Tag: noindex, nofollow` from the edge | Yes |
| Publisher permission set | `DebateDevSitePublisher` | `DebateProdSitePublisher` |
| Publisher SSO profile | `debate-dev-site` | `debate-prod-site` |
| Terraform root | `infrastructure/envs/dev` | `infrastructure/envs/prod` |

Both buckets are private: all four block-public-access flags, ACLs disabled, and a policy whose
only `Allow` is `s3:GetObject` for `cloudfront.amazonaws.com` conditioned on that environment's
distribution. There is **no CloudFront access logging** anywhere, so no per-request record of
visitor IP addresses exists (ADR-0012 decision 8).

## Why the applies run as `debate-admin`

Both roots now create an IAM Identity Center permission set, and `DebateMaintainer` is denied
`sso:Create*` by its own guardrail policy — the one that stops a maintainer removing the controls
that separate dev from prod. `DebateMaintainer` is also denied every `debate-prod-*` resource.
So the dev apply and the prod apply both run under `DebateBreakGlassAdmin` (`debate-admin`), and
step 1 confirms that rather than assuming it.

That is a real cost of putting the publisher permission set in the site module, and it is the
right trade: the alternative is publishing prod with break-glass admin every week instead of
once at setup.

## Before you start

**Shell variables**, used by every block below. Quote the email — an unquoted `<...>` placeholder
is a redirection to zsh.

```bash
WT=/path/to/your/checkout          # the task worktree during the task, the main clone afterwards
OWNER_EMAIL='you@example.com'
SSO_USER_NAME='your-identity-center-user-name'
```

**Sign in and confirm which identity you are about to apply as.**

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```
Success looks like: an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

**The operator-local tfvars**, which are gitignored. They carry the maintainer's email and
Identity Center user name; the second is what makes the publisher permission set usable.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
for env in dev prod; do
  cat > "infrastructure/envs/$env/owner.auto.tfvars" <<TFVARS
owner = "$OWNER_EMAIL"
site_publisher_user_names = ["$SSO_USER_NAME"]
TFVARS
done
cat infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like: two lines, the email and the user name. `git status` still reports a clean
tree — these files are gitignored.

## Step 1 — Confirm the two hosted zones exist and are delegated

`wfbdebate.org` and `wfbdebate.com` were registered on 2026-09-20. Terraform **reads** their
hosted zones and never creates or destroys one; a `destroy` that took a zone with it would strand
the domain. A zone whose name servers have not propagated will make the certificate step in step 3
sit for its full 30-minute timeout, so check first.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
for DOMAIN in wfbdebate.org wfbdebate.com; do
  echo "== $DOMAIN"
  aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN" \
    --query "HostedZones[?Name=='${DOMAIN}.'].{Id:Id,Records:ResourceRecordSetCount}" --output table
  echo "-- name servers the internet sees:"
  dig +short NS "$DOMAIN" @1.1.1.1
done
```
Success looks like: one hosted zone per domain, and four `awsdns` name servers returned by the
public resolver for each. If `dig` returns nothing, the delegation has not propagated yet —
registration the same day can take a few hours. Wait and re-run; do not go on to step 3's domain
apply until both answer.

If a domain's registrar is not Route 53, compare the registrar's name-server list with the zone's:

```bash
aws route53 get-hosted-zone --id <zone-id> --query 'DelegationSet.NameServers' --output text
```

Changing name servers at a registrar is a manual step in the registrar's console. It is not
Terraform's job and never an agent's.

## Step 2 — Confirm `debate-admin` can apply and `DebateMaintainer` cannot

The premise of the previous section, checked rather than assumed. `simulate-principal-policy`
evaluates the policies without performing anything.

**Operator command** (expected runtime ~2 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin

MAINTAINER=$(aws iam list-roles \
  --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateMaintainer`)].Arn' --output text)
echo "simulating: $MAINTAINER"

echo "== Identity Center writes (expect explicitDeny: this is why applies run as debate-admin)"
aws iam simulate-principal-policy --policy-source-arn "$MAINTAINER" \
  --action-names sso:CreatePermissionSet sso:PutInlinePolicyToPermissionSet \
                 sso:CreateAccountAssignment sso:ProvisionPermissionSet \
  --resource-arns '*' \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

echo "== the prod site bucket (expect explicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$MAINTAINER" \
  --action-names s3:PutObject s3:DeleteObject \
  --resource-arns "arn:aws:s3:::debate-prod-site-a7508de8/index.html" \
  --query 'EvaluationResults[].{Action:EvalActionName,Resource:EvalResourceName,Decision:EvalDecision}' \
  --output table

echo "== the dev site bucket (expect allowed)"
aws iam simulate-principal-policy --policy-source-arn "$MAINTAINER" \
  --action-names s3:PutObject s3:DeleteObject \
  --resource-arns "arn:aws:s3:::debate-dev-site-a7508de8/index.html" \
  --query 'EvaluationResults[].{Action:EvalActionName,Resource:EvalResourceName,Decision:EvalDecision}' \
  --output table
```
Success looks like: `explicitDeny` on every Identity Center action and on the prod bucket;
`allowed` on the dev bucket. An `allowed` against `debate-prod-*` means the environment boundary
ADR-0010 rests on is gone — stop and fix `infrastructure/bootstrap/organization/identity.tf`
before applying anything.

One resource ARN per call, as in [terraform-bootstrap.md](terraform-bootstrap.md) step 5: with
several at once the top-level decision is a roll-up and the resource name comes back as the
policy's own variable pattern.

## Step 3 — Apply dev

Two applies, deliberately. The first brings the site up on its CloudFront domain with no
certificate, which proves the bucket, the distribution, the function and the headers before DNS
is in the picture at all. The second adds the preview host.

If step 1 showed the delegation already settled, you can skip straight to 3b — but 3a costs five
minutes and makes a failure in 3b much easier to read.

### 3a — Without the domain

**Operator command** (expected runtime ~8 min; a CloudFront distribution takes several minutes to
create)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev init
terraform -chdir=infrastructure/envs/dev apply -var 'site_domain_names=[]'
```
Read the plan before approving. It should create the site bucket and its configuration resources,
one origin access control, one CloudFront Function, one response headers policy, one distribution,
and the `DebateDevSitePublisher` permission set with its inline policy and one assignment —
**no ACM certificate and no Route 53 records**. Success looks like `Apply complete!` and a
`site_url` output ending in `.cloudfront.net/`.

```bash
DEV_CF=$(terraform -chdir=infrastructure/envs/dev output -raw site_distribution_domain_name)
echo "$DEV_CF"
```

### 3b — With the preview host

**Operator command** (expected runtime ~10 min, most of it waiting for ACM and the distribution
update; the certificate wait times out at 30 min)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev apply
```
The plan adds an ACM certificate for `dev.wfbdebate.org`, its validation record, the validation
wait, two alias records (A and AAAA) and an update to the distribution's aliases and certificate.
Success looks like `Apply complete!` and `site_url = "https://dev.wfbdebate.org/"`.

If it fails with a certificate timeout, the zone's name servers have not propagated: go back to
step 1, wait, and re-run this same command. The apply is idempotent; nothing is lost.

## Step 4 — Confirm dev is private, encrypted in transit, and not indexable

Nothing is deployed into the bucket yet — `v1-e36-t05-site-deploy` does that — so a 404 from the
site's own error page is the expected answer for a page. What matters here is *how* it answers.

**Operator command** (expected runtime ~2 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin

echo "== public access block (expect four times True)"
aws s3api get-public-access-block --bucket debate-dev-site-a7508de8 \
  --query PublicAccessBlockConfiguration --output table

echo "== a direct S3 object URL (expect AccessDenied)"
curl -s "https://debate-dev-site-a7508de8.s3.us-east-1.amazonaws.com/index.html" | head -5

echo "== http:// must redirect to https:// (expect 301 and a https:// location)"
curl -sSI "http://dev.wfbdebate.org/" | sed -n '1p;/^[Ll]ocation:/p'

echo "== the preview must not be indexable (expect x-robots-tag: noindex, nofollow)"
curl -sSI "https://dev.wfbdebate.org/" | tr 'A-Z' 'a-z' \
  | grep -E 'strict-transport-security|content-security-policy|x-content-type-options|x-frame-options|referrer-policy|permissions-policy|x-robots-tag'
```
Success looks like: `True` four times; `<Error><Code>AccessDenied</Code>` from the S3 URL; a
`301` with an `https://` location; and all seven headers present, including
`x-robots-tag: noindex, nofollow`.

A `200` from the direct S3 URL means the bucket is public — stop and do not apply prod.

## Step 5 — Apply prod

Same shape, one root along. This one also creates the `.com` redirect distribution and its
certificate.

**Operator command** (expected runtime ~15 min; two CloudFront distributions and two certificates)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/prod init
terraform -chdir=infrastructure/envs/prod apply
```
Read the plan. It should create the prod site bucket and its configuration, the site distribution
with aliases `wfbdebate.org` and `www.wfbdebate.org`, a certificate covering both, four alias
records, the `DebateProdSitePublisher` permission set — and, from the `domain_redirect` module, a
second certificate for `wfbdebate.com` and `www.wfbdebate.com`, a second distribution, and four
more alias records in the `.com` zone. It must **not** create a hosted zone or an S3 bucket for
the redirect.

Success looks like `Apply complete!` and `site_url = "https://wfbdebate.org/"`.

To go out on the CloudFront domain first, as in 3a:

```bash
terraform -chdir=infrastructure/envs/prod apply -var 'site_domain_names=[]' -var 'redirect_domain_names=[]'
```

Both have to be emptied together: a redirect with no canonical host to point at is refused by a
`check` block in `site.tf`.

## Step 6 — Confirm prod, and that every other spelling lands on the apex

**Operator command** (expected runtime ~3 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin

echo "== public access block (expect four times True)"
aws s3api get-public-access-block --bucket debate-prod-site-a7508de8 \
  --query PublicAccessBlockConfiguration --output table

echo "== a direct S3 object URL (expect AccessDenied)"
curl -s "https://debate-prod-site-a7508de8.s3.us-east-1.amazonaws.com/index.html" | head -5

echo "== every other name must 301 to https://wfbdebate.org/"
for URL in http://wfbdebate.org/ https://www.wfbdebate.org/ https://wfbdebate.com/ https://www.wfbdebate.com/; do
  printf '%-32s ' "$URL"
  curl -sSI "$URL" | tr 'A-Z' 'a-z' | awk '/^http\//{code=$2} /^location:/{loc=$2} END{print code, loc}'
done

echo "== the canonical host answers, with the headers, and is indexable"
curl -sSI "https://wfbdebate.org/" | tr 'A-Z' 'a-z' \
  | grep -E 'strict-transport-security|content-security-policy|x-content-type-options|x-frame-options|referrer-policy|permissions-policy|x-robots-tag'

echo "== and that a deep link keeps its path through the .com redirect"
curl -sSI "https://wfbdebate.com/parents/faq/" | tr 'A-Z' 'a-z' | sed -n '1p;/^location:/p'
```
Success looks like: `True` four times; `AccessDenied` from the S3 URL; `301` with
`https://wfbdebate.org/` from all four spellings; six headers on the canonical host with **no**
`x-robots-tag`; and the deep link redirecting to `https://wfbdebate.org/parents/faq/`, path
intact.

`curl` may report a TLS error on a name for a minute or two after the apply, while CloudFront
finishes rolling the certificate out. Re-run before treating it as a failure.

## Step 7 — Add the two publisher SSO profiles

These are what `v1-e36-t05-site-deploy` deploys with. They assume a permission set that can do
five things: list, read, write and delete objects in its own site bucket, and create an
invalidation on its own distribution.

**Operator command** (expected runtime ~3 min)
Where: your Mac, in `~/.aws/config`
```ini
[profile debate-dev-site]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateDevSitePublisher
region = us-east-1
output = json

[profile debate-prod-site]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateProdSitePublisher
region = us-east-1
output = json
```
Then:
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-site  --query Arn --output text
aws sts get-caller-identity --profile debate-prod-site --query Arn --output text
```
Success looks like: two ARNs containing `AWSReservedSSO_DebateDevSitePublisher` and
`AWSReservedSSO_DebateProdSitePublisher`. A failure here usually means
`site_publisher_user_names` was empty when the root was applied — put your Identity Center user
name in `owner.auto.tfvars` and re-apply.

## Step 8 — Confirm the publishers are least-privilege

Again with `simulate-principal-policy`, never by attempting the action — one of these is a write
into the *other* environment's bucket.

**Operator command** (expected runtime ~3 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin

for ENV in dev prod; do
  case "$ENV" in
    dev)  PERMISSION_SET=DebateDevSitePublisher;  OTHER=prod ;;
    prod) PERMISSION_SET=DebateProdSitePublisher; OTHER=dev ;;
  esac
  ROLE=$(aws iam list-roles \
    --query "Roles[?starts_with(RoleName, \`AWSReservedSSO_${PERMISSION_SET}\`)].Arn" --output text)
  echo "===== $ENV publisher: $ROLE"

  echo "-- its own bucket (expect allowed)"
  aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
    --action-names s3:GetObject s3:PutObject s3:DeleteObject \
    --resource-arns "arn:aws:s3:::debate-${ENV}-site-a7508de8/index.html" \
    --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

  echo "-- the other environment's bucket (expect implicitDeny)"
  aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
    --action-names s3:GetObject s3:PutObject s3:DeleteObject \
    --resource-arns "arn:aws:s3:::debate-${OTHER}-site-a7508de8/index.html" \
    --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

  echo "-- the evidence and state buckets, and IAM (expect implicitDeny throughout)"
  aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
    --action-names s3:GetObject \
    --resource-arns "arn:aws:s3:::debate-${ENV}-tfstate-a7508de8/envs/${ENV}/terraform.tfstate" \
    --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
  aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
    --action-names iam:CreateAccessKey cloudfront:CreateDistribution sso:CreatePermissionSet \
    --resource-arns '*' \
    --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
done
```
Success looks like: `allowed` only against the publisher's own site bucket; `implicitDeny`
everywhere else, including the other environment's bucket, the Terraform state bucket, IAM and
CloudFront management.

`implicitDeny` rather than `explicitDeny` is correct here and is the stronger result to read:
the policy is a five-action allow-list, so anything not on the list is denied by having never
been granted.

One thing the publisher deliberately **cannot** do: `cloudfront:GetInvalidation`. The task's ac4
lists five actions and that is not one of them, so `aws cloudfront wait invalidation-completed`
will be denied. `v1-e36-t05-site-deploy` has to create the invalidation and move on, or ask for
the policy to be widened in a spec change.

The publisher also cannot read Terraform state, so a deploy script that runs `terraform output`
does that under `debate-admin` and the sync under the publisher profile.

## What to record

Fill this in as you go and commit it with the session report. Bucket names, distribution domains
and hosted zone names are fine here; **the account id is not**.

| | dev | prod |
|---|---|---|
| Site bucket | `debate-dev-site-a7508de8` | `debate-prod-site-a7508de8` |
| Applied on | _pending_ | _pending_ |
| Applied as | `debate-admin` (DebateBreakGlassAdmin) | `debate-admin` (DebateBreakGlassAdmin) |
| Distribution domain | _pending_ | _pending_ |
| Site URL | `https://dev.wfbdebate.org/` | `https://wfbdebate.org/` |
| Certificate issued on | _pending_ | _pending_ |
| Redirect distribution domain | — | _pending_ |
| Publisher profile confirmed | _pending_ | _pending_ |

| Check | Result | Date |
|---|---|---|
| Hosted zones delegated (`dig NS`) | _pending_ | |
| `DebateMaintainer` denied Identity Center writes and `debate-prod-*` | _pending_ | |
| Four block-public-access flags on both buckets | _pending_ | |
| Direct S3 object URL returns `AccessDenied` (both) | _pending_ | |
| `http://` redirects to `https://` (both) | _pending_ | |
| Security headers present (both) | _pending_ | |
| `dev.wfbdebate.org` sends `X-Robots-Tag: noindex, nofollow`; `wfbdebate.org` does not | _pending_ | |
| `www.wfbdebate.org`, `wfbdebate.com`, `www.wfbdebate.com` each 301 to `https://wfbdebate.org/` | _pending_ | |
| `.com` redirect preserves the path | _pending_ | |
| Publishers allowed only their own site bucket and distribution | _pending_ | |

## Recurring checks

| When | What |
|---|---|
| After any apply | `terraform plan` reports no changes in the root you applied |
| After any deploy | `scripts/site_smoke.py` against the environment you deployed (`v1-e36-t05-site-deploy`) |
| Monthly | The four spellings still 301 to `https://wfbdebate.org/` |
| Monthly | `dev.wfbdebate.org` still sends `X-Robots-Tag: noindex`, and a `site:dev.wfbdebate.org` search returns nothing |
| Yearly, before the registration renews | Both domains are set to auto-renew, and the zones' name servers still match the registrar's |
| When the certificate approaches expiry | ACM renews DNS-validated certificates automatically **as long as the validation CNAMEs stay in the zone**. Do not delete them |

## What this runbook deliberately does not do

Owned by later tasks, not here:

- Building and uploading the site, cache headers, invalidation and smoke checks —
  `v1-e36-t05-site-deploy`.
- Page content and copy — `v1-e36-t03-site-scaffold` and `v1-e36-t04-core-pages`, under the
  publishing policy of `v1-e36-t01-publishing-policy`.
- Keyless deploys from CI — `v2-e10-t03`. Until they exist, publishing is an operator running
  the deploy script, which is the property that keeps an unreviewed page about a student from
  reaching the public by a merge.
- Hosting the authenticated V2 app under the same domain — `v2-e14-t03-app-hosting`, which amends
  [ADR-0012](../adr/0012-web-hosting.md).

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
| Site | `https://dev.wfbdebate.com/` — the preview | `https://wfbdebate.com/` — what parents see |
| Also answers | — | `www.wfbdebate.com`, a 301 to the apex |
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

`WT` is the checkout that holds **this task's** Terraform: the task worktree while the task is in
flight, the main clone once it has merged. It is not the same path as the last task's `WT`, and a
stale one is the failure this block exists to catch — `cd` to a directory that no longer exists
leaves you wherever you were, and the next `terraform` command runs against a checkout where
`site.tf` does not exist yet. That looks like `Error: Value for undeclared variable`, and it
happens after `init` has already run somewhere it should not have.

```bash
WT=/path/to/your/checkout          # e.g. .../debate-intelligence-worktrees/v1-e36-t02-site-hosting
OWNER_EMAIL='you@example.com'
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || { echo "WT does not exist: $WT"; }
test -f infrastructure/envs/dev/site.tf \
  && echo "ok: $(pwd) on branch $(git branch --show-current)" \
  || echo "WRONG CHECKOUT: $(pwd) has no infrastructure/envs/dev/site.tf — fix WT before going on"
```
Success looks like: `ok: <the worktree path> on branch task/v1-e36-t02-site-hosting`. Anything
else, fix `WT` and re-run; do not carry on to the applies.

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

Skipping this is why an apply stops to ask `Enter a value:` for `var.owner`. Answering the prompt
works for one run, but the value is not recorded anywhere, so the next plan asks again and
`site_publisher_user_names` stays empty — which leaves the publisher permission set with nobody
assigned to it (step 7 then fails). Write the files instead of answering the prompt.

## Step 1 — Confirm the hosted zone exists and is delegated

`wfbdebate.com` is the canonical team domain, registered 2026-09-20. `wfbdebate.org` was the first
choice and could not be registered — three attempts failed, an AWS Support case is open, and the
*If a registration failed* section below has the detail. The environments are wired to the domain
that exists; if `.org` is ever issued it becomes a redirect to `.com`, which is a tfvars change and
an apply, not new code.

Terraform **reads** the hosted zone and never creates or destroys one; a `destroy` that took a zone
with it would strand the domain. A zone whose name servers have not propagated will make the
certificate step in step 3 sit for its full 30-minute timeout, so check first. The loop covers
`.org` as well, so that the day it resolves is visible here.

The `aws sso login` is part of this block on purpose: an expired token fails the two `aws` calls
while `dig` still answers, which reads like a DNS result and is not one.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
aws sso login --sso-session debate

for DOMAIN in wfbdebate.org wfbdebate.com; do
  echo "===== $DOMAIN"

  echo "-- the hosted zone, and the name servers it expects to be delegated to:"
  ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN" \
    --query "HostedZones[?Name=='${DOMAIN}.'].Id | [0]" --output text)
  if [ "$ZONE_ID" = "None" ] || [ -z "$ZONE_ID" ]; then
    echo "   no hosted zone (expected while a domain is unregistered)"
  else
    echo "   zone: $ZONE_ID"
    aws route53 get-hosted-zone --id "$ZONE_ID" \
      --query 'DelegationSet.NameServers' --output text | tr '\t' '\n' | sed 's/^/   /'
  fi

  echo "-- is it registered at all, and with which name servers?"
  whois "$DOMAIN" 2>/dev/null \
    | grep -iE '^[[:space:]]*(Domain Name|Registrar|Creation Date|Name Server|Domain Status):' \
    | sed 's/^[[:space:]]*/   /' | head -12

  echo "-- what the registry itself publishes (authoritative; no resolver cache in the way):"
  # NS rows only. An answer that holds nothing but the TLD's own SOA means the registry has no
  # delegation for this name, and reading its TTL as a name server is an easy mistake to make.
  dig +noall +authority +answer NS "$DOMAIN" @$(dig +short NS "${DOMAIN##*.}." | head -1) \
    | awk '$4 == "NS" { print "   " $5 }'

  echo "-- what a public resolver sees:"
  dig +short NS "$DOMAIN" @1.1.1.1 | sed 's/^/   /'
done
```
Success looks like, **for `wfbdebate.com`**: a `whois` block naming a registrar and a creation
date, a zone id, and the **same four `awsdns` name servers** in the zone, the registry and the
public resolver. The registry line is the one that matters — a public resolver can lag it by
minutes, but it cannot be ahead of it.

`wfbdebate.org` is expected to show no hosted zone, no registrar and no delegation, for as long as
its registration keeps failing. That row is here so the day it changes is visible.

Three ways this comes back wrong, and what each means:

| What you see | What it means | What to do |
|---|---|---|
| `whois` says `Domain not found` / `No match` | **The domain is not registered.** It is not a propagation delay; there is nothing to propagate | Register it, or check whether the purchase completed — see the block below. Nothing in step 3b or step 5 can work for that name |
| `whois` names a registrar, but the registry line is empty | Registered; the delegation has not been published yet. Same-day registration can take a few hours | Wait and re-run |
| The registry's name servers differ from the zone's | The registrar points somewhere else | Fix the name-server list in the registrar's console — an operator step, never Terraform — then re-run |

**Do not run step 3b or step 5 for a domain whose registry line is still empty**: the certificate
wait will sit for its full 30 minutes and then fail the apply. Step 3a needs no DNS at all and can
be run meanwhile, which is the point of it being a separate step.

If a domain was bought through Route 53 and has not appeared, the registration may still be
running or may have failed. The Route 53 Domains API lives only in `us-east-1`.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin

echo "== domains this account holds"
aws route53domains list-domains --region us-east-1 \
  --query 'Domains[].{Name:DomainName,Expiry:Expiry,AutoRenew:AutoRenew}' --output table

echo "== recent registration operations and how they ended"
aws route53domains list-operations --region us-east-1 \
  --query 'Operations[?Type==`REGISTER_DOMAIN`].{Domain:DomainName,Status:Status,Submitted:SubmittedDate,Message:Message}' \
  --output table
```
Success looks like: both domains listed, and every `REGISTER_DOMAIN` operation `SUCCESSFUL`. A
`FAILED` operation carries the reason in `Message`; an `IN_PROGRESS` one just needs time. A domain
that appears in neither list was never bought from this account.

### If a registration failed

`wfbdebate.org` failed this way three times on 2026-09-20, the first of them 0.9 seconds after it
was submitted and two seconds after `wfbdebate.com` succeeded with the same contacts, with only the
generic "Contact AWS Support" message. A failure that fast, on an account and contacts that had
just worked, is not the contact data — check the name is still free and try once more before
opening a case, which is what happened here.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin
aws route53domains check-domain-availability --region us-east-1 \
  --domain-name wfbdebate.org --query Availability --output text
```
Success looks like: `AVAILABLE`. `UNAVAILABLE` means someone else has taken it since — stop and
re-decide the canonical name; do not keep retrying.

The retry itself is easiest in the **Route 53 console** (*Registered domains → Register domains*),
which fills the contact panel from your account and keeps the details off your disk entirely.

The CLI version reuses the contacts from the domain that *did* register, without printing them.
They are a person's name, address, phone and email, so the temp file is mode 600 and is removed
on the way out.

**Operator command** (expected runtime ~2 min to submit, up to ~15 min to complete)
Where: your Mac, anywhere
```bash
export AWS_PROFILE=debate-admin

CONTACTS=$(mktemp -t wfbdebate-register) && chmod 600 "$CONTACTS"
trap 'rm -f "$CONTACTS"' EXIT

aws route53domains get-domain-detail --region us-east-1 --domain-name wfbdebate.com \
  --query '{AdminContact:AdminContact,RegistrantContact:RegistrantContact,TechContact:TechContact}' \
  --output json > "$CONTACTS"

aws route53domains register-domain --region us-east-1 \
  --cli-input-json "file://$CONTACTS" \
  --domain-name wfbdebate.org \
  --duration-in-years 1 \
  --auto-renew \
  --privacy-protect-admin-contact \
  --privacy-protect-registrant-contact \
  --privacy-protect-tech-contact \
  --query OperationId --output text
```
This **spends money** (about $12 for a year of `.org`) and is a mutating call: run it yourself, not
from an agent session. Explicit flags win over the values in `--cli-input-json`, which is what lets
the file carry only the three contacts.

Then watch the operation it printed:

```bash
export AWS_PROFILE=debate-admin
aws route53domains get-operation-detail --region us-east-1 \
  --operation-id <the-operation-id> \
  --query '{Status:Status,Message:Message}' --output json
```
Success looks like `"Status": "SUCCESSFUL"`, usually within a few minutes. Route 53 creates the
hosted zone for you; re-run step 1 and the registry line should fill in shortly afterwards.

If it reports `FAILED` a second time, stop retrying: open the AWS Support case the message points
at, and decide whether to wait for it or to make the domain you already have the canonical name.

That is what happened here: `wfbdebate.org` failed three times on 2026-09-20 (`4cb18c5e…` at
12:11:28, `f79d71d2…` at 13:03:20, `cc87fa96…` at 13:04:26, all CDT, each in under a second). The
successful `wfbdebate.com` registration took **10 minutes 12 seconds**, and `credencesports.com`
before it took 11 minutes — a registration that reaches the registry takes minutes, so a
sub-second failure never left Amazon Registrar. A Support case is open. The canonical name moved
to `wfbdebate.com`, which cost only two `terraform.tfvars` files and some prose, because nothing in
the modules or their 16 tests depends on which name is canonical.

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
The plan adds an ACM certificate for `dev.wfbdebate.com`, its validation record, the validation
wait, two alias records (A and AAAA) and an update to the distribution's aliases and certificate.
Success looks like `Apply complete!` and `site_url = "https://dev.wfbdebate.com/"`.

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
curl -sSI "http://dev.wfbdebate.com/" | sed -n '1p;/^[Ll]ocation:/p'

echo "== the preview must not be indexable (expect x-robots-tag: noindex, nofollow)"
curl -sSI "https://dev.wfbdebate.com/" | tr 'A-Z' 'a-z' \
  | grep -E 'strict-transport-security|content-security-policy|x-content-type-options|x-frame-options|referrer-policy|permissions-policy|x-robots-tag'
```
Success looks like: `True` four times; `<Error><Code>AccessDenied</Code>` from the S3 URL; a
`301` with an `https://` location; and all seven headers present, including
`x-robots-tag: noindex, nofollow`.

A `200` from the direct S3 URL means the bucket is public — stop and do not apply prod.

**Before the first deploy, expect `403` where this says `404`.** The distribution maps both 403 and
404 to `/404.html`, but until `v1-e36-t05-site-deploy` has put the site in the bucket that page
does not exist either, so CloudFront cannot serve the custom error page and returns the original
status. Confirm the mapping is configured rather than inferring it from a response:

```bash
export AWS_PROFILE=debate-admin
aws cloudfront get-distribution-config --id <the distribution id> \
  --query 'DistributionConfig.{Logging:Logging.Enabled,CustomErrors:CustomErrorResponses.Items[].{Code:ErrorCode,Response:ResponseCode,Page:ResponsePagePath},MinTLS:ViewerCertificate.MinimumProtocolVersion,DefaultCert:ViewerCertificate.CloudFrontDefaultCertificate}' \
  --output json
```
Success looks like `"Logging": false`, both error codes mapped to `/404.html`, and — while the
distribution is still on the CloudFront domain — `"MinTLS": "TLSv1"` with
`"DefaultCert": true`. That `TLSv1` is AWS's, not ours: it is forced on any distribution using the
CloudFront default certificate, and it becomes `TLSv1.2_2021` in step 3b when the ACM certificate
is attached (ADR-0012 consequences).

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
with aliases `wfbdebate.com` and `www.wfbdebate.com`, a certificate covering both, four alias
records, and the `DebateProdSitePublisher` permission set. It must **not** create a hosted zone.

It also must **not** create anything from the `domain_redirect` module: `redirect_domain_names` is
empty while there is only one registrable domain. That module is built and tested and waiting —
if `wfbdebate.org` is ever issued, uncomment the two lines at the bottom of
`envs/prod/terraform.tfvars` and re-apply, and the `.org` names will 301 to their `.com`
equivalents.

Success looks like `Apply complete!` and `site_url = "https://wfbdebate.com/"`.

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

echo "== every other name must 301 to https://wfbdebate.com/"
for URL in http://wfbdebate.com/ https://www.wfbdebate.com/; do
  printf '%-32s ' "$URL"
  curl -sSI "$URL" | tr 'A-Z' 'a-z' | awk '/^http\//{code=$2} /^location:/{loc=$2} END{print code, loc}'
done

echo "== the canonical host answers, with the headers, and is indexable"
curl -sSI "https://wfbdebate.com/" | tr 'A-Z' 'a-z' \
  | grep -E 'strict-transport-security|content-security-policy|x-content-type-options|x-frame-options|referrer-policy|permissions-policy|x-robots-tag'

echo "== and that a deep link keeps its path through the www redirect"
curl -sSI "https://www.wfbdebate.com/parents/faq/" | tr 'A-Z' 'a-z' | sed -n '1p;/^location:/p'
```
Success looks like: `True` four times; `AccessDenied` from the S3 URL; `301` with
`https://wfbdebate.com/` from both other spellings; six headers on the canonical host with **no**
`x-robots-tag`; and the deep link redirecting to `https://wfbdebate.com/parents/faq/`, path
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
| Applied on | 2026-09-20 — step 3a (no domain) 14 added; step 3b (preview host) 5 added, 2 changed | _pending_ |
| Applied as | `debate-admin` (DebateBreakGlassAdmin) | `debate-admin` (DebateBreakGlassAdmin) |
| Distribution | `doq8i8utzst6e.cloudfront.net` (`E2OSZZB3X6M1T0`) | _pending_ |
| Site URL | `https://dev.wfbdebate.com/` | `https://wfbdebate.com/` — _pending_ |
| Certificate | 2026-09-20, `ISSUED` and in use, `CN=dev.wfbdebate.com`, DNS validated in the `.com` zone | _pending_ |
| TLS floor | `TLSv1.2_2021`, `sni-only` (was AWS's forced `TLSv1` on the default certificate before 3b); negotiates TLS 1.3 | _pending_ |
| Redirect distribution | — | — (no second registrable domain; see `wfbdebate.org` below) |
| Publisher permission set provisioned | 2026-09-20, `DebateDevSitePublisher`, assigned to `ccl1196` | _pending_ |
| Publisher profile confirmed | _pending_ (step 7) | _pending_ |

| Check | Result | Date |
|---|---|---|
| Canonical domain registered (`whois`) | `wfbdebate.com` registered 2026-09-20T17:11:33Z (Amazon Registrar), `SUCCESSFUL` after 10m 12s | 2026-09-20 |
| `wfbdebate.org` | **Registration FAILED three times**, each in under a second, with only the generic "Contact AWS Support" message: `4cb18c5e-dc01-4b99-8cff-b782eecf8cd5` (12:11:28), `f79d71d2-7ce8-47b4-825b-644a83fdc3bc` (13:03:20), `cc87fa96-df2f-4004-8637-67211510a714` (13:04:26), all CDT. `check-domain-availability` → `AVAILABLE`; `Domain not found` at the `.org` registry. AWS Support case filed 2026-09-20; canonical name moved to `.com` rather than waiting on it | 2026-09-20 |
| Hosted zone delegated (registry `NS`) | `wfbdebate.com` delegated to four `awsdns` servers, visible at the registry and at 1.1.1.1 and 8.8.8.8 | 2026-09-20 |
| `DebateMaintainer` denied Identity Center writes and `debate-prod-*` | _pending_ | |
| Four block-public-access flags | dev: all four `true`, `BucketOwnerEnforced`. prod: _pending_ | 2026-09-20 |
| Direct S3 object URL returns `AccessDenied` | dev: `<Error><Code>AccessDenied</Code>`. prod: _pending_ | 2026-09-20 |
| `http://` redirects to `https://` | dev: `301` to `https://dev.wfbdebate.com/`. prod: _pending_ | 2026-09-20 |
| Alias records resolve | dev: `dev.wfbdebate.com` returns four CloudFront A records at 1.1.1.1. prod: _pending_ | 2026-09-20 |
| TLS 1.2 floor once the certificate is attached | dev: `MinimumProtocolVersion = TLSv1.2_2021`, `CloudFrontDefaultCertificate = false`, certificate `ISSUED`/`InUse`, `Verify return code: 0 (ok)`. prod: _pending_ | 2026-09-20 |
| Security headers present | dev: all seven — HSTS `max-age=31536000; includesubdomains`, CSP with `frame-ancestors 'none'`, `nosniff`, `x-frame-options: deny`, `referrer-policy`, `permissions-policy`, `x-robots-tag`. prod: _pending_ | 2026-09-20 |
| CloudFront access logging off | dev: `Logging.Enabled = false`. prod: _pending_ | 2026-09-20 |
| 403 and 404 both map to `/404.html` | dev: both present in the distribution config | 2026-09-20 |
| `dev.wfbdebate.com` sends `X-Robots-Tag: noindex, nofollow`; `wfbdebate.com` does not | dev: `x-robots-tag: noindex, nofollow` confirmed on both the CloudFront domain and `https://dev.wfbdebate.com/`. prod: _pending_ | 2026-09-20 |
| `www.wfbdebate.com` 301s to `https://wfbdebate.com/`, path preserved | _pending_ (step 6) | |
| Publishers allowed only their own site bucket and distribution | dev: `allowed` on `debate-dev-site-a7508de8/*`; `implicitDeny` on the prod site bucket, the dev state bucket, `iam:CreateAccessKey`, `cloudfront:CreateDistribution`, `sso:CreatePermissionSet`. prod: _pending_ | 2026-09-20 |

## Recurring checks

| When | What |
|---|---|
| After any apply | `terraform plan` reports no changes in the root you applied |
| After any deploy | `scripts/site_smoke.py` against the environment you deployed (`v1-e36-t05-site-deploy`) |
| Monthly | `www.wfbdebate.com` still 301s to `https://wfbdebate.com/` |
| Monthly | `dev.wfbdebate.com` still sends `X-Robots-Tag: noindex`, and a `site:dev.wfbdebate.com` search returns nothing |
| While the AWS Support case is open | `aws route53domains check-domain-availability --domain-name wfbdebate.org`. If it is ever registered, add the two `redirect_*` lines to `envs/prod/terraform.tfvars` and re-apply |
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

# Runbook: the evidence store

| | |
|---|---|
| Purpose | Create the dev and prod evidence buckets and the credentials that reach them |
| Who runs it | The operator (Charlie). Not an agent session, not CI |
| How long | About 45 minutes, dev and prod together |
| Destructive? | No. It creates resources; nothing here deletes evidence |
| Spec | [`v1-e29-t03-evidence-buckets`](../../plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml) |

The bucket this creates is the system of record
([ADR-0003](../adr/0003-s3-source-of-truth-for-raw-artifacts.md)). The key layout inside it is
[docs/architecture/evidence-store-layout.md](../architecture/evidence-store-layout.md); the
Terraform is [`infrastructure/modules/evidence_bucket`](../../infrastructure/modules/evidence_bucket/).

Runs after [terraform-bootstrap.md](terraform-bootstrap.md) and before `v1-e29-t04-s3-blob-store`
and `v1-e29-t05-evidence-sync-cli`, which are what actually put evidence in it.

Written for an adult engineer with administrator access to the account. **Every step here is run
by a human operator.** CI has no AWS credentials — the GitHub OIDC plan/apply roles arrive in
`v2-e10-t03` — and an agent session never runs `plan` or `apply`.

Every permission question below is answered with `aws iam simulate-principal-policy`, which
evaluates the policies **without performing the action**. Never test a deny by attempting the real
call: if the deny has failed, the test itself is the damage. The one real delete in this runbook
is of a synthetic test object the operator has just created, under `quarantine/`, and it is there
to prove that a takedown will work when one is needed.

## What this builds

| | dev | prod |
|---|---|---|
| Bucket | `debate-dev-evidence-a7508de8` | `debate-prod-evidence-a7508de8` |
| KMS key alias | `alias/debate-dev-evidence` | `alias/debate-prod-evidence` |
| Superseded versions | expire after 30 days | Standard-IA at 30 days, expire at 365 |
| Everyday permission set | `DebateDevEvidenceOperator` | `DebateProdEvidenceOperator` |
| Everyday SSO profile | `debate-dev-evidence` | `debate-prod-evidence` |
| Takedown permission set | `DebateDevEvidenceRemoval` | `DebateProdEvidenceRemoval` |
| Takedown SSO profile | `debate-dev-evidence-removal` | `debate-prod-evidence-removal` |
| Terraform root | `infrastructure/envs/dev` | `infrastructure/envs/prod` |
| Holds | Synthetic and sample data | The real corpus |

Both buckets are private (all four block-public-access flags, ACLs disabled, no website hosting),
versioned, encrypted with their own customer-managed KMS key with rotation on, and refuse any
request that is not over TLS. **No lifecycle rule expires a current object version** except under
`exports/`, which holds regenerable zip downloads and expires after a day.

## The two credentials, and why

`DebateEvidenceOperator` is everyday work: list the documented prefixes, read, publish, use the
key. It has **no `s3:DeleteObject` at all**. `DebateEvidenceRemoval` is the only credential in the
account that can delete evidence; it is scoped to `raw/`, `parsed/`, `files/`, `manifests/` and
`quarantine/`, may write only the suppression list under `manifests/_suppression/`, and is
assigned to one person. A removal purges noncurrent versions too, so there is nothing to restore
from afterwards ([caselist-removal.md](caselist-removal.md)) — which is why the credential that
can do it is not the one left signed in all week.

Note what `debate-dev` is **not**. That profile is `DebateMaintainer`, which holds
`PowerUserAccess` minus the prod denies, so in dev it can delete an object. The least-privilege
claim in the task spec belongs to the `debate-<env>-evidence` profiles, and those are what the
checks below simulate.

## Why the applies run as `debate-admin`

Both roots create Identity Center permission sets, and `DebateMaintainer` is denied `sso:Create*`
by its own guardrail policy — the one that stops a maintainer removing the controls that separate
dev from prod. `DebateMaintainer` is also denied every `debate-prod-*` resource and every
`alias/debate-prod-*` key. So the dev apply and the prod apply both run under
`DebateBreakGlassAdmin` (`debate-admin`), and step 2 confirms that rather than assuming it.

## Before you start

**Shell variables**, used by every block below. `WT` is the checkout that holds this task's
Terraform: the task worktree while the task is in flight, the main clone once it has merged. A
stale `WT` is the failure this block exists to catch.

```bash
WT=/path/to/your/checkout          # e.g. .../debate-intelligence-worktrees/v1-e29-t03-evidence-buckets
OWNER_EMAIL='you@example.com'
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || { echo "WT does not exist: $WT"; }
test -f infrastructure/envs/dev/evidence_store.tf \
  && echo "ok: $(pwd) on branch $(git branch --show-current)" \
  || echo "WRONG CHECKOUT: $(pwd) has no infrastructure/envs/dev/evidence_store.tf — fix WT before going on"
```
Success looks like: `ok: <the worktree path> on branch task/v1-e29-t03-evidence-buckets`.

**The operator-local tfvars**, which are gitignored. They carry the maintainer's email and the
Identity Center user names the permission sets are assigned to. If you have already run
[team-website.md](team-website.md), these files exist and you are appending to them.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
for env in dev prod; do
  f="infrastructure/envs/$env/owner.auto.tfvars"
  touch "$f"
  grep -q '^owner ' "$f" || echo "owner = \"$OWNER_EMAIL\"" >> "$f"
  grep -q '^site_publisher_user_names' "$f" || echo "site_publisher_user_names = [\"$SSO_USER_NAME\"]" >> "$f"
  cat >> "$f" <<TFVARS
evidence_operator_user_names = ["$SSO_USER_NAME"]
evidence_removal_user_names  = ["$SSO_USER_NAME"]
TFVARS
done

# scripts/terraform_checks.sh runs `terraform fmt -check -recursive` over the working tree, which
# includes gitignored .tfvars. Unaligned `=` here fails pre-commit on every later commit from this
# checkout, which is a confusing thing to debug later.
terraform fmt infrastructure/envs/dev infrastructure/envs/prod
cat infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like: four assignments with their `=` aligned, and `git status` still clean — these
files are gitignored. `evidence_removal_user_names` takes **one** name; the module refuses a
second.

## Step 1 — Sign in

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```
Success looks like: an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

## Step 2 — Confirm the boundary before you widen it

The premise of the section above, checked rather than assumed: `DebateMaintainer` cannot create
these permission sets and cannot reach prod evidence.

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

echo "== the prod evidence bucket (expect explicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$MAINTAINER" \
  --action-names s3:GetObject s3:PutObject \
  --resource-arns "arn:aws:s3:::debate-prod-evidence-a7508de8/raw/caselist/probe" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
```
Success looks like: `explicitDeny` on every row. An `allowed` against `debate-prod-*` means the
boundary ADR-0010 rests on is gone — stop and fix
`infrastructure/bootstrap/organization/identity.tf` before applying anything.

The prod bucket does not exist yet, and that does not matter: `simulate-principal-policy`
evaluates policies against an ARN, not against a resource that has to be there.

## Step 3 — Apply dev

**Operator command** (expected runtime ~5 min)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin

terraform -chdir=infrastructure/envs/dev init
terraform -chdir=infrastructure/envs/dev plan -out=/tmp/evidence-dev.tfplan
```
Read the plan before applying it. Success looks like: a KMS key, a KMS alias, an S3 bucket and its
five configuration resources, two permission sets with inline policies, and two account
assignments — and **no changes to the site resources**. If the plan wants to replace or destroy
anything that already exists, stop.

```bash
terraform -chdir=infrastructure/envs/dev apply /tmp/evidence-dev.tfplan
terraform -chdir=infrastructure/envs/dev output evidence_bucket_name
terraform -chdir=infrastructure/envs/dev output evidence_kms_alias_name
```
Success looks like: `debate-dev-evidence-a7508de8` and `alias/debate-dev-evidence`.

## Step 4 — Add the dev SSO profiles

Two more profiles against the same account id, differing by permission set. Append to
`~/.aws/config`, using the same `[sso-session debate]` block the existing profiles use.

```ini
[profile debate-dev-evidence]
sso_session = debate
sso_account_id = <your account id>
sso_role_name = DebateDevEvidenceOperator
region = us-east-1
output = json

[profile debate-dev-evidence-removal]
sso_session = debate
sso_account_id = <your account id>
sso_role_name = DebateDevEvidenceRemoval
region = us-east-1
output = json
```

**Operator command** (expected runtime ~2 min)
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-evidence --query Arn --output text
aws sts get-caller-identity --profile debate-dev-evidence-removal --query Arn --output text
```
Success looks like: two ARNs naming `AWSReservedSSO_DebateDevEvidenceOperator` and
`AWSReservedSSO_DebateDevEvidenceRemoval`.

## Step 5 — Check dev: put, get, and the denies

Real puts and gets (they prove the key and the encryption work end to end), simulated denies.

**Operator command** (expected runtime ~5 min)
Where: your Mac, anywhere
```bash
BUCKET=debate-dev-evidence-a7508de8
export AWS_PROFILE=debate-dev-evidence

echo "== put and get (expect both to succeed)"
echo "synthetic probe $(date -u +%FT%TZ)" > /tmp/evidence-probe.txt
aws s3api put-object --bucket "$BUCKET" --key quarantine/_probe/probe.txt \
  --body /tmp/evidence-probe.txt --query 'VersionId' --output text
aws s3api get-object --bucket "$BUCKET" --key quarantine/_probe/probe.txt /tmp/evidence-probe-back.txt >/dev/null
diff /tmp/evidence-probe.txt /tmp/evidence-probe-back.txt && echo "round trip ok"

echo "== the object is encrypted with this environment's own key (expect aws:kms and debate-dev-evidence)"
aws s3api head-object --bucket "$BUCKET" --key quarantine/_probe/probe.txt \
  --query '{Encryption:ServerSideEncryption,Key:SSEKMSKeyId}' --output table

echo "== listing is scoped to a prefix: this works"
aws s3 ls "s3://$BUCKET/quarantine/"
echo "== and listing the bucket root does not (expect AccessDenied; that is the scoping, not a fault)"
aws s3 ls "s3://$BUCKET" || true
```
Success looks like: a version id, `round trip ok`, `ServerSideEncryption: aws:kms` with an
`SSEKMSKeyId` ending in the key behind `alias/debate-dev-evidence`, a listing of
`quarantine/_probe/`, and an `AccessDenied` on the bare bucket listing.

**Operator command** (expected runtime ~3 min)
```bash
export AWS_PROFILE=debate-admin
BUCKET=debate-dev-evidence-a7508de8

OPERATOR=$(aws iam list-roles \
  --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateDevEvidenceOperator`)].Arn' --output text)
REMOVER=$(aws iam list-roles \
  --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateDevEvidenceRemoval`)].Arn' --output text)

echo "== the everyday credential must not be able to delete (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$OPERATOR" \
  --action-names s3:DeleteObject s3:DeleteObjectVersion \
  --resource-arns "arn:aws:s3:::$BUCKET/raw/caselist/hsld26/probe" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

echo "== nor to change the controls (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$OPERATOR" \
  --action-names s3:PutBucketPolicy s3:PutLifecycleConfiguration s3:PutBucketPublicAccessBlock \
  --resource-arns "arn:aws:s3:::$BUCKET" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

echo "== the takedown credential may delete disclosed material (expect allowed)"
aws iam simulate-principal-policy --policy-source-arn "$REMOVER" \
  --action-names s3:DeleteObject s3:DeleteObjectVersion \
  --resource-arns "arn:aws:s3:::$BUCKET/raw/caselist/hsld26/probe" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

echo "== but not under reports/ (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$REMOVER" \
  --action-names s3:DeleteObject s3:DeleteObjectVersion \
  --resource-arns "arn:aws:s3:::$BUCKET/reports/hsld26/probe" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

echo "== and may not publish outside the suppression list (expect implicitDeny)"
aws iam simulate-principal-policy --policy-source-arn "$REMOVER" \
  --action-names s3:PutObject \
  --resource-arns "arn:aws:s3:::$BUCKET/raw/caselist/hsld26/probe" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
```
Success looks like: `implicitDeny` everywhere except the `raw/` delete under the takedown
credential, which is `allowed`. `implicitDeny` is the right answer here rather than
`explicitDeny`: these policies are allow-lists, so an action that is not granted is simply not
allowed. Any `allowed` in a block labelled `expect implicitDeny` is a defect in
`infrastructure/modules/evidence_bucket/operator_access.tf` — stop and fix it before prod.

**The real takedown check**, on the synthetic probe object from the block above and nothing else.

**Operator command** (expected runtime ~3 min)
```bash
export AWS_PROFILE=debate-dev-evidence-removal
BUCKET=debate-dev-evidence-a7508de8

aws s3api list-object-versions --bucket "$BUCKET" --prefix quarantine/_probe/ \
  --query '{Versions:Versions[].VersionId,Markers:DeleteMarkers[].VersionId}' --output json

for v in $(aws s3api list-object-versions --bucket "$BUCKET" --prefix quarantine/_probe/ \
             --query 'Versions[].VersionId' --output text); do
  aws s3api delete-object --bucket "$BUCKET" --key quarantine/_probe/probe.txt --version-id "$v"
done

aws s3api list-object-versions --bucket "$BUCKET" --prefix quarantine/_probe/ --output json
```
Success looks like: the version list is non-empty to begin with, and empty (`{}`) at the end — the
takedown credential can remove an object *and its versions*, which is what a removal request
requires. Delete the probe from any local copy too.

**The bucket's own configuration**, read back from the account rather than from the plan. This is
the live half of what `tests/evidence_bucket.tftest.hcl` asserts offline, and it is cheaper to
catch a wrong lifecycle rule in dev than to create it in prod first.

**Operator command** (expected runtime ~2 min)
```bash
export AWS_PROFILE=debate-admin
export AWS_PAGER=""          # the lifecycle output is long enough to trigger the pager otherwise
BUCKET=debate-dev-evidence-a7508de8
ALIAS=alias/debate-dev-evidence

echo "== public access block (expect all four true)"
aws s3api get-public-access-block --bucket "$BUCKET" --query 'PublicAccessBlockConfiguration' --output json

echo "== versioning (expect Enabled)"
aws s3api get-bucket-versioning --bucket "$BUCKET" --output json

echo "== encryption (expect aws:kms with this environment's key, BucketKeyEnabled true)"
aws s3api get-bucket-encryption --bucket "$BUCKET" \
  --query 'ServerSideEncryptionConfiguration.Rules' --output json

echo "== lifecycle (expect 3 rules, and exactly one Expiration block, under exports/)"
aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET" --output json

echo "== the key is customer-managed and rotating"
# get-key-rotation-status does not accept an alias, unlike most KMS calls, so resolve it first.
KEY_ID=$(aws kms describe-key --key-id "$ALIAS" --query 'KeyMetadata.KeyId' --output text)
aws kms describe-key --key-id "$ALIAS" \
  --query 'KeyMetadata.{KeyId:KeyId,Manager:KeyManager,State:KeyState}' --output table
aws kms get-key-rotation-status --key-id "$KEY_ID" --output json
```
Success looks like: all four public-access flags `true`; versioning `Enabled`; `aws:kms` with the
`KMSMasterKeyID` this environment's own key and `BucketKeyEnabled: true`; `KeyManager: CUSTOMER`,
`KeyState: Enabled` and `"KeyRotationEnabled": true`; and three lifecycle rules —

* `age-out-superseded-evidence-versions`: `NoncurrentVersionExpiration.NoncurrentDays` 30 in dev
  and 365 in prod, **no `Expiration` block**, and a `NoncurrentVersionTransitions` entry to
  `STANDARD_IA` at 30 days in prod only (dev omits it on purpose — see the module README).
* `expire-bulk-export-archives`: `Filter.Prefix: "exports/"`, `Expiration.Days: 1`.
* `abort-incomplete-multipart-uploads`: `DaysAfterInitiation: 7`.

**The thing to look hardest at is that no rule except the `exports/` one has an `Expiration`
block.** That is the guarantee that evidence is never deleted by a timer.

`TransitionDefaultMinimumObjectSize: all_storage_classes_128K` also appears, and is the provider
and S3 default: objects under 128 KB are not transitioned to Standard-IA. That is the behaviour to
want, because Standard-IA bills a 128 KB minimum per object, so moving a smaller object there
costs more than leaving it in Standard.

## Step 6 — Apply prod, then repeat the checks

Only after dev is applied and every check above has passed.

**Operator command** (expected runtime ~5 min)
Where: `$WT`
```bash
cd "$WT"
export AWS_PROFILE=debate-admin

terraform -chdir=infrastructure/envs/prod init
terraform -chdir=infrastructure/envs/prod plan -out=/tmp/evidence-prod.tfplan
```
Read the plan. Success looks like the same resource list as dev, named `debate-prod-*`, with the
lifecycle rule carrying `noncurrent_days = 365` and a Standard-IA transition at 30.

```bash
terraform -chdir=infrastructure/envs/prod apply /tmp/evidence-prod.tfplan
terraform -chdir=infrastructure/envs/prod output evidence_bucket_name
```

Then add `[profile debate-prod-evidence]` and `[profile debate-prod-evidence-removal]` to
`~/.aws/config` exactly as in step 4 but with `DebateProdEvidenceOperator` and
`DebateProdEvidenceRemoval`, and run the whole of step 5 again with
`BUCKET=debate-prod-evidence-a7508de8` and the prod profiles. The probe object is synthetic and
under `quarantine/_probe/`; remove it at the end, as step 5 does.

## Step 7 — Confirm the assignments

The configuration read-back in step 5 covers the bucket and the key. The one thing left is who
holds each permission set — and `DebateProdEvidenceRemoval` having exactly one assignee is the
task's own acceptance criterion.

**Operator command** (expected runtime ~2 min)
```bash
export AWS_PROFILE=debate-admin
export AWS_PAGER=""
INSTANCE_ARN=$(aws sso-admin list-instances --query 'Instances[0].InstanceArn' --output text)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

for ARN in $(aws sso-admin list-permission-sets --instance-arn "$INSTANCE_ARN" \
               --query 'PermissionSets[]' --output text); do
  NAME=$(aws sso-admin describe-permission-set --instance-arn "$INSTANCE_ARN" \
           --permission-set-arn "$ARN" --query 'PermissionSet.Name' --output text)
  case "$NAME" in
    DebateDevEvidence*|DebateProdEvidence*)
      COUNT=$(aws sso-admin list-account-assignments --instance-arn "$INSTANCE_ARN" \
                --account-id "$ACCOUNT_ID" --permission-set-arn "$ARN" \
                --query 'length(AccountAssignments)' --output text)
      echo "$NAME: $COUNT assignment(s)" ;;
  esac
done
```
Success looks like: all four sets reporting `1 assignment(s)`. More than one on either
`*EvidenceRemoval` set means someone was added outside Terraform — the module's own variable
validation allows only one name.

The same facts are visible in the console (Identity Center → Permission sets → the set → AWS
accounts), and S3 → the bucket → Properties and Permissions shows the block-public-access,
versioning, encryption and lifecycle state that step 5 read back.

## The record

Both environments applied on **2026-09-20**. Bucket names, aliases and dates only — **no account
ids** (this repository is public).

| | dev | prod |
|---|---|---|
| Applied on | 2026-09-20 | 2026-09-20 |
| Apply result | `15 added, 0 changed, 0 destroyed` | `15 added, 0 changed, 0 destroyed` |
| Bucket | `debate-dev-evidence-a7508de8` | `debate-prod-evidence-a7508de8` |
| Key alias | `alias/debate-dev-evidence` | `alias/debate-prod-evidence` |
| Key is customer-managed, enabled, rotating | PASS — `CUSTOMER`, `Enabled`, `KeyRotationEnabled: true`, 365-day period | PASS — same |
| Put/get round trip, everyday profile | PASS — version id returned, `round trip ok` | PASS |
| Object encrypted with this environment's own key | PASS — `aws:kms` with this environment's CMK, and **not** the other environment's | PASS |
| Block all public access (four flags) | PASS — all four `true` | PASS |
| Versioning | PASS — `Enabled` | PASS |
| Default encryption, bucket key | PASS — `aws:kms` + `BucketKeyEnabled: true` | PASS |
| Lifecycle: superseded versions | PASS — expire at 30 days, no Standard-IA transition | PASS — Standard-IA at 30, expire at 365 |
| Lifecycle: only `exports/` expires current versions | PASS — one `Expiration` block in the whole configuration, scoped to `exports/`, `Days: 1` | PASS |
| Lifecycle: abort incomplete multipart | PASS — 7 days | PASS |
| `s3:ListBucket` scoped to prefixes | PASS — prefix listing works, bare bucket listing `AccessDenied` | PASS |
| `s3:DeleteObject` denied to the everyday profile | PASS — `implicitDeny` | PASS |
| Bucket policy / lifecycle / public-access changes denied to the everyday profile | PASS — `implicitDeny` on all three | PASS |
| Takedown profile deletes an object **and its versions** under `quarantine/` | PASS — one version before, none after, and no delete marker left behind | PASS |
| Takedown profile denied a delete under `reports/` | PASS — `implicitDeny` | PASS |
| Takedown profile denied `PutObject` outside `manifests/_suppression/` | PASS — `implicitDeny` | PASS |
| Permission set assignments | PASS — `DebateDevEvidenceOperator` 1, `DebateDevEvidenceRemoval` 1 | PASS — `DebateProdEvidenceOperator` 1, `DebateProdEvidenceRemoval` 1 |

The two environments hold **different** customer-managed keys, which is what ADR-0010 rule 4 rests
on: a dev-scoped credential cannot decrypt prod evidence even if it somehow reached the object.

## If something is wrong

* **The plan wants to replace the bucket or the key.** Stop. Both carry `prevent_destroy`, so the
  apply will refuse anyway. A replacement means a rename, and renaming the system of record is a
  spec change, not an apply.
* **`AccessDenied` listing the bucket root.** Expected. `ListBucket` is scoped to the documented
  prefixes; list a prefix (`aws s3 ls s3://$BUCKET/raw/`).
* **`AccessDenied` on a put with the everyday profile.** Check the object is not being uploaded
  with `--sse` naming another algorithm or another key: the bucket policy denies an upload that
  asks for encryption other than this key, and nothing else in it denies a put.
* **An `allowed` where a deny was expected.** Do not carry on to prod. The inline policies are in
  `infrastructure/modules/evidence_bucket/operator_access.tf` and their assertions are in
  `tests/evidence_bucket.tftest.hcl`; add the case that was missed to the tests first, then fix
  the policy.

## References

- [docs/architecture/evidence-store-layout.md](../architecture/evidence-store-layout.md) — what
  goes in which prefix, and the key form.
- [docs/runbooks/caselist-removal.md](caselist-removal.md) — the takedown procedure this
  credential exists for.
- [docs/runbooks/terraform-bootstrap.md](terraform-bootstrap.md) — the state buckets and the
  environment roots this runs after.
- [ADR-0003](../adr/0003-s3-source-of-truth-for-raw-artifacts.md),
  [ADR-0010](../adr/0010-primary-aws-region.md),
  [ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md).

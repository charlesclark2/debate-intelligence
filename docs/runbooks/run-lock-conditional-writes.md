<!-- docs-index: Applying the evidence bucket's deny of an unconditional write of the run lock, and proving it without disturbing the lock -->
# The run lock refuses an unconditional write

The weekly run's lock, `reports/sync/run-lock.json` in the home environment's evidence bucket
(`v1-e40-t04`, ADR-0020 (4)), changes only by compare-and-swap. Every write the code makes is a
`PutObject` with `If-None-Match: *` (the seed creating it) or `If-Match: <entity tag>` (taking,
renewing and releasing it). Until `v1-e40-t07` the bucket did not insist on it. So a tool or a hand
command that wrote the key blind, `aws s3 cp` say, could overwrite a live holder's lease. The
holder's next renewal would then fail with `412`, and the run would end `RUN_LOCK_LOST`.

`v1-e40-t07` adds one statement to the evidence bucket's policy, in both environments
(`infrastructure/modules/evidence_bucket/main.tf`):

| | |
|---|---|
| Sid | `DenyUnconditionalWritesOfTheRunLock` |
| Effect, principal | Deny, every principal (`{"AWS": "*"}`) |
| Action | `s3:PutObject`, and nothing else |
| Resource | `arn:aws:s3:::<bucket>/reports/sync/run-lock.json`, and no other key |
| Condition | `Null`: `s3:if-match` is `true` **and** `s3:if-none-match` is `true`, that is both headers absent |

**What AWS says the condition keys cover**
([Enforce conditional writes on Amazon S3 buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html),
read 2026-10-31):

* The keys are `s3:if-match` and `s3:if-none-match`. They apply to `PutObject` and to
  `CompleteMultipartUpload`, both authorised as `s3:PutObject`.
* `CreateMultipartUpload`, `UploadPart` and `UploadPartCopy` are also authorised as `s3:PutObject`
  but cannot carry the headers. AWS's examples exempt them with `s3:ObjectCreationOperation`. This
  statement leaves that key out on purpose, so a multipart upload onto the lock is refused at its
  first step. The lock is one small `PutObject`, and nothing writes it in parts.
* `CopyObject` onto a key under such a policy fails: `403 Access Denied` without the headers, and
  `501 Not Implemented` with them. So a copy, an S3 Batch Operations copy or a "restore by copying an
  old version back" can never write the lock around the deny.

**What it does not cover.** A delete. The lock is released by a conditional `PutObject` of
`state: free`, never deleted (`run_lock.py`, rule 5), and no everyday or takedown grant holds
`s3:DeleteObject` on `reports/sync/` (`operator_access.tf`). Only the break-glass admin could delete
it. A deleted lock fails closed: the next run refuses with `RUN_STATE_NOT_SEEDED` and nothing is
written. Whether that deserves a statement of its own is a question for the PM
(`docs/session-reports/v1-e40-t07-lock-writes-conditional-at-the-bucket.md`). Nor does the deny stop
a writer that reads the current entity tag and writes over it with `If-Match`: that is a
compare-and-swap, and the policy cannot tell a holder from a tool that read first.

## When

* **After `v1-e40-t07` has merged into `dev`.** Plan and apply from a checkout on `origin/dev`, never
  from the task branch.
* **Never on a Wednesday**, the cloud run's day. Every block that applies or writes checks the day.
* **Dev first.** Prod follows with the pilot's next promotion, with the same blocks and
  `ENVIRONMENT=prod`, after the PM's word on dev ([Prod](#prod)).
* **The PM reads the plan before the apply.** The plan must show one change, the bucket policy, and no
  change to any account assignment or permission set.

## Before you start

`WT` is a checkout of `origin/dev` that has `v1-e40-t07`, holding the gitignored
`infrastructure/envs/<env>/owner.auto.tfvars` of the checkout that last applied that environment.
Without that file every user-name variable is empty, and the plan proposes destroying every account
assignment in the root. Replace `/path/to/your/apply/checkout` with that checkout's absolute path. Set
`ENVIRONMENT` and `BUCKET` in the same terminal window, which every block below reads.

**Operator command** (expected runtime a few seconds)
Where: your Mac, in a new terminal window
```bash
WT=/path/to/your/apply/checkout
ENVIRONMENT=dev
BUCKET="debate-${ENVIRONMENT}-evidence-a7508de8"
cd "$WT" || echo "WT does not exist: $WT"
git fetch origin
git switch --detach origin/dev
grep -c 'DenyUnconditionalWritesOfTheRunLock' infrastructure/modules/evidence_bucket/main.tf
grep -c -E '^(evidence_operator_user_names|evidence_removal_user_names) ' "infrastructure/envs/${ENVIRONMENT}/owner.auto.tfvars"
aws --version
aws s3api put-object --generate-cli-skeleton input | grep -c -E '"If(None)?Match"'
date +%A
```
Success looks like `1` (the statement is in this checkout), `2` (the file names the evidence
operator and the removal user), an `aws-cli/2.` version, `2` (this CLI can send `If-Match` and
`If-None-Match`), and a day that is not Wednesday. A `0` on the first line means `v1-e40-t07` is not
merged yet. A `0` or `1` on the second means the tfvars are not the ones that last applied this
environment: copy them from that checkout, and do not plan. A `0` on the fourth means the CLI predates
conditional writes: update it (`brew upgrade awscli`) before step 1.

**Sign in.** The plan and the apply run as `debate-admin`, and the proof as the everyday profile.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the same window
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
aws sts get-caller-identity --profile "debate-${ENVIRONMENT}-evidence" --query Arn --output text
```
Success looks like one ARN containing `AWSReservedSSO_DebateBreakGlassAdmin` and one containing
`AWSReservedSSO_Debate<Env>EvidenceOperator`.

## 1. The probe, before the apply: it must find no deny yet

Three `PutObject` requests, as the everyday profile. **None of them can store anything, whatever the
bucket policy says**, so the live lock is never written:

1. **A scratch key beside the lock**, `reports/sync/run-lock-probe.json`, written blind with a
   `Content-MD5` that does not match its body. The deny does not name this key, so S3 lets the request
   through and refuses the body: `BadDigest`. This is the control. It shows how S3 answers a blind
   write it does not refuse, and that the deny does not reach a key beside the lock.
2. **The lock's key, the same blind request.** Before the apply S3 lets it through to the same
   digest check: `BadDigest`. After the apply the bucket refuses it before the body is read:
   `AccessDenied ... with an explicit deny in a resource-based policy`.
3. **The lock's key, conditional**: `If-Match` naming an entity tag no object has. It is a
   conditional write, so the bucket lets it through, and S3 then refuses it because the tag does not
   match: `PreconditionFailed`. Before and after the apply alike. A `NoSuchKey` here means the bucket
   holds no lock, which prod's may not.

S3 authorises a request before it reads the body. If it ever checked the digest first, request 2
would answer `BadDigest` after the apply too, and this probe would say the deny is missing. It can be
wrong only in that direction, never by writing.

The block refuses a Wednesday, a shell with a `DEBATE_` override, a `caselist pull` running on this
Mac, and a lock that is held: it never sends a request at a key a holder is renewing. In dev it also
refuses a lock it could not read, which since the cutover means an expired sign-in, never a bucket
without a lock. It reads the
lock's entity tag before and after, and they must be the same.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the same window
```bash
PROBE_DIR=$(mktemp -d /tmp/run-lock-probe.XXXXXX)
printf 'run lock probe, never stored\n' > "$PROBE_DIR/body"
WRONG_MD5=$(printf 'not the body' | openssl dgst -md5 -binary | base64)
LOCK_STATE=$(aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile "debate-${ENVIRONMENT}-evidence" 2>/dev/null | python3 -I -c 'import json, sys; print(json.load(sys.stdin).get("state", "unreadable"))' 2>/dev/null || echo absent)
echo "lock: ${LOCK_STATE}"
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ "$LOCK_STATE" = absent ] && [ "$ENVIRONMENT" = dev ]; then echo "STOP: the dev lock could not be read; sign in again with aws sso login --sso-session debate"; elif [ "$LOCK_STATE" != free ] && [ "$LOCK_STATE" != absent ]; then echo "STOP: the lock is ${LOCK_STATE}; run this when it is free"; else
  BEFORE=$(aws s3api head-object --profile "debate-${ENVIRONMENT}-evidence" --bucket "$BUCKET" --key reports/sync/run-lock.json --query ETag --output text 2>/dev/null || echo absent)
  echo "== 1. scratch key, blind:"
  aws s3api put-object --profile "debate-${ENVIRONMENT}-evidence" --bucket "$BUCKET" --key reports/sync/run-lock-probe.json --body "$PROBE_DIR/body" --content-md5 "$WRONG_MD5" > "$PROBE_DIR/1.out" 2>&1 && echo "WROTE reports/sync/run-lock-probe.json: tell the PM" || grep -oE '\([A-Za-z]+\)|explicit deny in a resource-based policy' "$PROBE_DIR/1.out" | tr '\n' ' '; echo
  echo "== 2. the lock, blind:"
  aws s3api put-object --profile "debate-${ENVIRONMENT}-evidence" --bucket "$BUCKET" --key reports/sync/run-lock.json --body "$PROBE_DIR/body" --content-md5 "$WRONG_MD5" > "$PROBE_DIR/2.out" 2>&1 && echo "WROTE THE LOCK: tell the PM now" || grep -oE '\([A-Za-z]+\)|explicit deny in a resource-based policy' "$PROBE_DIR/2.out" | tr '\n' ' '; echo
  echo "== 3. the lock, conditional on a tag nothing has:"
  aws s3api put-object --profile "debate-${ENVIRONMENT}-evidence" --bucket "$BUCKET" --key reports/sync/run-lock.json --body "$PROBE_DIR/body" --if-match '"00000000000000000000000000000000"' > "$PROBE_DIR/3.out" 2>&1 && echo "WROTE THE LOCK: tell the PM now" || grep -oE '\([A-Za-z]+\)|explicit deny in a resource-based policy' "$PROBE_DIR/3.out" | tr '\n' ' '; echo
  AFTER=$(aws s3api head-object --profile "debate-${ENVIRONMENT}-evidence" --bucket "$BUCKET" --key reports/sync/run-lock.json --query ETag --output text 2>/dev/null || echo absent)
  [ "$BEFORE" = "$AFTER" ] && echo "lock unchanged: ${AFTER}" || echo "LOCK CHANGED: ${BEFORE} then ${AFTER}: tell the PM now"
fi
rm -rf "$PROBE_DIR"
```
Success looks like, **before the apply**:

```text
lock: free
== 1. scratch key, blind:
(BadDigest)
== 2. the lock, blind:
(BadDigest)
== 3. the lock, conditional on a tag nothing has:
(PreconditionFailed)
lock unchanged: "<the lock's entity tag>"
```

In prod with no lock object, `lock: absent`, `(NoSuchKey)` on request 3 and `lock unchanged: absent`.

* `(AccessDenied)` on request 2 **before** the apply: the deny is already there, so someone applied
  it already. Tell the PM before planning.
* `(AccessDenied)` on request 1 or 3: something other than this statement refuses the everyday
  profile, so this probe cannot tell you anything. Stop and send the output to the PM.
* `WROTE`, or `LOCK CHANGED`, has no way to happen. If one is printed, stop everything and tell the
  PM with the output. The next run takes over the lock from whatever is there, and says so.

## 2. The plan

Saved to a file, so that what step 3 applies is what the PM read.

**Operator command** (expected runtime ~2 min)
Where: `$WT`, the same window
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" plan -input=false -no-color -out=run-lock-conditional-writes.tfplan | tee "/tmp/run-lock-conditional-writes-${ENVIRONMENT}-plan.txt" | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed|will be created' "/tmp/run-lock-conditional-writes-${ENVIRONMENT}-plan.txt"
grep -v -E 'Refreshing state|: Read(ing\.\.\.| complete)' "/tmp/run-lock-conditional-writes-${ENVIRONMENT}-plan.txt" | grep -c 'aws_ssoadmin'
grep -E '^  # ' "/tmp/run-lock-conditional-writes-${ENVIRONMENT}-plan.txt"
```
Expect `Plan: 0 to add, 1 to change, 0 to destroy.`, no line saying a resource is replaced, destroyed
or created, then `0` (the count leaves out the lines where Terraform only refreshes or reads an
account assignment, a permission set or the `aws_ssoadmin_instances` data source; the 2026-11-01 dev
plan's raw count was 26 refresh lines and 2 read lines, and no change), then exactly one line:
`module.evidence_store.aws_s3_bucket_policy.evidence will be updated in-place`. No `Plan:` line at
all means the plan failed: read the end of the file. **An account assignment, a permission set, or
anything but the bucket policy in the plan stops everything**: never apply it, and send the plan to the
PM. The usual cause is an `owner.auto.tfvars` that is not the last applier's, or another task's change
waiting for its own apply.

**The plan checked against exactly that shape.** It prints `PLAN OK` only for one in-place update of
the evidence bucket's policy whose statements gain exactly `DenyUnconditionalWritesOfTheRunLock`, as the
table at the top gives it, and lose and change nothing. Then it prints the statement added, for the
PM to read. Anything else prints `PLAN STOP` with the reason.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, the same window
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" show -json run-lock-conditional-writes.tfplan > "/tmp/run-lock-conditional-writes-${ENVIRONMENT}-plan.json"
python3 -I - "/tmp/run-lock-conditional-writes-${ENVIRONMENT}-plan.json" "$BUCKET" <<'RUNLOCKPLAN'
import json, sys
plan = json.load(open(sys.argv[1]))
bucket = sys.argv[2]
target = "module.evidence_store.aws_s3_bucket_policy.evidence"
expected = {
    "Sid": "DenyUnconditionalWritesOfTheRunLock",
    "Effect": "Deny",
    "Principal": {"AWS": "*"},
    "Action": "s3:PutObject",
    "Resource": "arn:aws:s3:::" + bucket + "/reports/sync/run-lock.json",
    "Condition": {"Null": {"s3:if-match": "true", "s3:if-none-match": "true"}},
}
def canonical(value):
    if isinstance(value, list):
        items = [canonical(v) for v in value]
        return items[0] if len(items) == 1 else sorted(items, key=json.dumps)
    if isinstance(value, dict):
        if set(value) == {"AWS"} and canonical(value["AWS"]) == "*":
            return "*"
        return {k: canonical(v) for k, v in value.items()}
    return value
def statements(policy):
    return {json.dumps(canonical(s), sort_keys=True) for s in json.loads(policy or "{}").get("Statement", [])}
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
problems = []
sso = sorted(c["address"] for c in changes if "aws_ssoadmin" in c["address"])
if sso:
    problems.append("an account assignment or permission set changes: " + str(sso))
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["address"] != target)
if others:
    problems.append("changes other than the evidence bucket's policy: " + str(others))
found = [c["change"] for c in changes if c["address"] == target]
if not found:
    problems.append("the evidence bucket's policy does not change: is v1-e40-t07 merged in this checkout, or applied already?")
added = set()
for change in found:
    if change["actions"] != ["update"]:
        problems.append(target + " is " + "/".join(change["actions"]) + ", expected an update in place")
    before, after = change["before"] or {}, change["after"] or {}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k) or (change.get("after_unknown") or {}).get(k))
    if changed != ["policy"]:
        problems.append(target + " changes " + str(changed) + ", expected only policy")
        continue
    old, new = statements(before.get("policy")), statements(after.get("policy"))
    added, removed = new - old, old - new
    if removed:
        problems.append("statements removed or changed: " + str(sorted(removed)))
    if added != {json.dumps(canonical(expected), sort_keys=True)}:
        problems.append("statements added are not exactly the run lock deny: " + str(sorted(added)))
if problems:
    print("PLAN STOP: " + "; ".join(problems))
else:
    print("PLAN OK: 0 to add, 1 to change, 0 to destroy; the evidence bucket's policy gains DenyUnconditionalWritesOfTheRunLock and nothing else in it changes; no account assignment or permission set changes; nothing else")
    for statement in sorted(added):
        print(json.dumps(json.loads(statement), indent=2, sort_keys=True))
RUNLOCKPLAN
```
Success looks like `PLAN OK: 0 to add, 1 to change, 0 to destroy; the evidence bucket's policy gains
DenyUnconditionalWritesOfTheRunLock …; nothing else`, then the statement, naming
`arn:aws:s3:::debate-dev-evidence-a7508de8/reports/sync/run-lock.json`. **`PLAN STOP` stops
everything**: send its line and the plan to the PM. Either way, send
`/tmp/run-lock-conditional-writes-<env>-plan.txt` and the `PLAN` line to the PM, and wait for the PM's
word before step 3.

## 3. The apply, after the PM's word

**Operator command** (expected runtime ~1 min)
Where: `$WT`, the same window, after the PM's word, on any day but Wednesday
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; elif [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the run's day; apply on another day"; else AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" apply -input=false run-lock-conditional-writes.tfplan; fi
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` A stale plan
(`Saved plan is stale`) means something changed in between: go back to step 2. Never `-target`.

## 4. The probe again: the blind write is refused

Run step 1's block again, unchanged. Success looks like:

```text
lock: free
== 1. scratch key, blind:
(BadDigest)
== 2. the lock, blind:
(AccessDenied) explicit deny in a resource-based policy
== 3. the lock, conditional on a tag nothing has:
(PreconditionFailed)
lock unchanged: "<the same entity tag as step 1>"
```

Request 2 is the deny. Request 1 shows it reaches no key beside the lock, and request 3 shows a
conditional write still gets through the bucket to its condition. Still `(BadDigest)` on request 2:
the deny is not in force, so read the apply's output. `(AccessDenied)` on request 3: the deny refuses
conditional writes too, and **the cloud run would stop on Wednesday**. Tell the PM at once; the
remedy is to re-apply the previous policy.

## 5. A conditional write that succeeds: a take and a release (dev only)

Steps 1 and 4 show what the bucket refuses. This step shows the lock's own writes still succeed, by
the path the cloud run uses: a bucket-mode command takes the lock with `If-Match`, holds it and
releases it with `If-Match`. `store sync --push` over `quarantine/_probe/`, a prefix with nothing to
move, does that and transfers nothing. It writes at the lock's key, as every runner does, so it runs
only while the lock is free. It needs a dev release carrying `v1-e40-t04` (bucket mode) on this Mac.
Prod's bucket holds no lock to take, so this step is dev's alone.

First the dry run, which takes no lock and changes nothing:

**Operator command** (expected runtime ~1 min)
Where: your Mac, the same window
```bash
cd "$HOME"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else env DEBATE_ENV=dev DEBATE_CASELIST__RUN_STATE=bucket debate-research --json store sync --prefix quarantine/_probe/ > /tmp/run-lock-take-dry-run.json; echo "exit $?"; python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1]))["data"]; print("applied", d["applied"], "| counts", d["counts"])' /tmp/run-lock-take-dry-run.json; fi
```
Success looks like `exit 0`, then `applied False | counts {...}` with `'new': 0` and `'changed': 0`:
nothing would be transferred. Anything above zero under `new` or `changed`: stop, and choose another
empty prefix with the PM.

**The take and the release.** The block refuses a Wednesday, a `DEBATE_` override, a running pull and
a held lock. Then it notes the time and the lock's entity tag, runs the push, and reads the lock back.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the same window
```bash
cd "$HOME"
LOCK_STATE=$(aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile debate-dev-evidence 2>/dev/null | python3 -I -c 'import json, sys; print(json.load(sys.stdin).get("state", "unreadable"))' 2>/dev/null || echo absent)
if [ "$ENVIRONMENT" != dev ]; then echo "STOP: this step is dev's alone"; elif [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ "$LOCK_STATE" != free ]; then echo "STOP: the lock is ${LOCK_STATE}; run this when it is free"; else
  STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  BEFORE=$(aws s3api head-object --profile debate-dev-evidence --bucket "$BUCKET" --key reports/sync/run-lock.json --query ETag --output text)
  env DEBATE_ENV=dev DEBATE_CASELIST__RUN_STATE=bucket debate-research --json store sync --apply --prefix quarantine/_probe/ > /tmp/run-lock-take.json; echo "exit $?"
  grep -oE '"code": "[A-Z_]+"' /tmp/run-lock-take.json
  python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1])).get("data") or {}; print("applied", d.get("applied"), "| transferred", d.get("transferred"))' /tmp/run-lock-take.json
  AFTER=$(aws s3api head-object --profile debate-dev-evidence --bucket "$BUCKET" --key reports/sync/run-lock.json --query ETag --output text)
  aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile debate-dev-evidence | python3 -I -c 'import json, sys; b = json.load(sys.stdin); started = sys.argv[1]; print("state", b["state"], "| released after this block started:", (b.get("renewed_at") or "") >= started)' "$STARTED"
  [ "$BEFORE" != "$AFTER" ] && echo "the lock was written: ${BEFORE} then ${AFTER}" || echo "THE LOCK WAS NOT WRITTEN"
fi
rm -f /tmp/run-lock-take-dry-run.json /tmp/run-lock-take.json
```
Success looks like `exit 0` with no `"code"` line, `applied True | transferred 0`, then `state free |
released after this block started: True`, then `the lock was written: "<tag>" then "<another tag>"`. That is the push's take
and release, both `If-Match` writes the bucket accepted. Two kinds of stop:

* `RUN_LOCK_HELD`: a runner took the lock after the block read it. Nothing was transferred. Wait for
  it, then run the block again.
* An `AccessDenied` code, or `THE LOCK WAS NOT WRITTEN`: the bucket refuses the lock's own
  conditional writes, and **the cloud run would stop on Wednesday**. Tell the PM at once.

## 6. The next Wednesday's run

The cloud run takes the lock, renews it every five minutes and releases it, every write `If-Match`.
On the Thursday after the apply, its record is the last proof:

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
env DEBATE_ENV=dev debate-research caselist runs --remote --last 1
```
Success looks like Wednesday's run, `succeeded`, with no `RUN_LOCK_LOST` and no `AccessDenied` in its
failures. A run that failed with either since the apply: tell the PM, with the run's id.

## Prod

The same blocks with `ENVIRONMENT=prod` set in the first block, after the PM's word on dev and with
the pilot's next promotion: [Before you start](#before-you-start), steps 1 to 4, and the record. Prod's
plan names `arn:aws:s3:::debate-prod-evidence-a7508de8/reports/sync/run-lock.json`. Step 5 is dev's
alone, and step 6 has nothing to read in prod.

## The record

Dates and results only: no account ids (this repository is public).

| | dev | prod |
|---|---|---|
| Probe before the apply (step 1): `BadDigest`, `BadDigest`, `PreconditionFailed`, lock unchanged | not run yet | not run yet |
| Plan read by the PM (step 2): `PLAN OK`, `0 to add, 1 to change, 0 to destroy` | not run yet | not run yet |
| Applied (step 3) | not applied yet | not applied yet |
| Probe after the apply (step 4): `BadDigest`, `AccessDenied` (explicit deny), `PreconditionFailed`, lock unchanged | not run yet | not run yet |
| A take and a release succeed (step 5) | not run yet | — |
| The next Wednesday's run succeeded (step 6) | not run yet | — |

## References

* [Enforce conditional writes on Amazon S3 buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html):
  the condition keys, the multipart exemption and `CopyObject`.
* [Conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html):
  `If-None-Match`, `If-Match`, `412` and `409`.
* ADR-0020 (4), the run lock; [evidence-store-layout.md](../architecture/evidence-store-layout.md),
  the key; [evidence-store.md](evidence-store.md), the evidence store's applies.
* `infrastructure/modules/evidence_bucket/main.tf`, the statement, and its tests in
  `infrastructure/modules/evidence_bucket/tests/evidence_bucket.tftest.hcl`.

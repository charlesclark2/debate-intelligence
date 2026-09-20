# Runbook: Terraform bootstrap and environments

How the Terraform state buckets and the two environment roots are created and verified. Spec:
[`v1-e29-t02-terraform-bootstrap`](../../plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml).
Decisions: [ADR-0010](../adr/0010-primary-aws-region.md) (one account, two environments separated
by tag and name), [ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md) (no third
environment).

Runs after [aws-account-baseline.md](aws-account-baseline.md) and before
`v1-e29-t03-evidence-buckets`.

Written for an adult engineer with administrator access to the account. **Every step here is run
by a human operator.** CI has no AWS credentials — the GitHub OIDC plan/apply roles arrive in
`v2-e10-t03` — and an agent session never runs `apply`, `init -migrate-state` or `force-unlock`.

## What this bootstrap is

| | |
|---|---|
| Region | `us-east-1` ([ADR-0010](../adr/0010-primary-aws-region.md)) |
| State buckets | `debate-dev-tfstate-a7508de8` and `debate-prod-tfstate-a7508de8` — one per environment, private, versioned, SSE-S3, public access blocked, TLS required |
| Locking | The S3 backend's native lock object (`use_lockfile`, Terraform ≥ 1.10). No DynamoDB table |
| Roots | `infrastructure/bootstrap/organization`, `infrastructure/bootstrap/state`, `infrastructure/envs/dev`, `infrastructure/envs/prod` |
| State keys | `bootstrap/organization/`, `bootstrap/state/<env>/`, `envs/<env>/`, each `terraform.tfstate` |

One bucket per environment, not one shared bucket: `DebateMaintainer` denies `debate-prod-*`, so a
dev-scoped session is refused the prod state file by the same policy that refuses it prod
evidence. A shared bucket would hand every dev session the prod state, which lists every prod
resource.

The `a7508de8` suffix exists because S3 bucket names are a global namespace. It is a committed
constant, not the account id, and not a `random_id` — the environment roots' `backend` blocks
cannot contain expressions, so the name has to be knowable before the apply.

## Before you start

**Terraform ≥ 1.10.** The `use_lockfile` backend argument does not exist before it, and every
root in this repository now pins `>= 1.10.0, < 2.0.0`. Check and upgrade:

```bash
terraform version
brew trust hashicorp/tap          # only if brew refuses the formula as untrusted
brew upgrade hashicorp/tap/terraform
```

**tflint**, for `scripts/terraform_checks.sh`. It is not in homebrew-core — the formula was
removed — so it comes from the project's own tap:

```bash
brew tap terraform-linters/tap
brew trust terraform-linters/tap        # only if brew refuses the tap as untrusted
brew install terraform-linters/tap/tflint
tflint --version
```

`brew install tflint` fails with "No available formula". If you would rather not add a tap, the
release binary works just as well — the AWS ruleset still comes from `tflint --init`, which
`scripts/terraform_checks.sh` runs for you:

```bash
curl -sSL -o /tmp/tflint.zip \
  https://github.com/terraform-linters/tflint/releases/download/v0.64.0/tflint_darwin_arm64.zip
unzip -o /tmp/tflint.zip -d /usr/local/bin && tflint --version
```

**Three SSO profiles.** `debate-dev` and `debate-prod` come from
[aws-account-baseline.md](aws-account-baseline.md) step 6. This runbook also needs a break-glass
profile, because `DebateMaintainer` cannot write `debate-prod-*` and `DebateReadOnly` cannot write
anything. Add it with `aws configure sso` if it does not exist:

```ini
[profile debate-admin]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateBreakGlassAdmin
region = us-east-1
output = json
```

Sign in and confirm which identity you are about to apply as — every step below says which
profile it wants:

```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev
aws sts get-caller-identity --profile debate-admin
```

**The owner email**, which is not in the repository. Create the two gitignored files:

```bash
cd <repo>
printf 'owner = "<your-email>"\n' > infrastructure/bootstrap/state/terraform.tfvars
printf 'owner = "<your-email>"\n' > infrastructure/envs/dev/owner.auto.tfvars
printf 'owner = "<your-email>"\n' > infrastructure/envs/prod/owner.auto.tfvars
```

## Step 1 — Create the dev state bucket and migrate its state

Profile: `debate-dev`. Expected runtime: about 2 minutes.

`infrastructure/bootstrap/state` stores its own state in the bucket it creates, so the first apply
runs on a local backend. `backend.tf` is never edited; the temporary local backend comes from a
gitignored `backend_override.tf`, which Terraform merges over the real one. The local state path
is per environment so dev's state can never be picked up by a prod apply.

```bash
cd <repo>/infrastructure/bootstrap/state
export AWS_PROFILE=debate-dev

cat > backend_override.tf <<'OVERRIDE'
terraform {
  backend "local" {
    path = "bootstrap-dev.tfstate"
  }
}
OVERRIDE

terraform init -reconfigure
terraform apply -var-file=dev.tfvars
```

Read the plan before approving. It should create exactly one bucket and its seven configuration
resources, named `debate-dev-tfstate-a7508de8`, and nothing else. Then migrate the state into it:

```bash
rm backend_override.tf
terraform init -migrate-state -backend-config=dev.s3.tfbackend
```

Answer `yes` when Terraform offers to copy the existing state to the new backend. Confirm the
migration landed and left nothing behind:

```bash
terraform plan -var-file=dev.tfvars          # "No changes."
aws s3api list-objects-v2 --profile debate-dev \
  --bucket debate-dev-tfstate-a7508de8 --query 'Contents[].Key'
```

The listing shows `bootstrap/state/dev/terraform.tfstate`. Keep a dated copy of the local file
outside the repository and then remove it:

```bash
mkdir -p ~/aws-backups/debate-terraform-state
cp bootstrap-dev.tfstate ~/aws-backups/debate-terraform-state/bootstrap-state-dev-$(date +%Y%m%d).tfstate
rm -f bootstrap-dev.tfstate bootstrap-dev.tfstate.backup
```

If the bucket name is already taken globally, `apply` fails with `BucketAlreadyExists`. Pick a new
suffix (`openssl rand -hex 4`), change it in `dev.tfvars`, `prod.tfvars`, both
`<env>.s3.tfbackend` files, both `infrastructure/envs/<env>/backend.tf` files and
`infrastructure/bootstrap/organization/backend.tf`, commit, and start again.

## Step 2 — Create the prod state bucket and migrate its state

Profile: `debate-admin` (`DebateBreakGlassAdmin`). `DebateMaintainer` is denied `debate-prod-*` by
design, and `DebateReadOnly` cannot create anything — a prod apply is a deliberate break-glass
action. Expected runtime: about 2 minutes.

Same sequence, different environment. The working directory is currently bound to the dev backend,
so the override has to be re-established with `-reconfigure`, which discards that binding without
touching the dev state already in S3.

```bash
cd <repo>/infrastructure/bootstrap/state
export AWS_PROFILE=debate-admin

cat > backend_override.tf <<'OVERRIDE'
terraform {
  backend "local" {
    path = "bootstrap-prod.tfstate"
  }
}
OVERRIDE

terraform init -reconfigure
terraform apply -var-file=prod.tfvars
```

The plan must create `debate-prod-tfstate-a7508de8` and **must not** show any change to the dev
bucket. If it proposes renaming a bucket, the local state from step 1 is still present: stop,
check that `bootstrap-dev.tfstate` is gone, and start step 2 again.

```bash
rm backend_override.tf
terraform init -migrate-state -backend-config=prod.s3.tfbackend
terraform plan -var-file=prod.tfvars          # "No changes."

cp bootstrap-prod.tfstate ~/aws-backups/debate-terraform-state/bootstrap-state-prod-$(date +%Y%m%d).tfstate
rm -f bootstrap-prod.tfstate bootstrap-prod.tfstate.backup
```

Afterwards, switching this root between environments is an explicit `init`, and the `-var-file`
and the `-backend-config` always name the same environment:

```bash
terraform init -reconfigure -backend-config=dev.s3.tfbackend
terraform plan -var-file=dev.tfvars
```

## Step 3 — Point the environment roots at their backends

Profile: `debate-dev` for dev, `debate-admin` for prod. Both roots are empty of resources at this
task — the evidence buckets arrive in `v1-e29-t03-evidence-buckets` — so this proves the backend
works, nothing more.

```bash
cd <repo>
AWS_PROFILE=debate-dev   terraform -chdir=infrastructure/envs/dev  init
AWS_PROFILE=debate-dev   terraform -chdir=infrastructure/envs/dev  plan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/prod init
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/prod plan
```

Each `init` must print `Successfully configured the backend "s3"!`, and each `plan` must report no
changes. A plan that fails the `environment_matches_directory` check means `terraform.tfvars` and
the directory disagree — fix the tfvars, do not silence the check.

## Step 4 — Confirm locking works

Two plans at once against the same state key. `-lock-timeout=0` makes the loser fail immediately
instead of retrying for the default ten minutes.

```bash
cd <repo>
export AWS_PROFILE=debate-dev
terraform -chdir=infrastructure/envs/dev plan -lock-timeout=0 > /tmp/lock-a.txt 2>&1 &
terraform -chdir=infrastructure/envs/dev plan -lock-timeout=0 > /tmp/lock-b.txt 2>&1 &
wait
grep -l "Error acquiring the state lock" /tmp/lock-a.txt /tmp/lock-b.txt
```

One of the two files must contain `Error acquiring the state lock` with a `Lock Info` block. If
both succeeded, the two plans did not actually overlap — an empty root plans in under a second.
Repeat the same race against `infrastructure/bootstrap/state`, which has real resources to refresh
and so holds the lock for several seconds:

```bash
cd <repo>/infrastructure/bootstrap/state
terraform init -reconfigure -backend-config=dev.s3.tfbackend
terraform plan -var-file=dev.tfvars -lock-timeout=0 > /tmp/lock-a.txt 2>&1 &
terraform plan -var-file=dev.tfvars -lock-timeout=0 > /tmp/lock-b.txt 2>&1 &
wait
grep -l "Error acquiring the state lock" /tmp/lock-a.txt /tmp/lock-b.txt
```

While a lock is held, `envs/dev/terraform.tfstate.tflock` exists in the bucket. If a crashed run
leaves one behind, `terraform force-unlock <lock-id>` removes it — only after confirming no other
`terraform` process is running, and never from an agent session.

## Step 5 — Confirm a dev credential cannot reach the prod state

This is the premise ADR-0010's single-account fallback rests on, so check it on purpose.

Use `iam simulate-principal-policy`, which evaluates the policies **without performing the
actions**. Never test a deny by attempting the real call: if the deny has failed, the test itself
reads or overwrites the prod state file.

`iam:SimulatePrincipalPolicy` is not in `PowerUserAccess`, so the simulation itself runs under
`debate-admin` while the principal being simulated is the `DebateMaintainer` role that `debate-dev`
assumes:

```bash
ROLE=$(aws iam list-roles --profile debate-admin \
  --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateMaintainer`)].Arn' --output text)

aws iam simulate-principal-policy --profile debate-admin --policy-source-arn "$ROLE" \
  --action-names s3:ListBucket s3:GetObject s3:PutObject s3:DeleteObject \
  --resource-arns \
    "arn:aws:s3:::debate-prod-tfstate-a7508de8" \
    "arn:aws:s3:::debate-prod-tfstate-a7508de8/envs/prod/terraform.tfstate" \
    "arn:aws:s3:::debate-prod-tfstate-a7508de8/bootstrap/organization/terraform.tfstate" \
  --query 'EvaluationResults[].{Action:EvalActionName,Resource:EvalResourceName,Decision:EvalDecision}' \
  --output table
```

Every row must read `explicitDeny`. Anything reading `allowed` means the environment boundary is
gone: stop and fix `identity.tf` before putting anything else in the account.

The same simulation against the **dev** bucket must read `allowed`, or the dev roots cannot work:

```bash
aws iam simulate-principal-policy --profile debate-admin --policy-source-arn "$ROLE" \
  --action-names s3:ListBucket s3:GetObject s3:PutObject \
  --resource-arns \
    "arn:aws:s3:::debate-dev-tfstate-a7508de8" \
    "arn:aws:s3:::debate-dev-tfstate-a7508de8/envs/dev/terraform.tfstate" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
```

## Step 6 — Migrate the organization root's state out of the main clone

`infrastructure/bootstrap/organization` has kept a local `terraform.tfstate` since
`v1-e29-t01-aws-account-baseline`, in the operator's main clone only. Its resources are
account-wide and admin-applied, so its state belongs with the other prod-scoped state: the prod
bucket, under its own key, where `DebateMaintainer`'s deny keeps a dev session out of it.

Profile: `debate-admin`. Run from the **main clone**, which is where the local state file is. This
step needs `infrastructure/bootstrap/organization/backend.tf`, which arrives with this task's PR —
so either run it after the PR has merged into `dev`, or bring that one file over first:

```bash
cd <main-clone>
git checkout task/v1-e29-t02-terraform-bootstrap -- infrastructure/bootstrap/organization/backend.tf
```

Back the state up first, outside the repository, with the date in the name. This file names every
permission set and policy in the account; treat it as sensitive even though it holds no secrets:

```bash
cd <main-clone>
mkdir -p ~/aws-backups/debate-terraform-state
cp infrastructure/bootstrap/organization/terraform.tfstate \
   ~/aws-backups/debate-terraform-state/organization-$(date +%Y%m%d-%H%M%S).tfstate
ls -l ~/aws-backups/debate-terraform-state/
```

Then migrate and verify:

```bash
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/bootstrap/organization init -migrate-state
terraform -chdir=infrastructure/bootstrap/organization plan
```

This state was written by Terraform 1.7.3 (serial 31, 31 resources). The first write from 1.16.3
upgrades its recorded version, and 1.7.3 cannot read it afterwards — which is the point of the
dated backup above, and harmless now that every root pins `>= 1.10`.

Answer `yes` to the copy. The plan must report **no changes**; a plan that wants to create the
permission sets or the trail again means the state did not come across — stop, restore the backup
over `terraform.tfstate`, and do not apply.

With a clean plan confirmed, remove the local state from the clone and check the object is in the
bucket:

```bash
cd <main-clone>
rm -f infrastructure/bootstrap/organization/terraform.tfstate \
      infrastructure/bootstrap/organization/terraform.tfstate.backup
aws s3api list-objects-v2 --profile debate-admin \
  --bucket debate-prod-tfstate-a7508de8 --query 'Contents[].Key'
terraform -chdir=infrastructure/bootstrap/organization plan   # still "No changes."
```

The dated backup stays. It is the only copy if the bucket is ever lost, and it costs nothing.

## What to record

Fill this in as you go and commit it with the session report. Bucket names are fine here; the
account id is not.

| | dev | prod |
|---|---|---|
| State bucket | `debate-dev-tfstate-a7508de8` | `debate-prod-tfstate-a7508de8` |
| Applied on | | |
| Applied as | `debate-dev` (DebateMaintainer) | `debate-admin` (DebateBreakGlassAdmin) |
| State migrated into the bucket | | |
| `envs/<env>` init against the S3 backend | | |
| Concurrent-plan lock error observed | | |

| Check | Result | Date |
|---|---|---|
| `DebateMaintainer` denied the prod state bucket (simulate-principal-policy) | | |
| `DebateMaintainer` allowed the dev state bucket | | |
| `bootstrap/organization` migrated, plan clean, local state removed | | |
| Dated state backups in `~/aws-backups/debate-terraform-state/` | | |

## Recurring checks

| When | What |
|---|---|
| After any apply | `terraform plan` reports no changes in the root you applied |
| After any change to `identity.tf` | Re-run step 5; the deny is what the environment boundary is made of |
| Quarterly | No `*.tfstate` file has reappeared in either clone (`find . -name '*.tfstate'` under the repo returns nothing) |
| Quarterly | The state buckets still have versioning on and public access blocked |
| When Terraform is upgraded | `scripts/terraform_checks.sh` passes, and the pin in every `versions.tf` still admits the installed version |

## What this bootstrap deliberately does not do

Owned by later tasks, not here:

- Evidence buckets, the evidence KMS key and the least-privilege operator permission set —
  `v1-e29-t03-evidence-buckets`.
- GitHub OIDC plan/apply roles — `v2-e10-t03`. Until they exist, CI runs only
  `scripts/terraform_checks.sh`, which needs no credentials, and every apply is a step in this
  runbook.
- V2 KMS/Secrets Manager (`v2-e10-t04`) and networking/ECS (`v2-e10-t05`).

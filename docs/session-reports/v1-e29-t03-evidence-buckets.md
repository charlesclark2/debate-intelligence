# Session report: v1-e29-t03-evidence-buckets

| | |
|---|---|
| Task | `v1-e29-t03-evidence-buckets` — Evidence buckets and operator access |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t03-evidence-buckets` |
| Session status | COMPLETE — both environments applied by the operator on 2026-09-20 (`15 added, 0 changed, 0 destroyed` each) and every access check verified live. Three spec wordings need the PM's amendment; see **Deviations** |

## Summary

`infrastructure/modules/evidence_bucket` now creates one environment's evidence store: a
customer-managed KMS key with rotation and its own alias, and a private, versioned, SSE-KMS bucket
with S3 Bucket Keys, all four block-public-access flags, `BucketOwnerEnforced`, a TLS-only policy
and lifecycle rules that age out superseded versions without ever expiring a current one outside
`exports/`. The key and its alias are ordinary, separately addressable resources with outputs of
their own, so `v2-e10-t04` can adopt them with `moved` blocks instead of creating a second key and
re-encrypting the corpus, and `additional_reader_principal_arns` (empty in V1) is how the V2
worker and API roles attach read-and-presign access later without editing the module.

Access is two Identity Center permission sets rather than one. `DebateEvidenceOperator` is
everyday work — list the documented prefixes, read, publish, use the key — with **no
`s3:DeleteObject` at all**. `DebateEvidenceRemoval` is the only credential in the account that can
delete evidence: scoped to `raw/`, `parsed/`, `files/`, `manifests/` and `quarantine/`, able to
write only the suppression list under `manifests/_suppression/`, and assigned to one person, which
a variable validation enforces. Both are modelled on the `SitePublisher` set of
`v1-e36-t02-site-hosting`, as the operator asked. 11 offline `terraform test` runs with a mocked
provider assert all of it; both environment roots call the module from an identical
`evidence_store.tf` and validate.

`docs/architecture/evidence-store-layout.md` is now the layout contract — bucket naming,
content-addressed sha256 keys with a two-level fan-out, the eight prefixes and which task writes
each — and `docs/runbooks/evidence-store.md` is the operator procedure, with every deny answered
by `aws iam simulate-principal-policy` rather than by attempting the real call.

The operator applied dev and then prod on 2026-09-20 and worked through
`docs/runbooks/evidence-store.md`: a probe object round-tripped under the everyday profile and
came back encrypted with that environment's own key, the bare bucket listing was refused while a
prefix listing worked, every deny came back `implicitDeny` under `simulate-principal-policy`, and
the takedown profile removed the probe *and its version* under `quarantine/` while being refused
under `reports/`. The runbook's record table holds the results. The two environments hold
different customer-managed keys, so ADR-0010 rule 4 is enforced by cryptography as well as by
policy.

Three things the PM should look at first. **The KMS alias is `alias/debate-<env>-evidence`, not
the spec's `alias/debate-evidence-<env>`**, because `DebateMaintainer`'s existing guardrail denies
`alias/debate-prod-*` and the spec's form would slip straight past it — Deviation 1. **The
`raw/` key form in this task's layout document disagrees with `v1-e30-t05-caselist-publish`**,
which still says `raw/<caselist>/<sha256>.<ext>` — Deviation 2, a spec edit and not a migration,
since nothing has been written to either bucket yet. **The delete-denied check in the plan node
names the wrong profile**: `debate-dev` is `DebateMaintainer`, which holds `PowerUserAccess` and
*can* delete a dev object; the least-privilege claim belongs to the new `debate-dev-evidence`
profile — Deviation 3.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `bucket-module` — key, versioning, lifecycle | DONE | `infrastructure/modules/evidence_bucket/{main,variables,outputs,versions}.tf` + `README.md`. `operator_access.tf` (listed under the later node) landed in the same commit, so the module's tests could assert both permission sets in one pass |
| `module-tests` — offline `terraform test` | DONE | `tests/evidence_bucket.tftest.hcl`, 11 runs with `mock_provider "aws"`: no credentials, no network, no AWS account. Includes two `expect_failures` runs for the variable validations |
| `key-layout-doc` — evidence store key layout | DONE | `docs/architecture/evidence-store-layout.md`, indexed in `docs/README.md`. Records the two earlier documents that name `raw/` differently |
| `operator-access-and-envs` — permission sets and env wiring | DONE | `evidence_store.tf` character-for-character identical in `envs/dev` and `envs/prod`; only the retention in `terraform.tfvars` differs. Both roots validate |
| `operator-apply` — apply dev, then prod | DONE | Operator applied dev then prod on 2026-09-20, 15 resources each with nothing changed or destroyed, so the site resources in those roots were untouched. All 18 live checks pass; `docs/runbooks/evidence-store.md` **The record** has them |

## Acceptance criteria

Every Terraform command below was run with no AWS credentials; `terraform test` uses
`mock_provider "aws"` and `validate` runs against `init -backend=false`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** module passes `terraform test` offline asserting versioning, SSE-KMS with the module's key, four PAB flags, `BucketOwnerEnforced`, and a TLS deny | PASS | `terraform -chdir=infrastructure/modules/evidence_bucket test` → `Success! 11 passed, 0 failed.` The run `bucket_is_private_versioned_and_kms_encrypted` asserts all four flags, `BucketOwnerEnforced`, `sse_algorithm == "aws:kms"` with `kms_master_key_id == aws_kms_key.evidence.arn`, `bucket_key_enabled`, versioning `Enabled`, the bucket name and `force_destroy == false`; `bucket_policy_requires_tls_and_this_key` asserts the `aws:SecureTransport = false` deny |
| **ac2** noncurrent versions to `STANDARD_IA` at 30 days, expire at 365 in prod (30 in dev), abort incomplete multipart at 7 days, `exports/` expires at 1 day, no other rule expires current versions | PASS | Same run. `dev_ages_out_superseded_versions_after_thirty_days` → expiry at 30, **no** transition (see Deviation 4), abort at 7, `exports/` expiration `days = 1` scoped to `prefix = "exports/"`, and `alltrue([… length(rule.expiration) == 0 \|\| rule.filter[0].prefix == "exports/"])`. `prod_moves_superseded_versions_to_infrequent_access_then_expires_them` → transition at 30 to `STANDARD_IA`, expiry at 365, same no-current-expiry assertion |
| **ac3** `EvidenceOperator` grants only ListBucket (prefix-scoped), GetObject, PutObject, GetObjectVersion and kms Encrypt/Decrypt/GenerateDataKey; a DeleteObject attempt returns AccessDenied. `EvidenceRemoval` deletes under the five prefixes only (a delete under `reports/` denied) and is assigned to Charlie alone | PASS | **Offline:** `operator_permission_set_reads_and_publishes_but_cannot_delete` asserts the action set is **exactly** those seven, every resource is this environment's own bucket or key, every statement is an `Allow`, and the `s3:prefix` condition equals the eight documented prefixes; `removal_permission_set_deletes_disclosed_material_and_nothing_else` asserts every `s3:Delete*` resource sits under one of the five prefixes, that the only `PutObject` resource is `manifests/_suppression/*`, and one assignment; `takedown_rights_are_refused_to_a_second_person` shows the module refuses a second assignee. **Live, both environments** (`aws iam simulate-principal-policy`, which evaluates without performing): operator `s3:DeleteObject` and `s3:DeleteObjectVersion` → `implicitDeny`; operator `s3:PutBucketPolicy`, `s3:PutLifecycleConfiguration`, `s3:PutBucketPublicAccessBlock` → `implicitDeny`; remover delete under `raw/` → `allowed`; remover delete under `reports/` → `implicitDeny`; remover `PutObject` under `raw/` → `implicitDeny`. A real `aws s3 ls s3://<bucket>` returned `AccessDenied` while `…/quarantine/` listed. `list-account-assignments` → `DebateProdEvidenceRemoval: 1`, `DebateDevEvidenceRemoval: 1` |
| **ac4** `docs/architecture/evidence-store-layout.md` documents bucket naming, the eight prefixes with examples, content-addressed sha256 keys, and which task writes each | PASS | File committed. `grep -c "quarantine/" docs/architecture/evidence-store-layout.md` → `3`. It carries the bucket table, the fan-out explanation, the "what never appears in a key" rule from the data-use policy, a per-prefix owner table and 13 example keys |
| **ac6** the KMS key and its alias are separate resources exposed as outputs, and a `terraform test` run with a non-empty `additional_reader_principal_arns` shows those principals in the bucket and key policies with read/decrypt-only actions | PASS | `key_is_customer_managed_rotated_and_separately_addressable` asserts rotation, the 30-day deletion window, the alias name and target, and `output.kms_key_arn` / `output.kms_alias_name`. `additional_readers_may_read_and_decrypt_and_nothing_else` passes two role ARNs and asserts each appears in both policies, that the bucket-policy `Allow` action set is exactly `s3:ListBucket`, `s3:GetObject`, `s3:GetObjectVersion`, that the key-policy action set is exactly `kms:Decrypt`, `kms:DescribeKey`, and that every granted resource is this bucket |
| **ac5** the operator has applied dev then prod; the runbook records apply dates, bucket names (no account ids) and a put/get/delete-denied check with each SSO profile | PASS | Both applied 2026-09-20, `15 added, 0 changed, 0 destroyed` each. `docs/runbooks/evidence-store.md` **The record** is filled in: dates, `debate-dev-evidence-a7508de8` / `debate-prod-evidence-a7508de8`, the two key aliases, and 18 rows of check results per environment — no account ids. Per environment: a probe object put with the everyday profile returned a version id and round-tripped; `head-object` showed `aws:kms` with **that environment's own** CMK; the takedown profile listed one version, deleted it by version id and left the prefix empty with no delete marker |
| **node** `bucket-module`: `main.tf` matches `aws_s3_bucket_versioning` | PASS | `grep -c aws_s3_bucket_versioning infrastructure/modules/evidence_bucket/main.tf` → `2` |
| **node** `bucket-module`: `main.tf` matches `restrict_public_buckets = true` | PASS | `grep -c 'restrict_public_buckets = true' …/main.tf` → `1` |
| **node** `module-tests`: `terraform -chdir=infrastructure/modules/evidence_bucket test` | PASS | `Success! 11 passed, 0 failed.` |
| **node** `key-layout-doc`: doc matches `quarantine/` | PASS | `grep -c "quarantine/" docs/architecture/evidence-store-layout.md` → `3` |
| **node** `operator-access-and-envs`: `terraform -chdir=infrastructure/envs/dev validate` | PASS | `Success! The configuration is valid.` |
| **node** `operator-access-and-envs`: `terraform -chdir=infrastructure/envs/prod validate` | PASS | `Success! The configuration is valid.` |
| **node** `operator-apply`: runbook matches `debate-prod` | PASS | `grep -c "debate-prod" docs/runbooks/evidence-store.md` → `13` |
| **node** `operator-apply`: Charlie confirms both buckets and least privilege | PASS | Read back from the account rather than eyeballed, which is stronger: `get-public-access-block` → all four `true`; `get-bucket-versioning` → `Enabled`; `get-bucket-encryption` → `aws:kms` with the environment's key and `BucketKeyEnabled: true`; `get-bucket-lifecycle-configuration` → three rules, dev with `NoncurrentVersionExpiration: 30` and no transition, prod with `STANDARD_IA` at 30 and expiry at 365, and in both the **only** `Expiration` block scoped to `exports/` at `Days: 1`, abort at 7; `kms describe-key` → `CUSTOMER`, `Enabled`; `get-key-rotation-status` → `KeyRotationEnabled: true`, 365-day period |
| Repository-wide Terraform checks | PASS | `scripts/terraform_checks.sh` → `All Terraform checks passed.` (fmt, validate on 4 roots and 4 modules, tflint config parity and `tflint --recursive`), 1 min 43 s |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 278 files, 38 epics, 220 tasks, 20 releases` |

## Files changed

**`infrastructure/modules/evidence_bucket/`** (new) — the module. `main.tf` (key, alias, bucket,
public access block, ownership controls, SSE-KMS, versioning, lifecycle, bucket policy),
`operator_access.tf` (both permission sets, their inline policies and assignments),
`variables.tf`, `outputs.tf`, `versions.tf`, `README.md`, `.tflint.hcl`, `.terraform.lock.hcl` and
`tests/evidence_bucket.tftest.hcl`.

**`infrastructure/envs/dev/`, `infrastructure/envs/prod/`** — `evidence_store.tf` (new, identical
in both), five `evidence_*` variables and nine `evidence_*` outputs appended to the roots'
`variables.tf` and `outputs.tf` (still character-for-character identical between the two roots),
the retention value in each `terraform.tfvars`, and the two user-name lists in
`owner.auto.tfvars.example`.

**`docs/`** — `architecture/evidence-store-layout.md` (new, the layout contract),
`runbooks/evidence-store.md` (new, the operator procedure, with its record table filled in from
the two applies), `README.md` (both indexed), and `runbooks/caselist-removal.md`, whose open
permissions note this task answers (Deviation 6).

**`infrastructure/README.md`** — the module in the layout table and a section describing the
evidence store, matching the existing section for the website.

## Deviations from the spec

1. **KMS alias is `alias/debate-<env>-evidence`, not `alias/debate-evidence-<env>`.** The spec's
   plan node gives the latter. `DebateMaintainer`'s guardrail
   (`infrastructure/bootstrap/organization/identity.tf`, `DenyProdKmsKeysByAlias`) denies KMS
   actions on `alias/debate-prod-*`, and ADR-0010 rule 2 requires `debate-<environment>-<purpose>`
   for exactly that reason. `alias/debate-evidence-prod` would not match the deny, so a dev-scoped
   credential could use the prod evidence key — the boundary ADR-0010 rule 4 rests on. Written the
   way the guardrail needs; **the spec text needs amending to match.**

2. **The `raw/` key form disagrees with two earlier documents.** This task owns the layout (ac4)
   and specifies `raw/caselist/<slug>/sha256/ab/cd/<hash>`, which is also the
   `<prefix>/sha256/<ab>/<cd>/<sha256>` form `v1-e29-t04-s3-blob-store` builds. But
   `v1-e30-t05-caselist-publish` says `raw/<caselist>/<sha256>.<ext>` — no `caselist/` segment, no
   fan-out, and an extension — and `docs/runbooks/caselist-removal.md` step 6 used the flat form.
   The layout document records the canonical form and names both disagreements; the runbook
   example was corrected. **`v1-e30-t05` is a spec edit for the PM.** Nothing has been written to
   either bucket, so this costs an edit and not a migration. The extension is dropped on purpose:
   a content-addressed key that carries a filename extension makes two names for identical bytes
   into two objects. Content type and original filename go in the manifest row and object
   metadata.

3. **The delete-denied check cannot use the `debate-dev` profile.** The `operator-apply` node says
   "delete is denied with the `debate-dev` profile". `debate-dev` is `DebateMaintainer`, which
   holds `PowerUserAccess` minus the prod denies and therefore *can* delete a dev object; the
   check would fail for a reason that is not a defect. The least-privilege claim belongs to the
   new `debate-dev-evidence` / `debate-prod-evidence` profiles, which is what the runbook
   simulates. **Worth a wording fix in the spec.**

4. **dev gets no Standard-IA transition.** ac2 reads "transitions noncurrent versions to
   STANDARD_IA after 30 days and expires them after 365 days in prod (30 in dev)". In dev both
   numbers are 30, and S3 rejects a lifecycle rule whose noncurrent expiration is not later than
   its noncurrent transition; Standard-IA also bills a 30-day minimum, so a version that expires
   on the day it would move would cost more, not less. The module omits the transition whenever
   retention is not longer than the transition day, and
   `dev_ages_out_superseded_versions_after_thirty_days` asserts the omission. prod (30/365) gets
   both.

5. **Names the spec gave as examples.** The permission sets are `DebateDevEvidenceOperator` /
   `DebateProdEvidenceOperator` and `DebateDevEvidenceRemoval` / `DebateProdEvidenceRemoval`,
   following the `Debate<Env>SitePublisher` pattern of `v1-e36-t02`. The takedown SSO profiles are
   `debate-dev-evidence-removal` / `debate-prod-evidence-removal` rather than the spec's
   `debate-dev-removal` / `debate-prod-removal`, so that every profile name is `name_prefix` plus
   its purpose and a future non-evidence removal credential cannot collide with this one.

6. **One file outside this task's outputs was edited.** `docs/runbooks/caselist-removal.md`
   (owned by `v1-e30-t01`) carried a note saying the `EvidenceOperator` set has no `DeleteObject`,
   that the PM was amending this task to settle it, and that until then a takedown needed an
   administrator profile. This task settles it, so the note now names the `EvidenceRemoval`
   profiles; the `raw/` example and the sign-in checklist were corrected at the same time. `docs`
   is in the task's `constraints.packages`, but it is another task's document, so it is recorded
   here rather than done quietly.

7. **`EvidenceRemoval` also has `s3:GetObject` on `manifests/_suppression/`.** The spec enumerates
   `PutObject` on that prefix but no plain `GetObject` anywhere. The suppression list is
   append-only and merged as a set union (`v1-e30-t07`), which means reading the current list
   before writing it, and in a versioning-enabled bucket a read without a version id needs
   `s3:GetObject` rather than `s3:GetObjectVersion`. Granted on that one prefix — the only prefix
   this credential may write — and nowhere else.

## Decisions and assumptions

* **`prevent_destroy` on the bucket and the key**, as `bootstrap/state` already does for the state
  bucket. `terraform destroy` in a root holding this module has no legitimate use, and destroying
  the key makes every object permanently unreadable. It cannot be a variable (Terraform requires a
  literal), and it is not assertable in a test, so it is called out in both READMEs. Checked that
  it does not break `terraform test` teardown on Terraform 1.16.3, the pinned version.
* **The bucket policy contains no `Allow` at all** unless `additional_reader_principal_arns` is
  set. Everything the operator and the CLI do comes from the permission sets, where it can be read
  in one place; an account-wide `Allow` in the bucket policy would quietly widen what those sets
  carefully withhold. A test asserts the empty-`Allow` case.
* **Two extra denies in the bucket policy**, beyond the TLS one the spec asks for: an upload that
  explicitly asks for an encryption algorithm other than `aws:kms`, or for another KMS key, is
  denied. Both are guarded by a `Null` condition so that an ordinary `PutObject` which sends no
  encryption header — the common case, which default encryption handles — is unaffected. A test
  asserts the guard, because getting this wrong denies every upload.
* **`ListBucket` is scoped to the documented prefixes, so listing the bucket root is denied.**
  That is what "scoped to the documented prefixes" means in IAM: an absent `s3:prefix` matches no
  `StringLike`. Both READMEs and the runbook say so, and the runbook's expected output includes
  the `AccessDenied` so it is not read as a fault.
* **`kms:DescribeKey` for additional readers**, alongside `kms:Decrypt`. It is read-only key
  metadata that SDKs ask for, and no `kms:ViaService` condition was added: it would be tighter,
  but a wrong `ViaService` silently breaks presigning in V2 and `DescribeKey` is not called
  through S3.
* **A `check` block in each root** warns at plan time when `evidence_operator_user_names` is
  empty. The names live in a gitignored file, so an empty list is easy to end up with and
  otherwise invisible until a sync fails with `AccessDenied`. A `check` block is a warning and not
  a hard failure — which is the right strength here, since a root with no operator assigned is
  still a legitimate thing to apply.
* **The bucket suffix is `a7508de8`**, the committed constant the state and site buckets already
  use. The buckets differ by their `-evidence` purpose segment, and a committed suffix is what
  lets the runbook, a takedown and `debate-research store` name the bucket without reading state.
* **`evidence_removal_user_names` is limited to one entry by a variable validation**, which is how
  "assigned to Charlie alone" becomes machine-checkable; `takedown_rights_are_refused_to_a_second_person`
  asserts the refusal with `expect_failures`.
* **No smoke check was added.** `plan_specs/README.md` asks for one from every task that changes a
  user-facing surface; this task adds infrastructure and IAM, and no CLI command, API route or
  page. The surfaces that read this bucket arrive in `v1-e29-t04` and `v1-e29-t05`, which own
  their own smoke checks.
* **dev is assumed to hold synthetic or sample data only**, per the spec, unless `v1-e30-t06` says
  otherwise. Nothing in this task loads data of any kind, and the test fixtures contain no real
  caselist material and no student names.

## Operator follow-ups

**None outstanding.** The applies and every live check were completed by the operator on
2026-09-20, working through [docs/runbooks/evidence-store.md](../runbooks/evidence-store.md); the
results are in that runbook's **The record** and in the criteria table above. Four SSO profiles
were added to the operator's `~/.aws/config` — `debate-dev-evidence`, `debate-dev-evidence-removal`,
`debate-prod-evidence`, `debate-prod-evidence-removal` — and `evidence_operator_user_names` /
`evidence_removal_user_names` to each root's gitignored `owner.auto.tfvars`.

Two things were corrected during the applies and are committed:

* The runbook gained a **configuration read-back** block in step 5 (public access block,
  versioning, encryption, lifecycle, key rotation). It was written ad hoc during the dev apply,
  because the simulated permission checks said nothing about whether the lifecycle rules had
  actually landed, and that is worth catching in dev rather than in prod. It is the live half of
  what the module's tests assert.
* `aws kms get-key-rotation-status` does not accept an alias, unlike most KMS calls. The runbook
  resolves the alias with `describe-key` first.

No GitHub or CI settings need changing: `scripts/terraform_checks.sh` discovers new module
directories by itself, so the `terraform-checks` job covers `evidence_bucket` without an edit. The
module's `terraform test` is still not part of that script — see **Follow-up work**.

## Follow-up work

* **Spec edits for the PM**, all recorded under **Deviations**: the KMS alias form in this task's
  spec (1), the `raw/` key form in `v1-e30-t05-caselist-publish` (2), and the profile named in
  this task's `operator-apply` node (3).
* **`terraform test` is not in `scripts/terraform_checks.sh`.** The script runs `fmt`, `validate`
  and `tflint`; the module tests of `static_site`, `domain_redirect` and now `evidence_bucket` are
  run by hand. They take seconds and need no credentials, so a `test` pass over
  `infrastructure/modules/*/tests/` belongs in the script and therefore in the `terraform-checks`
  CI job. Left alone here because the script is `v1-e29-t02`'s output and changing it affects
  every task in flight.
* **`v1-e29-t04` and `v1-e29-t05`** should take the bucket name and key from the roots'
  `evidence_bucket_name` / `evidence_kms_key_arn` outputs, or from the committed constant, rather
  than hard-coding a name a third time.
* **`v2-e10-t04`** adopts `aws_kms_key.evidence` and `aws_kms_alias.evidence` with `moved` blocks
  rather than creating a data-class key for evidence. The outputs it needs exist.
* **V2 presigning** attaches its worker and API roles through
  `evidence_additional_reader_principal_arns` in each root's tfvars; no module edit is required,
  and the read-only shape is already covered by a test.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

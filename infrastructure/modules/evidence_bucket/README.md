# `evidence_bucket` module

One environment's evidence store: the private, versioned, KMS-encrypted S3 bucket that is the
system of record for disclosed caselist evidence, camp files, parsed cards, built team files and
reports. Spec:
[`v1-e29-t03-evidence-buckets`](../../../plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml).
Decision: [ADR-0003](../../../docs/adr/0003-s3-source-of-truth-for-raw-artifacts.md).
Region and account structure: [ADR-0010](../../../docs/adr/0010-primary-aws-region.md).
Key layout: [docs/architecture/evidence-store-layout.md](../../../docs/architecture/evidence-store-layout.md).
Operator steps: [docs/runbooks/evidence-store.md](../../../docs/runbooks/evidence-store.md).

Called once from [`envs/dev`](../../envs/dev/) and once from [`envs/prod`](../../envs/prod/) with
different inputs. It holds no account id and no region: the region comes from the calling root's
provider.

## What it creates

| Resource | Why it is the way it is |
|---|---|
| `aws_kms_key.evidence` + `aws_kms_alias.evidence` | A customer-managed key per environment, rotation on, 30-day deletion window. Separate, ordinary resources with outputs of their own so `v2-e10-t04` can adopt them with `moved` blocks instead of creating a second key and re-encrypting the corpus |
| `aws_s3_bucket` + public access block, ownership controls, encryption, versioning | Private, ACLs disabled, SSE-KMS with that key, S3 Bucket Keys on, versioned. `force_destroy` stays false and `prevent_destroy` is set |
| `aws_s3_bucket_lifecycle_configuration` | Superseded versions age out; `exports/` expires after a day; incomplete multipart uploads abort after 7. **No rule expires a current version outside `exports/`** |
| `aws_s3_bucket_policy` | Denies non-TLS requests and uploads that ask for another encryption key. No `Allow` at all unless `additional_reader_principal_arns` is set |
| `aws_ssoadmin_permission_set` ×2 + inline policies + assignments | `EvidenceOperator` and `EvidenceRemoval`, below |

The bucket is `<name_prefix>-<bucket_suffix>` — `debate-dev-evidence-a7508de8`,
`debate-prod-evidence-a7508de8` — and the key alias is `alias/<name_prefix>`. The environment
prefix is load-bearing rather than decorative: `DebateMaintainer` denies `s3:*` on
`debate-prod-*` buckets and KMS actions on `alias/debate-prod-*`
([`bootstrap/organization/identity.tf`](../../bootstrap/organization/identity.tf)), which is how
ADR-0010 rule 4 — prod evidence unreadable by a dev-scoped credential — is enforced in a single
account. A variable validation refuses a `name_prefix` that does not carry its environment.

## Inputs worth knowing about

| Variable | Notes |
|---|---|
| `name_prefix` | `debate-dev-evidence` or `debate-prod-evidence`. Must contain the environment |
| `bucket_suffix` | Makes the bucket name globally unique. A committed constant, as the state and site buckets use, so the runbook, a removal and `debate-research store` can name the bucket without reading state |
| `noncurrent_version_retention_days` | 365 in prod, 30 in dev. How long the recovery path stays open for a bad publish |
| `noncurrent_version_transition_days` | 30, which is also S3's floor for a noncurrent transition to Standard-IA. When retention is not longer than this, the transition is **omitted** rather than written as a rule S3 would reject — which is what happens in dev |
| `additional_reader_principal_arns` | Empty in V1. The V2 worker and API roles add their ARNs here and get `s3:ListBucket`, `s3:GetObject`, `s3:GetObjectVersion`, `kms:Decrypt` and `kms:DescribeKey` in the bucket and key policies. Never write, never delete, never encrypt |
| `identity_center_instance_arn`, `identity_store_id` | Optional. Null creates neither permission set, which is what the tests and any reuse outside this account want |
| `evidence_operator_user_names` | Adult maintainers only, from the gitignored `owner.auto.tfvars` |
| `evidence_removal_user_names` | At most one person, enforced by a variable validation |

## The two permission sets

[`operator_access.tf`](operator_access.tf) defines them. Everyday work and takedowns are
deliberately separate credentials: a removal is irreversible — the noncurrent versions go too, so
there is nothing to restore from — while a sync happens every week, and the weekly profile is the
one that is left signed in.

| | `DebateDevEvidenceOperator` / `DebateProdEvidenceOperator` | `DebateDevEvidenceRemoval` / `DebateProdEvidenceRemoval` |
|---|---|---|
| SSO profile | `debate-dev-evidence`, `debate-prod-evidence` | `debate-dev-evidence-removal`, `debate-prod-evidence-removal` |
| Session | 8 hours | 1 hour |
| Who | Adult maintainers | One accountable person |
| S3 | `ListBucket` (scoped to the documented prefixes), `GetObject`, `GetObjectVersion`, `PutObject` | `ListBucketVersions`, `GetObjectVersion`, `DeleteObject`, `DeleteObjectVersion` under `raw/`, `parsed/`, `files/`, `manifests/`, `quarantine/`; `GetObject`/`PutObject` under `manifests/_suppression/` only |
| KMS | `Encrypt`, `Decrypt`, `GenerateDataKey` on this key | `Decrypt`, `GenerateDataKey` on this key |
| Cannot | Delete anything. Change a bucket policy, a lifecycle rule or a key policy | Delete under `reports/`. Delete the bucket. Change a bucket policy, a lifecycle rule or a key policy |

Two consequences worth knowing before they surprise someone:

* **`ListBucket` is scoped to prefixes, so listing the bucket root is denied.** `aws s3 ls
  s3://<bucket>/raw/` sends `prefix=raw/` and is allowed; `aws s3 ls s3://<bucket>` sends no
  prefix, and an absent condition key matches no `StringLike`. List a prefix.
* **`debate-dev` (`DebateMaintainer`) is not this credential.** It holds `PowerUserAccess` minus
  the prod denies, so in dev it *can* delete an object. The least-privilege claim belongs to the
  profiles above, and that is what the runbook's deny checks simulate.

## Tests

[`tests/evidence_bucket.tftest.hcl`](tests/evidence_bucket.tftest.hcl) runs with
`mock_provider "aws"`: no credentials, no network, no AWS account.

```bash
terraform -chdir=infrastructure/modules/evidence_bucket init -backend=false
terraform -chdir=infrastructure/modules/evidence_bucket test
```

`init` first — `terraform test` does not initialise for you, and
[`scripts/terraform_checks.sh`](../../../scripts/terraform_checks.sh) has usually done it already.

The bucket policy, the key policy and both inline policies are built with `jsonencode` rather than
`aws_iam_policy_document` data sources, because a data source's rendered JSON is opaque under a
mocked provider and those four policies are exactly what the tests need to read back.

No real caselist data and no student names appear in the fixtures (task spec: forbidden); the
bucket names, account id and user names in the tests are invented.

## Two things tflint cannot see from here

* The five standard tags reach every resource through the calling root's provider `default_tags`
  ([infrastructure/README.md](../../README.md)). `aws_resource_missing_tags` reads that block and
  cannot see it when it lints this directory alone, so the taggable resources carry a
  `# tflint-ignore` with that reason. Linting `envs/dev` or `envs/prod` follows the module call and
  does check the tags.
* `prevent_destroy` on the bucket and the key is a lifecycle meta-argument, so no test can assert
  it. It is there because `terraform destroy` in a root holding this module has no legitimate use.

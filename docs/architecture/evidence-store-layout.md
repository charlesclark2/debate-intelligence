# Evidence store layout

What the evidence buckets are called, how keys inside them are built, which prefix each task
writes, and what may never appear in a key. Spec:
[`v1-e29-t03-evidence-buckets`](../../plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml).
Decision: [ADR-0003](../adr/0003-s3-source-of-truth-for-raw-artifacts.md) (S3 is the system of
record). Region and account structure: [ADR-0010](../adr/0010-primary-aws-region.md). The
Terraform is [`infrastructure/modules/evidence_bucket`](../../infrastructure/modules/evidence_bucket/);
the operator steps are [docs/runbooks/evidence-store.md](../runbooks/evidence-store.md).

This is the contract every writer and reader of the store codes against. A task that needs a new
prefix changes this document and
[`local.evidence_prefixes`](../../infrastructure/modules/evidence_bucket/main.tf) in the same PR —
that list is what the operator's `ListBucket` grant is scoped to, so a prefix missing from it is a
prefix the CLI cannot see.

## The buckets

| | dev | prod |
|---|---|---|
| Bucket | `debate-dev-evidence-a7508de8` | `debate-prod-evidence-a7508de8` |
| KMS key alias | `alias/debate-dev-evidence` | `alias/debate-prod-evidence` |
| Superseded versions kept | 30 days | 365 days, in Standard-IA after 30 |
| Holds | Synthetic and sample data, plus whatever the backfill (`v1-e30-t06`) loads for validation | The real corpus |
| Everyday profile | `debate-dev-evidence` | `debate-prod-evidence` |
| Takedown profile | `debate-dev-evidence-removal` | `debate-prod-evidence-removal` |

`<name_prefix>-<bucket_suffix>`, where the suffix is a committed constant shared with the state
and site buckets. It is committed so that a runbook, a removal and `debate-research store` can
name the bucket without reading Terraform state.

Both buckets are private (all four block-public-access flags, ACLs disabled, no website hosting),
versioned, and encrypted with their own customer-managed KMS key. Nothing is ever served from
them directly: downloads are short-lived presigned URLs (ADR-0003), which arrive with the web app
in V2. The environment prefix in the bucket name and the key alias is load-bearing — it is what
`DebateMaintainer`'s deny on `debate-prod-*` and `alias/debate-prod-*` matches, and so how
ADR-0010 rule 4 keeps prod evidence out of reach of a dev-scoped credential in a single account.

## Content-addressed keys

Everything that is *content* — a disclosed file, a camp file, an uploaded document — is stored
under the sha256 of its bytes, in a two-level fan-out:

```
raw/caselist/hsld26/sha256/ab/cd/abcd1234…def0
                           ^^ ^^ first two byte pairs of the hex digest
```

The fan-out is not for S3's benefit (S3 has not needed key-prefix sharding for years) but for
everything that lists the store: a flat prefix with 60,000 members under it is slow to page
through and unreadable in a console.

Content addressing is what makes publishing idempotent and verification deterministic. The same
file disclosed by four teams is one object. A re-publish of bytes that are already there is a
no-op rather than a new version, so the version history means "this key changed", which for a
content-addressed key should never happen — and `v1-e29-t04-s3-blob-store` raises
`BlobIntegrityError` if it does.

**Keys carry no extension.** The original filename, its extension and its content type are
recorded in the manifest row and in the object's S3 metadata, never in the key. A key is the
digest and nothing else, so that two names for identical bytes cannot become two objects.

### What never appears in a key

No school name, no team code, no debater name, no original filename, in the key or in object
metadata. This is a rule of
[the caselist data-use policy](../policies/caselist-data-use.md), not a style preference: an S3
key is quoted in logs, in error messages, in CloudTrail and in this repository's documentation,
and a key that identifies a high-school team is a disclosure of its own. The mapping from a team
to the sources it disclosed lives in the manifests and in DynamoDB (V2), where it can be deleted
on request.

The one identifier that does appear is the caselist slug (`hsld26`, `ndtceda26`), which names a
public season-and-division archive rather than a person or a school.

## The prefixes

| Prefix | What is under it | Written by | Lifecycle |
|---|---|---|---|
| `raw/` | The bytes exactly as they were downloaded: disclosed caselist files and OpenEv camp files | `caselist publish` (E30 `t05`), scheduled sync (E34) | Kept. Removed only on request |
| `parsed/` | Extracted cards, paragraphs and offsets derived from a raw file by one parser version | The parse pipeline (E31 `t06`) | Kept; regenerable by re-parsing |
| `files/` | Built team files — the DOCX and its provenance sidecar (E33) | The file builder (E33) | Kept |
| `manifests/` | One JSONL row per source: sha256, size, content type, caselist, snapshot, provenance | The importers and `caselist publish` (E30 `t03`–`t05`) | Kept. The record of what the store holds |
| `reports/` | Run logs and derived reports: argument-landscape output, sync run summaries | Landscape analysis (E32), sync runs (E34), V2 tub index (`reports/tub/`) | Kept; regenerable |
| `uploads/` | Files a coach or a user put in themselves, after they have passed scanning | V2 debate tub (`v2-e35-t03`), V3 user uploads (`v3-e20-t02`) | Kept |
| `exports/` | Bulk zip downloads built for one download | V2 bulk export (`v2-e35-t03`, `v2-e17-t05`) | **Expires after 1 day**, versions included |
| `quarantine/` | Files held before they are trusted: fresh uploads awaiting scanning and validation, and material held pending a removal decision | V3 upload pipeline (`v3-e20-t02`), the operator | Kept until promoted to `uploads/` or deleted |

`exports/` is the only prefix whose *current* object versions a lifecycle rule ever deletes. An
export is a zip of objects that are still in the bucket; keeping them would mean paying to store
a second copy of the corpus in an ever-growing pile of archives. Everywhere else, a current
version is deleted by a removal request
([docs/runbooks/caselist-removal.md](../runbooks/caselist-removal.md)) or not at all.

### Example keys

```
raw/caselist/hsld26/sha256/ab/cd/abcd1234…def0          a disclosed file, by digest
raw/openev/2026/sha256/1f/9e/1f9e5678…c4a1              an OpenEv camp file
parsed/hsld26/v3/sha256/ab/cd/abcd1234…def0.jsonl       its cards, from parser version v3
files/hsld26/2026-09-15/aff-warming-core.docx           a built team file
files/hsld26/2026-09-15/aff-warming-core.provenance.json  what it cites
manifests/hsld26/2026-09-15.jsonl                       one snapshot's sources
manifests/openev/2026-ndi.jsonl                         one camp's files
manifests/_suppression/suppression-list.jsonl           sha256 values that must never be re-imported
manifests/_suppression/removal-log.jsonl                request id, date, reason code, environment
reports/hsld26/2026-09-15/argument-landscape.json       what the field is running
reports/sync/2026-09-15T06-00Z.json                     one scheduled sync run
uploads/wfb/sha256/7c/2b/7c2b90ab…33ef                  a coach's own file (V2)
exports/wfb/2026-09-15T18-04Z-selection.zip             a bulk download (gone within a day)
quarantine/wfb/01J9Z4K7QF3M2N                           an upload awaiting scanning (V3)
```

`manifests/_suppression/` is singled out in the IAM policies: it is the one place the takedown
credential may write, because a suppression list that is appended to has to be read first.

## Who may touch what

| | `EvidenceOperator` | `EvidenceRemoval` |
|---|---|---|
| List | Every prefix in the table above, one prefix at a time | `raw/`, `parsed/`, `files/`, `manifests/`, `quarantine/`, with versions |
| Read | Any object, any version | Versions under those five prefixes; current objects under `manifests/_suppression/` |
| Write | Any object | `manifests/_suppression/` only |
| Delete | **Nothing** | Objects and noncurrent versions under those five prefixes |

`reports/` is deliberately absent from the removal column. A report is derived and cites evidence
rather than holding it, so a takedown regenerates it rather than deleting it — and leaving
`reports/` out is what makes "this credential deletes disclosed material and nothing else" a
sentence IAM can enforce.

Listing is scoped to the prefixes above, which means listing the bucket *root* is denied: `aws s3
ls s3://<bucket>/raw/` works, `aws s3 ls s3://<bucket>` does not.

## Two earlier specs that name `raw/` differently

This document is the layout contract (`v1-e29-t03` ac4), and `v1-e29-t04-s3-blob-store` builds the
same `<prefix>/sha256/<ab>/<cd>/<sha256>` keys. Two documents written before it still describe the
older, flatter form and need reconciling by the PM rather than by a session:

* [`v1-e30-t05-caselist-publish`](../../plan_specs/v1/e30-caselist-ingestion/t05-caselist-publish.yaml)
  says `raw/<caselist>/<sha256>.<ext>` — no `caselist/` segment, no fan-out, and an extension.
* [docs/runbooks/caselist-removal.md](../runbooks/caselist-removal.md) step 6 lists versions under
  `raw/hsld26/<sha256>`.

Nothing has been written to either bucket yet, so this costs a spec edit and not a migration.

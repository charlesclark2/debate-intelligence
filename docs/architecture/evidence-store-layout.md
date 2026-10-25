<!-- docs-index: Evidence bucket naming, the `raw/`…`quarantine/` key layout, and which task writes each prefix -->
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
| `reports/` | Run logs and derived reports: argument-landscape output, sync run summaries, the student search pilot's index (`reports/tub/search/`) | Landscape analysis (E32), sync runs (E34), `tub index publish` (`v1-e39-t02`), V2 tub index (`reports/tub/`) | Kept; regenerable. Superseded index versions pruned by `v1-e39-t07`. A landscape bundle's school views (`schools.csv`, `schools.md`) are deleted with their sources by `caselist remove` and by the annual purge (`v1-e32-t13`) |
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
manifests/_run-state/run-state.tar.gz                   the run's manifests and database (v1-e40-t04)
reports/hsld26/2026-09-15/argument-landscape.json       what the field is running
reports/sync/2026-09-15T06-00Z.json                     one scheduled sync run
reports/sync/run-lock.json                              which runner may write to the bucket now
reports/sync/state/caselist-sync-download-starts.json   the run's download ledger, and its other state
reports/tub/search/3f9a0c1d2e4b5a69/search-index.sqlite.gz  one build of the search pilot's index
reports/tub/search/3f9a0c1d2e4b5a69/manifest.json       what that build is and was built from
reports/tub/search/current.json                         which build the pilot serves; written last
uploads/wfb/sha256/7c/2b/7c2b90ab…33ef                  a coach's own file (V2)
exports/wfb/2026-09-15T18-04Z-selection.zip             a bulk download (gone within a day)
quarantine/wfb/01J9Z4K7QF3M2N                           an upload awaiting scanning (V3)
```

`manifests/_suppression/` is singled out in the IAM policies: it is the one place the takedown
credential may write, because a suppression list that is appended to has to be read first.

### The weekly run's state: `reports/sync/run-lock.json`, `reports/sync/state/` and `manifests/_run-state/`

In bucket mode (`caselist.run_state = "bucket"`, `v1-e40-t04`,
[ADR-0020](../adr/0020-weekly-caselist-run-in-the-cloud.md) (3) and (4)) the evidence bucket of the
run's home environment is the record of the weekly run's state, and a data directory is a working
copy restored from it. Three keys or prefixes hold it.

| Key or prefix | What is under it | Personal data | Written by | Deleted |
|---|---|---|---|---|
| `reports/sync/run-lock.json` | The run lock: which runner holds a lease to write to this bucket, until when, and whom it took over from | None: run ids, commands, times | `caselist seed-run-state` creates it; every bucket-writing command in bucket mode takes, renews and releases it, by S3 conditional writes only | Never. Released by writing `state: free`; its history is its versions |
| `reports/sync/state/` | The run log and its details, the download ledger, the OpenEv deliveries and the pending-work file, by their names in the data directory | None | A bucket-mode run, each as it is written (the ledger before each download); the seed | Never. A file the run removed is saved as an empty object |
| `manifests/_run-state/` | The run-state bundle, `run-state.tar.gz`: the data directory's manifests and a compacted copy of its SQLite database | **Yes**: the manifests' paths and the database's school and team codes | A bucket-mode run, only when every snapshot it records is confirmed in the bucket and none is withheld; the seed; a removal's rewrite | Only by `caselist remove`, under `EvidenceRemoval`, which purges its noncurrent versions after its rewrite is confirmed |

`store sync` skips `manifests/_run-state/` either way and on either side, as it skips
`manifests/_suppression/` and `parsed/`: the bundle's rules are its writers', and a copy would keep
none of them. A run never creates the lock: a bucket with no lock object has no run state, and a
bucket-mode command refuses it before it restores or writes anything. Neither credential needs a
grant it did not already hold: the everyday policy reads and writes every key above, and a
conditional write needs `s3:PutObject` alone; the removal credential's listing and deleting of
versions under `manifests/` already reach `manifests/_run-state/`, and it writes the bundle and the
lock through the everyday profile, as it writes rewritten manifests.

### `reports/tub/search/`: the student search pilot's index

`debate-research tub index publish` (`v1-e39-t02`, [ADR-0019](../adr/0019-student-search-pilot-stack-sign-in-and-hosting.md)
(c)) writes one directory per build, named by its index id, the first 16 hex characters of the
SQLite file's sha256: the SQLite file gzipped, and its manifest. Then, last, it writes `current.json`,
which names that build's object and manifest by key and sha256. The pilot's function reads
`current.json` and follows it, so a publish stopped part-way leaves the previous build current and
whole. The SQLite file and the manifest are described in
[docs/data/search-index.md](../data/search-index.md).

Unlike the rest of `reports/`, the index holds card text, and in stored provenance columns, never
searchable, the school, team code, side, tournament and round of each disclosure it keeps
(data-use policy, "Where personal data is allowed to live"). Its key holds none of them: an index id
is a digest. It is written by the everyday `EvidenceOperator` profile and read by the pilot's
function. The operator's listing grant names `reports/tub/search/` beside the documented prefixes, so
the listing that `v1-e39-t07`'s pruning depends on survives a narrower `reports/` grant.

After a removal the index is rebuilt and published, and every superseded build is deleted,
noncurrent versions included ([removal runbook](../runbooks/caselist-removal.md), the pilot's
steps). So `reports/tub/search/` is the one prefix under `reports/` where the `EvidenceRemoval`
credential may list versions and delete objects and their versions (`v1-e39-t07`, the PM's amendment
of 2026-10-19). Nothing else under `reports/` gains a delete, and the everyday credential's grant is
unchanged. `infrastructure/modules/evidence_bucket/operator_access.tf` keeps the prefix in a local of
its own, `removable_index_prefix`, apart from the five prefixes of disclosed material.

## Who may touch what

| | `EvidenceOperator` | `EvidenceRemoval` |
|---|---|---|
| List | Every prefix in the table above, one prefix at a time, and `reports/tub/search/` by name | `raw/`, `parsed/`, `files/`, `manifests/`, `quarantine/`, and `reports/tub/search/`, with versions |
| Read | Any object, any version | Versions under those six prefixes; current objects under `manifests/_suppression/` |
| Write | Any object | `manifests/_suppression/` only |
| Delete | **Nothing** | Objects and noncurrent versions under those six prefixes |

The rest of `reports/` is deliberately absent from the removal column. A report is derived and
cites evidence rather than holding it, so a takedown regenerates it rather than deleting it — and
leaving it out is what makes "this credential deletes disclosed material and nothing else" a
sentence IAM can enforce. The pilot's index is the exception because it holds card text: it is
disclosed material in another form, and a superseded build of it is deleted like any other copy.

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

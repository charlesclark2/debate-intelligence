# ADR-0003: S3 as the source of truth for raw source snapshots and files

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
  - [§8 Evidence Integrity and Provenance](../architecture/architecture_proposal.md#8-evidence-integrity-and-provenance)

## Context

Evidence integrity ([ADR-0006](0006-exact-source-evidence-verification.md)) requires that
every card be reproducible from a stored snapshot of the source. That snapshot may be raw
HTML, a downloaded PDF, an uploaded DOCX/PDF debate file, or extracted plain text — the
sizes range from kilobytes to hundreds of megabytes. Storing these in DynamoDB is expensive
and hits item-size limits; storing them on a Fargate task's local disk loses them when the
task dies.

We also need to keep versioned copies (extractor version, retrieval date), be able to hash
them for verification, and expose them to downloaders via short-lived signed URLs rather
than a public bucket.

## Decision

Raw source snapshots, uploaded files, generated DOCX exports, and JSON manifests are stored
in versioned S3 buckets with server-side encryption (SSE-KMS). DynamoDB records store the
S3 key and metadata (`snapshot_id`, `sha256`, `extractor_version`, `retrieved_at`), never
the blob itself.

The `SourceSnapshotRepository` and `FileStore` interfaces live in `debate_core`. The
production implementation uses S3; the V1 local implementation uses a filesystem tree with
the same content-addressed structure. Downloads always go through short-lived pre-signed
URLs; buckets are never made public.

## Consequences

- Blob storage cost scales cheaply and independently from operational metadata.
- Re-running verification against a stored snapshot is deterministic.
- All infrastructure that reads/writes blobs must go through the repository interface —
  no direct `boto3.client("s3")` from application code.
- Bucket lifecycle rules (transient retrieval artifacts, retention for verified evidence)
  must be defined in Terraform, not assumed.

## Alternatives considered

- **Store raw HTML/text inside DynamoDB items.** Simple and transactional with metadata,
  but item-size limits (400 KB) rule out full debate files and long articles, and DynamoDB
  storage is much more expensive per GB than S3.
- **Elastic File System / EBS shared volume.** Costs more, harder to encrypt with
  per-object keys, and does not naturally give us signed-URL delivery.
- **Skip snapshots and re-fetch on demand.** Would violate [ADR-0006](0006-exact-source-evidence-verification.md):
  the source might change or disappear between retrieval and verification.

## References

- [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
- [§8 Evidence Integrity and Provenance](../architecture/architecture_proposal.md#8-evidence-integrity-and-provenance)
- [ADR-0002: DynamoDB operational store](0002-dynamodb-operational-store.md)
- [ADR-0006: Exact-source evidence verification](0006-exact-source-evidence-verification.md)

# ADR-0002: DynamoDB as the operational system of record

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)

## Context

Operational entities in this system — users, searches, cards, files, jobs, argument nodes,
round state, opponent metadata — are almost always accessed by known keys or short GSI
lookups: "cards owned by user X", "jobs for search Y", "rounds in state Z". The workloads
are read-heavy per user but bursty during a tournament weekend. There is no reporting
warehouse in the roadmap, so we do not need a query engine that can do arbitrary joins;
we need predictable single-digit-millisecond reads/writes with low idle cost.

Running a relational database (RDS PostgreSQL, Aurora Serverless) means paying for capacity
during long idle periods, taking on schema-migration operations for every model change, and
managing connections from container workers and Lambdas. Snowflake/Redshift are explicitly
out of scope in the proposal.

## Decision

DynamoDB is the system of record for operational entities and their relationships. Access
patterns drive the physical design; the initial split is:

- **AppTable** — users, searches, cards, jobs, files, rounds, user-owned resources.
- **ArgumentTable** — argument nodes and adjacency edges (see [ADR-0008](0008-no-neptune-initially.md)).
- **OpponentTable** — team/debater identities, disclosure records, tournament results.

Repository interfaces live in `debate_core`; the DynamoDB implementation lives in an
infrastructure module. V1 may use an in-memory or filesystem implementation of the same
interfaces so the CLI runs without cloud credentials. Optimistic concurrency (revision
fields) protects cards and parsed files from model reprocessing silently overwriting
student edits.

## Consequences

- Access patterns must be enumerated before physical keys are chosen for each table; adding
  a new pattern later may require a GSI or a data migration.
- No ad-hoc SQL: reporting/analytics are done from S3 exports (see [ADR-0003](0003-s3-source-of-truth-for-raw-artifacts.md))
  and OpenSearch (see [ADR-0004](0004-opensearch-is-derived-not-authoritative.md)).
- Local development is cheap (DynamoDB Local or the in-memory repository).
- Point-in-time recovery, backups, and IaC-managed tables must be in place before real user
  data lands.

## Alternatives considered

- **Aurora Serverless v2 (PostgreSQL).** Rich query language and familiar migrations, but
  higher baseline cost and connection-management overhead for Fargate workers. Not needed
  because the access patterns are key-based.
- **Single-table DynamoDB across everything.** Considered and rejected as the initial cut:
  argument graph adjacency and user-owned data have very different key shapes, and mixing
  them makes access-pattern documentation harder to reason about. Revisit only if
  cross-domain queries become common.
- **MongoDB / DocumentDB.** Flexible documents but weaker durability/serverless-cost story
  than DynamoDB inside AWS, and no benefit that the domain models actually need.

## References

- [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
- [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
- [ADR-0003: S3 source-of-truth for raw artifacts](0003-s3-source-of-truth-for-raw-artifacts.md)
- [ADR-0004: OpenSearch is derived, not authoritative](0004-opensearch-is-derived-not-authoritative.md)
- [ADR-0008: No Neptune initially](0008-no-neptune-initially.md)

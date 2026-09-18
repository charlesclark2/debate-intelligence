# ADR-0004: OpenSearch is a derived index, not an authoritative store

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
  - [§9 Search and Retrieval Architecture](../architecture/architecture_proposal.md#9-search-and-retrieval-architecture)

## Context

The retrieval pipeline needs both BM25/lexical search and vector similarity across articles,
cards, files, and argument nodes. OpenSearch Serverless is the AWS-native option that
offers both. A common failure mode in similar systems is to gradually treat the search
index as the primary store — writing to it directly, editing documents in it, and losing
data when the index has to be rebuilt or migrated.

Search index formats also change: embedding models rotate ([§10](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy))
and OpenSearch mappings evolve. Any rebuild has to be safe.

## Decision

DynamoDB ([ADR-0002](0002-dynamodb-operational-store.md)) and S3 ([ADR-0003](0003-s3-source-of-truth-for-raw-artifacts.md))
are the systems of record. OpenSearch is populated from them via indexer workers and is
always rebuildable. The application never writes user-visible truth directly to OpenSearch:
edits go through the domain repositories, which emit indexing events.

The `SearchIndex` interface in `debate_core` exposes read operations (lexical, vector,
hybrid) and background reindex triggers. The concrete implementation may be OpenSearch
Serverless, or a local Whoosh/lunr-style implementation for V1, or a null implementation
that returns empty results for CLI-only workflows.

## Consequences

- We can rebuild the entire index from DynamoDB + S3 without asking users to re-upload.
- Embedding-model or mapping changes are handled by dual-writing to a new index and
  atomically swapping, with no risk to the operational data.
- Extra write path: repositories must emit events (SQS/EventBridge) that indexer workers
  consume. This is not free but is straightforward with the async job architecture
  ([ADR-0009](0009-async-job-architecture.md)).
- Consistency is eventual: a card created a moment ago may not yet appear in search
  results. UI copy needs to acknowledge that.

## Alternatives considered

- **Use OpenSearch as primary store for cards/articles.** Simpler write path but takes on
  serious durability risk during any index migration, and OpenSearch is a poor OLTP store.
- **Store embeddings and lexical text inside DynamoDB with in-memory search.** Fine for a
  single-user CLI but does not scale to V2 where thousands of cards and files are searched.
- **PostgreSQL with `pg_trgm` + `pgvector`.** Would work at V2 scale but conflicts with
  [ADR-0002](0002-dynamodb-operational-store.md); we would be introducing a whole new
  operational database just for search.

## References

- [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
- [§9 Search and Retrieval Architecture](../architecture/architecture_proposal.md#9-search-and-retrieval-architecture)
- [ADR-0002: DynamoDB operational store](0002-dynamodb-operational-store.md)
- [ADR-0003: S3 source-of-truth](0003-s3-source-of-truth-for-raw-artifacts.md)
- [ADR-0009: Async job architecture](0009-async-job-architecture.md)

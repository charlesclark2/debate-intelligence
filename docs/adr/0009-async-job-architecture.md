# ADR-0009: Async job architecture for slow work in V2 and beyond

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§12 V2 Detailed Architecture](../architecture/architecture_proposal.md#12-v2-detailed-architecture)
  - [§15 Reliability, Observability, and Cost Controls](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls)

## Context

Most user-visible actions in V2 kick off work that takes seconds to minutes: federated
search fan-out, article retrieval and extraction, DOCX/PDF parsing, embedding generation,
DOCX export, LLM extraction over long files, round-simulation turns. Handling any of those
synchronously inside a browser request would either time out at API Gateway (30-second
hard limit), tie up FastAPI worker slots during retries, or produce a poor UX with
apparent hangs.

Retries also need to be idempotent and safe: an article-extraction retry should not
double-charge Bedrock, and a card export retry should not create duplicate S3 objects.

## Decision

Slow work is modeled as **jobs** in V2. Job orchestration uses AWS Step Functions for
durable multi-step flows (retrieval → normalization → verification → indexing) and Amazon
SQS as the queue between the API and workers running on ECS Fargate. Every job has a
`job_id`, correlation ID, status, and typed input/output records persisted in DynamoDB.
Clients poll or subscribe (websocket/SSE) for updates instead of holding an open request.

`debate_core` defines the job schemas (`SearchJob`, `CardJob`, `FileParseJob`,
`ExportJob`, `RoundTurnJob`, …) and the `JobRepository` interface. Domain code enqueues
jobs through a `JobDispatcher` port; the concrete implementations are SQS+Step Functions
in cloud and in-process for local V1 development.

Job handlers are idempotent where possible: they check `job_id`/content hash before
retrying model calls or writing to S3, and they use optimistic concurrency on DynamoDB
records they update.

## Consequences

- User-facing endpoints stay fast even when the backing work is slow.
- Failures are inspectable in Step Functions state history rather than lost in a request
  timeout.
- The V1 CLI can call the same application services synchronously by using an in-process
  `JobDispatcher`; the same code paths become async in V2 without rewrites.
- Observability requires correlation IDs across API, Step Functions, workers, Bedrock,
  and source retrieval, and cost telemetry per job class ([§15](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls)).
- Every new slow operation has to define a job schema and a handler, not just a new
  request handler — a small tax on new features, with the benefit that they inherit
  retries, telemetry, and status UI for free.

## Alternatives considered

- **Long-lived synchronous requests with API Gateway websocket only.** Doesn't survive
  worker restarts, offers no retry semantics, and mixes UI transport concerns with domain
  logic.
- **AWS Lambda for every job.** Runs into 15-minute limits for large file parses and
  argument-graph extraction; Fargate containers avoid those limits and can hold model
  clients warm across jobs.
- **Celery / RQ on self-managed brokers.** Extra operational burden for no benefit over
  SQS + Step Functions inside AWS.

## References

- [§12 V2 Detailed Architecture](../architecture/architecture_proposal.md#12-v2-detailed-architecture)
- [§15 Reliability, Observability, and Cost Controls](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls)
- [ADR-0001: Python domain core](0001-python-domain-core.md)
- [ADR-0004: OpenSearch is derived](0004-opensearch-is-derived-not-authoritative.md) — indexer jobs are the write path.

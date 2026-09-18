# ADR-0008: No Amazon Neptune until DynamoDB adjacency proves insufficient

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
  - [§13 V3 Detailed Architecture](../architecture/architecture_proposal.md#13-v3-detailed-architecture)

## Context

The argument graph ([ADR-0007](0007-argument-graph-before-simulator.md)) is naturally a
graph and could be persisted in a graph database like Amazon Neptune. Adopting Neptune
would add a managed service with non-trivial baseline cost (an always-on cluster), a
second query language (Gremlin or SPARQL), IAM/VPC configuration, and a new operational
skillset — before we know whether any of the V3 queries actually require it.

Most of the graph traversals V3 needs are one- to three-hop lookups: "given this
argument node, find edges of type ANSWERS/TURNS whose targets have supporting evidence
older than N", or "find nodes with no supporting edge". Those are within reach of
DynamoDB adjacency-list patterns.

## Decision

V1 and V2 do not introduce Neptune. The argument graph is persisted in DynamoDB's
`ArgumentTable` with an adjacency-list layout: `PK=GRAPH#<file-or-case-id>`,
`SK=NODE#<node-id>` for nodes and `SK=EDGE#<from>#<relationship>#<to>` for edges, with
GSIs supporting node-type and claim lookups.

A `GraphRepository` interface in `debate_core` hides the storage detail. If a specific V3
traversal cannot be expressed efficiently against DynamoDB adjacency (multi-hop
pattern-matching, cycle detection over large graphs, all-shortest-paths, etc.), a Neptune
implementation of the same interface can be introduced without touching the application
layer.

Adopting Neptune later requires a superseding ADR that names the traversal that motivated
the change, shows the cost estimate, and describes the migration path from DynamoDB.

## Consequences

- One fewer AWS service to operate, secure, and pay for in V1/V2.
- Complex traversals will feel awkward in DynamoDB and may push us to precompute
  materialized views. That is preferable to pre-adopting a graph database we do not yet
  need.
- The interface discipline is important: application code must not depend on DynamoDB
  query shapes, or a future switch will not be transparent.
- Graph tooling (visualizations, debug queries) has to work against the repository, not
  against a graph-query console.

## Alternatives considered

- **Adopt Neptune from the start.** Rejected: baseline cost, second query language, and
  no evidence the workload needs it. Easy to add later if it does.
- **Use PostgreSQL with recursive CTEs.** Would work for adjacency but conflicts with
  [ADR-0002](0002-dynamodb-operational-store.md); introducing a second operational
  database just for graphs is a bigger change than moving to Neptune when the time comes.
- **Store graph data in OpenSearch as parent/child docs.** Would violate [ADR-0004](0004-opensearch-is-derived-not-authoritative.md)
  (search is derived, not authoritative) and does not model relationships cleanly.

## References

- [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture) — the "Future graph database" note.
- [§13 V3 Detailed Architecture](../architecture/architecture_proposal.md#13-v3-detailed-architecture)
- [ADR-0002: DynamoDB operational store](0002-dynamodb-operational-store.md)
- [ADR-0007: Argument graph before simulator](0007-argument-graph-before-simulator.md)

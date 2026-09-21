# ADR-0007: Build the argument graph before the round simulator

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
  - [§13 V3 Detailed Architecture](../architecture/architecture_proposal.md#13-v3-detailed-architecture)

## Context

V3 promises four capabilities that look distinct on the surface: predicting opponent
positions, auditing debate files for coverage, cross-examination generation, and full round
simulation. Each of them fails the same way if it is built on top of raw text and vector
similarity alone — the system cannot say *why* an argument answers, turns, or mitigates
another one, so it produces vague suggestions instead of debate-grade analysis.

An argument graph — typed nodes (plan, advantage, uniqueness, link, impact, counterplan,
kritik, evidence card) and typed edges (SUPPORTS, ANSWERS, TURNS, MITIGATES, CONTRADICTS,
PREREQUISITE, LINKS_TO, SOLVES, IMPACTS, PERMUTES) — is the shared substrate that gives
those features something to reason over.

## Decision

The V3 sequence is: parse debate files into typed argument nodes, extract edges with
explicit source references and confidence, then build coverage analysis, file audits, CX,
and round simulation on top of that graph. The simulator does not ship before the graph is
in place; it is a state machine that operates over graph nodes, not a chat-only feature.

`ArgumentNode` and `ArgumentEdge` are first-class domain entities (see [§7](../architecture/architecture_proposal.md#7-data-architecture)),
persisted via a `GraphRepository` interface in `debate_core`. LLM extraction of nodes and
edges follows the same "structured outputs + evaluations" discipline as evidence
extraction — the model returns typed proposals, the domain layer validates and stores
them.

## Consequences

- Every downstream V3 feature has the same evaluation surface: node-type accuracy, edge
  accuracy, source-reference accuracy. Fixes to extraction improve everything at once.
- Predictions are auditable: a "predicted opponent argument" is a graph node with source
  edges to disclosures and cases, not an unexplained model utterance.
- The initial V3 releases spend time on graph tooling before any simulator UI exists.
  That is a schedule cost worth taking because a stateless chat simulator would need to
  be rewritten as soon as coverage analysis lands.
- Graph storage is currently DynamoDB adjacency (see [ADR-0008](0008-no-neptune-initially.md));
  a dedicated graph database is deferred until evidence shows it is needed.

## Alternatives considered

- **Ship a stateless chat-based simulator first, then retrofit structure.** Faster demo
  but does not learn from coverage/audit work, and the state-tracking rewrite would be
  large. Rejected because it would teach students the wrong flow of debate too.
- **Skip the graph and use vector similarity for coverage.** Similarity can only say
  "these look alike", not "this answers that with this warrant". Coverage decisions would
  be indistinguishable from keyword search.
- **Model debate rounds as unstructured events with post-hoc analysis.** Loses the
  concessions/drops precision the "experienced flow" judge setting needs.

## References

- [§13 V3 Detailed Architecture](../architecture/architecture_proposal.md#13-v3-detailed-architecture)
- [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
- [ADR-0008: No Neptune initially](0008-no-neptune-initially.md)
- [ADR-0002: DynamoDB operational store](0002-dynamodb-operational-store.md)

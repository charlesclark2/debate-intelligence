# ADR-0001: Python domain core shared by every delivery surface

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§2 Goals and Architectural Principles](../architecture/architecture_proposal.md#2-goals-and-architectural-principles)
  - [§4 Technology Stack](../architecture/architecture_proposal.md#4-technology-stack)
  - [§6 Repository and Service Boundaries](../architecture/architecture_proposal.md#6-repository-and-service-boundaries)
  - [§17 Deployment and Evolution Plan](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan)

## Context

The platform ships a CLI in V1, an authenticated web application in V2, and argument
intelligence plus round simulation agents in V3. All three generations do the same kinds of
work: retrieve articles, cut cards, verify evidence, extract arguments, and run round state.
A CLI-first implementation could easily grow business logic inside its command handlers,
which would either be duplicated in the V2 web API and V3 workers or force a rewrite when
those surfaces are added.

Retrieval, document parsing, LLM orchestration, and Pydantic-based schema validation are
also all strongest in Python; the debate-adjacent tooling the team already relies on (uv,
Typer, Rich, trafilatura, docx renderers) is Python. A polyglot core would fragment the
domain model and duplicate contracts.

## Decision

`packages/debate_core/` is the single home for domain entities, use cases, retrieval and
evidence services, argument graph logic, and provider interfaces. It is written in Python
3.12+ and depends only on the standard library, Pydantic, and other pure-Python domain
packages — it must not import AWS SDKs, HTTP clients, web frameworks, or CLI frameworks.

`debate_cli`, `debate_api`, and `debate_workers` are thin adapters: they parse arguments or
requests, translate to the application layer, and render results. Any logic beyond
translation belongs in `debate_core`. Import boundaries are enforced by `import-linter` in
CI (see [t03 uv workspace tooling](../../plan_specs/v1/e01-repo-foundation/t03-uv-workspace-tooling.yaml)).

## Consequences

- New surfaces (a REST route, a worker, a V3 agent) are cheap because they wire into
  existing services instead of re-implementing them.
- Contracts between layers are validated Pydantic types, which makes provider swaps and
  schema evolution reviewable.
- The rule adds friction the first time a delivery-surface engineer needs to change domain
  behavior: the change lands in `debate_core` with tests, then the surface calls it.
- The core cannot know about request contexts (Typer options, FastAPI dependencies); those
  have to be passed in as plain values or protocol objects.

## Alternatives considered

- **CLI-first implementation with logic in `debate_cli`.** Fastest for V1, but every later
  surface would either duplicate the logic or reach into CLI internals. Ruled out because
  the whole point of the architecture is that V1 is the first client of a permanent
  platform, not the platform itself.
- **TypeScript/Node core to match the web frontend.** Loses the Python ecosystem for
  retrieval, document parsing, and Bedrock/embeddings tooling. Would require rebuilding
  trafilatura-class extraction and DOCX rendering.
- **Split by capability into independently versioned repos** (retrieval-service,
  evidence-service, …). Premature: the team is one person plus AI assistance, and cross-repo
  refactors would be far more expensive than in a monorepo. Revisit only if team size and
  release cadence make in-repo coupling painful.

## References

- [§4 Technology Stack](../architecture/architecture_proposal.md#4-technology-stack)
- [§6 Repository and Service Boundaries](../architecture/architecture_proposal.md#6-repository-and-service-boundaries)
- [§17 Deployment and Evolution Plan](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan)
- [ADR-005: Bedrock behind ModelRouter](0005-bedrock-behind-model-router.md) — a concrete instance of the boundary rule.

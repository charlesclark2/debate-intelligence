# ADR-0005: Amazon Bedrock accessed through a ModelRouter abstraction

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§10 LLM and Retrieval Model Strategy](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy)

## Context

The platform uses LLMs for card tagging, argument extraction, coverage analysis, judge
reasoning, and other tasks; embeddings for retrieval; and a reranker before returning
search results. Model catalogs change every few months: new Anthropic model versions land
on Bedrock, embedding models get replaced, and reranker choices come and go. Hard-coding
model IDs (or worse, provider SDK calls) across the codebase would guarantee wide-blast
changes on every model upgrade.

AWS-native access is preferred for credential governance, per-call telemetry, and regional
inference profiles. But operators need to be able to switch providers or point at a local
mock without touching business logic — the CLI in V1 runs offline for tests, and the
evaluation harness needs deterministic replay.

## Decision

All model calls go through a `ModelRouter` interface defined in `debate_core`. Callers
request a *task class* (for example `card_tagging`, `argument_extraction`, `embed_chunk`,
`rerank`) and pass structured inputs; the router chooses the concrete provider, model ID,
inference profile, and prompt version based on configuration.

The default production implementation targets Amazon Bedrock (Anthropic Claude, Titan
embeddings, Cohere Rerank per [§10](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy)).
A fake/replay implementation used by tests reads recorded fixtures. Every call records
`model_id`, `prompt_id` and version, temperature, and retrieval context IDs against the
generated artifact so upgrades are auditable.

## Consequences

- Model upgrades are a config change plus a golden-file evaluation, not a code change.
- Tests never hit the live network; recorded fixtures and the fake router satisfy the
  offline-CI rule in [working agreements §1](../process/working-agreements.md#1-ci-stays-light).
- The router is a real abstraction that has to be maintained: adding a new task class means
  adding a schema, a prompt version, and evaluation coverage.
- Bedrock-specific features (session tokens for streaming, tool-use variants) may need to
  be exposed through the router carefully so callers do not depend on provider details.

## Alternatives considered

- **Call `boto3` Bedrock APIs directly from application code.** Fastest path today, but
  every model upgrade touches many files and there is no easy hook to record/replay for
  tests.
- **A third-party abstraction library (LangChain / LiteLLM).** Adds a dependency with its
  own release cadence and opinions about prompt templating; harder to keep the strict
  Pydantic-in/Pydantic-out contract the platform requires.
- **One provider per environment (Bedrock in prod, OpenAI in dev).** Would create prod-only
  behavior differences and complicate evaluations. If a second provider becomes necessary
  it should be added under the same router.

## References

- [§10 LLM and Retrieval Model Strategy](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy)
- [ADR-0001: Python domain core](0001-python-domain-core.md)
- [ADR-0006: Exact-source evidence verification](0006-exact-source-evidence-verification.md) — router callers never receive freeform evidence text.

# Architecture Decision Records

Each ADR captures one architectural decision as a standalone record: its status, the
context that forced the choice, the decision itself, the consequences, the alternatives
considered, and the references that back it up. ADR-0001 through ADR-0009 make the
`§18` decision table in [docs/architecture/architecture_proposal.md](../architecture/architecture_proposal.md#18-key-architecture-decisions-adrs)
individually reviewable; every ADR links back to the proposal sections that motivate it.
ADR-0013 records a later decision (two environments) that supersedes part of the proposal.

New records use the template in [0000-template.md](0000-template.md).

## Index

| ADR | Title | Status | Topic |
|---|---|---|---|
| [0001](0001-python-domain-core.md) | Python domain core shared by every delivery surface | Accepted 2026-09-17 | Language and layering rules for `packages/debate_core` and the thin CLI/API/worker surfaces. |
| [0002](0002-dynamodb-operational-store.md) | DynamoDB as the operational system of record | Accepted 2026-09-17 | Primary store for users, cards, jobs, files, arguments, rounds. |
| [0003](0003-s3-source-of-truth-for-raw-artifacts.md) | S3 as the source of truth for raw source snapshots and files | Accepted 2026-09-17 | Blob storage for versioned source snapshots, uploads, exports. |
| [0004](0004-opensearch-is-derived-not-authoritative.md) | OpenSearch is a derived index, not an authoritative store | Accepted 2026-09-17 | Rebuildable lexical/vector index over DynamoDB + S3. |
| [0005](0005-bedrock-behind-model-router.md) | Amazon Bedrock accessed through a ModelRouter abstraction | Accepted 2026-09-17 | Provider/model portability, replay for tests, prompt versioning. |
| [0006](0006-exact-source-evidence-verification.md) | Exact-source evidence verification — LLMs select spans, they do not author evidence | Accepted 2026-09-17 | The evidence-integrity rule the platform is built around. |
| [0007](0007-argument-graph-before-simulator.md) | Build the argument graph before the round simulator | Accepted 2026-09-17 | V3 sequencing: typed nodes and edges precede coverage, audit, CX, and simulation. |
| [0008](0008-no-neptune-initially.md) | No Amazon Neptune until DynamoDB adjacency proves insufficient | Accepted 2026-09-17 | Graph storage strategy for V1/V2. |
| [0009](0009-async-job-architecture.md) | Async job architecture for slow work in V2 and beyond | Accepted 2026-09-17 | Step Functions + SQS + Fargate for slow, retryable work. |
| [0013](0013-two-environments-and-dev-main-promotion.md) | Two environments (dev, prod) and dev→main promotion | Accepted 2026-09-17 | Supersedes the `stage` environment in proposal [§4](../architecture/architecture_proposal.md#4-technology-stack) and [§5](../architecture/architecture_proposal.md#5-aws-cloud-architecture); operational detail in [docs/process/branching-and-environments.md](../process/branching-and-environments.md). |

## Reserved numbers

Some numbers are already referenced by task specs but the ADR files themselves have not
been written yet. Keep the numbers reserved for these topics; write the record when the
decision lands.

| ADR | Topic | Owning spec |
|---|---|---|
| 0010 | Primary AWS region | [`v1-e29-t01-aws-account-baseline`](../../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml) |
| 0011 | VPC egress design | [`v2-e10-t05-container-platform`](../../plan_specs/v2/e10-aws-foundation/t05-container-platform.yaml) |
| 0012 | Web hosting | [`v2-e14-t03-app-hosting`](../../plan_specs/v2/e14-web-cut-card/t03-app-hosting.yaml) |
| 0014 | Debate file editor and format reference (CardMirror evaluation) | [`v1-e31-t01-cardmirror-evaluation`](../../plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml) |

New ADRs take the next free number after the highest written or reserved one: **0015** is the
next free number. Do not skip numbers; if a reservation is dropped, note it here rather than silently
reusing the number.

## Proposing a new ADR (ADR-0015+)

1. **Confirm this needs an ADR.** ADRs record decisions that shape the architecture and
   would be expensive to reverse. Configuration choices, feature toggles, and everyday
   code reviews do not need ADRs.
2. **Claim the next number.** Look at the largest existing filename in `docs/adr/` and add
   the next number after any reserved slot above. Add a row to the *Index* or *Reserved
   numbers* table in this README in the same PR.
3. **Copy [0000-template.md](0000-template.md)** to `docs/adr/NNNN-short-descriptive-title.md`.
   Use kebab-case slugs; keep the title short but say what the decision is
   (`0015-signed-url-download-strategy.md`, not `0015-download.md`).
4. **Write in the standard sections.** Status, Context, Decision, Consequences,
   Alternatives considered, References. Reference at least one section anchor in
   [docs/architecture/architecture_proposal.md](../architecture/architecture_proposal.md);
   if the decision is not covered by the proposal yet, extend the proposal in the same PR.
5. **Open the ADR PR into `dev`.** Set the initial `Status:` to `Proposed`. Reviewers
   push back or ask questions on the PR itself; when the decision is agreed, change
   `Status:` to `Accepted` and merge.
6. **Update the index** in this README whenever an ADR changes status.

## Superseding an ADR

An accepted ADR is never edited to change the decision. To change a decision:

1. Open a new ADR with the next free number that describes the new decision and, in its
   References section, links back to the ADRs it replaces.
2. In each superseded ADR, change `Status:` to `Superseded by ADR-NNNN` with a real link
   to the replacement file, and leave the rest of the file intact so the historical
   rationale is preserved.
3. Update the index above so both rows reflect the new statuses.

A deprecation without a replacement is `Status: Deprecated` on the original ADR, with a
short note in Consequences explaining why the decision no longer applies.

## Numbering rules

- Numbers are four digits, zero-padded (`0001`, `0014`, `0100`).
- Numbers are permanent and never reused. If an ADR is withdrawn before it is accepted,
  keep its file with `Status: Withdrawn` and a one-line explanation.
- The template file is `0000-template.md`; never write an actual decision as `0000`.

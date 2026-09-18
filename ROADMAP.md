# Roadmap — Debate Research & Argument Intelligence Platform

This roadmap is generated from the PlanSpecs in [`plan_specs/`](plan_specs/README.md), which are
the source of truth. The tables below are refreshed by the PM with `uv run scripts/spec_index.py`
in a `specs/roadmap-refresh` PR, not by individual tasks (so parallel task PRs don't conflict),
so the Status column can lag a few merges behind. For live status run
`uv run scripts/validate_specs.py --status`. Everything outside the GENERATED markers is hand-written.

## How releases work

* **Major versions** follow the [architecture proposal](docs/architecture/architecture_proposal.md):
  **V1** CLI evidence-research MVP → **V2** authenticated AWS research workspace →
  **V3** argument intelligence and round simulation.
* **Minor releases** (v1.0, v1.1, …) are the incremental drops. Each one ships something a
  student or coach can use, closes with a git tag, and passes a review Gate
  (`plan_specs/releases/<version>.yaml`).
* **Epics** (E01–E28) each belong to exactly one minor release, so they never cross a major
  version. Tasks inside an epic may depend on work from the same or earlier releases only.

## Branches and environments

`main` is production and `dev` is the development environment. Task branches merge into `dev`;
`dev` is deployed (V1: pre-release CLI build, V2+: dev AWS environment) and must pass
`validate-dev` plus Charlie's approval before a `dev` → `main` promotion ships it to prod.
Only two environments exist (ADR-0013). See
[docs/process/branching-and-environments.md](docs/process/branching-and-environments.md).
The mechanics are tasks v1-e01-t08 (promotion guards), t09 (dev pre-release channel),
t10 (`validate-dev` gate) and v2-e12-t07 (cloud dev→prod pipeline).

## Suggested timeline

Projected from the specs' own effort estimates (~1,630 engineering hours in total), starting
Monday 2026-09-21. These are planning assumptions to revisit at each release Gate, not
commitments; the real pace will show after v1.0.

| Release | What students/coaches get | Cumulative hrs | @ 20 hrs/week | @ 12 hrs/week |
|---|---|---|---|---|
| v1.0 | Repo, CI, domain core, `verify` for evidence manifests | 114 | Oct 2026 | Nov 2026 |
| v1.1 | `cut <URL>` → verified, tagged, cited DOCX card | 285 | Dec 2026 | Mar 2027 |
| v1.2 | `search`, `--auto-cut`, `daily` digests | 381 | Feb 2027 | May 2027 |
| v1.3 | Evaluation gates, packaged CLI, team pilot | 443 | Feb 2027 | Jun 2027 |
| v2.0 | AWS, Cognito sign-in, API, cloud persistence | 607 | Apr 2027 | Sep 2027 |
| v2.1 | Web Cut-a-Card with async jobs + editor | 731 | Jun 2027 | Nov 2027 |
| v2.2 | Web research workspace (hybrid search + rerank) | 840 | Jul 2027 | Jan 2028 |
| v2.3 | Card library + extensions | 956 | Aug 2027 | Mar 2028 |
| v2.4 | Production readiness, privacy/legal sign-off | 1,035 | Sep 2027 | May 2028 |
| v3.0–v3.2 | File intelligence, argument graph, coverage, file audits | 1,307 | Dec 2027 | Oct 2028 |
| v3.3–v3.4 | Opponent data + scouting reports | 1,429 | Feb 2028 | Jan 2029 |
| v3.5–v3.7 | Round engine, CX simulator, full round simulation | 1,626 | Apr 2028 | Apr 2029 |

**Reading this for the 2026-27 season:** at a solid part-time pace, V1 (the whole CLI) lands
inside this season, with `cut` available before winter break. V2 is a summer 2027 / 2027-28
season deliverable, and V3 belongs to 2027-28 onward. To pull the web app into this season,
the most effective cuts are v1.2's optional adapters (GDELT, government sources) and deferring
v2.3's extension work.

<!-- BEGIN GENERATED -->

## Release summary

| Release | Theme | Epics | Tasks | Done | Est. hours |
|---|---|---|---|---|---|
| [v1.0](plan_specs/releases/v1.0.yaml) | Foundation & verified evidence core | 3 | 23 | 3 | 147 |
| [v1.1](plan_specs/releases/v1.1.yaml) | URL → verified card | 3 | 20 | 0 | 171 |
| [v1.2](plan_specs/releases/v1.2.yaml) | Federated research from the CLI | 2 | 14 | 0 | 96 |
| [v1.3](plan_specs/releases/v1.3.yaml) | V1 quality gate & team pilot | 1 | 7 | 0 | 62 |
| [v2.0](plan_specs/releases/v2.0.yaml) | Cloud platform foundation | 3 | 19 | 0 | 180 |
| [v2.1](plan_specs/releases/v2.1.yaml) | Async jobs & web Cut-a-Card | 2 | 12 | 0 | 124 |
| [v2.2](plan_specs/releases/v2.2.yaml) | Research workspace | 2 | 11 | 0 | 109 |
| [v2.3](plan_specs/releases/v2.3.yaml) | Card library & extensions | 2 | 11 | 0 | 116 |
| [v2.4](plan_specs/releases/v2.4.yaml) | Production readiness & school rollout | 1 | 7 | 0 | 79 |
| [v3.0](plan_specs/releases/v3.0.yaml) | Debate file intelligence & argument graph | 2 | 11 | 0 | 139 |
| [v3.1](plan_specs/releases/v3.1.yaml) | Case coverage analysis | 1 | 6 | 0 | 69 |
| [v3.2](plan_specs/releases/v3.2.yaml) | File auditing | 1 | 6 | 0 | 64 |
| [v3.3](plan_specs/releases/v3.3.yaml) | Opponent data integrations | 1 | 6 | 0 | 61 |
| [v3.4](plan_specs/releases/v3.4.yaml) | Scouting reports | 1 | 5 | 0 | 61 |
| [v3.5](plan_specs/releases/v3.5.yaml) | Round engine core | 1 | 5 | 0 | 55 |
| [v3.6](plan_specs/releases/v3.6.yaml) | Cross-examination simulator | 1 | 5 | 0 | 62 |
| [v3.7](plan_specs/releases/v3.7.yaml) | Full round simulation | 1 | 6 | 0 | 80 |

## V1

### v1.0 — Foundation & verified evidence core

Repo, tooling, CI, domain core, and deterministic evidence verification exist; `debate-research verify` works on JSON manifests. No LLM yet.

#### [E01 — Repository & Delivery Foundation](plan_specs/v1/e01-repo-foundation/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Initialize local git repository and monorepo skeleton](plan_specs/v1/e01-repo-foundation/t01-init-local-repo.yaml) `v1-e01-t01-init-local-repo` | Succeeded | 0 | 6.0 |
| [Create GitHub repository, push, and protect main](plan_specs/v1/e01-repo-foundation/t02-github-remote.yaml) `v1-e01-t02-github-remote` | Pending | 1 | 2.5 |
| [uv workspace, Python 3.12 and quality tooling](plan_specs/v1/e01-repo-foundation/t03-uv-workspace-tooling.yaml) `v1-e01-t03-uv-workspace-tooling` | Pending | 1 | 5.5 |
| [GitHub Actions CI pipeline](plan_specs/v1/e01-repo-foundation/t04-ci-pipeline.yaml) `v1-e01-t04-ci-pipeline` | Pending | 3 | 4.0 |
| [PlanSpec validation and index tooling](plan_specs/v1/e01-repo-foundation/t05-spec-tooling.yaml) `v1-e01-t05-spec-tooling` | Pending | 1 | 6.5 |
| [Architecture proposal and ADR records](plan_specs/v1/e01-repo-foundation/t06-adr-docs.yaml) `v1-e01-t06-adr-docs` | Succeeded | 1 | 4.5 |
| [debate_cli Typer + Rich skeleton](plan_specs/v1/e01-repo-foundation/t07-cli-skeleton.yaml) `v1-e01-t07-cli-skeleton` | Pending | 1 | 6.0 |
| [dev→main promotion workflow and guards](plan_specs/v1/e01-repo-foundation/t08-branch-promotion-workflow.yaml) `v1-e01-t08-branch-promotion-workflow` | Pending | 2 | 7.5 |
| [Dev pre-release channel and environment profiles for the CLI](plan_specs/v1/e01-repo-foundation/t09-dev-prerelease-channel.yaml) `v1-e01-t09-dev-prerelease-channel` | Pending | 3 | 9.0 |
| [validate-dev smoke gate for promotions](plan_specs/v1/e01-repo-foundation/t10-validate-dev-gate.yaml) `v1-e01-t10-validate-dev-gate` | Pending | 2 | 9.0 |
| [Task lifecycle CLI and session workflow](plan_specs/v1/e01-repo-foundation/t11-task-workflow-cli.yaml) `v1-e01-t11-task-workflow-cli` | Succeeded | 1 | 8.0 |

#### [E02 — Domain Core: Entities, Ports & Local Persistence](plan_specs/v1/e02-domain-core/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Pydantic domain entities and enums](plan_specs/v1/e02-domain-core/t01-domain-entities.yaml) `v1-e02-t01-domain-entities` | Pending | 1 | 8.0 |
| [Repository and provider port interfaces](plan_specs/v1/e02-domain-core/t02-ports.yaml) `v1-e02-t02-ports` | Pending | 1 | 6.5 |
| [Local filesystem and SQLite repository implementations](plan_specs/v1/e02-domain-core/t03-local-repositories.yaml) `v1-e02-t03-local-repositories` | Pending | 2 | 7.0 |
| [Reusable repository contract test suite](plan_specs/v1/e02-domain-core/t04-repo-contract-tests.yaml) `v1-e02-t04-repo-contract-tests` | Pending | 1 | 6.0 |
| [Settings and configuration](plan_specs/v1/e02-domain-core/t05-settings-config.yaml) `v1-e02-t05-settings-config` | Pending | 2 | 5.5 |
| [Import-boundary enforcement](plan_specs/v1/e02-domain-core/t06-import-boundary-guard.yaml) `v1-e02-t06-import-boundary-guard` | Pending | 2 | 5.5 |

#### [E03 — Evidence Integrity & Verification Engine](plan_specs/v1/e03-evidence-integrity/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Deterministic, versioned text normalization](plan_specs/v1/e03-evidence-integrity/t01-text-normalization.yaml) `v1-e03-t01-text-normalization` | Pending | 2 | 9.0 |
| [SHA-256 provenance and snapshot creation](plan_specs/v1/e03-evidence-integrity/t02-hashing-provenance.yaml) `v1-e03-t02-hashing-provenance` | Pending | 2 | 6.0 |
| [Span-addressed evidence extraction](plan_specs/v1/e03-evidence-integrity/t03-span-extraction.yaml) `v1-e03-t03-span-extraction` | Pending | 1 | 7.5 |
| [EvidenceVerifier and verification statuses](plan_specs/v1/e03-evidence-integrity/t04-verifier.yaml) `v1-e03-t04-verifier` | Pending | 1 | 7.0 |
| [Evidence edit policy](plan_specs/v1/e03-evidence-integrity/t05-edit-constraints.yaml) `v1-e03-t05-edit-constraints` | Pending | 1 | 5.5 |
| [`debate-research verify` command](plan_specs/v1/e03-evidence-integrity/t06-verify-command.yaml) `v1-e03-t06-verify-command` | Pending | 2 | 5.0 |


### v1.1 — URL → verified card

A student can run `debate-research cut <URL>` and receive a verified, tagged, cited, underlined card as DOCX + JSON.

#### [E04 — Article Retrieval & Extraction](plan_specs/v1/e04-article-retrieval/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [URL canonicalization and identifier detection](plan_specs/v1/e04-article-retrieval/t01-url-canonicalization.yaml) `v1-e04-t01-url-canonicalization` | Pending | 1 | 7.0 |
| [Polite HTTP fetcher](plan_specs/v1/e04-article-retrieval/t02-http-fetcher.yaml) `v1-e04-t02-http-fetcher` | Pending | 4 | 10.0 |
| [Access-status and paywall detection](plan_specs/v1/e04-article-retrieval/t03-access-status.yaml) `v1-e04-t03-access-status` | Pending | 2 | 6.0 |
| [Readable-text extraction (HTML + PDF)](plan_specs/v1/e04-article-retrieval/t04-content-extraction.yaml) `v1-e04-t04-content-extraction` | Pending | 2 | 8.5 |
| [ArticleService orchestration](plan_specs/v1/e04-article-retrieval/t05-article-service.yaml) `v1-e04-t05-article-service` | Pending | 3 | 8.5 |
| [`debate-research fetch` command and recorded fixtures](plan_specs/v1/e04-article-retrieval/t06-fetch-command.yaml) `v1-e04-t06-fetch-command` | Pending | 2 | 7.5 |

#### [E05 — Model Router & Structured LLM Contracts](plan_specs/v1/e05-model-router/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [ModelRouter interface and routing config](plan_specs/v1/e05-model-router/t01-model-router-port.yaml) `v1-e05-t01-model-router-port` | Pending | 1 | 9.0 |
| [Amazon Bedrock adapter](plan_specs/v1/e05-model-router/t02-bedrock-adapter.yaml) `v1-e05-t02-bedrock-adapter` | Pending | 1 | 10.0 |
| [Deterministic fake and record/replay models](plan_specs/v1/e05-model-router/t03-fake-replay-models.yaml) `v1-e05-t03-fake-replay-models` | Pending | 1 | 9.0 |
| [Versioned prompt registry](plan_specs/v1/e05-model-router/t04-prompt-registry.yaml) `v1-e05-t04-prompt-registry` | Pending | 1 | 8.0 |
| [Structured output validation and repair](plan_specs/v1/e05-model-router/t05-structured-output-validation.yaml) `v1-e05-t05-structured-output-validation` | Pending | 2 | 7.0 |
| [CardSelection / MarkupSpan contract and prompts](plan_specs/v1/e05-model-router/t06-card-selection-contract.yaml) `v1-e05-t06-card-selection-contract` | Pending | 3 | 12.0 |
| [Token/cost telemetry and budgets](plan_specs/v1/e05-model-router/t07-usage-telemetry.yaml) `v1-e05-t07-usage-telemetry` | Pending | 1 | 8.0 |

#### [E06 — Card Cutting, Citation & Export](plan_specs/v1/e06-card-cutting/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [CitationService with per-field provenance](plan_specs/v1/e06-card-cutting/t01-citation-service.yaml) `v1-e06-t01-citation-service` | Pending | 1 | 9.0 |
| [CardService pipeline](plan_specs/v1/e06-card-cutting/t02-card-service.yaml) `v1-e06-t02-card-service` | Pending | 3 | 10.0 |
| [Card format profiles from team conventions](plan_specs/v1/e06-card-cutting/t03-format-profiles.yaml) `v1-e06-t03-format-profiles` | Pending | 1 | 9.5 |
| [DOCX renderer](plan_specs/v1/e06-card-cutting/t04-docx-renderer.yaml) `v1-e06-t04-docx-renderer` | Pending | 3 | 11.0 |
| [JSON manifest export](plan_specs/v1/e06-card-cutting/t05-json-manifest-export.yaml) `v1-e06-t05-json-manifest-export` | Pending | 2 | 6.0 |
| [`debate-research cut` command](plan_specs/v1/e06-card-cutting/t06-cut-command.yaml) `v1-e06-t06-cut-command` | Pending | 3 | 7.0 |
| [Verify DOCX files](plan_specs/v1/e06-card-cutting/t07-verify-docx.yaml) `v1-e06-t07-verify-docx` | Pending | 2 | 8.0 |


### v1.2 — Federated research from the CLI

`debate-research search` fans out to scholarly/news/government adapters, dedupes and ranks results, supports --argument/--need and --auto-cut, and `daily` digests.

#### [E07 — Discovery Provider Adapters](plan_specs/v1/e07-discovery-adapters/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [SearchProvider contract, health and circuit breaking](plan_specs/v1/e07-discovery-adapters/t01-search-provider-contract.yaml) `v1-e07-t01-search-provider-contract` | Pending | 1 | 9.0 |
| [OpenAlex adapter](plan_specs/v1/e07-discovery-adapters/t02-openalex-adapter.yaml) `v1-e07-t02-openalex-adapter` | Pending | 1 | 5.0 |
| [Crossref adapter](plan_specs/v1/e07-discovery-adapters/t03-crossref-adapter.yaml) `v1-e07-t03-crossref-adapter` | Pending | 2 | 5.0 |
| [Semantic Scholar adapter](plan_specs/v1/e07-discovery-adapters/t04-semantic-scholar-adapter.yaml) `v1-e07-t04-semantic-scholar-adapter` | Pending | 1 | 4.0 |
| [Publisher RSS/Atom and Google News RSS adapter](plan_specs/v1/e07-discovery-adapters/t05-rss-news-adapter.yaml) `v1-e07-t05-rss-news-adapter` | Pending | 1 | 8.0 |
| [GDELT news adapter](plan_specs/v1/e07-discovery-adapters/t06-gdelt-adapter.yaml) `v1-e07-t06-gdelt-adapter` | Pending | 1 | 4.0 |
| [Government and policy source adapters](plan_specs/v1/e07-discovery-adapters/t07-government-adapters.yaml) `v1-e07-t07-government-adapters` | Pending | 1 | 8.0 |

#### [E08 — Federated Research Workflows](plan_specs/v1/e08-research-workflows/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [SearchService fan-out](plan_specs/v1/e08-research-workflows/t01-federated-search-service.yaml) `v1-e08-t01-federated-search-service` | Pending | 1 | 7.0 |
| [Normalization and deduplication](plan_specs/v1/e08-research-workflows/t02-normalize-dedupe.yaml) `v1-e08-t02-normalize-dedupe` | Pending | 2 | 8.0 |
| [Explainable feature ranking](plan_specs/v1/e08-research-workflows/t03-feature-ranking.yaml) `v1-e08-t03-feature-ranking` | Pending | 1 | 8.0 |
| [Argument/need query expansion](plan_specs/v1/e08-research-workflows/t04-argument-need-expansion.yaml) `v1-e08-t04-argument-need-expansion` | Pending | 3 | 7.5 |
| [`debate-research search` command](plan_specs/v1/e08-research-workflows/t05-search-command.yaml) `v1-e08-t05-search-command` | Pending | 4 | 6.0 |
| [`--auto-cut N` batch cutting](plan_specs/v1/e08-research-workflows/t06-auto-cut.yaml) `v1-e08-t06-auto-cut` | Pending | 3 | 9.0 |
| [`debate-research daily` digests](plan_specs/v1/e08-research-workflows/t07-daily-command.yaml) `v1-e08-t07-daily-command` | Pending | 2 | 7.0 |


### v1.3 — V1 quality gate & team pilot

Golden-card and LLM evaluations gate prompt/model changes; the CLI is packaged and piloted with the team.

#### [E09 — V1 Quality, Evaluation & Team Pilot](plan_specs/v1/e09-v1-quality-pilot/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Golden card fixtures from team files](plan_specs/v1/e09-v1-quality-pilot/t01-golden-card-fixtures.yaml) `v1-e09-t01-golden-card-fixtures` | Pending | 1 | 12.0 |
| [Golden DOCX regression tests](plan_specs/v1/e09-v1-quality-pilot/t02-docx-golden-tests.yaml) `v1-e09-t02-docx-golden-tests` | Pending | 1 | 7.0 |
| [Card selection and underlining eval harness](plan_specs/v1/e09-v1-quality-pilot/t03-span-eval-harness.yaml) `v1-e09-t03-span-eval-harness` | Pending | 2 | 9.0 |
| [Prompt/model promotion gate](plan_specs/v1/e09-v1-quality-pilot/t04-prompt-promotion-gate.yaml) `v1-e09-t04-prompt-promotion-gate` | Pending | 3 | 5.5 |
| [End-to-end recorded suite](plan_specs/v1/e09-v1-quality-pilot/t05-e2e-fixture-suite.yaml) `v1-e09-t05-e2e-fixture-suite` | Pending | 1 | 9.0 |
| [Packaging and release workflow](plan_specs/v1/e09-v1-quality-pilot/t06-packaging-release.yaml) `v1-e09-t06-packaging-release` | Pending | 2 | 6.0 |
| [Student/coach guide and team pilot](plan_specs/v1/e09-v1-quality-pilot/t07-team-pilot.yaml) `v1-e09-t07-team-pilot` | Pending | 2 | 14.0 |


## V2

### v2.0 — Cloud platform foundation

AWS accounts/Terraform/CI deploy, DynamoDB + S3 repositories passing the same contract tests, Cognito auth and the FastAPI service are live in dev and prod, with every prod deploy promoted from a validated dev deploy.

#### [E10 — AWS & Infrastructure-as-Code Foundation](plan_specs/v2/e10-aws-foundation/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [AWS account baseline](plan_specs/v2/e10-aws-foundation/t01-aws-account-baseline.yaml) `v2-e10-t01-aws-account-baseline` | Pending | 0 | 10.0 |
| [Terraform bootstrap and environments](plan_specs/v2/e10-aws-foundation/t02-terraform-bootstrap.yaml) `v2-e10-t02-terraform-bootstrap` | Pending | 1 | 6.0 |
| [GitHub OIDC deploy roles](plan_specs/v2/e10-aws-foundation/t03-github-oidc-deploy.yaml) `v2-e10-t03-github-oidc-deploy` | Pending | 1 | 8.0 |
| [KMS keys and Secrets Manager](plan_specs/v2/e10-aws-foundation/t04-kms-secrets.yaml) `v2-e10-t04-kms-secrets` | Pending | 1 | 9.0 |
| [Networking, ECR and ECS/Fargate cluster](plan_specs/v2/e10-aws-foundation/t05-container-platform.yaml) `v2-e10-t05-container-platform` | Pending | 1 | 10.0 |
| [Observability baseline](plan_specs/v2/e10-aws-foundation/t06-observability-baseline.yaml) `v2-e10-t06-observability-baseline` | Pending | 1 | 11.0 |

#### [E11 — Cloud Persistence Adapters](plan_specs/v2/e11-cloud-persistence/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [AppTable access-pattern design](plan_specs/v2/e11-cloud-persistence/t01-access-pattern-design.yaml) `v2-e11-t01-access-pattern-design` | Pending | 1 | 8.0 |
| [DynamoDB tables in Terraform](plan_specs/v2/e11-cloud-persistence/t02-dynamodb-tables.yaml) `v2-e11-t02-dynamodb-tables` | Pending | 2 | 6.0 |
| [DynamoDB repository implementations](plan_specs/v2/e11-cloud-persistence/t03-dynamodb-repositories.yaml) `v2-e11-t03-dynamodb-repositories` | Pending | 2 | 13.0 |
| [S3 snapshot and export store](plan_specs/v2/e11-cloud-persistence/t04-s3-snapshot-store.yaml) `v2-e11-t04-s3-snapshot-store` | Pending | 2 | 8.0 |
| [Optimistic concurrency for cards and files](plan_specs/v2/e11-cloud-persistence/t05-optimistic-concurrency.yaml) `v2-e11-t05-optimistic-concurrency` | Pending | 1 | 10.0 |
| [V1 local-library migration tool](plan_specs/v2/e11-cloud-persistence/t06-v1-data-migration.yaml) `v2-e11-t06-v1-data-migration` | Pending | 3 | 10.0 |

#### [E12 — Identity & API Service](plan_specs/v2/e12-identity-api/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Cognito user pool and Google federation](plan_specs/v2/e12-identity-api/t01-cognito-user-pool.yaml) `v2-e12-t01-cognito-user-pool` | Pending | 1 | 8.0 |
| [FastAPI service skeleton](plan_specs/v2/e12-identity-api/t02-fastapi-service.yaml) `v2-e12-t02-fastapi-service` | Pending | 1 | 9.0 |
| [Authentication, roles and tenancy](plan_specs/v2/e12-identity-api/t03-authn-authz.yaml) `v2-e12-t03-authn-authz` | Pending | 2 | 9.0 |
| [API Gateway + ECS Fargate deployment](plan_specs/v2/e12-identity-api/t04-api-deploy.yaml) `v2-e12-t04-api-deploy` | Pending | 3 | 11.0 |
| [Core resource endpoints](plan_specs/v2/e12-identity-api/t05-core-endpoints.yaml) `v2-e12-t05-core-endpoints` | Pending | 5 | 12.0 |
| [OpenAPI TypeScript client generation](plan_specs/v2/e12-identity-api/t06-openapi-client.yaml) `v2-e12-t06-openapi-client` | Pending | 1 | 6.0 |
| [Cloud dev→prod promotion pipeline](plan_specs/v2/e12-identity-api/t07-promotion-pipeline.yaml) `v2-e12-t07-promotion-pipeline` | Pending | 3 | 15.5 |


### v2.1 — Async jobs & web Cut-a-Card

Students log in to the web app, paste a URL, watch an async CardJob, edit the verified card within provenance rules, and export it.

#### [E13 — Async Job Orchestration](plan_specs/v2/e13-async-jobs/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Job entity and repository](plan_specs/v2/e13-async-jobs/t01-job-model.yaml) `v2-e13-t01-job-model` | Pending | 1 | 8.0 |
| [SQS queues and worker framework](plan_specs/v2/e13-async-jobs/t02-sqs-workers.yaml) `v2-e13-t02-sqs-workers` | Pending | 3 | 12.0 |
| [CardJob Step Functions workflow](plan_specs/v2/e13-async-jobs/t03-card-job-workflow.yaml) `v2-e13-t03-card-job-workflow` | Pending | 2 | 13.0 |
| [SearchJob workflow](plan_specs/v2/e13-async-jobs/t04-search-job-workflow.yaml) `v2-e13-t04-search-job-workflow` | Pending | 2 | 9.0 |
| [Job status API (polling + SSE)](plan_specs/v2/e13-async-jobs/t05-job-status-api.yaml) `v2-e13-t05-job-status-api` | Pending | 2 | 10.0 |
| [EventBridge domain events and schedules](plan_specs/v2/e13-async-jobs/t06-domain-events.yaml) `v2-e13-t06-domain-events` | Pending | 3 | 10.0 |

#### [E14 — Web App Shell & Cut-a-Card](plan_specs/v2/e14-web-cut-card/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Next.js application scaffold](plan_specs/v2/e14-web-cut-card/t01-nextjs-scaffold.yaml) `v2-e14-t01-nextjs-scaffold` | Pending | 2 | 8.0 |
| [Authentication UX](plan_specs/v2/e14-web-cut-card/t02-auth-ui.yaml) `v2-e14-t02-auth-ui` | Pending | 2 | 10.0 |
| [Web hosting and environments](plan_specs/v2/e14-web-cut-card/t03-app-hosting.yaml) `v2-e14-t03-app-hosting` | Pending | 5 | 9.0 |
| [Cut-a-Card flow](plan_specs/v2/e14-web-cut-card/t04-cut-card-flow.yaml) `v2-e14-t04-cut-card-flow` | Pending | 4 | 12.0 |
| [Provenance-constrained card editor](plan_specs/v2/e14-web-cut-card/t05-card-editor.yaml) `v2-e14-t05-card-editor` | Pending | 3 | 14.0 |
| [DOCX export and copy-as-rich-text](plan_specs/v2/e14-web-cut-card/t06-export-copy.yaml) `v2-e14-t06-export-copy` | Pending | 2 | 9.0 |


### v2.2 — Research workspace

Hybrid BM25/vector search with reranking returns ten strong, explained results in the web UI with open/cut actions.

#### [E15 — Search Index & Hybrid Retrieval](plan_specs/v2/e15-search-index/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [OpenSearch Serverless collections](plan_specs/v2/e15-search-index/t01-opensearch-serverless.yaml) `v2-e15-t01-opensearch-serverless` | Pending | 1 | 10.0 |
| [Index mappings and chunking](plan_specs/v2/e15-search-index/t02-index-mappings-chunking.yaml) `v2-e15-t02-index-mappings-chunking` | Pending | 2 | 10.5 |
| [Titan embeddings pipeline](plan_specs/v2/e15-search-index/t03-embeddings-pipeline.yaml) `v2-e15-t03-embeddings-pipeline` | Pending | 3 | 11.5 |
| [Hybrid BM25 + kNN retrieval](plan_specs/v2/e15-search-index/t04-hybrid-retrieval.yaml) `v2-e15-t04-hybrid-retrieval` | Pending | 1 | 10.0 |
| [Rerank and result rationale](plan_specs/v2/e15-search-index/t05-rerank-rationale.yaml) `v2-e15-t05-rerank-rationale` | Pending | 2 | 9.0 |
| [Index rebuild from source of truth](plan_specs/v2/e15-search-index/t06-index-rebuild.yaml) `v2-e15-t06-index-rebuild` | Pending | 3 | 11.0 |

#### [E16 — Research Workspace UI](plan_specs/v2/e16-research-ui/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Search API endpoints](plan_specs/v2/e16-research-ui/t01-search-api.yaml) `v2-e16-t01-search-api` | Pending | 2 | 8.0 |
| [Research page](plan_specs/v2/e16-research-ui/t02-research-page.yaml) `v2-e16-t02-research-page` | Pending | 3 | 10.0 |
| [Result cards with rationale and actions](plan_specs/v2/e16-research-ui/t03-result-cards.yaml) `v2-e16-t03-result-cards` | Pending | 2 | 8.0 |
| [Search history and saved searches](plan_specs/v2/e16-research-ui/t04-search-history.yaml) `v2-e16-t04-search-history` | Pending | 2 | 10.0 |
| [Search relevance evaluation](plan_specs/v2/e16-research-ui/t05-relevance-eval.yaml) `v2-e16-t05-relevance-eval` | Pending | 1 | 11.0 |


### v2.3 — Card library & extensions

Saved card library with revisions, folders, sharing and bulk export; pasted cards produce labeled extension bullets and CX questions.

#### [E17 — Card Library](plan_specs/v2/e17-card-library/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Library data model](plan_specs/v2/e17-card-library/t01-library-model.yaml) `v2-e17-t01-library-model` | Pending | 1 | 11.0 |
| [Library API](plan_specs/v2/e17-card-library/t02-library-api.yaml) `v2-e17-t02-library-api` | Pending | 3 | 11.0 |
| [Library UI](plan_specs/v2/e17-card-library/t03-library-ui.yaml) `v2-e17-t03-library-ui` | Pending | 2 | 12.0 |
| [Revision history and restore](plan_specs/v2/e17-card-library/t04-revision-history.yaml) `v2-e17-t04-revision-history` | Pending | 1 | 10.0 |
| [Bulk DOCX export](plan_specs/v2/e17-card-library/t05-bulk-export.yaml) `v2-e17-t05-bulk-export` | Pending | 4 | 10.0 |
| [Organization sharing](plan_specs/v2/e17-card-library/t06-team-sharing.yaml) `v2-e17-t06-team-sharing` | Pending | 1 | 10.0 |

#### [E18 — Card Extensions](plan_specs/v2/e18-card-extensions/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Pasted-card parser](plan_specs/v2/e18-card-extensions/t01-card-parser.yaml) `v2-e18-t01-card-parser` | Pending | 1 | 11.5 |
| [Claim/warrant component extraction](plan_specs/v2/e18-card-extensions/t02-component-extraction.yaml) `v2-e18-t02-component-extraction` | Pending | 2 | 9.0 |
| [Extension, CX question and answer generation](plan_specs/v2/e18-card-extensions/t03-extension-generator.yaml) `v2-e18-t03-extension-generator` | Pending | 1 | 10.0 |
| [Extensions API and UI](plan_specs/v2/e18-card-extensions/t04-extension-ui.yaml) `v2-e18-t04-extension-ui` | Pending | 3 | 10.0 |
| [Extension evaluation](plan_specs/v2/e18-card-extensions/t05-extension-eval.yaml) `v2-e18-t05-extension-eval` | Pending | 2 | 11.0 |


### v2.4 — Production readiness & school rollout

Quotas, audit logs, retention/deletion, backups, cost telemetry and a completed privacy/legal review clear the platform for team-wide use.

#### [E19 — Production Readiness, Privacy & Safety](plan_specs/v2/e19-production-readiness/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Quotas and rate limits](plan_specs/v2/e19-production-readiness/t01-quotas-rate-limits.yaml) `v2-e19-t01-quotas-rate-limits` | Pending | 2 | 10.0 |
| [Audit logging](plan_specs/v2/e19-production-readiness/t02-audit-logging.yaml) `v2-e19-t02-audit-logging` | Pending | 2 | 10.0 |
| [Account export, deletion and retention](plan_specs/v2/e19-production-readiness/t03-account-lifecycle.yaml) `v2-e19-t03-account-lifecycle` | Pending | 3 | 14.0 |
| [Privacy and legal review](plan_specs/v2/e19-production-readiness/t04-privacy-legal-review.yaml) `v2-e19-t04-privacy-legal-review` | Pending | 0 | 13.0 |
| [Backups and restore drill](plan_specs/v2/e19-production-readiness/t05-backups-dr.yaml) `v2-e19-t05-backups-dr` | Pending | 4 | 10.0 |
| [Cost telemetry dashboard](plan_specs/v2/e19-production-readiness/t06-cost-dashboard.yaml) `v2-e19-t06-cost-dashboard` | Pending | 2 | 8.0 |
| [Load and security testing](plan_specs/v2/e19-production-readiness/t07-load-security-testing.yaml) `v2-e19-t07-load-security-testing` | Pending | 2 | 14.0 |


## V3

### v3.0 — Debate file intelligence & argument graph

Uploaded debate files are parsed into sections/cards and an explicit, sourced argument graph.

#### [E20 — Debate File Intelligence](plan_specs/v3/e20-file-intelligence/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [DebateFile and FileSection model](plan_specs/v3/e20-file-intelligence/t01-debate-file-model.yaml) `v3-e20-t01-debate-file-model` | Pending | 3 | 10.0 |
| [Upload pipeline](plan_specs/v3/e20-file-intelligence/t02-upload-pipeline.yaml) `v3-e20-t02-upload-pipeline` | Pending | 3 | 13.0 |
| [DOCX structure parser](plan_specs/v3/e20-file-intelligence/t03-docx-structure-parser.yaml) `v3-e20-t03-docx-structure-parser` | Pending | 3 | 15.0 |
| [Parser accuracy evaluation](plan_specs/v3/e20-file-intelligence/t04-parser-eval.yaml) `v3-e20-t04-parser-eval` | Pending | 1 | 15.0 |
| [File library UI](plan_specs/v3/e20-file-intelligence/t05-file-library-ui.yaml) `v3-e20-t05-file-library-ui` | Pending | 3 | 14.0 |

#### [E21 — Argument Graph](plan_specs/v3/e21-argument-graph/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [ArgumentTable and GraphRepository](plan_specs/v3/e21-argument-graph/t01-graph-repository.yaml) `v3-e21-t01-graph-repository` | Pending | 2 | 10.0 |
| [Argument node extraction](plan_specs/v3/e21-argument-graph/t02-node-extraction.yaml) `v3-e21-t02-node-extraction` | Pending | 4 | 13.0 |
| [Argument edge extraction](plan_specs/v3/e21-argument-graph/t03-edge-extraction.yaml) `v3-e21-t03-edge-extraction` | Pending | 2 | 13.0 |
| [Coverage and coherence query primitives](plan_specs/v3/e21-argument-graph/t04-graph-queries.yaml) `v3-e21-t04-graph-queries` | Pending | 1 | 12.0 |
| [Graph extraction evaluation](plan_specs/v3/e21-argument-graph/t05-graph-eval.yaml) `v3-e21-t05-graph-eval` | Pending | 1 | 12.0 |
| [Argument graph viewer](plan_specs/v3/e21-argument-graph/t06-graph-viewer.yaml) `v3-e21-t06-graph-viewer` | Pending | 2 | 12.0 |


### v3.1 — Case coverage analysis

An uploaded affirmative yields predicted opposition positions and a coverage-gap report against the student's extensions.

#### [E22 — Case Coverage Analysis](plan_specs/v3/e22-coverage-analysis/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Argument archetype library](plan_specs/v3/e22-coverage-analysis/t01-argument-archetypes.yaml) `v3-e22-t01-argument-archetypes` | Pending | 1 | 11.0 |
| [Affirmative case structure](plan_specs/v3/e22-coverage-analysis/t02-aff-case-parser.yaml) `v3-e22-t02-aff-case-parser` | Pending | 1 | 11.0 |
| [Likely-position prediction](plan_specs/v3/e22-coverage-analysis/t03-position-prediction.yaml) `v3-e22-t03-position-prediction` | Pending | 3 | 14.0 |
| [Coverage gap detection](plan_specs/v3/e22-coverage-analysis/t04-gap-detection.yaml) `v3-e22-t04-gap-detection` | Pending | 3 | 10.0 |
| [Coverage report UI and export](plan_specs/v3/e22-coverage-analysis/t05-coverage-report-ui.yaml) `v3-e22-t05-coverage-report-ui` | Pending | 2 | 13.0 |
| [Coverage evaluation](plan_specs/v3/e22-coverage-analysis/t06-coverage-eval.yaml) `v3-e22-t06-coverage-eval` | Pending | 1 | 10.0 |


### v3.2 — File auditing

A DA (or other) file can be audited for 1NC shell coherence with explained card-by-card alternatives.

#### [E23 — File Auditing](plan_specs/v3/e23-file-auditing/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [1NC shell identification](plan_specs/v3/e23-file-auditing/t01-shell-identification.yaml) `v3-e23-t01-shell-identification` | Pending | 1 | 11.0 |
| [Shell coherence checks](plan_specs/v3/e23-file-auditing/t02-coherence-checks.yaml) `v3-e23-t02-coherence-checks` | Pending | 2 | 10.0 |
| [Card-vs-alternative comparison](plan_specs/v3/e23-file-auditing/t03-card-comparison.yaml) `v3-e23-t03-card-comparison` | Pending | 1 | 12.0 |
| [Newer external evidence suggestions](plan_specs/v3/e23-file-auditing/t04-newer-evidence.yaml) `v3-e23-t04-newer-evidence` | Pending | 3 | 7.0 |
| [Audit report UI](plan_specs/v3/e23-file-auditing/t05-audit-report-ui.yaml) `v3-e23-t05-audit-report-ui` | Pending | 2 | 13.0 |
| [File audit evaluation](plan_specs/v3/e23-file-auditing/t06-audit-eval.yaml) `v3-e23-t06-audit-eval` | Pending | 2 | 11.0 |


### v3.3 — Opponent data integrations

Public OpenCaselist disclosures and Tabroom results are ingested with provenance and resolved to team identities.

#### [E24 — Opponent Data Integrations](plan_specs/v3/e24-opponent-data/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [OpponentTable design](plan_specs/v3/e24-opponent-data/t01-opponent-table.yaml) `v3-e24-t01-opponent-table` | Pending | 3 | 9.0 |
| [OpenCaselist adapter](plan_specs/v3/e24-opponent-data/t02-opencaselist-adapter.yaml) `v3-e24-t02-opencaselist-adapter` | Pending | 2 | 12.0 |
| [Tabroom public results adapter](plan_specs/v3/e24-opponent-data/t03-tabroom-adapter.yaml) `v3-e24-t03-tabroom-adapter` | Pending | 2 | 10.0 |
| [Team and debater identity resolution](plan_specs/v3/e24-opponent-data/t04-identity-resolution.yaml) `v3-e24-t04-identity-resolution` | Pending | 2 | 12.0 |
| [Refresh scheduling and removal](plan_specs/v3/e24-opponent-data/t05-refresh-provenance.yaml) `v3-e24-t05-refresh-provenance` | Pending | 3 | 10.0 |
| [Opponent data governance review](plan_specs/v3/e24-opponent-data/t06-data-governance.yaml) `v3-e24-t06-data-governance` | Pending | 1 | 8.0 |


### v3.4 — Scouting reports

Coaches and students generate sourced scouting reports on opponents, and disclosures inform coverage predictions.

#### [E25 — Scouting Reports](plan_specs/v3/e25-scouting-reports/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Disclosure summarization](plan_specs/v3/e25-scouting-reports/t01-disclosure-summarization.yaml) `v3-e25-t01-disclosure-summarization` | Pending | 1 | 14.0 |
| [Results analytics](plan_specs/v3/e25-scouting-reports/t02-results-analytics.yaml) `v3-e25-t02-results-analytics` | Pending | 1 | 9.0 |
| [Scouting report generation](plan_specs/v3/e25-scouting-reports/t03-report-generation.yaml) `v3-e25-t03-report-generation` | Pending | 4 | 14.0 |
| [Scouting UI and export](plan_specs/v3/e25-scouting-reports/t04-scouting-ui.yaml) `v3-e25-t04-scouting-ui` | Pending | 3 | 14.0 |
| [Disclosure-informed coverage predictions](plan_specs/v3/e25-scouting-reports/t05-prediction-integration.yaml) `v3-e25-t05-prediction-integration` | Pending | 3 | 10.0 |


### v3.5 — Round engine core

A persisted, replayable round state machine models Policy/LD/PF formats, judge profiles and the flow.

#### [E26 — Round Engine Core](plan_specs/v3/e26-round-engine/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Round, RoundEvent and flow state model](plan_specs/v3/e26-round-engine/t01-round-model.yaml) `v3-e26-t01-round-model` | Pending | 1 | 10.0 |
| [Format rule modules](plan_specs/v3/e26-round-engine/t02-format-rules.yaml) `v3-e26-t02-format-rules` | Pending | 1 | 8.0 |
| [Round state machine](plan_specs/v3/e26-round-engine/t03-state-machine.yaml) `v3-e26-t03-state-machine` | Pending | 3 | 13.0 |
| [Judge profile policies](plan_specs/v3/e26-round-engine/t04-judge-profiles.yaml) `v3-e26-t04-judge-profiles` | Pending | 1 | 9.0 |
| [Flow tracking](plan_specs/v3/e26-round-engine/t05-flow-tracking.yaml) `v3-e26-t05-flow-tracking` | Pending | 2 | 15.0 |


### v3.6 — Cross-examination simulator

Students practice CX against a simulated opponent grounded in the argument graph, with concessions recorded to the flow.

#### [E27 — Cross-Examination Simulator](plan_specs/v3/e27-cx-simulator/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [CX question generation](plan_specs/v3/e27-cx-simulator/t01-cx-question-generation.yaml) `v3-e27-t01-cx-question-generation` | Pending | 2 | 11.0 |
| [Simulated CX answers](plan_specs/v3/e27-cx-simulator/t02-cx-answer-simulation.yaml) `v3-e27-t02-cx-answer-simulation` | Pending | 1 | 11.0 |
| [Concession detection](plan_specs/v3/e27-cx-simulator/t03-concession-detection.yaml) `v3-e27-t03-concession-detection` | Pending | 2 | 12.0 |
| [CX session UI](plan_specs/v3/e27-cx-simulator/t04-cx-session-ui.yaml) `v3-e27-t04-cx-session-ui` | Pending | 3 | 14.0 |
| [CX evaluation](plan_specs/v3/e27-cx-simulator/t05-cx-eval.yaml) `v3-e27-t05-cx-eval` | Pending | 1 | 14.0 |


### v3.7 — Full round simulation

Full simulated rounds with opponent-informed strategy and a traceable judge decision/RFD, gated by coach-curated evals.

#### [E28 — Full Round Simulation](plan_specs/v3/e28-round-simulation/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Speech planning](plan_specs/v3/e28-round-simulation/t01-speech-planning.yaml) `v3-e28-t01-speech-planning` | Pending | 1 | 11.0 |
| [Opponent speech generation](plan_specs/v3/e28-round-simulation/t02-opponent-speech-generation.yaml) `v3-e28-t02-opponent-speech-generation` | Pending | 2 | 12.0 |
| [Judge decision and RFD](plan_specs/v3/e28-round-simulation/t03-judge-decision.yaml) `v3-e28-t03-judge-decision` | Pending | 2 | 10.0 |
| [Opponent-informed simulation](plan_specs/v3/e28-round-simulation/t04-opponent-informed-sim.yaml) `v3-e28-t04-opponent-informed-sim` | Pending | 3 | 10.0 |
| [Full round UI](plan_specs/v3/e28-round-simulation/t05-full-round-ui.yaml) `v3-e28-t05-full-round-ui` | Pending | 2 | 19.0 |
| [Simulation evaluation and coach review](plan_specs/v3/e28-round-simulation/t06-simulation-eval.yaml) `v3-e28-t06-simulation-eval` | Pending | 4 | 18.0 |

<!-- END GENERATED -->

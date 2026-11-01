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
| [v1.0](plan_specs/releases/v1.0.yaml) | Foundation & verified evidence core | 3 | 55 | 55 | 252 |
| [v1.1](plan_specs/releases/v1.1.yaml) | Caselist evidence store | 4 | 115 | 94 | 505 |
| [v1.2](plan_specs/releases/v1.2.yaml) | Argument landscape & file building | 3 | 73 | 67 | 304 |
| [v1.3](plan_specs/releases/v1.3.yaml) | URL → verified card | 2 | 16 | 11 | 114 |
| [v1.4](plan_specs/releases/v1.4.yaml) | Federated research from the CLI | 2 | 16 | 7 | 98 |
| [v1.5](plan_specs/releases/v1.5.yaml) | V1 quality gate & team pilot | 1 | 7 | 0 | 66 |
| [v1.6](plan_specs/releases/v1.6.yaml) | Public team website | 3 | 29 | 21 | 166 |
| [v1.7](plan_specs/releases/v1.7.yaml) | Team evidence search pilot | 1 | 29 | 25 | 94 |
| [v1.8](plan_specs/releases/v1.8.yaml) | Weekly caselist run in the cloud | 2 | 51 | 30 | 90 |
| [v2.0](plan_specs/releases/v2.0.yaml) | Cloud platform foundation | 3 | 17 | 0 | 164 |
| [v2.1](plan_specs/releases/v2.1.yaml) | Web app, debate tub & async jobs | 3 | 18 | 0 | 198 |
| [v2.2](plan_specs/releases/v2.2.yaml) | Research workspace | 2 | 12 | 0 | 117 |
| [v2.3](plan_specs/releases/v2.3.yaml) | Card library & extensions | 2 | 11 | 0 | 116 |
| [v2.4](plan_specs/releases/v2.4.yaml) | Production readiness & school rollout | 1 | 7 | 0 | 79 |
| [v3.0](plan_specs/releases/v3.0.yaml) | Debate file intelligence & argument graph | 2 | 9 | 0 | 109 |
| [v3.1](plan_specs/releases/v3.1.yaml) | Case coverage analysis | 1 | 6 | 0 | 69 |
| [v3.2](plan_specs/releases/v3.2.yaml) | File auditing | 1 | 6 | 0 | 64 |
| [v3.3](plan_specs/releases/v3.3.yaml) | Opponent data integrations | 1 | 6 | 0 | 61 |
| [v3.4](plan_specs/releases/v3.4.yaml) | Scouting reports | 1 | 5 | 0 | 61 |
| [v3.5](plan_specs/releases/v3.5.yaml) | Round engine core | 1 | 5 | 0 | 55 |
| [v3.6](plan_specs/releases/v3.6.yaml) | Cross-examination simulator | 1 | 5 | 0 | 62 |
| [v3.7](plan_specs/releases/v3.7.yaml) | Full round simulation | 1 | 6 | 0 | 80 |

## V1

### v1.0 — Foundation & verified evidence core

Repo, tooling, CI, promotion flow, task tooling, domain core, and deterministic evidence verification exist; `debate-research verify` works on JSON manifests.

#### [E01 — Repository & Delivery Foundation](plan_specs/v1/e01-repo-foundation/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Initialize local git repository and monorepo skeleton](plan_specs/v1/e01-repo-foundation/t01-init-local-repo.yaml) `v1-e01-t01-init-local-repo` | Succeeded | 0 | 6.0 |
| [Create GitHub repository, push, and protect main](plan_specs/v1/e01-repo-foundation/t02-github-remote.yaml) `v1-e01-t02-github-remote` | Succeeded | 1 | 2.5 |
| [uv workspace, Python 3.12 and quality tooling](plan_specs/v1/e01-repo-foundation/t03-uv-workspace-tooling.yaml) `v1-e01-t03-uv-workspace-tooling` | Succeeded | 1 | 5.5 |
| [GitHub Actions CI pipeline](plan_specs/v1/e01-repo-foundation/t04-ci-pipeline.yaml) `v1-e01-t04-ci-pipeline` | Succeeded | 3 | 4.0 |
| [PlanSpec validation and index tooling](plan_specs/v1/e01-repo-foundation/t05-spec-tooling.yaml) `v1-e01-t05-spec-tooling` | Succeeded | 2 | 9.5 |
| [Architecture proposal and ADR records](plan_specs/v1/e01-repo-foundation/t06-adr-docs.yaml) `v1-e01-t06-adr-docs` | Succeeded | 1 | 4.5 |
| [debate_cli Typer + Rich skeleton](plan_specs/v1/e01-repo-foundation/t07-cli-skeleton.yaml) `v1-e01-t07-cli-skeleton` | Succeeded | 1 | 6.0 |
| [dev→main promotion workflow and guards](plan_specs/v1/e01-repo-foundation/t08-branch-promotion-workflow.yaml) `v1-e01-t08-branch-promotion-workflow` | Succeeded | 2 | 7.5 |
| [Dev pre-release channel and environment profiles for the CLI](plan_specs/v1/e01-repo-foundation/t09-dev-prerelease-channel.yaml) `v1-e01-t09-dev-prerelease-channel` | Succeeded | 3 | 9.0 |
| [validate-dev smoke gate for promotions](plan_specs/v1/e01-repo-foundation/t10-validate-dev-gate.yaml) `v1-e01-t10-validate-dev-gate` | Succeeded | 2 | 9.0 |
| [Task lifecycle CLI and session workflow](plan_specs/v1/e01-repo-foundation/t11-task-workflow-cli.yaml) `v1-e01-t11-task-workflow-cli` | Succeeded | 1 | 8.0 |
| [Re-run the promotion guards when main moves](plan_specs/v1/e01-repo-foundation/t12-promotion-guard-rerun.yaml) `v1-e01-t12-promotion-guard-rerun` | Succeeded | 1 | 3.5 |
| [Empty the import-boundary exception lists](plan_specs/v1/e01-repo-foundation/t13-composition-root-cleanup.yaml) `v1-e01-t13-composition-root-cleanup` | Succeeded | 1 | 4.0 |
| [One source for the supported interpreter, enforced at install](plan_specs/v1/e01-repo-foundation/t14-install-interpreter-bound.yaml) `v1-e01-t14-install-interpreter-bound` | Succeeded | 2 | 6.0 |
| [Re-run the promotion guards without waiting for an event](plan_specs/v1/e01-repo-foundation/t15-promotion-guard-sweep.yaml) `v1-e01-t15-promotion-guard-sweep` | Succeeded | 1 | 7.0 |
| [Generate the docs index instead of hand-editing it](plan_specs/v1/e01-repo-foundation/t16-generated-docs-index.yaml) `v1-e01-t16-generated-docs-index` | Succeeded | 1 | 6.5 |
| [The installed build carries what its commands need](plan_specs/v1/e01-repo-foundation/t17-installed-build-extras.yaml) `v1-e01-t17-installed-build-extras` | Succeeded | 1 | 4.0 |
| [scripts/task restarts a task that merged partially](plan_specs/v1/e01-repo-foundation/t18-restart-partial-tasks.yaml) `v1-e01-t18-restart-partial-tasks` | Succeeded | 1 | 3.0 |
| [Command blocks in the docs are safe to paste into zsh](plan_specs/v1/e01-repo-foundation/t19-paste-safe-command-blocks.yaml) `v1-e01-t19-paste-safe-command-blocks` | Succeeded | 1 | 3.0 |
| [A failure that may succeed on retry never shares an exit code with a verdict](plan_specs/v1/e01-repo-foundation/t20-retryable-failures-exit-3.yaml) `v1-e01-t20-retryable-failures-exit-3` | Succeeded | 1 | 3.0 |
| [The storage and OpenCaselist smoke checks run against the installed build](plan_specs/v1/e01-repo-foundation/t21-installed-smoke-stand-ins.yaml) `v1-e01-t21-installed-smoke-stand-ins` | Succeeded | 1 | 4.0 |
| [The real install is the build the rehearsal checked, and doctor answers for all of it](plan_specs/v1/e01-repo-foundation/t22-install-resolves-once.yaml) `v1-e01-t22-install-resolves-once` | Succeeded | 1 | 3.0 |
| [The installed build runs on a Python that uv manages](plan_specs/v1/e01-repo-foundation/t23-managed-python.yaml) `v1-e01-t23-managed-python` | Succeeded | 1 | 2.5 |
| [A partial merge's open items are read from the current session's sections](plan_specs/v1/e01-repo-foundation/t24-partial-open-items-current-session.yaml) `v1-e01-t24-partial-open-items-current-session` | Succeeded | 1 | 1.5 |
| [An unexpected error never prints its message on the command line](plan_specs/v1/e01-repo-foundation/t25-unmodelled-errors-print-no-text.yaml) `v1-e01-t25-unmodelled-errors-print-no-text` | Succeeded | 1 | 1.0 |
| [The manual sweep also opens the back-merge pull request](plan_specs/v1/e01-repo-foundation/t26-dispatch-opens-back-merge.yaml) `v1-e01-t26-dispatch-opens-back-merge` | Succeeded | 1 | 1.5 |
| [The CI test job finishes well inside the five-minute budget](plan_specs/v1/e01-repo-foundation/t27-ci-test-job-within-budget.yaml) `v1-e01-t27-ci-test-job-within-budget` | Succeeded | 1 | 3.0 |
| [scripts/affected_tests.py prints the tests a branch's changes can break](plan_specs/v1/e01-repo-foundation/t28-affected-test-selection.yaml) `v1-e01-t28-affected-test-selection` | Succeeded | 1 | 4.0 |
| [debate_core.testing and debate_core.evidence stop importing more than a caller asks for](plan_specs/v1/e01-repo-foundation/t29-slim-package-reexports.yaml) `v1-e01-t29-slim-package-reexports` | Succeeded | 1 | 3.0 |
| [Tests stop reaching code they do not use: fakes by port, no port re-exports, and a graph option](plan_specs/v1/e01-repo-foundation/t30-test-selection-reach.yaml) `v1-e01-t30-test-selection-reach` | Succeeded | 1 | 4.0 |
| [Repository checks stop flagging true values, and the smoke tests type-check](plan_specs/v1/e01-repo-foundation/t31-repo-check-false-positives.yaml) `v1-e01-t31-repo-check-false-positives` | Succeeded | 1 | 1.0 |
| [Test selection, round three: command registration, quoted words, the root pyproject and the contract suites](plan_specs/v1/e01-repo-foundation/t32-test-selection-reach-round-three.yaml) `v1-e01-t32-test-selection-reach-round-three` | Succeeded | 1 | 3.0 |
| [validate-dev is green again, and a red one is seen](plan_specs/v1/e01-repo-foundation/t34-validate-dev-green-again.yaml) `v1-e01-t34-validate-dev-green-again` | Succeeded | 1 | 3.0 |
| [CI's pyright covers tests/architecture and tests/smoke](plan_specs/v1/e01-repo-foundation/t35-pyright-scope-tests.yaml) `v1-e01-t35-pyright-scope-tests` | Succeeded | 1 | 1.0 |
| [A dev pre-release for a commit dev has moved past with a workflow change is reported superseded, not failed](plan_specs/v1/e01-repo-foundation/t36-prerelease-superseded-commit.yaml) `v1-e01-t36-prerelease-superseded-commit` | Succeeded | 1 | 2.0 |
| [A pull request into dev runs the tests its changes reach; a push to dev and a pull request into main run them all](plan_specs/v1/e01-repo-foundation/t38-ci-affected-tests-on-dev-pull-requests.yaml) `v1-e01-t38-ci-affected-tests-on-dev-pull-requests` | Succeeded | 1 | 3.0 |
| [The container imports each integration in its own factory, and selection follows a command to its factories](plan_specs/v1/e01-repo-foundation/t39-container-builds-integrations-lazily.yaml) `v1-e01-t39-container-builds-integrations-lazily` | Succeeded | 1 | 4.0 |
| [The planted-break check runs the tests nearest a break by what reads it, not by path](plan_specs/v1/e01-repo-foundation/t40-planted-break-nearest-ordering.yaml) `v1-e01-t40-planted-break-nearest-ordering` | Succeeded | 1 | 1.0 |
| [The pull request's smoke tier reads the bundled profiles, as the installed build does](plan_specs/v1/e01-repo-foundation/t41-pr-smoke-reads-the-bundled-profiles.yaml) `v1-e01-t41-pr-smoke-reads-the-bundled-profiles` | Succeeded | 1 | 2.0 |
| [Coverage measured in the test parts and combined, so the push run is never held by one unsplit job](plan_specs/v1/e01-repo-foundation/t42-coverage-measured-in-the-parts.yaml) `v1-e01-t42-coverage-measured-in-the-parts` | Succeeded | 1 | 2.0 |
| [A change to container.py reaches only the tests of the parts it changes](plan_specs/v1/e01-repo-foundation/t43-container-diff-read-part-by-part.yaml) `v1-e01-t43-container-diff-read-part-by-part` | Succeeded | 0 | 2.0 |
| [A test that mentions debate-research inside a longer message is not read as running the app](plan_specs/v1/e01-repo-foundation/t44-cli-mention-in-a-message-is-prose.yaml) `v1-e01-t44-cli-mention-in-a-message-is-prose` | Succeeded | 2 | 1.0 |

#### [E02 — Domain Core: Entities, Ports & Local Persistence](plan_specs/v1/e02-domain-core/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Pydantic domain entities and enums](plan_specs/v1/e02-domain-core/t01-domain-entities.yaml) `v1-e02-t01-domain-entities` | Succeeded | 1 | 8.0 |
| [Repository and provider port interfaces](plan_specs/v1/e02-domain-core/t02-ports.yaml) `v1-e02-t02-ports` | Succeeded | 1 | 6.5 |
| [Local filesystem and SQLite repository implementations](plan_specs/v1/e02-domain-core/t03-local-repositories.yaml) `v1-e02-t03-local-repositories` | Succeeded | 2 | 7.0 |
| [Reusable repository contract test suite](plan_specs/v1/e02-domain-core/t04-repo-contract-tests.yaml) `v1-e02-t04-repo-contract-tests` | Succeeded | 1 | 6.0 |
| [Settings and configuration](plan_specs/v1/e02-domain-core/t05-settings-config.yaml) `v1-e02-t05-settings-config` | Succeeded | 2 | 5.5 |
| [Import-boundary enforcement](plan_specs/v1/e02-domain-core/t06-import-boundary-guard.yaml) `v1-e02-t06-import-boundary-guard` | Succeeded | 2 | 5.5 |

#### [E03 — Evidence Integrity & Verification Engine](plan_specs/v1/e03-evidence-integrity/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Deterministic, versioned text normalization](plan_specs/v1/e03-evidence-integrity/t01-text-normalization.yaml) `v1-e03-t01-text-normalization` | Succeeded | 2 | 9.0 |
| [SHA-256 provenance and snapshot creation](plan_specs/v1/e03-evidence-integrity/t02-hashing-provenance.yaml) `v1-e03-t02-hashing-provenance` | Succeeded | 2 | 6.0 |
| [Span-addressed evidence extraction](plan_specs/v1/e03-evidence-integrity/t03-span-extraction.yaml) `v1-e03-t03-span-extraction` | Succeeded | 1 | 7.5 |
| [EvidenceVerifier and verification statuses](plan_specs/v1/e03-evidence-integrity/t04-verifier.yaml) `v1-e03-t04-verifier` | Succeeded | 1 | 7.0 |
| [Evidence edit policy](plan_specs/v1/e03-evidence-integrity/t05-edit-constraints.yaml) `v1-e03-t05-edit-constraints` | Succeeded | 2 | 5.5 |
| [`debate-research verify` command](plan_specs/v1/e03-evidence-integrity/t06-verify-command.yaml) `v1-e03-t06-verify-command` | Succeeded | 2 | 5.0 |
| [Card omissions and the selection-to-card mapping](plan_specs/v1/e03-evidence-integrity/t07-card-omissions.yaml) `v1-e03-t07-card-omissions` | Succeeded | 2 | 10.0 |


### v1.1 — Caselist evidence store

OpenCaselist archives and OpenEv camp files for HS LD, Policy and PF are imported, deduplicated, parsed into cards and stored in S3 (dev and prod) with manifests; a weekly scheduled sync keeps the store current without a manual download; CardMirror is evaluated and ADR-0014 records the editor decision. E34 sits in this release rather than v1.2 because its client is already built and accepted, because the capture-first split of the scheduled run stands on its own, and because automating a weekly manual chore early is worth doing. ADR-0016 moved it here for a stronger reason that turned out to be false; ADR-0017 records what actually holds.

#### [E29 — Cloud Evidence Store (S3)](plan_specs/v1/e29-cloud-evidence-store/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [AWS account baseline](plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml) `v1-e29-t01-aws-account-baseline` | Succeeded | 0 | 10.0 |
| [Terraform bootstrap and environments](plan_specs/v1/e29-cloud-evidence-store/t02-terraform-bootstrap.yaml) `v1-e29-t02-terraform-bootstrap` | Succeeded | 1 | 7.0 |
| [Evidence buckets and operator access](plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml) `v1-e29-t03-evidence-buckets` | Succeeded | 1 | 9.0 |
| [S3 blob-store adapter](plan_specs/v1/e29-cloud-evidence-store/t04-s3-blob-store.yaml) `v1-e29-t04-s3-blob-store` | Succeeded | 2 | 11.0 |
| [`debate-research store` sync commands](plan_specs/v1/e29-cloud-evidence-store/t05-evidence-sync-cli.yaml) `v1-e29-t05-evidence-sync-cli` | Succeeded | 3 | 11.5 |
| [Removal grants: the scope is tested, and a plan can count versions](plan_specs/v1/e29-cloud-evidence-store/t06-removal-grant-scope-test.yaml) `v1-e29-t06-removal-grant-scope-test` | Succeeded | 1 | 8.0 |
| [A profile missing from the AWS config is a configuration error, not an expired session](plan_specs/v1/e29-cloud-evidence-store/t07-missing-profile-not-retryable.yaml) `v1-e29-t07-missing-profile-not-retryable` | Succeeded | 1 | 1.0 |
| [The takedown preflight refuses the everyday profile before it writes anything](plan_specs/v1/e29-cloud-evidence-store/t08-takedown-preflight-identity.yaml) `v1-e29-t08-takedown-preflight-identity` | InProgress | 1 | 2.0 |
| [Loose ends in how store errors are classified, worded and wrapped](plan_specs/v1/e29-cloud-evidence-store/t09-store-error-loose-ends.yaml) `v1-e29-t09-store-error-loose-ends` | Succeeded | 1 | 2.0 |
| [The retirement rule reaches empty objects, the tagging grant names its one tag, and the module's failures print](plan_specs/v1/e29-cloud-evidence-store/t10-retention-rule-and-grant-loose-ends.yaml) `v1-e29-t10-retention-rule-and-grant-loose-ends` | Pending | 1 | 3.0 |
| [store sync says why it skipped what it skipped](plan_specs/v1/e29-cloud-evidence-store/t11-store-sync-skip-reasons.yaml) `v1-e29-t11-store-sync-skip-reasons` | Succeeded | 1 | 2.0 |
| [store sync stops moving the parsed store, which caselist parse --publish publishes](plan_specs/v1/e29-cloud-evidence-store/t12-store-sync-skips-parsed.yaml) `v1-e29-t12-store-sync-skips-parsed` | Succeeded | 1 | 2.0 |
| [store sync reports a stale parsed copy without needing a blob prefix](plan_specs/v1/e29-cloud-evidence-store/t13-stale-parsed-note-without-blob-prefix.yaml) `v1-e29-t13-stale-parsed-note-without-blob-prefix` | Succeeded | 1 | 1.0 |

#### [E30 — Caselist Evidence Ingestion](plan_specs/v1/e30-caselist-ingestion/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Caselist and OpenEv data-use policy](plan_specs/v1/e30-caselist-ingestion/t01-caselist-data-use-policy.yaml) `v1-e30-t01-caselist-data-use-policy` | Succeeded | 0 | 9.0 |
| [Caselist domain model](plan_specs/v1/e30-caselist-ingestion/t02-caselist-domain-model.yaml) `v1-e30-t02-caselist-domain-model` | Succeeded | 2 | 7.0 |
| [Weekly archive importer](plan_specs/v1/e30-caselist-ingestion/t03-archive-importer.yaml) `v1-e30-t03-archive-importer` | Succeeded | 4 | 15.0 |
| [OpenEv camp-file importer](plan_specs/v1/e30-caselist-ingestion/t04-openev-importer.yaml) `v1-e30-t04-openev-importer` | Succeeded | 1 | 8.0 |
| [Publish sources and manifests to S3](plan_specs/v1/e30-caselist-ingestion/t05-caselist-publish.yaml) `v1-e30-t05-caselist-publish` | Succeeded | 2 | 9.0 |
| [Initial caselist and camp-file backfill](plan_specs/v1/e30-caselist-ingestion/t06-initial-backfill.yaml) `v1-e30-t06-initial-backfill` | Succeeded | 3 | 5.0 |
| [Source removal and suppression list](plan_specs/v1/e30-caselist-ingestion/t07-source-removal.yaml) `v1-e30-t07-source-removal` | Succeeded | 2 | 12.5 |
| [Importer metadata defects found by the backfill](plan_specs/v1/e30-caselist-ingestion/t08-import-metadata-defects.yaml) `v1-e30-t08-import-metadata-defects` | Succeeded | 3 | 7.0 |
| [A removal leaves no removed bytes in the inbox](plan_specs/v1/e30-caselist-ingestion/t09-removal-purges-inbox.yaml) `v1-e30-t09-removal-purges-inbox` | Succeeded | 2 | 6.0 |
| [caselist status reports noncurrent versions a removal left behind](plan_specs/v1/e30-caselist-ingestion/t10-removal-docstrings-and-residue.yaml) `v1-e30-t10-removal-docstrings-and-residue` | Succeeded | 1 | 2.0 |
| [A removal also takes down later uploads at the removed path](plan_specs/v1/e30-caselist-ingestion/t11-removal-covers-later-uploads.yaml) `v1-e30-t11-removal-covers-later-uploads` | Succeeded | 2 | 3.0 |
| [caselist status tells a manifest mismatch from a source mismatch](plan_specs/v1/e30-caselist-ingestion/t12-status-names-manifest-mismatch.yaml) `v1-e30-t12-status-names-manifest-mismatch` | Succeeded | 1 | 1.0 |
| [A removed caselist path holds the uploads that arrive after the removal](plan_specs/v1/e30-caselist-ingestion/t13-removed-path-holds-caselist-uploads.yaml) `v1-e30-t13-removed-path-holds-caselist-uploads` | Succeeded | 1 | 4.0 |
| [A camp file is identified by its upstream record, and a camp path can be withdrawn on its own](plan_specs/v1/e30-caselist-ingestion/t14-camp-path-identity.yaml) `v1-e30-t14-camp-path-identity` | InProgress | 1 | 3.0 |
| [caselist status reports manifest and aggregate versions older than a removal](plan_specs/v1/e30-caselist-ingestion/t15-manifest-and-aggregate-residue.yaml) `v1-e30-t15-manifest-and-aggregate-residue` | Succeeded | 1 | 3.0 |
| [The removal plan names holders correctly in every case](plan_specs/v1/e30-caselist-ingestion/t16-removal-output-names-holders.yaml) `v1-e30-t16-removal-output-names-holders` | Succeeded | 1 | 2.0 |
| [No text calls a weekly archive cumulative, and import ordering is checked against the window model](plan_specs/v1/e30-caselist-ingestion/t17-weekly-window-wording-and-ordering.yaml) `v1-e30-t17-weekly-window-wording-and-ordering` | Succeeded | 1 | 3.0 |
| [A weekly imported late re-measures the weeks after it, and a re-import needs no flag](plan_specs/v1/e30-caselist-ingestion/t18-late-imports-re-measure-later-manifests.yaml) `v1-e30-t18-late-imports-re-measure-later-manifests` | Succeeded | 1 | 4.0 |
| [Removal residue the status reports can always be cleared, and says whose it is](plan_specs/v1/e30-caselist-ingestion/t19-residue-clearing-gaps.yaml) `v1-e30-t19-residue-clearing-gaps` | Succeeded | 4 | 3.0 |
| [Loose ends in what a removal plan prints and how it decides what to drop](plan_specs/v1/e30-caselist-ingestion/t20-removal-output-loose-ends.yaml) `v1-e30-t20-removal-output-loose-ends` | Succeeded | 1 | 2.0 |
| [Loose ends of the removed-path hold: status, the publisher and the inbox](plan_specs/v1/e30-caselist-ingestion/t21-held-path-loose-ends.yaml) `v1-e30-t21-held-path-loose-ends` | Succeeded | 1 | 3.0 |
| [A held path's bytes and skipped rows never reach the bucket](plan_specs/v1/e30-caselist-ingestion/t22-held-rows-publish-nothing.yaml) `v1-e30-t22-held-rows-publish-nothing` | Succeeded | 1 | 3.0 |
| [Held digests are remembered once the copy is gone, and a manifest write survives a power cut](plan_specs/v1/e30-caselist-ingestion/t23-held-digests-and-manifest-fsync.yaml) `v1-e30-t23-held-digests-and-manifest-fsync` | Succeeded | 1 | 3.0 |
| [caselist status fails on every removal left unfinished, and reports a held digest the re-run has not listed](plan_specs/v1/e30-caselist-ingestion/t24-status-residue-and-held-digests.yaml) `v1-e30-t24-status-residue-and-held-digests` | Succeeded | 2 | 4.0 |
| [store sync pushes no manifest the publisher withholds, and junk beside a held link does not keep its row](plan_specs/v1/e30-caselist-ingestion/t25-store-sync-withholding.yaml) `v1-e30-t25-store-sync-withholding` | Succeeded | 1 | 2.0 |
| [A .cmir file is imported as CMIR, and every rename-into-place writer fsyncs its directory](plan_specs/v1/e30-caselist-ingestion/t26-cmir-extension-and-directory-fsync.yaml) `v1-e30-t26-cmir-extension-and-directory-fsync` | Succeeded | 2 | 2.0 |
| [caselist publish, verify, parse and pull panels print a summary, not the whole record](plan_specs/v1/e30-caselist-ingestion/t27-command-panels-print-summaries.yaml) `v1-e30-t27-command-panels-print-summaries` | Succeeded | 1 | 2.0 |
| [The annual purge, as one runbook](plan_specs/v1/e30-caselist-ingestion/t28-annual-purge-runbook.yaml) `v1-e30-t28-annual-purge-runbook` | Succeeded | 1 | 2.0 |
| [A removal lists raw/ and parsed/ again after deleting, and stops incomplete if a version survived](plan_specs/v1/e30-caselist-ingestion/t29-removal-confirms-raw-and-parsed-deletes.yaml) `v1-e30-t29-removal-confirms-raw-and-parsed-deletes` | Succeeded | 1 | 1.0 |
| [Inbox deletions fsync the inbox directory, so a removed archive cannot come back after a power cut](plan_specs/v1/e30-caselist-ingestion/t30-inbox-deletions-fsync-the-directory.yaml) `v1-e30-t30-inbox-deletions-fsync-the-directory` | Succeeded | 0 | 1.0 |
| [The pull keeps OpenEv's own camp word on a camp file's manifest row](plan_specs/v1/e30-caselist-ingestion/t31-openev-camp-word-on-the-manifest-row.yaml) `v1-e30-t31-openev-camp-word-on-the-manifest-row` | Succeeded | 2 | 1.0 |
| [Michigan's three camps are filed apart, as OpenEv files them, so their cards can link](plan_specs/v1/e30-caselist-ingestion/t32-michigan-split-into-openevs-three-camps.yaml) `v1-e30-t32-michigan-split-into-openevs-three-camps` | InProgress | 1 | 2.0 |

#### [E31 — Debate File Parsing](plan_specs/v1/e31-debate-file-parsing/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [CardMirror evaluation and editor decision](plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml) `v1-e31-t01-cardmirror-evaluation` | Succeeded | 1 | 11.5 |
| [Verbatim/CardMirror style profile](plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml) `v1-e31-t02-verbatim-style-profile` | Succeeded | 2 | 13.0 |
| [Debate .docx parser](plan_specs/v1/e31-debate-file-parsing/t03-debate-docx-parser.yaml) `v1-e31-t03-debate-docx-parser` | Succeeded | 2 | 15.0 |
| [Card fingerprints and occurrences](plan_specs/v1/e31-debate-file-parsing/t04-card-fingerprints.yaml) `v1-e31-t04-card-fingerprints` | Succeeded | 1 | 13.0 |
| [Parser accuracy evaluation](plan_specs/v1/e31-debate-file-parsing/t05-parser-eval.yaml) `v1-e31-t05-parser-eval` | InProgress | 1 | 16.0 |
| [Incremental parse pipeline](plan_specs/v1/e31-debate-file-parsing/t06-parse-pipeline.yaml) `v1-e31-t06-parse-pipeline` | Succeeded | 5 | 12.0 |
| [Labeling worksheets survive a spreadsheet round trip](plan_specs/v1/e31-debate-file-parsing/t07-worksheet-round-trip.yaml) `v1-e31-t07-worksheet-round-trip` | Succeeded | 1 | 4.0 |
| [Near-duplicate matching finds short cards and abbreviated disclosures](plan_specs/v1/e31-debate-file-parsing/t08-short-card-recall.yaml) `v1-e31-t08-short-card-recall` | Succeeded | 1 | 5.0 |
| [Parser findings from the first full-corpus parse](plan_specs/v1/e31-debate-file-parsing/t09-first-corpus-parse-findings.yaml) `v1-e31-t09-first-corpus-parse-findings` | Succeeded | 1 | 4.0 |
| [The weekly aggregate rebuild costs what the week added, not the whole store](plan_specs/v1/e31-debate-file-parsing/t10-incremental-aggregate-rebuild.yaml) `v1-e31-t10-incremental-aggregate-rebuild` | Pending | 1 | 6.0 |
| [Copies split apart by the short-body rule, and long bodies merged through a fragment](plan_specs/v1/e31-debate-file-parsing/t11-long-card-splits-and-fragment-merges.yaml) `v1-e31-t11-long-card-splits-and-fragment-merges` | Succeeded | 2 | 5.0 |
| [Cites the parser misses or misreads](plan_specs/v1/e31-debate-file-parsing/t12-cite-detection.yaml) `v1-e31-t12-cite-detection` | Succeeded | 1 | 5.0 |
| [Split a cite from its words when a card or wiki entry is one paragraph](plan_specs/v1/e31-debate-file-parsing/t13-one-paragraph-cards-and-wiki-entries.yaml) `v1-e31-t13-one-paragraph-cards-and-wiki-entries` | Pending | 1 | 6.0 |
| [A card with no tag has no tag in memory and in every output](plan_specs/v1/e31-debate-file-parsing/t14-card-tag-optional.yaml) `v1-e31-t14-card-tag-optional` | Succeeded | 2 | 2.0 |
| [The zip guard judges only the parts it reads, and exporter quirks are decided](plan_specs/v1/e31-debate-file-parsing/t15-zip-guard-and-exporter-quirks.yaml) `v1-e31-t15-zip-guard-and-exporter-quirks` | Succeeded | 1 | 2.0 |
| [Superseded parsed-store version directories are retired, locally and in both buckets](plan_specs/v1/e31-debate-file-parsing/t16-version-directory-retention.yaml) `v1-e31-t16-version-directory-retention` | InProgress | 1 | 3.0 |
| [A transient parse failure is retried, and one data directory publishes a bucket's parsed store](plan_specs/v1/e31-debate-file-parsing/t17-parse-retries-and-one-publisher.yaml) `v1-e31-t17-parse-retries-and-one-publisher` | Pending | 1 | 2.0 |
| [The parser evaluation's labels are corrected one keypress per row, in a local page](plan_specs/v1/e31-debate-file-parsing/t18-click-through-labeller.yaml) `v1-e31-t18-click-through-labeller` | Succeeded | 1 | 5.0 |
| [The cite shapes the parser still misses, counted first](plan_specs/v1/e31-debate-file-parsing/t19-remaining-cite-shapes.yaml) `v1-e31-t19-remaining-cite-shapes` | Succeeded | 1 | 6.0 |
| [Long cuts join the one cluster that holds them, and the matching limits are set from samples](plan_specs/v1/e31-debate-file-parsing/t20-long-cuts-and-limits.yaml) `v1-e31-t20-long-cuts-and-limits` | Succeeded | 2 | 6.0 |
| [Measure cluster shapes, and ask a person only about the pairs a rule cannot decide](plan_specs/v1/e31-debate-file-parsing/t21-cluster-shapes-and-sampler.yaml) `v1-e31-t21-cluster-shapes-and-sampler` | Succeeded | 1 | 4.0 |
| [Bodies too long to be one card, and two cards stored as one](plan_specs/v1/e31-debate-file-parsing/t22-card-boundaries.yaml) `v1-e31-t22-card-boundaries` | Succeeded | 2 | 6.0 |
| [In-round markers kept in a card's evidence text](plan_specs/v1/e31-debate-file-parsing/t23-in-round-markers.yaml) `v1-e31-t23-in-round-markers` | Pending | 2 | 3.0 |
| [A bold tag above a cite is read as the card's tag](plan_specs/v1/e31-debate-file-parsing/t24-bold-tag-above-bracketed-cite.yaml) `v1-e31-t24-bold-tag-above-bracketed-cite` | Succeeded | 1 | 3.0 |
| [The labeller warns before a card is lost, and import refuses a file already corrected](plan_specs/v1/e31-debate-file-parsing/t25-labeller-safeguards.yaml) `v1-e31-t25-labeller-safeguards` | Pending | 1 | 3.0 |
| [parse --publish sends nothing of a held upload](plan_specs/v1/e31-debate-file-parsing/t26-held-upload-parsed-publish.yaml) `v1-e31-t26-held-upload-parsed-publish` | Succeeded | 1 | 2.0 |
| [The parse time-limit test does not depend on the machine's load](plan_specs/v1/e31-debate-file-parsing/t27-parse-time-limit-test.yaml) `v1-e31-t27-parse-time-limit-test` | Pending | 1 | 1.0 |
| [What the cautious cite rules leave, and a short cite behind a first name](plan_specs/v1/e31-debate-file-parsing/t28-cite-rules-leftovers.yaml) `v1-e31-t28-cite-rules-leftovers` | Pending | 1 | 3.0 |
| [Card matching recovers two kinds of pair it now keeps apart](plan_specs/v1/e31-debate-file-parsing/t29-card-matching-recall.yaml) `v1-e31-t29-card-matching-recall` | Pending | 1 | 4.0 |
| [Publish the parsed store without rebuilding it](plan_specs/v1/e31-debate-file-parsing/t30-parsed-store-publish-only.yaml) `v1-e31-t30-parsed-store-publish-only` | Succeeded | 1 | 2.0 |
| [Where the labelled evaluation's missed cites, tags and highlights go, counted before any rule](plan_specs/v1/e31-debate-file-parsing/t31-labelled-evaluation-gaps.yaml) `v1-e31-t31-labelled-evaluation-gaps` | InProgress | 1 | 5.0 |
| [A tag with a word left unbolded, above a cite, counted before any rule](plan_specs/v1/e31-debate-file-parsing/t32-bold-in-part-tags.yaml) `v1-e31-t32-bold-in-part-tags` | Pending | 1 | 3.0 |
| [A pointer to another card (`<<AUTHOR 'YY FOR REFERENCE>>`) is never promoted to a cite](plan_specs/v1/e31-debate-file-parsing/t33-reference-pointers-are-not-cites.yaml) `v1-e31-t33-reference-pointers-are-not-cites` | Pending | 1 | 1.0 |

#### [E34 — Scheduled Caselist Sync](plan_specs/v1/e34-caselist-sync/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [OpenCaselist API client](plan_specs/v1/e34-caselist-sync/t01-caselist-api-client.yaml) `v1-e34-t01-caselist-api-client` | Succeeded | 2 | 11.0 |
| [Weekly scheduled sync](plan_specs/v1/e34-caselist-sync/t02-scheduled-sync.yaml) `v1-e34-t02-scheduled-sync` | Succeeded | 4 | 11.0 |
| [Sync run log and staleness warnings](plan_specs/v1/e34-caselist-sync/t03-sync-monitoring.yaml) `v1-e34-t03-sync-monitoring` | Succeeded | 1 | 9.0 |
| [Periodic full-archive refresh](plan_specs/v1/e34-caselist-sync/t04-full-archive-refresh.yaml) `v1-e34-t04-full-archive-refresh` | Succeeded | 2 | 6.5 |
| [Install and enable the weekly agent](plan_specs/v1/e34-caselist-sync/t05-enable-schedule.yaml) `v1-e34-t05-enable-schedule` | Succeeded | 6 | 1.5 |
| [Defects found by operating the sync](plan_specs/v1/e34-caselist-sync/t06-sync-defects.yaml) `v1-e34-t06-sync-defects` | Succeeded | 1 | 7.0 |
| [The sync does not re-download a file it has been told to remove](plan_specs/v1/e34-caselist-sync/t07-suppressed-downloads.yaml) `v1-e34-t07-suppressed-downloads` | Succeeded | 2 | 7.0 |
| [A camp file uploaded again upstream is fetched](plan_specs/v1/e34-caselist-sync/t08-revised-camp-files.yaml) `v1-e34-t08-revised-camp-files` | Succeeded | 1 | 4.0 |
| [Retire the legacy download ledger](plan_specs/v1/e34-caselist-sync/t09-retire-legacy-ledger.yaml) `v1-e34-t09-retire-legacy-ledger` | Succeeded | 1 | 2.0 |
| [The weekly agent runs nothing from a git checkout](plan_specs/v1/e34-caselist-sync/t10-agent-outside-checkout.yaml) `v1-e34-t10-agent-outside-checkout` | Succeeded | 1 | 2.0 |
| [Imported downloads leave the inbox](plan_specs/v1/e34-caselist-sync/t11-inbox-retention.yaml) `v1-e34-t11-inbox-retention` | Succeeded | 1 | 4.0 |
| [The pull summary names a camp download by id, never by title](plan_specs/v1/e34-caselist-sync/t12-summary-names-no-camp-file.yaml) `v1-e34-t12-summary-names-no-camp-file` | Succeeded | 1 | 1.5 |
| [A pull stage that fails on a retryable cause ends the run with exit 3](plan_specs/v1/e34-caselist-sync/t13-pull-stage-failure-classes.yaml) `v1-e34-t13-pull-stage-failure-classes` | Succeeded | 2 | 4.0 |
| [A camp file already in the inbox is held if its path was removed](plan_specs/v1/e34-caselist-sync/t14-removed-path-hold-for-inbox-copies.yaml) `v1-e34-t14-removed-path-hold-for-inbox-copies` | Succeeded | 1 | 1.5 |
| [A camp release of junk alone leaves the inbox once it is handled](plan_specs/v1/e34-caselist-sync/t15-junk-release-leaves-inbox.yaml) `v1-e34-t15-junk-release-leaves-inbox` | Succeeded | 1 | 1.0 |
| [The dry run's download plan names no path on the operator's machine](plan_specs/v1/e34-caselist-sync/t16-dry-run-names-no-home-path.yaml) `v1-e34-t16-dry-run-names-no-home-path` | Succeeded | 1 | 0.5 |
| [The weekly pull parses the sources it imported](plan_specs/v1/e34-caselist-sync/t17-pull-parses-new-sources.yaml) `v1-e34-t17-pull-parses-new-sources` | InProgress | 2 | 3.0 |
| [A publish stopped by an expired session still owes every snapshot it did not finish](plan_specs/v1/e34-caselist-sync/t18-publish-owes-every-unpublished-snapshot.yaml) `v1-e34-t18-publish-owes-every-unpublished-snapshot` | Succeeded | 1 | 2.0 |
| [Unreadable local files fail a stage, and a notification says whether a failure is transient](plan_specs/v1/e34-caselist-sync/t19-unreadable-local-files-and-notification-codes.yaml) `v1-e34-t19-unreadable-local-files-and-notification-codes` | Succeeded | 1 | 3.0 |
| [After a login, the parsed store publishes without a second rebuild when nothing was removed](plan_specs/v1/e34-caselist-sync/t20-parsed-store-publish-after-login.yaml) `v1-e34-t20-parsed-store-publish-after-login` | Pending | 2 | 4.0 |
| [The parse stage holds the run lock and has a time budget](plan_specs/v1/e34-caselist-sync/t21-parse-stage-bounds.yaml) `v1-e34-t21-parse-stage-bounds` | Pending | 1 | 2.0 |
| [A weekly run that cannot reach its bucket is recorded and announced, and the profile is checked before install](plan_specs/v1/e34-caselist-sync/t22-refusal-to-start-is-recorded.yaml) `v1-e34-t22-refusal-to-start-is-recorded` | Succeeded | 2 | 3.0 |
| [Loose ends in the weekly sync's findings, records and notifications](plan_specs/v1/e34-caselist-sync/t23-sync-loose-ends.yaml) `v1-e34-t23-sync-loose-ends` | Succeeded | 1 | 3.0 |
| [The agent's installer checks what it can, and never changes an agent's environment by default](plan_specs/v1/e34-caselist-sync/t24-agent-install-loose-ends.yaml) `v1-e34-t24-agent-install-loose-ends` | Succeeded | 1 | 3.0 |
| [A reinstall keeps the agent's schedule and options, and doctor names a takedown profile's environment](plan_specs/v1/e34-caselist-sync/t25-reinstall-keeps-every-setting.yaml) `v1-e34-t25-reinstall-keeps-every-setting` | Succeeded | 2 | 2.0 |
| [A drifted snapshot is owed again, and the banner and run list say what is pending](plan_specs/v1/e34-caselist-sync/t26-pending-work-and-banner-words.yaml) `v1-e34-t26-pending-work-and-banner-words` | Succeeded | 2 | 3.0 |
| [The wrapper exports no AWS_PROFILE, and --check-launchd refuses options it ignores](plan_specs/v1/e34-caselist-sync/t27-wrapper-and-check-launchd-options.yaml) `v1-e34-t27-wrapper-and-check-launchd-options` | Succeeded | 1 | 1.0 |
| [Publish-stage loose ends: a cut-short report check, the manifest count, and a report-only outcome](plan_specs/v1/e34-caselist-sync/t28-publish-stage-loose-ends.yaml) `v1-e34-t28-publish-stage-loose-ends` | Succeeded | 1 | 2.0 |
| [An older build never rewrites or publishes an occurrence table stamped with a newer fingerprint version](plan_specs/v1/e34-caselist-sync/t29-newer-fingerprint-table-guard.yaml) `v1-e34-t29-newer-fingerprint-table-guard` | Succeeded | 1 | 2.0 |
| [doctor says when a store the weekly run will index has never been parsed](plan_specs/v1/e34-caselist-sync/t30-doctor-unparsed-store.yaml) `v1-e34-t30-doctor-unparsed-store` | Succeeded | 0 | 1.0 |
| [The weekly run names caselist parse --publish-only where a publish-only finishes the stage](plan_specs/v1/e34-caselist-sync/t31-pull-fix-text-publish-only.yaml) `v1-e34-t31-pull-fix-text-publish-only` | Succeeded | 2 | 2.0 |
| [The staleness hook reports a caselist stale when its latest run failed](plan_specs/v1/e34-caselist-sync/t32-failed-run-reads-stale.yaml) `v1-e34-t32-failed-run-reads-stale` | Succeeded | 1 | 2.0 |
| [A keychain failure under launchd names its cause, and clearing a token already gone is no error](plan_specs/v1/e34-caselist-sync/t33-keychain-errors-named.yaml) `v1-e34-t33-keychain-errors-named` | Succeeded | 1 | 2.0 |
| [Earlier seasons' complete archives, from 2021-22 on, imported and parsed as backfiles](plan_specs/v1/e34-caselist-sync/t34-backfile-seasons-import.yaml) `v1-e34-t34-backfile-seasons-import` | Succeeded | 1 | 4.0 |
| [A Mac run stopped for a missing token says to log in again](plan_specs/v1/e34-caselist-sync/t35-token-missing-hint-on-the-mac.yaml) `v1-e34-t35-token-missing-hint-on-the-mac` | Succeeded | 1 | 0.5 |
| [A Mac run stopped for an unreadable token says to log out and log in again](plan_specs/v1/e34-caselist-sync/t36-token-unreadable-hint-on-the-mac.yaml) `v1-e34-t36-token-unreadable-hint-on-the-mac` | Succeeded | 1 | 0.5 |
| [A listed camp file is not taken as already imported because a file of another camp shares its name](plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml) `v1-e34-t37-listed-camp-file-with-a-hand-imported-name` | Pending | 1 | 1.0 |


### v1.2 — Argument landscape & file building

Weekly argument-landscape reports show which positions are being read and with which cards; coaches build Verbatim/CardMirror-compatible files from disclosed cards with provenance. The scheduled sync moved to v1.1 under ADR-0017; what this release adds to it is the parse and landscape stages of the same weekly run.

#### [E05 — Model Router & Structured LLM Contracts](plan_specs/v1/e05-model-router/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [ModelRouter interface and routing config](plan_specs/v1/e05-model-router/t01-model-router-port.yaml) `v1-e05-t01-model-router-port` | Succeeded | 1 | 9.0 |
| [Amazon Bedrock adapter](plan_specs/v1/e05-model-router/t02-bedrock-adapter.yaml) `v1-e05-t02-bedrock-adapter` | Succeeded | 1 | 10.0 |
| [Deterministic fake and record/replay models](plan_specs/v1/e05-model-router/t03-fake-replay-models.yaml) `v1-e05-t03-fake-replay-models` | Succeeded | 1 | 9.0 |
| [Versioned prompt registry](plan_specs/v1/e05-model-router/t04-prompt-registry.yaml) `v1-e05-t04-prompt-registry` | Succeeded | 1 | 8.0 |
| [Structured output validation and repair](plan_specs/v1/e05-model-router/t05-structured-output-validation.yaml) `v1-e05-t05-structured-output-validation` | Succeeded | 2 | 7.0 |
| [CardSelection / MarkupSpan contract and prompts](plan_specs/v1/e05-model-router/t06-card-selection-contract.yaml) `v1-e05-t06-card-selection-contract` | Succeeded | 3 | 12.0 |
| [Token/cost telemetry and budgets](plan_specs/v1/e05-model-router/t07-usage-telemetry.yaml) `v1-e05-t07-usage-telemetry` | Succeeded | 1 | 8.0 |
| [A profile that may call Bedrock, and the model access its first call needs](plan_specs/v1/e05-model-router/t08-bedrock-invoke-access.yaml) `v1-e05-t08-bedrock-invoke-access` | Succeeded | 1 | 4.0 |
| [Replay tolerates a new optional parameter, a refused model call is not retryable, and doctor can check the routing file](plan_specs/v1/e05-model-router/t09-replay-and-model-exit-codes.yaml) `v1-e05-t09-replay-and-model-exit-codes` | Succeeded | 2 | 3.0 |
| [Record mode keeps an invalid answer, so a repaired call can be recorded live](plan_specs/v1/e05-model-router/t10-record-mode-keeps-invalid-answers.yaml) `v1-e05-t10-record-mode-keeps-invalid-answers` | Succeeded | 2 | 2.0 |
| [A prompt may set its own effort, so a classifier need not think at the route's default](plan_specs/v1/e05-model-router/t11-per-prompt-effort.yaml) `v1-e05-t11-per-prompt-effort` | Pending | 1 | 2.0 |
| [An installed build carries config/model_pricing.yaml beside the routing files](plan_specs/v1/e05-model-router/t12-installed-build-carries-model-pricing.yaml) `v1-e05-t12-installed-build-carries-model-pricing` | Succeeded | 1 | 1.0 |
| [Dev routes to Claude models this account can call while the 5.5 quotas are held at zero](plan_specs/v1/e05-model-router/t13-dev-routes-to-callable-claude-models.yaml) `v1-e05-t13-dev-routes-to-callable-claude-models` | Succeeded | 1 | 2.0 |
| [A cheaper model for the high-volume route, chosen by the coach-labelled evaluation](plan_specs/v1/e05-model-router/t14-cheaper-model-for-high-volume-evaluated-first.yaml) `v1-e05-t14-cheaper-model-for-high-volume-evaluated-first` | Pending | 2 | 3.0 |
| [A monthly model budget beside the daily one, at the coach's $50 ceiling](plan_specs/v1/e05-model-router/t15-monthly-model-budget.yaml) `v1-e05-t15-monthly-model-budget` | Succeeded | 1 | 2.0 |
| [An AWS budget alarm on the account's model spend, $100 a month with a first notice at $50](plan_specs/v1/e05-model-router/t16-bedrock-budget-alarm.yaml) `v1-e05-t16-bedrock-budget-alarm` | Succeeded | 1 | 2.0 |
| [Dev back on the 5.5 models, and prod's Bedrock grant applied, once the quotas are restored](plan_specs/v1/e05-model-router/t17-switch-back-to-the-5-5-models.yaml) `v1-e05-t17-switch-back-to-the-5-5-models` | Blocked | 3 | 2.0 |
| [The cost allocation tags are active by Terraform, so the budgets that filter on them never read zero again](plan_specs/v1/e05-model-router/t18-cost-allocation-tags-in-terraform.yaml) `v1-e05-t18-cost-allocation-tags-in-terraform` | Succeeded | 1 | 1.0 |
| [The cost allocation tags' import blocks are removed once both tags are in state](plan_specs/v1/e05-model-router/t19-cost-allocation-tag-imports-removed.yaml) `v1-e05-t19-cost-allocation-tag-imports-removed` | Succeeded | 1 | 0.5 |

#### [E32 — Argument Landscape Reports](plan_specs/v1/e32-argument-landscape/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Topic position taxonomies](plan_specs/v1/e32-argument-landscape/t01-position-taxonomy.yaml) `v1-e32-t01-position-taxonomy` | Succeeded | 1 | 14.0 |
| [Position classification](plan_specs/v1/e32-argument-landscape/t02-position-classification.yaml) `v1-e32-t02-position-classification` | Succeeded | 2 | 8.5 |
| [Weekly landscape report](plan_specs/v1/e32-argument-landscape/t03-landscape-report.yaml) `v1-e32-t03-landscape-report` | Succeeded | 4 | 12.0 |
| [Trends and per-school views](plan_specs/v1/e32-argument-landscape/t04-trend-and-school-views.yaml) `v1-e32-t04-trend-and-school-views` | Succeeded | 1 | 9.0 |
| [`debate-research landscape` command](plan_specs/v1/e32-argument-landscape/t05-landscape-cli.yaml) `v1-e32-t05-landscape-cli` | Succeeded | 2 | 10.0 |
| [LD de-extinction position taxonomy](plan_specs/v1/e32-argument-landscape/t06-ld-de-extinction-taxonomy.yaml) `v1-e32-t06-ld-de-extinction-taxonomy` | Pending | 1 | 3.0 |
| [Model classification of what headings cannot place](plan_specs/v1/e32-argument-landscape/t07-model-classification-stage.yaml) `v1-e32-t07-model-classification-stage` | InProgress | 3 | 8.0 |
| [A released position id is never deleted or reused](plan_specs/v1/e32-argument-landscape/t08-released-position-ids.yaml) `v1-e32-t08-released-position-ids` | Succeeded | 1 | 3.0 |
| [Each Policy affirmative round's plan, counted first, so the landscape names what affs read](plan_specs/v1/e32-argument-landscape/t09-policy-plan-texts.yaml) `v1-e32-t09-policy-plan-texts` | Succeeded | 1 | 5.0 |
| [Impact cards per DA and advantage in the landscape report](plan_specs/v1/e32-argument-landscape/t10-impact-cards-per-position.yaml) `v1-e32-t10-impact-cards-per-position` | Succeeded | 1 | 4.0 |
| [Counterplan texts, kritik alternatives and overviews in the landscape report](plan_specs/v1/e32-argument-landscape/t11-negative-analytic-texts.yaml) `v1-e32-t11-negative-analytic-texts` | Succeeded | 2 | 5.0 |
| [The landscape command names the seven-file bundle and counts its trends and schools](plan_specs/v1/e32-argument-landscape/t12-landscape-cli-seven-files.yaml) `v1-e32-t12-landscape-cli-seven-files` | Succeeded | 1 | 1.0 |
| [A removal and the annual purge reach the landscape bundles' school views](plan_specs/v1/e32-argument-landscape/t13-removal-reaches-landscape-school-views.yaml) `v1-e32-t13-removal-reaches-landscape-school-views` | Succeeded | 2 | 3.0 |
| [Each DA's and advantage's scenarios and link chain, and what each impact card runs through](plan_specs/v1/e32-argument-landscape/t14-scenarios-and-link-chains.yaml) `v1-e32-t14-scenarios-and-link-chains` | Succeeded | 1 | 5.0 |
| [The advantages each affirmative's teams read](plan_specs/v1/e32-argument-landscape/t15-advantages-per-aff.yaml) `v1-e32-t15-advantages-per-aff` | Succeeded | 1 | 3.0 |
| [An advantage counterplan's planks, and the advantage each one solves](plan_specs/v1/e32-argument-landscape/t16-advantage-cp-planks.yaml) `v1-e32-t16-advantage-cp-planks` | Succeeded | 1 | 4.0 |
| [Kritikal affirmatives identified, not left among the rounds with no identified aff](plan_specs/v1/e32-argument-landscape/t17-kritikal-affirmatives.yaml) `v1-e32-t17-kritikal-affirmatives` | Succeeded | 2 | 4.0 |
| [The school view by position: every team that reads each DA, CP and K, with its caselist page](plan_specs/v1/e32-argument-landscape/t18-school-view-by-position.yaml) `v1-e32-t18-school-view-by-position` | Succeeded | 1 | 2.0 |
| [A dry run's scan refusal says nothing was written and gives the publish command](plan_specs/v1/e32-argument-landscape/t19-dry-run-scan-refusal-wording.yaml) `v1-e32-t19-dry-run-scan-refusal-wording` | Succeeded | 1 | 1.0 |
| [report.md in two halves: every affirmative section together, then every negative one](plan_specs/v1/e32-argument-landscape/t20-report-sides-together.yaml) `v1-e32-t20-report-sides-together` | Succeeded | 1 | 2.0 |
| [A local text classifier for the cards headings cannot place, compared before anything is wired](plan_specs/v1/e32-argument-landscape/t21-local-classifier-comparison.yaml) `v1-e32-t21-local-classifier-comparison` | Succeeded | 1 | 5.0 |
| [A coach-edited scenario vocabulary per DA and advantage](plan_specs/v1/e32-argument-landscape/t22-scenario-vocabulary.yaml) `v1-e32-t22-scenario-vocabulary` | Succeeded | 2 | 3.0 |
| [Team links on a school's page, as on a position's](plan_specs/v1/e32-argument-landscape/t23-school-page-team-links.yaml) `v1-e32-t23-school-page-team-links` | Succeeded | 1 | 1.0 |
| [Policy affs whose plan text has no label, identified by the plan or the advantages](plan_specs/v1/e32-argument-landscape/t24-unlabelled-plan-affs.yaml) `v1-e32-t24-unlabelled-plan-affs` | Succeeded | 2 | 4.0 |
| [What each impact runs through, named in words a debater uses](plan_specs/v1/e32-argument-landscape/t25-readable-impact-chains.yaml) `v1-e32-t25-readable-impact-chains` | Succeeded | 1 | 3.0 |
| [The review queue ordered by the local proxy model, which places nothing](plan_specs/v1/e32-argument-landscape/t26-review-queue-proxy-ordering.yaml) `v1-e32-t26-review-queue-proxy-ordering` | Succeeded | 1 | 3.0 |
| [Branches and mechanisms in the DA sections, counted first](plan_specs/v1/e32-argument-landscape/t27-branches-and-mechanisms-counted-first.yaml) `v1-e32-t27-branches-and-mechanisms-counted-first` | Succeeded | 2 | 4.0 |
| [Tags quoted in the impact and link-chain tables, held to the report's withholding, counted first](plan_specs/v1/e32-argument-landscape/t28-tags-in-the-tables-held-to-withholding.yaml) `v1-e32-t28-tags-in-the-tables-held-to-withholding` | Succeeded | 1 | 2.0 |
| [Harms headings counted under Impact, the word the coach's debaters use](plan_specs/v1/e32-argument-landscape/t29-harms-headings-under-impact.yaml) `v1-e32-t29-harms-headings-under-impact` | Succeeded | 1 | 2.0 |
| [A dry run fills the plan-text and analytic-text caches, so the first report after a parser bump reads sources once](plan_specs/v1/e32-argument-landscape/t30-dry-run-fills-the-text-caches.yaml) `v1-e32-t30-dry-run-fills-the-text-caches` | Succeeded | 0 | 1.0 |
| [Model cassettes name their caselist, so one season's recordings can be deleted alone](plan_specs/v1/e32-argument-landscape/t31-cassettes-filed-by-caselist.yaml) `v1-e32-t31-cassettes-filed-by-caselist` | Succeeded | 0 | 2.0 |
| [A landscape model stage stopped by throttling ends as retryable, not as a verdict](plan_specs/v1/e32-argument-landscape/t32-throttled-model-stage-is-retryable.yaml) `v1-e32-t32-throttled-model-stage-is-retryable` | Succeeded | 0 | 1.0 |
| [A throttled landscape evaluation exits as retryable, and a throttled stop says how long to wait](plan_specs/v1/e32-argument-landscape/t33-landscape-evaluate-retry-exit.yaml) `v1-e32-t33-landscape-evaluate-retry-exit` | Succeeded | 1 | 1.0 |
| [A command lists and deletes one caselist's model cassettes, and the annual purge calls it](plan_specs/v1/e32-argument-landscape/t34-landscape-cassettes-command.yaml) `v1-e32-t34-landscape-cassettes-command` | Succeeded | 1 | 1.0 |
| [A CP text the landscape shows is whole: a text ending in a colon shows its planks, and a text split across paragraphs is joined](plan_specs/v1/e32-argument-landscape/t35-cp-texts-shown-whole.yaml) `v1-e32-t35-cp-texts-shown-whole` | Succeeded | 1 | 3.0 |
| [landscape cassettes gains a smoke check and a removal form that reaches every copy](plan_specs/v1/e32-argument-landscape/t36-landscape-cassettes-smoke-check-and-removal-form.yaml) `v1-e32-t36-landscape-cassettes-smoke-check-and-removal-form` | Succeeded | 1 | 2.0 |
| [The model-use gate reads open question 4 from the policy's open-questions table, not the first row numbered 4](plan_specs/v1/e32-argument-landscape/t37-model-use-gate-reads-the-open-questions-table.yaml) `v1-e32-t37-model-use-gate-reads-the-open-questions-table` | Succeeded | 1 | 0.5 |
| [The landscape smoke check reads the review queue's order line and a dry run's scan refusal](plan_specs/v1/e32-argument-landscape/t38-landscape-smoke-checks-order-line-and-dry-run-refusal.yaml) `v1-e32-t38-landscape-smoke-checks-order-line-and-dry-run-refusal` | Pending | 2 | 1.0 |

#### [E33 — Evidence File Builder](plan_specs/v1/e33-file-builder/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [File recipe format](plan_specs/v1/e33-file-builder/t01-file-recipe-format.yaml) `v1-e33-t01-file-recipe-format` | Succeeded | 1 | 11.0 |
| [Lossless card writer](plan_specs/v1/e33-file-builder/t02-lossless-card-writer.yaml) `v1-e33-t02-lossless-card-writer` | Succeeded | 3 | 15.0 |
| [`debate-research files` commands](plan_specs/v1/e33-file-builder/t03-file-build-cli.yaml) `v1-e33-t03-file-build-cli` | Succeeded | 4 | 10.0 |
| [Built-file quality checks](plan_specs/v1/e33-file-builder/t04-file-quality-checks.yaml) `v1-e33-t04-file-quality-checks` | Succeeded | 2 | 11.0 |
| [Publish built files to S3](plan_specs/v1/e33-file-builder/t05-file-publish.yaml) `v1-e33-t05-file-publish` | Succeeded | 3 | 9.0 |
| [A recipe can name a camp (OpenEv) card](plan_specs/v1/e33-file-builder/t06-camp-pins.yaml) `v1-e33-t06-camp-pins` | Succeeded | 1 | 2.0 |
| [A camp occurrence row carries its camp path's digest, so a camp-path withdrawal stops it before a rebuild](plan_specs/v1/e33-file-builder/t07-camp-path-on-occurrence-rows.yaml) `v1-e33-t07-camp-path-on-occurrence-rows` | Succeeded | 1 | 2.0 |
| [Built files carry no provenance line; the sidecar keeps the provenance](plan_specs/v1/e33-file-builder/t08-provenance-line-one-function.yaml) `v1-e33-t08-provenance-line-one-function` | Succeeded | 0 | 1.0 |
| [files build refuses a store written under another style profile, as it refuses another parser version](plan_specs/v1/e33-file-builder/t09-style-profile-version-refusal.yaml) `v1-e33-t09-style-profile-version-refusal` | Succeeded | 1 | 1.0 |
| [files check and files publish warn when a built file's style profile is not the running one](plan_specs/v1/e33-file-builder/t10-sidecar-style-profile-warning.yaml) `v1-e33-t10-sidecar-style-profile-warning` | Succeeded | 1 | 1.0 |
| [files suggest drafts a CP file a coach can build on: a CP text slot first, no other position's blocks, and plank-dependent blocks marked](plan_specs/v1/e33-file-builder/t11-suggest-drafts-a-cp-file-a-coach-can-build-on.yaml) `v1-e33-t11-suggest-drafts-a-cp-file-a-coach-can-build-on` | Succeeded | 1 | 2.0 |
| [files check and files build name each warned or failed card, its check and why, as the quality report does](plan_specs/v1/e33-file-builder/t12-files-check-names-each-warned-card.yaml) `v1-e33-t12-files-check-names-each-warned-card` | Succeeded | 1 | 1.0 |
| [A CP draft keeps a block an affirmative-side position places, marked to check against the plan](plan_specs/v1/e33-file-builder/t13-cp-draft-keeps-aff-side-blocks-marked.yaml) `v1-e33-t13-cp-draft-keeps-aff-side-blocks-marked` | Succeeded | 1 | 1.0 |
| [A coach-edited list of plan-mechanism words in the topic config marks a CP draft's plan-dependent blocks](plan_specs/v1/e33-file-builder/t14-plan-mechanism-words-in-the-topic-config.yaml) `v1-e33-t14-plan-mechanism-words-in-the-topic-config` | Succeeded | 1 | 1.0 |
| [A built file still holding the CP text placeholder is warned, and a CP draft has a smoke check](plan_specs/v1/e33-file-builder/t15-unreplaced-cp-text-slot-warned.yaml) `v1-e33-t15-unreplaced-cp-text-slot-warned` | Succeeded | 1 | 1.0 |
| [files publish names a quality report written by an older version of the checks, rather than calling it missing](plan_specs/v1/e33-file-builder/t16-publish-names-an-older-quality-report.yaml) `v1-e33-t16-publish-names-an-older-quality-report` | Succeeded | 1 | 1.0 |


### v1.3 — URL → verified card

A student can run `debate-research cut <URL>` and receive a verified, tagged, cited, underlined card as DOCX + JSON.

#### [E04 — Article Retrieval & Extraction](plan_specs/v1/e04-article-retrieval/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [URL canonicalization and identifier detection](plan_specs/v1/e04-article-retrieval/t01-url-canonicalization.yaml) `v1-e04-t01-url-canonicalization` | Succeeded | 1 | 7.0 |
| [Polite HTTP fetcher](plan_specs/v1/e04-article-retrieval/t02-http-fetcher.yaml) `v1-e04-t02-http-fetcher` | Succeeded | 4 | 10.0 |
| [Access-status and paywall detection](plan_specs/v1/e04-article-retrieval/t03-access-status.yaml) `v1-e04-t03-access-status` | Succeeded | 2 | 6.0 |
| [Readable-text extraction (HTML + PDF)](plan_specs/v1/e04-article-retrieval/t04-content-extraction.yaml) `v1-e04-t04-content-extraction` | Succeeded | 2 | 8.5 |
| [ArticleService orchestration](plan_specs/v1/e04-article-retrieval/t05-article-service.yaml) `v1-e04-t05-article-service` | Succeeded | 3 | 8.5 |
| [`debate-research fetch` command and recorded fixtures](plan_specs/v1/e04-article-retrieval/t06-fetch-command.yaml) `v1-e04-t06-fetch-command` | Succeeded | 2 | 7.5 |
| [How extraction and access classification behave on real pages, measured in place](plan_specs/v1/e04-article-retrieval/t07-real-page-measurement.yaml) `v1-e04-t07-real-page-measurement` | Pending | 1 | 2.0 |
| [An Article found by its DOI and by a URL a snapshot was fetched from](plan_specs/v1/e04-article-retrieval/t08-article-lookup-by-identifier-and-fetched-url.yaml) `v1-e04-t08-article-lookup-by-identifier-and-fetched-url` | Pending | 1 | 3.0 |
| [fetch --paste can report the access status of the user's own copy](plan_specs/v1/e04-article-retrieval/t09-reported-status-for-pasted-text.yaml) `v1-e04-t09-reported-status-for-pasted-text` | Pending | 1 | 1.0 |

#### [E06 — Card Cutting, Citation & Export](plan_specs/v1/e06-card-cutting/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [CitationService with per-field provenance](plan_specs/v1/e06-card-cutting/t01-citation-service.yaml) `v1-e06-t01-citation-service` | Succeeded | 1 | 9.0 |
| [CardService pipeline](plan_specs/v1/e06-card-cutting/t02-card-service.yaml) `v1-e06-t02-card-service` | Succeeded | 3 | 10.0 |
| [Card format profiles from team conventions](plan_specs/v1/e06-card-cutting/t03-format-profiles.yaml) `v1-e06-t03-format-profiles` | Succeeded | 2 | 9.5 |
| [DOCX renderer](plan_specs/v1/e06-card-cutting/t04-docx-renderer.yaml) `v1-e06-t04-docx-renderer` | Succeeded | 3 | 11.0 |
| [JSON manifest export](plan_specs/v1/e06-card-cutting/t05-json-manifest-export.yaml) `v1-e06-t05-json-manifest-export` | Succeeded | 2 | 6.0 |
| [`debate-research cut` command](plan_specs/v1/e06-card-cutting/t06-cut-command.yaml) `v1-e06-t06-cut-command` | Pending | 3 | 7.0 |
| [Verify DOCX files](plan_specs/v1/e06-card-cutting/t07-verify-docx.yaml) `v1-e06-t07-verify-docx` | Pending | 2 | 8.0 |


### v1.4 — Federated research from the CLI

`debate-research search` fans out to scholarly/news/government adapters, dedupes and ranks results, supports --argument/--need and --auto-cut, and `daily` digests.

#### [E07 — Discovery Provider Adapters](plan_specs/v1/e07-discovery-adapters/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [SearchProvider contract, health and circuit breaking](plan_specs/v1/e07-discovery-adapters/t01-search-provider-contract.yaml) `v1-e07-t01-search-provider-contract` | Succeeded | 1 | 9.0 |
| [OpenAlex adapter](plan_specs/v1/e07-discovery-adapters/t02-openalex-adapter.yaml) `v1-e07-t02-openalex-adapter` | Succeeded | 2 | 5.0 |
| [Crossref adapter](plan_specs/v1/e07-discovery-adapters/t03-crossref-adapter.yaml) `v1-e07-t03-crossref-adapter` | Pending | 3 | 5.0 |
| [Semantic Scholar adapter](plan_specs/v1/e07-discovery-adapters/t04-semantic-scholar-adapter.yaml) `v1-e07-t04-semantic-scholar-adapter` | Pending | 2 | 4.0 |
| [Publisher RSS/Atom and Google News RSS adapter](plan_specs/v1/e07-discovery-adapters/t05-rss-news-adapter.yaml) `v1-e07-t05-rss-news-adapter` | Succeeded | 2 | 8.0 |
| [GDELT news adapter](plan_specs/v1/e07-discovery-adapters/t06-gdelt-adapter.yaml) `v1-e07-t06-gdelt-adapter` | Pending | 2 | 4.0 |
| [Government and policy source adapters](plan_specs/v1/e07-discovery-adapters/t07-government-adapters.yaml) `v1-e07-t07-government-adapters` | Pending | 2 | 8.0 |
| [One Retry-After reader for every HTTP adapter, on an injected clock](plan_specs/v1/e07-discovery-adapters/t08-shared-retry-after.yaml) `v1-e07-t08-shared-retry-after` | Succeeded | 2 | 1.0 |
| [A Google News item resolved by its headline in a configured publisher's own feed](plan_specs/v1/e07-discovery-adapters/t09-google-news-title-match.yaml) `v1-e07-t09-google-news-title-match` | Pending | 1 | 2.0 |

#### [E08 — Federated Research Workflows](plan_specs/v1/e08-research-workflows/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [SearchService fan-out](plan_specs/v1/e08-research-workflows/t01-federated-search-service.yaml) `v1-e08-t01-federated-search-service` | Succeeded | 1 | 7.0 |
| [Normalization and deduplication](plan_specs/v1/e08-research-workflows/t02-normalize-dedupe.yaml) `v1-e08-t02-normalize-dedupe` | Succeeded | 2 | 8.0 |
| [Explainable feature ranking](plan_specs/v1/e08-research-workflows/t03-feature-ranking.yaml) `v1-e08-t03-feature-ranking` | Succeeded | 1 | 8.0 |
| [Argument/need query expansion](plan_specs/v1/e08-research-workflows/t04-argument-need-expansion.yaml) `v1-e08-t04-argument-need-expansion` | Pending | 3 | 7.5 |
| [`debate-research search` command](plan_specs/v1/e08-research-workflows/t05-search-command.yaml) `v1-e08-t05-search-command` | Pending | 4 | 6.0 |
| [`--auto-cut N` batch cutting](plan_specs/v1/e08-research-workflows/t06-auto-cut.yaml) `v1-e08-t06-auto-cut` | Pending | 3 | 9.0 |
| [`debate-research daily` digests](plan_specs/v1/e08-research-workflows/t07-daily-command.yaml) `v1-e08-t07-daily-command` | Pending | 2 | 7.0 |


### v1.5 — V1 quality gate & team pilot

Golden-card and LLM evaluations gate prompt/model changes; the CLI is packaged and piloted with the team.

#### [E09 — V1 Quality, Evaluation & Team Pilot](plan_specs/v1/e09-v1-quality-pilot/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Golden card fixtures from team files](plan_specs/v1/e09-v1-quality-pilot/t01-golden-card-fixtures.yaml) `v1-e09-t01-golden-card-fixtures` | Pending | 1 | 12.0 |
| [Golden DOCX regression tests](plan_specs/v1/e09-v1-quality-pilot/t02-docx-golden-tests.yaml) `v1-e09-t02-docx-golden-tests` | Pending | 1 | 7.0 |
| [Card selection and underlining eval harness](plan_specs/v1/e09-v1-quality-pilot/t03-span-eval-harness.yaml) `v1-e09-t03-span-eval-harness` | Pending | 2 | 9.0 |
| [Prompt/model promotion gate](plan_specs/v1/e09-v1-quality-pilot/t04-prompt-promotion-gate.yaml) `v1-e09-t04-prompt-promotion-gate` | Pending | 3 | 5.5 |
| [End-to-end recorded suite](plan_specs/v1/e09-v1-quality-pilot/t05-e2e-fixture-suite.yaml) `v1-e09-t05-e2e-fixture-suite` | Pending | 1 | 12.0 |
| [Packaging and release workflow](plan_specs/v1/e09-v1-quality-pilot/t06-packaging-release.yaml) `v1-e09-t06-packaging-release` | Pending | 2 | 6.0 |
| [Student/coach guide and team pilot](plan_specs/v1/e09-v1-quality-pilot/t07-team-pilot.yaml) `v1-e09-t07-team-pilot` | Pending | 2 | 14.0 |


### v1.6 — Public team website

Whitefish Bay Debate has a public, mobile-friendly team website: team information, a tournament and events calendar parents can subscribe to, coach-posted announcements, and a donation page that links to the district's payment process; a minimal version is live before the October 1, 2026 parent information session. Independent of v1.1-v1.5: it needs only the repo foundation and the AWS baseline.

#### [E36 — Team Website Foundation](plan_specs/v1/e36-team-website/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Website publishing and student-privacy policy](plan_specs/v1/e36-team-website/t01-publishing-policy.yaml) `v1-e36-t01-publishing-policy` | Succeeded | 0 | 6.0 |
| [Site hosting infrastructure (ADR-0012)](plan_specs/v1/e36-team-website/t02-site-hosting.yaml) `v1-e36-t02-site-hosting` | Succeeded | 1 | 10.0 |
| [Static site scaffold](plan_specs/v1/e36-team-website/t03-site-scaffold.yaml) `v1-e36-t03-site-scaffold` | Succeeded | 0 | 8.0 |
| [Core pages for parents and students](plan_specs/v1/e36-team-website/t04-core-pages.yaml) `v1-e36-t04-core-pages` | Succeeded | 2 | 8.5 |
| [Deploy flow: dev preview then prod](plan_specs/v1/e36-team-website/t05-site-deploy.yaml) `v1-e36-t05-site-deploy` | Succeeded | 2 | 5.5 |
| [Visual design pass: layout system and home page](plan_specs/v1/e36-team-website/t06-visual-design-pass.yaml) `v1-e36-t06-visual-design-pass` | Succeeded | 1 | 7.0 |
| [Scannable structure for the FAQ, events and remaining pages](plan_specs/v1/e36-team-website/t07-page-structure-pass.yaml) `v1-e36-t07-page-structure-pass` | Succeeded | 1 | 9.5 |
| [Pre-launch visual QA and launch readiness](plan_specs/v1/e36-team-website/t08-prelaunch-visual-qa.yaml) `v1-e36-t08-prelaunch-visual-qa` | Succeeded | 2 | 6.5 |
| [Home page: the academic case for debate](plan_specs/v1/e36-team-website/t09-home-academic-case.yaml) `v1-e36-t09-home-academic-case` | Succeeded | 1 | 5.0 |
| [The export checks run against an export](plan_specs/v1/e36-team-website/t10-export-checks-in-ci.yaml) `v1-e36-t10-export-checks-in-ci` | Succeeded | 2 | 6.0 |
| [Visual QA refuses a stale export](plan_specs/v1/e36-team-website/t11-visual-qa-freshness.yaml) `v1-e36-t11-visual-qa-freshness` | Pending | 2 | 2.0 |
| [A pull request into main that touches site/ is built for prod before it merges, and site/ never trips the Python tests](plan_specs/v1/e36-team-website/t12-prod-build-before-main.yaml) `v1-e36-t12-prod-build-before-main` | Succeeded | 0 | 2.0 |

#### [E37 — Calendar & Announcements (Coach-Editable)](plan_specs/v1/e37-calendar-and-announcements/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [How coaches edit content (ADR-0015)](plan_specs/v1/e37-calendar-and-announcements/t01-content-editing-decision.yaml) `v1-e37-t01-content-editing-decision` | Succeeded | 1 | 13.0 |
| [Events and tournaments calendar](plan_specs/v1/e37-calendar-and-announcements/t02-events-calendar.yaml) `v1-e37-t02-events-calendar` | Succeeded | 2 | 11.0 |
| [Announcements and news](plan_specs/v1/e37-calendar-and-announcements/t03-announcements.yaml) `v1-e37-t03-announcements` | Pending | 2 | 10.0 |
| [Automatic republish on content changes](plan_specs/v1/e37-calendar-and-announcements/t04-auto-republish.yaml) `v1-e37-t04-auto-republish` | Cancelled | 3 | 11.0 |
| [Parent email updates](plan_specs/v1/e37-calendar-and-announcements/t05-parent-email-signup.yaml) `v1-e37-t05-parent-email-signup` | Succeeded | 2 | 6.0 |
| [Season results: how the team's students placed at each tournament](plan_specs/v1/e37-calendar-and-announcements/t06-season-results.yaml) `v1-e37-t06-season-results` | Succeeded | 2 | 6.0 |
| [A link to the team's Instagram account, never an embed](plan_specs/v1/e37-calendar-and-announcements/t07-instagram-link.yaml) `v1-e37-t07-instagram-link` | Succeeded | 1 | 1.0 |
| [The site smoke check reads the home page's results band and the results page](plan_specs/v1/e37-calendar-and-announcements/t08-smoke-results-band.yaml) `v1-e37-t08-smoke-results-band` | Pending | 2 | 1.0 |
| [Website changes reach the public site in a day, without waiting for a release](plan_specs/v1/e37-calendar-and-announcements/t09-site-changes-publish-without-a-release.yaml) `v1-e37-t09-site-changes-publish-without-a-release` | Succeeded | 1 | 3.0 |
| [A coach's schedule or results edit passes the site's tests without editing a test](plan_specs/v1/e37-calendar-and-announcements/t10-coach-edits-need-no-test-edit.yaml) `v1-e37-t10-coach-edits-need-no-test-edit` | Succeeded | 2 | 3.0 |
| [The shipped-content checks follow the publishing policy, and a season change is one edit of three files](plan_specs/v1/e37-calendar-and-announcements/t11-content-guards-follow-the-policy.yaml) `v1-e37-t11-content-guards-follow-the-policy` | Succeeded | 0 | 1.0 |
| [The prod build refuses an image whose consent has lapsed, as it refuses a lapsed name](plan_specs/v1/e37-calendar-and-announcements/t12-stale-image-consent-refused.yaml) `v1-e37-t12-stale-image-consent-refused` | Succeeded | 0 | 1.0 |
| [A consent entry checked after its season ends is stale to the build, for names and images](plan_specs/v1/e37-calendar-and-announcements/t13-consent-checked-after-the-season-is-stale.yaml) `v1-e37-t13-consent-checked-after-the-season-is-stale` | Succeeded | 1 | 1.0 |
| [A check dated after the season says so, and the schedule and results use one season end](plan_specs/v1/e37-calendar-and-announcements/t14-season-end-warning-and-one-definition.yaml) `v1-e37-t14-season-end-warning-and-one-definition` | Pending | 1 | 1.0 |

#### [E38 — Team Donations](plan_specs/v1/e38-donations/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [District donation process](plan_specs/v1/e38-donations/t01-district-donation-process.yaml) `v1-e38-t01-district-donation-process` | Pending | 1 | 6.0 |
| [Donation page](plan_specs/v1/e38-donations/t02-donation-page.yaml) `v1-e38-t02-donation-page` | Pending | 4 | 9.0 |
| [Opt-in donor recognition](plan_specs/v1/e38-donations/t03-donor-recognition.yaml) `v1-e38-t03-donor-recognition` | Pending | 3 | 6.0 |


### v1.7 — Team evidence search pilot

Debaters search the team's evidence store from a school Chromebook or at home: a signed-in, team-only web page over every disclosed and camp card, one result per card, each card copied into Google Docs or Word with its formatting, its provenance shown on the card page, or downloaded as a Verbatim .docx. A pilot for the end of the 2026 fall semester. Independent of v1.2-v1.6: it needs v1.1's parsed store and fingerprints, and the E33 writer from v1.2.

#### [E39 — Team Evidence Search (Student Pilot)](plan_specs/v1/e39-evidence-search-pilot/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [ADR-0019: the student search pilot's stack, sign-in and hosting](plan_specs/v1/e39-evidence-search-pilot/t01-pilot-architecture-adr.yaml) `v1-e39-t01-pilot-architecture-adr` | Succeeded | 1 | 3.0 |
| [tub index build and publish: one searchable document per card cluster, from the parsed store](plan_specs/v1/e39-evidence-search-pilot/t02-search-index-build.yaml) `v1-e39-t02-search-index-build` | Succeeded | 3 | 6.0 |
| [Search core: safe queries, ranking, filters, pages and card rendering over the index](plan_specs/v1/e39-evidence-search-pilot/t03-search-core.yaml) `v1-e39-t03-search-core` | Succeeded | 1 | 5.0 |
| [Pilot infrastructure: the function, CloudFront, the user pool and the audit log, in dev and prod](plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml) `v1-e39-t04-pilot-infrastructure` | Succeeded | 1 | 6.0 |
| [Accounts and sign-in: the session flow, roles, and the coach's tub users commands](plan_specs/v1/e39-evidence-search-pilot/t05-accounts-and-sign-in.yaml) `v1-e39-t05-accounts-and-sign-in` | Succeeded | 1 | 5.0 |
| [Search pages: search, results, the card page and Copy card, on a Chromebook](plan_specs/v1/e39-evidence-search-pilot/t06-search-pages.yaml) `v1-e39-t06-search-pages` | Succeeded | 2 | 6.0 |
| [Removal, access audit and exposure: the pilot meets the policy's E39 gate](plan_specs/v1/e39-evidence-search-pilot/t07-removal-audit-and-exposure.yaml) `v1-e39-t07-removal-audit-and-exposure` | Succeeded | 1 | 5.0 |
| [Download a card or a small file as Verbatim .docx through the E33 writer](plan_specs/v1/e39-evidence-search-pilot/t08-card-download.yaml) `v1-e39-t08-card-download` | Succeeded | 3 | 4.0 |
| [The weekly agent run rebuilds and publishes the search index when the parsed store changed](plan_specs/v1/e39-evidence-search-pilot/t09-weekly-index-refresh.yaml) `v1-e39-t09-weekly-index-refresh` | Succeeded | 1 | 3.0 |
| [Dev smoke checks, the coach's beta and the student pilot](plan_specs/v1/e39-evidence-search-pilot/t10-pilot-smoke-and-review.yaml) `v1-e39-t10-pilot-smoke-and-review` | InProgress | 2 | 3.0 |
| [Search pages: a result count, a way back to the results, a link to the disclosed file, and Copy card without the provenance line](plan_specs/v1/e39-evidence-search-pilot/t11-search-pages-follow-ups.yaml) `v1-e39-t11-search-pages-follow-ups` | Succeeded | 2 | 4.0 |
| [Only real cards come back: entries with no cite or a few words of text, counted before any rule](plan_specs/v1/e39-evidence-search-pilot/t12-card-only-results.yaml) `v1-e39-t12-card-only-results` | Succeeded | 1 | 3.0 |
| [Find a card that says something: passage search, word stems and prefixes](plan_specs/v1/e39-evidence-search-pilot/t13-passage-search.yaml) `v1-e39-t13-passage-search` | Succeeded | 2 | 5.0 |
| [An index that would drop most of the cards is never published](plan_specs/v1/e39-evidence-search-pilot/t14-index-shrink-guard.yaml) `v1-e39-t14-index-shrink-guard` | Succeeded | 1 | 3.0 |
| [tub index prune: the runbook's prune of superseded index versions as one command](plan_specs/v1/e39-evidence-search-pilot/t15-tub-index-prune.yaml) `v1-e39-t15-tub-index-prune` | Succeeded | 1 | 2.0 |
| [Open on OpenEv: a camp card links to its camp file](plan_specs/v1/e39-evidence-search-pilot/t16-open-on-openev.yaml) `v1-e39-t16-open-on-openev` | Succeeded | 1 | 3.0 |
| [The landscape report and its school view on the pilot, for signed-in team members](plan_specs/v1/e39-evidence-search-pilot/t17-landscape-pages.yaml) `v1-e39-t17-landscape-pages` | Succeeded | 2 | 6.0 |
| [Backfile seasons searchable on the pilot, without slowing its cold start](plan_specs/v1/e39-evidence-search-pilot/t18-backfiles-in-the-pilot-index.yaml) `v1-e39-t18-backfiles-in-the-pilot-index` | Blocked | 2 | 4.0 |
| [A rebuilt index identical to the published one records the suppression list it was checked against](plan_specs/v1/e39-evidence-search-pilot/t19-identical-rebuild-records-its-suppression-list.yaml) `v1-e39-t19-identical-rebuild-records-its-suppression-list` | Succeeded | 1 | 2.0 |
| [The pilot API's test world split by surface, so a change selects only the tests it reaches](plan_specs/v1/e39-evidence-search-pilot/t20-api-conftest-split-by-surface.yaml) `v1-e39-t20-api-conftest-split-by-surface` | Succeeded | 1 | 2.0 |
| [The tub deploy test records each stub call alone, as the caselist run's does](plan_specs/v1/e39-evidence-search-pilot/t21-one-call-recorder-for-deploy-tests.yaml) `v1-e39-t21-one-call-recorder-for-deploy-tests` | Succeeded | 0 | 1.0 |
| [Smoke checks for tub index build, publish and prune, and a test of P4's shape](plan_specs/v1/e39-evidence-search-pilot/t22-tub-index-commands-smoke-and-p4-shape.yaml) `v1-e39-t22-tub-index-commands-smoke-and-p4-shape` | Succeeded | 1 | 2.0 |
| [uvicorn's app factory lives in the composition root, so app.py stops reaching every adapter](plan_specs/v1/e39-evidence-search-pilot/t23-uvicorn-factory-in-the-composition-root.yaml) `v1-e39-t23-uvicorn-factory-in-the-composition-root` | Succeeded | 1 | 1.0 |
| [A card or cart download skips the header page, and the student can name its pocket](plan_specs/v1/e39-evidence-search-pilot/t24-download-skips-the-header-page-and-names-its-pocket.yaml) `v1-e39-t24-download-skips-the-header-page-and-names-its-pocket` | Succeeded | 1 | 2.0 |
| [The weekly index stage skips an identical rebuild its record already matches, and publish --newest on the current index records instead of republishing](plan_specs/v1/e39-evidence-search-pilot/t25-identical-rebuild-skipped-and-newest-records.yaml) `v1-e39-t25-identical-rebuild-skipped-and-newest-records` | Succeeded | 1 | 2.0 |
| [The cloud smoke checks reach dev: a check marked live is let through pytest-socket, and validate-dev's cloud job proves it](plan_specs/v1/e39-evidence-search-pilot/t26-cloud-smoke-checks-reach-dev.yaml) `v1-e39-t26-cloud-smoke-checks-reach-dev` | Succeeded | 0 | 1.0 |
| [A smoke check runs publish --newest on the current index against an installed build](plan_specs/v1/e39-evidence-search-pilot/t27-newest-on-the-current-index-smoke-check.yaml) `v1-e39-t27-newest-on-the-current-index-smoke-check` | Pending | 1 | 1.0 |
| [A camp card links to its camp's page on OpenEv, the address the operator confirmed](plan_specs/v1/e39-evidence-search-pilot/t28-openev-link-goes-to-the-camps-page.yaml) `v1-e39-t28-openev-link-goes-to-the-camps-page` | Succeeded | 1 | 2.0 |
| [A camp card's OpenEv link takes the camp word the pull recorded, before the table's](plan_specs/v1/e39-evidence-search-pilot/t29-openev-camp-word-from-the-row-into-the-index.yaml) `v1-e39-t29-openev-camp-word-from-the-row-into-the-index` | Pending | 2 | 2.0 |


### v1.8 — Weekly caselist run in the cloud

The weekly caselist run (pull, import, publish, parse, search index) runs in the team's AWS account on a schedule, logging in to OpenCaselist by itself with credentials held in Secrets Manager, keeping its state in the evidence bucket, and telling the coach when a run fails or is late. The coach's Mac stops being the server the debaters' fresh evidence depends on. Needs v1.1's sync and parsed store and v1.7's search index stage.

#### [E40 — Weekly Caselist Run in the Cloud](plan_specs/v1/e40-cloud-caselist-run/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [ADR-0020: the weekly caselist run in the cloud, its credentials and its state](plan_specs/v1/e40-cloud-caselist-run/t01-cloud-run-adr.yaml) `v1-e40-t01-cloud-run-adr` | Succeeded | 2 | 3.0 |
| [The caselist token in Secrets Manager, and a scheduled login that renews it](plan_specs/v1/e40-cloud-caselist-run/t02-secrets-token-store-and-login.yaml) `v1-e40-t02-secrets-token-store-and-login` | InProgress | 1 | 4.0 |
| [The weekly run as a container on a schedule](plan_specs/v1/e40-cloud-caselist-run/t03-run-image-and-schedule.yaml) `v1-e40-t03-run-image-and-schedule` | Succeeded | 1 | 4.0 |
| [A cloud run keeps its state in the evidence bucket](plan_specs/v1/e40-cloud-caselist-run/t04-run-state-on-s3.yaml) `v1-e40-t04-run-state-on-s3` | Succeeded | 1 | 5.0 |
| [A failed or late cloud run emails the coach](plan_specs/v1/e40-cloud-caselist-run/t05-run-alerts.yaml) `v1-e40-t05-run-alerts` | Succeeded | 1 | 2.0 |
| [Cut over: the cloud run takes the schedule and the Mac stops](plan_specs/v1/e40-cloud-caselist-run/t06-cutover.yaml) `v1-e40-t06-cutover` | Succeeded | 4 | 2.0 |
| [The evidence bucket itself refuses an unconditional write of the run lock](plan_specs/v1/e40-cloud-caselist-run/t07-lock-writes-conditional-at-the-bucket.yaml) `v1-e40-t07-lock-writes-conditional-at-the-bucket` | InProgress | 1 | 1.0 |
| [A week a killed run published is parsed by the next run, not left for the next import](plan_specs/v1/e40-cloud-caselist-run/t08-parse-owed.yaml) `v1-e40-t08-parse-owed` | Succeeded | 1 | 3.0 |
| [The backfile imports run once each in the cloud, not on the operator's machine](plan_specs/v1/e40-cloud-caselist-run/t09-cloud-backfile-import.yaml) `v1-e40-t09-cloud-backfile-import` | InProgress | 2 | 3.0 |
| [A restored working copy that brings the raw sources a hand prod publish needs](plan_specs/v1/e40-cloud-caselist-run/t10-restore-with-sources.yaml) `v1-e40-t10-restore-with-sources` | Succeeded | 1 | 2.0 |
| [The dev lock held for good when the weekly run's home moves to prod](plan_specs/v1/e40-cloud-caselist-run/t11-run-home-moved-holder.yaml) `v1-e40-t11-run-home-moved-holder` | Succeeded | 1 | 2.0 |
| [A held upload a cloud task records reaches the bucket, not only its working copy](plan_specs/v1/e40-cloud-caselist-run/t12-held-upload-records-reach-the-bucket.yaml) `v1-e40-t12-held-upload-records-reach-the-bucket` | Succeeded | 1 | 3.0 |
| [In bucket mode, the report stage counts a source the bucket holds at its manifest digest as present](plan_specs/v1/e40-cloud-caselist-run/t13-bucket-mode-report-counts-held-sources.yaml) `v1-e40-t13-bucket-mode-report-counts-held-sources` | InProgress | 1 | 3.0 |
| [The deploy script's region test, which failed once under load, made deterministic](plan_specs/v1/e40-cloud-caselist-run/t14-deploy-script-region-test-under-load.yaml) `v1-e40-t14-deploy-script-region-test-under-load` | Succeeded | 0 | 1.0 |
| [A plan check for a new run image after the cutover, with the schedule left enabled](plan_specs/v1/e40-cloud-caselist-run/t15-image-plan-check-after-the-cutover.yaml) `v1-e40-t15-image-plan-check-after-the-cutover` | Succeeded | 1 | 1.0 |
| [Prod's parsed store re-parsed after a parser bump, from a copy restored with its sources](plan_specs/v1/e40-cloud-caselist-run/t16-prod-reparse-after-a-parser-bump.yaml) `v1-e40-t16-prod-reparse-after-a-parser-bump` | Pending | 2 | 2.0 |
| [A landscape report counts the weeks the cloud run pulled, from a copy restored from the bucket](plan_specs/v1/e40-cloud-caselist-run/t17-landscape-report-from-the-cloud-runs-state.yaml) `v1-e40-t17-landscape-report-from-the-cloud-runs-state` | Succeeded | 1 | 3.0 |
| [In bucket mode a failed parse stage names the cloud cure, never a publish from the operator's Mac](plan_specs/v1/e40-cloud-caselist-run/t18-cloud-parse-stage-cure.yaml) `v1-e40-t18-cloud-parse-stage-cure` | Succeeded | 0 | 2.0 |
| [The weekly cloud run builds the landscape reports, counted for cost first](plan_specs/v1/e40-cloud-caselist-run/t19-landscape-stage-in-the-weekly-run.yaml) `v1-e40-t19-landscape-stage-in-the-weekly-run` | Pending | 2 | 4.0 |
| [The caselist pull table's Detail column shortens digests as its panel does](plan_specs/v1/e40-cloud-caselist-run/t20-pull-table-shortens-digests.yaml) `v1-e40-t20-pull-table-shortens-digests` | Pending | 1 | 1.0 |
| [A restored working copy carries a marker, so leftover copies are found exactly](plan_specs/v1/e40-cloud-caselist-run/t21-restored-copy-marker.yaml) `v1-e40-t21-restored-copy-marker` | Succeeded | 0 | 1.0 |
| [In bucket mode the login banner and the parse stage's other hints point at the cloud run, not the operator's Mac](plan_specs/v1/e40-cloud-caselist-run/t22-bucket-mode-hints-point-at-the-cloud.yaml) `v1-e40-t22-bucket-mode-hints-point-at-the-cloud` | Succeeded | 0 | 1.0 |
| [The leftover search drops its pre-marker list, and a report over a restored copy requires the marker](plan_specs/v1/e40-cloud-caselist-run/t23-restored-copy-marker-required.yaml) `v1-e40-t23-restored-copy-marker-required` | Pending | 1 | 1.0 |
| [A restore refuses both environments' data directories, not only its own](plan_specs/v1/e40-cloud-caselist-run/t24-restore-refuses-either-data-directory.yaml) `v1-e40-t24-restore-refuses-either-data-directory` | Succeeded | 1 | 1.0 |
| [In bucket mode the failed-publish banners and the CLI's next step point at the cloud run, not a publish from the Mac](plan_specs/v1/e40-cloud-caselist-run/t25-remaining-bucket-mode-publish-pending-hints.yaml) `v1-e40-t25-remaining-bucket-mode-publish-pending-hints` | Succeeded | 2 | 1.0 |
| [A smoke check reads parses_owed from caselist runs and caselist status](plan_specs/v1/e40-cloud-caselist-run/t26-parses-owed-smoke-check.yaml) `v1-e40-t26-parses-owed-smoke-check` | Succeeded | 1 | 0.5 |
| [store sync never moves reports/sync/, so a push of pulled copies cannot overwrite the run's lock or state files](plan_specs/v1/e40-cloud-caselist-run/t27-store-sync-leaves-the-run-state-alone.yaml) `v1-e40-t27-store-sync-leaves-the-run-state-alone` | Pending | 1 | 1.0 |
| [The last bucket-mode wording pass: banners and the CLI name the next cloud run, and a cloud run's login hint names the task role](plan_specs/v1/e40-cloud-caselist-run/t28-last-bucket-mode-wording-pass.yaml) `v1-e40-t28-last-bucket-mode-wording-pass` | Succeeded | 1 | 2.0 |
| [A Mac pull refused because the weekly run moved to prod is recorded as skipped, with its own notice](plan_specs/v1/e40-cloud-caselist-run/t29-pull-refused-by-the-move-is-skipped.yaml) `v1-e40-t29-pull-refused-by-the-move-is-skipped` | Succeeded | 1 | 1.0 |
| [The run task gets 32 GB, so a full re-parse or a backfile import is not killed for memory](plan_specs/v1/e40-cloud-caselist-run/t30-run-task-memory-fits-a-full-parse.yaml) `v1-e40-t30-run-task-memory-fits-a-full-parse` | Succeeded | 1 | 1.0 |
| [A parse worker over its share of memory fails its file, not the whole run](plan_specs/v1/e40-cloud-caselist-run/t31-parse-worker-memory-ceiling.yaml) `v1-e40-t31-parse-worker-memory-ceiling` | Succeeded | 1 | 3.0 |
| [A backfile import logs each step as it ends, so a task killed part-way shows how far it got](plan_specs/v1/e40-cloud-caselist-run/t32-backfile-import-logs-each-step.yaml) `v1-e40-t32-backfile-import-logs-each-step` | Succeeded | 1 | 1.0 |
| [A cloud run refused for an expired login says the Wednesday login renews it, not to log in by hand](plan_specs/v1/e40-cloud-caselist-run/t33-expired-login-cloud-notice-names-the-wednesday-login.yaml) `v1-e40-t33-expired-login-cloud-notice-names-the-wednesday-login` | Succeeded | 2 | 1.0 |
| [The OpenEv metadata re-import runs in bucket mode, so a camp table change reaches dev's records](plan_specs/v1/e40-cloud-caselist-run/t34-openev-metadata-reimport-in-bucket-mode.yaml) `v1-e40-t34-openev-metadata-reimport-in-bucket-mode` | InProgress | 2 | 2.0 |
| [A cloud run refused for an expired login names the Wednesday login in its own output too](plan_specs/v1/e40-cloud-caselist-run/t35-expired-login-cli-output-in-bucket-mode.yaml) `v1-e40-t35-expired-login-cli-output-in-bucket-mode` | Pending | 1 | 1.0 |
| [The aggregate rebuild reads cards source by source, so it no longer holds a whole caselist's cards in memory](plan_specs/v1/e40-cloud-caselist-run/t36-parse-rebuild-streams-occurrence-rows.yaml) `v1-e40-t36-parse-rebuild-streams-occurrence-rows` | Pending | 2 | 3.0 |
| [Redaction no longer takes two apostrophes for a quoted path and removes the words between them](plan_specs/v1/e40-cloud-caselist-run/t37-redact-keeps-text-between-apostrophes.yaml) `v1-e40-t37-redact-keeps-text-between-apostrophes` | Pending | 1 | 1.0 |
| [A lock refusal is not reported as a run that stopped before its stages](plan_specs/v1/e40-cloud-caselist-run/t38-landscape-staleness-ignores-lock-refusals.yaml) `v1-e40-t38-landscape-staleness-ignores-lock-refusals` | Pending | 1 | 0.8 |

#### [E41 — Delivery Tooling Upkeep](plan_specs/v1/e41-delivery-tooling-upkeep/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [When a newer build wrote the database or added a setting, the error says so](plan_specs/v1/e41-delivery-tooling-upkeep/t01-newer-build-messages.yaml) `v1-e41-t01-newer-build-messages` | Succeeded | 2 | 2.0 |
| [A CI check that every locked package's licence is one the project accepts](plan_specs/v1/e41-delivery-tooling-upkeep/t02-licence-check-over-the-lock.yaml) `v1-e41-t02-licence-check-over-the-lock` | Pending | 1 | 2.0 |
| [The docstrings say what the stamped build carries](plan_specs/v1/e41-delivery-tooling-upkeep/t03-stamp-docstrings.yaml) `v1-e41-t03-stamp-docstrings` | Pending | 1 | 0.5 |
| [The single-interpreter scan leaves site/ out, as the Node project it is](plan_specs/v1/e41-delivery-tooling-upkeep/t04-single-interpreter-scan-leaves-site-out.yaml) `v1-e41-t04-single-interpreter-scan-leaves-site-out` | Pending | 1 | 0.5 |
| [One hard stop for a session's test runs that kills the whole process group, named by agreement 10](plan_specs/v1/e41-delivery-tooling-upkeep/t05-test-runs-stopped-by-process-group.yaml) `v1-e41-t05-test-runs-stopped-by-process-group` | Succeeded | 1 | 1.0 |
| [An import change in container.py that loads no new module reaches only the parts using its names](plan_specs/v1/e41-delivery-tooling-upkeep/t06-container-imports-read-by-use.yaml) `v1-e41-t06-container-imports-read-by-use` | Succeeded | 1 | 2.0 |
| [The spec validator holds each epic's graph to its tasks' prerequisites, and the task helper refuses a prerequisite it cannot find](plan_specs/v1/e41-delivery-tooling-upkeep/t07-spec-graph-checks.yaml) `v1-e41-t07-spec-graph-checks` | Succeeded | 1 | 2.0 |
| [Test selection reads a run-shaped string in an f-string or a comparison, and a shell script's quoted command words](plan_specs/v1/e41-delivery-tooling-upkeep/t08-run-shaped-strings-read-wherever-they-stand.yaml) `v1-e41-t08-run-shaped-strings-read-wherever-they-stand` | Pending | 1 | 2.0 |
| [validate_specs.py is clean under pyright, and task start refuses an unknown prerequisite even under --force](plan_specs/v1/e41-delivery-tooling-upkeep/t09-validate-specs-pyright-and-start-refuses-unknown.yaml) `v1-e41-t09-validate-specs-pyright-and-start-refuses-unknown` | Succeeded | 1 | 1.0 |
| [An unknown DEBATE_ name in .env is refused, and files build tells a newer-stamped store to install the newer build](plan_specs/v1/e41-delivery-tooling-upkeep/t10-unknown-env-names-refused-and-newer-stamp-hint.yaml) `v1-e41-t10-unknown-env-names-refused-and-newer-stamp-hint` | Pending | 1 | 1.0 |
| [Test selection no longer reads ast.walk( as a directory walk, and a contract keeps debate_api.container imported one way](plan_specs/v1/e41-delivery-tooling-upkeep/t11-selector-ast-walk-and-container-contract.yaml) `v1-e41-t11-selector-ast-walk-and-container-contract` | Succeeded | 1 | 1.0 |
| [CI's pyright covers the scripts already clean, so they stay clean](plan_specs/v1/e41-delivery-tooling-upkeep/t12-pyright-covers-the-clean-scripts.yaml) `v1-e41-t12-pyright-covers-the-clean-scripts` | Pending | 1 | 0.5 |
| [The image plan check refuses a schedule repointed at a revision registered before the apply](plan_specs/v1/e41-delivery-tooling-upkeep/t13-image-plan-check-known-revision-rule.yaml) `v1-e41-t13-image-plan-check-known-revision-rule` | Pending | 1 | 0.5 |


## V2

### v2.0 — Cloud platform foundation

Keyless CI deploys, DynamoDB + S3 repositories passing the same contract tests, Cognito auth and the FastAPI service are live in dev and prod, with every prod deploy promoted from a validated dev deploy.

#### [E10 — AWS & Infrastructure-as-Code Foundation](plan_specs/v2/e10-aws-foundation/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [GitHub OIDC deploy roles](plan_specs/v2/e10-aws-foundation/t03-github-oidc-deploy.yaml) `v2-e10-t03-github-oidc-deploy` | Blocked | 1 | 8.0 |
| [KMS keys and Secrets Manager](plan_specs/v2/e10-aws-foundation/t04-kms-secrets.yaml) `v2-e10-t04-kms-secrets` | Blocked | 1 | 9.0 |
| [Networking, ECR and ECS/Fargate cluster](plan_specs/v2/e10-aws-foundation/t05-container-platform.yaml) `v2-e10-t05-container-platform` | Blocked | 1 | 10.0 |
| [Observability baseline](plan_specs/v2/e10-aws-foundation/t06-observability-baseline.yaml) `v2-e10-t06-observability-baseline` | Pending | 1 | 11.0 |

#### [E11 — Cloud Persistence Adapters](plan_specs/v2/e11-cloud-persistence/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [AppTable access-pattern design](plan_specs/v2/e11-cloud-persistence/t01-access-pattern-design.yaml) `v2-e11-t01-access-pattern-design` | Blocked | 1 | 8.0 |
| [DynamoDB tables in Terraform](plan_specs/v2/e11-cloud-persistence/t02-dynamodb-tables.yaml) `v2-e11-t02-dynamodb-tables` | Pending | 2 | 6.0 |
| [DynamoDB repository implementations](plan_specs/v2/e11-cloud-persistence/t03-dynamodb-repositories.yaml) `v2-e11-t03-dynamodb-repositories` | Pending | 2 | 13.0 |
| [S3 snapshot and export store](plan_specs/v2/e11-cloud-persistence/t04-s3-snapshot-store.yaml) `v2-e11-t04-s3-snapshot-store` | Pending | 3 | 8.0 |
| [Optimistic concurrency for cards and files](plan_specs/v2/e11-cloud-persistence/t05-optimistic-concurrency.yaml) `v2-e11-t05-optimistic-concurrency` | Pending | 1 | 10.0 |
| [V1 local-library migration tool](plan_specs/v2/e11-cloud-persistence/t06-v1-data-migration.yaml) `v2-e11-t06-v1-data-migration` | Pending | 3 | 10.0 |

#### [E12 — Identity & API Service](plan_specs/v2/e12-identity-api/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Cognito user pool and Google federation](plan_specs/v2/e12-identity-api/t01-cognito-user-pool.yaml) `v2-e12-t01-cognito-user-pool` | Blocked | 2 | 8.0 |
| [FastAPI service skeleton](plan_specs/v2/e12-identity-api/t02-fastapi-service.yaml) `v2-e12-t02-fastapi-service` | Blocked | 1 | 9.0 |
| [Authentication, roles and tenancy](plan_specs/v2/e12-identity-api/t03-authn-authz.yaml) `v2-e12-t03-authn-authz` | Pending | 2 | 9.0 |
| [API Gateway + ECS Fargate deployment](plan_specs/v2/e12-identity-api/t04-api-deploy.yaml) `v2-e12-t04-api-deploy` | Pending | 3 | 11.0 |
| [Core resource endpoints](plan_specs/v2/e12-identity-api/t05-core-endpoints.yaml) `v2-e12-t05-core-endpoints` | Pending | 5 | 12.0 |
| [OpenAPI TypeScript client generation](plan_specs/v2/e12-identity-api/t06-openapi-client.yaml) `v2-e12-t06-openapi-client` | Pending | 1 | 6.0 |
| [Cloud dev→prod promotion pipeline](plan_specs/v2/e12-identity-api/t07-promotion-pipeline.yaml) `v2-e12-t07-promotion-pipeline` | Pending | 3 | 15.5 |


### v2.1 — Web app, debate tub & async jobs

Debaters sign in to the web app and browse, search and download the team's evidence files (the debate tub); students paste a URL and get a verified card through an async job.

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
| [Web hosting and environments](plan_specs/v2/e14-web-cut-card/t03-app-hosting.yaml) `v2-e14-t03-app-hosting` | Pending | 6 | 9.0 |
| [Cut-a-Card flow](plan_specs/v2/e14-web-cut-card/t04-cut-card-flow.yaml) `v2-e14-t04-cut-card-flow` | Pending | 4 | 12.0 |
| [Provenance-constrained card editor](plan_specs/v2/e14-web-cut-card/t05-card-editor.yaml) `v2-e14-t05-card-editor` | Pending | 3 | 14.0 |
| [DOCX export and copy-as-rich-text](plan_specs/v2/e14-web-cut-card/t06-export-copy.yaml) `v2-e14-t06-export-copy` | Pending | 2 | 9.0 |

#### [E35 — Debate Tub (Web File Access)](plan_specs/v2/e35-debate-tub/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Tub data model](plan_specs/v2/e35-debate-tub/t01-tub-data-model.yaml) `v2-e35-t01-tub-data-model` | Pending | 2 | 11.0 |
| [Index the evidence store](plan_specs/v2/e35-debate-tub/t02-tub-index-sync.yaml) `v2-e35-t02-tub-index-sync` | Pending | 3 | 13.0 |
| [Tub API](plan_specs/v2/e35-debate-tub/t03-tub-api.yaml) `v2-e35-t03-tub-api` | Pending | 2 | 13.0 |
| [Tub UI](plan_specs/v2/e35-debate-tub/t04-tub-ui.yaml) `v2-e35-t04-tub-ui` | Pending | 2 | 15.0 |
| [Access audit and removal](plan_specs/v2/e35-debate-tub/t05-tub-access-and-removal.yaml) `v2-e35-t05-tub-access-and-removal` | Pending | 4 | 12.0 |
| [Tub smoke checks and debater review](plan_specs/v2/e35-debate-tub/t06-tub-smoke-and-review.yaml) `v2-e35-t06-tub-smoke-and-review` | Pending | 2 | 10.0 |


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
| [Parse PDF disclosures into the parsed card store](plan_specs/v2/e15-search-index/t07-pdf-disclosure-parsing.yaml) `v2-e15-t07-pdf-disclosure-parsing` | Pending | 2 | 8.0 |

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
| [Organization sharing](plan_specs/v2/e17-card-library/t06-team-sharing.yaml) `v2-e17-t06-team-sharing` | Pending | 2 | 10.0 |

#### [E18 — Card Extensions](plan_specs/v2/e18-card-extensions/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Pasted-card parser](plan_specs/v2/e18-card-extensions/t01-card-parser.yaml) `v2-e18-t01-card-parser` | Blocked | 1 | 11.5 |
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
| [Privacy and legal review](plan_specs/v2/e19-production-readiness/t04-privacy-legal-review.yaml) `v2-e19-t04-privacy-legal-review` | Blocked | 0 | 13.0 |
| [Backups and restore drill](plan_specs/v2/e19-production-readiness/t05-backups-dr.yaml) `v2-e19-t05-backups-dr` | Pending | 4 | 10.0 |
| [Cost telemetry dashboard](plan_specs/v2/e19-production-readiness/t06-cost-dashboard.yaml) `v2-e19-t06-cost-dashboard` | Pending | 2 | 8.0 |
| [Load and security testing](plan_specs/v2/e19-production-readiness/t07-load-security-testing.yaml) `v2-e19-t07-load-security-testing` | Pending | 2 | 14.0 |


## V3

### v3.0 — Debate file intelligence & argument graph

Uploaded debate files are parsed (with the V1 parser) into sections/cards and an explicit, sourced argument graph.

#### [E20 — Debate File Intelligence](plan_specs/v3/e20-file-intelligence/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [DebateFile and FileSection model](plan_specs/v3/e20-file-intelligence/t01-debate-file-model.yaml) `v3-e20-t01-debate-file-model` | Pending | 3 | 10.0 |
| [Upload pipeline](plan_specs/v3/e20-file-intelligence/t02-upload-pipeline.yaml) `v3-e20-t02-upload-pipeline` | Pending | 3 | 13.0 |
| [File library UI](plan_specs/v3/e20-file-intelligence/t05-file-library-ui.yaml) `v3-e20-t05-file-library-ui` | Pending | 4 | 14.0 |

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
| [Newer external evidence suggestions](plan_specs/v3/e23-file-auditing/t04-newer-evidence.yaml) `v3-e23-t04-newer-evidence` | Pending | 4 | 7.0 |
| [Audit report UI](plan_specs/v3/e23-file-auditing/t05-audit-report-ui.yaml) `v3-e23-t05-audit-report-ui` | Pending | 2 | 13.0 |
| [File audit evaluation](plan_specs/v3/e23-file-auditing/t06-audit-eval.yaml) `v3-e23-t06-audit-eval` | Pending | 2 | 11.0 |


### v3.3 — Opponent data integrations

Public OpenCaselist disclosures and Tabroom results are ingested with provenance and resolved to team identities.

#### [E24 — Opponent Data Integrations](plan_specs/v3/e24-opponent-data/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [OpponentTable design](plan_specs/v3/e24-opponent-data/t01-opponent-table.yaml) `v3-e24-t01-opponent-table` | Pending | 3 | 9.0 |
| [OpenCaselist adapter](plan_specs/v3/e24-opponent-data/t02-opencaselist-adapter.yaml) `v3-e24-t02-opencaselist-adapter` | Pending | 3 | 12.0 |
| [Tabroom public results adapter](plan_specs/v3/e24-opponent-data/t03-tabroom-adapter.yaml) `v3-e24-t03-tabroom-adapter` | Pending | 2 | 10.0 |
| [Team and debater identity resolution](plan_specs/v3/e24-opponent-data/t04-identity-resolution.yaml) `v3-e24-t04-identity-resolution` | Pending | 2 | 12.0 |
| [Refresh scheduling and removal](plan_specs/v3/e24-opponent-data/t05-refresh-provenance.yaml) `v3-e24-t05-refresh-provenance` | Pending | 3 | 10.0 |
| [Opponent data governance review](plan_specs/v3/e24-opponent-data/t06-data-governance.yaml) `v3-e24-t06-data-governance` | Pending | 2 | 8.0 |


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

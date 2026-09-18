# Debate Research & Argument Intelligence Platform

Evidence research, card cutting, argument intelligence, opponent scouting and round
simulation for high-school Policy, Lincoln-Douglas and Public Forum debate.

* **Architecture:** [docs/architecture/architecture_proposal.md](docs/architecture/architecture_proposal.md)
* **Roadmap (releases → epics → tasks):** [ROADMAP.md](ROADMAP.md)
* **Plan specs and conventions:** [plan_specs/README.md](plan_specs/README.md)

## Status

Planning complete; implementation starts with release **v1.0**
([plan_specs/releases/v1.0.yaml](plan_specs/releases/v1.0.yaml)). The next tasks are
`v1-e01-t02-github-remote`, `v1-e01-t03-uv-workspace-tooling` and `v1-e01-t06-adr-docs`.

## Versions

| Major | Delivery surface | Minor releases |
|---|---|---|
| **V1** | `debate-research` CLI: search, cut, verify, daily | v1.0 – v1.3 |
| **V2** | Authenticated web workspace on AWS: research, Cut-a-Card, library, extensions | v2.0 – v2.4 |
| **V3** | Argument graph, coverage analysis, file audits, scouting, CX + round simulation | v3.0 – v3.7 |

## Non-negotiables

1. **Evidence integrity.** Models select spans; they never write quoted evidence. Every card
   is reproducible from a stored, hashed source snapshot or it is marked UNVERIFIED.
2. **One domain core.** CLI, API, workers and agents are thin surfaces over `debate_core`.
3. **Adapters at every boundary.** Providers, models and persistence sit behind ports.
4. **Public or authorized data only.** No paywall, login or robots bypassing.
5. **Students may be minors.** Minimize personal data; legal review precedes school rollout.

## Repository layout

```
packages/debate_core      domain, application services, evidence, retrieval (Python)
packages/debate_cli       Typer CLI (V1)
packages/debate_api       FastAPI service (V2)
packages/debate_workers   async job handlers (V2+)
web/                      Next.js client (V2)
infrastructure/           Terraform (V2)
tests/                    fixtures, golden cards, integration suites
plan_specs/               PlanSpecs: releases/, v1/, v2/, v3/
docs/                     architecture proposal, ADRs
scripts/                  validate_specs.py, spec_index.py
```

## Branches and environments

`main` is production and `dev` is the development environment; every change is deployed to
and validated in dev before a `dev` → `main` promotion. Details:
[docs/process/branching-and-environments.md](docs/process/branching-and-environments.md).

## Working on a task

```bash
uv run scripts/validate_specs.py --status   # validate specs + progress roll-up
uv run scripts/spec_index.py                # refresh ROADMAP.md after changing a spec's status
```

Pick a task whose prerequisites are `Succeeded`, branch `task/<task-name>`, implement its
plan nodes in order until each node's acceptance criteria pass, set the task Goal's
`status.phase` to `Succeeded`, and open a PR into `dev` that references the spec path.

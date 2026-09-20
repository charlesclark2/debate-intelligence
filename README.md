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

## Development setup

Python 3.12 (pinned in `.python-version`) and [uv](https://docs.astral.sh/uv/). The root
`pyproject.toml` is a uv workspace whose members are the four packages under `packages/`; it also
holds the configuration for every quality tool.

```bash
uv sync --all-packages             # create .venv with all packages + dev tools from uv.lock
uv run pre-commit install          # once per clone: ruff, formatting, whitespace, large-file guard
uv run ruff check                  # lint
uv run ruff format --check         # formatting
uv run pyright packages/debate_core   # strict type check of the domain core
uv run pytest                      # parallel, with coverage, network blocked
```

`pytest` runs with `-n auto`, coverage and sockets disabled, and deselects `slow` and `live`
tests; opt in with `uv run pytest -m slow` or `-m live`. The project's markers (`slow`, `live`,
`eval`, `dev`, `prod`) are all registered in the root `pyproject.toml`; `--strict-markers`
rejects any other.

## Branches and environments

`main` is production and `dev` is the development environment; every change is deployed to
and validated in dev before a `dev` → `main` promotion. Details:
[docs/process/branching-and-environments.md](docs/process/branching-and-environments.md).

## Working on a task

```bash
scripts/task ready                 # what can start now
scripts/task start <task>          # worktree + branch off dev, launches Claude with the spec
scripts/task pr <task>             # after PM review: PR into dev
scripts/task finish <task>         # after merge: clean up worktree and branches
```

See [docs/process/task-workflow.md](docs/process/task-workflow.md) and the
[documentation index](docs/README.md).

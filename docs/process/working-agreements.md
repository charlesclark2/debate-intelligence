# Working agreements

Rules every contributor and every Claude session follows on this project. Task specs, CI and
`scripts/task` are built to enforce them. Change them only through a PR that updates this file.

## 1. CI stays light

The goal is a short wait between opening a PR and being able to merge it into `dev`.

* **Budget:** the required `ci` check on a PR into `dev` should finish in **under 5 minutes**
  wall-clock, with 10 minutes as a hard ceiling. A change that pushes CI past the budget has to
  move work out of the PR path in the same PR.
* **What runs on every PR:** formatting and lint, type checks, fast unit and contract tests,
  import-boundary checks, spec validation. All offline: recorded fixtures and the fake/replay
  model router, no live network, no real model calls.
* **Path filters:** jobs only run when their area changed. Web jobs when `web/` or
  `clients/` changed, Terraform `fmt`/`validate` when `infrastructure/` changed, Python jobs when
  `packages/`, `tests/` or `pyproject.toml` changed.
* **Not on PRs into `dev`:** LLM evaluation suites, browser end-to-end suites, live canaries,
  `terraform plan/apply` against real accounts, load tests, security scans that take minutes. They
  run in `validate-dev` after the merge (before a promotion to `main`), on a nightly schedule, or on
  manual dispatch.
* **Test markers:** tests that are slow or need the network are marked (`@pytest.mark.slow`,
  `@pytest.mark.live`) and excluded from the default `pytest` run.

## 2. Anything over about 2 minutes goes to the operator

A session never starts a command it expects to run longer than about 2 minutes: full test suites,
large dependency installs, model evaluations, embedding backfills, `terraform apply`, load tests,
bulk fixture generation, index rebuilds. Instead it stops and hands Charlie a block like this:

````markdown
**Operator command** (expected runtime ~6 min)
Where: your Mac, in the task worktree `debate-intelligence-worktrees/<task>`
```bash
uv run pytest -m slow packages/debate_core/tests/evidence
```
Success looks like: `42 passed`; paste the last 20 lines back into the session.
````

It waits for the result, then continues. The same commands are listed under **Operator
follow-ups** in the session report.

**What makes something a hand-off** is one of three things, not a label in a spec:

1. It is expected to run longer than about 2 minutes.
2. It changes something outside the worktree: an apply, a deploy, a purchase, a push, a message.
3. It needs credentials, an approval or a device the session should not use on its own.

A read-only command over files the operator already has, finishing in seconds, is none of those: a
session runs it and reports the measured runtime. If a spec calls such a step "operator-run", the
session may run it and say so in Deviations. When in doubt, hand it over.

## 3. Documentation lives in predictable places

| Directory | What goes there |
|---|---|
| `docs/architecture/` | The architecture proposal and diagrams |
| `docs/adr/` | Architecture decision records, `NNNN-short-title.md` |
| `docs/process/` | How we work: branching and environments, the task workflow, these agreements, templates |
| `docs/session-reports/` | One report per task, `<task-name>.md`, committed with the task's PR |
| `docs/runbooks/` | Operational procedures (deploys, restores, incident steps), added as V2 needs them |
| `docs/guides/` | Student- and coach-facing guides for using the tools |
| `docs/data/` | Data models and DynamoDB access patterns; recorded results of operator-run data jobs (counts, eval summaries; aggregates only, no debater names) |
| `docs/policies/` | Data-use policies (caselist and OpenEv data use, removal process), approved by Charlie |
| `plan_specs/` | PlanSpecs only: releases, epics, tasks |
| `packages/<pkg>/README.md` | Package-level developer notes |

[`docs/README.md`](../README.md) indexes these. New documentation goes in the matching directory
and gets a line in the index; don't create new top-level doc folders without updating this table.

## 4. Descriptive names, not opaque labels

Name things for what they are. Avoid labels like `A1`, `A2`, `Phase B`, `Option 3` or `Step 4`
for tasks, documents, sections, files, branches, flags or identifiers unless the label is a real
domain term (for example `1NC`, `2AR`, `v1.2`) or a stable ID that is always shown next to a
descriptive name.

* Task names combine an ID with a slug: `v1-e04-t02-http-fetcher`, never just `t02`.
* Spec acceptance-criteria IDs (`ac1`, `ac2`) are schema identifiers inside one spec; when a
  report or PR refers to one, quote its text or give a short description too.
* Headings, commit messages and PR titles say what changed ("Add robots.txt check to the HTTP
  fetcher"), not which step it was.

## 5. Specs are the contract

* Work starts only from a task spec whose prerequisites are `Succeeded`.
* Scope changes are made in the spec, in a PR, before or alongside the code; never silently.
* A session that finds the spec wrong or incomplete stops and records it in the report under
  **Deviations** instead of improvising.
* Every task that changes a user-facing surface adds or updates its smoke checks for
  `validate-dev`.

## 6. Expected output is written by hand, not generated

A test whose expected value came out of the code under test cannot contradict that code. It
pins the behaviour that exists rather than the behaviour that was asked for, and it goes green
through the bug it was meant to catch.

* Where a task's acceptance rests on a fixture's expected output — a parsed document, an import
  summary, a rendered file — that expectation is **written by hand from the fixture** and
  committed, never produced by running the implementation and saving the result.
* Snapshot tooling that regenerates expectations on demand is fine for churn-heavy detail, but
  not for the criterion a task is accepted on.
* This is not theoretical. `v1-e30-t03` hand-wrote `expected_summary.json` and it held the
  cumulative dedupe honest. `v1-e31-t03` hand-wrote its parser expectations and they caught two
  bugs that every test the session had written itself passed: a second tag nested under the first
  instead of beside it, and a tag demoted to an analytic that went on occupying tag level.
* The same reasoning applies to a number quoted in a report. A count is recorded from a run that
  happened, and a criterion that could not be exercised is `NOT RUN`, never a plausible value.

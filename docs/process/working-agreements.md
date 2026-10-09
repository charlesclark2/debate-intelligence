<!-- docs-index: Project rules: light CI, operator hand-off for long commands, doc locations, naming -->
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
| `docs/evidence/` | Evidence-integrity rules that stored data depends on: the versioned text normalization policy |
| `plan_specs/` | PlanSpecs only: releases, epics, tasks |
| `packages/<pkg>/README.md` | Package-level developer notes |

[`docs/README.md`](../README.md) indexes these. New documentation goes in the matching directory;
don't create new top-level doc folders without updating this table.

The index's table is generated, so nobody writes a line in it. A new document's **first line** is
its one-line description, `<!-- docs-index: What this document is for -->`, which is invisible
when rendered and is copied into the index as written; a directory with its own `README.md` is
indexed by that README alone, so its other files need none. CI fails a pull request whose document
has no such line, naming the file. Don't edit or regenerate `docs/README.md` in a task:
`.github/workflows/refresh-generated-files.yml` regenerates it, with `ROADMAP.md`, after each merge
into `dev`, so two tasks that each add a document never conflict over the index. Until
[`v1-e01-t16`](../../plan_specs/v1/e01-repo-foundation/t16-generated-docs-index.yaml) this
paragraph asked for the line by hand, and concurrent tasks collided on the index four times.

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

## 7. A decision record is measured first, and checked against policy

ADR-0016 was written and superseded on the same day. It reordered a release and drove spec changes
across three epics on two premises that one authenticated listing call disproved, and it decided a
download cadence that an already-approved policy forbade.

* **Measure the source, not a sample of its output.** ADR-0016 inferred how OpenCaselist publishes
  archives from three files that had been downloaded by hand. What it needed was the list of what the
  site actually offers. Where a decision rests on how an external system behaves, ask that system
  before writing the decision down.
* **A decision that contradicts an approved policy is wrong, not an exception.** The daily cadence in
  ADR-0016 contradicted `docs/policies/caselist-data-use.md`, agreed with a volunteer maintainer who
  answered a question as a favour. The policy is checked before a decision record is written, and
  where they conflict the policy governs until it is renegotiated with whoever approved it.
* **Urgency is a reason to check, not a reason to skip checking.** The argument for haste - every day
  costs data that cannot be recovered - was itself the thing that was untrue.
* Superseded records stay in place with their reasoning intact. Whoever reads them next should be
  able to see what was believed, what it caused, and what disproved it.

## 8. A mutation run starts from an empty Hypothesis database

Hypothesis saves every failing example it finds and replays it first on the next run. During
mutation testing that makes a property look stronger than it is. In `v1-e03-t03` one mutant was
caught 28 seconds into a run and then twice more in 0.3 seconds, because the later runs replayed
the example the first had found instead of finding it again.

* Every run against a mutant sets `HYPOTHESIS_STORAGE_DIRECTORY` to a new, empty directory, so the
  property has to find the break from scratch.
* A report that gives catch times, or says a property caught a mutant, states that each run used a
  fresh database.
* A property is checked for what it actually generates (`--hypothesis-show-statistics`) before it
  is offered as evidence. One that rarely produces the input it was written for passes without
  testing it.
* An attempt that errors before it runs is not a catch. A mutation that fails at collection proves
  nothing about the check it was aimed at, and is redone or discarded rather than counted.
* Deleting a check is a legitimate result. If mutation cannot tell a check apart from its absence,
  the honest outcome is usually to remove it, not to write a test that justifies keeping it.
* Catch times reported before 2026-10-01, in `v1-e03-t01` and `v1-e03-t02`, were measured without
  database isolation. Their conclusions about which checks are load-bearing stand; their timings
  are upper bounds on speed, not evidence of how readily a property finds a break from cold.
  (Added by the PM.)

## 9. Command blocks are safe to paste into zsh

The operator's shell is zsh, which does not treat `#` as a comment when commands are pasted
interactively. A trailing comment becomes arguments: `git status --porcelain # must print nothing`
reads the words as pathspecs and prints nothing even on a dirty tree, so the check it was meant to
be always passes.

* **No `#` comments inside a shell code block** that a person will paste: runbooks, guides,
  READMEs and the operator follow-ups of a session report. Put the explanation in the prose.
* Put one-time commands and every-time commands in separate blocks, rather than marking them with
  a comment.
* `scripts/check_command_blocks.py` enforces this in CI (`v1-e01-t19`). It reads the `bash`, `sh`,
  `zsh`, `shell` and `console` blocks of every tracked Markdown file, and a session report when a
  pull request adds or changes it. A `#` inside quotes, a heredoc body or a word such as a URL's
  `#anchor` is not a comment and passes.


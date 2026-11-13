<!-- docs-index: Project rules: light CI, operator hand-off for long commands, doc locations, naming -->
# Working agreements

Rules every contributor and every Claude session follows on this project. Task specs, CI and
`scripts/task` are built to enforce them. Change them only through a PR that updates this file.

## 1. CI stays light

The goal is a short wait between opening a PR and being able to merge it into `dev`.

* **Budget:** the required `ci` check on a PR into `dev` should finish in **under 5 minutes**
  wall-clock, with 10 minutes as a hard ceiling. A change that pushes CI past the budget has to
  move work out of the PR path in the same PR.
* **Target:** on a typical PR into `dev`, `ci` finishes in **under 3 minutes**. The budget is the
  limit; the target is where the check is kept, so that a growing suite is noticed two minutes
  before it is a problem. Until `v1-e01-t27` the `test` job alone took 4 to 6 minutes.
* **The test job runs in parts.** `ci.yml`'s `test` job is a matrix, and each part runs
  `pytest --part K/N` on its own runner. A part is not a list of directories:
  `tests/pytest_plugins/run_in_parts.py` deals the selection to the N parts, so every selected
  test is in exactly one part. It deals whole test files by the seconds each took on dev's last
  push run (`v1-e41-t17`), so a file's module-scoped fixtures are built in one part instead of in
  all of them: every push part times its files, `ci.yml`'s `test-durations` job adds them up and
  saves them in GitHub's Actions cache, and `test-selection` restores them once and hands every part
  the same deal. A file with no record counts as the record's median, and a file heavier than a
  part's share is dealt test by test. A record that is missing, older than two weeks, or that knows
  under three quarters of the chosen files deals every file's tests round the parts as before,
  and the job summary says why; it never fails a run (`scripts/ci_test_durations.py`). Under a
  deal a part collects only the files it was dealt and any file the deal does not name, which it
  deals test by test, never another part's (`v1-e41-t18`); its summary says how long it took to
  collect. The
  parts together are the selection: on a pull request into `dev` the tests its changes reach, and
  otherwise the whole default selection ([agreement 10](#10-a-session-tests-what-it-changed-a-pull-request-what-it-reaches-and-dev-and-main-everything)).
  `ci.yml`'s `test-selection` job chooses it once and every part reads it; when it chooses no test,
  the parts are skipped and `ci` still passes (`v1-e41-t15`).
* **The selection decides how many parts run** (`v1-e41-t16`): one part per 30 test files chosen,
  at least one and at most eight, and eight for the whole selection. `test-selection` counts its
  own list, so the count costs nothing, and hands the `test` matrix a list of part numbers; each
  part asks for `--part K/N` with N the matrix's size. Thirty test files are about 1,000 tests on
  today's suite, which a runner's part runs in about 100 seconds. A small affected set saves
  runners and the queue for them; most task pull requests reach a third of the suite or more and
  still get seven or eight parts, so sizing does not shorten their wait
  ([`docs/process/ci-test-part-costs.md`](ci-test-part-costs.md) has the figures). A dispatch of
  `ci.yml` can ask for pytest-xdist's `--dist load` (the `xdist_dist` input); every other run uses
  `--dist worksteal`, the default since the PM's comparison on one commit (2026-11-02).
* **The parts are proved to be the selection.**
  `tests/scripts/test_ci_workflow_test_job.py` collects every part and proves it, for an affected
  set and for the whole selection, dealt by durations and test by test, in a job of its own, `partition-proof`: on every push to `dev` and `main`, and on a pull request that
  changes what the proof covers (`ci.yml`, `tests/pytest_plugins/`, the selection scripts, pytest's
  configuration, the proof itself). The proof collects the whole suite nine times, and in a part it
  held that part for about 70 seconds. It also deals the real collection at every size the matrix
  can take, one part to eight, with the plugin's own dealing function, under a deal and under none.
  No other test is moved off the PR path to make room.
* **A pull request's newer push cancels its older run; nothing else is cancelled.** A push to `dev`
  or `main` and a dispatched run each have a concurrency group of their own, so every merge commit
  gets its own verdict and never waits for the run before it (`v1-e41-t15`).
* **When it drifts**, read the `test` parts of a few recent pull requests. Each ends with its 25
  slowest tests.
  * One part's pytest step over 2 minutes on a whole-selection run: raise `MOST_PARTS` in
    `scripts/ci_test_selection.py` (8 becomes 9). Over 2 minutes on an affected set: lower its
    `TEST_FILES_PER_PART` (30). Nothing else changes. Each extra part repeats the job's setup,
    about 15 seconds, and its own collection. `ci` over 3 minutes on ordinary pull requests while
    every part is under 2 is not a part count to change: read the costs page first.
  * One part steadily slower than the others: a few slow tests have landed together. Its durations
    name them, and `test-selection`'s summary says whether the parts were dealt by durations, from
    which record, and the seconds it expected of each part. Make them cheaper; never mark them
    `slow` to get them out of the way.
* **The same option splits a long local run** for the operator: `uv run pytest --part 1/2` and
  then `--part 2/2` are the whole default selection between them, for any N. A session does not use
  it to run the whole selection in pieces; what a session runs is [agreement 10](#10-a-session-tests-what-it-changed-a-pull-request-what-it-reaches-and-dev-and-main-everything).
* **Coverage is not measured on a PR, or by a plain `uv run pytest`.** It took a third of the
  suite's time and nothing is gated on it. On every push to `dev` and `main`, each test part measures
  its share and `ci.yml`'s `coverage` job combines them (`v1-e01-t42`), so the push run waits only for
  its parts. A push part that takes over 8 minutes means one part more: a larger `MOST_PARTS`. Locally, ask for it:
  `uv run pytest --cov --cov-report=term-missing`.
* **What runs on every PR:** formatting and lint, type checks, fast unit and contract tests,
  import-boundary checks, spec validation, and on a pull request into `dev` the slow tests its
  affected set reaches (below). All offline: recorded fixtures and the fake/replay model router,
  no live network, no real model calls.
* **A pull request into `dev` runs the slow tests its affected set reaches** (`v1-e41-t29`, the PM's
  rulings of 2026-11-13). The parts run `not slow`. Beside them, `ci.yml`'s `slow-tests` job runs
  the slow tests of the same chosen files, or for the whole selection every slow test, with
  validate-dev's slow-tier markers (`validate_dev.SLOW`, imported by `scripts/ci_slow_tests.py`).
  `v1-e08-t24`'s ranking change broke a slow end-to-end test its affected set had chosen. No pull
  request ran it, and dev was red for a day until validate-dev's slow tier saw it.
  * **Four tests stay on validate-dev only**, deselected by node id, each with its reason in the job
    summary (`LEFT_TO_VALIDATE_DEV` in `scripts/ci_slow_tests.py`, pinned by its test): the
    planted-break cases, which every task pull request reaches through its own spec and which are
    most of validate-dev's 6–7-minute slow tier, the LibreOffice renderer check and the two
    Lambda-image SQLite checks. A new one is a reviewed change to that list.
  * **A skip fails it**, as it fails validate-dev's tier. No slow test left to run passes.
  * **It is one of `ci`'s needs**, gated on `test-selection`'s `run_slow`, so a slow failure blocks
    the merge into `dev`. The required checks do not change. A push, a promotion and a dispatch
    leave the slow tier to validate-dev, which runs it whole on every dev pre-release.
  * **Its bound:** the pytest step at most 120 seconds on a runner, and the job at most 60 seconds
    past the longest test part. When that is passed on ordinary pull requests, the browser files
    move to a job of their own first, then the slowest test is made cheaper. Nothing ever leaves
    validate-dev's slow tier. Its log ends with the 25 slowest tests, as validate-dev's tiers do;
    [`ci-test-part-costs.md`](ci-test-part-costs.md#the-slow-tests-job) has the figures it was
    sized by.
* **Path filters:** jobs only run when their area changed. Web jobs when `web/` or
  `clients/` changed, Terraform `fmt`/`validate` when `infrastructure/` changed, Python jobs when
  `packages/`, `tests/` or `pyproject.toml` changed.
* **Not on PRs into `dev`:** LLM evaluation suites, browser suites against a deployed site, live
  canaries, `terraform plan/apply` against real accounts, load tests, security scans that take
  minutes. They run in `validate-dev` after the merge (before a promotion to `main`), on a nightly
  schedule, or on manual dispatch. The search pages' browser files are not among them: they drive Chromium against
  pages served in-process and reach nothing outside the runner, so a pull request's `slow-tests`
  job runs them when its affected set reaches them.
* **Test markers:** tests that are slow or need the network are marked (`@pytest.mark.slow`,
  `@pytest.mark.live`) and excluded from the default `pytest` run. A `slow` test still runs on a
  pull request into `dev` that reaches it, in the `slow-tests` job, so marking a test `slow` moves it
  off the parts, never off the pull request.

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

## 10. A session tests what it changed, a pull request what it reaches, and dev and main everything

The whole default selection takes about six minutes on the operator's Mac and grows with almost every
task. Sessions were running it in eighths several times each (at red, at green, after formatting,
after mutation runs, after a sync), and that had become most of a session's wall-clock time. CI ran
the whole selection on every pull request, in parallel parts, in about three minutes, once per push
rather than once per idea. (Added by the PM, 2026-10-19.) By 2026-10-26 that run neared the
5-minute budget of [agreement 1](#1-ci-stays-light), so a pull request into `dev` now runs only the
tests its changes reach, and the whole selection runs once per merge instead (`v1-e01-t38`).

* **A pull request into `dev` runs the affected set.** ci.yml's `test-selection` job reads
  `scripts/affected_tests.py`'s selection against the pull request's base commit, always-run list
  included, once, with the deal of its files to the parts, and the `test` parts follow it. When the pull request changes
  shared test ground (ci.yml among it), or its selection fails, comes back empty or has no base
  commit to compare with, the parts run the whole selection instead: it fails toward more tests,
  never fewer. The job summary says how many test files it chose and, for the whole selection, why.
  The one change that runs no test is the two generated files alone, `ROADMAP.md` and
  `docs/README.md`: the bot's refresh pull request, and the run it dispatches on its branch, run
  only the doc checks (`v1-e41-t15`); since `v1-e41-t16` that dispatch also runs no type check,
  import check, Terraform, site or workflow job, as its pull request runs none. An affected set
  runs in one part per 30 test files, at most eight, and the whole selection in eight.
* **It runs the slow tests its affected set reaches as well** (`v1-e41-t29`). The parts run
  `not slow`; beside them the `slow-tests` job runs the slow tests of the same chosen files, with
  validate-dev's slow-tier markers, less the four tests left to validate-dev
  ([agreement 1](#1-ci-stays-light) says which, why, and the job's bound). For the whole selection it
  runs every slow test but those four.
* **Dev's push run and every promotion run everything.** A push to `dev` or `main`, a pull request
  into `main` and a dispatched run each run the whole default selection, and the `coverage` job
  measures it on every push. The dev pre-release waits for dev's push run, so a test the affected set
  missed fails there, before any release.
* **A red push run on `dev` is fixed by the next pull request, before anything else merges.** A red
  push run means a test is failing on `dev` that a pull request's affected set did not reach, or
  that two pull requests broke only together. Nothing else merges into `dev` until a pull request
  fixes it. That pull request's session runs the failing tests by
  name as well as its affected set, because the fix's own selection may not reach them.
* **A session never runs the whole default selection**, in one command or in parts. Not at red, not
  before the report, not after a sync. The whole-suite run is CI's: the pull request's `ci` check
  when the selection is the whole one, and dev's push run after every merge.
* **Nor the whole slow tier** (the PM's ruling of 2026-11-13, `v1-e41-t29`). It runs the slow tests
  of the files it changes, under the same 115-second bound, and before the report those its
  affected set reaches (`--run --slow`, below). The planted-break cases in
  `tests/scripts/test_affected_tests_planted_breaks.py` are validate-dev's alone, with no hand-off:
  one of them needs about 123 seconds on the operator's Mac, over the bound, and all of them are
  most of validate-dev's slow tier on a runner. A session that changes `scripts/affected_tests.py`
  runs that file's fast tests like any other.
* **While working, run the tests for what you are changing:** the new or changed test files, the
  test directory of the module under change, and the plan node's own acceptance command. A red run
  is the new tests alone, shown failing. Their slow tests run too, with `-m slow`, when the files
  changed hold any.
  * **A change that moves a fixture search's ranking** (a weight, the recency rule, a tie-break,
    a provider's order) greps `tests/integration` for the same query or fixture, and runs what it
    finds with `-m slow`. Those end-to-end tests pin the order and the cut of the same recorded
    searches the CLI tests do. In `v1-e08-t24` only they saw the reorder, no pull request ran
    them, and dev was red for a day. The pull request's `slow-tests` job now runs them when its
    affected set reaches them (`v1-e41-t29`); the grep finds them before the push.
* **Before the report, run the affected set once**, plus the cheap whole-repo checks:
  * the affected set, run with `uv run scripts/affected_tests.py --run` (`v1-e01-t28`). It prints
    every test file the branch's changes can reach, committed or not: through imports, directly or
    through any chain of modules, the conftest files above a test, a script or fixture a test names
    by path, and an always-run list (`tests/architecture`, `tests/specs`, the CLI's wiring tests).
    Then it runs pytest over them with CI's markers. Run it as `--run --slow` (`v1-e41-t29`): it then
    runs the slow tests those files hold, as the pull request's `slow-tests` job does, with
    validate-dev's markers, less the four tests left to validate-dev, a skip counted as a failure.
    On today's suite that is at most about a minute. `--explain` says why each file was chosen. When
    the branch changes shared test ground (`pyproject.toml`, `uv.lock`, the root `conftest.py`,
    `tests/pytest_plugins/`, `ci.yml`) it prints that the whole selection is affected and runs
    nothing: that run is CI's, or the operator's under the exception below;
  * **when the affected set would take longer than about two minutes,** the session does not hand it
    to the operator: it says so in the report and leaves it to the pull request's `ci` check, which
    runs the same affected set, or the whole selection. It still runs, within the two minutes, the
    test directories of what it changed and the always-run list (the PM's ruling of 2026-10-19,
    written in 2026-10-20);
  * `ruff format --check`, `ruff check`, `pyright packages/<changed packages>`, `lint-imports`,
    `scripts/validate_specs.py`, and the docs checks when docs changed. These take seconds.
* **A test run's time limit stops its whole process group.** A session bounds every test run it
  starts at 115 seconds with `scripts/hard_stop.py`:
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest ...`. The script runs the
  command in a process group of its own, which pytest-xdist's workers join. At the limit it sends
  TERM to the whole group, then KILL after 5 seconds, says on stderr that it stopped the run at its
  115-second limit, and exits 124. A run that finishes in time exits with its own code. The perl
  alarm sessions used before stopped only the process it was set on: on `uv` it left uv's pytest
  running (`v1-e39-t09`), and on pytest it left behind the xdist workers and the subprocesses
  their tests had started, which run on as orphans. `v1-e40-t22`'s run went on for about 30 minutes
  at a load near 50 after its alarm (`v1-e41-t05`). The group kill reaches all of them, and the
  limit still goes on `.venv/bin/python`, which skips uv's sync. A process that starts its own
  session or process group escapes the kill; pytest, xdist and the subprocesses of a test do not.
* **Tests that share process-wide state are checked in one process.** A logging filter, a logger's
  handlers or any module-level registry is shared by every test in an xdist worker, so a test can
  pass or fail, or a leak can be hidden, by which other suite ran first. When a task's tests assert
  on such state, they start from it bare and restore it, and before the report they run once with
  `-n 0 -p no:randomly` after the neighbouring suites that touch the same state. The httpx and
  httpcore loggers are the known case (`v1-e07-t01`'s CI, written in by the PM, 2026-10-21).
* **After a sync or rebase**, run the affected set again, never the whole selection.
* **When CI fails** on the pull request, the operator pastes the failing part's output into the
  session, which fixes it, runs the affected set and the failing tests, and commits; the operator
  pushes the branch again (`git -C <worktree> push`) and the open pull request runs `ci` again. The
  session is still open until `scripts/task finish`, so this costs one round trip.
* **The report records what was run**: the commands and their results, not a table of parts. The PM
  does not ask for a whole-suite run in a review.
* **Mutation runs are scoped and capped.** They target the module the task's logic lives in, run
  only the test files that cover it, and stop at about 20 mutants unless the spec asks for more.
  They are worth their time for integrity-critical rules (evidence text, removal and suppression,
  fingerprints, access control) and rarely elsewhere. Agreement 8 still applies to every run.
* **Exceptions go to the operator, not the session.** A change to shared test ground (`conftest.py`,
  `tests/pytest_plugins/`, `pyproject.toml` or `uv.lock`, the parser version with its golden
  fixtures) may deserve one whole-selection run before the pull request. The session hands it over
  as one operator command (`uv run pytest -n auto -m "not slow and not live"`, about six minutes),
  once, at the end, under agreement 2.

## 11. An operator block that changes shared state cannot be pasted wrong

Two hand-offs on 2026-10-22 went wrong for the same reason. A removal's dry run and its `--execute`
were one paste, so the plan, which listed every caselist's aggregates, was never read before they
were deleted. Then the rebuild of those aggregates ran in a window where an earlier block had left
`DEBATE_STORAGE__DATA_DIR` naming a scratch store, and it published empty aggregates to the dev
bucket. Its success check, "0 parsed", is also what an empty store prints. (Added by the PM,
2026-10-22.)

* **A command that deletes, removes, publishes or applies is two blocks.** The first is its dry run
  or plan. The prose between them says what to read in that output and what stops the operator.
  The second is the real run, with its confirmation code if it takes one. A block never holds both.
* **A block that writes shared state refuses an environment it did not set.** It starts by
  checking that no leftover `DEBATE_*` override is set (or clears it for that command with
  `env -u`), and that no `caselist pull` is running, and stops with a plain message otherwise. A
  block that sets an override for one step unsets it at the end of that step.
* **A success check tells "nothing to do" from "nothing there".** "0 parsed" or "0 uploaded" also
  describes an empty store, so a check names a count that must be above zero as well, for example
  `Sources` equal to `Skipped` and above zero.
* **The PM checks these three things** when reviewing a session's operator blocks, and a session
  writing a runbook step follows them too.

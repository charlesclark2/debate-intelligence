# Session report: v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none

| | |
|---|---|
| Task | `v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` — The spec validator refuses an unfinished task with no prerequisites unless it says why |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t27-a-task-names-its-prerequisites-or-why-it-has-none.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t27-a-task-names-its-prerequisites-or-why-it-has-none.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`scripts/validate_specs.py` now refuses any task Goal that is not `Succeeded` or `Cancelled` and has
no prerequisite, unless a `debate/no-prerequisite` annotation gives a reason. It also warns, without
refusing, when an unfinished task's description names a task id that its context does not list. The
warnings come in three kinds: an unfinished task of the same or an earlier release (likely a missing
prerequisite, printed in full), a Succeeded task (a graph link that could be added), and a task that
is never a prerequisite (a later release, or Cancelled). The last two print as counts unless
`--all-warnings` is given. The tests use invented specs
(`tests/scripts/test_validate_specs_prerequisites.py`, 31 tests). The red runs and 30 mutants are
recorded below.

The first pass found that the ruling's premise missed V2: `v2-e19-t04-privacy-legal-review`, V2's
root task, was `Blocked` with an empty context. The PM's answers of 2026-11-11 settled it: the session
added the PM's annotation to that spec (see Deviations), and a named Cancelled task now counts as
never a prerequisite. On today's dev (`7b81d85`), with that one annotation, the validator passes:
`OK: 669 files, 41 epics, 606 tasks, 22 releases`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-task-names-its-prerequisites-or-why-it` (Prerequisites named) | DONE | The rule, annotation, warnings, flag, tests, docs, and the PM's two answers |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: an unfinished task with an empty context is refused unless annotated with why, and a task id named in a description but not in the context is warned about, by tests on invented specs shown failing first, with dev's specs passing | PASS | Invented-spec tests, red runs and mutants are below. Dev's specs: `uv run scripts/validate_specs.py` → `OK: 669 files, 41 epics, 606 tasks, 22 releases`, exit 0, on `origin/dev` `7b81d85` plus this branch. The branch's only spec edits are this task's phase and the PM's annotation on v2-e19-t04 |
| Node: "Prerequisites named tests pass", `uv run pytest tests/scripts tests/specs -k validate` | PASS | `292 passed in 17.14s`, including `test_the_repository_spec_tree_is_valid` and `test_status_reports_every_release_in_the_repository`, which failed in the first pass before the annotation |

### First red run (the new tests against the old validator)

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts/test_validate_specs_prerequisites.py -n 0 -q --tb=line`
at the start commit with the old validator: **25 failed, 4 passed**. There were 29 tests then. Two
came later: the invalid-phase test, written with its fix, and the Cancelled named-task test. The
mutants below show both failing. Failures grouped by reason:

| Tests | Why they failed |
|---|---|
| 6 refusal tests (5 unfinished phases, and a context with only a `relatesTo` reference) | `assert [] == ['…names no prerequisite…']`: nothing refused |
| 4 blank-reason tests (`""`, `"   "`, `null`, `true`) | `assert [] == ['…gives no reason…']` |
| the refusal's exit and output | `(0, 'OK: 7 files…')` where `(1, <refusal line>)` was expected |
| the output with all three kinds | the OK line alone where the warning block was expected |
| `--all-warnings`, and the no-warning output | `SystemExit: 2`, unrecognized argument `--all-warnings` |
| 11 warning tests (the kinds, once only, the three "not warned" cases, the two finished phases, the baseline) | `AttributeError: 'SpecTree' object has no attribute 'warnings'` |

The 4 that passed all assert that nothing is refused (Succeeded and Cancelled exempt, an annotation
with a reason, a task that has prerequisites). They cannot fail against a validator that refuses
nothing, and the AttributeError group is a weak red for its "not warned" cases. The mutants show each
of those failing for its own reason.

### Second red run (the PM's answer 2: a Cancelled named task is never a prerequisite)

The kind's constant was first renamed `NEVER_A_PREREQUISITE` and committed alone, with all 31 tests
green (`22c5f92`), so that the red run would fail on the rule and not on a missing attribute. The
tests were then changed before the code. Result: **3 failed, 28 passed**:

- `test_a_cancelled_task_named_from_an_earlier_release_is_never_a_prerequisite`:
  `[('missing pr... work first')] == [('never a pr...rerequisite')]`. The Cancelled task was still
  the first kind.
- `test_a_missing_prerequisite_prints_in_full_and_the_other_kinds_as_counts` and
  `test_all_warnings_prints_every_kind_in_full`: the old heading, `Never a prerequisite (a task of a
  later release)`.

With the change (`1af98f4`): `31 passed`.

### Mutants on the rule

Hand-applied one at a time to `check_named_prerequisites`, `named_task_warning`, `render_warnings`
and `main`. Each was run against `tests/scripts/test_validate_specs_prerequisites.py` and restored
with `git checkout HEAD --` or from a saved copy, with `git status` clean afterwards. These tests use
no Hypothesis, so agreement 8's database rule does not apply. **30 run, 29 caught, 1 discarded as
equivalent.**

| Mutant | Result |
|---|---|
| refusal removed | caught, 11 failed |
| only Succeeded exempt (Cancelled refused) | caught, 2 failed |
| only Cancelled exempt | caught, 30 failed (the baseline's Succeeded root task is refused) |
| Succeeded and Cancelled not exempt from the refusal (warnings keep the exemption) | caught, 31 failed |
| Blocked exempt too | caught, 1 failed (`…is_refused[Blocked]`) |
| annotation ignored | caught, 5 failed |
| any annotation accepted, reason or not | caught, 4 failed |
| reason not stripped | caught, 1 failed (`"   "`) |
| reason need not be a string | caught, 1 failed (`true`) |
| a context of any reference counts as a prerequisite | caught, 1 failed (`relatesTo`) |
| annotation refused even when the task has prerequisites | caught, 1 failed |
| a phase that is not one also refused for no prerequisite | caught, 1 failed |
| warnings for finished tasks too | caught, 2 failed |
| context not excluded from warnings | caught, 1 failed |
| the task itself not excluded | caught, 1 failed |
| a repeated mention warned twice | caught, 1 failed |
| same release counted as later | caught, 3 failed |
| later release counted as earlier | caught, 3 failed |
| Succeeded named task counted as a missing prerequisite | caught, 3 failed |
| unfinished named task counted as a graph link | caught, 5 failed |
| Cancelled named task counted as a graph link (before answer 2) | survived the first run (no test named a Cancelled task); caught, 1 failed, once the test was added |
| missing prerequisites printed as counts | caught, 1 failed |
| every kind printed in full always | caught, 1 failed |
| `--all-warnings` ignored | caught, 1 failed |
| after answer 2: the Cancelled branch removed | caught, 1 failed (the Cancelled test) |
| after answer 2: Succeeded counted with Cancelled | caught, 3 failed (the graph-link test and both print tests) |
| "Succeeded and Cancelled not exempt", as first written | **discarded**: it changed a line below the exemption's `continue`, so it was equivalent to the original; rebuilt as the fourth row |

The rows before answer 2 ran on the first pass's code. The rule they exercise was unchanged by the
answer except for the Cancelled branch, which the last two rows cover. The mutant scripts and outputs
stayed in the session scratchpad.

### Checks before the report (after `scripts/task sync` onto `origin/dev` `7b81d85`)

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | **Over two minutes**: 64 of 743 test files chosen in 17.7 s. The run was stopped at its 115-second limit (exit 124) at 95%, with no F or E in the progress lines before the stop (the first pass's run stopped at about 87%, also clean). Under agreement 10 it goes to the pull request's `ci`, with no hand-off |
| Changed files' tests and the always-run list: `tests/architecture/ tests/specs/`, the three CLI wiring files, the four validator test files, `test_task_helper_unknown_prerequisites.py`, `test_check_stable_release.py`, `tests/docs/test_check_links.py`, `test_check_command_blocks.py`, `test_docs_index.py` (`-n auto`, hard stop 115) | `663 passed in 27.78s` |
| `uv run ruff format --check .` | `2057 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright scripts/validate_specs.py tests/scripts/test_validate_specs_prerequisites.py tests/scripts/test_validate_specs_epic_graphs.py tests/scripts/spec_graph_tree.py` (no package changed) | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` (after setting the phase) | `OK: 669 files, 41 epics, 606 tasks, 22 releases` |
| `uv run scripts/validate_specs.py --require-succeeded v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` | `…: Succeeded` |
| `uv run python scripts/docs_index.py --check-descriptions` | `All 69 indexed documents under docs/ have a description` |
| `uv run python scripts/check_links.py` | `OK: 3751 relative links and anchors in 642 Markdown files` (includes the new `#dependencies` anchor) |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments … (1 session reports changed since origin/dev)` |

## What the warnings say on today's dev (ruling 3)

`uv run scripts/validate_specs.py` on `origin/dev` `7b81d85` plus this branch. Its spec tree differs
from dev only by this task's phase and v2-e19-t04's annotation.

- **With this task still unfinished, as dev records it today:** 88 warnings: 21 likely missing
  prerequisites, 57 graph links, 10 never a prerequisite. Four of the 21, and one graph link, are this
  task's own description naming the five tasks of the 2026-11-09 batch.
- **With this task Succeeded, as dev will read after the merge:** **83 warnings: 17 likely missing
  prerequisites, 56 graph links that could be added, 10 never a prerequisite** (7 of a later release,
  3 Cancelled).

The 17 likely missing prerequisites, in full. Each is an unfinished task of the same or an earlier
release that the description names and the context does not list:

| Unfinished task | Names | Named task's phase, release |
|---|---|---|
| `v1-e07-t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429` | `v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke` | Pending, v1.4 |
| `v1-e31-t23-in-round-markers` | `v1-e31-t32-bold-in-part-tags` | InProgress, v1.1 |
| `v1-e32-t07-model-classification-stage` | `v1-e05-t20-prod-routes-on-the-4x-models` | Pending, v1.2 |
| `v1-e34-t21-parse-stage-bounds` | `v1-e31-t10-incremental-aggregate-rebuild` | InProgress, v1.1 |
| `v1-e37-t16-announcement-guard-follow-ups` | `v1-e37-t03-announcements` | InProgress, v1.6 |
| `v1-e38-t01-district-donation-process` | `v1-e38-t02-donation-page` | Pending, v1.6 |
| `v1-e38-t01-district-donation-process` | `v1-e38-t03-donor-recognition` | Pending, v1.6 |
| `v1-e40-t46-a-backfile-without-the-running-parsers-directory-is-named` | `v1-e39-t18-backfiles-in-the-pilot-index` | Pending, v1.7 |
| `v1-e40-t47-prods-one-time-backfile-publish` | `v1-e39-t18-backfiles-in-the-pilot-index` | Pending, v1.7 |
| `v2-e12-t01-cognito-user-pool` | `v2-e12-t03-authn-authz` | Pending, v2.0 |
| `v2-e12-t04-api-deploy` | `v2-e12-t07-promotion-pipeline` | Pending, v2.0 |
| `v2-e17-t01-library-model` | `v2-e35-t01-tub-data-model` | Pending, v2.1 |
| `v2-e17-t03-library-ui` | `v2-e35-t04-tub-ui` | Pending, v2.1 |
| `v3-e20-t01-debate-file-model` | `v2-e35-t01-tub-data-model` | Pending, v2.1 |
| `v3-e20-t02-upload-pipeline` | `v2-e35-t03-tub-api` | Pending, v2.1 |
| `v3-e20-t05-file-library-ui` | `v2-e35-t03-tub-api` | Pending, v2.1 |
| `v3-e24-t06-data-governance` | `v2-e35-t05-tub-access-and-removal` | Pending, v2.1 |

`v1-e07-t22` is new since the first pass, from PM batch 2026-11-11 (#882).

- **Graph links that could be added** (a Succeeded task of the same or an earlier release): **56**.
- **Never a prerequisite** (a later release, or Cancelled): **10**. The 3 Cancelled ones are
  v1-e05-t20 and v1-e32-t07 naming v1-e05-t17, and v1-e38-t03 naming v1-e37-t04; in the first pass
  these were in the first kind.
- `uv run scripts/validate_specs.py --all-warnings` prints both kinds in full.

## Files changed

- `scripts/validate_specs.py`: the refusal and the annotation (`check_named_prerequisites`), and the
  warnings (`named_task_warning`, `NamedTask`, `SpecTree.warnings`). Also `render_warnings`, the
  `--all-warnings` flag, and the docstring's list of checks.
- `tests/scripts/test_validate_specs_prerequisites.py` (new, 31 tests on invented specs).
- `tests/scripts/spec_graph_tree.py`: a synthetic `Task` can carry a `description` and
  `annotations`. The defaults write what they wrote before.
- `tests/scripts/test_validate_specs_epic_graphs.py`: three tests that empty an unfinished task's
  context on purpose, to test a graph rule, now annotate that task. Each still asserts its own error
  list alone (test fixtures).
- `plan_specs/v2/e19-production-readiness/t04-privacy-legal-review.yaml`: the PM's
  `debate/no-prerequisite` annotation, word for word (see Deviations).
- `plan_specs/README.md` (Dependencies) and `docs/process/task-workflow.md` (Start it, step 2): both
  rules, the annotation and the flag, in a few lines.
- `plan_specs/v1/e41-delivery-tooling-upkeep/t27-…yaml`: Goal phase `Succeeded`.
- `docs/session-reports/…` (this report).

## Deviations from the spec

- **One spec edit outside the test fixtures, by the PM's ruling of 2026-11-11.** The spec forbids "A
  spec other than a test fixture edited by the session". The ruling's premise (no unfinished task
  with an empty context) had checked V1's tasks only, and `v2-e19-t04-privacy-legal-review`, V2's
  `Blocked` root task, had `context: []`. Answer 1 had the session add, under that spec's
  `metadata.annotations`, exactly
  `debate/no-prerequisite: "V2's root task, held Blocked until V2 starts: a privacy and legal review that changes no code, so no earlier task built code it changes."`
  (commit `698b511`, alone). With it, `validate_specs.py` passes on dev's tree.
- **"Nor in its filing comment" (spec description) became "nor itself" (ruling 2).** The ruling is
  later. A filing comment is a YAML comment the validator never parses.
- **A named Cancelled task is never a prerequisite** (answer 2), not the first kind that ruling 2's
  "not Succeeded" read gave it. The third kind's heading is `Never a prerequisite (a later release,
  or Cancelled)`, capitalized like the other two headings. Its constant is now
  `NEVER_A_PREREQUISITE`, renamed from `LATER_RELEASE` to say what it holds. That makes the change a
  rename commit plus the rule, not one line.

## Decisions and assumptions

- **"Empty context" is read as no `dependsOn` TaskRef in `spec.context`.** That is the list
  `scripts/task ready` and `start` read, so a context holding only some other reference names no
  prerequisite. Every one of the 922 context entries in the first pass's tree was a dependsOn
  TaskRef, so the reading changes nothing on dev. A test pins it (`relatesTo`).
- **A reason is a non-empty string after stripping.** An empty, whitespace-only, `null` or `true`
  annotation gets its own message: the annotation gives no reason.
- **An annotation on a task that has prerequisites is ignored.** The forbidden list rules out ever
  refusing such a task.
- **A task whose phase is not a phase** (`Done`) gets the existing phase error alone, without a
  second prerequisite error on top of a typo.
- **A named id that no task declares is not a warning.** In the first pass's tree the five such ids
  are tasks' former names ("Moved from E01 as `v1-e01-t37-…`") or words broken across a line. None of
  them is another task.
- **One warning per (task, named id).** A task id named twice, or named once as a short id and once
  as a full name, is one warning.
- **A Cancelled named task in a later release** gets the later-release line. Both are the same kind.
- **The warnings print before the errors**, so a refusal is still the last thing above the error
  count. They print only when there is one, and never change the exit code. `--require-succeeded`
  prints none.

## Operator follow-ups

None. The affected set (64 test files) is over two minutes. It is left to the pull request's `ci`
check under agreement 10, with no hand-off.

## Follow-up work

- The 17 likely missing prerequisites above, plus the 56 graph links and 10 never-a-prerequisite
  mentions that `--all-warnings` lists, for the PM's next batch (ruling 3).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

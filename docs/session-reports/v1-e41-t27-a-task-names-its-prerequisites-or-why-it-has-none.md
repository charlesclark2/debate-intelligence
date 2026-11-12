# Session report: v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none

| | |
|---|---|
| Task | `v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` — The spec validator refuses an unfinished task with no prerequisites unless it says why |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t27-a-task-names-its-prerequisites-or-why-it-has-none.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t27-a-task-names-its-prerequisites-or-why-it-has-none.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`scripts/validate_specs.py` now refuses any task Goal that is not `Succeeded` or `Cancelled` and has
no prerequisite, unless a `debate/no-prerequisite` annotation gives a reason. It also warns, without
refusing, when an unfinished task's description names a task id that its context does not list. The
warnings come in the PM's three kinds: the likely missing prerequisites are printed in full, the other
two kinds as counts, and `--all-warnings` prints all three in full. The tests use invented specs
(`tests/scripts/test_validate_specs_prerequisites.py`, 31 tests). The red run against the old
validator and 26 mutants are recorded below.

**Look at this first:** the ruling says no unfinished task has an empty context after PM batch
2026-11-09, but one does. **`v2-e19-t04-privacy-legal-review`** (`Blocked`, V2's root task) has
`context: []`, so the validator refuses today's tree and the repository-tree tests fail. The session
may not edit that spec (forbidden: "A spec other than a test fixture edited by the session"), so the
Goal stays **InProgress** and ac1 is FAIL until the PM decides. The relay block under Operator
follow-ups asks the question.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-task-names-its-prerequisites-or-why-it` (Prerequisites named) | PARTIAL | The rule, warnings, flag, tests and docs are done. The node's command fails only on the two repository-tree tests, both because of v2-e19-t04 |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: an unfinished task with an empty context is refused unless annotated with why, and a task id named in a description but not in the context is warned about, by tests on invented specs shown failing first, with dev's specs passing | **FAIL** (one part) | Refusal, annotation and warnings on invented specs: PASS, red run and mutants below. **Dev's specs passing: FAIL.** `uv run scripts/validate_specs.py` → exit 1, `plan_specs/v2/e19-production-readiness/t04-privacy-legal-review.yaml: task v2-e19-t04-privacy-legal-review is Blocked and names no prerequisite: …`, `1 error(s) in 667 files` |
| Node: "Prerequisites named tests pass", `uv run pytest tests/scripts tests/specs -k validate` | **FAIL** | `2 failed, 290 passed in 20.87s`. The failures are `test_the_repository_spec_tree_is_valid` and `test_status_reports_every_release_in_the_repository`, both on v2-e19-t04. Once the PM annotates that task they pass with no code change |

### Red run (the new tests against the old validator)

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts/test_validate_specs_prerequisites.py -n 0 -q --tb=line`
at commit `40c50fe` with the old validator: **25 failed, 4 passed**. There were 29 tests then. Two
came later: the invalid-phase test, written with its fix, and the Cancelled named-task test, written
after the mutants. The mutants below show both failing. Failures grouped by reason:

| Tests | Why they failed |
|---|---|
| 6 refusal tests (5 unfinished phases, and a context with only a `relatesTo` reference) | `assert [] == ['…names no prerequisite…']`: nothing refused |
| 4 blank-reason tests (`""`, `"   "`, `null`, `true`) | `assert [] == ['…gives no reason…']` |
| the refusal's exit and output | `(0, 'OK: 7 files…')` where `(1, <refusal line>)` was expected |
| the output with all three kinds | the OK line alone where the warning block was expected |
| `--all-warnings`, and the no-warning output | `SystemExit: 2`, unrecognized argument `--all-warnings` |
| 11 warning tests (the four kinds' positions, once only, the three "not warned" cases, the two finished phases, the baseline) | `AttributeError: 'SpecTree' object has no attribute 'warnings'` |

The 4 that passed all assert that nothing is refused (Succeeded and Cancelled exempt, an annotation
with a reason, a task that has prerequisites). They cannot fail against a validator that refuses
nothing, and the AttributeError group is a weak red for its "not warned" cases. The mutants below
show each of those failing for its own reason.

### Mutants on the rule

The mutants were hand-applied one at a time to `check_named_prerequisites`, `named_task_warning`,
`render_warnings` and `main` in `scripts/validate_specs.py`. Each was run against
`tests/scripts/test_validate_specs_prerequisites.py`, and the file was restored with
`git checkout HEAD --` afterwards (`git status` clean). These tests use no Hypothesis, so agreement
8's database rule does not apply. **26 run, 25 caught, 1 discarded as equivalent.**

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
| warnings for finished tasks too | caught, 2 failed |
| context not excluded from warnings | caught, 1 failed |
| the task itself not excluded | caught, 1 failed |
| a repeated mention warned twice | caught, 1 failed |
| same release counted as later | caught, 3 failed |
| later release counted as earlier | caught, 3 failed |
| Succeeded named task counted as a missing prerequisite | caught, 3 failed |
| unfinished named task counted as a graph link | caught, 5 failed |
| Cancelled named task counted as a graph link | **survived** in the first run (no test named a Cancelled task); caught, 1 failed, after `test_a_cancelled_task_named_from_an_earlier_release_is_not_a_graph_link` was added (commit `38738df`) |
| missing prerequisites printed as counts | caught, 1 failed |
| every kind printed in full always | caught, 1 failed |
| `--all-warnings` ignored | caught, 1 failed |
| a phase that is not one also refused for no prerequisite | caught, 1 failed (`test_a_task_whose_phase_is_not_one_gets_the_phase_error_alone`) |
| "Succeeded and Cancelled not exempt" as first written | **discarded**: it changed a line below the exemption's `continue`, so it was equivalent to the original; rebuilt as the fourth row |

The mutant scripts and outputs are in the session scratchpad and are not committed.

### Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | **Over two minutes**: 64 of 743 test files chosen in 18.1 s. The run was stopped at its 115-second limit (exit 124) at about 87%, with no F or E in the roughly 2,350 tests that had run. Under agreement 10 it goes to the pull request's `ci`, not to the operator |
| Changed files' tests and the always-run list: `tests/architecture/ tests/specs/`, the three CLI wiring files, the four validator test files, `test_task_helper_unknown_prerequisites.py`, `test_check_stable_release.py`, `tests/docs/test_check_links.py`, `test_check_command_blocks.py`, `test_docs_index.py` (`-n auto`, hard stop 115) | `2 failed, 661 passed in 57.06s`: the two repository-tree tests on v2-e19-t04 |
| `uv run ruff format --check .` | `2057 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright scripts/validate_specs.py tests/scripts/test_validate_specs_prerequisites.py tests/scripts/test_validate_specs_epic_graphs.py tests/scripts/spec_graph_tree.py` (no package changed) | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | exit 1: the v2-e19-t04 refusal alone (0.86 s) |
| `uv run python scripts/docs_index.py --check-descriptions` | `All 69 indexed documents under docs/ have a description` |
| `uv run python scripts/check_links.py` | `OK: 3751 relative links and anchors in 642 Markdown files` (includes the new `#dependencies` anchor) |
| `uv run python scripts/check_command_blocks.py` | `OK: no '#' comments in 697 shell code blocks in 256 Markdown files` |

## What the warnings say on today's dev (ruling 3)

`uv run scripts/validate_specs.py` on this branch. Its spec tree is `origin/dev` at `9fdc83f` plus
this task's own phase change (`git diff origin/dev --stat -- plan_specs`: one file, one line).
**87 warnings: 23 likely missing prerequisites, 57 graph links that could be added, 7 later-release
mentions.**

Each likely missing prerequisite, in full. Each one is an unfinished task of the same or an earlier
release that the description names and the context does not list:

| Unfinished task | Names | Named task's phase, release | Note |
|---|---|---|---|
| `v1-e05-t20-prod-routes-on-the-4x-models` | `v1-e05-t17-switch-back-to-the-5-5-models` | Cancelled, v1.2 | Cancelled; see question 2 |
| `v1-e31-t23-in-round-markers` | `v1-e31-t32-bold-in-part-tags` | InProgress, v1.1 | |
| `v1-e32-t07-model-classification-stage` | `v1-e05-t17-switch-back-to-the-5-5-models` | Cancelled, v1.2 | Cancelled; see question 2 |
| `v1-e32-t07-model-classification-stage` | `v1-e05-t20-prod-routes-on-the-4x-models` | Pending, v1.2 | |
| `v1-e34-t21-parse-stage-bounds` | `v1-e31-t10-incremental-aggregate-rebuild` | InProgress, v1.1 | |
| `v1-e37-t16-announcement-guard-follow-ups` | `v1-e37-t03-announcements` | InProgress, v1.6 | |
| `v1-e38-t01-district-donation-process` | `v1-e38-t02-donation-page` | Pending, v1.6 | |
| `v1-e38-t01-district-donation-process` | `v1-e38-t03-donor-recognition` | Pending, v1.6 | |
| `v1-e38-t03-donor-recognition` | `v1-e37-t04-auto-republish` | Cancelled, v1.6 | Cancelled; see question 2 |
| `v1-e40-t46-a-backfile-without-the-running-parsers-directory-is-named` | `v1-e39-t18-backfiles-in-the-pilot-index` | Pending, v1.7 | |
| `v1-e40-t47-prods-one-time-backfile-publish` | `v1-e39-t18-backfiles-in-the-pilot-index` | Pending, v1.7 | |
| `v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` | `v1-e04-t10-snapshot-canonical-url-without-tracking-parameters` | Pending, v1.3 | this task's description lists the five tasks; gone once this task is Succeeded |
| `v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` | `v1-e07-t17-providers-without-an-adapter-pinned-to-the-factories` | Pending, v1.4 | the same |
| `v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` | `v1-e40-t46-a-backfile-without-the-running-parsers-directory-is-named` | Pending, v1.8 | the same |
| `v1-e41-t27-a-task-names-its-prerequisites-or-why-it-has-none` | `v1-e41-t21-order-dependence-checks-without-pytest-randomly` | Pending, v1.8 | the same |
| `v2-e12-t01-cognito-user-pool` | `v2-e12-t03-authn-authz` | Pending, v2.0 | |
| `v2-e12-t04-api-deploy` | `v2-e12-t07-promotion-pipeline` | Pending, v2.0 | |
| `v2-e17-t01-library-model` | `v2-e35-t01-tub-data-model` | Pending, v2.1 | |
| `v2-e17-t03-library-ui` | `v2-e35-t04-tub-ui` | Pending, v2.1 | |
| `v3-e20-t01-debate-file-model` | `v2-e35-t01-tub-data-model` | Pending, v2.1 | |
| `v3-e20-t02-upload-pipeline` | `v2-e35-t03-tub-api` | Pending, v2.1 | |
| `v3-e20-t05-file-library-ui` | `v2-e35-t03-tub-api` | Pending, v2.1 | |
| `v3-e24-t06-data-governance` | `v2-e35-t05-tub-access-and-removal` | Pending, v2.1 | |

Excluding this task's own four leaves 19 for the next batch, three of which name a Cancelled task.

- **Graph links that could be added** (a Succeeded task of the same or an earlier release): **57**.
- **Never a prerequisite** (a task of a later release): **7**.
- `uv run scripts/validate_specs.py --all-warnings` prints both kinds in full.

## Files changed

- `scripts/validate_specs.py`: the refusal and the annotation, and the warnings in three kinds
  (`check_named_prerequisites`, `named_task_warning`, `NamedTask`, `SpecTree.warnings`). Also
  `render_warnings`, the `--all-warnings` flag, and the docstring's list of checks.
- `tests/scripts/test_validate_specs_prerequisites.py` (new, 31 tests on invented specs).
- `tests/scripts/spec_graph_tree.py`: a synthetic `Task` can carry a `description` and
  `annotations`. The defaults write what they wrote before.
- `tests/scripts/test_validate_specs_epic_graphs.py`: three tests that empty an unfinished task's
  context on purpose, to test a graph rule, now annotate that task. Each still asserts its own error
  list alone (test fixtures; ruling 3 allows them).
- `plan_specs/README.md` (Dependencies) and `docs/process/task-workflow.md` (Start it, step 2): both
  rules, the annotation and the flag, in a few lines.
- `docs/session-reports/…` (this report).

## Deviations from the spec

- **Dev's specs do not pass.** The ruling and the spec both expected none, but v2-e19-t04 is an
  unfinished task with an empty context, and the session may not annotate it. ac1 stays FAIL and the
  Goal InProgress until the PM decides; see question 1.
- **"Nor in its filing comment" (spec description) became "nor itself" (ruling 2).** The ruling is
  later. A filing comment is a YAML comment the validator never parses.

## Decisions and assumptions

- **"Empty context" is read as no `dependsOn` TaskRef in `spec.context`.** That is the list
  `scripts/task ready` and `start` read, so a context holding only some other reference names no
  prerequisite. Every one of today's 922 context entries is a dependsOn TaskRef, so the reading
  changes nothing on dev. A test pins it (`relatesTo`).
- **A reason is a non-empty string after stripping.** An empty, whitespace-only, `null` or `true`
  annotation gets its own message: the annotation gives no reason.
- **An annotation on a task that has prerequisites is ignored.** The forbidden list rules out ever
  refusing such a task.
- **A task whose phase is not a phase** (`Done`) gets the existing phase error alone, without a
  second prerequisite error on top of a typo.
- **A named id that no task declares is not a warning.** On today's tree the five such ids are
  tasks' former names ("Moved from E01 as `v1-e01-t37-…`") or words broken across a line. None of
  them is another task.
- **One warning per (task, named id).** A task id named twice, or named once as a short id and once
  as a full name, is one warning.
- **A named Cancelled task is kind (a)**, as the ruling's "not Succeeded" reads (see question 2).
- **The warnings print before the errors**, so a refusal is still the last thing above the error
  count. They print only when there is one, and never change the exit code. `--require-succeeded`
  prints none.

## Operator follow-ups

Two questions for the PM, to relay as written:

```text
PM questions from v1-e41-t27 (the prerequisite rule), 2026-11-11

1. v2-e19-t04-privacy-legal-review is Blocked with context: [], so the new rule refuses dev's tree
   (the ruling expected no unfinished task with an empty context; this one is V2's root task, held
   until V2 starts). The session may not edit the spec. Options:
   (a) Recommended: you add, under its metadata.annotations,
         debate/no-prerequisite: "V2's root task: a privacy and legal review that changes no code; every other V2 and V3 task depends on it or on one held with it."
       either on this branch (tell the session and it commits your edit with your verdict) or on dev
       (the session then runs scripts/task sync). The rule needs no change.
   (b) Exempt Blocked tasks. Not recommended: a Blocked task goes back to Pending when its condition
       is met, and the refusal would then land on that unblocking edit instead of now.
   Why (a): it is the annotation's own use (the first task of a new epic), and it keeps the rule
   exactly as ruled.

2. Three of the 23 likely-missing-prerequisite warnings name a Cancelled task (v1-e05-t17 twice,
   v1-e37-t04). A Cancelled task can never be listed as a prerequisite (it would never be
   Succeeded), so these are not missing prerequisites. Options:
   (a) Keep as ruled: anything not Succeeded is the first kind (what the code does now).
   (b) Recommended: count a Cancelled named task with the third kind, "never a prerequisite", and
       say so in its heading. A one-line change plus one test.
   Why (b): it keeps the printed list down to tasks someone can act on.
```

The affected set (64 test files) is over two minutes. It is left to the pull request's `ci` check
under agreement 10, with no hand-off.

## Follow-up work

- The 19 likely missing prerequisites above, plus the 57 graph links and 7 later-release mentions
  that `--all-warnings` lists, for the PM's next batch (ruling 3).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

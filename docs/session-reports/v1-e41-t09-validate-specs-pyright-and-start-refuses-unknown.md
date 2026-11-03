# Session report: v1-e41-t09-validate-specs-pyright-and-start-refuses-unknown

| | |
|---|---|
| Task | `v1-e41-t09-validate-specs-pyright-and-start-refuses-unknown` — validate_specs.py is clean under pyright, and task start refuses an unknown prerequisite even under --force |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t09-validate-specs-pyright-and-start-refuses-unknown.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t09-validate-specs-pyright-and-start-refuses-unknown.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t09-validate-specs-pyright-and-start-refuses-unknown` |
| Session status | COMPLETE |

## Summary

`uv run pyright scripts/validate_specs.py` now reports 0 errors (10 before), with no `cast` and no
`# type: ignore`. The validator records a missing name, label or graph `goalRef` as `None` and then
refuses the tree, naming `None`. So the containers that hold those values are now typed
`str | None`, and the two places that needed a `str` narrow to one. On dev's tree it prints the same
`OK: 543 files, 41 epics, 480 tasks, 22 releases` and a byte-identical `--status`. A differential run
of the old and new validator over 1496 perturbed trees gave identical error lists for every one.

`scripts/task start` now catches `task_helper.py prereqs`' exit code past `set -e` and branches on
it:
* exit 1 (a prerequisite not yet Succeeded) still starts under `--force`, with today's warning;
* exit 2 (a prerequisite no task spec declares) refuses with exit 2, with or without `--force`;
* any other code refuses with that code.

Tests were shown failing first. All four mutants the PM asked for (one in two variants), plus a
fourth for the `set -e` capture, are caught at assertions. The PM should look first at Deviations:
`start` without `--force` on an unknown prerequisite now exits 2, not 1, because today's message
tells the operator to use `--force`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `validate-specs-pyright-and-start-refuses` (Validator pyright, start refusal) | Done | Red tests `12e08e6`, `scripts/task` `2bf4f9d`, validator `0ad5b0e`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — `pyright scripts/validate_specs.py` is clean with its tests unchanged in what they accept, and `scripts/task start --force` refuses a task with an unknown prerequisite while still starting one with an unmet one, by tests shown failing first | PASS | Pyright: `uv run pyright scripts/validate_specs.py` → `10 errors` at the start commit, `0 errors, 0 warnings, 0 informations` at `0ad5b0e`. Existing validator tests, unedited: `tests/specs/test_validate_specs.py` and `tests/scripts/test_validate_specs_epic_graphs.py` pass (88 passed with the new file, below). Start: the tests in the next section were red at `12e08e6` and green at `2bf4f9d`. |
| Node criterion "Validator pyright, start refusal tests pass" — `uv run pytest tests/scripts -k "validate_specs or task_helper or task_restart"` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts -k "validate_specs or task_helper or task_restart" -q` → `659 passed in 42.74s`. |

### Tests shown failing first

At `12e08e6` (tests only, today's `scripts/task` and validator):

* `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts/test_task_restart.py -k "prerequisite or failure_after" -n 4 -q --tb=line`
  → `3 failed, 7 passed`:
  * `test_start_refuses_a_task_whose_prerequisite_no_task_spec_declares[force]`: `assert 0 == 2`,
    with stderr `warning: starting despite unmet prerequisites (--force)`. The task was started.
  * `test_start_refuses_a_task_whose_prerequisite_no_task_spec_declares[plain]`: exit 1, with
    `error: prerequisites are not Succeeded on origin/dev; nothing was created (override with --force)`.
  * `test_start_force_refuses_when_the_prerequisite_check_itself_fails`: `assert 0 == 3`. `--force`
    started the task after `prereqs` failed with exit 3.
  * The two unmet-prerequisite tests (refused plainly with exit 1; started under `--force` with the
    warning) passed. They pin today's behaviour, which this task keeps.
* `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts/test_validate_specs_missing_values.py -n 0 -p no:randomly -q --tb=line`
  → `1 failed, 6 passed`. The failure is
  `test_epic_task_nodes_naming_no_task_and_an_undeclared_task_are_each_refused`, with
  `TypeError: '<' not supported between instances of 'str' and 'NoneType'` at
  `scripts/validate_specs.py:334`. The other six pin what today's validator refuses, and their
  hand-written error lists matched it unchanged.

At `2bf4f9d`: `test_task_restart.py` whole → `624 passed in 36.14s`. At `0ad5b0e`: the three
validator test files → `88 passed in 6.61s`.

### Unchanged behaviour of the validator

* Dev's tree: `git archive origin/dev plan_specs` (dev at `4b29946`) into the scratchpad, then
  `uv run scripts/validate_specs.py --root <that copy>` → `OK: 543 files, 41 epics, 480 tasks, 22 releases`,
  the same line as before the change. The same on this branch.
* `uv run scripts/validate_specs.py --status`, before and after → byte-identical (`cmp`).
* Differential: a scratch script loaded the start commit's `validate_specs.py` and the new one. For
  every value in every document of the synthetic baseline tree (`spec_graph_tree.baseline()`), it
  made four trees: the value deleted, set to null, set to `7`, and set to `[]`. It then compared the
  full outcome of `collect()` (the error list, or the exception raised) between the two validators.
  Result: `1496 perturbed trees, 1496 identical outcomes, 0 different`; `accept/refuse changed: 0`.
  The check is not vacuous: on mutant 3 below it reported `20 different`. It changes one value at a
  time, so it cannot reach the one deliberate difference (two missing values in one epic graph,
  under Decisions), which the red test covers.

### Mutants

Each run used a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`. None of these tests is a Hypothesis
property, but the files hold some. Each mutant was restored with `git checkout HEAD --` after its
run, and `git status --porcelain` was empty afterwards. Every catch is an assertion failure, not a
crash.

| Mutant | Result |
|---|---|
| 1. `--force` overrides exit 2 again (`1)` → `1\|2)` in `start`'s `case`) | Caught: `test_start_refuses_a_task_whose_prerequisite_no_task_spec_declares[plain]` and `[force]` fail at `assert result.returncode == 2` (`1 == 2` and `0 == 2`). 2 failed, 3 passed. |
| 2. `--force` refuses exit 1 (the warning replaced by `die`) | Caught: `test_start_force_starts_a_task_whose_prerequisite_is_not_yet_succeeded`. 1 failed, 4 passed. |
| 3. A pyright fix that changes what the validator accepts: in `check_epics`, keep only `str` goalRefs (`isinstance(ref := ..., str)`) and drop `key=str` | `uv run pyright scripts/validate_specs.py` → `0 errors`: pyright cannot tell this fix from the real one. The validator then **accepts** an epic whose graph has a Task node naming no task: `errors == []`, where today's refuses it with `epic Plan lists None but no task file declares it`. Caught: `test_an_epic_task_node_that_names_no_task_is_refused` (`assert [] == [...]`) and `test_epic_task_nodes_naming_no_task_and_an_undeclared_task_are_each_refused`. 2 failed, 86 passed. The existing suites (`tests/specs/test_validate_specs.py`, the epic-graph tests) do not catch it. |
| 3, second field. The same `isinstance` filter on a release Plan's External-node goalRefs (`release_epics`) | Pyright `0 errors`. The validator accepts a release whose Plan has an External node naming no epic (today: `unknown epic None`). Caught: `test_a_release_node_that_names_no_epic_is_refused` only. 1 failed, 87 passed. |
| 4. The `set -e` trap: `helper "$wt" prereqs "$task"; prereqs_status=$?` (a bare call) | Caught: all five prerequisite tests fail, because `set -e` stops `start` at the failing call, before the `case` decides. This is why the code is caught with `\|\|`. |

### Checks before the report

* Affected set: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run`
  → `1831 passed in 66.43s`, `Affected set: 39 test files, pytest exited 0 after 68 s.`
* `uv run ruff format --check` and `uv run ruff check` on the three changed Python files →
  `3 files already formatted`, `All checks passed!`
* `uv run pyright scripts/validate_specs.py tests/scripts/test_validate_specs_missing_values.py tests/scripts/test_task_restart.py`
  → `0 errors, 0 warnings, 0 informations`. No package under `packages/` changed.
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`
* `shellcheck scripts/task` → clean.
* `uv run scripts/validate_specs.py` (after setting the phase) → `OK: 543 files, 41 epics, 480 tasks, 22 releases`.

## Files changed

* `scripts/validate_specs.py`: the typing fix. `SpecTree.names`, `goals`, `epic_tasks`,
  `task_release`, `task_epic` and `release_epics` are typed `str | None` where the validator really
  stores `None`, with a comment saying why. This follows `by_kind` and `in_graph`, which were
  already typed that way. `read_release` reads the version from the file name, which the label is
  checked against, so it is a `str`. `check_prerequisites` binds both releases to locals so the
  `in order` check narrows them. `main` annotates `--require-succeeded` as `str`. `check_epics`
  sorts with `key=str`.
* `scripts/task`: `start` catches `prereqs`' exit code with `||` and decides with a `case`. A new
  `die_with <code> <message>` sits beside `die`, which always exits 1.
* `tests/scripts/test_validate_specs_missing_values.py` (new): seven tests on the values whose types
  changed. Each removes one value from the synthetic tree and asserts the whole error list, written
  by hand.
* `tests/scripts/test_task_restart.py`: five tests (one parametrized into two) for `start` and its
  prerequisites, in a new section. `spec_text` takes an optional `context`. The `uv` stub's forced
  helper failure can exit with a chosen code (`fail_code`, default 1, which is what the existing
  tests use).
* The task spec's phase and this report.

## Deviations from the spec

* **An unknown prerequisite without `--force` now exits 2, not 1, with a new message.** The PM's
  context said "Without `--force`, both refuse as today". It still refuses. But today's refusal
  exits 1 with `prerequisites are not Succeeded on origin/dev; nothing was created (override with --force)`,
  which tells the operator to use the override that now refuses. So exit 2 (`prereqs`' "spec error"
  code) gets one message whatever the flags:
  `<task>'s spec.context names a prerequisite no task spec declares (above); --force does not override that. Fix the spec on dev; nothing was created`.
  The line above it is the helper's, naming the prerequisite. An unmet prerequisite without
  `--force` is unchanged: exit 1, same message.
* **`--force` no longer overrides a `prereqs` failure other than exit 1.** Before, `--force`
  overrode any non-zero exit, including uv failing to run the helper. Now any code other than 0, 1
  and 2 refuses with that code and `task_helper.py prereqs exited <code>; nothing was created`. A
  Python traceback in the helper exits 1, so it is still indistinguishable from an unmet
  prerequisite. That was already true and is out of scope.

## Decisions and assumptions

* **No `cast` and no validated model.** Every error was a missing value that the validator
  deliberately keeps as `None` and later refuses. Typing the containers as what they hold was the
  smallest true statement. A model or an `isinstance` accessor would have to decide what a
  non-string or missing name means, and mutant 3 shows the obvious decision changes acceptance.
  Values pyright cannot see into (a non-string name, such as `name: 123`) stay as they are, because
  documents are bare `dict`s. The comment on `SpecTree` says missing values are kept as `None` on
  purpose.
* **One deliberate difference, which does not change acceptance:** an epic graph with a Task node
  naming no task *and* a Task node naming an undeclared task used to crash the validator with
  `TypeError` (still a refusal: exit 1, with a traceback). It is now refused with both lines, `None`
  sorted as the string `"None"`. `key=str` leaves the order of an all-string list unchanged. The
  red test is `test_epic_task_nodes_naming_no_task_and_an_undeclared_task_are_each_refused`.
* The `start` tests live in `test_task_restart.py`, so the spec's `-k "... or task_restart"` selects
  them and they reuse its throwaway repository, stubs and rollback assertions. The validator tests
  are in a new `tests/scripts/test_validate_specs_missing_values.py`, which matches `-k validate_specs`.
* `ROADMAP.md` and `docs/README.md` were not touched. Dev moved during the session (v1-e40-t26
  merged); none of its files overlap this branch's.

## Operator follow-ups

None.

## Follow-up work

* **Recommendation: add `scripts/validate_specs.py` to CI's pyright scope** so it stays clean.
  CI runs a bare `uv run --frozen pyright`, whose scope is `[tool.pyright].include` in
  `pyproject.toml` (`packages`, `tests/architecture`, `tests/smoke`). Adding the file there is one
  line. It is a `pyproject.toml` change, which makes the affected selection whole, so it is better
  as its own small upkeep task than folded into a task with tests to select. Pyright over all of
  `scripts/` still reports 12 errors, in eight other files (`run_parser_eval.py` 4,
  `scrub_docx_fixture.py` 2, and one each in `compare_docx_roundtrip.py`, `parser_corpus_health.py`,
  `plan_eval_sampling.py`, `prelabel_docx.py`, `sample_card_boundaries.py`, `select_eval_files.py`).
  So the include should name files, not the directory, until those are cleared. `task_helper.py`
  and `affected_tests.py` are already clean.
* The existing validator suites caught neither variant of mutant 3. A missing value in a graph
  reference was only refused by accident of storing `None`. The new tests now pin it. No further
  work is proposed.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

Both leftovers closed. Mutant 3 turned up a real point: pyright alone cannot tell a typing fix that
changes acceptance from one that doesn't.
1. **pyright:** 10 errors → 0, with no `cast` and no ignore. The containers are typed as what they
   really hold, `str | None` where the validator keeps a missing value to refuse it later. That is
   the smallest true statement, and the `SpecTree` comment says why.
2. **Unchanged acceptance, shown three ways:**
   * dev's tree prints the same OK line;
   * `--status` is byte-identical;
   * the 1,496-tree differential run of the old and new validators gives identical outcomes, and is
     shown not to be vacuous (mutant 3 gave 20 different).

   The one intended difference, a `TypeError` crash becoming a named refusal, refuses either way, and
   the red test covers it.
3. **start.** `prereqs`' code is captured past `set -e` with `||` and decided by a `case`:
   * exit 1 starts under `--force`, with the warning;
   * exit 2 refuses with or without it;
   * anything else refuses with its code.

   Mutant 4, a bare call stopped by `set -e`, shows why the capture is written that way.
4. **Mutants:** five, all caught at assertions. Mutant 3 in two fields, each pyright-clean, accepted a
   graph node naming nothing, and the new missing-value tests are the only thing that catches it.
5. **Deviations accepted.**
   * Exit 2 without `--force` gets its own message, because the old one advised the override that no
     longer works.
   * `--force` no longer overrides a helper failure other than exit 1. That is the right reading of
     "override an unmet prerequisite".
6. **Follow-up: yes, one p3 E41 task in the next PM batch.** CI's pyright `include` gains
   `scripts/validate_specs.py`, `scripts/task_helper.py` and `scripts/affected_tests.py` by name.
   The other eight scripts' 12 errors are left out of scope until someone clears them.
7. **Closing checks:** the affected set ran whole within the limit (39 files, 1,831 passed). ruff,
   pyright, lint-imports (20), shellcheck and the specs are clean.
8. **Merge:** a plain `scripts/task pr` once `ci` is green.

# Session report: v1-e41-t07-spec-graph-checks

| | |
|---|---|
| Task | `v1-e41-t07-spec-graph-checks` — The spec validator holds each epic's graph to its tasks' prerequisites, and the task helper refuses a prerequisite it cannot find |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t07-spec-graph-checks.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t07-spec-graph-checks.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t07-spec-graph-checks` |
| Session status | COMPLETE |

## Summary

`scripts/validate_specs.py` now holds each epic's graph to its tasks' `spec.context`, in both
directions. A Task node's `dependsOn` must name exactly its task's prerequisites, a same-epic one
through that task's node and a cross-epic one through an External node. An External node must name
a task of another epic from the epic's release or an earlier one. An epic Goal may be Succeeded only
when every task in it is Succeeded or Cancelled. I extended that rule to release Goals over their
epics, as the PM invited. `scripts/task_helper.py ready` now leaves out a task whose prerequisite no
task spec declares, and says why on stderr. Before, it counted such a prerequisite as met. `prereqs`
marks one `UNKNOWN` and exits 2. The two pyright errors in task_helper.py are cleared.
After `scripts/task sync`, dev's tree at `a01f789` passes every new check, so nothing outside this
task's files had to change. Things to look at first: the message wording (each names the epic file,
the node and the task) and two choices under Decisions. `ready` warns rather than failing, and
External nodes that name no task, or a task of their own epic, are also refused.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `spec-graph-checks` (Spec graph checks) | Done | Tests written first and shown red (20 failed, 8 passed), then the validator, the helper and `plan_specs/README.md`; 9 mutants, all caught |

## Acceptance criteria

All commands were run in the task worktree after `scripts/task sync` onto `origin/dev` at `a01f789`.
Test runs were bounded with `.venv/bin/python scripts/hard_stop.py 115 ...`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: the validator refuses a graph edge missing from a task's context, a context prerequisite missing from the graph, an External node in a later release and a Succeeded epic with an open task; `task ready` and `task prereqs` refuse an unknown prerequisite; dev's spec tree passes; by tests shown failing first | PASS | Red run, before any script changed: `pytest tests/scripts/test_validate_specs_epic_graphs.py tests/scripts/test_task_helper_unknown_prerequisites.py -n 0 -p no:randomly` → `20 failed, 8 passed`. All 20 failures are assertion failures; none failed at collection or setup. The 8 that passed are the five clean trees and the three helper baselines. The same files after the change → `28 passed`. Dev's tree: `uv run scripts/validate_specs.py --root <git archive origin/dev plan_specs>` → `OK: 527 files, 41 epics, 464 tasks, 22 releases`, exit 0, at `a01f789`. `task_helper.py ready` over the same export → exit 0, 49 tasks listed, nothing on stderr. Mutants: see below |
| Node `spec-graph-checks`: Spec graph checks tests pass (`uv run pytest tests/scripts -k "validate_specs or task_helper"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/scripts -k "validate_specs or task_helper"` → `28 passed in 16.09s`, exit 0 |
| Epic E41 node t07: `uv run scripts/validate_specs.py --require-succeeded v1-e41-t07-spec-graph-checks` | PASS | → `v1-e41-t07-spec-graph-checks: Succeeded` |

### Mutants (agreement 8)

Each mutant was applied to the committed script, run against the two new test files with
`-n 0 -p no:randomly`, and then restored with `git checkout HEAD --`. These tests use no Hypothesis.
Each run still had a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY`.

| Mutant | Caught by |
|---|---|
| 1 (PM): graph-to-context direction unchecked | 2 tests: same-epic and cross-epic edge missing from the context |
| 2 (PM): context-to-graph direction unchecked | 4 tests: same-epic and cross-epic prerequisite missing from the graph, an unused External node, the command-line exit |
| 3 (PM): an External node's release unchecked | 2 tests: an unused External node, and one an edge uses, both naming a later release |
| 4 (PM): a Succeeded epic with an open task accepted | 6 tests: one per open phase (Pending, Ready, InProgress, Blocked, Failed), and a test that every open task is named |
| 5 (PM): `ready` treats an unknown prerequisite as met | 2 tests: `ready` listed the task (assertion on stdout). See the note below |
| 6: a Succeeded release with an open epic accepted | 1 test |
| 7: an External node naming a task of its own epic accepted | 1 test |
| 8: an External node naming no task accepted | 1 test |
| 9: `prereqs` lets an unknown prerequisite through (exit 0) | 1 test |

My first version of mutant 5 only disabled the new branch. `ready` then crashed with a `KeyError`
on the unknown name instead of listing the task, so that catch proved nothing and I don't count it.
The counted run restores the old `if p in goals` filter, and the failing assertions show the task
listed as ready.

### Before the report (agreement 10)

| Check | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | `48 of 590 test files` chosen from 8 changed files; `2185 passed in 91.45s`; `pytest exited 0 after 94 s` (112 s with the selection, at a load average near 20) |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1653 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright scripts/task_helper.py` and the three new test files | `0 errors` (task_helper.py had 2 at the start: lines 61 and 438) |
| `uv run --frozen pyright` (CI's scope) | `0 errors`, 21 s |
| `uv run --frozen pyright scripts/validate_specs.py` | `10 errors`, the same count as at the start commit; see Follow-up work |
| `uv run --frozen lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 527 files, 41 epics, 464 tasks, 22 releases` |
| `scripts/check_command_blocks.py`, `check_thin_handlers.py`, `docs_index.py --check-descriptions`, `check_links.py`, `pre-commit run check-merge-conflict` | all OK |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/specs tests/scripts/test_task_restart.py tests/scripts/test_task_validate_dev_status.py` and the new files | `709 passed`. These are the older validator tests, including `test_the_repository_spec_tree_is_valid` and the `minimal_valid` fixture, which already obeys the new rules, plus the shell tests of `scripts/task` |

## Files changed

* `scripts/validate_specs.py`: new `check_epic_graphs` (with `check_task_node`,
  `check_external_node`) and `check_closed_goals`, a `release_goals` map, and the docstring's checks
  list.
* `scripts/task_helper.py`: `ready` and `prereqs` refuse an unknown prerequisite. `die` is
  `NoReturn`, and `main` passes `die` a string, which clears the two pyright errors.
* `tests/scripts/spec_graph_tree.py` (new): a builder for synthetic spec trees. By default an epic's
  graph is drawn from its tasks' contexts, and a test changes the one thing it is about.
* `tests/scripts/test_validate_specs_epic_graphs.py`, `tests/scripts/test_task_helper_unknown_prerequisites.py`
  (new): one test per refusal plus the clean trees. Each test compares the whole error list against
  messages written by hand.
* `plan_specs/README.md`: the Dependencies section and the Status lifecycle paragraph now say what
  is enforced.
* The task spec's phase, and this report.

## Deviations from the spec

None. The PM's context asked me to name here any edit to dev's specs. None was needed: dev's tree at
`a01f789` (after PM batch 2026-11-01b and v1-e40-t07 merged) passes every new check.

## Decisions and assumptions

* **Release Goals too.** A release Goal marked Succeeded is refused while one of its epics (the epics
  labelled with that release) is not Succeeded or Cancelled. v1.0 is the only Succeeded release, and
  its three epics are Succeeded.
* **Two refusals beyond the four named.** An External node in an epic graph that names a task of the
  same epic is refused, and so is one that names no task. Both follow from "a same-epic node, or an
  External node per cross-epic one", and the second keeps a mistyped `goalRef` from slipping past
  the release check. Dev has neither: all 259 External nodes name a task of another epic. I did not
  refuse an unused External node that is otherwise sound.
* **Messages are filed against the epic file.** The graph and the context can each be the wrong
  side. The message names the epic file, the node and the task, and says which list lacks the name.
  A context prerequisite missing from the graph also says how to draw it: "depend on node t01", or
  "depend on an External node for it".
* **`ready` warns and goes on.** A task with an unknown prerequisite is not listed, and stderr says
  `<task> is not listed: its spec.context names <name>, which no task spec declares`. The command
  still exits 0. `scripts/task ready` runs it inside `rows="$(...)"` under `set -e`, so a non-zero
  exit would hide every other ready task and leave its temporary directory behind.
* **`prereqs` exits 2 on an unknown prerequisite.** That is the helper's code for a spec error. Exit 1
  still means "not Succeeded yet". Before this change it already exited 1, printing
  `BLOCKED <name> (MISSING)`. Now it prints `UNKNOWN <name> (no task spec declares it)` and a stderr
  line naming the task's context. `scripts/task start` refuses on any non-zero exit, so a start
  without `--force` stops. `--force`, the operator's override for unmet prerequisites, still
  overrides it. I left `scripts/task` unchanged because the validator keeps such a tree off dev.
* **Empty contexts are not refused.** The audit found PM-filed tasks with no prerequisites. A root
  task legitimately has none, so no check can tell the two apart, and the README's follow-up rule
  stays a review rule.
* **The tests live in `tests/scripts`**, the spec's package, rather than beside the older validator
  tests in `tests/specs`. They build their own trees instead of copying `tests/specs/fixtures/minimal_valid`.

## Operator follow-ups

None.

## Follow-up work

* `scripts/validate_specs.py` carries 10 pyright errors, all `str | None` read from YAML
  (`pyright scripts/validate_specs.py`). CI's pyright scope leaves `scripts/` out, so nothing fails
  on them. This task added none. Clearing them would be a small E41 upkeep task like this one's
  task_helper.py amendment.
* `scripts/task start --force` still starts a task whose prerequisite is unknown (see Decisions). If
  the PM wants that refused even under `--force`, `start` can tell exit 2 from exit 1 (E41).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The validator now refuses the drift the dependency audit cleaned up, and the task helper no longer
counts an unknown prerequisite as met.
1. **ac1 passes.**
   * Red: 20 failed and 8 passed, the 8 being the clean trees and baselines, every failure an
     assertion. Green: 28 passed.
   * Dev's tree at `a01f789` passes every new check, with nothing outside this task changed.
   * Nine mutants were caught. You discarded mutant 5's first form, which crashed rather than listing
     the task, and redid it with the old filter restored. That is the right standard.
2. **Decisions accepted:**
   * release Goals checked over their epics;
   * External nodes that name no task, or a task of their own epic, refused;
   * messages filed against the epic file, naming which side lacks the name and how to draw it;
   * `ready` warning and exiting 0, because of `scripts/task`'s `set -e` capture;
   * `prereqs` exiting 2 for a spec error, apart from 1 for not yet Succeeded;
   * empty contexts not refused, since a root task has none. The README's follow-up rule stays a
     review rule, and the PM follows it.
3. **Follow-ups:** one p3 E41 task in the next PM batch.
   * The 10 pyright errors in `validate_specs.py`.
   * `scripts/task start` refusing an unknown prerequisite even under `--force`. `--force` overrides
     an unmet prerequisite, not a spec error, so `start` should tell exit 2 from exit 1.
4. **Closing checks:** the affected set ran whole within the limit (48 files, 2,185 passed). pyright
   over CI's scope and over task_helper.py is clean, and the whole-repo checks pass.
5. **Merge:** once the PR's `ci` is green. It is a plain `scripts/task pr`. From then on a batch that
   breaks the graph is refused by `validate_specs.py` before it reaches dev.

# Session report: v1-e41-t06-container-imports-read-by-use

| | |
|---|---|
| Task | `v1-e41-t06-container-imports-read-by-use` — An import change in container.py that loads no new module reaches only the parts using its names |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t06-container-imports-read-by-use.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t06-container-imports-read-by-use.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t06-container-imports-read-by-use` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`scripts/affected_tests.py` now reads a change to `container.py`'s top-level imports by use, as
the PM ruled on t43's question 1 (b). The script works out which modules each side's imports load,
and in what order. When both sides load the same modules in the same order, nothing new runs on
import. The change then reaches only the parts that use a name it rebinds, the files that import
that name from the container, and the callers of those parts. A module loaded, or no longer loaded,
is still the whole file. A `"debate_cli.container.X"` string now reaches part X, or names a
module-level name X, which is reached when an import rebinds it and otherwise only as the whole
file. `--whole-container` turns off both new readings.

**Measured over t43's six merges** (graph tree: the start commit, 586 test files; "whole" is now 177
files, where t43's tree gave 198):

- **af7052e's edit alone: 177 → 77 files.** This is the case the PM named, below t43's scratch
  variant's 110, because the new string reading also drops the bucket-mode suite.
- f5a8221's edit alone: 89 → 80; 65f56d7's: 144 → 143.
- 030cc4c and f5d9cb7 each load a new module (`…models.usage`, `debate_cli.build_info`), so they
  stay whole. ec02c33 changes a module constant, so it stays whole too.

No list gains a file. Each of the 100 dropped test files was run with the changed parts recorded:
none starts its own merge's changed part.

**The Goal is `Succeeded`.** ac1 passed in the session, the node criterion passed, and all 22
mutants were caught. PM mutants 1 and 3 each show the forbidden item caught: mutant 3 on a planted
real break, where it leaves out a test file with 21 failing tests.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `container-imports-read-by-use` (Imports by use) | Done | Six commits, listed under Files changed. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: t43's six merges re-measured, and af7052e's edit alone selects fewer files | PASS | [The measurements](#ac1-the-measurements), below. af7052e's edit alone: **177 → 77**, read by part with `MODEL_PROFILE_SETTING` rebound. |
| ac1: an import loading a new module is still the whole file | PASS | 030cc4c and f5d9cb7, merge and edit alone, → `container.py is read as one file: it loads debate_core.integrations.models.usage, which its imports did not load before (line 271)` and `… debate_cli.build_info … (line 152)`. Each selects what `dev`'s script selects. Cases: an import added, `from a import b` loading a submodule, the same import outside `if TYPE_CHECKING:`, and a module no longer loaded. |
| ac1: a `debate_cli.container.X` string reaches part X | PASS | Real tree: a scratch commit changing `_utc_now`'s code. `--explain` gives `packages/debate_cli/tests/test_tub_index_prune.py <- asks for debate_cli.container's _utc_now (…container.py), which changed`, and that file names the container only as `"debate_cli.container._utc_now"`. Cases: `ServiceContainer.verified` and a function beside the container each reach their part and not another, and `"debate_cli.container.RULES"` is reached only when RULES is rebound or the change is read whole. |
| ac1: every after-list is a subset of before | PASS | All 12 diffs: `comm -13 before after` → 0 lines each. The same holds for the planted break, the `_utc_now` scratch commit and dev's newest `container.py` merge (82c7348, v1-e40-t08: 282 → 281, read by use). |
| ac1: nothing collected is lost (PM: a run check over the dropped files) | PASS | Every file dropped by the three diffs read more narrowly (100 files; af7052e's list holds the other two) was run with t43's `sys.monitoring` recorder in scratch, watching the four changed parts. Result: **1,468 passed, 0 failed**, in five runs (below). No dropped file started its own merge's changed part. Positive control: `commands/test_doctor_evidence_profiles.py` → 22 passed, with 25 starts each of `evidence_profile_check` and `_build_evidence_profile_check`. Collected cases: 117 at the start commit, 144 now; 28 added, 1 replaced (Decision 6). |
| ac1: tests shown failing first | PASS | [Red runs](#the-red-runs), below. Over the 28 new or changed cases: **20 failed, 8 passed** against a skeleton, and **21 failed, 7 passed** against `origin/dev`'s script. |
| PM: mutants 1 to 4, with 1 and 3 showing the forbidden item caught | PASS | 22 mutants, [below](#mutation-run), all caught. Mutant 1 fails the three new-module cases as missing selections. Over the real tree it drops 12 files from f5d9cb7's edit alone and 89 from 030cc4c's. Mutant 3 fails six cases as missing selections. On a planted break (`FileBuildService` imported under another name, still used by `_build_file_build`), the branch selects 80 files and mutant 3 selects 38. One file mutant 3 drops, `commands/test_files.py`, has 21 failing tests on that break (`NameError`). |
| Node `container-imports-read-by-use`: `uv run pytest tests/scripts -k affected` | PASS | At `380bcbe`: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts -k affected -p no:cacheprovider -q` → `174 passed in 56.39s`. |

### ac1: the measurements

**Method.** t43's recipe:

- "Before" is the start commit's script, which is byte-identical to `origin/dev`'s (`cmp`).
- "After" is this branch's script.
- Both run with `--diff <commit> --graph 033060e`, so the tree is the same for both.
- "Alone" is a local, unreferenced commit made with `git commit-tree`. It holds only that merge's
  `container.py` on the merge's first parent. Nothing was pushed.

The counts differ from t43's because the tree has grown (586 test files) and v1-e01-t44 changed how
mentions are read.

| Diff | Before | After | Dropped | Added | How the branch reads `container.py` |
|---|---|---|---|---|---|
| `030cc4c` merge | 477 | 477 | 0 | 0 | whole: it loads `debate_core.integrations.models.usage` (line 271) |
| `030cc4c` alone | 177 | 177 | 0 | 0 | the same |
| `65f56d7` merge | 276 | 276 | 0 | 0 | by part: `_build_caselist_status` |
| `65f56d7` alone | 144 | **143** | 1 | 0 | the same |
| `f5a8221` merge | 339 | 339 | 0 | 0 | by part: `_build_file_build` |
| `f5a8221` alone | 89 | **80** | 9 | 0 | the same |
| `af7052e` merge | 413 | 413 | 0 | 0 | by part: `_build_evidence_profile_check`, `evidence_profile_check`; rebinds `MODEL_PROFILE_SETTING` |
| `af7052e` alone | 177 | **77** | 100 | 0 | the same |
| `ec02c33` merge | 250 | 250 | 0 | 0 | whole: a module constant (line 407); its imports also load new modules |
| `ec02c33` alone | 177 | 177 | 0 | 0 | the same |
| `f5d9cb7` merge | 192 | 192 | 0 | 0 | whole: it loads `debate_cli.build_info` (line 152) |
| `f5d9cb7` alone | 177 | 177 | 0 | 0 | the same |

Notes on the table:

- **`--whole-container` gives exactly `dev`'s `--whole-container` output** on all 12 diffs (`cmp`
  of the sorted lists).
- **Why no merge drops files:** the other files each merge changes reach every file its
  `container.py` edit no longer does.
- **What af7052e's edit alone drops:**
  - the seven bucket-mode test files, which `bucket_mode/conftest.py`'s
    `"debate_cli.container.ProcessPoolParseRunner"` and `"…_utc_now"` strings used to take;
  - `commands/test_caselist_pull_parses.py` and `commands/test_files.py`, which name
    `ProcessPoolParseRunner` the same way;
  - about 90 files that the whole-file reading reached through the container's importers.

**The run check.** The 100 dropped files were run with the recorder on `PYTHONPATH`. Every run had
a new `HYPOTHESIS_STORAGE_DIRECTORY` and a `--basetemp` in scratch. The machine's load was between
6 and 26 from other work, so one run over all of them was stopped at 115 s (at 90%), and so were two
halves (at 92% and 82%). Four interleaved quarters followed:

| Run | Result |
|---|---|
| quarter 0 | `456 passed in 44.59s` |
| quarter 1 | `230 passed in 36.52s` |
| quarter 2 (stopped at 82%), then its two halves | `166 passed in 101.27s` and `183 passed in 35.39s` |
| quarter 3 | `433 passed, 2 warnings in 112.21s` |

The quarters' union equals the dropped list (`cmp` under `LC_ALL=C`). No run left a worker behind
(`pgrep`).

What the recorder saw:

- Starts of `_build_caselist_status`, in 14 dropped files. They are dropped for f5a8221 or
  af7052e, never for 65f56d7, whose changed part this is. For 65f56d7 they are still selected.
- Starts of `_build_file_build`, in `commands/test_files.py`. It is dropped for af7052e, not for
  f5a8221.
- No start of either af7052e part.

### The red runs

The 28 cases are chosen with `-k` on their names. Each run had a new
`HYPOTHESIS_STORAGE_DIRECTORY`, and the script was restored with `git checkout HEAD --` afterwards.

- **The skeleton** keeps the plumbing but reads every import change as rebinding nothing, and
  records no container names. It is the committed script with `return frozenset()` as the first
  line of `imports_by_use` and a bare `return` as the first line of `add_container_names`.
  → `20 failed, 8 passed`.
  - 15 of the failures are selections that miss files (`missing: [...]`). The others are a reason
    or note not printed, and one explain `KeyError`.
  - The 8 that pass pin readings the skeleton keeps from t43: imports below module code and star
    imports read as module code, a part-local import, the whole file, the renamed import's whole
    reading, the module named another way, and both `--whole-container` cases.
- **`origin/dev`'s script**, checked out over the file. → `21 failed, 7 passed`. The by-use cases
  select the whole file (`missing: [], extra: [...]`), the new reasons are not printed, and the
  string cases over-select.
- **Green at HEAD:** all 144 cases pass.

A case for a string naming a function beside the container was added after these runs, since no
case covered that form. Against the skeleton, its "another part" side fails (`1 failed, 1 passed`).

### Mutation run

22 mutants were run against `09e1fa3`; `380bcbe` after it changes only the docstring and `--help`.
Each mutant is an exact replacement in the committed script, run against the whole of
`tests/scripts/test_affected_tests.py`. Each run had a new `HYPOTHESIS_STORAGE_DIRECTORY`. The
script was restored with `git checkout HEAD --` after each run, and the driver asserted a clean tree.
Every catch below is an assertion failure; none is a collection error.

| # | Mutant | Result |
|---|---|---|
| 1 | **PM:** a newly loaded module read by use (the module one side newly loads is not seen) | caught: 3, an import added, `from a import b` loading `a.b`, and the import outside `TYPE_CHECKING`, each as missing selections. Over the real tree, f5d9cb7's edit alone loses 12 files and 030cc4c's 89. |
| 2 | **PM:** a removed import that unloads a module read by use | caught: 1, a module no longer loaded |
| 3 | **PM:** a rebinding missed, so a part using the name is left out | caught: 6, every by-use case with a part, as missing selections. Over the planted break it drops 42 of the branch's 80 files, `commands/test_files.py` among them. |
| 4 | **PM:** a `container.X` string for a module-level name read as part-local | caught: 3, the rebound name, its explain, and `--whole-container`'s by-use case |
| 5 | an import for the type checker counted as loading its module | caught: 1 |
| 6 | an `if TYPE_CHECKING:` block read as module code | caught: 1 |
| 7 | `import a.b` loading only `a.b` | caught: 1 (after `cded5ec` made that import the first to load `a`) |
| 8 | `from a import b` always counting `a.b` as loaded | caught: 11 |
| 9 | `from a import b` never counting `a.b` as loaded | caught: 1 |
| 10 | the load order ignored (the loads compared as sets) | caught: 1 |
| 11 | a rebound name that code run on import uses, read by use | caught: 2 |
| 12 | a rebound name that a definition binds too, read by use | caught: 1 |
| 13 | names read by a computed name (`globals()`) ignored | caught: 1 |
| 14 | an import below module code read by use | caught: 1 |
| 15 | a star import read by use | caught: 1 |
| 16 | a name in a string run on import (`__all__`) ignored | caught: 1 |
| 17 | a name bound to another target missed (only names added or removed) | caught: 7 |
| 18 | a file importing a rebound name from the container not reached | caught: 3 |
| 19 | files naming the container only by its names still reached by the module's name | caught: 3, each over-selecting |
| 20 | a string naming a function beside the container asks for nothing | caught: 1 |
| 21 | a string naming `ServiceContainer.X` asks for nothing | caught: 4 |
| 22 | `--whole-container` keeps the strings' edges | caught: 1 |

Two changes came out of the run:

- **Mutant 7 first survived.** In the case it was aimed at, a line above had already loaded `a`.
  `cded5ec` reorders that case's setup so that `import a.b` is what first loads `a`.
- **Mutant 1, as first written, was caught only by its reason text.** It disabled the "loads a new
  module" check. The order check, which compared the two load lists, still read the change as
  whole, so the selection did not show the mutant (agreement 8). `09e1fa3` folds the three checks
  into one comparison of the load lists, with the reason picked inside it. Mutants 1 and 2 are now
  the faults themselves: the module one side loads newly, or no longer, is not seen.

### What this session ran before the report (working agreement 10)

The affected set and the whole-repo checks are under [Final checks](#final-checks).

### Final checks

Run with the report written and the Goal set to `Succeeded`, at load 4:

- **The affected set:**
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run`
  → `46 of 586 test files (7.8%) chosen in 11.9 s from 4 changed files`, then
  `2180 passed in 70.02s`, `Affected set: 46 test files, pytest exited 0 after 71 s`. No worker was
  left behind. This covers `test_affected_tests.py`, the planted-break harness's cases, both CI
  workflow test-selection files, the always-run list, and the docs and spec tests.
- **Ruff:** `uv run --frozen ruff format --check .` → `1644 files already formatted`;
  `uv run --frozen ruff check .` → `All checks passed!`.
- **pyright:** `.venv/bin/pyright scripts/affected_tests.py tests/scripts/test_affected_tests.py`
  → `0 errors, 0 warnings, 0 informations`. No package changed.
- **Import boundaries:** `uv run --frozen lint-imports` → `Contracts: 19 kept, 0 broken.`;
  `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 68 CLI command and API route
  handlers within 25 statements`.
- **Specs:** `uv run scripts/validate_specs.py` → `OK: 524 files, 41 epics, 461 tasks, 22
  releases`.
- **Docs checks**, on this report:
  - `uv run --frozen python scripts/check_links.py` → `OK: 3052 relative links and anchors in 473
    Markdown files`;
  - `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments
    in 592 shell code blocks in 199 Markdown files (1 session reports changed since origin/dev)`;
  - `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 59 indexed
    documents under docs/ have a description`.

## Files changed

Six commits after the start commit, plus this report's:

- **`scripts/affected_tests.py`** (`f002750`, `09e1fa3`, `380bcbe`):
  - `leading_imports`, `is_typing_block`, `imports_at_module_level`: the imports at the top, and
    when imports must still be read as module code;
  - `Modules` and `package_paths_at`: which names are modules on each side;
  - `ImportReading`, `read_imports`, `imports_by_use`: the load and binding comparison;
  - `ContainerOutline` and `ContainerDiff` gain the imports, the names code run on import uses, and
    the rebound names and their users; `first_difference` is factored out of `container_diff`;
  - `add_container_names` and `container_names`: the dotted strings, as edges to parts and as
    `Graph.container_named`;
  - the walk: starting from the users of rebound names and the files importing them, and leaving
    dotted-name files out of the name search;
  - `--whole-container` passed to the graph; the docstring and `--help`.
- **`tests/scripts/test_affected_tests.py`** (`84c4374`, `1bdbcd7`, `cded5ec`): 28 cases. Two
  existing whole-file cases now expect the new reasons, and the dotted-name case is replaced
  (Decision 6).
- **The spec:** the Goal's phase, `Succeeded`. **This report.**

## Deviations from the spec

None. Decisions 2, 3 and 5 read more than the spec's words ask; each only selects more.

## Decisions and assumptions

1. **The imports read by use are the ones at the top.**
   - That means the plain imports and `if TYPE_CHECKING:` blocks of imports before any other
     statement, after the docstring. A `from __future__` import stays module code.
   - If an import appears anywhere else at module level (in a `try`, below a constant, or in a
     `TYPE_CHECKING` block with an `else`), every import is read as module code, as t43 read
     them. The same applies to a star import.
   - Imports read this way run before any other module code, so their only effects are the
     modules loaded and the names bound.
   - `container.py` today has exactly that shape.
2. **The same modules, in the same order.** The PM's rule compares sets. I compare the order of
   first loads too: a reordering reads as the whole file, as a moved part does. It costs nothing on
   the measured merges.
3. **What counts as loaded.**
   - `import a.b` loads `a` and `a.b`.
   - `from a.b import c` loads `a` and `a.b`, and `a.b.c` unless `c` is known not to be a module.
     A workspace package's files and folders are read on each side from git. The standard library
     is asked through `importlib.util.find_spec` on the parent package, which is the same on both
     sides.
   - Any other name counts as possibly a module. For example, adding `x` to an import from a
     third-party package reads as the whole file.
   - A name newly imported from a module already loaded may fail to import, or run a module
     `__getattr__`. Either would fail every test that imports the container, including the
     always-run `test_container_factories.py` and `test_app.py`, and the users of that name.
4. **`if TYPE_CHECKING:` blocks load nothing.** Their names are bound only for the type checker,
   and a change to them is read by the parts that use them, like any other rebinding.
   `TYPE_CHECKING` itself is read on import, so rebinding it is the whole file. This also means
   adding a type-only import of a module nothing loads does not make the change whole.
5. **When a rebinding is still the whole file:**
   - the name is used by code run on import: module code, `__init__` and the other dunder methods,
     a part's decorators, defaults or evaluated annotations, or a string there such as an
     `__all__` entry;
   - the name is also bound by a definition beside the container. A module constant's own name is
     among the names module code uses, so the first rule covers it;
   - the module reads names by a name it computes (`globals`, `vars`, `eval`, `exec`, `__dict__`,
     a module `__getattr__`).
6. **A `"debate_cli.container.X"` string.**
   - A file that names the module only in such strings asks for part X, or for X in
     `ServiceContainer.X`.
   - Any other X is a name the container imports or defines. The PM's context says such a file
     reaches the whole file. It does that here too, and it is also reached when an import rebinds
     X. Without that second part, reading imports by use would leave out a test that patches a
     rebound name.
   - A file that names the module any other way stays reached by that name. That includes the
     module name alone, a path, or an f-string such as `f"debate_cli.container.{name}"`.
   - t43's case `test_a_file_naming_the_container_module_is_still_reached_by_the_name` pinned the
     old reading of `"debate_cli.container.RULES"`. It is replaced by
     `…another_way_is_still_reached_by_the_name` (the module alone, and an f-string), and RULES's
     string moves into the new name cases.
7. **The edges from those strings are in the graph for every change**, so a change elsewhere that
   reaches part X also reaches the file naming it. That only adds selection. `--whole-container`
   leaves the edges out, so it reproduces `dev` exactly.
8. **Files that import a rebound name, or read it off the module,** are the container's direct
   importers whose text holds the name as a word. Each is reached as a file, so its own importers
   follow, for example a name re-exported through `app.py`.
9. **An import inside a part is that part's.** t43 already read it so; the case
   `test_an_import_inside_a_part_is_that_parts` pins it.
10. **Measured over the start commit's tree, `033060e`.** `origin/dev` moved during the session
    (#662 to #668). v1-e40-t08 (#662) edits `container.py` but none of this task's files.

## Operator follow-ups

None.

## Follow-up work

- **The floor every `container.py` change selects is now most of what remains.**
  - A `container.py` change that reaches no part selects 38 files (the planted break under mutant
    3). These are the source readers, the always-run tests, and the files that name the container
    module as a path or alone.
  - Any part's change selects at least 77. `doctor` reads every part, so its tests and the files
    that run it come with every part; t43's Follow-up says its check could be read finer.
  - af7052e's 77 is that number.
  - This belongs in E41 if the PM wants the next cut.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

An import change that loads no new module is now read by the parts using its names, and a
`debate_cli.container.X` string reaches part X. af7052e's edit alone fell from 177 files to 77.
1. **ac1 passes.**
   * All 12 diffs are subsets of before. `--whole-container` reproduces `dev`'s output exactly.
   * The two merges that load a new module stay whole, with the module and the line named.
   * The run check over all 100 dropped files: 1,468 passed, with no dropped file starting its own
     merge's changed part, and a positive control that fired.
   * Red: 20 failed against the skeleton, and 21 against `dev`'s script.
   * 22 mutants were caught. Mutant 3 on a planted real break leaves out `commands/test_files.py`
     with 21 failing tests, which is the forbidden item shown concretely.
   * Rewriting mutant 1 until it failed on a selection, not only on reason text, and reordering
     mutant 7's case until it could fail, is agreement 8 done properly.
2. **Decisions accepted:**
   * only the leading import block read by use;
   * the load order compared, not only the set, which is stricter than the ruling and free;
   * possibly-a-module treated as a module;
   * `TYPE_CHECKING` loading nothing;
   * the whole-file fallbacks for names used on import, bound twice or read by a computed name;
   * the string reading, keeping a patched rebound name reachable;
   * the replaced t43 case.
3. **Follow-up, `doctor`'s floor of about 77 files: no task now.** With t43, t44 and this task, the
   biggest test-selection costs are cut. The PM files the next cut only if a week of task PRs shows
   container changes still costing more than agreement 10's two minutes.
4. **Closing checks:** the affected set ran whole within the limit (46 files, 2,180 passed), and the
   whole-repo checks pass.
5. **Merge:** once the PR's `ci` is green. It is a plain `scripts/task pr`.

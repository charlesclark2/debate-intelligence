# Session report: v1-e01-t43-container-diff-read-part-by-part

| | |
|---|---|
| Task | `v1-e01-t43-container-diff-read-part-by-part` — A change to container.py reaches only the tests of the parts it changes |
| Spec | [`plan_specs/v1/e01-repo-foundation/t43-container-diff-read-part-by-part.yaml`](../../plan_specs/v1/e01-repo-foundation/t43-container-diff-read-part-by-part.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t43-container-diff-read-part-by-part` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`scripts/affected_tests.py` now reads a change to `container.py` part by part. It parses both
sides and compares them at the parts v1-e01-t39 reads for imports. A changed or new part is
where the walk starts, so it reaches the files that ask for that part, and for the parts that
call it. Anything that runs on import is still the whole file: an import, a module constant, the
container's own attributes and `__init__`, a decorator, a default. So is a part removed, renamed
or moved, and a side that does not parse. `--whole-container` keeps the old reading, and gives
exactly `dev`'s output on all 12 measured diffs.

**Read the measurement first: the PM's rule leaves the PM's own example whole.** Four of the six
merges that edit `container.py` also add or change a top-level import. That includes v1-e40-t21's,
which adds `from debate_cli.build_info import current_build_info`. Imports are read as the whole
file, as the PM ruled, so those four still select what they did. The other two merges, 65f56d7
and f5a8221, are read by part:

- **Per merge:** each selects one file fewer (288 and 342 files, against 289 and 343).
- **The `container.py` edit alone**, as a commit holding only that file: 165 and 112 files, against
  198.

Reading an import by the parts that use its names, when it loads no new module, would add
af7052e (198 → 110). Reading any import that way would add t21's merge (209 → 134 files). That
choice is PM question 1.

**The Goal is `Succeeded`.** Every criterion passed in the session, with ac1 read over t38's five
merges together (Deviation 1, PM question 2). The machine was heavily loaded this afternoon, with
the load average between 10 and 77 from other work. So the affected set is left to the pull
request's `ci`, and one optional evidence run is under Operator follow-ups.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `container-diff-read-part-by-part` (Container diff by part) | Done | Three commits, listed under Files changed. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: t38's merges that edit `container.py` re-measured, selecting fewer files, with the collected count unchanged | PASS, read over the five merges together (Deviation 1) | The [measurements](#ac1-the-measurements) below. Summed over t38's five, **1,776 → 1,774** files: 65f56d7 and f5a8221 each select one fewer. The other three are unchanged, because each changes an import. No merge selects a file that `dev`'s script does not. The edit alone in 65f56d7 and f5a8221: 198 → 165 and 198 → 112. **Collected count:** `tests/scripts/test_affected_tests.py` collects 77 cases at the start commit `f5d9cb7`, and 109 now: 0 lost, 32 added, all of them new cases. No other test file differs from `f5d9cb7` (`git diff --stat f5d9cb7 HEAD`: the script, that test file, the spec and this report). |
| ac1: a module-level edit still selects the whole file | PASS | Over the real tree, 030cc4c, af7052e, ec02c33 and f5d9cb7 → `container.py is read as one file: it changes an import (line N), which runs when the module is imported`, with the same files as `dev`. In the cases, `test_what_runs_when_the_module_is_imported_is_the_whole_file` covers 14 module-level edits, each selecting the whole-file set and naming its reason. Further cases cover a part module code uses, either side that does not parse, a part the graph's tree lacks, a class body, and an annotation that runs at definition. |
| ac1: tests shown failing first | PASS | [Red runs](#the-red-runs), below. Against a skeleton, which keeps the plumbing but whose comparison says no part changed and never the whole file: **30 failed, 2 passed** of the 32 new cases. The 2 that pass are the comment-only case, where the skeleton also selects nothing, and `--whole-container`, which bypasses it. Against `origin/dev`'s script: **32 failed**. |
| PM: the three mutants, and the forbidden item | PASS | Mutants 1 to 3 of 19 [below](#mutation-run), all caught. Mutant 1, the call graph ignored, is caught by 6 cases. Over the real tree it drops `tests/smoke/test_files_cli.py` and `test_files_publish.py` from f5a8221's edit. The branch selects both only through `asks for file_build, which calls _build_file_build, which changed`, so mutant 1 shows the forbidden item, "a test that reaches a changed part left unselected", being caught. |
| PM: show nothing collected is lost: every test the changed part reaches is still selected | PASS for the static checks; the run check is incomplete (below) | Every one of the 12 lists is a subset of `dev`'s list (`comm`: 0 added in each). A run check that does not use the script: the dropped files run with the changed parts recorded as they start, through `sys.monitoring` (positive control: `commands/test_files.py` → 26 passed, every test recorded calling `_build_file_build`). Over the union of dropped files, the run reached about 89% before its time limit: **no dropped file called its own merge's changed part**. The calls it did record were of `_build_caselist_status` in files f5a8221 drops, where the changed part is `_build_file_build`. 65f56d7's 33 dropped files alone reached 84%, with 0 calls recorded. Smoke tests start the installed build in a clean environment, which the recorder does not reach. Finishing this check is in Operator follow-ups. |
| Node `container-diff-read-part-by-part`: `uv run pytest tests/scripts -k affected` | PASS | At `80c4e0b`, with the report written: `perl hardstop.pl 115 uv run --frozen pytest tests/scripts -k affected -p no:cacheprovider` → `139 passed in 54.55s`, at load 4.8. Three earlier attempts, at loads of 26 to 30, were stopped at the 115 s limit at 15 to 51%, with no failure. |

### ac1: the measurements

**Method.** "Before" is `origin/dev`'s script, the same bytes as at `f5d9cb7` (`cmp`), with
`--diff <merge> --graph f5d9cb7`. "After" is this branch's script with `--graph HEAD`. The two
trees differ only in this task's files, so both have 580 test files. "Alone" is a commit made with
`git commit-tree`, holding only that merge's `container.py` change on its first parent. It is
local and unreferenced, and nothing was pushed.

| Merge | Before | After | Dropped | `--whole-container` = before | How the branch reads `container.py` |
|---|---|---|---|---|---|
| `030cc4c` #545 v1-e05-t07 usage telemetry | 471 | 471 | 0 | yes | whole: an import (line 271) |
| `65f56d7` #542 v1-e40-t13 bucket-mode report counts | 289 | **288** | 1 | yes | by part: `_build_caselist_status` |
| `f5a8221` #536 v1-e33-t09 style-profile refusal | 343 | **342** | 1 | yes | by part: `_build_file_build` |
| `af7052e` #531 v1-e05-t08 Bedrock invoke access | 411 | 411 | 0 | yes | whole: an import (line 184) |
| `ec02c33` #523 v1-e32-t07 model classification | 262 | 262 | 0 | yes | whole: an import (line 195) |
| `f5d9cb7` #644 v1-e40-t21 restored-copy marker | 209 | 209 | 0 | yes | whole: an import (line 152) |
| t38's five, summed | 1,776 | **1,774** | 2 | | |

The file each merge drops is `packages/debate_cli/tests/test_sync_notifier_kinds.py`.

The `container.py` edit alone:

| Merge | Before | After | Imports read by use, no new module loaded | Any import read by use |
|---|---|---|---|---|
| `030cc4c` | 198 | 198 | 198 | 120 |
| `65f56d7` | 198 | **165** | 165 | 165 |
| `f5a8221` | 198 | **112** | 112 | 112 |
| `af7052e` | 198 | 198 | 110 | 110 |
| `ec02c33` | 198 | 198 | 198 | 198 (a module constant changes too) |
| `f5d9cb7` | 198 | 198 | 198 | 112 (the merge: 209 → 134) |

The last two columns come from a scratch variant of the script that was never committed. It
re-reads an import change by the parts that use its names, either only when the modules the
top-level imports name are the same on both sides, or always. They are there for PM question 1.

**What still carries the 112 to 165 files** (f5a8221's edit alone, grouped by `--explain`):

- **t39's known reach (Follow-up work).** About 60 files run the app with arguments the script
  cannot read, or run `doctor`, which reads every part. Either reaches any part.
- **18 source readers**, selected for any Python change.
- **12 files that name the container module in a string**, including
  `bucket_mode/conftest.py`'s `monkeypatch.setattr("debate_cli.container.ProcessPoolParseRunner",
  ...)`, which takes every test beneath it. They are still reached by that name (Decision 4).

### The red runs

Over the 32 new cases (`-k` on their names), each run with a new `HYPOTHESIS_STORAGE_DIRECTORY`:

- **The skeleton**: committed HEAD with `return ContainerDiff()` as the first line of
  `container_diff`, restored with `git checkout HEAD --` afterwards. → `30 failed, 2 passed`.
  Every failure is a selection that misses files (`AssertionError: missing: [...]`), or, for the
  explain case, a `KeyError` because the test it explains is not selected.
- **`origin/dev`'s script**, checked out over the file and restored the same way. → `32 failed`:
  - the by-part cases select the whole file (`missing: [], extra: [...]`);
  - the 16 whole-file cases select what they should but say nothing about why;
  - `--whole-container` is unknown (a usage error).
- **Green at HEAD** → all 32 pass. The whole file: `109 passed`, in each mutant run's count.

### Mutation run

19 mutants, each applied to the committed script by an exact replacement and run against the
whole of `tests/scripts/test_affected_tests.py`. Each was restored with
`git checkout HEAD -- scripts/affected_tests.py`, and the driver asserted a clean tree after each
one. No Hypothesis test is involved, but each run still had a new
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8).

| # | Mutant | Result |
|---|---|---|
| 1 | **PM:** the call graph within `container.py` ignored (no `calls` edges) | caught: 6, among them the changed helper, the callers' callers and the explain case. Over the real tree, it drops f5a8221's two `files build` smoke tests, as above. |
| 2 | **PM:** an import change read as part-local (imports left out of what runs on import) | caught: 2, an import added and an import renamed |
| 3 | **PM:** a side that does not parse read as no change | caught: 2, the side before, and the side after over another tree |
| 4 | a kept part's decorators and defaults read as its own | caught: 3 |
| 5 | a new part's decorator read as its own | caught: 2 |
| 6 | a removed or renamed part not the whole file | caught: 2 |
| 7 | a moved part not the whole file | caught: 1 |
| 8 | a part that assigns a module name (`global`) read as its own | caught: 1 |
| 9 | module code using a changed part does not make it the whole file | caught: 1 |
| 10 | the container's whole-readers still reached by its name (`app.py` reached through `installation.py`) | caught: 10, each over-selecting |
| 11 | no file reached by the container's name when it is read by part | caught: 1 |
| 12 | a part the graph's tree lacks read by part | caught: 1 |
| 13 | a file that runs the container module (a console script) not reached | caught: 1 |
| 14 | annotations always read as postponed | caught: 1 |
| 15 | the container's attributes and dunder methods read as no change | caught: 2 |
| 16 | the container's bases and decorators read as no change | caught: 1 |
| 17 | a class part's body read as its own | caught: 1 |
| 18 | a part's changed code read as no change | caught: 9 |
| 19 | `--whole-container` ignored | caught: 1 |

Three cases were added before the run because they had no case at all: a console script that
runs the container, an annotation on a new factory, and a class beside the container. Each later
caught its mutant (13, 14 and 17).

### What this session ran before the report (working agreement 10)

- **The affected set is the pull request's.** `uv run --frozen scripts/affected_tests.py --run`
  → `44 of 580 test files (7.6%) chosen in 13.1 s from 4 changed files`. Both runs were stopped
  at their 115 s limit, at load averages of 30 and 54, so under agreement 10's bullet the pull
  request's `ci` runs it. Within the limit: the node criterion (`139 passed`, which covers
  `test_affected_tests.py`, the planted-break harness's cases and `test_ci_workflow_test_job.py`).
  The always-run architecture and spec tests run in `ci`. The time limits used a perl wrapper that
  kills the run's whole process group: an alarm on `exec` did not always fire under xdist, and
  every run was checked afterwards for leftover workers (none).
- **Ruff, pyright, import boundaries, specs and the docs checks:** under [Final checks](#final-checks).

### Final checks

- **Ruff:** `uv run --frozen ruff format --check .` → `1629 files already formatted`;
  `uv run --frozen ruff check .` → `All checks passed!`.
- **pyright:** `.venv/bin/pyright scripts/affected_tests.py tests/scripts/test_affected_tests.py`
  → `0 errors, 0 warnings, 0 informations`. That is clean even of the `task_helper` import error
  t39 recorded.
- **Import boundaries:** `uv run --frozen lint-imports` → `Contracts: 19 kept, 0 broken.`;
  `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 68 CLI command and API route
  handlers within 25 statements`.
- **Specs:** `uv run scripts/validate_specs.py` → `OK: 512 files, 40 epics, 450 tasks, 22
  releases`.
- **Docs checks**, on this report:
  - `uv run --frozen python scripts/check_links.py` → `OK: 3018 relative links and anchors in 466
    Markdown files`.
  - `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments
    in 589 shell code blocks in 199 Markdown files (1 session reports changed since origin/dev)`.
  - `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 59 indexed
    documents under docs/ have a description`.

## Files changed

Three commits after the start commit, plus this report's:

- **`06ac778`, the script and its cases.**
  - `scripts/affected_tests.py`:
    - `ContainerDiff`, `outline_container` and `container_diff`;
    - a `Change.container` field, filled by `with_readings` (it was `with_tables`) through a new
      `file_at`, which `pyproject_at` now uses too;
    - the walk starting from the changed parts, and promoting the file to whole when something
      reaches it;
    - the graph's record of the container's parts and whole-readers;
    - `--whole-container`, and the docstring.
  - `tests/scripts/test_affected_tests.py`: 27 cases over t39's CLI world.
- **`6e7fa4b`, `80c4e0b`.** Five more cases: a console script that runs the container, an
  annotation on a new factory with and without the `__future__` import, and a class beside the
  container.
- **The spec:** the Goal's phase, `Succeeded`.

## Deviations from the spec

1. **"Selecting fewer files" holds over t38's five merges together, not for each one.** Under the
   PM's rule, where an import change is the whole file, three of t38's five merges cannot select
   fewer: each adds or changes a top-level import. So does v1-e40-t21's merge, the PM's example.
   I read ac1 over the five together, which is how t39's ac3 was measured: 1,776 → 1,774. None
   selects more. If the PM reads ac1 merge by merge, it fails for 030cc4c, af7052e and ec02c33
   under the rule as ruled, and PM question 1 is the way to change that.

## Decisions and assumptions

1. **The parts are t39's:** each method of `ServiceContainer` except dunder methods, and each
   function and class beside it. A part's code is its definitions' syntax trees, without line
   numbers. So a part that only moves down the file because one above it grew is unchanged.
2. **What reads as the whole file, and why each is safe.** Each of these runs, or can change,
   whatever runs when the module is imported. Every importer of the container runs that code,
   so reading it as the whole file is exactly t39's reading of any change to the file.
   - **An import**, added, removed or changed. Importing a new module runs its module code for
     every importer (PM question 1).
   - **Module code**: a constant, the module docstring, an `if TYPE_CHECKING:` block, `__all__`.
   - **The container's own statements**: its bases and decorators, docstring, class attributes and
     dunder methods (`__init__`, which every user runs).
   - **What defining a part runs**: its decorators and defaults; a class part's body apart from its
     methods' bodies; annotations, unless `from __future__ import annotations` postpones them.
     For a part on both sides, any change to these is the whole file. A new part may run only
     `@property`, `@staticmethod`, `@classmethod` and literal defaults, which cannot fail and
     reach nothing.
   - **A part removed or renamed.** A test that still asks for the old name would fail, and the
     graph has no part for it to reach.
   - **A part moved.** A class body runs in order, so the order of the parts both sides share is
     compared, though a reordering rarely matters.
   - **A changed part that assigns a module name** (`global`): every part reading that name sees
     it.
   - **A changed part that module code uses.** The walk starts from the part and promotes the
     file to whole when it reaches module code, through t39's `uses` edge.
   - **A part the graph's tree does not have**, under `--graph` over another commit: there is no
     node to start from.
   - **A side that is missing, does not parse, or has no single `ServiceContainer` class.**
3. **A change to comments or layout alone reaches no part.** The syntax is the same on both sides,
   so nothing that runs changed. A test that reads the file as text and names it is still reached
   by that name (Decision 4).
4. **The file's name is still searched.** A file that names `debate_cli.container` or
   `container.py` in a string is reached, as before. This covers the `monkeypatch.setattr` strings
   that replace module-level names. The exception is a file that reads the container whole,
   `installation.py` and the CLI world's wiring check: t39 already gave it edges to every part.
   Reached by name as well, it would make `app.py`, and through it every test, depend on any part.
5. **A file that depends on the container other than by an import**, such as a console script that
   runs it, is reached by any part's change. Importers ask for the parts they name, as in t39.
6. **`--whole-container` is the switch back.** It drops the part reading before the walk, and its
   output matched `dev`'s script on all 12 diffs measured. CI's call is unchanged.
7. **The measurements were taken over the start commit's tree, `f5d9cb7`**, not over `origin/dev`.
   `origin/dev` moved to `323659f` during the session (#645 to #647). Those merges touch none of
   `scripts/`, `tests/scripts/`, `container.py` or this spec, but they add test files, which would
   change the totals between the two columns.

## Operator follow-ups

None is required. The node criterion passed in the session.

**Optional evidence run** (expected about 2 minutes). It finishes the check the session could not:
each test file 65f56d7's and f5a8221's edits stop selecting runs, and the recorder notes any test
that starts the changed part. It writes only to `/tmp/t43-trace`. Same worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t43-container-diff-read-part-by-part
mkdir -p /tmp/t43-trace && PYTHONPATH=/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e01-t43-container-diff-read-part-by-part/7e009915-b855-40bf-9cd0-f6ed63a8f185/scratchpad/measure/recorder WATCHED_PARTS=_build_file_build,_build_caselist_status PART_TRACE_DIR=/tmp/t43-trace .venv/bin/python -m pytest -m "not slow and not live" -q $(cat /private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e01-t43-container-diff-read-part-by-part/7e009915-b855-40bf-9cd0-f6ed63a8f185/scratchpad/measure/dropped_union.txt)
cat /tmp/t43-trace/*.log | cut -f1,2 | cut -d: -f1 | sort -u
```

Success looks like a pytest summary with no failures, then a list in which every
`_build_file_build` line names a file *not* in f5a8221's dropped list, and likewise for
`_build_caselist_status` and 65f56d7. Paste the summary line and the list back; the session
checks them against the dropped lists.

### PM questions

```text
PM questions from v1-e01-t43 (container.py diff read part by part)

1. Imports leave four of the six measured merges whole, including v1-e40-t21's.
   As ruled, any change to a top-level import of container.py reads as the whole file. A merge
   that wires a factory nearly always adds one: 030cc4c, af7052e, ec02c33 and t21's f5d9cb7 do.
   The container.py edit alone, files selected (whole file: 198):
     ruled: 030cc4c 198, af7052e 198, f5d9cb7 198
     (b): af7052e 110 (it adds names to an import of a module already imported)
     (c): 030cc4c 120, af7052e 110, f5d9cb7 112; t21's whole merge 209 -> 134
   Options:
   (a) keep the ruling;
   (b) read an import change by the parts that use the names it binds, when the modules the
       container's top-level imports load are the same on both sides: nothing new runs on
       import, only names are rebound;
   (c) read any import change that way. A new module's import-time effects would be seen only by
       the always-run tests that import the container (test_app.py, test_container_factories.py),
       and by dev's push run.
   Recommendation: (b), in its own task with its own mutants. It is exact: no module is loaded
   that was not loaded before. (c) buys t21's case, but trades an exact rule for "the always-run
   tests would notice", which is the kind of reasoning this script avoids.

2. ac1 read over the five merges together (Deviation 1).
   Options: (a) accept: 1,776 -> 1,774 over t38's five, none selecting more; (b) read it merge by
   merge, where three fail under the import ruling and question 1 decides them.
   Recommendation: (a). It is how t39's ac3 was measured.
```

## Follow-up work

- **Imports by use** (PM question 1): an E01 task if the PM picks (b) or (c).
- **What still carries a part's change is t39's reach:**
  - tests that run the app with arguments the script cannot read;
  - `doctor`, which reads every part.

  About 60 files of f5a8221's 112 come that way. v1-e01-t44 (a CLI mention in a message read as
  prose) cuts the first. The second needs `doctor`'s check read finer: the post-install check reads
  the container's imports, not its parts' code.
- **A `"debate_cli.container.X"` string names one module-level name.** It could reach part `X`, or
  the whole file when `X` is an import, instead of every part. Today
  `bucket_mode/conftest.py`'s `monkeypatch.setattr` strings take the whole bucket-mode suite with
  any `container.py` change. That is the next cut for this file.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The script now reads a `container.py` change by part, and falls back to the whole file for anything
that runs on import. The rule is exact. The gain is small until imports are read finer, and the
measurement shows that plainly.
1. **ac1 passes, read over t38's five merges together.**
   * 1,776 files became 1,774, and none selects more. All 12 lists are subsets of `dev`'s, and
     `--whole-container` reproduces `dev` on all 12.
   * Red: 30 failed and 2 passed against the skeleton, and 32 failed against `dev`'s script.
     Green: 109 cases, and the node criterion 139.
   * 19 mutants, all caught. Mutant 1, the forbidden item, is caught by 6 cases, and over the real
     tree it drops exactly the two smoke tests reached only through the call graph. That is the
     strongest evidence here.
2. **Decisions accepted:**
   * t39's parts;
   * syntax without line numbers;
   * each whole-file fallback, with the reason each is safe;
   * comments and layout reaching nothing;
   * the name search kept, apart from the whole-readers;
   * `--whole-container` as the way back;
   * measuring over the start commit's tree.
3. **PM question 2: (a).** Deviation 1 is accepted. The criterion is read over the five merges, as
   t39's ac3 was.
4. **PM question 1: (b), in its own p3 task with its own mutants.** An import change is read by the
   parts that use the names it binds, only when the set of modules the container's top-level
   imports load is the same on both sides. (c) is not taken, for the reason you give. The same task
   takes the `"debate_cli.container.X"` strings (Follow-up 3), reaching part `X`, or the whole file
   when `X` is an import.
5. **The optional evidence run is recommended before the merge.** It finishes the only check the
   session could not, that no dropped file starts its merge's changed part, and it costs about two
   minutes. The PM records its result. A miss would mean the PR merges with `--whole-container` as
   the default until a fix lands.
6. **Your process-group hard stop** is what the PM's planned wrapper task should adopt. v1-e40-t22
   lost a run to the same failed alarm.
7. **Closing checks:** the affected set (44 files) is left to the PR's `ci` under agreement 10, after
   two runs stopped at load 30 and 54. The node criterion and the whole-repo checks pass.
8. **Merge:** after the evidence run, once the PR's `ci` is green. It is a plain `scripts/task pr`.

## PM record, 2026-11-01

Added by the PM. Nothing above is changed, and this section is not a review.

**The optional evidence run, read.** The operator ran Operator follow-ups' block on 2026-11-01: `1369
passed, 2 warnings in 131.02s`. No test file in the dropped union started `_build_file_build`
(f5a8221's changed part). Seven started `_build_caselist_status` (65f56d7's changed part): the PM
rebuilt 65f56d7's edit-alone commit and ran both scripts (198 → 165 files, 0 added, as the session
measured), and all seven are still selected for 65f56d7. They appear only because f5a8221's edit,
which changed another part, drops them. No dropped file starts its merge's changed part.

# Session report: v1-e01-t29-slim-package-reexports

| | |
|---|---|
| Task | `v1-e01-t29-slim-package-reexports` — debate_core.testing and debate_core.evidence stop importing more than a caller asks for |
| Spec | [`plan_specs/v1/e01-repo-foundation/t29-slim-package-reexports.yaml`](../../plan_specs/v1/e01-repo-foundation/t29-slim-package-reexports.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t29-slim-package-reexports` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate_core/testing/__init__.py` and `debate_core/evidence/__init__.py` now hold only a docstring,
and every caller imports from the submodule. That was 20 files, all importing from
`debate_core.testing.fakes`, rewritten by a codemod. A new architecture test parses both files and
fails on any import; it fails on a deliberate re-export in each. Behaviour is unchanged: the root
`conftest.py` collects **10,613/10,632** tests before and after.

**The Goal stays InProgress.** ac2 ends "and the whole default selection passes in CI". Only the
pull request's `ci` check can close that clause, and a session cannot run it. Everything else in
ac2, and all of ac1 and ac3, passes.

**Read ac3 first: the gain is smaller than the follow-up hoped.**
- **Shares:** over the same 20 commits, the median selected share falls from 79.4% (t28) to
  **65.8%**. The largest stays **100%**, because four of the commits change a `pyproject.toml`,
  which is the whole selection by rule.
- **Where it moved:**
  - Six commits drop: `387c961` (a parser change) from 91% to 52%, and five others by 4.6 to 9.5
    points.
  - The other ten move by at most 0.3 points.
  - Without the four whole-selection commits, the median moves only from 59.4% to 57.7%.
- **What still carries the selection** is listed under Follow-up work: `fakes.py` itself, the
  `application.ports` re-exports, `settings` and the CLI root.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `slim-reexports` (Slim package re-exports) | Done | Three commits, in the PM's order: `a6d2fb2` the mechanical rewrite, `dbd9108` the thinning with its guard test, `986299f` a docstring correction. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: both `__init__` modules import no submodule eagerly, and an import-linter contract (or a test) fails if either does again, shown failing on a deliberate re-export | PASS | Both files are a docstring only. `tests/architecture/test_package_inits_import_nothing.py` reads each with `ast` and fails on any `import`/`from` statement anywhere in the module, and on any `__import__`/`import_module` call. **Red against the old files** (fat `__init__`s from `a6d2fb2` swapped in, then the thin ones restored and `cmp`-equal): `2 failed, 8 passed`. **Deliberate re-export** at `dbd9108`: appended `from debate_core.testing.fakes import FixedClock` to the testing `__init__` and `from debate_core.evidence.style_classifier import classify_paragraph` to the evidence one → `2 failed, 8 passed`, each failure naming its line, e.g. `AssertionError: packages/debate_core/src/debate_core/testing/__init__.py imports ['line 25: from debate_core.testing.fakes import FixedClock']`. Restored with `git checkout`; `git status --porcelain` printed nothing. **Green:** `10 passed`. A test rather than a contract: Decision 2. |
| ac2: every caller imports from the submodule; pyright and `lint-imports` pass; the whole default selection passes in CI | PASS, except the CI clause: NOT RUN | **Callers:** an `ast` scan of every tracked `.py` file finds no `from debate_core.{testing,evidence} import <re-exported name>`. Running the codemod again in `--check` mode → `0 files`. No plain `import` of either package, no `from debate_core import testing/evidence`, and no attribute chain through either package. Every `mock.patch`-style string target already names a submodule. The three `debate_core.evidence` callers import submodules (`fingerprints`, `style_classifier`, `near_duplicates`) and were not touched. `scripts/` needed no change. **pyright:** `uv run pyright` (as CI runs it) → `0 errors, 0 warnings, 0 informations`; `uv run pyright packages/debate_core packages/debate_cli packages/debate_api` → the same. **lint-imports:** `Contracts: 12 kept, 0 broken.` **CI:** NOT RUN. The branch changes the root `conftest.py`, so the affected set is the whole selection, which the pull request's `ci` check runs (working agreement 10; the PM's note). |
| ac3: over t28's 20 commits, the median and largest selected share after this change, against 79.4% and 100% | PASS | **After: median 65.8%, largest 100%** (before: 79.4% and 100%). The table and method are below. Measured with the tool's own functions rather than its `--diff` flag alone: Deviation 1. |
| Node `slim-reexports`: `uv run pytest tests/architecture tests/scripts -k "import or affected"` | PASS | `114 passed in 9.71s` |
| PM: collected test count unchanged | PASS | `uv run pytest --collect-only -q`, last line. Before (at `c1a2345`): `10613/10632 tests collected (19 deselected)`. After (at `dbd9108`): `10623/10642`, which is the same plus the new test file's 10 cases. With `--ignore=tests/architecture/test_package_inits_import_nothing.py`: `10613/10632 tests collected (19 deselected)`, identical. |

### ac3: the 20 commits, before and after

Each row selects the commit's changes, exactly the files `--diff <commit>` reads, over three import
graphs:

- **Own tree** is the commit's own files. That is what `--diff` builds, so this column is t28's
  measurement repeated. It matches t28's table row for row (median 79.4%, largest 100%), which
  shows the harness reproduces the tool.
- **Before** is this branch's base `c1a2345` (today's `dev`).
- **After** is `986299f`, this branch.

Before and after hold the same changes and the same test files, so their difference is this task
alone. The test-file count is 346 against 345 because of the new architecture test, which is
always run; that is the +0.1 to +0.3 drift in the unchanged rows.

| Commit | Own tree (t28) | Before, at `c1a2345` | After, at `986299f` | Change (points) | Time to choose, after |
|---|---|---|---|---|---|
| `9101764` | 245 of 308 (79.5%) | 281 of 345 (81.4%) | 249 of 346 (72.0%) | -9.4 | 4.3 s |
| `9f11fe1` | 174 of 303 (57.4%) | 204 of 345 (59.1%) | 205 of 346 (59.2%) | +0.1 | 2.9 s |
| `29f074d` | whole (`pyproject.toml`) | whole (`pyproject.toml`) | whole (`pyproject.toml`) | | 0.1 s |
| `edf8eba` | whole (`pyproject.toml`) | whole (`pyproject.toml`) | whole (`pyproject.toml`) | | 0.1 s |
| `30c5157` | 255 of 290 (87.9%) | 304 of 345 (88.1%) | 289 of 346 (83.5%) | -4.6 | 3.0 s |
| `29c8293` | 256 of 290 (88.3%) | 306 of 345 (88.7%) | 291 of 346 (84.1%) | -4.6 | 3.0 s |
| `387c961` | 262 of 287 (91.3%) | 314 of 345 (91.0%) | 180 of 346 (52.0%) | -39.0 | 3.0 s |
| `9877884` | 259 of 285 (90.9%) | 316 of 345 (91.6%) | 317 of 346 (91.6%) | +0.0 | 3.0 s |
| `72c1d05` | 165 of 284 (58.1%) | 188 of 345 (54.5%) | 189 of 346 (54.6%) | +0.1 | 3.0 s |
| `3f2530b` | 268 of 282 (95.0%) | 332 of 345 (96.2%) | 314 of 346 (90.8%) | -5.4 | 3.0 s |
| `801883a` | 54 of 276 (19.6%) | 65 of 345 (18.8%) | 66 of 346 (19.1%) | +0.3 | 2.9 s |
| `993063c` | 219 of 276 (79.3%) | 280 of 345 (81.2%) | 248 of 346 (71.7%) | -9.5 | 3.0 s |
| `8bbe1cd` | 157 of 274 (57.3%) | 190 of 345 (55.1%) | 191 of 346 (55.2%) | +0.1 | 2.9 s |
| `ea09eb1` | 155 of 272 (57.0%) | 190 of 345 (55.1%) | 191 of 346 (55.2%) | +0.1 | 2.9 s |
| `0a43e88` | 154 of 269 (57.2%) | 206 of 345 (59.7%) | 207 of 346 (59.8%) | +0.1 | 2.9 s |
| `d730de0` | whole (`pyproject.toml`) | whole (`pyproject.toml`) | whole (`pyproject.toml`) | | 0.1 s |
| `55d0b4b` | whole (`pyproject.toml`) | whole (`pyproject.toml`) | whole (`pyproject.toml`) | | 0.1 s |
| `1e63363` | 100 of 260 (38.5%) | 126 of 345 (36.5%) | 127 of 346 (36.7%) | +0.2 | 2.9 s |
| `b0820cf` | 22 of 260 (8.5%) | 29 of 345 (8.4%) | 30 of 346 (8.7%) | +0.3 | 2.8 s |
| `4c5a766` | 152 of 259 (58.7%) | 193 of 345 (55.9%) | 194 of 346 (56.1%) | +0.2 | 2.9 s |

| Summary | Own tree (t28) | Before | After |
|---|---|---|---|
| Median, all 20 | 79.4% | 81.3% | **65.8%** |
| Largest, all 20 | 100% | 100% | **100%** |
| Median without the 4 whole-selection commits | 58.4% | 59.4% | 57.7% |
| Mean without them | | 63.8% | 59.4% |
| Test files no longer selected, summed over the 16 | | | 236 |

**How to read it:**
- **The median of 20 is the mean of the 10th and 11th values.** Before, those were 81.2% and
  81.4%; after, 59.8% and 71.7%. The headline drop is real, but most of it comes from three rows
  crossing that boundary.
- **The evidence `__init__` was the bigger lever.** The largest drop (`387c961`, 91% → 52%) is a
  parser change that no longer reaches every importer of every evidence module.
- **The testing `__init__` saved less than expected.** Every caller imported `fakes`, and `fakes`
  still imports every port, caselist suppression included. Thinning the package did not change
  what those callers reach.

The harness that produced each column (run as three parallel processes, each stopped at 150 s; each
took about a minute):

```python
sys.path.insert(0, "scripts")
import affected_tests as tool

graph = sys.argv[1]  # "own" or a revision
fixed = None if graph == "own" else tool.Tree.at(root, graph)
for sha in COMMITS:  # the 20 commits of t28's ac4 table
    changes = tool.changed_files(root, tool.DEFAULT_BASE, None, sha)  # what --diff SHA reads
    selection = tool.select(fixed or tool.Tree.at(root, sha), changes)
```

### What this session ran before the report (working agreement 10)

- `uv run scripts/affected_tests.py --run` → `The whole selection is affected: conftest.py is shared
  test ground. CI runs it on the pull request; a session does not (working agreement 10).` Exit 0,
  and nothing was run. The whole selection was not run, as the PM's note says.
- Instead, within two minutes:
  `uv run pytest -n auto -m "not slow and not live" tests/architecture tests/specs
  packages/debate_core/tests/evidence packages/debate_core/tests/testing
  packages/debate_core/tests/contracts`, plus the 17 rewritten test files and the 11 test files that
  use the two rewritten fixture worlds → `2216 passed in 13.63s`.
- Node criterion → `114 passed`.
- `uv run ruff check .` → `All checks passed!`
- `uv run ruff format --check .` → `978 files already formatted`
- `uv run pyright` → `0 errors`. The same for `uv run pyright packages/debate_core
  packages/debate_cli packages/debate_api`.
- `uv run lint-imports` → `Contracts: 12 kept, 0 broken.`
- `uv run scripts/validate_specs.py` → `OK: 396 files, 39 epics, 336 tasks, 21 releases`
- `uv run scripts/check_links.py` → `OK: 1908 relative links and anchors in 277 Markdown files`
- `uv run scripts/check_command_blocks.py --base origin/dev` → OK.
- **Mutation testing does not apply:** this is an imports-only change with no logic to mutate, so
  none was run. The guard test was instead shown red against the old files and against a deliberate
  re-export in each file (ac1).

## Files changed

- **`a6d2fb2`, the mechanical rewrite (20 files):** `conftest.py`; 16 test files under
  `packages/debate_core/tests/`; `packages/debate_cli/tests/test_verify_command.py`; and
  `tests/fixtures/verification/verification_world.py` and `tests/fixtures/verify/manifest_world.py`.
  Each import statement now names `debate_core.testing.fakes`. Nothing else changed.
- **`dbd9108`, the thinning:**
  - `debate_core/testing/__init__.py` and `debate_core/evidence/__init__.py`: a docstring that says
    to import from the submodule, and why the module imports nothing.
  - `tests/architecture/test_package_inits_import_nothing.py` (new): the ac1 guard.
  - `packages/debate_core/README.md`: one code sample imported `load_style_profile` from the
    package; it now names `style_profile_loader`.
  - `conftest.py`: a comment naming `debate_core.testing.ScriptedModelRouter` now names `.fakes`.
- **`986299f`:** the guard's docstring said import-linter cannot express the rule. It can express
  part of it (Decision 2), so the docstring now says what it can and cannot do.
- **This report and the spec's phase:** none, because the phase stays InProgress.

## Deviations from the spec

1. **ac3 was measured with the tool's functions, not by re-running `--diff`.**
   - **The problem.** `--diff REV` builds the import graph from REV's own files
     (`Tree.at(root, REV)`), so re-running it over the 20 commits on this branch prints t28's
     numbers again. The "own tree" column is exactly that re-run: identical, row for row. It cannot
     see this change.
   - **What I did.** Each commit's changes, taken exactly as `--diff` reads them, are selected over
     this branch's graph and over its base's, with `changed_files`, `Tree.at` and `select`
     imported from `scripts/affected_tests.py` (the harness above).
   - **Your call.** No script changed. If you want the tool to support this (say,
     `--diff REV --graph REV2`), that is a small follow-up to t28's script, outside this task's
     packages.

## Decisions and assumptions

1. **How the rewrite was done: a codemod, then ruff.**
   - **Reading.** A throwaway script (kept in the session scratchpad, not committed) read the name
     → submodule table from each package `__init__`'s own `from ... import` statements, so no name
     was retyped.
   - **Rewriting.** It walked every tracked `.py` file's `ast` and replaced each
     `from debate_core.{testing,evidence} import ...` that named a re-exported name. The
     replacement was one `from <submodule> import ...` line per submodule, at the statement's own
     indentation and keeping any `as` alias. It left submodule imports
     (`from debate_core.testing import fakes`) alone, and refused any statement with a comment
     inside it (none had one).
   - **Tidying.** `ruff check --select I --fix` and `ruff format` on the 20 touched files sorted and
     wrapped them, and merged three existing `from debate_core.testing.fakes import
     ScriptedModelResponse` lines into the new ones.
   - **Check.** A second run in `--check` mode finds `0 files`.
2. **A test, not an import-linter contract (ac1 allows either).**
   - **Your question.** You asked whether import-linter can express "the package module imports
     nothing". It can only partly. import-linter 2.15's forbidden contract has `as_packages =
     false`, which narrows the source to the `__init__` alone. But it forbids only the modules it
     names: a stdlib or third-party import (`import pytest`) is outside its graph unless listed, and
     it does not see `importlib.import_module`.
   - **What the test covers.** The `ast` test is strictly stronger. It also catches a lazy import
     inside a module `__getattr__`, which a contract reads as an ordinary import edge anyway.
   - **Keeping the guard honest.** Seven cases pin each kind of import the check finds, and one
     case shows a docstring and a plain function pass.
3. **No module `__getattr__` shim.** I tested it in a scratch package rather than assume.
   - **Pyright.** With a module `__getattr__`, `pyright --strict` reports `0 errors` for a stale
     `from pkg import FixedClock`. pyright is the earliest signal an in-flight branch gets after the
     merge, and the shim would switch it off.
   - **Runtime.** A shim that raises `ImportError` also breaks `from pkg import submodule`. The
     `from`-import probes the package with `hasattr` first, and `hasattr` lets the `ImportError`
     through. It would have to raise `AttributeError` for unknown names, and so keep a list of the
     old names.
   - **Without it.** Plain Python already says `ImportError: cannot import name 'FixedClock' from
     'debate_core.testing'`, and the new docstrings say where names live.
4. **The docstrings were kept and rewritten,** so `help(debate_core.testing)` still says what is
   in the package and where to import it from.
5. **No sync with `dev`.** `dev` moved by one commit since this branch started, `234a4a7` (#372),
   which refreshes `ROADMAP.md` and `docs/README.md`. Nothing here touches either file.
6. **Coordination with v1-e39-t03 and v1-e39-t09** (read-only, against their local branches
   `2b19963` and `d42d846`):
   - Neither has merged.
   - None of the files they add or change imports a re-exported name from either package.
   - Neither touches any file this branch changes.
   - So whichever merges after this one has only dev's own imports to inherit, and those are
     already rewritten here.

## Operator follow-ups

None. The whole default selection runs in the pull request's `ci` check, as the PM's note says. When
that check is green, ac2's last clause is met, and the Goal's phase can be set to `Succeeded` (the
PM's call).

## Follow-up work

- **What still carries the selection.** I traced it with `select()`'s reasons over this branch,
  for the commits that barely moved:
  - **`debate_core/testing/fakes.py` is one module that imports every port.** Every test that
    needs one fake reaches caselist suppression, `parsed_store` and the rest. In `9877884` it
    accounts for 44 test files, and in `3f2530b` for 23. Splitting it per port (or per area) is the
    next cut.
  - **`debate_core/application/ports/__init__.py` re-exports every port**, the same pattern this
    task removed.
  - **`application/settings.py` imports `debate_core.evidence.near_duplicates`.** That puts every
    importer of `settings` into a near-duplicate change: 37 test files in `30c5157`.
  - **`debate_cli.container`, `app` and `exit_codes`** are reached by every CLI test, as expected of
    a composition root.
  - **`packages/debate_core/tests/conftest.py` names `tests/smoke/stand_ins/s3.py`.** That file in
    turn names a held-digests data folder, which brings 66 test files into `3f2530b`.

  The first three belong with E01 or E02, for the PM to place.
- **`docs/evidence/snapshot-text-format.md:299`** names `debate_core.testing.InMemoryCardEditLog`,
  which is now `debate_core.testing.fakes.InMemoryCardEditLog`. `docs/` is outside this task's
  packages, so I left it. It is a one-word fix whenever that document is next touched.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

Accepted. One step in this session before the pull request: set the phase `Succeeded` (question 2
below). The pull request then opens with no `--partial`. If its `ci` check fails, paste the failure
back here.

**What is good:**

* **The evidence is honest.** "Behaviour unchanged" is shown by identical collected counts
  (10,613/10,632, the same with the new file ignored). The guard was red against the old files and
  against a deliberate re-export in each.
* **The ac3 table explains its own median.** It says three rows crossing the 10th and 11th
  boundary carry most of the headline drop, and that without the whole-selection commits the gain
  is 1.7 points. That is the reading I need, not a flattering number.
* **Decision 3 was tested, not assumed:** a module `__getattr__` would silence pyright for stale
  imports, the earliest signal an in-flight branch gets. Declining it is right.
* **The coordination check** against v1-e39-t03's and t09's branches was done read-only.

**Rulings:**

1. **ac3's method: (a), accepted.** The own-tree column matching t28 row for row is the proof the
   harness reproduces the tool. The `--graph REV` option goes into the follow-up task (point 3),
   since that task has to be measured the same way.
2. **The phase: set it `Succeeded` now, in this session, with no spec amendment.** Every task since
   working agreement 10 has left the whole selection to the PR's `ci` check, and that check gates
   the merge: a red `ci` means no merge. So ac2's last clause is closed by the gate itself. Record
   that in ac2's row as "the CI clause is the pull request's required `ci` check, which gates the
   merge (working agreement 10)", then run `validate_specs.py`. Leaving the phase `InProgress`
   would force `--partial`, which holds back the follow-up task that will depend on this one.
3. **The follow-up: one p2 task in E01,** which owns `affected_tests.py`. The PM files it in the
   next batch. Its scope:
   * split `debate_core/testing/fakes.py` by port or area;
   * remove `application/ports/__init__.py`'s re-exports;
   * drop `settings.py`'s import of `evidence.near_duplicates`;
   * look at the test conftest's reach into `tests/smoke/stand_ins/s3.py`;
   * add `--graph REV` to `affected_tests.py`;
   * fix the one-word stale name in `docs/evidence/snapshot-text-format.md`.

   It is measured over the same 20 commits with that option.

**Not syncing with `dev`** (decision 5) is fine. `scripts/task sync` does it before the pull
request.

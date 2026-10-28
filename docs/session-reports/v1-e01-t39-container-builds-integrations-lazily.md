# Session report: v1-e01-t39-container-builds-integrations-lazily

| | |
|---|---|
| Task | `v1-e01-t39-container-builds-integrations-lazily` — The container imports each integration in its own factory, and selection follows a command to its factories |
| Spec | [`plan_specs/v1/e01-repo-foundation/t39-container-builds-integrations-lazily.yaml`](../../plan_specs/v1/e01-repo-foundation/t39-container-builds-integrations-lazily.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t39-container-builds-integrations-lazily` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Decision 6 of v1-e01-t32 is built. Every criterion passed in the session, so the Goal is
`Succeeded`.

- **The container.** Each `debate_core.integrations` import moved into the method that builds
  with it. Importing `debate_cli.container` or `debate_cli.app` used to load 35 integration
  modules and now loads none. A test in a fresh interpreter holds that.
- **Ruled condition 1.** A test builds every factory, found by reflection, under three settings
  variants. Between them the builds must import every integration the post-install check finds,
  and with any one made to fail to import, a build that imports it must fail.
- **Ruled condition 2.** No command's output changed except `UnknownCaselistEvent`'s hint, which
  now names `debate_cli.caselist_events`.
- **`affected_tests.py`** reads the container part by part and the registry command by command.
  A command module reaches the factories it names. A test that runs the app reaches the commands
  its literal arguments name; one whose arguments cannot be read still reaches every command.

**Read ac1 and ac3 first.** Over t38's 20 merges:

| | Before | After |
|---|---|---|
| Files selected only through `app.py`, summed | 531 of 3,621 | **335** of 3,380 |
| Median share of files | 41.3% | **29.6%** |
| Median share of tests | 34.7% | **30.2%** |
| t27's merge | 215 files, 104 only through `app.py` | **137** files, 45 |

t27's `bucket_mode/test_bucket_mode_kills.py` and `test_bucket_mode_removal.py` are no longer
selected for t27's change.

**Look at Deviation 1.** The PM's wording reads only a *function-level* import in `container.py`
as a factory's. That alone buys almost nothing (531 to 495), because the landscape merges reach
the container through its top-level *application* imports. I read a top-level import as belonging
to the parts whose code uses its names. That is t32's rule for conftests, and it is where the gain
comes from.

`UnknownSyncEvent`, in `debate_core`, carries the same stale module name. It is not changed,
because the forbidden list allows one hint (PM question 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `lazy-integrations` (Lazy integrations) | Done | Nine commits after the start commit, on `dev` at `03b23e2`, listed under Files changed. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, the files selected only through `app.py` over t38's 20 merges, before and after the rule | PASS | Under [ac1](#ac1-the-counts-first), measured before any code changed and again at the end. **At the start** (base `52ee574`, its own script, `--graph 52ee574`, t32's `reach_app.py`): **531 of the 3,565 files** selected come only through `app.py`; t32 measured 521 of 3,529 over the same 20. **Before** (base after the sync, `4c0fe72`): 531 of 3,621. **After** (this branch): **335 of 3,380**. With the PM's literal wording only: 495. |
| ac2: a test builds every factory and fails on an integration that fails to import; a planted break in a lazily imported integration is caught; tests shown failing first | PASS | **Red at the base** (`.venv/bin/python -m pytest -n 0 -p no:randomly packages/debate_cli/tests/test_container_factories.py`) → `3 failed, 3 passed`: both imports loaded 35 integration modules (`Left contains 35 more items, first extra item: 'debate_core.integrations'`), and 14 wired integrations were imported by no factory build (`no factory build imports these … 'debate_core.integrations.landscape.analytic_text_store', …`), since they were bound at import. **Green** → `6 passed`. **The script's new cases, red** against the base's `affected_tests.py` → `6 failed, 70 passed`. The 4 new cases that pass there are the ones that must not change: the app, the registry and `context.py` themselves, and an import module code uses. **Green** → `76 passed`. **The planted break** (`version_directories.py` names the wrong place; only `caselist retire`'s test reads it, through `cli.services.version_retention`) → `92 of 553 test files selected …; the nearest 11 ran (exit 1): 1 failed in 1.48s; caught: a selected test failed`. **The hint**, red → `1 failed`, green → `1 passed`. |
| ac3: the 20 merges re-measured with `--graph`, and the collected count unchanged | PASS | The table under [ac3](#ac3-the-measurements). **Collected count**, with CI's markers: the base `4c0fe72`, collected in a clone with its packages first on `PYTHONPATH` (checked: `debate_cli.container` loaded from the clone) → `17496/17549 tests collected (53 deselected)`. The branch → `17512/17566 (54 deselected)`. `comm` over the sorted ids: **0 lost, 16 added**: 6 in `test_container_factories.py` and 10 new cases in `test_affected_tests.py`. The extra deselected test is the new slow planted break. |
| Node `lazy-integrations`: `uv run pytest tests/scripts -k affected` | PASS | After the last sync: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/scripts -k affected -p no:cacheprovider -q` → `93 passed in 16.27s`. Same interpreter and arguments as `uv run pytest`, with the time limit on the interpreter (agreement 10). |
| PM: startup cost before and after | PASS | Below, under [Startup](#startup). `--help` 501 → 469 ms, `--json --version` 489 → 463 ms, medians of 10, interleaved. |
| PM: doctor still reports every integration's health | PASS | `doctor`'s wired-integrations check reads the container's import statements (`installation.wired_integrations`), wherever they are. It finds the same 33 modules: the every-factory test checks that the builds cover all of them. `commands/test_doctor.py` and `test_installation.py`, which pin the list, pass unchanged (in the CLI runs below). |
| PM: the four mutants | PASS | Each is caught (mutants 1 to 4 below). |

### ac1: the counts first

**Method:** t32's. Each column is that commit's own `affected_tests.py` over that commit's tree
(`--diff <merge> --graph <rev>`), in one process per batch (`measure.py` and `reach_app.py`, copied
from t32's scratchpad). "Only through `app.py`" is the selection with and without `app.py`'s
dependents in the walk. The new script reads them in its per-command step as well, so blocking
them blocks both.

**At the start of the session** (base `52ee574`, before any code changed): over t38's 20 merges,
**531 of the 3,565 selected files** came only through `app.py`. That is 104 per landscape merge,
and t27's merge selected 211.

**t27's slow files, then** (`--diff 8051c77 --graph 52ee574 --explain`):

- `bucket_mode/test_bucket_mode_kills.py` and `test_bucket_mode_removal.py`: `uses the world
  fixture of packages/debate_cli/tests/bucket_mode/conftest.py, which needs debate_cli.app, which
  imports debate_cli.command_registry, which imports debate_cli.commands.landscape, which imports
  debate_core.application.landscape_report, which changed`.
- `tests/smoke/test_caselist_remove_smoke.py` and `test_caselist_pull.py`: `imports
  tests/smoke/installed_build.py, which runs debate_cli.app, which imports …` (the same chain).
- `tests/smoke/test_caselist_pull_in_process.py`: `imports debate_cli.container, which imports
  debate_core.application.aff_assignment, which imports debate_core.application.landscape_report`.

The last chain is the one that matters for the design. The landscape merges reached every command
through the container's top-level **application** imports (`aff_assignment`, `landscape_run`),
through `context.py`, not through an integration. Reading only function-level imports as a
factory's could not cut it (Deviation 1).

**At the end, t27's slow files** (`--diff 8051c77`, before over `4c0fe72` with its script, after
over this branch):

| File | Before | After |
|---|---|---|
| `bucket_mode/test_bucket_mode_kills.py` | through `app.py` → `commands.landscape` | **not selected** |
| `bucket_mode/test_bucket_mode_removal.py` | the same | **not selected** |
| `tests/smoke/test_caselist_remove_smoke.py` | through `installed_build.py` → `app.py` | `names tests/fixtures/landscape/golden/report.md, which changed`: t27 changed a fixture it reads |
| `tests/smoke/test_caselist_pull.py` | the same | through the smoke conftest's `installed_build.py`, `for landscape report and landscape evaluate`. The pull test's tuple of stage names holds `"landscape", "report"`, which reads as those two words of a command. It over-selects one file, as a fail-toward-more coincidence should. |

### ac3: the measurements

**Columns.** Before is `4c0fe72` (`dev` after the first sync) with its own `affected_tests.py`.
The script did not change on `dev` between `52ee574` and there (`cmp`). After is this branch,
measured at `0d64b06`. Later commits change only test cases and the planted-break harness, which
`dev` changed too (`03b23e2`, synced after measuring). Neither is an input the selection reads
for these merges. **"Tests"** weights each file by its test count in that tree's own collection.

#### t27 and t38's 20 merges

| Commit | Files before | Files after | Tests before | Tests after | Only through `app.py`, before | after |
|---|---|---|---|---|---|---|
| `8051c77` #552 t27 | 215 (38.9%) | 137 (24.8%) | 5,704 (32.6%) | 4,592 (26.2%) | 104 | 45 |
| `a077632` #546 PM batch | 52 (9.4%) | 53 (9.6%) | 1,902 (10.9%) | 1,918 (11.0%) | 0 | 0 |
| `9c99f03` #543 refresh | 19 (3.4%) | 20 (3.6%) | 1,164 (6.7%) | 1,180 (6.7%) | 0 | 0 |
| `030cc4c` #545 usage telemetry | 446 (80.8%) | 447 (80.8%) | 13,049 (74.6%) | 13,065 (74.6%) | 6 | 6 |
| `1ace4e5` #544 readable impact chains | 215 (38.9%) | 137 (24.8%) | 5,704 (32.6%) | 4,592 (26.2%) | 104 | 45 |
| `65f56d7` #542 bucket-mode report counts | 265 (48.0%) | 266 (48.1%) | 6,214 (35.5%) | 6,230 (35.6%) | 29 | 29 |
| `8a597db` #540 refresh | 19 (3.4%) | 20 (3.6%) | 1,164 (6.7%) | 1,180 (6.7%) | 0 | 0 |
| `8cf5e91` #541 PM batch | 33 (6.0%) | 34 (6.1%) | 1,516 (8.7%) | 1,532 (8.7%) | 0 | 0 |
| `7e271ed` #539 citation service | 441 (79.9%) | 442 (79.9%) | 13,159 (75.2%) | 13,175 (75.2%) | 16 | 11 |
| `57e3060` #538 refresh | 19 (3.4%) | 20 (3.6%) | 1,164 (6.7%) | 1,180 (6.7%) | 0 | 0 |
| `321b5ee` #537 scenario vocabulary | 271 (49.1%) | 222 (40.1%) | 8,212 (46.9%) | 7,479 (42.7%) | 70 | 34 |
| `f5a8221` #536 style-profile refusal | 321 (58.2%) | 322 (58.2%) | 8,922 (51.0%) | 8,938 (51.0%) | 20 | 20 |
| `ad7f5a1` #535 refresh | 19 (3.4%) | 20 (3.6%) | 1,164 (6.7%) | 1,180 (6.7%) | 0 | 0 |
| `206f2ec` #533 fetch command | whole | whole | 100% | 100% | whole | whole |
| `b3273fb` #534 unlabelled plan affs | 222 (40.2%) | 143 (25.9%) | 5,943 (34.0%) | 4,789 (27.3%) | 104 | 45 |
| `d0cc9c3` #530 refresh | 19 (3.4%) | 20 (3.6%) | 1,164 (6.7%) | 1,180 (6.7%) | 0 | 0 |
| `af7052e` #531 Bedrock invoke access | 385 (69.7%) | 386 (69.8%) | 10,559 (60.4%) | 10,575 (60.4%) | 11 | 11 |
| `ec02c33` #523 model classification | 243 (44.0%) | 244 (44.1%) | 6,867 (39.2%) | 6,883 (39.3%) | 87 | 86 |
| `2a33947` #529 kritikal affs | 234 (42.4%) | 184 (33.3%) | 6,616 (37.8%) | 5,802 (33.1%) | 71 | 35 |
| `987fa89` #528 refresh | 19 (3.4%) | 20 (3.6%) | 1,164 (6.7%) | 1,180 (6.7%) | 0 | 0 |
| `2110c13` #527 article service | 379 (68.7%) | 380 (68.7%) | 11,209 (64.1%) | 11,225 (64.1%) | 13 | 13 |

Totals: before 552 test files and 17,496 tests; after 553 and 17,512.

| Summary, t38's 20 | Files before | Files after | Tests before | Tests after |
|---|---|---|---|---|
| Median | 41.3% | **29.6%** | 34.7% | **30.2%** |
| Mean | 37.8% | 35.6% | 35.5% | 34.5% |
| Median of the 19 that are not whole | 40.2% | 25.9% | 34.0% | 27.3% |
| Files only through `app.py`, summed | 531 of 3,621 | **335 of 3,380** | | |
| The same under the PM's literal wording (Deviation 1) | | 495 of 3,640 | | |

**How to read it:**

- **The +1 rows are the new always-run test**, `test_container_factories.py`. No merge selects
  a file the base did not, apart from that one.
- **The landscape merges move most.** t27, t25 (`1ace4e5`), t24 (`b3273fb`), t17 (`2a33947`)
  and `321b5ee` lose 49 to 79 files each, and their files only through `app.py` halve.
- **What is left through `app.py`, 335 files:**
  - 152 are in the five merges that edit `container.py` itself (`030cc4c`, `65f56d7`, `f5a8221`,
    `af7052e`, `ec02c33`). A change to the file itself is still read as the whole file, as the
    proposal said (Follow-up work).
  - Most of the rest, 30 of each landscape merge's 45, are tests that mention `debate-research` in
    a string (an expected message) but whose arguments name no command. They cannot be told
    apart, so they reach every command, as before (Follow-up work).
- **Time to choose:** `measure.py`'s per-merge time, the graph built once, has a median of 9.7 s
  before and 10.0 s after (ranges 7.5 to 11.3 and 7.6 to 12.7 s). A whole run of the script on
  this branch takes 12 to 14 s.

### Startup

`debate-research --help` and `--json --version`, ten rounds, base and branch alternating inside
each round, through the same interpreter (`python -c "…from debate_cli.app import main; main()"`).
The base ran with its clone's packages first on `PYTHONPATH`. Load average was 3.3.

| Command | Base median (min) | Branch median (min) | Output |
|---|---|---|---|
| `--help` | 501 ms (475) | 469 ms (453) | identical |
| `--json --version` | 489 ms (465) | 463 ms (438) | identical but for the `commit` each checkout reports |

Lazy imports make neither command slower: both are about 30 ms faster.

### Planted breaks

- **New: `version_directories.py` names the wrong place.** Only `caselist retire`'s test reads
  the changed value, through `cli.services.version_retention` → `_build_version_retention` →
  the lazy import. That test is five steps from the break. Every test that runs the app with
  unreadable arguments sits at four, so the nearest ten would never reach it, and `dev`'s new
  mention-first ordering finds no name in the changed line (`return "this machine"`). The break
  therefore names the test (`read_by`, Deviation 2): it must be selected, and it runs first.
  Result: caught, `1 failed in 1.48s`.
- **Under PM mutant 4**, with the mutant committed so that the harness's clone carries it: caught,
  `AssertionError: packages/debate_cli/tests/test_caselist_retire.py is not selected`.
- The other breaks are unchanged, and validate-dev's slow tier runs them on the next pre-release.

### Mutation run

24 mutants, each applied to a committed file, run against the tests covering it and restored with
`git checkout`. The driver asserts the tree is clean after each. No Hypothesis test is involved;
each run still had a fresh `HYPOTHESIS_STORAGE_DIRECTORY`. That is more than agreement 10's
guide of about 20: the PM named four, and each rule of the script got at least one.

| # | Mutant | Result |
|---|---|---|
| 1 | **PM:** one factory's import (`LocalVersionDirectories`) moved back to module level | caught: both guard cases, and the every-factory test (the block no longer fails a build) |
| 2 | **PM:** the every-factory test skips one factory (`version_retention`) | caught: `no factory build imports` its two integrations |
| 3 | **PM:** a test whose arguments cannot be read is narrowed to fewer commands | caught: 4 cases |
| 4 | **PM:** `cli.services.X` is not followed, through the planted break | caught, with the mutant committed (above). The first attempt left it uncommitted; the harness clones `HEAD`, so it never ran the mutant. That attempt is discarded, not counted. |
| 5 | **PM:** `cli.services.X` is not followed, through the script's cases | caught: 5 |
| 6 | an import inside a part is not that part's | caught: 4 |
| 7 | a top-level import is always the whole module's (the PM's literal wording) | caught |
| 8 | a part does not reach the parts that call it (`self.bucket()`) | caught: 3 |
| 9 | module code that reads the container by reflection is not read whole | **survived first**: no case had such module code. Caught (4) after `factory_index.py` was added. |
| 10 | a function that reads the container's source gives its callers nothing | caught: 4 |
| 11 | every importer of a module that reads the container gets every part (what made `app.py` reach every factory through `installation.py`) | caught: 4 |
| 12 | a nested group's parent's words are left out | **survived twice**: the world had no nested group. Caught after `tub index build` and a test naming `index build` without `tub` were added. |
| 13 | a group named alone does not name its commands | caught: 2 |
| 14 | a helper's `("caselist", *arguments)` is not joined to its caller's `("remove", ...)` | caught: 2 |
| 15 | any `--help` is the root's | caught: 3 |
| 16 | `--help` names nothing | caught: 3 |
| 17 | prose is read as arguments | **survived first**: the prose sat in an `assert` message, which is never read as a run. Caught (2) after it moved into a call. |
| 18 | a helper that runs the app is reached whole instead of followed to its callers | caught: 4 |
| 19 | the conftests above a test add no arguments | **survived first**: no conftest ran the app. Caught (2) after the `world` conftest was added. |
| 20 | a narrowed conftest reached for a command is reached by its chain, not its import (the bug that sent every smoke test along) | **survived first**, for the same reason. Caught: 6. |
| 21 | the guard ignores a library an extra adds | caught |
| 22 | a blocked integration leaves its package attribute (`from debate_core.integrations import secrets_manager` then still works) | caught |
| 23 | a reflection call does not read the container whole | caught: 4 |
| 24 | a command's own group words are left out | caught: 4 |

Every mutant but 4 was rerun once on the final world: 23 of 23 caught. Mutant 4 was run
committed, as above.

### What this session ran before the report (working agreement 10)

- **The affected set is the pull request's.** `.venv/bin/python scripts/affected_tests.py` →
  `188 of 553 test files (34.0%) chosen in 14.3 s from 9 changed files`, which is 4,888 tests.
  That is over two minutes here, so agreement 10's bullet applies and the pull request's `ci`
  runs it. Instead, within two minutes each (alarm on `.venv/bin/python -m pytest`,
  `-n auto -m "not slow and not live"`), after the first sync:
  - the always-run list with `tests/scripts` → `2006 passed in 73.46s`;
  - `packages/debate_cli/tests` without `bucket_mode/` → `1059 passed in 50.68s`;
  - `packages/debate_cli/tests/bucket_mode` → `132 passed in 80.88s`.

  The second sync brought one commit, `03b23e2`, which changes only
  `tests/scripts/test_affected_tests_planted_breaks.py`. After it: the node criterion (`93
  passed`) and the planted break (caught).
- **Ruff:** `uv run --frozen ruff format --check .` → `1550 files already formatted`. `uv run
  --frozen ruff check .` → `All checks passed!`.
- **pyright:**
  - `.venv/bin/pyright packages/debate_cli` → `0 errors, 0 warnings, 0 informations`.
  - On the script and the test files I changed, outside pyright's `include` → `1 error`:
    `Import "task_helper" could not be resolved` in `test_affected_tests.py`. The base's copy of
    that file gives the same error, as t32 recorded.
- **Import boundaries:** `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.` `uv run
  --frozen python scripts/check_thin_handlers.py` → `OK: 67 CLI command and API route handlers
  within 25 statements`.
- **Specs:** `uv run scripts/validate_specs.py` → `OK: 492 files, 40 epics, 430 tasks, 22
  releases`.
- **Docs checks**, on this report:
  - `uv run --frozen python scripts/check_links.py` → `OK: 2793 relative links and anchors in 427
    Markdown files`.
  - `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments
    in 530 shell code blocks in 192 Markdown files (1 session reports changed since origin/dev)`.
  - `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 56 indexed documents
    under docs/ have a description`.

## Files changed

Nine commits on `dev` at `03b23e2`, after the start commit, plus this report's:

- **`b7325d9`, the container.** `container.py`: the 17 top-level `debate_core.integrations`
  statements moved into the 34 functions that use their names, by a codemod that read the syntax
  tree. The three names used only in annotations are under `TYPE_CHECKING`. The per-import
  "Imported here, not at module scope" comments went, since the sort had left several over imports
  they did not describe. The module docstring says once why every integration is imported in its
  factory. `test_container_factories.py` (new): the guard, the every-factory test with its
  planted import failure, and two checks of the test's own machinery.
- **`16d2975`, the script.** `affected_tests.py`: the container read part by part, the registry
  read command by command, the per-command walk from the app to the files that run it, and the
  docstring. `test_container_factories.py` joins `ALWAYS_RUN`. Ten new cases in
  `test_affected_tests.py`.
- **`b8c53f0`, `1404873`.** The planted break, the `read_by` field, and `--help` read as the root's
  only before any command word.
- **`e39ff01`, the hint.** `commands/caselist.py`'s `UnknownCaselistEvent`, and its assertion in
  `test_caselist_import.py`.
- **`0d64b06`, `c8077c8`, `f015d27`.** A comment's layout, and the cases the surviving mutants
  asked for.
- **The spec:** the Goal's phase, Succeeded.

## Deviations from the spec

1. **A top-level import in `container.py` belongs to the parts whose code uses its names.** The
   PM's wording reads only a function-level import as a factory's.
   - **Why:** the container imports 58 `debate_core` application, domain and retrieval modules at the top. Under the literal
     rule they stay the whole file's, and through `context.py` every command's. Measured over t38's
     20 merges, files only through `app.py` go from 531 to 495 under the literal rule, and to 335
     under this one. t27's merge selects 216 files under the literal rule and 137 under this one.
     The difference is the landscape merges, whose changes reach the container through
     `aff_assignment` and `landscape_run`.
   - **Precedent:** t32 read conftests the same way, and the PM accepted it ("an import inside a
     fixture's function counts for that fixture, as one at the top of the file does").
   - **Failing toward more:**
     - an import that module code uses (a base class, a decorator, a constant, a dunder method)
       is the whole file's;
     - so is one that nothing uses;
     - so is any change to `container.py` itself.

     An application module that fails to import still fails the container's import. The tests
     selected for the parts that use it are among those that fail, and the every-factory test is
     always run.
   - Mutant 7 is this rule turned back into the literal one, and the cases catch it.
2. **The planted-break harness gained an optional `read_by`**, a test that must be selected and
   runs first. This break's reading test is five steps away and the nearest ten cannot reach it.
   The PM has filed the ordering itself (`v1-e01-t40`); this leaves every other break as it was.
3. **"The commands its literal arguments name" is read as runs of literal words**, not as single
   words. A first version took any literal word, and over the real tree it selected the
   bucket-mode tests "for `files build`" (a `"files"` in prose and the `"build"` of `tub index
   build`). It also selected every smoke test for words in the smoke conftest. The rules, each
   with a case and a mutant:
   - a run is the literal words of one call's arguments, list, tuple or assigned constant;
   - a spaced string counts only if it starts like a command line;
   - a group ending a run that `*arguments` follows joins its caller's run;
   - a group alone names all its commands;
   - `--help` is the root's only before any command word.
4. **A module whose *functions* read the container's source gives every part to the files that
   call them, or run the module, not to every importer.** `app.py` imports `installation.py` for
   its error message. Read whole, that made every factory reach every test that runs the app.
5. **`UnknownSyncEvent`'s message (`debate_core/application/caselist_sync.py`) also says "the table
   in debate_cli.commands.caselist".** The ruling names `UnknownCaselistEvent`, and the forbidden
   list allows one hint, so it is unchanged (PM question 1).

## Decisions and assumptions

1. **What counts as an integration module, for the guard:** a `debate_core.integrations` module,
   or a module whose distribution is one an extra of `debate-core` adds. The extras are read from
   the installed metadata through `installation.optional_core_dependencies`, not listed in the test.
2. **The every-factory test's settings variants:**
   - the `test` profile;
   - "the operator's Mac": a bucket, the caselist API, Bedrock, the macOS notifier, a takedown
     profile;
   - "the cloud run": SNS, bucket run state.

   Between them they reach every branch that imports an integration; the coverage assertion
   fails if a new integration is reached under none.
3. **What is kept by hand in that test** is only what a factory is called with, by
   `name: annotation`. A new factory with a new parameter fails the test, naming it. Two methods,
   `singleton` and `override`, are the container's machinery and are left out by name.
4. **Refusals.** A factory may raise a `ConfigurationError` or `TakedownNotConfigured` instead of
   building: the settings say no, as a run with them would be told.
5. **Offline building.** The AWS factories build under made-up static credentials and an
   AWS config in `tmp_path`, with instance metadata off. pytest-socket caught botocore's
   credential chain reaching for the network in the first version. One botocore data loader
   serves every session, which cut the test from 6.5 s to about 4 s. The clients are still real.
6. **The containers in that test are built through `validating_routing`, as `app.py` builds
   them.** Without it, `routing_policy`'s import was never exercised, and blocking it failed
   nothing.
7. **Holders.** A file can hold a container if it is a `debate_cli` module or imports one. The
   container's own parts import CLI modules too (`package_version`) and are excluded: counting
   them made one part read every other.
8. **A narrowed conftest reached for one command is reached by its import edge**, so that its
   fixtures go on narrowing it. Reached by the chain's description, it lost its narrowing, and every
   smoke test beneath it came along.

## Operator follow-ups

None. The whole planted-break set runs in validate-dev's slow tier on the next dev pre-release; the
new break was run here.

### PM questions

```text
PM questions from v1-e01-t39 (container builds integrations lazily)

1. UnknownSyncEvent names the old module too.
   debate_core/application/caselist_sync.py's UnknownSyncEvent (caselist pull, backfile import)
   ends "add the slug prefix to the table in debate_cli.commands.caselist". This task changed only
   UnknownCaselistEvent, as ruled, because the forbidden list allows one hint.
   Options:
   (a) leave it;
   (b) change it to debate_cli.caselist_events in the next task that touches caselist_sync.py.
   Recommendation: (b). Same reason as t32's question 1, and caselist_sync.py is a hub, so it is
   cheapest beside another change to it.

2. Deviation 1: top-level container imports read by use.
   Options:
   (a) accept it;
   (b) keep the literal wording: 495 rather than 335 files only through app.py.
   Recommendation: (a). It is t32's conftest rule applied to the container, and it is where the
   gain is.
```

## Follow-up work

- **A change to `container.py` itself is read as the whole file.** Five of t38's 20 merges edit
  it, carrying 152 of the 335 files left. Reading the diff part by part, so that a new factory
  reaches only what names it, is the next step. That is an E01 task for the PM to place.
- **Tests that mention `debate-research` in a string run the app**, by the script's console-script
  rule, and name no command. They reach every command: about 30 per landscape merge, most of them
  `debate_core` tests asserting a message. Reading a mention inside a longer message as prose
  would cut them.
- **Doctor reads every part**, because its check imports every integration, so a test that runs
  `doctor` is selected for any integration's change. A test that runs it with `--help` no longer
  is.
- **The nearest-ten ordering** is `v1-e01-t40`'s, as the PM filed it. `read_by` can go once
  ordering by duration or by readers reaches a five-step test.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-28

**Notes:**

t32's Decision 6 is built, and its measured gain is real.
1. **ac1 and ac3 pass.** Over t38's 20 merges, files selected only through `app.py` fall from 531 to
   335, and the median share of files from 41.3% to 29.6%. t27's merge goes from 215 files to 137, and
   its two slow bucket-mode files are no longer selected. No merge selects a file the base did not,
   except the new always-run test. The collected count loses nothing (0 lost, 16 added, all named).
2. **ac2 passes.**
   * The guard and the every-factory test were red at the base for the right reasons: 35 modules
     loaded at import, and 14 wired integrations imported by no build. They are green now.
   * The script's new cases were red, except the four that must not change.
   * The new planted break is caught.
3. **Ruled conditions met.** The every-factory test finds factories by reflection, covers every
   integration the post-install check names under three settings variants, and fails a build whose
   integration fails to import. No command's output changed except the one hint. Startup is about
   30 ms faster on both commands measured, and `doctor` still finds the same 33 modules.
4. **Mutants:** the PM's four and twenty more are caught. Five survived first; each called for a case
   that was then added. Mutant 4 counts only once it was committed, which the report says plainly.
5. **Deviation 1: accepted (question 2: (a)).** It is t32's conftest rule applied to the container,
   and it is where the gain is (495 under the literal wording, 335 under this). It fails toward
   more: module-level use, an unused import and any edit to `container.py` stay the whole file's.
   An application module that fails to import still breaks the container's import, and the
   every-factory test is always run.
6. **Deviation 2, `read_by`: accepted as a stopgap.** The break still asserts that the script selects
   the reading test (mutant 4 shows that assertion biting). It only skips the nearest-ten
   ordering, which is `v1-e01-t40`'s. The PM's next batch adds to t40: once its ordering reaches
   this five-step test, `read_by` is removed and this break is run without it.
7. **Deviations 3 and 4: accepted.** Each rule has a case and a mutant, and the first version's
   over-selection (`files build`, every smoke test) is the evidence for them.
8. **Question 1: (b).** The PM's next batch adds `UnknownSyncEvent`'s module name to
   `v1-e34-t31`, which changes the pull's messages and is the next task likely to touch
   `caselist_sync.py`.
9. **Decisions 1 to 8: accepted.** In particular, offline building with static credentials under
   pytest-socket, and building through `validating_routing` as `app.py` does.
10. **Follow-up work.** The PM's next batch files two E01 p3 tasks: a `container.py` diff read part
    by part (152 of the 335 files left), and a `debate-research` mention inside a longer message
    read as prose. The `doctor` note needs no task.
11. **The affected set** (188 files, 4,888 tests) is left to the PR's `ci`. The always-run list, the
    CLI tests and bucket mode pass in parts, and ruff, pyright, lint-imports and the docs checks
    pass. The one pyright error in `test_affected_tests.py` is the base's, outside the include
    (`v1-e01-t35`).
12. **Merge timing:** after Thursday 2026-10-29's tag has a green validate-dev run, and after the four
    PRs already held (e31-t31, e01-t41, e01-t42, e32-t29). This changes what CI selects and what the
    slow tier plants, so it must not ride Thursday's tag. Sync it first if any of those touched
    `affected_tests.py` or its tests. The PM checks the next pre-release's slow tier after it merges,
    since the new break runs there for the first time.

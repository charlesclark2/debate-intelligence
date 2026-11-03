# Session report: v1-e01-t32-test-selection-reach-round-three

| | |
|---|---|
| Task | `v1-e01-t32-test-selection-reach-round-three` — Test selection, round three: command registration, quoted words, the root pyproject and the contract suites |
| Spec | [`plan_specs/v1/e01-repo-foundation/t32-test-selection-reach-round-three.yaml`](../../plan_specs/v1/e01-repo-foundation/t32-test-selection-reach-round-three.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t32-test-selection-reach-round-three` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

All four of the spec's edges are cut, and so are the PM's additions, except `app.py`. That one is
counted and proposed, not built, as the PM's note allows (Decision 6).

- **Command registration:** registration moved to `debate_cli/command_registry.py`, which only
  `app.py` imports. `commands/__init__.py` holds only a docstring. The eight command modules that
  borrowed a flag or a helper from `store`, `caselist` or `landscape` now import it from
  `debate_cli/options/` or a module beside it. Imported alone, each of the 21 command modules
  loads no other command module. At the base, importing `verify` loaded 20 others.
- **Contract suites:** `testing/contracts/__init__.py` holds only its docstring. t30's guard covers
  it and `commands/__init__.py`. A new guard says no command module imports another, by any
  spelling.
- **Quoted strings:** a quoted string names only what it denotes.
  - A `Path(__file__)` join denotes the path it builds.
  - A string with a slash denotes the existing paths it is the end of. One that starts with a
    slash denotes a path only from the root or the file's own folder, as the PM ruled.
  - A bare word names a folder or a script only where a path is built from it, and only from four
    letters up.

  So `"/account/email/verify"`, `"s3"`, `"flow"` and the planted-break file's
  `f"{CORE}/retrieval/identifiers.py"` name nothing.
- **Root `pyproject.toml`:** a change that touches only `[tool.importlinter]` selects
  `tests/architecture`. Any other table, or only a comment, is still the whole selection.
- **Conftests:** every conftest is read fixture by fixture, as the root one already was. The two
  package conftests were not edited (Decision 4).

**Behaviour is unchanged.** No test was lost: the base collects 17,166 tests and the branch
17,224. The 58 new ids are this task's own, by a diff of the collected ids.

**The Goal is Succeeded.** Every criterion passed in the session. One planted break, an old one
whose selection is identical at the base, runs longer than two minutes here. It is the one operator
follow-up, and it is not a criterion.

**Read ac3 first.** The gain is real but modest:

| | Files | Tests |
|---|---|---|
| t38's 20 merges, median share | 46.8% → 41.0% | 41.4% → 34.2% |
| t27, its share | 44.2% → 38.6% | 40.7% → 32.1% |

- t27's 7 API auth tests are gone.
- t27's removal smoke test and its bucket-mode kill tests stay, through `app.py`.
- `app.py` alone carries 521 of the 3,529 test files those 20 merges select, and 101 of t27's
  209.

**Look at Deviation 2:** the quoted-path rule is wider than the PM's wording in two places, so that
it never selects fewer tests than a real read needs.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `reach-three` (Selection reach, round three) | Done | Nine commits on `dev` at `b4c28c8`, listed under Files changed. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a test of one command imports no other command module, the contract re-exports are gone, and the guard fails on each re-added, by tests shown failing first | PASS | **Red first** (before any refactor): `.venv/bin/python -m pytest -n 0 -q tests/architecture/test_a_command_module_imports_no_other_command.py tests/architecture/test_fakes_reach_only_their_port.py --tb=line` → `14 failed, 76 passed`. The 14 were the 12 command modules that imported another (`caselist_backfile.py imports {'caselist': 44, 'store': 45}` and so on) and the two package modules (`contracts/__init__.py holds ['line 32: from debate_core.testing.contracts…`). **Green:** the same guards and `test_thin_handlers.py` → `124 passed`. **Re-added, each guard fails** (mutants 24 to 27 below): a re-export in `contracts/__init__.py`, an import in `commands/__init__.py`, `caselist.py` importing `store`'s flag, and `files.py` importing from `landscape` lazily inside a function. **A command alone:** a fresh interpreter imported each of the 21 command modules and listed the `debate_cli.commands.*` modules loaded → `imports no other command module` for all 21, with `command_registry` not loaded. At the base, `import debate_cli.commands.verify` loaded 20 others. |
| ac2: quoted words without a slash below the minimum length name no file, and an import-linter-only root pyproject change selects tests/architecture alone, by tests | PASS | Cases in `tests/scripts/test_affected_tests.py`, each expected selection written by hand. **Red:** against the previous script, the new-behaviour cases → `6 failed, 11 passed`. The 11 are cases that must not change, such as a pytest-table change still being the whole selection. The conftest cases → `3 failed, 11 passed`. The path-position cases → `2 failed, 64 passed`. **Green:** `66 passed`. Covered: `"s3"` names no script while a four-letter word in a path still does; a route, the root, the file's own folder, an f-string's tail from the root, a wildcard, a command line, an unknown base, a loop's items; another package's folder of the same name; a module named only in an f-string tail (the planted-break shape); a deleted fixture; import-linter only, both by `--diff` and on a branch; six other root `pyproject.toml` edits that stay whole; a package `pyproject.toml`. |
| ac3: the 20 commits re-measured with --graph against v1-e01-t30's figures, and the collected count unchanged, recorded in the report | PASS | Under [ac3](#ac3-the-measurements). t28's 20: median 60.1% → 58.5% of files, against t30's 57.7% over a 390-file tree. **Collected count:** at the synced base, `b4c28c8`, collected in a clone with its packages first on `PYTHONPATH` → `17166/17213 tests collected (47 deselected)`. The branch tip → `17224/17276 (52 deselected)`. `comm` over the sorted ids: 0 lost, 58 added. They are 33 in the new guard, 2 in t30's guard and 23 in `test_affected_tests.py`. The 5 extra deselected are the new slow planted breaks. |
| Node `reach-three`: `uv run pytest tests/scripts -k affected` | PASS | After the sync: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/scripts -k affected -p no:cacheprovider -q` → `83 passed in 16.59s`. Same interpreter and arguments as `uv run pytest`, with the time limit on the interpreter (agreement 10). |
| PM: a planted break for each narrowed edge | PASS | Five added to `test_affected_tests_planted_breaks.py`; each is caught after the sync (below). |

### ac3: the measurements

**Method.**

- **Columns.** Before is `b4c28c8` (today's `dev`, this branch's base after the sync) with its own
  `affected_tests.py`. After is `e2a0820` (this branch) with its script. The script's rules
  changed, so each column uses its own version. The only later commit, `19f4baa`, adds type
  annotations.
- **Each row** is `--diff <commit> --graph <graph>`, run in one process per graph
  (`measure.py`, kept in the scratchpad). The process builds the graph's layout and import graph
  once, since they depend only on the graph. It ran in batches under a 118 s alarm.
- **"Tests"** weights each file by its test count in that tree's own collection.
- **"Only through `app.py`"** is the selection with and without `app.py`'s edges in the walk.

#### t27 and t38's 20 merges

| Commit | Files before | Files after | Tests before | Tests after | Only through `app.py`, after |
|---|---|---|---|---|---|
| `8051c77` #552 t27 | 239 (44.2%) | 209 (38.6%) | 6,978 (40.7%) | 5,527 (32.1%) | 101 |
| `a077632` #546 PM batch | 77 (14.2%) | 49 (9.0%) | 2,356 (13.7%) | 1,809 (10.5%) | 0 |
| `9c99f03` #543 refresh | 26 (4.8%) | 18 (3.3%) | 1,382 (8.1%) | 1,127 (6.5%) | 0 |
| `030cc4c` #545 usage telemetry | 440 (81.3%) | 437 (80.6%) | 13,113 (76.4%) | 12,811 (74.4%) | 6 |
| `1ace4e5` #544 readable impact chains | 239 (44.2%) | 209 (38.6%) | 6,978 (40.7%) | 5,527 (32.1%) | 101 |
| `65f56d7` #542 bucket-mode report counts | 275 (50.8%) | 258 (47.6%) | 6,631 (38.6%) | 6,031 (35.0%) | 28 |
| `8a597db` #540 refresh | 26 (4.8%) | 18 (3.3%) | 1,382 (8.1%) | 1,127 (6.5%) | 0 |
| `8cf5e91` #541 PM batch | 35 (6.5%) | 30 (5.5%) | 1,615 (9.4%) | 1,423 (8.3%) | 0 |
| `7e271ed` #539 citation service | whole (`pyproject.toml`) | 432 (79.7%) | 100% | 12,921 (75.0%) | 16 |
| `57e3060` #538 refresh | 26 (4.8%) | 18 (3.3%) | 1,382 (8.1%) | 1,127 (6.5%) | 0 |
| `321b5ee` #537 scenario vocabulary | 270 (49.9%) | 265 (48.9%) | 8,171 (47.6%) | 8,008 (46.5%) | 69 |
| `f5a8221` #536 style-profile refusal | 328 (60.6%) | 314 (57.9%) | 9,247 (53.9%) | 8,739 (50.7%) | 19 |
| `ad7f5a1` #535 refresh | 26 (4.8%) | 18 (3.3%) | 1,382 (8.1%) | 1,127 (6.5%) | 0 |
| `206f2ec` #533 fetch command | whole (`packages/debate_cli/pyproject.toml`) | whole (same) | 100% | 100% | whole |
| `b3273fb` #534 unlabelled plan affs | 247 (45.7%) | 216 (39.9%) | 7,232 (42.1%) | 5,766 (33.5%) | 101 |
| `d0cc9c3` #530 refresh | 26 (4.8%) | 18 (3.3%) | 1,382 (8.1%) | 1,127 (6.5%) | 0 |
| `af7052e` #531 Bedrock invoke access | 393 (72.6%) | 376 (69.4%) | 11,098 (64.7%) | 10,321 (59.9%) | 11 |
| `ec02c33` #523 model classification | 268 (49.5%) | 236 (43.5%) | 8,126 (47.3%) | 6,657 (38.6%) | 87 |
| `2a33947` #529 kritikal affs | 259 (47.9%) | 228 (42.1%) | 7,708 (44.9%) | 6,412 (37.2%) | 70 |
| `987fa89` #528 refresh | 26 (4.8%) | 18 (3.3%) | 1,382 (8.1%) | 1,127 (6.5%) | 0 |
| `2110c13` #527 article service | 394 (72.8%) | 371 (68.5%) | 11,808 (68.8%) | 10,993 (63.8%) | 13 |

Totals: before 541 test files and 17,166 tests; after 542 and 17,224.

| Summary, t38's 20 | Files before | Files after | Tests before | Tests after |
|---|---|---|---|---|
| Median | 46.8% | **41.0%** | 41.4% | **34.2%** |
| Mean | 41.2% | 37.6% | 39.8% | 35.2% |
| Median of the 18 that are whole in neither column | 44.9% | 39.2% | 39.6% | 32.8% |
| Files only through `app.py`, summed | | 521 of 3,529 selected (14.8%) | | |

**How to read it:**
- **Landscape merges move most.** That is t27, t25 (`1ace4e5`), t24 (`b3273fb`), t07 (`ec02c33`)
  and t17 (`2a33947`). They drop by 5.6 to 6.0 points of files and 7.7 to 8.7 of tests.
  - The API tests named `tests/fixtures/landscape/` through their own `fixtures/landscape` join and
    through routes such as `"/landscape/synthpolicy26"`.
  - `tests/config` and `test_headings.py` read `config/landscape`.
  - Those three groups made up most of the drop.
- **The six refreshes fall from 26 files to 18.** The word `"task"` in branch names such as
  `"task/v1-e04-t02-http-fetcher"` no longer names `scripts/task`.
- **`7e271ed` is no longer the whole selection.** Its root `pyproject.toml` edit only touched
  `[tool.importlinter]`, so the commit selects what its code reaches: 79.7%.
- **The conftests' share is smaller than their reputation.**
  - The caselist conftest's fixture reading removes 15 files from `65f56d7` and 11 from
    `f5a8221`. Those tests use `local`, `imported_data_dir` or no fixture.
  - Most API tests use `world`, which needs almost everything (Follow-up work).
- **What is left above 40% is `app.py`, `settings.py` and `errors.py`.** In the five landscape
  merges, `app.py` alone carries 69 to 101 files.

#### t27's slowest files

PM's list: the API auth tests, the caselist removal smoke tests and the bucket-mode kill tests. From
`--diff 8051c77 --graph HEAD --explain`:

- **The 7 `test_auth_*.py` API files are no longer selected** (7 before, 0 after). They came
  through the API conftest naming `tests/fixtures/landscape/golden/report.md` by the word
  `"landscape"`. That word was really its own folder,
  `Path(__file__).resolve().parent / "fixtures" / "landscape"`.
- **`tests/smoke/test_caselist_remove_smoke.py` and `tests/smoke/test_caselist_pull.py` are still
  selected**, through `app.py`: `imports tests/smoke/installed_build.py, which runs debate_cli.app,
  which imports debate_cli.command_registry, which imports debate_cli.commands.landscape, which
  imports debate_core.application.landscape_report, which changed`.
- **`bucket_mode/test_bucket_mode_kills.py` and `test_bucket_mode_removal.py` are still selected**,
  through `app.py`: `uses the world fixture of packages/debate_cli/tests/bucket_mode/conftest.py,
  which needs debate_cli.app, which imports debate_cli.command_registry, which imports
  debate_cli.commands.landscape, …`.

These slow files are the floor until `app.py` stops reaching every command for every test that
runs the app. They are named under Follow-up work. The slow tests themselves were not changed.

#### t28's 20 commits, against t30's figures

t30's column was measured over a tree of 390 test files; these two are over today's 541 and 542.

| Commit | Files before | Files after | Tests before | Tests after | t30's after |
|---|---|---|---|---|---|
| `9101764` | 336 (62.1%) | 335 (61.8%) | 8,708 (50.7%) | 8,626 (50.1%) | 57.9% |
| `9f11fe1` | 321 (59.3%) | 315 (58.1%) | 8,405 (49.0%) | 8,106 (47.1%) | 56.9% |
| `29f074d` | whole (`pyproject.toml`) | 520 (95.9%) | 100% | 16,581 (96.3%) | whole |
| `edf8eba` | whole (`packages/debate_core/pyproject.toml`) | whole | 100% | 100% | whole |
| `30c5157` | 327 (60.4%) | 305 (56.3%) | 8,761 (51.0%) | 8,134 (47.2%) | 59.0% |
| `29c8293` | 349 (64.5%) | 326 (60.1%) | 9,543 (55.6%) | 8,910 (51.7%) | 64.1% |
| `387c961` | 272 (50.3%) | 258 (47.6%) | 8,503 (49.5%) | 8,021 (46.6%) | 52.1% |
| `9877884` | 474 (87.6%) | 466 (86.0%) | 14,653 (85.4%) | 14,284 (82.9%) | 84.9% |
| `72c1d05` | 256 (47.3%) | 234 (43.2%) | 6,092 (35.5%) | 5,438 (31.6%) | 52.3% |
| `3f2530b` | 377 (69.7%) | 336 (62.0%) | 10,146 (59.1%) | 8,651 (50.2%) | 66.7% |
| `801883a` | 94 (17.4%) | 67 (12.4%) | 3,035 (17.7%) | 2,492 (14.5%) | 18.5% |
| `993063c` | 335 (61.9%) | 334 (61.6%) | 8,692 (50.6%) | 8,610 (50.0%) | 57.7% |
| `8bbe1cd` | 275 (50.8%) | 255 (47.0%) | 6,631 (38.6%) | 6,008 (34.9%) | 52.8% |
| `ea09eb1` | 275 (50.8%) | 255 (47.0%) | 6,631 (38.6%) | 6,008 (34.9%) | 52.8% |
| `0a43e88` | 323 (59.7%) | 319 (58.9%) | 8,457 (49.3%) | 8,162 (47.4%) | 57.7% |
| `d730de0` | whole (`packages/debate_core/pyproject.toml`) | whole | 100% | 100% | whole |
| `55d0b4b` | whole (`packages/debate_core/pyproject.toml`) | whole | 100% | 100% | whole |
| `1e63363` | 191 (35.3%) | 189 (34.9%) | 4,926 (28.7%) | 4,797 (27.9%) | 36.4% |
| `b0820cf` | 50 (9.2%) | 43 (7.9%) | 2,232 (13.0%) | 1,995 (11.6%) | 8.7% |
| `4c5a766` | 282 (52.1%) | 265 (48.9%) | 6,725 (39.2%) | 6,215 (36.1%) | 54.1% |

| Summary, t28's 20 | Files before | Files after | Tests before | Tests after |
|---|---|---|---|---|
| Median | 60.1% | **58.5%** | 50.1% | 47.3% |
| Mean | 61.9% | 59.5% | 55.6% | 53.0% |
| Median of the 16 that are whole in neither column | 55.7% | 52.6% | 49.1% | 46.8% |

- **`29f074d` is the import-linter-only commit t30 named.** It is no longer the whole selection,
  but its other changes still select 95.9%.
- **The other three whole rows are package `pyproject.toml` dependency changes.** They stay whole
  by rule.
- **Over t30's own column the median is 57.7% to 58.5%.** The tree has 152 more test files since
  then, so the columns above are the like-for-like comparison.

**Time to choose.** `affected_tests.py --diff 8051c77`, old and new alternated twice at load
average 4 to 5:
- old: 8.4 s and 8.0 s;
- new: 10.0 s and 9.8 s.

The path index and the per-file path reading cost about 1.7 s. CI makes the choice in each part,
in parallel.

### Planted breaks

`.venv/bin/python -m pytest -m slow -n 0 -s -p no:cacheprovider -p no:randomly -q
tests/scripts/test_affected_tests_planted_breaks.py -k …`, in five groups after the sync, each under
a 115 s alarm. The load average was 4 to 49, from another session's tests.

| Break | Result after the sync |
|---|---|
| **New:** `caselist_events.py`, a slug implies the wrong event (the moved command helper) | 170 selected; nearest 10 → `1 failed, 22 passed, 13 deselected`; caught: a selected test failed |
| **New:** `contracts/harness.py` counts every page twice (no package re-export) | 49 selected; `1 failed, 18 passed`; caught |
| **New:** `fs_version_store.py` drops its last version (used through the caselist conftest's `removal_world`) | 218 selected; `1 failed, 22 passed`; caught |
| **New:** `tests/fixtures/extraction/news-article.html` changes its title (read as `"extraction/news-article.html"`, the end of its path) | 21 selected; `1 failed, 2 passed, 13 deselected`; caught |
| **New:** `pyproject.toml` renames an import-linter contract, nothing else | **10** selected, not the whole selection; `1 failed, 96 passed`; caught |
| DOI keeps a trailing dot | `1 failed in 1.25s`; caught. The inner run now shows no `deselected`: t34's showed this file's own 8 slow cases, the self-selection the spec named. |
| Canonical URL keeps its port; public suffix list gains a line | caught, both |
| File builder's fingerprint reversed | caught |
| `debate_api` fails to import | exit 4; caught: a conftest the selected tests load failed to import |
| `debate_workers` fails to import | caught |
| Unreached: a function nothing calls | `536 passed`; caught: **no**, as it must be |
| `debate_cli` retrieval failure exits 4 | **Not finished in the session.** It ran past 115 s twice. Its 10 nearest tests are the same 10 files at the base and on the branch, 7 of them `bucket_mode/`, which run serially under `-n 0`. Operator follow-up 1. |

Before the sync, the five new breaks were each caught in their own runs, all under two minutes. The
first version of the fixture break used `config/landscape/released.yaml`. Its 10 nearest tests are
the CLI tests that name the whole `config/` folder. The test that would catch it,
`tests/config/test_landscape_released_ids.py`, sorts after them and never ran, so it hung on slow
bucket-mode tests. I replaced it, and the harness's ordering is a follow-up.

### Mutation run

26 mutants of the new code and 4 re-added imports, each applied to a committed file. Each ran
against the tests covering it and was restored with `git checkout --`. The driver asserts that
`git status --porcelain` is empty after each. The guard mutants ran the two guard files with
`-n 0`, about 1 s each; the script mutants ran `test_affected_tests.py`, about 10 s each. No
Hypothesis test is involved, so agreement 8's database rule does not apply. That is more than
agreement 10's guide of about 20: the PM's amendment added a rule, and each of my rules got at least
one.

| # | Mutant | Result |
|---|---|---|
| 1 | **PM:** an existing quoted path is no longer selected (the tail lookup returns nothing) | caught: 4 tests |
| 2 | **PM:** the import-linter-only rule applies to a `[tool.pytest]` change | caught: `test_any_other_root_pyproject_change_is_the_whole_selection` |
| 3 | **PM:** a command module importing another through `from debate_cli.commands import x` passes the guard | caught: 4 self-checks |
| 4 | the guard checks nothing | caught: 9 |
| 5 | the guard misses a relative import | caught: 3 |
| 6 | two letters are enough for a word | caught |
| 7 | four letters are not enough | caught |
| 8 | a leading slash is read like a relative path | caught: the f-string tail case |
| 9 | a leading slash is read from the file's folder only, not the root | caught: the route case |
| 10 | a deleted file is not a known path | caught: the deleted-fixture case |
| 11 | `Path(__file__)` joins are not followed | caught: the other-package-folder case |
| 12 | `parents[N]` is one folder too high | **survived first**: the join fell back to words, which still selected. Caught after the case gained a test one folder down. A first version crashed the script and was discarded, not counted. |
| 13 | a wildcard is read as a name | caught |
| 14 | a string with whitespace is read as one path | caught: the command-line case |
| 15 | conftests are not read fixture by fixture | caught: 3 |
| 16 | a conftest reached by an import and then by a name stays narrowed | caught |
| 17 | a pytest hook is not module code | **survived first**: the hook's import was used by nothing else, so the unused-import rule selected every test anyway. Caught after `light` used the same import. |
| 18 | an import nothing uses reaches no test | caught: 2 |
| 19 | a fixture's parameters are not what it uses | caught, after `heavy` stopped using `light` in its body |
| 20 | a lower conftest naming a fixture does not make its tests users | caught: 3 |
| 21 | the `tool` table is compared whole | caught: both import-linter cases |
| 22 | a comment-only change is read as import-linter only | caught: 2 |
| 23 | an import-linter-only change selects nothing of its own | caught: the `--explain` reason |
| 24 | a word names a folder wherever it is | caught: 2 |
| 25 | a word names a folder nowhere | caught: 2 |
| 26 | a loop's items are not path segments | caught, after the loop case was added |
| 27 | re-added: `contracts/__init__.py` re-exports `walk_all_pages` | caught: `test_the_package_module_holds_only_a_docstring` |
| 28 | re-added: `commands/__init__.py` imports `verify` | caught: the same |
| 29 | re-added: `caselist.py` imports `store`'s flag | caught: `test_a_command_module_imports_no_other_command_module` |
| 30 | re-added: `files.py` imports from `landscape` inside a function | caught: the same |

### What this session ran before the report (working agreement 10)

All after the sync onto `b4c28c8`, unless said otherwise.

- **The affected set is the PR's.** `.venv/bin/python scripts/affected_tests.py` → `207 of 542 test
  files (38.2%) … from 46 changed files`, which is 5,976 tests. That is over two minutes here, so
  agreement 10's bullet applies and the pull request's `ci` runs it. Instead, within two minutes
  each (alarm on `.venv/bin/python -m pytest`, `-n auto -m "not slow and not live"`):
  - the always-run list with `tests/scripts` → `1934 passed, 1 warning in 69.59s`. The warning is
    pytest-socket's in `test_app.py::test_doctor_renders_a_table`. It appears at the base too: that
    test alone, run in the base clone, gives `1 passed, 1 warning`;
  - `packages/debate_cli/tests` without `bucket_mode/` → `1048 passed in 48.64s`;
  - `packages/debate_cli/tests/bucket_mode` → `103 passed in 61.13s`. Run together with the
    contracts, it ran past the alarm at load 13.5;
  - `packages/debate_core/tests/{contracts,testing,integrations/models,integrations/bedrock}` and
    `integrations/s3/test_s3_snapshot_store.py` → `978 passed in 5.31s`.
- **The node criterion:** `83 passed` (above).
- **Ruff:** `uv run --frozen ruff format --check .` → `1520 files already formatted`. `uv run
  --frozen ruff check .` → `All checks passed!`.
- **pyright:**
  - `.venv/bin/pyright packages/debate_cli packages/debate_core` → `0 errors, 0 warnings, 0
    informations`.
  - On the script and the test files I changed (outside pyright's `include`) → `1 error`: `Import
    "task_helper" could not be resolved` in `test_affected_tests.py`. The base's copy of that file
    gives the same error.
- **Import boundaries:** `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.` `uv run
  --frozen python scripts/check_thin_handlers.py` → `OK: 67 CLI command and API route handlers
  within 25 statements`.
- **Docs checks:**
  - `uv run --frozen python scripts/check_links.py` → `OK: 2716 relative links and anchors in 416
    Markdown files`.
  - `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → OK.
  - `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 55 indexed documents
    under docs/ have a description`.
- **Specs:** `uv run scripts/validate_specs.py` → `OK: 480 files, 40 epics, 418 tasks, 22
  releases`.

## Files changed

Nine commits on `dev` at `b4c28c8`, after the start commit, plus this report's:

- **`aed4f19`, command registration.**
  - `debate_cli/command_registry.py` (new) holds `register_commands` and `command_group`, with the
    old package docstring and a section on why. `commands/__init__.py` is a docstring.
  - `debate_cli/options/bucket_environment.py`, `options/snapshot_date.py`,
    `options/landscape_config.py`, `caselist_events.py` and `caselist_publish_refusals.py` are
    new. A script sliced the bodies out of `store.py`, `caselist.py` and `landscape.py` by their
    syntax trees, unchanged. The private helpers became public names; `_snapshot_date` is now
    `parse_snapshot_date`.
  - `app.py`, two tests (`test_app.py`, `test_caselist_import.py`), the container's and
    `caselist.py`'s docstrings, `check_thin_handlers.py`'s docstring, the CLI README and the
    `task-workflow.md` conflict table now name the new modules.
  - The new guard; t30's guard covers the two package modules.
- **`0266344`, contract suites.**
  - `contracts/__init__.py` is a docstring.
  - Ten importers name the defining module. A codemod read the table from the old file.
  - The contracts README.
  - The sync resolved two conflicts where `dev` had added imports beside them.
- **`bf862c6`, `cb006f4`, `4f010ac`, the script.** The path rules, the short-word rule and the
  table-aware root `pyproject.toml`; every conftest read fixture by fixture; bare words only from
  a path position. Each comes with its cases.
- **`1928950`, `627b99e`, `e2a0820`.** The five planted breaks, and the cases strengthened for
  mutants 12, 17, 19 and 26.
- **`19f4baa`.** Type annotations for pyright.
- **The spec:** the Goal's phase, Succeeded.

## Deviations from the spec

1. **`docs/process/task-workflow.md` changed**, outside `constraints.packages`. Its table of usual
   merge conflicts named `commands/__init__.py` as where commands are registered; it now names
   `command_registry.py`. No behaviour changes.
2. **The quoted-path rule is wider than the PM's wording in two places, so as never to select fewer
   tests than a real read needs.**
   - **Relative strings.** A string with a slash and no leading slash also denotes any existing
     path it is the end of, not only one from the root or the file's own folder.
     `test_citation_harvest.py` reads `tests/fixtures/extraction/news-article.html` as
     `"extraction/news-article.html"`, joined to a fixtures folder. Under the literal rule it would
     have named nothing. The planted break on that file shows the edge holds. Strings starting with
     a slash follow the PM's rule exactly, which is what cuts routes and f-string tails.
   - **Bare words.** A bare word in a path position keeps its old meaning when the script cannot
     follow the base (`root / "verify"`, an imported `FIXTURES / "cards"`). Only the words
     elsewhere stop naming folders and scripts: labels, arguments, dictionary keys. A survey of
     the repository found 730 such joins on bases the script cannot follow, and about 1,500 words
     outside path positions (dictionary keys, keyword arguments, comparisons, CLI arguments).
   - Every bare word still names a file by its full file name, wherever it is.
3. **One user-facing message names a module that no longer holds what it describes.**
   `UnknownCaselistEvent` says "add the slug prefix to the table in debate_cli.commands.caselist";
   the table is now in `debate_cli.caselist_events`. The forbidden list says no output change, so
   the text is unchanged, and `caselist.py` still imports the table, so the name resolves. Changing
   it is the PM's call (PM question 1).
4. **One planted break, "a retrieval failure exits 4", did not finish in the session after the
   sync.** It is t28's, not this task's. Its ten nearest tests are the same at the base. Operator
   follow-up 1 runs the whole set.

## Decisions and assumptions

1. **What two commands share goes outside the commands package.** That was the only way to meet
   "a test of one command imports no other command module" and the PM's guard mutant.
   - The new modules sit in `debate_cli/options/`, whose docstring already says "options more
     than one command takes", or beside it for the event table and the publish refusals.
   - `files.py` and `tub_index.py` keep their own `CONFIRM_PROD_FLAG` constants as they were.
2. **Function-level imports, as the PM asked.**
   - **Before this task:** for every file except the root conftest, `affected_tests.py` counted an
     import inside a function exactly as one at the top (`imported_names` walks every node), and
     grimp does the same between package modules. So moving a conftest's import inside a fixture
     would have changed nothing.
   - **Only the root conftest** attributed its imports to the fixtures whose code used the name.
   - **Now every conftest does**, and an import inside a fixture's function counts for that
     fixture, exactly as a module-level import used only by that fixture does. The case "an import
     inside a fixture" holds it, and a planted break through `removal_world` shows a real break is
     still caught.
3. **Fixture reading fails toward more tests.** These reach every test beneath a conftest:
   - its module code and autouse fixtures;
   - `pytest_*` hooks (new; the root conftest has none, so its behaviour is unchanged);
   - an import nothing in the conftest uses, since an import that fails still fails every test
     beneath;
   - a file it names, and a change to the conftest itself.

   A fixture's users are the tests beneath that contain its name as a word, and every test beneath
   a lower conftest that does. A fixture's parameters count as what it uses.
4. **The two conftests were narrowed in the script, not by editing them.**
   - Reading fixture by fixture gave each test what its fixtures use without moving a line of test
     code.
   - The caselist conftest's gain shows in `65f56d7` and `f5a8221`.
   - The API conftest's does not, because 19 of its 24 test files use `world` and its module-level
     corpus is built at import. Splitting those is test-code work (Follow-up work).
5. **The root `pyproject.toml` is compared as TOML, table by table** (`tool.<name>` on its own).
   - The changes are read from git for `--diff`, `--head` and CI's base, and from the working tree
     otherwise.
   - A missing or unreadable version, or a comment-only change, is the whole selection.
   - The whole-selection message is unchanged, so CI's summary text is the same. A stderr note
     lists the tables that changed.
6. **`app.py`: counted and proposed, not built.**
   - **The count:** over t38's 20 merges, 521 of the 3,529 selected test files come only through
     `app.py`, 14.8%. That is 69 to 101 per landscape merge.
   - **Why not lazy factory methods in the container:**
     - **They change behaviour.** An integration's import error would surface only in the commands
       that use it, not at startup, and the container's import time changes. The PM's condition was
       behaviour-identical.
     - **The script would not see it.** grimp and the script both count function-level imports, so
       lazy methods alone would not narrow the selection.
     - **Two edges would be missing.** Reading it that way needs a test-to-command edge (the
       command words a test invokes, `["landscape", "report", …]` or `debate-research caselist
       pull`) and a command-to-factory edge (`cli.services.<name>`).
   - **The proposal, for a follow-up task:**
     - the container imports each integration inside the factory that builds it;
     - the script reads a function-level import in `container.py` as that factory's;
     - a command module's `cli.services.X` reaches factory `X`;
     - a test that runs the app reaches the commands its literal arguments name;
     - a test whose arguments the script cannot read reaches every command, as now.

     A planted break in a lazily imported integration would hold it. The forbidden list would need
     the PM's ruling on the import-timing change.
7. **Measurement columns use each version's own script**, because the rules changed. t30 could use
   one script for both columns. This makes the after column the change a pull request sees.

## Operator follow-ups

1. **The whole planted-break set, once, after this report** (optional; validate-dev's slow tier runs
   it on the next dev pre-release anyway). Expected runtime: 3 to 5 minutes, most of it in the
   exit-code break's seven `bucket_mode/` files.

   Where: your Mac, in the task worktree.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t32-test-selection-reach-round-three
   ```

   ```bash
   uv run pytest -m slow -n 0 -s -p no:randomly tests/scripts/test_affected_tests_planted_breaks.py
   ```

   Success looks like `14 passed`. Every break's line ends `caught: a selected test failed` (or
   `errored`, or `a conftest … failed to import`), except "a function nothing calls answers
   wrongly", which must end `caught: no`. Paste the lines that start `debate_` and the last line.

2. **A note on the sync.** `scripts/task sync` fetched `origin/dev`, as it always does. Before that I
   also ran one `git fetch origin dev` by hand, to see whether `dev` had moved. It was read-only,
   but it was a network call I should have handed to you.

### PM questions

```text
PM questions from v1-e01-t32 (test selection, round three)

1. UnknownCaselistEvent's hint names the old module.
   The event table moved from debate_cli.commands.caselist to debate_cli.caselist_events. The
   message still says "add the slug prefix to the table in debate_cli.commands.caselist", because
   the forbidden list rules out an output change.
   Options:
   (a) leave it;
   (b) change the one module name in the next CLI task.
   Recommendation: (b). The hint is for whoever adds a slug, and the old module only re-imports it.

2. The app.py edge (Decision 6).
   It carries 14.8% of the selected files over t38's 20 merges, and about half of each landscape
   merge.
   Options:
   (a) file the proposal as a task, with a ruling that lazy integration imports in the container
       are an accepted change of import timing;
   (b) leave it.
   Recommendation: (a). It is the largest edge left, and the slow bucket-mode and smoke tests sit
   behind it.
```

## Follow-up work

- **`app.py` and the container** (Decision 6, PM question 2). The slow floor of t27's selection,
  `bucket_mode/test_bucket_mode_kills.py`, `test_bucket_mode_removal.py`,
  `tests/smoke/test_caselist_remove_smoke.py` and `test_caselist_pull.py`, is reached only through
  it.
- **The API conftest.** 15 of `f5a8221`'s 25 API test files come through `world` and 5 through
  module code (the corpus built at import). Splitting `PilotWorld` by surface (search, download,
  landscape, auth) and building the corpus in a fixture would let the script narrow it. That is
  test-code work for an E39 task.
- **The planted-break check's nearest-ten rule sorts by path within a chain length.** For a data
  file many tests name at one hop, the ten run are the alphabetically first. They can be seven slow
  `bucket_mode/` files, and the test that reads the file may never run. That is why the
  `released.yaml` break hung. Ordering by a file's test count or duration, or preferring readers by
  path over readers by word, would make each break faster and more pointed. It is t28's and t34's
  harness, so the PM places it.
- **The time to choose rose by about 1.7 s.** The path index is rebuilt for each selection; it
  could be built once from the tree and extended by the changed paths.
- **Words in path positions with bases the script cannot follow** (730 of them) still name
  folders, often `tmp_path / "parsed"`. Following more bases, a module-level constant imported from
  a helper or a fixture's `tmp_path`, would cut more without guessing.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

Every edge the spec named is cut, and the gain is honestly measured: modest, with the floor named.
1. **ac1 passes.**
   * Red first: 14 failed, the 12 command modules that imported another and the two package
     modules.
   * Each of the 21 command modules, imported alone in a fresh interpreter, loads no other. At the
     base, `verify` loaded 20.
   * Each guard fails on its re-added import (mutants 27 to 30), the lazy one inside a function
     included.
2. **ac2 passes.** 66 cases, each expected selection written by hand, red against the previous
   script. The cases that must not change (a pytest-table edit stays whole) are among them.
3. **ac3 passes.**
   * t38's 20 merges: median 46.8% to 41.0% of files, 41.4% to 34.2% of tests.
   * t27's seven API auth files are gone. Its slow smoke and bucket-mode files remain, through
     `app.py`, as reported.
   * Collected ids: 0 lost, 58 added, all this task's own.
4. **Planted breaks:** the five new ones are each caught. The import-linter-only break selects 10
   files, not the whole selection. The retrieval exit-4 break did not finish in the session, but its
   ten nearest files are the same as at the base. Validate-dev's slow tier runs the whole set, so
   operator follow-up 1 is not required.
5. **Mutants: 30.** Mutants 12 and 17 survived at first and were caught after the cases were
   strengthened. That is the right response, and the report says so plainly.
6. **Deviations 1 to 4 accepted.** Deviation 2 widens the PM's quoted-path wording in the one safe
   direction: it never selects fewer tests than a real read needs.
7. **Decisions accepted:**
   * what two commands share lives outside the commands package;
   * every conftest is read fixture by fixture, failing toward more tests;
   * the root `pyproject.toml` is compared as TOML, table by table, with a comment-only change
     still the whole selection;
   * each measurement column uses its own version's script;
   * `app.py` was counted and proposed, not built.
8. **PM question 1: (b).** `UnknownCaselistEvent`'s hint will name `debate_cli.caselist_events`.
   The output change is ruled into the container task below.
9. **PM question 2: (a).** The PM files Decision 6's proposal as an E01 task. Lazy integration
   imports in the container are an accepted change of import timing, on two conditions:
   * a test builds every factory, so an integration that fails to import still fails `ci`;
   * every command's output is otherwise unchanged.
10. **Follow-ups:**
    * the API conftest split (`PilotWorld` by surface, the corpus in a fixture) becomes an E39
      task;
    * the planted-break harness's nearest-ten ordering becomes an E01 p3 task;
    * the 1.7 s path index and the 730 unfollowable bases are noted, not filed.
11. **The hand `git fetch`** was read-only and was reported. Network calls go to the operator,
    except `scripts/task sync`.
12. **The affected set** (207 files) is left to the PR's `ci` under agreement 10. The always-run
    list, the CLI tests in two groups and the core suites the change reaches all passed, as did the
    static checks.

No re-review is needed. The Goal is `Succeeded`, and the PR merges in full.

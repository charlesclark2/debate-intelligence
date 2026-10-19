# Session report: v1-e01-t28-affected-test-selection

| | |
|---|---|
| Task | `v1-e01-t28-affected-test-selection` — scripts/affected_tests.py prints the tests a branch's changes can break |
| Spec | [`plan_specs/v1/e01-repo-foundation/t28-affected-test-selection.yaml`](../../plan_specs/v1/e01-repo-foundation/t28-affected-test-selection.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t28-affected-test-selection` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`uv run scripts/affected_tests.py [--base origin/dev] [--explain] [--run]` prints the test files a
branch's changes can reach. It builds the graph from the files on every run, with no saved state,
and choosing takes about 3–4 s. The graph covers imports between the workspace packages (grimp),
imports in test, conftest, helper and script files (`ast`), conftest scope, console-script and `-m`
runs, and files named by path, plus an always-run list. `--diff REV` / `--head REV` describe a past
commit from git without checking it out.

Every criterion passes. ac4's time to choose was measured by the operator on his Mac: median
3.1 s, largest 4.1 s, over the 20 commits. The Goal is **Succeeded**.

**Look at Deviation 1 first.** Read literally, "a conftest's imports count for every test beneath
it" makes the root `conftest.py` pull in a third of `debate_core`. That turns 9 of the last 20 task
commits into the whole selection. I narrowed the rule for the root conftest only, and that needs
your ruling.

The selected shares are high (median 79% of test files, 73% of tests) because of real coupling,
not rule noise: package `__init__` re-exports and the composition root. Follow-up work has a
proposal.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `affected-tests` (Affected test selection) | Done | Node criterion passes (40 passed), and so does every goal criterion. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on synthetic workspaces, a changed module selects every direct or transitive importer and nothing else, a changed fixture selects the tests naming it, the always-run list is always selected; tests shown failing first | PASS | `tests/scripts/test_affected_tests.py` builds a git workspace per case and compares exact, hand-written sets. **Red:** against a skeleton `select()` that selects nothing and never reports the whole selection (swapped in from a byte copy and restored, `cmp` equal, `git status` clean), `uv run pytest tests/scripts/test_affected_tests.py` → `37 failed in 4.10s`. The three cases added later were each shown red first: the generic-folder case against the old folder list (`extra: [...test_writes_a_data_folder.py]`), the wiring case against the pre-edit docs and prompt, and the root-conftest-names case against the mutant it was written for. **Green:** `40 passed`. **Mutation:** 19 mutants, each removing one selection rule, all caught (table below). |
| ac2: shared test ground reports the whole selection; a docs-only change selects the docs-check tests | PASS | Same file: `test_shared_test_ground_reports_the_whole_selection_and_exits_zero[conftest.py \| tests/pytest_plugins/run_in_parts.py \| pyproject.toml \| packages/debate_cli/pyproject.toml \| uv.lock \| .github/workflows/ci.yml]` checks the exact one line and exit 0; `test_run_runs_nothing_when_the_whole_selection_is_affected` (a failing test in the workspace is not run, exit 0); `test_a_docs_only_change_selects_the_docs_checks`, plus the `site/` Markdown, Terraform and spec cases. |
| ac3: planted breaks in at least five real modules across the four packages each fail a selected test; selection size reported | PASS | `uv run pytest tests/scripts/test_affected_tests_planted_breaks.py -m slow -s -n 0` → `7 passed in 46.97s` at `20c302a`. It runs in a `git clone --shared` of HEAD in a temp directory, and the worktree is never written. Each break is committed in the clone and described with `--diff HEAD`. pytest then runs the nearest selected tests with the clone's `src` first on `PYTHONPATH`, and the clone is reset and its bytes compared. Against the select-nothing skeleton (a temporary commit, dropped afterwards), two cases fail with `no selected test is traced to ...`. Results in the table below. |
| ac4: over the last 20 task commits, median and largest selected share and the time to choose; under 10 s on the operator's Mac (operator-measured) | PASS | Shares: median **79.4%** of test files (**72.8%** of tests), largest **100%** (4 commits are the whole selection; without them the median is 58.4% of files, 42.4% of tests). **Operator-measured time to choose** (the command under Operator follow-ups, run on the operator's Mac, 2026-10-19): median **3.1 s**, largest **4.1 s**, all 20 under 10 s. His shares matched the session's row for row. The session's own figures on the same Mac were a median of 3.2 s and a largest of 3.9 s. |
| ac5: working agreement 10 names the command in place of its interim rule, the session prompt tells a session to run it before the report, and the task-workflow guide says the same | PASS | Agreement 10's affected-set bullet now names `uv run scripts/affected_tests.py --run`; the interim rule ("Until then, the test directories…") is gone. `scripts/task_helper.py`'s "How to work" list has a new item 9. `docs/process/task-workflow.md` §3 says the same. `test_the_agreement_the_session_prompt_and_the_workflow_guide_send_a_session_to_the_script` failed against the pre-edit files (`assert 'uv run scripts/affected_tests.py --run' in '...'`) and passes now. No existing test pins the prompt's text (the ones that read `task_helper.PROMPT` check other substrings and still pass). |
| Node: `uv run pytest tests/scripts -k affected` | PASS | `40 passed in 9.72s` (the planted-break file is `slow`, so it is deselected here). |

### ac3: planted breaks

| Break | Module | Selected | Traced to it | Nearest run |
|---|---|---|---|---|
| A DOI keeps a trailing dot | `debate_core/retrieval/identifiers.py` | 20 of 310 | 6 | 6 files: 1 failed |
| A canonical URL keeps its default port | `debate_core/retrieval/canonical_url.py` | 20 of 310 | 6 | 6 files: 1 failed, 4 passed |
| The bundled public suffix list gains a line (package data) | `debate_core/retrieval/data/public_suffix_list.dat` | 12 of 310 | 5 | 5 files: 1 failed, 89 passed |
| The file builder's fingerprint is reversed (shared test helper) | `debate_core/testing/file_builder.py` | 18 of 310 | 5 | 5 files: 1 failed, 1 passed |
| A retrieval failure exits 4 | `debate_cli/exit_codes.py` | 107 of 310 | 97 | 10 files: 1 failed, 23 passed |
| The package fails to import | `debate_api/__init__.py` | 19 of 310 | 7 | 7 files: 1 failed |
| The package fails to import | `debate_workers/__init__.py` | 18 of 310 | 4 | 4 files: 1 failed |

"Selected" includes the always-run list and the tests that read Python source, which every Python
change selects. "Nearest" means the selected tests with the shortest chain back to the break, run
with `-x`.

The first version of this check found a real bug. The `.dat` file's folder is named `data`, and
`"data"` is a path literal in dozens of CLI tests (`tmp_path / "data"`). Those tests were therefore
"nearest", and 179 of them passed. `data` is now a generic folder name, with a test for it.

### ac4: the last 20 task commits on dev

| Commit | Task | Selected | Share of files | Share of tests | Time to choose | Root conftest reached |
|---|---|---|---|---|---|---|
| `9101764` | v1-e30-t24-status-residue-and-held-digests | 245 of 308 files | 79.5% | 75.9% | 3.9 s | yes |
| `9f11fe1` | v1-e30-t25-store-sync-withholding | 174 of 303 files | 57.4% | 43.8% | 3.7 s | |
| `29f074d` | v1-e33-t02-lossless-card-writer | whole: `pyproject.toml` | 100% | 100% | 0.2 s | |
| `edf8eba` | v1-e04-t01-url-canonicalization | whole: `packages/debate_core/pyproject.toml` (also root `pyproject.toml`, `uv.lock`) | 100% | 100% | 0.2 s | |
| `30c5157` | v1-e31-t20-long-cuts-and-limits | 255 of 290 files | 87.9% | 79.9% | 3.6 s | yes |
| `29c8293` | v1-e33-t01-file-recipe-format | 256 of 290 files | 88.3% | 80.9% | 3.5 s | yes |
| `387c961` | v1-e31-t19-remaining-cite-shapes | 262 of 287 files | 91.3% | 83.2% | 3.3 s | yes |
| `9877884` | v1-e31-t15-zip-guard-and-exporter-quirks | 259 of 285 files | 90.9% | 81.4% | 3.3 s | yes |
| `72c1d05` | v1-e30-t20-removal-output-loose-ends | 165 of 284 files | 58.1% | 41.0% | 3.2 s | |
| `3f2530b` | v1-e30-t23-held-digests-and-manifest-fsync | 268 of 282 files | 95.0% | 85.4% | 3.2 s | yes |
| `801883a` | v1-e34-t27-wrapper-and-check-launchd-options | 54 of 276 files | 19.6% | 18.6% | 3.1 s | |
| `993063c` | v1-e30-t19-residue-clearing-gaps | 219 of 276 files | 79.3% | 69.8% | 3.2 s | yes |
| `8bbe1cd` | v1-e34-t16-dry-run-names-no-home-path | 157 of 274 files | 57.3% | 40.1% | 3.1 s | |
| `ea09eb1` | v1-e34-t26-pending-work-and-banner-words | 155 of 272 files | 57.0% | 39.9% | 3.2 s | |
| `0a43e88` | v1-e30-t22-held-rows-publish-nothing | 154 of 269 files | 57.2% | 40.5% | 3.1 s | |
| `d730de0` | v1-e05-t04-prompt-registry | whole: `packages/debate_core/pyproject.toml` (also `uv.lock`) | 100% | 100% | 0.2 s | |
| `55d0b4b` | v1-e05-t02-bedrock-adapter | whole: `packages/debate_core/pyproject.toml` (also root `pyproject.toml`) | 100% | 100% | 0.2 s | |
| `1e63363` | v1-e34-t25-reinstall-keeps-every-setting | 100 of 260 files | 38.5% | 28.8% | 3.0 s | |
| `b0820cf` | v1-e31-t21-cluster-shapes-and-sampler | 22 of 260 files | 8.5% | 11.6% | 3.0 s | |
| `4c5a766` | v1-e31-t16-version-directory-retention | 152 of 259 files | 58.7% | 39.8% | 3.0 s | |

How this was measured:
- Each row is `uv run scripts/affected_tests.py --diff <commit>`, which reads that commit's own files
  from git.
- "Share of tests" weights each selected file by its test count in today's default selection
  (`pytest --collect-only`: 9,514 tests in 8.5 s). For older commits it is an estimate.
- The task commits are the first-parent commits on `origin/dev` whose subject starts with a task
  name.
- "Root conftest reached" marks the commits that Deviation 1 keeps from being the whole selection.

### Mutation run: 19 mutants on `scripts/affected_tests.py`

Each mutant removed one selection rule. The synthetic tests ran against it, then the file was
restored from a byte copy, compared, and `git status` checked clean. All 19 were caught. The rules
removed:

- a module depends on the packages that contain it
- tests depend on the conftests above them
- the root conftest's fixture users are found
- its autouse fixtures count for every test
- console scripts and `-m` count as runs
- a name in a literal counts as a mention
- the Python files beside a data file read it
- a package module reads only its own package
- an unnamed data file falls back to its package's tests or the whole selection
- a package `pyproject.toml` is shared ground
- any Markdown file selects the docs checks
- source readers are selected when Python changes
- docstrings are not mentions
- a bare import finds a script
- relative imports in test folders resolve
- a deleted module's package is reached
- `data` is a generic folder
- uncommitted and untracked changes count
- a root conftest reached by name is the whole selection

That last mutant survived the first run, so its test was added, and the mutant was then caught.

### What this session ran before the report (working agreement 10)

- `uv run scripts/affected_tests.py --run` on this branch printed the whole-selection line and ran
  nothing, because the branch changes `pyproject.toml` and `uv.lock` (adding grimp).
- To test everything else on the branch, `uv run scripts/affected_tests.py --base 628b07e --run`
  described every change except that dependency commit: 28 of 310 test files, chosen in 3.8 s.
  pytest finished `1 failed, 1272 passed in 62.46s`. The failure was real:
  `tests/architecture/test_single_interpreter_source.py` read `"grimp>=3.17"` as a Python version.
  Fixed in `20c302a` (Decision 9). The same 28 files then gave `1273 passed in 75.50s`.
- `ruff format --check .` → 872 files already formatted
- `ruff check .` → All checks passed
- `pyright scripts/affected_tests.py` → 0 errors. No package changed.
- `lint-imports` → 12 kept, 0 broken
- `scripts/validate_specs.py` → OK
- `scripts/check_command_blocks.py --base origin/dev` → OK
- `scripts/check_links.py` → OK

## Files changed

- `scripts/affected_tests.py` (new): the tool.
- `tests/scripts/test_affected_tests.py` (new): ac1, ac2, ac5 and `--run`, on synthetic workspaces.
- `tests/scripts/test_affected_tests_planted_breaks.py` (new, `slow`): ac3.
- `pyproject.toml`, `uv.lock`: grimp named in the dev dependencies, as the PM asked.
- `docs/process/working-agreements.md`: agreement 10 names the command in place of the interim rule.
- `scripts/task_helper.py`: the session prompt's "How to work" list, item 9.
- `docs/process/task-workflow.md`: §3 says the same.
- `plan_specs/.../t28-affected-test-selection.yaml`: the Goal's phase, InProgress at the start and
  Succeeded at the end.

## Deviations from the spec

1. **The root conftest's imports count only for the tests that use its fixtures (PM ruling
   needed).**
   - **What the PM note said.** "A conftest's imports count for every test beneath it." Every test
     is beneath the root `conftest.py`. It imports `debate_core.testing`, whose `__init__` imports
     `fakes`, which imports caselist suppression. It also imports the model-router port, which
     imports `settings`, which imports `debate_core.evidence`. Together that is 68 of the 206
     package modules.
   - **What the literal rule would cost.** 9 of the last 20 task commits become the whole selection,
     13 of 20 with the `pyproject.toml` ones.
   - **What I did instead, for the root conftest only.** Its autouse fixtures and module-level code
     count for every test, but use no workspace module today. Each of its other fixtures counts for
     the tests, and the conftests, that name it: today that is `model_router`. A file the root
     conftest names by path is still the whole selection.
   - **Why no break is missed.** A module the root conftest imports can affect another test in only
     two ways. If it fails to import, every test fails, including the always-run ones, which are
     always selected. Otherwise it changes what a fixture hands a test. The one gap is a module with
     import-time side effects on global state, and this codebase has none that I know of.
   - **What is unchanged.** Deeper conftests keep the literal rule. The tool prints a note whenever
     the root conftest's imports reach a change, and `test_a_root_conftest_import_no_fixture_uses_...`
     pins the behaviour.
   - **Your call.** Confirm this, or tell me to apply the literal rule.
2. **Every `pyproject.toml` is shared ground, not only the root one.** A package's
   `pyproject.toml` holds its dependencies and entry points. In the 20-commit sample, every commit
   that changed one also changed the root `pyproject.toml` or `uv.lock`, so this cost nothing extra.
3. **Markdown under `site/` or `web/` selects the docs checks.** The PM note said `site/` and `web/`
   select nothing. Both `test_check_command_blocks.py::test_this_repository_passes` and
   `tests/docs/test_check_links.py` scan every tracked Markdown file, so a `site/` Markdown change
   can fail them. Everything else under `site/` and `web/` selects only tests that name it, and the
   tool prints that the pnpm checks are the real ones.
4. **`uv.lock` changed** although `constraints.packages` lists only `pyproject.toml`. Naming grimp
   in the dev dependencies rewrites two lines of the lock.
5. **The planted-break check is marked `slow`.** It takes about 50 s, so it is not on the
   pull-request path. It is a new evidence test, not an existing test moved off the path, so the
   spec's forbidden item does not apply. It runs with
   `uv run pytest -m slow -s -k planted tests/scripts`.

## Decisions and assumptions

1. **One file-level graph.**
   - Its edges come from four sources: grimp's imports between package modules (built with
     `cache_dir=None`, so nothing is saved); `ast` imports for every other Python file; conftest
     scope; and runs.
   - Imports resolve as follows:
     - `tests.fixtures.x` paths resolve from the repository root;
     - relative imports resolve in test folders;
     - a bare `import check_links` resolves to every `check_links.py` outside the packages;
     - `importlib.import_module("x")` with a constant argument counts as an import.
   - A module depends on its parent packages, because importing `a.b.c` runs `a/__init__.py`. That
     single rule is most of why shares are high.
2. **Mentions are searched in string literals only**, not in docstrings or comments. A first version
   searched all text, and docstrings that described `tests/smoke/` made 20 of 20 commits the whole
   selection. Shell scripts are searched whole.
3. **A package module reads only its own package's files.** `settings.py` names a runbook in an
   error message, and that should not select every importer of `settings`. An installed wheel has
   no `docs/`.
4. **Data-file folders.** A data file is also named by the folders it sits in. The walk up its path
   stops at a Python package, at a folder holding tests or a conftest, or at a generic name
   (`tests`, `fixtures`, `data`, `src`, `packages`, `scripts`, `docs`). Names like `v1` and names of
   one or two characters are skipped. The Python files in the walked folders count as readers.
5. **Fallbacks for a data file nothing names.**
   - Inside a package, it selects that package's tests.
   - Anywhere else, the tool reports the whole selection and says why.
   - The known consequence: an unnamed data file sitting directly in a `tests/` test folder is the
     whole selection. That is conservative, and it did not occur in the 20 commits.
6. **Source readers.** A test that calls `ast.parse` and globs or walks a directory is selected for
   any Python change. Seven tests match today, among them `test_verifier.py`'s builders allow-list
   and `test_installation.py`.
7. **Always run:** `tests/architecture/`, `tests/specs/`, `packages/debate_cli/tests/test_app.py`
   and `test_help_rendering.py`. `test_app.py` builds the app through `container.py`, and
   `test_help_rendering.py` covers every registered command's help.
8. **Output.** stdout is one path per line (with `--explain`, `path  <- reason chain`), and stderr
   carries the summary and notes. The whole-selection line goes to stdout. `--run` exits with
   pytest's status, and exit 5 (every test deselected) counts as 0.
9. **grimp's floor is `>=3.0`, not `>=3.17`.** The single-interpreter check reads a specifier such as
   `>=3.17` as a Python version. The lock still pins 3.17, and the tool uses only `build_graph`,
   `modules` and `find_modules_directly_imported_by`.
10. **pytest-testmon.** I agree with leaving it out. It needs a coverage-measured baseline per
    worktree, which is the slow run this replaces, plus state kept between runs, which the spec
    forbids. It also cannot see files a test opens by path or a script it starts with subprocess.

## Operator follow-ups

**ac4: time to choose on your Mac.** Done: the operator ran this on 2026-10-19. The results are
under ac4 above (median 3.1 s, largest 4.1 s). The command is kept here as the record of what was
run (about 1 minute: 20 runs of 2–4 s each).

Where: your Mac, in the task worktree. These are the 20 commits in the ac4 table.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t28-affected-test-selection
for sha in 9101764 9f11fe1 29f074d edf8eba 30c5157 29c8293 387c961 9877884 72c1d05 3f2530b 801883a 993063c 8bbe1cd ea09eb1 0a43e88 d730de0 55d0b4b 1e63363 b0820cf 4c5a766; do uv run scripts/affected_tests.py --diff $sha > /dev/null; done
```

Success looked like 20 lines, most reading `N of M test files (P%) chosen in X s from K changed
files.` and the four `pyproject.toml` commits reading `Chose in X s; ...`, with every X under 10.
That is what the run printed.

**Optional, not needed: one whole-selection run.** The branch touches shared test ground (one
dev-dependency line in `pyproject.toml` and its two lines in `uv.lock`). Under agreement 10's
exception you may want one whole-selection run before the pull request. I don't think it's needed:
grimp was already installed through import-linter, and the one test that reads `pyproject.toml`
for this kind of thing (`test_single_interpreter_source.py`) ran and passes. CI runs everything on
the pull request either way. If you want it (about 6 minutes, same worktree):

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t28-affected-test-selection
uv run pytest -n auto -m "not slow and not live"
```

## Follow-up work

- **Package `__init__` re-exports set most of the selection size.** Four modules drive it.
  - `debate_core/evidence/__init__.py` imports `style_classifier` (among others), so a parser change
    reaches every test that imports any `debate_core.evidence.*` module. That is why commit
    `387c961` selects 91%.
  - `debate_core/testing/__init__.py` imports `fakes`, which imports caselist suppression. That
    puts 62 tests into `3f2530b`'s selection.
  - `debate_cli.container` and `debate_cli.commands/__init__` are reached by every CLI test, as
    expected of a composition root.

  Slimming the first two (importing from submodules rather than the package) would cut typical
  shares sharply. `debate_core.evidence` is v1-e31-t22's ground, and `debate_core.testing` belongs
  with E01 or E02. That is for the PM to place.
- **Shell scripts that name a doc in a message** (`ops/launchd/install.sh`, `scripts/task`) select a
  handful of extra tests when docs change. This costs seconds and is left as is.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, with the phase `Succeeded`. The report reached me without the template's PM review
section, so the PM has added it here; a session leaves that section in place, empty.

**The work itself:**

* **Conservative where it matters.** When the tool cannot tell, it selects more or reports the whole
  selection, and says why. The planted-break check proves it against real modules in all four
  packages, run in a shared clone so the worktree is never written.
* **The planted-break check found a real bug in its own first version,** the generic `data` folder.
  That is the check doing its job.
* **A real failure, caught by using the tool on its own branch:** the single-interpreter test read
  `grimp>=3.17` as a Python version (Decision 9).
* **No saved state, about 3 to 4 s to choose** on my Mac, with shares matching the session's
  row for row.
* **19 mutants, one per selection rule, all caught.** The one survivor became a test.

**Rulings:**

1. **Deviation 1 is accepted.** The root conftest counts only for its fixtures' users, and its
   autouse fixtures and module-level code count for every test. Read literally, the rule would make
   nearly half of all tasks the whole selection, for a gap the codebase does not have: import-time
   side effects on global state. CI runs everything on every pull request, so the narrowing cannot
   let a break merge. If a module ever gains such a side effect, the root conftest's note and
   `test_a_root_conftest_import_no_fixture_uses_...` are where to change it.
2. **Deviations 2 to 5 are accepted.** Every `pyproject.toml` is shared ground; Markdown under
   `site/` and `web/` selects the docs checks, which really do scan it; `uv.lock` is in the change;
   and the planted-break check is a new `slow` test, not an existing one moved off the path.
3. **Decisions 1 to 10 are accepted.** Decision 3 (a package module reads only its own package) and
   Decision 2 (string literals only) are the two that keep shares honest.
4. **Follow-up work: the re-exports.** A median of 79% is real coupling, not rule noise, and the
   session named the four modules behind it. The PM files a task for the next batch to slim
   `debate_core.testing/__init__.py` and `debate_core.evidence/__init__.py` (import from
   submodules), at p2. It starts after v1-e31-t22 closes, since `debate_core.evidence` is that
   task's ground. Success is measured with this tool's own `--diff` table over the same 20 commits.
5. **The optional whole-selection run is not needed.** CI runs it on the pull request.
6. **The merge with v1-e39-t04.** Both change `uv.lock`. This task merges first, and t04 then syncs
   and regenerates the lock (`git checkout --ours uv.lock && uv lock`), never by hand.

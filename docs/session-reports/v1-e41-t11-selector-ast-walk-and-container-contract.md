# Session report: v1-e41-t11-selector-ast-walk-and-container-contract

| | |
|---|---|
| Task | `v1-e41-t11-selector-ast-walk-and-container-contract` — Test selection no longer reads ast.walk( as a directory walk, and a contract keeps debate_api.container imported one way |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t11-selector-ast-walk-and-container-contract.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t11-selector-ast-walk-and-container-contract.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t11-selector-ast-walk-and-container-contract` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`scripts/affected_tests.py` no longer counts a `walk(` called on a name the file binds to the ast
module (`ast.walk(tree)`, or `syntax.walk(tree)` after `import ast as syntax`) as a directory walk.
Every other `walk(` still counts, and so do `rglob`, `glob` and `iterdir`. On a Python change that
nothing names, the files selected drop **from 30 to 20**. All ten that leave read only files they
name. On the parser-only merge `387c961` the selection goes **259 → 253**, and API files go
**10 → 9**.

**PM, look first at:** `test_card_download_image.py` does leave the "every Python change" set, but
**it stays selected on `387c961`**. That is right: its assertion names
`debate_core.integrations.docx_parser.parser`, which `387c961` changed. On `387c961`
`test_landscape_image.py` is the API file that leaves.

A new lint-imports contract says no `debate_api` module but the container may import
`debate_api.container`. It is kept on the tree (**20 kept**), and a planted import breaks it. To make
it bite, it had to be written with `as_packages = false`; the obvious way to write it (the package
listed whole) is kept vacuously. All seven mutants are caught. The affected set (39 files) reached the
115 s limit at about 94% with no failure, so the full run is left to the PR's CI. The changed areas
and the always-run list pass within the limit.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `selector-ast-walk-and-container-contract` (Selector and container contract) | Done | `2134507` (selector), `4f9c4cd` (contract), `6424fb1` (two redundant early returns dropped). The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the selector no longer selects a test for `ast.walk(` alone | PASS | `test_a_syntax_tree_walk_on_one_named_file_is_not_a_directory_walk[ast.walk]` and `[an alias of ast]`: a test that parses one named file and calls `ast.walk`/`syntax.walk` is not selected by a change to `nobody_imports.py`. Real tree: see [The measurement](#the-measurement). Ten files leave the unnamed-change selection. |
| ac1: still selects for `os.walk(` and `Path.walk(` | PASS | `test_a_walk_that_may_list_a_folder_still_reads_every_python_change`, 12 cases: `os.walk`, `from os import walk`, `Path("packages").walk()`, `Path(__file__).parent.walk()`, a path variable's `root.walk()`, `rglob`, `glob`, `iterdir`, both walks in one file, `from ast import walk`, an `ast` alias that is also a parameter, `tree.ast.walk()`. **Real tree, planted:** see [The planted directory walks](#the-planted-directory-walks). Both planted files rejoin the selection (20 → 22). |
| ac1: the 387c961 counts before and after | PASS | `affected_tests.py --diff 387c961 --graph aee0158`: before **259** test files, **10** API; after **253**, **9** API. Six files leave; each is named with its reason under [The measurement](#the-measurement). |
| ac1: the new contract is kept on dev's tree | PASS | `.venv/bin/lint-imports --no-cache --no-logo` → `Contracts: 20 kept, 0 broken.` Local `origin/dev` (`a21bb68`) differs from this branch's base `caf1708` only in t26's smoke-test files and docs, with nothing under `packages/`. `test_the_unmodified_copy_keeps_every_contract` → passes. |
| ac1: broken by a planted import | PASS | See [The contract](#the-contract). A scratch copy of the four package trees with `from debate_api import container` planted inside a function in `debate_api/routes.py`, run against this branch's `pyproject.toml`: `No debate_api module but the composition root imports debate_api.container BROKEN`, `Contracts: 19 kept, 1 broken.`, exit 1. Committed cases: a route module, a new subpackage's `__init__` with a function-level import, and the package's own `__init__`. |
| ac1: tests shown failing first | PASS | **Selector** (before `2134507`'s code, tests only): `2 failed, 12 passed`. The two syntax-tree cases failed with `missing: [], extra: ['tests/readers/test_reader.py']`, and the twelve folder cases passed under the old pattern too. **Contract** (this branch's tests, dev's `pyproject.toml`): `4 failed, 1 passed`. Each planted case failed at `assert result.returncode != 0` (lint-imports exited 0), and `test_every_configured_contract_is_proven_to_fail` failed because a case names a contract that did not exist. The control (`test_the_unmodified_copy_keeps_every_contract`) passed. |
| Node: `uv run pytest tests/scripts -k affected_tests` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts -k affected_tests -q` → `182 passed in 25.53s`. |
| PM: mutants 1–4 (pattern back; `os.walk` not matching; a path variable's `.walk` not matching; the forbidden module mistyped) | PASS (all caught) | See [Mutants](#mutants). Three more were added: a rebound alias, `as_packages` removed, and the lookbehind dropped. All are caught. |
| Forbidden: a test file dropped from a selection where a real directory walk reads it | PASS | Each of the ten files that leave was read by hand. None lists a folder (see the table under [The measurement](#the-measurement)). The ten source readers that stay all call `rglob`, `glob` or `iterdir`. The planted `os.walk` and path-variable `.walk()` rejoin. |
| Forbidden: a contract that is not kept on dev's tree | PASS | 20 kept, above. |

### The measurement

Run as in v1-e39-t23 on t20's parser-only merge `387c961` (22 changed files). Both runs use the
same import graph, `aee0158` (this branch's start, dev's tree). Only the script differs:
"before" is `aee0158`'s `affected_tests.py`, saved to the scratchpad, and "after" is this branch's
final one (`6424fb1`). "API files" means selected files under `packages/debate_api/tests/`.
`S` is the session's scratchpad folder.

```bash
git show aee0158:scripts/affected_tests.py > "${S}/affected_tests_before.py"
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python "${S}/affected_tests_before.py" --diff 387c961 --graph aee0158
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --diff 387c961 --graph aee0158
```

| | Test files | API files |
|---|---|---|
| Before (old pattern) | **259** of 610 | **10** |
| After | **253** of 610 | **9** |

Leaving on `387c961` (6), each previously `reads the Python source of the files it walks, and Python changed`:
`test_landscape_image.py` (API), `test_article_service.py`, `test_federated_ranking.py`,
`test_landscape_report.py`, `test_local_classifier.py`, `test_matcher.py`. No file joins.

`test_card_download_image.py` stays on `387c961`. `--explain` gives it, before and after alike:
`names debate_core.integrations.docx_parser.parser (...parser.py), which changed`. Its assertion is
that the container imports that module, so a change to the parser is a real reason to run it.

**A Python change nothing names** shows the rule by itself. This is a dangling commit, `f44eabf`,
not on the branch: `aee0158` plus a new
`packages/debate_core/src/debate_core/nothing_names_this.py`, measured with
`--diff f44eabf --graph aee0158`. Before **30**, after **20**. The ten that leave are exactly the
test files whose only directory-walk match was `ast.walk(`. The one other such file,
`tests/architecture/test_package_inits_import_nothing.py`, is always run. What each one reads:

| Leaves | What it parses (no folder listed) |
|---|---|
| `debate_api/tests/test_card_download_image.py` | `container.py`, a fixed path |
| `debate_api/tests/test_landscape_image.py` | the renderer module, a fixed path |
| `debate_core/tests/application/test_article_service.py` | `inspect.getsource` of a module it imports |
| `debate_core/tests/application/test_federated_ranking.py` | an imported module's `__file__` |
| `debate_core/tests/application/test_landscape_report.py` | five modules listed by path |
| `debate_core/tests/arguments/landscape/test_local_classifier.py` | `MODULES`, two paths |
| `debate_core/tests/arguments/landscape/test_matcher.py` | `CLASSIFYING_MODULES`, three paths |
| `debate_core/tests/retrieval/test_robots_rules.py` | `resources.files("debate_core.retrieval") / "robots_rules.py"` |
| `tests/evals/parser/test_docx_render.py` | `docx_render.py` beside it |
| `tests/scripts/test_compare_cloud_run.py` | `SCRIPT`, one path |

Each of them is still reached by a change to what it reads, through the import or the named path.
On `387c961`, `--explain` shows four of them selected through those routes (`test_card_download_image.py`,
`test_robots_rules.py`, `test_docx_render.py`, `test_compare_cloud_run.py`).

### The planted directory walks

Two dangling commits, also not on the branch. `75c863d` is `aee0158` plus a planted test in each of
two leaving files: `test_card_download_image.py` gets `assert list(os.walk(REPOSITORY / "packages"))`,
and `test_landscape_image.py` gets `root = REPOSITORY / "packages"; assert list(root.walk())`.
`105c9e9` adds the unnamed module on top. Then
`affected_tests.py --diff 105c9e9 --graph 75c863d` → **22** of 610. Both files are back, each
`<- reads the Python source of the files it walks, and Python changed`.

### The contract

```toml
[[tool.importlinter.contracts]]
name = "No debate_api module but the composition root imports debate_api.container"
type = "forbidden"
as_packages = false
source_modules = ["debate_api", "debate_api.**"]
forbidden_modules = ["debate_api.container"]
```

How it was chosen, each probe run on a scratch copy of the package trees with a plant:

| `source_modules` | dev's tree | plant in a module (`routes_probe.py`) | plant in `debate_api/__init__.py` |
|---|---|---|---|
| `["debate_api"]` | kept | **kept** (vacuous) | not run |
| `["debate_api.*"]` / `["debate_api.**"]` | kept | broken | **kept** |
| `["debate_api", "debate_api.**"]` | kept | not run | **kept** |
| `["debate_api", "debate_api.**"]`, `as_packages = false` | kept | broken | broken |

Listed as a package, `debate_api` contains the container, and import-linter does not check imports
inside one package. With `as_packages = false` each module is a source of its own: `debate_api` is
the `__init__` module alone and `debate_api.**` is every module under it, now and later. The
container is among the sources and never imports itself. Indirect chains are checked too: the
planted `routes.py` import is reported directly and as `debate_api.app -> debate_api.routes -> debate_api.container`.

### Mutants

Each mutant was applied in place by `${S}/mutants.py`, run against the files that cover it, and
restored with `git checkout HEAD -- <file>`; the tree was clean afterwards. Every run had a new,
empty `HYPOTHESIS_STORAGE_DIRECTORY`; none of these tests uses Hypothesis. Selector tests:
`tests/scripts/test_affected_tests.py -k "syntax_tree_walk or may_list_a_folder"`. Contract tests:
`tests/architecture/test_import_contracts.py`. Every catch below fails at an assertion
(`test_affected_tests.py:244`, the selection comparison, or `test_import_contracts.py:263/276`,
`returncode != 0`), not a crash.

| Mutant | Result | Caught by |
|---|---|---|
| 1. The pattern back as it was (`\b(?:rglob\|glob\|iterdir\|walk)\(`) | caught, 2 failed | `[ast.walk]`, `[an alias of ast]`: `extra: ['tests/readers/test_reader.py']` |
| 2. `os.walk(` no longer matching (`- {"os"}`) | caught, 2 failed | `[os.walk]`, `[both walks]`: `missing: [...]` |
| 3. A path variable's `.walk(` no longer matching (only `os` or no plain name counts) | caught, 2 failed | `[a path variable]`, `[an alias rebound]` |
| 4. The forbidden module mistyped (`debate_api.contaner`) | caught, 3 failed | both planted `Violation` cases and the package-init test: lint-imports exits 0 on the plant. Mistyped, the contract is kept vacuously, as the PM expected, so the planted cases are the test that the contract names a real module. |
| 5. A rebound alias still read as the ast module (`return aliases`) | caught, 1 failed | `[an alias rebound]` |
| 6. `as_packages = false` removed | caught, 1 failed | the package-init test |
| 7. The lookbehind dropped, so `tree.ast.walk(` reads as ast's | caught, 1 failed | `[an attribute named ast]` |

### Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | 39 of 610 files chosen. **Stopped at the 115 s limit** (exit 124) at about 94%, no failure or error in the output. Left to the PR's `ci` check under agreement 10. |
| `... pytest tests/scripts/test_affected_tests.py tests/scripts/test_affected_tests_planted_breaks.py tests/scripts/test_ci_workflow_test_selection.py tests/scripts/test_ci_workflow_test_job.py -n auto -m "not slow and not live"` | `230 passed in 73.68s` |
| `... pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_api/tests/test_auth_pages_and_script.py -n auto -m "not slow and not live"` | `392 passed in 21.63s` |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1694 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (CI's step, its configured scope) | `0 errors, 0 warnings, 0 informations` (29 s) |
| `uv run --frozen pyright` on the four changed Python files | `0 errors`. Pointed at whole `scripts tests/scripts tests/architecture packages/debate_api` it reports 29 errors, all in files this branch does not touch (`scripts/validate_specs.py`, `scripts/run_parser_eval.py`, `tests/scripts/test_compare_card_clusters.py` and others), outside CI's pyright scope. |
| `.venv/bin/lint-imports` / `uv run --frozen python scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` (after `set-phase ... Succeeded`) | `OK: 539 files, 41 epics, 476 tasks, 22 releases` |
| `check_command_blocks.py --base dev` / `docs_index.py --check-descriptions` / `check_links.py` | `OK: no # comments in 627 shell code blocks ... (1 session reports changed since dev)` / `All 61 indexed documents under docs/ have a description` / `OK: 3171 relative links and anchors in 493 Markdown files` |

**What a PR with this change selects.** CI's `ci_test_selection.py` imports the branch's own
`affected_tests.py`, so the new rule chooses this PR's tests: 39 of 610 files. The `pyproject.toml`
change touches only `[tool.importlinter]`, so it selects `tests/architecture` rather than the whole
selection. Under the old rule the ten ast-walk-only files above would have been selected too.

## Files changed

* `scripts/affected_tests.py`: `DIRECTORY_WALK` became `DIRECTORY_LISTING` (`rglob`, `glob`,
  `iterdir`) plus `WALK_CALL`. The new `walks_a_directory` and `ast_module_names` exempt a walk only
  on a name bound to the ast module and to nothing else. The module docstring's "Source readers" item
  says so.
* `tests/scripts/test_affected_tests.py`: 14 cases. 2 syntax-tree walks are not selected, and 12
  walks that may list a folder still are.
* `pyproject.toml`: the 20th import-linter contract.
* `tests/architecture/test_import_contracts.py`: two `Violation` cases and a package-init test for
  the new contract.
* `packages/debate_api/tests/test_auth_pages_and_script.py`: t23's visitor docstring said the
  selector reads any walk as a directory walk. It now says that was true until this task. It also
  points at the contract.

## Deviations from the spec

* **`tests/architecture/test_import_contracts.py` is outside `constraints.packages`.** The packages
  list is `[scripts, tests/scripts, pyproject.toml, packages/debate_api/tests]`. But
  `test_every_configured_contract_is_proven_to_fail` fails for a contract with no planted case, so
  the contract cannot be added without a case there. The spec should list `tests/architecture`.
* **`test_card_download_image.py` does not leave the `387c961` selection.** The PM context expected
  it to. It leaves the "every Python change" set (shown on an unnamed change, 30 → 20), but
  `387c961` changed the parser module its assertion names, so it stays on that merge for that reason.

## Decisions and assumptions

* **How a walk on the ast module is told apart.** The plain name before `.walk(` is read from the
  text. The file's syntax tree, already parsed and cached by `Tree.syntax`, says which names
  `import ast` / `import ast as name` binds. A name counts only if nothing else in the file binds it:
  no assignment, parameter, `def`/`class`, other import, `except ... as`, or match capture.
* **Cases left matching, failing toward more tests:** a bare `walk(` (whether imported from ast or
  os), a walk on an attribute (`self.ast.walk(`), a walk on any expression (`Path(x).walk(`), a
  name bound to the ast module and also to anything else, and any file that does not parse.
* **`as_packages = false`** is the one style difference from the other 19 contracts, all of which
  list whole packages. The probes above show why this contract needs it.
* The selector's two early returns (`if not receivers`, `if None in receivers`) gave the same answer
  as the set difference after them. No mutant could tell them from their absence, so `6424fb1` drops
  them. The measurement was re-run after that commit: identical selections.

## Operator follow-ups

None.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

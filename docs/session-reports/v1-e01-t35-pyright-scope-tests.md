# Session report: v1-e01-t35-pyright-scope-tests

| | |
|---|---|
| Task | `v1-e01-t35-pyright-scope-tests` — CI's pyright covers tests/architecture and tests/smoke |
| Spec | [`plan_specs/v1/e01-repo-foundation/t35-pyright-scope-tests.yaml`](../../plan_specs/v1/e01-repo-foundation/t35-pyright-scope-tests.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t35-pyright-scope-tests` |
| Session status | COMPLETE |

## Summary

CI's pyright step runs a bare `uv run --frozen pyright`, and that run now checks tests/architecture
and tests/smoke as well as packages/. `[tool.pyright]` in pyproject.toml has
`include = ["packages", "tests/architecture", "tests/smoke"]` and `extraPaths = ["scripts"]`. The two
scoped `# pyright: ignore[reportMissingImports]` comments v1-e01-t31 added are removed, because
`check_thin_handlers` and `site_smoke` now resolve from scripts/. The widened run reports 0 errors.
No file in either directory needed a fix: v1-e01-t31's clean state has held, including the smoke
files added since. A planted type error in each directory turns the bare command red. Both mutants
the PM named behave as expected: reverting the include lets the planted errors pass, and dropping
extraPaths fails the two imports. The rest of tests/ stays out of scope.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `pyright-scope` (Pyright scope) | Done | Include widened, extraPaths added, both ignores removed; a type error planted in each directory and then removed. Committed in `516dcad`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `uv run --frozen pyright` with no arguments reports 0 errors and checks tests/architecture and tests/smoke | PASS | `uv run --frozen pyright` → `0 errors, 0 warnings, 0 informations` (23 s). `uv run --frozen pyright --verbose` → `Found 977 source files` and `Looking in extraPath '.../scripts'`. |
| ac1: a planted type error in each directory fails it | PASS | `planted_type_error: int = "not an int"` appended to `tests/architecture/test_thin_handlers.py`, then `uv run --frozen pyright` → exit 1, `test_thin_handlers.py:456:27 - error: Type "Literal['not an int']" is not assignable to declared type "int"`, `1 error`. The same line in `tests/smoke/test_site.py` → exit 1, `test_site.py:86:27 - error: ...`, `1 error`. Each was restored with `git checkout HEAD --`, and the run was green again: `0 errors`, exit 0. |
| ac1: the two scoped ignores are gone | PASS | `grep -rn 'pyright: ignore\[reportMissingImports\]' tests/architecture tests/smoke` → no output. |
| Node `pyright-scope`: Architecture tests pass (`uv run pytest tests/architecture`) | PASS | `.venv/bin/python -m pytest tests/architecture` → `245 passed in 11.03s`. |

### Mutants (agreement 8)

Both mutants were run against the committed config, then reverted with `git checkout HEAD -- pyproject.toml`.
Pyright uses no Hypothesis database, so agreement 8's fresh-database rule doesn't apply.

| Mutant | Expected | Result |
|---|---|---|
| `include` back to `["packages"]`, with both planted errors present | The planted errors pass unseen | `0 errors, 0 warnings, 0 informations`. The widened include is what catches them. |
| `extraPaths = ["scripts"]` deleted, no planted errors | The scripts imports fail to resolve | `test_thin_handlers.py:21:8 - error: Import "check_thin_handlers" could not be resolved (reportMissingImports)`, `test_site.py:44:8 - error: Import "site_smoke" could not be resolved`, `2 errors`. |

### Checks before the report

* Affected set: `uv run scripts/affected_tests.py --run` → `The whole selection is affected: pyproject.toml is shared test ground. CI runs it on the pull request; a session does not`. Nothing more was run (agreement 10). Before editing pyproject.toml I measured the selection for the two test-file edits alone: `uv run scripts/affected_tests.py` listed 44 files. Running them as `.venv/bin/python -m pytest -n auto -m "not slow and not live" -p no:cacheprovider <the 44 files>`, under a 115 s alarm, gave `2027 passed in 103.51s`.
* `tests/smoke/test_site.py`'s two tests are both `live` (they fetch the real site), so no session runs them. `pytest tests/smoke/test_site.py -m '' --co` → `2 tests collected`: the module, and its `site_smoke` import, still load without the ignore.
* `uv run --frozen ruff format --check .` → `1603 files already formatted`; `uv run --frozen ruff check .` → `All checks passed!`.
* `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 494 files, 40 epics, 432 tasks, 22 releases`.

## Files changed

* `pyproject.toml`: `[tool.pyright]` gains the two directories in `include` and `extraPaths = ["scripts"]`, with a short comment that CI's bare run makes `include` its whole scope.
* `tests/architecture/test_thin_handlers.py`, `tests/smoke/test_site.py`: the scoped `# pyright: ignore[reportMissingImports]` is removed from the scripts import; `# noqa: E402` stays. Test behaviour is unchanged.
* `plan_specs/v1/e01-repo-foundation/t35-pyright-scope-tests.yaml`: Goal phase set to `Succeeded`.
* This report.

## Deviations from the spec

None.

## Decisions and assumptions

* **No new errors to fix.** The PM expected the files added to tests/smoke since 2026-10-23 might bring errors. They don't: the widened run reports 0 errors, so no file outside the spec's packages was touched.
* **Planted errors went into existing files**, not new ones, so the red runs show pyright reading the real modules in each directory.
* **No operator whole-selection run.** Agreement 10 lets a pyproject.toml change go to the operator for one whole run. This edit touches only `[tool.pyright]`, which pytest never reads, so I left the whole selection to the pull request's `ci` check.
* **No sync.** v1-e05-t12 was already in this branch's base. Since then dev has gained only v1-e40-t14 and a refresh of generated files. Neither touches pyproject.toml, tests/architecture or tests/smoke (checked with `git diff --stat HEAD...origin/dev`).

## Operator follow-ups

None.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-30

**Notes:**

CI's bare pyright now covers tests/architecture and tests/smoke, exactly as specified.
1. **ac1 passes, all three parts.**
   * The bare run reports 0 errors over 977 files, with the scripts extraPath in use.
   * A planted error in each directory turns it red, and it is green again after.
   * Both scoped ignores are gone.
2. **Mutants:** both behave as named. The old include lets the planted errors pass, which shows the
   widened include is what catches them. Dropping extraPaths fails the two scripts imports.
3. **No new errors in either directory.** v1-e01-t31's clean state held through this week's smoke
   additions, so nothing outside the packages was touched.
4. **Decisions accepted:**
   * planted errors in existing files;
   * no operator whole-selection run, since `[tool.pyright]` is never read by pytest and the PR's
     `ci` runs the whole selection anyway;
   * no sync needed.
5. **Checks:** the 44 files of the two test edits passed (2,027) before pyproject.toml changed. ruff,
   lint-imports and the specs pass, and `test_site.py` still collects without the ignore.
6. **Merge:** any time.
